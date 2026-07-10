"""scripts/metabolism_dream.py — Weekly dream cycle entrypoint (V2-D §3).

Reads closed trial_ledger contracts + realized verify outcomes → writes
data/metabolism/preference_prior.json (advisory only, never gate-altering).

Also triggers anti-rot resummary of lessons.jsonl when needed: if lessons.jsonl
exceeds the byte cap, this script requests an LLM-assisted summary (display-tier
only) and calls memory.resummary_lessons() with the result.

INERTNESS: writes artifacts only; dispatches nothing.
Exit 0 always.  NEVER raises at module level.

Usage:
    python -m scripts.metabolism_dream [--root /path/to/repo] [--dry-run]
                                       [--today YYYY-MM-DD]
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
_ROOT = _HERE.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger("metabolism_dream")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


def _check_paused() -> bool:
    """Return True if AUTONOMY_PAUSED is set (and thus we should no-op)."""
    try:
        from scripts.metabolism_guard import is_paused  # type: ignore[import]
        return is_paused()
    except Exception:  # noqa: BLE001
        val = os.environ.get("AUTONOMY_PAUSED", "")
        return bool(val) and val.lower() not in ("false", "0", "")


def _maybe_resummary(root: Path, dry_run: bool) -> None:
    """If lessons.jsonl is over the byte cap, do an LLM-assisted resummary.

    The LLM summary is DISPLAY-TIER ONLY — it never alters gates.
    On dry-run, prints what would be done.  NEVER raises.
    """
    try:
        from engine.metabolism.memory import (  # type: ignore[import]
            _needs_resummary, load_recent_lessons, resummary_lessons, LESSONS_BYTE_CAP,
        )
        if not _needs_resummary(root):
            return

        log.info("dream: lessons.jsonl exceeds %d bytes — triggering anti-rot resummary", LESSONS_BYTE_CAP)
        raw_lessons = load_recent_lessons(root, byte_cap=4000)

        if dry_run:
            log.info("dream: DRY-RUN — would resummary lessons.jsonl (LLM-assisted, display-only)")
            return

        # Attempt LLM-assisted summarization (display-only)
        summary_text = _request_llm_summary(raw_lessons, root)
        if summary_text:
            ok = resummary_lessons(summary_text, root)
            if ok:
                log.info("dream: lessons.jsonl resummary complete")
            else:
                log.warning("dream: lessons.jsonl resummary failed")
        else:
            # No LLM available — write a marker summary
            marker = (
                "[anti-rot marker] LLM summary unavailable — raw tail preserved. "
                "Lessons before the tail were compressed out to prevent context-rot."
            )
            resummary_lessons(marker, root)
    except Exception as exc:  # noqa: BLE001
        log.warning("dream._maybe_resummary: %s", exc)


def _request_llm_summary(raw_lessons: str, root: Path) -> str | None:
    """Request an LLM-assisted summary of the old lessons.

    DISPLAY-TIER ONLY — the summary is advisory context for the next cycle;
    it never alters gates, thresholds, or authority surfaces.

    Returns the summary text, or None if the LLM is unavailable.  NEVER raises.
    """
    try:
        from engine import llm_auth  # type: ignore[import]

        cfg: dict[str, Any] = {
            "provider_order": ["oauth", "anthropic"],
            "oauth_token_env": "CLAUDE_CODE_OAUTH_TOKEN",
            "api_key_env": "ANTHROPIC_API_KEY",
            "opus_model": "claude-opus-4-8",
            "max_tokens": 800,
        }
        providers = llm_auth.build_providers(cfg, opus_model=cfg["opus_model"])
        if not providers:
            return None

        system = (
            "You are a memory-compression assistant for the Metabolism system. "
            "Your task is to write a CONCISE summary of the lessons shown below. "
            "The summary is DISPLAY-ONLY — advisory context for the next proposal cycle. "
            "It NEVER alters gates, thresholds, or authority surfaces. "
            "Focus on: which construction kinds worked, which failed, and what to avoid repeating. "
            "Maximum 300 words. Plain language only — no jargon. "
            "Never use the word 'validated'. Never include signals, scores, or escalations."
        )
        user = (
            "Lessons to summarize (old entries that will be compressed):\n\n"
            + raw_lessons[:4000]
        )

        def _do_call(client: Any, model: str) -> tuple[str | None, str | None]:
            resp = client.messages.create(
                model=model, max_tokens=800, system=system,
                messages=[{"role": "user", "content": user}], temperature=0,
            )
            text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
            return (text.strip() or None), None

        text, _, _ = llm_auth.make_call(providers, _do_call, context="metabolism_dream_resummary")
        return text
    except Exception as exc:  # noqa: BLE001
        log.warning("dream._request_llm_summary: %s", exc)
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Metabolism weekly dream cycle (V2-D §3) — writes preference_prior.json"
    )
    parser.add_argument("--root", default=None, help="Repo root override")
    parser.add_argument("--dry-run", action="store_true", help="Print instead of writing")
    parser.add_argument("--today", default=None, help="Override today date (YYYY-MM-DD)")
    args = parser.parse_args(argv)

    root = Path(args.root) if args.root else _ROOT
    today = args.today

    # is_paused gate — INERTNESS: no-op when paused
    if _check_paused():
        log.info("metabolism_dream: AUTONOMY_PAUSED — no-op")
        return 0

    try:
        from engine.metabolism.dream import run_dream_cycle  # type: ignore[import]
        prior = run_dream_cycle(root=root, today=today, dry_run=args.dry_run)

        if args.dry_run:
            print(json.dumps(prior, indent=2, default=str))
        else:
            log.info(
                "metabolism_dream: prior written (status=%s, n_closed=%s)",
                prior.get("status", "ok"),
                prior.get("n_closed_contracts", "?"),
            )

        # Anti-rot resummary
        _maybe_resummary(root, args.dry_run)

    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_dream.main: %s", exc)

    return 0


if __name__ == "__main__":
    sys.exit(main())
