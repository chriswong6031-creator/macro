"""tests/test_seo_director.py — Tests for engine.marketing.seo_director.

Builds a fixture mini-site in tmp_path and asserts:
  - Issues detected with right severity and class
  - health_score in (0, 100) and drops when more issues injected
  - Artifacts written atomically with correct schema keys
  - History appends (2 runs -> 2 lines)
  - Scorecard deltas computed on 2nd run
  - No writes outside tmp_path
  - CLI --dry-run writes nothing

Follows MM_DATA_GUARD: ALL writes go to tmp_path only.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from engine.marketing.seo_director import (  # noqa: E402
    audit_site,
    classify_page,
    run,
    SITE_BASE,
    _ARTIFACTS_REL,
    _AUDIT_FILE,
    _WORK_ORDERS_FILE,
    _SCORECARD_FILE,
    _HISTORY_FILE,
)

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

_CANONICAL_HOST = "https://mastermind-x.com"  # site currently uses non-www
_WRONG_HOST_CANONICAL = "https://evil-site.com"

_GOOD_PAGE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<title>Good Core Page — Macro Regime Dashboard</title>
<meta name="description" content="A thorough meta description that is long enough to pass the 50-char minimum and doesn't exceed 170 chars.">
<link rel="canonical" href="{canonical_host}/good.html">
<meta property="og:title" content="Good Core Page">
<meta property="og:description" content="OG description here for sharing.">
<meta property="og:image" content="{canonical_host}/apple-touch-icon.png">
</head>
<body>
<a href="good.html">self</a>
<a href="other.html">other</a>
</body>
</html>
"""

_MISSING_DESC_PAGE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<title>No Description Page Title Here</title>
<link rel="canonical" href="{canonical_host}/nodesc.html">
<meta property="og:title" content="No Desc">
<meta property="og:description" content="OG only">
<meta property="og:image" content="{canonical_host}/img.png">
</head>
<body></body>
</html>
"""

_WRONG_HOST_PAGE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<title>Wrong Canonical Host Page Title!</title>
<meta name="description" content="Description is here and it is long enough to pass validation checks.">
<link rel="canonical" href="{wrong_host}/wronghost.html">
<meta property="og:title" content="Wrong Host">
<meta property="og:description" content="OG desc">
<meta property="og:image" content="{canonical_host}/img.png">
</head>
<body></body>
</html>
"""

_FUND_PAGE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<title>AKO Capital — Fund Dossier — 13F</title>
<meta name="description" content="AKO Capital fund dossier with 13F holdings analysis, sector exposure, and portfolio changes updated quarterly.">
<link rel="canonical" href="{canonical_host}/fund_ako.html">
<meta property="og:title" content="AKO Capital Fund Dossier">
<meta property="og:description" content="AKO Capital fund dossier">
<meta property="og:image" content="{canonical_host}/img.png">
</head>
<body></body>
</html>
"""

_BROKEN_LINK_PAGE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<title>Broken Link Page Title Here!</title>
<meta name="description" content="Description here long enough to pass the fifty character minimum threshold.">
<link rel="canonical" href="{canonical_host}/broken_links.html">
<meta property="og:title" content="Broken">
<meta property="og:description" content="OG desc">
<meta property="og:image" content="{canonical_host}/img.png">
</head>
<body>
<a href="nonexistent_target_page.html">broken link</a>
</body>
</html>
"""

_STOCKS_SAMPLE_PAGE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<title>AAPL — Apple Inc.: signals & factor profile</title>
<meta name="description" content="AAPL (Apple Inc.) signals, options positioning, factor profile updated nightly.">
<link rel="canonical" href="{canonical_host}/stocks/AAPL.html">
<meta property="og:title" content="AAPL Apple">
<meta property="og:description" content="AAPL signals">
<meta property="og:image" content="{canonical_host}/stocks/AAPL.png">
</head>
<body></body>
</html>
"""

_ROBOTS_TXT = """\
User-agent: *
Allow: /

Sitemap: {canonical_host}/sitemap.xml
"""

_ROBOTS_TXT_BLOCKING = """\
User-agent: *
Disallow: /
"""

_BRAND_FACTS_FRESH = json.dumps({
    "schema": "brand-facts.v1",
    "effective_at": "2026-07-01",
    "brand": "Mastermind",
})

_BRAND_FACTS_STALE = json.dumps({
    "schema": "brand-facts.v1",
    "effective_at": "2020-01-01",
    "brand": "Mastermind",
})


def _sitemap_xml(urls: list[str]) -> str:
    locs = "\n".join(f"  <url><loc>{u}</loc></url>" for u in urls)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{locs}
</urlset>
"""


def _build_mini_site(
    tmp_path: Path,
    *,
    canonical_host: str = _CANONICAL_HOST,
    include_llms: bool = True,
    brand_facts_content: str | None = None,
    robots_content: str | None = None,
    extra_sitemap_urls: list[str] | None = None,
    include_sitemap: bool = True,
    include_robots: bool = True,
) -> Path:
    """Build a mini site in tmp_path/site/ and return site_dir."""
    site = tmp_path / "site"
    site.mkdir(parents=True)

    ch = canonical_host

    # Core pages
    (site / "good.html").write_text(
        _GOOD_PAGE.format(canonical_host=ch), encoding="utf-8"
    )
    (site / "other.html").write_text(
        _GOOD_PAGE.format(canonical_host=ch).replace("good.html", "other.html").replace(
            "Good Core Page", "Other Core Page"), encoding="utf-8"
    )
    (site / "nodesc.html").write_text(
        _MISSING_DESC_PAGE.format(canonical_host=ch), encoding="utf-8"
    )
    (site / "wronghost.html").write_text(
        _WRONG_HOST_PAGE.format(canonical_host=ch, wrong_host=_WRONG_HOST_CANONICAL),
        encoding="utf-8",
    )
    (site / "broken_links.html").write_text(
        _BROKEN_LINK_PAGE.format(canonical_host=ch), encoding="utf-8"
    )

    # Fund page
    (site / "fund_ako.html").write_text(
        _FUND_PAGE.format(canonical_host=ch), encoding="utf-8"
    )

    # stocks/ sample
    stocks_dir = site / "stocks"
    stocks_dir.mkdir()
    (stocks_dir / "AAPL.html").write_text(
        _STOCKS_SAMPLE_PAGE.format(canonical_host=ch), encoding="utf-8"
    )

    # sitemap.xml — includes one orphan URL
    if include_sitemap:
        sitemap_urls = [
            f"{ch}/good.html",
            f"{ch}/other.html",
            f"{ch}/nodesc.html",
            f"{ch}/wronghost.html",
            f"{ch}/broken_links.html",
            f"{ch}/fund_ako.html",
            f"{ch}/orphan_that_does_not_exist.html",  # orphan
            f"{ch}/stocks/AAPL.html",
        ]
        if extra_sitemap_urls:
            sitemap_urls.extend(extra_sitemap_urls)
        (site / "sitemap.xml").write_text(_sitemap_xml(sitemap_urls), encoding="utf-8")

    # robots.txt
    if include_robots:
        robots = robots_content or _ROBOTS_TXT.format(canonical_host=ch)
        (site / "robots.txt").write_text(robots, encoding="utf-8")

    # llms.txt
    if include_llms:
        (site / "llms.txt").write_text("# Mastermind AI access\n", encoding="utf-8")

    # brand-facts.json
    if brand_facts_content is not None:
        (site / "brand-facts.json").write_text(brand_facts_content, encoding="utf-8")
    else:
        (site / "brand-facts.json").write_text(_BRAND_FACTS_FRESH, encoding="utf-8")

    return site


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestClassifyPage:
    def test_stocks(self):
        assert classify_page("stocks/AAPL") == "stocks"

    def test_fund(self):
        assert classify_page("fund_ako") == "fund"

    def test_strategy(self):
        assert classify_page("strategy_btc") == "strategy"

    def test_report(self):
        assert classify_page("report_haven") == "report"

    def test_utility_mockup(self):
        assert classify_page("_mockup_credit_desk") == "utility"

    def test_utility_chat(self):
        assert classify_page("chat") == "utility"

    def test_utility_calibration(self):
        assert classify_page("calibration") == "utility"

    def test_core_default(self):
        assert classify_page("macro") == "core"
        assert classify_page("index") == "core"


class TestIssueDetection:
    def test_wrong_host_canonical_detected_as_critical(self, tmp_path):
        site = _build_mini_site(tmp_path)
        result = audit_site(site)
        issues = result["issues"]
        wrong_host = [i for i in issues if i["class"] == "canonical_wrong_host"]
        assert len(wrong_host) >= 1
        assert all(i["severity"] == "critical" for i in wrong_host)

    def test_missing_desc_detected_as_high_for_core(self, tmp_path):
        site = _build_mini_site(tmp_path)
        result = audit_site(site)
        issues = result["issues"]
        missing_desc = [i for i in issues if i["class"] == "missing_description"]
        assert len(missing_desc) >= 1
        # nodesc.html is a core page
        pages = [i["page"] for i in missing_desc]
        assert any("nodesc" in p for p in pages)
        core_issue = next(i for i in missing_desc if "nodesc" in i["page"])
        assert core_issue["severity"] == "high"

    def test_sitemap_orphan_detected_as_critical(self, tmp_path):
        site = _build_mini_site(tmp_path)
        result = audit_site(site)
        issues = result["issues"]
        orphans = [i for i in issues if i["class"] == "sitemap_orphan"]
        assert len(orphans) >= 1
        assert all(i["severity"] == "critical" for i in orphans)
        # The orphan URL should be in the issues
        assert any("orphan_that_does_not_exist" in i["detail"] for i in orphans)

    def test_broken_internal_link_detected_as_high(self, tmp_path):
        site = _build_mini_site(tmp_path)
        result = audit_site(site)
        issues = result["issues"]
        broken = [i for i in issues if i["class"] == "broken_internal_link"]
        assert len(broken) >= 1
        assert all(i["severity"] == "high" for i in broken)
        assert any("nonexistent_target_page" in i["detail"] for i in broken)

    def test_orphan_in_sitemap_field(self, tmp_path):
        site = _build_mini_site(tmp_path)
        result = audit_site(site)
        orphans = result["sitemap"]["orphans_in_sitemap"]
        assert len(orphans) >= 1
        assert any("orphan_that_does_not_exist" in u for u in orphans)

    def test_missing_from_sitemap_detected(self, tmp_path):
        # Add a page not in sitemap
        site = _build_mini_site(tmp_path)
        extra = site / "extra_page.html"
        extra.write_text(
            _GOOD_PAGE.format(canonical_host=_CANONICAL_HOST).replace(
                "good.html", "extra_page.html"
            ).replace("Good Core Page", "Extra Core Page"),
            encoding="utf-8",
        )
        result = audit_site(site)
        missing = result["sitemap"]["missing_from_sitemap"]
        assert any("extra_page" in p for p in missing)

    def test_no_llms_txt_flagged_as_low(self, tmp_path):
        site = _build_mini_site(tmp_path, include_llms=False)
        result = audit_site(site)
        llms_issues = [i for i in result["issues"] if i["class"] == "missing_llms_txt"]
        assert len(llms_issues) == 1
        assert llms_issues[0]["severity"] == "low"

    def test_stale_brand_facts_flagged_as_low(self, tmp_path):
        site = _build_mini_site(tmp_path, brand_facts_content=_BRAND_FACTS_STALE)
        result = audit_site(site)
        bf_issues = [i for i in result["issues"] if i["class"] == "brand_facts_stale"]
        assert len(bf_issues) == 1
        assert bf_issues[0]["severity"] == "low"

    def test_robots_blocking_flagged_as_critical(self, tmp_path):
        site = _build_mini_site(tmp_path, robots_content=_ROBOTS_TXT_BLOCKING)
        result = audit_site(site)
        block_issues = [i for i in result["issues"] if i["class"] == "robots_blocks_all"]
        assert len(block_issues) >= 1
        assert block_issues[0]["severity"] == "critical"

    def test_missing_robots_flagged(self, tmp_path):
        site = _build_mini_site(tmp_path, include_robots=False)
        result = audit_site(site)
        rob_issues = [i for i in result["issues"] if i["class"] == "missing_robots"]
        assert len(rob_issues) >= 1

    def test_missing_sitemap_flagged_as_critical(self, tmp_path):
        site = _build_mini_site(tmp_path, include_sitemap=False)
        result = audit_site(site)
        sm_issues = [i for i in result["issues"] if i["class"] == "missing_sitemap"]
        assert len(sm_issues) == 1
        assert sm_issues[0]["severity"] == "critical"

    def test_fund_page_detected(self, tmp_path):
        site = _build_mini_site(tmp_path)
        result = audit_site(site)
        census = result["census"]["by_family"]
        assert census["fund"]["pages"] >= 1


class TestHealthScore:
    def test_health_score_in_valid_range(self, tmp_path):
        site = _build_mini_site(tmp_path)
        result = audit_site(site)
        score = result["health_score"]
        assert 0 < score < 100

    def test_health_score_drops_with_more_issues(self, tmp_path):
        """Adding wrong-host canonicals should lower health score."""
        # Baseline: healthy mini site (all valid canonicals)
        site_good = tmp_path / "site_good"
        site_good.mkdir()
        # Write just good pages
        ch = _CANONICAL_HOST
        (site_good / "good.html").write_text(
            _GOOD_PAGE.format(canonical_host=ch), encoding="utf-8"
        )
        (site_good / "other.html").write_text(
            _GOOD_PAGE.format(canonical_host=ch).replace("good.html", "other.html").replace(
                "Good Core Page", "Other Core Page"), encoding="utf-8"
        )
        (site_good / "sitemap.xml").write_text(
            _sitemap_xml([f"{ch}/good.html", f"{ch}/other.html"]), encoding="utf-8"
        )
        (site_good / "robots.txt").write_text(_ROBOTS_TXT.format(canonical_host=ch), encoding="utf-8")
        (site_good / "llms.txt").write_text("# llms\n", encoding="utf-8")
        (site_good / "brand-facts.json").write_text(_BRAND_FACTS_FRESH, encoding="utf-8")

        # Worse: add wrong-host canonical page
        site_bad = tmp_path / "site_bad"
        site_bad.mkdir()
        (site_bad / "good.html").write_text(
            _GOOD_PAGE.format(canonical_host=ch), encoding="utf-8"
        )
        (site_bad / "wronghost.html").write_text(
            _WRONG_HOST_PAGE.format(canonical_host=ch, wrong_host=_WRONG_HOST_CANONICAL),
            encoding="utf-8",
        )
        (site_bad / "sitemap.xml").write_text(
            _sitemap_xml([f"{ch}/good.html", f"{ch}/wronghost.html"]), encoding="utf-8"
        )
        (site_bad / "robots.txt").write_text(_ROBOTS_TXT.format(canonical_host=ch), encoding="utf-8")
        (site_bad / "llms.txt").write_text("# llms\n", encoding="utf-8")
        (site_bad / "brand-facts.json").write_text(_BRAND_FACTS_FRESH, encoding="utf-8")

        score_good = audit_site(site_good)["health_score"]
        score_bad = audit_site(site_bad)["health_score"]
        assert score_bad < score_good, (
            f"Expected bad score ({score_bad}) < good score ({score_good})"
        )


class TestArtifacts:
    def test_artifacts_written_with_correct_schema_keys(self, tmp_path):
        site = _build_mini_site(tmp_path)
        run(tmp_path, write=True)

        seo_dir = tmp_path / _ARTIFACTS_REL
        # seo_audit.json
        audit_path = seo_dir / _AUDIT_FILE
        assert audit_path.exists(), f"Missing {audit_path}"
        audit = json.loads(audit_path.read_text())
        assert audit["schema"] == "seo_audit.v1"
        assert "as_of" in audit
        assert "health_score" in audit
        assert "census" in audit
        assert "sitemap" in audit
        assert "crawl_infra" in audit
        assert "issues" in audit
        assert isinstance(audit["issues"], list)

        # seo_work_orders.json
        wo_path = seo_dir / _WORK_ORDERS_FILE
        assert wo_path.exists()
        wo = json.loads(wo_path.read_text())
        assert wo["schema"] == "seo_work_orders.v1"
        assert "orders" in wo
        assert isinstance(wo["orders"], list)
        if wo["orders"]:
            order = wo["orders"][0]
            assert "id" in order
            assert "priority" in order
            assert "severity" in order
            assert "suggested_fix" in order
            assert "falsifiable_check" in order

        # seo_scorecard.json
        sc_path = seo_dir / _SCORECARD_FILE
        assert sc_path.exists()
        sc = json.loads(sc_path.read_text())
        assert sc["schema"] == "seo_scorecard.v1"
        assert "health_score" in sc
        assert "issue_counts_by_severity" in sc

        # seo_history.jsonl — 1 line after first run
        hist_path = seo_dir / _HISTORY_FILE
        assert hist_path.exists()
        lines = [l for l in hist_path.read_text().splitlines() if l.strip()]
        assert len(lines) == 1
        hl = json.loads(lines[0])
        assert "as_of" in hl
        assert "health_score" in hl
        assert "issues" in hl
        assert "total_pages" in hl

    def test_history_appends_two_runs(self, tmp_path):
        site = _build_mini_site(tmp_path)
        run(tmp_path, write=True)
        run(tmp_path, write=True)

        hist_path = tmp_path / _ARTIFACTS_REL / _HISTORY_FILE
        lines = [l for l in hist_path.read_text().splitlines() if l.strip()]
        assert len(lines) == 2

    def test_scorecard_deltas_on_second_run(self, tmp_path):
        site = _build_mini_site(tmp_path)
        run(tmp_path, write=True)
        # Second run — deltas should be non-None
        run(tmp_path, write=True)

        sc_path = tmp_path / _ARTIFACTS_REL / _SCORECARD_FILE
        sc = json.loads(sc_path.read_text())
        assert sc["deltas_vs_prior"] is not None
        assert "health_score" in sc["deltas_vs_prior"]
        assert "critical" in sc["deltas_vs_prior"]

    def test_first_run_scorecard_deltas_null(self, tmp_path):
        site = _build_mini_site(tmp_path)
        run(tmp_path, write=True)

        sc_path = tmp_path / _ARTIFACTS_REL / _SCORECARD_FILE
        sc = json.loads(sc_path.read_text())
        # First run has no prior — deltas should be null
        assert sc["deltas_vs_prior"] is None


class TestNoWritesOutsideTmpPath:
    def test_dry_run_writes_nothing(self, tmp_path):
        """--dry-run must leave data/marketing/seo/ empty."""
        site = _build_mini_site(tmp_path)
        run(tmp_path, write=False)
        seo_dir = tmp_path / _ARTIFACTS_REL
        # None of the artifact files should exist
        assert not (seo_dir / _AUDIT_FILE).exists()
        assert not (seo_dir / _WORK_ORDERS_FILE).exists()
        assert not (seo_dir / _SCORECARD_FILE).exists()
        assert not (seo_dir / _HISTORY_FILE).exists()

    def test_run_writes_only_under_tmp(self, tmp_path, monkeypatch):
        """Artifacts written by run() must be within tmp_path."""
        site = _build_mini_site(tmp_path)
        written_paths: list[Path] = []

        import engine.marketing.seo_director as seo_mod
        original_write = seo_mod._write_json_atomic
        original_append = seo_mod._append_jsonl

        def tracking_write(path: Path, obj):
            written_paths.append(path.resolve())
            original_write(path, obj)

        def tracking_append(path: Path, obj):
            written_paths.append(path.resolve())
            original_append(path, obj)

        monkeypatch.setattr(seo_mod, "_write_json_atomic", tracking_write)
        monkeypatch.setattr(seo_mod, "_append_jsonl", tracking_append)

        run(tmp_path, write=True)

        repo_root = REPO_ROOT.resolve()
        for p in written_paths:
            assert p.is_relative_to(tmp_path.resolve()), (
                f"Unexpected write outside tmp_path: {p}"
            )


class TestCLI:
    def test_cli_dry_run_no_artifacts(self, tmp_path):
        """CLI --dry-run: prints summary, no files written."""
        site = _build_mini_site(tmp_path)
        result = subprocess.run(
            [sys.executable, "-m", "engine.marketing.seo_director",
             "--root", str(tmp_path), "--dry-run"],
            capture_output=True, text=True, cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0, f"CLI crashed: {result.stderr}"
        assert "health" in result.stdout.lower()
        # No artifacts written
        seo_dir = tmp_path / _ARTIFACTS_REL
        assert not (seo_dir / _AUDIT_FILE).exists()

    def test_cli_exits_zero_on_findings(self, tmp_path):
        """CLI must exit 0 even when critical issues exist."""
        site = _build_mini_site(tmp_path)
        result = subprocess.run(
            [sys.executable, "-m", "engine.marketing.seo_director",
             "--root", str(tmp_path), "--dry-run"],
            capture_output=True, text=True, cwd=str(REPO_ROOT),
        )
        # Critical issues will be present (wrong-host canonical, orphan) — still exit 0
        assert result.returncode == 0

    def test_cli_warning_lines_for_critical(self, tmp_path):
        """CLI emits ::warning:: lines for critical issues."""
        site = _build_mini_site(tmp_path)
        result = subprocess.run(
            [sys.executable, "-m", "engine.marketing.seo_director",
             "--root", str(tmp_path), "--dry-run"],
            capture_output=True, text=True, cwd=str(REPO_ROOT),
        )
        assert "::warning::" in result.stdout


class TestStocksHandling:
    def test_stocks_not_audited_individually(self, tmp_path):
        """stocks/ files should not produce per-page issues; aggregate only."""
        site = _build_mini_site(tmp_path)
        result = audit_site(site)
        # No issue should reference stocks/AAPL.html for missing-canonical etc
        # (stocks are sampled, not individually audited for all checks)
        non_canonical_stock_issues = [
            i for i in result["issues"]
            if "stocks/AAPL" in i["page"]
            and i["class"] not in ("canonical_wrong_host",)
        ]
        # Stock sample pages with wrong host ARE reported, but no missing-desc/title individually
        assert all(
            i["class"] == "canonical_wrong_host"
            for i in non_canonical_stock_issues
        ), f"Unexpected non-sample issue on stocks page: {non_canonical_stock_issues}"

    def test_stocks_census_entry_has_sampled_field(self, tmp_path):
        site = _build_mini_site(tmp_path)
        result = audit_site(site)
        stocks_census = result["census"]["by_family"]["stocks"]
        assert "sampled" in stocks_census
        assert stocks_census["pages"] >= 1


class TestSitemapLogic:
    def test_sitemap_census_fields(self, tmp_path):
        site = _build_mini_site(tmp_path)
        result = audit_site(site)
        sm = result["sitemap"]
        assert sm["total_urls"] > 0
        assert "orphans_in_sitemap" in sm
        assert "missing_from_sitemap" in sm
        assert "duplicates" in sm

    def test_duplicate_sitemap_url_detected(self, tmp_path):
        site = _build_mini_site(
            tmp_path,
            extra_sitemap_urls=[f"{_CANONICAL_HOST}/good.html"],  # duplicate
        )
        result = audit_site(site)
        assert len(result["sitemap"]["duplicates"]) >= 1
        dup_issues = [i for i in result["issues"] if i["class"] == "sitemap_duplicates"]
        assert len(dup_issues) >= 1


class TestCrawlInfra:
    def test_crawl_infra_fields_present(self, tmp_path):
        site = _build_mini_site(tmp_path)
        result = audit_site(site)
        ci = result["crawl_infra"]
        assert "robots_ok" in ci
        assert "llms_txt_present" in ci
        assert "brand_facts_present" in ci
        assert "brand_facts_age_days" in ci

    def test_brand_facts_age_computed(self, tmp_path):
        site = _build_mini_site(tmp_path, brand_facts_content=_BRAND_FACTS_FRESH)
        as_of = datetime(2026, 7, 20, tzinfo=timezone.utc)
        result = audit_site(site, as_of=as_of)
        ci = result["crawl_infra"]
        assert ci["brand_facts_present"] is True
        # 2026-07-01 to 2026-07-20 = 19 days
        assert ci["brand_facts_age_days"] == 19


class TestHostSemanticsR1:
    """R1: canonical host is www. Apex must be flagged, not silently accepted."""

    def test_apex_sitemap_host_flagged_not_masked(self, tmp_path):
        # Fixture uses the apex (non-www) host for sitemap URLs.
        site = _build_mini_site(tmp_path)
        result = audit_site(site)
        # host_ok must be FALSE — apex is not canonical.
        assert result["sitemap"]["host_ok"] is False
        assert result["sitemap"]["apex_host_count"] >= 1
        # bad_host_count is foreign-only; apex is our host, so it stays 0 here.
        assert result["sitemap"]["bad_host_count"] == 0
        apex_issues = [i for i in result["issues"] if i["class"] == "sitemap_apex_host"]
        assert len(apex_issues) >= 1
        assert apex_issues[0]["severity"] == "high"

    def test_apex_robots_sitemap_host_not_ok(self, tmp_path):
        site = _build_mini_site(tmp_path)  # robots Sitemap: uses apex host
        result = audit_site(site)
        assert result["crawl_infra"]["robots_sitemap_host_ok"] is False
        apex_rob = [i for i in result["issues"] if i["class"] == "robots_sitemap_apex_host"]
        assert len(apex_rob) >= 1
        assert apex_rob[0]["severity"] == "high"

    def test_www_canonical_host_accepted_as_ok(self, tmp_path):
        # When the site uses the www canonical host, host_ok must be TRUE and no apex flag.
        site = _build_mini_site(tmp_path, canonical_host="https://www.mastermind-x.com")
        result = audit_site(site)
        assert result["sitemap"]["host_ok"] is True
        assert result["sitemap"]["apex_host_count"] == 0
        assert result["crawl_infra"]["robots_sitemap_host_ok"] is True
        assert not [i for i in result["issues"] if i["class"] == "sitemap_apex_host"]
        assert not [i for i in result["issues"] if i["class"] == "canonical_non_www"]

    def test_foreign_host_stays_critical(self, tmp_path):
        # A genuinely foreign host in the sitemap is a critical wrong-host defect.
        site = _build_mini_site(
            tmp_path, extra_sitemap_urls=["https://evil-site.com/x.html"]
        )
        result = audit_site(site)
        bad = [i for i in result["issues"] if i["class"] == "sitemap_bad_host"]
        assert len(bad) >= 1
        assert bad[0]["severity"] == "critical"
        assert result["sitemap"]["bad_host_count"] >= 1


class TestLinkResolver:
    """The href resolver must not cry wolf on non-static / non-broken links."""

    def _audit_page_with_body(self, tmp_path, body_links: str):
        site = tmp_path / "site"
        site.mkdir(parents=True)
        page = f"""<!DOCTYPE html>
<html lang="en">
<head><title>Link Resolver Test Page Title</title>
<meta name="description" content="A description long enough to pass the fifty character validation minimum here.">
<link rel="canonical" href="https://www.mastermind-x.com/lr.html">
<meta property="og:title" content="LR"><meta property="og:description" content="d">
<meta property="og:image" content="https://www.mastermind-x.com/i.png"></head>
<body>{body_links}</body></html>"""
        (site / "lr.html").write_text(page, encoding="utf-8")
        # a real neighbour + a real subdir target — CLEAN (no test links in their bodies,
        # else the broken href would be counted once per page and defeat the per-page dedup test)
        clean = page.replace(body_links, "")
        (site / "real.html").write_text(clean, encoding="utf-8")
        sub = site / "basket"
        sub.mkdir()
        (sub / "ai_agents.html").write_text(clean, encoding="utf-8")
        return audit_site(site)

    def test_js_template_href_not_flagged(self, tmp_path):
        links = (
            '<a href="basket/${t.id}.html">tmpl1</a>'
            '<a href="${BASE}${encodeURIComponent(t.id)}.html">tmpl2</a>'
            '<a href="${_bbase()}${esc(x.tid)}.html">tmpl3</a>'
        )
        result = self._audit_page_with_body(tmp_path, links)
        broken = [i for i in result["issues"] if i["class"] == "broken_internal_link"]
        assert broken == [], f"Template-literal hrefs must not be flagged: {broken}"

    def test_fragment_query_external_not_flagged(self, tmp_path):
        links = (
            '<a href="#section">frag</a>'
            '<a href="real.html?x=1">query</a>'
            '<a href="mailto:a@b.com">mail</a>'
            '<a href="tel:+123">tel</a>'
            '<a href="javascript:void(0)">js</a>'
            '<a href="//cdn.example.com/x.html">protorel</a>'
            '<a href="https://www.mastermind-x.com/real.html">abs-self</a>'
            '<a href="basket/">dir</a>'
        )
        result = self._audit_page_with_body(tmp_path, links)
        broken = [i for i in result["issues"] if i["class"] == "broken_internal_link"]
        assert broken == [], f"Non-static / non-.html hrefs must not be flagged: {broken}"

    def test_real_relative_and_subdir_links_pass(self, tmp_path):
        links = '<a href="real.html">ok</a><a href="basket/ai_agents.html">ok-sub</a>'
        result = self._audit_page_with_body(tmp_path, links)
        broken = [i for i in result["issues"] if i["class"] == "broken_internal_link"]
        assert broken == [], f"Existing targets must not be flagged: {broken}"

    def test_genuinely_broken_link_still_flagged(self, tmp_path):
        result = self._audit_page_with_body(tmp_path, '<a href="does_not_exist.html">x</a>')
        broken = [i for i in result["issues"] if i["class"] == "broken_internal_link"]
        assert len(broken) == 1
        assert "does_not_exist" in broken[0]["detail"]

    def test_duplicate_broken_href_deduped_per_page(self, tmp_path):
        links = '<a href="gone.html">a</a><a href="gone.html">b</a><a href="gone.html">c</a>'
        result = self._audit_page_with_body(tmp_path, links)
        broken = [i for i in result["issues"] if i["class"] == "broken_internal_link"]
        assert len(broken) == 1, "Same broken target should report once per page"


class TestHonestCounts:
    """Counts and health score must reflect TRUE totals, not the display-capped list."""

    def test_missing_from_sitemap_true_count(self, tmp_path):
        # good/other/nodesc/wronghost/broken_links/fund_ako are in the fixture sitemap;
        # add several pages NOT in the sitemap and assert the honest count includes all.
        site = _build_mini_site(tmp_path)
        for i in range(6):
            (site / f"loose_{i}.html").write_text(
                _GOOD_PAGE.format(canonical_host=_CANONICAL_HOST).replace(
                    "good.html", f"loose_{i}.html"
                ).replace("Good Core Page", f"Loose Page {i}"),
                encoding="utf-8",
            )
        result = audit_site(site)
        # 6 loose pages must all be counted (field is a capped sample, count is honest).
        assert result["sitemap"]["missing_from_sitemap_count"] >= 6

    def test_severity_counts_are_uncapped(self, tmp_path):
        # Force more issues than the display cap by writing many broken-link pages.
        site = tmp_path / "site"
        site.mkdir(parents=True)
        n = 260  # > _MAX_ISSUES (200)
        for i in range(n):
            (site / f"p{i}.html").write_text(
                f'<html lang="en"><head><title>Page {i} title long enough here</title>'
                f'<meta name="description" content="Description for page {i} that is '
                f'well beyond the fifty character minimum length requirement.">'
                f'<link rel="canonical" href="https://www.mastermind-x.com/p{i}.html">'
                f'<meta property="og:title" content="t"><meta property="og:description" content="d">'
                f'<meta property="og:image" content="i.png"></head>'
                f'<body><a href="missing_{i}.html">broken</a></body></html>',
                encoding="utf-8",
            )
        result = audit_site(site)
        # Display list is capped, but the TRUE severity tally must count all broken links.
        assert len(result["issues"]) <= 200
        assert result["issue_counts_by_severity"]["high"] >= n
        assert result["_issues_truncated_count"] > 0

    def test_score_keeps_dropping_past_display_cap(self, tmp_path):
        """Health score must reflect issues beyond _MAX_ISSUES (no plateau at the cap)."""
        def _site_with_broken(n: int) -> Path:
            root = tmp_path / f"s{n}"
            site = root / "site"
            site.mkdir(parents=True)
            for i in range(n):
                (site / f"p{i}.html").write_text(
                    f'<html lang="en"><head><title>Page {i} title long enough here</title>'
                    f'<meta name="description" content="Description for page {i} that is '
                    f'well beyond the fifty character minimum length requirement here.">'
                    f'<link rel="canonical" href="https://www.mastermind-x.com/p{i}.html">'
                    f'<meta property="og:title" content="t"><meta property="og:description" content="d">'
                    f'<meta property="og:image" content="i.png"></head>'
                    f'<body><a href="missing_{i}.html">broken</a></body></html>',
                    encoding="utf-8",
                )
            return site

        score_250 = audit_site(_site_with_broken(250))["health_score"]
        score_400 = audit_site(_site_with_broken(400))["health_score"]
        # Both far past the 200-issue cap; the larger break count must not score HIGHER.
        assert score_400 <= score_250


class TestWorkOrdersHonesty:
    def test_late_emitted_class_still_gets_order(self, tmp_path):
        """missing_from_sitemap / sitemap_apex_host are emitted LATE and can overflow the
        display cap; they must still produce work orders with true counts."""
        from engine.marketing.seo_director import _build_work_orders

        site = _build_mini_site(tmp_path)  # apex host in sitemap
        # add a page NOT in the sitemap so missing_from_sitemap fires
        (site / "loose.html").write_text(
            _GOOD_PAGE.format(canonical_host=_CANONICAL_HOST).replace(
                "good.html", "loose.html").replace("Good Core Page", "Loose Page"),
            encoding="utf-8",
        )
        audit = audit_site(site)
        wo = _build_work_orders(audit, audit["as_of"])
        classes = {o["class"] for o in wo["orders"]}
        assert "sitemap_apex_host" in classes
        assert "missing_from_sitemap" in classes
        assert len(wo["orders"]) <= 20
        # order count must be the TRUE class count, not the exemplar-list length.
        mfs = next(o for o in wo["orders"] if o["class"] == "missing_from_sitemap")
        assert mfs["pages_count"] == audit["issue_counts_by_class"]["missing_from_sitemap"]
