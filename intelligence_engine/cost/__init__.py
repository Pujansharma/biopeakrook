"""Cost estimation for LLM calls in the intelligence engine.

Estimate the dollar cost of a call from the model, the input token count, and
the task type (which sets how many output tokens to expect). Pricing for the
OpenAI, Mistral, and Anthropic/Claude families lives in `cost.pricing`.

    from intelligence_engine.cost import estimate_cost, count_tokens

    tokens = count_tokens(document_text, "gpt-5-mini")
    est = estimate_cost("gpt-5-mini", tokens, "reasoning")
    print(est.total_cost)
"""

from intelligence_engine.cost.estimate import (
    OUTPUT_RATIO,
    CostEstimate,
    count_tokens,
    estimate_cost,
    estimate_output_tokens,
)
from intelligence_engine.cost.pricing import DEFAULT_PRICE, PRICING, ModelPrice, price_for

__all__ = [
    "CostEstimate",
    "OUTPUT_RATIO",
    "count_tokens",
    "estimate_cost",
    "estimate_output_tokens",
    "ModelPrice",
    "PRICING",
    "DEFAULT_PRICE",
    "price_for",
]
