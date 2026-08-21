"""HK + Canada Prophet Shadow Substrate — K1-K14 + standing clauses.

research/PROPHET_SHADOW_CONTRACT_V1.md §6 is the binding test contract. Every
test below is named for the finding class it kills (Kn) and cites the F-number
of the adversarial review finding that motivated it. Each writer-exercising
kill carries a POSITIVE CONTROL arm (asserts the control wrote > 0 rows — a
lane-gated no-op passing every kill vacuously is exactly what F3 closes) and,
where the test concerns Lane A, a NON-VACUITY assertion (the fixture
challenger's order differs from the incumbent's — F2).
"""
from __future__ import annotations

import ast
import copy
import datetime as dt
import json
import re
import subprocess
import sys
import uuid
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine import board_ledger  # noqa: E402
from engine import board_shadow as bs  # noqa: E402
from lib import config  # noqa: E402


# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _isolated_store(tmp_path, monkeypatch):
    """Every test gets its own tmp data_dir and a CLEARED challenger registry
    (the registry is a module-level dict; a leak between tests would make one
    test's fixture challenger silently backstop another's positive control)."""
    data_root = tmp_path / "data"
    monkeypatch.setattr(config, "data_dir", lambda: data_root)
    bs.CHALLENGER_REGISTRY.clear()
    monkeypatch.delenv("CN_LANE", raising=False)
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    monkeypatch.delenv("US_LANE", raising=False)
    yield data_root
    bs.CHALLENGER_REGISTRY.clear()


def _lane_on(monkeypatch, market: str) -> None:
    if market.upper() == "HK":
        monkeypatch.setenv("CN_LANE", "asia")
        monkeypatch.delenv("COLLECT_LANE", raising=False)
    else:
        monkeypatch.setenv("COLLECT_LANE", "nightly")
        monkeypatch.delenv("CN_LANE", raising=False)


def _population() -> list[dict]:
    """4-name incumbent population, board_pos order AAA(1) BBB(2) CCC(3) DDD(4)."""
    return [
        {"ticker": "AAA", "group": "entry_open", "board_definition": "test_board_v1"},
        {"ticker": "BBB", "group": "entry_open", "board_definition": "test_board_v1"},
        {"ticker": "CCC", "group": "setting_up", "board_definition": "test_board_v1"},
        {"ticker": "DDD", "group": "watch", "board_definition": "test_board_v1"},
    ]


def _seed_board_ledger(monkeypatch, market: str, date: str, calls: list[dict]) -> None:
    """Write the incumbent board_ledger row set via the REAL append_board."""
    _lane_on(monkeypatch, market)
    n = board_ledger.append_board(copy.deepcopy(calls), market=market, asof=date)
    assert n > 0, "fixture setup: append_board must actually write rows"


def _reversed_rank_fn(calls: list[dict]) -> dict:
    """Adversarial fixture challenger (F2 non-vacuity): reverses the incumbent
    order exactly, so DDD scores highest and AAA lowest."""
    tickers = [c["ticker"] for c in calls if c.get("ticker")]
    order = list(reversed(tickers))
    return {
        tk: {"score_raw": float(len(order) - i), "score_conservative": float(len(order) - i) * 0.9}
        for i, tk in enumerate(order)
    }


def _register_adversarial(definition: str = "adv_challenger_v1") -> None:
    bs.register_challenger(definition, rank_fn=_reversed_rank_fn)


def _lane_a_frame(market: str) -> pd.DataFrame | None:
    return bs._read_own_store(bs._lane_a_path(market))


def _lane_b_frame(market: str) -> pd.DataFrame | None:
    return bs._read_own_store(bs._lane_b_path(market))


# ---------------------------------------------------------------------------
# K1 — zero-authority breach (byte-identity harness) + non-vacuity
# ---------------------------------------------------------------------------
def test_k1_ca_zero_authority_breach_and_non_vacuity(tmp_path, monkeypatch):
    """K1 CA leg (F1/F2). Byte-identity REGRESSION harness over everything
    DOWNSTREAM of the CA shadow call site, using the REAL production wiring
    function (scripts.build_canada._canada_board_ledger — the exact code path
    the contract wires the shadow call into), across four variants: shadow
    module absent / present-empty / present-with-adversarial-challenger
    (non-vacuous order) / present-with-a-mutating-writer.

    CORRECTED DOCSTRING (M5, review round 2): this test does NOT detect a
    removal of write_shadow's deep-copy, and was WRONGLY described as doing
    so in the original draft. Structural reason: `_canada_board_ledger`
    builds `calls` as brand-new dicts via `calls.append({"ticker": r.get(...),
    ...})` from `setups["buy"]` rows — `calls` and `setups["buy"]` never share
    row-dict identity in the first place, so a hostile challenger mutating
    `calls[0]` was never going to reach `setups["buy"][0]` regardless of
    board_shadow's own protections. What this test DOES genuinely verify is
    the byte-identity regression on setups["buy"]/["board_track"] (the JSON
    body that becomes canada_standouts.json) and
    data/board_ledger/ca_board.parquet across all four variants — a real and
    useful guard, just not the F1 aliasing kill. F1's actual load-bearing
    kill for a genuine aliasing/write-surface channel is the write-surface
    fence test below (m2, review round 2), which snapshots the filesystem
    itself rather than relying on an object graph that happens not to alias
    here. The template-rendered HTML pages named in the contract's identity
    set are NOT exercised here (see DEVIATIONS in the build packet) — a full
    render needs the live site template + data tree this sparse suite does
    not check out.
    """
    sys.path.insert(0, str(ROOT))
    from scripts import build_canada  # noqa: PLC0415

    def _run(*, absent: bool, register=None) -> tuple[bytes, bytes]:
        data_dir = tmp_path / f"run_{uuid.uuid4().hex}"
        site_dir = tmp_path / f"site_{uuid.uuid4().hex}"
        (site_dir / "factordata").mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(config, "data_dir", lambda: data_dir)
        # `_canada_board_ledger`'s track_ledger emit resolves its site path via
        # `Path(config.load()["storage"]["site_dir"])` — a CWD-relative path,
        # not `config.site_dir()` — so it must be redirected too, or this
        # harness would write into the real, committed site/factordata/
        # ca_track_ledger.json (MM_DATA_GUARD caught exactly this on first
        # draft of this test).
        monkeypatch.setattr(config, "load", lambda: {"storage": {"site_dir": str(site_dir)}})
        bs.CHALLENGER_REGISTRY.clear()
        _lane_on(monkeypatch, "CA")
        if register:
            register()
        if absent:
            monkeypatch.setitem(sys.modules, "engine.board_shadow", None)
        else:
            monkeypatch.delitem(sys.modules, "engine.board_shadow", raising=False)
            import engine.board_shadow  # noqa: F401,PLC0415 — re-import after delitem

        setups = {"buy": copy.deepcopy(_population())}
        latest = {"date": "2026-08-21"}
        health = build_canada._canada_board_ledger(setups, latest)
        assert not any(h.get("status") == "ERROR" for h in health), health

        board_path = data_dir / "board_ledger" / "ca_board.parquet"
        board_bytes = board_path.read_bytes() if board_path.exists() else b""
        artifact_bytes = json.dumps(setups, sort_keys=True, default=str).encode()
        return artifact_bytes, board_bytes

    baseline_artifact, baseline_board = _run(absent=True)
    empty_artifact, empty_board = _run(absent=False)
    adv_artifact, adv_board = _run(absent=False, register=_register_adversarial)

    def _hostile_rank_fn(calls):
        calls[0]["ticker"] = "HACKED"  # attempt to mutate the caller's population
        return _reversed_rank_fn(calls)

    hostile_artifact, hostile_board = _run(
        absent=False, register=lambda: bs.register_challenger("hostile_v1", rank_fn=_hostile_rank_fn)
    )

    assert empty_artifact == baseline_artifact == adv_artifact == hostile_artifact
    assert empty_board == baseline_board == adv_board == hostile_board
    assert "HACKED" not in json.loads(baseline_artifact.decode() if False else empty_artifact)["buy"][0].values()

    # NON-VACUITY (F2): the adversarial challenger's own store shows a rank
    # order that differs from the incumbent's — this suite is not passing
    # merely because nothing runs.
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path / "nonvacuity")
    bs.CHALLENGER_REGISTRY.clear()
    _lane_on(monkeypatch, "CA")
    _seed_board_ledger(monkeypatch, "CA", "2026-08-21", _population())
    _register_adversarial()
    result = bs.write_shadow(_population(), market="CA", asof="2026-08-21")
    assert result["written"] > 0, "POSITIVE CONTROL: the adversarial write must write > 0 rows"
    lane_a = _lane_a_frame("CA")
    assert lane_a is not None and len(lane_a) == 4
    by_ticker = lane_a.set_index("ticker")
    incumbent_order = by_ticker["incumbent_rank"].sort_values().index.tolist()
    challenger_order = by_ticker["challenger_rank"].sort_values().index.tolist()
    assert incumbent_order != challenger_order, "fixture challenger must reorder the board"


def test_k1_hk_zero_authority_byte_identity(monkeypatch):
    """K1 HK leg (F1/F2), rebuilt on the REAL production transform (M5,
    review round 2). The earlier draft's fixture set `out["buy"] = calls` —
    WRONG: production's published artifact is `out["buy"] = buys` (the
    ORIGINAL per-name board rows), and `calls` is a SEPARATELY-BUILT list
    scripts.build_hk_library._board_ledger_calls(buys, watch, ...) constructs
    from `buys`/`watch` via fresh dicts (`calls.append({"ticker": e.get(...),
    ...})`) — `calls` and `buys` never share row-dict identity to begin with.
    This test uses the REAL `_board_ledger_calls` function so the object
    graph matches production exactly, and (like the CA leg) is a genuine
    byte-identity regression on `out["buy"]`, not an F1 aliasing kill — that
    structural fact is the same reason the CA leg cannot detect a deep-copy
    removal either. F1's real load-bearing kill is the write-surface fence
    test below (m2).
    """
    _lane_on(monkeypatch, "HK")
    sys.path.insert(0, str(ROOT))
    from scripts import build_hk_library  # noqa: PLC0415

    buys = [
        {"ticker": "AAA", "group": "entry_open", "edge_z": 1.5,
         "signal": {"tier": "T1"}, "entry_window": {"kind": "open-now"}, "price": 10.0},
        {"ticker": "BBB", "group": "entry_open", "edge_z": 1.2,
         "signal": {"tier": "T2"}, "entry_window": {"kind": "pullback"}, "price": 20.0},
        {"ticker": "CCC", "group": "setting_up", "edge_z": 0.8,
         "signal": {"tier": "T2"}, "entry_window": {"kind": "wait-for-weekly"}, "price": 30.0},
    ]
    watch = [
        {"ticker": "DDD", "edge_z": -0.5,
         "signal": {"tier": "T3"}, "entry_window": {}, "price": 40.0},
    ]
    calls = build_hk_library._board_ledger_calls(buys, watch)
    out = {"buy": buys, "board_definition": "hk_prophet_v1"}
    before = json.dumps(out, sort_keys=True, default=str)

    _seed_board_ledger(monkeypatch, "HK", "2026-08-21", calls)

    def _hostile_rank_fn(inner_calls):
        inner_calls[0]["ticker"] = "HACKED"  # attempt to mutate the writer's population
        return _reversed_rank_fn(inner_calls)

    bs.register_challenger("hostile_v1", rank_fn=_hostile_rank_fn)
    result = bs.write_shadow(calls, market="HK", asof="2026-08-21")
    assert result["written"] > 0  # POSITIVE CONTROL

    after = json.dumps(out, sort_keys=True, default=str)
    assert before == after, "out['buy'] (== buys) must be byte-identical after write_shadow"
    assert out["buy"][0]["ticker"] == "AAA", "buys must never be touched — it never shared identity with calls"


def test_write_surface_fence_only_data_prophet_shadow_is_touched(tmp_path, monkeypatch):
    """m2 (M5, review round 2): the REAL F1/K1 load-bearing kill. Snapshots
    every file under the tmp data root before and after a positive-control
    write_shadow pass and asserts every path CREATED or MODIFIED lies under
    data/prophet_shadow/. This closes the residual channel the review proved
    live: neither K1's byte-identity harness (which only compares the
    PUBLISHED artifact + board_ledger's own store, and — per the corrected
    docstrings above — cannot even see an aliasing violation in the CA/HK
    object graphs as they actually exist) nor K6's static string fence (which
    only catches the literal 'prophet_shadow', not an arbitrary stray write)
    would notice a writer that also emits, say,
    `pd.DataFrame(...).to_parquet(data/hk_pick_lab/x.parquet)` — a write
    entirely outside this module's own two lanes.

    MUTATION THIS KILLS: adding any write inside write_shadow/_write_lane_a/
    _write_lane_b/_merge_write_lane_a/_merge_write_lane_b that targets a path
    outside data/prophet_shadow/.
    """
    data_root = tmp_path / "data"
    monkeypatch.setattr(config, "data_dir", lambda: data_root)
    _lane_on(monkeypatch, "CA")
    calls = _population()
    # Seed board_ledger's own store FIRST (a legitimate prior write) so its
    # mtime/size are already part of the "before" snapshot — write_shadow
    # itself must not re-touch it either.
    n = board_ledger.append_board(copy.deepcopy(calls), market="CA", asof="2026-08-21")
    assert n > 0

    def _snapshot() -> dict[str, tuple[int, int]]:
        if not data_root.exists():
            return {}
        return {
            str(p.relative_to(data_root)): (p.stat().st_mtime_ns, p.stat().st_size)
            for p in data_root.rglob("*") if p.is_file()
        }

    before = _snapshot()
    _register_adversarial()
    result = bs.write_shadow(calls, market="CA", asof="2026-08-21")
    assert result["written"] > 0  # POSITIVE CONTROL
    after = _snapshot()

    changed = {p for p in (set(before) | set(after)) if before.get(p) != after.get(p)}
    offenders = sorted(p for p in changed if not (p == "prophet_shadow" or p.startswith("prophet_shadow/")))
    assert not offenders, (
        f"write_shadow touched path(s) outside data/prophet_shadow/: {offenders}"
    )
    # Sanity: the positive control DID write something under prophet_shadow/,
    # so this is not passing merely because nothing happened on disk.
    assert any(p.startswith("prophet_shadow/") for p in changed), (
        "positive control: the write must actually touch data/prophet_shadow/"
    )


# ---------------------------------------------------------------------------
# K2 — silent population divergence
# ---------------------------------------------------------------------------
def test_k2_population_is_never_reoriginated_from_the_challenger(monkeypatch):
    """K2: the writer takes `calls` as its sole population input. A challenger
    naming a ticker OFF that list must never become a Lane A row for that
    ticker — it is counted in challenger_offlist_n and nothing else."""
    monkeypatch  # noqa: B018
    _lane_on(monkeypatch, "CA")
    calls = _population()
    _seed_board_ledger(monkeypatch, "CA", "2026-08-21", calls)

    def _rank_fn(_calls):
        base = _reversed_rank_fn(_calls)
        base["ZZZ_OFFLIST"] = {"score_raw": 999.0, "score_conservative": 999.0}
        return base

    bs.register_challenger("offlist_v1", rank_fn=_rank_fn)
    result = bs.write_shadow(calls, market="CA", asof="2026-08-21")
    assert result["written"] > 0  # POSITIVE CONTROL

    frame = _lane_a_frame("CA")
    assert frame is not None
    assert set(frame["ticker"]) == {"AAA", "BBB", "CCC", "DDD"}
    assert "ZZZ_OFFLIST" not in set(frame["ticker"])
    assert int(frame["challenger_offlist_n"].iloc[0]) == 1
    assert int(frame["population_n"].iloc[0]) == 4


# ---------------------------------------------------------------------------
# K3 — private grader: AST guard + runtime guard + schema/denylist half
# ---------------------------------------------------------------------------
_K3_FORBIDDEN_NAMES = frozenset({
    "_hk_close", "_ca_close", "_bench_close", "forward_metrics",
    "terminal_state", "fill_index",
})
_K3_EXCLUDED_FUNCS = frozenset({"_read_board_parquet", "_read_own_store"})


def _dotted_chain(node: ast.AST) -> tuple[str, ...]:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return tuple(reversed(parts))


class _K3Visitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.stack: list[str] = []
        self.hits: list[str] = []

    def _excluded(self) -> bool:
        return any(name in _K3_EXCLUDED_FUNCS for name in self.stack)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    def visit_Attribute(self, node: ast.Attribute) -> None:  # noqa: N802
        if not self._excluded():
            joined = ".".join(_dotted_chain(node))
            if (
                joined.startswith("grading.")
                or joined == "store.read"
                or joined in ("pd.read_parquet", "pd.read_csv")
                # The trailing `.attr` alone is forbidden regardless of what
                # precedes it — `board_ledger._hk_close(...)`, `_bl.grading.
                # forward_metrics(...)`, `something._bench_close(...)` are all
                # the same private-grader surface wearing a different prefix,
                # and a prefix-anchored check (`joined.startswith(...)`) never
                # sees them (review finding M1).
                or node.attr in _K3_FORBIDDEN_NAMES
            ):
                self.hits.append(joined)
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:  # noqa: N802
        if not self._excluded() and node.id in _K3_FORBIDDEN_NAMES:
            self.hits.append(node.id)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        if (
            not self._excluded()
            and isinstance(node.func, ast.Name)
            and node.func.id == "open"
        ):
            self.hits.append("open(...)")
        self.generic_visit(node)


def test_k3_private_grader_ast_guard():
    """K3(i) (F7/F13): static CALL-surface fence scoped to engine/board_shadow.py
    ONLY. No Name/Attribute in the module may resolve to grading.*, store.read,
    pd.read_parquet, pd.read_csv, _hk_close, _ca_close, _bench_close,
    forward_metrics, terminal_state, fill_index, or a bare open() — outside
    the two pinned, sanctioned read-back helpers (_read_board_parquet reading
    board_ledger's own parquet §2; _read_own_store reading this module's own
    Lane A/B store).

    MUTATION THIS KILLS: add an outcome computation anywhere else in the
    module (e.g. `from engine import grading` at module scope, or a stray
    `pd.read_parquet(hk_close_path)` in a writer helper) → this test fails.
    """
    source = (ROOT / "engine" / "board_shadow.py").read_text()
    tree = ast.parse(source)
    visitor = _K3Visitor()
    visitor.visit(tree)
    assert not visitor.hits, f"forbidden private-grader surface found: {visitor.hits}"


def test_k3_private_grader_runtime_guard(monkeypatch):
    """K3(ii): monkeypatch pandas.read_parquet AND lib.store.read to raise for
    anything that is NOT the sanctioned board_ledger read-back path, and
    assert a full positive-control writer pass still succeeds — the writer's
    own execution never depends on reading anything else. Contract §6 K3(ii)
    names BOTH `lib.store.read` and `pandas.read_parquet` as the runtime half;
    guarding only pandas would miss a mutation that reaches price data via
    `store.read` (e.g. calling board_ledger._hk_close, which itself calls
    `store.read("hk_stocks", ticker)`) without ever calling pd.read_parquet
    directly — review finding M1(b).
    """
    _lane_on(monkeypatch, "CA")
    calls = _population()
    _seed_board_ledger(monkeypatch, "CA", "2026-08-21", calls)
    board_path = board_ledger._store_path("CA")

    real_read_parquet = pd.read_parquet

    def _guarded_read_parquet(path, *args, **kwargs):
        if Path(path) == board_path:
            return real_read_parquet(path, *args, **kwargs)
        raise AssertionError(f"private grader detected: read_parquet({path})")

    def _guarded_store_read(*args, **kwargs):
        # board_shadow.py has ZERO legitimate reason to call lib.store.read —
        # unlike the board_ledger parquet, there is no sanctioned exception.
        raise AssertionError(f"private grader detected: store.read{args!r}")

    from lib import store as _store_module

    # Seed the shadow store's own prior state via the real path BEFORE arming
    # the guard, then register the challenger and run under the guard.
    monkeypatch.setattr(bs.pd, "read_parquet", _guarded_read_parquet)
    monkeypatch.setattr(_store_module, "read", _guarded_store_read)
    _register_adversarial()
    result = bs.write_shadow(calls, market="CA", asof="2026-08-21")
    assert result["written"] > 0, "POSITIVE CONTROL: writer must still succeed under the guard"


def test_k3_schema_denylist_blocks_outcome_columns():
    """K3(iii) (schema half): an outcome column can never reach disk — the
    denylist outranks the allowlist at the write seam (K11's mechanism,
    reused here for K3's third leg)."""
    frame = pd.DataFrame([{**{c: None for c in bs._SCHEMA_A}, "fwd_ret_5": 0.03, "hit_rate": 1}])
    out = bs._apply_write_seam(frame, bs._SCHEMA_A, "lane_a")
    assert "fwd_ret_5" not in out.columns
    assert "hit_rate" not in out.columns


def test_k3_denylist_outranks_schema_membership_even_for_a_pinned_column(monkeypatch):
    """K3(iii)/M3: the denylist must strip a column EVEN IF that exact name
    is a member of the schema being reindexed to — not just when the column
    was already outside the allowlist (which 'not in schema' alone already
    handles trivially). Uses a SYNTHETIC schema containing a denylisted-
    shaped name, since no real _SCHEMA_A/schema_b() member matches a deny
    pattern today (pinned by the import-time assertion in
    engine/board_shadow.py).

    MUTATION THIS KILLS: neutering `_is_denylisted` (or reverting
    `_apply_write_seam` to reindex against the raw `schema` instead of an
    `effective_schema` with denylisted names stripped) lets `fwd_ret_5`
    survive here, because it IS nominally part of this synthetic schema.
    """
    synthetic_schema = (*bs._SCHEMA_A, "fwd_ret_5")
    frame = pd.DataFrame([{**{c: None for c in bs._SCHEMA_A}, "fwd_ret_5": 0.03}])

    out = bs._apply_write_seam(frame, synthetic_schema, "lane_a")
    assert "fwd_ret_5" not in out.columns, (
        "a column matching a deny pattern must be stripped even when it is "
        "nominally a schema member"
    )

    monkeypatch.setattr(bs, "_is_denylisted", lambda _col: False)
    neutered_out = bs._apply_write_seam(frame, synthetic_schema, "lane_a")
    assert "fwd_ret_5" in neutered_out.columns, (
        "sanity check: with the denylist neutered, the synthetic schema "
        "member DOES survive — proving the guard above is load-bearing, not "
        "a byproduct of 'fwd_ret_5' being absent from the schema"
    )


# ---------------------------------------------------------------------------
# K4 — era pooling: whitespace normalisation + identity binding
# ---------------------------------------------------------------------------
def test_k4_whitespace_bearing_definition_is_normalised(monkeypatch):
    """K4(i) (F6): a whitespace-bearing incumbent_definition stamp must
    normalise to the stripped string, not the raw whitespace-bearing form.
    MUTATION THIS KILLS: skip the _definition_or_none call and store
    call.get('board_definition') raw."""
    _lane_on(monkeypatch, "CA")
    calls = [{"ticker": "AAA", "group": "entry_open", "board_definition": " test_board_v1 "}]
    _seed_board_ledger(monkeypatch, "CA", "2026-08-21", calls)
    _register_adversarial()
    result = bs.write_shadow(calls, market="CA", asof="2026-08-21")
    assert result["written"] > 0  # POSITIVE CONTROL
    frame = _lane_a_frame("CA")
    assert frame is not None
    assert frame["incumbent_definition"].iloc[0] == "test_board_v1"


def test_k4_normalizer_is_the_same_object_as_board_ledger(monkeypatch):
    """K4(ii) (F6): board_shadow's normalizer must be board_ledger's exact
    function OBJECT (`is`, not equality) — two normalizers feeding one
    exact-equality comparison must be one object.

    MUTATION THIS KILLS: `board_shadow._definition_or_none` defined as a
    SEPARATE copy of the same logic (equal behaviour today, but the two
    would silently diverge the next time board_ledger's nullish set grows).
    The identity assertion below is the primary kill; the second half proves
    they are not just equal-by-accident — extending board_ledger's live
    `_NULLISH_STR` (which `_definition_or_none` reads from module globals at
    CALL time, not at def time) must move board_shadow's bound reference too,
    because it is literally the same function object reading the same
    global."""
    assert bs._definition_or_none is board_ledger._definition_or_none

    extra_nullish = "totally-not-a-real-definition-sentinel"
    assert bs._definition_or_none(extra_nullish) == extra_nullish  # not nullish YET
    monkeypatch.setattr(board_ledger, "_NULLISH_STR", (*board_ledger._NULLISH_STR, extra_nullish))
    assert bs._definition_or_none(extra_nullish) is None, (
        "board_shadow's bound reference must observe board_ledger's live "
        "_NULLISH_STR — proving the two names share one function object"
    )
    assert bs._definition_or_none is board_ledger._definition_or_none


# ---------------------------------------------------------------------------
# K5 — missing score coerced to 0 is forbidden (missing != zero)
# ---------------------------------------------------------------------------
def test_k5_missing_challenger_score_is_null_not_zero(monkeypatch):
    """K5: a ticker the challenger did NOT score gets challenger_rank/scores
    NULL, never 0. MUTATION THIS KILLS: `.get("score_raw") or 0.0` instead of
    `_finite(...)` (None stays None)."""
    _lane_on(monkeypatch, "CA")
    calls = _population()
    _seed_board_ledger(monkeypatch, "CA", "2026-08-21", calls)

    def _partial_rank_fn(_calls):
        # Only scores AAA and BBB — CCC/DDD are unscored (missing, not 0).
        return {
            "AAA": {"score_raw": 5.0, "score_conservative": 4.5},
            "BBB": {"score_raw": 3.0, "score_conservative": 2.5},
        }

    bs.register_challenger("partial_v1", rank_fn=_partial_rank_fn)
    result = bs.write_shadow(calls, market="CA", asof="2026-08-21")
    assert result["written"] > 0  # POSITIVE CONTROL

    frame = _lane_a_frame("CA").set_index("ticker")
    assert pd.isna(frame.loc["CCC", "challenger_score_raw"])
    assert pd.isna(frame.loc["CCC", "challenger_rank"])
    assert pd.isna(frame.loc["DDD", "challenger_score_raw"])
    assert frame.loc["AAA", "challenger_score_raw"] == 5.0


# ---------------------------------------------------------------------------
# K6 — leakage: repo-wide static fence
# ---------------------------------------------------------------------------
_K6_SCAN_ROOTS = ("engine", "scripts", "app", "admin", "templates")
_K6_ALLOWED_FILES = {
    "engine/board_shadow.py",
    "tests/test_board_shadow.py",
}

#: Named FORMS the literal 'prophet_shadow' legitimately takes in pre-existing,
#: unrelated code (review finding M2, replacing a per-file occurrence COUNT
#: that a masking probe defeated: deleting one legitimate line and adding a
#: genuinely dangerous one in the same file nets the SAME count). Each form is
#: a regex tied to the SHAPE the safe usage takes; classification is by
#: MATCHING SPAN, not raw substring count, so a occurrence's position must
#: fall inside a form's match to be excused — a masking edit that changes
#: WHICH forms appear (not just how many) is caught even at constant count.
_K6_FORMS: dict[str, re.Pattern] = {
    # prophet_shadow_definition / _score / _score_rank / _{component}[_points] —
    # a LONGER identifier that merely starts with "prophet_shadow_"; this is
    # the US fusion-override's own column-name family, never a bare
    # "prophet_shadow" token.
    "prefixed_identifier": re.compile(r"prophet_shadow_[A-Za-z{]"),
    # row["prophet_shadow"] / row.get("prophet_shadow") / board.get("prophet_shadow")
    # — a dict-key ACCESS on some unrelated in-memory row/board dict.
    "dict_access": re.compile(r'(\[|\.get\(\s*)["\']prophet_shadow["\']'),
    # "prophet_shadow": (...) — a dict LITERAL key.
    "dict_literal_key": re.compile(r'["\']prophet_shadow["\']\s*:'),
    # ("prophet", "prophet_shadow", "score_rank", ...) — a bare member of a
    # tuple/list of field-name string constants (iterate-and-pop idiom).
    "tuple_member": re.compile(r'[,(]\s*["\']prophet_shadow["\']\s*[,)]'),
    # `prophet_shadow` / ``prophet_shadow`` — a bare backtick-wrapped
    # docstring/comment mention (prose, not executable).
    "backtick_bare_mention": re.compile(r"`{1,2}prophet_shadow`{1,2}"),
    # engine/china_prophet_shadow.py / china_prophet_shadow — the DIFFERENT,
    # pre-existing CN module name (substring collision: "china_prophet_shadow"
    # contains "prophet_shadow" starting at its 6th character).
    "china_module_reference": re.compile(r"china_prophet_shadow(\.py)?"),
    # options.prophet_shadow/v1 — the options-flow schema string literal.
    "options_schema_string": re.compile(r"options\.prophet_shadow/v1"),
    # "prophet_shadow.score_rank" / "prophet_shadow.score" as a quoted VALUE
    # (a human-readable label, not a key access) in us_prophet_fusion_compare.py.
    "label_literal": re.compile(r'["\']prophet_shadow\.(score_rank|score)["\']'),
    # `prophet_shadow.score` — the same label above, but backtick-wrapped
    # prose in prophet_bridge.py's docstring rather than a quoted string.
    "bridge_prose_attribute": re.compile(r"`prophet_shadow\.score`"),
}

#: {file: (allowed form names, reason)} — PER-FILE, not global: a file may
#: only excuse an occurrence via the specific forms audited to be present in
#: IT, so a masking edit that deletes one file's legitimate occurrence and
#: adds a differently-shaped one (the review's demonstrated probe: delete the
#: line-488 comment in engine/us_candidate_lanes.py, add
#: `pd.read_parquet(config.data_dir()/"prophet_shadow"/...)` — net count
#: unchanged) is caught because the ADDED occurrence's shape (a path-segment
#: literal, preceded by `/` not `[`/`.get(`/a backtick/a comma) matches NONE
#: of that file's declared forms.
_K6_PREEXISTING_UNRELATED_FILES: dict[str, tuple[tuple[str, ...], str]] = {
    "engine/us_board_rank.py": (("dict_access", "backtick_bare_mention"), (
        "US C1 fusion override's own `prophet_shadow` dict key (the retired "
        "v2 scorer's legs), unrelated to engine/board_shadow.py — see that "
        "module's own SHADOW_COLUMNS-style docstring."
    )),
    "engine/us_context_vector.py": (
        ("china_module_reference", "backtick_bare_mention", "prefixed_identifier", "dict_access"), (
        "reads/documents the same US `prophet_shadow` dict key above via "
        "us_board_rank, plus its own `prophet_shadow_*` SHADOW_COLUMNS family "
        "and the unrelated pre-existing china_prophet_shadow.py mention."
    )),
    "scripts/build_options_prophet.py": (("options_schema_string",), (
        "options-flow schema literal 'options.prophet_shadow/v1' — an "
        "unrelated schema name that happens to share the substring."
    )),
    "scripts/mirror_flow_idx.py": (("options_schema_string",), (
        "reads the same options-flow schema literal above."
    )),
    "engine/us_prophet_w3.py": (("prefixed_identifier",), (
        "US W3 evidence module's own `prophet_shadow_*` dict key family "
        "(same US fusion-override feature as us_board_rank.py above)."
    )),
    "engine/us_candidate_lanes.py": (
        ("dict_access", "backtick_bare_mention", "dict_literal_key"), (
        "reads the same US `prophet_shadow` dict key family above (subscript "
        "access, a docstring mention, and a dict-literal key)."
    )),
    "scripts/us_prophet_fusion_compare.py": (
        ("backtick_bare_mention", "dict_access", "tuple_member", "label_literal"), (
        "compares the US `prophet_shadow` dict key family above — a fusion "
        "research script, not this module's caller."
    )),
    "engine/cn_theme_tape.py": (("china_module_reference",), (
        "names the DIFFERENT, pre-existing engine/china_prophet_shadow.py "
        "module (substring collision: 'china_prophet_shadow' contains "
        "'prophet_shadow') — not this contract's engine/board_shadow.py."
    )),
    "engine/prophet_bridge.py": (("bridge_prose_attribute",), (
        "`prophet_shadow.score` — the same US retired-v2-scorer dict key "
        "above, mentioned in prose in the bridge module's docstring."
    )),
    "scripts/build_china_library.py": (("china_module_reference",), (
        "`from engine import china_prophet_shadow` — the different, "
        "pre-existing CN shadow module (substring collision as above)."
    )),
}


def _k6_unclassified_occurrences(text: str, allowed_forms: tuple[str, ...]) -> list[str]:
    """Every raw 'prophet_shadow' occurrence in `text` whose position is not
    covered by any of `allowed_forms`'s matched spans — the actual leak
    detector. A NEW occurrence whose shape matches none of a file's declared
    forms is unclassified regardless of whether the file's total count of
    'prophet_shadow' happens to be unchanged (M2's fix: count alone cannot
    tell 'a legitimate line moved' from 'a legitimate line was traded for a
    dangerous one')."""
    raw_positions = [m.start() for m in re.finditer("prophet_shadow", text)]
    if not raw_positions:
        return []
    classified_spans: list[tuple[int, int]] = []
    for form_name in allowed_forms:
        pattern = _K6_FORMS[form_name]
        classified_spans.extend((m.start(), m.end()) for m in pattern.finditer(text))
    unclassified = []
    for pos in raw_positions:
        if not any(start <= pos < end for start, end in classified_spans):
            lo, hi = max(0, pos - 40), min(len(text), pos + 40)
            unclassified.append(text[lo:hi].replace("\n", "\\n"))
    return unclassified


def test_k6_prophet_shadow_literal_is_confined_to_its_own_module_and_tests():
    """K6 (F12): a repo-wide walk of engine/, scripts/, app/, admin/,
    templates/ for the literal 'prophet_shadow' must find it ONLY in
    engine/board_shadow.py and its own test file. This is the leakage fence a
    byte-identity harness (K1) cannot provide — it catches a READER of an
    empty store (which produces byte-identical published output but still
    binds the store into production code), the exact CN-shadow precedent
    the contract cites as already having happened once.

    DEVIATION NOTE (reported in the build packet): the literal
    'prophet_shadow' already appears, pre-existing and unrelated, in the US
    board_rank fusion-override dict key family and the options-flow schema
    string (see _K6_PREEXISTING_UNRELATED_FILES) — a blind scan as literally
    specified is permanently red from day one regardless of this module.
    Those files are excused by a PER-FILE set of named regex FORMS (M2 fix,
    2026-08-21 review round 2 — a raw occurrence COUNT allowlist was proven
    maskable: delete one legitimate occurrence, add a differently-shaped
    dangerous one, net count unchanged), so a NEW occurrence whose shape
    matches none of that file's declared forms still fails loudly.

    MUTATION THIS KILLS: any production module importing
    engine.board_shadow / referencing 'prophet_shadow' by name (e.g. a
    template or admin page rendering the store path), a new reference added
    to one of the excused pre-existing files in an UNRECOGNISED shape (the
    review's masking probe: delete engine/us_candidate_lanes.py's line-488
    comment AND add `pd.read_parquet(config.data_dir()/"prophet_shadow"/...)`
    — net occurrence count unchanged, but the added occurrence's shape
    matches none of that file's declared forms)."""
    offenders: list[str] = []
    for root_name in _K6_SCAN_ROOTS:
        root = ROOT / root_name
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            rel = path.relative_to(ROOT).as_posix()
            if rel in _K6_ALLOWED_FILES:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue  # binary/unreadable files carry no source-level leak
            if "prophet_shadow" not in text:
                continue
            if rel in _K6_PREEXISTING_UNRELATED_FILES:
                allowed_forms, _reason = _K6_PREEXISTING_UNRELATED_FILES[rel]
                unclassified = _k6_unclassified_occurrences(text, allowed_forms)
                if unclassified:
                    offenders.append(
                        f"{rel}: unrecognised 'prophet_shadow' form(s) beyond its "
                        f"audited forms {allowed_forms}: {unclassified}"
                    )
                continue
            offenders.append(rel)
    assert not offenders, f"'prophet_shadow' literal leaked outside its owning module: {offenders}"


# ---------------------------------------------------------------------------
# K7 — board-ledger protection
# ---------------------------------------------------------------------------
def test_k7_shadow_writer_never_touches_board_ledger_store(monkeypatch):
    """K7: the shadow writer must never add columns or rows to
    data/board_ledger/*.parquet. Compared by schema equality + (date,ticker)
    key-set equality + board_pos equality — never byte equality, because
    grade() legitimately rewrites that parquet on-lane (F-K7)."""
    _lane_on(monkeypatch, "CA")
    calls = _population()
    _seed_board_ledger(monkeypatch, "CA", "2026-08-21", calls)
    board_path = board_ledger._store_path("CA")
    before = pd.read_parquet(board_path)

    _register_adversarial()
    result = bs.write_shadow(calls, market="CA", asof="2026-08-21")
    assert result["written"] > 0  # POSITIVE CONTROL

    after = pd.read_parquet(board_path)
    assert list(before.columns) == list(after.columns)
    before_keys = set(zip(before["date"].astype(str), before["ticker"].astype(str)))
    after_keys = set(zip(after["date"].astype(str), after["ticker"].astype(str)))
    assert before_keys == after_keys
    before_pos = dict(zip(before["ticker"].astype(str), before["board_pos"]))
    after_pos = dict(zip(after["ticker"].astype(str), after["board_pos"]))
    assert before_pos == after_pos


# ---------------------------------------------------------------------------
# K8 — backfill refusals (asof mismatch / wall-clock / behind-the-head)
# ---------------------------------------------------------------------------
def _discovery_fn_factory(rows: list[dict]):
    def _fn(_asof):
        return rows
    return _fn


def test_k8a_session_date_must_equal_current_asof(monkeypatch):
    """K8a: a Lane B row whose session_date != the current build's asof is
    refused. Uses session_date = asof - 1 DAY, INSIDE the settle window
    (SETTLE_WINDOW_DAYS=3) — a wide gap (e.g. 20 days) would ALSO trip K8b's
    wall-clock settle fence on its own, so deleting K8a's own
    `session_date != asof` block would still pass this test for the WRONG
    reason (M6/m1 isolation fix, review round 2: date bomb + isolation).
    With a 1-day gap, removing K8a's block leaves K8b (1 day < 3-day window)
    and K8c (no prior store, nothing to be behind) both silent, so a real
    K8a removal writes the row and this test genuinely fails.

    MUTATION THIS KILLS: drop the `session_date != asof` check."""
    _lane_on(monkeypatch, "CA")
    today = dt.datetime.now(dt.timezone.utc).date()
    asof = today.isoformat()
    mismatched_session_date = (today - dt.timedelta(days=1)).isoformat()
    rows = [{"session_date": mismatched_session_date, "security_ref_raw": "AAA",
              "candidate_origin": "test"}]
    bs.register_challenger("disc_v1", discovery_fn=_discovery_fn_factory(rows))
    result = bs.write_shadow([], market="CA", asof=asof)
    frame = _lane_b_frame("CA")
    assert frame is None or frame.empty
    assert result["written"] == 0


def test_k8a_positive_control_matching_asof_writes(monkeypatch):
    """Positive control for K8a: a row whose session_date DOES match asof
    must actually write — otherwise K8a would pass vacuously. Dates derived
    from the live wall clock (M6/m1 date-bomb fix, review round 2): a
    hardcoded date would eventually trip K8b's wall-clock settle fence for
    reasons unrelated to what this test checks, the moment real time moves
    far enough past it."""
    _lane_on(monkeypatch, "CA")
    today = dt.datetime.now(dt.timezone.utc).date().isoformat()
    rows = [{"session_date": today, "security_ref_raw": "AAA",
              "candidate_origin": "test"}]
    bs.register_challenger("disc_v1", discovery_fn=_discovery_fn_factory(rows))
    result = bs.write_shadow([], market="CA", asof=today)
    assert result["written"] > 0
    frame = _lane_b_frame("CA")
    assert frame is not None and len(frame) == 1


def test_k8b_wall_clock_settle_fence(monkeypatch):
    """K8b (F10): stamped_at's date may not exceed session_date beyond the
    settle window, even when session_date == asof — a caller passing a stale
    asof pretending it is live must still be refused. MUTATION THIS KILLS:
    delete the _settle_violation check."""
    stale_asof = "2020-01-01"
    _lane_on(monkeypatch, "CA")
    rows = [{"session_date": stale_asof, "security_ref_raw": "AAA", "candidate_origin": "test"}]
    bs.register_challenger("disc_v1", discovery_fn=_discovery_fn_factory(rows))
    result = bs.write_shadow([], market="CA", asof=stale_asof)
    assert result["written"] == 0
    frame = _lane_b_frame("CA")
    assert frame is None or frame.empty


def test_k8c_behind_the_head_is_refused(monkeypatch):
    """K8 (behind-the-head): a session_date older than the store's current
    max session_date is refused — no filling holes behind the head."""
    _lane_on(monkeypatch, "CA")
    today = dt.datetime.now(dt.timezone.utc).date()
    newer = today.isoformat()
    older = (today - dt.timedelta(days=1)).isoformat()

    bs.register_challenger("disc_v1", discovery_fn=_discovery_fn_factory(
        [{"session_date": newer, "security_ref_raw": "AAA", "candidate_origin": "test"}]))
    result = bs.write_shadow([], market="CA", asof=newer)
    assert result["written"] > 0  # POSITIVE CONTROL — establishes the head

    bs.CHALLENGER_REGISTRY.clear()
    bs.register_challenger("disc_v1", discovery_fn=_discovery_fn_factory(
        [{"session_date": older, "security_ref_raw": "BBB", "candidate_origin": "test"}]))
    result2 = bs.write_shadow([], market="CA", asof=older)
    assert result2["written"] == 0
    frame = _lane_b_frame("CA")
    assert "BBB" not in set(frame["security_ref"])


# ---------------------------------------------------------------------------
# K9 — identity divergence (collision counting)
# ---------------------------------------------------------------------------
def _strip_canonicalizer(raw):
    """A future semantic canonicalizer stand-in — folds whitespace variants
    together. canonical_ref() itself is EXACT str() identity today (m3 review
    correction: no .strip()), so the collision MACHINERY (ref_collision_n) is
    dormant in production until an upgrade like this one lands; K9 exercises
    that machinery by monkeypatching canonical_ref to this variant rather
    than relying on today's identity rule to collide anything."""
    if raw is None:
        return None
    text = str(raw).strip()
    return text or None


def test_k9_ref_collision_is_counted_and_kept(monkeypatch):
    """K9 (F11): two distinct raw refs canonicalising to one security_ref in
    one session must be COUNTED (ref_collision_n) and both observations kept
    — never silently collapsed to one row, including across a SECOND write
    that merges against the store the first write created (M4: security_ref_raw
    joined _LANE_B_KEY precisely so this merge cannot silently drop_duplicates
    the two collision rows down to one)."""
    _lane_on(monkeypatch, "CA")
    today = dt.datetime.now(dt.timezone.utc).date().isoformat()
    monkeypatch.setattr(bs, "canonical_ref", _strip_canonicalizer)
    rows = [
        {"session_date": today, "security_ref_raw": " AAA", "candidate_origin": "a"},
        {"session_date": today, "security_ref_raw": "AAA ", "candidate_origin": "b"},
    ]
    bs.register_challenger("disc_v1", discovery_fn=_discovery_fn_factory(rows))
    result = bs.write_shadow([], market="CA", asof=today)
    assert result["written"] > 0  # POSITIVE CONTROL
    frame = _lane_b_frame("CA")
    assert len(frame) == 2
    assert set(frame["ref_collision_n"]) == {2}
    assert set(frame["security_ref"]) == {"AAA"}
    assert set(frame["security_ref_raw"]) == {"AAA", "AAA "} or set(frame["security_ref_raw"]) == {" AAA", "AAA "}

    # M4: a SECOND write_shadow call (unrelated ticker, different session)
    # forces the merge path (`prior is not None` in _merge_write_lane_b) that
    # runs drop_duplicates on _LANE_B_KEY. Both day-1 collision rows must
    # still be present afterward — the bug this fix closes destroyed them
    # here specifically.
    bs.CHALLENGER_REGISTRY.clear()
    monkeypatch.setattr(bs, "canonical_ref", _strip_canonicalizer)
    tomorrow = (dt.datetime.now(dt.timezone.utc).date() + dt.timedelta(days=1)).isoformat()
    bs.register_challenger("disc_v1", discovery_fn=_discovery_fn_factory(
        [{"session_date": tomorrow, "security_ref_raw": "ZZZ", "candidate_origin": "z"}]))
    result2 = bs.write_shadow([], market="CA", asof=tomorrow)
    assert result2["written"] > 0

    frame_after = _lane_b_frame("CA")
    day1_rows = frame_after[frame_after["session_date"] == today]
    assert len(day1_rows) == 2, (
        "both day-1 collision rows must survive a later merge — "
        f"got {len(day1_rows)} row(s): {day1_rows.to_dict('records')}"
    )
    assert set(day1_rows["ref_collision_n"]) == {2}


def test_k9_non_colliding_refs_stay_separate(monkeypatch):
    """K9 mirror kill: two refs that do NOT canonicalize together must not be
    merged (ref_collision_n == 1 for each). Uses the real (identity) canonical_ref
    — "AAA" and "BBB" never collide under any canonicalizer."""
    _lane_on(monkeypatch, "CA")
    today = dt.datetime.now(dt.timezone.utc).date().isoformat()
    rows = [
        {"session_date": today, "security_ref_raw": "AAA", "candidate_origin": "a"},
        {"session_date": today, "security_ref_raw": "BBB", "candidate_origin": "b"},
    ]
    bs.register_challenger("disc_v1", discovery_fn=_discovery_fn_factory(rows))
    bs.write_shadow([], market="CA", asof=today)
    frame = _lane_b_frame("CA")
    assert set(frame["security_ref"]) == {"AAA", "BBB"}
    assert set(frame["ref_collision_n"]) == {1}


def test_canonical_ref_is_exact_str_identity_matching_board_ledger():
    """m3: canonical_ref() must be EXACT identity over str(raw) — no strip,
    no fold — matching what board_ledger stores verbatim (`str(tk)`,
    unstripped, in append_board). A whitespace-bearing raw ref must NOT be
    silently normalised here; that would mint a second identity truth (the
    exact F11 concern this function exists to close).

    MUTATION THIS KILLS: reintroducing `.strip()` (or any other
    normalisation) into canonical_ref's body."""
    assert bs.canonical_ref("AAA") == str("AAA")
    assert bs.canonical_ref(" AAA ") == str(" AAA ")  # NOT stripped
    assert bs.canonical_ref(" AAA ") != bs.canonical_ref("AAA")
    assert bs.canonical_ref(700) == str(700)
    assert bs.canonical_ref(None) is None


# ---------------------------------------------------------------------------
# K10 — coverage substitution (F8)
# ---------------------------------------------------------------------------
def test_k10_coverage_denominator_is_population_n_only(monkeypatch):
    """K10 (F8): challenger_coverage must reproduce from population_n — the
    incumbent minted population is the ONLY lawful denominator. Store
    validator identities fail on any other denominator (e.g. buy-lane-only)."""
    _lane_on(monkeypatch, "CA")
    calls = _population()  # 4 names, 1 of which is 'watch'
    _seed_board_ledger(monkeypatch, "CA", "2026-08-21", calls)

    def _rank_fn(_calls):
        return {"AAA": {"score_raw": 1.0}, "BBB": {"score_raw": 2.0}}  # 2 of 4 scored

    bs.register_challenger("cov_v1", rank_fn=_rank_fn)
    result = bs.write_shadow(calls, market="CA", asof="2026-08-21")
    assert result["written"] > 0  # POSITIVE CONTROL

    frame = _lane_a_frame("CA")
    assert set(frame["population_n"]) == {4}, "denominator must be the full incumbent population, not the buy lane"
    assert set(round(c, 6) for c in frame["challenger_coverage"]) == {round(2 / 4, 6)}
    violations = bs.validate_population_identities("CA")
    assert violations == [], violations


def test_k10_store_validator_catches_a_bad_denominator():
    """K10 mutation-kill proof: hand-craft a Lane A frame whose
    challenger_coverage was computed over a wrong denominator (3 instead of
    4) and assert the validator FLAGS it — proving the identity check is not
    a no-op."""
    monkeypatch_path = bs._lane_a_path("CA")
    monkeypatch_path.parent.mkdir(parents=True, exist_ok=True)
    bad = pd.DataFrame([
        {"date": "2026-08-21", "market": "CA", "ticker": "AAA",
         "challenger_definition": "bad_v1", "population_n": 4,
         "challenger_rank": 1, "challenger_coverage": 0.5},  # should be 1/4=0.25
    ])
    bad.to_parquet(monkeypatch_path, index=False)
    violations = bs.validate_population_identities("CA")
    assert violations, "a wrong coverage denominator must be flagged"


# ---------------------------------------------------------------------------
# K11 — unclassified column (runtime drop + hard-fail agreement)
# ---------------------------------------------------------------------------
def test_k11_unclassified_column_is_dropped_at_the_write_seam(capsys):
    """K11 (F4): a column reaching the writer that is neither on the
    allowlist nor the denylist is DROPPED with a line-start ::warning."""
    frame = pd.DataFrame([{**{c: None for c in bs._SCHEMA_A}, "totally_new_field": "x"}])
    out = bs._apply_write_seam(frame, bs._SCHEMA_A, "lane_a")
    assert "totally_new_field" not in out.columns
    captured = capsys.readouterr()
    assert captured.out.startswith("::warning") or "::warning" in captured.out
    assert "totally_new_field" in captured.out


def test_k11_the_runtime_drop_and_the_classifier_agree():
    """The dual-check shape (mirrors
    test_the_runtime_drop_and_the_hard_fail_law_agree in
    tests/test_us_context_vector_payload_containment.py): every column the
    write seam KEEPS must classify as 'allowed'; every column it DROPS must
    classify as 'denied' or 'unclassified'."""
    columns = [*bs._SCHEMA_A, "fwd_ret_5", "somenewfield"]
    frame = pd.DataFrame([{c: None for c in columns}])
    out = bs._apply_write_seam(frame, bs._SCHEMA_A, "lane_a")
    for col in out.columns:
        assert bs.classify_column(col, bs._SCHEMA_A) == "allowed"
    for col in set(columns) - set(out.columns):
        assert bs.classify_column(col, bs._SCHEMA_A) in ("denied", "unclassified")


# ---------------------------------------------------------------------------
# K12 — incumbent-rank fidelity (F5)
# ---------------------------------------------------------------------------
def test_k12_incumbent_rank_matches_board_pos_with_a_ticker_less_row(monkeypatch):
    """K12 (F5): a calls list containing one ticker-less row must not shift
    board_pos assignment for the real tickers, and shadow's incumbent_rank
    must equal board_ledger's board_pos for EVERY ticker — never
    independently re-derived by enumerate(calls), which would see the
    ticker-less row and mint a phantom position.

    board_ledger.append_board mints board_pos via
    `enumerate(calls, start=1)` BEFORE checking whether a row has a ticker —
    a ticker-less row still consumes its position number, so real
    board_ledger board_pos here is {AAA: 2, BBB: 3} (a GAP at 1), never the
    compacted {AAA: 1, BBB: 2} an independent re-enumeration over
    ticker-having rows only would phantom-mint. That gap is exactly what
    this kill targets."""
    _lane_on(monkeypatch, "CA")
    calls_with_gap = [
        {"ticker": None, "group": "entry_open", "board_definition": "test_board_v1"},  # consumes pos=1, skipped
        {"ticker": "AAA", "group": "entry_open", "board_definition": "test_board_v1"},
        {"ticker": "BBB", "group": "entry_open", "board_definition": "test_board_v1"},
    ]
    _seed_board_ledger(monkeypatch, "CA", "2026-08-21", calls_with_gap)
    board_frame = pd.read_parquet(board_ledger._store_path("CA"))
    real_positions = dict(zip(board_frame["ticker"].astype(str), board_frame["board_pos"]))
    assert real_positions == {"AAA": 2, "BBB": 3}  # the gap at pos=1 is real, not a bug

    _register_adversarial()
    result = bs.write_shadow(calls_with_gap, market="CA", asof="2026-08-21")
    assert result["written"] > 0  # POSITIVE CONTROL

    frame = _lane_a_frame("CA").set_index("ticker")
    for ticker, pos in real_positions.items():
        assert int(frame.loc[ticker, "incumbent_rank"]) == int(pos), (
            f"{ticker}: incumbent_rank must equal board_ledger board_pos"
        )


# ---------------------------------------------------------------------------
# K13 — rank-domain (F9)
# ---------------------------------------------------------------------------
def test_k13_challenger_rank_is_dense_over_the_minted_population_with_nulls(monkeypatch):
    """K13 (F9): challenger ranks must be dense (1..k) over only the SCORED
    subset while unscored names stay NULL, when population_n > k — never a
    1..population_n rank that pretends everyone was scored.

    n4 (post-review clarification): this IS K13's operative reading — the
    contract's parenthetical ("dense rank over the minted population with
    NULLs is the only lawful shape"). A rank of 1..k over ONLY the scored
    subset (no gaps for the unscored names) is the alternative reading K13
    exists to KILL, not an equally valid interpretation."""
    _lane_on(monkeypatch, "CA")
    calls = _population()  # population_n = 4
    _seed_board_ledger(monkeypatch, "CA", "2026-08-21", calls)

    def _rank_fn(_calls):
        # Only 2 of 4 scored, with a TIE, to also assert dense (not skip) ranking.
        return {
            "AAA": {"score_raw": 5.0},
            "BBB": {"score_raw": 5.0},  # tie with AAA
        }

    bs.register_challenger("dense_v1", rank_fn=_rank_fn)
    result = bs.write_shadow(calls, market="CA", asof="2026-08-21")
    assert result["written"] > 0  # POSITIVE CONTROL

    frame = _lane_a_frame("CA").set_index("ticker")
    assert frame.loc["AAA", "challenger_rank"] == 1
    assert frame.loc["BBB", "challenger_rank"] == 1  # dense tie, not 1/2
    assert pd.isna(frame.loc["CCC", "challenger_rank"])
    assert pd.isna(frame.loc["DDD", "challenger_rank"])
    assert set(frame["challenger_rank_domain"]) == {"minted_population"}
    assert int(frame["population_n"].iloc[0]) == 4


# ---------------------------------------------------------------------------
# K14 — forward-clock (never reset first_seen_at)
# ---------------------------------------------------------------------------
def test_k14_reobservation_never_advances_first_seen_at(monkeypatch):
    """K14: re-observing a name on a LATER session must not advance
    first_seen_at — it must carry forward the EARLIEST stamped_at ever
    recorded for that (security_ref, challenger_definition). Dates derived
    from the live wall clock (M6/m1 date-bomb fix, review round 2): fixed
    calendar dates eventually fall outside K8b's wall-clock settle window
    relative to the REAL current date and start failing for a reason
    unrelated to K14."""
    _lane_on(monkeypatch, "CA")
    today = dt.datetime.now(dt.timezone.utc).date()
    day1 = (today - dt.timedelta(days=1)).isoformat()
    day2 = today.isoformat()

    bs.register_challenger("disc_v1", discovery_fn=_discovery_fn_factory(
        [{"session_date": day1, "security_ref_raw": "AAA", "candidate_origin": "a"}]))
    r1 = bs.write_shadow([], market="CA", asof=day1)
    assert r1["written"] > 0  # POSITIVE CONTROL
    frame1 = _lane_b_frame("CA")
    first_seen_day1 = frame1.loc[frame1["session_date"] == day1, "first_seen_at"].iloc[0]

    bs.CHALLENGER_REGISTRY.clear()
    bs.register_challenger("disc_v1", discovery_fn=_discovery_fn_factory(
        [{"session_date": day2, "security_ref_raw": "AAA", "candidate_origin": "a"}]))
    r2 = bs.write_shadow([], market="CA", asof=day2)
    assert r2["written"] > 0
    frame2 = _lane_b_frame("CA")
    first_seen_day2_row = frame2.loc[frame2["session_date"] == day2, "first_seen_at"].iloc[0]

    assert first_seen_day2_row == first_seen_day1, "first_seen_at must carry the EARLIEST stamp, never advance"
    assert len(frame2) == 2, "append-only: the day1 row must still be present as its own row"


def test_k14_first_seen_at_is_a_true_min_under_clock_skew(monkeypatch, tmp_path):
    """n2 (review round 2 clock-skew correction): first_seen_at must be a
    TRUE min(prior_min, stamped_at), not 'prior_min if it exists' — the
    earlier shape silently assumed prior_min always precedes today's write
    clock, true only in the ordinary forward-flowing case. Hand-seeds a Lane
    B store whose existing first_seen_at is artificially in the FUTURE
    relative to `stamped_at` (a clock-skew stand-in), then performs a real
    write and asserts the result is the earlier of the two, not the
    (incorrectly later) prior value.

    MUTATION THIS KILLS: `prior_min if prior_min else stamped_at` (returns
    the future prior_min unconditionally whenever one exists)."""
    data_root = tmp_path / "data"
    monkeypatch.setattr(config, "data_dir", lambda: data_root)
    _lane_on(monkeypatch, "CA")
    today = dt.datetime.now(dt.timezone.utc).date().isoformat()

    future_first_seen = "2099-01-01T00:00:00+00:00"  # deliberately "in the future"
    path = bs._lane_b_path("CA")
    path.parent.mkdir(parents=True, exist_ok=True)
    seed = pd.DataFrame([{
        "session_date": (dt.datetime.now(dt.timezone.utc).date() - dt.timedelta(days=1)).isoformat(),
        "market": "CA", "security_ref": "AAA", "security_ref_raw": "AAA",
        "ref_collision_n": 1, "challenger_definition": "disc_v1",
        "candidate_origin": "a", "first_seen_at": future_first_seen,
        "availability_status": None, "availability_source": None,
        "visible_to_user": False, "published_authority": False,
        "stamped_at": future_first_seen,
    }])
    seed.to_parquet(path, index=False)

    bs.register_challenger("disc_v1", discovery_fn=_discovery_fn_factory(
        [{"session_date": today, "security_ref_raw": "AAA", "candidate_origin": "a"}]))
    result = bs.write_shadow([], market="CA", asof=today)
    assert result["written"] > 0  # POSITIVE CONTROL

    frame = _lane_b_frame("CA")
    new_row = frame.loc[frame["session_date"] == today]
    assert len(new_row) == 1
    written_first_seen = new_row["first_seen_at"].iloc[0]
    assert written_first_seen < future_first_seen, (
        "first_seen_at must be the EARLIER of prior_min and today's stamped_at "
        f"— got {written_first_seen!r}, which is not earlier than the seeded "
        f"future prior_min {future_first_seen!r}"
    )


# ---------------------------------------------------------------------------
# Standing clauses — registry_state distinguishability (F16) + lane gates
# ---------------------------------------------------------------------------
def test_empty_registry_is_distinguishable_from_a_broken_writer(monkeypatch, caplog):
    """F16: an on-lane pass with NOTHING registered must log
    registry_state=no_challenger_registered — an empty store must be
    distinguishable from a broken writer, not silently indistinguishable."""
    _lane_on(monkeypatch, "CA")
    with caplog.at_level("INFO"):
        result = bs.write_shadow(_population(), market="CA", asof="2026-08-21")
    assert result["registry_state"] == "no_challenger_registered"
    assert result["written"] == 0


def test_populated_pass_logs_wrote_n_rows(monkeypatch):
    """F16 mirror: a populated pass logs registry_state=wrote_n_rows n=<n>."""
    _lane_on(monkeypatch, "CA")
    calls = _population()
    _seed_board_ledger(monkeypatch, "CA", "2026-08-21", calls)
    _register_adversarial()
    result = bs.write_shadow(calls, market="CA", asof="2026-08-21")
    assert result["registry_state"].startswith("wrote_n_rows n=")
    assert result["written"] > 0


def test_off_lane_ca_is_a_fail_soft_no_op(monkeypatch):
    """Lane gate (contract §4): CA writes only under COLLECT_LANE=nightly.
    Off-lane must be a silent (log-only), fail-closed no-op — never a raise."""
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    monkeypatch.delenv("CN_LANE", raising=False)
    _register_adversarial()
    result = bs.write_shadow(_population(), market="CA", asof="2026-08-21")
    assert result["written"] == 0
    assert result["registry_state"] == "off_lane"


def test_off_lane_hk_is_a_fail_soft_no_op(monkeypatch):
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    monkeypatch.delenv("CN_LANE", raising=False)
    _register_adversarial()
    result = bs.write_shadow(_population(), market="HK", asof="2026-08-21")
    assert result["written"] == 0
    assert result["registry_state"] == "off_lane"


def test_ledger_lane_import_failure_is_fail_closed(monkeypatch):
    """Contract §4: an import failure of engine.ledger_lane is treated as
    off-lane (fail-closed), never as on-lane-by-default."""
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    monkeypatch.setitem(sys.modules, "engine.ledger_lane", None)
    try:
        _register_adversarial()
        result = bs.write_shadow(_population(), market="CA", asof="2026-08-21")
        assert result["written"] == 0
        assert result["registry_state"] == "off_lane"
    finally:
        monkeypatch.delitem(sys.modules, "engine.ledger_lane", raising=False)


def test_write_shadow_never_raises_on_a_hostile_registered_challenger(monkeypatch):
    """Fail-soft law: a challenger whose rank_fn raises must never break the
    build — write_shadow degrades to null-scored rows (or zero rows) and
    continues, never propagating the exception."""
    _lane_on(monkeypatch, "CA")
    _seed_board_ledger(monkeypatch, "CA", "2026-08-21", _population())

    def _boom(_calls):
        raise RuntimeError("boom")

    bs.register_challenger("boom_v1", rank_fn=_boom)
    result = bs.write_shadow(_population(), market="CA", asof="2026-08-21")  # must not raise
    assert result["registry_state"].startswith("wrote_n_rows")
    frame = _lane_a_frame("CA")
    if frame is not None and len(frame):
        assert frame["challenger_score_raw"].isna().all(), "a raising rank_fn must yield null scores, never fabricated ones"


# ---------------------------------------------------------------------------
# Cross-store validator (F15) — the compensating invariant for a
# separately-keyed Lane A rather than a paired row.
# ---------------------------------------------------------------------------
def test_cross_store_validator_clean_case(monkeypatch):
    """F15: every Lane-A (date, ticker) exists in board_ledger with matching
    board_pos and board_definition, in the ordinary case."""
    _lane_on(monkeypatch, "CA")
    calls = _population()
    _seed_board_ledger(monkeypatch, "CA", "2026-08-21", calls)
    _register_adversarial()
    bs.write_shadow(calls, market="CA", asof="2026-08-21")
    violations = bs.validate_lane_a_against_board_ledger("CA")
    assert violations == [], violations


def test_cross_store_validator_catches_a_mismatch():
    """Mutation-kill proof: hand-craft a Lane A row whose incumbent_rank
    disagrees with board_ledger's board_pos, and assert the validator flags
    it — the compensating invariant a separately-keyed lane needs in place of
    a paired row's for-free guarantee (DEC:PROPHET-SHADOW-GRAIN-IS-A-PAIRED-ROW)."""
    board_path = board_ledger._store_path("CA")
    board_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([
        {"date": "2026-08-21", "ticker": "AAA", "board_pos": 1, "board_definition": "test_board_v1"},
    ]).to_parquet(board_path, index=False)

    lane_a_path = bs._lane_a_path("CA")
    lane_a_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([
        {"date": "2026-08-21", "market": "CA", "ticker": "AAA",
         "incumbent_definition": "test_board_v1", "incumbent_rank": 99,  # WRONG — should be 1
         "challenger_definition": "x"},
    ]).to_parquet(lane_a_path, index=False)

    violations = bs.validate_lane_a_against_board_ledger("CA")
    assert violations, "a rank mismatch between Lane A and board_ledger must be flagged"


# ---------------------------------------------------------------------------
# Denylist exemption precision (contract §1 parenthetical)
# ---------------------------------------------------------------------------
def test_visible_and_published_literal_names_are_exempt_but_the_pattern_still_denies():
    """The two pinned literal-False columns are exempt by EXACT NAME only —
    anything else matching visible*/published* is still denied."""
    assert not bs._is_denylisted("visible_to_user")
    assert not bs._is_denylisted("published_authority")
    assert bs._is_denylisted("visible_to_admin")
    assert bs._is_denylisted("published_score")


def test_lane_b_carries_the_two_literal_false_columns(monkeypatch):
    _lane_on(monkeypatch, "CA")
    today = dt.datetime.now(dt.timezone.utc).date().isoformat()
    bs.register_challenger("disc_v1", discovery_fn=_discovery_fn_factory(
        [{"session_date": today, "security_ref_raw": "AAA", "candidate_origin": "a"}]))
    bs.write_shadow([], market="CA", asof=today)
    frame = _lane_b_frame("CA")
    assert set(frame["visible_to_user"]) == {False}
    assert set(frame["published_authority"]) == {False}


# ---------------------------------------------------------------------------
# Static wiring-order guard (contract §4): "A refactor that hoists either call
# upstream of its market's artifact write is a contract breach even if bytes
# happen to match" — a runtime harness cannot see a refactor that happens to
# still produce identical bytes today, so this pins the TEXTUAL ordering.
# ---------------------------------------------------------------------------
def test_ca_shadow_call_is_textually_downstream_of_append_board_and_track_ledger():
    source = (ROOT / "scripts" / "build_canada.py").read_text()
    i_append = source.index('board_ledger.append_board(calls, market="CA"')
    i_track_ledger = source.index('_tl.atomic_write(_ca_site / "factordata" / "ca_track_ledger.json"')
    i_shadow = source.index('board_shadow.write_shadow(calls, market="CA"')
    assert i_append < i_track_ledger < i_shadow, (
        "the CA shadow call must stay textually downstream of append_board AND "
        "the track_ledger emit — hoisting it earlier is a contract breach even "
        "if today's bytes happen to still match"
    )


def test_hk_shadow_call_is_textually_downstream_of_the_standouts_json_write():
    source = (ROOT / "scripts" / "build_hk_library.py").read_text()
    i_append = source.index('board_ledger.append_board(calls, market="HK"')
    i_json_write = source.index('(fdir / "hk_standouts.json").write_text(')
    i_shadow = source.index('board_shadow.write_shadow(calls, market="HK"')
    assert i_append < i_json_write < i_shadow, (
        "the HK shadow call must stay textually downstream of the "
        "hk_standouts.json write, never beside the upstream append_board site "
        "— that upstream placement is the named F1 contract breach"
    )
