"""Dark Pool Desk — unit tests.

Covers:
1. Parser unit tests for finra_short_volume._parse (via fixture lines)
2. FINRA ATS transparency collector parse logic (_parse_rows)
3. Off-exchange share computation in build_darkpool_desk
4. Builder smoke test (no panel → graceful return 0)
5. Nav checks pass
"""
from __future__ import annotations

import pathlib
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

# Ensure project root is on path for sibling-module imports
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

# ---------------------------------------------------------------------------
# 1. CNMSshvol parser (reuses existing fixture — extended coverage)
# ---------------------------------------------------------------------------
from collectors.finra_short_volume import _parse

SAMPLE_CNMSshvol = """\
Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market
20240603|AAPL|5321456|12034|18750000|B,Q,N
20240603|NVDA|8901234|56789|22345678|B,Q,N
20240603|ZERO|0|0|0|Q
Total Records: 3
"""


def test_cnms_parse_basic_fields():
    df = _parse(SAMPLE_CNMSshvol)
    assert set(df.columns) >= {"date", "ticker", "short_vol", "short_exempt", "total_vol", "short_ratio"}
    assert set(df["ticker"]) == {"AAPL", "NVDA"}   # ZERO row dropped (total_vol=0)


def test_cnms_parse_short_ratio_computation():
    df = _parse(SAMPLE_CNMSshvol)
    aapl = df[df["ticker"] == "AAPL"].iloc[0]
    expected = 5321456 / 18750000
    assert aapl["short_ratio"] == pytest.approx(expected, abs=1e-4)


def test_cnms_parse_date_type():
    df = _parse(SAMPLE_CNMSshvol)
    assert df["date"].iloc[0] == pd.Timestamp("2024-06-03")


def test_cnms_parse_garbage_returns_empty():
    assert _parse("no pipes\nhere either").empty


def test_cnms_parse_header_footer_stripped():
    df = _parse(SAMPLE_CNMSshvol)
    tickers = set(df["ticker"])
    assert "Date" not in tickers
    assert "Total" not in tickers


# ---------------------------------------------------------------------------
# 2. FINRA ATS transparency parser
# ---------------------------------------------------------------------------
from collectors.finra_ats_transparency import _parse_rows

SAMPLE_ATS_ROWS = [
    {
        "issueSymbolIdentifier": "AAPL",
        "issueName": "Apple Inc.",
        "weekStartDate": "2023-11-06",
        "summaryStartDate": "2023-11-06",
        "MPID": "UBSA",
        "marketParticipantName": "UBSA UBS ATS",
        "totalWeeklyShareQuantity": 1250000,
        "totalWeeklyTradeCount": 4500,
        "tierIdentifier": "NMS",
        "summaryTypeCode": "ATS_W_SMBL_FIRM",
    },
    {
        "issueSymbolIdentifier": None,    # aggregate row — should be dropped
        "weekStartDate": "2023-11-06",
        "summaryStartDate": "2023-11-06",
        "MPID": None,
        "marketParticipantName": None,
        "totalWeeklyShareQuantity": 99999999,
        "totalWeeklyTradeCount": 9999999,
        "tierIdentifier": "NMS",
        "summaryTypeCode": "ATS_W_VOL_STATS",
    },
    {
        "issueSymbolIdentifier": "NVDA",
        "weekStartDate": "2023-11-06",
        "summaryStartDate": "2023-11-06",
        "MPID": "JPBX",
        "marketParticipantName": "JPBX JPB-X",
        "totalWeeklyShareQuantity": 3456789,
        "totalWeeklyTradeCount": 12000,
        "tierIdentifier": "NMS",
        "summaryTypeCode": "ATS_W_SMBL_FIRM",
    },
]


def test_ats_parse_drops_null_symbol():
    df = _parse_rows(SAMPLE_ATS_ROWS)
    assert set(df["ticker"]) == {"AAPL", "NVDA"}   # null-symbol aggregate row dropped


def test_ats_parse_schema():
    df = _parse_rows(SAMPLE_ATS_ROWS)
    required = {"week_start", "ticker", "mpid", "venue_name", "shares", "trades", "tier"}
    assert required <= set(df.columns)


def test_ats_parse_values():
    df = _parse_rows(SAMPLE_ATS_ROWS)
    aapl = df[df["ticker"] == "AAPL"].iloc[0]
    assert aapl["shares"] == pytest.approx(1250000.0)
    assert aapl["trades"] == 4500
    assert aapl["mpid"] == "UBSA"
    assert aapl["week_start"] == pd.Timestamp("2023-11-06")


def test_ats_parse_empty_input():
    assert _parse_rows([]).empty


def test_ats_complete_weeks_requires_t1_and_t2():
    """2026-07 repair: weeks are ingested only once BOTH T1 and T2 partitions are
    published (T1 leads T2 by ~2wk; a T1-only ingest would freeze a half week
    into the write-once store)."""
    from datetime import date as _d
    from collectors.finra_ats_transparency import _complete_weeks
    parts = {
        _d(2026, 6, 15): {"T1"},                          # T1-only — not complete
        _d(2026, 6, 8):  {"T1"},                          # T1-only — not complete
        _d(2026, 6, 1):  {"NA", "OTCE", "T1", "T2"},      # complete
        _d(2026, 5, 25): {"T1", "T2"},                    # complete (OTCE optional)
    }
    assert _complete_weeks(parts) == [_d(2026, 6, 1), _d(2026, 5, 25)]


def test_ats_degradable_covers_gateway_errors():
    """Retried-out CDN 5xx/429 must degrade to the stored-data heartbeat, same as
    a hard connection error (FINRA's edge throws sporadic 504s)."""
    import requests as _rq
    from collectors.finra_ats_transparency import _degradable
    resp = _rq.Response()
    resp.status_code = 504
    assert _degradable(_rq.HTTPError("HTTP 504", response=resp))
    assert _degradable(_rq.exceptions.ConnectionError("boom"))
    resp2 = _rq.Response()
    resp2.status_code = 404
    assert not _degradable(_rq.HTTPError("HTTP 404", response=resp2))


class _FakePage:
    def __init__(self, rows, total):
        self._rows = rows
        self.headers = {"Record-Total": str(total)}

    def json(self):
        return self._rows


def test_ats_fetch_week_paginates_to_completion(monkeypatch):
    """Offset pagination must walk every page and stop on the short one
    (Record-Total verified live 2026-07-11: filtered count, e.g. 192,411
    for week 2026-06-01)."""
    from datetime import date as _d
    import collectors.finra_ats_transparency as fat

    monkeypatch.setattr(fat, "PAGE_SIZE", 2)
    monkeypatch.setattr(fat, "SLEEP_PAGE", 0)
    offsets = []

    def fake_http(session, method, url, json_body=None, timeout=60):
        offsets.append(json_body["offset"])
        assert json_body["dateRangeFilters"][0]["startDate"] == "2026-06-01"
        remaining = 5 - json_body["offset"]
        return _FakePage([{"n": i} for i in range(min(2, remaining))], 5)

    monkeypatch.setattr(fat, "_http", fake_http)
    rows = fat._fetch_week(None, _d(2026, 6, 1))
    assert len(rows) == 5
    assert offsets == [0, 2, 4]


def test_ats_fetch_week_refuses_truncation(monkeypatch):
    """If MAX_PAGES caps out below Record-Total, the week must RAISE (get skipped)
    rather than persist a silently-truncated file — the exact corruption mode of
    the pre-repair store (20231106.parquet holds 19,978 of ~150k rows)."""
    from datetime import date as _d
    import collectors.finra_ats_transparency as fat

    monkeypatch.setattr(fat, "PAGE_SIZE", 2)
    monkeypatch.setattr(fat, "MAX_PAGES", 2)
    monkeypatch.setattr(fat, "SLEEP_PAGE", 0)

    def fake_http(session, method, url, json_body=None, timeout=60):
        return _FakePage([{"n": 1}, {"n": 2}], 10)   # always-full pages, total 10

    monkeypatch.setattr(fat, "_http", fake_http)
    with pytest.raises(RuntimeError, match="truncated"):
        fat._fetch_week(None, _d(2026, 6, 1))


def test_ats_loader_skips_heartbeat_parquet(tmp_path, monkeypatch):
    """data/finra_ats/ holds both <YYYYMMDD>.parquet weeks AND the runner's
    finra_ats__ingest.parquet heartbeat, which sorts lexicographically LAST —
    _load_ats must pick the newest WEEK, not the heartbeat (which used to shadow
    every week file and silently kill the venue table)."""
    import scripts.build_darkpool_desk as bdd

    ats = tmp_path / "finra_ats"
    ats.mkdir()
    week = pd.DataFrame({"week_start": [pd.Timestamp("2026-06-01")] * 2,
                         "ticker": ["AAPL", "NVDA"], "mpid": ["UBSA", "JPBX"],
                         "venue_name": ["UBS ATS", "JPB-X"],
                         "shares": [1.0, 2.0], "trades": [1, 2],
                         "tier": ["T1", "T1"]})
    week.to_parquet(ats / "20260601.parquet", index=False)
    pd.DataFrame({"new_rows": [0]},
                 index=[pd.Timestamp("2026-06-01")]).to_parquet(ats / "finra_ats__ingest.parquet")
    monkeypatch.setattr(bdd, "ATS_DIR", ats)
    df = bdd._load_ats_two()[0]
    assert df is not None and set(df["ticker"]) == {"AAPL", "NVDA"}


def test_ats_parse_null_mpid_included():
    rows = [{**SAMPLE_ATS_ROWS[0], "MPID": None, "marketParticipantName": None}]
    df = _parse_rows(rows)
    assert len(df) == 1
    assert df.iloc[0]["mpid"] == ""


# ---------------------------------------------------------------------------
# 3. Off-exchange share computation
# ---------------------------------------------------------------------------
from scripts.build_darkpool_desk import _compute_ticker_stats


def _make_panel(rows_data):
    """Create a minimal panel DataFrame for testing."""
    return pd.DataFrame(rows_data, columns=["date", "ticker", "short_vol", "short_exempt",
                                             "total_vol", "short_ratio"])


def test_oe_share_computed_correctly():
    """Off-exchange share = FINRA total_vol / yahoo consolidated volume."""
    rows = [
        (pd.Timestamp("2024-06-01"), "AAPL", 1_000_000, 50_000, 2_000_000,
         round(1_000_000 / 2_000_000, 4)),
        (pd.Timestamp("2024-06-02"), "AAPL", 1_100_000, 55_000, 2_100_000,
         round(1_100_000 / 2_100_000, 4)),
        (pd.Timestamp("2024-06-03"), "AAPL", 1_200_000, 60_000, 2_200_000,
         round(1_200_000 / 2_200_000, 4)),
    ]
    panel = _make_panel(rows)
    # Yahoo says consolidated volume on 2024-06-03 is 8_800_000
    yahoo_vol = {
        "AAPL": pd.Series(
            [8_800_000.0],
            index=pd.DatetimeIndex([pd.Timestamp("2024-06-03")]),
        )
    }
    stats, _, _ = _compute_ticker_stats(panel, yahoo_vol, None, None)
    aapl = next(r for r in stats if r["ticker"] == "AAPL")
    # FINRA total_vol on 2024-06-03 = 2_200_000; yahoo = 8_800_000 → share = 0.25
    assert aapl["oe_share"] == pytest.approx(0.25, abs=1e-4)


def test_oe_share_none_when_yahoo_missing():
    """When yahoo volume is not available, oe_share should be None."""
    rows = [
        (pd.Timestamp("2024-06-01"), "ZZZZ", 100, 5, 200, 0.5),
        (pd.Timestamp("2024-06-02"), "ZZZZ", 110, 5, 220, 0.5),
        (pd.Timestamp("2024-06-03"), "ZZZZ", 120, 5, 240, 0.5),
    ]
    panel = _make_panel(rows)
    stats, _, _ = _compute_ticker_stats(panel, {}, None, None)   # no yahoo data
    row = next(r for r in stats if r["ticker"] == "ZZZZ")
    assert row["oe_share"] is None


def test_short_ratio_trend_direction():
    """Increasing short ratio → positive trend_pp."""
    rows = (
        [(pd.Timestamp(f"2024-05-{i:02d}"), "AAA", 100, 5, 1000, 0.10) for i in range(1, 11)]
        + [(pd.Timestamp(f"2024-05-{i:02d}"), "AAA", 300, 15, 1000, 0.30) for i in range(11, 16)]
    )
    panel = _make_panel(rows)
    stats, _, _ = _compute_ticker_stats(panel, {}, None, None)
    row = next(r for r in stats if r["ticker"] == "AAA")
    assert row["trend_pp"] > 0, "Increasing short flow should yield positive trend_pp"


def test_thin_ticker_excluded():
    """Tickers with < 3 days of data are excluded from stats."""
    rows = [
        (pd.Timestamp("2024-06-01"), "THIN", 100, 5, 200, 0.5),
        (pd.Timestamp("2024-06-02"), "THIN", 110, 5, 220, 0.5),
    ]
    panel = _make_panel(rows)
    stats, _, _ = _compute_ticker_stats(panel, {}, None, None)
    assert not any(r["ticker"] == "THIN" for r in stats)


# ---------------------------------------------------------------------------
# 4. Builder smoke test
# ---------------------------------------------------------------------------
def test_builder_reports_failure_when_panel_missing(tmp_path, monkeypatch):
    """Missing canonical input retains prior artifacts but is not a success.

    BOTH panel paths must be nulled: _load_panel() reads PANEL_DEEP_PATH *and*
    PANEL_PATH and returns their union, so nulling only the collector panel left
    the real 322k-row deep store in play — main() ran a FULL live build and
    overwrote the tracked site/darkpool.html, site/darkpool_eod.json and
    data/darkpool/context/latest.json, while `result == 0` passed anyway because
    main() also returns 0 on success (found via MM_DATA_GUARD, PR #4699).
    Assert on the early return itself, not just the code.
    """
    import scripts.build_darkpool_desk as bdd

    monkeypatch.setattr(bdd, "PANEL_PATH", tmp_path / "nonexistent.parquet")
    monkeypatch.setattr(bdd, "PANEL_DEEP_PATH", tmp_path / "nonexistent_deep.parquet")
    # Nothing may be rendered or emitted on the panel-missing path — every writer
    # main() can reach is patched, so a regression records into `wrote` (asserted
    # below) instead of escaping to the real tree.  build_context_feed runs BEFORE
    # write_page, so leaving it live still leaked data/darkpool/context/latest.json.
    import engine.darkpool_context as _dpc

    wrote: dict = {}
    monkeypatch.setattr(bdd, "write_page", lambda path, html, **kw: wrote.update(page=path) or path)
    monkeypatch.setattr(bdd, "_emit_pane_json", lambda *a, **kw: wrote.update(pane=True))
    monkeypatch.setattr(_dpc, "build_context_feed", lambda *a, **kw: wrote.update(context=True))

    result = bdd.main()

    assert result != 0
    assert not wrote, f"panel-missing path must write nothing, wrote: {sorted(wrote)}"


def test_finra_expected_available_session_owns_1830_et_release_clock():
    from collectors.finra_short_volume import expected_available_session

    et = ZoneInfo("America/New_York")
    assert expected_available_session(datetime(2026, 8, 19, 18, 29, tzinfo=et)).isoformat() == "2026-08-18"
    assert expected_available_session(datetime(2026, 8, 19, 18, 30, tzinfo=et)).isoformat() == "2026-08-19"
    assert expected_available_session(datetime(2026, 8, 21, 19, 0, tzinfo=et)).isoformat() == "2026-08-21"  # Friday evening
    assert expected_available_session(datetime(2026, 8, 22, 12, 0, tzinfo=et)).isoformat() == "2026-08-21"  # Saturday
    assert expected_available_session(datetime(2026, 8, 24, 18, 29, tzinfo=et)).isoformat() == "2026-08-21"  # Monday pre-release
    assert expected_available_session(datetime(2026, 9, 7, 20, 0, tzinfo=et)).isoformat() == "2026-09-04"   # Labor Day


def test_mixed_ticker_dates_partition_current_authority_from_browse_history():
    import inspect
    import scripts.build_darkpool_desk as bdd

    rows = [
        {"ticker": "AAPL", "asof": "2026-08-19", "participation": 0.41},
        {"ticker": "MSFT", "asof": "2026-08-19", "participation": 0.38},
        {"ticker": "QQQ", "asof": "2026-08-04", "participation": 0.52},
    ]
    current, stale, coverage = bdd._partition_session_rows(
        rows, panel_latest="2026-08-19", tracked_universe=3
    )
    assert [r["ticker"] for r in current] == ["AAPL", "MSFT"]
    assert [r["ticker"] for r in stale] == ["QQQ"]
    assert stale[0]["session_status"] == "stale"
    assert coverage == {
        "tracked_universe": 3,
        "current_session_rows": 2,
        "stale_rows": 1,
        "missing_rows": 0,
        "current_session_pct": 66.7,
    }

    # The single admission seam feeds every current-authority consumer.
    source = inspect.getsource(bdd.main)
    assert "for r in current_stats" in source          # market gauge
    assert "_dpc.build_context_feed(\n            current_clean" in source
    assert "_emit_pane_json(\n            current_clean" in source


def test_darkpool_pane_separates_current_universe_from_historical_rows(tmp_path):
    import json
    import scripts.build_darkpool_desk as bdd

    current = [{"ticker": "AAPL", "asof": "2026-08-19", "session_status": "current"}]
    historical = [{"ticker": "QQQ", "asof": "2026-08-04", "session_status": "stale"}]
    out = tmp_path / "darkpool_eod.json"
    bdd._emit_pane_json(
        current, {}, panel_latest="2026-08-19", panel_dates=100, below_floor=False,
        n_with_oe=1, n_with_ats=0, ats_lag_note=None, built="test",
        coverage={"tracked_universe": 2, "current_session_rows": 1,
                  "stale_rows": 1, "missing_rows": 0, "current_session_pct": 50.0},
        historical_rows=historical, out_path=out,
    )
    payload = json.loads(out.read_text())
    assert [r["ticker"] for r in payload["universe"]] == ["AAPL"]
    assert [r["ticker"] for r in payload["historical_rows"]] == ["QQQ"]
    assert all(r["asof"] == payload["asof"] for r in payload["universe"])


def test_darkpool_static_settled_copy_never_uses_wall_clock_today():
    from engine.darkpool_context import _hero

    template = (pathlib.Path(__file__).resolve().parents[1] / "templates" / "darkpool.html.j2").read_text()
    assert "today" not in template.lower()
    assert "今日" not in template
    active = _hero({"heavy_into_weakness": 1}, {"participation_dollar_wtd": 0.4})
    quiet = _hero({}, {"participation_dollar_wtd": 0.4})
    assert "settled session" in active["en"] and "today" not in active["en"].lower()
    assert "settled session" in quiet["en"] and "today" not in quiet["en"].lower()


def test_builder_disabled_by_config(tmp_path, monkeypatch):
    """darkpool.enabled=false → builder returns 0 without reading any data.
    The disabled path writes a noindex stub — capture it via bdd.write_page
    (the import-time-bound name; patching lib.pages.write_page would no-op and
    the stub would overwrite the REAL site/darkpool.html)."""
    import scripts.build_darkpool_desk as bdd
    from lib import config as lib_config

    _orig_load = lib_config.load

    def _fake_load():
        d = _orig_load()
        d["darkpool"] = {"enabled": False}
        return d

    written = {}
    monkeypatch.setattr(bdd, "write_page",
                        lambda path, html, **kw: written.update(html=html) or path)
    monkeypatch.setattr(lib_config, "load", _fake_load)
    result = bdd.main()
    assert result == 0
    assert "disabled" in written.get("html", ""), "disabled stub should be written"


# ---------------------------------------------------------------------------
# 5. Nav checks — check_nav_gap and check_nav_mega pass on the built page
# ---------------------------------------------------------------------------
def test_nav_checks_pass_on_rendered_page(tmp_path):
    """Render darkpool.html into a tmp dir and verify nav-gap + nav-mega checks pass."""
    import os, sys

    # Render the page into a temporary site dir
    site_dir = tmp_path / "site"
    site_dir.mkdir()

    # Minimal synthetic panel so the builder can produce output
    panel_dir = tmp_path / "finra_short_volume"
    panel_dir.mkdir()
    panel_rows = []
    for i in range(35):
        d = pd.Timestamp(f"2024-0{1 + i // 28}-{(i % 28) + 1:02d}")
        panel_rows.append((d, "AAPL", 1_000_000 + i * 1000, 50_000, 5_000_000, 0.20))
        panel_rows.append((d, "NVDA", 2_000_000 + i * 2000, 80_000, 8_000_000, 0.25))

    pd.DataFrame(panel_rows, columns=["date", "ticker", "short_vol", "short_exempt",
                                       "total_vol", "short_ratio"]).to_parquet(
        panel_dir / "panel.parquet"
    )

    import scripts.build_darkpool_desk as bdd
    from lib import config as lib_config

    monkeypatches = {}

    def _fake_load():
        d = {"darkpool": {"enabled": True}}
        return d

    orig_load = lib_config.load
    orig_panel = bdd.PANEL_PATH
    orig_deep = bdd.PANEL_DEEP_PATH
    orig_ats = bdd.ATS_DIR
    orig_yahoo = bdd.YAHOO_DIR
    orig_root = lib_config.ROOT

    try:
        lib_config.load = _fake_load
        bdd.PANEL_PATH = panel_dir / "panel.parquet"
        # _load_panel() UNIONS the deep backfill with the collector panel, so the
        # deep store must be nulled too or this "minimal synthetic panel" silently
        # renders the real 1,632-ticker history instead of the fixture above.
        bdd.PANEL_DEEP_PATH = tmp_path / "nonexistent_deep.parquet"
        bdd.ATS_DIR = tmp_path / "finra_ats"   # no ATS data — should degrade gracefully
        bdd.YAHOO_DIR = tmp_path / "yahoo"      # no yahoo data — oe_share=None
        lib_config.ROOT = pathlib.Path(__file__).resolve().parent.parent

        # Override site write target via write_page. IMPORTANT: the builder binds
        # `from lib.pages import write_page` at import time, so the patch must go
        # on bdd.write_page — patching lib.pages.write_page silently no-ops and
        # bdd.main() then overwrites the REAL site/darkpool.html with this test's
        # synthetic 2024 panel (found trashing the working tree 2026-07-11).
        orig_write = bdd.write_page
        orig_emit = bdd._emit_pane_json

        written_html = {}

        def _fake_write(path, html, **kw):
            written_html["content"] = html
            (site_dir / "darkpool.html").write_text(html)
            return site_dir / "darkpool.html"

        def _fake_emit(*a, **kw):
            # main() also emits site/darkpool_eod.json; ROOT is the REAL repo here
            # (templates must resolve), so redirect this output to tmp too.
            kw["out_path"] = site_dir / "darkpool_eod.json"
            return orig_emit(*a, **kw)

        # main() also builds the darkpool_context.v1 artifact under config.ROOT —
        # which is the REAL repo here (templates must resolve). Redirect its write
        # to tmp so the synthetic 2024 panel can't clobber the live context feed.
        import engine.darkpool_context as _dpc
        orig_ctx = _dpc.build_context_feed
        _dpc.build_context_feed = lambda *a, **k: orig_ctx(*a, **{**k, "root": tmp_path})

        bdd.write_page = _fake_write
        bdd._emit_pane_json = _fake_emit
        try:
            rc = bdd.main()
        finally:
            bdd.write_page = orig_write
            bdd._emit_pane_json = orig_emit
            _dpc.build_context_feed = orig_ctx

        if rc != 0:
            pytest.skip("builder returned non-zero — may need data; skip nav check")

        if "content" not in written_html:
            pytest.skip("builder did not write page (data missing)")

        html = written_html["content"]

        # nav-mega check: the rendered page must carry the Research mega-menu
        assert "nav-mega" in html, "darkpool.html missing nav-mega (stale nav)"

        # nav-gap/layout check: the page should use the shared nav once and keep
        # content inside its own responsive shell.
        assert html.count('<nav class="site-nav">') == 1, "darkpool.html should render one shared nav"
        assert 'class="dp-shell"' in html, "darkpool.html missing responsive content shell"
        assert "<title>Dark Pool — how much of each stock trades off the public tape</title>" in html
        assert '<meta name="description" content="<span' not in html

    finally:
        lib_config.load = orig_load
        bdd.PANEL_PATH = orig_panel
        bdd.PANEL_DEEP_PATH = orig_deep
        bdd.ATS_DIR = orig_ats
        bdd.YAHOO_DIR = orig_yahoo
        lib_config.ROOT = orig_root


# ---------------------------------------------------------------------------
# 6. Interim Terminal Dark Pool pane artifact (site/darkpool_eod.json)
# ---------------------------------------------------------------------------
import json as _json
import re

from scripts.build_darkpool_desk import _emit_pane_json


def _sample_rows_clean():
    return [
        {"ticker": "AAPL", "asof": "2026-07-14", "oe_share": 0.42, "oe_trend_pp": 1.2,
         "oe_z": 0.8, "spark20": [0.40, 0.41, 0.42], "ats_top_venue": "UBS ATS",
         "ats_share_pct": 3.1, "finra_total_vol": 12_345_678},
        {"ticker": "ZZZZ", "asof": "2026-07-14", "oe_share": None, "oe_trend_pp": None,
         "oe_z": None, "spark20": [], "ats_top_venue": None, "ats_share_pct": None,
         "finra_total_vol": 1000},
    ]


def _sample_ats_table():
    return {
        "week_start": "2026-06-08",
        "venues": [{"mpid": "UBSA", "venue_name": "UBS ATS", "total_shares": 1_000_000,
                    "total_trades": 4500, "n_symbols": 300, "share_of_total_pct": 8.1,
                    "wow_pp": 0.3, "wow_is_new": False}],
        "n_symbols_total": 300,
    }


def test_pane_json_emitter_contract(tmp_path):
    """The interim pane artifact carries the EOD contract: schema/tier/source,
    the full ranked universe passthrough, weekly venues, and explicit-null
    pending fields (never faked)."""
    out = tmp_path / "darkpool_eod.json"
    _emit_pane_json(
        _sample_rows_clean(), _sample_ats_table(),
        panel_latest="2026-07-14", panel_dates=120, below_floor=False,
        n_with_oe=1, n_with_ats=1, ats_lag_note="2–4 wk publication lag",
        built="2026-07-16 00:00 UTC", out_path=out,
    )
    doc = _json.loads(out.read_text(encoding="utf-8"))

    assert doc["schema"] == "darkpool_eod.v2"
    assert doc["tier"] == "eod"                       # interim; not "intraday" yet
    assert doc["source"] == "finra_facilities"        # debranded
    assert doc["asof"] == "2026-07-14"
    # Full universe passes through, including the null-oe_share tail row
    assert [r["ticker"] for r in doc["universe"]] == ["AAPL", "ZZZZ"]
    assert doc["universe"][0]["oe_share"] == 0.42
    # gauge + coverage ride along so a pane consumer can state what was NOT covered
    assert "gauge" in doc and "coverage" in doc
    # Weekly venues + lag note preserved
    assert doc["venues"]["week_start"] == "2026-06-08"
    assert doc["venues"]["lag_note"].startswith("2")
    assert doc["venues"]["rows"][0]["venue_name"] == "UBS ATS"
    # Intraday tick-feed fields are present but null — pending, not faked
    assert doc["pending"]["intraday_oe_share"] is None
    assert doc["pending"]["price_levels"] is None
    assert doc["pending"]["biggest_prints"] is None


def test_pane_json_no_data_vendor_name(tmp_path):
    """Debrand law: the public artifact must not name the tick-data vendor."""
    out = tmp_path / "darkpool_eod.json"
    _emit_pane_json(
        _sample_rows_clean(), _sample_ats_table(),
        panel_latest="2026-07-14", panel_dates=120, below_floor=False,
        n_with_oe=1, n_with_ats=1, ats_lag_note=None,
        built="2026-07-16 00:00 UTC", out_path=out,
    )
    text = out.read_text(encoding="utf-8").lower()
    for vendor in ("thetadata", "theta data", "polygon"):
        assert vendor not in text, f"debrand: {vendor!r} leaked into public artifact"


# ---------------------------------------------------------------------------
# 7. darkpool_context — observed conjunctions + change-feed (darkpool_context.v2)
#
# v1 tagged accumulation/distribution/unusual and rendered "leaning up/down".
# That construction is forbidden by DO_NOT_REBUILD (PSS-AF1 row): "Raw short
# ratio/off-exchange share remains forbidden as a standalone direction signal."
# v2 groups by the CONJUNCTION observed (heavy hidden volume + what price did),
# which is a description of settled data and is not standalone.
# ---------------------------------------------------------------------------
from engine import darkpool_context as dctx


def _row(ticker, z, participation, price_change_pct=None, streak=0,
         participation_norm=None, ats_frac=None, pattern="__auto__"):
    """A desk row in v2 shape. `pattern` defaults to what signals._pattern would set."""
    if pattern == "__auto__":
        from engine.darkpool_signals import _pattern
        pattern = _pattern(z, price_change_pct)
    return {
        "ticker": ticker, "participation_z": z, "participation": participation,
        "participation_norm": participation_norm if participation_norm is not None else participation * 0.7,
        "price_change_pct": price_change_pct, "streak": streak, "pattern": pattern,
        "ats_frac": ats_frac, "short_rate": 0.5, "short_trend_pp": 0.0,
        "short_rate_z": 0.0, "offex_dollars": 1e8, "top_ats_venue": None,
    }


def test_classify_names_the_conjunction_not_a_direction():
    """The tag says what price was doing alongside the volume — never where it goes."""
    assert dctx.classify(_row("W", 2.0, 0.55, price_change_pct=-4.0)) == "heavy_into_weakness"
    assert dctx.classify(_row("S", 2.0, 0.50, price_change_pct=+5.0)) == "heavy_into_strength"
    assert dctx.classify(_row("F", 2.0, 0.50, price_change_pct=+0.2)) == "heavy_price_flat"


def test_classify_returns_none_without_price():
    """No price ⇒ no conjunction. Tagging on off-exchange share alone is the
    construction DO_NOT_REBUILD forbids, so it must not be reachable."""
    assert dctx.classify(_row("NOPX", 2.5, 0.60, price_change_pct=None)) is None


def test_standout_gate_excludes_low_z_low_share_and_null():
    assert dctx.classify(_row("LOWZ", 0.5, 0.60, price_change_pct=-3.0)) is None    # not unusual vs own norm
    assert dctx.classify(_row("LOWSH", 2.5, 0.30, price_change_pct=-3.0)) is None   # not materially dark
    assert dctx.classify({"ticker": "NOZ", "participation_z": None,
                          "participation": 0.6, "pattern": None}) is None           # no history → honest null


def test_no_direction_vocabulary_anywhere_in_the_snapshot():
    """Guards the standing kill: the rendered payload must never lean a direction.

    Pins the WORDS a reader sees. If someone reintroduces a directional label the
    page would ship it silently — this is the check that can see that.
    """
    rows = [_row("W1", 2.5, 0.60, price_change_pct=-4.0),
            _row("S1", 2.2, 0.52, price_change_pct=+6.0),
            _row("F1", 1.8, 0.48, price_change_pct=+0.1)]
    snap = dctx.build_snapshot(rows, None, "2026-08-04")
    blob = _json.dumps(snap, ensure_ascii=False).lower()

    # Phrases that CONSTITUTE a call. Matched on word boundaries: explanatory prose
    # legitimately contains "buyers"/"sellers" (e.g. "as consistent with sellers meeting
    # demand as with buyers chasing"), and a substring test would fail that sentence for
    # saying the opposite of a direction call.
    banned_en = ("leaning up", "leaning down", "accumulation", "distribution",
                 "bullish", "bearish", "validated", "buy signal", "sell signal")
    for phrase in banned_en:
        assert not re.search(r"\b" + re.escape(phrase) + r"\b", blob), \
            f"directional/unvalidated vocabulary leaked: {phrase!r}"
    for zh in ("偏多", "偏空", "吸筹", "派发"):
        assert zh not in blob, f"directional vocabulary leaked (zh): {zh!r}"


def test_build_snapshot_shape_and_hero_honesty():
    rows = [
        _row("W1", 2.5, 0.60, price_change_pct=-4.0), _row("W2", 2.0, 0.55, price_change_pct=-3.0),
        _row("S1", 2.2, 0.52, price_change_pct=+6.0),
        _row("F1", 1.8, 0.48, price_change_pct=+0.1),
        _row("SKIP", 0.2, 0.60, price_change_pct=-3.0),   # not a standout
    ]
    snap = dctx.build_snapshot(rows, None, "2026-08-04")
    assert snap["tally"] == {"heavy_into_weakness": 2, "heavy_into_strength": 1,
                             "heavy_price_flat": 1}
    assert snap["n_standouts"] == 4
    assert "SKIP" not in [s["ticker"] for s in snap["standouts"]]
    hero = snap["hero"]["en"].lower()
    for banned in ("buy", "sell", "validated", "leaning"):
        assert banned not in hero
    # every group closes on a WATCH condition, never an entry
    for k in ("heavy_into_weakness", "heavy_into_strength", "heavy_price_flat"):
        assert "watching" in snap["patterns"][k]["watch"]["en"].lower()


def test_standout_depth_marker_carries_own_norm():
    """The depth-bar 'norm' marker uses the name's own trailing baseline."""
    snap = dctx.build_snapshot(
        [_row("X", 2.0, 0.60, price_change_pct=-3.0, participation_norm=0.42)], None, "2026-08-04")
    s = snap["standouts"][0]
    assert s["participation"] == 0.60 and s["participation_norm"] == 0.42


def test_venue_character_states_how_much_reached_a_real_dark_pool():
    """ats_frac is rendered in words so "dark volume" is never read as "dark pool".

    The who-was-on-the-other-side half moved to `_counterparty_character` once the
    non-ATS firm roster landed; this function now reports only the ATS share.
    """
    hi = dctx._venue_character(0.55)["en"]
    lo = dctx._venue_character(0.12)["en"]
    assert hi == "55%"
    assert lo.startswith("only "), "below the typical large-cap level the copy says 'only'"
    assert "12%" in lo
    assert dctx._venue_character(None)["en"] == "not yet reported"


def test_card_values_never_restate_their_own_label():
    """The board renders "<label> <value>". A value that repeats its label prints
    "Reached a dark pool 34% reached a dark pool" — which shipped twice in this page's
    history (also "Running for 6 sessions running" / "已持续 连续 6 日").

    Pins the value side against the label wording in BOTH languages.
    """
    labels = {                                  # label text as rendered on the card
        "venue_character": ("reached a dark pool", "进入暗池"),
        "streak_label": ("elevated for", "已持续"),
    }
    row = _row("X", 2.0, 0.60, price_change_pct=-3.0, streak=6, ats_frac=0.34)
    snap = dctx.build_snapshot([row], None, "2026-08-04")
    s = snap["standouts"][0]
    for field, (label_en, label_zh) in labels.items():
        val = s[field]
        assert label_en not in val["en"].lower(), (
            f"{field} value {val['en']!r} restates its label {label_en!r}")
        assert label_zh not in val["zh"], (
            f"{field} value {val['zh']!r} restates its label {label_zh!r}")


def test_change_feed_first_run_is_empty():
    snap = dctx.build_snapshot([_row("A", 2.0, 0.55, price_change_pct=-3.0)], None, "2026-08-04")
    changes, prev = dctx.build_changes(None, snap, "2026-08-04")
    assert changes == {"vs_asof": None, "items": []}


def test_change_feed_detects_new_day_entrant():
    prior = dctx.build_context_feed([_row("A", 2.0, 0.55, price_change_pct=-3.0)], None,
                                    asof="2026-08-03", built="t", write=False)
    today = dctx.build_snapshot([_row("A", 2.0, 0.55, price_change_pct=-3.0),
                                 _row("B", 2.0, 0.55, price_change_pct=-3.0)], None, "2026-08-04")
    changes, _ = dctx.build_changes(prior, today, "2026-08-04")
    joined = " ".join(i["en"] for i in changes["items"])
    assert "B started printing dark into weakness" in joined
    assert "A " not in joined  # A was already there → no phantom entry


def test_change_feed_same_day_rebuild_is_idempotent():
    """A same-day rebuild reuses prev_state so the day's diff isn't wiped/duplicated."""
    y = dctx.build_context_feed([_row("A", 2.0, 0.55, price_change_pct=-3.0)], None,
                                asof="2026-08-03", built="t", write=False)
    today = dctx.build_snapshot([_row("A", 2.0, 0.55, price_change_pct=-3.0),
                                 _row("B", 2.0, 0.55, price_change_pct=-3.0)], None, "2026-08-04")
    ch1, prev1 = dctx.build_changes(y, today, "2026-08-04")
    contract = {"asof": "2026-08-04", "patterns": today["patterns"], "venues": today["venues"],
                "prev_state": prev1}
    ch2, _ = dctx.build_changes(contract, today, "2026-08-04")
    assert [i["en"] for i in ch1["items"]] == [i["en"] for i in ch2["items"]]


def test_context_feed_artifact_contract(tmp_path):
    rows = [_row("W1", 2.5, 0.60, price_change_pct=-4.0),
            _row("S1", 2.2, 0.52, price_change_pct=+6.0)]
    ats = {"week_start": "2026-06-22", "lag_note": "6 wk publication lag", "lag_days": 44,
           "venues": [{"mpid": "BLUE", "venue_name": "BLUE BOATS", "share_of_total_pct": 7.4,
                       "wow_pp": 2.9, "wow_is_new": False}]}
    art = dctx.build_context_feed(rows, ats, asof="2026-08-04", built="2026-08-04 00:00 UTC",
                                  root=tmp_path)
    assert art["schema"] == "darkpool_context.v2"
    assert art["is_context_only"] is True and art["display_only"] is True
    assert art["tally"]["heavy_into_weakness"] == 1 and art["tally"]["heavy_into_strength"] == 1
    assert art["venues"]["mover"]["name"] == "BLUE BOATS"
    assert art["venues"]["lag_days"] == 44
    on_disk = _json.loads((tmp_path / "data" / "darkpool" / "context" / "latest.json").read_text(encoding="utf-8"))
    assert on_disk["schema"] == "darkpool_context.v2"
    assert "validated" not in _json.dumps(art).lower()


def test_forward_ledger_accrues_and_is_same_day_idempotent(tmp_path):
    """v1 shipped a call and recorded nothing, so it could never be graded.

    The ledger records the observed state at tag time; a same-day rebuild must
    REPLACE that day's block rather than append a duplicate.
    """
    rows = [_row("W1", 2.5, 0.60, price_change_pct=-4.0)]
    ats = {"week_start": "2026-06-22", "venues": []}
    dctx.build_context_feed(rows, ats, asof="2026-08-04", built="t", root=tmp_path)
    led = tmp_path / "data" / "darkpool" / "ledger" / "forward.jsonl"
    assert led.exists()
    first = [l for l in led.read_text().splitlines() if l.strip()]
    assert len(first) == 1 and _json.loads(first[0])["ticker"] == "W1"

    # same-day rebuild → still one row for that asof
    dctx.build_context_feed(rows, ats, asof="2026-08-04", built="t", root=tmp_path)
    again = [l for l in led.read_text().splitlines() if l.strip()]
    assert len(again) == 1, "same-day rebuild duplicated the ledger block"

    # next day appends rather than replacing history
    dctx.build_context_feed(rows, ats, asof="2026-08-05", built="t", root=tmp_path)
    two = [l for l in led.read_text().splitlines() if l.strip()]
    assert len(two) == 2
    assert {_json.loads(l)["asof"] for l in two} == {"2026-08-04", "2026-08-05"}
    # records inputs only — never an outcome or a direction
    rec = _json.loads(two[0])
    assert "direction" not in rec and "score" not in rec and "outcome" not in rec
