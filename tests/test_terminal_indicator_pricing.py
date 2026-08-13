"""Cross-surface guards for the Terminal indicator entitlement copy."""
from __future__ import annotations

from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader

from scripts.build_public_pages import plans_view_model
from scripts.build_site import _plans_view_model


ROOT = Path(__file__).resolve().parents[1]


def _access() -> dict:
    catalog = yaml.safe_load((ROOT / "config" / "plans.yml").read_text())
    return catalog["terminal_indicators"]


def test_both_plans_builders_receive_the_indicator_access_contract():
    expected = _access()
    assert plans_view_model()["terminal_indicators"] == expected
    assert _plans_view_model()["terminal_indicators"] == expected


def test_landing_and_onboarding_compare_show_each_tier_access():
    """The landing cards and the matrix must both quote the SAME ladder as plans.yml.

    The card bullets were cut to their nouns on 2026-07-31 (operator: "too much
    information") and the module count is now the only bolded thing in the list, so
    these pins carry the <b> — matching the shipping markup, not a paraphrase of it.

    2026-08-04 (operator: "1 / 31 Candle Painter 15 / 31 core trend + signals All 31 5
    complete suites … its confusing"): the matrix ROW stopped printing fractions and
    now prints ✗ / grey ✓ / green ✓. The ladder did not disappear — it moved into the
    row's tipbox, which is what the last block asserts. Pinning the tipbox is the
    load-bearing half: a checkmark row that quietly dropped the numbers would look
    identical to one that kept them, so the guard has to read the sentence.
    """
    access = _access()
    ladder = (
        f"Every plan includes {access['core_count']} core indicators. Free also includes "
        f"Candle Painter; Essential unlocks {access['access']['essential']} of "
        f"{access['advanced_total']} advanced modules; Pro unlocks all five suites and "
        f"all {access['access']['pro']} modules."
    )
    for rel in ("templates/index.html", "site/index.html"):
        page = (ROOT / rel).read_text()
        assert "Advanced indicator modules" in page
        assert f"Terminal charting — {access['core_count']} core indicators" in page
        assert f"<b>{access['access']['essential']} of {access['advanced_total']}</b> advanced modules" in page
        assert f"<b>All {access['access']['pro']}</b> advanced modules" in page
        # the row itself: no fractions, a grey tick for the partial tier
        assert '<td class="no">✗</td><td class="ok some">✓</td><td class="ok">✓</td>' in page
        assert f"{access['access']['free']} / {access['advanced_total']}" not in page
        assert f"{access['access']['essential']} / {access['advanced_total']}" not in page
        # the numbers still ship — in the tipbox, where a fraction explains
        assert ladder in page
        assert "Candle Painter" in page

    # The onboarding compare sheet mirrors the landing row, so it took the same edit:
    # 0 / "some" / 1 in place of the three fractions. test_onboard_compare_matrix.py
    # is what keeps the two label sets identical; this pin is about the CELLS.
    for rel in ("templates/onboard.js", "site/onboard.js"):
        compare = (ROOT / rel).read_text()
        assert (
            '{ l: ["Advanced indicator modules", "高级指标模块"], v: [0, "some", 1] }'
        ) in compare
        assert f'"{access["access"]["free"]} / {access["advanced_total"]}"' not in compare
        assert f'"{access["access"]["essential"]} / {access["advanced_total"]}"' not in compare
        # The value and its renderer have to stay together. compareCell()'s final
        # `else` treats a cell as an [en, zh] pair, so a "some" that lost its own
        # branch would not throw — it would quietly render v[1], the letter "o", in
        # the Essential column. Pin the branch AND its position ahead of the pair
        # fallback, plus the aria-label, since colour alone cannot say "partly".
        cell = compare.split("function compareCell(", 1)[1].split("\n  }", 1)[0]
        assert 'v === "some"' in cell
        assert cell.index('v === "some"') < cell.index("v[1]")
        assert '"partly included"' in cell
    for rel in ("templates/onboard.css", "site/onboard.css"):
        assert ".obm-cmp-cell svg.obm-cmp-part{stroke:var(--faint)}" in (ROOT / rel).read_text()


def test_rendered_plans_page_names_the_indicator_ladder():
    access = _access()
    vm = plans_view_model()
    page = Environment(
        loader=FileSystemLoader(ROOT / "templates"),
        autoescape=True,
    ).get_template("plans.html.j2").render(generated_utc="test", **vm)
    assert "Advanced indicator modules" in page
    assert f"{access['core_count']} " in page and "core indicators" in page
    # Same row, same treatment as the landing (2026-08-04): checkmarks in the cells,
    # the ladder in the tipbox. The two pages may not disagree about one row.
    assert '<td class="no">✗</td>' in page
    assert '<td class="ok some">✓</td>' in page
    assert (
        f"Essential unlocks {access['access']['essential']} of "
        f"{access['advanced_total']} advanced modules"
    ) in page
    assert f"{access['access']['free']} / {access['advanced_total']}" not in page


def test_market_terminal_showcase_uses_the_current_indicator_contract():
    access = _access()
    page = (ROOT / "site" / "products" / "market-terminal.html").read_text()

    assert "Five complementary systems.<br>One clearer technical workflow." in page
    assert f"complete {access['advanced_total']}-module library" in page
    assert "All five, complete · Available in Pro" in page
    assert "Essential unlocks a curated selection" in page
    assert "Structure Core" in page
    assert "Trend Waves" in page
    assert "Pulse Oscillator" in page
    assert "RSI Ultimate" in page
    assert "MACD Ultimate" in page
    assert "TP1–TP6" in page
    assert "complementary systems you can combine" in page
    assert "Essential + Pro modules · one example combination" in page
    assert 'data-aria-zh="选择工作流阶段"' in page
    assert "../plans.html#pricing-matrix" in page
    assert "mt-access-ladder" not in page
    assert f"{access['core_count']} core +" not in page
    assert "Seventeen built in" not in page
    assert "17 indicators in the picker" not in page
    assert "five coordinated systems" not in page.lower()
    assert "before the move is already mature" not in page
