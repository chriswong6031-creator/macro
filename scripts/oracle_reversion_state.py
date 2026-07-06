"""Oracle Reversion State — sidecar writer (P1, display tier only).

Writes ``site/basketdata/oracle_reversion_state.json`` with schema
``oracle_reversion_state.v1``.  Reads:

  - ``data/oracle/compounds/registry.jsonl``      (source of truth for compounds)
  - ``data/oracle/reversion_forward/<id>.jsonl``  (P0 forward ledger per compound)

One entry per reversion compound.  All signals are ``authority_level: "display"``
unconditionally — no authority is earned yet (P0 ledger is just starting to
accrue).  The live block is honest even at n=0 (nulls, never fabricated).

Sidecar design: this does NOT modify oracle_state.v1 / the episode contract.
See research/ORACLE_REVERSION_PROMOTION_TRACK_DESIGN.md §2 and the scout
report for why the sidecar is the correct seam.

Constitution compliance
-----------------------
- Article 1: no signal/score/escalation originated here (purely derived from
  deterministic grading + backtest data from the registry).
- Article 2: authority_level is ALWAYS "display"; the article2_surface key
  is always "display".  No ranking surface is touched.
- DO NOT call grant_authority here (that belongs to P2 promotion scan).

Usage
-----
  python -m scripts.oracle_reversion_state --data-dir /path/to/data
  python -m scripts.oracle_reversion_state --data-dir /path/to/data --site-dir /path/to/site
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("oracle_reversion_state")

SCHEMA = "oracle_reversion_state.v1"
_ARTIFACT_ID = "oracle-reversion-state"   # must match synapse.yml key
_REGISTRY_PATH_REL = Path("oracle") / "compounds" / "registry.jsonl"
_FORWARD_DIR_REL = Path("oracle") / "reversion_forward"
_OUT_REL = Path("basketdata") / "oracle_reversion_state.json"


# ---------------------------------------------------------------------------
# Registry helpers
# ---------------------------------------------------------------------------

def _load_reversion_compounds(data_dir: Path) -> list[dict]:
    registry_path = data_dir / _REGISTRY_PATH_REL
    if not registry_path.exists():
        log.warning("registry not found: %s", registry_path)
        return []
    compounds = []
    for line in registry_path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            c = json.loads(line)
        except Exception:  # noqa: BLE001
            continue
        if "reversion" in c and c["reversion"].get("gauntlet") == "PASS":
            compounds.append(c)
    return compounds


# ---------------------------------------------------------------------------
# Forward ledger helpers
# ---------------------------------------------------------------------------

def _load_ledger(data_dir: Path, compound_id: str) -> list[dict]:
    """Load all rows from a compound's forward ledger. Fail-open (empty list)."""
    p = data_dir / _FORWARD_DIR_REL / f"{compound_id}.jsonl"
    if not p.exists():
        return []
    rows = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:  # noqa: BLE001
            pass
    return rows


# ---------------------------------------------------------------------------
# Panel: latest date for fired_today detection
# ---------------------------------------------------------------------------

def _latest_panel_date(data_dir: Path, tier: str) -> pd.Timestamp | None:
    p = data_dir / "oracle" / f"panel_{tier}.parquet"
    if not p.exists():
        return None
    try:
        raw = pd.read_parquet(p)
        return pd.Timestamp(raw.index.get_level_values("date").max())
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# Live stats: computed from the P0 ledger (honest at n=0)
# ---------------------------------------------------------------------------

def _compute_live_stats(
    rows: list[dict],
    operating_regime: str,
    panel_data_dir: Path,
    tier: str,
) -> dict[str, Any]:
    """Compute live stats from the forward ledger rows.

    ``operating_regime``: "dual" | "risk_off" | "risk_on" (from reversion block).
    For single-regime signals, only count fires in the operating regime.

    base_rate: unconditional trailing 21-session WR on the same universe (buy-anytime
    rate, computed from the full panel as the fraction of 21-session returns > 0).
    Per PREREG.md, this is the entry-timing LIFT measure.
    """
    matured = [r for r in rows if r.get("matured") is True]

    # Regime-gate for single-regime signals
    if operating_regime in ("risk_off", "risk_on"):
        matured = [r for r in matured if r.get("regime") == operating_regime]

    n = len(matured)
    if n == 0:
        return {
            "n_matured": 0,
            "hits": 0,
            "wr": None,
            "wilson_lower": None,
            "base_rate": None,
            "lift_lb": None,
        }

    hits = sum(1 for r in matured if (r.get("ret_exit") or 0) > 0)
    wr = hits / n

    from engine.neuralweb.constitution import wilson_lower as _wilson_lower
    wl = _wilson_lower(hits, n, z=1.645)

    # Base rate: unconditional trailing 21-session WR from the panel
    base_rate = _compute_base_rate(panel_data_dir, tier, operating_regime)

    lift_lb: float | None = None
    if base_rate is not None and base_rate > 0:
        lift_lb = round(wl / base_rate, 4)

    return {
        "n_matured": n,
        "hits": hits,
        "wr": round(wr, 4),
        "wilson_lower": round(wl, 4),
        "base_rate": round(base_rate, 4) if base_rate is not None else None,
        "lift_lb": lift_lb,
    }


def _compute_base_rate(data_dir: Path, tier: str, operating_regime: str) -> float | None:
    """Unconditional trailing 21-session WR on the panel (buy-anytime rate).

    Returns None if panel is unavailable.
    """
    p = data_dir / "oracle" / f"panel_{tier}.parquet"
    if not p.exists():
        return None
    try:
        panel = pd.read_parquet(p)
        if "ret" not in panel.columns:
            return None

        ret_series = panel["ret"].sort_index()

        # For each (node, date) compute 21-session forward return
        # We use the panel as-is: for each node's sorted ret series,
        # compute rolling 21-session cumulative return
        results: list[float] = []
        for node in panel.index.get_level_values("node").unique():
            try:
                node_ret = panel.xs(node, level="node")["ret"].sort_index().fillna(0)
                lvl = (1 + node_ret).cumprod()
                # 21-session forward return at each date
                fwd = lvl.shift(-21) / lvl - 1
                fwd = fwd.dropna()
                if operating_regime in ("risk_off", "risk_on") and "spy_above_200d" in panel.columns:
                    try:
                        regime_col = panel.xs(node, level="node")["spy_above_200d"].sort_index()
                        vix_col = panel.xs(node, level="node").get("vix_pctile", pd.Series(dtype=float))
                        if vix_col is not None and len(vix_col) > 0:
                            is_risk_off = (regime_col == 0) | (vix_col >= 0.70)
                        else:
                            is_risk_off = regime_col == 0
                        if operating_regime == "risk_off":
                            fwd = fwd[is_risk_off.reindex(fwd.index, fill_value=False)]
                        elif operating_regime == "risk_on":
                            fwd = fwd[~is_risk_off.reindex(fwd.index, fill_value=False)]
                    except Exception:  # noqa: BLE001
                        pass
                results.extend((fwd > 0).tolist())
            except Exception:  # noqa: BLE001
                continue

        if not results:
            return None
        return float(np.mean(results))
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# Per-compound signal record builder
# ---------------------------------------------------------------------------

def _build_signal_record(
    compound: dict,
    data_dir: Path,
    latest_date_by_tier: dict[str, pd.Timestamp | None],
) -> dict[str, Any]:
    """Build one signal record for the sidecar output."""
    cid = compound["id"]
    reversion = compound.get("reversion", {})
    universe = compound.get("universe", {})
    tier = universe.get("tier", "s")

    operating_regime = reversion.get("operating_regime", "dual")

    # Backtest stats from the registry (frozen; never recomputed here)
    backtest = {
        "asym": reversion.get("asym"),
        "wr": reversion.get("wr"),
        "ret_exit": reversion.get("ret_exit"),
        "n": reversion.get("n"),
        "mfe": reversion.get("mfe"),
        "mae": reversion.get("mae"),
    }

    # Forward ledger
    ledger_rows = _load_ledger(data_dir, cid)
    latest_date = latest_date_by_tier.get(tier)

    # fired_today: nodes with fire_date == latest panel date
    fired_today: list[str] = []
    if latest_date is not None:
        latest_str = latest_date.isoformat()
        fired_today = [
            r["node"] for r in ledger_rows
            if r.get("fire_date", "").startswith(latest_str[:10])
        ]

    # Live stats
    live = _compute_live_stats(ledger_rows, operating_regime, data_dir, tier)

    return {
        "id": cid,
        "name": compound.get("name", cid),
        "mechanism": compound.get("mechanism_en", ""),
        "cluster": reversion.get("cluster", None),
        "universe_tier": tier,
        "operating_regime": operating_regime,
        "authority_level": "display",       # ALWAYS display — never escalate here
        "article2_surface": "display",      # Article 2: no money path
        "fired_today": fired_today,
        "backtest": backtest,
        "live": live,
        "ledger_n_total": len(ledger_rows),
    }


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------

def build_reversion_state(
    data_dir: Path,
    site_dir: Path,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Build and write oracle_reversion_state.json. Fail-open: never raises."""
    compounds = _load_reversion_compounds(data_dir)
    if not compounds:
        log.info("oracle_reversion_state: no reversion compounds")

    # Pre-load latest dates per tier (expensive per tier, not per compound)
    tiers_needed = {c.get("universe", {}).get("tier", "s") for c in compounds}
    latest_date_by_tier: dict[str, pd.Timestamp | None] = {
        t: _latest_panel_date(data_dir, t) for t in tiers_needed
    }

    signals: list[dict] = []
    for compound in compounds:
        try:
            record = _build_signal_record(compound, data_dir, latest_date_by_tier)
            signals.append(record)
        except Exception as e:  # noqa: BLE001
            log.warning("oracle_reversion_state: %s failed: %s", compound.get("id"), e)

    # asof from the tier-s panel (primary tier)
    asof = None
    for t in ("s", "m"):
        d = latest_date_by_tier.get(t)
        if d is not None:
            asof = d.isoformat()[:10]
            break
    if asof is None:
        asof = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "asof": asof,
        "n_signals": len(signals),
        "signals": signals,
    }

    # Envelope stamp (mirrors oracle_state.json convention per scout report)
    try:
        from engine.neuralweb.envelope import stamp
        payload = stamp(payload, artifact_id=_ARTIFACT_ID)
    except Exception as e:  # noqa: BLE001
        log.warning("oracle_reversion_state: envelope stamp failed (non-fatal): %s", e)

    if not dry_run:
        out_path = site_dir / _OUT_REL
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, indent=2, default=str))
        log.info("oracle_reversion_state: wrote %s (%d signals)", out_path, len(signals))

    return payload


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(description="Oracle reversion state sidecar writer (P1, display tier)")
    p.add_argument("--data-dir", type=Path, default=None)
    p.add_argument("--site-dir", type=Path, default=None)
    p.add_argument("--dry-run", action="store_true",
                   help="Build and print but write no files")
    args = p.parse_args()

    from lib import config as _cfg
    data_dir = args.data_dir or _cfg.data_dir()
    site_dir = args.site_dir or (_cfg.ROOT / "site")

    log.info("oracle_reversion_state: data_dir=%s site_dir=%s dry_run=%s",
             data_dir, site_dir, args.dry_run)

    payload = build_reversion_state(data_dir, site_dir, dry_run=args.dry_run)
    print(json.dumps(payload, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
