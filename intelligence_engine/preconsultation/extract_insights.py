"""Extract doctor-facing insights from an uploaded patient document.

Given a raw uploaded file (pdf, docx, jpg, jpeg, png, txt, md) this module:

1. Identifies the file type and reads it accordingly.
2. Reads embedded images / scans / charts with a vision LLM and slots the
   transcribed text back at its native location in the document.
3. Strips PII (client name, emails, phone numbers, long ID-like tokens) before
   anything is sent to the insight LLM.
4. Extracts a small set of patient-specific insights per page (out-of-range
   measurements, client-specific findings, recommendations, monitoring
   checklists) — never generic textbook detail or routine demographics.
5. Tags each insight with a category and a pointer (page + bbox where the
   parser gave us one) back to its source so the doctor can be directed to it.
6. Deduplicates across pages.

Public API:
    extract_insights(filepath, filebytestream, metadata, client_details)
        -> DocumentInsights        # one document
    extract_insights_batch(reports, max_concurrency=5)
        -> list[DocumentInsights]  # many documents, page-wise, bounded fan-out

All LLM/VLM calls are traced in Langfuse under the environment
"preconsultation-report-prasing".
"""

from __future__ import annotations

import asyncio
import base64
import difflib
import hashlib
import logging
import re
import os
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal
import json

from pydantic import BaseModel, Field, computed_field
from langchain_core.messages import HumanMessage
from langchain_core.prompts import ChatPromptTemplate

from intelligence_engine.cost import count_tokens, estimate_cost
from intelligence_engine.preconsultation import prompts
from intelligence_engine.preconsultation.timing import log_stage
from intelligence_engine.preconsultation.llm import build_llm
from intelligence_engine.preconsultation.llm_config import TASK_CONFIGS
from intelligence_engine.preconsultation.langfuse_util import (
    build_client,
    doc_trace_span,
    fetch_client_spend,
    trace_config,
)
from intelligence_engine.preconsultation.validation import (
    validate_extract_identity,
    validate_extract_input,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

LANGFUSE_ENVIRONMENT = "preconsultation-report-prasing"

SUPPORTED_EXTENSIONS = {"pdf", "docx", "jpg", "jpeg", "png", "txt", "md"}

InsightCategory = Literal[
    "abnormal_measurement",
    "symptom",
    "clinical_finding",
    "imaging_finding",
    "diagnosis",
    "medication",
    "procedure",
    "treatment_recommendation",
    "monitoring_plan",
    "risk_factor",
]

# Per-category importance weight (INTERNAL — folded into the existing `necessity`
# field, never exposed separately). A moderate multiplier so clinically weightier
# categories (a diagnosis, an out-of-range measurement) outrank softer ones (a
# monitoring checklist) at equal LLM necessity, while a strongly-necessary
# insight in a lighter category can still beat a weak one in a heavier category.
# Ordering mirrors the precedence stated in CONSOLIDATE_SYSTEM_PROMPT. Tune freely.
_CATEGORY_WEIGHT: dict[str, float] = {
    "diagnosis": 1.00,
    "abnormal_measurement": 0.95,
    "imaging_finding": 0.90,
    "clinical_finding": 0.85,
    "symptom": 0.80,
    "medication": 0.70,
    "risk_factor": 0.65,
    "treatment_recommendation": 0.60,
    "procedure": 0.55,
    "monitoring_plan": 0.50,
}
# Default for any unmapped/paraphrased category.
_DEFAULT_CATEGORY_WEIGHT = 0.5

# Intra-category rank decay: within one category each successive insight (after
# the most necessary) is discounted by this factor ** rank, so a single category
# that produces many insights can't monopolize the top of the list and bury the
# best insight of another category. Mirrors the checklist's _TAG_RANK_DECAY.
_CATEGORY_RANK_DECAY = 0.6

_REDACTION = "[REDACTED]"


# ---------------------------------------------------------------------------
# OCR strategy
#
# Which embedded images get sent to the vision model — and how they are
# rendered — is fully described by an OCRConfig so strategies can be swapped
# and compared (see compare_ocr.py). The five optimizations:
#   1. text-layer routing  — trust a page's text layer; OCR a whole scanned
#      page once instead of cropping its fragmented image XObjects.
#   2. dedupe_images       — OCR each distinct image once (logos/letterheads
#      reused across pages share one transcription).
#   3. boilerplate filter  — drop any image that recurs on many pages (chrome).
#   4. geometry filters    — min side, min area, max aspect ratio.
#   5. payload tuning      — render DPI and image format/quality.
# ---------------------------------------------------------------------------


@dataclass
class OCRConfig:
    # (4) geometry filters — skip tiny noise, extreme aspect ratios.
    min_image_side: float = 20.0
    min_image_area: float = 2500.0
    max_aspect_ratio: float = 12.0
    # (1) text-layer routing.
    text_layer_routing: bool = True
    text_layer_min_chars: int = 0  # >= this on a page ⇒ trust its text layer
    figure_min_side_on_text_page: float = 20.0  # only OCR genuine figures there
    # (2) dedupe identical images (by content hash) across the document.
    #     OCR each distinct image once; reuse the result for all identical copies.
    dedupe_images: bool = True
    # (5) payload tuning.
    render_dpi: int = 150
    image_format: str = "jpeg"  # "jpeg" | "png"
    jpeg_quality: int = 80


# Default strategy used by the pipeline: optimizations 1, 2, 4, 5 all enabled.
DEFAULT_OCR_CONFIG = OCRConfig()

# Reproduces the original behaviour (OCR every image > 40pt, region crops at
# 200 DPI PNG, no routing/dedupe). Kept for before/after comparison.
LEGACY_OCR_CONFIG = OCRConfig(
    min_image_side=40.0,
    min_image_area=0.0,
    max_aspect_ratio=float("inf"),
    text_layer_routing=False,
    dedupe_images=False,
    render_dpi=200,
    image_format="png",
)


@dataclass
class _ImageJob:
    """A planned OCR target: which region of which page to render and read."""

    block_id: str
    page: int
    bbox: list[float] | None  # None ⇒ whole-page render (scanned page)
    identity: str  # content hash for dedupe / boilerplate grouping
    kind: str  # "region" | "full_page"
    width: float
    height: float
    image_bytes: bytes | None = None  # filled in at render time


# ---------------------------------------------------------------------------
# Output models
# ---------------------------------------------------------------------------


class SourceIndex(BaseModel):
    """Where an insight came from. Page is always known; bbox is best-effort."""

    page: int
    bbox: list[float] | None = None  # [x0, y0, x1, y1] in parser coordinates


class Citation(BaseModel):
    """One individual raw fact that was grouped into a parent Insight."""

    fact: str
    page: int
    bbox: list[float] | None = None

    @computed_field
    @property
    def citation(self) -> str:
        """The fact rendered with its page reference, e.g. 'ALT 56 U/L <Page 4>'."""
        return f"{self.fact} <Page {self.page}>"


class Insight(BaseModel):
    id: str
    title: str
    category: InsightCategory
    necessity: int  # 1-100: how necessary it is for the doctor to see this pre-consult
    index: SourceIndex  # primary source (first / lowest page in the group)
    content: str  # brief summary of the group — one sentence for a quick read
    citations: list[Citation] = Field(
        default_factory=list,
        description="Individual raw facts grouped into this insight, each cited as <Page i>.",
    )


class DocumentInsights(BaseModel):
    """The doctor-facing output for one document: metadata + its insights."""

    doc_id: str
    name: str | None = None
    upload_date: str | None = None
    owner: str | None = None
    insights: list[Insight]


class SkippedFile(BaseModel):
    """A document that was not processed, with the reason it was skipped."""

    doc_id: str | None = None
    filename: str | None = None
    reason: str  # "exceeds_token_limit" | "over_budget" | "extraction_failed"
    detail: str  # human-readable explanation (tokens/limit, cost, or error)


class ExtractionRunResult(BaseModel):
    """The result of an extraction run: processed documents plus any skipped ones."""

    results: list[DocumentInsights] = Field(default_factory=list)
    skipped: list[SkippedFile] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal models
# ---------------------------------------------------------------------------


class _Block(BaseModel):
    """One extracted unit of the document, with a stable id for citation."""

    block_id: str
    page: int
    bbox: list[float] | None  # None for sources without coordinates
    text: str


class _InsightLLMItem(BaseModel):
    """One insight as returned by the extraction LLM (page resolved by us)."""

    title: str = Field(description="Short title for the insight.")
    category: InsightCategory = Field(description="Insight category.")
    content: str = Field(description="Minimal-words insight content.")
    source_block_ids: list[str] = Field(
        default_factory=list,
        description="BLOCK_IDs this insight was drawn from, for source tracing.",
    )


class _PageInsights(BaseModel):
    """Structured output of one page's insight-extraction call."""

    insights: list[_InsightLLMItem] = Field(
        default_factory=list,
        description="Patient-specific insights found on this page (may be empty).",
    )


class _GroupLLMItem(BaseModel):
    """One consolidated insight group as returned by the consolidation LLM."""

    title: str = Field(description="Short title for the group.")
    category: InsightCategory = Field(description="Most specific category in the group.")
    necessity: int = Field(
        description="1-100 score for how necessary it is that the doctor see this "
        "before the consultation (use the provided rubric).",
        ge=1,
        le=100,
    )
    content: str = Field(description="One-sentence summary of the grouped facts.")
    source_indices: list[int] = Field(
        description="Indices of the raw facts that belong to this group."
    )
    subset_of: int | None = Field(
        default=None,
        description="0-based position of another group in this output whose content "
        "fully contains this group's content, or null when this group is standalone. "
        "Groups marked as a subset are folded into their parent and dropped.",
    )


class _ConsolidationOutput(BaseModel):
    """Structured output of the consolidation LLM call."""

    groups: list[_GroupLLMItem] = Field(
        default_factory=list,
        description="Consolidated insight groups covering all raw facts.",
    )


# ---------------------------------------------------------------------------
# PII redaction
# ---------------------------------------------------------------------------

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

# Several phone shapes, tried in order from most to least specific.
_PHONE_RES = [
    re.compile(r"\+\d[\d\s().-]{7,}\d"),  # +91 98765 43210, +1-202-...
    re.compile(r"\(\d{3}\)\s*\d{3}[-.\s]?\d{4}"),  # (202) 555-0147
    re.compile(
        r"\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b"
    ),  # 202-555-0147 / 202.555.0147
    re.compile(r"\b\d{5}[-.\s]\d{5}\b"),  # 98765 43210
    re.compile(r"\b\d{10}\b"),  # 2025550147
]

# Any pure number longer than 8 digits.
_LONG_NUMBER_RE = re.compile(r"\b\d{9,}\b")

# Alphanumeric token longer than 8 chars mixing letters AND digits (MRNs,
# accession/order numbers, etc.). Short measurement values stay untouched.
_ALNUM_ID_RE = re.compile(
    r"\b(?=[A-Za-z0-9]*[A-Za-z])(?=[A-Za-z0-9]*\d)[A-Za-z0-9]{9,}\b"
)

# Honorifics / titles that may appear in the name field. These are common words
# and must NOT be fuzzy-matched (doing so would redact unrelated text).
_HONORIFICS = {
    "mr", "mrs", "ms", "miss", "mx", "dr", "doctor", "prof", "professor",
    "sir", "madam", "shri", "smt", "kumari", "kum", "master", "baby",
}

# Alphabetic word, for fuzzy name matching. Numbers/measurements are untouched.
_WORD_RE = re.compile(r"\b[A-Za-z]{3,}\b")

# Similarity threshold above which a word is considered a variant of a name
# token (catches OCR slips and minor misspellings).
_NAME_SIMILARITY = 0.82


def _redact_pii(text: str, client_details: dict) -> str:
    """Strip client-identifying information from a block of text.

    Removes: emails, phone numbers (several patterns), numbers longer than 8
    digits, alphanumeric tokens longer than 8 chars that mix letters and digits,
    and any word similar to a token of the client's name. The name is split into
    its individual words; honorifics (Mr, Dr, ...) are excluded from fuzzy
    matching so common words are not wrongly redacted.
    """
    if not text:
        return text

    original_len = len(text)
    text_before = text

    text = _EMAIL_RE.sub(_REDACTION, text)
    for rx in _PHONE_RES:
        text = rx.sub(_REDACTION, text)
    text = _LONG_NUMBER_RE.sub(_REDACTION, text)
    text = _ALNUM_ID_RE.sub(_REDACTION, text)

    name = (client_details or {}).get("name") or ""
    name_tokens = [
        t.lower()
        for t in re.split(r"\s+", name.strip())
        if len(t) >= 3 and t.lower() not in _HONORIFICS
    ]
    if not name_tokens:
        # DEBUG: show that no name tokens were extracted
        if text != text_before:
            logger.debug(f"[pii] redacted (no name matching): {original_len} → {len(text)} chars")
        return text

    def _redact_if_name(match: re.Match) -> str:
        word = match.group(0)
        wl = word.lower()
        for token in name_tokens:
            if wl == token:
                return _REDACTION
            if difflib.SequenceMatcher(None, wl, token).ratio() >= _NAME_SIMILARITY:
                return _REDACTION
        return word

    text = _WORD_RE.sub(_redact_if_name, text)

    # DEBUG: Show redaction summary
    if text != text_before:
        logger.debug(
            f"[pii] name tokens: {name_tokens}  |  redacted: {original_len} → {len(text)} chars"
        )
    return text


# ---------------------------------------------------------------------------
# Document reading (file-type dispatch)
# ---------------------------------------------------------------------------


def _extension(filepath: str) -> str:
    return Path(filepath).suffix.lower().lstrip(".")


# Model that runs the per-page extraction — drives the pre-flight cost estimate.
_EXTRACT_MODEL = TASK_CONFIGS["extract_insights"].model
# Flat per-image token allowance used only by the lightweight pre-read (real OCR
# token usage is measured later by the actual pipeline).
_IMAGE_TOKEN_ESTIMATE = 800


def _token_limit() -> int | None:
    """Per-file input-token ceiling from INSIGHT_EXTRACTION_TOKEN_LIMIT, or None."""
    raw = os.environ.get("INSIGHT_EXTRACTION_TOKEN_LIMIT")
    return int(raw) if raw else None


def _resolve_budget(budget: float | None) -> float | None:
    """Return the explicit `budget`, else INSIGHT_EXTRACTION_BUDGET, else None."""
    if budget is not None:
        return budget
    raw = os.environ.get("INSIGHT_EXTRACTION_BUDGET")
    return float(raw) if raw else None


def _pre_read_text(ext: str, data: bytes) -> tuple[str, int]:
    """Cheaply extract text + count embedded images from a file for token estimation.

    No OCR / LLM calls — native text only. Returns (text, image_count).

    For PDFs the image_count is the number of images the pipeline would ACTUALLY
    OCR, not the raw count of image references. It reuses `_plan_pdf_images`
    (geometry filters + text-layer routing) and the same dedupe `_read_pdf`
    applies, so a text report decorated with one logo repeated hundreds of times
    per page is not mis-estimated as hundreds of OCR targets (which previously
    inflated the token estimate ~70x and wrongly tripped exceeds_token_limit).
    """
    if ext == "pdf":
        import fitz  # PyMuPDF

        parts: list[str] = []
        with fitz.open(stream=data, filetype="pdf") as doc:
            for page in doc:
                parts.append(page.get_text("text"))
            # Count only images that survive planning; then dedupe identical
            # images to one OCR each, exactly as _read_pdf does.
            jobs, _stats = _plan_pdf_images(doc, DEFAULT_OCR_CONFIG)
            if DEFAULT_OCR_CONFIG.dedupe_images:
                images = len({j.identity for j in jobs})
            else:
                images = len(jobs)
        return "\n".join(parts), images
    if ext == "docx":
        import io

        from docx import Document  # python-docx

        document = Document(io.BytesIO(data))
        parts = [p.text for p in document.paragraphs]
        for table in document.tables:
            for row in table.rows:
                parts.extend(cell.text for cell in row.cells)
        return "\n".join(parts), len(document.inline_shapes)
    if ext in ("txt", "md"):
        return data.decode("utf-8", "ignore"), 0
    if ext in ("jpg", "jpeg", "png"):
        return "", 1
    return "", 0


def _estimate_input_tokens(filename: str, filebytestream: bytes) -> int:
    """Estimate the input tokens the extraction LLM will see for one document.

    Fail-open: if the file can't be pre-read (corrupt/unsupported), log and
    return 0 so the document is neither wrongly token-skipped nor cost-inflated.
    """
    ext = _extension(filename)
    try:
        text, image_count = _pre_read_text(ext, filebytestream)
    except Exception as exc:
        logger.warning("[cost] input-token pre-read failed for %s: %s", filename, exc)
        return 0
    return count_tokens(text, _EXTRACT_MODEL) + image_count * _IMAGE_TOKEN_ESTIMATE


def _mock_document_insights(metadata: dict | None) -> DocumentInsights:
    """Return a fixed dummy result whose shape mirrors a real response.

    doc_id, name, upload_date, and owner are taken from metadata so callers
    can still correlate the result to the input without reading the file or
    making any LLM calls.
    """
    meta = metadata or {}
    doc_id = str(meta.get("doc_id", "mock-doc"))
    return DocumentInsights(
        doc_id=doc_id,
        name=meta.get("name"),
        upload_date=meta.get("upload_date"),
        owner=meta.get("owner"),
        insights=[
            Insight(
                id=f"{doc_id}-0",
                title="[MOCK] Sample Insight",
                category="clinical_finding",
                necessity=50,
                index=SourceIndex(page=1, bbox=None),
                content="[MOCK] This is a placeholder insight; no LLM was called.",
                citations=[
                    Citation(
                        fact="[MOCK] Placeholder fact",
                        page=1,
                        bbox=None,
                    )
                ],
            )
        ],
    )


def _resolve_source(
    filename: str | None,
    filepath: str | None,
    filebytestream: bytes | None,
) -> tuple[str, bytes]:
    """Resolve the document name and its raw bytes from the provided inputs.

    Bytes are taken from `filebytestream` when given; otherwise they are read
    from `filepath`. The name used for file-type detection is `filename` when
    given, otherwise the basename of `filepath`.

    Raises:
        ValueError: neither bytes nor a filepath were provided, or no name
            could be determined for type detection.
        FileNotFoundError: a filepath was given but does not point to a
            readable file.
    """
    name = filename or (Path(filepath).name if filepath else None)

    if filebytestream is not None:
        if not name:
            raise ValueError(
                "filename or filepath is required to detect the file type "
                "when filebytestream is provided."
            )
        return name, filebytestream

    # No bytes provided — fall back to reading from filepath.
    if not filepath:
        raise ValueError(
            "No file content provided: pass filebytestream, or a filepath to "
            "read the bytes from."
        )
    path = Path(filepath)
    if not path.is_file():
        raise FileNotFoundError(
            f"filepath does not point to a readable file: {filepath!r}"
        )
    return name, path.read_bytes()


def _image_mime(image_bytes: bytes) -> str:
    """Detect image MIME type from magic bytes (PNG vs JPEG)."""
    if image_bytes[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    return "image/png"


async def _read_image_block(
    png_bytes: bytes,
    page: int,
    bbox: list[float] | None,
    block_id: str,
    semaphore: asyncio.Semaphore,
    handler,
    client_details: dict | None = None,
) -> _Block | None:
    """Transcribe one image (whole image file, scan, or embedded figure).

    The image itself must reach the vision model unredacted (that's the point
    of OCR), but its transcribed text is redacted immediately on return —
    before it is placed in a `_Block` or logged — so a name visible only as
    pixels (e.g. a letterhead or ID sticker) never survives into a log line,
    a later prompt, or a Langfuse trace as plain text.
    """
    logger.info(
        "  [image] reading %s (page %s, %.1f KB)",
        block_id,
        page,
        len(png_bytes) / 1024,
    )
    b64 = base64.b64encode(png_bytes).decode()
    mime = _image_mime(png_bytes)
    llm = build_llm("read_image")

    msg = HumanMessage(
        content=[
            {"type": "text", "text": prompts.IMAGE_READ_PROMPT},
            {
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{b64}"},
            },
        ]
    )
    config = trace_config(
        handler,
        {"step": "image_read", "page": page, "bbox": bbox},
        f"image_read_p{page}",
    )
    try:
        async with semaphore:
            resp = await llm.ainvoke([msg], config=config)
    except Exception as exc:
        logger.warning(
            "  [image] read failed (page %s, %s): %s", page, block_id, exc
        )
        return None

    text = (resp.content or "").strip()
    if not text:
        logger.info("  [image] no text returned for %s", block_id)
        return None

    text = _redact_pii(text, client_details or {})
    logger.info("  [image] %s → %d chars transcribed", block_id, len(text))
    return _Block(block_id=block_id, page=page, bbox=bbox, text=text)


def _image_identity(doc, xref: int) -> str:
    """Stable identity for an embedded image, for dedupe / boilerplate grouping.

    Hashes the raw image stream so the same logo/letterhead reused across pages
    — even under different xrefs — collapses to one identity.
    """
    try:
        raw = doc.extract_image(xref)["image"]
        return hashlib.md5(raw).hexdigest()
    except Exception:
        return f"xref:{xref}"


def _plan_pdf_images(doc, config: OCRConfig) -> tuple[list[_ImageJob], dict]:
    """Decide which images to OCR for a PDF, per the OCR strategy.

    Returns the planned jobs (without rendered bytes yet) and a stats dict
    counting kept vs. skipped (by reason). Implements optimizations 1, 3, 4;
    dedupe (2) and rendering/payload (5) are applied by the caller.
    """
    import fitz  # PyMuPDF

    stats = {
        "kept_region": 0,
        "kept_fullpage": 0,
        "skip_small": 0,
        "skip_area": 0,
        "skip_aspect": 0,
    }

    jobs: list[_ImageJob] = []
    for page in doc:
        page_no = page.number + 1
        text_chars = len(page.get_text("text").strip())
        has_images = bool(page.get_images(full=True))
        is_text_page = text_chars >= config.text_layer_min_chars

        # (1) Scanned / image-only page: render the whole page once instead of
        # cropping its fragmented image XObjects.
        if config.text_layer_routing and not is_text_page:
            if not has_images and text_chars == 0:
                continue  # blank page — nothing to read
            r = page.rect
            jobs.append(
                _ImageJob(
                    block_id=f"p{page_no}_full",
                    page=page_no,
                    bbox=None,
                    identity=f"fullpage:{page_no}",
                    kind="full_page",
                    width=r.width,
                    height=r.height,
                )
            )
            stats["kept_fullpage"] += 1
            continue

        # Text page (or routing off): consider each embedded image. On a
        # text-rich page only genuine figures are worth OCR (the text layer
        # already carries the prose), so the size bar is higher.
        min_side = (
            config.figure_min_side_on_text_page
            if (config.text_layer_routing and is_text_page)
            else config.min_image_side
        )
        for img_idx, img in enumerate(page.get_images(full=True)):
            xref = img[0]
            ident = _image_identity(doc, xref)
            try:
                rects = page.get_image_rects(xref)
            except Exception:
                rects = []
            for rect_idx, rect in enumerate(rects):
                w, h = rect.width, rect.height
                if w < min_side or h < min_side:
                    stats["skip_small"] += 1
                    continue
                if w * h < config.min_image_area:
                    stats["skip_area"] += 1
                    continue
                aspect = max(w, h) / max(min(w, h), 1e-6)
                if aspect > config.max_aspect_ratio:
                    stats["skip_aspect"] += 1
                    continue
                jobs.append(
                    _ImageJob(
                        block_id=f"p{page_no}_img{img_idx}_{rect_idx}",
                        page=page_no,
                        bbox=[rect.x0, rect.y0, rect.x1, rect.y1],
                        identity=ident,
                        kind="region",
                        width=w,
                        height=h,
                    )
                )
                stats["kept_region"] += 1

    stats["skipped"] = (
        stats["skip_small"]
        + stats["skip_area"]
        + stats["skip_aspect"]
    )
    return jobs, stats


def _render_job(doc, job: _ImageJob, config: OCRConfig) -> bytes:
    """Render a planned job to image bytes (PNG or JPEG) at the configured DPI."""
    import fitz  # PyMuPDF

    page = doc[job.page - 1]
    clip = fitz.Rect(job.bbox) if job.bbox is not None else None
    pix = page.get_pixmap(clip=clip, dpi=config.render_dpi, colorspace=fitz.csRGB)
    if config.image_format == "jpeg":
        return pix.tobytes("jpg", jpg_quality=config.jpeg_quality)
    return pix.tobytes("png")


async def _read_pdf(
    filebytestream: bytes,
    semaphore: asyncio.Semaphore,
    handler,
    ocr_config: OCRConfig = DEFAULT_OCR_CONFIG,
    client_details: dict | None = None,
) -> list[_Block]:
    import fitz  # PyMuPDF

    blocks: list[_Block] = []
    image_coros = []

    with fitz.open(stream=filebytestream, filetype="pdf") as doc:
        num_pages = len(doc)
        logger.info("[pdf] opened — %d pages", num_pages)

        # Native text blocks with bounding boxes (no LLM, fast).
        for page in doc:
            page_no = page.number + 1
            page_blocks_before = len(blocks)
            for idx, block in enumerate(page.get_text("blocks")):
                x0, y0, x1, y1, btext, *_ = block
                btext = btext.strip()
                if not btext:
                    continue
                blocks.append(
                    _Block(
                        block_id=f"p{page_no}_b{idx}",
                        page=page_no,
                        bbox=[x0, y0, x1, y1],
                        text=btext,
                    )
                )
            page_blocks_added = len(blocks) - page_blocks_before
            logger.info(
                "[pdf] page %d/%d — %d text block(s)",
                page_no,
                num_pages,
                page_blocks_added,
            )
            if page_blocks_added > 0:
                logger.debug(f"[pdf] page {page_no} blocks: {', '.join(b.block_id for b in blocks[page_blocks_before:page_blocks_before + page_blocks_added])}")

        # Plan which images to OCR, then dedupe and render only the survivors.
        jobs, stats = _plan_pdf_images(doc, ocr_config)
        logger.info(
            "[pdf] image plan: %d candidate(s) kept "
            "(%d region, %d full-page), %d skipped "
            "(small=%d area=%d aspect=%d)",
            len(jobs),
            stats["kept_region"],
            stats["kept_fullpage"],
            stats["skipped"],
            stats["skip_small"],
            stats["skip_area"],
            stats["skip_aspect"],
        )

        # (2) Dedupe — OCR each distinct image (by content hash) only ONCE.
        # Repeated images that pass the filters are OCR'd a single time; the
        # transcription is cached in memory and reused for every later
        # occurrence of the same image within this file (see block placement
        # below). We keep one representative job per identity to render+read.
        if ocr_config.dedupe_images:
            representatives: dict[str, _ImageJob] = {}
            for j in jobs:
                representatives.setdefault(j.identity, j)
            ocr_jobs = list(representatives.values())
            if len(ocr_jobs) < len(jobs):
                logger.info(
                    "[pdf] dedupe: OCR %d unique image(s), reuse across %d occurrence(s)",
                    len(ocr_jobs),
                    len(jobs),
                )
        else:
            ocr_jobs = jobs

        # (5) Render the representatives at the configured DPI / format.
        for j in ocr_jobs:
            j.image_bytes = _render_job(doc, j, ocr_config)
            image_coros.append(
                _read_image_block(
                    j.image_bytes,
                    j.page,
                    j.bbox,
                    j.block_id,
                    semaphore,
                    handler,
                    client_details,
                )
            )

    if image_coros:
        total_kb = sum(len(j.image_bytes) for j in ocr_jobs) / 1024
        logger.info(
            "[pdf] reading %d image(s) via VLM (%.1f KB total payload) ...",
            len(image_coros),
            total_kb,
        )
        image_blocks = await asyncio.gather(*image_coros)

        if ocr_config.dedupe_images:
            # Cache each unique image's transcription by identity, then place a
            # block for EVERY occurrence of that image in the file (at its own
            # page/bbox), reusing the cached text instead of OCR'ing again.
            text_by_identity: dict[str, str] = {
                j.identity: b.text
                for j, b in zip(ocr_jobs, image_blocks)
                if b is not None
            }
            added = 0
            for j in jobs:
                text = text_by_identity.get(j.identity)
                if not text:
                    continue
                blocks.append(
                    _Block(
                        block_id=j.block_id, page=j.page, bbox=j.bbox, text=text
                    )
                )
                added += 1
            logger.info(
                "[pdf] %d image block(s) placed across %d occurrence(s) "
                "from %d unique transcription(s)",
                added,
                len(jobs),
                len(text_by_identity),
            )
        else:
            added = sum(1 for b in image_blocks if b is not None)
            blocks.extend(b for b in image_blocks if b is not None)
            logger.info("[pdf] %d image block(s) transcribed", added)

    logger.info("[pdf] extraction complete — %d total block(s)", len(blocks))
    return blocks


async def _read_docx(
    filebytestream: bytes,
    semaphore: asyncio.Semaphore,
    handler,
    client_details: dict | None = None,
) -> list[_Block]:
    import io

    from docx import Document  # python-docx

    logger.info("[docx] parsing document ...")
    document = Document(io.BytesIO(filebytestream))
    blocks: list[_Block] = []

    # Paragraphs and table cells -> text blocks (docx has no page/bbox).
    idx = 0
    for para in document.paragraphs:
        text = para.text.strip()
        if text:
            blocks.append(
                _Block(block_id=f"p1_b{idx}", page=1, bbox=None, text=text)
            )
            idx += 1
    for table in document.tables:
        rows = []
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells]
            if any(cells):
                rows.append("\t".join(cells))
        if rows:
            blocks.append(
                _Block(
                    block_id=f"p1_b{idx}",
                    page=1,
                    bbox=None,
                    text="\n".join(rows),
                )
            )
            idx += 1

    # Embedded images -> vision LLM.
    image_coros = []
    img_idx = 0
    for rel in document.part.rels.values():
        if "image" in rel.reltype:
            try:
                png_bytes = rel.target_part.blob
            except Exception:
                continue
            image_coros.append(
                _read_image_block(
                    png_bytes,
                    1,
                    None,
                    f"p1_img{img_idx}",
                    semaphore,
                    handler,
                    client_details,
                )
            )
            img_idx += 1
    logger.info("[docx] %d text block(s) extracted", len(blocks))
    if image_coros:
        logger.info(
            "[docx] reading %d embedded image(s) via VLM ...", len(image_coros)
        )
        image_blocks = await asyncio.gather(*image_coros)
        added = sum(1 for b in image_blocks if b is not None)
        blocks.extend(b for b in image_blocks if b is not None)
        logger.info("[docx] %d image block(s) transcribed", added)

    logger.info("[docx] extraction complete — %d total block(s)", len(blocks))
    return blocks


async def _read_plain_text(filebytestream: bytes) -> list[_Block]:
    logger.info("[txt] parsing plain text ...")
    text = filebytestream.decode("utf-8", errors="replace")
    blocks: list[_Block] = []
    # Split on blank lines into paragraph-sized blocks.
    paragraphs = re.split(r"\n\s*\n", text)
    idx = 0
    for para in paragraphs:
        para = para.strip()
        if para:
            blocks.append(
                _Block(block_id=f"p1_b{idx}", page=1, bbox=None, text=para)
            )
            idx += 1
    logger.info("[txt] %d paragraph block(s) extracted", len(blocks))
    return blocks


async def _read_image_file(
    filebytestream: bytes,
    semaphore: asyncio.Semaphore,
    handler,
    client_details: dict | None = None,
) -> list[_Block]:
    logger.info("[image] reading whole image via VLM ...")
    block = await _read_image_block(
        filebytestream, 1, None, "p1_img0", semaphore, handler, client_details
    )
    return [block] if block is not None else []


async def _read_document(
    filename: str,
    filebytestream: bytes,
    semaphore: asyncio.Semaphore,
    handler,
    ocr_config: OCRConfig = DEFAULT_OCR_CONFIG,
    client_details: dict | None = None,
) -> list[_Block]:
    ext = _extension(filename)
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file type {ext!r}. Supported: {sorted(SUPPORTED_EXTENSIONS)}"
        )
    logger.info(
        "[read] %s detected as .%s (%.1f KB)",
        Path(filename).name,
        ext,
        len(filebytestream) / 1024,
    )

    if ext == "pdf":
        return await _read_pdf(filebytestream, semaphore, handler, ocr_config, client_details)
    if ext == "docx":
        return await _read_docx(filebytestream, semaphore, handler, client_details)
    if ext in {"jpg", "jpeg", "png"}:
        return await _read_image_file(filebytestream, semaphore, handler, client_details)
    # txt, md
    return await _read_plain_text(filebytestream)


# ---------------------------------------------------------------------------
# Insight extraction (per page)
# ---------------------------------------------------------------------------


def _format_blocks(blocks: list[_Block]) -> str:
    return "\n\n".join(
        f"BLOCK_ID: {b.block_id}\nTEXT:\n{b.text}" for b in blocks
    )


def _union_bbox(bboxes: list[list[float]]) -> list[float] | None:
    boxes = [b for b in bboxes if b]
    if not boxes:
        return None
    x0 = min(b[0] for b in boxes)
    y0 = min(b[1] for b in boxes)
    x1 = max(b[2] for b in boxes)
    y1 = max(b[3] for b in boxes)
    return [x0, y0, x1, y1]


async def _extract_page_insights(
    page: int,
    blocks: list[_Block],
    semaphore: asyncio.Semaphore,
    handler,
) -> list[_InsightLLMItem]:
    """Run the insight LLM over one page's blocks.

    Faithful per-page extraction only — no necessity scoring happens here (the
    page schema has no `necessity` field). Demographic-anomaly scoring is applied
    later in _consolidate, where necessity is assigned.
    """
    if not blocks:
        logger.info("[insights] page %d — no blocks, skipping", page)
        return []

    logger.info(
        "[insights] page %d — extracting from %d block(s) ...",
        page,
        len(blocks),
    )

    formatted = _format_blocks(blocks)

    llm = build_llm("extract_insights").with_structured_output(_PageInsights)
    template = ChatPromptTemplate.from_messages(
        [
            ("system", prompts.INSIGHT_SYSTEM_PROMPT),
            ("human", prompts.INSIGHT_HUMAN_PROMPT),
        ]
    )
    chain = template | llm
    config = trace_config(
        handler, {"step": "extract_insights", "page": page}, f"insights_p{page}"
    )
    try:
        async with semaphore:
            result: _PageInsights = await chain.ainvoke(
                {"page": page, "blocks": formatted}, config=config
            )
    except Exception as exc:
        logger.warning("[insights] page %d — failed: %s", page, exc)
        return []

    # DEBUG: Show the insights returned by the LLM
    logger.info(
        "[insights] page %d — %d insight(s) found", page, len(result.insights)
    )
    for idx, ins in enumerate(result.insights):
        logger.debug(
            f"[insights] page {page} insight {idx}: "
            f"title={ins.title!r}  category={ins.category}  "
            f"source_blocks={ins.source_block_ids}  content={ins.content[:100]}..."
        )
    return result.insights


def _wrap_single_citation(ins: Insight, new_id: str) -> Insight:
    return Insight(
        id=new_id,
        title=ins.title,
        category=ins.category,
        necessity=ins.necessity,
        index=ins.index,
        content=ins.content,
        citations=[Citation(fact=ins.content, page=ins.index.page, bbox=ins.index.bbox)],
    )


def _rescore_insights_by_category(insights: list[Insight]) -> list[Insight]:
    """Fold category weight + intra-category rank decay into each insight's
    `necessity`, mirroring the checklist's _score_hypotheses.

        final_necessity = llm_necessity * category_weight * (_CATEGORY_RANK_DECAY ** rank)

    where rank is the insight's position within its OWN category (ordered by base
    score, most-necessary first). Both factors are INTERNAL: the adjusted value
    is written back into the existing `necessity` field — no new field is exposed
    and only this one score leaves the module. Returns new Insight objects; the
    input list is not mutated.
    """
    if not insights:
        return insights

    # First pass: base = llm_necessity * category_weight.
    bases: list[float] = []
    for ins in insights:
        weight = _CATEGORY_WEIGHT.get(ins.category, _DEFAULT_CATEGORY_WEIGHT)
        base = ins.necessity * weight
        bases.append(base)
        logger.debug(
            "[necessity] id=%s category=%r llm_necessity=%d x weight=%.2f -> base=%.2f",
            ins.id,
            ins.category,
            ins.necessity,
            weight,
            base,
        )

    # Group indices by category, rank within each by base desc, apply decay.
    by_cat: dict[str, list[int]] = {}
    for idx, ins in enumerate(insights):
        by_cat.setdefault(ins.category, []).append(idx)

    adjusted: dict[int, int] = {}
    for cat, idxs in by_cat.items():
        idxs.sort(key=lambda i: bases[i], reverse=True)
        logger.debug(
            "[necessity] category=%r has %d insight(s) -> applying intra-category rank decay",
            cat,
            len(idxs),
        )
        for rank, i in enumerate(idxs):
            decay = _CATEGORY_RANK_DECAY**rank
            final = bases[i] * decay
            # Keep within the field's 1-100 range; never drop below 1.
            final_int = max(1, min(100, round(final)))
            adjusted[i] = final_int
            logger.debug(
                "[necessity]   rank=%d id=%s base=%.2f x decay=%.3f -> necessity=%d%s",
                rank,
                insights[i].id,
                bases[i],
                decay,
                final_int,
                "  <-- suppressed by rank" if rank > 0 else "",
            )

    return [
        ins.model_copy(update={"necessity": adjusted[idx]})
        for idx, ins in enumerate(insights)
    ]


def _resolve_subset_target(
    grp_idx: int,
    subset_of: dict[int, int | None],
    built: dict[int, "Insight"],
) -> int:
    """Follow the subset_of chain to the ultimate parent grp_idx (cycle-safe).

    Returns `grp_idx` itself when the group is standalone or its parent chain
    dead-ends at a missing group, a cycle, or itself.
    """
    seen: set[int] = set()
    current = grp_idx
    while True:
        parent = subset_of.get(current)
        if (
            parent is None
            or parent == current
            or parent not in built
            or parent in seen
        ):
            return current
        seen.add(current)
        current = parent


async def _consolidate(
    insights: list[Insight],
    doc_id: str,
    semaphore: asyncio.Semaphore,
    handler,
    age="?",
    gender="?",
) -> list[Insight]:
    """Group raw per-page facts into fewer dense insights, each with citations.

    Sends all facts to gpt-5-nano which returns groups; each group becomes one
    Insight whose `citations` list carries the individual broken-out facts. The
    patient's age/gender are passed so the LLM can lower the necessity of
    findings that are incompatible with or atypical for the demographics.
    """
    if not insights:
        return []

    if len(insights) == 1:
        return [_wrap_single_citation(insights[0], f"{doc_id}-g0")]

    logger.info("[consolidate] grouping %d raw fact(s) ...", len(insights))

    formatted = "\n\n".join(
        f"INDEX: {i}\nCATEGORY: {ins.category}\nPAGE: {ins.index.page}\nCONTENT: {ins.content}"
        for i, ins in enumerate(insights)
    )

    llm = build_llm("consolidate_insights").with_structured_output(_ConsolidationOutput)
    template = ChatPromptTemplate.from_messages(
        [
            ("system", prompts.CONSOLIDATE_SYSTEM_PROMPT),
            ("human", prompts.CONSOLIDATE_HUMAN_PROMPT),
        ]
    )
    chain = template | llm
    config = trace_config(
        handler, {"step": "consolidate_insights"}, "consolidate_insights"
    )

    try:
        async with semaphore:
            result: _ConsolidationOutput = await chain.ainvoke(
                {"formatted_facts": formatted, "age": age, "gender": gender},
                config=config,
            )
    except Exception as exc:
        logger.warning(
            "[consolidate] LLM call failed, returning raw facts: %s", exc
        )
        fallback = [
            _wrap_single_citation(ins, f"{doc_id}-g{i}")
            for i, ins in enumerate(insights)
        ]
        return _rescore_insights_by_category(fallback)

    # DEBUG: Show consolidated groups returned by LLM
    logger.debug(f"[consolidate] LLM returned {len(result.groups)} group(s)")
    for grp_idx, grp in enumerate(result.groups):
        logger.debug(
            f"[consolidate] group {grp_idx}: title={grp.title!r}  category={grp.category}  "
            f"necessity={grp.necessity}  source_indices={grp.source_indices}  content={grp.content[:100]}..."
        )

    covered: set[int] = set()
    built: dict[int, Insight] = {}  # grp_idx -> Insight (before subset folding)
    subset_of: dict[int, int | None] = {}

    for grp_idx, grp in enumerate(result.groups):
        valid = sorted(i for i in grp.source_indices if 0 <= i < len(insights))
        if not valid:
            continue
        covered.update(valid)
        sources = [insights[i] for i in valid]
        built[grp_idx] = Insight(
            id=f"{doc_id}-g{grp_idx}",
            title=grp.title,
            category=grp.category,
            necessity=grp.necessity,
            index=sources[0].index,
            content=grp.content,
            citations=[
                Citation(fact=s.content, page=s.index.page, bbox=s.index.bbox)
                for s in sources
            ],
        )
        subset_of[grp_idx] = grp.subset_of

    # Dedup: fold every group flagged as a subset into its (ultimate) parent,
    # merging citations so nothing is lost, and drop the subset from the output.
    targets = {g: _resolve_subset_target(g, subset_of, built) for g in built}
    grouped: list[Insight] = []
    kept_pos: dict[int, int] = {}  # kept grp_idx -> position in `grouped`
    for grp_idx, insight in built.items():
        if targets[grp_idx] == grp_idx:
            kept_pos[grp_idx] = len(grouped)
            grouped.append(insight)
    for grp_idx, insight in built.items():
        target = targets[grp_idx]
        if target == grp_idx or target not in kept_pos:
            continue
        parent = grouped[kept_pos[target]]
        seen_facts = {(c.fact, c.page) for c in parent.citations}
        for citation in insight.citations:
            if (citation.fact, citation.page) not in seen_facts:
                parent.citations.append(citation)
                seen_facts.add((citation.fact, citation.page))
        logger.debug(
            "[consolidate] group %d folded into %d (subset)", grp_idx, target
        )

    # Any facts the LLM orphaned — add as single-citation insights.
    for i, ins in enumerate(insights):
        if i not in covered:
            logger.warning(
                "[consolidate] orphaned fact at index %d, adding standalone", i
            )
            grouped.append(_wrap_single_citation(ins, f"{doc_id}-g{len(grouped)}"))

    # Fold category weight + intra-category rank decay into `necessity`
    # (INTERNAL — overwrites the existing field; no new field is exposed).
    grouped = _rescore_insights_by_category(grouped)

    # Most necessary first, so the doctor sees what matters at a glance.
    grouped.sort(key=lambda x: x.necessity, reverse=True)
    logger.info(
        "[consolidate] %d raw fact(s) → %d insight(s)", len(insights), len(grouped)
    )
    return grouped


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


async def _aextract_insights(
    filename: str | None,
    filepath: str | None,
    filebytestream: bytes | None,
    metadata: dict,
    client_details: dict,
    semaphore: asyncio.Semaphore,
    langfuse_client,
    ocr_config: OCRConfig = DEFAULT_OCR_CONFIG,
    strategy_name: str = "default",
) -> DocumentInsights:
    doc_name, filebytestream = _resolve_source(filename, filepath, filebytestream)
    logger.info("=== starting extraction: %s [%s] ===", doc_name, strategy_name)

    # One parent Langfuse span per document: every image read, page extraction,
    # and the consolidation call nests beneath it as a single expandable trace
    # (rather than N sibling traces grouped only by session). Metadata carries
    # doc_id + client_id (+ upload_date) so the trace is filterable by client.
    with doc_trace_span(
        langfuse_client,
        metadata,
        LANGFUSE_ENVIRONMENT,
        str(client_details["client_id"]),
        strategy_name,
    ) as (handler, span):
        with log_stage(
            "extract:doc_total",
            doc_id=str(metadata.get("doc_id")),
            client_id=str(client_details.get("client_id", "")),
        ):
            result = await _run_doc_extraction(
                doc_name,
                filebytestream,
                metadata,
                client_details,
                semaphore,
                handler,
                ocr_config,
            )
        # Close out the parent trace with a compact summary of what was produced.
        if span is not None:
            try:
                span.update_trace(
                    output={
                        "insight_count": len(result.insights),
                        "insights": [
                            {
                                "title": i.title,
                                "category": i.category,
                                "necessity": i.necessity,
                            }
                            for i in result.insights
                        ],
                    }
                )
            except Exception as exc:
                logger.warning("[langfuse] trace finalize failed: %s", exc)

    return json.loads(result.model_dump_json())


async def _run_doc_extraction(
    doc_name: str,
    filebytestream: bytes,
    metadata: dict,
    client_details: dict,
    semaphore: asyncio.Semaphore,
    handler,
    ocr_config: OCRConfig,
) -> DocumentInsights:
    """OCR -> PII redaction -> per-page insight extraction -> consolidation for
    one document. All LLM/VLM calls use `handler` so they nest under the active
    parent span (see `_aextract_insights`)."""
    doc_id = str(metadata.get("doc_id"))
    client_id = str((client_details or {}).get("client_id", ""))

    with log_stage("extract:ocr_read", doc_id=doc_id, client_id=client_id):
        blocks = await _read_document(
            doc_name, filebytestream, semaphore, handler, ocr_config, client_details
        )

    # Redact PII before anything reaches the insight LLM.
    logger.info(
        "[pii] redacting client information from %d block(s) ...", len(blocks)
    )
    for b in blocks:
        original = b.text
        b.text = _redact_pii(b.text, client_details)
        if len(original) != len(b.text):
            logger.debug(f"[pii] {b.block_id}: {len(original)} → {len(b.text)} chars")
    logger.info("[pii] done")

    block_lookup = {b.block_id: b for b in blocks}

    # Group by page and infer page-wise (concurrently, bounded by the semaphore).
    by_page: dict[int, list[_Block]] = {}
    for b in blocks:
        by_page.setdefault(b.page, []).append(b)

    pages = sorted(by_page)
    logger.info("[insights] processing %d page(s) concurrently ...", len(pages))
    logger.debug(f"[insights] page distribution: {dict(sorted((p, len(blocks)) for p, blocks in by_page.items()))}")

    with log_stage("extract:page_insights", doc_id=doc_id, client_id=client_id):
        page_results = await asyncio.gather(
            *(
                _extract_page_insights(page, by_page[page], semaphore, handler)
                for page in pages
            )
        )

    raw_insights: list[Insight] = []
    counter = 0
    for page, items in zip(pages, page_results):
        for item in items:
            cited = [
                block_lookup[bid]
                for bid in item.source_block_ids
                if bid in block_lookup
            ]
            bbox = _union_bbox([b.bbox for b in cited if b.bbox])
            src_page = cited[0].page if cited else page
            raw_insights.append(
                Insight(
                    id=f"{doc_id}-{counter}",
                    title=item.title,
                    category=item.category,
                    necessity=50,
                    index=SourceIndex(page=src_page, bbox=bbox),
                    content=item.content,
                )
            )
            counter += 1

    logger.info(
        "[insights] %d raw fact(s) collected across all pages", len(raw_insights)
    )
    if raw_insights:
        categories = Counter(ins.category for ins in raw_insights)
        logger.debug(f"[insights] raw facts by category: {dict(categories)}")
    age = (client_details or {}).get("age", "?")
    gender = (client_details or {}).get("gender", "?")
    with log_stage("extract:consolidate", doc_id=doc_id, client_id=client_id):
        insights = await _consolidate(
            raw_insights, doc_id, semaphore, handler, age, gender
        )
    logger.info("=== done: %s — %d insight(s) ===", doc_name, len(insights))

    # DEBUG: Show final insights
    for ins in insights:
        logger.debug(
            f"[final] {ins.id}: title={ins.title!r}  category={ins.category}  "
            f"necessity={ins.necessity}  page={ins.index.page}  "
            f"citations={len(ins.citations)}"
        )

    return DocumentInsights(
        doc_id=doc_id,
        # name=metadata.get("name"),
        # upload_date=metadata.get("upload_date"),
        # owner=metadata.get("owner"),
        insights=insights,
    )


def _plan_reports(
    reports: list[dict],
    budget: float | None,
    token_limit: int | None,
    environment: str,
) -> tuple[list[tuple[int, dict]], list[SkippedFile]]:
    """Decide which reports to process and which to skip (token limit + budget).

    Returns (to_process, skipped):
      - to_process: (original_index, resolved_report) pairs in input order, with
        the byte source resolved so the pipeline does not re-read from disk.
      - skipped: SkippedFile entries (reason exceeds_token_limit | over_budget).

    Budget gating is per-client: surviving files are grouped by client_id, each
    client's Langfuse spend is fetched, and within the remaining budget the
    cheapest files (by estimated input cost) are taken as a prefix — the first
    file that does not fit and every file after it are skipped.
    """
    planned: list[dict] = []
    for idx, report in enumerate(reports):
        name, data = _resolve_source(
            report.get("filename"), report.get("filepath"), report.get("filebytestream")
        )
        input_tokens = _estimate_input_tokens(name, data)
        est = estimate_cost(_EXTRACT_MODEL, input_tokens, "reasoning")
        planned.append(
            {
                "idx": idx,
                "report": {**report, "filename": name, "filebytestream": data},
                "doc_id": str(report["metadata"].get("doc_id")),
                "filename": name,
                "client_id": str(report["client_details"].get("client_id")),
                "input_tokens": input_tokens,
                "input_cost": est.input_cost,
                "est_cost": est.total_cost,
            }
        )

    skipped_by_idx: dict[int, SkippedFile] = {}
    survivors: list[dict] = []
    for p in planned:
        if token_limit is not None and p["input_tokens"] > token_limit:
            skipped_by_idx[p["idx"]] = SkippedFile(
                doc_id=p["doc_id"],
                filename=p["filename"],
                reason="exceeds_token_limit",
                detail=(
                    f"estimated {p['input_tokens']} input tokens exceeds limit "
                    f"{token_limit}"
                ),
            )
        else:
            survivors.append(p)

    if budget is not None:
        by_client: dict[str, list[dict]] = {}
        for p in survivors:
            by_client.setdefault(p["client_id"], []).append(p)
        kept_idxs: set[int] = set()
        for client_id, items in by_client.items():
            remaining = budget - fetch_client_spend(environment, client_id)
            spent = 0.0
            cutoff = False
            for p in sorted(items, key=lambda x: x["input_cost"]):
                if not cutoff and spent + p["est_cost"] <= remaining:
                    spent += p["est_cost"]
                    kept_idxs.add(p["idx"])
                else:
                    cutoff = True
                    skipped_by_idx[p["idx"]] = SkippedFile(
                        doc_id=p["doc_id"],
                        filename=p["filename"],
                        reason="over_budget",
                        detail=(
                            f"estimated cost ${p['est_cost']:.4f} does not fit the "
                            f"remaining client budget ${max(remaining - spent, 0.0):.4f}"
                        ),
                    )
        survivors = [p for p in survivors if p["idx"] in kept_idxs]

    to_process = [(p["idx"], p["report"]) for p in sorted(survivors, key=lambda x: x["idx"])]
    skipped = [skipped_by_idx[i] for i in sorted(skipped_by_idx)]
    return to_process, skipped


async def _run_reports(
    reports: list[dict],
    max_concurrency: int,
    ocr_config: OCRConfig,
    budget: float | None,
    strategy_name: str,
) -> ExtractionRunResult:
    """Validate, cost-gate, and process a list of reports into an ExtractionRunResult."""
    for report in reports:
        validate_extract_input(
            report.get("filepath"),
            report.get("filebytestream"),
            report.get("filename"),
            report.get("metadata"),
            report.get("client_details"),
        )

    to_process, skipped = _plan_reports(
        reports, _resolve_budget(budget), _token_limit(), LANGFUSE_ENVIRONMENT
    )
    logger.info(
        "=== run: %d document(s) to process, %d skipped, concurrency=%d ===",
        len(to_process),
        len(skipped),
        max_concurrency,
    )

    langfuse_client = build_client(LANGFUSE_ENVIRONMENT)
    try:
        semaphore = asyncio.Semaphore(max_concurrency)
        with log_stage("extract:batch_total", docs=len(to_process)):
            # return_exceptions=True: a single failing document (corrupt file,
            # unsupported type, transient LLM error) is isolated below as a
            # SkippedFile instead of aborting the whole batch.
            outcomes = await asyncio.gather(
                *(
                    _aextract_insights(
                        report.get("filename"),
                        report.get("filepath"),
                        report.get("filebytestream"),
                        report["metadata"],
                        report["client_details"],
                        semaphore,
                        langfuse_client,
                        ocr_config,
                        strategy_name,
                    )
                    for _idx, report in to_process
                ),
                return_exceptions=True,
            )
    finally:
        if langfuse_client is not None:
            try:
                langfuse_client.flush()
            except Exception:
                pass

    results: list = []
    for (_idx, report), outcome in zip(to_process, outcomes):
        if isinstance(outcome, BaseException):
            meta = report.get("metadata") or {}
            logger.warning(
                "[extract] document failed (doc_id=%s): %s",
                meta.get("doc_id"),
                outcome,
            )
            skipped.append(
                SkippedFile(
                    doc_id=(None if meta.get("doc_id") is None else str(meta.get("doc_id"))),
                    filename=report.get("filename"),
                    reason="extraction_failed",
                    detail=str(outcome),
                )
            )
        else:
            results.append(outcome)

    return ExtractionRunResult(results=results, skipped=skipped)


def _run_sync(coro):
    """Run a coroutine to completion from sync code, tolerating a running loop."""
    try:
        asyncio.get_running_loop()
        import nest_asyncio

        nest_asyncio.apply()
    except RuntimeError:
        pass
    return asyncio.run(coro)


async def aextract_insights(
    filepath: str | None = None,
    filebytestream: bytes | None = None,
    metadata: dict | None = None,
    client_details: dict | None = None,
    filename: str | None = None,
    max_concurrency: int = 5,
    ocr_config: OCRConfig = DEFAULT_OCR_CONFIG,
    strategy_name: str = "default",
    budget: float | None = None,
    mock: bool = False,
    debug: bool = False,
) -> ExtractionRunResult:
    """Async core of extract_insights. Await this directly from async code; the
    sync `extract_insights` is a thin wrapper around it. See `extract_insights`
    for full argument documentation."""
    if debug:
        logging.getLogger("intelligence_engine.preconsultation").setLevel(logging.DEBUG)
    else:
        logging.getLogger("intelligence_engine.preconsultation").setLevel(logging.WARNING)
    if mock:
        validate_extract_identity(metadata, client_details)
        return json.loads(
            ExtractionRunResult(
                results=[_mock_document_insights(metadata)]
            ).model_dump_json()
        )

    report = {
        "filepath": filepath,
        "filebytestream": filebytestream,
        "filename": filename,
        "metadata": metadata,
        "client_details": client_details,
    }
    result = await _run_reports(
        [report], max_concurrency, ocr_config, budget, strategy_name
    )
    return json.loads(result.model_dump_json())


async def aextract_insights_batch(
    reports: list[dict],
    max_concurrency: int = 5,
    ocr_config: OCRConfig = DEFAULT_OCR_CONFIG,
    budget: float | None = None,
    mock: bool = False,
    debug: bool = False,
) -> ExtractionRunResult:
    """Async core of extract_insights_batch. See `extract_insights_batch` for
    full argument documentation."""
    if debug:
        logging.getLogger("intelligence_engine.preconsultation").setLevel(logging.DEBUG)
    else:
        logging.getLogger("intelligence_engine.preconsultation").setLevel(logging.WARNING)
    if mock:
        for r in reports:
            validate_extract_identity(r.get("metadata"), r.get("client_details"))
        return json.loads(
            ExtractionRunResult(
                results=[_mock_document_insights(r.get("metadata")) for r in reports]
            ).model_dump_json()
        )

    result = await _run_reports(
        reports, max_concurrency, ocr_config, budget, "default"
    )
    return json.loads(result.model_dump_json())


def extract_insights(
    filepath: str | None = None,
    filebytestream: bytes | None = None,
    metadata: dict | None = None,
    client_details: dict | None = None,
    filename: str | None = None,
    max_concurrency: int = 5,
    ocr_config: OCRConfig = DEFAULT_OCR_CONFIG,
    strategy_name: str = "default",
    budget: float | None = None,
    mock: bool = False,
    debug: bool = False,
) -> ExtractionRunResult:
    """Extract patient-specific insights from one uploaded document.

    Synchronous wrapper around `aextract_insights`.

    The document's bytes come from `filebytestream` if provided; otherwise they
    are read from disk at `filepath`. At least one of the two must be given, and
    a filepath used as the fallback must point to a readable file or an error is
    raised. The file type is detected from `filename` if provided, else from the
    basename of `filepath`.

    Args:
        filepath: path to the file on disk. Read as the byte source when
            `filebytestream` is omitted, and used for type detection when
            `filename` is omitted.
        filebytestream: the file's raw bytes. Takes precedence over `filepath`
            as the byte source; when omitted, the bytes are read from `filepath`.
        metadata: {doc_id, name, upload_date, owner}. doc_id is REQUIRED and
            becomes the document id and the insight-id prefix.
        client_details: {client_id, name, age, gender}. client_id is REQUIRED
            (a ValueError is raised without it); name is used for PII redaction.
        filename: original filename used only to detect the file type. Falls
            back to the basename of `filepath` when omitted.
        max_concurrency: max in-flight LLM/VLM calls.
        ocr_config: OCR strategy for embedded-image handling. Defaults to the
            optimized strategy; pass LEGACY_OCR_CONFIG for the original one.
        strategy_name: label embedded in the Langfuse trace name and tags so
            runs from different strategies are distinguishable side by side.
        budget: per-client USD budget for this run. Falls back to the
            INSIGHT_EXTRACTION_BUDGET env var; when neither is set, no budget
            gating is applied. The document is skipped (reason "over_budget") if
            its estimated cost plus the client's current Langfuse spend exceeds
            the budget. Independently, a document is skipped (reason
            "exceeds_token_limit") when its estimated input tokens exceed the
            INSIGHT_EXTRACTION_TOKEN_LIMIT env var.
        mock: when True, skip file reading and all LLM calls and return a fixed
            dummy result derived from metadata. client_id/doc_id are still
            required. Useful for integration testing without API keys or files.

    Returns:
        ExtractionRunResult with `results` (0 or 1 DocumentInsights) and
        `skipped` (SkippedFile entries). Call .model_dump() for the plain dict.

    Raises:
        ValueError: no byte source given, or metadata/client_details missing the
            required doc_id / client_id.
        FileNotFoundError: `filepath` was used as the fallback but does not
            point to a readable file.
    """
    return _run_sync(
        aextract_insights(
            filepath=filepath,
            filebytestream=filebytestream,
            metadata=metadata,
            client_details=client_details,
            filename=filename,
            max_concurrency=max_concurrency,
            ocr_config=ocr_config,
            strategy_name=strategy_name,
            budget=budget,
            mock=mock,
            debug=debug,
        )
    )


def extract_insights_batch(
    reports: list[dict],
    max_concurrency: int = 5,
    ocr_config: OCRConfig = DEFAULT_OCR_CONFIG,
    budget: float | None = None,
    mock: bool = False,
    debug: bool = False,
) -> ExtractionRunResult:
    """Extract insights from many documents, page-wise, with bounded fan-out.

    Synchronous wrapper around `aextract_insights_batch`.

    Args:
        reports: list of {filepath, filebytestream, metadata, client_details}.
            `filename` is optional; `filebytestream` may be omitted to read the
            bytes from `filepath` instead. Each report's metadata must include a
            doc_id and its client_details a client_id.
        max_concurrency: shared cap on in-flight LLM/VLM calls across ALL
            reports and ALL their pages (enforced via a single asyncio.Semaphore).
        ocr_config: OCR strategy applied to every document.
        budget: per-client USD budget applied to this batch (env fallback
            INSIGHT_EXTRACTION_BUDGET). Files are cost-gated per client: within
            each client's remaining budget the cheapest files (by estimated input
            cost) are taken as a prefix; the first that does not fit and every
            file after it are skipped ("over_budget"). Files whose estimated
            input tokens exceed INSIGHT_EXTRACTION_TOKEN_LIMIT are skipped first
            ("exceeds_token_limit").
        mock: when True, skip file reading and all LLM calls for every report
            and return dummy results derived from each report's metadata.

    Returns:
        ExtractionRunResult with `results` (processed documents) and `skipped`
        (SkippedFile entries). Call .model_dump() for the plain dict.
    """
    return _run_sync(
        aextract_insights_batch(
            reports,
            max_concurrency=max_concurrency,
            ocr_config=ocr_config,
            budget=budget,
            mock=mock,
            debug=debug,
        )
    )
