"""Reconstruct multi-year index dealer-gamma HISTORY from the ThetaData T1 EOD store
(roadmap P1.1b / brainstorm §5.4) — replaces the ~20-row CBOE-delayed `market_gamma`
estimate with a 2017-> daily regime/levels series for the index ETFs.

WHAT IT DOES
------------
For each completed index-ETF root (SPY, QQQ, IWM, DIA), for every EOD trading date
in the greeks era (2017->), it rebuilds the per-strike option chain by joining the
ThetaData `greeks` store (gamma/vanna/charm + underlying_price + implied_vol) to the
`oi` store on (root, expiration, strike, right, date), then feeds the
[K, T, iv, oi, is_call, expiry] subset to engine.gex_engine.compute_gex — the SAME
pure function that produces both the live data/cboe/gex store and the live
data/polygon_gex summaries. Using that exact function is what makes the reconstructed
series sign- and scale-COMPARABLE with the live path: the dealer long-call / short-put
sign, the ±25% strike window, the ±25% zero-gamma grid flip, the $/1%-move net-GEX
scaling, and the "long above flip / short below" regime are all inherited verbatim
(engine/gex_engine.py). compute_gex RE-IMPLIES the greeks from iv via engine.greeks
rather than trusting the vendor's stored gamma — again matching the live path exactly.

Every emitted row is stamped reconstructed=True.

MID-WRITE / R-law: reads ONLY roots+years listed 'completed' in the live backfill
worktree's _backfill_state.json at run time; the exact (root, year) set read is stamped
into data/index_gex_history/_manifest.json. SPX / SPXW are index-native GEX candidates
but are NOT read unless the state file lists them complete (it does not today), so they
are recorded as EXCLUDED, not silently reconstructed with a divergent basis.

DISPLAY-ONLY: this is a levels / vol-CONTEXT series (net-GEX percentile-vs-own-history,
regime persistence). GEX score integration is a settled NULL — nothing here feeds a
score path.

STORE RESOLUTION (OIP E3c, 2026-07-29)
--------------------------------------
The ThetaData EOD store path is NOT hardcoded here any more. It routes through
engine.thetadata_store.resolve_thetadata_store() — the canonical single fallback chain
(THETADATA_STORE env -> lib.config data_dir()/thetadata_eod -> the ops-host worktree),
content-checked so an empty stub directory never resolves. The old module-level constant
pinned the ops-host worktree path literally — the fragmented per-module resolution the
options_witness empty-store incident came from. On any host without that exact path the
builder died with a bare SystemExit and the committed artifact silently froze (measured:
the store sat at 2026-07-02 while engine/market_gamma kept serving percentiles off it as
if current). That path now lives in exactly one place: engine.thetadata_store.

Nothing in CI or the nightly render reads the store — they read the COMMITTED
data/index_gex_history/*.parquet (and its R2 mirror). This script runs ONLY where the
store lives: the M1 ops host, weekly, via ops/launchd/com.macro.indexgexhistory.plist.

Output: data/index_gex_history/<ROOT>.parquet, one row per trading day.
Columns mirror compute_gex's summary plus: reconstructed(bool), root, source.
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from engine.gex_engine import DEFAULTS, compute_gex
from engine.thetadata_store import resolve_thetadata_store
from lib import config

log = logging.getLogger("build_index_gex_history")

# Optional OVERRIDE hook (tests point this at a fixture store). Left None in
# production so _theta_root() always goes through the canonical resolver.
THETA_ROOT: Path | None = None
_RESOLVED: Path | None = None


def _theta_root() -> Path:
    """The ThetaData EOD store root for this run (READ-ONLY, completed years only).

    Resolution order: the THETA_ROOT test override, then the canonical resolver.
    Raises SystemExit naming every path tried when nothing content-bearing resolves —
    the honest failure for a host that simply does not hold the store, and never a
    silent empty-frame run.
    """
    global _RESOLVED
    if THETA_ROOT is not None:
        return Path(THETA_ROOT)
    if _RESOLVED is None:
        root = resolve_thetadata_store(purpose="build_index_gex_history")
        if root is None:
            raise SystemExit(
                "ThetaData EOD store did not resolve — set THETADATA_STORE or run this "
                "on the store host. This reconstruction is host-bound by design; CI and "
                "the nightly render read the committed data/index_gex_history parquets.")
        _RESOLVED = root
    return _RESOLVED


def _state_path() -> Path:
    return _theta_root() / "_backfill_state.json"

# Roots requested by P1.1b. SPX/SPXW added ONLY if state marks them complete.
INDEX_ROOTS = ["SPY", "QQQ", "IWM", "DIA"]
INDEX_CANDIDATE_NATIVE = ["SPX", "SPXW"]

# greeks era per the roadmap (T1 greeks begin 2017; earlier years lack the greeks store).
MIN_YEAR = 2017

# The scalar summary fields we keep (1 row/day). Match compute_gex output keys.
SUMMARY_KEYS = [
    "tier", "n_strikes", "spot", "net_gex_bn", "net_vex", "net_cex",
    "gamma_flip", "dist_to_flip_pct", "gamma_regime",
    "magnet_up", "magnet_down", "charm_anchor", "charm_net_sign",
    "iv30", "put_call_oi_ratio", "max_pain", "top_oi_share",
]


def _completed_map() -> dict[str, list[str]]:
    """{root: [year,...]} that the live backfill marks 'completed' RIGHT NOW."""
    p = _state_path()
    if not p.exists():
        raise SystemExit(f"backfill state not found: {p}")
    return json.loads(p.read_text()).get("completed", {})


def _roots_to_build(completed: dict[str, list[str]]) -> tuple[list[str], list[str]]:
    """(roots we will read, native-index roots deliberately excluded).
    A root is buildable only if the state lists it complete AND it has >=1 year >=MIN_YEAR."""
    build, excluded = [], []
    for r in INDEX_ROOTS:
        yrs = [int(y) for y in completed.get(r, []) if str(y).isdigit()]
        if any(y >= MIN_YEAR for y in yrs):
            build.append(r)
        else:
            excluded.append(r)
    for r in INDEX_CANDIDATE_NATIVE:
        yrs = [int(y) for y in completed.get(r, []) if str(y).isdigit()]
        if any(y >= MIN_YEAR for y in yrs):
            build.append(r)  # only if the state truly lists it complete
    return build, excluded


def _read_year_chain(root: str, year: int) -> pd.DataFrame | None:
    """greeks ⋈ oi for one (root, year) -> long per-strike-per-date frame with the
    columns compute_gex needs: K, T, iv, oi, is_call, expiry (+ date, underlying spot)."""
    theta = _theta_root()
    gpath = theta / "greeks" / root / f"{year}.parquet"
    opath = theta / "oi" / root / f"{year}.parquet"
    if not gpath.exists() or not opath.exists():
        return None
    g = pd.read_parquet(
        gpath,
        columns=["root", "expiration", "strike", "right", "date",
                 "underlying_price", "implied_vol"],
    )
    o = pd.read_parquet(opath)  # root,expiration,strike,right,date,open_interest
    keys = ["root", "expiration", "strike", "right", "date"]
    m = g.merge(o, on=keys, how="inner")
    if m.empty:
        return None
    m = m[m["open_interest"] > 0]
    if m.empty:
        return None
    # compute_gex/_window contract columns:
    m["K"] = m["strike"].astype(float)
    m["oi"] = m["open_interest"].astype(float)
    m["iv"] = m["implied_vol"].astype(float)
    m["is_call"] = m["right"].astype(str).str.upper().eq("C")
    m["expiry"] = pd.to_datetime(m["expiration"])
    dts = pd.to_datetime(m["date"])
    # T = calendar days to expiry / 365 — EXACTLY collectors/polygon_options.parse_chain.
    m["T"] = (m["expiry"] - dts).dt.days / 365.0
    m["date"] = dts
    return m[["date", "expiry", "K", "T", "iv", "oi", "is_call", "underlying_price"]]


def _summarise_day(day: pd.DataFrame, root: str) -> dict | None:
    """One trading date's per-strike frame -> compute_gex summary (1 row)."""
    up = day["underlying_price"].dropna()
    spot = float(up.iloc[0]) if len(up) else 0.0
    if not (spot > 0):
        return None
    chain = day[["K", "T", "iv", "oi", "is_call", "expiry"]].copy()
    # compute_gex._window already filters T<=365d, ±25% strike band, iv>0, oi>0.
    out = compute_gex(chain, spot, cfg=None, symbol=root)
    row = {k: out.get(k) for k in SUMMARY_KEYS}
    row["reconstructed"] = True
    row["root"] = root
    row["source"] = "thetadata_eod:greeks⋈oi"
    return row


def build_root(root: str, completed: dict[str, list[str]], min_year: int) -> tuple[pd.DataFrame, list[int]]:
    """Full 2017-> daily summary series for one root. Returns (frame, years_read)."""
    years = sorted(int(y) for y in completed.get(root, [])
                   if str(y).isdigit() and int(y) >= min_year)
    rows, years_read = [], []
    for yr in years:
        chain = _read_year_chain(root, yr)
        if chain is None or chain.empty:
            log.warning("%s %d: empty/absent chain", root, yr)
            continue
        years_read.append(yr)
        for dt, day in chain.groupby("date"):
            r = _summarise_day(day, root)
            if r is None:
                continue
            r["date"] = pd.Timestamp(dt)
            rows.append(r)
        log.info("%s %d: %d trading days", root, yr, sum(1 for x in rows if x.get("date") and pd.Timestamp(x["date"]).year == yr))
    if not rows:
        return pd.DataFrame(), years_read
    df = pd.DataFrame(rows).set_index("date").sort_index()
    df = df[~df.index.duplicated(keep="last")]
    return df, years_read


# Tolerance for same-spot filter (fraction of reconstructed spot).
# The live polygon_gex store settles on T-1 close data; spot discrepancies larger than
# this fraction indicate a settlement-timing mismatch rather than model mismatch.
_SPOT_TOL_FRAC = 0.005  # 0.5 %


def audit_overlap(recon: pd.DataFrame, live: pd.DataFrame) -> dict:
    """Blocking P1.1b audit primitive: on the shared dates of the reconstructed and a
    LIVE reference frame (polygon_gex summary_<ROOT>), report:
      - net_gex_corr_raw      : Pearson on all shared dates (diluted by T-1 lag).
      - net_gex_corr_same_spot: Pearson after filtering to sessions where the
                                reconstructed underlying spot and live spot agree within
                                _SPOT_TOL_FRAC (0.5 %).  This separates settlement-timing
                                mismatch from model mismatch — the PR #1374 claim of
                                0.94–0.998 is grounded in this filtered measure.
      - regime_agreement_raw  : sign-agreement rate across all shared dates.
      - regime_agreement_same_spot: sign-agreement on same-spot subset.
      - n_same_spot           : number of rows that pass the spot filter.
    Pure — no tuning, just measurement. A materially divergent overlap is a FINDING for
    the caller to surface, not something to hide."""
    ri = recon.copy(); li = live.copy()
    ri.index = pd.to_datetime(ri.index).normalize()
    li.index = pd.to_datetime(li.index).normalize()
    j = ri.join(li, how="inner", lsuffix="_r", rsuffix="_l")
    n = int(len(j))
    out: dict = {
        "n_overlap": n,
        # raw (all shared dates — includes T-1 settlement lag)
        "net_gex_corr_raw": None,
        "regime_agreement_raw": None,
        "mean_abs_net_gex_diff_raw": None,
        # same-spot filtered (removes timing mismatch)
        "spot_tol_frac": _SPOT_TOL_FRAC,
        "n_same_spot": 0,
        "net_gex_corr_same_spot": None,
        "regime_agreement_same_spot": None,
        "mean_abs_net_gex_diff_same_spot": None,
    }
    if n == 0:
        return out
    a = pd.to_numeric(j["net_gex_bn_r"], errors="coerce")
    b = pd.to_numeric(j["net_gex_bn_l"], errors="coerce")
    m = a.notna() & b.notna()
    # --- raw metrics ---
    if m.sum() >= 2 and a[m].std() > 0 and b[m].std() > 0:
        out["net_gex_corr_raw"] = round(float(a[m].corr(b[m])), 4)
    if m.sum() >= 1:
        out["mean_abs_net_gex_diff_raw"] = round(float((a[m] - b[m]).abs().mean()), 4)
    if "gamma_regime_r" in j.columns and "gamma_regime_l" in j.columns:
        agree = (j["gamma_regime_r"].astype(str) == j["gamma_regime_l"].astype(str))
        out["regime_agreement_raw"] = round(float(agree.mean()), 4)
    # --- same-spot filter ---
    # spot_r = reconstructed spot (same-session T+0 from greeks store).
    # spot_l = live source spot (typically T-1 close carried into the next trading day).
    # Filter to rows where both agree within tolerance; those rows have no timing mismatch.
    if "spot_r" in j.columns and "spot_l" in j.columns:
        sr = pd.to_numeric(j["spot_r"], errors="coerce")
        sl = pd.to_numeric(j["spot_l"], errors="coerce")
        same_spot = (sr - sl).abs() / sr.abs().clip(lower=1e-6) < _SPOT_TOL_FRAC
        ms = m & same_spot
        out["n_same_spot"] = int(ms.sum())  # match the actual correlation sample (m & same_spot)
        if ms.sum() >= 2 and a[ms].std() > 0 and b[ms].std() > 0:
            out["net_gex_corr_same_spot"] = round(float(a[ms].corr(b[ms])), 4)
        if ms.sum() >= 1:
            out["mean_abs_net_gex_diff_same_spot"] = round(
                float((a[ms] - b[ms]).abs().mean()), 4)
        if "gamma_regime_r" in j.columns and "gamma_regime_l" in j.columns:
            agree_ss = (j["gamma_regime_r"].astype(str) == j["gamma_regime_l"].astype(str))
            out["regime_agreement_same_spot"] = round(float(agree_ss[same_spot].mean()), 4)
    return out


def run_audit(outdir: Path, roots: list[str]) -> dict:
    """Compare each reconstructed root against its live polygon_gex summary on the
    2026-06-15-> overlap, plus a note vs the SPX cboe/gex current-day store."""
    from lib import store
    reports = {}
    for root in roots:
        rp = outdir / f"{root}.parquet"
        if not rp.exists():
            continue
        recon = pd.read_parquet(rp)
        summ = config.data_dir() / "polygon_gex" / f"summary_{root}.parquet"
        if not summ.exists():
            reports[root] = {"note": "no live polygon summary to audit against"}
            continue
        live = pd.read_parquet(summ)
        reports[root] = audit_overlap(recon, live)
    # SPX/SPXW: NOT reconstructed in this run (backfill state does not list them as
    # completed; see _roots_to_build exclusion logic).  The cboe/gex store holds a
    # short daily SPX snapshot usable as a spot-check against SPY.
    # NOTE: the cboe store and the SPY reconstructed series are DIFFERENT UNDERLYINGS
    # (SPX ≠ SPY/10x).  This comparison is directional only (regime sign).
    try:
        cboe = store.read("cboe", "gex")
        if cboe is not None and (outdir / "SPY.parquet").exists():
            spy = pd.read_parquet(outdir / "SPY.parquet")
            reports["SPY_vs_cboe_SPX"] = audit_overlap(spy, cboe)
            reports["SPY_vs_cboe_SPX"]["note"] = (
                "directional only: SPX cboe store vs SPY reconstructed "
                "(different underlyings; SPX/SPXW excluded from reconstruction — "
                "backfill_state does not list them complete as of this run)")
    except Exception as e:  # noqa: BLE001 — audit note must never crash the build
        reports["SPY_vs_cboe_SPX"] = {"note": f"cboe compare skipped: {e}"}
    return reports


def shrink_verdict(new: pd.DataFrame, existing_path: Path) -> tuple[bool, str]:
    """May `new` overwrite the parquet already at `existing_path`?

    WHY THIS FENCE EXISTS. The years a run reads come from `_backfill_state.json` in a
    LIVE-MUTATING worktree, and `build_root` skips an absent/empty year with only a
    log.warning. So a mid-write state file, a moved store, or a single unreadable year
    parquet yields a shorter-but-perfectly-valid frame that `to_parquet` used to write
    straight over ~10 years of committed history — the truncation would then be pushed by
    the weekly lane and mirrored to R2, destroying every copy at once.

    Refuses when the new frame has FEWER rows than the existing one, or when its latest
    date REGRESSES (a rebuild that lost the recent end is the worse shape: the staleness
    disclosure downstream keys off exactly that endpoint). `--allow-shrink` is the
    deliberate-re-export escape hatch.

    Returns (ok, reason). A missing/unreadable existing file is always writable.
    """
    if not existing_path.exists():
        return True, "no existing file"
    try:
        old = pd.read_parquet(existing_path)
    except Exception as e:  # noqa: BLE001 — an unreadable existing file is replaceable
        return True, f"existing file unreadable ({e})"
    if not len(old):
        return True, "existing file empty"
    if len(new) < len(old):
        return False, (f"would shrink {len(old)} -> {len(new)} rows; pass --allow-shrink "
                       f"for a deliberate re-export")
    try:
        old_end = pd.Timestamp(old.index.max())
        new_end = pd.Timestamp(new.index.max())
    except Exception:  # noqa: BLE001
        return True, "index endpoints not comparable"
    if new_end < old_end:
        return False, (f"latest date regresses {old_end.date()} -> {new_end.date()}; "
                       f"pass --allow-shrink for a deliberate re-export")
    return True, f"{len(old)} -> {len(new)} rows, through {new_end.date()}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--roots", nargs="*", default=None, help="subset override (testing)")
    ap.add_argument("--min-year", type=int, default=MIN_YEAR)
    ap.add_argument("--out", default=None, help="output dir override (testing)")
    ap.add_argument("--allow-shrink", action="store_true",
                    help="permit a rebuild that has fewer rows or an earlier end date "
                         "than the committed parquet (deliberate re-export only)")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    completed = _completed_map()
    build, excluded = _roots_to_build(completed)
    if args.roots:
        build = [r for r in build if r in args.roots]

    outdir = Path(args.out) if args.out else (config.data_dir() / "index_gex_history")
    outdir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "reconstructed": True,
        "engine": "engine.gex_engine.compute_gex",
        # Provenance: WHICH store this run actually read (resolver output, not a
        # hardcoded guess). Deliberately no wall-clock stamp — the per-root parquet's
        # max index date is the freshness fact, and a clock here would churn the
        # committed manifest on every run.
        "store_root": str(_theta_root()),
        "dealer_sign": "long-call/short-put (call +1, put -1); regime long above flip, short below",
        "era_min_year": args.min_year,
        "roots_read": {},
        "roots_excluded_native_index": excluded + [
            r for r in INDEX_CANDIDATE_NATIVE if r not in build],
        "note": ("SPX/SPXW excluded unless _backfill_state 'completed' lists them; "
                 "read only completed roots/years (house mid-write law)."),
        "cfg": {k: DEFAULTS[k] for k in ("strike_window_pct", "max_expiry_days",
                                          "pct_move", "contract_multiplier", "r", "q")},
    }

    refused: dict[str, str] = {}
    for root in build:
        df, years_read = build_root(root, completed, args.min_year)
        if df.empty:
            log.warning("%s: no rows produced", root)
            continue
        target = outdir / f"{root}.parquet"
        ok, why = shrink_verdict(df, target)
        if not ok and not args.allow_shrink:
            # REFUSED, and deliberately NOT recorded in roots_read — the runner gates its
            # git push on roots_read, so a truncated root cannot reach the commit.
            print(f"::warning title=index-gex-shrink-guard::{root}: {why} — keeping the "
                  f"existing parquet", flush=True)
            log.warning("%s: REFUSED overwrite (%s)", root, why)
            refused[root] = why
            continue
        if not ok:
            log.warning("%s: shrink allowed by --allow-shrink (%s)", root, why)
        df.to_parquet(target)
        manifest["roots_read"][root] = years_read
        log.info("WROTE %s: %d rows %s..%s (years %s; %s)",
                 root, len(df), df.index.min().date(), df.index.max().date(),
                 years_read, why)
    if refused:
        manifest["roots_refused_shrink"] = refused

    # BLOCKING overlap audit vs the live stores (report, never tune-to-match).
    audit = run_audit(outdir, list(manifest["roots_read"].keys()))
    manifest["overlap_audit_2026_06_15_onward"] = audit
    log.info("OVERLAP AUDIT: %s", json.dumps(audit, indent=2))

    (outdir / "_manifest.json").write_text(json.dumps(manifest, indent=2))
    log.info("manifest -> %s", outdir / "_manifest.json")


if __name__ == "__main__":
    main()
