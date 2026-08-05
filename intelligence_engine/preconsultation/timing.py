"""Lightweight latency logging for the preconsultation pipeline.

Langfuse spans already record per-call latency, but that is only visible when
tracing is up. These helpers put the same timings in the application log so a
slow run is diagnosable from logs alone, in production, with no Langfuse.

`log_stage` wraps a block (sync or async — it only brackets a `with`, the awaits
happen inside) and logs its wall-clock ms on exit, even on failure. `elapsed_ms`
is the raw primitive for call sites that need the number itself.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from time import perf_counter

logger = logging.getLogger(__name__)


def _ctx_str(ctx: dict) -> str:
    """Render trailing context (e.g. client id, stage) as ' key=value ...'."""
    return "".join(f" {k}={v}" for k, v in ctx.items() if v is not None)


@contextmanager
def log_stage(label: str, log: logging.Logger | None = None, **ctx):
    """Time a block and log its duration in ms at INFO on exit.

    On an exception the duration is still logged (at WARNING, marked FAILED) and
    the exception is re-raised unchanged — this is measurement only, it never
    swallows errors. Usable around async work: `with log_stage(...): await ...`.
    """
    log = log or logger
    start = perf_counter()
    failed = False
    try:
        yield
    except BaseException:
        failed = True
        raise
    finally:
        ms = (perf_counter() - start) * 1000.0
        suffix = _ctx_str(ctx)
        if failed:
            log.warning("[timing] %s FAILED after %.0fms%s", label, ms, suffix)
        else:
            log.info("[timing] %s %.0fms%s", label, ms, suffix)


def elapsed_ms(start: float) -> float:
    """Milliseconds since a `perf_counter()` reading."""
    return (perf_counter() - start) * 1000.0
