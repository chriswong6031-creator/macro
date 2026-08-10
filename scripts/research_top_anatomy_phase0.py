"""TOP ANATOMY Phase-0 harness — extended-move anatomy: topped vs continued.

Runs the frozen construction in `research/top_anatomy/TOPA_PHASE0_PREREG.md` §4
over two tracks and writes the two committed artifacts: a vintage-stamped summary
JSON and `reports/top-anatomy-phase0.md`.

THE QUESTION. Among days when a name is ALREADY EXTENDED, does anything
point-in-time separate the days that go on to top from the days that keep going —
beyond what extension magnitude and realized volatility already separate (they
are matched away)? Never "collapsed names vs average names": extension is a
prerequisite for some tops, not proof of one, so the only honest contrast is
extended-that-topped against extended-that-continued.

WHAT RUNS (prereg §4–§5)
  E1   36 features x matched-control contrast, month-block CI, BH-FDR within family
  E1b  pooled AUC increment over an extension-only baseline (grouped + walk-forward)
  E2   lead-time profiles -> EARLY / MID / LATE / POST-TOP CONFIRMATION labels
  E3   descriptive first-crossing ordering of survivors
  E4   era and dollar-volume-tercile sign stability
  G0.2 delisting verification (the Wide track's dead names, named not assumed)
  Today's tape: the current extended cohort with its feature readout

TIER. Research / display tier, zero scored authority; AVOID-not-SHORT (the outputs
are entry-side avoidance and trim-conviction CONTEXT, never a directional bear
position and never an exit rule). A discovery phase-0 has no program kill on a
null: a well-powered null re-scopes Wave-1 copy, it does not close the search.

DATA HONESTY
  * Track W (`data/massive_stock_day`, the registration track) is UNADJUSTED; split
    repair reuses the canonical yahoo-verified `scripts.replay_standout_pipeline
    .split_adjust`. Dividends are not adjusted (a small stated downward drift).
  * Tickers get REUSED. Every ticker's tape is cut at interior gaps > 60 sessions
    into identity segments, so a reassigned ticker can never stitch two companies
    into one forward path (`engine.top_anatomy`, prereg ratification log).
  * Track D (`engine.price_ladder` adjusted rungs, first-rung-wins) is a CURATED
    universe: names that topped and died are underrepresented, so its topped-arm
    severity is understated. Every D table says so.
  * The run's last data day is derived FROM THE PANEL, never from a manifest, and
    stamped on every artifact alongside the git sha.

Run:
  python -m scripts.research_top_anatomy_phase0 --data-root <primary>/data
  python -m scripts.research_top_anatomy_phase0 --data-root <...> --track W --quick 300
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

from engine import price_ladder, top_anatomy as ta  # noqa: E402
from scripts.replay_standout_pipeline import split_adjust  # noqa: E402

FAMILY = "top_anatomy_p0"
CACHE_SUBDIR = "research/top_anatomy_p0"
#: `raw_close`/`raw_dvol` carry the AS-PRINTED prints the §3 floors are evaluated on;
#: `split_day` flags the factor step day (ineligible). Everything else is repaired.
W_PANEL_COLS = ("close", "open", "high", "low", "volume", "raw_close", "raw_dvol",
                "split_day")
D_START = "1997-01-01"
SAMPLE_EVERY = 5                      # 1-in-5 systematic sample of all EXT days
#: §4.8 windows, stated POSITIVE-BEFORE-PEAK: days_to_peak = peak_date − d.
E2_BUCKETS = ((22, 63), (6, 21), (1, 5), (-5, 0))
E2_LABELS = {(22, 63): "EARLY", (6, 21): "MID", (1, 5): "LATE",
             (-5, 0): "POST-TOP CONFIRMATION"}
PARITY_SAMPLE_NAMES = 3               # §3 hard pre-run gate, per track
PARITY_TOLERANCE = 1e-9
W_ERAS = (("2021H2-2022", "2021-07-01", "2022-12-31"),
          ("2023-2024", "2023-01-01", "2024-12-31"),
          ("2025-2026", "2025-01-01", "2099-12-31"))
D_ERAS = (("1997-2003", "1997-01-01", "2003-12-31"),
          ("2004-2012", "2004-01-01", "2012-12-31"),
          ("2013-2020", "2013-01-01", "2020-12-31"),
          ("2021-2026", "2021-01-01", "2099-12-31"))
COVERAGE_FLOOR = 0.60
TODAY_TAPE_CAP = 200

_T0 = time.time()


def say(msg: str) -> None:
    """Plain progress print — no logging config, no GitHub annotations (off-lane)."""
    print(f"[{time.time() - _T0:7.1f}s] {msg}", flush=True)


# ══════════════════════════════════════════════════════════════════════════════
# panels
# ══════════════════════════════════════════════════════════════════════════════
def _wide(segments: dict[str, pd.DataFrame], col: str) -> pd.DataFrame:
    have = {k: v[col] for k, v in segments.items() if col in v.columns}
    return pd.DataFrame(have).sort_index() if have else pd.DataFrame()


def repair_bars(df: pd.DataFrame) -> pd.DataFrame:
    """THE repair path: split-repair one ticker's RAW bars, carrying the factor to all legs.

    `split_adjust` recovers a share-split factor from the close series; §3 requires
    it to be carried to **open/high/low/close by DIVISION and to volume by
    MULTIPLICATION**, so repaired close×volume is invariant across the repair and a
    liquidity floor cannot move because a name split. The as-printed `raw_close` and
    `raw_dvol` ride along because the §3 price/liquidity floors are evaluated on the
    RAW prints, and `split_day` marks the factor STEP DAY, which is ineligible.

    This is the single function both `build_panel_w` and the full-series-vs-prefix
    parity gate call — a parity test against a re-implementation of the repair would
    prove nothing about the repair the study actually runs.
    """
    px = pd.to_numeric(df["close"], errors="coerce").dropna()
    factor = (px / split_adjust(px)).reindex(df.index).ffill().bfill()
    raw_c = pd.to_numeric(df["close"], errors="coerce")
    raw_v = pd.to_numeric(df["volume"], errors="coerce") if "volume" in df.columns \
        else pd.Series(np.nan, index=df.index)
    out = {"close": raw_c / factor, "volume": raw_v * factor,
           "raw_close": raw_c, "raw_dvol": raw_c * raw_v,
           "split_day": factor.diff().fillna(0.0).abs() > 1e-9}
    for c in ("open", "high", "low"):
        if c in df.columns:
            out[c] = pd.to_numeric(df[c], errors="coerce") / factor
    return pd.DataFrame(out).dropna(subset=["close"])


def _finish_panel(bars: dict[str, pd.DataFrame], cache: Path, tag: str) -> dict:
    """Identity-segment a per-ticker store, widen it, and cache the frames."""
    calendar = pd.DatetimeIndex(sorted({d for b in bars.values() for d in b.index}))
    segs = ta.split_identity_segments(bars, calendar)
    n_split = len({ta.segment_ticker(s) for s in segs if "#" in s})
    say(f"{tag}: {len(bars)} tickers -> {len(segs)} identity segments "
        f"({n_split} tickers split on a >60-session gap)")
    panel = {c: _wide(segs, c) for c in W_PANEL_COLS}
    panel["close"] = panel["close"].reindex(calendar)
    for c in W_PANEL_COLS:
        if not panel[c].empty:
            panel[c] = panel[c].reindex(index=calendar, columns=panel["close"].columns)
            if c == "split_day":
                panel[c] = panel[c].fillna(False).astype(bool)
    cache.mkdir(parents=True, exist_ok=True)
    for c, fr in panel.items():
        if not fr.empty:
            fr.to_parquet(cache / f"panel_{c}.parquet")
    meta = {"n_tickers": len(bars), "n_segments": len(segs), "n_tickers_split": n_split,
            "n_split_factor_step_days": (int(panel["split_day"].to_numpy().sum())
                                         if not panel["split_day"].empty else 0)}
    (cache / "meta.json").write_text(json.dumps(meta, indent=2))
    return {"panel": panel, "meta": meta}


#: Legs a cache MUST carry to be usable. `raw_close`/`raw_dvol`/`split_day` are the
#: §3 floor inputs: a cache written before they existed would silently fall the
#: floors back to repaired prices — the exact leak §3 closes — so a cache missing
#: any of them is REBUILT, never partially loaded.
_REQUIRED_PANEL_LEGS = ("close", "raw_close", "raw_dvol", "split_day")


def _load_cached(cache: Path) -> dict | None:
    if not (cache / "meta.json").exists():
        return None
    missing = [c for c in _REQUIRED_PANEL_LEGS
               if not (cache / f"panel_{c}.parquet").exists()]
    if missing:
        say(f"cache at {cache} predates the raw-eligibility legs ({', '.join(missing)}) "
            "— rebuilding rather than running the floors on repaired prices")
        return None
    panel = {}
    for c in W_PANEL_COLS:
        p = cache / f"panel_{c}.parquet"
        panel[c] = pd.read_parquet(p) if p.exists() else pd.DataFrame()
    if not panel["split_day"].empty:
        panel["split_day"] = panel["split_day"].fillna(False).astype(bool)
    return {"panel": panel, "meta": json.loads((cache / "meta.json").read_text())}


def build_panel_w(data_root: Path, cache: Path, *, quick: int | None = None) -> dict:
    """Track W: split-repaired, identity-segmented wide OHLCV from `massive_stock_day`.

    The pre-filter is a strict SUPERSET of §3 eligibility — a name is dropped only
    when it can never clear a floor on ANY day (its whole-series maximum close is
    under $3, its best 21d median dollar volume is under $2M, or it has fewer bars
    than the 261 a single EXT day needs). Dropping on a per-day floor here would
    silently delete the population the study exists to measure.
    """
    cached = _load_cached(cache)
    if cached is not None:
        say(f"track W: panel cache hit at {cache} "
            f"({cached['meta']['n_segments']} segments)")
        return cached
    files = sorted((data_root / "massive_stock_day").glob("*.parquet"))
    if quick:
        files = files[:quick]
    say(f"track W: scanning {len(files)} ticker files in {data_root / 'massive_stock_day'}")
    keep: dict[str, pd.DataFrame] = {}
    for k, f in enumerate(files):
        if k and k % 2500 == 0:
            say(f"track W: ...{k}/{len(files)} scanned, {len(keep)} kept")
        try:
            df = pd.read_parquet(f)
        except Exception:  # noqa: BLE001 — one torn vendor file must not kill the scan
            continue
        if len(df) < 261 or not {"close", "volume"} <= set(df.columns):
            continue
        df = df[~df.index.duplicated(keep="last")].sort_index()
        px = pd.to_numeric(df["close"], errors="coerce").dropna()
        vol = pd.to_numeric(df["volume"], errors="coerce").reindex(px.index)
        if len(px) < 261 or float(px.max()) < ta.MIN_CLOSE:
            continue
        dv21 = (px * vol).rolling(21, min_periods=21).median()
        if not (dv21.max() >= ta.MIN_MEDIAN_DVOL21):
            continue
        frame = repair_bars(df)
        if len(frame) >= 261:
            keep[f.stem] = frame
    say(f"track W: {len(keep)} tickers pass the superset pre-filter")
    return _finish_panel(keep, cache, "track W")


_D_RUNGS = (("baskets_ohlcv", "baskets/ohlcv"), ("yahoo", "yahoo"), ("data_stocks", "stocks"))


def build_panel_d(data_root: Path, cache: Path, *, quick: int | None = None) -> dict:
    """Track D: adjusted OHLCV on the `engine.price_ladder` rungs, FIRST-RUNG-WINS.

    The ladder contract is imported rather than restated (`price_ladder
    .ADJUSTED_SOURCES`), but the per-name read pulls OHLCV instead of close alone,
    since `resolve_close` returns only the close leg. Rungs carry different column
    sets — `yahoo` has no open/high/low, `data_stocks` has no open — so those
    features are NULL on those names and counted, never imputed.

    SURVIVORSHIP: this is a curated-current universe. Names that topped and died
    before basket curation are missing, so the topped arm is understated here. D
    is era CONTEXT and can never register a claim.
    """
    cached = _load_cached(cache)
    if cached is not None:
        say(f"track D: panel cache hit at {cache} "
            f"({cached['meta']['n_segments']} segments)")
        return cached
    assert price_ladder.ADJUSTED_SOURCES[:3] == tuple(s for s, _ in _D_RUNGS), \
        "the ladder's adjusted rung ORDER moved; re-read engine/price_ladder.py"
    names: list[str] = []
    for _, sub in _D_RUNGS:
        d = data_root / sub
        if d.exists():
            names.extend(p.stem for p in d.glob("*.parquet") if not p.stem.startswith("_"))
    names = sorted(set(names))
    if quick:
        names = names[:quick]
    say(f"track D: {len(names)} names across the adjusted rungs")
    keep: dict[str, pd.DataFrame] = {}
    rung_counts = {src: 0 for src, _ in _D_RUNGS}
    for tk in names:
        for src, sub in _D_RUNGS:
            p = data_root / sub / f"{tk}.parquet"
            if not p.exists():
                continue
            try:
                df = pd.read_parquet(p)
            except Exception:  # noqa: BLE001
                continue
            col = next((c for c in ("close", "close_price") if c in df.columns), None)
            if col is None:
                continue
            df = df[~df.index.duplicated(keep="last")].sort_index()
            df.index = pd.to_datetime(df.index)
            df = df[df.index >= pd.Timestamp(D_START)]
            out = {"close": pd.to_numeric(df[col], errors="coerce")}
            for c in ("open", "high", "low", "volume"):
                if c in df.columns:
                    out[c] = pd.to_numeric(df[c], errors="coerce")
            # The D rungs are ALREADY split+dividend adjusted, so there is no repair
            # to carry and no factor step day: the as-printed leg IS the adjusted
            # leg. Stated rather than left implicit — a reader must be able to see
            # that raw-level eligibility means something different on this track.
            out["raw_close"] = out["close"]
            out["raw_dvol"] = out["close"] * out.get(
                "volume", pd.Series(np.nan, index=df.index))
            out["split_day"] = pd.Series(False, index=df.index)
            frame = pd.DataFrame(out).dropna(subset=["close"])
            if len(frame) >= 261:
                keep[tk] = frame
                rung_counts[src] += 1
            break                       # first-rung-wins, per the frozen ladder
    say(f"track D: {len(keep)} names kept; rungs {rung_counts}")
    res = _finish_panel(keep, cache, "track D")
    res["meta"]["rung_counts"] = rung_counts
    (cache / "meta.json").write_text(json.dumps(res["meta"], indent=2))
    return res


# ══════════════════════════════════════════════════════════════════════════════
# assembly helpers
# ══════════════════════════════════════════════════════════════════════════════
def _segment_bars(panel: dict[str, pd.DataFrame], segments) -> dict[str, pd.DataFrame]:
    """Per-segment OHLCV frames (each compacted to its own bars) for the feature library."""
    close = panel["close"]
    out = {}
    for s in segments:
        c = close[s]
        c = c[c.notna()]
        if c.empty:
            continue
        d = {"close": c}
        for col in ("open", "high", "low", "volume"):
            fr = panel.get(col)
            if fr is not None and not fr.empty and s in fr.columns:
                d[col] = fr[s].reindex(c.index)
        out[s] = pd.DataFrame(d)
    return out


def _gate_context(close: pd.DataFrame, dvol: pd.DataFrame) -> pd.DataFrame:
    """r126 / rv63 / dvol21 at every bar — the matching gates, computed once."""
    frames = []
    for col in close.columns:
        c = close[col]
        c = c[c.notna()]
        if len(c) < 130:
            continue
        lr = np.log(c).diff()
        dv = dvol[col].reindex(c.index) if col in dvol.columns else pd.Series(np.nan, index=c.index)
        frames.append(pd.DataFrame({
            "segment": col, "ticker": ta.segment_ticker(col), "date": c.index,
            "r126": (c / c.shift(126) - 1.0).to_numpy(),
            "rv63": (lr.rolling(63, min_periods=63).std() * np.sqrt(252.0)).to_numpy(),
            "dvol21": dv.rolling(21, min_periods=21).median().to_numpy(),
        }))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _pick(df: pd.DataFrame, keys: pd.DataFrame) -> pd.DataFrame:
    """Left-join `df`'s VALUE columns onto the (segment, date) rows in `keys`.

    Only columns `keys` does not already carry are joined, so a shared label like
    `ticker` can never split into `ticker_x`/`ticker_y` and silently break a
    downstream contract.
    """
    take = ["segment", "date"] + [c for c in df.columns
                                  if c not in ("segment", "date") and c not in keys.columns]
    return keys.merge(df[take], on=["segment", "date"], how="left")


def _describe(x) -> dict:
    s = pd.Series(x, dtype="float64").dropna()
    if s.empty:
        return {"n": 0, "median": None, "p25": None, "p75": None, "mean": None}
    return {"n": int(len(s)), "median": float(s.median()),
            "p25": float(s.quantile(0.25)), "p75": float(s.quantile(0.75)),
            "mean": float(s.mean())}


# ══════════════════════════════════════════════════════════════════════════════
# §3 hard pre-run gate: a future split may not move a past feature value
# ══════════════════════════════════════════════════════════════════════════════
def _parity_side(rep: pd.DataFrame, d: pd.Timestamp, eqw: pd.Series) -> pd.DataFrame:
    """One side of the parity check: features at d, with the EPISODE anchor rebuilt
    from that side's own bars and the cross-section held fixed.

    The episode context is rebuilt per side on purpose — an episode-anchored feature
    (F1/F2/F5) reading a boundary that moved would fail here. The equal-weight index
    is deliberately NOT rebuilt per side: it compounds the per-day CROSS-SECTIONAL
    MEDIAN DAILY RETURN over thousands of names, and repairing one name's splits
    rescales that name's closes by a constant, which leaves its returns — and
    therefore the index — untouched. Rebuilding it from the single name under test
    would instead make `rs_line = c / index` a degenerate near-constant whose
    63-session argmax is decided by float noise, and the gate would fail on E3f/E4f
    for a reason that has nothing to do with the repair (measured on ABVE, 2026-08).
    The RS family is still fully exercised: `rs_line` carries the split factor, so a
    broken carry would still move E5f's log-slope and E3f's lag.
    """
    close = pd.DataFrame({"T": rep["close"]})
    dvol = pd.DataFrame({"T": rep["close"] * rep.get("volume", np.nan)})
    floors = {"raw_close_df": pd.DataFrame({"T": rep["raw_close"]}),
              "raw_dollar_vol_df": pd.DataFrame({"T": rep["raw_dvol"]}),
              "split_day_df": pd.DataFrame({"T": rep["split_day"]})}
    ext = ta.extended_mask(close, dvol, high_df=pd.DataFrame({"T": rep["high"]})
                           if "high" in rep else None,
                           low_df=pd.DataFrame({"T": rep["low"]}) if "low" in rep else None,
                           **floors)
    eps = ta.extract_episodes(ext, close)
    return ta.feature_library({"T": rep}, eqw, {"T": [d]}, episodes=eps)


def prefix_parity_report(bars: pd.DataFrame, d: pd.Timestamp,
                         eqw: pd.Series | None = None) -> pd.DataFrame:
    """Feature values at d computed from the FULL series vs from a prefix ending at d+1.

    Both sides go through `repair_bars`, the real repair path. The prefix cannot see
    any split after d+1, so its recovered factor differs from the full series' factor
    at every bar ≤ d — if a feature value at d moves with it, that feature is reading
    the future through the repair, and no matched contrast built on it would mean
    anything. ``eqw`` is the track's cross-section, identical on both sides (see
    `_parity_side`). Returns one row per feature with both values and their gap.
    """
    idx = bars.index
    pos = int(idx.searchsorted(pd.Timestamp(d)))
    a = _parity_side(repair_bars(bars), d, eqw)
    b = _parity_side(repair_bars(bars.iloc[:min(pos + 2, len(idx))]), d, eqw)
    rows = []
    for f in ta.FEATURES:
        va = float(a[f].iloc[0]) if len(a) else float("nan")
        vb = float(b[f].iloc[0]) if len(b) else float("nan")
        both_null = not np.isfinite(va) and not np.isfinite(vb)
        gap = 0.0 if both_null else abs(va - vb)
        rows.append({"feature": f, "family": ta.FEATURE_FAMILY[f], "full": va,
                     "prefix": vb, "abs_gap": gap, "null_both": both_null})
    return pd.DataFrame(rows)


def assert_prefix_parity(panel: dict, track: str, eqw: pd.Series, *,
                         n_names: int = PARITY_SAMPLE_NAMES,
                         tol: float = PARITY_TOLERANCE) -> dict:
    """§3 HARD GATE — run the parity check on sampled names and raise before experiments.

    The synthetic version of this lives in `tests/test_top_anatomy.py`; this is the
    runtime half, so the gate also fires on REAL bars with real vendor splits. It runs
    before a single label is computed: a repair that leaks the future must stop the
    run, not appear as a footnote under a result.
    """
    close = panel["close"]
    step = panel.get("split_day")
    cands = []
    if step is not None and not step.empty:                 # prefer names that split
        cands = list(step.columns[step.fillna(False).any().to_numpy()])
    pool = [c for c in cands if close[c].notna().sum() > 400]
    pool += [c for c in close.columns if c not in pool and close[c].notna().sum() > 400]
    checked, worst = [], 0.0
    for seg in pool[:n_names]:
        c = close[seg]
        c = c[c.notna()]
        bars = pd.DataFrame({
            "close": panel["raw_close"][seg].reindex(c.index)
            if not panel.get("raw_close", pd.DataFrame()).empty else c,
            "volume": (panel["raw_dvol"][seg].reindex(c.index)
                       / panel["raw_close"][seg].reindex(c.index))
            if not panel.get("raw_dvol", pd.DataFrame()).empty
            else pd.Series(np.nan, index=c.index),
        }).dropna(subset=["close"])
        if len(bars) < 400:
            continue
        d = bars.index[int(len(bars) * 0.7)]
        rep = prefix_parity_report(bars, d, eqw)
        bad = rep[(rep["abs_gap"] > tol) & rep["abs_gap"].notna()]
        worst = max(worst, float(rep["abs_gap"].max(skipna=True) or 0.0))
        if not bad.empty:
            raise AssertionError(
                f"§3 prefix-parity gate FAILED on track {track} segment {seg} at "
                f"{pd.Timestamp(d).date()}: "
                + ", ".join(f"{r.feature} full={r.full!r} prefix={r.prefix!r}"
                            for r in bad.itertuples())
                + " — a future split is moving a past feature value; stop and fix the "
                  "repair carry before reading any outcome.")
        checked.append({"segment": seg, "asof": str(pd.Timestamp(d).date()),
                        "n_features_compared": int((~rep["null_both"]).sum()),
                        "max_abs_gap": float(rep["abs_gap"].max())})
    say(f"[{track}] §3 prefix-parity gate PASSED on {len(checked)} name(s); "
        f"worst |gap| = {worst:.3g}")
    return {"passed": True, "tolerance": tol, "n_names_checked": len(checked),
            "worst_abs_gap": worst, "names": checked}


def _instrument_census(panel: dict, ext: pd.DataFrame, elig: pd.DataFrame,
                       n_files: int) -> dict:
    """§3 — PRINT the instrument/dead-name census instead of inferring it from a file count."""
    close = panel["close"]
    if close.empty:
        return {"n_files_scanned": n_files, "n_segments": 0}
    last_day = close.index.max()
    cutoff = close.index[max(0, len(close.index) - 61)]
    lasts = close.apply(lambda s: s.last_valid_index())
    dead = lasts[lasts.notna() & (lasts < cutoff)]
    dead_with_ext = [s for s in dead.index if s in ext.columns and bool(ext[s].any())]
    return {
        "n_files_scanned": int(n_files),
        "n_tickers_kept": int(len({ta.segment_ticker(c) for c in close.columns})),
        "n_segments": int(close.shape[1]),
        "n_segments_ever_eligible": int((elig.sum() > 0).sum()),
        "n_segments_with_ext": int((ext.sum() > 0).sum()),
        "last_panel_day": str(last_day.date()),
        "dead_cutoff_last_bar_before": str(pd.Timestamp(cutoff).date()),
        "n_segments_candidate_dead": int(len(dead)),
        "n_candidate_dead_with_ext_day": int(len(dead_with_ext)),
        "share_candidate_dead": (float(len(dead) / close.shape[1])
                                 if close.shape[1] else 0.0),
    }


# ══════════════════════════════════════════════════════════════════════════════
# the track pipeline
# ══════════════════════════════════════════════════════════════════════════════
def run_track(track: str, panel: dict, meta: dict, *, seed: int, quick: bool,
              n_files: int = 0) -> dict:
    """EXT -> episodes -> race -> peaks -> cases/controls -> features -> E1..E4."""
    close = panel["close"]
    volume = panel.get("volume")
    dvol = (close * volume).reindex_like(close) if volume is not None and not volume.empty \
        else pd.DataFrame(np.nan, index=close.index, columns=close.columns)
    raw_close = panel.get("raw_close")
    raw_dvol = panel.get("raw_dvol")
    split_day = panel.get("split_day")
    floors = {"raw_close_df": raw_close if raw_close is not None and not raw_close.empty
              else None,
              "raw_dollar_vol_df": raw_dvol if raw_dvol is not None and not raw_dvol.empty
              else None,
              "split_day_df": split_day if split_day is not None and not split_day.empty
              else None}
    out: dict = {"track": track, "panel": dict(meta)}
    out["panel"].update({
        "n_sessions": int(close.shape[0]), "n_segments": int(close.shape[1]),
        "first_session": str(close.index.min().date()) if len(close) else None,
        "last_session": str(close.index.max().date()) if len(close) else None,
        "floors_on_raw_prints": floors["raw_close_df"] is not None,
    })

    # §3 eligibility and the PIT cross-section come first — neither is an outcome —
    # then the HARD GATE, before a single label exists.
    elig = ta.eligibility_mask(close, dvol, **floors)
    eqw = ta.equal_weight_median_index(close, elig, min_names=20 if not quick else 1)
    out["prefix_parity_gate"] = assert_prefix_parity(panel, track, eqw)

    say(f"[{track}] EXT mask (primary; floors on raw prints, split-step days excluded)")
    ext = ta.extended_mask(close, dvol, high_df=panel.get("high"),
                           low_df=panel.get("low"), **floors)
    n_ext = int(ext.to_numpy().sum())
    out["ext"] = {"n_ext_days": n_ext,
                  "n_eligible_days": int(elig.to_numpy().sum()),
                  "n_segments_with_ext": int((ext.sum() > 0).sum())}
    out["census"] = _instrument_census(panel, ext, elig, n_files)
    say(f"[{track}] {n_ext} EXT days on {out['ext']['n_segments_with_ext']} segments")
    c = out["census"]
    say(f"[{track}] census: {c.get('n_files_scanned')} files scanned · "
        f"{c.get('n_tickers_kept')} tickers · {c.get('n_segments')} segments · "
        f"{c.get('n_segments_ever_eligible')} ever-eligible · "
        f"{c.get('n_segments_candidate_dead')} candidate-dead (last bar before "
        f"{c.get('dead_cutoff_last_bar_before')}) · "
        f"{c.get('n_candidate_dead_with_ext_day')} of those held >=1 EXT day")

    say(f"[{track}] sensitivity arms (report-only)")
    out["ext_variants"] = {"primary": n_ext}
    for variant in ("r63", "atrz"):
        try:
            m = ta.extended_mask(close, dvol, variant=variant, high_df=panel.get("high"),
                                 low_df=panel.get("low"), **floors)
            out["ext_variants"][variant] = int(m.to_numpy().sum())
            out["ext_variants"][f"{variant}_overlap_with_primary"] = int(
                (m & ext).to_numpy().sum())
        except Exception as exc:  # noqa: BLE001 — a report-only arm never kills the run
            out["ext_variants"][variant] = None
            out["ext_variants"][f"{variant}_error"] = str(exc)

    if n_ext == 0:
        out["null_reason"] = "no EXT days on this track"
        return out

    say(f"[{track}] episodes")
    episodes = ta.extract_episodes(ext, close)
    out["episodes"] = {
        "n_episodes": int(len(episodes)),
        "n_micro_under_5_ext_days": int(episodes["micro"].sum()),
        "n_e1_eligible": int((~episodes["micro"]).sum()),
        "n_names": int(episodes["ticker"].nunique()),
        "ext_days_per_episode": _describe(episodes["n_ext_days"]),
    }
    say(f"[{track}] {len(episodes)} episodes "
        f"({int(episodes['micro'].sum())} micro) on {episodes['ticker'].nunique()} names")

    say(f"[{track}] race labels")
    race = ta.race_labels(close, ext)
    counts = race["label"].value_counts().to_dict()
    out["race"] = {
        "counts": {k: int(v) for k, v in counts.items()},
        "censor_reasons": {k: int(v) for k, v in
                           race.loc[race["label"] == "CENSORED", "censor_reason"]
                           .value_counts().to_dict().items()},
        "sessions_to_resolve": _describe(race["sessions_to_resolve"]),
        "fwd_ret_63_by_label": {
            k: _describe(g["fwd_ret_63"]) for k, g in race.groupby("label")},
    }
    say(f"[{track}] race: {out['race']['counts']}")

    say(f"[{track}] episode peaks")
    episodes, dtp = ta.episode_peaks(close, episodes, ext)
    out["episodes"]["outcomes"] = {k: int(v) for k, v in
                                   episodes["outcome"].value_counts().to_dict().items()}
    out["episodes"]["n_peak_window_censored"] = int(episodes["peak_window_censored"].sum())
    out["episodes"]["days_to_peak"] = _describe(dtp["days_to_peak"])
    topped_eps = episodes[(episodes["outcome"] == "TOPPED") & (~episodes["micro"])]
    out["episodes"]["n_topped_e1_eligible"] = int(len(topped_eps))
    say(f"[{track}] episode outcomes {out['episodes']['outcomes']}; "
        f"{len(topped_eps)} TOPPED and E1-eligible")

    # ── case / control assembly (§4.5) ───────────────────────────────────────
    gates = _gate_context(close, dvol)
    e1_eps = set(episodes.loc[~episodes["micro"], "episode_id"])
    dtp_e1 = dtp[dtp["episode_id"].isin(e1_eps)]
    topped_ids = set(topped_eps["episode_id"])

    cases = dtp_e1[dtp_e1["episode_id"].isin(topped_ids)
                   & dtp_e1["days_to_peak"].isin(ta.CASE_OFFSETS)].copy()
    cases["offset"] = cases["days_to_peak"]
    cases["case_id"] = (cases["episode_id"] + "@" + cases["offset"].astype(str))
    out["cases"] = {
        "n_cases": int(len(cases)),
        "per_offset": {int(k): int(v) for k, v in
                       cases["offset"].value_counts().to_dict().items()},
        "n_case_episodes": int(cases["episode_id"].nunique()),
    }

    race_e1 = race.merge(dtp_e1[["segment", "date", "episode_id"]], on=["segment", "date"],
                         how="inner")
    pool = race_e1[race_e1["label"] == "CONTINUED"][["segment", "ticker", "date"]].copy()
    pool["case_id"] = ["p%d" % i for i in range(len(pool))]
    out["cases"]["n_control_candidates"] = int(len(pool))

    cases = _pick(gates, cases).dropna(subset=["r126", "rv63", "dvol21"])
    pool = _pick(gates, pool).dropna(subset=["r126", "rv63", "dvol21"])
    say(f"[{track}] {len(cases)} cases vs {len(pool)} CONTINUED control candidates")

    pairs, diag = ta.matched_controls(cases, pool)
    out["matching"] = diag
    say(f"[{track}] matched {diag['n_matched']}/{diag['n_cases']} cases "
        f"({diag['n_pairs']} pairs, {diag['n_dropped_no_control']} dropped)")

    # ── the days features are actually needed on ─────────────────────────────
    ext_long = race[["segment", "ticker", "date"]].copy()
    sample = ext_long.iloc[::SAMPLE_EVERY].copy()
    e3_days = dtp[dtp["episode_id"].isin(topped_ids)][["segment", "ticker", "date"]]
    e2_days = _pick(gates, _e2_case_days(dtp_e1, topped_ids)) \
        .dropna(subset=["r126", "rv63", "dvol21"])
    ctrl_days = (pairs[["control_segment", "control_ticker", "control_date"]]
                 .set_axis(["segment", "ticker", "date"], axis=1)
                 if not pairs.empty else
                 pd.DataFrame(columns=["segment", "ticker", "date"]))
    need = pd.concat([
        cases[["segment", "ticker", "date"]], ctrl_days,
        sample[["segment", "ticker", "date"]], e3_days,
        e2_days[["segment", "ticker", "date"]],
    ], ignore_index=True).drop_duplicates(["segment", "date"])
    say(f"[{track}] features on {len(need)} (segment, day) points "
        f"({len(sample)} from the 1-in-{SAMPLE_EVERY} EXT sample)")

    bars = _segment_bars(panel, sorted(set(need["segment"])))
    feats = ta.feature_library(bars, eqw, need[["segment", "date"]], episodes=episodes)
    out["feature_coverage"] = {
        f: float(feats[f].notna().mean()) for f in ta.FEATURES if f in feats.columns}
    out["feature_coverage_floor"] = COVERAGE_FLOOR
    out["features_below_coverage_floor"] = sorted(
        f for f, c in out["feature_coverage"].items() if c < COVERAGE_FLOOR)

    # ── E1 (EPISODE-FIRST, §4.5) ─────────────────────────────────────────────
    say(f"[{track}] E1 matched deltas -> episode-first aggregation -> "
        f"episode-peak-month bootstrap (B={ta.BOOTSTRAP_B})")
    case_deltas = ta.matched_deltas(pairs, feats)
    ep_deltas = ta.episode_deltas(case_deltas, cases, episodes)
    e1 = ta.matched_delta_stats(ep_deltas, b=ta.BOOTSTRAP_B if not quick else 400,
                                seed=seed, coverage_floor=COVERAGE_FLOOR)
    n_months = (int(pd.to_datetime(ep_deltas["peak_date"]).dt.to_period("M").nunique())
                if not ep_deltas.empty else 0)
    out["e1"] = {
        "aggregation": "episode-first (median over the episode's {21,10,5} snapshots)",
        "n_case_sets": int(len(case_deltas)),
        "n_episodes": int(len(ep_deltas)),
        "n_distinct_peak_months": n_months,
        "min_peak_months_required": ta.MIN_EPISODE_MONTHS,
        "min_finite_controls": ta.MIN_FINITE_CONTROLS,
        "snapshots_per_episode": _describe(ep_deltas["n_snapshots"])
        if not ep_deltas.empty else _describe([]),
        "table": _records(e1),
        "n_separating": int(e1["separates"].sum()) if not e1.empty else 0,
        "separating": sorted(e1.loc[e1["separates"], "feature"]) if not e1.empty else [],
        "registered_separating": sorted(e1.loc[e1["grade"] == "REGISTERED", "feature"])
        if not e1.empty else [],
        "exploratory_separating": sorted(
            e1.loc[e1["grade"] == "EXPLORATORY-DISCOVERY", "feature"]) if not e1.empty else [],
        "by_family": ({fam: {"n_tested": int(len(g)), "n_separating": int(g["separates"].sum())}
                       for fam, g in e1.groupby("family")} if not e1.empty else {}),
    }
    say(f"[{track}] E1: {out['e1']['n_separating']} of {len(ta.FEATURES)} separate "
        f"(N = {len(ep_deltas)} episodes / {len(case_deltas)} case-sets, "
        f"{n_months} peak-months vs the {ta.MIN_EPISODE_MONTHS} required)")

    # ── E1b ──────────────────────────────────────────────────────────────────
    say(f"[{track}] E1b pooled AUC increment")
    out["e1b"] = _e1b(feats, race, episodes, sample, close.index, seed=seed, quick=quick)

    # ── E2 / E3 / E4 ─────────────────────────────────────────────────────────
    survivors = out["e1"]["separating"]
    # §2/§4.8: the control tail is DIRECTION-ALIGNED; an exploratory field has no
    # declared risk side, so its OBSERVED sign picks the tail (discovery-only).
    obs = ({r["feature"]: r["median_delta"] for r in out["e1"]["table"]}
           if out["e1"]["table"] else {})
    grades = ({r["feature"]: r.get("grade", "") for r in out["e1"]["table"]}
              if out["e1"]["table"] else {})
    say(f"[{track}] E2 lead-time profiles on {len(survivors)} survivor(s)")
    out["e2"] = _e2(e2_days, pool, feats, survivors, episodes, grades,
                    seed=seed, quick=quick)
    say(f"[{track}] E3 ordering")
    out["e3"] = _e3(feats, dtp, topped_ids, pool, survivors, obs)
    say(f"[{track}] E4 era / dollar-volume stability")
    out["e4"] = _e4(ep_deltas, gates, cases, survivors,
                    W_ERAS if track == "W" else D_ERAS, seed=seed, quick=quick)

    # ── the ruler (§2) ───────────────────────────────────────────────────────
    say(f"[{track}] top ruler on survivor legs")
    out["ruler"] = _ruler(feats, ext, episodes, close, pool, survivors, obs)

    # ── G0.2 + today's tape ──────────────────────────────────────────────────
    out["g0_2_delisting"] = _delisting_check(close, episodes)
    out["today_tape"] = _today_tape(close, ext, feats, bars, eqw, episodes, gates)
    out["episodes_table_sample"] = _records(
        episodes.sort_values("n_ext_days", ascending=False).head(25)
        [["episode_id", "ticker", "start", "end", "n_ext_days", "peak_date",
          "peak_close", "outcome", "peak_window_censored"]])
    return out


def _records(df: pd.DataFrame) -> list[dict]:
    """JSON-safe records (timestamps to ISO dates, numpy scalars to python)."""
    if df is None or df.empty:
        return []
    d = df.copy()
    for c in d.columns:
        if pd.api.types.is_datetime64_any_dtype(d[c]):
            d[c] = d[c].dt.strftime("%Y-%m-%d")
    return json.loads(d.to_json(orient="records"))


def _e2_case_days(dtp_e1: pd.DataFrame, topped_ids: set) -> pd.DataFrame:
    """The E2 lead-time case set: up to 2 EXT days per (TOPPED episode, bucket).

    §4.5's three registered offsets populate only two of §4.8's four buckets, so the
    lead-time PROFILE (a descriptive read, no new test) needs days sampled across
    all four. Sampling is deterministic — the earliest days in each bucket.
    """
    d = dtp_e1[dtp_e1["episode_id"].isin(topped_ids)].copy()
    if d.empty:
        return d.assign(bucket=None, case_id=None)
    # §4.8 windows are stated POSITIVE-BEFORE-PEAK, so the bucket variable IS
    # days_to_peak (= peak_date − d): +22..+63 EARLY through 0..−5 POST-TOP.
    lab = []
    for lo, hi in E2_BUCKETS:
        g = d[(d["days_to_peak"] >= lo) & (d["days_to_peak"] <= hi)].copy()
        g["bucket"] = _bucket_tag(lo, hi)
        lab.append(g.sort_values("days_to_peak", ascending=False)
                   .groupby("episode_id", as_index=False).head(2))
    out = pd.concat(lab, ignore_index=True) if lab else d.head(0)
    out["case_id"] = (out["episode_id"] + "@" + out["bucket"] + "@"
                      + out["days_to_peak"].astype(str))
    return out


def _bucket_tag(lo: int, hi: int) -> str:
    """`+22..+63` style tag — days BEFORE the peak read positive (§4.8, entry (a))."""
    return f"{hi:+d}..{lo:+d}" if lo > 0 else f"{hi:+d}..{lo:+d}"


def _episode_block_ci(y: np.ndarray, p: np.ndarray, blocks: np.ndarray, auc_fn,
                      *, b: int, seed: int, paired: np.ndarray | None = None) -> dict:
    """95% percentile CI for an AUC (and, when `paired` is given, for the ΔAUC).

    Resamples EPISODE blocks with replacement: EXT days inside one episode are the
    same event looked at repeatedly, so a row-level interval would be a fiction. The
    ΔAUC uses the SAME draws as the two AUCs, which is what makes it a paired
    interval rather than two independent ones subtracted.
    """
    rng = np.random.default_rng(seed)
    keys, inv = np.unique(blocks, return_inverse=True)
    members = [np.flatnonzero(inv == i) for i in range(len(keys))]
    k = len(members)
    if k < 5:
        return {"ci_lo": None, "ci_hi": None, "n_blocks": int(k),
                "reason": "fewer than 5 episode blocks"}
    a_draws, d_draws = [], []
    for _ in range(b):
        idx = np.concatenate([members[j] for j in rng.integers(0, k, k)])
        if len(np.unique(y[idx])) < 2:
            continue
        a_draws.append(auc_fn(y[idx], p[idx]))
        if paired is not None:
            d_draws.append(a_draws[-1] - auc_fn(y[idx], paired[idx]))
    if len(a_draws) < 50:
        return {"ci_lo": None, "ci_hi": None, "n_blocks": int(k),
                "reason": "too few two-class resamples"}
    lo, hi = np.percentile(a_draws, [2.5, 97.5])
    out = {"ci_lo": float(lo), "ci_hi": float(hi), "n_blocks": int(k)}
    if d_draws:
        dlo, dhi = np.percentile(d_draws, [2.5, 97.5])
        out["delta_ci_lo"], out["delta_ci_hi"] = float(dlo), float(dhi)
    return out


def _e1b(feats: pd.DataFrame, race: pd.DataFrame, episodes: pd.DataFrame,
        sample: pd.DataFrame, calendar: pd.DatetimeIndex, *, seed: int,
        quick: bool = False) -> dict:
    """§4.7 pooled increment: NESTED M0 ⊂ M1 ⊂ M2, two CV schemes, episode-block CIs.

    M0 = r126 alone. M1 = M0 + the rv63 realized-volatility nuisance control.
    M2 = M1 + the other 35 frozen features (r126 appears once). The models are
    NESTED on purpose: the question is what the library adds over extension AND
    volatility, so M1 is the baseline that must be beaten, not M0.

    Leakage discipline (§4.7): every fold fits its median-imputer and its
    standardization on TRAINING ROWS ONLY — they live inside the sklearn Pipeline,
    so a test row can never contribute to its own scaling. No missingness
    indicators, no full-sample preprocessing, and rows are IMPUTED rather than
    dropped (dropping every incomplete row is itself a full-sample decision, and it
    silently deletes the thin-coverage names the study cares about).

    CV-A: 5-fold grouped by RAW TICKER, so every identity segment of a reused ticker
    stays on one side. CV-B: expanding walk-forward by calendar quarter with a
    250-SESSION purge between train end and test start — the full race-label
    horizon, because a training row's label can be resolved by bars up to 250
    sessions later and anything shorter trains on the test window's own outcome.

    Descriptive: E1b creates no registered test. AUCs and the paired ΔAUC carry
    episode-block bootstrap CIs.
    """
    try:
        from sklearn.impute import SimpleImputer
        from sklearn.linear_model import LogisticRegression
        from sklearn.metrics import roc_auc_score
        from sklearn.model_selection import GroupKFold
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler
    except Exception as exc:  # noqa: BLE001
        return {"error": f"scikit-learn unavailable: {exc}"}

    lab = race[race["label"].isin(("TOPPED", "CONTINUED"))][
        ["segment", "ticker", "date", "label"]]
    d = sample[["segment", "date"]].merge(lab, on=["segment", "date"], how="inner")
    d = d.merge(feats, on=["segment", "date"], how="left", suffixes=("", "_f"))
    d["y"] = (d["label"] == "TOPPED").astype(int)
    if d.empty or d["y"].nunique() < 2:
        return {"error": "no two-class EXT-day sample", "n": int(len(d))}

    # rv63 is the §4.7 nuisance control; the library carries rv21 and rv21/rv63, so
    # it is reconstructed exactly rather than re-derived from bars on a second path.
    d["N1_rv63"] = d["C1_rv21"] / d["C2_rv21_over_rv63"].replace(0.0, np.nan)
    m0 = ["A3_r126"]
    m1 = [*m0, "N1_rv63"]
    m2 = [*m1, *[f for f in ta.FEATURES if f not in m1]]
    models = {"M0": m0, "M1": m1, "M2": m2}

    # Episode membership: the block key for every bootstrap and the episode-AUC join.
    ep = episodes[["segment", "start", "end", "episode_id", "outcome"]]
    j = d[["segment", "date"]].reset_index().merge(ep, on="segment", how="left")
    j = j[(j["date"] >= j["start"]) & (j["date"] <= j["end"])]
    d["episode_id"] = pd.Series(j.set_index("index")["episode_id"]).reindex(d.index)
    d["episode_id"] = d["episode_id"].fillna("_" + d["segment"].astype(str))

    b_boot = 300 if quick else 1000
    out: dict = {"n_rows": int(len(d)), "base_rate_topped": float(d["y"].mean()),
                 "n_names": int(d["ticker"].nunique()),
                 "n_episodes_in_sample": int(d["episode_id"].nunique()),
                 "nested": "M0 (r126) subset M1 (+rv63) subset M2 (+the other 35)",
                 "preprocessing": "median-impute + standardize, fit on TRAIN folds only",
                 "embargo_sessions": ta.E1B_EMBARGO_SESSIONS, "models": {}}

    y_all = d["y"].to_numpy()
    dates = pd.to_datetime(d["date"]).to_numpy()
    probs: dict[str, dict[str, np.ndarray]] = {}

    def oof(cols: list[str], scheme: str) -> np.ndarray | str:
        """Out-of-fold probabilities, or a string reason why there are none."""
        x = d[cols].to_numpy(dtype=float)
        if len(y_all) < 200:
            return "too thin"
        prob = np.full(len(y_all), np.nan)
        pipe = make_pipeline(
            SimpleImputer(strategy="median", keep_empty_features=True),
            StandardScaler(),
            LogisticRegression(C=1.0, max_iter=2000, random_state=seed))
        if scheme == "grouped":
            g = d["ticker"].to_numpy()
            n_split = min(5, len(np.unique(g)))
            if n_split < 2:
                return "one group"
            for tr, te in GroupKFold(n_splits=n_split).split(x, y_all, groups=g):
                if len(np.unique(y_all[tr])) < 2:
                    continue
                prob[te] = pipe.fit(x[tr], y_all[tr]).predict_proba(x[te])[:, 1]
        else:
            q = pd.PeriodIndex(pd.to_datetime(d["date"]), freq="Q")
            uq = sorted(q.unique())
            for i in range(4, len(uq)):
                te = np.flatnonzero(q == uq[i])
                # 250-SESSION label purge on the panel's own trading calendar: a
                # training row's race label can need 250 forward sessions to resolve,
                # so anything shorter trains on the test window's own outcome.
                pos = int(calendar.searchsorted(uq[i].start_time))
                cut = calendar[max(0, pos - ta.E1B_EMBARGO_SESSIONS)]
                tr = np.flatnonzero(dates < np.datetime64(cut))
                if len(tr) < 200 or len(te) == 0 or len(np.unique(y_all[tr])) < 2:
                    continue
                prob[te] = pipe.fit(x[tr], y_all[tr]).predict_proba(x[te])[:, 1]
        return prob

    for name, cols in models.items():
        cols = [c for c in cols if c in d.columns]
        entry: dict = {"features": cols, "n_features": len(cols)}
        probs[name] = {}
        for scheme in ("grouped", "walk_forward"):
            p = oof(cols, scheme)
            if isinstance(p, str):
                entry[scheme] = {"auc": None, "reason": p}
                continue
            m = np.isfinite(p)
            if m.sum() < 100 or len(np.unique(y_all[m])) < 2:
                entry[scheme] = {"auc": None, "n": int(m.sum()), "reason": "no scored fold"}
                continue
            probs[name][scheme] = p
            res = {"auc": float(roc_auc_score(y_all[m], p[m])), "n": int(m.sum())}
            res.update(_episode_block_ci(y_all[m], p[m],
                                         d["episode_id"].to_numpy()[m], roc_auc_score,
                                         b=b_boot, seed=seed))
            scored = d[m].copy()
            scored["p"] = p[m]
            agg = scored[scored["episode_id"].isin(set(ep["episode_id"]))] \
                .groupby("episode_id").agg(p=("p", "max"))
            agg = agg.join(ep.set_index("episode_id")["outcome"], how="inner")
            if not agg.empty and (agg["outcome"] == "TOPPED").nunique() == 2:
                res["episode_auc"] = float(
                    roc_auc_score((agg["outcome"] == "TOPPED").astype(int), agg["p"]))
                res["n_episodes"] = int(len(agg))
            entry[scheme] = res
        out["models"][name] = entry

    for scheme in ("grouped", "walk_forward"):
        a2 = out["models"]["M2"][scheme].get("auc")
        a1 = out["models"]["M1"][scheme].get("auc")
        out[f"increment_{scheme}"] = (a2 - a1) if (a2 is not None and a1 is not None) else None
        p2, p1 = probs["M2"].get(scheme), probs["M1"].get(scheme)
        if p2 is not None and p1 is not None:
            m = np.isfinite(p2) & np.isfinite(p1)
            if m.sum() >= 100:
                ci = _episode_block_ci(y_all[m], p2[m], d["episode_id"].to_numpy()[m],
                                       roc_auc_score, b=b_boot, seed=seed + 1,
                                       paired=p1[m])
                out[f"increment_{scheme}_ci"] = [ci.get("delta_ci_lo"),
                                                 ci.get("delta_ci_hi")]
    incs = [out.get("increment_grouped"), out.get("increment_walk_forward")]
    out["sign_consistent"] = (all(i is not None for i in incs)
                              and (incs[0] > 0) == (incs[1] > 0))
    return out


def _e2(e2_days: pd.DataFrame, pool: pd.DataFrame, feats: pd.DataFrame,
        survivors: list[str], episodes: pd.DataFrame, grades: dict, *,
        seed: int, quick: bool) -> dict:
    """§4.8 lead-time profile: matched Δ per positive-before-peak window, with the label.

    Windows are stated POSITIVE-BEFORE-PEAK: EARLY +22..+63, MID +6..+21, LATE
    +1..+5, POST-TOP CONFIRMATION 0..−5. A survivor takes the EARLIEST pre-peak
    window whose episode-block CI excludes 0; a survivor that separates only in the
    last window is POST-TOP CONFIRMATION and may never be described as detection
    (G0.4). An exploratory field keeps an `EXPLORATORY ` prefix and cannot reach
    DETECTION grade whatever its lead time.
    """
    if not survivors or e2_days.empty or pool.empty:
        return {"labels": {}, "buckets": {}, "note": "no E1 survivors to profile",
                "convention": "positive = sessions BEFORE the peak"}
    res: dict = {"buckets": {}, "labels": {},
                 "convention": "positive = sessions BEFORE the peak"}
    for lo, hi in E2_BUCKETS:
        tag = _bucket_tag(lo, hi)
        sub = e2_days[e2_days["bucket"] == tag]
        if sub.empty:
            res["buckets"][tag] = {"n_cases": 0, "n_episodes": 0, "table": []}
            continue
        pairs, diag = ta.matched_controls(sub, pool)
        # episode-first here too: a window contributes one row per episode.
        ep_d = ta.episode_deltas(ta.matched_deltas(pairs, feats), sub, episodes)
        stats = ta.matched_delta_stats(ep_d, survivors,
                                       b=500 if quick else ta.BOOTSTRAP_B, seed=seed,
                                       coverage_floor=COVERAGE_FLOOR)
        res["buckets"][tag] = {
            "window": E2_LABELS[(lo, hi)], "n_cases": int(diag["n_matched"]),
            "n_episodes": int(len(ep_d)),
            "n_episodes_available": int(sub["episode_id"].nunique()),
            "table": _records(stats),
        }
    for f in survivors:
        label = "NO PRE-PEAK SEPARATION"
        for lo, hi in E2_BUCKETS:
            t = res["buckets"].get(_bucket_tag(lo, hi), {}).get("table", [])
            row = next((r for r in t if r["feature"] == f), None)
            if row and row.get("separates"):
                label = E2_LABELS[(lo, hi)]
                break
        if grades.get(f) == "EXPLORATORY-DISCOVERY":
            label = f"EXPLORATORY {label}"
        res["labels"][f] = label
    return res


def _tail_for(feat: str, observed: dict) -> tuple[int, float]:
    """(direction, control-tail quantile) for a survivor leg — §2's direction-aligned tail."""
    direction = ta.FEATURE_DIRECTION.get(feat, 0)
    return direction, ta.direction_tail(direction, float(observed.get(feat, np.nan)))


def _e3(feats: pd.DataFrame, dtp: pd.DataFrame, topped_ids: set, pool: pd.DataFrame,
        survivors: list[str], observed: dict) -> dict:
    """§4.8 E3 — descriptive first-crossing ORDER at direction-aligned control tails."""
    if not survivors:
        return {"note": "no E1 survivors to order", "order": []}
    ctrl = _pick(feats, pool[["segment", "date"]])
    rows = []
    d = dtp[dtp["episode_id"].isin(topped_ids)][["segment", "date", "episode_id",
                                                 "days_to_peak"]]
    f = d.merge(feats, on=["segment", "date"], how="left")
    for feat in survivors:
        if feat not in ctrl.columns or ctrl[feat].notna().sum() < 50:
            continue
        direction, tail = _tail_for(feat, observed)
        thr = float(ctrl[feat].quantile(tail))
        cross = f[f[feat] >= thr] if tail >= 0.5 else f[f[feat] <= thr]
        if cross.empty:
            continue
        first = cross.sort_values("days_to_peak", ascending=False) \
            .groupby("episode_id", as_index=False).first()
        rows.append({
            "feature": feat, "direction": direction, "control_tail": tail,
            "threshold": thr,
            "n_episodes_crossing": int(len(first)),
            "median_days_to_peak_at_first_cross": float(first["days_to_peak"].median()),
            "p25": float(first["days_to_peak"].quantile(0.25)),
            "p75": float(first["days_to_peak"].quantile(0.75)),
        })
    rows.sort(key=lambda r: -r["median_days_to_peak_at_first_cross"])
    return {"order": rows, "convention": "positive = sessions BEFORE the peak"}


def _e4(ep_deltas: pd.DataFrame, gates: pd.DataFrame, cases: pd.DataFrame,
        survivors: list[str], eras, *, seed: int, quick: bool) -> dict:
    """§4.9 descriptive sign stability of survivors across eras and dollar-volume terciles.

    Stratifies the EPISODE-level deltas (§4.5 aggregation), keyed on the episode's
    peak date, so an era cell counts episodes rather than snapshots.
    """
    if not survivors or ep_deltas.empty:
        return {"eras": {}, "dvol_terciles": {}, "note": "no E1 survivors to stratify"}
    d = ep_deltas.copy()
    d["peak_date"] = pd.to_datetime(d["peak_date"])
    dv = (cases[["episode_id", "dvol21"]].groupby("episode_id", as_index=False).median()
          if "dvol21" in cases.columns else pd.DataFrame(columns=["episode_id", "dvol21"]))
    d = d.merge(dv, on="episode_id", how="left")
    b = 400 if quick else 1000
    res: dict = {"eras": {}, "dvol_terciles": {}, "unit": "distinct episodes"}
    for name, lo, hi in eras:
        sub = d[(d["peak_date"] >= pd.Timestamp(lo)) & (d["peak_date"] <= pd.Timestamp(hi))]
        res["eras"][name] = {
            "n_episodes": int(len(sub)),
            "table": _records(ta.matched_delta_stats(sub, survivors, b=b, seed=seed,
                                                     coverage_floor=COVERAGE_FLOOR))
            if len(sub) >= 20 else [],
        }
    if "dvol21" in d.columns and d["dvol21"].notna().sum() >= 30:
        try:
            d["_terc"] = pd.qcut(d["dvol21"].rank(method="first"), 3,
                                 labels=["low", "mid", "high"])
        except ValueError:
            d["_terc"] = "all"
        for terc, sub in d.groupby("_terc", observed=True):
            res["dvol_terciles"][str(terc)] = {
                "n_episodes": int(len(sub)),
                "table": _records(ta.matched_delta_stats(sub, survivors, b=b, seed=seed,
                                                         coverage_floor=COVERAGE_FLOOR))
                if len(sub) >= 20 else [],
            }
    return res


def _ruler(feats: pd.DataFrame, ext: pd.DataFrame, episodes: pd.DataFrame,
           close: pd.DataFrame, pool: pd.DataFrame, survivors: list[str],
           observed: dict) -> dict:
    """§2 wrong-ruler check per survivor leg, at the DIRECTION-ALIGNED control tail."""
    if not survivors:
        return {"note": "no E1 survivors to rule", "legs": {}}
    ctrl = _pick(feats, pool[["segment", "date"]])
    # The all-EXT-days null is the same for every leg, and it is the expensive pass
    # (it walks every EXT day in the tape) — compute it ONCE.
    null = ta.top_ruler(ext, episodes, close)
    legs = {}
    for feat in survivors:
        if feat not in ctrl.columns or ctrl[feat].notna().sum() < 50:
            continue
        direction, tail = _tail_for(feat, observed)
        thr = float(ctrl[feat].quantile(tail))
        f = feats[["segment", "date", feat]].dropna()
        f = f[f[feat] >= thr] if tail >= 0.5 else f[f[feat] <= thr]
        fires = pd.DataFrame(False, index=ext.index, columns=ext.columns)
        for seg, g in f.groupby("segment"):
            if seg in fires.columns:
                fires.loc[fires.index.isin(g["date"]), seg] = True
        r = ta.top_ruler(fires & ext, episodes, close)
        fh, fn = r.get("fwd_63_fires"), null.get("fwd_63_fires")
        r["fwd_63_all_ext_null"] = fn
        r["fwd_63_excess"] = (fh - fn) if (fh is not None and fn is not None
                                          and np.isfinite(fh) and np.isfinite(fn)) else None
        r["null_median_remaining_upside"] = null.get("median_remaining_upside")
        legs[feat] = {"direction": direction, "control_tail": tail,
                      "threshold": thr, **r}
    return {"legs": legs, "all_ext_null": null}


def _delisting_check(close: pd.DataFrame, episodes: pd.DataFrame) -> dict:
    """G0.2 — NAME the dead tickers in the tape instead of assuming they are there."""
    if close.empty:
        return {"n_candidates": 0, "named": []}
    last_day = close.index.max()
    cutoff_pos = max(0, len(close.index) - 61)
    cutoff = close.index[cutoff_pos]
    lasts = close.apply(lambda s: s.last_valid_index())
    dead = lasts[lasts.notna() & (lasts < cutoff)]
    in_ep = set(episodes["segment"]) if not episodes.empty else set()
    named = [{"segment": s, "ticker": ta.segment_ticker(s), "last_bar": str(pd.Timestamp(v).date())}
             for s, v in dead.items() if s in in_ep]
    named.sort(key=lambda r: r["last_bar"])
    known = [r for r in named
             if r["ticker"] in {"BBBY", "SIVB", "SBNY", "FRC", "AMTD", "TWTR", "ATVI",
                                "VMW", "SGEN", "HZNP", "PXD", "SPWR", "WEWKQ", "WE",
                                "MULN", "RIDE", "NKLA", "PTRA", "VLTA", "ROVR"}]
    return {
        "last_data_day": str(last_day.date()),
        "cutoff_last_bar_before": str(pd.Timestamp(cutoff).date()),
        "n_dead_segments": int(len(dead)),
        "n_dead_with_an_episode": len(named),
        "named": named[:40],
        "known_delistings_found": known,
        "gate_g0_2_satisfied": len(named) >= 3,
    }


def _today_tape(close: pd.DataFrame, ext: pd.DataFrame, feats: pd.DataFrame,
                bars: dict, eqw: pd.Series, episodes: pd.DataFrame,
                gates: pd.DataFrame) -> dict:
    """G0.5 — the CURRENT extended cohort with its feature readout (display-tier)."""
    if close.empty or ext.empty:
        return {"asof": None, "rows": []}
    asof = close.index.max()
    row = ext.loc[asof]
    live = list(row.index[row.fillna(False).to_numpy(dtype=bool)])
    if not live:
        return {"asof": str(asof.date()), "n_extended_today": 0, "rows": [],
                "note": "nothing extended on the last session — an honest null"}
    need = pd.DataFrame({"segment": live, "date": asof})
    have = feats.merge(need, on=["segment", "date"], how="right")
    missing = sorted(set(need["segment"]) - set(feats.loc[feats["date"] == asof, "segment"]))
    if missing:
        extra_bars = {s: b for s, b in bars.items() if s in missing}
        if len(extra_bars) < len(missing):
            extra_bars.update({s: pd.DataFrame({"close": close[s].dropna()})
                               for s in missing if s not in extra_bars})
        extra = ta.feature_library(extra_bars, eqw, {s: [asof] for s in missing},
                                   episodes=episodes)
        have = pd.concat([have.dropna(subset=["A3_r126"]), extra], ignore_index=True)
    g = gates[gates["date"] == asof][["segment", "r126", "rv63", "dvol21"]]
    have = have.merge(g, on="segment", how="left")
    have = have.sort_values("r126", ascending=False).head(TODAY_TAPE_CAP)
    keep = ["segment", "ticker", "date", "r126", "rv63", "dvol21",
            "A5_ext_ma50_atr21", "A6_ext_ma200_atr21", "A7_late_gain_share",
            "B1_accel_r21", "C2_rv21_over_rv63", "C3_semivol_ratio63",
            "D3_updown_dvol_ratio21", "D6_churn21", "E3f_rs_peak_lag",
            "E4f_price_rs_gap", "E5f_rs_decel", "F1_episode_age",
            "F2_drawdown_in_episode", "F3_days_since_63d_high"]
    keep = [c for c in keep if c in have.columns]
    return {"asof": str(asof.date()), "n_extended_today": len(live),
            "n_rows": int(len(have)), "capped_at": TODAY_TAPE_CAP,
            "rows": _records(have[keep])}


# ══════════════════════════════════════════════════════════════════════════════
# report
# ══════════════════════════════════════════════════════════════════════════════
def _fmt(x, nd: int = 4) -> str:
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "null"
    if isinstance(x, (int, np.integer)):
        return f"{int(x):,}"
    if isinstance(x, (float, np.floating)):
        return f"{float(x):.{nd}f}"
    return str(x)


def _e1_table(rows: list[dict]) -> list[str]:
    out = ["| feature | family | dir | episodes | peak-months | cov | median Δ "
           "| 95% CI (peak-month block) | q | grade |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        d = {1: "higher⇒TOPPED", -1: "lower⇒TOPPED", 0: "exploratory"}[r["direction"]]
        ci = f"[{_fmt(r['ci_lo'])}, {_fmt(r['ci_hi'])}]"
        grade = r.get("grade") or ("no" if not r.get("separates") else "**YES**")
        out.append(f"| `{r['feature']}` | {r['family']} | {d} | "
                   f"{_fmt(r.get('n_episodes'))} | {_fmt(r.get('n_blocks'))} | "
                   f"{_fmt(r['coverage'], 2)} | {_fmt(r['median_delta'])} | {ci} | "
                   f"{_fmt(r['q_value'], 3)} | {grade} |")
    return out


def write_report(path: Path, summary: dict) -> None:
    """The house phase-0 report: verdict first, nulls printed, honest N everywhere."""
    w = summary["tracks"].get("W", {})
    d = summary["tracks"].get("D", {})
    e1 = w.get("e1", {})
    n_sep = e1.get("n_separating", 0)
    eps = w.get("episodes", {})
    L: list[str] = []
    A = L.append

    if not e1:
        verdict = "NO REGISTRATION TRACK RESULT — the W pipeline produced no matched set"
    elif n_sep == 0:
        verdict = ("ZERO of 36 features separate TOPPED from CONTINUED extended days "
                   "on the registration track")
    else:
        labels = w.get("e2", {}).get("labels", {})
        pre = [f for f, lab in labels.items() if lab in ("EARLY", "MID", "LATE")]
        verdict = (f"{n_sep} of 36 features separate; "
                   f"{len(pre)} carry a PRE-PEAK lead-time label"
                   if pre else
                   f"{n_sep} of 36 features separate — all POST-TOP CONFIRMATION, "
                   "no detection claim")

    A("# TOP ANATOMY Phase-0 — extended-move anatomy: topped vs continued")
    A("")
    A(f"**Verdict: {verdict}.** *(prose pass pending — numbers below are the run's own.)*")
    A("")
    A(f"- **Date:** {summary['run_date']} · **Family:** `{FAMILY}`")
    A(f"- **Prereg:** `research/top_anatomy/TOPA_PHASE0_PREREG.md` (frozen "
      f"{summary['prereg_frozen']}, before any result) · **Masterplan:** "
      "`research/TOP_ANATOMY_MASTERPLAN_BY_FABLE.md`")
    A(f"- **Reproduce:** `{summary['reproduce']}`")
    A(f"- **Vintage:** git `{summary['git_sha']}` · track W data through "
      f"**{w.get('panel', {}).get('last_session')}** · track D through "
      f"**{d.get('panel', {}).get('last_session')}**")
    A("- **Tier:** research / display, zero scored authority. AVOID-not-SHORT: nothing "
      "here is a directional bear position, a rank, a size, or an exit rule. A TOPPED "
      "label is a statement about the declared race (−20% from the post-entry running "
      "peak before +15% from entry, inside 250 sessions) — never that a move \"is over\".")
    A("")
    A("---")
    A("")

    A("## 1. The tape")
    A("")
    A("| | track W (registration) | track D (era context, TILTED) |")
    A("|---|---|---|")
    for lab, key, sub in (("segments (identity-split names)", "panel", "n_segments"),
                          ("sessions", "panel", "n_sessions"),
                          ("first session", "panel", "first_session"),
                          ("last session", "panel", "last_session"),
                          ("tickers split on a >60-session gap", "panel", "n_tickers_split"),
                          ("EXT days", "ext", "n_ext_days"),
                          ("segments with ≥1 EXT day", "ext", "n_segments_with_ext")):
        A(f"| {lab} | {_fmt(w.get(key, {}).get(sub))} | {_fmt(d.get(key, {}).get(sub))} |")
    for lab, sub in (("episodes", "n_episodes"),
                     ("…micro (<5 EXT days, excluded from E1)", "n_micro_under_5_ext_days"),
                     ("…E1-eligible", "n_e1_eligible"), ("distinct names", "n_names"),
                     ("TOPPED episodes (E1-eligible)", "n_topped_e1_eligible"),
                     ("peak-window censored", "n_peak_window_censored")):
        A(f"| {lab} | {_fmt(w.get('episodes', {}).get(sub))} | "
          f"{_fmt(d.get('episodes', {}).get(sub))} |")
    A("")
    A("Extension sensitivity arms (report-only, no registration claim rides on them): "
      f"primary `r126≥+0.50` = {_fmt(w.get('ext_variants', {}).get('primary'))} EXT days; "
      f"`r63≥+0.35` = {_fmt(w.get('ext_variants', {}).get('r63'))}; "
      f"`(c−MA200)/ATR63≥6` = {_fmt(w.get('ext_variants', {}).get('atrz'))}.")
    A("")

    A("## 1b. Instrument / dead-name census (§3) and the §3 parity gate")
    A("")
    A("Counted from the panel, never inferred from a file count.")
    A("")
    A("| | track W | track D |")
    A("|---|---|---|")
    for lab, key in (("files scanned", "n_files_scanned"),
                     ("tickers kept", "n_tickers_kept"),
                     ("identity segments", "n_segments"),
                     ("segments ever ELIGIBLE", "n_segments_ever_eligible"),
                     ("segments with ≥1 EXT day", "n_segments_with_ext"),
                     ("segments CANDIDATE-DEAD (last bar >60 sessions back)",
                      "n_segments_candidate_dead"),
                     ("…of those, held ≥1 EXT day", "n_candidate_dead_with_ext_day")):
        A(f"| {lab} | {_fmt(w.get('census', {}).get(key))} | "
          f"{_fmt(d.get('census', {}).get(key))} |")
    A("")
    pg = (w.get("prefix_parity_gate") or d.get("prefix_parity_gate") or {})
    pg_track = "W" if w.get("prefix_parity_gate") else "D"
    A(f"**§3 full-series-vs-prefix parity gate: PASSED** on "
      f"{_fmt(pg.get('n_names_checked'))} sampled track-{pg_track} name(s) "
      f"(worst |gap| {_fmt(pg.get('worst_abs_gap'), 12)}, tolerance "
      f"{_fmt(pg.get('tolerance'), 12)}). Features at d are recomputed from the "
      "series truncated just after d, through the same repair path — so a split "
      "discovered later cannot move a value the study already read. The gate runs "
      "before any label is computed and hard-fails the run; the synthetic twin lives "
      "in `tests/test_top_anatomy.py`.")
    A("")
    A("Split-factor step days are INELIGIBLE, and the §3 price/liquidity floors are "
      "evaluated on the **raw as-printed** close and close×volume — an adjusted-price "
      "floor would evict 2022 days on a 2025 split. The recovered factor divides "
      "open/high/low/close and multiplies volume, so repaired dollar volume is "
      "invariant across the repair.")
    A("")
    A("## 2. Race labels (§4.3) — the outcome, with its nulls printed")
    A("")
    A("| label | track W | track D |")
    A("|---|---|---|")
    for lab in ("TOPPED", "CONTINUED", "CENSORED"):
        A(f"| {lab} | {_fmt(w.get('race', {}).get('counts', {}).get(lab, 0))} | "
          f"{_fmt(d.get('race', {}).get('counts', {}).get(lab, 0))} |")
    cr = w.get("race", {}).get("censor_reasons", {})
    A("")
    A(f"Censoring splits {cr.get('horizon', 0):,} at the 250-session horizon and "
      f"{cr.get('data_end', 0):,} at the tape's end (delisting without a −20% print; a "
      "delisting that collapses fires TOPPED on its own bars).")
    A("")

    A("## 3. E1 — matched-control separation (registration track W)")
    A("")
    if not e1:
        A("*Track W was not run in this pass, so there is no registration result. "
          "Track D can never register a claim (survivorship tilt, §11).*")
        A("")
    A(f"Cases: {_fmt(w.get('cases', {}).get('n_cases'))} snapshots at `days_to_peak ∈ "
      f"{{21, 10, 5}}` from {_fmt(w.get('cases', {}).get('n_case_episodes'))} TOPPED "
      f"episodes (per offset: {w.get('cases', {}).get('per_offset', {})}). Controls: "
      f"{_fmt(w.get('cases', {}).get('n_control_candidates'))} CONTINUED EXT-day "
      "candidates, matched within calendar quarter × r126 quintile × rv63 tercile × "
      "dollar-volume tercile, ≤4 nearest neighbours by |Δr126| then |Δrv63|, never from "
      "the case's own name.")
    A("")
    m = w.get("matching", {})
    A(f"**Honest N: {_fmt(e1.get('n_episodes'))} DISTINCT EPISODES** "
      f"(from {_fmt(e1.get('n_case_sets'))} matched case-sets; "
      f"{_fmt(m.get('n_dropped_no_control'))} cases dropped with zero eligible "
      f"controls, {_fmt(m.get('controls_per_case_mean'), 2)} controls per matched "
      "case). §4.5 aggregation is EPISODE-FIRST: an episode's {21,10,5} snapshots "
      "collapse to their median Δ before anything is pooled, because three looks at "
      "one event are not three events. A Δ exists only where the case and ≥"
      f"{ta.MIN_FINITE_CONTROLS} controls are finite.")
    A("")
    A(f"Distinct episode-peak months: **{_fmt(e1.get('n_distinct_peak_months'))}** "
      f"against the {ta.MIN_EPISODE_MONTHS} a registered separation requires.")
    A("")
    A(f"**{n_sep} of 36 features separate** (≥{ta.MIN_EPISODE_MONTHS} peak-months "
      "AND the 95% episode-peak-month block CI excluding 0 AND the declared sign "
      "where one was declared AND BH-FDR q ≤ 0.10 within family AND ≥60% coverage). "
      f"Registered: {e1.get('registered_separating') or 'none'}. "
      f"Exploratory (discovery-only, never DETECTION): "
      f"{e1.get('exploratory_separating') or 'none'}. "
      f"By family: {e1.get('by_family', {})}.")
    A("")
    L.extend(_e1_table(e1.get("table", [])))
    A("")
    below = w.get("features_below_coverage_floor", [])
    A(f"Features under the 60% coverage floor on track W (not interpreted): "
      f"{', '.join('`%s`' % f for f in below) if below else 'none'}.")
    A("")

    A("## 4. E1b — pooled AUC increment over extension + volatility (§4.7)")
    A("")
    b = w.get("e1b", {})
    if not b:
        A("Track W was not run in this pass — no E1b.")
    elif b.get("error"):
        A(f"Not computed: {b['error']}.")
    else:
        A(f"Nested: {b.get('nested')}. Preprocessing: {b.get('preprocessing')}. "
          f"Walk-forward purge = {b.get('embargo_sessions')} sessions (the full "
          "race-label horizon, so a training row's label cannot be resolved by bars "
          "inside the test window).")
        A("")
        A("| model | features | grouped-by-ticker AUC [95% CI] | walk-forward AUC "
          "[95% CI] | episode AUC (grouped) |")
        A("|---|---|---|---|---|")
        for k in ("M0", "M1", "M2"):
            mm = b.get("models", {}).get(k, {})
            g, wf = mm.get("grouped", {}), mm.get("walk_forward", {})
            gci = f"[{_fmt(g.get('ci_lo'), 3)}, {_fmt(g.get('ci_hi'), 3)}]"
            wci = f"[{_fmt(wf.get('ci_lo'), 3)}, {_fmt(wf.get('ci_hi'), 3)}]"
            A(f"| {k} | {mm.get('n_features', len(mm.get('features', [])))} | "
              f"{_fmt(g.get('auc'), 3)} {gci} | {_fmt(wf.get('auc'), 3)} {wci} | "
              f"{_fmt(g.get('episode_auc'), 3)} |")
        A("")
        gci = b.get("increment_grouped_ci") or [None, None]
        wci = b.get("increment_walk_forward_ci") or [None, None]
        A(f"AUC(M2) − AUC(M1), paired episode-block CI: grouped "
          f"{_fmt(b.get('increment_grouped'), 3)} [{_fmt(gci[0], 3)}, {_fmt(gci[1], 3)}], "
          f"walk-forward {_fmt(b.get('increment_walk_forward'), 3)} "
          f"[{_fmt(wci[0], 3)}, {_fmt(wci[1], 3)}] — "
          f"sign-consistent: **{b.get('sign_consistent')}**. "
          f"n = {_fmt(b.get('n_rows'))} EXT days on {_fmt(b.get('n_names'))} names / "
          f"{_fmt(b.get('n_episodes_in_sample'))} episodes, base rate TOPPED = "
          f"{_fmt(b.get('base_rate_topped'), 3)}. Descriptive — E1b registers no test.")
    A("")

    A("## 5. E2 — lead-time labels (§4.8; G0.4 is mandatory)")
    A("")
    A("A feature that separates only in the last window (`0..-5`, peak day through "
      "five sessions after) is **POST-TOP CONFIRMATION** and may never be described "
      "as detection. An exploratory field keeps an `EXPLORATORY` prefix and can never "
      "reach DETECTION grade.")
    A("")
    labels = w.get("e2", {}).get("labels", {})
    if labels:
        A("| survivor | lead-time label |")
        A("|---|---|")
        for f, lab in labels.items():
            A(f"| `{f}` | **{lab}** |")
    else:
        A(f"No survivors to profile — {w.get('e2', {}).get('note', '')}.")
    A("")
    A("")
    A("Windows are stated **positive-before-peak** (`days_to_peak = peak_date − d`): "
      "EARLY +22..+63, MID +6..+21, LATE +1..+5, POST-TOP CONFIRMATION 0..−5.")
    for tag, blk in w.get("e2", {}).get("buckets", {}).items():
        A(f"- `{tag}` ({blk.get('window', '')}): {_fmt(blk.get('n_episodes'))} episodes "
          f"from {_fmt(blk.get('n_cases'))} matched cases.")
    A("")

    A("## 6. E3 — first-crossing order (descriptive)")
    A("")
    order = w.get("e3", {}).get("order", [])
    if order:
        A("| survivor | control tail | threshold | episodes crossing "
          "| median days_to_peak at first cross |")
        A("|---|---|---|---|---|")
        for r in order:
            A(f"| `{r['feature']}` | P{int(r.get('control_tail', 0.9) * 100)} | "
              f"{_fmt(r['threshold'])} | {_fmt(r['n_episodes_crossing'])} | "
              f"{_fmt(r['median_days_to_peak_at_first_cross'], 1)} |")
    else:
        A(f"Nothing to order — {w.get('e3', {}).get('note', 'no survivors')}.")
    A("")

    A("## 7. E4 — era and dollar-volume stability (descriptive)")
    A("")
    for track_key, blk, eras in (("W", w.get("e4", {}), W_ERAS), ("D", d.get("e4", {}), D_ERAS)):
        A(f"**Track {track_key}**"
          + (" — survivorship-TILTED, era context only, never a registration claim."
             if track_key == "D" else ""))
        rows = blk.get("eras", {})
        if not rows:
            A(f"- {blk.get('note', 'track not run')}")
        for name, _, _ in eras:
            if name not in rows:
                continue
            e = rows[name]
            signs = {r["feature"]: _fmt(r["median_delta"]) for r in e.get("table", [])}
            note = "" if signs else " — under the 20-case floor, not estimated (printed null)"
            A(f"- `{name}`: {_fmt(e.get('n_episodes'))} episodes · median Δ "
              f"{signs if signs else 'null'}{note}")
        terc = blk.get("dvol_terciles", {})
        for t, e in terc.items():
            signs = {r["feature"]: _fmt(r["median_delta"]) for r in e.get("table", [])}
            A(f"- dollar-volume tercile `{t}`: {_fmt(e.get('n_episodes'))} episodes · "
              f"median Δ {signs if signs else 'null (under the 20-episode floor)'}")
        A("")

    A("## 8. The top ruler (§2) — is a fire a GOOD warning?")
    A("")
    legs = w.get("ruler", {}).get("legs", {})
    if legs:
        A("| survivor leg @ direction-aligned control tail | fires | episodes "
          "| median remaining upside to peak | within 5% of peak price "
          "| within ±10td of peak | fwd-63 excess vs all-EXT null |")
        A("|---|---|---|---|---|---|---|")
        for f, r in legs.items():
            A(f"| `{f}` @P{int(r.get('control_tail', 0.9) * 100)} | "
              f"{_fmt(r.get('n_fires'))} | {_fmt(r.get('n_fire_episodes'))} | "
              f"{_fmt(r.get('median_remaining_upside'), 3)} | "
              f"{_fmt(r.get('share_within_peak_price'), 3)} | "
              f"{_fmt(r.get('share_within_peak_time'), 3)} | "
              f"{_fmt(r.get('fwd_63_excess'), 4)} |")
        A("")
        A("Every metric is computed per NAME first and then pooled by median, so one "
          "heavily-fired name cannot carry a number. A warning with large remaining "
          "upside is a bad warning even when the episode eventually tops.")
    else:
        A(f"Nothing to rule — {w.get('ruler', {}).get('note', 'no survivors')}.")
    A("")

    A("## 9. G0.2 — delisting verification (the dead names, NAMED)")
    A("")
    g = w.get("g0_2_delisting", {})
    A(f"Track W carries {_fmt(g.get('n_dead_segments'))} segments whose last bar predates "
      f"{g.get('cutoff_last_bar_before')} (60 sessions before the tape's end of "
      f"{g.get('last_data_day')}); {_fmt(g.get('n_dead_with_an_episode'))} of them were "
      f"inside an extended episode. **Gate satisfied: {g.get('gate_g0_2_satisfied')}.**")
    A("")
    named = g.get("known_delistings_found") or g.get("named", [])[:10]
    if named:
        A("| segment | ticker | last bar |")
        A("|---|---|---|")
        for r in named[:15]:
            A(f"| `{r['segment']}` | {r['ticker']} | {r['last_bar']} |")
    A("")

    A("## 10. Today's tape (G0.5) — the current extended cohort")
    A("")
    t = w.get("today_tape", {})
    A(f"As of **{t.get('asof')}**: {_fmt(t.get('n_extended_today'))} names are EXTENDED "
      f"under the primary definition (showing the top {_fmt(t.get('n_rows'))} by r126, "
      f"capped at {TODAY_TAPE_CAP}).")
    A("")
    rows = t.get("rows", [])
    if rows:
        cols = ["ticker", "r126", "A6_ext_ma200_atr21", "A7_late_gain_share",
                "C3_semivol_ratio63", "D3_updown_dvol_ratio21", "E3f_rs_peak_lag",
                "E4f_price_rs_gap", "F1_episode_age", "F3_days_since_63d_high"]
        cols = [c for c in cols if c in rows[0]]
        A("| " + " | ".join(cols) + " |")
        A("|" + "---|" * len(cols))
        for r in rows[:40]:
            A("| " + " | ".join(_fmt(r.get(c), 3) for c in cols) + " |")
        A("")
        A("*Display-tier readout only: these are present-tense descriptive facts about "
          "names that are already extended, not a ranking, a call, or a probability.*")
    else:
        A("*Nothing extended on the last session — that is a finding, not an empty table.*")
    A("")

    A("## 11. Who is missing (survivorship)")
    A("")
    A("**Track W is honest by construction**: it is a whole-market pull, so names that "
      "topped and then died are in the tape with bars through their final trading day "
      "(§9 names them rather than assuming them). Its own limits are stated: dividends "
      "are unadjusted, and no derivative/warrant/unit filtering is applied beyond the "
      "price and liquidity floors.")
    A("")
    dl = d.get("panel", {})
    span = (f"{_fmt(dl.get('n_segments'))} segments, {dl.get('first_session')} → "
            f"{dl.get('last_session')}" if dl.get("n_segments") else "not run in this pass")
    A("**Track D is TILTED and can never register a claim.** It is a curated-current "
      f"universe ({span}) built from the adjusted "
      "price ladder on a FIRST-RUNG-WINS basis. The names that are missing are exactly "
      "the ones this study cares most about: companies that topped and were delisted, "
      "acquired, or dropped from basket curation before the current universe was drawn. "
      "The topped arm is therefore UNDERSTATED on D, and every D number above is era "
      "context for a W finding — never standalone evidence.")
    A("")
    A("---")
    A("")
    A(f"*Generated by `{summary['reproduce']}` · seed {summary['seed']} · "
      f"{summary['wall_seconds']:.0f}s wall.*")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(L) + "\n")


# ══════════════════════════════════════════════════════════════════════════════
# entry point
# ══════════════════════════════════════════════════════════════════════════════
def _source_file_count(data_root: Path, track: str, quick: int | None) -> int:
    """How many source files the census denominator should use (cache-hit safe)."""
    if track == "W":
        n = len(list((data_root / "massive_stock_day").glob("*.parquet")))
    else:
        names: set[str] = set()
        for _, sub in _D_RUNGS:
            d = data_root / sub
            if d.exists():
                names |= {p.stem for p in d.glob("*.parquet") if not p.stem.startswith("_")}
        n = len(names)
    return min(n, quick) if quick else n


def _git_sha() -> str:
    try:
        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=_REPO,
                           capture_output=True, text=True, timeout=20)
        return r.stdout.strip() or "unknown"
    except Exception:  # noqa: BLE001
        return "unknown"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--data-root", required=True, type=Path,
                    help="primary checkout's data/ directory (panels + cache live here)")
    ap.add_argument("--track", choices=("W", "D", "both"), default="both")
    ap.add_argument("--quick", type=int, default=None,
                    help="first N tickers alphabetically per track (smoke run)")
    ap.add_argument("--out-json", type=Path,
                    default=_REPO / "data/research/top_anatomy_p0_summary.json")
    ap.add_argument("--out-report", type=Path,
                    default=_REPO / "reports/top-anatomy-phase0.md")
    ap.add_argument("--seed", type=int, default=20260810)
    a = ap.parse_args(argv)

    quick = a.quick is not None
    cache_root = a.data_root / CACHE_SUBDIR
    tracks = ["W", "D"] if a.track == "both" else [a.track]
    summary = {
        "family": FAMILY,
        "run_date": pd.Timestamp.now("UTC").strftime("%Y-%m-%d"),
        "run_timestamp_utc": pd.Timestamp.now("UTC").isoformat(),
        "git_sha": _git_sha(),
        "prereg": "research/top_anatomy/TOPA_PHASE0_PREREG.md",
        "prereg_frozen": "2026-08-10",
        "seed": a.seed,
        "quick": a.quick,
        "reproduce": ("python -m scripts.research_top_anatomy_phase0 "
                      f"--data-root {a.data_root}"
                      + (f" --track {a.track}" if a.track != "both" else "")
                      + (f" --quick {a.quick}" if quick else "")),
        "tier": ("research/display tier, zero scored authority; AVOID-not-SHORT; "
                 "no rank, no size, no gate, no exit rule"),
        "tracks": {},
    }
    for tk in tracks:
        cache = cache_root / (f"W_quick{a.quick}" if (tk == "W" and quick) else
                              f"D_quick{a.quick}" if (tk == "D" and quick) else tk)
        built = (build_panel_w(a.data_root, cache, quick=a.quick) if tk == "W"
                 else build_panel_d(a.data_root, cache, quick=a.quick))
        n_files = _source_file_count(a.data_root, tk, a.quick)
        summary["tracks"][tk] = run_track(tk, built["panel"], built["meta"],
                                          seed=a.seed, quick=quick, n_files=n_files)
        say(f"track {tk} complete")

    summary["wall_seconds"] = time.time() - _T0
    a.out_json.parent.mkdir(parents=True, exist_ok=True)
    a.out_json.write_text(json.dumps(summary, indent=2, default=str))
    write_report(a.out_report, summary)
    say(f"wrote {a.out_json}")
    say(f"wrote {a.out_report}")
    say(f"done in {summary['wall_seconds']:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
