"""tests/test_flow_enrich.py — hermetic tests for engine/flow_enrich.py.

All tests are network-free: no clock reads, no R2, no Theta Terminal.

Coverage:
  1.  q_score parity — 3 hand-computed events match the formula exactly
  2.  q_score tier boundaries — ELITE/STRONG/HIGH/MEDIUM/LOW at exact thresholds
  3.  MULTI_LEG detector — fires on swept=True (live poller field)
  4.  MULTI_LEG detector — near-miss on swept=False/absent
  5.  MULTI_LEG detector — direction_discounted True when swept fires
  6.  LADDER detector — fires on >= 3 distinct strikes; near-miss on 2
  7.  REPEAT_HITTER detector — fires on >= 3 events for same root; near-miss on 2
  8.  SIZE_VS_OI detector — fires on vol_gt_oi=True + prem >= $500k; near-miss on prem < $500k
  9.  SIZE_VS_OI detector — near-miss on vol_gt_oi=None even with large premium
  10. WHALE detector — fires on prem >= $3M (hard floor)
  11. WHALE detector — fires on $1M + ~buy + z >= 2
  12. WHALE detector — near-miss on $1M + ~buy + z < 2
  13. FRESH detector — fires on vol_gt_oi=True + atm + 1d <= dte <= 45d
  14. FRESH detector — near-miss on mny=far_otm (correct vol/dte)
  15. FRESH detector — near-miss on dte=0 (0DTE)
  16. Z_OUTLIER detector — fires on premium_z >= 3.0; near-miss on 2.9
  17. direction_discounted flag — True when MULTI_LEG fires; False otherwise
  18. threshold computation — percentile ordering (elite >= strong >= high >= medium)
  19. threshold bootstrap flag — True when pool has one session_date
  20. threshold bootstrap flag — False when pool spans multiple session_dates
  21. enrich_feed end-to-end — correct schema keys present, including why/why_zh
  22. OI join — empty confirmed returns empty list + note
  23. OI join — matching contract returned in confirmed_yesterday
  24. envelope schema — required top-level keys all present
  25. q_score determinism check — same fields produce same score every time
  26. elite $1M floor enforcement — event with q >= elite threshold but premium < $1M is NOT elite
  27. elite $1M floor pass — event with q >= elite threshold AND premium >= $1M is elite
  28. bilingual why/why_zh — every enriched event has non-empty why and why_zh strings
"""
from __future__ import annotations

import math
import pytest

from engine import flow_enrich as fe

# ── helpers ───────────────────────────────────────────────────────────────────

SESSION_DATE = "2026-07-08"
ASOF         = "2026-07-08T16:00:00Z"


def _mk_event(
    root="NVDA", right="C", exp="2026-07-18", strike=800.0,
    dte=10, dte_bucket="8_30d", mny_bucket="atm",
    side="~buy", signing_source="tape",
    premium=1_000_000, premium_z=None,
    vol_gt_oi=None, repeated=False, n_prints=1,
    swept=False, zerodte=False,
    **extra,
) -> dict:
    """Make a minimal event dict for testing."""
    d = dict(
        id="test_id", ts=f"{SESSION_DATE}T14:00:00Z",
        root=root, right=right, exp=exp, strike=strike,
        dte=dte, dte_bucket=dte_bucket, mny_bucket=mny_bucket,
        side=side, signing_source=signing_source,
        premium=premium, premium_z=premium_z,
        vol_gt_oi=vol_gt_oi, repeated=repeated, n_prints=n_prints,
        swept=swept, zerodte=zerodte,
        group="Technology", group_zh="科技",
        size=100, avg_price=10.0,
        baseline_source="floor" if premium_z is None else "z252",
        session_date=SESSION_DATE,
    )
    d.update(extra)
    return d


# ════════════════════════════════════════════════════════════════════════════════
# 1–3. Q-score parity: hand-computed expected values
# ════════════════════════════════════════════════════════════════════════════════

def _hand_compute_q(ev: dict) -> int:
    """Reproduce the flowScore.ts formula in pure Python for hand-check."""
    premium       = float(ev.get("premium", 0) or 0)
    premium_z     = ev.get("premium_z")
    dte           = int(ev.get("dte", 0) or 0)
    dte_bucket    = str(ev.get("dte_bucket", ""))
    mny_bucket    = str(ev.get("mny_bucket", ""))
    vol_gt_oi     = ev.get("vol_gt_oi")
    repeated      = bool(ev.get("repeated", False))
    n_prints      = int(ev.get("n_prints", 1) or 1)
    side          = str(ev.get("side", "mixed"))
    signing_src   = str(ev.get("signing_source", "tape"))

    # Premium factor
    LO, HI = math.log(50_000), math.log(5_000_000)
    if premium <= 50_000:
        f_prem = 0.0
    elif premium >= 5_000_000:
        f_prem = 1.0
    else:
        f_prem = (math.log(premium) - LO) / (HI - LO)

    # Unusualness
    z = premium_z
    if z is None or z <= 0:
        f_unusual = 0.0
    elif z >= 4:
        f_unusual = 1.0
    else:
        f_unusual = z / 4.0

    # DTE
    if dte_bucket == "0d" or dte == 0:
        f_dte = 0.20
    elif 1 <= dte <= 45:
        f_dte = 1.0
    elif dte <= 90:
        f_dte = 1.0 - ((dte - 45) / 45.0) * 0.5
    else:
        f_dte = 0.30

    # Moneyness
    mny_map = {"atm": 1.0, "near_otm": 0.85, "itm": 0.50, "far_otm": 0.30}
    f_mny = mny_map.get(mny_bucket, 0.60)

    # Fresh
    if vol_gt_oi is True:
        f_fresh = 1.0
    elif vol_gt_oi is None:
        f_fresh = 0.60
    else:
        f_fresh = 0.40

    # Cluster
    base = 0.60 if repeated else 0.20
    print_bonus = min(0.40, math.log1p(max(0, n_prints - 1)) * 0.18)
    f_cluster = min(1.0, base + print_bonus)

    # Direction penalty
    is_mixed = side == "mixed"
    is_floor = signing_src == "floor"
    if is_mixed and is_floor:
        f_dir = -1.0
    elif is_mixed:
        f_dir = -0.75
    elif is_floor:
        f_dir = -0.40
    else:
        f_dir = -0.20

    raw = (f_prem * 0.30 + f_unusual * 0.20 + f_dte * 0.15 + f_fresh * 0.12
           + f_mny * 0.10 + f_cluster * 0.08 + f_dir * 0.05) * 100
    return int(round(min(100.0, max(0.0, raw))))


# Hand-computed test cases
_HAND_CASES = [
    # Case A: large premium, good z, atm, fresh, tape-signed ~buy, single print
    dict(premium=2_000_000, premium_z=3.5, dte=14, dte_bucket="8_30d",
         mny_bucket="atm", vol_gt_oi=True, repeated=False, n_prints=1,
         side="~buy", signing_source="tape"),
    # Case B: small premium, no z, far_otm, 0DTE, mixed
    dict(premium=100_000, premium_z=None, dte=0, dte_bucket="0d",
         mny_bucket="far_otm", vol_gt_oi=False, repeated=False, n_prints=1,
         side="mixed", signing_source="tape"),
    # Case C: whale-range premium, repeated, near_otm, ~sell, floor-signed
    dict(premium=5_000_000, premium_z=2.0, dte=30, dte_bucket="8_30d",
         mny_bucket="near_otm", vol_gt_oi=None, repeated=True, n_prints=5,
         side="~sell", signing_source="floor"),
]


@pytest.mark.parametrize("case_data", _HAND_CASES)
def test_q_score_matches_hand_computation(case_data):
    """Q-score must equal the hand-computed TS formula for each test case."""
    ev       = _mk_event(**case_data)
    expected = _hand_compute_q(case_data)
    result   = fe.compute_q_score(ev)
    assert result["q_score"] == expected, (
        f"q_score={result['q_score']} != expected={expected} for {case_data}"
    )


# ════════════════════════════════════════════════════════════════════════════════
# 2. Tier boundaries
# ════════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("score, expected_tier", [
    (100, "ELITE"), (90, "ELITE"), (89, "STRONG"), (80, "STRONG"),
    (79, "HIGH"),   (70, "HIGH"),  (69, "MEDIUM"), (60, "MEDIUM"),
    (59, "LOW"),    (0,  "LOW"),
])
def test_tier_boundaries(score, expected_tier):
    """_to_tier must produce correct tier at each boundary."""
    assert fe._to_tier(score) == expected_tier


# ════════════════════════════════════════════════════════════════════════════════
# 3–5. MULTI_LEG detector
# The live poller (engine/live_flow.py) emits `swept` (bool) — not has_multileg,
# spread_type, or cluster_type. The detector keys off `swept` only.
# ════════════════════════════════════════════════════════════════════════════════

def test_multi_leg_fires_on_swept_true():
    """MULTI_LEG fires when the poller's swept flag is True."""
    ev = _mk_event(swept=True)
    assert fe.detect_multi_leg(ev, [ev]) is True


def test_multi_leg_near_miss_swept_false():
    """MULTI_LEG does not fire when swept=False (the default)."""
    ev = _mk_event(swept=False)
    assert fe.detect_multi_leg(ev, [ev]) is False


def test_multi_leg_near_miss_swept_absent():
    """MULTI_LEG does not fire when swept key is absent."""
    ev = {k: v for k, v in _mk_event().items() if k != "swept"}
    assert fe.detect_multi_leg(ev, [ev]) is False


def test_multi_leg_direction_discounted_via_swept():
    """direction_discounted=True in the envelope when swept=True fires MULTI_LEG."""
    ev = _mk_event(swept=True)
    envelope = fe.build_enrich_envelope(
        [ev], SESSION_DATE, ASOF,
        thresholds=fe.compute_thresholds([ev]),
    )
    enriched = envelope["events"][0]
    assert "MULTI_LEG" in enriched["badges"]
    assert enriched["direction_discounted"] is True


# ════════════════════════════════════════════════════════════════════════════════
# 6. LADDER detector
# ════════════════════════════════════════════════════════════════════════════════

def _make_session_with_strikes(root, right, exp, strikes):
    return [_mk_event(root=root, right=right, exp=exp, strike=s) for s in strikes]


def test_ladder_fires_on_three_strikes():
    evs = _make_session_with_strikes("AAPL", "C", "2026-07-18", [150, 155, 160])
    assert fe.detect_ladder(evs[0], evs) is True


def test_ladder_near_miss_two_strikes():
    evs = _make_session_with_strikes("AAPL", "C", "2026-07-18", [150, 155])
    assert fe.detect_ladder(evs[0], evs) is False


def test_ladder_does_not_cross_right():
    """CALL and PUT strikes must not be combined for LADDER."""
    call_evs = _make_session_with_strikes("AAPL", "C", "2026-07-18", [150, 155])
    put_evs  = _make_session_with_strikes("AAPL", "P", "2026-07-18", [145])
    all_evs  = call_evs + put_evs
    # CALL event only sees 2 CALL strikes → no ladder
    assert fe.detect_ladder(call_evs[0], all_evs) is False


# ════════════════════════════════════════════════════════════════════════════════
# 7. REPEAT_HITTER detector
# ════════════════════════════════════════════════════════════════════════════════

def test_repeat_hitter_fires_on_three_events():
    evs = [_mk_event(root="MSFT") for _ in range(3)]
    assert fe.detect_repeat_hitter(evs[0], evs) is True


def test_repeat_hitter_near_miss_two_events():
    evs = [_mk_event(root="MSFT") for _ in range(2)]
    assert fe.detect_repeat_hitter(evs[0], evs) is False


def test_repeat_hitter_does_not_cross_root():
    msft = [_mk_event(root="MSFT"), _mk_event(root="MSFT")]
    aapl = [_mk_event(root="AAPL")]
    all_evs = msft + aapl
    # AAPL has only 1 event → not a repeat hitter
    assert fe.detect_repeat_hitter(aapl[0], all_evs) is False


# ════════════════════════════════════════════════════════════════════════════════
# 8–9. SIZE_VS_OI detector
# ════════════════════════════════════════════════════════════════════════════════

def test_size_vs_oi_fires_vol_gt_oi_and_large_premium():
    ev = _mk_event(vol_gt_oi=True, premium=600_000)
    assert fe.detect_size_vs_oi(ev, [ev]) is True


def test_size_vs_oi_near_miss_premium_below_floor():
    ev = _mk_event(vol_gt_oi=True, premium=499_000)
    assert fe.detect_size_vs_oi(ev, [ev]) is False


def test_size_vs_oi_near_miss_vol_gt_oi_none():
    ev = _mk_event(vol_gt_oi=None, premium=2_000_000)
    assert fe.detect_size_vs_oi(ev, [ev]) is False


def test_size_vs_oi_near_miss_vol_gt_oi_false():
    ev = _mk_event(vol_gt_oi=False, premium=2_000_000)
    assert fe.detect_size_vs_oi(ev, [ev]) is False


# ════════════════════════════════════════════════════════════════════════════════
# 10–12. WHALE detector
# ════════════════════════════════════════════════════════════════════════════════

def test_whale_fires_hard_floor_3M():
    ev = _mk_event(premium=3_000_000, side="~sell", premium_z=None)
    assert fe.detect_whale(ev, [ev]) is True


def test_whale_fires_hard_floor_above_3M():
    ev = _mk_event(premium=5_000_000, side="mixed", premium_z=None)
    assert fe.detect_whale(ev, [ev]) is True


def test_whale_fires_1M_buy_z_ge_2():
    ev = _mk_event(premium=1_200_000, side="~buy", premium_z=2.5)
    assert fe.detect_whale(ev, [ev]) is True


def test_whale_near_miss_1M_buy_z_lt_2():
    ev = _mk_event(premium=1_200_000, side="~buy", premium_z=1.9)
    assert fe.detect_whale(ev, [ev]) is False


def test_whale_near_miss_1M_sell_z_ge_2():
    """$1M with z >= 2 but side is ~sell: not whale (requires ~buy)."""
    ev = _mk_event(premium=1_200_000, side="~sell", premium_z=2.5)
    assert fe.detect_whale(ev, [ev]) is False


# ════════════════════════════════════════════════════════════════════════════════
# 13–15. FRESH detector
# ════════════════════════════════════════════════════════════════════════════════

def test_fresh_fires_vol_gt_oi_atm_middte():
    ev = _mk_event(vol_gt_oi=True, mny_bucket="atm", dte=14, dte_bucket="8_30d")
    assert fe.detect_fresh(ev, [ev]) is True


def test_fresh_fires_vol_gt_oi_near_otm():
    ev = _mk_event(vol_gt_oi=True, mny_bucket="near_otm", dte=7, dte_bucket="1_7d")
    assert fe.detect_fresh(ev, [ev]) is True


def test_fresh_near_miss_far_otm():
    ev = _mk_event(vol_gt_oi=True, mny_bucket="far_otm", dte=14, dte_bucket="8_30d")
    assert fe.detect_fresh(ev, [ev]) is False


def test_fresh_near_miss_0dte():
    ev = _mk_event(vol_gt_oi=True, mny_bucket="atm", dte=0, dte_bucket="0d")
    assert fe.detect_fresh(ev, [ev]) is False


def test_fresh_near_miss_dte_gt_45():
    ev = _mk_event(vol_gt_oi=True, mny_bucket="atm", dte=60, dte_bucket="31_90d")
    assert fe.detect_fresh(ev, [ev]) is False


# ════════════════════════════════════════════════════════════════════════════════
# 16. Z_OUTLIER detector
# ════════════════════════════════════════════════════════════════════════════════

def test_z_outlier_fires_ge_3():
    ev = _mk_event(premium_z=3.0)
    assert fe.detect_z_outlier(ev, [ev]) is True


def test_z_outlier_fires_above_3():
    ev = _mk_event(premium_z=5.5)
    assert fe.detect_z_outlier(ev, [ev]) is True


def test_z_outlier_near_miss_2_9():
    ev = _mk_event(premium_z=2.9)
    assert fe.detect_z_outlier(ev, [ev]) is False


def test_z_outlier_near_miss_none():
    ev = _mk_event(premium_z=None)
    assert fe.detect_z_outlier(ev, [ev]) is False


# ════════════════════════════════════════════════════════════════════════════════
# 17. direction_discounted flag
# ════════════════════════════════════════════════════════════════════════════════

def test_direction_discounted_true_when_multi_leg():
    """direction_discounted=True when MULTI_LEG fires (swept=True)."""
    ev = _mk_event(swept=True)
    envelope = fe.build_enrich_envelope(
        [ev], SESSION_DATE, ASOF,
        thresholds=fe.compute_thresholds([ev]),
    )
    assert len(envelope["events"]) == 1
    enriched = envelope["events"][0]
    assert "MULTI_LEG" in enriched["badges"]
    assert enriched["direction_discounted"] is True


def test_direction_discounted_false_without_multi_leg():
    """direction_discounted=False when swept=False (default)."""
    ev = _mk_event(swept=False)
    envelope = fe.build_enrich_envelope(
        [ev], SESSION_DATE, ASOF,
        thresholds=fe.compute_thresholds([ev]),
    )
    enriched = envelope["events"][0]
    assert enriched["direction_discounted"] is False


# ════════════════════════════════════════════════════════════════════════════════
# 18–20. Threshold computation
# ════════════════════════════════════════════════════════════════════════════════

def test_thresholds_ordering():
    """elite >= strong >= high >= medium for any non-trivial pool."""
    pool = [
        _mk_event(premium=5_000_000, premium_z=4.0, mny_bucket="atm", dte=14,
                  vol_gt_oi=True, repeated=True, n_prints=5, session_date="2026-07-07"),
        _mk_event(premium=500_000,   premium_z=1.0, mny_bucket="far_otm", dte=0,
                  session_date="2026-07-07"),
        _mk_event(premium=1_000_000, premium_z=None, mny_bucket="near_otm", dte=30,
                  session_date="2026-07-07"),
    ]
    t = fe.compute_thresholds(pool)
    assert t["elite"] >= t["strong"] >= t["high"] >= t["medium"]


def test_thresholds_bootstrap_one_session():
    pool = [_mk_event(session_date="2026-07-08")]
    t = fe.compute_thresholds(pool)
    assert t["bootstrap"] is True


def test_thresholds_bootstrap_multi_session():
    pool = [
        _mk_event(session_date="2026-07-07"),
        _mk_event(session_date="2026-07-08"),
    ]
    t = fe.compute_thresholds(pool)
    assert t["bootstrap"] is False


def test_thresholds_empty_pool():
    t = fe.compute_thresholds([])
    assert t["n"] == 0
    assert t["bootstrap"] is True
    assert t["elite"] == 0.0


# ════════════════════════════════════════════════════════════════════════════════
# 21. enrich_feed end-to-end
# ════════════════════════════════════════════════════════════════════════════════

def test_enrich_feed_schema_keys():
    feed = {
        "schema": "live_flow.feed/v1",
        "asof": ASOF,
        "session_date": SESSION_DATE,
        "events": [_mk_event()],
    }
    envelope = fe.enrich_feed(feed, ASOF)
    required = {"schema", "asof", "session_date", "thresholds", "bootstrap",
                "n_events", "events", "confirmed_yesterday"}
    assert required.issubset(envelope.keys())
    assert envelope["schema"] == "flow.enrich/v1"
    assert envelope["n_events"] == 1
    ev = envelope["events"][0]
    assert "q_score" in ev
    assert "q_tier" in ev
    assert "badges" in ev
    assert "direction_discounted" in ev
    assert "components" in ev
    # bilingual why-strings (spec §4)
    assert "why" in ev
    assert "why_zh" in ev
    assert isinstance(ev["why"], str) and len(ev["why"]) > 0
    assert isinstance(ev["why_zh"], str) and len(ev["why_zh"]) > 0


def test_enrich_feed_empty_events():
    feed = {"schema": "live_flow.feed/v1", "asof": ASOF,
            "session_date": SESSION_DATE, "events": []}
    envelope = fe.enrich_feed(feed, ASOF)
    assert envelope["n_events"] == 0
    assert envelope["events"] == []


# ════════════════════════════════════════════════════════════════════════════════
# 22–23. OI join
# ════════════════════════════════════════════════════════════════════════════════

def test_oi_join_empty_confirmed():
    """Empty confirmed list → empty result + explanatory note."""
    oi = {"schema": "options_hub.oi_confirmed/v1", "asof": "2026-07-06",
          "confirmed": []}
    evs = [_mk_event(ts="2026-07-07T14:00:00Z")]
    confirmed_yday, note = fe.join_oi_confirmed(evs, oi, SESSION_DATE)
    assert confirmed_yday == []
    assert note is not None
    assert len(note) > 0


def test_oi_join_matching_contract():
    """A yesterday event matching an OI confirmed contract is returned."""
    yesterday_ts = "2026-07-07T14:00:00Z"  # day before SESSION_DATE 2026-07-08
    ev = _mk_event(root="TSLA", right="C", exp="2026-07-18", strike=250.0,
                   ts=yesterday_ts)
    oi = {
        "schema": "options_hub.oi_confirmed/v1",
        "asof": "2026-07-07",
        "confirmed": [
            {"root": "TSLA", "right": "C", "exp": "2026-07-18", "strike": 250.0}
        ],
    }
    confirmed_yday, note = fe.join_oi_confirmed([ev], oi, SESSION_DATE)
    assert len(confirmed_yday) == 1
    assert confirmed_yday[0]["root"] == "TSLA"
    assert note is None


def test_oi_join_non_matching_contract():
    """A yesterday event with different strike does NOT match."""
    yesterday_ts = "2026-07-07T14:00:00Z"
    ev = _mk_event(root="TSLA", right="C", exp="2026-07-18", strike=260.0,
                   ts=yesterday_ts)
    oi = {
        "schema": "options_hub.oi_confirmed/v1",
        "asof": "2026-07-07",
        "confirmed": [
            {"root": "TSLA", "right": "C", "exp": "2026-07-18", "strike": 250.0}
        ],
    }
    confirmed_yday, note = fe.join_oi_confirmed([ev], oi, SESSION_DATE)
    assert confirmed_yday == []
    assert note is None  # join ran, just found nothing


# ════════════════════════════════════════════════════════════════════════════════
# 24. Envelope required keys
# ════════════════════════════════════════════════════════════════════════════════

def test_envelope_has_required_keys():
    ev = _mk_event()
    envelope = fe.build_enrich_envelope(
        [ev], SESSION_DATE, ASOF,
        thresholds=fe.compute_thresholds([ev]),
        oi_confirmed={"schema": "options_hub.oi_confirmed/v1",
                      "asof": "2026-07-06", "confirmed": []},
    )
    required = {"schema", "asof", "session_date", "thresholds", "bootstrap",
                "n_events", "events", "confirmed_yesterday", "oi_confirm_note"}
    assert required.issubset(envelope.keys())


# ════════════════════════════════════════════════════════════════════════════════
# 25. Q-score determinism — same event fields produce same score every time.
# (Weights are registered against FLOW_INTELLIGENCE_V2_SPEC.md §3, not a TS file.)
# ════════════════════════════════════════════════════════════════════════════════

def test_q_score_deterministic():
    """Same event dict must produce the same q_score every time."""
    ev = _mk_event(premium=2_500_000, premium_z=2.0, dte=21, dte_bucket="8_30d",
                   mny_bucket="near_otm", vol_gt_oi=True, repeated=True, n_prints=3,
                   side="~buy", signing_source="tape")
    s1 = fe.compute_q_score(ev)["q_score"]
    s2 = fe.compute_q_score(ev)["q_score"]
    assert s1 == s2


def test_q_score_components_sum_matches_score():
    """Sum of component values (with penalty negative) must round to q_score."""
    ev = _mk_event(premium=1_500_000, premium_z=2.5, dte=14, dte_bucket="8_30d",
                   mny_bucket="atm", vol_gt_oi=True, repeated=False, n_prints=1,
                   side="~buy", signing_source="tape")
    result = fe.compute_q_score(ev)
    total  = sum(c["value"] for c in result["components"])
    assert int(round(min(100.0, max(0.0, total)))) == result["q_score"]


# ════════════════════════════════════════════════════════════════════════════════
# 26–27. Elite $1M floor enforcement (spec §3: ELITE requires q >= threshold AND premium >= $1M)
# ════════════════════════════════════════════════════════════════════════════════

def test_elite_floor_blocks_low_premium_high_q():
    """An event with q >= elite threshold but premium < $1M must NOT get session_tier='elite'."""
    # Use a pool with known low premium to drive elite threshold low (e.g. ~50),
    # then present an event with q well above that threshold but premium = $300k.
    pool = [
        _mk_event(premium=200_000, premium_z=None, mny_bucket="far_otm", dte=0,
                  session_date="2026-07-07"),
        _mk_event(premium=150_000, premium_z=None, mny_bucket="far_otm", dte=0,
                  session_date="2026-07-07"),
    ]
    thresh = fe.compute_thresholds(pool)
    # A high-q event with premium $300k (below _ELITE_PREM_FLOOR of $1M)
    ev = _mk_event(premium=300_000, premium_z=4.0, mny_bucket="atm", dte=14,
                   vol_gt_oi=True, repeated=True, n_prints=5)
    q = fe.compute_q_score(ev)["q_score"]
    # Verify that q is above the elite threshold (precondition for this test to be meaningful)
    assert q >= thresh["elite"], (
        f"Test precondition failed: q={q} < elite={thresh['elite']}; "
        "adjust pool to lower the threshold"
    )
    envelope = fe.build_enrich_envelope([ev], SESSION_DATE, ASOF, thresholds=thresh)
    result_tier = envelope["events"][0]["session_tier"]
    assert result_tier != "elite", (
        f"Expected NOT elite (premium $300k < $1M floor) but got {result_tier!r}"
    )


def test_elite_floor_passes_high_premium_high_q():
    """An event with q >= elite threshold AND premium >= $1M must get session_tier='elite'."""
    pool = [
        _mk_event(premium=200_000, premium_z=None, mny_bucket="far_otm", dte=0,
                  session_date="2026-07-07"),
        _mk_event(premium=150_000, premium_z=None, mny_bucket="far_otm", dte=0,
                  session_date="2026-07-07"),
    ]
    thresh = fe.compute_thresholds(pool)
    ev = _mk_event(premium=1_500_000, premium_z=4.0, mny_bucket="atm", dte=14,
                   vol_gt_oi=True, repeated=True, n_prints=5)
    q = fe.compute_q_score(ev)["q_score"]
    assert q >= thresh["elite"], (
        f"Test precondition failed: q={q} < elite={thresh['elite']}"
    )
    envelope = fe.build_enrich_envelope([ev], SESSION_DATE, ASOF, thresholds=thresh)
    result_tier = envelope["events"][0]["session_tier"]
    assert result_tier == "elite", (
        f"Expected elite (premium $1.5M >= $1M floor, q={q} >= {thresh['elite']}) "
        f"but got {result_tier!r}"
    )


# ════════════════════════════════════════════════════════════════════════════════
# 28. Bilingual why/why_zh present and non-empty on every enriched event
# ════════════════════════════════════════════════════════════════════════════════

def test_bilingual_why_strings_present_on_all_events():
    """Every event in the envelope must carry non-empty why and why_zh strings."""
    events = [
        _mk_event(root="AAPL", swept=True),        # will have MULTI_LEG badge
        _mk_event(root="TSLA", premium=4_000_000),  # will have WHALE badge
        _mk_event(root="NVDA"),                     # no badges expected
    ]
    envelope = fe.build_enrich_envelope(
        events, SESSION_DATE, ASOF,
        thresholds=fe.compute_thresholds(events),
    )
    for ev in envelope["events"]:
        assert "why" in ev, f"missing 'why' for {ev.get('root')}"
        assert "why_zh" in ev, f"missing 'why_zh' for {ev.get('root')}"
        assert isinstance(ev["why"], str) and len(ev["why"]) > 0, (
            f"empty 'why' for {ev.get('root')}"
        )
        assert isinstance(ev["why_zh"], str) and len(ev["why_zh"]) > 0, (
            f"empty 'why_zh' for {ev.get('root')}"
        )


def test_bilingual_why_zh_is_chinese_for_whale():
    """An event that fires WHALE should have Chinese characters in why_zh."""
    ev = _mk_event(premium=4_000_000)
    envelope = fe.build_enrich_envelope(
        [ev], SESSION_DATE, ASOF,
        thresholds=fe.compute_thresholds([ev]),
    )
    enriched = envelope["events"][0]
    assert "WHALE" in enriched["badges"]
    # Chinese characters have codepoints in the CJK Unified Ideographs range
    has_chinese = any("一" <= ch <= "鿿" for ch in enriched["why_zh"])
    assert has_chinese, f"why_zh contains no Chinese characters: {enriched['why_zh']!r}"
