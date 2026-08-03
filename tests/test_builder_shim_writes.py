"""Every page builder emits the data-base shim — proved by RUNNING the builder.

tests/test_site_shim.py holds the source guard (no raw write_text on an *.html
target) and the committed-page tripwire. Both are indirect: the guard reads
source, and the tripwire reads pages the render lane's inject_data_base sweep has
already healed. Neither actually runs a builder, which is why nine builders sat
green while shipping shim-less pages — visible ONLY in a standalone run.

This file closes that gap the way #3635 proved build_leader_radar: point the real
entry point at a fixture root with the repo's templates/ symlinked in, then read
the page it wrote back off disk.

Why the assertion is the MARKER, not "window.DATA_BASE": intraday_flow.html.j2
references window.DATA_BASE in its own page JS to build per-ticker fetch URLs
(flow_desk.html.j2 did too, until W1.6-B turned it into a redirect stub — see the
CASES note below). Before the fix those pages contained the string while carrying
nothing that DEFINED it — the read was live, the definition was missing. Only
`<script data-dbase>` separates a working page from that one.

Run: .venv/bin/python -m pytest tests/test_builder_shim_writes.py -q
"""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402
from lib.pages import DBASE_MARKER  # noqa: E402

ROOT = config.ROOT


@pytest.fixture(autouse=True)
def _no_committed_registry_writes(monkeypatch):
    """Keep the committed run_status registry out of this suite.

    build_intraday_flow._run_nightly registers itself in data/run_status.json
    through lib.store, which resolves against config.ROOT — the REAL repo, not
    the fixture root. Running it here would dirty a tracked file (and trip
    MM_DATA_GUARD). The registration is orthogonal to what this file proves, so
    stub it rather than patch config.ROOT: repointing ROOT would also move the
    shim source out from under lib.pages and prove nothing about the real one.
    """
    from lib import store

    monkeypatch.setattr(store, "write_status", lambda *a, **k: None)


def _fixture_root(tmp_path: Path, *, content: bool = False) -> Path:
    """A throwaway repo root: real templates/, empty data/ and site/.

    Empty data/ is deliberate — every builder here is fail-soft and renders its
    honest warm-up/empty state, which is enough to exercise the write path
    without pinning the test to today's artifacts.
    """
    (tmp_path / "templates").symlink_to(ROOT / "templates")
    (tmp_path / "site").mkdir()
    (tmp_path / "data").mkdir()
    if content:
        (tmp_path / "content").symlink_to(ROOT / "content")
    return tmp_path


def _mod(name: str):
    return importlib.import_module(f"scripts.{name}")


# WHY THE OPTIONS ESTATE'S FOUR PAGES ARE ABSENT (OIP W1.6-B): gex.html,
# options_screener.html, flow_desk.html and flow_leaders.html are redirect stubs
# now — self-contained interstitials that load no assets and run no per-ticker
# fetch, so there is nothing on them for the data-base shim to reroute. Their
# builders still write through write_page (tests/test_site_shim.py's source guard
# keeps that true), so the shim is still injected; it is the CLAIM that would go
# vacuous, not the tag. What those pages must be instead is pinned by
# tests/test_options_estate_redirect_stubs.py. build_options_command (options.html,
# the page that ABSORBED all four) stays below — it is the surface that actually
# fetches per-ticker data now.
#
# (id, needs content/, invoke(fixture_root, monkeypatch), page relative to site/)
CASES = [
    (
        "build_intraday_flow",
        False,
        lambda f, mp: _mod("build_intraday_flow")._run_nightly({}, f / "data", f / "site", ROOT / "templates"),
        "intraday_flow.html",
    ),
    (
        "build_leader_radar",
        False,
        lambda f, mp: _mod("build_leader_radar").build(f / "data", f / "site"),
        "leader_radar.html",
    ),
    (
        "build_state_of_themes",
        False,
        lambda f, mp: _mod("build_state_of_themes").main(["--root", str(f)]),
        "state_of_themes.html",
    ),
    (
        "build_market_structure_page",
        False,
        lambda f, mp: _mod("build_market_structure_page").main(["--root", str(f)]),
        "market_structure.html",
    ),
    (
        "build_stage_analysis_page",
        False,
        lambda f, mp: _mod("build_stage_analysis_page").main(["--root", str(f)]),
        "stage_analysis.html",
    ),
    (
        "build_options_command",
        False,
        lambda f, mp: _mod("build_options_command").main(["--root", str(f)]),
        "options.html",
    ),
    # free_content renders many pages from content/seo/; the blog hub stands for
    # the write sites in that builder (product, article, hubs, tools, calc).
    (
        "build_free_content",
        True,
        lambda f, mp: _mod("build_free_content").render_all(f / "site"),
        "blog/index.html",
    ),
    # The OTHER guard-blind write in the tree. An AST sweep over all 99 builders
    # that call write_page found exactly two page writes whose path is never a
    # source literal at the write: build_free_content's article write (above) and
    # this one, `out = site / PAGE_OUT` against a module constant. The source
    # guard now propagates html-ness through names so it can see this shape, but
    # a runtime proof is what actually holds a path the static layers can lose.
    (
        "build_qa_bottom_sensors",
        False,
        lambda f, mp: (_seed_bottom_sensors(f), _point_root_at(mp, f),
                       _mod("build_qa_bottom_sensors").build(f)),
        "qa_bottom_sensors.html",
    ),
]


def _point_root_at(monkeypatch, fixture: Path) -> None:
    """Repoint config.ROOT at the fixture for builders that ignore their root arg.

    build_qa_bottom_sensors resolves its output through _site_dir(), which reads
    config.ROOT rather than the `root` it was handed — so calling build(fixture)
    writes into the REAL site/ and dirties a tracked file. Repointing ROOT is safe
    HERE only because _fixture_root symlinks the repo's templates/ in: lib.pages
    still finds templates/data_base.js under the patched ROOT, so the shim it
    injects is the real one, and its per-source-path cache (#3635) keeps this
    fixture's entry from leaking into any other suite in the process.
    """
    from lib import config as _config

    monkeypatch.setattr(_config, "ROOT", fixture)


def _seed_bottom_sensors(fixture: Path) -> None:
    """Minimal bottom_sensors payload — this builder is NOT fail-soft.

    Unlike the others here it raises FileNotFoundError rather than rendering a
    warm-up state, so an empty fixture proves nothing. One row is enough to reach
    the write; the shim does not depend on row content.
    """
    out = fixture / "site" / "neuralwebdata"
    out.mkdir(parents=True, exist_ok=True)
    (out / "bottom_sensors.json").write_text(json.dumps({
        "as_of": "2026-07-26",
        "labels_version": "labels_v1",
        "is_display_only": True,
        "n_rows": 1,
        "rows": [{"ticker": "TEST", "state": "watch"}],
    }))


@pytest.mark.parametrize(
    "name,needs_content,invoke,page_rel",
    CASES,
    ids=[c[0] for c in CASES],
)
def test_builder_writes_page_with_shim(tmp_path, monkeypatch, name, needs_content, invoke, page_rel):
    fixture = _fixture_root(tmp_path, content=needs_content)

    invoke(fixture, monkeypatch)

    page = fixture / "site" / page_rel
    assert page.exists(), f"{name} wrote no page at site/{page_rel}"
    text = page.read_text(errors="ignore")

    assert f"<script {DBASE_MARKER}>" in text, (
        f"{name} wrote site/{page_rel} WITHOUT the data-base shim — its per-ticker "
        "fetches resolve against Pages instead of R2 in any run outside the render "
        "lane's inject_data_base sweep. Write through lib.pages.write_page."
    )
    assert "window.DATA_BASE" in text, f"{name}: shim tag present but body empty"
    assert text.count(DBASE_MARKER) == 1, f"{name}: shim injected more than once"


def test_free_content_renders_every_family_with_shim(tmp_path):
    """free_content's article write is the one target NO source guard can see.

    Its path comes from _output_path(), whose ".html" lives in the content
    frontmatter rather than in any source literal — so neither the line regex nor
    the AST pass in tests/test_site_shim.py can reach it. This is the only thing
    standing between that write path and a silent regression.
    """
    fixture = _fixture_root(tmp_path, content=True)
    bfc = _mod("build_free_content")
    bfc.render_all(fixture / "site")

    site = fixture / "site"
    pages = sorted(site.rglob("*.html"))
    assert len(pages) > 20, f"expected the full free estate, got {len(pages)} page(s)"
    assert (site / "products" / "index.html").exists()

    # The flagship product pages are hand-authored SOURCE (build_free_content's
    # HAND_AUTHORED carve-out), so a fresh render deliberately produces none of
    # them — their committed bytes carry their own shim and this builder must
    # not overwrite them. Asserting their ABSENCE keeps the shim sweep below
    # honest: without it, a regression that resumed writing them would be graded
    # by a loop that never saw the file.
    rendered_flagships = [rel for rel in sorted(bfc.HAND_AUTHORED) if (site / rel).exists()]
    assert not rendered_flagships, (
        f"render_all overwrote hand-authored source page(s): {rendered_flagships}"
    )

    missing = [str(p.relative_to(site)) for p in pages if DBASE_MARKER not in p.read_text(errors="ignore")]
    assert not missing, f"{len(missing)} free-estate page(s) written without the shim: {missing[:10]}"
