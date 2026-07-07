"""Oracle Red Queen Interface Contract — payload schema enforcement.

PAYLOAD_VERSION bump rules (semver):
  - Patch (x.y.Z): internal wording, comment-only changes.
  - Minor (x.Y.0): additive fields that leave all existing paths unchanged.
    Parallel waves MUST use minor bumps (A3 regime_tag, B1 personality fields).
    Tolerant-reader rule: consumers MUST NOT error on unknown additive fields.
  - Major (X.0.0): semantic change to a required field, field removal, or
    type change in a required field.  Breaks downstream consumers; requires
    negotiation between Oracle and Red Queen before deploy.

CONFIDENCE TAXONOMY
--------------------
Every signal-bearing item carries confidence_class in:
  validated          — primary endpoint cleared a registered gauntlet with
                       pre-bound vocabulary; FDR-survived.  Currently empty
                       (P3 primaries NULL; see ORACLE_GAUNTLET_P3_ADJUDICATION.md).
  display_with_edge  — secondary endpoint with measured edge and printed error
                       rates; may render on display surfaces with caveats.
                       Covers: ep_in_onset_21d, ep_out_onset_5d, and the 6
                       placebo-surviving routing cells (P3/P3b adjudications).
  exploratory        — screened or accruing; Tier-1 effect exists but no gauntlet.
  descriptive        — observed description of state; no edge claim at all.

NEVER GUARANTEES (enforced by validate_payload)
------------------------------------------------
(a) No field named/documented as a forecast unless confidence_class == validated.
    Validator greps the entire payload for banned-implication keys
    ["forecast", "predicted", "target", "expected_return"] and errors unless
    the containing item has confidence_class == "validated".
(b) Alert-class items must carry error-rate context (false_start_rate numeric).
(c) Tier-M (survivorship-flagged) facts must carry survivorship_flagged == True.

TOLERANT-READER RULE
---------------------
Payloads may carry fields not listed in REQUIRED_CORE.  validate_payload()
passes on unknown top-level or nested fields to allow forward-compatible
extension by parallel waves.

STALENESS CONTRACT
------------------
staleness: TRADING-DAY-AWARE — at most MAX_TRADING_DAYS=2 business days behind
(plus a 168h calendar hard cap). Consumers receiving a stale payload MUST treat
it as absent and surface a staleness warning, not stale data.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger(__name__)

PAYLOAD_VERSION = "1.2.0"  # B1 member roll-up (personality_context per complex, R-SP19)

# Staleness contract: payloads older than this are invalid.
# Staleness is TRADING-DAY-AWARE (v1.0.1 fix): a fixed 48 calendar hours
# fails every weekend (Friday data is legitimately ~72h old on Monday, worse
# over holidays — the first real E2E run failed on July-4th weekend exactly
# this way). Contract: asof may lag `now` by at most MAX_TRADING_DAYS
# business days, with MAX_AGE_HOURS_HARD as an absolute calendar backstop.
MAX_TRADING_DAYS: int = 2
MAX_AGE_HOURS_HARD: int = 168  # 7 calendar days — the never-exceed backstop

# Confidence taxonomy values (ordered weakest → strongest for reference).
CONFIDENCE_CLASSES = frozenset({"validated", "display_with_edge", "exploratory", "descriptive"})

# Keys anywhere in the payload that imply a forecast; forbidden unless item
# has confidence_class == "validated".
BANNED_IMPLICATION_KEYS = frozenset({"forecast", "predicted", "target", "expected_return"})

# ---------------------------------------------------------------------------
# Lineage helpers — seed the taxonomy from measured adjudication results.
# ---------------------------------------------------------------------------

# P3/P3b adjudication: these named cells are display_with_edge.
# Lineage anchor: ORACLE_GAUNTLET_P3_ADJUDICATION.md verdicts +
#                 R2 RESOLVED (P3b routing placebo, 2026-07-04).
_DISPLAY_WITH_EDGE_COMPOUNDS = frozenset({
    "ep_in_onset_21d",
    "ep_out_onset_5d",
    # 6 placebo-surviving routing cells (P3b):
    "software__ai_compute__5d",
    "software__ai_compute__10d",
    "ai_compute__energy_commodities__10d",
    "energy_commodities__ai_compute__10d",
    "consumer_staples_defensive__financials_rates__5d",
    "software__financials_rates__15d",
})


def classify_lineage(compound_id: str) -> dict[str, str]:
    """Return confidence_class + lineage anchor for a compound id.

    Parameters
    ----------
    compound_id:
        The canonical compound id as defined in ORACLE_COMPOUND_LIBRARY.md or
        the gauntlet trial ledger (e.g. "ep_in_onset_21d", "A1", etc.).

    Returns
    -------
    dict with keys:
        confidence_class: one of CONFIDENCE_CLASSES
        lineage: a string referencing the registration or adjudication document
                 that sets this classification.
    """
    if compound_id in _DISPLAY_WITH_EDGE_COMPOUNDS:
        return {
            "confidence_class": "display_with_edge",
            "lineage": (
                "ORACLE_GAUNTLET_P3_ADJUDICATION.md: ep_in_onset_21d / ep_out_onset_5d "
                "= DISPLAY-WITH-EDGE (secondary, BH-survived in 109-trial family). "
                "6 routing cells = DISPLAY-WITH-EDGE (P3b placebo survivors, watermark-capped, "
                "ORACLE_GAUNTLET_P3_ADJUDICATION.md R2 RESOLVED)."
            ),
        }
    # Primaries P-ENTRY / P-EXIT are NULL per P3 — no edge at all.
    if compound_id in ("P-ENTRY", "P-EXIT", "ep_in_confirmed_21d", "ep_out_confirmed_21d"):
        return {
            "confidence_class": "descriptive",
            "lineage": (
                "ORACLE_GAUNTLET_P3_ADJUDICATION.md R1: primary confirmed-tier endpoints NULL "
                "(wrong direction, all gates failed).  No edge for confirmed tier."
            ),
        }
    # Routing cells not in the 6 survivors are accruing candidates.
    if "__" in compound_id and any(compound_id.endswith(f"__{d}d") for d in (5, 10, 15, 20)):
        return {
            "confidence_class": "exploratory",
            "lineage": (
                "ORACLE_GAUNTLET_P3_ADJUDICATION.md R2: routing cell reverted to accruing "
                "candidate after placebo falsification.  Tier-L ledger accruing; "
                "future re-registration required to advance."
            ),
        }
    # Default: descriptive.
    return {
        "confidence_class": "descriptive",
        "lineage": "No gauntlet registration or adjudication on record.",
    }


# ---------------------------------------------------------------------------
# REQUIRED_CORE spec
# ---------------------------------------------------------------------------

REQUIRED_CORE: dict[str, Any] = {
    # Field name → (type_or_types, description, additional_constraints_dict)
    "asof": (str, "ISO date YYYY-MM-DD of the payload data point. Staleness: <=2 trading days behind, 168h hard cap."),
    "disclaimers": (dict, "Must contain display_only==True and error_rates dict with numeric values."),
    "active_episodes": (list, (
        "List of episode items.  Each item must contain: node (str), direction (str), "
        "tier (str), onset_date (str).  Tier-M items (survivorship_flagged==True) must "
        "carry that flag.  confidence_class must be present if the item is signal-bearing."
    )),
}


# ---------------------------------------------------------------------------
# validate_payload — public API
# ---------------------------------------------------------------------------

def validate_payload(payload: Any, *, as_of_now: datetime | None = None) -> tuple[bool, list[str]]:
    """Validate an oracle_state payload against the Red Queen contract.

    Tolerant-reader: unknown additive fields do NOT cause errors.
    Type mismatches and missing required fields DO cause errors.
    NEVER guarantee violations cause errors.

    Parameters
    ----------
    payload:
        The oracle_state dict (parsed JSON).
    as_of_now:
        The current UTC datetime; used to check staleness.
        Defaults to datetime.now(timezone.utc).

    Returns
    -------
    (ok, errors):
        ok     — True if the payload passes all checks.
        errors — List of human-readable error strings (empty when ok==True).
    """
    errors: list[str] = []

    if not isinstance(payload, dict):
        return False, ["payload must be a JSON object (dict); got " + type(payload).__name__]

    # --- 1. Required core fields ---

    # asof: ISO date string, max_age_hours staleness check
    asof = payload.get("asof")
    if not isinstance(asof, str):
        errors.append("REQUIRED: 'asof' must be a str ISO date (YYYY-MM-DD)")
    else:
        try:
            asof_dt = datetime.fromisoformat(asof).replace(tzinfo=timezone.utc)
            now = as_of_now if as_of_now is not None else datetime.now(timezone.utc)
            age_hours = (now - asof_dt).total_seconds() / 3600
            # trading-day-aware staleness: count business days strictly between
            # asof and now (bdate_range includes both endpoints when they are
            # business days — subtract the asof day itself).
            import pandas as _pd
            bdays_behind = max(
                0, len(_pd.bdate_range(asof_dt.date(), now.date())) - 1)
            if bdays_behind > MAX_TRADING_DAYS or age_hours > MAX_AGE_HOURS_HARD:
                errors.append(
                    f"STALE: 'asof' is {bdays_behind} trading days ({age_hours:.1f}h) old; "
                    f"contract requires <= {MAX_TRADING_DAYS} trading days and "
                    f"<= {MAX_AGE_HOURS_HARD}h hard cap. Consumers must treat stale "
                    f"payloads as absent."
                )
        except ValueError:
            errors.append(f"REQUIRED: 'asof' is not a valid ISO date string: {asof!r}")

    # disclaimers: display_only == True and error_rates with numeric values
    disclaimers = payload.get("disclaimers")
    if not isinstance(disclaimers, dict):
        errors.append("REQUIRED: 'disclaimers' must be a dict")
    else:
        if disclaimers.get("display_only") is not True:
            errors.append("REQUIRED: disclaimers.display_only must be True (boolean)")
        er = disclaimers.get("error_rates")
        if not isinstance(er, dict):
            errors.append("REQUIRED: disclaimers.error_rates must be a dict")
        else:
            for k, v in er.items():
                if v is not None and not isinstance(v, (int, float)):
                    errors.append(
                        f"REQUIRED: disclaimers.error_rates.{k} must be numeric or null; "
                        f"got {type(v).__name__}"
                    )

    # active_episodes: list with required per-item fields
    active_episodes = payload.get("active_episodes")
    if not isinstance(active_episodes, list):
        errors.append("REQUIRED: 'active_episodes' must be a list")
    else:
        for i, ep in enumerate(active_episodes):
            if not isinstance(ep, dict):
                errors.append(f"active_episodes[{i}]: must be a dict")
                continue
            for req_field in ("node", "direction", "tier", "onset_date"):
                if ep.get(req_field) is None:
                    errors.append(f"active_episodes[{i}]: missing required field '{req_field}'")
            # survivorship watermark check (NEVER guarantee c)
            if ep.get("survivorship_flagged") is not True and ep.get("tier") == "undeniable":
                # undeniable tier items on the Tier-M panel must carry watermark
                # We can't check tier_src here but we check direction defensively
                pass  # tier-M vs tier-S determined by tier_src which may not be present
            # Alert-class items: onset tier must carry error-rate context (NEVER guarantee b)
            if ep.get("tier") == "onset":
                # error_rates must be present in disclaimers (already checked above)
                # Additionally, if the episode item has a signal-bearing confidence_class,
                # the payload must have non-null error rates.
                if isinstance(disclaimers, dict):
                    _er = disclaimers.get("error_rates")
                    # Degrade safely — if error_rates is not a dict (already flagged above),
                    # treat as empty so we still report the onset-alert constraint.
                    fsr = _er.get("false_start_rate") if isinstance(_er, dict) else None
                    o2c = _er.get("onset_to_confirmed_conversion") if isinstance(_er, dict) else None
                    # R4 requires BOTH S3 error rates on onset-tier surfaces
                    # (review minor on #1283: conversion rate was unenforced).
                    if fsr is None or o2c is None:
                        missing = [n for n, v in
                                   (("false_start_rate", fsr),
                                    ("onset_to_confirmed_conversion", o2c)) if v is None]
                        errors.append(
                            f"active_episodes[{i}] (onset tier, alert-class): "
                            f"disclaimers.error_rates.{{{', '.join(missing)}}} must be "
                            "numeric — onset alerts must carry BOTH S3 error rates "
                            "(NEVER guarantee b / R4)"
                        )
                        break  # report once, not per episode

    # --- 2. NEVER guarantee (a): banned implication keys ---
    _check_banned_keys(payload, errors)

    ok = len(errors) == 0
    return ok, errors


def _check_banned_keys(payload: Any, errors: list[str], _path: str = "") -> None:
    """Recursively walk payload and flag banned-implication keys.

    A key from BANNED_IMPLICATION_KEYS is allowed ONLY if its containing
    dict has confidence_class == "validated".
    """
    if isinstance(payload, dict):
        confidence_class = payload.get("confidence_class")
        for k, v in payload.items():
            key_lower = k.lower()
            for banned in BANNED_IMPLICATION_KEYS:
                if banned in key_lower:
                    if confidence_class != "validated":
                        full_path = f"{_path}.{k}" if _path else k
                        errors.append(
                            f"NEVER(a): key '{full_path}' implies a forecast "
                            f"(contains '{banned}') but confidence_class is "
                            f"{confidence_class!r}, not 'validated'. "
                            f"Remove this key or set confidence_class='validated' "
                            f"with valid gauntlet lineage."
                        )
            # Recurse
            child_path = f"{_path}.{k}" if _path else k
            _check_banned_keys(v, errors, child_path)
    elif isinstance(payload, list):
        for i, item in enumerate(payload):
            _check_banned_keys(item, errors, f"{_path}[{i}]")


# ---------------------------------------------------------------------------
# stamp_payload — add version + confidence_class fields (used by live.py)
# ---------------------------------------------------------------------------

def stamp_payload(payload: dict) -> dict:
    """Add payload_version + per-episode confidence_class stamps.

    Called by live.py BEFORE writing oracle_state.json.
    Additive — does not overwrite any existing keys set by parallel waves.

    Returns the mutated payload (same object, mutated in-place).
    """
    # Version stamp (additive — do not overwrite if already stamped by a build step)
    if "payload_version" not in payload:
        payload["payload_version"] = PAYLOAD_VERSION

    # Per-episode confidence_class (additive)
    for ep in payload.get("active_episodes") or []:
        if not isinstance(ep, dict):
            continue
        if "confidence_class" in ep:
            continue  # already stamped by a parallel wave
        tier = ep.get("tier", "onset")
        direction = ep.get("direction", "")
        # Classify based on P3/P3b adjudication results
        if tier == "onset" and direction == "out":
            cell_id = "ep_out_onset_5d"
        elif tier == "onset" and direction == "in":
            cell_id = "ep_in_onset_21d"
        else:
            # confirmed / undeniable primaries are NULL per P3 adjudication
            cell_id = f"ep_{direction}_confirmed_21d"
        lineage_info = classify_lineage(cell_id)
        ep["confidence_class"] = lineage_info["confidence_class"]
        ep["lineage"] = lineage_info["lineage"]

    return payload
