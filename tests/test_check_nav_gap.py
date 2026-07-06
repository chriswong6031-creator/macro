from scripts.check_nav_gap import _split_selector_list, find_jammed


def test_split_selector_list_ignores_commas_inside_is():
    selectors = "body:is(.page-macro, .page-china, .page-canada) .rrx, .site-nav"

    assert _split_selector_list(selectors) == [
        "body:is(.page-macro, .page-china, .page-canada) .rrx",
        ".site-nav",
    ]


def test_nav_gap_does_not_treat_is_descendant_padding_as_body_padding(tmp_path):
    html = """<!doctype html>
<html>
<head>
<style>
body { margin: 0; padding: 18px; }
.site-nav { margin: 0 auto 16px; }
body:is(.page-macro, .page-china, .page-canada) .ms-front > .rrx .rrx-rec {
  padding: 7px 10px;
}
</style>
</head>
<body class="page-china">
<nav class="site-nav"><div class="nav-dd-menu"></div></nav>
<main class="ms-front"><section class="rrx"><div class="rrx-rec"></div></section></main>
</body>
</html>"""
    site_dir = tmp_path / "site"
    site_dir.mkdir()
    (site_dir / "china.html").write_text(html, encoding="utf-8")

    assert find_jammed(str(site_dir)) == []
