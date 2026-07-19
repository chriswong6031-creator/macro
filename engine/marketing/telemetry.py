"""engine.marketing.telemetry — Engagement telemetry store + Lab roll-up.

Row schema (stored as JSONL at data/marketing/telemetry/YYYY-MM.jsonl):
    post_id        str   — joins to content_plan queue item id
    captured_at    str   — ISO-8601 datetime
    impressions    int
    likes          int
    replies        int
    reposts        int
    bookmarks      int
    link_clicks    int   (optional)
    followers_at_post int (optional)

Entry points
    ingest_rows(rows, *, root)                  validate + append
    load_telemetry(root) -> list[dict]           read all monthly files
    join_provenance(rows, plan) -> dict          join to content_plan
    rollup(joined, orphans, *, as_of) -> dict   compute roll-up artifact
    write_rollup(root, *, as_of=None) -> dict   orchestrator — reads+writes

N-floor law: any cell with n < 20 carries verdict="seeding"; no hypothesis
is promoted above "seeding" in W0.

Never-raise at orchestrator level: exceptions are caught; returns a dict
with an "error" key on failure.
"""
from __future__ import annotations

import json
import logging
import statistics
import tempfile
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

_N_FLOOR = 20  # cells below this never declare a verdict

_REQUIRED_FIELDS = {"post_id", "captured_at", "impressions", "likes", "replies", "reposts", "bookmarks"}
_METRIC_FIELDS = {"impressions", "likes", "replies", "reposts", "bookmarks", "link_clicks", "followers_at_post"}
_NON_NEG_FIELDS = {"impressions", "likes", "replies", "reposts", "bookmarks", "link_clicks", "followers_at_post"}

# Seeded hypothesis list from the zero-follower traction playbook.
# Each id is stable — do not reorder.
_SEED_HYPOTHESES: list[dict[str, Any]] = [
    {
        "id": "H01",
        "title": "Multi-cashtag theme list outperforms single-ticker posts on impressions",
        "state": "seeding",
        "n_evidence": 0,
        "note": (
            "Playbook §2: one post in 6–10 cashtag streams simultaneously. "
            "Test: compare theme_list vs. signal/chart impressions medians."
        ),
    },
    {
        "id": "H02",
        "title": "Instant earnings reaction posts capture the highest-traffic cashtag window",
        "state": "seeding",
        "n_evidence": 0,
        "note": (
            "Playbook §3 item 3: earnings cards posted within minutes of release reach "
            "thousands of searchers while the cashtag is hot. "
            "Test: event-type posts vs. non-event impressions, same slot."
        ),
    },
    {
        "id": "H03",
        "title": "Chart receipt posts generate more replies than copy-only posts",
        "state": "seeding",
        "n_evidence": 0,
        "note": (
            "Playbook §3: annotated mover chart on its cashtag earns more scroll-stops "
            "and replies than text-only. "
            "Test: posts with chart_id set vs. chart_id null — replies median."
        ),
    },
    {
        "id": "H04",
        "title": "Persona effect: 'tape reader' voice outperforms 'authoritative desk' on engagement rate at cold-start",
        "state": "seeding",
        "n_evidence": 0,
        "note": (
            "Playbook §7: cold accounts need loud/engagement-bait style. "
            "Test: research_b (tape-reader) vs. flagship (authoritative desk) — (likes+replies)/impressions."
        ),
    },
    {
        "id": "H05",
        "title": "LLM-written copy outperforms deterministic copy on likes in theme-list format",
        "state": "seeding",
        "n_evidence": 0,
        "note": (
            "Copywriter layer: llm mode uses persona voice ceiling; deterministic uses "
            "templated floor. "
            "Test: mode=llm vs mode=deterministic within theme_list kind — likes median."
        ),
    },
    {
        "id": "H06",
        "title": "Open-window (D1-AM / pre-market) slots generate higher impressions than mid-day",
        "state": "seeding",
        "n_evidence": 0,
        "note": (
            "Playbook §4: 09:15–10:30 ET and earnings windows are attention peaks. "
            "Test: slot D1-AM vs. D2-PM median impressions."
        ),
    },
    {
        "id": "H07",
        "title": "Bearish/crash-themed mover posts reach more non-followers than rally posts",
        "state": "seeding",
        "n_evidence": 0,
        "note": (
            "Playbook §3 item 2: 'pain travels' — bearish chart of a crash outperforms rally. "
            "Test: mover posts where move_pct < 0 vs > 0 — impressions."
        ),
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# Path helpers
# ─────────────────────────────────────────────────────────────────────────────

def _repo_root(root: Path | str | None = None) -> Path:
    """Return repo root; defaults to three parents above this file."""
    if root is not None:
        return Path(root)
    return Path(__file__).resolve().parent.parent.parent


def _telemetry_dir(root: Path | str | None = None) -> Path:
    return _repo_root(root) / "data" / "marketing" / "telemetry"


def _rollup_path(root: Path | str | None = None) -> Path:
    return _repo_root(root) / "data" / "marketing" / "lab_rollup.json"


def _content_plan_path(root: Path | str | None = None) -> Path:
    return _repo_root(root) / "data" / "marketing" / "content_plan.json"


def _cashtag_tiers_path(root: Path | str | None = None) -> Path:
    return _repo_root(root) / "data" / "marketing" / "cashtag_tiers.json"


def _monthly_path(root: Path | str | None, captured_at: str) -> Path:
    """Return the YYYY-MM.jsonl path for a captured_at ISO string."""
    try:
        dt = datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
        month_key = dt.strftime("%Y-%m")
    except (ValueError, AttributeError):
        month_key = "unknown"
    return _telemetry_dir(root) / f"{month_key}.jsonl"


# ─────────────────────────────────────────────────────────────────────────────
# Validation
# ─────────────────────────────────────────────────────────────────────────────

def _validate_row(row: dict[str, Any]) -> str | None:
    """Return an error string if the row is invalid, else None."""
    if not isinstance(row, dict):
        return "row is not a dict"

    # Required fields
    missing = _REQUIRED_FIELDS - row.keys()
    if missing:
        return f"missing required fields: {sorted(missing)}"

    # post_id non-empty string
    if not isinstance(row.get("post_id"), str) or not row["post_id"].strip():
        return "post_id must be a non-empty string"

    # captured_at parseable ISO
    try:
        datetime.fromisoformat(str(row["captured_at"]).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return f"captured_at is not a valid ISO datetime: {row.get('captured_at')!r}"

    # At least one metric must be present and non-negative int
    metric_present = False
    for field in _NON_NEG_FIELDS:
        if field not in row:
            continue
        val = row[field]
        if not isinstance(val, int):
            return f"{field} must be an int, got {type(val).__name__}"
        if val < 0:
            return f"{field} must be non-negative, got {val}"
        metric_present = True

    if not metric_present:
        return "at least one metric field must be present"

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Ingest
# ─────────────────────────────────────────────────────────────────────────────

def ingest_rows(rows: list[dict[str, Any]], *, root: Path | str | None = None) -> dict[str, Any]:
    """Validate and append telemetry rows to the monthly JSONL files.

    Args:
        rows: list of raw telemetry row dicts.
        root: repo root (None = auto-detect from file location).

    Returns:
        {"ok": int, "rejected": [{"row": ..., "reason": str}]}
    """
    ok_count = 0
    rejected: list[dict[str, Any]] = []

    for row in rows:
        err = _validate_row(row)
        if err:
            log.warning("telemetry.ingest_rows: rejected row — %s | row=%r", err, row)
            rejected.append({"row": row, "reason": err})
            continue

        path = _monthly_path(root, str(row["captured_at"]))
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(row, ensure_ascii=False, separators=(",", ":"))
        with path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
        ok_count += 1

    return {"ok": ok_count, "rejected": rejected}


# ─────────────────────────────────────────────────────────────────────────────
# Load
# ─────────────────────────────────────────────────────────────────────────────

def load_telemetry(root: Path | str | None = None) -> list[dict[str, Any]]:
    """Read all monthly JSONL files under data/marketing/telemetry/.

    Returns:
        List of raw row dicts; malformed lines are skipped with a warning.
    """
    tdir = _telemetry_dir(root)
    rows: list[dict[str, Any]] = []
    if not tdir.exists():
        return rows

    for jl_file in sorted(tdir.glob("*.jsonl")):
        try:
            for line in jl_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    log.warning("telemetry.load: skipping malformed line in %s", jl_file)
        except Exception as exc:  # noqa: BLE001
            log.warning("telemetry.load: error reading %s: %s", jl_file, exc)

    return rows


# ─────────────────────────────────────────────────────────────────────────────
# Provenance join
# ─────────────────────────────────────────────────────────────────────────────

def _build_post_index(plan: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Build {post_id: {kind, account, slot, persona, mode}} from content_plan."""
    index: dict[str, dict[str, Any]] = {}
    accounts: list[dict[str, Any]] = plan.get("accounts", [])
    for acct in accounts:
        acct_id = acct.get("id", "")
        persona = acct.get("voice", "")
        for item in acct.get("queue", []):
            pid = item.get("id", "")
            if not pid:
                continue
            if pid in index:
                log.warning(
                    "telemetry._build_post_index: duplicate post_id %r across accounts "
                    "(previous account=%r, current account=%r) — keeping last",
                    pid,
                    index[pid].get("account", ""),
                    acct_id,
                )
            index[pid] = {
                "kind": item.get("type", ""),
                "account": acct_id,
                "slot": item.get("slot", ""),
                "persona": persona,
                "mode": item.get("_copy_mode", "deterministic"),
            }
    return index


def join_provenance(
    rows: list[dict[str, Any]],
    plan: dict[str, Any],
    *,
    root: Path | str | None = None,
) -> dict[str, Any]:
    """Join telemetry rows to content_plan provenance.

    Args:
        rows:  raw telemetry rows (from load_telemetry or ingest_rows).
        plan:  parsed content_plan dict (data/marketing/content_plan.json).
        root:  repo root; used to look up cashtag_tiers.json.

    Returns:
        {
            "joined": [row + dims],   # rows that matched a queue post
            "orphans": [row + {orphan: True}],  # unmatched rows — never dropped
        }

    Joined rows gain dims:
        kind, account, slot, persona, mode, cashtag_tier
    Orphan rows gain flag {"orphan": True}.
    """
    post_index = _build_post_index(plan)

    # Load cashtag tiers if available (future Radar artifact)
    cashtag_tiers: dict[str, str] = {}
    tiers_path = _cashtag_tiers_path(root)
    if tiers_path.exists():
        try:
            cashtag_tiers = json.loads(tiers_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            log.warning("telemetry.join_provenance: failed to load cashtag_tiers: %s", exc)

    joined: list[dict[str, Any]] = []
    orphans: list[dict[str, Any]] = []

    for row in rows:
        pid = row.get("post_id", "")
        dims = post_index.get(pid)
        if dims is None:
            orphan_row = dict(row)
            orphan_row["orphan"] = True
            orphans.append(orphan_row)
            continue

        enriched = dict(row)
        enriched["kind"] = dims["kind"]
        enriched["account"] = dims["account"]
        enriched["slot"] = dims["slot"]
        enriched["persona"] = dims["persona"]
        enriched["mode"] = dims["mode"]

        # Cashtag tier: look up by post cashtag if tiers available
        cashtag = row.get("cashtag", "").lstrip("$").upper()
        enriched["cashtag_tier"] = cashtag_tiers.get(cashtag, "unknown")

        joined.append(enriched)

    return {"joined": joined, "orphans": orphans}


# ─────────────────────────────────────────────────────────────────────────────
# Roll-up
# ─────────────────────────────────────────────────────────────────────────────

_DIM_KEYS = ("kind", "account", "persona", "slot", "mode", "cashtag_tier")


def _median_int(values: list[int]) -> float | None:
    """Compute median; returns None for empty list."""
    if not values:
        return None
    return statistics.median(values)


def rollup(
    joined: list[dict[str, Any]],
    orphans: list[dict[str, Any]],
    *,
    as_of: str | None = None,
) -> dict[str, Any]:
    """Compute the Lab roll-up artifact.

    Args:
        joined:  list of joined+enriched rows.
        orphans: list of orphan rows.
        as_of:   ISO date string; defaults to today UTC.

    Returns:
        Roll-up dict matching lab_rollup.json schema.

    N-floor law: any cell with n < _N_FLOOR carries verdict="seeding".
    Empty telemetry → valid artifact with n_posts=0.
    """
    if as_of is None:
        as_of = datetime.now(tz=timezone.utc).date().isoformat()

    # Unique post IDs with impressions data (joined only)
    n_posts = len({r["post_id"] for r in joined if "post_id" in r})
    n_rows = len(joined) + len(orphans)  # total telemetry rows received
    n_orphans = len(orphans)

    # Per-dimension cell aggregation
    # Group by the full dim tuple
    cell_map: dict[tuple, list[dict[str, Any]]] = {}
    for row in joined:
        key = tuple(row.get(k, "") for k in _DIM_KEYS)
        cell_map.setdefault(key, []).append(row)

    cells: list[dict[str, Any]] = []
    for key, cell_rows in cell_map.items():
        dims = dict(zip(_DIM_KEYS, key))

        # Dedupe: keep the row with the latest captured_at per post_id.
        # X metrics are cumulative so the latest capture is the current truth.
        # n counts unique posts, not telemetry rows.
        deduped_by_post: dict[str, dict[str, Any]] = {}
        for row in cell_rows:
            pid = row.get("post_id", "")
            if pid not in deduped_by_post:
                deduped_by_post[pid] = row
            else:
                existing_ts = str(deduped_by_post[pid].get("captured_at", ""))
                candidate_ts = str(row.get("captured_at", ""))
                if candidate_ts > existing_ts:
                    deduped_by_post[pid] = row
        deduped_rows = list(deduped_by_post.values())
        n = len(deduped_rows)  # unique post count

        def _med(field: str, rows: list[dict[str, Any]] = deduped_rows) -> float | None:
            vals = [r[field] for r in rows if isinstance(r.get(field), int)]
            return _median_int(vals)

        cell: dict[str, Any] = {
            "dims": dims,
            "n": n,
            "n_posts": n,
            "med_impressions": _med("impressions"),
            "med_likes": _med("likes"),
            "med_replies": _med("replies"),
            "med_reposts": _med("reposts"),
        }
        if n < _N_FLOOR:
            cell["verdict"] = "seeding"

        cells.append(cell)

    # Top 10 posts by impressions — deduped to latest capture per post_id first.
    # X metrics are cumulative so latest captured_at == current truth.
    def _impressions(r: dict) -> int:
        return r.get("impressions", 0) if isinstance(r.get("impressions"), int) else 0

    # Build global latest-capture-per-post (across all cells / dim combos)
    global_latest: dict[str, dict[str, Any]] = {}
    for row in joined:
        pid = row.get("post_id", "")
        if not pid:
            continue
        if pid not in global_latest:
            global_latest[pid] = row
        else:
            existing_ts = str(global_latest[pid].get("captured_at", ""))
            candidate_ts = str(row.get("captured_at", ""))
            if candidate_ts > existing_ts:
                global_latest[pid] = row

    sorted_deduped = sorted(global_latest.values(), key=_impressions, reverse=True)
    top_posts: list[dict[str, Any]] = []
    for row in sorted_deduped:
        pid = row.get("post_id", "")
        dims_out = {k: row.get(k, "") for k in _DIM_KEYS}
        top_posts.append(
            {
                "post_id": pid,
                "dims": dims_out,
                "impressions": _impressions(row),
                "likes": row.get("likes", 0),
                "replies": row.get("replies", 0),
            }
        )
        if len(top_posts) >= 10:
            break

    # Hypotheses: all seeding in W0; update n_evidence from joined count per hypothesis
    # (actual evidence counting deferred to W1 — W0 seeds them with n=0)
    hypotheses = [dict(h) for h in _SEED_HYPOTHESES]

    return {
        "schema": "marketing.lab_rollup/v1",
        "produced_by": "engine/marketing/telemetry.py",
        "as_of": as_of,
        "n_posts": n_posts,
        "n_rows": n_rows,
        "n_orphans": n_orphans,
        "cells": cells,
        "top_posts": top_posts,
        "hypotheses": hypotheses,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Orchestrator
# ─────────────────────────────────────────────────────────────────────────────

def write_rollup(
    root: Path | str | None = None,
    *,
    as_of: str | None = None,
) -> dict[str, Any]:
    """Read telemetry + content_plan, compute roll-up, write lab_rollup.json.

    Args:
        root:  repo root (None = auto-detect).
        as_of: ISO date override; defaults to today UTC.

    Returns:
        {"ok": True, "n_posts": N, "n_rows": M, "n_orphans": K, "path": str}
        or {"error": str, ...} on failure — never raises.
    """
    try:
        r = _repo_root(root)

        # Load telemetry
        rows = load_telemetry(r)

        # Load content plan
        plan: dict[str, Any] = {}
        cp = _content_plan_path(r)
        if cp.exists():
            try:
                plan = json.loads(cp.read_text(encoding="utf-8"))
            except Exception as exc:  # noqa: BLE001
                log.warning("telemetry.write_rollup: could not load content_plan: %s", exc)

        # Join
        join_result = join_provenance(rows, plan, root=r)
        joined = join_result["joined"]
        orphans = join_result["orphans"]

        # Compute rollup
        result = rollup(joined, orphans, as_of=as_of)

        # Atomic write
        out_path = _rollup_path(r)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_fd, tmp_name = tempfile.mkstemp(
            dir=out_path.parent, prefix=".lab_rollup_", suffix=".json"
        )
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            os.replace(tmp_name, out_path)
        except Exception:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise

        log.info("telemetry.write_rollup: wrote %s", out_path)
        return {
            "ok": True,
            "n_posts": result["n_posts"],
            "n_rows": result["n_rows"],
            "n_orphans": result["n_orphans"],
            "path": str(out_path),
        }

    except Exception as exc:  # noqa: BLE001
        log.warning("telemetry.write_rollup: failed: %s", exc, exc_info=True)
        return {"error": str(exc)}
