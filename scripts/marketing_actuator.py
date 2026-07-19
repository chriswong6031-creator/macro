"""scripts/marketing_actuator.py — D02 posting-queue actuator (W0: dry-run only).

Usage:
    python -m scripts.marketing_actuator --dry-run
    python scripts/marketing_actuator.py --dry-run

Live actuation is W1 (operator accounts/browser profiles not provisioned).
Run with --dry-run to inspect the queue without posting.

ZERO network imports.  Never reads or writes content_plan.json.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def _repo_root(root_arg: str | None) -> Path:
    if root_arg is not None:
        return Path(root_arg)
    # Derive from script location: scripts/ is one level below repo root
    return Path(__file__).resolve().parent.parent


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_json_atomic(path: Path, obj: dict) -> None:
    """Atomic write via temp file in the same directory.

    House law: never open('w') directly on the target — always temp+os.replace.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=path.parent, prefix=".tmp_actuator_", suffix=".json"
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except Exception:  # noqa: BLE001
            pass
        raise


def _load_marketing_cfg(root: Path) -> dict:
    """Load config/marketing.yml fail-soft; return {} on any error."""
    try:
        import yaml  # type: ignore[import-untyped]
        cfg_path = root / "config" / "marketing.yml"
        if cfg_path.exists():
            return yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    except Exception:  # noqa: BLE001
        pass
    return {}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Marketing posting-queue actuator (D02 W0 — dry-run only)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Inspect the queue and produce a dryrun_report.json (no posting)",
    )
    parser.add_argument(
        "--no-apply",
        action="store_true",
        help="Skip applying operator decisions; just report current state",
    )
    parser.add_argument(
        "--root",
        default=None,
        help="Repo root directory (default: derived from script location)",
    )
    args = parser.parse_args(argv)

    if not args.dry_run:
        print(
            "live actuation is W1 (operator accounts/browser profiles not provisioned)"
            " — refusing; run with --dry-run",
            file=sys.stderr,
        )
        return 2

    root = _repo_root(args.root)

    # Ensure the code root (where engine/ lives) is importable.
    # The data root (--root / args.root) controls where data is read/written;
    # the code root is always the directory that contains engine/ (the actual
    # repo root where this script lives, NOT the --root data directory).
    code_root = Path(__file__).resolve().parent.parent
    if str(code_root) not in sys.path:
        sys.path.insert(0, str(code_root))

    from engine.marketing import outbox as _outbox  # noqa: PLC0415

    cfg = _load_marketing_cfg(root)
    cap = _outbox.effective_cap(cfg)

    # 1. Load items, statuses, decisions
    items = _outbox.read_items(root)
    statuses = _outbox.current_statuses(root)
    decisions = _outbox.latest_decisions(root)

    # 2. Apply operator decisions (unless --no-apply)
    if not args.no_apply:
        for item_id, dec_row in decisions.items():
            decision = dec_row.get("decision")
            current_status = statuses.get(item_id, "queued")
            if decision == "approve" and current_status == "queued":
                _outbox.transition(
                    item_id,
                    "approved",
                    actor="actuator",
                    root=root,
                    note="operator approval applied (dry-run)",
                )
            # "hold" decisions leave status queued — no transition needed

    # 3. Re-fold statuses after applying decisions
    statuses = _outbox.current_statuses(root)

    # 4. Build report of approved items
    # Build an item lookup by id
    item_by_id: dict[str, dict] = {i["id"]: i for i in items}

    # Counts
    count_map: dict[str, int] = {s: 0 for s in ("queued", "approved", "posted", "failed", "quarantined")}
    held_ids: list[str] = []
    approved_items: list[dict] = []

    for item_id, status in statuses.items():
        count_map[status] = count_map.get(status, 0) + 1

    # Identify held items: status queued AND latest decision is "hold"
    for item_id, status in statuses.items():
        if status == "queued":
            dec = decisions.get(item_id, {})
            if dec.get("decision") == "hold":
                held_ids.append(item_id)

    # Approved items sorted by scheduled_at, then priority
    for item_id, status in statuses.items():
        if status == "approved":
            item = item_by_id.get(item_id, {})
            if item:
                approved_items.append(item)

    # Sort by priority (lower = higher priority), then scheduled_at
    approved_items.sort(key=lambda i: (i.get("priority", 5), i.get("scheduled_at", "")))

    # 5. Cap check: per (account, as_of), flag would_exceed_cap on items beyond cap
    # in scheduled order (approved + posted count against the cap)
    from collections import defaultdict
    account_day_counts: dict[tuple[str, str], int] = defaultdict(int)

    # Count already-posted items toward the cap
    for item in items:
        item_id = item["id"]
        st = statuses.get(item_id, "queued")
        if st == "posted":
            key = (item.get("account", ""), item.get("as_of", ""))
            account_day_counts[key] += 1

    would_post: list[dict] = []
    for item in approved_items:
        account = item.get("account", "")
        as_of = item.get("as_of", "")
        key = (account, as_of)
        account_day_counts[key] += 1
        over_cap = account_day_counts[key] > cap

        media_list = item.get("media") or []
        entry: dict = {
            "id": item["id"],
            "account": account,
            "kind": item.get("kind", ""),
            "scheduled_at": item.get("scheduled_at", ""),
            "slot": item.get("slot"),
            "priority": item.get("priority", 5),
            "provenance": item.get("provenance", ""),
            "chars": len(item.get("text", "")),
            "text": item.get("text", ""),
            "media": [
                {
                    "path": m.get("path", ""),
                    "exists": (root / m.get("path", "")).exists() if m.get("path") else False,
                }
                for m in media_list
            ],
            "would_exceed_cap": over_cap,
        }
        would_post.append(entry)

    # 6. Kill-switch echo
    kill_switch = {
        "MARKETING_PUBLISH_ENABLED": os.environ.get("MARKETING_PUBLISH_ENABLED") or "unset",
    }

    # 7. Build and write dryrun_report.json atomically
    report = {
        "schema": "marketing.outbox.dryrun/v1",
        "generated_at": _iso_now(),
        "dry_run": True,
        "kill_switch": kill_switch,
        "counts": {
            "items_total": len(items),
            "queued": count_map.get("queued", 0),
            "approved": count_map.get("approved", 0),
            "held": len(held_ids),
            "posted": count_map.get("posted", 0),
            "failed": count_map.get("failed", 0),
            "quarantined": count_map.get("quarantined", 0),
        },
        "cap": cap,
        "would_post": would_post,
        "held": held_ids,
    }

    report_path = root / "data" / "marketing" / "outbox" / "dryrun_report.json"
    _write_json_atomic(report_path, report)

    # 8. Human-readable summary
    counts = report["counts"]
    print(
        f"outbox dry-run | total={counts['items_total']} "
        f"queued={counts['queued']} approved={counts['approved']} "
        f"held={counts['held']} posted={counts['posted']} "
        f"failed={counts['failed']} quarantined={counts['quarantined']} "
        f"cap={cap}"
    )
    for entry in would_post:
        media_count = len(entry.get("media") or [])
        cap_flag = " [WOULD_EXCEED_CAP]" if entry.get("would_exceed_cap") else ""
        print(
            f"  [{entry['account']}] {entry['kind']} "
            f"{entry['chars']}ch "
            f"scheduled={entry['scheduled_at']} "
            f"media={media_count}{cap_flag}"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
