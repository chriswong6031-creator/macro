"""Contracts for the compact macro.html "What To Do Now" glance."""

from pathlib import Path

import jinja2


ROOT = Path(__file__).resolve().parents[1]
DASH = ROOT / "templates" / "dashboard.html.j2"


def _glance_source() -> str:
    source = DASH.read_text(encoding="utf-8")
    start = source.index('{# Three-priority glance.')
    end = source.index("</div>{# /sx-evidence #}", start)
    return source[start:end]


def _render_glance(*, catalysts=True, policy_state="QUIET", risk_elevated=True) -> str:
    state = {
        "color": "yellow",
        "label_en": "Mixed",
        "label_zh": "混合",
        "score": 44,
        "radar": {
            "state": "ELEVATED" if risk_elevated else "QUIET",
            "do_en": "Avoid chasing extended leaders.",
            "do_zh": "避免追逐过度延伸的领涨股。",
        },
    }
    events = (
        [{"label": "FOMC rate decision", "label_zh": "FOMC 利率决议", "impact": "high"}]
        if catalysts
        else []
    )
    return jinja2.Environment().from_string(_glance_source()).render(
        market_state=state,
        MS=state,
        macro_catalysts=events,
        _weakest={"label_en": "Volatility", "label_zh": "波动率", "score": 48},
        PL={"state": policy_state},
        _mx5_risk_elevated=risk_elevated,
    )


def test_glance_is_capped_at_three_rendered_rows():
    """The face stays a decision glance instead of growing back into a report."""
    html = _render_glance()
    assert html.count('class="mx5-action-item') == 3
    assert "data-wtd-primary" in html
    assert "Trade small. Stay selective." in html
    assert "FOMC rate decision: expect noise; ignore the first move." in html
    assert "Avoid chasing extended leaders." in html


def test_active_policy_takes_the_third_priority_slot():
    html = _render_glance(policy_state="ARMED")
    assert html.count('class="mx5-action-item') == 3
    assert "Watch for repricing." in html
    assert "Avoid chasing extended leaders." not in html


def test_weakest_leg_replaces_event_when_calendar_is_empty():
    html = _render_glance(catalysts=False)
    assert html.count('class="mx5-action-item') == 3
    assert "Volatility (48/100)." in html
    assert "expect noise" not in html


def test_quiet_policy_copy_does_not_consume_a_glance_row():
    """Only active policy conditions deserve one of the three priority slots."""
    glance = _glance_source()
    assert "Policy is quiet" not in glance
    assert "No active jawboning" not in glance
    assert "PL.get('state') in ('ARMED','ELEVATED')" in glance


def test_primary_copy_is_short_and_live_patchable():
    glance = _glance_source()
    assert "Trade small. Stay selective." in glance
    assert "{{ MS.label_en }} &middot; {{ MS.score }}/100" in glance
