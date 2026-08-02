"""tests/test_seo_search_console.py — Tests for engine.marketing.seo_search_console.

All writes go to tmp_path only (MM_DATA_GUARD).  No network calls — the HTTP layer
is mocked via monkeypatch / unittest.mock.patch.

Test coverage:
  - Pagination assembly: multiple pages combined correctly
  - State-file honesty: no creds -> available:false + reason, parquet NOT written, exit 0
  - API-error path -> available:false w/ reason (no traceback in artifact)
  - Credential loading: a DOUBLE-encoded secret loads (the operator's real bug);
    triple-encoded / garbage / missing-keys produce precise NAMED errors
  - 403 / 404 produce their distinct actionable reasons + GitHub annotations
  - Parquet append-dedupe: two runs overlapping window -> no dup keys
  - 16-month trim: old rows dropped
  - Family scorecard joins via seo_director classifier
  - Brand split regex
  - Query-gap heuristics incl. boundary cases
  - Sitemap + URL-inspection parsing over real-shaped API payloads
  - One URL failing mid-sweep does not abort the others
  - Secret hygiene: the private key never appears in ANY emitted string
  - Annotation compliance asserted via capsys with line.startswith("::")
  - Workflow YAML parses with new step + secret only via env
"""
from __future__ import annotations

import json
import os
import re
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
    _core_inspect_urls,
    _DEFAULT_PROPERTY,
    _DAILY_FILE,
    _describe_shape,
    _emit_index_annotations,
    _GAPS_FILE,
    _GAP_MAX_CTR,
    _GAP_MIN_IMPRESSIONS,
    _GAP_POS_HIGH,
    _GAP_POS_LOW,
    _INDEX_STATUS_FILE,
    _MAX_INSPECT_URLS,
    _PAGE_CAP_MONTHS,
    _parse_sa_json,
    _print_index_summary,
    _SCORECARD_FILE,
    _STATE_FILE,
    _validate_sa_info,
    collect_index_status,
    fetch_search_analytics,
    fetch_sitemaps,
    GscApiError,
    inspect_urls,
    load_sa_info,
    run,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_AS_OF = date(2026, 7, 20)
_WINDOW = {"start": "2026-06-23", "end": "2026-07-20"}  # 28-day default

#: The exact private-key body that must never appear in ANY string this module
#: emits — reason, artifact, stdout, log record.
_PRIVATE_KEY = (
    "-----BEGIN PRIVATE KEY-----\n"
    "MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjNEVER_LEAK_THIS_STRING\n"
    "-----END PRIVATE KEY-----\n"
)
_CLIENT_EMAIL = "mastermindx@mastermindx-503122.iam.gserviceaccount.com"


def _sa_info(**over) -> dict:
    """A realistically shaped, valid service-account blob."""
    info = {
        "type": "service_account",
        "project_id": "mastermindx-503122",
        "private_key_id": "0123456789abcdef0123456789abcdef01234567",
        "private_key": _PRIVATE_KEY,
        "client_email": _CLIENT_EMAIL,
        "client_id": "109876543210987654321",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url":
            "https://www.googleapis.com/oauth2/v1/certs",
        "client_x509_cert_url":
            "https://www.googleapis.com/robot/v1/metadata/x509/mastermindx",
    }
    info.update(over)
    return info


def _write_creds(tmp_path: Path, name: str = "key.json", **over) -> Path:
    """Write a VALID service-account key file and return its path."""
    p = tmp_path / name
    p.write_text(json.dumps(_sa_info(**over)), encoding="utf-8")
    return p


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

        @classmethod
        def from_service_account_info(cls, info, scopes=None):
            # Mirror google-auth's real contract: it calls .keys() on the arg.
            # A str here is exactly the operator's production crash.
            info.keys()
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
# Network lockout + realistic API payload fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _no_live_calls(monkeypatch):
    """No test in this module may reach the network.

    The two index-diagnostics HTTP seams are replaced with hard failures by
    default, so a test that forgets to stub them fails soft through the adapter
    rather than quietly calling googleapis.com.  Pacing sleeps are neutralised
    so the 12-URL sweep costs nothing.
    """
    def _blocked(*_a, **_kw):
        raise GscApiError(503, "no network in tests")

    monkeypatch.setattr(
        "engine.marketing.seo_search_console._sitemaps_get", _blocked)
    monkeypatch.setattr(
        "engine.marketing.seo_search_console._inspect_post", _blocked)
    monkeypatch.setattr("engine.marketing.seo_search_console.time.sleep",
                        lambda *_a, **_kw: None)


def _sitemaps_payload() -> dict:
    """A real-shaped webmasters/v3 sitemaps.list response.

    Counts arrive as STRINGS (int64 over JSON) — that is not a typo.
    """
    return {
        "sitemap": [
            {
                "path": "https://www.mastermind-x.com/sitemap.xml",
                "lastSubmitted": "2026-07-22T09:14:11.000Z",
                "lastDownloaded": "2026-07-23T04:02:55.000Z",
                "isPending": False,
                "isSitemapsIndex": False,
                "type": "sitemap",
                "warnings": "3",
                "errors": "0",
                "contents": [
                    {"type": "web", "submitted": "2219", "indexed": "0"},
                ],
            },
            {
                "path": "https://www.mastermind-x.com/news-sitemap.xml",
                "lastSubmitted": "2026-07-22T09:14:12.000Z",
                # No lastDownloaded at all — Google has NEVER fetched it.
                "isPending": True,
                "isSitemapsIndex": False,
                "type": "sitemap",
                "warnings": "0",
                "errors": "0",
                "contents": [
                    {"type": "web", "submitted": "40", "indexed": "0"},
                ],
            },
        ]
    }


def _inspect_payload(
    *,
    verdict="PASS",
    coverage="Submitted and indexed",
    last_crawl="2026-07-19T11:22:33Z",
    fetch_state="SUCCESSFUL",
    url="https://www.mastermind-x.com/",
) -> dict:
    """A real-shaped urlInspection/index:inspect response."""
    return {
        "inspectionResult": {
            "inspectionResultLink": (
                "https://search.google.com/search-console/inspect"
                "?resource_id=sc-domain%3Amastermind-x.com&id=abc123"
            ),
            "indexStatusResult": {
                "sitemap": ["https://www.mastermind-x.com/sitemap.xml"],
                "verdict": verdict,
                "coverageState": coverage,
                "robotsTxtState": "ALLOWED",
                "indexingState": "INDEXING_ALLOWED",
                "lastCrawlTime": last_crawl,
                "pageFetchState": fetch_state,
                "googleCanonical": url,
                "userCanonical": url,
                "crawledAs": "MOBILE",
            },
            "mobileUsabilityResult": {"verdict": "VERDICT_UNSPECIFIED"},
        }
    }


def _annotation_lines(captured: str) -> list[str]:
    """Only the lines GitHub would actually parse: '::' at column 0."""
    return [ln for ln in captured.splitlines() if ln.startswith("::")]


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
        creds_file = _write_creds(tmp_path)

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
        creds_file = _write_creds(tmp_path)

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

        creds_file = _write_creds(tmp_path)

        rows = fetch_search_analytics(
            str(creds_file), _DEFAULT_PROPERTY, "2026-07-01", "2026-07-20",
            row_limit=3,  # page1=3 rows (== row_limit) -> fetch page2; page2=2 rows (<3) -> stop
        )
        assert len(rows) == 5

    def test_single_page_no_extra_call(self, tmp_path, monkeypatch):
        """Single page (fewer rows than row_limit) -> pagination stops."""
        page1 = [_make_api_row(query=f"q{i}") for i in range(3)]
        self._mock_gsc_query(monkeypatch, [page1])

        creds_file = _write_creds(tmp_path)

        rows = fetch_search_analytics(
            str(creds_file), _DEFAULT_PROPERTY, "2026-07-01", "2026-07-20",
            row_limit=10  # page1 has 3 rows < 10, so no second call needed
        )
        assert len(rows) == 3

    def test_empty_response_returns_no_rows(self, tmp_path, monkeypatch):
        """Empty rows list on first call -> zero rows returned."""
        self._mock_gsc_query(monkeypatch, [[]])

        creds_file = _write_creds(tmp_path)

        rows = fetch_search_analytics(str(creds_file), _DEFAULT_PROPERTY, "2026-07-01", "2026-07-20")
        assert rows == []

    def test_dimension_keys_mapped_correctly(self, tmp_path, monkeypatch):
        """Row dict keys match requested dimensions."""
        row = _make_api_row(date_str="2026-07-10", query="alpha", country="gbr", device="MOBILE")
        self._mock_gsc_query(monkeypatch, [[row]])

        creds_file = _write_creds(tmp_path)

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

        creds_file = _write_creds(tmp_path)

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
        creds_file = _write_creds(tmp_path)

        def _fake_gsc_query(*args, **kwargs):
            return {"rows": []}

        monkeypatch.setattr("engine.marketing.seo_search_console._gsc_query", _fake_gsc_query)

        run(tmp_path, creds_path=str(creds_file), as_of=_AS_OF, write=True)

        seo_dir = tmp_path / _ARTIFACTS_REL
        for artifact_file in [_STATE_FILE, _SCORECARD_FILE, _GAPS_FILE,
                              _INDEX_STATUS_FILE]:
            path = seo_dir / artifact_file
            if path.exists():
                text = path.read_text()
                assert "private_key" not in text, f"{artifact_file} contains 'private_key'"
                assert _PRIVATE_KEY not in text, f"{artifact_file} contains the key"
                assert "NEVER_LEAK_THIS_STRING" not in text, (
                    f"{artifact_file} contains raw key material"
                )

    def test_scorecard_no_token(self, tmp_path, monkeypatch):
        """Scorecard and gaps artifacts must not contain 'token'."""
        _stub_google_auth(monkeypatch)
        monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
        monkeypatch.delenv("GSC_SA_JSON", raising=False)

        creds_file = _write_creds(tmp_path)

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

    def test_gscsajson_env_secret_never_reaches_an_artifact(self, tmp_path, monkeypatch):
        """The GSC_SA_JSON secret is parsed in-process and never lands on disk.

        (Replaces the old tmp-file-deletion test: there IS no tmp file any more —
        ``load_sa_info`` hands the parsed dict straight to
        ``from_service_account_info``, so key material never touches disk at all.)
        """
        _stub_google_auth(monkeypatch)
        monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
        monkeypatch.setenv("GSC_SA_JSON", json.dumps(_sa_info()))

        def _fake_gsc_query(*args, **kwargs):
            return {"rows": []}

        monkeypatch.setattr("engine.marketing.seo_search_console._gsc_query", _fake_gsc_query)

        state = run(tmp_path, creds_path=None, as_of=_AS_OF, write=True)
        assert state["available"] is True

        seo_dir = tmp_path / _ARTIFACTS_REL
        for artifact_file in [_STATE_FILE, _SCORECARD_FILE, _GAPS_FILE,
                              _INDEX_STATUS_FILE]:
            path = seo_dir / artifact_file
            if path.exists():
                text = path.read_text()
                assert "NEVER_LEAK_THIS_STRING" not in text
                assert _PRIVATE_KEY not in text

    def test_no_tmp_credential_file_is_created(self, tmp_path, monkeypatch):
        """`tempfile.mkstemp` must never be used to stage key material.

        The old code wrote GSC_SA_JSON to a chmod-600 tmp file so google-auth
        could read it back; a crash between write and unlink left the key on
        disk.  Artifact writes still use mkstemp, so the pin is on the SUFFIX
        the credential path used.
        """
        import engine.marketing.seo_search_console as mod

        _stub_google_auth(monkeypatch)
        monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
        monkeypatch.setenv("GSC_SA_JSON", json.dumps(_sa_info()))

        real_mkstemp = mod.tempfile.mkstemp
        seen: list[dict] = []

        def _spy(*args, **kwargs):
            seen.append(dict(kwargs))
            return real_mkstemp(*args, **kwargs)

        monkeypatch.setattr(mod.tempfile, "mkstemp", _spy)
        monkeypatch.setattr(
            "engine.marketing.seo_search_console._gsc_query",
            lambda *a, **k: {"rows": []},
        )

        run(tmp_path, creds_path=None, as_of=_AS_OF, write=True)

        cred_tmps = [k for k in seen if str(k.get("prefix", "")).startswith(".gsc_sa")]
        assert not cred_tmps, f"credential material staged on disk: {cred_tmps}"


# ---------------------------------------------------------------------------
# Tests: full run() integration (mocked)
# ---------------------------------------------------------------------------


class TestRunIntegration:
    def test_full_run_writes_all_artifacts(self, tmp_path, monkeypatch):
        """Full run with rows -> all 4 artifacts written."""
        _stub_google_auth(monkeypatch)
        monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
        monkeypatch.delenv("GSC_SA_JSON", raising=False)

        creds_file = _write_creds(tmp_path)

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

        creds_file = _write_creds(tmp_path)

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


# ---------------------------------------------------------------------------
# Tests: credential loading — the operator's actual production bug
#
# GH Actions run 30737705794 failed with
#   gsc: fetch failed: 'str' object has no attribute 'keys'
# because google-auth's from_service_account_file does json.load(f) then
# from_service_account_info(data), and a DOUBLE-ENCODED secret makes json.load
# return a str.  These tests pin: the double-encoded case now LOADS, and every
# other malformation is NAMED rather than crashed on.
# ---------------------------------------------------------------------------


class TestLoadSaInfo:
    def test_plain_object_loads(self, tmp_path, monkeypatch):
        monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
        monkeypatch.setenv("GSC_SA_JSON", json.dumps(_sa_info()))

        info, err = load_sa_info()
        assert err is None
        assert info["client_email"] == _CLIENT_EMAIL

    def test_double_encoded_secret_loads(self, monkeypatch):
        """THE operator bug: json.dumps applied twice must still work.

        json.loads(json.dumps(json.dumps(obj))) -> str, which is precisely what
        google-auth then calls .keys() on.  We unwrap it instead of dying.
        """
        monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
        monkeypatch.setenv("GSC_SA_JSON", json.dumps(json.dumps(_sa_info())))

        info, err = load_sa_info()
        assert err is None, f"double-encoded secret rejected: {err}"
        assert isinstance(info, dict)
        assert info["client_email"] == _CLIENT_EMAIL
        assert info["type"] == "service_account"

    def test_double_encoded_reaches_a_real_token(self, tmp_path, monkeypatch):
        """End-to-end: the unwrapped dict survives google-auth's .keys() call."""
        import engine.marketing.seo_search_console as mod

        _stub_google_auth(monkeypatch)
        monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
        monkeypatch.setenv("GSC_SA_JSON", json.dumps(json.dumps(_sa_info())))

        info, err = load_sa_info()
        assert err is None
        # The stub calls info.keys() exactly as google-auth does.
        assert mod._get_bearer_token(info) == "FAKE_TOKEN"

    def test_triple_encoded_secret_named_error(self, monkeypatch):
        monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
        monkeypatch.setenv(
            "GSC_SA_JSON", json.dumps(json.dumps(json.dumps(_sa_info())))
        )

        info, err = load_sa_info()
        assert info is None
        # The innermost layer IS the key file here, so the fingerprint says so.
        inner_len = len(json.dumps(_sa_info()))
        assert err == (
            "GSC_SA_JSON parsed to str after 2 unwraps — "
            "the secret is multiply-encoded "
            f"[inner payload: looks like a complete JSON object ({inner_len} chars)]"
        ), err

    def test_garbage_is_named_not_valid_json(self, monkeypatch):
        monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
        monkeypatch.setenv("GSC_SA_JSON", "{not json at all")

        info, err = load_sa_info()
        assert info is None
        assert err.startswith("GSC_SA_JSON is not valid JSON:"), err

    def test_json_array_is_not_an_object(self, monkeypatch):
        monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
        monkeypatch.setenv("GSC_SA_JSON", json.dumps([_sa_info()]))

        info, err = load_sa_info()
        assert info is None
        assert "parsed to list — expected a JSON object" in err, err

    def test_missing_keys_are_named(self, monkeypatch):
        monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
        blob = _sa_info()
        blob.pop("private_key")
        blob.pop("token_uri")
        monkeypatch.setenv("GSC_SA_JSON", json.dumps(blob))

        info, err = load_sa_info()
        assert info is None
        assert "service-account JSON missing keys: private_key, token_uri" in err, err

    def test_empty_string_value_counts_as_missing(self, monkeypatch):
        monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
        monkeypatch.setenv("GSC_SA_JSON", json.dumps(_sa_info(client_email="  ")))

        info, err = load_sa_info()
        assert info is None
        assert "missing keys: client_email" in err, err

    def test_wrong_type_is_named(self, monkeypatch):
        monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
        monkeypatch.setenv(
            "GSC_SA_JSON", json.dumps(_sa_info(type="authorized_user"))
        )

        info, err = load_sa_info()
        assert info is None
        assert "type='authorized_user'" in err, err
        assert "expected 'service_account'" in err, err

    def test_bom_and_whitespace_tolerated(self, monkeypatch):
        monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
        monkeypatch.setenv(
            "GSC_SA_JSON", "﻿  \n" + json.dumps(_sa_info()) + "\n  "
        )

        info, err = load_sa_info()
        assert err is None, err
        assert info["client_email"] == _CLIENT_EMAIL

    def test_empty_env_reports_not_configured(self, monkeypatch):
        monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
        monkeypatch.setenv("GSC_SA_JSON", "   ")

        info, err = load_sa_info()
        assert info is None
        assert err == "credentials not configured"

    def test_no_source_reports_not_configured(self, monkeypatch):
        monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
        monkeypatch.delenv("GSC_SA_JSON", raising=False)

        info, err = load_sa_info()
        assert info is None
        assert err == "credentials not configured"

    def test_explicit_path_read_as_file(self, tmp_path, monkeypatch):
        monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
        monkeypatch.delenv("GSC_SA_JSON", raising=False)
        p = _write_creds(tmp_path)

        info, err = load_sa_info(creds_path=p)
        assert err is None
        assert info["project_id"] == "mastermindx-503122"

    def test_explicit_path_takes_precedence_over_env(self, tmp_path, monkeypatch):
        p = _write_creds(tmp_path, client_email="from-file@x.iam.gserviceaccount.com")
        monkeypatch.setenv("GSC_SA_JSON", json.dumps(
            _sa_info(client_email="from-env@x.iam.gserviceaccount.com")))

        info, err = load_sa_info(creds_path=p)
        assert err is None
        assert info["client_email"] == "from-file@x.iam.gserviceaccount.com"

    def test_gac_env_read_as_file_path(self, tmp_path, monkeypatch):
        p = _write_creds(tmp_path, name="gac.json",
                         client_email="gac@x.iam.gserviceaccount.com")
        monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(p))
        monkeypatch.setenv("GSC_SA_JSON", json.dumps(_sa_info()))

        info, err = load_sa_info()
        assert err is None
        assert info["client_email"] == "gac@x.iam.gserviceaccount.com"

    def test_gac_env_double_encoded_file_also_unwraps(self, tmp_path, monkeypatch):
        p = tmp_path / "gac2.json"
        p.write_text(json.dumps(json.dumps(_sa_info())), encoding="utf-8")
        monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(p))
        monkeypatch.delenv("GSC_SA_JSON", raising=False)

        info, err = load_sa_info()
        assert err is None, err
        assert info["client_email"] == _CLIENT_EMAIL

    def test_gac_missing_file_named(self, tmp_path, monkeypatch):
        monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(tmp_path / "nope.json"))
        monkeypatch.delenv("GSC_SA_JSON", raising=False)

        info, err = load_sa_info()
        assert info is None
        assert "GOOGLE_APPLICATION_CREDENTIALS points at a missing file" in err, err

    def test_explicit_missing_path_named(self, tmp_path, monkeypatch):
        monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
        monkeypatch.delenv("GSC_SA_JSON", raising=False)

        info, err = load_sa_info(creds_path="/nonexistent/key.json")
        assert info is None
        assert err == "credentials file not found: /nonexistent/key.json"

    def test_no_failure_mode_ever_emits_the_private_key(self, tmp_path, monkeypatch):
        """SECURITY: sweep every branch; the key must not appear in ANY error."""
        monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
        blob = _sa_info()
        no_type = _sa_info(type="authorized_user")
        no_email = _sa_info()
        no_email.pop("client_email")

        payloads = [
            json.dumps(blob),                                   # valid
            json.dumps(json.dumps(blob)),                       # double-encoded
            json.dumps(json.dumps(json.dumps(blob))),           # triple-encoded
            json.dumps(no_type),                                # wrong type
            json.dumps(no_email),                               # missing key
            json.dumps([blob]),                                 # not an object
            json.dumps(blob)[:-4],                              # truncated JSON
            '{"private_key": "' + _PRIVATE_KEY.replace("\n", "\\n") + '"}',
        ]
        for payload in payloads:
            monkeypatch.setenv("GSC_SA_JSON", payload)
            info, err = load_sa_info()
            emitted = "" if err is None else err
            assert "NEVER_LEAK_THIS_STRING" not in emitted, (payload[:40], err)
            assert "BEGIN PRIVATE KEY" not in emitted, (payload[:40], err)


# ---------------------------------------------------------------------------
# Tests: the payload SHAPE fingerprint
#
# Live run 30742044120 rejected the secret with only
#   GSC_SA_JSON is multiply-encoded and the inner layer is not valid JSON:
#   Expecting value: line 1 column 1 (char 0)
# — which says the paste was a quoted string but not WHAT string.  Each wrong
# operator guess costs a 30-60 min CI cycle, so the error now names the SHAPE
# (category + character count) of what actually landed in the secret.  It must
# NEVER name the content: the classifier returns literals and a len(), nothing
# derived from the payload's bytes.
# ---------------------------------------------------------------------------


_LENGTH_SUFFIX_RE = re.compile(r" \((\d+) chars\)$")


class TestDescribeShape:
    """One test per category — each must be distinguishable from the others.

    Every assertion here fails if its branch is deleted (the payload then falls
    through to 'unrecognized text'), so none of them is vacuous.
    """

    def test_empty_string(self):
        assert _describe_shape("") == "empty / whitespace-only (0 chars)"

    def test_whitespace_only(self):
        assert _describe_shape("  \n\t  ") == "empty / whitespace-only (0 chars)"

    def test_email_is_named_actionably(self):
        """The likeliest paste: the SA's own address instead of its key file."""
        out = _describe_shape(_CLIENT_EMAIL)
        assert out.startswith("looks like an email address — "), out
        assert "paste the CONTENTS of the downloaded .json key file" in out, out
        assert "not the service-account email" in out, out
        assert out.endswith(f"({len(_CLIENT_EMAIL)} chars)"), out

    def test_email_survives_surrounding_whitespace(self):
        out = _describe_shape(f"  {_CLIENT_EMAIL}\n")
        assert out.startswith("looks like an email address"), out

    def test_prose_containing_an_at_sign_is_not_an_email(self):
        """The regex anchors the WHOLE payload — a sentence must not match."""
        out = _describe_shape("email me @ mastermindx@example.com please")
        assert out == "unrecognized text (41 chars)", out

    def test_bare_pem_is_named(self):
        out = _describe_shape(_PRIVATE_KEY)
        assert out.startswith("looks like a bare PEM private key — "), out
        assert "not just the private_key field" in out, out

    def test_absolute_path_is_named(self):
        out = _describe_shape("/Users/chriswong/secrets/mastermindx-key.json")
        assert out.startswith("looks like a FILE PATH — "), out
        assert "must contain the file's CONTENTS" in out, out
        assert "GOOGLE_APPLICATION_CREDENTIALS" in out, out

    def test_home_relative_path_is_named(self):
        out = _describe_shape("~/keys/sa.json")
        assert out.startswith("looks like a FILE PATH"), out

    def test_bare_json_basename_is_a_path(self):
        out = _describe_shape("mastermindx-503122-a1b2c3d4.json")
        assert out.startswith("looks like a FILE PATH"), out

    def test_truncated_json_is_named(self):
        payload = json.dumps(_sa_info())[:-4]
        out = _describe_shape(payload)
        assert out.startswith("looks like TRUNCATED JSON"), out
        assert "the paste was cut off" in out, out
        assert out.endswith(f"({len(payload)} chars)"), out

    def test_complete_json_object_is_not_called_truncated(self):
        payload = json.dumps(_sa_info())
        assert _describe_shape(payload) == (
            f"looks like a complete JSON object ({len(payload)} chars)"
        )

    def test_unrecognized_text(self):
        assert _describe_shape("paste your key here") == "unrecognized text (19 chars)"

    def test_length_reported_for_every_category(self):
        payloads = [
            "",
            _CLIENT_EMAIL,
            _PRIVATE_KEY,
            "/etc/gsc/key.json",
            json.dumps(_sa_info())[:-4],
            json.dumps(_sa_info()),
            "hello",
        ]
        for payload in payloads:
            out = _describe_shape(payload)
            hit = _LENGTH_SUFFIX_RE.search(out)
            assert hit, f"no length in {out!r}"
            assert int(hit.group(1)) == len(payload.strip()), out

    def test_categories_are_mutually_distinguishable(self):
        """A collapsed classifier (one label for everything) fails here."""
        labels = {
            _LENGTH_SUFFIX_RE.sub("", _describe_shape(p))
            for p in (
                "",
                _CLIENT_EMAIL,
                _PRIVATE_KEY,
                "/etc/gsc/key.json",
                json.dumps(_sa_info())[:-4],
                json.dumps(_sa_info()),
                "hello",
            )
        }
        assert len(labels) == 7, labels


class TestCredentialShapeHintInErrors:
    """The fingerprint reaches the operator-facing error, outer AND inner layer."""

    def test_quoted_email_reports_the_INNER_shape(self, monkeypatch):
        """Exact reproduction of live run 30742044120's payload shape."""
        monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
        monkeypatch.setenv("GSC_SA_JSON", json.dumps(_CLIENT_EMAIL))

        info, err = load_sa_info()
        assert info is None
        assert err.startswith(
            "GSC_SA_JSON is multiply-encoded and the inner layer is not valid JSON:"
        ), err
        assert "[inner payload: looks like an email address" in err, err
        assert f"({len(_CLIENT_EMAIL)} chars)]" in err, err

    def test_quoted_path_reports_the_INNER_shape(self, monkeypatch):
        monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
        monkeypatch.setenv("GSC_SA_JSON", json.dumps("/home/ci/gsc-key.json"))

        info, err = load_sa_info()
        assert info is None
        assert "[inner payload: looks like a FILE PATH" in err, err

    def test_bare_email_reports_the_OUTER_shape(self, monkeypatch):
        monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
        monkeypatch.setenv("GSC_SA_JSON", _CLIENT_EMAIL)

        info, err = load_sa_info()
        assert info is None
        assert err.startswith("GSC_SA_JSON is not valid JSON:"), err
        assert "[payload: looks like an email address" in err, err

    def test_bare_pem_reports_the_OUTER_shape(self, monkeypatch):
        monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
        monkeypatch.setenv("GSC_SA_JSON", _PRIVATE_KEY)

        info, err = load_sa_info()
        assert info is None
        assert "[payload: looks like a bare PEM private key" in err, err

    def test_truncated_paste_reports_the_OUTER_shape(self, monkeypatch):
        monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
        payload = json.dumps(_sa_info())[:-4]
        monkeypatch.setenv("GSC_SA_JSON", payload)

        info, err = load_sa_info()
        assert info is None
        assert "[payload: looks like TRUNCATED JSON" in err, err
        assert f"({len(payload)} chars)]" in err, err

    def test_unrecognized_paste_still_reports_a_length(self, monkeypatch):
        monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
        monkeypatch.setenv("GSC_SA_JSON", "paste the key here")

        info, err = load_sa_info()
        assert info is None
        assert "[payload: unrecognized text (18 chars)]" in err, err

    def test_validate_error_carries_the_shape_too(self, monkeypatch):
        """A 2300-char complete object with a missing key ≠ a 40-char paste."""
        monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
        blob = _sa_info()
        blob.pop("token_uri")
        payload = json.dumps(blob)
        monkeypatch.setenv("GSC_SA_JSON", payload)

        info, err = load_sa_info()
        assert info is None
        assert "missing keys: token_uri" in err, err
        assert err.endswith(
            f"[payload: looks like a complete JSON object ({len(payload)} chars)]"
        ), err

    def test_wrong_type_error_carries_the_shape_too(self, monkeypatch):
        monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
        payload = json.dumps(_sa_info(type="authorized_user"))
        monkeypatch.setenv("GSC_SA_JSON", payload)

        info, err = load_sa_info()
        assert info is None
        assert "type='authorized_user'" in err, err
        assert "[payload: looks like a complete JSON object" in err, err

    def test_file_source_gets_the_fingerprint_as_well(self, tmp_path, monkeypatch):
        monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
        monkeypatch.delenv("GSC_SA_JSON", raising=False)
        p = tmp_path / "wrong.json"
        p.write_text(_CLIENT_EMAIL, encoding="utf-8")

        info, err = load_sa_info(creds_path=p)
        assert info is None
        assert "[payload: looks like an email address" in err, err

    def test_valid_double_encoded_still_loads_unchanged(self, monkeypatch):
        """Non-regression for PR #4269 — the fingerprint must not gate success."""
        monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
        monkeypatch.setenv("GSC_SA_JSON", json.dumps(json.dumps(_sa_info())))

        info, err = load_sa_info()
        assert err is None, f"double-encoded secret rejected: {err}"
        assert info["client_email"] == _CLIENT_EMAIL
        assert info["private_key"] == _PRIVATE_KEY

    def test_valid_single_encoded_still_loads_unchanged(self, monkeypatch):
        monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
        monkeypatch.setenv("GSC_SA_JSON", json.dumps(_sa_info()))

        info, err = load_sa_info()
        assert err is None, err
        assert info["type"] == "service_account"

    def test_no_error_path_emits_any_20_char_window_of_the_key(
        self, tmp_path, monkeypatch
    ):
        """SECURITY: sweep every path with a realistic PEM-shaped key present.

        Substring-level, not sentinel-level: no 20-character window of the key
        body may survive into any emitted string.
        """
        monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
        blob = _sa_info()
        no_email = _sa_info()
        no_email.pop("client_email")

        windows = {
            _PRIVATE_KEY[i:i + 20] for i in range(len(_PRIVATE_KEY) - 19)
        }
        assert len(windows) > 50, "fixture key too short to make this test mean much"

        emitted: list[tuple[str, str]] = []

        env_payloads = {
            "valid": json.dumps(blob),
            "double-encoded": json.dumps(json.dumps(blob)),
            "triple-encoded": json.dumps(json.dumps(json.dumps(blob))),
            "wrong-type": json.dumps(_sa_info(type="authorized_user")),
            "missing-key": json.dumps(no_email),
            "not-an-object": json.dumps([blob]),
            "truncated": json.dumps(blob)[:-4],
            "bare-pem": _PRIVATE_KEY,
            "quoted-pem": json.dumps(_PRIVATE_KEY),
            "key-only-object": '{"private_key": "'
                               + _PRIVATE_KEY.replace("\n", "\\n") + '"}',
            "pem-then-garbage": _PRIVATE_KEY + "\n{oops",
        }
        for name, payload in env_payloads.items():
            monkeypatch.setenv("GSC_SA_JSON", payload)
            _info, err = load_sa_info()
            emitted.append((f"env:{name}", err or ""))

        # File sources take a different branch of load_sa_info.
        for name, body in (
            ("file:bare-pem", _PRIVATE_KEY),
            ("file:truncated", json.dumps(blob)[:-4]),
            ("file:key-only", json.dumps({"private_key": _PRIVATE_KEY})),
        ):
            p = tmp_path / f"{name.split(':')[1]}.txt"
            p.write_text(body, encoding="utf-8")
            _info, err = load_sa_info(creds_path=p)
            emitted.append((name, err or ""))

        # And the three helpers directly, with key material in hand.
        emitted.append(("shape:pem", _describe_shape(_PRIVATE_KEY)))
        emitted.append(("shape:object", _describe_shape(json.dumps(blob))))
        emitted.append(
            ("parse:direct", _parse_sa_json(_PRIVATE_KEY, "GSC_SA_JSON")[1] or "")
        )
        emitted.append((
            "validate:direct",
            _validate_sa_info(no_email, "GSC_SA_JSON", raw=json.dumps(blob)) or "",
        ))

        assert len([t for _, t in emitted if t]) >= 14, emitted

        for label, text in emitted:
            assert "NEVER_LEAK_THIS_STRING" not in text, (label, text)
            assert "BEGIN PRIVATE KEY" not in text, (label, text)
            for window in windows:
                assert window not in text, (label, text)


class TestBearerTokenFromInfo:
    def test_auth_failure_is_one_clean_scrubbed_line(self, monkeypatch):
        """A google.auth blow-up becomes one line, with key material removed."""
        import engine.marketing.seo_search_console as mod

        _stub_google_auth(monkeypatch)
        sa_mod = sys.modules["google.oauth2.service_account"]

        def _boom(info, scopes=None):
            raise ValueError(
                "invalid JWT signature\ntraceback line 2\nkey=" + _PRIVATE_KEY
            )

        monkeypatch.setattr(sa_mod.Credentials, "from_service_account_info", _boom)

        with pytest.raises(mod.GscAuthError) as exc:
            mod._get_bearer_token(_sa_info())

        msg = str(exc.value)
        assert "\n" not in msg, "auth error must be ONE line"
        assert _CLIENT_EMAIL in msg, "must name which SA failed"
        assert "NEVER_LEAK_THIS_STRING" not in msg
        assert "BEGIN PRIVATE KEY" not in msg


# ---------------------------------------------------------------------------
# Tests: HTTP status -> distinct, actionable operator reason + annotation
# ---------------------------------------------------------------------------


def _run_with_status(tmp_path, monkeypatch, status: int, message: str = "denied"):
    _stub_google_auth(monkeypatch)
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    monkeypatch.delenv("GSC_SA_JSON", raising=False)
    creds_file = _write_creds(tmp_path)

    def _fail(*args, **kwargs):
        raise GscApiError(status, message)

    monkeypatch.setattr("engine.marketing.seo_search_console._gsc_query", _fail)
    return run(tmp_path, creds_path=str(creds_file), as_of=_AS_OF, write=True)


class TestStatusReasons:
    def test_403_names_the_service_account_and_the_ui_action(
        self, tmp_path, monkeypatch, capsys
    ):
        state = _run_with_status(tmp_path, monkeypatch, 403)

        assert state["available"] is False
        reason = state["reason"]
        assert _CLIENT_EMAIL in reason
        assert _DEFAULT_PROPERTY in reason
        assert "add it as a user in Search Console" in reason
        assert "api error" not in reason.lower()

        lines = _annotation_lines(capsys.readouterr().out)
        hit = [ln for ln in lines if "gsc-no-access" in ln]
        assert hit, f"no 403 annotation among {lines}"
        assert hit[0].startswith("::warning title=gsc-no-access::")
        assert _CLIENT_EMAIL in hit[0]

    def test_404_names_the_domain_property(self, tmp_path, monkeypatch, capsys):
        state = _run_with_status(tmp_path, monkeypatch, 404, "not found")

        reason = state["reason"]
        assert state["available"] is False
        assert "not found" in reason
        assert "DOMAIN property" in reason
        assert _DEFAULT_PROPERTY in reason

        lines = _annotation_lines(capsys.readouterr().out)
        hit = [ln for ln in lines if "gsc-property-not-found" in ln]
        assert hit, f"no 404 annotation among {lines}"
        assert hit[0].startswith("::warning title=gsc-property-not-found::")

    def test_500_stays_a_generic_api_error(self, tmp_path, monkeypatch, capsys):
        state = _run_with_status(tmp_path, monkeypatch, 500, "backend error")

        assert state["available"] is False
        assert state["reason"].startswith("api error: ")
        lines = _annotation_lines(capsys.readouterr().out)
        assert not [ln for ln in lines if "gsc-no-access" in ln]
        assert not [ln for ln in lines if "gsc-property-not-found" in ln]

    def test_403_does_not_burn_quota_on_the_inspection_sweep(
        self, tmp_path, monkeypatch
    ):
        """12 more copies of the same 403 buy nothing — and cost quota."""
        calls = []
        monkeypatch.setattr(
            "engine.marketing.seo_search_console._inspect_post",
            lambda *a, **k: calls.append(a) or {},
        )
        _run_with_status(tmp_path, monkeypatch, 403)
        assert calls == []

    def test_malformed_credentials_reason_and_annotation(
        self, tmp_path, monkeypatch, capsys
    ):
        monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
        monkeypatch.setenv(
            "GSC_SA_JSON", json.dumps(json.dumps(json.dumps(_sa_info())))
        )

        state = run(tmp_path, creds_path=None, as_of=_AS_OF, write=True)

        assert state["available"] is False
        inner_len = len(json.dumps(_sa_info()))
        assert state["reason"] == (
            "GSC_SA_JSON parsed to str after 2 unwraps — "
            "the secret is multiply-encoded "
            f"[inner payload: looks like a complete JSON object ({inner_len} chars)]"
        )
        lines = _annotation_lines(capsys.readouterr().out)
        hit = [ln for ln in lines if "gsc-credentials-malformed" in ln]
        assert hit, f"no malformed-credentials annotation among {lines}"
        assert hit[0].startswith("::warning title=gsc-credentials-malformed::")

    def test_absent_credentials_stay_quiet(self, tmp_path, monkeypatch, capsys):
        """'not configured' is a state, not an alarm — no annotation for it."""
        monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
        monkeypatch.delenv("GSC_SA_JSON", raising=False)

        state = run(tmp_path, creds_path=None, as_of=_AS_OF, write=True)
        assert state["reason"] == "credentials not configured"
        assert not [
            ln for ln in _annotation_lines(capsys.readouterr().out)
            if "gsc-credentials-malformed" in ln
        ]


# ---------------------------------------------------------------------------
# Tests: sitemap diagnostics
# ---------------------------------------------------------------------------


class TestFetchSitemaps:
    def test_real_shaped_payload_parsed(self, monkeypatch):
        _stub_google_auth(monkeypatch)
        monkeypatch.setattr(
            "engine.marketing.seo_search_console._sitemaps_get",
            lambda token, prop: _sitemaps_payload(),
        )

        doc = fetch_sitemaps(_sa_info(), _DEFAULT_PROPERTY)

        assert doc["count"] == 2
        first = doc["sitemaps"][0]
        assert first["path"] == "https://www.mastermind-x.com/sitemap.xml"
        assert first["lastSubmitted"] == "2026-07-22T09:14:11.000Z"
        assert first["lastDownloaded"] == "2026-07-23T04:02:55.000Z"
        assert first["isPending"] is False
        # Counts arrive as strings over JSON; they must land as ints.
        assert first["warnings"] == 3 and isinstance(first["warnings"], int)
        assert first["errors"] == 0
        assert first["submitted"] == 2219
        assert first["indexed"] == 0
        assert first["contents"] == [
            {"type": "web", "submitted": 2219, "indexed": 0}
        ]

    def test_never_downloaded_is_flagged(self, monkeypatch):
        _stub_google_auth(monkeypatch)
        monkeypatch.setattr(
            "engine.marketing.seo_search_console._sitemaps_get",
            lambda token, prop: _sitemaps_payload(),
        )

        doc = fetch_sitemaps(_sa_info(), _DEFAULT_PROPERTY)
        assert doc["never_downloaded"] == [
            "https://www.mastermind-x.com/news-sitemap.xml"
        ]
        assert doc["sitemaps"][1]["lastDownloaded"] is None

    def test_empty_property_has_no_sitemaps(self, monkeypatch):
        _stub_google_auth(monkeypatch)
        monkeypatch.setattr(
            "engine.marketing.seo_search_console._sitemaps_get",
            lambda token, prop: {},
        )

        doc = fetch_sitemaps(_sa_info(), _DEFAULT_PROPERTY)
        assert doc == {"sitemaps": [], "never_downloaded": [], "count": 0}


# ---------------------------------------------------------------------------
# Tests: URL inspection
# ---------------------------------------------------------------------------


class TestInspectUrls:
    def test_real_shaped_payload_projected(self, monkeypatch):
        _stub_google_auth(monkeypatch)
        monkeypatch.setattr(
            "engine.marketing.seo_search_console._inspect_post",
            lambda token, prop, url: _inspect_payload(url=url),
        )

        recs = inspect_urls(
            _sa_info(), _DEFAULT_PROPERTY,
            ["https://www.mastermind-x.com/"], pace_s=0,
        )
        assert len(recs) == 1
        r = recs[0]
        assert r["url"] == "https://www.mastermind-x.com/"
        assert r["verdict"] == "PASS"
        assert r["coverageState"] == "Submitted and indexed"
        assert r["robotsTxtState"] == "ALLOWED"
        assert r["indexingState"] == "INDEXING_ALLOWED"
        assert r["lastCrawlTime"] == "2026-07-19T11:22:33Z"
        assert r["pageFetchState"] == "SUCCESSFUL"
        assert r["googleCanonical"] == "https://www.mastermind-x.com/"
        assert r["userCanonical"] == "https://www.mastermind-x.com/"
        assert r["inspectionResultLink"].startswith(
            "https://search.google.com/search-console/inspect")
        assert r["indexed"] is True
        assert r["error"] is None

    def test_deindexed_verdict_is_not_indexed(self, monkeypatch):
        """'URL is unknown to Google' — the mastermind-x.com situation."""
        _stub_google_auth(monkeypatch)
        monkeypatch.setattr(
            "engine.marketing.seo_search_console._inspect_post",
            lambda token, prop, url: _inspect_payload(
                verdict="FAIL",
                coverage="URL is unknown to Google",
                last_crawl=None,
                fetch_state="PAGE_FETCH_STATE_UNSPECIFIED",
                url=url,
            ),
        )

        recs = inspect_urls(
            _sa_info(), _DEFAULT_PROPERTY,
            ["https://www.mastermind-x.com/"], pace_s=0,
        )
        assert recs[0]["indexed"] is False
        assert recs[0]["coverageState"] == "URL is unknown to Google"
        assert recs[0]["lastCrawlTime"] is None

    def test_crawled_but_not_indexed_is_not_indexed(self, monkeypatch):
        """coverageState contains the word 'indexed' — the verdict decides."""
        _stub_google_auth(monkeypatch)
        monkeypatch.setattr(
            "engine.marketing.seo_search_console._inspect_post",
            lambda token, prop, url: _inspect_payload(
                verdict="NEUTRAL",
                coverage="Crawled - currently not indexed",
                url=url,
            ),
        )

        recs = inspect_urls(
            _sa_info(), _DEFAULT_PROPERTY,
            ["https://www.mastermind-x.com/macro.html"], pace_s=0,
        )
        assert recs[0]["indexed"] is False

    def test_one_failure_mid_sweep_does_not_abort_the_others(self, monkeypatch):
        _stub_google_auth(monkeypatch)
        urls = [f"https://www.mastermind-x.com/p{i}.html" for i in range(5)]

        def _post(token, prop, url):
            if url.endswith("p2.html"):
                raise GscApiError(500, "backend error on p2")
            return _inspect_payload(url=url)

        monkeypatch.setattr(
            "engine.marketing.seo_search_console._inspect_post", _post)

        recs = inspect_urls(_sa_info(), _DEFAULT_PROPERTY, urls, pace_s=0)

        assert len(recs) == len(urls), "sweep aborted early"
        assert [r["url"] for r in recs] == urls, "order not preserved"
        failed = [r for r in recs if r["error"]]
        assert len(failed) == 1
        assert failed[0]["url"].endswith("p2.html")
        assert "backend error on p2" in failed[0]["error"]
        assert failed[0]["indexed"] is False
        assert sum(1 for r in recs if r["indexed"]) == 4

    def test_per_url_error_never_leaks_key_material(self, monkeypatch):
        _stub_google_auth(monkeypatch)

        def _post(token, prop, url):
            raise RuntimeError("boom private_key=" + _PRIVATE_KEY)

        monkeypatch.setattr(
            "engine.marketing.seo_search_console._inspect_post", _post)

        recs = inspect_urls(
            _sa_info(), _DEFAULT_PROPERTY,
            ["https://www.mastermind-x.com/"], pace_s=0,
        )
        assert "NEVER_LEAK_THIS_STRING" not in recs[0]["error"]
        assert "BEGIN PRIVATE KEY" not in recs[0]["error"]

    def test_requests_are_paced_between_urls(self, monkeypatch):
        """Quota is 600/min — a 12-URL burst must be spaced, not fired at once."""
        import engine.marketing.seo_search_console as mod

        _stub_google_auth(monkeypatch)
        slept: list[float] = []
        monkeypatch.setattr(mod.time, "sleep", lambda s: slept.append(s))
        monkeypatch.setattr(
            "engine.marketing.seo_search_console._inspect_post",
            lambda token, prop, url: _inspect_payload(url=url),
        )

        urls = [f"https://www.mastermind-x.com/p{i}.html" for i in range(4)]
        inspect_urls(_sa_info(), _DEFAULT_PROPERTY, urls, pace_s=0.25)

        assert slept == [0.25, 0.25, 0.25], slept  # n-1 gaps, none before the first

    def test_body_carries_the_property_and_language(self, monkeypatch):
        _stub_google_auth(monkeypatch)
        seen: list[tuple] = []
        monkeypatch.setattr(
            "engine.marketing.seo_search_console._inspect_post",
            lambda token, prop, url: seen.append((token, prop, url)) or {},
        )

        inspect_urls(
            _sa_info(), _DEFAULT_PROPERTY,
            ["https://www.mastermind-x.com/"], pace_s=0,
        )
        assert seen == [("FAKE_TOKEN", _DEFAULT_PROPERTY,
                         "https://www.mastermind-x.com/")]


# ---------------------------------------------------------------------------
# Tests: the deterministic core URL set
# ---------------------------------------------------------------------------


def _write_sitemap(root: Path, blog: list[tuple[str, str | None]]) -> None:
    """Write a site/sitemap.xml with the given (url, lastmod) blog entries."""
    site = root / "site"
    site.mkdir(parents=True, exist_ok=True)
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
        "  <url><loc>https://www.mastermind-x.com/</loc></url>",
    ]
    for loc, lastmod in blog:
        lm = f"<lastmod>{lastmod}</lastmod>" if lastmod else ""
        parts.append(f"  <url><loc>{loc}</loc>{lm}</url>")
    parts.append("</urlset>")
    (site / "sitemap.xml").write_text("\n".join(parts), encoding="utf-8")


class TestCoreUrlSet:
    def test_capped_and_root_first(self, tmp_path):
        urls = _core_inspect_urls(tmp_path, _DEFAULT_PROPERTY)
        assert len(urls) <= _MAX_INSPECT_URLS
        assert urls[0] == "https://www.mastermind-x.com/"
        assert "https://www.mastermind-x.com/macro.html" in urls
        assert "https://www.mastermind-x.com/plans.html" in urls

    def test_deterministic_across_calls(self, tmp_path):
        _write_sitemap(tmp_path, [
            ("https://www.mastermind-x.com/blog/a.html", None),
            ("https://www.mastermind-x.com/blog/b.html", None),
            ("https://www.mastermind-x.com/blog/c.html", None),
        ])
        assert (_core_inspect_urls(tmp_path, _DEFAULT_PROPERTY)
                == _core_inspect_urls(tmp_path, _DEFAULT_PROPERTY))

    def test_two_most_recent_blog_posts_appended(self, tmp_path):
        _write_sitemap(tmp_path, [
            ("https://www.mastermind-x.com/blog/old.html", "2026-01-01"),
            ("https://www.mastermind-x.com/blog/newest.html", "2026-07-30"),
            ("https://www.mastermind-x.com/blog/second.html", "2026-07-15"),
            ("https://www.mastermind-x.com/blog/index.html", "2026-07-31"),
        ])
        urls = _core_inspect_urls(tmp_path, _DEFAULT_PROPERTY)

        assert len(urls) == _MAX_INSPECT_URLS
        assert urls[-2:] == [
            "https://www.mastermind-x.com/blog/newest.html",
            "https://www.mastermind-x.com/blog/second.html",
        ]
        # blog/index.html is already in the core set; it is not a "post".
        assert urls.count("https://www.mastermind-x.com/blog/index.html") == 1
        assert "https://www.mastermind-x.com/blog/old.html" not in urls

    def test_lastmod_free_blog_entries_still_deterministic(self, tmp_path):
        """This repo's sitemap emits blog URLs with NO lastmod — sort must hold."""
        _write_sitemap(tmp_path, [
            ("https://www.mastermind-x.com/blog/aaa.html", None),
            ("https://www.mastermind-x.com/blog/zzz.html", None),
            ("https://www.mastermind-x.com/blog/mmm.html", None),
        ])
        urls = _core_inspect_urls(tmp_path, _DEFAULT_PROPERTY)
        assert urls[-2:] == [
            "https://www.mastermind-x.com/blog/zzz.html",
            "https://www.mastermind-x.com/blog/mmm.html",
        ]

    def test_origin_taken_from_the_sitemap(self, tmp_path):
        site = tmp_path / "site"
        site.mkdir(parents=True, exist_ok=True)
        (site / "sitemap.xml").write_text(
            '<urlset><url><loc>https://example.test/</loc></url></urlset>',
            encoding="utf-8",
        )
        urls = _core_inspect_urls(tmp_path, _DEFAULT_PROPERTY)
        assert urls[0] == "https://example.test/"
        assert all(u.startswith("https://example.test/") for u in urls)

    def test_origin_falls_back_to_the_property(self, tmp_path):
        urls = _core_inspect_urls(tmp_path, "sc-domain:other-site.example")
        assert urls[0] == "https://www.other-site.example/"

    def test_real_repo_sitemap_yields_twelve(self):
        """Against the checked-in site/sitemap.xml, not a fixture."""
        urls = _core_inspect_urls(REPO_ROOT, _DEFAULT_PROPERTY)
        assert len(urls) == _MAX_INSPECT_URLS
        assert urls[0] == "https://www.mastermind-x.com/"
        assert len(set(urls)) == len(urls), "duplicate URL in the core set"


# ---------------------------------------------------------------------------
# Tests: index-status artifact + annotations
# ---------------------------------------------------------------------------


def _stub_index_endpoints(monkeypatch, *, indexed_urls=(), sitemaps=None):
    """Stub both diagnostics seams; URLs in `indexed_urls` come back PASS."""
    monkeypatch.setattr(
        "engine.marketing.seo_search_console._sitemaps_get",
        lambda token, prop: _sitemaps_payload() if sitemaps is None else sitemaps,
    )

    def _post(token, prop, url):
        if url in indexed_urls:
            return _inspect_payload(url=url)
        return _inspect_payload(
            verdict="FAIL", coverage="URL is unknown to Google",
            last_crawl=None, fetch_state="PAGE_FETCH_STATE_UNSPECIFIED", url=url,
        )

    monkeypatch.setattr(
        "engine.marketing.seo_search_console._inspect_post", _post)


class TestIndexStatusArtifact:
    def test_run_writes_the_index_status_artifact(self, tmp_path, monkeypatch):
        _stub_google_auth(monkeypatch)
        monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
        monkeypatch.delenv("GSC_SA_JSON", raising=False)
        _stub_index_endpoints(monkeypatch)
        monkeypatch.setattr(
            "engine.marketing.seo_search_console._gsc_query",
            lambda *a, **k: {"rows": []},
        )
        creds_file = _write_creds(tmp_path)

        state = run(tmp_path, creds_path=str(creds_file), as_of=_AS_OF,
                    write=True, pace_s=0)

        path = tmp_path / _ARTIFACTS_REL / _INDEX_STATUS_FILE
        assert path.exists(), "index-status artifact not written"
        doc = json.loads(path.read_text())

        assert doc["schema"] == "gsc_index_status.v1"
        assert doc["as_of"] == "2026-07-20"
        assert doc["available"] is True
        assert doc["property"] == _DEFAULT_PROPERTY
        assert doc["service_account"]["client_email"] == _CLIENT_EMAIL
        assert doc["sitemaps"]["count"] == 2
        assert doc["sitemaps"]["never_downloaded"] == [
            "https://www.mastermind-x.com/news-sitemap.xml"
        ]
        assert len(doc["urls"]) == 10   # no site/sitemap.xml in tmp_path
        assert all("coverageState" in u for u in doc["urls"])
        assert all(u["indexed"] is False for u in doc["urls"])

        # The state file does NOT duplicate it (one fact, one writer).
        on_disk_state = json.loads(
            (tmp_path / _ARTIFACTS_REL / _STATE_FILE).read_text())
        assert "index_status" not in on_disk_state
        # ...but the returned dict carries it for callers.
        assert state["index_status"]["schema"] == "gsc_index_status.v1"

    def test_index_status_written_even_without_credentials(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
        monkeypatch.delenv("GSC_SA_JSON", raising=False)

        run(tmp_path, creds_path=None, as_of=_AS_OF, write=True)

        doc = json.loads(
            (tmp_path / _ARTIFACTS_REL / _INDEX_STATUS_FILE).read_text())
        assert doc["available"] is False
        assert doc["reason"] == "credentials not configured"
        assert doc["urls"] == []

    def test_sitemap_leg_failure_keeps_the_url_leg(self, tmp_path, monkeypatch):
        """Independent legs: a sitemaps 500 must not cost the inspections."""
        _stub_google_auth(monkeypatch)
        monkeypatch.setattr(
            "engine.marketing.seo_search_console._sitemaps_get",
            lambda token, prop: (_ for _ in ()).throw(GscApiError(500, "sitemaps down")),
        )
        monkeypatch.setattr(
            "engine.marketing.seo_search_console._inspect_post",
            lambda token, prop, url: _inspect_payload(url=url),
        )

        doc = collect_index_status(
            tmp_path, info=_sa_info(), prop=_DEFAULT_PROPERTY,
            as_of_iso="2026-07-20", pace_s=0,
        )
        assert doc["available"] is True
        assert len(doc["urls"]) == 10
        assert "sitemaps down" in doc["sitemaps"]["error"]
        assert "sitemaps:" in doc["reason"]

    def test_summary_prints_counts_coverage_and_last_downloaded(
        self, tmp_path, monkeypatch, capsys
    ):
        _stub_google_auth(monkeypatch)
        _stub_index_endpoints(
            monkeypatch, indexed_urls={"https://www.mastermind-x.com/"})

        doc = collect_index_status(
            tmp_path, info=_sa_info(), prop=_DEFAULT_PROPERTY,
            as_of_iso="2026-07-20", pace_s=0,
        )
        _print_index_summary(doc)
        out = capsys.readouterr().out

        assert "indexed   : 1 of 10 inspected" in out
        assert "URL is unknown to Google" in out
        assert "Submitted and indexed" in out
        assert "2026-07-23T04:02:55.000Z" in out          # sitemap last download
        assert "never downloaded by Google" in out
        assert "last_crawl=2026-07-19T11:22:33Z" in out
        assert "last_crawl=never" in out


class TestIndexAnnotations:
    def test_zero_indexed_warns_at_line_start(self, capsys):
        doc = {
            "available": True,
            "property": _DEFAULT_PROPERTY,
            "sitemaps": {"sitemaps": [
                {"path": "s.xml", "lastDownloaded": "2026-07-23T04:02:55.000Z"}
            ]},
            "urls": [
                {"url": "u1", "indexed": False, "error": None},
                {"url": "u2", "indexed": False, "error": None},
            ],
        }
        _emit_index_annotations(doc)
        lines = _annotation_lines(capsys.readouterr().out)

        assert len(lines) == 1, lines
        assert lines[0].startswith("::warning title=gsc-index-status::")
        assert "0 of 2 inspected URLs are indexed" in lines[0]
        assert "2026-07-23T04:02:55.000Z" in lines[0]

    def test_some_indexed_emits_a_notice(self, capsys):
        doc = {
            "available": True,
            "property": _DEFAULT_PROPERTY,
            "sitemaps": {"sitemaps": [
                {"path": "s.xml", "lastDownloaded": "2026-07-23T04:02:55.000Z"}
            ]},
            "urls": [
                {"url": "u1", "indexed": True, "error": None},
                {"url": "u2", "indexed": False, "error": None},
            ],
        }
        _emit_index_annotations(doc)
        lines = _annotation_lines(capsys.readouterr().out)

        assert len(lines) == 1, lines
        assert lines[0].startswith("::notice title=gsc-index-status::")
        assert "1 of 2 inspected URLs indexed" in lines[0]

    def test_never_downloaded_sitemap_says_never(self, capsys):
        doc = {
            "available": True,
            "property": _DEFAULT_PROPERTY,
            "sitemaps": {"sitemaps": [{"path": "s.xml", "lastDownloaded": None}]},
            "urls": [{"url": "u1", "indexed": False, "error": None}],
        }
        _emit_index_annotations(doc)
        lines = _annotation_lines(capsys.readouterr().out)
        assert lines[0].startswith("::warning title=gsc-index-status::")
        assert "sitemap last downloaded: never" in lines[0]

    def test_unavailable_warns_with_the_reason(self, capsys):
        doc = {
            "available": False, "property": _DEFAULT_PROPERTY,
            "reason": "sitemaps: boom", "sitemaps": {"sitemaps": []}, "urls": [],
        }
        _emit_index_annotations(doc)
        lines = _annotation_lines(capsys.readouterr().out)
        assert len(lines) == 1
        assert lines[0].startswith("::warning title=gsc-index-status::")
        assert "sitemaps: boom" in lines[0]

    def test_run_emits_the_annotation_end_to_end(self, tmp_path, monkeypatch, capsys):
        _stub_google_auth(monkeypatch)
        monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
        monkeypatch.delenv("GSC_SA_JSON", raising=False)
        _stub_index_endpoints(monkeypatch)
        monkeypatch.setattr(
            "engine.marketing.seo_search_console._gsc_query",
            lambda *a, **k: {"rows": []},
        )
        creds_file = _write_creds(tmp_path)

        run(tmp_path, creds_path=str(creds_file), as_of=_AS_OF, write=True,
            pace_s=0)

        lines = _annotation_lines(capsys.readouterr().out)
        hit = [ln for ln in lines if "gsc-index-status" in ln]
        assert hit, f"no index-status annotation among {lines}"
        assert hit[0].startswith("::warning title=gsc-index-status::")
        assert "0 of 10 inspected URLs are indexed" in hit[0]


class TestIndexStatusSecretHygiene:
    def test_nothing_the_sweep_emits_contains_the_private_key(
        self, tmp_path, monkeypatch, capsys
    ):
        """Artifact + stdout + reason, all three, across a failing sweep."""
        _stub_google_auth(monkeypatch)
        monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
        monkeypatch.delenv("GSC_SA_JSON", raising=False)
        creds_file = _write_creds(tmp_path)

        def _boom(*a, **k):
            raise RuntimeError("upstream said: " + _PRIVATE_KEY)

        monkeypatch.setattr(
            "engine.marketing.seo_search_console._sitemaps_get", _boom)
        monkeypatch.setattr(
            "engine.marketing.seo_search_console._inspect_post", _boom)
        monkeypatch.setattr(
            "engine.marketing.seo_search_console._gsc_query",
            lambda *a, **k: {"rows": []},
        )

        state = run(tmp_path, creds_path=str(creds_file), as_of=_AS_OF,
                    write=True, pace_s=0)
        from engine.marketing.seo_search_console import _print_summary
        _print_summary(state, tmp_path / _ARTIFACTS_REL)

        blob = capsys.readouterr().out + json.dumps(state, default=str)
        for name in [_STATE_FILE, _INDEX_STATUS_FILE, _SCORECARD_FILE, _GAPS_FILE]:
            p = tmp_path / _ARTIFACTS_REL / name
            if p.exists():
                blob += p.read_text()

        assert "NEVER_LEAK_THIS_STRING" not in blob
        assert "BEGIN PRIVATE KEY" not in blob
        # ...while the SAFE identity fields ARE surfaced, on purpose.
        assert _CLIENT_EMAIL in blob


# ---------------------------------------------------------------------------
# Tests: the HTTP layer itself carries the status
#
# The TestStatusReasons cases above stub _gsc_query and raise GscApiError by
# hand, so they say nothing about whether a REAL 403 response ever becomes one.
# (Mutation check: replacing GscApiError with a bare RuntimeError in
# _raise_for_status left all of TestStatusReasons green.)  These drive the
# transport for real, with requests.get/post monkeypatched.
# ---------------------------------------------------------------------------


#: Bound at import time, BEFORE the _no_live_calls autouse fixture swaps the
#: module attributes — these are the genuine transport functions.
from engine.marketing.seo_search_console import (  # noqa: E402
    _gsc_query as _REAL_GSC_QUERY,
    _inspect_post as _REAL_INSPECT_POST,
    _sitemaps_get as _REAL_SITEMAPS_GET,
)


class _FakeResponse:
    def __init__(self, status_code, payload=None, reason="", raises=False):
        self.status_code = status_code
        self._payload = payload
        self.reason = reason
        self._raises = raises

    def json(self):
        if self._raises:
            raise ValueError("not json")
        return self._payload


def _google_error(message: str, status: str = "PERMISSION_DENIED") -> dict:
    return {"error": {"code": 403, "message": message, "status": status}}


class TestTransportStatusMapping:
    def test_403_response_becomes_a_gscapierror_with_status(self, monkeypatch):
        import requests

        body = _google_error(
            "User does not have sufficient permission for site "
            "'sc-domain:mastermind-x.com'."
        )
        monkeypatch.setattr(
            requests, "post",
            lambda *a, **k: _FakeResponse(403, body, reason="Forbidden"))

        with pytest.raises(GscApiError) as exc:
            _REAL_GSC_QUERY("TOK", _DEFAULT_PROPERTY, "2026-07-01", "2026-07-20",
                            ("date",), "web", 0, 100)

        assert exc.value.status == 403
        assert "sufficient permission" in str(exc.value)

    def test_404_response_becomes_a_gscapierror_with_status(self, monkeypatch):
        import requests

        monkeypatch.setattr(
            requests, "get",
            lambda *a, **k: _FakeResponse(
                404, {"error": {"code": 404, "message": "Site not found."}}))

        with pytest.raises(GscApiError) as exc:
            _REAL_SITEMAPS_GET("TOK", _DEFAULT_PROPERTY)
        assert exc.value.status == 404
        assert "Site not found." in str(exc.value)

    def test_unparseable_error_body_falls_back_to_reason(self, monkeypatch):
        import requests

        monkeypatch.setattr(
            requests, "post",
            lambda *a, **k: _FakeResponse(
                500, raises=True, reason="Internal Server Error"))

        with pytest.raises(GscApiError) as exc:
            _REAL_INSPECT_POST("TOK", _DEFAULT_PROPERTY, "https://x.test/")
        assert exc.value.status == 500
        assert "Internal Server Error" in str(exc.value)

    def test_2xx_passes_through(self, monkeypatch):
        import requests

        monkeypatch.setattr(
            requests, "post",
            lambda *a, **k: _FakeResponse(200, _inspect_payload()))

        payload = _REAL_INSPECT_POST("TOK", _DEFAULT_PROPERTY,
                                     "https://www.mastermind-x.com/")
        assert payload["inspectionResult"]["indexStatusResult"]["verdict"] == "PASS"

    def test_live_403_reaches_the_actionable_reason_end_to_end(
        self, tmp_path, monkeypatch, capsys
    ):
        """The whole chain: HTTP 403 -> GscApiError(403) -> operator instruction."""
        import requests

        _stub_google_auth(monkeypatch)
        monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
        monkeypatch.delenv("GSC_SA_JSON", raising=False)
        creds_file = _write_creds(tmp_path)

        monkeypatch.setattr(
            requests, "post",
            lambda *a, **k: _FakeResponse(
                403, _google_error("User does not have sufficient permission.")))

        state = run(tmp_path, creds_path=str(creds_file), as_of=_AS_OF,
                    write=True, pace_s=0)

        assert state["available"] is False
        assert "add it as a user in Search Console" in state["reason"]
        assert _CLIENT_EMAIL in state["reason"]
        lines = _annotation_lines(capsys.readouterr().out)
        assert any(ln.startswith("::warning title=gsc-no-access::") for ln in lines)

    def test_live_404_reaches_the_property_reason_end_to_end(
        self, tmp_path, monkeypatch, capsys
    ):
        import requests

        _stub_google_auth(monkeypatch)
        monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
        monkeypatch.delenv("GSC_SA_JSON", raising=False)
        creds_file = _write_creds(tmp_path)

        monkeypatch.setattr(
            requests, "post",
            lambda *a, **k: _FakeResponse(
                404, {"error": {"code": 404, "message": "Site not found."}}))

        state = run(tmp_path, creds_path=str(creds_file), as_of=_AS_OF,
                    write=True, pace_s=0)

        assert "DOMAIN property" in state["reason"]
        lines = _annotation_lines(capsys.readouterr().out)
        assert any(
            ln.startswith("::warning title=gsc-property-not-found::")
            for ln in lines
        )


class TestInspectBudgetCap:
    def test_cap_holds_when_the_core_set_grows(self, tmp_path, monkeypatch):
        """The 12-URL cap must bind, not merely coincide with today's core set.

        10 core paths + 2 blog posts == 12 exactly, so the slice is invisible
        until someone adds an eleventh core page.  (Mutation check: deleting the
        slice left every other TestCoreUrlSet case green.)
        """
        monkeypatch.setattr(
            "engine.marketing.seo_search_console._CORE_INSPECT_PATHS",
            tuple([""] + [f"p{i}.html" for i in range(25)]),
        )
        _write_sitemap(tmp_path, [
            (f"https://www.mastermind-x.com/blog/b{i}.html", f"2026-07-0{i}")
            for i in range(1, 4)
        ])
        urls = _core_inspect_urls(tmp_path, _DEFAULT_PROPERTY)
        assert len(urls) == _MAX_INSPECT_URLS
        assert urls[0] == "https://www.mastermind-x.com/"

    def test_cap_never_exceeds_the_daily_quota_headroom(self):
        """2000 inspections/day; one weekly run of 12 is ~0.6% of a single day."""
        assert _MAX_INSPECT_URLS <= 12
