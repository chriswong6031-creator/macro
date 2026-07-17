"""Consecutive-failure escalation for resilient brun() builders — daily.yml ENGINE job + asia-close.yml CN/HK bands.

Reads the band scratch dir ($RUNNER_TEMP/band/<slug>.rc + <slug>.log) written by
the parallelised regional + desk builders step.  Maintains a per-builder streak
ledger (data/ci/builder_failstreaks.json) and escalates loudly when any builder
has failed for N consecutive nightlies — making a sustained page freeze visible
even while the nightly stays green.

Background: brun() BY DESIGN never aborts on a non-zero exit (::error:: +
step summary only, site still deploys).  This is correct — one broken builder
must not 404 the whole dashboard.  The visibility gap is that a builder failing
MANY CONSECUTIVE nights (e.g. build_cycle 2026-07-16/17) looks identical to a
one-off at a glance.  cycle.html silently froze while the run stayed green.
This script fixes that gap.

Design principles (house laws):
 - Lane-gated writes: each write lane advances exactly ONE ledger (nightly ->
   data/ci/builder_failstreaks.json; asia -> data/ci/builder_failstreaks_asia.json
   — asia-close.yml is the sole nightly for the CN/HK pages so it owns a
   separate forward ledger).  A write lane pointing at another lane's ledger
   degrades to report-only (loud warning) — this stops a misconfigured port
   or a copy-paste into closing-bell.yml from advancing another lane's ledger.
   Unmapped lanes (closing-bell) never write, exactly as in #2738.
 - Fail-open: any read/parse failure degrades gracefully; exit 0 always.
 - Idempotent same-day reruns: same UTC date re-run does NOT increment the
   streak (last_rc / label updated only).
 - Gap tolerance: a streak is preserved across runs whose last_run_utc is within
   max-gap-days calendar days (runner starvation sometimes kills the nightly
   before the band step; a builder broken across such a gap is still one
   continuous freeze).
 - Stale-escalation decay (write lane, non-empty rc set): if a ledger entry's
   slug is absent from this run's rc-file set, the builder was renamed or
   retired; the entry is dropped immediately so it does not re-enter the
   breached list for up to prune-days days.  Trade-off: a mid-band cancellation
   that wrote only SOME rc files can drop a real streak (it restarts at 1 the
   next night) — accepted; the alternative (keeping absent slugs) produces
   30-day zombie alerts on renames, which is worse.  In the multi-dir case:
   if ONE band died but the other wrote rc files, the union is non-empty and
   the dead band's slugs decay (restarting their streaks at 1 next run) —
   same accepted trade-off.  Guard: if the rc set is EMPTY (all art dirs
   missing or crashed before writing any .rc files), the ledger is NOT mutated
   and escalation from ledger-only state is suppressed — real streaks must not
   be wiped by a run where the band itself died.
 - Prune: entries older than prune-days are dropped so removed builders leave
   no zombie rows (belt-and-braces; mostly superseded by the decay rule above
   on write lanes).
 - Escalation fires every night while breached (pressure intentional; dedup is
   the W6b spine's job).
 - Dispatch-always invariant: push_ops_alert is dispatch-always for ops lanes.
 - Maintenance vocabulary only: no trading verbs in composed messages.
 - Atomic-ish write: tmp file then os.replace so the commit step never reads a
   partial write.
 - Article 2: ops-tier alerting via ratified W6b spine only.

Run IMMEDIATELY AFTER the builder band step(s) in daily.yml ENGINE job and
asia-close.yml CN/HK nightly.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

try:
    from lib.logging import get_logger
    log = get_logger(__name__)
except Exception:  # noqa: BLE001
    import logging
    log = logging.getLogger(__name__)

# ── constants ──────────────────────────────────────────────────────────────
_DEFAULT_LEDGER = "data/ci/builder_failstreaks.json"
_DEFAULT_THRESHOLD = 2
_DEFAULT_MAX_GAP_DAYS = 4
_DEFAULT_PRUNE_DAYS = 30
# lane -> the ONE repo-root-relative ledger that lane may advance (sole-advancer law).
# daily.yml's ENGINE job owns the US nightly ledger; asia-close.yml is the SOLE
# nightly for the CN/HK pages, so it owns its own, separate forward ledger. A write
# lane whose --ledger does not resolve to its owned path degrades to report-only
# (loud warning) — this stops a misconfigured port (or a copy-paste into
# closing-bell.yml) from advancing another lane's ledger. Lanes not in this map
# (e.g. closingbell) never write, exactly as in #2738.
_WRITE_LANES: dict[str, str] = {
    "nightly": "data/ci/builder_failstreaks.json",
    "asia": "data/ci/builder_failstreaks_asia.json",
}

# Trading-verb blacklist (mirrors engine/neuralweb/daily_brief.py TRADING_VERBS).
# Message assembly must not produce any of these words.
_TRADING_VERBS = frozenset({
    "buy", "sell", "hold", "add", "trim", "long", "short",
    "overweight", "underweight",
})


# ── helpers ────────────────────────────────────────────────────────────────


def _root_dir() -> Path:
    """Repo root (two parents above scripts/)."""
    return Path(__file__).resolve().parent.parent


def _load_ledger(ledger_path: Path) -> dict[str, Any]:
    """Load the builder_failstreaks.json ledger; return skeleton on any error."""
    skeleton: dict[str, Any] = {
        "schema": "builder_failstreaks.v1",
        "updated_utc": None,
        "builders": {},
    }
    if not ledger_path.exists():
        return skeleton
    try:
        raw = ledger_path.read_text(encoding="utf-8")
        data = json.loads(raw)
        if not isinstance(data, dict):
            log.warning("check_builder_failstreaks: ledger is not a dict — treating as empty")
            return skeleton
        # Ensure builders key present
        if "builders" not in data or not isinstance(data["builders"], dict):
            data["builders"] = {}
        return data
    except Exception as exc:  # noqa: BLE001
        log.warning("check_builder_failstreaks: ledger unreadable (%s) — starting fresh", exc)
        return skeleton


def _save_ledger(ledger_path: Path, data: dict[str, Any]) -> None:
    """Atomic-ish write: tmp in same dir then os.replace (fail-open)."""
    try:
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        # Write to a sibling tmp file, then atomically replace
        fd, tmp_path = tempfile.mkstemp(
            dir=ledger_path.parent,
            prefix=".builder_failstreaks_tmp_",
            suffix=".json",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2)
                fh.write("\n")
            os.replace(tmp_path, ledger_path)
        except Exception:  # noqa: BLE001
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
    except Exception as exc:  # noqa: BLE001
        log.warning("check_builder_failstreaks: could not save ledger (%s) — fail-open", exc)


def _read_label(art_dir: Path, slug: str) -> str:
    """First line of <slug>.log if readable, else the slug itself."""
    log_path = art_dir / f"{slug}.log"
    try:
        first_line = log_path.read_text(encoding="utf-8", errors="replace").splitlines()[0]
        return first_line.strip() or slug
    except Exception:  # noqa: BLE001
        return slug


def _check_trading_verbs(text: str) -> list[str]:
    """Return any trading verbs found in text (case-insensitive word-boundary check)."""
    import re
    found = []
    lower = text.lower()
    for verb in _TRADING_VERBS:
        if re.search(rf"\b{re.escape(verb)}\b", lower):
            found.append(verb)
    return found


def _emit_annotation(slug: str, streak: int, first_fail_utc: str, label: str, last_rc: int, *, ledger_ref: str = _DEFAULT_LEDGER) -> None:
    """Print a GitHub Actions ::error:: annotation for a breached builder."""
    title = f"BUILDER {slug} failed {streak} consecutive nightlies — page frozen since {first_fail_utc}"
    body = (
        f"{label} rc={last_rc} — output last refreshed before {first_fail_utc}; "
        f"see {ledger_ref}"
    )
    print(f"::error title={title}::{body}")


def _append_step_summary(breached: list[dict[str, Any]]) -> None:
    """Append a markdown section to GITHUB_STEP_SUMMARY if set."""
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY", "")
    if not summary_path:
        return
    try:
        lines = ["", "### 🔁 builder fail-streaks (consecutive nightlies)", ""]
        for b in breached:
            lines.append(
                f"- **{b['slug']}**: {b['streak']} consecutive nightlies, "
                f"frozen since {b['first_fail_utc']}, rc={b['last_rc']} — {b['label']}"
            )
        lines.append("")
        with open(summary_path, "a", encoding="utf-8") as fh:
            fh.write("\n".join(lines))
    except Exception as exc:  # noqa: BLE001
        log.warning("check_builder_failstreaks: could not write step summary (%s)", exc)


def _dispatch_ops_alert(breached: list[dict[str, Any]], root: Path, *, lane: str = "nightly") -> None:
    """Dispatch one combined ops alert through the W6b spine (fail-open)."""
    if not breached:
        return

    if lane and lane != "nightly":
        header = f"Builder fail-streaks ({lane} lane) — pages frozen while the run stays green"
        type_ = f"fail_streak_{lane}"
    else:
        header = "Nightly builder fail-streaks — pages frozen while the run stays green"
        type_ = "fail_streak"

    bullets = []
    for b in breached:
        bullets.append(
            f"• {b['slug']}: {b['streak']} consecutive nightlies, "
            f"frozen since {b['first_fail_utc']} (rc={b['last_rc']}) — {b['label']}"
        )
    message = header + "\n" + "\n".join(bullets)

    # Sanity-check: no trading verbs in composed message
    bad = _check_trading_verbs(message)
    if bad:
        log.error(
            "check_builder_failstreaks: composed message contains trading verb(s) %s — "
            "replacing with sanitised fallback",
            bad,
        )
        slugs = ", ".join(b["slug"] for b in breached)
        message = (
            f"Nightly builder fail-streaks detected — {len(breached)} builder(s) "
            f"breached streak threshold: {slugs}. "
            f"Review data/ci/builder_failstreaks.json."
        )

    try:
        from engine.alert_triage import push_ops_alert
        # Dedup is keyed on (source, type_) across all lanes, so the per-run-kind
        # type_ is what keeps the two nightlies (daily.yml US, asia-close CN/HK) from
        # suppressing each other; sharing the builder_failstreak ops-lane file is
        # intentional.
        push_ops_alert(
            source="builder_failstreak",
            type_=type_,
            message=message,
            severity="major",
            lane="builder_failstreak",
            root=root,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "check_builder_failstreaks: push_ops_alert failed (%s) — fail-open, no-op",
            exc,
        )


def process_band(
    art_dirs: list[Path],
    ledger_path: Path,
    lane: str,
    threshold: int,
    max_gap_days: int,
    prune_days: int,
    root: Path,
    _now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Core logic: update the ledger from rc files and return list of breached builders.

    Parameters
    ----------
    art_dirs:     Band scratch dirs, each with <slug>.rc and <slug>.log files;
                  later dirs win on a duplicate slug.
    ledger_path:  Path to builder_failstreaks.json.
    lane:         Write lanes are bound to their own ledger (nightly ->
                  data/ci/builder_failstreaks.json, asia ->
                  data/ci/builder_failstreaks_asia.json); any other lane is
                  report-only.
    threshold:    Consecutive failures required to escalate.
    max_gap_days: Max calendar-day gap before starting a fresh streak.
    prune_days:   Drop entries older than this many days.
    root:         Repo root (for push_ops_alert).
    _now:         Injectable datetime for tests.

    Returns list of dicts for each builder whose streak >= threshold:
      {slug, streak, first_fail_utc, last_fail_utc, last_rc, label}
    """
    now = _now if _now is not None else datetime.now(timezone.utc)
    today_str = now.date().isoformat()

    data = _load_ledger(ledger_path)
    builders: dict[str, Any] = data.get("builders", {})

    # Resolve whether this lane is allowed to write THIS ledger.
    owned = _WRITE_LANES.get(lane)
    may_write = False
    if owned is not None:
        try:
            may_write = ledger_path.resolve() == (root / owned).resolve()
        except Exception:  # noqa: BLE001
            may_write = False
        if not may_write:
            log.warning(
                "check_builder_failstreaks: lane %r owns %r but --ledger resolves to "
                "%s — refusing ledger write (report-only)",
                lane, owned, ledger_path,
            )

    # Merge rc files from all art dirs; later dir wins on a duplicate slug.
    rc_by_slug: dict[str, Path] = {}
    for art_dir in art_dirs:
        try:
            rc_files = sorted(art_dir.glob("*.rc"))
        except Exception as exc:  # noqa: BLE001
            log.warning("check_builder_failstreaks: cannot glob art dir %s (%s) — skip", art_dir, exc)
            continue
        for rc_path in rc_files:
            if rc_path.stem in rc_by_slug:
                log.warning(
                    "check_builder_failstreaks: duplicate slug %s across art dirs — later dir wins",
                    rc_path.stem,
                )
            rc_by_slug[rc_path.stem] = rc_path
    rc_slugs: set[str] = set(rc_by_slug)

    # Stale-escalation decay guard: if the union of all band art dirs produced NO rc
    # files at all (all art dirs missing or crashed before writing anything), do NOT
    # mutate the ledger — real streaks must not be wiped by a dead band run.
    # Note: if ONE band died but the other wrote rc files, the union is non-empty and
    # the dead band's slugs decay (restarting their streaks at 1 next run) — same
    # accepted trade-off as the mid-band-cancellation case already documented in the
    # module docstring.
    if may_write and not rc_slugs:
        log.warning(
            "check_builder_failstreaks: art_dir has no .rc files — band may have "
            "crashed before writing; skipping ledger write and escalation to protect "
            "real streaks"
        )
        return []

    for slug, rc_path in sorted(rc_by_slug.items()):
        # Parse exit code
        try:
            rc_str = rc_path.read_text(encoding="utf-8").strip()
            rc = int(rc_str)
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "check_builder_failstreaks: cannot parse rc for %s (%s) — skipping slug",
                slug, exc,
            )
            continue

        label = _read_label(rc_path.parent, slug)

        if rc == 0:
            # Reset: remove entry on success
            if slug in builders:
                del builders[slug]
                log.info("check_builder_failstreaks: %s recovered (rc=0) — entry reset", slug)
        else:
            # Failure: update or create entry
            entry = builders.get(slug)
            if entry and isinstance(entry, dict):
                last_run = entry.get("last_run_utc", "")
                if last_run == today_str:
                    # Idempotent same-day rerun: update label/rc, do NOT increment streak
                    entry["last_rc"] = rc
                    entry["label"] = label
                    log.info(
                        "check_builder_failstreaks: %s same-day rerun (streak=%d unchanged)",
                        slug, entry.get("streak", 1),
                    )
                else:
                    # Check gap
                    try:
                        last_run_date = date.fromisoformat(last_run)
                        gap = (now.date() - last_run_date).days
                    except Exception:  # noqa: BLE001
                        gap = max_gap_days + 1  # treat parse failure as stale

                    if gap <= max_gap_days:
                        # Continue streak
                        entry["streak"] = entry.get("streak", 1) + 1
                        entry["last_fail_utc"] = today_str
                        entry["last_run_utc"] = today_str
                        entry["last_rc"] = rc
                        entry["label"] = label
                        log.info(
                            "check_builder_failstreaks: %s streak=%d (gap=%dd)",
                            slug, entry["streak"], gap,
                        )
                    else:
                        # Stale gap — fresh streak
                        log.info(
                            "check_builder_failstreaks: %s gap=%dd > max_gap=%d — fresh streak",
                            slug, gap, max_gap_days,
                        )
                        builders[slug] = {
                            "streak": 1,
                            "first_fail_utc": today_str,
                            "last_fail_utc": today_str,
                            "last_run_utc": today_str,
                            "last_rc": rc,
                            "label": label,
                        }
            else:
                # New entry
                builders[slug] = {
                    "streak": 1,
                    "first_fail_utc": today_str,
                    "last_fail_utc": today_str,
                    "last_run_utc": today_str,
                    "last_rc": rc,
                    "label": label,
                }
                log.info("check_builder_failstreaks: %s first failure (rc=%d)", slug, rc)

    # Stale-escalation decay: on a write lane with a non-empty rc set, drop
    # any ledger entry whose slug was absent from this run's rc files — the
    # builder was renamed or retired.  We already guarded the empty-rc-set case
    # above, so rc_slugs is non-empty here whenever may_write.
    if may_write and rc_slugs:
        absent_slugs = [s for s in list(builders.keys()) if s not in rc_slugs]
        for slug in absent_slugs:
            log.info(
                "check_builder_failstreaks: %s absent from this run's rc set — "
                "builder retired/renamed; retiring streak entry",
                slug,
            )
            del builders[slug]

    # Prune stale entries (belt-and-braces for off-lane reads and edge cases)
    cutoff = (now.date() - timedelta(days=prune_days)).isoformat()
    to_prune = [
        slug for slug, entry in builders.items()
        if isinstance(entry, dict) and entry.get("last_run_utc", "9999") < cutoff
    ]
    for slug in to_prune:
        log.info("check_builder_failstreaks: pruning stale entry %s (last_run < %s)", slug, cutoff)
        del builders[slug]

    # Identify breached builders
    breached = []
    for slug, entry in builders.items():
        if not isinstance(entry, dict):
            continue
        streak = entry.get("streak", 0)
        if streak >= threshold:
            breached.append({
                "slug": slug,
                "streak": streak,
                "first_fail_utc": entry.get("first_fail_utc", today_str),
                "last_fail_utc": entry.get("last_fail_utc", today_str),
                "last_rc": entry.get("last_rc", 1),
                "label": entry.get("label", slug),
            })

    # Write updated ledger — only when this lane owns this ledger path
    if may_write:
        data["builders"] = builders
        data["updated_utc"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        _save_ledger(ledger_path, data)
        log.info(
            "check_builder_failstreaks: ledger written (%d entries, %d breached)",
            len(builders), len(breached),
        )
    else:
        log.info(
            "check_builder_failstreaks: ledger write skipped (lane=%r does not own %s) — "
            "report-only mode",
            lane, ledger_path,
        )

    return breached


def main(argv: list[str] | None = None) -> int:
    """Entry point. Always returns 0 (fail-open)."""
    parser = argparse.ArgumentParser(
        description="Consecutive-failure escalation for brun() builders.",
    )
    parser.add_argument(
        "--art-dir", required=True, action="append",
        help="Band scratch dir containing <slug>.rc and <slug>.log files. "
             "Repeatable — asia-close passes both bands; later dirs win on a duplicate slug.",
    )
    parser.add_argument(
        "--ledger",
        default=_DEFAULT_LEDGER,
        help=f"Path to builder_failstreaks.json (default: {_DEFAULT_LEDGER}), "
             "resolved relative to repo root unless absolute.",
    )
    parser.add_argument(
        "--lane", default="",
        help="Pipeline lane. Write lanes are bound to their own ledger "
             "(nightly -> data/ci/builder_failstreaks.json, "
             "asia -> data/ci/builder_failstreaks_asia.json); "
             "any other lane is report-only.",
    )
    parser.add_argument(
        "--threshold", type=int, default=_DEFAULT_THRESHOLD,
        help=f"Consecutive failures to escalate (default: {_DEFAULT_THRESHOLD}).",
    )
    parser.add_argument(
        "--max-gap-days", type=int, default=_DEFAULT_MAX_GAP_DAYS,
        help=f"Max gap days before resetting streak (default: {_DEFAULT_MAX_GAP_DAYS}).",
    )
    parser.add_argument(
        "--prune-days", type=int, default=_DEFAULT_PRUNE_DAYS,
        help=f"Drop entries older than this many days (default: {_DEFAULT_PRUNE_DAYS}).",
    )
    parser.add_argument(
        "--root", default=None,
        help="Repo root override (for tests).",
    )
    args = parser.parse_args(argv)

    try:
        root = Path(args.root).resolve() if args.root else _root_dir()
        art_dirs = [Path(p).resolve() for p in args.art_dir]

        ledger_raw = args.ledger
        if Path(ledger_raw).is_absolute():
            ledger_path = Path(ledger_raw)
        else:
            ledger_path = root / ledger_raw

        breached = process_band(
            art_dirs=art_dirs,
            ledger_path=ledger_path,
            lane=args.lane,
            threshold=args.threshold,
            max_gap_days=args.max_gap_days,
            prune_days=args.prune_days,
            root=root,
        )

        # Emit per-builder annotations
        for b in breached:
            _emit_annotation(
                slug=b["slug"],
                streak=b["streak"],
                first_fail_utc=b["first_fail_utc"],
                label=b["label"],
                last_rc=b["last_rc"],
                ledger_ref=args.ledger,
            )

        # Append step summary section
        if breached:
            _append_step_summary(breached)

        # Dispatch combined ops alert
        if breached:
            _dispatch_ops_alert(breached, root, lane=args.lane)
        else:
            log.info("check_builder_failstreaks: no builders at or above threshold — no alert")

    except Exception as exc:  # noqa: BLE001
        log.warning("check_builder_failstreaks: unexpected error (%s) — fail-open", exc)

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
