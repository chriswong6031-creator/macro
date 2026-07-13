"""engine.neuralweb.orchestrator_log — the Neural Web orchestrator's run log + N-run review (W-AI).

The "master brain" of the Neural Web is not a module — it is the nightly pipeline (daily.yml
engine job) over the config/synapse.yml registry. This module gives that orchestrator a FACE the
operator asked for: one log entry per pipeline run summarising everything the loop completed, and
every N runs (config.yml ``orchestrator.review_every_n_runs``, default 5) a roll-up review with a
deterministic progress assessment.

DETERMINISTIC BY LAW (the daily_brief discipline): no LLM, no randomness — every field is composed
from artifacts the run already produced (health.json, daily_brief.json, mastermind_feedback_summary
.json). Display/ops only: no trading semantics, no authority.

RUNS IN THE CORTEX JOB (after ``build_neuralweb_brief --finalize``) so it sees the run's final
state; its outputs are committed in the cortex commit lane. Entries key on the CALENDAR run date
(+ workflow, keep-first) — a same-day retry is idempotent; a run whose cortex job died entirely
records nothing (visible instead as a calendar gap in the ledger + workflow warnings). The
market-data date is carried separately as ``data_as_of``.

ARTIFACTS
  data/neuralweb/orchestrator_runlog.jsonl   — full per-run ledger (keep-first per run_date+workflow)
  data/neuralweb/orchestrator_reviews.jsonl  — one row per N-run review
  site/neuralwebdata/orchestrator_runlog.json — published dict {schema, entries (last N),
      reviews (last 12)}, envelope-stamped (artifact_id ``neuralweb-orchestrator-runlog``)

Schema (site artifact): ``neuralweb.orchestrator_runlog.v1``.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

SCHEMA = "neuralweb.orchestrator_runlog.v1"
ARTIFACT_ID = "neuralweb-orchestrator-runlog"

_RUNLOG_REL = Path("data") / "neuralweb" / "orchestrator_runlog.jsonl"
_REVIEWS_REL = Path("data") / "neuralweb" / "orchestrator_reviews.jsonl"
_SITE_REL = Path("site") / "neuralwebdata" / "orchestrator_runlog.json"

_DEFAULT_REVIEW_EVERY_N = 5
_DEFAULT_SITE_ROWS = 60
_SITE_REVIEWS = 12


def _repo_root(root: Path | str | None = None) -> Path:
    if root is not None:
        return Path(root)
    return Path(__file__).resolve().parent.parent.parent


def _read_json(p: Path) -> dict | None:
    try:
        if p.exists():
            v = json.loads(p.read_text(encoding="utf-8"))
            return v if isinstance(v, dict) else None
    except Exception:  # noqa: BLE001
        pass
    return None


def _read_jsonl(p: Path) -> list[dict]:
    try:
        if not p.exists():
            return []
        rows = []
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            if isinstance(r, dict):
                rows.append(r)
        return rows
    except Exception:  # noqa: BLE001
        return []


def _append_jsonl(p: Path, row: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, separators=(",", ":"), ensure_ascii=False, default=str) + "\n")


def _settings(root: Path) -> dict:
    """config.yml ``orchestrator:`` block, degrade-safe to defaults."""
    out = {"review_every_n_runs": _DEFAULT_REVIEW_EVERY_N, "site_rows": _DEFAULT_SITE_ROWS,
           "ingest_bot_feedback": True}
    try:
        import yaml  # noqa: PLC0415
        cfg = yaml.safe_load((root / "config.yml").read_text(encoding="utf-8")) or {}
        block = cfg.get("orchestrator") or {}
        n = block.get("review_every_n_runs")
        if isinstance(n, int) and 2 <= n <= 50:
            out["review_every_n_runs"] = n
        rows = block.get("site_rows")
        if isinstance(rows, int) and 10 <= rows <= 365:
            out["site_rows"] = rows
        if isinstance(block.get("ingest_bot_feedback"), bool):
            out["ingest_bot_feedback"] = block["ingest_bot_feedback"]
    except Exception:  # noqa: BLE001
        pass
    return out


# ─────────────────────────────────────────────────────────────────────────────
# entry composition
# ─────────────────────────────────────────────────────────────────────────────

def build_entry(root: Path | str | None = None, *, workflow: str = "daily",
                now: datetime | None = None) -> dict:
    """Compose one run-log entry from the run's own artifacts. Never raises."""
    repo = _repo_root(root)
    now = now or datetime.now(timezone.utc)

    health = _read_json(repo / "data" / "neuralweb" / "health.json") or {}
    brief = _read_json(repo / "data" / "neuralweb" / "daily_brief.json") or {}
    feedback = _read_json(repo / "data" / "governance" / "mastermind_feedback_summary.json") or {}

    counts = health.get("summary_counts") or {}
    lobes = health.get("lobes") or []
    dbr = brief.get("did_the_brain_run") or {}
    nudges = feedback.get("nudges") or []
    directives = feedback.get("operator_directives") or []

    what_changed = brief.get("what_changed") or []
    attention = brief.get("operator_attention") or []
    # run_date is the CALENDAR date of this pipeline run — the keep-first dedup key must be
    # per-run, not per-market-data-day: keying on the brief's as_of made degraded runs (stale
    # carried-forward brief) and weekend runs collide with a prior entry and go permanently
    # unrecorded (review finding, 2026-07-13). The market-data date is kept as data_as_of.
    run_date = now.strftime("%Y-%m-%d")
    data_as_of = str(brief.get("as_of") or health.get("as_of") or run_date)[:10]

    lobes_total = len(lobes) if isinstance(lobes, list) else 0
    lobes_stale = int(counts.get("stale") or 0)
    changed_n = len(what_changed) if isinstance(what_changed, list) else 0
    contradicted_n = len(brief.get("what_contradicted") or [])
    gaps_n = len(brief.get("_gaps") or []) + len(feedback.get("gap_notes") or [])
    cortex_status = str(dbr.get("cortex_status") or (health.get("cortex") or {}).get("status")
                        or "unknown")

    summary = (f"{workflow} run {run_date} (data through {data_as_of}): "
               f"{lobes_total} lobes ({lobes_stale} stale), "
               f"{changed_n} changes, {contradicted_n} contradictions, "
               f"cortex {cortex_status}; bot dialogue: {len(nudges)} nudges, "
               f"{len(directives)} directives "
               f"({feedback.get('state', 'absent')})")

    return {
        "run_date": run_date,
        "data_as_of": data_as_of,
        "produced_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "workflow": workflow,
        "overall_status": health.get("overall_status") or brief.get("status") or "unknown",
        "lobes_total": lobes_total,
        "lobes_stale": lobes_stale,
        "what_changed_n": changed_n,
        "what_changed_kinds": _kind_counts(what_changed),
        "contradictions_n": contradicted_n,
        "gaps_n": gaps_n,
        "operator_attention_n": len(attention) if isinstance(attention, list) else 0,
        "cortex_status": cortex_status,
        "cortex_tool_calls": dbr.get("individual_tool_calls"),
        "feedback_state": feedback.get("state") or "absent",
        "nudges_n": len(nudges),
        "nudge_codes": [n.get("code") for n in nudges[:10] if isinstance(n, dict)],
        "directives_n": len(directives),
        "summary": summary,
    }


def _kind_counts(what_changed: list) -> dict:
    out: dict[str, int] = {}
    for w in what_changed if isinstance(what_changed, list) else []:
        if isinstance(w, dict):
            k = str(w.get("kind") or "other")
            out[k] = out.get(k, 0) + 1
    return out


# ─────────────────────────────────────────────────────────────────────────────
# N-run review
# ─────────────────────────────────────────────────────────────────────────────

def _trend(first, last) -> str:
    try:
        if first is None or last is None:
            return "flat"
        return "up" if last > first else ("down" if last < first else "flat")
    except Exception:  # noqa: BLE001
        return "flat"


def build_review(entries: list[dict], review_n: int, now: datetime | None = None) -> dict:
    """Deterministic roll-up of the last ``review_n`` entries: what the orchestrator completed
    + an honest progress assessment (trends, not vibes)."""
    now = now or datetime.now(timezone.utc)
    window = entries[-review_n:]
    first, last = (window[0], window[-1]) if window else ({}, {})

    changed_total = sum(int(e.get("what_changed_n") or 0) for e in window)
    kinds: dict[str, int] = {}
    for e in window:
        for k, v in (e.get("what_changed_kinds") or {}).items():
            kinds[k] = kinds.get(k, 0) + int(v or 0)
    nudge_codes: list[str] = []
    for e in window:
        for c in (e.get("nudge_codes") or []):
            if c and c not in nudge_codes:
                nudge_codes.append(c)

    assessment = [
        f"stale lobes {_trend(first.get('lobes_stale'), last.get('lobes_stale'))} "
        f"({first.get('lobes_stale')} -> {last.get('lobes_stale')}) over {len(window)} runs",
        f"bot nudges {_trend(first.get('nudges_n'), last.get('nudges_n'))} "
        f"({first.get('nudges_n')} -> {last.get('nudges_n')}); "
        f"codes seen this window: {', '.join(nudge_codes[:8]) or 'none'}",
        f"cortex status latest: {last.get('cortex_status')}; "
        f"degraded runs in window: "
        f"{sum(1 for e in window if e.get('overall_status') not in ('ok', 'fresh'))}/{len(window)}",
        f"operator attention items latest: {last.get('operator_attention_n')} "
        f"({_trend(first.get('operator_attention_n'), last.get('operator_attention_n'))})",
    ]

    return {
        "produced_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "window_runs": len(window),
        "from_run": first.get("run_date"),
        "to_run": last.get("run_date"),
        "completed": {
            "runs": len(window),
            "what_changed_total": changed_total,
            "what_changed_kinds": kinds,
            "directives_seen": sum(int(e.get("directives_n") or 0) for e in window),
        },
        "assessment": assessment,
    }


# ─────────────────────────────────────────────────────────────────────────────
# record + publish
# ─────────────────────────────────────────────────────────────────────────────

def record_run(root: Path | str | None = None, *, workflow: str = "daily",
               now: datetime | None = None) -> dict:
    """Append this run's entry (keep-first per run_date+workflow), write the N-run review when
    due, and publish the site artifact. Returns {entry, review?, published}. Never raises."""
    repo = _repo_root(root)
    try:
        entry = build_entry(repo, workflow=workflow, now=now)
        runlog_path = repo / _RUNLOG_REL
        entries = _read_jsonl(runlog_path)
        key = (entry["run_date"], entry["workflow"])
        out: dict = {"entry": entry, "published": False}
        if any((e.get("run_date"), e.get("workflow")) == key for e in entries):
            log.info("orchestrator_log: entry for %s/%s already recorded (keep-first)", *key)
        else:
            _append_jsonl(runlog_path, entry)
            entries.append(entry)
            # review due every N entries
            cfg = _settings(repo)
            n = cfg["review_every_n_runs"]
            if len(entries) % n == 0:
                review = build_review(entries, n, now=now)
                _append_jsonl(repo / _REVIEWS_REL, review)
                out["review"] = review
        out["published"] = _publish_site(repo, entries, now=now)
        return out
    except Exception as exc:  # noqa: BLE001
        log.warning("orchestrator_log: record_run failed — %s", exc)
        return {"entry": None, "published": False, "error": str(exc)}


def _publish_site(repo: Path, entries: list[dict], now: datetime | None = None) -> bool:
    """Write site/neuralwebdata/orchestrator_runlog.json (envelope-stamped dict root)."""
    try:
        cfg = _settings(repo)
        reviews = _read_jsonl(repo / _REVIEWS_REL)
        payload = {
            "schema": SCHEMA,
            "as_of": entries[-1]["run_date"] if entries else None,
            "review_every_n_runs": cfg["review_every_n_runs"],
            "n_entries_total": len(entries),
            "entries": entries[-cfg["site_rows"]:],
            "reviews": reviews[-_SITE_REVIEWS:],
            "is_context_only": True,
        }
        try:
            from engine.neuralweb.envelope import stamp  # noqa: PLC0415
            payload = stamp(payload, artifact_id=ARTIFACT_ID,
                            now=now or datetime.now(timezone.utc))
        except Exception as exc:  # noqa: BLE001
            log.warning("orchestrator_log: envelope stamp failed (%s) — writing unstamped", exc)
        out = repo / _SITE_REL
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, separators=(",", ":"), ensure_ascii=False,
                                  default=str), encoding="utf-8")
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("orchestrator_log: site publish failed — %s", exc)
        return False


# ─────────────────────────────────────────────────────────────────────────────
# read surfaces (admin Observatory)
# ─────────────────────────────────────────────────────────────────────────────

def load(root: Path | str | None = None, *, limit: int = 60) -> dict:
    """{entries, reviews, settings} for the admin backend. Never raises."""
    repo = _repo_root(root)
    return {
        "entries": _read_jsonl(repo / _RUNLOG_REL)[-limit:],
        "reviews": _read_jsonl(repo / _REVIEWS_REL)[-_SITE_REVIEWS:],
        "settings": _settings(repo),
    }
