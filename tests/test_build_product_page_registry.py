"""Tests for scripts/build_product_page_registry.py.

Two halves:

  * a SCHEMA suite that runs against the committed
    ``data/product_experience/page_registry.json`` — this is the CI drift guard,
    and it is the only part that touches a real artifact;
  * DERIVATION units built on tmp_path fixtures with an injected ``run_git``
    callable, so no test reads a sister repo, calls git, calls gh, or touches
    the network.  Everything here is TZ-agnostic (CI runs UTC).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import build_product_page_registry as reg

REPO_ROOT = Path(__file__).resolve().parents[1]
REGISTRY = REPO_ROOT / "data" / "product_experience" / "page_registry.json"
OVERRIDES = REPO_ROOT / "config" / "product_experience" / "page_registry_overrides.yml"


# ---------------------------------------------------------------------------
# committed artifact — schema invariants (the CI drift guard)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def committed() -> dict:
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


def test_committed_registry_passes_schema_invariants(committed):
    problems = reg.validate(committed)
    assert problems == [], "\n".join(problems)


def test_committed_registry_covers_all_three_repos(committed):
    counts: dict[str, int] = {}
    for row in committed["pages"]:
        counts[row["repo"]] = counts.get(row["repo"], 0) + 1
    # Floors, not exact counts: the census grows with the product.
    assert counts.get("macro", 0) >= 60, counts
    assert counts.get("terminal", 0) >= 13, counts
    assert counts.get("mastermind", 0) >= 7, counts


def test_committed_registry_records_a_terminal_sha(committed):
    terminal = committed["sources"]["terminal"]
    assert terminal["available"] is True
    assert terminal["ref"] == "origin/master"
    assert len(terminal["sha"]) == 40, terminal["sha"]


def test_committed_page_ids_are_unique(committed):
    ids = [row["page_id"] for row in committed["pages"]]
    assert len(ids) == len(set(ids))


def test_committed_rows_never_use_null_for_unknown(committed):
    for row in committed["pages"]:
        for field, value in row.items():
            assert value is not None, f"{row['page_id']}.{field} is null"


def test_every_committed_row_cites_evidence(committed):
    missing = [row["page_id"] for row in committed["pages"]
               if not row["source_evidence"]]
    assert missing == []


def test_committed_overrides_all_resolve(committed):
    known = {row["page_id"] for row in committed["pages"]}
    stale = sorted(set(reg.load_overrides(OVERRIDES)) - known)
    assert stale == [], f"stale overrides: {stale}"


def test_committed_overrides_only_set_overridable_fields():
    for page_id, entry in reg.load_overrides(OVERRIDES).items():
        for key in entry:
            assert key in reg.OVERRIDABLE or key in reg.OVERRIDE_META, \
                f"{page_id}: {key} is derived-only"


# ---------------------------------------------------------------------------
# fake macro repo
# ---------------------------------------------------------------------------

SITE_ACCESS = """
schema: site_access.v1
public:
  exact:
    - /
    - /index.html
    - /alpha.html
    - /delta.html
  prefixes:
    - /stocks/
free_registered:
  exact:
    - /beta.html
  prefixes: []
deny:
  exact:
    - /status.html
  prefixes: []
premium:
  default_tier: essential
  enforced_early:
    exact: []
    prefixes:
      - /premiumdata/
"""

NAVLINKS = """
<div class="nav-links">
  <a class="nav-brand" href="{{ NP }}start.html">Home</a>
  <div class="nav-dd">
    <a class="nav-link" href="{{ NP }}alpha.html">{{ t('United States', '美国') }}</a>
    <div class="nav-dd-menu">
      <a class="nav-mega-item" href="{{ NP }}beta.html">Beta</a>
    </div>
  </div>
  <div class="nav-dd">
    <a class="nav-link" href="{{ NP }}gamma.html">{{ t('Research', '研究') }}</a>
  </div>
</div>
"""

PUBLIC_NAV = """
<nav><a href="{{ rel }}index.html">Home</a><a href="{{ rel }}alpha.html">Alpha</a></nav>
"""

# Mirrors the real footer's shape: a brand tagline that is NOT a column heading,
# per-column bare `<p>` headings (one translated, one plain), a link the navs
# also carry, and a bottom strip that repeats links under no heading at all.
PUBLIC_FOOTER = """
<footer class="public-footer">
  <div class="f-brand">
    <p class="ft">{{ t('A tagline, not a column heading.', '一句标语。') }}</p>
  </div>
  <div class="f-cols">
    <div class="f-col">
      <p>{{ t('Platform', '平台') }}</p>
      <a href="{{ rel }}alpha.html">Alpha</a>
      <a href="{{ rel }}delta.html">Delta</a>
    </div>
    <div class="f-col">
      <p>Legal</p>
      <a href="{{ rel }}products/handmade.html">Handmade</a>
    </div>
  </div>
  <div class="f-bot">
    <span>© 2026</span>
    <span class="f-legal"><a href="{{ rel }}products/handmade.html">Handmade</a>
      · <a href="{{ rel }}delta.html">Delta</a></span>
  </div>
</footer>
"""

BUILDER = '''
from lib.pages import write_page

def main(site):
    tmpl = env.get_template("alpha.html.j2")
    write_page(site / "alpha.html", tmpl.render())
    write_page(site / "beta.html", env.get_template("beta.html.j2").render())
    write_page(site / "delta.html", env.get_template("delta.html.j2").render())
    out = site / "stocks"
    for t in tickers:
        write_page(out / f"{t}.html", ticker_tmpl.render())
'''

PAGES_PY = '''
HAND_AUTHORED_PAGES = frozenset({
    "products/handmade.html",
})
'''

SEO_PY = '''
_EXCLUDE_PREFIXES = frozenset({"_mockup"})
_EXCLUDE_NAMES = frozenset({"status", "alpha_lab"})
'''

TRACKED = [
    "site/index.html",
    "site/alpha.html",
    "site/alpha_lab.html",
    "site/beta.html",
    "site/gamma.html",
    "site/delta.html",
    "site/status.html",
    "site/products/index.html",
    "site/products/handmade.html",
    "site/stocks/index.html",
    "site/stocks/AAPL.html",
    "site/stocks/MSFT.html",
]


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture()
def macro_repo(tmp_path: Path) -> Path:
    root = tmp_path / "macro"
    _write(root / "config" / "site_access.yml", SITE_ACCESS)
    _write(root / "templates" / "_navlinks.html.j2", NAVLINKS)
    _write(root / "templates" / "_public_nav.html.j2", PUBLIC_NAV)
    _write(root / "templates" / "_public_footer.html.j2", PUBLIC_FOOTER)
    _write(root / "templates" / "alpha.html.j2",
           "<html data-theme='light'>{{ t('Hi', '你好') }}</html>")
    _write(root / "templates" / "beta.html.j2", "<html>plain</html>")
    _write(root / "templates" / "delta.html.j2",
           "<html data-theme='light'>fetch('/premiumdata/delta.json')</html>")
    _write(root / "templates" / "index.html", "<html>{{ t('Home', '首页') }}</html>")
    _write(root / "templates" / "gamma.html", "<html>plain copy</html>")
    _write(root / "scripts" / "build_demo.py", BUILDER)
    _write(root / "lib" / "pages.py", PAGES_PY)
    _write(root / "lib" / "seo.py", SEO_PY)
    return root


def fake_git(tracked: list[str] | None = None, sha: str = "a" * 40):
    listing = "\n".join(TRACKED if tracked is None else tracked) + "\n"

    def _git(root: Path, args: list[str]):
        if args[:2] == ["ls-files", "site/*.html"]:
            return listing
        if args[0] == "rev-parse":
            return sha + "\n"
        if args[0] == "status":
            return ""
        return None
    return _git


def rows_by_id(rows: list[dict]) -> dict[str, dict]:
    return {row["page_id"]: row for row in rows}


# ---------------------------------------------------------------------------
# macro derivation
# ---------------------------------------------------------------------------

def test_macro_derives_routes_builders_and_templates(macro_repo):
    rows, source = reg.derive_macro(macro_repo, git=fake_git())
    index = rows_by_id(rows)
    alpha = index["macro:alpha"]
    assert alpha["route"] == "/alpha.html"
    assert alpha["route_kind"] == "page"
    assert alpha["builder"] == ["scripts/build_demo.py"]
    assert alpha["source_template"] == "templates/alpha.html.j2"
    assert alpha["generated"] is True
    assert "scripts/build_demo.py:6" in alpha["source_evidence"]
    assert source["available"] is True
    assert source["tracked_html_pages"] == len(TRACKED)


def test_macro_nav_family_comes_from_the_nav_templates(macro_repo):
    index = rows_by_id(reg.derive_macro(macro_repo, git=fake_git())[0])
    assert index["macro:alpha"]["nav_family"] == "product_nav.united_states"
    assert index["macro:beta"]["nav_family"] == "product_nav.united_states"
    assert index["macro:gamma"]["nav_family"] == "product_nav.research"
    # index.html is only in the public nav
    assert index["macro:index"]["nav_family"] == "public_nav.public"
    # A page no nav and no footer names is an ORPHAN and says so — it is not
    # "unknown".
    assert index["macro:alpha_lab"]["nav_family"] == "none"


def test_macro_footer_rescues_a_page_the_navs_do_not_link(macro_repo):
    """The public footer is a link inventory too, so a page only IT names is
    not an orphan — and it carries the footer COLUMN that names it."""
    index = rows_by_id(reg.derive_macro(macro_repo, git=fake_git())[0])
    assert index["macro:delta"]["nav_family"] == "footer.platform"
    # a column heading with no t() helper reads just as well
    assert index["macro:products_handmade"]["nav_family"] == "footer.legal"


def test_macro_nav_outranks_the_footer_for_the_same_route(macro_repo):
    """alpha.html sits in both navs AND in the footer: the footer is the
    lowest-precedence source, so it never overwrites a nav family."""
    index = rows_by_id(reg.derive_macro(macro_repo, git=fake_git())[0])
    alpha = index["macro:alpha"]
    assert alpha["nav_family"] == "product_nav.united_states"
    assert "templates/_public_footer.html.j2" not in alpha["source_evidence"]


def test_macro_footer_sourced_row_cites_the_footer_template(macro_repo):
    """The family and the file it came from move together."""
    evidence = rows_by_id(reg.derive_macro(macro_repo, git=fake_git())[0])[
        "macro:delta"]["source_evidence"]
    assert "templates/_public_footer.html.j2" in evidence
    assert "templates/_navlinks.html.j2" not in evidence
    assert "templates/_public_nav.html.j2" not in evidence


def test_footer_bottom_strip_never_moves_a_route_to_another_column():
    """The `f-bot` strip repeats links under no heading; FIRST occurrence wins,
    so a repeated route keeps the column that named it rather than the column
    that happens to be open when the strip is reached."""
    footer = reg.parse_footer(PUBLIC_FOOTER, group_prefix="footer")
    assert footer["/products/handmade.html"] == "footer.legal"
    assert footer["/delta.html"] == "footer.platform"


def test_footer_reads_only_a_bare_paragraph_as_a_column_heading():
    """`<p class="ft">` is the brand tagline, not a heading — letting it open a
    group would file the first column under a marketing sentence."""
    footer = reg.parse_footer(PUBLIC_FOOTER, group_prefix="footer")
    assert set(footer.values()) == {"footer.platform", "footer.legal"}
    # a link that precedes every heading still lands somewhere honest
    assert reg.parse_footer('<a href="x.html">X</a>', group_prefix="footer") == \
        {"/x.html": "footer.brand"}


def test_macro_lifecycle_from_lab_suffix_and_deny_bucket(macro_repo):
    index = rows_by_id(reg.derive_macro(macro_repo, git=fake_git())[0])
    assert index["macro:alpha_lab"]["lifecycle"] == "lab"
    status = index["macro:status"]
    assert status["lifecycle"] == "internal"
    assert status["payload_tier"] == "internal"
    assert status["access_shell"] == "unknown"
    assert any("deny" in note for note in status["notes"])


def test_macro_payload_tier_splits_public_from_gated(macro_repo):
    index = rows_by_id(reg.derive_macro(macro_repo, git=fake_git())[0])
    assert index["macro:alpha"]["payload_tier"] == "public"
    # free_registered: the shell is anonymous, the payload is not public
    assert index["macro:beta"]["payload_tier"] == "public_shell_premium_payload"
    assert "site_access.v1:free_registered" in index["macro:beta"]["known_contracts"]
    assert index["macro:alpha"]["access_shell"] == "anonymous"


def test_macro_public_shell_over_a_premium_payload_is_its_own_tier(macro_repo):
    """A public page whose template fetches a premium-enforced payload is NOT
    simply "public" — the split between shell and payload is the product."""
    index = rows_by_id(reg.derive_macro(macro_repo, git=fake_git())[0])
    assert index["macro:delta"]["payload_tier"] == "public_shell_premium_payload"


def test_macro_unknown_stays_the_literal_unknown(macro_repo):
    """A page no builder claims keeps "unknown" — never a guess, never null."""
    index = rows_by_id(reg.derive_macro(macro_repo, git=fake_git())[0])
    lab = index["macro:alpha_lab"]
    assert lab["source_template"] == "unknown"
    assert lab["builder"] == []
    assert lab["generated"] == "unknown"
    assert lab["bilingual"] == "unknown"
    assert lab["themes"] == "unknown"
    assert all(value is not None for value in lab.values())


def test_macro_plain_copy_pair_is_not_reported_as_generated(macro_repo):
    gamma = rows_by_id(reg.derive_macro(macro_repo, git=fake_git())[0])["macro:gamma"]
    assert gamma["generated"] is False
    assert gamma["source_template"] == "templates/gamma.html"


def test_macro_hand_authored_page_gets_its_own_row(macro_repo):
    index = rows_by_id(reg.derive_macro(macro_repo, git=fake_git())[0])
    hand = index["macro:products_handmade"]
    assert hand["generated"] is False
    assert hand["source_template"] == "site/products/handmade.html"
    assert "macro:products_index" in index  # family hubs keep their own row


def test_macro_collapses_a_directory_into_one_family_row(macro_repo):
    index = rows_by_id(reg.derive_macro(macro_repo, git=fake_git())[0])
    family = index["macro:stocks_family"]
    assert family["route_kind"] == "family"
    assert family["route"] == "/stocks/<t>.html"
    assert family["builder"] == ["scripts/build_demo.py"]
    assert any("2 committed pages" in note for note in family["notes"])
    # the members themselves do NOT get rows; the hub does
    assert "macro:stocks_aapl" not in index
    assert "macro:stocks_index" in index


def test_macro_chrome_facts_read_the_template_not_a_blanket_rule(macro_repo):
    index = rows_by_id(reg.derive_macro(macro_repo, git=fake_git())[0])
    assert index["macro:alpha"]["bilingual"] is True
    assert index["macro:alpha"]["themes"] == ["light", "dark"]
    assert index["macro:alpha"]["locales"] == ["en", "zh"]
    # beta.html.j2 has neither the translation helper nor a theme attribute
    assert index["macro:beta"]["bilingual"] is False
    assert index["macro:beta"]["themes"] == "unknown"


def test_macro_survives_a_repo_with_no_git(macro_repo):
    rows, source = reg.derive_macro(macro_repo, git=lambda root, args: None)
    assert source["sha"] == "unknown"
    assert source["page_inventory"] == "write_page() call sites only"
    # the builder's own write sites still produce rows
    assert "macro:alpha" in rows_by_id(rows)


# ---------------------------------------------------------------------------
# path-expression resolution
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("expr,names,expected", [
    ("site / 'x.html'", {}, ("/x.html", False)),
    ("site_root / 'x.html'", {}, ("/x.html", False)),
    ("config.ROOT / 'site' / 'x.html'", {}, ("/x.html", False)),
    ("Path(a.root).resolve() if a.root else _REPO / 'site' / 'x.html'", {},
     ("/x.html", False)),
    ("Path(config.load()['storage']['site_dir']) / 'sectors' / f'{fund}.html'", {},
     ("/sectors/<fund>.html", True)),
    ("out / f'{ticker}.html'", {"out": "site / 'stocks'"},
     ("/stocks/<ticker>.html", True)),
    ("site / f'strategy_{spec.key}.html'", {}, ("/strategy_<key>.html", True)),
    ("site / _PAGE", {"_PAGE": "'named.html'"}, ("/named.html", False)),
    ("out_dir / (bid + '.html')", {"out_dir": "site / out_name"},
     ("/<out_name>/<bid>.html", True)),
])
def test_resolve_path_expr(expr, names, expected):
    assert reg._resolve_path_expr(expr, names) == expected


def test_resolve_path_expr_refuses_an_unanchored_expression():
    assert reg._resolve_path_expr("destination", {}) is None
    assert reg._resolve_path_expr("tmp_dir / 'x.html'", {}) is None


def test_family_pattern_refuses_a_pattern_that_matches_everything():
    """`/<name>.html` names no page in particular, so it attributes none."""
    assert reg._family_pattern("/<name>.html") is None
    assert reg._family_pattern("/alpha.html") is None
    pattern = reg._family_pattern("/fund_<slug>.html")
    assert pattern is not None
    assert pattern.match("/fund_berkshire.html")
    assert not pattern.match("/alpha.html")
    assert not pattern.match("/stocks/fund_x.html")


# ---------------------------------------------------------------------------
# terminal / mastermind derivation (injected git, no sister repo)
# ---------------------------------------------------------------------------

TERMINAL_TREE = "\n".join([
    "terminal/app/page.tsx",
    "terminal/app/layout.tsx",
    "terminal/app/(shell)/discover/page.tsx",
    "terminal/app/(shell)/options/page.tsx",
    "terminal/app/(shell)/admin/page.tsx",
    "terminal/app/dev/theater/page.tsx",
    "terminal/app/x/[slug]/page.tsx",
])

TERMINAL_FILES = {
    "terminal/components/AppNav.tsx":
        'export const TOP = [\n  { k: "discover", label: "Discover", href: "/discover" },\n];\n',
    "terminal/app/layout.tsx": '<html lang="en" data-theme="dark">',
    "terminal/lib/i18n.tsx": 'export type Lang = "en" | "zh";',
    "terminal/app/(shell)/discover/page.tsx": 'import SignupGate from "x";',
    "terminal/app/(shell)/options/page.tsx": 'import { hasLiveOptions } from "y";',
    "terminal/app/(shell)/admin/page.tsx": 'import { isAdminRequest } from "z";',
    "terminal/app/page.tsx": "export default function Landing() {}",
    "terminal/app/dev/theater/page.tsx": "export default function Theater() {}",
    "terminal/app/x/[slug]/page.tsx": "export default function Slug() {}",
}


def fake_terminal_git(root: Path, args: list[str]):
    if args[0] == "ls-tree":
        return TERMINAL_TREE + "\n"
    if args[0] == "rev-parse":
        return "b" * 40 + "\n"
    if args[0] == "show":
        return TERMINAL_FILES.get(args[1].split(":", 1)[1])
    return None


def test_terminal_routes_strip_route_groups_and_mark_families(tmp_path):
    root = tmp_path / "charting-app"
    root.mkdir()
    rows, source = reg.derive_terminal(root, "origin/master", git=fake_terminal_git)
    index = rows_by_id(rows)
    assert source["sha"] == "b" * 40
    assert index["terminal:landing"]["route"] == "/"
    assert index["terminal:discover"]["route"] == "/discover"   # (shell) dropped
    assert index["terminal:x_slug"]["route"] == "/x/<slug>"
    assert index["terminal:x_slug"]["route_kind"] == "family"


def test_terminal_gate_markers_drive_access_shell(tmp_path):
    root = tmp_path / "charting-app"
    root.mkdir()
    index = rows_by_id(reg.derive_terminal(root, "origin/master",
                                           git=fake_terminal_git)[0])
    assert index["terminal:discover"]["access_shell"] == "signed_in"
    assert index["terminal:options"]["access_shell"] == "paid"
    assert index["terminal:options"]["payload_tier"] == "premium"
    assert index["terminal:admin"]["access_shell"] == "admin"
    # No marker is NOT proof of anonymity — the overrides file carries that fact.
    assert index["terminal:landing"]["access_shell"] == "unknown"


def test_terminal_theme_locale_and_dev_lifecycle(tmp_path):
    root = tmp_path / "charting-app"
    root.mkdir()
    index = rows_by_id(reg.derive_terminal(root, "origin/master",
                                           git=fake_terminal_git)[0])
    assert index["terminal:discover"]["themes"] == ["dark"]
    assert index["terminal:discover"]["locales"] == ["en", "zh"]
    assert index["terminal:discover"]["bilingual"] is True
    assert index["terminal:discover"]["nav_family"] == "app_nav.rail"
    assert index["terminal:dev_theater"]["lifecycle"] == "dev_only"


def test_missing_sister_repo_is_recorded_not_fatal(tmp_path):
    rows, source = reg.derive_terminal(tmp_path / "absent", "origin/master",
                                       git=fake_terminal_git)
    assert rows == []
    assert source["available"] is False
    assert "reason" in source

    rows, source = reg.derive_mastermind(tmp_path / "absent",
                                         git=lambda root, args: None)
    assert rows == []
    assert source["available"] is False


MASTERMIND_WEB = '''
from fastapi import APIRouter
router = APIRouter()

@router.get("/", include_in_schema=False)
def dashboard():
    return FileResponse(_STATIC / "index.html", media_type="text/html")

@router.get("/portfolio_desk", include_in_schema=False)
def portfolio_desk_page():
    return FileResponse(_STATIC / "portfolio_desk.html", media_type="text/html")

@router.get("/theme.css", include_in_schema=False)
def theme_css():
    return FileResponse(_STATIC / "theme.css", media_type="text/css")

@router.get("/api/performance")
def performance():
    return {"ok": True}
'''


def test_mastermind_html_routes_only(tmp_path):
    root = tmp_path / "Mastermind"
    _write(root / "app" / "web.py", MASTERMIND_WEB)
    rows, source = reg.derive_mastermind(
        root, git=lambda r, a: "master\n" if a[1:2] == ["--abbrev-ref"] else "c" * 40)
    index = rows_by_id(rows)
    assert sorted(index) == ["mastermind:index", "mastermind:portfolio_desk"]
    assert index["mastermind:portfolio_desk"]["route"] == "/portfolio_desk"
    assert index["mastermind:portfolio_desk"]["access_shell"] == "anonymous"
    assert index["mastermind:portfolio_desk"]["payload_tier"] == "public"
    assert index["mastermind:index"]["source_template"] == "app/static/index.html"
    assert source["html_routes"] == 2


# ---------------------------------------------------------------------------
# overrides
# ---------------------------------------------------------------------------

def test_overrides_merge_onto_the_derived_row():
    rows = [reg.blank_row("macro:alpha", "macro", "/alpha.html")]
    errors = reg.apply_overrides(rows, {
        "macro:alpha": {
            "priority": "P0",
            "archetype": "ranked_decision_board",
            "primary_user_question": "Which names are set up?",
            "evidence": ["docs/x.md"],
            "note": "seeded by hand",
        },
    }, source_name="test.yml")
    assert errors == []
    assert rows[0]["priority"] == "P0"
    assert rows[0]["archetype"] == "ranked_decision_board"
    assert "docs/x.md" in rows[0]["source_evidence"]
    assert "seeded by hand" in rows[0]["notes"]


def test_override_on_an_unknown_page_id_is_a_hard_error():
    rows = [reg.blank_row("macro:alpha", "macro", "/alpha.html")]
    errors = reg.apply_overrides(rows, {"macro:ghost": {"priority": "P0"}},
                                 source_name="test.yml")
    assert len(errors) == 1
    assert "macro:ghost" in errors[0]


def test_override_cannot_set_a_derived_field():
    rows = [reg.blank_row("macro:alpha", "macro", "/alpha.html")]
    errors = reg.apply_overrides(rows, {"macro:alpha": {"builder": ["nope.py"]}},
                                 source_name="test.yml")
    assert len(errors) == 1
    assert "builder" in errors[0]
    assert rows[0]["builder"] == []


# ---------------------------------------------------------------------------
# whole-build behaviour
# ---------------------------------------------------------------------------

def _build(macro_repo: Path, tmp_path: Path) -> dict:
    doc, errors = reg.build_registry(
        repo_root=macro_repo,
        terminal_root=tmp_path / "absent-terminal",
        terminal_ref="origin/master",
        mastermind_root=tmp_path / "absent-mastermind",
        site_dir=None,
        as_of="2026-08-11T00:00:00Z",
        overrides_path=tmp_path / "no-overrides.yml",
        git=fake_git(),
    )
    assert errors == []
    return doc


def test_build_is_deterministic_under_a_pinned_as_of(macro_repo, tmp_path):
    first = json.dumps(_build(macro_repo, tmp_path), indent=2, sort_keys=False)
    second = json.dumps(_build(macro_repo, tmp_path), indent=2, sort_keys=False)
    assert first == second
    assert json.loads(first)["generated_at"] == "2026-08-11T00:00:00Z"


def test_build_sorts_rows_by_repo_then_route(macro_repo, tmp_path):
    pages = _build(macro_repo, tmp_path)["pages"]
    keys = [(row["repo"], row["route"], row["page_id"]) for row in pages]
    assert keys == sorted(keys)


def test_build_output_validates(macro_repo, tmp_path):
    assert reg.validate(_build(macro_repo, tmp_path)) == []


def test_validate_catches_a_missing_field_and_a_null(macro_repo, tmp_path):
    doc = _build(macro_repo, tmp_path)
    doc["pages"][0].pop("owner")
    doc["pages"][1]["nav_family"] = None
    problems = reg.validate(doc)
    assert any("missing fields" in p for p in problems)
    assert any("null" in p for p in problems)


def test_validate_catches_a_duplicate_page_id(macro_repo, tmp_path):
    doc = _build(macro_repo, tmp_path)
    doc["pages"].append(dict(doc["pages"][0]))
    assert any("duplicate page_id" in p for p in reg.validate(doc))


def test_annotation_starts_the_line(capsys):
    """GitHub drops any annotation that does not start the line (house law)."""
    reg.annotate("boom")
    out = capsys.readouterr().out.splitlines()
    assert out and out[0].startswith("::error title=page-registry::")
