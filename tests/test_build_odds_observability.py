"""Observability contract for scripts/build_odds.py — the fail-soft odds lane.

build_odds returns 0 on EVERY path (it must never break the nightly), so its
degraded paths were log-only and production degradation was invisible: on
2026-07-21 AMAT silently left site/oddsdata/catalog.json (118/119) because its
yfinance max-fetch came back empty during a cold-store backfill — the drop
happened at the ``exists()`` filter in ensure_store with no log line at all.

The fix is GitHub Actions annotations, and the load-bearing mechanic is COLUMN
ZERO: the runner parses ``::warning`` only at the start of a line, and this
module's logging format prefixes every record — a ``log.warning("::warning
...")`` never annotates (PRs #3487/#3515 shipped exactly that dead form).  Every
assertion below therefore checks ``line.startswith("::warning title=odds::")``,
not a substring match.

Pins (network-free — the ``_download`` seam and ``yfinance`` are stubbed, and
lib.config.ROOT is redirected to tmp_path so nothing touches the real tree):
1. the coverage census counts all THREE drop layers — store (no parquet),
   depth (rows < min_rows) and matrix error — and lands in catalog.json with a
   built_utc heartbeat; a drop annotates at column 0 and names every ticker.
2. a clean run prints a grep-able ``odds census:`` heartbeat and NO census /
   staleness / fetch warning.
3. an asof more than 2 trading days old trips the store-not-advancing tripwire.
4. the store-empty bail annotates and still returns 0.
5. the outer fail-soft except annotates (with the exception type) and returns 0.
6. ensure_meta RETRIES the degraded empty-sector cache form instead of freezing
   it forever, and leaves healthy entries alone (no refetch).
7. a failed retry preserves the prior good entry instead of clobbering it.
8. _gha emits exactly one column-0 line with whitespace collapsed.

Run: .venv/bin/python -m pytest tests/test_build_odds_observability.py -q
"""
from __future__ import annotations

import json
import sys
import types
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import build_odds as bo  # noqa: E402

ANN = "::warning title=odds::"


# ---------------------------------------------------------------------------
# plumbing: tmp ROOT, stubbed download + yfinance, faked odds_lab
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Deny-all yfinance stub for every test in this module.

    ensure_meta imports yfinance lazily inside main(); without this the suite
    would make real .info calls.  Pins 6/7 override it with their own stub.
    """
    mod = types.ModuleType("yfinance")

    class _DeadTicker:
        def __init__(self, t):
            self._t = t

        @property
        def info(self):
            raise RuntimeError("network disabled in tests")

    mod.Ticker = _DeadTicker
    mod.download = lambda *a, **kw: pytest.fail("real yfinance.download called")
    monkeypatch.setitem(sys.modules, "yfinance", mod)


@pytest.fixture()
def root(tmp_path, monkeypatch):
    """Redirect lib.config.ROOT so every read/write lands under tmp_path.

    House tripwire (tests/conftest.py MM_DATA_GUARD): a test must never write
    the repo's real data/ or site/ tree.  There is no templates/odds.html.j2
    under tmp_path either, so _render's template-absent annotation fires on
    every main() run — expected, and asserted around rather than against.
    """
    monkeypatch.setattr(bo.config, "ROOT", tmp_path)
    (tmp_path / "data" / "odds_ohlcv").mkdir(parents=True)
    return tmp_path


def _store(root: Path) -> Path:
    return root / "data" / "odds_ohlcv"


def _seed(root: Path, ticker: str, n: int = 400, end: str | pd.Timestamp = "2026-06-30") -> Path:
    """Write a lowercase-OHLCV parquet into the store; returns the path."""
    idx = pd.bdate_range(end=end, periods=n)
    close = np.linspace(100.0, 150.0, n)
    df = pd.DataFrame({"open": close, "high": close + 1.0, "low": close - 1.0,
                       "close": close, "volume": 1e6}, index=idx)
    df.index.name = "Date"
    p = _store(root) / f"{ticker}.parquet"
    df.to_parquet(p)
    return p


def _cfg(universe: list[str], **over) -> dict:
    cfg = {"enabled": True, "universe": list(universe), "shallow_rows": 300,
           "min_rows": 60, "batch_size": 40, "batch_pause_s": 0.0,
           "meta_pause_s": 0.0, "stale_trading_days": 0}
    cfg.update(over)
    return cfg


def _patch(monkeypatch, cfg: dict, asof: str, frames: dict | None = None) -> None:
    """Pin _cfg + the download seam + the odds_lab compute layer."""
    monkeypatch.setattr(bo, "_cfg", lambda: cfg)
    monkeypatch.setattr(bo, "_download",
                        lambda tickers, period, bs, pause: dict(frames or {}))
    monkeypatch.setattr(bo.odds_lab, "build_matrix",
                        lambda t, df, market=None: {"asof": asof, "ticker": t})
    monkeypatch.setattr(bo.odds_lab, "run_factor_match",
                        lambda matrices, **kw: {"rows": [], "templates": []})


def _out(capsys) -> list[str]:
    return capsys.readouterr().out.splitlines()


def _anns(lines: list[str]) -> list[str]:
    """Only column-0 annotations count — a prefixed line never reaches GH."""
    return [ln for ln in lines if ln.startswith(ANN)]


def _catalog(root: Path) -> dict:
    return json.loads((root / "site" / "oddsdata" / "catalog.json").read_text())


def _last_bd() -> pd.Timestamp:
    """The last business day at or before today (UTC) — a non-stale asof."""
    return pd.bdate_range(end=pd.Timestamp(datetime.now(timezone.utc).date()), periods=5)[-1]


# ---------------------------------------------------------------------------
# 1. the coverage census counts all three drop layers
# ---------------------------------------------------------------------------

def test_census_counts_store_depth_and_publishes_reasons(root, monkeypatch, capsys):
    """AAA builds; BBB is a shallow stub (depth drop); CCC never fetched (the
    invisible store-layer drop — the AMAT class)."""
    _seed(root, "AAA", n=400)
    _seed(root, "BBB", n=5)
    # CCC: deliberately absent from the store
    _patch(monkeypatch, _cfg(["AAA", "BBB", "CCC"], stale_trading_days=9999),
           asof="2026-07-24")

    assert bo.main() == 0

    cov = _catalog(root)["coverage"]
    assert cov["declared"] == 3
    assert cov["built"] == 1
    assert "built_utc" in cov
    reasons = {d["t"]: d["reason"] for d in cov["dropped"]}
    assert set(reasons) == {"BBB", "CCC"}
    assert "rows < min_rows" in reasons["BBB"]
    assert reasons["BBB"].startswith("5 rows")
    assert "no parquet in store" in reasons["CCC"]
    # schema key is untouched — coverage is purely additive
    assert _catalog(root)["schema"] == "odds_catalog.v1"

    anns = _anns(_out(capsys))
    census = [a for a in anns if a.startswith(ANN + "coverage")]
    assert len(census) == 1, anns
    assert "coverage 1/3 built, 2 dropped" in census[0]
    assert "BBB" in census[0] and "CCC" in census[0]
    # BBB + CCC both needed a fetch and _download returned nothing
    assert any("yfinance returned no data for all 2 fetch-needing tickers" in a
               for a in anns), anns


def test_matrix_build_error_is_recorded_as_a_drop(root, monkeypatch, capsys):
    """The third drop layer: a per-ticker matrix raise is fail-soft but must
    still show up in the census with its reason."""
    _seed(root, "AAA", n=400)
    _seed(root, "BBB", n=400)
    cfg = _cfg(["AAA", "BBB"], stale_trading_days=9999)
    _patch(monkeypatch, cfg, asof="2026-07-24")

    def _boom(t, df, market=None):
        if t == "BBB":
            raise ValueError("bad frame")
        return {"asof": "2026-07-24", "ticker": t}

    monkeypatch.setattr(bo.odds_lab, "build_matrix", _boom)
    assert bo.main() == 0

    cov = _catalog(root)["coverage"]
    assert cov["declared"] == 2 and cov["built"] == 1
    assert cov["dropped"] == [{"t": "BBB", "reason": "matrix build error: bad frame"}]
    assert any(a.startswith(ANN + "coverage") and "BBB" in a for a in _anns(_out(capsys)))


# ---------------------------------------------------------------------------
# 2. a clean run is a grep-able heartbeat, not an annotation
# ---------------------------------------------------------------------------

def test_clean_run_prints_heartbeat_and_no_degradation_warning(root, monkeypatch, capsys):
    last = _last_bd()
    _seed(root, "AAA", n=400, end=last)
    # stale_trading_days high -> nothing needs fetching -> attempted == 0
    _patch(monkeypatch, _cfg(["AAA"], stale_trading_days=9999),
           asof=str(last.date()))

    assert bo.main() == 0

    lines = _out(capsys)
    assert any(ln.startswith(f"odds census: coverage 1/1 built, 0 dropped, asof {last.date()}")
               for ln in lines), lines
    anns = _anns(lines)
    assert not [a for a in anns if a.startswith(ANN + "coverage")], anns
    assert not [a for a in anns if a.startswith(ANN + "asof")], anns
    assert not [a for a in anns if "yfinance returned no data" in a], anns
    # the template-absent annotation IS expected under a tmp ROOT
    assert any("odds.html.j2 absent" in a for a in anns), anns
    assert _catalog(root)["coverage"]["dropped"] == []


# ---------------------------------------------------------------------------
# 3. a frozen store trips the staleness tripwire
# ---------------------------------------------------------------------------

def test_stale_asof_trips_the_freeze_tripwire(root, monkeypatch, capsys):
    """_stale_days measures against the real utcnow, so a 2026-06-01 asof is
    always far past the 2-trading-day tolerance on this repo's timeline."""
    _seed(root, "AAA", n=400, end="2026-06-01")
    _patch(monkeypatch, _cfg(["AAA"], stale_trading_days=9999), asof="2026-06-01")

    assert bo.main() == 0

    stale = [a for a in _anns(_out(capsys)) if a.startswith(ANN + "asof 2026-06-01")]
    assert len(stale) == 1, stale
    assert "trading days old" in stale[0]
    assert "not advancing" in stale[0]


# ---------------------------------------------------------------------------
# 4/5. the two bail-outs annotate at column 0 and still return 0
# ---------------------------------------------------------------------------

def test_store_empty_bail_annotates_and_returns_zero(root, monkeypatch, capsys):
    _patch(monkeypatch, _cfg(["AAA"]), asof="2026-07-24")   # no parquets seeded

    assert bo.main() == 0

    anns = _anns(_out(capsys))
    empty = [a for a in anns if a.startswith(ANN + "store empty (1 declared)")]
    assert len(empty) == 1, anns
    assert "NOT rebuilt this run" in empty[0]
    assert not (root / "site" / "oddsdata" / "catalog.json").exists()


def test_no_matrices_bail_annotates_and_returns_zero(root, monkeypatch, capsys):
    """Every stored ticker is too shallow: the store is non-empty but nothing
    publishable comes out of it."""
    _seed(root, "AAA", n=5)
    _patch(monkeypatch, _cfg(["AAA"], shallow_rows=1, stale_trading_days=9999),
           asof="2026-07-24")

    assert bo.main() == 0

    anns = _anns(_out(capsys))
    assert [a for a in anns if a.startswith(ANN + "0/1 matrices built")], anns
    assert not (root / "site" / "oddsdata" / "catalog.json").exists()


def test_outer_exception_annotates_and_returns_zero(root, monkeypatch, capsys):
    def _boom():
        raise RuntimeError("boom")

    monkeypatch.setattr(bo, "_cfg", _boom)

    assert bo.main() == 0

    anns = _anns(_out(capsys))
    failed = [a for a in anns if a.startswith(ANN + "odds desk build failed")]
    assert len(failed) == 1, anns
    assert "RuntimeError" in failed[0] and "boom" in failed[0]
    assert "fail-soft rc=0" in failed[0]


# ---------------------------------------------------------------------------
# 6/7. the degraded meta cache retries instead of freezing
# ---------------------------------------------------------------------------

def _yf(monkeypatch, infos: dict) -> list[str]:
    """Install a yfinance stub; returns the list of tickers it was asked for."""
    asked: list[str] = []
    mod = types.ModuleType("yfinance")

    class _Ticker:
        def __init__(self, t):
            asked.append(t)
            self._t = t

        @property
        def info(self):
            v = infos[self._t]
            if isinstance(v, Exception):
                raise v
            return v

    mod.Ticker = _Ticker
    monkeypatch.setitem(sys.modules, "yfinance", mod)
    return asked


DEGRADED_META = {"AAA": {"name": "Real Name", "sector": ""},   # the degraded form
                 "BBB": {"name": "Bee", "sector": "Tech"}}     # healthy


def test_empty_sector_entry_is_retried_and_heals(tmp_path, monkeypatch):
    (tmp_path / "_meta.json").write_text(json.dumps(DEGRADED_META))
    asked = _yf(monkeypatch, {"AAA": {"sector": "Technology", "shortName": "Ayy"}})

    meta = bo.ensure_meta({"meta_pause_s": 0}, tmp_path, ["AAA", "BBB"])

    assert asked == ["AAA"], "a healthy entry must not be refetched"
    assert meta["AAA"]["sector"] == "Technology"
    assert meta["AAA"]["name"] == "Ayy"
    assert meta["BBB"] == {"name": "Bee", "sector": "Tech"}
    assert json.loads((tmp_path / "_meta.json").read_text())["AAA"]["sector"] == "Technology"


def test_failed_retry_preserves_the_prior_entry(tmp_path, monkeypatch):
    (tmp_path / "_meta.json").write_text(json.dumps(DEGRADED_META))
    asked = _yf(monkeypatch, {"AAA": RuntimeError("info 404")})

    meta = bo.ensure_meta({"meta_pause_s": 0}, tmp_path, ["AAA", "BBB"])

    assert asked == ["AAA"]
    assert meta["AAA"]["name"] == "Real Name", "a failed retry must not clobber a good name"
    assert meta["AAA"]["sector"] == "", "still degraded — it retries again next run"
    assert meta["BBB"] == {"name": "Bee", "sector": "Tech"}


# ---------------------------------------------------------------------------
# 8. the annotation primitive itself
# ---------------------------------------------------------------------------

def test_gha_emits_one_column_zero_line_with_collapsed_whitespace(capsys):
    bo._gha("warning", "a\nb\tc")
    lines = _out(capsys)
    assert len(lines) == 1
    assert lines[0].startswith(ANN)
    assert lines[0] == ANN + "a b c"


def test_gha_truncates_and_never_wraps(capsys):
    bo._gha("warning", "x " * 800)
    lines = _out(capsys)
    assert len(lines) == 1, "an annotation must stay on one line"
    assert len(lines[0]) == len(ANN) + 600


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
