"""scripts/metabolism_agenda.py — CLI driver for the Metabolism Agenda stage (V2-A §4).

INERTNESS: writes data/metabolism/agenda/<cycle_id>.json only.
Dispatches NOTHING, grants NOTHING, opens NO PR, touches NO lobe roster.

KILL SWITCH: respects AUTONOMY_PAUSED (double-gated — env var + code).
Unset or non-'false' → clean journaled no-op (exit 0).

Also double-gated to AUTONOMY_PAUSED=='false' exactly (mirrors Phase-A workflows).

Usage:
    python -m scripts.metabolism_agenda --cycle-id <id>
    python -m scripts.metabolism_agenda --cycle-id <id> --dry-run
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

_ROOT_DIR = Path(__file__).resolve().parent.parent
if str(_ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(_ROOT_DIR))

from scripts.metabolism_guard import is_paused, pause_reason  # noqa: E402
from engine.metabolism.agenda import build_agenda, AGENDA_DIR  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("metabolism_agenda")


def _load_providers(model: str) -> list[dict]:
    """Build the LLM provider waterfall via llm_auth."""
    try:
        from engine.llm_auth import build_providers  # noqa: PLC0415
        cfg = {
            "provider_order": ["oauth", "anthropic"],
            "oauth_token_env": "CLAUDE_CODE_OAUTH_TOKEN",
            "api_key_env": "ANTHROPIC_API_KEY",
        }
        return build_providers(cfg, opus_model=model)
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_agenda: cannot build providers — %s", exc)
        return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Metabolism Agenda stage (V2-A, INERT)")
    parser.add_argument("--cycle-id", required=True, help="Cycle id")
    parser.add_argument("--root", default=None, help="Repo root override")
    parser.add_argument("--dry-run", action="store_true", help="Print artifact without writing")
    parser.add_argument("--model", default="claude-opus-4-5", help="LLM model id")
    args = parser.parse_args(argv)

    # KILL SWITCH — double-gated: code check
    if is_paused():
        log.info("AUTONOMY_PAUSED — %s — clean no-op.", pause_reason())
        return 0

    # Double-gate: explicit AUTONOMY_PAUSED env check (mirrors Phase-A workflow pattern)
    ap_raw = os.environ.get("AUTONOMY_PAUSED", "").strip().lower()
    if ap_raw != "false":
        log.info(
            "AUTONOMY_PAUSED=%r (not 'false') — clean no-op (double-gate).",
            os.environ.get("AUTONOMY_PAUSED", "<unset>"),
        )
        return 0

    root = Path(args.root) if args.root else _ROOT_DIR

    # Build providers (Opus model for reasoning)
    providers = _load_providers(args.model)
    if not providers:
        log.warning("metabolism_agenda: no LLM providers available — will produce floor-only agenda")

    log.info("Building agenda for cycle %s …", args.cycle_id)
    agenda = build_agenda(
        cycle_id=args.cycle_id,
        root=root,
        providers=providers,
        model=args.model,
    )

    out_str = json.dumps(agenda, indent=2, ensure_ascii=False)

    if args.dry_run:
        print(out_str)
        log.info("DRY RUN — not written.")
        return 0

    out_path = root / AGENDA_DIR / f"{args.cycle_id}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(out_str, encoding="utf-8")
    n_items = len(agenda.get("items") or [])
    log.info("Wrote %s (%d items)", out_path, n_items)
    print(str(out_path))  # last line is the artifact path (consumed by workflow)
    return 0


if __name__ == "__main__":
    sys.exit(main())
