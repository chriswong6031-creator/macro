"""Live Entry Radar PR-4 (W4) — the health receipt and the W5 firewall.

WHAT THIS SUITE IS FOR
----------------------
A live lane fails most often by staying GREEN.  The process is up, the artifact
is being rewritten, the checks pass — and the content stopped moving hours ago.
Design §6 answers that with a receipt whose states are ENUMERATED and whose
content-advance is a separate signal from its process-advance, and this suite is
where those claims stop being prose:

  LIV-1   PIT-W4-14: every health state is REACHABLE from a constructed input
          and DISTINGUISHABLE from every other one — a receipt whose states
          collapse into each other sends an operator to the wrong lane
  LIV-2   a whole-cycle refusal publishes §5's shape exactly: every probe name
          ``unavailable``, ZERO transitions, ZERO events, and nothing spooled
  LIV-3   a missed cadence is NAMED, with the gap counted in intervals
  LIV-4   the receipt is design §6's own key structure, asserted from a
          re-typed copy of the spec rather than from the module's output
  LIV-5   the content-advance signal actually advances — and holds still when
          nothing was admitted, which is the half that makes it a signal
  LIV-6   a killed lane publishes an HONEST payload: schema, asof, an all-false
          authority block and every probe name, so "stood down" can never be
          misread as "no names in the universe"
  LIV-7   PIT-W4-20: the W5 firewall over every EMITTED key in the pack, the
          journal, the ledger, the spool object and the payload
  LIV-8   RESOLVED-at-H is calendar arithmetic — no price is read on the
          stamping path, asserted structurally AND behaviourally
  LIV-9   the freshness sentinel reads a field the payload actually emits

WHY EACH GUARD CARRIES A MUTATION CONTROL.  Reachability tests are the easiest
in the world to write vacuously: a state that is "reached" because the pass
degraded for an unrelated reason proves nothing.  So LIV-1 collects (state,
reasons) pairs and asserts they are PAIRWISE DISTINCT, LIV-3 pairs the 20-minute
gap with a 5-minute control that must report no gap at all, LIV-5 pairs the
advance with a re-run that must NOT advance, LIV-7 plants a forward-return key
and requires the sweep to find it, and LIV-8 plants a price read and requires
the scanner to catch it.

``failed`` IS REACHED, AND FROM EXACTLY ONE PLACE.  It has no producer inside
``run_pass`` — a pass that raised cannot describe itself — and exactly one
outside it: ``live_eval.failure_payload``, called by the entrypoint's top-level
handler, which publishes the receipt and exits 6.  Both halves are asserted (the
producer test names the only lawful producer; the script test drives the
entrypoint and reads the published file), because the state used to be declared
in ``HEALTH_STATES`` with nothing producing it at all, and a raised pass then
returned 0 in silence over a stale-but-whole artifact.

Synthetic fixtures only, shared with ``test_entry_radar_w4_pack.py``.  No
``data/``, no network, no wall clock — every instant in this file is a value the
test chose.  The two script tests write only into ``tmp_path``.
"""
from __future__ import annotations

import ast
import inspect
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import scripts.freshness_sentinel as FS
from engine.entry_radar import live_eval as le
from engine.entry_radar import live_ledger as ll
from engine.session_digest import session_window_et
from tests.test_entry_radar_w4_pack import AS_OF, NEXT_SESSION, build

ROOT = Path(__file__).resolve().parents[1]

#: Design §6's health block, RE-TYPED from the doc rather than imported from the
#: module under test.  Two independent copies is the point: a drift in either one
#: reds this suite, which an ``assert BLOCK == BLOCK`` cannot.  Extra keys are
#: lawful (the implementation adds ``prev_at``, ``pack_hash``, ``proof_failed``,
#: ``unchecked_n``, ``deferred_n``, ``dark``); a MISSING one is not.
DESIGN_S6_HEALTH: dict = {
    "state": None,
    "reasons": None,
    "pass": {"seq": None, "at": None, "expected_next": None,
             "prev_gap_intervals": None},
    "inputs": {
        "quotes": {"asof": None, "age_s": None, "coverage": None, "stale_n": None},
        "pack": {"as_of": None, "fresh": None},
        "spool": {"ok": None, "key": None},
        "c3_reader": {"fetched_n": None, "cache_hits": None, "errors": None},
    },
    "basis": {"audited_n": None, "mismatched_n": None, "refused": None},
    "content": {"last_transition_at": None, "events_total": None,
                "ledger_hash": None},
}

#: A Saturday, asserted against the calendar helper in the test below rather
#: than trusted from the literal.
WEEKEND_INSTANT = datetime(2026, 8, 15, 14, 2, tzinfo=timezone.utc)

#: Names a price read on the RESOLVED-at-H path would have to touch.
PRICE_ACCESSORS = ("close", "price", "sampled_close", "high", "low",
                   "as_of_close", "prev_close")

#: Exemptions that genuinely match a forbidden token, and so are load-bearing —
#: without them the token sweep would flag a lawful field.  MEASURED, then pinned.
LOAD_BEARING_EXEMPTIONS = frozenset({
    "can_rank", "scored_authority", "detector_score", "opportunity_score",
})

#: Exemptions that match NO forbidden token today, so they exempt nothing.  They
#: are inert rather than wrong — see the test that pins this split and why the
#: list is stated instead of quietly tolerated.
INERT_EXEMPTIONS = frozenset({
    "can_size", "can_gate", "can_originate_signal", "can_escalate",
    "research_priority",
})


# ---------------------------------------------------------------------------
# fixtures — one pack, one quote book, one pass helper
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def pack():
    return build()


def session_instant(minutes: float) -> datetime:
    """``minutes`` after the NEXT_SESSION open, as a UTC instant."""
    open_dt, _close = session_window_et(NEXT_SESSION)
    return (open_dt + timedelta(minutes=float(minutes))).astimezone(timezone.utc)


def quote_book(pack, *, ts: datetime, mult: float = 0.90, basis: str = "trade",
               prev_mult: float = 1.0, tickers=None) -> dict:
    """The shared snapshot in ``live_verify.load_live_quotes`` shape."""
    rows = pack.by_ticker()
    names = list(tickers) if tickers is not None else sorted(pack.substrate)
    return {
        "asof": ts.isoformat(),
        "delayed_min": 15,
        "quotes": {t: {"price": float(rows[t].as_of_close or 100.0) * mult,
                       "ts": ts.timestamp() * 1000.0,
                       "source": "polygon", "basis": basis,
                       "prevClose": (None if rows[t].as_of_close is None
                                     else float(rows[t].as_of_close) * prev_mult)}
                   for t in names},
    }


class RecordingSpool(ll.EventSpool):
    """A spool that records every call and never writes.  ``ok`` controls the
    receipt so the same double serves both the "never called" and the "failed"
    assertions."""

    def __init__(self, local_dir: Path, *, ok: bool = True) -> None:
        super().__init__(local_dir=local_dir)
        self.calls: list[dict] = []
        self._ok = bool(ok)

    def append_pass(self, payload, *, session, stamp, pass_id):
        self.calls.append({"session": session, "stamp": stamp, "pass_id": pass_id})
        if not self._ok:
            return None
        return ll.spool_key(session, stamp, prefix=self.prefix, pass_id=pass_id)


def arming_pass(base, state_dir: Path, *, now: datetime | None = None,
                ledger=None, spool=None, **overrides):
    """One in-window pass whose quote is early enough to produce a C1 arm.

    The print lands two minutes after the open and the pass looks ten minutes
    later, so the first sampled interval has closed and its reading is a real
    one — a pass that looks BEFORE any interval has ended evaluates honestly to
    ``unavailable`` and mints no transition, which is correct behaviour and
    useless as a fixture for the ledger-hash and spool tests.

    The pack is the first POSITIONAL argument and ``pack=`` is an override, so a
    route that needs a different pack (or none at all) says so without the
    fixture having to know why.
    """
    when = session_instant(12) if now is None else now
    quotes = overrides.pop("quotes", None)
    if quotes is None:
        quotes = quote_book(base, ts=session_instant(2))
    return le.run_pass(now=when, pack=overrides.pop("pack", base), quotes=quotes,
                       ledger=ledger if ledger is not None
                       else ll.LiveEpisodeLedger(state_dir),
                       state_dir=state_dir, spool=spool,
                       unspooled_ok=overrides.pop("unspooled_ok", spool is None),
                       env=overrides.pop("env", {}), **overrides)


# ---------------------------------------------------------------------------
# LIV-1 — PIT-W4-14: reachable AND distinguishable
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def census(pack, tmp_path_factory):
    """One pass per health route, each in its OWN state dir.

    Separate dirs matter: the kill FILE route writes a sentinel into the state
    directory, and a shared dir would kill every later route in the census — a
    fixture that reached one state by accidentally reaching another is exactly
    the vacuous reachability this test exists to refuse.
    """
    def fresh(label: str) -> Path:
        return tmp_path_factory.mktemp(label)

    out: dict[str, le.PassResult] = {}

    out["killed_env"] = arming_pass(pack, fresh("killed_env"),
                                    env={le.KILL_ENV: "1"})

    kill_dir = fresh("killed_file")
    (kill_dir / le.KILL_FILE).write_text("stood down by hand\n", encoding="utf-8")
    out["killed_file"] = arming_pass(pack, kill_dir)

    out["weekend"] = arming_pass(pack, fresh("weekend"), now=WEEKEND_INSTANT)
    out["pre_open"] = arming_pass(pack, fresh("pre_open"), now=session_instant(-30))
    close_dt = session_window_et(NEXT_SESSION)[1]
    out["post_close"] = arming_pass(
        pack, fresh("post_close"),
        now=(close_dt + timedelta(minutes=le.WINDOW_END_GRACE_MIN + 10)
             ).astimezone(timezone.utc))
    out["grace"] = arming_pass(
        pack, fresh("grace"),
        now=(close_dt + timedelta(minutes=le.WINDOW_END_GRACE_MIN - 5)
             ).astimezone(timezone.utc),
        quotes=quote_book(pack, ts=(close_dt - timedelta(minutes=2)
                                    ).astimezone(timezone.utc)))

    out["no_pack"] = arming_pass(pack, fresh("no_pack"), pack=None)
    out["stale_pack"] = arming_pass(
        pack, fresh("stale_pack"),
        now=datetime(2026, 8, 18, 14, 2, tzinfo=timezone.utc),
        quotes=quote_book(pack, ts=datetime(2026, 8, 18, 14, 0, tzinfo=timezone.utc)))
    out["proof_failed"] = arming_pass(
        pack, fresh("proof_failed"),
        pack=pack.with_proof({"pass": False, "cases": []}))

    spool_dir = fresh("spool_failed")
    out["spool_failed"] = arming_pass(
        pack, spool_dir, spool=RecordingSpool(spool_dir / "spool", ok=False),
        unspooled_ok=False)

    out["stale_quotes"] = arming_pass(
        pack, fresh("stale_quotes"), now=session_instant(180),
        quotes=quote_book(pack, ts=session_instant(2)))
    out["basis_mismatch"] = arming_pass(
        pack, fresh("basis_mismatch"),
        quotes=quote_book(pack, ts=session_instant(2), prev_mult=1.05))

    out["live"] = arming_pass(pack, fresh("live"))
    return out


def state_of(result) -> str:
    return str(result.health["state"])


def test_LIV1_the_env_kill_switch_reaches_killed_and_NAMES_the_switch(census):
    result = census["killed_env"]
    assert state_of(result) == "killed"
    assert result.health["reasons"] == [f"kill_switch:{le.KILL_ENV}"]
    assert result.exit_code == 0, "a deliberate stand-down is not a failure"


def test_LIV1_the_kill_FILE_reaches_killed_and_NAMES_A_DIFFERENT_switch(census):
    """Two doors, two receipts.

    The env var is the operator's stand-down without a unit edit; the file is
    the stand-down for a host whose environment they cannot change.  A receipt
    that said only "killed" would leave an operator hunting the wrong one.
    """
    result = census["killed_file"]
    assert state_of(result) == "killed"
    assert result.health["reasons"] == [f"kill_switch:{le.KILL_FILE} file"]
    assert result.health["reasons"] != census["killed_env"].health["reasons"]


@pytest.mark.parametrize("label,reason", [("weekend", "not_a_session"),
                                          ("pre_open", "pre_open"),
                                          ("post_close", "post_close")])
def test_LIV1_out_of_window_distinguishes_its_three_reasons(census, label, reason):
    """Three different facts about "we did not evaluate", never one flat bool.

    A calendar holiday, a timer that fired early and a timer that fired after
    the grace are three different operational stories; a lane that reported only
    ``out_of_window`` would make the first indistinguishable from the third.
    """
    from lib.nyse_calendar import is_session

    result = census[label]
    assert state_of(result) == "out_of_window"
    assert result.health["reasons"] == [reason]
    assert result.exit_code == 0
    if label == "weekend":
        # VERIFIED against the calendar rather than trusted from a date literal.
        assert is_session(WEEKEND_INSTANT.date()) is False
        assert result.payload["session"] is None
    else:
        assert is_session(NEXT_SESSION) is True
        assert result.payload["session"] == NEXT_SESSION.isoformat()


def test_LIV1_CONTROL_the_close_side_grace_keeps_a_late_pass_IN_window(census):
    """The grace is load-bearing, not decorative.

    The session's last sampled interval ends AT the close and the timer fires on
    a UTC grid, so an ungraced window would drop the most informative interval
    of the day on most days.
    """
    result = census["grace"]
    assert state_of(result) != "out_of_window"
    assert result.payload["session"] == NEXT_SESSION.isoformat()


def test_LIV1_the_window_boundary_is_the_grace_and_nothing_wider():
    """CONTROL on the boundary itself, at the pure function.

    Asserting on ``run_pass`` alone could not tell a grace of ten minutes from
    one of ten hours; this pins both sides of the edge.
    """
    close_dt = session_window_et(NEXT_SESSION)[1]
    inside, why, _s = le.in_window(
        (close_dt + timedelta(minutes=le.WINDOW_END_GRACE_MIN - 1)
         ).astimezone(timezone.utc))
    assert (inside, why) == (True, "in_window")
    outside, why, _s = le.in_window(
        (close_dt + timedelta(minutes=le.WINDOW_END_GRACE_MIN + 1)
         ).astimezone(timezone.utc))
    assert (outside, why) == (False, "post_close")


@pytest.mark.parametrize("label,reason", [("no_pack", "no_pack"),
                                          ("stale_pack", f"pack_as_of:{AS_OF}")])
def test_LIV1_both_pack_faults_reach_stale_pack_with_exit_5(census, label, reason):
    """A wrong-session series FABRICATES crossings, so the gate is fail-closed
    and the exit code says the lane did not do its job."""
    result = census[label]
    assert state_of(result) == "stale_pack"
    assert result.health["reasons"] == [reason]
    assert result.exit_code == 5


def test_LIV1_a_failed_inversion_proof_reaches_proof_failed_with_exit_5(census):
    """Carried separately from ``stale_pack`` on purpose: a pack whose proof
    failed is a different operational fault from one built for the wrong
    session, and collapsing them sends an operator to the wrong lane."""
    result = census["proof_failed"]
    assert state_of(result) == "proof_failed"
    assert result.health["reasons"] == ["pack_inversion_proof_failed"]
    assert result.exit_code == 5


def test_LIV1_a_spool_failure_degrades_the_pass_and_WITHHOLDS_its_transitions(census):
    """Spool before consume: a failure withholds from the ledger AND the payload.

    A payload showing a transition the ledger refused to admit would be the
    second source of truth the whole rule exists to prevent.
    """
    result = census["spool_failed"]
    assert state_of(result) == "degraded"
    assert "spool_failed" in result.health["reasons"]
    assert result.committed is False
    assert result.exit_code == 4
    assert result.payload["transitions"] == []
    assert result.payload["events"] == []
    assert not result.delta.empty, "the fixture withheld nothing at all"


def test_LIV1_stale_quotes_degrade_the_pass_and_are_COUNTED(census):
    result = census["stale_quotes"]
    assert state_of(result) == "degraded"
    assert any(r.startswith("stale_quote:") for r in result.health["reasons"])
    assert result.health["inputs"]["quotes"]["stale_n"] == len(result.names)
    assert result.health["dark"]["stale_quote"] == len(result.names)


def test_LIV1_a_basis_mismatch_degrades_the_pass_and_names_the_refused(census):
    """W3-1 carried forward: the engine is never reached for a mismatched name."""
    result = census["basis_mismatch"]
    assert state_of(result) == "degraded"
    assert any(r.startswith("basis_mismatch:") for r in result.health["reasons"])
    assert result.health["basis"]["mismatched_n"] == len(result.names)
    assert result.health["basis"]["refused"] == sorted(
        n.ticker for n in result.names)
    assert all(n.observations == () for n in result.names)


def test_LIV1_a_clean_pass_is_live_with_no_reasons(census):
    result = census["live"]
    assert state_of(result) == "live"
    assert result.health["reasons"] == []
    assert result.exit_code == 0


def test_LIV1_failed_has_EXACTLY_ONE_producer_and_run_pass_is_not_it(census):
    """``failed`` is unreachable from any input to ``run_pass``, and produced by
    exactly one function outside it.

    TRUTH CHANGE (W4R/C2 adjudication).  This test previously asserted that
    ``failed`` had NO producer anywhere, on the reasoning that a process which
    has genuinely failed cannot be trusted to diagnose itself.  The measured
    consequence was worse than the risk: a pass that raised exited 0 with nothing
    written, so the served artifact kept its previous body AND its previous
    ``health.pass.at`` — stale but whole — and the only alarm was the freshness
    sentinel, pinned at SESSION grain.  A persistent per-name defect could burn a
    full session green.

    The reasoning survives where it was right: ``run_pass`` still never produces
    ``failed``.  The producer is :func:`live_eval.failure_payload`, called from
    the ENTRYPOINT's outer handler — a live process with a resolved live
    directory, publishing a receipt about the pass that died rather than about
    itself.  The state is reachable and its reachability case is below.
    """
    tree = ast.parse((ROOT / "engine" / "entry_radar" / "live_eval.py")
                     .read_text(encoding="utf-8"))
    producers = [node for node in ast.walk(tree)
                 if isinstance(node, ast.FunctionDef)
                 and any(isinstance(n, ast.Constant) and n.value == "failed"
                         for n in ast.walk(node))]
    assert [f.name for f in producers] == ["failure_payload"], (
        f"'failed' is produced by {[f.name for f in producers]}; the only lawful "
        f"producer is failure_payload, and a new one needs its own reachability "
        f"case in LIV-1")
    assert "failed" in le.HEALTH_STATES
    assert "failed" in le.CYCLE_REFUSALS
    assert "failed" not in {state_of(r) for r in census.values()}, \
        "run_pass produced 'failed' — the receipt must come from outside it"


def test_LIV1_every_declared_health_state_is_accounted_for(census):
    """No state is declared and forgotten, and none is reached by accident."""
    reached = {state_of(result) for result in census.values()}
    assert reached <= set(le.HEALTH_STATES), sorted(reached - set(le.HEALTH_STATES))
    assert set(le.HEALTH_STATES) - reached == {"failed"}


def test_LIV1_the_reached_states_are_PAIRWISE_DISTINGUISHABLE(census):
    """Reachability without distinguishability is a receipt that says nothing.

    Two routes that publish the same (state, reasons) pair are two faults an
    operator cannot tell apart from the artifact, which is the failure mode §6's
    enumeration exists to prevent.

    ``grace`` is excluded and its collision with ``live`` is asserted separately
    below, because there the sameness IS the property: a graced pass is an
    ordinary live pass, not a mode of its own.
    """
    routes = {k: v for k, v in census.items() if k != "grace"}
    fingerprints: dict[tuple[str, tuple[str, ...]], list[str]] = {}
    for label, result in routes.items():
        key = (state_of(result), tuple(sorted(result.health["reasons"])))
        fingerprints.setdefault(key, []).append(label)
    collisions = {k: v for k, v in fingerprints.items() if len(v) > 1}
    assert collisions == {}, f"indistinguishable routes: {collisions}"
    assert len(fingerprints) == len(routes)


def test_LIV1_a_graced_pass_is_DELIBERATELY_the_same_receipt_as_a_normal_one(census):
    """The one collision this suite wants.

    The grace exists so the session's LAST interval — the most informative one
    of the day — is evaluated rather than dropped by a timer that fired seconds
    late.  A receipt that flagged it would turn every well-behaved close into an
    anomaly for an operator to chase.
    """
    grace, live = census["grace"], census["live"]
    assert state_of(grace) == state_of(live) == "live"
    assert grace.health["reasons"] == live.health["reasons"] == []


# ---------------------------------------------------------------------------
# LIV-2 — a whole-cycle refusal publishes §5's shape
# ---------------------------------------------------------------------------

#: The census labels whose state is a whole-cycle refusal AND which carry a pack,
#: so a probe set exists to be named.  ``no_pack`` is excluded deliberately: with
#: no pack there is no embedded probe set, so there are no names to publish.
REFUSAL_LABELS = ("killed_env", "killed_file", "weekend", "pre_open", "post_close",
                  "stale_pack", "proof_failed")


@pytest.mark.parametrize("label", REFUSAL_LABELS)
def test_LIV2_a_whole_cycle_refusal_darks_every_name_and_admits_nothing(census, label):
    """§5's row is not a degraded evaluation but an ABSENT one, said for every
    probe name at once."""
    result = census[label]
    assert state_of(result) in le.CYCLE_REFUSALS
    rows = result.payload["names"]
    assert rows, "a refusal that names no probe is indistinguishable from an empty universe"
    assert {row["state"] for row in rows} == {"unavailable"}
    assert all(row["reasons"] == result.health["reasons"] for row in rows)
    assert all(row["lanes"] == {} for row in rows)
    assert result.payload["transitions"] == []
    assert result.payload["events"] == []
    assert result.delta is None
    assert result.spool_key is None


@pytest.mark.parametrize("label", REFUSAL_LABELS)
def test_LIV2_a_refusal_names_EVERY_probe_and_drops_none(census, pack, label):
    """Coverage honesty carried into the refusal path: a name the cycle could
    not look at is ``unavailable``, never absent."""
    rows = census[label].payload["names"]
    assert [row["ticker"] for row in rows] == sorted(pack.substrate)


@pytest.mark.parametrize("label,make", [
    ("killed", lambda p, d: {"env": {le.KILL_ENV: "1"}}),
    ("out_of_window", lambda p, d: {"now": session_instant(-30)}),
    ("stale_pack", lambda p, d: {
        "now": datetime(2026, 8, 18, 14, 2, tzinfo=timezone.utc)}),
    ("proof_failed", lambda p, d: {"pack": p.with_proof({"pass": False, "cases": []})}),
])
def test_LIV2_the_spool_is_NEVER_TOUCHED_on_a_whole_cycle_refusal(pack, tmp_path,
                                                                 label, make):
    """Zero spool is part of the §5 row, and a recording double is the only way
    to prove a call that did not happen."""
    spool = RecordingSpool(tmp_path / "spool")
    result = arming_pass(pack, tmp_path, spool=spool, unspooled_ok=False,
                         **make(pack, tmp_path))
    assert state_of(result) == label
    assert spool.calls == [], spool.calls
    assert list((tmp_path / "spool").rglob("*.json")) == []


def test_LIV2_the_unreachable_refusal_is_NAMED_rather_than_silently_skipped(census):
    """Which CYCLE_REFUSALS this suite could not construct, stated out loud."""
    covered = {state_of(census[label]) for label in REFUSAL_LABELS}
    covered.add(state_of(census["no_pack"]))
    assert set(le.CYCLE_REFUSALS) - covered == {"failed"}


# ---------------------------------------------------------------------------
# LIV-3 — a missed cadence is NAMED
# ---------------------------------------------------------------------------

def test_LIV3_a_twenty_minute_gap_is_counted_in_intervals_and_NAMED(pack, tmp_path):
    """Four intervals should have elapsed; three of them produced no pass.

    The gap is expressed in INTERVALS rather than minutes because that is the
    unit the cadence is defined in — a receipt saying "20 minutes" would need
    the reader to know the interval width to know whether that was a fault.
    """
    ledger = ll.LiveEpisodeLedger(tmp_path)
    first = arming_pass(pack, tmp_path, ledger=ledger)
    assert first.health["pass"]["seq"] == 1
    assert first.health["pass"]["prev_gap_intervals"] is None

    later = session_instant(32)
    second = arming_pass(pack, tmp_path, now=later, ledger=ledger,
                         quotes=quote_book(pack, ts=session_instant(30)))
    assert second.health["pass"]["seq"] == 2
    assert second.health["pass"]["prev_gap_intervals"] == 3
    assert "cadence_gap:3" in second.health["reasons"]


def test_LIV3_CONTROL_consecutive_five_minute_passes_report_no_gap(pack, tmp_path):
    """Without this the test above would pass on a receipt that called every
    pass a gap."""
    ledger = ll.LiveEpisodeLedger(tmp_path)
    arming_pass(pack, tmp_path, ledger=ledger)
    second = arming_pass(pack, tmp_path, now=session_instant(17), ledger=ledger,
                         quotes=quote_book(pack, ts=session_instant(15)))
    assert second.health["pass"]["prev_gap_intervals"] == 0
    assert [r for r in second.health["reasons"] if r.startswith("cadence_gap")] == []


def test_LIV3_the_cadence_gap_is_excluded_from_the_STABLE_content(pack, tmp_path):
    """A gap is a fact about the LANE, not about the reading.

    PIT-W4-9 compares two same-cycle runs byte for byte; leaving the cadence
    reason in would make a re-run after a pause look like changed content.
    """
    ledger = ll.LiveEpisodeLedger(tmp_path)
    first = arming_pass(pack, tmp_path, ledger=ledger)
    second = arming_pass(pack, tmp_path, now=session_instant(32), ledger=ledger,
                         quotes=quote_book(pack, ts=session_instant(30)))
    assert "cadence_gap:3" in second.health["reasons"]
    assert "cadence_gap" not in le.stable_content(second.payload)
    assert "cadence_gap" not in le.stable_content(first.payload)


# ---------------------------------------------------------------------------
# LIV-4 — the receipt is design §6's own shape
# ---------------------------------------------------------------------------

def missing_keys(spec, got, prefix: str = "health") -> list[str]:
    """Required paths absent from ``got``.  Extra keys are lawful."""
    out: list[str] = []
    for key, child in spec.items():
        path = f"{prefix}.{key}"
        if not isinstance(got, dict) or key not in got:
            out.append(path)
            continue
        if isinstance(child, dict):
            out.extend(missing_keys(child, got[key], path))
    return out


def test_LIV4_an_evaluating_pass_publishes_the_design_S6_shape(census):
    assert missing_keys(DESIGN_S6_HEALTH, census["live"].health) == []


@pytest.mark.parametrize("label", REFUSAL_LABELS + ("no_pack", "spool_failed"))
def test_LIV4_a_refusal_publishes_the_SAME_shape(census, label):
    """A refusal receipt is not a shorter receipt.

    An operator reading a refused cycle needs the same fields in the same
    places, or the artifact stops being machine-readable exactly when it matters.
    """
    assert missing_keys(DESIGN_S6_HEALTH, census[label].health) == []


def test_LIV4_the_health_block_on_the_payload_is_the_one_returned(census):
    for label, result in census.items():
        assert result.payload["health"] == result.health, label


def test_LIV4_CONTROL_the_shape_checker_reports_a_removed_key(census):
    """A structure checker that never fires proves nothing."""
    mangled = json.loads(json.dumps(census["live"].health, default=str))
    mangled["inputs"]["quotes"].pop("coverage")
    mangled.pop("content")
    assert sorted(missing_keys(DESIGN_S6_HEALTH, mangled)) == [
        "health.content", "health.inputs.quotes.coverage"]


def test_LIV4_the_receipt_enumerates_every_per_name_refusal(census):
    """``dark`` carries one counter per enumerated refusal, always — a reason
    that only appears when it fires cannot be read as a zero."""
    assert set(census["live"].health["dark"]) == set(le.NAME_REFUSALS)
    assert set(census["stale_quotes"].health["dark"]) == set(le.NAME_REFUSALS)


# ---------------------------------------------------------------------------
# LIV-5 — the content-advance signal actually advances
# ---------------------------------------------------------------------------

def test_LIV5_the_ledger_hash_MOVES_when_a_transition_commits(pack, tmp_path):
    """Read from two RECEIPTS rather than from the module's private helper.

    The "before" hash is taken from a killed pass over the same fresh ledger —
    a receipt an operator could actually read — so the comparison is between two
    published values rather than between a published one and a test-computed one.
    """
    ledger = ll.LiveEpisodeLedger(tmp_path)
    stood_down = arming_pass(pack, tmp_path, ledger=ledger, env={le.KILL_ENV: "1"})
    before = stood_down.health["content"]["ledger_hash"]

    result = arming_pass(pack, tmp_path, ledger=ledger)
    assert not result.delta.empty, "the fixture committed nothing to detect"
    after = result.health["content"]["ledger_hash"]
    assert before is not None and after is not None
    assert after != before
    assert result.health["content"]["events_total"] >= 1
    assert result.health["content"]["last_transition_at"]


def test_LIV5_CONTROL_a_rerun_that_admits_nothing_leaves_the_hash_ALONE(pack, tmp_path):
    """This is the half that makes it a signal.

    A hash that moved on every pass would say "the process ran", which the pass
    stamp already says.  What it has to say is "the STATE changed", and the only
    way to prove that is a re-run whose delta is empty and whose hash holds.
    """
    ledger = ll.LiveEpisodeLedger(tmp_path)
    first = arming_pass(pack, tmp_path, ledger=ledger)
    second = arming_pass(pack, tmp_path, ledger=ledger)
    assert second.delta.empty
    assert second.health["content"]["ledger_hash"] == \
        first.health["content"]["ledger_hash"]
    assert le.state_map(second.payload) == le.state_map(first.payload)


def test_LIV5_process_input_and_content_are_THREE_separate_readings(pack, tmp_path):
    """Green process != current content, answered by three independent stamps.

    Any two of them can advance while the third is frozen: a lane can keep
    passing over a frozen quote file, a quote file can keep moving while the
    ledger never changes, and a ledger can be current while the lane has stopped.
    """
    ledger = ll.LiveEpisodeLedger(tmp_path)
    result = arming_pass(pack, tmp_path, ledger=ledger)
    health = result.health
    assert health["pass"]["at"] == result.payload["asof"]
    assert health["inputs"]["quotes"]["asof"] == session_instant(2).isoformat()
    assert health["inputs"]["quotes"]["age_s"] == pytest.approx(600.0, abs=1.0)
    assert health["content"]["ledger_hash"]
    assert len({health["pass"]["at"], health["inputs"]["quotes"]["asof"],
                health["content"]["ledger_hash"]}) == 3


# ---------------------------------------------------------------------------
# LIV-6 — the killed payload is honest
# ---------------------------------------------------------------------------

def test_LIV6_a_killed_lane_still_publishes_a_complete_honest_artifact(census, pack):
    """Stood down must never read as "no names in the universe".

    A truncated or empty artifact is indistinguishable from a probe set that
    found nothing, and the difference is the whole reason the receipt exists.
    """
    payload = census["killed_env"].payload
    assert payload["schema"] == le.SCHEMA_LIVE_PAYLOAD
    assert payload["asof"]
    assert [row["ticker"] for row in payload["names"]] == sorted(pack.substrate)
    assert payload["pack"]["as_of"] == pack.as_of
    assert payload["pack"]["pack_hash"] == pack.pack_hash


def test_LIV6_the_authority_block_is_present_and_ALL_FALSE(census):
    """The live lane holds no authority of any kind, and says so on every
    artifact including the ones it publishes while stood down."""
    for label in ("killed_env", "live", "stale_pack"):
        authority = census[label].payload["authority"]
        assert authority, label
        assert set(authority.values()) == {False}, (label, authority)


def test_LIV6_a_killed_pass_exits_zero_and_spools_nothing(census):
    assert census["killed_env"].exit_code == 0
    assert census["killed_env"].spool_key is None
    assert census["killed_env"].committed is True


# ---------------------------------------------------------------------------
# LIV-7 — PIT-W4-20: the W5 firewall over EMITTED keys
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def emitted(pack, tmp_path_factory):
    """One committed pass, with its journal and spool object on DISK.

    Reading the artifacts back off disk rather than from the in-memory objects
    is the point: the firewall is a claim about what this lane PUBLISHES, and a
    key that only appears after serialisation would be invisible to an in-memory
    sweep.
    """
    state_dir = tmp_path_factory.mktemp("firewall")
    ledger = ll.LiveEpisodeLedger(state_dir)
    spool = ll.EventSpool(local_dir=state_dir / "spool")
    result = arming_pass(pack, state_dir, ledger=ledger, spool=spool)
    assert result.committed and result.spool_key
    ledger.save()
    journals = sorted((state_dir / "journal").rglob("*.json"))
    spooled = sorted((state_dir / "spool").rglob("*.json"))
    assert journals and len(spooled) == 1
    return {
        "pack_manifest": pack.manifest(),
        "journal": [json.loads(p.read_text(encoding="utf-8")) for p in journals],
        "ledger": ledger.to_dict(),
        "spool_object": json.loads(spooled[0].read_text(encoding="utf-8")),
        "payload": result.payload,
    }


@pytest.mark.parametrize("surface", ["pack_manifest", "journal", "ledger",
                                     "spool_object", "payload"])
def test_LIV7_no_emitted_key_anywhere_requires_forward_knowledge(emitted, surface):
    """A field that would need to know what happened AFTER an observation was
    knowable belongs to W5, and W4 must not be able to spell it."""
    assert le.forward_knowledge_keys(emitted[surface]) == []


def test_LIV7_MUTATION_CONTROL_the_sweep_finds_a_planted_forward_key(emitted):
    """Without this the five assertions above would pass on a sweep that had
    quietly stopped matching anything at all."""
    planted = {"names": [dict(emitted["payload"], forward_return_21d=0.1)]}
    assert le.forward_knowledge_keys(planted) == ["forward_return_21d"]
    assert le.forward_knowledge_keys({"a": [{"b": {"mfe_pct": 1}}]}) == ["mfe_pct"]
    assert le.forward_knowledge_keys({"hit_rate": 1, "grade": "A"}) == ["grade",
                                                                       "hit_rate"]


def test_LIV7_emitted_keys_actually_walks_the_whole_structure(emitted):
    """CONTROL on the walker under the sweep: a walker that missed nested lists
    would make every assertion above vacuous."""
    keys = le.emitted_keys(emitted["payload"])
    assert {"schema", "asof", "names", "health", "ticker", "state", "reasons",
            "ledger_hash"} <= keys
    assert le.emitted_keys({"a": [{"b": [{"c": 1}]}]}) == {"a", "b", "c"}


def test_LIV7_the_exemption_list_is_non_empty_and_its_split_is_PINNED():
    """An exemption is only honest while it exempts something.

    ``FIREWALL_EXEMPT_KEYS`` is subtracted from the sweep BY NAME, and its own
    docstring calls its entries "keys that MATCH a forbidden token and are
    nonetheless lawful".  Four of them do; five match no token at all and so
    exempt nothing — inert rather than wrong, since the sweep would never have
    flagged them.  The split is stated here rather than quietly tolerated, and
    it is pinned in BOTH directions: a new exemption that matches nothing is
    dead weight, and an inert one that becomes load-bearing means a token was
    widened underneath it — which is exactly the change that would silence a
    true positive beside it.
    """
    assert le.FIREWALL_EXEMPT_KEYS, "an empty exemption list hides nothing"
    matching, inert = set(), set()
    for key in le.FIREWALL_EXEMPT_KEYS:
        low = key.lower()
        (matching if any(t in low for t in le.FORBIDDEN_KEY_TOKENS)
         else inert).add(key)
    assert matching == LOAD_BEARING_EXEMPTIONS, (
        f"the set of exemptions that actually suppress a token match moved to "
        f"{sorted(matching)}; a NEW one means the firewall now skips a key it "
        f"used to refuse — say why here before widening the pin")
    assert inert == INERT_EXEMPTIONS, (
        f"the inert exemptions moved to {sorted(inert)}; one leaving this set "
        f"means a FORBIDDEN token was widened to cover it, which would also "
        f"have widened it over the true positives beside it")
    assert matching | inert == set(le.FIREWALL_EXEMPT_KEYS)
    for key, why in le.FIREWALL_EXEMPT_KEYS.items():
        assert why.strip(), f"{key} is exempted with no stated reason"


def test_LIV7_a_load_bearing_exemption_really_would_be_flagged_without_it():
    """CONTROL: the four matching entries are doing work.

    Each is a structurally-constant field — an all-false authority declaration
    or a §13 slot the ledger refuses to fill — so the sweep must skip it by name
    and would otherwise refuse a lawful artifact.
    """
    for key in sorted(LOAD_BEARING_EXEMPTIONS):
        assert le.forward_knowledge_keys({key: None}) == []
        assert le.forward_knowledge_keys({f"{key}_x": None}) == [f"{key}_x"], key


# ---------------------------------------------------------------------------
# LIV-8 — RESOLVED-at-H is calendar arithmetic only
# ---------------------------------------------------------------------------

def _price_reads(source: str) -> list[str]:
    """Attribute and string-subscript names that would read a price."""
    tree = ast.parse(source)
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in PRICE_ACCESSORS:
            found.add(node.attr)
        elif isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant):
            if node.slice.value in PRICE_ACCESSORS:
                found.add(str(node.slice.value))
    return sorted(found)


def test_LIV8_the_resolve_path_reads_NO_PRICE_at_AST_level():
    """The structural half, and the one this suite leads with.

    A behavioural counterfactual can only show that the prices it happened to
    vary made no difference; the AST statement is about the whole function —
    there is no expression in it that could read a price at all. Both are
    asserted (the behavioural one below), because the AST scan alone would miss
    a price arriving through a helper, and the behavioural one alone would miss
    a price that is read but not yet used.
    """
    assert _price_reads(inspect.getsource(ll.apply_session_clocks)) == []


def test_LIV8_CONTROL_the_price_scanner_catches_a_planted_read():
    """A scanner that never fires proves nothing."""
    assert _price_reads("def f(e):\n    return e.close\n") == ["close"]
    assert _price_reads("def f(e):\n    return e['sampled_close']\n") == \
        ["sampled_close"]
    assert _price_reads("def f(e):\n    return e.bar.high - e.bar.low\n") == \
        ["high", "low"]


def test_LIV8_a_DIFFERENT_price_produces_an_IDENTICAL_resolved_record(tmp_path):
    """The behavioural half, through the ledger's own save/load surface.

    Two ledgers identical except for the candidate's recorded price resolve to
    byte-identical transitions — which is what "no outcome is attached" has to
    mean operationally, not merely in the docstring.
    """
    from tests.test_entry_radar_w4_ledger import ledger_with_candidate

    baseline, _run, _delta = ledger_with_candidate(tmp_path)
    episode = baseline.episodes[0]
    resolving = ll.session_at_offset(episode.market_session,
                                     ll.RESOLVE_HORIZON_SESSIONS)
    assert resolving is not None

    saved = baseline.save()
    other_dir = tmp_path / "other"
    other_dir.mkdir()
    body = json.loads(saved.read_text(encoding="utf-8"))
    body["episodes"][0]["price_at_signal"] = {"sampled_close": 999.99,
                                              "basis": "adjusted"}
    (other_dir / saved.name).write_text(json.dumps(body), encoding="utf-8")
    repriced = ll.LiveEpisodeLedger.load(other_dir)
    assert repriced.episodes[0].price_at_signal != episode.price_at_signal

    first = ll.apply_session_clocks(baseline, as_of_session=resolving.isoformat())
    second = ll.apply_session_clocks(repriced, as_of_session=resolving.isoformat())
    assert first.transitions, "the fixture resolved nothing"
    assert json.dumps(first.transitions, sort_keys=True) == \
        json.dumps(second.transitions, sort_keys=True)
    assert first.transitions[0]["at"] == ll.session_close_instant(resolving)
    assert first.transitions[0]["to_state"] == "RESOLVED"


# ---------------------------------------------------------------------------
# LIV-9 — the sentinel reads a field the payload emits
# ---------------------------------------------------------------------------

def sentinel_entry() -> dict | None:
    for surface in FS.SURFACES:
        if surface.get("id") == "entry_radar_live":
            return dict(surface)
    return None


def test_LIV9_the_live_lane_is_REGISTERED_with_the_freshness_sentinel():
    """The design's mandated positive liveness registration.

    Silence has to page through the sentinel plane that already exists rather
    than through a watchdog of its own — an unregistered lane is one whose only
    liveness evidence is the artifact nobody is reading.
    """
    entry = sentinel_entry()
    if entry is None:
        pytest.skip("scripts/freshness_sentinel.py SURFACES carries no entry with "
                    "id 'entry_radar_live' — the W4 registration has not landed "
                    "yet; this test activates the moment it does")
    assert entry["kind"] == "live_file"
    assert entry["path"] == "/live/entry_radar.json"
    assert entry["absent_ok"] is True, (
        "the artifact does not exist until the operator arms the lane; without "
        "the exemption a pre-activation absence pages as blindness")


def test_LIV9_the_sentinel_reads_a_field_the_payload_ACTUALLY_EMITS(census):
    """The whole point of the registration test: the field has to exist.

    A sentinel pointed at a key the artifact never publishes reads as
    INDETERMINATE forever — a lane that looks watched and is not.
    """
    entry = sentinel_entry()
    if entry is None:
        pytest.skip("no 'entry_radar_live' SURFACES entry to check the payload "
                    "against")
    field = entry["asof_field"]
    for label in ("live", "killed_env", "stale_pack"):
        payload = census[label].payload
        assert field in payload, (label, field, sorted(payload))
        assert payload[field], f"{label}: {field} is present but empty"
    assert entry["asof_max_sessions_behind"] >= 1


# ---------------------------------------------------------------------------
# W4R — round-1 adversarial review regressions (health receipt half)
# ---------------------------------------------------------------------------

def test_W4R_H1_a_pass_in_which_EVERY_reading_is_null_is_not_live(pack, tmp_path):
    """Measured before the fix, probe set ["STALE"], quotes fresh, basis clean:

        name.state = evaluated   reasons = ('reading_stale',)
        HEALTH.state = live      HEALTH.reasons = []   HEALTH.dark = all zeroes

    Zero measurements taken, ``condition_met`` None everywhere, and the receipt
    said ``live`` with nothing to report.  ``health.dark`` cannot cover it by
    construction — it counts DARK names, and a null reading is not a dark name —
    which is §0's "``stale`` != non-fire" failing at the one surface an operator
    reads.
    """
    result = arming_pass(pack, tmp_path, tickers=["STALE"],
                         quotes=quote_book(pack, ts=session_instant(2),
                                           tickers=["STALE"]))
    stale = result.names[0]
    assert stale.state == "evaluated" and "reading_stale" in stale.reasons
    assert state_of(result) == "degraded"
    assert "reading_null:1/1" in result.health["reasons"]
    assert result.health["null_readings"]["reading_stale"] == 1
    assert result.health["null_readings"]["reading_unavailable"] == 0


def test_W4R_H1_CONTROL_one_real_measurement_is_enough_for_live(pack, tmp_path):
    """The floor is ONE non-null reading, not zero nulls: a probe set always
    carries names whose history is stale, and reddening the whole receipt for
    them would make the state useless."""
    result = arming_pass(pack, tmp_path)
    assert state_of(result) == "live" and result.health["reasons"] == []
    assert result.health["null_readings"]["reading_stale"] >= 1, \
        "the corpus has no null reading at all — the control proves nothing"


def test_W4R_H1_the_null_counters_are_always_present(census):
    """A counter that only appears when it fires cannot be read as a zero."""
    for label, result in census.items():
        block = result.health["null_readings"]
        assert set(block) >= {"reading_unavailable", "reading_stale", "suppressed"}, \
            (label, block)


# --- M6: the heartbeat is written on every terminal path --------------------

def test_W4R_M6_three_stale_pack_refusals_ADVANCE_the_pass_counter(pack, tmp_path):
    """Measured before the fix — one good pass, then three ``stale_pack``
    refusals::

        ('stale_pack', 2, '2026-08-17T13:50:00Z')
        ('stale_pack', 2, '2026-08-17T13:50:00Z')
        ('stale_pack', 2, '2026-08-17T13:50:00Z')

    ``seq`` was an EVALUATION counter wearing a pass counter's name, so "ran 78
    times and refused" and "did not run at all" left the identical heartbeat
    trace — the failure signature this estate has already been burned by.
    """
    good = arming_pass(pack, tmp_path)
    assert state_of(good) == "live"

    stale_now = datetime(2026, 8, 18, 14, 2, tzinfo=timezone.utc)
    seqs, states = [], []
    for minute in range(3):
        when = stale_now + timedelta(minutes=5 * minute)
        result = arming_pass(pack, tmp_path, now=when,
                             quotes=quote_book(pack, ts=when - timedelta(minutes=2)))
        assert state_of(result) == "stale_pack"
        seqs.append(result.health["pass"]["seq"])
        states.append(json.loads((tmp_path / "heartbeat.json")
                                 .read_text(encoding="utf-8")))

    assert seqs == [2, 3, 4], seqs
    assert [row["state"] for row in states] == ["stale_pack"] * 3
    assert [row["seq"] for row in states] == [2, 3, 4]
    assert {row["evaluated_seq"] for row in states} == {1}, \
        "a refusal must not advance the EVALUATION counter"


def test_W4R_M6_the_cadence_gap_still_reads_off_the_refusal_heartbeats(pack, tmp_path):
    """Writing the heartbeat more often must not blind the gap detector."""
    arming_pass(pack, tmp_path)
    late = arming_pass(pack, tmp_path, now=session_instant(32),
                       quotes=quote_book(pack, ts=session_instant(30)))
    assert late.health["pass"]["prev_gap_intervals"] == 3
    assert any(r.startswith("cadence_gap:") for r in late.health["reasons"])


# --- M7: a dry run touches nothing ------------------------------------------

def test_W4R_M7_a_dry_run_leaves_the_state_dir_UNTOUCHED(pack, tmp_path):
    """``--dry-run``'s help text says "spool nothing, commit nothing, publish
    nothing", and the script only gated the SPOOL.

    Measured with the same wiring ``run(dry_run=True)`` used: the state dir went
    from ``[]`` to ``['heartbeat.json', 'journal']`` — so an operator running
    ``python -m scripts.entry_radar_live --dry-run`` on the VPS (no
    ``--state-dir``, the natural invocation) appended a point to the LIVE journal
    and bumped the heartbeat, corrupting the next real pass's
    ``prev_gap_intervals`` and ``seq``.
    """
    assert list(tmp_path.iterdir()) == []
    result = arming_pass(pack, tmp_path, dry_run=True)
    assert result.names, "the dry run evaluated nothing at all"
    assert list(tmp_path.iterdir()) == [], sorted(p.name for p in tmp_path.iterdir())


def test_W4R_M7_CONTROL_a_wet_pass_writes_both(pack, tmp_path):
    arming_pass(pack, tmp_path)
    written = sorted(p.name for p in tmp_path.iterdir())
    assert "heartbeat.json" in written and "journal" in written


# --- C2: the failed receipt is a real, shape-identical refusal ---------------

def test_W4R_C2_the_failed_receipt_is_reachable_and_shaped_like_every_refusal(pack):
    """``failed``'s reachability case (see the producer test above)."""
    now = session_instant(12)
    payload, health = le.failure_payload(
        now=now, pack=pack, error=RuntimeError("injected: the pass raised"))
    assert health["state"] == "failed"
    assert missing_keys(DESIGN_S6_HEALTH, health) == []
    assert health["reasons"] == ["evaluator_failed:RuntimeError: injected: the pass "
                                 "raised"]
    assert payload["health"] == health
    assert {row["state"] for row in payload["names"]} == {"unavailable"}
    assert len(payload["names"]) == len(pack.substrate)
    assert payload["transitions"] == [] and payload["events"] == []
    assert le.forward_knowledge_keys(payload) == []


def test_W4R_C2_the_failed_receipt_writes_NO_heartbeat_of_its_own(pack, tmp_path):
    """It describes a pass that died; claiming a heartbeat for it would say the
    lane is alive at the instant it is not."""
    le.failure_payload(now=session_instant(12), pack=pack, state_dir=tmp_path,
                       error=RuntimeError("boom"))
    assert list(tmp_path.iterdir()) == []


# --- C2, the SCRIPT half: the entrypoint is what turned a raise into exit 0 ---
#
# The two tests above exercise ``failure_payload`` in isolation, which cannot see
# whether anything PUBLISHES it or what the process returns — and "returned 0
# with nothing written" was the whole defect.  These drive
# ``scripts.entry_radar_live.run`` and read the file off disk.

def _script_env(monkeypatch, tmp_path):
    """Hermetic wiring for one ``run()`` call: no VPS paths, no quote files."""
    import scripts.entry_radar_live as ERL

    live = tmp_path / "live"
    live.mkdir()
    monkeypatch.setattr(ERL, "LOCAL_QUOTE_PATHS", ())
    monkeypatch.setattr(ERL, "_VPS_STATE_DIR", tmp_path / "no-vps" / "entry_radar")
    monkeypatch.setattr(ERL, "_VPS_LIVE_DIR", tmp_path / "no-vps" / "live")
    monkeypatch.delenv(ERL._NO_PUBLISH_ENV, raising=False)
    return ERL, live


def test_W4R_C2_the_SCRIPT_publishes_the_failed_receipt_and_exits_6(
        pack, tmp_path, monkeypatch, capsys):
    """Measured before the fix: the top-level ``except Exception`` returned 0.

    The served artifact then kept its previous body AND its previous
    ``health.pass.at`` — stale but whole — so the only alarm was the freshness
    sentinel, which §3b pins at SESSION grain.  A persistent per-name defect
    therefore burned a full session, green.
    """
    ERL, live = _script_env(monkeypatch, tmp_path)
    # A REAL pack, so the receipt is the one an operator would actually be
    # served: every probe name present and every one of them unavailable.
    monkeypatch.setattr(ERL.LP, "load_pack", lambda state: pack)
    monkeypatch.setattr(ERL.LE, "run_pass",
                        lambda **kw: (_ for _ in ()).throw(
                            RuntimeError("injected: the pass frame raised")))

    code = ERL.run(ROOT, now=session_instant(12), state_override=str(tmp_path / "st"),
                   live_override=str(live))

    assert code == 6, "a raised pass must not exit 0"
    published = live / ERL.PAYLOAD_NAME
    assert published.is_file(), "the failed receipt was never published"
    body = json.loads(published.read_text(encoding="utf-8"))
    assert body["health"]["state"] == "failed"
    assert body["health"]["reasons"] == [
        "evaluator_failed:RuntimeError: injected: the pass frame raised"]
    assert body["transitions"] == [] and body["events"] == []
    assert {row["state"] for row in body["names"]} == {"unavailable"}
    # The annotation is line-start and bare-printed, or Actions drops it.
    err = [ln for ln in capsys.readouterr().out.splitlines() if "::error" in ln]
    assert err and err[0].startswith("::error title=entry-radar-live::")


def test_W4R_C2_CONTROL_a_clean_script_pass_publishes_and_does_NOT_exit_6(
        tmp_path, monkeypatch):
    """Without this the test above passes on a script that ALWAYS exits 6."""
    ERL, live = _script_env(monkeypatch, tmp_path)
    code = ERL.run(ROOT, now=session_instant(12), state_override=str(tmp_path / "st"),
                   live_override=str(live))
    assert code != 6
    body = json.loads((live / ERL.PAYLOAD_NAME).read_text(encoding="utf-8"))
    assert body["health"]["state"] != "failed"


def test_W4R_LOW_a_NO_PUBLISH_rehearsal_exits_0_and_not_3(tmp_path, monkeypatch):
    """A DOCUMENTED refusal is not a sink failure.

    ``ENTRY_RADAR_NO_PUBLISH`` makes ``publish`` refuse on purpose, so the old
    ``return 3`` ("the pass produced no output at all") reddened every rehearsal
    pass with the code that means the sink is broken — and a code that fires on
    purpose stops meaning anything when it fires for real.  3 must stay reachable
    for the real case, which is the second half below.
    """
    ERL, live = _script_env(monkeypatch, tmp_path)
    monkeypatch.setenv(ERL._NO_PUBLISH_ENV, "1")
    code = ERL.run(ROOT, now=session_instant(12), state_override=str(tmp_path / "st"),
                   live_override=str(live))
    assert code == 0
    assert not (live / ERL.PAYLOAD_NAME).exists(), "NO_PUBLISH still wrote the payload"

    # CONTROL: a publish that fails for a REAL reason still returns 3.
    monkeypatch.delenv(ERL._NO_PUBLISH_ENV)
    monkeypatch.setattr(ERL, "publish", lambda path, payload: False)
    assert ERL.run(ROOT, now=session_instant(12),
                   state_override=str(tmp_path / "st2"),
                   live_override=str(live)) == 3


def test_W4R_LOW_the_printed_receipt_NAMES_the_durable_write_set(
        tmp_path, monkeypatch, capsys):
    """``DURABLE_WRITES = ()`` was read by nothing, unlike both sibling scripts.

    An empty-by-design list nobody ever sees is a claim; printing it is what
    makes the ledger-law guard checkable from a run log.
    """
    ERL, live = _script_env(monkeypatch, tmp_path)
    ERL.run(ROOT, now=session_instant(12), state_override=str(tmp_path / "st"),
            live_override=str(live))
    receipt = [ln for ln in capsys.readouterr().out.splitlines()
               if ln.startswith("entry-radar-live pass=")]
    assert receipt, "the pass printed no receipt line at all"
    assert "durable_writes=[]" in receipt[0]
    assert ERL.DURABLE_WRITES == ()
