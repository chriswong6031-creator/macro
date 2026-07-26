"""Every page builder emits the data-base shim — proved by RUNNING the builder.

tests/test_site_shim.py holds the source guard (no raw write_text on an *.html
target) and the committed-page tripwire. Both are indirect: the guard reads
source, and the tripwire reads pages the render lane's inject_data_base sweep has
already healed. Neither actually runs a builder, which is why nine builders sat
green while shipping shim-less pages — visible ONLY in a standalone run.

This file closes that gap the way #3635 proved build_leader_radar: point the real
entry point at a fixture root with the repo's templates/ symlinked in, then read
the page it wrote back off disk.

Why the assertion is the MARKER, not "window.DATA_BASE": flow_desk.html.j2 and
intraday_flow.html.j2 reference window.DATA_BASE in their own page JS (4 and 2
times) to build per-ticker fetch URLs. Before the fix those pages contained the
string while carrying nothing that DEFINED it — the read was live, the definition
was missing. Only `<script data-dbase>` separates a working page from that one.

Run: .venv/bin/python -m pytest tests/test_builder_shim_writes.py -q
"""
from __future__ import annotations

import importlib
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


# (id, needs content/, invoke(fixture_root), page path relative to site/)
CASES = [
    (
        "build_flow_desk",
        False,
        lambda f: _mod("build_flow_desk")._render_html({}, f / "site"),
        "flow_desk.html",
    ),
    (
        "build_flow_leaders",
        False,
        lambda f: _mod("build_flow_leaders").build(f / "data", f / "site", ROOT / "templates"),
        "flow_leaders.html",
    ),
    (
        "build_intraday_flow",
        False,
        lambda f: _mod("build_intraday_flow")._run_nightly({}, f / "data", f / "site", ROOT / "templates"),
        "intraday_flow.html",
    ),
    (
        "build_leader_radar",
        False,
        lambda f: _mod("build_leader_radar").build(f / "data", f / "site"),
        "leader_radar.html",
    ),
    (
        "build_state_of_themes",
        False,
        lambda f: _mod("build_state_of_themes").main(["--root", str(f)]),
        "state_of_themes.html",
    ),
    (
        "build_market_structure_page",
        False,
        lambda f: _mod("build_market_structure_page").main(["--root", str(f)]),
        "market_structure.html",
    ),
    (
        "build_stage_analysis_page",
        False,
        lambda f: _mod("build_stage_analysis_page").main(["--root", str(f)]),
        "stage_analysis.html",
    ),
    (
        "build_options_command",
        False,
        lambda f: _mod("build_options_command").main(["--root", str(f)]),
        "options.html",
    ),
    # free_content renders many pages from content/seo/; the blog hub stands for
    # the four write sites in that builder (article, blog, learn, tools, calc).
    (
        "build_free_content",
        True,
        lambda f: _mod("build_free_content").render_all(f / "site"),
        "blog/index.html",
    ),
]


@pytest.mark.parametrize(
    "name,needs_content,invoke,page_rel",
    CASES,
    ids=[c[0] for c in CASES],
)
def test_builder_writes_page_with_shim(tmp_path, name, needs_content, invoke, page_rel):
    fixture = _fixture_root(tmp_path, content=needs_content)

    invoke(fixture)

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
    _mod("build_free_content").render_all(fixture / "site")

    site = fixture / "site"
    pages = sorted(site.rglob("*.html"))
    assert len(pages) > 20, f"expected the full free estate, got {len(pages)} page(s)"

    missing = [str(p.relative_to(site)) for p in pages if DBASE_MARKER not in p.read_text(errors="ignore")]
    assert not missing, f"{len(missing)} free-estate page(s) written without the shim: {missing[:10]}"
