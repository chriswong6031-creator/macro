"""GR1 — Basket Read surfaces (basket_detail READ band + the board's group-pulse column).

The page's own JS is executed under node rather than mirrored in Python: a Python
re-implementation of the stance matrix would pass while the shipped copy drifted (the
mirrored-guard-is-vacuous trap). Every assertion below runs the REGION that ships.

What is pinned:

  * the stance matrix is TOTAL over (participation x sign x state_change x arc) and never
    leaks a machine slug, an internal state name, an untranslated statistic, "igniting",
    "validated", or refutation vocabulary into either language;
  * every branch answers "so what do I do" — a stance token from the honest vocabulary is
    always present, and it is never a directional call, because participation carries no
    directional authority (DNR:KILL-PSS-SR3-PARTICIPATION);
  * the Tier-1 read sentence stays inside the DESIGN_DOCTRINE word budget;
  * the two group_earnings_pulse.v1 traps: `season.next` is a PREVIEW capped by the
    builder, so the upcoming count must come from `n_upcoming_14d`; and `n_no_data` can
    sit far above `n_beat + n_miss`, so it is shown rather than divided away;
  * every panel has a plain-word null state, and every artifact fetch is fail-silent —
    these three JSONs only exist after the first post-merge nightly;
  * the board's ordering is a disclosed RULE over named legs, never a composite score
    (R-TIL-3 / G0-2).
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DETAIL = ROOT / "templates" / "basket_detail.html.j2"
BOARD = ROOT / "templates" / "sector_central.html.j2"
DESK_JS = ROOT / "templates" / "baskets_desk.js"

needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node not on PATH")

# Every enum the two engines can emit, so the matrix is exercised over its real domain
# (engine/group_pulse.py: arc ladder + episode.state_change + direction.sign).
ARC_STATES = ["washout_in_progress", "washout_complete_awaiting_reclaim", "turning",
              "advancing", "distributing", "quiet", "insufficient_coverage"]
STATE_CHANGES = ["strengthening", "steady", "cooling", "quiet", None]
SIGNS = ["up", "down", "mixed", None]
SHARES = [None, 0.0, 0.12, 0.34, 0.62, 1.0]
COUNTS = [None, 0, 2, 5, 11]

# Scoped to THIS surface (banned-list-scoped-to-one-postmortem): machine slugs the two
# artifacts carry, the house-law words, and the refutation vocabulary the operator moved
# backstage (2026-07-27, #3821). Matched case-insensitively against rendered copy.
BANNED = [
    # artifact slugs / internal field names
    "washout_in_progress", "washout_complete_awaiting_reclaim", "insufficient_coverage",
    "reclaimed_20d_share", "washed_out_share", "activity_share", "agreement_pct",
    "state_change", "median_move_spy_adj", "drawdown_pctile", "capitulation_median_age",
    "null_disclosure", "oracle_p8", "oracle p8", "group_pulse", "coverage_warnings",
    "n_upcoming_14d", "n_no_data", "beat_basis", "net_up_share", "pos_share_5d",
    "context_only", "n_covered", "activity_basis", "trend_share",
    # house-law vocabulary
    "igniting", "ignition", "validated",
    # refutation vocabulary — never front-facing
    "falsifier", "falsify", "refuted", "refutation", "invalidated", "证伪", "被证伪",
    # untranslated statistics at glance tier
    "z-score", "p-value", "pctile", "%ile", "t-stat", "wilson",
]

STANCE_EN = {"Watch — don't chase", "Stand aside", "Nothing to do", "Not enough data"}
STANCE_ZH = {"观察，不要追", "先观望", "暂无操作", "数据不足"}


def _region(src: str, start: str, end: str) -> str:
    i = src.index(start)
    return src[i:src.index(end, i)]


def _read_js() -> str:
    """The whole shipped READ module. It depends only on the six page helpers stubbed by
    the harness, which is exactly why it is a self-contained region."""
    return _region(DETAIL.read_text(encoding="utf-8"),
                   "/* ── GR1:READ:BEGIN", "/* ── GR1:READ:END ── */")


HARNESS_PRELUDE = """
// The six page helpers the READ module borrows. L() keeps both languages so the test can
// see each one separately; esc/cls/fmtPct/cssv match the page's own semantics.
function L(en, zh){ return '<en>' + en + '</en><zh>' + (zh == null ? en : zh) + '</zh>'; }
function esc(s){ return (s == null ? '' : String(s)).replace(/[&<>"]/g, function(c){
  return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]; }); }
function cls(x){ return x == null ? 'muted' : (x >= 0 ? 'pos' : 'neg'); }
function fmtPct(x){ return x == null ? '\\u2014' : (x >= 0 ? '+' : '') + (x * 100).toFixed(1) + '%'; }
function cssv(n){ return 'var(' + n + ')'; }
var DETAIL = {stock_base: '../stock.html#'};
"""


def _run(body: str) -> object:
    script = HARNESS_PRELUDE + _read_js() + "\n" + textwrap.dedent(body)
    res = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=60)
    assert res.returncode == 0, f"node failed:\nSTDERR:\n{res.stderr}"
    assert res.stdout.strip(), f"no stdout; stderr:\n{res.stderr}"
    return json.loads(res.stdout)


def _langs(html: str) -> tuple[str, str]:
    """Split the harness's dual-language markup back into (english, chinese)."""
    en = " ".join(re.findall(r"<en>(.*?)</en>", html, re.S))
    zh = " ".join(re.findall(r"<zh>(.*?)</zh>", html, re.S))
    return _strip(en), _strip(zh)


def _strip(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s)).strip()


# ══════════════════════════════════════════════════════════════════════════════
# 1 — the stance matrix, over its whole domain
# ══════════════════════════════════════════════════════════════════════════════

@needs_node
def _matrix() -> list[dict]:
    return _run("""
        var ARCS = %s, CHGS = %s, SIGNS = %s, SHARES = %s, COUNTS = %s;
        var out = [];
        ARCS.forEach(function (arc) { CHGS.forEach(function (chg) {
          SIGNS.forEach(function (sign) { SHARES.forEach(function (sh) {
            COUNTS.forEach(function (n) {
              var p = {n_members: 14, n_covered: 12, as_of: '2026-08-07',
                participation: {activity_share: sh, activity_n: n,
                                trend_share_50d: 0.5, trend_share_200d: 0.4,
                                activity_basis: {ret_only: 1, ret_and_volume: 2}},
                direction: {sign: sign, agreement_pct: 0.42, median_move_spy_adj: 0.001,
                            leader: null, strongest: null, weakest: null},
                arc: {state: arc, washed_out_share: 0.6, washed_out_n: 7,
                      reclaimed_20d_share: 0.3, capitulation_median_age_d: 9,
                      drawdown_pctile_own_history: 0.8, null_disclosure: 'oracle_p8'},
                episode: {active_now: chg !== 'quiet', current_start: '2026-08-04',
                          sessions_active: 3, state_change: chg},
                coverage_warnings: []};
              var st = grStance(p), w = grWatchList(p);
              out.push({arc: arc, chg: chg, sign: sign, share: sh, n: n,
                        en: st.en, zh: st.zh, tokEn: st.tok.en, tokZh: st.tok.zh,
                        cls: st.tok.cls,
                        backdrop: grArcWords(arc).slice(0, 2),
                        up: w.up, down: w.down});
            }); }); }); }); });
        process.stdout.write(JSON.stringify(out));
    """ % (json.dumps(ARC_STATES), json.dumps(STATE_CHANGES), json.dumps(SIGNS),
           json.dumps(SHARES), json.dumps(COUNTS)))


@needs_node
def test_stance_matrix_is_total_and_bilingual():
    """Every combination the engines can emit produces a stance and a read, in both
    languages, and the two languages are genuinely different text (not EN echoed into ZH)."""
    rows = _matrix()
    assert len(rows) == len(ARC_STATES) * len(STATE_CHANGES) * len(SIGNS) * len(SHARES) * len(COUNTS)
    for r in rows:
        where = f"arc={r['arc']} chg={r['chg']} sign={r['sign']} share={r['share']} n={r['n']}"
        assert r["en"] and r["zh"], f"empty read at {where}"
        assert r["en"] != r["zh"], f"ZH is an English echo at {where}"
        assert r["tokEn"] in STANCE_EN, f"unknown stance {r['tokEn']!r} at {where}"
        assert r["tokZh"] in STANCE_ZH, f"unknown zh stance {r['tokZh']!r} at {where}"
        assert r["cls"] in {"act", "mut"}


@needs_node
def test_stance_matrix_never_leaks_a_slug_or_banned_word():
    """The glance tier is plain words in both languages — no machine slug, no house-law
    word, no refutation vocabulary, anywhere in the matrix or its watch conditions."""
    rows = _matrix()
    for r in rows:
        blobs = [r["en"], r["zh"], r["tokEn"], r["tokZh"], *r["backdrop"]]
        blobs += [x for pair in (r["up"] + r["down"]) for x in pair]
        for blob in blobs:
            low = blob.lower()
            for bad in BANNED:
                assert bad.lower() not in low, f"banned {bad!r} in {blob!r}"
            # a bare snake_case token is a slug leak whatever its spelling
            assert not re.search(r"\b[a-z]+_[a-z_]+\b", blob), f"slug-shaped token in {blob!r}"


@needs_node
def test_read_sentence_respects_the_tier1_word_budget():
    """DESIGN_DOCTRINE Law 4: the subtitle-tier line is a hard <=14 words. basket_detail is
    a Tier-3 page, but the top-of-page band is where the eye lands, so Tier 1 binds."""
    for r in _matrix():
        words = [w for w in re.split(r"\s+", r["en"]) if w not in {"—", "-", "·"}]
        assert len(words) <= 14, f"{len(words)} words: {r['en']!r}"


@needs_node
def test_participation_never_becomes_a_directional_call():
    """DNR:KILL-PSS-SR3-PARTICIPATION — participation ships as description. No branch may
    produce an act/buy/sell stance, however broad and one-way the group is."""
    forbidden = {"act", "buy", "sell", "get ready", "enter", "add", "accumulate", "trim",
                 "short", "买入", "卖出", "加仓", "减仓", "入场"}
    for r in _matrix():
        for tok in (r["tokEn"], r["tokZh"]):
            assert not any(f in tok.lower() for f in forbidden), f"directional stance {tok!r}"


@needs_node
def test_a_group_direction_needs_a_floor_of_movers():
    """Two names out of four is 50% and still not a group. Below the movers floor the read
    must not claim members are moving together, however clean the sign is."""
    rows = [r for r in _matrix()
            if r["n"] is not None and r["n"] < 3 and r["sign"] in ("up", "down")]
    assert rows, "fixture no longer exercises the floor"
    for r in rows:
        assert "together" not in r["en"].lower(), f"direction claimed on {r['n']} movers: {r['en']!r}"


@needs_node
def test_every_branch_watches_something_in_both_directions():
    for r in _matrix():
        assert 1 <= len(r["up"]) <= 3 and 1 <= len(r["down"]) <= 3
        for pair in r["up"] + r["down"]:
            assert len(pair) == 2 and pair[0] and pair[1] and pair[0] != pair[1]


# ══════════════════════════════════════════════════════════════════════════════
# 2 — the two group_earnings_pulse.v1 traps
# ══════════════════════════════════════════════════════════════════════════════

def _earnings(payload: dict) -> tuple[str, str]:
    html = _run("""
        GRE = %s;
        process.stdout.write(JSON.stringify(grEarningsSection('t') + grEarnTileBody(GRE.t)));
    """ % json.dumps({"t": payload}))
    return _langs(html)


def _season(**over) -> dict:
    base = {"season": {"n_members": 14, "n_reported": 2, "n_upcoming_14d": 11,
                       "next": [{"ticker": f"AA{i}", "date": f"2026-08-1{i}", "session": "amc"}
                                for i in range(6)]},
            "results": {"n_beat": 1, "n_miss": 1, "n_inline": 0, "n_no_data": 12,
                        "beat_basis": "eps_surprise vs consensus; floor n_reported>=4"},
            "guidance": {"band": None, "n_filers": 1, "basis": "x"},
            "revisions": {"net_up_share": 0.5, "n_covered": 10},
            "drift": {"pos_share_5d": None, "n": 2},
            "sympathy": {"ratio": None, "n_events": 6, "n_reporters": 3, "window_q": 8,
                         "basis": "x", "directional": {"beat_day_median": None,
                                                       "miss_day_median": None,
                                                       "n_beat_days": 0, "n_miss_days": 0}}}
    base.update(over)
    return base


@needs_node
def test_upcoming_count_comes_from_the_field_not_the_preview_length():
    """TRAP — `season.next` is capped at 6 by the builder (group_earnings.MAX_NEXT). Reading
    the count off `next.length` under-reports every busy basket by an unbounded amount."""
    en, zh = _earnings(_season())
    assert "11" in en and "11" in zh
    assert not re.search(r"\b6 members report", en), "count taken from the capped preview"
    # the cap itself is disclosed rather than silently truncating
    assert "next 6" in en
    # and a season inside the cap says nothing about a cap
    small = _season(season={"n_members": 14, "n_reported": 2, "n_upcoming_14d": 2,
                            "next": [{"ticker": "AA", "date": "2026-08-11", "session": "bmo"},
                                     {"ticker": "BB", "date": "2026-08-12", "session": "amc"}]})
    en2, _ = _earnings(small)
    assert "next 2" not in en2 and "Showing" not in en2


@needs_node
def test_no_data_members_are_counted_not_divided_away():
    """TRAP — n_beat + n_miss can sit far below n_members. The honest denominator is the
    whole roster, so the no-data count is shown and no beat RATE is computed over survivors
    (resolution-conditioned-denominator law)."""
    en, zh = _earnings(_season())
    assert "12" in en, "the no-data count is not on the surface"
    assert "12" in zh
    # 1 beat of 2 resolved would be a 50% beat rate — a survivor statistic. Never printed.
    assert "50%" not in en and "50%" not in zh
    assert re.search(r"no figure yet|No figure yet", en, re.I)
    # the refusal below the reporting floor is stated in plain words
    refused = _season(results={"n_beat": 0, "n_miss": 0, "n_inline": 0, "n_no_data": 14,
                               "beat_basis": "eps_surprise vs consensus; floor n_reported>=4"
                                             " not met — every member counted as no-data"})
    en3, zh3 = _earnings(refused)
    assert "Too few members have reported" in en3
    assert "已报成分股太少" in zh3


@needs_node
def test_refused_earnings_stats_print_their_n_in_plain_words():
    en, zh = _earnings(_season())
    assert "Guidance reads are thin" in en and "本季指引样本很薄" in zh
    assert "Too few reporters" in en          # drift refusal
    assert "Not enough report days" in en     # sympathy refusal
    for blob in (en, zh):
        for bad in BANNED:
            assert bad.lower() not in blob.lower(), f"banned {bad!r} in earnings copy"


@needs_node
def test_absent_artifacts_render_a_plain_word_null_state():
    """These three files only exist after the first post-merge nightly. Every panel must
    say so in plain words rather than break, blank, or print a machine reason."""
    out = _run("""
        GRP = null; GRE = null; GRH = null;
        var o = {band: grBand('x'), ep: grEpisodesSection('x'), earn: grEarningsSection('x'),
                 chips: grMemberChips('x', 'AAPL')};
        GRH = {x: []};
        GRP = {x: {as_of: '2026-08-07'}};
        o.epEmpty = grEpisodesSection('x');
        process.stdout.write(JSON.stringify(o));
    """)
    assert out["chips"] == ""
    for key in ("band", "ep", "earn", "epEmpty"):
        en, zh = _langs(out[key])
        assert en and zh and en != zh, f"{key} has no bilingual null copy"
        assert "undefined" not in out[key] and "NaN" not in out[key]
        for bad in BANNED:
            assert bad.lower() not in en.lower(), f"banned {bad!r} in {key} null state"
    assert "after the first nightly run" in _langs(out["band"])[0]
    # an EMPTY ledger says the log is empty; an ABSENT one says it has not run
    assert "No completed group episodes recorded yet" in _langs(out["epEmpty"])[0]
    assert "2026-08-07" in out["epEmpty"]


# ══════════════════════════════════════════════════════════════════════════════
# 3 — surface contracts that live in the template source
# ══════════════════════════════════════════════════════════════════════════════

def test_every_group_artifact_fetch_is_fail_silent():
    src = DETAIL.read_text(encoding="utf-8")
    for name in ("pulse.json", "earnings_pulse.json", "episodes.json"):
        assert f"'../basketdata/{name}'" in src, f"{name} is not fetched"
    block = _region(src, "['../basketdata/pulse.json'", "}\n")
    assert ".catch(" in block, "a missing artifact would reach the console"


def test_no_translated_text_lands_in_a_title_attribute():
    """The dual-span mechanism cannot operate inside an attribute (scripts/check_title_i18n).
    Every GR1 tooltip goes through data-tip-en / data-tip-zh instead."""
    js = _read_js()
    assert "data-tip-en" in js and "data-tip-zh" in js
    for m in re.finditer(r'title="([^"]*)"', js):
        assert not re.search(r"[一-鿿]", m.group(1)), f"CJK in title=: {m.group(1)!r}"


def test_the_arc_read_discloses_its_null_verbatim_in_both_languages():
    """G0-3 — the washout->turn construction printed NULL standalone. The disclosure is a
    Tier-2 receipt on the arc tile and the rail, in plain words, in both languages."""
    js = _read_js()
    assert "no standalone edge in our graded tests" in js
    assert "并未显现优势" in js
    assert js.count("GR_P8_EN") >= 3 and js.count("GR_P8_ZH") >= 3   # tile + rail + reuse


@needs_node
def test_the_capitulation_age_prints_sessions_not_days():
    """F-2 (audit 2026-08-10, MAJOR/correctness) — `capitulation_median_age_d` counts TRADING
    SESSIONS by contract (engine/group_pulse.py: "the unit is sessions, not calendar days").

    Rendered as "days" it understated the elapsed time on every page by ~40%: the live
    maximum, 90 sessions, is ~126 calendar days.  Pinned on the RENDERED copy in both
    languages, and pinned NEGATIVELY so the calendar-day wording cannot come back.
    """
    ages = [1, 9, 90]
    rows = _run("""
        var out = [];
        %s.forEach(function (age) {
          out.push(grArcRail({arc: {state: 'turning', capitulation_median_age_d: age}}));
        });
        process.stdout.write(JSON.stringify(out));
    """ % json.dumps(ages))
    for age, html in zip(ages, rows):
        en, zh = _langs(html)
        assert f"{age} trading session" in en, f"EN unit is not sessions at {age}: {en!r}"
        assert f"{age} 个交易日前" in zh, f"ZH unit is not sessions at {age}: {zh!r}"
        assert not re.search(r"\bdays?\b", en), f"calendar-day wording is back in EN: {en!r}"
        assert "天前" not in zh, f"calendar-day wording is back in ZH: {zh!r}"
    # and the unit agrees with itself on either side of the plural
    assert "1 trading session ago" in _langs(rows[0])[0]
    assert "9 trading sessions ago" in _langs(rows[1])[0]


def _uncommented(js: str) -> str:
    """Strip comments so the scan reads the CODE, not the reasoning about it — a rule that
    forbids a word must not be tripped by the comment explaining why it is forbidden."""
    js = re.sub(r"/\*.*?\*/", " ", js, flags=re.S)
    return re.sub(r"^\s*//.*$", " ", js, flags=re.M)


def test_the_read_band_carries_no_score_rank_or_heat():
    """G0-2 / R-TIL-3 — no fused number anywhere on these surfaces. The band may SAY it
    does not rank (the disclaimers below), so the check is on rendered copy, not prose."""
    js = _uncommented(_read_js())
    allowed = ("ranks", "sizes or gates", "不参与排序", "never ranks")
    for bad in (r"\bscore\b", r"\bheat\b", r"评分"):
        for m in re.finditer(bad, js, re.I):
            ctx = js[max(0, m.start() - 140):m.start() + 60]
            assert any(a in ctx for a in allowed), f"{bad} at {ctx!r}"
    # and no key that would carry one into the markup
    assert not re.search(r"\.(score|rank|heat)\b", js)


def test_board_orders_by_a_disclosed_rule_and_prints_it():
    """The board's alternative ordering is a rule over NAMED legs, printed on the surface it
    orders — never a weighting the reader cannot see (G0-2)."""
    src = BOARD.read_text(encoding="utf-8")
    assert "btbl-gr-rule" in src, "the ordering rule has no home on the page"
    assert "state change, then breadth of movement, then agreement" in src
    assert "no composite score" in src
    assert "参与度变化，其次是在动成分股的广度，再次是方向一致度" in src
    # the default sort is untouched: the reader opts in by clicking the column
    assert """btblSort = JSON.parse(localStorage.getItem('fw-btbl-sort')||'{"col":"20d","dir":-1}')""" in src
    # and the rule's legs are the artifact's own named fields, in that order
    rule = _region(src, "function grCmp(a,b){", "function renderGroupPulseCol")
    assert rule.index("state_change") < rule.index("activity_share") < rule.index("agreement_pct")


def test_board_column_and_desk_chips_survive_an_absent_artifact():
    board = BOARD.read_text(encoding="utf-8")
    assert ".catch(()=>{" in _region(board, "function renderGroupPulseCol", "\nfunction renderBTable")
    assert "const gp=!!GPULSE" in board, "the column is not gated on the artifact"
    desk = DESK_JS.read_text(encoding="utf-8")
    assert ".catch(function(){" in _region(desk, "function renderGroupPulse()", "\nfunction renderThemeDesk")
    # a board whose own basket ids are absent from the artifact must not re-render
    assert "grPulseCovers" in desk


def test_desk_reorder_resets_the_show_more_row_cap():
    """initShowMore caches its child list and marks the grid done; re-ordering without a
    reset leaves the cap hiding the OLD positions."""
    desk = DESK_JS.read_text(encoding="utf-8")
    fn = _region(desk, "function grResetShowMore()", "function grOrderBar")
    assert "sm-bar" in fn and "smInit" in fn
    render = _region(desk, "function renderThemeDesk(){", "function renderMacroCtx")
    assert render.index("grResetShowMore()") < render.index("innerHTML")
    assert "initShowMore" in render
