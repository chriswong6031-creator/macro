#!/usr/bin/env python3
"""Price-blind Dislocation P0-A1 primitives.

Frozen lexicon, query-ledger serialization, access firewall, form/clock
normalization, deterministic selection keys, and span extraction. Network I/O
lives in dislocation_p0_a1_harvest.py. No price, volume, return, or outcome
field is legal here.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

# Frozen before querying (Turn-5 / PR #6062 capacity census).
# These phrases are candidate-retrieval hooks, never event-family evidence.
LEXICON: dict[str, list[str]] = {
    "PHYSICAL_MECHANICAL_INTERRUPTION": [
        "equipment failure",
        "mechanical failure",
        "unplanned outage",
        "temporary shutdown",
        "temporarily shut down",
        "temporarily suspended operations",
        "operations were suspended",
        "production interruption",
        "manufacturing interruption",
        "plant outage",
        "facility outage",
        "equipment malfunction",
        "power outage",
    ],
    "EXTERNAL_HUMAN_INTERRUPTION": [
        "labor strike",
        "work stoppage",
        "labor action",
        "union strike",
        "blockade",
        "community protest",
        "civil unrest",
        "picket line",
        "access restriction",
        "workforce walkout",
    ],
    "CYBER_OR_IT_INTERRUPTION": [
        "cybersecurity incident",
        "cyber incident",
        "ransomware",
        "network outage",
        "systems outage",
        "system outage",
        "information technology outage",
        "data breach",
        "unauthorized access",
        "cyber-related business interruption",
    ],
    "WEATHER_OR_PHYSICAL_DISASTER": [
        "severe weather",
        "hurricane damage",
        "winter storm",
        "wildfire",
        "flooding",
        "earthquake",
        "tornado",
        "facility fire",
        "plant fire",
        "natural disaster",
        "storm damage",
    ],
    "TEMPORARY_EXPECTATION_RESET": [
        "temporary headwinds",
        "temporary margin pressure",
        "temporary cost pressure",
        "temporary demand weakness",
        "temporary slowdown",
        "one-time impact",
        "one-time charge",
        "transitory impact",
        "guidance withdrawn",
        "lowered guidance",
        "temporary disruption",
        "temporary factors",
    ],
    "STRUCTURAL_IMPAIRMENT_CONTROL": [
        "going concern",
        "bankruptcy",
        "permanent closure",
        "permanently close",
        "non-reliance on previously issued financial statements",
        "material weakness",
        "ceased operations",
        "liquidation",
        "insolvency",
        "default under",
    ],
    "RESOLVED_BEFORE_DISCLOSURE_CONTROL": [
        "operations have resumed",
        "resumed normal operations",
        "service has been restored",
        "fully restored operations",
        "returned to normal operations",
        "operations resumed",
        "issue has been resolved",
    ],
}

PRIMARY_FAMILIES = (
    "PHYSICAL_MECHANICAL_INTERRUPTION",
    "EXTERNAL_HUMAN_INTERRUPTION",
    "CYBER_OR_IT_INTERRUPTION",
    "WEATHER_OR_PHYSICAL_DISASTER",
    "TEMPORARY_EXPECTATION_RESET",
)
CONTROL_FAMILIES = (
    "STRUCTURAL_IMPAIRMENT_CONTROL",
    "RESOLVED_BEFORE_DISCLOSURE_CONTROL",
)
BLOCKED_FAMILIES = {
    "MACRO_OR_INDUSTRY_WIDE": "SOURCE_CAPACITY_SHORTFALL",
}

FORMS = ("8-K", "6-K")
BASE_FORMS = frozenset(FORMS)
AMENDMENT_FORMS = frozenset({"8-K/A", "6-K/A"})
ALLOWED_FORMS = BASE_FORMS | AMENDMENT_FORMS
WINDOWS = {
    "full_2016_2025": ("2016-01-01", "2025-12-31"),
    "modern_2022_2025": ("2022-01-01", "2025-12-31"),
    "development_2016_2021": ("2016-01-01", "2021-12-31"),
}
SEED = "DISLOCATION-P0-SOURCE-2026-08-20-v1"
TURN5_LEXICON_SHA256 = "c164b5b3d0cfa8365a685e88662b00d8ad338957886fd51771286bf3c137cb58"
A1_DECLARED_LEDGER_SHA256 = "04d502e398a0f2ae65df7b2f9d5156305094f7b10ca104da08792d7219c1f83c"
A1_DECLARED_SAMPLE_SEED = "ec34136d9ed11f0070a5eed0a0225f465f8095d3f3cd228b752b3c27c9f1e876"
FTS_CAP = 10_000
PAGE_SIZE = 100

QUOTAS = {
    "PHYSICAL_MECHANICAL_INTERRUPTION": {
        "source_target": 48, "modern": 32, "development": 16, "form_8k": 32, "form_6k": 16,
    },
    "EXTERNAL_HUMAN_INTERRUPTION": {
        "source_target": 48, "modern": 32, "development": 16, "form_8k": 32, "form_6k": 16,
    },
    "CYBER_OR_IT_INTERRUPTION": {
        "source_target": 48, "modern": 32, "development": 16, "form_8k": 32, "form_6k": 16,
    },
    "WEATHER_OR_PHYSICAL_DISASTER": {
        "source_target": 48, "modern": 32, "development": 16, "form_8k": 32, "form_6k": 16,
    },
    "TEMPORARY_EXPECTATION_RESET": {
        "source_target": 48, "modern": 32, "development": 16, "form_8k": 32, "form_6k": 16,
    },
    "STRUCTURAL_IMPAIRMENT_CONTROL": {
        "source_target": 48, "modern": 32, "development": 16, "form_8k": 32, "form_6k": 16,
    },
    "RESOLVED_BEFORE_DISCLOSURE_CONTROL": {
        "source_target": 24, "modern": 16, "development": 8, "form_8k": 16, "form_6k": 8,
    },
    "MACRO_OR_INDUSTRY_WIDE": {
        "source_target": 24, "modern": 16, "development": 8, "form_8k": 16, "form_6k": 8,
        "status": "SOURCE_CAPACITY_SHORTFALL",
        "reason": "Turn-5 frozen lexicon has no MACRO_OR_INDUSTRY_WIDE phrases",
    },
}

MAX_PER_ISSUER_BEFORE_AUDIT = 5
RAW_CANDIDATE_FLOOR = 320
EPISODE_ORIGIN_FLOOR = 160
MODERN_FLOOR = 150

FORBIDDEN_PATHS = (
    "data/yahoo",
    "data/stocks",
    "data/ohlc",
    "data/stockdata",
    "data/intraday",
    "data/chinaohlc",
    "data/hkohlc",
    "data/canadaohlc",
    "data/intlohlc",
    "data/price_pressure",
    "data/washout_turn",
    "data/dislocation",
    "data/prophet",
    "data/radar",
)
FORBIDDEN_PATH_SUBSTRINGS = (
    "/ohlc",
    "/yahoo",
    "price_pressure",
    "washout_turn",
    "winner",
    "failure_case",
    "EXK_TURN4_CANONICAL_REPLAY",
)
ALLOWED_HOSTS = frozenset(
    {
        "efts.sec.gov",
        "data.sec.gov",
        "www.sec.gov",
    }
)
ALLOWED_SCHEMES = frozenset({"https"})
FORBIDDEN_MARKET_FIELDS = (
    "price",
    "return",
    "volume",
    "market_cap",
    "dollar_volume",
    "relative_strength",
    "forward_return",
    "mfe",
    "mae",
    "outcome",
)
AUTHORITY_FALSE = {
    "can_rank": False,
    "can_gate": False,
    "can_size": False,
    "can_originate_signal": False,
    "can_escalate": False,
}

EXCLUDED_TICKERS = frozenset({"EXK"})
EXCLUDED_NAME_SUBSTRINGS = ("endeavour silver",)
EXCLUDED_CIKS = frozenset({"0001015647"})

_ACCESSION_RE = re.compile(r"^[0-9]{10}-[0-9]{2}-[0-9]{6}$")
_CIK_RE = re.compile(r"^[0-9]{1,10}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ACCEPTANCE_SGML_RE = re.compile(br"<ACCEPTANCE-DATETIME>\s*(\d{14})", re.I)
_ACCEPTANCE_HTML_RE = re.compile(
    r"Accepted:</(?:div|td|th)>\s*<(?:div|td)[^>]*>\s*"
    r"(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2}:\d{2})",
    re.I,
)
_TICKER_FROM_DISPLAY_RE = re.compile(
    r"\(([A-Z][A-Z.\-]{0,6})\)\s*\(CIK",
    re.I,
)

STRUCTURAL_SPANS = (
    "going concern",
    "chapter 11",
    "chapter 7",
    "permanent closure",
    "permanently close",
    "ceased operations",
    "liquidation",
    "insolvency",
    "material weakness",
    "non-reliance",
    "restatement",
)
RECOVERABILITY_SPANS = {
    "PHYSICAL_REPAIR": (
        "repair",
        "repaired",
        "restore operations",
        "expected to resume",
        "return to service",
        "rebuild",
    ),
    "OPERATING_WORKAROUND": (
        "workaround",
        "alternate facility",
        "shifted production",
        "rerouted",
        "temporary facility",
    ),
    "NEGOTIATED_RESOLUTION": (
        "settlement",
        "agreement reached",
        "resolved the dispute",
        "labor agreement",
    ),
    "TEMPORARY_ORDER": (
        "temporary restraining",
        "injunction",
        "regulatory order",
        "stop-work order",
    ),
    "ONE_TIME_ACCOUNTING": (
        "one-time charge",
        "one-time impact",
        "non-recurring",
        "transitory",
    ),
}


class BlindWorkspaceError(RuntimeError):
    """Price-blind workspace or host contract violated."""


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def lexicon_sha256() -> str:
    return sha256_text(canonical_json(LEXICON))


def canonical_cik(value: Any) -> str | None:
    if value is None or value == "":
        return None
    text = str(value).strip()
    if not _CIK_RE.fullmatch(text) or int(text) == 0:
        return None
    return f"{int(text):010d}"


def canonical_accession(value: Any) -> str | None:
    if value is None or value == "":
        return None
    text = str(value).strip()
    if _ACCESSION_RE.fullmatch(text):
        return text
    digits = re.sub(r"[^0-9]", "", text)
    if len(digits) == 18:
        candidate = f"{digits[:10]}-{digits[10:12]}-{digits[12:]}"
        if _ACCESSION_RE.fullmatch(candidate):
            return candidate
    return None


def base_form(form: str | None) -> str | None:
    if not form:
        return None
    text = str(form).strip().upper().replace(" ", "")
    if text.endswith("/A"):
        text = text[:-2]
    if text in {"8-K", "8K"}:
        return "8-K"
    if text in {"6-K", "6K"}:
        return "6-K"
    return None


def is_amendment(form: str | None) -> bool:
    if not form:
        return False
    return str(form).strip().upper().endswith("/A")


def normalize_form(form: str | None) -> str | None:
    family = base_form(form)
    if family is None:
        return None
    return f"{family}/A" if is_amendment(form) else family


def client_side_form_ok(form: str | None, expected_base: str) -> bool:
    family = base_form(form)
    return family == expected_base


def era_for_filed_on(filed_on: str | None) -> str | None:
    if not filed_on or not _DATE_RE.fullmatch(filed_on):
        return None
    year = int(filed_on[:4])
    if 2022 <= year <= 2025:
        return "modern"
    if 2016 <= year <= 2021:
        return "development"
    return None


def selection_key(
    *,
    family: str,
    era: str,
    base: str,
    cik: str,
    accession: str,
    seed: str = SEED,
) -> str:
    payload = "|".join((seed, family, era, base, cik, accession))
    return sha256_text(payload)


def query_cell_id(family: str, phrase: str, form: str, start: str, end: str) -> str:
    return sha256_text(canonical_json(
        {
            "family": family,
            "phrase": phrase,
            "form": form,
            "start": start,
            "end": end,
        }
    ))


def build_query_ledger() -> dict[str, Any]:
    cells: list[dict[str, Any]] = []
    start, end = WINDOWS["full_2016_2025"]
    for family, phrases in LEXICON.items():
        for phrase in phrases:
            for form in FORMS:
                cells.append(
                    {
                        "query_cell_id": query_cell_id(family, phrase, form, start, end),
                        "family": family,
                        "phrase": phrase,
                        "base_form": form,
                        "date_shard": {"start": start, "end": end},
                    }
                )
    ledger = {
        "schema": "mastermind.dislocation_p0.source_query_ledger.v1",
        "seed": SEED,
        "lexicon_sha256": lexicon_sha256(),
        "turn5_lexicon_sha256": TURN5_LEXICON_SHA256,
        "a1_declared_ledger_sha256": A1_DECLARED_LEDGER_SHA256,
        "a1_declared_sample_seed": A1_DECLARED_SAMPLE_SEED,
        "a1_declared_ledger_status": "UNVERIFIED_ABSENT_SOURCE_FILE",
        "forms": list(FORMS),
        "windows": {
            key: {"start": value[0], "end": value[1]} for key, value in WINDOWS.items()
        },
        "lexicon": LEXICON,
        "quotas": QUOTAS,
        "blocked_families": BLOCKED_FAMILIES,
        "exclusions": {
            "tickers": sorted(EXCLUDED_TICKERS),
            "ciks": sorted(EXCLUDED_CIKS),
            "name_substrings": list(EXCLUDED_NAME_SUBSTRINGS),
            "note": (
                "Ticker EDR is not a blanket exclusion: US EDR is a different "
                "issuer. Exclude Endeavour Silver by CIK/name/EXK only."
            ),
        },
        "selection": {
            "seed": SEED,
            "formula": "SHA256(seed | family | era | base_form | cik | accession)",
            "review_order": "ascending selection_key",
            "max_per_issuer_before_audit": MAX_PER_ISSUER_BEFORE_AUDIT,
        },
        "query_cells": cells,
        "rights": {
            "sec_reporting_core": True,
            "sedar_public_automation": False,
            "sedar_status": "RIGHTS_BLOCKED",
        },
        "authority": dict(AUTHORITY_FALSE),
        "warning": (
            "Query phrase is candidate provenance, never event-family evidence. "
            "A search hit is not an economic episode."
        ),
    }
    return ledger


def query_ledger_sha256(ledger: Mapping[str, Any] | None = None) -> str:
    payload = ledger if ledger is not None else build_query_ledger()
    return sha256_text(canonical_json(payload))


def present_forbidden_paths(root: Path) -> list[str]:
    found: list[str] = []
    for rel in FORBIDDEN_PATHS:
        if (root / rel).exists():
            found.append(rel)
    return found


def assert_blind_workspace(root: Path) -> list[str]:
    present = present_forbidden_paths(root)
    if present:
        raise BlindWorkspaceError(
            f"price/outcome paths present in blind workspace: {present}"
        )
    return present


def assert_allowed_url(url: str) -> None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in ALLOWED_SCHEMES or host not in ALLOWED_HOSTS:
        raise BlindWorkspaceError(f"banned host or scheme: {url}")


class AccessLog:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def record(self, kind: str, target: str, *, allowed: bool, note: str = "") -> None:
        self.events.append(
            {
                "kind": kind,
                "target": target,
                "allowed": allowed,
                "note": note,
            }
        )

    def read_path(self, path: Path, root: Path) -> None:
        rel = str(path.resolve())
        banned = any(token in rel for token in FORBIDDEN_PATH_SUBSTRINGS)
        self.record("path", rel, allowed=not banned)
        if banned:
            raise BlindWorkspaceError(f"banned-path read: {rel}")

    def fetch_url(self, url: str) -> None:
        try:
            assert_allowed_url(url)
        except BlindWorkspaceError:
            self.record("url", url, allowed=False)
            raise
        self.record("url", url, allowed=True)

    def digest(self) -> str:
        return sha256_text(canonical_json(self.events))

    def banned_reads(self) -> list[dict[str, Any]]:
        return [row for row in self.events if not row["allowed"]]


def split_date_range(start: str, end: str) -> tuple[tuple[str, str], tuple[str, str]] | None:
    first = date.fromisoformat(start)
    last = date.fromisoformat(end)
    if last <= first:
        return None
    delta_days = (last - first).days
    mid = first + timedelta(days=delta_days // 2)
    if mid <= first or mid >= last:
        left_end = first
        right_start = first + timedelta(days=1)
        if right_start > last:
            return None
        return (start, left_end.isoformat()), (right_start.isoformat(), end)
    left_end = mid
    right_start = mid + timedelta(days=1)
    return (start, left_end.isoformat()), (right_start.isoformat(), end)


def annual_shards(start: str, end: str) -> list[tuple[str, str]]:
    start_year = int(start[:4])
    end_year = int(end[:4])
    shards: list[tuple[str, str]] = []
    for year in range(start_year, end_year + 1):
        shard_start = f"{year}-01-01"
        shard_end = f"{year}-12-31"
        if year == start_year:
            shard_start = start
        if year == end_year:
            shard_end = end
        shards.append((shard_start, shard_end))
    return shards


def parse_sgml_acceptance(raw: bytes) -> str | None:
    match = _ACCEPTANCE_SGML_RE.search(raw[:65536] if len(raw) > 65536 else raw)
    if not match:
        return None
    stamp = match.group(1).decode("ascii")
    try:
        eastern = datetime.strptime(stamp, "%Y%m%d%H%M%S").replace(
            tzinfo=ZoneInfo("America/New_York")
        )
    except ValueError:
        return None
    return eastern.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_html_acceptance(text: str) -> str | None:
    match = _ACCEPTANCE_HTML_RE.search(text)
    if not match:
        return None
    stamp = f"{match.group(1)} {match.group(2)}"
    try:
        eastern = datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=ZoneInfo("America/New_York")
        )
    except ValueError:
        return None
    return eastern.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso_acceptance(value: Any) -> str | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def clock_quality(accepted_at: str | None, filed_on: str | None) -> str:
    if accepted_at:
        return "EXACT_SEC_ACCEPTANCE"
    if filed_on:
        return "DATE_ONLY_REFUSED"
    return "UNAVAILABLE"


def ticker_from_display_name(display_name: str | None) -> str | None:
    if not display_name:
        return None
    match = _TICKER_FROM_DISPLAY_RE.search(display_name)
    if match:
        return match.group(1).upper()
    return None


def is_design_excluded(
    *,
    ticker: str | None,
    cik: str | None,
    display_name: str | None,
) -> bool:
    if ticker and ticker.upper() in EXCLUDED_TICKERS:
        return True
    canonical = canonical_cik(cik)
    if canonical and canonical in EXCLUDED_CIKS:
        return True
    name = (display_name or "").lower()
    return any(token in name for token in EXCLUDED_NAME_SUBSTRINGS)


def decode_document(raw: bytes) -> str:
    for encoding in ("utf-8", "latin-1", "cp1252"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def find_spans(text: str, needles: Iterable[str], *, claim_field: str) -> list[dict[str, Any]]:
    lowered = text.lower()
    spans: list[dict[str, Any]] = []
    for needle in needles:
        target = needle.lower()
        start = 0
        while True:
            idx = lowered.find(target, start)
            if idx < 0:
                break
            end = idx + len(target)
            excerpt = text[max(0, idx - 80): min(len(text), end + 80)]
            excerpt = re.sub(r"\s+", " ", excerpt).strip()[:500]
            payload = {
                "start": idx,
                "end": end,
                "claim_field": claim_field,
                "excerpt": excerpt,
                "needle": needle,
            }
            payload["span_id"] = sha256_text(canonical_json(payload))[:16]
            spans.append(payload)
            start = end
    return spans


def extract_pass(
    text: str,
    *,
    query_phrase: str,
    family_candidate: str,
    pass_id: str,
) -> dict[str, Any]:
    """Deterministic, evidence-cited extraction. Pass id changes only the
    structural-alternative threshold, not the source bytes."""
    phrase_spans = find_spans(text, [query_phrase], claim_field="query_provenance")
    structural = find_spans(text, STRUCTURAL_SPANS, claim_field="structural_impairment_at_t0")
    recoverability: list[dict[str, Any]] = []
    recoverability_type = "UNKNOWN"
    for kind, needles in RECOVERABILITY_SPANS.items():
        hits = find_spans(text, needles, claim_field="recoverability_evidence_at_t0")
        if hits and recoverability_type == "UNKNOWN":
            recoverability_type = kind
        recoverability.extend(hits)

    duration_spans = find_spans(
        text,
        (
            "temporary",
            "temporarily",
            "expected to resume",
            "duration",
            "days",
            "weeks",
            "months",
        ),
        claim_field="adverse_uncertainty_at_t0",
    )
    adverse_spans = phrase_spans + find_spans(
        text,
        ("interruption", "outage", "suspend", "disruption", "incident", "damage"),
        claim_field="new_adverse_information_at_t0",
    )

    structural_present = bool(structural)
    # Pass two requires two distinct structural needles before asserting
    # structural evidence, so the independent pass can disagree.
    if pass_id == "pass2":
        distinct = {row["needle"] for row in structural}
        structural_present = len(distinct) >= 2

    if not phrase_spans and not adverse_spans:
        family = None
        state = "REFUSED"
        refusal = "NOT_AN_ADVERSE_EVENT"
        adverse = "UNKNOWN"
    else:
        family = family_candidate
        state = "PROPOSED"
        refusal = None
        adverse = True

    if structural_present and family_candidate not in CONTROL_FAMILIES:
        # Keep the query family as candidate provenance; flag structural alternative.
        structural_state = "EVIDENCE_PRESENT"
    elif structural_present:
        structural_state = "EVIDENCE_PRESENT"
    else:
        structural_state = "UNKNOWN"

    if duration_spans and recoverability_type != "UNKNOWN":
        uncertainty = "PARTIALLY_BOUNDED"
    elif duration_spans:
        uncertainty = "OPEN"
    else:
        uncertainty = "UNKNOWN"

    return {
        "pass_id": pass_id,
        "state": state,
        "refusal_reason": refusal,
        "event_family": family,
        "new_adverse_information_at_t0": adverse,
        "adverse_uncertainty_at_t0": uncertainty,
        "recoverability_evidence_at_t0": recoverability_type,
        "structural_impairment_at_t0": structural_state,
        "intent_orchestration": "UNKNOWN",
        "proposed_by": f"dislocation_p0_a1_lib.extract_pass:{pass_id}",
        "spans": phrase_spans + structural + recoverability + duration_spans[:12],
    }


def forbidden_market_fields(payload: Mapping[str, Any]) -> list[str]:
    found: list[str] = []

    def walk(node: Any, path: str) -> None:
        if isinstance(node, Mapping):
            for key, value in node.items():
                key_l = str(key).lower()
                here = f"{path}.{key}" if path else str(key)
                if key_l in FORBIDDEN_MARKET_FIELDS:
                    found.append(here)
                walk(value, here)
        elif isinstance(node, list):
            for idx, value in enumerate(node):
                walk(value, f"{path}[{idx}]")

    walk(payload, "")
    return found


def authority_flags(payload: Mapping[str, Any]) -> dict[str, bool]:
    authority = payload.get("authority") if isinstance(payload.get("authority"), Mapping) else {}
    return {key: bool(authority.get(key, False)) for key in AUTHORITY_FALSE}


def issuer_identity(hit: Mapping[str, Any]) -> str:
    cik = canonical_cik(hit.get("cik"))
    if cik:
        return f"cik:{cik}"
    ticker = (hit.get("ticker") or ticker_from_display_name(hit.get("display_name")) or "").upper()
    if ticker:
        return f"ticker:{ticker}"
    accession = canonical_accession(hit.get("accession"))
    return f"accession:{accession or hit.get('hit_id')}"


def select_quota_rows(
    rows: list[dict[str, Any]],
    *,
    family: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    quota = QUOTAS[family]
    accepted: list[dict[str, Any]] = []
    refused: list[dict[str, Any]] = []
    issuer_counts: dict[str, int] = {}
    modern_n = 0
    development_n = 0
    form_8k_n = 0
    form_6k_n = 0
    target = int(quota["source_target"])
    ordered = sorted(rows, key=lambda row: row["selection_key"])
    for row in ordered:
        issuer = issuer_identity(row)
        era = row.get("era")
        form_family = base_form(row.get("form"))
        reasons: list[str] = []
        if issuer_counts.get(issuer, 0) >= MAX_PER_ISSUER_BEFORE_AUDIT:
            reasons.append("ISSUER_CAP")
        if era == "modern" and modern_n >= int(quota["modern"]):
            reasons.append("MODERN_QUOTA")
        if era == "development" and development_n >= int(quota["development"]):
            reasons.append("DEVELOPMENT_QUOTA")
        if form_family == "8-K" and form_8k_n >= int(quota["form_8k"]):
            reasons.append("FORM_8K_QUOTA")
        if form_family == "6-K" and form_6k_n >= int(quota["form_6k"]):
            reasons.append("FORM_6K_QUOTA")
        if len(accepted) >= target:
            reasons.append("FAMILY_TARGET")
        if reasons:
            refused.append(row | {"refusal_reason": reasons[0], "refusal_reasons": reasons})
            continue
        accepted.append(row)
        issuer_counts[issuer] = issuer_counts.get(issuer, 0) + 1
        if era == "modern":
            modern_n += 1
        elif era == "development":
            development_n += 1
        if form_family == "8-K":
            form_8k_n += 1
        elif form_family == "6-K":
            form_6k_n += 1
    return accepted, refused
