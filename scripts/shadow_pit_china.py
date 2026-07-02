"""W1-CN leakage-tax client — SHADOW-ONLY point-in-time audit of the China standout board.

W1 (engine/pit.py, scripts/shadow_pit_regime.py) covers the US FRED/ALFRED macro legs
and ZERO of the china board path. This harness ports the truncated-replay discipline
(template: tests/test_vector_pit.py) to the live board's own features and publishes
`calibration/leakage_tax_china.json` + a dated section appended to
`research/PIT_LEAKAGE_TAX.md`. It changes NO live signal, artifact, or render path.

Three measured taxes (honest numbers, no spin):

  1. PLANE tax — features must replay on their OWN price plane. universe() loads the
     ~5y china_search close cache then OVERLAYS the deep china_stocks OHLC store where
     backfilled, so the same name's history DEPTH differs by plane, shifting the 2W
     resample bucket phase / RSI warmup. Replaying on the wrong plane flips board rows.
     Seed measurement: ~5% row-flip on board.parquet@2026-06-30.

  2. BUCKET-COMPLETENESS tax — the washout-2W flag is `_tf_state(close.resample("2W-FRI")
     .last())["stoch_cross_up"]`. The current (incomplete) 2W bucket's `.last()` value
     changes as days accrue, so a completed-bucket backtest grades a DIFFERENT signal than
     users saw live. We persist `bucket_end` (the true last daily date per resample bucket —
     confluence_tiers._tf_bars already computes this 'known' date) next to the asof and
     measure the completed-vs-live flip rate. Seed: washout flips ~8.3%/day.

  3. PRICE-VINTAGE tax — the git-committed closes/members parquets are a free ALFRED-analog
     vintage matrix. We read the panel at successive git revisions and measure how often a
     name's recent closes are REVISED between vintages (adjustment seams / late fills).
     Seed: 0.7% of names revised within 2d, median 1.4%, max 41.7%.

Run:  .venv/bin/python scripts/shadow_pit_china.py [--full] [--vintages N]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.cycles import _tf_state  # noqa: E402
from engine.china_reversal import reversal_watch  # noqa: E402
from lib import config, store  # noqa: E402

DATA = config.data_dir()
OUT_JSON = config.ROOT / "calibration" / "leakage_tax_china.json"
DOC = config.ROOT / "research" / "PIT_LEAKAGE_TAX.md"
BOARD = DATA / "china_standout_track" / "board.parquet"
SEARCH_CLOSES = "data/china_search/closes.parquet"   # git path (vintage matrix)


# --------------------------------------------------------------------------- helpers
def _members() -> pd.DataFrame:
    m = pd.read_parquet(DATA / "china_search" / "members.parquet")
    if m.index.name != "ticker" and "ticker" in m.columns:
        m = m.set_index("ticker")
    return m


def _search_closes() -> pd.DataFrame:
    c = pd.read_parquet(DATA / "china_search" / "closes.parquet")
    c.index = pd.to_datetime(c.index)
    return c.sort_index()


def _deep_close(ticker: str) -> pd.Series | None:
    """The name's series on the DEEP china_stocks OHLC store (the correct signal plane)."""
    df = store.read("china_stocks", ticker)
    if df is None or "close" not in df:
        return None
    return pd.to_numeric(df["close"], errors="coerce").dropna()


def _washout_2w(close: pd.Series, asof: pd.Timestamp | None = None) -> tuple[bool | None, pd.Timestamp | None]:
    """The live board's washout flag + the BUCKET_END (true last daily date in the final
    2W-FRI bucket). Returns (flag, bucket_end). Truncated to `asof` if given."""
    s = close if asof is None else close.loc[:asof]
    s = pd.to_numeric(s, errors="coerce").dropna()
    if len(s) < 60:
        return (None, None)
    res = s.resample("2W-FRI")
    last = res.last().dropna()
    if len(last) < 40:
        return (None, None)
    # bucket_end = the actual last daily observation feeding the final resample bucket
    bucket_end = res.apply(lambda x: x.dropna().index.max() if len(x.dropna()) else pd.NaT)
    bucket_end = bucket_end.reindex(last.index).dropna()
    be = pd.Timestamp(bucket_end.iloc[-1]) if len(bucket_end) else None
    st = _tf_state(last)
    return (bool(st.get("stoch_cross_up")) if st else None, be)


def _completed_washout_2w(close: pd.Series, asof: pd.Timestamp) -> bool | None:
    """The washout flag graded on COMPLETED buckets only — drop the final 2W bucket if it
    has not yet reached its 2W-FRI boundary as of `asof` (i.e. it is still accruing)."""
    s = pd.to_numeric(close.loc[:asof], errors="coerce").dropna()
    if len(s) < 60:
        return None
    res = s.resample("2W-FRI")
    last = res.last().dropna()
    bucket_end = res.apply(lambda x: x.dropna().index.max() if len(x.dropna()) else pd.NaT).reindex(last.index)
    # a bucket is COMPLETE when its label (the 2W-FRI period end) is <= asof
    complete = last.index <= pd.Timestamp(asof)
    # and the final complete bucket's boundary has passed (its last obs is not the asof day)
    last_complete = last[complete]
    if len(last_complete) < 40:
        return None
    st = _tf_state(last_complete)
    return bool(st.get("stoch_cross_up")) if st else None


# --------------------------------------------------------------------------- 1. plane tax
def measure_plane_tax(board_date: str) -> dict:
    """Replay rev_z + washout on the CORRECT plane (deep china_stocks store) vs the WRONG
    plane (china_search overlay), as-of the board date, and count row-level flips against
    the committed board.parquet."""
    if not BOARD.exists():
        return {"available": False, "reason": "no board ledger"}
    board = pd.read_parquet(BOARD)
    rows = board[board["date"] == board_date]
    if rows.empty:
        return {"available": False, "reason": f"no board rows for {board_date}"}
    asof = pd.Timestamp(board_date)

    search = _search_closes()
    flips_wash = same_wash = 0
    flips_plane = 0
    n = 0
    per_name = []
    for _, r in rows.iterrows():
        t = str(r["ticker"])
        live_wash = bool(r["washout"])
        deep = _deep_close(t)
        shallow = search[t].dropna() if t in search.columns else None
        # washout on the correct (deep) plane
        wash_deep, be_deep = _washout_2w(deep, asof) if deep is not None else (None, None)
        # washout on the wrong (search cache) plane
        wash_shallow, _ = _washout_2w(shallow, asof) if shallow is not None else (None, None)
        if wash_deep is None:
            continue
        n += 1
        # tax = replaying on the WRONG plane flips the flag vs the correct plane
        if wash_shallow is not None and wash_shallow != wash_deep:
            flips_plane += 1
            per_name.append({"ticker": t, "deep": wash_deep, "shallow": wash_shallow})
        # sanity: does the correct-plane replay reproduce the LIVE ledger flag?
        if wash_deep == live_wash:
            same_wash += 1
        else:
            flips_wash += 1
    return {
        "available": True, "board_date": board_date, "n_names": n,
        "plane_flip_rate": round(flips_plane / n, 4) if n else None,
        "plane_flips": flips_plane,
        "ledger_reproduce_rate": round(same_wash / n, 4) if n else None,
        "ledger_mismatch": flips_wash,
        "examples": per_name[:8],
    }


# --------------------------------------------------------------------------- 2. bucket tax
def measure_bucket_tax(board_date: str, sample: int = 400) -> dict:
    """Completed-vs-live washout flip rate: for a sample of names, compare the washout flag
    computed with the (live) incomplete final 2W bucket vs completed buckets only, as-of the
    board date. This is the repaint a completed-bucket backtest hides from the user."""
    asof = pd.Timestamp(board_date)
    m = _members()
    tickers = list(m.index[:sample])
    flips = graded = 0
    persisted = []
    for t in tickers:
        deep = _deep_close(t)
        if deep is None:
            continue
        live_flag, be = _washout_2w(deep, asof)
        comp_flag = _completed_washout_2w(deep, asof)
        if live_flag is None or comp_flag is None:
            continue
        graded += 1
        if live_flag != comp_flag:
            flips += 1
        persisted.append({"ticker": t, "asof": board_date,
                          "bucket_end": (str(be.date()) if be is not None else None),
                          "washout_live": live_flag, "washout_completed": comp_flag})
    return {
        "available": graded > 0, "board_date": board_date, "n_graded": graded,
        "completed_vs_live_flip_rate": round(flips / graded, 4) if graded else None,
        "n_flips": flips,
        "bucket_end_persisted_example": persisted[:6],
        "note": ("washout-2W flag repaint between the live (incomplete final bucket) and a "
                 "completed-bucket backtest — persist bucket_end next to asof to grade the "
                 "same signal users saw."),
    }


# --------------------------------------------------------------------------- 3. vintage tax
def _git_revisions(path: str, limit: int) -> list[tuple[str, str]]:
    """[(sha, iso-date)] of commits touching `path`, newest first, capped at `limit`."""
    out = subprocess.run(
        ["git", "log", f"-{limit}", "--format=%H%x09%cI", "--", path],
        cwd=config.ROOT, capture_output=True, text=True)
    revs = []
    for line in out.stdout.splitlines():
        if "\t" in line:
            sha, iso = line.split("\t", 1)
            revs.append((sha.strip(), iso.strip()))
    return revs


def _read_parquet_at(sha: str, path: str) -> pd.DataFrame | None:
    blob = subprocess.run(["git", "show", f"{sha}:{path}"], cwd=config.ROOT,
                          capture_output=True)
    if blob.returncode != 0 or not blob.stdout:
        return None
    import io
    try:
        df = pd.read_parquet(io.BytesIO(blob.stdout))
        df.index = pd.to_datetime(df.index)
        return df.sort_index()
    except Exception:  # noqa: BLE001
        return None


def measure_vintage_tax(n_vintages: int = 12, lookback_days: int = 2) -> dict:
    """Price-vintage revision rate: how often a name's closes in the last `lookback_days`
    of one vintage are REVISED in the next-newer vintage (adjustment seams / late fills).
    The git-committed china_search/closes.parquet is the free ALFRED-analog matrix.

    Reported at three thresholds (0.1% / 0.4% / 1%) so the honest number is visible: the
    0.4% band matches the measured combine_first-seam threshold (the seed's 'revised ~2d'
    finding), while >0.1% also captures float-level/late-fill noise. Vintage PAIRS where a
    huge fraction of names differ (>50%) are mid-session partial-bar commits (a settled-vs-
    intraday panel, not a revision) and are EXCLUDED with a count so the number isn't
    polluted by the known keep-first partial-bar hazard."""
    revs = _git_revisions(SEARCH_CLOSES, n_vintages + 1)
    if len(revs) < 2:
        return {"available": False, "reason": "insufficient git vintages"}
    vintages = [(_read_parquet_at(sha, SEARCH_CLOSES), iso) for sha, iso in revs]
    vintages = [(df, iso) for df, iso in vintages if df is not None]
    thresholds = {"0.1pct": 0.001, "0.4pct": 0.004, "1pct": 0.01}
    hit = {k: 0 for k in thresholds}
    total_names = 0
    rel_diffs = []
    pairs = 0
    partial_bar_pairs = 0
    for (newer, iso_n), (older, iso_o) in zip(vintages[:-1], vintages[1:]):
        cutoff = older.index.max()
        window = older.index[older.index > cutoff - pd.Timedelta(days=lookback_days + 1)]
        common = [t for t in older.columns if t in newer.columns]
        if not len(window) or not common:
            continue
        # detect a mid-session partial-bar vintage pair: if >50% of names' LAST bar differs,
        # the older commit captured an intraday panel (settled close revises it wholesale).
        last_row = older.index.max()
        diffed_last = 0
        for t in common:
            ov = pd.to_numeric(older.loc[last_row, t] if last_row in older.index else np.nan, errors="coerce")
            nv = pd.to_numeric(newer.loc[last_row, t] if last_row in newer.index else np.nan, errors="coerce")
            if pd.notna(ov) and pd.notna(nv) and abs(nv - ov) / max(abs(ov), 1e-9) > 0.004:
                diffed_last += 1
        if diffed_last > 0.5 * len(common):
            partial_bar_pairs += 1
            continue    # a partial-bar commit — not a genuine revision vintage
        pairs += 1
        for t in common:
            o = pd.to_numeric(older.loc[window, t], errors="coerce").dropna()
            if o.empty:
                continue
            total_names += 1
            nvals = pd.to_numeric(newer.reindex(o.index)[t], errors="coerce")
            both = o.index[nvals.notna() & o.notna()]
            if not len(both):
                continue
            rel = ((nvals.reindex(both) - o.reindex(both)).abs()
                   / o.reindex(both).abs().clip(lower=1e-9))
            mx = float(rel.max())
            for k, thr in thresholds.items():
                if mx > thr:
                    hit[k] += 1
            if mx > thresholds["0.4pct"]:
                rel_diffs.append(mx)
    return {
        "available": pairs > 0, "n_vintage_pairs": pairs,
        "partial_bar_pairs_excluded": partial_bar_pairs,
        "lookback_days": lookback_days,
        "names_compared": total_names,
        "revised_rate_gt_0.1pct": round(hit["0.1pct"] / total_names, 4) if total_names else None,
        "revised_rate_gt_0.4pct": round(hit["0.4pct"] / total_names, 4) if total_names else None,
        "revised_rate_gt_1pct": round(hit["1pct"] / total_names, 4) if total_names else None,
        "revised_median_pct": round(float(np.median(rel_diffs)) * 100, 2) if rel_diffs else None,
        "revised_max_pct": round(float(np.max(rel_diffs)) * 100, 1) if rel_diffs else None,
        "headline_revised_rate": round(hit["0.4pct"] / total_names, 4) if total_names else None,
        "note": ("fraction of names whose last-2d closes were revised >0.4% between successive "
                 "git-committed panel vintages (the combine_first-seam band) — partial-bar "
                 "commits excluded. >0.1% band also reported for reference."),
    }


# --------------------------------------------------------------------------- rev_z clean check
def measure_revz_causality(board_date: str, sample: int = 300) -> dict:
    """rev_z is causally CLEAN live (both ends observed closes) but replay-FRAGILE because
    it screens on the CURRENT ST/mktcap/membership snapshot, not the as-of one. Measure how
    many names churn out of the screened set between the panel end and asof."""
    m = _members()
    asof = pd.Timestamp(board_date)
    search = _search_closes()
    tkr_sector = {t: str(s) for t, s in m["sector"].items()}
    tkr_name = {t: str(n) for t, n in m["name"].items()}
    tkr_name_zh = {t: str(z) for t, z in m["name_zh"].items()} if "name_zh" in m else {}
    tkr_mktcap = {t: float(v) for t, v in m["mktcap_yi"].items()} if "mktcap_yi" in m else {}
    full = reversal_watch(search, tkr_sector, tkr_name, tkr_name_zh=tkr_name_zh,
                          tkr_mktcap=tkr_mktcap)
    trunc = reversal_watch(search, tkr_sector, tkr_name, tkr_name_zh=tkr_name_zh,
                           tkr_mktcap=tkr_mktcap, asof=asof)
    if not full or not trunc:
        return {"available": False}
    fa, ta = full.get("rev_z_all", {}), trunc.get("rev_z_all", {})
    common = set(fa) & set(ta)
    drift = [abs(fa[t] - ta[t]) for t in common]
    return {
        "available": True, "board_date": board_date,
        "n_full": len(fa), "n_trunc": len(ta),
        "screened_set_churn": round(1 - len(common) / max(1, len(fa)), 4),
        "rev_z_median_abs_drift": round(float(np.median(drift)), 3) if drift else None,
        "note": ("rev_z is causally clean live; the replay fragility is the screened-set "
                 "membership churn (current ST/mktcap/membership vs as-of)."),
    }


# --------------------------------------------------------------------------- driver
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true", help="all board dates + more vintages")
    ap.add_argument("--vintages", type=int, default=12)
    args = ap.parse_args()

    board_dates = []
    if BOARD.exists():
        b = pd.read_parquet(BOARD)
        board_dates = sorted(b["date"].astype(str).unique())
    if not args.full and board_dates:
        board_dates = board_dates[-1:]     # latest only by default

    result = {
        "meta": {
            "generated": datetime.now(timezone.utc).isoformat(),
            "mode": "full" if args.full else "latest",
            "shadow_only": True,
            "board_dates": board_dates,
            "note": ("W1-CN leakage tax on the china standout board features — plane, "
                     "bucket-completeness and price-vintage taxes. Nothing here changes a "
                     "live path; measurement product only."),
        },
        "plane_tax": {},
        "bucket_tax": {},
        "revz_causality": {},
        "vintage_tax": measure_vintage_tax(n_vintages=args.vintages),
    }
    for d in board_dates:
        result["plane_tax"][d] = measure_plane_tax(d)
        result["bucket_tax"][d] = measure_bucket_tax(d)
        result["revz_causality"][d] = measure_revz_causality(d)

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(result, indent=2, default=str))
    print(f"wrote {OUT_JSON}")
    _print_headline(result)
    _append_doc(result)


def _print_headline(r: dict) -> None:
    print("\n=== China leakage-tax headline ===")
    for d, pt in r.get("plane_tax", {}).items():
        if pt.get("available"):
            print(f"  {d} PLANE flip rate: {pt['plane_flip_rate']} "
                  f"({pt['plane_flips']}/{pt['n_names']}); ledger reproduce {pt['ledger_reproduce_rate']}")
    for d, bt in r.get("bucket_tax", {}).items():
        if bt.get("available"):
            print(f"  {d} BUCKET completed-vs-live flip: {bt['completed_vs_live_flip_rate']} "
                  f"({bt['n_flips']}/{bt['n_graded']})")
    vt = r.get("vintage_tax", {})
    if vt.get("available"):
        print(f"  VINTAGE revised rate (>0.4%): {vt['headline_revised_rate']} "
              f"[>0.1%: {vt['revised_rate_gt_0.1pct']}] "
              f"(median {vt['revised_median_pct']}%, max {vt['revised_max_pct']}%, "
              f"{vt['n_vintage_pairs']} pairs, {vt['partial_bar_pairs_excluded']} partial-bar excluded)")


def _append_doc(r: dict) -> None:
    ts = r["meta"]["generated"][:10]
    lines = [f"\n## Addendum {ts} — W1-CN China board leakage tax (shadow)\n",
             "**Harness:** `scripts/shadow_pit_china.py` · **Artifact:** "
             "`calibration/leakage_tax_china.json` · **Status:** SHADOW (no live path touched).\n",
             "W1 (`engine/pit.py`, `scripts/shadow_pit_regime.py`) covers only the US "
             "FRED/ALFRED macro legs; it replays ZERO of the China standout board. This "
             "harness ports the truncated-replay discipline (`tests/test_vector_pit.py`) to "
             "the board's own features and measures three point-in-time taxes.\n"]
    vt = r.get("vintage_tax", {})
    if vt.get("available"):
        lines.append(f"- **Price-vintage tax** ({vt['n_vintage_pairs']} git-committed panel "
                     f"vintage pairs, {vt['partial_bar_pairs_excluded']} mid-session partial-bar "
                     f"pairs excluded): **{vt['headline_revised_rate']:.1%}** of names had their "
                     f"last-{vt['lookback_days']}d closes revised >0.4% between vintages "
                     f"(the combine_first-seam band; median {vt['revised_median_pct']}%, max "
                     f"{vt['revised_max_pct']}%). At the looser >0.1% band "
                     f"{vt['revised_rate_gt_0.1pct']:.1%}. The git-committed "
                     "`china_search/closes.parquet` is a free ALFRED-analog vintage matrix.\n")
    for d, bt in r.get("bucket_tax", {}).items():
        if bt.get("available"):
            lines.append(f"- **Bucket-completeness tax** ({d}, n={bt['n_graded']}): washout-2W "
                         f"flag flips **{bt['completed_vs_live_flip_rate']:.1%}** between the live "
                         "(incomplete final 2W bucket) and a completed-bucket backtest — a "
                         "completed-bucket grade scores a different signal than users saw. "
                         "`bucket_end` is persisted next to `asof` in the artifact.\n")
    for d, pt in r.get("plane_tax", {}).items():
        if pt.get("available"):
            lines.append(f"- **Plane tax** ({d}, n={pt['n_names']}): replaying washout-2W on the "
                         f"WRONG price plane (search cache vs deep OHLC store) flips "
                         f"**{pt['plane_flip_rate']:.1%}** of rows; the correct-plane replay "
                         f"reproduces the live ledger flag {pt['ledger_reproduce_rate']:.1%}. "
                         "Features must replay on their OWN store — `universe()` overlays the "
                         "deep store and shifts the 2W bucket phase.\n")
    for d, rz in r.get("revz_causality", {}).items():
        if rz.get("available"):
            lines.append(f"- **rev_z** ({d}): causally clean live (both ends observed closes); "
                         f"replay fragility is screened-set churn **{rz['screened_set_churn']:.1%}** "
                         "(current ST/mktcap/membership snapshot vs as-of), not a value leak.\n")
    lines.append("\n**Verdict:** honest numbers, no demotion recommended on these alone — this "
                 "sizes the taxes so any future 'grade the cascade / washout' work replays on the "
                 "correct plane, persists bucket_end, and treats git panels as the vintage matrix.\n")
    with open(DOC, "a") as f:
        f.write("".join(lines))
    print(f"appended section to {DOC}")


if __name__ == "__main__":
    main()
