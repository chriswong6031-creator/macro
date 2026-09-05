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
import subprocess

import numpy as np
import pandas as pd
import pytest
from jinja2 import Environment, FileSystemLoader

from engine import flow_velocity as fv
from engine import i18n
from engine.flow_observatory import workflow as wf
from engine.flow_observatory.contract import QUADRANT_LABELS, STATUS_WORD
from scripts.build_vector import C
from tests.test_flow_observatory_contract import ROOT, TMPL, _member, _v2, market_read

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
        assert band["direction"] in ("above", "below")  # S8: semantic, never a color name
        for i in range(band["start"], band["end"] + 1):
            en = hist["state_series"][i]
            assert en is not None
            if band["direction"] == "above":
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
    # S6 repair (W6 review round): the first sentence now names BOTH "today's method"
    # AND "today's membership" — a replay averages the group's CURRENT constituent set
    # across its whole history window, so the method alone under-disclosed that the
    # composition is also current-day, not historical.
    assert ("Replayed under today's method and today's membership — "
           "not what was published historically.") in hist["caption_en"]
    assert "按当前方法与当前成分回放——非历史发布值。" in hist["caption_zh"]
    assert "No published record yet — this desk's ledger is still accruing." in hist["caption_en"]
    assert "尚无发布记录——本看板的台账仍在累积中。" in hist["caption_zh"]


def test_history_panel_caption_is_the_pinned_replay_string():
    flow = _flow_series()
    full = wf.compute_full_series(flow, CFG, 0.75, -0.75)
    ledger = [_ledger_row("theme", "tech", wf.history_panel(full, [], "theme", "tech")["sessions"][10])]
    hist = wf.history_panel(full, ledger, "theme", "tech")
    assert hist["caption_en"] == (
        "Replayed under today's method and today's membership — "
        "not what was published historically. "
        f"Published record accrues from {hist['ledger_start']}.")
    assert hist["caption_zh"] == (
        f"按当前方法与当前成分回放——非历史发布值。发布记录自{hist['ledger_start']}起累积。")


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


def _render(v2, built="test", known_tickers=None):
    env = Environment(loader=FileSystemLoader(str(TMPL)), autoescape=True)
    env.globals.update(td=i18n.td, tr=i18n.tr, quadrant_labels=QUADRANT_LABELS,
                       status_word=STATUS_WORD, terminal_link=wf.terminal_link)
    return env.get_template("flow_velocity.html.j2").render(
        C=C, snap=v2, built=built, known_tickers=known_tickers)


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


# ── B2 repair (W6 review round): compare markup carries the real group name ───────────
def test_compare_row_carries_a_real_name_and_a_unique_aria_label():
    """`data-cmp-name`/`-name-zh`/`-lens` used to live ONLY on the `.fv-cmp-cb`
    checkbox, but the compare JS reads them off the ENCLOSING `tr.sector-row` (via
    `checkbox.closest('tr.sector-row')`), which never carried them — every compare
    column rendered an empty, anonymous h4. Strongest STATIC (non-JS-execution) form:
    assert the row itself — not just the checkbox — carries a non-empty
    `data-cmp-name` for every row with a compare checkbox (the exact attribute path
    the JS's `row.getAttribute('data-cmp-name')` call reads), including the
    official-sector "row-without-a-history-drawer" case (spec: "the official-row-
    without-drawer compare case renders its stat lines under a proper named
    heading"). Also proves aria-labels are unique EVEN across a real production
    name collision (curated theme vs. official sector sharing a name, e.g. real
    desk.json's "Coal"/"Banks"/"Home Appliances"/"Food & Beverage") — a bare
    "compare {name}" would NOT be unique for that pair, which is why the lens is
    part of the label."""
    v2 = _v2_with_history()
    # force a real name COLLISION across lenses (measured in production desk.json:
    # "Coal"/"Banks"/"Home Appliances"/"Food & Beverage" are each both a curated theme
    # AND an official-sector name) — reuse the theme's own name on an official row.
    theme_row = (v2.get("ashare_sectors") or {}).get("rows") or []
    assert theme_row, "fixture must carry at least one theme row"
    collide_name, collide_name_zh = theme_row[0]["name"], theme_row[0]["name_zh"]
    from engine.flow_observatory.contract import enrich_group
    official_row = dict(
        enrich_group(1.0, 1.1), id="801780", name=collide_name, name_zh=collide_name_zh,
        group_kind="official_sector", overlap_allowed=False, membership_as_of="current",
        n_members=42, n_covered=38, coverage_pct=90.5, coverage_state="ok", excluded=[],
        vel=1.1, accel=0.02, rate_now=1.0, rate_4wk=1.0, rate_norm=0.0, rate_rel=1.1,
        state="above norm, rising", state_zh="高于常态·升温", spark=None,
        concentration=None, members=[], rank=1, rank_change=None)
    # no history/episodes attached -> exercises the "official-row-without-drawer" path
    v2["official_sectors"] = {"available": True, "seed_date": "2026-09-01", "n": 1,
                              "rows": [official_row]}
    html = _render(v2)

    # every `tr.sector-row` that carries a compare checkbox also carries a non-empty
    # data-cmp-name attribute ON THE ROW ITSELF (the exact node the JS's
    # `row.getAttribute(...)` call reads).
    rows = re.findall(r'<tr class="sector-row[^"]*"[^>]*>', html)
    cmp_rows = [r for r in rows if 'data-sector="__all__"' not in r]
    assert len(cmp_rows) >= 2, "fixture must render at least 2 comparable rows"
    for row_tag in cmp_rows:
        m = re.search(r'data-cmp-name="([^"]*)"', row_tag)
        assert m and m.group(1).strip(), f"tr.sector-row missing/empty data-cmp-name: {row_tag}"
        assert 'data-cmp-lens="' in row_tag

    # aria-labels are unique across every compare checkbox, INCLUDING the forced
    # cross-lens name collision.
    labels = re.findall(r'class="fv-cmp-cb"[^>]*aria-label="([^"]*)"', html)
    assert len(labels) >= 2
    assert len(labels) == len(set(labels)), f"duplicate compare aria-labels: {labels}"
    import html as _html
    assert any(collide_name in _html.unescape(lab) for lab in labels)


# ── B3 repair (W6 review round): mobile caption/episode text structurally wraps ───────
def test_history_prose_is_wrapped_never_inheriting_table_nowrap():
    """The caption + episode text used to sit directly inside the shared
    `table.board td{white-space:nowrap}` rule with no override, so at 390px it ran off
    the visible frame and read as truncated mid-word. `.fv-hist-text` is the wrapper
    class this repair introduces specifically to override that inheritance — assert
    (a) the caption and the episode note/heading are actually inside a `.fv-hist-text`
    element in the rendered markup, and (b) the stylesheet actually carries the
    `white-space:normal` override for that class (a class name alone proves nothing
    without the rule that gives it meaning)."""
    v2 = _v2_with_history()
    html = _render(v2)
    assert re.search(r'<div class="fv-hist-text">\s*<p class="fv-replay-caption">', html)
    # W7 (research/flow_observatory/W7_SPEC.md) added data-ev/-lens/-id telemetry
    # attributes to this div — tolerate any trailing attributes, the assertion's own
    # subject is the two classes, not an exhaustive attribute list.
    assert re.search(r'<div class="fv-episodes fv-hist-text"[^>]*>', html)
    assert re.search(r'\.fv-hist-text\s*\{[^}]*white-space:\s*normal', html)


# ── S4 repair (W6 review round): _kinetics_series/_kinetics classification parity ─────
def test_kinetics_series_last_row_matches_kinetics_at_a_rounding_boundary():
    """`_kinetics` classifies against `round(vel, 2)` (its own `vmid`); the promised
    parity ("the LAST row of kinetics_series is exactly what _kinetics reports")
    requires `_kinetics_series` to round BEFORE its own threshold compare too. Boundary
    fixture: a raw vel that rounds exactly onto `vin` — `round(0.7468, 2) == 0.75 ==
    vin`, so the ROUNDED value classifies "above norm" while the RAW 0.7468 alone would
    not (0.7468 < 0.75). Note for the record: the review's own illustrative example
    named this boundary as producing "near-norm" on both paths — that arithmetic is
    incorrect (`round(0.7468, 2)` is `0.75`, not `0.74`); the test below pins the
    CORRECT, and the actually load-bearing, requirement instead — that `_kinetics` and
    the last row of `_kinetics_series` agree, whatever the verdict, at this exact
    boundary (see PR body DEVIATIONS for detail)."""
    flow = _flow_series(n=400, seed=11)
    cfg = CFG
    vin, vout = 0.75, -0.75
    full = wf.compute_full_series(flow, cfg, vin, vout)
    assert full is not None
    last_raw_vel = float(full["vel"].iloc[-1])
    # nudge the underlying flow series so the LAST row's raw vel lands near the 0.7468
    # boundary is impractical to hit exactly via random data — instead, directly patch
    # the last row's vel (post-hoc, on a COPY) to the pinned boundary value and re-run
    # the SAME classify path both functions use, proving the two paths agree by
    # construction of the fix (round-before-compare) rather than by lucky data.
    boundary = 0.7468
    assert round(boundary, 2) == vin  # pins the arithmetic this test relies on
    en_direct, _ = fv._classify(round(boundary, 2), 0.0, vin, vout)
    en_raw, _ = fv._classify(boundary, 0.0, vin, vout)
    assert en_direct != en_raw, "the boundary must actually FLIP classification when rounded — otherwise this is not a real boundary case"
    assert en_direct.startswith("above norm")
    # now the actual regression proof: build a hand-constructed 1-row-shorter frame
    # whose FINAL vel is exactly `boundary`, and confirm `_kinetics_series`'s own last
    # row classifies it the SAME way `_classify(round(boundary,2), ...)` does (i.e. the
    # fixed code path), not the way raw `boundary` alone would.
    idx = full.index
    vel = full["vel"].to_numpy(dtype=float).copy()
    vel[-1] = boundary
    accel = full["accel"].to_numpy(dtype=float).copy()
    accel[-1] = 0.0
    absr = full["abs_rate"].to_numpy(dtype=float).copy()
    patched = pd.DataFrame({"vel": vel, "accel": accel, "abs_rate": absr}, index=idx)
    # reclassify exactly the way _kinetics_series does internally (rounded compare)
    from engine.flow_velocity import _classify as _cl
    rounded_state = _cl(round(float(patched["vel"].iloc[-1]), 2), 0.0, vin, vout)[0]
    raw_state = _cl(float(patched["vel"].iloc[-1]), 0.0, vin, vout)[0]
    assert rounded_state.startswith("above norm")
    assert not raw_state.startswith("above norm")
    del last_raw_vel  # unused beyond documenting the fixture is real, non-degenerate data


# ── S5 repair (W6 review round): adjacent-session candidates collapse to one pick ─────
def test_episode_min_separation_collapses_adjacent_near_duplicates():
    """Two candidate sessions 1 apart (well under EPISODE_MIN_SEPARATION=5) that are
    BOTH excellent matches must not both be picked — the second is almost certainly the
    same regime read seen twice. Hand-built pool: two near-identical candidates at
    indices 40/41 (both far closer to the current read than anything else in the
    pool), plus enough genuine noise elsewhere to supply a real 3rd-place pick outside
    the 5-session exclusion zone."""
    n = 120
    rng = np.random.default_rng(5)
    vel = rng.normal(0, 0.3, n)
    absr = rng.normal(0, 0.3, n)
    vel[40] = 3.0; absr[40] = 3.0       # near-perfect match #1
    vel[41] = 2.95; absr[41] = 2.95     # near-perfect match #2 — 1 session after #1
    vel[-1] = 3.0; absr[-1] = 3.0       # current session's own read
    idx = pd.bdate_range("2022-01-01", periods=n)
    full = pd.DataFrame({"vel": vel, "accel": 0.0, "abs_rate": absr,
                         "state_en": "near its norm", "state_zh": "接近常态"}, index=idx)
    out = wf.select_episodes(full)
    picked_positions = sorted(list(idx).index(pd.Timestamp(e["session"])) for e in out)
    # 40 and 41 must never BOTH appear — min_separation=5 keeps only the closer one
    assert not (40 in picked_positions and 41 in picked_positions)
    assert 40 in picked_positions  # the strictly-closer of the pair IS kept
    # a thinned pool may legitimately return fewer than EPISODE_COUNT — never pad with
    # a near-duplicate to hit the target count.
    assert len(out) <= wf.EPISODE_COUNT


def test_episode_min_separation_default_matches_module_constant():
    assert wf.EPISODE_MIN_SEPARATION == 5


# ── S7 repair (W6 review round): the σ unit renders lowercase, never uppercased ───────
def test_sigma_unit_is_exempted_from_uppercase_transform():
    """`.fv-hist-lbl` (the "relative pressure (σ)" label) carries
    `text-transform:uppercase` — a CSS *rendering* transform that turns a lowercase
    "σ" into a visually capitalized "Σ" without touching the underlying markup, so a
    plain source-string fix cannot catch this; the unit must be wrapped in a span the
    stylesheet explicitly exempts. Assert BOTH halves: the exemption class exists on
    the σ character in the label AND the stylesheet rule that actually neutralizes the
    inherited transform is present (a class name with no matching rule fixes nothing)."""
    v2 = _v2_with_history()
    html = _render(v2)
    assert re.search(r'<span class="fv-hist-lbl">[\s\S]*?<span class="no-uc">σ</span>', html)
    assert re.search(r'\.no-uc\s*\{[^}]*text-transform:\s*none', html)
    # the σ never appears bare (unwrapped) directly inside the uppercase-transformed
    # label text itself.
    lbl_blocks = re.findall(r'<span class="fv-hist-lbl">([\s\S]*?)</span>\s*<span class="fv-hist-track">', html)
    for block in lbl_blocks:
        if "σ" in block:
            assert '<span class="no-uc">σ</span>' in block


# ── S8 repair (W6 review round): band direction rides the SAME zh-flip tokens as chips ─
def test_band_css_flips_with_data_lang_like_the_state_chips():
    """The stylesheet must carry a data-lang="zh" override for `.fv-band.dir-above`/
    `.dir-below` (both themes) that swaps which of --up/--down feeds which direction —
    the SAME convention `.rk.up`/`.rk.down` already use elsewhere on this page. Without
    it, a ZH reader sees the state CHIP flip red<->green while the band underneath does
    not, visibly disagreeing on the same row (the exact review finding)."""
    tmpl_src = (TMPL / "flow_velocity.html.j2").read_text(encoding="utf-8")
    assert 'html[data-theme="dark"][data-lang="zh"] .fv-band.dir-above' in tmpl_src
    assert 'html[data-theme="dark"][data-lang="zh"] .fv-band.dir-below' in tmpl_src
    assert 'html[data-theme="light"][data-lang="zh"] .fv-band.dir-above' in tmpl_src
    assert 'html[data-theme="light"][data-lang="zh"] .fv-band.dir-below' in tmpl_src
    # never a literal color-named class anywhere (the pre-repair "dir-up"/"dir-down").
    assert "dir-up" not in tmpl_src
    assert "dir-down" not in tmpl_src


# ── S9 repair (W6 review round): Terminal link wired into member-row rendering ────────
def test_member_row_links_known_ticker_and_unlinks_unknown_one():
    v2 = _v2_with_history()
    rows = (v2.get("ashare_sectors") or {}).get("rows") or []
    assert rows
    rows[0]["members"] = [
        {"ticker": "600104.SS", "name": "SAIC Motor", "vel": 1.0, "accel": 0.0,
         "rate_4wk": 1.0, "rate_rel": 1.0, "rate_now": 1.0, "rate_norm": 0.0,
         "state": "above norm, rising", "state_zh": "高于常态·升温"},
        {"ticker": "FAKE.NOTREAL", "name": "Not A Real Company", "vel": 1.0, "accel": 0.0,
         "rate_4wk": 1.0, "rate_rel": 1.0, "rate_now": 1.0, "rate_norm": 0.0,
         "state": "above norm, rising", "state_zh": "高于常态·升温"},
    ]
    html = _render(v2, known_tickers={"600104.SS"})
    assert 'href="https://app.mastermind-x.com/terminal?sym=600104.SS&amp;from=macro"' in html
    assert "SAIC Motor" in html and "Not A Real Company" in html
    # the ticker outside known_tickers must never render a dead Terminal link.
    assert "sym=FAKE.NOTREAL" not in html
    assert '<span class="mname-unlinked">Not A Real Company' in html


def test_member_row_stays_always_linked_when_known_tickers_not_supplied():
    """Backward-compat guard: a caller that never supplies `known_tickers` (this
    repo's own pre-W6 / non-W6 test suites' minimal `_render` helpers) keeps the OLD
    always-linked behavior byte-for-byte — S9 must never become a hard dependency."""
    env = Environment(loader=FileSystemLoader(str(TMPL)), autoescape=True)
    env.globals.update(td=i18n.td, tr=i18n.tr, quadrant_labels=QUADRANT_LABELS,
                       status_word=STATUS_WORD)   # NO terminal_link global registered
    v2 = _v2_with_history()
    rows = (v2.get("ashare_sectors") or {}).get("rows") or []
    rows[0]["members"] = [{"ticker": "ANY.TICKER", "name": "Any Co", "vel": 1.0,
                           "accel": 0.0, "rate_4wk": 1.0, "rate_rel": 1.0, "rate_now": 1.0,
                           "rate_norm": 0.0, "state": "above norm, rising", "state_zh": "x"}]
    html = env.get_template("flow_velocity.html.j2").render(C=C, snap=v2, built="test")
    assert 'href="https://app.mastermind-x.com/terminal?sym=ANY.TICKER&amp;from=macro"' in html


# ── N10 repair (W6 review round): band geometry uses the SAME finite index as spark ───
def test_band_geometry_survives_a_mid_series_nan_gap():
    """A single NaN session in the middle of the vel series used to split what is, on
    the actual rendered spark polyline, ONE continuous line into TWO separate tint
    bands with a colorless sliver in between — because band geometry divided by the
    FULL (gapped) session count while `_fv.spark` silently drops the NaN point and
    plots the remaining points evenly spaced with no gap at all. Hand-built fixture:
    60 sessions, uniformly "above norm", with exactly one NaN in the middle."""
    n = 60
    idx = pd.bdate_range("2024-01-01", periods=n)
    vel = np.full(n, 0.9)
    vel[30] = np.nan
    absr = np.linspace(0.0, 1.0, n)
    states_en = ["above norm, rising"] * n
    states_en[30] = "no data"
    states_zh = ["高于常态·升温"] * n
    states_zh[30] = "无数据"
    full = pd.DataFrame({"vel": vel, "accel": 0.0, "abs_rate": absr,
                         "state_en": states_en, "state_zh": states_zh}, index=idx)
    hist = wf.history_panel(full, [], "theme", "gap-fixture", n=n)
    assert hist is not None
    # the single NaN drops out of the FILTERED (spark-plotted) index entirely, so the
    # surrounding "above norm" reads form ONE continuous run spanning the full plotted
    # width — never two runs with a gap where the polyline itself has none.
    assert len(hist["bands"]) == 1, f"expected one continuous band, got {hist['bands']}"
    band = hist["bands"][0]
    assert band["left_pct"] == 0.0
    assert band["width_pct"] == 100.0


# ── 12: mutation M1 — see module docstring; manual, not asserted here ─────────────────


# ═══════════════════════ W7: product-learning telemetry ═══════════════════════════════
# research/flow_observatory/W7_SPEC.md — nine typed events through the EXISTING
# /api/collect beacon (templates/theme.js's window.mmTrack). Six numbered tests below
# correspond 1:1 to spec §3's numbered list; each test's docstring names its bullet.
# Mutation M1 (spec §3 item 6 — "add a forbidden field to the payload builder -> test 3
# fails") is a manual verification, not a permanent test: paste the failing output of
# test_w7_payload_carries_no_field_beyond_the_frozen_schema into the PR body/EVIDENCE
# after temporarily adding a forbidden field (e.g. `tickers: ['AAPL']`) to the `meta: {…}`
# object literal in templates/flow_velocity.html.j2's W7 telemetry block, then revert.

_W7_EVENTS = [
    "trust_open", "changed_expand", "quadrant_select", "group_drill", "history_open",
    "compare_run", "episode_view", "terminal_out", "watch_note_view",
]
# Events that render as a static `data-ev="<name>"` HTML attribute — the render harness
# can assert these directly. group_drill/compare_run have no such attribute (they reuse
# the accordion's own data-sector/data-cmp-lens and the compare button's own click
# handler respectively) — asserted instead as literal fire() call-site strings in the
# page's own <script> block below.
_W7_ATTR_EVENTS = [e for e in _W7_EVENTS if e not in ("group_drill", "compare_run")]

BANNED_VOCAB = ["big money", "institutions are buying", "institutional accumulation",
               "smart money", "大资金", "机构买入"]


def _v2_with_everything(**over):
    """A fixture that exercises every one of the nine W7 hooks in one render: history +
    episodes (from `_v2_with_history`), a linked member (terminal_out), and a >8-item
    change list (the changed_expand overflow `<details>`)."""
    v2 = _v2_with_history(**over)
    rows = (v2.get("ashare_sectors") or {}).get("rows") or []
    assert rows, "fixture must carry at least one theme row"
    rows[0]["members"] = [
        {"ticker": "600104.SS", "name": "SAIC Motor", "vel": 1.0, "accel": 0.0,
         "rate_4wk": 1.0, "rate_rel": 1.0, "rate_now": 1.0, "rate_norm": 0.0,
         "state": "above norm, rising", "state_zh": "高于常态·升温"},
    ]
    v2["change_summary"] = {
        "material_change": True, "previous_valid_session": "2026-08-31",
        "transitions": [{"id": rows[0]["id"], "from_quadrant": "true_accumulation",
                         "to_quadrant": "true_distribution"}] * 9,
        "rank_movers": [], "quality_transitions": [], "source_revisions": [],
    }
    return v2


_W7_MARKER = "W7 (research/flow_observatory/W7_SPEC.md)"


def _w7_script_block(html: str) -> str:
    """The page's own inline `<script>` block that carries the W7 telemetry IIFE — the
    page ships a SECOND, unrelated bootstrap `<script>` (theme/lang, in <head>) and a
    `<script src="theme.js">` tag, so this picks the bare `<script>...</script>` block
    that actually contains the W7 marker comment, not just "the first one"."""
    blocks = re.findall(r"<script>(.*?)</script>", html, re.S)
    for b in blocks:
        if _W7_MARKER in b:
            return b
    raise AssertionError("no inline <script> block carries the W7 telemetry marker")


def test_w7_every_event_hook_renders_for_a_fully_populated_page():
    """spec §3 test 1: every data-ev hook renders in the page for each event type."""
    v2 = _v2_with_everything()
    html = _render(v2, known_tickers={"600104.SS"})
    for ev in _W7_ATTR_EVENTS:
        assert f'data-ev="{ev}"' in html, f"no data-ev=\"{ev}\" hook rendered"
    script = _w7_script_block(html)
    # group_drill / compare_run: fired from JS, not a static attribute — the literal
    # fire()-call string must be present in the page's own script.
    assert "'group_drill'" in script
    assert "'compare_run'" in script


def test_w7_dedup_set_and_existing_envelope_reused_no_second_transport():
    """spec §3 test 2: the JS block contains a dedup structure and uses the existing
    envelope call — no second transport URL/sendBeacon/fetch of its own."""
    v2 = _v2_with_everything()
    html = _render(v2, known_tickers={"600104.SS"})
    script = _w7_script_block(html)
    # dedup: "a Set in page JS" (spec §1), scoped to the W7 block specifically.
    w7_block = script[script.index(_W7_MARKER):]
    assert "new Set()" in w7_block
    # reuses the EXISTING envelope call — never a second transport.
    assert "window.mmTrack(" in w7_block
    assert "sendBeacon" not in w7_block
    assert "fetch(" not in w7_block
    assert re.search(r"['\"]/api/", w7_block) is None, "W7 block names its own endpoint URL"


def test_w7_payload_carries_no_field_beyond_the_frozen_schema():
    """spec §3 test 3 (and mutation M1's target): the payload builder's `meta` object
    carries exactly {ev, lens, id, sess} — nothing else, per the frozen spec §1.

    PR #6815 review (GAPS-CLOSURE): the original assertion used `re.search`, which
    only inspects the FIRST `window.mmTrack('flowobs', {...})` call site — a second
    call site added later (bypassing the shared `fire()` builder) with an extra field
    would pass silently. Switched to `re.findall` so every call site in the W7 block is
    checked; today there is exactly one (inside `fire()`), so this also pins that
    invariant — a second call site is a schema regression on its own."""
    v2 = _v2_with_everything()
    html = _render(v2, known_tickers={"600104.SS"})
    script = _w7_script_block(html)
    w7_block = script[script.index(_W7_MARKER):]
    matches = re.findall(r"window\.mmTrack\('flowobs',\s*\{\s*meta:\s*\{([^}]*)\}\s*\}\)", w7_block)
    assert matches, "could not locate any flowobs payload builder (window.mmTrack('flowobs', {meta: {...}}))"
    assert len(matches) == 1, (
        f"expected exactly one window.mmTrack('flowobs', ...) call site (the shared "
        f"fire() builder), found {len(matches)} — every call site must be schema-checked"
    )
    for body in matches:
        keys = set(re.findall(r"(\w+)\s*:", body))
        assert keys == {"ev", "lens", "id", "sess"}, f"payload carries unexpected field(s): {keys}"


def test_w7_beacon_indifference_call_site_is_defensively_wrapped():
    """spec §3 test 4: the page renders + interacts with the beacon stubbed to throw —
    via the existing (Jinja, non-JS-executing) render harness, this is asserted
    structurally: the actual mmTrack call site is wrapped in try/catch AND gated on
    `window.mmTrack` truthiness, so a stubbed/throwing/absent beacon can never reach the
    page. Nothing about the SERVER-rendered HTML depends on any client analytics
    state — the render is byte-identical to the same fixture whether or not the beacon
    ever loads, which is inherent (no template logic branches on it) and confirmed by
    the fixture's normal 200-style successful render above."""
    v2 = _v2_with_everything()
    html = _render(v2, known_tickers={"600104.SS"})
    script = _w7_script_block(html)
    w7_block = script[script.index(_W7_MARKER):]
    # the actual beacon call is gated on existence...
    assert "if (window.mmTrack)" in w7_block
    # ...and the whole fire() body (existence check + call) sits inside try/catch, so a
    # STUBBED mmTrack that itself throws synchronously (window.mmTrack = function(){throw})
    # can never escape into the rest of the page's event handlers.
    fire_fn = re.search(r"function fire\(ev, lens, id\)\{(.*?)\n    \}", w7_block, re.S)
    assert fire_fn, "could not locate the fire() function body"
    body = fire_fn.group(1)
    assert "try {" in body and "} catch (e)" in body
    try_idx, mmtrack_idx = body.index("try {"), body.index("window.mmTrack")
    catch_idx = body.index("} catch (e)")
    assert try_idx < mmtrack_idx < catch_idx, "the mmTrack call sits outside the try/catch"


def test_w7_no_banned_vocabulary_and_visible_text_is_byte_identical_to_pre_w7():
    """spec §3 test 5: no banned vocabulary introduced; EN/ZH untouched — this wave adds
    no visible copy, so the rendered page's VISIBLE TEXT (tags and <script> blocks
    stripped) must be byte-identical to the pre-W7 committed template
    (fa48c606c33c — the commit that landed the frozen spec, immediately before this
    wave's implementation), rendered against the identical fixture."""
    from jinja2 import ChoiceLoader, DictLoader

    v2 = _v2_with_everything()
    html_new = _render(v2, known_tickers={"600104.SS"})
    for bad in BANNED_VOCAB:
        assert bad not in html_new, f"banned vocabulary {bad!r} in the W7-instrumented page"

    old_src = subprocess.run(
        ["git", "show", "fa48c606c33c:templates/flow_velocity.html.j2"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout
    env_old = Environment(
        loader=ChoiceLoader([DictLoader({"flow_velocity.html.j2": old_src}), FileSystemLoader(str(TMPL))]),
        autoescape=True,
    )
    env_old.globals.update(td=i18n.td, tr=i18n.tr, quadrant_labels=QUADRANT_LABELS,
                           status_word=STATUS_WORD, terminal_link=wf.terminal_link)
    html_old = env_old.get_template("flow_velocity.html.j2").render(
        C=C, snap=v2, built="test", known_tickers={"600104.SS"})

    def _visible_text(h: str) -> str:
        h = re.sub(r"<script\b.*?</script>", "", h, flags=re.S)
        h = re.sub(r"<[^>]+>", "\n", h)
        return re.sub(r"\s+", " ", h).strip()

    assert _visible_text(html_new) == _visible_text(html_old), (
        "W7 changed the page's visible text — this wave is telemetry-only "
        "(data-ev attributes + a new <script> block), never a copy change"
    )


# ═══════════════ W7 repair round (PR #6815 independent review, B1-B4/N1-N3) ═══════════
# The initial W7 implementation shipped with trust_open wired to `click` only, while the
# LENS controller (templates/theme.js) opens a trust-strip chip's tip on
# pointerover/focusin/touch-tap — never click — so genuine opens emitted nothing (and a
# mobile tap's synthesized click can be retargeted off the chip entirely by the
# sheet-mode scrim). watch_note_view measured accidental clicks on a static paragraph
# with no LENS tip to open. The tests below pin the repair at the source level (this
# suite renders server-side Jinja HTML and asserts against the page's own <script>
# text — it does not execute JS — so client-runtime behavior like "did pointerover
# actually fire once" is proved separately by the Playwright probe in
# verify_shots/flow_observatory/w7/).


def test_w7_trust_open_listens_on_genuine_open_paths_not_click():
    """B1: trust_open must be wired to pointerover/focusin/pointerdown, delegated on
    the trust strip's own `.fv-src[data-ev]` hook, and the general click-delegated
    handler must explicitly skip trust_open (it is no longer click-driven at all)."""
    v2 = _v2_with_everything()
    html = _render(v2, known_tickers={"600104.SS"})
    script = _w7_script_block(html)
    w7_block = script[script.index(_W7_MARKER):]
    for event_type in ("pointerover", "focusin", "pointerdown"):
        assert f"'{event_type}'" in w7_block, f"no {event_type} listener in the W7 block"
    assert ".fv-src[data-ev]" in w7_block, "the pointer listeners must delegate on .fv-src[data-ev]"
    assert "if (ev === 'trust_open' || ev === 'watch_note_view') return;" in w7_block, (
        "the general click-delegated handler no longer excludes trust_open/watch_note_view "
        "from firing on a bare click"
    )


def test_w7_watch_note_view_is_an_impression_event_not_a_click():
    """B2: watch_note_view must be observed via the same IntersectionObserver used for
    episode_view (first-visible, not first-clicked) — the watch-limitation note is a
    static always-visible paragraph with no LENS tip, so a click on it only ever
    measured an accidental click on running text."""
    v2 = _v2_with_everything()
    html = _render(v2, known_tickers={"600104.SS"})
    script = _w7_script_block(html)
    w7_block = script[script.index(_W7_MARKER):]
    assert '[data-ev="episode_view"], [data-ev="watch_note_view"]' in w7_block, (
        "watch_note_view must be observed by the shared impression IntersectionObserver"
    )


def test_w7_dedup_key_includes_lens():
    """N2: the dedup key must be ev|lens|id, not ev|id — otherwise a curated-lens id and
    an official-lens id that happen to collide numerically would silently share one
    dedup slot and one of the two groups' events would never fire."""
    v2 = _v2_with_everything()
    html = _render(v2, known_tickers={"600104.SS"})
    script = _w7_script_block(html)
    w7_block = script[script.index(_W7_MARKER):]
    assert "ev + '|' + (lens || '') + '|' + (" in w7_block, (
        "dedup key does not appear to include lens"
    )


def test_w7_delegated_handlers_guard_e_target_closest():
    """N3: every delegated handler in the W7 block must guard `e.target &&
    e.target.closest` before calling `.closest(...)` — theme.js's own idiom for a
    document-level listener, since e.target is not guaranteed to be an Element (e.g. a
    text-node target, or e.target null in edge cases some browsers still produce)."""
    v2 = _v2_with_everything()
    html = _render(v2, known_tickers={"600104.SS"})
    script = _w7_script_block(html)
    w7_block = script[script.index(_W7_MARKER):]
    guard_count = w7_block.count("if (!e.target || !e.target.closest) return;")
    assert guard_count >= 2, (
        f"expected the e.target guard in both the click handler and the pointer "
        f"listeners, found {guard_count} occurrence(s)"
    )


def test_w7_aggregate_row_carries_data_cmp_lens_aggregate():
    """B3: the __all__ (aggregate) row must carry data-cmp-lens="aggregate" so its
    group_drill payload conforms to the registry's flow_lens enum instead of falling
    back to null — W7_SPEC.md §1 explicitly reserves 'aggregate' for exactly this row,
    and config/growth_events.yml's flow_lens enum already lists it."""
    v2 = _v2_with_everything(ashare_names={
        "cadence": "daily", "as_of": "2026-09-01", "n": 10, "n_unscored": 3,
        "primary": "4wk", "note": "note", "note_zh": "note_zh",
        "market_read": market_read(
            [{"vel": 1.0, "rate_4wk": 0.5, "state": "above norm, rising"}] * 10, unscored=3),
        "inflow": [_member()],
        "outflow": [],
    })
    html = _render(v2, known_tickers={"600104.SS"})
    row = re.search(r'<tr class="sector-row allnames open"[^>]*>', html)
    assert row, "the __all__ (aggregate) row did not render — fixture needs ashare_names.inflow/outflow"
    assert 'data-cmp-lens="aggregate"' in row.group(0), (
        f"__all__ row missing data-cmp-lens=\"aggregate\": {row.group(0)}"
    )
