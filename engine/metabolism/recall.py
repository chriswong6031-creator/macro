"""engine.metabolism.recall — Relevance-ranked lesson recall (R-V3-2).

Kills the byte-tail approach in orchestrator_brain._load_recent_lessons() by
scoring every row in lessons.jsonl and returning the highest-relevance rows
up to a byte budget — never chopping a high-scored row mid-way.

Scoring is deterministic token-overlap (no embeddings, no vector DB).  The
corpus is tiny (~hundreds of rows); exhaustive linear scan is correct here.

All functions are NEVER-RAISE and return safe fallbacks on any error.
No LLM calls, no network, no reads from ~/. Deterministic.
"""
from __future__ import annotations

import json
import logging
import re
import string
from collections import Counter
from pathlib import Path

log = logging.getLogger(__name__)

LESSONS_PATH = ("data", "metabolism", "lessons.jsonl")

# Sentinel returned by recall_lessons when the lesson corpus is absent or empty.
# Callers should compare against this constant rather than using fragile startswith('(')
# pattern matching (FIX-6 / R-V8-12).
LESSONS_ABSENT_SENTINEL = "(lessons.jsonl not yet present — accruing)"

# Score weights
_WEIGHT_LOBE_MATCH = 4.0            # strong: lobe keyword found anywhere in row
_WEIGHT_CONSTRUCTION_JACCARD = 3.0  # token-overlap on construction field only
_WEIGHT_FAIL_VERDICT = 2.0          # FAIL/kill/reject verdicts weighted higher (anti-repetition signal)
_WEIGHT_RECENCY = 0.5               # small tiebreak only (newer is marginally preferred)

# Max possible non-FAIL score: lobe(4.0) + construction_jaccard(3.0) + sensor(1.0) + recency(0.5) = 8.5
# The dominating FAIL floor must exceed this.
_FAIL_FLOOR_BONUS = 20.0            # added when FAIL row's construction matches query (Jaccard >= 0.5)
_FAIL_CONSTRUCTION_MATCH_THRESHOLD = 0.5  # Jaccard threshold for "same construction"

# Stopwords to drop during fingerprinting and scoring
_STOPWORDS = frozenset({
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "was", "are", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "shall", "can", "not", "no", "nor",
    "so", "yet", "both", "either", "neither", "as", "if", "than", "then",
    "that", "this", "these", "those", "it", "its", "we", "i", "you", "he",
    "she", "they", "them", "their", "our", "my", "your", "vs", "via",
})

_PUNCT_TABLE = str.maketrans("", "", string.punctuation)


def _repo_root(root: Path | None = None) -> Path:
    if root is not None:
        return Path(root)
    return Path(__file__).resolve().parent.parent.parent


def _tokenize(text: str) -> list[str]:
    """Lowercase, strip punctuation, split on whitespace, drop stopwords."""
    cleaned = text.lower().translate(_PUNCT_TABLE)
    return [t for t in cleaned.split() if t and t not in _STOPWORDS]


def fingerprint_construction(text: str) -> str:
    """Return a stable, order-insensitive fingerprint of a construction description.

    Lowercase, strip punctuation, drop stopwords, sort the significant tokens,
    join with spaces.  Deterministic and order-insensitive:
      "A vs B momentum" and "momentum B A" → same fingerprint.

    Empty input → "".
    NEVER-RAISE.
    """
    try:
        if not text or not text.strip():
            return ""
        tokens = _tokenize(text)
        return " ".join(sorted(set(tokens)))
    except Exception as exc:  # noqa: BLE001
        log.warning("recall.fingerprint_construction: %s", exc)
        return ""


def _jaccard(set_a: frozenset[str], set_b: frozenset[str]) -> float:
    """Jaccard similarity between two token sets.  Returns 0.0 if both empty."""
    if not set_a and not set_b:
        return 0.0
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union else 0.0


_FAIL_TOKENS: frozenset[str] = frozenset({
    "fail", "failed", "kill", "killed", "reject", "rejected", "dead", "false",
})


def is_fail_verdict(verdict: str) -> bool:
    """Return True for FAIL/kill/reject-class verdicts.

    Tokenizes the verdict string and tests set-membership against an exact
    fail-token set.  This avoids substring false-fires such as "no" matching
    inside "NONE", "normal", or "PASS (no issues)".
    """
    tokens = frozenset(_tokenize(verdict))
    return bool(tokens & _FAIL_TOKENS)


# Back-compat alias — kept so any callers of the private name still work.
_is_fail_verdict = is_fail_verdict


def _score_row(
    row: dict,
    *,
    lobe_tokens: frozenset[str],
    construction_tokens: frozenset[str],
    sensor_tokens: frozenset[str],
    newest_ts: str,
    oldest_ts: str,
) -> tuple[float, list[str]]:
    """Score a single lesson row.  Returns (score, reasons)."""
    score = 0.0
    reasons: list[str] = []

    # Combine all text fields for lobe-match and sensor searches (broad bag)
    row_text_fields_broad = [
        str(row.get("construction") or ""),
        str(row.get("what_worked") or ""),
        str(row.get("what_failed") or ""),
        str(row.get("proposal_id") or ""),
        str(row.get("cycle_id") or ""),
    ]
    row_all_tokens = frozenset(_tokenize(" ".join(row_text_fields_broad)))

    # Construction-only tokens (used for Jaccard — must NOT pool what_* so long
    # what_failed prose doesn't inflate the union and drive FAIL rows DOWN)
    row_construction_tokens = frozenset(_tokenize(str(row.get("construction") or "")))

    # 1. Lobe match — prefer exact row["lobe"] match (new structured field from BUG 3 fix);
    #    fall back to broad-bag text-overlap so old rows without the field still score.
    if lobe_tokens:
        row_lobe_str = str(row.get("lobe") or "").strip()
        row_lobe_tokens = frozenset(_tokenize(row_lobe_str)) if row_lobe_str else frozenset()
        if lobe_tokens and row_lobe_tokens and lobe_tokens == row_lobe_tokens:
            # Exact lobe field match — strong signal
            score += _WEIGHT_LOBE_MATCH
            reasons.append(f"lobe_exact:{row_lobe_str}")
        else:
            # Fall back to broad-bag overlap (works for old rows without lobe field
            # and for partial matches where lobe keyword appears in text fields)
            overlap = lobe_tokens & row_all_tokens
            if overlap:
                score += _WEIGHT_LOBE_MATCH
                reasons.append(f"lobe_match:{','.join(sorted(overlap))}")

    # 2. Construction-token overlap (Jaccard on construction field ONLY — B1a fix)
    construction_jaccard = 0.0
    if construction_tokens:
        construction_jaccard = _jaccard(construction_tokens, row_construction_tokens)
        if construction_jaccard > 0:
            weighted = construction_jaccard * _WEIGHT_CONSTRUCTION_JACCARD
            score += weighted
            reasons.append(f"construction_jaccard:{construction_jaccard:.3f}")

    # 3. Sensor match bonus (small, helps filter when sensors provided)
    if sensor_tokens:
        s_overlap = sensor_tokens & row_all_tokens
        if s_overlap:
            score += 1.0
            reasons.append(f"sensor_match:{','.join(sorted(s_overlap))}")

    # 4. FAIL verdict weight — critical for anti-repetition
    verdict = str(row.get("verdict") or "")
    if _is_fail_verdict(verdict):
        # B1b: hard FAIL floor — when this FAIL row's construction matches the
        # query (Jaccard >= threshold), add a dominating bonus that provably
        # exceeds the maximum possible non-FAIL score (8.5).  An unrelated FAIL
        # (construction does NOT match) gets only the normal small weight so it
        # does not flood out relevant PASS rows.
        if construction_tokens and construction_jaccard >= _FAIL_CONSTRUCTION_MATCH_THRESHOLD:
            score += _FAIL_FLOOR_BONUS
            reasons.append(f"fail_floor_bonus:{_FAIL_FLOOR_BONUS}")
        else:
            score += _WEIGHT_FAIL_VERDICT
        reasons.append(f"fail_verdict:{verdict}")

    # 5. Recency tiebreak: normalize ts position in [oldest, newest] range
    ts = str(row.get("ts") or "")
    if ts and newest_ts and oldest_ts and newest_ts != oldest_ts:
        # Lexicographic ISO8601 comparison is valid for recency ordering
        ts_range = newest_ts > oldest_ts  # always True after sort
        if ts_range:
            # Map ts into [0, 1] by position within the observed range
            # Since strings are ISO8601 they compare correctly lexicographically
            if ts >= newest_ts:
                normalized = 1.0
            elif ts <= oldest_ts:
                normalized = 0.0
            else:
                # Middle range: assign a flat 0.5 tiebreak weight.
                # ISO 8601 strings sort correctly lexicographically, but
                # linear interpolation on strings is not implemented here —
                # recency is intentionally a small tiebreak (0–0.5 pts total),
                # not a precise normalization.
                normalized = 0.5
            score += normalized * _WEIGHT_RECENCY
            if normalized > 0:
                reasons.append(f"recency:{normalized:.2f}")

    return score, reasons


def recall_lesson_rows(
    *,
    lobe: str | None = None,
    construction_terms: str | list[str] | None = None,
    sensors: list[str] | None = None,
    k: int = 12,
    root: Path | None = None,
) -> list[dict]:
    """Load lessons.jsonl, score each row, return top-k rows augmented with _score/_reasons.

    Scoring:
      - lobe match (strong weight)
      - construction-token Jaccard overlap (medium weight)
      - FAIL/kill/reject verdicts weighted HIGHER (anti-repetition signal)
      - recency as small tiebreak only

    Returns [] when lessons.jsonl absent.  NEVER-RAISE.
    """
    try:
        repo = _repo_root(root)
        p = repo.joinpath(*LESSONS_PATH)
        if not p.exists():
            return []

        # Build query token sets
        lobe_tokens: frozenset[str] = frozenset()
        if lobe:
            lobe_tokens = frozenset(_tokenize(lobe))

        construction_tokens: frozenset[str] = frozenset()
        if construction_terms is not None:
            if isinstance(construction_terms, list):
                combined = " ".join(str(t) for t in construction_terms)
            else:
                combined = str(construction_terms)
            construction_tokens = frozenset(_tokenize(combined))

        sensor_tokens: frozenset[str] = frozenset()
        if sensors:
            sensor_tokens = frozenset(_tokenize(" ".join(str(s) for s in sensors)))

        # Load rows
        rows: list[dict] = []
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
                if not isinstance(r, dict):
                    continue
                # Skip summary blocks (anti-rot compressed entries)
                if r.get("is_summary"):
                    continue
                rows.append(r)
            except Exception:  # noqa: BLE001
                continue

        if not rows:
            return []

        # Determine timestamp bounds for recency normalization
        all_ts = sorted(str(r.get("ts") or "") for r in rows if r.get("ts"))
        newest_ts = all_ts[-1] if all_ts else ""
        oldest_ts = all_ts[0] if all_ts else ""

        # Score all rows
        scored: list[tuple[float, int, dict]] = []
        for idx, row in enumerate(rows):
            s, reasons = _score_row(
                row,
                lobe_tokens=lobe_tokens,
                construction_tokens=construction_tokens,
                sensor_tokens=sensor_tokens,
                newest_ts=newest_ts,
                oldest_ts=oldest_ts,
            )
            augmented = dict(row)
            augmented["_score"] = s
            augmented["_reasons"] = reasons
            scored.append((s, idx, augmented))

        # Sort descending by score, then by original index (stable)
        scored.sort(key=lambda x: (-x[0], x[1]))

        return [item[2] for item in scored[:k]]

    except Exception as exc:  # noqa: BLE001
        log.warning("recall.recall_lesson_rows: %s", exc)
        return []


def recall_lessons(
    *,
    lobe: str | None = None,
    construction_terms: str | list[str] | None = None,
    sensors: list[str] | None = None,
    byte_budget: int = 2000,
    root: Path | None = None,
) -> str:
    """Return the highest-relevance lessons as compact text, packed to byte_budget.

    Rows are formatted as compact JSON lines.  The top-scored row is ALWAYS kept
    whole even if it alone exceeds byte_budget (G5 fix: never chop mid-row).
    Remaining rows are added highest-score-first until the budget would be exceeded.

    Returns the canonical absence string when lessons.jsonl is missing.
    NEVER-RAISE.
    """
    try:
        repo = _repo_root(root)
        p = repo.joinpath(*LESSONS_PATH)
        if not p.exists():
            return LESSONS_ABSENT_SENTINEL

        top_rows = recall_lesson_rows(
            lobe=lobe,
            construction_terms=construction_terms,
            sensors=sensors,
            k=50,  # over-fetch; budget packing will trim
            root=root,
        )

        if not top_rows:
            return LESSONS_ABSENT_SENTINEL

        def _fmt(row: dict) -> str:
            # Compact format: drop internal scoring fields for the prompt
            out = {k: v for k, v in row.items() if not k.startswith("_")}
            return json.dumps(out, separators=(",", ":"), default=str)

        lines: list[str] = []
        used_bytes = 0

        for i, row in enumerate(top_rows):
            line = _fmt(row)
            line_bytes = len(line.encode())

            if i == 0:
                # Always keep the top-scored row whole (G5 fix)
                lines.append(line)
                used_bytes += line_bytes + 1  # +1 for newline
            else:
                if used_bytes + line_bytes + 1 > byte_budget:
                    break
                lines.append(line)
                used_bytes += line_bytes + 1

        return "\n".join(lines)

    except Exception as exc:  # noqa: BLE001
        log.warning("recall.recall_lessons: %s", exc)
        return "(lessons unavailable)"
