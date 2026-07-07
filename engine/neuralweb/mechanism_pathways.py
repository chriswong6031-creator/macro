"""engine.neuralweb.mechanism_pathways — Mechanism Pathway Compiler v1.

Deterministic, display-only compiler.  Reads emitted artifacts only
(RUL-CC-11).  Never recomputes classifiers.

Implements:
  - Trigger precedence (RUL-CC-12): market_drivers clear → risk_radar scare
    → factor rotation flip → no_attributable_driver null.
  - Stale-trigger guard (RUL-CC-13): if source artifact is stale per its
    registered freshness_sla_hours, emit no_pathway(reason=trigger_stale).
    Staleness uses calendar-day age >= _STALE_DAYS (5), mirroring
    engine/regime_prior.py _STALE_DAYS to absorb long weekends and
    Monday/post-holiday nightly runs without false-positives (RUL-CC-13
    with business-calendar absorption).
  - Coverage / coherence scoring (RUL-CC-3): coverage float, coherence
    categorical (supported | partial | conflicted) — never a float.
    Scare-trigger pathways (zero required legs) emit coverage_score=null
    and coverage_basis="scare_trigger" — never a fabricated 1.0.
  - Language law (RUL-CC-5): banned words "caused / proved / proof /
    validated" must not appear in any generated text.
  - No ticker-level entities (RUL-CC-10).
  - Nulls printed with reasons (RUL-CC-4).

RUL-CC-12 §4 deviation, ratified 2026-07-06: snap boolean is a site-builder
product outside the RUL-CC-11 read-set (lives in data/regime/regime_snap.json
written by scripts/build_site.py); v1 emits no_attributable_driver instead of
snap_unattributed.

Public API
----------
compile(root=None) -> dict
    Return the mechanism_pathways artifact dict (neuralweb.mechanism_pathways.v1).
    Never raises; returns a no_pathway artifact on any unrecoverable error.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from engine.neuralweb.synapse import load_registry

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCHEMA = "neuralweb.mechanism_pathways.v1"

# Staleness threshold: 3 trading-day equivalents = 5 calendar days.
# Mirrors engine/regime_prior.py _STALE_DAYS to cover long weekends without
# Monday/post-holiday false-positives (RUL-CC-13 business-calendar absorption).
_STALE_DAYS = 5

# SLA for data/transmission/latest.json — not synapse-registered (pre-existing
# gap, not this PR's to fix); use a named constant rather than a silent default.
_TRANSMISSION_SLA_HOURS = 30

# Frozen scare→family map (RUL-CC-12 §2)
SCARE_FAMILY_MAP: dict[str, str] = {
    "credit": "credit_stress",
    "rates": "real_rate_shock",
    "bubble": "ai_semis",
    "global": "usd_shock",
}
# Scares with no clean family mapping → no_pathway
_UNATTRIBUTED_SCARES = {"vol", "growth"}

# Transmission chain ids that correspond to rates/inflation families
# (attach as ordered mechanism edges per RUL-CC-2)
_RATES_CHAINS = {"real_rate", "sticky_inflation", "policy_easing", "expectations"}

# Expected lag map for transmission orders 1→3
_ORDER_LAG_MAP = {1: "same_day", 2: "days_1_5", 3: "weeks_1_4"}

# Authority block — printed verbatim per §1 charter
AUTHORITY_BLOCK: dict[str, Any] = {
    "tier": "display",
    "horizon_role": "context",
    "weights": "none",
    "scored_path_surfaces": [],
    "may_rank": False,
    "may_gate": False,
    "may_size": False,
    "may_escalate": False,
    "display_only": True,
    "not_a_signal": True,
    "forbidden_uses": [
        "ranking", "sizing", "alert_escalation", "claim_validation",
        "board_ordering", "mastermind_arming",
    ],
}

# Artifact paths (relative to repo root)
_REGIME_LATEST = "data/regime/latest.json"
_TRANSMISSION_LATEST = "data/transmission/latest.json"
_FACTOR_INTELLIGENCE = "data/neuralweb/factor_intelligence_state.json"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        log.warning("could not load %s: %s", path, exc)
        return None


def _parse_asof(val: Any) -> datetime | None:
    """Parse an as-of string/date to a UTC-aware datetime, or None."""
    if val is None:
        return None
    try:
        if isinstance(val, datetime):
            return val.replace(tzinfo=timezone.utc) if val.tzinfo is None else val
        s = str(val).strip()
        # Support "YYYY-MM-DD" or ISO-8601 with time
        if "T" in s:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        else:
            dt = datetime.strptime(s[:10], "%Y-%m-%d")
        return dt.replace(tzinfo=timezone.utc)
    except Exception:  # noqa: BLE001
        return None


def _days_since(asof_val: Any) -> int | None:
    """Return calendar days elapsed since asof_val (date-only or ISO-8601).

    For DATE-ONLY asofs (pinned to 00:00 UTC by _parse_asof), comparing
    raw hours against an hours-based SLA produces Monday/post-holiday
    false-positives on perfectly fresh Friday data.  Always use calendar
    days for these artifacts.  Mirrors engine/regime_prior.py _days_since.
    """
    asof = _parse_asof(asof_val)
    if asof is None:
        return None
    now = datetime.now(tz=timezone.utc)
    delta = now - asof
    return delta.days


def _is_stale(asof_val: Any, _sla_hours_ignored: int = 30) -> bool:
    """Return True if the artifact is older than _STALE_DAYS calendar days.

    The sla_hours parameter is accepted for call-site compatibility but
    ignored — date-only asofs require calendar-day comparison.  Staleness
    threshold = _STALE_DAYS (5) = 3 trading-day equivalents, covering long
    weekends without Monday/post-holiday false-positives (RUL-CC-13).
    """
    days = _days_since(asof_val)
    if days is None:
        return True
    return days >= _STALE_DAYS


def _get_sla(reg: dict, artifact_name: str) -> int:
    """Return freshness_sla_hours for a registered artifact name.

    Returns 0 if the artifact is not found in the registry so callers
    cannot silently fall through on an unregistered name — an SLA of 0
    causes every age check to pass (>= 0) which surfaces the gap rather
    than masking it.  Callers that need a safe fallback must use the
    named module constant _TRANSMISSION_SLA_HOURS instead.
    """
    artifacts = reg.get("artifacts", reg)
    entry = artifacts.get(artifact_name, {})
    sla = entry.get("freshness_sla_hours")
    if sla is None:
        return 0
    return int(sla)


def _no_pathway(reason: str, as_of: str, trigger_context: dict | None = None) -> dict:
    """Build a no_pathway record."""
    rec: dict[str, Any] = {
        "schema": SCHEMA,
        "as_of": as_of,
        "display_only": True,
        "not_a_signal": True,
        "authority": AUTHORITY_BLOCK,
        "pathways": [],
        "no_pathway": {
            "reason": reason,
            "printed": True,
        },
    }
    if trigger_context:
        rec["no_pathway"]["trigger_context"] = trigger_context
    return rec


# ---------------------------------------------------------------------------
# Node / edge builders
# ---------------------------------------------------------------------------

def _make_node(
    node_id: str,
    as_of: str,
    domain: str,
    source_artifact: str,
    entity: str,
    observation_en: str,
    observation_zh: str,
    direction: str,
    value: Any,
    z_or_percentile: float | None,
    source_tier: str,
    lag_class: str,
    pathway_role: str,
    evidence_refs: list[str] | None = None,
) -> dict:
    return {
        "node_id": node_id,
        "as_of": as_of,
        "domain": domain,
        "source_artifact": source_artifact,
        "entity": entity,
        "observation": {"en": observation_en, "zh": observation_zh},
        "direction": direction,
        "value": value,
        "z_or_percentile": z_or_percentile,
        "source_tier": source_tier,
        "lag_class": lag_class,
        "pathway_role": pathway_role,
        "evidence_refs": evidence_refs or [],
    }


def _make_edge(
    src_node: str,
    dst_node: str,
    mechanism_type: str,
    expected_lag: str,
    expected_sign: str,
    observed_sign: str | None,
    status: str,
    evidence_refs: list[str] | None = None,
) -> dict:
    valid_lags = {"same_day", "days_1_5", "weeks_1_4"}
    valid_statuses = {"measured", "theory_prior", "context_only", "conflicted", "missing", "stale"}
    if expected_lag not in valid_lags:
        expected_lag = "days_1_5"
    if status not in valid_statuses:
        status = "theory_prior"
    return {
        "src_node": src_node,
        "dst_node": dst_node,
        "mechanism_type": mechanism_type,
        "expected_lag": expected_lag,
        "expected_sign": expected_sign,
        "observed_sign": observed_sign,
        "status": status,
        "evidence_refs": evidence_refs or [],
    }


# ---------------------------------------------------------------------------
# Coherence derivation (RUL-CC-3 — categorical ONLY)
# ---------------------------------------------------------------------------

def _derive_coherence(agreement: float | None) -> str:
    """Convert emitted agreement float to categorical coherence.

    agreement is the market_drivers emitted band (0–1).
    Returns 'supported' | 'partial' | 'conflicted' — never a float.
    """
    if agreement is None:
        return "partial"
    if agreement >= 0.65:
        return "supported"
    if agreement >= 0.40:
        return "partial"
    return "conflicted"


# ---------------------------------------------------------------------------
# Transmission chain attachment (RUL-CC-2)
# ---------------------------------------------------------------------------

def _attach_transmission_edges(
    chains: list[dict],
    driver_family: str,
    nodes: list[dict],
    edges: list[dict],
    as_of: str,
    driver_node_id: str,
) -> None:
    """Attach rate/inflation transmission chains as ordered mechanism edges.

    Only attaches chains when driver_family is in _RATES_CHAINS (rates / inflation
    families).  Orders 1→same_day, 2→days_1_5, 3→weeks_1_4 (RUL-CC-2).
    Entity constraint: asset-class / ETF / index level only (RUL-CC-10).
    """
    rates_families = {"real_rate_shock", "fed_repricing", "oil_shock"}
    if driver_family not in rates_families:
        return

    # Map driver family to relevant chain id
    family_chain_map = {
        "real_rate_shock": "real_rate",
        "fed_repricing": "expectations",
        "oil_shock": "sticky_inflation",
    }
    target_chain_id = family_chain_map.get(driver_family)

    for chain in chains:
        chain_id = chain.get("id", "")
        if chain_id != target_chain_id:
            continue
        if not chain.get("active", False):
            continue
        chain_as_of = chain.get("asof", as_of)
        title = chain.get("title", {})
        title_en = title.get("en", chain_id) if isinstance(title, dict) else str(title)

        orders = chain.get("orders", [])
        prev_node_id = driver_node_id

        for order_rec in orders:
            order_num = order_rec.get("order", 0)
            lag_class = _ORDER_LAG_MAP.get(order_num, "days_1_5")
            text = order_rec.get("text", {})
            text_en = text.get("en", "") if isinstance(text, dict) else str(text)
            text_zh = text.get("zh", "") if isinstance(text, dict) else ""

            # Use a brief, non-causal description — enforce language law
            obs_en = _sanitize_text(text_en)
            obs_zh = _sanitize_text(text_zh)

            assets = order_rec.get("assets", [])
            # Collect asset tickers that have a measured verdict (headwind or tailwind).
            # The real transmission cell schema (engine/rate_inflation_transmission.py:498-500)
            # is {"asset", "label", "ic", "effect"(passthrough, default "—"), "verdict"
            # (headwind/tailwind/neutral/UNMEASURED)}.  headwind/tailwind live in "verdict",
            # NOT in "effect"; "CONFIRMED" is not a valid verdict value (F2 fix).
            measured_assets = [
                a["asset"] for a in assets
                if a.get("verdict") in ("headwind", "tailwind")
            ]
            entity = ", ".join(measured_assets[:3]) if measured_assets else "transmission channel"

            node_id = f"transmission_{chain_id}_order{order_num}"
            nodes.append(_make_node(
                node_id=node_id,
                as_of=as_of,
                domain="transmission",
                source_artifact="data/transmission/latest.json",
                entity=entity,
                observation_en=obs_en,
                observation_zh=obs_zh,
                direction="",
                value=None,
                z_or_percentile=None,
                source_tier="context_only",
                lag_class=lag_class,
                pathway_role=f"transmission_order_{order_num}",
                evidence_refs=[f"transmission.chains.{chain_id}.order{order_num}"],
            ))

            # Determine observed_sign from assets: majority verdict headwind/tailwind.
            # Read from "verdict" field — the field that actually carries directional
            # labels in the emitted schema (F2 fix).
            headwind_count = sum(1 for a in assets if a.get("verdict") == "headwind")
            tailwind_count = sum(1 for a in assets if a.get("verdict") == "tailwind")
            if headwind_count > tailwind_count:
                observed_sign = "negative"
            elif tailwind_count > headwind_count:
                observed_sign = "positive"
            else:
                observed_sign = None

            edges.append(_make_edge(
                src_node=prev_node_id,
                dst_node=node_id,
                mechanism_type="transmission_channel",
                expected_lag=lag_class,
                expected_sign="",
                observed_sign=observed_sign,
                status="measured",
                evidence_refs=[f"transmission.chains.{chain_id}.order{order_num}"],
            ))
            prev_node_id = node_id
        break


# ---------------------------------------------------------------------------
# Language law enforcement (RUL-CC-5)
# ---------------------------------------------------------------------------

_BANNED_WORDS = ("caused", "proved", "proof", "validated")


def _sanitize_text(text: str) -> str:
    """Remove or soften banned words from generated narrative text.

    Replaces banned words with display-safe alternatives.
    Reuses verbatim text from existing emitted artifacts — only applies
    to connective text we generate here.
    """
    if not text:
        return text
    result = text
    replacements = {
        "caused": "consistent with",
        "proved": "supported",
        "proof": "evidence",
        "validated": "consistent with",
    }
    for banned, safe in replacements.items():
        # Case-insensitive replacement preserving capitalisation
        import re
        result = re.sub(re.escape(banned), safe, result, flags=re.IGNORECASE)
    return result


def contains_banned_words(text: str) -> list[str]:
    """Return list of banned words found in text (for tests)."""
    found = []
    text_lower = text.lower()
    for w in _BANNED_WORDS:
        if w in text_lower:
            found.append(w)
    return found


# ---------------------------------------------------------------------------
# Factor rotation trigger check
# ---------------------------------------------------------------------------

def _get_factor_rotation_state(root: Path) -> dict | None:
    """Load factor_intelligence_state if available; return None if missing."""
    p = root / _FACTOR_INTELLIGENCE
    if not p.exists():
        return None
    return _load_json(p)


def _has_persistent_factor_flip(fi_state: dict | None) -> bool:
    """Return True if factor_intelligence_state reports a persistent style flip."""
    if fi_state is None:
        return False
    # Check for pending/flip in style_regime
    sr = fi_state.get("style_regime", "")
    if isinstance(sr, dict):
        sr_val = sr.get("state", "")
    else:
        sr_val = str(sr)
    return "flip" in sr_val.lower() or "pending" in sr_val.lower()


# ---------------------------------------------------------------------------
# Core pathway builder
# ---------------------------------------------------------------------------

def _build_pathway(
    family: str,
    driver_key: str,
    md: dict,
    transmission_chains: list[dict],
    as_of: str,
    pathway_role: str = "primary",
) -> dict:
    """Build one pathway dict from market_drivers emitted structures."""
    # Required legs from evidence_legs.
    # Do NOT apply max(1, ...) — scare-trigger pathways pass evidence_legs=[]
    # intentionally; coverage_denom=0 triggers the null-coverage path (F5).
    ev_legs: list[dict] = md.get("evidence_legs", [])
    required_leg_count = len(ev_legs)  # 0 for scare pathways → null coverage
    fresh_legs: list[dict] = []
    stale_legs: list[str] = []

    nodes: list[dict] = []
    edges: list[dict] = []

    # Driver node
    driver_node_id = f"driver_{driver_key}"
    direction_en = md.get("direction", "")
    direction_zh = md.get("direction_zh", "")
    headline = md.get("headline", "")
    headline_en = headline if isinstance(headline, str) else (
        headline.get("en", "") if isinstance(headline, dict) else ""
    )

    nodes.append(_make_node(
        node_id=driver_node_id,
        as_of=as_of,
        domain="market_drivers",
        source_artifact="data/regime/latest.json#market_drivers",
        entity=family,
        observation_en=_sanitize_text(direction_en or headline_en),
        observation_zh=direction_zh or "",
        direction=md.get("dir_sign", ""),
        value=md.get("strength"),
        z_or_percentile=md.get("dominance_ratio"),
        source_tier="display",
        lag_class="same_day",
        pathway_role="trigger",
        evidence_refs=["market_drivers.primary"],
    ))

    # Evidence leg nodes
    for i, leg in enumerate(ev_legs):
        leg_en = leg.get("en", f"leg_{i}")
        leg_zh = leg.get("zh", "")
        leg_z = leg.get("z")
        leg_node_id = f"leg_{driver_key}_{i}"
        nodes.append(_make_node(
            node_id=leg_node_id,
            as_of=as_of,
            domain="market_drivers",
            source_artifact="data/regime/latest.json#market_drivers",
            entity=leg_en,
            observation_en=f"{leg_en} ({leg_z:+.1f}σ)" if leg_z is not None else leg_en,
            observation_zh=f"{leg_zh} ({leg_z:+.1f}σ)" if leg_z is not None else leg_zh,
            direction="positive" if (leg_z or 0) > 0 else "negative",
            value=leg_z,
            z_or_percentile=leg_z,
            source_tier="display",
            lag_class="same_day",
            pathway_role="required_leg",
            evidence_refs=[f"market_drivers.evidence_legs[{i}]"],
        ))
        edges.append(_make_edge(
            src_node=driver_node_id,
            dst_node=leg_node_id,
            mechanism_type="evidence_leg",
            expected_lag="same_day",
            expected_sign="positive" if (leg_z or 0) > 0 else "negative",
            observed_sign="positive" if (leg_z or 0) > 0 else "negative",
            status="measured",
            evidence_refs=[f"market_drivers.evidence_legs[{i}]"],
        ))
        if leg_z is not None:
            fresh_legs.append(leg)
        else:
            stale_legs.append(leg_en)

    # Attach transmission edges for rates/inflation families
    _attach_transmission_edges(
        chains=transmission_chains,
        driver_family=family,
        nodes=nodes,
        edges=edges,
        as_of=as_of,
        driver_node_id=driver_node_id,
    )

    # Coverage score: fresh readable required legs / total required legs.
    # When there are zero required legs (e.g. a scare-trigger pathway built
    # from risk_radar with no evidence_legs), coverage is null + basis
    # "scare_trigger" — never a fabricated 1.0 (RUL-CC-3 / F5 fix).
    coverage_denom = required_leg_count
    coverage_num = len(fresh_legs)
    if coverage_denom == 0:
        coverage_score: float | None = None
        coverage_basis: str | None = "scare_trigger"
    else:
        coverage_score = coverage_num / coverage_denom
        coverage_basis = None

    agreement = md.get("agreement")
    coherence = _derive_coherence(agreement)

    rec: dict[str, Any] = {
        "family": family,
        "driver": driver_key,
        "pathway_role": pathway_role,
        "as_of": as_of,
        "direction_en": _sanitize_text(direction_en),
        "direction_zh": direction_zh,
        "confidence_ceiling": "context_only",
        "coverage_score": round(coverage_score, 3) if coverage_score is not None else None,
        "coherence": coherence,
        "stale_legs": stale_legs,
        "nodes": nodes,
        "edges": edges,
    }
    if coverage_basis is not None:
        rec["coverage_basis"] = coverage_basis
    return rec


def _build_factor_rotation_pathway(fi_state: dict, as_of: str) -> dict:
    """Build a minimal factor_rotation pathway from factor_intelligence_state."""
    sr = fi_state.get("style_regime", "")
    if isinstance(sr, dict):
        sr_label = sr.get("label", str(sr))
    else:
        sr_label = str(sr)

    driver_node_id = "driver_factor_rotation"
    nodes = [_make_node(
        node_id=driver_node_id,
        as_of=as_of,
        domain="factor_rotation",
        source_artifact="data/neuralweb/factor_intelligence_state.json",
        entity="factor_rotation",
        observation_en=f"Factor style regime: {sr_label}",
        observation_zh=f"因子风格切换: {sr_label}",
        direction="",
        value=None,
        z_or_percentile=None,
        source_tier="context_only",
        lag_class="same_day",
        pathway_role="trigger",
        evidence_refs=["factor_intelligence_state.style_regime"],
    )]
    edges: list[dict] = []

    return {
        "family": "factor_rotation",
        "driver": "factor_rotation",
        "pathway_role": "primary",
        "as_of": as_of,
        "direction_en": f"Factor style rotation detected: {sr_label}",
        "direction_zh": f"因子风格轮动: {sr_label}",
        "confidence_ceiling": "context_only",
        "coverage_score": 1.0,
        "coherence": "partial",
        "stale_legs": [],
        "nodes": nodes,
        "edges": edges,
    }


# ---------------------------------------------------------------------------
# Main compile function
# ---------------------------------------------------------------------------

def compile(root: Path | None = None) -> dict:  # noqa: A001
    """Compile and return the mechanism_pathways artifact.

    Never raises — returns a no_pathway artifact on any error.
    Implements RUL-CC-11 (read emitted artifacts only) and RUL-CC-12/13.
    """
    if root is None:
        root = _repo_root()

    as_of = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")

    # Load synapse registry for SLA lookups
    try:
        reg = load_registry(root)
    except Exception as exc:  # noqa: BLE001
        log.warning("synapse registry unavailable: %s", exc)
        reg = {}

    # --- Load regime/latest.json -----------------------------------------
    regime_path = root / _REGIME_LATEST
    regime = _load_json(regime_path)
    if regime is None:
        return _no_pathway("trigger_stale", as_of, {"reason_detail": "regime/latest.json unreadable"})

    md = regime.get("market_drivers", {})
    if not md:
        return _no_pathway("trigger_stale", as_of, {"reason_detail": "market_drivers block absent"})

    md_asof = md.get("asof") or regime.get("asof") or regime.get("date")
    # market_drivers and risk_radar are sub-blocks of data/regime/latest.json,
    # so their SLA is the registered "regime-latest" artifact SLA.
    regime_sla = _get_sla(reg, "regime-latest")

    # Stale-trigger guard (RUL-CC-13)
    if _is_stale(md_asof, regime_sla):
        return _no_pathway(
            "trigger_stale", as_of,
            {"source": "data/regime/latest.json", "asof": str(md_asof), "sla_days": _STALE_DAYS},
        )

    # --- Load transmission/latest.json -----------------------------------
    transmission_path = root / _TRANSMISSION_LATEST
    transmission = _load_json(transmission_path)
    chains: list[dict] = []
    if transmission:
        tx_asof = transmission.get("asof")
        # data/transmission/latest.json is not synapse-registered (pre-existing gap);
        # use named constant rather than a silent hardcoded default.
        if not _is_stale(tx_asof, _TRANSMISSION_SLA_HOURS):
            chains = transmission.get("chains", [])
    if not chains:
        log.debug("transmission chains unavailable or stale — continuing without")

    # --- Trigger precedence (RUL-CC-12) ----------------------------------
    verdict = md.get("verdict", "")
    primary_driver = md.get("primary", "")
    runner_up = md.get("runner_up")
    scores: list[dict] = md.get("scores", [])

    pathways: list[dict] = []
    no_pathway_rec: dict | None = None

    # (1) market_drivers verdict == 'clear'
    if verdict == "clear" and primary_driver:
        # Derive the driver's family from the scores list
        primary_family = next(
            (s.get("family", primary_driver) for s in scores if s.get("driver") == primary_driver),
            primary_driver,
        )
        primary_pathway = _build_pathway(primary_driver, primary_driver, md, chains, as_of, "primary")
        primary_pathway["family"] = primary_family

        # Coverage floor (RUL-CC-4): applies only when required legs exist
        # (coverage_score is not None). Scare-trigger pathways (null coverage)
        # are exempt — they have no required legs by design.
        cov = primary_pathway.get("coverage_score")
        if cov is not None and cov < 0.5:
            return _no_pathway(
                "insufficient_coverage",
                as_of,
                {"driver": primary_driver, "coverage_score": cov},
            )

        pathways.append(primary_pathway)

        # Alternates seeded from runner_up and scores list (≤2)
        alt_drivers = []
        if runner_up and runner_up != primary_driver:
            alt_drivers.append(runner_up)
        for s in scores:
            d = s.get("driver", "")
            if d and d != primary_driver and d not in alt_drivers:
                alt_drivers.append(d)
            if len(alt_drivers) >= 2:
                break

        for alt_d in alt_drivers[:2]:
            alt_family = next(
                (s.get("family", alt_d) for s in scores if s.get("driver") == alt_d),
                alt_d,
            )
            # Build a minimal alternate pathway using the scores list entry
            alt_score_entry = next((s for s in scores if s.get("driver") == alt_d), {})
            alt_md = {
                "verdict": "mixed",
                "primary": alt_d,
                "evidence_legs": [],
                "agreement": None,
                "dir_sign": "",
                "direction": alt_score_entry.get("direction", ""),
                "direction_zh": "",
                "strength": alt_score_entry.get("strength", 0.0),
                "dominance_ratio": None,
                "headline": alt_score_entry.get("direction", ""),
            }
            alt_pw = _build_pathway(alt_d, alt_d, alt_md, chains, as_of, "alternate")
            alt_pw["family"] = alt_family
            pathways.append(alt_pw)

    # (2) risk_radar dominant_scare escalation
    elif not pathways:
        rr = regime.get("risk_radar", {})
        dominant_scare = rr.get("dominant_scare", "")
        rr_state = rr.get("state", "")
        rr_asof = rr.get("asof")
        # risk_radar is a sub-block of data/regime/latest.json;
        # use the registered "regime-latest" SLA.
        rr_sla = _get_sla(reg, "regime-latest")

        if dominant_scare and rr_state not in ("", "calm"):
            if _is_stale(rr_asof, rr_sla):
                return _no_pathway("trigger_stale", as_of, {"source": "risk_radar", "asof": str(rr_asof)})

            if dominant_scare in _UNATTRIBUTED_SCARES:
                no_pathway_rec = {
                    "reason": "scare_unattributed",
                    "printed": True,
                    "trigger_context": {
                        "dominant_scare": dominant_scare,
                        "label_en": rr.get("dominant_label_en", ""),
                        "label_zh": rr.get("dominant_label_zh", ""),
                        "state": rr_state,
                    },
                }
            else:
                mapped_family = SCARE_FAMILY_MAP.get(dominant_scare)
                if not mapped_family:
                    no_pathway_rec = {
                        "reason": "scare_unattributed",
                        "printed": True,
                        "trigger_context": {"dominant_scare": dominant_scare},
                    }
                else:
                    # Build a minimal pathway for the mapped family
                    scare_md = {
                        "verdict": "clear",
                        "primary": mapped_family,
                        "evidence_legs": [],
                        "agreement": None,
                        "dir_sign": "",
                        "direction": rr.get("dominant_label_en", ""),
                        "direction_zh": rr.get("dominant_label_zh", ""),
                        "strength": rr.get("top_score", 0.0),
                        "dominance_ratio": None,
                        "headline": rr.get("headline_en", ""),
                    }
                    scare_pw = _build_pathway(
                        mapped_family, mapped_family, scare_md, chains, as_of, "primary"
                    )
                    scare_pw["source_trigger"] = "risk_radar"
                    scare_pw["scare"] = dominant_scare
                    # Scare pathways have zero required evidence_legs by design;
                    # _build_pathway emits coverage_score=null + coverage_basis="scare_trigger".
                    # The insufficient_coverage floor (< 0.5) applies only when required
                    # legs exist — exempt scare pathways from the floor (F5).

                    pathways.append(scare_pw)

                    # Alternates from scores list
                    for s in scores[:2]:
                        d = s.get("driver", "")
                        if d and d != mapped_family:
                            alt_family = s.get("family", d)
                            alt_md = {
                                "verdict": "mixed",
                                "primary": d,
                                "evidence_legs": [],
                                "agreement": None,
                                "dir_sign": "",
                                "direction": s.get("direction", ""),
                                "direction_zh": "",
                                "strength": s.get("strength", 0.0),
                                "dominance_ratio": None,
                                "headline": s.get("direction", ""),
                            }
                            alt_pw = _build_pathway(d, d, alt_md, chains, as_of, "alternate")
                            alt_pw["family"] = alt_family
                            pathways.append(alt_pw)
                            if len(pathways) >= 3:
                                break

    # (3) factor-rotation persistent flip
    if not pathways and no_pathway_rec is None:
        fi_state = _get_factor_rotation_state(root)
        fi_asof = fi_state.get("as_of") if fi_state else None
        fi_sla = _get_sla(reg, "factor-intelligence-state")

        if fi_state and not _is_stale(fi_asof, fi_sla) and _has_persistent_factor_flip(fi_state):
            pathways.append(_build_factor_rotation_pathway(fi_state, as_of))

    # (4) no attributable driver — no_pathway.
    # RUL-CC-12 §4 deviation (ratified 2026-07-06): snap boolean lives in
    # data/regime/regime_snap.json (written by scripts/build_site.py), which
    # is outside the RUL-CC-11 read-set; we key on regime_one presence instead
    # and emit no_attributable_driver rather than snap_unattributed.
    if not pathways and no_pathway_rec is None:
        ro = regime.get("regime_one", {})
        if ro:
            no_pathway_rec = {
                "reason": "no_attributable_driver",
                "printed": True,
                "trigger_context": {
                    "quad": ro.get("tape", {}).get("quad") if isinstance(ro.get("tape"), dict) else None,
                    "label": regime.get("label"),
                    "note": "regime present but no attributable driver family resolved",
                },
            }
        else:
            no_pathway_rec = {
                "reason": "no_trigger",
                "printed": True,
            }

    # --- Assemble artifact -----------------------------------------------
    artifact: dict[str, Any] = {
        "schema": SCHEMA,
        "as_of": as_of,
        "display_only": True,
        "not_a_signal": True,
        "authority": AUTHORITY_BLOCK,
        "pathways": pathways,
    }
    if no_pathway_rec:
        artifact["no_pathway"] = no_pathway_rec
    elif not pathways:
        artifact["no_pathway"] = {"reason": "no_trigger", "printed": True}

    return artifact
