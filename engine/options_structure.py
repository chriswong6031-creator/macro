"""engine/options_structure.py — Options Sensor Contract: dataclasses + validators + chain-heat aggregator.

Package A of the MomoEdge-parity Options Terminal + Prophet build.

Six schemas are defined here; each carries authority_tier and reliability metadata.
No schema in this module claims "validated" status (CI-enforced law); every artifact
ships at authority_tier='display' or 'shadow' until a forward ledger gate passes.

Schemas (all DISPLAY-ONLY until gauntleted):
  options_structure.gex_state/v1   — per-symbol dealer gamma structure state
  options_flow.chain_heat/v1       — contract-day accumulation campaigns
  options_structure.matrix/v1      — strike × expiration matrix (PRISM)
  options_structure.structural/v1  — structural detector state (shadow tier)
  prophet.trade_plan/v1             — prophet base trade plan envelope
  prophet.management_state/v1       — prophet live management confidence state

EPISTEMIC LAWS (binding on this module):
  • "validated" MUST NOT appear in any user-facing string.
  • Direction is always soft without NBBO.  ask_share-derived lean ≠ confirmed trade side.
  • LLMs may only narrate/de-escalate — never originate signals, scores, or escalations.
  • New artifacts ship display→shadow→confirmer→scored; each step requires a gated
    forward ledger.  Authority escalation must be explicit and pre-registered.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

log = logging.getLogger(__name__)

# ── authority tier constants ──────────────────────────────────────────────────
AUTHORITY_DISPLAY = "display"
AUTHORITY_SHADOW  = "shadow"
AUTHORITY_CONFIRMER = "confirmer"
AUTHORITY_SCORED  = "scored"

# ── chain-heat aggregation thresholds ────────────────────────────────────────
_CHAIN_HEAT_PREMIUM_MN_DEFAULT = 3.0    # minimum campaign premium in $M
_CHAIN_HEAT_MIN_ALERTS_DEFAULT = 2      # minimum alert count to form a campaign
_ASK_SHARE_ACCUMULATION = 0.65          # ask_share threshold → accumulation lean
_ASK_SHARE_DISTRIBUTION = 0.35          # ask_share threshold → distribution lean


# ===========================================================================
# 1. Schema: options_structure.gex_state/v1
# ===========================================================================

_GEX_REGIME_VALUES = frozenset({
    "PIN", "DRIFT", "RANGE", "TRANSITION", "TREND", "CASCADE",
})


@dataclass
class GexState:
    """Per-symbol dealer gamma structure state.

    schema: options_structure.gex_state/v1
    authority_tier: display
    freshness_sla_hours: 30

    All gamma-regime and level fields are DISPLAY-ONLY until the GEX→forward-vol
    validation gate passes (~Sept 2026).  Single-name regime is a near-constant
    product attribute, NOT a time-varying signal.  Preserve regime_passport.
    """
    schema: str = "options_structure.gex_state/v1"
    asof: str = ""                        # ISO-8601 with timezone offset
    root: str = ""
    spot: float | None = None
    net_gex_bn: float | None = None       # net GEX in $B (assumption-signed)
    gamma_regime: str = "RANGE"           # PIN|DRIFT|RANGE|TRANSITION|TREND|CASCADE
    stability_pct: float | None = None    # posGex/(posGex+|negGex|) × 100, ±20% window
    gamma_flip: float | None = None
    dist_to_flip_pct: float | None = None
    call_wall: float | None = None
    put_wall: float | None = None
    magnet: float | None = None
    max_pain: float | None = None
    pin_probability: float | None = None  # None when insufficient data
    gravity_direction: str | None = None  # "up" | "down" | None
    gravity_up_pct: float | None = None
    cascade_trigger: float | None = None
    upside_trigger: float | None = None
    oi_delta_clusters: dict[str, list[dict]] = field(default_factory=lambda: {
        "new_oi": [], "exit_oi": []
    })
    regime_passport: dict = field(default_factory=lambda: {
        "basis": "dealer-short-assumption",
        "structurally_constant": False,
        "is_index_product": False,
        "verdict": "display-only",
        "note": "GEX regime display-only until GEX→forward-vol gate (~Sept 2026).",
    })
    authority_tier: str = AUTHORITY_DISPLAY
    reliability: dict = field(default_factory=lambda: {
        "levels": "display-only-until-gate",
        "regime": "assumption-signed",
        "note": "Direction soft — sign not NBBO-confirmed.",
    })


def validate_gex_state(d: dict) -> list[str]:
    """Return a list of error strings; empty list = clean."""
    errors: list[str] = []
    if d.get("schema") != "options_structure.gex_state/v1":
        errors.append(f"schema mismatch: {d.get('schema')!r}")
    if not d.get("asof"):
        errors.append("asof is required")
    if not d.get("root"):
        errors.append("root is required")
    regime = d.get("gamma_regime", "")
    if regime and regime not in _GEX_REGIME_VALUES:
        errors.append(f"gamma_regime {regime!r} not in {sorted(_GEX_REGIME_VALUES)}")
    if d.get("authority_tier") not in (AUTHORITY_DISPLAY, AUTHORITY_SHADOW,
                                       AUTHORITY_CONFIRMER, AUTHORITY_SCORED):
        errors.append(f"invalid authority_tier: {d.get('authority_tier')!r}")
    return errors


# ===========================================================================
# 2. Schema: options_flow.chain_heat/v1
# ===========================================================================

_LEAN_VALUES = frozenset({"accumulation", "distribution", "contested"})


@dataclass
class ChainHeatCampaign:
    """One contract-day accumulation campaign.

    lean is derived from ask_share:
        ask_share >= 0.65 → "accumulation"
        ask_share <= 0.35 → "distribution"
        else              → "contested"

    This is NOT an asserted BOUGHT/SOLD direction.  ask_share is a heuristic
    (tick-rule signed prints) — direction_reliability='soft' always.
    """
    option_symbol: str = ""      # OCC-style symbol, e.g. "SMH   260618P00530000"
    ticker: str = ""
    right: str = ""              # "CALL" | "PUT"
    strike: float = 0.0
    expiry: str = ""             # YYYY-MM-DD
    dte: int | None = None
    total_premium_mn: float = 0.0
    alert_count: int = 0
    span_minutes: float = 0.0
    first_seen: str = ""         # ISO-8601 UTC
    last_seen: str = ""          # ISO-8601 UTC
    ask_share: float | None = None   # fraction at ask (0–1); None if unavailable
    lean: str = "contested"      # accumulation | distribution | contested
    direction_reliability: str = "soft"    # always soft (no NBBO)
    authority_tier: str = AUTHORITY_DISPLAY


@dataclass
class ChainHeatFeed:
    """Feed envelope for chain-heat campaigns.

    schema: options_flow.chain_heat/v1
    authority_tier: display
    """
    schema: str = "options_flow.chain_heat/v1"
    asof: str = ""
    session_date: str = ""
    campaigns: list[dict] = field(default_factory=list)
    authority_tier: str = AUTHORITY_DISPLAY
    reliability: dict = field(default_factory=lambda: {
        "lean": "soft — ask_share heuristic, not NBBO-confirmed",
        "premium_magnitude": "reliable",
        "direction": "soft",
    })


def _campaign_lean(ask_share: float | None) -> str:
    """Map ask_share fraction to a lean label."""
    if ask_share is None:
        return "contested"
    if ask_share >= _ASK_SHARE_ACCUMULATION:
        return "accumulation"
    if ask_share <= _ASK_SHARE_DISTRIBUTION:
        return "distribution"
    return "contested"


def aggregate_chain_heat(
    events: list[dict],
    min_premium_mn: float = _CHAIN_HEAT_PREMIUM_MN_DEFAULT,
    min_alerts: int = _CHAIN_HEAT_MIN_ALERTS_DEFAULT,
    session_date: str | None = None,
) -> list[dict]:
    """Aggregate live_flow.feed/v1 event dicts into chain-heat campaigns.

    Groups events by (root + strike + expiry + right); emits one campaign per
    group that meets both threshold gates.  This is a PURE function — no I/O,
    no clock reads.

    Parameters
    ----------
    events:
        List of event dicts in live_flow.feed/v1 format (output of
        engine/live_flow.py:process_batch).  Required keys per event:
            root, strike, exp (YYYY-MM-DD), right ("C"|"P" or "CALL"/"PUT"),
            premium (float, in dollars), ts (ISO-8601 str).
        Optional keys: ask_share (float 0-1).
    min_premium_mn:
        Minimum total_premium_mn ($ millions) for a campaign to be emitted.
        Default 3.0 (matches MomoEdge $3M gate; operator-adjustable).
    min_alerts:
        Minimum number of component events.  Campaigns formed from fewer events
        are suppressed.
    session_date:
        Trading session date as "YYYY-MM-DD" string.  Used to compute ``dte``
        (days to expiry) deterministically.  When None, ``dte`` is set to None
        for all campaigns.  The caller (poller writer) is responsible for
        stamping the correct session date — this keeps the function PIT-safe
        and fully deterministic (same inputs → same outputs regardless of wall
        clock).

    Returns
    -------
    List of campaign dicts sorted by total_premium_mn descending.  Each dict
    matches the ChainHeatCampaign field layout (serialisable as-is).

    Reliability contract
    --------------------
    • lean derives from ask_share, which is tick-rule signed (net recovery ~0.41).
      direction_reliability='soft' is hardcoded and may not be elevated without an
      NBBO-signed data source and a forward-ledger gate.
    • total_premium_mn and alert_count are signing-free RELIABLE fields.
    • authority_tier='display' always (Package A contract doc §2).
    """
    # Group by (root, strike, expiry, right).
    groups: dict[tuple, dict] = {}

    for ev in events:
        root   = str(ev.get("root", "")).upper()
        strike = float(ev.get("strike", 0))
        exp    = str(ev.get("exp", ""))
        right  = str(ev.get("right", "")).upper()[:1]   # "C" or "P"

        if not (root and exp and right in ("C", "P")):
            continue

        key = (root, strike, exp, right)
        prem = float(ev.get("premium", 0))

        if key not in groups:
            groups[key] = {
                "root": root,
                "strike": strike,
                "expiry": exp,
                "right": "CALL" if right == "C" else "PUT",
                "total_premium": 0.0,
                "alert_count": 0,
                "ask_prem_sum": 0.0,
                "total_prem_for_ask": 0.0,
                "ts_list": [],
            }

        g = groups[key]
        g["total_premium"] += prem
        g["alert_count"]   += 1

        ts = str(ev.get("ts", ""))
        if ts:
            g["ts_list"].append(ts)

        # ask_share contribution
        ask_share_ev = ev.get("ask_share")
        if ask_share_ev is not None and prem > 0:
            try:
                g["ask_prem_sum"]        += float(ask_share_ev) * prem
                g["total_prem_for_ask"]  += prem
            except (TypeError, ValueError):
                pass

    campaigns: list[dict] = []
    for key, g in groups.items():
        total_prem_mn = g["total_premium"] / 1_000_000.0
        if total_prem_mn < min_premium_mn:
            continue
        if g["alert_count"] < min_alerts:
            continue

        # Parse timestamps to aware datetimes before sorting so that mixed
        # UTC offsets (e.g. 'Z' vs '-04:00') are ordered correctly.
        raw_ts = [t for t in g["ts_list"] if t]
        parsed_ts: list[tuple[datetime, str]] = []
        for raw in raw_ts:
            try:
                dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                parsed_ts.append((dt, raw))
            except Exception:  # noqa: BLE001
                pass
        parsed_ts.sort(key=lambda x: x[0])

        first_seen = parsed_ts[0][1]  if parsed_ts else ""
        last_seen  = parsed_ts[-1][1] if parsed_ts else ""

        # span in minutes
        span_minutes: float = 0.0
        if len(parsed_ts) >= 2:
            try:
                t0 = parsed_ts[0][0]
                t1 = parsed_ts[-1][0]
                span_minutes = max(0.0, (t1 - t0).total_seconds() / 60.0)
            except Exception:  # noqa: BLE001
                span_minutes = 0.0

        # ask_share aggregate
        ask_share: float | None = None
        if g["total_prem_for_ask"] > 0:
            ask_share = g["ask_prem_sum"] / g["total_prem_for_ask"]

        lean = _campaign_lean(ask_share)

        # DTE from expiry string relative to session_date (PIT-safe; pure).
        # When session_date is None, dte is left as None — the writer stamps
        # it using the correct session date before persisting.
        dte: int | None = None
        if session_date:
            try:
                exp_date     = datetime.strptime(g["expiry"], "%Y-%m-%d").date()
                session_dt   = datetime.strptime(session_date, "%Y-%m-%d").date()
                dte = (exp_date - session_dt).days
            except Exception:  # noqa: BLE001
                pass

        # Build option_symbol (simplified OCC format for display)
        root_padded = g["root"].ljust(6)
        exp_yymmdd  = g["expiry"].replace("-", "")[2:] if len(g["expiry"]) == 10 else ""
        right_char  = "C" if g["right"] == "CALL" else "P"
        strike_int  = int(round(g["strike"] * 1000))
        option_symbol = f"{root_padded}{exp_yymmdd}{right_char}{strike_int:08d}"

        campaigns.append({
            "option_symbol":       option_symbol,
            "ticker":              g["root"],
            "right":               g["right"],
            "strike":              g["strike"],
            "expiry":              g["expiry"],
            "dte":                 dte,
            "total_premium_mn":    round(total_prem_mn, 3),
            "alert_count":         g["alert_count"],
            "span_minutes":        round(span_minutes, 1),
            "first_seen":          first_seen,
            "last_seen":           last_seen,
            "ask_share":           round(ask_share, 4) if ask_share is not None else None,
            "lean":                lean,
            "direction_reliability": "soft",
            "authority_tier":      AUTHORITY_DISPLAY,
        })

    campaigns.sort(key=lambda c: c["total_premium_mn"], reverse=True)
    return campaigns


def validate_chain_heat_feed(d: dict) -> list[str]:
    """Return error strings; empty = clean."""
    errors: list[str] = []
    if d.get("schema") != "options_flow.chain_heat/v1":
        errors.append(f"schema mismatch: {d.get('schema')!r}")
    if not d.get("asof"):
        errors.append("asof is required")
    if not isinstance(d.get("campaigns"), list):
        errors.append("campaigns must be a list")
        return errors
    for i, c in enumerate(d["campaigns"]):
        if not c.get("option_symbol"):
            errors.append(f"campaign[{i}] missing option_symbol")
        lean = c.get("lean", "")
        if lean and lean not in _LEAN_VALUES:
            errors.append(f"campaign[{i}] lean {lean!r} not in {sorted(_LEAN_VALUES)}")
        dr = c.get("direction_reliability", "")
        if dr and dr != "soft":
            errors.append(
                f"campaign[{i}] direction_reliability={dr!r}: only 'soft' is permitted "
                "in Package A (NBBO-signing gate not yet passed)"
            )
    return errors


# ===========================================================================
# 3. Schema: options_structure.matrix/v1
# ===========================================================================

@dataclass
class MatrixCell:
    """One cell in the strike × expiration matrix."""
    strike: float = 0.0
    expiry: str = ""
    gex: float | None = None           # net $γ/1% in this cell (assumption-signed)
    call_oi: int | None = None
    put_oi: int | None = None
    call_vol: int | None = None
    put_vol: int | None = None
    delta_oi: dict = field(default_factory=lambda: {"call": None, "put": None})
    unusual: dict | None = None         # ratio, samples, side — or None if no history


@dataclass
class MatrixLevels:
    """Key levels derived from the full matrix."""
    call_wall: float | None = None
    put_support: float | None = None
    hvl: float | None = None           # high-volume level
    gamma_flip: float | None = None
    max_pain: float | None = None


@dataclass
class MatrixHeatSeeker:
    """Descriptive standout cell — NOT a recommendation."""
    strike: float | None = None
    expiry: str | None = None
    lens: str = "GEX"
    standout_ratio: float | None = None
    confidence: float | None = None    # (ratio-1)/3; uncalibrated
    note: str = "descriptive — not a recommendation"


@dataclass
class OptionsMatrix:
    """Strike × expiration matrix for one underlying.

    schema: options_structure.matrix/v1
    authority_tier: display
    """
    schema: str = "options_structure.matrix/v1"
    asof: str = ""
    root: str = ""
    spot: float | None = None
    expiries: list[str] = field(default_factory=list)
    strikes: list[float] = field(default_factory=list)
    cells: list[dict] = field(default_factory=list)
    levels: dict = field(default_factory=dict)
    heat_seeker: dict | None = None
    authority_tier: str = AUTHORITY_DISPLAY
    reliability: dict = field(default_factory=lambda: {
        "gex": "assumption-signed — display-only until GEX→vol gate",
        "delta_oi": "reliable — signing-free OI change",
        "vol": "reliable magnitude",
        "note": "Sign is an assumption, not a fact. Magnitude is the reliable read.",
    })


def validate_matrix(d: dict) -> list[str]:
    """Return error strings; empty = clean."""
    errors: list[str] = []
    if d.get("schema") != "options_structure.matrix/v1":
        errors.append(f"schema mismatch: {d.get('schema')!r}")
    if not d.get("asof"):
        errors.append("asof is required")
    if not d.get("root"):
        errors.append("root is required")
    if not isinstance(d.get("cells"), list):
        errors.append("cells must be a list")
    for i, c in enumerate(d.get("cells", [])):
        if "strike" not in c:
            errors.append(f"cell[{i}] missing strike")
        if "expiry" not in c:
            errors.append(f"cell[{i}] missing expiry")
    hs = d.get("heat_seeker")
    if hs and hs.get("note") != "descriptive — not a recommendation":
        errors.append("heat_seeker.note must be 'descriptive — not a recommendation'")
    return errors


# ===========================================================================
# 4. Schema: options_structure.structural/v1
# ===========================================================================

_SQUEEZE_STATE_VALUES = frozenset({"NONE", "BUILDING", "ACTIVE"})
_CASCADE_STATE_VALUES = frozenset({"NONE", "BUILDING", "ACTIVE"})


@dataclass
class StructuralState:
    """Structural detector state (squeeze, cascade, regime context).

    schema: options_structure.structural/v1
    authority_tier: shadow  (context-only until gauntlet)

    This artifact feeds the Neural Web as a GATED CONTEXT SENSOR only.
    It may not originate signals or escalations.
    """
    schema: str = "options_structure.structural/v1"
    asof: str = ""
    root: str = ""
    squeeze_state: str = "NONE"        # NONE|BUILDING|ACTIVE
    cascade_state: str = "NONE"        # NONE|BUILDING|ACTIVE
    top_relevance_score: float | None = None    # 0-100 descriptive index
    contributing_flows: int = 0
    flow_near_flip: bool = False
    flow_near_wall: bool = False
    dealer_regime: str = ""            # from gex_state.gamma_regime
    explanation: str = ""              # plain-language description (no "validated")
    vol_ladder_suppressed: bool = False
    authority_tier: str = AUTHORITY_SHADOW
    allowed_authority: str = "context-only-until-gauntlet"
    reliability: dict = field(default_factory=lambda: {
        "structural_state": "shadow — context sensor only, not a signal",
        "note": "LLMs may only narrate. Escalation requires pre-registered forward ledger gate.",
    })


def validate_structural(d: dict) -> list[str]:
    """Return error strings; empty = clean."""
    errors: list[str] = []
    if d.get("schema") != "options_structure.structural/v1":
        errors.append(f"schema mismatch: {d.get('schema')!r}")
    if not d.get("asof"):
        errors.append("asof is required")
    if not d.get("root"):
        errors.append("root is required")
    sq = d.get("squeeze_state", "")
    if sq and sq not in _SQUEEZE_STATE_VALUES:
        errors.append(f"squeeze_state {sq!r} not in {sorted(_SQUEEZE_STATE_VALUES)}")
    ca = d.get("cascade_state", "")
    if ca and ca not in _CASCADE_STATE_VALUES:
        errors.append(f"cascade_state {ca!r} not in {sorted(_CASCADE_STATE_VALUES)}")
    if d.get("authority_tier") != AUTHORITY_SHADOW:
        errors.append("structural/v1 must carry authority_tier='shadow'")
    return errors


# ===========================================================================
# 5. Schema: prophet.trade_plan/v1
# ===========================================================================

_DIRECTION_VALUES = frozenset({"BULL", "BEAR"})
_TRANCHE_VALUES   = frozenset({1, 2})


@dataclass
class ProphetTradePlan:
    """Prophet base trade plan envelope.

    schema: prophet.trade_plan/v1
    authority_tier: display

    The Neural Web ORIGINATES candidates; the Prophet MANAGES them.
    LLMs may narrate but MUST NOT originate signals, scores, or escalations.
    This schema carries the static plan; live management state lives in
    prophet.management_state/v1 at prophet/state/<id>.json.
    """
    schema: str = "prophet.trade_plan/v1"
    id: str = ""                        # stable UUID or composite key
    asof: str = ""                      # plan creation timestamp
    asset: str = ""
    direction: str = "BULL"             # BULL | BEAR
    thesis: str = ""                    # plain-language thesis summary
    source_engines: list[str] = field(default_factory=lambda: ["neural_web"])
    trigger: float | None = None        # price level that activates the trade
    entry: float | None = None
    invalidation: float | None = None
    targets: list[float] = field(default_factory=list)
    horizon_days: int | None = None
    min_hold_days: int | None = None
    tranche: int = 1                    # 1 or 2
    option_contract: dict | None = None  # type, strike, expiry, entry_premium
    management_ref: str = ""            # "prophet/state/<id>.json"
    authority_tier: str = AUTHORITY_DISPLAY
    reliability: dict = field(default_factory=lambda: {
        "plan": "display — NW-originated; Prophet manages; LLM narrates only",
        "option_premium": "display — EOD/delayed, not NBBO-live",
    })


def validate_trade_plan(d: dict) -> list[str]:
    """Return error strings; empty = clean."""
    errors: list[str] = []
    if d.get("schema") != "prophet.trade_plan/v1":
        errors.append(f"schema mismatch: {d.get('schema')!r}")
    if not d.get("id"):
        errors.append("id is required")
    if not d.get("asof"):
        errors.append("asof is required")
    if not d.get("asset"):
        errors.append("asset is required")
    direction = d.get("direction", "")
    if direction and direction not in _DIRECTION_VALUES:
        errors.append(f"direction {direction!r} not in {sorted(_DIRECTION_VALUES)}")
    tranche = d.get("tranche")
    if tranche is not None and tranche not in _TRANCHE_VALUES:
        errors.append(f"tranche {tranche!r} must be 1 or 2")
    if "targets" in d and not isinstance(d["targets"], list):
        errors.append("targets must be a list")
    # Verify LLM-origination guard: source_engines must contain at least one entry
    sources = d.get("source_engines", [])
    if not sources:
        errors.append("source_engines must list at least one originating engine")
    return errors


# ===========================================================================
# 6. Schema: prophet.management_state/v1
# ===========================================================================

_PHASE_VALUES = frozenset({
    "pre_trigger", "triggered_pre_t1", "at_t1", "between_t1_t2",
    "at_t2", "overtime", "invalidated",
})
_ACTION_VALUES = frozenset({
    "wait", "enter", "hold", "trim", "trail", "exit", "invalidated",
})

MANAGEMENT_CONFIDENCE_CEILING = 92   # honest uncertainty cap (mirrors MomoEdge)


@dataclass
class ProphetManagementState:
    """Prophet live management confidence state.

    schema: prophet.management_state/v1
    authority_tier: display

    This is a TRADE-MANAGEMENT score, NOT a pick-rank score.  The Neural Web
    produces pick candidates; the Prophet manages active trades.  These two
    surfaces must stay separated.

    Confidence ceiling: 92 (uncertainty is honest; certainty is forbidden).
    """
    schema: str = "prophet.management_state/v1"
    id: str = ""                        # matches prophet.trade_plan/v1 id
    asof: str = ""
    phase: str = "pre_trigger"          # 7-phase lifecycle
    management_confidence: float | None = None   # EMA-smoothed, ≤92
    raw_confidence: float | None = None          # pre-EMA
    delta_vs_base: float | None = None           # change vs plan baseline
    recommended_action: str = "wait"
    components: dict = field(default_factory=lambda: {
        "validity": None,   # plan still structurally intact?
        "progress": None,   # distance traveled toward targets
        "pace": None,       # pace vs horizon
        "retention": None,  # how much of early move was retained
        "overlay": None,    # macro/regime overlay
    })
    geometry: dict = field(default_factory=lambda: {
        "dist_to_stop_r": None,   # distance to stop in R-units
        "dist_to_t1_r": None,
        "horizon_pct_used": None,
    })
    change_reason: str = ""
    confidence_ceiling: int = MANAGEMENT_CONFIDENCE_CEILING
    authority: str = "trade-management-only-NOT-pick-rank"
    authority_tier: str = AUTHORITY_DISPLAY
    reliability: dict = field(default_factory=lambda: {
        "management_confidence": "display — no forward ledger has passed yet",
        "recommended_action": "display — narrate, not authoritative order",
        "ceiling": f"hard cap at {MANAGEMENT_CONFIDENCE_CEILING} — uncertainty is honest",
    })


def validate_management_state(d: dict) -> list[str]:
    """Return error strings; empty = clean."""
    errors: list[str] = []
    if d.get("schema") != "prophet.management_state/v1":
        errors.append(f"schema mismatch: {d.get('schema')!r}")
    if not d.get("id"):
        errors.append("id is required")
    if not d.get("asof"):
        errors.append("asof is required")
    phase = d.get("phase", "")
    if phase and phase not in _PHASE_VALUES:
        errors.append(f"phase {phase!r} not in {sorted(_PHASE_VALUES)}")
    action = d.get("recommended_action", "")
    if action and action not in _ACTION_VALUES:
        errors.append(f"recommended_action {action!r} not in {sorted(_ACTION_VALUES)}")
    mc = d.get("management_confidence")
    if mc is not None:
        try:
            if float(mc) > MANAGEMENT_CONFIDENCE_CEILING:
                errors.append(
                    f"management_confidence {mc} exceeds ceiling {MANAGEMENT_CONFIDENCE_CEILING}"
                )
        except (TypeError, ValueError):
            errors.append(f"management_confidence {mc!r} is not numeric")
    return errors


# ===========================================================================
# Convenience dispatcher
# ===========================================================================

_VALIDATORS = {
    "options_structure.gex_state/v1":  validate_gex_state,
    "options_flow.chain_heat/v1":      validate_chain_heat_feed,
    "options_structure.matrix/v1":     validate_matrix,
    "options_structure.structural/v1": validate_structural,
    "prophet.trade_plan/v1":            validate_trade_plan,
    "prophet.management_state/v1":      validate_management_state,
}


def validate(d: dict) -> list[str]:
    """Dispatch to the correct validator by schema key.

    Returns a list of error strings (empty = clean).
    """
    schema = d.get("schema", "")
    validator = _VALIDATORS.get(schema)
    if validator is None:
        return [f"Unknown schema: {schema!r}. Known: {sorted(_VALIDATORS)}"]
    return validator(d)
