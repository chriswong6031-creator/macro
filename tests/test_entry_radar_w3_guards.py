"""Live Entry Radar PR-3 (W3) — boundary, write-discipline and determinism guards.

WHAT THIS SUITE IS FOR
----------------------
W3 is the first Radar wave that COMPUTES.  That changes which mistakes are
possible, so the W2 fences are re-asked at the new surface and three new ones are
added:

  PIT-21  no W3 module imports ``engine.technicals`` — the §4 indicator-core law
          (two incompatible RSI families live in this repo and they differ exactly
          where crosses flip)
  PIT-22  no W3 module imports the Prophet / entry-gate chain or the two adjacent
          display organs
  PIT-23  no W3 module or suite imports an outcome grader, a forward-return
          evaluator, a qledger grading path, a TrialLedger result reader, or a
          per-name performance store — and no W3 identifier is outcome-shaped
  PIT-24  every W3 reading and event carries an all-false authority block
  PIT-25  the same frozen inputs produce byte-identical canonical output, across
          repeated execution AND across ``PYTHONHASHSEED`` variation
  PIT-26  no W3 module names a ``data/`` path or opens a writer

plus the `DNR:KILL-WASHOUT-TURN` fence (no expression path from higher-timeframe
depth to candidate authority) and the `DNR:KILL-OUTCOME-AUDITION` fence (no
per-name threshold table anywhere).

EVERY SCANNER HERE IS CONTROL-TESTED.  A guard that has never fired is a guard
whose absence nobody would notice, so each detector is run against a planted
defect first.  The docstring-exclusion trick is inherited from the W2 suite: a
module that DOCUMENTS its refusal must not trip the scanner that enforces it.

Nothing here reads ``data/``, ``site/`` or the network.
"""
from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from engine.entry_radar import c5_adapter as c5
from engine.entry_radar import challengers as ch
from engine.entry_radar import four_hour as fh
from engine.entry_radar import indicator_core as ic
from engine.entry_radar.readings import DetectorReading, canonical_readings

from tests.test_entry_radar_w3_c1c2_pit import (
    TICKER,
    daily_history,
    load_fixture,
    observation_path,
)

ROOT = Path(__file__).resolve().parents[1]
RADAR_DIR = ROOT / "engine" / "entry_radar"
TESTS = ROOT / "tests"

#: The five modules W3 adds.  Named explicitly so the guards below cannot go
#: vacuous through a glob that matches nothing.
W3_MODULES = ("indicator_core.py", "readings.py", "challengers.py", "four_hour.py",
              "c5_adapter.py")

#: The six suites W3 adds.
W3_SUITES = ("test_entry_radar_w3_detectors.py", "test_entry_radar_w3_c1c2_pit.py",
             "test_entry_radar_w3_c3_4h_pit.py", "test_entry_radar_w3_c4.py",
             "test_entry_radar_w3_c5.py", "test_entry_radar_w3_guards.py")

#: PIT-22 + PIT-21.  The Prophet/entry-gate chain, the two ADJACENT display organs
#: (§2 — different grain, different product), the wrong RSI family, the durable
#: -write gate, and the Terminal package.
PROTECTED_MODULE_PREFIXES = (
    "engine.entry_signal",
    "engine.signal_gate",
    "engine.confluence_tiers",
    "engine.signal_quality",
    "engine.washout_turn",
    "engine.mtf_upturn",
    "engine.prophet_",
    "engine.technicals",
    "engine.stock_identity",
    "engine.setups",
    "engine.stock_personality",
    "engine.marketing.hot_tape",
    "engine.ledger_lane",
    "signal_layer",
)

#: PIT-23.  Outcome machinery, by module.  Importing any of these from a W3 module
#: or suite would put a forward return one attribute access away from a detector
#: that must not have seen one (contract §18 A5.0: PR-5 owns the first read).
OUTCOME_MODULE_PREFIXES = (
    "engine.qledger",
    "engine.trial_ledger",
    "engine.forward_dist",
    "engine.pick_forward_dist",
    "engine.grading",
    "engine.grading_stats",
    "engine.operator_grading",
    "engine.track_scoring",
    "engine.rule_experiments",
    "engine.plan_ledger",
    "engine.ledger_lane",
    "engine.backtest",
)

#: PIT-23, the identifier half.  Matched on underscore-delimited word boundaries so
#: ``domain`` never reads as ``mae``.
OUTCOME_TOKENS = ("forward_return", "fwd_return", "mfe", "mae", "false_start",
                  "hit_rate", "win_rate", "top_k", "rank_ic", "best_variant",
                  "excess_vs", "outcome", "pnl", "sharpe")

#: This file names every banned token AS DATA, so it is excluded from the
#: identifier sweep it defines.  Its own imports are still swept (below) — the
#: exclusion buys the guard a vocabulary, not an exemption.
IDENTIFIER_SWEEP_EXCLUDED = "test_entry_radar_w3_guards.py"

WRITE_CALLS = frozenset({
    "write_text", "write_bytes", "to_parquet", "to_csv", "to_json", "to_pickle",
    "makedirs", "mkdir", "unlink", "rmtree", "savefig",
})

FILESYSTEM_MODULES = frozenset({"os", "shutil", "tempfile", "boto3", "s3fs",
                                "requests", "httpx", "urllib", "socket"})

_TICKER_KEY = re.compile(r"^[A-Z]{1,5}$")


# ---------------------------------------------------------------------------
# scanners (shared shapes, control-tested below)
# ---------------------------------------------------------------------------

def _imports_in(text: str, *, name: str = "<probe>") -> set[str]:
    tree = ast.parse(text, filename=name)
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module:
                found.add(module)
            for alias in node.names:
                found.add(f"{module}.{alias.name}" if module else alias.name)
    return found


def _offenders(names: set[str], prefixes: tuple[str, ...]) -> list[str]:
    return sorted(n for n in names
                  if any(n == p or n.startswith(p) for p in prefixes))


def _docstring_ids(tree: ast.AST) -> set[int]:
    out: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)):
            body = getattr(node, "body", None) or []
            if body and isinstance(body[0], ast.Expr) and \
                    isinstance(body[0].value, ast.Constant) and \
                    isinstance(body[0].value.value, str):
                out.add(id(body[0].value))
    return out


def _identifiers_in(text: str, *, name: str = "<probe>") -> set[str]:
    """Every identifier a file defines or reads.  Docstrings are NOT identifiers."""
    tree = ast.parse(text, filename=name)
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            found.add(node.id)
        elif isinstance(node, ast.Attribute):
            found.add(node.attr)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            found.add(node.name)
        elif isinstance(node, ast.arg):
            found.add(node.arg)
        elif isinstance(node, ast.keyword) and node.arg:
            found.add(node.arg)
    return found


def _outcome_identifiers(names: set[str]) -> list[str]:
    hits = []
    for name in names:
        low = name.lower()
        for token in OUTCOME_TOKENS:
            if re.search(rf"(^|_){re.escape(token)}(_|$)", low):
                hits.append(name)
                break
    return sorted(set(hits))


def _data_path_literals(text: str, *, name: str = "<probe>") -> list[str]:
    tree = ast.parse(text, filename=name)
    docstrings = _docstring_ids(tree)
    return [node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
            and id(node) not in docstrings and "data/" in node.value]


def _writers_in(text: str, *, name: str = "<probe>") -> list[str]:
    tree = ast.parse(text, filename=name)
    found: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id == "open":
            mode = ""
            if len(node.args) > 1 and isinstance(node.args[1], ast.Constant):
                mode = str(node.args[1].value)
            for kw in node.keywords:
                if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
                    mode = str(kw.value.value)
            if any(ch_ in mode for ch_ in "wax+"):
                found.append(f"open(mode={mode!r})")
        elif isinstance(func, ast.Attribute) and func.attr in WRITE_CALLS:
            found.append(func.attr)
    found += sorted(n for n in _imports_in(text, name=name)
                    if n.split(".")[0] in FILESYSTEM_MODULES)
    return found


def _per_name_tables(text: str, *, name: str = "<probe>") -> list[str]:
    """Dict literals whose keys are all ticker-shaped and whose values are numbers.

    That shape IS `DNR:KILL-OUTCOME-AUDITION`'s construction — a per-name
    threshold/gate/rank table.  Ticker identity may key memory and continuity;
    it may never key a number the detector reads.
    """
    tree = ast.parse(text, filename=name)
    hits: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict) or not node.keys:
            continue
        keys = [k.value for k in node.keys
                if isinstance(k, ast.Constant) and isinstance(k.value, str)]
        if len(keys) != len(node.keys) or not keys:
            continue
        if not all(_TICKER_KEY.match(k) for k in keys):
            continue
        numeric = [v for v in node.values
                   if isinstance(v, ast.Constant) and isinstance(v.value, (int, float))]
        if numeric:
            hits.append(",".join(sorted(keys)))
    return hits


# ---------------------------------------------------------------------------
# the guards are pointed at real files
# ---------------------------------------------------------------------------

def test_the_guard_file_lists_are_not_empty():
    present = {p.name for p in RADAR_DIR.rglob("*.py")}
    assert set(W3_MODULES) <= present, sorted(set(W3_MODULES) - present)
    assert all((TESTS / suite).exists() for suite in W3_SUITES)


# ---------------------------------------------------------------------------
# PIT-21 / PIT-22 — the import fence
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("source,expected", [
    ("import engine.technicals", "engine.technicals"),
    ("from engine.technicals import rsi", "engine.technicals"),
    ("def f():\n    import engine.technicals as t\n", "engine.technicals"),
    ("from engine import washout_turn", "engine.washout_turn"),
    ("from engine.prophet_us import x", "engine.prophet_us"),
    ("from engine.entry_signal import gate as g", "engine.entry_signal"),
    ("import engine.mtf_upturn", "engine.mtf_upturn"),
])
def test_CONTROL_the_protected_import_scanner_catches_a_planted_import(source, expected):
    assert expected in _offenders(_imports_in(source), PROTECTED_MODULE_PREFIXES)


@pytest.mark.parametrize("name", W3_MODULES)
def test_PIT21_PIT22_no_w3_module_imports_a_protected_module(name):
    text = (RADAR_DIR / name).read_text(encoding="utf-8")
    assert _offenders(_imports_in(text, name=name), PROTECTED_MODULE_PREFIXES) == []


@pytest.mark.parametrize("name", W3_SUITES)
def test_PIT21_PIT22_no_w3_suite_imports_a_protected_module(name):
    text = (TESTS / name).read_text(encoding="utf-8")
    offenders = _offenders(_imports_in(text, name=name), PROTECTED_MODULE_PREFIXES)
    assert offenders == [], f"{name} imports {offenders}"


def test_the_ATR_pair_is_the_ONLY_route_to_engine_technicals_and_it_is_disclosed():
    """``engine.stock_technicals`` transitively LOADS ``engine.technicals``.

    Recorded rather than hidden.  The §4 law forbids Radar COMPUTING with that
    family; the direct-import fence above is intact, and the parity test below
    proves Radar's ATR is that module's ATR rather than a second implementation.
    """
    text = (RADAR_DIR / "indicator_core.py").read_text(encoding="utf-8")
    imported = _imports_in(text, name="indicator_core.py")
    assert "engine.stock_technicals" in imported
    assert not [n for n in imported if n.startswith("engine.technicals")]
    assert "TRANSITIVE-IMPORT NOTE" in text, "the note must stay in the docstring"
    for name in W3_MODULES:
        if name == "indicator_core.py":
            continue
        assert "engine.stock_technicals" not in _imports_in(
            (RADAR_DIR / name).read_text(encoding="utf-8"), name=name), \
            f"{name} must reach ATR through indicator_core, not around it"


def test_radar_ATR_is_the_house_ATR_and_the_pit_shift_is_one_bar():
    from engine.stock_technicals import atr as house_atr

    rng = np.random.default_rng(11)
    close = pd.Series(100 + np.cumsum(rng.normal(0, 1, 200)))
    high, low = close * 1.01, close * 0.99
    assert ic.atr14(high, low, close).equals(house_atr(high, low, close, 14))
    shifted = ic.atr14_prior_confirmed(high, low, close)
    assert shifted.equals(ic.atr14(high, low, close).shift(1))
    # and the shift is EQUIVALENT to cutting the frame — the form W3 actually uses
    cut = ic.atr14(high.iloc[:-1], low.iloc[:-1], close.iloc[:-1])
    assert ic.last_finite(cut) == pytest.approx(float(shifted.iloc[-1]))


def test_the_indicator_family_is_canon_and_nothing_else():
    assert ic.INDICATOR_CORE["module"] == "engine.canon"
    assert ic.INDICATOR_CORE["rsi_len"] == 14 and ic.INDICATOR_CORE["stoch_len"] == 14
    assert ic.INDICATOR_CORE["macd_slow"] == 60
    for spec in (ch.C1_SPEC, ch.C2_SPEC, ch.C4_SPEC, fh.C3_SPEC):
        assert spec["indicator_core"] == ic.INDICATOR_CORE


# ---------------------------------------------------------------------------
# PIT-23 — no outcome access, in code or in tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("source,expected", [
    ("import engine.qledger", "engine.qledger"),
    ("from engine.trial_ledger import TrialLedger", "engine.trial_ledger"),
    ("from engine import forward_dist", "engine.forward_dist"),
    ("def f():\n    from engine.grading import grade\n", "engine.grading"),
    ("import engine.track_scoring as ts", "engine.track_scoring"),
])
def test_CONTROL_the_outcome_import_scanner_catches_a_planted_import(source, expected):
    assert expected in _offenders(_imports_in(source), OUTCOME_MODULE_PREFIXES)


@pytest.mark.parametrize("name", W3_MODULES + W3_SUITES)
def test_PIT23_nothing_in_w3_imports_an_outcome_module(name):
    path = (RADAR_DIR / name) if name in W3_MODULES else (TESTS / name)
    offenders = _offenders(_imports_in(path.read_text(encoding="utf-8"), name=name),
                           OUTCOME_MODULE_PREFIXES)
    assert offenders == [], f"{name} imports outcome machinery {offenders}"


@pytest.mark.parametrize("source,expected", [
    ("forward_return = 1", "forward_return"),
    ("def compute_mfe(x): return x", "compute_mfe"),
    ("row.mae_63", "mae_63"),
    ("false_start_rate = 0", "false_start_rate"),
    ("best_variant = 'c2a'", "best_variant"),
])
def test_CONTROL_the_outcome_identifier_scanner_catches_a_planted_name(source, expected):
    assert expected in _outcome_identifiers(_identifiers_in(source))


def test_CONTROL_the_outcome_identifier_scanner_is_not_trigger_happy():
    """``domain`` is not ``mae``; ``image`` is not ``mfe``."""
    assert _outcome_identifiers(_identifiers_in(
        "domain = 1\nimage = 2\nmaefile = 3\nrecovery_count = 4\ntopaz = 5")) == []


@pytest.mark.parametrize(
    "name", W3_MODULES + tuple(s for s in W3_SUITES if s != IDENTIFIER_SWEEP_EXCLUDED))
def test_PIT23_no_w3_identifier_is_outcome_shaped(name):
    path = (RADAR_DIR / name) if name in W3_MODULES else (TESTS / name)
    hits = _outcome_identifiers(_identifiers_in(path.read_text(encoding="utf-8"),
                                                name=name))
    assert hits == [], f"{name} defines/reads outcome-shaped identifier(s) {hits}"


def test_the_identifier_sweep_exclusion_is_narrow_and_named():
    """The excluded file is THIS one, and its own imports are still swept."""
    assert IDENTIFIER_SWEEP_EXCLUDED == Path(__file__).name
    assert _offenders(_imports_in(Path(__file__).read_text(encoding="utf-8")),
                      OUTCOME_MODULE_PREFIXES) == []


# ---------------------------------------------------------------------------
# PIT-26 — no durable writer, no data/ path
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("source", [
    'PATH = "data/entry_radar/forward.parquet"',
    'def f():\n    return {"out": "data/live/x.json"}\n',
])
def test_CONTROL_the_data_path_scanner_fires_on_a_planted_literal(source):
    assert _data_path_literals(source)


@pytest.mark.parametrize("source", [
    'open("x.jsonl", "w")',
    'open("x.jsonl", mode="a")',
    'from pathlib import Path\nPath("x").write_text("y")',
    'import os\nos.makedirs("x")',
    'import boto3',
    'import requests',
])
def test_CONTROL_the_writer_scanner_fires_on_a_planted_writer(source):
    assert _writers_in(source)


def test_CONTROL_the_writer_scanner_does_not_fire_on_a_read():
    assert _writers_in('from pathlib import Path\nPath("x").read_text()') == []
    assert _writers_in('"a".replace("a", "b")') == []


@pytest.mark.parametrize("name", W3_MODULES)
def test_PIT26_no_w3_module_names_a_data_path_or_opens_a_writer(name):
    text = (RADAR_DIR / name).read_text(encoding="utf-8")
    assert _data_path_literals(text, name=name) == [], f"{name} names a data/ path"
    assert _writers_in(text, name=name) == [], (
        f"{name} contains a durable writer or a network client; PR-5's reconciler is "
        f"the only durable data/ writer and it is gated by "
        f"ledger_lane.nightly_advance_enabled()")


# ---------------------------------------------------------------------------
# DNR:KILL-WASHOUT-TURN and DNR:KILL-OUTCOME-AUDITION
# ---------------------------------------------------------------------------

def test_no_w3_module_carries_a_per_name_threshold_table():
    for name in W3_MODULES:
        text = (RADAR_DIR / name).read_text(encoding="utf-8")
        assert _per_name_tables(text, name=name) == [], \
            f"{name} carries a ticker-keyed number table (DNR:KILL-OUTCOME-AUDITION)"


def test_CONTROL_the_per_name_table_scanner_fires_on_a_planted_table():
    assert _per_name_tables('THRESH = {"NVDA": 18.0, "TSLA": 22.5}')
    assert _per_name_tables('{"KRUS": 3}')
    # and does not fire on ordinary string maps
    assert _per_name_tables('{"early_dot": "washout_early_watch"}') == []
    assert _per_name_tables('{"rsi_len": 14}') == []


def test_the_c2_evaluators_read_no_higher_timeframe_field():
    """`DNR:KILL-WASHOUT-TURN`: depth is context and never reaches a turn predicate.

    Checked at AST level on the six evaluator functions themselves, so a future
    variant that reached for ``d3.recent_washout`` fails here rather than in a
    review.
    """
    source = (RADAR_DIR / "challengers.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    functions = {node.name: node for node in ast.walk(tree)
                 if isinstance(node, ast.FunctionDef)}
    banned = {"recent_washout", "d2", "d3", "mtf", "depth", "recovery_count",
              "c4_snapshot", "washed", "drawdown"}
    for variant in ch.C2_VARIANTS:
        key = "_eval_" + variant.split("_")[0]
        assert key in functions, key
        names = _identifiers_in(ast.unparse(functions[key]))
        assert not [n for n in names if n.lower() in banned], \
            f"{key} reads a higher-timeframe field"
    # CONTROL: the same check on a planted evaluator must fail.
    planted = _identifiers_in(
        "def _eval_c2x(state, obs):\n    return obs.k > obs.d and obs.d3.recent_washout")
    assert [n for n in planted if n.lower() in banned] != []


def _depth_conjunctions(text: str, *, name: str = "<probe>") -> list[str]:
    """``... and <something>.recent_washout ...`` — the killed interaction form."""
    hits: list[str] = []
    for node in ast.walk(ast.parse(text, filename=name)):
        if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.And):
            names = {n.attr for n in ast.walk(node) if isinstance(n, ast.Attribute)}
            if "recent_washout" in names:
                hits.append(ast.unparse(node))
    return hits


def test_CONTROL_the_depth_conjunction_scanner_fires_on_the_killed_form():
    assert _depth_conjunctions("cand = state.turn and state.recent_washout")
    assert _depth_conjunctions("if d3.recent_washout and k > d:\n    pass")
    assert _depth_conjunctions("x = state.turn and state.k > 20") == []


def test_c4_appears_in_no_firing_expression():
    """No ``turn && recent_washout -> candidate`` expression exists anywhere."""
    for name in W3_MODULES:
        text = (RADAR_DIR / name).read_text(encoding="utf-8")
        assert _depth_conjunctions(text, name=name) == [], \
            f"{name} conjoins recent_washout — the killed interaction form"
    assert ch.STRATIFICATION_ONLY_IDS == frozenset({ch.C4_DETECTOR_ID})


# ---------------------------------------------------------------------------
# PIT-24 — authority is all-false on everything W3 produces
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def w3_products():
    fixture = load_fixture()
    path = observation_path(fixture)
    c1 = ch.run_c1(path)
    c2 = ch.run_c2(path, c1.episode)
    session = date.fromisoformat(fixture["tape_sessions"][1])
    c4 = ch.c4_reading(
        ch.c4_snapshot(ticker=TICKER, daily=daily_history(fixture),
                       market_session=session),
        observed_at=c1.episode.candidate_at)
    return c1, c2, c4


def test_PIT24_every_w3_reading_and_event_is_authority_all_false(w3_products):
    c1, c2, c4 = w3_products
    readings = list(c1.readings) + list(c2.readings) + [c4]
    events = list(c1.events) + list(c2.events)
    assert len(readings) > 1000 and events
    for record in readings:
        assert record.authority == {k: False for k in record.authority}
    for event in events:
        assert event.authority == {k: False for k in event.authority}
        assert event.scored_authority is False
        assert all(v == "radar_derived" for v in event.field_origin.values())
        assert event.family_first_available["kind"] == "era_fence"


def test_PIT24_a_reading_claiming_authority_is_refused_at_construction():
    from engine.entry_radar.readings import ReadingError

    with pytest.raises(ReadingError, match="claims authority"):
        DetectorReading(ticker="ZZTOP", detector_id="C1_1D_LIVE_WASHOUT@1",
                        detector_version=1, detector_spec_hash="x",
                        observed_at="2026-06-24T14:00:00Z",
                        market_session="2026-06-24", availability="provisional",
                        bar_state="provisional",
                        authority={"can_rank": True, "can_size": False,
                                   "can_gate": False, "can_originate_signal": False,
                                   "can_escalate": False})


def test_a_reading_may_not_grow_a_strength_number():
    from engine.entry_radar.readings import ReadingError

    with pytest.raises(ReadingError, match="strength/priority"):
        DetectorReading(ticker="ZZTOP", detector_id="C1_1D_LIVE_WASHOUT@1",
                        detector_version=1, detector_spec_hash="x",
                        observed_at="2026-06-24T14:00:00Z",
                        market_session="2026-06-24", availability="provisional",
                        bar_state="provisional", features={"detector_score": 91})


def test_the_reading_field_list_is_exactly_the_A5_0_list():
    """`mastermind.entry_detector_reading.v1` is frozen at the amendment's names."""
    from engine.entry_radar.readings import (
        READING_FIELDS,
        ReadingError,
        reading_dataclass_fields,
    )

    assert READING_FIELDS == (
        "schema", "ticker", "detector_id", "detector_version", "detector_spec_hash",
        "variant", "observed_at", "market_session", "availability", "source_bar_time",
        "source_bar_known_at", "bar_state", "data_vintage", "features",
        "condition_met", "evidence_refs", "authority")
    assert set(READING_FIELDS) == set(reading_dataclass_fields())
    with pytest.raises(ReadingError, match="unknown reading field"):
        DetectorReading.from_dict({"ticker": "ZZTOP", "detector_score": 91})


def test_an_unavailable_reading_may_not_carry_a_boolean():
    from engine.entry_radar.readings import ReadingError

    with pytest.raises(ReadingError, match="null law"):
        DetectorReading(ticker="ZZTOP", detector_id="C1_1D_LIVE_WASHOUT@1",
                        detector_version=1, detector_spec_hash="x",
                        observed_at="2026-06-24T14:00:00Z",
                        market_session="2026-06-24", availability="unavailable",
                        bar_state="provisional", condition_met=False)


# ---------------------------------------------------------------------------
# PIT-25 — determinism
# ---------------------------------------------------------------------------

def test_PIT25_repeated_execution_is_byte_identical(w3_products):
    c1, c2, _c4 = w3_products
    fixture = load_fixture()
    path = observation_path(fixture)
    again_c1 = ch.run_c1(path)
    again_c2 = ch.run_c2(path, again_c1.episode)
    assert canonical_readings(again_c1.readings) == canonical_readings(c1.readings)
    assert canonical_readings(again_c2.readings) == canonical_readings(c2.readings)
    assert [e.event_id for e in again_c2.events] == [e.event_id for e in c2.events]


DETERMINISM_PROBE = """
import hashlib, json, sys
from datetime import date
sys.path.insert(0, %(root)r)
from tests.test_entry_radar_w3_c1c2_pit import load_fixture, observation_path
from engine.entry_radar import challengers as ch
from engine.entry_radar.readings import canonical_readings
fixture = load_fixture()
path = observation_path(fixture)
c1 = ch.run_c1(path)
c2 = ch.run_c2(path, c1.episode)
blob = canonical_readings(list(c1.readings) + list(c2.readings))
ids = ",".join(sorted(str(e.event_id) for e in list(c1.events) + list(c2.events)))
print(hashlib.sha256((blob + ids).encode()).hexdigest())
"""


def test_PIT25_output_is_stable_across_PYTHONHASHSEED(tmp_path):
    """Two probes, two seeds, in SUBPROCESSES — the only way to vary the hash seed.

    Dict iteration order is the classic way a "deterministic" pipeline becomes
    seed-dependent, and ``PYTHONHASHSEED`` cannot be changed inside a running
    interpreter.  Both seeds run inside ONE test so a ``-k`` selection or a
    randomised order can never leave the comparison unmade.
    """
    script = tmp_path / "probe.py"
    script.write_text(DETERMINISM_PROBE % {"root": str(ROOT)}, encoding="utf-8")
    digests = {}
    for seed in ("0", "12345"):
        out = subprocess.run([sys.executable, str(script)], capture_output=True,
                             text=True, cwd=str(ROOT), timeout=600,
                             env={**os.environ, "PYTHONHASHSEED": seed})
        assert out.returncode == 0, out.stderr[-2000:]
        digests[seed] = out.stdout.strip().splitlines()[-1]
        assert len(digests[seed]) == 64
    assert len(set(digests.values())) == 1, f"hash-seed dependent output: {digests}"


def test_the_spec_hashes_are_stable_across_processes(tmp_path):
    script = tmp_path / "spec_probe.py"
    script.write_text(
        "import sys; sys.path.insert(0, %r)\n"
        "from engine.entry_radar.detectors import DETECTORS\n"
        "print(sorted((k, v.spec_hash) for k, v in DETECTORS.items()))\n" % str(ROOT),
        encoding="utf-8")
    runs = []
    for seed in ("0", "999"):
        out = subprocess.run([sys.executable, str(script)], capture_output=True,
                             text=True, cwd=str(ROOT), timeout=600,
                             env={**os.environ, "PYTHONHASHSEED": seed})
        assert out.returncode == 0, out.stderr[-2000:]
        runs.append(out.stdout.strip())
    assert runs[0] == runs[1]


# ---------------------------------------------------------------------------
# purity — the engine holds no clock and no ambient state
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", W3_MODULES)
def test_no_w3_module_reads_an_environment_variable_or_the_wall_clock(name):
    text = (RADAR_DIR / name).read_text(encoding="utf-8")
    tree = ast.parse(text, filename=name)
    bad: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in {"getenv", "environ"}:
                bad.append(node.func.attr)
            if node.func.attr in {"now", "today", "utcnow"}:
                bad.append(node.func.attr)
    assert bad == [], f"{name} reads ambient state {bad}; every input is passed in"


def test_c5_mints_no_event_type_at_all():
    assert "build_radar_native_event" not in (
        RADAR_DIR / "c5_adapter.py").read_text(encoding="utf-8"), \
        "C5 references the preserved watch events; it never mints (A5.8)"
    assert c5.C5_SPEC["implementation"].startswith("interpretation of the two")


# ---------------------------------------------------------------------------
# 2026-08-14 adversarial-review regressions (W3-3, W3-4)
# ---------------------------------------------------------------------------

def _module_numeric_constants(path: Path) -> dict[str, float]:
    """Module-level ALL-CAPS constants bound to a plain number."""
    out: dict[str, float] = {}
    for node in ast.parse(path.read_text(encoding="utf-8"), filename=path.name).body:
        targets = (node.targets if isinstance(node, ast.Assign)
                   else [node.target] if isinstance(node, ast.AnnAssign) else [])
        for target in targets:
            if not (isinstance(target, ast.Name) and target.id.isupper()):
                continue
            value = node.value
            if isinstance(value, ast.Constant) and \
                    isinstance(value.value, (int, float)) and \
                    not isinstance(value.value, bool):
                out[target.id] = float(value.value)
    return out


def _spec_numbers() -> set[float]:
    from engine.entry_radar.detectors import DETECTORS

    found: set[float] = set()

    def walk(node):
        if isinstance(node, dict):
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)
        elif isinstance(node, bool):
            return
        elif isinstance(node, (int, float)):
            found.add(float(node))

    for record in DETECTORS.values():
        walk(record.spec)
    return found


#: W3-4 allowlist: module-level numeric constants that are NOT firing-relevant and
#: therefore need not ride a spec hash.  EMPTY on purpose — every constant in the
#: four W3 modules currently reaches a spec by value.  A new row needs a one-line
#: reason, and "it was inconvenient" is not one.
NON_FIRING_CONSTANTS: dict[str, str] = {}


def test_W3_4_every_numeric_constant_rides_a_spec_hash_by_value():
    """W3-4: firing-relevant constants lived OUTSIDE the hashes.

    ``ATR_LEN`` and ``MINUTE_BAR_SECONDS`` decided what fired while sitting in
    prose, and the §10 re-arm numbers were hand-typed into a sentence beside the
    constants they were supposed to describe — a spec that can lie with a stable
    hash.  The sweep below is the mechanical version of "carry it by value".
    """
    numbers = _spec_numbers()
    missing: list[str] = []
    for module in ("indicator_core.py", "challengers.py", "four_hour.py",
                   "c5_adapter.py"):
        for name, value in sorted(_module_numeric_constants(RADAR_DIR / module).items()):
            if name in NON_FIRING_CONSTANTS:
                continue
            if value not in numbers:
                missing.append(f"{module}:{name}={value}")
    assert missing == [], \
        f"constant(s) decide behaviour but ride no spec hash: {missing}"


def test_W3_4_CONTROL_the_constant_sweep_fires_on_a_planted_unhashed_constant(tmp_path):
    planted = tmp_path / "planted.py"
    planted.write_text("SOME_THRESHOLD = 1234567\nOTHER = 'x'\n", encoding="utf-8")
    constants = _module_numeric_constants(planted)
    assert constants == {"SOME_THRESHOLD": 1234567.0}
    assert 1234567.0 not in _spec_numbers()


def test_W3_4_the_named_constants_are_the_ones_that_moved():
    assert ic.INDICATOR_CORE["atr_len"] == ic.ATR_LEN == 14
    assert ch.C1_SPEC["minute_bar_seconds"] == ch.MINUTE_BAR_SECONDS == 60
    assert ch.C2_SPEC["sampling"]["minute_bar_seconds"] == ch.MINUTE_BAR_SECONDS
    assert ch.C2_SPEC["sampling"]["interval_minutes"] == ch.SAMPLE_INTERVAL_MINUTES
    rearm = ch.C1_SPEC["rearm_law"]
    assert rearm["confirmed_k_floor"] == ch.REARM_K_FLOOR == 50
    assert rearm["consecutive_sessions"] == ch.REARM_K_SESSIONS == 2
    assert rearm["max_sessions"] == ch.REARM_MAX_SESSIONS == 15
    assert fh.C3_SPEC["arm_expiry_sessions"] == fh.C3_ARM_EXPIRY_SESSIONS == 15
    assert "non-positive" in ch.C2_SPEC["variants"]["c2f_rebound_atr"]  # W3-13


def test_W3_3_no_reading_in_ANY_w3_suite_cites_an_event_from_its_own_future():
    """W3-3, swept across every W3 detector that mints or references an event.

    The invariant is one line — a reading may only cite what already existed —
    and it is checked on C1/C2 (Radar-minted), C3 (Radar-minted) and C5
    (Terminal-preserved) in one place, because a per-detector version of it is
    how one detector ends up exempt.
    """
    from engine.entry_radar import c5_adapter as c5_mod
    from engine.entry_radar.g0_adapter import g0_events
    from engine.entry_radar.indicator_ingest import load_slice
    from engine.entry_radar.entry_events import EntryEventStore

    checked = 0

    fixture = load_fixture()
    path = observation_path(fixture)
    c1 = ch.run_c1(path)
    c2 = ch.run_c2(path, c1.episode)
    clocks = {str(e.event_id): e.signal_ts for e in list(c1.events) + list(c2.events)}
    for reading in list(c1.readings) + list(c2.readings):
        for ref in reading.evidence_refs:
            assert clocks[ref] <= reading.observed_at
            checked += 1

    store = EntryEventStore()
    g0_events(load_slice(ROOT / "tests" / "fixtures" / "entry_radar" /
                         "NFLX.slice.json"), store)
    watch_clocks = {str(e.event_id): (e.signal_known_ts or e.signal_ts)
                    for e in store.events()}
    for reading in c5_mod.run_c5(store).readings:
        for ref in reading.evidence_refs:
            assert watch_clocks[ref] <= reading.observed_at
            checked += 1

    assert checked > 100, "the sweep must actually inspect citations"
