"""CN live-board rescue classifier — bounded, READ-ONLY stage diagnosis (CN-PR-4).

research/CN_BREATHING_PLATFORM_ARCHITECTURE_2026-08-15.md §8. The freshness
sentinel answers ONE question — "is the mainland runtime board fresh right now?"
— and when the answer is no, an operator still has to find out WHICH of five
independent legs broke: the nightly/asia-close arming step, the VPS evaluator
timer, the quote plane, the publish leg, or the reader route. Each has a
different lever and three of them look identical from the outside (a stale board
on the page). This maps the miss to its stage and names that stage's lever.

WHAT THIS IS NOT. v1 is ALERT/REPORT ONLY — it dispatches nothing, cancels
nothing and writes nothing, anywhere. There is no state file, no issue receipt,
no workflow_dispatch. That is not timidity, it is the §0.4 invariant set this
inherits from scripts/prophet_rescue.py plus the two things that lane learned the
hard way: asia-close's own gate already self-retries same-day (a second
dispatcher racing it spends runner hours to no effect), and killing a production
run is an OPERATOR call — a cancel is invisible to every staleness instrument we
own, because a killed bake and a bake that never fired leave the same trace:
nothing. So this prints a verdict and exits 0. Always 0: a diagnosis is not an
outcome, and a non-zero exit here would make an unattended shell treat "I looked
and told you" as a failure.

    python -m scripts.cn_live_rescue --classify
    python -m scripts.cn_live_rescue --classify --json
    python -m scripts.cn_live_rescue --classify --now 2026-08-17T06:00:00+00:00

ARCHITECTURE. ``collect()`` does every read and returns a frozen ``CNLiveState``;
``decide(state)`` is pure — no clock, no socket, no filesystem — and returns one
``Verdict`` from a CLOSED vocabulary. That split is what makes the ladder
testable over synthetic states instead of over a live estate that, by
construction, is only in the interesting configurations when something is on
fire. Same shape as prophet_rescue's ``decide``; a new failure mode gets a new
name in the vocabulary and a fixture in the matrix, never an unlabelled branch.

THE THREE-WAY PROBE SPLIT is the load-bearing detail. Every read answers ``ok``,
``absent``, ``unavailable`` or ``error``, and the last two must never collapse:

  * ``unavailable`` — NOT ATTEMPTED. No R2 credentials, no GH_TOKEN, not running
    on the VPS. Ordinary off-host conditions; they narrow what can be concluded
    and are reported as such.
  * ``error``   — ATTEMPTED AND FAILED. The probe is broken, so anything built on
    it would be a guess. Guesses become BLIND.
  * ``absent``  — a DEFINITIVE "not there" (HTTP 404, a missing file on a live
    tree). Only this may be read as a missing artifact.

Conflating the first two would make every laptop run BLIND; conflating the last
two would let a dead network read as "the pack was never armed" and send an
operator to re-arm a pack that is sitting right where it should be.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, time, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ONE clock and ONE set of budgets, imported from the sentinel rather than
# copied. A classifier that disagreed with the watchdog about what "stale" means
# would send operators to look at a leg the alarm is not even measuring.
from scripts.freshness_sentinel import (  # noqa: E402
    CN_LIVE_LUNCH_BUDGET_MIN,
    CN_LIVE_SESSION_BUDGET_MIN,
    DEFAULT_BASE,
    DEFAULT_PUBLIC_DIR,
    cn_phase,
)

# One definition of the repo slug, pinned by prophet_rescue's own
# test_default_repo_matches_the_git_remote. A second literal here is a second
# thing to rot, and a wrong slug 404s into BLIND rather than a false green.
from scripts.prophet_rescue import DEFAULT_REPO  # noqa: E402

USER_AGENT = "macro-cn-live-rescue/1.0"
HTTP_TIMEOUT_S = 15

#: The served live plane on the VPS (Caddy's external root). Read-only.
SERVED_LIVE_PATH = "/live/cn_prophet_live.json"
#: The R2 runtime plane (engine.prophet_live.r2io key space).
R2_PACK_KEY = "live_flow/cn_prophet_live_armed.json"
R2_LIVE_KEY = "live_flow/cn_prophet_live.json"

ASIA_CLOSE_WORKFLOW = "asia-close.yml"
#: By this UTC hour on a session day every scheduled asia-close attempt has been
#: spent — the lane's crons are 06:00 / 06:40 / 07:20 / 08:30 / 09:30 / 10:30 and
#: a last-chance 11:15, all of which fire with GitHub's usual lag. Past noon a
#: missing success is a miss, not a slow start.
SETTLEMENT_DEADLINE_UTC = time(12, 0)

#: Minutes of ``built_at`` skew between the two publish legs that still counts as
#: one write ordering rather than a split. The evaluator writes both within a
#: single pass, so three missed passes is already generous.
PUBLISH_SPLIT_SKEW_MIN = 15.0
#: Multiple of the payload's own ``delay_floor_min`` past which quotes are stale.
#: Mirrors the client's refusal rule (§7.5: age > 15 min × 3 tears the live layer
#: down), so the classifier and the browser draw the line in the same place.
QUOTE_AGE_CEILING_MULTIPLE = 3
DEFAULT_DELAY_FLOOR_MIN = 15.0

#: Reader-route statuses that mean the route WORKS. 401 is the healthy answer for
#: a gated artifact: /live/ is registration-walled by default (§6), so an
#: anonymous probe SHOULD be refused — a 200 here would be the finding. 403 is
#: deliberately NOT in this set: it is the CDN/WAF refusing, which is a broken
#: route for a real reader even though it is also "not a 404".
ROUTE_OK_STATUSES = frozenset({200, 401})

# ─────────────────────────────────────────────────────────────────────────────
# verdict vocabulary — CLOSED
# ─────────────────────────────────────────────────────────────────────────────
HEALTHY = "HEALTHY"
OUT_OF_SESSION = "OUT_OF_SESSION"
PACK_MISSING = "PACK_MISSING"
EVALUATOR_DEAD = "EVALUATOR_DEAD"
QUOTES_STALE = "QUOTES_STALE"
PUBLISH_SPLIT = "PUBLISH_SPLIT"
ROUTE_BROKEN = "ROUTE_BROKEN"
SETTLEMENT_LATE = "SETTLEMENT_LATE"
BLIND = "BLIND"

VERDICTS = (
    HEALTHY, OUT_OF_SESSION, PACK_MISSING, EVALUATOR_DEAD, QUOTES_STALE,
    PUBLISH_SPLIT, ROUTE_BROKEN, SETTLEMENT_LATE, BLIND,
)

#: One lever per verdict. Prose, not a command to run automatically — every one
#: of these is an operator action, and the script has no authority to take any of
#: them (see the module docstring).
LEVERS: dict[str, str] = {
    HEALTHY: "nothing to do — pack armed, board ticking inside its phase budget, "
             "publish legs agree and the reader route answers.",
    OUT_OF_SESSION: "nothing to do — the mainland is closed (weekend, holiday or "
                    "outside 09:30-15:15 CST); no pass is owed until it reopens.",
    PACK_MISSING: "the arm step did not leave a pack: asia-close's own gate "
                  "retries same-day, so check its runs first and only then "
                  "`gh workflow run asia-close.yml`.",
    EVALUATOR_DEAD: "the VPS evaluator is not ticking: check the mainland lane's "
                    "timer and journal (`systemctl list-timers 'macro-live-*'`) "
                    "and /live/orchestrator_status.json.",
    QUOTES_STALE: "the board is alive on a frozen quote plane: check the quote "
                  "lane on the VPS (/live/quotes.json age, /api/status "
                  "checks.quotes) — the state machine is evaluating stale prices.",
    PUBLISH_SPLIT: "the two publish legs disagree: one of the R2 put and the "
                   "atomic rename into /var/lib/macro-live/public/live is "
                   "failing — check the evaluator's publish step and R2 "
                   "credentials on the host.",
    ROUTE_BROKEN: "the artifact is fresh but the reader cannot get it: check "
                  "Caddy's /live/ handling and the regwall allowlists "
                  "(a 401 is HEALTHY here; a 404 or 5xx is not).",
    SETTLEMENT_LATE: "asia-close has no success today past the last-chance cron: "
                     "its gate retries same-day, so read the existing runs "
                     "first; if every attempt is spent, "
                     "`gh workflow run asia-close.yml`.",
    BLIND: "a probe this verdict depends on FAILED — no verdict is possible and "
           "none is guessed; fix the probe (network, token, R2 endpoint) and "
           "re-run before concluding anything about the lane.",
}


@dataclass(frozen=True)
class Verdict:
    """One classification: the name, the stage that owns it, and its lever."""

    name: str
    stage: str
    detail: str

    @property
    def lever(self) -> str:
        return LEVERS[self.name]

    def line(self) -> str:
        return f"{self.name} [{self.stage}] — {self.detail} LEVER: {self.lever}"


@dataclass(frozen=True)
class Probe:
    """One read. ``status`` ∈ ok | absent | unavailable | error (see the module
    docstring — ``unavailable`` and ``error`` must never collapse)."""

    status: str = "unavailable"
    detail: str = ""
    payload: dict | None = None
    code: int | None = None

    @property
    def ok(self) -> bool:
        return self.status == "ok"

    @property
    def failed(self) -> bool:
        """Attempted and broken — the only status that may produce BLIND."""
        return self.status == "error"


@dataclass(frozen=True)
class CNLiveState:
    """An already-fetched snapshot. ``decide`` sees nothing else."""

    now: datetime
    phase: str = "unknown"
    session: str | None = None
    budget_min: float | None = None
    in_window: bool = False
    clock_error: str | None = None
    pack: Probe = field(default_factory=Probe)
    served: Probe = field(default_factory=Probe)
    r2_live: Probe = field(default_factory=Probe)
    route: Probe = field(default_factory=Probe)
    settlement: Probe = field(default_factory=Probe)

    @property
    def evaluating(self) -> bool:
        """Whether a pass is OWED right now. ``budget_min`` is set exactly in the
        phases that owe a tick (morning, lunch freeze, afternoon, post-close) and
        None in pre-open, the post-close watch tail, and every closed phase."""
        return self.budget_min is not None

    @property
    def trading(self) -> bool:
        """In a phase where quote ages must advance. NOT the lunch freeze: quote
        ages are anchored to the 11:30 close of the morning segment by contract
        (§2), so they legitimately grow to 90 minutes across the break and a
        wall-clock quote-age rule would page every single session at 12:30."""
        return self.phase in ("morning", "afternoon", "post_close")


# ─────────────────────────────────────────────────────────────────────────────
# pure helpers
# ─────────────────────────────────────────────────────────────────────────────
def _instant(value: object) -> datetime | None:
    """One timezone-qualified ISO instant, normalized to UTC, or None."""
    if not isinstance(value, str) or not value:
        return None
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (stamp if stamp.tzinfo else stamp.replace(tzinfo=timezone.utc)).astimezone(
        timezone.utc
    )


def _age_min(stamp: datetime | None, now: datetime) -> float | None:
    return None if stamp is None else (now - stamp).total_seconds() / 60.0


def _built_age_min(probe: Probe, now: datetime) -> float | None:
    if not probe.ok or not isinstance(probe.payload, dict):
        return None
    return _age_min(_instant(probe.payload.get("built_at")), now)


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


# ─────────────────────────────────────────────────────────────────────────────
# the ladder — pure
# ─────────────────────────────────────────────────────────────────────────────
def decide(state: CNLiveState) -> Verdict:
    """One verdict over an already-fetched snapshot. No network, no clock.

    ORDER IS THE ARGUMENT, so it is stated rather than implied:

    1. A broken clock is BLIND before anything else — every branch below is
       phase-conditioned, so a phase we could not compute poisons all of them.
    2. Settlement is judged BEFORE the out-of-session gate, because its deadline
       (12:00 UTC = 20:00 CST) is deliberately outside the session: settlement is
       the post-session stage, and gating it on "in session" would make it
       unreachable by construction.
    3. Out of session, every remaining verdict is meaningless — nothing is owed —
       so OUT_OF_SESSION short-circuits.
    4. Then upstream to downstream: pack → publish → evaluator → quotes → route.
       PUBLISH_SPLIT sits ahead of EVALUATOR_DEAD on purpose: when both legs are
       readable and disagree, the disagreement itself PROVES the evaluator is
       alive, and calling that leg dead would send an operator to restart a timer
       that is running fine while the failing put goes unlooked-at.
    """
    now = state.now

    # 1 ── the clock ---------------------------------------------------------
    if state.clock_error:
        return Verdict(BLIND, "clock", f"cannot place the mainland session clock: "
                                       f"{state.clock_error}.")

    # 2 ── settlement (post-session; runs whether or not a pass is owed) ------
    if state.session and now.timetz().replace(tzinfo=None) >= SETTLEMENT_DEADLINE_UTC:
        if state.settlement.failed:
            return Verdict(BLIND, "settlement",
                           f"the asia-close probe failed ({state.settlement.detail}), "
                           "so 'no run today' cannot be distinguished from 'cannot "
                           "see the runs'.")
        if state.settlement.status == "absent":
            return Verdict(
                SETTLEMENT_LATE, "settlement",
                f"no successful {ASIA_CLOSE_WORKFLOW} run for session "
                f"{state.session} at "
                f"{now.strftime('%H:%M')}Z, past the "
                f"{SETTLEMENT_DEADLINE_UTC.strftime('%H:%M')}Z deadline "
                f"({state.settlement.detail}).",
            )

    # 3 ── out of session ----------------------------------------------------
    if not state.evaluating:
        return Verdict(
            OUT_OF_SESSION, "clock",
            f"mainland phase is {state.phase}"
            + (f" on session {state.session}" if state.session else "")
            + "; no evaluator pass is owed.",
        )

    # 4 ── in session: a failed probe is BLIND, never a guess ----------------
    for name, probe in (("pack", state.pack), ("served artifact", state.served),
                        ("R2 artifact", state.r2_live), ("reader route", state.route)):
        if probe.failed:
            return Verdict(BLIND, "probe",
                           f"the {name} probe failed ({probe.detail}); a verdict "
                           "built on it would be a guess.")
    if state.served.status == "unavailable" and state.r2_live.status == "unavailable":
        return Verdict(BLIND, "probe",
                       "neither publish leg could be read at all (not on the VPS "
                       f"and no R2 reader available: {state.r2_live.detail or 'no detail'}); "
                       "nothing about the lane can be concluded.")

    # ── pack (arm step) -----------------------------------------------------
    if state.pack.status == "absent":
        return Verdict(PACK_MISSING, "arm",
                       f"no armed pack at {R2_PACK_KEY} for session {state.session}.")
    if state.pack.ok:
        pack_session = (state.pack.payload or {}).get("session") or \
            (state.pack.payload or {}).get("as_of")
        if isinstance(pack_session, str) and state.session and pack_session < state.session:
            return Verdict(
                PACK_MISSING, "arm",
                f"the armed pack names session {pack_session}, older than today's "
                f"{state.session} — this session was never armed.",
            )

    served_age = _built_age_min(state.served, now)
    r2_age = _built_age_min(state.r2_live, now)
    budget = state.budget_min or CN_LIVE_SESSION_BUDGET_MIN

    # ── publish split (both legs readable and disagreeing) -------------------
    if state.served.ok and state.r2_live.status == "absent":
        return Verdict(PUBLISH_SPLIT, "publish",
                       "the VPS is serving a board that does not exist in R2 — the "
                       "R2 put leg is failing.")
    if state.r2_live.ok and state.served.status == "absent":
        return Verdict(PUBLISH_SPLIT, "publish",
                       "R2 holds a board that was never renamed into the served live "
                       "plane — the VPS publish leg is failing.")
    if served_age is not None and r2_age is not None:
        skew = abs(served_age - r2_age)
        if skew > PUBLISH_SPLIT_SKEW_MIN:
            older = "served" if served_age > r2_age else "R2"
            return Verdict(
                PUBLISH_SPLIT, "publish",
                f"the publish legs are {skew:.1f} min apart (served "
                f"{served_age:.1f} min, R2 {r2_age:.1f} min) — the {older} copy is "
                f"the stale one (skew budget {PUBLISH_SPLIT_SKEW_MIN:.0f} min).",
            )

    # ── evaluator ------------------------------------------------------------
    primary = state.served if state.served.ok else state.r2_live
    primary_name = "served" if state.served.ok else "R2"
    primary_age = served_age if state.served.ok else r2_age
    if not primary.ok:
        return Verdict(
            EVALUATOR_DEAD, "evaluator",
            f"no runtime board on either publish leg during phase {state.phase} "
            f"(served: {state.served.status}; R2: {state.r2_live.status}) — the "
            "lane is either not running or has never shipped its first artifact.",
        )
    if primary_age is None:
        return Verdict(EVALUATOR_DEAD, "evaluator",
                       f"the {primary_name} board carries no readable built_at "
                       f"({(primary.payload or {}).get('built_at')!r}) — it cannot "
                       "vouch for its own tick.")
    if primary_age > budget:
        return Verdict(
            EVALUATOR_DEAD, "evaluator",
            f"the {primary_name} board last built {primary_age:.1f} min ago, past "
            f"the {budget:.0f} min budget for phase {state.phase}.",
        )

    payload = primary.payload or {}
    liveness = payload.get("liveness")
    liveness = liveness if isinstance(liveness, dict) else {}

    # ── quotes ---------------------------------------------------------------
    if state.trading:
        floor_min = _number(payload.get("delay_floor_min")) or DEFAULT_DELAY_FLOOR_MIN
        ceiling_sec = floor_min * 60.0 * QUOTE_AGE_CEILING_MULTIPLE
        p50 = _number(liveness.get("quote_age_sec_p50"))
        if p50 is not None and p50 > ceiling_sec:
            return Verdict(
                QUOTES_STALE, "quotes",
                f"the board is ticking ({primary_age:.1f} min) but its median quote "
                f"is {p50 / 60.0:.1f} min old, past the "
                f"{ceiling_sec / 60.0:.0f} min ceiling "
                f"({floor_min:.0f} min delay floor x{QUOTE_AGE_CEILING_MULTIPLE}).",
            )

    # ── reader route ---------------------------------------------------------
    if state.route.status == "absent" or (
        state.route.code is not None and state.route.code not in ROUTE_OK_STATUSES
    ):
        return Verdict(
            ROUTE_BROKEN, "route",
            f"the board is fresh ({primary_age:.1f} min) but the public route "
            f"answers {state.route.code if state.route.code is not None else 'nothing'} "
            f"({state.route.detail}) — a reader sees the static board only.",
        )

    return Verdict(
        HEALTHY, "end-to-end",
        f"phase {state.phase}, board built {primary_age:.1f} min ago (budget "
        f"{budget:.0f} min), publish legs agree, route "
        f"{state.route.code if state.route.code is not None else 'not probed'}.",
    )


# ─────────────────────────────────────────────────────────────────────────────
# fetch layer — thin, total, and never raises into decide()
# ─────────────────────────────────────────────────────────────────────────────
def _get(url: str, headers: dict[str, str] | None = None,
         timeout: int = HTTP_TIMEOUT_S) -> tuple[int | None, bytes | None, str | None]:
    """GET → (status, body, error). Every failure is a string, never an exception.

    An HTTPError still carries its STATUS, which is the whole point for the route
    probe: 401 and 404 are both "not 200" to urllib and opposite answers here.
    """
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                               **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            return resp.status, resp.read(), None
    except urllib.error.HTTPError as exc:
        return exc.code, None, f"HTTP {exc.code}"
    except Exception as exc:  # noqa: BLE001 — DNS/TLS/timeout are facts, not crashes
        return None, None, f"{type(exc).__name__}: {exc}"


def probe_served(public_dir: Path) -> Probe:
    """The board as the VPS serves it, read off disk.

    A missing PARENT directory means we are not on the VPS at all → unavailable
    (not attempted), while a missing FILE inside a live tree is a definitive
    absent. The distinction is what keeps a laptop run from reporting an outage.
    """
    target = public_dir / SERVED_LIVE_PATH.lstrip("/")
    if not target.parent.is_dir():
        return Probe("unavailable", f"no live plane at {target.parent} "
                                    "(not running on the VPS)")
    try:
        raw = target.read_text(encoding="utf-8")
    except FileNotFoundError:
        return Probe("absent", f"no file at {target}")
    except OSError as exc:
        return Probe("error", f"{type(exc).__name__}: {exc}")
    try:
        doc = json.loads(raw)
    except ValueError as exc:
        return Probe("error", f"served payload is not JSON ({exc})")
    if not isinstance(doc, dict):
        return Probe("error", "served payload is not a JSON object")
    return Probe("ok", f"read {target}", payload=doc)


def probe_r2(key: str) -> Probe:
    """One R2 object through the shared engine helpers.

    ``r2io.get_json`` prefers the authenticated path and falls back to the public
    mirror, and returns None for BOTH "no such key" and "the read failed" — an
    ambiguity a watchdog cannot afford, because it is the difference between "the
    pack was never armed" and "your network is down". So a None is classified
    with one HTTP status against the same public base before it is called absent.
    """
    try:
        from engine.prophet_live import r2io  # noqa: PLC0415 — lazy: boto3 may be absent
    except Exception as exc:  # noqa: BLE001
        return Probe("unavailable",
                     f"engine.prophet_live.r2io unimportable "
                     f"({type(exc).__name__}: {exc})")
    try:
        doc = r2io.get_json(key)
    except Exception as exc:  # noqa: BLE001 — boto3/credential failures are facts
        return Probe("error", f"R2 read raised ({type(exc).__name__}: {exc})")
    if isinstance(doc, dict):
        return Probe("ok", f"read {key}", payload=doc)
    if doc is not None:
        return Probe("error", f"{key} is not a JSON object")
    try:
        base = r2io.public_base()
    except Exception as exc:  # noqa: BLE001
        return Probe("error", f"cannot resolve the R2 public base "
                              f"({type(exc).__name__}: {exc})")
    code, _, err = _get(f"{base}/{key.lstrip('/')}")
    if code == 404:
        return Probe("absent", f"no object at {key} (404 on the public mirror)",
                     code=code)
    if code is None:
        return Probe("error", f"{key} unreadable and unclassifiable ({err})")
    return Probe("error", f"{key} answered HTTP {code} on the public mirror",
                 code=code)


def probe_route(base: str = DEFAULT_BASE) -> Probe:
    """What a reader's browser gets from the public route.

    401 is a PASS: /live/ is registration-walled by default (§6), so an anonymous
    probe should be refused — being served the payload anonymously would be the
    finding, not the health check. 404 and 5xx are the failures; the artifact can
    be perfect on disk and invisible on the site.
    """
    url = base.rstrip("/") + SERVED_LIVE_PATH
    code, _, err = _get(url)
    if code is None:
        return Probe("error", f"{url}: {err}")
    if code in ROUTE_OK_STATUSES:
        return Probe("ok", f"{url} answered HTTP {code}"
                           + (" (gated — the healthy answer for a walled artifact)"
                              if code == 401 else ""),
                     code=code)
    if code == 404:
        return Probe("absent", f"{url} answered HTTP 404", code=code)
    return Probe("error", f"{url} answered HTTP {code}", code=code)


def probe_settlement(now: datetime, repo: str, token: str | None) -> Probe:
    """Newest completed asia-close run for today, through the GitHub API.

    ONE page, never paginated: the REST pool is one shared bucket across the
    whole fleet and this is a diagnostic, not a monitor. No token ⇒ not attempted
    (``unavailable``), because anonymous reads are 60/hr and a rate-limited probe
    that answered "no runs" would manufacture SETTLEMENT_LATE out of thin air.
    """
    if not token:
        return Probe("unavailable", "no GH_TOKEN/GITHUB_TOKEN — settlement "
                                    "recency not probed")
    url = (f"https://api.github.com/repos/{repo}/actions/workflows/"
           f"{ASIA_CLOSE_WORKFLOW}/runs?per_page=20")
    code, body, err = _get(url, {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Authorization": f"Bearer {token}",
    })
    if err is not None or body is None:
        return Probe("error", f"GitHub API: {err or 'empty body'}", code=code)
    try:
        payload = json.loads(body)
    except ValueError as exc:
        return Probe("error", f"GitHub API: unparseable JSON ({exc})", code=code)
    runs = payload.get("workflow_runs") if isinstance(payload, dict) else None
    if not isinstance(runs, list):
        return Probe("error", "GitHub API: no workflow_runs array", code=code)
    today = now.date()
    for row in runs:
        if not isinstance(row, dict):
            continue
        if row.get("status") != "completed" or row.get("conclusion") != "success":
            continue
        started = _instant(row.get("run_started_at")) or _instant(row.get("created_at"))
        if started is not None and started.date() == today:
            return Probe("ok", f"run {row.get('id')} succeeded at "
                               f"{started.isoformat()}", payload=dict(row))
    return Probe("absent", f"no successful {ASIA_CLOSE_WORKFLOW} run in the newest "
                           f"{len(runs)} for {today.isoformat()}")


def collect(now: datetime, *, public_dir: Path | None = None,
            base: str = DEFAULT_BASE, repo: str = DEFAULT_REPO,
            token: str | None = None) -> CNLiveState:
    """Every read this classifier makes, once, into a frozen snapshot.

    Reads only what the phase can use: outside a mainland session nothing is
    owed, so the R2, disk and route probes are skipped entirely (the settlement
    probe still runs — its deadline is deliberately post-session). A diagnostic
    that spends four network round trips to say "it is Sunday" is a diagnostic
    nobody runs.
    """
    phase = cn_phase(now)
    session = phase["session"]
    settlement = Probe("unavailable", "before the settlement deadline")
    if session and now.timetz().replace(tzinfo=None) >= SETTLEMENT_DEADLINE_UTC:
        settlement = probe_settlement(now, repo, token)
    if phase["error"] or phase["budget_min"] is None:
        return CNLiveState(
            now=now, phase=phase["phase"], session=session,
            budget_min=phase["budget_min"], in_window=bool(phase["in_window"]),
            clock_error=phase["error"], settlement=settlement,
            pack=Probe("unavailable", "not probed outside an evaluating phase"),
            served=Probe("unavailable", "not probed outside an evaluating phase"),
            r2_live=Probe("unavailable", "not probed outside an evaluating phase"),
            route=Probe("unavailable", "not probed outside an evaluating phase"),
        )
    return CNLiveState(
        now=now, phase=phase["phase"], session=session,
        budget_min=phase["budget_min"], in_window=bool(phase["in_window"]),
        clock_error=None,
        pack=probe_r2(R2_PACK_KEY),
        served=probe_served(Path(public_dir or DEFAULT_PUBLIC_DIR)),
        r2_live=probe_r2(R2_LIVE_KEY),
        route=probe_route(base),
        settlement=settlement,
    )


# ─────────────────────────────────────────────────────────────────────────────
# reporting
# ─────────────────────────────────────────────────────────────────────────────
def report(state: CNLiveState, verdict: Verdict) -> dict[str, Any]:
    """The --json body: the verdict AND every probe that produced it.

    The probe table ships whether or not it changed the verdict, because the
    first question asked of any diagnosis is "what did you actually look at" —
    and for a classifier whose honest answer is often 'unavailable', that table
    is most of the information.
    """
    return {
        "schema": "cn_live_rescue.classification/v1",
        "generated_at": state.now.isoformat(),
        "verdict": verdict.name,
        "stage": verdict.stage,
        "detail": verdict.detail,
        "lever": verdict.lever,
        "phase": state.phase,
        "session": state.session,
        "budget_min": state.budget_min,
        "probes": {
            name: {k: v for k, v in asdict(probe).items() if k != "payload"}
            for name, probe in (
                ("pack", state.pack), ("served", state.served),
                ("r2_live", state.r2_live), ("route", state.route),
                ("settlement", state.settlement),
            )
        },
        "authority": "report-only — this tool dispatches nothing and writes nothing",
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="CN live-board rescue classifier (CN-PR-4) — read-only")
    ap.add_argument("--classify", action="store_true",
                    help="collect the estate and print one verdict (the only mode)")
    ap.add_argument("--json", action="store_true", help="emit the machine body")
    ap.add_argument("--now", default=None,
                    help="ISO-8601 clock override for the decision (testing/drills)")
    ap.add_argument("--public-dir", default=os.environ.get(
        "SENTINEL_PUBLIC_DIR", DEFAULT_PUBLIC_DIR))
    ap.add_argument("--base", default=os.environ.get("SENTINEL_BASE", DEFAULT_BASE))
    ap.add_argument("--repo", default=DEFAULT_REPO)
    args = ap.parse_args(argv)

    if not args.classify:
        ap.error("--classify is required (this tool has exactly one mode)")

    if args.now:
        # A bad --now ERRORS rather than falling back to the wall clock:
        # silently answering about a different moment than the operator asked
        # about turns a deliberate probe into a misleading one.
        now = _instant(args.now)
        if now is None:
            ap.error(f"--now is not an ISO-8601 instant: {args.now!r}")
    else:
        now = datetime.now(timezone.utc)

    state = collect(now, public_dir=Path(args.public_dir), base=args.base,
                    repo=args.repo,
                    token=os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN"))
    verdict = decide(state)
    body = report(state, verdict)
    if args.json:
        print(json.dumps(body, indent=1, sort_keys=True), flush=True)
    else:
        print(verdict.line(), flush=True)
        for name, probe in sorted(body["probes"].items()):
            print(f"  {name:<11} {probe['status']:<12} {probe['detail']}", flush=True)
    # ALWAYS 0. A diagnosis is not an outcome, and this lane has no authority to
    # act on one (module docstring).
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
