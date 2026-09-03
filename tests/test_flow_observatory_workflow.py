"""Flow Observatory V2 W6 — per-group history drawers, two-group compare, prior
episodes, Terminal deep links, and the watch-store integration decision
(research/flow_observatory/W6_SPEC.md).

Written FIRST and failing per the frozen spec's §0 gate, against
``engine.flow_observatory.workflow`` (new), the ``engine.flow_velocity.kinetics_series``
series helper it wraps, and the W6 extensions to ``templates/flow_velocity.html.j2`` /
``scripts/build_flow_velocity.py``. The twelve numbered tests below correspond 1:1 to
spec §5's numbered list; each test's docstring names its bullet. Tests 10/11 are
template-integration tests (render against a fixture v2 snap with `history`/`episodes`
already attached, the same shape ``scripts/build_flow_velocity.py`` wires on) and would
fail on the pre-W6 template even once the engine math is right — that gap is the point.

Mutation M1 (spec §5 item 12 — "strip the replay caption -> tests 1/4-adjacent caption
assertions fail") is a manual verification, not a permanent test: paste the failing
output of test_history_panel_caption_is_the_pinned_replay_string and
test_bootstrap_empty_ledger_has_no_ticks_and_accruing_caption into the PR body/EVIDENCE
after temporarily blanking ``REPLAY_CAPTION_LEAD_EN``/``_ZH`` in
``engine/flow_observatory/workflow.py``, then revert.
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd
import pytest
from jinja2 import Environment, FileSystemLoader

from engine import flow_velocity as fv
from engine import i18n
from engine.flow_observatory import workflow as wf
from engine.flow_observatory.contract import QUADRANT_LABELS, STATUS_WORD
from scripts.build_vector import C
from tests.test_flow_observatory_contract import ROOT, TMPL, _v2

CFG = fv._WK


# ── fixture flow series ──────────────────────────────────────────────────────────────
def _flow_series(n=500, seed=0, mean=0.05, jump_at=None, jump=3.0):
    idx = pd.bdate_range("2019-01-01", periods=n)
    rng = np.random.default_rng(seed)
    vals = rng.normal(mean, 1.0, n)
    if jump_at is not None:
        vals[jump_at:] += jump
    return pd.Series(vals, index=idx)


def _ledger_row(entity_kind, entity_id, session, *, revision_id=0,
               first_known_at="2020-01-01T00:00:00.000+00:00", vel=1.0, abs_value=1.0,
               quadrant="true_accumulation", state="x", rank=1, coverage_n=5, status="HEALTHY"):
    return {"entity_kind": entity_kind, "entity_id": entity_id, "effective_session": session,
           "revision_id": revision_id, "first_known_at": first_known_at, "revised_at": None,
           "vel": vel, "abs_value": abs_value, "quadrant": quadrant, "state": state,
           "rank": rank, "coverage_n": coverage_n, "status": status}


# ── 1: replay history uses source-effective sessions (no build timestamps) ────────────
def test_history_sessions_are_source_effective_not_build_timestamps():
    flow = _flow_series()
    full = wf.compute_full_series(flow, CFG, 0.75, -0.75)
    hist = wf.history_panel(full, [], "theme", "tech")
    assert hist is not None
    assert len(hist["sessions"]) == wf.HISTORY_SESSIONS
    for s in hist["sessions"]:
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", s)
    # the axis is EXACTLY the flow series' own trailing trading-day index — never a
    # "generated_at"/"built" wall-clock stamp mixed in.
    expected = [d.strftime("%Y-%m-%d") for d in full.tail(wf.HISTORY_SESSIONS).index]
    assert hist["sessions"] == expected
    assert hist["sessions"] == sorted(hist["sessions"])  # ascending, no build-time reorder


# ── 2: state bands match the replayed classifications at current thresholds ───────────
def test_state_bands_match_replayed_classification():
    flow = _flow_series(n=400, jump_at=350, jump=4.0)  # forces a clean "above norm" run
    full = wf.compute_full_series(flow, CFG, 0.5, -0.5)
    hist = wf.history_panel(full, [], "theme", "tech", n=60)
    assert hist is not None
    for band in hist["bands"]:
        for i in range(band["start"], band["end"] + 1):
            en = hist["state_series"][i]
            assert en is not None
            if band["direction"] == "up":
                assert en.startswith("above norm")
            else:
                assert en.startswith("below norm")
        assert 0.0 <= band["left_pct"] <= 100.0
        assert band["width_pct"] > 0
    # every index the bands DON'T cover is genuinely neutral/no-data
    covered = {i for b in hist["bands"] for i in range(b["start"], b["end"] + 1)}
    for i, en in enumerate(hist["state_series"]):
        if i not in covered:
            assert en is None or en in ("near its norm", "no data")


# ── 3: revision markers appear ONLY at ledger revision rows (fixture ledger) ──────────
def test_revision_markers_only_at_ledger_revision_rows():
    flow = _flow_series()
    full = wf.compute_full_series(flow, CFG, 0.75, -0.75)
    hist0 = wf.history_panel(full, [], "theme", "tech")
    target_session = hist0["sessions"][20]
    other_session = hist0["sessions"][30]
    ledger = [
        _ledger_row("theme", "tech", target_session, revision_id=0),
        _ledger_row("theme", "tech", target_session, revision_id=1, vel=1.5),
        _ledger_row("theme", "tech", other_session, revision_id=0),  # no revision
    ]
    hist = wf.history_panel(full, ledger, "theme", "tech")
    assert hist["revision_markers"] == [20]
    assert 30 not in hist["revision_markers"]
    assert len(hist["revision_marker_pct"]) == 1


# ── 4: published-record ticks only for ledger-covered sessions; bootstrap = no ticks ──
def test_published_ticks_only_for_ledger_covered_sessions():
    flow = _flow_series()
    full = wf.compute_full_series(flow, CFG, 0.75, -0.75)
    hist0 = wf.history_panel(full, [], "theme", "tech")
    covered_sessions = hist0["sessions"][40:]  # a trailing run really is published
    ledger = [_ledger_row("theme", "tech", s) for s in covered_sessions]
    hist = wf.history_panel(full, ledger, "theme", "tech")
    assert hist["published_idx"] == list(range(40, len(hist0["sessions"])))
    assert hist["ledger_start"] == covered_sessions[0]
    assert hist["published_segments"] and hist["published_segments"][0]["start"] == 40


def test_bootstrap_empty_ledger_has_no_ticks_and_accruing_caption():
    flow = _flow_series()
    full = wf.compute_full_series(flow, CFG, 0.75, -0.75)
    hist = wf.history_panel(full, [], "theme", "tech")
    assert hist["published_idx"] == []
    assert hist["published_segments"] == []
    assert hist["revision_markers"] == []
    assert hist["ledger_start"] is None
    # first sentence is the pinned, unconditional replay caption; the bootstrap gets an
    # honest accruing sentence rather than a broken "{ledger_start}" fill. Asserted
    # against LITERAL text (never the module constants themselves) — comparing a
    # caption against the very constant that built it is tautological and would keep
    # passing even if the constant were blanked out (mutation M1 must catch this).
    assert "Replayed under today's method — not what was published historically." in hist["caption_en"]
    assert "按当前方法回放——非历史发布值。" in hist["caption_zh"]
    assert "No published record yet — this desk's ledger is still accruing." in hist["caption_en"]
    assert "尚无发布记录——本看板的台账仍在累积中。" in hist["caption_zh"]


def test_history_panel_caption_is_the_pinned_replay_string():
    flow = _flow_series()
    full = wf.compute_full_series(flow, CFG, 0.75, -0.75)
    ledger = [_ledger_row("theme", "tech", wf.history_panel(full, [], "theme", "tech")["sessions"][10])]
    hist = wf.history_panel(full, ledger, "theme", "tech")
    assert hist["caption_en"] == (
        "Replayed under today's method — not what was published historically. "
        f"Published record accrues from {hist['ledger_start']}.")
    assert hist["caption_zh"] == (
        f"按当前方法回放——非历史发布值。发布记录自{hist['ledger_start']}起累积。")


# ── 5: compare refuses cross-lens pairs with the pinned reason ─────────────────────────
def test_compare_refuses_cross_lens_pairs():
    theme_row = {"name": "Autos", "name_zh": "汽车", "abs": {"value": 1.0}, "vel": 0.9,
                "quadrant": "true_accumulation", "coverage_pct": 100.0, "concentration": {}}
    sector_row = {"name": "Banks", "name_zh": "银行", "abs": {"value": 0.5}, "vel": 0.3,
                 "quadrant": "true_accumulation", "coverage_pct": 90.0, "concentration": {}}
    out = wf.compare_groups("theme", "cn_autos", theme_row, "sector", "801780", sector_row)
    assert out["available"] is False
    assert out["reason"] == "cross_lens"
    assert "denominator" in out["reason_en"] or "universe" in out["reason_en"]
    assert out["reason_zh"]

    same_lens = wf.compare_groups("theme", "cn_autos", theme_row, "theme", "cn_gold", theme_row)
    assert same_lens["available"] is True
    assert same_lens["a"]["kind"] == same_lens["b"]["kind"] == "theme"


# ── 6: episode selection excludes future-crossing windows + trailing 5 sessions ───────
def test_episode_selection_excludes_trailing_and_future_crossing():
    flow = _flow_series(n=300, seed=3)
    full = wf.compute_full_series(flow, CFG, 0.5, -0.5)
    n = len(full)
    current_idx = n - 1
    episodes = wf.select_episodes(full)
    for e in episodes:
        c = list(full.index).index(pd.Timestamp(e["session"]))
        # trailing-5 self-match exclusion
        assert c < current_idx - wf.EPISODE_TRAILING_EXCLUDE
        # no future leakage: candidate's own forward window must stay entirely BEFORE
        # the current session
        assert c + wf.EPISODE_FORWARD_WINDOW < current_idx

    # a hand-built pool where the ONLY near-identical match sits inside the excluded
    # zones proves the exclusion actually removes it rather than coincidentally never
    # matching it.
    vel = np.zeros(80)
    absr = np.zeros(80)
    vel[80 - 3] = 5.0   # a "perfect" match 3 sessions back — inside trailing-5
    absr[80 - 3] = 5.0
    vel[79] = 5.0        # current session's own read
    absr[79] = 5.0
    idx2 = pd.bdate_range("2021-01-01", periods=80)
    full2 = pd.DataFrame({"vel": vel, "accel": 0.0, "abs_rate": absr,
                          "state_en": "near its norm", "state_zh": "接近常态"}, index=idx2)
    out2 = wf.select_episodes(full2)
    sessions2 = {e["session"] for e in out2}
    assert idx2[80 - 3].strftime("%Y-%m-%d") not in sessions2


# ── 7: episode summaries are descriptive-vocabulary only ──────────────────────────────
def test_episode_summaries_have_no_returns_or_predictive_words():
    flow = _flow_series(n=300, seed=4)
    full = wf.compute_full_series(flow, CFG, 0.5, -0.5)
    episodes = wf.select_episodes(full)
    assert episodes, "fixture should produce at least one episode"
    for e in episodes:
        assert not wf.has_banned_predictive_language(e["outcome_en"])
        assert not wf.has_banned_predictive_language(e["outcome_zh"])
        assert e["outcome_zh"].startswith("此后10个交易日")
        assert e["outcome_en"].startswith("over the next 10 sessions")

    # the guard itself: catches an obviously-banned string
    assert wf.has_banned_predictive_language("expect a +5% return")
    assert wf.has_banned_predictive_language("预期将上涨")
    assert not wf.has_banned_predictive_language(wf.EPISODE_NOTE_EN)


# ── 8: Terminal links follow the existing contract; unknown ticker -> unlinked ────────
def test_terminal_link_follows_existing_contract_and_unknown_ticker_unlinked():
    assert wf.terminal_link("600104.SS") == "https://app.mastermind-x.com/terminal?sym=600104.SS&from=macro"
    assert wf.terminal_link(None) is None
    assert wf.terminal_link("") is None
    # a ticker outside our own known/covered universe renders unlinked (no dead link)
    assert wf.terminal_link("FAKE.NOTREAL", known_tickers={"600104.SS", "000001.SZ"}) is None
    assert wf.terminal_link("600104.SS", known_tickers={"600104.SS"}) is not None


# ── 9: watch-store integration — key namespace honored OR recorded-limitation taken ───
def test_watch_store_decision_is_the_recorded_limitation_path():
    """templates/watchstore.js / watchlist.js are both a single account/device-level
    list of REAL stock tickers wired to live price quotes and shared with the
    Watchlist product page (verified by reading both files — neither exposes a typed/
    namespaced key space; `symbolAdd`/`WL.add` accept an unvalidated string but writing
    a non-ticker "flowgroup:<lens>:<id>" key into that SAME list would corrupt the
    Watchlist page rather than extend the store). Spec §4's own fallback applies:
    "if it does NOT [allow arbitrary keys as a SAFE namespace], record the limitation
    and ship without watches rather than forking the store." This test pins THAT
    decision — not a watch-store integration test, since none was built.
    """
    assert wf.WATCH_AVAILABLE is False
    assert wf.WATCH_LIMITATION_REASON
    assert wf.WATCH_LIMITATION_EN and wf.WATCH_LIMITATION_ZH
    assert wf.ALERT_DEPENDENCY_NOTE
    # the template must actually surface the limitation (not silently drop the feature)
    # and must NEVER fork the store by writing a flowgroup: key into it.
    tmpl_src = (TMPL / "flow_velocity.html.j2").read_text(encoding="utf-8")
    assert "flowgroup:" not in tmpl_src
    assert "WatchStore." not in tmpl_src
    assert "WL.add(" not in tmpl_src
    assert "fv-watch-note" in tmpl_src  # the rendered limitation note's hook class


# ── 10/11: template integration — JS-off top-3 expanded, compare hidden, no chart lib ─
def _v2_with_history(**over):
    v2 = _v2(**over)
    rows = (v2.get("ashare_sectors") or {}).get("rows") or []
    flow = _flow_series(n=300, seed=7)
    full = wf.compute_full_series(flow, CFG, 0.75, -0.75)
    for i, r in enumerate(rows):
        r["entity_kind"] = "theme"
        hist = wf.history_panel(full, [], "theme", r["id"])
        r["history"] = hist
        r["episodes"] = wf.select_episodes(full)
    return v2


def _render(v2, built="test"):
    env = Environment(loader=FileSystemLoader(str(TMPL)), autoescape=True)
    env.globals.update(td=i18n.td, tr=i18n.tr, quadrant_labels=QUADRANT_LABELS,
                       status_word=STATUS_WORD)
    return env.get_template("flow_velocity.html.j2").render(C=C, snap=v2, built=built)


def test_js_off_top3_histories_expanded_compare_hidden_with_note():
    v2 = _v2_with_history()
    html = _render(v2)
    # every group with a history panel gets a real, server-rendered <details> — but
    # only the first 3 are forced OPEN (bounds initial page weight; JS-off users can
    # still click any other one open, <details> needs no JS to toggle).
    opens = re.findall(r'<details class="fv-disc fv-hist"[^>]*\bopen\b[^>]*>', html)
    all_hist = re.findall(r'<details class="fv-disc fv-hist"', html)
    assert len(all_hist) >= 2
    assert len(opens) == min(3, len(all_hist))
    # compare UI is JS-gated (hidden without the `.js` class the boot script adds) and
    # a <noscript> note names the JS dependency.
    assert 'fv-compare' in html
    assert "<noscript>" in html
    noscript_blocks = re.findall(r"<noscript>(.*?)</noscript>", html, re.S)
    assert any("compare" in b.lower() or "JavaScript" in b for b in noscript_blocks)


def test_no_new_chart_library_sparks_are_server_side_svg():
    v2 = _v2_with_history()
    html = _render(v2)
    low = html.lower()
    for banned in ("plotly", "chart.js", "d3.min.js", "d3.v", "highcharts", "apexcharts"):
        assert banned not in low
    # the history drawer's dual sparkline is the SAME server-side inline-SVG polyline
    # idiom the rest of the page already uses (engine.flow_velocity._spark) — never a
    # <canvas>-based chart element.
    assert "<canvas" not in low
    assert re.search(r"<svg class=\"spark", html)


# ── 12: mutation M1 — see module docstring; manual, not asserted here ─────────────────
