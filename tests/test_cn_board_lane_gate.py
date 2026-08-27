"""CN COLLECTION-LANE GATE — the board/ripening/audit/event-latch half of the CN_LANE fix.

WHAT SHIPPED DEAD
-----------------
Three CN sinks refused a write only when a lane was passed AND was not asia::

    if lane is not None and lane != "asia":      # china_standout_track.append_board
    if lane is not None and lane != "asia":      # china_standout_track.append_ripening
    if lane is not None and lane != "asia":      # cn_prophet_audit.run

and the one production caller resolved its lane with a PERMISSIVE default::

    _lane = os.environ.get("CN_LANE", "asia")    # scripts/build_china_library

Only .github/workflows/asia-close.yml sets ``CN_LANE`` ("the ONLY lane that may persist the
board ledger" — its own comment, line 276; line 278 says render lanes "leave CN_LANE
unset/non-asia so china_standout_track.append_board refuses"). So every other lane resolved
to the string "asia" and the refusal could not fire on any run — doubly dead, once at the
resolver and once at each sink. daily.yml (`git add data/`) and weekly.yml (`git add data/
reports/ site/`) both run scripts.build_china_library and both COMMIT ``data/``.

WHY IT MATTERS. The board store is keep-FIRST per (date, ticker, board_definition): the
first lane to write a date OWNS it — its ranks and its ``own_market_regime``, which stays
null forever when the regime row was not written in that lane, because no later nightly may
correct a kept row. The T2 event latch is worse: a fired conjunction may never be un-fired,
so a render lane running mid-CN-session could latch a conjunction computed on a partial bar.

WHAT THIS FILE PINS
-------------------
§1 RESOLVER CENSUS   — AST: exactly ONE CN_LANE environment read exists in
                       scripts/build_china_library.py, it lives in ``_collection_lane``, and
                       it carries no default. This reds on a permissive re-introduction
                       ANYWHERE in the file, which is the strongest pin here.
§2 FAIL-CLOSED SINKS — unit pins on a writable fixture: asia writes (the witness), an
                       unnamed lane and a named non-asia lane refuse.
§3 PRODUCTION PATH   — the env-driven shape ``main()`` actually uses, over unset / "" /
                       daily / weekly / asia. This is the path the old tests never took:
                       they hand-fed ``lane=`` and stayed green while the gate did nothing.
§4 CALL-SHAPE SCAN   — every CN-sink call in engine/ + scripts/ names its lane. The gate is
                       fail-closed now, so a FORGOTTEN ``lane=`` silently stops persisting
                       instead — equally wrong and invisible without this scan.
§5 EVENT-LATCH SITE  — the third gate, pinned by content (executing main() is not an option).

HERMETIC IN DATA AND IN TIME. Every store is redirected under ``tmp_path`` and
``lib.store.read_status`` is stubbed empty, so ``session_status`` takes its documented
"no run_status — assumed settled" branch instead of reading the repo's panel stamp. Nothing
on these write paths consults the wall clock, so ``BOARD_DATE`` below is a fixture key, not
a date that can rot: it is only ever compared to itself as a keep-first store key.

Run: python3 -m pytest tests/test_cn_board_lane_gate.py -q
"""
from __future__ import annotations

import ast
from pathlib import Path

import pandas as pd
import pytest

from lib import config, store
from engine import china_standout_track as t
from engine import cn_prophet_audit as cpa
from scripts import build_china_library as bcl


ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "scripts" / "build_china_library.py"

# A pure fixture key. See the module docstring: no code under test reads a clock, so this
# constant is compared only against itself (the keep-first store key) and cannot rot.
BOARD_DATE = "2026-08-05"
TICKER = "300363.SZ"

# The lanes production actually presents. asia-close.yml sets CN_LANE=asia; daily.yml and
# weekly.yml set nothing at all; "" is the empty-but-present shape a shell export leaves.
REFUSING_LANES = [None, "", "daily", "weekly", "render", "intraday", "ASIA"]


def _board_rows() -> list[dict]:
    return [{"ticker": TICKER, "price": 10.0, "board_definition": "cn_prophet_v2",
             "lane": "featured"}]


def _ripening_rows() -> list[dict]:
    return [{"ticker": TICKER, "reasons": ["macd_cross_imminent"], "imminence": 2,
             "w2_stoch": 18.0, "zone": "READY"}]


def _n_board() -> int:
    p = t._store_path()  # noqa: SLF001 — read-only path accessor
    return 0 if not p.exists() else len(pd.read_parquet(p))


def _n_ripening() -> int:
    p = t._ripening_path()  # noqa: SLF001 — read-only path accessor
    return 0 if not p.exists() else len(pd.read_parquet(p))


@pytest.fixture(autouse=True)
def cn_store(monkeypatch, tmp_path):
    """Every CN store under tmp_path; the price panel stamp stubbed as SETTLED.

    ``session_status`` reads run_status.json from the REPO root (config.ROOT), not from
    data_dir, so an unstubbed read would let a live partial-session stamp refuse the asia
    witness and turn every refusal assertion below vacuous. The empty dict takes the
    documented "no run_status — assumed settled" branch.
    """
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(store, "read_status", lambda: {})
    return tmp_path


# ===========================================================================
# 1. RESOLVER CENSUS — one CN_LANE read, in one function, with no default
# ===========================================================================
# The AST is the lens on purpose: the builder's own docstrings quote the defective form
# `os.environ.get("CN_LANE", "asia")` verbatim, so a grep-based census would either miss
# real reads or trip over prose. Only executable Call/Subscript nodes count here.

def _is_os_environ(node: ast.AST) -> bool:
    """``os.environ`` (or a bare ``environ`` from ``from os import environ``)."""
    if isinstance(node, ast.Attribute):
        return node.attr == "environ"
    return isinstance(node, ast.Name) and node.id == "environ"


def _is_cn_lane(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and node.value == "CN_LANE"


def _cn_lane_env_reads(tree: ast.AST) -> list[ast.AST]:
    """Every executable environment read of CN_LANE in ``tree`` (both access forms)."""
    hits: list[ast.AST] = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "get" and _is_os_environ(node.func.value)
                and node.args and _is_cn_lane(node.args[0])):
            hits.append(node)
        elif (isinstance(node, ast.Subscript) and _is_os_environ(node.value)
                and _is_cn_lane(node.slice)):
            hits.append(node)
    return hits


def test_the_builder_reads_cn_lane_in_exactly_one_place():
    """One resolver. A second read is how the two halves of this defect drifted apart:
    the latch path resolved fail-closed while the board path four screens away kept its
    "asia" default, and both looked correct in isolation.
    """
    tree = ast.parse(BUILDER.read_text(encoding="utf-8"), filename=str(BUILDER))
    reads = _cn_lane_env_reads(tree)
    where = [f"line {n.lineno}" for n in reads]
    assert len(reads) == 1, (
        "scripts/build_china_library.py must read CN_LANE exactly once, inside "
        f"_collection_lane(); found {len(reads)} reads at {where}")

    resolver = next((n for n in ast.walk(tree)
                     if isinstance(n, ast.FunctionDef) and n.name == "_collection_lane"), None)
    assert resolver is not None, "the fail-closed resolver _collection_lane() is gone"
    inside = _cn_lane_env_reads(resolver)
    assert len(inside) == 1, (
        f"the CN_LANE read at {where} sits outside _collection_lane() — every CN "
        "collection gate must resolve through the one fail-closed resolver")


def test_the_resolver_carries_no_permissive_default():
    """``os.environ.get("CN_LANE", "asia")`` is the defect itself: with a default, EVERY
    lane is the asia lane and no sink can ever refuse. Only the one-argument form passes.
    """
    tree = ast.parse(BUILDER.read_text(encoding="utf-8"), filename=str(BUILDER))
    read = _cn_lane_env_reads(tree)[0]
    assert isinstance(read, ast.Call), "os.environ['CN_LANE'] would raise on a render lane"
    assert not read.keywords and len(read.args) == 1, (
        "the CN_LANE read carries a default — "
        f"`{ast.unparse(read)}`; a default makes every unset lane the asia lane")


@pytest.mark.parametrize("raw", [None, "", "   "])
def test_an_unnamed_lane_resolves_to_none(monkeypatch, raw):
    """Behavioural half of the census: unset, empty and whitespace all mean "no lane"."""
    if raw is None:
        monkeypatch.delenv("CN_LANE", raising=False)
    else:
        monkeypatch.setenv("CN_LANE", raw)
    assert bcl._collection_lane() is None  # noqa: SLF001 — the resolver under test


def test_the_asia_lane_resolves_to_asia(monkeypatch):
    """WITNESS: the resolver is not simply always-None."""
    monkeypatch.setenv("CN_LANE", "asia")
    assert bcl._collection_lane() == "asia"  # noqa: SLF001


# ===========================================================================
# 2. FAIL-CLOSED SINKS — with a writable witness on the SAME fixture
# ===========================================================================

def test_the_asia_lane_persists_a_board():
    """WITNESS FIRST. Every refusal below is only meaningful because this write lands —
    otherwise an unwritable fixture would prove the gate for the wrong reason.
    """
    assert t.append_board(_board_rows(), asof=BOARD_DATE, lane="asia") == 1
    assert _n_board() == 1


@pytest.mark.parametrize("lane", REFUSING_LANES)
def test_a_lane_that_is_not_asia_never_persists_a_board(lane):
    """FAIL-CLOSED. ``lane=None`` is in this list on purpose: it used to take the
    permissive branch, and it is what the one production call site effectively passed.
    """
    assert t.append_board(_board_rows(), asof=BOARD_DATE, lane=lane) == 0
    assert _n_board() == 0, f"lane={lane!r} wrote to the keep-first board store"


def test_the_asia_lane_persists_ripening():
    """WITNESS for the ripening store, on the same fixture as its refusals."""
    assert t.append_ripening(_ripening_rows(), asof=BOARD_DATE, lane="asia") == 1
    assert _n_ripening() == 1


@pytest.mark.parametrize("lane", REFUSING_LANES)
def test_a_lane_that_is_not_asia_never_persists_ripening(lane):
    assert t.append_ripening(_ripening_rows(), asof=BOARD_DATE, lane=lane) == 0
    assert _n_ripening() == 0, f"lane={lane!r} wrote to the ripening store"


def test_the_refusal_names_the_lane(caplog):
    """A silent refusal is indistinguishable from an empty board in the nightly log."""
    with caplog.at_level("INFO"):
        t.append_board(_board_rows(), asof=BOARD_DATE, lane="weekly")
        t.append_ripening(_ripening_rows(), asof=BOARD_DATE, lane=None)
    text = caplog.text
    assert "'weekly'" in text and "None" in text, (
        f"the refusals must name the lane they refused; got: {text!r}")


@pytest.mark.parametrize("lane", REFUSING_LANES)
def test_the_prophet_audit_refuses_every_lane_but_asia(lane):
    """The audit refuses BEFORE reading any store, so it needs no fixture of its own.

    Its asia witness is deliberately not rebuilt here — standing up the board store, the
    price frames and the benchmark it needs is disproportionate, and
    tests/test_cn_prophet_audit.py::TestWriteGates already drives the asia path (and
    carries its own written=True witness beside the unnamed-lane refusal).
    """
    res = cpa.run(asof=BOARD_DATE, lane=lane)
    assert res["written"] is False
    assert res["reason"] == f"lane={lane} (not asia)", (
        f"the refusal must name the lane it refused; got {res['reason']!r}")
    assert not cpa.latest_path().exists() and not cpa.forward_log_path().exists()


# ===========================================================================
# 3. THE PRODUCTION CALL PATH — env in, store out, nothing hand-fed
# ===========================================================================
# main() does exactly this: `_lane = _collection_lane()` once, then passes `lane=_lane` to
# append_board / append_ripening / cn_prophet_audit.run. The old tests hand-fed `lane=`,
# which is why they stayed green while the gate was unreachable in production.

def _drive(monkeypatch, cn_lane: str | None) -> tuple[int, int]:
    """Set the ONE variable the workflows set, then take main()'s shape end to end."""
    if cn_lane is None:
        monkeypatch.delenv("CN_LANE", raising=False)
    else:
        monkeypatch.setenv("CN_LANE", cn_lane)
    _lane = bcl._collection_lane()  # noqa: SLF001 — the resolver main() calls
    t.append_board(_board_rows(), asof=BOARD_DATE, lane=_lane)
    t.append_ripening(_ripening_rows(), asof=BOARD_DATE, lane=_lane)
    return _n_board(), _n_ripening()


@pytest.mark.parametrize("cn_lane", [None, "", "daily", "weekly"],
                         ids=["unset", "empty", "daily", "weekly"])
def test_a_render_lane_commits_nothing_to_the_cn_stores(monkeypatch, cn_lane):
    """daily.yml and weekly.yml run this builder with CN_LANE unset and `git add data/`.

    Under the old default they resolved to "asia" and wrote the keep-first stores, so
    scheduling order decided which lane owned a published date.
    """
    assert _drive(monkeypatch, cn_lane) == (0, 0)


def test_the_asia_nightly_is_the_lane_that_commits(monkeypatch):
    """asia-close.yml sets CN_LANE=asia — byte-identical behaviour to before the fix."""
    assert _drive(monkeypatch, "asia") == (1, 1)


# ===========================================================================
# 4. CALL-SHAPE SCAN — every CN-sink write names its lane
# ===========================================================================
# Scoped by RECEIVER, not by function name: engine/board_ledger.append_board is the HK/CA
# sink with its own env-var gate and no lane parameter, and scripts/build_canada.py and
# scripts/build_hk_library.py call it without one. A name-only scan would flag them.

_CN_SINKS = {"engine.china_standout_track": {"append_board", "append_ripening"},
             "engine.cn_prophet_audit": {"run"}}


def _module_aliases(tree: ast.AST, dotted: str) -> set[str]:
    """Local names bound to ``dotted`` by any import form in this file."""
    pkg, _, leaf = dotted.rpartition(".")
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name == dotted:
                    names.add(a.asname or a.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module == pkg:
            for a in node.names:
                if a.name == leaf:
                    names.add(a.asname or a.name)
    return names


def _unlaned_calls(src: str, label: str) -> list[str]:
    """``label:lineno`` for every CN-sink call in ``src`` that does not name a lane."""
    tree = ast.parse(src, filename=label)
    wanted: dict[str, set[str]] = {}
    for dotted, attrs in _CN_SINKS.items():
        for alias in _module_aliases(tree, dotted):
            wanted.setdefault(alias, set()).update(attrs)
    if not wanted:
        return []
    out: list[str] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)):
            continue
        if node.func.attr not in wanted.get(node.func.value.id, ()):
            continue
        if not any(kw.arg == "lane" for kw in node.keywords):
            out.append(f"{label}:{node.lineno}")
    return out


def _laned_calls(src: str) -> int:
    """How many CN-sink calls the scan judged COMPLIANT (the witness half)."""
    tree = ast.parse(src)
    wanted: dict[str, set[str]] = {}
    for dotted, attrs in _CN_SINKS.items():
        for alias in _module_aliases(tree, dotted):
            wanted.setdefault(alias, set()).update(attrs)
    n = 0
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.attr in wanted.get(node.func.value.id, ())
                and any(kw.arg == "lane" for kw in node.keywords)):
            n += 1
    return n


def test_every_production_cn_collection_write_names_its_lane():
    """The defect was a CALL SITE resolver, not a policy — so pin the call sites.

    Fail-closed changes the failure mode rather than removing it: a forgotten ``lane=``
    now stops persisting silently. This scan is what makes that visible.
    """
    offenders: list[str] = []
    laned = 0
    for path in sorted([*(ROOT / "engine").rglob("*.py"), *(ROOT / "scripts").rglob("*.py")]):
        src = path.read_text(encoding="utf-8")
        # Cheap pre-filter on the MODULE names, not the attribute names: "run" appears in
        # nearly every file here, and parsing all of engine/ + scripts/ costs ~30s.
        if not any(d.rpartition(".")[2] in src for d in _CN_SINKS):
            continue
        rel = str(path.relative_to(ROOT))
        offenders += _unlaned_calls(src, rel)
        laned += _laned_calls(src)
    assert offenders == [], (
        "CN collection sink called without lane=; the gates are fail-closed, so these 
        f"writes no-op silently and the store stops advancing: {offenders}")
    # WITNESS: the scan can SEE calls — it found the production ones and judged them
    # compliant (4x append_board, 1x append_ripening, 1x cn_prophet_audit.run in the
    # builder alone). Without this, deleting every call would also pass.
    assert laned >= 6, f"the scan resolved only {laned} CN-sink calls — check the aliasing"


def test_the_call_shape_scan_can_see_a_missing_lane():
    """CALIBRATION. A detector never shown catching the defect is not a detector.

    Also pins the scoping: the HK/CA ``board_ledger.append_board`` shares the name and
    must NOT be flagged, or this scan would red on scripts/build_canada.py forever.
    """
    bad = ("from engine import china_standout_track\n"
           "china_standout_track.append_board(rows, asof=d)\n")
    assert _unlaned_calls(bad, "synthetic.py") == ["synthetic.py:2"]

    aliased = ("from engine import cn_prophet_audit as _a\n"
               "_a.run(asof=d)\n")
    assert _unlaned_calls(aliased, "synthetic.py") == ["synthetic.py:2"]

    other_module = ("from engine import board_ledger\n"
                    "board_ledger.append_board(rows, 'HK', asof=d)\n")
    assert _unlaned_calls(other_module, "synthetic.py") == []

    compliant = ("from engine import china_standout_track\n"
                 "china_standout_track.append_board(rows, asof=d, lane=_lane)\n")
    assert _unlaned_calls(compliant, "synthetic.py") == []


# ===========================================================================
# 5. THE EVENT-LATCH RECORD SITE — the third gate, pinned by content
# ===========================================================================

def test_the_t2_event_latch_records_only_on_the_asia_lane():
    """A fired confluence event may never be un-fired, so recording one off-lane is the
    least reversible write in this file — and it is unreachable from a test without
    running the whole CN build. Pin the two lines that decide it.

    ``None == "asia"`` is False, so an unnamed lane records nothing.
    """
    src = BUILDER.read_text(encoding="utf-8")
    assert "_latch_lane = _collection_lane()" in src, (
        "the T2 event-latch lane must come from the fail-closed resolver")
    assert 'record=(_latch_lane == "asia")' in src, (
        "the EventLatch record flag must still be the asia-lane comparison")


# ===========================================================================
# 6. DEEP-OHLC FRESHNESS — enrichment may never regress the settled board clock
# ===========================================================================

def _freshness_close(end: str, n: int = 320) -> pd.Series:
    idx = pd.bdate_range(end=end, periods=n)
    return pd.Series(range(n), index=idx, dtype=float)


def _freshness_deep(end: str, n: int = 320) -> pd.DataFrame:
    close = _freshness_close(end, n)
    return pd.DataFrame({"close": close, "high": close * 1.01}, index=close.index)


def test_deep_ohlc_never_regresses_a_fresher_cache_close(monkeypatch):
    """The deep store enriches high/low; it cannot move the Prophet price clock backward."""
    cache_close = _freshness_close("2026-08-27")
    deep = _freshness_deep("2026-08-26")
    monkeypatch.setattr(bcl.store, "read", lambda group, ticker: deep)
    universe = [("000001.SZ", cache_close, None, "Ping An", "Banks")]

    upgraded = bcl._overlay_deep_ohlc(universe, "china_stocks", min_rows=300)

    assert upgraded == 0
    assert universe[0][1].index.max() == cache_close.index.max()
    assert universe[0][2] is None


def test_deep_ohlc_still_upgrades_when_it_is_equally_fresh(monkeypatch):
    """Same-session deep OHLC keeps its real high/low enrichment authority."""
    cache_close = _freshness_close("2026-08-27")
    deep = _freshness_deep("2026-08-27")
    monkeypatch.setattr(bcl.store, "read", lambda group, ticker: deep)
    universe = [("000001.SZ", cache_close, None, "Ping An", "Banks")]

    upgraded = bcl._overlay_deep_ohlc(universe, "china_stocks", min_rows=300)

    assert upgraded == 1
    assert universe[0][1].index.max() == deep.index.max()
    pd.testing.assert_series_equal(universe[0][2], deep["high"])
