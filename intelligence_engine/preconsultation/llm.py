"""Shared LLM construction for the preconsultation package.

One place to build a ChatOpenAI for a named task from TASK_CONFIGS, with the
temperature-restriction handling that both summarize.py and extract_insights.py
need. Keeping this here avoids the two modules drifting apart.
"""

from __future__ import annotations

import logging

from langchain_openai import ChatOpenAI

from intelligence_engine.preconsultation.llm_config import TASK_CONFIGS

logger = logging.getLogger(__name__)

# Models that reject a custom `temperature` (only the default of 1 is allowed):
# the GPT-5 family and the o-series reasoning models.
_NO_TEMPERATURE_PREFIXES = ("gpt-5", "o1", "o3", "o4")


def supports_temperature(model: str) -> bool:
    """True unless the model only accepts its default temperature."""
    return not model.lower().startswith(_NO_TEMPERATURE_PREFIXES)


def build_llm(task: str, model: str | None = None) -> ChatOpenAI:
    """Build a ChatOpenAI for `task` from TASK_CONFIGS.

    `model` overrides the configured model for the task when given. For models
    that only accept the default temperature (gpt-5 / o-series), the temperature
    kwarg is omitted entirely rather than sent and rejected by the API.
    """
    cfg = TASK_CONFIGS[task]
    chosen = model or cfg.model
    pass_temperature = supports_temperature(chosen)
    logger.debug(
        "[llm] task=%s model=%s (override=%s, config_default=%s) temperature=%s extra=%s",
        task,
        chosen,
        model,
        cfg.model,
        cfg.temperature if pass_temperature else "default(unset, model-restricted)",
        cfg.extra,
    )
    kwargs = {"max_retries": cfg.max_retries}
    kwargs.update(cfg.extra)  # per-task extra overrides the defaults above
    if pass_temperature:
        kwargs["temperature"] = cfg.temperature
    return ChatOpenAI(model=chosen, **kwargs)
