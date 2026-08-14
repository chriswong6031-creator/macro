"""tools/earnings_worker/prompts.py — re-export of the ONE scoring prompt.

THIS FILE NO LONGER DEFINES ANYTHING.  Until 2026-08-14 it opened with "the
scoring prompt (the product)", "The prompt IS the product", and
``PROMPT_VERSION = "equal-v2"`` — and it was imported by nothing.
``grep -rn "earnings_worker.prompts"`` across the repo returned only this file's
own docstring.  Every score ever produced came from the "compact mirror" in
``engine/earnings_qual.py``, so the deliberately-written prompt here — the one
carrying the calibration anchors — had never once executed, while
``config/earnings_qual.yml`` stamped every row ``equal-v2`` after this file.

The measured cost of that split, over the 64 calls scored on 2026-08-14 through
the local Qwen rung: the mirror anchored only "10 = blowout", so 34.4% of
quarters scored >= 9 (metered rungs on the same schema: 8.4%), 45 of 64 sentiment
values landed on two numbers, and the ten-word tone vocabulary collapsed to two.
The anchors that would have prevented that were sitting in this file, unused.

Two copies with a "keep them in sync" comment is a drift bug with a schedule, and
the sync note here is what made the drift feel handled.  The engine is the
importable library and the worker is its consumer, so the engine owns the prompt
and this module re-exports it.  There is nothing left to keep in sync — and
``tests/test_earnings_prompt_quality.py`` fails if this file ever grows its own
copy again.

Callers that used ``prompts.SYSTEM`` / ``prompts.build_user_prompt`` keep working
unchanged; they now get the text that actually runs.
"""
from __future__ import annotations

from pathlib import Path
import sys

# The worker runs from its own checkout (see ops/launchd/run_earnings_worker.sh,
# which passes --repo-root), so the repository root may not be on sys.path yet.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from engine.earnings_qual import (  # noqa: E402
    TAG_TAXONOMY as TAGS,
    TONE_WORDS,
    _SYSTEM_PROMPT as SYSTEM,
    _build_user_prompt,
    prompt_fingerprint,
    resolve_prompt_version,
)

__all__ = [
    "PROMPT_VERSION",
    "SYSTEM",
    "TAGS",
    "TONE_WORDS",
    "build_user_prompt",
    "prompt_fingerprint",
    "resolve_prompt_version",
]

# Derived from the bytes actually sent to the model, never hand-typed.  The
# human-facing label lives in config/earnings_qual.yml; the row stamp is
# `<label>+<this>`.
PROMPT_VERSION = prompt_fingerprint()


def build_user_prompt(
    ticker: str,
    quarter: str | None,
    year: int | None,
    source: str,
    body: str,
) -> str:
    """Compose the user message for one filing.

    `source` in {"transcript", "8k"}.  `body` is the (already-truncated) text.
    Delegates to the engine so the worker and the engine cannot compose
    different user messages from the same inputs.
    """
    return _build_user_prompt(ticker, quarter, year, source, body)
