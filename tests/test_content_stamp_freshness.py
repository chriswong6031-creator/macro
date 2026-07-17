"""Content-stamp freshness gates — the #2690 frozen-cache class, repo-wide sweep.

Every gate here once judged the freshness of a GIT-COMMITTED artifact by file
mtime. On CI runners a checkout rewrites files with mtime = checkout time, so a
committed months-old cache perpetually looks minutes old and the refresh
short-circuits forever (data/finra/short_interest.parquet, data/sec_insider/
insider.parquet, data/edgar/eps_quarterly.parquet and data/baskets_china_ths/
concept_map.json all froze at their June-2026 first fills this way). The fix
pattern (from scripts/build_polygon_universe.py, #2690): judge freshness from an
embedded content stamp (asof column / built field / stamped blob), treat
stamp-less or unreadable artifacts as stale, keep the no-regress fetch-failure
fallbacks.

Each gate gets an mtime-blindness regression lock: an artifact with a STALE
content stamp but a FRESH mtime must read as stale.

Run:
    python -m pytest tests/test_content_stamp_freshness.py -v
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

from lib import config


def _freshen_mtime(p: Path) -> None:
    """Set mtime to NOW — simulates the CI checkout rewrite."""
    os.utime(p, (time.time(), time.time()))


def _age_mtime(p: Path, days: float) -> None:
    """Backdate mtime — the pre-fix gates keyed off this; ours must not."""
    old = time.time() - days * 86400
    os.utime(p, (old, old))


# ═══════════════════════════════════════════════════════════════════════════════
# collectors/finra.py — asof column gate
# ═══════════════════════════════════════════════════════════════════════════════

from collectors import finra


def _si_frame(asof: str | None) -> pd.DataFrame:
    df = pd.DataFrame({"short_shares": [100.0], "days_to_cover": [2.0],
                       "settlement_date": ["2026-05-29"]},
                      index=pd.Index(["AAPL"], name="ticker"))
    if asof is not None:
        df["asof"] = asof
    return df


class TestFinraGate:
    def test_fresh_asof_short_circuits_despite_old_mtime(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        cache = tmp_path / "finra" / "short_interest.parquet"
        cache.parent.mkdir(parents=True)
        _si_frame(date.today().isoformat()).to_parquet(cache)
        _age_mtime(cache, 30)                     # ancient mtime, fresh stamp
        monkeypatch.setattr(finra, "_latest_settlement",
                            lambda: (_ for _ in ()).throw(AssertionError("fetched")))
        out = finra.fetch_short_interest()
        assert out is not None and "AAPL" in out.index

    def test_stale_asof_fetches_despite_fresh_mtime(self, tmp_path, monkeypatch):
        """The mtime-blindness lock: fresh mtime must NOT rescue a stale stamp."""
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        cache = tmp_path / "finra" / "short_interest.parquet"
        cache.parent.mkdir(parents=True)
        _si_frame((date.today() - timedelta(days=30)).isoformat()).to_parquet(cache)
        _freshen_mtime(cache)
        calls = []
        monkeypatch.setattr(finra, "_latest_settlement",
                            lambda: calls.append(1) or None)
        out = finra.fetch_short_interest()        # fetch attempted; fails → keeps cache
        assert calls, "stale stamp must trigger a fetch attempt"
        assert out is not None and "AAPL" in out.index   # no-regress fallback intact

    def test_legacy_stampless_cache_reads_stale(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        cache = tmp_path / "finra" / "short_interest.parquet"
        cache.parent.mkdir(parents=True)
        _si_frame(None).to_parquet(cache)          # pre-fix schema: no asof column
        _freshen_mtime(cache)
        calls = []
        monkeypatch.setattr(finra, "_latest_settlement",
                            lambda: calls.append(1) or None)
        finra.fetch_short_interest()
        assert calls, "stamp-less cache must read as stale"

    def test_write_stamps_asof_and_history_stays_clean(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        (tmp_path / "finra").mkdir(parents=True)
        snap = _si_frame(None)
        monkeypatch.setattr(finra, "_latest_settlement", lambda: "2026-07-01")
        monkeypatch.setattr(finra, "_snapshot", lambda s: snap.copy())
        monkeypatch.setattr(finra, "_universe_tickers", lambda: set())
        out = finra.fetch_short_interest(force=True)
        assert out["asof"].iloc[0] == date.today().isoformat()
        hist = pd.read_parquet(tmp_path / "finra" / "short_interest_history.parquet")
        assert "asof" not in hist.columns          # history schema unchanged


# ═══════════════════════════════════════════════════════════════════════════════
# collectors/sec_insider.py — _meta.json built-stamp gate
# ═══════════════════════════════════════════════════════════════════════════════

from collectors import sec_insider


class TestSecInsiderGate:
    def _seed(self, tmp_path, built: str | None):
        d = tmp_path / "sec_insider"
        d.mkdir(parents=True)
        pd.DataFrame({"buy_usd": [1.0]}, index=pd.Index(["AAPL"], name="ticker")
                     ).to_parquet(d / "insider.parquet")
        if built is not None:
            (d / "_meta.json").write_text(json.dumps({"built": built}))
        _freshen_mtime(d / "insider.parquet")      # checkout-fresh mtime everywhere

    def test_fresh_built_short_circuits(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        self._seed(tmp_path, datetime.now(timezone.utc).isoformat())
        monkeypatch.setattr(sec_insider, "_download_quarter",
                            lambda: (_ for _ in ()).throw(AssertionError("fetched")))
        out = sec_insider.fetch_insider()
        assert out is not None

    def test_stale_built_fetches_despite_fresh_mtime(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        self._seed(tmp_path,
                   (datetime.now(timezone.utc) - timedelta(days=32)).isoformat())
        calls = []
        monkeypatch.setattr(sec_insider, "_download_quarter",
                            lambda: calls.append(1) or None)
        out = sec_insider.fetch_insider()
        assert calls, "stale built stamp must trigger a fetch attempt"
        assert out is not None                     # no-regress fallback intact

    def test_missing_meta_reads_stale(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        self._seed(tmp_path, None)
        calls = []
        monkeypatch.setattr(sec_insider, "_download_quarter",
                            lambda: calls.append(1) or None)
        sec_insider.fetch_insider()
        assert calls


# ═══════════════════════════════════════════════════════════════════════════════
# collectors/edgar_eps.py — sidecar built-stamp gate (panel + filing dates)
# ═══════════════════════════════════════════════════════════════════════════════

from collectors import edgar_eps as ee


class TestEdgarEpsGate:
    def test_fresh_meta_short_circuits_panel(self, tmp_path, monkeypatch):
        p = tmp_path / "eps_quarterly.parquet"
        pd.DataFrame({"ticker": ["AAPL"], "period_end": [pd.Timestamp("2026-03-31")],
                      "eps_q": [1.5], "asof_date": [pd.Timestamp("2026-05-30")]}
                     ).to_parquet(p)
        ee._write_built_meta(p, 1)
        _age_mtime(p, 30)                          # stamp decides, not mtime
        monkeypatch.setattr(ee, "eps_panel_path", lambda: p)
        monkeypatch.setattr(ee, "_universe_tickers",
                            lambda: (_ for _ in ()).throw(AssertionError("fetched")))
        out = ee.build_eps_panel()
        assert len(out) == 1

    def test_stampless_panel_reads_stale_but_no_regress(self, tmp_path, monkeypatch):
        p = tmp_path / "eps_quarterly.parquet"
        pd.DataFrame({"ticker": ["AAPL"], "period_end": [pd.Timestamp("2026-03-31")],
                      "eps_q": [1.5], "asof_date": [pd.Timestamp("2026-05-30")]}
                     ).to_parquet(p)
        _freshen_mtime(p)                          # fresh mtime, no meta → stale
        monkeypatch.setattr(ee, "eps_panel_path", lambda: p)
        calls = []
        monkeypatch.setattr(ee, "_universe_tickers", lambda: calls.append(1) or [])
        out = ee.build_eps_panel()                 # fetch attempted; no universe →
        assert calls, "stamp-less panel must attempt a refetch"
        assert list(out["ticker"]) == ["AAPL"]     # …prior panel retained (no raise)
        assert ee._built_age_days(p) is None       # meta NOT bumped → retries next build

    def test_cold_start_without_universe_still_raises(self, tmp_path, monkeypatch):
        p = tmp_path / "eps_quarterly.parquet"     # absent — nothing to fall back to
        monkeypatch.setattr(ee, "eps_panel_path", lambda: p)
        monkeypatch.setattr(ee, "_universe_tickers", lambda: [])
        with pytest.raises(RuntimeError):
            ee.build_eps_panel()

    def test_built_age_days_roundtrip(self, tmp_path):
        p = tmp_path / "x.parquet"
        assert ee._built_age_days(p) is None       # no meta at all
        ee._write_built_meta(p, 0)
        age = ee._built_age_days(p)
        assert age is not None and age < 0.01


# ═══════════════════════════════════════════════════════════════════════════════
# collectors/china_ths_concepts.py — stamped-blob gate with legacy fallback
# ═══════════════════════════════════════════════════════════════════════════════

from collectors import china_ths_concepts as ths


class _AkStub:
    """akshare stub whose name endpoint always fails (forces the fallback path)."""
    @staticmethod
    def stock_board_concept_name_ths():
        raise RuntimeError("network down")


class TestThsConceptMapGate:
    def _install_stub(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "akshare", _AkStub())

    def test_fresh_stamped_map_short_circuits(self, tmp_path, monkeypatch):
        cache = tmp_path / "concept_map.json"
        cache.write_text(json.dumps(
            {"asof": date.today().isoformat(), "map": {"半导体": "885921"}}))
        _age_mtime(cache, 30)
        monkeypatch.setattr(ths, "_MAP_CACHE", cache)
        self._install_stub(monkeypatch)            # would fail if fetch attempted
        assert ths.concept_code_map() == {"半导体": "885921"}

    def test_stale_stamp_refetch_fails_falls_back(self, tmp_path, monkeypatch):
        cache = tmp_path / "concept_map.json"
        cache.write_text(json.dumps(
            {"asof": (date.today() - timedelta(days=30)).isoformat(),
             "map": {"半导体": "885921"}}))
        _freshen_mtime(cache)                      # mtime-blindness lock
        monkeypatch.setattr(ths, "_MAP_CACHE", cache)
        self._install_stub(monkeypatch)
        # fetch fails → better-stale-than-nothing fallback returns the old map
        assert ths.concept_code_map() == {"半导体": "885921"}

    def test_legacy_flat_map_reads_stale_but_usable_as_fallback(self, tmp_path, monkeypatch):
        cache = tmp_path / "concept_map.json"
        cache.write_text(json.dumps({"半导体": "885921"}))   # pre-fix flat format
        _freshen_mtime(cache)
        monkeypatch.setattr(ths, "_MAP_CACHE", cache)
        self._install_stub(monkeypatch)
        assert ths.concept_code_map() == {"半导体": "885921"}
        m, age = ths._read_map_cache()
        assert age is None, "legacy blob must never read as fresh"

    def test_successful_fetch_writes_stamped_format(self, tmp_path, monkeypatch):
        cache = tmp_path / "concept_map.json"
        monkeypatch.setattr(ths, "_MAP_CACHE", cache)
        monkeypatch.setattr(ths, "_DATA", tmp_path)

        class _AkOk:
            @staticmethod
            def stock_board_concept_name_ths():
                return pd.DataFrame({"name": ["半导体"], "code": ["885921"]})

        monkeypatch.setitem(sys.modules, "akshare", _AkOk())
        assert ths.concept_code_map(force=True) == {"半导体": "885921"}
        blob = json.loads(cache.read_text())
        assert blob["asof"] == date.today().isoformat()
        assert blob["map"] == {"半导体": "885921"}


# ═══════════════════════════════════════════════════════════════════════════════
# engine/macro_surprise.py — stamped cache blob
# ═══════════════════════════════════════════════════════════════════════════════

from engine import macro_surprise as ms


class TestMacroSurpriseCache:
    def test_roundtrip_fresh(self, tmp_path):
        p = tmp_path / "CPIAUCSL.json"
        recs = [{"date": "2026-06-01", "value": 321.5}]
        ms._cache_write(p, recs)
        _age_mtime(p, 5)                           # mtime must not matter
        assert ms._cache_fresh(p) is True
        assert ms._cache_read(p) == recs

    def test_stale_stamp_despite_fresh_mtime(self, tmp_path):
        p = tmp_path / "CPIAUCSL.json"
        p.write_text(json.dumps(
            {"asof": (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat(),
             "records": []}))
        _freshen_mtime(p)
        assert ms._cache_fresh(p) is False

    def test_legacy_bare_list_reads_stale_but_readable(self, tmp_path):
        p = tmp_path / "ICSA.json"
        p.write_text(json.dumps([{"date": "2026-07-09", "value": 230000}]))
        _freshen_mtime(p)
        assert ms._cache_fresh(p) is False         # stamp-less ⇒ one refetch
        assert ms._cache_read(p) == [{"date": "2026-07-09", "value": 230000}]


# ═══════════════════════════════════════════════════════════════════════════════
# engine/china_sector_central.py — leg ages from content dates
# ═══════════════════════════════════════════════════════════════════════════════

from engine import china_sector_central as cc


class TestLegStalenessContentAges:
    def test_ages_come_from_content_not_mtime(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        (tmp_path / "china_credit").mkdir(parents=True)
        (tmp_path / "china_margin").mkdir(parents=True)
        (tmp_path / "china").mkdir(parents=True)

        old = pd.Timestamp(date.today() - timedelta(days=90))
        fresh = pd.Timestamp(date.today() - timedelta(days=2))
        pd.DataFrame({"tsf_total": [1.0], "availability_date": [old]}
                     ).to_parquet(tmp_path / "china_credit" / "tsf.parquet")
        pd.DataFrame({"margin_total": [1.0]},
                     index=pd.DatetimeIndex([fresh], name="DIM_DATE")
                     ).to_parquet(tmp_path / "china_margin" / "balance.parquet")
        pd.DataFrame({"close": [1.0]},
                     index=pd.DatetimeIndex([fresh], name="Date")
                     ).to_parquet(tmp_path / "china" / "510300.SS.parquet")
        for f in tmp_path.rglob("*.parquet"):
            _freshen_mtime(f)                      # checkout-fresh mtimes everywhere

        ages = cc._regime_leg_staleness(None)
        assert ages["credit"] == 90                # content age, not mtime age
        assert ages["margin"] == 2
        assert ages["vol"] == 2
        assert ages["credit"] > cc._LEG_STALE_DAYS["credit"]   # watchdog can now fire

    def test_missing_file_and_unreadable_stamp_are_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        (tmp_path / "china_credit").mkdir(parents=True)
        # tsf present but without availability_date → unknown (None), logged
        pd.DataFrame({"tsf_total": [1.0]}).to_parquet(
            tmp_path / "china_credit" / "tsf.parquet")
        ages = cc._regime_leg_staleness(None)
        assert ages["credit"] is None
        assert ages["margin"] is None              # file absent
        assert ages["vol"] is None


# ═══════════════════════════════════════════════════════════════════════════════
# scripts/collect_zori.py + scripts/collect_nyfed_cmdi.py — sidecar fetch stamps
# ═══════════════════════════════════════════════════════════════════════════════

from scripts import collect_nyfed_cmdi as cmdi
from scripts import collect_zori as zori


class TestSidecarStamps:
    def test_payems_is_fresh_reads_stamp_not_mtime(self, tmp_path, monkeypatch):
        from scripts import collect_payems_vintages as pv
        out = tmp_path / "payems_all_vintages.parquet"
        pd.DataFrame({"period": [pd.Timestamp("2026-06-01")], "value": [1.0]}
                     ).to_parquet(out)
        stamp = tmp_path / "payems_fetched.json"
        monkeypatch.setattr(pv, "_STAMP_PATH", stamp)
        _freshen_mtime(out)
        assert pv._is_fresh(out) is False                       # no stamp ⇒ stale
        stamp.write_text(json.dumps({"asof": date.today().isoformat()}))
        assert pv._is_fresh(out) is True
        stamp.write_text(json.dumps(
            {"asof": (date.today() - timedelta(days=7)).isoformat()}))
        _freshen_mtime(out)                                     # mtime-blindness lock
        assert pv._is_fresh(out) is False                       # 7d > _FRESH_DAYS=6

    def test_zori_stamp_ages(self, tmp_path):
        stamp = tmp_path / "_fetched.json"
        assert zori._fetched_age_days(stamp) is None            # missing ⇒ stale
        stamp.write_text(json.dumps({"asof": date.today().isoformat()}))
        assert zori._fetched_age_days(stamp) == 0
        stamp.write_text(json.dumps(
            {"asof": (date.today() - timedelta(days=3)).isoformat()}))
        _freshen_mtime(stamp)                                   # mtime-blindness lock
        assert zori._fetched_age_days(stamp) == 3
        stamp.write_text("not json")
        assert zori._fetched_age_days(stamp) is None

    def test_cmdi_is_fresh_reads_stamp_not_mtime(self, tmp_path, monkeypatch):
        weekly = tmp_path / "cmdi_weekly.parquet"
        pd.DataFrame({"market_cmdi": [0.1]}).to_parquet(weekly)
        stamp = tmp_path / "_fetched.json"
        monkeypatch.setattr(cmdi, "CMDI_STAMP_PATH", stamp)
        _freshen_mtime(weekly)
        assert cmdi._is_fresh(weekly) is False                  # no stamp ⇒ stale
        stamp.write_text(json.dumps({"asof": date.today().isoformat()}))
        assert cmdi._is_fresh(weekly) is True
        stamp.write_text(json.dumps(
            {"asof": (date.today() - timedelta(days=1)).isoformat()}))
        assert cmdi._is_fresh(weekly) is False                  # yesterday ≠ today
        assert cmdi._is_fresh(tmp_path / "absent.parquet") is False
