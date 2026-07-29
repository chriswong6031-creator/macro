"""The nightly earnings sweep must sweep the UNIVERSE, and its tripwire must see coverage.

OIP E8 / E5 diagnosis, 2026-07-29.  ``data/earnings/earnings.parquet`` held 1364 rows of
which exactly 3 were fresh — AAPL, NVDA, JPM.  Two independent defects, stacked:

1. **daily.yml ran the smoke test.**  ``collectors/equity_earnings.__main__`` was
   ``ts = sys.argv[1:] or ["AAPL", "NVDA", "JPM"]`` followed by
   ``fetch_earnings(force=True, max_new=len(ts), tickers=ts)`` — and daily.yml's
   collect_tail step invokes ``python -m collectors.equity_earnings`` bare.  Passing
   ``tickers=`` bypasses ``_universe()`` entirely, so the "~66 weekday, whole universe"
   sweep the step comment promises had never once run in production.  Nasdaq was never
   the problem: probed live the same day, the calendar endpoint returned HTTP 200 with
   305 / 61 / 132 rows for 2026-07-30 / 07-31 / 08-03.  After the fix a bare run swept
   1513 names and stamped 1066 of them today.
2. **The tripwire graded max(as_of).**  ``scripts/audit_earnings_freshness.audit()``
   returned ``ok: true, warnings: [], sla_ok: true`` over that store, because ONE fresh
   row satisfies a max-based SLA.  It was structurally incapable of catching (1) — the
   presence-vs-coverage class.  It now grades the SHARE of rows inside the SLA and
   escalates a stale-at-scale store to a line-start ``::error``.

These tests pin both.  Hermetic: no network (the collector's own network functions are
monkeypatched), no live stores.

Run: .venv/bin/python -m pytest tests/test_earnings_sweep_entrypoint.py -q
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import collectors.equity_earnings as ee  # noqa: E402

DAILY = (ROOT / ".github" / "workflows" / "daily.yml").read_text()
COLLECTOR_SRC = (ROOT / "collectors" / "equity_earnings.py").read_text()


# ─────────────────────────────────────────────────────────────── the entry point


def test_daily_invokes_the_collector_bare():
    """Premise of the whole bug: the nightly passes NO ticker arguments."""
    assert "python -m collectors.equity_earnings \\\n" in DAILY, (
        "daily.yml's invocation shape changed — re-check which code path it reaches"
    )
    step = DAILY.split("python -m collectors.equity_earnings", 1)[1].split("\n", 1)[0]
    assert step.strip() in ("\\", ""), (
        f"daily.yml now passes arguments to the collector ({step!r}); a ticker list "
        "switches it back to the SMOKE path"
    )


def test_no_hardcoded_ticker_list_in_collector_code():
    """A ticker-list literal in this module's CODE is the bug (docstrings exempt: the
    postmortem above quotes the old line on purpose)."""
    import ast
    tree = ast.parse(COLLECTOR_SRC)
    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.List, ast.Tuple)) or len(node.elts) < 2:
            continue
        vals = [e.value for e in node.elts
                if isinstance(e, ast.Constant) and isinstance(e.value, str)]
        if len(vals) != len(node.elts):
            continue
        # a ticker list looks like short ALL-CAPS alphabetic symbols
        if all(1 <= len(v) <= 5 and v.isalpha() and v.isupper() for v in vals):
            offenders.append(vals)
    assert not offenders, (
        f"hardcoded ticker list(s) in collector code: {offenders} — a bare "
        "`python -m collectors.equity_earnings` must sweep _universe(), never a fixed list"
    )


def _stub_network(monkeypatch, tmp_path, universe, cal_rows):
    """Replace the two network functions + the cache path; return the calls seen."""
    seen = {"calendar": 0, "surprises": []}

    def fake_calendar_sweep(session, uni):
        seen["calendar"] += 1
        seen["universe"] = set(uni)
        return {t: dict(cal_rows[t]) for t in cal_rows if t in uni}, False

    def fake_surprises(session, sym):
        seen["surprises"].append(sym)
        return [{"qtr": "Jun 2026", "reported": "7/1/2026", "eps": 1.0,
                 "consensus": 0.9, "surprise_pct": 11.1}]

    monkeypatch.setattr(ee, "_calendar_sweep", fake_calendar_sweep)
    monkeypatch.setattr(ee, "_surprises", fake_surprises)
    monkeypatch.setattr(ee, "_universe", lambda: set(universe))
    monkeypatch.setattr(ee, "_cache_path", lambda: tmp_path / "earnings.parquet")
    # the drip's politeness sleep is real wall-clock; 120 names × 0.25s per test is
    # 30s of CI for nothing when the network calls are already stubbed
    monkeypatch.setattr(ee.time, "sleep", lambda *_a, **_k: None)
    return seen


def test_bare_main_sweeps_the_whole_universe(monkeypatch, tmp_path):
    universe = {f"TK{i:03d}" for i in range(200)}
    cal = {t: {"next_date": "2026-08-14", "next_time": "time-after-hours",
               "eps_forecast": 1.23} for t in sorted(universe)[:150]}
    seen = _stub_network(monkeypatch, tmp_path, universe, cal)

    assert ee.main([]) == 0
    assert seen["universe"] == universe, "bare main() must sweep _universe()"

    out = pd.read_parquet(tmp_path / "earnings.parquet")
    assert len(out) == 150, f"expected the whole calendar hit persisted, got {len(out)}"
    today = datetime.now(timezone.utc).date().isoformat()
    assert (out["as_of"].astype(str).str.startswith(today)).sum() == 150


def test_bare_main_caps_the_surprise_drip(monkeypatch, tmp_path):
    """The expensive per-name call stays capped — the calendar is what must be whole."""
    universe = {f"TK{i:03d}" for i in range(400)}
    cal = {t: {"next_date": "2026-08-14", "next_time": None, "eps_forecast": None}
           for t in sorted(universe)}
    seen = _stub_network(monkeypatch, tmp_path, universe, cal)

    ee.main([])
    assert len(seen["surprises"]) == ee.DEFAULT_MAX_NEW == 120
    # ...but every calendar hit is persisted, not just the dripped batch
    assert len(pd.read_parquet(tmp_path / "earnings.parquet")) == 400


def test_explicit_tickers_still_run_the_smoke_path(monkeypatch, tmp_path):
    universe = {f"TK{i:03d}" for i in range(200)}
    cal = {"AAPL": {"next_date": "2026-08-14", "next_time": None, "eps_forecast": None},
           "NVDA": {"next_date": "2026-08-26", "next_time": None, "eps_forecast": None}}
    seen = _stub_network(monkeypatch, tmp_path, universe, cal)

    assert ee.main(["AAPL", "NVDA"]) == 0
    assert seen["universe"] == {"AAPL", "NVDA"}, "named tickers must not sweep the universe"

    seen["universe"] = None
    assert ee.main(["--tickers", "aapl,nvda"]) == 0
    assert seen["universe"] == {"AAPL", "NVDA"}, "--tickers is the same smoke path"


def test_a_bot_walled_sweep_keeps_the_cache_and_annotates(monkeypatch, tmp_path, capsys):
    """The Akamai-wall path must stay non-destructive AND visible."""
    cache = tmp_path / "earnings.parquet"
    pd.DataFrame([{"ticker": "AAPL", "next_date": "2026-08-01", "next_time": None,
                   "eps_forecast": None, "surprises_json": "[]",
                   "as_of": "2026-06-19T00:00:00+00:00"}]).set_index("ticker").to_parquet(cache)

    monkeypatch.setattr(ee, "_universe", lambda: {"AAPL", "MSFT"})
    monkeypatch.setattr(ee, "_cache_path", lambda: cache)
    monkeypatch.setattr(ee, "_calendar_sweep", lambda s, u: ({}, True))

    assert ee.main([]) == 0
    out = pd.read_parquet(cache)
    assert len(out) == 1 and out.loc["AAPL", "as_of"].startswith("2026-06-19"), (
        "a blocked sweep must leave the cache byte-identical"
    )
    # nothing was written, so the run reports the empty result loudly
    assert len(pd.read_parquet(cache)) == 1


def test_empty_sweep_annotation_starts_the_line(capsys, monkeypatch, tmp_path):
    monkeypatch.setattr(ee, "_universe", lambda: {"AAPL"})
    monkeypatch.setattr(ee, "_cache_path", lambda: tmp_path / "absent.parquet")
    monkeypatch.setattr(ee, "_calendar_sweep", lambda s, u: ({}, False))
    ee.main([])
    lines = [ln for ln in capsys.readouterr().out.splitlines() if "::" in ln]
    assert lines, "an empty production sweep must annotate"
    for ln in lines:
        assert ln.startswith("::"), f"annotation not at line start: {ln!r}"
    assert any("earnings-sweep-empty" in ln for ln in lines)


# ───────────────────────────────────────────────────── the coverage-aware tripwire


def _write_store(tmp_path: Path, fresh_n: int, stale_n: int) -> Path:
    d = tmp_path / "earnings"
    d.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    old = (now - timedelta(days=40)).isoformat()
    rows = []
    for i in range(fresh_n):
        rows.append({"ticker": f"FR{i:04d}", "next_date": "2026-08-14", "next_time": None,
                     "eps_forecast": None, "surprises_json": "[]", "as_of": now.isoformat()})
    for i in range(stale_n):
        rows.append({"ticker": f"ST{i:04d}", "next_date": "2026-09-14", "next_time": None,
                     "eps_forecast": None, "surprises_json": "[]", "as_of": old})
    pd.DataFrame(rows).set_index("ticker").to_parquet(d / "earnings.parquet")
    return d / "earnings.parquet"


def _audit(monkeypatch, tmp_path):
    import lib.config as cfg
    import scripts.audit_earnings_freshness as af
    monkeypatch.setattr(cfg, "data_dir", lambda: tmp_path)
    return af, af.audit()


def test_three_fresh_rows_in_a_big_store_is_an_error_not_a_green(monkeypatch, tmp_path):
    """THE regression: the exact 2026-07-29 store shape must no longer read green."""
    _write_store(tmp_path, fresh_n=3, stale_n=1361)
    af, result = _audit(monkeypatch, tmp_path)
    assert result["errors"], "a 3-of-1364 store must escalate, not pass"
    assert result["detail"]["fresh_rows"] == 3
    assert result["detail"]["fresh_share"] < 0.01
    # the OLD check still reports fresh — which is precisely why it was not enough
    assert result["detail"]["sla_ok"] is True
    assert "coverage_ok" not in result["detail"]


def test_a_real_sweep_passes_coverage(monkeypatch, tmp_path):
    """70% fresh is the measured shape of a healthy sweep (1066 of 1513)."""
    _write_store(tmp_path, fresh_n=1066, stale_n=447)
    af, result = _audit(monkeypatch, tmp_path)
    assert not result["errors"] and not result["warnings"]
    assert result["detail"]["coverage_ok"] is True
    assert result["detail"]["fresh_share"] > ee_min_share(af)


def ee_min_share(af) -> float:
    return af.MIN_FRESH_SHARE


def test_the_sla_was_not_widened(monkeypatch, tmp_path):
    """A wholly-stale store must still say stale — coverage is an ADDITION."""
    import scripts.audit_earnings_freshness as af
    assert af.DEFAULT_MAX_AGE_TD == 2, "the 2-trading-day SLA is not negotiable here"
    _write_store(tmp_path, fresh_n=0, stale_n=800)
    _, result = _audit(monkeypatch, tmp_path)
    assert any("stale" in w.lower() for w in result["warnings"]), "age check must still fire"
    assert result["errors"], "and coverage must fire too"


def test_small_store_stays_a_warning(monkeypatch, tmp_path):
    """Below the plausibility floor the share is not meaningful — don't cry ::error."""
    _write_store(tmp_path, fresh_n=1, stale_n=20)
    _, result = _audit(monkeypatch, tmp_path)
    assert not result["errors"]
    assert any("suspiciously small" in w for w in result["warnings"])
    assert any("stale AT SCALE" in w for w in result["warnings"])


def test_stale_at_scale_annotation_starts_the_line(monkeypatch, tmp_path, capsys):
    _write_store(tmp_path, fresh_n=3, stale_n=1361)
    import lib.config as cfg
    import scripts.audit_earnings_freshness as af
    monkeypatch.setattr(cfg, "data_dir", lambda: tmp_path)
    rc = af.run_as_main(strict=False)
    assert rc == 0, "the nightly step is non-fatal by design"
    out = capsys.readouterr().out
    ann = [ln for ln in out.splitlines() if "::" in ln]
    assert ann
    for ln in ann:
        assert ln.startswith("::"), f"annotation not at line start: {ln!r}"
    assert any(ln.startswith("::error title=earnings-stale::") for ln in ann), (
        "a stale-at-scale store must emit a line-start ::error"
    )


def test_strict_mode_fails_on_a_coverage_error(monkeypatch, tmp_path):
    _write_store(tmp_path, fresh_n=3, stale_n=1361)
    import lib.config as cfg
    import scripts.audit_earnings_freshness as af
    monkeypatch.setattr(cfg, "data_dir", lambda: tmp_path)
    assert af.run_as_main(strict=True) == 1


@pytest.mark.parametrize("keys", [
    ("fresh_rows", "fresh_share", "min_fresh_share"),
])
def test_detail_publishes_the_denominator(monkeypatch, tmp_path, keys):
    """The artifact must carry the numbers, not just a verdict — nulls printed."""
    _write_store(tmp_path, fresh_n=60, stale_n=60)
    _, result = _audit(monkeypatch, tmp_path)
    for k in keys:
        assert k in result["detail"], f"detail missing {k}"
