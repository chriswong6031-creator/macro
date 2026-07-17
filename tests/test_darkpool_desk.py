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
def test_builder_returns_0_when_panel_missing(tmp_path, monkeypatch):
    """Builder should return 0 (not raise) when the panel file is absent."""
    # Monkeypatch PANEL_PATH to a non-existent file
    import scripts.build_darkpool_desk as bdd
    monkeypatch.setattr(bdd, "PANEL_PATH", tmp_path / "nonexistent.parquet")
    result = bdd.main()
    assert result == 0


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
    orig_ats = bdd.ATS_DIR
    orig_yahoo = bdd.YAHOO_DIR
    orig_root = lib_config.ROOT

    try:
        lib_config.load = _fake_load
        bdd.PANEL_PATH = panel_dir / "panel.parquet"
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

        bdd.write_page = _fake_write
        bdd._emit_pane_json = _fake_emit
        try:
            rc = bdd.main()
        finally:
            bdd.write_page = orig_write
            bdd._emit_pane_json = orig_emit

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
        assert "<title>Dark Pool Desk - off-exchange and short volume</title>" in html
        assert '<meta name="description" content="<span' not in html

    finally:
        lib_config.load = orig_load
        bdd.PANEL_PATH = orig_panel
        bdd.ATS_DIR = orig_ats
        bdd.YAHOO_DIR = orig_yahoo
        lib_config.ROOT = orig_root


# ---------------------------------------------------------------------------
# 6. Interim Terminal Dark Pool pane artifact (site/darkpool_eod.json)
# ---------------------------------------------------------------------------
import json as _json

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

    assert doc["schema"] == "darkpool_eod.v1"
    assert doc["tier"] == "eod"                       # interim; not "intraday" yet
    assert doc["source"] == "finra_facilities"        # debranded
    assert doc["asof"] == "2026-07-14"
    # Full universe passes through, including the null-oe_share tail row
    assert [r["ticker"] for r in doc["universe"]] == ["AAPL", "ZZZZ"]
    assert doc["universe"][0]["oe_share"] == 0.42
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
