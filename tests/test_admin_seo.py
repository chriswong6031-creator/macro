"""tests/test_admin_seo.py — Fail-soft panel tests for admin.marketing.seo().

Mirrors the harness in test_admin_marketing.py: fixture roots seed the four
Beacon SEO artifacts under data/marketing/seo/, and the panel is invoked with
root=tmp_path so it reads the fixture rather than the repo.

The director-state read reaches for the GitHub API. To keep the tests hermetic
(no network, no token dependency) every test that exercises seo() patches
admin.github_api.token to return None — which is also the honest real-world
day-0 state (docket §11.1: unknown ≠ off). One test patches it to a live token
to prove the director-state branch surfaces enabled/paused correctly.

Assertions:
  - day-0 (no files)        → ok:True, available:False, honest note
  - seeded audit + orders   → correct fields surface, available:True
  - corrupt JSON            → the outer try/except is NOT tripped by a single
                              unreadable artifact (fail-soft read), but a
                              genuinely broken invocation returns ok:False
  - history parsing         → jsonl lines parsed, malformed line skipped
  - director state          → null when no token; true/false when readable
  - search console          → always the explicit "not connected" slot
"""
from __future__ import annotations

import json

import pytest

from admin import marketing


# ---------------------------------------------------------------------------
# Fixtures — artifacts authored here, independent of the engine lane.
# ---------------------------------------------------------------------------

AUDIT = {
    "schema": "seo_audit.v1",
    "as_of": "2026-07-20",
    "health_score": 78,
    "census": {
        "total_pages": 1500,
        "by_family": {
            "core": {"pages": 40, "with_canonical": 40, "with_desc": 38,
                     "with_og": 40, "with_jsonld": 12, "in_sitemap": 40},
            "stocks": {"pages": 1460, "with_canonical": 1460, "with_desc": 900,
                       "with_og": 1200, "with_jsonld": 1460, "in_sitemap": 1455},
        },
    },
    "sitemap": {
        "total_urls": 1500, "core": 40, "stocks": 1460,
        "host_ok": True, "bad_host_count": 0,
        "orphans_in_sitemap": ["https://x/a", "https://x/b"],
        "missing_from_sitemap": ["https://x/c"],
        "duplicates": [],
    },
    "crawl_infra": {
        "robots_ok": True, "robots_sitemap_host_ok": True,
        "llms_txt_present": True, "brand_facts_present": True,
        "brand_facts_age_days": 5,
    },
    "issues": [
        {"id": "i1", "severity": "high", "class": "meta_desc", "page": "/p1", "detail": "missing"},
        {"id": "i2", "severity": "medium", "class": "og", "page": "/p2", "detail": "missing og:image"},
        {"id": "i3", "severity": "low", "class": "jsonld", "page": "/p3", "detail": "no jsonld"},
    ],
}

ORDERS = {
    "schema": "seo_work_orders.v1",
    "as_of": "2026-07-20",
    "orders": [
        {"id": "wo1", "priority": 1, "title": "Add meta descriptions to 600 stock pages",
         "class": "meta_desc", "severity": "high", "pages": ["/s/AAPL", "/s/MSFT"],
         "suggested_fix": "Emit <meta name=description> from the dossier summary.",
         "falsifiable_check": "grep -L 'name=\"description\"' site/s/*.html == []"},
        {"id": "wo2", "priority": 2, "title": "Backfill JSON-LD on core pages",
         "class": "jsonld", "severity": "medium", "pages": ["/about"],
         "suggested_fix": "Add Organization schema block.",
         "falsifiable_check": "every core page emits application/ld+json"},
    ],
}

SCORECARD = {
    "schema": "seo_scorecard.v1",
    "as_of": "2026-07-20",
    "health_score": 78,
    "issue_counts_by_severity": {"critical": 0, "high": 1, "medium": 1, "low": 1},
    "deltas_vs_prior": {"health_score": 4},
    "families_summary": {"core": "ok", "stocks": "improving"},
}

HISTORY_LINES = [
    json.dumps({"as_of": "2026-07-13", "health_score": 70,
                "issues": {"critical": 1, "high": 3, "medium": 5, "low": 8}, "total_pages": 1480}),
    json.dumps({"as_of": "2026-07-16", "health_score": 74,
                "issues": {"critical": 0, "high": 2, "medium": 4, "low": 6}, "total_pages": 1490}),
    "{ this is not valid json",  # malformed line — must be skipped, not fatal
    json.dumps({"as_of": "2026-07-20", "health_score": 78,
                "issues": {"critical": 0, "high": 1, "medium": 1, "low": 1}, "total_pages": 1500}),
]


def _seed_dir(tmp_path):
    d = tmp_path / "data" / "marketing" / "seo"
    d.mkdir(parents=True)
    return d


@pytest.fixture()
def no_token(monkeypatch):
    """Force the director-state read to the honest 'no token → unknown' branch.

    Patches at the source module so the lazy import inside _seo_director_state
    picks up the stub.
    """
    from admin import github_api
    monkeypatch.setattr(github_api, "token", lambda: None)
    return None


@pytest.fixture()
def seeded_root(tmp_path, no_token):
    d = _seed_dir(tmp_path)
    (d / "seo_audit.json").write_text(json.dumps(AUDIT), encoding="utf-8")
    (d / "seo_work_orders.json").write_text(json.dumps(ORDERS), encoding="utf-8")
    (d / "seo_scorecard.json").write_text(json.dumps(SCORECARD), encoding="utf-8")
    (d / "seo_history.jsonl").write_text("\n".join(HISTORY_LINES) + "\n", encoding="utf-8")
    return tmp_path


@pytest.fixture()
def empty_root(tmp_path, no_token):
    """No SEO artifacts at all (day-0)."""
    return tmp_path


# ---------------------------------------------------------------------------
# Day-0 (no artifacts)
# ---------------------------------------------------------------------------

class TestDayZero:
    def test_available_false_with_note(self, empty_root):
        r = marketing.seo(empty_root)
        assert r["ok"] is True
        assert r["available"] is False
        assert r.get("note")  # a plain-word accruing note
        assert "seo-director.yml" in r["note"] or "Sunday" in r["note"]

    def test_null_sections_not_zeroed(self, empty_root):
        r = marketing.seo(empty_root)
        # Missing data is null / empty, never a fake-healthy zero.
        assert r["health_score"] is None
        assert r["census"] is None
        assert r["sitemap"] is None
        assert r["crawl_infra"] is None
        assert r["issues"] == []
        assert r["work_orders"] == []

    def test_search_console_slot_present_day0(self, empty_root):
        r = marketing.seo(empty_root)
        sc = r["search_console"]
        assert sc["connected"] is False
        assert "unavailable" in sc["note"].lower()

    def test_does_not_raise(self, empty_root):
        # Belt-and-suspenders: never raise on an empty root.
        assert isinstance(marketing.seo(empty_root), dict)


# ---------------------------------------------------------------------------
# Seeded (artifacts present)
# ---------------------------------------------------------------------------

class TestSeeded:
    def test_available_and_top_fields(self, seeded_root):
        r = marketing.seo(seeded_root)
        assert r["ok"] is True
        assert r["available"] is True
        assert r["as_of"] == "2026-07-20"
        assert r["health_score"] == 78

    def test_census_surfaces(self, seeded_root):
        r = marketing.seo(seeded_root)
        c = r["census"]
        assert c["total_pages"] == 1500
        assert set(c["by_family"].keys()) == {"core", "stocks"}
        assert c["by_family"]["stocks"]["with_jsonld"] == 1460

    def test_sitemap_and_infra(self, seeded_root):
        r = marketing.seo(seeded_root)
        assert r["sitemap"]["host_ok"] is True
        assert r["sitemap"]["orphans_in_sitemap"] == ["https://x/a", "https://x/b"]
        assert r["crawl_infra"]["brand_facts_age_days"] == 5

    def test_issues_and_orders(self, seeded_root):
        r = marketing.seo(seeded_root)
        assert len(r["issues"]) == 3
        # work_orders is unwrapped from the {"orders": [...]} envelope.
        assert isinstance(r["work_orders"], list)
        assert len(r["work_orders"]) == 2
        assert r["work_orders"][0]["falsifiable_check"]

    def test_scorecard_deltas(self, seeded_root):
        r = marketing.seo(seeded_root)
        sc = r["scorecard"]
        assert sc["issue_counts_by_severity"]["high"] == 1
        assert sc["deltas_vs_prior"]["health_score"] == 4

    def test_search_console_never_healthy(self, seeded_root):
        # Even with a full audit, GSC stays explicitly unavailable — not zeroed.
        r = marketing.seo(seeded_root)
        assert r["search_console"]["connected"] is False


# ---------------------------------------------------------------------------
# History parsing
# ---------------------------------------------------------------------------

class TestHistory:
    def test_parses_valid_lines_skips_malformed(self, seeded_root):
        r = marketing.seo(seeded_root)
        h = r["history"]
        # 3 valid lines, 1 malformed dropped.
        assert len(h) == 3
        assert [row["health_score"] for row in h] == [70, 74, 78]
        assert h[-1]["issues"]["high"] == 1

    def test_history_available_even_without_audit(self, tmp_path, no_token):
        # History can start accruing before the first full audit.
        d = _seed_dir(tmp_path)
        (d / "seo_history.jsonl").write_text(HISTORY_LINES[0] + "\n", encoding="utf-8")
        r = marketing.seo(tmp_path)
        assert r["available"] is False
        assert len(r["history"]) == 1


# ---------------------------------------------------------------------------
# Corrupt / fail-soft
# ---------------------------------------------------------------------------

class TestFailSoft:
    def test_corrupt_audit_degrades_to_day0(self, tmp_path, no_token):
        # A single unreadable artifact must not raise — _read_json returns None,
        # so a corrupt audit reads as "no audit yet" (available:False), never a crash.
        d = _seed_dir(tmp_path)
        (d / "seo_audit.json").write_text("{ not json at all", encoding="utf-8")
        r = marketing.seo(tmp_path)
        assert r["ok"] is True
        assert r["available"] is False

    def test_hard_error_returns_ok_false(self, tmp_path, no_token, monkeypatch):
        # If the read layer itself blows up unexpectedly, the panel returns the
        # ok:False error envelope rather than propagating.
        def boom(_path):
            raise RuntimeError("disk on fire")
        monkeypatch.setattr(marketing, "_read_json", boom)
        r = marketing.seo(tmp_path)
        assert r["ok"] is False
        assert "error" in r


# ---------------------------------------------------------------------------
# Director state (honest unknown; readable true/false)
# ---------------------------------------------------------------------------

class TestDirectorState:
    def test_unknown_when_no_token(self, seeded_root):
        # no_token fixture is active via seeded_root.
        r = marketing.seo(seeded_root)
        dir_ = r["director"]
        assert dir_["enabled"] is None          # unknown, NOT off
        assert dir_.get("note")

    def test_enabled_true_when_variable_true(self, tmp_path, monkeypatch):
        from admin import github_api
        monkeypatch.setattr(github_api, "token", lambda: "tok")
        monkeypatch.setattr(github_api, "get_repo_variable", lambda name: "true")
        _seed_dir(tmp_path)
        r = marketing.seo(tmp_path)
        assert r["director"]["enabled"] is True

    def test_enabled_false_when_variable_false(self, tmp_path, monkeypatch):
        from admin import github_api
        monkeypatch.setattr(github_api, "token", lambda: "tok")
        monkeypatch.setattr(github_api, "get_repo_variable", lambda name: "false")
        _seed_dir(tmp_path)
        r = marketing.seo(tmp_path)
        assert r["director"]["enabled"] is False

    def test_unset_variable_defaults_off(self, tmp_path, monkeypatch):
        # D12A R5: workflow gate is `vars.SEO_DIRECTOR_ENABLED == 'true'`, so an
        # unset variable means scheduled runs stay dark (opt-in, CODEX_MODE
        # pattern). The admin must mirror the gate, never claim armed-when-dark.
        from admin import github_api
        monkeypatch.setattr(github_api, "token", lambda: "tok")
        monkeypatch.setattr(github_api, "get_repo_variable", lambda name: None)
        _seed_dir(tmp_path)
        r = marketing.seo(tmp_path)
        assert r["director"]["enabled"] is False
        assert "not set" in r["director"]["note"]
        assert "manual" in r["director"]["note"].lower()
