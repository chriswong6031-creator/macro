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
W_PANEL_COLS = ("close", "open", "high", "low", "volume")
D_START = "1997-01-01"
SAMPLE_EVERY = 5                      # 1-in-5 systematic sample of all EXT days
E2_BUCKETS = ((-63, -22), (-21, -6), (-5, -1), (0, 5))
E2_LABELS = {(-63, -22): "EARLY", (-21, -6): "MID", (-5, -1): "LATE",
             (0, 5): "POST-TOP CONFIRMATION"}
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
    cache.mkdir(parents=True, exist_ok=True)
    for c, fr in panel.items():
        if not fr.empty:
            fr.to_parquet(cache / f"panel_{c}.parquet")
    meta = {"n_tickers": len(bars), "n_segments": len(segs), "n_tickers_split": n_split}
    (cache / "meta.json").write_text(json.dumps(meta, indent=2))
    return {"panel": panel, "meta": meta}


def _load_cached(cache: Path) -> dict | None:
    if not (cache / "panel_close.parquet").exists() or not (cache / "meta.json").exists():
        return None
    panel = {}
    for c in W_PANEL_COLS:
        p = cache / f"panel_{c}.parquet"
        panel[c] = pd.read_parquet(p) if p.exists() else pd.DataFrame()
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
        factor = (px / split_adjust(px)).reindex(df.index).ffill().bfill()
        out = {"close": pd.to_numeric(df["close"], errors="coerce") / factor,
               "volume": pd.to_numeric(df["volume"], errors="coerce") * factor}
        for c in ("open", "high", "low"):
            if c in df.columns:
                out[c] = pd.to_numeric(df[c], errors="coerce") / factor
        frame = pd.DataFrame(out).dropna(subset=["close"])
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
# the track pipeline
# ══════════════════════════════════════════════════════════════════════════════
def run_track(track: str, panel: dict, meta: dict, *, seed: int, quick: bool) -> dict:
    """EXT -> episodes -> race -> peaks -> cases/controls -> features -> E1..E4."""
    close = panel["close"]
    volume = panel.get("volume")
    dvol = (close * volume).reindex_like(close) if volume is not None and not volume.empty \
        else pd.DataFrame(np.nan, index=close.index, columns=close.columns)
    out: dict = {"track": track, "panel": dict(meta)}
    out["panel"].update({
        "n_sessions": int(close.shape[0]), "n_segments": int(close.shape[1]),
        "first_session": str(close.index.min().date()) if len(close) else None,
        "last_session": str(close.index.max().date()) if len(close) else None,
    })

    say(f"[{track}] EXT mask (primary)")
    ext = ta.extended_mask(close, dvol, high_df=panel.get("high"), low_df=panel.get("low"))
    elig = ta.eligibility_mask(close, dvol)
    n_ext = int(ext.to_numpy().sum())
    out["ext"] = {"n_ext_days": n_ext,
                  "n_eligible_days": int(elig.to_numpy().sum()),
                  "n_segments_with_ext": int((ext.sum() > 0).sum())}
    say(f"[{track}] {n_ext} EXT days on {out['ext']['n_segments_with_ext']} segments")

    say(f"[{track}] sensitivity arms (report-only)")
    out["ext_variants"] = {"primary": n_ext}
    for variant in ("r63", "atrz"):
        try:
            m = ta.extended_mask(close, dvol, variant=variant,
                                 high_df=panel.get("high"), low_df=panel.get("low"))
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

    eqw = ta.equal_weight_median_index(close, elig, min_names=20 if not quick else 1)
    bars = _segment_bars(panel, sorted(set(need["segment"])))
    feats = ta.feature_library(bars, eqw, need[["segment", "date"]], episodes=episodes)
    out["feature_coverage"] = {
        f: float(feats[f].notna().mean()) for f in ta.FEATURES if f in feats.columns}
    out["feature_coverage_floor"] = COVERAGE_FLOOR
    out["features_below_coverage_floor"] = sorted(
        f for f, c in out["feature_coverage"].items() if c < COVERAGE_FLOOR)

    # ── E1 ───────────────────────────────────────────────────────────────────
    say(f"[{track}] E1 matched deltas + month-block bootstrap (B={ta.BOOTSTRAP_B})")
    deltas = ta.matched_deltas(pairs, feats)
    e1 = ta.matched_delta_stats(deltas, b=ta.BOOTSTRAP_B if not quick else 400, seed=seed,
                                coverage_floor=COVERAGE_FLOOR)
    out["e1"] = {
        "n_matched_cases": int(len(deltas)),
        "n_case_episodes": int(cases.loc[cases["case_id"].isin(deltas["case_id"]),
                                         "episode_id"].nunique()) if not deltas.empty else 0,
        "table": _records(e1),
        "n_separating": int(e1["separates"].sum()) if not e1.empty else 0,
        "separating": sorted(e1.loc[e1["separates"], "feature"]) if not e1.empty else [],
        "by_family": ({fam: {"n_tested": int(len(g)), "n_separating": int(g["separates"].sum())}
                       for fam, g in e1.groupby("family")} if not e1.empty else {}),
    }
    say(f"[{track}] E1: {out['e1']['n_separating']} of {len(ta.FEATURES)} features separate")

    # ── E1b ──────────────────────────────────────────────────────────────────
    say(f"[{track}] E1b pooled AUC increment")
    out["e1b"] = _e1b(feats, race, episodes, sample, close.index, seed=seed)

    # ── E2 / E3 / E4 ─────────────────────────────────────────────────────────
    survivors = out["e1"]["separating"]
    say(f"[{track}] E2 lead-time profiles on {len(survivors)} survivor(s)")
    out["e2"] = _e2(e2_days, pool, feats, survivors, seed=seed, quick=quick)
    say(f"[{track}] E3 ordering")
    out["e3"] = _e3(feats, dtp, topped_ids, pool, survivors)
    say(f"[{track}] E4 era / dollar-volume stability")
    out["e4"] = _e4(deltas, cases, gates, survivors, W_ERAS if track == "W" else D_ERAS,
                    seed=seed, quick=quick)

    # ── the ruler (§2) ───────────────────────────────────────────────────────
    say(f"[{track}] top ruler on survivor legs")
    out["ruler"] = _ruler(feats, ext, episodes, close, pool, survivors)

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
    d["signed"] = -d["days_to_peak"]                  # negative = before the peak
    lab = []
    for lo, hi in E2_BUCKETS:
        g = d[(d["signed"] >= lo) & (d["signed"] <= hi)].copy()
        g["bucket"] = f"{lo}..{hi}"
        lab.append(g.sort_values("signed").groupby("episode_id", as_index=False).head(2))
    out = pd.concat(lab, ignore_index=True) if lab else d.head(0)
    out["case_id"] = out["episode_id"] + "@" + out["bucket"] + "@" + out["signed"].astype(str)
    return out


def _e1b(feats: pd.DataFrame, race: pd.DataFrame, episodes: pd.DataFrame,
        sample: pd.DataFrame, calendar: pd.DatetimeIndex, *, seed: int) -> dict:
    """§4.7 pooled increment: M0 (r126) vs M1 (+rv63) vs M2 (all 36), two CV schemes.

    Fixed L2 logistic (C=1.0) on standardized inputs, no grid, no selection inside
    folds. CV-A groups by TICKER so no company appears in both arms; CV-B expands by
    calendar quarter with a 63-session embargo between train end and test start.
    The claim of interest is AUC(M2) − AUC(M1), sign-consistent across both schemes.
    """
    try:
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

    models = {"M0": ["A3_r126"], "M1": ["A3_r126", "C1_rv21"], "M2": list(ta.FEATURES)}
    # M1's second leg is rv63; the library carries rv21 and the rv21/rv63 ratio, so
    # rv63 is reconstructed rather than re-derived from bars.
    d["_rv63"] = d["C1_rv21"] / d["C2_rv21_over_rv63"].replace(0.0, np.nan)
    models["M1"] = ["A3_r126", "_rv63"]

    ticker = d["ticker"].astype(str) if "ticker" in d.columns else d["segment"].astype(str)
    ep = episodes[["segment", "start", "end", "episode_id", "outcome"]]
    out: dict = {"n_rows": int(len(d)), "base_rate_topped": float(d["y"].mean()),
                 "n_names": int(ticker.nunique()), "models": {}}

    def fit_auc(cols: list[str], scheme: str) -> dict:
        x = d[cols].to_numpy(dtype=float)
        y = d["y"].to_numpy()
        ok = np.isfinite(x).all(axis=1)
        x, y2 = x[ok], y[ok]
        sub = d[ok]
        if len(np.unique(y2)) < 2 or len(y2) < 200:
            return {"auc": None, "n": int(len(y2)), "reason": "too thin"}
        prob = np.full(len(y2), np.nan)
        pipe = make_pipeline(StandardScaler(),
                             LogisticRegression(C=1.0, max_iter=2000, random_state=seed))
        if scheme == "grouped":
            g = sub["ticker"].to_numpy()
            n_split = min(5, len(np.unique(g)))
            if n_split < 2:
                return {"auc": None, "n": int(len(y2)), "reason": "one group"}
            for tr, te in GroupKFold(n_splits=n_split).split(x, y2, groups=g):
                if len(np.unique(y2[tr])) < 2:
                    continue
                prob[te] = pipe.fit(x[tr], y2[tr]).predict_proba(x[te])[:, 1]
        else:
            q = pd.PeriodIndex(pd.to_datetime(sub["date"]), freq="Q")
            uq = sorted(q.unique())
            dates = pd.to_datetime(sub["date"]).to_numpy()
            for i in range(4, len(uq)):
                te = np.flatnonzero(q == uq[i])
                # 63-SESSION embargo, counted on the panel's own trading calendar
                # (a calendar-day approximation would leak on holiday-dense quarters).
                pos = int(calendar.searchsorted(uq[i].start_time))
                cut = calendar[max(0, pos - 63)]
                tr = np.flatnonzero(dates < np.datetime64(cut))
                if len(tr) < 200 or len(te) == 0 or len(np.unique(y2[tr])) < 2:
                    continue
                prob[te] = pipe.fit(x[tr], y2[tr]).predict_proba(x[te])[:, 1]
        m = np.isfinite(prob)
        if m.sum() < 100 or len(np.unique(y2[m])) < 2:
            return {"auc": None, "n": int(m.sum()), "reason": "no scored fold"}
        res = {"auc": float(roc_auc_score(y2[m], prob[m])), "n": int(m.sum())}
        # episode-level AUC: max probability inside an episode vs the episode outcome
        scored = sub[m].copy()
        scored["p"] = prob[m]
        joined = scored.merge(ep, on="segment", how="left")
        joined = joined[(joined["date"] >= joined["start"]) & (joined["date"] <= joined["end"])]
        if not joined.empty:
            agg = joined.groupby("episode_id").agg(p=("p", "max"),
                                                   outcome=("outcome", "first"))
            yy = (agg["outcome"] == "TOPPED").astype(int)
            if yy.nunique() == 2:
                res["episode_auc"] = float(roc_auc_score(yy, agg["p"]))
                res["n_episodes"] = int(len(agg))
        return res

    for name, cols in models.items():
        cols = [c for c in cols if c in d.columns]
        out["models"][name] = {"features": cols,
                               "grouped": fit_auc(cols, "grouped"),
                               "walk_forward": fit_auc(cols, "walk_forward")}
    for scheme in ("grouped", "walk_forward"):
        a2 = out["models"]["M2"][scheme].get("auc")
        a1 = out["models"]["M1"][scheme].get("auc")
        out[f"increment_{scheme}"] = (a2 - a1) if (a2 is not None and a1 is not None) else None
    incs = [out.get("increment_grouped"), out.get("increment_walk_forward")]
    out["sign_consistent"] = (all(i is not None for i in incs)
                              and (incs[0] > 0) == (incs[1] > 0))
    return out


def _e2(e2_days: pd.DataFrame, pool: pd.DataFrame, feats: pd.DataFrame,
        survivors: list[str], *, seed: int, quick: bool) -> dict:
    """§4.8 lead-time profile: matched Δ by days_to_peak bucket, with the label.

    A survivor is labelled by the EARLIEST bucket whose month-block CI excludes 0;
    a survivor that separates only in {0..+5} is POST-TOP CONFIRMATION and may
    never be described as detection (G0.4).
    """
    if not survivors or e2_days.empty or pool.empty:
        return {"labels": {}, "buckets": {}, "note": "no E1 survivors to profile"}
    res: dict = {"buckets": {}, "labels": {}}
    for lo, hi in E2_BUCKETS:
        tag = f"{lo}..{hi}"
        sub = e2_days[e2_days["bucket"] == tag]
        if sub.empty:
            res["buckets"][tag] = {"n_cases": 0, "features": {}}
            continue
        pairs, diag = ta.matched_controls(sub, pool)
        deltas = ta.matched_deltas(pairs, feats)
        stats = ta.matched_delta_stats(deltas, survivors,
                                       b=500 if quick else ta.BOOTSTRAP_B, seed=seed,
                                       coverage_floor=COVERAGE_FLOOR)
        res["buckets"][tag] = {
            "n_cases": int(diag["n_matched"]),
            "n_episodes": int(sub["episode_id"].nunique()),
            "table": _records(stats),
        }
    for f in survivors:
        label = "NO PRE-PEAK SEPARATION"
        for lo, hi in E2_BUCKETS:
            t = res["buckets"].get(f"{lo}..{hi}", {}).get("table", [])
            row = next((r for r in t if r["feature"] == f), None)
            if row and row.get("separates"):
                label = E2_LABELS[(lo, hi)]
                break
        res["labels"][f] = label
    return res


def _e3(feats: pd.DataFrame, dtp: pd.DataFrame, topped_ids: set, pool: pd.DataFrame,
        survivors: list[str]) -> dict:
    """§4.8 E3 — descriptive first-crossing ORDER of survivors at control-P90 thresholds."""
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
        direction = ta.FEATURE_DIRECTION.get(feat, 0)
        thr = float(ctrl[feat].quantile(0.90 if direction >= 0 else 0.10))
        cross = f[f[feat] >= thr] if direction >= 0 else f[f[feat] <= thr]
        if cross.empty:
            continue
        first = cross.sort_values("days_to_peak", ascending=False) \
            .groupby("episode_id", as_index=False).first()
        rows.append({
            "feature": feat, "direction": direction, "threshold_control_p90": thr,
            "n_episodes_crossing": int(len(first)),
            "median_days_to_peak_at_first_cross": float(first["days_to_peak"].median()),
            "p25": float(first["days_to_peak"].quantile(0.25)),
            "p75": float(first["days_to_peak"].quantile(0.75)),
        })
    rows.sort(key=lambda r: -r["median_days_to_peak_at_first_cross"])
    return {"order": rows}


def _e4(deltas: pd.DataFrame, cases: pd.DataFrame, gates: pd.DataFrame,
        survivors: list[str], eras, *, seed: int, quick: bool) -> dict:
    """§4.9 descriptive sign stability of survivors across eras and dollar-volume terciles."""
    if not survivors or deltas.empty:
        return {"eras": {}, "dvol_terciles": {}, "note": "no E1 survivors to stratify"}
    d = deltas.merge(cases[["case_id", "date", "dvol21"]].drop_duplicates("case_id"),
                     on="case_id", how="left", suffixes=("", "_c"))
    d["date"] = pd.to_datetime(d["date"])
    b = 400 if quick else 1000
    res: dict = {"eras": {}, "dvol_terciles": {}}
    for name, lo, hi in eras:
        sub = d[(d["date"] >= pd.Timestamp(lo)) & (d["date"] <= pd.Timestamp(hi))]
        res["eras"][name] = {
            "n_cases": int(len(sub)),
            "table": _records(ta.matched_delta_stats(sub, survivors, b=b, seed=seed,
                                                     coverage_floor=COVERAGE_FLOOR))
            if len(sub) >= 20 else [],
        }
    if d["dvol21"].notna().sum() >= 30:
        try:
            d["_terc"] = pd.qcut(d["dvol21"].rank(method="first"), 3, labels=["low", "mid", "high"])
        except ValueError:
            d["_terc"] = "all"
        for terc, sub in d.groupby("_terc", observed=True):
            res["dvol_terciles"][str(terc)] = {
                "n_cases": int(len(sub)),
                "table": _records(ta.matched_delta_stats(sub, survivors, b=b, seed=seed,
                                                         coverage_floor=COVERAGE_FLOOR))
                if len(sub) >= 20 else [],
            }
    return res


def _ruler(feats: pd.DataFrame, ext: pd.DataFrame, episodes: pd.DataFrame,
           close: pd.DataFrame, pool: pd.DataFrame, survivors: list[str]) -> dict:
    """§2 wrong-ruler check for each survivor leg thresholded at control-P90."""
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
        direction = ta.FEATURE_DIRECTION.get(feat, 0)
        thr = float(ctrl[feat].quantile(0.90 if direction >= 0 else 0.10))
        f = feats[["segment", "date", feat]].dropna()
        f = f[f[feat] >= thr] if direction >= 0 else f[f[feat] <= thr]
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
        legs[feat] = {"threshold_control_p90": thr, **r}
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
    out = ["| feature | family | dir | n | cov | median Δ | 95% CI (month-block) | q | separates |",
           "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        d = {1: "higher⇒TOPPED", -1: "lower⇒TOPPED", 0: "exploratory"}[r["direction"]]
        ci = f"[{_fmt(r['ci_lo'])}, {_fmt(r['ci_hi'])}]"
        out.append(f"| `{r['feature']}` | {r['family']} | {d} | {_fmt(r['n_cases'])} | "
                   f"{_fmt(r['coverage'], 2)} | {_fmt(r['median_delta'])} | {ci} | "
                   f"{_fmt(r['q_value'], 3)} | {'**YES**' if r['separates'] else 'no'} |")
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
    A(f"Cases: {_fmt(w.get('cases', {}).get('n_cases'))} snapshots at `days_to_peak ∈ "
      f"{{21, 10, 5}}` from {_fmt(w.get('cases', {}).get('n_case_episodes'))} TOPPED "
      f"episodes (per offset: {w.get('cases', {}).get('per_offset', {})}). Controls: "
      f"{_fmt(w.get('cases', {}).get('n_control_candidates'))} CONTINUED EXT-day "
      "candidates, matched within calendar quarter × r126 quintile × rv63 tercile × "
      "dollar-volume tercile, ≤4 nearest neighbours by |Δr126| then |Δrv63|, never from "
      "the case's own name.")
    A("")
    m = w.get("matching", {})
    A(f"**Honest N:** {_fmt(m.get('n_matched'))} matched cases across "
      f"{_fmt(e1.get('n_case_episodes'))} DISTINCT EPISODES "
      f"({_fmt(m.get('n_dropped_no_control'))} cases dropped with zero eligible "
      f"controls, {_fmt(m.get('controls_per_case_mean'), 2)} controls per matched case).")
    A("")
    A(f"**{n_sep} of 36 features separate** (month-block CI excluding 0 on the "
      "pre-declared side AND BH-FDR q ≤ 0.10 within family AND ≥60% coverage). "
      f"By family: {e1.get('by_family', {})}.")
    A("")
    L.extend(_e1_table(e1.get("table", [])))
    A("")
    below = w.get("features_below_coverage_floor", [])
    A(f"Features under the 60% coverage floor on track W (not interpreted): "
      f"{', '.join('`%s`' % f for f in below) if below else 'none'}.")
    A("")

    A("## 4. E1b — pooled AUC increment over extension alone (§4.7)")
    A("")
    b = w.get("e1b", {})
    if b.get("error"):
        A(f"Not computed: {b['error']}.")
    else:
        A("| model | grouped-by-ticker AUC | walk-forward AUC | episode AUC (grouped) |")
        A("|---|---|---|---|")
        for k in ("M0", "M1", "M2"):
            mm = b.get("models", {}).get(k, {})
            A(f"| {k} ({len(mm.get('features', []))} features) | "
              f"{_fmt(mm.get('grouped', {}).get('auc'), 3)} | "
              f"{_fmt(mm.get('walk_forward', {}).get('auc'), 3)} | "
              f"{_fmt(mm.get('grouped', {}).get('episode_auc'), 3)} |")
        A("")
        A(f"AUC(M2) − AUC(M1): grouped {_fmt(b.get('increment_grouped'), 3)}, "
          f"walk-forward {_fmt(b.get('increment_walk_forward'), 3)} — "
          f"sign-consistent: **{b.get('sign_consistent')}**. "
          f"n = {_fmt(b.get('n_rows'))} EXT days on {_fmt(b.get('n_names'))} names, "
          f"base rate TOPPED = {_fmt(b.get('base_rate_topped'), 3)}.")
    A("")

    A("## 5. E2 — lead-time labels (§4.8; G0.4 is mandatory)")
    A("")
    A("A feature that separates only in the `{0..+5}` bucket is **POST-TOP "
      "CONFIRMATION** and may never be described as detection.")
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
    for tag, blk in w.get("e2", {}).get("buckets", {}).items():
        A(f"- bucket `{tag}`: {_fmt(blk.get('n_cases'))} matched cases across "
          f"{_fmt(blk.get('n_episodes'))} episodes.")
    A("")

    A("## 6. E3 — first-crossing order (descriptive)")
    A("")
    order = w.get("e3", {}).get("order", [])
    if order:
        A("| survivor | control-P90 threshold | episodes crossing "
          "| median days_to_peak at first cross |")
        A("|---|---|---|---|")
        for r in order:
            A(f"| `{r['feature']}` | {_fmt(r['threshold_control_p90'])} | "
              f"{_fmt(r['n_episodes_crossing'])} | "
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
            A(f"- `{name}`: {_fmt(e.get('n_cases'))} cases · median Δ "
              f"{signs if signs else 'null'}{note}")
        terc = blk.get("dvol_terciles", {})
        for t, e in terc.items():
            signs = {r["feature"]: _fmt(r["median_delta"]) for r in e.get("table", [])}
            A(f"- dollar-volume tercile `{t}`: {_fmt(e.get('n_cases'))} cases · median Δ "
              f"{signs if signs else 'null (under the 20-case floor)'}")
        A("")

    A("## 8. The top ruler (§2) — is a fire a GOOD warning?")
    A("")
    legs = w.get("ruler", {}).get("legs", {})
    if legs:
        A("| survivor leg @ control-P90 | fires | episodes "
          "| median remaining upside to peak | within 5% of peak price "
          "| within ±10td of peak | fwd-63 excess vs all-EXT null |")
        A("|---|---|---|---|---|---|---|")
        for f, r in legs.items():
            A(f"| `{f}` | {_fmt(r.get('n_fires'))} | {_fmt(r.get('n_fire_episodes'))} | "
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
        summary["tracks"][tk] = run_track(tk, built["panel"], built["meta"],
                                          seed=a.seed, quick=quick)
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
