"""engine/washout_turn.py — per-name WEEKLY washout-turn watch organ (US).

DISPLAY-ONLY.  Authority block: tier=display, horizon_role=context,
may_rank/gate/size/escalate = false.  Nothing in the pick chain imports this
module; this module imports nothing from prophet/board code.

WHY IT EXISTS
-------------
`research/washout_turn_name_lane/MCD_MISS_EVIDENCE_2026-08-05.md`: MCD printed a
weekly RSI-MACD bullish cross on the completed 2026-07-31 bar at the 6.3rd
percentile of its own weekly line history since 1968 — the house canonical math
(`engine.canon`) even composes a full weekly-grid confluence BUY on that bar —
and NO organ consumed weekly-grain confluence PER NAME, so no surface said so.
`mtf_upturn`'s weekly leg watches standard *price* MACD-vs-zero (a different
indicator family); the shipped washout-turn lanes are basket/theme grain and can
never name a single member.  This organ closes that hole with watch vocabulary
only.

WHAT IT PRODUCES
----------------
  site/stockdata/washout_turn.json   (schema: washout_turn.v1)
  data/washout_turn/ledger.jsonl     (nightly-only, COLLECT_LANE gate; transitions only)
  per-ticker `rec["washout_turn"]`   (scripts/build_stock_library, additive)

MATH — REUSED, NEVER REIMPLEMENTED
----------------------------------
Every indicator comes from `engine.canon` (the corrected SMA-seeded RMA /
adjust=False EMA primitives the cross-repo signal contract is anchored to):
`rsi_macd`, `stoch_rsi_kd`, `rsi`, `crossover`, `bars_since`, and the frozen
params `RSI_LEN / CONF_W / OB / OS / BUY_RSI_MAX`.

WARNING: `engine.technicals.rsi` is a DIFFERENT rsi (bare `ewm` warm-up) and
must NEVER be used here — it flips near-threshold crosses in the early history,
which is exactly the depth region this organ reads.  Canon only.

PIT LAW
-------
Completed W-FRI weekly bars only.  A weekly label that lands strictly AFTER the
last daily bar is a PARTIAL week and is dropped before any indicator is
computed.  (When the last daily bar IS a Friday the label equals the date and
the bar is kept.)

READ THE DEPTH RECEIPT HONESTLY
-------------------------------
`depth_pctile` is a WHOLE-SAMPLE percentile of the name's own weekly line series
(the framing the evidence doc reproduces), so for a HISTORICAL cross it is
computed against bars that came after it.  For the live cross — the only one a
surface renders — the last bar is the sample end, so there is no forward look.
The own-history base rates are likewise a descriptive receipt, not a forecast:
they are printed with their n, immature (right-censored) events are dropped from
the medians, and nothing here ranks, gates, sizes, or escalates.

HISTORY-DEEPENING SPLICE (W2)
-----------------------------
`_load_close` prefers data/baskets/ohlcv/, which for long-listed names is the
SHORTEST store: MCD's ohlcv history starts 2014 (~580 weekly line bars) while
data/stocks/MCD.parquet starts 1966 (~3,000).  A depth percentile over the
name's own history is only as deep as the store behind it — off the truncated
store the 2026-07-31 MCD cross read depth 8.6 / n=8; off the full store it reads
6.3 / n=36 (same state, same since; the evidence doc's numbers).  So the DEPTH
legs (the percentile wherever it is read, including the qualification gate) and
the OWN-HISTORY BASE RATES evaluate a DEEPENED series: the preferred store
extended backward with the longest available store (data/stocks/ first, then
data/yahoo/) via a prepend-only splice at the preferred store's first bar
(`_splice_prepend`; precedent: the #4561 GOLD heal).  The splice only ever ADDS
bars strictly BEFORE the preferred store's first date — recent-close
disagreements between stores are real (split/dividend adjustment epochs differ;
the prepended segment is ratio-aligned at the boundary for exactly that reason)
— so the SIGNAL legs (cross detection, graduation/failure exits, watch
momentum, every last-bar indicator receipt) keep reading the preferred store's
values unchanged, and a name with no deeper store evaluates byte-identically.
`mtf_upturn` is deliberately NOT deepened: every field it emits is a
recent-window cross/state read (no own-history percentile, no base rates), so
deepening would add per-name store I/O for zero receipt change.

CN LANE DELIBERATELY NOT BUILT — operator sequencing is US first, CN after the US
lane ships.  No `compute_cn` / `_cn_*` twins exist in this module on purpose.

Amendment log:
  2026-08-05 W1: initial US lane (this file).
  2026-08-05 W2: history-deepening splice for the depth/base-rate legs
                 (prepend-only; signal legs unchanged on the preferred store).
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from engine.canon import (  # REUSE VERBATIM — never reimplement these
    BUY_RSI_MAX,
    CONF_W,
    OB,
    OS,
    RSI_LEN,
    bars_since,
    crossover,
    rsi,
    rsi_macd,
    stoch_rsi_kd,
)
from engine.ledger_lane import nightly_advance_enabled as _ledger_advance_enabled
# Universe + price loading are the mtf_upturn definitions (precedent:
# scripts/build_congress.py imports _load_close the same way) — one universe,
# one fallback chain, no second source of truth.
from engine.mtf_upturn import _build_universe, _load_close

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Authority block (invariant — display tier, zero authority)
# ---------------------------------------------------------------------------

AUTHORITY = {
    "tier": "display",
    "horizon_role": "context",
    "may_rank": False,
    "may_gate": False,
    "may_size": False,
    "may_escalate": False,
}

DISCLOSURE = (
    "Display-tier watch lane. Scored washout-to-turn constructions at sector grain "
    "printed NULL (Oracle P8 P-W1/S-W3) and the 2W operator-seed entry leg was killed "
    "(Entry-stack Amendment-3 #1747; DO_NOT_REBUILD §2) — this lane ranks nothing, "
    "gates nothing, sizes nothing. Per-name weekly-grain watch vocabulary on the house "
    "canon indicator; forward ledger ruler = 21d and 63d excess-vs-SPY from state entry; "
    "promotion only via a pre-registered gate after a matured cohort exists."
)

SCHEMA = "washout_turn.v1"

# ---------------------------------------------------------------------------
# Construction constants (FROZEN — amendments go through the program ruling)
# ---------------------------------------------------------------------------

#: Minimum COMPLETED weekly bars before a depth percentile is meaningful.
MIN_WEEKLY_BARS = 200

#: Depth gate — the weekly RSI-MACD line must sit in the bottom N% of the name's
#: own weekly line history for a cross to qualify as a WASHOUT turn.
DEPTH_PCTILE_MAX = 15.0

#: Consecutive negative-histogram bars after the cross that FAIL the attempt.
#: 2 means a SINGLE negative bar does not drop the state (1-bar hysteresis).
FAIL_HIST_BARS = 2

#: Minimum own-history events before base rates are summarised at all.
MIN_HISTORY_EVENTS = 8

#: Forward horizons for the own-history receipt, in completed weekly bars.
FWD_13W, FWD_26W = 13, 26

#: 52-week high lookback in daily sessions (drawdown receipt).
DD_LOOKBACK_SESSIONS = 252

STATE_TURN = "WASHOUT_TURN"
STATE_WATCH = "TURN_WATCH"
STATE_NONE = "NONE"

#: History-deepening stores, in preference order, as data_root-relative dirs.
#: data/stocks/ is the house deep store (MCD 1966→); data/yahoo/ is the last
#: resort (usually 2023→, but reaches 1999 for some names the stocks store
#: lacks).  Both are derived from data_root — unlike mtf_upturn._try_yahoo's
#: ROOT-pinned path — so a tmp data_root in tests never reads the real store
#: (prod is identical: config.data_dir() == ROOT/"data").
DEEPEN_STORES = ("stocks", "yahoo")

#: A deep store must actually REACH the preferred store's first bar for the
#: splice to engage.  A join across a longer hole would fabricate a multi-week
#: gap-jump bar inside the depth distribution; better to keep the shallow read
#: (which prints its own truncation via history_weeks / history_start).
MAX_SPLICE_GAP_DAYS = 14

#: Canon params actually consumed here — emitted in the artifact as an audit
#: trail so a param drift in canon is visible in the shipped JSON.
CANON_PARAMS = {
    "rsi_len": RSI_LEN,
    "conf_w": CONF_W,
    "ob": OB,
    "os": OS,
    "buy_rsi_max": BUY_RSI_MAX,
    "grid": "W-FRI completed bars",
}

# ---------------------------------------------------------------------------
# Ledger (data/washout_turn/ledger.jsonl) — nightly-only, transitions only
# ---------------------------------------------------------------------------

_LEDGER_DIR = "washout_turn"
_LEDGER_FILE = "ledger.jsonl"


def _ledger_path(data_root: Path | None = None) -> Path:
    from lib import config
    root = data_root if data_root is not None else config.data_dir()
    return root / _LEDGER_DIR / _LEDGER_FILE


def _load_ledger(data_root: Path | None = None) -> list[dict]:
    p = _ledger_path(data_root)
    if not p.exists():
        return []
    out: list[dict] = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def _write_ledger(rows: list[dict], data_root: Path | None = None) -> None:
    """Atomic tmp-file replace (mtf_upturn._write_ledger pattern)."""
    p = _ledger_path(data_root)
    p.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join(json.dumps(r, default=str) for r in rows)
    if content:
        content += "\n"
    fd, tmp_path = tempfile.mkstemp(dir=p.parent, prefix=".washout_turn_ledger_tmp_")
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(content)
        os.replace(tmp_path, p)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _load_prior_states(data_root: Path | None = None) -> dict[str, dict]:
    """Most recent ledger row per symbol → {symbol: {"state", "since"}}."""
    rows = _load_ledger(data_root)
    prior: dict[str, dict] = {}
    for row in reversed(rows):
        sym = row.get("symbol")
        if sym and sym not in prior:
            prior[sym] = {
                "state": row.get("state") or STATE_NONE,
                "since": row.get("since"),
            }
    return prior


def _stamp_ledger(transition_rows: list[dict], data_root: Path | None = None) -> int:
    """Append state-transition rows.  Nightly-only (COLLECT_LANE gate).

    Idempotent: keep-FIRST per (session, symbol) — a re-run in the same session
    never rewrites the row that already recorded the transition.
    """
    if not _ledger_advance_enabled():
        log.debug("washout_turn._stamp_ledger: skipped (COLLECT_LANE != nightly)")
        return 0
    if not transition_rows:
        return 0
    try:
        rows = _load_ledger(data_root)
        existing = {(r.get("symbol"), r.get("session")) for r in rows}
        appended = 0
        for t in transition_rows:
            key = (t.get("symbol"), t.get("session"))
            if key in existing:
                continue
            rows.append(t)
            existing.add(key)
            appended += 1
        if appended:
            _write_ledger(rows, data_root)
        return appended
    except Exception as e:  # noqa: BLE001
        log.warning("washout_turn._stamp_ledger failed: %s", e)
        return 0


# ---------------------------------------------------------------------------
# History-deepening splice (W2) — depth/base-rate legs only
# ---------------------------------------------------------------------------

def _load_store_close(path: Path) -> pd.Series | None:
    """One store parquet → clean close Series (mtf `_load_close` conventions)."""
    if not path.exists():
        return None
    try:
        df = pd.read_parquet(path)
        df.index = pd.to_datetime(df.index)
        col = "close" if "close" in df.columns else "close_price"
        s = pd.to_numeric(df[col], errors="coerce").dropna().sort_index()
        return s if len(s) else None
    except Exception:  # noqa: BLE001 — a broken deep store must never break the read
        return None


def _splice_prepend(preferred: pd.Series, deeper: pd.Series | None) -> pd.Series:
    """Prepend-only idempotent splice (the #4561 GOLD-heal shape).

    Only bars of ``deeper`` STRICTLY BEFORE ``preferred``'s first date are
    taken; every overlapping date keeps ``preferred``'s value and the recent
    end is never extended (data/yahoo/ runs a session or two PAST the ohlcv
    store — those trailing bars must not leak in).  The prepended segment is
    ratio-aligned at the boundary because the stores' split/dividend
    adjustment epochs differ (JPM: 0.45% level offset on the same dates); a
    raw prepend would fabricate a jump bar inside the depth distribution.

    Returns the ``preferred`` OBJECT ITSELF when nothing is prepended — the
    caller uses identity (`spliced is close`) as the no-deepening signal.
    Idempotent: splicing an already-spliced series prepends nothing new.
    """
    if deeper is None or preferred.empty or deeper.empty:
        return preferred
    d0 = preferred.index[0]
    old = deeper.loc[deeper.index < d0]
    if old.empty:
        return preferred
    if (d0 - old.index[-1]).days > MAX_SPLICE_GAP_DAYS:
        return preferred
    anchor = float(deeper.loc[d0]) if d0 in deeper.index else float(old.iloc[-1])
    p0 = float(preferred.iloc[0])
    if not (np.isfinite(anchor) and anchor > 0.0 and np.isfinite(p0) and p0 > 0.0):
        return preferred
    out = pd.concat([old * (p0 / anchor), preferred])
    # Disjoint by construction (old < d0 <= preferred); belt-and-braces only.
    if not out.index.is_monotonic_increasing or out.index.has_duplicates:
        out = out[~out.index.duplicated(keep="last")].sort_index()
    return out


def _deepen_close(sym: str, close: pd.Series, data_root: Path | None = None) -> pd.Series:
    """The deepened series for the DEPTH/BASE-RATE legs, or ``close`` itself.

    Tries DEEPEN_STORES in order; the first store that actually deepens (starts
    strictly earlier AND reaches the boundary) wins.  Never raises — any
    failure falls back to the preferred series unchanged.
    """
    try:
        if close is None or close.empty:
            return close
        from lib import config
        root = data_root if data_root is not None else config.data_dir()
        for store in DEEPEN_STORES:
            cand = _load_store_close(root / store / f"{sym}.parquet")
            if cand is None or cand.index[0] >= close.index[0]:
                continue
            spliced = _splice_prepend(close, cand)
            if spliced is not close:
                return spliced
        return close
    except Exception as e:  # noqa: BLE001 — deepening is a receipt upgrade, never a gate
        log.debug("washout_turn._deepen_close %s failed: %s", sym, e)
        return close


# ---------------------------------------------------------------------------
# PIT weekly grid
# ---------------------------------------------------------------------------

def _completed_weekly(close: pd.Series) -> pd.Series:
    """W-FRI resample with the PARTIAL trailing week dropped (PIT law).

    ``resample("W-FRI")`` labels every bucket with its FRIDAY.  When the series
    ends mid-week that label is in the FUTURE relative to the last traded
    session — an incomplete bar whose indicator values will still move.  Drop it.
    When the last daily bar IS the Friday, label == date and the bar is kept.
    """
    s = pd.to_numeric(close, errors="coerce").dropna().sort_index()
    if s.empty:
        return s
    wk = s.resample("W-FRI").last().dropna()
    if len(wk) and wk.index[-1].date() > s.index[-1].date():
        wk = wk.iloc[:-1]
    return wk


# ---------------------------------------------------------------------------
# Own-history base rates (descriptive receipt — printed with its n)
# ---------------------------------------------------------------------------

def _base_rates(wk_closes: np.ndarray, event_idx: list[int]) -> dict:
    """Forward 13w/26w medians + win rates over ALL qualifying crosses.

    ``n`` is the EVENT count (every qualifying cross in the series).  Immature
    (right-censored) events — those without a full forward window yet — are
    dropped from the medians and win rates; nothing is imputed.
    """
    n = len(event_idx)
    if n < MIN_HISTORY_EVENTS:
        return {
            "n": n,
            "reason": "insufficient_events",
            "med_13w": None,
            "med_26w": None,
            "win_13w": None,
            "win_26w": None,
        }
    total = len(wk_closes)

    def _fwd(h: int) -> np.ndarray:
        out = [
            wk_closes[j + h] / wk_closes[j] - 1.0
            for j in event_idx
            if j + h < total and np.isfinite(wk_closes[j]) and wk_closes[j] > 0
        ]
        arr = np.asarray(out, dtype=float)
        return arr[np.isfinite(arr)]

    f13, f26 = _fwd(FWD_13W), _fwd(FWD_26W)
    return {
        "n": n,
        "med_13w": (round(float(np.median(f13)) * 100.0, 1) if len(f13) else None),
        "med_26w": (round(float(np.median(f26)) * 100.0, 1) if len(f26) else None),
        "win_13w": (round(float((f13 > 0).mean()) * 100.0, 1) if len(f13) else None),
        "win_26w": (round(float((f26 > 0).mean()) * 100.0, 1) if len(f26) else None),
    }


# ---------------------------------------------------------------------------
# Per-symbol evaluation
# ---------------------------------------------------------------------------

def _evaluate(close: pd.Series, deep_close: pd.Series | None = None) -> dict:
    """Full per-symbol evaluation.

    Returns ``{"insufficient": bool, "state": str|None, "receipts": dict|None,
    "none_reason": str|None, "deepened": bool}``.  ``insufficient`` is the SKIP
    signal (too little weekly history to read a depth percentile at all) and is
    distinct from a clean no-state read.

    ``deep_close`` is the SAME series extended backward by ``_splice_prepend``
    (never a different store's recent values).  It feeds ONLY the depth
    percentile — wherever depth is read, including the qualification gate —
    and the own-history base rates; admission (MIN_WEEKLY_BARS), cross
    detection, the graduation/failure exits, watch momentum, and every
    last-bar indicator receipt evaluate the preferred ``close`` unchanged.
    When ``deep_close`` IS ``close`` (identity — the no-deepening signal from
    ``_deepen_close``) or is None, every leg reads the preferred grid and the
    result is byte-identical to a pre-W2 evaluation.
    """
    blank = {"insufficient": False, "state": None, "receipts": None,
             "none_reason": None, "deepened": False}

    wk = _completed_weekly(close)
    if len(wk) < MIN_WEEKLY_BARS:
        return {**blank, "insufficient": True}

    line_raw, sig_raw = rsi_macd(wk)
    ok = line_raw.notna() & sig_raw.notna()
    line, sig = line_raw[ok], sig_raw[ok]
    if len(line) < FWD_26W + 5:  # nothing meaningful to read after the warm-up
        return {**blank, "insufficient": True}
    hist = line - sig
    wk_on_line = wk.reindex(line.index)

    n_bars = len(line)
    line_vals = line.to_numpy(dtype=float)

    # ---- deep grid (W2): depth percentile + own-history base rates only ----
    dline, dsig, dwk = line, sig, wk
    if deep_close is not None and deep_close is not close:
        dwk_c = _completed_weekly(deep_close)
        dline_raw, dsig_raw = rsi_macd(dwk_c)
        dok = dline_raw.notna() & dsig_raw.notna()
        dline_c, dsig_c = dline_raw[dok], dsig_raw[dok]
        # The deep grid must COVER every preferred line bar (prepending bars
        # only moves the warm-up EARLIER, so it always does); anything else is
        # a malformed splice and the depth gate must not run on it.
        if len(dline_c) >= n_bars and line.index.isin(dline_c.index).all():
            dline, dsig, dwk = dline_c, dsig_c, dwk_c

    deepened = dline is not line
    dn = len(dline)
    dline_vals = dline.to_numpy(dtype=float) if deepened else line_vals
    # Preferred-grid bar i → deep-grid position (identity when not deepened).
    dpos = dline.index.get_indexer(line.index) if deepened else None

    def _depth_deep(j: int) -> float:
        """Percent of the FULL (deepened) weekly line history strictly BELOW
        deep-grid bar j — the whole-sample framing the evidence doc uses."""
        return 100.0 * float((dline_vals < dline_vals[j]).sum()) / dn

    def _depth(i: int) -> float:
        """Deep-grid depth percentile of PREFERRED-grid bar i."""
        return _depth_deep(int(dpos[i]) if deepened else i)

    macd_bull = crossover(line, sig)
    qual_idx = [
        i for i in range(n_bars)
        if bool(macd_bull.iloc[i]) and _depth(i) <= DEPTH_PCTILE_MAX
    ]

    # --- state machine -----------------------------------------------------
    state: str | None = None
    none_reason: str | None = None
    cross_i: int | None = None

    if qual_idx:
        c = qual_idx[-1]
        after_line = line_vals[c + 1:]
        after_hist = hist.to_numpy(dtype=float)[c + 1:]
        if len(after_line) and bool(np.nanmax(after_line) >= 0.0):
            # The line reclaimed zero — the turn GRADUATED; trend lenses own it.
            none_reason = "graduated"
        elif _has_consecutive_negative(after_hist, FAIL_HIST_BARS):
            # Two consecutive negative histogram bars — the attempt FAILED.
            # (A single negative bar is absorbed: built-in 1-bar hysteresis.)
            none_reason = "failed"
        else:
            state = STATE_TURN
            cross_i = c

    if state is None:
        # No LIVE qualifying cross — is the name still coiling at depth with a
        # strictly rising histogram?  (Deep base, momentum curling up.)
        h = hist.to_numpy(dtype=float)
        if (len(h) >= 3
                and _depth(n_bars - 1) <= DEPTH_PCTILE_MAX
                and np.isfinite(h[-1]) and h[-1] < 0.0
                and np.isfinite(h[-2]) and np.isfinite(h[-3])
                and h[-1] > h[-2] > h[-3]):
            state = STATE_WATCH
            none_reason = None

    if state is None:
        return {**blank, "none_reason": none_reason or "expired", "deepened": deepened}

    # --- receipts ----------------------------------------------------------
    k_raw, d_raw = stoch_rsi_kd(wk)
    k, d = k_raw.reindex(line.index), d_raw.reindex(line.index)
    r14 = rsi(wk, RSI_LEN).reindex(line.index)

    weekly_cb = False
    since_iso: str | None = None
    depth_at_cross: float | None = None
    weeks_since: int | None = None
    if cross_i is not None:
        since_iso = str(line.index[cross_i].date())
        depth_at_cross = round(_depth(cross_i), 1)
        weeks_since = int(n_bars - 1 - cross_i)
        weekly_cb = _weekly_cb_on_bar(line, sig, k, d, r14, cross_i)

    # Own-history base rates read the DEEP grid: every qualifying cross in the
    # full (deepened) line history, not just the preferred store's window.
    if deepened:
        dcross = crossover(dline, dsig)
        deep_qual = [
            j for j in range(dn)
            if bool(dcross.iloc[j]) and _depth_deep(j) <= DEPTH_PCTILE_MAX
        ]
        hist_events = _base_rates(
            dwk.reindex(dline.index).to_numpy(dtype=float), deep_qual)
    else:
        hist_events = _base_rates(wk_on_line.to_numpy(dtype=float), qual_idx)

    return {
        "insufficient": False,
        "state": state,
        "none_reason": None,
        "deepened": deepened,
        "receipts": {
            "state": state,
            "since": since_iso,
            "weeks_since_cross": weeks_since,
            "depth_pctile": round(_depth(n_bars - 1), 1),
            "depth_pctile_at_cross": depth_at_cross,
            "line": _r(line.iloc[-1], 3),
            "sig": _r(sig.iloc[-1], 3),
            "hist": _r(hist.iloc[-1], 3),
            "stoch_k": _r(k.iloc[-1], 1),
            "stoch_d": _r(d.iloc[-1], 1),
            "weekly_cb": bool(weekly_cb),
            "drawdown_pct": _drawdown_pct(close),
            "data_through": str(close.dropna().index[-1].date()),
            # WHICH history the percentile and the base rates were measured over.
            # A depth percentile is only as deep as the store behind it: MCD off
            # data/stocks (1966→) reads 6.3 with n=36; off data/baskets/ohlcv
            # (2014→) the SAME bar reads 8.6 with n=8.  W2 deepens these two legs
            # via the prepend-only splice, and the span printed here is the span
            # they were ACTUALLY measured over — a name whose deep store is
            # missing still discloses its truncation instead of hiding it.
            "history_weeks": int(dn),
            "history_start": str(dline.index[0].date()),
            "history": hist_events,
        },
    }


def _has_consecutive_negative(arr: np.ndarray, k: int) -> bool:
    """True when ``arr`` contains ``k`` CONSECUTIVE finite values < 0."""
    run = 0
    for v in arr:
        if np.isfinite(v) and v < 0.0:
            run += 1
            if run >= k:
                return True
        else:
            run = 0
    return False


def _weekly_cb_on_bar(
    line: pd.Series,
    sig: pd.Series,
    k: pd.Series,
    d: pd.Series,
    r14: pd.Series,
    i: int,
) -> bool:
    """The weekly-grid CB composition, exactly as ``canon.confluence_signals``
    composes it on its own grid (macd bull cross · recent StochRSI bull cross ·
    from-oversold · buy RSI regime), evaluated on weekly bar ``i``.

    Composition (canon.confluence_signals, buy side)::

        cb = macd_bull & (bars_since(stoch_bull) <= CONF_W)
                       & (d.rolling(CONF_W).min() < OS)
                       & (rsi14 < BUY_RSI_MAX)

    The 3D-grid version ORs the weekly confirm gate with `from oversold`; on the
    weekly grid itself there is no higher confirm TF to consult, so the
    from-oversold leg stands alone (the composition the evidence reproduction
    used).
    """
    try:
        macd_bull = crossover(line, sig)
        stoch_bull = crossover(k, d)
        recent_b1 = bars_since(stoch_bull) <= CONF_W
        from_os = d.rolling(CONF_W).min() < OS
        regime_ok = r14 < BUY_RSI_MAX
        return bool(
            bool(macd_bull.iloc[i])
            and bool(recent_b1.iloc[i])
            and bool(from_os.iloc[i])
            and bool(regime_ok.iloc[i])
        )
    except Exception as e:  # noqa: BLE001 — a receipt must never break the state
        log.debug("washout_turn._weekly_cb_on_bar failed: %s", e)
        return False


def _drawdown_pct(close: pd.Series) -> float | None:
    """Current close vs the trailing 52-week (252-session) max close, in percent."""
    try:
        s = pd.to_numeric(close, errors="coerce").dropna()
        if len(s) < 20:
            return None
        hi = s.rolling(DD_LOOKBACK_SESSIONS, min_periods=20).max().iloc[-1]
        if not np.isfinite(hi) or hi <= 0:
            return None
        return round((float(s.iloc[-1]) / float(hi) - 1.0) * 100.0, 1)
    except Exception:  # noqa: BLE001
        return None


def _r(v: Any, nd: int) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(f):
        return None
    return round(f, nd)


def compute_symbol_washout(
    close: pd.Series, deep_close: pd.Series | None = None,
) -> dict | None:
    """Pure per-symbol read → the receipts dict, or None when there is no state.

    ``None`` covers both "not enough weekly history" and "no washout turn / no
    deep-base watch right now" — a caller that needs to tell those apart uses
    ``_evaluate``.  Never raises on a well-formed close series.

    ``deep_close`` (optional) is a ``_splice_prepend``-shaped backward
    extension of ``close`` for the depth/base-rate legs.  Callers that already
    hold a deep-store series — scripts/build_stock_library feeds data/stocks/
    closes directly — pass nothing and are byte-identical to pre-W2.
    """
    res = _evaluate(close, deep_close)
    return res["receipts"] if res["state"] else None


# ---------------------------------------------------------------------------
# Full-universe compute
# ---------------------------------------------------------------------------

def compute(data_root: Path | None = None, as_of: str | None = None) -> dict:
    """Compute washout_turn.v1 for the full US universe.  Never raises."""
    try:
        return _compute_inner(data_root, as_of)
    except Exception as e:  # noqa: BLE001
        log.error("washout_turn.compute crashed: %s", e)
        return {
            "schema": SCHEMA,
            "as_of": as_of or date.today().isoformat(),
            "universe_n": 0,
            "skipped_n": 0,
            "deepened_n": 0,
            "elapsed_s": 0.0,
            "tickers": {},
            "cohort": {"turn": [], "watch": []},
            "authority": AUTHORITY,
            "tier": "display",
            "disclosure": DISCLOSURE,
            "canon_params": CANON_PARAMS,
            "error": str(e),
        }


def _compute_inner(data_root: Path | None, as_of: str | None) -> dict:
    t0 = time.time()

    universe = _build_universe(data_root)
    prior_states = _load_prior_states(data_root)

    universe_n = 0
    skipped_n = 0
    deepened_n = 0
    tickers_out: dict[str, Any] = {}
    transition_rows: list[dict] = []
    turn_list: list[str] = []
    watch_list: list[str] = []
    max_bar_date: str | None = None

    for sym, basket_ids in sorted(universe.items()):
        close = _load_close(sym, data_root)
        if close is None:
            skipped_n += 1
            continue

        try:
            res = _evaluate(close, _deepen_close(sym, close, data_root))
        except Exception as e:  # noqa: BLE001 — one bad name never kills the pass
            log.debug("washout_turn: %s evaluate failed: %s", sym, e)
            skipped_n += 1
            continue

        if res["insufficient"]:
            skipped_n += 1
            log.debug("washout_turn: skipped %s (<%d completed weekly bars)",
                      sym, MIN_WEEKLY_BARS)
            continue

        universe_n += 1
        deepened_n += 1 if res.get("deepened") else 0
        sym_asof = str(close.index[-1].date())
        if max_bar_date is None or sym_asof > max_bar_date:
            max_bar_date = sym_asof

        state = res["state"]
        receipts = res["receipts"] or {}
        prior = prior_states.get(sym) or {}
        prior_state = prior.get("state") or STATE_NONE
        cur_state = state or STATE_NONE

        if state == STATE_TURN:
            turn_list.append(sym)
        elif state == STATE_WATCH:
            watch_list.append(sym)

        if state:
            tickers_out[sym] = {**receipts, "basket_ids": basket_ids}

        # Transitions ONLY — a symbol whose state differs from its last ledger row.
        if cur_state != prior_state:
            transition_rows.append({
                "session": sym_asof,
                "symbol": sym,
                "state": cur_state,
                "prior_state": prior_state,
                "since": receipts.get("since"),
                "depth_pctile": receipts.get("depth_pctile"),
                "line": receipts.get("line"),
                "hist": receipts.get("hist"),
                "data_through": receipts.get("data_through", sym_asof),
                "reason": (res["none_reason"] if cur_state == STATE_NONE else None),
            })

    computed_asof = as_of
    if computed_asof is None:
        if max_bar_date is not None:
            computed_asof = max_bar_date
        else:
            log.warning("washout_turn: universe empty — falling back to date.today() for as_of")
            computed_asof = date.today().isoformat()

    _stamp_ledger(transition_rows, data_root)

    elapsed = time.time() - t0
    log.info(
        "washout_turn: universe=%d skipped=%d deepened=%d turn=%d watch=%d "
        "transitions=%d elapsed=%.1fs",
        universe_n, skipped_n, deepened_n, len(turn_list), len(watch_list),
        len(transition_rows), elapsed,
    )

    return {
        "schema": SCHEMA,
        "as_of": computed_asof,
        "universe_n": universe_n,
        "skipped_n": skipped_n,
        "deepened_n": deepened_n,
        "elapsed_s": round(elapsed, 2),
        "tickers": tickers_out,
        "cohort": {"turn": sorted(turn_list), "watch": sorted(watch_list)},
        "authority": AUTHORITY,
        "tier": "display",
        "disclosure": DISCLOSURE,
        "canon_params": CANON_PARAMS,
    }


# ---------------------------------------------------------------------------
# Site artifact writer
# ---------------------------------------------------------------------------

def write_site_artifact(result: dict, site_root: Path | None = None) -> Path:
    """Write site/stockdata/washout_turn.json.  Returns the written path."""
    from lib import config
    if site_root is None:
        site_root = config.ROOT / config.load()["storage"]["site_dir"]
    out_dir = site_root / "stockdata"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "washout_turn.json"

    payload = json.dumps(result, separators=(",", ":"), default=str)
    out_path.write_text(payload + "\n", encoding="utf-8")
    log.info("washout_turn: wrote %s (%dKB)", out_path, len(payload.encode()) // 1024)
    return out_path
