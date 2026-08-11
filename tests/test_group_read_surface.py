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


def _rail_note(html: str) -> tuple[str, str]:
    """The sentence under the arc rail — not the stop labels and not the hover."""
    m = re.search(r'<div class="gpr-arc-note">.*?<span>(.*?)</span>', html, re.S)
    assert m, f"the rail has no note: {html[:300]!r}"
    return _langs(m.group(1))


@needs_node
def test_the_arc_rail_refuses_the_capitulation_age_under_the_coverage_floor():
    """Belt and braces over the engine-side null. `capitulation_median_age_d` is a
    MEDIAN over a cross-section the state has declined to read, and the rail was
    printing it — "the typical member's low was about 90 trading sessions ago" — beside
    a tile that refuses. The engine nulls it, but only when the artifact is REBUILT, so
    the first fixture below is the exact shape sitting in site/basketdata/pulse.json
    right now: a refused state carrying a live age.

    Gating on the STATE also holds against any future artifact that publishes a value
    under a refusal — the page never has to trust the producer for this."""
    out = _run("""
        var o = {};
        o.stale = grArcRail({arc: {state: 'insufficient_coverage',
                                   capitulation_median_age_d: 90}});
        o.fresh = grArcRail({arc: {state: 'insufficient_coverage',
                                   capitulation_median_age_d: null}});
        o.real  = grArcRail({arc: {state: 'turning', capitulation_median_age_d: 8}});
        process.stdout.write(JSON.stringify(o));
    """)
    for key in ("stale", "fresh"):
        en, zh = _rail_note(out[key])
        assert not re.search(r"\d", en), f"{key}: a figure survived the refusal: {en!r}"
        assert not re.search(r"\d", zh), f"{key}: a figure survived the refusal: {zh!r}"
        assert "trading session" not in en and "交易日" not in zh, (key, en, zh)
        assert en == "Context, not a signal." and zh == "仅为背景，不是信号。", (key, en, zh)
        for blob in (en, zh):
            assert "undefined" not in blob and "NaN" not in blob and "null" not in blob
    # above the floor the age is still the whole point of the note
    en, zh = _rail_note(out["real"])
    assert "8 trading sessions ago" in en, en
    assert "8 个交易日前" in zh, zh


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


# ══════════════════════════════════════════════════════════════════════════════
# 2b — the tiles divide by the denominator the engine divided by (G0-10 / F-4)
# ══════════════════════════════════════════════════════════════════════════════

def _pulse(**over) -> dict:
    """A pulse object carrying the FULL key set, including the denominators the
    coverage-floor pass added. `_legacy_pulse` below is the same object as emitted
    before them — both shapes reach the page during the transition."""
    p = {"n_members": 16, "n_covered": 14, "as_of": "2026-08-11",
         "participation": {"activity_share": 0.5, "activity_n": 7,
                           "trend_share_50d": 0.6, "trend_n_50d": 11,
                           "trend_share_200d": 0.5, "trend_n_200d": 10,
                           "activity_basis": {"ret_only": 2, "ret_and_volume": 5}},
         "direction": {"agreement_pct": 0.42, "n_active": 7, "sign": "up",
                       "median_move_spy_adj": 0.012, "cohesion": 0.3,
                       "leader": None, "strongest": None, "weakest": None},
         "arc": {"state": "turning", "washed_out_share": 0.8182, "washed_out_n": 9,
                 "washout_readable_n": 11, "reclaimed_20d_share": 1.0,
                 "reclaimed_readable_n": 3, "capitulation_median_age_d": 8,
                 "stage2_share": 0.5, "stage4_share": 0.1, "staged_n": 12,
                 "drawdown_pctile_own_history": 0.94, "null_disclosure": "oracle_p8"},
         "episode": {"active_now": True, "current_start": "2026-08-04",
                     "sessions_active": 3, "state_change": "steady"},
         "coverage_warnings": []}
    for block, vals in over.items():
        p[block] = {**p[block], **vals} if isinstance(p.get(block), dict) else vals
    return p


#: The keys the artifact did not carry before this pass — a page that has fetched
#: last night's pulse.json sees exactly this shape.
_NEW_KEYS = ("trend_n_50d", "trend_n_200d", "n_active",
             "washout_readable_n", "reclaimed_readable_n", "staged_n")


def _legacy_pulse(**over) -> dict:
    p = _pulse(**over)
    for block in ("participation", "direction", "arc"):
        p[block] = {k: v for k, v in p[block].items() if k not in _NEW_KEYS}
    return p


def _tiles(p: dict) -> list[str]:
    """The four rendered tiles, in order: participation, direction, arc, earnings."""
    html = _run("""
        process.stdout.write(JSON.stringify(grTiles(%s, null)));
    """ % json.dumps(p))
    parts = str(html).split('<div class="gpr-tile">')
    assert len(parts) == 5, f"expected 4 tiles, got {len(parts) - 1}"
    return parts[1:]


def _detail(tile: str) -> tuple[str, str]:
    """The tile's small-print line — the `d` div, not the hover and not the headline."""
    m = re.search(r'<div class="d">(.*?)</div>', tile, re.S)
    assert m, f"tile has no detail line: {tile[:200]!r}"
    return _langs(m.group(1))


@needs_node
def test_the_washout_line_divides_by_the_members_it_was_computed_over():
    """F-4 (audit 2026-08-10) — the state was decided on 9 of the 11 members with a
    readable washout (0.82) while the tile printed "9 of 14", the covered count, which
    reads 0.64. The tile and the arc word disagreed on every basket holding a member
    too young for the 308-session read."""
    en, zh = _detail(_tiles(_pulse())[2])
    assert "9 of 11" in en, en
    assert "of 14" not in en, f"the covered count is back as the denominator: {en!r}"
    assert "11" in zh and "9" in zh, zh
    assert "14" not in zh, f"ZH still divides by the covered count: {zh!r}"
    assert "enough history" in en, "the denominator is printed without saying what it is"


@needs_node
def test_the_reclaimed_count_uses_its_own_denominator():
    """`reclaimed_20d_share` is a share of the washed-out members that HAVE a 20-day
    line (3 here), never of washed_out_n (9) — multiplying it back by 9 invents six
    members that reclaimed nothing."""
    en, _zh = _detail(_tiles(_pulse())[2])
    assert "3 back above their 20-day line" in en, en
    assert "9 back above" not in en


@needs_node
def test_the_trend_line_divides_by_the_members_that_have_the_line():
    """Same defect, the other tile: 0.6 of the 11 members with a 50-day line is 7, and
    0.6 of the 14 covered is 8. The two legs also carry DIFFERENT denominators."""
    en, zh = _detail(_tiles(_pulse())[0])
    assert "7 of 11" in en and "5 of 10" in en, en
    assert "of 14" not in en, f"trend shares are back on the covered count: {en!r}"
    assert "11" in zh and "10" in zh, zh


@needs_node
def test_a_basket_with_no_200_day_line_drops_the_clause_instead_of_printing_a_hole():
    en, zh = _detail(_tiles(_pulse(participation={"trend_share_200d": None,
                                                  "trend_n_200d": 0}))[0])
    assert "200-day" not in en and "200日线" not in zh
    assert "50-day line: 7 of 11" in en
    for blob in (en, zh):
        assert "null" not in blob and "NaN" not in blob and "undefined" not in blob


@needs_node
def test_the_arc_tile_refuses_with_no_figure_at_all():
    """G0-10 — the refusal branch was dead: it tested `washed_out_n == null`, a count
    the engine never nulls, so "Not enough covered" always shipped with a confident
    number underneath it. Under the floor the detail must carry NO digit."""
    refused = _pulse(arc={"state": "insufficient_coverage", "washed_out_share": None,
                          "washed_out_n": 2, "washout_readable_n": 4,
                          "reclaimed_20d_share": None, "reclaimed_readable_n": 2,
                          "stage2_share": None, "stage4_share": None, "staged_n": 4,
                          "drawdown_pctile_own_history": None})
    tile = _tiles(refused)[2]
    en, zh = _detail(tile)
    assert not re.search(r"\d", en), f"a figure survived the refusal: {en!r}"
    assert not re.search(r"\d", zh), f"a figure survived the refusal: {zh!r}"
    assert "Too few members are covered" in en
    assert "太少" in zh
    # the refusal WORD still stands in the headline — the tile refuses, it does not blank
    head = _langs(re.search(r'<div class="v">(.*?)</div>', tile, re.S).group(1))
    assert head[0] and head[1] and head[0] != head[1]


@needs_node
def test_a_stale_artifact_under_the_floor_still_refuses_on_the_state():
    """The page refuses on the STATE, not on the nulls — so last night's bytes, which
    still carry numeric legs under `insufficient_coverage`, refuse too rather than
    printing the numbers the engine has since stopped standing behind."""
    stale = _legacy_pulse(arc={"state": "insufficient_coverage"})
    en, zh = _detail(_tiles(stale)[2])
    assert not re.search(r"\d", en), en
    assert not re.search(r"\d", zh), zh


def _headline(tile: str) -> tuple[str, str]:
    """The tile's largest type — the `v` div."""
    m = re.search(r'<div class="v">(.*?)</div>', tile, re.S)
    assert m, f"tile has no headline: {tile[:200]!r}"
    return _langs(m.group(1))


@needs_node
def test_a_refused_agreement_never_renders_a_dash_placeholder_as_the_headline():
    """The two floors do not coincide: at exactly three movers the tile is ABOVE its own
    movers floor (so it prints a direction word) and BELOW the engine's agreement floor
    (so there is no band to append). The band's null form is an em-dash, and it was
    landing in the tile's largest type as "Up — —" on six live baskets.

    The sign word now stands alone; the refusal is spoken in the small print below."""
    p = _pulse(participation={"activity_n": 3},
               direction={"agreement_pct": None, "n_active": 3, "sign": "up"})
    en, zh = _headline(_tiles(p)[1])
    assert en == "Up", f"headline is not the bare sign word: {en!r}"
    assert zh == "上行", f"ZH headline is not the bare sign word: {zh!r}"
    for blob in (en, zh):
        assert "—" not in blob and "-" not in blob, f"placeholder in the headline: {blob!r}"
    # ...and the band still renders when there IS an agreement figure to band
    en2, zh2 = _headline(_tiles(_pulse(participation={"activity_n": 3}))[1])
    assert "—" in en2 and "—" in zh2, "the band clause vanished for a real read"
    assert "mostly the same way" in en2 and "多数同向" in zh2


@needs_node
def test_the_direction_hover_names_both_floors_in_plain_words():
    """The floor's Tier-2 receipt has to live where the floor fires. The board caption
    says four; the tile's own visible refusal line says three — a reader who sees the
    percentage withheld needs both numbers in one place, or the page contradicts
    itself."""
    from engine import group_pulse as GP
    tile = _tiles(_pulse(direction={"agreement_pct": None, "n_active": 3}))[1]
    en = re.search(r'data-tip-en="([^"]*)"', tile).group(1)
    zh = re.search(r'data-tip-zh="([^"]*)"', tile).group(1)
    assert "at least 3 members moving" in en, en
    assert f"needs at least {GP.AGREEMENT_MIN_N}" in en, en
    assert "至少需要 3 只在动" in zh, zh
    assert f"至少需要 {GP.AGREEMENT_MIN_N} 只" in zh, zh
    assert not re.search(r"[一-鿿]", en), "ZH leaked into the EN tip"
    for blob in (en, zh):
        assert "AGREEMENT_MIN_N" not in blob and "GR_MIN_MOVERS" not in blob


def test_the_template_agreement_floor_tracks_the_engine_constant():
    """The tile hardcodes the engine's floor to speak it in plain words. Bumping
    AGREEMENT_MIN_N without the template would silently start lying to the reader."""
    from engine import group_pulse as GP
    m = re.search(r"var GR_MIN_AGREEMENT_N=(\d+);", DETAIL.read_text(encoding="utf-8"))
    assert m, "the template no longer declares its agreement floor"
    assert int(m.group(1)) == GP.AGREEMENT_MIN_N


@needs_node
def test_the_watch_list_does_not_watch_a_figure_that_was_refused():
    """"agreement fading below a third of the movers" was firing on every basket whose
    agreement is null — 43 of 49 live — watching a number the engine declined to
    compute. With nothing to fade, the condition is the movers never converging."""
    rows = _run("""
        var out = {};
        [null, 0.42].forEach(function (ag, i) {
          out[i] = grWatchList({participation: {activity_share: 0.5, activity_n: 3},
                                direction: {sign: 'up', agreement_pct: ag},
                                arc: {state: 'quiet'}, episode: {active_now: true}});
        });
        process.stdout.write(JSON.stringify(out));
    """)
    refused, real = rows["0"], rows["1"]
    flat = " ".join(x for pair in refused["down"] for x in pair)
    assert "fading" not in flat, f"a refused figure is still being watched: {flat}"
    assert "never settling into one direction" in flat, flat
    assert "始终无法收敛" in flat, flat
    # the real read keeps the original condition
    assert "fading" in " ".join(x for pair in real["down"] for x in pair)
    # and the same words never appear in both columns
    for row in (refused, real):
        assert not ({tuple(x) for x in row["up"]} & {tuple(x) for x in row["down"]})


@needs_node
def test_a_refused_agreement_reads_as_plain_words_in_both_languages():
    """`agreement_pct` is null below the engine's movers floor. "Agreement pending"
    said the figure was on its way; it is not coming, and the tile says why."""
    en, zh = _detail(_tiles(_pulse(direction={"agreement_pct": None, "n_active": 3}))[1])
    assert "Too few members moving to read agreement" in en, en
    assert "在动的个股太少" in zh, zh
    assert "median" in en, "the SPY-adjusted median is a different leg and survives"
    for blob in (en, zh):
        assert "NaN" not in blob and "undefined" not in blob and "null" not in blob
    # the median move is the ONLY figure left; no agreement percentage is reconstructed
    assert "net agreement" not in en and "净一致度" not in zh
    assert re.findall(r"[\d.]+%", en) == ["1.2%"], en


@needs_node
def test_the_tiles_render_clean_against_last_nights_artifact():
    """Transition — the denominators appear only after the next nightly re-emits
    pulse.json. Until then every tile must render without junk and without inventing
    a denominator it does not have."""
    tiles = _tiles(_legacy_pulse())
    for i, tile in enumerate(tiles[:3]):
        en, zh = _detail(tile)
        for blob in (en, zh):
            assert "undefined" not in blob and "NaN" not in blob, (i, blob)
            assert "null" not in blob, (i, blob)
    arc_en, _ = _detail(tiles[2])
    assert "9" in arc_en, "the washout count itself is still printed"
    assert " of " not in arc_en, f"a denominator was invented for a legacy object: {arc_en!r}"
    # The trend line drops rather than borrowing n_covered: substituting it invents the
    # NUMERATOR too — 0.6 x 14 renders "8 of 14" where the truth is 7 of 11.
    trend_en, trend_zh = _detail(tiles[0])
    assert "Trend coverage pending" in trend_en, trend_en
    assert "趋势读数待补" in trend_zh, trend_zh
    for blob in (trend_en, trend_zh):
        assert not re.search(r"\d", blob), f"a count was fabricated: {blob!r}"


@needs_node
def test_no_tile_leaks_a_slug_or_a_banned_word():
    for p in (_pulse(), _legacy_pulse(),
              _pulse(arc={"state": "insufficient_coverage", "washed_out_share": None,
                          "reclaimed_20d_share": None, "stage2_share": None,
                          "stage4_share": None,
                          "drawdown_pctile_own_history": None}),
              _pulse(direction={"agreement_pct": None, "n_active": 2})):
        for tile in _tiles(p):
            en, zh = _langs(tile)
            for blob in (en, zh):
                for bad in BANNED:
                    assert bad.lower() not in blob.lower(), f"banned {bad!r} in {blob!r}"


# ══════════════════════════════════════════════════════════════════════════════
# 2c — a refused agreement must not out-sort a real one
# ══════════════════════════════════════════════════════════════════════════════

@needs_node
def test_a_refused_agreement_sorts_below_a_real_one_on_the_board():
    """The tiebreak reads `agreement_pct` raw. Now that the leg is nullable, a basket
    the engine declined to read must not sort ABOVE one it did read — a null that
    coalesced to 1.0 would put the least-readable baskets at the top of the board."""
    board = BOARD.read_text(encoding="utf-8")
    rule = _region(board, "let GPULSE=null;", "function renderGroupPulseCol")
    order = _run("""
        %s
        %s
        GPULSE = {real: {episode: {state_change: 'steady'},
                         participation: {activity_share: 0.5},
                         direction: {agreement_pct: 0.1}},
                  refused: {episode: {state_change: 'steady'},
                            participation: {activity_share: 0.5},
                            direction: {agreement_pct: null}},
                  absent: {episode: {state_change: 'steady'},
                           participation: {activity_share: 0.5}, direction: {}}};
        var ids = [{id: 'refused'}, {id: 'absent'}, {id: 'real'}];
        ids.sort(grCmp);
        process.stdout.write(JSON.stringify(ids.map(function (r) { return r.id; })));
    """ % (HARNESS_PRELUDE, rule))
    assert order[0] == "real", f"a refused agreement out-sorted a real read: {order}"


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
    # G0-10 — a leg that REFUSES below a floor is part of the rule. A caption that
    # names agreement as a tiebreak without saying when agreement exists describes an
    # ordering the reader cannot reproduce on the baskets where it is null.
    assert "sorts below a basket that has one" in src


#: The caption says the floor in WORDS (glance tier prints no bare constants), so the
#: link back to the engine is this map. Bumping AGREEMENT_MIN_N reds the test below by
#: name until the caption and this row are updated together.
_FLOOR_WORDS = {4: ("four", "四")}


def test_the_board_caption_names_the_floor_the_engine_actually_uses():
    from engine import group_pulse as GP
    assert GP.AGREEMENT_MIN_N in _FLOOR_WORDS, (
        f"AGREEMENT_MIN_N moved to {GP.AGREEMENT_MIN_N} — update the board caption in "
        "templates/sector_central.html.j2 (EN + ZH) and add the word to _FLOOR_WORDS")
    en_word, zh_word = _FLOOR_WORDS[GP.AGREEMENT_MIN_N]
    src = BOARD.read_text(encoding="utf-8")
    assert f"Agreement counts only where at least {en_word} members are moving" in src
    assert f"方向一致度仅在至少{zh_word}只成分股在动时才计入" in src
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
