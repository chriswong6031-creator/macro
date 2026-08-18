"""scripts.close_pass_slo_report — the evening board's acceptance record (W-L1, PR-C).

THE INSTRUMENT THE GATE IS GRADED WITH
======================================
The W-L1 gate is "fresh US picks live on the site by 18:30 ET, five consecutive
sessions". ``scripts/freshness_sentinel.py`` measures that and files one
append-only stamp per (session, surface) in ``<state-dir>/first_fresh.json``.
This reads that record back as a table a human can accept or reject a wave on.

A PASS/FAIL ON ONE DEADLINE IS NOT AN ACCEPTANCE RECORD. Fri 2026-08-14 is the
case that forced this: the board published at 23:19:14Z — 19:19 ET, against an
18:30 SLA and a 16:15 product target — with 22 cards from 253 evaluated names of
a 1,763 universe. "MISSED" is the whole of what the record could say. It could
not say whether the 49 minutes went into waiting for closes, into the pass
itself, or into the gap between publishing and a reader being able to see it,
and those three have three different owners and three different fixes.

So every row here decomposes the evening into legs that add up:

    close_observed_at ──close_to_candidate──▶ board_generated_at
                       ──candidate_to_visible──▶ first_user_visible_at

WHAT IS MEASURED AND WHAT IS ONLY READ
  * ``sla_met`` is READ from the record, never recomputed. The stamp is
    append-only and "when did this FIRST read fresh" has exactly one answer; a
    report that recomputed it would be free to disagree with the thing being
    accepted, and the report is not the authority.
  * ``product_slo_met`` is COMPUTED here from the recorded instant, because the
    16:15 ET product target is this report's question and not the sentinel's.
    Moving that target must not require re-stamping history.
  * Every absent field prints ``—``. Never 0, never a blank, never an inferred
    value: an unmeasured leg and a zero-length leg are different claims, and
    only one of them is ever true here.
  * ``candidate_to_visible_sec`` is bounded below by the sentinel's own 30-minute
    cadence. The record publishes that bound as ``visible_resolution_sec`` and
    this report prints it in the legend rather than dressing the number up as
    second-precision knowledge.

A SESSION WITH NO STAMP IS A ROW, NOT A GAP. Rows are walked over the NYSE
calendar (``lib.nyse_calendar``), exactly as ``freshness_sentinel.sla_streak``
does, so an evening on which the board never published prints as a full row of
``—`` and a MISSED verdict. Iterating the record's own keys would step straight
over the miss and report a five-session acceptance that never happened — the
gate passing on the strength of its own missing data.

THE BOOTSTRAP LEG — "is the code that fires the clock the code we merged?"
The lane's launchd clock does NOT run this repository. It runs a SNAPSHOT that
``scripts/install_closepass_launchd.sh`` froze into Application Support, and the
freeze is deliberate (a mid-day push to main must not change what the clock
executes). The cost of that design is that a merged fix is not a deployed fix,
and on 2026-08-18 nothing in the estate could see the difference: PR #5862 merged
as af416e4a1066 while the host kept executing the pre-fix bytes from Aug 15, and
its receipts looked perfect because the only vintage they compared to anything
was the LANE's — which is reset to origin/main every run and is therefore always
fresh no matter how old the file computing it is.

So every receipt now carries a ``bootstrap`` verdict and this report grades it:

  * the column is per session — history, printed and never re-graded.
  * the EXIT CODE follows the NEWEST session that has a receipt, because the
    question is "will tonight's fire run origin/main", and only the newest
    receipt answers it. Grading the whole window would hold a healed host red
    for a week and teach everyone to ignore the column.
  * a receipt whose ``schema`` predates this checkout's is itself DRIFT and is
    reported as such: the bootstrap that wrote it is provably older than the
    code being read here. That is the merged-but-not-deployed detector.
  * no receipt is ``—`` and says so in the footer, naming the directory it read.
    "I could not look" never renders as "nothing is wrong".

Usage:
  python -m scripts.close_pass_slo_report                     # last 5 sessions
  python -m scripts.close_pass_slo_report --sessions 10
  python -m scripts.close_pass_slo_report --json              # machine-readable
  python -m scripts.close_pass_slo_report --with-r2           # + tonight's board
  python -m scripts.close_pass_slo_report --state-dir ./state --now 2026-08-15T10:00Z
  python -m scripts.close_pass_slo_report --receipts-dir ~/Library/Application\\ Support/macro-closepass/runs

Exit status: 0 when every reported session met BOTH gates AND the newest host
receipt shows no bootstrap drift, 1 when any did not, 2 when the report could not
be built at all (no calendar, unreadable record) — "I could not measure" must
never share an exit code with "it passed".
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from scripts import close_pass_host_runner as HOST  # noqa: E402
from scripts import freshness_sentinel as FS  # noqa: E402

#: The sentinel surface this report grades. One surface on purpose: the W-L1
#: gate is about the evening close-pass board and nothing else, and a report
#: that quietly averaged several surfaces would grade a gate nobody set.
SURFACE_ID = "us_board_provisional"
#: The masterplan gate, and the default when a stamp predates the field.
SLA_BY_ET = "18:30"
#: The PRODUCT target: the board in front of a reader within 15 minutes of the
#: close. Deliberately NOT the SLA — the SLA is what the estate committed to and
#: this is what the product wants, and collapsing the two would delete the only
#: number that says how far short a "passing" evening still falls.
PRODUCT_SLO_BY_ET = "16:15"
#: The R2 key ``--with-r2`` reads (scripts/close_pass_publish.BOARD_KEY).
BOARD_R2_KEY = "/live_flow/us_board_provisional.json"
#: What an unmeasured cell prints as.
ABSENT = "—"
#: The bootstrap cells. Only ``ok`` is a pass; everything else is a finding or a
#: hole, and the two are never spelled the same way.
BOOT_OK = "ok"
BOOT_UNKNOWN = "?"
BOOT_OLD_SCHEMA = "OLD-SCHEMA"
#: The one remedy, printed wherever the finding is. There is no self-heal by
#: design — the installer's freeze is the feature the drift is the price of.
REINSTALL_CMD = "bash scripts/install_closepass_launchd.sh"


# --------------------------------------------------------------------------- #
# The bootstrap leg — read from the host clock's own run receipts
# --------------------------------------------------------------------------- #
def default_receipts_dir() -> Path:
    """Where ``close_pass_host_runner`` leaves one JSON per session.

    Resolved through the runner's own ``support_dir()`` rather than a second
    literal, so a host that moves its support directory moves both halves at
    once and this report cannot end up grading a directory nobody writes to.
    """
    return HOST.support_dir() / "runs"


def read_receipts(runs: Path) -> dict[str, dict]:
    """``{session: receipt}``. An unreadable receipt is an ABSENT one, not a crash.

    This report is read-only on the lane: it grades the clock, it never writes to
    the clock's state, and a malformed receipt must not be able to stop a
    latency table that does not depend on it.
    """
    out: dict[str, dict] = {}
    try:
        files = sorted(runs.glob("*.json"))
    except OSError:
        return out
    for path in files:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(payload, dict) and isinstance(payload.get("session"), str):
            out[payload["session"]] = payload
    return out


def bootstrap_state(receipt: object) -> tuple[str, str]:
    """``(cell, detail)`` for one session's host receipt. One pass, three findings.

      * no receipt              → ``—``. The host was not read; nothing is claimed.
      * receipt predates this   → ``OLD-SCHEMA``, and that IS drift, provably: a
        checkout's schema          bootstrap old enough to lack the block is older
                                   than the code reading it, which is what
                                   "behind" means. This is the detector that
                                   catches merged-but-not-deployed.
      * an explicit verdict     → ``ok`` / ``BEHIND n`` / ``BEHIND ?``
      * anything else           → ``?``, recorded and never rendered as a pass.
    """
    if not isinstance(receipt, dict):
        return ABSENT, "no host receipt for this session"
    boot = receipt.get("bootstrap")
    if not isinstance(boot, dict):
        schema = receipt.get("schema")
        if schema != HOST.RECEIPT_SCHEMA:
            return BOOT_OLD_SCHEMA, (
                f"receipt schema {schema!r} predates this checkout's "
                f"{HOST.RECEIPT_SCHEMA!r}, so the bootstrap that wrote it is older "
                f"than origin/main.")
        return BOOT_UNKNOWN, "receipt carries no bootstrap block"
    detail = str(boot.get("detail") or "")
    verdict = boot.get("matches_main")
    if verdict is True:
        return BOOT_OK, detail or "byte-identical to origin/main"
    if verdict is False:
        behind = boot.get("commits_behind")
        n = behind if isinstance(behind, int) and not isinstance(behind, bool) else "?"
        return f"BEHIND {n}", detail or "the executing bootstrap is not origin/main."
    return BOOT_UNKNOWN, detail or "the run could not grade its own bootstrap"


def bootstrap_verdict(rows: list[dict[str, Any]], runs: Path) -> dict[str, Any]:
    """The NEWEST session that HAS a receipt decides. History is printed, not graded.

    Grading the whole window would keep a healed host red for as many sessions as
    the window is wide — the older rows genuinely did run a stale bootstrap and
    that stays visible in the column — but the question this leg exists to answer
    is "will tonight's firing execute origin/main", and only the newest receipt
    can answer it.
    """
    for row in rows:
        cell = row.get("bootstrap")
        if cell in (None, ABSENT):
            continue
        state = ("ok" if cell == BOOT_OK
                 else "unknown" if cell == BOOT_UNKNOWN else "drift")
        return {"state": state, "session": row["session"], "cell": cell,
                "detail": row.get("bootstrap_detail") or "", "receipts_dir": str(runs)}
    return {"state": "unmeasured", "session": None, "cell": ABSENT,
            "detail": f"no host receipt under {runs} for any reported session",
            "receipts_dir": str(runs)}


def bootstrap_footer(verdict: dict[str, Any]) -> str:
    """One line, always printed. Silence would be the same bug one layer up."""
    state, session = verdict["state"], verdict["session"]
    if state == "drift":
        detail = verdict["detail"].rstrip()
        # The remedy is printed EXACTLY once. A receipt's own detail already
        # carries it — the runner's annotation has to stand alone in a launchd
        # log with no footer under it — so the footer does not repeat itself.
        remedy = ("" if "install_closepass_launchd.sh" in detail else
                  f" Merging does not deploy scripts/{HOST.RUNNER_BASENAME} — "
                  f"re-run: {REINSTALL_CMD}")
        if remedy and not detail.endswith((".", "!")):
            detail += "."
        return f"BOOTSTRAP DRIFT on {session}: {detail}{remedy}"
    if state == "ok":
        return (f"bootstrap: the host snapshot matched origin/main on {session}.")
    if state == "unknown":
        return (f"bootstrap: UNVERIFIED on {session} — {verdict['detail']} "
                f"(not a clean bill; a stale snapshot reads the same way).")
    return (f"bootstrap: NOT MEASURED — {verdict['detail']}. Run this on the host "
            f"that owns com.macro.closepass, or pass --receipts-dir.")


# --------------------------------------------------------------------------- #
# Reading the record
# --------------------------------------------------------------------------- #
def _et_clock(value: object) -> datetime | None:
    """One recorded ISO instant on the Eastern clock, or None when unknowable.

    Two ways to be unknowable and both must answer None rather than a number: an
    unparseable or offset-less stamp (``FS._instant`` refuses a naive one — an
    assumed UTC would read 20:47Z as "missed 18:30" on an evening the board made
    with 100 minutes to spare), and a host with no tzdata (``FS._et``).
    """
    stamp = FS._instant(value)
    return None if stamp is None else FS._et(stamp)


def _hhmm(value: object, session: str) -> str:
    """``HH:MM`` on the session's own ET day, ``HH:MM+1`` when it is not.

    The suffix is load-bearing. A board published at 01:30 ET the next morning
    prints "01:30", which reads as the earliest, best evening in the table
    unless the row says out loud that it is a different day.
    """
    et = _et_clock(value)
    if et is None:
        return ABSENT
    try:
        days = (et.date() - datetime.fromisoformat(session).date()).days
    except ValueError:
        return et.strftime("%H:%M")
    return et.strftime("%H:%M") + (f"{days:+d}" if days else "")


def _met_by(value: object, session: str, by_et: str) -> bool | None:
    """Did ``value`` land on the session's OWN ET day, by ``by_et``?

    Both halves, for the reason ``freshness_sentinel.record_first_fresh`` spells
    out: a board published at 02:00 ET the next morning reads "02:00 ≤ 16:15" and
    would score as a pass on a session it missed entirely.
    """
    et = _et_clock(value)
    if et is None:
        return None
    return et.date().isoformat() == session and et.strftime("%H:%M") <= by_et


def build_row(record: dict, session: str,
              receipt: object = None) -> dict[str, Any]:
    """One session's row. Absent everywhere is legal.

    Two independent sources on purpose: the sentinel record answers WHEN the
    board reached a reader, the host receipt answers WHAT CODE produced it. A
    row can be green on the first and drifted on the second, and that
    combination — a perfect-looking evening run by stale plumbing — is exactly
    the state 2026-08-18 shipped undetected.
    """
    entry = ((record.get("sessions") or {}).get(session) or {}).get(SURFACE_ID) or {}
    latency = entry.get("latency") or {}
    coverage = entry.get("coverage") or {}
    provenance = entry.get("provenance") or {}
    # VERSION TOLERANCE, in one expression. A stamp written before the
    # decomposition existed carries no `latency` block and does carry
    # `first_fresh_at`, which IS the first-user-visible instant under its older
    # name. Falling back keeps every historical session gradeable on the two
    # columns that do not need the new fields.
    visible = latency.get("first_user_visible_at") or entry.get("first_fresh_at")
    boot_cell, boot_detail = bootstrap_state(receipt)
    return {
        "session": session,
        "stamped": bool(entry),
        "close_observed_at": latency.get("close_observed_at"),
        "board_generated_at": latency.get("board_generated_at"),
        "first_user_visible_at": visible,
        "close_to_candidate_sec": latency.get("close_to_candidate_sec"),
        "candidate_to_visible_sec": latency.get("candidate_to_visible_sec"),
        "visible_resolution_sec": latency.get("visible_resolution_sec"),
        "evaluated_n": coverage.get("evaluated_n"),
        "universe_n": coverage.get("universe_n"),
        "admitted_n": coverage.get("admitted_n"),
        "close_source": provenance.get("close_source"),
        "close_basis": provenance.get("close_basis"),
        "close_finalized": provenance.get("close_finalized"),
        # READ, not recomputed — the record is the authority on its own gate.
        "sla_by_et": entry.get("by_et") or SLA_BY_ET,
        # AN UNSTAMPED SESSION IS A MISS, NOT AN UNKNOWN. The record is
        # append-only and every fresh reader-visible pass stamps it, so no stamp
        # means no pass observed the board live on that session's own evening.
        # ``freshness_sentinel.sla_streak`` already grades it exactly this way
        # (``entry.get("met") is True``), and a report that were more lenient
        # than the streak would accept a wave the gate itself refuses.
        #
        # Distinct from ``None``, which survives only when a stamp EXISTS and
        # its verdict is genuinely unknowable — a host with no tzdata. That
        # renders ``—``: "could not tell" and "was late" send someone to fix two
        # different things.
        "sla_met": entry.get("met") if entry else False,
        # COMPUTED — this report's question, applied to the recorded instant.
        "product_slo_by_et": PRODUCT_SLO_BY_ET,
        "product_slo_met": (_met_by(visible, session, PRODUCT_SLO_BY_ET)
                            if entry else False),
        "facts_from": "sentinel_record" if entry else None,
        # From the HOST receipt, never the sentinel record — see bootstrap_state.
        "bootstrap": boot_cell,
        "bootstrap_detail": boot_detail,
    }


def build_rows(record: dict, now: datetime, sessions: int,
               receipts: dict[str, dict] | None = None) -> list[dict[str, Any]]:
    """The last ``sessions`` NYSE sessions, newest first. Raises on no calendar.

    Anchored on ``expected_last_session`` so today's board is not graded until
    today is over — the same anchor the sentinel's own streak uses, because a
    report and the gate it reports on disagreeing about which sessions count is
    a way to accept a wave that did not happen.
    """
    from lib import nyse_calendar  # noqa: PLC0415 — see module docstring

    receipts = receipts or {}
    last = nyse_calendar.expected_last_session(now)
    rows: list[dict[str, Any]] = []
    for n in range(max(sessions, 0)):
        day = last if n == 0 else nyse_calendar.session_n_back(last, n)
        if day is None:
            break
        session = day.isoformat()
        rows.append(build_row(record, session, receipts.get(session)))
    return rows


def merge_r2_board(rows: list[dict[str, Any]], payload: object) -> list[dict[str, Any]]:
    """Fill one row's PRODUCER-side facts from a freshly-read R2 board.

    The newest session is normally the one being watched, and it may have a
    board on R2 minutes before the sentinel's next pass stamps it. Reading the
    board directly closes that window for the producer-side legs.

    It CANNOT close it for the reader-side leg, and does not pretend to. The
    board says when it was built; only the sentinel can say when a reader could
    first see it, so ``first_user_visible_at`` and everything derived from it
    are left exactly as the record had them. A row filled this way is marked
    ``facts_from: "r2_board"`` so nobody grades an acceptance on a column that
    came from the producer rather than from the observer.
    """
    facts = FS.close_pass_facts(payload)
    session = payload.get("as_of") if isinstance(payload, dict) else None
    if not facts or not isinstance(session, str):
        return rows
    coverage = facts.get("coverage") or {}
    for row in rows:
        if row["session"] != session or row["close_observed_at"] is not None:
            continue
        row["close_observed_at"] = facts.get("close_observed_at")
        row["board_generated_at"] = facts.get("board_generated_at")
        row["close_to_candidate_sec"] = FS._seconds_between(
            facts.get("close_observed_at"), facts.get("board_generated_at")
        )
        for key in ("universe_n", "evaluated_n", "admitted_n"):
            if row[key] is None:
                row[key] = coverage.get(key)
        for key in ("close_source", "close_basis", "close_finalized"):
            if row[key] is None:
                row[key] = facts.get(key)
        row["facts_from"] = "r2_board" if not row["stamped"] else "sentinel_record+r2"
    return rows


def read_r2_board(r2_base: str, fetcher=None) -> object:
    """The published board, or None. A failed read is a missing column, not a crash."""
    fetcher = fetcher or FS.fetch
    result = fetcher(r2_base.rstrip("/") + BOARD_R2_KEY, want_body=True)
    if result.error or result.status != 200 or not result.body:
        print(f"close-pass-slo: R2 board unread ({result.error or result.status})"
              " — producer columns stay unmeasured", file=sys.stderr)
        return None
    try:
        return json.loads(result.body)
    except ValueError as exc:
        print(f"close-pass-slo: R2 board is not JSON ({exc})", file=sys.stderr)
        return None


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #
def _secs(value: object) -> str:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return ABSENT
    return f"{value:,.0f}s"


def _count(value: object) -> str:
    return ABSENT if not isinstance(value, int) or isinstance(value, bool) else str(value)


def _verdict(value: object) -> str:
    """``met`` / ``MISSED`` / ``—``. Unknown is its own word, never a fail.

    A tri-state on purpose: "the sentinel could not tell" (no tzdata, no stamp)
    and "the board was late" are different findings, and rendering the first as
    the second would send someone to fix a lane that is working.
    """
    return ABSENT if value is None else ("met" if value else "MISSED")


def _fraction(evaluated: object, universe: object) -> str:
    left, right = _count(evaluated), _count(universe)
    return ABSENT if left == ABSENT and right == ABSENT else f"{left}/{right}"


#: (header, key, formatter). Order is the brief's column order — the reading
#: order of the evening, left to right, ending in the two verdicts.
COLUMNS: tuple[tuple[str, str, Any], ...] = (
    ("session", "session", lambda row: row["session"]),
    ("close", "close_observed_at",
     lambda row: _hhmm(row["close_observed_at"], row["session"])),
    ("built", "board_generated_at",
     lambda row: _hhmm(row["board_generated_at"], row["session"])),
    ("visible", "first_user_visible_at",
     lambda row: _hhmm(row["first_user_visible_at"], row["session"])),
    ("close→cand", "close_to_candidate_sec",
     lambda row: _secs(row["close_to_candidate_sec"])),
    ("cand→vis", "candidate_to_visible_sec",
     lambda row: _secs(row["candidate_to_visible_sec"])),
    ("eval/univ", "evaluated_n",
     lambda row: _fraction(row["evaluated_n"], row["universe_n"])),
    ("admit", "admitted_n", lambda row: _count(row["admitted_n"])),
    ("source", "close_source", lambda row: row["close_source"] or ABSENT),
    ("final", "close_finalized",
     lambda row: ABSENT if row["close_finalized"] is None
     else ("yes" if row["close_finalized"] else "no")),
    ("SLA 18:30", "sla_met", lambda row: _verdict(row["sla_met"])),
    ("SLO 16:15", "product_slo_met", lambda row: _verdict(row["product_slo_met"])),
    # Last on purpose: it grades the PRODUCER's plumbing, not the evening, and a
    # reader scanning for the two gate verdicts should hit them before this one.
    ("bootstrap", "bootstrap", lambda row: row["bootstrap"]),
)


def render(rows: list[dict[str, Any]], resolution_sec: int | None = None,
           boot_footer: str | None = None) -> str:
    """The acceptance table. Column widths follow the content, so the output is
    stable for a given set of rows and diffable across runs."""
    cells = [[header for header, _, _ in COLUMNS]]
    cells += [[fmt(row) for _, _, fmt in COLUMNS] for row in rows]
    widths = [max(len(row[i]) for row in cells) for i in range(len(COLUMNS))]
    lines = ["  ".join(cell.ljust(widths[i]) for i, cell in enumerate(cells[0])).rstrip()]
    lines.append("  ".join("-" * w for w in widths))
    for row in cells[1:]:
        lines.append("  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)).rstrip())

    met = sum(1 for row in rows if row["sla_met"] is True)
    slo = sum(1 for row in rows if row["product_slo_met"] is True)
    lines.append("")
    lines.append(f"{met}/{len(rows)} sessions met the {SLA_BY_ET} ET SLA; "
                 f"{slo}/{len(rows)} met the {PRODUCT_SLO_BY_ET} ET product SLO.")
    # The error bar, stated once, beside the column it qualifies.
    if resolution_sec:
        lines.append(f"'visible' is observed on the sentinel's {resolution_sec // 60}-minute "
                     "cadence, so cand→vis is known to that resolution, no better.")
    lines.append(f"{ABSENT} = not measured. Times are ET on the session's own day "
                 "(+1 = the following morning).")
    # ALWAYS printed, including when it says nothing was measured: a leg that
    # goes quiet when it cannot see is indistinguishable from a leg that saw
    # nothing wrong, which is the whole defect this column was added to catch.
    if boot_footer:
        lines.append(boot_footer)
    return "\n".join(lines)


def _resolution(rows: list[dict[str, Any]]) -> int | None:
    for row in rows:
        value = row.get("visible_resolution_sec")
        if isinstance(value, int) and not isinstance(value, bool):
            return value
    return None


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def run(*, now: datetime, state_dir: Path, sessions: int, as_json: bool,
        with_r2: bool, r2_base: str, fetcher=None, out=None,
        receipts_dir: Path | None = None) -> int:
    out = sys.stdout if out is None else out
    record = FS.load_first_fresh(state_dir)
    runs = default_receipts_dir() if receipts_dir is None else receipts_dir
    try:
        rows = build_rows(record, now, sessions, read_receipts(runs))
    except Exception as exc:  # noqa: BLE001 — no calendar ⇒ no report, and say so
        print(f"close-pass-slo: cannot walk the session calendar "
              f"({type(exc).__name__}: {exc}) — no report", file=sys.stderr)
        return 2

    if with_r2:
        payload = read_r2_board(r2_base, fetcher=fetcher)
        if payload is not None:
            rows = merge_r2_board(rows, payload)

    verdict = bootstrap_verdict(rows, runs)
    if as_json:
        json.dump({"schema": "close_pass.slo_report/v2",
                   "generated_at": now.isoformat(),
                   "surface": SURFACE_ID,
                   "sla_by_et": SLA_BY_ET,
                   "product_slo_by_et": PRODUCT_SLO_BY_ET,
                   "state_dir": str(state_dir),
                   "bootstrap_verdict": verdict,
                   "sessions": rows}, out, indent=1, sort_keys=True)
        out.write("\n")
    else:
        out.write(render(rows, _resolution(rows), bootstrap_footer(verdict)) + "\n")

    if not rows:
        # No sessions to grade is not an acceptance. Exit 2 keeps "nothing to
        # report" out of the same bucket as "everything passed".
        return 2
    # DRIFT FAILS THE REPORT. A board that met both gates on plumbing nobody
    # deployed is not an accepted session — it is an unmeasured one that happened
    # to work, and W-ACCEPT already lost a day to exactly that.
    if verdict["state"] == "drift":
        return 1
    return 0 if all(row["sla_met"] is True and row["product_slo_met"] is True
                    for row in rows) else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Close-pass board acceptance record (W-L1 close→candidate→visible)")
    ap.add_argument("--sessions", type=int, default=5,
                    help="NYSE sessions to report, newest first (default 5)")
    ap.add_argument("--state-dir", default=FS.DEFAULT_STATE_DIR,
                    help="the sentinel's private state directory")
    ap.add_argument("--json", dest="as_json", action="store_true",
                    help="machine-readable rows, same fields as the table")
    ap.add_argument("--with-r2", action="store_true",
                    help="fill the newest session's PRODUCER columns from the "
                         "published R2 board (never the reader-side ones)")
    ap.add_argument("--r2-base", default=FS.DEFAULT_R2_BASE)
    ap.add_argument("--receipts-dir", default=None,
                    help="the host clock's run receipts (default: the runner's own "
                         "support dir). Off-host this reads nothing and the "
                         "bootstrap leg says so rather than passing.")
    ap.add_argument("--now", default=None, help="ISO clock override (naive = UTC)")
    args = ap.parse_args(argv)

    if args.now:
        now = datetime.fromisoformat(args.now.replace("Z", "+00:00"))
        # Naive stamps are UTC BY CONTRACT (the repo-wide #2463 convention) — the
        # same rule the sentinel's own --now carries, for the same reason.
        now = (now.replace(tzinfo=timezone.utc) if now.tzinfo is None
               else now.astimezone(timezone.utc))
    else:
        now = datetime.now(timezone.utc)

    return run(now=now, state_dir=Path(args.state_dir), sessions=args.sessions,
               as_json=args.as_json, with_r2=args.with_r2, r2_base=args.r2_base,
               receipts_dir=Path(args.receipts_dir) if args.receipts_dir else None)


if __name__ == "__main__":
    sys.exit(main())
