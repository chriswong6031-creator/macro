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

# Review F-12: the salience band cutoffs used for stratification are hypotheses
# about where "high"/"mid"/"low" sit on a 0-100 scale, not facts — they were
# hardcoded 70/40 in `_stratum`.
DEFAULT_BANDS: tuple[float, float] = (70.0, 40.0)

# Review F-7: a bare sign test on two precisions is not evidence. `beats_salience`
# now requires BOTH a pre-registered margin and a pre-registered significance
# level on a PAIRED test over the discordant pairs.
DEFAULT_ALPHA = 0.05
DEFAULT_MIN_MARGIN = 0.05
DEFAULT_BOOTSTRAP = 2000
DEFAULT_BOOTSTRAP_SEED = 20260728


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
                   batch_id: str = "", sample_mode: str = "",
                   inclusion_weight: float = 1.0) -> dict:
    """Build a schema-valid label row (the CLI's row constructor).

    `sample_mode` and `inclusion_weight` travel from the batch into the label so
    the eval knows which estimator it is entitled to (review F-8a). A label with
    no sample_mode is still valid — it just forces the honest
    "unweighted-unknown-design" estimator rather than a silent assumption.
    """
    now = now or datetime.now(tz=timezone.utc)
    return {
        "schema": LABEL_SCHEMA,
        "item_id": str(item_id),
        "label": str(label),
        "labeler": str(labeler),
        "labeled_at": now.astimezone(timezone.utc).isoformat(),
        "batch_id": str(batch_id),
        "sample_mode": str(sample_mode),
        "inclusion_weight": float(inclusion_weight or 1.0),
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

def baseline_salience(row: dict) -> float:
    """The UNCONTAMINATED incumbent score for a corpus row (review F-8b).

    Prefers `salience_base` — the pre-demotion number press_lane persists — and
    falls back to `salience` for rows written before that field existed. Once
    demotion arms, `salience` is partly the challenger's output, and ranking the
    control on it would compare the new scorer against a blend of itself and the
    baseline.
    """
    for field in ("salience_base", "salience"):
        value = row.get(field)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return 0.0


def _stratum(row: dict, *, bands: tuple[float, float] = DEFAULT_BANDS) -> str:
    """Sampling stratum: (outcome family, source tier, salience band).

    A batch drawn purely at random over a wire corpus is ~all low-salience
    aggregator noise, and a batch drawn from the top of the ranking only
    measures the ranking's own opinion of itself. Stratifying across outcome and
    salience band is what makes the labeled set informative about BOTH the
    garbage gate and the ordering — at the cost of no longer being a uniform
    sample of the production head, which `evaluate` corrects for (review F-8a).
    """
    outcome = str(row.get("outcome", "")).split(":", 1)[0] or "scored"
    tier = str(row.get("source_tier", "") or "unknown")
    salience = baseline_salience(row)
    high, mid = bands
    if salience >= high:
        band = "high"
    elif salience >= mid:
        band = "mid"
    else:
        band = "low"
    return f"{outcome}|{tier}|{band}"


def _stable_rank(item_id: str, seed: str) -> str:
    return hashlib.sha1(f"{seed}|{item_id}".encode("utf-8")).hexdigest()


def dedupe_rows(rows: Iterable[dict]) -> list[dict]:
    """One row per item_id, newest kept (review F-1/F-2).

    The corpus is append-only and, before the lane's per-item window landed, a
    non-emitting item was re-rowed every tick. Even with that fixed, a corpus
    spanning more than one window legitimately holds several rows for one item
    (its features change as corroboration accrues). EVERY consumer that treats
    a row as an ITEM — batch export, ranking, precision — has to collapse first,
    or it silently weights loud repeats and calls it a sample.
    """
    latest: dict[str, dict] = {}
    for row in rows:
        item_id = str(row.get("item_id", ""))
        if not item_id:
            continue
        prior = latest.get(item_id)
        if prior is None or str(row.get("ingested_at", "")) >= str(prior.get("ingested_at", "")):
            latest[item_id] = row
    return list(latest.values())


def export_batch(rows: Sequence[dict], *, n: int = 200,
                 labeled: Iterable[str] | None = None,
                 seed: str = "xg-w5", now: datetime | None = None,
                 mode: str = "stratified",
                 cfg: dict | None = None) -> dict:
    """Assemble a labeling batch of up to `n` DISTINCT items.

    Deterministic: selection is a stable hash of (seed, item_id), so re-running
    the export over the same corpus yields the SAME batch — a labeling session
    interrupted halfway can be resumed without re-sampling, and an eval can name
    the exact batch it graded. Already-labeled ids are excluded, so successive
    batches extend the golden set instead of re-asking the same questions.

    Rows are DEDUPED BY item_id first (review F-1): the reviewer's replay
    produced a "200-item" batch holding 22 distinct items, two of them ninety
    times over, because the corpus carried one row per item per tick.

    `mode` picks the estimator the eval will be entitled to use (review F-8a):

      "stratified"  round-robin across (outcome, tier, salience band). Rich in
                    rare cells, but NOT a uniform sample of the production head,
                    so unweighted precision@k over it is biased. Each item
                    carries `inclusion_weight` = 1/p so the eval can compute the
                    inverse-inclusion-probability estimate.
      "head"        uniform random sample of the top `head_size` items by the
                    baseline score. Directly estimates precision on the head the
                    top-K/day counter actually spends; weights are all 1.0.
    """
    now = now or datetime.now(tz=timezone.utc)
    cfg = cfg or {}
    bands = tuple(cfg.get("bands") or DEFAULT_BANDS)  # type: ignore[assignment]
    done = {str(x) for x in (labeled or ())}
    pool = [r for r in dedupe_rows(rows) if str(r["item_id"]) not in done]

    if mode == "head":
        head_size = int(cfg.get("head_size", 500))
        head = sorted(pool, key=lambda r: (-baseline_salience(r), str(r["item_id"])))[:head_size]
        ordered = sorted(head, key=lambda r: _stable_rank(str(r["item_id"]), seed))
        selected = ordered[:n]
        p_incl = (len(selected) / len(head)) if head else 0.0
        weights = {str(r["item_id"]): 1.0 for r in selected}
        buckets = {"head": head}
    else:
        buckets = {}
        for row in pool:
            buckets.setdefault(_stratum(row, bands=bands), []).append(row)
        for key in buckets:
            buckets[key].sort(key=lambda r: _stable_rank(str(r["item_id"]), seed))

        # Round-robin across strata so no single stratum can swamp the batch.
        selected = []
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
        # Inverse inclusion probability: within a stratum every item had the same
        # chance of selection, so p = taken/available and the item stands for 1/p
        # of its stratum in the population.
        taken: dict[str, int] = {}
        for row in selected:
            taken[_stratum(row, bands=bands)] = taken.get(_stratum(row, bands=bands), 0) + 1
        weights = {}
        for row in selected:
            key = _stratum(row, bands=bands)
            available = max(1, len(buckets.get(key, [])))
            p = taken[key] / available
            weights[str(row["item_id"])] = round(1.0 / p, 6) if p > 0 else 1.0
        p_incl = 0.0

    batch_id = "gb-" + hashlib.sha1(
        f"{seed}|{mode}|{now.astimezone(timezone.utc).strftime('%Y-%m-%d')}|{len(selected)}"
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
        "stratum": _stratum(r, bands=bands) if mode != "head" else "head",
        "sample_mode": mode,
        "inclusion_weight": weights.get(str(r.get("item_id", "")), 1.0),
        # The engine's own numbers travel with the row so a labeler can see them,
        # but the LABEL is the human's call — they are printed, never proposed.
        "salience": r.get("salience"),
        "salience_base": r.get("salience_base", r.get("salience")),
        "rank_score": r.get("rank_score"),
        "label": "",
    } for r in selected]

    return {
        "batch_id": batch_id,
        "created_at": now.astimezone(timezone.utc).isoformat(),
        "seed": seed,
        "mode": mode,
        "requested": int(n),
        "returned": len(items),
        "distinct_items": len({i["item_id"] for i in items}),
        "corpus_rows": len(rows),
        "distinct_corpus_items": len(dedupe_rows(rows)),
        "already_labeled": len(done),
        "head_inclusion_p": round(p_incl, 6),
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


def _baseline_sort_key():
    """Order by the UNCONTAMINATED incumbent score (review F-8b)."""
    def _key(row: dict) -> tuple[float, str]:
        return (baseline_salience(row), str(row.get("item_id", "")))
    return _key


def top_k_ids(ordered_rows: Sequence[dict], labels: dict[str, dict], *,
              k: int = 20) -> list[str]:
    """The first k DISTINCT labeled item ids of an ordering.

    Review F-2: this used to walk raw rows, so a corpus holding one item ninety
    times filled the whole top-k with that one item and reported k_effective=20
    over three distinct stories. Ranking is over items; the ordering must be
    deduped before it is truncated, not after.
    """
    considered: list[str] = []
    seen: set[str] = set()
    for row in ordered_rows:
        item_id = str(row.get("item_id", ""))
        if not item_id or item_id in seen or item_id not in labels:
            continue
        seen.add(item_id)
        considered.append(item_id)
        if len(considered) >= k:
            break
    return considered


def precision_at_k(ordered_rows: Sequence[dict], labels: dict[str, dict], *,
                   k: int = 20, weighted: bool = False) -> dict:
    """precision@k over the labeled subset of an ordering.

    ONLY LABELED ROWS COUNT, in both numerator and denominator: an unlabeled row
    is not evidence either way, and silently treating it as a negative would
    manufacture a number out of missing data. `k_effective` reports how many
    DISTINCT labeled items the top-k actually contained.

    `weighted=True` computes the inverse-inclusion-probability estimate using
    each label's `inclusion_weight` (review F-8a) — the unbiased form when the
    labeled set came from a stratified batch rather than a uniform head sample.
    """
    considered = top_k_ids(ordered_rows, labels, k=k)
    if not considered:
        return {"precision": None, "k_effective": 0, "hits": 0}

    hits = sum(1 for i in considered if labels[i].get("label") in POSITIVE_LABELS)
    if not weighted:
        return {
            "precision": round(hits / len(considered), 6),
            "k_effective": len(considered),
            "hits": hits,
        }

    numerator = 0.0
    denominator = 0.0
    for item_id in considered:
        weight = float(labels[item_id].get("inclusion_weight", 1.0) or 1.0)
        denominator += weight
        if labels[item_id].get("label") in POSITIVE_LABELS:
            numerator += weight
    return {
        "precision": round(numerator / denominator, 6) if denominator else None,
        "k_effective": len(considered),
        "hits": hits,
        "weight_sum": round(denominator, 4),
    }


def _binom_two_sided_p(b: int, c: int) -> float:
    """Exact two-sided binomial p for McNemar's test on b vs c discordant pairs."""
    n = b + c
    if n == 0:
        return 1.0
    from math import comb  # noqa: PLC0415

    total = 2 ** n
    observed = min(b, c)
    tail = sum(comb(n, i) for i in range(observed + 1))
    return min(1.0, 2.0 * tail / total)


def mcnemar(rank_ids: Sequence[str], salience_ids: Sequence[str],
            labels: dict[str, dict]) -> dict:
    """Paired comparison of two top-k sets over the SAME labeled items.

    Review F-7. The old `beats_salience` was `delta > 0` — a bare sign test on
    two point estimates from one small sample, which will read "better" about
    half the time on two identical rankers. The honest question is paired: among
    the items where the two orderings DISAGREE, does the new one pick the
    positives?

        b = positives the rank ordering caught that salience missed
        c = positives salience caught that rank missed

    Concordant items carry no information about which is better and are
    excluded, which is the whole point of the pairing.
    """
    rank_set, salience_set = set(rank_ids), set(salience_ids)
    only_rank = rank_set - salience_set
    only_salience = salience_set - rank_set
    b = sum(1 for i in only_rank if labels[i].get("label") in POSITIVE_LABELS)
    c = sum(1 for i in only_salience if labels[i].get("label") in POSITIVE_LABELS)
    return {
        "b_rank_only_positives": b,
        "c_salience_only_positives": c,
        "discordant_pairs": b + c,
        "p_value": round(_binom_two_sided_p(b, c), 6),
        "note": "McNemar exact, two-sided, over discordant top-k membership",
    }


def _bootstrap_delta_ci(rows: Sequence[dict], labels: dict[str, dict], *, k: int,
                        weighted: bool, n_boot: int, seed: int,
                        alpha: float) -> dict:
    """Percentile CI for (rank P@k − salience P@k) by PAIRED item resampling.

    Both orderings are recomputed on the SAME resampled item set every draw, so
    the interval is about the difference between the rankers rather than about
    two independently noisy precisions.
    """
    import random  # noqa: PLC0415

    labeled = [r for r in rows if str(r.get("item_id", "")) in labels]
    if len(labeled) < 2:
        return {"low": None, "high": None, "n_boot": 0,
                "note": "too few labeled items to resample"}
    rng = random.Random(seed)
    deltas: list[float] = []
    size = len(labeled)
    for _ in range(n_boot):
        sample = [labeled[rng.randrange(size)] for _ in range(size)]
        by_rank = sorted(sample, key=_sort_key("rank_score"), reverse=True)
        by_base = sorted(sample, key=_baseline_sort_key(), reverse=True)
        a = precision_at_k(by_rank, labels, k=k, weighted=weighted)["precision"]
        b = precision_at_k(by_base, labels, k=k, weighted=weighted)["precision"]
        if a is None or b is None:
            continue
        deltas.append(a - b)
    if not deltas:
        return {"low": None, "high": None, "n_boot": 0,
                "note": "no resample produced a comparable pair"}
    deltas.sort()
    lo_idx = int((alpha / 2) * len(deltas))
    hi_idx = min(len(deltas) - 1, int((1 - alpha / 2) * len(deltas)))
    return {
        "low": round(deltas[lo_idx], 6),
        "high": round(deltas[hi_idx], 6),
        "n_boot": len(deltas),
        "note": f"paired percentile CI at alpha={alpha}",
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
    cfg = cfg or {}
    min_labeled = int(cfg.get("min_labeled", DEFAULT_MIN_LABELED))
    alpha = float(cfg.get("alpha", DEFAULT_ALPHA))
    min_margin = float(cfg.get("min_margin", DEFAULT_MIN_MARGIN))
    n_boot = int(cfg.get("bootstrap_draws", DEFAULT_BOOTSTRAP))
    boot_seed = int(cfg.get("bootstrap_seed", DEFAULT_BOOTSTRAP_SEED))

    # Review F-1/F-2: collapse to one row per item BEFORE ranking anything.
    usable = dedupe_rows(rows)
    labeled_ids = {r["item_id"] for r in usable if str(r["item_id"]) in labels}

    # Review F-8a: which estimator are we entitled to? A stratified batch is not
    # a uniform sample of the production head, so the unweighted precision over
    # it is biased; the labels carry the inclusion weights that fix it. A head
    # batch needs no weights. A mixture of the two is neither, and says so.
    modes = {str(labels[i].get("sample_mode", "")) for i in labeled_ids}
    modes.discard("")
    if modes == {"head"}:
        estimator, weighted = "uniform-head", False
    elif modes == {"stratified"}:
        estimator, weighted = "stratified-iip", True
    elif not modes:
        estimator, weighted = "unweighted-unknown-design", False
    else:
        estimator, weighted = "unweighted-mixed-design", False

    by_rank = sorted(usable, key=_sort_key("rank_score"), reverse=True)
    by_salience = sorted(usable, key=_baseline_sort_key(), reverse=True)
    rank_result = precision_at_k(by_rank, labels, k=k, weighted=weighted)
    salience_result = precision_at_k(by_salience, labels, k=k, weighted=weighted)

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
    paired: dict = {}
    ci: dict = {}
    if rank_result["precision"] is not None and salience_result["precision"] is not None:
        # The raw delta is DISPLAY, always printed, never the gate (review F-7).
        delta = round(rank_result["precision"] - salience_result["precision"], 6)
        paired = mcnemar(top_k_ids(by_rank, labels, k=k),
                         top_k_ids(by_salience, labels, k=k), labels)
    if state == "ok" and delta is not None:
        ci = _bootstrap_delta_ci(usable, labels, k=k, weighted=weighted,
                                 n_boot=n_boot, seed=boot_seed, alpha=alpha)
        # PRE-REGISTERED GATE: a margin AND a significance level, both config.
        beats = bool(delta >= min_margin
                     and paired.get("p_value", 1.0) <= alpha
                     and paired.get("b_rank_only_positives", 0)
                     > paired.get("c_salience_only_positives", 0))

    estimator_notes = {
        "uniform-head": ("Uniform sample of the production head — unweighted "
                         "precision@k is an unbiased estimate of head precision."),
        "stratified-iip": ("Stratified batch — precision@k is the INVERSE-"
                           "INCLUSION-PROBABILITY estimate. The unweighted "
                           "number over a stratified sample is biased and is "
                           "not reported as the estimate."),
        "unweighted-unknown-design": ("Labels carry no sample_mode (hand-added, "
                                      "or exported before the design was "
                                      "recorded) — unweighted, and the target "
                                      "population is UNKNOWN. Treat as indicative."),
        "unweighted-mixed-design": ("Labels mix head and stratified batches — "
                                    "no single estimator is valid across them. "
                                    "Unweighted, indicative only; re-export one "
                                    "design before treating this as evidence."),
    }

    return {
        "schema": "golden_eval.v2",
        "state": state,
        "k": int(k),
        "min_labeled": min_labeled,
        "alpha": alpha,
        "min_margin": min_margin,
        "estimator": estimator,
        "corpus_rows": len(rows),
        "distinct_items": len(usable),
        "labeled_rows": len(labeled_ids),
        "labels_in_store": len(labels),
        "label_counts": label_counts,
        "precision_at_k": {
            "rank_score": rank_result,
            "salience": salience_result,
        },
        "delta": delta,
        "delta_ci": ci,
        "paired_test": paired,
        "beats_salience": beats,
        "note": {
            "no-labels": ("NO LABELS YET — precision@k is undefined, not zero. "
                          "The comparison becomes binding when the operator/Fable "
                          "labeling session lands rows in the label store."),
            "insufficient": (f"Fewer than {min_labeled} labeled items — numbers "
                             "printed for inspection only; they gate nothing."),
            "ok": (f"Binding: rank ordering vs the pre-demotion salience ordering. "
                   f"beats_salience requires delta >= {min_margin} AND McNemar "
                   f"p <= {alpha} on the discordant pairs."),
        }[state] + " " + estimator_notes[estimator],
    }


def format_report(report: dict) -> str:
    """Plain-text report for the CLI + CI logs (no colours, no emoji)."""
    lines = [
        "golden-set eval — XG-W5 scoring brain",
        f"  state          : {report.get('state')}",
        f"  estimator      : {report.get('estimator')}",
        f"  corpus rows    : {report.get('corpus_rows')} "
        f"({report.get('distinct_items')} distinct items)",
        f"  labeled items  : {report.get('labeled_rows')} "
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
    ci = report.get("delta_ci") or {}
    lines.append(f"  delta (display): {report.get('delta')}  "
                 f"CI[{ci.get('low')}, {ci.get('high')}] n_boot={ci.get('n_boot', 0)}")
    paired = report.get("paired_test") or {}
    lines.append(f"  paired test    : b={paired.get('b_rank_only_positives')} "
                 f"c={paired.get('c_salience_only_positives')} "
                 f"discordant={paired.get('discordant_pairs')} "
                 f"p={paired.get('p_value')}")
    lines.append(f"  gate           : delta >= {report.get('min_margin')} "
                 f"AND p <= {report.get('alpha')}")
    lines.append(f"  beats salience : {report.get('beats_salience')}")
    lines.append(f"  note           : {report.get('note')}")
    return "\n".join(lines)
