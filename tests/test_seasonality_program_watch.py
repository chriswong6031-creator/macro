"""Program watch — the four things that can move biopharma seasonality forward.

The tests that carry weight here are not the happy paths:

* ``test_no_wall_clock_in_the_module`` is the idempotence root cause. A watch
  that reads ``date.today()`` answers differently on a re-run of the same night,
  which makes the artifact non-reproducible and every downstream assertion about
  it unfalsifiable. The grep is crude on purpose: it catches the defect at the
  only place it can be caught cheaply, before it reaches an artifact.
* ``Test*Unavailable*`` pin the state that is easiest to collapse. ``waiting``
  and ``unavailable`` look identical to a reader — both are "no news" — and the
  difference is that one has been checked. A missing input reported as
  ``waiting`` is waited on forever.
* ``test_contract_match_is_not_a_hardcoded_filename`` pins the one design
  decision that expires: the producer session owns the contract's name, so a
  watch keyed on today's guess reports ``waiting`` forever AFTER the thing it
  watches for has landed. Two differently-named payloads must both fire.
* ``test_earliest_pending_ignores_already_graded_rows`` pins the field the
  operator times their check-in on. If a graded row's register still counts as
  pending, the earliest date walks backwards into the past and the watch tells
  them to look for a grade that already exists.
* ``test_annotation_starts_the_line`` is the house law (#3487/#3515/#3562/…):
  every builder here logs with a prefixing format, so an annotation routed
  through ``log`` emits ``INFO ::notice …`` and GitHub drops it silently. The
  assertion is on stdout via ``capsys`` and on ``startswith("::")`` — not on the
  wording — so it pins the defect rather than the message.
* ``test_public_context_carries_only_counts`` is the leak gate's unit half. The
  watch payload is full of operator prompts, doc paths, module names, and
  blocker keys; ``site/measurement.html`` is a PUBLIC page. The only thing
  allowed to cross is two integers and a flag.

Pure stdlib and offline: every case builds its own tree in ``tmp_path``.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.seasonality import program_watch as pw  # noqa: E402
from scripts import build_program_watch as builder  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent

ASOF = "2026-08-07"

TRIPWIRE_KEYS = {
    "key",
    "state",
    "headline",
    "why",
    "evidence",
    "operator_prompt",
    "handoff_doc",
}

EXPECTED_TRIPWIRES = [
    "biocatalyst_event_contract",
    "first_matured_grade",
    "catalyst_render",
    "deferred_followups",
]


# ---------------------------------------------------------------------------
# synthetic tree
# ---------------------------------------------------------------------------


def _write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _register(key: str, end: str) -> str:
    return json.dumps(
        {"row_type": "register", "key": key, "symbol": key.split(":")[0],
         "occurrence_end_date": end, "schema": "seasonality.nw_forward_ledger.v1"},
        sort_keys=True,
    )


def _grade(key: str, status: str = "graded") -> str:
    """A grade row shaped like the real writer's.

    ``grade_status`` is not decoration: ``engine.seasonality.state`` writes
    ``row_type: "grade"`` rows with ``grade_status: "ungradable_missing_prices"``
    and every outcome field ``None`` for a symbol that left the price store.
    """
    graded = status == "graded"
    return json.dumps(
        {"row_type": "grade", "key": key, "symbol": key.split(":")[0],
         "realized_log_return": 0.031 if graded else None,
         "outcome_up": True if graded else None,
         "brier": 0.0576 if graded else None,
         "grade_status": status,
         "schema": "seasonality.nw_forward_ledger.v1"},
        sort_keys=True,
    )


_SYNAPSE_V2 = """\
artifacts:
  data-neuralweb-biopharma-seasonality-state:
    path: data/neuralweb/biopharma_seasonality_state.json
    tier: shadow
    notes: >
      Lane 6 shadow lobe — per-symbol states built by build_neuralweb_state_v2
      (schema neuralweb.biopharma_seasonality_state.v2; the envelope declares the
      per-state schema in state_schema).
  data-something-else:
    path: data/other.json
    notes: >
      Unrelated neighbour. Mentions v1 states loudly so a sloppy scan that walks
      past the entry boundary picks it up: neuralweb.biopharma_seasonality_state.v1.
"""

_SYNAPSE_V1 = _SYNAPSE_V2.replace(
    "build_neuralweb_state_v2\n      (schema neuralweb.biopharma_seasonality_state.v2; the envelope declares the\n"
    "      per-state schema in state_schema).",
    "build_neuralweb_state\n      (schema neuralweb.biopharma_seasonality_state.v1; one state per covered\n"
    "      symbol).",
)


def _make_root(
    tmp_path: Path,
    *,
    contract_names: list[str] | None = None,
    contracts_dir: bool = True,
    ledger: list[str] | None = None,
    template_markers: tuple[str, ...] = pw.CATALYST_MARKERS,
    page_markers: tuple[str, ...] | None = (),
    foundation_names_spa: bool = True,
    validation_defines_spa: bool = False,
    synapse: str | None = _SYNAPSE_V2,
    prophet_first: bool = True,
    dag_decision_token: bool = False,
    dag_token_in_comment: bool = False,
) -> Path:
    """A tree with every watch input present, each one independently knobbed."""
    root = tmp_path / "repo"
    root.mkdir(exist_ok=True)

    if contracts_dir:
        cdir = root / pw.BIOCATALYST_CONTRACTS_DIR
        cdir.mkdir(parents=True, exist_ok=True)
        (cdir / "trial_snapshot.v1.schema.json").write_text("{}", encoding="utf-8")
        for name in contract_names or []:
            (cdir / name).write_text("{}", encoding="utf-8")

    if ledger is not None:
        _write(root, pw.LEDGER_PATH, "\n".join(ledger) + ("\n" if ledger else ""))

    _write(
        root,
        pw.SEASONALITY_TEMPLATE,
        "<div class=\"" + " ".join(template_markers) + "\">seasonality</div>\n",
    )
    if page_markers is not None:
        _write(
            root,
            pw.SEASONALITY_PAGE,
            "<div class=\"" + " ".join(page_markers) + "\">built</div>\n",
        )

    _write(
        root,
        pw.FOUNDATION_PATH,
        '"selection_controls": ["trial_ledger", '
        + ('"spa_reality_check"' if foundation_names_spa else '"joint_max_t"')
        + "]\n",
    )
    _write(
        root,
        pw.VALIDATION_PATH,
        "def reality_check(a, b):\n    return {}\n\n\ndef spa_test(a, b):\n    return {}\n"
        + ("\n\ndef spa_reality_check(a, b):\n    return {}\n" if validation_defines_spa else ""),
    )

    if synapse is not None:
        _write(root, pw.SYNAPSE_PATH, synapse)

    order = (
        ["brun prophet scripts.build_prophet", "brun ss scripts.build_stock_seasonality"]
        if prophet_first
        else ["brun ss scripts.build_stock_seasonality", "brun prophet scripts.build_prophet"]
    )
    _write(root, pw.DAILY_WORKFLOW_PATH, "steps:\n  " + "\n  ".join(order) + "\n")

    # The dag is where the ORDER decision is written down, so the baseline tree
    # carries the file WITHOUT the token: undecided is the default state, and a
    # prophet-first nightly with no decision record stays open.
    dag = "lanes:\n  - id: build_prophet\n    note: Prophet nightly\n"
    if dag_decision_token:
        dag += f"    decision: {pw.DAG_ORDER_DECISION_TOKEN} (one-night lag accepted)\n"
    if dag_token_in_comment:
        dag += f"    # decided elsewhere: {pw.DAG_ORDER_DECISION_TOKEN}\n"
    _write(root, pw.DAG_PATH, dag)
    return root


def _tw(payload: dict, key: str) -> dict:
    matches = [t for t in payload["tripwires"] if t["key"] == key]
    assert len(matches) == 1, f"expected exactly one {key!r} tripwire, got {len(matches)}"
    return matches[0]


# ---------------------------------------------------------------------------
# module-level laws
# ---------------------------------------------------------------------------


class TestModuleLaws:
    def test_no_wall_clock_in_the_module(self):
        """``asof`` is ALWAYS an argument — a clock read here breaks idempotence."""
        source = (REPO_ROOT / "engine" / "seasonality" / "program_watch.py").read_text(
            encoding="utf-8"
        )
        # Strip the docstrings/comments that legitimately NAME the banned calls
        # while explaining why they are banned.
        code = "\n".join(
            line for line in source.splitlines() if not line.lstrip().startswith(("#", "*"))
        )
        code = re.sub(r'"""(?:.|\n)*?"""', "", code)
        for banned in ("datetime.now", "date.today", "time.time", "utcnow"):
            assert banned not in code, (
                f"{banned!r} appears in engine/seasonality/program_watch.py — the watch "
                "must take asof as an explicit argument so two runs over identical "
                "inputs agree."
            )

    def test_schema_is_pinned(self):
        assert pw.WATCH_SCHEMA == "seasonality.program_watch.v1"

    def test_states_are_the_three_declared(self):
        assert set(pw.STATES) == {"fired", "waiting", "unavailable"}

    def test_evaluate_stamps_the_asof_it_was_given(self, tmp_path):
        payload = pw.evaluate(_make_root(tmp_path, ledger=[]), asof="1999-01-02")
        assert payload["asof"] == "1999-01-02"

    def test_every_tripwire_has_the_full_shape(self, tmp_path):
        payload = pw.evaluate(_make_root(tmp_path, ledger=[]), asof=ASOF)
        assert [t["key"] for t in payload["tripwires"]] == EXPECTED_TRIPWIRES
        for tw in payload["tripwires"]:
            assert set(tw) == TRIPWIRE_KEYS, tw["key"]
            assert tw["state"] in pw.STATES
            for field in ("headline", "why", "operator_prompt", "handoff_doc"):
                assert isinstance(tw[field], str) and tw[field].strip(), (tw["key"], field)
            assert isinstance(tw["evidence"], dict) and tw["evidence"]

    def test_counts_account_for_every_tripwire(self, tmp_path):
        payload = pw.evaluate(_make_root(tmp_path, ledger=[]), asof=ASOF)
        assert sum(payload["counts"].values()) == len(payload["tripwires"])
        assert set(payload["counts"]) == set(pw.STATES)

    def test_evaluate_never_raises_on_an_empty_tree(self, tmp_path):
        """A bare directory must degrade to four ``unavailable`` reads, not an exception."""
        payload = pw.evaluate(tmp_path / "nothing-here", asof=ASOF)
        assert payload["counts"]["unavailable"] == len(EXPECTED_TRIPWIRES)

    def test_payload_is_json_serialisable(self, tmp_path):
        payload = pw.evaluate(_make_root(tmp_path, ledger=[]), asof=ASOF)
        json.dumps(payload, sort_keys=True)  # would raise on a Path or a set


# ---------------------------------------------------------------------------
# tripwire 1 — the BioCatalyst producer contract
# ---------------------------------------------------------------------------


class TestBioCatalystEventContract:
    def test_absent_contract_is_waiting_with_a_scanned_count(self, tmp_path):
        tw = _tw(pw.evaluate(_make_root(tmp_path, ledger=[]), asof=ASOF), "biocatalyst_event_contract")
        assert tw["state"] == "waiting"
        assert tw["evidence"]["matched"] == []
        assert tw["evidence"]["n_files_scanned"] >= 1

    @pytest.mark.parametrize(
        "name",
        [
            "biocatalyst_seasonality_event_projection.v1.schema.json",
            "seasonality_event_window.v3.schema.json",
            "EVENT_SEASONALITY_projection.schema.json",
        ],
    )
    def test_contract_match_is_not_a_hardcoded_filename(self, tmp_path, name):
        """The producer owns the naming — matching on one exact string would rot.

        A watch keyed on today's guess reports ``waiting`` forever AFTER the
        contract lands under a neighbouring name, which is worse than no watch:
        it is a green light that never turns.
        """
        tw = _tw(
            pw.evaluate(_make_root(tmp_path, contract_names=[name], ledger=[]), asof=ASOF),
            "biocatalyst_event_contract",
        )
        assert tw["state"] == "fired"
        assert tw["evidence"]["matched"] == [name]
        assert name in tw["headline"]

    def test_a_half_match_does_not_fire(self, tmp_path):
        """One token is not the contract — ``trial_change_alert_projection`` is not it."""
        tw = _tw(
            pw.evaluate(
                _make_root(
                    tmp_path,
                    contract_names=["seasonality_calendar.v1.schema.json", "fda_event.v1.schema.json"],
                    ledger=[],
                ),
                asof=ASOF,
            ),
            "biocatalyst_event_contract",
        )
        assert tw["state"] == "waiting"

    def test_missing_directory_is_unavailable_not_waiting(self, tmp_path):
        tw = _tw(
            pw.evaluate(_make_root(tmp_path, contracts_dir=False, ledger=[]), asof=ASOF),
            "biocatalyst_event_contract",
        )
        assert tw["state"] == "unavailable"
        assert tw["evidence"]["reason"] == "absent"

    def test_fired_prompt_names_the_reconciliation_work(self, tmp_path):
        root = _make_root(
            tmp_path,
            contract_names=["biocatalyst_seasonality_event_projection.v1.schema.json"],
            ledger=[],
        )
        tw = _tw(pw.evaluate(root, asof=ASOF), "biocatalyst_event_contract")
        assert tw["state"] == "fired"
        assert "event_clock.py" in tw["operator_prompt"]
        assert tw["handoff_doc"].startswith("research/")

    def test_contract_matched_by_content_under_a_domain_first_name(self, tmp_path):
        """The producer's own convention carries no ``seasonality`` token.

        All 51 contracts already in ``contracts/biocatalyst/`` are domain-first
        (``trial_protocol_projection.v1.schema.json``,
        ``fda_regulatory_event.v1.schema.json``). A filename-token matcher misses
        a landing named ``biocatalyst_event_projection.v1.schema.json`` — a green
        light that never turns, which is worse than no watch.
        """
        root = _make_root(tmp_path, ledger=[])
        (root / pw.BIOCATALYST_CONTRACTS_DIR / "biocatalyst_event_projection.v1.schema.json").write_text(
            json.dumps({"contract_id": pw.CONTRACT_ID_STEM + ".v1", "schema_version": "1.0.0"}),
            encoding="utf-8",
        )
        tw = _tw(pw.evaluate(root, asof=ASOF), "biocatalyst_event_contract")
        assert tw["state"] == "fired"
        assert tw["evidence"]["matched_by_content"] == [
            "biocatalyst_event_projection.v1.schema.json"
        ]

    def test_contract_filed_in_a_subdirectory_is_found(self, tmp_path):
        """A non-recursive scan reports ``waiting`` forever with 0 files scanned."""
        root = _make_root(tmp_path, ledger=[])
        sub = root / pw.BIOCATALYST_CONTRACTS_DIR / "seasonality"
        sub.mkdir(parents=True, exist_ok=True)
        (sub / "event_projection.v1.schema.json").write_text("{}", encoding="utf-8")
        tw = _tw(pw.evaluate(root, asof=ASOF), "biocatalyst_event_contract")
        assert tw["state"] == "fired"
        assert tw["evidence"]["matched"] == ["seasonality/event_projection.v1.schema.json"]

    def test_a_markdown_note_is_not_a_contract(self, tmp_path):
        """``README_seasonality_event_notes.md`` satisfies both tokens and is prose.

        Firing on it sends the operator to run a reconciliation PR against
        nothing, and the tripwire never returns to ``waiting``.
        """
        root = _make_root(tmp_path, ledger=[])
        (root / pw.BIOCATALYST_CONTRACTS_DIR / "README_seasonality_event_notes.md").write_text(
            "notes about a seasonality event projection\n", encoding="utf-8"
        )
        tw = _tw(pw.evaluate(root, asof=ASOF), "biocatalyst_event_contract")
        assert tw["state"] == "waiting"
        assert tw["evidence"]["matched"] == []

    def test_waiting_prompt_does_not_assert_the_fired_world(self, tmp_path):
        """A prompt written for the FIRED world is a false statement of state.

        The prompts are the field an operator pastes back and an automation would
        pipe; ``"The contract has landed. Run the W1B reconciliation PR"`` on a
        night when the tripwire says it has NOT landed is a lie with a to-do list
        attached.
        """
        tw = _tw(pw.evaluate(_make_root(tmp_path, ledger=[]), asof=ASOF), "biocatalyst_event_contract")
        assert tw["state"] == "waiting"
        assert "has landed" not in tw["operator_prompt"]
        assert "NOT landed" in tw["operator_prompt"]

    def test_unavailable_prompt_does_not_assert_the_fired_world(self, tmp_path):
        tw = _tw(
            pw.evaluate(_make_root(tmp_path, contracts_dir=False, ledger=[]), asof=ASOF),
            "biocatalyst_event_contract",
        )
        assert tw["state"] == "unavailable"
        assert "has landed" not in tw["operator_prompt"]
        assert "could not be checked" in tw["operator_prompt"]


# ---------------------------------------------------------------------------
# tripwire 2 — the first matured grade
# ---------------------------------------------------------------------------


class TestFirstMaturedGrade:
    def test_registrations_without_grades_are_waiting(self, tmp_path):
        root = _make_root(
            tmp_path, ledger=[_register("A:2026:299-344", "2026-12-10"), _register("B:2026:1-30", "2026-09-01")]
        )
        tw = _tw(pw.evaluate(root, asof=ASOF), "first_matured_grade")
        assert tw["state"] == "waiting"
        assert tw["evidence"]["registered"] == 2
        assert tw["evidence"]["graded"] == 0
        assert tw["evidence"]["earliest_pending_occurrence_end"] == "2026-09-01"

    def test_first_grade_fires(self, tmp_path):
        root = _make_root(
            tmp_path,
            ledger=[_register("A:2026:1-30", "2026-08-01"), _grade("A:2026:1-30")],
        )
        tw = _tw(pw.evaluate(root, asof=ASOF), "first_matured_grade")
        assert tw["state"] == "fired"
        assert tw["evidence"]["graded"] == 1

    def test_earliest_pending_ignores_already_graded_rows(self, tmp_path):
        """The graded window's date must not resurface as "when to expect the first grade"."""
        root = _make_root(
            tmp_path,
            ledger=[
                _register("A:2026:1-30", "2026-01-30"),
                _grade("A:2026:1-30"),
                _register("B:2026:200-240", "2026-08-28"),
            ],
        )
        tw = _tw(pw.evaluate(root, asof=ASOF), "first_matured_grade")
        assert tw["evidence"]["earliest_pending_occurrence_end"] == "2026-08-28"
        assert tw["evidence"]["pending"] == 1

    def test_malformed_line_is_counted_not_fatal(self, tmp_path):
        root = _make_root(
            tmp_path,
            ledger=[
                _register("A:2026:1-30", "2026-09-01"),
                "{not json at all",
                "[1, 2, 3]",  # valid JSON, wrong shape
                _register("B:2026:1-30", "2026-10-01"),
            ],
        )
        tw = _tw(pw.evaluate(root, asof=ASOF), "first_matured_grade")
        assert tw["state"] == "waiting"
        assert tw["evidence"]["malformed"] == 2
        assert tw["evidence"]["registered"] == 2

    def test_garbled_occurrence_date_never_becomes_the_earliest(self, tmp_path):
        """A junk date must not become the field the operator times a check-in on."""
        root = _make_root(
            tmp_path,
            ledger=[
                json.dumps({"row_type": "register", "key": "A:x", "occurrence_end_date": "soon"}),
                _register("B:2026:1-30", "2026-11-11"),
            ],
        )
        tw = _tw(pw.evaluate(root, asof=ASOF), "first_matured_grade")
        assert tw["evidence"]["earliest_pending_occurrence_end"] == "2026-11-11"

    def test_all_pending_dates_garbled_reports_none_not_a_guess(self, tmp_path):
        root = _make_root(
            tmp_path,
            ledger=[json.dumps({"row_type": "register", "key": "A:x", "occurrence_end_date": ""})],
        )
        tw = _tw(pw.evaluate(root, asof=ASOF), "first_matured_grade")
        assert tw["evidence"]["earliest_pending_occurrence_end"] is None

    def test_missing_ledger_is_unavailable_not_zero(self, tmp_path):
        """A partial checkout must not be reported as "nothing has been registered"."""
        tw = _tw(pw.evaluate(_make_root(tmp_path, ledger=None), asof=ASOF), "first_matured_grade")
        assert tw["state"] == "unavailable"
        assert "could not be read" in tw["headline"]

    def test_empty_ledger_is_waiting_with_real_zeros(self, tmp_path):
        tw = _tw(pw.evaluate(_make_root(tmp_path, ledger=[]), asof=ASOF), "first_matured_grade")
        assert tw["state"] == "waiting"
        assert tw["evidence"]["registered"] == 0

    def test_read_ledger_counts_is_shape_stable(self, tmp_path):
        root = _make_root(tmp_path, ledger=[_register("A:2026:1-30", "2026-09-01")])
        counts = pw.read_ledger_counts(root)
        assert counts["available"] is True
        assert counts["by_type"] == {"register": 1}

    # --- what counts as SCORED -------------------------------------------

    def test_a_closeout_with_no_prices_is_not_a_score(self, tmp_path):
        """``ungradable_missing_prices`` rows are closed, not scored.

        ``engine.seasonality.state.live_n_by_symbol`` — the canonical
        forward-sample reader — excludes them by name: "closed but carry no
        outcome, so they are not evidence and are not counted". Counting them
        here fires "the first forward evidence the calendar clock has any edge at
        all" on zero forward evidence.
        """
        root = _make_root(
            tmp_path,
            ledger=[
                _register("A:2026:1-30", "2026-01-30"),
                _register("B:2026:1-30", "2026-02-28"),
                _grade("A:2026:1-30", status="ungradable_missing_prices"),
                _grade("B:2026:1-30", status="ungradable_missing_prices"),
            ],
        )
        tw = _tw(pw.evaluate(root, asof=ASOF), "first_matured_grade")
        assert tw["state"] == "waiting", "a close-out is not forward evidence"
        assert tw["evidence"]["graded"] == 0
        assert tw["evidence"]["closed_out_ungradable"] == 2
        assert tw["evidence"]["grade_status_counts"] == {"ungradable_missing_prices": 2}
        assert "first forward evidence" not in tw["why"]

    def test_a_closeout_is_not_pending_either(self, tmp_path):
        """It will never produce a grade, so it must not be waited on."""
        root = _make_root(
            tmp_path,
            ledger=[
                _register("A:2026:1-30", "2026-01-30"),
                _grade("A:2026:1-30", status="ungradable_missing_prices"),
                _register("B:2026:200-240", "2026-08-28"),
            ],
        )
        counts = pw.read_ledger_counts(root)
        assert counts["pending"] == 1
        assert counts["earliest_pending_occurrence_end"] == "2026-08-28"

    def test_one_real_grade_alongside_closeouts_still_fires(self, tmp_path):
        root = _make_root(
            tmp_path,
            ledger=[
                _register("A:2026:1-30", "2026-01-30"),
                _register("B:2026:1-30", "2026-02-28"),
                _grade("A:2026:1-30"),
                _grade("B:2026:1-30", status="ungradable_missing_prices"),
            ],
        )
        tw = _tw(pw.evaluate(root, asof=ASOF), "first_matured_grade")
        assert tw["state"] == "fired"
        assert tw["evidence"]["graded"] == 1
        assert "1 of 2" in tw["headline"]

    # --- identity: keys, not rows ----------------------------------------

    def test_keyless_rows_do_not_collapse_onto_one_identity(self, tmp_path):
        """Every keyless row got identity ``""`` — so one keyless grade graded them all."""
        root = _make_root(
            tmp_path,
            ledger=[
                json.dumps({"row_type": "register", "occurrence_end_date": "2026-09-01"}),
                json.dumps({"row_type": "register", "occurrence_end_date": "2026-10-01"}),
                json.dumps({"row_type": "grade", "grade_status": "graded"}),
            ],
        )
        counts = pw.read_ledger_counts(root)
        assert counts["registered"] == 2
        assert counts["pending"] == 2, "a keyless grade must not mark keyless registers graded"
        assert counts["earliest_pending_occurrence_end"] == "2026-09-01"
        assert counts["keyless_rows"] == 3

    def test_a_grade_for_an_unregistered_key_does_not_deflate_pending(self, tmp_path):
        """``pending = registered - graded`` over unintersected sets erases real windows."""
        root = _make_root(
            tmp_path,
            ledger=[
                _register("A:2026:1-30", "2026-09-01"),
                _register("B:2026:1-30", "2026-10-01"),
                _grade("ZZZ:2026:1-30"),
                _grade("YYY:2026:1-30"),
            ],
        )
        tw = _tw(pw.evaluate(root, asof=ASOF), "first_matured_grade")
        assert tw["state"] == "waiting", "no REGISTERED window is graded"
        assert tw["evidence"]["graded"] == 0
        assert tw["evidence"]["graded_total"] == 2
        assert tw["evidence"]["graded_unregistered"] == 2
        assert tw["evidence"]["pending"] == 2

    def test_duplicate_rows_count_once_so_graded_never_exceeds_registered(self, tmp_path):
        """Rows on one side and distinct keys on the other prints ``2 of 1``."""
        root = _make_root(
            tmp_path,
            ledger=[
                _register("A:2026:1-30", "2026-09-01"),
                _register("A:2026:1-30", "2026-09-01"),  # append-only re-register
                _register("B:2026:1-30", "2026-10-01"),
                _grade("A:2026:1-30"),
                _grade("A:2026:1-30"),  # append-only re-grade
            ],
        )
        counts = pw.read_ledger_counts(root)
        assert counts["registered"] == 2
        assert counts["graded"] == 1
        assert counts["pending"] == 1
        assert counts["graded"] <= counts["registered"]

    def test_dropped_occurrence_dates_are_counted_not_hidden(self, tmp_path):
        """A dropped date pushes the operator's check-in LATER, silently.

        ``pending`` and the number of usable dates disagreed with nothing in the
        evidence disclosing the gap — the reported "earliest" was four months
        after the true earliest and the tripwire said "nothing before then is
        news".
        """
        root = _make_root(
            tmp_path,
            ledger=[
                json.dumps({"row_type": "register", "key": "A:x", "occurrence_end_date": "2026-8-1"}),
                _register("B:2026:1-30", "2026-12-31"),
            ],
        )
        counts = pw.read_ledger_counts(root)
        assert counts["pending"] == 2
        assert counts["earliest_pending_occurrence_end"] == "2026-12-31"
        assert counts["pending_without_readable_end"] == 1

    # --- prompts state-correct -------------------------------------------

    def test_waiting_prompt_does_not_announce_a_grade(self, tmp_path):
        root = _make_root(tmp_path, ledger=[_register("A:2026:1-30", "2026-09-01")])
        tw = _tw(pw.evaluate(root, asof=ASOF), "first_matured_grade")
        assert tw["state"] == "waiting"
        assert "has its first graded window" not in tw["operator_prompt"]
        assert "No seasonality window has been graded yet" in tw["operator_prompt"]

    def test_unavailable_prompt_says_unknown_not_zero(self, tmp_path):
        tw = _tw(pw.evaluate(_make_root(tmp_path, ledger=None), asof=ASOF), "first_matured_grade")
        assert tw["state"] == "unavailable"
        assert "has its first graded window" not in tw["operator_prompt"]
        assert "UNKNOWN" in tw["operator_prompt"]


# ---------------------------------------------------------------------------
# tripwire 3 — the catalyst UI reaching the built page
# ---------------------------------------------------------------------------


class TestCatalystRender:
    def test_both_have_it_is_fired(self, tmp_path):
        root = _make_root(tmp_path, ledger=[], page_markers=pw.CATALYST_MARKERS)
        tw = _tw(pw.evaluate(root, asof=ASOF), "catalyst_render")
        assert tw["state"] == "fired"
        assert tw["evidence"]["missing_from_page"] == []

    def test_template_only_is_waiting(self, tmp_path):
        root = _make_root(tmp_path, ledger=[], page_markers=())
        tw = _tw(pw.evaluate(root, asof=ASOF), "catalyst_render")
        assert tw["state"] == "waiting"
        assert set(tw["evidence"]["missing_from_page"]) == set(pw.CATALYST_MARKERS)

    def test_partial_render_is_still_waiting(self, tmp_path):
        """Shell present, catalyst block absent — a half-rendered page is not live."""
        root = _make_root(tmp_path, ledger=[], page_markers=("sx-mode",))
        tw = _tw(pw.evaluate(root, asof=ASOF), "catalyst_render")
        assert tw["state"] == "waiting"
        assert tw["evidence"]["missing_from_page"] == ["sx-catalyst"]

    def test_template_lacks_the_markers_is_unavailable(self, tmp_path):
        root = _make_root(tmp_path, ledger=[], template_markers=(), page_markers=())
        tw = _tw(pw.evaluate(root, asof=ASOF), "catalyst_render")
        assert tw["state"] == "unavailable"
        assert tw["evidence"]["template_markers"] == []

    def test_missing_built_page_is_unavailable_not_waiting(self, tmp_path):
        root = _make_root(tmp_path, ledger=[], page_markers=None)
        tw = _tw(pw.evaluate(root, asof=ASOF), "catalyst_render")
        assert tw["state"] == "unavailable"

    def test_no_age_measure_anywhere_in_the_evidence(self, tmp_path):
        """mtimes are observer-stamped repo-wide — an age gate here would lie."""
        root = _make_root(tmp_path, ledger=[], page_markers=())
        tw = _tw(pw.evaluate(root, asof=ASOF), "catalyst_render")
        blob = json.dumps(tw["evidence"]).lower()
        # Whole words: "page" legitimately contains "age", and a substring test
        # that flagged it would be a guard nobody could keep green.
        for banned in ("mtime", "days", "age", "stuck_for", "modified", "since", "stale_for"):
            assert not re.search(rf"\b{banned}\b", blob), (
                f"{banned!r} in catalyst_render evidence — mtimes are observer-stamped "
                "repo-wide in this fleet, so any age measure here would lie"
            )

    def test_why_names_the_two_night_reading(self, tmp_path):
        root = _make_root(tmp_path, ledger=[], page_markers=())
        tw = _tw(pw.evaluate(root, asof=ASOF), "catalyst_render")
        assert "two nights" in tw["why"]

    def test_a_partial_template_marker_set_cannot_declare_the_page_live(self, tmp_path):
        """Half a marker pair cannot tell a partial render from a complete one.

        ``missing`` was computed against the markers found in the TEMPLATE, so a
        template carrying only ``sx-mode`` (a generic mode class) and a page
        carrying only ``sx-mode`` satisfied ``missing == []`` and the tripwire
        published "the catalyst mode is live on the built page" with the catalyst
        block nowhere in the tree. The pair exists precisely to make that
        distinction; when the pair is incomplete the honest answer is that the
        comparison could not be made.
        """
        root = _make_root(
            tmp_path, ledger=[], template_markers=("sx-mode",), page_markers=("sx-mode",)
        )
        tw = _tw(pw.evaluate(root, asof=ASOF), "catalyst_render")
        assert tw["state"] == "unavailable"
        assert "live" not in tw["headline"]
        assert tw["evidence"]["missing_from_template"] == ["sx-catalyst"]

    def test_unavailable_prompt_does_not_blame_the_render_lane(self, tmp_path):
        """The old prompt contradicted its own headline.

        With the markers absent from the TEMPLATE, the headline said "the
        catalyst markers are not in the seasonality template" while the prompt
        said "…is present in templates/stock_seasonality.html.j2 but missing from
        the built page. Check the render lane."
        """
        root = _make_root(tmp_path, ledger=[], template_markers=(), page_markers=())
        tw = _tw(pw.evaluate(root, asof=ASOF), "catalyst_render")
        assert tw["state"] == "unavailable"
        assert "is present in templates/stock_seasonality.html.j2" not in tw["operator_prompt"]
        assert "could not be made" in tw["operator_prompt"]


# ---------------------------------------------------------------------------
# tripwire 4 — the three quiet deferrals
# ---------------------------------------------------------------------------


class TestDeferredFollowups:
    def _sub(self, root: Path, key_fragment: str) -> dict:
        tw = _tw(pw.evaluate(root, asof=ASOF), "deferred_followups")
        matches = [s for s in tw["evidence"]["checked"] if key_fragment in s["key"]]
        assert len(matches) == 1, f"{key_fragment}: {[s['key'] for s in tw['evidence']['checked']]}"
        return matches[0]

    def test_all_three_sub_checks_are_reported(self, tmp_path):
        tw = _tw(pw.evaluate(_make_root(tmp_path, ledger=[]), asof=ASOF), "deferred_followups")
        assert len(tw["evidence"]["checked"]) == 3
        for sub in tw["evidence"]["checked"]:
            assert set(sub) == {"key", "state", "detail", "prompt"}
            assert sub["state"] in {"open", "closed", "unavailable"}
            assert sub["prompt"].strip()

    def test_spa_symbol_open_when_named_but_undefined(self, tmp_path):
        root = _make_root(tmp_path, ledger=[], foundation_names_spa=True, validation_defines_spa=False)
        assert self._sub(root, "foundation_names")["state"] == "open"

    def test_spa_symbol_closes_once_the_symbol_exists(self, tmp_path):
        root = _make_root(tmp_path, ledger=[], foundation_names_spa=True, validation_defines_spa=True)
        assert self._sub(root, "foundation_names")["state"] == "closed"

    def test_spa_symbol_closes_when_the_manifest_stops_naming_it(self, tmp_path):
        root = _make_root(tmp_path, ledger=[], foundation_names_spa=False, validation_defines_spa=False)
        assert self._sub(root, "foundation_names")["state"] == "closed"

    def test_synapse_notes_open_on_v1_prose(self, tmp_path):
        root = _make_root(tmp_path, ledger=[], synapse=_SYNAPSE_V1)
        assert self._sub(root, "synapse")["state"] == "open"

    def test_synapse_notes_closed_on_v2_prose(self, tmp_path):
        root = _make_root(tmp_path, ledger=[], synapse=_SYNAPSE_V2)
        assert self._sub(root, "synapse")["state"] == "closed"

    def test_synapse_scan_stops_at_the_entry_boundary(self, tmp_path):
        """The neighbour entry shouts "v1" — reading past the boundary would flip the answer."""
        root = _make_root(tmp_path, ledger=[], synapse=_SYNAPSE_V1)
        detail = self._sub(root, "synapse")["detail"]
        # The v1 fixture's own notes are ~150 chars; the neighbour's add ~150 more.
        n_chars = int(re.search(r"\((\d+) chars", detail).group(1))
        assert n_chars < 300, f"notes scan ran past the entry boundary ({n_chars} chars)"

    def test_missing_synapse_entry_is_unavailable_not_closed(self, tmp_path):
        root = _make_root(tmp_path, ledger=[], synapse="artifacts:\n  other:\n    path: x\n")
        assert self._sub(root, "synapse")["state"] == "unavailable"

    def test_daily_order_open_when_prophet_runs_first(self, tmp_path):
        root = _make_root(tmp_path, ledger=[], prophet_first=True)
        sub = self._sub(root, "daily_workflow")
        assert sub["state"] == "open"
        assert "line" in sub["detail"]

    def test_daily_order_closed_when_seasonality_runs_first(self, tmp_path):
        root = _make_root(tmp_path, ledger=[], prophet_first=False)
        assert self._sub(root, "daily_workflow")["state"] == "closed"

    def test_daily_order_closes_on_a_documented_decision(self, tmp_path):
        """The follow-up asked for a DECISION, not for one particular order.

        Prophet-first with the rationale written into ``config/dag.yml`` is a
        closed follow-up: the lag is one night on a window family rebuilt from
        COMPLETE years, so last night's windows are this night's windows on every
        night but the one after a rollover.
        """
        root = _make_root(tmp_path, ledger=[], prophet_first=True, dag_decision_token=True)
        sub = self._sub(root, "daily_workflow")
        assert sub["state"] == "closed"
        assert pw.DAG_ORDER_DECISION_TOKEN in sub["detail"]

    def test_daily_order_stays_open_when_the_token_is_only_a_comment(self, tmp_path):
        """A commented token is prose about a decision, not the decision.

        Same discipline as the workflow scan one function up: the dag text is
        comment-stripped first, so a ``#`` line naming the token cannot close the
        follow-up on its own.
        """
        root = _make_root(tmp_path, ledger=[], prophet_first=True, dag_token_in_comment=True)
        sub = self._sub(root, "daily_workflow")
        assert sub["state"] == "open"
        assert pw.DAG_ORDER_DECISION_TOKEN in sub["detail"]

    def test_daily_order_stays_open_when_the_dag_is_unreadable(self, tmp_path):
        """Fail-closed: a missing decision record is undecided, never decided."""
        root = _make_root(tmp_path, ledger=[], prophet_first=True, dag_decision_token=True)
        (root / pw.DAG_PATH).unlink()
        assert self._sub(root, "daily_workflow")["state"] == "open"

    def test_daily_order_does_not_match_a_longer_sibling_name(self, tmp_path):
        """``build_prophet_board`` / ``build_stock_seasonality_page`` are different builders."""
        root = _make_root(tmp_path, ledger=[])
        (root / pw.DAILY_WORKFLOW_PATH).write_text(
            "steps:\n  brun a scripts.build_prophet_board\n"
            "  brun b scripts.build_stock_seasonality_page\n",
            encoding="utf-8",
        )
        assert self._sub(root, "daily_workflow")["state"] == "unavailable"

    def test_any_open_sub_check_fires_the_tripwire(self, tmp_path):
        root = _make_root(tmp_path, ledger=[], foundation_names_spa=True, validation_defines_spa=False,
                          synapse=_SYNAPSE_V2, prophet_first=False)
        tw = _tw(pw.evaluate(root, asof=ASOF), "deferred_followups")
        assert tw["state"] == "fired"
        assert [s["key"] for s in tw["evidence"]["open"]] == [
            "foundation_names_a_validation_symbol_that_does_not_exist"
        ]

    def test_every_open_sub_check_carries_its_own_prompt(self, tmp_path):
        root = _make_root(tmp_path, ledger=[], synapse=_SYNAPSE_V1, prophet_first=True)
        tw = _tw(pw.evaluate(root, asof=ASOF), "deferred_followups")
        assert len(tw["evidence"]["open"]) == 3
        prompts = {s["prompt"] for s in tw["evidence"]["open"]}
        assert len(prompts) == 3, "sub-checks share a prompt — each needs its own next action"

    def test_all_closed_is_waiting_not_fired(self, tmp_path):
        root = _make_root(tmp_path, ledger=[], validation_defines_spa=True, prophet_first=False)
        tw = _tw(pw.evaluate(root, asof=ASOF), "deferred_followups")
        assert tw["state"] == "waiting"
        assert tw["evidence"]["n_open"] == 0

    def test_unreadable_input_with_no_open_check_is_unavailable(self, tmp_path):
        root = _make_root(tmp_path, ledger=[], validation_defines_spa=True, prophet_first=False)
        (root / pw.SYNAPSE_PATH).unlink()
        tw = _tw(pw.evaluate(root, asof=ASOF), "deferred_followups")
        assert tw["state"] == "unavailable"
        assert tw["evidence"]["n_unavailable"] == 1

    def test_an_open_check_outranks_an_unavailable_one(self, tmp_path):
        """Something actionable beats something unknown — the operator can act on it now."""
        root = _make_root(tmp_path, ledger=[], prophet_first=True)
        (root / pw.SYNAPSE_PATH).unlink()
        tw = _tw(pw.evaluate(root, asof=ASOF), "deferred_followups")
        assert tw["state"] == "fired"

    def test_headline_discloses_the_sub_checks_it_could_not_read(self, tmp_path):
        """"1 of 3 still open" reads as "2 are closed". Zero were closed.

        The same collapse this module exists to prevent, one level down: an
        unavailable sub-check swallowed into ``evidence.n_unavailable`` while the
        headline implies it was checked and passed.
        """
        root = _make_root(
            tmp_path, ledger=[], foundation_names_spa=True, validation_defines_spa=False
        )
        (root / pw.SYNAPSE_PATH).unlink()
        (root / pw.DAILY_WORKFLOW_PATH).unlink()
        tw = _tw(pw.evaluate(root, asof=ASOF), "deferred_followups")
        assert tw["state"] == "fired"
        assert tw["evidence"]["n_open"] == 1
        assert tw["evidence"]["n_closed"] == 0
        assert tw["evidence"]["n_unavailable"] == 2
        assert "2 could not be checked" in tw["headline"]

    # --- the sub-checks must test the condition they NAME ------------------

    @pytest.mark.parametrize(
        "notes",
        [
            "Emits the v2 per-state schema; the envelope declares state_schema.",
            "Per-state rows now follow schema version 2 (state_schema on the envelope).",
            "neuralweb.biopharma_seasonality_state.v2 per-state schema.",
        ],
    )
    def test_synapse_notes_close_on_any_correct_rewrite(self, tmp_path, notes):
        """The detector must test the CONDITION, not three magic substrings.

        The old test — ``_state_v2`` / ``_state.v2`` / ``state v2`` — read
        ``open`` for correct rewrites, so the follow-up could be done and the
        tripwire would keep firing forever: a detector that cannot be satisfied.
        """
        synapse = (
            "artifacts:\n"
            "  data-neuralweb-biopharma-seasonality-state:\n"
            "    path: data/neuralweb/biopharma_seasonality_state.json\n"
            f"    notes: >\n      {notes}\n"
        )
        root = _make_root(tmp_path, ledger=[], synapse=synapse)
        assert self._sub(root, "synapse")["state"] == "closed"

    def test_synapse_notes_stay_open_when_only_the_v2_BUILDER_is_named(self, tmp_path):
        """Notes that still describe v1 fields are not closed by naming the v2 producer.

        ``\\bv2\\b`` is load-bearing: ``_`` is a word character, so it does not
        match inside ``build_neuralweb_state_v2``.
        """
        synapse = (
            "artifacts:\n"
            "  data-neuralweb-biopharma-seasonality-state:\n"
            "    path: data/neuralweb/biopharma_seasonality_state.json\n"
            "    notes: >\n"
            "      Each state carries the band/score/expires_at fields exactly as before.\n"
            "      Built by contracts.build_neuralweb_state_v2.\n"
        )
        root = _make_root(tmp_path, ledger=[], synapse=synapse)
        assert self._sub(root, "synapse")["state"] == "open"

    def test_daily_order_ignores_a_comment_that_names_a_builder(self, tmp_path):
        """COMMENTS ARE NOT STEPS.

        The real ``daily.yml``'s first textual ``build_prophet`` is the prose line
        "# R2 creds: … build_prophet skips upload gracefully when absent."; the
        invocation is eleven lines below it. Reading comments makes the verdict
        accidental — adding a comment naming the other builder flips the
        sub-check with nothing about the nightly having changed.
        """
        root = _make_root(tmp_path, ledger=[])
        (root / pw.DAILY_WORKFLOW_PATH).write_text(
            "steps:\n"
            "  # build_stock_seasonality is mentioned here in prose only\n"
            "  - run: python -m scripts.build_prophet --publish\n"
            "  - run: python -m scripts.build_stock_seasonality\n",
            encoding="utf-8",
        )
        sub = self._sub(root, "daily_workflow")
        assert sub["state"] == "open", "a comment decided the ordering verdict"
        assert "line 3" in sub["detail"]

    def test_daily_order_ignores_a_trailing_comment(self, tmp_path):
        root = _make_root(tmp_path, ledger=[])
        (root / pw.DAILY_WORKFLOW_PATH).write_text(
            "steps:\n"
            "  - run: echo hi   # build_prophet runs later, see below\n"
            "  - run: python -m scripts.build_stock_seasonality\n"
            "  - run: python -m scripts.build_prophet\n",
            encoding="utf-8",
        )
        assert self._sub(root, "daily_workflow")["state"] == "closed"


# ---------------------------------------------------------------------------
# the builder
# ---------------------------------------------------------------------------


class TestBuilder:
    def test_writes_the_artifact_at_the_registered_path(self, tmp_path):
        root = _make_root(tmp_path, ledger=[])
        builder.build(root=root, asof=ASOF)
        out = root / builder.OUT_PATH
        assert out.exists()
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["schema"] == pw.WATCH_SCHEMA
        assert payload["asof"] == ASOF

    def test_idempotent_byte_for_byte(self, tmp_path):
        root = _make_root(tmp_path, ledger=[_register("A:2026:1-30", "2026-09-01")])
        builder.build(root=root, asof=ASOF)
        first = (root / builder.OUT_PATH).read_bytes()
        builder.build(root=root, asof=ASOF)
        assert (root / builder.OUT_PATH).read_bytes() == first

    def test_no_tmp_file_survives_the_write(self, tmp_path):
        root = _make_root(tmp_path, ledger=[])
        builder.build(root=root, asof=ASOF)
        leftovers = sorted(p.name for p in (root / builder.OUT_PATH).parent.glob("*.tmp"))
        assert leftovers == []

    def test_annotation_starts_the_line(self, tmp_path, capsys):
        """House law: an annotation routed through a prefixing logger is dropped silently."""
        root = _make_root(tmp_path, ledger=[], prophet_first=True)  # fires deferred_followups
        builder.build(root=root, asof=ASOF)
        lines = [ln for ln in capsys.readouterr().out.splitlines() if "::notice" in ln]
        assert lines, "a fired tripwire emitted no annotation"
        for line in lines:
            assert line.startswith("::"), f"annotation does not start the line: {line!r}"

    def test_one_annotation_per_fired_tripwire_and_none_for_the_rest(self, tmp_path, capsys):
        root = _make_root(tmp_path, ledger=[], prophet_first=True)
        summary = builder.build(root=root, asof=ASOF)
        notices = [ln for ln in capsys.readouterr().out.splitlines() if ln.startswith("::notice")]
        assert len(notices) == len(summary["fired"]) == summary["counts"]["fired"]
        for key in summary["fired"]:
            assert any(f"seasonality_watch_{key}" in ln for ln in notices)

    def test_no_annotation_when_nothing_fired(self, tmp_path, capsys):
        root = _make_root(tmp_path, ledger=[], validation_defines_spa=True, prophet_first=False)
        summary = builder.build(root=root, asof=ASOF)
        assert summary["counts"]["fired"] == 0
        assert [ln for ln in capsys.readouterr().out.splitlines() if ln.startswith("::notice")] == []

    def test_asof_falls_back_the_same_way_the_sibling_does(self, tmp_path):
        root = _make_root(tmp_path, ledger=[])
        _write(root, builder.INDEX_PATH, json.dumps({"as_of": "2026-07-31"}))
        assert builder.resolve_asof(root) == "2026-07-31"

    def test_asof_ignores_a_garbled_index_value(self, tmp_path):
        from datetime import datetime, timezone

        root = _make_root(tmp_path, ledger=[])
        _write(root, builder.INDEX_PATH, json.dumps({"as_of": "not-a-date"}))
        now = datetime(2026, 8, 7, 5, 0, tzinfo=timezone.utc)
        assert builder.resolve_asof(root, now=now) == "2026-08-07"

    def test_annotation_escapes_newlines_and_percent(self, tmp_path, capsys):
        """An annotation body is line-oriented: a raw newline TRUNCATES it.

        The message interpolates matched contract FILENAMES and free-text
        ``why`` prose, so the payload is not under the builder's control. A
        ``%`` can also eat the next two characters as an escape.
        """
        root = _make_root(tmp_path, ledger=[])
        cdir = root / pw.BIOCATALYST_CONTRACTS_DIR
        (cdir / "seasonality_event_100%_draft.v1.schema.json").write_text("{}", encoding="utf-8")
        builder.build(root=root, asof=ASOF)
        notices = [ln for ln in capsys.readouterr().out.splitlines() if ln.startswith("::notice")]
        contract_lines = [ln for ln in notices if "biocatalyst_event_contract" in ln]
        assert contract_lines, "the contract tripwire did not fire"
        for line in contract_lines:
            assert "100%25_draft" in line, "a bare % survived into the annotation body"
            assert "%_draft" not in line.replace("%25", "")

    def test_escape_helper_encodes_newlines(self):
        assert builder._escape_annotation("a\nb\r\nc") == "a%0Ab%0D%0Ac"
        assert builder._escape_annotation("50% off\n") == "50%25 off%0A"

    def test_main_is_fail_open(self, tmp_path, monkeypatch, capsys):
        """A watch must never take the nightly down."""
        def _boom(**_kwargs):
            raise RuntimeError("synthetic")

        monkeypatch.setattr(builder, "build", _boom)
        monkeypatch.setattr(sys, "argv", ["build_program_watch", "--root", str(tmp_path)])
        assert builder.main() == 0
        out = capsys.readouterr().out
        assert any(ln.startswith("::warning") for ln in out.splitlines())


# ---------------------------------------------------------------------------
# public-page containment
# ---------------------------------------------------------------------------


class TestHandoffResolution:
    """The handoff path feeds ``handoff_doc`` and the prompt text of 3 tripwires."""

    _NEW = "BIOPHARMA_SEASONALITY_INTELLIGENCE_CLAUDE_CONTINUATION_HANDOFF_2026-09-30.md"
    _OLD = "BIOPHARMA_SEASONALITY_INTELLIGENCE_CONTINUATION_HANDOFF_2026-08-06.md"

    def _research(self, tmp_path: Path, *names: str) -> Path:
        root = tmp_path / "repo"
        (root / "research").mkdir(parents=True, exist_ok=True)
        for name in names:
            (root / "research" / name).write_text("handoff\n", encoding="utf-8")
        return root

    def test_the_date_decides_not_the_prefix(self, tmp_path):
        """A whole-name sort lets the variable infix decide, and it is already ambiguous.

        The glob admits ``…INTELLIGENCE*CONTINUATION_HANDOFF_…`` and this tree
        holds both a ``_CLAUDE_`` and a plain prefix. ``'L' < 'O'``, so a newer
        ``_CLAUDE_`` doc loses to an older plain one and every operator prompt
        cites a stale handoff.
        """
        root = self._research(tmp_path, self._NEW, self._OLD)
        assert pw.latest_handoff(root) == f"research/{self._NEW}"

    def test_a_v2_infix_does_not_win_on_letters(self, tmp_path):
        newer = "BIOPHARMA_SEASONALITY_INTELLIGENCE_CONTINUATION_HANDOFF_2026-08-06.md"
        older = "BIOPHARMA_SEASONALITY_INTELLIGENCE_V2_CONTINUATION_HANDOFF_2026-08-01.md"
        root = self._research(tmp_path, newer, older)
        assert pw.latest_handoff(root) == f"research/{newer}"

    def test_no_handoff_at_all_falls_back_to_the_pinned_doc(self, tmp_path):
        root = self._research(tmp_path)
        assert pw.latest_handoff(root) == pw._HANDOFF_FALLBACK


class TestPublicContainment:
    #: Everything the watch carries that must never reach a ``site/`` page.
    PRIVATE_TOKENS = (
        "operator_prompt",
        "handoff",
        "program_watch",
        "biocatalyst",
        "event_clock",
        "spa_reality_check",
        "synapse",
        "build_prophet",
    )

    #: The ONLY fields the public template may reach for. Two integers, a flag,
    #: and one plain ISO date. Pinning the attribute set closes the VALUE
    #: channel that a token grep over the template source cannot see: a private
    #: string can only be printed through a field that is both returned and
    #: referenced, and neither side may grow without this test going red.
    PUBLIC_FIELDS = {"available", "registered", "graded", "next_close"}

    def test_public_context_carries_only_counts(self):
        """The template context is two integers, a flag, and a date — nothing else."""
        from scripts.build_measurement import build_seasonality_forward_record

        record = build_seasonality_forward_record()
        assert set(record) == self.PUBLIC_FIELDS
        assert isinstance(record["registered"], int)
        assert isinstance(record["graded"], int)
        assert record["next_close"] is None or re.fullmatch(
            r"\d{4}-\d{2}-\d{2}", record["next_close"]
        )
        blob = json.dumps(record).lower()
        for token in self.PRIVATE_TOKENS:
            assert token not in blob

    def test_the_template_reaches_for_no_other_field(self):
        """The value channel, pinned structurally rather than by wording."""
        tpl = (REPO_ROOT / "templates" / "measurement.html.j2").read_text(encoding="utf-8")
        referenced = set(re.findall(r"seasonality_record\.(\w+)", tpl))
        assert referenced, "the forward-record block is gone from the template"
        extra = referenced - self.PUBLIC_FIELDS
        assert not extra, (
            f"measurement.html.j2 reads seasonality_record fields that are not in the "
            f"public contract: {sorted(extra)} — the watch payload is full of operator "
            "prompts, doc paths and module names, and this page is served anonymously"
        )

    def test_unreadable_ledger_renders_unavailable_not_zero(self, tmp_path, monkeypatch):
        """A zero would read as a measurement; "we could not check" is not a measurement."""
        import scripts.build_measurement as bm

        monkeypatch.setattr(bm, "ROOT", tmp_path)
        record = bm.build_seasonality_forward_record()
        assert record["available"] is False

    def test_a_partially_parseable_ledger_is_not_published(self, tmp_path, monkeypatch):
        """``available: True`` covers any file that OPENS — including a corrupt one.

        A truncated ledger publishes a confident undercount: one surviving row of
        28 renders "1 seasonal window on the record" with nothing saying 27 were
        lost, and a wholly unparseable file renders "0 · 0" — the exact reading
        the unavailable branch exists to prevent.
        """
        import scripts.build_measurement as bm

        _write(tmp_path, pw.LEDGER_PATH, _register("A:2026:1-30", "2026-09-01") + "\n<<<junk>>>\n")
        monkeypatch.setattr(bm, "ROOT", tmp_path)
        record = bm.build_seasonality_forward_record()
        assert record["available"] is False, "a partial parse is not a count"
        assert record["registered"] == 0

    def test_a_wholly_unparseable_ledger_is_not_published_as_zeros(self, tmp_path, monkeypatch):
        import scripts.build_measurement as bm

        _write(tmp_path, pw.LEDGER_PATH, "<<<junk>>>\nnot json\n")
        monkeypatch.setattr(bm, "ROOT", tmp_path)
        assert bm.build_seasonality_forward_record()["available"] is False

    def test_closeouts_are_not_published_as_scored(self, tmp_path, monkeypatch):
        """The public "scored so far" must mean the same thing the repo means."""
        import scripts.build_measurement as bm

        _write(
            tmp_path,
            pw.LEDGER_PATH,
            "\n".join(
                [
                    _register("A:2026:1-30", "2026-01-30"),
                    _register("B:2026:1-30", "2026-08-28"),
                    _grade("A:2026:1-30", status="ungradable_missing_prices"),
                ]
            )
            + "\n",
        )
        monkeypatch.setattr(bm, "ROOT", tmp_path)
        record = bm.build_seasonality_forward_record()
        assert record["available"] is True
        assert record["registered"] == 2
        assert record["graded"] == 0, "a close-out with no prices was published as scored"
        assert record["next_close"] == "2026-08-28"

    def test_template_line_never_prints_a_bare_zero_when_unavailable(self):
        tpl = (REPO_ROOT / "templates" / "measurement.html.j2").read_text(encoding="utf-8")
        assert "seasonality_record.available" in tpl, "the unavailable branch is gone"
        for token in self.PRIVATE_TOKENS:
            assert token not in tpl.lower(), f"{token!r} reached the public template"

    def test_the_zero_arrives_with_its_interpretation(self):
        """Doctrine Law 3: a Tier-1 number arrives with the sentence saying what it means.

        A bare "0 scored so far" cannot be told apart from "nothing works" by the
        reader it is written for. The interpreting fact — a window has to close
        before it can be scored, and when the earliest one closes — is public-safe
        (a date; no study name, no path, no slug) and was being withheld to the
        private artifact.
        """
        tpl = (REPO_ROOT / "templates" / "measurement.html.j2").read_text(encoding="utf-8")
        block = tpl.split('class="mh-fwd"', 1)[1].split("</p>", 1)[0]
        assert "seasonality_record.graded == 0" in block, (
            "the zero-state branch is gone — a bare 0 is decoration, not a measurement"
        )
        assert "seasonality_record.next_close" in block
        assert "has to close before it can be scored" in block
        assert "收官后才能打分" in block, "the ZH half lost the interpreting clause"


class TestRenderedPageContainment:
    """The leak gate over the ARTIFACT, not the source.

    Grepping the template catches a private LITERAL; it cannot catch a private
    string arriving through a value. ``site/measurement.html`` is tracked, so
    this runs in any checkout.
    """

    PAGE = REPO_ROOT / "site" / "measurement.html"

    #: Scoped to what THIS change could leak. Deliberately not the template's
    #: token list: "handoff" and "biocatalyst" both appear in the shared nav
    #: include on every product page and predate this work.
    LEAK_TOKENS = (
        "operator_prompt",
        "program_watch",
        "event_clock",
        "spa_reality_check",
        "nw_forward_ledger",
        "build_prophet",
        "build_stock_seasonality",
        "seasonality_record",
        "ungradable_missing_prices",
        "grade_status",
        "CONTINUATION_HANDOFF",
    )

    def test_no_private_token_reached_the_built_page(self):
        assert self.PAGE.exists(), f"{self.PAGE} is tracked and must be in this checkout"
        html = self.PAGE.read_text(encoding="utf-8")
        for token in self.LEAK_TOKENS:
            assert token not in html, (
                f"{token!r} reached site/measurement.html — the Calibration Lab is "
                "served to anonymous visitors"
            )


# ---------------------------------------------------------------------------
# the real repo
# ---------------------------------------------------------------------------


class TestAgainstThisRepo:
    def test_evaluate_reads_this_checkout_without_raising(self):
        payload = pw.evaluate(REPO_ROOT, asof=ASOF)
        assert [t["key"] for t in payload["tripwires"]] == EXPECTED_TRIPWIRES

    def test_the_repo_ledger_parses(self):
        counts = pw.read_ledger_counts(REPO_ROOT)
        assert counts["available"] is True
        assert counts["malformed"] == 0, "the committed forward ledger has unparseable lines"

    def test_handoff_doc_resolves_to_a_file_that_exists(self):
        doc = pw.latest_handoff(REPO_ROOT)
        assert (REPO_ROOT / doc).exists(), f"{doc} does not exist — the prompt cites a dead path"

    def test_registered_in_the_synapse_registry(self):
        text = (REPO_ROOT / "config" / "synapse.yml").read_text(encoding="utf-8")
        assert "data/seasonality/program_watch.json" in text
        assert "scripts/build_program_watch.py" in text

    def test_registered_in_the_dag(self):
        text = (REPO_ROOT / "config" / "dag.yml").read_text(encoding="utf-8")
        assert "scripts.build_program_watch" in text, "an unregistered builder never runs"

    def test_contract_id_stem_tracks_the_event_clocks_expectation(self):
        """The content matcher is only as good as the id it looks for.

        ``CONTRACT_ID_STEM`` is a literal here on purpose (this module is pure
        stdlib and must not drag the event clock's imports into the nightly
        watch), so the drift between the two is pinned by a test instead.
        """
        source = (REPO_ROOT / "engine" / "seasonality" / "event_clock.py").read_text(
            encoding="utf-8"
        )
        m = re.search(r'EXPECTED_PROJECTION_CONTRACT\s*=\s*"([^"]+)"', source)
        assert m, "EXPECTED_PROJECTION_CONTRACT is gone from event_clock.py"
        assert m.group(1).startswith(pw.CONTRACT_ID_STEM), (
            f"event_clock expects {m.group(1)!r} but the watch greps for "
            f"{pw.CONTRACT_ID_STEM!r} — the contract tripwire would miss the landing"
        )

    def test_the_real_contract_directory_does_not_false_fire(self):
        """Run the matcher over the 51 real contract files, not a hand-picked fixture.

        ``test_contract_match_is_not_a_hardcoded_filename`` parametrises names
        that all carry both tokens, so it proves only that the matcher is not
        ``== "<one string>"``. This exercises the producer's actual tree.
        """
        directory = REPO_ROOT / pw.BIOCATALYST_CONTRACTS_DIR
        assert directory.is_dir()
        matched, by_content, scanned = pw._contract_candidates(directory)
        assert len(scanned) >= 40, "the contract directory scan found almost nothing"
        assert matched == [], f"a non-seasonality contract fired the tripwire: {matched}"
        assert by_content == []

    def test_the_repo_ledger_grade_statuses_are_all_known(self):
        """An unknown ``grade_status`` would be silently bucketed as a close-out."""
        counts = pw.read_ledger_counts(REPO_ROOT)
        unknown = set(counts["grade_status_counts"]) - {
            pw.GRADED_STATUS,
            "ungradable_missing_prices",
        }
        assert not unknown, f"unrecognised grade_status in the forward ledger: {sorted(unknown)}"
