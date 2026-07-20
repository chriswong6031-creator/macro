"""Render smoke tests for templates/dashboard.html.j2 (macro.html + us_stocks.html).

Why this exists: the template is rendered ONLY by scripts/build_site.py's nightly
build — no test rendered it, so template-level Jinja errors (undefined filters,
missing-key crashes per the `{% if d.key is not none %}` gotcha) reached the
nightly uncaught.  Concrete incident: PR #1784's original commit shipped
`{{ _nbr | map('extract', _NBR_EN) }}` — 'extract' is not a Jinja2 filter — and
the full suite stayed green; the crash would have surfaced as a dead
us_stocks.html render.  This suite reproduces build_site.py's exact environment
and render calls against a small synthetic view-model so that class of bug fails
here first.

The environment mirrors scripts/build_site.py: FileSystemLoader on templates/,
filters['min'], and globals td / tr (engine.i18n) + zip.  The template is
rendered twice with the same vm — mode='macro' (macro.html) and mode='stocks'
(us_stocks.html) — exactly like the build.

The standout-board fixture row carries a `dossier` dict (action / why_now /
no_buy_reasons / stale_flags / authority_level) matching the Buy Decision Packet
producer shape (PR #1784, build_stock_library join) — a non-empty
`no_buy_reasons` list is what caught the 'extract' filter crash.  Do not trim
these keys.  NOTE (PR #3012, 2026-07-19): the dossier/details markup is now
gated `mode != 'stocks'` while the board itself is `mode != 'macro'`, so the
dossier renders in NEITHER mode — the fixture now proves intentional absence
(see test_stocks_mode_dossier_block_intentionally_absent) instead of reaching
the markup.
"""
from __future__ import annotations

from pathlib import Path

import jinja2

ROOT = Path(__file__).resolve().parent.parent


def _env() -> jinja2.Environment:
    """Mirror scripts/build_site.py's Jinja env exactly (loader, filters, globals)."""
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(str(ROOT / "templates")))
    env.filters["min"] = lambda seq: min(seq)
    from engine import i18n  # noqa: PLC0415 — same import site as build_site.py
    env.globals.update(td=i18n.td, tr=i18n.tr, zip=zip)
    return env


# --------------------------------------------------------------------------- #
# Fixture — synthetic view-model
# --------------------------------------------------------------------------- #

def _board_row(**overrides) -> dict:
    """One standout-board card (us_standouts.buy item), field census from the
    template's card body.  Keys are set explicitly (None where inert) because
    dict-attribute access on a MISSING key yields Undefined and `n.field > 0`
    style guards then raise — explicit None keeps the honest-degradation
    branches rendering instead of crashing."""
    row = {
        "ticker": "ACME",
        "name": "Acme Corp",
        "sector": "Information Technology",
        "lane": "bottoming",
        "signal": None,
        "signal_date": "2026-07-01",
        "conviction": None,
        "alpha": 0.42,
        "alpha_z": 0.42,
        "alpha_entry": None,
        "alpha_sector_rank": 3,
        "alpha_sector_n": 25,
        "sector_rank": 3,
        "sector_n": 25,
        "price": 42.5,
        "off_high": -18.0,
        "ext_z": 0.1,
        "demand": None,
        "sue_z": None,
        "insider_buyers": None,
        "insider_net_mn": None,
        "insider_bps": None,
        "news_burst": None,
        "gex_confirm": None,
        "confluence_plus": None,
        "altdata": None,
        "smartmoney_chip": None,
        "eq_grade": None,
        "eq_grade_zh": None,
        "eq_dir": None,
        "eq_badge": None,
        "stop_guidance": None,
        "spark_svg": None,
        "sector_capitulating": None,
        "hold": None,
        "dir": None,
        "days": None,
        "count": None,
        "age_short": None,
        "age_short_zh": None,
        "align_tier": None,
        "urgency": None,
        "risk_sizing": None,
        "label": None,
        "entry_signal": None,
        "above_trend": None,
        # Buy Decision Packet dossier (PR #1784 shape) — see module docstring.
        "dossier": {
            "action": {"verb": "WAIT", "verb_zh": "等待", "tone": "wait"},
            "why_now": "Weekly cross fresh; daily reset underway.",
            "no_buy_reasons": ["freshness_expired", "risk_veto"],
            "stale_flags": ["insider stale 45d"],
            "authority_level": {"tier": "T2 calibrated", "css": "trust-t2"},
        },
    }
    row.update(overrides)
    return row


def _base_vm() -> dict:
    """Every key scripts/build_site.py passes to dashboard.html.j2 (the vm dict
    ahead of the macro.html render), populated with the smallest synthetic
    values that exercise the standout board in both modes."""
    return dict(
        latest={
            "date": "2026-07-04",
            "quad": "Q2",
            "quad_name": "Reflation",
            "label": "Q2 — Reflation",
            "confidence": 0.72,
            "fed_stance": None,
            "dislocation": None,
            "turning_point": None,
            "risk_radar": None,
            "rate_inflation_transmission": None,
            "cross_asset_confirm": None,
            "transition_state": "stable",
            "liquidity_overlay": "neutral",
            "conditions": None,
            "risk_state": None,
            "cycle_tag": "mid",
        },
        mtf=None,
        macro_catalysts=[],
        event_strip=[],
        event_risk=None,
        prediction_markets=None,
        narrative_regime=None,
        ndi=None,
        macro_news=None,
        macro_brief=None,
        macro_news_disclaimer="",
        macro_news_disclaimer_zh="",
        alerts=[],
        pb=None,
        month_name="July",
        commodities=[],
        sector_timing={},
        action_board={"hold": [], "avoid": [], "notable": [], "buy": []},
        top_setups=[],
        us_standouts={
            # ACME exercises the lane-grouped path + full dossier;
            # ZEUS exercises the ungrouped (lane=None) path + dossier-absent fail-soft.
            "buy": [
                _board_row(),
                _board_row(ticker="ZEUS", name="Zeus Industries", lane=None, dossier=None),
            ],
            "eligible": 2,
        },
        us_board_outcomes=None,
        market_gamma=None,
        components_confirming=[],
        components_contradicting=[],
        flip_plain=None,
        internals=[],
        size_style=[],
        breadth_div=None,
        breadth_panel=None,
        adv_breadth=None,
        sector_setups=None,
        generated_utc="2026-07-04 06:00",
        chart_liquidity=None,
        chart_credit_breadth=None,
        market_tiles=[],
        vix=None,
        chart_vix=None,
        positioning=[],
        holdings_changes=[],
        holdings_threshold=5.0,
        accumulation=[],
        flows_html="",
        health=[],
        factor_leadership=None,
        nowcast_hist=None,
        stance=None,
        index_health=[],
        alloc_card=None,
        risk_model=None,
        chart_risk_model=None,
        chart_curve=None,
        chart_vix_term=None,
        cross_asset=None,
        fear_euphoria=None,
        regime_snap=None,
        market_state=None,
        signal_stack=None,
        vol_shock=None,
        froth_fragility=None,
        fear_greed=None,
        sector_heat=None,
        dispersion_regime=None,
        policy_lever=None,
    )


def _render(mode: str) -> str:
    """The exact build_site.py call shape: render(**vm, mode=...)."""
    return _env().get_template("dashboard.html.j2").render(**_base_vm(), mode=mode)


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #

def test_macro_mode_renders_without_exception():
    """macro.html render path — must not raise on the synthetic vm."""
    html = _render("macro")
    assert len(html) > 50_000  # full page, not a truncated shell


def test_stocks_mode_renders_without_exception():
    """us_stocks.html render path — must not raise on the synthetic vm."""
    html = _render("stocks")
    assert len(html) > 50_000


def test_stocks_mode_renders_standout_card_body():
    """The board-row loop body actually ran — this is where the template-crash
    class lives (per-card chips; the dossier/expander legs were removed from
    stocks mode by #3012).  An empty board would let a broken card body pass
    silently."""
    html = _render("stocks")
    assert "ACME" in html
    assert "ZEUS" in html  # ungrouped lane=None card renders too


def test_stocks_mode_dossier_block_intentionally_absent():
    """Supersedes test_stocks_mode_renders_dossier_block (the presence form)
    after PR #3012 — the removal its docstring warned about happened ON PURPOSE.

    Archaeology: the standout board renders only in stocks mode (the whole
    section sits under `mode != 'macro'`, ~L12886 — macro.html lost its Prophet
    cards to the macro-v2 grid).  PR #3012 (operator request 2026-07-19) then
    gated the Details dropdown + .nb-more panel — which contains the Buy
    Decision Packet dossier — behind `mode != 'stocks'`.  build_site.py renders
    only mode in {macro, stocks}, so the dossier markup is now unreachable in
    BOTH modes; #3012's "retained on macro.html" premise was wrong.

    This test pins the intentional absence: even a buy row carrying a FULL
    dossier (the ACME fixture — see test_fixture_row_carries_dossier_contract)
    must not emit the dossier or dropdown markup on stocks.  If the Buy
    Decision Packet is ever re-homed, flip these assertions back to presence
    so the 'extract'-filter crash class (#1784) is covered again."""
    html = _render("stocks")
    assert "ACME" in html  # board rendered — absence assertions are not vacuous
    assert "nb-dossier" not in html
    assert '<button class="nb-more-btn"' not in html  # dropdown toggle gone too


def test_fixture_row_carries_dossier_contract():
    """Pin the dossier fixture shape (Buy Decision Packet, PR #1784): a
    non-empty no_buy_reasons list is what exercised the reason-code mapping.
    Post-#3012 the markup no longer renders (see the absence test above), but
    the fixture stays full-shape: it keeps the producer contract documented and
    makes the absence assertion meaningful (dossier in, no dossier markup out)."""
    dossier = _base_vm()["us_standouts"]["buy"][0]["dossier"]
    for key in ("action", "no_buy_reasons", "stale_flags", "authority_level"):
        assert dossier.get(key), f"dossier fixture lost its {key!r} leg"
    assert isinstance(dossier["no_buy_reasons"], list) and dossier["no_buy_reasons"]


def test_both_modes_render_with_no_standouts():
    """us_standouts=None (older artifact / degraded build) must still render —
    the board falls back to the action_board.notable branch."""
    env = _env()
    vm = _base_vm()
    vm["us_standouts"] = None
    for mode in ("macro", "stocks"):
        html = env.get_template("dashboard.html.j2").render(**vm, mode=mode)
        assert len(html) > 50_000
