"""Render tests for the K2c Institutional Visits block in china_intel.html.j2
(P1, China Alpha Intelligence, PR #6050 — SOL acceptance-review repair).

Renders the REAL template through the SAME Jinja environment the production
builder uses (scripts/build_china_intel.py's `_env()` — imported, not
hand-rolled): same loader, same autoescape flag, same i18n globals. A
hand-rolled Environment could silently diverge (wrong autoescape, missing
`t`/`td`/`tr` globals) and pass while the real page fails, or the reverse.

Covers every state the block can actually render (masterplan §9.3 ten-state
taxonomy, the six reachable at this build stage): ok, measured_no_event,
no_coverage, stale, source_failure, not_applicable. Also asserts:
  - unresolved / not_yet_available visitor identity renders the honest unknown
    line, never disappears, never a bare zero
  - a resolved visitor identity DOES render its name (the "when actually
    resolved" branch)
  - "first seen since coverage start" wording appears; "first ever" never does
  - no directional hue class (rs-pos/rs-neg/stage-*) is emitted BY the visits
    block itself (those classes exist elsewhere in the page for unrelated
    desks — this suite scopes its negative assertion to the disc-card markup
    the visits block actually emits)
  - no translated text lands in a bare title= attribute (house CI i18n guard)

This suite is wired into the china_intel_hub owner lane in
.github/ci/legacy-jobs.yml (unrun-brain-desks) alongside test_china_intel_hub_visits.py.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.build_china_intel import _env  # noqa: E402 — the REAL builder env


def _b_fixture() -> dict:
    """Minimal-but-complete top-level briefing dict — every b.X the template
    dereferences bare (no guard) must be present; everything else may be None
    so its `if b.X` guard skips cleanly."""
    return {
        "asof": "2026-08-20",
        "schema": "china_intel.briefing.v6",
        "regime": None, "policy": None, "news": None,
        "max_staleness_days": None,
        "surfaces_present": [], "surface_asof": {},
        "policy_phrase": None, "narrative_divergence": None,
        "salience": None, "what_changed": None, "conviction": None,
        "analysis": None, "flagged_tickers": None,
        "special_situations": None, "analogs": None, "digest": None,
    }


def _cmd_row(ticker: str, name: str, visits: dict) -> dict:
    """A command-list dossier row shaped like engine.china_intel_hub._dossier()'s
    real output, carrying the given `visits` block."""
    return {
        "ticker": ticker, "name": name, "stage": "quiet",
        "opportunity_score": 10.0, "edge_remaining": 0.5,
        "desk_matrix": {}, "traj": None, "read": "context only",
        "read_zh": "仅供参考", "falsifier": None, "veto_blind": False,
        "visits": visits,
    }


_RESOLVED_ROW = {
    "title": "顺网科技：投资者关系活动记录表", "kind_en": "IR activity record",
    "kind_zh": "投资者关系活动记录表", "source_published_at": "2026-08-19T09:00:00+08:00",
    "visitor_raw": "某知名私募基金", "visitor_class": "class_1_concentrated",
    "ontology_version": "v1", "adjunct_url": "/x.pdf",
    "first_seen_since_coverage_start": False,
}
_UNRESOLVED_FIRST_ROW = {
    "title": "关于接待特定对象调研的公告", "kind_en": "site visit",
    "kind_zh": "特定对象调研", "source_published_at": "2026-08-05T09:00:00+08:00",
    "visitor_raw": "not_yet_available", "visitor_class": "not_yet_available",
    "ontology_version": "v1", "adjunct_url": "",
    "first_seen_since_coverage_start": True,
}


def _cmd_full_fixture() -> dict:
    return {
        "command": [
            _cmd_row("600519.SS", "贵州茅台",
                     {"state": "ok", "coverage_start": "2026-08-01",
                      "recent": [_RESOLVED_ROW, _UNRESOLVED_FIRST_ROW], "n_total": 2}),
            _cmd_row("000001.SZ", "平安银行",
                     {"state": "measured_no_event", "coverage_start": "2026-08-01",
                      "recent": []}),
            _cmd_row("300059.SZ", "东方财富",
                     {"state": "no_coverage", "recent": []}),
            _cmd_row("600030.SS", "中信证券",
                     {"state": "stale", "stale_days": 7, "coverage_start": "2026-08-01",
                      "recent": []}),
            _cmd_row("000002.SZ", "万科A",
                     {"state": "source_failure",
                      "detail": "filings store unreadable: bad magic bytes",
                      "recent": []}),
            _cmd_row("0700.HK", "腾讯控股",
                     {"state": "not_applicable", "recent": []}),
        ],
        "discovery": [],
        "visits_coverage_start": "2026-08-01",
    }


_UNSET = object()


def _render(cmd_full=_UNSET) -> str:
    tmpl = _env().get_template("china_intel.html.j2")
    resolved = _cmd_full_fixture() if cmd_full is _UNSET else cmd_full
    return tmpl.render(b=_b_fixture(), cmd_full=resolved)


# --------------------------------------------------------------------------- #
# render smoke
# --------------------------------------------------------------------------- #

def test_renders_without_exception():
    html = _render()
    assert len(html) > 2000


def test_renders_with_no_cmd_full():
    # cmd_full absent entirely (builder degrade path) must not raise, and the
    # section must not appear at all.
    html = _render(cmd_full=None)
    assert "Institutional visits" not in html


# --------------------------------------------------------------------------- #
# section presence + heading
# --------------------------------------------------------------------------- #

def test_section_heading_and_qualifier_present():
    html = _render()
    assert "Institutional visits" in html
    assert "机构调研" in html
    assert "Investor-relations visit filings" in html
    assert "coverage begins" in html
    assert "2026-08-01" in html


# --------------------------------------------------------------------------- #
# per-state copy — exact wording from the repair spec
# --------------------------------------------------------------------------- #

def test_ok_state_lists_recent_filings_with_type_and_date():
    html = _render()
    assert "2026-08-19" in html          # resolved row's filing date
    assert "IR activity record" in html
    assert "投资者关系活动记录表" in html
    assert "2026-08-05" in html          # unresolved-first row's filing date
    assert "site visit" in html
    assert "特定对象调研" in html


def test_resolved_visitor_identity_renders_its_name():
    html = _render()
    assert "某知名私募基金" in html


def test_unresolved_visitor_never_disappears_never_zero():
    html = _render()
    assert "Visitors not yet identified in the filing" in html
    assert "拜访机构暂未识别" in html


def test_first_seen_since_coverage_start_never_first_ever():
    html = _render()
    assert "first seen since coverage start" in html
    assert "覆盖开始以来首次出现" in html
    assert "first ever" not in html.lower()


def test_measured_no_event_copy():
    html = _render()
    assert "No investor-relations visit filings since coverage start" in html
    assert "自覆盖开始以来无投资者关系调研备案" in html


def test_no_coverage_copy():
    html = _render()
    assert "Visit records are not yet covered for this listing." in html
    assert "该股票的调研记录尚未纳入覆盖范围。" in html


def test_stale_copy_names_the_day_count():
    # "Visit records last refreshed" / "7" / "days ago — treat as out of
    # date." land in separate bilingual <span> pairs (the file's own t()
    # idiom — see test_no_translated_text_in_a_bare_title_attribute for why
    # each half is a distinct span rather than one interpolated string), so
    # this asserts the pieces individually rather than one contiguous regex.
    html = _render()
    assert "Visit records last refreshed" in html
    assert ">7<" in html or "> 7 " in html or " 7 " in html
    assert "days ago" in html
    assert "treat as out of date" in html
    assert "调研记录最近一次刷新于" in html
    assert "请视为过期数据" in html


def test_source_failure_copy_never_leaks_internal_detail():
    html = _render()
    assert "Visit-record source unavailable" in html
    assert "absence means nothing today" in html
    assert "调研记录来源当前不可用" in html
    # the internal diagnostic string must NEVER surface on a user-facing page
    assert "bad magic bytes" not in html
    assert "filings store unreadable" not in html


def test_not_applicable_copy():
    html = _render()
    assert "Visit-record disclosures do not apply to this listing." in html
    assert "调研披露规则不适用于该股票。" in html


# --------------------------------------------------------------------------- #
# house laws
# --------------------------------------------------------------------------- #

def test_no_directional_hue_class_in_visit_cards():
    """No score/rank/directional coloring is keyed to visits — the visit
    cards must never emit the page's directional-hue classes (those exist
    elsewhere on the page for unrelated desks; this asserts none of them
    appear as part of the .disc-card markup this block emits)."""
    html = _render()
    section = html.split("Institutional visits", 1)[1]
    section = section.split("<h2", 1)[0]   # up to the next section heading
    for banned in ("rs-pos", "rs-neg", "stage-emerging", "stage-exhausted",
                   "cmd-dot up", "cmd-dot down"):
        assert banned not in section, f"directional class {banned!r} leaked into visits block"


def test_no_score_or_rank_vocabulary_in_visit_cards():
    html = _render()
    section = html.split("Institutional visits", 1)[1]
    section = section.split("<h2", 1)[0]
    for banned in ("bullish", "bearish", "opportunity_score", "score:", "rank:"):
        assert banned.lower() not in section.lower()


def test_no_translated_text_in_a_bare_title_attribute():
    """CI-guarded house law: translated text may never sit in a title= attr."""
    html = _render()
    section = html.split("Institutional visits", 1)[1]
    section = section.split("<h2", 1)[0]
    for m in re.finditer(r'title="([^"]*)"', section):
        val = m.group(1)
        assert not re.search(r"[一-鿿]", val), (
            f"Chinese text found inside a bare title= attribute: {val!r}")
