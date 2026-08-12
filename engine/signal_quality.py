"""MTF MACD-RSI × StochRSI confluence — validated buy-filter signal leaf.

DISPLAY-ONLY entry-QUALITY / RISK signal for the Mastermind brain + the chart.
NOT alpha, NOT a standalone strategy. See research/signal_engine/CHARTER.md for the
framing and the marker contract (§7). The buy-filter (reclaim-and-hold + bearish-
divergence veto + 200-day-MA as a confidence bar-raiser) cut average max drawdown
-23.7% -> -15.5% across 110 held-out US names (84% improved) — it is a drawdown tool.
That citation is a PRE-ERA measurement (start-anchored bins, 110 names). Re-run on the
238-name panel with everything held fixed except the bucket phase, the same construction
reads -24.7 -> -15.3, shallower on 82% (research/SIGNAL_QUALITY_SESSION_ANCHOR_ADJUDICATION_
BY_FABLE.md §Re-validation): the claim REPRODUCES under the absolute anchor. Both numbers
are quoted, neither is silently re-baked.

Faithful to the owner's `MACD STOCH RSI CONFLUENCE SIGNAL.pine`, run on the 3D:
  RSI-MACD : macd = EMA(RSI14,14) - EMA(RSI14,60); signal = EMA(macd,5)   (NOT price MACD)
  StochRSI : k = SMA(stoch(RSI14,14),3); d = SMA(k,3)

EXITS — the mechanical sell/cut stay the SIMPLE validated baseline (oscillator SELL* =>
`sell`; fast-reversal cut-loss => `cut`). A cross-sectional exit bake-off
(research/signal_engine/diagnose_v5_exits.py) tested Chandelier-ATR and close-below-EMA
trailing stops as REPLACEMENTS and they did NOT generalize: on the held-out US panel the
best (close<EMA8) improved drawdown on only ~58-69% of names and the joint drawdown-AND-
capture gate was ~37-43% — below the pre-committed 70%. So per the kill rule we ship the
simpler baseline (this echoes the CHARTER §5 killed regime-router: drawdown control is an
ENTRY problem, not an exit-routing one). The one robust finding: a close-below-EMA8 breach
is a TAIL-risk protector (rescues drawdown on 81-92% of the deepest-drawdown-quartile names
across two windows, at some capture cost). We surface it ONLY as a display-only `risk_flags`
date list + current `trail_breach`/`trail_stop` state fields — kept OUT of the validated
trade-marker stream, never an auto-sell, never per-ticker, never routed. EMA8 is CLOSE-ONLY
by construction, so the flag needs no high/low and works identically on the close-only names
(Tencent 0700.HK, BABA) — that, plus simplicity and the better tail, is why we chose it over
a high/low Chandelier ATR.
"""
from __future__ import annotations

import json
from functools import lru_cache
from typing import NamedTuple

import numpy as np
import pandas as pd

from engine import session_anchor   # the ONE absolute session calendar (R-SQ1)
from engine.technicals import rsi   # Wilder RSI, matches Pine ta.rsi

#: The bucketing era every §7 marker below was drawn under (R-SQ3). The 2D/3D grids are
#: anchored to an ABSOLUTE session calendar (``engine/session_anchor``), never to the
#: caller's slice: ``bucket(d) = session_positions(d, market) // n``, labelled by the
#: bucket's OPEN date. Before 2026-08-06 these were pandas ``2B``/``3B`` bins phased to
#: the SERIES' FIRST timestamp, so the four production history depths that reach ``gate()``
#: each read a DIFFERENT marker stream for the same name (measured on the 2026-08-06 tape:
#: one dropped leading bar moved 238/238 data/stocks last-marker dates, changed 91 marker
#: IDENTITIES, flipped 95 tick counts, 11 gate eligibilities and 3 final buy verdicts).
#: Ruling: research/SIGNAL_QUALITY_SESSION_ANCHOR_ADJUDICATION_BY_FABLE.md; measured
#: blast radius: reports/sq_anchor_blast_radius.md. It is a SEPARATE era from the
#: cascade's ``confluence_tiers.ANCHOR_ERA`` — a verdict is jointly produced by two
#: bucketing grids and a graded row must be able to place itself against BOTH.
ANCHOR_ERA = "sq-abs-session-2026-08-06"

RSI_LEN, FAST_LEN, BASE_LEN, SIG_LEN = 14, 14, 60, 5
STOCH_LEN, SMOOTH_K, SMOOTH_D = 14, 3, 3
OB, OS = 80, 20
CONF_W, BUY_RSI_MAX, EXT_RSI, REV_BARS = 8, 65, 70, 3
MA_LEN = 200
TRAIL_SPAN = 8   # 3D close-below-EMA8 trailing trend — the display-only tail-risk flag (see below)


def _ema(s, span):
    return s.ewm(span=span, min_periods=span).mean()


def _rsi_macd(c):
    r = rsi(c, RSI_LEN)
    macd = _ema(r, FAST_LEN) - _ema(r, BASE_LEN)
    return macd, _ema(macd, SIG_LEN)


def _stoch_rsi_kd(c):
    r = rsi(c, RSI_LEN)
    lo, hi = r.rolling(STOCH_LEN).min(), r.rolling(STOCH_LEN).max()
    rawk = (r - lo) / (hi - lo).replace(0, np.nan) * 100
    k = rawk.rolling(SMOOTH_K).mean()
    return k, k.rolling(SMOOTH_D).mean()


def _xup(a, b):
    return (a > b) & (a.shift(1) <= b.shift(1))


def _xdn(a, b):
    return (a < b) & (a.shift(1) >= b.shift(1))


def _since(cond):
    pos = np.arange(len(cond))
    last = pd.Series(np.where(cond.to_numpy(), pos, np.nan), index=cond.index).ffill()
    return pd.Series(pos, index=cond.index) - last


class _Grid(NamedTuple):
    """One n-session timeframe grid cut on the ABSOLUTE session calendar (R-SQ1/R-SQ2)."""
    close: pd.Series          #: bucket close (its LAST finite close), indexed by the OPEN-date label
    last_session: pd.Series   #: the bucket's last session that carried a close, same index
    bucket: pd.Series         #: per-daily-row bucket id, indexed by the working daily index
    label: pd.Series          #: bucket id -> OPEN-date label (buckets with a finite close only)
    index: pd.DatetimeIndex   #: the working daily index (sorted, de-duplicated)


def _tf_grid(daily: pd.Series, n: int, market: str = "US") -> _Grid:
    """The n-session grid every §7 timeframe is cut on, anchored ABSOLUTELY (R-SQ1/R-SQ2).

    ``bucket(d) = session_anchor.session_positions(d, market) // n`` — a function of
    ``(reference calendar, date)`` alone, so the grid is IDENTICAL no matter how much
    leading history the caller handed in. That is the whole repair: the retired pandas
    ``3B`` resample anchored its bin edges to the SERIES' FIRST timestamp, so the four
    production history
    depths that reach ``gate()`` each read a different §7 marker stream for the same name,
    and the business-day bins additionally MIS-SPLIT every bucket spanning a market holiday
    (the defect ``engine/canon.py::resample_sessions`` records as relocating ~80% of NVDA
    signal dates). Ruling: research/SIGNAL_QUALITY_SESSION_ANCHOR_ADJUDICATION_BY_FABLE.md.

    LABELS ARE OPEN DATES (R-SQ2): a bucket is stamped with the FIRST session in it that
    carried a close, so a §7 marker date is always a real traded bar of THIS series. The
    old bin labels were pandas' synthetic left edges and could land on a holiday, which is
    why the charter's "Dates are 3D bar dates" was only approximately true. Known-date
    labels (the ``confluence_tiers._tf_bars`` internal convention) were REJECTED here: §7
    labels are the PUBLIC contract, and moving them would silently age every take by a tick.

    Returns the bucket ``close`` and ``last_session`` indexed by that label, PLUS the
    per-row ``bucket`` ids and the ``label`` map — so a caller aggregating a SECOND series
    (the high/low band) cuts it on exactly these buckets instead of re-deriving a grid that
    could disagree. One vectorized groupby; no Python-per-bucket loop on the hot path.
    """
    s = daily
    if not s.index.is_monotonic_increasing:
        s = s.sort_index()                       # resample used to sort; keep that contract
    s = s[~s.index.duplicated(keep="last")]
    idx = s.index if isinstance(s.index, pd.DatetimeIndex) else pd.DatetimeIndex(
        pd.to_datetime(s.index))
    empty_v = pd.Series(dtype="float64")
    empty_d = pd.Series(dtype="datetime64[ns]")
    if len(idx) == 0:
        return _Grid(empty_v, empty_d, pd.Series(dtype="int64"), empty_d, idx)
    b = pd.Series(session_anchor.session_positions(idx, market) // n, index=idx)
    # ``.dropna()`` on the old resample result dropped ALL-NaN buckets and nothing else,
    # and ``.last()`` skipped NaN within a bucket — both preserved by filtering here.
    ok = s.notna().to_numpy()
    if not ok.any():
        return _Grid(empty_v, empty_d, b, empty_d, idx)
    agg = (pd.DataFrame({"v": s.to_numpy()[ok], "d": idx.to_numpy()[ok]})
           .groupby(b.to_numpy()[ok], sort=True)
           .agg(close=("v", "last"), open_date=("d", "first"), last_session=("d", "last")))
    labels = pd.DatetimeIndex(agg["open_date"])
    return _Grid(pd.Series(agg["close"].to_numpy(), index=labels),
                 pd.Series(pd.DatetimeIndex(agg["last_session"]), index=labels),
                 b, pd.Series(labels, index=agg.index), idx)


def signal_frame(daily_close: pd.Series, daily_high: pd.Series | None = None,
                 daily_low: pd.Series | None = None, *,
                 market: str = "US") -> pd.DataFrame:
    """3D confluence signals (CB/CS/revBuy/revSell) + regime gates, leak-free.

    Every confluence value stays CLOSE-driven (faithful to the owner's Pine source).
    If a daily ``high``/``low`` is supplied — true OHLC for US deep names, or a
    conservative reconstruction for close-only names (engine.ohlc_reconstruct) — it
    is bucketed onto the 3D grid (high=max, low=min over each bucket) and exposed
    as ``high``/``low`` so swing-high & bearish-divergence can read intrabar extremes.
    With NO high/low given, ``high``/``low`` collapse to ``close`` — i.e. the original
    close-only behaviour is preserved EXACTLY (the validated buy-filter default).

    ``market`` picks the reference session calendar the 2D/3D buckets are anchored to
    (:func:`_tf_grid`, R-SQ1). US default; :func:`analyze` infers it from its own ticker
    and ``hk_board_rank`` passes HK, so no board caller needs an edit. The W-FRI weekly
    leg is calendar-absolute already and is deliberately untouched (R-SQ6)."""
    grid3 = _tf_grid(daily_close, 3, market)
    s3 = grid3.close
    if len(s3) < 90:
        return pd.DataFrame()
    macd, sig = _rsi_macd(s3)
    k, d = _stoch_rsi_kd(s3)
    r14 = rsi(s3, RSI_LEN)
    sb, ss = _xup(k, d), _xdn(k, d)
    mb, ms = _xup(macd, sig), _xdn(macd, sig)
    wk = daily_close.resample("W-FRI").last().dropna()
    wm, wsg = _rsi_macd(wk)
    wbull = (wm >= wsg).shift(1).reindex(s3.index, method="ffill").fillna(False).astype(bool)
    ma = daily_close.rolling(MA_LEN).mean()
    above = (s3 > ma.reindex(s3.index).ffill()).fillna(False)
    ema_trail = s3.ewm(span=TRAIL_SPAN, min_periods=TRAIL_SPAN).mean()   # close-only; no high/low
    b1os, s1ob = d.rolling(CONF_W).min() < OS, d.rolling(CONF_W).max() > OB
    cb = (mb & (_since(sb) <= CONF_W) & (wbull | b1os) & (r14 < BUY_RSI_MAX)).fillna(False)
    rext = (k.rolling(CONF_W).max() >= OB) | (r14.rolling(CONF_W).max() >= EXT_RSI)
    cs = (ms & (_since(ss) <= CONF_W) & ((~wbull) | s1ob) & rext).fillna(False)
    revsell = (ms & (_since(cb) <= REV_BARS)).fillna(False)
    revbuy = (mb & (_since(cs) <= REV_BARS)).fillna(False)
    # ---- DISPLAY-ONLY early-anticipation leg (the 2D-MACD pre-cross advance warning) ----
    # Validated as m2d_s3d_early (research/signal_engine/CONFLUENCE_TUNING.md §3): the 3D
    # StochRSI bottom-turn (from oversold) WHILE the faster 2D RSI-MACD histogram is only
    # RISING (pre-cross) fires ~5 trading days BEFORE the confirmed CB and enters ~2% cheaper.
    # It does NOT improve drawdown/location out-of-sample (acting early is empirically WORSE
    # entry quality — deeper drawdown, the §5b guard avenue could not fix it), so it is surfaced
    # ONLY as a display-only advance-warning, NEVER scored, NEVER auto-traded, NEVER a buy
    # `quality`. Leak-free: 2D histogram uses the prior CLOSED 2D bar (.shift(1), no repaint).
    s2 = _tf_grid(daily_close, 2, market).close
    m2, sg2 = _rsi_macd(s2)
    hist2 = m2 - sg2
    rising2 = ((hist2 > hist2.shift(1)) & (hist2.shift(1) > hist2.shift(2))).shift(1)
    rising2_on3 = rising2.reindex(s3.index, method="ffill").fillna(False).astype(bool)
    early = (sb & b1os & rising2_on3 & (wbull | b1os) & (r14 < BUY_RSI_MAX)).fillna(False)
    if daily_high is not None and daily_low is not None:
        # The band is cut on grid3's OWN bucket ids — the same session positions that made
        # the close — so an anchor mismatch between the band and the close is now
        # STRUCTURALLY impossible. The old code aligned high/low onto the close's daily
        # index first and re-resampled, a precaution against a leading-NaN/short high|low
        # phasing its own "3B" bins differently and silently collapsing the band back to
        # close; the reindex stays (the inputs may still carry a different index), the
        # second bucketing is gone.
        hl = pd.DataFrame({"high": daily_high, "low": daily_low}).reindex(grid3.index)
        band = (hl.groupby(grid3.bucket.to_numpy(), sort=True)
                .agg({"high": "max", "low": "min"}).reindex(grid3.label.index))
        h3 = pd.Series(band["high"].to_numpy(), index=s3.index)
        l3 = pd.Series(band["low"].to_numpy(), index=s3.index)
        h3 = pd.concat([h3, s3], axis=1).max(axis=1)   # 3D high never below its close
        l3 = pd.concat([l3, s3], axis=1).min(axis=1)   # 3D low never above its close
    else:
        h3 = l3 = s3
    return pd.DataFrame({"close": s3, "high": h3, "low": l3,
                         "macd": macd, "sig": sig, "k": k, "d": d, "rsi14": r14,
                         "CB": cb, "CS": cs, "revBuy": revbuy, "revSell": revsell,
                         "w_bull": wbull, "above200": above, "ema_trail": ema_trail,
                         "early": early})


def fresh_breach_mask(daily_close: pd.Series, *, market: str = "US") -> pd.Series:
    """Return a boolean Series (3D-bucket-indexed) of fresh EMA8 breaches.

    A 'fresh breach' fires on the 3D bar where:
      (1) close < ema_trail  (below)
      (2) previous 3D bar was NOT below (first time under)
      (3) ema_trail was rising into the breach (slope: bar-1 > bar-3)

    The result index is :func:`_tf_grid`'s OPEN-date labels — the first TRADED session of
    each bucket, so every breach date IS a daily bar of this series and a membership test
    against the daily index always resolves.  (Pre-``sq-abs-session-2026-08-06`` it was the
    retired ``3B`` bin's synthetic LEFT edge, which could be a holiday and belonged to
    no series at all.)  Reindex to a daily index with method='ffill' to carry a breach
    forward across the bucket.

    ``market`` picks the reference session calendar (R-SQ1); see :func:`signal_frame`.

    This is the canonical single source of truth for the fresh_breach
    construction used by both analyze() and dump_breakdown_events.py.
    """
    sf = signal_frame(daily_close, market=market)
    if sf.empty:
        return pd.Series(dtype=bool)
    trail = sf["ema_trail"]
    c = sf["close"]
    below = c < trail
    prev_below = below.shift(1, fill_value=False)
    rising_into = (trail.shift(1) > trail.shift(3))
    return (below & ~prev_below & rising_into).fillna(False)


def _swing_highs(s, w=2):
    v = s.to_numpy()
    return [i for i in range(w, len(v) - w) if v[i] == v[i - w:i + w + 1].max()]


def _bear_div(i, price, macd, hi, look=12):
    """Bearish divergence: price prints a HIGHER swing-high while the RSI-MACD prints
    a LOWER one. ``price`` is the 3D HIGH when available (true OHLC / reconstruction),
    else the close; MACD stays close-based (faithful to the Pine confluence)."""
    pv, mv = price.to_numpy(), macd.to_numpy()
    rh = [h for h in hi if i - look < h <= i]
    return len(rh) >= 2 and pv[rh[-1]] > pv[rh[-2]] and mv[rh[-1]] < mv[rh[-2]]


BEAR_DIV_REASON = "veto: bearish divergence"
# A block reason must name the leg that was EVALUATED and FAILED — no more, no less.
# Corrected 2026-08-04 (research/cn_prophet_audit/CN_RECLAIM_HOLD_AUDIT.md §10/§11): the two
# shipped strings below described tests that had not run.
#   * The main branch (a name NOT both below-200 and weekly-down) resolves on ``held`` ALONE,
#     yet emitted "failed reclaim-and-hold" — 1,094 blocks in the audit year named a reclaim
#     that was never evaluated, on names that may never have been near their 200-day line.
#     002155.SZ sat 5.2% ABOVE its 200-day mean at its buy bar: its binding leg is the HOLD.
#     It now emits HOLD_FAIL — the SAME literal the reclaim_veto=False branch already used for
#     the identical one-test outcome, so no new vocabulary and no new plain-word copy.
#   * The counter-trend branch tests TWO legs and collapsed all three failure shapes into one
#     string, so a row reading "no 200-reclaim" was actually relieved by dropping the reclaim
#     rule only 40.2% of the time (639 of 1,590; 922 failed both, 29 failed the hold only).
#     The legacy string is now kept ONLY where both legs genuinely failed.
# Same defect family as the first-match masking `gate_reasons` fixes, from the other side of
# the filter: the label named a leg, just not the one doing the work.
HOLD_FAIL = "failed next-bar hold"
CT_BOTH_FAIL = "counter-trend, no 200-reclaim/hold"       # legacy — both legs tested, both fail
CT_RECLAIM_FAIL = "counter-trend, held but no 200-reclaim"
CT_HOLD_FAIL = "counter-trend, reclaimed 200 but no next-bar hold"

# The one reason the RATIFIED waiver below adds.  It is a FIXED literal, not an f-string:
# `site/chart.js`'s REASON_ZH is an exact-key map whose miss path renders the raw ENGLISH
# string to a Chinese reader (tests/test_gate_reasons_exhaustive.py::
# TestEveryEmittedReasonStaysBilingual is the guard), so a per-name reason carrying the
# group id and the peer drawdown could never be translated — and `gold_miners` / `-0.272065`
# / `us_prophet_v2` are a raw slug, an untranslated stat and an internal era name, the three
# things docs/DESIGN_DOCTRINE.md bans from rendered copy.  The receipt those numbers belong
# in rides on the GATE VERDICT instead (`engine.signal_gate.gate()["waiver"]`), which no page
# renders and every audit can read.
#
# AND IT IS DELIBERATELY NOT NAMED `CT_*`.  That prefix is a load-bearing convention, not a
# style: `engine.china_continuation_watch` selects its whole cohort from the counter-trend
# BLOCK family, and `tests/test_china_continuation_watch.py` enforces the set equality
# `{every CT_* constant} == {the three strings the filter's block branches emit}` so a fourth
# block shape added upstream reds there instead of going unswept.  This string is a TAKE.
# Prefixing it `CT_` would have quietly enrolled an admission in a block sweep.
RECLAIM_WAIVED = "counter-trend, reclaim waived (basket washout)"


# --------------------------------------------------------------------------- #
# The ratified counter-trend RECLAIM WAIVER — Arm P, `us_prophet_v2`
# --------------------------------------------------------------------------- #
# WHAT THIS IS.  `research/RECLAIM_VETO_CONDITIONAL_PREREG.md` (family
# `reclaim_veto_conditional_v1`) §4 Arm P, ADJUDICATED §5 2026-08-10 and RATIFIED the same
# day, with the notch moved to 20% family-wide by the operator in the §5 entry "NOTCH MOVED
# TO 20% FAMILY-WIDE".  It is the single revival path
# `research/prophet_us_audit/RECLAIM_VETO_PACKET_2026-08-05.md` §9 left open for this leg
# (`DNR:KILL-200DMA-RECLAIM-VETO-FLAT` — a flat drop stays killed; a REGIME-CONDITIONAL
# relaxation behind its own prereg and era stamp is the named exception).
#
# WHAT IT DOES, EXACTLY.  For a US name whose basket peers are themselves washed out, the
# counter-trend 200-day RECLAIM leg is waived.  The HOLD leg is NOT: `CT_HOLD_FAIL` and
# `CT_BOTH_FAIL` are byte-identical to v1 under every state, and only the pure
# `CT_RECLAIM_FAIL` branch — held passed, reclaim failed — can convert to a take.  That is
# the boundary §5 drew and named: the motivating exemplar HL 2026-06-16 is a hold-leg
# failure, "the basket state admits it but this construction cannot", and hold-leg
# relaxation is a different construction needing its own prereg.  Do not widen this branch.
#
# EVIDENCE AT THE SHIPPED NOTCH (`research/reclaim_veto_study/arm_p_faithful.json`,
# grid["0.20"], faithful packet path `sq.analyze` on/off): capped-R +1.165 on 832 fires /
# 600 names, episode-clustered CI [0.123, 2.527] over 21 episodes, name-clustered CI
# [0.924, 1.412], equal-date +0.304 CI [0.017, 0.614], difference-vs-complement CI
# [0.861, 1.481], ex-COVID +0.554 (= the leave-one-episode-out minimum), fire-weighted
# coverage 75.6% against the §3 floor of 60%.  Coverage gate: NEM's 2026-07-23 refusal
# carries peer_dd −0.378 and admits.
#
# WHY THE ERA STAMP MOVED.  An admission change makes the old and the new board two
# different products, so `engine.us_board_rank.BOARD_DEFINITION` goes `us_prophet_v1` ->
# `us_prophet_v2` in the same PR and the forward ledgers never pool — the fence the packet
# §7 specified and `hk_prophet_v2` (#4470) set the pattern for.

#: The nightly artifact this waiver reads, written out as ONE literal.
#: `scripts/check_synapse_reads.py` is a literal-path scan — a path assembled from
#: fragments is invisible to it — and this module is the declared consumer of
#: `site-basket-washout-state` in config/synapse.yml.
WASHOUT_STATE_PATH = "site/factordata/basket_washout_state.json"
WASHOUT_STATE_SCHEMA = "basket_washout_state.v1"

#: The ratified notch, as the STRING key the artifact publishes under `qualifies` — never a
#: number we re-derive.  `scripts/build_basket_washout_state._qualifies` computes the flag
#: from the PUBLISHED (rounded) `peer_dd`, precisely so a consumer that re-derived
#: `peer_dd <= -0.20` could not disagree with the producer on a boundary name.  Read the
#: flag.  25 was the §5 adjudication's recommendation; the operator moved the whole family
#: (blocked-entry override AND both reclaim arms) to 20 on 2026-08-10.  Arm P passed every
#: frozen gate at 20, 25 and 30 — this is a dial position, not a fresh construction.
WASHOUT_NOTCH = "20"

#: PIT staleness ceiling, counted in the NAME'S OWN trading sessions between the artifact's
#: `as_of` and the date the marker's label became knowable.
#:
#: NIGHTLY ORDERING (checked 2026-08-10, `.github/workflows/daily.yml`): `basket_washout`
#: builds inside the `cl_baskets` cluster of the "regional + desk builders" step, which runs
#: LATE — after "MTF buy-filter signals" (this module's own nightly), after the engine-core
#: step that runs `build_site` -> `build_stock_library`, and after "Prophet nightly".  So
#: every US consumer of this waiver reads the PRIOR night's artifact: on a healthy night
#: `stale_sessions == 1`.  Both orderings are PIT-safe and this is the stricter of the two —
#: the state is a published fact of a session that had already closed — but it is also the
#: reason the ceiling is 5 rather than 1: a skipped or failed `basket_washout` night must
#: degrade to "the peers were washed out as of Friday", not to a hard outage, and a long
#: weekend plus one bad night is 4 sessions.  Past 5 the state no longer describes the tape
#: the fire is firing into and the leg reverts to v1 (veto intact).
WASHOUT_MAX_STALE_SESSIONS = 5


class ReclaimWaiver(NamedTuple):
    """The receipt for one waived counter-trend reclaim leg.

    Never rendered: every field here is a raw slug, an untranslated stat or an internal era
    name.  It is published on the GATE VERDICT (`engine.signal_gate.gate()["waiver"]`) and
    deliberately NOT on the §7 marker, whose schema is closed and cross-repo — see the note
    beside `markers.append` in :func:`analyze`.  It exists so a graded row can prove WHICH
    state relieved it and HOW OLD that state was, which is the whole audit surface of an
    admission change.
    """
    group_id: str        #: the peer group the name read through (basket id or GICS sector)
    basis: str           #: "basket" | "sector" — which map answered
    peer_dd: float       #: the LEAVE-ONE-OUT peer median 252-session drawdown
    as_of: str           #: the artifact's own as_of — the PIT stamp of the state
    notch: str           #: the qualifying notch, as published ("20")
    stale_sessions: int  #: sessions between `as_of` and the label's knowable date


def _washout_state_file() -> "Path":
    """Absolute path of :data:`WASHOUT_STATE_PATH`, resolved through ``lib.config`` so a
    relocated site dir is followed, with a repo-relative fallback for a bare checkout."""
    from pathlib import Path
    try:
        from lib import config
        return Path(config.site_dir()) / "factordata" / "basket_washout_state.json"
    except Exception:                                              # noqa: BLE001
        return Path(__file__).resolve().parent.parent / WASHOUT_STATE_PATH


@lru_cache(maxsize=4)
def _load_washout_state(path_str: str) -> dict | None:
    """Parse the artifact once per process.  ``None`` on ANY doubt — absent, unreadable,
    wrong schema, no `as_of`, no `names` — because every such answer must land the leg back
    on its v1 behaviour rather than on a guess.  `analyze` runs this across the whole US
    panel in one process, so the parse is cached; tests call
    :func:`reset_washout_state_cache` after rewriting a fixture."""
    from pathlib import Path
    try:
        raw = json.loads(Path(path_str).read_text())
    except Exception:                                              # noqa: BLE001
        return None
    if not isinstance(raw, dict) or raw.get("schema") != WASHOUT_STATE_SCHEMA:
        return None
    if not isinstance(raw.get("names"), dict) or not isinstance(raw.get("as_of"), str):
        return None
    return raw


def reset_washout_state_cache() -> None:
    """Drop the parsed-artifact cache (tests; a long-lived service that re-reads nightly)."""
    _load_washout_state.cache_clear()


def washout_state() -> dict | None:
    """The nightly basket-washout state, or ``None`` when it cannot be trusted."""
    return _load_washout_state(str(_washout_state_file()))


def washout_qualifier(ticker: str, *, state: dict | None = None) -> dict | None:
    """The name's qualifying record at :data:`WASHOUT_NOTCH`, or ``None``.

    Name-level only — it answers "could this name ever be waived tonight", never "is this
    BAR waived", which is :func:`reclaim_waiver_for`'s PIT question.  Split so `analyze` can
    do the dict work once per ticker instead of once per marker.

    FENCED TO THE US TAPE.  Arm P is the Prophet US arm; prereg §1 puts CN/HK names out of
    scope outright ("no CN/HK basket-washout state exists; their arms require their own
    construction").  The `names` map is a US universe and would not claim `600547.SS` or
    `0700.HK` anyway, but an accidental symbol collision must not be the only thing standing
    between a CN board and an unratified admission change, so the market is checked first.
    """
    if session_anchor.market_for_ticker(ticker) != "US":
        return None
    st = washout_state() if state is None else state
    if not st:
        return None
    rec = st.get("names", {}).get(str(ticker or "").strip().upper())
    if not isinstance(rec, dict):
        return None
    if not bool((rec.get("qualifies") or {}).get(WASHOUT_NOTCH)):
        return None
    peer_dd, as_of = rec.get("peer_dd"), st.get("as_of")
    if not isinstance(peer_dd, (int, float)) or not isinstance(as_of, str):
        return None
    return {"group_id": str(rec.get("group_id") or "?"),
            "basis": str(rec.get("basis") or "?"),
            "peer_dd": float(peer_dd), "as_of": as_of}


def _sessions_since(session_index, as_of: str, known: str) -> int | None:
    """Sessions in ``session_index`` strictly after ``as_of`` up to and including ``known``.

    Counted on the NAME'S OWN calendar rather than in calendar days, so a holiday week and
    a halted name both read honestly.  ``None`` when either stamp will not parse or the
    index is unusable — an unanswerable staleness question is a refusal, not a zero.
    """
    try:
        idx = pd.DatetimeIndex(session_index)
        a, k = pd.Timestamp(as_of), pd.Timestamp(known)
    except Exception:                                              # noqa: BLE001
        return None
    if len(idx) == 0 or pd.isna(a) or pd.isna(k):
        return None
    return int(idx.searchsorted(k, side="right") - idx.searchsorted(a, side="right"))


def reclaim_waiver_for(qualifier: dict | None, known_date: str | None,
                       session_index) -> ReclaimWaiver | None:
    """The PIT half: does tonight's state legitimately reach THIS marker?

    ``known_date`` is the first close at which the `_buy_filter` label was knowable — the
    marker's `confirmed_date`, :data:`CONFIRM_BARS` buckets past the fire — which is the
    "fire's known date" prereg §2 pinned the state to.  Two conditions, both fail-closed:

      * ``as_of <= known_date``.  A state published AFTER the label was knowable is future
        information; it may never relieve that label.  This is what keeps a re-scan of
        history honest — an old fire is not retroactively waived by tonight's washout, so
        the marker stream a rebuild produces cannot drift under the artifact.
      * ``known_date - as_of <= WASHOUT_MAX_STALE_SESSIONS``.  See that constant.
    """
    if qualifier is None or not known_date:
        return None
    stale = _sessions_since(session_index, qualifier["as_of"], known_date)
    if stale is None or stale < 0 or stale > WASHOUT_MAX_STALE_SESSIONS:
        return None
    return ReclaimWaiver(group_id=qualifier["group_id"], basis=qualifier["basis"],
                         peer_dd=qualifier["peer_dd"], as_of=qualifier["as_of"],
                         notch=WASHOUT_NOTCH, stale_sessions=stale)


def _confirm_legs(i, sig, n, *, reclaim_veto: bool = True, waiver: ReclaimWaiver | None = None):
    """The post-divergence CONFIRMATION legs of :func:`_buy_filter` — the next-bar hold plus,
    for a name that is BOTH below its 200-day average and weekly-down under ``reclaim_veto``,
    the 2-bar 200-day reclaim. Returns (take: bool|None, reason).

    SPLIT OUT FOR ONE REASON: so :func:`_buy_filter_full` can still evaluate these legs after
    the bearish-divergence veto has already decided the verdict, and report an EXHAUSTIVE
    account instead of a first-match label. It carries no policy of its own and has no other
    caller. Every ``take`` value it returns is identical to the pre-split filter's; only the
    failure STRINGS were corrected to name the leg each branch actually tested (see above).

    ``waiver`` (default ``None`` = the v1 policy, byte-identical) is the resolved
    :class:`ReclaimWaiver` receipt for THIS bar.  It is resolved by the caller — all of the
    artifact I/O and the PIT arithmetic live in :func:`analyze`, none of it here — and it
    reaches exactly ONE branch below.
    """
    c, a = sig["close"], sig["above200"]
    if i + 1 >= n:
        return None, "pending confirmation"
    held = bool(c.iloc[i + 1] > c.iloc[i])
    below, wkdn = (not bool(a.iloc[i])), (not bool(sig["w_bull"].iloc[i]))
    if below and wkdn:
        if reclaim_veto:
            if i + 2 >= n:
                return None, "pending confirmation"
            reclaim = bool(a.iloc[i + 1]) or bool(a.iloc[i + 2])
            ok = held and reclaim
            if ok:
                return True, "reclaimed 200 & held"
            # BOTH legs ran here, so the reason names whichever of them actually refused.
            if not held and not reclaim:
                return False, CT_BOTH_FAIL
            if not held:
                return False, CT_HOLD_FAIL
            # The PURE reclaim failure — the hold leg PASSED and only the 2-bar reclaim
            # refused.  This branch, and nothing else, is what the ratified waiver converts.
            if waiver is not None:
                return True, RECLAIM_WAIVED
            return False, CT_RECLAIM_FAIL
        # reclaim_veto=False: the counter-trend branch keeps the SAME next-bar
        # follow-through every other name gets, and nothing else. Reason strings stay
        # accurate — no reclaim was tested, so neither outcome may mention one.
        return held, ("held confirmation (counter-trend)" if held else HOLD_FAIL)
    # The MAIN branch. One test — ``held`` — and no reclaim anywhere in it.
    return held, ("held confirmation" if held else HOLD_FAIL)


def _buy_filter_full(i, sig, bear, n, *, reclaim_veto: bool = True,
                     waiver: ReclaimWaiver | None = None):
    """(take, reason, reasons) — the buy-filter verdict PLUS the EXHAUSTIVE ordered account.

    ``take`` and ``reason`` are the SAME first-match values :func:`_buy_filter` returns, and
    admission is untouched: when ``bear`` is False this is the original code path verbatim, and
    when ``bear`` is True the verdict is still the hardcoded (False, veto) it always was.

    ``reasons`` is the ordered list of every leg outcome that is not a clean pass, evaluated in
    EVALUATION ORDER, with ``reasons[0]`` byte-identical to ``reason`` always. It exists because
    ``reason`` is a FIRST-MATCH LABEL, not an account: the bearish-divergence veto returns before
    the reclaim/hold legs are ever tested, so a name blocked twice over reads as blocked once.
    That ambiguity sent an operator and a full audit down the wrong lever — 湖南黄金 002155.SZ
    shipped ``buy blocked by filter: veto: bearish divergence`` while ALSO failing reclaim-and-hold,
    and 575 of 743 vetoed fires (77%) were blocked by another leg anyway
    (``research/cn_prophet_audit/CN_DIVERGENCE_VETO_AUDIT.md`` §Case receipt, recommendation 2).

    The divergence veto is the ONLY short-circuiting leg — the confirmation legs are terminal —
    so the extra evaluation runs on vetoed bars only, and costs the same handful of scalar
    ``.iloc`` lookups the verdict itself costs. A leg that CANNOT be decided yet (the last 1-2
    bars, 'pending confirmation') is reported rather than silently dropped, so a one-element list
    always means 'every other leg passed', never 'we did not look'.

    ``waiver`` passes straight through to :func:`_confirm_legs`.  On a VETOED bar it can only
    remove a second block from ``reasons`` (a waived reclaim is no longer a refusal); the
    verdict stays the hardcoded (False, veto) it always was — the divergence veto is not
    waivable by anything in this family.
    """
    if not bear:
        take, reason = _confirm_legs(i, sig, n, reclaim_veto=reclaim_veto, waiver=waiver)
        return take, reason, [reason]
    rest_take, rest_reason = _confirm_legs(i, sig, n, reclaim_veto=reclaim_veto, waiver=waiver)
    reasons = [BEAR_DIV_REASON]
    if rest_take is not True:                # False = a second real block; None = undecidable
        reasons.append(rest_reason)
    return False, BEAR_DIV_REASON, reasons


def _buy_filter(i, sig, bear, n, *, reclaim_veto: bool = True,
                waiver: ReclaimWaiver | None = None):
    """The VALIDATED buy-filter: reclaim-and-hold + bearish-div veto + 200MA bar-raiser.
    Returns (take: bool|None, reason). None = pending (last 1-2 bars can't confirm yet).

    This is the FIRST-MATCH verdict and the stable public shape — every existing caller keeps
    it. :func:`_buy_filter_full` returns the same verdict plus the exhaustive leg account; read
    that docstring before treating ``reason`` as a complete explanation of a block.

    ``reclaim_veto`` (keyword-only, DEFAULT True = the validated US/CN behaviour, unchanged)
    controls ONE leg: the 2-bar 200-day reclaim requirement applied to a name that is BOTH
    below its 200-day average AND weekly-down. With it False, such a name is admitted on the
    same terms as everyone else — the next-bar ``held`` confirmation — and the bearish-
    divergence veto above still applies untouched.

    WHY THE LEG IS SWITCHABLE (operator directive 2026-08-03, HK board). For a name in a deep
    drawdown the reclaim test is not a risk judgement, it is an UNSATISFIABLE condition: a name
    17% below its 200-day line cannot travel 17% in two sessions, so every buy signal it fires
    while washed out is auto-blocked until it has already recovered to the 200-day average —
    i.e. until the bounce being signalled is over. On the HK tape, whose setups are
    predominantly deep-washout bounces, this blocked the board's best entries (measured on the
    2026-06-26→07-31 leg: the blocked names ran +8.7% to +44%). The leg stays ON by default
    because the US/CN drawdown validation was measured WITH it; only a board that has taken the
    era stamp for the looser policy passes False.

    ``waiver`` (keyword-only, DEFAULT None = the v1 policy, byte-identical) is the RATIFIED
    conditional relaxation of the same leg on the US tape — see the WHY block above
    :class:`ReclaimWaiver`.  It is narrower than the flag in every direction: it needs a
    per-name measured washout state, it needs that state to be PIT-clean for the bar, it can
    only convert the PURE reclaim failure (the hold leg must still have PASSED), and it is
    resolved outside this function.  ``reclaim_veto=False`` and a waiver are not alternatives
    — HK dropped the leg flat, the US relaxes it conditionally, and the two live behind
    different era stamps (``hk_prophet_v2`` / ``us_prophet_v2``).

    ⚠ MARKER-DATE GRADING IS FORBIDDEN (CN-1 masterplan §W6-CN). The ``held``/``reclaim`` tests
    below read bars i+1/i+2 — i.e. the label at bar ``i`` is knowable only in the FUTURE relative to
    ``i``. A 'take' marker therefore carries +5.7pp/10d of look-ahead (measured: +9.47%/10d 84.7%
    from marker dates vs +3.77%/61.5% from the confirmation-day close). Any forward-return grader,
    backtest, or chart-marker hit-rate MUST anchor on the first close at which the label was
    KNOWABLE — never on the marker date itself. The china_standout_track ledger enforces this by
    anchoring on the board-date close (post-confirmation) and measuring from the T+1 fill; see
    tests/test_signal_quality_no_leak.py which pins that any grade off ``analyze`` markers overstates
    forward returns. Do NOT grade forward returns from ``marker['date']``."""
    if bear:
        return False, BEAR_DIV_REASON
    return _confirm_legs(i, sig, n, reclaim_veto=reclaim_veto, waiver=waiver)


# ---- the legal anchor for anything measured FORWARD from a marker ------------ #
# Bars of forward 3D data every ``_buy_filter`` label depends on.  2, not 1, and the
# bound is exact rather than a safety margin:
#
#   * the counter-trend branch reads ``a.iloc[i + 2]`` outright;
#   * the plain branch reads only ``c.iloc[i + 1]`` — but it is REACHED only when the
#     ``bear`` test above it is False, and ``bear`` is ``_bear_div(i, ...)`` over
#     ``_swing_highs(..., w=2)``, whose candidate list includes a swing high AT bar
#     ``i``.  A swing high at ``i`` is confirmed against ``v[i-2 : i+3]``, so the bear
#     leg itself is not settled until bar ``i + 2``;
#   * the bear-veto branch is the same test, so it inherits the same bound.
#
# So no ``_buy_filter`` label is knowable before bar ``i + 2``, and the counter-trend
# reason — 44 of the 54 HK vetoed-lane admits on the 2026-08-03 panel — is knowable
# exactly there.  A per-branch offset would be shorter for some rows only by reading
# the data that decided them, which is the look-ahead this constant exists to close.
CONFIRM_BARS = 2


def _bucket_last_session(daily_close: pd.Series, *, market: str = "US") -> pd.Series:
    """3D bucket label (its OPEN date) -> the last DAILY session in it that carried a close.

    The SAME :func:`_tf_grid` call :func:`signal_frame` cuts its 3D close on — one grid,
    one set of buckets, one set of labels — so the two halves of a confirmation read can no
    longer disagree by construction.

    Under the pre-``sq-abs-session-2026-08-06`` ``3B`` resample this function carried a
    caveat instead of a guarantee: bins anchored on the series' FIRST index date, so
    re-deriving them from a differently-trimmed copy shifted EVERY boundary (measured:
    dropping one leading row moved every label), and both halves of a read had to come from
    one series object.  The absolute anchor retires that caveat — the grid is a function of
    ``(reference calendar, date)`` alone, so any two windows of the same name agree.
    """
    return _tf_grid(daily_close, 3, market).last_session


def marker_last_session(daily_close: pd.Series, marker_date, *,
                        market: str = "US") -> pd.Timestamp | None:
    """The LAST daily session inside a §7 marker's own 3D bucket — the knowability date.

    A marker is LABELLED with its bucket's OPEN date (:func:`_tf_grid`, R-SQ2), so the
    label precedes the bar that closed the bucket by up to two sessions. Anything that
    measures HOW OLD a signal is from the label therefore ages it by up to two sessions
    it did not exist for. Measured on the committed 2026-08-06 board: APH and FCX
    published ``days_since_signal 4`` on signals whose bucket had only closed 2 sessions
    earlier, which is past ``templates/stocktable.js``'s ``FRESH_DAYS = 2`` — the freshest
    turns on the board were the ones the fresh-only filter dropped.

    This is NOT :func:`confirmation_date`, and the two must not be swapped. That function
    answers "when was the ``_buy_filter`` LABEL knowable" and walks a further
    :data:`CONFIRM_BARS` buckets forward (~6 more daily sessions) because a forward RETURN
    graded any earlier would be reading its own answer. An AGE measured from that anchor
    would run negative on every genuinely fresh marker — the opposite of the defect above.
    Ages come from here; forward returns come from there.

    Returns ``None`` — never a guess — when ``marker_date`` is not a bucket label of THIS
    series, or the series/date cannot be read. Cheap on purpose: :func:`_tf_grid` alone,
    no :func:`signal_frame`, no MACD/StochRSI — this runs per-ticker on the render path.
    """
    if daily_close is None or marker_date is None or len(daily_close) == 0:
        return None
    try:
        stamp = pd.Timestamp(marker_date).normalize()
    except (TypeError, ValueError):
        return None
    if pd.isna(stamp):
        return None
    try:
        sessions = _bucket_last_session(daily_close, market=market)
    except FileNotFoundError:
        # session_anchor RAISES rather than silently bucketing a non-US name on NYSE
        # sessions (the no-fallback-chain law). A checkout without that market's
        # reference calendar cannot derive this anchor — a disclosed null, not a guess.
        return None
    if sessions is None or len(sessions) == 0:
        return None
    session = sessions.get(stamp)
    if session is None or pd.isna(session):
        return None
    return pd.Timestamp(session)


def confirmation_date(daily_close: pd.Series, marker_date, *,
                      market: str = "US") -> pd.Timestamp | None:
    """First daily close at which a marker's ``_buy_filter`` label was KNOWABLE.

    THE ONLY LEGAL ANCHOR for a forward return off a §7 marker — see the warning on
    :func:`_buy_filter`, which forbids grading from ``marker['date']``.  Two separate
    look-aheads sit between the two dates and this function closes both:

    1. ``marker['date']`` is the 3D bucket's OPEN date (:func:`_tf_grid` labels a bucket
       with its first TRADED session, R-SQ2), so it precedes even its OWN close by up to
       two sessions.  Pre-``sq-abs-session-2026-08-06`` it was the retired ``3B`` bin's
       synthetic LEFT EDGE, which could be a holiday belonging to no series at all; the
       gap it opens is the same size and the same direction, and closing it is still this
       function's job;
    2. the label at bar ``i`` reads forward to bar ``i + 2`` (:data:`CONFIRM_BARS`).

    Together that is ~8 daily sessions, and the marker date sits at the trough that
    CREATED the signal.  Measured on the HK vetoed lane, anchoring the displayed move
    on the marker overstated it by +7.16pp on average across the lane's own 48-54 name
    population (2026-07-31 and 2026-08-03 as-of dates).

    The geometry is not re-implemented: :func:`signal_frame` is called and its index
    walked, so the bucket set is the one ``analyze`` iterated — including its mid-panel
    gaps.  A flat-price stretch NaNs the StochRSI band and drops buckets out of the
    middle of the frame, which no arithmetic on the daily index reproduces (measured:
    a busday-offset derivation matched 8977 of 8978 HK markers and missed exactly that
    case — 2607.HK, a 2008 penny stock frozen at 0.0133 for 14 buckets).

    Returns ``None`` — never a guess — when the anchor cannot be derived: series too
    short for :func:`signal_frame`, ``marker_date`` not a bucket label of THIS series,
    or bar ``i + 2`` not printed yet.  That last one is the live-edge case: a marker
    inside its own confirmation window has no knowable-yet close, and the caller owes
    the reader a disclosed null rather than a number measured from the wrong bar.

    ``market`` must be the calendar the marker was LABELLED on (R-SQ1) — pass the same
    value ``analyze`` used, or the lookup lands on a grid the marker never sat on and
    returns the disclosed ``None``.  ``hk_board_rank`` passes HK.
    """
    if daily_close is None or marker_date is None or len(daily_close) == 0:
        return None
    try:
        stamp = pd.Timestamp(marker_date).normalize()
    except (TypeError, ValueError):
        return None
    if pd.isna(stamp):
        return None
    sig = signal_frame(daily_close, market=market)
    if sig.empty:
        return None
    # analyze()'s own prefix, verbatim — the frame this walks must be the frame the
    # marker was labelled on, or i+2 counts buckets analyze() never saw.
    sig = sig.dropna(subset=["macd", "sig", "k", "d", "rsi14"])
    if len(sig) < 5:
        return None
    index = sig.index
    position = int(index.get_indexer([stamp])[0])
    if position < 0:
        return None                      # not a bucket label of this series
    if position + CONFIRM_BARS >= len(index):
        return None                      # _buy_filter's own "pending confirmation"
    session = _bucket_last_session(
        daily_close, market=market).get(index[position + CONFIRM_BARS])
    if session is None or pd.isna(session):
        return None
    return pd.Timestamp(session)


def analyze(ticker: str, daily_close: pd.Series, daily_high: pd.Series | None = None,
            daily_low: pd.Series | None = None, *, reclaim_veto: bool = True,
            washout_waiver: bool = True) -> dict | None:
    """Per-ticker chart-marker + state object (the site/signals/<T>.json contract, §7).

    Optional ``daily_high``/``daily_low`` let swing-high & bearish-divergence read
    intrabar extremes (true OHLC for US; a conservative reconstruction for close-only
    names — see engine.ohlc_reconstruct). Omit them for the close-only default.

    ``reclaim_veto`` is passed straight through to :func:`_buy_filter` (default True =
    the validated US/CN policy, unchanged). See that docstring for why HK passes False.

    ``washout_waiver`` (default True = the RATIFIED ``us_prophet_v2`` policy) enables the
    counter-trend reclaim waiver; THIS is the function that resolves it, because it is the
    only one in the chain that knows the ticker and the daily calendar.  Pass False to
    reproduce the v1 admission exactly — that is what the frozen packet isolation
    (`research/prophet_us_audit/reclaim_veto_packet.py`) measures against, and it is a
    research escape hatch, not a board setting.  It costs one dict lookup per ticker and one
    integer compare per buy marker; on a name the artifact does not qualify (or on any
    non-US tape) it costs the lookup alone.

    The 2D/3D grids are anchored to the reference session calendar of the market inferred
    from ``ticker`` (``session_anchor.market_for_ticker``, R-SQ1) — so no caller needs an
    edit to get the right calendar — and every payload carries ``anchor_era`` naming the
    bucketing era it was drawn under (R-SQ3)."""
    market = session_anchor.market_for_ticker(ticker)
    sig = signal_frame(daily_close, daily_high, daily_low, market=market)
    if sig.empty:
        return None
    sig = sig.dropna(subset=["macd", "sig", "k", "d", "rsi14"])
    if len(sig) < 5:
        return None
    c, macd, idx, n = sig["close"], sig["macd"], sig.index, len(sig)
    hi = _swing_highs(sig["high"])
    # close-only trailing trend + its fresh breaches. A breach of a trail that was RISING
    # INTO it = an uptrend's trailing trend breaking down (the tail-risk event we want to
    # surface). NB: below.shift(1, fill_value=False) keeps BOOL dtype — plain .shift(1)
    # returns object dtype, where ~ does integer bitwise-not (~True == -2, truthy) and
    # silently corrupts the mask. The breach BAR itself can't be "rising" (its sub-trail
    # close pulls the EMA down), so we test the slope leading into it.
    trail = sig["ema_trail"]
    below = (c < trail)
    prev_below = below.shift(1, fill_value=False)
    rising_into = (trail.shift(1) > trail.shift(3))
    fresh_breach = (below & ~prev_below & rising_into).fillna(False)
    # `markers` is the validated TRADE stream (buy/sell/cut/rebuy), one per bar -> strictly
    # date-ascending (the §7 contract / validate_signals.py invariant). The trail-stop breach
    # is a DISTINCT display-only risk layer in its OWN `risk_flags` date list, so it can co-
    # occur with a sell/cut on the same bar without violating the one-marker-per-bar rule.
    # `early_markers` is a SECOND display-only date list (like risk_flags): the 2D-MACD pre-cross
    # advance-warning. Kept OUT of the validated trade stream; suppressed on a confirmed-buy bar
    # (then it is no longer "early"). Advance-warning ONLY — not every one is followed by a buy.
    # `early_signal_dates` is the ADDITIVE knowability stamp for `early_markers` (§6.7
    # signal-date family; the bake-off measured 3,756/3,760 dots carrying the bucket-OPEN
    # label). The legacy list keeps its exact meaning and position so no consumer moves;
    # this parallel list carries the SAME dots' last-session dates, index-aligned 1:1.
    markers, risk_flags, early_markers, early_signal_dates = [], [], [], []
    # THE THREE DATES A MARKER HAS, named on the marker itself (§7 signal-date family).
    # They disagree by up to ~8 daily sessions and three separate surfaces were each
    # reading a different one as "the signal date" with no field saying which:
    #   `date`           the bucket's OPEN label (R-SQ2) — the chart's x-anchor. FROZEN
    #                    here; it is what `marker_integrity` may never re-date.
    #   `signal_date`    the SAME bucket's last session — the close that produced the
    #                    signal, i.e. when it became KNOWABLE. This is the date a
    #                    "Buy · Aug 7" panel means and what an AGE must use.
    #   `confirmed_date` the first close at which the `_buy_filter` LABEL was knowable
    #                    (:data:`CONFIRM_BARS` buckets further on) — null while the
    #                    confirmation window is open. Buy/rebuy only: sell/cut run no buy
    #                    filter, so they have no confirmation to date.
    # Derive from ONE `_bucket_last_session` call so these emitted fields and the
    # standalone resolvers cannot drift apart (tests/test_signal_date_family.py).
    sessions = _bucket_last_session(daily_close, market=market)
    # Name-level half of the reclaim waiver, resolved ONCE (see :func:`washout_qualifier`).
    # None on every path that is not the ratified one: the flag off, the leg already dropped
    # flat (`reclaim_veto=False`, HK — there is no reclaim test left to waive), a non-US
    # tape, a missing/stale/unparseable artifact, or a name the state does not qualify at
    # :data:`WASHOUT_NOTCH`.  The PIT half is per-marker, below.
    qualifier = (washout_qualifier(ticker)
                 if (washout_waiver and reclaim_veto) else None)

    def _session_str(label) -> str | None:
        """Return this bucket label's last session, disclosing null rather than guessing."""
        got = sessions.get(label) if sessions is not None else None
        if got is None or pd.isna(got):
            return None
        return str(pd.Timestamp(got).date())

    for i in range(n):
        ds = str(idx[i].date())
        signal_date = _session_str(idx[i])
        is_buy = bool(sig["CB"].iloc[i]) or bool(sig["revBuy"].iloc[i])
        if is_buy:
            # `confirmed` is BOTH the emitted `confirmed_date` below and the waiver's PIT
            # anchor — the first close at which this label was knowable (prereg §2's "fire's
            # known date").  Derived once, from the same `_bucket_last_session` map, so the
            # date the waiver is judged against and the date the marker publishes can never
            # be two different days.
            confirmed = (_session_str(idx[i + CONFIRM_BARS])
                         if i + CONFIRM_BARS < n else None)
            waiver = reclaim_waiver_for(qualifier, confirmed, daily_close.index)
            ok, reason, reasons = _buy_filter_full(
                i, sig, _bear_div(i, sig["high"], macd, hi), n,
                reclaim_veto=reclaim_veto, waiver=waiver)
            q = "pending" if ok is None else ("take" if ok else "block")
            m = {"date": ds, "type": "rebuy" if bool(sig["revBuy"].iloc[i]) else "buy",
                 "quality": q, "reason": reason}
            # `reasons` (SCHEMA.json §marker) is emitted ONLY when it says something `reason`
            # does not — i.e. when the block is over-determined. A single-leg verdict keeps the
            # file byte-identical to the pre-change render, and its absence is unambiguous
            # because reasons[0] is always `reason`: a reader falls back to [reason] exactly.
            if len(reasons) > 1:
                m["reasons"] = reasons
            # Append after legacy keys so the marker's published prefix stays unchanged.
            m["signal_date"] = signal_date
            m["confirmed_date"] = confirmed
            # NO waiver key is added to the marker.  `research/signal_engine/SCHEMA.json`
            # closes `$defs/marker` with `additionalProperties: false` and that file is a
            # CROSS-REPO published contract (exported nightly as `golden_signals`), so the
            # receipt lives on the gate verdict instead — `engine.signal_gate.gate()` re-
            # derives it from this same pair of pure functions.  The audit chain is intact
            # without widening the contract: the reason names the waiver, and the state
            # artifact is committed to git every night, so (ticker, as_of, notch) recovers
            # the exact peer reading that relieved any historical row.
            markers.append(m)
        elif bool(sig["CS"].iloc[i]):
            markers.append({"date": ds, "type": "sell", "signal_date": signal_date})
        elif bool(sig["revSell"].iloc[i]):
            markers.append({"date": ds, "type": "cut", "signal_date": signal_date})
        if bool(fresh_breach.iloc[i]):
            risk_flags.append(ds)
        if bool(sig["early"].iloc[i]) and not is_buy:
            early_markers.append(ds)
            early_signal_dates.append(signal_date)
    last = sig.iloc[-1]
    state = ("long-bias" if (last["k"] >= last["d"] and last["macd"] >= last["sig"])
             else "short-bias" if (last["k"] < last["d"] and last["macd"] < last["sig"]) else "mixed")
    t_last = float(trail.iloc[-1])
    # Emitted ONLY when every dot resolved a last session, so a reader may rely on
    # ``len(early_signal_dates) == len(early_markers)`` and on positional pairing. A
    # partially-resolved list would be worse than none: it would silently re-index the pairs.
    stamped = all(x is not None for x in early_signal_dates)
    doc = {"ticker": ticker, "asof": str(idx[-1].date()), "tf": "3D",
           # the bucketing era this marker stream was drawn under (R-SQ3). It rides ON the
           # payload so site/signals/<T>.json, the brain leaves, marker_integrity's cutover
           # and the track-record ledger can all place a row in the right cohort forever.
           "anchor_era": ANCHOR_ERA, "state": state,
           "above200": bool(last["above200"]), "weekly_bull": bool(last["w_bull"]),
           "trail_stop": round(t_last, 4) if pd.notna(t_last) else None,
           "trail_breach": bool(pd.notna(t_last) and last["close"] < t_last),
           "markers": markers, "risk_flags": risk_flags,
           "early_markers": early_markers, "early_now": bool(last["early"])}
    if stamped:
        doc["early_signal_dates"] = early_signal_dates
    return doc
