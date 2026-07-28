"""engine.marketing.golden_set — labels, labeling batches, precision@20 (XG-W5).

The masterplan's IS-W2 gate names a 200-item golden set (garbage / useful /
post-worthy / viral-grade) and requires the scorer's precision@20 to beat the
current salience-only ordering on it. THE LABELS ARE AN OPERATOR/FABLE LEVER, so
this wave ships the machinery and the honest empty state — never a fake green:

    * the label-store SCHEMA + validator                    (here)
    * the candidate-batch EXPORTER (stratified, deterministic)  (here)
    * the EVAL HARNESS: precision@k for rank_score ordering vs salience ordering,
      over whatever labels exist                             (here)

With zero labels the harness reports ``state="no-labels"`` and a null precision.
It never invents a number, never reports 0.0 as if it were measured, and never
returns "pass".

WHERE THE CORPUS LIVES. The ingested press corpus is RUNTIME-ONLY: the press
daemon writes ``data/marketing/press/ingest_corpus.jsonl`` on the VPS, and
``data/marketing/press/`` is gitignored (house law: pollers make zero git
writes). There is therefore NO ingested-corpus snapshot in the repo to sample
from — a labeling batch is exported ON THE HOST and carried back by the
operator. The exact command is in docs/scoring_brain.md §2; the repo-side
fallback (``data/marketing/outbox/items.jsonl``) is EMITTED items only, which is
a survivorship-biased sample of the very ordering under test, so it is offered
only as a last resort and is labeled as such in the export report.

Label vocabulary (masterplan §0 IS-W2, verbatim):
    garbage       should never have entered the pipeline
    useful        real information, not worth a post on its own
    post_worthy   worth an X post
    viral_grade   worth a prime slot

The POSITIVE CLASS for precision@k is {post_worthy, viral_grade} — "did the top
k of the ranking deserve the scarce slots", which is exactly what the top-K/day
flagship counter spends.

NO LLM. Labels come from humans; the harness does arithmetic.

Public API:
    LABELS, POSITIVE_LABELS
    validate_label_row(row) -> list[str]
    load_labels(root=None, *, path=None) -> dict[item_id, row]
    read_corpus(paths) -> list[dict]
    export_batch(rows, *, n=200, labeled=None, seed=..., now=None, cfg=None) -> dict
    precision_at_k(ordered_rows, labels, *, k=20) -> dict
    evaluate(rows, labels, *, k=20, cfg=None) -> dict
    format_report(report) -> str
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

LABELS: tuple[str, ...] = ("garbage", "useful", "post_worthy", "viral_grade")
LABEL_RANK: dict[str, int] = {name: i for i, name in enumerate(LABELS)}
POSITIVE_LABELS: frozenset[str] = frozenset({"post_worthy", "viral_grade"})

LABEL_SCHEMA = "golden.v1"
CORPUS_SCHEMA = "press_corpus.v1"

# The committed label store. OPERATOR/FABLE-AUTHORED: no engine path writes it —
# the labeling CLI writes it from a human session and the rows are committed like
# config/reply_targets.yml. It is not a forward ledger and the nightly does not
# advance it.
DEFAULT_LABEL_PATH = "data/marketing/golden_set/labels.jsonl"

# Where the runtime corpus lives, most-authoritative first.
DEFAULT_CORPUS_PATHS: tuple[str, ...] = (
    "data/marketing/press/ingest_corpus.jsonl",
)

# Minimum labeled rows before the precision@k comparison is reported as a
# comparison at all. Below it the harness says "insufficient" and prints the n.
DEFAULT_MIN_LABELED = 40


# ─────────────────────────────────────────────────────────────────────────────
# Label store
# ─────────────────────────────────────────────────────────────────────────────

def validate_label_row(row: object) -> list[str]:
    """Schema errors for one label row; [] when valid."""
    errors: list[str] = []
    if not isinstance(row, dict):
        return ["row is not an object"]
    if str(row.get("schema", LABEL_SCHEMA)) != LABEL_SCHEMA:
        errors.append(f"schema must be {LABEL_SCHEMA!r}")
    if not str(row.get("item_id", "")).strip():
        errors.append("item_id is required")
    label = str(row.get("label", ""))
    if label not in LABELS:
        errors.append(f"label must be one of {LABELS!r} (got {label!r})")
    labeler = str(row.get("labeler", "")).strip()
    if not labeler:
        errors.append("labeler is required (who made this call)")
    labeled_at = str(row.get("labeled_at", "")).strip()
    if labeled_at:
        try:
            datetime.fromisoformat(labeled_at.replace("Z", "+00:00"))
        except ValueError:
            errors.append("labeled_at must be ISO-8601")
    return errors


def make_label_row(item_id: str, label: str, *, labeler: str,
                   now: datetime | None = None, notes: str = "",
                   headline: str = "", source: str = "",
                   batch_id: str = "") -> dict:
    """Build a schema-valid label row (the CLI's row constructor)."""
    now = now or datetime.now(tz=timezone.utc)
    return {
        "schema": LABEL_SCHEMA,
        "item_id": str(item_id),
        "label": str(label),
        "labeler": str(labeler),
        "labeled_at": now.astimezone(timezone.utc).isoformat(),
        "batch_id": str(batch_id),
        "headline": str(headline)[:200],
        "source": str(source),
        "notes": str(notes)[:500],
    }


def load_labels(root: Path | str | None = None, *,
                path: Path | str | None = None) -> dict[str, dict]:
    """Load the label store as {item_id: row}. Last row for an id wins.

    A malformed row is SKIPPED WITH A START-OF-LINE WARNING rather than silently
    dropped — a golden set that quietly loses labels is worse than one that is
    loud about it.
    """
    target = Path(path) if path else Path(root or ".") / DEFAULT_LABEL_PATH
    if not target.exists():
        return {}
    out: dict[str, dict] = {}
    for lineno, line in enumerate(target.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            print(f"::warning title=golden-set-bad-row::{target}:{lineno}: {exc}",
                  flush=True)
            continue
        errors = validate_label_row(row)
        if errors:
            print(f"::warning title=golden-set-bad-row::{target}:{lineno}: "
                  f"{errors[0]}", flush=True)
            continue
        out[str(row["item_id"])] = row
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Corpus
# ─────────────────────────────────────────────────────────────────────────────

def read_corpus(paths: Iterable[Path | str]) -> list[dict]:
    """Read JSONL corpus rows from the first path that exists and parses."""
    rows: list[dict] = []
    for raw in paths:
        target = Path(raw)
        if not target.exists():
            continue
        for line in target.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict) and row.get("item_id"):
                rows.append(row)
        if rows:
            break
    return rows


def corpus_paths(root: Path | str | None = None, *,
                 cfg: dict | None = None) -> list[Path]:
    """Configured corpus paths, absolutized against `root`."""
    raw = (cfg or {}).get("corpus_paths") or DEFAULT_CORPUS_PATHS
    base = Path(root or ".")
    out = []
    for entry in raw:
        path = Path(entry)
        out.append(path if path.is_absolute() else base / path)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Candidate batch export
# ─────────────────────────────────────────────────────────────────────────────

def _stratum(row: dict) -> str:
    """Sampling stratum: (outcome family, source tier, salience band).

    A batch drawn purely at random over a wire corpus is ~all low-salience
    aggregator noise, and a batch drawn from the top of the ranking only
    measures the ranking's own opinion of itself. Stratifying across outcome and
    salience band is what makes the labeled set informative about BOTH the
    garbage gate and the ordering.
    """
    outcome = str(row.get("outcome", "")).split(":", 1)[0] or "scored"
    tier = str(row.get("source_tier", "") or "unknown")
    try:
        salience = float(row.get("salience") or 0.0)
    except (TypeError, ValueError):
        salience = 0.0
    if salience >= 70:
        band = "high"
    elif salience >= 40:
        band = "mid"
    else:
        band = "low"
    return f"{outcome}|{tier}|{band}"


def _stable_rank(item_id: str, seed: str) -> str:
    return hashlib.sha1(f"{seed}|{item_id}".encode("utf-8")).hexdigest()


def export_batch(rows: Sequence[dict], *, n: int = 200,
                 labeled: Iterable[str] | None = None,
                 seed: str = "xg-w5", now: datetime | None = None,
                 cfg: dict | None = None) -> dict:
    """Assemble a labeling batch of up to `n` rows, stratified and deterministic.

    Deterministic: selection is a stable hash of (seed, item_id), so re-running
    the export over the same corpus yields the SAME batch — a labeling session
    interrupted halfway can be resumed without re-sampling, and an eval can name
    the exact batch it graded.

    Already-labeled ids are excluded, so successive batches extend the golden set
    instead of re-asking the same questions.
    """
    now = now or datetime.now(tz=timezone.utc)
    done = {str(x) for x in (labeled or ())}
    pool = [r for r in rows if str(r.get("item_id", "")) and str(r["item_id"]) not in done]

    buckets: dict[str, list[dict]] = {}
    for row in pool:
        buckets.setdefault(_stratum(row), []).append(row)
    for key in buckets:
        buckets[key].sort(key=lambda r: _stable_rank(str(r["item_id"]), seed))

    # Round-robin across strata so no single stratum can swamp the batch.
    selected: list[dict] = []
    order = sorted(buckets)
    cursor = {key: 0 for key in order}
    while len(selected) < n:
        progressed = False
        for key in order:
            if len(selected) >= n:
                break
            idx = cursor[key]
            if idx < len(buckets[key]):
                selected.append(buckets[key][idx])
                cursor[key] = idx + 1
                progressed = True
        if not progressed:
            break

    batch_id = "gb-" + hashlib.sha1(
        f"{seed}|{now.astimezone(timezone.utc).strftime('%Y-%m-%d')}|{len(selected)}"
        .encode("utf-8")
    ).hexdigest()[:12]

    items = [{
        "batch_id": batch_id,
        "item_id": str(r.get("item_id", "")),
        "headline": str(r.get("headline", "")),
        "body_snippet": str(r.get("body_snippet", ""))[:300],
        "url": str(r.get("url", "")),
        "source": str(r.get("source", "")),
        "source_name": str(r.get("source_name", "")),
        "source_tier": str(r.get("source_tier", "")),
        "published_at": str(r.get("published_at", "")),
        "event_class": str(r.get("event_class", "")),
        "outcome": str(r.get("outcome", "")),
        "stratum": _stratum(r),
        # The engine's own numbers travel with the row so a labeler can see them,
        # but the LABEL is the human's call — they are printed, never proposed.
        "salience": r.get("salience"),
        "rank_score": r.get("rank_score"),
        "label": "",
    } for r in selected]

    return {
        "batch_id": batch_id,
        "created_at": now.astimezone(timezone.utc).isoformat(),
        "seed": seed,
        "requested": int(n),
        "returned": len(items),
        "corpus_rows": len(rows),
        "already_labeled": len(done),
        "strata": {key: len(value) for key, value in sorted(buckets.items())},
        "items": items,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Evaluation
# ─────────────────────────────────────────────────────────────────────────────

def _sort_key(field: str):
    def _key(row: dict) -> tuple[float, str]:
        try:
            value = float(row.get(field) or 0.0)
        except (TypeError, ValueError):
            value = 0.0
        # item_id as the tiebreak keeps the ordering total and reproducible.
        return (value, str(row.get("item_id", "")))
    return _key


def precision_at_k(ordered_rows: Sequence[dict], labels: dict[str, dict], *,
                   k: int = 20) -> dict:
    """precision@k over the labeled subset of an ordering.

    ONLY LABELED ROWS COUNT, in both numerator and denominator: an unlabeled row
    is not evidence either way, and silently treating it as a negative would
    manufacture a number out of missing data. `k_effective` reports how many
    labeled rows the top-k actually contained.
    """
    considered: list[str] = []
    for row in ordered_rows:
        item_id = str(row.get("item_id", ""))
        if item_id in labels:
            considered.append(item_id)
        if len(considered) >= k:
            break
    if not considered:
        return {"precision": None, "k_effective": 0, "hits": 0}
    hits = sum(1 for i in considered if labels[i].get("label") in POSITIVE_LABELS)
    return {
        "precision": round(hits / len(considered), 6),
        "k_effective": len(considered),
        "hits": hits,
    }


def evaluate(rows: Sequence[dict], labels: dict[str, dict], *, k: int = 20,
             cfg: dict | None = None) -> dict:
    """Compare the XG-W5 rank ordering against the incumbent salience ordering.

    Returns a report whose `state` is one of:
        "no-labels"    zero labeled rows intersect the corpus — precision is
                       UNDEFINED, not zero. The comparison becomes binding when
                       labels exist; until then this is the honest answer.
        "insufficient" fewer than `min_labeled` labeled rows — the numbers are
                       printed but must not gate anything.
        "ok"           enough labels for the comparison the masterplan names.
    `beats_salience` is None in the first two states — never a fabricated pass.
    """
    min_labeled = int((cfg or {}).get("min_labeled", DEFAULT_MIN_LABELED))
    usable = [r for r in rows if str(r.get("item_id", ""))]
    labeled_ids = {r["item_id"] for r in usable if str(r["item_id"]) in labels}

    by_rank = sorted(usable, key=_sort_key("rank_score"), reverse=True)
    by_salience = sorted(usable, key=_sort_key("salience"), reverse=True)
    rank_result = precision_at_k(by_rank, labels, k=k)
    salience_result = precision_at_k(by_salience, labels, k=k)

    label_counts: dict[str, int] = {name: 0 for name in LABELS}
    for item_id in labeled_ids:
        name = str(labels[item_id].get("label", ""))
        if name in label_counts:
            label_counts[name] += 1

    if not labeled_ids:
        state = "no-labels"
    elif len(labeled_ids) < min_labeled:
        state = "insufficient"
    else:
        state = "ok"

    delta = None
    beats = None
    if state == "ok" and rank_result["precision"] is not None \
            and salience_result["precision"] is not None:
        delta = round(rank_result["precision"] - salience_result["precision"], 6)
        beats = bool(delta > 0)

    return {
        "schema": "golden_eval.v1",
        "state": state,
        "k": int(k),
        "min_labeled": min_labeled,
        "corpus_rows": len(usable),
        "labeled_rows": len(labeled_ids),
        "labels_in_store": len(labels),
        "label_counts": label_counts,
        "precision_at_k": {
            "rank_score": rank_result,
            "salience": salience_result,
        },
        "delta": delta,
        "beats_salience": beats,
        "note": {
            "no-labels": ("NO LABELS YET — precision@k is undefined, not zero. "
                          "The comparison becomes binding when the operator/Fable "
                          "labeling session lands rows in the label store."),
            "insufficient": (f"Fewer than {min_labeled} labeled rows — numbers "
                             "printed for inspection only; they gate nothing."),
            "ok": "Comparison is binding: rank ordering vs salience-only ordering.",
        }[state],
    }


def format_report(report: dict) -> str:
    """Plain-text report for the CLI + CI logs (no colours, no emoji)."""
    lines = [
        "golden-set eval — XG-W5 scoring brain",
        f"  state          : {report.get('state')}",
        f"  corpus rows    : {report.get('corpus_rows')}",
        f"  labeled rows   : {report.get('labeled_rows')} "
        f"(store holds {report.get('labels_in_store')})",
        f"  label counts   : {report.get('label_counts')}",
    ]
    pak = report.get("precision_at_k") or {}
    for name in ("rank_score", "salience"):
        entry = pak.get(name) or {}
        value = entry.get("precision")
        shown = "undefined" if value is None else f"{value:.4f}"
        lines.append(f"  P@{report.get('k')} {name:<11}: {shown} "
                     f"(labeled in top-k: {entry.get('k_effective', 0)}, "
                     f"hits: {entry.get('hits', 0)})")
    lines.append(f"  delta          : {report.get('delta')}")
    lines.append(f"  beats salience : {report.get('beats_salience')}")
    lines.append(f"  note           : {report.get('note')}")
    return "\n".join(lines)
