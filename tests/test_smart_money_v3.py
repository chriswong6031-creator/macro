"""Smart-Money v3 "Signal Desk" — consolidated test suite.

Merged from the four authored parts (tests/parts/*.py — left in place for
provenance): one imports header, every test preserved, fixtures deduplicated.
The ONLY content changes vs the parts:

  * the sys.path bootstrap uses ``parents[1]`` (this file sits in ``tests/``;
    the fund-intelligence part sat one level deeper in ``tests/parts/``);
  * jinja2 is imported guarded (try/except) instead of the part's module-level
    ``pytest.importorskip`` — importorskip here would have skipped the ENGINE
    tests too when jinja2 is absent; the dossier tests carry the skip instead.

--- engine/insider_intel.py (from parts/test_insider_intel.py) ---------------
All tests are network- and disk-free: synthetic DataFrames ride in through the
`_df` override params (the _insider_rows_quiver idiom) or via monkeypatched
lane functions. No parquets are read or written.

Coverage:
  1. Grants/awards (TransactionCode M/A) excluded from the quiver flow, even
     when AcquiredDisposedCode says "A" (code-column precedence).
  2. Re-filed rows (identical on the natural key, differing fileDate) collapse
     to one trade before aggregation (the −$6.2B OLPX fix).
  3. Per-trade usd sanity cap drops the whale row; price<=0 rows drop.
  4. Missing TransactionCode column → AcquiredDisposedCode fallback with the
     "filter": "ad_code_only" honesty flag.
  5. |net_usd| floor (100k) bounds the payload.
  6. Trailing-window gate anchored at the store's max Date.
  7. Panel boards: C-suite = role bucket "top" only, min-usd gate, short role
     labels; sells on the S side.
  8. Cluster buys: distinct officer/director CIK count with threshold.
  9. Panel causality: filing_date > asof rows never enter (PIT law).
 10. Two-clock invariant (SM2-R3): quiver and panel sub-dicts each carry their
     OWN asof; top-net rows never hold a blended numeric; roster_hit plumbing;
     panel score enrichment requested for the quiver top-net names.
 11. Degradation: empty store → None; both lanes down → None.

--- engine/fund_intelligence.py (from parts/test_fund_intelligence.py) --------
Pure-math invariants. Load-bearing contracts under test: the conviction
composite's component math (each component carries value+points, weights
mirror config defaults and sum to 100), tier boundaries (high >= 70,
moderate >= 45, low below), the degenerate one-position book (percentile 1.0,
no division error); add_streak counting (consecutive most-recent new/add
quarters, anything else breaks the streak); theme_read lean clustering (a
multi-name SNDK/TSM/VST-style add cluster must outrank a single-name add,
held_pp counts the whole book, narratives are template strings incl. zh) plus
the Finviz fallback; and sector_rotation's QoQ delta math (union of sectors,
Unclassified kept in deltas but off the boards). All PURE — no disk, no
network, no config.

--- engine/ownership_flow.py (from parts/test_ownership_flow.py) --------------
The module under test is 100% PURE (no disk, no config, no network), so every
fixture is a plain dict — no parquet, no monkeypatching, no vendor data.
Covers the review-gate requirements from the v3 design:
  * grade-weighted breadth math + sign correctness (A=2 / B=1.5 / C=1 / else 0.75),
  * index-ETF exclusion on the cross-stock boards,
  * est_flow_usd honesty (None when deltas are not computable — never fabricated),
  * group_flow net_pp aggregation (+ top_grades restriction),
  * models buyer_base_rate EXCLUDES the latest cohort (F8 — soft-leakage guard),
  * percentile norm() stability at n=3 (ties, singleton, empty).

--- templates/fund_dossier.html.j2 (from parts/test_dossier_template.py) ------
Jinja parse + render smoke tests. The dossier template is rendered once per
tracked fund by build_smart_money.py phase 6.5 (try/except PER FUND —
NEVER-BREAK). These tests pin the two guarantees the build relies on:
  1. the template PARSES (no Jinja syntax error can ever reach the render loop);
  2. it RENDERS without raising for an EMPTY fund (``fi={}, lb_row={}, bf={}``),
     for a fully-absent context (every var Undefined), and for a minimal
     populated fund — i.e. every field access is guarded.

Context contract consumed by the template (all keys optional):

    fi       fund_intel entry:
             {book: [{ticker, issuer, shares, value_usd, pct_book, position_rank,
                      tilt_pp, action, shares_change_pct, add_streak_q,
                      conviction: {score, tier, components: {k: {value, points}}},
                      sector, themes: [{slug, name}] | [str], since_excess}],
              sector_series: [{period_end, filing_date, weights: {sector: pct},
                               top_theme_weights: {category: pct}}],
              sector_rotation: {into: [{sector, delta_pp}], out_of: [...],
                                deltas: {sector: delta_pp}},
              theme_read: {leans: [{theme_key, label, label_zh, category, tickers,
                                    added_pp, held_pp, n_names}], core,
                           narrative_en, narrative_zh},
              book_meta: {n_positions, n_resolved, resolution_pct, book_value_usd,
                          filing_date, period_end}}
    lb_row   tracker leaderboard row: {slug, name, grade, rank, median_buy_excess,
             buy_hit_rate, n_buys, sell_skill, turnover_pct, turnover_tier,
             holding_period_q, concentration_pct, style, status,
             quarter_history: [{period_end, n_buys, median_excess, hit_rate,
                                median_fwd63}],
             reliability: {n_q, pos_share, recent4_median, alltime_median, trend,
                           label_en, label_zh},
             trade_log: [{ticker, issuer, action, period_end, filing_date,
                          pct_portfolio, shares_change_pct, since_excess,
                          since_abs, spy_since, hold_days, fwd_excess}]}
    bf       trk.by_fund entry: {slug, name, period_end, filing_date,
             book_value_usd, rotation: {into, out, top_holdings}}
    generated_utc   build timestamp string
    active_section / active_page   ride through to the site-nav include.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

# Repo root on sys.path so `from engine import ...` resolves no matter where
# pytest is invoked from (this file lives at tests/test_smart_money_v3.py).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine import fund_intelligence as fi  # noqa: E402
from engine import insider_intel as ii  # noqa: E402
from engine.ownership_flow import (_INDEX_ETFS, grade_weight, group_flow,  # noqa: E402
                                   models, norm, rotation_history, stock_flow)

try:
    # jinja2 is only needed by the dossier-template tests below — a missing
    # jinja2 must skip THOSE tests, never this whole module (the engine tests
    # above are jinja-free).
    import jinja2
    from jinja2 import ChoiceLoader, Environment, FileSystemLoader
except ImportError:  # pragma: no cover — CI installs jinja2; local minimal envs may not
    jinja2 = None  # type: ignore[assignment]
    ChoiceLoader = Environment = FileSystemLoader = None  # type: ignore[assignment,misc]


# =========================================================================== #
# SECTION 1 — engine/insider_intel.py                                          #
# =========================================================================== #

# ─── synthetic-frame builders ─────────────────────────────────────────────────

def _trade(ticker: str = "AAPL", date: str = "2026-07-01", name: str = "DOE JANE",
           code: str = "P", ad: str = "A", shares: float = 10_000,
           price: float = 50.0, filedate: str = "2026-07-02") -> dict:
    """One quiver insiders row (collector schema incl. the fileDate that makes
    re-files duplicate)."""
    return {"Ticker": ticker, "Date": date, "Name": name,
            "TransactionCode": code, "AcquiredDisposedCode": ad,
            "Shares": shares, "PricePerShare": price, "fileDate": filedate}


def _panel_row(ticker: str, filing: str, cik: int, code: str = "P",
               officer: bool = True, director: bool = False, tenpct: bool = False,
               title: str = "Chief Executive Officer", shares: float = 10_000,
               price: float = 30.0, usd: float = 300_000.0) -> dict:
    """One SEC Form-4 panel row (insider_power schema)."""
    f = pd.Timestamp(filing)
    return {"ticker": ticker, "filing_date": f, "trans_date": f - pd.Timedelta(days=2),
            "rptownercik": cik, "code": code, "is_officer": officer,
            "is_director": director, "is_tenpct": tenpct, "title": title,
            "shares": shares, "price": price, "usd": usd}


# ─── quiver lane ──────────────────────────────────────────────────────────────

def test_grants_excluded_by_transaction_code():
    """M/A rows are grants/awards, not open-market trades — excluded even when
    AcquiredDisposedCode marks them 'A' (acquired)."""
    df = pd.DataFrame([
        _trade(code="P", ad="A", name="BUYER ONE", shares=10_000, price=50.0),
        _trade(code="M", ad="A", name="GRANTEE",   shares=100_000, price=50.0),
        _trade(code="A", ad="A", name="AWARDEE",   shares=50_000, price=50.0),
        _trade(code="S", ad="D", name="SELLER",    shares=2_000, price=50.0),
    ])
    out = ii.quiver_flow(_df=df)
    assert out is not None
    assert out["filter"] == "open_market_ps"
    m = out["by_ticker"]["AAPL"]
    assert m["buy_usd"] == 500_000.0     # the P row only — no $5m grant leak
    assert m["sell_usd"] == 100_000.0
    assert m["net_usd"] == 400_000.0
    assert m["n_buys"] == 1
    assert m["n_sells"] == 1


def test_dedup_collapses_refiled_rows():
    """Identical trades that differ only on fileDate are re-files of the same
    Form 4 — they must count once."""
    df = pd.DataFrame([
        _trade(name="SMITH JOHN", shares=4_000, price=50.0, filedate="2026-07-02"),
        _trade(name="SMITH JOHN", shares=4_000, price=50.0, filedate="2026-07-05"),
    ])
    out = ii.quiver_flow(_df=df)
    m = out["by_ticker"]["AAPL"]
    assert m["buy_usd"] == 200_000.0     # NOT 400k
    assert m["n_buys"] == 1
    assert m["n_buyers"] == 1


def test_usd_cap_drops_whale_and_bad_price_rows():
    df = pd.DataFrame([
        _trade(ticker="WHL", name="WHALE", shares=20_000_000, price=30.0),  # $600m
        _trade(ticker="OK1", name="NORMAL", shares=10_000, price=25.0),     # $250k
        _trade(ticker="BAD", name="ZEROPX", shares=5_000, price=0.0),
    ])
    out = ii.quiver_flow(_df=df)  # default cap $500m
    assert "WHL" not in out["by_ticker"]
    assert "BAD" not in out["by_ticker"]
    assert out["by_ticker"]["OK1"]["net_usd"] == 250_000.0


def test_missing_transaction_code_falls_back_with_honesty_flag():
    rows = [
        _trade(ticker="FLB", name="BUYER", ad="A", shares=6_000, price=50.0),
        _trade(ticker="FLB", name="SELLER", ad="D", shares=1_000, price=50.0),
    ]
    df = pd.DataFrame(rows).drop(columns=["TransactionCode"])
    out = ii.quiver_flow(_df=df)
    assert out["filter"] == "ad_code_only"   # honesty flag: grants may leak in
    m = out["by_ticker"]["FLB"]
    assert m["net_usd"] == 250_000.0
    assert m["n_buys"] == 1
    assert m["n_sells"] == 1


def test_min_net_floor_bounds_payload():
    df = pd.DataFrame([
        _trade(ticker="TINY", name="SMALL", shares=1_500, price=20.0),   # $30k net
        _trade(ticker="BIGG", name="LARGE", shares=5_000, price=50.0),   # $250k net
    ])
    out = ii.quiver_flow(_df=df)
    assert "TINY" not in out["by_ticker"]
    assert "BIGG" in out["by_ticker"]


def test_window_anchored_at_store_max_date():
    df = pd.DataFrame([
        _trade(ticker="NEW1", name="RECENT", date="2026-07-01", shares=5_000, price=50.0),
        _trade(ticker="OLDT", name="ANCIENT", date="2026-01-02", shares=5_000, price=50.0),
    ])
    out = ii.quiver_flow(_df=df)  # asof = 2026-07-01; 90d window
    assert out["asof"] == "2026-07-01"
    assert "NEW1" in out["by_ticker"]
    assert "OLDT" not in out["by_ticker"]


def test_quiver_flow_degrades_to_none_on_empty():
    assert ii.quiver_flow(_df=pd.DataFrame()) is None


# ─── panel lane ───────────────────────────────────────────────────────────────

def test_csuite_boards_top_bucket_and_min_usd():
    panel = pd.DataFrame([
        _panel_row("ACME", "2026-03-20", 101, title="Chief Executive Officer",
                   usd=300_000.0),
        _panel_row("ACME", "2026-03-21", 102, title="Chief Accounting Officer",
                   usd=400_000.0),                                # officer, not top
        _panel_row("LOWB", "2026-03-22", 103, title="Chief Executive Officer",
                   usd=100_000.0),                                # below $250k gate
        _panel_row("BETA", "2026-03-23", 104, code="S",
                   title="Chief Financial Officer", usd=500_000.0),
    ])
    out = ii.panel_boards(_df=panel)
    assert out is not None
    assert out["asof"] == "2026-03-23"
    buy_tickers = [r["ticker"] for r in out["csuite_buys"]]
    assert buy_tickers == ["ACME"]       # top bucket only, sized only
    assert out["csuite_buys"][0]["role_label"] == "CEO"
    assert out["csuite_buys"][0]["usd"] == 300_000.0
    sell = out["csuite_sells"]
    assert [r["ticker"] for r in sell] == ["BETA"]
    assert sell[0]["role_label"] == "CFO"


def test_cluster_buys_distinct_officer_ciks():
    panel = pd.DataFrame([
        # CLUS: 3 distinct officer/director CIKs (201 buys twice — counts once)
        _panel_row("CLUS", "2026-03-10", 201, title="Controller", usd=50_000.0),
        _panel_row("CLUS", "2026-03-11", 201, title="Controller", usd=50_000.0),
        _panel_row("CLUS", "2026-03-12", 202, title="General Counsel", usd=50_000.0),
        _panel_row("CLUS", "2026-03-13", 203, officer=False, director=True,
                   title="Director", usd=50_000.0),
        # TWOB: only 2 distinct buyers — below threshold
        _panel_row("TWOB", "2026-03-14", 301, title="Controller", usd=50_000.0),
        _panel_row("TWOB", "2026-03-15", 302, title="General Counsel", usd=50_000.0),
    ])
    out = ii.panel_boards(_df=panel)
    clusters = {r["ticker"]: r for r in out["cluster_buys"]}
    assert "CLUS" in clusters
    assert "TWOB" not in clusters
    assert clusters["CLUS"]["n_officer_buyers"] == 3
    assert clusters["CLUS"]["buy_usd"] == 200_000.0
    assert clusters["CLUS"]["last_date"] == "2026-03-13"


def test_panel_causal_filing_date_gate():
    """PIT law: a filing dated after asof must not enter any board."""
    panel = pd.DataFrame([
        _panel_row("ACME", "2026-03-20", 101, usd=300_000.0),
        _panel_row("LEAK", "2026-04-15", 102, usd=10_000_000.0),  # after asof
    ])
    out = ii.panel_boards(asof="2026-03-31", _df=panel)
    tickers = [r["ticker"] for r in out["csuite_buys"]]
    assert tickers == ["ACME"]
    assert "LEAK" not in out["scores"]
    assert out["asof"] == "2026-03-31"


def test_panel_scores_carry_no_asof_key():
    """The panel clock lives at the payload level, not inside each score —
    one clock per lane, stamped once."""
    panel = pd.DataFrame([_panel_row("ACME", "2026-03-20", 101, usd=300_000.0)])
    out = ii.panel_boards(_df=panel)
    assert "ACME" in out["scores"]
    assert set(out["scores"]["ACME"]) == {"score", "signal", "confidence"}


# ─── orchestrator — two clocks, no fusion ─────────────────────────────────────

_FAKE_QUIVER = {
    "asof": "2026-07-10", "window_days": 90, "filter": "open_market_ps",
    "by_ticker": {
        "AAA": {"net_usd": 900_000.0, "buy_usd": 900_000.0, "sell_usd": 0.0,
                "n_buys": 3, "n_sells": 0, "n_buyers": 2, "last_date": "2026-07-09"},
        "CCC": {"net_usd": 500_000.0, "buy_usd": 600_000.0, "sell_usd": 100_000.0,
                "n_buys": 2, "n_sells": 1, "n_buyers": 1, "last_date": "2026-07-08"},
        "BBB": {"net_usd": -400_000.0, "buy_usd": 0.0, "sell_usd": 400_000.0,
                "n_buys": 0, "n_sells": 2, "n_buyers": 0, "last_date": "2026-07-07"},
    },
}

_FAKE_PANEL = {
    "asof": "2026-03-31", "window_days": 180,
    "csuite_buys": [], "csuite_sells": [], "cluster_buys": [],
    "scores": {"AAA": {"score": 71.0, "signal": "BUY", "confidence": "High"}},
}


def test_two_clock_invariant(monkeypatch):
    seen_panel_kwargs: dict = {}

    def fake_quiver(**kw):
        return dict(_FAKE_QUIVER)

    def fake_panel(**kw):
        seen_panel_kwargs.update(kw)
        return dict(_FAKE_PANEL)

    monkeypatch.setattr(ii, "quiver_flow", fake_quiver)
    monkeypatch.setattr(ii, "panel_boards", fake_panel)

    out = ii.build_insider_intel({}, roster={"AAA"})
    assert out is not None

    # Each lane keeps its OWN clock at the payload level.
    assert out["quiver"]["asof"] == "2026-07-10"
    assert out["panel"]["asof"] == "2026-03-31"

    buys, sells = out["top_net_buys"], out["top_net_sells"]
    assert [r["ticker"] for r in buys] == ["AAA", "CCC"]   # net_usd desc
    assert [r["ticker"] for r in sells] == ["BBB"]         # most negative first

    for row in buys + sells:
        # Strict row shape: nothing lives outside the two lane sub-dicts.
        assert set(row) == {"ticker", "quiver", "panel", "roster_hit"}
        # Two clocks, one per lane — never shared, never merged.
        assert row["quiver"]["asof"] == "2026-07-10"
        if row["panel"] is not None:
            assert row["panel"]["asof"] == "2026-03-31"
            assert set(row["panel"]) == {"score", "signal", "confidence", "asof"}
        # No blended top-level numeric: dollars stay in quiver, scores in panel.
        for k, v in row.items():
            if k not in ("quiver", "panel"):
                assert isinstance(v, (str, bool)), (
                    f"top-level numeric {k}={v!r} would blend lanes (SM2-R3)")

    aaa = buys[0]
    assert aaa["roster_hit"] is True
    assert aaa["panel"]["score"] == 71.0
    ccc = buys[1]
    assert ccc["panel"] is None            # no panel read for CCC — shown as absent
    assert ccc["roster_hit"] is False
    assert sells[0]["panel"] is None

    # Enrichment plumbing: the panel lane was asked to score the quiver
    # top-net names (side-by-side display), ranked buys first.
    assert seen_panel_kwargs.get("extra_tickers") == ["AAA", "CCC", "BBB"]


def test_build_returns_none_when_both_lanes_down(monkeypatch):
    monkeypatch.setattr(ii, "quiver_flow", lambda **kw: None)
    monkeypatch.setattr(ii, "panel_boards", lambda **kw: None)
    assert ii.build_insider_intel({}) is None


def test_build_survives_quiver_only(monkeypatch):
    monkeypatch.setattr(ii, "quiver_flow", lambda **kw: dict(_FAKE_QUIVER))
    monkeypatch.setattr(ii, "panel_boards", lambda **kw: None)
    out = ii.build_insider_intel({"insider_intel": {"top_net_n": 1}})
    assert out["panel"] is None
    assert [r["ticker"] for r in out["top_net_buys"]] == ["AAA"]  # top_net_n knob
    assert [r["ticker"] for r in out["top_net_sells"]] == ["BBB"]
    assert all(r["panel"] is None for r in out["top_net_buys"])


# =========================================================================== #
# SECTION 2 — engine/fund_intelligence.py                                      #
# =========================================================================== #

# --------------------------------------------------------------------------- #
# helpers                                                                       #
# --------------------------------------------------------------------------- #

def _pos(ticker="AAA", pct=5.0, rank=1, tilt=1.0, action="add", persistence="persisted"):
    return {"ticker": ticker, "pct_book": pct, "position_rank": rank,
            "tilt_pp": tilt, "action": action, "persistence": persistence}


def _cls():
    ai = {"slug": "ai_infra", "name": "AI Infrastructure",
          "name_zh": "AI 基础设施", "category": "AI & Technology"}
    gas = {"slug": "natgas", "name": "Natural Gas",
           "name_zh": "天然气", "category": "Energy"}
    return {
        "SNDK": {"sector": "Technology", "sub_industry": None, "themes": [dict(ai)], "finviz": []},
        "TSM":  {"sector": "Technology", "sub_industry": None, "themes": [dict(ai)], "finviz": []},
        "VST":  {"sector": "Utilities", "sub_industry": None, "themes": [dict(ai)], "finviz": []},
        "MSFT": {"sector": "Technology", "sub_industry": None, "themes": [dict(ai)], "finviz": []},
        "EQT":  {"sector": "Energy", "sub_industry": None, "themes": [dict(gas)], "finviz": []},
        "ZZZ":  {"sector": None, "sub_industry": None, "themes": [],
                 "finviz": [{"subsector_key": "aicompute", "subsector_name": "Compute",
                             "theme": "Artificial Intelligence"}]},
    }


# --------------------------------------------------------------------------- #
# conviction — component math                                                   #
# --------------------------------------------------------------------------- #

def test_default_weights_sum_to_100():
    assert sum(fi._DEFAULT_WEIGHTS.values()) == 100.0


def test_conviction_component_math():
    book = [_pos("AAA", 8.0), _pos("BBB", 4.0), _pos("CCC", 2.0), _pos("DDD", 1.0)]
    pos = book[0]  # pct 8 (top), rank 1, tilt +1, action add, persisted
    res = fi.conviction_score(pos, book, ["new", "add", "add"])
    comps = res["components"]
    assert comps["pct_book"]["value"] == 1.0          # 4/4 of the book <= 8.0
    assert comps["pct_book"]["points"] == 35.0
    assert comps["rank_top10"]["value"] == 1
    assert comps["rank_top10"]["points"] == 15.0
    assert comps["tilt"]["points"] == 10.0
    assert comps["add_streak"]["value"] == 3
    assert comps["add_streak"]["points"] == 15.0      # 20 * min(3,4)/4
    assert comps["new_at_size"]["value"] is False     # action is add, not new
    assert comps["new_at_size"]["points"] == 0.0
    assert comps["persisted"]["points"] == 10.0
    assert res["score"] == 85.0
    assert res["tier"] == "high"
    # every component carries both value and points (transparent composite)
    for c in comps.values():
        assert "value" in c and "points" in c


def test_conviction_tier_boundaries():
    book = [_pos("AAA", 8.0), _pos("BBB", 4.0)]
    # exactly 70 = 35 (pctile 1.0) + 15 (rank) + 10 (tilt) + 10 (streak 2) -> high
    hi = fi.conviction_score(
        _pos("AAA", 8.0, rank=1, tilt=1.0, action="hold", persistence="pending"),
        book, ["add", "add"])
    assert hi["score"] == 70.0 and hi["tier"] == "high"
    # exactly 45 = 35 (pctile) + 10 (streak 2); rank 11 and tilt<0 earn nothing
    mod = fi.conviction_score(
        _pos("AAA", 8.0, rank=11, tilt=-1.0, action="hold", persistence="pending"),
        book, ["add", "add"])
    assert mod["score"] == 45.0 and mod["tier"] == "moderate"
    # 35 < 45 -> low
    lo = fi.conviction_score(
        _pos("AAA", 8.0, rank=11, tilt=-1.0, action="hold", persistence="pending"),
        book, ["hold"])
    assert lo["score"] == 35.0 and lo["tier"] == "low"


def test_conviction_one_position_degenerate_book():
    pos = _pos("ONLY", 100.0, rank=1, tilt=0.0, action="new", persistence="pending")
    res = fi.conviction_score(pos, [pos], ["new"])
    # 35 (pctile 1.0) + 15 (rank) + 0 (tilt==0 is not >0) + 5 (streak 1) + 10 (new @ size)
    assert res["components"]["pct_book"]["value"] == 1.0
    assert res["components"]["new_at_size"]["value"] is True
    assert res["components"]["new_at_size"]["points"] == 10.0
    assert res["components"]["tilt"]["points"] == 0.0
    assert res["score"] == 65.0
    assert res["tier"] == "moderate"


def test_conviction_null_safe_and_custom_weights():
    # a bare pos with an empty book earns zero everywhere, never raises
    res = fi.conviction_score({"ticker": "X"}, [], None)
    assert res["score"] == 0.0 and res["tier"] == "low"
    # custom weights flow through; unknown keys are ignored
    book = [_pos("AAA", 8.0)]
    res2 = fi.conviction_score(_pos("AAA", 8.0, action="hold", persistence="pending"),
                               book, [], weights={"w_pct_book": 0.0, "bogus": 99})
    assert res2["components"]["pct_book"]["points"] == 0.0


# --------------------------------------------------------------------------- #
# add_streak                                                                    #
# --------------------------------------------------------------------------- #

def test_add_streak_correctness():
    assert fi.add_streak(None) == 0
    assert fi.add_streak([]) == 0
    assert fi.add_streak(["new"]) == 1
    assert fi.add_streak(["new", "add", "add"]) == 3
    assert fi.add_streak(["add", "hold", "add"]) == 1        # hold breaks the run
    assert fi.add_streak(["new", "add", "trim"]) == 0        # latest quarter not a buy
    assert fi.add_streak([None, "new", "add"]) == 2          # absence breaks, then counts
    assert fi.add_streak(["exit", "new", "add", "add", "add", "add"]) == 5  # no cap here


# --------------------------------------------------------------------------- #
# theme_read — lean clustering                                                  #
# --------------------------------------------------------------------------- #

def test_theme_read_ranks_the_cluster():
    cls = _cls()
    book = [
        {"ticker": "MSFT", "pct_book": 5.0, "action": "hold"},
        {"ticker": "SNDK", "pct_book": 4.0, "action": "new"},
        {"ticker": "TSM", "pct_book": 3.3, "action": "add"},
        {"ticker": "VST", "pct_book": 2.0, "action": "add"},
        {"ticker": "EQT", "pct_book": 1.0, "action": "add"},
    ]
    buys = [p for p in book if p["action"] in ("new", "add")]
    out = fi.theme_read(book, buys, cls)
    core = out["core"]
    assert core is not None
    assert core["theme_key"] == "ai_infra"
    assert core["added_pp"] == 9.3                    # 4.0 + 3.3 + 2.0
    assert core["held_pp"] == 14.3                    # + MSFT's held 5.0
    assert core["tickers"] == ["SNDK", "TSM", "VST"]  # buys only, size-ordered
    assert core["n_names"] == 4                       # holdings incl. MSFT
    keys = [ln["theme_key"] for ln in out["leans"]]
    assert keys.index("ai_infra") < keys.index("natgas")  # 3-name cluster outranks 1-name
    assert "AI Infrastructure" in out["narrative_en"]
    assert "SNDK, TSM, VST" in out["narrative_en"]
    assert "+9.3pp" in out["narrative_en"]
    assert "AI 基础设施" in out["narrative_zh"]


def test_theme_read_finviz_fallback():
    cls = _cls()
    book = [{"ticker": "ZZZ", "pct_book": 3.0, "action": "new"}]
    out = fi.theme_read(book, book, cls)
    assert out["core"] is not None
    assert out["core"]["theme_key"] == "fv:aicompute"  # prefixed — no basket collision
    assert out["core"]["label"] == "Compute"
    assert out["core"]["source"] == "finviz"


def test_theme_read_no_buys_degrades():
    out = fi.theme_read([], [], {})
    assert out["core"] is None
    assert out["leans"] == []
    assert out["narrative_en"] and out["narrative_zh"]


# --------------------------------------------------------------------------- #
# sector_rotation — QoQ delta math                                              #
# --------------------------------------------------------------------------- #

def test_sector_rotation_delta_math():
    series = [
        {"period_end": "2026-03-31",
         "weights": {"Technology": 30.0, "Energy": 10.0, "Healthcare": 5.0}},
        {"period_end": "2026-06-30",
         "weights": {"Technology": 40.0, "Energy": 5.0, "Healthcare": 5.0,
                     "Unclassified": 3.0}},
    ]
    rot = fi.sector_rotation(series)
    assert rot["deltas"]["Technology"] == 10.0
    assert rot["deltas"]["Energy"] == -5.0
    assert rot["deltas"]["Healthcare"] == 0.0
    assert rot["deltas"]["Unclassified"] == 3.0        # kept in deltas (honesty)
    assert rot["into"][0] == {"sector": "Technology", "delta_pp": 10.0}
    assert all(r["sector"] != "Unclassified" for r in rot["into"])  # off the boards
    assert rot["out_of"][0] == {"sector": "Energy", "delta_pp": -5.0}
    assert rot["period_end"] == "2026-06-30"
    assert rot["prev_period_end"] == "2026-03-31"
    assert rot["method_note"]["en"] and rot["method_note"]["zh"]  # F12 caveat travels


def test_sector_rotation_sector_dropped_to_zero():
    series = [
        {"period_end": "q1", "weights": {"Energy": 8.0, "Technology": 20.0}},
        {"period_end": "q2", "weights": {"Technology": 28.0}},
    ]
    rot = fi.sector_rotation(series)
    assert rot["deltas"]["Energy"] == -8.0             # union of sectors, absent -> 0
    assert rot["out_of"][0] == {"sector": "Energy", "delta_pp": -8.0}


def test_sector_rotation_short_series():
    empty = fi.sector_rotation([])
    assert empty["into"] == [] and empty["out_of"] == [] and empty["deltas"] == {}
    one = fi.sector_rotation([{"period_end": "2026-06-30", "weights": {"Technology": 10.0}}])
    assert one["into"] == [] and one["deltas"] == {}
    assert one["period_end"] == "2026-06-30"


# =========================================================================== #
# SECTION 3 — engine/ownership_flow.py                                          #
# =========================================================================== #

# --------------------------------------------------------------------------- #
# Fixtures (plain dicts — the module is pure)                                   #
# --------------------------------------------------------------------------- #

def _holder(fund: str, name: str, action: str, pct: float, value: float,
            chg: float | None, issuer: str) -> dict:
    return {
        "fund": fund, "fund_name": name, "action": action,
        "pct_portfolio": pct, "value_usd": value, "shares_change_pct": chg,
        "issuer": issuer, "period_end": "2026-03-31", "filing_date": "2026-05-14",
        "position_rank": 5, "tilt_pp": 0.5, "shares": 1000.0,
    }


def _sm() -> dict:
    return {
        "as_of": "2026-03-31",
        "by_ticker": {
            # net buy: A-grade new (w 2.0) vs C-grade trim (w 1.0) -> gw +1.0
            "AAA": {
                "holders": [
                    _holder("ALPHA", "Alpha Fund", "new", 4.0, 40_000_000.0, None, "AAA CORP"),
                    _holder("GAMMA", "Gamma Fund", "trim", 2.0, 10_000_000.0, -50.0, "AAA CORP"),
                ],
                "n_holders": 2, "n_buying": 1, "n_selling": 1, "vip": 2,
                "as_of": "2026-03-31",
                "trend": {"holders_series": [1, 2]},
            },
            # net sell: C-grade trim (w 1.0) + UNGRADED exit (w 0.75) -> gw -1.75
            "BBB": {
                "holders": [
                    _holder("GAMMA", "Gamma Fund", "trim", 1.5, 8_000_000.0, -25.0, "BBB INC"),
                    _holder("DELTA", "Delta Fund", "exit", 0.0, 5_000_000.0, -100.0, "BBB INC"),
                ],
                "n_holders": 2, "n_buying": 0, "n_selling": 2, "vip": 1,
                "as_of": "2026-03-31",
            },
            # flow honesty: an 'add' with NO shares_change_pct -> est_flow_usd None
            "CCC": {
                "holders": [
                    _holder("BETA", "Beta Fund", "add", 3.0, 12_000_000.0, None, "CCC LTD"),
                ],
                "n_holders": 1, "n_buying": 1, "n_selling": 0, "vip": 1,
                "as_of": "2026-03-31",
            },
            # index ETF with a buyer — must be excluded from every cross-stock board
            "SPY": {
                "holders": [
                    _holder("ALPHA", "Alpha Fund", "new", 6.0, 60_000_000.0, None, "SPDR S&P 500"),
                ],
                "n_holders": 1, "n_buying": 1, "n_selling": 0, "vip": 1,
                "as_of": "2026-03-31",
            },
        },
    }


def _tracker() -> dict:
    return {
        "latest_filing": "2026-05-15",
        "leaderboard": [
            {"slug": "alpha", "grade": "A"},
            {"slug": "beta", "grade": "B"},
            {"slug": "gamma", "grade": "C"},
            # 'delta' intentionally absent -> ungraded default weight 0.75
        ],
        "by_fund": {
            "alpha": {
                "name": "Alpha Fund", "filing_date": "2026-05-14",
                "scorecard": {
                    "quarter_history": [
                        {"period_end": "2025-09-30", "n_buys": 4,
                         "median_excess": 0.08, "hit_rate": 0.75, "median_fwd63": 0.05},
                        {"period_end": "2025-12-31", "n_buys": 6,
                         "median_excess": 0.12, "hit_rate": 0.50, "median_fwd63": 0.02},
                        # LATEST cohort — unresolved; must be EXCLUDED from the base rate
                        {"period_end": "2026-03-31", "n_buys": 9,
                         "median_excess": -0.90, "hit_rate": 0.00, "median_fwd63": None},
                    ],
                },
            },
        },
    }


def _fund_intel() -> dict:
    return {
        "funds": {
            "alpha": {
                "book_meta": {"filing_date": "2026-05-14", "period_end": "2026-03-31"},
                "sector_rotation": {"deltas": {"Information Technology": 3.0,
                                               "Energy": -1.0}},
                "sector_series": [],
                "theme_read": {},
                "book": [
                    {"ticker": "AAA", "issuer": "AAA CORP", "action": "new",
                     "pct_book": 4.0, "sector": "Information Technology", "themes": [],
                     "conviction": {"score": 82.0, "tier": "high"}},
                ],
            },
            "gamma": {
                "book_meta": {"filing_date": "2026-05-15", "period_end": "2026-03-31"},
                "sector_rotation": {"deltas": {"Information Technology": 1.5,
                                               "Energy": -0.5}},
                "sector_series": [],
                "theme_read": {},
                "book": [
                    {"ticker": "EEE", "issuer": "EEE CO", "action": "trim",
                     "pct_book": 2.0, "sector": "Energy", "themes": [],
                     "conviction": {"score": 30.0, "tier": "low"}},
                ],
            },
        },
    }


# --------------------------------------------------------------------------- #
# stock_flow — breadth math, sign correctness, ETF exclusion, flow honesty      #
# --------------------------------------------------------------------------- #

def test_stock_flow_breadth_math_and_signs():
    flow = stock_flow(_sm(), _tracker())
    assert flow is not None
    ins = {r["ticker"]: r for r in flow["in"]}
    outs = {r["ticker"]: r for r in flow["out"]}

    # AAA: A-grade buyer (2.0) minus C-grade seller (1.0) = +1.0 -> 'in'
    assert "AAA" in ins
    assert ins["AAA"]["gw_breadth"] == 1.0
    assert ins["AAA"]["n_buying"] == 1 and ins["AAA"]["n_selling"] == 1

    # BBB: C-grade trim (1.0) + ungraded exit (0.75) = -1.75 -> 'out'
    assert "BBB" in outs
    assert outs["BBB"]["gw_breadth"] == -1.75

    # sign partition holds for every row on each board
    assert all(r["gw_breadth"] > 0 for r in flow["in"])
    assert all(r["gw_breadth"] < 0 for r in flow["out"])

    # grade weights: the 'else 0.75' bucket covers D / n/a / unknown funds
    assert grade_weight("A") == 2.0
    assert grade_weight("B") == 1.5
    assert grade_weight("C") == 1.0
    assert grade_weight("D") == 0.75
    assert grade_weight(None) == 0.75

    # fund cards carry the grade + action for transparent display
    buyer = ins["AAA"]["buy_funds"][0]
    assert buyer["slug"] == "alpha" and buyer["grade"] == "A" and buyer["action"] == "new"

    # d_funds_qoq from the accumulation trend (2 - 1 = +1); None without history
    assert ins["AAA"]["d_funds_qoq"] == 1
    assert outs["BBB"]["d_funds_qoq"] is None


def test_stock_flow_est_flow_usd_computable_and_honest_none():
    flow = stock_flow(_sm(), _tracker())
    ins = {r["ticker"]: r for r in flow["in"]}
    outs = {r["ticker"]: r for r in flow["out"]}

    # AAA: new +40M; trim of -50% on a 10M residual = -10M -> net +30M
    assert ins["AAA"]["est_flow_usd"] == 30_000_000.0

    # BBB: exit -5M (prior value) + trim -25% on 8M residual (-8M/3) -> negative
    assert outs["BBB"]["est_flow_usd"] is not None
    assert outs["BBB"]["est_flow_usd"] < 0

    # CCC: 'add' with no shares_change_pct -> NOT computable -> None, never invented
    assert "CCC" in ins
    assert ins["CCC"]["est_flow_usd"] is None
    assert ins["CCC"]["gw_breadth"] == 1.5  # B-grade buyer still counts for breadth


def test_stock_flow_excludes_index_etfs():
    flow = stock_flow(_sm(), _tracker())
    tickers = {r["ticker"] for r in flow["in"]} | {r["ticker"] for r in flow["out"]}
    assert "SPY" not in tickers
    assert "SPY" in _INDEX_ETFS  # the mirror constant actually covers the fixture


# --------------------------------------------------------------------------- #
# group_flow — net_pp aggregation + top-grades restriction                      #
# --------------------------------------------------------------------------- #

def test_group_flow_net_pp_aggregation():
    gf = group_flow(_fund_intel(), _tracker(), level="sector")
    assert gf is not None
    groups = {g["key"]: g for g in gf["groups"]}

    it = groups["Information Technology"]
    assert it["net_pp"] == 4.5            # 3.0 (alpha) + 1.5 (gamma)
    assert it["avg_pp"] == 2.25
    assert it["intensity"] == 4.5
    assert it["n_funds_in"] == 2 and it["n_funds_out"] == 0

    en = groups["Energy"]
    assert en["net_pp"] == -1.5           # -1.0 + -0.5
    assert en["n_funds_out"] == 2

    # ranked net_pp descending: IT before Energy
    keys = [g["key"] for g in gf["groups"]]
    assert keys.index("Information Technology") < keys.index("Energy")

    # this-cycle names land on the right side of the right group
    assert {n["ticker"] for n in it["top_names_in"]} == {"AAA"}
    assert {n["ticker"] for n in en["top_names_out"]} == {"EEE"}

    # asof = max contributing filing date (filing clock, never period_end)
    assert gf["asof"] == "2026-05-15"


def test_group_flow_top_grades_restricts_funds():
    gf = group_flow(_fund_intel(), _tracker(), level="sector", top_grades=["A"])
    assert gf is not None
    assert gf["n_funds"] == 1             # gamma (C) filtered out
    groups = {g["key"]: g for g in gf["groups"]}
    assert groups["Information Technology"]["net_pp"] == 3.0
    assert groups["Energy"]["net_pp"] == -1.0


def test_rotation_history_equal_weight_labeled():
    fi = _fund_intel()
    fi["funds"]["alpha"]["sector_series"] = [
        {"period_end": "2025-12-31", "filing_date": "2026-02-14",
         "weights": {"Information Technology": 60.0, "Energy": 40.0}},
        {"period_end": "2026-03-31", "filing_date": "2026-05-14",
         "weights": {"Information Technology": 70.0, "Energy": 30.0}},
    ]
    fi["funds"]["gamma"]["sector_series"] = [
        {"period_end": "2026-03-31", "filing_date": "2026-05-15",
         "weights": {"Information Technology": 50.0, "Energy": 50.0}},
    ]
    hist = rotation_history(fi)
    assert [h["period_end"] for h in hist] == ["2025-12-31", "2026-03-31"]
    latest = hist[-1]
    assert latest["n_funds"] == 2
    assert latest["weighting"] == "equal"     # no per-quarter book values -> stated
    assert latest["weights"]["Information Technology"] == 60.0  # (70+50)/2
    assert latest["weights"]["Energy"] == 40.0                  # (30+50)/2


# --------------------------------------------------------------------------- #
# models — buyer base rate excludes the LATEST cohort (F8)                      #
# --------------------------------------------------------------------------- #

def _models(crowding: list[dict] | None = None) -> dict:
    sm, tracker, fi = _sm(), _tracker(), _fund_intel()
    flow = stock_flow(sm, tracker)
    return models(sm, tracker, flow, crowding or [], fi, cls={})


def test_models_base_rate_excludes_latest_cohort():
    m = _models()
    assert m is not None
    rows = {r["ticker"]: r for r in m["conviction_buys"]["rows"]}
    assert "AAA" in rows                   # alpha (grade A) new @ conviction 'high'
    br = rows["AAA"]["buyer_base_rate"]

    # priors only: n = 4+6 = 10 (latest 9 excluded); hit = (0.75*4 + 0.5*6)/10;
    # median_excess = median(0.08, 0.12) — the latest -0.90 must NOT contaminate it
    assert br["n"] == 10
    assert br["hit_rate"] == 0.6
    assert br["median_excess"] == 0.1

    # ranking: conviction 82 x grade-A weight 2.0
    assert rows["AAA"]["rank_score"] == 164.0
    # L5 anchor rides on the row (max buyer filing date)
    assert rows["AAA"]["filing_date"] == "2026-05-14"


def test_models_board_contract_and_uncrowded_filter():
    m = _models()
    for key in ("most_favored", "conviction_buys", "asymmetric", "rotating_out"):
        board = m[key]
        for field in ("rows", "method_en", "method_zh", "asof", "title_en", "title_zh"):
            assert field in board, f"{key} missing {field}"
    # F9 honesty rename: key stays 'asymmetric', the TITLE is Uncrowded conviction
    assert m["asymmetric"]["title_en"] == "Uncrowded conviction"

    # AAA: 2 tracked holders (<=3), off the crowding radar -> on the uncrowded board
    unc = {r["ticker"] for r in m["asymmetric"]["rows"]}
    assert "AAA" in unc

    # confirmed-elevated crowding excludes it
    m2 = _models(crowding=[{"ticker": "AAA", "crowding_tier": "elevated"}])
    assert "AAA" not in {r["ticker"] for r in m2["asymmetric"]["rows"]}

    # rotating_out requires >=2 sellers: BBB qualifies, AAA (1 seller) does not
    rot = {r["ticker"] for r in m["rotating_out"]["rows"]}
    assert "BBB" in rot and "AAA" not in rot


# --------------------------------------------------------------------------- #
# norm() — percentile rank, stable at n=3 (never a z-score)                     #
# --------------------------------------------------------------------------- #

def test_norm_percentile_stability_n3():
    vals = [1.0, 2.0, 3.0]
    assert norm(1.0, vals) == 0.0
    assert norm(2.0, vals) == 0.5
    assert norm(3.0, vals) == 1.0

    # ties share the mean rank; bounded 0..1 even at n=3
    tied = [5.0, 5.0, 9.0]
    assert norm(5.0, tied) == 0.25
    assert norm(9.0, tied) == 1.0

    # degenerate sets stay honest: singleton = median, empty/None = None
    assert norm(7.0, [7.0]) == 0.5
    assert norm(1.0, []) is None
    assert norm(None, vals) is None


# =========================================================================== #
# SECTION 4 — templates/fund_dossier.html.j2                                    #
# =========================================================================== #

_HERE = Path(__file__).resolve()
_DOSSIER = "fund_dossier.html.j2"
_BASE_FILES = ("report_base.html.j2", "_site_nav.html.j2")


def _find_templates_dir(*needed: str) -> Path | None:
    """Walk up from this test file and return the first ``templates/`` dir that
    contains every file in `needed` (works from the repo root AND from the
    handoff staging tree)."""
    for up in _HERE.parents:
        cand = up / "templates"
        if all((cand / n).exists() for n in needed):
            return cand
    return None


_DOSSIER_DIR = _find_templates_dir(_DOSSIER)
_BASE_DIR = _find_templates_dir(*_BASE_FILES)


def _env() -> "jinja2.Environment":
    """Mirror the build environment (build_smart_money.py phase 6):
    FileSystemLoader over templates/, autoescape ON."""
    loaders = [FileSystemLoader(str(_DOSSIER_DIR))]
    if _BASE_DIR is not None and _BASE_DIR != _DOSSIER_DIR:
        loaders.append(FileSystemLoader(str(_BASE_DIR)))
    return Environment(loader=ChoiceLoader(loaders), autoescape=True)


# ---------------------------------------------------------------------------
# synthetic contexts
# ---------------------------------------------------------------------------

EMPTY_CTX = {
    "fi": {},
    "lb_row": {},
    "bf": {},
    "generated_utc": "2026-07-12 04:00 UTC",
    "active_section": "us",
    "active_page": "fund_dossier",
}

_LEAN = {
    "theme_key": "ai-infrastructure",
    "label": "AI Infrastructure",
    "label_zh": "AI基础设施",
    "category": "Tech",
    "tickers": ["SNDK", "TSM", "VST"],
    "added_pp": 9.3,
    "held_pp": 21.0,
    "n_names": 3,
}

MINIMAL_CTX = {
    "fi": {
        "book": [
            {
                "ticker": "SNDK",
                "issuer": "SANDISK CORP",
                "shares": 1_000_000,
                "value_usd": 250_000_000.0,
                "pct_book": 6.2,
                "position_rank": 1,
                "tilt_pp": 1.4,
                "action": "add",
                "shares_change_pct": 25.0,
                "add_streak_q": 3,
                "conviction": {
                    "score": 78.0,
                    "tier": "high",
                    "components": {
                        "pct_book": {"value": 0.97, "points": 34},
                        "rank_top10": {"value": 1, "points": 15},
                    },
                },
                "sector": "Information Technology",
                "themes": [{"slug": "ai-infrastructure", "name": "AI Infrastructure"}],
                "since_excess": 0.041,
            },
            {
                # a deliberately hole-riddled row — every display path must guard
                "ticker": "XYZ",
                "issuer": None,
                "shares": None,
                "value_usd": None,
                "pct_book": None,
                "position_rank": None,
                "tilt_pp": None,
                "action": "trim",
                "shares_change_pct": -30.0,
                "add_streak_q": 0,
                "conviction": {},
                "sector": None,
                "themes": [],
                "since_excess": None,
            },
        ],
        "sector_series": [
            {
                "period_end": "2025-12-31",
                "filing_date": "2026-02-14",
                "weights": {"Information Technology": 55.0, "Unclassified": 45.0},
                "top_theme_weights": {"AI": 40.0},
            },
            {
                "period_end": "2026-03-31",
                "filing_date": "2026-05-15",
                "weights": {"Information Technology": 60.0, "Unclassified": 40.0},
                "top_theme_weights": {"AI": 44.0},
            },
        ],
        "sector_rotation": {
            "into": [{"sector": "Information Technology", "delta_pp": 5.0}],
            "out_of": [{"sector": "Unclassified", "delta_pp": -5.0}],
            "deltas": {"Information Technology": 5.0, "Unclassified": -5.0},
        },
        "theme_read": {
            "leans": [_LEAN],
            "core": _LEAN,
            "narrative_en": ("Core lean: AI Infrastructure — added SNDK, TSM, VST "
                             "(+9.3pp of book this quarter)."),
            "narrative_zh": "核心倾向：AI基础设施——本季度加仓 SNDK、TSM、VST（占组合+9.3pp）。",
        },
        "book_meta": {
            "n_positions": 2,
            "n_resolved": 2,
            "resolution_pct": 100.0,
            "book_value_usd": 4.03e9,
            "filing_date": "2026-05-15",
            "period_end": "2026-03-31",
        },
    },
    "lb_row": {
        "slug": "testfund",
        "name": "Test Fund LP",
        "grade": "A",
        "rank": 1,
        "median_buy_excess": 0.021,
        "buy_hit_rate": 0.58,
        "n_buys": 24,
        "sell_skill": 0.004,
        "turnover_pct": 12.0,
        "turnover_tier": "low",
        "holding_period_q": 4.0,
        "concentration_pct": 61.0,
        "style": "concentrated growth",
        "status": "active",
        "quarter_history": [
            {"period_end": "2025-12-31", "n_buys": 6, "median_excess": -0.012,
             "hit_rate": 0.33, "median_fwd63": -0.004},
            {"period_end": "2026-03-31", "n_buys": 8, "median_excess": 0.034,
             "hit_rate": 0.62, "median_fwd63": 0.011},
        ],
        "reliability": {
            "n_q": 8, "pos_share": 0.62, "recent4_median": 0.018,
            "alltime_median": 0.009, "trend": "improving",
            "label_en": "improving", "label_zh": "走强",
        },
        "trade_log": [
            {"ticker": "SNDK", "issuer": "SANDISK CORP", "action": "add",
             "period_end": "2026-03-31", "filing_date": "2026-05-15",
             "pct_portfolio": 6.2, "shares_change_pct": 25.0,
             "since_excess": 0.041, "since_abs": 0.062, "spy_since": 0.021,
             "hold_days": 58, "fwd_excess": None},
        ],
    },
    "bf": {
        "slug": "testfund",
        "name": "Test Fund LP",
        "period_end": "2026-03-31",
        "filing_date": "2026-05-15",
        "book_value_usd": 4.03e9,
        "rotation": {
            "into": [{"ticker": "SNDK", "action": "add", "pct_portfolio": 6.2,
                      "since_excess": 0.041}],
            "out": [{"ticker": "OLD", "action": "exit", "shares_change_pct": -100.0,
                     "since_excess": -0.02}],
            "top_holdings": [{"ticker": "SNDK", "pct": 6.2, "action": "add"}],
        },
    },
    "generated_utc": "2026-07-12 04:00 UTC",
    "active_section": "us",
    "active_page": "fund_dossier",
}


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------

@pytest.mark.skipif(jinja2 is None or _DOSSIER_DIR is None,
                    reason="jinja2 unavailable, or templates/fund_dossier.html.j2 "
                           "not found above this test")
def test_dossier_template_parses():
    """Syntax gate: Environment().parse never raises."""
    src = (_DOSSIER_DIR / _DOSSIER).read_text(encoding="utf-8")
    Environment(loader=FileSystemLoader(str(_DOSSIER_DIR)), autoescape=True).parse(src)


@pytest.mark.skipif(jinja2 is None or _DOSSIER_DIR is None or _BASE_DIR is None,
                    reason="jinja2 unavailable, or report_base.html.j2 / "
                           "_site_nav.html.j2 not found — render test needs the "
                           "full templates dir")
def test_dossier_renders_empty_fund():
    """NEVER-BREAK: an empty fund ({} for every entry) renders a graceful page."""
    html = _env().get_template(_DOSSIER).render(**EMPTY_CTX)
    assert len(html) > 1000
    # the honest 'unavailable' degradations are present rather than a blank page
    assert "fund" in html.lower()
    # no raw Python None leaked into the page or its data attributes
    assert ">None<" not in html
    assert '"None"' not in html


@pytest.mark.skipif(jinja2 is None or _DOSSIER_DIR is None or _BASE_DIR is None,
                    reason="jinja2 unavailable, or report_base.html.j2 / "
                           "_site_nav.html.j2 not found — render test needs the "
                           "full templates dir")
def test_dossier_renders_without_any_context():
    """Even harsher than the empty fund: every context var Undefined."""
    html = _env().get_template(_DOSSIER).render()
    assert len(html) > 500


@pytest.mark.skipif(jinja2 is None or _DOSSIER_DIR is None or _BASE_DIR is None,
                    reason="jinja2 unavailable, or report_base.html.j2 / "
                           "_site_nav.html.j2 not found — render test needs the "
                           "full templates dir")
def test_dossier_renders_minimal_fund():
    """A minimal populated fund renders every section, including a row with
    None in every optional numeric field."""
    html = _env().get_template(_DOSSIER).render(**MINIMAL_CTX)
    assert "Test Fund LP" in html
    assert "SNDK" in html                      # book row + lean chip + trade log
    assert "AI Infrastructure" in html         # core-lean label
    assert "XYZ" in html                       # hole-riddled row survived
    assert "2026-03-31" in html                # quarter history row
    assert "fund_index.html" in html           # directory breadcrumb (root-level, F6)
    assert "ticker_icons/SNDK.png" in html     # logo idiom (F10)
    assert ">None<" not in html
    assert 'data-pct="None"' not in html
