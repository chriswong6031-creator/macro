#!/usr/bin/env python3
"""Honest-N measurement primitives for the source-only S1F feasibility wave."""
from __future__ import annotations

from collections import Counter
from typing import Any, Iterable, Mapping

try:
    from scipy.stats import beta
except ImportError:  # fail closed rather than silently substituting an approximation
    beta = None


class MeasurementBlocked(RuntimeError):
    pass


PRIMARY_FAMILIES = (
    "PHYSICAL_MECHANICAL_INTERRUPTION",
    "EXTERNAL_HUMAN_INTERRUPTION",
    "CYBER_OR_IT_INTERRUPTION",
    "WEATHER_OR_PHYSICAL_DISASTER",
    "TEMPORARY_EXPECTATION_RESET",
)
SECTOR_PARTITIONS = (
    "NON_MINING_CORE",
    "EXTERNAL_VALIDATION_MINING",
    "SECTOR_PARTITION_UNRESOLVED",
)


def exact_binomial_95(successes: int, trials: int) -> dict[str, Any]:
    if not isinstance(successes, int) or not isinstance(trials, int) or trials < 0 or successes < 0 or successes > trials:
        raise MeasurementBlocked("invalid binomial inputs")
    if trials == 0:
        return {"status": "UNDEFINED_ZERO_DENOMINATOR", "value": None, "successes": successes, "trials": trials}
    if beta is None:
        raise MeasurementBlocked("SCIPY_EXACT_INTERVAL_UNAVAILABLE")
    alpha = 0.05
    lower = 0.0 if successes == 0 else float(beta.ppf(alpha / 2, successes, trials - successes + 1))
    upper = 1.0 if successes == trials else float(beta.ppf(1 - alpha / 2, successes + 1, trials - successes))
    # Fixed decimal strings keep receipts byte-stable across JSON encoders.
    fmt = lambda value: format(value, ".12f")
    return {"status": "OBSERVED", "successes": successes, "trials": trials, "proportion": fmt(successes / trials),
            "confidence": "0.950000000000", "method": "CLOPPER_PEARSON_EXACT_TWO_SIDED", "lower": fmt(lower), "upper": fmt(upper)}


def _admitted(row: Mapping[str, Any]) -> bool:
    return bool(row.get("audited_episode_origin")) and str(row.get("audit_verdict")) in {"ACCEPT", "REPAIR"} and not bool(row.get("rejected"))


def measure(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    items = [dict(row) for row in rows]
    if len(items) != 70:
        raise MeasurementBlocked("S1F measurement requires exactly 70 audited packets")
    identities = {(str(row.get("cik")), str(row.get("accession"))) for row in items}
    if len(identities) != 70:
        raise MeasurementBlocked("S1F measurement requires 70 distinct packet identities")
    for row in items:
        verdict = str(row.get("audit_verdict") or "")
        if verdict not in {"ACCEPT", "REPAIR", "REJECT"}:
            raise MeasurementBlocked("every S1F packet requires a final independent audit verdict")
        if row.get("unresolved_audit_disagreement") is True:
            raise MeasurementBlocked("S1F measurement cannot consume an unresolved audit disagreement")
        if bool(row.get("audited_episode_origin")) and not _admitted(row):
            raise MeasurementBlocked("a rejected/non-audited packet cannot be an episode origin")
        row["matched_document_role_class"] = _matched_role_class(row.get("reviewed_documents"))
    for stratum in sorted({str(row.get("stratum")) for row in items}):
        subset = [row for row in items if str(row.get("stratum")) == stratum]
        if len(subset) != 10 or sum(row.get("era") == "modern" for row in subset) != 7 or sum(row.get("form") == "8-K" for row in subset) != 7:
            raise MeasurementBlocked("fixed S1F 10/7/7 stratum margins violated")
    if sum(row.get("era") == "modern" for row in items) != 49 or sum(row.get("form") == "8-K" for row in items) != 49:
        raise MeasurementBlocked("fixed S1F 49/21 era/form margins violated")
    admitted = [row for row in items if _admitted(row)]
    episode_ids = [str(row.get("economic_episode_id") or "") for row in admitted]
    if any(not episode_id for episode_id in episode_ids) or len(set(episode_ids)) != len(episode_ids):
        raise MeasurementBlocked("each admitted episode requires one unique designated origin")
    hard_admitted = [row for row in items if row.get("shadow_disposition") == "HARD_REFUSAL" and _admitted(row)]
    by = lambda predicate: exact_binomial_95(sum(_admitted(row) for row in items if predicate(row)), sum(predicate(row) for row in items))
    retained = [row for row in items if row.get("shadow_disposition") == "RETAIN"]
    retained_origins = sum(_admitted(row) for row in retained)
    suppressed = {
        state: [
            {
                "packet_id": str(row.get("packet_id") or ""),
                "economic_episode_id": str(row.get("economic_episode_id") or ""),
                "cik": str(row.get("cik") or ""),
                "accession": str(row.get("accession") or ""),
                "triage_rule_ids": sorted(str(rule) for rule in row.get("triage_rule_ids") or []),
            }
            for row in items
            if row.get("shadow_disposition") == state and _admitted(row)
        ]
        for state in ("DEFER", "HARD_REFUSAL")
    }
    unsafe_rules: dict[str, list[str]] = {}
    for row in hard_admitted:
        rule_ids = [str(rule) for rule in row.get("triage_rule_ids") or []]
        if not rule_ids:
            raise MeasurementBlocked("hard-refused admitted origin lacks its frozen triage rule identity")
        identity = f"{row.get('cik')}:{row.get('accession')}"
        for rule_id in rule_ids:
            unsafe_rules.setdefault(rule_id, []).append(identity)

    sector_by_row: dict[int, str] = {}
    for index, row in enumerate(items):
        partition = str(row.get("canonical_sector_partition") or "SECTOR_PARTITION_UNRESOLVED")
        if partition not in SECTOR_PARTITIONS:
            raise MeasurementBlocked("noncanonical sector partition value")
        sector_by_row[index] = partition

    rate = {"overall_origin_yield": exact_binomial_95(len(admitted), 70),
            "modern_origin_yield": by(lambda row: row.get("era") == "modern"),
            "by_stratum": {stratum: by(lambda row, s=stratum: row.get("stratum") == s) for stratum in sorted({str(row.get("stratum")) for row in items})},
            "by_era": {era: by(lambda row, e=era: row.get("era") == e) for era in ("modern", "development")},
            "by_form": {form: by(lambda row, f=form: row.get("form") == f) for form in ("8-K", "6-K")},
            "by_document_role": {role: by(lambda row, r=role: row.get("matched_document_role_class") == r) for role in sorted({str(row.get("matched_document_role_class")) for row in items})},
            "by_sector_partition": {partition: by(lambda row, p=partition: str(row.get("canonical_sector_partition") or "SECTOR_PARTITION_UNRESOLVED") == p) for partition in SECTOR_PARTITIONS},
            "sector_partition_status": "SECTOR_PARTITION_UNRESOLVED" if "SECTOR_PARTITION_UNRESOLVED" in sector_by_row.values() else "COMPLETE",
            "p0_s2_sector_partition_blocker": "SECTOR_PARTITION_UNRESOLVED" in sector_by_row.values(),
            "retain_rate": exact_binomial_95(len(retained), 70),
            "retained_precision": exact_binomial_95(retained_origins, len(retained)),
            "suppressed_admitted_origins": suppressed,
            "hard_refusal_safety": "UNSAFE_FOR_PROMOTION" if hard_admitted else "NO_HARD_REFUSED_ADMITTED_ORIGIN",
            "unsafe_hard_refusal_rules": {rule: sorted(identities) for rule, identities in sorted(unsafe_rules.items())},
            "candidates_per_origin": {"status": "UNDEFINED_ZERO_DENOMINATOR", "value": None} if not admitted else {"status": "OBSERVED", "value": format(70 / len(admitted), ".12f")},
            "unique_reviewed_source_bytes_per_origin": _bytes_per_origin(items, len(admitted)),
            "dominant_false_positive_mechanisms": _dominant_false_positives(items),
            "family_zero_of_ten": {stratum: "SOURCE_FEASIBILITY_UNPROVEN" for stratum in PRIMARY_FAMILIES if sum(_admitted(row) for row in items if str(row.get("stratum")) == stratum) == 0},
            "source_feasibility": "SOURCE_PRECISION_NOT_PROVEN" if not any(_admitted(row) and row.get("era") == "modern" for row in items) else "OBSERVED"}
    overall = len(admitted) / 70
    retained_fraction = retained_origins / len(retained) if retained else None
    rate["enrichment"] = {"status": "UNDEFINED_ZERO_DENOMINATOR", "value": None} if not overall or retained_fraction is None else {"status": "OBSERVED", "value": format(retained_fraction / overall, ".12f")}
    return rate


def _bytes_per_origin(rows: list[dict[str, Any]], origins: int) -> dict[str, Any]:
    if not origins:
        return {"status": "UNDEFINED_ZERO_DENOMINATOR", "value": None}
    hashes: dict[str, int] = {}
    for row in rows:
        for doc in row.get("reviewed_documents") or []:
            if isinstance(doc, Mapping) and isinstance(doc.get("sha256"), str) and isinstance(doc.get("byte_length"), int):
                prior = hashes.get(str(doc["sha256"]))
                if prior is not None and prior != int(doc["byte_length"]):
                    raise MeasurementBlocked("one document SHA has conflicting byte lengths")
                hashes[str(doc["sha256"])] = int(doc["byte_length"])
    return {"status": "OBSERVED", "unique_bytes": sum(hashes.values()), "origins": origins, "value": format(sum(hashes.values()) / origins, ".12f")}


def _matched_role_class(documents: Any) -> str:
    if not isinstance(documents, list):
        return "UNRESOLVED"
    roles: set[str] = set()
    for document in documents:
        if not isinstance(document, Mapping) or document.get("exact_fts_matched") is not True:
            continue
        role = document.get("canonical_owner_role")
        if role not in {"primary", "archive"}:
            return "UNRESOLVED"
        roles.add(str(role))
    if roles == {"primary"}:
        return "PRIMARY_ONLY"
    if roles == {"archive"}:
        return "ARCHIVE_ONLY"
    if roles == {"primary", "archive"}:
        return "MIXED"
    return "UNRESOLVED"


ALLOWED_FALSE_POSITIVE_MECHANISMS = frozenset({
    "CERTIFICATION_ONLY", "AGREEMENT_COVENANT_DEFINITION_ONLY", "HYPOTHETICAL_RISK_ONLY",
    "ORDINARY_FINANCING_OR_TRANSACTION", "COMPLETED_PERIOD_RESULTS", "ORDINARY_EARNINGS",
    "RISK_FACTOR_EXHIBIT", "OTHER_AUDITED_FALSE_POSITIVE", "AUDITED_NO_EPISODE",
})


def _dominant_false_positives(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    non_origins = [row for row in rows if not _admitted(row)]
    missing = [row for row in non_origins if str(row.get("audit_verdict")) in {"ACCEPT", "REPAIR", "REJECT"} and row.get("audited_false_positive_mechanism") not in ALLOWED_FALSE_POSITIVE_MECHANISMS]
    if missing:
        raise MeasurementBlocked("audited non-origin lacks allowed audited_false_positive_mechanism")
    values = Counter(str(row.get("audited_false_positive_mechanism")) for row in non_origins)
    total = len(non_origins)
    return [{
        "mechanism": key,
        "count": value,
        "proportion_of_non_origins": format(value / total, ".12f") if total else None,
    } for key, value in sorted(values.items(), key=lambda item: (-item[1], item[0]))]
