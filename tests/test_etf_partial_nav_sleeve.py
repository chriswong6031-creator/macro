"""W3 — swap-sleeve funds: the equity sleeve, and the guard that knows it is partial.

A fund like Roundhill's NCLD parks a deliberate slice of NAV outside listed
equity: ~30% T-bills, a government money-market sweep, and total-return swaps on
the very names its direct position cannot hold under the RIC diversification
tests. Two things had to be true before such a fund could ship, and this file
pins both.

1) ONLY THE EQUITY SLEEVE IS COUNTED. `is_non_equity_holding` already dropped the
   "-USD CASH-" form (masterplan §6b) but two sleeve forms walked straight past it:

     * a government money-market SWEEP whose ticker is a real symbol and whose
       name says neither "cash" nor "money market" — FGXXX "First American
       Government Obligations Fund", AGPXX "Invesco Government & Agency
       Portfolio". Measured on the live feed these carry shares EXACTLY equal to
       market_value (a $1-NAV fund: the "share count" IS a dollar balance), and in
       METV that balance was 18.9% of the fund's TOTAL share count at 0.81% of its
       weight. It sits inside the SUM-ratio denominator `active_changes_dir` uses,
       so METV measured a 1.4164 scale against a true 1.1688 and EVERY constituent
       published a phantom +21.18% active change against a 5% alert bar.

     * a swap line the NAME cannot give away. Roundhill files the same TRS two
       ways depending on the date: "21873S108 TRS 090827 GS" named
       "COREWEAVE, INC.-SWAP-GOLD-L", and "21873S108 SWP" whose name column merely
       REPEATS the ticker. The second form survived as a 16.38% and a 20.38%
       phantom equity constituent whose shares are swap units.

   Both fixes are anchored NARROWLY on purpose, and the false-positive cases below
   are the reason: "BILL Holdings" (XSW/FINX/MDY), "Liquidity Services" (EBIZ),
   "Treasury Wine Estates" and TriMas (ticker TRS) are real issuers that a loose
   `bill|liquidity|treasury|trs` rule would silently delete from the board.

2) A PARTIAL SLEEVE IS NOT A BROKEN PARSE. With the sleeve dropped, a perfectly
   parsed NCLD snapshot sums to ~63, and the weight-sum guard — whose whole job is
   to reject a snapshot summing far from 100 — would quarantine every one of them.
   `nav_equity_frac` is the declared fraction that rescales the bounds. It is
   declared, never derived: a fraction computed from the snapshot it checks could
   not fail, and the guard's value is that it still can.

Run: python3 -m pytest tests/test_etf_partial_nav_sleeve.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import collectors.holdings as ch  # noqa: E402
import lib.config as config  # noqa: E402
from engine import etf_consensus as ec  # noqa: E402
from engine import holdings_signals as hs  # noqa: E402


@pytest.fixture(autouse=True)
def _clear_snapshot_caches():
    hs._SNAP_CACHE.clear()
    hs._FLEET_LATEST.clear()
    yield
    hs._SNAP_CACHE.clear()
    hs._FLEET_LATEST.clear()


# =============================================================================
# 1) the equity sleeve — what the predicate drops, and what it must NOT
# =============================================================================

# Every row here was copied off a live sponsor file (the fund it appeared in is
# named), so the pin degrades the day a feed changes shape rather than the day
# someone edits the regex to match its own test.
DROPPED = [
    ("FGXXX", "First American Government Obligations Fund 12/01/2031", "METV/CHAT/NCLD"),
    ("AGPXX", "Invesco Government & Agency Portfolio 12/31/2031", "BLOK/SILJ"),
    ("AGPXX", "Invesco Government &amp; Agency Portfolio", "PHO/PPA/PSI — HTML-escaped"),
    ("912797UJ4", "United States Treasury Bill 10/08/2026", "NCLD"),
    ("21873S108 TRS 090827 GS", "COREWEAVE, INC.-SWAP-GOLD-L", "NCLD, named form"),
    ("21873S108 SWP", "21873S108 SWP", "NCLD, name repeats the ticker"),
    ("N97284108 SWP", "N97284108 SWP", "NCLD, name repeats the ticker"),
]

KEPT = [
    ("BILL", "BILL HOLDINGS INC", "XSW/FINX — a bare `bill` rule kills it"),
    ("BILL", "BILL Holdings Inc.", "MDY"),
    ("LQDT", "LIQUIDITY SERVICES INC", "EBIZ — a bare `liquidity` rule kills it"),
    ("TSRYY", "Treasury Wine Estates Ltd", "a bare `treasury` rule kills it"),
    ("TRS", "TriMas Corp", "the swap TOKEN must not match a whole ticker"),
    ("SWP", "Swoop Aero Ltd", "same, for the other marker"),
    ("CRWV", "CoreWeave Inc", "NCLD's real equity sleeve"),
    ("AG", "First Majestic Silver Corp", "SILJ"),
    ("1211 HK", "BYD Co Ltd", "BATT — a two-token FOREIGN ticker is not a swap"),
    ("006400 KS", "Samsung SDI Co Ltd", "BATT"),
    ("002709 C2", "Guangzhou Tinci Materials Technology Co Ltd", "BATT"),
]


@pytest.mark.parametrize("ticker,name,seen_in", DROPPED)
def test_sleeve_rows_are_not_equity(ticker: str, name: str, seen_in: str) -> None:
    assert ch.is_non_equity_holding(ticker, name), f"{ticker} ({seen_in}) must drop"


@pytest.mark.parametrize("ticker,name,why", KEPT)
def test_real_issuers_survive_the_sleeve_patterns(ticker: str, name: str, why: str) -> None:
    assert not ch.is_non_equity_holding(ticker, name), f"{ticker} must survive: {why}"


def test_the_mutual_fund_ticker_belt_needs_both_halves() -> None:
    """The 5-letter-X structural rule is a belt for a sweep vehicle we have not
    seen yet, so it may never fire on its own — neither half is sufficient."""
    assert ch.is_non_equity_holding("XXXXX", "Some Government Obligations Fund")
    assert not ch.is_non_equity_holding("XXXXX", "Xylophone Exports Inc")
    assert not ch.is_non_equity_holding("XYZ", "Some Government Obligations")


def test_the_sweep_line_really_is_a_dollar_balance() -> None:
    """WHY these rows are dropped rather than kept as tiny positions: a $1-NAV
    money-market fund reports shares == market_value, so its "share count" is a
    balance that moves with cash flows, not a float claim that moves with a
    decision. Pinned against the shipped snapshot the fix was measured on."""
    p = Path(__file__).resolve().parent.parent / "data" / "etf_holdings" / "METV"
    snaps = sorted(p.glob("*.parquet")) if p.exists() else []
    if not snaps:
        pytest.skip("data/etf_holdings is not checked out in this worktree")
    df = pd.read_parquet(snaps[-1])
    row = df[df["ticker"].astype(str) == "FGXXX"]
    if row.empty:
        pytest.skip("the sponsor dropped the sweep line from METV's newest file")
    r = row.iloc[0]
    assert float(r["shares"]) == pytest.approx(float(r["market_value"]), rel=1e-9)


def test_dropping_the_sweep_moves_the_scale_the_board_publishes() -> None:
    """The consequence, not just the classification: with the sweep line in the
    denominator the common scale factor is wrong, so every constituent carries a
    phantom active change. Rebuilt from the METV shape measured on 2026-08-12."""
    # 6 real positions that all grew 1.17x, plus a sweep balance that grew 15x.
    first = pd.Series({f"BAL{i}": 1000.0 for i in range(1, 7)} | {"FGXXX": 112_731.0})
    last = pd.Series({f"BAL{i}": 1170.0 for i in range(1, 7)} | {"FGXXX": 1_722_755.0})
    with_sweep = last.sum() / first.sum()
    without = (last.drop("FGXXX").sum() / first.drop("FGXXX").sum())
    assert without == pytest.approx(1.17)
    phantom = 100 * (with_sweep / without - 1)
    assert phantom > 5, (
        "the fixture must reproduce a phantom ABOVE the 5% alert bar, else it "
        f"pins nothing (got {phantom:.2f}%)")


# =============================================================================
# 2) nav_equity_frac — the declared partial sleeve
# =============================================================================

def _with_universe(monkeypatch, universe: dict) -> None:
    monkeypatch.setattr(config, "load", lambda: {"etf_holdings": {"universe": universe}})


def test_an_undeclared_fund_keeps_the_full_nav_bounds(monkeypatch) -> None:
    _with_universe(monkeypatch, {"PLAIN": {"sponsor": "globalx"}})
    assert hs.nav_equity_frac("PLAIN") == 1.0
    assert hs.weight_sum_bounds("PLAIN") == hs.WEIGHT_SUM_BOUNDS
    assert hs.weight_sum_bounds("NOT_A_FUND") == hs.WEIGHT_SUM_BOUNDS


def test_a_declared_fraction_scales_the_bounds_relatively(monkeypatch) -> None:
    """Relative, so the tolerance stays ±20% OF THE SLEEVE — an absolute ±20 band
    would get proportionally looser the smaller the declared sleeve is."""
    _with_universe(monkeypatch, {"NCLD": {"sponsor": "roundhill", "nav_equity_frac": 0.63}})
    assert hs.nav_equity_frac("NCLD") == 0.63
    lo, hi = hs.weight_sum_bounds("NCLD")
    assert (lo, hi) == pytest.approx((50.4, 75.6))
    assert hi / lo == pytest.approx(hs.WEIGHT_SUM_BOUNDS[1] / hs.WEIGHT_SUM_BOUNDS[0])


@pytest.mark.parametrize("bad", [0, -0.5, 1.5, "sixty-three", None, float("nan")])
def test_a_nonsense_declaration_falls_back_to_full_nav(monkeypatch, bad) -> None:
    """A typo must not open the guard to any weight sum at all — it fails CLOSED,
    back onto the strict full-NAV bounds."""
    _with_universe(monkeypatch, {"ODD": {"nav_equity_frac": bad}})
    assert hs.nav_equity_frac("ODD") == 1.0


def _write(d: Path, asof: str, shares: pd.Series, weights: pd.Series) -> Path:
    d.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame({
        "ticker": list(shares.index),
        "name": [f"{t} Corp" for t in shares.index],
        "weight_pct": [float(weights[t]) for t in shares.index],
        "shares": shares.astype(float).values,
        "market_value": (shares * 10.0).astype(float).values,
        "as_of": asof,
    })
    p = d / f"{asof}.parquet"
    df.to_parquet(p)
    return p


def _sleeve_fund(tmp_path: Path, sum_pct: float, name: str = "NCLD") -> Path:
    """Two snapshots of a fund whose equity lines sum to `sum_pct` of NAV."""
    d = tmp_path / name
    tickers = [f"BAL{i}" for i in range(1, 7)]
    w = pd.Series({t: sum_pct / len(tickers) for t in tickers})
    _write(d, "2026-08-07", pd.Series({t: 1000.0 for t in tickers}), w)
    _write(d, "2026-08-12", pd.Series({t: 1000.0 for t in tickers} | {"BAL1": 1200.0}), w)
    return d


def test_a_declared_sleeve_is_read_instead_of_quarantined(tmp_path, monkeypatch, capsys) -> None:
    """The whole point: NCLD's real snapshots sum to 61.55-64.40, which the
    unscaled 80-120 guard rejects outright — the fund could never reach the board."""
    _with_universe(monkeypatch, {"NCLD": {"nav_equity_frac": 0.63}})
    d = _sleeve_fund(tmp_path, 63.0)
    dec = hs.fund_flow_decomposition(d, 10, fund="NCLD")
    assert dec is not None and dec["quarantined"] == []
    assert dec["by_ticker"]["BAL1"]["selection_shares"] == pytest.approx(200.0)
    assert "::warning" not in capsys.readouterr().out


def test_the_same_snapshot_is_quarantined_without_the_declaration(tmp_path, monkeypatch) -> None:
    """The counterfactual that makes the test above mean something: it is the
    DECLARATION doing the work, not a fixture that would have passed anyway."""
    _with_universe(monkeypatch, {"NCLD": {}})
    d = _sleeve_fund(tmp_path, 63.0)
    assert hs.fund_flow_decomposition(d, 10, fund="NCLD") is None


def test_a_declared_fund_can_still_fail_the_guard(tmp_path, monkeypatch, capsys) -> None:
    """A declared fraction relaxes the bounds, it does not remove them: a REAL
    broken parse for the same fund is still quarantined, and still printed."""
    _with_universe(monkeypatch, {"NCLD": {"nav_equity_frac": 0.63}})
    d = _sleeve_fund(tmp_path, 63.0)
    tickers = [f"BAL{i}" for i in range(1, 7)]
    _write(d, "2026-08-13", pd.Series({t: 1000.0 for t in tickers}),
           pd.Series({t: 4.0 for t in tickers}))          # sums to 24, not ~63
    dec = hs.fund_flow_decomposition(d, 10, fund="NCLD")
    assert dec is not None and dec["quarantined"] == ["2026-08-13"]
    line = next((ln for ln in capsys.readouterr().out.splitlines()
                 if "etf-snapshot-quarantine" in ln), "")
    assert line.startswith("::warning "), (
        "the null has to be PRINTED at line start or GitHub drops it: " + repr(line))
    assert "NCLD" in line


def test_a_full_nav_fund_is_still_held_to_the_strict_bounds(tmp_path, monkeypatch) -> None:
    """The relaxation must not leak to funds that never declared anything."""
    _with_universe(monkeypatch, {"PLAIN": {}})
    d = _sleeve_fund(tmp_path, 63.0, name="PLAIN")
    assert hs.fund_flow_decomposition(d, 10, fund="PLAIN") is None


def test_the_sparkline_reads_the_same_sleeve_as_the_scored_path(tmp_path, monkeypatch) -> None:
    """The guard verdict has to reach the RANKED consumer too. If the fund name
    never got to `_trajectory_snapshots`, the sparkline would quarantine exactly
    the snapshots the numbers beside it accepted — a picture denying its own row."""
    _with_universe(monkeypatch, {"NCLD": {"nav_equity_frac": 0.63}})
    d = _sleeve_fund(tmp_path, 63.0)
    assert len(ec._trajectory_snapshots(d, 12, fund="NCLD")) == 2
    assert ec._trajectory_snapshots(d, 12, fund="PLAIN") == []


def test_the_directory_name_is_the_fallback_fund_identity(tmp_path, monkeypatch) -> None:
    """Both call sites resolve the fund the same way, so a caller that passes no
    explicit name still gets the declared bounds rather than silently the strict
    ones."""
    _with_universe(monkeypatch, {"NCLD": {"nav_equity_frac": 0.63}})
    d = _sleeve_fund(tmp_path, 63.0)
    assert hs.fund_flow_decomposition(d, 10) is not None
    assert len(ec._trajectory_snapshots(d, 12)) == 2


# =============================================================================
# 3) the funds this shipped for
# =============================================================================

def _cfg_block() -> dict:
    return config.load().get("etf_holdings") or {}


@pytest.mark.parametrize("ticker,sponsor,ftype,theme", [
    ("SILJ", "amplify", "thematic_passive", "precious-miners"),
    ("BATT", "amplify", "thematic_passive", "critical-minerals"),
    ("NCLD", "roundhill", "active", "data-center"),
])
def test_the_w3_funds_are_configured(ticker: str, sponsor: str, ftype: str, theme: str) -> None:
    uni = _cfg_block().get("universe") or {}
    reg = _cfg_block().get("registry") or {}
    assert ticker in uni, f"{ticker} missing from etf_holdings.universe"
    assert uni[ticker]["sponsor"] == sponsor
    assert reg.get(ticker) == {"type": ftype, "sponsor": sponsor, "theme": theme}


def test_only_declared_funds_carry_a_nav_equity_frac() -> None:
    """The key is an exception, not a default — if it starts spreading, the guard
    it relaxes is being turned off fund by fund instead of parsers being fixed."""
    uni = _cfg_block().get("universe") or {}
    declared = {t for t, s in uni.items() if isinstance(s, dict) and "nav_equity_frac" in s}
    assert declared == {"NCLD"}, f"undocumented partial-NAV declarations: {declared - {'NCLD'}}"


def test_every_w3_fund_shipped_with_a_real_snapshot() -> None:
    """House rule: a fund ships only with a parsed snapshot on disk, inside its
    own declared bounds, in the shipped schema."""
    root = Path(__file__).resolve().parent.parent / "data" / "etf_holdings"
    if not root.exists():
        pytest.skip("data/etf_holdings is not checked out in this worktree")
    for ticker in ("SILJ", "BATT", "NCLD"):
        snaps = sorted((root / ticker).glob("*.parquet"))
        assert snaps, f"{ticker} was configured with no snapshot on disk"
        lo, hi = hs.weight_sum_bounds(ticker)
        for p in snaps:
            df = pd.read_parquet(p)
            assert list(df.columns) == ["ticker", "name", "weight_pct", "shares",
                                        "market_value", "as_of"], f"{ticker}/{p.stem}"
            assert len(df) > 5, f"{ticker}/{p.stem}: {len(df)} rows"
            assert not df["shares"].isna().any(), f"{ticker}/{p.stem}: null shares"
            assert str(df["as_of"].iloc[0]) == p.stem, f"{ticker}/{p.stem}: as_of drift"
            wsum = float(pd.to_numeric(df["weight_pct"], errors="coerce").sum())
            assert lo <= wsum <= hi, f"{ticker}/{p.stem}: weight sum {wsum:.2f}"
