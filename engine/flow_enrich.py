"""engine/flow_enrich.py — display-tier flow enrichment engine (DISPLAY-TIER, hermetic).

Pure functions: no network calls, no clock reads, no randomness.
Takes a list of live_flow.feed/v1 event dicts (from feed_current.json) and
emits a list of enriched events per the flow.enrich/v1 schema (§5 of brief).

Detectors (all deterministic, no LLM):
  MULTI_LEG    — has_multileg or cluster with spread_type present
  LADDER       — repeated contract appearing across multiple strikes (same root/right/exp)
  REPEAT_HITTER — same root hits notable threshold in >= 3 distinct events in the session
  SIZE_VS_OI   — size > OI (vol_gt_oi == True with premium >= $500k floor)
  WHALE        — premium >= $1M AND (side == ~buy) AND premium_z >= 2 (if available) OR
                  premium >= $3M regardless of z (floor-based whale)
  FRESH        — vol_gt_oi == True AND mny_bucket in (atm, near_otm) AND dte in (1..45)
  Z_OUTLIER    — premium_z >= 3.0

Q-score: port of terminal/lib/flowScore.ts formula (weights copied exactly).
  premiumMagnitude   0.30  log ramp $50k → $5M
  unusualness        0.20  z-score cap at z=4
  dteRelevance       0.15  0DTE=0.20, 1-45d=1.0, taper to 0.5@90d, 0.30>90d
  freshPositioning   0.12  vol_gt_oi: True=1.0, None=0.60, False=0.40
  moneynessProximity 0.10  atm=1.0, near_otm=0.85, itm=0.50, far_otm=0.30, unknown=0.60
  repeatCluster      0.08  repeated+n_prints bonus
  directionPenalty  -0.05  mixed+floor=-1.0, mixed=-0.75, floor=-0.40, tape=-0.20

Thresholds (trailing-sessions percentiles):
  elite  = top 2%  with $1M floor
  strong = top 10%
  high   = top 25%
  medium = top 50%

HOUSE LAWS (binding):
  - Display-tier only; no user-facing "signal" or "validated" strings.
  - direction_discounted=True whenever MULTI_LEG fires (direction ambiguous on spreads).
  - EARNINGS_WINDOW detector skipped (no PIT-clean earnings source consumable inline).
  - OI data comes from event field vol_gt_oi (OI[t-1] law already honoured upstream).
"""
from __future__ import annotations

import math
import logging
from typing import Any

log = logging.getLogger(__name__)

# ── Q-score weights (must match flowScore.ts exactly) ────────────────────────
_W_PREM    = 0.30
_W_UNUSUAL = 0.20
_W_DTE     = 0.15
_W_FRESH   = 0.12
_W_MNY     = 0.10
_W_CLUSTER = 0.08
_W_DIR_PEN = 0.05  # penalty weight (factor is ≤ 0)

# ── detector thresholds ───────────────────────────────────────────────────────
_WHALE_FLOOR_HARD    = 3_000_000   # $3M — qualifies regardless of z
_WHALE_FLOOR_SOFT    = 1_000_000   # $1M + z >= 2 + side ~buy
_WHALE_Z_MIN         = 2.0
_SIZE_VS_OI_PREM_MIN = 500_000     # $500k floor for SIZE_VS_OI badge
_Z_OUTLIER_MIN       = 3.0
_REPEAT_HITTER_MIN   = 3           # root must appear in >= 3 events

# ── elite q-score floor ───────────────────────────────────────────────────────
_ELITE_PREM_FLOOR    = 1_000_000   # $1M — elite badge requires this minimum premium

# ── tier cutoffs (from flowScore.ts toTier) ──────────────────────────────────
_TIER_ELITE  = 90
_TIER_STRONG = 80
_TIER_HIGH   = 70
_TIER_MEDIUM = 60


# ═══════════════════════════════════════════════════════════════════════════════
# Internal Q-score helpers (ported 1-for-1 from flowScore.ts)
# ═══════════════════════════════════════════════════════════════════════════════

def _premium_factor(premium: float) -> float:
    """Log ramp: $50k → 0.0, $5M → 1.0, linear in log space."""
    LO = math.log(50_000)
    HI = math.log(5_000_000)
    if premium <= 50_000:
        return 0.0
    if premium >= 5_000_000:
        return 1.0
    return (math.log(premium) - LO) / (HI - LO)


def _unusualness_factor(z: float | None) -> float:
    """z ≤ 0 → 0, z ≥ 4 → 1, linear between."""
    if z is None:
        return 0.0
    if z <= 0:
        return 0.0
    if z >= 4:
        return 1.0
    return z / 4.0


def _dte_factor(dte: int, dte_bucket: str) -> float:
    """0DTE=0.20, 1-45d=1.0, taper 45→90d to 0.5, >90d=0.30."""
    if dte_bucket == "0d" or dte == 0:
        return 0.20
    if 1 <= dte <= 45:
        return 1.0
    if dte <= 90:
        return 1.0 - ((dte - 45) / 45.0) * 0.5
    return 0.30


def _moneyness_factor(mny_bucket: str) -> float:
    """atm=1.0, near_otm=0.85, itm=0.50, far_otm=0.30, else 0.60 (unknown)."""
    return {
        "atm":      1.00,
        "near_otm": 0.85,
        "itm":      0.50,
        "far_otm":  0.30,
    }.get(mny_bucket, 0.60)


def _fresh_factor(vol_gt_oi: bool | None) -> float:
    """True=1.0, None=0.60, False=0.40."""
    if vol_gt_oi is True:
        return 1.0
    if vol_gt_oi is None:
        return 0.60
    return 0.40


def _cluster_factor(repeated: bool, n_prints: int) -> float:
    """Repeat/cluster bonus: base=0.60 if repeated else 0.20, log bonus per extra print."""
    base = 0.60 if repeated else 0.20
    print_bonus = min(0.40, math.log1p(max(0, n_prints - 1)) * 0.18)
    return min(1.0, base + print_bonus)


def _direction_penalty(side: str, signing_source: str) -> float:
    """Penalty factor ≤ 0. Applied with weight 0.05 so max penalty = 5 pts."""
    is_mixed = side == "mixed"
    is_floor = signing_source == "floor"
    if is_mixed and is_floor:
        return -1.0
    if is_mixed:
        return -0.75
    if is_floor:
        return -0.40
    return -0.20


def _to_tier(score: int) -> str:
    if score >= _TIER_ELITE:
        return "ELITE"
    if score >= _TIER_STRONG:
        return "STRONG"
    if score >= _TIER_HIGH:
        return "HIGH"
    if score >= _TIER_MEDIUM:
        return "MEDIUM"
    return "LOW"


def compute_q_score(event: dict) -> dict:
    """Compute the flow conviction q-score for a single live_flow.feed/v1 event.

    Returns dict with:
      q_score   : int 0-100
      q_tier    : str ELITE|STRONG|HIGH|MEDIUM|LOW
      components: list of {key, value, weight} dicts (for display decomposition)

    Deterministic: depends only on the event dict fields; no network/clock.
    """
    premium       = float(event.get("premium", 0) or 0)
    premium_z     = event.get("premium_z")
    dte           = int(event.get("dte", 0) or 0)
    dte_bucket    = str(event.get("dte_bucket", "") or "")
    mny_bucket    = str(event.get("mny_bucket", "") or "")
    vol_gt_oi     = event.get("vol_gt_oi")
    repeated      = bool(event.get("repeated", False))
    n_prints      = int(event.get("n_prints", 1) or 1)
    side          = str(event.get("side", "mixed") or "mixed")
    signing_src   = str(event.get("signing_source", "tape") or "tape")

    f_prem    = _premium_factor(premium)
    f_unusual = _unusualness_factor(premium_z)
    f_dte     = _dte_factor(dte, dte_bucket)
    f_fresh   = _fresh_factor(vol_gt_oi)
    f_mny     = _moneyness_factor(mny_bucket)
    f_cluster = _cluster_factor(repeated, n_prints)
    f_dir_pen = _direction_penalty(side, signing_src)  # ≤ 0

    c_prem    = f_prem    * _W_PREM    * 100
    c_unusual = f_unusual * _W_UNUSUAL * 100
    c_dte     = f_dte     * _W_DTE     * 100
    c_fresh   = f_fresh   * _W_FRESH   * 100
    c_mny     = f_mny     * _W_MNY     * 100
    c_cluster = f_cluster * _W_CLUSTER * 100
    c_dir_pen = f_dir_pen * _W_DIR_PEN * 100  # negative

    raw_total = c_prem + c_unusual + c_dte + c_fresh + c_mny + c_cluster + c_dir_pen
    score     = int(round(min(100.0, max(0.0, raw_total))))
    tier      = _to_tier(score)

    components = [
        {"key": "premiumMagnitude",    "value": round(c_prem,    1), "weight": _W_PREM},
        {"key": "unusualness",         "value": round(c_unusual, 1), "weight": _W_UNUSUAL},
        {"key": "dteRelevance",        "value": round(c_dte,     1), "weight": _W_DTE},
        {"key": "freshPositioning",    "value": round(c_fresh,   1), "weight": _W_FRESH},
        {"key": "moneynessProximity",  "value": round(c_mny,     1), "weight": _W_MNY},
        {"key": "repeatCluster",       "value": round(c_cluster, 1), "weight": _W_CLUSTER},
        {"key": "directionPenalty",    "value": round(c_dir_pen, 1), "weight": _W_DIR_PEN},
    ]

    return {"q_score": score, "q_tier": tier, "components": components}


# ═══════════════════════════════════════════════════════════════════════════════
# Detectors — each takes (event, session_events) and returns bool
# All are pure functions; OI data comes from event["vol_gt_oi"] only.
# ═══════════════════════════════════════════════════════════════════════════════

def detect_multi_leg(event: dict, _session_events: list[dict]) -> bool:
    """MULTI_LEG: has_multileg flag OR cluster with a spread_type.

    Both fields are upstream-set (from poller/engine). On the feed/v1 schema
    these are not present as top-level keys; the swept field covers part of the
    spread territory. We check 'has_multileg', 'spread_type', and 'cluster_type'
    fields if they are present on the event.
    """
    if event.get("has_multileg"):
        return True
    # spread_type present and non-empty → multi-leg spread
    spread = event.get("spread_type") or ""
    if spread:
        return True
    # cluster_type present → accumulated / iceberg / cluster
    cluster = event.get("cluster_type") or ""
    if cluster:
        return True
    return False


def detect_ladder(event: dict, session_events: list[dict]) -> bool:
    """LADDER: the same root+right+exp appears across >= 3 distinct strike levels.

    Indicates accumulation or a structured ladder of strikes on one expiry.
    """
    root  = event.get("root", "")
    right = event.get("right", "")
    exp   = event.get("exp", "")
    if not (root and right and exp):
        return False

    strikes: set[float] = set()
    for ev in session_events:
        if (ev.get("root") == root
                and ev.get("right") == right
                and ev.get("exp") == exp):
            s = ev.get("strike")
            if s is not None:
                try:
                    strikes.add(float(s))
                except (TypeError, ValueError):
                    pass

    return len(strikes) >= 3


def detect_repeat_hitter(event: dict, session_events: list[dict]) -> bool:
    """REPEAT_HITTER: the same root appears in >= 3 distinct events in the session."""
    root = event.get("root", "")
    if not root:
        return False
    count = sum(1 for ev in session_events if ev.get("root") == root)
    return count >= _REPEAT_HITTER_MIN


def detect_size_vs_oi(event: dict, _session_events: list[dict]) -> bool:
    """SIZE_VS_OI: vol > OI (vol_gt_oi=True) AND premium >= $500k floor."""
    if event.get("vol_gt_oi") is not True:
        return False
    return float(event.get("premium", 0) or 0) >= _SIZE_VS_OI_PREM_MIN


def detect_whale(event: dict, _session_events: list[dict]) -> bool:
    """WHALE: premium >= $3M (hard floor), OR ($1M + side=~buy + premium_z >= 2)."""
    premium = float(event.get("premium", 0) or 0)
    if premium >= _WHALE_FLOOR_HARD:
        return True
    if premium >= _WHALE_FLOOR_SOFT:
        if event.get("side") == "~buy":
            z = event.get("premium_z")
            if z is not None and float(z) >= _WHALE_Z_MIN:
                return True
    return False


def detect_fresh(event: dict, _session_events: list[dict]) -> bool:
    """FRESH: vol > OI AND moneyness is atm or near_otm AND dte in [1, 45]."""
    if event.get("vol_gt_oi") is not True:
        return False
    mny = event.get("mny_bucket", "")
    if mny not in ("atm", "near_otm"):
        return False
    dte = int(event.get("dte", 0) or 0)
    return 1 <= dte <= 45


def detect_z_outlier(event: dict, _session_events: list[dict]) -> bool:
    """Z_OUTLIER: premium_z >= 3.0 (vs 252-session baseline)."""
    z = event.get("premium_z")
    if z is None:
        return False
    try:
        return float(z) >= _Z_OUTLIER_MIN
    except (TypeError, ValueError):
        return False


# ── detector registry (ordered for badge output) ─────────────────────────────

_DETECTORS: list[tuple[str, Any]] = [
    ("MULTI_LEG",     detect_multi_leg),
    ("LADDER",        detect_ladder),
    ("REPEAT_HITTER", detect_repeat_hitter),
    ("SIZE_VS_OI",    detect_size_vs_oi),
    ("WHALE",         detect_whale),
    ("FRESH",         detect_fresh),
    ("Z_OUTLIER",     detect_z_outlier),
]


# ═══════════════════════════════════════════════════════════════════════════════
# Threshold computation — trailing-sessions percentiles
# ═══════════════════════════════════════════════════════════════════════════════

def compute_thresholds(session_events_pool: list[dict]) -> dict:
    """Compute q-score percentile thresholds from a pool of events (trailing sessions).

    Uses the pool to compute each event's q-score, then derives:
      elite  = max(top 2% q-score, _ELITE_PREM_FLOOR-equivalent guard)
      strong = top 10%
      high   = top 25%
      medium = top 50%

    elite has a $1M minimum premium floor: events below $1M cannot qualify as elite
    even if their q-score is ≥ threshold.

    Returns:
      {
        "elite":  float,  "strong": float, "high": float, "medium": float,
        "n":      int,
        "bootstrap": bool  (True when pool has only one session — less stable)
      }

    If pool is empty, returns zeros with bootstrap=True.
    """
    if not session_events_pool:
        return {"elite": 0.0, "strong": 0.0, "high": 0.0, "medium": 0.0,
                "n": 0, "bootstrap": True}

    scores = []
    for ev in session_events_pool:
        try:
            r = compute_q_score(ev)
            scores.append(r["q_score"])
        except Exception:  # noqa: BLE001
            pass

    if not scores:
        return {"elite": 0.0, "strong": 0.0, "high": 0.0, "medium": 0.0,
                "n": 0, "bootstrap": True}

    scores.sort(reverse=True)
    n = len(scores)

    def _pct_val(pct: float) -> float:
        """top-pct value: e.g. top 2% → index = floor(n * 0.02)."""
        idx = max(0, min(n - 1, int(n * pct)))
        return float(scores[idx])

    elite_raw = _pct_val(0.02)
    strong    = _pct_val(0.10)
    high      = _pct_val(0.25)
    medium    = _pct_val(0.50)

    # Elite guard: must be at least the score corresponding to a $1M event
    # Compute a reference score for a $1M, 14d, atm, vol_gt_oi=None, not repeated event
    _ref_elite_event = {
        "premium": _ELITE_PREM_FLOOR,
        "premium_z": None,
        "dte": 14, "dte_bucket": "8_30d",
        "mny_bucket": "atm",
        "vol_gt_oi": None,
        "repeated": False, "n_prints": 1,
        "side": "~buy", "signing_source": "tape",
    }
    ref_score = compute_q_score(_ref_elite_event)["q_score"]
    elite = max(elite_raw, float(ref_score))

    # Unique sessions count: use the presence of multiple session_date values
    session_dates = {ev.get("session_date", "unknown") for ev in session_events_pool
                     if isinstance(ev, dict)}
    bootstrap = len(session_dates) <= 1

    return {
        "elite":  round(elite, 1),
        "strong": round(strong, 1),
        "high":   round(high, 1),
        "medium": round(medium, 1),
        "n":      n,
        "bootstrap": bootstrap,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# OI-confirmation join
# ═══════════════════════════════════════════════════════════════════════════════

def join_oi_confirmed(session_events: list[dict],
                      oi_confirmed: dict,
                      session_date: str) -> tuple[list[dict], str | None]:
    """Join yesterday's events against options_hub/oi_confirmed.json.

    The oi_confirmed artifact has schema options_hub.oi_confirmed/v1 with:
      confirmed: list of dicts (currently empty per live data check)

    Strategy: match on (root, right, strike, exp) — any yesterday's event whose
    contract appears in oi_confirmed.confirmed is returned as confirmed_yesterday.

    Returns:
      (confirmed_yesterday: list[dict], oi_confirm_note: str | None)

    If the artifact is empty or the join produces no matches, returns ([], note).
    """
    confirmed_list = oi_confirmed.get("confirmed", [])
    if not isinstance(confirmed_list, list) or not confirmed_list:
        note = (f"oi_confirmed.json has confirmed=[] (asof {oi_confirmed.get('asof','?')}); "
                "no OI confirmation join possible — emitting empty list.")
        return [], note

    # Build lookup: (root, right, exp, strike_rounded) → True
    confirmed_set: set[tuple] = set()
    for entry in confirmed_list:
        try:
            key = (
                str(entry.get("root", "") or entry.get("ticker", "") or "").upper(),
                str(entry.get("right", "") or entry.get("option_type", "") or "").upper()[:1],
                str(entry.get("exp", "") or entry.get("expiry", "") or "")[:10],
                round(float(entry.get("strike", 0) or 0), 3),
            )
            confirmed_set.add(key)
        except (TypeError, ValueError):
            pass

    # Match yesterday's events
    import datetime as _dt
    try:
        sess_dt   = _dt.datetime.strptime(session_date, "%Y-%m-%d").date()
        yesterday = (sess_dt - _dt.timedelta(days=1)).strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        yesterday = ""

    confirmed_yesterday: list[dict] = []
    for ev in session_events:
        ev_date = (ev.get("ts", "") or "")[:10]
        if ev_date != yesterday:
            continue
        try:
            key = (
                str(ev.get("root", "")).upper(),
                str(ev.get("right", "")).upper()[:1],
                str(ev.get("exp", ""))[:10],
                round(float(ev.get("strike", 0) or 0), 3),
            )
            if key in confirmed_set:
                confirmed_yesterday.append(ev)
        except (TypeError, ValueError):
            pass

    return confirmed_yesterday, None


# ═══════════════════════════════════════════════════════════════════════════════
# Envelope builder — flow.enrich/v1
# ═══════════════════════════════════════════════════════════════════════════════

def build_enrich_envelope(
    feed_events: list[dict],
    session_date: str,
    asof: str,
    thresholds: dict,
    oi_confirmed: dict | None = None,
    *,
    bootstrap: bool = False,
) -> dict:
    """Build the flow.enrich/v1 envelope.

    Runs all detectors over every event, computes q-scores, applies badges,
    joins OI confirmation, and returns the complete envelope.

    Parameters
    ----------
    feed_events    : events from live_flow.feed/v1 (list of dicts).
    session_date   : "YYYY-MM-DD" — trading session for which this enrichment applies.
    asof           : ISO-8601 timestamp for this enrichment run.
    thresholds     : output of compute_thresholds() (trailing-session percentiles).
    oi_confirmed   : the options_hub/oi_confirmed.json dict; None = skip join.
    bootstrap      : whether thresholds were computed from a single-session pool.

    Returns
    -------
    dict matching schema flow.enrich/v1
    """
    enriched: list[dict] = []

    for ev in feed_events:
        try:
            # Q-score
            q_result = compute_q_score(ev)
            q_score  = q_result["q_score"]
            q_tier   = q_result["q_tier"]

            # Detectors
            badges: list[str] = []
            direction_discounted = False
            for badge_name, detector_fn in _DETECTORS:
                try:
                    fires = detector_fn(ev, feed_events)
                except Exception:  # noqa: BLE001
                    fires = False
                if fires:
                    badges.append(badge_name)
                    if badge_name == "MULTI_LEG":
                        direction_discounted = True

            # Tier from thresholds
            def _tier_from_thresholds(score: int) -> str:
                if score >= thresholds.get("elite", 999):
                    return "elite"
                if score >= thresholds.get("strong", 999):
                    return "strong"
                if score >= thresholds.get("high", 999):
                    return "high"
                if score >= thresholds.get("medium", 999):
                    return "medium"
                return "below_medium"

            session_tier = _tier_from_thresholds(q_score)

            enriched.append({
                # pass-through identity fields
                "id":                ev.get("id"),
                "ts":                ev.get("ts"),
                "root":              ev.get("root"),
                "right":             ev.get("right"),
                "exp":               ev.get("exp"),
                "strike":            ev.get("strike"),
                "dte":               ev.get("dte"),
                "dte_bucket":        ev.get("dte_bucket"),
                "mny_bucket":        ev.get("mny_bucket"),
                "premium":           ev.get("premium"),
                "side":              ev.get("side"),
                "n_prints":          ev.get("n_prints"),
                "size":              ev.get("size"),
                "vol_gt_oi":         ev.get("vol_gt_oi"),
                "repeated":          ev.get("repeated"),
                "zerodte":           ev.get("zerodte"),
                "swept":             ev.get("swept"),
                "group":             ev.get("group"),
                "group_zh":          ev.get("group_zh"),
                # enrichment
                "q_score":            q_score,
                "q_tier":             q_tier,
                "session_tier":       session_tier,
                "badges":             badges,
                "direction_discounted": direction_discounted,
                "components":         q_result["components"],
            })
        except Exception as e:  # noqa: BLE001
            log.warning("flow_enrich: skipped event %s: %s", ev.get("id"), e)

    # OI join
    oi_confirm_note: str | None = None
    confirmed_yesterday: list[dict] = []
    if oi_confirmed is not None:
        confirmed_yesterday, oi_confirm_note = join_oi_confirmed(
            feed_events, oi_confirmed, session_date
        )

    return {
        "schema":              "flow.enrich/v1",
        "asof":                asof,
        "session_date":        session_date,
        "thresholds":          thresholds,
        "bootstrap":           bootstrap,
        "n_events":            len(enriched),
        "events":              enriched,
        "confirmed_yesterday": confirmed_yesterday,
        **({"oi_confirm_note": oi_confirm_note} if oi_confirm_note else {}),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Convenience: enrich a full feed payload in one call
# ═══════════════════════════════════════════════════════════════════════════════

def enrich_feed(
    feed_payload: dict,
    asof: str,
    pool_events: list[dict] | None = None,
    oi_confirmed: dict | None = None,
) -> dict:
    """Top-level convenience: enrich a live_flow.feed/v1 payload.

    Parameters
    ----------
    feed_payload  : the feed JSON dict (schema live_flow.feed/v1).
    asof          : ISO timestamp for this enrichment run.
    pool_events   : events from trailing sessions for threshold computation.
                    If None or empty, uses feed_payload events only (bootstrap=True).
    oi_confirmed  : options_hub/oi_confirmed.json dict; None = skip.

    Returns
    -------
    flow.enrich/v1 envelope dict.
    """
    events       = feed_payload.get("events", [])
    session_date = feed_payload.get("session_date", "")

    # Pool for thresholds: trailing sessions first, then current session
    pool = list(pool_events or [])
    if pool:
        # Annotate current events with session_date for bootstrap detection
        for ev in events:
            ev = dict(ev)  # copy to avoid mutation
            ev.setdefault("session_date", session_date)
        pool_for_thresh = pool
    else:
        # Bootstrap: use current session events only
        for ev in events:
            if isinstance(ev, dict):
                ev.setdefault("session_date", session_date)
        pool_for_thresh = events

    thresholds = compute_thresholds(pool_for_thresh)
    bootstrap  = thresholds.get("bootstrap", True) or not pool_events

    return build_enrich_envelope(
        feed_events=events,
        session_date=session_date,
        asof=asof,
        thresholds=thresholds,
        oi_confirmed=oi_confirmed,
        bootstrap=bootstrap,
    )
