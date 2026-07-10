"""scripts/metabolism_digest.py — Operator weekly digest + observability (A8).

Produces a one-page markdown at data/metabolism/digest/<week>.md and sends a
Telegram summary.  The operator's window into the organism.

Content:
  - cycles run in the past 7 days (from journal directory)
  - proposals / grants / denies (from governance.jsonl)
  - PRs opened (from budget_ledger)
  - realized fitness deltas (from verify/<cycle_id>.json)
  - reverts issued (from verify triage)
  - budget spent (from budget_ledger)
  - circuit breaker trips (from budget_ledger lobe states)
  - AUTONOMY_PAUSED state
  - capability audit tape link

Exit 0 always.  NEVER raises.

Usage:
    python -m scripts.metabolism_digest [--root /path/to/repo] [--dry-run]
                                        [--week YYYY-WNN]
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
_ROOT = _HERE.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger("metabolism_digest")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

_DIGEST_DIR = Path("data") / "metabolism" / "digest"
_JOURNAL_DIR = Path("data") / "metabolism" / "journal"
_VERIFY_DIR = Path("data") / "metabolism" / "verify"
_BUDGET_LEDGER = Path("data") / "metabolism" / "budget_ledger.json"
_GOVERNANCE_LEDGER = Path("data") / "neuralweb" / "governance.jsonl"
_CAPABILITY_AUDIT = Path("data") / "neuralweb" / "capability_audit.jsonl"


def _week_label(now: datetime) -> str:
    """Return ISO week label: YYYY-WNN (e.g. 2026-W28)."""
    iso = now.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def _load_jsonl(path: Path, since: datetime | None = None) -> list[dict]:
    """Load all rows from a JSONL file, optionally filtering by 'ts' >= since."""
    if not path.exists():
        return []
    rows = []
    since_str = since.isoformat() if since else None
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
            if since_str and r.get("ts", "") < since_str:
                continue
            rows.append(r)
        except Exception:  # noqa: BLE001
            continue
    return rows


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _count_journals(root: Path, since: datetime) -> dict[str, int]:
    """Count cycle journals by status in the past 7 days."""
    journal_dir = root / _JOURNAL_DIR
    counts: dict[str, int] = {"total": 0, "done": 0, "failed": 0, "noop_paused": 0, "running": 0}
    if not journal_dir.exists():
        return counts
    since_str = since.isoformat()
    for jf in journal_dir.glob("*.json"):
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
            ts = data.get("ts") or ""
            if ts < since_str:
                continue
            counts["total"] += 1
            status = data.get("status", "")
            if status in counts:
                counts[status] += 1
        except Exception:  # noqa: BLE001
            continue
    return counts


def _count_governance(root: Path, since: datetime) -> dict[str, int]:
    """Count metabolism-related governance events from governance.jsonl."""
    gov_path = root / _GOVERNANCE_LEDGER
    rows = _load_jsonl(gov_path, since=since)
    # Filter to metabolism events
    metab_rows = [r for r in rows if "metabolism" in r.get("target", "").lower()
                  or "metabolism" in r.get("authored_by", "").lower()]
    counts: dict[str, int] = {}
    for r in metab_rows:
        et = r.get("event_type", "unknown")
        counts[et] = counts.get(et, 0) + 1
    return counts


def _collect_verify_summary(root: Path, since: datetime) -> dict[str, Any]:
    """Scan verify/<cycle_id>.json files and summarize outcomes."""
    verify_dir = root / _VERIFY_DIR
    summary = {
        "total": 0,
        "confirmed": 0,
        "overfit_revert_plans": 0,
        "operator_taps": 0,
        "pending": 0,
        "unverifiable": 0,
    }
    if not verify_dir.exists():
        return summary
    since_str = since.isoformat()
    for vf in verify_dir.glob("*.json"):
        try:
            data = json.loads(vf.read_text(encoding="utf-8"))
            ts = data.get("ts") or ""
            if ts < since_str:
                continue
            summary["total"] += 1
            action = data.get("triage", {}).get("action", "")
            classification = data.get("triage", {}).get("classification", "")
            if classification == "confirmed":
                summary["confirmed"] += 1
            elif action == "revert_plan":
                summary["overfit_revert_plans"] += 1
            elif action == "operator_tap":
                summary["operator_taps"] += 1
            elif classification == "pending":
                summary["pending"] += 1
            else:
                summary["unverifiable"] += 1
        except Exception:  # noqa: BLE001
            continue
    return summary


def _budget_summary(root: Path) -> dict[str, Any]:
    """Read the budget ledger for spend and circuit breaker summary."""
    ledger = _load_json(root / _BUDGET_LEDGER)
    lobes = ledger.get("lobes") or {}
    tripped = [l for l, s in lobes.items() if s.get("paused")]
    return {
        "cycle_id": ledger.get("cycle_id"),
        "usd_cap": ledger.get("usd_cap"),
        "usd_spent": ledger.get("usd_spent", 0.0),
        "token_spent": ledger.get("token_spent", 0),
        "entries_count": len(ledger.get("entries") or []),
        "breaker_tripped_lobes": tripped,
    }


def _autonomy_state() -> str:
    """Return the current AUTONOMY_PAUSED state as a readable string."""
    val = os.environ.get("AUTONOMY_PAUSED", "<unset>")
    try:
        from scripts.metabolism_guard import is_paused, pause_reason  # type: ignore[import]
        return f"{val!r} → {'PAUSED' if is_paused() else 'ARMED'}: {pause_reason()}"
    except Exception:  # noqa: BLE001
        return f"AUTONOMY_PAUSED={val!r}"


def build_operator_onepager(root: Path, now: datetime) -> str:
    """Build the V2-D operator one-pager: FIXED FOUR-HEADING plain-English contract.

    Phone-readable, plain language, NO internal metric jargon.
    Headings: 'What got better' / 'What's slipping' / 'What I'm about to do' /
              'What needs your tap'.
    This is the operator relationship: minimal work, plain language.

    The dense digest (build_digest) is ADMIN-tier and is linked, not pushed.
    NEVER raises.
    """
    try:
        week = _week_label(now)
        since = now - timedelta(days=7)

        journal_counts = _count_journals(root, since)
        verify = _collect_verify_summary(root, since)
        budget = _budget_summary(root)
        gov_counts = _count_governance(root, since)
        auto_state = _autonomy_state()

        # ── Section: What got better ─────────────────────────────────────────
        better: list[str] = []
        if verify["confirmed"] > 0:
            better.append(
                f"{verify['confirmed']} building block(s) held their targets and are still running."
            )
        if journal_counts["done"] > 0 and journal_counts["failed"] == 0:
            better.append(
                f"All {journal_counts['done']} checks ran cleanly this week — no failures."
            )
        elif journal_counts["done"] > 0:
            better.append(
                f"{journal_counts['done']} checks ran this week."
            )
        grants = gov_counts.get("metabolism_adjudication", 0)
        if grants > 0:
            better.append(f"{grants} new build proposal(s) cleared review.")
        if not better:
            better.append("Nothing new confirmed this week — still early in the accrual period.")

        # ── Section: What's slipping ─────────────────────────────────────────
        slipping: list[str] = []
        if verify["overfit_revert_plans"] > 0:
            slipping.append(
                f"{verify['overfit_revert_plans']} building block(s) missed their target "
                f"— a reversal plan has been drafted for your review."
            )
        if verify["operator_taps"] > 0:
            slipping.append(
                f"{verify['operator_taps']} outcome(s) are ambiguous (possibly a market-regime shift "
                f"rather than a real miss) — held for your call, not auto-reversed."
            )
        if journal_counts["failed"] > 0:
            slipping.append(
                f"{journal_counts['failed']} check(s) hit an error this week."
            )
        if budget["breaker_tripped_lobes"]:
            lobes_str = ", ".join(budget["breaker_tripped_lobes"])
            slipping.append(f"Spending limit hit for: {lobes_str} — those areas are paused.")
        if not slipping:
            slipping.append("Nothing is slipping this week.")

        # ── Section: What I'm about to do ────────────────────────────────────
        upcoming: list[str] = []
        upcoming.append("Run the weekly calibration pass over past proposals.")
        if verify["pending"] > 0:
            upcoming.append(
                f"Wait on {verify['pending']} pending outcome(s) — their check dates haven't arrived yet."
            )
        upcoming.append(
            f"Budget status: about ${budget['usd_spent']:.2f} of ${budget['usd_cap']} used."
        )
        usd_remaining = (budget["usd_cap"] or 0) - (budget["usd_spent"] or 0)
        if usd_remaining is not None and budget["usd_cap"] and usd_remaining < budget["usd_cap"] * 0.2:
            upcoming.append("Heads up: spending budget is getting low (under 20% remaining).")

        # ── Section: What needs your tap ─────────────────────────────────────
        needs_tap: list[str] = []
        # Load open tap cards
        tap_dir = root / "data" / "metabolism" / "tap"
        if tap_dir.exists():
            tap_files = sorted(tap_dir.glob("*.json"))
            for tf in tap_files[-3:]:  # show at most 3 most recent
                try:
                    tc = json.loads(tf.read_text(encoding="utf-8"))
                    headline = tc.get("headline", "")
                    why_now = tc.get("why_now", "")
                    rec = tc.get("recommended_default", "defer")
                    if headline:
                        needs_tap.append(
                            f"**{headline}** — {why_now} "
                            f"(suggested: {rec}; auto-action on timeout: "
                            f"{tc.get('auto_action_on_timeout', {}).get('action', 'defer')})"
                        )
                except Exception:  # noqa: BLE001
                    continue
        if verify["overfit_revert_plans"] > 0:
            needs_tap.append(
                f"Review {verify['overfit_revert_plans']} reversal plan(s) "
                f"— they're waiting for your go-ahead before anything rolls back."
            )
        if not needs_tap:
            needs_tap.append("Nothing needs your attention this week — keep going.")

        # ── Compose the one-pager ─────────────────────────────────────────────
        arm_status = "Armed" if "ARMED" in auto_state.upper() else "Paused (safe)"
        lines = [
            f"# Weekly Check-In — {week}",
            f"",
            f"*System status: {arm_status}*",
            f"",
            f"## What got better",
            f"",
        ]
        for b in better:
            lines.append(f"- {b}")
        lines.extend([
            f"",
            f"## What's slipping",
            f"",
        ])
        for s in slipping:
            lines.append(f"- {s}")
        lines.extend([
            f"",
            f"## What I'm about to do",
            f"",
        ])
        for u in upcoming:
            lines.append(f"- {u}")
        lines.extend([
            f"",
            f"## What needs your tap",
            f"",
        ])
        for n in needs_tap:
            lines.append(f"- {n}")
        lines.extend([
            f"",
            f"---",
            f"",
            f"*Full technical digest (admin): data/metabolism/digest/{week}.md*",
        ])

        return "\n".join(lines) + "\n"
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_digest.build_operator_onepager: %s", exc)
        return f"# Weekly Check-In ERROR\n\nError building one-pager: {exc}\n"


def build_digest(root: Path, now: datetime) -> str:
    """Build the weekly digest markdown string.  Never raises."""
    try:
        week = _week_label(now)
        since = now - timedelta(days=7)

        journal_counts = _count_journals(root, since)
        gov_counts = _count_governance(root, since)
        verify = _collect_verify_summary(root, since)
        budget = _budget_summary(root)
        auto_state = _autonomy_state()

        capability_audit_path = root / _CAPABILITY_AUDIT
        audit_link = str(capability_audit_path) if capability_audit_path.exists() else "(not yet present)"

        lines = [
            f"# Metabolism Weekly Digest — {week}",
            f"",
            f"Generated: {now.isoformat(timespec='seconds')} UTC",
            f"",
            f"## Kill-switch state",
            f"",
            f"AUTONOMY_PAUSED: {auto_state}",
            f"",
            f"## Cycles (past 7 days)",
            f"",
            f"- Total cycles started: {journal_counts['total']}",
            f"- Done: {journal_counts['done']}",
            f"- Failed: {journal_counts['failed']}",
            f"- Noop (paused): {journal_counts['noop_paused']}",
            f"- Still running: {journal_counts['running']}",
            f"",
            f"## Governance events (metabolism-related)",
            f"",
        ]
        if gov_counts:
            for et, n in sorted(gov_counts.items()):
                lines.append(f"- {et}: {n}")
        else:
            lines.append("- (none in the past 7 days)")
        lines.extend([
            f"",
            f"## Verify outcomes (past 7 days)",
            f"",
            f"- Total verified: {verify['total']}",
            f"- Confirmed (contract held): {verify['confirmed']}",
            f"- Overfit revert plans emitted: {verify['overfit_revert_plans']}",
            f"- Operator tap requests: {verify['operator_taps']}",
            f"- Pending (check_by not yet arrived): {verify['pending']}",
            f"- Unverifiable: {verify['unverifiable']}",
            f"",
            f"## Budget",
            f"",
            f"- Current cycle: {budget['cycle_id'] or 'N/A'}",
            f"- USD cap: ${budget['usd_cap']}",
            f"- USD spent: ${budget['usd_spent']:.4f}",
            f"- Token spent: {budget['token_spent']:,}",
            f"- Spend events: {budget['entries_count']}",
        ])
        if budget["breaker_tripped_lobes"]:
            lines.append(f"- CIRCUIT BREAKER TRIPPED for lobes: {', '.join(budget['breaker_tripped_lobes'])}")
        else:
            lines.append("- Circuit breaker: OK (no lobes paused)")
        lines.extend([
            f"",
            f"## Capability audit tape",
            f"",
            f"Path: {audit_link}",
            f"",
            f"---",
            f"",
            f"*This digest is generated by scripts/metabolism_digest.py (A8) and is display-context only.*",
            f"*All values are accruing until Phase A is armed and cycles complete.*",
        ])

        return "\n".join(lines) + "\n"
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_digest.build_digest: %s", exc)
        return f"# Metabolism Digest ERROR\n\nError building digest: {exc}\n"


def _write_digest(content: str, root: Path, week: str) -> Path | None:
    """Atomically write the digest to data/metabolism/digest/<week>.md."""
    try:
        d = root / _DIGEST_DIR
        d.mkdir(parents=True, exist_ok=True)
        p = d / f"{week}.md"
        tmp = p.with_suffix(".tmp")
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(p)
        return p
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_digest._write_digest: %s", exc)
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Metabolism operator digest (A8)")
    parser.add_argument("--root", default=None)
    parser.add_argument("--dry-run", action="store_true", help="Print instead of writing")
    parser.add_argument("--week", default=None, help="Override week label (YYYY-WNN)")
    parser.add_argument("--no-notify", action="store_true", help="Skip Telegram notification")
    args = parser.parse_args(argv)

    root = Path(args.root) if args.root else _ROOT
    now = datetime.now(timezone.utc)

    content = build_digest(root, now)
    week = args.week or _week_label(now)

    if args.dry_run:
        print("=== OPERATOR ONE-PAGER ===")
        onepager = build_operator_onepager(root, now)
        print(onepager)
        print("=== ADMIN DIGEST ===")
        print(content)
        return 0

    # Write admin digest (ADMIN-tier, not pushed to phone)
    out_path = _write_digest(content, root, week)
    if out_path:
        log.info("metabolism_digest: wrote admin digest %s", out_path)

    # Write operator one-pager (separate file)
    onepager = build_operator_onepager(root, now)
    onepager_path = _write_digest(onepager, root, f"{week}-onepager")
    if onepager_path:
        log.info("metabolism_digest: wrote operator one-pager %s", onepager_path)

    if not args.no_notify:
        try:
            from scripts.notify import send_telegram  # type: ignore[import]
            # Push the operator one-pager to Telegram (phone-readable, plain language)
            # The dense admin digest is NEVER pushed — it's linked in the one-pager footer.
            telegram_msg = onepager[:2000] + (
                "\n...(full one-pager on disk)" if len(onepager) > 2000 else ""
            )
            send_telegram(telegram_msg)
        except Exception as exc:  # noqa: BLE001
            log.warning("metabolism_digest: telegram notify failed: %s", exc)

    return 0


if __name__ == "__main__":
    sys.exit(main())
