"""Options→NW Entry Intelligence W-B wiring tests (RO-5/RO-6/RO-7 + lobe).

Covers: spine adapter (ungraded-honest fold, fail-open), LEDGER_ENUM,
confluence options edges (display_only, sanctioned verbs, no oracle edge),
cortex read tools (whitelist, refusal, read-only), world_state options_weather
lobe (null fallback, <5-root suppression, no composite fields).
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from engine.neuralweb.query import LEDGER_ENUM, adapt_options_entry
from engine.neuralweb.confluence import _build_options_edges
from engine.neuralweb.world_state import (
    _OPTIONS_WEATHER_MIN_ROOTS,
    _compose_options_weather,
)
from engine.neuralweb import cortex


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

def _state_df(tickers: list[str], **overrides) -> pd.DataFrame:
    base = {
        "as_of": "2026-07-05",
        "iv30": 0.25,
        "iv_rank_252": None,
        "iv_rank_5d_chg": None,
        "ivspread_rel": 0.01,
        "ivspread_5d_chg": 0.002,
        "skew": 0.05,
        "skew_5d_chg": -0.01,
        "net_doi": 100.0,
        "doi_pc": 0.8,
        "fresh_contracts": 5,
        "fresh_premium_mn": 1.2,
        "zerodte_share": 0.1,
        "gamma_regime": "long",
        "gamma_regime_structurally_constant": True,
        "dist_to_flip_pct": 3.0,
        "wall_up_dist_pct": 2.5,
        "wall_down_dist_pct": 4.0,
        "max_pain_dist_pct": 1.0,
        "opex_days": 12,
        "pin_risk": False,
        "gex_confirm_verdict": "NEUTRAL",
        "evidence_quality": "full",
        "src_gex_asof": "2026-07-05",
        "src_skew_asof": "2026-07-05",
        "src_ivspread_asof": "2026-07-05",
        "src_flow_asof": "2026-07-05",
    }
    rows = []
    for t in tickers:
        r = dict(base)
        r["ticker"] = t
        r.update(overrides)
        rows.append(r)
    return pd.DataFrame(rows)


def _board_df(buy: list[str], watch: list[str]) -> pd.DataFrame:
    rows = []
    for t in buy:
        rows.append({"as_of": "2026-07-05", "ticker": t, "lane": "buy"})
    for t in watch:
        rows.append({"as_of": "2026-07-05", "ticker": t, "lane": "watch"})
    return pd.DataFrame(rows)


@pytest.fixture()
def tmp_root(tmp_path: Path) -> Path:
    (tmp_path / "data" / "options_entry").mkdir(parents=True)
    (tmp_path / "data" / "us_board_ledger").mkdir(parents=True)
    (tmp_path / "data" / "neuralweb").mkdir(parents=True)
    return tmp_path


# ---------------------------------------------------------------------------
# adapter (RO-5)
# ---------------------------------------------------------------------------

def test_ledger_enum_has_options_entry():
    assert "options_entry" in LEDGER_ENUM


def test_adapter_fail_open_missing_store(tmp_path):
    df, gaps = adapt_options_entry(tmp_path)
    assert df.empty
    assert any("absent" in g for g in gaps)


def test_adapter_folds_ungraded_honest(tmp_root):
    _state_df(["AAPL", "MSFT"]).to_parquet(
        tmp_root / "data" / "options_entry" / "state.parquet", index=False)
    df, gaps = adapt_options_entry(tmp_root)
    assert len(df) == 2
    assert (df["outcome_graded"] == False).all()  # noqa: E712
    assert (df["direction"] == 0).all()
    assert (df["ledger"] == "options_entry").all()
    assert (df["size_binding"] == False).all()  # noqa: E712
    assert set(df["signal_id"]) == {
        "options_entry:2026-07-05:AAPL", "options_entry:2026-07-05:MSFT"}


def test_adapter_corrupt_store_fail_open(tmp_root):
    (tmp_root / "data" / "options_entry" / "state.parquet").write_text("not parquet")
    df, gaps = adapt_options_entry(tmp_root)
    assert df.empty
    assert any("unreadable" in g for g in gaps)


# ---------------------------------------------------------------------------
# confluence edges (RO-6)
# ---------------------------------------------------------------------------

def test_options_edges_display_only_and_sanctioned_verbs(tmp_root):
    _state_df(["AAA", "BBB", "CCC"]).to_parquet(
        tmp_root / "data" / "options_entry" / "state.parquet", index=False)
    _board_df(buy=["AAA"], watch=["BBB"]).to_parquet(
        tmp_root / "data" / "us_board_ledger" / "retro_grades.parquet", index=False)
    gaps: list[str] = []
    edges = _build_options_edges(tmp_root, gaps)
    assert edges, f"no edges built; gaps={gaps}"
    sanctioned = {"feeds", "stable", "leads", "contradicts", "confirms"}
    for e in edges:
        assert e["display_only"] is True
        assert e["edge_type"] in sanctioned
        assert "AMPLIFIES" not in json.dumps(e)
    # No oracle edge (deferred to Oracle-program review, RO-6)
    assert not any("oracle" in str(e.get("src", "")) + str(e.get("dst", ""))
                   for e in edges)


def test_options_edges_counts(tmp_root):
    st = pd.concat([
        _state_df(["RISING"], skew_5d_chg=0.02),
        _state_df(["FALLING"], skew=0.99, skew_5d_chg=-0.02),
        # 30+ rows so the tercile threshold computes
        _state_df([f"F{i}" for i in range(30)], skew=0.01),
    ])
    st.to_parquet(tmp_root / "data" / "options_entry" / "state.parquet", index=False)
    _board_df(buy=["RISING", "FALLING"], watch=[]).to_parquet(
        tmp_root / "data" / "us_board_ledger" / "retro_grades.parquet", index=False)
    gaps: list[str] = []
    edges = _build_options_edges(tmp_root, gaps)
    by_src = {e["src"]: e for e in edges}
    assert by_src["options.skew_rising"]["n"] == 1          # RISING only
    assert by_src["options.skew_decel"]["n"] == 1           # FALLING only
    # extension edge declared honestly with no fabricated count
    assert by_src["options.skew_rising_or_call_wall_pin"]["n"] is None


def test_options_edges_fail_open_missing_stores(tmp_root):
    gaps: list[str] = []
    edges = _build_options_edges(tmp_root, gaps)
    assert edges == []
    assert gaps  # noted, not raised


# ---------------------------------------------------------------------------
# cortex tools (RO-7)
# ---------------------------------------------------------------------------

def test_cortex_whitelist_contains_new_tools():
    for name in ("read_options_entry_state", "explain_options_context",
                 "query_options_confluence", "list_options_contradictions"):
        assert name in cortex._READ_TOOLS
        assert name in cortex._ALLOWED_TOOLS


def test_cortex_dispatch_refuses_unknown(tmp_root):
    out = cortex.dispatch_tool("rank_options_names", {}, tmp_root, "now", {}, {})
    assert "not allowed" in out.get("error", "")


def test_cortex_read_options_entry_state(tmp_root):
    _state_df(["ZZZ", "AAA"]).to_parquet(
        tmp_root / "data" / "options_entry" / "state.parquet", index=False)
    out = cortex.dispatch_tool("read_options_entry_state", {}, tmp_root, "now", {}, {})
    assert [r["ticker"] for r in out["rows"]] == ["AAA", "ZZZ"]  # alphabetical, no rank
    out2 = cortex.dispatch_tool(
        "read_options_entry_state", {"ticker": "zzz"}, tmp_root, "now", {}, {})
    assert len(out2["rows"]) == 1 and out2["rows"][0]["ticker"] == "ZZZ"


def test_cortex_explain_options_context(tmp_root):
    _state_df(["AAPL"], pin_risk=True, opex_days=3).to_parquet(
        tmp_root / "data" / "options_entry" / "state.parquet", index=False)
    out = cortex.dispatch_tool(
        "explain_options_context", {"ticker": "AAPL"}, tmp_root, "now", {}, {})
    text = " ".join(out["plain_english"])
    assert "structurally constant" in text          # audit #29 caveat
    assert "PIN RISK" in text
    assert "display/context only" in out["mandate"]


def test_cortex_list_options_contradictions(tmp_root):
    pd.concat([
        _state_df(["BADLONG"], skew_5d_chg=0.05, ivspread_rel=-0.02),
        _state_df(["GOODLONG"], skew_5d_chg=-0.05, ivspread_rel=0.02),
    ]).to_parquet(tmp_root / "data" / "options_entry" / "state.parquet", index=False)
    _board_df(buy=["BADLONG", "GOODLONG"], watch=[]).to_parquet(
        tmp_root / "data" / "us_board_ledger" / "retro_grades.parquet", index=False)
    out = cortex.dispatch_tool(
        "list_options_contradictions", {}, tmp_root, "now", {}, {})
    names = [c["ticker"] for c in out["contradictions"]]
    assert names == ["BADLONG"]
    assert out["display_only"] is True
    assert "never a short signal" in out["mandate"]


def test_cortex_tools_missing_store_graceful(tmp_root):
    out = cortex.dispatch_tool("read_options_entry_state", {}, tmp_root, "now", {}, {})
    assert out["rows"] == [] and "absent" in out["error"]


# ---------------------------------------------------------------------------
# world_state lobe (RO-1)
# ---------------------------------------------------------------------------

def test_lobe_null_fallback_missing_store(tmp_path):
    out = _compose_options_weather(tmp_path)
    assert out["display_only"] is True
    assert out["median_iv30"] is None and out["n_roots"] is None


def test_lobe_suppression_below_min_roots(tmp_root):
    _state_df(["SPY", "QQQ"]).to_parquet(  # 2 < 5 weather roots
        tmp_root / "data" / "options_entry" / "state.parquet", index=False)
    out = _compose_options_weather(tmp_root)
    assert out["n_roots"] == 2
    assert out["median_iv30"] is None       # suppressed
    assert out["share_skew_rising"] is None


def test_lobe_aggregates_with_enough_roots(tmp_root):
    roots = ["SPY", "QQQ", "IWM", "DIA", "XLK", "XLF"]
    _state_df(roots).to_parquet(
        tmp_root / "data" / "options_entry" / "state.parquet", index=False)
    out = _compose_options_weather(tmp_root)
    assert out["n_roots"] == 6
    assert out["median_iv30"] == pytest.approx(0.25)
    assert out["share_skew_rising"] == pytest.approx(0.0)  # all falling in fixture
    assert out["display_only"] is True
    # no composite/score keys (RO-2)
    assert not any("score" in k or "rank" in k or "quality" in k for k in out)


def test_lobe_ignores_non_weather_roots(tmp_root):
    _state_df(["AAPL", "MSFT", "NVDA", "AMZN", "GOOG", "META"]).to_parquet(
        tmp_root / "data" / "options_entry" / "state.parquet", index=False)
    out = _compose_options_weather(tmp_root)
    assert out["n_roots"] is None  # none are weather roots → empty frame path
