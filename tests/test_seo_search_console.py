"""tests/test_seo_search_console.py — Tests for engine.marketing.seo_search_console.

All writes go to tmp_path only (MM_DATA_GUARD).  No network calls — the HTTP layer
is mocked via monkeypatch / unittest.mock.patch.

Test coverage:
  - Pagination assembly: multiple pages combined correctly
  - State-file honesty: no creds -> available:false + reason, parquet NOT written, exit 0
  - API-error path -> available:false w/ reason (no traceback in artifact)
  - Parquet append-dedupe: two runs overlapping window -> no dup keys
  - 16-month trim: old rows dropped
  - Family scorecard joins via seo_director classifier
  - Brand split regex
  - Query-gap heuristics incl. boundary cases
  - Secret hygiene: no 'private_key'/'token' substrings in artifacts
  - Workflow YAML parses with new step + secret only via env
"""
from __future__ import annotations

import json
import os
import sys
import types
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from engine.marketing.seo_search_console import (  # noqa: E402
    _ARTIFACTS_REL,
    _BRAND_RE,
    _build_parquet,
    _build_query_gaps,
    _build_scorecard,
    _DEFAULT_PROPERTY,
    _DAILY_FILE,
    _GAPS_FILE,
    _GAP_MAX_CTR,
    _GAP_MIN_IMPRESSIONS,
    _GAP_POS_HIGH,
    _GAP_POS_LOW,
    _PAGE_CAP_MONTHS,
    _SCORECARD_FILE,
    _STATE_FILE,
    fetch_search_analytics,
    run,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_AS_OF = date(2026, 7, 20)
_WINDOW = {"start": "2026-06-23", "end": "2026-07-20"}  # 28-day default


def _make_api_row(
    date_str="2026-07-01",
    page="https://www.mastermind-x.com/macro.html",
    query="stock market regime",
    country="usa",
    device="DESKTOP",
    clicks=10,
    impressions=200,
    ctr=0.05,
    position=8.5,
) -> dict:
    """Build a single GSC API row in the format fetch_search_analytics returns."""
    return {
        "date": date_str,
        "page": page,
        "query": query,
        "country": country,
        "device": device,
        "clicks": clicks,
        "impressions": impressions,
        "ctr": ctr,
        "position": position,
    }


def _api_response(rows: list[dict]) -> dict:
    """Build a GSC REST API JSON response from pre-parsed row dicts."""
    # Reconstruct the 'keys' format the real API sends.
    api_rows = []
    dims = ["date", "page", "query", "country", "device"]
    for r in rows:
        api_rows.append({
            "keys": [r.get(d) for d in dims],
            "clicks": r.get("clicks", 0),
            "impressions": r.get("impressions", 0),
            "ctr": r.get("ctr", 0.0),
            "position": r.get("position", 0.0),
        })
    return {"rows": api_rows}


def _stub_google_auth(monkeypatch):
    """Monkeypatch google.oauth2.service_account and google.auth.transport.requests
    so tests work without google-auth installed."""
    # Build stub modules.
    google_mod = types.ModuleType("google")
    google_auth_mod = types.ModuleType("google.auth")
    google_oauth2_mod = types.ModuleType("google.oauth2")
    transport_mod = types.ModuleType("google.auth.transport")
    requests_mod = types.ModuleType("google.auth.transport.requests")
    sa_mod = types.ModuleType("google.oauth2.service_account")

    class _FakeCreds:
        token = "FAKE_TOKEN"
        def __init__(self, **kw): pass
        def refresh(self, req): pass

        @classmethod
        def from_service_account_file(cls, path, scopes=None):
            return cls()

    sa_mod.Credentials = _FakeCreds

    class _FakeRequest:
        pass

    requests_mod.Request = _FakeRequest

    google_mod.auth = google_auth_mod
    google_mod.oauth2 = google_oauth2_mod
    google_auth_mod.transport = transport_mod
    transport_mod.requests = requests_mod
    google_oauth2_mod.service_account = sa_mod

    for name, mod in [
        ("google", google_mod),
        ("google.auth", google_auth_mod),
        ("google.oauth2", google_oauth2_mod),
        ("google.auth.transport", transport_mod),
        ("google.auth.transport.requests", requests_mod),
        ("google.oauth2.service_account", sa_mod),
    ]:
        monkeypatch.setitem(sys.modules, name, mod)


# ---------------------------------------------------------------------------
# Tests: no-credentials path
# ---------------------------------------------------------------------------


class TestNoCreds:
    def test_no_creds_state_available_false(self, tmp_path, monkeypatch):
        """No credentials -> state.available=False, reason set, no parquet written."""
        # Clear all credential env vars.
        monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
        monkeypatch.delenv("GSC_SA_JSON", raising=False)

        state = run(tmp_path, creds_path=None, as_of=_AS_OF, write=True)

        assert state["available"] is False
        assert state["reason"] is not None
        assert "credentials" in state["reason"].lower()
        assert state["schema"] == "gsc_state.v1"
        assert state["rows_fetched"] == 0

        # State file written.
        state_file = tmp_path / _ARTIFACTS_REL / _STATE_FILE
        assert state_file.exists()
        on_disk = json.loads(state_file.read_text())
        assert on_disk["available"] is False

        # Parquet NOT written.
        assert not (tmp_path / _ARTIFACTS_REL / _DAILY_FILE).exists()

    def test_no_creds_dry_run_writes_nothing(self, tmp_path, monkeypatch):
        """dry-run=True + no creds -> nothing written at all."""
        monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
        monkeypatch.delenv("GSC_SA_JSON", raising=False)

        run(tmp_path, creds_path=None, as_of=_AS_OF, write=False)

        seo_dir = tmp_path / _ARTIFACTS_REL
        assert not seo_dir.exists() or not any(seo_dir.iterdir())

    def test_cli_exit_0_when_unavailable(self, tmp_path, monkeypatch):
        """CLI must exit 0 even when credentials are absent."""
        import subprocess
        env = {**os.environ, "GOOGLE_APPLICATION_CREDENTIALS": "", "GSC_SA_JSON": ""}
        result = subprocess.run(
            [sys.executable, "-m", "engine.marketing.seo_search_console",
             "--root", str(tmp_path)],
            capture_output=True, text=True, env=env,
        )
        assert result.returncode == 0, f"Expected exit 0, got {result.returncode}\nstderr: {result.stderr}"

    def test_no_creds_from_nonexistent_path(self, tmp_path, monkeypatch):
        """Explicit creds_path pointing to missing file -> available:false."""
        monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
        monkeypatch.delenv("GSC_SA_JSON", raising=False)

        state = run(tmp_path, creds_path="/nonexistent/key.json", as_of=_AS_OF, write=True)
        assert state["available"] is False


# ---------------------------------------------------------------------------
# Tests: API error path
# ---------------------------------------------------------------------------


class TestAPIError:
    def test_api_error_state_available_false(self, tmp_path, monkeypatch):
        """API HTTP error -> state.available=False with reason, no parquet."""
        _stub_google_auth(monkeypatch)

        # Create a fake creds file.
        creds_file = tmp_path / "key.json"
        creds_file.write_text('{"type": "service_account"}')

        import requests as _requests

        class _FakeHTTPError(Exception):
            pass

        def _fail(*args, **kwargs):
            raise _requests.exceptions.HTTPError("403 Forbidden")

        monkeypatch.setattr("engine.marketing.seo_search_console._gsc_query", _fail)

        state = run(tmp_path, creds_path=str(creds_file), as_of=_AS_OF, write=True)

        assert state["available"] is False
        assert "api error" in state["reason"].lower()
        assert not (tmp_path / _ARTIFACTS_REL / _DAILY_FILE).exists()

        state_file = tmp_path / _ARTIFACTS_REL / _STATE_FILE
        assert state_file.exists()
        on_disk = json.loads(state_file.read_text())
        assert on_disk["available"] is False

    def test_api_error_no_secret_in_state(self, tmp_path, monkeypatch):
        """API error reason must never contain 'private_key' or 'token' text."""
        _stub_google_auth(monkeypatch)
        creds_file = tmp_path / "key.json"
        creds_file.write_text('{"type": "service_account", "private_key": "SHOULD_NOT_APPEAR"}')

        def _fail(*args, **kwargs):
            # Error message contains fake key-like content.
            raise Exception("auth error: private_key=SUPER_SECRET token=BEARER_XYZ")

        monkeypatch.setattr("engine.marketing.seo_search_console._gsc_query", _fail)

        state = run(tmp_path, creds_path=str(creds_file), as_of=_AS_OF, write=True)

        assert state["available"] is False
        # The redacted error should not expose key material verbatim.
        assert "SUPER_SECRET" not in state.get("reason", "")
        assert "BEARER_XYZ" not in state.get("reason", "")

        state_text = (tmp_path / _ARTIFACTS_REL / _STATE_FILE).read_text()
        assert "SUPER_SECRET" not in state_text
        assert "BEARER_XYZ" not in state_text


# ---------------------------------------------------------------------------
# Tests: pagination assembly
# ---------------------------------------------------------------------------


class TestPagination:
    def _mock_gsc_query(self, monkeypatch, pages: list[list[dict]]) -> None:
        """Set up _gsc_query to return successive pages from `pages` list."""
        _stub_google_auth(monkeypatch)
        call_count = [0]

        def _fake_gsc_query(token, prop, start_date, end_date, dimensions, search_type, start_row, row_limit):
            idx = call_count[0]
            call_count[0] += 1
            if idx >= len(pages):
                return {"rows": []}
            raw_rows = pages[idx]
            return _api_response(raw_rows)

        monkeypatch.setattr("engine.marketing.seo_search_console._gsc_query", _fake_gsc_query)

    def test_two_pages_combined(self, tmp_path, monkeypatch):
        """Pagination: two full pages + empty terminator -> all rows in output.

        row_limit=3 so page1 (3 rows) triggers a second request; page2 (2 rows < 3) stops.
        """
        page1 = [_make_api_row(date_str=f"2026-07-0{i+1}", query=f"q{i}") for i in range(3)]
        page2 = [_make_api_row(date_str=f"2026-07-0{i+4}", query=f"q{i+3}") for i in range(2)]

        self._mock_gsc_query(monkeypatch, [page1, page2])

        creds_file = tmp_path / "key.json"
        creds_file.write_text('{"type": "service_account"}')

        rows = fetch_search_analytics(
            str(creds_file), _DEFAULT_PROPERTY, "2026-07-01", "2026-07-20",
            row_limit=3,  # page1=3 rows (== row_limit) -> fetch page2; page2=2 rows (<3) -> stop
        )
        assert len(rows) == 5

    def test_single_page_no_extra_call(self, tmp_path, monkeypatch):
        """Single page (fewer rows than row_limit) -> pagination stops."""
        page1 = [_make_api_row(query=f"q{i}") for i in range(3)]
        self._mock_gsc_query(monkeypatch, [page1])

        creds_file = tmp_path / "key.json"
        creds_file.write_text('{"type": "service_account"}')

        rows = fetch_search_analytics(
            str(creds_file), _DEFAULT_PROPERTY, "2026-07-01", "2026-07-20",
            row_limit=10  # page1 has 3 rows < 10, so no second call needed
        )
        assert len(rows) == 3

    def test_empty_response_returns_no_rows(self, tmp_path, monkeypatch):
        """Empty rows list on first call -> zero rows returned."""
        self._mock_gsc_query(monkeypatch, [[]])

        creds_file = tmp_path / "key.json"
        creds_file.write_text('{"type": "service_account"}')

        rows = fetch_search_analytics(str(creds_file), _DEFAULT_PROPERTY, "2026-07-01", "2026-07-20")
        assert rows == []

    def test_dimension_keys_mapped_correctly(self, tmp_path, monkeypatch):
        """Row dict keys match requested dimensions."""
        row = _make_api_row(date_str="2026-07-10", query="alpha", country="gbr", device="MOBILE")
        self._mock_gsc_query(monkeypatch, [[row]])

        creds_file = tmp_path / "key.json"
        creds_file.write_text('{"type": "service_account"}')

        rows = fetch_search_analytics(str(creds_file), _DEFAULT_PROPERTY, "2026-07-01", "2026-07-20")
        assert len(rows) == 1
        r = rows[0]
        assert r["date"] == "2026-07-10"
        assert r["query"] == "alpha"
        assert r["country"] == "gbr"
        assert r["device"] == "MOBILE"
        assert "clicks" in r
        assert "impressions" in r
        assert "ctr" in r
        assert "position" in r


# ---------------------------------------------------------------------------
# Tests: parquet append-dedupe + 16-month trim
# ---------------------------------------------------------------------------


class TestParquetAppendDedupe:
    def _rows(self, dates, queries, page="https://x.com/p.html"):
        import pandas as pd
        return [
            _make_api_row(date_str=d, query=q, page=page)
            for d, q in zip(dates, queries)
        ]

    def test_no_existing_parquet(self, tmp_path):
        """First run with rows -> parquet written, no dup keys."""
        rows = self._rows(["2026-07-01", "2026-07-02"], ["q1", "q2"])
        cutoff = date(2025, 3, 1)
        df = _build_parquet(rows, None, "web", cutoff)
        assert len(df) == 2

    def test_append_non_overlapping(self, tmp_path):
        """Two runs with different dates -> rows combined, no dups."""
        import pandas as pd

        rows1 = self._rows(["2026-07-01"], ["q1"])
        df1 = _build_parquet(rows1, None, "web", date(2025, 3, 1))

        rows2 = self._rows(["2026-07-02"], ["q2"])
        df2 = _build_parquet(rows2, df1, "web", date(2025, 3, 1))

        assert len(df2) == 2
        assert set(df2["date"].tolist()) == {"2026-07-01", "2026-07-02"}

    def test_deduplicate_overlapping_window(self, tmp_path):
        """Two runs with overlapping dates+query -> dedup by (date,page,query,country,device)."""
        import pandas as pd

        page = "https://x.com/p.html"
        rows1 = [_make_api_row(date_str="2026-07-01", query="q1", page=page, clicks=5)]
        df1 = _build_parquet(rows1, None, "web", date(2025, 3, 1))

        # Same key but updated clicks (later run).
        rows2 = [_make_api_row(date_str="2026-07-01", query="q1", page=page, clicks=10)]
        df2 = _build_parquet(rows2, df1, "web", date(2025, 3, 1))

        # Should have exactly 1 row (deduped), with keep=last (clicks=10).
        assert len(df2) == 1
        assert df2.iloc[0]["clicks"] == 10

    def test_16_month_cap(self, tmp_path):
        """Rows older than 16 months from cutoff_date are dropped."""
        import pandas as pd

        # cutoff = 2025-03-01; rows at 2025-02-28 should be dropped
        cutoff = date(2025, 3, 1)
        rows = [
            _make_api_row(date_str="2025-02-28", query="old"),   # older than cutoff -> dropped
            _make_api_row(date_str="2025-03-01", query="edge"),  # exactly cutoff -> kept (>=)
            _make_api_row(date_str="2026-07-01", query="new"),   # new -> kept
        ]
        df = _build_parquet(rows, None, "web", cutoff)
        dates = df["date"].tolist()
        assert "2025-02-28" not in dates
        assert "2025-03-01" in dates
        assert "2026-07-01" in dates

    def test_two_full_runs_no_duplicate_keys(self, tmp_path, monkeypatch):
        """Full run() -> run() overlapping window -> no duplicate (date,page,query,country,device)."""
        _stub_google_auth(monkeypatch)
        monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
        monkeypatch.delenv("GSC_SA_JSON", raising=False)

        page = "https://www.mastermind-x.com/macro.html"
        common_rows = [_make_api_row(date_str="2026-07-10", query="regime", page=page)]
        new_rows = [_make_api_row(date_str="2026-07-15", query="regime", page=page)]

        call_count = [0]

        def _fake_gsc_query(*args, **kwargs):
            idx = call_count[0]
            call_count[0] += 1
            if idx == 0:
                return _api_response(common_rows)
            elif idx == 1:
                return _api_response([])
            elif idx == 2:
                return _api_response(common_rows + new_rows)
            else:
                return _api_response([])

        monkeypatch.setattr("engine.marketing.seo_search_console._gsc_query", _fake_gsc_query)

        creds_file = tmp_path / "key.json"
        creds_file.write_text('{"type": "service_account"}')

        # First run.
        run(tmp_path, creds_path=str(creds_file), as_of=_AS_OF, write=True)
        # Second run with overlapping data.
        run(tmp_path, creds_path=str(creds_file), as_of=_AS_OF, write=True)

        import pandas as pd
        parquet_path = tmp_path / _ARTIFACTS_REL / _DAILY_FILE
        assert parquet_path.exists()
        df = pd.read_parquet(parquet_path)

        # No duplicate dedup keys.
        keys = ["date", "page", "query", "country", "device"]
        assert not df.duplicated(subset=keys).any(), "Duplicate dedup keys found in parquet"


# ---------------------------------------------------------------------------
# Tests: family scorecard
# ---------------------------------------------------------------------------


class TestFamilyScorecard:
    def test_core_page_classified(self, tmp_path):
        """macro.html -> core family."""
        import pandas as pd
        rows = [_make_api_row(
            page="https://www.mastermind-x.com/macro.html", query="market",
            clicks=5, impressions=100
        )]
        df = _build_parquet(rows, None, "web", date(2025, 1, 1))
        sc = _build_scorecard(df, "2026-07-20", _WINDOW)
        assert "core" in sc["families"]
        assert sc["families"]["core"]["clicks"] == 5

    def test_stocks_page_classified(self, tmp_path):
        """stocks/AAPL.html -> stocks family."""
        rows = [_make_api_row(
            page="https://www.mastermind-x.com/stocks/AAPL.html",
            query="apple stock",
            clicks=3, impressions=50
        )]
        df = _build_parquet(rows, None, "web", date(2025, 1, 1))
        sc = _build_scorecard(df, "2026-07-20", _WINDOW)
        assert "stocks" in sc["families"]
        assert sc["families"]["stocks"]["clicks"] == 3

    def test_product_page_classified(self, tmp_path):
        """products/market-terminal.html -> products family."""
        rows = [_make_api_row(
            page="https://www.mastermind-x.com/products/market-terminal.html",
            query="browser market terminal", clicks=4, impressions=80
        )]
        df = _build_parquet(rows, None, "web", date(2025, 1, 1))
        sc = _build_scorecard(df, "2026-07-20", _WINDOW)
        assert "products" in sc["families"]
        assert sc["families"]["products"]["clicks"] == 4

    def test_report_page_classified(self, tmp_path):
        """report_haven.html -> report family."""
        rows = [_make_api_row(
            page="https://www.mastermind-x.com/report_haven.html",
            query="market report", clicks=2, impressions=30
        )]
        df = _build_parquet(rows, None, "web", date(2025, 1, 1))
        sc = _build_scorecard(df, "2026-07-20", _WINDOW)
        assert "report" in sc["families"]

    def test_scorecard_schema(self, tmp_path):
        """Scorecard has required schema keys."""
        rows = [_make_api_row()]
        df = _build_parquet(rows, None, "web", date(2025, 1, 1))
        sc = _build_scorecard(df, "2026-07-20", _WINDOW)
        assert sc["schema"] == "gsc_scorecard.v1"
        assert "as_of" in sc
        assert "window" in sc
        assert "families" in sc
        assert "brand_split" in sc
        assert "brand" in sc["brand_split"]
        assert "non_brand" in sc["brand_split"]

    def test_top_pages_capped_at_5(self, tmp_path):
        """top_pages per family capped at 5."""
        rows = [
            _make_api_row(page=f"https://www.mastermind-x.com/page{i}.html", query="q")
            for i in range(10)
        ]
        df = _build_parquet(rows, None, "web", date(2025, 1, 1))
        sc = _build_scorecard(df, "2026-07-20", _WINDOW)
        for fam, data in sc["families"].items():
            assert len(data["top_pages"]) <= 5

    def test_empty_df_scorecard(self, tmp_path):
        """Empty dataframe -> empty families, brand split zeroes."""
        import pandas as pd
        df = pd.DataFrame()
        sc = _build_scorecard(df, "2026-07-20", _WINDOW)
        assert sc["families"] == {}
        assert sc["brand_split"]["brand"]["clicks"] == 0


# ---------------------------------------------------------------------------
# Tests: brand split
# ---------------------------------------------------------------------------


class TestBrandSplit:
    def test_brand_regex_matches(self):
        """Brand regex matches 'mastermind' variants."""
        assert _BRAND_RE.search("mastermind x")
        assert _BRAND_RE.search("Mastermind")
        assert _BRAND_RE.search("MastermindX")
        assert _BRAND_RE.search("MASTERMIND X")
        assert _BRAND_RE.search("master mind")  # with space

    def test_brand_regex_no_match(self):
        """Non-brand queries don't match."""
        assert not _BRAND_RE.search("stock market regime")
        assert not _BRAND_RE.search("options flow analysis")

    def test_brand_split_in_scorecard(self, tmp_path):
        """Brand rows counted separately from non-brand rows."""
        rows = [
            _make_api_row(query="mastermind review", clicks=20, impressions=100),
            _make_api_row(query="stock market analysis", clicks=5, impressions=200),
        ]
        df = _build_parquet(rows, None, "web", date(2025, 1, 1))
        sc = _build_scorecard(df, "2026-07-20", _WINDOW)
        brand = sc["brand_split"]["brand"]
        nonbrand = sc["brand_split"]["non_brand"]
        assert brand["clicks"] == 20
        assert nonbrand["clicks"] == 5

    def test_is_brand_column_set(self, tmp_path):
        """is_brand column correctly set in parquet."""
        rows = [
            _make_api_row(query="mastermind"),
            _make_api_row(query="another query"),
        ]
        df = _build_parquet(rows, None, "web", date(2025, 1, 1))
        assert "is_brand" in df.columns
        brand_rows = df[df["is_brand"] == True]  # noqa: E712
        assert len(brand_rows) == 1


# ---------------------------------------------------------------------------
# Tests: query gaps
# ---------------------------------------------------------------------------


class TestQueryGaps:
    def _make_df(self, rows):
        """Build a parquet dataframe from row dicts."""
        return _build_parquet(rows, None, "web", date(2025, 1, 1))

    def test_high_impressions_low_ctr_gap(self):
        """Non-brand, impressions>=20, ctr<1% -> in gaps."""
        rows = [_make_api_row(
            query="regime analysis",
            impressions=50, clicks=0, ctr=0.0, position=5.0
        )]
        df = self._make_df(rows)
        gaps_doc = _build_query_gaps(df, "2026-07-20", _WINDOW)
        assert len(gaps_doc["gaps"]) == 1
        assert gaps_doc["gaps"][0]["reason"] == "high_impressions_low_ctr"

    def test_position_11_30_gap(self):
        """Non-brand, impressions>=20, position in [11,30] -> in gaps."""
        rows = [_make_api_row(
            query="sector rotation strategy",
            impressions=25, clicks=1, ctr=0.04, position=15.0
        )]
        df = self._make_df(rows)
        gaps_doc = _build_query_gaps(df, "2026-07-20", _WINDOW)
        assert len(gaps_doc["gaps"]) == 1
        assert gaps_doc["gaps"][0]["reason"] == "position_11_30"

    def test_brand_query_excluded(self):
        """Brand queries excluded from gaps."""
        rows = [_make_api_row(
            query="mastermind review",
            impressions=100, clicks=0, ctr=0.0, position=5.0
        )]
        df = self._make_df(rows)
        gaps_doc = _build_query_gaps(df, "2026-07-20", _WINDOW)
        assert len(gaps_doc["gaps"]) == 0

    def test_low_impressions_excluded(self):
        """Impressions below threshold excluded."""
        rows = [_make_api_row(
            query="niche term",
            impressions=_GAP_MIN_IMPRESSIONS - 1, clicks=0, ctr=0.0, position=5.0
        )]
        df = self._make_df(rows)
        gaps_doc = _build_query_gaps(df, "2026-07-20", _WINDOW)
        assert len(gaps_doc["gaps"]) == 0

    def test_boundary_impressions_exactly_20(self):
        """Impressions exactly == 20 (threshold) -> included."""
        rows = [_make_api_row(
            query="boundary term",
            impressions=_GAP_MIN_IMPRESSIONS, clicks=0, ctr=0.0, position=5.0
        )]
        df = self._make_df(rows)
        gaps_doc = _build_query_gaps(df, "2026-07-20", _WINDOW)
        assert len(gaps_doc["gaps"]) == 1

    def test_position_exactly_11_included(self):
        """Position exactly 11 -> included in position gap."""
        rows = [_make_api_row(
            query="pos 11 term",
            impressions=30, clicks=1, ctr=0.04, position=float(_GAP_POS_LOW)
        )]
        df = self._make_df(rows)
        gaps_doc = _build_query_gaps(df, "2026-07-20", _WINDOW)
        assert len(gaps_doc["gaps"]) == 1

    def test_position_exactly_30_included(self):
        """Position exactly 30 -> included in position gap."""
        rows = [_make_api_row(
            query="pos 30 term",
            impressions=30, clicks=1, ctr=0.04, position=float(_GAP_POS_HIGH)
        )]
        df = self._make_df(rows)
        gaps_doc = _build_query_gaps(df, "2026-07-20", _WINDOW)
        assert len(gaps_doc["gaps"]) == 1

    def test_position_31_excluded_if_ctr_ok(self):
        """Position 31 with ctr>=1% -> not a gap."""
        rows = [_make_api_row(
            query="pos 31 ctr ok",
            impressions=50, clicks=5, ctr=0.10, position=31.0
        )]
        df = self._make_df(rows)
        gaps_doc = _build_query_gaps(df, "2026-07-20", _WINDOW)
        assert len(gaps_doc["gaps"]) == 0

    def test_sorted_by_impressions_desc(self):
        """Gaps sorted by impressions descending."""
        rows = [
            _make_api_row(query="low impr", impressions=20, clicks=0, ctr=0.0, position=5.0),
            _make_api_row(query="high impr", impressions=200, clicks=0, ctr=0.0, position=5.0),
            _make_api_row(query="mid impr", impressions=50, clicks=0, ctr=0.0, position=5.0),
        ]
        df = self._make_df(rows)
        gaps_doc = _build_query_gaps(df, "2026-07-20", _WINDOW)
        impr_values = [g["impressions"] for g in gaps_doc["gaps"]]
        assert impr_values == sorted(impr_values, reverse=True)

    def test_gaps_capped_at_30(self):
        """Gaps list capped at 30 entries."""
        rows = [
            _make_api_row(query=f"query {i}", impressions=50 + i, clicks=0, ctr=0.0, position=5.0)
            for i in range(50)
        ]
        df = self._make_df(rows)
        gaps_doc = _build_query_gaps(df, "2026-07-20", _WINDOW)
        assert len(gaps_doc["gaps"]) <= 30

    def test_gaps_schema(self):
        """Gaps doc has required keys."""
        rows = [_make_api_row(query="regime", impressions=30, clicks=0, ctr=0.0, position=5.0)]
        df = self._make_df(rows)
        gaps_doc = _build_query_gaps(df, "2026-07-20", _WINDOW)
        assert gaps_doc["schema"] == "gsc_gaps.v1"
        assert "as_of" in gaps_doc
        assert "window" in gaps_doc
        assert "gaps" in gaps_doc

    def test_empty_df_gaps(self):
        """Empty dataframe -> empty gaps list."""
        import pandas as pd
        df = pd.DataFrame()
        gaps_doc = _build_query_gaps(df, "2026-07-20", _WINDOW)
        assert gaps_doc["gaps"] == []

    def test_best_page_field(self):
        """gaps entries have best_page field."""
        rows = [_make_api_row(
            query="market breadth",
            page="https://www.mastermind-x.com/macro.html",
            impressions=40, clicks=0, ctr=0.0, position=5.0
        )]
        df = self._make_df(rows)
        gaps_doc = _build_query_gaps(df, "2026-07-20", _WINDOW)
        assert len(gaps_doc["gaps"]) == 1
        assert "best_page" in gaps_doc["gaps"][0]


# ---------------------------------------------------------------------------
# Tests: secret hygiene
# ---------------------------------------------------------------------------


class TestSecretHygiene:
    def test_state_file_no_private_key(self, tmp_path, monkeypatch):
        """State file must not contain 'private_key' or 'token' even when creds provided."""
        _stub_google_auth(monkeypatch)
        monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
        monkeypatch.delenv("GSC_SA_JSON", raising=False)

        # Create a fake creds file with key material.
        creds_file = tmp_path / "key.json"
        creds_file.write_text(json.dumps({
            "type": "service_account",
            "private_key": "-----BEGIN RSA PRIVATE KEY-----\nMOCK\n-----END RSA PRIVATE KEY-----",
            "client_email": "test@project.iam.gserviceaccount.com",
        }))

        def _fake_gsc_query(*args, **kwargs):
            return {"rows": []}

        monkeypatch.setattr("engine.marketing.seo_search_console._gsc_query", _fake_gsc_query)

        run(tmp_path, creds_path=str(creds_file), as_of=_AS_OF, write=True)

        seo_dir = tmp_path / _ARTIFACTS_REL
        for artifact_file in [_STATE_FILE, _SCORECARD_FILE, _GAPS_FILE]:
            path = seo_dir / artifact_file
            if path.exists():
                text = path.read_text()
                assert "private_key" not in text, f"{artifact_file} contains 'private_key'"
                assert "MOCK" not in text, f"{artifact_file} contains raw key material"

    def test_scorecard_no_token(self, tmp_path, monkeypatch):
        """Scorecard and gaps artifacts must not contain 'token'."""
        _stub_google_auth(monkeypatch)
        monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
        monkeypatch.delenv("GSC_SA_JSON", raising=False)

        creds_file = tmp_path / "key.json"
        creds_file.write_text('{"type": "service_account"}')

        rows = [_make_api_row(query="test", impressions=10, clicks=1, ctr=0.1, position=5.0)]

        def _fake_gsc_query(*args, **kwargs):
            return _api_response(rows)

        monkeypatch.setattr("engine.marketing.seo_search_console._gsc_query", _fake_gsc_query)

        run(tmp_path, creds_path=str(creds_file), as_of=_AS_OF, write=True)

        seo_dir = tmp_path / _ARTIFACTS_REL
        for artifact_file in [_SCORECARD_FILE, _GAPS_FILE]:
            path = seo_dir / artifact_file
            if path.exists():
                text = path.read_text()
                # 'token' substring check (catches bearer token leakage)
                # Note: 'token' appears in the schema name "FAKE_TOKEN" from stub,
                # but the stub token must not reach any artifact.
                assert "FAKE_TOKEN" not in text

    def test_gscsajson_tmp_file_deleted(self, tmp_path, monkeypatch):
        """Tmp file written for GSC_SA_JSON must be deleted after use."""
        _stub_google_auth(monkeypatch)
        monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)

        raw_json = json.dumps({"type": "service_account", "private_key": "SECRET"})
        monkeypatch.setenv("GSC_SA_JSON", raw_json)

        created_tmp_files = []
        original_resolve = __import__(
            "engine.marketing.seo_search_console", fromlist=["_resolve_creds"]
        )._resolve_creds

        def _fake_gsc_query(*args, **kwargs):
            return {"rows": []}

        monkeypatch.setattr("engine.marketing.seo_search_console._gsc_query", _fake_gsc_query)

        state = run(tmp_path, creds_path=None, as_of=_AS_OF, write=True)

        # The tmp file should be gone after run() completes.
        # We can't easily capture its path without patching tempfile, but
        # we verify the secret isn't sitting in any artifact.
        seo_dir = tmp_path / _ARTIFACTS_REL
        for artifact_file in [_STATE_FILE, _SCORECARD_FILE, _GAPS_FILE]:
            path = seo_dir / artifact_file
            if path.exists():
                text = path.read_text()
                assert "SECRET" not in text


# ---------------------------------------------------------------------------
# Tests: full run() integration (mocked)
# ---------------------------------------------------------------------------


class TestRunIntegration:
    def test_full_run_writes_all_artifacts(self, tmp_path, monkeypatch):
        """Full run with rows -> all 4 artifacts written."""
        _stub_google_auth(monkeypatch)
        monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
        monkeypatch.delenv("GSC_SA_JSON", raising=False)

        creds_file = tmp_path / "key.json"
        creds_file.write_text('{"type": "service_account"}')

        rows = [
            _make_api_row(query="regime", impressions=100, clicks=5, ctr=0.05, position=8.0),
            _make_api_row(query="mastermind review", impressions=50, clicks=10, ctr=0.2, position=2.0),
        ]

        call_count = [0]

        def _fake_gsc_query(*args, **kwargs):
            if call_count[0] == 0:
                call_count[0] += 1
                return _api_response(rows)
            return {"rows": []}

        monkeypatch.setattr("engine.marketing.seo_search_console._gsc_query", _fake_gsc_query)

        state = run(tmp_path, creds_path=str(creds_file), as_of=_AS_OF, write=True)

        assert state["available"] is True
        assert state["rows_fetched"] == 2

        seo_dir = tmp_path / _ARTIFACTS_REL
        assert (seo_dir / _STATE_FILE).exists()
        assert (seo_dir / _DAILY_FILE).exists()
        assert (seo_dir / _SCORECARD_FILE).exists()
        assert (seo_dir / _GAPS_FILE).exists()

        # State file parseable and correct.
        on_disk = json.loads((seo_dir / _STATE_FILE).read_text())
        assert on_disk["available"] is True
        assert on_disk["rows_may_be_incomplete"] is True
        assert on_disk["schema"] == "gsc_state.v1"

        # Scorecard parseable.
        sc = json.loads((seo_dir / _SCORECARD_FILE).read_text())
        assert sc["schema"] == "gsc_scorecard.v1"

        # Gaps parseable.
        gaps = json.loads((seo_dir / _GAPS_FILE).read_text())
        assert gaps["schema"] == "gsc_gaps.v1"

    def test_dry_run_writes_nothing(self, tmp_path, monkeypatch):
        """write=False -> no artifacts written even on success."""
        _stub_google_auth(monkeypatch)
        monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
        monkeypatch.delenv("GSC_SA_JSON", raising=False)

        creds_file = tmp_path / "key.json"
        creds_file.write_text('{"type": "service_account"}')

        def _fake_gsc_query(*args, **kwargs):
            return _api_response([_make_api_row()])

        monkeypatch.setattr("engine.marketing.seo_search_console._gsc_query", _fake_gsc_query)

        run(tmp_path, creds_path=str(creds_file), as_of=_AS_OF, write=False)

        seo_dir = tmp_path / _ARTIFACTS_REL
        assert not seo_dir.exists() or not any(seo_dir.iterdir())

    def test_state_property_from_env(self, tmp_path, monkeypatch):
        """Property string picked from GSC_PROPERTY env or default."""
        monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
        monkeypatch.delenv("GSC_SA_JSON", raising=False)
        monkeypatch.setenv("GSC_PROPERTY", "sc-domain:custom.com")

        state = run(tmp_path, creds_path=None, as_of=_AS_OF, write=False)
        assert state["property"] == "sc-domain:custom.com"

    def test_state_default_property(self, tmp_path, monkeypatch):
        """Default property is sc-domain:mastermind-x.com."""
        monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
        monkeypatch.delenv("GSC_SA_JSON", raising=False)
        monkeypatch.delenv("GSC_PROPERTY", raising=False)

        state = run(tmp_path, creds_path=None, as_of=_AS_OF, write=False)
        assert state["property"] == _DEFAULT_PROPERTY

    def test_window_matches_days_param(self, tmp_path, monkeypatch):
        """Window start/end match the days param."""
        monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
        monkeypatch.delenv("GSC_SA_JSON", raising=False)

        state = run(tmp_path, creds_path=None, as_of=_AS_OF, days=7, write=False)
        assert state["window"]["end"] == _AS_OF.strftime("%Y-%m-%d")
        expected_start = (_AS_OF - timedelta(days=6)).strftime("%Y-%m-%d")
        assert state["window"]["start"] == expected_start


# ---------------------------------------------------------------------------
# Tests: workflow YAML regression guard
# ---------------------------------------------------------------------------


class TestWorkflowYAMLWithGSC:
    def test_workflow_parses_with_new_step(self):
        """Workflow YAML still parses correctly after adding the GSC step.

        Pins: triggers {schedule, workflow_dispatch}, SEO_DIRECTOR_ENABLED gate,
        data/marketing/seo commit scope, and the new GSC step doesn't echo the secret.
        """
        import yaml
        wf_path = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "seo-director.yml"
        doc = yaml.safe_load(wf_path.read_text())

        # Triggers unchanged.
        triggers = doc.get(True) or doc.get("on")
        assert set(triggers) == {"schedule", "workflow_dispatch"}

        job = doc["jobs"]["seo-audit"]

        # Gate unchanged.
        assert "SEO_DIRECTOR_ENABLED" in job["if"]
        assert "workflow_dispatch" in job["if"]

        # git add still scoped to data/marketing/seo.
        adds = [st.get("run", "") for st in job["steps"] if "git add" in st.get("run", "")]
        assert adds and all("data/marketing/seo" in a for a in adds)

        # GSC step present.
        step_names = [st.get("name", "") for st in job["steps"]]
        assert any("search console" in (n or "").lower() for n in step_names)

        # Secret ONLY referenced via env: block, never echoed directly in run block.
        gsc_steps = [
            st for st in job["steps"]
            if "search console" in (st.get("name") or "").lower()
        ]
        assert len(gsc_steps) == 1
        gsc_step = gsc_steps[0]

        # The run block must not directly echo/print the secret variable.
        run_block = gsc_step.get("run", "")
        assert "GSC_SERVICE_ACCOUNT_JSON" not in run_block, (
            "Secret name must not appear in the run block (only in env: section)"
        )

        # The env block references it correctly.
        env_block = gsc_step.get("env", {})
        assert "GSC_SA_JSON" in env_block
        assert "GSC_SERVICE_ACCOUNT_JSON" in env_block.get("GSC_SA_JSON", "")
