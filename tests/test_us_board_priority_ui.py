"""Rendered-HTML contract for the US board priority display layer (us_prophet_v1).

Program: research/PROPHET_BOARD_PRIORITY_ENGINE_MASTERPLAN_BY_FABLE.md
Gates covered here: G0.1 (priority order + stage buckets), G0.2 (featured glow),
G0.4 (ran lane), G0.5 (theme chips + themes-in-favour strip), G0.6 (stage filter
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

from tests.test_dashboard_template_render import _base_vm, _board_row, _env

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
_STAGE_ORDER = ["live", "setting_up", "ran", "blocked"]

# Three in-favour baskets, mirroring the shape §3.6's loader stamps onto rows.
_THEMES = [
    {"id": "ai_software", "name": "AI software", "name_zh": "AI软件", "rank": 3, "reco": "accumulate"},
    {"id": "non_ai_software", "name": "Software", "name_zh": "软件", "rank": 4, "reco": "accumulate"},
    {"id": "power_grid", "name": "Power & grid", "name_zh": "电力与电网", "rank": 6, "reco": "enter"},
]


def _stage_of(row: dict) -> str:
    if (row.get("label") or "").upper() == "DOWNTREND":
        return "blocked"
    status = ((row.get("entry_signal") or {}).get("status")) or ""
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
    # the green aura never sits on a lighter `near` card.
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
    """A board wide enough to fill all four stage buckets, with sectors that make the
    featured sector-cap bite and one DOWNTREND row that must land in `blocked`."""
    spec = [
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
    for key in ("live", "setting_up", "ran", "blocked"):
        needle = f'<div class="nb-stage-hd sg-{key}" data-stage="{key}"'
        idx = html.find(needle)
        assert idx != -1, f"stage heading for {key!r} missing"
        positions.append(idx)
    assert positions == sorted(positions), f"stage headings out of order: {positions}"


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
    assert '<div class="nb-lane-hd">' in html            # legacy headings still render
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
    and the zh-safe hue (never --up, which flips to red under html[data-lang=zh])."""
    html = _priority_html()
    assert ".pvcard.pv-featured{background:color-mix(in srgb,var(--pv-buy)" in html
    assert 'html[data-theme="light"] .pvcard.pv-featured{background:color-mix(' in html
    assert ".pvcard.pv-featured:hover{" in html          # hover ADDS lift, never replaces the aura
    assert 'html[data-theme="light"] .pvcard.pv-featured:hover{' in html
    glow = html[html.find(".pvcard.pv-featured{"):html.find(".pv-chart{")]
    assert "animation" not in glow and "@keyframes" not in glow, "featured glow must not animate"
    assert "var(--up)" not in glow, "the glow must use --pv-buy; --up flips to red in zh"


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
# G0.5 — theme linkage
# --------------------------------------------------------------------------- #

def test_theme_strip_lists_top_three_themes_with_their_board_tickers():
    vm = _priority_vm()
    html = _render(vm)
    assert '<div class="pbt">' in html
    assert '<span class="l-en">Themes in favour</span><span class="l-zh">主题风向</span>' in html
    assert '<span class="l-en">AI software</span><span class="l-zh">AI软件</span>' in html
    strip = html[html.find('<div class="pbt">'):html.find('<div class="pbf-bar"')]
    rows = re.findall(r'<div class="pbt-r">', strip)
    assert len(rows) == 3, f"the strip must show at most the top three themes, got {len(rows)}"
    # highest-ranked theme first (rank 3 AI software before rank 6 Power & grid)
    assert strip.find("AI software") < strip.find("Power & grid")
    # A theme with no name on THIS board is dropped, not padded in to look fuller.
    assert "Shipping" not in strip
    # …and off-board basket members never leak into a board strip.
    board = {r["ticker"] for r in vm["us_standouts"]["buy"]}
    for ticker in re.findall(r"<span>([A-Z.\-]{1,6})</span>", strip):
        assert ticker in board, f"{ticker} is a basket member, not a name on this board"
    assert re.search(r"<span>[A-Z]", strip), "the strip printed no tickers at all"
    # bull_days rides as a quiet tail where the engine supplies it
    assert '<span class="l-en">turned 5d ago</span><span class="l-zh">5天前转向</span>' in strip


def test_theme_strip_falls_back_to_row_grouping_without_themes_in_favour():
    """A partial artifact (rows stamped, top-level list missing) still gets a strip."""
    vm = _priority_vm()
    art = dict(vm["us_standouts"])
    art.pop("themes_in_favour")
    vm["us_standouts"] = art
    html = _render(vm)
    strip = html[html.find('<div class="pbt">'):html.find('<div class="pbf-bar"')]
    assert '<div class="pbt-r">' in strip
    assert '<span class="l-en">AI software</span><span class="l-zh">AI软件</span>' in strip


def test_theme_strip_absent_when_no_favoured_theme_has_a_name_on_the_board():
    """The sparse case is real — theme membership on the buy lane is 2-of-71 on the
    first live artifact.  The strip shrinks and then disappears; it never pads."""
    vm = _priority_vm()
    board = [{k: v for k, v in r.items() if k != "theme"} for r in vm["us_standouts"]["buy"]]
    vm["us_standouts"] = dict(
        vm["us_standouts"], buy=board,
        themes_in_favour=[{"id": "shipping", "name": "Shipping", "name_zh": "航运",
                           "rank": 9, "reco": "accumulate", "tickers": ["ZIM", "MATX"]}])
    html = _render(vm)
    assert '<div class="pbt">' not in html
    assert '<div class="pbf-bar" id="us-stage-filter"' in html   # the rest is intact


def test_theme_strip_absent_when_no_row_carries_a_theme():
    """Absence is scoped to the whole panel here: board, ran AND leaders lose their
    themes, so a stray chip from any of the three lanes would fail this."""
    vm = _priority_vm()
    art = dict(vm["us_standouts"])
    art.pop("themes_in_favour")
    for key in ("buy", "ran", "leaders"):
        stripped = []
        for row in art[key]:
            row = dict(row)
            row.pop("theme", None)
            row.pop("theme_confirmed", None)
            stripped.append(row)
        art[key] = stripped
    vm["us_standouts"] = art
    html = _render(vm)
    assert '<div class="pbt">' not in html
    assert '<div class="nb-stage-hd sg-live"' in html
    assert '<span class="pv-mk-i pv-mk-theme"' not in html
    assert '<div class="pbr" data-stage="ran">' in html   # the ran lane itself survives


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
    legacy["us_standouts"] = {"buy": [dict(r, lane="watch") for r in _rich_rows()], "eligible": 17}
    assert '<span class="l-en">Watch · 17</span>' in _render(legacy)


def test_leaders_table_gains_a_theme_column_only_when_rows_carry_themes():
    vm = _priority_vm()
    html = _render(vm)
    assert '<th data-tip-en="The in-favour basket this name belongs to' in html
    assert '<span class="l-en">theme</span><span class="l-zh">主题</span>' in html
    assert '<span class="pv-mk-i pv-mk-warm"' in html    # the theme_confirmed leader

    plain = [dict(r) for r in vm["us_standouts"]["leaders"]]
    for row in plain:
        row.pop("theme", None)
        row.pop("theme_confirmed", None)
    vm["us_standouts"] = dict(vm["us_standouts"], leaders=plain)
    html2 = _render(vm)
    assert '<th data-tip-en="The in-favour basket this name belongs to' not in html2
    assert '<span class="ts-tk">NOW</span>' in html2     # the table itself still ships


# --------------------------------------------------------------------------- #
# G0.7 — honest framing wherever the score surfaces
# --------------------------------------------------------------------------- #

def test_priority_score_replaces_the_edge_slot_with_the_no_forecast_tooltip():
    html = _priority_html()
    assert '<span class="l-en">Priority</span><span class="l-zh">优先级</span>' in html
    assert "not a win probability or return forecast." in html
    assert "不是胜率，也不是收益预测。" in html


def test_legacy_rows_keep_the_edge_label_untouched():
    html = _legacy_html()
    assert '<span class="l-en">Edge</span><span class="l-zh">优势</span>' in html
    assert '<span class="l-en">Priority</span>' not in html


def test_board_carries_the_priority_formula_footnote_once():
    html = _priority_html()
    assert html.count('<p class="pb-fn">') == 1
    assert "Priority = signal 30% + entry 25% + edge 25% + runway 10% + setup quality 10%." in html
    assert "并非胜率" in html


def test_stage_heading_tips_disclose_priority_order_not_a_forecast():
    html = _priority_html()
    assert "Priority order, not a return forecast." in html
    assert "这是排序，不是收益预测。" in html


# --------------------------------------------------------------------------- #
# M1 — the runway leg is dead, and the surface that advertises its weight says so
#
# Measured 2026-08-02: the runway leg contributes 0 on 0 of 71 rows, because the
# extension reading it scores (ext_z) is absent everywhere.  The formula is printed
# in exactly two places — the board footnote and the card's Priority tooltip — and
# a weight advertised while its input is dark is an overclaim in both.
#
# The claim is COUNTED FROM THE ARTIFACT (`ranking.component_coverage`), never a
# literal, so the night the evidence is wired the note switches itself off; a
# hardcoded sentence would outlive the null it discloses.
# --------------------------------------------------------------------------- #

_RW_EN = "Runway currently contributes 0 for "
_RW_ZH = "上行空间目前对"
_RW_TAIL_EN = "the extension reading it scores is not wired up yet"
_RW_TAIL_ZH = "它所依据的拉伸幅度数据尚未接入"


def _coverage_vm(runway: dict | None) -> dict:
    vm = _priority_vm()
    ranking = {"component_coverage": {"runway": runway}} if runway is not None else {}
    vm["us_standouts"] = dict(vm["us_standouts"], ranking=ranking)
    return vm


def _footnote(html: str) -> str:
    start = html.find('<p class="pb-fn">')
    assert start != -1, "the board footnote did not render"
    return html[start:html.find("</p>", start)]


def _priority_tip(html: str, ticker: str) -> str:
    """The Priority slot's tooltip on one card — the second of the two places."""
    card = _card_markup(html, ticker)
    idx = card.find('data-tip-en="US Prophet priority')
    assert idx != -1, f"{ticker} carries no Priority tooltip"
    return card[idx:card.find("</div>", idx)]


def test_dead_runway_leg_is_disclosed_in_the_footnote_and_the_card_tooltip():
    """Both places, both languages, with the count read off the artifact."""
    html = _render(_coverage_vm({"nonzero": 0, "n": 71}))
    for place in (_footnote(html), _priority_tip(html, "AAPL")):
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
    for place in (_footnote(html), _priority_tip(html, "AAPL")):
        assert _RW_EN not in place
        assert _RW_ZH not in place
        assert _RW_TAIL_ZH not in place
    # the formula itself is untouched — this is a disclosure, not a weight change
    assert "runway 10%" in _footnote(html)
    assert "上行空间10%" in _footnote(html)


def test_runway_disclosure_without_the_coverage_key_claims_no_count():
    """Every artifact predating the coverage key IS the measured state, so the note
    stays on — but it may not print a count it never read."""
    html = _render(_coverage_vm(None))
    for place in (_footnote(html), _priority_tip(html, "AAPL")):
        assert _RW_EN + "every name" in place
        assert _RW_ZH + "每一只股票" in place
        assert "71" not in place.split(_RW_EN)[1].split(".")[0]


def test_runway_disclosure_never_reaches_the_legacy_board():
    """The legacy path prints no formula at all, so it must grow no disclosure."""
    html = _legacy_html()
    assert _RW_EN not in html and _RW_ZH not in html


# --------------------------------------------------------------------------- #
# m5 — the featured edge gate is an absolute floor, not a rank
# --------------------------------------------------------------------------- #

def test_featured_tip_calls_the_edge_gate_an_absolute_floor():
    """engine ranking_block featured_requirements: "residual alpha at or above zero".
    The old copy ("above the board's midpoint") described a cross-sectional test the
    engine never runs — on a weak board it promised the opposite of the real gate."""
    html = _priority_html()
    assert "edge above zero (an absolute floor)" in html
    assert "优势为正（绝对下限，而非同榜排名）" in html
    assert "above the board’s midpoint" not in html
    assert "above the board's midpoint" not in html
    assert "优势高于本板中位" not in html


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


def test_theme_that_turned_today_keeps_its_age_chip_and_reads_today():
    vm = _zero_bull_days_vm()
    html = _render(vm)
    strip = html[html.find('<div class="pbt">'):html.find('<div class="pbf-bar"')]
    assert '<span class="pbt-age">' in strip, "bull_days == 0 lost the age chip entirely"
    assert '<span class="l-en">turned today</span><span class="l-zh">今日转向</span>' in strip
    assert "turned 0d ago" not in html and "0天前转向" not in html


def test_ran_lane_theme_note_reads_today_at_zero_bull_days():
    html = _render(_zero_bull_days_vm())
    assert "watch for the next entry (turned today)" in html
    assert "关注下一个买点（今日转向）" in html
    assert "(turned 0d ago)" not in html and "（0天前转向）" not in html


def test_nonzero_bull_days_still_prints_the_age():
    """The other direction: the None-test must not swallow real ages."""
    strip = _priority_html()
    assert '<span class="l-en">turned 5d ago</span><span class="l-zh">5天前转向</span>' in strip
    assert "turned today" not in strip


def test_absent_bull_days_still_prints_no_age_chip():
    """None is genuinely unknown and stays silent — the fix must not turn a missing
    age into a claim that the theme turned today."""
    vm = _priority_vm()
    art = dict(vm["us_standouts"])
    art["themes_in_favour"] = [{k: v for k, v in t.items() if k != "bull_days"}
                               for t in art["themes_in_favour"]]
    vm["us_standouts"] = art
    html = _render(vm)
    strip = html[html.find('<div class="pbt">'):html.find('<div class="pbf-bar"')]
    assert '<div class="pbt-r">' in strip          # the strip DID render
    assert '<span class="pbt-age">' not in strip
    assert "turned today" not in strip


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
