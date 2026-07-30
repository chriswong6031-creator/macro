"""tests/test_stock_iflow_panel_js.py — the stock page's inline flow panel, run against the
REAL published payloads.

The panel's `_iflowLoadFlow` shipped reading a rollup shape that no endpoint ever published:
`tickerData.cum_ncp`, `tickerData.flow_dur`, `tickerData.meta.asof` and `enrich.tickers{}`.
`live_flow.ticker/v1` publishes top-level `asof` + `day{}` + cumulative `minutes[]`, and
`flow.enrich/v1` publishes top-level `asof` + a FLAT `events[]`. Every read was therefore
`undefined`, and nothing threw — so four chips (~net call prem, session tier, badges) plus
the L5 `~flow bid` confluence leg dark-rendered forever, the options as-of stamp never
appeared, and K/7 was structurally capped at 6. The identical reads were fixed on
intraday_flow.html.j2 in #2391 ("fixed live flow"); this copy was left behind.

A text assertion cannot catch that class — the old code was valid JS reading plausible field
names. So the JS is extracted from the shipped page and EXECUTED against payloads built by
`engine.live_flow.build_ticker_json` and `engine.flow_enrich.enrich_feed`, i.e. by the real
builders. If either schema moves again, these tests fail instead of the panel going quietly
dark. Node ships on CI + dev Macs; the suite skips loudly when it is absent (mirrors
tests/test_watchlist_chains_js.py).
"""
from __future__ import annotations

import json
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

TEMPLATE = ROOT / "templates" / "stock.html.j2"
SITE = ROOT / "site" / "stock.html"

ROOT_SYM = "SPY"
SESSION_DATE = "2026-07-02"
ASOF_TICKER = "2026-07-02T14:30:00Z"
ASOF_ENRICH = "2026-07-02T14:31:00Z"

# The badge order the panel renders, and the tier ladder it ranks on.
BADGE_ORDER = ["WHALE", "FRESH", "Z_OUTLIER", "SIZE_VS_OI", "REPEAT_HITTER"]


# ═══════════════════════════════════════════════════════════════════════════════
# Payloads — built by the real builders, never hand-written
# ═══════════════════════════════════════════════════════════════════════════════

def _day_state(ncp_deltas: list[float], npp_on_last: float = -300.0) -> dict:
    """A root_minutes day_state whose per-minute NCP deltas are `ncp_deltas`.

    build_ticker_json turns these into the CUMULATIVE minutes[] series the panel reads.
    npp_on_last keeps day.net_soft (= ncp+npp) distinct from the cumulative NCP, so a
    test can tell the two apart.
    """
    minutes = {}
    for i, d in enumerate(ncp_deltas):
        mkey = f"{9 + (30 + i) // 60:02d}:{(30 + i) % 60:02d}"
        minutes[mkey] = {"ncp": float(d), "npp": 0.0, "vol": 10}
    last = sorted(minutes)[-1]
    minutes[last]["npp"] = float(npp_on_last)
    return {
        "root_minutes": {ROOT_SYM: minutes},
        "root_strikes": {ROOT_SYM: {"550.0": {"call_prem": 50000.0, "put_prem": 20000.0, "vol": 200}}},
        "root_expiries": {ROOT_SYM: {"2026-07-05": {"call_prem": 40000.0, "put_prem": 30000.0, "vol": 200}}},
        "root_top_contracts": {ROOT_SYM: [
            {"right": "C", "exp": "2026-07-05", "strike": 550.0,
             "premium": 50000.0, "vol": 200, "vol_gt_oi": True},
        ]},
        "root_gross_today": {ROOT_SYM: 140000.0},
    }


def _ticker_payload(ncp_deltas: list[float], npp_on_last: float = -300.0) -> dict:
    """A real live_flow.ticker/v1 payload."""
    return lf.build_ticker_json(ROOT_SYM, SESSION_DATE, ASOF_TICKER,
                                _day_state(ncp_deltas, npp_on_last))


def _mk_event(root: str = ROOT_SYM, **over) -> dict:
    """A minimal live_flow.feed/v1 event for enrich_feed."""
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
    ev.update(over)
    return ev


def _enrich_payload(events: list[dict]) -> dict:
    """A real flow.enrich/v1 envelope."""
    feed = {"schema": "live_flow.feed/v1", "asof": ASOF_ENRICH,
            "session_date": SESSION_DATE, "events": events}
    return fe.enrich_feed(feed, ASOF_ENRICH)


# ═══════════════════════════════════════════════════════════════════════════════
# Extract the panel's JS from the shipped page and run it under node
# ═══════════════════════════════════════════════════════════════════════════════

def _region(src: str, start: str, end: str) -> str:
    i = src.index(start)
    j = src.index(end, i)
    return src[i:j]


def _panel_js(path: Path) -> str:
    """The loader + the leg computation, verbatim from the page. Both are Jinja-free."""
    src = path.read_text(encoding="utf-8")
    return "\n".join([
        _region(src, "function _iflowComputeLegs", "function _iflowRenderPanel"),
        _region(src, "function _iflowFlowDur", "function renderIFlow"),
    ])


def _run(path: Path, ticker: dict | None, enrich: dict | None, body: str = "") -> dict:
    """Execute the panel JS against the given payloads; return its JSON stdout."""
    script = textwrap.dedent(
        """
        var TICKER = %(ticker)s, ENRICH = %(enrich)s;
        var _iflowFlow = {}, _iflowFlowAsof = null;
        var IFLOW_DUR_MIN = 0.60, IFLOW_WASHOUT_LB = 10, IFLOW_RVOL_CONFIRM = 1.30;
        var window = {DATA_BASE: 'https://data.example.test/'};
        var FETCHED = [];
        globalThis.fetch = function (url) {
          FETCHED.push(url);
          var body = /enrich_current/.test(url) ? ENRICH : TICKER;
          return Promise.resolve({ok: body !== null, json: function () { return Promise.resolve(body); }});
        };
        %(js)s
        _iflowLoadFlow(%(root)s, function () {
          var flow = _iflowFlow[%(root)s] || null;
          var out = {flow: flow, asof: _iflowFlowAsof, fetched: FETCHED,
                     legs: _iflowComputeLegs({}, null, flow).legs,
                     K: _iflowComputeLegs({}, null, flow).K};
          %(body)s
          process.stdout.write(JSON.stringify(out));
        });
        """
    ) % {
        "ticker": json.dumps(ticker),
        "enrich": json.dumps(enrich),
        "js": _panel_js(path),
        "root": json.dumps(ROOT_SYM),
        "body": body,
    }
    res = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=30)
    assert res.returncode == 0, f"node failed:\nSTDERR:\n{res.stderr}\nSTDOUT:\n{res.stdout}"
    assert res.stdout.strip(), f"no stdout; stderr:\n{res.stderr}"
    return json.loads(res.stdout)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. The reads land — the whole point. Every one of these was undefined/null before.
# ═══════════════════════════════════════════════════════════════════════════════

@needs_node
@pytest.mark.parametrize("path", [TEMPLATE, SITE], ids=["template", "site"])
def test_panel_populates_from_real_payloads(path):
    """~net call prem, flow durability, badges, session tier and the as-of stamp all fill in."""
    ticker = _ticker_payload([100.0] * 11)          # 11 cumulative minutes, all rising
    enrich = _enrich_payload([_mk_event()])
    out = _run(path, ticker, enrich)
    flow = out["flow"]

    assert flow is not None
    # Final cumulative NCP = 11 × 100. Was `tickerData.cum_ncp` → undefined.
    assert flow["ncp"] == pytest.approx(1100.0)
    # Every 5-min window positive. Was `tickerData.flow_dur` → undefined.
    assert flow["flow_dur"] == pytest.approx(1.0)
    # Aggregated off the flat events[]. Was `enrich.tickers[t].badge_counts` → undefined.
    assert flow["badges"], "badges never aggregated from enrich events[]"
    assert all("×" in b for b in flow["badges"])
    assert all(b.split("×")[0] in BADGE_ORDER for b in flow["badges"])
    assert flow["session_tier"], "session_tier never picked up from enrich events[]"
    # Top-level asof on flow.enrich/v1. Was `enrich.meta.asof` → undefined → stamp absent.
    assert out["asof"] == ASOF_ENRICH


@needs_node
@pytest.mark.parametrize("path", [TEMPLATE, SITE], ids=["template", "site"])
def test_asof_falls_back_to_ticker_top_level(path):
    """With enrich down, the stamp still shows — from the ticker payload's TOP-LEVEL asof.

    The retired fallback read `tickerData.meta.asof`; live_flow.ticker/v1 has no `meta`.
    """
    out = _run(path, _ticker_payload([100.0] * 11), None)
    assert out["asof"] == ASOF_TICKER


# ═══════════════════════════════════════════════════════════════════════════════
# 2. ~net call prem means net CALL premium — not the net total
# ═══════════════════════════════════════════════════════════════════════════════

@needs_node
@pytest.mark.parametrize("path", [TEMPLATE, SITE], ids=["template", "site"])
def test_ncp_is_cumulative_net_call_premium_not_day_net_soft(path):
    """The chip is labelled `~net call prem`, and L5 is defined on cum NCP.

    day.net_soft is ncp+npp — a net TOTAL. Reading it would mislabel puts as call premium
    and feed L5 a different series than the durability it is ANDed with.
    """
    ticker = _ticker_payload([100.0] * 11, npp_on_last=-300.0)
    assert ticker["day"]["net_soft"] == pytest.approx(800.0)   # 1100 + (-300)
    out = _run(path, ticker, None)
    assert out["flow"]["ncp"] == pytest.approx(1100.0)
    assert out["flow"]["ncp"] != pytest.approx(ticker["day"]["net_soft"])


# ═══════════════════════════════════════════════════════════════════════════════
# 3. L5 (~flow bid) is reachable again — it was permanently null, capping K at 6
# ═══════════════════════════════════════════════════════════════════════════════

@needs_node
@pytest.mark.parametrize("path", [TEMPLATE, SITE], ids=["template", "site"])
def test_l5_fires_when_flow_is_bid_and_durable(path):
    out = _run(path, _ticker_payload([100.0] * 11), None)
    assert out["legs"][4] is True                     # L5, index 4
    assert out["K"] >= 1


@needs_node
@pytest.mark.parametrize("path", [TEMPLATE, SITE], ids=["template", "site"])
def test_l5_is_false_not_null_when_durability_is_short(path):
    """A real negative is a ✗, not the `·` that a dead read produced."""
    # +100 ×6 then −100 ×5: window one positive, window two negative → durability 0.5 < 0.60.
    out = _run(path, _ticker_payload([100.0] * 6 + [-100.0] * 5), None)
    assert out["flow"]["flow_dur"] == pytest.approx(0.5)
    assert out["legs"][4] is False


@needs_node
@pytest.mark.parametrize("path", [TEMPLATE, SITE], ids=["template", "site"])
def test_l5_stays_null_when_the_tape_is_absent(path):
    """Fail-soft is preserved: no payload → no leg claim, no throw, callback still runs."""
    out = _run(path, None, None)
    assert out["flow"] == {}
    assert out["asof"] is None
    assert out["legs"][4] is None


@needs_node
@pytest.mark.parametrize("path", [TEMPLATE, SITE], ids=["template", "site"])
def test_short_minute_series_yields_no_durability_claim(path):
    """Under 6 cumulative minutes there is no window to score — null, never a fabricated 0."""
    out = _run(path, _ticker_payload([100.0] * 4), None)
    assert "flow_dur" not in out["flow"] or out["flow"]["flow_dur"] is None
    assert out["legs"][4] is None


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Cross-root isolation — the flat events[] carries every root
# ═══════════════════════════════════════════════════════════════════════════════

@needs_node
@pytest.mark.parametrize("path", [TEMPLATE, SITE], ids=["template", "site"])
def test_badges_do_not_leak_across_roots(path):
    """enrich_current.json is session-wide; only this root's events may count."""
    enrich = _enrich_payload([_mk_event(root="NVDA", id="ev-nvda")])
    out = _run(path, _ticker_payload([100.0] * 11), enrich)
    assert not out["flow"].get("badges")
    assert not out["flow"].get("session_tier")


@needs_node
@pytest.mark.parametrize("path", [TEMPLATE, SITE], ids=["template", "site"])
def test_session_tier_takes_the_highest_of_the_roots_events(path):
    """Mirrors bestTier() on intraday_flow — the day's best tier, not the last one seen."""
    enrich = _enrich_payload([
        _mk_event(id="small", premium=200_000, premium_z=None, swept=False,
                  vol_gt_oi=None, baseline_source="floor"),
        _mk_event(id="big", premium=9_000_000, premium_z=6.0),
    ])
    tiers = {e["session_tier"] for e in enrich["events"] if e["root"] == ROOT_SYM}
    rank = {"below_medium": 0, "medium": 1, "high": 2, "strong": 3, "elite": 4}
    best = max(tiers, key=lambda t: rank.get(t, 0))
    out = _run(path, _ticker_payload([100.0] * 11), enrich)
    assert out["flow"]["session_tier"] == best


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Schema-level proof the retired reads were dead, and paired-copy parity
# ═══════════════════════════════════════════════════════════════════════════════

def test_retired_rollup_keys_are_absent_from_the_published_payloads():
    """Documents WHY the reads changed — and fires if anyone re-adds them believing otherwise."""
    ticker = _ticker_payload([100.0] * 11)
    enrich = _enrich_payload([_mk_event()])
    for dead in ("cum_ncp", "flow_dur", "meta"):
        assert dead not in ticker, f"live_flow.ticker/v1 unexpectedly grew {dead!r}"
    assert "meta" not in enrich, "flow.enrich/v1 unexpectedly grew a meta object"
    assert "tickers" not in enrich, "flow.enrich/v1 unexpectedly grew a tickers rollup"
    # The fields the panel does read must be there.
    assert "asof" in ticker and "asof" in enrich
    assert ticker["minutes"] and "ncp" in ticker["minutes"][0]
    assert isinstance(enrich["events"], list)


def test_template_and_site_copies_agree():
    """site/stock.html is rendered from the template by scripts/build_site.py; this region is
    Jinja-free, so the two must be byte-identical or the live page and the source disagree."""
    assert _panel_js(TEMPLATE) == _panel_js(SITE)
