from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_CSS = ROOT / "templates" / "product-nav-icons.css"
SITE_CSS = ROOT / "site" / "product-nav-icons.css"
NAV_TEMPLATE = ROOT / "templates" / "_navlinks.html.j2"


def _css() -> str:
    return TEMPLATE_CSS.read_text(encoding="utf-8")


def test_nav_icon_asset_pair_is_byte_identical():
    assert TEMPLATE_CSS.read_bytes() == SITE_CSS.read_bytes()


def test_every_navigation_icon_family_keeps_a_mask_definition():
    css = _css()
    markup = NAV_TEMPLATE.read_text(encoding="utf-8")

    for prefix, custom_property in (
        ("menu-icon", "--menu-icon-mask"),
        ("submenu-icon", "--submenu-icon-mask"),
        ("research-icon", "--research-icon-mask"),
    ):
        classes = set(re.findall(rf"\b({prefix}-[a-z0-9-]+)\b", markup))
        if prefix == "menu-icon":
            classes -= {
                # Custom-property name used by the one inline Crypto icon;
                # it is not a semantic class in the navigation markup.
                "menu-icon-mask",
                "menu-icon-flag",
                "menu-icon-us",
                "menu-icon-cn",
                "menu-icon-hk",
                "menu-icon-ca",
            }
        assert classes
        for class_name in classes:
            rule = rf"\.{re.escape(class_name)}\s*\{{[^}}]*{re.escape(custom_property)}\s*:"
            assert re.search(rule, css, re.S), f"{class_name} lost its semantic mask"


def test_flags_stay_small_while_destination_drawings_use_the_approved_scale():
    css = _css()

    flag_rule = re.search(r"\.nav-links \.menu-icon-flag,.*?\{(.*?)\}", css, re.S)
    submenu_rule = re.search(r"\.nav-dd-menu \.submenu-icon\{(.*?)\}", css, re.S)
    submenu_drawing_rule = re.search(r"\.nav-dd-menu \.submenu-icon::before\{(.*?)\}", css, re.S)
    mega_rule = re.search(r"\.nav-mega \.research-icon::before\{(.*?)\}", css, re.S)
    assert flag_rule and "width:19px" in flag_rule.group(1) and "height:13px" in flag_rule.group(1)
    assert submenu_rule and "width:48px" in submenu_rule.group(1) and "height:48px" in submenu_rule.group(1)
    assert submenu_drawing_rule and "width:44px" in submenu_drawing_rule.group(1)
    assert mega_rule and "width:44px" in mega_rule.group(1) and "height:44px" in mega_rule.group(1)


def test_drafting_accents_themes_and_reduced_motion_are_explicit():
    css = _css()

    assert "--nav-icon-grid:" in css
    assert "--nav-icon-accent:#5877e9" in css
    assert "--nav-icon-accent:#42a9b7" in css
    assert "--nav-icon-accent:#8671d8" in css
    assert 'html[data-theme="light"]' in css
    assert 'html[data-theme="dark"]' in css
    assert "@media (prefers-reduced-motion:reduce)" in css
    assert ".nav-dd-menu a:hover .submenu-icon" in css
    assert ".nav-mega a:hover .research-icon" in css


def test_icon_stylesheet_contains_no_emoji_glyphs():
    css = _css()
    assert not re.search(
        "[\U0001F1E6-\U0001F1FF\U0001F300-\U0001FAFF]",
        css,
    )
