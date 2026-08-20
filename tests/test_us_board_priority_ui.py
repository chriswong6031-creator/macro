"""Rendered-HTML contract for the US board priority display layer (us_prophet_v1).

Program: research/PROPHET_BOARD_PRIORITY_ENGINE_MASTERPLAN_BY_FABLE.md
Gates covered here: G0.1 (priority order + stage buckets), G0.2 (featured glow),
G0.4 (ran lane), G0.5 (theme chips), G0.6 (stage filter
chips + NEW badge), G0.7 (honest score framing on the surface).

TWO SHAPES, ONE TEMPLATE.  The committed `site/factordata/us_standouts.json` does
NOT carry stage / prophet / featured / new / theme yet — the first nightly after the
engine lane merges fills them.  So every assertion below comes in a pair: the new
schema must produce the priority surface, and the OLD schema must still produce the
legacy lane-partition board with none of it.  A regression that quietly drops the
fail-soft branch would ship a blank board on merge night.

ASSERTION STYLE (harness law): every presence/absence assertion targets a full
markup string (`'<div class="nb-stage-hd sg-live"'`), never a bare class token.
The CSS rules for all of this ship on every render, so `'nb-stage-hd' in html`
is true even when nothing renders — an absence test written that way is vacuous.

`priority_overlay()` is also the fixture the preview/screenshot pass uses against
the LIVE artifact (see the module docstring on how to run it) — keeping it here,
deterministic and site/-free, means the picture and the test see the same shapes.
"""
from __future__ import annotations

import re
from zlib import crc32

import jinja2

from tests.test_dashboard_template_render import _base_vm, _board_row, _env, _setup_row

# --------------------------------------------------------------------------- #
# Deterministic us_prophet_v1 overlay
# --------------------------------------------------------------------------- #

# Stage buckets — masterplan §3.1.  entry_signal.status is the grouping authority;
# a DOWNTREND label forces `blocked` regardless of status.
_STAGE_OF_STATUS = {
    "buy_now": "live", "partial": "live", "buy_soon": "live",
    "await_confluence": "setting_up", "bounce_wait": "setting_up", "watch": "setting_up",
    "extended": "ran", "topping": "ran", "hold": "ran",
    "blocked": "blocked", "exit": "blocked", "avoid": "blocked",
}
_STAGE_ORDER = ["live", "setting_up", "ran", "basing", "blocked"]

# Three in-favour baskets, mirroring the shape §3.6's loader stamps onto rows.
_THEMES = [
    {"id": "ai_software", "name": "AI software", "name_zh": "AI软件", "rank": 3, "reco": "accumulate"},
    {"id": "non_ai_software", "name": "Software", "name_zh": "软件", "rank": 4, "reco": "accumulate"},
    {"id": "power_grid", "name": "Power & grid", "name_zh": "电力与电网", "rank": 6, "reco": "enter"},
]


def _stage_of(row: dict) -> str:
    status = ((row.get("entry_signal") or {}).get("status")) or ""
    if status in ("blocked", "exit", "avoid"):
        return "blocked"
    # BOTTOM WATCH before DOWNTREND — both are `dir: down`, and the specific one wins
    # (engine.us_board_rank.stage_for, W-E.1).
    if (row.get("state") or "").upper() == "BOTTOM WATCH":
        return "basing"
    if (row.get("label") or "").upper() == "DOWNTREND":
        return "blocked"
    return _STAGE_OF_STATUS.get(status, "setting_up")


# Entry-value points (§3.2 gives `entry` 25 of the 100).  The overlay reproduces this
# leg for real so the preview ORDER is shaped like the engine's: a buy_now outranks a
# buy_soon of equal idiosyncratic strength.  A pure random score would have put a
# "buy soon" card at slot #1 of the screenshots — pretty, and a lie about the design.
_ENTRY_VALUE = {
    "buy_now": 25, "partial": 21, "buy_soon": 14,
    "await_confluence": 11, "bounce_wait": 9, "watch": 6,
    "hold": 5, "extended": 4, "topping": 3,
    "blocked": 0, "exit": 0, "avoid": 0,
}


def _pseudo_score(ticker: str, status: str = "") -> float:
    """Stable 0–100 stand-in for the real priority score: the true entry leg plus a
    deterministic stand-in for the other 75 points.  crc32, not hash() — hash() is
    salted per process, so a hashed fixture would reorder between runs."""
    other = (crc32(ticker.encode()) % 7000) / 100.0     # 0.0–69.9 of the other 75 pts
    return round(_ENTRY_VALUE.get(status, 6) + other, 1)


def priority_overlay(rows, *, n_themed=15, board_cap=12, sector_cap=4):
    """Stamp the frozen us_prophet_v1 row contract onto a list of buy rows and return
    them in the order the engine promises: stage bucket first (live → setting_up →
    ran → blocked), priority score desc inside the bucket, ticker as the tiebreak.

    Mutates copies, never the input rows.  Deterministic for a given input order.
    """
    out = []
    for i, row in enumerate(rows):
        row = dict(row)
        ticker = row.get("ticker") or f"T{i}"
        stage = _stage_of(row)
        score = _pseudo_score(ticker, ((row.get("entry_signal") or {}).get("status")) or "")
        row["stage"] = stage
        row["prophet"] = {
            "version": "us_prophet_v1",
            "score": score,
            "components": {"signal": 26.0, "entry": 21.0, "edge": 17.5, "runway": 7.0, "quality": 8.0},
        }
        row["new"] = (i % 4 == 0) and stage == "live"
        row["days_since_signal"] = i % 9
        if i < n_themed:
            row["theme"] = dict(_THEMES[i % len(_THEMES)])
        out.append(row)

    out.sort(key=lambda r: (_STAGE_ORDER.index(r["stage"]), -r["prophet"]["score"], r["ticker"]))

    # Featured: buy_now/partial ONLY (§3.4 excludes buy_soon), board cap 12,
    # sector cap 4, score desc.  The buy_soon exclusion is load-bearing for the
    # display layer, not just the engine: buy_now/partial are the two statuses the
    # card maps to the `buy` verb, so every featured card's hue rail is --pv-buy and
    # the bullish aura never sits on a lighter `near` card.
    per_sector: dict[str, int] = {}
    featured = 0
    for row in out:
        sector = row.get("sector") or "—"
        eligible = (
            ((row.get("entry_signal") or {}).get("status")) in ("buy_now", "partial")
            and featured < board_cap
            and per_sector.get(sector, 0) < sector_cap
        )
        row["featured"] = bool(eligible)
        if eligible:
            featured += 1
            per_sector[sector] = per_sector.get(sector, 0) + 1

    for rank, row in enumerate(out, start=1):
        row["score_rank"] = rank
        row["display_rank"] = rank
    return out


def ran_overlay(rows, *, cap=6):
    """The separate `ran` artifact array (§3.5): fired 3–15 sessions ago, trend intact.

    `ticks` and `sessions_since` are BOTH emitted and they are NOT the same number:
    ticks counts 3-day-grid buckets, so it runs ~3x short of the real session age
    (engine/us_board_rank.py cross_read).  The fixture keeps them deliberately
    different so a template that renders the wrong one fails visibly.

    `anchor` (B3) is the age's provenance, and the fixture ships BOTH values plus the
    absent case: "marker" = counted from the row's own buy-marker date, "approx" =
    worked back from the fresh-bar window, so the number is an estimate and must not
    print like a measurement.  Row 1 is approx, the rest are marker; the caller drops
    the key entirely to reproduce a pre-B3 artifact.

    Two rows carry theme_confirmed plus the engine's own theme_note strings — the
    front-running case the warm treatment marks."""
    out = []
    for i, row in enumerate(rows[:cap]):
        ticks = 3 + (i * 2)
        entry = {
            "ticker": row.get("ticker"),
            "name": row.get("name"),
            "sector": row.get("sector"),
            "price": row.get("price"),
            "ticks": ticks,
            "sessions_since": ticks * 3 - 1,
            "anchor": "approx" if i == 1 else "marker",
            "cross_date": "2026-07-14",
            "pct_since": round(-2.0 + _pseudo_score(row.get("ticker") or "X") / 8.0, 1),
            "label": row.get("label"),
            "label_zh": row.get("label_zh"),
            "stage": "ran",
            "lane": "ran",
            "theme": dict(_THEMES[i % len(_THEMES)]),
        }
        if i < 2:
            entry["theme_confirmed"] = True
            entry["theme_note"] = "Theme just confirmed — watch for the next entry"
            entry["theme_note_zh"] = "主题刚确认 — 关注下一个买点"
            entry["theme"]["bull_days"] = 3 + i
        out.append(entry)
    return out


def leaders_overlay(rows):
    """Theme stamps on the leaders lane (G0.5a) — one row also theme_confirmed."""
    out = []
    for i, row in enumerate(rows):
        row = dict(row)
        row["theme"] = dict(_THEMES[i % len(_THEMES)])
        if i == 0:
            row["theme_confirmed"] = True
            row["theme"]["bull_days"] = 4
        out.append(row)
    return out


# --------------------------------------------------------------------------- #
# View models
# --------------------------------------------------------------------------- #

def _rich_rows() -> list[dict]:
    """A board wide enough to fill all five stage buckets, with sectors that make the
    featured sector-cap bite, one DOWNTREND row that must land in `blocked`, and one
    BOTTOM WATCH row that must land in `basing` — the two are both `dir: down` and the
    board used to file them together, which is the defect W-E.1 fixes."""
    spec = [
        ("HL", "Hecla Mining", "Materials", "wait_pullback", "NEARING A LOW"),
        ("AAPL", "Apple Inc.", "Information Technology", "buy_now", None),
        ("MSFT", "Microsoft Corp.", "Information Technology", "partial", None),
        ("PLTR", "Palantir Technologies", "Information Technology", "buy_now", None),
        ("CRWD", "CrowdStrike Holdings", "Information Technology", "buy_now", None),
        ("APP", "AppLovin Corp.", "Information Technology", "partial", None),
        ("VST", "Vistra Corp.", "Utilities", "buy_now", None),
        ("CEG", "Constellation Energy", "Utilities", "buy_soon", None),
        ("ISRG", "Intuitive Surgical", "Health Care", "buy_now", None),
        ("JPM", "JPMorgan Chase", "Financials", "await_confluence", None),
        ("BAC", "Bank of America", "Financials", "bounce_wait", None),
        ("XOM", "Exxon Mobil", "Energy", "watch", None),
        ("CVX", "Chevron Corp.", "Energy", "bounce_wait", None),
        ("KO", "Coca-Cola Co.", "Consumer Staples", "extended", None),
        ("PEP", "PepsiCo Inc.", "Consumer Staples", "topping", None),
        ("M", "Macy's Inc.", "Consumer Discretionary", "hold", None),
        ("ORA", "Ormat Technologies", "Utilities", "avoid", None),
        ("NXE", "NexGen Energy", "Energy", "blocked", "DOWNTREND"),
    ]
    rows = []
    for ticker, name, sector, status, label in spec:
        rows.append(_board_row(
            ticker=ticker, name=name, sector=sector, label=label,
            # The ladder stamps BOTH `state` (internal key) and `label` (display) on a
            # board row; the engine matches the state first, so the fixture carries it.
            state=("BOTTOM WATCH" if label == "NEARING A LOW" else None),
            dir=("down" if label in ("NEARING A LOW", "DOWNTREND") else "up"),
            lane="bottoming" if status in ("buy_now", "await_confluence") else "continuation",
            entry_signal={"status": status, "headline": f"{status} headline", "headline_zh": "标题",
                          "buy_zone": {"low": 100.0, "high": 110.0}},
            signal={"asof": "2026-07-31"},
        ))
    return rows


def themes_in_favour_overlay(board):
    """The artifact's own top-level strip source (build_stock_library wide[...]).

    Its `tickers` are the FULL basket membership — mostly names that are NOT on this
    board — so the fixture deliberately mixes on-board and off-board tickers, and one
    theme (rank 9) has NO on-board name at all.  A strip that printed the raw list, or
    that kept an empty theme to look fuller, fails on this fixture."""
    on_board = [r["ticker"] for r in board]
    return [
        {"id": "ai_software", "name": "AI software", "name_zh": "AI软件", "rank": 3,
         "reco": "accumulate", "bull_days": 5, "clean_entry": True,
         "tickers": sorted(set(on_board[:5] + ["NVDA", "AMD", "SNOW"]))},
        {"id": "non_ai_software", "name": "Software", "name_zh": "软件", "rank": 4,
         "reco": "accumulate", "bull_days": 3, "clean_entry": True,
         "tickers": sorted(set(on_board[5:8] + ["ADBE", "INTU"]))},
        {"id": "power_grid", "name": "Power & grid", "name_zh": "电力与电网", "rank": 6,
         "reco": "enter", "bull_days": None, "clean_entry": False,
         "tickers": sorted(set(on_board[8:10] + ["GEV"]))},
        {"id": "shipping", "name": "Shipping", "name_zh": "航运", "rank": 9,
         "reco": "accumulate", "bull_days": 2, "clean_entry": True,
         "tickers": ["ZIM", "MATX"]},          # none of these are on the board
    ]


def _priority_vm() -> dict:
    vm = _base_vm()
    board = priority_overlay(_rich_rows())
    vm["us_standouts"] = {
        "buy": board,
        "ran": ran_overlay([r for r in board if r["stage"] == "ran"] or board[-4:]),
        "leaders": leaders_overlay([
            _board_row(ticker="NOW", name="ServiceNow", sector="Information Technology", alpha=1.8),
            _board_row(ticker="WDAY", name="Workday Inc.", sector="Information Technology", alpha=1.1),
        ]),
        "themes_in_favour": themes_in_favour_overlay(board),
        "eligible": len(board),
        "as_of": "2026-07-31",
        "rank_by": "us_prophet_v1",
    }
    return vm


def _render(vm: dict, mode: str = "stocks") -> str:
    return _env().get_template("dashboard.html.j2").render(**vm, mode=mode)


def _priority_html() -> str:
    return _render(_priority_vm())


def _legacy_html() -> str:
    """The committed-artifact shape: rows with no stage / prophet / featured keys."""
    vm = _base_vm()
    vm["us_standouts"] = {"buy": _rich_rows(), "eligible": 17}
    return _render(vm)


# --------------------------------------------------------------------------- #
# G0.1 — priority order and stage buckets
# --------------------------------------------------------------------------- #

def test_stage_headings_render_in_fixed_order():
    html = _priority_html()
    positions = []
    for key in ("live", "setting_up", "ran", "basing", "blocked"):
        needle = f'<div class="nb-stage-hd sg-{key}" data-stage="{key}"'
        idx = html.find(needle)
        assert idx != -1, f"stage heading for {key!r} missing"
        positions.append(idx)
    assert positions == sorted(positions), f"stage headings out of order: {positions}"


def test_the_basing_shelf_renders_between_ran_and_blocked():
    """W-E.1 / D18. The shelf is the whole deliverable: a BOTTOM WATCH name used to
    render inside `Blocked` beside the falling knives, which is where the operator
    stops reading. Its own shelf, above Blocked, is what makes the state visible."""
    html = _priority_html()
    basing = html.find('<div class="nb-stage-hd sg-basing" data-stage="basing"')
    assert basing != -1, "the basing shelf never rendered"
    assert (html.find('<div class="nb-stage-hd sg-ran" data-stage="ran"') < basing
            < html.find('<div class="nb-stage-hd sg-blocked" data-stage="blocked"'))
    # The BOTTOM WATCH name is on the shelf, and the DOWNTREND name is NOT.
    assert html.find('data-ticker="HL"') > basing
    assert html.find('data-ticker="HL"') < html.find('data-ticker="NXE"')


def test_the_basing_shelf_speaks_watch_words_in_both_languages():
    """P2/G0.4: a watch lane that never makes a claim. The shelf says what the state
    is and what to do about it — and 'buy' is not one of the things it can say."""
    html = _priority_html()
    assert '<span class="l-en">Basing</span><span class="l-zh">筑底中</span>' in html
    assert ('<span class="l-en">no entry signal yet — watch, don’t chase</span>'
            '<span class="l-zh">尚无入场信号 — 观察，勿追高</span>') in html
    shelf = html[html.find('<div class="nb-stage-hd sg-basing"'):]
    shelf = shelf[:shelf.find("</div>") + 6]
    for banned in ("Buy", "buy", "买入"):
        assert banned not in shelf, f"{banned!r} on a watch-only shelf"


def test_the_basing_shelf_takes_a_direction_neutral_tone():
    """--pv-wait and --muted are the two verb tones theme.css does NOT flip under the
    zh 红涨绿跌 convention, so a stance with no direction in it reads the same in both
    languages. Inheriting --pv-avoid (what these rows had inside Blocked) would paint
    a basing name with the stand-aside colour it is being taken out of."""
    html = _priority_html()
    assert ".sg-basing     { --sgc: var(--pv-wait); }" in html
    assert ".sg-blocked    { --sgc: var(--pv-avoid); }" in html


def test_the_basing_bucket_is_filterable_like_every_other():
    html = _priority_html()
    assert 'data-stagepick="basing"' in html
    assert ('#us-standouts[data-stagef="basing"]     '
            '[data-stage]:not([data-stage="basing"])') in html
    assert ('#us-standouts[data-stagef="basing"]     '
            '.sm-hidden[data-stage="basing"]') in html


def test_stage_headings_carry_label_count_and_stance():
    """Tier-1 budget: the bucket name IS the stance, the count is a pill, and the
    tail sentence stays under the 14-word subtitle cap."""
    html = _priority_html()
    assert '<span class="l-en">Live now</span><span class="l-zh">现在可操作</span>' in html
    # The ZH separator is the em-dash the EN label uses, not a middot: the two halves
    # are a state and a stance, and every sibling ZH label on this surface
    # (`尚未触发 — 做好准备`) already joins them that way.
    assert '<span class="l-en">Ran — don’t chase</span><span class="l-zh">已启动 — 勿追</span>' in html
    assert "已启动 · 勿追" not in html
    assert '<span class="l-en">entry window is open</span>' in html
    assert '<span class="l-en">stand aside for now</span>' in html
    assert '<span class="sh-n">' in html


def test_no_blocked_or_ran_card_renders_above_the_first_live_card():
    """The measured defect this program exists to fix: 'Extended — don't chase' and
    DOWNTREND rows outranking fresh buy_now rows."""
    html = _priority_html()
    first_live = html.find('data-stage="live"')
    assert first_live != -1
    for late in ("ran", "blocked"):
        idx = html.find(f'data-stage="{late}"')
        assert idx > first_live, f"a {late!r} element renders above the first live element"
    # And concretely: the DOWNTREND name may not precede the first buy_now name.
    assert html.find('data-ticker="AAPL"') < html.find('data-ticker="NXE"')


def test_legacy_artifact_keeps_the_lane_partition_and_grows_no_priority_surface():
    """Fail-soft proof: no stage on the rows -> today's board, unchanged."""
    html = _legacy_html()
    # legacy headings still render. `data-lane` was added 2026-08-20 as the
    # hydration join key (tests/test_us_board_hydration_merge.py) — additive,
    # same class, same label; the class is what this test is about.
    assert '<div class="nb-lane-hd" data-lane="' in html
    assert '<div class="nb-stage-hd sg-' not in html     # …and nothing new appears
    assert '<div class="pbf-bar" id="us-stage-filter"' not in html
    assert '<div class="pbt">' not in html
    assert '<div class="pbr" data-stage="ran">' not in html
    assert 'class="pvcard pv-buy pv-featured"' not in html
    assert '<div class="pv-mk">' not in html
    assert '<p class="pb-fn">' not in html
    assert 'data-ticker="AAPL"' in html                  # the board DID render


# --------------------------------------------------------------------------- #
# G0.2 — featured glow
# --------------------------------------------------------------------------- #

def test_featured_class_and_chip_land_only_on_featured_rows():
    vm = _priority_vm()
    html = _render(vm)
    featured = [r["ticker"] for r in vm["us_standouts"]["buy"] if r["featured"]]
    plain = [r["ticker"] for r in vm["us_standouts"]["buy"] if not r["featured"]]
    assert featured and plain, "fixture must contain both featured and non-featured rows"

    for ticker in featured:
        card = _card_markup(html, ticker)
        # Always the BUY verb: §3.4 admits only buy_now/partial, so the aura's green
        # never lands on a lighter `near` rail (the card's one-hue law).
        assert '<a class="pvcard pv-buy pv-featured"' in card, f"{ticker} lost its glow class"
        assert '<span class="pv-mk-i pv-mk-feat"' in card, f"{ticker} lost its Featured chip"
    for ticker in plain:
        card = _card_markup(html, ticker)
        assert "pv-featured" not in card, f"{ticker} must not glow"
        assert "pv-mk-feat" not in card, f"{ticker} must not carry the Featured chip"


def test_featured_chip_is_bilingual_and_supersedes_the_triage_ring():
    html = _priority_html()
    assert '<span class="l-en">★ Featured</span><span class="l-zh">★ 精选</span>' in html
    # One accent per card: a featured card never also carries the older triage ring.
    assert "pv-featured pv-triage" not in html
    assert "pv-triage pv-featured" not in html


def test_featured_glow_is_static_and_theme_aware():
    """No animation means no prefers-reduced-motion kill block to keep in sync — but
    that only holds while nothing animates.  Pin both halves, plus the light override
    and the semantic Prophet hue (never bypassing --pv-buy with --up)."""
    html = _priority_html()
    # Tone calibration (operator correction 2026-08-03): the card BODY stays plain —
    # dark keeps a 2.5% barely-there lift, light is pure #fff with NO tint; featured
    # reads through the thin --pv-buy ring + faint aura + the star chip.
    assert ".pvcard.pv-featured{background:color-mix(in srgb,var(--pv-buy) 2.5%" in html
    assert 'html[data-theme="light"] .pvcard.pv-featured{background:#fff' in html
    assert 'border-color:color-mix(in srgb,var(--pv-buy) 30%,var(--line))' in html
    assert ".pvcard.pv-featured:hover{" in html          # hover ADDS lift, never replaces the aura
    assert 'html[data-theme="light"] .pvcard.pv-featured:hover{' in html
    glow = html[html.find(".pvcard.pv-featured{"):html.find(".pv-chart{")]
    assert "animation" not in glow and "@keyframes" not in glow, "featured glow must not animate"
    assert "var(--up)" not in glow, "the glow must use the language-aware --pv-buy token"


# --------------------------------------------------------------------------- #
# ANTICIPATION v1 — the per-row "Extended? Not checked" mark
#
# PR #4976 made the board DISCLOSE a missing extension reading instead of vetoing
# the row out of the featured shelf, and wrote honest copy at four sites — two of
# which never rendered, because `_MK_NOTIP = ('feat', 'new')` drops the ★ Featured
# tooltip on both boards.  The aggregate count reached the reader (board footnote);
# WHICH picks were unmeasured did not.  This section pins the visible carrier.
#
# ASSERTION STYLE: `.pv-mk-nck`'s CSS ships on every render, so every presence and
# absence claim below targets the full markup string, never the bare class token
# (module docstring, harness law).
# --------------------------------------------------------------------------- #

_NCK_MARK = '<span class="pv-mk-i pv-mk-nck"'


def _ext_vm(mode: str) -> tuple[dict, list[str]]:
    """The priority VM with `ext_unknown` stamped on every row, plus the receipt.

    `mode="mixed"` is the ordinary board: two featured rows lost the reading and the
    rest kept it — AND every non-featured row is unknown too, which is what makes the
    featured-only scope falsifiable rather than incidental.
    `mode="all"` is the total-outage night (2026-08-06 published a featured lane of
    0 of 69 under the old veto; the same outage now lights the whole shelf unmeasured).

    The coverage receipt is COMPUTED from these rows by the engine's own function, so
    the footnote's count cannot drift from the cards the fixture renders.
    """
    from engine import us_board_rank as _ubr

    vm = _priority_vm()
    rows = vm["us_standouts"]["buy"]
    featured = [r["ticker"] for r in rows if r.get("featured")]
    assert len(featured) >= 3, "fixture lost its featured shelf — assertions would be weak"
    if mode == "all":
        unknown = {r["ticker"] for r in rows}
    else:
        unknown = {featured[0], featured[-1]}
        unknown |= {r["ticker"] for r in rows if not r.get("featured")}
    for row in rows:
        row["ext_unknown"] = row["ticker"] in unknown
    vm["us_standouts"]["ranking"] = {
        "ext_unknown_coverage": _ubr.ext_unknown_coverage(rows),
    }
    return vm, featured


def test_an_unmeasured_featured_card_says_so_and_a_measured_one_does_not():
    """The deliverable: the reader can see WHICH picks the chase-risk check skipped."""
    vm, featured = _ext_vm("mixed")
    html = _render(vm)
    rows = vm["us_standouts"]["buy"]
    unknown_featured = [r["ticker"] for r in rows if r.get("featured") and r["ext_unknown"]]
    known_featured = [r["ticker"] for r in rows if r.get("featured") and not r["ext_unknown"]]
    assert unknown_featured and known_featured, "fixture must contain both to discriminate"

    for ticker in unknown_featured:
        assert _NCK_MARK in _card_markup(html, ticker), f"{ticker} lost its absence mark"
    for ticker in known_featured:
        assert _NCK_MARK not in _card_markup(html, ticker), (
            f"{ticker} has an extension reading and must claim nothing about a gap")


def test_the_absence_mark_stays_off_rows_whose_featured_claim_it_would_not_qualify():
    """Scope is featured-only ON PURPOSE, though the engine stamps every row.

    The extension reading feeds the featured gate; on a Wait or Blocked card nothing
    on the card leans on it, so the mark would answer a question no reader is asking
    (doctrine Law 1) while spending a slot in a row whose median card shows one chip.
    The fixture makes every non-featured row unknown, so a mark that leaked onto them
    fails here rather than shipping as chip spam."""
    vm, _ = _ext_vm("mixed")
    html = _render(vm)
    plain_unknown = [r["ticker"] for r in vm["us_standouts"]["buy"]
                     if not r.get("featured") and r["ext_unknown"]]
    assert plain_unknown, "fixture must carry unknown NON-featured rows"
    for ticker in plain_unknown:
        assert _NCK_MARK not in _card_markup(html, ticker), (
            f"{ticker} is not featured — it makes no claim for the mark to qualify")


def test_the_absence_mark_is_bilingual_and_asserts_nothing_about_the_name():
    """The honest stance is "we could not check", never "this name IS extended" and
    never an all-clear.  The question mark is what carries that — the chip poses the
    open question and answers it with the null, so neither misreading survives."""
    vm, _ = _ext_vm("mixed")
    html = _render(vm)
    assert ('<span class="l-en">Extended? Not checked</span>'
            '<span class="l-zh">涨过头？未检查</span>') in html
    # The mark keeps its Tier-2 receipt: 'nck' is deliberately NOT in _MK_NOTIP,
    # because unlike feat/new it names something the reader cannot infer from the card.
    mark = html[html.find(_NCK_MARK):]
    mark = mark[:mark.find("</span>", mark.find("l-zh"))]
    assert "data-tip-en=" in mark and "data-tip-zh=" in mark
    assert "an absence, not a finding that it has" in html
    assert "是「没查」，不是「查出来涨过头了」" in html
    # No slug and no enum token: the flag's name never reaches the page, and the mark's
    # own markup carries neither it nor the engine field it is derived from.  (`ext_z`
    # is NOT asserted page-wide — a long-standing display-only chip owns that class
    # name in the stylesheet, which is not user-visible copy.)
    assert "ext_unknown" not in html
    assert "ext_z" not in mark
    # Falsifier/refutation vocabulary is never front-facing (operator 2026-07-27).
    for banned in ("falsifier", "refuted", "证伪"):
        assert banned not in mark


def test_the_absence_mark_suppresses_itself_when_the_whole_shelf_is_unmeasured():
    """DESIGN_DOCTRINE Law 4 — "a constant belongs in the footer, once".

    The mark identifies WHICH picks are unmeasured, and identification is worth a chip
    only while the answer is *some of them*.  On an all-unknown shelf it degenerates
    into the same chip on every card, so it suppresses and the footnote — which is
    already stating the count — carries the whole story.  This is the rule that keeps
    the HK board (no extension wiring at all, so 100% unknown) from turning every card
    into noise, and it is keyed on the data, not on the market."""
    vm, _ = _ext_vm("all")
    html = _render(vm)
    assert _NCK_MARK not in html, "an all-unknown shelf must not mark every card"
    # ... and the footer is doing the work, so nothing goes dark.
    footnote = _footnote(html)
    featured = sum(1 for r in vm["us_standouts"]["buy"] if r.get("featured"))
    assert f"We could not check whether {featured} featured names had already run too far." in footnote
    assert f"其中 {featured} 只精选股票无法检查是否已经涨得太远。" in footnote


def test_the_absence_mark_is_the_only_hollow_chip_in_the_row():
    """The form IS the message: every other mark is a filled tint stating something
    that IS true of the name; this one marks a slot where a reading should have been,
    so it is drawn as the outline of a chip.  Dashed is borrowed from .pv-trg-soon
    ("pending, not settled"), so the card gains no new hue and no new idiom."""
    vm, _ = _ext_vm("mixed")
    html = _render(vm)
    rule = html[html.find(".pv-mk-nck{"):]
    rule = rule[:rule.find("}") + 1]
    assert "background:transparent" in rule, "the missing fill is the whole idea"
    assert "border-style:dashed" in rule
    assert "color:var(--muted)" in rule
    # Sentence case is load-bearing — feat/new/adj/blow are uppercase badges, this is
    # a note.  It must inherit .pv-mk-i's untransformed case.
    assert "text-transform" not in rule
    # No new colour: the featured aura is where this card spends its boldness.
    for hue in ("--warn", "--info", "--pv-buy", "--up", "--down"):
        assert hue not in rule


def test_the_legacy_board_grows_no_absence_mark():
    """Fail-soft: the pre-priority artifact carries no `featured` and no `ext_unknown`,
    and must render byte-identically to before this lane."""
    assert _NCK_MARK not in _legacy_html()


# --------------------------------------------------------------------------- #
# G0.6 — stage filter chips + NEW badge
# --------------------------------------------------------------------------- #

def test_filter_chip_row_renders_real_buttons_with_counts_and_aria():
    vm = _priority_vm()
    html = _render(vm)
    assert '<div class="pbf-bar" id="us-stage-filter" role="group"' in html
    assert '<button type="button" data-stagepick="all" aria-pressed="true">' in html
    for key in ("live", "setting_up", "ran", "blocked"):
        assert f'<button type="button" data-stagepick="{key}" aria-pressed="false"' in html
    # Counts are computed from rendered rows, and the ran chip spans BOTH arrays.
    board = vm["us_standouts"]["buy"]
    n_ran = len([r for r in board if r["stage"] == "ran"]) + len(vm["us_standouts"]["ran"])
    assert f'<span class="pbf-n">{n_ran}</span>' in html
    assert f'<span class="pbf-n">{len(board) + len(vm["us_standouts"]["ran"])}</span>' in html
    assert '<span class="pbf-live" id="us-stage-status" aria-live="polite">' in html


def test_filter_css_reveals_matching_cards_hidden_by_the_show_more_collapse():
    """Without the reveal half, filtering to a bucket below the show-more fold (Blocked
    always is) would show an empty board."""
    html = _priority_html()
    assert '#us-standouts[data-stagef="blocked"]    [data-stage]:not([data-stage="blocked"])' in html
    assert '#us-standouts[data-stagef="blocked"]    .sm-hidden[data-stage="blocked"]' in html
    assert '#us-standouts[data-stagef]:not([data-stagef="all"]) .nb-grid-section .sm-bar' in html


def test_filter_chips_meet_the_mobile_touch_target():
    html = _priority_html()
    assert "@media (max-width: 680px) { .pbf-bar button { min-height: 44px;" in html


def test_new_badge_renders_only_on_fresh_rows():
    vm = _priority_vm()
    html = _render(vm)
    fresh = [r["ticker"] for r in vm["us_standouts"]["buy"] if r["new"]]
    assert fresh, "fixture must contain at least one NEW row"
    assert '<span class="pv-mk-i pv-mk-new"' in html
    assert '<span class="l-en">New</span><span class="l-zh">新</span>' in html
    for ticker in fresh:
        assert "pv-mk-new" in _card_markup(html, ticker)
    stale = next(r["ticker"] for r in vm["us_standouts"]["buy"] if not r["new"])
    assert "pv-mk-new" not in _card_markup(html, stale)


def test_table_payload_carries_days_since_signal():
    """stocktable.js already had a NEW-dot path keyed on this field; it was dead on US
    because the payload never emitted it."""
    html = _priority_html()
    assert '"days_since_signal":' in html


# --------------------------------------------------------------------------- #
# G0.4 — ran section
# --------------------------------------------------------------------------- #

def test_ran_section_renders_muted_rows_with_the_no_entry_stance():
    vm = _priority_vm()
    html = _render(vm)
    assert '<div class="pbr" data-stage="ran">' in html
    assert ('<div class="pbr-s">'
            '<span class="l-en">Recently fired — the entry window has passed; '
            'wait for the next setup.</span>') in html
    assert "信号已触发 — 入场窗口已过，等待下一个买点。" in html
    first = vm["us_standouts"]["ran"][0]
    assert f'<span class="pbr-tk">{first["ticker"]}</span>' in html


def test_ran_age_reads_sessions_since_not_ticks():
    """`ticks` counts 3-day-grid buckets and runs ~3x short of the real session age
    (MSFT: ticks=4, sessions_since=9).  Rendering ticks would print a wrong number —
    the fixture keeps the two deliberately different so this cannot pass by accident."""
    vm = _priority_vm()
    html = _render(vm)
    first = vm["us_standouts"]["ran"][0]
    assert first["sessions_since"] != first["ticks"], "fixture lost its distinguishing gap"
    assert f'fired {first["sessions_since"]} sessions ago' in html
    assert f'{first["sessions_since"]}个交易日前触发' in html
    assert f'fired {first["ticks"]} sessions ago' not in html
    # …and a partial artifact with only `ticks` still renders rather than going blank.
    ran = [{k: v for k, v in r.items() if k != "sessions_since"} for r in vm["us_standouts"]["ran"]]
    vm["us_standouts"] = dict(vm["us_standouts"], ran=ran)
    assert f'fired {first["ticks"]} sessions ago' in _render(vm)


def test_ran_theme_confirmed_rows_get_the_warm_treatment():
    html = _priority_html()
    assert '<a class="pbr-r pbr-warm" href="stock.html#' in html
    assert '<span class="pbr-wl"><span class="l-en">Theme just confirmed — watch for the next entry' in html
    assert "主题刚确认 — 关注下一个买点" in html
    assert ".pbr-r.pbr-warm { border-color: color-mix(in srgb, var(--warn)" in html


# --------------------------------------------------------------------------- #
# B3 — approximate session ages carry the ≈ marker AND say why
#
# The engine emits `anchor` on every ran row: "marker" when the age was measured
# from that row's own buy-marker date, "approx" when it was worked back from the
# fresh-bar window instead.  Printed identically, an estimate reads as a
# measurement — the same class of wrong number the `ticks`/`sessions_since` note
# above this section exists to prevent.  Two states only: an absent `anchor`
# (every artifact older than the engine lane) reads as "marker".
# --------------------------------------------------------------------------- #

_APPROX_TIP_EN = 'the age is counted back from its recent bars'
_APPROX_TIP_ZH = '此处的交易日数由近期K线倒推得出'


def _ran_row_markup(html: str, ticker: str) -> str:
    """One ran-lane row, from its own <a> to the next — so an assertion about the
    approx row can never be satisfied by a marker row's markup, or vice versa."""
    anchor = html.find(f'<span class="pbr-tk">{ticker}</span>')
    assert anchor != -1, f"ran row for {ticker} not found"
    start = html.rfind('<a class="pbr-r', 0, anchor)
    assert start != -1
    end = html.find('<a class="pbr-r', start + 10)
    return html[start:end if end != -1 else html.find("</div>", anchor)]


def test_ran_row_markup_helper_isolates_one_row():
    """Guard the guard: a slicer that returned the whole ran list would make every
    per-row ≈ assertion below pass vacuously in both directions."""
    vm = _priority_vm()
    html = _render(vm)
    approx, marker = _approx_and_marker_tickers(vm)
    row = _ran_row_markup(html, approx)
    assert f'<span class="pbr-tk">{approx}</span>' in row
    assert f'<span class="pbr-tk">{marker}</span>' not in row


def _approx_and_marker_tickers(vm: dict) -> tuple[str, str]:
    rows = vm["us_standouts"]["ran"]
    approx = next(r["ticker"] for r in rows if r["anchor"] == "approx")
    marker = next(r["ticker"] for r in rows if r["anchor"] == "marker")
    return approx, marker


def test_approx_ran_age_prints_the_marker_and_discloses_why():
    vm = _priority_vm()
    html = _render(vm)
    approx_tk, _ = _approx_and_marker_tickers(vm)
    row = next(r for r in vm["us_standouts"]["ran"] if r["ticker"] == approx_tk)
    markup = _ran_row_markup(html, approx_tk)
    n = row["sessions_since"]
    # ≈ sits on the FIGURE, not the sentence — both languages.
    assert f'fired ≈{n} sessions ago' in markup
    assert f'≈{n}个交易日前触发' in markup
    # …and the reason is disclosed in plain words on the row's own hover, bilingually.
    assert _APPROX_TIP_EN in markup and _APPROX_TIP_ZH in markup
    assert 'data-tip-en="≈ means' in markup


def test_marker_ran_age_prints_no_marker_and_no_disclosure():
    """The other half of the guard: a one-directional test would pass with ≈ stamped
    on every row, which would disclose nothing and mistrust an exact number."""
    vm = _priority_vm()
    html = _render(vm)
    _, marker_tk = _approx_and_marker_tickers(vm)
    row = next(r for r in vm["us_standouts"]["ran"] if r["ticker"] == marker_tk)
    markup = _ran_row_markup(html, marker_tk)
    n = row["sessions_since"]
    assert f'fired {n} sessions ago' in markup
    assert f'fired ≈{n} sessions ago' not in markup
    assert "≈" not in markup
    assert _APPROX_TIP_EN not in markup and _APPROX_TIP_ZH not in markup


def test_ran_row_without_anchor_reads_as_a_marker_row():
    """Fail-soft for every artifact older than the engine lane: a missing `anchor`
    renders exactly as it does today — no ≈, no hover, and NO third state."""
    vm = _priority_vm()
    ran = [{k: v for k, v in r.items() if k != "anchor"} for r in vm["us_standouts"]["ran"]]
    vm["us_standouts"] = dict(vm["us_standouts"], ran=ran)
    html = _render(vm)
    section = html[html.find('<div class="pbr" data-stage="ran">'):html.find('<p class="pb-fn">')]
    assert f'fired {ran[0]["sessions_since"]} sessions ago' in section   # rows DID render
    assert "≈" not in section
    assert _APPROX_TIP_EN not in section and _APPROX_TIP_ZH not in section


def test_ran_section_absent_when_the_artifact_carries_no_ran_array():
    vm = _priority_vm()
    vm["us_standouts"] = dict(vm["us_standouts"])
    vm["us_standouts"].pop("ran")
    html = _render(vm)
    assert '<div class="pbr" data-stage="ran">' not in html
    assert '<div class="nb-stage-hd sg-live"' in html    # rest of the surface intact


# --------------------------------------------------------------------------- #
# G0.5 — theme linkage without a duplicate Prophet mini-strip
# --------------------------------------------------------------------------- #

def test_prophet_does_not_repeat_the_theme_tape_above_its_cards():
    """Theme membership remains on the cards and in the full Theme Heat panel.
    The retired mini-strip duplicated that context, and its regime-age tail made a
    mature theme read like stale data inside an entry-timing board."""
    vm = _priority_vm()
    html = _render(vm)
    assert '<div class="pbt">' not in html
    assert "Themes in favour" not in html
    assert "turned 90d ago" not in html
    assert '<div class="pbf-bar" id="us-stage-filter"' in html   # the rest is intact
    assert '<span class="pv-mk-i pv-mk-theme"' in html     # card context survives


def test_earnings_candidates_stay_visible_below_the_actionable_cards():
    vm = _priority_vm()
    vm["us_standouts"] = dict(
        vm["us_standouts"],
        earnings_blackout_note={"count": 3, "tickers": ["UAMY", "LAC", "YETI"]},
    )
    html = _render(vm)
    watch = html[html.index('<div class="nb-ewatch"'):html.index('</div>', html.index('<div class="nb-ewatch"')) + 6]
    assert html.index('<div class="nb-ewatch"') > html.index('<div class="nbgrid"')
    assert '<span class="l-en">Earnings watch</span>' in watch
    for ticker in ("UAMY", "LAC", "YETI"):
        assert f'<a href="stock.html#{ticker}">{ticker}</a>' in watch
    assert "Prophet waits through the report date" in watch
    assert "setups suppressed today" not in html.lower()
    assert '<div class="nb-eb-note"' not in html
    assert "W1.5" not in watch and "adjudicated" not in watch and "hygiene" not in watch


def test_earnings_watch_names_do_not_reappear_as_fresh_triggers():
    """A waiting name cannot simultaneously be presented as an actionable trigger."""
    vm = _priority_vm()
    vm["us_standouts"] = dict(
        vm["us_standouts"],
        earnings_blackout_note={"count": 1, "tickers": ["UAMY"]},
    )
    vm["top_setups"] = {
        "buy": [_setup_row(ticker="UAMY"), _setup_row(ticker="ZORB")],
        "eligible": 2,
    }
    html = _render(vm)
    assert '<span class="ts-tk">ZORB</span>' in html
    assert '<span class="ts-tk">UAMY</span>' not in html
    assert html.count('href="stock.html#UAMY"') == 1  # the Earnings watch link


def test_all_earnings_window_triggers_get_an_honest_empty_state():
    vm = _priority_vm()
    vm["us_standouts"] = dict(
        vm["us_standouts"],
        earnings_blackout_note={"count": 1, "tickers": ["UAMY"]},
    )
    vm["top_setups"] = {"buy": [_setup_row(ticker="UAMY")], "eligible": 1}
    html = _render(vm)
    assert "Today's fresh signals are in Earnings watch while their reports are due." in html
    assert "Every actionable signal is already on the board above" not in html


def test_theme_chip_and_demoted_lane_chip_ride_the_card_marks_row():
    html = _priority_html()
    assert '<div class="pv-mk">' in html
    assert '<span class="pv-mk-i pv-mk-theme"' in html
    assert '<span class="pv-mk-i pv-mk-lane"' in html
    # the lane survives DEMOTED, not deleted
    assert '<span class="l-en">Bottoming</span><span class="l-zh">筑底</span>' in html


def test_watch_lane_is_not_chipped_on_the_priority_path():
    """`watch` names TIMING, and timing is the stage bucket's job now.  Chipped, it put
    two stances on one card — a live featured pick reading "★ Featured · Watch"."""
    vm = _priority_vm()
    board = [dict(r, lane="watch") for r in vm["us_standouts"]["buy"]]
    vm["us_standouts"] = dict(vm["us_standouts"], buy=board)
    html = _render(vm)
    assert '<span class="pv-mk-i pv-mk-lane"' not in html
    assert '<span class="pv-mk-i pv-mk-feat"' in html      # the rest of the row is intact
    # …but the LEGACY path still groups by it, heading and all.
    legacy = _base_vm()
    rich = _rich_rows()
    legacy["us_standouts"] = {"buy": [dict(r, lane="watch") for r in rich],
                              "eligible": len(rich)}
    # Counted from the fixture, never a literal: the heading prints the ROW count, so a
    # test that hardcodes it goes red for the fixture growing rather than the lane
    # heading breaking (it did, the night the basing row was added).
    assert f'<span class="l-en">Watch · {len(rich)}</span>' in _render(legacy)


def test_leaders_table_gains_a_theme_column_only_when_rows_carry_themes():
    vm = _priority_vm()
    html = _render(vm)
    assert '<th class="c-theme" data-tip-en="The in-favour basket this name belongs to' in html
    assert '<span class="l-en">theme</span><span class="l-zh">主题</span>' in html
    assert '<span class="pv-mk-i pv-mk-warm"' in html    # the theme_confirmed leader

    plain = [dict(r) for r in vm["us_standouts"]["leaders"]]
    for row in plain:
        row.pop("theme", None)
        row.pop("theme_confirmed", None)
    vm["us_standouts"] = dict(vm["us_standouts"], leaders=plain)
    html2 = _render(vm)
    assert '<th class="c-theme" data-tip-en="The in-favour basket this name belongs to' not in html2
    assert '<span class="ts-tk">NOW</span>' in html2     # the table itself still ships


# --------------------------------------------------------------------------- #
# G0.7 — honest framing wherever the score surfaces
# --------------------------------------------------------------------------- #

def test_priority_score_replaces_the_edge_slot_with_the_no_forecast_framing():
    """The Priority slot kept its label but LOST its hover card (operator 2026-08-05 —
    the per-card popovers covered the neighbouring cards).  The framing it carried is
    honesty copy, so it may not vanish with it: it now sits in the board footnote,
    stated once instead of on all 40 cards."""
    html = _priority_html()
    assert '<span class="l-en">Priority</span><span class="l-zh">优先级</span>' in html
    assert "not more likely to win" in _footnote(html)
    assert "并不代表更容易获胜" in _footnote(html)


def test_the_card_chips_carry_no_hover_cards():
    """The removal itself, pinned.  Verb / Priority / ★ Featured / NEW are read at a
    glance and each restated what the card already shows; their popovers overhung the
    card and covered its neighbour.  A tooltip re-added to any of them is a regression,
    so this asserts the ABSENCE at the one place all four are rendered."""
    card = _card_markup(_priority_html(), "AAPL")
    for probe in ('class="pv-chip" data-tip-en',
                  'class="pv-edge" data-tip-en',
                  'pv-mk-feat" data-tip-en',
                  'pv-mk-new" data-tip-en'):
        assert probe not in card, f"{probe} — the chip grew a hover card back"
    # the ⚠ caution popover is the ONE the operator kept: it carries per-name detail
    # that appears nowhere else on the card.
    assert "pv-cau" in _priority_html()


def test_legacy_rows_keep_the_edge_label_untouched():
    html = _legacy_html()
    assert '<span class="l-en">Edge</span><span class="l-zh">优势</span>' in html
    assert '<span class="l-en">Priority</span>' not in html


def test_board_carries_the_plain_language_priority_footnote_once():
    html = _priority_html()
    assert html.count('<p class="pb-fn">') == 1
    foot = _footnote(html)
    assert "Higher Priority means the setup is more ready today" in foot
    assert "not more likely to win" in foot
    assert "signal 30%" not in foot and "us_prophet_v1" not in foot


def test_stage_heading_tips_explain_priority_in_plain_language():
    html = _priority_html()
    assert "Higher Priority means the setup is more ready today, not more likely to win." in html
    assert "优先级越高，表示今天越接近可操作，并不代表更容易获胜。" in html
    assert "awaiting confluence" not in html


# --------------------------------------------------------------------------- #
# M1 — when the runway leg is dead, the surface that advertises its weight says so
#
# The runway leg contributed 0 on 71 of 71 rows of the 07-31 board because the
# extension reading it scores (ext_z) never reached a row: the builder handed
# `extension_signals` one close panel mixing the equity and 24/7 crypto calendars, so
# on any non-session build date every equity read NaN.  A weight advertised while its
# input is dark is an overclaim, and it is printed in exactly two places — the board
# footnote and the card's Priority tooltip.
#
# Both states are tested here against SYNTHETIC coverage, so this suite is era-neutral:
# the claim is COUNTED FROM THE ARTIFACT (`ranking.component_coverage`), never a
# literal, and the night the evidence is wired the note switches itself off (see the
# kill-switch test below).  A hardcoded sentence would outlive the null it discloses.
# --------------------------------------------------------------------------- #

_RW_EN = "Room to run could not be checked for "
_RW_ZH = "今晚无法检查"
_RW_TAIL_EN = "so that part adds no points"
_RW_TAIL_ZH = "因此这一项不加分"


def _coverage_vm(runway: dict | None) -> dict:
    vm = _priority_vm()
    ranking = {"component_coverage": {"runway": runway}} if runway is not None else {}
    vm["us_standouts"] = dict(vm["us_standouts"], ranking=ranking)
    return vm


def _footnote(html: str) -> str:
    start = html.find('<p class="pb-fn">')
    assert start != -1, "the board footnote did not render"
    return html[start:html.find("</p>", start)]


def test_dead_runway_leg_is_disclosed_in_the_footnote():
    """Both languages, with the count read off the artifact.  This used to be pinned in
    TWO places — the footnote and the per-card Priority tooltip.  The tooltip is gone
    (operator 2026-08-05), which leaves the footnote as the single home; a board-wide
    constant repeated on every card was a doctrine Law 4 violation anyway."""
    html = _render(_coverage_vm({"nonzero": 0, "n": 71}))
    for place in (_footnote(html),):
        assert _RW_EN + "all 71 names" in place
        assert _RW_TAIL_EN in place
        assert _RW_ZH + "全部 71 只股票" in place
        assert _RW_TAIL_ZH in place
        # no English left inside the ZH half (bilingual parity law)
        zh = place[place.find('l-zh') if 'l-zh' in place else place.find('data-tip-zh'):]
        assert "Runway currently contributes" not in zh


def test_runway_disclosure_reads_the_artifact_and_stops_when_the_leg_scores():
    """The kill switch: a nightly where the extension evidence IS wired reports a
    non-zero count, and the note must disappear from BOTH places rather than
    outliving the null.  Without this half the disclosure is a hardcoded sentence."""
    html = _render(_coverage_vm({"nonzero": 12, "n": 71}))
    for place in (_footnote(html),):
        assert _RW_EN not in place
        assert _RW_ZH not in place
        assert _RW_TAIL_ZH not in place
    assert "Higher Priority means the setup is more ready today" in _footnote(html)


def test_runway_disclosure_without_the_coverage_key_claims_no_count():
    """Every artifact predating the coverage key IS the measured state, so the note
    stays on — but it may not print a count it never read."""
    html = _render(_coverage_vm(None))
    for place in (_footnote(html),):
        assert _RW_EN + "these names" in place
        assert _RW_ZH + "这些股票" in place
        assert "71" not in place.split(_RW_EN)[1].split(".")[0]


def test_runway_disclosure_never_reaches_the_legacy_board():
    """The legacy path prints no formula at all, so it must grow no disclosure."""
    html = _legacy_html()
    assert _RW_EN not in html and _RW_ZH not in html


# --------------------------------------------------------------------------- #
# m5 — featured stays lossless without exposing engine language
# --------------------------------------------------------------------------- #

def test_featured_shelf_is_explained_without_engine_language():
    html = _priority_html()
    foot = _footnote(html)
    assert "Featured highlights up to 12 of the most ready names" in foot
    assert "no more than four per sector" in foot
    assert "absolute floor" not in foot and "admission limit" not in foot


def test_featured_shelf_does_not_misstate_the_lossless_board_depth():
    html = _footnote(_priority_html())
    assert "every qualifying name still appears on this board" in html
    assert "所有合格股票仍会保留在本榜" in html


# --------------------------------------------------------------------------- #
# m6 — bull_days == 0 is a theme that turned TODAY, not a missing age
#
# Truthiness deleted the age chip on exactly the freshest reading.  All three sites
# are pinned together: a fix applied to one conditional and not its twins is the
# recurring shape of this defect.
# --------------------------------------------------------------------------- #

def _zero_bull_days_vm() -> dict:
    """Every theme turned TODAY — strip, ran lane and leaders table at once."""
    vm = _priority_vm()
    art = dict(vm["us_standouts"])
    art["themes_in_favour"] = [dict(t, bull_days=0)
                               for t in art["themes_in_favour"]]
    for key in ("buy", "ran", "leaders"):
        rows = []
        for row in art[key]:
            row = dict(row)
            if row.get("theme"):
                row["theme"] = dict(row["theme"], bull_days=0)
            rows.append(row)
        art[key] = rows
    vm["us_standouts"] = art
    return vm


def test_ran_lane_theme_note_reads_today_at_zero_bull_days():
    html = _render(_zero_bull_days_vm())
    assert "watch for the next entry (turned today)" in html
    assert "关注下一个买点（今日转向）" in html
    assert "(turned 0d ago)" not in html and "（0天前转向）" not in html


def test_nonzero_bull_days_still_prints_the_age():
    """The other direction: the None-test must not swallow real ages."""
    html = _priority_html()
    assert "turned 3d ago" in html and "3天前转向" in html
    assert "turned today" not in html


# --------------------------------------------------------------------------- #
# m20 — no CSS for markup nothing emits
# --------------------------------------------------------------------------- #

def test_no_dead_empty_bucket_css_ships():
    """`.pbf-empty` was styled but never emitted by any template, macro or script,
    and it cannot be: a bucket with zero rows renders no filter chip, so there is no
    way to filter into one.  Dead CSS on a stylesheet that ships on every render
    reads at review like a shipped feature.

    Asserted as CSS/markup shapes, not the bare token: the removal note left in the
    stylesheet names the class in prose, and a token test would fail on the very
    comment that records the fix."""
    for html in (_priority_html(), _legacy_html()):
        assert not re.search(r"\.pbf-empty\s*[\[{,]", html), "the dead rule is back"
        assert not re.search(r'class="[^"]*\bpbf-empty\b', html)
    # …and the assertion is not vacuous: the filter rules it sat among still ship.
    assert ('#us-standouts[data-stagef="blocked"]    [data-stage]:not([data-stage="blocked"])'
            in _priority_html())


# --------------------------------------------------------------------------- #
# Degradation + i18n hygiene
# --------------------------------------------------------------------------- #

def test_rows_with_no_stage_render_last_never_above_a_live_row():
    """A row the engine forgot to stamp (or a stage newer than this template) must stay
    visible — but below every classified bucket, so G0.1's ordering rule still holds."""
    vm = _priority_vm()
    board = [dict(r) for r in vm["us_standouts"]["buy"]]
    board[0].pop("stage")
    board[0]["ticker"] = "STRAY"
    vm["us_standouts"] = dict(vm["us_standouts"], buy=board)
    html = _render(vm)
    assert 'data-ticker="STRAY"' in html
    assert html.find('data-ticker="STRAY"') > html.find('<div class="nb-stage-hd sg-blocked"')


def test_degraded_vm_with_lane_none_still_renders_the_priority_board():
    vm = _priority_vm()
    board = [dict(r, lane=None) for r in vm["us_standouts"]["buy"]]
    vm["us_standouts"] = dict(vm["us_standouts"], buy=board)
    html = _render(vm)
    assert len(html) > 50_000
    assert '<div class="nb-stage-hd sg-live"' in html
    assert '<span class="pv-mk-i pv-mk-lane"' not in html   # no lane -> no lane chip


def test_unmarked_cards_still_reserve_the_marks_slot_on_the_priority_path():
    """The card macro's founding contract is that the layout never moves between cards.
    A card with nothing to mark used to pull its tracker and zone rows ~18px up, out of
    line with its grid-row neighbours — visible on the live board (CLF vs SFNC)."""
    vm = _priority_vm()
    board = [{k: v for k, v in r.items() if k not in ("theme", "lane")} for r in vm["us_standouts"]["buy"]]
    board = [dict(r, featured=False, new=False, theme_confirmed=False) for r in board]
    vm["us_standouts"] = dict(vm["us_standouts"], buy=board)
    html = _render(vm)
    assert '<div class="pv-mk"></div>' in html, "the empty marks slot must still render"
    assert "min-height:18px" in html
    # …and the LEGACY path emits no slot at all, so an old artifact is byte-identical.
    assert '<div class="pv-mk"' not in _legacy_html()


def test_no_translated_text_in_title_attributes_on_the_new_surface():
    """The l-en/l-zh mechanism cannot operate inside an attribute (check_title_i18n)."""
    html = _priority_html()
    for value in re.findall(r'title\s*=\s*"([^"]*)"', html):
        assert not re.search(r"[一-鿿]", value), f"CJK leaked into a title attribute: {value!r}"


def test_macro_mode_is_unaffected_by_the_priority_surface():
    """us_stocks owns this board; macro.html must not grow a filter bar."""
    html = _render(_priority_vm(), mode="macro")
    assert '<div class="pbf-bar" id="us-stage-filter"' not in html
    assert len(html) > 50_000


def test_both_shapes_render_in_both_modes_without_raising():
    for vm in (_priority_vm(), {**_base_vm(), "us_standouts": {"buy": _rich_rows(), "eligible": 17}}):
        for mode in ("macro", "stocks"):
            assert len(_render(vm, mode)) > 50_000


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

def _card_markup(html: str, ticker: str) -> str:
    """The one card's markup, from its opening <a> to the next card boundary — so a
    per-row assertion can never be satisfied by a different row's markup."""
    start = html.rfind("<a class=\"pvcard", 0, html.find(f'data-ticker="{ticker}"'))
    assert start != -1, f"card for {ticker} not found"
    end = html.find("<a class=\"pvcard", start + 10)
    return html[start:end if end != -1 else len(html)]


def test_card_markup_helper_isolates_one_card():
    """Guard the guard: if the slicer ever returned the whole document, every
    per-row assertion above would pass vacuously."""
    html = _priority_html()
    card = _card_markup(html, "AAPL")
    assert 'data-ticker="AAPL"' in card
    assert 'data-ticker="NXE"' not in card
    assert len(card) < len(html) / 4


assert isinstance(jinja2.__version__, str)  # import used by the harness env
