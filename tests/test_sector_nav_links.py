"""Sector pages render under site/sectors/ (one directory deep), so every site-nav
link MUST be ../-prefixed (or absolute) — a bare `href="macro.html"` resolves to
/sectors/macro.html and 404s on the live site. Regression guard for that bug."""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent
# a bare relative link: not ../, not root-absolute, not external/anchor/scheme
BARE = re.compile(r'href="(?!\.\./|/|https?:|#|mailto:|tel:|data:|javascript:)([^"]+)"')


def _nav(html: str) -> str:
    i = html.find('<nav class="site-nav">')
    if i < 0:
        return ""
    j = html.find("</nav>", i)
    return html[i:j] if j > 0 else ""


def test_sector_templates_have_no_bare_nav_links():
    bad = {}
    for name in ("sector", "canada_sector", "china_sector", "hk_sector"):
        p = ROOT / "templates" / f"{name}.html.j2"
        if not p.exists():
            continue
        hits = BARE.findall(_nav(p.read_text()))
        if hits:
            bad[name] = hits[:8]
    assert not bad, f"bare (un-prefixed) nav links in sector templates: {bad}"


def test_built_sector_pages_have_no_bare_nav_links():
    d = ROOT / "site" / "sectors"
    if not d.is_dir():
        import pytest
        pytest.skip("no built sector pages in this checkout")
    bad = {}
    for p in sorted(d.glob("*.html")):
        hits = BARE.findall(_nav(p.read_text(errors="ignore")))
        if hits:
            bad[p.name] = hits[:5]
    assert not bad, f"bare nav links in built sector pages (would 404 live): {bad}"


if __name__ == "__main__":
    for fn in [v for k, v in sorted(globals().items()) if k.startswith("test_")]:
        fn(); print("PASS", fn.__name__)
