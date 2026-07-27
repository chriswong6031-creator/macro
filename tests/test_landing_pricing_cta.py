from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("rel", ("templates/index.html", "site/index.html"))
def test_billing_toggle_updates_paid_plan_cta_period(rel: str) -> None:
    html = (ROOT / rel).read_text(encoding="utf-8")
    start = html.index("function applyPricing()")
    end = html.index("tog.forEach", start)
    apply_pricing = html[start:end]

    assert "document.querySelectorAll('.js-plan-cta[data-period]')" in apply_pricing
    assert "el.dataset.period = period;" in apply_pricing
    assert "url.searchParams.set('period', period);" in apply_pricing
    assert "el.href = url.toString();" in apply_pricing
