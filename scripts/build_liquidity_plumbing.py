"""scripts/build_liquidity_plumbing.py — NW Liquidity Plumbing lobe builder (Phase 0+1).

DISPLAY / SHADOW tier. DE-ESCALATION-ONLY authority. Zero scored surfaces.

Reads existing data stores, assembles the liquidity_plumbing.v1 lobe payload,
stamps it via engine.neuralweb.envelope.stamp(), and atomically writes:
    data/neuralweb/liquidity_plumbing.json   (primary; git-committed)

Always exits 0. Never crashes the cortex job. Missing sources degrade
gracefully — a gaps[] entry is added and the block is nulled, but valid JSON
is always written.

Mirror style: build_netliq_daily.py (argparse main, atomic write, sys.path insert)
              build_context_risk.py (fail-open structure, logging to stderr)

Usage:
    python -m scripts.build_liquidity_plumbing
    python -m scripts.build_liquidity_plumbing --root /path/to/repo
    python -m scripts.build_liquidity_plumbing --out data/neuralweb/liquidity_plumbing.json
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("build_liquidity_plumbing")

_REPO_ROOT = Path(__file__).resolve().parent.parent
_ARTIFACT_ID = "liquidity-plumbing"
_DEFAULT_OUT = _REPO_ROOT / "data" / "neuralweb" / "liquidity_plumbing.json"


def _atomic_write_json(path: Path, payload: dict) -> None:
    """Write JSON atomically via temp-file + rename (build_context_risk pattern)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".tmp_{path.name}_",
        suffix=".json",
        delete=False,
    ) as tf:
        tf.write(text)
        tmp_path = Path(tf.name)
    tmp_path.replace(path)


def main(argv: list[str] | None = None) -> int:
    """Entry point for `python -m scripts.build_liquidity_plumbing`."""
    ap = argparse.ArgumentParser(
        description="Build NW liquidity plumbing lobe (Phase 0+1, shadow/display tier)."
    )
    ap.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Repo root (default: auto-detected from script location).",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=None,
        help=f"Output path (default: {_DEFAULT_OUT}).",
    )
    args = ap.parse_args(argv)

    root = args.root.resolve() if args.root is not None else _REPO_ROOT
    out_path = args.out.resolve() if args.out is not None else _DEFAULT_OUT

    # Late import so sys.path insert above takes effect before any engine import
    from engine.neuralweb.liquidity_plumbing import snapshot  # noqa: E402
    from engine.neuralweb.envelope import stamp  # noqa: E402

    try:
        payload = snapshot(root=root)
    except Exception as exc:  # noqa: BLE001
        log.error("build_liquidity_plumbing: snapshot() raised — %s", exc)
        # Fail-open: write a minimal degraded artifact so consumers see something
        from datetime import date  # noqa: E402
        from engine.neuralweb.liquidity_plumbing import _SCHEMA, _AUTHORITY  # noqa: E402
        payload = {
            "schema": _SCHEMA,
            "asof": str(date.today()),
            "authority": _AUTHORITY,
            "headline": {
                "state": "data_degraded",
                "summary": "Build error — see gaps.",
            },
            "fed": {
                "assets_bn": None, "assets_chg_20d_bn": None,
                "reserve_balances_bn": None, "walcl_stale_days": None,
                "policy_stance": None, "administered_rate_posture": None,
                "asof": None,
            },
            "treasury": {
                "tga_bn": None, "tga_chg_20d_bn": None,
                "net_issuance_20d_bn": None,
                "expected_tga_pressure": "unknown_until_financing_estimates_parser",
                "coupon_supply_pressure": "context_only",
                "asof": None,
            },
            "rrp": {"rrp_bn": None, "rrp_chg_20d_bn": None, "buffer_state": "unknown"},
            "quantity": {
                "netliq_bn": None, "netliq_chg_20d_bn": None,
                "netliq_chg_65d_bn": None, "netliq_pctile_expanding": None,
                "overlay": "unknown",
            },
            "quality": {
                "label": None, "fed_share": None,
                "mechanical": None, "stress_confirming": None,
            },
            "funding": {
                "effr_minus_iorb_bp": None, "sofr_minus_iorb_bp": None,
                "srf_takeup_bn": None, "discount_window_primary_credit_bn": None,
                "reserve_scarcity_state": "unknown",
            },
            "foreign_dollar": {
                "swap_lines_bn": None, "fima_repo_bn": None,
                "state": "not_integrated_yet",
            },
            "entry_effect": {
                "direction": "unknown", "quality": "unknown",
                "measured_basis": "cycle_ladder_21d_odds",
                "use": "support existing buy setup, never originate one",
            },
            "gaps": [f"snapshot() error: {exc}"],
            "degraded": True,
        }

    # Stamp with envelope (artifact_id must be registered in config/synapse.yml)
    try:
        payload = stamp(payload, artifact_id=_ARTIFACT_ID)
    except KeyError as exc:
        # artifact_id not yet in synapse.yml (Registry builder's task) — stamp with
        # a best-effort inline envelope so the file is still readable
        log.warning(
            "build_liquidity_plumbing: artifact_id %r not in synapse.yml — "
            "writing without envelope stamp (%s). Registry builder must add it.",
            _ARTIFACT_ID, exc,
        )
        payload["_envelope_warning"] = (
            f"liquidity-plumbing not yet registered in config/synapse.yml: {exc}"
        )
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "build_liquidity_plumbing: envelope.stamp() failed — %s. "
            "Writing without stamp.",
            exc,
        )
        payload["_envelope_warning"] = f"stamp() error: {exc}"

    # Atomic write — primary data path
    try:
        _atomic_write_json(out_path, payload)
        log.info(
            "build_liquidity_plumbing: wrote %s (state=%s degraded=%s gaps=%d)",
            out_path,
            (payload.get("headline") or {}).get("state"),
            payload.get("degraded"),
            len(payload.get("gaps") or []),
        )
    except Exception as exc:  # noqa: BLE001
        log.error("build_liquidity_plumbing: write to %s failed — %s", out_path, exc)
        return 0  # non-fatal; always exit 0

    # Site mirror — required so committee.html loadLiquidityPlumbing() can fetch
    # 'neuralwebdata/liquidity_plumbing.json' (mirrors build_context_risk.py pattern).
    site_path = root / "site" / "neuralwebdata" / "liquidity_plumbing.json"
    try:
        _atomic_write_json(site_path, payload)
        log.info("build_liquidity_plumbing: wrote site mirror %s", site_path)
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "build_liquidity_plumbing: site mirror write to %s failed — %s", site_path, exc
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
