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
# Shared session date
# ---------------------------------------------------------------------------
# ``write_shadow`` stamps itself from the real wall clock and refuses any row
# whose ``session_date`` trails that stamp by more than
# ``bs.SETTLE_WINDOW_DAYS`` (K8b/F10).  A hard-coded session date is therefore a
# time bomb: it passes until it ages out, then every POSITIVE CONTROL in this
# file -- the arms that assert the writer wrote > 0 rows -- flips red on a UTC
# date rollover with no commit anywhere near this substrate.  A literal
# ``2026-08-21`` did exactly that at 2026-08-25T00:00Z, reddening
# ``board-shadow-substrate`` on main and on every branch cut from it.  Deriving
# the date from the clock keeps the settle-window fence itself under test --
# the ancient ``2020-01-01`` stale-refusal control below is deliberately NOT
# derived, so the negative arm still proves the fence refuses.
ASOF = (dt.date.today() - dt.timedelta(days=1)).isoformat()


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
    # Lane B stamps with _now_iso(). Several tests still pass asof="2026-08-21".
    # SETTLE_WINDOW_DAYS is 3, so a live UTC date of 2026-08-25 refuses those
    # rows (wallclock_fence) even though the tests are not about the fence.
    # Pin the stamp to the fixture asof. test_k8a/k8c keep live session dates;
    # a stamp earlier than session_date is not a settle violation.
    monkeypatch.setattr(bs, "_now_iso", lambda: "2026-08-21T12:00:00+00:00")
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


def _register_adversarial(definition: str = "adv_challenger_v1", market: str = "CA") -> None:
    bs.register_challenger(market, definition, rank_fn=_reversed_rank_fn)


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
        latest = {"date": ASOF}
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
        absent=False, register=lambda: bs.register_challenger("CA", "hostile_v1", rank_fn=_hostile_rank_fn)
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
    _seed_board_ledger(monkeypatch, "CA", ASOF, _population())
    _register_adversarial()
    result = bs.write_shadow(_population(), market="CA", asof=ASOF)
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

    _seed_board_ledger(monkeypatch, "HK", ASOF, calls)

    def _hostile_rank_fn(inner_calls):
        inner_calls[0]["ticker"] = "HACKED"  # attempt to mutate the writer's population
        return _reversed_rank_fn(inner_calls)

    bs.register_challenger("HK", "hostile_v1", rank_fn=_hostile_rank_fn)
    result = bs.write_shadow(calls, market="HK", asof=ASOF)
    assert result["written"] > 0  # POSITIVE CONTROL

    after = json.dumps(out, sort_keys=True, default=str)
    assert before == after, "out['buy'] (== buys) must be byte-identical after write_shadow"
    assert out["buy"][0]["ticker"] == "AAA", "buys must never be touched — it never shared identity with calls"


def _offenders_for_market(changed: set[str], market: str) -> list[str]:
    """D3 (MAJOR, m2 fence was market-blind): the write-surface fence
    predicate. A changed path is lawful ONLY if it lies under
    data/prophet_shadow/ AND its basename belongs to THIS market (starts
    with ``<market.lower()>_``) — the pre-fix fence checked only the
    prophet_shadow/ prefix, so a CA pass that also wrote
    hk_discovery.parquet (reviewer probe G2) passed green. Factored out so
    the market-scoping logic itself is directly, unit-testably killable
    (see test_write_surface_fence_trips_on_a_foreign_market_file below),
    independent of whether write_shadow itself ever actually produces a
    foreign-market write today."""
    prefix = f"{market.lower()}_"
    offenders: list[str] = []
    for p in sorted(changed):
        if p == "prophet_shadow":
            continue
        if not p.startswith("prophet_shadow/"):
            offenders.append(p)
            continue
        if not Path(p).name.startswith(prefix):
            offenders.append(p)
    return offenders


def test_write_surface_fence_only_data_prophet_shadow_is_touched(tmp_path, monkeypatch):
    """m2 (M5, review round 2) + D3 market-scoping repair. Snapshots every
    file under the tmp data root before and after a positive-control
    write_shadow pass and asserts every path CREATED or MODIFIED lies under
    data/prophet_shadow/ AND belongs to the market under test. This closes
    the residual channel the review proved live: neither K1's byte-identity
    harness (which only compares the PUBLISHED artifact + board_ledger's own
    store, and — per the corrected docstrings above — cannot even see an
    aliasing violation in the CA/HK object graphs as they actually exist)
    nor K6's static string fence (which only catches the literal
    'prophet_shadow', not an arbitrary stray write) would notice a writer
    that also emits, say, `pd.DataFrame(...).to_parquet(data/hk_pick_lab/x.parquet)`
    — a write entirely outside this module's own two lanes. D3 additionally
    closes the market-blind gap the m2 fence itself had: a CA pass writing
    into `data/prophet_shadow/hk_discovery.parquet` (reviewer probe G2) used
    to pass this fence green because that path still starts with
    `prophet_shadow/`.

    MUTATION THIS KILLS: adding any write inside write_shadow/_write_lane_a/
    _write_lane_b/_merge_write_lane_a/_merge_write_lane_b that targets a path
    outside data/prophet_shadow/, OR that targets a foreign-market file
    inside data/prophet_shadow/ (e.g. a CA pass touching hk_*.parquet).
    """
    data_root = tmp_path / "data"
    monkeypatch.setattr(config, "data_dir", lambda: data_root)
    _lane_on(monkeypatch, "CA")
    calls = _population()
    # Seed board_ledger's own store FIRST (a legitimate prior write) so its
    # mtime/size are already part of the "before" snapshot — write_shadow
    # itself must not re-touch it either.
    n = board_ledger.append_board(copy.deepcopy(calls), market="CA", asof=ASOF)
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
    result = bs.write_shadow(calls, market="CA", asof=ASOF)
    assert result["written"] > 0  # POSITIVE CONTROL
    after = _snapshot()

    changed = {p for p in (set(before) | set(after)) if before.get(p) != after.get(p)}
    offenders = _offenders_for_market(changed, "CA")
    assert not offenders, (
        f"write_shadow touched path(s) outside CA's own data/prophet_shadow/ files: {offenders}"
    )
    # Sanity: the positive control DID write something under prophet_shadow/,
    # so this is not passing merely because nothing happened on disk.
    assert any(p.startswith("prophet_shadow/") for p in changed), (
        "positive control: the write must actually touch data/prophet_shadow/"
    )


def test_write_surface_fence_trips_on_a_foreign_market_file():
    """D3 executed kill (reviewer probe G2 shape): a CA pass whose changed-file
    set includes a foreign-market file under prophet_shadow/ (e.g.
    hk_discovery.parquet) must be flagged as an offender by the fence
    predicate, not waved through. The pre-fix predicate
    (`not p.startswith('prophet_shadow/')`) would have passed this shape
    green — it only ever checked the directory prefix, never which market
    the file belongs to."""
    changed = {
        "prophet_shadow/ca_rank_pairs.parquet",
        "prophet_shadow/hk_discovery.parquet",  # foreign-market file — must trip the fence
    }
    offenders = _offenders_for_market(changed, "CA")
    assert offenders == ["prophet_shadow/hk_discovery.parquet"]

    # Mirror: an HK pass must equally reject a foreign CA file, and a
    # same-market file must never be flagged.
    offenders_hk = _offenders_for_market(
        {"prophet_shadow/hk_discovery.parquet", "prophet_shadow/ca_rank_pairs.parquet"}, "HK",
    )
    assert offenders_hk == ["prophet_shadow/ca_rank_pairs.parquet"]


def test_write_surface_fence_only_data_prophet_shadow_is_touched_hk(tmp_path, monkeypatch):
    """R8 (F8, build commission): the HK arm of the REAL snapshot write-surface
    fence — mirrors test_write_surface_fence_only_data_prophet_shadow_is_touched
    above (CA, Lane A) but exercises HK's Lane B DISCOVERY write (the
    hk_discovery_v1 registration + its receipt), a path the CA arm above never
    touches at all. Same before/after filesystem snapshot technique: every
    path CREATED or MODIFIED by a real write_shadow(market="HK") pass must lie
    under data/prophet_shadow/ and carry the hk_ market prefix.

    This is the REAL fence R8 asks for — unlike
    test_write_surface_fence_accepts_the_hk_discovery_receipt_path below
    (fixed by this same commission to stop claiming it is this test), the
    `changed` set here comes from an actual before/after directory walk, never
    a hand-written literal.

    MUTATION THIS KILLS: adding any write inside the HK discovery path
    (_write_lane_b / _merge_write_lane_b / _write_discovery_receipt) that
    targets a path outside data/prophet_shadow/, or a foreign-market
    (ca_-prefixed) file.
    """
    data_root = tmp_path / "data"
    monkeypatch.setattr(config, "data_dir", lambda: data_root)
    _lane_on(monkeypatch, "HK")

    def _snapshot() -> dict[str, tuple[int, int]]:
        if not data_root.exists():
            return {}
        return {
            str(p.relative_to(data_root)): (p.stat().st_mtime_ns, p.stat().st_size)
            for p in data_root.rglob("*") if p.is_file()
        }

    before = _snapshot()
    bs.register_challenger("HK", "hk_discovery_v1", discovery_fn=_discovery_fn_ok)
    result = bs.write_shadow([], market="HK", asof=ASOF)
    assert result["written"] > 0  # POSITIVE CONTROL
    after = _snapshot()

    changed = {p for p in (set(before) | set(after)) if before.get(p) != after.get(p)}
    offenders = _offenders_for_market(changed, "HK")
    assert not offenders, (
        f"write_shadow(HK) touched path(s) outside HK's own data/prophet_shadow/ "
        f"files: {offenders}"
    )
    assert any(p.startswith("prophet_shadow/") for p in changed), (
        "positive control: the write must actually touch data/prophet_shadow/"
    )
    assert "prophet_shadow/hk_discovery_receipt.json" in changed, (
        "a real HK pass writes the receipt too — this fence must see it, not "
        "just the Lane B parquet"
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
    _seed_board_ledger(monkeypatch, "CA", ASOF, calls)

    def _rank_fn(_calls):
        base = _reversed_rank_fn(_calls)
        base["ZZZ_OFFLIST"] = {"score_raw": 999.0, "score_conservative": 999.0}
        return base

    bs.register_challenger("CA", "offlist_v1", rank_fn=_rank_fn)
    result = bs.write_shadow(calls, market="CA", asof=ASOF)
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
    _seed_board_ledger(monkeypatch, "CA", ASOF, calls)
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
    result = bs.write_shadow(calls, market="CA", asof=ASOF)
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
    _seed_board_ledger(monkeypatch, "CA", ASOF, calls)
    _register_adversarial()
    result = bs.write_shadow(calls, market="CA", asof=ASOF)
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
    _seed_board_ledger(monkeypatch, "CA", ASOF, calls)

    def _partial_rank_fn(_calls):
        # Only scores AAA and BBB — CCC/DDD are unscored (missing, not 0).
        return {
            "AAA": {"score_raw": 5.0, "score_conservative": 4.5},
            "BBB": {"score_raw": 3.0, "score_conservative": 2.5},
        }

    bs.register_challenger("CA", "partial_v1", rank_fn=_partial_rank_fn)
    result = bs.write_shadow(calls, market="CA", asof=ASOF)
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
    # hk-discovery wave: scripts/check_surface_freshness.py's ONE reviewed
    # reference — a module-level path CONSTANT naming the additive
    # hk_discovery_receipt.json (never the Lane A/B stores themselves), the
    # contract §4 "surface-freshness absent-vs-stale vocabulary" wiring.
    "freshness_receipt_path": re.compile(
        r'"data/prophet_shadow/hk_discovery_receipt\.json"'
    ),
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

#: {file: (allowed form names, reason)} — files whose 'prophet_shadow'
#: occurrence is NOT pre-existing/unrelated (unlike every entry in
#: _K6_PREEXISTING_UNRELATED_FILES above): it is a REVIEWED READER this
#: contract itself sanctions, added and audited as part of THIS wave.
#: Re-filed here out of _K6_PREEXISTING_UNRELATED_FILES (build commission
#: R10/F13) — that dict's own name/docstring claims "pre-existing,
#: unrelated" code, which this file's occurrence never was: it is
#: scripts/check_surface_freshness.py's own sanctioned, contract-cited read
#: of engine/board_shadow.py's additive receipt, filed under the same name
#: as genuinely unrelated pre-existing collisions was itself a mis-filing.
#: Merged into the same fence below via _K6_ALL_ALLOWLISTED_FILES — the
#: per-file pinned-token-form mechanism (M2's fix) is unchanged; only the
#: bookkeeping of WHICH dict a file's entry lives in changed.
_K6_REVIEWED_READER_FILES: dict[str, tuple[tuple[str, ...], str]] = {
    "scripts/check_surface_freshness.py": (("freshness_receipt_path",), (
        "hk-discovery wave (WS:PROPHET-HK-CA-REVAMP): the sanctioned "
        "surface-freshness reader of engine/board_shadow.py's OWN additive "
        "hk_discovery_receipt.json — contract §4's 'when a challenger "
        "registers, the store paths get wired into the surface-freshness "
        "absent-vs-stale vocabulary' clause names exactly this. It never "
        "reads the Lane A/B parquet stores themselves, so it is not the "
        "production-reader leak K6 exists to catch."
    )),
}

#: The fence's actual per-file lookup — every file excused from the raw K6
#: walk, regardless of WHY (pre-existing-unrelated vs. reviewed-reader). Never
#: read _K6_PREEXISTING_UNRELATED_FILES or _K6_REVIEWED_READER_FILES directly
#: at the scan site below; this union is the one source of truth for "is this
#: file excused, and under which forms".
_K6_ALL_ALLOWLISTED_FILES: dict[str, tuple[tuple[str, ...], str]] = {
    **_K6_PREEXISTING_UNRELATED_FILES,
    **_K6_REVIEWED_READER_FILES,
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
    scripts/check_surface_freshness.py is excused too, but is filed
    separately in _K6_REVIEWED_READER_FILES (build commission R10/F13): it is
    a REVIEWED READER this contract itself sanctions, not a pre-existing
    coincidence, so it does not belong in the "pre-existing, unrelated" dict
    above. Both dicts merge into _K6_ALL_ALLOWLISTED_FILES, which is what the
    scan below actually reads.

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
            if not path.is_file():
                continue
            # prune on the path RELATIVE to the scan root, never the absolute
            # path — an absolute-part prune also matches anything ABOVE the
            # root and silently skips every file in a .claude/worktrees/<name>/
            # checkout (#3802; pinned by test_no_absolute_path_part_prunes).
            if "__pycache__" in path.relative_to(root).parts:
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
            if rel in _K6_ALL_ALLOWLISTED_FILES:
                allowed_forms, _reason = _K6_ALL_ALLOWLISTED_FILES[rel]
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
    _seed_board_ledger(monkeypatch, "CA", ASOF, calls)
    board_path = board_ledger._store_path("CA")
    before = pd.read_parquet(board_path)

    _register_adversarial()
    result = bs.write_shadow(calls, market="CA", asof=ASOF)
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
    bs.register_challenger("CA", "disc_v1", discovery_fn=_discovery_fn_factory(rows))
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
    bs.register_challenger("CA", "disc_v1", discovery_fn=_discovery_fn_factory(rows))
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
    bs.register_challenger("CA", "disc_v1", discovery_fn=_discovery_fn_factory(rows))
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

    bs.register_challenger("CA", "disc_v1", discovery_fn=_discovery_fn_factory(
        [{"session_date": newer, "security_ref_raw": "AAA", "candidate_origin": "test"}]))
    result = bs.write_shadow([], market="CA", asof=newer)
    assert result["written"] > 0  # POSITIVE CONTROL — establishes the head

    bs.CHALLENGER_REGISTRY.clear()
    bs.register_challenger("CA", "disc_v1", discovery_fn=_discovery_fn_factory(
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
    bs.register_challenger("CA", "disc_v1", discovery_fn=_discovery_fn_factory(rows))
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
    bs.register_challenger("CA", "disc_v1", discovery_fn=_discovery_fn_factory(
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
    bs.register_challenger("CA", "disc_v1", discovery_fn=_discovery_fn_factory(rows))
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
    _seed_board_ledger(monkeypatch, "CA", ASOF, calls)

    def _rank_fn(_calls):
        return {"AAA": {"score_raw": 1.0}, "BBB": {"score_raw": 2.0}}  # 2 of 4 scored

    bs.register_challenger("CA", "cov_v1", rank_fn=_rank_fn)
    result = bs.write_shadow(calls, market="CA", asof=ASOF)
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
        {"date": ASOF, "market": "CA", "ticker": "AAA",
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
    _seed_board_ledger(monkeypatch, "CA", ASOF, calls_with_gap)
    board_frame = pd.read_parquet(board_ledger._store_path("CA"))
    real_positions = dict(zip(board_frame["ticker"].astype(str), board_frame["board_pos"]))
    assert real_positions == {"AAA": 2, "BBB": 3}  # the gap at pos=1 is real, not a bug

    _register_adversarial()
    result = bs.write_shadow(calls_with_gap, market="CA", asof=ASOF)
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
    _seed_board_ledger(monkeypatch, "CA", ASOF, calls)

    def _rank_fn(_calls):
        # Only 2 of 4 scored, with a TIE, to also assert dense (not skip) ranking.
        return {
            "AAA": {"score_raw": 5.0},
            "BBB": {"score_raw": 5.0},  # tie with AAA
        }

    bs.register_challenger("CA", "dense_v1", rank_fn=_rank_fn)
    result = bs.write_shadow(calls, market="CA", asof=ASOF)
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

    bs.register_challenger("CA", "disc_v1", discovery_fn=_discovery_fn_factory(
        [{"session_date": day1, "security_ref_raw": "AAA", "candidate_origin": "a"}]))
    r1 = bs.write_shadow([], market="CA", asof=day1)
    assert r1["written"] > 0  # POSITIVE CONTROL
    frame1 = _lane_b_frame("CA")
    first_seen_day1 = frame1.loc[frame1["session_date"] == day1, "first_seen_at"].iloc[0]

    bs.CHALLENGER_REGISTRY.clear()
    bs.register_challenger("CA", "disc_v1", discovery_fn=_discovery_fn_factory(
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

    bs.register_challenger("CA", "disc_v1", discovery_fn=_discovery_fn_factory(
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
# K15-K20 — market-scoped registration (post-merge Sol review correction,
# 2026-08-21). CEO Sol's post-merge review of the shadow-contract wave
# (merged fc5282f438fb, PR #6178) found CHALLENGER_REGISTRY keyed by
# challenger_definition only and write_shadow(market) iterating EVERY
# registration regardless of market — the first real registrant would have
# executed in BOTH the HK and CA lanes. Zero production registrants existed
# at merge, so no backward compatibility with the unscoped API was owed; the
# repair keys the registry (market, challenger_definition) and adds the
# market-selection seam _registrations_for(market). K15-K18 are the
# isolation kills proper (each with a POSITIVE CONTROL per the standing
# clause above); K19 is the executed mutation kill proving K15-K18 are
# load-bearing; K20 pins the four-state registry_state ladder.
# ---------------------------------------------------------------------------
def test_k15_hk_only_discovery_challenger_is_invisible_to_ca(monkeypatch):
    """K15: an HK-only discovery challenger, wrapped in a call-sentinel, must
    be structurally incapable of executing during a CA write_shadow call —
    the sentinel is never invoked and CA's Lane B store gains zero rows for
    that definition. POSITIVE CONTROL: the same registration DOES fire, and
    DOES write, under an HK call.

    MUTATION THIS KILLS: a CHALLENGER_REGISTRY keyed by challenger_definition
    alone (or write_shadow iterating the whole registry instead of
    _registrations_for(market)) — the exact shape the merged wave shipped."""
    today = dt.datetime.now(dt.timezone.utc).date().isoformat()
    invocations: list[str] = []

    def _sentinel_discovery(asof):
        invocations.append(asof)
        return [{"session_date": today, "security_ref_raw": "HKONLY", "candidate_origin": "hk"}]

    bs.register_challenger("HK", "hk_only_disc_v1", discovery_fn=_sentinel_discovery)

    # CA leg — the HK-only challenger must never fire, never write.
    _lane_on(monkeypatch, "CA")
    result_ca = bs.write_shadow([], market="CA", asof=today)
    assert invocations == [], "an HK-only discovery_fn must never be invoked by a CA write_shadow call"
    ca_frame = _lane_b_frame("CA")
    assert ca_frame is None or ca_frame.empty
    assert result_ca["registry_state"] == "no_challenger_for_market"
    assert result_ca["written"] == 0

    # POSITIVE CONTROL — the same registration fires for HK.
    _lane_on(monkeypatch, "HK")
    result_hk = bs.write_shadow([], market="HK", asof=today)
    assert invocations == [today], "the HK-only discovery_fn must be invoked exactly once by the HK call"
    hk_frame = _lane_b_frame("HK")
    assert hk_frame is not None and len(hk_frame) == 1
    assert result_hk["written"] > 0


def test_k16_ca_only_discovery_challenger_is_invisible_to_hk(monkeypatch):
    """K16: symmetric to K15 — a CA-only discovery challenger must be
    structurally incapable of executing during an HK write_shadow call."""
    today = dt.datetime.now(dt.timezone.utc).date().isoformat()
    invocations: list[str] = []

    def _sentinel_discovery(asof):
        invocations.append(asof)
        return [{"session_date": today, "security_ref_raw": "CAONLY", "candidate_origin": "ca"}]

    bs.register_challenger("CA", "ca_only_disc_v1", discovery_fn=_sentinel_discovery)

    # HK leg — the CA-only challenger must never fire, never write.
    _lane_on(monkeypatch, "HK")
    result_hk = bs.write_shadow([], market="HK", asof=today)
    assert invocations == [], "a CA-only discovery_fn must never be invoked by an HK write_shadow call"
    hk_frame = _lane_b_frame("HK")
    assert hk_frame is None or hk_frame.empty
    assert result_hk["registry_state"] == "no_challenger_for_market"
    assert result_hk["written"] == 0

    # POSITIVE CONTROL — the same registration fires for CA.
    _lane_on(monkeypatch, "CA")
    result_ca = bs.write_shadow([], market="CA", asof=today)
    assert invocations == [today], "the CA-only discovery_fn must be invoked exactly once by the CA call"
    ca_frame = _lane_b_frame("CA")
    assert ca_frame is not None and len(ca_frame) == 1
    assert result_ca["written"] > 0


def test_k17_lane_a_rank_challenger_market_isolation(monkeypatch):
    """K17: the same isolation as K15/K16, for Lane-A rank_fn challengers,
    both directions with positive controls."""
    calls = _population()
    hk_invocations: list[str] = []
    ca_invocations: list[str] = []

    def _hk_only_rank_fn(inner_calls):
        hk_invocations.append("called")
        return _reversed_rank_fn(inner_calls)

    def _ca_only_rank_fn(inner_calls):
        ca_invocations.append("called")
        return _reversed_rank_fn(inner_calls)

    bs.register_challenger("HK", "hk_only_rank_v1", rank_fn=_hk_only_rank_fn)
    bs.register_challenger("CA", "ca_only_rank_v1", rank_fn=_ca_only_rank_fn)

    # CA leg — must invoke ONLY the CA-registered rank_fn.
    _seed_board_ledger(monkeypatch, "CA", ASOF, calls)
    result_ca = bs.write_shadow(calls, market="CA", asof=ASOF)
    assert hk_invocations == [], "an HK-only rank_fn must never be invoked by a CA write_shadow call"
    assert ca_invocations == ["called"]
    assert result_ca["written"] > 0  # POSITIVE CONTROL
    ca_frame = _lane_a_frame("CA")
    assert ca_frame is not None and set(ca_frame["challenger_definition"]) == {"ca_only_rank_v1"}

    # HK leg (mirror) — must invoke ONLY the HK-registered rank_fn, and the
    # CA-only rank_fn must not fire again either.
    _seed_board_ledger(monkeypatch, "HK", ASOF, calls)
    result_hk = bs.write_shadow(calls, market="HK", asof=ASOF)
    assert hk_invocations == ["called"]
    assert ca_invocations == ["called"], "the CA-only rank_fn must not be invoked again by the HK call"
    assert result_hk["written"] > 0  # POSITIVE CONTROL
    hk_frame = _lane_a_frame("HK")
    assert hk_frame is not None and set(hk_frame["challenger_definition"]) == {"hk_only_rank_v1"}


def test_k18_simultaneous_hk_and_ca_registrations_stay_isolated(monkeypatch):
    """K18: registering one HK challenger and one CA challenger SIMULTANEOUSLY
    (a mixed Lane-A/Lane-B pair, unlike K17's same-lane-type mirror) must
    still isolate — an HK pass executes only the HK definition (the CA
    sentinel stays silent, and the HK stores carry only the HK definition),
    and a CA pass executes only the CA definition (the HK rank_fn stays
    silent, and the CA stores carry only the CA definition)."""
    today = dt.datetime.now(dt.timezone.utc).date().isoformat()
    hk_invocations: list[str] = []
    ca_invocations: list[str] = []

    def _hk_rank_fn(inner_calls):
        hk_invocations.append("called")
        return _reversed_rank_fn(inner_calls)

    def _ca_discovery_fn(asof):
        ca_invocations.append(asof)
        return [{"session_date": today, "security_ref_raw": "CAONLY", "candidate_origin": "ca"}]

    bs.register_challenger("HK", "hk_simul_v1", rank_fn=_hk_rank_fn)
    bs.register_challenger("CA", "ca_simul_v1", discovery_fn=_ca_discovery_fn)

    calls = _population()
    _seed_board_ledger(monkeypatch, "HK", today, calls)
    result_hk = bs.write_shadow(calls, market="HK", asof=today)
    assert hk_invocations == ["called"]
    assert ca_invocations == [], "the CA-registered discovery_fn must stay silent during the HK pass"
    assert result_hk["written"] > 0  # POSITIVE CONTROL
    hk_a_frame = _lane_a_frame("HK")
    assert hk_a_frame is not None and set(hk_a_frame["challenger_definition"]) == {"hk_simul_v1"}
    hk_b_frame = _lane_b_frame("HK")
    assert hk_b_frame is None or hk_b_frame.empty, "the CA discovery challenger must not write into HK's Lane B store"

    # D4 (K18 CA leg was unfalsifiable): the CA leg used to call write_shadow
    # with `calls=[]`. Since `_write_lane_a` returns immediately when
    # `population_n == 0` WITHOUT ever invoking `rank_fn` (see
    # engine/board_shadow.py's `_write_lane_a`), a market-blind mutation of
    # `_registrations_for` (K19's shape) would have made the CA pass ALSO
    # select `hk_simul_v1`'s rank_fn — but with an empty calls list that
    # rank_fn still never fires, so `hk_invocations == ["called"]` stayed
    # true even under the mutation and this leg's isolation assertions could
    # never fail. Passing the real, non-empty `calls` fixture (and seeding
    # CA's own board_ledger row set, mirroring the HK leg above) makes the
    # CA leg genuinely killable: under the mutation, `_write_lane_a` WOULD
    # invoke `hk_simul_v1`'s rank_fn with a non-empty population.
    _seed_board_ledger(monkeypatch, "CA", today, calls)
    result_ca = bs.write_shadow(calls, market="CA", asof=today)
    assert ca_invocations == [today]
    assert hk_invocations == ["called"], "the HK rank_fn must not be invoked again by the CA pass"
    assert result_ca["written"] > 0  # POSITIVE CONTROL
    ca_b_frame = _lane_b_frame("CA")
    assert ca_b_frame is not None and set(ca_b_frame["challenger_definition"]) == {"ca_simul_v1"}
    ca_a_frame = _lane_a_frame("CA")
    assert ca_a_frame is None or ca_a_frame.empty, "the HK rank_fn must not write into CA's Lane A store"


def test_k19_mutated_market_filter_is_caught_by_the_isolation_kills(monkeypatch):
    """K19 (executed mutation kill): simulates removal/bypass of the market
    filter by monkeypatching _registrations_for to return every registered
    definition regardless of market — the exact shape of the original merged
    defect (a definition-only registry key with no market filter in
    write_shadow at all) — and asserts the K15-style isolation assertions
    then FAIL. Restores the real filter afterward and proves the suite is
    green again: this is what proves K15-K18 are non-vacuous kills, not
    decorative ones.

    MUTATION APPLIED: bs._registrations_for patched to ignore its `market`
    argument and return every registered definition, regardless of market.
    """
    today = dt.datetime.now(dt.timezone.utc).date().isoformat()
    invocations: list[str] = []

    def _sentinel_discovery(asof):
        invocations.append(asof)
        return [{"session_date": today, "security_ref_raw": "HKONLY", "candidate_origin": "hk"}]

    bs.register_challenger("HK", "hk_only_disc_v1", discovery_fn=_sentinel_discovery)

    real_registrations_for = bs._registrations_for

    def _unscoped_registrations(_market):
        # THE MUTATION: ignore `_market` entirely and hand back every
        # registered (definition, spec) pair from the WHOLE registry — the
        # exact shape of the original merged defect, where the registry was
        # keyed by definition alone and write_shadow had no market filter.
        return sorted(
            ((d, spec) for (_mkt, d), spec in bs.CHALLENGER_REGISTRY.items()),
            key=lambda pair: pair[0],
        )

    monkeypatch.setattr(bs, "_registrations_for", _unscoped_registrations)
    _lane_on(monkeypatch, "CA")
    bs.write_shadow([], market="CA", asof=today)

    # THE MUTATION FIRES: the HK-only sentinel WAS invoked by a CA call, and
    # a foreign row landed in CA's own store — exactly the cross-market
    # execution the merged defect shipped, and exactly what K15's isolation
    # assertions above would fail on.
    ca_frame = _lane_b_frame("CA")
    mutation_fired = bool(invocations) and ca_frame is not None and not ca_frame.empty
    assert mutation_fired, (
        "MUTATED _registrations_for (market-blind) must make the K15-style "
        f"isolation assertions fail; instead nothing broke — invocations="
        f"{invocations}, ca_frame present="
        f"{ca_frame is not None and not ca_frame.empty}"
    )
    assert invocations == [today], "the HK-only sentinel must have fired under the mutation"
    assert set(ca_frame["challenger_definition"]) == {"hk_only_disc_v1"}, (
        "the foreign HK-only definition must have leaked into CA's own store under the mutation"
    )

    # RESTORE the real market filter and prove the isolation holds again —
    # no new invocation, no new foreign row, and the correct distinguishable
    # registry_state.
    monkeypatch.setattr(bs, "_registrations_for", real_registrations_for)
    result_restored = bs.write_shadow([], market="CA", asof=today)
    assert invocations == [today], "restored: the HK-only sentinel must NOT fire again for a CA call"
    assert result_restored["registry_state"] == "no_challenger_for_market"
    ca_frame_after = _lane_b_frame("CA")
    assert len(ca_frame_after) == 1, "restored: no additional foreign row may appear"


def test_k20_registry_state_ladder_is_four_way_distinguishable(monkeypatch, caplog):
    """K20: the four registry_state values are mutually distinguishable —
    no_challenger_registered (globally empty registry), no_challenger_for_market
    (registrations exist, none for this market), wrote_n_rows n=0 (this
    market HAS a registration but it legitimately yields zero rows this
    session — a lawful successful zero-row pass), and error. MUTATION THIS
    KILLS: collapsing no_challenger_for_market into either of the other three
    states anywhere in write_shadow's ladder.

    D1 (MAJOR fix): the `error` state used to be asserted by injecting the
    literal string "error" into the four-way `states` set rather than
    executing the error path — a mutation collapsing the REAL `error` return
    into another state would never have been caught (proven: collapsing
    `error` into `no_challenger_registered` left this test green, see the
    build packet's executed verification). `error` is now produced by
    EXECUTION: registering a CA challenger, then monkeypatching
    `bs._read_incumbent_positions` — the SUBSTRATE-level dependency D7
    reserves `error` for — to raise, and asserting the resulting
    `registry_state` is used in the set. D8: every state's actual
    `registry_state=` log token is asserted present in caplog, fulfilling the
    contract's per-state log-line requirement."""
    today = dt.datetime.now(dt.timezone.utc).date().isoformat()

    # State 1: globally empty registry.
    _lane_on(monkeypatch, "CA")
    with caplog.at_level("INFO"):
        result_empty = bs.write_shadow([], market="CA", asof=today)
    assert result_empty["registry_state"] == "no_challenger_registered"
    assert result_empty["written"] == 0
    assert "registry_state=no_challenger_registered" in caplog.text

    # State 2: registry non-empty, but nothing registered for CA (HK-only).
    caplog.clear()
    bs.register_challenger("HK", "hk_only_v1", discovery_fn=_discovery_fn_factory([]))
    with caplog.at_level("INFO"):
        result_foreign = bs.write_shadow([], market="CA", asof=today)
    assert result_foreign["registry_state"] == "no_challenger_for_market"
    assert result_foreign["written"] == 0
    assert "registry_state=no_challenger_for_market" in caplog.text

    # State 3: CA now has its own registration, but it legitimately yields
    # zero rows this session — distinct from both state 1 and state 2.
    caplog.clear()
    bs.register_challenger("CA", "ca_empty_v1", discovery_fn=_discovery_fn_factory([]))
    with caplog.at_level("INFO"):
        result_zero = bs.write_shadow([], market="CA", asof=today)
    assert result_zero["registry_state"] == "wrote_n_rows n=0"
    assert result_zero["written"] == 0
    assert "registry_state=wrote_n_rows n=0" in caplog.text

    # State 4 (D1 executed fix): produce `error` by EXECUTION, not by
    # injecting the literal string. D7 reserves `error` for a SUBSTRATE-level
    # failure (never a single challenger raising, which the per-registration
    # try/except now absorbs as `challenger_failed` and continues) — so this
    # monkeypatches `_read_incumbent_positions`, the substrate read outside
    # every registration's own try/except, to raise.
    def _boom_incumbent_read(_market, _date):
        raise RuntimeError("substrate read exploded")

    caplog.clear()
    with monkeypatch.context() as m:
        m.setattr(bs, "_read_incumbent_positions", _boom_incumbent_read)
        with caplog.at_level("WARNING"):
            result_error = bs.write_shadow(_population(), market="CA", asof=today)
    assert result_error["registry_state"] == "error"
    assert result_error["written"] == 0
    assert "registry_state=error" in caplog.text

    # Restored: the substrate read works again and CA's registrations still
    # execute normally — the monkeypatch did not leave the module wedged.
    result_restored = bs.write_shadow([], market="CA", asof=today)
    assert result_restored["registry_state"] == "wrote_n_rows n=0"

    states = {
        result_empty["registry_state"],
        result_foreign["registry_state"],
        result_zero["registry_state"],
        result_error["registry_state"],
    }
    assert len(states) == 4, f"registry_state ladder must be 4-way distinguishable, got {states}"


def test_register_challenger_requires_market_and_fails_loud_on_unknown_market():
    """Contract correction (2026-08-21): `market` is a required first
    positional argument to register_challenger, and an unrecognised market
    raises ValueError IMMEDIATELY at registration time (fail-loud, never a
    silent no-op that would mis-lane a future registrant's writes).

    MUTATION THIS KILLS: dropping the market validation (or accepting any
    string silently instead of normalizing + checking against MARKETS)."""
    with pytest.raises(TypeError):
        bs.register_challenger("some_definition")  # market is required, no default

    with pytest.raises(ValueError):
        bs.register_challenger("US", "some_definition", rank_fn=lambda calls: {})

    # Case-insensitive normalisation still succeeds and binds the LOWERCASE
    # caller spelling to the normalised uppercase key.
    bs.register_challenger("ca", "lowercase_market_v1", rank_fn=lambda calls: {})
    assert ("CA", "lowercase_market_v1") in bs.CHALLENGER_REGISTRY


def test_register_challenger_overwrite_logs_a_named_warning(caplog):
    """D9 (nit): last-wins semantics are unchanged, but overwriting an
    existing (market, definition) registration must log a warning naming the
    key — a silent overwrite is exactly the shape a later registrant would
    want visible."""
    bs.register_challenger("CA", "dup_v1", rank_fn=lambda calls: {})
    with caplog.at_level("WARNING"):
        bs.register_challenger("CA", "dup_v1", rank_fn=lambda calls: {"OVERWRITTEN": {}})
    assert any("dup_v1" in rec.message for rec in caplog.records)
    assert bs.CHALLENGER_REGISTRY[("CA", "dup_v1")]["rank_fn"]([]) == {"OVERWRITTEN": {}}, (
        "last registration wins"
    )


def test_cross_market_same_definition_string_is_independent(monkeypatch):
    """D10: the same challenger_definition string registered independently for
    HK and CA (distinct sentinel functions) must invoke ONLY its own market's
    function, and each market's store must carry ONLY its own rows —
    registering 'shared_def_v1' for both markets is not a collision because
    the registry key is (market, definition), never definition alone."""
    today = dt.datetime.now(dt.timezone.utc).date().isoformat()
    hk_seen: list[str] = []
    ca_seen: list[str] = []

    def _hk_discovery(asof):
        hk_seen.append(asof)
        return [{"session_date": today, "security_ref_raw": "HKSHARED", "candidate_origin": "hk"}]

    def _ca_discovery(asof):
        ca_seen.append(asof)
        return [{"session_date": today, "security_ref_raw": "CASHARED", "candidate_origin": "ca"}]

    bs.register_challenger("HK", "shared_def_v1", discovery_fn=_hk_discovery)
    bs.register_challenger("CA", "shared_def_v1", discovery_fn=_ca_discovery)
    assert len(bs.CHALLENGER_REGISTRY) == 2, "same definition string for two markets is NOT a collision"

    _lane_on(monkeypatch, "HK")
    result_hk = bs.write_shadow([], market="HK", asof=today)
    assert result_hk["written"] > 0  # POSITIVE CONTROL
    assert hk_seen == [today]
    assert ca_seen == [], "the CA-registered 'shared_def_v1' must not fire during the HK pass"

    _lane_on(monkeypatch, "CA")
    result_ca = bs.write_shadow([], market="CA", asof=today)
    assert result_ca["written"] > 0  # POSITIVE CONTROL
    assert ca_seen == [today]
    assert hk_seen == [today], "the HK-registered 'shared_def_v1' must not fire again during the CA pass"

    hk_frame = _lane_b_frame("HK")
    ca_frame = _lane_b_frame("CA")
    assert hk_frame is not None and set(hk_frame["security_ref"]) == {"HKSHARED"}
    assert ca_frame is not None and set(ca_frame["security_ref"]) == {"CASHARED"}
    assert set(hk_frame["challenger_definition"]) == {"shared_def_v1"}
    assert set(ca_frame["challenger_definition"]) == {"shared_def_v1"}


def test_malformed_registry_key_is_skipped_not_fatal(monkeypatch):
    """D6: `_registrations_for` unpacked every CHALLENGER_REGISTRY key
    unconditionally, so ONE malformed (non-2-tuple) key raised inside the
    generator and — because `_registrations_for` is called from
    write_shadow's OUTER try — flipped the ENTIRE pass to
    registry_state=error for BOTH markets, even though the malformed key
    belonged to neither. A bare string key is poked directly into the
    registry (register_challenger itself only ever mints well-formed keys,
    so this simulates the registry being corrupted by some other means) and
    both markets must still run their own well-formed registrations
    normally — never `error`.

    MUTATION THIS KILLS: reverting `_registrations_for` to the unconditional
    `for (mkt, d), spec in CHALLENGER_REGISTRY.items()` unpack."""
    today = dt.datetime.now(dt.timezone.utc).date().isoformat()
    bs.CHALLENGER_REGISTRY["not_a_tuple_key"] = {"rank_fn": None, "discovery_fn": None}
    bs.register_challenger("CA", "ca_survivor_v1", discovery_fn=_discovery_fn_factory(
        [{"session_date": today, "security_ref_raw": "SURVIVOR", "candidate_origin": "ca"}]))

    _lane_on(monkeypatch, "CA")
    result_ca = bs.write_shadow([], market="CA", asof=today)
    assert result_ca["registry_state"] == "wrote_n_rows n=1", (
        f"CA's own well-formed registration must still run: {result_ca}"
    )
    assert result_ca["written"] == 1

    _lane_on(monkeypatch, "HK")
    result_hk = bs.write_shadow([], market="HK", asof=today)
    assert result_hk["registry_state"] == "no_challenger_for_market", (
        f"HK must see the malformed key skipped, never flip to error: {result_hk}"
    )


def test_reentrant_write_shadow_call_is_refused_fail_soft(monkeypatch):
    """D2(a): a challenger that calls write_shadow for the OTHER market
    mid-pass (probe-G1 shape — the concrete reentrant hole the falsified
    'structurally incapable' contract claim left open) must be refused
    fail-soft by the module-level reentrancy guard: the inner call returns
    registry_state=reentrant_refused, the other market's store gains ZERO
    rows, and the other market's own registered challenger never fires.
    POSITIVE CONTROL: the outer pass still writes, and — once the guard has
    cleared — a normal, non-reentrant call for the other market still
    executes its own registration and writes."""
    today = dt.datetime.now(dt.timezone.utc).date().isoformat()
    hk_invocations: list[str] = []
    inner_results: list[dict] = []

    def _hk_discovery_fn(asof):
        hk_invocations.append(asof)
        return [{"session_date": today, "security_ref_raw": "HKREENTRANT", "candidate_origin": "hk"}]

    bs.register_challenger("HK", "hk_reentrant_target_v1", discovery_fn=_hk_discovery_fn)

    def _reentrant_ca_discovery_fn(asof):
        # THE PROBE-G1 SHAPE: a challenger calling write_shadow for the
        # OTHER market from inside its own discovery_fn, mid-pass.
        inner = bs.write_shadow([], market="HK", asof=asof)
        inner_results.append(inner)
        return [{"session_date": today, "security_ref_raw": "CAOUTER", "candidate_origin": "ca"}]

    bs.register_challenger("CA", "ca_reentrant_v1", discovery_fn=_reentrant_ca_discovery_fn)

    _lane_on(monkeypatch, "CA")
    result = bs.write_shadow([], market="CA", asof=today)

    assert result["written"] > 0  # POSITIVE CONTROL: the outer CA pass still writes
    assert len(inner_results) == 1
    assert inner_results[0]["registry_state"] == "reentrant_refused"
    assert inner_results[0]["written"] == 0
    assert hk_invocations == [], "HK's own registered challenger must never fire from inside the refused reentrant call"
    hk_frame = _lane_b_frame("HK")
    assert hk_frame is None or hk_frame.empty, "HK's store must gain zero rows from the refused reentrant call"

    # POSITIVE CONTROL (guard clears cleanly): a normal, non-reentrant HK
    # call after the outer pass has returned still executes HK's own
    # registration and writes.
    _lane_on(monkeypatch, "HK")
    result_hk_normal = bs.write_shadow([], market="HK", asof=today)
    assert result_hk_normal["written"] > 0
    assert hk_invocations == [today]


# ---------------------------------------------------------------------------
# Standing clauses — registry_state distinguishability (F16) + lane gates
# ---------------------------------------------------------------------------
def test_empty_registry_is_distinguishable_from_a_broken_writer(monkeypatch, caplog):
    """F16: an on-lane pass with NOTHING registered must log
    registry_state=no_challenger_registered — an empty store must be
    distinguishable from a broken writer, not silently indistinguishable."""
    _lane_on(monkeypatch, "CA")
    with caplog.at_level("INFO"):
        result = bs.write_shadow(_population(), market="CA", asof=ASOF)
    assert result["registry_state"] == "no_challenger_registered"
    assert result["written"] == 0


def test_populated_pass_logs_wrote_n_rows(monkeypatch):
    """F16 mirror: a populated pass logs registry_state=wrote_n_rows n=<n>."""
    _lane_on(monkeypatch, "CA")
    calls = _population()
    _seed_board_ledger(monkeypatch, "CA", ASOF, calls)
    _register_adversarial()
    result = bs.write_shadow(calls, market="CA", asof=ASOF)
    assert result["registry_state"].startswith("wrote_n_rows n=")
    assert result["written"] > 0


def test_off_lane_ca_is_a_fail_soft_no_op(monkeypatch):
    """Lane gate (contract §4): CA writes only under COLLECT_LANE=nightly.
    Off-lane must be a silent (log-only), fail-closed no-op — never a raise."""
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    monkeypatch.delenv("CN_LANE", raising=False)
    _register_adversarial()
    result = bs.write_shadow(_population(), market="CA", asof=ASOF)
    assert result["written"] == 0
    assert result["registry_state"] == "off_lane"


def test_off_lane_hk_is_a_fail_soft_no_op(monkeypatch):
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    monkeypatch.delenv("CN_LANE", raising=False)
    _register_adversarial(market="HK")
    result = bs.write_shadow(_population(), market="HK", asof=ASOF)
    assert result["written"] == 0
    assert result["registry_state"] == "off_lane"


def test_ledger_lane_import_failure_is_fail_closed(monkeypatch):
    """Contract §4: an import failure of engine.ledger_lane is treated as
    off-lane (fail-closed), never as on-lane-by-default."""
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    monkeypatch.setitem(sys.modules, "engine.ledger_lane", None)
    try:
        _register_adversarial()
        result = bs.write_shadow(_population(), market="CA", asof=ASOF)
        assert result["written"] == 0
        assert result["registry_state"] == "off_lane"
    finally:
        monkeypatch.delitem(sys.modules, "engine.ledger_lane", raising=False)


def test_write_shadow_never_raises_on_a_hostile_registered_challenger(monkeypatch):
    """Fail-soft law: a challenger whose rank_fn raises must never break the
    build — write_shadow degrades to null-scored rows (or zero rows) and
    continues, never propagating the exception."""
    _lane_on(monkeypatch, "CA")
    _seed_board_ledger(monkeypatch, "CA", ASOF, _population())

    def _boom(_calls):
        raise RuntimeError("boom")

    bs.register_challenger("CA", "boom_v1", rank_fn=_boom)
    result = bs.write_shadow(_population(), market="CA", asof=ASOF)  # must not raise
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
    _seed_board_ledger(monkeypatch, "CA", ASOF, calls)
    _register_adversarial()
    bs.write_shadow(calls, market="CA", asof=ASOF)
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
        {"date": ASOF, "ticker": "AAA", "board_pos": 1, "board_definition": "test_board_v1"},
    ]).to_parquet(board_path, index=False)

    lane_a_path = bs._lane_a_path("CA")
    lane_a_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([
        {"date": ASOF, "market": "CA", "ticker": "AAA",
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
    bs.register_challenger("CA", "disc_v1", discovery_fn=_discovery_fn_factory(
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


# ---------------------------------------------------------------------------
# hk-discovery wave — receipt emission (contract §4's deferred
# surface-freshness wiring, activated by the hk_discovery_v1 registration).
# ---------------------------------------------------------------------------
def _discovery_fn_ok(asof_arg: str) -> list[dict]:
    return [{
        "session_date": asof_arg, "security_ref_raw": "AAA",
        "candidate_origin": "washout_reclaim",
        "availability_status": "WAIT_CONFLUENCE",
        "availability_source": "hk_signal_gate",
    }]


def _receipt_path(market: str) -> Path:
    return config.data_dir() / "prophet_shadow" / f"{market.lower()}_discovery_receipt.json"


def test_discovery_receipt_written_on_a_successful_pass(monkeypatch):
    _lane_on(monkeypatch, "HK")
    bs.register_challenger("HK", "hk_discovery_v1", discovery_fn=_discovery_fn_ok)
    result = bs.write_shadow([], market="HK", asof=ASOF)
    assert result["written"] == 1  # POSITIVE CONTROL

    path = _receipt_path("HK")
    assert path.exists()
    payload = json.loads(path.read_text())
    assert payload["market"] == "HK"
    assert payload["as_of"] == ASOF
    assert payload["registry_state"] == "wrote_n_rows n=1"
    assert payload["written"] == 1
    assert payload["definitions"] == ["hk_discovery_v1"]
    assert payload["challenger_failures"] == []
    assert payload["stamped_at"]


def test_discovery_receipt_not_written_when_the_market_has_no_registration(monkeypatch):
    """A CA pass with only an HK registration must create NO CA receipt —
    the receipt is written ONLY when _registrations_for(market) is non-empty
    for THIS market's own call."""
    _lane_on(monkeypatch, "CA")
    bs.register_challenger("HK", "hk_discovery_v1", discovery_fn=_discovery_fn_ok)
    result = bs.write_shadow([], market="CA", asof=ASOF)
    assert result["registry_state"] == "no_challenger_for_market"
    assert not _receipt_path("CA").exists()


def test_discovery_receipt_written_on_the_error_path(monkeypatch):
    """A substrate-level failure (below the per-registration boundary) still
    owes a receipt — registry_state=error, with the true accumulated
    `written` total."""
    _lane_on(monkeypatch, "HK")
    bs.register_challenger("HK", "hk_discovery_v1", discovery_fn=_discovery_fn_ok)

    def _boom(*args, **kwargs):
        raise RuntimeError("synthetic substrate failure")

    monkeypatch.setattr(bs, "_read_incumbent_positions", _boom)
    result = bs.write_shadow([], market="HK", asof=ASOF)
    assert result["registry_state"] == "error"

    path = _receipt_path("HK")
    assert path.exists()
    payload = json.loads(path.read_text())
    assert payload["registry_state"] == "error"


def test_discovery_receipt_names_a_per_registration_challenger_failure(monkeypatch):
    """D7 semantics preserved: one registration raising does not flip the
    whole pass to error, but the receipt NAMES the failure."""
    _lane_on(monkeypatch, "HK")

    def _boom_discovery(asof_arg):
        raise RuntimeError("challenger exploded")

    bs.register_challenger("HK", "hk_discovery_v1", discovery_fn=_boom_discovery)
    result = bs.write_shadow([], market="HK", asof=ASOF)
    assert result["registry_state"] == "wrote_n_rows n=0"

    payload = json.loads(_receipt_path("HK").read_text())
    assert payload["registry_state"] == "wrote_n_rows n=0"
    assert len(payload["challenger_failures"]) == 1
    assert payload["challenger_failures"][0]["definition"] == "hk_discovery_v1"
    assert "challenger exploded" in payload["challenger_failures"][0]["error"]


def test_write_surface_fence_accepts_the_hk_discovery_receipt_path(monkeypatch):
    """R8 (F8, build commission) fix: this is a PREDICATE-ONLY check of
    _offenders_for_market's market-prefix rule against the
    hk_discovery_receipt.json shape (hk_ prefix), using hand-constructed
    `changed` literals — the same pattern as
    test_write_surface_fence_trips_on_a_foreign_market_file above. It is NOT
    a real-write snapshot fence: the docstring previously claimed this
    exercised the predicate "against a REAL receipt write", which overstated
    what the assertions below actually check (they never look at the real
    filesystem at all). test_write_surface_fence_only_data_prophet_shadow_
    is_touched_hk is the actual real-snapshot fence for HK. The write_shadow
    call here is kept only as a positive control proving the receipt path is
    real and reachable, not as evidence for the offender-predicate assertions
    below."""
    _lane_on(monkeypatch, "HK")
    bs.register_challenger("HK", "hk_discovery_v1", discovery_fn=_discovery_fn_ok)
    result = bs.write_shadow([], market="HK", asof=ASOF)
    assert result["written"] == 1  # POSITIVE CONTROL

    changed = {"prophet_shadow/hk_discovery_receipt.json", "prophet_shadow/hk_discovery.parquet"}
    assert _offenders_for_market(changed, "HK") == []
    # Mirror: a CA pass must reject an HK-named receipt as a foreign file.
    assert _offenders_for_market(changed, "CA") == list(sorted(changed))


# ---------------------------------------------------------------------------
# Regression: the shared session date must never age out of the settle window
# ---------------------------------------------------------------------------
def test_shared_session_date_can_never_age_out_of_the_settle_window():
    """A literal session date silently disarms every POSITIVE CONTROL here.

    ``_settle_violation`` compares ``session_date`` against a stamp taken from
    the real wall clock, so a hard-coded date passes only until it drifts past
    ``SETTLE_WINDOW_DAYS``.  A literal ``2026-08-21`` aged out at
    ``2026-08-25T00:00Z`` and turned ``board-shadow-substrate`` red on main and
    on every branch cut from it, with no commit touching this substrate --
    exactly the failure mode a POSITIVE CONTROL exists to make loud.  Pin the
    property rather than the date, and keep the stale arm genuinely stale so
    the fence itself is still under test in both directions.
    """
    today = dt.date.today().isoformat()
    age = (dt.date.today() - dt.date.fromisoformat(ASOF)).days
    assert 0 <= age <= bs.SETTLE_WINDOW_DAYS
    assert not bs._settle_violation(ASOF, today)
    # the deliberately ancient negative arm must still be refused
    assert bs._settle_violation("2020-01-01", today)
    # and the fence must still bite one day past the window
    just_past = (dt.date.today() - dt.timedelta(days=bs.SETTLE_WINDOW_DAYS + 1)).isoformat()
    assert bs._settle_violation(just_past, today)


def test_no_bare_session_date_literal_reintroduces_the_time_bomb():
    """Guard the repair: only the ancient stale arm may be a bare date literal."""
    source = (ROOT / "tests/test_board_shadow.py").read_text()
    code = "\n".join(
        line.split("#", 1)[0] for line in source.splitlines()
        if not line.lstrip().startswith("#")
    )
    literals = set(re.findall(r'"(20\d{2}-\d{2}-\d{2})"', code))
    assert literals <= {"2020-01-01"}, (
        f"bare session-date literal(s) {sorted(literals - {'2020-01-01'})} will age out of "
        "SETTLE_WINDOW_DAYS and red this pack on a date rollover -- use ASOF"
    )
