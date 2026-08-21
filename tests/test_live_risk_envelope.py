"""Acceptance suite for the Grey Deer LIVE provisional risk envelope (GD-3).

Every test here pins one FROZEN constraint from the GD-3 build commission
(`research/grey_deer/commissions/GD-3_LIVE_PROVISIONAL_ENVELOPE_COMMISSION_2026-08-20.md`)
as restated in the GD-3 build packet §FROZEN SPEC. `tests/test_risk_envelope.py`
(GD-2) is the settled-lane sibling and is untouched by this file; the two share the
same pure composer and the same source adapters — GD-3 never forks the state logic.
"""

from __future__ import annotations

import ast
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

import scripts.build_live_risk_envelope as blre
from engine.risk_envelope import STAGE_VOCABULARY, compose_envelope
from scripts.build_risk_envelope import (
    _leadership_crack_read,
    _market_state_read,
    _risk_radar_read,
    build_sources,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_GD1_FIXTURE = _REPO_ROOT / "tests" / "fixtures" / "risk_envelope" / "gd1_dual_read_2026-08-18.json"
_LIVE_MODULE = _REPO_ROOT / "scripts" / "build_live_risk_envelope.py"
_THEME_CSS = _REPO_ROOT / "templates" / "theme.css"

# The GD1 fixture's settled bundle_id, composed through the SAME code path this
# file's adapter refactor touches — pinned so a change to the refactor's default
# behaviour (stale_override=None) is caught byte-for-byte, not just semantically.
_GD1_PINNED_BUNDLE_ID = "a423374ffe40facb"


@pytest.fixture(scope="module")
def gd1():
    return json.loads(_GD1_FIXTURE.read_text(encoding="utf-8"))


def _write_root(tmp_path, *, risk_state=None, leadership=None, settled=None,
                 prev_envelope=None):
    (tmp_path / "site" / "live").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data" / "leadership_crack").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data" / "risk_envelope").mkdir(parents=True, exist_ok=True)
    if risk_state is not None:
        (tmp_path / "site" / "live" / "risk_state.json").write_text(json.dumps(risk_state))
    if leadership is not None:
        (tmp_path / "data" / "leadership_crack" / "latest.json").write_text(json.dumps(leadership))
    if settled is not None:
        (tmp_path / "data" / "risk_envelope" / "latest.json").write_text(json.dumps(settled))
    if prev_envelope is not None:
        (tmp_path / "site" / "live" / "risk_envelope.json").write_text(json.dumps(prev_envelope))
    return tmp_path


def _risk_state(built, *, live_active=True, verdict="RISK_OFF", score=40,
                 radar_state="warning", radar_score=61.0, display_verdict="RISK_ON"):
    """A minimal risk_state.json — the RAW `live` block is what this file's builder
    may read; `display` deliberately disagrees so tests can prove it is never read
    (item 11)."""
    return {
        "schema": "risk_state.v1",
        "built": built,
        "session": {"region": "us", "open": True, "local_time": "11:31 EDT"},
        "live_active": live_active,
        "realtime": True,
        "delayed_min": 15,
        "live": {
            "verdict": verdict, "score": score, "raw_score": score,
            "label_en": verdict.title(), "label_zh": "x",
            "radar": {"state": radar_state, "top_score": radar_score,
                      "label_en": "x", "label_zh": "y"},
        },
        "display": {"verdict": display_verdict, "score": 5, "label_en": "SHOULD NEVER BE READ"},
    }


def _risk_state_empty_live(built, *, live_active=True):
    """build_risk_state.py:233-239's own recompute-exception path: the fast lane
    RAN (live_active stays True, `built` is a fresh timestamp) but the recompute
    inside it raised, so it ships `"live": {}` — content-empty, not artifact-
    missing. Adjudication #1's regression fixture."""
    return {
        "schema": "risk_state.v1",
        "built": built,
        "session": {"region": "us", "open": True, "local_time": "11:31 EDT"},
        "live_active": live_active,
        "realtime": True,
        "delayed_min": 15,
        "live": {},
        "display": {"verdict": "RISK_ON", "score": 81, "label_en": "SHOULD NEVER BE READ"},
    }


def _leadership(asof, state="BROKEN"):
    return {"schema": "leadership_crack.v1", "asof": asof, "state": state,
            "state_since": "2026-07-07", "cohort_role": "x", "n_fresh": 42,
            "n_total": 42, "high_window_sessions": 63}


def _settled(session, bundle_id="fd9ccdbe47f7f008", stage="FRAGILE"):
    return {"source_session": session, "bundle_id": bundle_id,
            "hazard_summary": {"stage": stage}}


# ══ item 1 — settled fixture compose output byte-identical after the adapter edit ══

class TestAdapterRefactorIsANoOp:

    def test_default_stale_override_matches_the_original_expression(self, gd1):
        """Omitting `stale_override` (the settled lane's own call sites) must be
        byte-identical to passing `stale_override=None` explicitly — the refactor's
        entire contract."""
        ms, session = gd1["market_state"], gd1["session"]
        lc = gd1["leadership_crack"]
        assert _market_state_read(ms, session) == _market_state_read(ms, session, stale_override=None)
        assert _leadership_crack_read(lc, session) == _leadership_crack_read(lc, session, stale_override=None)
        assert _risk_radar_read(ms.get("radar"), session, ms.get("asof")) == _risk_radar_read(
            ms.get("radar"), session, ms.get("asof"), stale_override=None
        )

    def test_gd1_settled_bundle_id_is_unchanged_by_the_refactor(self, gd1):
        sources = build_sources(gd1["market_state"], gd1["leadership_crack"], gd1["session"])
        env = compose_envelope(
            sources=sources, market="US", source_session=gd1["session"],
            observed_at="2026-08-19T00:00:00Z", produced_at="2026-08-19T00:00:00Z",
            as_of=gd1["session"], revision="settled",
        )
        assert env["bundle_id"] == _GD1_PINNED_BUNDLE_ID


# ══ item 2/3 — same adapters, no state->stage mapping, no ceiling promotion ══════

class TestSameAdaptersNoNewMapping:

    def test_live_module_imports_the_settled_adapters(self):
        src = _LIVE_MODULE.read_text(encoding="utf-8")
        tree = ast.parse(src)
        imported_from_settled = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "scripts.build_risk_envelope":
                imported_from_settled |= {a.name for a in node.names}
        assert {"_market_state_read", "_leadership_crack_read", "_risk_radar_read"} <= imported_from_settled

    def test_no_state_word_to_hazard_stage_dict_literal_in_the_live_module(self):
        """The live module may reshape docs, but it must never itself decide what a
        state word MEANS in hazard-stage terms — that mapping is the settled
        adapters' own (`_LEADERSHIP_STAGE` / `_RADAR_STAGE`), imported and reused."""
        src = _LIVE_MODULE.read_text(encoding="utf-8")
        tree = ast.parse(src)
        offences = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                keys_are_strings = all(isinstance(k, ast.Constant) and isinstance(k.value, str)
                                       for k in node.keys if k is not None)
                if not keys_are_strings:
                    continue
                values = [v.value for v in node.values
                         if isinstance(v, ast.Constant) and isinstance(v.value, str)]
                if any(v in STAGE_VOCABULARY for v in values):
                    offences.append(f"line {node.lineno}: dict literal maps into {STAGE_VOCABULARY}")
        assert not offences, offences

    def test_source_identity_matches_settled_lane_for_identical_inputs(self, gd1):
        """Feeding the live builder the SAME semantic content the settled fixture
        carries must produce SourceReads whose (source_id, role, required,
        stage_ceiling) are identical to the settled lane's — no promotion, no role
        reassignment, no re-declared requiredness anywhere in the live path."""
        settled_sources = build_sources(gd1["market_state"], gd1["leadership_crack"], gd1["session"])
        ms = gd1["market_state"]
        risk_state_doc = _risk_state(
            "2026-08-18 20:00:00 UTC", verdict=ms["verdict"], score=ms["score"],
            radar_state=ms["radar"]["state"], radar_score=ms["radar"]["top_score"],
        )
        live_sources = blre.build_live_sources(
            risk_state_doc=risk_state_doc, leadership_doc=gd1["leadership_crack"],
            settled_source_session=gd1["session"], live_session=gd1["session"],
            market_usable=True, now=datetime(2026, 8, 18, 20, 1, tzinfo=timezone.utc),
        )

        def identity(reads):
            return {s.source_id: (s.role, s.required, s.stage_ceiling) for s in reads}

        assert identity(live_sources) == identity(settled_sources)

    def test_no_stage_ceiling_is_ever_set_in_the_live_module(self):
        """item 3 — no promotion: the live module must never itself pass
        `stage_ceiling=` to a SourceRead/adapter call (the only lawful ceiling is
        whatever the shared, imported adapter already assigns)."""
        src = _LIVE_MODULE.read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.keyword) and node.arg == "stage_ceiling":
                pytest.fail(f"live module sets stage_ceiling at line {node.value.lineno}")


# ══ adjudication #1 (BLOCKER) — an empty "live" block must never launder as a
#    present-but-null FRESH/calm read; it must degrade like a missing source. ════

class TestEmptyLiveBlockIsNeverLaundered:

    def test_empty_live_block_is_not_present_never_fresh_calm(self, tmp_path):
        """build_risk_state.py's own recompute-exception path ships `live_active:
        true` with `"live": {}` when the fast-lane recompute itself raised. Before
        the fix, a doc dict with every value None still passed the settled
        adapters' truthiness check (`if not doc:`), so the source came back
        present=True and voted on staleness alone — laundering a genuine upstream
        failure into a calm/fresh-looking read. After the fix, market-state must
        come back NOT present, and the WRAPPER must never claim `live_active` off
        the presence of an empty block."""
        S = "2026-08-19"
        root = _write_root(
            tmp_path, risk_state=_risk_state_empty_live("2026-08-20 15:00:00 UTC"),
            leadership=_leadership(S, state="INTACT"), settled=_settled(S, stage="NONE"),
        )
        env = blre.build(root=root, now=datetime(2026, 8, 20, 15, 1, tzinfo=timezone.utc))
        measured = next(s for s in env["provenance"]["sources"]
                        if s["source_id"] == "market-state-latest")
        assert measured["coverage"] == "MISSING"
        assert env["measured_state"]["usable"] is False
        assert env["measured_state"]["verdict"] is None
        assert env["data_state"] != "FRESH", (
            "an empty live block must never be laundered into FRESH coverage"
        )

    def test_empty_radar_sub_block_is_also_not_present(self, tmp_path):
        """Same fix, the radar leg: a verdict-bearing `live` block whose nested
        `radar` sub-block is empty must not launder the radar source present
        either (it is optional, so this degrades coverage rather than nulling the
        stage — but it must never silently vote 'calm')."""
        risk_state = _risk_state("2026-08-20 15:00:00 UTC")
        risk_state["live"]["radar"] = {}
        root = _write_root(
            tmp_path, risk_state=risk_state,
            leadership=_leadership("2026-08-19"), settled=_settled("2026-08-19"),
        )
        env = blre.build(root=root, now=datetime(2026, 8, 20, 15, 1, tzinfo=timezone.utc))
        radar = next(s for s in env["provenance"]["sources"]
                    if s["source_id"] == "risk-radar-us")
        assert radar["coverage"] == "MISSING"
        assert radar["hazard_stage"] is None

    def test_stage_never_reads_none_from_a_laundered_empty_live_block(self, tmp_path):
        """The full reviewer scenario: live_active true + "live": {} while LC is
        ALSO unusable (a realistic joint failure) must null the stage — never
        report NONE (a positive 'we looked and found nothing') from evidence that
        was never actually looked at."""
        S = "2026-08-19"
        root = _write_root(
            tmp_path, risk_state=_risk_state_empty_live("2026-08-20 15:00:00 UTC"),
            leadership=_leadership("2026-08-11", state="INTACT"),  # stale vs S -> unusable
            settled=_settled(S, stage="FRAGILE"),
        )
        env = blre.build(root=root, now=datetime(2026, 8, 20, 15, 1, tzinfo=timezone.utc))
        assert env["hazard_summary"]["stage"] is None
        assert env["hazard_summary"]["stage"] != "NONE"


# ══ item 4 — the clock law: future-dated input is refused, never a calmer read ═══

class TestClockLaw:

    def test_is_future_helper(self):
        now = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)
        assert blre._is_future("2026-08-21", "2026-08-20", now) is True     # as_of > L
        assert blre._is_future("2026-08-19", "2026-08-20", now) is False    # as_of < L
        assert blre._is_future("2026-08-20", "2026-08-20", now) is False    # as_of == L
        assert blre._is_future(None, "2026-08-20", now) is False            # unknown clock

    def test_future_dated_calm_leadership_crack_is_refused_not_admitted_calm(self):
        """A future-dated LC claiming INTACT (calm) must never be let through — if it
        were, a corrupted/clock-skewed future row could paint a false all-clear.
        Required + unusable -> stage null (the null law), never NONE."""
        L, S = "2026-08-20", "2026-08-19"
        risk_state_doc = _risk_state("2026-08-20 15:00:00 UTC")
        lc = _leadership("2026-08-21", state="INTACT")  # future beyond L, calm state
        sources = blre.build_live_sources(
            risk_state_doc=risk_state_doc, leadership_doc=lc,
            settled_source_session=S, live_session=L, market_usable=True,
            now=datetime(2026, 8, 20, 15, 1, tzinfo=timezone.utc),
        )
        lc_read = next(s for s in sources if s.source_id == "leadership-crack-latest")
        assert lc_read.usable is False
        env = compose_envelope(
            sources=sources, market="US", source_session=L, as_of=L,
            observed_at="x", produced_at="x", revision="live_provisional",
        )
        assert env["hazard_summary"]["stage"] is None
        assert env["hazard_summary"]["stage_reason"] == "required_coverage_unavailable"
        assert env["hazard_summary"]["stage"] != "NONE"

    # ── adjudication #3: the ORIGINAL suite only covered the LC leg's future
    #    refusal; the MARKET leg's carrying artifact (risk_state.json's own
    #    `built` clock) needs the same law, PLUS it must never be half-refused —
    #    a future-dated `built` must not be used to derive L at all. ────────────

    def test_market_leg_future_dated_artifact_is_refused_and_never_used_as_l(self, tmp_path):
        """A risk_state.json whose OWN `built` clock sits >120s ahead of wall-clock
        (a corrupted/clock-skewed publish) must be refused WHOLESALE: never used to
        derive L, never republished as `clocks.event_time`, and the envelope must
        fall back to the settled anchor S rather than carrying the untrusted future
        date as its own session."""
        S = "2026-08-19"
        now = datetime(2026, 8, 20, 15, 0, tzinfo=timezone.utc)
        future_built = "2026-08-20 15:10:00 UTC"   # 10min ahead of `now`, past the 120s tolerance
        root = _write_root(
            tmp_path, risk_state=_risk_state(future_built),
            leadership=_leadership(S), settled=_settled(S),
        )
        env = blre.build(root=root, now=now)
        assert env["precedence"] == "settled"
        assert env["live_active"] is False
        assert env["stale_reason"] == "refused_future"
        assert env["source_session"] == S            # never the future date, never null
        assert env["as_of"] == S
        assert env["clocks"]["event_time"] is None    # untrusted clock is never republished
        assert env["live_transition"]["pending"] is None   # transition frozen/superseded
        measured = next(s for s in env["provenance"]["sources"]
                        if s["source_id"] == "market-state-latest")
        assert measured["coverage"] != "FRESH"


# ══ item 5 — LC judged against S, never NONE from missing/stale required evidence ═

class TestLeadershipCrackClockIsJudgedAgainstSettled:

    def test_as_of_equal_settled_session_is_usable(self):
        L, S = "2026-08-20", "2026-08-19"
        risk_state_doc = _risk_state("2026-08-20 15:00:00 UTC")
        lc = _leadership(S, state="INTACT")
        sources = blre.build_live_sources(
            risk_state_doc=risk_state_doc, leadership_doc=lc,
            settled_source_session=S, live_session=L, market_usable=True,
            now=datetime(2026, 8, 20, 15, 1, tzinfo=timezone.utc),
        )
        lc_read = next(s for s in sources if s.source_id == "leadership-crack-latest")
        assert lc_read.usable is True

    def test_as_of_older_than_settled_session_is_stale_and_degrades(self):
        L, S = "2026-08-20", "2026-08-19"
        risk_state_doc = _risk_state("2026-08-20 15:00:00 UTC")
        lc = _leadership("2026-08-17", state="BROKEN")   # older than S
        sources = blre.build_live_sources(
            risk_state_doc=risk_state_doc, leadership_doc=lc,
            settled_source_session=S, live_session=L, market_usable=True,
            now=datetime(2026, 8, 20, 15, 1, tzinfo=timezone.utc),
        )
        lc_read = next(s for s in sources if s.source_id == "leadership-crack-latest")
        assert lc_read.usable is False
        env = compose_envelope(
            sources=sources, market="US", source_session=L, as_of=L,
            observed_at="x", produced_at="x", revision="live_provisional",
        )
        assert env["data_state"] == "DEGRADED"   # market-state fresh, LC required-stale
        assert env["hazard_summary"]["stage"] is None
        assert env["hazard_summary"]["stage"] != "NONE"


# ══ item 6 — precedence triple + transition-clear on settle-catch-up ═════════════

class TestPrecedence:

    def test_l_greater_than_s_is_live(self, tmp_path):
        root = _write_root(
            tmp_path, risk_state=_risk_state("2026-08-20 15:00:00 UTC"),
            leadership=_leadership("2026-08-19"), settled=_settled("2026-08-19"),
        )
        env = blre.build(root=root, now=datetime(2026, 8, 20, 15, 1, tzinfo=timezone.utc))
        assert env["precedence"] == "live"
        assert env["live_active"] is True

    def test_l_less_than_s_is_settled_and_never_ticks(self, tmp_path):
        """A live observation older than the newest settled session can never
        outrank it: live_active false, stale_reason 'older than settled', and the
        dwell state must not tick toward the stale candidate."""
        # settled session is AHEAD of the live plane's own clock (an odd but
        # possible state — e.g. a live artifact frozen over a long weekend while a
        # correction re-settled a newer session).
        root = _write_root(
            tmp_path, risk_state=_risk_state("2026-08-17 15:00:00 UTC"),
            leadership=_leadership("2026-08-17"), settled=_settled("2026-08-19", stage="NONE"),
        )
        env = blre.build(root=root, now=datetime(2026, 8, 17, 15, 1, tzinfo=timezone.utc))
        assert env["precedence"] == "settled"
        assert env["live_active"] is False
        assert env["stale_reason"] == "older than settled"
        assert env["live_transition"]["pending"] is None
        assert env["live_transition"]["stable_stage"] == "NONE"   # supersede: settled stage wins

    def test_l_equal_s_clears_the_transition_on_settle_catch_up(self, tmp_path):
        """The transition-clear fixture pair: fire 1 while live (L > S) reads a
        de-escalation candidate (NONE) against a still-FRAGILE settled baseline, so
        a pending appears immediately without reaching the debounce window. Fire 2,
        after the nightly settles TODAY's session confirming that de-escalation
        (S advances to == L, new settled stage NONE), must supersede + CLEAR —
        stable_stage reinitializes straight to the new settled stage and pending
        drops, even though fire 1's pending never reached 3 ticks. (V0 has no
        source with a ceiling above FRAGILE — engine/risk_envelope.py's
        stage_ceiling default — so every reachable live candidate here is NONE or
        FRAGILE; an escalation-shaped pending is exercised in TestDwellLaw directly
        against the pure `_advance_transition` function instead.)"""
        risk_state_calm = _risk_state("2026-08-20 15:00:00 UTC", verdict="RISK_ON",
                                      radar_state="calm", radar_score=10.0)
        root = _write_root(
            tmp_path, risk_state=risk_state_calm,
            leadership=_leadership("2026-08-19", state="REPAIRING"),
            settled=_settled("2026-08-19", stage="FRAGILE"),
        )
        env1 = blre.build(root=root, now=datetime(2026, 8, 20, 15, 1, tzinfo=timezone.utc))
        assert env1["precedence"] == "live"
        assert env1["hazard_summary"]["stage"] == "NONE"
        assert env1["live_transition"]["stable_stage"] == "FRAGILE"   # not yet flipped
        assert env1["live_transition"]["pending"] == {"stage": "NONE", "ticks": 1, "needs": 3}
        blre.write(root=root, now=datetime(2026, 8, 20, 15, 1, tzinfo=timezone.utc))

        # nightly settles: the settled envelope's source_session advances to L,
        # confirming the de-escalation the live plane already saw.
        (root / "data" / "risk_envelope" / "latest.json").write_text(
            json.dumps(_settled("2026-08-20", bundle_id="newbundle00000001", stage="NONE"))
        )
        env2 = blre.build(root=root, now=datetime(2026, 8, 20, 15, 3, tzinfo=timezone.utc))
        assert env2["precedence"] == "settled"
        assert env2["stale_reason"] == "session already settled"
        assert env2["live_transition"]["pending"] is None
        assert env2["live_transition"]["stable_stage"] == "NONE"
        assert env2["overlays"]["settled_source_session"] == "2026-08-20"


# ══ item 7 — the dwell/debounce law (adjudication #2/#5 add live_active +
#    observed_built gating) ════════════════════════════════════════════════════

class TestDwellLaw:

    def test_pending_immediate_flip_at_three_ticks_null_freezes_symmetric(self):
        L = "2026-08-20"
        state = None
        # fire 1: cold start, candidate escalates immediately away from settled FRAGILE
        state = blre._advance_transition(
            state, live_session=L, precedence="live", live_active=True,
            candidate_stage="TRANSMITTING", settled_stage="FRAGILE", debounce_ticks=3,
            observed_built="obs-1",
        )
        assert state["stable_stage"] == "FRAGILE"
        assert state["pending"] == {"stage": "TRANSMITTING", "ticks": 1, "needs": 3}

        # fire 2: same candidate repeats, a DISTINCT observation
        state = blre._advance_transition(
            state, live_session=L, precedence="live", live_active=True,
            candidate_stage="TRANSMITTING", settled_stage="FRAGILE", debounce_ticks=3,
            observed_built="obs-2",
        )
        assert state["pending"]["ticks"] == 2
        assert state["stable_stage"] == "FRAGILE"   # not yet flipped

        # fire 3: third consecutive same candidate, distinct observation -> flip
        state = blre._advance_transition(
            state, live_session=L, precedence="live", live_active=True,
            candidate_stage="TRANSMITTING", settled_stage="FRAGILE", debounce_ticks=3,
            observed_built="obs-3",
        )
        assert state["stable_stage"] == "TRANSMITTING"
        assert state["pending"] is None

        # fire 4: outage — a null candidate must NEVER tick in any direction
        frozen_before = dict(state)
        state = blre._advance_transition(
            state, live_session=L, precedence="live", live_active=True,
            candidate_stage=None, settled_stage="FRAGILE", debounce_ticks=3,
            observed_built="obs-4",
        )
        assert state["stable_stage"] == frozen_before["stable_stage"]
        assert state["pending"] == frozen_before["pending"]
        assert state["candidate_stage"] is None

        # fires 5-7: symmetric DE-escalation — same 3-tick mechanism, opposite direction
        state = blre._advance_transition(
            state, live_session=L, precedence="live", live_active=True,
            candidate_stage="NONE", settled_stage="FRAGILE", debounce_ticks=3,
            observed_built="obs-5",
        )
        assert state["pending"] == {"stage": "NONE", "ticks": 1, "needs": 3}
        state = blre._advance_transition(
            state, live_session=L, precedence="live", live_active=True,
            candidate_stage="NONE", settled_stage="FRAGILE", debounce_ticks=3,
            observed_built="obs-6",
        )
        assert state["pending"]["ticks"] == 2
        state = blre._advance_transition(
            state, live_session=L, precedence="live", live_active=True,
            candidate_stage="NONE", settled_stage="FRAGILE", debounce_ticks=3,
            observed_built="obs-7",
        )
        assert state["stable_stage"] == "NONE"
        assert state["pending"] is None

    def test_new_live_day_reinitializes_from_settled_not_from_yesterdays_dwell(self):
        prev = {"session": "2026-08-19", "stable_stage": "TRANSMITTING", "pending": None,
                "candidate_stage": "TRANSMITTING", "last_observed_built": "yesterday"}
        state = blre._advance_transition(
            prev, live_session="2026-08-20", precedence="live", live_active=True,
            candidate_stage="TRANSMITTING", settled_stage="NONE", debounce_ticks=3,
            observed_built="obs-today-1",
        )
        # yesterday's stable TRANSMITTING must not silently carry into a new session;
        # today re-baselines from the settled stage and starts a FRESH pending count.
        assert state["stable_stage"] == "NONE"
        assert state["pending"] == {"stage": "TRANSMITTING", "ticks": 1, "needs": 3}

    # ── adjudication #2: ticking is gated on wrapper live_active, not just
    #    precedence — an outage (live_active False) must freeze the dwell state
    #    exactly, never de-escalate it toward calm, and ticking must resume from
    #    the frozen pending (not reset to zero) once live_active recovers. ──────

    def test_outage_freezes_pending_and_resumes_without_resetting(self):
        L = "2026-08-20"
        # fire 1: live, first candidate differs from settled -> pending starts at 1/3
        state = blre._advance_transition(
            None, live_session=L, precedence="live", live_active=True,
            candidate_stage="TRANSMITTING", settled_stage="FRAGILE", debounce_ticks=3,
            observed_built="obs-1",
        )
        assert state["pending"] == {"stage": "TRANSMITTING", "ticks": 1, "needs": 3}

        # fire 2: a second distinct observation -> ticks advance to 2/3
        state = blre._advance_transition(
            state, live_session=L, precedence="live", live_active=True,
            candidate_stage="TRANSMITTING", settled_stage="FRAGILE", debounce_ticks=3,
            observed_built="obs-2",
        )
        assert state["pending"]["ticks"] == 2

        # fires 3-6: outage — live_active False for FOUR consecutive fires (the
        # reviewer's literal reproduction scenario), even though the (stale) read
        # would still claim to differ from stable. stable_stage must never move
        # off its baseline, and pending must not advance OR reset.
        pre_outage = dict(state)
        for i, obs in enumerate(("obs-3", "obs-4", "obs-5", "obs-6")):
            state = blre._advance_transition(
                state, live_session=L, precedence="live", live_active=False,
                candidate_stage="TRANSMITTING", settled_stage="FRAGILE", debounce_ticks=3,
                observed_built=obs,
            )
            assert state["stable_stage"] == pre_outage["stable_stage"] == "FRAGILE", i
            assert state["pending"] == pre_outage["pending"], i   # frozen at 2/3, not 3/3, not reset

        # fire 7: recovery — live_active True again, a genuinely NEW observation,
        # SAME candidate as before the outage -> ticking RESUMES from the frozen
        # 2/3 (not from 0), reaching the debounce window on this one fire.
        state = blre._advance_transition(
            state, live_session=L, precedence="live", live_active=True,
            candidate_stage="TRANSMITTING", settled_stage="FRAGILE", debounce_ticks=3,
            observed_built="obs-7",
        )
        assert state["stable_stage"] == "TRANSMITTING"
        assert state["pending"] is None

    def test_null_candidate_during_live_precedence_freezes_not_just_outage(self):
        """A null candidate (composer degraded to stage=null) must freeze even
        when live_active is True — a source-side null is not the same signal as a
        wrapper-side freshness outage, but both must refuse to tick."""
        L = "2026-08-20"
        state = blre._advance_transition(
            None, live_session=L, precedence="live", live_active=True,
            candidate_stage="FRAGILE", settled_stage="FRAGILE", debounce_ticks=3,
            observed_built="obs-1",
        )
        assert state["pending"] is None and state["stable_stage"] == "FRAGILE"
        frozen = dict(state)
        state = blre._advance_transition(
            state, live_session=L, precedence="live", live_active=True,
            candidate_stage=None, settled_stage="FRAGILE", debounce_ticks=3,
            observed_built="obs-2",
        )
        assert state["stable_stage"] == frozen["stable_stage"]
        assert state["pending"] == frozen["pending"]

    # ── adjudication #5: ticks are keyed to DISTINCT risk_state.json
    #    observations, not fires — this module runs every minute but risk_state
    #    only refreshes on odd minutes, so re-reading the SAME built timestamp
    #    must never count as a second confirmation. ─────────────────────────────

    def test_repeated_observation_does_not_double_tick(self):
        L = "2026-08-20"
        state = blre._advance_transition(
            None, live_session=L, precedence="live", live_active=True,
            candidate_stage="TRANSMITTING", settled_stage="FRAGILE", debounce_ticks=3,
            observed_built="obs-1",
        )
        assert state["pending"]["ticks"] == 1

        # SAME observed_built as fire 1 (risk_state.json has not been rewritten
        # yet) -> must NOT advance to ticks=2.
        state = blre._advance_transition(
            state, live_session=L, precedence="live", live_active=True,
            candidate_stage="TRANSMITTING", settled_stage="FRAGILE", debounce_ticks=3,
            observed_built="obs-1",
        )
        assert state["pending"]["ticks"] == 1, "reusing the same observation must not tick again"

        # a genuinely new observation -> now it advances to 2.
        state = blre._advance_transition(
            state, live_session=L, precedence="live", live_active=True,
            candidate_stage="TRANSMITTING", settled_stage="FRAGILE", debounce_ticks=3,
            observed_built="obs-2",
        )
        assert state["pending"]["ticks"] == 2


# ══ item 8 — no forward ledger, no write beyond site/live/risk_envelope.json ═════

class TestNoLedger:

    def test_module_never_imports_ledger_lane(self):
        src = _LIVE_MODULE.read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [a.name for a in getattr(node, "names", [])] + [getattr(node, "module", "") or ""]
                assert not any("ledger" in n for n in names), f"live module imports a ledger module: {names}"

    def test_only_write_is_site_live_risk_envelope_json(self, tmp_path):
        root = _write_root(
            tmp_path, risk_state=_risk_state("2026-08-20 15:00:00 UTC"),
            leadership=_leadership("2026-08-19"), settled=_settled("2026-08-19"),
        )
        before = {p for p in root.rglob("*") if p.is_file()}
        blre.write(root=root, now=datetime(2026, 8, 20, 15, 1, tzinfo=timezone.utc))
        after = {p for p in root.rglob("*") if p.is_file()}
        new_files = after - before
        assert new_files == {root / "site" / "live" / "risk_envelope.json"}


# ══ item 9 — authority stays hard-false; revision + overlays are correct ═════════

class TestAuthorityAndRevision:

    def test_authority_booleans_all_false_and_revision_is_live_provisional(self, tmp_path):
        root = _write_root(
            tmp_path, risk_state=_risk_state("2026-08-20 15:00:00 UTC"),
            leadership=_leadership("2026-08-19"), settled=_settled("2026-08-19"),
        )
        env = blre.build(root=root, now=datetime(2026, 8, 20, 15, 1, tzinfo=timezone.utc))
        assert env["revision"] == "live_provisional"
        auth = env["authority"]
        assert auth["envelope_may_rank"] is False
        assert auth["envelope_may_gate"] is False
        assert auth["envelope_may_size"] is False
        assert auth["envelope_may_execute"] is False
        assert auth["policy_actions_require_individual_authority"] is True

    def test_overlays_carry_the_settled_bundle(self, tmp_path):
        root = _write_root(
            tmp_path, risk_state=_risk_state("2026-08-20 15:00:00 UTC"),
            leadership=_leadership("2026-08-19"),
            settled=_settled("2026-08-19", bundle_id="fd9ccdbe47f7f008"),
        )
        env = blre.build(root=root, now=datetime(2026, 8, 20, 15, 1, tzinfo=timezone.utc))
        assert env["overlays"]["settled_bundle_id"] == "fd9ccdbe47f7f008"
        assert env["overlays"]["settled_source_session"] == "2026-08-19"


# ══ item 10 — wrapper fields, nullable event_time ════════════════════════════════

class TestWrapperShape:

    REQUIRED_WRAPPER_KEYS = (
        "built", "live_active", "stale_reason", "stale_after_min", "precedence",
        "overlays", "live_transition", "clocks",
    )

    def test_wrapper_fields_present(self, tmp_path):
        root = _write_root(
            tmp_path, risk_state=_risk_state("2026-08-20 15:00:00 UTC"),
            leadership=_leadership("2026-08-19"), settled=_settled("2026-08-19"),
        )
        env = blre.build(root=root, now=datetime(2026, 8, 20, 15, 1, tzinfo=timezone.utc))
        for key in self.REQUIRED_WRAPPER_KEYS:
            assert key in env, f"missing wrapper key {key}"
        for clock in ("event_time", "observed_at", "produced_at"):
            assert clock in env["clocks"]

    def test_event_time_is_nullable_when_risk_state_is_absent(self, tmp_path):
        root = _write_root(tmp_path, leadership=_leadership("2026-08-19"),
                           settled=_settled("2026-08-19"))
        env = blre.build(root=root, now=datetime(2026, 8, 20, 15, 1, tzinfo=timezone.utc))
        assert env["clocks"]["event_time"] is None
        assert env["stale_reason"] == "risk_state artifact unavailable"
        assert env["live_active"] is False


# ══ item 11 — "display" is never read; the envelope follows "live" ═══════════════

class TestDisplayBlockIsNeverConsulted:

    def test_module_source_never_accesses_the_display_key(self):
        src = _LIVE_MODULE.read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "get":
                if node.args and isinstance(node.args[0], ast.Constant) and node.args[0].value == "display":
                    pytest.fail(f"live module reads .get('display') at line {node.lineno}")
            if isinstance(node, ast.Subscript):
                sl = node.slice
                if isinstance(sl, ast.Constant) and sl.value == "display":
                    pytest.fail(f"live module reads ['display'] at line {node.lineno}")

    def test_envelope_follows_live_block_when_display_disagrees(self, tmp_path):
        """`_risk_state()` bakes `display.verdict == 'RISK_ON'` while
        `live.verdict == 'RISK_OFF'` — a real fast-lane shape whenever the debounced
        display word hasn't caught up to the raw live read yet. The envelope must
        follow `live`, never `display`."""
        root = _write_root(
            tmp_path,
            risk_state=_risk_state("2026-08-20 15:00:00 UTC", verdict="RISK_OFF",
                                   display_verdict="RISK_ON"),
            leadership=_leadership("2026-08-19"), settled=_settled("2026-08-19"),
        )
        env = blre.build(root=root, now=datetime(2026, 8, 20, 15, 1, tzinfo=timezone.utc))
        assert env["measured_state"]["verdict"] == "RISK_OFF"
        assert "RISK_ON" not in json.dumps(env)


# ══ adjudication #6 — the band's live-dot reuses theme.css's existing .dtp-dot /
#    @keyframes dtp-pulse; pin their presence so a theme refactor can't silently
#    kill the overlay's only motion without anyone noticing here. ════════════════

class TestLiveDotReusesTheThemeIdiom:

    def test_theme_css_still_carries_the_reused_dot_idiom(self):
        src = _THEME_CSS.read_text(encoding="utf-8")
        assert ".dtp-dot" in src, "templates/theme.css dropped .dtp-dot — the GD-3 live chip reuses it"
        assert "@keyframes dtp-pulse" in src, (
            "templates/theme.css dropped @keyframes dtp-pulse — the GD-3 live chip reuses it"
        )
