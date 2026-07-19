"""engine/tech_confluence.py — multi-signal ("combo") descriptive backtest miner.

Answers: which 2/3/4-signal combinations — possibly across timeframes — have
historically produced a higher win rate than random entries, while still firing
often enough to be usable?

HONESTY CONTRACT (display-tier; gauntlet applies only at promotion)
-------------------------------------------------------------------
- Descriptive research artefact over the SURVIVORSHIP-BIASED mega-cap universe.
- Combos are found by SEARCH over many candidates; the artifact records how many
  were evaluated so the UI can disclose "found by searching N combos — leads,
  not proof".
- Effective sample size is time-clustered: fires cluster in calendar months, so
  all edge claims use MONTH-COLLAPSED win rates (each calendar month contributes
  one observation) and a train/test split at SPLIT_DATE. Ranking uses the Wilson
  lower bound on the TEST half only.
- No 'validated' claims. Nulls (insufficient history) are reported, not hidden.
- TLT-R3: signal fires come only from engine.tech_catalog.compute — this module
  composes those canonical series; it never reimplements an indicator.
- TLT-R6: forward horizons restricted to the descriptive ladder {10, 21, 42, 63}.

LEG MODEL
---------
A leg is (signal_id, timeframe) with timeframe ∈ {"D", "W"}:

- kind="state" legs are ACTIVE while the state is on (>0).
- kind="event" legs are ACTIVE for EVENT_WINDOW bars after a fire (window
  includes the fire bar) — "fired recently".
- "W" legs are computed on W-FRI resampled bars (close=last, high=max, low=min,
  volume=sum) and mapped to the daily index with ffill. A daily bar only ever
  sees the most recent COMPLETED week: a Friday bar sees the week that closed
  that Friday (legitimate because entries are next-bar); when Friday is a
  holiday the W-FRI label postdates the week's last trading day, so that week
  becomes visible only from the label date onward — up to a few days LATE,
  never early (conservative). Weekly legs are restricted to trend/context
  families (W_FAMILIES); tickers with under 60 completed weeks keep those legs
  all-False (insufficient history, an honest null).

A combo is a set of 2..4 same-direction legs. Its activity is the AND of leg
activities; a combo FIRE is the rising edge of that AND (the bar where the last
missing condition arrives). Entry = next close; forward return over each
horizon h is close[t+1+h]/close[t+1] - 1 (same convention as
engine.tech_stars.compute_fire_metrics).

SEARCH
------
Exhaustive pair sweep → apriori/beam extension: a combo is only extended by one
leg if it passed the SUPPORT gate and showed non-negative month-collapsed
train-half edge at 21d. Triples are beam-capped before quad extension. Pairs of
near-duplicate legs (pooled Jaccard > JACCARD_MAX) are excluded — the AND of a
signal with itself is not confluence. All caps/gates live in MinerConfig and
are exported into the artifact meta.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from itertools import combinations
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

HORIZONS: tuple[int, ...] = (10, 21, 42, 63)  # TLT-R6 descriptive ladder
_Z90 = 1.6449  # one-sided 90% z for Wilson lower bound


# ---------------------------------------------------------------------------
# Configuration (pre-registered constants — exported into artifact meta)
# ---------------------------------------------------------------------------

@dataclass
class MinerConfig:
    event_window_d: int = 5        # daily event legs: active for 5 bars after fire
    event_window_w: int = 4        # weekly event legs: active for 4 completed weeks
    split_date: str = "2018-01-01" # train (<) / test (>=) fire-date split
    jaccard_max: float = 0.90      # legs more similar than this can't share a combo
    min_fires: int = 40            # SUPPORT gate: pooled fires (21d-defined)
    min_months: int = 24           # SUPPORT gate: distinct fire months
    min_tickers: int = 10          # SUPPORT gate: distinct tickers fired
    min_test_fires: int = 15       # REPORT gate: test-half fires
    min_test_months: int = 12      # REPORT gate: test-half distinct months
    beam_triples: int = 900        # top triples (by train edge) extended to quads
    max_k: int = 4                 # max legs per combo
    rank_horizon: int = 21         # ranking horizon
    base_samples: int = 300_000    # random-entry baseline sample size
    seed: int = 42

    def as_meta(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


# Families eligible for weekly legs (trend/context — slow structures where the
# higher timeframe is the natural home; fast one-bar patterns stay daily-only).
W_FAMILIES = frozenset({
    "trend", "trend_ribbon", "ichimoku", "ma_price", "ma_crosses",
    "rsi_bands", "rsi_stack", "tech_stars",
    # Momentum cross events — weekly is a natural home (weekly MACD / RSI / Stoch-RSI
    # crosses). stoch_events_2w is deliberately excluded (a "weekly of a biweekly" is
    # meaningless; it is a daily leg that resamples to 2 weeks internally).
    "macd_events", "rsi_events", "stoch_events",
})

# Never legs: snapshot families without dated per-bar fires (TLT canonical
# exemption) and raw/derived signals that are not usable combo conditions.
EXCLUDED_FAMILIES = frozenset({"fundamental_valuation", "insider"})
EXCLUDED_SIGNALS = frozenset({
    "return_1d",        # raw daily return, not a condition
    "new_golden_star",  # age-window duplicate of golden_star_st_7_35
})

# ---------------------------------------------------------------------------
# Combo v1 gate: families eligible for the primary combo miner.
# Only families present BEFORE the Technical Lab integration are included here.
# This keeps tonight's off-render miner runtime unchanged.
# Combo v2 lifts this gate by using the role-grammar search over all families.
# ---------------------------------------------------------------------------
LEGACY_COMBO_FAMILIES: frozenset[str] = frozenset({
    "ma_crosses", "ma_price", "tech_stars", "trend", "trend_ribbon",
    "pivots", "formations",
    "rsi_bands", "rsi_events", "rsi_stack",
    "bollinger_events",
    "macd_events", "stoch_events", "stoch_events_2w",
    "ichimoku",
    "performance",
    # fundamental_valuation and insider are already excluded via EXCLUDED_FAMILIES
    # Indicators M2 (D04): VWAP/volume-profile families — daily-only legs (week-anchored VWAP
    # and rolling-anchor AVWAP need daily bars; families deliberately NOT in W_FAMILIES).
    "vwap_events", "volume_profile_events",
})


# ---------------------------------------------------------------------------
# Leg enumeration
# ---------------------------------------------------------------------------

def build_leg_defs(tc: Any) -> list[dict[str, Any]]:
    """Enumerate eligible legs from the tech_catalog.

    Combo v1 gate: excludes (a) challenger_only=True signals and (b) any signal
    whose family is not in LEGACY_COMBO_FAMILIES (the families present before the
    Technical Lab integration). This keeps the off-render miner runtime unchanged.
    Combo v2 will lift this gate via the role-grammar search.

    Returns a list of dicts: {leg_id, signal_id, tf, kind, family, direction,
    display_en, display_zh}. Directions are ±1 only.
    """
    legs: list[dict[str, Any]] = []
    for sig in tc.list_signals():
        sid = sig["signal_id"]
        fam = sig.get("family", "")
        direction = int(sig.get("direction", 0) or 0)
        # Combo v1 gate: exclude challenger-only signals and new-integration families
        if sig.get("challenger_only", False):
            continue
        if fam not in LEGACY_COMBO_FAMILIES:
            continue
        if fam in EXCLUDED_FAMILIES or sid in EXCLUDED_SIGNALS or direction == 0:
            continue
        tfs = ["D"] + (["W"] if fam in W_FAMILIES else [])
        for tf in tfs:
            legs.append({
                "leg_id": f"{sid}@{tf}",
                "signal_id": sid,
                "tf": tf,
                "kind": sig.get("kind", "event"),
                "family": fam,
                "direction": direction,
                "display_en": sig.get("display", {}).get("en", sid),
                "display_zh": sig.get("display", {}).get("zh", sid),
            })
    return legs


# ---------------------------------------------------------------------------
# Per-ticker leg activity
# ---------------------------------------------------------------------------

def _weekly_bars(df: pd.DataFrame) -> pd.DataFrame:
    """Resample daily OHLCV to completed W-FRI bars."""
    wk = pd.DataFrame({
        "close": df["close"].resample("W-FRI").last(),
        "high": df["high"].resample("W-FRI").max(),
        "low": df["low"].resample("W-FRI").min(),
        "volume": df["volume"].resample("W-FRI").sum(),
    }).dropna(subset=["close"])
    return wk


def _event_recent(fires: pd.Series, window: int) -> pd.Series:
    """Boolean 'fired within the last `window` bars (inclusive)'."""
    return (fires > 0).rolling(window, min_periods=1).max().astype(bool)


def leg_activity_matrix(
    df: pd.DataFrame,
    legs: list[dict[str, Any]],
    tc: Any,
    cfg: MinerConfig,
) -> np.ndarray:
    """Compute the (n_legs, n_bars) boolean activity matrix for one ticker.

    Daily legs: state → series>0; event → fired within event_window_d bars.
    Weekly legs: computed on completed W-FRI bars, activity mapped to the daily
    index via ffill (a daily bar sees only the most recent completed week).
    Legs whose compute fails are all-False (logged at debug).
    """
    n = len(df)
    out = np.zeros((len(legs), n), dtype=bool)
    daily_index = df.index

    wk = None  # lazy — only resample when some W leg is present
    for i, leg in enumerate(legs):
        try:
            if leg["tf"] == "D":
                series = tc.compute(leg["signal_id"], df)
                if leg["kind"] == "state":
                    act = series.fillna(0.0) > 0
                else:
                    act = _event_recent(series.fillna(0.0), cfg.event_window_d)
                out[i] = act.reindex(daily_index, fill_value=False).to_numpy()
            else:
                if wk is None:
                    wk = _weekly_bars(df)
                if len(wk) < 60:
                    continue  # not enough weekly history
                series_w = tc.compute(leg["signal_id"], wk)
                if leg["kind"] == "state":
                    act_w = series_w.fillna(0.0) > 0
                else:
                    act_w = _event_recent(series_w.fillna(0.0), cfg.event_window_w)
                # Map completed weeks onto daily bars. W-FRI labels are >= the
                # last daily bar of their bin, so ffill never leaks an
                # incomplete week into an earlier daily bar.
                act_d = act_w.reindex(daily_index.union(act_w.index)).ffill() \
                             .reindex(daily_index).fillna(False)
                out[i] = act_d.to_numpy(dtype=bool)
        except Exception as exc:  # noqa: BLE001 — a broken leg is all-False
            log.debug("leg %s failed on %s: %s", leg["leg_id"], df.attrs.get("ticker"), exc)
    return out


# ---------------------------------------------------------------------------
# Global panel — all tickers concatenated on one timeline with guard bars
# ---------------------------------------------------------------------------

@dataclass
class LegPanel:
    """Concatenated per-ticker arrays with one guard slot between tickers.

    Guard slots have all-False activity and NaN forward returns, so combo
    rising edges and forward stats can never bleed across tickers.
    """
    legs: list[dict[str, Any]]
    act: np.ndarray                    # (n_legs, N) bool
    fwd: dict[int, np.ndarray]         # horizon → (N,) float32 fwd return at fire bar
    mfe: np.ndarray                    # (N,) float32 max fav. excursion @ rank horizon
    mae: np.ndarray                    # (N,) float32 max adv. excursion @ rank horizon
    month_id: np.ndarray               # (N,) int32  year*12+month of the FIRE bar
    is_test: np.ndarray                # (N,) bool   fire date >= split_date
    ticker_id: np.ndarray              # (N,) int32
    dates: np.ndarray                  # (N,) datetime64[D]
    tickers: list[str]
    last_pos: dict[str, int]           # ticker → global index of its last real bar
    cfg: MinerConfig = field(default_factory=MinerConfig)


def build_panel(
    universe: dict[str, pd.DataFrame],
    tc: Any,
    cfg: MinerConfig | None = None,
    legs: list[dict[str, Any]] | None = None,
) -> LegPanel:
    """Build the global LegPanel from a {ticker: OHLCV df} universe."""
    cfg = cfg or MinerConfig()
    legs = legs if legs is not None else build_leg_defs(tc)
    split = np.datetime64(cfg.split_date)
    hmax = max(HORIZONS)
    rank_h = cfg.rank_horizon

    acts, fwds, mfes, maes, months, tests, tids, dats = [], {h: [] for h in HORIZONS}, [], [], [], [], [], []
    tickers = sorted(universe.keys())
    last_pos: dict[str, int] = {}
    offset = 0

    for t_i, tk in enumerate(tickers):
        df = universe[tk]
        df.attrs["ticker"] = tk
        n = len(df)
        if n < 300:
            continue

        act = leg_activity_matrix(df, legs, tc, cfg)
        close = df["close"].to_numpy(dtype=np.float64)

        # forward returns anchored at the FIRE bar t: entry close[t+1], exit close[t+1+h]
        for h in HORIZONS:
            f = np.full(n, np.nan, dtype=np.float32)
            valid_n = n - 1 - h
            if valid_n > 0:
                entry = close[1:1 + valid_n]
                exit_ = close[1 + h:1 + h + valid_n]
                with np.errstate(divide="ignore", invalid="ignore"):
                    f[:valid_n] = (exit_ / entry - 1.0).astype(np.float32)
                f[:valid_n][entry <= 0] = np.nan
            fwds[h].append(np.append(f, np.float32(np.nan)))  # +guard

        # MFE / MAE over [t+1, t+1+rank_h] closes
        m_fe = np.full(n, np.nan, dtype=np.float32)
        m_ae = np.full(n, np.nan, dtype=np.float32)
        w = rank_h + 1
        if n - 1 >= w:
            sw = np.lib.stride_tricks.sliding_window_view(close[1:], w)  # window at t starts close[t+1]
            entry = close[1:1 + sw.shape[0]]
            with np.errstate(divide="ignore", invalid="ignore"):
                m_fe[:sw.shape[0]] = ((sw.max(axis=1) - entry) / entry).astype(np.float32)
                m_ae[:sw.shape[0]] = ((entry - sw.min(axis=1)) / entry).astype(np.float32)
            m_fe[:sw.shape[0]][entry <= 0] = np.nan
            m_ae[:sw.shape[0]][entry <= 0] = np.nan
        mfes.append(np.append(m_fe, np.float32(np.nan)))
        maes.append(np.append(m_ae, np.float32(np.nan)))

        idx = df.index.to_numpy().astype("datetime64[D]")
        mo = (df.index.year * 12 + df.index.month).to_numpy().astype(np.int32)
        acts.append(np.concatenate([act, np.zeros((len(legs), 1), dtype=bool)], axis=1))
        months.append(np.append(mo, np.int32(-1)))
        tests.append(np.append(idx >= split, False))
        tids.append(np.full(n + 1, t_i, dtype=np.int32))
        dats.append(np.append(idx, np.datetime64("1900-01-01", "D")))
        last_pos[tk] = offset + n - 1
        offset += n + 1

    panel = LegPanel(
        legs=legs,
        act=np.concatenate(acts, axis=1),
        fwd={h: np.concatenate(fwds[h]) for h in HORIZONS},
        mfe=np.concatenate(mfes),
        mae=np.concatenate(maes),
        month_id=np.concatenate(months),
        is_test=np.concatenate(tests),
        ticker_id=np.concatenate(tids),
        dates=np.concatenate(dats),
        tickers=tickers,
        last_pos=last_pos,
        cfg=cfg,
    )
    log.info("panel: %d legs × %d bars (%d tickers)", len(legs), panel.act.shape[1], len(tickers))
    return panel


# ---------------------------------------------------------------------------
# Stats helpers
# ---------------------------------------------------------------------------

def wilson_lb(p: float, n: int, z: float = _Z90) -> float:
    """One-sided Wilson lower bound. Heuristic when applied to month-collapsed
    proportions (months are averages, not Bernoulli draws) — used for RANKING
    only, disclosed as such."""
    if n <= 0 or not np.isfinite(p):
        return float("nan")
    z2 = z * z
    denom = 1.0 + z2 / n
    center = p + z2 / (2 * n)
    rad = z * np.sqrt(p * (1 - p) / n + z2 / (4 * n * n))
    return float((center - rad) / denom)


def _month_collapsed_wr(win: np.ndarray, months: np.ndarray) -> tuple[float, int]:
    """Mean of per-calendar-month win rates. Returns (wr_mc, n_months)."""
    if len(win) == 0:
        return float("nan"), 0
    uniq, inv = np.unique(months, return_inverse=True)
    sums = np.bincount(inv, weights=win.astype(np.float64))
    cnts = np.bincount(inv)
    return float((sums / cnts).mean()), int(len(uniq))


def combo_fires(panel: LegPanel, leg_idx: tuple[int, ...]) -> np.ndarray:
    """Global positions of combo rising-edge fires."""
    a = np.logical_and.reduce(panel.act[list(leg_idx)], axis=0)
    prev = np.empty_like(a)
    prev[0] = False
    prev[1:] = a[:-1]
    return np.flatnonzero(a & ~prev)


def evaluate_combo(
    panel: LegPanel,
    leg_idx: tuple[int, ...],
    direction: int,
) -> dict[str, Any] | None:
    """Full descriptive stats for one combo, or None if zero fires.

    'win' for direction=+1 is fwd_ret > 0; for direction=-1 it is fwd_ret < 0.
    """
    fi = combo_fires(panel, leg_idx)
    if len(fi) == 0:
        return None
    cfg = panel.cfg
    out: dict[str, Any] = {"legs": [panel.legs[i]["leg_id"] for i in leg_idx],
                           "dir": direction, "k": len(leg_idx)}
    # fire-set fingerprint — lets the miner drop combos whose extra legs add no
    # constraint (identical fire sets → identical stats → duplicate rows)
    out["_fp"] = hashlib.blake2b(fi.tobytes(), digest_size=12).hexdigest()

    months_all = panel.month_id[fi]
    test_all = panel.is_test[fi]

    for h in HORIZONS:
        r = panel.fwd[h][fi]
        ok = np.isfinite(r)
        r, mo, te = r[ok], months_all[ok], test_all[ok]
        win = (r > 0) if direction > 0 else (r < 0)
        st: dict[str, Any] = {"n": int(len(r))}
        if len(r):
            st["wr"] = round(float(win.mean()), 4)
            st["mean"] = round(float(r.mean()) * direction, 5)
            st["median"] = round(float(np.median(r)) * direction, 5)
            wr_mc, n_mo = _month_collapsed_wr(win, mo)
            st["wr_mc"], st["months"] = round(wr_mc, 4), n_mo
            for half, mask in (("train", ~te), ("test", te)):
                if mask.sum():
                    wmc, nmo = _month_collapsed_wr(win[mask], mo[mask])
                    st[f"wr_mc_{half}"], st[f"months_{half}"] = round(wmc, 4), nmo
                    st[f"n_{half}"] = int(mask.sum())
                else:
                    st[f"wr_mc_{half}"], st[f"months_{half}"], st[f"n_{half}"] = None, 0, 0
        out[f"h{h}"] = st

    # rank-horizon extras
    fi_ok = fi[np.isfinite(panel.fwd[cfg.rank_horizon][fi])]
    if len(fi_ok):
        mfe, mae = panel.mfe[fi_ok], panel.mae[fi_ok]
        if direction < 0:
            mfe, mae = mae, mfe  # favourable for a short = downside excursion
        with np.errstate(divide="ignore", invalid="ignore"):
            ratio = mfe / np.where(mae > 1e-9, mae, np.nan)
        ratio = ratio[np.isfinite(ratio)]
        out["mfe_mae_med"] = round(float(np.median(ratio)), 3) if len(ratio) else None

    out["n_fires"] = int(len(fi))
    out["n_tickers"] = int(len(np.unique(panel.ticker_id[fi])))
    d = panel.dates[fi]
    out["first_fire"] = str(d.min())
    out["last_fire"] = str(d.max())
    span_years = max(0.5, (d.max() - d.min()).astype("timedelta64[D]").astype(float) / 365.25)
    out["fires_per_year"] = round(len(fi) / span_years, 2)
    cutoff3y = d.max() - np.timedelta64(365 * 3, "D")
    out["fires_last3y"] = int((d >= cutoff3y).sum())
    return out


def passes_support(stats: dict[str, Any], cfg: MinerConfig) -> bool:
    h = stats.get(f"h{cfg.rank_horizon}", {})
    return (
        h.get("n", 0) >= cfg.min_fires
        and h.get("months", 0) >= cfg.min_months
        and stats.get("n_tickers", 0) >= cfg.min_tickers
    )


def passes_report(stats: dict[str, Any], cfg: MinerConfig) -> bool:
    h = stats.get(f"h{cfg.rank_horizon}", {})
    return (
        passes_support(stats, cfg)
        and h.get("n_test", 0) >= cfg.min_test_fires
        and h.get("months_test", 0) >= cfg.min_test_months
    )


# ---------------------------------------------------------------------------
# Baseline (random entries)
# ---------------------------------------------------------------------------

def baseline_stats(panel: LegPanel, direction: int = +1) -> dict[str, Any]:
    """Random-entry baseline: wr / wr_mc pooled and per split half, per horizon.

    Each horizon draws its own sample from the bars where THAT horizon's
    forward return is defined, so a combo's h-stats and the baseline they are
    compared against share the same date support (a shorter horizon includes
    more-recent bars than a longer one; reusing one 63d-windowed pool for all
    horizons would compare recent combo fires against a strictly older
    baseline — review finding, 2026-07-12).
    """
    cfg = panel.cfg
    rng = np.random.default_rng(cfg.seed)
    out: dict[str, Any] = {"n_samples": {}}
    for h in HORIZONS:
        pool = np.flatnonzero(np.isfinite(panel.fwd[h]))
        take = min(cfg.base_samples, len(pool))
        fi = rng.choice(pool, size=take, replace=False)
        r = panel.fwd[h][fi]  # finite by construction
        mo, te = panel.month_id[fi], panel.is_test[fi]
        win = (r > 0) if direction > 0 else (r < 0)
        wr_mc, _ = _month_collapsed_wr(win, mo)
        h_out = {"wr": round(float(win.mean()), 4), "wr_mc": round(wr_mc, 4)}
        for half, mask in (("train", ~te), ("test", te)):
            if mask.sum():
                wmc, _ = _month_collapsed_wr(win[mask], mo[mask])
                h_out[f"wr_mc_{half}"] = round(wmc, 4)
        out[f"h{h}"] = h_out
        out["n_samples"][f"h{h}"] = int(take)
    return out


# ---------------------------------------------------------------------------
# Miner
# ---------------------------------------------------------------------------

def _edge(stats: dict[str, Any], base: dict[str, Any], h: int, half: str) -> float | None:
    s = stats.get(f"h{h}", {}).get(f"wr_mc_{half}")
    b = base.get(f"h{h}", {}).get(f"wr_mc_{half}")
    if s is None or b is None:
        return None
    return round(s - b, 4)


def _rank_score(stats: dict[str, Any], base: dict[str, Any], cfg: MinerConfig) -> float:
    """Wilson lower bound of test-half month-collapsed WR minus test baseline."""
    h = stats.get(f"h{cfg.rank_horizon}", {})
    p, n = h.get("wr_mc_test"), h.get("months_test", 0)
    b = base.get(f"h{cfg.rank_horizon}", {}).get("wr_mc_test")
    if p is None or b is None or n <= 0:
        return float("-inf")
    return wilson_lb(p, n) - b


def _jaccard_forbidden(panel: LegPanel, idx: list[int], cfg: MinerConfig) -> set[frozenset[int]]:
    """Pairs of legs too similar to co-occur in a combo (pooled Jaccard)."""
    forbidden: set[frozenset[int]] = set()
    counts = {i: int(panel.act[i].sum()) for i in idx}
    for i, j in combinations(idx, 2):
        if counts[i] == 0 or counts[j] == 0:
            continue
        inter = int(np.count_nonzero(panel.act[i] & panel.act[j]))
        union = counts[i] + counts[j] - inter
        if union > 0 and inter / union > cfg.jaccard_max:
            forbidden.add(frozenset((i, j)))
    return forbidden


def mine(
    panel: LegPanel,
    direction: int = +1,
    progress: Any = None,
) -> dict[str, Any]:
    """Mine pair/triple/quad combos for one direction.

    Returns {"combos": [stats...], "n_evaluated": {2:…,3:…,4:…}, "base": {...},
    "forbidden_pairs": int}. Every returned combo passed the REPORT gate; each
    carries edge_* fields and rank_score.
    """
    cfg = panel.cfg
    base = baseline_stats(panel, direction)
    idx = [i for i, l in enumerate(panel.legs) if l["direction"] == direction]
    forbidden = _jaccard_forbidden(panel, idx, cfg)
    log.info("mine dir=%+d: %d legs, %d forbidden near-duplicate pairs", direction, len(idx), len(forbidden))

    n_eval = {2: 0, 3: 0, 4: 0}
    n_dup_dropped = 0
    reported: dict[frozenset[int], dict[str, Any]] = {}
    fp_owner: dict[str, frozenset[int]] = {}  # fire-set fingerprint → first combo
    frontier: list[tuple[frozenset[int], dict[str, Any]]] = []

    def _admissible(combo: frozenset[int]) -> bool:
        return not any(frozenset(p) <= combo for p in forbidden) if forbidden else True

    def _train_edge(stats: dict[str, Any]) -> float | None:
        return _edge(stats, base, cfg.rank_horizon, "train")

    def _finalize(stats: dict[str, Any]) -> dict[str, Any]:
        stats["edge_wr_test"] = _edge(stats, base, cfg.rank_horizon, "test")
        stats["edge_wr_train"] = _edge(stats, base, cfg.rank_horizon, "train")
        stats["edges_by_h"] = {h: _edge(stats, base, h, "test") for h in HORIZONS}
        stats["consistent"] = bool(
            (stats["edge_wr_train"] or 0) > 0 and (stats["edge_wr_test"] or 0) > 0
        )
        stats["rank_score"] = round(_rank_score(stats, base, cfg), 4)
        return stats

    # --- pairs (exhaustive) ---
    for pair in combinations(idx, 2):
        combo = frozenset(pair)
        if not _admissible(combo):
            continue
        n_eval[2] += 1
        stats = evaluate_combo(panel, tuple(sorted(combo)), direction)
        if stats is None or not passes_support(stats, cfg):
            continue
        te = _train_edge(stats)
        if te is not None and te >= 0:
            frontier.append((combo, stats))
        if passes_report(stats, cfg):
            fp = stats.pop("_fp", None)
            if fp is None or fp not in fp_owner:
                if fp is not None:
                    fp_owner[fp] = combo
                reported[combo] = _finalize(stats)
            else:
                n_dup_dropped += 1
        if progress and n_eval[2] % 500 == 0:
            progress(f"pairs evaluated: {n_eval[2]}")

    # --- triples & quads (apriori extension + beam) ---
    for k in (3, 4):
        if k > cfg.max_k or not frontier:
            break
        if k == 4 and len(frontier) > cfg.beam_triples:
            frontier.sort(key=lambda cs: -(_train_edge(cs[1]) or float("-inf")))
            frontier = frontier[: cfg.beam_triples]
        next_frontier: list[tuple[frozenset[int], dict[str, Any]]] = []
        seen: set[frozenset[int]] = set()
        for combo, _ in frontier:
            for j in idx:
                if j in combo:
                    continue
                cand = combo | {j}
                if cand in seen or not _admissible(cand):
                    continue
                seen.add(cand)
                n_eval[k] += 1
                stats = evaluate_combo(panel, tuple(sorted(cand)), direction)
                if stats is None or not passes_support(stats, cfg):
                    continue
                te = _train_edge(stats)
                if te is not None and te >= 0:
                    next_frontier.append((cand, stats))
                if passes_report(stats, cfg):
                    # dedupe on the fire-set fingerprint: sweep order (k=2→3→4)
                    # guarantees the incumbent has fewer-or-equal legs, so a
                    # duplicate here is an extra leg adding no constraint
                    fp = stats.pop("_fp", None)
                    if fp is None or fp not in fp_owner:
                        if fp is not None:
                            fp_owner[fp] = cand
                        reported[cand] = _finalize(stats)
                    else:
                        n_dup_dropped += 1
                if progress and n_eval[k] % 2000 == 0:
                    progress(f"k={k} evaluated: {n_eval[k]}")
        frontier = next_frontier

    combos = sorted(reported.values(), key=lambda s: -s["rank_score"])
    log.info(
        "mine dir=%+d: evaluated %s, reported %d (dropped %d duplicate fire-sets)",
        direction, n_eval, len(combos), n_dup_dropped,
    )
    return {"combos": combos, "n_evaluated": n_eval, "base": base,
            "forbidden_pairs": len(forbidden), "n_dup_dropped": n_dup_dropped}


# ---------------------------------------------------------------------------
# Current-state helpers (for the UI's "who matches now")
# ---------------------------------------------------------------------------

def active_now(panel: LegPanel, leg_ids: list[str]) -> list[str]:
    """Tickers whose latest bar has ALL of the given legs active."""
    id_map = {l["leg_id"]: i for i, l in enumerate(panel.legs)}
    rows = [id_map[lid] for lid in leg_ids if lid in id_map]
    if len(rows) != len(leg_ids):
        return []
    return [tk for tk, pos in panel.last_pos.items()
            if bool(panel.act[rows, pos].all())]


def recent_fire_events(
    panel: LegPanel, leg_ids: list[str], years: int = 3, cap: int = 60,
) -> list[dict[str, str]]:
    """Most recent combo fires as {ticker, date} rows (newest first, capped)."""
    id_map = {l["leg_id"]: i for i, l in enumerate(panel.legs)}
    rows = tuple(sorted(id_map[lid] for lid in leg_ids if lid in id_map))
    if len(rows) != len(leg_ids):
        return []
    fi = combo_fires(panel, rows)
    if len(fi) == 0:
        return []
    d = panel.dates[fi]
    cutoff = d.max() - np.timedelta64(365 * years, "D")
    keep = fi[d >= cutoff]
    keep = keep[np.argsort(panel.dates[keep])][::-1][:cap]
    return [
        {"ticker": panel.tickers[int(panel.ticker_id[p])], "date": str(panel.dates[p])}
        for p in keep
    ]
