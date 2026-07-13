"""Extract doctor-facing insights from an uploaded patient document.

Given a raw uploaded file (pdf, docx, jpg, jpeg, png, heic, heif, webp, txt, md)
this module:

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
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
import json

from decouple import config
from pydantic import BaseModel, Field
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
SUPPORTED_EXTENSIONS = {
    "pdf", "docx", "jpg", "jpeg", "png", "heic", "heif", "webp", "txt", "md"
}

# Image extensions that a browser/VLM cannot always consume directly and that we
# transcode to JPEG before OCR. jpg/jpeg/png reach the vision model as-is.
_TRANSCODE_IMAGE_EXTENSIONS = {"heic", "heif", "webp"}

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

# Category precedence (INTERNAL) — used only to order the raw facts fed to the
# consolidation LLM so the most clinically weighty categories appear first and the
# summary paragraph naturally leads with them. Lower number = higher precedence.
_CATEGORY_ORDER: dict[str, int] = {
    "diagnosis": 0,
    "abnormal_measurement": 1,
    "imaging_finding": 2,
    "clinical_finding": 3,
    "symptom": 4,
    "medication": 5,
    "risk_factor": 6,
    "treatment_recommendation": 7,
    "procedure": 8,
    "monitoring_plan": 9,
}
_DEFAULT_CATEGORY_ORDER = 5

_REDACTION = "[REDACTED]"

# Document-level metadata (creation date + issuing facility) is read only from
# the opening pages, where letterheads/headers live — bounding the metadata LLM
# call's input regardless of how long the full document is.
_METADATA_PAGE_LIMIT = 3


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


class Biomarker(BaseModel):
    """One biomarker measurement found in the report.

    Values are kept as strings: short lab values (e.g. "13.5") survive PII
    redaction, and reference ranges are free-form (e.g. "7-40", "<200", "0.4-4.0").
    """

    name: str  # analyte name, e.g. "ALT", "Haemoglobin"
    value: str  # measured value as printed, e.g. "56"
    unit: str | None = None  # e.g. "U/L", "g/dL"; null when not printed
    reference_range: str | None = None  # e.g. "7-40"; null when not printed


class DocumentInsights(BaseModel):
    """The doctor-facing output for one document: a short report title, a
    prioritized summary paragraph (abnormal/critical first), and structured
    biomarker data."""

    doc_id: str
    title: str = ""  # what this report is, e.g. "Comprehensive Metabolic Panel"
    name: str | None = None
    upload_date: str | None = None
    owner: str | None = None
    summary: str  # one paragraph, most critical/abnormal findings first
    report_date: str | None = None  # ISO date the document was created/issued
    report_location: str | None = None  # issuing facility/lab/clinic/author
    is_flagged: bool = False  # something clinically critical the doctor must review
    flag_reason: str = ""  # why it was flagged (abnormal biomarkers + LLM reason)
    contains_biomarkers: bool = False  # true if any biomarker measurement was found
    abnormal_biomarkers: list[Biomarker] = Field(
        default_factory=list,
        description="Out-of-range biomarkers with value, unit, and reference range.",
    )


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
    """One extracted unit of the document, with a stable id."""

    block_id: str
    page: int
    bbox: list[float] | None  # None for sources without coordinates
    text: str


class _BiomarkerLLM(BaseModel):
    """One biomarker measurement as captured from a page (with abnormality)."""

    name: str = Field(description="Analyte name, e.g. 'ALT', 'Haemoglobin'.")
    value: str = Field(description="Measured value as printed, e.g. '56'.")
    unit: str | None = Field(default=None, description="Unit, e.g. 'U/L'; null if not printed.")
    reference_range: str | None = Field(
        default=None,
        description="Reference range as printed, e.g. '7-40'; null if not printed.",
    )
    status: Literal["high", "low", "normal"] = Field(
        description="Whether the value is above ('high'), below ('low'), or within "
        "('normal') its reference range (use the printed range, else the universal one)."
    )


class _InsightLLMItem(BaseModel):
    """One insight as returned by the extraction LLM."""

    title: str = Field(description="Short title for the insight.")
    category: InsightCategory = Field(description="Insight category.")
    content: str = Field(description="Minimal-words insight content.")


class _PageInsights(BaseModel):
    """Structured output of one page's insight-extraction call."""

    insights: list[_InsightLLMItem] = Field(
        default_factory=list,
        description="Patient-specific insights found on this page (may be empty).",
    )
    biomarkers: list[_BiomarkerLLM] = Field(
        default_factory=list,
        description="Biomarker measurements found on this page, in or out of range (may be empty).",
    )


class _RawFact(BaseModel):
    """One patient-specific fact collected from a page, fed to consolidation."""

    page: int
    category: InsightCategory
    content: str


class _ConsolidatedSummary(BaseModel):
    """Structured output of the consolidation LLM call: a report title + summary."""

    title: str = Field(
        description="A short (2-6 word) title naming what this report IS, so a "
        "doctor knows its type at a glance, e.g. 'Comprehensive Metabolic Panel', "
        "'Thyroid Function Panel', 'Gut Microbiome Analysis', 'Thyroid Ultrasound'. "
        "Empty string if the document has no identifiable clinical content."
    )
    summary: str = Field(
        description="One tight paragraph summarizing the whole report, most "
        "abnormal/critical findings first, then the rest. Empty string if nothing "
        "patient-specific was found."
    )
    has_findings: bool = Field(
        default=True,
        description="False if the raw facts do not amount to genuine, coherent "
        "patient-specific clinical content — e.g. they are garbled, "
        "non-clinical, or otherwise unusable. When False, `title` and `summary` "
        "are discarded and returned empty regardless of what was written above.",
    )
    is_flagged: bool = Field(
        default=False,
        description="True only if the document contains something clinically "
        "critical the doctor must not miss (markedly out-of-range value, red-flag "
        "finding, acute/serious diagnosis, urgent recommendation).",
    )
    flag_reason: str = Field(
        default="",
        description="A brief, HIGH-LEVEL phrase (under ~10 words) naming the kind "
        "of critical finding — e.g. 'Markedly elevated HbA1c and lipid panel', "
        "'Red-flag imaging finding'. No values, no exhaustive lists. Empty string "
        "when is_flagged is false.",
    )


class _DocumentMetadata(BaseModel):
    """Document-level header metadata: when and where the document was created.

    Not specific to medical reports — a diet plan, letter, or discharge note all
    carry an issue date and an author/facility. Multiple candidates are common
    (collection vs report vs print date; issuing lab vs referring clinic), so the
    LLM lists every candidate it finds, then selects the single best of each.
    """

    report_date: str | None = Field(
        default=None,
        description="The single best ISO date (YYYY-MM-DD) for when this document "
        "was created/issued/reported. Prefer a report/issue date over a "
        "sample-collection date over a print date. NEVER the patient's date of "
        "birth. Null if the document states no such date.",
    )
    date_candidates: list[str] = Field(
        default_factory=list,
        description="Every date found, each labelled with what the document called "
        "it, e.g. 'Reported On: 2024-03-12', 'Collected: 2024-03-10'. For audit.",
    )
    report_location: str | None = Field(
        default=None,
        description="The single best name of the facility/lab/clinic/organisation "
        "or author that CREATED/ISSUED the document (the letterhead/issuer), not a "
        "referring physician or the patient's address. Null if none is stated.",
    )
    location_candidates: list[str] = Field(
        default_factory=list,
        description="Every candidate issuer found, each with its role, e.g. "
        "'Issuing lab: ABC Diagnostics', 'Referring: Dr X Clinic'. For audit.",
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
    raw = config("INSIGHT_EXTRACTION_TOKEN_LIMIT", default="")
    return int(raw) if raw else None


def _resolve_budget(budget: float | None) -> float | None:
    """Return the explicit `budget`, else INSIGHT_EXTRACTION_BUDGET, else None."""
    if budget is not None:
        return budget
    raw = config("INSIGHT_EXTRACTION_BUDGET", default="")
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
    if ext in ("jpg", "jpeg", "png", "heic", "heif", "webp"):
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
        logger.warning("[cost] input-token pre-read failed for %s: %s", filename, exc, exc_info=True)
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
        title="[MOCK] Comprehensive Metabolic Panel",
        name=meta.get("name"),
        upload_date=meta.get("upload_date"),
        owner=meta.get("owner"),
        summary=(
            "[MOCK] Placeholder report summary; no LLM was called. Critical "
            "findings would lead here, followed by the rest."
        ),
        report_date="2024-03-12",
        report_location="[MOCK] ABC Diagnostics",
        is_flagged=True,
        flag_reason="[MOCK] ALT elevated at 56 U/L.",
        contains_biomarkers=True,
        abnormal_biomarkers=[
            Biomarker(name="[MOCK] ALT", value="56", unit="U/L", reference_range="7-40")
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


# JPEG quality for transcoded heic/heif/webp — high enough to preserve small
# printed lab values, low enough to keep the VLM payload lean.
_TRANSCODE_JPEG_QUALITY = 85


def _transcode_image_to_jpeg(ext: str, data: bytes) -> bytes:
    """Decode a heic/heif/webp image and re-encode it as JPEG for the vision model.

    heic/heif need the pillow-heif opener registered; webp is decoded by Pillow's
    stock libwebp support. EXIF orientation is applied (phone-camera heic files
    routinely carry a rotation flag Pillow does not auto-apply), and the image is
    flattened to RGB so JPEG encoding never fails on an alpha/palette mode. Any
    decode failure propagates — the caller's fail-soft path records a skip.
    """
    import io

    from PIL import Image, ImageOps

    if ext in ("heic", "heif"):
        from pillow_heif import register_heif_opener

        register_heif_opener()

    with Image.open(io.BytesIO(data)) as img:
        img = ImageOps.exif_transpose(img)
        img = img.convert("RGB")
        out = io.BytesIO()
        img.save(out, format="JPEG", quality=_TRANSCODE_JPEG_QUALITY)
    logger.info(
        "[transcode] %s -> jpeg (%.1f KB -> %.1f KB)",
        ext,
        len(data) / 1024,
        out.tell() / 1024,
    )
    return out.getvalue()


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
            "  [image] read failed (page %s, %s): %s", page, block_id, exc, exc_info=True
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
    except Exception as exc:
        logger.warning(
            "[pdf] image identity hash failed for xref %s, falling back to "
            "xref-based identity (dedupe may miss this image): %s",
            xref,
            exc,
        )
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
            except Exception as exc:
                logger.warning(
                    "[pdf] get_image_rects failed for xref %s on page %d, "
                    "skipping this image: %s",
                    xref,
                    page_no,
                    exc,
                )
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
            except Exception as exc:
                logger.warning(
                    "[docx] embedded image %d blob read failed, skipping: %s",
                    img_idx,
                    exc,
                )
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
    if ext in _TRANSCODE_IMAGE_EXTENSIONS:
        # heic/heif/webp aren't reliably consumable by the vision model directly;
        # transcode to JPEG first, then read exactly like a native jpg/png.
        filebytestream = _transcode_image_to_jpeg(ext, filebytestream)
        return await _read_image_file(filebytestream, semaphore, handler, client_details)
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


async def _extract_page_insights(
    page: int,
    blocks: list[_Block],
    semaphore: asyncio.Semaphore,
    handler,
) -> _PageInsights:
    """Run the insight LLM over one page's blocks.

    Returns the page's patient-specific facts AND any biomarker measurements (in
    or out of range). No scoring happens here — the summary paragraph is written
    by the consolidation LLM, and biomarker aggregation is deterministic."""
    if not blocks:
        logger.info("[insights] page %d — no blocks, skipping", page)
        return _PageInsights()

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
        logger.warning("[insights] page %d — failed: %s", page, exc, exc_info=True)
        return _PageInsights()

    logger.info(
        "[insights] page %d — %d fact(s), %d biomarker(s) found",
        page,
        len(result.insights),
        len(result.biomarkers),
    )
    for idx, ins in enumerate(result.insights):
        logger.debug(
            f"[insights] page {page} fact {idx}: title={ins.title!r}  "
            f"category={ins.category}  content={ins.content[:100]}..."
        )
    return result


# Lab abnormality flags/markers a report may print next to a value (e.g. "6.1 *H").
# The numeric value belongs in `value`; the high/low signal belongs in `status`.
# Stripped deterministically as a safety net even though the prompt forbids them.
# The flag word must be preceded by a space/asterisk/paren so a real unit letter
# (e.g. the "L" in "56 U/L") is never mistaken for a "low" flag.
_BIOMARKER_FLAG_RE = re.compile(
    r"(?:[*↑↓]+|[\s*(]\(?(?:HH|LL|HI|LO|HIGH|LOW|H|L)\)?)\s*$",
    re.IGNORECASE,
)


def _clean_biomarker_value(value: str) -> str:
    """Strip trailing lab abnormality flags from a biomarker value ('6.1 *H' -> '6.1')."""
    v = (value or "").strip()
    prev = None
    while v and v != prev:
        prev = v
        v = _BIOMARKER_FLAG_RE.sub("", v).strip()
    return v or (value or "").strip()


def _aggregate_biomarkers(
    biomarkers: list[_BiomarkerLLM],
) -> tuple[bool, list[Biomarker]]:
    """Deterministically fold every page's biomarkers into the output shape.

    Dedupe by (name, value) so the same analyte printed on several pages collapses
    to one. `contains_biomarkers` is True if ANY biomarker was seen (in or out of
    range); `abnormal_biomarkers` are the out-of-range ones (status != "normal").
    Values are cleaned of any lab flag marker so `value` stays numeric."""
    seen: set[tuple[str, str]] = set()
    abnormal: list[Biomarker] = []
    for b in biomarkers:
        clean_value = _clean_biomarker_value(b.value)
        key = (b.name.strip().lower(), clean_value.lower())
        if key in seen:
            continue
        seen.add(key)
        if b.status != "normal":
            abnormal.append(
                Biomarker(
                    name=b.name,
                    value=clean_value,
                    unit=b.unit,
                    reference_range=b.reference_range,
                )
            )
    logger.info(
        "[biomarkers] %d reading(s) -> %d unique, %d abnormal",
        len(biomarkers),
        len(seen),
        len(abnormal),
    )
    return bool(biomarkers), abnormal


# Cap how many biomarker names appear in a flag_reason — the reason is meant to
# be a brief, high-level pointer, not an exhaustive value dump.
_MAX_FLAG_BIOMARKER_NAMES = 3


def _resolve_flag(
    abnormal_biomarkers: list[Biomarker],
    llm_is_flagged: bool,
    llm_flag_reason: str,
) -> tuple[bool, str]:
    """Combine the two flag sources into a final (is_flagged, flag_reason).

    A document is flagged if EITHER any out-of-range biomarker was found OR the
    consolidation LLM judged something clinically critical. The reason is kept
    brief and high-level: at most a few biomarker names (never values/ranges,
    never the full list) plus the LLM's own short justification."""
    reasons: list[str] = []
    if abnormal_biomarkers:
        names = [b.name for b in abnormal_biomarkers]
        shown = ", ".join(names[:_MAX_FLAG_BIOMARKER_NAMES])
        remaining = len(names) - _MAX_FLAG_BIOMARKER_NAMES
        suffix = f" (+{remaining} more)" if remaining > 0 else ""
        reasons.append(f"Abnormal biomarkers: {shown}{suffix}.")
    if llm_is_flagged and llm_flag_reason:
        reasons.append(llm_flag_reason)

    is_flagged = bool(abnormal_biomarkers) or llm_is_flagged
    return is_flagged, " ".join(reasons)


async def _consolidate(
    facts: list[_RawFact],
    doc_id: str,
    semaphore: asyncio.Semaphore,
    handler,
    age="?",
    gender="?",
) -> tuple[str, str, bool, str]:
    """Name the report and write ONE prioritized summary paragraph from the raw
    per-page facts, most abnormal/critical findings first. Returns
    (title, summary, is_flagged, flag_reason) — title/summary "" and is_flagged
    False if there is nothing patient-specific. The patient's age/gender are
    passed so the LLM can de-prioritize demographically implausible findings
    (likely data errors)."""
    if not facts:
        return "", "", False, ""

    # Order facts by category precedence so the weightiest ones lead the input
    # (the prompt then keeps the paragraph critical-first).
    ordered = sorted(
        facts, key=lambda f: _CATEGORY_ORDER.get(f.category, _DEFAULT_CATEGORY_ORDER)
    )
    formatted = "\n".join(f"- [{f.category}] (p{f.page}) {f.content}" for f in ordered)
    logger.info("[consolidate] summarizing %d fact(s) ...", len(facts))

    llm = build_llm("consolidate_insights").with_structured_output(_ConsolidatedSummary)
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
            result: _ConsolidatedSummary = await chain.ainvoke(
                {"formatted_facts": formatted, "age": age, "gender": gender},
                config=config,
            )
    except Exception as exc:
        logger.warning(
            "[consolidate] LLM call failed, falling back to joined facts: %s", exc, exc_info=True
        )
        # Degraded fallback: no title, join the (category-ordered) facts so the
        # document is not lost entirely. No flag opinion on this path — the
        # deterministic abnormal-biomarker check still runs in the caller.
        return "", " ".join(f.content.rstrip(".") + "." for f in ordered), False, ""

    has_findings = bool(result.has_findings)
    if not has_findings:
        # The LLM judged its own input facts as not genuine clinical content
        # (garbled, non-clinical, or hallucination-shaped) — discard whatever
        # title/summary/flag it produced rather than trust text built on a
        # premise it just disavowed.
        logger.info(
            "[consolidate] has_findings=False — discarding title/summary/flag"
        )
        return "", "", False, ""

    title = (result.title or "").strip()
    summary = (result.summary or "").strip()
    is_flagged = bool(result.is_flagged)
    flag_reason = (result.flag_reason or "").strip() if is_flagged else ""
    logger.info(
        "[consolidate] title=%r, summary generated (%d chars), is_flagged=%s",
        title,
        len(summary),
        is_flagged,
    )
    return title, summary, is_flagged, flag_reason


async def _extract_document_metadata(
    header_blocks: list[_Block],
    semaphore: asyncio.Semaphore,
    handler,
) -> _DocumentMetadata:
    """Pull document-level creation date + issuing facility from the opening pages.

    Runs one structured LLM call over the first pages' redacted blocks (facility
    names and report dates are not client PII and survive redaction). Robust to
    multiple candidates: the LLM enumerates every date/location it sees, then
    selects the single best of each. Fails soft — any error yields empty metadata
    so document extraction is never aborted by a missing header."""
    if not header_blocks:
        return _DocumentMetadata()

    formatted = _format_blocks(header_blocks)
    llm = build_llm("extract_document_metadata").with_structured_output(_DocumentMetadata)
    template = ChatPromptTemplate.from_messages(
        [
            ("system", prompts.DOC_METADATA_SYSTEM_PROMPT),
            ("human", prompts.DOC_METADATA_HUMAN_PROMPT),
        ]
    )
    chain = template | llm
    config = trace_config(
        handler, {"step": "extract_document_metadata"}, "document_metadata"
    )
    try:
        async with semaphore:
            result: _DocumentMetadata = await chain.ainvoke(
                {"blocks": formatted}, config=config
            )
    except Exception as exc:
        logger.warning("[metadata] extraction failed: %s", exc, exc_info=True)
        return _DocumentMetadata()

    logger.info(
        "[metadata] date=%r (%d candidate(s)), location=%r (%d candidate(s))",
        result.report_date,
        len(result.date_candidates),
        result.report_location,
        len(result.location_candidates),
    )
    return result


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
                        "title": result.title,
                        "summary_chars": len(result.summary),
                        "report_date": result.report_date,
                        "report_location": result.report_location,
                        "is_flagged": result.is_flagged,
                        "flag_reason": result.flag_reason,
                        "contains_biomarkers": result.contains_biomarkers,
                        "abnormal_biomarker_count": len(result.abnormal_biomarkers),
                        "abnormal_biomarkers": [
                            {
                                "name": b.name,
                                "value": b.value,
                                "unit": b.unit,
                                "reference_range": b.reference_range,
                            }
                            for b in result.abnormal_biomarkers
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

    # Group by page and infer page-wise (concurrently, bounded by the semaphore).
    by_page: dict[int, list[_Block]] = {}
    for b in blocks:
        by_page.setdefault(b.page, []).append(b)

    pages = sorted(by_page)
    logger.info("[insights] processing %d page(s) concurrently ...", len(pages))
    logger.debug(f"[insights] page distribution: {dict(sorted((p, len(blocks)) for p, blocks in by_page.items()))}")

    # Document-level metadata (creation date + issuing facility) reads only the
    # opening pages and runs concurrently with the per-page insight extraction,
    # sharing the same semaphore, so it adds no extra wall-clock latency.
    header_blocks = [b for b in blocks if b.page <= _METADATA_PAGE_LIMIT]

    with log_stage("extract:page_insights", doc_id=doc_id, client_id=client_id):
        metadata_result, *page_results = await asyncio.gather(
            _extract_document_metadata(header_blocks, semaphore, handler),
            *(
                _extract_page_insights(page, by_page[page], semaphore, handler)
                for page in pages
            ),
        )

    raw_facts: list[_RawFact] = []
    all_biomarkers: list[_BiomarkerLLM] = []
    for page, result in zip(pages, page_results):
        for item in result.insights:
            raw_facts.append(
                _RawFact(page=page, category=item.category, content=item.content)
            )
        all_biomarkers.extend(result.biomarkers)

    logger.info(
        "[insights] %d raw fact(s), %d biomarker reading(s) collected across all pages",
        len(raw_facts),
        len(all_biomarkers),
    )
    if raw_facts:
        categories = Counter(f.category for f in raw_facts)
        logger.debug(f"[insights] raw facts by category: {dict(categories)}")

    contains_biomarkers, abnormal_biomarkers = _aggregate_biomarkers(all_biomarkers)

    age = (client_details or {}).get("age", "?")
    gender = (client_details or {}).get("gender", "?")
    with log_stage("extract:consolidate", doc_id=doc_id, client_id=client_id):
        title, summary, llm_is_flagged, llm_flag_reason = await _consolidate(
            raw_facts, doc_id, semaphore, handler, age, gender
        )

    is_flagged, flag_reason = _resolve_flag(
        abnormal_biomarkers, llm_is_flagged, llm_flag_reason
    )
    logger.info(
        "=== done: %s — title=%r, summary %d chars, biomarkers=%s (%d abnormal), "
        "flagged=%s ===",
        doc_name,
        title,
        len(summary),
        contains_biomarkers,
        len(abnormal_biomarkers),
        is_flagged,
    )

    return DocumentInsights(
        doc_id=doc_id,
        title=title,
        summary=summary,
        report_date=metadata_result.report_date,
        report_location=metadata_result.report_location,
        is_flagged=is_flagged,
        flag_reason=flag_reason,
        contains_biomarkers=contains_biomarkers,
        abnormal_biomarkers=abnormal_biomarkers,
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
            except Exception as exc:
                logger.warning("[langfuse] client flush failed: %s", exc)

    results: list = []
    for (_idx, report), outcome in zip(to_process, outcomes):
        if isinstance(outcome, BaseException):
            meta = report.get("metadata") or {}
            logger.warning(
                "[extract] document failed (doc_id=%s): %s",
                meta.get("doc_id"),
                outcome,
                exc_info=outcome,
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
