"""Build data/macro/fed_net_liquidity.parquet — the CPI net-liquidity daily artifact.

DATA INFRASTRUCTURE ONLY (cycle-pattern-intelligence program). This builder emits a
context-tier artifact; it registers NO trial. FT-3 (netliq covariate on the pooled
hazard) is NOT registered here: additive-feature FT trials on the pooled hazard are
SUSPENDED by truth cycle_truth_ft2_credit_hazard_null_v1 (data/cycle_pattern/truths.jsonl)
and may only be registered later under that truth's reopening conditions.

Formula — engine.canon (audit #28), IMPORTED not re-implemented:

    netliq_bn = WALCL_bn − RRP_bn − TGA_bn        (all BILLIONS)

via :func:`engine.canon.load_net_liquidity_components`, which owns the unit contract
(WALCL & TGA stored in MILLIONS → /1000; RRP/RRPONTSYD already billions; a missing
drain contributes 0 rather than annihilating the balance-sheet trend).

Emitted columns (date is a regular column, not the index):
    date                     daily UNION of the three components' real observation dates
    walcl_bn                 Fed balance sheet, billions (ffilled to the union index)
    rrp_bn                   ON-RRP drain, billions (ffilled; 0 pre-history / missing)
    tga_bn                   Treasury General Account, billions (ffilled; 0 pre-history)
    netliq_bn                walcl_bn − rrp_bn − tga_bn (canon)
    netliq_d13w              65-row change of netliq_bn  (≈13 trading weeks where the
                             union index is business-daily; pre-2005 the index is
                             WALCL-weekly, so the window spans longer wall-clock)
    netliq_d26w              130-row change of netliq_bn
    netliq_pctile_expanding  expanding percentile of the netliq_bn LEVEL — PIT-pure:
                             the value at t is the rank of netliq_bn[t] within history
                             ≤ t only, so appending future rows never changes the past.

Stale-guard: every component is ffilled, but the frame is TRUNCATED at
min(per-component last real observation) + 10 business days. A dead component
collector therefore cannot silently ffill a drain flat for weeks — the artifact's
tail stops advancing instead. Per-component last-obs dates are logged AND written to
the JSON sidecar (data/macro/fed_net_liquidity_meta.json, no timestamps → the whole
build is a deterministic, idempotent full rebuild).

Usage:
    python -m scripts.build_netliq_daily
    python -m scripts.build_netliq_daily --fred-dir data/fred --tga-path data/treasury/tga.parquet
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine.canon import load_net_liquidity_components  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("build_netliq_daily")

_REPO_ROOT = Path(__file__).resolve().parent.parent

D13W_ROWS = 65    # 13 trading weeks on a business-daily index
D26W_ROWS = 130   # 26 trading weeks on a business-daily index
STALE_GUARD_BDAYS = 10

DEFAULT_FRED_DIR = _REPO_ROOT / "data" / "fred"
DEFAULT_TGA_PATH = _REPO_ROOT / "data" / "treasury" / "tga.parquet"
DEFAULT_OUT = _REPO_ROOT / "data" / "macro" / "fed_net_liquidity.parquet"
DEFAULT_META_OUT = _REPO_ROOT / "data" / "macro" / "fed_net_liquidity_meta.json"


def _component_paths(fred_dir: str | Path, tga_path: str | Path) -> dict[str, Path]:
    """The three component parquets, keyed by canonical component name.

    RRP deliberately mirrors engine.canon.load_net_liquidity_components, which reads
    the FRED mirror data/fred/RRPONTSYD.parquet (NOT data/nyfed/rrp.parquet — same
    values, but canon owns the choice and this builder must not fork it).
    """
    F = Path(fred_dir)
    return {
        "walcl": F / "WALCL.parquet",
        "rrp": F / "RRPONTSYD.parquet",
        "tga": Path(tga_path),
    }


def _real_obs_dates(path: Path) -> pd.DatetimeIndex:
    """Sorted real (non-NaN) observation dates of one component parquet's first column."""
    df = pd.read_parquet(path)
    s = pd.to_numeric(df[df.columns[0]], errors="coerce").dropna()
    return pd.DatetimeIndex(s.index).sort_values()


def build_frame(
    fred_dir: str | Path = DEFAULT_FRED_DIR,
    tga_path: str | Path = DEFAULT_TGA_PATH,
    stale_guard_bdays: int = STALE_GUARD_BDAYS,
) -> tuple[pd.DataFrame, dict]:
    """Deterministic full rebuild → (frame, meta sidecar dict).

    The union index is the union of the components' REAL observation dates (never a
    synthetic calendar), truncated at min(component last real obs) + `stale_guard_bdays`
    business days. Component scaling/ffill/fillna(0) semantics live entirely in
    engine.canon.load_net_liquidity_components.
    """
    paths = _component_paths(fred_dir, tga_path)
    obs: dict[str, pd.DatetimeIndex] = {}
    for name, p in paths.items():
        if p.exists():
            dates = _real_obs_dates(p)
            if len(dates):
                obs[name] = dates
        else:
            log.warning("component %s missing on disk (%s) — canon fills its drain with 0", name, p)
    if "walcl" not in obs:
        raise FileNotFoundError(f"WALCL component missing or empty at {paths['walcl']} — cannot build net liquidity")

    union = obs["walcl"]
    for name in ("rrp", "tga"):
        if name in obs:
            union = union.union(obs[name])

    last_obs = {name: dates.max() for name, dates in obs.items()}
    stalest = min(last_obs, key=lambda k: last_obs[k])
    cutoff = last_obs[stalest] + pd.offsets.BDay(stale_guard_bdays)
    n_dropped = int((union > cutoff).sum())
    idx = union[union <= cutoff]
    if n_dropped:
        log.warning(
            "stale-guard: dropped %d union dates after %s (stalest component %r last obs %s + %dbd)",
            n_dropped, cutoff.date(), stalest, last_obs[stalest].date(), stale_guard_bdays,
        )

    comps = load_net_liquidity_components(idx, fred_dir=fred_dir, tga_path=tga_path)
    df = pd.DataFrame(comps, index=idx).dropna(subset=["walcl_bn"])
    df["netliq_d13w"] = df["netliq_bn"].diff(D13W_ROWS)
    df["netliq_d26w"] = df["netliq_bn"].diff(D26W_ROWS)
    # PIT-pure by construction: expanding rank only ever sees history ≤ t.
    df["netliq_pctile_expanding"] = df["netliq_bn"].expanding(min_periods=1).rank(pct=True)
    df.index.name = "date"
    df = df.reset_index()

    meta = {
        "artifact": "data/macro/fed_net_liquidity.parquet",
        "formula": "netliq_bn = walcl_bn - rrp_bn - tga_bn (engine.canon.net_liquidity_bn, audit #28)",
        "component_last_obs": {name: str(last_obs[name].date()) for name in sorted(last_obs)},
        "components_missing": sorted(set(paths) - set(obs)),
        "stalest_component": stalest,
        "stale_guard_bdays": stale_guard_bdays,
        "stale_guard_cutoff": str(cutoff.date()),
        "rows_dropped_by_stale_guard": n_dropped,
        "rows": int(len(df)),
        "first_date": str(df["date"].iloc[0].date()),
        "last_date": str(df["date"].iloc[-1].date()),
        "columns": list(df.columns),
    }
    for name in sorted(last_obs):
        log.info("component %-5s last real obs %s", name, last_obs[name].date())
    log.info("frame %d rows %s → %s (cutoff %s)",
             len(df), meta["first_date"], meta["last_date"], meta["stale_guard_cutoff"])
    return df, meta


def write_artifact(df: pd.DataFrame, meta: dict,
                   out_path: str | Path = DEFAULT_OUT,
                   meta_path: str | Path = DEFAULT_META_OUT) -> None:
    """Atomic write of the parquet + deterministic JSON sidecar (no timestamps)."""
    out_path, meta_path = Path(out_path), Path(meta_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(".parquet.tmp")
    df.to_parquet(tmp, index=False)
    tmp.replace(out_path)
    meta_tmp = meta_path.with_suffix(".json.tmp")
    meta_tmp.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    meta_tmp.replace(meta_path)
    log.info("wrote %s (%d rows) + %s", out_path, len(df), meta_path)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--fred-dir", default=str(DEFAULT_FRED_DIR))
    ap.add_argument("--tga-path", default=str(DEFAULT_TGA_PATH))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--meta-out", default=str(DEFAULT_META_OUT))
    ap.add_argument("--stale-guard-bdays", type=int, default=STALE_GUARD_BDAYS)
    args = ap.parse_args(argv)
    df, meta = build_frame(args.fred_dir, args.tga_path, args.stale_guard_bdays)
    write_artifact(df, meta, args.out, args.meta_out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
