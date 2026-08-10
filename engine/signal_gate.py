"""Validated-confluence BUY GATE for the per-country Standout grids (US/CN/HK/CA/Intl).

Wraps :func:`engine.signal_quality.analyze` — the VALIDATED MACD-RSI x StochRSI confluence
buy-filter (reclaim-and-hold + bearish-div veto + 200MA bar-raiser; cut avg max drawdown
-23.7% -> -15.5% across 110 held-out US names; CHARTER.md §2/§5) — and turns its §7 marker
stream into a single grid ELIGIBILITY verdict so every country's "Standout Top Stocks" board
gates on the SAME validated signal that the chart renders.

This REPLACES the per-grid ad-hoc screens (the US standard-MACD(12,26,9)+StochRSI `cycles`
ladder; the non-US alpha-only floors) as the PRIMARY buy-entry gate. It is a DISPLAY-ONLY
entry-QUALITY / RISK gate, NOT alpha and NOT an auto-trade trigger (CHARTER §2).

Tiers (ranked; take is always above every anticipation — CHARTER §2/§7):

  TIER take          currently holding a buy-filter-ENDORSED entry: the last §7 marker is a
                     buy/rebuy with quality 'take' and no sell/cut has fired since. This is
                     the validated primary buy signal.
  TIER anticipation  imminently forming but NOT yet endorsed — surfaced as an *eligibility
                     exception*, never as a stronger buy than a take:
                       sub 'pending' = the confluence buy fired on the last 1-2 bars but its
                                       forward reclaim-and-hold confirmation isn't in yet
                                       (resolves to take/block next build; §7 'pending').
                       sub 'early'   = the validated 2D-MACD pre-cross advance-warning
                                       (early_now / m2d_s3d_early). Acting on it early is
                                       empirically WORSE entry quality (CONFLUENCE_TUNING.md
                                       §3), so it only makes a name ELIGIBLE to surface — it
                                       is never a take and never fed to conviction/auto-trade.
  not eligible       blocked buy, flat (last marker is a sell/cut), no buy signal, or
                     insufficient history (analyze() returned None -> graceful skip).

signal_quality is CLOSE-ONLY by construction (it stochs the RSI of close; it never needs
high/low), so this gate runs on every market's close-only price store and self-degrades to
"insufficient history" on thin names instead of crashing.

REASONS vs REASON. Every verdict carries BOTH `reason` (the single first-match label, unchanged
and back-compatible) and `reasons` (the ordered, exhaustive account, `reasons[0] == reason`
always). They differ only where a verdict is over-determined — today, a buy that more than one
buy-filter leg refuses. `reason` alone is a first-match LABEL: the bearish-divergence veto returns
before reclaim-and-hold is ever tested, so a name blocked twice reads as blocked once, and 77% of
divergence-vetoed CN fires were blocked by another leg anyway
(research/cn_prophet_audit/CN_DIVERGENCE_VETO_AUDIT.md). Neither field is a gate input — admission,
tier and eligibility are byte-identical with or without the account.

Anticipation-form decision: research/signal_engine/tuning_anticipation.py compared the
in-engine from-OS `early` leg (a) against a from-above-OS + 2D-cross relaxation (b) as
SURFACERS of imminent base3d buys on the 110 held-out US names. (a) dominated (b) on recall
(38.5% vs 21.9% of TAKEs), precision (32% vs 20.5%) and lead (4.6d vs 2.2d), so the gate uses
(a) = `early_now`; (b) was NOT adopted (it added mostly false alarms). See GRID_GATE.md.
"""
from __future__ import annotations

import pandas as pd

from engine import signal_quality     # the §7 marker master (its own bucketing era, R-SQ3)
from engine.signal_quality import analyze
from engine import confluence_tiers   # owner's weighted T1->T4 cascade (TIERED_CASCADE.md)
from engine import session_anchor     # absolute session-calendar anchor (per-market, R3)

TAKE = "take"
ANTICIPATION = "anticipation"
_BUY_TYPES = ("buy", "rebuy")

# tier sort order: take above every anticipation; within anticipation, a fired-but-pending
# buy ranks above the pre-cross early warning (it is "more formed"). 0 = best.
_TIER_ORDER = {(TAKE, None): 0, (ANTICIPATION, "pending"): 1, (ANTICIPATION, "early"): 2}
# operator-ratified 2026-07-06: T2 now scores above T1 for entry quality (fills closer to
# trough, confirmed-bar with low repaint). T2=0 (best), T1-held=1, T1-pending=2, T3=3, T4=4.
# pending (3D master forming) sits at 2, just below the held T1 and the T2 cross.
_CASCADE_RANK = {"T1": 1, "T2": 0, "T3": 3, "T4": 4}
# board ranking = convex blend of cascade tier (TIER_FRAC) + conviction percentile (1-TIER_FRAC).
# Conviction-led (<0.5) so strong EARLIER tiers surface on a take-heavy board; tier is a real
# boost (a master beats an equal-conviction earlier tier). See signal_gate.blend_sorted.
TIER_FRAC = 0.45

# The tiers that constitute a FRESH, ACTIONABLE confluence BUY for the "what to buy now"
# boards (the Top-setups strip on us_stocks.html + the discovery "Buy-zone" picks). This is
# the owner's explicit spec — a name is only a recommendation if EITHER:
#   * it has triggered the MACD-2D x StochRSI-3D confluence — the 2D RSI-MACD has JUST crossed
#     (its arrow is <= FRESH_TICKS 2D-ticks old, the "just-crossed" trigger) while the 3D
#     StochRSI has crossed RECENTLY (within the confluence window CONF_W) and is still
#     constructive / not-topped (T2); or the validated 3D master take is itself just-crossed
#     and not-topped (T1, the stronger superset). NOTE the asymmetry is intentional and matches
#     the validated engine (confluence_tiers TIERED_CASCADE.md): the StochRSI sets up the zone
#     (it need not be same-bar), the 2D MACD cross is the freshness-gated trigger; the
#     not-topped veto kills a stale/overbought setup regardless of when the StochRSI crossed; OR
#   * the 3D StochRSI has ALREADY crossed and the 2D RSI-MACD is about to cross in the next
#     1-2 ticks (T3, the anticipation tier).
# T4 is DELIBERATELY EXCLUDED: it fires off the *2D* StochRSI (not the 3D), so it does not meet
# the "StochRSI 3D crossover" requirement and is the earliest / weakest anti-falling-knife tier.
BUYABLE_TIERS = ("T1", "T2", "T3")


def is_buyable(v: dict | None) -> bool:
    """True iff a gate verdict (full or :func:`compact`) is a fresh, actionable confluence buy
    per BUYABLE_TIERS — a just-crossed confirmed cross (T1/T2) or the StochRSI-3D-crossed /
    MACD-2D-about-to-cross anticipation (T3). The topped / stale / early-only paths in
    :func:`gate` clear ``tier_cascade`` to None, so a HOLD or a downtrend never reads buyable."""
    if not v or not v.get("eligible"):
        return False
    return v.get("tier_cascade") in BUYABLE_TIERS


_VERDICT_KEYS = ("eligible", "tier", "sub", "reason", "reasons", "state", "above200",
                 "weekly_bull", "early_now", "asof", "last",
                 "tier_cascade", "weight", "tier_sub", "bars_to_cross", "fresh_bars",
                 # the knowability-anchored twin of fresh_bars (bucket LAST session, not
                 # its OPEN label). Display-tier: it feeds the shown age, never a gate.
                 "fresh_bars_knowable", "ticks",
                 # Cascade-native provenance. Never substitute `last.date`: T2/T3/T4 can
                 # coexist with an unrelated §7 marker. T3/T4 are observations without a
                 # fired event, so their event date is null and the provisional bit is true.
                 "tier_event_date", "tier_observed_date",
                 "tier_observation_provisional",
                 "provisional", "htf_s1", "htf_s2", "young_history", "history_bars",
                 # the bucketing era this verdict was graded under (R5) — a cohort label like
                 # young_history, so it travels the same way. `veto_legs_null` is deliberately
                 # NOT here: it is a warmup DISCLOSURE and rides beside `null_legs`, which the
                 # compact row has never carried either.
                 "anchor_era",
                 # ...and the §7 marker stream's OWN bucketing era (R-SQ3). A verdict is
                 # jointly produced by TWO grids — the cascade's and signal_quality's — and
                 # they moved to the absolute anchor in different PRs, so a graded row must
                 # be able to place itself against both. Same cohort-label idiom as above.
                 "sq_anchor_era")

_BLOCKED_PREFIX = "buy blocked by filter: "


def _set_reason(v: dict, reason: str, *extra: str) -> None:
    """Write ``reason`` and its EXHAUSTIVE companion ``reasons`` in lockstep.

    ``reason`` stays exactly what it always was — a single first-match label, unchanged for
    back-compat — and ``reasons`` is the ordered account, with ``reasons[0]`` byte-identical to
    ``reason`` on every verdict. Extra elements appear only where a verdict is over-determined
    (today: a buy blocked by more than one filter leg), and each one is a COMPLETE reason string
    in the same idiom as ``reason``, so any element renders on its own.

    Every ``reason`` write in this module goes through here on purpose: :func:`gate` REWRITES
    the verdict reason after :func:`verdict` has run (the stale/topped demotions and the
    ``tier T*`` extension), and an account left behind by an earlier stage would then describe a
    verdict that no longer exists. Setting both together makes that impossible rather than
    something a later reader has to notice."""
    v["reason"] = reason
    v["reasons"] = [reason, *extra]


def _bars_since(daily_close, marker) -> int | None:
    """Trading bars between a §7 buy marker's date and the latest close bar (None if unknown).
    Used to age a held 'take': a buy that fired weeks ago is no longer a FRESH entry."""
    if not marker or not marker.get("date"):
        return None
    try:
        idx = pd.to_datetime(pd.Index(getattr(daily_close, "index", [])))
        if len(idx) == 0:
            return None
        return int((idx > pd.Timestamp(marker["date"])).sum())
    except Exception:
        return None


def _knowable_bars(daily_close, marker, *, market_of: str) -> int | None:
    """Trading bars since the session the marker's 3D bucket CLOSED on (None if unknown).

    The knowability twin of :func:`_bars_since`: same daily-index count, but anchored on
    the bucket's LAST session instead of its OPEN label, so a signal is never reported as
    older than it was ever possible to know about. The bucket geometry is not
    re-implemented here — :func:`engine.signal_quality.marker_last_session` walks the same
    grid ``analyze`` labelled the marker on, and the calendar is inferred from the ticker
    exactly as the cascade's is.

    Fail-soft and fail-CLOSED: any unreadable input returns ``None`` (a disclosed null the
    caller falls back from), never a substituted count.
    """
    if not marker or not marker.get("date"):
        return None
    try:
        from engine.signal_quality import marker_last_session

        market = session_anchor.market_for_ticker(market_of)
        session = marker_last_session(daily_close, marker["date"], market=market)
        if session is None:
            return None
        idx = pd.to_datetime(pd.Index(getattr(daily_close, "index", [])))
        if len(idx) == 0:
            return None
        return int((idx > pd.Timestamp(session)).sum())
    except Exception:  # noqa: BLE001 — an additive disclosure never breaks the gate
        return None


def _emitted_marker_event_date(daily_close, marker) -> str | None:
    """Validate an explicitly emitted marker ``signal_date`` against this input tape.

    Used only for the forming-T1 path that signal_gate promotes after cascade() returns
    no native tier. There is intentionally no fallback to the legacy bucket-open
    ``marker['date']``: a missing or invalid knowability close stays null.
    """
    if not marker or "signal_date" not in marker or marker.get("signal_date") is None:
        return None
    try:
        stamp = pd.Timestamp(marker["signal_date"])
        if pd.isna(stamp):
            return None
        if stamp.tzinfo is not None:
            stamp = stamp.tz_localize(None)
        stamp = stamp.normalize()
        idx = pd.DatetimeIndex(getattr(daily_close, "index", []))
        if idx.tz is not None:
            idx = idx.tz_localize(None)
        if int(idx.normalize().get_indexer([stamp])[0]) < 0:
            return None
        return str(stamp.date())
    except (TypeError, ValueError):
        return None


def _observed_session_date(daily_close) -> str | None:
    """The final observed session in the exact tape handed to gate(), or null."""
    try:
        idx = pd.DatetimeIndex(getattr(daily_close, "index", []))
        if len(idx) == 0:
            return None
        return str(pd.Timestamp(idx[-1]).date())
    except (TypeError, ValueError):
        return None


def _extra_block_legs(marker: dict) -> list[str]:
    """The blocking legs BEYOND the first-match one, off a §7 buy marker's `reasons` list.

    Defensive by construction: the marker's account is trusted only when it actually starts with
    the marker's own `reason` (that invariant is what makes `reasons[0] == reason` safe to rely
    on downstream). A missing, malformed, or out-of-sync list yields no extras rather than a
    verdict whose account contradicts its label."""
    first = (marker.get("reason") or "").strip()
    raw = marker.get("reasons")
    if not isinstance(raw, (list, tuple)):
        return []
    legs = [str(r).strip() for r in raw if str(r).strip()]
    if not legs or legs[0] != first:
        return []
    return legs[1:]


def verdict(result: dict | None) -> dict:
    """Map an :func:`engine.signal_quality.analyze` result (or None) to a gate verdict."""
    # `reason`/`reasons` are seeded here (not via _set_reason) so the key ORDER of a verdict
    # dict is identical to the pre-change one — a raw verdict serialized to JSON keeps its
    # byte layout, with `reasons` slotted directly behind the label it accounts for.
    # `sq_anchor_era` is seeded on EVERY verdict shape, blanks included: the row was
    # produced by THIS engine under THIS bucketing era whether or not `result` had enough
    # history to grade (R-SQ3). Reading it off the payload would leave the "insufficient
    # history" refusal — the one row a cohort audit most needs to place — unlabelled.
    v = {"eligible": False, "tier": None, "sub": None, "reason": "no signal",
         "reasons": ["no signal"],
         "state": None, "above200": None, "weekly_bull": None, "early_now": False,
         "asof": None, "last": None, "sq_anchor_era": signal_quality.ANCHOR_ERA}
    if not result:
        _set_reason(v, "insufficient history")
        return v
    markers = result.get("markers") or []
    last = markers[-1] if markers else None
    early = bool(result.get("early_now"))
    v.update(state=result.get("state"), above200=result.get("above200"),
             weekly_bull=result.get("weekly_bull"), early_now=early,
             asof=result.get("asof"), last=last)
    if last and last.get("type") in _BUY_TYPES:
        q = last.get("quality")
        if q == "take":
            v.update(eligible=True, tier=TAKE)
            _set_reason(v, last.get("reason") or "held buy-filter confirmation")
            return v
        if q == "pending":
            v.update(eligible=True, tier=ANTICIPATION, sub="pending")
            _set_reason(v, "buy fired; forward confirmation pending")
            return v
        # a blocked buy: only a live early advance-warning can still surface it
        if early:
            v.update(eligible=True, tier=ANTICIPATION, sub="early")
            _set_reason(v, "early advance-warning (last buy was filtered out)")
            return v
        # THE over-determined case. `reason` keeps naming the FIRST leg that fired, exactly as
        # before; `reasons` names every leg that refused the name, so a reader can tell a buy
        # blocked once from a buy blocked twice over. The marker only carries `reasons` when it
        # adds something (signal_quality.analyze), so [reason] is the correct fallback, not a gap.
        _set_reason(v, _BLOCKED_PREFIX + (last.get("reason") or "").strip(),
                    *(_BLOCKED_PREFIX + leg for leg in _extra_block_legs(last)))
        return v
    # flat: last marker is a sell/cut, or there are no markers yet
    if early:
        v.update(eligible=True, tier=ANTICIPATION, sub="early")
        _set_reason(v, "early advance-warning (no open buy)")
        return v
    _set_reason(v, "flat: " + (last.get("type") if last else "no buy signal"))
    return v


def _waiver_receipt(ticker: str, daily_close, marker: dict | None) -> dict | None:
    """The RECEIPT for a counter-trend reclaim the ratified waiver relieved, or ``None``.

    RE-DERIVED, not carried.  `research/signal_engine/SCHEMA.json` closes the §7 marker
    shape (`additionalProperties: false`) and it is a cross-repo published contract, so
    `analyze` emits only the reason literal and this function reconstructs the rest from the
    same two pure functions `analyze` used — same artifact, same ticker, same knowable date,
    so the answer is the same answer.  It is the audit surface for an ADMISSION change: which
    peer group relieved the name, how washed out that group was, and how old the reading was.
    Never rendered — every field is a raw slug, an untranslated stat or an era name.
    """
    if not marker or marker.get("reason") != signal_quality.RECLAIM_WAIVED:
        return None
    w = signal_quality.reclaim_waiver_for(
        signal_quality.washout_qualifier(ticker), marker.get("confirmed_date"),
        getattr(daily_close, "index", []))
    if w is None:                       # unreachable in practice; a refusal, never a guess
        return None
    return {"rule": "reclaim", "notch": w.notch, "group_id": w.group_id, "basis": w.basis,
            "peer_dd": w.peer_dd, "as_of": w.as_of, "stale_sessions": w.stale_sessions,
            "era": "us_prophet_v2"}


def gate(ticker: str, daily_close, *, reclaim_veto: bool = True, event_latch=None,
         washout_waiver: bool = True) -> dict:
    """analyze() the close series, then return the verdict PLUS the raw analyze() result
    (the §7 site/signals/<T>.json payload) under "result". Never raises on thin/bad data.

    ``reclaim_veto`` passes through to :func:`engine.signal_quality._buy_filter`. DEFAULT
    True keeps every existing caller (US, CN, and the ~12 modules importing this) on the
    validated policy byte-for-byte; HK passes False per the 2026-08-03 operator ruling —
    see that function's docstring for the mechanism.

    ``washout_waiver`` passes through to :func:`engine.signal_quality.analyze`. DEFAULT True
    = the RATIFIED ``us_prophet_v2`` policy (prereg `reclaim_veto_conditional_v1` §4 Arm P,
    notch 20): a US name whose basket peers are themselves washed out has the counter-trend
    200-day RECLAIM leg waived — the HOLD leg is still required, and nothing else in the
    filter moves. A verdict the waiver decided carries a ``waiver`` receipt naming the peer
    group, its drawdown and the state's ``as_of``; every other verdict is byte-identical to
    before, key order included.

    ``event_latch`` (engine.confluence_latch.EventLatch) makes the T2 event history immutable
    so the incomplete trailing bucket cannot un-fire an event on a bar that already printed.
    DEFAULT None = unchanged for every caller that does not opt in."""
    try:
        res = analyze(ticker, daily_close, reclaim_veto=reclaim_veto,
                      washout_waiver=washout_waiver)
    except Exception:
        res = None
    v = verdict(res)
    # Emitted ONLY when the waiver actually decided the verdict, so a run in which nothing
    # was waived serializes exactly as it did pre-change.
    _wr = _waiver_receipt(ticker, daily_close, v.get("last"))
    if _wr is not None:
        v["waiver"] = _wr
    # ---- owner's WEIGHTED tier cascade (T1 master -> T4 earliest), TIERED_CASCADE.md ----
    # Extends the take/pending/early leaf: T1 = the validated master (TAKE, or a forming
    # 'pending' master), T2/T3/T4 = the 2D-MACD-cross / 2D-projected / 2D-projected+2D-stoch
    # tiers computed close-only here. A T2/T4 name with no take/early still becomes eligible.
    take_active = (v.get("tier") == TAKE)
    last_m = v.get("last")
    is_buy = bool(last_m and last_m.get("type") in _BUY_TYPES)   # take OR forming 'pending'
    take_date = last_m.get("date") if is_buy else None           # age the arrow by its OWN date
    # The event date is a separate clock: the bucket's knowability close emitted by §7.
    # Pass it only when the producer supplied the field, preserving narrow monkeypatched
    # cascade signatures and legacy callers that predate the date family.
    _event_kw = ({"take_event_date": last_m.get("signal_date")}
                 if is_buy and "signal_date" in last_m else {})
    v["fresh_bars"] = _bars_since(daily_close, last_m) if is_buy else None
    # ...and the same count anchored on the bar the marker's bucket actually CLOSED on.
    # `fresh_bars` counts from the bucket's OPEN label, so it ages a signal by up to two
    # sessions it did not exist for (engine.signal_quality.marker_last_session). Emitted
    # ALONGSIDE rather than replacing: `fresh_bars` gates eligibility/FRESH_TICKS across
    # five boards and re-anchoring it is a semantic change owing a blast-radius report
    # (research/SQ_BUCKET_LABEL_AS_DATE_FINDINGS_2026-08-07.md §4). This field feeds the
    # DISPLAYED age only. None whenever the anchor is not derivable — a disclosed null.
    v["fresh_bars_knowable"] = (
        _knowable_bars(daily_close, last_m, market_of=ticker) if is_buy else None)
    # The 2D/3D buckets are anchored to a per-MARKET reference session calendar (R3). Inferring
    # it from the ticker suffix here is what lets every board (US/CN/HK/CA/Intl) route through
    # gate() and get the right calendar with no caller edit; unmapped suffixes resolve to US
    # openly (engine/session_anchor.market_for_ticker).
    market = session_anchor.market_for_ticker(ticker)
    # Pass the latch kwargs ONLY when a latch was supplied: every other caller — and the
    # several suites that monkeypatch cascade with a narrow stub — then see the exact call
    # signature they saw before, so opting in stays a strictly additive change.
    _latch_kw = ({"event_latch": event_latch, "latch_key": ticker}
                 if event_latch is not None else {})
    casc = confluence_tiers.cascade(daily_close, take_active=take_active,
                                    take_date=take_date, market=market,
                                    **_event_kw, **_latch_kw)
    topped = not casc.get("not_topped", True)
    tier_c = casc.get("tier")
    ticks = casc.get("ticks")
    v["ticks"] = ticks                                   # native-TF ticks since the cross/arrow
    fresh = (ticks is None) or (ticks <= confluence_tiers.FRESH_TICKS)   # just-crossed window
    # FRESHNESS + NOT-TOPPED gate (the AMAT / HON-after-10-days fix). A held 'take' makes the
    # name eligible in verdict() the whole time it is long (until a sell fires) -- but for a BUY
    # board that surfaces names that crossed several ticks ago and have been rising. cascade()
    # blesses the take as T1 ONLY while its arrow is JUST-crossed (<= FRESH_TICKS ticks old on the
    # 3D grid; 1 tick = 3 days, so 2 ticks ~= 6 days) AND momentum is still constructive. Otherwise
    # the name drops: it is a HOLD, not one of the "about to cross" / "just crossed" board buys.
    if take_active and tier_c != "T1":
        why = "topped/rolled-over" if topped else "risen for many days (cross 2+ ticks ago)"
        v.update(eligible=False, tier=None)
        _set_reason(v, f"held but {why} — no longer a fresh entry")
        # W0.2 Stage C near-miss annotation (Appendix A): stamped ONLY when the name
        # failed EXACTLY ONE condition — topped AND stale together is two failures,
        # which is a plain rejection, not a near-miss.
        if topped and not fresh:
            pass
        elif topped:
            v["near_miss_reason"] = "not_topped_veto"
        else:
            v["near_miss_reason"] = "freshness_expired"
    # A forming 'pending' master counts as T1, but only while it is JUST-fired (<= FRESH_TICKS)
    # and not already topping -- otherwise it too is stale and drops off the board.
    if tier_c is None and v.get("sub") == "pending":
        # `evaluated` gate (audit F2 2026-08-06): a CRASHED cascade returns a blank whose
        # not_topped=True / ticks=None read here as clean-and-fresh — awarding T1 off a
        # data failure. Missing key (older callers/fixtures) defaults True: only the
        # explicit crash marker refuses. The legitimate forming-master path (ticks=None
        # because no completed cross exists yet) is untouched — it carries evaluated=True.
        if not topped and fresh and casc.get("evaluated", True):
            tier_c = "T1"
        else:
            why = "already topping" if topped else "risen for many days"
            v.update(eligible=False, tier=None)
            _set_reason(v, f"forming master {why} — not a fresh entry")
            # W0.2 Stage C: same exactly-one near-miss rule as the held-take branch.
            if topped and not fresh:
                pass
            elif topped:
                v["near_miss_reason"] = "not_topped_veto"
            else:
                v["near_miss_reason"] = "freshness_expired"
    tier_event_date = casc.get("tier_event_date")
    tier_observed_date = casc.get("tier_observed_date")
    tier_observation_provisional = bool(casc.get("tier_observation_provisional"))
    if tier_c == "T1" and casc.get("tier") != "T1":
        # signal_gate's forming-master promotion is the one T1 path cascade() cannot name:
        # it deliberately receives take_active=False until the buy filter clears. The
        # marker's emitted close is authoritative; its confirmation is still pending.
        tier_event_date = _emitted_marker_event_date(daily_close, last_m)
        tier_observed_date = _observed_session_date(daily_close)
        tier_observation_provisional = True
    elif tier_c is None:
        tier_event_date = None
        tier_observed_date = None
        tier_observation_provisional = False
    v["tier_cascade"] = tier_c
    v["tier_event_date"] = tier_event_date
    v["tier_observed_date"] = tier_observed_date
    v["tier_observation_provisional"] = tier_observation_provisional
    v["weight"] = confluence_tiers.WEIGHTS.get(tier_c, 0.0)
    v["tier_sub"] = casc.get("sub")           # deep|shallow (display modifier; equal weight)
    v["bars_to_cross"] = casc.get("bars_to_cross")
    # 2D/3D RSI-MACD histogram (display-tier glyph feed for the boards' MACD D/2D/3D
    # column; sign → ▲/▼). Carried on every verdict incl. non-eligible — never a gate input.
    v["hist_d2"] = casc.get("hist_d2")
    v["hist_d3"] = casc.get("hist_d3")
    # PROVISIONAL-basis flag (W6 #22): a T3 grade is projected off the incomplete 2D resample
    # tail and repaints at a measured 23.8% US / 15.1% CN of fresh fires — above the ~15% flip
    # criterion (T1/T2 measured 5.3%/8.8%, fine). Boards badge it so the trader knows the tier
    # may vanish when the bucket completes (calibration/provisional_replay.json).
    v["provisional"] = bool(casc.get("provisional")) and tier_c == "T3"
    # HTF super-tier (S1/S2): display-only, rank-neutral, 2026-07-06.
    # Sourced from cascade() htf dict; defaults to False when absent (thin history / exception).
    _htf = casc.get("htf") or {}
    v["htf_s1"] = bool(_htf.get("s1", False))
    v["htf_s2"] = bool(_htf.get("s2", False))
    # ── warmup disclosure (2026-08-05 measured-floor change) ──────────────────────────────
    # young_history is the GRADED-COHORT LABEL: True = the name tiered on fewer daily bars
    # than the pre-change 200-bar floor, so the ledger can forever separate the pre/post
    # populations. Carried on every verdict, eligible or not.
    # None passes THROUGH (audit F5 2026-08-06): a cascade that never ran carries
    # young_history=None ("never got that far"); bool(None) stamped it into the MATURE
    # graded cohort — the exact above200-PLTR shape the era law forbids, two lines down
    # from the code that gets it right for above200.
    _yh = casc.get("young_history")
    v["young_history"] = None if _yh is None else bool(_yh)
    v["history_bars"] = casc.get("bars")
    v["null_legs"] = casc.get("null_legs") or {}
    # veto_legs_null names each NOT-TOPPED VETO leg the history could not check (F6/R4). It
    # rides beside null_legs for the same reason: the veto shipped `not_topped=True` on names
    # whose macd_bear leg was structurally unknowable, as if all three legs had been checked.
    v["veto_legs_null"] = casc.get("veto_legs_null") or {}
    # anchor_era is the graded-COHORT label for the bucketing era (R5) — it travels exactly
    # like young_history, onto every verdict and into the slim board dict. sq_anchor_era is
    # its §7 twin (R-SQ3), already seeded by verdict() above; re-asserting it here keeps the
    # two eras adjacent in the dict and makes a gate() verdict self-describing even if a
    # future caller hands in a hand-built verdict dict.
    v["anchor_era"] = casc.get("anchor_era")
    v["sq_anchor_era"] = signal_quality.ANCHOR_ERA
    # above200 HEALING, not widening. signal_quality.analyze needs ~270 daily bars, so it
    # returns None for a name the cascade can now grade — leaving above200 None on a series
    # whose 200dMA IS computable. Every consumer tests `is True`, so that None reads exactly
    # like False and the name silently leaves every lane (the PLTR narration gap, one layer
    # deeper). Fill ONLY from the cascade's own measurement and ONLY when the primary source
    # produced nothing; a genuinely unknowable 200dMA stays None and is named in null_legs.
    if v.get("above200") is None and casc.get("above200") is not None:
        v["above200"] = bool(casc.get("above200"))
    if tier_c and not v.get("eligible"):      # T2/T4 (or a fresh re-trigger) extend eligibility
        # NB this path can overwrite a blocked-buy reason (and its account): the name is no
        # longer surfaced as blocked, it is surfaced on the cascade tier, so the buy-filter
        # legs no longer explain the verdict. _set_reason drops the stale account with the
        # stale label — the two can never disagree.
        v.update(eligible=True)
        _set_reason(v, f"tier {tier_c} (weight {v['weight']})")
    v["result"] = res
    return v


def tier_rank(v: dict | None) -> int:
    """Ascending sort rank (0 = best). Operator-ratified 2026-07-06 order: T2 confirmed
    cross=0, T1 held take=1, T1 forming master (pending)=2, T3=3, T4=4. Non-eligible sinks."""
    if not v or not v.get("eligible"):
        return 9
    tc = v.get("tier_cascade")
    if tc == "T1" and v.get("sub") == "pending":
        return 2                              # forming master ranks just below T1 held and T2
    if tc:
        return _CASCADE_RANK.get(tc, 8)
    return _TIER_ORDER.get((v.get("tier"), v.get("sub")), 8)


def blend_sorted(items: list, base_of, verdict_of, reverse: bool = True, bonus_of=None,
                 *, tier_frac: float | None = None, wn_floor: float = 0.0) -> list:
    """Order `items` by the owner's WEIGHTED cascade blend (best first by default).

    Strict tier-first buries the earlier tiers whenever confirmed masters outnumber the board
    cap (US/CN). The owner asked for a WEIGHTED blend instead: a name's board score is its
    base-score PERCENTILE within the pool, lifted by 0.5 and SCALED by the cascade weight
    (T1 1.0 .. T4 0.4) -- so masters still dominate, but a strong-conviction T2/T3 outranks a
    weak master and surfaces. Percentile-based ⇒ robust to the per-market base scale
    (US/HK composite_z, CN/CA alpha/setup). `base_of(x)`->market rank score; `verdict_of(x)`->
    the signal_gate verdict (for .weight). Ineligible / weightless names sink (score 0).

    `bonus_of(x)` (optional) -> an ADDITIVE per-row lift on the 0..1 blend scale (e.g. the China
    2W-StochRSI washout-reclaim bonus, or a NEGATIVE anti-chase extension penalty). It is added on
    top of the tier×conviction blend, so a bonus of ~one TIER_FRAC lifts a row by roughly a full
    tier WHILE the cascade tier still orders rows that share the same bonus. Default None = no lift.

    `tier_frac` overrides the module TIER_FRAC (how much the tier vs conviction drives the blend);
    `wn_floor` COMPRESSES the tier weight toward parity — the normalised tier weight wn (T1→1 ..
    T4→0) is remapped to [wn_floor, 1], so wn_floor=0.6 means T4 still gets 60% of T1's tier credit.
    Both default to the US behaviour (unchanged callers). CHINA passes a lower tier_frac + a wn_floor
    so a FRESH T2/T3 competes with a fresh — but often already-extended — T1 (medium-term A-share
    momentum is dead; a confirmed breakout is frequently already run). Anti-chase is handled
    ORTHOGONALLY by the extension penalty in bonus_of, NOT by inverting the tier.
    See research/signal_engine/TIERED_CASCADE.md."""
    import bisect
    tf = TIER_FRAC if tier_frac is None else tier_frac
    wf = max(0.0, min(1.0, wn_floor))

    def _base(x):
        # `or 0.0` passes NaN through (NaN is truthy) — one NaN base left `vals` unsorted,
        # ranked the NaN row FIRST and corrupted EVERY row's bisect percentile (audit F7
        # 2026-08-06). NaN and None both mean "no basis": rank as 0.0.
        v = base_of(x)
        return 0.0 if v is None or v != v else float(v)

    vals = sorted(_base(x) for x in items)
    n = len(vals) or 1

    def _score(x):
        b = (bonus_of(x) if bonus_of else 0.0) or 0.0           # optional additive lift/penalty
        if b != b:
            b = 0.0                                              # NaN lift is no lift (F7 sibling)
        w = (verdict_of(x) or {}).get("weight") or 0.0
        if not w:
            return -1.0 + b
        wn = max(0.0, min(1.0, (w - 0.4) / 0.6))                 # T1->1.0 .. T4->0.0
        wn = wf + (1.0 - wf) * wn                                # compress toward parity (CN flatten)
        pct = bisect.bisect_right(vals, _base(x)) / n            # conviction percentile in pool
        return tf * wn + (1.0 - tf) * pct + b                    # convex blend + optional lift

    return sorted(items, key=_score, reverse=reverse)


def compact(v: dict | None) -> dict:
    """The display-safe verdict subset to attach to a grid card row (drops "result")."""
    if not v:
        return {"eligible": False, "tier": None, "sub": None, "reason": "no signal",
                "reasons": ["no signal"]}
    return {k: v.get(k) for k in _VERDICT_KEYS}


# the SLIM, fully JSON-safe verdict for the "what to buy" boards (Top-setups strip on
# us_stocks.html + the discovery Buy-zone picks). Unlike compact() it drops the §7 marker
# payload ("last"/"state"/...) — those can carry NaN, and the boards only need the tier +
# freshness — so it is safe to persist with allow_nan=False. is_buyable() reads from this.
_BUY_KEYS = ("eligible", "tier_cascade", "tier_sub", "ticks", "bars_to_cross", "provisional",
             "htf_s1", "htf_s2", "young_history", "anchor_era", "sq_anchor_era")


def buy_signal(v: dict | None) -> dict:
    """Slim, JSON-safe buy verdict: confluence tier + freshness + HTF badges, no markers."""
    if not v:
        # a BLANK is still a post-era row: the board persisted it under this anchor, so the
        # graded record must be able to place it in the right cohort (R5/R-SQ3). BOTH eras
        # ride along — the row was produced by both grids, blank or not.
        return {"eligible": False, "tier_cascade": None, "htf_s1": False, "htf_s2": False,
                "young_history": False, "anchor_era": confluence_tiers.ANCHOR_ERA,
                "sq_anchor_era": signal_quality.ANCHOR_ERA}
    return {k: v.get(k) for k in _BUY_KEYS}
