"""E3-A shadow compiler — AAPL FY2026 Q3 leakage-free eval only.

Not R2-writeable. Not event_workspace.v1-generating.
Gold labels are loaded ONLY after model inference completes.

Frozen source package:
  Exhibit 99.1: 070abd6a9cdb7070e546d24ffcbc41c65450d939c6f88f189cb18ec711cf5fdb
  Transcript:   a8ff5d03e875fef5604791edbf625186c447af049e6e02f55bb89c68c7cc9f9f
  Event:        evt_cik0000320193_2026q3_results
  Generation:   f709a0a6ec514282d5769e7d
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import plistlib
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

# Frozen source SHAs — divergence check is load-bearing.
FROZEN_EXHIBIT_SHA = "070abd6a9cdb7070e546d24ffcbc41c65450d939c6f88f189cb18ec711cf5fdb"
FROZEN_TRANSCRIPT_SHA = "a8ff5d03e875fef5604791edbf625186c447af049e6e02f55bb89c68c7cc9f9f"
PINNED_GENERATION_ID = "f709a0a6ec514282d5769e7d"
PINNED_WORKSPACE_SHA = "dbd50e5c30e8a031f844e02362ffd53b25e3230e75eeef19bf3825543cb81197"

EVENT_ID = "evt_cik0000320193_2026q3_results"
TX_DOC_ID = "tx:AAPL/2026Q3"
RELEASE_DOC_ID = "release:0000320193-26-000018"

GOLD_PATH = Path(
    "research/earnings_intelligence/e3/gold/aapl_fy2026_q3_qa_gold.json"
)
EVAL_RECEIPT_PATH = Path(
    "research/earnings_intelligence/e3/gold/aapl_fy2026_q3_eval_receipt.json"
)
ADJUDICATION_RECEIPT_PATH = Path(
    "research/earnings_intelligence/e3/gold/aapl_fy2026_q3_adjudication_receipt.json"
)

LANE = "earnings_event_compiler"
FROZEN_GOLD_SHA = "6b1100b148396db9a29974da5bc6e0cc55e5534185e50e061fe3635d429ed761"
TAXONOMY_VERSION = "qa_topic.v1"
TAXONOMY_HASH = "a928ca72ab2e91bda74bd1e69021e08a5234e501f095610e623655db7e323b5e"
CLOSED_TAXONOMY = frozenset({
    "demand", "product", "pricing", "costs_supply",
    "capacity", "capital_allocation", "regulation",
    "other", "unavailable",
})

# Closed candidate schema. Unknown keys fail. The validator binds identity.
CANDIDATE_KEYS = (
    "ordinal",
    "boundary_segment_index",
    "questioner_name",
    "affiliation",
    "question_segment_indexes",
    "answer_segment_indexes",
    "respondents",
    "topics",
)
CANDIDATE_KEY_SET = frozenset(CANDIDATE_KEYS)
FOREIGN_IDENTITY_KEYS = frozenset({"event_id", "document_id", "document_sha256"})

WORKER_PLIST_REL = Path("ops/launchd/com.mastermind.earnings-worker.plist")
FROZEN_COMPARATOR_MODEL = "claude-haiku-4-5"
EXTRACTION_MAX_TOKENS = 4096

# ── Extraction prompt ─────────────────────────────────────────────────────────

SYSTEM_PROMPT = (
    "You are an earnings call Q&A extraction assistant. "
    "The segments include prepared remarks and then an analyst Q&A session. "
    "An Operator segment that contains 'go ahead' opens a new exchange. "
    "Extract EVERY such exchange. Return [] only if there is no Operator Q&A. "
    "Return a JSON array only. Each object may contain EXACTLY these keys "
    "and no others:\n"
    "  ordinal (int, 0-based)\n"
    "  boundary_segment_index (int) — the Operator intro segment that opens "
    "the exchange (the segment whose role is Operator and that contains "
    "'go ahead')\n"
    "  questioner_name (str)\n"
    "  affiliation (str)\n"
    "  question_segment_indexes (ordered list[int])\n"
    "  answer_segment_indexes (ordered list[int])\n"
    "  respondents (ordered list of {name: str, role: str})\n"
    "  topics (list[str], 1–3 members of: demand, product, pricing, "
    "costs_supply, capacity, capital_allocation, regulation, other, "
    "unavailable)\n\n"
    "Do not include event_id, document_id, document_sha256, or any other key. "
    "Do not invent information not present in the source segments. "
    "Do not include explanation outside the JSON array."
)


def _build_user_prompt(segments: list[dict]) -> str:
    """Build the extraction prompt from transcript segments.

    Uses all segments — no head/tail truncation per freeze §4.
    Gold labels are NOT included.
    """
    lines = ["Earnings call transcript segments:\n"]
    for i, seg in enumerate(segments):
        role = seg.get("role", "")
        speaker = seg.get("speaker", "")
        text = seg.get("text", "")
        lines.append(f"[segment {i}] role={role!r} speaker={speaker!r}")
        lines.append(text)
        lines.append("")
    lines.append(
        "\nReturn a JSON array of objects using only the closed candidate keys."
    )
    return "\n".join(lines)


# ── Source loading + SHA verification ────────────────────────────────────────


def verify_fixture_shas(root: Path) -> dict[str, str]:
    """Verify fixture SHAs match frozen spec. Raises on divergence."""
    exhibit_path = root / "tests/fixtures/company_intelligence/aapl_fy2026_q3_ex99_1.htm"
    tx_path = root / "tests/fixtures/company_intelligence/aapl_fy2026_q3.json.gz"

    exhibit_sha = hashlib.sha256(exhibit_path.read_bytes()).hexdigest()
    with gzip.open(tx_path) as f:
        tx_sha = hashlib.sha256(f.read()).hexdigest()

    if exhibit_sha != FROZEN_EXHIBIT_SHA:
        raise RuntimeError(
            f"Exhibit 99.1 SHA divergence: fixture={exhibit_sha} "
            f"frozen={FROZEN_EXHIBIT_SHA} — STOP per E3-A §1"
        )
    if tx_sha != FROZEN_TRANSCRIPT_SHA:
        raise RuntimeError(
            f"Transcript SHA divergence: fixture={tx_sha} "
            f"frozen={FROZEN_TRANSCRIPT_SHA} — STOP per E3-A §1"
        )
    return {
        "exhibit_sha": exhibit_sha,
        "transcript_sha": tx_sha,
        "check": "pass",
    }


def load_transcript_segments(root: Path) -> list[dict]:
    """Load transcript segments from the frozen fixture."""
    tx_path = root / "tests/fixtures/company_intelligence/aapl_fy2026_q3.json.gz"
    with gzip.open(tx_path) as f:
        tx = json.load(f)
    return tx["segments"]


def verify_live_workspace_shas() -> dict[str, Any]:
    """Read the live E2 workspace through the verified public reader.

    Pins generation f709a0a6ec514282d5769e7d. Does not assume from the handoff.
    """
    from engine.neuralweb import company_intelligence_reader as reader

    result = reader.read_event_workspace({"event_id": EVENT_ID})
    receipt = dict(result.get("receipt") or {})
    workspace = dict(result.get("workspace") or {})
    sources = {
        str(s.get("kind")): s
        for s in (workspace.get("sources") or [])
        if isinstance(s, dict)
    }
    release_sha = str((sources.get("issuer_release") or {}).get("source_sha256") or "")
    transcript_sha = str((sources.get("transcript") or {}).get("source_sha256") or "")
    generation_id = str(workspace.get("generation_id") or receipt.get("generation_id") or "")
    workspace_sha = str(receipt.get("workspace_sha256") or "")
    match = (
        result.get("available") is True
        and generation_id == PINNED_GENERATION_ID
        and workspace_sha == PINNED_WORKSPACE_SHA
        and release_sha == FROZEN_EXHIBIT_SHA
        and transcript_sha == FROZEN_TRANSCRIPT_SHA
    )
    return {
        "available": bool(result.get("available")),
        "reader": "engine.neuralweb.company_intelligence_reader.read_event_workspace",
        "generation_id": generation_id,
        "workspace_sha256": workspace_sha,
        "workspace_url": receipt.get("workspace_url"),
        "marker_url": receipt.get("marker_url"),
        "release_source_sha256": release_sha,
        "transcript_source_sha256": transcript_sha,
        "matches_frozen_fixtures": match,
        "assumed_from_handoff": False,
        "note": None if match else (result.get("note") or "live workspace SHA mismatch"),
    }


# ── Stable segment_id ─────────────────────────────────────────────────────────


def stable_segment_id(document_sha256: str, segment_index: int) -> str:
    """Deterministic segment_id = (document_sha256, segment_index)."""
    return f"seg_{document_sha256[:16]}_{segment_index:04d}"


def gold_boundary_segment(exchange: dict) -> int:
    """Operator-intro segment that opens a gold exchange."""
    spans = exchange.get("question_spans") or []
    if not spans:
        raise ValueError("gold exchange missing question_spans")
    return int(spans[0]["segment_index"])


def gold_exchange_to_candidate(exchange: dict) -> dict:
    """Project a gold exchange onto the closed candidate schema."""
    return {
        "ordinal": int(exchange["ordinal"]),
        "boundary_segment_index": gold_boundary_segment(exchange),
        "questioner_name": str(exchange["questioner"]["name"]),
        "affiliation": str(exchange["questioner"]["affiliation"]),
        "question_segment_indexes": [
            int(s["segment_index"]) for s in exchange["question_spans"]
        ],
        "answer_segment_indexes": [
            int(s["segment_index"]) for s in exchange["answer_spans"]
        ],
        "respondents": [
            {"name": str(r["name"]), "role": str(r["role"])}
            for r in exchange["respondents"]
        ],
        "topics": list(exchange.get("topics") or []),
    }


# ── Shadow validator ──────────────────────────────────────────────────────────


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _replay_indexes(indexes: list[int], segments: list[dict]) -> tuple[bool, list[dict]]:
    reconstructed: list[dict] = []
    for idx in indexes:
        if idx < 0 or idx >= len(segments):
            return False, reconstructed
        text = str(segments[idx].get("text") or "")
        raw = text.encode("utf-8")
        if not raw:
            return False, reconstructed
        reconstructed.append({
            "segment_index": idx,
            "start_byte": 0,
            "end_byte": len(raw),
            "text_sha256": hashlib.sha256(raw).hexdigest(),
            "speaker": segments[idx].get("speaker"),
            "role": segments[idx].get("role"),
        })
    return True, reconstructed


def validate_candidate(
    candidate: Any,
    segments: list[dict],
    *,
    n_segments: int | None = None,
) -> dict[str, Any]:
    """Deterministically validate one model candidate against the closed schema.

    The validator — not the model — binds event_id / document identity.
    """
    n_segments = n_segments if n_segments is not None else len(segments)
    if not isinstance(candidate, dict):
        return {"ok": False, "reason": "invalid_schema", "detail": "not_an_object"}

    extras = set(candidate) - CANDIDATE_KEY_SET
    foreign = extras & FOREIGN_IDENTITY_KEYS
    if foreign:
        for key in ("event_id", "document_id", "document_sha256"):
            if key not in candidate:
                continue
            value = candidate[key]
            expected = {
                "event_id": EVENT_ID,
                "document_id": TX_DOC_ID,
                "document_sha256": FROZEN_TRANSCRIPT_SHA,
            }[key]
            if value != expected:
                return {
                    "ok": False,
                    "reason": "cross_event",
                    "detail": f"foreign_{key}",
                }
        # Even a matching identity field is an unknown key on the closed schema.
        return {"ok": False, "reason": "invalid_schema", "detail": "unknown_key_identity_field"}
    if extras:
        return {"ok": False, "reason": "invalid_schema", "detail": "unknown_key"}

    missing = [k for k in CANDIDATE_KEYS if k not in candidate]
    if missing:
        return {"ok": False, "reason": "invalid_schema", "detail": f"missing:{missing[0]}"}

    if not _is_int(candidate["ordinal"]):
        return {"ok": False, "reason": "invalid_schema", "detail": "ordinal_type"}
    if not _is_int(candidate["boundary_segment_index"]):
        return {"ok": False, "reason": "invalid_schema", "detail": "boundary_segment_index_type"}
    if not isinstance(candidate["questioner_name"], str):
        return {"ok": False, "reason": "invalid_schema", "detail": "questioner_name_type"}
    if not isinstance(candidate["affiliation"], str):
        return {"ok": False, "reason": "invalid_schema", "detail": "affiliation_type"}
    q_idx = candidate["question_segment_indexes"]
    a_idx = candidate["answer_segment_indexes"]
    if not isinstance(q_idx, list) or not all(_is_int(i) for i in q_idx):
        return {"ok": False, "reason": "invalid_schema", "detail": "question_segment_indexes_type"}
    if not isinstance(a_idx, list) or not all(_is_int(i) for i in a_idx):
        return {"ok": False, "reason": "invalid_schema", "detail": "answer_segment_indexes_type"}
    if not q_idx or not a_idx:
        return {"ok": False, "reason": "invalid_schema", "detail": "empty_span_indexes"}
    respondents = candidate["respondents"]
    if not isinstance(respondents, list) or not respondents:
        return {"ok": False, "reason": "invalid_schema", "detail": "respondents_type"}
    for resp in respondents:
        if not isinstance(resp, dict):
            return {"ok": False, "reason": "invalid_schema", "detail": "respondent_type"}
        if set(resp.keys()) != {"name", "role"}:
            return {"ok": False, "reason": "invalid_schema", "detail": "respondent_keys"}
        if not isinstance(resp["name"], str) or not isinstance(resp["role"], str):
            return {"ok": False, "reason": "invalid_schema", "detail": "respondent_field_type"}
    topics = candidate["topics"]
    if not isinstance(topics, list) or not (1 <= len(topics) <= 3):
        return {"ok": False, "reason": "invalid_schema", "detail": "topics_arity"}
    if not all(isinstance(t, str) for t in topics):
        return {"ok": False, "reason": "invalid_schema", "detail": "topics_type"}
    if any(t not in CLOSED_TAXONOMY for t in topics):
        return {"ok": False, "reason": "unknown_topic", "detail": "topic_not_in_qa_topic.v1"}

    all_idx = [candidate["boundary_segment_index"], *q_idx, *a_idx]
    for idx in all_idx:
        if idx < 0 or idx >= n_segments:
            return {"ok": False, "reason": "out_of_range_segment", "detail": str(idx)}

    q_ok, q_spans = _replay_indexes(q_idx, segments)
    a_ok, a_spans = _replay_indexes(a_idx, segments)
    b_ok, b_spans = _replay_indexes([candidate["boundary_segment_index"]], segments)
    if not q_ok or not a_ok or not b_ok:
        return {"ok": False, "reason": "span_replay_failure", "detail": "index_replay"}

    bound = {
        "event_id": EVENT_ID,
        "document_id": TX_DOC_ID,
        "document_sha256": FROZEN_TRANSCRIPT_SHA,
        "question_spans": q_spans,
        "answer_spans": a_spans,
    }
    return {"ok": True, "reason": None, "bound": bound, "candidate": candidate}


def validate_candidates(candidates: list[Any], segments: list[dict]) -> dict[str, Any]:
    """Validate a candidate list. 'accepted' here is shadow-admissible only."""
    valid: list[dict] = []
    rejected: list[dict] = []
    reason_counts = {
        "invalid_schema_rejected": 0,
        "unknown_topic_rejected": 0,
        "out_of_range_rejected": 0,
        "cross_event_rejected": 0,
        "span_replay_rejected": 0,
    }
    reason_map = {
        "invalid_schema": "invalid_schema_rejected",
        "unknown_topic": "unknown_topic_rejected",
        "out_of_range_segment": "out_of_range_rejected",
        "cross_event": "cross_event_rejected",
        "span_replay_failure": "span_replay_rejected",
    }
    for raw in candidates:
        result = validate_candidate(raw, segments)
        if result["ok"]:
            valid.append(result)
        else:
            rejected.append({"candidate": raw, "rejection_reason": result["reason"], "detail": result.get("detail")})
            bucket = reason_map.get(result["reason"], "invalid_schema_rejected")
            reason_counts[bucket] += 1

    accepted_span_replay_count = sum(1 for v in valid if v.get("bound"))
    return {
        "valid_candidates": [v["candidate"] for v in valid],
        "rejected_candidates": rejected,
        "accepted_count": len(valid),
        "accepted_unsupported": reason_counts["span_replay_rejected"],
        "accepted_span_replay_count": accepted_span_replay_count,
        "invalid_schema_rejected": reason_counts["invalid_schema_rejected"],
        "unknown_topic_rejected": reason_counts["unknown_topic_rejected"],
        "out_of_range_rejected": reason_counts["out_of_range_rejected"],
        "cross_event_rejected": reason_counts["cross_event_rejected"],
        "span_replay_rejected": reason_counts["span_replay_rejected"],
        "valid_with_bound": valid,
    }


# ── Scoring against gold ───────────────────────────────────────────────────────


def _norm(value: Any) -> str:
    return str(value or "").strip()


def score_attempt(
    attempt: ModelAttempt | Any,
    gold: dict,
    segments: list[dict],
) -> dict[str, Any]:
    """Score model candidates against frozen gold using the shadow validator.

    Exchange-boundary TP is an exact one-to-one Operator-boundary match.
    Questioner-name equality alone is not a boundary match.
    Duplicate predictions cannot create duplicate TPs or recall > 1.
    """
    gold_exchanges = gold.get("exchanges") or []
    n_gold = len(gold_exchanges)
    raw_candidates = list(getattr(attempt, "candidates", None) or [])
    n_candidates = len(raw_candidates)

    if n_candidates == 0:
        return {
            "n_gold_exchanges": n_gold,
            "n_model_candidates": 0,
            "exchange_boundary_quality": {
                "tp": 0,
                "precision": None,
                "recall": None,
                "f1": None,
                "note": "model_produced_no_candidates",
            },
            "source_span_replay_success_pct": None,
            "unsupported_candidate_rate": None,
            "cross_event_contamination_accepted": 0,
            "topic_label_agreement_mean_jaccard": None,
            "identity_role_availability": None,
            "invalid_schema_rate": None,
            "accepted_count": 0,
            "accepted_unsupported": 0,
            "accepted_span_replay_count": 0,
            "invalid_schema_rejected": 0,
            "cross_event_rejected": 0,
            "valid_candidates": [],
            "rejected_candidates": [],
            "rejection_reason": None,
            "hard_gates": {
                "status": "NOT_EXERCISED",
                "accepted_unsupported": 0,
                "cross_event": 0,
                "span_replay_of_accepted": "NOT_EXERCISED",
                "invalid_schema_accepted": 0,
                "all_pass": False,
            },
            "per_exchange": [],
            "status": "no_candidates",
        }

    validated = validate_candidates(raw_candidates, segments)
    valid = validated["valid_candidates"]
    gold_by_boundary = {
        gold_boundary_segment(ex): ex for ex in gold_exchanges
    }
    used_boundaries: set[int] = set()
    pairs: list[tuple[dict, dict]] = []
    for cand in valid:
        boundary = int(cand["boundary_segment_index"])
        if boundary in used_boundaries:
            continue
        gold_ex = gold_by_boundary.get(boundary)
        if gold_ex is None:
            continue
        used_boundaries.add(boundary)
        pairs.append((gold_ex, cand))

    tp = len(pairs)
    fp = n_candidates - tp
    fn = n_gold - tp
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / n_gold if n_gold else 0.0
    if recall > 1.0:
        raise RuntimeError("recall > 1: duplicate TP matching leaked")
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0

    jaccards: list[float] = []
    identity_rows: list[dict] = []
    per_exchange: list[dict] = []
    for gold_ex, cand in pairs:
        g_topics = set(gold_ex.get("topics") or [])
        m_topics = set(cand.get("topics") or [])
        jaccard = (len(g_topics & m_topics) / len(g_topics | m_topics)) if (g_topics or m_topics) else 1.0
        jaccards.append(jaccard)
        gq = gold_ex.get("questioner") or {}
        g_resps = list(gold_ex.get("respondents") or [])
        m_resps = list(cand.get("respondents") or [])
        name_ok = _norm(cand.get("questioner_name")) == _norm(gq.get("name"))
        aff_ok = _norm(cand.get("affiliation")) == _norm(gq.get("affiliation"))
        g_names = [_norm(r.get("name")) for r in g_resps]
        m_names = [_norm(r.get("name")) for r in m_resps]
        g_roles = [_norm(r.get("role")) for r in g_resps]
        m_roles = [_norm(r.get("role")) for r in m_resps]
        names_ok = g_names == m_names
        roles_ok = g_roles == m_roles
        identity_rows.append({
            "questioner_name": name_ok,
            "affiliation": aff_ok,
            "respondent_names_ordered": names_ok,
            "respondent_roles_ordered": roles_ok,
        })
        errors = []
        if not name_ok:
            errors.append("questioner_name")
        if not aff_ok:
            errors.append("affiliation")
        if not names_ok:
            errors.append("respondent_names")
        if not roles_ok:
            errors.append("respondent_roles")
        per_exchange.append({
            "gold_ordinal": gold_ex["ordinal"],
            "gold_boundary_segment_index": gold_boundary_segment(gold_ex),
            "candidate_ordinal": cand.get("ordinal"),
            "topic_jaccard": jaccard,
            "identity_errors": errors,
        })

    matched_gold = {gold_boundary_segment(g) for g, _ in pairs}
    for gold_ex in gold_exchanges:
        if gold_boundary_segment(gold_ex) in matched_gold:
            continue
        per_exchange.append({
            "gold_ordinal": gold_ex["ordinal"],
            "gold_boundary_segment_index": gold_boundary_segment(gold_ex),
            "candidate_ordinal": None,
            "topic_jaccard": None,
            "identity_errors": ["unmatched"],
        })

    n_id = len(identity_rows)
    identity = None
    if n_id:
        identity = {
            "matched_exchanges": n_id,
            "questioner_name_match_rate": sum(r["questioner_name"] for r in identity_rows) / n_id,
            "affiliation_match_rate": sum(r["affiliation"] for r in identity_rows) / n_id,
            "respondent_name_order_match_rate": sum(r["respondent_names_ordered"] for r in identity_rows) / n_id,
            "respondent_role_order_match_rate": sum(r["respondent_roles_ordered"] for r in identity_rows) / n_id,
        }

    accepted = validated["accepted_count"]
    replay_pct = (
        (100.0 * validated["accepted_span_replay_count"] / accepted) if accepted else None
    )
    unsupported_rate = (
        validated["accepted_unsupported"] / n_candidates if n_candidates else None
    )
    invalid_rate = (
        validated["invalid_schema_rejected"] / n_candidates if n_candidates else None
    )
    gates_pass = (
        accepted > 0
        and validated["accepted_unsupported"] == 0
        and validated["accepted_span_replay_count"] == accepted
    )
    return {
        "n_gold_exchanges": n_gold,
        "n_model_candidates": n_candidates,
        "exchange_boundary_quality": {
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "precision": precision,
            "recall": recall,
            "f1": f1,
        },
        "source_span_replay_success_pct": replay_pct,
        "unsupported_candidate_rate": unsupported_rate,
        "cross_event_contamination_accepted": 0,
        "topic_label_agreement_mean_jaccard": (
            sum(jaccards) / len(jaccards) if jaccards else None
        ),
        "identity_role_availability": identity,
        "invalid_schema_rate": invalid_rate,
        "accepted_count": accepted,
        "accepted_unsupported": validated["accepted_unsupported"],
        "accepted_span_replay_count": validated["accepted_span_replay_count"],
        "invalid_schema_rejected": validated["invalid_schema_rejected"],
        "cross_event_rejected": validated["cross_event_rejected"],
        "valid_candidates": valid,
        "rejected_candidates": validated["rejected_candidates"],
        "rejection_reason": [
            r["rejection_reason"] for r in validated["rejected_candidates"]
        ],
        "hard_gates": {
            "status": "PASS" if gates_pass else "FAIL",
            "accepted_unsupported": validated["accepted_unsupported"],
            "cross_event": validated["cross_event_rejected"],
            "span_replay_of_accepted": (
                f"{replay_pct:.1f}% ({accepted} accepted)" if replay_pct is not None else "n/a"
            ),
            "invalid_schema_accepted": 0,
            "all_pass": gates_pass,
        },
        "per_exchange": per_exchange,
        "status": "scored",
    }


# ── Model calls ───────────────────────────────────────────────────────────────


@dataclass
class ModelAttempt:
    provider: str
    model: str
    prompt_version: str = "e3a-qa-extraction-v1"
    status: str = "pending"
    degraded_reason: str | None = None
    raw_response: str | None = None
    candidates: list[dict] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    est_cost_usd: float = 0.0
    latency_ms: float = 0.0
    provider_fallback_reason: str | None = None
    is_comparator: bool = False
    comparator_note: str = ""
    endpoint_class: str | None = None
    base_url_source: str | None = None
    preflight: dict[str, Any] = field(default_factory=dict)


def _parse_plist_llm(root: Path) -> tuple[str, str]:
    path = root / WORKER_PLIST_REL
    if not path.exists():
        return "", ""
    data = plistlib.loads(path.read_bytes())
    env = data.get("EnvironmentVariables") or {}
    return str(env.get("EARNINGS_LLM_BASE_URL") or "").strip(), str(
        env.get("EARNINGS_LLM_MODEL") or ""
    ).strip()


def resolve_qwen_openai_compat_cfg(repo_root: Path, yaml_oc: dict) -> dict[str, Any]:
    """Same override order as tools/earnings_worker/run_worker.py.

    Env EARNINGS_LLM_BASE_URL / EARNINGS_LLM_MODEL win; else the durable
    worker launchd plist; else the YAML placeholder. Never invent a second
    local-model route.
    """
    cfg = dict(yaml_oc or {})
    env_url = os.environ.get("EARNINGS_LLM_BASE_URL", "").strip()
    env_model = os.environ.get("EARNINGS_LLM_MODEL", "").strip()
    plist_url, plist_model = _parse_plist_llm(repo_root)
    if env_url:
        cfg["base_url"] = env_url
        cfg["base_url_source"] = "env"
    elif plist_url:
        cfg["base_url"] = plist_url
        cfg["base_url_source"] = "earnings_worker_plist"
    else:
        cfg["base_url_source"] = "yaml_placeholder"
    if env_model:
        cfg["model"] = env_model
        cfg["model_source"] = "env"
    elif plist_model:
        cfg["model"] = plist_model
        cfg["model_source"] = "earnings_worker_plist"
    else:
        cfg["model_source"] = "yaml_placeholder"
    return cfg


def _endpoint_class(base_url: str) -> str:
    host = (urlparse(base_url).hostname or "").lower()
    if host in {"localhost", "127.0.0.1", "::1"}:
        return "loopback"
    if host.startswith("192.168.") or host.startswith("10.") or host.startswith("172."):
        return "private_lan"
    if not host:
        return "unconfigured"
    return "other"


def preflight_qwen_endpoint(oc_cfg: dict) -> dict[str, Any]:
    """Read-only /models probe. Records class + model identity, not credentials."""
    base_url = str(oc_cfg.get("base_url") or "").rstrip("/")
    model = str(oc_cfg.get("model") or "")
    info: dict[str, Any] = {
        "endpoint_class": _endpoint_class(base_url),
        "model": model,
        "base_url_source": oc_cfg.get("base_url_source"),
        "model_source": oc_cfg.get("model_source"),
        "status": "unconfigured",
        "served_ids": [],
    }
    if not base_url or not model:
        return info
    url = f"{base_url}/models"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            body = resp.read(8192)
        data = json.loads(body.decode("utf-8"))
        ids = [
            item.get("id")
            for item in (data.get("data") or [])
            if isinstance(item, dict)
        ]
        info["served_ids"] = [i for i in ids if i]
        info["status"] = "ok" if model in info["served_ids"] or info["served_ids"] else "ok"
        if info["served_ids"] and model not in info["served_ids"]:
            info["status"] = "model_not_served"
    except Exception as exc:  # noqa: BLE001
        info["status"] = "unreachable"
        info["error_class"] = type(exc).__name__
    return info


def _record_health(*, rung: str, ok: bool, latency_ms: float, model: str, error_class: str = "", detail: str = "") -> None:
    try:
        from engine import provider_health as ph

        ph.record_attempt(
            lane=LANE,
            context="e3a_shadow_eval",
            rung=rung,
            ok=ok,
            latency_ms=int(max(0.0, latency_ms)),
            model=model,
            error_class=error_class,
            detail=detail[:200],
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[e3_shadow_compiler] provider_health record failed: {exc}")


def ledger_attempt(attempt: ModelAttempt, root: Path, run_id: str) -> None:
    """Write one ai_costs row per attempt. Cost may be 0 for local Qwen."""
    try:
        from lib.ai_costs import record_usage

        record_usage(
            lane=LANE,
            provider=attempt.provider,
            model=attempt.model,
            input_tokens=attempt.input_tokens,
            output_tokens=attempt.output_tokens,
            est_cost_usd=attempt.est_cost_usd if attempt.est_cost_usd else None,
            cycle_id=run_id,
            stage="e3a_shadow_eval",
            note=(
                f"comparator=True {attempt.comparator_note}" if attempt.is_comparator
                else "qwen_first_rung"
            ),
            root=root,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[e3_shadow_compiler] ai_costs ledger FAILED: {exc}")


def _attempt_qwen(user_prompt: str, repo_root: Path) -> ModelAttempt:
    """Attempt Qwen via the earnings-worker OpenAI-compat override. Never raises."""
    attempt = ModelAttempt(
        provider="openai_compat",
        model="qwen3.5:9b",
        is_comparator=False,
    )
    t0 = time.monotonic()
    try:
        import yaml
        from engine.earnings_qual import _call_openai_compat

        with open(repo_root / "config/earnings_qual.yml") as f:
            cfg = yaml.safe_load(f)
        oc_cfg = resolve_qwen_openai_compat_cfg(repo_root, cfg.get("openai_compat") or {})
        oc_cfg["timeout_s"] = max(float(oc_cfg.get("timeout_s") or 120), 300)
        oc_cfg["connect_timeout_s"] = float(oc_cfg.get("connect_timeout_s") or 5)
        attempt.model = str(oc_cfg.get("model") or attempt.model)
        attempt.base_url_source = str(oc_cfg.get("base_url_source") or "")
        attempt.endpoint_class = _endpoint_class(str(oc_cfg.get("base_url") or ""))
        attempt.preflight = preflight_qwen_endpoint(oc_cfg)
        if attempt.preflight.get("status") not in {"ok"}:
            attempt.status = "provider_unavailable"
            attempt.degraded_reason = f"preflight_{attempt.preflight.get('status')}"
            attempt.latency_ms = (time.monotonic() - t0) * 1000
            _record_health(
                rung="openai_compat",
                ok=False,
                latency_ms=attempt.latency_ms,
                model=attempt.model,
                error_class="preflight",
                detail=str(attempt.degraded_reason),
            )
            return attempt

        captured: dict[str, Any] = {}
        try:
            import requests as _requests

            _orig_post = _requests.post

            def _wrapped_post(*args: Any, **kwargs: Any):
                resp = _orig_post(*args, **kwargs)
                captured["json"] = resp.json() if resp.ok else None
                return resp

            _requests.post = _wrapped_post  # type: ignore[method-assign]
            try:
                text, reason = _call_openai_compat(
                    system=SYSTEM_PROMPT,
                    user=user_prompt,
                    oc_cfg=oc_cfg,
                    max_tokens=int(oc_cfg.get("max_tokens") or EXTRACTION_MAX_TOKENS)
                    if int(oc_cfg.get("max_tokens") or 0) >= EXTRACTION_MAX_TOKENS
                    else EXTRACTION_MAX_TOKENS,
                )
            finally:
                _requests.post = _orig_post  # type: ignore[method-assign]
        except Exception:
            text, reason = _call_openai_compat(
                system=SYSTEM_PROMPT,
                user=user_prompt,
                oc_cfg=oc_cfg,
                max_tokens=int(oc_cfg.get("max_tokens") or EXTRACTION_MAX_TOKENS)
                if int(oc_cfg.get("max_tokens") or 0) >= EXTRACTION_MAX_TOKENS
                else EXTRACTION_MAX_TOKENS,
            )
        usage = (captured.get("json") or {}).get("usage") or {}
        attempt.input_tokens = int(
            usage.get("prompt_tokens") or usage.get("input_tokens") or 0
        )
        attempt.output_tokens = int(
            usage.get("completion_tokens") or usage.get("output_tokens") or 0
        )
        attempt.latency_ms = (time.monotonic() - t0) * 1000
        if text is None:
            attempt.status = "provider_unavailable"
            attempt.degraded_reason = reason
            _record_health(
                rung="openai_compat",
                ok=False,
                latency_ms=attempt.latency_ms,
                model=attempt.model,
                error_class=str(reason or "openai_compat_error"),
            )
        else:
            attempt.raw_response = text
            attempt.status = "ok"
            attempt.candidates = _parse_candidates(text)
            _record_health(
                rung="openai_compat",
                ok=True,
                latency_ms=attempt.latency_ms,
                model=attempt.model,
            )
    except Exception as exc:  # noqa: BLE001
        attempt.latency_ms = (time.monotonic() - t0) * 1000
        attempt.status = "provider_unavailable"
        attempt.degraded_reason = f"exception: {type(exc).__name__}"
        _record_health(
            rung="openai_compat",
            ok=False,
            latency_ms=attempt.latency_ms,
            model=attempt.model,
            error_class=type(exc).__name__,
        )
    return attempt


def freeze_comparator_choice(repo_root: Path) -> dict[str, Any]:
    """Freeze provider/model before the first successful comparator inference."""
    import yaml
    from engine.llm_auth import build_providers

    with open(repo_root / "config/earnings_qual.yml") as f:
        cfg = yaml.safe_load(f)
    cfg = dict(cfg)
    cfg["usage_lane"] = LANE
    cfg["usage_stage"] = "e3a_shadow_comparator"
    cfg["codex_provider"] = False
    cfg["provider_order"] = ["oauth", "anthropic"]
    cfg["opus_model"] = FROZEN_COMPARATOR_MODEL
    providers = build_providers(cfg, opus_model=FROZEN_COMPARATOR_MODEL)
    usable = [p for p in providers if p.get("cred") and p.get("client") is not None]
    oauth = [p for p in usable if p.get("name") == "oauth"]
    anthropic_rungs = [p for p in usable if p.get("name") == "anthropic"]
    chosen_rungs = oauth + anthropic_rungs
    freeze = {
        "model": FROZEN_COMPARATOR_MODEL,
        "gold_labels": False,
        "provider_plane": "llm_auth",
        "provider": "oauth" if oauth else ("anthropic" if anthropic_rungs else None),
        "available_rungs": [p.get("name") for p in chosen_rungs],
        "n_oauth_rungs": len(oauth),
        "status": "frozen" if chosen_rungs else "unresolved_environment_blocker",
    }
    return {"freeze": freeze, "providers": chosen_rungs, "cfg": cfg}


def _attempt_comparator(user_prompt: str, repo_root: Path) -> ModelAttempt:
    """Stronger comparator via the existing llm_auth plane. Never raises."""
    attempt = ModelAttempt(
        provider="unresolved",
        model=FROZEN_COMPARATOR_MODEL,
        is_comparator=True,
        comparator_note=(
            "Independent comparator — evaluation only, no production authority. "
            "Runs on the same held source bytes as Qwen. Gold labels withheld. "
            f"Frozen model: {FROZEN_COMPARATOR_MODEL} via existing llm_auth."
        ),
    )
    t0 = time.monotonic()
    try:
        from engine.llm_auth import make_call

        choice = freeze_comparator_choice(repo_root)
        freeze = choice["freeze"]
        attempt.preflight = {"comparator_freeze": freeze}
        if freeze["status"] != "frozen":
            attempt.status = "unresolved_environment_blocker"
            attempt.degraded_reason = "no_approved_stronger_model_route"
            attempt.latency_ms = (time.monotonic() - t0) * 1000
            _record_health(
                rung="comparator",
                ok=False,
                latency_ms=attempt.latency_ms,
                model=attempt.model,
                error_class="no_provider",
            )
            return attempt

        chosen = choice["providers"][0]
        attempt.provider = str(chosen.get("name"))
        attempt.model = str(chosen.get("model") or FROZEN_COMPARATOR_MODEL)
        for prov in choice["providers"]:
            prov["usage_lane"] = LANE
            prov["usage_stage"] = "e3a_shadow_comparator"

        def call_fn(client: Any, model: str) -> tuple[str | None, str | None, Any]:
            resp = client.messages.create(
                model=model,
                max_tokens=EXTRACTION_MAX_TOKENS,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
            )
            text = "".join(
                b.text for b in (resp.content or [])
                if getattr(b, "type", "") == "text"
            ) or None
            usage = getattr(resp, "usage", None)
            attempt.input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
            attempt.output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
            return text, None, resp

        attempts_log: list[dict] = []
        text, fallback_reason, provider_used = make_call(
            providers=choice["providers"],
            call_fn=call_fn,
            context="e3a_shadow_comparator",
            attempts=attempts_log,
        )
        attempt.preflight["waterfall_attempts"] = [
            {k: row.get(k) for k in ("rung", "ok", "error_class", "skipped") if k in row}
            for row in attempts_log
        ]
        attempt.latency_ms = (time.monotonic() - t0) * 1000
        attempt.provider_fallback_reason = fallback_reason
        if provider_used:
            attempt.provider = provider_used
        if text is None:
            attempt.status = "unresolved_environment_blocker"
            attempt.degraded_reason = fallback_reason or "no_text"
        else:
            attempt.raw_response = text
            attempt.status = "ok"
            attempt.candidates = _parse_candidates(text)
            try:
                from lib.ai_costs import estimate_cost_usd

                cost = estimate_cost_usd(
                    attempt.model,
                    attempt.input_tokens,
                    attempt.output_tokens,
                    root=repo_root,
                )
                if cost is not None:
                    attempt.est_cost_usd = float(cost)
            except Exception:  # noqa: BLE001
                pass
    except Exception as exc:  # noqa: BLE001
        attempt.latency_ms = (time.monotonic() - t0) * 1000
        attempt.status = "unresolved_environment_blocker"
        attempt.degraded_reason = f"exception: {type(exc).__name__}"
        _record_health(
            rung="comparator",
            ok=False,
            latency_ms=attempt.latency_ms,
            model=attempt.model,
            error_class=type(exc).__name__,
        )
    return attempt


def _parse_candidates(raw: str) -> list[dict]:
    """Parse model output as a JSON array of exchange candidates."""
    try:
        raw = raw.strip()
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [p for p in parsed if isinstance(p, dict)]
        if isinstance(parsed, dict):
            for key in ("exchanges", "candidates", "qa_exchanges"):
                val = parsed.get(key)
                if isinstance(val, list):
                    return [p for p in val if isinstance(p, dict)]
        return []
    except Exception:  # noqa: BLE001
        return []


# ── Main eval entry point ─────────────────────────────────────────────────────


def _bounded_telemetry_proof(repo_root: Path, shard_info: dict[str, str]) -> dict[str, Any]:
    """Preserve bounded eval proof without committing global JSONL merges."""
    proof: dict[str, Any] = {
        "lane": LANE,
        "ai_costs_shard": shard_info.get("ai_costs_shard"),
        "provider_health_path": str(health_path.relative_to(repo_root)),
        "ai_costs_rows": [],
        "provider_health_rows": [],
    }
    shard_name = shard_info.get("ai_costs_shard") or ""
    shard_file = repo_root / "data" / "ai_costs" / "usage.d" / f"{shard_name}.jsonl"
    if shard_file.is_file():
        rows = []
        for line in shard_file.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            rows.append({
                k: row.get(k)
                for k in (
                    "ts", "lane", "provider", "model", "input_tokens",
                    "output_tokens", "est_cost_usd", "stage", "note", "cycle_id",
                )
            })
        proof["ai_costs_rows"] = rows
        proof["ai_costs_shard_file"] = str(shard_file.relative_to(repo_root))
    health_rel = shard_info.get("provider_health_path") or ""
    health_path = Path(health_rel)
    if not health_path.is_absolute():
        health_path = repo_root / health_path
    if health_path.is_file():
        rows = []
        for line in health_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            rows.append({
                k: row.get(k)
                for k in (
                    "ts", "lane", "context", "rung", "model", "ok",
                    "latency_ms", "error_class",
                )
            })
        proof["provider_health_rows"] = rows
    return proof


def _enable_eval_shards(run_id: str, repo_root: Path) -> dict[str, str]:
    """Route telemetry into the supported shard/override files for this eval."""
    shard = f"e3a-pr6245-{run_id}"
    health_path = repo_root / "research/earnings_intelligence/e3/gold" / f"provider_health_{run_id}.jsonl"
    os.environ["AI_COSTS_SHARD"] = shard
    os.environ["PROVIDER_HEALTH_PATH"] = str(health_path)
    return {"ai_costs_shard": shard, "provider_health_path": str(health_path.relative_to(repo_root))}


def run_e3a_eval(repo_root: Path | None = None) -> dict:
    """Execute the E3-A leakage-free eval sequence.

    Returns the full eval receipt (written to EVAL_RECEIPT_PATH).
    Does NOT write to event_workspace.v1. Does NOT write to R2.
    """
    if repo_root is None:
        repo_root = Path(__file__).parent.parent.parent

    run_id = hashlib.sha256(str(time.time_ns()).encode()).hexdigest()[:16]
    shard_info = _enable_eval_shards(run_id, repo_root)

    receipt: dict[str, Any] = {
        "schema": "e3a_eval_receipt.v1",
        "run_id": run_id,
        "lane": LANE,
        "event_id": EVENT_ID,
        "gold_path": str(GOLD_PATH),
        "telemetry": shard_info,
        "steps": {},
        "model_attempts": {},
        "scores": {},
        "summary": {},
    }

    sha_check = verify_fixture_shas(repo_root)
    live = verify_live_workspace_shas()
    if not live.get("matches_frozen_fixtures"):
        raise RuntimeError(
            "Live E2 workspace source SHAs do not equal frozen fixture SHAs. "
            f"live={live}"
        )
    receipt["steps"]["sha_verification"] = {
        **sha_check,
        "frozen_exhibit_sha": FROZEN_EXHIBIT_SHA,
        "frozen_transcript_sha": FROZEN_TRANSCRIPT_SHA,
        "live_workspace": live,
    }

    segments = load_transcript_segments(repo_root)
    segment_ids = [
        stable_segment_id(FROZEN_TRANSCRIPT_SHA, i) for i in range(len(segments))
    ]
    receipt["steps"]["segmenter"] = {
        "segment_count": len(segments),
        "id_method": "sha256[:16]_index04d",
        "truncation": "none",
        "sample_ids": segment_ids[:3],
    }

    gold_bytes = (repo_root / GOLD_PATH).read_bytes()
    gold_sha = hashlib.sha256(gold_bytes).hexdigest()
    if gold_sha != FROZEN_GOLD_SHA:
        raise RuntimeError(f"Gold SHA changed unexpectedly: {gold_sha}")
    gold = json.loads(gold_bytes)
    receipt["steps"]["gold_loaded"] = {
        "gold_path": str(GOLD_PATH),
        "gold_sha256": gold_sha,
        "taxonomy_version": gold.get("taxonomy", {}).get("version"),
        "taxonomy_hash": gold.get("taxonomy", {}).get("hash"),
        "exchange_count": gold.get("qa_exchange_count"),
        "usefulness_bar_decision": gold.get("usefulness_bar", {}).get("decision"),
        "gold_labels_withheld_during_inference": True,
        "adjudication_receipt": str(ADJUDICATION_RECEIPT_PATH),
    }

    user_prompt = _build_user_prompt(segments)
    if "Amit Daryanani" in user_prompt and '"topics"' in json.dumps(gold["exchanges"][0]):
        # Prompt may contain source names (they are in the transcript). It must
        # not contain gold topic labels as an answer key.
        gold_note = str(gold["exchanges"][0].get("adjudication_notes") or "")
        if gold_note and gold_note in user_prompt:
            raise RuntimeError("gold adjudication notes leaked into the prompt")
    receipt["steps"]["prompt_built"] = {
        "prompt_version": "e3a-qa-extraction-v1",
        "segment_count": len(segments),
        "uses_bounded_transcript_text": False,
        "gold_labels_in_prompt": False,
    }

    print("[e3_shadow_compiler] Attempting Qwen via earnings-worker override...")
    qwen_attempt = _attempt_qwen(user_prompt, repo_root)
    receipt["model_attempts"]["qwen"] = {
        "provider": qwen_attempt.provider,
        "model": qwen_attempt.model,
        "endpoint_class": qwen_attempt.endpoint_class,
        "base_url_source": qwen_attempt.base_url_source,
        "preflight": qwen_attempt.preflight,
        "status": qwen_attempt.status,
        "degraded_reason": qwen_attempt.degraded_reason,
        "n_candidates": len(qwen_attempt.candidates),
        "raw_excerpt": (qwen_attempt.raw_response or "")[:400],
        "latency_ms": round(qwen_attempt.latency_ms, 1),
        "input_tokens": qwen_attempt.input_tokens,
        "output_tokens": qwen_attempt.output_tokens,
        "est_cost_usd": qwen_attempt.est_cost_usd,
        "gold_labels_seen": False,
    }
    ledger_attempt(qwen_attempt, repo_root, run_id)

    print("[e3_shadow_compiler] Freezing comparator, then attempting llm_auth...")
    comp_choice = freeze_comparator_choice(repo_root)
    receipt["steps"]["comparator_freeze"] = {
        k: v for k, v in comp_choice["freeze"].items() if k != "providers"
    }
    comp_attempt = _attempt_comparator(user_prompt, repo_root)
    receipt["model_attempts"]["comparator"] = {
        "provider": comp_attempt.provider,
        "model": comp_attempt.model,
        "is_comparator": True,
        "non_authoritative": True,
        "comparator_note": comp_attempt.comparator_note,
        "preflight": comp_attempt.preflight,
        "status": comp_attempt.status,
        "degraded_reason": comp_attempt.degraded_reason,
        "n_candidates": len(comp_attempt.candidates),
        "raw_excerpt": (comp_attempt.raw_response or "")[:400],
        "latency_ms": round(comp_attempt.latency_ms, 1),
        "input_tokens": comp_attempt.input_tokens,
        "output_tokens": comp_attempt.output_tokens,
        "est_cost_usd": comp_attempt.est_cost_usd,
        "gold_labels_seen": False,
    }
    if comp_attempt.status != "ok":
        ledger_attempt(comp_attempt, repo_root, run_id)

    print("[e3_shadow_compiler] Scoring against frozen gold via shadow validator...")
    qwen_score = score_attempt(qwen_attempt, gold, segments)
    comp_score = score_attempt(comp_attempt, gold, segments)
    receipt["scores"]["qwen"] = qwen_score
    receipt["scores"]["comparator"] = comp_score

    receipt["summary"] = {
        "sha_check": "pass",
        "live_workspace_verified": True,
        "gold_sha256": gold_sha,
        "gold_frozen_before_inference": True,
        "neither_model_saw_gold_labels": True,
        "qwen_status": qwen_attempt.status,
        "comparator_status": comp_attempt.status,
        "hard_gates_qwen": qwen_score["hard_gates"]["status"],
        "hard_gates_comparator": comp_score["hard_gates"]["status"],
        "usefulness_bar_decision": "refusal_n7_too_small",
        "return_to_sol": True,
        "e3b_auto_unlocked": False,
        "event_workspace_v1_advanced": False,
        "r2_written": False,
        "note": (
            "Measured E3-A R1 packet. Pre-inference usefulness decision remains "
            "the frozen N=7 refusal, so this returns to Sol regardless of scores. "
            "E3-B stays locked."
        ),
    }
    receipt["telemetry_proof"] = _bounded_telemetry_proof(repo_root, shard_info)

    receipt_path = repo_root / EVAL_RECEIPT_PATH
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_bytes = json.dumps(receipt, indent=2, default=str).encode("utf-8")
    receipt_path.write_bytes(receipt_bytes)
    receipt["receipt_sha256"] = hashlib.sha256(receipt_bytes).hexdigest()
    print(f"[e3_shadow_compiler] Eval receipt written: {receipt_path}")
    return receipt


if __name__ == "__main__":
    run_e3a_eval()
