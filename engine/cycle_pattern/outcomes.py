"""engine/cycle_pattern/outcomes.py — Label-side OUTCOME spine for the CPI substrate.

The mirror image of lake.py (the FEATURE spine). For every (date, entity_id) row of
data/cycle_pattern/state_monthly.parquet this computes the *realized future* — forward
returns, drawdowns, benchmark-excess returns, turn-event labels, and phase transitions —
and NOTHING that was knowable at the stamp date. Features live in state, labels live
here, and the two are never mixed (PIT discipline). Row identity is (entity_id, date),
identical to state_monthly's key set.

FORWARD-WINDOW CONVENTION (the keystone). Forward returns/drawdowns use EXACTLY the
china grader convention — engine.china_sector_cycles_grader._fwd, which delegates to
engine.grading_stats.fwd_window (also copied verbatim into
scripts/keystone_position_gate_phase0.py._fwd):

  - anchor at the FIRST close STRICTLY AFTER the stamp date: j = searchsorted(side='right')
    (the bar-i+1 anchor — the engine/signal_quality.py marker-date leak guard, +5.7pp/10d
    phantom edge pinned by tests/test_signal_quality_no_leak.py);
  - window = close[j : j+h+1] (h+1 points);
  - ret   = close[j+h] / close[j] - 1;
  - maxdd = (win / cummax(win) - 1).min()  — the running-peak drawdown over the FULL
    window (including the entry bar's implicit 0), i.e. the deepest peak-to-trough move,
    NOT a purely entry-anchored min(0, close[k]/close[j]-1). This is what "EXACTLY the
    china grader convention" means; the two agree whenever the entry bar is the window
    high (the common case) and the grader's definition is the binding one.
  - NO partial windows: while j+h >= len(idx) (or the tape is missing / non-positive /
    non-finite at entry) the outcome is NaN — never estimated.

EXCESS RETURNS are the forward window of the RATIO series px/bench (multiplicative
excess, ret_ratio = (asset_gross)/(bench_gross) - 1), matching both the grader's `rel`
channel (_fwd on px/bench) and the repo's established relative-strength convention
(scripts/build_hazard_panel.py._rs_63d). Family benchmarks (the tapes the repo already
uses for RS): us_sector -> SPY, country/bloc -> ACWX (-> EFA fallback, as ACWX is absent
from data/yahoo/), cn_sector -> the CSI-300 proxy resolved the rs way (801050 Shenwan
Materials -> 801010 fallback; there is no standalone 000300 tape on disk, so RS_BENCH's
"000300" resolves through build_hazard_panel's _load_cn_sector_close proxy chain).

TAPES. US sectors + countries/blocs: data/yahoo/<TICKER-UPPER>.parquet 'close' (TR basis
-> the label outcome basis is 'tr'). China Shenwan: data/china_sectors/<code>.parquet
'close' (the same store engine.china_sector_index.sw_close reads). Absent tape -> all
price-derived outcomes NaN and tape_missing=True.

TURN EVENTS are a LEFT JOIN of y1/y3/y6 + direction from the hazard panel
(data/hazard/panel_price_c4414dcb.parquet) on (month-end date, UPPERCASE native_id),
surfaced as turn_event_1m/3m/6m + direction. These labels are DELIBERATELY excluded from
state_monthly (lake._FORBIDDEN_COLS) and live only here.

PHASE TRANSITIONS are derived WITHIN each entity's monthly backfill series:
phase_next_1m / phase_next_3m are the phase value 1 / 3 rows ahead **only when the
month-ends are consecutive** (no calendar gap); phase_changed_1m/3m flag a phase change
(NaN when the horizon phase is unknown).

EMBARGO. Rows with date >= 2024-01-01 sit inside the permanently embargoed holdout and
MUST NOT be used for any trial / model selection (config.yml embargo_holdout_start).

Pure numpy/pandas/pyarrow. No sklearn/statsmodels/scipy.stats. Deterministic (sorted
rows, stable dtypes) so a rebuild is frame-equal.
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parent.parent.parent
_DATA = _ROOT / "data"

STATE_MONTHLY_PATH = _DATA / "cycle_pattern" / "state_monthly.parquet"
YAHOO_DIR = _DATA / "yahoo"
CN_SECTOR_DIR = _DATA / "china_sectors"

HAZARD_EPOCH = "price_c4414dcb"
_HAZARD_PATH = _DATA / "hazard" / f"panel_{HAZARD_EPOCH}.parquet"

# Forward-window horizons (trading bars). 21/63/126 per the task spec — a superset of
# the grader's (21, 63) and the keystone backfill's (21, 63, 126).
HORIZONS: tuple[int, ...] = (21, 63, 126)

# Label outcome basis: yahoo/Shenwan closes are total-return / price-index levels.
BASIS = "tr"

# Family -> benchmark ticker (the tapes the repo already uses for RS —
# scripts/build_hazard_panel.RS_BENCH). "cn_sector" resolves to the CN proxy chain.
_BENCH_TICKER = {
    "us_sector": "SPY",
    "country": "ACWX",
    "bloc": "ACWX",
    "cn_sector": "000300",
}

# Final, sorted column order for outcomes.parquet. NO feature columns (no pos, no
# phase-at-t, no hazard features) — those live in state_monthly, never here.
OUTCOME_COLUMNS: list[str] = [
    "date", "entity_id", "basis", "tape_missing",
    "ret_fwd_21d", "ret_fwd_63d", "ret_fwd_126d",
    "excess_ret_fwd_21d", "excess_ret_fwd_63d", "excess_ret_fwd_126d",
    "max_drawdown_fwd_21d", "max_drawdown_fwd_63d", "max_drawdown_fwd_126d",
    "turn_event_1m", "turn_event_3m", "turn_event_6m", "direction",
    "phase_next_1m", "phase_next_3m", "phase_changed_1m", "phase_changed_3m",
]

# Columns that would leak the feature/label-at-t side into the outcome spine. Encoded as
# a hard guard so a future edit that accidentally carries a state column fails loudly.
_FORBIDDEN_COLS = frozenset({
    "pos", "phase", "osc_slope", "signal", "timing_state", "above200d", "rs_63d",
    "proj_next", "proj_central", "proj_lo", "proj_hi", "pos_v2", "phase_v2", "stance",
    "divergence", "overdue", "age_m", "age_bucket", "trend_pass", "mom_score",
    "rs_63d_hz", "vol_pctile", "amp_proxy", "log_age_ratio", "quad", "liquidity",
    "hazard_epoch", "y1", "y3", "y6", "event_date",
})


# ───────────────────────────────────────────── forward-window primitives (keystone) ──
# Copied verbatim from engine.china_sector_cycles_grader._fwd (-> grading_stats.fwd_window)
# and scripts/keystone_position_gate_phase0.py._fwd. Local copies keep this module a pure
# label-side leaf that does not import the grading engine — but the convention is theirs.

def _entry_pos(idx: pd.DatetimeIndex, stamp: pd.Timestamp) -> int | None:
    """Position of the FIRST bar STRICTLY AFTER the stamp date (the bar-i+1 anchor)."""
    j = int(idx.searchsorted(stamp, side="right"))
    return j if j < len(idx) else None


def _fwd(px: pd.Series, stamp: pd.Timestamp, h: int) -> dict | None:
    """Realized forward window of h trading bars anchored at bar i+1. Returns
    {ret, maxdd} or None if the window has not fully matured (no partial windows)."""
    idx = px.index
    j = _entry_pos(idx, stamp)
    if j is None or j + h >= len(idx):
        return None
    if not idx[j] > stamp:  # belt-and-braces vs the known marker-date leak trap
        raise ValueError(
            "look-ahead guard: forward anchor must be strictly after the stamp date "
            "(bar-i+1 convention; engine/signal_quality.py +5.7pp/10d leak trap)."
        )
    win = px.iloc[j:j + h + 1].to_numpy(dtype=float)
    if win[0] <= 0 or not np.isfinite(win).all():
        return None
    ret = float(win[-1] / win[0] - 1.0)
    dd = float((win / np.maximum.accumulate(win) - 1.0).min())
    return {"ret": ret, "maxdd": dd}


# ─────────────────────────────────────────────────────────────────── tape loaders ───

def _load_yahoo_close(ticker: str) -> pd.Series | None:
    """TR close (split+dividend adjusted). Matches build_hazard_panel._load_yahoo_close."""
    p = YAHOO_DIR / f"{ticker.upper()}.parquet"
    if not p.exists():
        return None
    df = pd.read_parquet(p)
    if "close" not in df.columns:
        return None
    s = df["close"].dropna().sort_index()
    s.index = pd.to_datetime(s.index)
    return s if not s.empty else None


def _load_cn_sector_close(code: str) -> pd.Series | None:
    """Shenwan L1 close — the store engine.china_sector_index.sw_close reads."""
    p = CN_SECTOR_DIR / f"{code}.parquet"
    if not p.exists():
        return None
    df = pd.read_parquet(p)
    if "close" not in df.columns:
        return None
    s = df["close"].dropna().sort_index()
    s.index = pd.to_datetime(s.index)
    return s if not s.empty else None


def _load_cn_benchmark() -> pd.Series | None:
    """CN RS benchmark resolved the way scripts/build_hazard_panel.py does: the CSI-300
    proxy chain 801050 (Shenwan Materials) -> 801010, since no standalone 000300 tape
    exists on disk. RS_BENCH labels this '000300'."""
    b = _load_cn_sector_close("801050")
    if b is None:
        b = _load_cn_sector_close("801010")
    return b


def _load_tape(family: str, native_id: str) -> pd.Series | None:
    if family == "cn_sector":
        return _load_cn_sector_close(str(native_id))
    return _load_yahoo_close(str(native_id))


def _load_benchmark(family: str) -> pd.Series | None:
    if family == "cn_sector":
        return _load_cn_benchmark()
    if family in ("country", "bloc"):
        b = _load_yahoo_close("ACWX")
        return b if b is not None else _load_yahoo_close("EFA")  # documented fallback
    if family == "us_sector":
        return _load_yahoo_close("SPY")
    return None


def _ratio_series(px: pd.Series, bench: pd.Series | None) -> pd.Series | None:
    """px / bench with the benchmark ffilled onto px's own calendar — the grader's
    _ratio convention (bench.reindex(px.index).ffill())."""
    if bench is None:
        return None
    b = bench.dropna().sort_index()
    if b.empty:
        return None
    aligned = b.reindex(px.index).ffill()
    r = (px / aligned).replace([np.inf, -np.inf], np.nan).dropna()
    return r if not r.empty else None


# ─────────────────────────────────────────────────────────────── outcome assembly ───

def _family_of(entity_id: str) -> str:
    return str(entity_id).split(":", 1)[0]


def _price_outcomes(state: pd.DataFrame) -> pd.DataFrame:
    """Forward ret/maxdd/excess per (entity_id, date), grouped by (family, native_id) so
    each tape + benchmark ratio is loaded once."""
    cols = {c: np.full(len(state), np.nan) for c in (
        "ret_fwd_21d", "ret_fwd_63d", "ret_fwd_126d",
        "excess_ret_fwd_21d", "excess_ret_fwd_63d", "excess_ret_fwd_126d",
        "max_drawdown_fwd_21d", "max_drawdown_fwd_63d", "max_drawdown_fwd_126d",
    )}
    tape_missing = np.zeros(len(state), dtype=bool)

    idx_np = state.index.to_numpy()
    fam_series = state["entity_id"].map(_family_of)

    for (fam, native), grp in state.groupby([fam_series, state["native_id"]], sort=False):
        px = _load_tape(fam, native)
        rows = grp.index.to_numpy()
        if px is None:
            for r in rows:
                tape_missing[np.searchsorted(idx_np, r)] = True
            continue
        px = px.dropna().sort_index()
        rr = _ratio_series(px, _load_benchmark(fam))
        for r, stamp in zip(rows, pd.to_datetime(grp["date"]).to_numpy()):
            pos = int(np.searchsorted(idx_np, r))
            ts = pd.Timestamp(stamp)
            for h, tag in zip(HORIZONS, ("21d", "63d", "126d")):
                w = _fwd(px, ts, h)
                if w is not None:
                    cols[f"ret_fwd_{tag}"][pos] = w["ret"]
                    cols[f"max_drawdown_fwd_{tag}"][pos] = w["maxdd"]
                if rr is not None:
                    wr = _fwd(rr, ts, h)
                    if wr is not None:
                        cols[f"excess_ret_fwd_{tag}"][pos] = wr["ret"]

    out = pd.DataFrame(cols, index=state.index)
    out["tape_missing"] = tape_missing
    return out


def _turn_events(state: pd.DataFrame) -> pd.DataFrame:
    """LEFT JOIN hazard y1/y3/y6 + direction on (month-end date, UPPER native_id)."""
    key = pd.DataFrame({
        "native_id": state["native_id"].astype(str).str.upper().to_numpy(),
        "date": (pd.to_datetime(state["date"]) + pd.offsets.MonthEnd(0)).dt.normalize().to_numpy(),
    }, index=state.index)

    h = pd.read_parquet(_HAZARD_PATH)
    h = h.copy()
    h["native_id"] = h["id"].astype(str).str.upper()
    h["date"] = (pd.to_datetime(h["date"]) + pd.offsets.MonthEnd(0)).dt.normalize()
    hk = h[["native_id", "date", "y1", "y3", "y6", "direction"]].copy()
    # hazard is unique per (id, date); guard against silent fan-out.
    if hk.duplicated(["native_id", "date"]).any():
        hk = hk.drop_duplicates(["native_id", "date"], keep="last")

    merged = key.merge(hk, on=["native_id", "date"], how="left")
    merged.index = state.index
    return pd.DataFrame({
        "turn_event_1m": merged["y1"].to_numpy(),
        "turn_event_3m": merged["y3"].to_numpy(),
        "turn_event_6m": merged["y6"].to_numpy(),
        "direction": merged["direction"].to_numpy(),
    }, index=state.index)


def _phase_transitions(state: pd.DataFrame) -> pd.DataFrame:
    """phase_next_1m/3m + phase_changed flags, per entity, only across CONSECUTIVE
    month-ends (a calendar gap breaks the chain -> next phase unknown -> NaN)."""
    phase_now = np.array([None] * len(state), dtype=object)
    n1 = np.array([None] * len(state), dtype=object)
    n3 = np.array([None] * len(state), dtype=object)

    for _, grp in state.groupby("entity_id", sort=False):
        g = grp.sort_values("date", kind="stable")
        pos = g.index.to_numpy()
        me = (pd.to_datetime(g["date"]) + pd.offsets.MonthEnd(0)).dt.normalize()
        month_ord = (me.dt.year * 12 + me.dt.month).to_numpy()
        phases = g["phase"].to_numpy()
        m = len(g)
        for i in range(m):
            phase_now[np.searchsorted(state.index.to_numpy(), pos[i])] = phases[i]
        state_ord = state.index.to_numpy()
        for i in range(m):
            gi = int(np.searchsorted(state_ord, pos[i]))
            if i + 1 < m and month_ord[i + 1] == month_ord[i] + 1:
                n1[gi] = phases[i + 1]
            if i + 3 < m and month_ord[i + 3] == month_ord[i] + 3:
                n3[gi] = phases[i + 3]

    def _changed(now: np.ndarray, nxt: np.ndarray) -> np.ndarray:
        out = np.array([None] * len(state), dtype=object)
        for i in range(len(state)):
            if nxt[i] is not None and now[i] is not None:
                out[i] = bool(nxt[i] != now[i])
        return out

    return pd.DataFrame({
        "phase_next_1m": n1,
        "phase_next_3m": n3,
        "phase_changed_1m": _changed(phase_now, n1),
        "phase_changed_3m": _changed(phase_now, n3),
    }, index=state.index)


def build_outcomes(state: pd.DataFrame | None = None) -> pd.DataFrame:
    """Return the label-side outcome spine, one row per state_monthly (entity_id, date),
    deterministically ordered (entity_id, date). state defaults to the committed
    state_monthly.parquet."""
    if state is None:
        state = pd.read_parquet(STATE_MONTHLY_PATH)
    state = state.reset_index(drop=True)

    price = _price_outcomes(state)
    turns = _turn_events(state)
    phase = _phase_transitions(state)

    out = pd.DataFrame(index=state.index)
    out["date"] = (pd.to_datetime(state["date"]) + pd.offsets.MonthEnd(0)).dt.normalize()
    out["entity_id"] = state["entity_id"].astype(str)
    out["basis"] = BASIS
    out["tape_missing"] = price["tape_missing"]

    for tag in ("21d", "63d", "126d"):
        out[f"ret_fwd_{tag}"] = price[f"ret_fwd_{tag}"].astype(float)
        out[f"excess_ret_fwd_{tag}"] = price[f"excess_ret_fwd_{tag}"].astype(float)
        out[f"max_drawdown_fwd_{tag}"] = price[f"max_drawdown_fwd_{tag}"].astype(float)

    out["turn_event_1m"] = turns["turn_event_1m"]
    out["turn_event_3m"] = turns["turn_event_3m"]
    out["turn_event_6m"] = turns["turn_event_6m"]
    out["direction"] = turns["direction"]

    out["phase_next_1m"] = phase["phase_next_1m"]
    out["phase_next_3m"] = phase["phase_next_3m"]
    out["phase_changed_1m"] = phase["phase_changed_1m"]
    out["phase_changed_3m"] = phase["phase_changed_3m"]

    # doctrine guard: no feature / phase-at-t / hazard column may have leaked in.
    leaked = _FORBIDDEN_COLS.intersection(out.columns)
    if leaked:
        raise ValueError(f"feature/label-at-t columns leaked into outcome spine: {sorted(leaked)}")

    out = out[OUTCOME_COLUMNS]
    out = out.sort_values(["entity_id", "date"], kind="stable").reset_index(drop=True)
    return out
