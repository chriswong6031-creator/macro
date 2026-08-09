"""intel_hub US universe-membership gate (`_scope_universe`).

The intelligence bundle's altdata feeder delivers FOREIGN listings symbol-shaped —
ANANTRAJ (NSE), BULTEN (Stockholm), CEMARGOS (.BO suffix stripped at keying), plus
German/Korean/SIX/LSE codes, unpriced OTC ordinaries (AKZOF) and warrants (ACHR.WS).
None of them can ever be graded: the forward track record is SPY-relative off the US
price layer, so each accrued a ledger row per night that could never mature (measured
2026-08-08: 1,045 of 3,083 names, 78,105 of 170,676 rows).

The gate decides membership ONCE, at ingestion:
  member = US-exchange roster (latest symbol_directory snapshot, test issues dropped)
           OR the hub's own US price spine (data/yahoo parquet | breadth close cache)
with ./- normalization ONLY (BRK.B ↔ BRK-B), never a prefix/suffix strip-and-map, no
China-parquet membership, and a fail-open ladder that leaves the universe untouched
(applied:false + reason) whenever the roster can't be trusted.

Every test isolates config.ROOT to tmp_path — build() persists a velocity ledger under
ROOT, so the real data/ tree must never be read or written here.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import intel_hub  # noqa: E402
from lib import config  # noqa: E402

TODAY = date(2026, 8, 8)


# --------------------------------------------------------------------------- #
# fixtures / helpers
# --------------------------------------------------------------------------- #

@pytest.fixture()
def root(tmp_path, monkeypatch):
    """Isolate config.ROOT — intel_hub reads the roster/price stores and WRITES the
    velocity ledger relative to it, so the real repo tree stays untouched."""
    monkeypatch.setattr(config, "ROOT", tmp_path)
    return tmp_path


def _roster_rows(symbols, *, snap: str = "2026-08-08", test_issues=()) -> list[dict]:
    ti = set(test_issues)
    return [{"date": snap, "symbol": s, "security_name": f"{s} Inc.", "exchange": "NASDAQ",
             "etf": False, "test_issue": s in ti, "is_preferred": False,
             "source": "nasdaqlisted"} for s in symbols]


def _write_roster(root: Path, named=(), *, n_filler: int = 8_100,
                  snap: str = "2026-08-08", test_issues=()) -> Path:
    """A synthetic symbol_directory snapshot: `named` symbols + enough generated filler
    to clear _ROSTER_SANITY_FLOOR (the real roster is ~13.1k)."""
    symbols = [f"F{i:04d}" for i in range(n_filler)] + list(named)
    d = root / "data" / "symbol_directory" / "snapshots"
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{snap}.parquet"
    pd.DataFrame(_roster_rows(symbols, snap=snap, test_issues=test_issues)).to_parquet(p)
    return p


def _write_prices(root: Path, ticker: str, sub: str = "yahoo", n: int = 40) -> Path:
    """A minimal close series (under the 60-bar on-demand gate threshold, so build()
    stays fast). `sub` selects the store: yahoo (US spine) vs china_stocks (NOT a spine)."""
    d = root / "data" / sub
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{ticker}.parquet"
    idx = pd.date_range("2026-05-01", periods=n, freq="B")
    pd.DataFrame({"close": [100.0 + i for i in range(n)]}, index=idx).to_parquet(p)
    return p


def _v(name: str = "ACME Corp") -> dict:
    """Minimal per-ticker facet bundle — the shape _dossier consumes."""
    return {"alt": {"signal_score": 75, "action": "BUY", "extended": False},
            "radar": {"state": "POSITIVE_DIVERGENCE", "lifecycle": "forming"},
            "news": {"sentiment_lean": "pos", "sentiment_score": 0.1, "n_recent": 0,
                     "sectors": ["XLK"], "name": name, "baskets": []}}


def _bundle(*tickers: str) -> dict:
    return {"tickers": {t: _v(f"{t} Corp") for t in tickers}}


def _cand(ticker: str, score: float = 0.9, source: str = "insider_cluster") -> dict:
    return {"ticker": ticker, "disc_score": score, "source": source,
            "reason": "quiet accumulation"}


def _build(**kw) -> dict:
    return intel_hub.build(today=TODAY, **kw)


def _dossier_tickers(hub: dict) -> set[str]:
    """Every dossier the build produced (track_rows carries ALL of them, not just top)."""
    return {r["t"] for r in hub["track_rows"]}


# --------------------------------------------------------------------------- #
# 1 — the headline case: an off-roster, unpriced foreign listing is excluded
# --------------------------------------------------------------------------- #

def test_off_roster_unpriced_name_is_excluded(root):
    _write_roster(root, named=["AAL"])
    hub = _build(bundle=_bundle("AAL", "ANANTRAJ"), policy=None)

    us = hub["universe_scope"]
    assert us["applied"] is True
    assert us["n_excluded"] == 1, us
    assert "ANANTRAJ" in us["excluded_sample"]
    assert us["n_in"] == 1

    assert "ANANTRAJ" not in _dossier_tickers(hub), "excluded name still built a dossier"
    assert "ANANTRAJ" not in {r["t"] for r in hub["track_rows"]}, (
        "excluded name still accrued a track-record row — the 46%-of-ledger defect"
    )
    assert "ANANTRAJ" not in {d["ticker"] for d in hub["command"]}
    assert "AAL" in _dossier_tickers(hub)
    assert hub["n_universe"] == 1


# --------------------------------------------------------------------------- #
# 2 — roster listing alone confers membership (the AAL case: no price store at all)
# --------------------------------------------------------------------------- #

def test_roster_listed_name_without_price_data_stays_a_member(root):
    _write_roster(root, named=["AAL"])
    assert not (root / "data" / "yahoo" / "AAL.parquet").exists()

    hub = _build(bundle=_bundle("AAL"), policy=None)
    assert hub["universe_scope"]["applied"] is True
    assert hub["universe_scope"]["n_excluded"] == 0
    assert "AAL" in _dossier_tickers(hub)


# --------------------------------------------------------------------------- #
# 3 — the US price spine alone confers membership (the RHHBY case: off-roster ADR
#     that the hub can nonetheless price, so it remains gradeable)
# --------------------------------------------------------------------------- #

def test_off_roster_name_with_yahoo_parquet_stays_a_member(root):
    _write_roster(root, named=["AAL"])           # RHHBY deliberately NOT on the roster
    _write_prices(root, "RHHBY")

    hub = _build(bundle=_bundle("AAL", "RHHBY"), policy=None)
    us = hub["universe_scope"]
    assert us["applied"] is True
    assert us["n_excluded"] == 0, us["excluded_sample"]
    assert "RHHBY" in _dossier_tickers(hub)


# --------------------------------------------------------------------------- #
# 4 — ./- normalization: roster BRK.B must match a feed emitting BRK-B (and back)
# --------------------------------------------------------------------------- #

def test_dot_dash_swap_matches_roster(root):
    _write_roster(root, named=["BRK.B"])
    hub = _build(bundle=_bundle("BRK-B"), policy=None)

    us = hub["universe_scope"]
    assert us["applied"] is True
    assert us["n_excluded"] == 0, us["excluded_sample"]
    assert "BRK-B" in _dossier_tickers(hub)
    # both directions, and the swap is the ONLY normalization (no suffix strip-and-map)
    assert intel_hub._dot_dash("BRK-B") == {"BRK-B", "BRK.B"}
    assert intel_hub._dot_dash("CEMARGOS.BO") == {"CEMARGOS.BO", "CEMARGOS-BO"}


# --------------------------------------------------------------------------- #
# 5 — fail-open: no snapshot directory at all
# --------------------------------------------------------------------------- #

def test_missing_snapshots_dir_fails_open(root):
    assert not (root / "data" / "symbol_directory").exists()
    hub = _build(bundle=_bundle("AAL", "ANANTRAJ"), policy=None)

    us = hub["universe_scope"]
    assert us["applied"] is False
    assert us["n_excluded"] == 0
    assert us["n_in"] == 2
    assert us.get("reason"), "fail-open must name a reason, never degrade silently"
    assert _dossier_tickers(hub) == {"AAL", "ANANTRAJ"}, "fail-open must pass the universe through"


# --------------------------------------------------------------------------- #
# 6 — fail-open: a roster below the sanity floor is a broken snapshot, not a universe
# --------------------------------------------------------------------------- #

def test_roster_below_sanity_floor_fails_open(root):
    _write_roster(root, named=["AAL"], n_filler=100)
    hub = _build(bundle=_bundle("AAL", "ANANTRAJ"), policy=None)

    us = hub["universe_scope"]
    assert us["applied"] is False
    assert us["n_excluded"] == 0
    assert "floor" in (us.get("reason") or "").lower(), us.get("reason")
    assert str(intel_hub._ROSTER_SANITY_FLOOR) in (us.get("reason") or "")
    assert _dossier_tickers(hub) == {"AAL", "ANANTRAJ"}


# --------------------------------------------------------------------------- #
# 7 — a test issue is not a listing
# --------------------------------------------------------------------------- #

def test_test_issue_row_does_not_confer_membership(root):
    _write_roster(root, named=["AAL", "ZXIET"], test_issues=["ZXIET"])
    hub = _build(bundle=_bundle("AAL", "ZXIET"), policy=None)

    us = hub["universe_scope"]
    assert us["applied"] is True
    assert us["n_excluded"] == 1, us
    assert "ZXIET" in us["excluded_sample"]
    assert "ZXIET" not in _dossier_tickers(hub)


# --------------------------------------------------------------------------- #
# 8 — off-desk discovery INJECTION is scoped (and counted), before the cap
# --------------------------------------------------------------------------- #

def test_off_desk_injection_is_scoped_and_counted(root):
    _write_roster(root, named=["AAL", "GOODX"])
    discovery = {"by_ticker": {},
                 "off_desk": [_cand("GOODX"), _cand("ANANTRAJ", 0.8)],
                 "candidates": [], "n": 0, "n_off_desk": 2}
    hub = _build(bundle=_bundle("AAL"), policy=None, discovery=discovery)

    us = hub["universe_scope"]
    assert us["n_excluded_off_desk"] == 1, us
    assert "ANANTRAJ" not in _dossier_tickers(hub), "off-scope off-desk name was injected"
    assert "GOODX" in _dossier_tickers(hub), "in-scope off-desk injection must still work"


# --------------------------------------------------------------------------- #
# 9 — the discovery DISPLAY list is scoped (and counted)
# --------------------------------------------------------------------------- #

def test_discovery_display_list_is_scoped_and_counted(root):
    _write_roster(root, named=["AAL", "GOODX"])
    discovery = {"by_ticker": {}, "off_desk": [],
                 "candidates": [_cand("GOODX"), _cand("ANANTRAJ", 0.8)],
                 "n": 2, "n_off_desk": 0}
    hub = _build(bundle=_bundle("AAL"), policy=None, discovery=discovery)

    us = hub["universe_scope"]
    assert us["n_excluded_discovery"] == 1, us
    shown = {row.get("ticker") for row in hub["discovery"]}
    assert "ANANTRAJ" not in shown, "off-scope name still rendered in the Discovery section"
    assert "GOODX" in shown
    # the feed's own total is untouched — it reports what the feed found, not what we show
    assert hub["n_discovery"] == 2


# --------------------------------------------------------------------------- #
# 10a — fail-open last rung: the gate must never EMPTY the universe.
# A verdict of "nothing is a member" is a broken roster/universe pairing (a changed
# keying convention, the wrong store, a caller that isn't the nightly bundle), and an
# empty hub is strictly worse than the pre-gate behaviour.
# --------------------------------------------------------------------------- #

def test_gate_never_empties_the_universe(root):
    _write_roster(root, named=[])                # a healthy roster that shares nothing
    hub = _build(bundle=_bundle("ANANTRAJ", "BULTEN"), policy=None)

    us = hub["universe_scope"]
    assert us["applied"] is False
    assert us["n_excluded"] == 0
    assert us["n_in"] == 2
    assert "all 2 names" in (us.get("reason") or ""), us.get("reason")
    assert _dossier_tickers(hub) == {"ANANTRAJ", "BULTEN"}


# --------------------------------------------------------------------------- #
# 10 — the China parquet fallback confers NO membership (US-only spine)
# --------------------------------------------------------------------------- #

def test_china_parquet_does_not_confer_membership(root):
    _write_roster(root, named=["AAL"])
    _write_prices(root, "CNONLY", sub="china_stocks")      # priceable by ai_desk, NOT by us
    assert not (root / "data" / "yahoo" / "CNONLY.parquet").exists()

    hub = _build(bundle=_bundle("AAL", "CNONLY"), policy=None)
    us = hub["universe_scope"]
    assert us["applied"] is True
    assert us["n_excluded"] == 1, us
    assert "CNONLY" in us["excluded_sample"]
    assert "CNONLY" not in _dossier_tickers(hub)
    assert intel_hub._spine_covered("CNONLY", root) is False, (
        "a China-only parquet must never confer US hub membership"
    )
