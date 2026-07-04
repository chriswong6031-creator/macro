"""Phase-4 GEX validation gate: does the gamma regime track FORWARD realized vol?

The ONE falsifiable claim of the dealer-gamma layer (a VOL-REGIME effect, NOT
direction): short-gamma days (net GEX < 0 / spot below the zero-gamma flip) should
precede HIGHER forward realized vol than long-gamma days. Runs on the daily
per-symbol GEX summaries the collector accumulates (data/cboe/gex*.parquet and
data/polygon_gex/summary_*.parquet).

There is NO free options history, so this FORWARD-ACCUMULATES: it honestly reports
"building history" until n per bucket clears MIN_PER_BUCKET, and its verdict GATES
whether GEX may ever touch the per-stock ladder SCORE (engine/cycles.py). If it never
beats a null, GEX stays display-only (the gex.html board + a context panel) and never
enters the scoring path — the same validate-before-weight rule the liquidity modifier
earned. Writes reports/gex-validation.md.

Two stores are evaluated:
  * data/cboe/gex*.parquet      — 10 named equities + SPX; retained as corroboration
  * data/polygon_gex/summary_*.parquet — 384-name per-name summaries; the primary
    gate store now that it has wider per-name history

Evidence lines in data/gex/gate.json name which store each verdict came from.
`scored` flips only on a CI-clean pass in EITHER store (per §3/A1).

Run: .venv/bin/python -m scripts.validate_gex
"""
from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402

MIN_PER_BUCKET = 30        # honest power floor before any verdict
HORIZONS = (5, 10)
N_BOOT = 2000


def _fwd_rv(spot: pd.Series, h: int) -> pd.Series:
    """Forward h-day realized vol (annualized), aligned to day t (uses t+1..t+h)."""
    r = np.log(pd.to_numeric(spot, errors="coerce")).diff()
    return r.rolling(h).std().shift(-h) * np.sqrt(252)


def _regime(d: pd.DataFrame):
    if "gamma_regime" in d and d["gamma_regime"].notna().any():
        return d["gamma_regime"].map({"long": 1.0, "short": -1.0})
    if "net_gex_bn" in d:
        return np.sign(pd.to_numeric(d["net_gex_bn"], errors="coerce"))
    if "spot_vs_flip_pct" in d:      # legacy SPX frame
        return np.sign(pd.to_numeric(d["spot_vs_flip_pct"], errors="coerce"))
    return None


def _boot(longg: np.ndarray, shortg: np.ndarray):
    """Bootstrap CI of (short-gamma mean RV - long-gamma mean RV). Positive = claim holds."""
    diffs = np.empty(N_BOOT)
    for i in range(N_BOOT):
        diffs[i] = (np.random.choice(shortg, len(shortg)).mean()
                    - np.random.choice(longg, len(longg)).mean())
    return float(shortg.mean() - longg.mean()), float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))


def evaluate(name: str, d: pd.DataFrame, store_label: str = "") -> list[str]:
    prefix = f"[{store_label}] " if store_label else ""
    if "spot" not in d.columns or len(d) < 5:
        return [f"{prefix}{name}: n={len(d)} — building history"]
    reg = _regime(d)
    if reg is None:
        return [f"{prefix}{name}: no regime column"]
    d = d.copy()
    d["reg"] = np.asarray(reg, dtype=float)
    out = []
    for h in HORIZONS:
        df = pd.DataFrame({"reg": d["reg"].values, "rv": _fwd_rv(d["spot"], h).values}).dropna()
        longg = df[df["reg"] > 0]["rv"].to_numpy()
        shortg = df[df["reg"] < 0]["rv"].to_numpy()
        if len(longg) < MIN_PER_BUCKET or len(shortg) < MIN_PER_BUCKET:
            out.append(f"{prefix}{name} h={h}d: building history (long n={len(longg)}, short n={len(shortg)}; "
                       f"need {MIN_PER_BUCKET}/bucket)")
            continue
        diff, lo, hi = _boot(longg, shortg)
        verdict = "PASS — short>long, CI excludes 0" if lo > 0 else "NO EDGE — CI includes 0 → display-only"
        out.append(f"{prefix}{name} h={h}d: short_RV−long_RV={diff:+.3f} [{lo:+.3f}, {hi:+.3f}] "
                   f"(long n={len(longg)}, short n={len(shortg)}) → {verdict}")
    return out


def _evaluate_cboe_store(config_root) -> list[str]:
    """Evaluate the legacy cboe/gex*.parquet store (10 equities + SPX)."""
    files = sorted(glob.glob(str(config_root / "cboe" / "gex*.parquet")))
    verdicts: list[str] = []
    if not files:
        return verdicts
    for f in files:
        try:
            evl = evaluate(Path(f).stem, pd.read_parquet(f), store_label="cboe")
            verdicts += evl
        except Exception as e:  # noqa: BLE001
            verdicts.append(f"[cboe] {Path(f).stem}: read error ({e})")
    return verdicts


def _evaluate_polygon_store(config_root) -> list[str]:
    """Evaluate polygon_gex/summary_*.parquet (384-name per-name summaries).

    Each summary file is one name × N date rows with columns: spot, gamma_regime, etc.
    We evaluate each name individually; evidence lines carry the [polygon_gex] label.
    """
    files = sorted(glob.glob(str(config_root / "polygon_gex" / "summary_*.parquet")))
    verdicts: list[str] = []
    if not files:
        return verdicts
    for f in files:
        stem = Path(f).stem  # e.g. "summary_AAPL"
        sym = stem.replace("summary_", "", 1)
        try:
            df = pd.read_parquet(f)
            evl = evaluate(sym, df, store_label="polygon_gex")
            verdicts += evl
        except Exception as e:  # noqa: BLE001
            verdicts.append(f"[polygon_gex] {sym}: read error ({e})")
    return verdicts


def main() -> int:
    data_root = config.data_dir()
    cboe_verdicts = _evaluate_cboe_store(data_root)
    poly_verdicts = _evaluate_polygon_store(data_root)
    all_verdicts = cboe_verdicts + poly_verdicts

    lines = ["# GEX validation — gamma regime vs forward realized vol", "",
             "Falsifiable claim: short-gamma days precede HIGHER forward realized vol than long-gamma days.",
             "Forward-accumulating (no free options history). This verdict GATES any ladder weight; "
             "until it PASSES, GEX is display-only and never touches the score.",
             "",
             "Stores evaluated:",
             "  * data/cboe/gex*.parquet — 10 named equities + SPX (corroboration)",
             "  * data/polygon_gex/summary_*.parquet — 384-name per-name summaries (primary gate store)",
             "Evidence lines are prefixed [cboe] or [polygon_gex] to identify the source.",
             ""]

    if not cboe_verdicts:
        lines.append("### cboe store")
        lines.append("- no GEX history yet (collector has not run)")
    else:
        lines.append("### cboe store")
        lines += ["- " + ln for ln in cboe_verdicts]

    lines.append("")
    if not poly_verdicts:
        lines.append("### polygon_gex store")
        lines.append("- no polygon_gex summaries yet (collector has not run)")
    else:
        lines.append("### polygon_gex store")
        # Summarise rather than print all 384 names to keep the report readable
        passes = [ln for ln in poly_verdicts if "PASS —" in ln]
        building = [ln for ln in poly_verdicts if "building history" in ln]
        no_edge = [ln for ln in poly_verdicts if "NO EDGE" in ln]
        errors = [ln for ln in poly_verdicts if "read error" in ln or "no regime" in ln]
        lines.append(f"- polygon_gex: {len(passes)} pass, {len(building)} building, "
                     f"{len(no_edge)} no-edge, {len(errors)} errors "
                     f"(out of {len(poly_verdicts)} total evidence lines)")
        # Print the passes and no-edge explicitly; building are verbose — just count
        for ln in passes:
            lines.append("  - " + ln)
        for ln in no_edge:
            lines.append("  - " + ln)
        if errors:
            for ln in errors[:5]:
                lines.append("  - " + ln)

    report = "\n".join(lines)
    print(report)
    out = config.ROOT / "reports" / "gex-validation.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report + "\n")

    # structured gate artifact — the firewall engine/stock_score.py consults before letting GEX
    # touch the per-stock score (mirrors data/vol_regime/gate.json). scored=true only when at
    # least one horizon's short−long forward-RV CI excludes 0 in EITHER store; otherwise
    # display-only. Evidence lines name the store they came from (via [cboe]/[polygon_gex] prefix).
    scored = any("PASS —" in ln for ln in all_verdicts)
    building = (not all_verdicts) or any("building history" in ln for ln in all_verdicts)
    status = "passed" if scored else ("building_history" if building else "no_edge")
    gate = {
        "schema": "gex.gate.v1",
        "generated_at": pd.Timestamp.now("UTC").strftime("%Y-%m-%d %H:%M UTC"),
        "scored": bool(scored),
        "status": status,
        "weight": 0.10 if scored else 0.0,
        "horizons": list(HORIZONS),
        "min_per_bucket": MIN_PER_BUCKET,
        "evidence": all_verdicts,
        "stores_evaluated": ["cboe", "polygon_gex"],
        "note": ("gamma regime beat a forward-RV null — GEX may enter the per-stock score"
                 if scored else
                 "display-only until a horizon's short−long forward-RV bootstrap CI excludes 0"),
    }
    gp = config.data_dir() / "gex" / "gate.json"
    gp.parent.mkdir(parents=True, exist_ok=True)
    gp.write_text(json.dumps(gate, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
