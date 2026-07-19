"""scripts/marketing_actuator.py — D02 posting-queue actuator (W0: dry-run only).

Usage:
    python -m scripts.marketing_actuator --dry-run
    python scripts/marketing_actuator.py --dry-run [--no-apply] [--root DIR]

What a dry run does:
  1. Applies pending operator approvals (outbox.apply_decisions — batch, one
     fold): queued→approved, plus governed re-arm of failed items (fresh
     approval only; auto-quarantine at MAX_POST_ATTEMPTS per docket W1 §7).
  2. Renders exactly what WOULD be posted (text + media paths) into
     data/marketing/outbox/dryrun_report.json, with per-item cap flags.
  3. Echoes the Sentinel contract the W1 publisher must honour (caps, spacing
     floor, link/media policy) — read from config, never hardcoded here
     (config/marketing.yml sentinel: LAW).
  4. Appends a run row to data/marketing/outbox/activity.jsonl so the admin
     Outbox page shows actuator activity.

Live actuation is W1 (operator accounts/browser profiles not provisioned);
without --dry-run this script refuses (exit 2).

ZERO network imports.  Never reads or writes content_plan.json.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from collections import defaultdict
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
    # The data root (--root) controls where data is read/written; the code
    # root is always the directory containing engine/ (where this script
    # lives), NOT the --root data directory.
    code_root = Path(__file__).resolve().parent.parent
    if str(code_root) not in sys.path:
        sys.path.insert(0, str(code_root))

    from engine.marketing import outbox as _outbox  # noqa: PLC0415
    try:
        from engine.marketing.sentinel import publish_enabled as _publish_enabled  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        def _publish_enabled() -> bool:  # conservative fallback: switch off
            return False

    cfg = _load_marketing_cfg(root)
    contract = _outbox.sentinel_contract(cfg)
    cap = contract["effective_cap"]

    # 1. Apply operator decisions (batch, one fold) unless --no-apply
    applied = {"approved": [], "rearmed": [], "quarantined": []}
    if not args.no_apply:
        applied = _outbox.apply_decisions(
            root, actor="actuator", note="operator approval applied (dry-run)"
        )

    # 2. Fold once for the report
    state = _outbox.fold_state(root)
    items_by_id = state["items"]
    statuses = state["status"]
    held_ids = sorted(state["held"])

    # Counts — held and queued are DISJOINT here (held = queued + hold
    # decision), matching the admin Outbox panel semantics.
    count_map: dict[str, int] = {
        s: 0 for s in ("queued", "approved", "posted", "failed", "quarantined")
    }
    for item_id, status in statuses.items():
        count_map[status] = count_map.get(status, 0) + 1
    count_map["held"] = len(held_ids)
    count_map["queued"] = max(0, count_map["queued"] - len(held_ids))

    # 3. Approved items → would-post entries, priority then schedule order
    approved_items = [
        items_by_id[i] for i, s in statuses.items() if s == "approved" and i in items_by_id
    ]
    approved_items.sort(key=lambda i: (i.get("priority", 5), i.get("scheduled_at", "")))

    # Cap accounting: posted items already consumed slots today
    account_day_counts: dict[tuple[str, str], int] = defaultdict(int)
    for item_id, status in statuses.items():
        if status == "posted" and item_id in items_by_id:
            item = items_by_id[item_id]
            account_day_counts[(item.get("account", ""), item.get("as_of", ""))] += 1

    would_post: list[dict] = []
    for item in approved_items:
        account = item.get("account", "")
        as_of = item.get("as_of", "")
        account_day_counts[(account, as_of)] += 1
        over_cap = account_day_counts[(account, as_of)] > cap

        entry: dict = {
            "id": item["id"],
            "account": account,
            "kind": item.get("kind", ""),
            "scheduled_at": item.get("scheduled_at", ""),
            "slot": item.get("slot"),
            "priority": item.get("priority", 5),
            "provenance": item.get("provenance", ""),
            "attempts": state["attempts"].get(item["id"], 0),
            "chars": len(item.get("text", "")),
            "text": item.get("text", ""),
            "media": [
                {
                    "path": m.get("path", ""),
                    "exists": (root / m.get("path", "")).exists() if m.get("path") else False,
                }
                for m in (item.get("media") or [])
            ],
            "would_exceed_cap": over_cap,
        }
        would_post.append(entry)

    # 4. Kill-switch echo (sentinel owns the semantics; raw env echoed for ops)
    kill_switch = {
        "publish_enabled": _publish_enabled(),
        "MARKETING_PUBLISH_ENABLED": os.environ.get("MARKETING_PUBLISH_ENABLED") or "unset",
    }

    # 5. Report
    report = {
        "schema": "marketing.outbox.dryrun/v2",
        "generated_at": _iso_now(),
        "dry_run": True,
        "kill_switch": kill_switch,
        "counts": {"items_total": len(items_by_id), **count_map},
        "cap": cap,
        "sentinel": contract,
        "applied_decisions": applied,
        "would_post": would_post,
        "held": held_ids,
    }

    report_path = root / "data" / "marketing" / "outbox" / "dryrun_report.json"
    _write_json_atomic(report_path, report)

    # 6. Activity row for the admin Outbox page
    try:
        _outbox._append_activity(root, {
            "at": report["generated_at"],
            "lane": "actuator_dry_run",
            "counts": report["counts"],
            "cap": cap,
            "applied": {k: len(v) for k, v in applied.items()},
            "would_post": len(would_post),
        })
    except Exception:  # noqa: BLE001
        pass

    # 7. Human-readable summary, grouped by account
    c = report["counts"]
    print(
        f"outbox dry-run | total={c['items_total']} queued={c['queued']} "
        f"held={c['held']} approved={c['approved']} posted={c['posted']} "
        f"failed={c['failed']} quarantined={c['quarantined']} | cap={cap}/day "
        f"spacing>={contract['min_minutes_between_posts']}m "
        f"links={'on' if contract['links_allowed'] else 'off'} "
        f"publish={'ON' if kill_switch['publish_enabled'] else 'off'}"
    )
    if any(applied.values()):
        print(
            f"  decisions applied: approved={len(applied['approved'])} "
            f"re-armed={len(applied['rearmed'])} quarantined={len(applied['quarantined'])}"
        )
    by_account: dict[str, list[dict]] = defaultdict(list)
    for entry in would_post:
        by_account[entry["account"]].append(entry)
    for account in sorted(by_account):
        print(f"  {account}:")
        for entry in by_account[account]:
            media_count = len(entry.get("media") or [])
            flags = ""
            if entry.get("would_exceed_cap"):
                flags += " [WOULD_EXCEED_CAP]"
            if entry.get("attempts"):
                flags += f" [attempt {entry['attempts'] + 1}]"
            print(
                f"    {entry['kind']:<10} {entry['chars']:>3}ch  "
                f"{entry['scheduled_at']}  media={media_count}{flags}"
            )
    if not would_post:
        print("  nothing approved to post — approve items in the admin Outbox first")

    return 0


if __name__ == "__main__":
    sys.exit(main())
