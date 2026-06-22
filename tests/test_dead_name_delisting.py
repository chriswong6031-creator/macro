"""Dead-name DELISTING-REASON detection + bankruptcy imputation
(collectors/edgar_delisting).

Network-free: the submissions fetcher (`_get_submissions`) is monkeypatched.
Invariants under test:
  * CLASSIFY — Item 1.03 → bankruptcy (earliest filing wins); seed/Item 5.01 →
    acquisition; neither → unknown; bankruptcy beats change-of-control on a tie.
  * RESILIENT — a name data.sec.gov declines is left uncached (retried next run)
    and the run never raises.
  * RESUMABLE + DRIP — a freshly-scanned name is skipped next non-forced run; the
    per-run scan count is capped by max_new.
  * LEAK-FREE IMPUTATION — the −100% terminal is stamped at >= the 8-K `filed`
    date and placed STRICTLY AFTER the last real bar; idempotent; needs a price
    anchor; the mis-resolution guard rejects an 8-K far from the end_date.
  * price_coverage() reports the reason breakdown + softens the caveat post-impute.
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from collectors import edgar_deadname_prices as dp
from collectors import edgar_delisting as dl


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #
def _recent(filings):
    """Build a submissions `recent` block from (form, items, date, accession) tuples."""
    return {
        "form": [f[0] for f in filings],
        "items": [f[1] for f in filings],
        "filingDate": [f[2] for f in filings],
        "accessionNumber": [f[3] for f in filings],
    }


def _setup(monkeypatch, tmp_path, resolved):
    """resolved: {ticker: (cik, method)}. Writes the CIK cache + a membership parquet
    whose end_date is 2016-01-01 for every name (so the impute guard window centres
    there)."""
    (tmp_path / "edgar").mkdir(parents=True, exist_ok=True)
    (tmp_path / "breadth").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(dl.config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(dl.time, "sleep", lambda *a, **k: None)
    (tmp_path / "edgar" / "dead_name_cik.json").write_text(
        json.dumps({t: {"cik": c, "method": m} for t, (c, m) in resolved.items()}))
    pd.DataFrame({"ticker": list(resolved),
                  "start_date": pd.to_datetime(["2010-01-01"] * len(resolved)),
                  "end_date": pd.to_datetime(["2016-01-01"] * len(resolved)),
                  "src": ["sp500"] * len(resolved)}).to_parquet(
        tmp_path / "breadth" / "sp1500_pit_membership.parquet")


def _seed_prices(tmp_path, ticker="AAA", last="2015-12-15", n=20, base=10.0):
    """Real recovered closes ending at `last`, so the imputer has an anchor."""
    idx = pd.bdate_range(end=pd.Timestamp(last), periods=n)
    df = pd.DataFrame({"ticker": ticker, "date": idx,
                       "close": [base - i * 0.2 for i in range(n)][::-1],
                       "source": "stooq"})
    df.to_parquet(tmp_path / "edgar" / "dead_name_prices.parquet")
    return df


# --------------------------------------------------------------------------- #
# classification
# --------------------------------------------------------------------------- #
def test_classify_bankruptcy_item_103():
    info = dl._classify_filings(
        _recent([("8-K", "1.03,3.01", "2015-12-20", "acc-bk"),
                 ("10-K", "", "2015-02-01", "acc-k")]), cik_method="company_tickers")
    assert info["reason"] == "bankruptcy"
    assert info["bankruptcy_date"] == "2015-12-20"
    assert info["bankruptcy_accession"] == "acc-bk"
    assert "1.03" in info["items_seen"]


def test_classify_earliest_bankruptcy_filing_wins():
    # two 1.03 filings — the EARLIEST is the first the wipeout is knowable (leak-free)
    info = dl._classify_filings(
        _recent([("8-K", "1.03", "2015-12-20", "late"),
                 ("8-K", "1.03", "2015-11-02", "early")]), cik_method="")
    assert info["bankruptcy_date"] == "2015-11-02" and info["bankruptcy_accession"] == "early"


def test_classify_acquisition_seed():
    info = dl._classify_filings(
        _recent([("8-K", "5.02", "2015-06-01", "a")]), cik_method="seed")
    assert info["reason"] == "acquisition" and info["method"] == "seed"


def test_classify_acquisition_change_control():
    info = dl._classify_filings(
        _recent([("8-K", "5.01,3.01", "2015-09-01", "a")]), cik_method="company_tickers")
    assert info["reason"] == "acquisition" and info["method"] == "8k_item_5.01"


def test_classify_unknown():
    info = dl._classify_filings(
        _recent([("8-K", "2.02,9.01", "2015-03-01", "a"),
                 ("10-Q", "", "2015-05-01", "b")]), cik_method="company_tickers")
    assert info["reason"] == "unknown" and info["bankruptcy_date"] is None


def test_classify_bankruptcy_wins_over_change_control():
    # acquired OUT of Chapter 11 → old equity still wiped → must flag bankruptcy
    info = dl._classify_filings(
        _recent([("8-K", "5.01", "2015-08-01", "cc"),
                 ("8-K", "1.03", "2015-07-01", "bk")]), cik_method="company_tickers")
    assert info["reason"] == "bankruptcy"


# --------------------------------------------------------------------------- #
# detection drip — resilient / resumable / capped
# --------------------------------------------------------------------------- #
def test_detect_classifies_and_caches(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path, {"AAA": (101, "company_tickers")})
    monkeypatch.setattr(dl, "_get_submissions", lambda cik: {
        "filings": {"recent": _recent([("8-K", "1.03", "2015-12-01", "x")])}})
    out = dl.detect_delisting_reasons(force=True)
    assert out["AAA"]["reason"] == "bankruptcy"
    cached = json.loads((tmp_path / "edgar" / "dead_name_delisting.json").read_text())
    assert cached["AAA"]["bankruptcy_date"] == "2015-12-01"


def test_detect_resilient_blocked_noop(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path, {"AAA": (101, "company_tickers")})
    monkeypatch.setattr(dl, "_get_submissions", lambda cik: None)   # blocked
    out = dl.detect_delisting_reasons(force=True)                   # must not raise
    assert "AAA" not in out                                         # left uncached → retried
    assert not (tmp_path / "edgar" / "dead_name_delisting.json").exists()


def test_detect_resumable_skips_fresh(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path, {"AAA": (101, "company_tickers")})
    calls = {"n": 0}

    def fetch(cik):
        calls["n"] += 1
        return {"filings": {"recent": _recent([("8-K", "1.03", "2015-12-01", "x")])}}

    monkeypatch.setattr(dl, "_get_submissions", fetch)
    dl.detect_delisting_reasons(force=True)
    dl.detect_delisting_reasons(force=False)        # fresh → skip
    assert calls["n"] == 1


def test_detect_drip_cap(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path,
           {t: (i + 1, "company_tickers") for i, t in enumerate(["AAA", "BBB", "CCC"])})
    seen = []
    monkeypatch.setattr(dl, "_get_submissions",
                        lambda cik: seen.append(cik) or {"filings": {"recent": _recent([])}})
    dl.detect_delisting_reasons(force=True, max_new=2)
    assert len(seen) == 2


# --------------------------------------------------------------------------- #
# imputation — leak-free / idempotent / anchored / guarded
# --------------------------------------------------------------------------- #
def _flag_bankrupt(tmp_path, ticker="AAA", filed="2015-12-20"):
    (tmp_path / "edgar" / "dead_name_delisting.json").write_text(json.dumps(
        {ticker: {"reason": "bankruptcy", "bankruptcy_date": filed, "method": "8k_item_1.03"}}))


def test_impute_terminal_when_filed_after_last_close(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path, {"AAA": (101, "company_tickers")})
    _seed_prices(tmp_path, last="2015-12-15", base=10.0)
    _flag_bankrupt(tmp_path, filed="2015-12-20")            # after the last real bar
    out = dl.impute_bankruptcies()
    imp = out[out["source"] == "imputed_bankruptcy"]
    assert len(imp) == 1
    assert imp["date"].iloc[0] == pd.Timestamp("2015-12-20")   # == filed (leak-free)
    assert imp["close"].iloc[0] == pytest.approx(dl._TERMINAL_CLOSE)
    # realized forward return into the wipe is ~ −100%
    last_real = out[out["source"] == "stooq"].sort_values("date")["close"].iloc[-1]
    assert imp["close"].iloc[0] / last_real - 1 < -0.99


def test_impute_strictly_after_last_close_when_filed_before(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path, {"AAA": (101, "company_tickers")})
    _seed_prices(tmp_path, last="2015-12-15")
    _flag_bankrupt(tmp_path, filed="2015-12-01")           # BEFORE last close (pink-sheet trading)
    out = dl.impute_bankruptcies()
    imp = out[out["source"] == "imputed_bankruptcy"]
    # placed strictly after the last real bar so it never overwrites realized data
    assert imp["date"].iloc[0] == pd.Timestamp("2015-12-16")
    assert (out[out["source"] == "stooq"]["date"].max()) == pd.Timestamp("2015-12-15")
    assert imp["date"].iloc[0] >= pd.Timestamp("2015-12-01")    # >= filed (leak-free)


def test_impute_idempotent(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path, {"AAA": (101, "company_tickers")})
    _seed_prices(tmp_path)
    _flag_bankrupt(tmp_path)
    dl.impute_bankruptcies()
    out = dl.impute_bankruptcies()                         # second run must not duplicate
    assert (out["source"] == "imputed_bankruptcy").sum() == 1


def test_impute_skips_name_without_price_anchor(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path, {"AAA": (101, "company_tickers"), "ZZZ": (102, "company_tickers")})
    _seed_prices(tmp_path, ticker="AAA")                   # only AAA has prices
    (tmp_path / "edgar" / "dead_name_delisting.json").write_text(json.dumps({
        "ZZZ": {"reason": "bankruptcy", "bankruptcy_date": "2015-12-20", "method": "8k_item_1.03"}}))
    out = dl.impute_bankruptcies()
    assert (out["source"] == "imputed_bankruptcy").sum() == 0   # no anchor → skipped


def test_impute_guard_rejects_8k_far_from_end_date(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path, {"AAA": (101, "company_tickers")})  # end_date 2016-01-01
    _seed_prices(tmp_path, last="2015-12-15")
    _flag_bankrupt(tmp_path, filed="2020-08-01")           # years after removal → mis-resolution
    out = dl.impute_bankruptcies()
    assert (out["source"] == "imputed_bankruptcy").sum() == 0


# --------------------------------------------------------------------------- #
# breakdown + coverage integration
# --------------------------------------------------------------------------- #
def test_delisting_breakdown_counts(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path,
           {"AAA": (1, "x"), "BBB": (2, "x"), "CCC": (3, "x")})
    (tmp_path / "edgar" / "dead_name_delisting.json").write_text(json.dumps({
        "AAA": {"reason": "bankruptcy"}, "BBB": {"reason": "acquisition"},
        "CCC": {"reason": "unknown"}}))
    b = dl.delisting_breakdown(["AAA", "BBB", "CCC"])
    assert b == {"bankruptcy": 1, "acquisition": 1, "unknown": 1, "n_classified": 3}


def test_price_coverage_softens_after_imputation(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path, {"AAA": (101, "company_tickers")})
    monkeypatch.setattr(dp.config, "data_dir", lambda: tmp_path)
    _seed_prices(tmp_path, last="2015-12-15")
    _flag_bankrupt(tmp_path, filed="2015-12-20")
    dl.impute_bankruptcies()
    cov = dp.price_coverage()
    assert cov["n_imputed_bankruptcies"] == 1
    assert cov["delisting_reason"]["bankruptcy"] == 1
    assert "imputed" in cov["residual_bias"] and "ACQUISITION" in cov["residual_bias"]
    assert cov["schema"] == "dead_name_price_coverage.v2"
