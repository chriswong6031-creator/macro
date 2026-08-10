"""Rendered-HTML contract for the HK board priority display layer (hk_prophet_v2 — era bumped 2026-08-03 with the reclaim-veto removal).

Program: research/HK_BOARD_RESURRECTION_MASTERPLAN_BY_FABLE.md
Gates covered here: G1 (the seven witnesses are visible), G2 (leaders lane),
G3 (ran lane, marker-anchored, fail-closed on unknown age), G4 (stage buckets +
filter chips + featured + priority score), G9 (fail-soft on pre-v1 artifacts).

TWO SHAPES, ONE TEMPLATE.  The assertions come in pairs: the new schema must
produce the priority surface, and the OLD schema must still produce the flat
three-lane board with none of it.  A regression that quietly drops the fail-soft
branch would ship a broken board the first night the engine lane degrades and the
artifact on disk comes back without `ran[]` / `leaders[]` / the era stamp.

FROZEN FIXTURES, NEVER THE LIVE ARTIFACT (incident 2026-08-04).  Both shapes are
read from committed fixtures pinned to the 2026-07-31 session — the same session
`tests/fixtures/hk_board_2026_07_31.json` and ``BOARD_ASOF`` are pinned to.  They
used to be read from `site/factordata/hk_standouts.json`, which the NIGHTLY
REWRITES, and that is a fixture with a fuse in it: this suite pins BOTH sides of a
one-way migration, so no single state of a live file can satisfy it.  The nightly
at 94568a91302 crossed the boundary (`ran: None→12`, `leaders: None→15`,
`board_definition: None→hk_prophet_v1`, `as_of: 07-31→08-03`) and took NINE gates
here red in one commit, while the same drift silently SKIPPED nine more in
tests/test_hk_board_rank.py through an ``as_of``-mismatch guard — eighteen dark
gates, and the red ones read as a template regression that had never happened.
The live artifact keeps exactly one, era-agnostic assertion here
(``test_the_live_artifact_still_renders``); everything era-specific reads a
fixture.  A fixture that has to be regenerated is a ledger event: re-pin
``BOARD_ASOF``, the price panel and BOTH json files in the same commit, or the
board is being scored against a session it did not happen in.

ASSERTION STYLE (harness law): every presence/absence assertion targets a full
markup string (`'<div class="nb-stage-hd sg-live"'`), never a bare class token.
pv_css() and this page's own <style> block emit the class SELECTORS as literal
text on every render, so `'nb-stage-hd' in html` is true even when nothing
renders — an absence test written that way is vacuous.

TWO FIXTURES, ONE RULE (adversarial review, 2026-08-03).  `production_fixture()` is
the board the nightly will actually ship — every row scored, staged and ordered by
`engine.hk_board_rank`, no synthetic name anywhere — and it is the ONLY thing the
screenshot pass photographs.  `shapes_fixture()` is that board plus the row shapes
the 2026-07-31 tape does not contain (an `approx` anchor, an unmeasurable move, a
blocked buy card, a featured card), on obviously synthetic 88xx.HK "Sample Holdings"
tickers, and it is never photographed.  The behaviour and copy tests run on the
shapes board; a block of fidelity tests at the foot of this file asserts the
production board is free of anything synthetic, so the two can never blur.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"

# The 2026-07-31 board, frozen.  Same session as the price panel and BOARD_ASOF.
LEGACY_ARTIFACT = FIXTURES / "hk_standouts_2026_07_31.json"
# The nightly's own output — read ONLY by the era-agnostic smoke test, because it
# is rewritten every night and cannot satisfy both halves of the era contract.
LIVE_ARTIFACT = ROOT / "site" / "factordata" / "hk_standouts.json"

_STAGE_ORDER = ["live", "setting_up", "ran", "basing", "blocked"]


# --------------------------------------------------------------------------- #
# Render harness — the whole page, both modes of the contract
# --------------------------------------------------------------------------- #

def _render(setups: dict | None, mode: str = "stocks") -> str:
    """Render templates/hk.html.j2 with a minimal vm and return the HTML."""
    from engine import i18n

    env = Environment(loader=FileSystemLoader(str(ROOT / "templates")), autoescape=False)
    env.globals.update(td=i18n.td, tr=i18n.tr, t=i18n.t)
    return env.get_template("hk.html.j2").render(**_vm(setups, mode))


def _render_source(src: str, setups: dict | None, mode: str = "stocks") -> str:
    """Render an ARBITRARY hk.html.j2 source (e.g. the base branch's) with the same
    vm — the other half of the fail-soft proof."""
    from engine import i18n
    from jinja2 import ChoiceLoader, DictLoader

    env = Environment(
        loader=ChoiceLoader([DictLoader({"hk.html.j2": src}),
                             FileSystemLoader(str(ROOT / "templates"))]),
        autoescape=False)
    env.globals.update(td=i18n.td, tr=i18n.tr, t=i18n.t)
    return env.get_template("hk.html.j2").render(**_vm(setups, mode))


def _vm(setups: dict | None, mode: str) -> dict:
    return {
        "mode": mode,
        "latest": {"date": "2026-07-31", "quad_name": "Goldilocks", "quad": "Q1",
                   "liquidity_overlay": "neutral", "pending_quad": None},
        "actions": {"buy_now": [], "buy_soon": [], "on_the_run": [],
                    "take_profits": [], "hold": [], "avoid": []},
        "setups": setups,
        "gv": None, "market_state": None, "hk_scoreboard": None,
        "sectors_by_ticker": {}, "velocity_desk": None,
        "built": "2026-07-31T00:00:00Z",
        "hk_breadth": None, "hk_full_breadth": None, "benchmark": None,
        "hk_sectors": [], "hk_flow": None, "track_record": None, "hk_ab": None,
        "hk_dispersion": None, "hk_cycles": None, "hk_indicators": None,
        "state_display_json": "{}", "washout_desk": None, "freshness": None,
        "hk_history": None, "hk_news": None, "hk_policy": None, "hk_macro": None,
        "hk_property": None, "hk_alerts": None, "hk_market_drivers": None,
        "hk_conditions": None, "hk_signal_stack": None, "hk_event_calendar": None,
        "hk_context_chips": None, "velocity_desk_picks": None, "hk_lab_button": None,
        "index_health": None, "hk_1d_velocity_desk": None,
    }


def _tags(html: str) -> list[str]:
    """The element stream — open/close tag names in document order.  The fail-soft
    contract is about STRUCTURE, so the comparison ignores text and attributes: CSS
    added inside the existing <style> element must be free, a new element must not."""
    return ["".join(m) for m in re.findall(r"<\s*(/?)([a-zA-Z][a-zA-Z0-9-]*)", html)]


def _without_opt_in_live_change(html: str) -> tuple[str, int]:
    """Collapse the approved live quote enhancement back to the legacy price node.

    The base-branch comparison below guards the HK artifact's fail-soft board shape,
    not cross-market additions explicitly opted into by the caller.  Normalize only
    the new ``pv-quote`` wrapper plus its adjacent ``nb-chg`` node; every other added
    or removed element must still fail the tag-stream comparison.
    """
    return re.subn(
        r'(<span class="pv-ov pv-ovr">)'
        r'<span class="pv-quote">'
        r'(<span class="nb-px pv-px"[^>]*>.*?</span>)'
        r'<span class="nb-chg pv-chg"[^>]*>.*?</span>'
        r'</span>(</span>)',
        r'\1\2\3',
        html,
    )


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

def legacy_artifact() -> dict:
    """The 2026-07-31 board as the nightly shipped it, BEFORE the priority engine.

    Frozen — see the module docstring.  Was `committed_artifact()`, reading the live
    `site/factordata/hk_standouts.json`; the word "committed" was doing the damage,
    because the file is committed AND rewritten nightly, and the second half is the
    one that matters to a fixture.
    """
    return json.loads(LEGACY_ARTIFACT.read_text())


def priority_era_artifact() -> dict:
    """The SAME board carrying the era stamp — the minimal-difference other half.

    The template gates the whole priority layer on
    ``(board_definition or rank_by).startswith('hk_prophet_v')`` and on nothing else
    (templates/hk.html.j2:3532), so stamping that one key is the exact inverse of the
    strip in :func:`test_legacy_render_is_tag_stream_identical_to_the_base_branch`.
    Deriving it here rather than freezing a second 184 KB artifact is what lets the
    pair claim what it claims: the era stamp is the ONLY variable between the two
    renders, so anything the second render gains, it gained from the stamp.
    """
    from engine import hk_board_rank as hbr

    art = dict(legacy_artifact())
    art["board_definition"] = hbr.BOARD_DEFINITION
    return art


def score_buy_lane(rows: list[dict]) -> list[dict]:
    """Stage, score, feature and order a buy pool with the REAL engine.

    Was `hk_priority_overlay` — a hand-rolled restatement of the contract that
    stamped a crc32 stand-in where the priority score goes and re-derived the stage
    from its own copy of the mapping.  A harness that reimplements the thing under
    test can only ever agree with itself, and the numbers it put on the reference
    screenshots were not the board's.  `hk_board_rank.score_rows` is the board.

    `bottom_watch_stage` is passed for the same reason every other argument is: the
    builder passes it (scripts/build_hk_library.py), so a harness that left it out
    would stage a BOTTOM WATCH row into `blocked` and photograph a board the nightly
    does not produce.  It changes nothing on the 2026-07-31 tape — that board carries
    no BOTTOM WATCH row in any lane — which is exactly why the shelf's subject is a
    synthetic one in `shapes_fixture()`.
    """
    from engine import hk_board_rank as hbr

    rows = [dict(r) for r in rows]
    verdict_by = {r["ticker"]: (r.get("signal") or {}) for r in rows if r.get("ticker")}
    entry_by = {r["ticker"]: (r.get("entry_signal") or {})
                for r in rows if r.get("ticker")}
    adv_by = {r["ticker"]: (r.get("_adv63") if r.get("_adv63") is not None
                            else r.get("adv63"))
              for r in rows if r.get("ticker")}
    return hbr.score_rows(rows, verdict_by=verdict_by, entry_by=entry_by,
                          adv_by=adv_by, board_asof=BOARD_ASOF,
                          bottom_watch_stage=hbr.STAGE_BASING)


# The seven witnesses (masterplan §1): every one of them bottomed 2026-06-26 and ran
# +8.7%…+44.0% by 07-31 while the board's eligibility fell 47 → 5.  9961.HK is named
# Trip.com Group here — engine/hk_adr_bridge.py:78 pairs the ticker with PDD and
# engine/market_heatmap.py:106 with 携程集团; the two disagree, and a display fixture
# must not commit a screenshot carrying a company name that may be wrong.
WITNESSES = [
    ("0700.HK", "Tencent Holdings", "腾讯控股", "Communication Services", 601.0, 21.4),
    ("9988.HK", "Alibaba Group", "阿里巴巴", "Consumer Discretionary", 118.9, 30.2),
    ("9618.HK", "JD.com", "京东集团", "Consumer Discretionary", 132.4, 15.8),
    ("1810.HK", "Xiaomi", "小米集团", "Technology", 55.2, 26.6),
    ("3690.HK", "Meituan", "美团", "Consumer Discretionary", 148.7, 44.0),
    ("1024.HK", "Kuaishou", "快手", "Communication Services", 62.1, 8.7),
    ("9961.HK", "Trip.com Group", "携程集团", "Consumer Discretionary", 494.0, 12.3),
]
WITNESS_TICKERS = [w[0] for w in WITNESSES]


def _a_real_spark() -> str:
    """Borrow a real pre-rendered sparkline off the committed artifact. The card
    recolors it to the verb hue in CSS, so any row's SVG is visually valid on any
    other — and a fixture whose cards have no chart produces a screenshot of a board
    that does not exist."""
    for row in legacy_artifact().get("buy") or []:
        if row.get("spark_svg"):
            return row["spark_svg"]
    return ""


def _witness_buy_row(w, status: str, block_reason: str | None = None) -> dict:
    tk, name, name_zh, sector, price, _ = w
    return {
        "ticker": tk, "name": name, "name_zh": name_zh,
        "sector": sector, "sector_zh": sector,
        "price": price, "alpha": 1.2, "edge_z": 1.2, "off_high": -6.4, "dir": "up",
        # a turnover above FEATURED_MIN_ADV_HKD, so a qualifying row can actually
        # earn the star — the featured tests need a subject, and inventing one by
        # hand is what let the real gate go unexercised
        "_adv63": 900_000_000.0,
        # NO `ext_z`, and that is the FIDELITY choice (2026-08-09).  This row used to
        # carry `ext_z: 0.0` — a prop invented purely to get past #4684's absence-veto,
        # which since 2026-08-06 refused any row with no extension reading and would
        # otherwise have left every G4 aura test asserting over an empty cohort.
        # ANTICIPATION v1 removed that veto, so the prop is no longer needed — and it
        # was never honest: the REAL HK board supplies no `ext_z` on any row, from any
        # source, so a synthetic featured row that carries one renders the ONE state
        # this market cannot produce, and renders it in the place the featured copy is
        # read off.  Without the prop the shapes board features the same rows and every
        # one of them is `ext_unknown`, exactly like production.
        #
        # Consequence to keep in mind when reading scores here: the runway leg pays 0 on
        # an unmeasured row (fail-closed on POINTS is unchanged), so these cards score
        # 10 points lower than they did with the prop.  That is what an HK card actually
        # scores.
        "label": "BOTTOMING", "label_zh": "筑底中", "group": "entry_open",
        "conviction": {"score": 71, "verdict": "Leader turning up",
                       "verdict_zh": "龙头转强", "cautions": [], "cautions_zh": [],
                       "vol_squeeze": None},
        "entry_signal": {"status": status, "headline": "Partial entry — half size now",
                         "headline_zh": "部分入场 — 当前可建半仓",
                         "buy_zone": {"low": round(price * 0.96, 2),
                                      "high": round(price * 1.01, 2)}},
        "signal": {"asof": "2026-07-31", "tier_cascade": "T2", "ticks": 0,
                   "fresh_bars": 1, "eligible": True,
                   "last": ({"quality": "block", "reason": block_reason, "type": "buy"}
                            if block_reason else {"quality": "ok", "reason": None})},
        "lead": {"en": "Leader cohort participating.", "zh": "龙头组合正在参与。"},
        "ah_value": None, "southbound": None, "extended": False,
        "spark_svg": _a_real_spark(),
    }


def _witness_ran_row(w, *, sessions: int | None, pct: float | None,
                     anchor: str, measured_from: str | None = None) -> dict:
    """A ran-lane row shape.  No `theme_confirmed` leg: the HK cohort organ emits no
    per-name turn, so that branch was unreachable in production and is gone from the
    template — a fixture that kept stamping it would be guarding deleted markup.

    A move may ride ONLY on the `confirm` anchor (see hk_board_rank.build_ran_rows), so
    a `pct` without a `measured_from` is a shape the engine cannot emit and the fixture
    refuses to invent — a UI test standing on an impossible row proves nothing.
    """
    from engine import hk_board_rank as hbr

    assert (pct is None) or (anchor == hbr.ANCHOR_CONFIRM and measured_from), (
        "a measured move requires the confirm anchor and its measured_from date")
    tk, name, name_zh, sector, price, run = w
    return {"ticker": tk, "name": name, "name_zh": name_zh, "sector": sector,
            "sector_zh": sector, "price": price, "sessions_since": sessions,
            "cross_date": "2026-07-14", "pct_since": pct, "anchor": anchor,
            "measured_from": measured_from,
            # the ENGINE's own stance string — a shape row that disagrees would
            # split the lane's shared stance line into per-row chips and hide the
            # "printed once" contract behind a fixture detail
            "stance": hbr.RAN_STANCE, "stance_zh": hbr.RAN_STANCE_ZH,
            "label": "RALLY", "label_zh": "上涨中"}


ENGINE_FIXTURE = ROOT / "tests" / "fixtures" / "hk_board_2026_07_31.json"
BOARD_ASOF = "2026-07-31"
# The leadership snapshot the builder holds; mirrors tests/test_hk_board_rank.py so
# the two suites see the same cohort read.
_LEADERSHIP = {"state": "leaders_participating", "cohesion_now": 0.9,
               "broad_breadth_pct": 71.2, "breadth_confirming": True}


SCOREBOARD = FIXTURES / "hk_scoreboard_2026_07_31.json"


def _universe_rows() -> list[dict]:
    """The whole scored HK universe for the fixture's session — name, sector, edge_z.

    The 156-name cross-section the builder's `enriched` list carries for 2026-07-31,
    and the only source with a company NAME and a SECTOR for every ticker.  Both
    matter to the picture: the frozen G1 price panel stores the ticker in its `name`
    slot and no sector at all, so a screenshot shot without this backfill shows a
    Sector column of em-dashes and rows reading "0669.HK  0669.HK" — a board that
    does not exist, which is what the review objected to.

    FROZEN for the same reason the board artifact is (module docstring).  This read
    was `site/factordata/hk_scoreboard.json` — nightly-rewritten, and by 2026-08-04
    already stamped `as_of: 2026-08-03` while every other input here is 07-31, so the
    "same session" the paragraph above claims had quietly stopped being true.
    """
    if not SCOREBOARD.exists():             # pragma: no cover — committed in-tree
        return []
    doc = json.loads(SCOREBOARD.read_text())
    return [dict(r) for r in ((doc.get("modes") or {}).get("all") or [])]


def _engine_laggards(art: dict) -> list[dict]:
    """The laggards strip as the builder computes it: the SHIPPED key over the WHOLE
    universe, capped, with the printed figure stamped.

    `sorted(enriched, key=hk_board_rank.laggards_key)[:n]` is the builder's own line
    (scripts/build_hk_library.py), and the scoreboard gives this fixture the same
    156-row cross-section to sort.  The committed artifact's `laggards` are NOT used:
    they were selected by the pre-G5 conviction composite, which averaged the
    selection axis together with the ENTRY axis, so four of its six rows carry a
    POSITIVE selection reading (3690.HK +0.55 in the middle of a +44% run) that G5
    makes structurally impossible.  Rendering those under the new header would put an
    accurate sentence on the wrong data.
    """
    from engine import hk_board_rank as hbr

    pool = _universe_rows() or [dict(r) for r in (art.get("laggards") or [])]
    rows = sorted(pool, key=hbr.laggards_key)[:len(art.get("laggards") or []) or 6]
    for row in rows:
        row["laggard_z"] = hbr.selection_value(row)
    return rows


def engine_lanes(exclude: set[str] | None = None) -> dict:
    """Build leaders / ran / vetoed with the REAL engine, off the committed G1 panel,
    using the BUILDER's arguments.

    Synthetic lane rows can only ever confirm what this template already assumes —
    and what it assumed was the US board's `theme` key, which the HK engine never
    emits (it stamps `leadership`). Building the lanes for real is what turns this
    suite into an integration check between the two halves of the program.

    `exclude` is the production claim order: buy ∪ watch ∪ laggards take their
    tickers before any display lane runs (scripts/build_hk_library.py). Calling the
    lanes without it — which this harness used to do — manufactures rows that
    production would never emit, and double-lists names the page shows elsewhere.
    """
    from engine import hk_board_rank as hbr
    from engine.setups import norm_company

    panel = json.loads(ENGINE_FIXTURE.read_text())
    verdicts, closes = panel["verdicts"], panel["closes"]
    meta = {t: dict(m) for t, m in panel["meta"].items()}
    skip = set(exclude or ())

    # Production's `_lane_meta` is built from the whole scored universe and carries a
    # name and a sector for every ticker; the frozen price panel carries neither.
    # Backfilled from the same session's scoreboard so `dedup_name=norm_company` has
    # real company names to collapse and the rendered columns are not em-dashes.
    for row in _universe_rows():
        m = meta.get(row.get("ticker"))
        if m is None:
            continue
        for key in ("name", "name_zh", "sector"):
            if row.get(key) and not (m.get(key) and key != "name"):
                m[key] = row[key]
    art = legacy_artifact()
    for lane in ("buy", "watch", "laggards"):
        for row in art.get(lane) or []:
            m = meta.get(row.get("ticker"))
            if m is None:
                continue
            for key in ("name", "name_zh", "sector"):
                if row.get(key):
                    m[key] = row[key]

    def close_of(ticker):
        series = closes.get(ticker)
        return (series["dates"], series["closes"]) if series else None

    momentum = hbr.total_return_z(
        {t: (s["closes"] or [])[-(hbr.LEADERS_MOMENTUM_SESSIONS + 1):]
         for t, s in closes.items() if s.get("closes")},
        sessions=hbr.LEADERS_MOMENTUM_SESSIONS)
    leaders = hbr.build_leaders_rows(momentum, verdict_by=verdicts, meta_by=meta,
                                     exclude=skip,
                                     leadership=_LEADERSHIP, board_asof=BOARD_ASOF,
                                     dedup_name=norm_company)
    ran = hbr.build_ran_rows(verdicts, meta_by=meta, close_of=close_of,
                             exclude=skip | {r["ticker"] for r in leaders},
                             leadership=_LEADERSHIP, board_asof=BOARD_ASOF)
    vetoed = hbr.build_vetoed_rows(
        verdicts, meta_by=meta, close_of=close_of,
        exclude=skip | {r["ticker"] for r in leaders} | {r["ticker"] for r in ran},
        leadership=_LEADERSHIP, board_asof=BOARD_ASOF)
    return {"leaders": leaders, "ran": ran, "vetoed": vetoed}


def production_fixture() -> dict:
    """The board the first nightly will actually ship, built through the REAL engine.

    THE SCREENSHOT FIXTURE MUST NOT FLATTER THE BOARD (adversarial review,
    2026-08-03).  The previous shape promoted watch rows into the buy lane, scored
    every card with a crc32 stand-in for the priority score, stamped cohort chips by
    hand, and carried the pre-G5 laggards under their old key with the wrong sign —
    so the committed reference shots showed a board that does not exist.  Every
    number here now comes from the engine that will produce it:

      * `buy`   — the artifact's own cascade-admitted rows, ordered/staged/featured
                  by `hk_board_rank.score_rows`.  NO watch→buy promotion: the buy
                  lane on 2026-07-31 is three names, and three is the operator's
                  complaint, not something a fixture gets to fix.
      * lanes   — `engine_lanes()` under the production claim order.
      * laggards— re-cut on the shipped selection key, `laggard_z` stamped.
      * chips   — `hk_board_rank.stamp_leadership_chips`, the builder's own helper.
      * ranking — `hk_board_rank.ranking_block` (real weights, points form).
      * the artifact stamps the board reads: rank_by / board_definition /
        universe_excluded / universe_source_rows / lane_counts.

    Shapes the 2026-07-31 tape does not contain (an `approx` anchor, a null move, a
    blocked buy card) live in `shapes_fixture()`, which is never photographed.
    """
    from engine import hk_board_rank as hbr

    art = legacy_artifact()
    su = dict(art)

    buy = [dict(r) for r in (art.get("buy") or [])]
    watch = [dict(r) for r in (art.get("watch") or [])]
    laggards = _engine_laggards(art)
    claimed = ({r["ticker"] for r in buy} | {r["ticker"] for r in watch}
               | {r["ticker"] for r in laggards})
    lanes = engine_lanes(exclude=claimed)

    su["buy"] = score_buy_lane(buy)
    hbr.stamp_leadership_chips(su["buy"], _LEADERSHIP)
    su["watch"] = watch
    su["laggards"] = laggards
    su["ran"] = lanes["ran"]
    su["leaders"] = lanes["leaders"]
    su["vetoed"] = lanes["vetoed"]
    su["ranking"] = hbr.ranking_block(su["buy"], theme_asof=BOARD_ASOF)
    su["rank_by"] = hbr.BOARD_DEFINITION
    su["board_definition"] = hbr.BOARD_DEFINITION
    su["universe_source_rows"] = int(art.get("universe") or 0) + 1
    su["universe_excluded"] = 1
    su["lane_counts"] = hbr.lane_counts(
        buy=su["buy"], leaders=su["leaders"], ran=su["ran"], vetoed=su["vetoed"],
        watch=su["watch"], laggards=su["laggards"],
        featured=su["ranking"].get("featured_count") or 0)
    return su


def shapes_fixture() -> dict:
    """The production board PLUS the row shapes the 2026-07-31 tape does not contain.

    NEVER PHOTOGRAPHED — `production_fixture()` is the picture.  This one exists so
    the copy for an `approx` anchor, an unmeasurable move, a blocked buy card and a
    setting-up bucket is pinned on a rendered row rather than only in a map literal;
    the real tape supplies none of the four.  Every added ticker is an obviously
    synthetic 88xx.HK "Sample Holdings" line so it can never be mistaken for a name
    the board called, and none of them collides with an engine lane.
    """
    su = dict(production_fixture())
    claimed = ({r["ticker"] for lane in ("buy", "watch", "laggards", "leaders",
                                         "ran", "vetoed")
                for r in su.get(lane) or []})

    # Edge shapes the 2026-07-31 panel happens not to contain: an `approx` anchor and
    # a null `pct_since`. 88xx.HK sample lines, so they can never be read as calls.
    ran_extra = [
        _witness_ran_row(("8801.HK", "Sample Holdings A", "样本控股甲",
                          "Industrials", 42.0, 18.0),
                         sessions=11, pct=18.0, anchor="confirm",
                         measured_from="2026-07-24"),
        # `approx` — no marker date resolved, so the age is worked back from recent
        # bars AND the move is unmeasurable: the confirmation anchor is derived from
        # the marker's bucket, and there is no marker.
        _witness_ran_row(("8802.HK", "Sample Holdings B", "样本控股乙",
                          "Industrials", 31.0, 9.0),
                         sessions=9, pct=None, anchor="approx"),
        # `marker` — an exact age, but bar i+2 has not printed yet
        _witness_ran_row(("8803.HK", "Sample Holdings C", "样本控股丙",
                          "Industrials", 12.0, 0.0),
                         sessions=6, pct=None, anchor="marker"),
    ]
    assert not (claimed & {r["ticker"] for r in ran_extra})

    # Buy-lane stages the real board has none of tonight: a LIVE featured card and a
    # BLOCKED card carrying a mapped block reason, so the G6 copy and the featured
    # aura are pinned on a rendered row rather than only in a map literal. Never
    # promoted watch rows — a watch name carded here would print twice on one page
    # with two stances, which is the double-listing the review caught.
    extra_buy = [
        _witness_buy_row(("8804.HK", "Sample Holdings D", "样本控股丁",
                          "Technology", 55.0, 0.0),
                         "blocked", "failed reclaim-and-hold"),
        _witness_buy_row(("8805.HK", "Sample Holdings E", "样本控股戊",
                          "Financials", 18.0, 0.0), "buy_now"),
        _witness_buy_row(("8807.HK", "Sample Holdings G", "样本控股庚",
                          "Utilities", 9.0, 0.0), "partial"),
        # the reason 39 of the 48 refusals on this panel carry — its CARD copy has
        # to be exercised somewhere, and the real buy lane never blocks tonight
        _witness_buy_row(("8808.HK", "Sample Holdings H", "样本控股辛",
                          "Property", 6.0, 0.0),
                         "blocked", "counter-trend, no 200-reclaim/hold"),
        # `failed next-bar hold` is what reclaim_veto=False (hk_prophet_v2) emits on a
        # counter-trend refusal — 10 of the first v2 board's 12 vetoed rows carried it.
        # Carded here so its CARD copy is exercised by a render, not only asserted
        # against a map literal: with no _HK_BLOCK entry the popover fell through to
        # the generic sentence with the raw engine slug appended.
        _witness_buy_row(("8809.HK", "Sample Holdings I", "样本控股壬",
                          "Healthcare", 7.0, 0.0),
                         "blocked", "failed next-bar hold"),
    ]
    # The BASING subject (W-E.1). HK's staged pool is cascade-gated, so a pre-signal
    # BOTTOM WATCH row is near-impossible on the real board — measured ZERO across the
    # 14 committed snapshots — which is precisely why the shelf's copy, tone and
    # filtering have to be pinned on a rendered row here rather than on a map literal.
    # The row carries the ladder's DISPLAY label and no `state` key, because that is
    # the HK row shape (the builder maps the scoreboard's `cycle` into `label`).
    # `await_confluence` is deliberate: no entry has fired — it is a setting-up
    # status, so without the shelf this row would read "Setting up" — and the card's
    # own verb map turns it into `near`, which makes this row the subject that proves
    # a buy-family verb demotes to Wait underneath a "no entry signal yet" heading.
    _basing = _witness_buy_row(("8806.HK", "Sample Holdings F", "样本控股己",
                                "Materials", 24.0, 0.0), "await_confluence")
    _basing.update({"label": "NEARING A LOW", "label_zh": "接近低点",
                    "dir": "down", "group": "setting_up"})
    extra_buy.append(_basing)
    # a setting-up subject the real tape does supply — its own stage, untouched
    su["buy"] = score_buy_lane([dict(r) for r in su["buy"]] + extra_buy)
    from engine import hk_board_rank as _hbr
    from engine import us_board_rank as _ubr
    # One buy card must carry the cohort chip so the "earns the card no points"
    # disclosure has a subject. The cohort is OVERRIDDEN to a sample ticker rather
    # than carding a real mega-cap the board did not call — the chip payload is the
    # engine's, which is the part under test.
    _hbr.stamp_leadership_chips(su["buy"], _LEADERSHIP, cohort=["8807.HK"])
    # And one LEADERS row must carry it, for the same reason and by the same
    # override. The anchor eras (sq/cyc-abs-session-2026-08-06, #4738/#4833)
    # re-cut the marker stream and the intact-trend reads, and no mega-cap cohort
    # member survives the leaders admission on the re-pinned 2026-07-31 panel —
    # so the c-theme column, its 7-column mobile budget, the chip and the
    # boost-disclosure copy all went dark on the engine lanes. The subject is the
    # top engine leader chipped with the engine's own payload; membership is the
    # only thing synthesized.
    if su["leaders"] and not any(r.get("leadership") for r in su["leaders"]):
        _hbr.stamp_leadership_chips(su["leaders"], _LEADERSHIP,
                                    cohort=[su["leaders"][0]["ticker"]])
    su["ran"] = list(su["ran"]) + ran_extra
    su["lane_counts"] = {
        "featured": sum(1 for r in su["buy"] if r.get("featured")),
        "live": sum(1 for r in su["buy"] if r["stage"] == "live"),
        "setting_up": sum(1 for r in su["buy"] if r["stage"] == "setting_up"),
        "ran": sum(1 for r in su["buy"] if r["stage"] == "ran"),
        "basing": sum(1 for r in su["buy"] if r["stage"] == "basing"),
        "blocked": sum(1 for r in su["buy"] if r["stage"] == "blocked"),
        "ran_lane": len(su["ran"]),
        "vetoed_lane": len(su["vetoed"]),
    }
    su["ranking"] = {
        "version": "hk_prophet_v2",
        "weights": {"signal": 0.30, "entry": 0.25, "edge": 0.25,
                    "runway": 0.10, "quality": 0.10},
        "component_coverage": {"runway": {"nonzero": 0, "n": len(su["buy"])},
                               "signal": {"nonzero": len(su["buy"]), "n": len(su["buy"])}},
        # The extension-coverage receipt, COMPUTED from the rows this fixture ships
        # rather than written by hand.  The board note's extension clause is read off
        # this key (templates/hk.html.j2), so a hand-built `ranking` that omitted it
        # silently rendered the pre-2026-08-08 copy on a board whose rows all carry
        # `ext_unknown` — the fixture would have been the only thing still asserting
        # HK verifies extension.  Computed, so it cannot drift from `su["buy"]`.
        "ext_unknown_coverage": _ubr.ext_unknown_coverage(su["buy"]),
    }
    return su


@pytest.fixture(scope="module")
def prio_html() -> str:
    """The SHAPES board — every row shape the surface can render.

    Behaviour and copy assertions live here because the real tape carries only a
    live buy bucket; the picture is `prod_html`, and the fidelity assertions on it
    are what keep the two honest about which is which.
    """
    return _render(shapes_fixture())


@pytest.fixture(scope="module")
def prod_html() -> str:
    """The faithful board — no synthetic row anywhere.  This is what is photographed."""
    return _render(production_fixture())


@pytest.fixture(scope="module")
def legacy_html() -> str:
    return _render(legacy_artifact())


# --------------------------------------------------------------------------- #
# G4 — stage buckets, in order, above every card they own
# --------------------------------------------------------------------------- #

def test_stage_headings_render_in_priority_order(prio_html):
    positions = []
    for sk in _STAGE_ORDER:
        marker = '<div class="nb-stage-hd sg-%s" data-stage="%s"' % (sk, sk)
        idx = prio_html.find(marker)
        assert idx != -1, "stage heading missing for bucket %r" % sk
        positions.append(idx)
    assert positions == sorted(positions), (
        "stage headings must render live → setting_up → ran → blocked, got %r" % positions)


def test_stage_heading_carries_label_count_and_stance(prio_html):
    su = shapes_fixture()
    n_live = sum(1 for r in su["buy"] if r["stage"] == "live")
    block = prio_html[prio_html.find('<div class="nb-stage-hd sg-live"'):]
    block = block[:block.find("</div>") + 6]
    assert '<span class="sh-l"><span class="l-en">Live now</span>' in block
    assert '<span class="l-zh">现在可操作</span>' in block
    assert '<span class="sh-n">%d</span>' % n_live in block
    assert '<span class="l-en">entry window is open</span>' in block


# --------------------------------------------------------------------------- #
# W-E.1 — the basing shelf, ported from the US board (#4609)
# --------------------------------------------------------------------------- #

def test_the_basing_shelf_renders_between_ran_and_blocked(prio_html):
    """The shelf is the whole deliverable: a BOTTOM WATCH name rendered inside
    `Blocked`, beside the falling knives, is where the reader stops looking.  Its own
    shelf ABOVE Blocked is what makes the state visible.

    On HK this ships for vocabulary parity — the cascade-gated pool has produced no
    BOTTOM WATCH row in any committed snapshot — so what is pinned is the routing and
    the position, not a population.
    """
    basing = prio_html.find('<div class="nb-stage-hd sg-basing" data-stage="basing"')
    assert basing != -1, "the basing shelf never rendered"
    assert (prio_html.find('<div class="nb-stage-hd sg-ran" data-stage="ran"') < basing
            < prio_html.find('<div class="nb-stage-hd sg-blocked" data-stage="blocked"'))
    # the basing subject is ON the shelf, and a blocked subject is NOT
    subject = prio_html.find('data-ticker="8806.HK" data-stage="basing"')
    assert subject > basing, "the basing subject did not land under its own heading"
    assert subject < prio_html.find('data-ticker="8804.HK" data-stage="blocked"')


def test_the_basing_shelf_speaks_watch_words_in_both_languages(prio_html):
    """A watch lane that never makes a claim: the shelf says what the state is and
    what to do about it, and 'buy' is not one of the things it can say."""
    assert '<span class="l-en">Basing</span><span class="l-zh">筑底中</span>' in prio_html
    assert ('<span class="l-en">no entry signal yet — watch, don’t chase</span>'
            '<span class="l-zh">尚无入场信号 — 观察，勿追高</span>') in prio_html
    shelf = prio_html[prio_html.find('<div class="nb-stage-hd sg-basing"'):]
    shelf = shelf[:shelf.find("</div>") + 6]
    for banned in ("Buy", "buy", "买入"):
        assert banned not in shelf, "%r on a watch-only shelf" % banned


def test_the_basing_shelf_takes_a_direction_neutral_tone(prio_html):
    """--pv-wait and --muted are the two verb tones theme.css does NOT flip under the
    zh 红涨绿跌 convention, so a stance with no direction in it reads the same in both
    languages.  Inheriting --pv-avoid (what these rows had inside Blocked) would paint
    a basing name with the stand-aside colour it is being taken out of."""
    assert ".sg-basing     { --sgc: var(--pv-wait); }" in prio_html
    assert ".sg-blocked    { --sgc: var(--pv-avoid); }" in prio_html


def test_the_basing_bucket_is_filterable_like_every_other(prio_html):
    """Both halves of the filter pair, or the facet is half-built: the hide half alone
    leaves a basing row below the show-more fold invisible when you filter to it."""
    assert 'data-stagepick="basing"' in prio_html
    assert ('#standouts:not(.st-table-mode)[data-stagef="basing"]     '
            '[data-stage]:not([data-stage="basing"])') in prio_html
    assert ('#standouts:not(.st-table-mode)[data-stagef="basing"]     '
            '.sm-hidden[data-stage="basing"]') in prio_html


def test_no_blocked_card_above_a_live_card(prio_html):
    """The G4 no-blocked-above-live rule, read off the rendered card order rather
    than off the fixture: a card carries its bucket as data-stage."""
    order = re.findall(r'<a class="pvcard[^"]*" href="hk_lookup\.html#[^"]+" '
                       r'data-ticker="[^"]+" data-stage="([a-z_]+)"', prio_html)
    assert order, "no staged cards rendered"
    assert order.index("live") < order.index("blocked")
    assert order == sorted(order, key=_STAGE_ORDER.index), (
        "cards must never leave their bucket: %r" % order)


def test_every_priority_card_carries_a_stage_attribute(prio_html):
    n_cards = prio_html.count('<a class="pvcard')
    n_staged = len(re.findall(r'<a class="pvcard[^"]*"[^>]*data-stage="', prio_html))
    assert n_cards == n_staged == len(shapes_fixture()["buy"])


# --------------------------------------------------------------------------- #
# G4 — the featured glow, and ONLY on featured rows
# --------------------------------------------------------------------------- #

def test_hk_still_has_no_extension_wiring_and_now_says_so_on_every_row():
    """THE SAME KNOWN DEFECT, pinned through its second disclosure mechanism.

    The defect has never changed: `ext_z` is set nowhere in
    `scripts/build_hk_library.py`, nowhere in `engine/hk_board_rank.py`, and on no row
    of the frozen 2026-07-31 artifact.  HK has no extension reading at all.  What has
    changed twice is what the shared US machinery DOES about it:

      * #4684 (B3, 2026-08-06) made an absent reading a featured VETO.  On the US
        board that is fail-closed on a wired input that happened to be null.  On HK
        it was UNSATISFIABLE — no wiring exists to repair — so the featured aura went
        dark board-wide, and the predecessor of this test pinned that darkness with
        `featured_count == 0` / `featured_blocked_unknown_extension == 3`.
      * ANTICIPATION v1 (2026-08-08, `us_board_rank`) replaced the absence-veto with a
        per-row disclosure after the same veto published a US featured lane of 0 out
        of 69 on a one-night data gap.  HK inherits that wholesale, so the shelf is
        reachable again — by rows whose chase-risk check still has no input.

    That inheritance is a CROSS-MARKET consequence of a US-program change and it is
    pinned here rather than left to a board diff.  The HK repair is unchanged and is
    still a board-owner call, not a CI heal: wire an HK extension reading, or scope
    the leg off the way `reclaim_veto=False` already scopes off the other leg HK
    cannot satisfy (`signal_quality._confirm_legs` calls that one "an UNSATISFIABLE
    condition" in as many words).

    WHAT THIS TEST MAY NOT DO IS PIN A TAUTOLOGY (audit finding, 2026-08-09).  It
    previously asserted `featured_with_unknown == featured_count`, which is
    identically true given the assertion three lines above it that EVERY row is
    `ext_unknown` — if every row is unknown then every featured row is unknown, for
    any board, under any code.  Worse, on this fixture both sides are 0 (the real
    2026-07-31 tape features nothing, held by `adv_unknown`), so it compared zero to
    zero and would have survived the absence-veto being reinstated.  Replaced with
    claims that can fail: the gap is real and total, the absence no longer vetoes, and
    the shelf stays BOUNDED by its caps now that a veto is no longer doing the
    bounding for it.  The DISCLOSURE-reaches-the-reader half is pinned separately, on
    rendered HTML, in the test directly below.
    """
    from engine import hk_board_rank as hbr

    su = production_fixture()
    buy = su["buy"]
    assert buy, "no buy lane — the assertions below would be vacuous"
    assert all(r.get("ext_unknown") is True for r in buy), (
        "an HK row carries an extension reading — if `ext_z` was finally wired, "
        "delete this test and re-pin the G4 gates on the real featured cohort")
    # The gap must be PRINTED, not merely true.
    rb = su["ranking"]
    cov = rb.get("ext_unknown_coverage") or {}
    assert cov.get("unknown") == cov.get("n") == len(buy), cov
    # The absence no longer routes through `featured_blocked_by` — pinned so a
    # re-introduced absence-veto shows up here instead of silently re-darkening HK.
    assert rb.get("featured_blocked_unknown_extension") == 0
    assert not any("ext_z_unknown" in (r.get("featured_blocked_by") or ())
                   for r in buy)
    # THE REAL BOUND.  Until 2026-08-08 the featured count was held at 0 by a veto that
    # could never pass here; with the veto gone the only things holding it are the caps
    # and the other gates, so those are what must be asserted.  A cap breach would put
    # unbounded unmeasured rows on the attention shelf, which is the actual risk the
    # widening introduced.
    featured = [r for r in buy if r.get("featured")]
    assert len(featured) == rb.get("featured_count") <= hbr.FEATURED_CAP, (
        f"{rb.get('featured_count')} featured rows against a cap of "
        f"{hbr.FEATURED_CAP}")
    per_sector: dict[str, int] = {}
    for r in featured:
        per_sector[r.get("sector")] = per_sector.get(r.get("sector"), 0) + 1
    assert all(v <= hbr.SECTOR_CAP for v in per_sector.values()), per_sector
    # And the reason today's count is what it is, stated so a change in it is read as
    # the event it would be rather than as noise: on this tape every row is held by an
    # unknown 63-day turnover, NOT by the extension leg.
    assert all("adv_unknown" in (r.get("featured_blocked_by") or ()) for r in buy), (
        "the HK featured gate is now binding on something else — re-read this test's "
        "premise before trusting its bound")


def test_an_hk_featured_row_without_an_extension_reading_says_so_on_the_board(prio_html):
    """The disclosure has to reach a READER, not just the artifact.

    The engine stamping `ext_unknown` and the block counting it are both invisible to
    the person looking at the board.  Since ANTICIPATION v1 lit a shelf whose
    chase-risk check has no input on this market, the board note may no longer state
    "price not extended" among the gates the green cards passed — it is a check HK has
    never run.  Pinned on rendered HTML because that is the only place the claim
    exists; the copy branches on the artifact's own `ext_unknown_coverage`, so the day
    an HK extension reading is wired this test fails and the claim comes back.

    NOTE the chip-level twin of this copy (`templates/hk.html.j2`, the ★ Featured
    mark's `tip_en`/`tip_zh`) is NOT asserted here, and deliberately: it is suppressed
    by `_MK_NOTIP = ('feat', 'new')` in `_prophet_card.html.j2` (operator 2026-08-05)
    and renders nowhere.  Asserting it would pin a string no reader receives.
    """
    su = shapes_fixture()
    featured = [r for r in su["buy"] if r.get("featured")]
    assert featured, "no featured row — the claim below would be vacuous"
    assert all(r.get("ext_unknown") is True for r in featured), (
        "a featured HK row carries an extension reading; this fixture no longer "
        "represents the board it stands in for")

    # The claim is GONE from the gate description ...
    assert "edge above zero, price not extended" not in prio_html
    assert "优势为正、价格未过度拉伸" not in prio_html
    # ... and replaced by a plain-word null in both languages (DESIGN_DOCTRINE Law 5 —
    # no slug, no untranslated stat, the absence stated where the claim used to be).
    assert ("no extension reading on this board, so how far a name has already run "
            "goes unchecked") in prio_html
    assert "本榜暂无拉伸读数，价格拉伸程度未作检查" in prio_html


# --------------------------------------------------------------------------- #
# The per-row absence mark — wired here, suppressed here, and why
# --------------------------------------------------------------------------- #

_NCK_MARK = '<span class="pv-mk-i pv-mk-nck"'


def test_hk_suppresses_the_per_row_absence_mark_because_the_gap_is_total(prio_html):
    """The US board marks WHICH featured names lost the chase-risk reading.  HK lost
    it on all of them, so here the mark would be the same chip on every green card —
    the per-row repetition of a constant DESIGN_DOCTRINE Law 4 files as a defect ("a
    constant belongs in the footer, once").  The board note above is that footer, and
    it already says it.

    The rule is keyed on the DATA, not on the market: it reads "is every featured row
    unknown?" off the rendered rows, which is why the sibling test below can turn the
    mark on by changing one row and nothing else.  Absence is asserted on the full
    markup string, never the bare class token — `.pv-mk-nck`'s CSS ships on every
    render (harness law).
    """
    su = shapes_fixture()
    featured = [r for r in su["buy"] if r.get("featured") and r.get("stage") == "live"]
    assert featured, "no featured live card — the claim below would be vacuous"
    assert all(r.get("ext_unknown") is True for r in featured), (
        "a featured HK row carries an extension reading — the suppression premise is "
        "gone and this test no longer describes the board")
    assert _NCK_MARK not in prio_html, (
        "every HK pick is unmeasured, so a per-row mark is noise, not information")


def test_the_hk_absence_mark_is_wired_and_appears_the_moment_the_gap_is_partial():
    """GUARD THE GUARD.  The suppression test above passes identically whether the
    mark is deliberately suppressed or was never wired into this template at all —
    the exact tautology this file's §G4 note was rewritten to avoid.  So: give ONE
    featured row an extension reading and nothing else, and the mark must appear on
    the rows that still have none.  That is the day-HK-gets-wired case, proven now.
    """
    su = shapes_fixture()
    featured = [r for r in su["buy"] if r.get("featured") and r.get("stage") == "live"]
    assert len(featured) >= 2, (
        "need two featured live cards to make one measured and one not")
    featured[0]["ext_unknown"] = False
    html = _render(su)

    unknown = [r for r in featured if r.get("ext_unknown")]
    assert unknown, "fixture must keep an unmeasured pick"
    assert _NCK_MARK in html, "the HK carrier is not wired — suppression proves nothing"
    assert ('<span class="l-en">Extended? Not checked</span>'
            '<span class="l-zh">涨过头？未检查</span>') in html
    # One mark per still-unmeasured pick, and none for the one that now has a reading.
    assert html.count(_NCK_MARK) == len(unknown)
    # The engine's field name never reaches the page (banned raw slug, doctrine Law 2).
    assert "ext_unknown" not in html


def test_featured_glow_lands_only_on_featured_rows(prio_html):
    su = shapes_fixture()
    feat = {r["ticker"] for r in su["buy"] if r.get("featured")}
    assert feat, "fixture must contain at least one featured row"
    glowing = set(re.findall(r'<a class="pvcard pv-\w+ pv-featured" href="[^"]*" '
                             r'data-ticker="([^"]+)"', prio_html))
    assert glowing == feat, "glow cohort %r != featured cohort %r" % (glowing, feat)


def test_featured_rows_carry_the_star_chip_so_colour_is_never_the_only_carrier(prio_html):
    su = shapes_fixture()
    n_feat = sum(1 for r in su["buy"] if r.get("featured"))
    assert prio_html.count('<span class="pv-mk-i pv-mk-feat"') == n_feat
    assert '<span class="l-en">★ Featured</span><span class="l-zh">★ 精选</span>' in prio_html


def test_featured_rows_are_all_buy_verb_so_the_aura_never_sits_on_a_lighter_card(prio_html):
    verbs = set(re.findall(r'<a class="pvcard pv-(\w+) pv-featured"', prio_html))
    assert verbs <= {"buy"}, "featured aura found on non-buy card(s): %r" % verbs


# --------------------------------------------------------------------------- #
# G4 — filter chips
# --------------------------------------------------------------------------- #

def test_filter_bar_renders_one_chip_per_non_empty_bucket_with_true_counts(prio_html):
    su = shapes_fixture()
    counts = {sk: sum(1 for r in su["buy"] if r["stage"] == sk) for sk in _STAGE_ORDER}
    counts["ran"] += len(su["ran"])
    # the vetoed lane IS the blocked bucket's second half
    counts["blocked"] += len(su["vetoed"])
    assert '<div class="pbf-bar" id="hk-stage-filter" role="group"' in prio_html
    bar = prio_html[prio_html.find('<div class="pbf-bar"'):]
    bar = bar[:bar.find("</div>")]
    assert '<button type="button" data-stagepick="all" aria-pressed="true">' in bar
    assert '<span class="pbf-n">%d</span>' % (
        len(su["buy"]) + len(su["ran"]) + len(su["vetoed"])) in bar
    for sk, n in counts.items():
        chip = '<button type="button" data-stagepick="%s" aria-pressed="false"' % sk
        if n:
            assert chip in bar, "missing filter chip for %r" % sk
            seg = bar[bar.find(chip):]
            assert '<span class="pbf-n">%d</span>' % n in seg[:seg.find("</button>")]
        else:
            assert chip not in bar, "empty bucket %r must render no chip" % sk


def test_filter_chip_counts_match_what_filtering_would_show(prio_html):
    """A chip whose number disagrees with the filtered result is a defect. The CSS
    filters on data-stage, so count the rendered data-stage carriers per bucket —
    cards plus the ran section, minus the headings (which also carry the attr)."""
    su = shapes_fixture()
    for sk in _STAGE_ORDER:
        chip = '<button type="button" data-stagepick="%s" aria-pressed="false"' % sk
        if chip not in prio_html:
            continue
        seg = prio_html[prio_html.find(chip):]
        claimed = int(re.search(r'<span class="pbf-n">(\d+)</span>',
                                seg[:seg.find("</button>")]).group(1))
        cards = len(re.findall(r'<a class="pvcard[^"]*"[^>]*data-stage="%s"' % sk, prio_html))
        extra = {"ran": len(su["ran"]), "blocked": len(su["vetoed"])}.get(sk, 0)
        assert claimed == cards + extra, (
            "chip %r claims %d, board shows %d" % (sk, claimed, cards + extra))


def test_filter_bar_has_exactly_one_polite_live_region_and_its_script(prio_html):
    assert prio_html.count('<span class="pbf-live" id="hk-stage-status" aria-live="polite">') == 1
    assert "var bar = document.getElementById('hk-stage-filter');" in prio_html
    assert "box.setAttribute('data-stagef', btn.getAttribute('data-stagepick'));" in prio_html


# --------------------------------------------------------------------------- #
# G3 — the ran section
# --------------------------------------------------------------------------- #

def test_ran_section_renders_with_stage_attr_so_the_filter_reaches_it(prio_html):
    assert '<div class="pbr" data-stage="ran">' in prio_html
    assert '<span class="pbr-t"><span class="l-en">Recently fired</span>' in prio_html
    seg = _ran_block(prio_html)
    n = len(shapes_fixture()["ran"])
    assert '<span class="pbr-n">%d</span>' % n in seg
    assert seg.count('<a class="pbr-r') == n


def test_ran_rows_count_sessions_never_ticks(prio_html):
    seg = _ran_block(prio_html)
    assert "fired 11 sessions ago" in seg
    assert "11个交易日前触发" in seg
    assert re.search(r"fired \d+d ago", seg) is None, "ran rows must not print day units"


def test_ran_approx_anchor_marks_the_figure_and_explains_itself(prio_html):
    seg = _ran_block(prio_html)
    assert "fired ≈9 sessions ago" in seg, "approx anchor must carry the ≈ glyph"
    assert "≈ means the exact date this signal fired was not recorded" in seg
    # the marker-anchored row must NOT be marked approximate
    row = _ran_row(seg, "3690.HK")
    assert "≈" not in row


def test_ran_row_with_no_measurable_move_prints_an_em_dash_not_a_zero(prio_html):
    row = _ran_row(_ran_block(prio_html), "8803.HK")
    assert '<span class="pbr-na"' in row, "null pct_since must render the em-dash slot"
    assert ">—</span>" in row
    assert "az-up" not in row and "az-dn" not in row
    assert "+0.0%" not in row


def test_the_ran_lane_keeps_the_engines_order_and_carries_no_warm_branch(prio_html):
    """Replaces the theme_confirmed sort/amber-line test (2026-08-03).

    That branch was ported from the US board, where `us_board_rank` stamps
    `theme_confirmed` from a `theme_by` map.  The HK builder passes no such map and
    `hk_leadership` emits no per-name turn, so on this page it could never be true:
    the amber wash, the warm-first partition and the "leader group just turned" line
    were unreachable, and the only thing that ever exercised them was the fixture
    stamping the flag itself.  Both are deleted; what remains is the engine's own
    order, which is the fact worth pinning.
    """
    seg = _ran_block(prio_html)
    order = re.findall(r'<span class="pbr-tk">([^<]+)</span>', seg)
    assert order == [r["ticker"] for r in shapes_fixture()["ran"]]
    assert "pbr-warm" not in seg, "the unreachable warm branch is gone"
    assert "pbr-wl" not in seg


def test_ran_section_carries_no_buy_family_language(prio_html):
    seg = _ran_block(prio_html)
    for word in ("Buy now", "buy now", "Buy zone", "Add here"):
        assert word not in seg, "ran lane must not use buy-family language (%r)" % word
    # the section line is the ENGINE's stance, printed once — not a literal here
    assert "The move already started — wait for the next entry." in seg
    assert "行情已经启动 — 等待下一个买点。" in seg


def _ran_block(html: str) -> str:
    """The ran section ONLY.

    The end sentinel is the vetoed section, which now sits between the ran lane and
    the footnote — when it was still `<p class="pb-fn">` this slice silently grew to
    include every vetoed row, and `assert X not in block` assertions stopped being
    scoped to the thing they name. A missing sentinel fails loudly rather than
    degrading into a vacuous pass.
    """
    start = html.find('<div class="pbr" data-stage="ran">')
    assert start != -1, "ran section not rendered"
    for sentinel in ('<div class="pbv" data-stage="blocked">', '<p class="pb-fn">'):
        end = html.find(sentinel, start)
        if end != -1:
            return html[start:end]
    raise AssertionError("no end sentinel found after the ran section")


def _veto_block(html: str) -> str:
    start = html.find('<div class="pbv" data-stage="blocked">')
    assert start != -1, "vetoed section not rendered"
    end = html.find('<p class="pb-fn">', start)
    assert end != -1, "pb-fn end sentinel not found after the vetoed section"
    return html[start:end]


def _veto_row(block: str, ticker: str) -> str:
    idx = block.find('<span class="pbr-tk">%s</span>' % ticker)
    assert idx != -1, "vetoed row %r not found" % ticker
    start = block.rfind("<a class=", 0, idx)
    return block[start:block.find("</a>", idx) + 4]


def _ran_row(block: str, ticker: str) -> str:
    idx = block.find('<span class="pbr-tk">%s</span>' % ticker)
    assert idx != -1, "ran row %r not found" % ticker
    start = block.rfind("<a class=", 0, idx)
    return block[start:block.find("</a>", idx) + 4]


# --------------------------------------------------------------------------- #
# G1 / G6 — the vetoed lane (what the entry gate refused)
# --------------------------------------------------------------------------- #

def test_vetoed_section_lives_inside_the_blocked_bucket(prio_html):
    """It is what the entry gate refused, so it belongs to Blocked — and the filter
    CSS keys on data-stage, so without the attribute the Blocked chip would reveal
    the blocked cards and hide the refusals its own count includes."""
    assert '<div class="pbv" data-stage="blocked">' in prio_html
    seg = _veto_block(prio_html)
    assert '<span class="pbr-t"><span class="l-en">What the gate refused</span>' in seg
    assert '<span class="l-zh">门控拒绝的信号</span>' in seg
    assert '<span class="pbr-n">%d</span>' % len(shapes_fixture()["vetoed"]) in seg


def test_vetoed_section_states_why_it_exists_in_both_languages(prio_html):
    seg = _veto_block(prio_html)
    assert "the section exists to keep the board honest, not to hand you a list to buy" in seg
    assert "这里记录门控拒绝后的走势，用于自我审视" in seg


def test_vetoed_rows_carry_no_buy_family_language(prio_html):
    seg = _veto_block(prio_html)
    for word in ("Buy now", "buy now", "Buy zone", "buy zone", "Add here", "pullback zone"):
        assert word not in seg, "the vetoed lane must not read as an entry list (%r)" % word
    assert 'class="pv-mk-feat"' not in seg and "pv-featured" not in seg


def test_vetoed_cohort_rows_lead_the_list(prio_html):
    su = shapes_fixture()
    cohort = [r["ticker"] for r in su["vetoed"] if r.get("in_leadership_cohort")]
    assert cohort, "fixture has no cohort members in the vetoed lane"
    seg = _veto_block(prio_html)
    order = re.findall(r'<span class="pbr-tk">([^<]+)</span>', seg)
    assert order[:len(cohort)] == cohort, (
        "cohort rows must lead the vetoed list: got %r, cohort %r" % (order, cohort))


def test_vetoed_cohort_rows_chip_the_plain_word_state_never_the_slug(prio_html):
    su = shapes_fixture()
    cohort = [r for r in su["vetoed"] if r.get("in_leadership_cohort")]
    seg = _veto_block(prio_html)
    for r in cohort:
        row = _veto_row(seg, r["ticker"])
        assert '<span class="pv-mk-i pv-mk-theme"' in row, "%s has no cohort chip" % r["ticker"]
        assert r["leadership"]["state_en"] in row
        assert r["leadership"]["state_zh"] in row
        assert r["leadership"]["state"] not in row, "the raw state slug reached the surface"
    # non-cohort rows carry no chip — the chip's PRESENCE is the per-row fact
    plain = [r for r in su["vetoed"] if not r.get("in_leadership_cohort")]
    if plain:
        assert '<span class="pv-mk-i pv-mk-theme"' not in _veto_row(seg, plain[0]["ticker"])


def test_vetoed_rows_name_the_refusal_and_the_marker_it_stands_on(prio_html):
    """G6's honesty: a name held out on ONE marker for a quarter is a different fact
    from one blocked yesterday, and only the date and the session count tell them
    apart. The engine's own `reason_raw` must never be the words on the surface."""
    su = shapes_fixture()
    seg = _veto_block(prio_html)
    for r in su["vetoed"][:5]:
        row = _veto_row(seg, r["ticker"])
        assert r["blocked_reason_en"] in row, "%s: reason missing" % r["ticker"]
        assert r["blocked_reason_zh"] in row
        if r.get("sessions_since") is not None:
            n = r["sessions_since"]
            assert "%d session%s ago" % (n, "" if n == 1 else "s") in row
            assert "%d个交易日前" % n in row
    assert "counter-trend, no 200-reclaim/hold" not in seg, (
        "the engine's raw reason string must stay off the glance tier")


def test_vetoed_move_is_signed_and_direction_coloured(prio_html):
    su = shapes_fixture()
    seg = _veto_block(prio_html)
    moved = [r for r in su["vetoed"] if r.get("pct_since") is not None]
    assert moved, "fixture has no measured moves"
    for r in moved[:4]:
        row = _veto_row(seg, r["ticker"])
        cls = "az-up" if r["pct_since"] >= 0 else "az-dn"
        assert '<span class="%s">%+.1f%%</span>' % (cls, r["pct_since"]) in row


def test_vetoed_move_says_it_is_measured_from_the_confirmation_close(prio_html):
    """The figure must not silently answer "since the signal fired".

    It is measured from the close at which the entry check could first reach its
    verdict — about eight sessions after the marker — so the label has to say which,
    and the hover has to name both dates.  Printing the confirmation figure under the
    old "since the block" label would be the same overstatement wearing new numbers.
    """
    su = shapes_fixture()
    seg = _veto_block(prio_html)
    assert "since the check finished" in seg
    assert "（检查完成后）" in seg
    assert "since the block</span>" not in seg, "the old marker-anchored label is gone"
    row = _veto_row(seg, su["vetoed"][0]["ticker"])
    measured = su["vetoed"][0]["measured_from"]
    assert measured and measured != su["vetoed"][0]["signal_date"]
    assert "It finished on %s" % measured in row
    assert "到 %s 才完成" % measured in row
    assert "The signal fired on %s" % su["vetoed"][0]["signal_date"] in row


def test_vetoed_section_prints_the_population_behind_its_truncated_rows(prio_html):
    """Twelve rows ranked BY the move and cut at a cap are the winning tail of it.

    Without the count and the middle move of the whole refused set beside them they
    read as a P&L claim the lane never made — the operator's own reading of the
    2026-08-03 board, where the section was cited as evidence in an admission change.
    """
    su = shapes_fixture()
    seg = _veto_block(prio_html)
    row0 = su["vetoed"][0]
    population, median = row0["population"], row0["population_median_pct"]
    assert population > len(su["vetoed"]), "the fixture must actually truncate"
    assert '<div class="pbv-pop">' in seg
    assert "Showing the %d biggest movers of %d refused signals." % (
        len(su["vetoed"]), population) in seg
    assert "the middle move is %+.1f%%" % median in seg
    assert "显示 %d 个被拒信号中涨幅最大的 %d 个。" % (
        population, len(su["vetoed"])) in seg
    assert "中位涨跌幅为 %+.1f%%" % median in seg
    # it reads BEFORE the rows: a reader who meets twelve green figures first has
    # already formed the impression the line exists to prevent
    assert seg.index('<div class="pbv-pop">') < seg.index('<a class="pbr-r pbr-veto"')


def test_the_population_line_is_fail_soft_on_a_pre_population_artifact(prio_html):
    """Every artifact written before this change carries none of the three keys."""
    su = shapes_fixture()
    su["vetoed"] = [{k: v for k, v in dict(r).items()
                     if not k.startswith("population")} for r in su["vetoed"]]
    seg = _veto_block(_render(su))
    assert '<div class="pbv-pop">' not in seg
    assert seg.count('<a class="pbr-r pbr-veto"') == len(su["vetoed"]), (
        "the rows must render exactly as before")


def test_a_stale_marker_anchored_artifact_prints_no_move_at_all(prio_html):
    """The transitional half, and it fails CLOSED.

    Every artifact written before 2026-08-03 carries a marker-anchored `pct_since`
    with `anchor: marker`, and the nightly that regenerates it can land a day after
    this template does.  Rendering those numbers under a label promising the
    confirmation close would wrap the old overstatement in a new claim — worse than
    the defect.  So the figure keys on the ANCHOR, not merely on the value.
    """
    su = shapes_fixture()
    legacy = dict(su["vetoed"][0], ticker="9998.HK", anchor="marker",
                  pct_since=20.1, measured_from=None)
    su["vetoed"] = [legacy]
    seg = _veto_block(_render(su))
    row = _veto_row(seg, "9998.HK")
    assert "20.1%" not in row, "a marker-anchored move must not reach the page"
    assert '<span class="pbr-na"' in row and ">—</span>" in row
    assert "az-up" not in row and "az-dn" not in row
    # the same law on the ran lane
    su2 = shapes_fixture()
    su2["ran"] = [dict(su2["ran"][0], ticker="9997.HK", anchor="marker",
                       pct_since=29.2, measured_from=None)]
    assert "29.2%" not in _ran_row(_ran_block(_render(su2)), "9997.HK")


def test_vetoed_row_with_no_measurable_move_prints_an_em_dash(prio_html):
    """The engine emits disclosed nulls (`_move_desc` sorts them last rather than
    dropping them) — the surface must print the gap, never a zero."""
    su = shapes_fixture()
    su["vetoed"] = [dict(su["vetoed"][0], ticker="9999.HK", pct_since=None)]
    seg = _veto_block(_render(su))
    row = _veto_row(seg, "9999.HK")
    assert '<span class="pbr-na"' in row and ">—</span>" in row
    assert "az-up" not in row and "az-dn" not in row
    assert "+0.0%" not in row


def test_vetoed_rows_are_counted_by_the_blocked_chip(prio_html):
    su = shapes_fixture()
    n_cards = sum(1 for r in su["buy"] if r["stage"] == "blocked")
    expected = n_cards + len(su["vetoed"])
    chip = '<button type="button" data-stagepick="blocked" aria-pressed="false"'
    seg = prio_html[prio_html.find(chip):]
    seg = seg[:seg.find("</button>")]
    assert '<span class="pbf-n">%d</span>' % expected in seg, (
        "the Blocked chip must count the refusals its own filter reveals")


def test_witnesses_reachable_only_through_the_vetoed_lane_are_visible(prio_html):
    """The whole reason this section exists: on the measured panel most of the
    mega-cap witnesses appear in NO other lane."""
    su = shapes_fixture()
    elsewhere = ({r["ticker"] for r in su["buy"]} | {r["ticker"] for r in su["ran"]}
                 | {r["ticker"] for r in su["leaders"]})
    veto_only = [r["ticker"] for r in su["vetoed"]
                 if r["ticker"] in WITNESS_TICKERS and r["ticker"] not in elsewhere]
    assert len(veto_only) >= 3, (
        "fixture drifted: expected witnesses reachable only via the vetoed lane, got %r"
        % veto_only)
    seg = _veto_block(prio_html)
    for tk in veto_only:
        assert '<span class="pbr-tk">%s</span>' % tk in seg


def test_no_vetoed_section_without_the_array(prio_html):
    su = shapes_fixture()
    su.pop("vetoed")
    html = _render(su)
    assert '<div class="pbv" data-stage="blocked">' not in html
    n_cards = sum(1 for r in su["buy"] if r["stage"] == "blocked")
    chip = '<button type="button" data-stagepick="blocked" aria-pressed="false"'
    seg = html[html.find(chip):]
    assert '<span class="pbf-n">%d</span>' % n_cards in seg[:seg.find("</button>")]


# --------------------------------------------------------------------------- #
# stance — the engine's own strings, printed once
# --------------------------------------------------------------------------- #

def test_a_lane_stance_is_printed_once_not_on_every_row(prio_html):
    """`stance` is identical on every row of a lane today. Printed per row it is a
    constant repeated 12–15 times (Law 4); dropped, the surface stops showing a
    stance the engine may one day vary. So it becomes the section's own line."""
    su = shapes_fixture()
    stance = su["vetoed"][0]["stance"]
    assert len({r["stance"] for r in su["vetoed"]}) == 1
    seg = _veto_block(prio_html)
    assert seg.count(stance) == 1, "the lane stance must appear exactly once"
    assert '<span class="pbv-st">' not in seg


def test_a_row_whose_stance_differs_prints_its_own(prio_html):
    """The other half of the rule — without it, a lane that ever varied its stance
    would silently show only the first row's."""
    su = shapes_fixture()
    su["vetoed"] = [dict(su["vetoed"][0]),
                    dict(su["vetoed"][1], stance="on hold pending a restructuring",
                         stance_zh="因重组暂缓")]
    seg = _veto_block(_render(su))
    assert '<span class="pbv-st">' in seg
    assert "on hold pending a restructuring" in seg
    assert "因重组暂缓" in seg


def test_ran_and_leaders_sections_carry_the_engines_stance_strings(prio_html):
    su = shapes_fixture()
    assert su["ran"][0]["stance"] and su["leaders"][0]["stance"]
    assert su["ran"][0]["stance_zh"] and su["leaders"][0]["stance_zh"]
    assert su["ran"][0]["stance"][0].upper() + su["ran"][0]["stance"][1:] + "." in \
        _ran_block(prio_html)
    assert su["leaders"][0]["stance"] + "." in _leaders_block(prio_html)


# --------------------------------------------------------------------------- #
# G2 — the leaders strip
# --------------------------------------------------------------------------- #

def _leaders_block(html: str) -> str:
    start = html.find('<div class="topsetups leaders-strip">')
    assert start != -1, "leaders strip not rendered"
    end = html.find("</table></div>", start)
    assert end != -1, "leaders table end sentinel not found"
    return html[start:end]


def test_leaders_strip_states_its_rank_key_and_its_stance(prio_html):
    seg = _leaders_block(prio_html)
    assert "🏃 <span class=\"l-en\">Market leaders</span>" in seg
    assert "Strongest runners by 3-month momentum" in seg
    # the stance sentence comes from the rows' own `stance`, printed once
    assert "watch — don't chase." in seg
    assert "观察 — 不要追高。" in seg


def test_leaders_numeric_column_names_the_key_the_engine_actually_ranks_by(prio_html):
    """HK leaders rows carry `momentum_z` + `rank_key` and NO `alpha` — the ported
    "α (tiebreak)" header sat over a column of em-dashes and named a field that
    does not exist on this board. The column must show, and be named after, the
    number the rows are ordered by."""
    seg = _leaders_block(prio_html)
    assert '<span class="l-en">3-mo momentum</span>' in seg
    assert "α (tiebreak)" not in seg, "the dead alpha header is back"
    assert "the number this table is ranked by" in seg
    rows = shapes_fixture()["leaders"][:15]
    assert any(r.get("momentum_z") is not None for r in rows), "fixture has no momentum"
    body = seg[seg.find("<tbody>"):]
    for r in rows:
        if r.get("momentum_z") is not None:
            assert "%+.2f" % r["momentum_z"] in body, (
                "%s momentum %r not rendered" % (r["ticker"], r["momentum_z"]))
    assert body.count('c-edge muted">—') == 0, "the ranked column rendered as em-dashes"


def test_leaders_age_column_replaced_the_dead_state_column(prio_html):
    """`label` is never stamped on a leaders row either, so the ported `state`
    column was dead. Signal age is the read this lane has — and the one that
    explains why the entry-gated board cannot see these names."""
    seg = _leaders_block(prio_html)
    assert '<th class="c-age"' in seg
    assert '<th class="c-state"' not in seg
    assert '<span class="l-en">last signal</span>' in seg
    rows = shapes_fixture()["leaders"][:15]
    aged = [r for r in rows if r.get("days_since_signal") is not None]
    assert aged, "fixture has no signal ages"
    body = seg[seg.find("<tbody>"):]
    for r in aged[:3]:
        unit = "session" if r.get("days_since_signal_basis") == "sessions" else "day"
        n = r["days_since_signal"]
        assert "%d %s%s ago" % (n, unit, "" if n == 1 else "s") in body


def test_leaders_rows_keep_the_engines_order(prio_html):
    seg = _leaders_block(prio_html)
    rendered = re.findall(r'<span class="ts-tk">([^<]+)</span>', seg)
    assert rendered == [r["ticker"] for r in shapes_fixture()["leaders"][:15]]


def test_leaders_rows_are_terminal_routable(prio_html):
    """Every leaders row must be reachable by theme.js's Terminal intercept.

    That intercept is a capture-phase listener on `a[href]` — it re-points
    hk_lookup.html#TKR (one of theme.js's TERMINAL_PAGES) at the Terminal portal.
    A `<tr onclick="location.href=…">` is invisible to it, so these rows navigated
    to the retired hk_lookup.html analyzer no matter what theme.js did (the same
    defect fixed for us_stocks in #4489, reported here 2026-08-03). The pin is
    two-sided: the anchor must exist AND the onclick form must be gone, on a
    render that actually has rows (an empty strip would make the absence half
    vacuous).
    """
    seg = _leaders_block(prio_html)
    tickers = [r["ticker"] for r in shapes_fixture()["leaders"][:15]]
    assert tickers, "fixture has no leaders — the assertions below are vacuous"

    for ticker in tickers:
        assert '<tr class="ts-row" data-tkr="%s">' % ticker in seg, (
            "%s row is not carrying the ticker the delegated handler reads" % ticker)
        assert '<a class="ts-tk-a" href="hk_lookup.html#%s">' % ticker in seg, (
            "%s ticker is not an anchor — theme.js cannot see it" % ticker)

    # The defect itself: no ts-row may navigate via an inline location.href.
    assert "onclick=\"location.href='hk_lookup.html#" not in prio_html

    # The delegated handler that covers clicks on the REST of the row. It lives
    # just past the table, so it is outside `seg` — search the whole page.
    assert "tr.ts-row[data-tkr]" in prio_html
    assert "window.MDXTerminal" in prio_html


def test_leaders_ticker_anchor_does_not_read_as_a_link(prio_html):
    """The row is the affordance; the anchor exists only so theme.js can see it
    (and so cmd-/middle-click keeps its native new-tab behaviour). Without this
    rule every ticker in the strip turns blue and underlined."""
    css = (Path(__file__).resolve().parents[1] / "templates" / "hk.html.j2").read_text()
    assert ".ts-tk-a { color: inherit; text-decoration: none; }" in css
    assert 'class="ts-tk-a"' in prio_html   # the rule has something to style


def test_every_leaders_column_carries_a_c_class_so_none_escapes_the_mobile_budget(prio_html):
    """The c-* classes ARE the mobile contract (≤680px hides the tertiary set); a th
    or td without one silently escapes that budget."""
    seg = _leaders_block(prio_html)
    head = seg[seg.find("<thead>"):seg.find("</thead>")]
    ths = re.findall(r"<th\b[^>]*>", head)
    assert len(ths) == 7, "expected 7 leader columns, got %d" % len(ths)
    for th in ths:
        assert re.search(r'class="[^"]*\bc-[a-z]+\b', th), "th without a c-* class: %s" % th
    body = seg[seg.find("<tbody>"):]
    first = body[:body.find("</tr>")]
    tds = re.findall(r"<td\b[^>]*>", first)
    assert len(tds) == len(ths), "row/column count mismatch: %d td vs %d th" % (len(tds), len(ths))
    for td in tds:
        assert re.search(r'class="[^"]*\bc-[a-z]+\b', td), "td without a c-* class: %s" % td


def test_leaders_cohort_column_appears_only_when_rows_carry_it(prio_html):
    assert '<th class="c-theme"' in _leaders_block(prio_html)
    su = shapes_fixture()
    su["leaders"] = [{k: v for k, v in r.items() if k not in ("leadership", "theme")}
                     for r in su["leaders"]]
    seg = _leaders_block(_render(su))
    assert '<th class="c-theme"' not in seg
    head = seg[seg.find("<thead>"):seg.find("</thead>")]
    assert len(re.findall(r"<th\b", head)) == 6


def test_cohort_chip_reads_the_engines_leadership_key_not_the_us_theme_key(prio_html):
    """The HK engine stamps `leadership` on lane rows; it never stamps the US
    board's `theme`. A chip that only looked for `theme` rendered NOTHING against a
    real artifact — the leaders column would have been all em-dashes and no card or
    ran row would have carried a cohort chip at all."""
    su = shapes_fixture()
    lanes = engine_lanes()
    assert not any(r.get("theme") for lane in lanes.values() for r in lane), (
        "fixture drifted: the engine now stamps `theme`, so this test is vacuous")
    assert any(r.get("leadership") for lane in lanes.values() for r in lane), (
        "engine stopped stamping `leadership` — the chip source moved")
    chipped = [r for r in su["leaders"][:15] if r.get("leadership")]
    assert chipped, "fixture has no cohort members among the leaders"
    seg = _leaders_block(prio_html)
    body = seg[seg.find("<tbody>"):]
    assert body.count('<span class="pv-mk-i pv-mk-theme"') >= len(chipped)
    # and the chip's words are the plain-word state, never the slug
    assert "leaders_participating" not in prio_html


def test_leaders_entry_column_never_promises_an_entry(prio_html):
    seg = _leaders_block(prio_html)
    body = seg[seg.find("<tbody>"):]
    n_rows = body.count("<tr ")
    assert n_rows, "no leader rows rendered"
    assert body.count('<span class="ent-warn">') >= n_rows, (
        "every leaders row must carry an explicit no-entry read")
    assert "Buy now" not in seg
    # no ROW may render the zone affordance when the engine ships no zone (the
    # header tip legitimately explains what a pullback zone is, so scope to <tbody>)
    assert '<span class="ent-good">' not in body


def test_leaders_entry_column_shows_a_zone_when_the_engine_has_one(prio_html):
    """Engine leaders rows carry no entry_signal today, so the zone branch is dark
    on the live fixture — pin it against a row that does, or the branch could rot
    unnoticed until the day the engine starts shipping one."""
    su = shapes_fixture()
    su["leaders"] = [dict(su["leaders"][0],
                          entry_signal={"buy_zone": {"low": 10.0, "high": 11.5}})]
    seg = _leaders_block(_render(su))
    assert '<span class="ent-good"><span class="l-en">pullback zone</span>' in seg
    assert "10.00–11.50" in seg


def test_no_cohort_member_currently_reaches_the_leaders_strip():
    """A KNOWN DEFECT, pinned so it cannot go quiet. THIS TEST IS MEANT TO FAIL when the
    defect is repaired — that failure is the signal to re-pin the G2 cohort gates above
    on the real cohort row and delete this test.

    Those gates are pinned on a chip `shapes_fixture()` stamps by hand (#4889), which is
    the right call — the column, the mobile budget and the HKRV-R5 disclosure must stay
    tested — but it means nothing above notices that the REAL strip carries no cohort
    member at all.  This does.  On the 2026-07-31 panel the leaders strip carries ZERO
    (it was two), the strip fills 14 of LEADERS_CAP=15, and `ran` fills 3 of 12.

    Root cause, measured 2026-08-07: `signal_quality.signal_frame` joins the
    calendar-absolute W-FRI weekly leg onto the 3D grid's INDEX LABEL —

        wbull = (wm >= wsg).shift(1).reindex(s3.index, method="ffill")

    — while a bucket's `close` is its LAST close.  R-SQ2 made that label the bucket's
    OPEN date, so each 3D bar is handed the weekly regime from up to a bucket before its
    own close.  Joining on `_tf_grid(...).last_session` instead flips `weekly_bull` on 28
    of 157 names here, and `weekly_bull is True` is half the leaders admission gate
    (`hk_board_rank.build_leaders_rows`); with it, 0941.HK and 9618.HK re-enter the strip
    and leaders/ran/vetoed all fill their caps (15/15, 12/12, 12/12).

    NOT REPAIRED IN THE PR THAT WROTE THIS TEST, deliberately.  The join is not an R-SQ2
    regression — `git log -S` puts the line at the module's original commit, and the
    retired 3B label was the synthetic LEFT edge too (mean 1.87 sessions before the close
    it carried), so this has always been label-anchored; the era only removed a truncation
    bin that had been masking it at this as-of.  Repairing it is therefore a SEMANTIC
    REVISION, not a defect repair, and R-SQ6 pins `_confirm_legs` semantics as
    "byte-identical".  It owes: `ANCHOR_ERA` bumped (R-SQ3), a committed blast-radius
    report (R-SQ4 — 107/157 marker lists move on the HK panel alone; US/CN/CA unmeasured),
    and the two sibling joins fixed with it (`above200` at 0.30% disagreement,
    `rising2_on3` at 19.76%) so `_confirm_legs` does not read two different as-of dates.
    `engine/canon.py:370,444` — the golden oracle — already joins the weekly on the
    bucket's last session and calls it leak-free; that is the precedent that work should
    cite.  Full site table: research/SQ_BUCKET_LABEL_AS_DATE_FINDINGS_2026-08-07.md.
    """
    lanes = engine_lanes()
    chipped = {lane: [r["ticker"] for r in rows if r.get("leadership")]
               for lane, rows in lanes.items()}
    assert chipped["leaders"] == [], (
        "a cohort member reached the leaders strip: %r — if the weekly-leg join was "
        "repaired, re-pin the G2 cohort gates on the real row and delete this test"
        % chipped["leaders"])
    # the chip source itself must still be alive, or the statement above is not about
    # the leaders gate at all — it is about a dead cohort read.
    assert chipped["ran"] or chipped["vetoed"], (
        "no lane carries a cohort chip — the cohort read is dead, which is a different "
        "and larger defect than the one this test pins")


def test_cohort_chip_tells_the_truth_about_where_it_counts(prio_html):
    """HKRV-R5 fence: the hk_leadership read boosts the leaders table's order and
    earns nothing at all on the graded buy lane. Both statements must be on the
    surface, on the element each one is about."""
    seg = _leaders_block(prio_html)
    assert "Membership adds a small boost to where a name sits in THIS table" in seg
    assert "on the board above it earns nothing at all" in seg
    assert "membership earns the card no points and changes nothing in the ranking" in prio_html


# --------------------------------------------------------------------------- #
# G1 — the seven witnesses are visible
# --------------------------------------------------------------------------- #

def test_six_of_the_seven_witnesses_appear_on_the_production_board(prod_html):
    """G1 at the PAGE, measured on the board the nightly will ship.

    SEVEN of seven since the anchor eras (sq/cyc-abs-session-2026-08-06,
    #4738/#4833 — the G1 fixture regen those PRs shipped).  Under the previous
    bucketing 9961.HK was genuinely dark and this guard pinned six, refusing the
    old harness's habit of carding any witness the engine placed nowhere.  The
    re-cut marker stream changes its VERDICT, not the harness: its blocked buy
    marker now reads weekly-bull, so `veto_admits` — fail-closed on every leg —
    seats it in the vetoed lane on its own merits.  The guard's job is unchanged:
    it pins the exact page-level witness count so a board that started "showing
    everything" (or silently losing names) still fails here.
    """
    seen = [tk for tk in WITNESS_TICKERS if tk in prod_html]
    assert len(seen) == 7, "page-level witness visibility moved: %r" % seen
    assert "9961.HK" in seen, "9961.HK earns its vetoed-lane seat under the era verdicts"


def test_at_least_five_witnesses_carry_a_stance_bearing_row(prio_html):
    """G1's fixture gate. A stance-bearing row is a staged card (its verb chip is
    the stance), a ran row (stance: the window has passed) or a leaders row
    (stance: watch — don't chase)."""
    carded = set(re.findall(r'data-ticker="([^"]+)"[^>]*data-stage="', prio_html))
    ran = set(re.findall(r'<span class="pbr-tk">([^<]+)</span>', prio_html))
    leaders = set(re.findall(r'<span class="ts-tk">([^<]+)</span>', prio_html))
    seen = {tk for tk in WITNESS_TICKERS if tk in (carded | ran | leaders)}
    assert len(seen) >= 5, "only %d of 7 witnesses carry a stance: %r" % (len(seen), seen)


def test_a_card_never_contradicts_the_bucket_it_sits_in(prio_html):
    """The bucket outranks the verb. HK's 200-day veto stamps a blocking marker while
    the entry gauge may still read `partial`, which would print a solid green BUY
    chip under a heading that says "stand aside". No buy-family verb is reachable in
    the ran, basing or blocked buckets — basing is the sharpest case, since its
    heading says "no entry signal yet" while its `await_confluence` subject would
    otherwise card as `near`."""
    su = shapes_fixture()
    shut = {r["ticker"] for r in su["buy"]
            if r["stage"] in ("ran", "basing", "blocked")}
    assert shut, "fixture must contain ran/basing/blocked rows"
    for tk in shut:
        m = re.search(r'<a class="pvcard pv-(\w+)[^"]*" href="[^"]*" data-ticker="%s"'
                      % re.escape(tk), prio_html)
        assert m, "card %r not rendered" % tk
        assert m.group(1) not in ("buy", "near"), (
            "%s sits in a shut bucket but carries a %r verb" % (tk, m.group(1)))


def test_a_buy_status_row_in_a_shut_bucket_is_demoted_not_hidden(prio_html):
    """The demotion must not cost the row its place: it stays carded, in its bucket,
    with the reason on the ⚠ mark."""
    su = shapes_fixture()
    blocked_buy = [r for r in su["buy"] if r["stage"] == "blocked"
                   and (r.get("entry_signal") or {}).get("status") in ("buy_now", "partial")]
    for r in blocked_buy:
        assert 'data-ticker="%s" data-stage="blocked"' % r["ticker"] in prio_html


def test_the_glow_can_never_land_outside_the_live_bucket(prio_html):
    su = shapes_fixture()
    su["buy"] = [dict(r, featured=True) for r in su["buy"]]   # engine gate gone rogue
    html = _render(su)
    lit = set(re.findall(r'<a class="pvcard \w+ pv-featured"[^>]*data-stage="(\w+)"', html))
    lit |= set(re.findall(r'<a class="pvcard pv-\w+ pv-featured" href="[^"]*" '
                          r'data-ticker="[^"]*" data-stage="(\w+)"', html))
    assert lit <= {"live"}, "featured aura escaped the live bucket: %r" % lit


def test_blocked_witnesses_name_the_check_that_is_holding_them_out(prio_html):
    """G6 display-tier relief: a blocked name is visible AND its reason is nameable
    in plain words, on Tier 2 where mechanics belong.

    The `failed reclaim-and-hold` sentence used to be "Price has not reclaimed its
    200-day line and held there, so entries stay shut until it does" — a promise about
    a 200-day condition that branch of `_buy_filter` never evaluates (it tests the
    next 3-day bar's close alone).  It now states the test that actually ran.
    """
    assert "The 3-day bar after the signal closed lower" in prio_html
    assert "信号后的下一根 3 日K线收低" in prio_html
    assert "still under its 200-day line" in prio_html
    for slug in ("failed reclaim-and-hold", "failed next-bar hold"):
        assert "%s</span>" % slug not in prio_html, (
            "the engine's raw reason string must not reach the glance tier verbatim")


def test_the_blocked_card_copy_never_promises_a_200day_reclaim_it_did_not_test(
        prio_html):
    """The inverse guard.  `counter-trend, no 200-reclaim/hold` DOES test the 200-day
    line, so its sentence must keep naming it — otherwise the fix above could be
    'passed' by deleting every 200-day mention from the page."""
    assert "This would be a bounce against the bigger downtrend" in prio_html
    assert "Price has not reclaimed its 200-day line and held there" not in prio_html, (
        "the next-bar-hold branch is again narrating a 200-day round trip it never "
        "measured")


# --------------------------------------------------------------------------- #
# G4 — the Priority slot and the formula footnote
# --------------------------------------------------------------------------- #

def test_priority_replaces_edge_in_the_card_slot_when_the_row_scores(prio_html):
    assert '<span class="pv-edl"><span class="l-en">Priority</span>' \
           '<span class="l-zh">优先级</span></span>' in prio_html
    assert '<span class="l-en">Edge</span><span class="l-zh">优势</span>' not in prio_html
    top = shapes_fixture()["buy"][0]
    assert '<span class="pv-edn">%d</span>' % round(top["prophet"]["score"]) in prio_html


def test_footnote_states_the_weights_read_from_the_artifact(prio_html):
    assert '<p class="pb-fn">' in prio_html
    assert "Priority = signal 30% + entry 25% + edge 25% + runway 10% + setup quality 10%." in prio_html
    assert "优先级＝信号30%＋入场25%＋优势25%＋上行空间10%＋形态质量10%。" in prio_html
    assert "it is not a win probability" in prio_html
    assert "The hk_prophet_v2 forward record is accruing separately." in prio_html


def test_footnote_follows_the_artifact_when_the_engine_changes_a_weight(prio_html):
    """The weights are READ, never hard-coded — a template that prints last quarter's
    constants beside this quarter's score is printing a wrong number."""
    su = shapes_fixture()
    su["ranking"]["weights"] = {"signal": 0.40, "entry": 0.20, "edge": 0.20,
                                "runway": 0.10, "quality": 0.10}
    html = _render(su)
    assert "Priority = signal 40% + entry 20% + edge 20% + runway 10% + setup quality 10%." in html
    assert "signal 30% + entry 25%" not in html


def test_footnote_reads_the_engines_real_weights_dict_not_a_lookalike():
    """The scale rule (fractions vs points) is the one place this template can print
    a plausible wrong number, so it is pinned against the ENGINE's own constant
    rather than a hand-written stand-in. us_board_rank.SCORE_WEIGHTS is shared —
    hk_board_rank.ranking_block() calls straight through to it — and it ships POINTS
    (30.0), not fractions; a template that divided by 100 would render "signal 0%"
    and nothing else would notice."""
    try:
        from engine.us_board_rank import SCORE_WEIGHTS
    except Exception:                                    # pragma: no cover
        pytest.skip("engine.us_board_rank unavailable in this checkout")
    su = shapes_fixture()
    su["ranking"]["weights"] = dict(SCORE_WEIGHTS)
    html = _render(su)
    foot = html[html.find('<p class="pb-fn">'):]
    foot = foot[:foot.find("</p>")]
    assert foot, "footnote not rendered"
    total = 0
    for leg in ("signal", "entry", "edge", "runway", "quality"):
        pts = round(SCORE_WEIGHTS[leg])
        total += pts
        label = "setup quality" if leg == "quality" else leg
        assert "%s %d%%" % (label, pts) in foot, "leg %r missing from the footnote" % leg
    assert total == 100, "the disclosed weights no longer sum to 100: %r" % SCORE_WEIGHTS
    # scoped to the footnote: `0%` is everywhere in the page's own gradients
    assert " 0%" not in foot, "a weight collapsed to 0% — the fraction/points scale flipped"


def test_dark_leg_is_disclosed_in_plain_words_wherever_the_weight_appears(prio_html):
    n = len(shapes_fixture()["buy"])
    assert "runway currently contributes 0 for all %d names" % n in prio_html
    assert "上行空间目前对全部 %d 只股票都记 0 分" % n in prio_html
    assert prio_html.count("currently contributes 0 for all") >= 2, (
        "the disclosure must ride with the weights on both the footnote and the card tip")


def test_no_dark_leg_note_when_the_artifact_reports_no_coverage(prio_html):
    """Silent, not fail-closed: HK has never measured leg coverage, and asserting an
    unmeasured null would be the same overclaim pointing the other way."""
    su = shapes_fixture()
    su["ranking"].pop("component_coverage")
    html = _render(su)
    assert "currently contributes 0" not in html
    assert "都记 0 分" not in html


def test_new_chip_honours_the_engine_flag_over_the_fallback(prio_html):
    assert '<span class="l-en">New</span><span class="l-zh">新</span>' in prio_html
    su = shapes_fixture()
    for r in su["buy"]:
        r["new"] = False
        r["days_since_signal"] = 0          # would trip the ≤2-session fallback
    html = _render(su)
    assert '<span class="pv-mk-i pv-mk-new"' not in html, (
        "an engine-supplied new=False must not be overridden by the fallback")


# --------------------------------------------------------------------------- #
# G9 — fail-soft: the committed artifact still renders the flat board
# --------------------------------------------------------------------------- #

_NEW_MARKUP = [
    '<div class="nb-stage-hd',
    '<div class="pbf-bar"',
    '<span class="pbf-live"',
    '<div class="pbr" data-stage="ran">',
    '<p class="pb-fn">',
    '<div class="topsetups leaders-strip">',
    '<div class="pv-mk">',
    "getElementById('hk-stage-filter')",
]


def test_the_frozen_legacy_fixture_carries_none_of_the_v1_contract():
    """If this ever fails the fixture has drifted and the fail-soft tests below have
    quietly stopped testing fail-soft.

    It fired for real on 2026-08-04 — correctly, and against the wrong subject.  It
    was reading the LIVE artifact, so what it actually detected was the nightly
    shipping the priority engine, not a fixture someone had broken; the fail-soft
    tests below went red beside it and the whole set read as a template regression.
    Pointed at the frozen fixture it now means what its name says: this file is the
    pre-v1 board, and nobody has regenerated it off a priority-era nightly.
    """
    art = legacy_artifact()
    assert art.get("as_of") == BOARD_ASOF, (
        "the legacy fixture must be the same session as the price panel and "
        "BOARD_ASOF, got %r" % art.get("as_of"))
    assert art.get("ran") is None and art.get("leaders") is None
    assert art.get("ranking") is None
    assert not any(r.get("stage") for r in art.get("buy") or [])


def test_legacy_artifact_renders_the_flat_board_with_no_priority_markup(legacy_html):
    for frag in _NEW_MARKUP:
        assert frag not in legacy_html, "priority markup leaked onto the legacy board: %r" % frag
    # `data-stage=` also appears in the filter CSS (which ships on every render), so
    # the absence test is anchored to a real TAG, never to the bare attribute name.
    stray = re.search(r'<[a-zA-Z][a-zA-Z0-9-]*[^>]*\sdata-stage="', legacy_html)
    assert stray is None, "legacy element carries data-stage: %r" % (stray and stray.group(0))
    assert legacy_html.count('<a class="pvcard') == len(legacy_artifact()["buy"])


def test_legacy_board_keeps_its_own_copy_and_the_edge_slot(legacy_html):
    assert '<span class="l-en">Edge</span><span class="l-zh">优势</span>' in legacy_html
    assert "Priority</span>" not in legacy_html
    assert "Only names with a fresh entry signal make this board." in legacy_html
    assert "Bottoming names, ranked by flow, value and strength" in legacy_html
    assert "Ranked by readiness" not in legacy_html


def test_legacy_board_keeps_the_artifacts_own_card_order(legacy_html):
    order = re.findall(r'<a class="pvcard[^"]*" href="hk_lookup\.html#([^"]+)"', legacy_html)
    assert order == [r["ticker"] for r in legacy_artifact()["buy"]]


def test_legacy_board_cards_opt_into_the_live_price_change_pill(legacy_html):
    cards = len(legacy_artifact()["buy"])
    assert legacy_html.count('<span class="pv-quote">') == cards
    assert legacy_html.count('<span class="nb-chg pv-chg"') == cards


def test_laggards_value_class_follows_the_sign(legacy_html):
    """The value was hardcoded `.neg`, so a POSITIVE laggard printed in the loss
    colour — and because `.neg` maps to --down, which inverts under
    html[data-lang="zh"], the same +1.05 read "loss" in English and "gain" in
    Chinese. The class must follow the sign; the theme still owns the hue."""
    art = legacy_artifact()
    lagg = art.get("laggards") or []
    assert lagg, "the committed artifact has no laggards — this test is vacuous"
    assert any(r.get("alpha") is not None and r["alpha"] > 0 for r in lagg), (
        "no positive-alpha laggard in the fixture, so the defect cannot be seen")
    block = legacy_html[legacy_html.find("⚠ <span class=\"l-en\">Weakest"):]
    block = block[:block.find("</p>", block.find("<p style="))]
    for r in lagg:
        if r.get("alpha") is None:
            continue
        expect = "pos" if r["alpha"] > 0 else "neg"
        assert '<span class="%s">%+.2f</span>' % (expect, r["alpha"]) in block, (
            "%s (%+.2f) must render as %s" % (r["ticker"], r["alpha"], expect))


def test_health_banner_survives_the_rebuild(legacy_html, prio_html):
    """The ledger-write failure is load-bearing until the engine lane heals it — it
    must be on the surface on BOTH paths."""
    for html in (legacy_html, prio_html):
        assert '<p class="note st-health"' in html
        assert "Some inputs didn't update this render" in html
        assert "部分数据本次未更新" in html


def test_legacy_render_is_tag_stream_identical_to_the_base_branch():
    """The strongest form of the fail-soft proof: render the LEGACY artifact through
    this template and through the base branch's, and compare the element streams.
    Skipped (never failed) when the base ref is unreachable — a shallow or sparse CI
    checkout has no business reddening main — because every observable half of the
    same contract is pinned unconditionally by the tests above."""
    base = None
    for ref in ("origin/main", "main"):
        try:
            base = subprocess.run(["git", "show", "%s:templates/hk.html.j2" % ref],
                                  cwd=ROOT, capture_output=True, text=True,
                                  check=True, timeout=30).stdout
            break
        except Exception:
            continue
    if not base:
        pytest.skip("base ref templates/hk.html.j2 unavailable in this checkout")
    # The era stamps used to be STRIPPED here, because the live artifact this read
    # from had become a priority-era board and comparing it whole had stopped testing
    # fail-soft and started asserting the priority layer never changes — which the
    # hk_prophet_v2 admission disclosure legitimately does.  The fixture is genuinely
    # legacy now, so the strip is gone and the absence is ASSERTED instead: a silent
    # pop would hide a fixture regenerated off a priority-era nightly, which is the
    # exact drift that took this file down.
    art = legacy_artifact()
    assert art.get("board_definition") is None and art.get("rank_by") is None
    normalized, quote_count = _without_opt_in_live_change(_render(art))
    assert quote_count == len(art["buy"]), (
        "live quote normalizer did not cover exactly one pill per legacy card")
    mine, theirs = _tags(normalized), _tags(_render_source(base, art))
    assert mine == theirs, "legacy render changed shape vs the base branch (%d vs %d tags)" % (
        len(mine), len(theirs))


def test_the_priority_era_render_gains_exactly_the_admission_disclosure():
    """The other half of the pair above: on a PRIORITY-era artifact the render is NOT
    unchanged — hk_prophet_v2 owes the reader the admission change in plain words.  Pin
    that it is present and that it names the cost, so a later edit cannot quietly drop
    the disclosure while keeping the wider board."""
    # Collapse whitespace: the copy wraps across template lines, so a raw substring
    # match would pin the indentation rather than the sentence.
    flat = re.sub(r"\s+", " ", _render(priority_era_artifact()))
    assert "until 3 Aug this board also" in flat
    assert "close back above that average within two sessions" in flat
    assert "roughly a third more names here, and deeper drawdowns" in flat, (
        "the disclosure must state the cost, not just the loosening")
    assert "8月3日之前" in flat and "回撤会更深" in flat


# --------------------------------------------------------------------------- #
# House invariants
# --------------------------------------------------------------------------- #

def test_no_cjk_in_title_attributes(prio_html):
    for value in re.findall(r'\stitle="([^"]*)"', prio_html):
        assert not re.search(r"[一-鿿]", value), (
            "translated text in a title= attribute (CI-guarded): %r" % value)


def test_no_validated_claim_in_the_new_surface(prio_html):
    """`check_validated_claims.py` guards the word house-wide; this pins the blocks
    this PR authored so a later edit cannot smuggle it back in."""
    for block in (_ran_block(prio_html), _leaders_block(prio_html)):
        assert "validated" not in block.lower()


def test_both_languages_are_present_on_every_new_block(prio_html):
    for block in (_ran_block(prio_html), _leaders_block(prio_html)):
        assert 'class="l-en"' in block and 'class="l-zh"' in block


def test_no_raw_stage_slug_reaches_the_glance_tier(prio_html):
    """`setting_up` may live in data-stage / data-stagepick attributes; it must never
    be the words a reader sees."""
    for text in re.findall(r'<span class="(?:sh-l|sh-s)">(.*?)</span></?', prio_html):
        assert "setting_up" not in text and "hk_prophet_v" not in text
    assert ">setting_up<" not in prio_html


def test_macro_mode_page_is_untouched_by_the_rebuild():
    html = _render(production_fixture(), mode="macro")
    assert '<div class="pbf-bar"' not in html
    assert '<div class="topsetups leaders-strip">' not in html


# --------------------------------------------------------------------------- #
# B3 — the v1 sentinel is artifact-level, not derived from the buy lane
# --------------------------------------------------------------------------- #

_V1_SECTIONS = (
    '<div class="pbf-bar" id="hk-stage-filter"',        # stage filter
    '<div class="topsetups leaders-strip">',            # leaders
    '<div class="pbr" data-stage="ran">',               # ran
    '<div class="pbv" data-stage="blocked">',           # vetoed
    '<p class="pb-fn">',                                # priority footnote
)


def test_an_empty_buy_lane_on_a_v1_artifact_keeps_every_section():
    """The night the cascade admits nobody is the night this surface matters most.

    The sentinel used to ask "does any BUY row carry a stage?", which reads the
    presence of the priority layer off a lane that is allowed to be empty — so a v1
    board with `buy: []` would have silently dropped the filter, the three display
    lanes and the footnote, deleting exactly the coverage built for that night.
    2026-07-31 came within three names of it.
    """
    su = dict(production_fixture())
    su["buy"] = []
    su["lane_counts"] = dict(su["lane_counts"] or {}, buy=0, live=0, setting_up=0,
                             ran=0, blocked=0)
    html = _render(su)
    for frag in _V1_SECTIONS:
        assert frag in html, "empty buy lane dropped %r" % frag
    # the Live bucket is empty and prints no chip (China precedent: a chip you can
    # press into a void is worse than none) — but the BAR is there, and its All chip
    # counts what the page actually shows.
    bar = html[html.find(_V1_SECTIONS[0]):]
    bar = bar[:bar.find("</div>")]
    assert 'data-stagepick="all"' in bar
    assert 'data-stagepick="live"' not in bar, "an empty bucket must not print a chip"
    assert '<span class="pbf-n">%d</span>' % (len(su["ran"]) + len(su["vetoed"])) in bar


def test_a_legacy_artifact_still_renders_none_of_it():
    """The other half: fail-soft is unchanged, and it is decided by the same key."""
    art = legacy_artifact()
    assert art.get("board_definition") is None and art.get("rank_by") is None
    html = _render(art)
    for frag in _V1_SECTIONS:
        assert frag not in html, "priority markup leaked onto a legacy artifact: %r" % frag


def test_the_live_artifact_still_renders():
    """The ONE assertion in this file that reads `site/factordata/hk_standouts.json`.

    Freezing the fixtures bought determinism at a price: nothing here would notice
    the NIGHTLY's own artifact drifting into a shape this template cannot render.
    This buys that back without re-arming the fuse, by asserting only what is true in
    BOTH eras — the page renders, it cards the buy lane, and the priority layer is
    present exactly when the era stamp says it should be.  No era-specific copy, no
    row counts, no lane membership: those are what made the old reads unsatisfiable.

    A failure here is a real incompatibility between the shipped board and the
    shipped template, which is the thing the era-pinned tests could never separate
    from an ordinary nightly.

    LANE-GATED, NOT ERA-GATED.  Three of the five priority sections are
    ``{% if _hsg.any and <lane> %}`` (templates/hk.html.j2:3861/3941/4010) — an empty
    lane correctly prints nothing.  Demanding them on every priority-era board would
    red main on a thin night, which is a worse gate than none; each is asserted
    against its OWN lane instead.
    """
    if not LIVE_ARTIFACT.exists():           # pragma: no cover — committed in-tree
        pytest.skip("%s not present" % LIVE_ARTIFACT)
    art = json.loads(LIVE_ARTIFACT.read_text())
    html = _render(art)

    assert html.count('<a class="pvcard') == len(art.get("buy") or []), (
        "the live board cards every buy row in both eras")

    stamp = str(art.get("board_definition") or art.get("rank_by") or "")
    priority_era = stamp.startswith("hk_prophet_v")
    # era stamp alone decides these two
    era_only = ('<div class="pbf-bar" id="hk-stage-filter"', '<p class="pb-fn">')
    # these need the era stamp AND rows in their own lane
    lane_gated = {'<div class="topsetups leaders-strip">': "leaders",
                  '<div class="pbr" data-stage="ran">': "ran",
                  '<div class="pbv" data-stage="blocked">': "vetoed"}

    for frag in era_only:
        assert (frag in html) is priority_era, (
            "live artifact stamps %r but the render %s %r"
            % (stamp, "dropped" if priority_era else "kept", frag))
    for frag, lane in lane_gated.items():
        expected = priority_era and bool(art.get(lane))
        assert (frag in html) is expected, (
            "live artifact stamps %r with %d %s row(s) but the render %s %r"
            % (stamp, len(art.get(lane) or []), lane,
               "dropped" if expected else "kept", frag))


def test_the_sentinel_reads_the_artifact_stamp_not_the_rows():
    """MUTATION: strip every row-level `stage` and the layer must still render;
    strip the artifact stamp and it must disappear even with stages intact."""
    su = dict(production_fixture())
    su["buy"] = [{k: v for k, v in r.items() if k != "stage"} for r in su["buy"]]
    assert _V1_SECTIONS[0] in _render(su), "the stamp, not the rows, decides"

    su2 = dict(production_fixture())
    su2.pop("board_definition", None)
    su2.pop("rank_by", None)
    html2 = _render(su2)
    for frag in _V1_SECTIONS:
        assert frag not in html2, "an unstamped artifact must fail soft: %r" % frag


def test_the_rank_by_key_alone_lights_the_layer():
    """`rank_by` is the older spelling of the same string — an artifact written
    between the two stamps must not render a half board."""
    su = dict(production_fixture())
    su.pop("board_definition")
    assert _V1_SECTIONS[0] in _render(su)


# --------------------------------------------------------------------------- #
# The production board is the one that gets photographed — assert it is faithful
# --------------------------------------------------------------------------- #

def test_the_production_fixture_carries_no_synthetic_row():
    su = production_fixture()
    for lane in ("buy", "watch", "laggards", "leaders", "ran", "vetoed"):
        strays = [r["ticker"] for r in su.get(lane) or []
                  if str(r.get("ticker", "")).startswith("88")]
        assert not strays, "%s carries a sample row: %r" % (lane, strays)


def test_no_display_lane_re_lists_a_name_the_board_already_placed():
    """The double-listing the review caught: one name, two stances, one page.

    The three display lanes claim in order, AFTER buy, watch and laggards have taken
    theirs — so a name can never carry a "market leader" chip in one section and a
    "the gate refused this" line in another.

    NOT asserted here: the watch↔laggards overlap (2331.HK on 2026-07-31).  Both
    lanes are drawn from the same scored universe by different keys and the builder
    has never excluded one from the other; it is pre-existing board behaviour, out of
    this change's scope, and it is recorded rather than silently normalised away.
    """
    su = production_fixture()
    board = {r["ticker"] for lane in ("buy", "watch", "laggards")
             for r in su.get(lane) or []}
    seen: dict[str, str] = {}
    for lane in ("leaders", "ran", "vetoed"):
        for row in su.get(lane) or []:
            tk = row["ticker"]
            assert tk not in board, "%s is on the board AND in %s" % (tk, lane)
            assert tk not in seen, "%s is in both %s and %s" % (tk, seen[tk], lane)
            seen[tk] = lane


def test_the_watch_lane_is_never_promoted_into_the_buy_lane():
    su = production_fixture()
    art = legacy_artifact()
    assert [r["ticker"] for r in su["buy"]] != []
    assert not ({r["ticker"] for r in su["buy"]}
                & {r["ticker"] for r in art["watch"]})
    assert len(su["buy"]) == len(art["buy"]), (
        "the buy lane is the cascade's, not the fixture's")


def test_the_production_board_stamps_the_keys_the_page_reads():
    su = production_fixture()
    assert su["board_definition"] == "hk_prophet_v2"
    assert su["rank_by"] == "hk_prophet_v2"
    assert isinstance(su["universe_excluded"], int)
    assert isinstance(su["universe_source_rows"], int)
    weights = su["ranking"]["weights"]
    assert sum(weights.values()) == pytest.approx(100.0), (
        "the artifact carries POINTS, not fractions — the footnote scales from the sum")
    assert su["ranking"]["definition"] == "hk_prophet_v2"


def test_the_vetoed_section_on_the_production_board_has_real_rows(prod_html):
    su = production_fixture()
    assert len(su["vetoed"]) >= 5
    seg = prod_html[prod_html.find('<div class="pbv" data-stage="blocked">'):]
    seg = seg[:seg.find('<p class="pb-fn">')]
    for row in su["vetoed"][:3]:
        assert row["ticker"] in seg
        assert row["blocked_reason_en"]


def test_the_laggards_strip_prints_its_own_sort_key_sign_correctly(prod_html):
    """MAJOR-2: the figure beside a laggard is the number the list is ordered by.

    It used to print `alpha` (the 3-month return z) beside a list ordered by the
    selection axis, so the column ran +6.60 between two negatives and the number
    argued against the lane it was on.
    """
    su = production_fixture()
    seg = prod_html[prod_html.find("Weakest selection edge"):]
    seg = seg[:seg.find("</p>", seg.find("<p style=\"margin:0;line-height:2\""))]
    keys = [r["laggard_z"] for r in su["laggards"]]
    assert keys == sorted(k for k in keys), "the strip must be printed in key order"
    for row in su["laggards"]:
        z = row["laggard_z"]
        expected = '<span class="%s">%+.2f</span>' % ("pos" if z > 0 else "neg", z)
        assert expected in seg, "%s prints %r" % (row["ticker"], expected)
    assert "%+.2f" % su["laggards"][0]["laggard_z"] in seg


def test_the_laggards_header_no_longer_claims_momentum(prod_html):
    assert "Weakest selection edge — distribution risk" in prod_html
    assert "选股优势最弱 — 派发风险" in prod_html
    assert "⚠ <span class=\"l-en\">Weakest</span>" not in prod_html
    # the momentum claim survives where it is still true — the knife chip
    assert "very weak trend — wait" in prod_html


def test_the_leaders_tooltip_states_the_real_tiebreak(prod_html):
    """M4: the α-tiebreak sentence described a field the HK engine never emits."""
    seg = _leaders_block(prod_html)
    assert "α only breaks ties" not in seg
    assert "α 仅用于分开名次并列的标的" not in prod_html
    assert "the plain 3-month return separates them" in seg
    assert "则先比未加成的3个月回报" in prod_html


def test_a_cohort_member_on_a_buy_card_carries_the_chip(prio_html):
    """M3 at the surface: the strip and the card say the same thing about one name."""
    su = shapes_fixture()
    chipped = [r for r in su["buy"] if r.get("leadership")]
    assert chipped, "the fixture must put a cohort member on the buy lane"
    for row in chipped:
        assert row["leadership"]["state_en"]
        assert row["ticker"] in prio_html
    assert "membership earns the card no points and changes nothing in the ranking" in prio_html


# --------------------------------------------------------------------------- #
# Ripening shelf (CN W8-R1 port, 2026-08-07) — rendered contract
# --------------------------------------------------------------------------- #

def _ripening_fixture() -> dict:
    """The production board plus two synthetic shelf rows (one per zone).

    Same convention as `shapes_fixture()`: obviously synthetic 88xx.HK "Sample
    Holdings" lines that can never be read as calls, and `production_fixture()`
    itself is never touched — the fidelity tests keep the photographed board
    synthetic-free.
    """
    su = dict(production_fixture())

    def _row(ticker: str, name: str, name_zh: str, zone: str, btc, stoch) -> dict:
        return {
            "ticker": ticker, "name": name, "name_zh": name_zh,
            "sector": "Industrials", "sector_zh": "工业",
            "zone": zone,
            "evidence": [f"2W MACD cross ~{btc} 2W-bars out"],
            "evidence_display": [{
                "en": f"time to turn: ~{btc} wk at this pace",
                "zh": f"距转向约{btc}周（按当前速度）",
                "receipt": f"2W MACD cross ~{btc} 2W-bars out"}],
            "reasons": ["2W stoch washout (stoch=%s)" % stoch],
            "imminence": btc, "w2_stoch": stoch, "w2_stoch_arrow": 1,
            "w1_cross_date": "2026-07-24", "w1_cross_bars_since": 1,
            "w1_d_at_cross": 18.0, "w1_from_washout": True,
            "spot_pct_in_range": 12.0, "ret_5d": -0.021,
            "macd_hist_d": 0.05, "macd_hist_slope": 1,
            "days_in_washout": 9, "price": 42.0,
            "display_only": True,
            "stance": "setup forming — no entry signal yet; watch, don't chase",
            "stance_zh": "形态形成中 — 入场信号未触发；观察，勿追高",
        }

    su["ripening"] = [
        _row("8810.HK", "Sample Holdings R", "样本控股丙", "READY", 1.5, 22.0),
        _row("8811.HK", "Sample Holdings S", "样本控股丁", "BASING", 4.0, 12.0),
    ]
    return su


@pytest.fixture(scope="module")
def ripening_html() -> str:
    return _render(_ripening_fixture())


def test_the_shelf_renders_inside_the_setting_up_bucket(ripening_html):
    """The shelf lives INSIDE the setting-up filter family — the vetoed-inside-
    blocked precedent — so the chip reveals it and counts it."""
    assert '<div class="rip-shelf" data-stage="setting_up"' in ripening_html
    assert ">RIPENING SHELF</span>" in ripening_html
    assert ">筑底观察区</span>" in ripening_html
    assert "NOT an entry signal" in ripening_html


def test_both_zones_render_with_their_cards(ripening_html):
    ready = ripening_html.find('<div class="rip-zone rz-ready">')
    basing = ripening_html.find('<div class="rip-zone rz-basing">')
    assert ready != -1 and basing != -1 and ready < basing
    assert 'href="hk_lookup.html#8810.HK"' in ripening_html
    assert 'href="hk_lookup.html#8811.HK"' in ripening_html
    assert ">共振形成中</span>" in ripening_html      # READY zh label
    assert ">筑底中</span>" in ripening_html          # BASING zh label


def test_shelf_evidence_is_plain_words_with_the_receipt_on_hover(ripening_html):
    assert "time to turn: ~1.5 wk at this pace" in ripening_html
    assert "距转向约1.5周（按当前速度）" in ripening_html
    assert 'data-tip-en="Technical: 2W MACD cross ~1.5 2W-bars out"' in ripening_html


def test_the_setting_up_chip_counts_the_shelf(ripening_html):
    """Chip counts come from rendered rows: buy-lane setting_up rows + shelf rows."""
    su = _ripening_fixture()
    lane_setting_up = sum(1 for r in su["buy"] if r.get("stage") == "setting_up")
    want = lane_setting_up + len(su["ripening"])
    m = re.search(
        r'data-stagepick="setting_up"[^>]*>.*?<span class="pbf-n">(\d+)</span>',
        ripening_html, re.S)
    assert m, "the Setting up chip must render when the shelf is populated"
    assert int(m.group(1)) == want


def test_the_shelf_speaks_no_buy_language(ripening_html):
    start = ripening_html.find('<div class="rip-shelf"')
    end = ripening_html.find('<div class="pbr"', start)
    shelf = ripening_html[start:end if end != -1 else None]
    for banned in ("v-buy", "Buy now", "买入", "BUY"):
        assert banned not in shelf, f"buy-family language inside the shelf: {banned!r}"


def test_fail_soft_without_the_key_and_on_the_legacy_schema(prod_html, legacy_html):
    """No `ripening` array (every pre-shelf artifact) → the shelf does not exist;
    the legacy pre-v1 schema renders none of the priority surface either."""
    assert '<div class="rip-shelf"' not in prod_html
    assert '<div class="rip-shelf"' not in legacy_html
