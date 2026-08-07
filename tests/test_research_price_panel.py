"""Guards for the versioned FROZEN research price panel.

The artifact's whole value is a negative: an existing version's bytes NEVER change, and a
reader can never quietly find prices somewhere else.  Both are proved here against a
synthetic store shaped like the real confound (#4698): adjusted per-name files that shadow
a wide close cache, cache-only names with no adjusted source at all, and a requested name
that no source carries.

The byte-stability test would be vacuous if the mutation it applies could not move the
numbers, so ``test_new_version_sees_the_drift_the_frozen_one_hides`` mints a SECOND version
from the mutated store and asserts it differs.  That is the anti-vacuity pin: if it ever
starts passing by producing identical bytes, the freeze test below it is proving nothing.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
from pathlib import Path

import pytest

pd = pytest.importorskip("pandas")

REPO = Path(__file__).resolve().parents[1]
MODULE = REPO / "research/research_panels/price_panel.py"
LADDER = REPO / "research/prophet_us_audit/price_ladder.py"

#: #4698's ladder as vendored.  The panel writer must reuse it, never re-implement it.
LADDER_SOURCE_REF = "a142c293db9"
LADDER_SHA256 = "a8e376e03c12c05c9a36fc1feec59ebc15da6b6a2c62890b95099e8670176175"

DATES = pd.date_range("2026-01-02", periods=12, freq="B")


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pp = _load(MODULE, "price_panel_under_test")


def _write_series(path: Path, values) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"close": values}, index=DATES).to_parquet(path)


def _write_cache(store: Path, frame: pd.DataFrame) -> None:
    p = store / "breadth" / "_closes_cache.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(p)


@pytest.fixture
def store(tmp_path: Path) -> Path:
    """A price store with the real shape: adjusted files over a wide unadjusted cache."""
    s = tmp_path / "store"
    _write_series(s / "baskets/ohlcv/ADJ1.parquet", [100.0 + i for i in range(12)])
    _write_series(s / "baskets/ohlcv/ADJ2.parquet", [50.0 + i for i in range(12)])
    _write_series(s / "yahoo/YHO1.parquet", [10.0 + i for i in range(12)])
    _write_series(s / "yahoo/SPY.parquet", [400.0 + i for i in range(12)])
    # The cache carries every name — including the two with no adjusted source anywhere,
    # which is the 266-of-1,493 hole the manifest has to make countable.
    _write_cache(s, pd.DataFrame({
        "ADJ1": [999.0] * 12,          # shadowed: the ladder must prefer baskets/ohlcv
        "ADJ2": [999.0] * 12,
        "YHO1": [999.0] * 12,
        "CACHEONLY1": [20.0 + i for i in range(12)],
        "CACHEONLY2": [30.0 + i for i in range(12)],
    }, index=DATES))
    return s


NAMES = ["ADJ1", "ADJ2", "YHO1", "CACHEONLY1", "CACHEONLY2", "GHOST"]


def _build(root: Path, store: Path, version: str = "v1", **kw):
    return pp.build_panel(version, NAMES, asof="2026-01-30", start="2026-01-01",
                          benchmarks=("SPY",), root=root, data_dir=store, **kw)


def _rebase_cache(store: Path) -> None:
    """The defect this artifact exists to remove: the cache moves under a finished study.

    Mirrors PNC's 2026-06-22 close reading 234.71 on 2026-07-01 and 232.8536 on 2026-08-06.
    """
    p = store / "breadth" / "_closes_cache.parquet"
    c = pd.read_parquet(p)
    c["CACHEONLY1"] = c["CACHEONLY1"] * 0.99      # a distribution-shaped re-base
    c.to_parquet(p)


# --------------------------------------------------------------------------------------
# the freeze
# --------------------------------------------------------------------------------------

def test_existing_version_is_byte_stable_across_a_rebuild(tmp_path, store):
    """Re-running the writer after the stores moved must not touch the frozen bytes."""
    root = tmp_path / "data"
    m1 = _build(root, store)
    path = pp.panel_path("v1", root)
    before = path.read_bytes()
    before_manifest = pp.manifest_path("v1", root).read_bytes()

    _rebase_cache(store)
    m2 = _build(root, store)

    assert path.read_bytes() == before, "a frozen panel version was rewritten"
    assert pp.manifest_path("v1", root).read_bytes() == before_manifest
    assert m2.get("_rebuild_was_a_noop") is True
    assert m2["sha256"] == m1["sha256"]


def test_new_version_sees_the_drift_the_frozen_one_hides(tmp_path, store):
    """Anti-vacuity pin for the freeze test: the mutation above MUST move the numbers."""
    root = tmp_path / "data"
    _build(root, store, "v1")
    v1_bytes = pp.panel_path("v1", root).read_bytes()

    _rebase_cache(store)
    _build(root, store, "v2")

    assert pp.panel_path("v2", root).read_bytes() != v1_bytes, (
        "the re-base did not move the panel — the freeze test is proving nothing"
    )
    px1, _ = pp.load_panel("v1", root=root)
    px2, _ = pp.load_panel("v2", root=root)
    assert float(px1.loc[DATES[0], "CACHEONLY1"]) == pytest.approx(20.0)
    assert float(px2.loc[DATES[0], "CACHEONLY1"]) == pytest.approx(19.8)
    # and v1 is still intact after v2 was minted
    assert pp.panel_path("v1", root).read_bytes() == v1_bytes


def test_in_place_edit_of_a_frozen_panel_fails_loudly(tmp_path, store):
    root = tmp_path / "data"
    _build(root, store)
    px, _ = pp.load_panel("v1", root=root)
    px.iloc[0, 0] = -1.0
    px.to_parquet(pp.panel_path("v1", root))          # an out-of-band "repair"

    with pytest.raises(pp.PanelCorrupt) as e:
        pp.load_panel("v1", root=root)
    assert "mint a new version" in str(e.value)


def test_half_written_version_is_never_auto_repaired(tmp_path, store):
    root = tmp_path / "data"
    _build(root, store)
    pp.manifest_path("v1", root).unlink()

    with pytest.raises(pp.PanelCorrupt) as e:
        _build(root, store)
    assert "half-written" in str(e.value)


# --------------------------------------------------------------------------------------
# the reader has no path back to the live stores
# --------------------------------------------------------------------------------------

def test_unknown_version_raises_and_never_falls_back(tmp_path, store):
    root = tmp_path / "data"
    _build(root, store)

    with pytest.raises(pp.PanelVersionNotFound) as e:
        pp.load_panel("2026-12-31", root=root)
    msg = str(e.value)
    assert "'v1'" in msg or "['v1']" in msg, "the error must name what IS available"
    assert "fatal ON PURPOSE" in msg


def test_load_manifest_raises_on_its_own(tmp_path, store):
    """``load_manifest`` is exported, so it needs the refusal too.

    Found by mutation: a fallback planted in ``load_manifest`` alone left the whole suite
    green, because ``load_panel`` re-derives the parquet path from the CALLER's version and
    tripped a different check.  A caller using ``load_manifest`` directly — the cheap way to
    read a coverage receipt without the 6 MB parquet — got someone else's manifest silently.
    """
    root = tmp_path / "data"
    _build(root, store)
    with pytest.raises(pp.PanelVersionNotFound) as e:
        pp.load_manifest("2026-12-31", root=root)
    assert "fatal ON PURPOSE" in str(e.value)


def test_read_survives_the_source_stores_being_deleted(tmp_path, store):
    """Structural proof that a pinned read consults the artifact and nothing else."""
    root = tmp_path / "data"
    _build(root, store)
    expected, _ = pp.load_panel("v1", root=root)

    subprocess.run(["rm", "-rf", str(store)], check=True)
    assert not store.exists()

    got, m = pp.load_panel("v1", root=root)
    pd.testing.assert_frame_equal(got, expected)
    assert m["n_covered"] == 3


def test_load_panel_does_not_touch_the_price_ladder(tmp_path, store, monkeypatch):
    """A reader that resolved anything through the ladder could drift again."""
    root = tmp_path / "data"
    _build(root, store)

    def _boom():
        raise AssertionError("load_panel resolved through the live price ladder")

    monkeypatch.setattr(pp, "_load_ladder", _boom)
    px, m = pp.load_panel("v1", root=root)
    assert not px.empty and m["version"] == "v1"


def test_available_versions_lists_only_complete_pairs(tmp_path, store):
    root = tmp_path / "data"
    _build(root, store, "v1")
    _build(root, store, "v2")
    assert pp.available_versions(root) == ["v1", "v2"]

    pp.manifest_path("v2", root).unlink()
    assert pp.available_versions(root) == ["v1"]


def test_there_is_no_latest_version_resolver():
    """An instrument that asks for 'latest' is not pinned — the defect, restated."""
    banned = {"latest", "latest_version", "newest", "current_version"}
    assert not banned & set(dir(pp))
    assert not banned & set(pp.__all__)


# --------------------------------------------------------------------------------------
# the coverage receipt
# --------------------------------------------------------------------------------------

def test_every_requested_name_lands_in_exactly_one_coverage_bucket(tmp_path, store):
    root = tmp_path / "data"
    m = _build(root, store)
    covered = set(m["covered"])
    unadj = set(m["uncovered"]["unadjusted_basis"])
    unres = set(m["uncovered"]["unresolved"])

    assert covered == {"ADJ1", "ADJ2", "YHO1"}
    assert unadj == {"CACHEONLY1", "CACHEONLY2"}
    assert unres == {"GHOST"}
    assert covered | unadj | unres == set(NAMES)
    assert not (covered & unadj) and not (covered & unres) and not (unadj & unres)
    assert m["n_requested"] == len(NAMES)
    assert m["n_covered"] == 3
    assert m["n_uncovered"] == 3
    assert m["coverage_pct"] == 50.0


def test_price_source_is_stamped_per_name_and_adjusted_shadows_the_cache(tmp_path, store):
    root = tmp_path / "data"
    m = _build(root, store)
    assert m["price_source"] == {
        "ADJ1": "baskets_ohlcv", "ADJ2": "baskets_ohlcv", "YHO1": "yahoo",
        "CACHEONLY1": "closes_cache_UNADJUSTED",
        "CACHEONLY2": "closes_cache_UNADJUSTED", "GHOST": None,
    }
    px, _ = pp.load_panel("v1", root=root)
    assert float(px.loc[DATES[0], "ADJ1"]) == pytest.approx(100.0), "cache shadowed adjusted"
    assert "GHOST" not in px.columns


def test_benchmarks_ride_the_same_basis_but_not_the_name_universe(tmp_path, store):
    root = tmp_path / "data"
    m = _build(root, store)
    px, _ = pp.load_panel("v1", root=root)
    assert "SPY" in px.columns, "a benchmark on a different basis is the original defect"
    assert m["benchmarks"] == ["SPY"]
    assert m["benchmark_price_source"]["SPY"] == "yahoo"
    assert "SPY" not in m["covered"] and m["n_requested"] == len(NAMES)


def test_coverage_line_states_the_hole(tmp_path, store):
    root = tmp_path / "data"
    m = _build(root, store)
    line = pp.coverage_line(m, n=42)
    assert "n=42" in line
    assert "3/6 adjusted-basis names (50.0%)" in line
    assert "2 on the unadjusted cache" in line
    assert "1 unresolved" in line
    assert "v1" in line


def test_manifest_records_the_ladder_it_was_built_with(tmp_path, store):
    root = tmp_path / "data"
    m = _build(root, store)
    assert m["price_ladder_source"] == "research/prophet_us_audit/price_ladder.py"
    assert len(m["price_ladder_sha256"]) == 64
    assert m["sha256"] == pp._sha256(pp.panel_path("v1", root))
    assert m["rows"] == 12 and m["columns"] == 6      # 5 resolved names + SPY


# --------------------------------------------------------------------------------------
# determinism + refusals
# --------------------------------------------------------------------------------------

def test_column_order_does_not_depend_on_the_caller(tmp_path, store):
    root = tmp_path / "data"
    pp.build_panel("a", NAMES, asof="2026-01-30", start="2026-01-01",
                   benchmarks=("SPY",), root=root, data_dir=store)
    pp.build_panel("b", list(reversed(NAMES)), asof="2026-01-30", start="2026-01-01",
                   benchmarks=("SPY",), root=root, data_dir=store)
    a, _ = pp.load_panel("a", root=root)
    b, _ = pp.load_panel("b", root=root)
    assert list(a.columns) == list(b.columns) == sorted(a.columns)
    pd.testing.assert_frame_equal(a, b)


def test_allow_unadjusted_false_drops_the_cache_only_names(tmp_path, store):
    root = tmp_path / "data"
    m = _build(root, store, allow_unadjusted=False)
    assert m["uncovered"]["unadjusted_basis"] == []
    assert set(m["uncovered"]["unresolved"]) == {"CACHEONLY1", "CACHEONLY2", "GHOST"}
    px, _ = pp.load_panel("v1", root=root)
    assert "CACHEONLY1" not in px.columns


def test_refuses_to_freeze_an_empty_evidence_base(tmp_path):
    with pytest.raises(ValueError, match="refusing to freeze an empty"):
        pp.build_panel("v1", ["NOPE"], asof="2026-01-30", root=tmp_path / "data",
                       data_dir=tmp_path / "empty")


def test_no_tmp_files_survive_a_build(tmp_path, store):
    root = tmp_path / "data"
    _build(root, store)
    assert not list((root / pp.PANEL_SUBDIR).glob("*.tmp"))


def test_a_failed_write_leaves_no_half_version_behind(tmp_path, store, monkeypatch):
    """A stranded temp is survivable; a stranded .parquet is not — write-once would then
    refuse to ever replace it, and the version could never be built."""
    root = tmp_path / "data"

    def _boom(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(pd.DataFrame, "to_parquet", _boom)
    with pytest.raises(OSError):
        _build(root, store)

    store_dir = root / pp.PANEL_SUBDIR
    assert not list(store_dir.glob("*.tmp"))
    assert not pp.panel_path("v1", root).exists()

    monkeypatch.undo()
    m = _build(root, store)          # and the version is still buildable afterwards
    assert m["version"] == "v1" and not m.get("_rebuild_was_a_noop")


@pytest.mark.parametrize("bad", ["../escape", "a/b", "", ".hidden", "/abs"])
def test_a_version_is_a_name_not_a_path(bad, tmp_path):
    """Versions arrive from env vars and CLI args; a separator must not escape the store."""
    with pytest.raises(ValueError, match="not a path"):
        pp.panel_path(bad, tmp_path)
    with pytest.raises(ValueError, match="not a path"):
        pp.manifest_path(bad, tmp_path)


# --------------------------------------------------------------------------------------
# the vendored ladder is #4698's, byte for byte
# --------------------------------------------------------------------------------------

def test_vendored_ladder_matches_the_4698_source():
    """SKIPS rather than passes when the source ref is absent — an unverifiable pin is not
    a green one (the #4698 ladder is not on main until that PR lands)."""
    assert LADDER.exists()
    assert pp._sha256(LADDER) == LADDER_SHA256

    out = subprocess.run(
        ["git", "show", f"{LADDER_SOURCE_REF}:research/prophet_us_audit/price_ladder.py"],
        cwd=REPO, capture_output=True,
    )
    if out.returncode != 0:
        pytest.skip(f"#4698 ref {LADDER_SOURCE_REF} not fetchable in this checkout")
    import hashlib
    assert hashlib.sha256(out.stdout).hexdigest() == LADDER_SHA256, (
        "the vendored ladder drifted from #4698's — re-vendor, do not hand-patch"
    )


def test_manifest_is_small_enough_to_read(tmp_path, store):
    """The manifest is the auditable half; it must not need the 6 MB parquet to be useful."""
    root = tmp_path / "data"
    _build(root, store)
    raw = pp.manifest_path("v1", root).read_text()
    m = json.loads(raw)
    assert set(m) >= {"version", "built_utc", "sha256", "rows", "columns",
                      "price_source", "covered", "uncovered", "contract"}
    assert os.path.getsize(pp.manifest_path("v1", root)) < 100_000
