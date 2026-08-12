"""Tests for the ETF fund registry (W2, masterplan §3) + the HTML-grid header
fallback the same wave added to the collector.

Two layers under test:
  * engine.etf_registry.fund_registry — the pure config reader that types every
    board fund active / thematic_passive / sector. Tested against the REAL
    config.yml (coverage + no sponsor drift vs the universe block) and against
    small in-memory configs (missing block, bogus type, theme fallback, purity).
  * collectors.etf_holdings.EtfHoldingsAdapter._pick_html_table — First Trust's
    ASP.NET grid ships its header as an unmarked first ROW, so read_html numbers
    the columns 0..n and the header scan found nothing: SKYY/CIBR/FDN/GRID were
    configured but collected ZERO snapshots. The row-0 promotion fallback lives
    here rather than in tests/test_etf_new_sponsors.py because that file is owned
    by a parallel wave; move it over when the branches reconcile.

Everything is in-memory; nothing hits the network and nothing reads data/.
Matches the save-and-restore / __main__-harness style of the sibling ETF tests."""
from __future__ import annotations

import copy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collectors.etf_holdings import EtfHoldingsAdapter  # noqa: E402
from engine.etf_registry import (  # noqa: E402
    DEFAULT_TYPE,
    FUND_TYPES,
    UNKNOWN_THEME,
    fund_registry,
)
from lib import config  # noqa: E402


# =============================================================================
# A) the registry against the real config.yml
# =============================================================================

def _funds_missing_from_registry_block(cfg: dict) -> list[str]:
    """Funds the CONFIG BLOCK itself does not list. Deliberately not routed through
    fund_registry(): the loader unions the universe keys in, so a loader-level
    coverage assertion can never fail and would be a decorative gate."""
    block = (cfg.get("etf_holdings") or {}).get("registry") or {}
    funds = list((cfg.get("etf_holdings") or {}).get("universe") or {})
    funds += list((cfg.get("holdings") or {}).get("watchlist") or {})
    return [t for t in funds if t not in block]


def test_config_registry_block_lists_every_fund() -> None:
    missing = _funds_missing_from_registry_block(config.load())
    assert not missing, f"funds added to the universe with no registry row: {missing}"


def test_the_coverage_gate_can_actually_fail() -> None:
    # Mutation check on the gate above — an unregistered fund must be reported.
    cfg = _cfg({"AAA": {"sponsor": "ssga"}, "BBB": {"sponsor": "ssga"}},
               registry={"AAA": {"type": "sector", "sponsor": "ssga", "theme": "semis"}})
    assert _funds_missing_from_registry_block(cfg) == ["BBB"]


def test_loader_returns_every_universe_and_watchlist_fund() -> None:
    cfg = config.load()
    reg = fund_registry()
    universe = cfg["etf_holdings"]["universe"]
    watchlist = cfg["holdings"]["watchlist"]
    assert not [t for t in list(universe) + list(watchlist) if t not in reg]
    assert len(reg) >= len(universe) + len(watchlist)


def test_registry_types_are_from_the_enum() -> None:
    bad = {t: r["type"] for t, r in fund_registry().items() if r["type"] not in FUND_TYPES}
    assert not bad, f"unknown fund types: {bad}"


def test_registry_rows_are_fully_populated() -> None:
    for ticker, row in fund_registry().items():
        assert set(row) == {"type", "sponsor", "theme"}, f"{ticker}: {sorted(row)}"
        assert row["sponsor"] and row["sponsor"] != "unknown", f"{ticker}: no sponsor"
        assert row["theme"] and row["theme"] != UNKNOWN_THEME, f"{ticker}: no theme"


def test_registry_sponsor_never_drifts_from_the_universe() -> None:
    # The registry restates `sponsor` for readability, so pin the duplication:
    # an edit to one block that misses the other must fail here, not on the page.
    cfg = config.load()
    reg = fund_registry()
    drift = {t: (spec["sponsor"], reg[t]["sponsor"])
             for t, spec in cfg["etf_holdings"]["universe"].items()
             if reg[t]["sponsor"] != spec["sponsor"]}
    assert not drift, f"registry/universe sponsor drift: {drift}"


def test_manager_run_funds_are_typed_active() -> None:
    # Flow-vs-selection routing hangs off this: if a registry edit silently
    # demoted an active fund, its manager picks would be read as index flow.
    cfg = config.load()
    reg = fund_registry()
    for ticker, spec in cfg["etf_holdings"]["universe"].items():
        if spec.get("active"):
            assert reg[ticker]["type"] == "active", f"{ticker} is run by a manager"
    for ticker in cfg["holdings"]["watchlist"]:
        assert reg[ticker]["type"] == "active", f"{ticker} (ARK) is run by a manager"


# =============================================================================
# B) the loader's fail-soft behaviour on in-memory configs
# =============================================================================

def _cfg(universe: dict, registry: dict | None = None, watchlist: dict | None = None) -> dict:
    holdings = {"universe": universe}
    if registry is not None:
        holdings["registry"] = registry
    return {"etf_holdings": holdings, "holdings": {"watchlist": watchlist or {}}}


def test_loader_tolerates_a_missing_registry_block() -> None:
    reg = fund_registry(_cfg({"AAA": {"sponsor": "ssga", "category": "Junior Gold Miners"},
                              "BBB": {"sponsor": "ark", "active": True}}))
    assert set(reg) == {"AAA", "BBB"}
    assert reg["AAA"] == {"type": DEFAULT_TYPE, "sponsor": "ssga",
                          "theme": "junior-gold-miners"}
    # with no registry row the universe's own `active` flag still decides the type
    assert reg["BBB"]["type"] == "active"


def test_loader_tolerates_an_empty_and_a_null_registry_block() -> None:
    for empty in ({}, None):
        reg = fund_registry(_cfg({"AAA": {"sponsor": "ssga"}}, registry=empty))
        assert reg["AAA"]["type"] == DEFAULT_TYPE
        assert reg["AAA"]["theme"] == UNKNOWN_THEME


def test_unknown_type_degrades_to_the_default() -> None:
    reg = fund_registry(_cfg({"AAA": {"sponsor": "ssga"}},
                             registry={"AAA": {"type": "hedge_fund", "sponsor": "ssga",
                                               "theme": "space"}}))
    assert reg["AAA"]["type"] == DEFAULT_TYPE
    assert reg["AAA"]["theme"] == "space"      # the rest of the row still lands


def test_malformed_registry_row_does_not_drop_the_fund() -> None:
    reg = fund_registry(_cfg({"AAA": {"sponsor": "ssga", "category": "Space"}},
                             registry={"AAA": "sector"}))   # string, not a mapping
    assert reg["AAA"] == {"type": DEFAULT_TYPE, "sponsor": "ssga", "theme": "space"}


def test_registry_only_fund_is_still_returned() -> None:
    # ARKK/ARKW live in holdings.watchlist, not the universe; a registry-only row
    # must survive so the board can carry funds collected on another path.
    reg = fund_registry(_cfg({}, registry={"ARKK": {"type": "active", "sponsor": "ark",
                                                    "theme": "broad-innovation"}}))
    assert reg["ARKK"]["type"] == "active"


def test_watchlist_funds_are_covered_without_a_registry_row() -> None:
    reg = fund_registry(_cfg({}, watchlist={"ARKK": {"sponsor": "ark"}}))
    assert reg["ARKK"] == {"type": DEFAULT_TYPE, "sponsor": "ark", "theme": UNKNOWN_THEME}


def test_loader_does_not_mutate_the_config_it_is_given() -> None:
    # config.load() is lru_cached, so a mutating reader would poison every caller.
    cfg = _cfg({"AAA": {"sponsor": "ssga"}}, registry={"AAA": {"type": "sector"}})
    before = copy.deepcopy(cfg)
    fund_registry(cfg)
    assert cfg == before


# =============================================================================
# C) _pick_html_table — the First Trust unmarked-header regression
# =============================================================================

_TH_TABLE = """<table><tr><th>Ticker</th><th>Shares</th><th>Weight</th></tr>
<tr><td>AAA</td><td>10</td><td>50%</td></tr></table>"""
_ROW0_TABLE = """<table><tr><td>Security Name</td><td>Identifier</td>
<td>Shares / Quantity</td><td>Market Value</td><td>Weighting</td></tr>
<tr><td>Arista Networks, Inc.</td><td>ANET</td><td>675146</td>
<td>$133,577,636.10</td><td>4.06%</td></tr></table>"""
_JUNK_TABLE = "<table><tr><td>Fund Summary</td><td>Holdings</td></tr></table>"


def test_pick_html_table_reads_a_real_th_header() -> None:
    df = EtfHoldingsAdapter._pick_html_table(
        _TH_TABLE, need_weight=True, need_shares=True, who="t")
    assert list(df.columns) == ["ticker", "shares", "weight"]
    assert len(df) == 1


def test_pick_html_table_promotes_an_unmarked_header_row() -> None:
    df = EtfHoldingsAdapter._pick_html_table(
        _JUNK_TABLE + _ROW0_TABLE, need_weight=True, need_shares=True, who="firsttrust")
    assert list(df.columns) == ["security_name", "identifier", "shares_/_quantity",
                                "market_value", "weighting"]
    assert len(df) == 1, "the promoted header row must not survive as data"
    assert df["identifier"].iloc[0] == "ANET"


def test_pick_html_table_prefers_a_real_header_over_promotion() -> None:
    # The fallback must never re-interpret a table that already has a header —
    # the row-0 candidate is listed FIRST here on purpose.
    df = EtfHoldingsAdapter._pick_html_table(
        _ROW0_TABLE + _TH_TABLE, need_weight=True, need_shares=True, who="t")
    assert list(df.columns) == ["ticker", "shares", "weight"]


def test_pick_html_table_still_raises_when_nothing_matches() -> None:
    try:
        EtfHoldingsAdapter._pick_html_table(
            _JUNK_TABLE, need_weight=True, need_shares=True, who="nobody")
    except ValueError as e:
        assert "no holdings table found" in str(e)
    else:
        raise AssertionError("expected ValueError on a page with no holdings table")


def test_pick_html_table_promotion_feeds_normalize_cleanly() -> None:
    # End-to-end on the shape that was dead: promoted header -> _fetch_firsttrust's
    # column renames -> _normalize's currency/percent coercion.
    df = EtfHoldingsAdapter._pick_html_table(
        _ROW0_TABLE, need_weight=True, need_shares=True, who="firsttrust")
    df = df.rename(columns={"security_name": "name", "identifier": "ticker"})
    out = EtfHoldingsAdapter._normalize(df, "SKYY", "2026-08-11", wcol="weighting",
                                        scol="shares_/_quantity", mcol="market_value")
    assert list(out.columns) == ["ticker", "name", "weight_pct", "shares",
                                 "market_value", "as_of"]
    assert out["ticker"].iloc[0] == "ANET"
    assert abs(float(out["weight_pct"].iloc[0]) - 4.06) < 1e-9
    assert float(out["shares"].iloc[0]) == 675146
    assert abs(float(out["market_value"].iloc[0]) - 133577636.10) < 1e-6


if __name__ == "__main__":
    tests = [
        test_config_registry_block_lists_every_fund,
        test_the_coverage_gate_can_actually_fail,
        test_loader_returns_every_universe_and_watchlist_fund,
        test_registry_types_are_from_the_enum,
        test_registry_rows_are_fully_populated,
        test_registry_sponsor_never_drifts_from_the_universe,
        test_manager_run_funds_are_typed_active,
        test_loader_tolerates_a_missing_registry_block,
        test_loader_tolerates_an_empty_and_a_null_registry_block,
        test_unknown_type_degrades_to_the_default,
        test_malformed_registry_row_does_not_drop_the_fund,
        test_registry_only_fund_is_still_returned,
        test_watchlist_funds_are_covered_without_a_registry_row,
        test_loader_does_not_mutate_the_config_it_is_given,
        test_pick_html_table_reads_a_real_th_header,
        test_pick_html_table_promotes_an_unmarked_header_row,
        test_pick_html_table_prefers_a_real_header_over_promotion,
        test_pick_html_table_still_raises_when_nothing_matches,
        test_pick_html_table_promotion_feeds_normalize_cleanly,
    ]
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL {fn.__name__}: {type(e).__name__}: {e}")
    if failed:
        print(f"{failed}/{len(tests)} FAILED")
        sys.exit(1)
    print("all etf-registry tests passed")
