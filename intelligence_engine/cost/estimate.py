"""Token counting and cost estimation.

Given the model that will run a call and the number of input tokens, estimate
the output tokens from the task type and compute the dollar cost from the
pricing table. If the caller already knows the output token count, it is used
verbatim instead of being estimated.

Output-token estimation by task type:
    - "summary"     -> output is 30% of input (condensing).
    - "translation" -> output is 100% of input (OCR / rewriting, ~1:1).
    - "reasoning"   -> output is 50% of input (high-order thinking).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from intelligence_engine.cost.pricing import price_for

try:  # optional dependency; degrade gracefully to a char heuristic
    import tiktoken

    _HAS_TIKTOKEN = True
except ImportError:  # pragma: no cover - environment-dependent
    tiktoken = None
    _HAS_TIKTOKEN = False

logger = logging.getLogger(__name__)

# Output-to-input token ratio per task type.
OUTPUT_RATIO: dict[str, float] = {
    "summary": 0.30,
    "translation": 1.00,
    "reasoning": 0.50,
}

# Fallback when the text can't be tokenised with tiktoken: ~4 chars/token.
_CHARS_PER_TOKEN = 4


@dataclass(frozen=True)
class CostEstimate:
    """A single call's estimated token usage and dollar cost."""

    model: str
    input_tokens: int
    output_tokens: int
    input_cost: float
    output_cost: float
    total_cost: float


def count_tokens(text: str, model: str) -> int:
    """Count tokens in `text` for `model`.

    Uses tiktoken when available (model-specific encoding, falling back to
    o200k_base), otherwise a ~4-chars-per-token heuristic so a missing tiktoken
    never breaks estimation.
    """
    if not text:
        return 0
    if not _HAS_TIKTOKEN:
        return max(1, len(text) // _CHARS_PER_TOKEN)
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        encoding = tiktoken.get_encoding("o200k_base")
    return len(encoding.encode(text))


def estimate_output_tokens(
    input_tokens: int,
    task_type: str,
    output_tokens: int | None = None,
) -> int:
    """Return `output_tokens` if given, else estimate from `task_type` ratio."""
    if output_tokens is not None:
        return output_tokens
    ratio = OUTPUT_RATIO.get(task_type)
    if ratio is None:
        logger.warning(
            "[cost] unknown task_type %r; defaulting output ratio to reasoning (0.50)",
            task_type,
        )
        ratio = OUTPUT_RATIO["reasoning"]
    return round(input_tokens * ratio)


def estimate_cost(
    model: str,
    input_tokens: int,
    task_type: str,
    output_tokens: int | None = None,
) -> CostEstimate:
    """Estimate the dollar cost of one LLM call.

    Args:
        model: the model that will run the call (drives pricing).
        input_tokens: number of input/prompt tokens.
        task_type: one of "summary", "translation", "reasoning" — drives the
            output-token estimate. Ignored when `output_tokens` is provided.
        output_tokens: known output token count; when given, skips estimation.

    Returns:
        CostEstimate with input/output tokens and input/output/total cost (USD).
    """
    out_tokens = estimate_output_tokens(input_tokens, task_type, output_tokens)
    price = price_for(model)
    input_cost = input_tokens / 1_000_000 * price.input
    output_cost = out_tokens / 1_000_000 * price.output
    return CostEstimate(
        model=model,
        input_tokens=input_tokens,
        output_tokens=out_tokens,
        input_cost=input_cost,
        output_cost=output_cost,
        total_cost=input_cost + output_cost,
    )
