"""scripts/audit_reused_tickers — reused-ticker / zombie-print tripwire.

Pins the ECHO-class detector (2026-08-06 identity swap): a dead-registry name whose
store file keeps advancing past the death date with a mismatched overlap is a ZOMBIE
(another company's tape under a dead key) and must ::warning unless operator-acked;
a same-instrument overlap is registry-side contamination (quiet); a post-death start
is a clean-break rebirth (quiet); a fresh-printing name absent from the NASDAQ
symbol directory is an in-flight delisting (summary ::warning, EA class).

Annotations are asserted via capsys with line.startswith("::") — the GitHub
annotation law (annotations must START the line, emitted by bare print, never a
logger; tests that assert via caplog are vacuous against that defect class).
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from scripts import audit_reused_tickers as art

NOW = datetime(2026, 8, 5, 12, 0, tzinfo=timezone.utc)  # today_et = 2026-08-05
CFG = {"stocks_stale_calendar_days": 7, "reused_grace_days": 30}


def _write_store(data_dir: Path, store: str, ticker: str, closes: pd.Series) -> None:
    p = data_dir / store
    p.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame({"close": closes.values},
                      index=pd.DatetimeIndex(closes.index, name="Date"))
    df.to_parquet(p / f"{ticker}.parquet")


def _write_registry(data_dir: Path, rows: dict[str, pd.Series]) -> None:
    p = data_dir / "edgar"
    p.mkdir(parents=True, exist_ok=True)
    frames = [pd.DataFrame({"ticker": t, "date": s.index, "close": s.values})
              for t, s in rows.items()]
    df = (pd.concat(frames, ignore_index=True) if frames
          else pd.DataFrame({"ticker": pd.Series(dtype=str),
                             "date": pd.Series(dtype="datetime64[ns]"),
                             "close": pd.Series(dtype=float)}))
    df.to_parquet(p / "dead_name_prices.parquet")


def _alternating(dates: pd.DatetimeIndex, start: float, up: float, down: float) -> pd.Series:
    """Deterministic series whose daily returns alternate up/down — nonzero return
    variance without randomness."""
    vals, x = [], start
    for i in range(len(dates)):
        vals.append(x)
        x *= (1 + up) if i % 2 == 0 else (1 + down)
    return pd.Series(vals, index=dates)


def _dead_era(end: str = "2026-01-15", n: int = 40) -> pd.DatetimeIndex:
    return pd.bdate_range(end=end, periods=n)


def _run(tmp_path, **kw):
    defaults = dict(cfg=CFG, now=NOW, out_dir=tmp_path / "quality",
                    data_dir=tmp_path / "data", directory={}, quality_raw={})
    defaults.update(kw)
    return art.run(**defaults)


def _lines(capsys, prefix: str) -> list[str]:
    return [ln for ln in capsys.readouterr().out.splitlines() if ln.startswith(prefix)]


# --------------------------------------------------------------------------- #
# zombie: spans death, advancing, mismatched overlap
# --------------------------------------------------------------------------- #

def test_zombie_detected_and_warned(tmp_path, capsys):
    dead = _dead_era()
    live = pd.bdate_range(start=dead[0], end="2026-07-31")
    _write_registry(tmp_path / "data", {"ZOMB": _alternating(dead, 50.0, 0.02, -0.01)})
    # anti-phase returns on the overlap => correlation ~ -1 (different instrument)
    _write_store(tmp_path / "data", "stocks", "ZOMB",
                 _alternating(live, 20.0, -0.01, 0.02))
    doc = _run(tmp_path, directory={"ZOMB": "New Holder Corp"})
    assert doc["totals"]["zombie"] == 1
    assert doc["totals"]["registry_mismatch"] == 0
    [entry] = doc["stores"][0]["zombie"]
    assert entry["ticker"] == "ZOMB" and entry["acked"] is False
    assert entry["overlap"]["min_ret_corr"] < art.CORR_DIFFERENT_INSTRUMENT
    assert doc["unacked_zombies"] == ["stocks/ZOMB"]
    warns = _lines(capsys, "::warning title=reused ticker key::")
    assert len(warns) == 1 and "stocks/ZOMB" in warns[0]


def test_acked_zombie_disclosed_but_quiet(tmp_path, capsys):
    dead = _dead_era()
    live = pd.bdate_range(start=dead[0], end="2026-07-31")
    _write_registry(tmp_path / "data", {"ZOMB": _alternating(dead, 50.0, 0.02, -0.01)})
    _write_store(tmp_path / "data", "stocks", "ZOMB",
                 _alternating(live, 20.0, -0.01, 0.02))
    doc = _run(tmp_path, quality_raw={"reused_ticker_acks": {"ZOMB": "documented reuse"}})
    assert doc["totals"]["zombie"] == 1
    [entry] = doc["stores"][0]["zombie"]
    assert entry["acked"] is True and entry["ack"] == "documented reuse"
    assert doc["unacked_zombies"] == []
    assert _lines(capsys, "::warning title=reused ticker key::") == []


def test_thin_overlap_is_still_a_zombie(tmp_path, capsys):
    # spans the death date but shares < MIN_OVERLAP_ROWS rows with the registry:
    # unverifiable continuity past a death must stay LOUD, not slide through.
    dead = _dead_era(n=10)
    live = pd.bdate_range(start=dead[-5], end="2026-07-31")
    _write_registry(tmp_path / "data", {"THIN": _alternating(dead, 30.0, 0.02, -0.01)})
    _write_store(tmp_path / "data", "stocks", "THIN",
                 _alternating(live, 10.0, -0.01, 0.02))
    doc = _run(tmp_path)
    assert doc["totals"]["zombie"] == 1
    assert "min_ret_corr" not in doc["stores"][0]["zombie"][0]["overlap"]
    assert any("overlap too thin" in ln
               for ln in _lines(capsys, "::warning title=reused ticker key::"))


# --------------------------------------------------------------------------- #
# same instrument => the registry, not the store, is contaminated
# --------------------------------------------------------------------------- #

def test_same_instrument_is_registry_mismatch_not_zombie(tmp_path, capsys):
    dead = _dead_era()
    live = pd.bdate_range(start=dead[0], end="2026-07-31")
    series = _alternating(live, 50.0, 0.02, -0.01)
    _write_registry(tmp_path / "data", {"ALIV": series.loc[dead[0]:dead[-1]]})
    # identical returns, different LEVEL (adjusted vs raw): corr == 1.0
    _write_store(tmp_path / "data", "stocks", "ALIV", series * 0.95)
    doc = _run(tmp_path)
    assert doc["totals"]["zombie"] == 0
    assert doc["totals"]["registry_mismatch"] == 1
    out = capsys.readouterr().out.splitlines()  # capture ONCE — readouterr consumes
    assert [ln for ln in out if ln.startswith("::warning title=reused ticker key::")] == []
    notices = [ln for ln in out if ln.startswith("::notice title=dead registry contamination::")]
    assert len(notices) == 1 and "ALIV" in notices[0]


# --------------------------------------------------------------------------- #
# clean break / frozen-at-death
# --------------------------------------------------------------------------- #

def test_post_death_start_is_rebirth_and_quiet(tmp_path, capsys):
    dead = _dead_era()
    reborn = pd.bdate_range(start="2026-04-01", end="2026-07-31")
    _write_registry(tmp_path / "data", {"REBN": _alternating(dead, 30.0, 0.02, -0.01)})
    _write_store(tmp_path / "data", "stocks", "REBN",
                 _alternating(reborn, 10.0, 0.01, -0.005))
    doc = _run(tmp_path)
    assert doc["totals"] == {"zombie": 0, "rebirth": 1, "registry_mismatch": 0,
                             "delisted_printing": 0}
    assert [ln for ln in capsys.readouterr().out.splitlines()
            if ln.startswith("::warning")] == []


def test_frozen_at_death_is_not_flagged(tmp_path):
    dead = _dead_era()
    series = _alternating(dead, 30.0, 0.02, -0.01)
    _write_registry(tmp_path / "data", {"DEAD": series})
    _write_store(tmp_path / "data", "stocks", "DEAD", series)  # tip == registry last
    doc = _run(tmp_path)
    assert doc["totals"] == {"zombie": 0, "rebirth": 0, "registry_mismatch": 0,
                             "delisted_printing": 0}


# --------------------------------------------------------------------------- #
# delisted_printing (EA class) + directory notation + acks
# --------------------------------------------------------------------------- #

def test_delisted_printing_summary_warning(tmp_path, capsys):
    fresh = pd.bdate_range(end="2026-08-04", periods=30)
    _write_registry(tmp_path / "data", {})
    _write_store(tmp_path / "data", "stocks", "GONE",
                 _alternating(fresh, 200.0, 0.001, -0.001))
    doc = _run(tmp_path, directory={"OTHER": "Some Corp"})
    assert doc["totals"]["delisted_printing"] == 1
    assert doc["unacked_delisted_printing"] == ["stocks/GONE"]
    warns = _lines(capsys, "::warning title=delisted still printing::")
    assert len(warns) == 1 and "stocks/GONE" in warns[0]


def test_delisted_printing_ack_and_dot_dash_normalization(tmp_path, capsys):
    fresh = pd.bdate_range(end="2026-08-04", periods=30)
    _write_registry(tmp_path / "data", {})
    _write_store(tmp_path / "data", "stocks", "RHHBY",
                 _alternating(fresh, 40.0, 0.001, -0.001))
    _write_store(tmp_path / "data", "stocks", "BRK-B",
                 _alternating(fresh, 400.0, 0.001, -0.001))
    doc = _run(tmp_path, directory={"BRK.B": "Berkshire Hathaway Inc. New Common Stock"},
               quality_raw={"delisted_printing_acks": ["RHHBY"]})
    # BRK-B is listed under dot notation => not flagged at all; RHHBY flagged but acked
    assert doc["totals"]["delisted_printing"] == 1
    assert doc["unacked_delisted_printing"] == []
    assert _lines(capsys, "::warning title=delisted still printing::") == []


def test_stale_unlisted_name_is_not_delisted_printing(tmp_path):
    # frozen keys are audit_stocks_freshness's stale_live domain — no double alarm
    stale = pd.bdate_range(end="2026-06-18", periods=30)
    _write_registry(tmp_path / "data", {})
    _write_store(tmp_path / "data", "stocks", "SATS",
                 _alternating(stale, 100.0, 0.001, -0.001))
    doc = _run(tmp_path, directory={"OTHER": "Some Corp"})
    assert doc["totals"]["delisted_printing"] == 0


# --------------------------------------------------------------------------- #
# degraded modes + shared-shape contract
# --------------------------------------------------------------------------- #

def test_absent_registry_darkens_not_crashes(tmp_path, capsys):
    fresh = pd.bdate_range(end="2026-08-04", periods=30)
    _write_store(tmp_path / "data", "stocks", "AAAA",
                 _alternating(fresh, 10.0, 0.001, -0.001))
    doc = _run(tmp_path, directory={"AAAA": "Alive Corp"})
    assert doc.get("registry_dark") is True
    assert any("DARK" in ln for ln in _lines(capsys, "::warning title=reused ticker key::"))


def test_directory_dark_disclosed(tmp_path, capsys):
    _write_registry(tmp_path / "data", {})
    _write_store(tmp_path / "data", "stocks", "AAAA",
                 _alternating(pd.bdate_range(end="2026-08-04", periods=30),
                              10.0, 0.001, -0.001))
    doc = _run(tmp_path, directory=None)  # fetch_directory monkeypatched below
    assert doc.get("directory_dark") is True
    assert any("DARK" in ln for ln in _lines(capsys, "::warning title=delisted still printing::"))


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    monkeypatch.setattr(art, "fetch_directory", lambda timeout=20: None)


def test_absent_stores_skip_and_findings_never_fail(tmp_path, capsys):
    _write_registry(tmp_path / "data", {})
    doc = _run(tmp_path)
    assert doc["n_failed"] == 0
    # both cohorts skipped: an absent store is a CI-lite checkout, never an abort
    assert doc["totals"] == {"zombie": 0, "rebirth": 0, "registry_mismatch": 0,
                             "delisted_printing": 0}


def test_zombie_is_a_flag_never_a_fail(tmp_path):
    dead = _dead_era()
    live = pd.bdate_range(start=dead[0], end="2026-07-31")
    _write_registry(tmp_path / "data", {"ZOMB": _alternating(dead, 50.0, 0.02, -0.01)})
    _write_store(tmp_path / "data", "stocks", "ZOMB",
                 _alternating(live, 20.0, -0.01, 0.02))
    doc = _run(tmp_path)
    assert doc["totals"]["zombie"] == 1
    assert doc["n_failed"] == 0  # CSP-R1: disclosure, never fail-dark
