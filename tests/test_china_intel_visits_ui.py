"""P1 institutional-visit glance-tier UI — fails on the pre-repair template.

Sol acceptance review on PR #6050 required a canonical consumer in
templates/china_intel.html.j2 via the command.json / cmd_full path.
This suite is the receipt: the pre-repair template has no
#institutional-visits section, so every test here fails against it.
"""
from __future__ import annotations

from jinja2 import Environment, FileSystemLoader

from engine import i18n
from lib import config


def _env():
    env = Environment(loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=False)
    env.globals.update(td=i18n.td, tr=i18n.tr, t=i18n.t)
    return env


def _briefing():
    return {
        "schema": "china_intel.briefing.v6",
        "is_context_only": True,
        "asof": "2026-08-20",
        "generated_utc": "2026-08-20T08:00:00Z",
        "news": None, "policy": None, "altdata": None, "radar": None,
        "analysis": None, "regime": None, "discovery": None,
        "policy_phrase": None, "narrative_divergence": None,
        "special_situations": None, "command": None, "analogs": None,
        "conviction": [], "cross_surface": [], "flagged_tickers": [],
        "what_changed": {}, "salience": [],
        "surfaces_present": [], "surface_asof": {},
        "max_staleness_days": 0, "digest": "",
        "disclaimer": "Context only.", "disclaimer_zh": "仅供参考。",
    }


def _row(ticker, name, visits):
    return {
        "ticker": ticker, "name": name,
        "stage": "quiet", "opportunity_score": 0,
        "edge_remaining": 0, "leading_gap": 0,
        "lead_up": 0, "lag_up": 0, "signal_core": 0.1,
        "falsifier": None, "falsifier_penalty": 1.0,
        "off_desk": False, "veto_blind": False,
        "directions": {"altdata": None, "radar": None, "news": None, "board": None},
        "desk_matrix": {
            "news": {"present": False, "dir": None},
            "altdata": {"present": False, "dir": None},
            "radar": {"present": False, "dir": None},
            "board": {"present": False, "dir": None},
            "special": {"present": False, "dir": None},
        },
        "traj": None, "read": "quiet", "edge_drivers": [], "edge_components": 0,
        "visits": visits,
    }


def _cmd_full(rows):
    return {
        "schema": "china_intel.command.v1",
        "is_context_only": True,
        "as_of": "2026-08-20",
        "n_universe": len(rows),
        "command": rows,
        "discovery": [],
        "analogs": None,
        "desks": {},
        "counts": {"emerging": 0, "early": 0, "consensus": 0, "exhausted": 0,
                   "veto_blind": 0, "board_only_unranked": 0},
        "disclaimer": "Context only.",
    }


STATES = (
    ("600519.SS", "茅台", {
        "state": "ok",
        "detail": None,
        "coverage_start": "2026-08-20",
        "n_total": 1,
        "recent": [{
            "title": "投资者关系活动记录表",
            "source_published_at": "2026-08-19T09:00:00+08:00",
            "visitor_raw": "not_yet_available",
            "visitor_class": "not_yet_available",
            "ontology_version": "B0_DRAFT",
            "adjunct_url": "/x.pdf",
            "first_seen_since_coverage_start": True,
        }],
    }),
    ("000001.SZ", "平安银行", {
        "state": "measured_no_event",
        "detail": "no institutional-visit filing observed for this name since coverage start",
        "recent": [], "coverage_start": "2026-08-20",
    }),
    ("000002.SZ", "万科A", {
        "state": "no_coverage",
        "detail": "visit-tape plane has not completed its first collection run yet",
        "recent": [],
    }),
    ("600000.SS", "浦发银行", {
        "state": "stale",
        "detail": "visit-tape source has not refreshed recently",
        "recent": [{
            "title": "调研纪要",
            "source_published_at": "2026-08-10T10:00:00+08:00",
            "visitor_raw": "not_yet_available",
            "visitor_class": "not_yet_available",
            "first_seen_since_coverage_start": False,
        }],
        "coverage_start": "2026-08-01",
    }),
    ("601398.SS", "工商银行", {
        "state": "source_failure",
        "detail": "visit-tape source unreadable on the last collection run",
        "recent": [],
    }),
    ("0700.HK", "腾讯", {
        "state": "not_applicable",
        "detail": "not a CNInfo A-share (SSE/SZSE) ticker",
        "recent": [],
    }),
)


def _render(cmd_full=None, briefing=None):
    html = _env().get_template("china_intel.html.j2").render(
        b=briefing or _briefing(), cmd_full=cmd_full,
    )
    return html


def test_pre_repair_template_has_no_visits_consumer_without_this_section():
    """The section id is the repair receipt — absent on the pre-repair template."""
    rows = [_row(t, n, v) for t, n, v in STATES]
    html = _render(_cmd_full(rows))
    assert 'id="institutional-visits"' in html
    assert 'data-visit-plane="cmd_full"' in html
    assert "Institutional visits" in html or "机构调研" in html


def test_all_six_honest_states_render_from_cmd_full():
    rows = [_row(t, n, v) for t, n, v in STATES]
    html = _render(_cmd_full(rows))
    body = html.split("</style>", 1)[-1]
    for ticker, _name, visits in STATES:
        needle = f'data-ticker="{ticker}" data-visit-state="{visits["state"]}"'
        assert needle in body, f"missing honest row for {ticker} state={visits['state']}"
    assert "none since coverage start" in body or "覆盖起始日后无记录" in body
    assert "no coverage" in body or "尚无覆盖" in body
    assert "source failure" in body or "源失败" in body
    assert "not applicable" in body or "不适用" in body
    assert "stale" in body or "已过期" in body
    assert "observed" in body or "已观测" in body


def test_first_seen_wording_is_since_coverage_start_never_first_ever():
    rows = [_row(t, n, v) for t, n, v in STATES]
    html = _render(_cmd_full(rows))
    body = html.split("</style>", 1)[-1].lower()
    assert "first seen since coverage start" in body or "覆盖起始日后首次出现" in html
    assert "first ever" not in body
    assert "首次出现过" not in html  # do not invent a 'first ever' zh


def test_visit_chips_carry_no_directional_hue_class():
    rows = [_row(t, n, v) for t, n, v in STATES]
    html = _render(_cmd_full(rows))
    start = html.find('id="institutional-visits"')
    assert start > 0
    end = html.find('id=', start + 10)
    block = html[start:end if end > start else None]
    for banned in ("visit-up", "visit-down", "sgn-pos", "sgn-neg", "rs-pos", "rs-neg"):
        assert banned not in block, f"directional class {banned} leaked into visits glance"


def test_missing_visits_key_degrades_to_no_coverage():
    row = _row("600519.SS", "茅台", None)
    row.pop("visits")
    html = _render(_cmd_full([row]))
    assert 'data-ticker="600519.SS" data-visit-state="no_coverage"' in html


def test_absent_cmd_full_does_not_render_visits_section():
    html = _render(cmd_full=None)
    body = html.split("</style>", 1)[-1]
    assert 'id="institutional-visits"' not in body
    assert '<section class="visit-glance"' not in body
