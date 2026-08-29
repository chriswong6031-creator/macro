"""The delisted-symbol exit ledger and the three behaviours it drives
(research/RESOLUTION_20260806_SIDE_STORE_SYMBOLS.md).

CTRA and TPH were carried for three months as "frozen feeds". They were not frozen:
Coterra closed its merger with Devon Energy on 2026-05-07 and Tri Pointe Homes closed
its merger with Sumitomo Forestry on 2026-05-14, both filed Form 25-NSE, and both
store tips are last trading sessions. TCNNF looked like the delisting of the three
(yfinance said "possibly delisted") and was the one live security — Trulieve uplisted
from the OTC quote to NYSE:TRLV.

Two claims are pinned here that a green test suite would otherwise leave open:
  * a delisted name is dropped from the FETCH but keeps its config membership, its
    store and its page — the fail-dark direction is as wrong as the fail-loud one;
  * a delisted name loses scoring authority WITHOUT depending on the lag arithmetic,
    because the R2 circuit breaker empties `demote_map` on exactly the runs where a
    dead name regaining a score would be least visible.

No network, no real config: every ledger read is monkeypatched onto a fixture so the
assertions pin behaviour rather than today's two rows.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors import yahoo as yh  # noqa: E402
from lib import config, delisted_symbols as ds  # noqa: E402

REPO = Path(__file__).resolve().parent.parent

_ROW = {
    "company": "Coterra Energy Inc.",
    "last_session": "2026-05-07",
    "delisted_on": "2026-05-07",
    "reason": "acquisition",
    "acquirer": "Devon Energy",
    "successor_ticker": None,
}


@pytest.fixture
def fake_ledger(monkeypatch):
    """Install a ledger fixture, bypassing the lru_cache on the real loader."""
    def _install(rows: dict) -> dict:
        monkeypatch.setattr(ds, "ledger", lambda: rows)
        monkeypatch.setattr(ds, "tickers", lambda: frozenset(rows))
        return rows
    return _install


# ---------------------------------------------------------------------------
# The shipping ledger — the resolution itself, not just its plumbing
# ---------------------------------------------------------------------------

def test_shipping_ledger_holds_the_resolved_delistings():
    rows = ds.ledger()
    assert set(rows) == {"CTRA", "TPH", "AVB", "LEG"}
    assert rows["CTRA"]["delisted_on"] == "2026-05-07"
    assert rows["CTRA"]["acquirer"] == "Devon Energy"
    assert rows["TPH"]["delisted_on"] == "2026-05-14"
    # Last session precedes the delisting date for a deal closing before the open —
    # conflating the two would put the wrong date on the page.
    assert rows["TPH"]["last_session"] == "2026-05-13"
    assert rows["TPH"]["acquirer"] == "Sumitomo Forestry"
    # AVB (PR #6082 row): Friday last session before the Monday merger close.
    assert rows["AVB"]["delisted_on"] == "2026-08-17"
    assert rows["AVB"]["last_session"] == "2026-08-14"
    # LEG (EQR->VMRK migration PR row): merger closed ON the last session (08-26,
    # the 13.7M-share final print); the 25-NSE followed the next day.
    assert rows["LEG"]["delisted_on"] == "2026-08-27"
    assert rows["LEG"]["last_session"] == "2026-08-26"
    assert rows["LEG"]["acquirer"] == "Somnigroup International"


def test_no_shipping_row_claims_a_successor_ticker():
    """An all-stock or all-cash acquirer does not continue the acquired security's
    price line. A non-null `successor_ticker` here would be an instruction to splice
    a different company's tape onto this one — the #2120 seam-defect class."""
    for ticker, row in ds.ledger().items():
        assert row.get("successor_ticker") is None, ticker


def test_delisted_names_keep_their_config_membership_and_a_company_label():
    """Removing them from extra_tickers would drop them out of
    build_stock_library.universe() and 404 pages that are still linked (CSP-R1)."""
    scfg = config.load()["stock_search"]
    for ticker in ds.ledger():
        assert ticker in scfg["extra_tickers"], ticker
        assert scfg["extra_names"].get(ticker), ticker


def test_tcnnf_migrated_to_trlv_across_config_and_store():
    """A rename is a KEY MIGRATION: ticker, store filename and label move together,
    or the library mints two companies out of one."""
    scfg = config.load()["stock_search"]
    assert "TCNNF" not in scfg["extra_tickers"]
    assert "TRLV" in scfg["extra_tickers"]
    assert scfg["extra_names"]["TRLV"]["name"] == "Trulieve Cannabis"
    assert (REPO / "data" / "yahoo" / "TRLV.parquet").exists()
    assert not (REPO / "data" / "yahoo" / "TCNNF.parquet").exists()
    # A live rename must never be filed as an exit — that is the mistake the whole
    # resolution protocol exists to prevent, in the direction that loses a real feed.
    assert "TCNNF" not in ds.ledger() and "TRLV" not in ds.ledger()


# ---------------------------------------------------------------------------
# Loader — fail-open, never half-applied
# ---------------------------------------------------------------------------

def test_row_missing_a_required_field_is_dropped_whole(tmp_path, monkeypatch):
    """A half-read row would strip a name's score while leaving the page unable to
    say why — strictly worse than the cause-neutral note it replaces."""
    p = tmp_path / "delisted.yml"
    p.write_text(yaml.safe_dump({"symbols": {
        "GOOD": dict(_ROW),
        "BAD": {k: v for k, v in _ROW.items() if k != "delisted_on"},
    }}))
    monkeypatch.setattr(ds, "LEDGER_PATH", p)
    ds.ledger.cache_clear()
    try:
        assert set(ds.ledger()) == {"GOOD"}
    finally:
        ds.ledger.cache_clear()


@pytest.mark.parametrize("body", ["symbols: [CTRA, TPH]", "{{{ not yaml", ""])
def test_unusable_ledger_fails_open_to_empty(tmp_path, monkeypatch, body):
    """Empty means "nothing is known to be delisted", which degrades every consumer
    to its pre-ledger behaviour. Failing closed would let a YAML typo un-score names
    or blank pages."""
    p = tmp_path / "delisted.yml"
    p.write_text(body)
    monkeypatch.setattr(ds, "LEDGER_PATH", p)
    ds.ledger.cache_clear()
    try:
        assert ds.ledger() == {}
    finally:
        ds.ledger.cache_clear()


def test_disclosure_falls_back_to_english_acquirer_when_zh_absent(fake_ledger):
    fake_ledger({"CTRA": dict(_ROW)})
    assert ds.disclosure("CTRA")["acquirer_zh"] == "Devon Energy"
    assert ds.disclosure("AAPL") is None


def test_disclosure_withholds_the_audit_trail_from_the_page(fake_ledger):
    """Accession numbers and CIKs are for the next engineer, not for a stock page."""
    fake_ledger({"CTRA": dict(_ROW, cik="0000858470", receipts=["25-NSE"],
                              consideration="0.70 DVN per share")})
    assert set(ds.disclosure("CTRA")) == {
        "on", "last_session", "reason", "acquirer", "acquirer_zh", "successor_ticker"}


# ---------------------------------------------------------------------------
# collectors/yahoo.py — fetch exclusion, disclosed
# ---------------------------------------------------------------------------

def test_fetch_list_drops_delisted_but_maintained_list_keeps_it(fake_ledger, monkeypatch):
    """The store audit must still see a store the fetch no longer touches — that is
    the only check that could catch a wrong exit row or a reused ticker.

    Drives the REAL `all_tickers()` against a fixture config. Stubbing that method
    and asserting on the stub would pass with the filter deleted from the shipping
    body — the test would pin its own monkeypatch, which is how a mirrored guard
    goes vacuous."""
    fake_ledger({"CTRA": dict(_ROW)})
    monkeypatch.setattr(yh.config, "load", lambda: {
        "yahoo": {"tickers": {"sectors": ["XLE"]}},
        "stock_search": {"extra_tickers": ["AAPL", "CTRA", "TPH", "^GSPC"]},
        "themes": {"t1": {"tickers": ["MSFT"]}},
    })
    adapter = yh.YahooAdapter()
    fetch_list = adapter.all_tickers()
    assert "CTRA" not in fetch_list
    assert fetch_list == ["XLE", "AAPL", "TPH", "MSFT"]
    assert "CTRA" in adapter.maintained_tickers()


def test_fetch_list_is_unchanged_when_nothing_is_delisted(fake_ledger, monkeypatch):
    """The exclusion is scoped to the ledger — an empty ledger must not shrink the
    fetch list, which is the fail-open direction the loader is built for."""
    fake_ledger({})
    monkeypatch.setattr(yh.config, "load", lambda: {
        "yahoo": {"tickers": {"sectors": ["XLE"]}},
        "stock_search": {"extra_tickers": ["AAPL", "CTRA"]},
        "themes": {},
    })
    assert yh.YahooAdapter().all_tickers() == ["XLE", "AAPL", "CTRA"]


def test_delisted_exclusion_is_announced_with_its_reason(fake_ledger, capsys):
    fake_ledger({"CTRA": dict(_ROW)})
    assert yh._report_delisted_exclusions(["AAPL", "CTRA"]) == ["CTRA"]
    lines = [ln for ln in capsys.readouterr().out.splitlines() if ln.startswith("::")]
    assert len(lines) == 1
    # A ::notice, not a ::warning — this is the system working, not a defect. And it
    # must start the line: an annotation emitted through a logger is dropped by
    # GitHub Actions and reviews as an alarm that never fires.
    assert lines[0].startswith("::notice title=yahoo collector delisted::")
    assert "CTRA" in lines[0] and "2026-05-07" in lines[0] and "acquisition" in lines[0]


def test_drop_delisted_is_silent_so_the_notice_prints_once_per_run(fake_ledger, capsys):
    """`_drop_delisted` runs on several lists per fetch(); printing inside it would
    emit the same exclusion two or three times and read as separate events."""
    fake_ledger({"CTRA": dict(_ROW)})
    yh._drop_delisted(["AAPL", "CTRA"])
    yh._drop_delisted(["CTRA"])
    assert not [ln for ln in capsys.readouterr().out.splitlines() if ln.startswith("::")]


# ---------------------------------------------------------------------------
# collectors/yahoo.py::audit_store_freshness — delisted is not stale (#4616)
# ---------------------------------------------------------------------------

def _store(monkeypatch, tips: dict[str, str], rows: int = 500):
    def fake_read(group, t):
        if t not in tips:
            return None
        idx = pd.bdate_range(end=pd.Timestamp(tips[t]), periods=rows)
        return pd.DataFrame({"close": range(len(idx))}, index=idx)
    monkeypatch.setattr(yh.store, "read", fake_read)


def test_audit_classifies_a_finished_tape_as_delisted_not_stale(
        fake_ledger, monkeypatch, capsys):
    fake_ledger({"CTRA": dict(_ROW)})
    _store(monkeypatch, {"AAPL": "2026-08-05", "CTRA": "2026-05-07"})
    res = yh.audit_store_freshness(["AAPL", "CTRA"], group="yahoo")
    assert res["delisted"] == {"CTRA": "2026-05-07"}
    assert "CTRA" not in res["stale"] and "CTRA" not in res["stub"]
    lines = [ln for ln in capsys.readouterr().out.splitlines() if ln.startswith("::")]
    assert any(ln.startswith("::notice title=yahoo store audit delisted::") for ln in lines)
    # The permanently-unclearable frozen warning is exactly what this removes.
    assert not any("store audit frozen" in ln for ln in lines)


def test_audit_does_not_count_a_delisted_stub_against_the_row_floor(
        fake_ledger, monkeypatch):
    """A young listing that then delisted is permanently under 60 rows; leaving it in
    `stub` makes that warning unclearable too."""
    fake_ledger({"CTRA": dict(_ROW)})
    _store(monkeypatch, {"AAPL": "2026-08-05", "CTRA": "2026-05-07"}, rows=19)
    res = yh.audit_store_freshness(["AAPL", "CTRA"], group="yahoo")
    assert "CTRA" not in res["stub"]
    assert "AAPL" in res["stub"]


def test_audit_shouts_when_a_delisted_store_advances_past_its_last_session(
        fake_ledger, monkeypatch, capsys):
    """Either the resolution is wrong or the symbol was reused by another issuer —
    a reused ticker refills with the new holder's history and looks born-clean."""
    fake_ledger({"CTRA": dict(_ROW)})
    _store(monkeypatch, {"AAPL": "2026-08-05", "CTRA": "2026-08-05"})
    yh.audit_store_freshness(["AAPL", "CTRA"], group="yahoo")
    lines = [ln for ln in capsys.readouterr().out.splitlines() if ln.startswith("::")]
    hits = [ln for ln in lines if "delisted contradiction" in ln]
    assert len(hits) == 1 and hits[0].startswith("::warning") and "CTRA" in hits[0]


# ---------------------------------------------------------------------------
# scripts/build_stock_library.py — authority strip + truthful copy
# ---------------------------------------------------------------------------

def test_delisting_replaces_the_cause_neutral_note_rather_than_stacking_on_it():
    """`feed_stale` says "we don't know why this stopped"; `delisted` says why.
    Shipping both would have the page contradict itself in adjacent clauses."""
    from scripts import build_stock_library as bsl
    rec = {"ticker": "CTRA", "asof": "2026-05-07",
           "feed_stale": {"behind_days": 90, "lib_asof": "2026-08-05"},
           "conviction": {"score": 61.0, "potential": {"score": 40}}}
    bsl._apply_delisting(rec, ds.disclosure("CTRA"))
    assert "feed_stale" not in rec
    assert rec["delisted"]["on"] == "2026-05-07"
    assert rec["delisted"]["acquirer"] == "Devon Energy"
    # Same authority strip as the freshness demotion: no potential call, no score.
    assert "potential" not in rec["conviction"]
    assert rec["conviction"]["score"] is None


def test_authority_refused_even_when_the_circuit_breaker_emptied_the_demote_map():
    """R2 empties `demote_map` wholesale on a mass-freeze run. A delisting is a
    resolved fact, not a lag measurement, and must not be disarmed by one."""
    from scripts import build_stock_library as bsl
    assert bsl._authority_admits("CTRA", {}) is False
    assert bsl._authority_admits("TPH", {}) is False
    assert bsl._authority_admits("AAPL", {}) is True


def test_delisted_recs_never_reach_the_demotion_map_or_its_breaker_denominator(capsys):
    """A finished tape is neither fresh nor stale, so it is not assessable — and it
    must not dilute the breaker's read of how much of the LIVE universe is frozen.
    Here 2 of 4 recs are dead: counted, they would blow the 20% breaker and disarm
    the gate for the whole run, so a genuinely frozen live name would keep its
    score on the strength of two securities that no longer exist."""
    from scripts import build_stock_library as bsl
    recs = [{"ticker": "AAPL", "asof": "2026-08-05"},
            {"ticker": "MSFT", "asof": "2026-08-05"},
            {"ticker": "CTRA", "asof": "2026-05-07"},
            {"ticker": "TPH", "asof": "2026-05-13"}]
    lib_asof, demote_map, n_dark = bsl._feed_freshness(recs)
    assert lib_asof == "2026-08-05"
    assert demote_map == {}
    assert n_dark == 0
    assert "gate disarmed" not in capsys.readouterr().out


# ---------------------------------------------------------------------------
# The data/stocks lane (collectors/sector_holdings + scripts/heal_stocks_basis) —
# the AVB 2026-08 successor-splice incident. A delisted feed is not merely
# useless: Yahoo can answer the dead string with a merger successor's CONTINUING
# series (AVB's whole 1994-2026 history came back re-based by the ~2.793 exchange
# ratio plus live post-delisting successor bars), and the collector's
# basis-rebase path then imports it wholesale via a period='max' re-pull.
# ---------------------------------------------------------------------------

def test_stocks_retention_drops_ledger_names_but_union_wins():
    """_fetch_universe semantics with the exit ledger folded into `dead`: a name
    kept only by on-disk retention is dropped; a name in TODAY's union is fetched
    anyway (symbol reuse — the union side always wins)."""
    from collectors import sector_holdings as sh
    dead = frozenset({"AVB"})
    assert sh._fetch_universe(["AAPL"], ["AAPL", "AVB"], dead) == ["AAPL"]
    assert sh._fetch_universe(["AVB", "AAPL"], ["AVB"], dead) == ["AAPL", "AVB"]


def test_stocks_fetch_excludes_ledger_names_from_retention(fake_ledger, monkeypatch):
    """The wiring: StockPriceAdapter.fetch() passes ledger tickers into the
    retention exclusion, so a delisted-but-still-on-disk name is never requested."""
    from collectors import sector_holdings as sh
    fake_ledger({"AVB": dict(_ROW, company="AvalonBay Communities, Inc.",
                             last_session="2026-08-14", delisted_on="2026-08-17")})
    monkeypatch.setattr(sh, "top10_union", lambda: ["AAPL"])
    monkeypatch.setattr(sh, "_dead_tickers", lambda: frozenset())
    monkeypatch.setattr(sh.config, "load", lambda: {
        "yahoo": {"retries": 1, "backoff_base_s": 0, "batch_size": 50,
                  "upsert_basis_tol": 1e-3}})
    ad = sh.StockPriceAdapter()
    monkeypatch.setattr(ad, "stored_series", lambda: ["AAPL", "AVB"])
    monkeypatch.setattr(ad, "_needs_full", lambda t: False)
    requested: list[str] = []

    def fake_pull(period, tlist, frames, rebase, tol):
        requested.extend(tlist)
        for t in tlist:
            frames[t] = pd.DataFrame({"close": [1.0]})

    monkeypatch.setattr(ad, "_pull", fake_pull)
    frames = ad.fetch()
    assert "AAPL" in requested
    assert "AVB" not in requested
    assert "AVB" not in frames


def test_stocks_delisted_exclusion_is_announced_at_column_zero(fake_ledger, capsys):
    from collectors import sector_holdings as sh
    fake_ledger({"AVB": dict(_ROW, company="AvalonBay Communities, Inc.",
                             last_session="2026-08-14", delisted_on="2026-08-17")})
    dropped = sh._report_delisted_exclusions(["AAPL"], ["AAPL", "AVB"], ds.tickers())
    assert dropped == ["AVB"]
    lines = [ln for ln in capsys.readouterr().out.splitlines()
             if ln.startswith("::notice title=stocks collector delisted::")]
    assert len(lines) == 1
    assert "AVB(last session 2026-08-14)" in lines[0]


def test_stocks_union_side_ledger_name_is_not_announced(fake_ledger, capsys):
    """A ledger name still in today's union is being fetched (union wins), so the
    exclusion notice must not name it — a notice that is always on is a notice
    nobody reads."""
    from collectors import sector_holdings as sh
    fake_ledger({"AVB": dict(_ROW, company="AvalonBay Communities, Inc.")})
    assert sh._report_delisted_exclusions(["AVB"], ["AVB"], ds.tickers()) == []
    assert "::notice title=stocks collector delisted::" not in capsys.readouterr().out


def test_heal_stocks_basis_refuses_ledger_names_even_explicitly(fake_ledger, monkeypatch):
    """heal() must refuse an exit-ledger name even via --tickers: the wholesale
    period='max' rewrite is exactly the path that imported the AVB splice."""
    from scripts import heal_stocks_basis as hsb
    fake_ledger({"AVB": dict(_ROW, company="AvalonBay Communities, Inc.")})

    def boom(*a, **k):  # network sentinel — a refused name must never be fetched
        raise AssertionError("download attempted for a delisted name")

    monkeypatch.setattr(hsb, "_download", boom)
    assert hsb.heal(["AVB"], dry_run=False) == []


def test_heal_stocks_basis_detect_skips_ledger_names(fake_ledger, monkeypatch, tmp_path):
    from scripts import heal_stocks_basis as hsb
    fake_ledger({"AVB": dict(_ROW, company="AvalonBay Communities, Inc.")})
    d = tmp_path / "stocks"
    d.mkdir(parents=True)
    (d / "AVB.parquet").touch()  # glob only needs the name; no read should happen
    monkeypatch.setattr(hsb.config, "data_dir", lambda: tmp_path)

    def boom(*a, **k):
        raise AssertionError("download attempted for a delisted-only store")

    monkeypatch.setattr(hsb, "_download", boom)
    assert hsb.detect(tol=0.005) == []
