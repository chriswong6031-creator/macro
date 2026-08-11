#!/usr/bin/env python3
"""scripts/marketing_liveness_tripwire.py — the alarm a dead publisher cannot duck.

THE INCIDENT IT EXISTS FOR (2026-08-06 → 2026-08-10, five days).
On 08-06 Buffer's plan locked and every send came back 429. On 08-08 the repo
VARIABLE ``MARKETING_PUBLISH_ENABLED`` was set to ``0`` — the correct move while
the backend was refusing. Buffer was then fixed and NOBODY RE-ARMED IT. For the
next five days the 30-minute ladder ran on schedule, concluded GREEN on every
sweep, and posted nothing at all.

Two silence bugs made that possible, and this module is the answer to the second:

  1. The publisher's disarmed downgrade only spoke through ``log.warning``. House
     law (CLAUDE.md, "GitHub annotations must START the line") is precisely about
     this: every builder here logs with a prefixing format, so a ``::warning``
     handed to a logger emits ``WARNING ::warning …`` and GitHub drops it. The
     Actions UI therefore showed NOTHING while the lane self-downgraded on all
     ~30 sweeps a day. Fixed at the source in scripts/marketing_publisher.py.
  2. NOTHING EVER ALARMED ON "no post in N hours". A dry-run sweep is a
     successful sweep; a green check meant the workflow ran, never that the
     product shipped. Absence of output had no observer. That is this file.

WHAT IT DOES. Reads two facts — the arm variable and the newest live receipt in
``data/marketing/publications.jsonl`` — and turns "the account has been quiet too
long" into a GitHub annotation and, when it matters, a non-zero exit that reds
the sweep.

    ARMED, deep in the posting window, no live post in stale_post_alarm_hours
        → ::error, exit 1. Armed and silent is an outage, full stop.
    DISARMED longer than disarmed_alarm_hours
        → ::warning on EVERY sweep, and once a day (13:00Z, the slot the
          workflow already reserves for the metrics poll) an ::error and exit 1.
          A kill-switch left off is a decision that has to be re-made out loud;
          the daily red is what stops "temporarily dark" from becoming five days.
    otherwise
        → one ::notice with the age, so a healthy lane still prints its proof.

The armed rule only fires inside [17:00Z..23:59Z] ∪ [00:00Z..00:30Z]. The ladder
posts 11:00Z–00:30Z (4:00 AM–5:30 PM PT); at 11:30Z "nothing since yesterday
afternoon" is the normal overnight gap, and an alarm that cries every morning is
an alarm nobody reads. By 17:00Z the day is deep enough in the window that
silence means something.

WHAT IT DELIBERATELY DOES NOT DO. It never posts, never approves, never selects,
never writes a ledger and never touches the outbox. It reads two files and
prints. It is wired as the LAST step of marketing-publish.yml, after the ledger
commit, with ``always()`` — a run that failed earlier is exactly the run whose
silence needs reporting, and a red tripwire must never be able to cost the ledger
a commit.

    python -m scripts.marketing_liveness_tripwire
    python -m scripts.marketing_liveness_tripwire --now 2026-08-10T20:00:00Z --root /tmp/x

EVERY annotation below is a bare ``print(..., flush=True)`` starting its line.
Never route one through ``log``: it would vanish, which is the exact defect this
module was built to end (guarded by tests/test_gh_annotation_line_start.py;
``flush`` is load-bearing because stdout is block-buffered when piped in CI).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

log = logging.getLogger("marketing_liveness_tripwire")

#: Append-only publication receipts — one row per SHIPPED X post
#: (scripts/marketing_publisher._publication_row). Dry-run sweeps write an
#: activity row elsewhere and never land here, so a `mode: "live"` row is the
#: only honest evidence that something actually went out.
PUBLICATIONS_REL = Path("data/marketing/publications.jsonl")
CONFIG_REL = Path("config/marketing.yml")

#: Thresholds, in hours. Overridable under `publish.liveness` in config/marketing.yml.
DEFAULT_STALE_POST_ALARM_HOURS = 8.0
DEFAULT_DISARMED_ALARM_HOURS = 24.0

#: An unknown last-post time is not a YOUNG one. No receipts at all means either a
#: brand-new checkout or a lane that has never shipped; both deserve the alarm
#: rather than a pass, so unknown reads as "very old" instead of "fine".
UNKNOWN_AGE_HOURS = 10_000.0

#: The once-daily slot where a long-dark lane turns from a warning into a red
#: sweep. 13:00Z is already reserved in marketing-publish.yml for the metrics
#: poll, so this reuses a decision instead of inventing a second clock.
DISARMED_FAIL_HOUR_UTC = 13


# ── inputs ───────────────────────────────────────────────────────────────────

def parse_iso(raw: object) -> datetime | None:
    """An ISO8601 stamp as an aware UTC datetime, or None when it is not one.

    Receipts write ``...Z``; a naive stamp is read as UTC because every producer
    in this lane stamps UTC. Never raises — a malformed row is skipped, not fatal.
    """
    if not isinstance(raw, str) or not raw.strip():
        return None
    txt = raw.strip()
    if txt[-1:] in ("Z", "z"):
        txt = txt[:-1] + "+00:00"
    try:
        when = datetime.fromisoformat(txt)
    except ValueError:
        return None
    if when.tzinfo is None:
        return when.replace(tzinfo=timezone.utc)
    return when.astimezone(timezone.utc)


def read_last_live_post(path: Path | str) -> datetime | None:
    """Newest ``published_at`` among ``mode == "live"`` rows. None when unknown.

    Fail-soft by construction: a missing file, an unreadable one, a truncated
    last line (the ledger is appended to by a job that can be cancelled) and a
    row with an unparseable stamp all degrade to "skip this row". The MAX is
    taken rather than the last line because the ledger is written by several
    lanes and union-merged (.gitattributes), so file order is not time order.

    ``mode`` is the whole point of the filter: a dry-run sweep also writes rows
    into the marketing ledgers, and counting one as a post is how a dark lane
    would go on looking alive.
    """
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return None

    newest: datetime | None = None
    live = skipped = 0
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            skipped += 1
            continue
        if not isinstance(row, dict):
            skipped += 1
            continue
        if str(row.get("mode") or "") != "live":
            continue
        when = parse_iso(row.get("published_at"))
        if when is None:
            skipped += 1
            continue
        live += 1
        if newest is None or when > newest:
            newest = when

    if skipped:
        log.info("publications.jsonl: skipped %d unreadable row(s), read %d live receipt(s)",
                 skipped, live)
    return newest


def load_config(root: Path | str | None = None) -> dict[str, float]:
    """The two thresholds from ``publish.liveness``, with defaults for everything
    absent, unparseable, non-positive, or unreachable.

    NEVER raises. A tripwire that dies on its own config is a tripwire that is
    off, which is the failure mode this whole module exists to prevent — so an
    unreadable file or a missing pyyaml degrades to the defaults and says so in
    the log.
    """
    cfg = {
        "stale_post_alarm_hours": DEFAULT_STALE_POST_ALARM_HOURS,
        "disarmed_alarm_hours": DEFAULT_DISARMED_ALARM_HOURS,
    }
    path = Path(root or ROOT) / CONFIG_REL
    try:
        import yaml  # noqa: PLC0415 — optional at import time, present in the lane's venv

        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        block = (payload.get("publish") or {}).get("liveness") or {}
    except Exception as exc:  # noqa: BLE001 — any failure means "use the defaults"
        log.warning("liveness config unreadable (%s) — using defaults %s", exc, cfg)
        return cfg

    if not isinstance(block, dict):
        log.warning("publish.liveness is not a mapping (%r) — using defaults", block)
        return cfg

    for key in list(cfg):
        raw = block.get(key)
        if raw is None:
            continue
        try:
            val = float(raw)
        except (TypeError, ValueError):
            log.warning("publish.liveness.%s = %r is not a number — keeping %s",
                        key, raw, cfg[key])
            continue
        if val <= 0:
            log.warning("publish.liveness.%s = %r is not positive — keeping %s",
                        key, raw, cfg[key])
            continue
        cfg[key] = val
    return cfg


def armed_from_env(env: dict[str, str] | None = None) -> bool:
    """True when the kill-switch variable reads armed.

    ``== "1"`` on purpose, matching marketing-publish.yml's own ledger-commit
    guard and the admin Publisher panel, which write the literal 1/0.
    ``engine.marketing.sentinel.publish_enabled`` additionally honours
    true/yes — a lane armed that way reads DISARMED here, which errs loud: the
    disarmed rule only fires after 24 quiet hours, so it can raise a differently
    worded alarm about a genuinely silent account but can never silence one.
    """
    src = os.environ if env is None else env
    return str(src.get("MARKETING_PUBLISH_ENABLED", "")).strip() == "1"


# ── the rule engine (pure — this is the part the tests drive) ────────────────

def in_evaluation_window(now_utc: datetime) -> bool:
    """Is it late enough in the posting day for silence to mean something?

    The ladder runs 11:00Z–00:30Z. [17:00Z..23:59Z] ∪ [00:00Z..00:30Z] is the
    back half of that, where a lane that has posted nothing has demonstrably had
    hours of rungs to do it in.
    """
    if 17 <= now_utc.hour <= 23:
        return True
    return now_utc.hour == 0 and now_utc.minute <= 30


def age_hours(now_utc: datetime, last_live_post_at: datetime | None) -> float:
    """Hours since the last live post; UNKNOWN_AGE_HOURS when there is none."""
    if last_live_post_at is None:
        return UNKNOWN_AGE_HOURS
    # A future stamp is clock skew, not freshness in reverse — clamp at 0 so it
    # reads "just posted" rather than "negative hours stale".
    return max((now_utc - last_live_post_at).total_seconds() / 3600.0, 0.0)


def evaluate(
    now_utc: datetime,
    armed: bool,
    last_live_post_at: datetime | None,
    cfg: dict[str, float],
) -> tuple[int, list[str]]:
    """The whole decision, as a pure function: ``(exit_code, annotations)``.

    Rules are evaluated top to bottom and the exit code is the max severity
    reached. Annotations come back as strings so a caller (and the test suite)
    can inspect them without capturing stdout; ``main`` is the only thing that
    prints them.
    """
    now = now_utc if now_utc.tzinfo else now_utc.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc)
    stale_thr = float(cfg.get("stale_post_alarm_hours", DEFAULT_STALE_POST_ALARM_HOURS))
    dark_thr = float(cfg.get("disarmed_alarm_hours", DEFAULT_DISARMED_ALARM_HOURS))
    age = age_hours(now, last_live_post_at)
    annotations: list[str] = []

    # (a) ARMED AND SILENT — an outage. Only judged deep in the posting window.
    if armed:
        if in_evaluation_window(now) and age > stale_thr:
            annotations.append(
                f"::error title=marketing-liveness::armed but last live post is "
                f"{age:.1f}h old (threshold {stale_thr:g}h) — the pipeline is "
                f"posting nothing"
            )
            return 1, annotations

    # (b) DARK TOO LONG — warn every sweep, red once a day so it cannot settle in.
    elif age > dark_thr:
        annotations.append(
            f"::warning title=marketing-dark::publisher disarmed and last live "
            f"post is {age:.1f}h old — posts are OFF"
        )
        if now.hour == DISARMED_FAIL_HOUR_UTC:
            annotations.append(
                f"::error title=marketing-dark::disarmed >{dark_thr:g}h — failing "
                f"the 13:00Z sweep so this cannot stay silently green"
            )
            return 1, annotations
        return 0, annotations

    # (c) HEALTHY — print the proof anyway. A lane that only speaks when broken
    # is a lane you cannot tell from one whose alarm has stopped working.
    annotations.append(
        f"::notice title=marketing-liveness::ok — last live post {age:.1f}h ago, "
        f"armed={armed}"
    )
    return 0, annotations


# ── CLI ──────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=None,
                    help="repo root holding data/marketing + config "
                         "(default: this repo)")
    ap.add_argument("--now", default=None,
                    help="iso8601 UTC override for the evaluation clock (testing)")
    args = ap.parse_args(argv)

    root = Path(args.root).resolve() if args.root else ROOT
    if args.now:
        now = parse_iso(args.now)
        if now is None:
            log.error("--now %r is not an iso8601 stamp", args.now)
            return 2
    else:
        now = datetime.now(timezone.utc)

    armed = armed_from_env()
    cfg = load_config(root)
    last = read_last_live_post(root / PUBLICATIONS_REL)
    code, annotations = evaluate(now, armed, last, cfg)

    for line in annotations:
        print(line, flush=True)

    # Human context, deliberately NOT annotation-shaped: the stamps and
    # thresholds behind the verdict, for whoever opens the step log.
    log.info(
        "liveness: now=%s armed=%s last_live_post=%s window=%s "
        "stale_thr=%gh disarmed_thr=%gh exit=%d",
        now.strftime("%Y-%m-%dT%H:%M:%SZ"), armed,
        last.strftime("%Y-%m-%dT%H:%M:%SZ") if last else "unknown (no live receipt)",
        in_evaluation_window(now),
        cfg["stale_post_alarm_hours"], cfg["disarmed_alarm_hours"], code,
    )
    return code


if __name__ == "__main__":
    raise SystemExit(main())
