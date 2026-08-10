"""Executable guards for the inert TOP ANATOMY W1 surface design freeze."""
from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader, Undefined


ROOT = Path(__file__).resolve().parent.parent


def _template():
    env = Environment(
        loader=FileSystemLoader(ROOT / "templates"),
        autoescape=True,
        undefined=Undefined,
    )
    # Shared chrome calls these globals; the future builder contract wires the
    # production implementations, while this inert design test needs only parity.
    env.globals.update(td=lambda x, *a, **k: x, tr=lambda x, *a, **k: x)
    return env.get_template("winner_health.html.j2")


def _row(**overrides):
    row = {
        "ticker": "TEST", "name": "Test Corp", "r126": 0.62,
        "spark": [10.0, 11.0, 10.5], "episode_high": 12.0,
        "legs": [], "analog": None,
    }
    row.update(overrides)
    return row


@pytest.mark.parametrize("wh", [
    None,
    {"null_state": True},
    {"null_state": False, "states": {}},
    {"null_state": False, "universe_n": 100, "states": {
        "extended_healthy": [_row()], "extended_watch": [],
        "thinning": [], "breaking": []}},
    {"null_state": False, "states": {"extended_watch": [
        _row(spark=[10.0, 11.0], analog={"n": 4, "track": "W"})]}},
])
def test_design_freeze_renders_board_and_honest_null_fixtures(wh):
    html = _template().render(wh=wh) if wh is not None else _template().render()
    assert "Winner Health" in html
    assert "winner_health.v1" not in html  # schema mechanics stay out of Tier 1


def test_optional_row_number_renders_an_honest_dash_not_fake_zero():
    wh = {"null_state": False, "states": {"extended_healthy": [{"ticker": "NULL"}]}}
    html = _template().render(wh=wh)
    assert "NULL" in html
    assert '<span class="fig">—</span>' in html
    assert '<span class="fig">+0%</span>' not in html
