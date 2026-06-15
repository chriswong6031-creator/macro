"""Quant Lab (advanced.html) render regression.

The "real fund moves" table on advanced.html.j2 was a STALE COPY of the main
dashboard's holdings panel: it read ``h.position`` / ``h.pct`` while the live
``holdings_rows()`` producer emits the conviction schema (ticker / name /
conviction_pp / active_chg_pct / ladder ...) with NO ``pct`` key at all. Jinja
renders a missing key as Undefined; ``h.position`` rendered blank silently, but
``h.pct > 0`` raised ``'dict object' has no attribute 'pct'`` — so the resilient
build logged "advanced page failed" and shipped a stale advanced.html.

These tests render the REAL template (same Jinja env as scripts/build_site) and
assert it survives the data shapes the producer actually emits — including rows
missing the optional fields — so the panel can never silently fall back again.
"""
from __future__ import annotations

import jinja2

from engine import i18n
from lib import config


def _env() -> jinja2.Environment:
    """Mirror scripts/build_site.main()'s template environment."""
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(config.ROOT / "templates"))
    env.filters["min"] = lambda seq: min(seq)
    env.globals.update(td=i18n.td, tr=i18n.tr, zip=zip)
    return env


def _context(holdings_changes: list[dict]) -> dict:
    """Minimal-but-complete context: every panel except the regime "dials" is
    None/empty-guarded in the template, so only ``latest`` needs real values."""
    return dict(
        latest={"date": "2026-06-14", "growth_score": 0.12, "inflation_score": -0.20,
                "growth_confidence": 0.71, "inflation_confidence": 0.63},
        generated_utc="2026-06-14 12:00",
        cross_asset=None, portfolio=None, ic_scorecard=None,
        components_confirming=[], components_contradicting=[],
        flip_plain="", internals=[], size_style=[], breadth_div=None,
        accumulation=[], holdings_changes=holdings_changes,
        holdings_threshold=0.15, flows_html=None,
    )


def _render(holdings_changes: list[dict]) -> str:
    return _env().get_template("advanced.html.j2").render(**_context(holdings_changes))


# A row exactly as engine/holdings_signals -> scripts.build_site.holdings_rows()
# emits it: the conviction schema, and crucially NO ``pct`` key.
_FULL_ROW = {
    "fund": "ARKK", "fund_name": "ARK Innovation", "ticker": "TSLA",
    "name": "Tesla", "sector": "Consumer Discretionary", "weight_pct": 4.2,
    "conviction_pp": 0.83, "active_chg_pct": 12.0, "direction": "accumulating",
    "is_active": True, "confirmed": True,
    "ladder": {"state": "early uptrend", "label": "Early uptrend"},
    "window": "2026-06-10..2026-06-13",
}


def test_real_holdings_schema_renders():
    """The production data shape (conviction schema, no ``pct``) must render — this
    is the exact input that crashed the stale ``h.pct`` template."""
    html = _render([_FULL_ROW])
    assert "advanced" not in html.lower() or True  # render succeeded (no raise)
    assert "ARKK" in html and "TSLA" in html
    assert "+0.83pp" in html          # conviction_pp formatted
    assert "Early uptrend" in html    # ladder state rendered


def test_holding_missing_optional_fields_does_not_raise():
    """Belt-and-suspenders: a row missing the optional conviction_pp / weight_pct /
    ladder degrades to "—" via the template's .get() guards instead of raising."""
    degenerate = {"fund": "XLK", "ticker": "NVDA", "name": "Nvidia",
                  "sector": "", "direction": "accumulating",
                  "window": "2026-06-10..2026-06-13"}
    html = _render([_FULL_ROW, degenerate])
    assert "NVDA" in html
    assert "—" in html                # degraded cells, not a crash


def test_legacy_stale_schema_row_does_not_raise():
    """Even a row in the OLD stale schema (position/pct, none of the new keys) must
    not raise — documents that the page survives the pre-reframe data shape."""
    legacy = {"fund": "XLF", "position": "JPM — JPMorgan", "pct": 1.4,
              "window": "2026-06-10..2026-06-13"}
    html = _render([legacy])          # must not raise
    assert "XLF" in html
