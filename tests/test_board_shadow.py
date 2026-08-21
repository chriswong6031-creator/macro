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
    """K1 CA leg (F1/F2). Byte-identity harness over everything DOWNSTREAM of
    the CA shadow call site, using the REAL production wiring function
    (scripts.build_canada._canada_board_ledger — the exact code path the
    contract wires the shadow call into), across four variants:
    shadow module absent / present-empty / present-with-adversarial-
    challenger (non-vacuous order) / present-with-a-mutating-writer.

    The 'must FAIL' language in contract §6 K1 describes what this test
    catches under mutation (e.g. removing write_shadow's deep-copy of the
    population): with F1's protection in place, all four variants must be
    byte-identical on both halves of the identity set this narrow harness
    covers — setups["buy"]/["board_track"] (the JSON body that becomes
    canada_standouts.json) and data/board_ledger/ca_board.parquet (the CA
    slice of K1's named identity set). The template-rendered HTML pages named
    in the contract's identity set are NOT exercised here (see DEVIATIONS in
    the build packet) — a full render needs the live site template + data
    tree this sparse suite does not check out.
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


def test_k1_hk_zero_authority_and_aliasing_unit_level(monkeypatch):
    """K1 HK leg (F1/F2), UNIT-LEVEL SCOPE. build_hk_library.compute_hk_standouts
    reads real per-ticker chart JSON from site/hkstockdata/ through several
    other engine modules (dispersion/entry_signal/extension/risk_sizing/
    hk_ah/hk_southbound_stocks/hk_stock_signals) and cannot be exercised
    end-to-end without the full checked-out data/site tree (F18) — see
    DEVIATIONS. This test instead exercises the SAME aliasing/byte-identity
    property at the exact granularity build_hk_library's wiring call
    operates on: an `out` dict holding the same `calls`/`buy` list object
    passed to append_board, mirroring the real call site's shape
    (`out["buy"] = calls`, board_shadow.write_shadow(calls, ...) called after).
    """
    _lane_on(monkeypatch, "HK")
    calls = _population()
    out = {"buy": calls, "board_definition": "hk_prophet_v1"}
    before = json.dumps(out, sort_keys=True, default=str)

    _seed_board_ledger(monkeypatch, "HK", "2026-08-21", calls)

    identity_checks: dict = {}

    def _hostile_rank_fn(inner_calls):
        # F1 aliasing assertion (contract §4, explicit part of K1): the
        # object the writer works with must share NO identity with the
        # caller's `calls` (== out["buy"]) list or any of its rows.
        identity_checks["list_is_same"] = inner_calls is calls
        identity_checks["row0_is_same"] = (
            len(inner_calls) > 0 and len(calls) > 0 and inner_calls[0] is calls[0]
        )
        inner_calls[0]["ticker"] = "HACKED"
        return _reversed_rank_fn(inner_calls)

    bs.register_challenger("hostile_v1", rank_fn=_hostile_rank_fn)
    result = bs.write_shadow(calls, market="HK", asof="2026-08-21")
    assert result["written"] > 0  # POSITIVE CONTROL

    assert identity_checks == {"list_is_same": False, "row0_is_same": False}, (
        "write_shadow's F1 deep-copy must give the challenger an object graph "
        "sharing NO identity with the caller's population"
    )
    after = json.dumps(out, sort_keys=True, default=str)
    assert before == after, "the artifact dict holding `calls` must be byte-identical after write_shadow"
    assert out["buy"][0]["ticker"] == "AAA", "the hostile challenger must never mutate the caller's population"


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
    """K3(ii): monkeypatch pandas.read_parquet to raise for anything that is
    NOT the sanctioned board_ledger read-back path, and assert a full
    positive-control writer pass still succeeds — the writer's own execution
    never depends on reading anything else.
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

    # Seed the shadow store's own prior state via the real path BEFORE arming
    # the guard, then register the challenger and run under the guard.
    monkeypatch.setattr(bs.pd, "read_parquet", _guarded_read_parquet)
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
#: Pre-existing, unrelated uses of the exact literal 'prophet_shadow' that
#: predate this contract and name a DIFFERENT feature (US board_rank's
#: retired-v2-scorer `row["prophet_shadow"]` leg block, and the standalone
#: options-flow schema string 'options.prophet_shadow/v1'). A blind substring
#: scan for 'prophet_shadow' collides with these unconditionally — they are
#: not a store-path reference and cannot leak this module's store. Allowlisted
#: by FILE (not by count) so a NEW hit anywhere in these files (beyond the
#: already-audited occurrences) still fails loudly the moment the file grows
#: an actual reference to this module's store.
#: {file: (audited occurrence count, reason)} — PINNED, not just allowlisted:
#: a new occurrence beyond this exact count still fails, so the exemption
#: cannot silently absorb a genuinely new store-path reference.
_K6_PREEXISTING_UNRELATED_FILES = {
    "engine/us_board_rank.py": (9, (
        "US C1 fusion override's own `prophet_shadow` dict key (the retired "
        "v2 scorer's legs), unrelated to engine/board_shadow.py — see that "
        "module's own SHADOW_COLUMNS-style docstring."
    )),
    "engine/us_context_vector.py": (16, (
        "reads/documents the same US `prophet_shadow` dict key above via "
        "us_board_rank; same unrelated feature."
    )),
    "scripts/build_options_prophet.py": (2, (
        "options-flow schema literal 'options.prophet_shadow/v1' — an "
        "unrelated schema name that happens to share the substring."
    )),
    "scripts/mirror_flow_idx.py": (1, (
        "reads the same options-flow schema literal above."
    )),
    "engine/us_prophet_w3.py": (16, (
        "US W3 evidence module's own `prophet_shadow` dict key family "
        "(same US fusion-override feature as us_board_rank.py above)."
    )),
    "engine/us_candidate_lanes.py": (3, (
        "reads the same US `prophet_shadow` dict key family above."
    )),
    "scripts/us_prophet_fusion_compare.py": (7, (
        "compares the US `prophet_shadow` dict key family above — a fusion "
        "research script, not this module's caller."
    )),
    "engine/cn_theme_tape.py": (1, (
        "names the DIFFERENT, pre-existing engine/china_prophet_shadow.py "
        "module (substring collision: 'china_prophet_shadow' contains "
        "'prophet_shadow') — not this contract's engine/board_shadow.py."
    )),
    "engine/prophet_bridge.py": (1, (
        "`prophet_shadow.score` — the same US retired-v2-scorer dict key "
        "above, read from the bridge module."
    )),
    "scripts/build_china_library.py": (1, (
        "`from engine import china_prophet_shadow` — the different, "
        "pre-existing CN shadow module (substring collision as above)."
    )),
}


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
    board_rank fusion-override dict key and the options-flow schema string
    (see _K6_PREEXISTING_UNRELATED_FILES) — a blind scan as literally
    specified is permanently red from day one regardless of this module.
    Those files are allowlisted explicitly (by file, not by count) rather
    than weakening the scan generally, so any NEW occurrence in them still
    fails.

    MUTATION THIS KILLS: any production module importing
    engine.board_shadow / referencing 'prophet_shadow' by name (e.g. a
    template or admin page rendering the store path), OR a new reference
    added to one of the allowlisted pre-existing files."""
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
            hits = text.count("prophet_shadow")
            if not hits:
                continue
            if rel in _K6_PREEXISTING_UNRELATED_FILES:
                expected_count, _reason = _K6_PREEXISTING_UNRELATED_FILES[rel]
                if hits > expected_count:
                    offenders.append(
                        f"{rel} (audited={expected_count}, found={hits} — "
                        "a NEW reference appeared beyond the pinned pre-existing count)"
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
    refused. MUTATION THIS KILLS: drop the `session_date != asof` check."""
    _lane_on(monkeypatch, "CA")
    rows = [{"session_date": "2026-08-01", "security_ref_raw": "AAA",
              "candidate_origin": "test"}]
    bs.register_challenger("disc_v1", discovery_fn=_discovery_fn_factory(rows))
    result = bs.write_shadow([], market="CA", asof="2026-08-21")
    frame = _lane_b_frame("CA")
    assert frame is None or frame.empty
    assert result["written"] == 0


def test_k8a_positive_control_matching_asof_writes(monkeypatch):
    """Positive control for K8a: a row whose session_date DOES match asof
    must actually write — otherwise K8a would pass vacuously."""
    _lane_on(monkeypatch, "CA")
    rows = [{"session_date": "2026-08-21", "security_ref_raw": "AAA",
              "candidate_origin": "test"}]
    bs.register_challenger("disc_v1", discovery_fn=_discovery_fn_factory(rows))
    result = bs.write_shadow([], market="CA", asof="2026-08-21")
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
def test_k9_ref_collision_is_counted_and_kept(monkeypatch):
    """K9 (F11): two distinct raw refs canonicalising to one security_ref in
    one session must be COUNTED (ref_collision_n) and both observations kept
    — never silently collapsed to one row."""
    _lane_on(monkeypatch, "CA")
    today = dt.datetime.now(dt.timezone.utc).date().isoformat()
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


def test_k9_non_colliding_refs_stay_separate(monkeypatch):
    """K9 mirror kill: two refs that do NOT canonicalize together must not be
    merged (ref_collision_n == 1 for each)."""
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
    1..population_n rank that pretends everyone was scored."""
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
    recorded for that (security_ref, challenger_definition)."""
    _lane_on(monkeypatch, "CA")
    day1 = "2026-08-19"
    day2 = "2026-08-20"

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
