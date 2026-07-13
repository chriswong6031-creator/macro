"""scripts/metabolism_attention.py — CLI driver for Metabolism Attention Allocation (V9).

INERTNESS: writes data/metabolism/lobe_criticality.json + attention_allocation.json
    + data/metabolism/attention_history.jsonl only.
    Dispatches NOTHING, grants NOTHING, opens NO PR, touches NO lobe roster.

KILL SWITCH: respects AUTONOMY_PAUSED (double-gated — env var + code).
    Unset or non-'false' → clean journaled no-op (exit 0).

Usage:
    python -m scripts.metabolism_attention --cycle-id <id>
    python -m scripts.metabolism_attention --cycle-id <id> --dry-run
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
from engine.metabolism.criticality import build_criticality, CRITICALITY_PATH  # noqa: E402
from engine.metabolism.attention import build_attention, ALLOCATION_PATH  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("metabolism_attention")


def _load_providers(model: str) -> list[dict]:
    """Build the LLM provider waterfall via llm_auth."""
    try:
        from engine.llm_auth import build_providers  # noqa: PLC0415
        cfg = {
            "provider_order": ["oauth", "anthropic"],
            "oauth_token_env": "CLAUDE_CODE_OAUTH_TOKEN",
            "oauth_pool_lane": "metabolism-attention",
            "api_key_env": "ANTHROPIC_API_KEY",
        }
        return build_providers(cfg, opus_model=model)
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_attention: cannot build providers — %s", exc)
        return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Metabolism Attention Allocation stage (V9, INERT)"
    )
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

    # Build providers
    providers = _load_providers(args.model)
    if not providers:
        log.warning(
            "metabolism_attention: no LLM providers available — will produce structural-only allocation"
        )

    log.info("Building criticality for cycle %s …", args.cycle_id)
    if args.dry_run:
        crit = build_criticality(root=root, write=False)
        crit_str = json.dumps(crit, indent=2, ensure_ascii=False)
        print("=== CRITICALITY (dry run) ===")
        print(crit_str)
    else:
        crit = build_criticality(root=root, write=True)
        n_lobes = len(crit.get("lobes") or {})
        log.info("Criticality built (%d lobes)", n_lobes)

    log.info("Building attention allocation for cycle %s …", args.cycle_id)

    if args.dry_run:
        # True dry run: build_attention always writes its artifacts, so build into
        # a throwaway tmp root (configs copied, no data) and print.  providers=[]
        # so a dry run never spends real LLM tokens (structural-only allocation).
        import tempfile  # noqa: PLC0415
        import shutil  # noqa: PLC0415
        tmp_root = Path(tempfile.mkdtemp())
        (tmp_root / "config").mkdir(parents=True)
        (tmp_root / "data" / "metabolism").mkdir(parents=True)
        for cfg_file in ["lobe_charters.yml", "synapse.yml", "metabolism_attention.yml",
                         "metabolism_roles.yml"]:
            src = root / "config" / cfg_file
            dst = tmp_root / "config" / cfg_file
            if src.exists():
                shutil.copy2(src, dst)
        alloc = build_attention(
            cycle_id=args.cycle_id,
            root=tmp_root,
            providers=[],
            model=args.model,
        )
        print("=== ATTENTION ALLOCATION (dry run) ===")
        print(json.dumps(alloc, indent=2, ensure_ascii=False))
        log.info("DRY RUN — not written.")
        return 0

    alloc = build_attention(
        cycle_id=args.cycle_id,
        root=root,
        providers=providers,
        model=args.model,
    )

    out_path = root / ALLOCATION_PATH
    n_focus = len(alloc.get("focus_lobes") or [])
    n_allocs = len(alloc.get("allocations") or {})
    log.info("Wrote %s (%d lobes, %d focus)", out_path, n_allocs, n_focus)
    print(str(out_path))  # last line is the artifact path (consumed by workflow)
    return 0


if __name__ == "__main__":
    sys.exit(main())
