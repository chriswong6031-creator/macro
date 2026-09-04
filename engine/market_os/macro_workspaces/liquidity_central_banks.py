"""Pure composer for the US ``liquidity_central_banks`` workspace snapshot (F01 / R3).

Reads TWO owner-native artifacts (plus one optional history-metadata artifact)
and projects them into a ``mastermind.macro_workspace_snapshot.v1`` body:

* ``site/liquiditydata/global_liquidity_transmission.json`` (schema
  ``global_liquidity_transmission.v1``, model ``glt_state.v1``, W-LIQ.1) - the
  global monetary/USD-funding impulse state: ``state.monetary_impulse`` (raw
  weekly change of a causal expanding z-score), ``state.monetary_impulse_z``
  (the causal expanding z of that change, itself requiring a 52-week owner
  warmup before it is computable), ``state.monetary_stance``,
  ``state.orthogonalised_impulse``, ``state.liquidity_breadth``,
  ``state.usd_funding_impulse``, ``state.policy_liquidity_impulse``,
  ``state.credit_impulse_global`` (structurally refused - see below),
  ``state.label`` (``expanding``/``flat``/``contracting``/``unknown``) and
  ``state.event_reference.quality`` (a SEPARATE closed vocabulary -
  ``easing``/``tightening``/``mixed``/``unknown``, the owner's own
  state-vs-US-quality AGREEMENT label, never a synonym for the direction
  label and never a data-quality score); plus the top-level ``freshness``
  block (the conservative all-evidence ``clocks.evidence_available_at``,
  per-component receipts, and ``monetary_coverage_ratio``/
  ``funding_coverage_ratio``) and the top-level ``quality`` block (data
  lineage/coverage disclosure - degraded flag, missing/stale legs, the
  ``global_credit`` refusal, and a ``confidence`` figure the owner itself
  labels ``data_lineage_and_coverage_only`` and explicitly NOT a predictive
  probability, alpha confidence, or promotion grade);
* the ``cb_desk`` block of ``data/intl_risk/latest.json`` (``engine.cb_desk``)
  - Fed/ECB/BoJ balance-sheet level + 13-week/52-week percent-change impulse,
  each with its own ``asof``/``unit``/``series``;
* ``data/global_liquidity_transmission/state_history_meta.json`` (optional) -
  history-depth metadata (row count, first/last asof) used only to disclose
  the GLT state-history artifact in ``sources``, never to fabricate a
  ``series`` timeseries this composer cannot see row-by-row.

GATE STATUS: architecture 10.9's "same-carrier repair required" gate on
Macro PR #6296 (the W-LIQ.1 global-liquidity transmission producer) is
CLEARED - PR #6296 merged to main 2026-09-04 as 38fd57a6 - so this composer
may consume the GLT artifact as an accepted owner input.

SCOPE BOUNDARY (disclosed, not silently narrowed): architecture 10.9's long-run
"Required composition" also names reserves, TGA, RRP, repo/funding facilities,
and swap-line context (US liquidity quantity/quality, ``data/regime/latest.json``
``liquidity_quality`` block - the SAME owner path ``liquidity_regime.py`` and
``financial_conditions.py`` already read). This bounded R3 packet's owner-input
set is fixed to exactly the two artifacts above (plus the optional history
metadata); it does NOT read ``data/regime/latest.json``. TGA/RRP/reserves
context is therefore not composed here - a future revision may extend
``required_components`` once explicitly directed to add that owner path. This
composer never claims that context exists by omission: it is absent from
``metrics``/``drivers`` entirely, not published as a fabricated null leg.

KNOWN OWNER DEFECT (disclosed, never silently corrected): cb_desk's FED
``bs_impulse.level`` is WALCL's raw FRED reading (natively MILLIONS of USD)
but the owner's own ``unit`` label claims "USD billions". This composer NEVER
rescales or corrects the number. It runs one deterministic, disclosed sanity
check scoped to ``series == "WALCL"`` (the one instance of this defect it has
been told to expect - it does not speculatively apply the same magnitude
check to ECB/BoJ, whose own unit labels are not currently disclosed as
defective): if the label says "billions" but the raw level is implausible at
that scale, the LEVEL leg (only) is refused as SOURCE_FAILED with an honest
note; the unit-free 13-week/52-week PERCENT-CHANGE legs are unaffected and
still published, since a percent change is scale-invariant.

FRESHNESS LAW: GLT publishes on a W-FRI weekly grid (``meta.frequency``). A
mid-week build is CURRENT relative to the last Friday grid tip; this composer
is LATE_WITHIN_TOLERANCE only once built_at has passed the next expected
Friday plus a disclosed grace window, and STALE_SOURCE beyond that (see
``_glt_freshness`` / ``_GLT_CADENCE_DAYS`` / ``_GLT_RELEASE_GRACE_DAYS``).
Per-leg GLT freshness (the FED/ECB/BoJ monetary contribution and the
broad-dollar/HY-OAS/real-10y funding contribution) additionally consults that
leg's OWN ``freshness.components.<group>.<name>.status`` receipt - an
"unusable" leg can never read CURRENT purely from date math. This is the
owner's typed no-look-ahead design; a quality degradation the owner itself
discloses (``quality.status == "degraded"``, e.g. because ``global_credit``
lacks comparable point-in-time coverage) is surfaced honestly via
``availability.reasons`` and a dedicated implication - it is never "fixed",
smoothed over, or silently dropped.

CONTRADICTION DETECTION: GLT's own directional read (``state.label`` -
expanding/contracting) is compared against the Fed's OWN cb_desk 13-week
balance-sheet percent change. When GLT reads decisively expanding/contracting,
the Fed's own 13w change is outside a disclosed flat band, and the two
directions disagree, this composer emits a typed ``global_state_vs_fed_desk``
DISAGREEMENT (never a composer-invented magnitude threshold beyond the one
disclosed flat-band constant). It stays silent whenever GLT itself reads
flat/unknown or the Fed leg is absent/flat - never forced.

HEADLINE: architecture section 10.9 gives this workspace NO headline model at
all - unlike ``liquidity_regime``/``financial_conditions``/``growth``'s
explicit x/y quadrant blueprints, or even ``monetary_policy``'s own
composition-list headline, section 10.9 has no "Headline model" subsection.
Per the ``monetary_policy`` precedent, ``headline.state_id`` stays ``null``
and typed NOT_APPLICABLE (a real vocabulary member, section 7.7) rather than
inventing an axis the architecture never specified; ``axes.items`` stays an
empty (schema-legal) array. The real headline content (global monetary/
funding impulse, Fed/ECB/BoJ balance-sheet impulses, the global-vs-Fed-desk
agreement check) lives in ``metrics``/``drivers``/``implications`` instead.

REGION: published as ``US`` like every current workspace page, though this
composer's owner inputs are explicitly global (Fed/ECB/BoJ) - disclosed via
the ``region_scope_disclosure`` implication rather than left implicit.

DRIVERS BUCKET REUSE (disclosed, mirrors ``financial_conditions.py``): the
contract's ``drivers`` block is closed to exactly ``{rate_side,
balance_sheet}``. ``balance_sheet`` carries the Fed/ECB/BoJ 13-week
balance-sheet impulses (a literal fit). ``rate_side`` carries the GLT USD
funding-side contribution legs (broad dollar / HY OAS / real 10y yield) -
NOT policy rates - because this workspace has no separate funding bucket to
use; the reuse is disclosed in each driver's own ``note`` and in the
``driver_bucket_naming_note`` implication.

NO rank/gate/size/trade authority. NO LLM-originated facts. Descriptive
ceiling only. Depends only on the standard library. The composer NEVER reads
a wall clock: ``built_at`` is passed in by the builder, and every staleness/
age check is a pure function of ``built_at`` and the owner artifacts' own
clocks, so an identical set of owner inputs always yields an identical
snapshot body.
"""
from __future__ import annotations

import datetime as _dt
from hashlib import sha256
from typing import Any, Mapping

METHOD_VERSION = "liquidity_central_banks.compose.v1"
DEFINITION_VERSION = "1.0.0"
PRODUCER = "engine.market_os.macro_workspaces.liquidity_central_banks"

# GLT publishes on a W-FRI weekly grid (meta.frequency). A mid-week build is
# CURRENT relative to the last Friday grid tip; LATE_WITHIN_TOLERANCE only
# once built_at has passed the next expected Friday (+7d) plus a disclosed
# grace window; STALE_SOURCE beyond that. Disclosed, not silently invented -
# the grace window mirrors the ~2-4 business-day release/availability lag
# pattern other composers already use (e.g. financial_conditions' OFR FSI lag).
_GLT_CADENCE_DAYS = 7
_GLT_RELEASE_GRACE_DAYS = 4

# cb_desk balance-sheet legs (level + 13w/52w impulse) reuse monetary_policy.py's
# own disclosed weekly Fed H.4.1 tolerance (data/macro/fed_net_liquidity_meta.json's
# stale_guard_bdays=10, ~14 calendar days) rather than a second, possibly-
# inconsistent copy of that threshold.
_WEEKLY_BS_STALE_DAYS = 14

# The Fed-desk-vs-global-state contradiction flat band (13w %, disclosed, not
# a silently invented threshold): a Fed 13w change smaller than this in
# magnitude is itself reading flat/neutral and can never be "disagreeing"
# with anything.
_FED_FLAT_BAND_PCT = 0.5

# KNOWN OWNER DEFECT sanity check (see module docstring): scoped to
# series == "WALCL" only. A raw level this large under a "billions" label is
# implausible for any G-SIFI-scale central-bank balance sheet (WALCL's native
# FRED unit is millions of USD, not billions) - fail closed, never rescale.
_WALCL_LABELED_BILLIONS_KEYWORD = "billion"
_WALCL_PLAUSIBLE_MAX_IN_LABELED_UNIT = 50_000.0

_TRACKED_CHANGE_METRICS = (
    "glt_monetary_impulse", "glt_monetary_impulse_z", "glt_usd_funding_impulse",
    "glt_liquidity_breadth", "cb_fed_balance_sheet_impulse_13w",
)


# --------------------------------------------------------------------------- #
# small pure helpers (deliberately self-contained -- no cross-import from any
# sibling composer, so this file can be added without touching any other
# module; the shape below intentionally mirrors monetary_policy.py)
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


def _round(v: float | None, n: int = 6) -> float | None:
    return None if v is None else round(float(v), n)


def _bil(en: str | None, zh: str | None) -> dict:
    return {"en": en, "zh": zh}


def _band(v, lo, hi):
    if v is None:
        return None
    return "LOW" if v < lo else ("HIGH" if v > hi else "MEDIUM")


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


def _glt_freshness(built_at, glt_asof, value_present: bool, *, owner_fresh: bool = True) -> str:
    """W-FRI weekly-grid release-lag law (see module docstring). ``owner_fresh``
    carries the owner's OWN freshness/status/degraded (or per-leg receipt
    ``status``) read; it can only ever downgrade a would-be-CURRENT date-math
    result, never upgrade a genuinely stale/absent one."""
    if not value_present:
        return "SOURCE_FAILED"
    age = _age_days(built_at, glt_asof)
    if age is None or age < 0:
        return "SOURCE_FAILED"
    if age <= _GLT_CADENCE_DAYS:
        tier = "CURRENT"
    elif age <= _GLT_CADENCE_DAYS + _GLT_RELEASE_GRACE_DAYS:
        tier = "LATE_WITHIN_TOLERANCE"
    else:
        tier = "STALE_SOURCE"
    if not owner_fresh and tier == "CURRENT":
        return "STALE_SOURCE"
    return tier


def _aged_freshness(built_at, asof, tolerance_days: int, value_present: bool,
                     *, not_yet_released: bool = False) -> str:
    if not value_present:
        return "NOT_YET_RELEASED" if not_yet_released else "SOURCE_FAILED"
    age = _age_days(built_at, asof)
    if age is None:
        return "SOURCE_FAILED"
    return "STALE_SOURCE" if age > tolerance_days else "CURRENT"


def _cb_bs_level_sane(series: Any, unit: Any, level: float | None) -> bool:
    """KNOWN OWNER DEFECT check (module docstring): scoped to WALCL only."""
    if series != "WALCL" or level is None:
        return True
    if not isinstance(unit, str) or _WALCL_LABELED_BILLIONS_KEYWORD not in unit.lower():
        return True
    return abs(level) <= _WALCL_PLAUSIBLE_MAX_IN_LABELED_UNIT


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
def compose(glt: Mapping[str, Any], cb_desk: Mapping[str, Any],
            glt_history_meta: Mapping[str, Any] | None = None, *, built_at: str,
            prior_snapshot: Mapping[str, Any] | None = None,
            code_version: str | None = None) -> dict:
    """Project ``glt`` (global_liquidity_transmission.v1) + ``cb_desk`` (+
    optional ``glt_history_meta``) into an UNSEALED snapshot body. The
    builder seals it via ``contract.finalize``."""
    g = glt or {}
    cbd = cb_desk or {}
    hist = glt_history_meta or {}

    meta = _get(g, "meta") or {}
    fr = _get(g, "freshness") or {}
    q = _get(g, "quality") or {}
    st = _get(g, "state") or {}
    er = _get(st, "event_reference") or {}

    glt_asof = st.get("asof")
    glt_generated_at = meta.get("generated_at")
    glt_owner_fresh = (fr.get("status") == "fresh") and (fr.get("degraded") is not True)
    glt_repr_fresh = _glt_freshness(built_at, glt_asof, glt_asof is not None, owner_fresh=glt_owner_fresh)

    cbs_list = _get(cbd, "cbs") or []
    cbs_by_id = {c.get("id"): c for c in cbs_list if isinstance(c, Mapping)}
    cbd_asof = cbd.get("as_of")

    fed_row = cbs_by_id.get("FED")
    ecb_row = cbs_by_id.get("ECB")
    boj_row = cbs_by_id.get("BOJ")
    fed_bs = _get(fed_row, "bs_impulse") if fed_row else None
    ecb_bs = _get(ecb_row, "bs_impulse") if ecb_row else None
    boj_bs = _get(boj_row, "bs_impulse") if boj_row else None
    fed_impulse_13w = _num(_get(fed_bs, "impulse_13w")) if fed_bs else None

    glt_label = st.get("label")
    contradictions = _detect_contradiction(glt_label, fed_impulse_13w)

    metrics = _metrics(built_at, st, er, q, fr, glt_asof, glt_repr_fresh,
                        fed_bs, ecb_bs, boj_bs, contradictions)
    metrics_by_id = {m["metric_id"]: m["value"] for m in metrics}

    required_avail = _required_availability(built_at, glt_asof, st, fed_bs, glt_owner_fresh)
    worst = _worst_freshness([c["freshness"] for c in required_avail])
    n_present = sum(1 for c in required_avail if c["status"] in ("PRESENT", "PARTIAL"))
    coverage_ratio = round(n_present / len(required_avail), 4) if required_avail else 0.0
    degraded = [c["component_id"] for c in required_avail if c["freshness"] != "CURRENT"]
    reasons: list[str] = []
    if worst != "CURRENT":
        reasons.append(f"worst_required_source_freshness={worst}")
    for c in contradictions:
        reasons.append(f"contradiction={c['kind']}")
    if q.get("status") == "degraded" or q.get("degraded") is True:
        reasons.append("glt_quality_status=degraded")
    missing_or_stale = q.get("missing_or_stale") or []
    if missing_or_stale:
        reasons.append(f"glt_missing_or_stale={list(missing_or_stale)}")

    fed_level_raw = _num(_get(fed_bs, "level")) if fed_bs else None
    fed_series = _get(fed_bs, "series") if fed_bs else None
    fed_unit = _get(fed_bs, "unit") if fed_bs else None
    fed_level_sane = _cb_bs_level_sane(fed_series, fed_unit, fed_level_raw)
    walcl_defect_fired = fed_level_raw is not None and not fed_level_sane

    primary_contradiction = contradictions[0] if contradictions else {
        "kind": None, "en": None, "zh": None, "components": [],
    }

    effective_date = glt_asof or cbd_asof
    headline = _headline(effective_date, prior_snapshot)
    changes = _changes(metrics_by_id, prior_snapshot)

    snapshot = {
        "schema": {"contract": "mastermind.macro_workspace_snapshot.v1", "version": "1.0.0"},
        "workspace": {
            "id": "liquidity_central_banks",
            "title": _bil("Liquidity & Central Banks", "流动性与央行"),
            "subtitle": _bil("Global monetary impulse x Fed/ECB/BoJ balance-sheet stance",
                              "全球货币脉冲 × 美联储/欧央行/日央行资产负债表姿态"),
        },
        "region": {"code": "US", "supported": True, "display_name": "United States"},
        "generation": {
            "generation_id": "PENDING",
            "built_at": built_at,
            "rendered_at": None,
            "producer": PRODUCER,
            "code_version": code_version,
            "calculation_as_of": glt_generated_at or effective_date,
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
        "drivers": _drivers(metrics_by_id),
        "changes": changes,
        "implications": {"items": _implications(
            st, er, q, contradictions, worst, coverage_ratio, walcl_defect_fired)},
        "scenario_contract": _scenario_contract(),
        "alert_contract": _alert_contract(),
        "sources": {"items": _sources(glt_asof, cbd_asof, hist, glt_repr_fresh, required_avail)},
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
    """Architecture 10.9 has NO headline model subsection at all (see module
    docstring). Per the ``monetary_policy`` precedent: state_id stays null
    and typed NOT_APPLICABLE; axes stays an empty (schema-legal) array."""
    prior_method = _get(prior_snapshot, "headline", "method_version")
    return {
        "state_id": None,
        "state_label": {"en": None, "zh": None},
        "subtitle": _bil(
            "Global monetary and USD-funding impulse, and Fed/ECB/BoJ balance-sheet stance",
            "全球货币与美元融资脉冲，及美联储/欧央行/日央行资产负债表姿态"),
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
            "note": ("liquidity_central_banks has no headline model at all in architecture "
                     "section 10.9 -- unlike liquidity_regime/financial_conditions/growth's "
                     "explicit x/y quadrant blueprints or monetary_policy's own composition-"
                     "list headline, section 10.9 has no headline-model subsection, only a "
                     "required-composition list. headline.state_id stays null and this is "
                     "not applicable by design, not by missing data; the real content "
                     "(global monetary/funding impulse, Fed/ECB/BoJ balance-sheet impulses, "
                     "the global-vs-Fed-desk agreement check) lives in metrics/drivers/"
                     "implications instead. Region is published as US per every current "
                     "Macro & Monetary page even though this composer's owner inputs are "
                     "explicitly global -- see the region_scope_disclosure implication for "
                     "the reader-facing version of this note."),
        },
        "status": "ABSENT",
        "null_reason": "NOT_APPLICABLE",
    }


def _detect_contradiction(glt_label: Any, fed_impulse_13w: float | None) -> list[dict]:
    """GLT's own directional read vs the Fed's OWN cb_desk 13w balance-sheet
    percent change (see module docstring). Owner-native on both sides; the
    only composer-invented number is the disclosed flat-band constant that
    keeps a merely-noisy Fed reading from manufacturing a contradiction."""
    out: list[dict] = []
    if glt_label in ("expanding", "contracting") and fed_impulse_13w is not None:
        if abs(fed_impulse_13w) >= _FED_FLAT_BAND_PCT:
            fed_direction = "expanding" if fed_impulse_13w > 0 else "contracting"
            if fed_direction != glt_label:
                glt_word_zh = "扩张" if glt_label == "expanding" else "收缩"
                fed_word_zh = "扩张" if fed_direction == "expanding" else "收缩"
                out.append({
                    "kind": "global_state_vs_fed_desk",
                    "en": (f"The global GLT monetary read is {glt_label}, but the Fed's own "
                           f"13-week balance-sheet change is {fed_impulse_13w:g}% "
                           f"({fed_direction}) - the Fed desk's own balance-sheet trend does "
                           "not agree with the global monetary-impulse direction."),
                    "zh": (f"全球GLT货币解读为{glt_word_zh}，但美联储自身13周资产负债表变化为"
                           f"{fed_impulse_13w:g}%（{fed_word_zh}）——"
                           "美联储自身资产负债表趋势与全球货币脉冲方向不一致。"),
                    "components": ["glt_monetary_impulse", "cb_fed_balance_sheet_impulse_13w"],
                })
    return out


def _required_availability(built_at, glt_asof, st, fed_bs, glt_owner_fresh) -> list[dict]:
    labels = {
        "glt_monetary_impulse": ("Global monetary impulse", "全球货币脉冲"),
        "glt_liquidity_breadth": ("Global liquidity breadth", "全球流动性广度"),
        "glt_usd_funding_impulse": ("USD funding impulse", "美元融资脉冲"),
        "cb_fed_balance_sheet_impulse_13w": ("Fed balance-sheet impulse (13w)", "美联储资产负债表脉冲（13周）"),
    }
    monetary_impulse = _num(st.get("monetary_impulse"))
    liquidity_breadth = _num(st.get("liquidity_breadth"))
    usd_funding_impulse = _num(st.get("usd_funding_impulse"))
    fed_impulse_13w = _num(_get(fed_bs, "impulse_13w")) if fed_bs else None
    fed_bs_asof = _get(fed_bs, "asof") if fed_bs else None

    specs = [
        ("glt_monetary_impulse", monetary_impulse,
         _glt_freshness(built_at, glt_asof, monetary_impulse is not None, owner_fresh=glt_owner_fresh),
         glt_asof),
        ("glt_liquidity_breadth", liquidity_breadth,
         _glt_freshness(built_at, glt_asof, liquidity_breadth is not None, owner_fresh=glt_owner_fresh),
         glt_asof),
        ("glt_usd_funding_impulse", usd_funding_impulse,
         _glt_freshness(built_at, glt_asof, usd_funding_impulse is not None, owner_fresh=glt_owner_fresh),
         glt_asof),
        ("cb_fed_balance_sheet_impulse_13w", fed_impulse_13w,
         _aged_freshness(built_at, fed_bs_asof, _WEEKLY_BS_STALE_DAYS, fed_impulse_13w is not None),
         fed_bs_asof),
    ]
    rows = []
    for cid, val, fresh, asof in specs:
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


def _cb_bs_metrics(cb_id: str, bs: Mapping | None, built_at: str, *,
                    disagree: bool = False) -> list[dict]:
    level_raw = _num(_get(bs, "level")) if bs else None
    unit = _get(bs, "unit") if bs else None
    series = _get(bs, "series") if bs else None
    asof = _get(bs, "asof") if bs else None
    impulse_13w = _num(_get(bs, "impulse_13w")) if bs else None
    impulse_52w = _num(_get(bs, "impulse_52w")) if bs else None

    sane = _cb_bs_level_sane(series, unit, level_raw)
    if bs is None:
        level_value, level_fresh, level_null = None, "SOURCE_FAILED", "SOURCE_FAILED"
        level_note = f"No balance-sheet data reported for {cb_id} this cycle (owner cb_desk gap)."
    elif level_raw is not None and not sane:
        level_value, level_fresh, level_null = None, "SOURCE_FAILED", "SOURCE_FAILED"
        level_note = (
            f"This composer refused to publish the level reading: the owner unit "
            f"label reads {unit!r} but the raw level ({level_raw:g}) is implausible "
            f"at that scale for {series} - a known owner cb_desk units defect (see "
            "the WALCL disclosure note in the module docstring). This composer never "
            "rescales or corrects the number; only the LEVEL leg fails, the unit-free "
            "13w/52w percent-change legs below are unaffected."
        )
    else:
        level_value = level_raw
        level_fresh = _aged_freshness(built_at, asof, _WEEKLY_BS_STALE_DAYS, level_raw is not None)
        level_null = None
        level_note = "owner-native pass-through; unit exactly as disclosed by cb_desk, never corrected by this composer"

    cb_lower = cb_id.lower()
    impulse_13w_disagree = disagree and impulse_13w is not None
    return [
        _metric(
            f"cb_{cb_lower}_balance_sheet_level", level_value, "currency_bn", unit,
            "level", "higher_more_accommodative", f"engine.cb_desk[{cb_id}]",
            "cb_desk.cbs.bs_impulse.level", asof, level_fresh,
            source_refs=[f"FRED:{series}"] if series else None,
            transformation=level_note, null_reason=level_null,
        ),
        _metric(
            f"cb_{cb_lower}_balance_sheet_impulse_13w", impulse_13w, "percent", "percent",
            "trailing_13w_pct_change", "higher_more_expansionary", f"engine.cb_desk[{cb_id}]",
            "cb_desk.cbs.bs_impulse.impulse_13w", asof,
            _aged_freshness(built_at, asof, _WEEKLY_BS_STALE_DAYS, impulse_13w is not None),
            source_refs=[f"FRED:{series}"] if series else None,
            status="DISAGREEMENT" if impulse_13w_disagree else "PRESENT",
            null_reason="DISAGREEMENT" if impulse_13w_disagree else None,
        ),
        _metric(
            f"cb_{cb_lower}_balance_sheet_impulse_52w", impulse_52w, "percent", "percent",
            "trailing_52w_pct_change", "higher_more_expansionary", f"engine.cb_desk[{cb_id}]",
            "cb_desk.cbs.bs_impulse.impulse_52w", asof,
            _aged_freshness(built_at, asof, _WEEKLY_BS_STALE_DAYS, impulse_52w is not None),
            source_refs=[f"FRED:{series}"] if series else None,
        ),
    ]


def _metrics(built_at, st, er, q, fr, glt_asof, glt_repr_fresh,
             fed_bs, ecb_bs, boj_bs, contradictions: list[dict]) -> list[dict]:
    items: list[dict] = []
    fired_kinds = {c["kind"] for c in contradictions}

    # -- GLT state aggregates (whole-state W-FRI release-lag freshness) ------ #
    mi_raw = _num(st.get("monetary_impulse"))
    mi_disagree = "global_state_vs_fed_desk" in fired_kinds and mi_raw is not None
    items.append(_metric(
        "glt_monetary_impulse", mi_raw, "number", "z_score_pts",
        "weekly_change_in_expanding_z_score", "higher_more_expansionary",
        "engine.global_liquidity_transmission", "state.monetary_impulse",
        glt_asof, glt_repr_fresh,
        status="DISAGREEMENT" if mi_disagree else "PRESENT",
        null_reason="DISAGREEMENT" if mi_disagree else None,
        transformation="owner-native weekly first difference of the causal monetary "
                        "stance z-score; a positive-vs-negative sign is the direction "
                        "reading, not itself standardized",
    ))

    mi_z = _num(st.get("monetary_impulse_z"))
    if mi_z is not None:
        mi_z_status, mi_z_null = "PRESENT", None
    elif mi_raw is not None:
        mi_z_status, mi_z_null = "ABSENT", "INSUFFICIENT_HISTORY"
    else:
        mi_z_status, mi_z_null = "ABSENT", "SOURCE_FAILED"
    mi_z_fresh = glt_repr_fresh if (mi_z is not None or mi_raw is not None) else "SOURCE_FAILED"
    items.append(_metric(
        "glt_monetary_impulse_z", mi_z, "z_score", "stddev",
        "prior_only_expanding_z_score_of_weekly_change", "higher_more_expansionary",
        "engine.global_liquidity_transmission", "state.monetary_impulse_z",
        glt_asof, mi_z_fresh, status=mi_z_status, null_reason=mi_z_null,
        transformation="causal, prior-only expanding z-score of the weekly monetary-"
                        "impulse first difference; the owner's own design requires a "
                        "52-week warmup before this standardized figure is computable "
                        "- an early-history week legitimately publishes the raw "
                        "monetary_impulse without this standardized twin, and this "
                        "composer never estimates one in its place",
    ))

    items.append(_metric(
        "glt_monetary_stance", _num(st.get("monetary_stance")), "z_score", "stddev",
        "expanding_z_score", "higher_more_expansionary",
        "engine.global_liquidity_transmission", "state.monetary_stance",
        glt_asof, glt_repr_fresh,
    ))

    items.append(_metric(
        "glt_orthogonalised_impulse", _num(st.get("orthogonalised_impulse")), "z_score",
        "stddev", "causal_regression_residual_z_units", "higher_more_expansionary",
        "engine.global_liquidity_transmission", "state.orthogonalised_impulse",
        glt_asof, glt_repr_fresh,
    ))

    items.append(_metric(
        "glt_liquidity_breadth", _num(st.get("liquidity_breadth")), "ratio", "share_0_to_1",
        "share_of_components_agreeing_with_direction", "higher_broader_agreement",
        "engine.global_liquidity_transmission", "state.liquidity_breadth",
        glt_asof, glt_repr_fresh,
    ))

    items.append(_metric(
        "glt_usd_funding_impulse", _num(st.get("usd_funding_impulse")), "z_score", "stddev",
        "expanding_z_score_positive_is_easier", "higher_easier_funding",
        "engine.global_liquidity_transmission", "state.usd_funding_impulse",
        glt_asof, glt_repr_fresh,
    ))

    items.append(_metric(
        "glt_policy_liquidity_impulse", _num(st.get("policy_liquidity_impulse")), "number",
        "z_score_pts", "weekly_change_in_expanding_z_score", "higher_more_expansionary",
        "engine.global_liquidity_transmission", "state.policy_liquidity_impulse",
        glt_asof, glt_repr_fresh,
        transformation="owner's own policy-liquidity-impulse shock-family reading; by "
                        "construction this coincides with monetary_impulse for the shock "
                        "class this snapshot's owner artifact currently reports - "
                        "published as its own field because it carries the owner-native "
                        "shock_type semantics, not merged with glt_monetary_impulse",
    ))

    # -- global credit: refused rather than a fabricated global scalar ------- #
    credit_raw = _num(st.get("credit_impulse_global"))
    global_credit = _get(q, "global_credit") or {}
    gc_status = global_credit.get("status")
    if credit_raw is not None:
        credit_status, credit_null, credit_fresh = "PRESENT", None, glt_repr_fresh
    else:
        credit_status = "ABSENT"
        credit_fresh = "NOT_COVERED" if gc_status else "SOURCE_FAILED"
        credit_null = "NOT_COVERED" if gc_status else "SOURCE_FAILED"
    items.append(_metric(
        "glt_credit_impulse_global", credit_raw, "z_score", "stddev",
        "cross_country_credit_impulse_comparison", "higher_more_credit_expansion",
        "engine.global_liquidity_transmission", "state.credit_impulse_global",
        glt_asof, credit_fresh, status=credit_status, null_reason=credit_null,
        transformation=(f"owner-disclosed refusal: {gc_status or 'no coverage status disclosed'} "
                         "- US C&I loans and China TSF are different constructs and are kept as "
                         "separate context (quality.global_credit.components), never blended into "
                         "a fabricated single global-credit scalar (architecture 10.9: 'separate "
                         "credit contexts rather than a fabricated global credit scalar')"),
    ))

    # -- state labels (owner-native categorical vocabularies) ---------------- #
    items.append(_metric(
        "glt_state_label", st.get("label"), "categorical", None, "owner_native_categorical",
        None, "engine.global_liquidity_transmission", "state.label", glt_asof, glt_repr_fresh,
        transformation="owner label_enum member (expanding/flat/contracting/unknown); "
                        "'unknown' -- when the owner publishes it -- is itself a real "
                        "disclosed value, not a null placeholder",
    ))
    items.append(_metric(
        "glt_state_quality_label", er.get("quality"), "categorical", None,
        "state_vs_us_quality_agreement_label", None,
        "engine.global_liquidity_transmission", "state.event_reference.quality",
        glt_asof, glt_repr_fresh,
        transformation="a different vocabulary from glt_state_label: quality_enum "
                        "(easing/tightening/mixed/unknown) is the owner's state-vs-US-"
                        "quality agreement label, never a synonym for the "
                        "expanding/flat/contracting direction reading, and never a "
                        "data-quality score (see glt_confidence for that concept)",
    ))

    # -- confidence: data lineage/coverage only, never a probability ---------- #
    conf_val = _num(_get(q, "confidence", "value"))
    items.append(_metric(
        "glt_confidence", conf_val, "ratio", "ratio_0_1", "level",
        "higher_more_coverage_and_pit_reliability",
        "engine.global_liquidity_transmission", "quality.confidence.value",
        glt_asof, glt_repr_fresh if conf_val is not None else "SOURCE_FAILED",
        transformation="monetary coverage ratio times mean disclosed point-in-time "
                        "reliability across contributing sources; the owner's own "
                        "disclosure explicitly excludes this from being read as a "
                        "predictive probability, an alpha confidence, or a promotion "
                        "grade, and this composer never reports it as one (frequencies, "
                        "never confidence, as a probability claim)",
    ))

    items.append(_metric(
        "glt_monetary_coverage_ratio", _num(fr.get("monetary_coverage_ratio")), "ratio",
        "ratio_0_1", "level", "higher_more_coverage",
        "engine.global_liquidity_transmission", "freshness.monetary_coverage_ratio",
        glt_asof, glt_repr_fresh,
    ))
    items.append(_metric(
        "glt_funding_coverage_ratio", _num(fr.get("funding_coverage_ratio")), "ratio",
        "ratio_0_1", "level", "higher_more_coverage",
        "engine.global_liquidity_transmission", "freshness.funding_coverage_ratio",
        glt_asof, glt_repr_fresh,
    ))

    # -- per-leg GLT contribution z-scores (own per-leg receipt freshness) --- #
    monetary_snap = _get(fr, "component_snapshot", "monetary") or {}
    monetary_status = _get(fr, "components", "monetary") or {}
    for leg, mid in (
        ("fed", "glt_fed_monetary_contribution_z"),
        ("ecb", "glt_ecb_monetary_contribution_z"),
        ("boj", "glt_boj_monetary_contribution_z"),
    ):
        val = _num(_get(monetary_snap, leg, "current_contribution_z"))
        leg_status = _get(monetary_status, leg, "status")
        leg_fresh = _glt_freshness(built_at, glt_asof, val is not None, owner_fresh=(leg_status == "usable"))
        items.append(_metric(
            mid, val, "z_score", "stddev", "standardized_monetary_contribution",
            "higher_more_expansionary", "engine.global_liquidity_transmission",
            f"freshness.component_snapshot.monetary.{leg}.current_contribution_z",
            glt_asof, leg_fresh,
        ))

    funding_snap = _get(fr, "component_snapshot", "usd_funding") or {}
    funding_status = _get(fr, "components", "usd_funding") or {}
    for leg, mid in (
        ("broad_dollar", "glt_broad_dollar_contribution_z"),
        ("high_yield_oas", "glt_high_yield_oas_contribution_z"),
        ("real_yield_10y", "glt_real_yield_10y_contribution_z"),
    ):
        val = _num(_get(funding_snap, leg, "current_contribution_z"))
        leg_status = _get(funding_status, leg, "status")
        leg_fresh = _glt_freshness(built_at, glt_asof, val is not None, owner_fresh=(leg_status == "usable"))
        items.append(_metric(
            mid, val, "z_score", "stddev", "standardized_funding_contribution",
            "higher_easier_funding", "engine.global_liquidity_transmission",
            f"freshness.component_snapshot.usd_funding.{leg}.current_contribution_z",
            glt_asof, leg_fresh,
        ))

    # -- cb_desk-sourced balance-sheet level / 13w / 52w impulses ------------- #
    for cb_id, bs in (("FED", fed_bs), ("ECB", ecb_bs), ("BOJ", boj_bs)):
        cb_disagree = cb_id == "FED" and "global_state_vs_fed_desk" in fired_kinds
        items.extend(_cb_bs_metrics(cb_id, bs, built_at, disagree=cb_disagree))

    return items


def _drivers(metrics_by_id: dict) -> dict:
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

    balance_sheet = [
        _mk("cb_fed_balance_sheet_impulse_13w", "Fed balance-sheet impulse (13w)",
            "美联储资产负债表脉冲（13周）", "cb_desk.cbs[FED].bs_impulse.impulse_13w",
            metrics_by_id.get("cb_fed_balance_sheet_impulse_13w"), "percent",
            "positive = balance sheet expanding over the trailing 13 weeks; negative = contracting"),
        _mk("cb_ecb_balance_sheet_impulse_13w", "ECB balance-sheet impulse (13w)",
            "欧洲央行资产负债表脉冲（13周）", "cb_desk.cbs[ECB].bs_impulse.impulse_13w",
            metrics_by_id.get("cb_ecb_balance_sheet_impulse_13w"), "percent",
            "positive = balance sheet expanding over the trailing 13 weeks; negative = contracting"),
        _mk("cb_boj_balance_sheet_impulse_13w", "BoJ balance-sheet impulse (13w)",
            "日本银行资产负债表脉冲（13周）", "cb_desk.cbs[BOJ].bs_impulse.impulse_13w",
            metrics_by_id.get("cb_boj_balance_sheet_impulse_13w"), "percent",
            "positive = balance sheet expanding over the trailing 13 weeks; negative = contracting"),
    ]
    rate_side = [
        _mk("glt_broad_dollar_contribution_z", "Broad dollar contribution (z)",
            "广义美元贡献（z值）",
            "freshness.component_snapshot.usd_funding.broad_dollar.current_contribution_z",
            metrics_by_id.get("glt_broad_dollar_contribution_z"), "z_score",
            "bucket reuse: published under drivers.rate_side because the contract's "
            "driver bucket pair is fixed as rate_side/balance_sheet; this is a USD "
            "funding leg, not a policy-rate driver -- see the driver_bucket_naming_note "
            "implication"),
        _mk("glt_high_yield_oas_contribution_z", "HY OAS contribution (z)",
            "高收益利差贡献（z值）",
            "freshness.component_snapshot.usd_funding.high_yield_oas.current_contribution_z",
            metrics_by_id.get("glt_high_yield_oas_contribution_z"), "z_score",
            "bucket reuse: see glt_broad_dollar_contribution_z's note"),
        _mk("glt_real_yield_10y_contribution_z", "Real 10y yield contribution (z)",
            "实际10年期收益率贡献（z值）",
            "freshness.component_snapshot.usd_funding.real_yield_10y.current_contribution_z",
            metrics_by_id.get("glt_real_yield_10y_contribution_z"), "z_score",
            "bucket reuse: see glt_broad_dollar_contribution_z's note"),
    ]
    return {"rate_side": rate_side, "balance_sheet": balance_sheet}


def _implications(st, er, q, contradictions, worst_freshness, coverage_ratio,
                   walcl_defect_fired: bool) -> list[dict]:
    conf = {
        "data_coverage": _band(coverage_ratio, 0.5, 0.99),
        "source_health": "HIGH" if worst_freshness == "CURRENT" else "LOW",
        "revision_risk": "MEDIUM",
        "method_stability": "HIGH",
        "evidence_breadth": "MEDIUM",
        "contradiction_state": "PRESENT" if contradictions else "ABSENT",
    }
    items: list[dict] = []
    label = st.get("label")
    quality_label = er.get("quality")
    if label is not None:
        items.append({
            "implication_id": "global_liquidity_state_descriptive",
            "text": _bil(
                f"Global monetary and USD-funding impulse reads {label} this week "
                f"(owner state-vs-quality read: {quality_label}).",
                f"本周全球货币与美元融资脉冲读数为{label}"
                f"（数据源自身的状态与质量一致性读数为：{quality_label}）。"),
            "evidence_class": "DESCRIPTIVE",
            "confidence": conf,
            "horizon": "current",
            "channels": ["liquidity", "funding", "credit"],
            "contradictions": [c["kind"] for c in contradictions],
            "trace_ref": "site/liquiditydata/global_liquidity_transmission.json#state",
        })
    for c in contradictions:
        items.append({
            "implication_id": f"contradiction_{c['kind']}",
            "text": _bil(c["en"], c["zh"]),
            "evidence_class": "DESCRIPTIVE",
            "confidence": conf,
            "horizon": "current",
            "channels": ["liquidity", "funding"],
            "contradictions": [c["kind"]],
            "trace_ref": "data/intl_risk/latest.json#cb_desk",
        })
    items.append({
        "implication_id": "glt_confidence_is_not_a_probability",
        "text": _bil(
            "The GLT confidence figure measures data lineage and coverage only "
            "(monetary coverage times the mean disclosed point-in-time reliability "
            "of contributing sources). It is never a predictive probability, an "
            "alpha confidence, or a promotion grade, and this composer never "
            "reports it as one.",
            "GLT置信度数字仅衡量数据谱系与覆盖率（货币覆盖率乘以各数据源平均披露的时点可靠性），"
            "绝非预测概率、alpha置信度或晋升评级，本组合器也从不将其作为此类指标报告。"),
        "evidence_class": "DESCRIPTIVE",
        "confidence": conf,
        "horizon": "current",
        "channels": ["liquidity"],
        "contradictions": [],
        "trace_ref": "site/liquiditydata/global_liquidity_transmission.json#quality.confidence",
    })
    if q.get("status") == "degraded" or q.get("degraded") is True:
        reason_bits = []
        gc = q.get("global_credit") or {}
        if gc.get("status"):
            reason_bits.append(f"global credit context: {gc.get('status')}")
        missing = q.get("missing_or_stale") or []
        if missing:
            reason_bits.append(f"missing/stale legs: {', '.join(str(m) for m in missing)}")
        detail = "; ".join(reason_bits) if reason_bits else "no further detail disclosed by the owner"
        items.append({
            "implication_id": "glt_quality_degraded_passthrough",
            "text": _bil(
                f"The GLT owner itself marks this cycle's overall quality as degraded "
                f"({detail}). This composer passes that read through unchanged rather "
                "than smoothing it over or recomputing a cleaner-looking number.",
                f"GLT数据源自身将本周期的整体质量标记为降级（{detail}）。本组合器原样传递该判断，"
                "不做平滑处理，也不重新计算出一个更好看的数字。"),
            "evidence_class": "DESCRIPTIVE",
            "confidence": conf,
            "horizon": "current",
            "channels": ["liquidity", "credit"],
            "contradictions": [],
            "trace_ref": "site/liquiditydata/global_liquidity_transmission.json#quality",
        })
    if walcl_defect_fired:
        items.append({
            "implication_id": "fed_balance_sheet_level_unit_defect",
            "text": _bil(
                "The Fed balance-sheet LEVEL figure could not be published this cycle: "
                "the upstream central-bank desk labels its unit as billions of dollars, "
                "but the raw number is the scale of the native millions-of-dollars WALCL "
                "reading. Rather than guess and rescale, this composer refuses the level "
                "reading and publishes it as a failed source; the unit-free 13-week and "
                "52-week percent changes are unaffected and remain published.",
                "美联储资产负债表水平数值本周期无法发布：上游央行台面将单位标注为十亿美元，"
                "但原始数字的量级实际对应原生的百万美元WALCL读数。本组合器不做猜测性换算，"
                "而是拒绝该水平读数并将其标记为数据源失败；不涉及单位的13周与52周百分比变化"
                "不受影响，仍照常发布。"),
            "evidence_class": "DESCRIPTIVE",
            "confidence": conf,
            "horizon": "current",
            "channels": ["liquidity"],
            "contradictions": [],
            "trace_ref": "data/intl_risk/latest.json#cb_desk",
        })
    items.append({
        "implication_id": "driver_bucket_naming_note",
        "text": _bil(
            "The drivers.rate_side bucket in this snapshot carries USD funding-side "
            "legs (broad dollar, HY OAS, real 10y yield), not policy rates. The "
            "contract's driver bucket pair is fixed as rate_side/balance_sheet and "
            "this workspace has no separate funding bucket to use, so the naming is "
            "cosmetic bucket reuse, disclosed here rather than left implicit.",
            "本快照中drivers.rate_side分组承载的是美元融资端分项（广义美元、高收益利差、"
            "实际10年期收益率），而非政策利率。合约的驱动因素分组固定为rate_side/"
            "balance_sheet，本工作区没有独立的融资分组可用，因此命名属于用途借用，"
            "在此明确披露而非隐含处理。"),
        "evidence_class": "DESCRIPTIVE",
        "confidence": conf,
        "horizon": "current",
        "channels": ["liquidity"],
        "contradictions": [],
        "trace_ref": "engine.market_os.macro_workspaces.liquidity_central_banks#drivers",
    })
    items.append({
        "implication_id": "region_scope_disclosure",
        "text": _bil(
            "This workspace is published under the US region label like every "
            "current Macro & Monetary page, but its owner inputs are explicitly "
            "global: the GLT monetary/funding state spans the Fed, ECB, and BoJ, "
            "and the balance-sheet desk covers multiple central banks, not a "
            "US-only economic series.",
            "本工作区与当前所有宏观与货币页面一样以US区域标签发布，但其数据源明确为全球性："
            "GLT货币/融资状态涵盖美联储、欧央行与日本银行，资产负债表台面覆盖多家央行，"
            "而非单一美国经济序列。"),
        "evidence_class": "DESCRIPTIVE",
        "confidence": conf,
        "horizon": "current",
        "channels": ["liquidity"],
        "contradictions": [],
        "trace_ref": "engine.market_os.macro_workspaces.liquidity_central_banks#region",
    })
    return items


def _scenario_contract() -> dict:
    return {
        "execution_available": False,
        "result_schema": "mastermind.macro_workspace_scenario_result.v1",
        "assumptions": [
            {"assumption_id": "fed_balance_sheet_13w_pct", "label": _bil("Fed balance-sheet 13w change", "美联储资产负债表13周变化"),
             "unit": "pct", "step": 0.5, "min": -20.0, "max": 20.0,
             "owner_field": "cb_desk.cbs[FED].bs_impulse.impulse_13w"},
            {"assumption_id": "ecb_balance_sheet_13w_pct", "label": _bil("ECB balance-sheet 13w change", "欧洲央行资产负债表13周变化"),
             "unit": "pct", "step": 0.5, "min": -20.0, "max": 20.0,
             "owner_field": "cb_desk.cbs[ECB].bs_impulse.impulse_13w"},
            {"assumption_id": "boj_balance_sheet_13w_pct", "label": _bil("BoJ balance-sheet 13w change", "日本银行资产负债表13周变化"),
             "unit": "pct", "step": 0.5, "min": -20.0, "max": 20.0,
             "owner_field": "cb_desk.cbs[BOJ].bs_impulse.impulse_13w"},
            {"assumption_id": "usd_funding_impulse_z", "label": _bil("USD funding impulse", "美元融资脉冲"),
             "unit": "z", "step": 0.1, "min": -3.0, "max": 3.0,
             "owner_field": "state.usd_funding_impulse"},
            {"assumption_id": "global_monetary_impulse_z", "label": _bil("Global monetary impulse (z)", "全球货币脉冲（z值）"),
             "unit": "z", "step": 0.1, "min": -3.0, "max": 3.0,
             "owner_field": "state.monetary_impulse_z"},
        ],
        "status": "PARTIAL",
        "note": "Assumption vocabulary is declared and closed; this composer ships no scenario execution endpoint (non-goal). A future owner-native pure scenario function produces mastermind.macro_workspace_scenario_result.v1 with no canonical write.",
    }


def _alert_contract() -> dict:
    return {
        "service_available": False,
        "eligible_conditions": [
            {"condition_id": "glt_label_transition", "kind": "state_transition",
             "label": _bil("Global monetary state change", "全球货币状态变化"), "params": ["from_label", "to_label"]},
            {"condition_id": "breadth_shock", "kind": "component_shock",
             "label": _bil("Liquidity breadth shock", "流动性广度冲击"), "params": ["liquidity_breadth"]},
            {"condition_id": "usd_funding_stress_shock", "kind": "component_shock",
             "label": _bil("USD funding stress shock", "美元融资压力冲击"), "params": ["usd_funding_impulse"]},
            {"condition_id": "fed_balance_sheet_shock", "kind": "component_shock",
             "label": _bil("Central-bank balance-sheet shock", "央行资产负债表冲击"), "params": ["cb_id", "pct_13w"]},
            {"condition_id": "source_stale_or_failed", "kind": "source_stale_or_failed",
             "label": _bil("Source stale or failed", "数据源过期或失败"), "params": ["source_id"]},
            {"condition_id": "global_vs_fed_disagreement_change", "kind": "contradiction_change",
             "label": _bil("Global-vs-Fed-desk disagreement change", "全球与美联储台面分歧变化"), "params": ["kind"]},
        ],
        "status": "ABSENT",
        "note": "Eligible condition types are declared; this composer writes no alert (non-goal). Alerts extend the existing Terminal alert lifecycle later; a page shows the Alerts tab only once the service can create/list/evaluate/delete these real conditions.",
    }


def _sources(glt_asof, cbd_asof, hist, glt_repr_fresh, required_avail) -> list[dict]:
    fed_row = next((r for r in required_avail if r["component_id"] == "cb_fed_balance_sheet_impulse_13w"), None)
    fed_fresh = fed_row["freshness"] if fed_row else "SOURCE_FAILED"

    def _src(source_id, en, zh, owner_ref, provider, ref_period, artifact_ref, fresh):
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
            "artifact_ref": artifact_ref,
            "freshness": fresh,
        }

    return [
        _src("glt_state", "Global Liquidity Transmission state (monetary + funding impulse)",
             "全球流动性传导状态（货币+融资脉冲）", "engine.global_liquidity_transmission",
             "Macro/Data Producer W-LIQ.1", glt_asof,
             "site/liquiditydata/global_liquidity_transmission.json#state", glt_repr_fresh),
        _src("glt_quality", "GLT quality & coverage disclosure", "GLT质量与覆盖率披露",
             "engine.global_liquidity_transmission", "Macro/Data Producer W-LIQ.1", glt_asof,
             "site/liquiditydata/global_liquidity_transmission.json#quality", glt_repr_fresh),
        _src("glt_component_receipts", "GLT per-component freshness receipts", "GLT分项新鲜度回执",
             "engine.global_liquidity_transmission", "Macro/Data Producer W-LIQ.1", glt_asof,
             "site/liquiditydata/global_liquidity_transmission.json#freshness", glt_repr_fresh),
        _src("glt_state_history", "GLT state-history metadata", "GLT状态历史元数据",
             "engine.global_liquidity_transmission", "Macro/Data Producer W-LIQ.1",
             hist.get("last_asof"), "data/global_liquidity_transmission/state_history_meta.json",
             "HISTORICAL_AS_KNOWN" if hist else "NOT_COVERED"),
        _src("cb_balance_sheets", "Central-bank balance sheets (WALCL/ECBASSETSW/JPNASSETS)",
             "央行资产负债表（WALCL/ECBASSETSW/JPNASSETS）", "engine.cb_desk", "FRED",
             cbd_asof, "data/intl_risk/latest.json#cb_desk", fed_fresh),
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
            delta = _round(cur - prev, 6)
        deltas.append({"metric_id": mid, "prior_value": prev, "current_value": cur,
                       "delta": delta, "note": "same method version; numeric comparison permitted"})
    return {"comparability": "COMPARABLE", "prior_generation_id": prior_gen,
            "prior_effective_date": prior_eff, "prior_method_version": prior_method,
            "deltas": deltas, "status": "PRESENT", "null_reason": None}


def _corrections(current_metrics_by_id: dict, effective_date, prior_snapshot: Mapping | None) -> dict:
    """Scoped supersession detection over the tracked metric subset (mirrors
    the monetary_policy/R1A pattern; see liquidity_regime._corrections for the
    full caveat about this being a scoped subset, not a persisted vintage
    ledger)."""
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
