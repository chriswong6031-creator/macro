"""Pure composer for the US ``monetary_policy`` workspace snapshot (F01 / R2).

Reads THREE owner-native artifacts and projects them into a
``mastermind.macro_workspace_snapshot.v1`` body:

* ``data/rates_command/latest.json`` (schema ``rates_command.v1``) - policy rate,
  futures-implied path, FOMC SEP dots, the dots-vs-market gap, hawk/ease
  pressure legs, and the owner's own divergence flags;
* the ``cb_desk`` block of ``data/intl_risk/latest.json`` (``engine.cb_desk``) -
  realized Fed/ECB/BoJ/BoE/SNB/BoC/RBA policy rates with per-CB ``stale``
  flags, balance-sheet impulse (WALCL/ECBASSETSW/JPNASSETS), and the next
  scheduled meeting date+day-count as computed AT THE CB-DESK BUILD TIME
  (``data/intl_risk/cb_calendar.yml``, official CB calendar pages);
* the ``rate_inflation_transmission`` block of ``data/regime/latest.json`` -
  nominal/real 10y, the 2s10s curve, and 10y breakeven.

DEVIATION FROM THE R1A HEADLINE SHAPE (see module-level note in ``_headline``):
architecture section 10.7 gives Monetary Policy a headline COMPOSITION LIST
(policy rates, futures path, curve, balance sheet, divergence, calendar), not
an x/y quadrant like ``liquidity_regime``. The committed
``macro_workspace_snapshot.v1`` schema's ``headline.state_id`` is closed to
``["A","B","C","D",null]`` and ``axes.items[].axis_id`` is closed to
``["funding_pressure","balance_sheet_support"]`` - both liquidity-regime-
specific enums this composer must not (and per the no-shared-file-edits
constraint, cannot) repurpose. This composer resolves that honestly: it never
invents a quadrant. ``headline.state_id`` is always ``null`` /
``NOT_APPLICABLE`` and ``axes.items`` is always ``[]`` (schema-legal - no
``minItems``), and the REAL headline content (policy rates, market-implied
path, curve, balance sheet, meeting calendar, divergence) is carried entirely
in ``metrics`` / ``drivers`` / ``implications``, each fully typed under the
metric law (section 7.4).

It:
* carries every KPI under the full metric law (section 7.4) with distinct
  clocks - the pre-computed "days to next meeting" in the owner cb_desk
  artifact is propagated AS-IS with its OWN ``calculation_as_of`` (the cb_desk
  build timestamp), never recomputed against this composer's ``built_at``
  (section 7.5's clock law; this composer never reads a wall clock itself);
* labels every futures/market-implied field's ``basis`` honestly as
  ``market_implied_futures_price_not_forecast`` - a market PRICE, never a
  Fed forecast or stated intent (architecture 10.7 authority law);
* propagates the FOMC SEP dot-plot median AS PUBLISHED BY THE OWNER
  (``rates_command``/``regime.fed_path``, itself sourced from FRED FEDTARMD);
  this composer never fabricates or estimates a dot;
* emits TYPED degraded states, never zero/neutral/calm:
    - a required source missing              -> SOURCE_FAILED
    - a required source flagged stale         -> STALE_SOURCE (owner "stale"
      flag or this composer's disclosed age tolerance vs the given built_at)
    - a required source not yet released      -> NOT_YET_RELEASED
    - fewer than 2 central banks report a
      policy rate (global divergence refused) -> value null + COMPUTATION_REFUSED
    - the market-implied path diverges from
      the FOMC SEP median beyond the owner's
      own disclosed tolerance                 -> a typed contradiction (DISAGREEMENT)
    - hawkish and easing pressure legs both
      active and roughly balanced             -> a second, independent typed
      contradiction (DISAGREEMENT)
    - no comparable prior print               -> changes/corrections WARMUP
    - prior print on a different method       -> changes METHOD_CHANGED (refuses deltas)

NO rank/gate/size/trade authority. NO LLM-originated facts, no policy-intent
prediction (architecture 10.7 authority law: "the page cannot call a market
path a forecast by the central bank"). Descriptive ceiling only. Depends only
on the standard library. The composer NEVER reads a wall clock: ``built_at``
is passed in by the builder, and every staleness/age check is a pure function
of ``built_at`` and the owner artifacts' own clocks, so an identical set of
owner inputs always yields an identical snapshot body.
"""
from __future__ import annotations

import datetime as _dt
from hashlib import sha256
from typing import Any, Mapping

METHOD_VERSION = "monetary_policy.compose.v1"
DEFINITION_VERSION = "1.0.0"
PRODUCER = "engine.market_os.macro_workspaces.monetary_policy"

# Staleness tolerances (disclosed, not silently invented): each mirrors an
# existing owner-declared cadence rather than a new guess. Per-CB policy-rate
# freshness does NOT use a tolerance constant here -- it reuses the owner's
# OWN pre-computed "stale" boolean (cb_desk's own cadence-aware tolerance:
# daily=12d / monthly=75d, engine/cb_desk.py _STALE_DAYS) rather than a second,
# possibly-inconsistent copy of that threshold.
#   market-implied futures board      : rates_command board publishes daily
#   Treasury curve / real-yield desk  : rate_inflation_transmission publishes
#                                        daily; a 10-day tolerance mirrors the
#                                        liquidity_regime OFR ~2-business-day
#                                        lag pattern scaled to a slower-refresh desk
#   weekly Fed H.4.1 balance sheet    : data/macro/fed_net_liquidity_meta.json's
#                                        own stale_guard_bdays=10 (~14 calendar days)
_MARKET_STALE_DAYS = 12
_CURVE_STALE_DAYS = 10
_WEEKLY_BS_STALE_DAYS = 14

_FRESH_SEVERITY = {
    "CURRENT": 0,
    "HISTORICAL_AS_KNOWN": 1,
    "LATE_WITHIN_TOLERANCE": 2,
    "SIMULATED": 3,
    "STALE_SOURCE": 4,
    "NOT_YET_RELEASED": 5,
    "RIGHTS_BLOCKED": 6,
    "NOT_COVERED": 7,
    "SOURCE_FAILED": 8,
}

# Central banks this composer projects (architecture 10.7: "Fed, ECB and BoJ
# current policy rates" are the named required trio; the remaining cb_desk
# banks feed only the global-divergence spread, never their own rate metric,
# to keep the required composition bounded to what the blueprint names).
_CB_RATE_SPECS = (
    ("FED", "fed_funds_rate", "Fed funds effective rate", "联邦基金有效利率"),
    ("ECB", "ecb_deposit_rate", "ECB deposit facility rate", "欧洲央行存款便利利率"),
    ("BOJ", "boj_policy_rate", "BoJ policy rate", "日本银行政策利率"),
)
_CB_BS_SPECS = (
    ("FED", "fed_balance_sheet_impulse_13w", "Fed balance-sheet impulse (13w)", "美联储资产负债表脉冲（13周）"),
    ("ECB", "ecb_balance_sheet_impulse_13w", "ECB balance-sheet impulse (13w)", "欧洲央行资产负债表脉冲（13周）"),
    ("BOJ", "boj_balance_sheet_impulse_13w", "BoJ balance-sheet impulse (13w)", "日本银行资产负债表脉冲（13周）"),
)
_CB_MEETING_SPECS = (
    ("FED", "next_fomc_meeting_days", "Next FOMC meeting", "下次FOMC会议"),
    ("ECB", "next_ecb_meeting_days", "Next ECB meeting", "下次欧洲央行会议"),
    ("BOJ", "next_boj_meeting_days", "Next BoJ meeting", "下次日本银行会议"),
)

# Metric ids tracked for "what changed" / corrections (architecture 7.8/6.3.7)
# in place of an axis x/y pair -- this workspace has no quadrant to diff.
_TRACKED_CHANGE_METRICS = (
    "fed_funds_rate", "market_implied_path_12m_bp", "curve_2s10s", "dots_vs_market_gap_bp",
)


# --------------------------------------------------------------------------- #
# small pure helpers
# --------------------------------------------------------------------------- #
def _get(d: Any, *path: str) -> Any:
    cur = d
    for key in path:
        if isinstance(cur, Mapping) and key in cur:
            cur = cur[key]
        else:
            return None
    return cur


def _num(v: Any) -> float | None:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return float(v)


def _round(v: float | None, n: int = 4) -> float | None:
    return None if v is None else round(float(v), n)


def _bil(en: str | None, zh: str | None) -> dict:
    return {"en": en, "zh": zh}


def _band(v, lo, hi):
    if v is None:
        return None
    return "LOW" if v < lo else ("HIGH" if v > hi else "MEDIUM")


def _worst_freshness(states: list[str]) -> str:
    if not states:
        return "SOURCE_FAILED"
    return max(states, key=lambda s: _FRESH_SEVERITY.get(s, 0))


def _parse_date(s: Any) -> _dt.date | None:
    if not isinstance(s, str) or len(s) < 10:
        return None
    try:
        return _dt.date.fromisoformat(s[:10])
    except ValueError:
        return None


def _age_days(built_at: Any, asof: Any) -> int | None:
    """Pure function of two GIVEN date/datetime strings -- never a wall-clock
    read. ``built_at`` is always supplied by the caller (the builder), never
    sourced from ``datetime.now()`` inside this module."""
    b, a = _parse_date(built_at), _parse_date(asof)
    if b is None or a is None:
        return None
    return (b - a).days


def _cb_freshness(row: Mapping | None, *, not_yet_released: bool = False) -> str:
    if row is None or _num((row or {}).get("policy_rate")) is None:
        return "NOT_YET_RELEASED" if not_yet_released else "SOURCE_FAILED"
    return "STALE_SOURCE" if row.get("stale") is True else "CURRENT"


def _aged_freshness(built_at, asof, tolerance_days: int, value_present: bool,
                     *, not_yet_released: bool = False) -> str:
    if not value_present:
        return "NOT_YET_RELEASED" if not_yet_released else "SOURCE_FAILED"
    age = _age_days(built_at, asof)
    if age is None:
        return "SOURCE_FAILED"
    return "STALE_SOURCE" if age > tolerance_days else "CURRENT"


def _metric(metric_id, value, value_type, unit, basis, direction, owner_ref,
            owner_field, reference_period, freshness, *, source_refs=None,
            transformation=None, status="PRESENT", null_reason=None,
            calculation_as_of=None) -> dict:
    return {
        "metric_id": metric_id,
        "reference_id": f"mastermind.market_reference/v1#{metric_id}",
        "definition_id": owner_field,
        "definition_version": DEFINITION_VERSION,
        "owner_ref": owner_ref,
        "value": value,
        "value_type": value_type,
        "unit": unit,
        "basis": basis,
        "direction_semantics": direction,
        "reference_period": reference_period,
        "observed_at": reference_period,
        "released_at": None,
        "available_at": None,
        "collected_at": None,
        "revised_at": None,
        "calculation_as_of": calculation_as_of if calculation_as_of is not None else reference_period,
        "market_session": None,
        "source_refs": source_refs or [owner_ref],
        "source_digest": None,
        "transformation": transformation,
        "model_version": METHOD_VERSION,
        "uncertainty": {"kind": None, "value": None},
        "coverage": None,
        "freshness": freshness,
        "rights_state": "OPEN",
        "status": status if value is not None else "ABSENT",
        "null_reason": null_reason if value is not None else (null_reason or "SOURCE_FAILED"),
        "authority_ceiling": "DESCRIPTIVE",
    }


def _metric_value(snapshot: Mapping | None, metric_id: str) -> Any:
    for m in (_get(snapshot, "metrics", "items") or []):
        if m.get("metric_id") == metric_id:
            return m.get("value")
    return None


# --------------------------------------------------------------------------- #
# the composer
# --------------------------------------------------------------------------- #
def compose(rates_command: Mapping[str, Any], cb_desk: Mapping[str, Any],
            rate_transmission: Mapping[str, Any], *, built_at: str,
            prior_snapshot: Mapping[str, Any] | None = None,
            code_version: str | None = None) -> dict:
    """Project ``rates_command`` + ``cb_desk`` + ``rate_transmission`` into an
    UNSEALED snapshot body. The builder seals it via ``contract.finalize``."""
    rc = rates_command or {}
    cbd = cb_desk or {}
    rt = rate_transmission or {}

    rc_asof = _get(rc, "asof")
    board = _get(rc, "board") or {}
    rate_path_row = _get(board, "rate_path_row") or {}
    inflation_row = _get(board, "inflation_row") or {}
    risk_row = _get(board, "risk_row") or {}
    policy_row = _get(board, "policy_row") or {}
    expectations_pressure = _get(rc, "expectations_pressure") or {}
    divergence = _get(rc, "divergence") or []
    stance = _get(rc, "stance") or {}
    gap = _get(rate_path_row, "gap") or {}

    cbs_list = _get(cbd, "cbs") or []
    cbs_by_id = {c.get("id"): c for c in cbs_list if isinstance(c, Mapping)}
    cbd_asof = _get(cbd, "as_of")

    rt_asof = _get(rt, "asof")
    rt_rates = _get(rt, "state", "rates") or {}
    rt_expect = _get(rt, "state", "expectations") or {}

    contradictions = _detect_contradictions(divergence, expectations_pressure)

    metrics = _metrics(rc_asof, rate_path_row, inflation_row, risk_row, policy_row,
                        cbs_by_id, cbd_asof, rt_asof, rt_rates, rt_expect,
                        gap, built_at, contradictions)
    metrics_by_id = {m["metric_id"]: m["value"] for m in metrics}

    required_avail = _required_availability(built_at, rc, cbs_by_id.get("FED"),
                                             rt, rc_asof, rt_asof)
    worst = _worst_freshness([c["freshness"] for c in required_avail])
    n_present = sum(1 for c in required_avail if c["status"] in ("PRESENT", "PARTIAL"))
    coverage_ratio = round(n_present / len(required_avail), 4) if required_avail else 0.0
    degraded = [c["component_id"] for c in required_avail if c["freshness"] != "CURRENT"]
    reasons: list[str] = []
    if worst != "CURRENT":
        reasons.append(f"worst_required_source_freshness={worst}")
    for c in contradictions:
        reasons.append(f"contradiction={c['kind']}")

    # availability.contradiction is a SINGLE typed block (schema shape carried
    # over from R1A) -- when more than one contradiction fires, the first
    # (architecture-named "policy stance vs market path") occupies the slot;
    # EVERY fired contradiction still gets its own implications entry AND its
    # own metric-level DISAGREEMENT status below, so no signal is dropped.
    primary_contradiction = contradictions[0] if contradictions else {
        "kind": None, "en": None, "zh": None, "components": [],
    }

    effective_date = rc_asof or cbd_asof or rt_asof
    headline = _headline(effective_date, prior_snapshot)
    changes = _changes(metrics_by_id, prior_snapshot)

    snapshot = {
        "schema": {"contract": "mastermind.macro_workspace_snapshot.v1", "version": "1.0.0"},
        "workspace": {
            "id": "monetary_policy",
            "title": _bil("Monetary Policy", "货币政策"),
            "subtitle": _bil("Policy stance x market-implied path", "政策立场 × 市场隐含路径"),
        },
        "region": {"code": "US", "supported": True, "display_name": "United States"},
        "generation": {
            "generation_id": "PENDING",
            "built_at": built_at,
            "rendered_at": None,
            "producer": PRODUCER,
            "code_version": code_version,
            "calculation_as_of": effective_date,
            "content_sha256": "0" * 64,
        },
        "authority": {
            "class": "context_only", "display_only": True, "can_rank": False,
            "can_gate": False, "can_size": False, "can_originate_signal": False,
            "can_execute": False, "axis_authority_ceiling": "DESCRIPTIVE",
        },
        "availability": {
            "state": worst,
            "required": required_avail,
            "degraded": degraded,
            "coverage_ratio": coverage_ratio,
            "worst_freshness": worst,
            "contradiction": {
                "present": bool(contradictions),
                "kind": primary_contradiction["kind"],
                "en": primary_contradiction["en"],
                "zh": primary_contradiction["zh"],
                "components": primary_contradiction["components"],
            },
            "reasons": reasons,
        },
        "headline": headline,
        "axes": {"items": []},
        "metrics": {"items": metrics},
        "series": {
            "items": [],
            "status": "ABSENT",
            "null_reason": "INSUFFICIENT_HISTORY",
        },
        "drivers": _drivers(metrics_by_id, cbs_by_id),
        "changes": changes,
        "implications": {"items": _implications(stance, contradictions, worst,
                                                coverage_ratio, gap)},
        "scenario_contract": _scenario_contract(),
        "alert_contract": _alert_contract(),
        "sources": {"items": _sources(rc_asof, cbd_asof, rt_asof)},
        "corrections": _corrections(metrics_by_id, effective_date, prior_snapshot),
        "learning": {
            "instrumentation": "first_party",
            "event_names": [
                "macro_workspace_opened", "macro_state_changed_seen",
                "macro_driver_expanded", "macro_source_opened",
                "macro_degraded_state_seen", "macro_unknown_or_refusal_seen",
            ],
            "privacy_note": "Event definitions reuse the existing first-party analytics owner; no second analytics store, no user identity copied into the artifact.",
        },
    }
    return snapshot


# --------------------------------------------------------------------------- #
# sub-builders
# --------------------------------------------------------------------------- #
def _headline(effective_date, prior_snapshot) -> dict:
    """Architecture 10.7 gives Monetary Policy a headline COMPOSITION LIST
    (rates/path/curve/balance-sheet/divergence/calendar), not an x/y quadrant.
    The committed schema's headline.state_id is closed to the liquidity_regime
    A/B/C/D enum and axes.items[].axis_id to its two liquidity axis ids -- both
    unusable here without a shared-schema edit (out of scope, "no shared-file
    edits"). This is resolved honestly, not papered over: state_id stays null
    and typed NOT_APPLICABLE (a real vocabulary member, section 7.7), axes
    stays an empty (schema-legal) array, and the actual headline content lives
    in metrics/drivers/implications instead."""
    prior_method = _get(prior_snapshot, "headline", "method_version")
    return {
        "state_id": None,
        "state_label": {"en": None, "zh": None},
        "subtitle": _bil("Policy rates, market-implied path, and balance sheet",
                          "政策利率、市场隐含路径与资产负债表"),
        "method_version": METHOD_VERSION,
        "effective_date": effective_date,
        "quadrant": {"x": None, "y": None, "x_status": "ABSENT", "y_status": "ABSENT"},
        "prior_state": {
            "state_id": None,
            "effective_date": _get(prior_snapshot, "headline", "effective_date"),
            "method_version": prior_method,
        },
        "transition_distance": None,
        "nearest_boundary": {"axis": None, "distance": None, "null_reason": "NOT_APPLICABLE"},
        "one_month_vector": {"dx": None, "dy": None, "status": "ABSENT", "null_reason": "NOT_APPLICABLE"},
        "hysteresis": {
            "band": 0.0, "applied": False, "held_prior": False,
            "note": ("monetary_policy has no dual-axis quadrant model (architecture "
                     "section 10.7 gives a headline composition list, not an x/y "
                     "quadrant like liquidity_regime/growth_real_economy/etc.); "
                     "headline content lives in metrics (policy rates, futures path, "
                     "curve, balance sheet) and implications (policy stance vs "
                     "market-implied path), not headline.state_id, which is "
                     "NOT_APPLICABLE by design, not by missing data."),
        },
        "status": "ABSENT",
        "null_reason": "NOT_APPLICABLE",
    }


def _detect_contradictions(divergence: list, expectations_pressure: Mapping) -> list[dict]:
    """Typed DISAGREEMENT contradictions, sourced from the OWNER's own
    pre-computed flags (never a threshold this composer invents)."""
    out: list[dict] = []
    d1 = next((d for d in divergence
               if isinstance(d, Mapping) and d.get("key") == "D1_dots_vs_market"), None)
    if d1 is not None and d1.get("active") is True:
        out.append({
            "kind": "dots_vs_market_path",
            "en": d1.get("detail_en") or (
                "Market-implied path diverges from the FOMC SEP median dot beyond "
                "the owner's disclosed tolerance."),
            "zh": d1.get("detail_zh") or (
                "市场隐含路径与FOMC点阵图中位数的偏离超出披露容差。"),
            "components": ["dots_vs_market_gap_bp"],
        })
    net_state = expectations_pressure.get("net_state")
    hawk = _num(expectations_pressure.get("hawk_score"))
    ease = _num(expectations_pressure.get("ease_score"))
    if net_state == "two_sided" and hawk and ease and hawk > 0 and ease > 0:
        sl_raw = expectations_pressure.get("state_label")
        sl = sl_raw if isinstance(sl_raw, Mapping) else {}
        sl_en = sl.get("en") or "two-sided, watch the tape"
        sl_zh = sl.get("zh") or "双向，观察市场走势"
        out.append({
            "kind": "hawk_ease_split",
            "en": (f"Hawkish and easing pressure legs are both active and roughly "
                   f"balanced (hawk={hawk:g} vs ease={ease:g}): {sl_en}."),
            "zh": (f"鹰派与宽松压力腿同时激活且大体制衡（鹰={hawk:g} 对 宽松={ease:g}）："
                   f"{sl_zh}。"),
            "components": ["hawk_score", "ease_score"],
        })
    return out


def _required_availability(built_at, rc: Mapping, fed_row: Mapping | None,
                            rt: Mapping, rc_asof, rt_asof) -> list[dict]:
    labels = {
        "fed_funds_rate": ("Fed funds effective rate", "联邦基金有效利率"),
        "market_implied_path_12m": ("Market-implied 12m path", "市场隐含12个月路径"),
        "curve_2s10s": ("2s10s curve", "2年期-10年期利差"),
        "fed_balance_sheet_impulse": ("Fed balance-sheet impulse", "美联储资产负债表脉冲"),
    }
    rate_path_row = _get(rc, "board", "rate_path_row") or {}
    implied_bp = _num(rate_path_row.get("implied_bp_12m"))
    implied_nyr = rate_path_row.get("not_yet_released") is True
    curve = _num(_get(rt, "state", "rates", "curve_2s10s"))
    curve_nyr = _get(rt, "not_yet_released") is True
    bs = _get(fed_row, "bs_impulse") if fed_row else None
    bs_val = _num(_get(bs, "impulse_13w")) if bs else None

    fed_fresh = _cb_freshness(fed_row, not_yet_released=bool(fed_row and fed_row.get("not_yet_released")))
    specs = [
        ("fed_funds_rate", fed_fresh, _num((fed_row or {}).get("policy_rate")),
         (fed_row or {}).get("asof")),
        ("market_implied_path_12m",
         _aged_freshness(built_at, rc_asof, _MARKET_STALE_DAYS, implied_bp is not None,
                          not_yet_released=implied_nyr),
         implied_bp, rc_asof),
        ("curve_2s10s",
         _aged_freshness(built_at, rt_asof, _CURVE_STALE_DAYS, curve is not None,
                          not_yet_released=curve_nyr),
         curve, rt_asof),
        ("fed_balance_sheet_impulse",
         _aged_freshness(built_at, _get(bs, "asof"), _WEEKLY_BS_STALE_DAYS, bs_val is not None),
         bs_val, _get(bs, "asof")),
    ]
    rows = []
    for cid, fresh, val, asof in specs:
        present = val is not None
        status = "PRESENT" if present and fresh == "CURRENT" else ("PARTIAL" if present else "ABSENT")
        if present:
            null_reason = None
        elif fresh == "NOT_YET_RELEASED":
            null_reason = "NOT_YET_RELEASED"
        elif fresh == "SOURCE_FAILED":
            null_reason = "SOURCE_FAILED"
        else:
            null_reason = "UNKNOWN"
        en, zh = labels[cid]
        rows.append({
            "component_id": cid, "label": _bil(en, zh), "required": True,
            "freshness": fresh, "status": status, "source_asof": asof,
            "null_reason": null_reason,
        })
    return rows


def _metrics(rc_asof, rate_path_row, inflation_row, risk_row, policy_row,
             cbs_by_id, cbd_asof, rt_asof, rt_rates, rt_expect, gap,
             built_at, contradictions: list[dict]) -> list[dict]:
    fired_kinds = {c["kind"] for c in contradictions}
    items: list[dict] = []

    # -- central-bank policy rates (Fed / ECB / BoJ; architecture-named trio) -
    for cb_id, mid, en, zh in _CB_RATE_SPECS:
        row = cbs_by_id.get(cb_id)
        val = _num((row or {}).get("policy_rate"))
        fresh = _cb_freshness(row)
        series = _get(row, "source", "series") if row else None
        items.append(_metric(
            mid, val, "percent", "percent", "realized_policy_rate", "higher_tighter",
            f"engine.cb_desk[{cb_id}]", "cb_desk.cbs.policy_rate",
            (row or {}).get("asof"), fresh,
            source_refs=[f"FRED:{series}"] if series else None,
        ))

    # -- global policy-rate divergence: refuse rather than default to 0 -------
    available_rates = [
        _num(r.get("policy_rate")) for r in cbs_by_id.values()
        if isinstance(r, Mapping) and _num(r.get("policy_rate")) is not None
    ]
    if len(available_rates) >= 2:
        spread_bp = _round((max(available_rates) - min(available_rates)) * 100.0, 1)
        div_status, div_null = "PRESENT", None
        div_fresh = "CURRENT"
    else:
        spread_bp = None
        div_status, div_null = "ABSENT", "COMPUTATION_REFUSED"
        div_fresh = "SOURCE_FAILED"
    items.append(_metric(
        "global_policy_divergence_bp", spread_bp, "basis_points", "bp",
        "max_minus_min_across_reporting_cbs", "higher_more_divergent",
        "engine.cb_desk", "cb_desk.cbs[*].policy_rate", cbd_asof, div_fresh,
        transformation="max(policy_rate) - min(policy_rate) over reporting central banks, in bp; refused (never 0) below 2 reporting banks",
        status=div_status, null_reason=div_null,
    ))

    # -- market-implied path (futures-derived; a PRICE, never a forecast) ----
    implied_bp_12m = _num(rate_path_row.get("implied_bp_12m"))
    items.append(_metric(
        "market_implied_path_12m_bp", implied_bp_12m, "basis_points", "bp",
        "market_implied_futures_price_not_forecast", "higher_more_hikes_priced",
        "engine.rates_inflation_command", "board.rate_path_row.implied_bp_12m",
        rc_asof, _aged_freshness(built_at, rc_asof, _MARKET_STALE_DAYS, implied_bp_12m is not None),
        source_refs=[rate_path_row.get("source_en") or "ZQ fed-funds futures"],
        transformation="futures-implied path reflects risk premium not stripped; not a forecast (owner caveat)",
    ))
    implied_path = rate_path_row.get("implied_path") or {}
    for horizon in ("m6", "m12"):
        val = _num(implied_path.get(horizon))
        items.append(_metric(
            f"market_implied_funds_{horizon}", val, "percent", "percent",
            "market_implied_futures_price_not_forecast", "level",
            "engine.rates_inflation_command", f"board.rate_path_row.implied_path.{horizon}",
            rc_asof, _aged_freshness(built_at, rc_asof, _MARKET_STALE_DAYS, val is not None),
        ))

    # -- FOMC SEP dot plot (owner-native, never fabricated) -------------------
    dots = rate_path_row.get("dots") or []
    nearest_dot = dots[0] if dots else None
    dot_val = _num((nearest_dot or {}).get("median"))
    items.append(_metric(
        "fed_dot_median_nearest", dot_val, "percent", "percent",
        "fomc_sep_median_dot_owner_native", "level",
        "engine.rates_inflation_command", "board.rate_path_row.dots[0].median",
        rc_asof, "CURRENT" if dot_val is not None else "SOURCE_FAILED",
        source_refs=["FRED:FEDTARMD"],
        transformation="owner-native FOMC Summary of Economic Projections median dot, passed through as published; this composer never estimates or fabricates a dot",
    ))

    # -- dots-vs-market disagreement (typed DISAGREEMENT when it fires) ------
    gap_bp = _num(gap.get("gap_bp"))
    gap_disagree = "dots_vs_market_path" in fired_kinds
    items.append(_metric(
        "dots_vs_market_gap_bp", gap_bp, "basis_points", "bp",
        "fed_dot_vs_market_implied_gap", "positive_when_market_prices_above_fed_dot",
        "engine.rates_inflation_command", "board.rate_path_row.gap.gap_bp",
        rc_asof, "CURRENT" if gap_bp is not None else "SOURCE_FAILED",
        status="DISAGREEMENT" if gap_disagree and gap_bp is not None else "PRESENT",
        null_reason="DISAGREEMENT" if gap_disagree and gap_bp is not None else None,
    ))

    # -- hawk/ease pressure legs (typed DISAGREEMENT when two-sided) ---------
    # policy_uncertainty_state is typed DISAGREEMENT exactly when the
    # hawk_ease_split contradiction fired (both pressure legs active and
    # roughly balanced) -- the raw hawk/ease scores themselves are not
    # separately republished as metrics; they are already fully disclosed in
    # the contradiction's own text (implications) and its `components` list.
    hawk_ease_fired = "hawk_ease_split" in fired_kinds
    items.append(_metric(
        "policy_uncertainty_state", policy_row.get("state"), "categorical", None,
        "owner_native_categorical", None,
        "engine.rates_inflation_command", "board.policy_row.state",
        rc_asof, "CURRENT" if policy_row.get("state") is not None else "SOURCE_FAILED",
        status="DISAGREEMENT" if hawk_ease_fired and policy_row.get("state") is not None else "PRESENT",
        null_reason="DISAGREEMENT" if hawk_ease_fired and policy_row.get("state") is not None else None,
    ))

    # -- curve / real-rate structure ------------------------------------------
    nominal_10y = _num(rt_rates.get("nominal_10y"))
    real_10y = _num(rt_rates.get("real_10y"))
    curve_2s10s = _num(rt_rates.get("curve_2s10s"))
    # NOTE: each rt-derived metric computes freshness from ITS OWN value's
    # presence, never a shared group flag -- a missing curve_2s10s must read
    # SOURCE_FAILED even when nominal_10y/real_10y are both present alongside
    # it in the same owner sub-object (they are, in the real artifact, three
    # independently-nullable fields of one desk, not one atomic reading).
    items.append(_metric(
        "nominal_10y", nominal_10y, "percent", "percent", "level", "level",
        "engine.rate_inflation_transmission", "state.rates.nominal_10y", rt_asof,
        _aged_freshness(built_at, rt_asof, _CURVE_STALE_DAYS, nominal_10y is not None),
        source_refs=["FRED:DGS10"],
    ))
    items.append(_metric(
        "real_10y", real_10y, "percent", "percent", "tips_implied_real_yield", "higher_more_restrictive",
        "engine.rate_inflation_transmission", "state.rates.real_10y", rt_asof,
        _aged_freshness(built_at, rt_asof, _CURVE_STALE_DAYS, real_10y is not None),
        source_refs=["FRED:DFII10"],
    ))
    items.append(_metric(
        "curve_2s10s", curve_2s10s, "number", "pct_pts", "level", "higher_steeper",
        "engine.rate_inflation_transmission", "state.rates.curve_2s10s", rt_asof,
        _aged_freshness(built_at, rt_asof, _CURVE_STALE_DAYS, curve_2s10s is not None),
    ))
    breakeven_10y = _num(rt_expect.get("breakeven_10y"))
    items.append(_metric(
        "breakeven_10y", breakeven_10y, "percent", "percent", "tips_breakeven_inflation_expectation",
        "higher_more_inflation_priced", "engine.rate_inflation_transmission",
        "state.expectations.breakeven_10y", rt_asof,
        _aged_freshness(built_at, rt_asof, _CURVE_STALE_DAYS, breakeven_10y is not None),
    ))

    # -- balance sheet: Fed level (owner-native pass-through) + 13w impulses -
    fed_row = cbs_by_id.get("FED")
    fed_bs = _get(fed_row, "bs_impulse") if fed_row else None
    fed_bs_level = _num(_get(fed_bs, "level")) if fed_bs else None
    fed_bs_unit = _get(fed_bs, "unit") if fed_bs else None
    items.append(_metric(
        "fed_balance_sheet_level", fed_bs_level, "currency_bn", fed_bs_unit,
        "level", "higher_more_accommodative", "engine.cb_desk[FED]",
        "cb_desk.cbs.bs_impulse.level", _get(fed_bs, "asof") if fed_bs else None,
        _aged_freshness(built_at, _get(fed_bs, "asof") if fed_bs else None,
                         _WEEKLY_BS_STALE_DAYS, fed_bs_level is not None),
        source_refs=["FRED:WALCL"],
        transformation=("owner-native pass-through; since the 2026-09-04 cb_desk units "
                         "fix the owner normalizes WALCL from FRED's native millions of "
                         "USD into its published 'USD billions' label at source "
                         "(bs_unit_mult) -- the value is propagated AS GIVEN, "
                         "not corrected by this composer"),
    ))
    for cb_id, mid, en, zh in _CB_BS_SPECS:
        row = cbs_by_id.get(cb_id)
        bs = _get(row, "bs_impulse") if row else None
        val = _num(_get(bs, "impulse_13w")) if bs else None
        items.append(_metric(
            mid, val, "percent", "percent", "trailing_13w_pct_change",
            "higher_more_expansionary", f"engine.cb_desk[{cb_id}]",
            "cb_desk.cbs.bs_impulse.impulse_13w", _get(bs, "asof") if bs else None,
            _aged_freshness(built_at, _get(bs, "asof") if bs else None,
                             _WEEKLY_BS_STALE_DAYS, val is not None),
        ))

    # -- recession probability (NY Fed) ---------------------------------------
    nyfed_prob = _num(risk_row.get("nyfed_prob"))
    items.append(_metric(
        "recession_prob_nyfed", nyfed_prob, "percent", "percent",
        "ny_fed_term_spread_model", "higher_more_recession_risk",
        "engine.rates_inflation_command", "board.risk_row.nyfed_prob",
        rc_asof, "CURRENT" if nyfed_prob is not None else "SOURCE_FAILED",
    ))

    # -- inflation-vs-target context (informs stance only; the Inflation
    # System workspace owns the full inflation decomposition -- this composer
    # carries only the one figure rates_command's own policy board publishes).
    vs_target_pp = _num(inflation_row.get("vs_target_pp"))
    items.append(_metric(
        "core_pce_vs_target_pp", vs_target_pp, "number", "pct_pts",
        "core_pce_yoy_minus_2pct_target", "higher_more_above_target",
        "engine.rates_inflation_command", "board.inflation_row.vs_target_pp",
        rc_asof, "CURRENT" if vs_target_pp is not None else "SOURCE_FAILED",
    ))

    # -- meeting calendar: propagate the DATE; never recompute days at build --
    for cb_id, mid, en, zh in _CB_MEETING_SPECS:
        row = cbs_by_id.get(cb_id)
        nxt = _get(row, "next_meeting") if row else None
        days = _num(_get(nxt, "days")) if nxt else None
        meeting_date = _get(nxt, "date") if nxt else None
        items.append(_metric(
            mid, days, "count", "days", "owner_precomputed_at_cb_desk_build_time",
            "lower_more_imminent", f"engine.cb_desk[{cb_id}]", "cb_desk.cbs.next_meeting.days",
            meeting_date, "CURRENT" if days is not None else "SOURCE_FAILED",
            # calculation_as_of pins WHEN the day-count was true: the cb_desk
            # artifact's own as-of, distinct from this snapshot's built_at, per
            # the clock law (section 7.5) -- this composer never recomputes
            # "days to meeting" against its own wall clock.
            calculation_as_of=cbd_asof,
            transformation="owner-precomputed day-count as of the cb_desk build; reference_period carries the exact meeting date, which is the durable fact -- the day-count is a snapshot of distance at cb_desk build time, not re-derived here",
        ))

    return items


def _drivers(metrics_by_id: dict, cbs_by_id: dict) -> dict:
    def _mk(driver_id, label_en, label_zh, owner_field, value, unit, note):
        sign = 0
        mag = None
        if isinstance(value, (int, float)):
            sign = 1 if value > 0 else (-1 if value < 0 else 0)
            mag = abs(value)
        return {
            "driver_id": driver_id, "label": _bil(label_en, label_zh),
            "owner_field": owner_field, "value": value, "unit": unit,
            "impact_sign": sign, "impact_magnitude": mag, "note": note,
            "coverage_state": "PRESENT" if value is not None else "ABSENT",
        }

    rate_side = [
        _mk("fed_funds_rate", "Fed funds effective rate", "联邦基金有效利率",
            "cb_desk.cbs.policy_rate", metrics_by_id.get("fed_funds_rate"), "percent",
            "realized level, sign relative to zero (not a contribution to any axis -- monetary_policy has none)"),
        _mk("market_implied_path_12m_bp", "Market-implied 12m path", "市场隐含12个月路径",
            "board.rate_path_row.implied_bp_12m", metrics_by_id.get("market_implied_path_12m_bp"), "bp",
            "positive = market prices net hikes over 12m; negative = net cuts; a market PRICE, not a forecast"),
        _mk("dots_vs_market_gap_bp", "Dots vs market gap", "点阵图与市场利差",
            "board.rate_path_row.gap.gap_bp", metrics_by_id.get("dots_vs_market_gap_bp"), "bp",
            "positive = market prices a higher rate than the FOMC SEP median dot"),
        _mk("curve_2s10s", "2s10s curve", "2年期-10年期利差",
            "state.rates.curve_2s10s", metrics_by_id.get("curve_2s10s"), "pct_pts",
            "positive = normal (upward-sloping) curve; near/below zero = flat-to-inverted"),
        _mk("real_10y", "Real 10y yield", "实际10年期收益率",
            "state.rates.real_10y", metrics_by_id.get("real_10y"), "percent",
            "higher = more restrictive real financing cost"),
    ]
    balance_sheet = [
        _mk(mid, en, zh, "cb_desk.cbs.bs_impulse.impulse_13w", metrics_by_id.get(mid), "percent",
            "positive = balance sheet expanding (more accommodative); negative = contracting")
        for _cb_id, mid, en, zh in _CB_BS_SPECS
    ]
    return {"rate_side": rate_side, "balance_sheet": balance_sheet}


def _implications(stance: Mapping, contradictions: list[dict], worst_freshness: str,
                   coverage_ratio: float, gap: Mapping) -> list[dict]:
    conf = {
        "data_coverage": _band(coverage_ratio, 0.5, 0.99),
        "source_health": "HIGH" if worst_freshness == "CURRENT" else "LOW",
        "revision_risk": "MEDIUM",
        "method_stability": "HIGH",
        "evidence_breadth": "MEDIUM",
        "contradiction_state": "PRESENT" if contradictions else "ABSENT",
    }
    items: list[dict] = []
    stance_en, stance_zh = stance.get("en"), stance.get("zh")
    if stance_en:
        items.append({
            "implication_id": "policy_stance_descriptive",
            "text": _bil(stance_en, stance_zh or stance_en),
            "evidence_class": "DESCRIPTIVE",
            "confidence": conf,
            "horizon": "current",
            "channels": ["rates", "curve", "credit"],
            "contradictions": [c["kind"] for c in contradictions],
            "trace_ref": "data/rates_command/latest.json#stance",
        })
    for c in contradictions:
        items.append({
            "implication_id": f"contradiction_{c['kind']}",
            "text": _bil(c["en"], c["zh"]),
            "evidence_class": "DESCRIPTIVE",
            "confidence": conf,
            "horizon": "current",
            "channels": ["rates", "curve"],
            "contradictions": [c["kind"]],
            "trace_ref": "data/rates_command/latest.json#divergence",
        })
    if gap:
        horizon_label = gap.get("horizon_label")
        market = gap.get("market")
        fed_dot = gap.get("fed_dot")
        gap_bp = gap.get("gap_bp")
        lean_en, lean_zh = gap.get("lean_en"), gap.get("lean_zh")
        if (horizon_label is not None and market is not None and fed_dot is not None
                and gap_bp is not None and lean_en is not None and lean_zh is not None):
            items.append({
                "implication_id": "dots_vs_market_read",
                "text": _bil(
                    f"At {horizon_label} the market implies {market}% vs the Fed's "
                    f"{fed_dot}% median dot ({gap_bp}bp - {lean_en}). This is a market "
                    "PRICE (futures-implied), not a Fed forecast or stated intent.",
                    f"在{horizon_label}，市场隐含{market}%，对比美联储{fed_dot}%的中位点"
                    f"（{gap_bp}个基点 — {lean_zh}）。这是市场价格（期货隐含），并非美联储"
                    "预测或既定意图。"),
                "evidence_class": "DESCRIPTIVE",
                "confidence": conf,
                "horizon": "months",
                "channels": ["rates", "curve"],
                "contradictions": [],
                "trace_ref": "data/rates_command/latest.json#board.rate_path_row.gap",
            })
    return items


def _scenario_contract() -> dict:
    return {
        "execution_available": False,
        "result_schema": "mastermind.macro_workspace_scenario_result.v1",
        "assumptions": [
            {"assumption_id": "fed_policy_rate_bp", "label": _bil("Fed policy rate", "美联储政策利率"),
             "unit": "bp", "step": 25.0, "min": -300.0, "max": 300.0,
             "owner_field": "board.rate_path_row.policy_rate"},
            {"assumption_id": "market_path_12m_bp", "label": _bil("Market-implied 12m path", "市场隐含12个月路径"),
             "unit": "bp", "step": 10.0, "min": -300.0, "max": 300.0,
             "owner_field": "board.rate_path_row.implied_bp_12m"},
            {"assumption_id": "ecb_policy_rate_bp", "label": _bil("ECB deposit rate", "欧洲央行存款利率"),
             "unit": "bp", "step": 25.0, "min": -200.0, "max": 200.0,
             "owner_field": "cb_desk.cbs[ECB].policy_rate"},
            {"assumption_id": "boj_policy_rate_bp", "label": _bil("BoJ policy rate", "日本银行政策利率"),
             "unit": "bp", "step": 10.0, "min": -100.0, "max": 300.0,
             "owner_field": "cb_desk.cbs[BOJ].policy_rate"},
            {"assumption_id": "fed_balance_sheet_bn", "label": _bil("Fed balance sheet", "美联储资产负债表"),
             "unit": "USD_bn", "step": 50.0, "min": -2000.0, "max": 2000.0,
             "owner_field": "cb_desk.cbs[FED].bs_impulse.level"},
        ],
        "status": "PARTIAL",
        "note": "Assumption vocabulary is declared and closed; this composer ships no scenario execution endpoint (non-goal). A future owner-native pure scenario function produces mastermind.macro_workspace_scenario_result.v1 with no canonical write.",
    }


def _alert_contract() -> dict:
    return {
        "service_available": False,
        "eligible_conditions": [
            {"condition_id": "meeting_approaching", "kind": "release_approaching",
             "label": _bil("CB meeting approaching", "央行会议临近"), "params": ["cb_id", "days"]},
            {"condition_id": "dots_market_gap_shock", "kind": "component_shock",
             "label": _bil("Dots-vs-market gap shock", "点阵图与市场利差冲击"), "params": ["gap_bp"]},
            {"condition_id": "policy_rate_change", "kind": "component_shock",
             "label": _bil("Policy rate change", "政策利率变动"), "params": ["cb_id", "bp"]},
            {"condition_id": "source_stale_or_failed", "kind": "source_stale_or_failed",
             "label": _bil("Source stale or failed", "数据源过期或失败"), "params": ["source_id"]},
            {"condition_id": "source_revision", "kind": "source_revision",
             "label": _bil("Material source revision", "数据源重大修订"), "params": ["source_id"]},
            {"condition_id": "stance_disagreement_change", "kind": "contradiction_change",
             "label": _bil("Stance disagreement change", "立场分歧变化"), "params": ["kind"]},
        ],
        "status": "ABSENT",
        "note": "Eligible condition types are declared; this composer writes no alert (non-goal). Alerts extend the existing Terminal alert lifecycle later; a page shows the Alerts tab only once the service can create/list/evaluate/delete these real conditions.",
    }


def _sources(rc_asof, cbd_asof, rt_asof) -> list[dict]:
    def _src(source_id, en, zh, owner_ref, provider, ref_period):
        return {
            "source_id": source_id,
            "label": _bil(en, zh),
            "owner_ref": owner_ref,
            "provider": provider,
            "reference_period": ref_period,
            "released_at": None,
            "first_known_at": None,
            "collected_at": None,
            "revised_at": None,
            "correction_state": "unknown",
            "transform": None,
            "rights_state": "OPEN",
            "definition_id": None,
            "definition_version": None,
            "artifact_ref": "data/rates_command/latest.json",
            "freshness": "CURRENT",
        }
    return [
        {**_src("fed_funds_futures", "Fed funds futures (market-implied path)", "联邦基金期货（市场隐含路径）",
                "engine.rates_inflation_command", "CME (ZQ, keyless)", rc_asof),
         "artifact_ref": "data/rates_command/latest.json"},
        {**_src("fomc_sep_dots", "FOMC Summary of Economic Projections (median dot)", "FOMC经济预测摘要（中位点）",
                "engine.rates_inflation_command", "Federal Reserve / FRED FEDTARMD", rc_asof),
         "artifact_ref": "data/rates_command/latest.json"},
        {**_src("cb_policy_rates", "Central-bank policy rates (Fed/ECB/BoJ/BoE/SNB/BoC/RBA)", "央行政策利率（美联储/欧央行/日央行/英央行/瑞士央行/加央行/澳央行）",
                "engine.cb_desk", "FRED (DFF/ECBDFR/IRSTCI01JPM156N/...)", cbd_asof),
         "artifact_ref": "data/intl_risk/latest.json#cb_desk"},
        {**_src("cb_balance_sheets", "Central-bank balance sheets (WALCL/ECBASSETSW/JPNASSETS)", "央行资产负债表（WALCL/ECBASSETSW/JPNASSETS）",
                "engine.cb_desk", "FRED", cbd_asof),
         "artifact_ref": "data/intl_risk/latest.json#cb_desk"},
        {**_src("cb_meeting_calendar", "Central-bank meeting calendar", "央行会议日历",
                "engine.cb_desk", "Official CB calendar pages (FOMC/ECB/BoJ/...)", cbd_asof),
         "artifact_ref": "data/intl_risk/cb_calendar.yml"},
        {**_src("treasury_curve_real_yields", "Treasury nominal/real yields and 2s10s curve", "美国国债名义/实际收益率与2年10年利差",
                "engine.rate_inflation_transmission", "FRED (DGS10/DFII10)", rt_asof),
         "artifact_ref": "data/regime/latest.json#rate_inflation_transmission"},
    ]


def _changes(current_metrics_by_id: dict, prior_snapshot: Mapping | None) -> dict:
    if prior_snapshot is None:
        return {"comparability": "NO_PRIOR", "prior_generation_id": None,
                "prior_effective_date": None, "prior_method_version": None,
                "deltas": [], "status": "ABSENT", "null_reason": "WARMUP"}
    prior_method = _get(prior_snapshot, "headline", "method_version")
    prior_gen = _get(prior_snapshot, "generation", "generation_id")
    prior_eff = _get(prior_snapshot, "headline", "effective_date")
    if prior_method != METHOD_VERSION:
        return {"comparability": "METHOD_CHANGED", "prior_generation_id": prior_gen,
                "prior_effective_date": prior_eff, "prior_method_version": prior_method,
                "deltas": [], "status": "ABSENT", "null_reason": "COMPUTATION_REFUSED"}
    deltas = []
    for mid in _TRACKED_CHANGE_METRICS:
        cur = current_metrics_by_id.get(mid)
        prev = _metric_value(prior_snapshot, mid)
        delta = None
        if isinstance(cur, (int, float)) and isinstance(prev, (int, float)):
            delta = _round(cur - prev, 4)
        deltas.append({"metric_id": mid, "prior_value": prev, "current_value": cur,
                       "delta": delta, "note": "same method version; numeric comparison permitted"})
    return {"comparability": "COMPARABLE", "prior_generation_id": prior_gen,
            "prior_effective_date": prior_eff, "prior_method_version": prior_method,
            "deltas": deltas, "status": "PRESENT", "null_reason": None}


def _corrections(current_metrics_by_id: dict, effective_date, prior_snapshot: Mapping | None) -> dict:
    """Scoped supersession detection over the tracked metric subset (mirrors
    the R1A pattern; see liquidity_regime._corrections for the full caveat
    about this being a scoped subset, not a persisted vintage ledger)."""
    prior_gen = _get(prior_snapshot, "generation", "generation_id")
    if prior_snapshot is None:
        return {
            "predecessor_generation_id": None,
            "changed_fingerprints": [],
            "correction_state": "none",
            "note": "First-known snapshot for this owner input; predecessor recorded when a prior accepted print exists.",
        }
    prior_eff = _get(prior_snapshot, "headline", "effective_date")
    if prior_eff != effective_date:
        return {
            "predecessor_generation_id": prior_gen,
            "changed_fingerprints": [],
            "correction_state": "none",
            "note": "Reference period differs from the predecessor print (a new observation, not a revision of the same period); no correction asserted.",
        }
    changed: list[str] = []
    for mid in _TRACKED_CHANGE_METRICS:
        cur = current_metrics_by_id.get(mid)
        prev = _metric_value(prior_snapshot, mid)
        if cur != prev:
            digest16 = sha256(f"{mid}:{cur!r}".encode("utf-8")).hexdigest()[:16]
            changed.append(f"{mid}:{mid}:{digest16}")
    if changed:
        return {
            "predecessor_generation_id": prior_gen,
            "changed_fingerprints": sorted(changed),
            "correction_state": "superseded",
            "note": "Same reference period as the predecessor print, but one or more owner-native metrics changed value: this print supersedes the prior one as a revision.",
        }
    return {
        "predecessor_generation_id": prior_gen,
        "changed_fingerprints": [],
        "correction_state": "none",
        "note": "Same reference period as the predecessor print; no tracked metric changed value (no-change republication).",
    }
