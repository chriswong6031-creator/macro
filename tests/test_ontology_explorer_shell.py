"""tests/test_ontology_explorer_shell.py — F04-X1 public shell (RED first).

`site/ontology.html` and its paired assets are served publicly by Caddy. They are
the discoverable entry point, so they must be able to describe the product
without containing a single current owner reading — no inlined snapshot, no
bootstrapped JSON, no commented-out sample, no source map.

The failure this guards against is mundane and common: a builder that renders a
"realistic" example into the static shell so the page looks alive before the
fetch resolves. That example is a current premium value published to a public
host.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / "ontology.html.j2"
PAGE = ROOT / "site" / "ontology.html"
PAIRS = (("templates/ontology.css", "site/ontology.css"),
         ("templates/ontology.js", "site/ontology.js"))


def _built_page() -> str:
    if not PAGE.exists():
        pytest.fail("site/ontology.html has not been built by "
                    "scripts/build_ontology_explorer.py")
    return PAGE.read_text(encoding="utf-8")


def test_the_public_shell_is_built(tmp_path):
    assert _built_page().lstrip().lower().startswith("<!doctype html")


def test_the_paired_plain_copy_assets_match_byte_for_byte():
    """House law: a non-.j2 templates/<name> that also ships as site/<name> must
    be byte-identical in the same commit."""
    for template_rel, site_rel in PAIRS:
        template, site = ROOT / template_rel, ROOT / site_rel
        assert template.exists(), f"{template_rel} missing"
        assert site.exists(), f"{site_rel} missing"
        assert template.read_bytes() == site.read_bytes(), (
            f"{template_rel} and {site_rel} have drifted; "
            "run python -m scripts.check_template_site_sync --fix")


def test_the_public_shell_contains_no_current_owner_reading():
    """Every number the researcher sees must have arrived over the authenticated
    API. Nothing that looks like a receipt may be baked into the static file."""
    page = _built_page()
    forbidden = (
        "chain_state", "value_receipt", "base_rate", "p_confirm",
        "ontology_explorer_snapshot", "source_manifest_hash",
        "first_blocking_leg", "duration_derate", "breakeven_rise",
        "T10YIE", "CL=F", "QQQ", "SPY",
    )
    for token in forbidden:
        assert token not in page, f"public shell leaks {token!r}"


def test_the_public_shell_inlines_no_json_payload():
    page = _built_page()
    for match in re.finditer(r"<script[^>]*>(.*?)</script>", page, re.S | re.I):
        body = match.group(1).strip()
        if not body:
            continue
        try:
            parsed = json.loads(body)
        except (ValueError, TypeError):
            continue
        assert not isinstance(parsed, dict) or "schema" not in parsed, (
            "a snapshot-shaped JSON payload is inlined into the public shell")


def test_the_public_shell_ships_no_source_map():
    page = _built_page()
    assert "sourceMappingURL" not in page
    for _template_rel, site_rel in PAIRS:
        path = ROOT / site_rel
        if path.exists():
            assert "sourceMappingURL" not in path.read_text(encoding="utf-8")
    assert not list((ROOT / "site").glob("ontology*.map"))


def test_the_client_persists_no_snapshot_in_browser_storage():
    """`private, no-store` on the wire is undone the moment the client writes the
    body into localStorage, IndexedDB or the Cache API."""
    script = ROOT / "site" / "ontology.js"
    if not script.exists():
        pytest.fail("site/ontology.js has not been written")
    body = script.read_text(encoding="utf-8")
    for api in ("localStorage", "sessionStorage", "indexedDB",
                "caches.open", "CacheStorage"):
        assert api not in body, f"the client persists the snapshot via {api}"


def test_the_client_requests_the_frozen_route_with_no_store():
    body = (ROOT / "site" / "ontology.js").read_text(encoding="utf-8")
    assert "/api/ontology/explorer/v1" in body
    assert "no-store" in body


def test_no_current_snapshot_is_committed_under_tracked_premium_paths():
    for candidate in (ROOT / "site" / "premiumdata").glob("ontology*"):
        pytest.fail(f"a current snapshot is committed publicly at {candidate}")


def test_every_internal_link_this_feature_adds_resolves():
    """A dead internal link is not a cosmetic defect here.

    The site publish walks links, and one 404 has previously frozen the whole
    publish rather than degrading the single page that carried it. This feature
    adds links from both the shell and the client, so both are checked.
    """
    sources = [PAGE.read_text(encoding="utf-8") if PAGE.exists() else "",
               (ROOT / "site" / "ontology.js").read_text(encoding="utf-8")]
    hrefs = set()
    for text in sources:
        hrefs.update(re.findall(r'["\'](/[a-zA-Z0-9_./-]+\.html)(?:[?#][^"\']*)?["\']', text))
        hrefs.update(re.findall(r'href="(?!https?:|//|#|mailto:)([a-zA-Z0-9_./-]+\.html)',
                                text))
    missing = sorted(h for h in hrefs
                     if not (ROOT / "site" / h.lstrip("/")).exists())
    assert missing == [], f"dead internal link(s) added by this feature: {missing}"


def test_the_builder_exposes_an_entry_point_the_site_build_can_call(tmp_path):
    """Stage B's hunk in scripts/build_site.py must be one self-contained block.
    If the only entry point were `main()`, the site build would have to stand up
    a second Jinja environment with its own autoescape settings — one page
    rendered by two differently-configured environments is how escaping drifts
    between the nightly build and a manual one."""
    from jinja2 import Environment, FileSystemLoader
    from scripts.build_ontology_explorer import PAGE, PAIRED_ASSETS, build_shell

    env = Environment(
        loader=FileSystemLoader(str(ROOT / "templates")), autoescape=True)
    site = tmp_path / "site"
    build_shell(env, site)

    assert (site / PAGE).exists()
    for name in PAIRED_ASSETS:
        assert (site / name).read_bytes() == (
            ROOT / "templates" / name).read_bytes()


def test_a_missing_paired_asset_raises_instead_of_reporting_success(tmp_path,
                                                                    monkeypatch):
    """The site build wraps every page in an additive try/except, so a raise is
    what that pattern expects. Returning quietly would let a page ship without
    its stylesheet and still count as a successful build."""
    import scripts.build_ontology_explorer as builder
    from jinja2 import Environment, FileSystemLoader

    env = Environment(
        loader=FileSystemLoader(str(ROOT / "templates")), autoescape=True)
    monkeypatch.setattr(builder, "PAIRED_ASSETS", ("ontology.css", "not-a-real-asset.js"))
    with pytest.raises(FileNotFoundError, match="not-a-real-asset.js"):
        builder.build_shell(env, tmp_path / "site")


def test_the_client_uses_the_house_sign_in_return_convention():
    """A bare `/?signin=1` strands a reader who came for one specific trace: the
    house wall carries `&ret=<root-relative path>`, consumed by onboard.js's
    retTarget(), which accepts same-origin "/..." only. The bounce is this
    page's, so the return is this page's responsibility."""
    client = (ROOT / "templates" / "ontology.js").read_text(encoding="utf-8")
    assert "signin=1&ret=" in client
    assert "encodeURIComponent" in client
    # the guard retTarget() applies, mirrored on our side before we hand it over
    assert 'path.slice(0, 2) !== "//"' in client
    # and never the bare form, which is the regression this pins
    assert '"/?signin=1"' not in client
