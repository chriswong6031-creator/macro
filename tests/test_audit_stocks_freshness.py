"""Per-name freshness tripwire for data/stocks/ (scripts/audit_stocks_freshness).

Pins the 2026-08-03 incident tripwire: a name that exits every sector SPDR's top-20
used to freeze its data/stocks/<T>.parquet forever with nothing watching per-name tips
(audit_prices checks interior gaps only; check_price_store_freshness gates only SPY).
This audit classifies every accountable ticker (stems of data/stocks/*.parquet UNION
top10_union()) into fresh / stale_live / stale_dead / missing / unreadable and
bare-prints a ::warning annotation when anything but stale_dead is present.

Also pins the 2026-08-03 LAG-ANCHOR correction: lag is measured from the ET calendar
date of `now` to the store's last bar — never from
lib.nyse_calendar.expected_last_session(now), which would let an exact-boundary freeze
hide under a `<= threshold` read (WDC: last bar Fri 07-24, expected session Fri 07-31
= exactly 7 days = inadmissible under the session anchor, even though the real freeze
was already 10 calendar days deep by 08-03). The threshold alone absorbs
weekends/holidays; expected_last_session is recorded as context only.

Synthetic stores in tmp dirs; cfg thresholds passed explicitly; every `now` is
injected — no wall clock anywhere. Every fail/stale annotation is asserted via capsys
at column 0 — the house rule from tests/test_gh_annotation_line_start.py.

Run: .venv/bin/python -m pytest tests/test_audit_stocks_freshness.py -q
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402
from scripts import audit_common, audit_stocks_freshness as asf  # noqa: E402

CFG = dict(audit_common.quality_cfg())
CFG.update({"stocks_stale_calendar_days": 7})

# Monday 2026-08-03, 20:00 UTC = 16:00 ET -> ET calendar date 2026-08-03 (also used
# for the real-data acceptance-gate dry run — see the task brief's Change B receipts).
_NOW = datetime.fromisoformat("2026-08-03T20:00:00+00:00")


@pytest.fixture()
def data_dir(tmp_path, monkeypatch):
    """The established idiom (tests/test_upsert_basis_guard.py): point lib.config's
    data_dir() at a tmp path. This is what makes the REAL (unmocked)
    collectors.sector_holdings._dead_tickers() hermetic — it always reads via
    config.data_dir(), never via a parameter this audit's own run() accepts."""
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    return tmp_path


def _write_stock(d: Path, ticker: str, last: str, n: int = 10) -> None:
    """A tiny synthetic parquet whose LAST index date is exactly `last`, regardless of
    weekday (calendar-day frequency — a business-day range would silently snap a
    weekend `last` to the preceding Friday, which several boundary tests below rely on
    NOT happening)."""
    idx = pd.date_range(end=last, periods=n, freq="D")
    df = pd.DataFrame({"close": 100.0, "high": 101.0, "low": 99.0, "volume": 1_000_000}, index=idx)
    df.index.name = "date"
    df.to_parquet(d / f"{ticker}.parquet")


def _annotations(out: str, prefix: str) -> list[str]:
    """Captured stdout lines that START with `prefix` — GitHub only parses a workflow
    command at column 0, so the startswith IS the assertion that matters."""
    return [ln for ln in out.splitlines() if ln.startswith(prefix)]


def _run(data_dir: Path, now: datetime = _NOW, cfg: dict = CFG) -> dict:
    return asf.run(cfg=cfg, now=now, out_dir=data_dir / "quality", data_dir=data_dir)


# ---------------------------------------------------------------------------
# classification + annotations
# ---------------------------------------------------------------------------


def test_all_fresh_zero_flags_no_annotation_exit_equivalent(data_dir, monkeypatch, capsys):
    d = data_dir / "stocks"
    d.mkdir(parents=True)
    _write_stock(d, "AAA", "2026-07-31")  # 3 calendar days before NOW's ET date
    _write_stock(d, "BBB", "2026-08-03")  # same day as NOW's ET date
    monkeypatch.setattr(asf, "top10_union", lambda: ["AAA", "BBB"])

    doc = _run(data_dir)

    assert doc["totals"] == {"fresh": 2, "stale_live": 0, "stale_dead": 0,
                             "missing": 0, "unreadable": 0}
    u = doc["universes"][0]
    assert u["n_failed"] == 0 and u["flags"] == []
    assert doc["stale_live"] == [] and doc["missing"] == [] and doc["unreadable"] == []
    assert asf.exit_code(doc, strict=True) == 0
    assert _annotations(capsys.readouterr().out, "::warning") == []


def test_stale_live_flagged_with_lag_and_annotation_at_column_zero(data_dir, monkeypatch, capsys):
    d = data_dir / "stocks"
    d.mkdir(parents=True)
    _write_stock(d, "CCC", "2026-07-01")  # 33 calendar days before NOW's ET date
    monkeypatch.setattr(asf, "top10_union", lambda: [])

    doc = _run(data_dir)

    assert doc["totals"]["stale_live"] == 1
    rec = doc["stale_live"][0]
    assert rec == {"ticker": "CCC", "last_bar": "2026-07-01", "lag_days": 33, "in_union": False}
    u = doc["universes"][0]
    assert u["n_failed"] == 0  # flags-only law: never a fail
    assert any(f["name"] == "CCC" and f["kind"] == "stale_live" for f in u["flags"])

    out = capsys.readouterr().out
    lines = _annotations(out, "::warning")
    assert len(lines) == 1
    assert lines[0].startswith("::warning title=stocks store freshness::")
    assert "CCC(33d)" in lines[0]
    assert "data/quality/stocks_freshness_audit.json" in lines[0]
    assert asf.exit_code(doc, strict=True) == 3
    assert asf.exit_code(doc, strict=False) == 0


def test_stale_dead_excluded_from_alarms(data_dir, monkeypatch, capsys):
    d = data_dir / "stocks"
    d.mkdir(parents=True)
    _write_stock(d, "DDD", "2026-06-01")
    monkeypatch.setattr(asf, "top10_union", lambda: [])
    monkeypatch.setattr(asf, "_dead_tickers", lambda: frozenset({"DDD"}))

    doc = _run(data_dir)

    assert doc["totals"]["stale_dead"] == 1
    assert doc["totals"]["stale_live"] == 0
    assert doc["stale_live"] == []
    # muted names are still visible in the marker, not buried in universe flags
    assert doc["stale_dead"][0]["ticker"] == "DDD"
    assert doc["stale_dead"][0]["in_union"] is False
    u = doc["universes"][0]
    assert u["n_failed"] == 0
    assert any(f["name"] == "DDD" and f["kind"] == "stale_dead" for f in u["flags"])
    assert _annotations(capsys.readouterr().out, "::warning") == []
    assert asf.exit_code(doc, strict=True) == 0


def test_missing_union_member_flagged(data_dir, monkeypatch, capsys):
    d = data_dir / "stocks"
    d.mkdir(parents=True)
    _write_stock(d, "AAA", "2026-08-03")  # keep the store non-empty so it isn't skipped
    monkeypatch.setattr(asf, "top10_union", lambda: ["AAA", "EEE"])  # EEE has no file

    doc = _run(data_dir)

    assert doc["totals"]["missing"] == 1
    assert doc["missing"] == [{"ticker": "EEE", "in_union": True}]
    lines = _annotations(capsys.readouterr().out, "::warning")
    assert len(lines) == 1
    assert "EEE(missing)" in lines[0]
    assert asf.exit_code(doc, strict=True) == 3


def test_unreadable_flagged_without_raising(data_dir, monkeypatch, capsys):
    d = data_dir / "stocks"
    d.mkdir(parents=True)
    (d / "FFF.parquet").write_bytes(b"not a parquet file")
    monkeypatch.setattr(asf, "top10_union", lambda: [])

    doc = _run(data_dir)  # must not raise

    assert doc["totals"]["unreadable"] == 1
    assert doc["unreadable"] == [{"ticker": "FFF", "in_union": False}]
    lines = _annotations(capsys.readouterr().out, "::warning")
    assert len(lines) == 1
    assert "FFF(unreadable)" in lines[0]
    assert asf.exit_code(doc, strict=True) == 3


def test_friday_tip_checked_monday_is_fresh_at_three_days(data_dir, monkeypatch, capsys):
    # 2026-08-03 lag-anchor correction's own worked example: a Friday tip checked the
    # following Monday is 3 calendar days old — fresh under the 7-day threshold, no
    # false alarm, entirely independent of expected_last_session.
    d = data_dir / "stocks"
    d.mkdir(parents=True)
    _write_stock(d, "GGG", "2026-07-31")  # Friday
    monkeypatch.setattr(asf, "top10_union", lambda: ["GGG"])

    doc = _run(data_dir, now=_NOW)  # _NOW is Monday 2026-08-03

    assert doc["totals"]["fresh"] == 1
    assert doc["totals"]["stale_live"] == 0
    assert doc["stale_live"] == []
    assert _annotations(capsys.readouterr().out, "::warning") == []


def test_boundary_lag_seven_not_flagged_eight_flagged(data_dir, monkeypatch):
    d = data_dir / "stocks"
    d.mkdir(parents=True)
    _write_stock(d, "SEVEN", "2026-07-27")  # exactly 7 calendar days before NOW
    _write_stock(d, "EIGHT", "2026-07-26")  # exactly 8 calendar days before NOW
    monkeypatch.setattr(asf, "top10_union", lambda: [])

    doc = _run(data_dir)

    assert doc["totals"]["fresh"] == 1
    assert doc["totals"]["stale_live"] == 1
    assert doc["stale_live"][0]["ticker"] == "EIGHT"
    assert doc["stale_live"][0]["lag_days"] == 8


def test_empty_store_dir_skipped(data_dir, monkeypatch, capsys):
    monkeypatch.setattr(asf, "top10_union", lambda: [])  # no data/stocks dir at all

    doc = _run(data_dir)

    u = doc["universes"][0]
    assert u["skipped"] is True
    assert doc["totals"] == {"fresh": 0, "stale_live": 0, "stale_dead": 0,
                             "missing": 0, "unreadable": 0}
    assert asf.exit_code(doc, strict=True) == 0
    out = capsys.readouterr().out  # readouterr() drains — read ONCE, assert twice
    assert "[stocks_freshness]" in out  # the plain summary line still prints
    # data/stocks is git-tracked, so an absent dir is a broken checkout: the skip
    # path must annotate that the detector is dark, not go quiet.
    dark = _annotations(out, "::warning")
    assert len(dark) == 1 and "DARK" in dark[0]


def test_top10_union_failure_does_not_raise(data_dir, monkeypatch):
    d = data_dir / "stocks"
    d.mkdir(parents=True)
    _write_stock(d, "AAA", "2026-08-03")

    def boom():
        raise RuntimeError("holdings store unreadable")

    monkeypatch.setattr(asf, "top10_union", boom)

    doc = _run(data_dir)  # must not raise — union just contributes nothing

    assert doc["totals"]["fresh"] == 1
    assert doc["totals"]["missing"] == 0
    # ...but the blindness must be DISCLOSED: without the union the `missing`
    # class is undetectable, so the doc records it and a DARK ::warning prints.
    assert doc["union_unavailable"] is True


def test_top10_union_failure_emits_dark_annotation(data_dir, monkeypatch, capsys):
    d = data_dir / "stocks"
    d.mkdir(parents=True)
    _write_stock(d, "AAA", "2026-08-03")
    monkeypatch.setattr(asf, "top10_union",
                        lambda: (_ for _ in ()).throw(RuntimeError("boom")))

    _run(data_dir)

    lines = _annotations(capsys.readouterr().out, "::warning")
    assert len(lines) == 1
    assert "missing" in lines[0] and "DARK" in lines[0]


def test_stale_dead_in_union_alarms_as_stale_live(data_dir, monkeypatch, capsys):
    """Union-aware mute (ECHO class): a dead-registry ticker STILL in the current
    union is a reused symbol being actively fetched — when its store goes stale it
    must alarm, not hide under stale_dead."""
    d = data_dir / "stocks"
    d.mkdir(parents=True)
    _write_stock(d, "DDD", "2026-06-01")
    monkeypatch.setattr(asf, "top10_union", lambda: ["DDD"])
    monkeypatch.setattr(asf, "_dead_tickers", lambda: frozenset({"DDD"}))

    doc = _run(data_dir)

    assert doc["totals"]["stale_live"] == 1
    assert doc["totals"]["stale_dead"] == 0
    assert doc["stale_dead"] == []
    assert doc["stale_live"][0]["ticker"] == "DDD"
    assert doc["stale_live"][0]["in_union"] is True
    assert len(_annotations(capsys.readouterr().out, "::warning")) == 1
    assert asf.exit_code(doc, strict=True) == 3


def test_writes_audit_json(data_dir, monkeypatch):
    d = data_dir / "stocks"
    d.mkdir(parents=True)
    _write_stock(d, "AAA", "2026-08-03")
    monkeypatch.setattr(asf, "top10_union", lambda: ["AAA"])

    _run(data_dir)

    import json
    out = json.loads((data_dir / "quality" / "stocks_freshness_audit.json").read_text())
    assert out["audit"] == "stocks"
    assert out["expected_session"] == "2026-07-31"  # context field, unused in the flag decision
    assert out["threshold_calendar_days"] == 7


# ---------------------------------------------------------------------------
# dead-registry integration (real _dead_tickers(), not mocked)
# ---------------------------------------------------------------------------


def test_dead_store_absent_flag_when_registry_missing(data_dir, monkeypatch):
    d = data_dir / "stocks"
    d.mkdir(parents=True)
    _write_stock(d, "AAA", "2026-08-03")
    monkeypatch.setattr(asf, "top10_union", lambda: ["AAA"])
    # No data/edgar/dead_name_prices.parquet written under data_dir -> real
    # _dead_tickers() (NOT mocked here) sees an absent file.

    doc = _run(data_dir)

    assert doc.get("dead_store_absent") is True


def test_real_dead_tickers_integration(data_dir, monkeypatch):
    d = data_dir / "stocks"
    d.mkdir(parents=True)
    _write_stock(d, "ZZZ", "2026-06-01")
    edgar = data_dir / "edgar"
    edgar.mkdir(parents=True)
    pd.DataFrame({"ticker": ["ZZZ"], "date": [pd.Timestamp("2026-01-01")],
                 "close": [0.0], "source": ["imputed_bankruptcy"]}).to_parquet(
        edgar / "dead_name_prices.parquet")
    monkeypatch.setattr(asf, "top10_union", lambda: [])
    # _dead_tickers is intentionally NOT mocked here — this exercises the real
    # collectors.sector_holdings._dead_tickers() against the monkeypatched
    # config.data_dir(), proving the two modules' registries actually agree.

    doc = _run(data_dir)

    assert doc["totals"]["stale_dead"] == 1
    assert doc["totals"]["stale_live"] == 0
    assert doc.get("dead_store_absent") is not True


# ---------------------------------------------------------------------------
# main(argv) — --strict / default exit behavior, no wall clock
# ---------------------------------------------------------------------------


def test_main_default_always_exits_zero_even_with_alarms(monkeypatch):
    monkeypatch.setattr(asf, "run", lambda **kw: {
        "totals": {"fresh": 1, "stale_live": 1, "stale_dead": 0, "missing": 0, "unreadable": 0}})
    assert asf.main(["--now", "2026-08-03T20:00:00+00:00"]) == 0


def test_main_strict_exits_three_with_alarms(monkeypatch):
    captured = {}

    def fake_run(**kw):
        captured.update(kw)
        return {"totals": {"fresh": 1, "stale_live": 1, "stale_dead": 0,
                           "missing": 0, "unreadable": 0}}

    monkeypatch.setattr(asf, "run", fake_run)
    assert asf.main(["--strict", "--now", "2026-08-03T20:00:00+00:00"]) == 3
    assert captured["now"] == datetime.fromisoformat("2026-08-03T20:00:00+00:00")


def test_main_strict_exits_zero_with_no_alarms(monkeypatch):
    monkeypatch.setattr(asf, "run", lambda **kw: {
        "totals": {"fresh": 5, "stale_live": 0, "stale_dead": 1, "missing": 0, "unreadable": 0}})
    assert asf.main(["--strict"]) == 0


def test_main_crash_exits_two(monkeypatch):
    def boom(**kw):
        raise RuntimeError("boom")

    monkeypatch.setattr(asf, "run", boom)
    assert asf.main([]) == 2
