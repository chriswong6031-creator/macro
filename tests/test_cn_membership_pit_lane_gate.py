"""CN membership-PIT LANE GATE, on the path production actually takes.

THE GATE WAS DOUBLY DEAD (both halves, on main, until 2026-08-09)
----------------------------------------------------------------
``engine.basket_membership_pit`` has carried an asia-lane gate since it shipped, and
neither half of it could ever refuse anything:

    engine/basket_membership_pit.py   if lane is not None and lane != "asia": ...
    scripts/build_baskets_china_ths.py  _pit.append_all(lane=os.environ.get("CN_LANE", "asia"))

The resolver defaulted to ``"asia"``, so every context that left ``CN_LANE`` unset
arrived at the gate CLAIMING to be the asia lane; and behind it the gate was
None-permissive anyway, so a caller that named no lane at all also walked through.
The builder's own docstring said "a hand-run from a render lane writes nothing" — it
was false, in both directions at once.  The existing unit tests all hand-fed ``lane=``,
so they stayed green while the guard did nothing: the monkeypatched-orphan shape.

WHY IT MATTERS
--------------
The store is append-only, keep-FIRST per ``(snapshot_date, basket_id, ticker)`` and
content-deduped (CN Prophet masterplan §5 W-C), so the FIRST lane to stamp a date owns
that snapshot FOREVER — a later lane's view of the same day is discarded in silence,
and every PIT answer from that date on is whatever the first writer happened to see.
That is the same immutability rationale as the entry latch (ef303a42061).  Today the
only workflow invoker is asia-close.yml band A (``brun ths_snapshot ... --snapshot``,
step-level ``CN_LANE: asia``), so the live exposure is hand-runs and any future lane
that adopts ``--snapshot`` — which is exactly the population a fail-open default is
invisible to.

WHAT THIS FILE PINS
-------------------
Only the ENV var is set on the production-path tests; nothing hand-feeds ``lane=``.
tests/test_basket_membership_pit.py holds the unit pins (and now names ``lane="asia"``
on every writer call, because relying on the permissive default is what hid this).
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from engine import basket_membership_pit as pit
from lib import config
from scripts import build_baskets_china_ths as bts

THS = pit.SUITE_THS
CURATED = pit.SUITE_CURATED


# ---------------------------------------------------------------------------
# fixtures (the house idiom, mirroring tests/test_basket_membership_pit.py)
# ---------------------------------------------------------------------------

def _m(ticker: str, added: str | None = "2021-06-15", removed: str | None = None) -> dict:
    return {"ticker": ticker, "added": added, "removed": removed,
            "name_zh": f"zh-{ticker}", "rationale": "test"}


def _doc(baskets: dict) -> dict:
    """A membership document in the shape both suites actually ship."""
    return {
        "version": 1, "seed_date": "2021-06-15", "curated": False,
        "baskets": {
            bid: {"name": bid.upper(), "name_zh": bid, "category": "theme",
                  "members": members}
            for bid, members in baskets.items()
        },
    }


def _write_membership(root: Path, suite: str, doc: dict) -> None:
    p = root / suite / "membership.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")


#: The seeded THS membership every production-path test below runs on.
MEMBERS = ("300474.SZ", "688981.SS")


@pytest.fixture
def data_root(tmp_path, monkeypatch):
    """Point config.data_dir() at a scratch tree (the house fixture idiom).

    ``engine.basket_membership_pit`` and ``scripts.build_baskets_china_ths`` both do
    ``from lib import config`` and call ``config.data_dir()``, so patching the attribute
    on the module object redirects BOTH — the writer and the entry point that drives it.
    """
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    return tmp_path


@pytest.fixture
def seeded(data_root):
    """A THS membership.json on disk and an empty store — the nightly's starting state."""
    _write_membership(data_root, THS, _doc({"ths_ai": [_m(t) for t in MEMBERS]}))
    assert not pit.history_path(THS).exists()
    return data_root


def _no_parquet_anywhere() -> None:
    """No suite may have a history parquet. The refusal is a NON-write, so read the disk."""
    written = [s for s in pit.SUITES if pit.history_path(s).exists()]
    assert written == [], f"the PIT store was advanced outside the asia lane: {written}"


def _stored_tickers(suite: str = THS) -> set[str]:
    return set(pit.read_history(suite)["ticker"].astype(str))


# ===========================================================================
# 1-2. the gate itself, fail-closed
# ===========================================================================

def test_an_unnamed_lane_refuses_to_append(seeded):
    """FAIL-CLOSED. No lane named → no write. This is the assertion the old gate inverted.

    Both spellings of "unnamed" are pinned: an explicit ``lane=None`` and a bare call
    that omits the kwarg entirely. The bare call is the one that mattered — under the
    permissive form it was indistinguishable from the asia nightly.
    """
    explicit = pit.append_snapshot(THS, asof="2026-07-08", lane=None)
    assert explicit["written"] is False
    assert explicit["reason"] == "lane=None"

    bare = pit.append_snapshot(THS, asof="2026-07-08")
    assert bare["written"] is False
    assert bare["reason"] == "lane=None"

    assert pit.backfill_from_json_snapshots(THS)["reason"] == "lane=None"
    every = pit.append_all(asof="2026-07-08")
    assert every[THS]["snapshot"]["reason"] == "lane=None"
    assert every[THS]["backfill"]["reason"] == "lane=None"
    _no_parquet_anywhere()

    # WITNESS: the SAME fixture writes once the lane is named, so the refusals above are
    # the gate and not an unwritable scratch tree.
    witness = pit.append_snapshot(THS, asof="2026-07-08", lane="asia")
    assert witness["written"] and witness["rows_added"] == len(MEMBERS)
    assert _stored_tickers() == set(MEMBERS)


@pytest.mark.parametrize("lane", ["render", "us"])
def test_a_non_asia_lane_still_refuses(seeded, lane):
    """Pre-existing behaviour, now pinned beside the None case it used to be alone with.

    Making the gate fail-closed must not quietly change what a NAMED foreign lane gets:
    the same refusal, the same ``reason`` shape the callers already read.
    """
    res = pit.append_snapshot(THS, asof="2026-07-08", lane=lane)
    assert res["written"] is False
    assert res["reason"] == f"lane={lane}"
    assert pit.backfill_from_json_snapshots(THS, lane=lane)["reason"] == f"lane={lane}"
    _no_parquet_anywhere()


# ===========================================================================
# 3-5. the production entry points, driven by the ENVIRONMENT alone
# ===========================================================================
# Nothing below hand-feeds `lane=`. `CN_LANE` is the one variable the workflows set —
# asia-close.yml band A, step "CN/HK builder band A" — so setting it is the whole
# difference between the asia nightly and every other context.


@pytest.mark.parametrize("cn_lane", [
    pytest.param(None, id="CN_LANE-unset"),
    pytest.param("", id="CN_LANE-empty"),
    pytest.param("us", id="CN_LANE-us"),
])
def test_the_render_lanes_never_append_membership_pit(seeded, monkeypatch, cn_lane):
    """A hand-run or a future non-asia adopter of --snapshot must advance nothing.

    This is the case the old resolver could not see: with ``os.environ.get("CN_LANE",
    "asia")`` an unset variable WAS the asia lane, so whoever ran first owned the
    snapshot date. The empty-string case is the same defect one step in — a workflow
    that sets ``CN_LANE:`` with no value must strip to None, not to a truthy lane name.
    """
    if cn_lane is None:
        monkeypatch.delenv("CN_LANE", raising=False)
    else:
        monkeypatch.setenv("CN_LANE", cn_lane)

    assert bts._membership_pit_lane() == (cn_lane or None)  # noqa: SLF001 — the resolver
    bts._snapshot_membership_pit()  # noqa: SLF001 — the production call, exactly as shipped
    _no_parquet_anywhere()

    # WITNESS: the identical fixture and the identical call DO write in the asia lane,
    # so the non-write above is the gate rather than a fixture that could never write.
    monkeypatch.setenv("CN_LANE", "asia")
    bts._snapshot_membership_pit()  # noqa: SLF001
    assert _stored_tickers() == set(MEMBERS)


def test_the_asia_nightly_is_the_lane_that_appends(seeded, monkeypatch):
    """asia-close.yml band A: CN_LANE=asia — the ONE lane that may advance the store.

    The byte-path identity check. The fix must leave the lane that actually runs this
    tonight doing precisely what it did before: stamp both suites from membership.json.
    """
    monkeypatch.setenv("CN_LANE", "asia")
    bts._snapshot_membership_pit()  # noqa: SLF001 — the production call

    assert pit.history_path(THS).exists()
    assert _stored_tickers() == set(MEMBERS)
    cov = pit.coverage(THS)
    assert cov["snapshots"] == 1 and cov["rows"] == len(MEMBERS)
    # Resolve through the reader on the store's own stamp — utcnow-derived, so the date
    # is read back rather than re-spelled here (this suite runs under TZ=UTC in CI).
    got = pit.members_asof("ths_ai", cov["last"], suite=THS)
    assert got["pit"] is True and got["members"] == sorted(MEMBERS)
    # The curated suite has no membership.json in this fixture: a skip, not a crash,
    # and not a lane refusal.
    assert not pit.history_path(CURATED).exists()


def test_snapshot_entrypoint_gates_only_the_pit_write(seeded, monkeypatch):
    """--snapshot ships TWO stores. Only the parquet is lane-gated; the JSON is not.

    ``snapshot_membership`` writes the dated JSON side-car unconditionally and always
    has — that is deliberate and out of scope here. Pinning it means a later change to
    the parquet gate cannot silently take the side-car with it, in either direction.

    Running the render leg FIRST is also the ordering pin: a side-car dropped by a
    non-asia lane must not stop the asia nightly from advancing the parquet afterwards.
    """
    snaps = seeded / THS / "snapshots"

    monkeypatch.delenv("CN_LANE", raising=False)
    assert bts.snapshot_membership() == 0
    side_cars = sorted(p.name for p in snaps.glob("????-??-??.json"))
    assert len(side_cars) == 1, f"the dated JSON side-car is ungated: {side_cars}"
    _no_parquet_anywhere()

    monkeypatch.setenv("CN_LANE", "asia")
    assert bts.snapshot_membership() == 0
    assert sorted(p.name for p in snaps.glob("????-??-??.json")) == side_cars
    assert pit.history_path(THS).exists()
    assert _stored_tickers() == set(MEMBERS)


# ===========================================================================
# 6. the call sites — the test that would have caught the original defect
# ===========================================================================

_PIT_MODULE = "engine.basket_membership_pit"
_PIT_WRITERS: tuple[str, ...] = ("append_all", "append_snapshot",
                                 "backfill_from_json_snapshots")


def _dotted(node: ast.AST) -> str | None:
    """``a.b.c`` for a Name/Attribute chain, else None."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    parts.append(node.id)
    return ".".join(reversed(parts))


def _scan_pit_writes(src: str, *, is_the_module: bool = False) -> tuple[list[int], list[int]]:
    """(lines that name ``lane=``, lines that do not) for calls resolving to a PIT writer.

    ALIAS RESOLUTION IS THE WHOLE POINT. ``append_snapshot`` is ALSO the name of
    ``collectors._drip.append_snapshot`` — a different function with no lane concept,
    called throughout collectors/ and inside engine/china_national_team.py. A scan that
    matched the bare attribute name would flag those, be wrong on its first run, and be
    deleted. So a call counts only when its receiver is a name bound to
    ``engine.basket_membership_pit``, or when the function name itself was imported from
    it. ``is_the_module`` covers the store's own internal threading (append_all ->
    backfill/append_snapshot), where the writers are bare local names.
    """
    tree = ast.parse(src)
    module_aliases: set[str] = {_PIT_MODULE}
    bare: set[str] = set(_PIT_WRITERS) if is_the_module else set()
    for node in ast.walk(tree):           # imports may be function-local — walk, don't peek
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name == _PIT_MODULE:
                    module_aliases.add(a.asname or a.name)
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod == _PIT_MODULE:                       # from engine.basket_membership_pit import X
                bare |= {a.asname or a.name for a in node.names if a.name in _PIT_WRITERS}
            elif mod == "engine" or (node.level and not node.module):
                module_aliases |= {a.asname or a.name for a in node.names
                                   if a.name == "basket_membership_pit"}
    named: list[int] = []
    unnamed: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if isinstance(fn, ast.Attribute) and fn.attr in _PIT_WRITERS:
            hit = _dotted(fn.value) in module_aliases
        elif isinstance(fn, ast.Name):
            hit = fn.id in bare
        else:
            hit = False
        if hit:
            (named if any(kw.arg == "lane" for kw in node.keywords)
             else unnamed).append(node.lineno)
    return named, unnamed


def test_every_production_membership_pit_write_names_its_lane():
    """The defect was a CALL SITE as much as a policy — so pin the call sites.

    The gate is fail-closed now, which flips the failure mode: a forgotten ``lane=``
    stops advancing the store SILENTLY instead of advancing it wrongly. Equally wrong,
    and invisible without this scan.
    """
    root = Path(__file__).resolve().parents[1]
    module_rel = "engine/basket_membership_pit.py"
    offenders: list[str] = []
    seen: list[str] = []
    for path in sorted([*(root / "engine").rglob("*.py"), *(root / "scripts").rglob("*.py")]):
        src = path.read_text(encoding="utf-8")
        if not any(w in src for w in _PIT_WRITERS):
            continue
        rel = path.relative_to(root).as_posix()
        named, unnamed = _scan_pit_writes(src, is_the_module=rel == module_rel)
        seen += [f"{rel}:{n}" for n in named]
        offenders += [f"{rel}:{n}" for n in unnamed]

    assert offenders == [], (
        "a membership-PIT writer is called without lane=; the gate is fail-closed, so "
        f"these writes no-op in silence and the store stops accruing: {offenders}")

    # WITNESS 1: the scan can SEE the real calls — the production entry point and the
    # store's own internal threading both resolved, and both were judged compliant.
    files = {s.rsplit(":", 1)[0] for s in seen}
    assert "scripts/build_baskets_china_ths.py" in files, seen
    assert module_rel in files, seen

    # WITNESS 2: it can FAIL. An aliased write with no lane is caught...
    assert _scan_pit_writes(
        "from engine import basket_membership_pit as _pit\n_pit.append_all()\n"
    ) == ([], [2])
    assert _scan_pit_writes(
        "from engine.basket_membership_pit import append_snapshot\nappend_snapshot('s')\n"
    ) == ([], [2])

    # WITNESS 3: ...and the homonym is NOT. collectors._drip.append_snapshot is a
    # different function, takes no lane, and is called inside engine/ today. A scan that
    # flagged it would be turned off, so prove on the real file that it does not.
    decoy = (root / "engine" / "china_national_team.py").read_text(encoding="utf-8")
    assert "_drip.append_snapshot(" in decoy, (
        "the homonym witness has moved — re-point it at a live collectors._drip caller "
        "under engine/ or scripts/, or the alias resolution is no longer being tested")
    assert _scan_pit_writes(decoy) == ([], []), (
        "collectors._drip.append_snapshot was resolved as a PIT write — the scan is "
        "matching bare names instead of the module the name is bound to")
