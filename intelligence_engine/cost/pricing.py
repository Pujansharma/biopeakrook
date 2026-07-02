"""Per-model token pricing for cost estimation.

Prices are stored as **USD per 1,000,000 tokens** (the unit every provider
publishes), split into input (prompt) and output (completion) rates. The
estimator converts to per-token internally.

Covers the OpenAI, Mistral, and Anthropic/Claude families. This table is the one
place to edit when a provider changes prices or a new model is adopted — keep it
current (see the project rule: always use latest published prices).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ModelPrice:
    """USD per 1,000,000 tokens, input (prompt) and output (completion)."""

    input: float
    output: float


# USD per 1M tokens. Update when providers change pricing.
PRICING: dict[str, ModelPrice] = {
    # --- OpenAI -----------------------------------------------------------
    "gpt-5": ModelPrice(input=1.25, output=10.00),
    "gpt-5-mini": ModelPrice(input=0.25, output=2.00),
    "gpt-5-nano": ModelPrice(input=0.05, output=0.40),
    "gpt-4o": ModelPrice(input=2.50, output=10.00),
    "gpt-4o-mini": ModelPrice(input=0.15, output=0.60),
    "gpt-4.1": ModelPrice(input=2.00, output=8.00),
    "gpt-4.1-mini": ModelPrice(input=0.40, output=1.60),
    "gpt-4.1-nano": ModelPrice(input=0.10, output=0.40),
    "o3": ModelPrice(input=2.00, output=8.00),
    "o4-mini": ModelPrice(input=1.10, output=4.40),
    # --- Anthropic / Claude ----------------------------------------------
    "claude-opus-4-8": ModelPrice(input=5.00, output=25.00),
    "claude-opus-4": ModelPrice(input=15.00, output=75.00),
    "claude-sonnet-5": ModelPrice(input=3.00, output=15.00),
    "claude-sonnet-4": ModelPrice(input=3.00, output=15.00),
    "claude-haiku-4-5": ModelPrice(input=1.00, output=5.00),
    "claude-3-5-haiku": ModelPrice(input=0.80, output=4.00),
    "claude-3-haiku": ModelPrice(input=0.25, output=1.25),
    # --- Mistral ----------------------------------------------------------
    "mistral-large-latest": ModelPrice(input=2.00, output=6.00),
    "mistral-medium-latest": ModelPrice(input=0.40, output=2.00),
    "mistral-small-latest": ModelPrice(input=0.10, output=0.30),
    "pixtral-large-latest": ModelPrice(input=2.00, output=6.00),
    "open-mistral-nemo": ModelPrice(input=0.15, output=0.15),
}

# Fallback when a model is not in the table (logged once per lookup).
DEFAULT_PRICE = ModelPrice(input=1.00, output=3.00)


def price_for(model: str) -> ModelPrice:
    """Return the price for `model`, falling back to DEFAULT_PRICE if unknown."""
    price = PRICING.get(model)
    if price is None:
        logger.warning(
            "[cost] no pricing for model %r; using DEFAULT_PRICE (%s)",
            model,
            DEFAULT_PRICE,
        )
        return DEFAULT_PRICE
    return price
