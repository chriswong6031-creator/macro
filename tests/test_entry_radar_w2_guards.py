"""Live Entry Radar PR-2 (W2) — boundary guards and mutation guards.

TWO JOBS.

**Boundary.**  W2 adds four runtime modules to `engine/entry_radar/`, and every
one of them must stay on Radar's side of the §1/§2/§16 line: Radar reads
ARTIFACTS, never gate code.  ``tests/test_entry_radar_w1.py`` already scans
import LINES; this suite re-asks the question at AST level (so an aliased or
function-local import cannot slip past a line filter) and widens the list with
``engine.technicals`` — the §4 indicator-core law, which binds here precisely
because W2 consumes an indicator artifact and computing one would be leaving W2's
scope entirely.

**Mutation.**  Four invariants whose SILENT removal would leave the rest of the
suite green.  Each is written to fail if the invariant is deleted rather than to
restate a passing assertion: the population union (delete one channel and F1/F4
still pass, because those names have no promotions), the suppression invariant
(the emitter never emits a dot in both channels, so nothing else notices if the
union starts double-counting), content-drift detection at the store door, and
the frozen G0 spec hash.

Nothing here reads ``data/``, ``site/`` or the network.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from engine.entry_radar.detectors import DETECTORS
from engine.entry_radar.entry_events import (
    AppendOnlyViolation,
    EntryEvent,
    EntryEventStore,
)
from engine.entry_radar.g0_adapter import (
    G0_DETECTOR_ID,
    WATCH_PROMOTED,
    G0IntegrityError,
    g0_population,
    g0_spec_hash,
)
from engine.entry_radar.indicator_ingest import EXPECTED_SOURCE_HASH, load_slice

ROOT = Path(__file__).resolve().parents[1]
RADAR_DIR = ROOT / "engine" / "entry_radar"
FIXTURES = ROOT / "tests" / "fixtures" / "entry_radar"

#: The four modules W2 adds.  Named explicitly so the write-discipline guard
#: below cannot go vacuous through a glob that matches nothing.
W2_MODULES = ("entry_events.py", "indicator_ingest.py", "g0_adapter.py", "detectors.py")

RADAR_SOURCES = sorted(RADAR_DIR.rglob("*.py"))

#: Protected module prefixes.  The first six are the Prophet/entry-gate chain and
#: the two ADJACENT display organs (§2: different grain, different product — name
#: similarity is not identity).  ``engine.technicals`` is the §4 indicator-core
#: law.  ``engine.ledger_lane`` is the PR-5 durable-write gate: a module that
#: cannot reach the gate cannot bypass it.
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


def _imported_names(path: Path) -> set[str]:
    """Every module path a file imports, AST-level (aliases and locals included)."""
    return _imports_in(path.read_text(encoding="utf-8"), name=str(path))


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


def _protected_offenders(names: set[str]) -> list[str]:
    return sorted(n for n in names
                  if any(n == prefix or n.startswith(prefix)
                         for prefix in PROTECTED_MODULE_PREFIXES))


def test_guard_sources_are_not_empty():
    """A file-list guard that matches nothing passes for the wrong reason."""
    assert len(RADAR_SOURCES) >= 10, RADAR_SOURCES
    present = {p.name for p in RADAR_SOURCES}
    assert set(W2_MODULES) <= present, sorted(set(W2_MODULES) - present)


@pytest.mark.parametrize("source,expected", [
    ("import engine.washout_turn", "engine.washout_turn"),
    ("from engine import mtf_upturn", "engine.mtf_upturn"),
    ("from engine.prophet_us import x", "engine.prophet_us"),
    ("def f():\n    import engine.technicals as t\n", "engine.technicals"),
    ("from engine.entry_signal import gate as g", "engine.entry_signal"),
])
def test_CONTROL_the_import_scanner_catches_a_planted_protected_import(source, expected):
    """The detector, control-tested.  A scanner that never fires proves nothing.

    Function-local and aliased forms are included because those are exactly the
    shapes a LINE-based scan (W1's) can be talked past.
    """
    offenders = _protected_offenders(_imports_in(source))
    assert expected in offenders, f"scanner missed {source!r}"


@pytest.mark.parametrize("path", RADAR_SOURCES, ids=lambda p: p.name)
def test_no_radar_module_imports_a_protected_module_ast(path):
    """Non-interference, at AST level: Radar reads artifacts, never gate code."""
    offenders = _protected_offenders(_imported_names(path))
    assert offenders == [], f"{path.name} imports protected module(s) {offenders}"


@pytest.mark.parametrize("name", W2_MODULES)
def test_w2_modules_compute_no_indicator(name):
    """§4: W2 consumes an artifact.  Computing an oscillator means leaving W2.

    pandas/numpy are the tell — the emitter already did the math and Radar's job
    is to carry its output across the boundary without recomputing any of it.
    """
    imported = _imported_names(RADAR_DIR / name)
    numeric = sorted(n for n in imported
                     if n.split(".")[0] in {"pandas", "numpy", "scipy", "talib"})
    assert numeric == [], f"{name} imports {numeric}; if you are computing RSI you "\
                          f"have left the W2 scope (§4 indicator-core law)"


# ---------------------------------------------------------------------------
# write discipline — no data/ path, no writer, in the W2 runtime modules
# ---------------------------------------------------------------------------

#: Unambiguous durable-write calls.  ``replace``/``rename`` are deliberately NOT
#: here: as ATTRIBUTE names they collide with ``str.replace``, and the atomic-
#: rename shape they would catch needs a temp file first — which ``open(mode=w)``
#: and ``write_text`` already catch.  A guard that reds on an innocent string
#: operation gets weakened by the first person it inconveniences.
WRITE_CALLS = frozenset({
    "write_text", "write_bytes", "to_parquet", "to_csv", "to_json", "to_pickle",
    "makedirs", "mkdir", "unlink", "rmtree", "savefig",
})

#: Modules whose presence in a W2 file means a filesystem writer arrived by
#: another door.  ``pathlib`` is allowed: ``load_slice`` READS a slice path.
FILESYSTEM_MODULES = frozenset({"os", "shutil", "tempfile", "boto3", "s3fs"})


def _docstring_nodes(tree: ast.AST) -> set[int]:
    """ids of the Constant nodes that ARE docstrings (module/class/function)."""
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


def _data_path_literals(text: str, *, name: str = "<probe>") -> list[str]:
    """Non-docstring string literals naming a ``data/`` path.

    Docstrings are excluded on purpose — they say ``data/`` precisely because
    they document the refusal.
    """
    tree = ast.parse(text, filename=name)
    docstrings = _docstring_nodes(tree)
    return [node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
            and id(node) not in docstrings and "data/" in node.value]


def _writers_in(text: str, *, name: str = "<probe>") -> list[str]:
    """Durable-writer calls and filesystem-module imports."""
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
            if any(ch in mode for ch in "wax+"):
                found.append(f"open(mode={mode!r})")
        elif isinstance(func, ast.Attribute) and func.attr in WRITE_CALLS:
            found.append(func.attr)
    found += sorted(n for n in _imports_in(text, name=name)
                    if n.split(".")[0] in FILESYSTEM_MODULES)
    return found


@pytest.mark.parametrize("name", W2_MODULES)
def test_w2_modules_name_no_data_path_and_open_no_writer(name):
    """Contract §7.3: PR-2 code writes no ``data/`` path and opens no writer."""
    text = (RADAR_DIR / name).read_text(encoding="utf-8")
    assert _data_path_literals(text, name=name) == [], \
        f"{name} names a data/ path in code"
    assert _writers_in(text, name=name) == [], (
        f"{name} contains a durable writer; PR-5's reconciler is the only durable "
        f"data/ writer and it is gated by ledger_lane.nightly_advance_enabled()")


@pytest.mark.parametrize("source", [
    'PATH = "data/entry_radar/events.jsonl"',
    'def f():\n    return {"out": "data/live/x.json"}\n',
])
def test_CONTROL_the_data_path_scanner_fires_on_a_planted_literal(source):
    assert _data_path_literals(source), f"scanner missed {source!r}"


@pytest.mark.parametrize("source", [
    'open("x.jsonl", "w")',
    'open("x.jsonl", mode="a")',
    'from pathlib import Path\nPath("x").write_text("y")',
    'import os\nos.makedirs("x")',
    'import shutil',
])
def test_CONTROL_the_writer_scanner_fires_on_a_planted_writer(source):
    assert _writers_in(source), f"scanner missed {source!r}"


def test_CONTROL_the_writer_scanner_does_not_fire_on_a_read():
    assert _writers_in('from pathlib import Path\nPath("x").read_text()') == []
    assert _writers_in('"a".replace("a", "b")') == []


# ---------------------------------------------------------------------------
# MUTATION GUARD 1 — the store detects content drift at a stable address
# ---------------------------------------------------------------------------

def test_MUTATION_a_mutated_dict_bypass_is_caught_by_append_validation():
    """Round-trip an event through its dict form, change a NON-address field, and
    try to re-append.  The address is unchanged, so only the store's content
    comparison can catch it.  If that comparison is removed the second event
    silently replaces the first and every other test still passes.
    """
    sl = load_slice(FIXTURES / "NFLX.slice.json")
    store = EntryEventStore()
    from engine.entry_radar.g0_adapter import g0_events
    g0_events(sl, store)

    original = next(e for e in store.events() if e.family == "washout_early_watch")
    payload = original.to_dict()
    payload["context"] = {**payload["context"], "sweep_low": -999.0}
    forged = EntryEvent.from_dict(payload)

    assert forged.event_id == original.event_id, "the address must be unchanged"
    assert forged.content_key != original.content_key
    with pytest.raises(AppendOnlyViolation):
        store.append(forged)
    assert store.get(str(original.event_id)).context["sweep_low"] == \
        original.context["sweep_low"]


# ---------------------------------------------------------------------------
# MUTATION GUARD 2 — the population really is a UNION of both channels
# ---------------------------------------------------------------------------

def _micro_slice(signals, *, early_dots=()):
    return {"indicator": {
        "schema": "mastermind.indicator/v1", "symbol": "ZZTOP",
        "as_of": "2026-08-13T00:00:00Z", "signal_era": "gc_v2_wo2", "timeframe": "3D",
        "early_dots": list(early_dots), "signals": list(signals), "warnings": [],
        "state": {}, "bar_quality": "synthetic", "meta": {},
        "indicator": {"source_hash": EXPECTED_SOURCE_HASH, "params": {}},
    }}


def _watch(ts, known_ts, subtype):
    return {"type": "BOTTOM_WATCH", "subtype": subtype, "ts": ts, "known_ts": known_ts,
            "quality": ("washout_early_watch" if subtype == "early_dot"
                        else "washout_trigger_watch"),
            "washout_ctx": {}, "trigger_ts": ts, "trigger_known_ts": known_ts,
            "sweep_low": 1.0, "atr14": 0.1, "stop_level": 0.9,
            "risk_basis": "daily_ohlc_atr14", "scored": False}


def test_MUTATION_a_dot_living_only_in_the_watch_stream_is_still_population():
    """Kills a "read early_dots only" regression.

    A1.1: the artifact's side channel carries only UNPROMOTED dots, so a
    side-channel-only reader loses exactly the deep-washout cohort.  On NVDA and
    TSLA that loss is invisible (no promotions ≥2025) — this synthetic slice makes
    it visible with a population of one.
    """
    sl = load_slice(_micro_slice([_watch("2026-07-01", "2026-07-03", "early_dot")],
                                 early_dots=[]))
    dots = g0_population(sl)
    assert [d.ts for d in dots] == ["2026-07-01"]
    assert dots[0].source_channel == WATCH_PROMOTED
    assert dots[0].known_ts == "2026-07-03"
    assert dots[0].washout_evidence == "promoted"


def test_MUTATION_side_channel_only_dot_is_still_population():
    """The complementary half — neither channel may be dropped."""
    sl = load_slice(_micro_slice([], early_dots=["2026-07-02"]))
    dots = g0_population(sl)
    assert [d.ts for d in dots] == ["2026-07-02"]
    assert dots[0].known_ts is None


# ---------------------------------------------------------------------------
# MUTATION GUARD 3 — the suppression invariant is asserted, not assumed
# ---------------------------------------------------------------------------

def test_MUTATION_a_date_in_both_channels_raises_rather_than_double_counting():
    """The emitter removes promoted dots from the side channel, so BOTH is
    impossible on a healthy artifact — which is exactly why nothing else would
    notice if it started happening.  A quiet de-duplication here would hide the
    day the suppression rule changed.
    """
    sl = load_slice(_micro_slice(
        [_watch("2026-07-01", "2026-07-03", "early_dot")],
        early_dots=["2026-07-01"]))
    with pytest.raises(G0IntegrityError, match="BOTH"):
        g0_population(sl)


def test_MUTATION_a_blocked_trigger_sharing_a_bar_with_a_dot_is_NOT_an_integrity_error():
    """A4.4's live specimen must stay lawful: only `early_dot` promotions are
    suppressed, so a blocked_trigger on a retained dot's bar is expected.
    """
    sl = load_slice(_micro_slice(
        [_watch("2026-07-01", "2026-07-03", "blocked_trigger")],
        early_dots=["2026-07-01"]))
    assert [d.ts for d in g0_population(sl)] == ["2026-07-01"]


# ---------------------------------------------------------------------------
# MUTATION GUARD 4 — the spec hash is frozen in three places at once
# ---------------------------------------------------------------------------

#: FROZEN literal.  Editing any value in ``g0_adapter.G0_SPEC`` changes this and
#: breaks this test on purpose: a detector's spec identity is what makes a result
#: attributable later, so a spec change must never be silent.
G0_SPEC_HASH_FROZEN = "9be89a8acc8b905c"


def test_MUTATION_g0_spec_hash_is_stable_and_matches_the_registry():
    assert g0_spec_hash() == G0_SPEC_HASH_FROZEN
    assert DETECTORS[G0_DETECTOR_ID].spec_hash == G0_SPEC_HASH_FROZEN
    assert g0_spec_hash() == g0_spec_hash(), "hash must not vary within a run"
    assert len(DETECTORS) == 1, "W2 registers exactly one detector"
