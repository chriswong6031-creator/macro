"""The earnings wire tripwire must fail on the outage it was written for.

The 2026-08-02 freeze survived twelve days because every green it produced was
true-but-irrelevant. So each test here pins a way this tripwire could go green
while the archive is dead, not merely that it computes a number.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.audit_earnings_wire_freshness import (
    EarningsWireFreshnessError,
    audit,
    main,
    newest_published_call_date,
)


def _catalog(events_by_ticker: dict[str, list[str]], **extra) -> dict:
    routes = {}
    for ticker, days in events_by_ticker.items():
        routes[ticker] = {
            "events": {f"E{i}": {"date": d} for i, d in enumerate(days)},
            "latest": {"date": max(days)},
        }
    return {"routes": routes, "article_count": len(routes), **extra}


def _index(days: list[str]) -> dict:
    return {"dates": {f"SYM{i}/2026Q2": d for i, d in enumerate(days)}}


def test_ok_when_publication_keeps_up() -> None:
    report = audit(_catalog({"AAA": ["2026-08-12"]}), _index(["2026-08-12"]))
    assert report["level"] == "ok"
    assert report["lag_days"] == 0
    assert report["upstream_bodies_newer_than_published"] == 0


def test_warns_then_errors_as_the_gap_widens() -> None:
    """Thresholds are inclusive: warn at lag >= 3d, escalate at lag >= 7d."""
    catalog = _catalog({"AAA": ["2026-08-01"]})
    assert audit(catalog, _index(["2026-08-03"]))["level"] == "ok"        # lag 2
    assert audit(catalog, _index(["2026-08-04"]))["level"] == "warning"   # lag 3
    assert audit(catalog, _index(["2026-08-07"]))["level"] == "warning"   # lag 6
    assert audit(catalog, _index(["2026-08-08"]))["level"] == "error"     # lag 7


def test_the_real_outage_shape_is_an_error_with_a_backlog_count() -> None:
    """2026-07-29 published vs 2026-08-12 upstream — the exact freeze."""
    report = audit(
        _catalog({"AAA": ["2026-07-29"], "BBB": ["2026-07-28"]}),
        _index(["2026-07-29", "2026-08-04", "2026-08-06", "2026-08-12"]),
    )
    assert report["level"] == "error"
    assert report["lag_days"] == 14
    assert report["upstream_bodies_newer_than_published"] == 3


def test_newest_published_reads_every_event_not_each_routes_latest() -> None:
    """Reading `latest` per route answers a question that stays green forever.

    Every route has a `latest`, so a per-route reading always finds something
    recent-looking. Only the max across ALL events can notice that the archive as
    a whole stopped moving.
    """
    catalog = _catalog({"AAA": ["2026-07-01"], "BBB": ["2026-07-29"]})
    assert newest_published_call_date(catalog).isoformat() == "2026-07-29"


def test_an_unmeasurable_index_is_an_error_not_a_zero_lag() -> None:
    """No `dates` map must never be reported as a healthy 0-day lag."""
    with pytest.raises(EarningsWireFreshnessError):
        audit(_catalog({"AAA": ["2026-08-12"]}), {"symbols": {"AAA": ["2026Q2"]}})
    with pytest.raises(EarningsWireFreshnessError):
        audit(_catalog({"AAA": ["2026-08-12"]}), {"dates": {}})


def test_a_catalog_with_no_dated_events_is_an_error() -> None:
    with pytest.raises(EarningsWireFreshnessError):
        audit({"routes": {}}, _index(["2026-08-12"]))
    with pytest.raises(EarningsWireFreshnessError):
        audit({}, _index(["2026-08-12"]))


def _run(tmp_path: Path, catalog: dict, index: dict, *extra: str) -> int:
    cat = tmp_path / "route-catalog.json"
    idx = tmp_path / "index.json"
    cat.write_text(json.dumps(catalog), encoding="utf-8")
    idx.write_text(json.dumps(index), encoding="utf-8")
    return main(["--catalog", str(cat), "--index-file", str(idx), "--offline", *extra])


def test_cli_emits_a_line_start_error_and_strict_exits_nonzero(tmp_path, capsys) -> None:
    rc = _run(tmp_path, _catalog({"AAA": ["2026-07-29"]}), _index(["2026-08-12"]), "--strict")
    out = capsys.readouterr().out
    line = next(ln for ln in out.splitlines() if "earnings-wire-stale" in ln)
    # A logger prefix would push the annotation off column 0 and GitHub would drop
    # it — the alarm would review as armed and emit nothing.
    assert line.startswith("::error title=earnings-wire-stale::")
    assert "lag=14d" in line and "backlog=1 bodies" in line
    assert rc == 1


def test_cli_stays_quiet_and_zero_when_fresh(tmp_path, capsys) -> None:
    rc = _run(tmp_path, _catalog({"AAA": ["2026-08-12"]}), _index(["2026-08-12"]), "--strict")
    out = capsys.readouterr().out
    assert rc == 0
    assert "::error" not in out and "::warning" not in out


def test_an_unreadable_input_annotates_instead_of_passing_silently(tmp_path, capsys) -> None:
    rc = main(
        ["--catalog", str(tmp_path / "missing.json"), "--index-file",
         str(tmp_path / "missing2.json"), "--offline", "--strict"]
    )
    out = capsys.readouterr().out
    assert rc == 1
    assert out.splitlines()[0].startswith("::error title=earnings-wire-freshness::")


def test_json_out_records_the_actionable_numbers(tmp_path) -> None:
    dest = tmp_path / "quality" / "wire.json"
    _run(tmp_path, _catalog({"AAA": ["2026-07-29"]}), _index(["2026-08-12"]),
         "--json-out", str(dest))
    report = json.loads(dest.read_text(encoding="utf-8"))
    assert report["schema"] == "macro.earnings_wire_freshness/v1"
    assert report["lag_days"] == 14
    assert report["level"] == "error"
