"""The options family must keep EXPRESS-LANE coverage — the #3515 freeze class.

OIP E8 (2026-07-29).  ``scripts/build_options_command.py`` builds options.html, the
canonical options surface, by re-serialising six stores other builders write.  It was
wired in ``daily.yml`` ONLY.  Consequences:

1. **Baked-page freeze.**  Every express render (``render.yml`` push/dispatch,
   ``engine-render.yml`` on an ``engine/**`` push) refreshed stores the workspace reads —
   ``site/gex/*.json`` and ``site/vol/regime.json`` in ``cl_gex``,
   ``site/flowleaders/leaders.json`` in ``flowleaders()`` — and then committed a
   ``site/options.html`` still describing the previous nightly.  Identical class to
   ``build_flow_leaders`` (#3515) and ``build_research_vault`` (#3487): a page whose
   builder lives in one lane while its inputs refresh in three.
2. **Un-bakeable edits.**  An edit to the builder or ``templates/options.html.j2``
   resolved through ``region_of``'s catch-all to ``all`` — and ``scope=all`` did not run
   the builder either, so the fix simply never shipped until the next nightly.
3. **Screener page, same hole.**  ``build_options_screener`` (which writes both
   ``options_screener.html`` and the workspace's Scanner payload
   ``site/screenerdata/rows.json``) was absent from BOTH express lanes.
4. **Narrow-vs-cluster drift.**  The narrow ``gex)`` case refreshed the skew and ivspread
   snapshots but never re-ran ``build_options_entry_state``, which consumes them — so
   ``data/options_entry/state.parquet`` stayed a generation behind its own inputs.

The load-bearing assertion is :func:`test_every_workspace_store_producer_is_accounted_for`:
it reads ``load_stores`` out of the builder and forces a wiring decision for every store
the workspace reads.  Add a seventh store and this test reds until you either wire its
producer into the express lanes or record it as an accepted committed-vintage input.

``region_of`` is EXECUTED, not grepped — the picker is inline shell, i.e. untested code
unless a test runs it (the tests/test_render_canada_scope.py precedent).

Run: .venv/bin/python -m pytest tests/test_render_options_workspace_scope.py -q
"""

from __future__ import annotations

import importlib
import re
import subprocess
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RENDER = (ROOT / ".github" / "workflows" / "render.yml").read_text()
ENGINE_RENDER = (ROOT / ".github" / "workflows" / "engine-render.yml").read_text()
DAILY = (ROOT / ".github" / "workflows" / "daily.yml").read_text()
CMD_SRC = (ROOT / "scripts" / "build_options_command.py").read_text()

EXPRESS_LANES = {"render.yml": RENDER, "engine-render.yml": ENGINE_RENDER}


# --------------------------------------------------------------- region_of picker


def _region_of_fn() -> str:
    """The literal `region_of() { ... }` shell function lifted out of render.yml."""
    lines = RENDER.splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.strip() == "region_of() {")
    end = next(i for i in range(start + 1, len(lines)) if lines[i].strip() == "}")
    return "\n".join(ln.strip() for ln in lines[start:end + 1])


def _region_of(path: str) -> str:
    out = subprocess.run(
        ["bash", "-c", f'{_region_of_fn()}\nregion_of "$1"', "_", path],
        capture_output=True, text=True, check=True,
    )
    return out.stdout.strip()


@pytest.mark.parametrize("path", [
    "templates/options.html.j2",
    "scripts/build_options_command.py",
    "templates/options_screener.html.j2",
    "scripts/build_options_screener.py",
])
def test_workspace_files_select_the_gex_scope(path):
    """Leaf pages the `gex` scope now rebuilds — narrow, don't fall through to `all`."""
    assert _region_of(path) == "gex"


@pytest.mark.parametrize("path", [
    # These stores feed builders the `gex` scope does NOT run (build_flow_leaders,
    # build_site's stock_score), so narrowing them would trade one staleness class for
    # another.  They must keep over-rendering via the catch-all.
    "scripts/build_options_ivspread.py",
    "scripts/build_options_entry_state.py",
    "scripts/build_flow_desk.py",
    "scripts/build_market_structure.py",
    "scripts/build_flow_leaders.py",
])
def test_multi_consumer_options_builders_still_over_render(path):
    assert _region_of(path) == "all"


def test_gex_is_in_the_dirty_region_union_loop():
    """region_of returning `gex` is inert unless the union loop iterates it."""
    assert "for R in macro intl china hk canada markets gex baskets sits; do" in RENDER


# ------------------------------------------------------- optionscmd() placement


@pytest.mark.parametrize("lane", sorted(EXPRESS_LANES))
def test_express_lane_defines_optionscmd(lane):
    text = EXPRESS_LANES[lane]
    assert "optionscmd() {" in text, f"{lane}: no optionscmd() function"
    fn = next(ln for ln in text.splitlines() if ln.strip().startswith("optionscmd() {"))
    assert "scripts.build_options_command" in fn


@pytest.mark.parametrize("lane", sorted(EXPRESS_LANES))
def test_full_render_runs_optionscmd_after_flowleaders(lane):
    """ORDERING LAW (daily.yml:1314-1324): the workspace re-serialises outputs of builders
    that straddle the parallel band and the serial post-band steps.  build_flow_leaders is
    a post-band step, so options.html must be built AFTER it — otherwise every render
    bakes a generation-stale Leaders mode."""
    text = EXPRESS_LANES[lane]
    all_branch = text.split("            all)\n", 1)[1].split(";;", 1)[0]
    assert "optionscmd" in all_branch, f"{lane}: scope=all never builds options.html"
    assert "flowleaders" in all_branch
    assert all_branch.index("flowleaders") < all_branch.index("optionscmd"), (
        f"{lane}: optionscmd must follow flowleaders — it re-serialises leaders.json"
    )


@pytest.mark.parametrize("lane", sorted(EXPRESS_LANES))
def test_optionscmd_is_never_a_parallel_band_member(lane):
    """Same law, other direction: a cl_* placement would run it before flowleaders()
    and concurrently with its own cl_gex producers."""
    text = EXPRESS_LANES[lane]
    band = text.split("          band() {", 1)[1].split("\n          }", 1)[0]
    assert "build_options_command" not in band, (
        f"{lane}: build_options_command must be a SERIAL POST-BAND step, not a band member"
    )


def _narrow_gex(text: str) -> str:
    return text.split("            gex)\n", 1)[1].split(";;", 1)[0]


@pytest.mark.parametrize("lane", sorted(EXPRESS_LANES))
def test_narrow_gex_case_builds_the_pages_in_order(lane):
    """The narrow single-scope case must not drift from cl_gex again."""
    case = _narrow_gex(EXPRESS_LANES[lane])
    for mod in ("scripts.build_options_skew", "scripts.build_options_ivspread",
                "scripts.build_options_screener"):
        assert mod in case, f"{lane}: narrow gex case missing {mod}"
    assert "optionscmd" in case, f"{lane}: narrow gex case never rebuilds options.html"
    # snapshots first, then the page builder, then the re-serialiser
    assert case.index("scripts.build_options_ivspread") < case.index("scripts.build_options_screener")
    assert case.index("scripts.build_options_screener") < case.index("optionscmd")


@pytest.mark.parametrize("lane", sorted(EXPRESS_LANES))
def test_narrow_gex_refreshes_leaders_before_baking_the_workspace(lane):
    """M10. options.html re-serialises site/flowleaders/leaders.json, and this scope is
    reachable by a template edit via region_of — so without flowleaders() the narrow case
    bakes a silently-stale Leaders block. Express-safe: zero data/ writes, exit 0, ~27s."""
    case = _narrow_gex(EXPRESS_LANES[lane])
    assert "flowleaders" in case, f"{lane}: narrow gex bakes options.html with stale leaders"
    assert case.index("flowleaders") < case.index("optionscmd"), (
        f"{lane}: flowleaders must run BEFORE optionscmd"
    )


@pytest.mark.parametrize("lane", sorted(EXPRESS_LANES))
def test_narrow_gex_does_not_run_a_data_only_builder(lane):
    """M11. build_options_entry_state's ONLY output is data/options_entry/state.parquet and
    both express lanes commit site/ ONLY, so running it in the narrow case was ~6.3s of
    compute whose result is discarded. It stays in cl_gex and in daily.yml — the lane that
    actually persists it, and therefore the lane whose cadence drift matters."""
    case = _narrow_gex(EXPRESS_LANES[lane])
    assert "scripts.build_options_entry_state" not in case, (
        f"{lane}: narrow gex runs build_options_entry_state, whose data/ write this lane "
        "discards — dead compute on the render budget"
    )
    # ...but it must still be a cl_gex member (that placement mirrors daily.yml)
    assert "scripts.build_options_entry_state" in _cl_gex(EXPRESS_LANES[lane])


# --------------------------------------------------------------- cl_gex membership


def _cl_gex(text: str) -> str:
    return text.split("            cl_gex() {", 1)[1].split("\n            }", 1)[0]


@pytest.mark.parametrize("lane", sorted(EXPRESS_LANES))
def test_cl_gex_runs_the_screener_after_the_snapshot_builders(lane):
    """build_options_screener reads data/options_skew + data/options_ivspread snapshots;
    it must read THIS run's, and it must stay inside cl_gex (sequential) because
    build_options_skew rewrites snapshots.parquet non-atomically."""
    cl = _cl_gex(EXPRESS_LANES[lane])
    assert "scripts.build_options_screener" in cl, f"{lane}: screener not in cl_gex"
    assert cl.index("scripts.build_options_skew") < cl.index("scripts.build_options_screener")
    assert cl.index("scripts.build_options_ivspread") < cl.index("scripts.build_options_screener")


@pytest.mark.parametrize("lane", sorted(EXPRESS_LANES))
def test_screener_has_order_membership_not_just_band_membership(lane):
    """`ORDER` is what prints a builder's log and raises its rc!=0 ::error — band
    membership without ORDER membership is a builder that runs unwatched (#3487)."""
    text = EXPRESS_LANES[lane]
    order = re.search(r'local ORDER="([^"]+)"', text).group(1).split()
    assert "options_screener" in order, f"{lane}: options_screener missing from ORDER"


# --------------------------------------------- the load-bearing coverage assertion


# Every store load_stores() reads → the builder that writes it → how the express lanes
# cover it.  "committed" means the express lanes deliberately serve the last nightly's
# vintage (documented reason required); "wired" means an express lane rebuilds it.
WORKSPACE_STORES = {
    "site/flow_desk.json":                 ("scripts.build_flow_desk",        "committed"),
    "site/screenerdata/rows.json":         ("scripts.build_options_screener",  "wired"),
    "site/flowleaders/leaders.json":       ("scripts.build_flow_leaders",      "wired"),
    "data/market_structure/latest.json":   ("scripts.build_market_structure",  "committed"),
    "site/vol/regime.json":                ("scripts.build_vol_regime",        "wired"),
    "site/gex/index.json":                 ("scripts.build_gex_board",         "wired"),
    # the INDEX_KEYS loop: site/gex/{SPX,SPY,QQQ,IWM}.json (path built with an f-string,
    # so the extractor sees the "site / gex" prefix only)
    "site/gex":                            ("scripts.build_gex_board",         "wired"),
}
# Named, accepted committed-vintage inputs.  build_flow_desk is NOT express-admitted
# because scripts/build_flow_desk.py:757 calls _rebuild_broad_proxy() unconditionally,
# upserting data/flows/broad_flow_proxy.parquet with no COLLECT_LANE gate in code (the
# express commit discards it, but the write is not lane-gated the way build_leader_radar's
# are).  build_market_structure appends a COLLECT_LANE=nightly-gated forward ledger and
# has never been an express-lane member.  Both keep the last nightly's vintage, which is
# coherent: the workspace then shows one nightly's states for those sections.
ACCEPTED_COMMITTED = {"scripts.build_flow_desk", "scripts.build_market_structure"}


def _store_paths_read_by_load_stores() -> set[str]:
    """Reconstruct the store paths from the literal `load_stores` body."""
    body = CMD_SRC.split("def load_stores(", 1)[1].split("\n\n", 1)[0]
    found = set()
    for seg, prefix in (("site /", "site"), ("data /", "data")):
        for m in re.finditer(re.escape(seg) + r'\s*((?:"[^"]+"\s*/\s*)*"[^"]+")', body):
            parts = re.findall(r'"([^"]+)"', m.group(1))
            found.add("/".join([prefix, *parts]))
    return found


def _import_builder():
    """Import the builder for the RUNTIME probe — in the THIN pack env too.

    CI packs install a minimal dep set, not requirements.txt.  When the owning job
    (`workflow-yaml` in .github/ci/legacy-jobs.yml) installed only `pytest pyyaml`, a bare
    `import scripts.build_options_command` died with ModuleNotFoundError before the probe
    ran — that module does `from jinja2 import Environment, FileSystemLoader` at module
    scope — so this ONE test was green in every dev venv and red only in ci-pack-1 (#3977).

    That job's install line now carries jinja2 for this suite's four siblings, whose
    assertions genuinely need it.  This helper stays anyway, and deliberately: it is what
    lets the express-lane suite run on nothing but pytest + bash, which is the dependency
    tier its OTHER 30 tests actually sit at (they read workflow YAML and shell out to
    render.yml's `region_of`).  Do not replace it with `importorskip` if the deps move
    again — a suite that skips in the only job naming it executes NOWHERE while reading
    green, the class scripts/check_skip_only_suites.py runs in this very job to catch, and
    this probe is the only guard that sees an f-string-built store path.

    Stubbing is safe here because load_stores() and _load() are pure stdlib (json +
    pathlib); jinja2 is touched only by render()'s `Environment(...)`
    (build_options_command.py:863), which this test never calls.  Two properties keep the
    stub honest:
      * installed ONLY when jinja2 is genuinely absent, so any env that has it — CI
        included, today — probes against the real module;
      * its attributes RAISE when called, so nothing can quietly render an empty page
        through it, and it is removed from sys.modules immediately after the import so a
        later `import jinja2` in the same session still fails loudly.
    """
    if "jinja2" not in sys.modules:
        try:
            importlib.import_module("jinja2")
        except ModuleNotFoundError:
            def _no_jinja(*_args, **_kwargs):
                raise RuntimeError(
                    "jinja2 is absent and only STUBBED for load_stores' runtime probe — "
                    "rendering is unavailable in this environment"
                )

            stub = types.ModuleType("jinja2")
            stub.Environment = _no_jinja
            stub.FileSystemLoader = _no_jinja
            sys.modules["jinja2"] = stub
            try:
                return importlib.import_module("scripts.build_options_command")
            finally:
                sys.modules.pop("jinja2", None)
    return importlib.import_module("scripts.build_options_command")


def test_load_stores_probes_exactly_the_documented_paths_at_RUNTIME():
    """MINOR 12: the source-regex above cannot see a path built purely by f-string — it
    only caught `site/gex` from the INDEX_KEYS loop and would miss a whole new store added
    the same way. Record what load_stores actually asks for, which is f-string-proof."""
    boc = _import_builder()

    probed: list[str] = []
    real_load = boc._load

    def _spy(path):
        probed.append(str(path))
        return real_load(path)

    boc._load = _spy
    try:
        boc.load_stores(Path("/nonexistent-root-for-probing"))
    finally:
        boc._load = real_load

    rel = set()
    for raw in probed:
        s = raw.replace("/nonexistent-root-for-probing/", "")
        # collapse the INDEX_KEYS family to its directory, as WORKSPACE_STORES documents it
        rel.add("site/gex" if (s.startswith("site/gex/") and s != "site/gex/index.json")
                else s)
    assert rel == set(WORKSPACE_STORES), (
        "build_options_command.load_stores PROBED a different path set than "
        f"WORKSPACE_STORES documents.  Added: {sorted(rel - set(WORKSPACE_STORES))}; "
        f"removed: {sorted(set(WORKSPACE_STORES) - rel)}.  Decide each new store's "
        "express-lane coverage and record it."
    )
    assert len(probed) >= len(WORKSPACE_STORES), probed


def test_load_stores_source_literals_match_the_documented_set():
    """Kept as the cheap static twin of the runtime probe above."""
    read = _store_paths_read_by_load_stores()
    assert read == set(WORKSPACE_STORES), (
        "build_options_command.load_stores changed.  Added: "
        f"{sorted(read - set(WORKSPACE_STORES))}; removed: "
        f"{sorted(set(WORKSPACE_STORES) - read)}.  Decide each new store's express-lane "
        "coverage and record it in WORKSPACE_STORES."
    )


@pytest.mark.parametrize("lane", sorted(EXPRESS_LANES))
def test_every_workspace_store_producer_is_accounted_for(lane):
    text = EXPRESS_LANES[lane]
    for store, (producer, disposition) in sorted(WORKSPACE_STORES.items()):
        if disposition == "wired":
            # build_gex_board is deliberately absent from engine-render's auto band
            # (~700 live Cboe chain fetches); the narrow gex dispatch runs it there.
            assert producer in text, (
                f"{lane}: {store} is produced by {producer}, declared 'wired', but that "
                "module appears nowhere in the lane"
            )
        else:
            assert producer in ACCEPTED_COMMITTED, (
                f"{lane}: {store}'s producer {producer} is neither wired nor an accepted "
                "committed-vintage input"
            )


# --------------------------------------------------------------- nightly unchanged


def test_daily_still_builds_the_workspace_post_band():
    """Gate: this change must not touch the nightly's own (correct) placement."""
    assert "python -m scripts.build_options_command" in DAILY
    engine = DAILY.split("  engine:", 1)[1]
    assert engine.index("check_builder_failstreaks") < engine.index("scripts.build_options_command"), (
        "build_options_command must stay AFTER the band wait barrier in daily.yml"
    )
