"""tests/test_intraday_flow_ncp_js.py — the Intraday Flow tracker's options-tape figure,
run against the REAL published payloads.

`intraday_flow.html.j2` labelled a figure `~Net call premium` / `~净看涨权利金` and derived a
`~call-heavy` / `~put-heavy` lean from its sign, while populating it from two net-TOTAL
sources:

  * `tickers/<ROOT>.json` → `day.net_soft`, which `build_ticker_json` computes as
    ``sum(ncp + npp)`` — net call premium PLUS net put premium;
  * `tide_current.json` → `top_net_impact[].net_prem_soft`, which `build_tide_current`
    computes as ``net_c + net_p`` — again a net total.

A net total is not a call figure and carries no side at all: it goes positive on put BUYING
and negative on put SELLING. So a name with calls being bought could print a negative
`~Net call premium` and read `~put-heavy`, and vice versa — the `~soft` tag covers the
Lee-Ready signing approximation, not a wrong numerator. The L5 confluence leg
(`~Options leaning in`, which feeds K/7 and the `act` stance gate) was worse than
mislabelled: it ANDed the SIGN of the net total with the DURABILITY of the call-only
`minutes[].ncp` series — two different series presented as one leg.

The fix re-sources the call-only figure from `minutes[last].ncp` — the cumulative net CALL
premium, the same array durability is scored on — and keeps the net total under its own
label in `net_all`. This mirrors `templates/stock.html.j2` (#4019) so the two surfaces
reading the same payload agree; `tests/test_stock_iflow_panel_js.py` is this suite's model.

A text assertion cannot catch that class — the old code was valid JS reading a real field
with a plausible name. So the JS is extracted from the shipped page and EXECUTED against
payloads built by `engine.live_flow.build_tide_current` / `build_ticker_json` and
`engine.flow_enrich.enrich_feed`, i.e. by the real builders. Node ships on CI + dev Macs;
the suite skips loudly when it is absent (mirrors tests/test_stock_iflow_panel_js.py).
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import flow_enrich as fe  # noqa: E402
from engine import live_flow as lf  # noqa: E402

HAS_NODE = shutil.which("node") is not None
needs_node = pytest.mark.skipif(not HAS_NODE, reason="node not on PATH")

TEMPLATE = ROOT / "templates" / "intraday_flow.html.j2"
SITE = ROOT / "site" / "intraday_flow.html"
PAGES = pytest.mark.parametrize("path", [TEMPLATE, SITE], ids=["template", "site"])

LEADER = "NVDA"          # on the board
OTHER_LEADER = "AMD"     # on the board, ranks below a non-leader in top_net_impact
NON_LEADER = "SPY"       # never on the board — dominates top_net_impact by premium
SESSION_DATE = "2026-07-02"
ASOF_TIDE = "2026-07-02T14:30:00Z"
ASOF_TICKER = "2026-07-02T14:30:30Z"
ASOF_ENRICH = "2026-07-02T14:31:00Z"

DUR_MIN = 0.60


# ═══════════════════════════════════════════════════════════════════════════════
# Payloads — built by the real builders, never hand-written
# ═══════════════════════════════════════════════════════════════════════════════

def _root_minutes(ncp_deltas: list[float], npp_total: float) -> dict:
    """Per-minute signed premium for one root.

    `ncp_deltas` are the per-minute net CALL premium deltas; build_ticker_json turns them
    into the CUMULATIVE minutes[] series the page reads. `npp_total` lands on the last
    minute, so day.net_soft (= ncp+npp) stays distinct from — and here opposite in sign
    to — the cumulative NCP.
    """
    minutes: dict[str, dict] = {}
    for i, d in enumerate(ncp_deltas):
        mkey = f"{9 + (30 + i) // 60:02d}:{(30 + i) % 60:02d}"
        minutes[mkey] = {"ncp": float(d), "npp": 0.0, "vol": 10}
    minutes[sorted(minutes)[-1]]["npp"] = float(npp_total)
    return minutes


def _day_state(roots: dict[str, tuple[list[float], float]]) -> dict:
    """A day_state carrying `roots` = {root: (ncp_deltas, npp_total)}."""
    root_minutes = {r: _root_minutes(d, n) for r, (d, n) in roots.items()}
    market: dict[str, dict] = {}
    for rmin in root_minutes.values():
        for t, m in rmin.items():
            mm = market.setdefault(t, {"ncp": 0.0, "npp": 0.0, "gross": 0.0, "vol": 0})
            mm["ncp"] += m["ncp"]
            mm["npp"] += m["npp"]
            mm["vol"] += m["vol"]
    return {
        "root_minutes": root_minutes,
        "market_tide_minutes": market,
        "sector_tide": {},
        # Gross ranks nothing here; top_net_impact sorts on |net_prem_soft|.
        "root_gross_today": {r: 1_000_000.0 for r in root_minutes},
        "root_strikes": {r: {"550.0": {"call_prem": 5e4, "put_prem": 2e4, "vol": 200}} for r in root_minutes},
        "root_expiries": {r: {"2026-07-05": {"call_prem": 4e4, "put_prem": 3e4, "vol": 200}} for r in root_minutes},
        "root_top_contracts": {r: [] for r in root_minutes},
    }


def _tide(day_state: dict) -> dict:
    """A real live_flow.tide/v1 payload."""
    return lf.build_tide_current(SESSION_DATE, ASOF_TIDE, day_state)


def _ticker(root: str, day_state: dict) -> dict:
    """A real live_flow.ticker/v1 payload."""
    return lf.build_ticker_json(root, SESSION_DATE, ASOF_TICKER, day_state)


def _enrich(root: str = LEADER) -> dict:
    """A real flow.enrich/v1 envelope with one event on `root`."""
    ev = dict(
        id="ev1", ts=f"{SESSION_DATE}T14:00:00Z",
        root=root, right="C", exp="2026-07-18", strike=800.0,
        dte=10, dte_bucket="8_30d", mny_bucket="atm",
        side="~buy", signing_source="tape",
        premium=5_000_000, premium_z=4.0,
        vol_gt_oi=True, repeated=False, n_prints=1,
        swept=True, zerodte=False,
        group="Technology", group_zh="科技",
        size=100, avg_price=10.0, baseline_source="z252",
    )
    feed = {"schema": "live_flow.feed/v1", "asof": ASOF_ENRICH,
            "session_date": SESSION_DATE, "events": [ev]}
    return fe.enrich_feed(feed, ASOF_ENRICH)


# ═══════════════════════════════════════════════════════════════════════════════
# Extract the page's JS and run it under node
# ═══════════════════════════════════════════════════════════════════════════════

def _region(src: str, start: str, end: str) -> str:
    i = src.index(start)
    return src[i:src.index(end, i)]


# Every region below is Jinja-free; the page's only {{ }} in this half sits inside
# updateFlowStamp, which is stubbed by the harness rather than extracted.
REGIONS = (
    ("function snapUrl", "function computeLegs"),   # url helpers, ET clock, derived metrics
    ("function computeLegs", "function dealerOf"),  # the confluence legs incl. L5
    ("var flowMeta", "function updateFlowStamp"),  # fetchFlow, bestTier, fetchRootFlow
)


def _flow_js(path: Path) -> str:
    src = path.read_text(encoding="utf-8")
    return "\n".join(_region(src, a, b) for a, b in REGIONS)


def _run(
    path: Path,
    *,
    tide,
    tickers: dict[str, dict],
    enrich,
    meta=None,
    leaders=(LEADER, OTHER_LEADER),
) -> dict:
    """Execute fetchFlow() against the payloads; return flowState + legs + fetched URLs.

    `tickers` maps root -> payload; a root absent from it serves a non-ok response, which
    is how a per-root 404 (or a root the page never deepened) reaches the render.
    """
    script = textwrap.dedent(
        """
        var TIDE = %(tide)s, TICKERS = %(tickers)s, ENRICH = %(enrich)s, META = %(meta)s;
        var DUR_MIN = %(dur_min)s, RVOL_CONFIRM = 1.30, WASHOUT_LB = 10;
        var LEADERS_BY_TK = %(leaders)s;
        var flowState = {}, flowAsof = null, flowRTH = false;
        var window = {DATA_BASE: 'https://data.example.test/'};
        var FETCHED = [];
        function render() {}
        function scheduleRender() {}
        function updateFlowStamp() {}
        globalThis.fetch = function (url) {
          FETCHED.push(url);
          var body = null;
          if (/tide_current/.test(url)) body = TIDE;
          else if (/enrich_current/.test(url)) body = ENRICH;
          else if (/meta[.]json/.test(url)) body = META;
          else {
            var m = /tickers\\/([^.]+)\\.json/.exec(url);
            if (m) body = Object.prototype.hasOwnProperty.call(TICKERS, m[1]) ? TICKERS[m[1]] : null;
          }
          return Promise.resolve({ok: body !== null, json: function () { return Promise.resolve(body); }});
        };
        %(js)s
        fetchFlow();
        // The mocked fetch resolves synchronously, so one macrotask lands after every
        // microtask — including the per-root wave fetchFlow starts from its own .then.
        setTimeout(function () {
          var out = {flowState: flowState, asof: flowAsof, meta: flowMeta, fetched: FETCHED, legs: {}, K: {}};
          Object.keys(LEADERS_BY_TK).forEach(function (tk) {
            var conf = computeLegs({}, null, null, flowState[tk] || null);
            out.legs[tk] = conf.legs;
            out.K[tk] = conf.K;
          });
          process.stdout.write(JSON.stringify(out));
        }, 20);
        """
    ) % {
        "tide": json.dumps(tide),
        "tickers": json.dumps(tickers),
        "enrich": json.dumps(enrich),
        "meta": json.dumps(meta),
        "dur_min": json.dumps(DUR_MIN),
        "leaders": json.dumps({t: {"ticker": t} for t in leaders}),
        "js": _flow_js(path),
    }
    res = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=30)
    assert res.returncode == 0, f"node failed:\nSTDERR:\n{res.stderr}\nSTDOUT:\n{res.stdout}"
    assert res.stdout.strip(), f"no stdout; stderr:\n{res.stderr}"
    return json.loads(res.stdout)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. The figure is the net CALL premium — the sign-inversion the old numerator caused
# ═══════════════════════════════════════════════════════════════════════════════

@needs_node
@PAGES
def test_calls_bought_while_the_net_total_is_negative(path):
    """Calls net BOUGHT, puts net SOLD → the net total is negative, the call figure is not.

    This is the inversion in the report: `day.net_soft` and `top_net_impact[].net_prem_soft`
    both come out at −1000 while cumulative NCP is +1000, so the old code printed a negative
    `~Net call premium`, read `~put-heavy`, and held L5 down on a name whose calls were bid.
    """
    ds = _day_state({LEADER: ([100.0] * 10, -2000.0)})
    tide, ticker = _tide(ds), _ticker(LEADER, ds)

    # The two net-TOTAL sources agree with each other and disagree in SIGN with the calls.
    assert ticker["day"]["net_soft"] == pytest.approx(-1000.0)
    assert ticker["minutes"][-1]["ncp"] == pytest.approx(1000.0)
    tide_row = next(r for r in tide["top_net_impact"] if r["root"] == LEADER)
    assert tide_row["net_prem_soft"] == pytest.approx(-1000.0)

    out = _run(path, tide=tide, tickers={LEADER: ticker}, enrich=None)
    flow = out["flowState"][LEADER]

    assert flow["ncp"] == pytest.approx(1000.0), "call figure must be cumulative NCP"
    assert flow["net_all"] == pytest.approx(-1000.0), "the net total keeps its own name"
    assert flow["ncp"] > 0 > flow["net_all"], "the sign inversion this fix is about"
    # L5 = ~Options leaning in: calls bid and durable → the leg fires. Was false.
    assert flow["flow_dur"] == pytest.approx(1.0)
    assert out["legs"][LEADER][4] is True


@needs_node
@PAGES
def test_calls_sold_while_the_net_total_is_positive(path):
    """The mirror: calls net SOLD, puts net BOUGHT → old code read `~call-heavy` and fired
    L5 (`~Options leaning in`) off put buying."""
    ds = _day_state({LEADER: ([-100.0] * 10, 2000.0)})
    tide, ticker = _tide(ds), _ticker(LEADER, ds)
    assert ticker["day"]["net_soft"] == pytest.approx(1000.0)
    assert ticker["minutes"][-1]["ncp"] == pytest.approx(-1000.0)

    out = _run(path, tide=tide, tickers={LEADER: ticker}, enrich=None)
    flow = out["flowState"][LEADER]

    assert flow["ncp"] == pytest.approx(-1000.0)
    assert flow["net_all"] == pytest.approx(1000.0)
    assert flow["ncp"] < 0 < flow["net_all"]
    assert out["legs"][LEADER][4] is False, "a leg named ~Options leaning in may not fire on put buying"


@needs_node
@PAGES
def test_ncp_and_durability_are_scored_on_the_same_series(path):
    """L5 ANDs the sign of `ncp` with `flow_dur`; both must come off minutes[].ncp.

    Rising then falling call premium: durability 0.5 < 0.60 → L5 false on a POSITIVE ncp.
    A leg that read one series for the sign and another for durability could not express
    this state. Put premium is kept non-zero and opposite, so the net total is −1300 while
    the call series is +1300 — the old read got the sign of the leg's own input backwards.
    """
    ds = _day_state({LEADER: ([300.0] * 6 + [-100.0] * 5, -2600.0)})
    ticker = _ticker(LEADER, ds)
    out = _run(path, tide=_tide(ds), tickers={LEADER: ticker}, enrich=None)
    flow = out["flowState"][LEADER]

    assert flow["ncp"] == pytest.approx(ticker["minutes"][-1]["ncp"])
    assert flow["ncp"] > 0
    assert flow["flow_dur"] == pytest.approx(0.5)
    assert out["legs"][LEADER][4] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 2. The tide seed is a net total and stays one
# ═══════════════════════════════════════════════════════════════════════════════

@needs_node
@PAGES
def test_tide_alone_never_supplies_a_call_figure(path):
    """With the per-root payload absent, top_net_impact fills net_all only.

    `net_prem_soft` cannot yield a call-only number, so the page holds no `ncp`, prints
    `side unknown` rather than a lean, and leaves L5 unknown rather than claiming a ✗.
    """
    ds = _day_state({LEADER: ([100.0] * 10, -2000.0)})
    out = _run(path, tide=_tide(ds), tickers={}, enrich=None)   # every per-root fetch 404s
    flow = out["flowState"][LEADER]

    assert flow.get("net_all") == pytest.approx(-1000.0)
    assert flow.get("ncp") is None, "a net total may not populate the call figure"
    assert flow.get("flow_dur") is None
    assert out["legs"][LEADER][4] is None, "unknown, not false — there is no call read"


@needs_node
@PAGES
def test_absent_tape_claims_nothing(path):
    """Fail-soft preserved: no payloads at all → no state, no leg claim, no throw."""
    out = _run(path, tide=None, tickers={}, enrich=None)
    assert out["flowState"] == {}
    assert out["legs"][LEADER][4] is None


@needs_node
@PAGES
def test_enrich_badges_do_not_synthesise_a_lean(path):
    """A root known only from enrich events gets badges and tier — never a premium figure."""
    out = _run(path, tide=None, tickers={}, enrich=_enrich(LEADER))
    flow = out["flowState"][LEADER]
    assert flow["badges"], "badges still aggregate off the flat events[]"
    assert flow.get("ncp") is None and flow.get("net_all") is None
    assert out["asof"] == ASOF_ENRICH


@needs_node
@PAGES
def test_meta_v2_source_clock_wins_over_newer_derivative_build_clocks(path):
    """The page stamps represented source age, not a newer tide/enrich rebuild."""
    ds = _day_state({LEADER: ([100.0] * 10, -2000.0)})
    source_asof = "2026-07-02T14:29:00Z"
    meta = {
        "schema": "live_flow.meta/v2",
        "asof": source_asof,
        "built_at": "2026-07-02T14:32:00Z",
        "poll_floor_sec": 120,
        "cycle_started_at": "2026-07-02T14:31:00Z",
        "observed_start_to_start_sec": 605.0,
        "fetch_compute_sec": 61.0,
        "source_response_at_first": source_asof,
        "source_response_at_last": source_asof,
        "roots_requested": 1,
        "roots_with_source_payload": 1,
    }
    out = _run(
        path,
        tide=_tide(ds),
        tickers={LEADER: _ticker(LEADER, ds)},
        enrich=_enrich(LEADER),
        meta=meta,
    )
    assert out["asof"] == source_asof
    assert out["meta"] == meta
    assert any(url.endswith("live_flow/meta.json") for url in out["fetched"])


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Coverage — every board name in the tide gets the call-only series
# ═══════════════════════════════════════════════════════════════════════════════

@needs_node
@PAGES
def test_the_board_deepens_its_own_names_not_the_market_top(path):
    """top_net_impact is ranked market-wide, so its head is index roots the board never
    shows. Deepening the leaders in it is what makes the call figure reachable for a name
    that ranks below them — under the old blind first-N slice such a name could only ever
    carry the net total, i.e. no lawful lean at all."""
    ds = _day_state({
        NON_LEADER:   ([9_000.0] * 10, 0.0),   # ranks first, never on the board
        LEADER:       ([100.0] * 10, -2000.0),
        OTHER_LEADER: ([50.0] * 10, 0.0),
    })
    tide = _tide(ds)
    assert tide["top_net_impact"][0]["root"] == NON_LEADER
    tickers = {r: _ticker(r, ds) for r in (NON_LEADER, LEADER, OTHER_LEADER)}
    out = _run(path, tide=tide, tickers=tickers, enrich=None)

    deepened = {m.group(1) for m in (re.search(r"tickers/([^.]+)\.json", u) for u in out["fetched"]) if m}
    assert deepened == {LEADER, OTHER_LEADER}, f"deepened the wrong roots: {deepened}"
    # Both board names carry a real call figure, not just the net total.
    for tk in (LEADER, OTHER_LEADER):
        assert out["flowState"][tk]["ncp"] == pytest.approx(1000.0 if tk == LEADER else 500.0)
    assert "ncp" not in out["flowState"].get(NON_LEADER, {})


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Copy — each label sits next to the field it names
# ═══════════════════════════════════════════════════════════════════════════════

def _line_with(src: str, needle: str) -> str:
    lines = [ln for ln in src.splitlines() if needle in ln]
    assert len(lines) == 1, f"expected exactly 1 line containing {needle!r}, found {len(lines)}"
    return lines[0]


@PAGES
def test_the_call_premium_row_is_fed_by_the_call_figure(path):
    """A regression guard, not a defect pin — this row always read `flow.ncp`; what the fix
    changed is what `flow.ncp` HOLDS (see §1). It fires if the row is ever re-pointed at a
    net total, which is how the mismatch arrived in the first place."""
    src = path.read_text(encoding="utf-8")
    row = _line_with(src, "'~Net call premium'")
    assert "flow.ncp" in row
    assert "net_all" not in row and "net_soft" not in row


@PAGES
def test_the_net_total_has_its_own_labelled_row(path):
    """Nothing is deleted — the net total keeps a Tier-3 home under an accurate label."""
    src = path.read_text(encoding="utf-8")
    row = _line_with(src, "'~Net premium (calls+puts)'")
    assert "~净权利金（看涨+看跌）" in row, "bilingual parity"
    assert "flow.net_all" in row


@PAGES
def test_the_lean_words_follow_the_call_only_series(path):
    """`~put-heavy` on a negative net CALL premium claims a put read we never measured, so
    the glance words state the call side: bought or sold. Both sites move together."""
    src = path.read_text(encoding="utf-8")
    assert "~put-heavy" not in src and "~call-heavy" not in src
    assert "~偏看涨" not in src and "~偏看跌" not in src
    lines = src.splitlines()
    hits = [i for i, ln in enumerate(lines) if "~call buying" in ln]
    assert len(hits) == 2, "spotlight card + board row"
    for i in hits:
        assert "~call selling" in lines[i] and "~买入看涨" in lines[i] and "~卖出看涨" in lines[i]
        # The branch that emits these words — its guard and the sign it switches on.
        block = "\n".join(lines[max(0, i - 3):i + 1])
        assert ".ncp" in block, "the lean must read the call-only series"
        assert "net_all" not in block, "a net total states no side"


@PAGES
def test_the_unknown_side_is_disclosed_in_plain_words(path):
    """A name carrying only the net total is not a quiet tape — say what is unknown."""
    src = path.read_text(encoding="utf-8")
    assert src.count("lz('side unknown','方向未知')") == 2, "spotlight card + board row"


@PAGES
def test_flow_copy_makes_no_fixed_cadence_or_unstamped_live_claim(path):
    src = path.read_text(encoding="utf-8")
    assert "2-3min RTH" not in src
    assert "asof ? 'as of '+asof : 'live'" not in src
    assert "asof ? '截至 '+asof : '实时'" not in src
    assert "last-session source as of" in src
    assert "上一交易时段来源截至" in src


@needs_node
def test_template_and_site_copies_agree():
    """site/intraday_flow.html is rendered from the template by scripts/build_intraday_flow.py;
    these regions are Jinja-free, so the two must be byte-identical or the live page and the
    source disagree."""
    assert _flow_js(TEMPLATE) == _flow_js(SITE)


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Boot regression — RTH first render with empty quote/pulse/flow state
# ═══════════════════════════════════════════════════════════════════════════════

# Regions needed for computeAll + computeStance (Jinja-free; no network calls).
# dealerOf sits between computeLegs and computeStance; computeAll comes after the
# stamp and format helpers.
BOOT_REGIONS = (
    ("var STANCE_META", "function snapUrl"),           # STANCE_META
    ("function snapUrl", "function computeLegs"),      # url/ET helpers, derived metrics
    ("function computeLegs", "function dealerOf"),     # computeLegs (incl. L5)
    ("function dealerOf", "function fmtNum"),          # dealerOf, quotePx, computeStance
    ("function computeAll", "function laneCounts"),    # computeAll
)


def _boot_js(path: Path) -> str:
    src = path.read_text(encoding="utf-8")
    return "\n".join(_region(src, a, b) for a, b in BOOT_REGIONS)


# Production-shaped AAPL fixture matching the verified crash context:
# opex_days=2, regime='long', call_wall=320, put_wall=290, magnet_up=320,
# magnet_down=315 — pin-watch branch fires unless quote is absent/null.
AAPL_LEADER = {
    "ticker": "AAPL",
    "options_entry": {
        "dealer": {
            "regime": "long",
            "opex_days": 2,
            "call_wall": 320,
            "put_wall": 290,
            "magnet_up": 320,
            "magnet_down": 315,
            "call_wall_hard": False,
            "call_wall_dist_sigma": None,
            "expected_move_daily_pct": None,
        },
        "evidence_quality": None,
    },
    "vol_squeeze": {"coiled": False},
    "adv20_shares": 60_000_000,
    "vol_share_curve": [],
}

VALID_LANE_KEYS = {"act", "get_ready", "in_favour", "take_profits", "watch", "stand_aside"}


def _boot_run(
    path: Path,
    *,
    market_hours: bool,
    leader: dict,
    quoteState: dict,  # noqa: N803
    pulseState: dict,  # noqa: N803
    flowState: dict,   # noqa: N803
) -> dict:
    """Execute computeAll() in a minimal harness; return rows + per-row stance/conf."""
    # _etMinutes stub: 630 = 10:30 ET (well inside RTH 565–965)
    et_minutes = 630 if market_hours else 300   # 10:30 or 05:00 ET
    script = textwrap.dedent(
        """
        var DUR_MIN = %(dur_min)s, RVOL_CONFIRM = 1.30, WASHOUT_LB = 10;
        var quoteState = %(quoteState)s;
        var pulseState = %(pulseState)s;
        var flowState  = %(flowState)s;
        var quotesStatus = 'connecting', pulseStatus = 'connecting', flowStatus = 'connecting';
        var leaders = %(leaders)s;
        var LEADERS_BY_TK = {};
        leaders.forEach(function(l){ LEADERS_BY_TK[l.ticker] = l; });
        function _etMinutes(){ return %(et_minutes)s; }
        var window = {};
        function document_stub() { return { getElementById: function(){ return null; } }; }
        var document = document_stub();
        %(js)s
        var rows = computeAll();
        var q0 = quoteState[leaders[0].ticker] || null;
        var out = { quotePx: quotePx(q0), rows: rows.map(function(r){
          return {
            ticker: r.l.ticker,
            stKey:  r.st.key,
            conf_legs: r.conf.legs,
            conf_K:    r.conf.K,
          };
        }) };
        process.stdout.write(JSON.stringify(out));
        """
    ) % {
        "dur_min": json.dumps(DUR_MIN),
        "quoteState": json.dumps(quoteState),
        "pulseState": json.dumps(pulseState),
        "flowState": json.dumps(flowState),
        "leaders": json.dumps([leader]),
        "et_minutes": et_minutes,
        "js": _boot_js(path),
    }
    res = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=30)
    assert res.returncode == 0, (
        f"node exited {res.returncode}:\nSTDERR:\n{res.stderr}\nSTDOUT:\n{res.stdout}"
    )
    assert res.stdout.strip(), f"no stdout; stderr:\n{res.stderr}"
    return json.loads(res.stdout)


@needs_node
@PAGES
def test_boot_empty_state_rth_no_throw(path):
    """First render during RTH with all state empty must not throw — this is the crash.

    AAPL's dealer has opex_days=2 and regime='long', which arms the pin-watch branch.
    Old code: quote.price on null quote → TypeError. New code: quotePx(null) → null → skip.
    """
    out = _boot_run(
        path,
        market_hours=True,
        leader=AAPL_LEADER,
        quoteState={},
        pulseState={},
        flowState={},
    )
    assert len(out["rows"]) >= 1, "computeAll must return at least one row"
    row = out["rows"][0]
    assert row["ticker"] == "AAPL"
    assert row["stKey"] in VALID_LANE_KEYS, f"stance key {row['stKey']!r} is not a valid lane"


@needs_node
@PAGES
def test_boot_empty_state_rth_l5_is_unknown_not_false(path):
    """L5 (Options leaning in) must be null/None when flow is absent, not false.

    False means 'known-negative'; null means 'no evidence'. Collapsing unknown evidence
    to false would block the act gate for a name whose options tape simply hasn't loaded.
    """
    out = _boot_run(
        path,
        market_hours=True,
        leader=AAPL_LEADER,
        quoteState={},
        pulseState={},
        flowState={},
    )
    row = out["rows"][0]
    legs = row["conf_legs"]
    assert legs[4] is None, (
        f"L5 must be null (unknown) when flow is absent, got {legs[4]!r}"
    )


@needs_node
@PAGES
def test_boot_empty_state_rth_quote_px_null(path):
    """Missing quote must yield quotePx === null so pin-watch cannot invent a distance.

    take_profits is independently unreachable without a quote (aboveVwap is false),
    so this asserts the pin-watch *input* rather than a downstream lane that cannot
    fire either way.
    """
    out = _boot_run(
        path,
        market_hours=True,
        leader=AAPL_LEADER,
        quoteState={},
        pulseState={},
        flowState={},
    )
    assert out["quotePx"] is None
    assert out["rows"][0]["stKey"] != "take_profits"


@needs_node
@PAGES
def test_boot_quote_arrives_no_throw(path):
    """Second computeAll call with a real quote must not throw and may update stance."""
    # First pass: empty state (proves fix).
    out_empty = _boot_run(
        path,
        market_hours=True,
        leader=AAPL_LEADER,
        quoteState={},
        pulseState={},
        flowState={},
    )
    assert out_empty["rows"][0]["ticker"] == "AAPL"

    # Second pass: quote present (price well away from walls → pinWatch false → no crash).
    out_quoted = _boot_run(
        path,
        market_hours=True,
        leader=AAPL_LEADER,
        quoteState={"AAPL": {"price": 180.0, "changePct": 1.5, "vol": 10_000_000,
                              "hi": 182.0, "lo": 178.0}},
        pulseState={},
        flowState={},
    )
    row = out_quoted["rows"][0]
    assert row["ticker"] == "AAPL"
    assert row["stKey"] in VALID_LANE_KEYS


@needs_node
@PAGES
def test_boot_quote_near_pin_take_profits(path):
    """Price within 1% of call_wall plus a VWAP below it must land take_profits.

    Positive control that pin-watch still fires when evidence exists (call_wall=320,
    price=321 → ~0.31%). Empty-state tests prove the null path; this proves the live path.
    """
    out = _boot_run(
        path,
        market_hours=True,
        leader=AAPL_LEADER,
        quoteState={"AAPL": {"price": 321.0, "changePct": 0.5, "vol": 5_000_000,
                              "hi": 322.0, "lo": 319.0}},
        pulseState={"AAPL": {"vwap": 300.0, "bars_today": 20, "vol_durability": 0.5,
                              "rvol_tod": 1.0}},
        flowState={},
    )
    row = out["rows"][0]
    assert row["ticker"] == "AAPL"
    assert row["stKey"] == "take_profits"


def test_the_net_total_sources_are_still_net_totals():
    """Documents WHY the reads changed — and fires if either builder ever narrows its field
    to calls only, which would make `net_all` a lie in the other direction."""
    ds = _day_state({LEADER: ([100.0] * 10, -2000.0)})
    ticker, tide = _ticker(LEADER, ds), _tide(ds)
    cum_ncp = ticker["minutes"][-1]["ncp"]
    cum_npp = ticker["minutes"][-1]["npp"]
    assert ticker["day"]["net_soft"] == pytest.approx(cum_ncp + cum_npp)
    row = next(r for r in tide["top_net_impact"] if r["root"] == LEADER)
    assert row["net_prem_soft"] == pytest.approx(cum_ncp + cum_npp)
    # And the call-only series the page now reads is genuinely published.
    assert ticker["minutes"] and "ncp" in ticker["minutes"][0]
