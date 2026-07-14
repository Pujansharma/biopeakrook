"""Shared Langfuse plumbing for the preconsultation package (langfuse v3).

Both features trace to Langfuse but under different environment labels
(summaries vs report parsing), so `environment` is a parameter here. This module
owns the LANGFUSE_BASE_URL -> LANGFUSE_HOST bridge and the handler/client
builders the modules need.

Design (langfuse v3): the v3 CallbackHandler nests its runs under whatever OTEL
span is active. With no active span each `ainvoke` becomes its own root trace, so
`trace_span` opens ONE parent span (`client.start_as_current_span`) for a whole
workflow and keeps it active across every await — the handler's calls then nest
beneath it as a single EXPANDABLE trace. `doc_trace_span` (one document) and
`patient_trace_span` (one client) are the two entry points. The parent span also
carries `user_id` (= client_id, the dimension `fetch_client_spend` queries),
`session_id`, and tags so traces stay filterable by environment + client_id.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager

from decouple import config
from langfuse import Langfuse
from langfuse.langchain import CallbackHandler as LangfuseCallbackHandler

logger = logging.getLogger(__name__)

# Bound the spend query so a slow/unreachable Langfuse never stalls a run: it
# fails fast and cost gating treats spend as 0.0 (fail-open). Tunable via env.
_SPEND_FETCH_TIMEOUT = config("INSIGHT_SPEND_FETCH_TIMEOUT", default=60, cast=float)
# Cap pagination so an enormous trace history can't turn into an unbounded loop.
_SPEND_MAX_PAGES = config("INSIGHT_SPEND_FETCH_MAX_PAGES", default=20, cast=int)


def _credentials_present() -> bool:
    return bool(config("LANGFUSE_SECRET_KEY", default=""))


def _client_kwargs(environment: str) -> dict:
    """Explicit Langfuse credentials read via decouple, passed straight to the
    SDK constructor rather than left for it to pick up from os.environ (which
    is never populated now that scripts don't call load_dotenv)."""
    kwargs = {
        "secret_key": config("LANGFUSE_SECRET_KEY", default=""),
        "public_key": config("LANGFUSE_PUBLIC_KEY", default=""),
        "environment": environment,
    }
    host = config("LANGFUSE_BASE_URL", default="") or config("LANGFUSE_HOST", default="")
    if host:
        kwargs["host"] = host
    return kwargs


def build_callback_handler(environment: str) -> LangfuseCallbackHandler | None:
    """Return a Langfuse callback handler if credentials are present, else None."""
    if not _credentials_present():
        logger.debug("[langfuse] LANGFUSE_SECRET_KEY not set -> tracing disabled")
        return None
    kwargs = _client_kwargs(environment)
    try:
        Langfuse(**kwargs)  # registers/initializes the client the handler binds to
        return LangfuseCallbackHandler(public_key=kwargs["public_key"])
    except Exception as exc:
        logger.warning("Langfuse handler could not be initialized: %s", exc)
        return None


def build_client(environment: str):
    """Return a Langfuse client if credentials are present, else None."""
    if not _credentials_present():
        return None
    try:
        return Langfuse(**_client_kwargs(environment))
    except Exception as exc:
        logger.warning("Langfuse client could not be initialized: %s", exc)
        return None


@contextmanager
def trace_span(
    client,
    trace_name: str,
    trace_meta: dict,
    environment: str,
    tags: list[str] | None = None,
    user_id: str | None = None,
    session_id: str | None = None,
):
    """Open ONE parent Langfuse span for a whole workflow so that every nested
    LangChain call (traced via the yielded CallbackHandler) falls under a single
    EXPANDABLE trace instead of N sibling traces.

    In langfuse v3 a CallbackHandler with no active span makes each `ainvoke` its
    own root trace; they can only be grouped after the fact by session_id. By
    opening `client.start_as_current_span(...)` and keeping it active across all
    the awaits, the handler's runs nest beneath it as child spans of one trace.
    (asyncio.gather wraps coroutines in Tasks that copy the current OTEL context,
    so concurrently-run calls still nest under this parent.)

    Yields (handler, span):
      - handler: v3 CallbackHandler whose runs nest under the active span; also
        carries `lf_run_attrs` for callers using trace_config()/run_metadata().
      - span:    the parent span (or None). Call `span.update_trace(output=...)`
        before the context exits to record the workflow's final result.

    Fully defensive: if the client is absent or the v3 span API is unavailable,
    yields (None, None) so callers degrade to no tracing (fail-open)."""
    if client is None:
        yield None, None
        return
    md = {k: v for k, v in (trace_meta or {}).items() if v is not None}
    span_cm = None
    span = None
    handler = None
    try:
        span_cm = client.start_as_current_span(name=trace_name)
        span = span_cm.__enter__()
        trace_attrs: dict = {}
        if user_id is not None:
            trace_attrs["user_id"] = str(user_id)
        if session_id is not None:
            trace_attrs["session_id"] = str(session_id)
        if tags:
            trace_attrs["tags"] = list(tags)
        if md:
            trace_attrs["metadata"] = md
        if trace_attrs:
            span.update_trace(**trace_attrs)
        handler = LangfuseCallbackHandler()
        run_attrs: dict = {}
        if user_id is not None:
            run_attrs["langfuse_user_id"] = str(user_id)
        if session_id is not None:
            run_attrs["langfuse_session_id"] = str(session_id)
        if tags:
            run_attrs["langfuse_tags"] = list(tags)
        run_attrs.update(md)
        handler.lf_run_attrs = run_attrs
        logger.debug(
            "[langfuse] parent span open: name=%r user_id=%s session_id=%s",
            trace_name,
            user_id,
            session_id,
        )
    except Exception as exc:
        logger.warning(
            "[langfuse] parent span init failed, tracing disabled for this run: %s",
            exc,
        )
        if span_cm is not None:
            try:
                span_cm.__exit__(None, None, None)
            except Exception as cleanup_exc:
                logger.debug(
                    "[langfuse] span cleanup after failed init raised: %s",
                    cleanup_exc,
                )
        yield None, None
        return
    try:
        yield handler, span
    finally:
        try:
            span_cm.__exit__(None, None, None)
        except Exception as exc:
            logger.debug("[langfuse] span __exit__ failed: %s", exc)


def doc_trace_span(
    client,
    metadata: dict,
    environment: str,
    client_id: str,
    strategy_name: str = "default",
):
    """Parent span for one document's extraction: every image read, page
    extraction, and the consolidation call nest under this single trace.
    Grouped by session=doc_id, filterable by user=client_id."""
    doc_id = metadata.get("doc_id")
    trace_meta = {"doc_id": doc_id, "client_id": client_id}
    if metadata.get("upload_date") is not None:
        trace_meta["upload_date"] = metadata.get("upload_date")
    return trace_span(
        client,
        f"extract_insights:{doc_id} [{strategy_name}]",
        trace_meta,
        environment,
        tags=["preconsultation", "extract_insights", f"ocr:{strategy_name}"],
        user_id=client_id,
        session_id=doc_id,
    )


def patient_trace_span(client, client_id: str, environment: str):
    """Parent span for one client's summarization: both LLM calls and both
    reorder passes nest under this single trace, filterable by user=client_id."""
    return trace_span(
        client,
        f"summarize_patient:{client_id}",
        {"client_id": client_id},
        environment,
        tags=["preconsultation", "summarize_patient"],
        user_id=client_id,
        session_id=client_id,
    )


def fetch_client_spend(environment: str, client_id: str) -> float:
    """Return the total USD spent for `client_id` under `environment`, from Langfuse.

    Uses the v3 traces API filtered natively by user_id (= client_id) and
    environment, summing each trace's total_cost across pages. Fully defensive:
    any failure (no credentials, API error) logs a warning and returns 0.0 so
    cost gating never blocks extraction.
    """
    client = build_client(environment)
    if client is None:
        return 0.0
    try:
        return _sum_trace_cost(client, environment, client_id)
    except Exception as exc:
        logger.warning("[langfuse] fetch_client_spend failed: %s", exc)
        return 0.0
    finally:
        try:
            client.flush()
        except Exception as exc:
            logger.warning("[langfuse] client flush failed in fetch_client_spend: %s", exc)


def _sum_trace_cost(client, environment: str, client_id: str) -> float:
    """Page through Langfuse traces (filtered by user_id + environment) and sum cost.

    Each request is bounded by `_SPEND_FETCH_TIMEOUT` (no retries) and the loop by
    `_SPEND_MAX_PAGES`, so a slow or unreachable Langfuse fails fast rather than
    hanging the extraction run."""
    request_options = {
        "timeout_in_seconds": _SPEND_FETCH_TIMEOUT,
        "max_retries": 0,
    }
    total = 0.0
    page = 1
    while page <= _SPEND_MAX_PAGES:
        response = client.api.trace.list(
            user_id=str(client_id),
            environment=environment,
            page=page,
            limit=100,
            request_options=request_options,
        )
        data = getattr(response, "data", None) or []
        for trace in data:
            total += float(getattr(trace, "total_cost", None) or 0)
        meta = getattr(response, "meta", None)
        total_pages = getattr(meta, "total_pages", None) if meta else None
        if not data or (total_pages is not None and page >= total_pages):
            break
        page += 1
    return total


def run_metadata(handler) -> dict:
    """Reserved langfuse run keys + trace metadata stashed on `handler`, or {}.

    For call sites that build a LangChain config directly (not via
    `trace_config`) so their runs are tagged/grouped identically."""
    if handler is None:
        return {}
    return dict(getattr(handler, "lf_run_attrs", {}))


def trace_config(handler, metadata: dict, run_name: str) -> dict:
    """LangChain invoke config that attaches the handler + trace/run metadata."""
    if handler is None:
        return {}
    merged = dict(metadata or {})
    merged.update(run_metadata(handler))
    return {"callbacks": [handler], "metadata": merged, "run_name": run_name}
