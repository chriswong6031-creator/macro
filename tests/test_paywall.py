"""Hermetic contract tests for the fail-closed paid static-site wall."""
from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from app import paywall
from app.main import app

client = TestClient(app, follow_redirects=False)
UID = "11111111-1111-1111-1111-111111111111"


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    monkeypatch.delenv("PAYWALL_ENABLED", raising=False)
    monkeypatch.delenv("PAYWALL_GRACE_SECONDS", raising=False)
    monkeypatch.delenv("PAYWALL_ENTITLEMENT_CACHE_SECONDS", raising=False)
    paywall._AUTH_CACHE.clear()
    paywall._ENT_CACHE.clear()
    paywall._CONFIG_CACHE = None


def _check(path="/neuralwebdata/ruling_graph.json", kind="asset", cookies=None):
    return client.get(
        "/api/paywall/check",
        headers={"X-Original-Uri": path, "X-Original-Kind": kind},
        cookies=cookies or {},
    )


def _arm(monkeypatch):
    monkeypatch.setenv("PAYWALL_ENABLED", "1")
    monkeypatch.setattr("app.main._mm_supabase_access_token", lambda request: "tok")
    monkeypatch.setattr(paywall, "_fresh_uid", lambda token: UID)


def test_staged_off_allows_premium_but_is_never_cacheable():
    r = _check()
    assert r.status_code == 204
    assert r.headers["x-paywall"] == "off"
    assert r.headers["cache-control"] == "private, no-store"


def test_internal_preview_is_404_even_while_switch_off():
    r = _check("/_mockup_research_vault.html", "document")
    assert r.status_code == 404
    assert r.headers["x-paywall"] == "not-found"


def test_free_registered_path_does_not_require_paid_feature(monkeypatch):
    _arm(monkeypatch)
    monkeypatch.setattr(paywall, "_fresh_uid", lambda token: (_ for _ in ()).throw(AssertionError))
    assert _check("/news.html", "document").status_code == 204
    assert _check("/news/latest.json", "asset").status_code == 204


@pytest.mark.parametrize("path", ["/macro.html", "/start.html", "/us_stocks.html"])
def test_public_dashboard_shells_never_require_paid_feature(monkeypatch, path):
    _arm(monkeypatch)
    monkeypatch.setattr(paywall, "_fresh_uid", lambda token: (_ for _ in ()).throw(AssertionError))
    assert paywall.classify_path(path) == "public"
    assert _check(path, "document").status_code == 204


def test_active_site_full_allows(monkeypatch):
    _arm(monkeypatch)
    monkeypatch.setattr(
        paywall,
        "_store_entitlement",
        lambda uid: ({"tier": "essential", "status": "active", "features": ["site_full"]}, True),
    )
    r = _check()
    assert r.status_code == 204
    assert r.headers["x-paywall"] == "allow-essential"


@pytest.mark.parametrize(
    "row",
    [
        {"tier": "free", "status": "active", "features": []},
        {"tier": "essential", "status": "past_due", "features": ["site_full"]},
        {"tier": "pro", "status": "active", "features": []},
        {"tier": "pro", "status": "canceled", "features": ["site_full"]},
    ],
)
def test_non_entitled_rows_fail_closed(monkeypatch, row):
    _arm(monkeypatch)
    monkeypatch.setattr(paywall, "_store_entitlement", lambda uid: (row, True))
    r = _check()
    assert r.status_code == 403
    assert r.json()["locked"] is True
    assert r.json()["required_feature"] == "site_full"


def test_document_denial_is_self_contained_bilingual_html(monkeypatch):
    _arm(monkeypatch)
    monkeypatch.setattr(
        paywall,
        "_store_entitlement",
        lambda uid: ({"tier": "free", "status": "none", "features": []}, True),
    )
    r = _check("/committee.html", "document")
    assert r.status_code == 403
    assert "Insider members" in r.text
    assert "会员" in r.text
    assert "text/html" in r.headers["content-type"]
    assert r.headers["cache-control"] == "private, no-store"


def test_missing_or_invalid_auth_never_uses_entitlement_grace(monkeypatch):
    monkeypatch.setenv("PAYWALL_ENABLED", "1")
    monkeypatch.setattr("app.main._mm_supabase_access_token", lambda request: None)
    paywall._ENT_CACHE[UID] = paywall._EntitlementVerdict(True, "pro", "active", 1.0, 10**12)
    assert _check().status_code == 403


def test_store_outage_graces_only_recent_positive(monkeypatch):
    _arm(monkeypatch)
    clock = [1000.0]
    monkeypatch.setattr(paywall.time, "monotonic", lambda: clock[0])
    monkeypatch.setenv("PAYWALL_ENTITLEMENT_CACHE_SECONDS", "5")
    monkeypatch.setenv("PAYWALL_GRACE_SECONDS", "100")
    state = {"reachable": True}

    def store(uid):
        if state["reachable"]:
            return {"tier": "pro", "status": "trialing", "features": ["site_full"]}, True
        return None, False

    monkeypatch.setattr(paywall, "_store_entitlement", store)
    assert _check().status_code == 204
    state["reachable"] = False
    clock[0] += 6
    assert _check().status_code == 204
    paywall.invalidate_entitlement(UID)
    assert _check().status_code == 403


def test_enforced_early_payload_locks_free_while_switch_off(monkeypatch):
    """/premiumdata/* is the tier-preview payload lane: gated NOW, not at launch."""
    monkeypatch.setattr("app.main._mm_supabase_access_token", lambda request: "tok")
    monkeypatch.setattr(paywall, "_fresh_uid", lambda token: UID)
    monkeypatch.setattr(
        paywall,
        "_store_entitlement",
        lambda uid: ({"tier": "free", "status": "none", "features": []}, True),
    )
    r = _check("/premiumdata/special_situations.json", "asset")
    assert r.status_code == 403
    assert r.json()["locked"] is True
    assert r.json()["upgrade_url"] == "/plans.html?upgrade=1"
    # the same switch-off request on any other premium path still stages open
    assert _check("/neuralwebdata/ruling_graph.json", "asset").status_code == 204


def test_enforced_early_payload_allows_entitled_while_switch_off(monkeypatch):
    monkeypatch.setattr("app.main._mm_supabase_access_token", lambda request: "tok")
    monkeypatch.setattr(paywall, "_fresh_uid", lambda token: UID)
    monkeypatch.setattr(
        paywall,
        "_store_entitlement",
        lambda uid: ({"tier": "essential", "status": "trialing", "features": ["site_full"]}, True),
    )
    r = _check("/premiumdata/special_situations.json", "asset")
    assert r.status_code == 204
    assert r.headers["x-paywall"] == "allow-essential"


def test_enforced_early_anon_payload_locks(monkeypatch):
    monkeypatch.setattr("app.main._mm_supabase_access_token", lambda request: None)
    assert _check("/premiumdata/special_situations.json", "asset").status_code == 403


def test_tier_preview_shell_is_free_but_its_payload_is_not(monkeypatch):
    """The pattern's two halves: free shell at the page URL, gated payload."""
    _arm(monkeypatch)
    monkeypatch.setattr(
        paywall,
        "_store_entitlement",
        lambda uid: ({"tier": "free", "status": "none", "features": []}, True),
    )
    assert paywall.classify_path("/special_situations.html") == "free"
    assert _check("/special_situations.html", "document").status_code == 204
    assert paywall.enforced_early("/premiumdata/special_situations.json") is True
    assert _check("/premiumdata/special_situations.json", "asset").status_code == 403


def test_malformed_enforced_early_policy_denies(monkeypatch):
    _arm(monkeypatch)
    monkeypatch.setattr(
        paywall,
        "_load_config",
        lambda: (_ for _ in ()).throw(ValueError("premium.enforced_early must be a mapping")),
    )
    assert _check("/premiumdata/special_situations.json").status_code == 403


def test_policy_load_failure_denies(monkeypatch):
    _arm(monkeypatch)
    monkeypatch.setattr(paywall, "_load_config", lambda: (_ for _ in ()).throw(ValueError("bad")))
    assert _check().status_code == 403


@pytest.mark.parametrize("path", ["//evil.test/x", "/a/../index.html", "/bad%00.json", "/a\\b.json"])
def test_noncanonical_paths_deny(monkeypatch, path):
    _arm(monkeypatch)
    assert _check(path).status_code == 403


# ===========================================================================
# The 'insider' alias (rename migration, Phase 2 — the direction REVERSED)
# ===========================================================================
def test_pre_rename_row_allows_exactly_like_the_canonical_one(monkeypatch):
    """An entitlement row still carrying the PRE-RENAME value is the same customer as one
    carrying the current wire value — and those rows are never back-filled. The wall gates
    on the FEATURE, so this passes on its own; the assertion that matters is that the alias
    never becomes a THIRD outcome."""
    _arm(monkeypatch)
    monkeypatch.setattr(
        paywall,
        "_store_entitlement",
        lambda uid: ({"tier": "essential", "status": "active", "features": ["site_full"]}, True),
    )
    r = _check()
    assert r.status_code == 204
    assert r.headers["x-paywall"].startswith("allow-")


@pytest.mark.parametrize(
    "row",
    [
        {"tier": "insider", "status": "past_due", "features": ["site_full"]},
        {"tier": "insider", "status": "active", "features": []},
    ],
)
def test_pre_rename_rows_fail_closed_wherever_the_canonical_one_does(monkeypatch, row):
    _arm(monkeypatch)
    monkeypatch.setattr(paywall, "_store_entitlement", lambda uid: (row, True))
    r = _check()
    assert r.status_code == 403
    assert r.json()["locked"] is True


def test_account_plan_label_reads_essential_for_both_keys():
    """The account pill (site/account.js renders plan_label) must name the CURRENT product
    for both spellings — config/plans.yml names it 'Essential', and
    app/billing_emails.plan_name() already reads that name onto every receipt."""
    from app.main import _PLAN_LABELS

    assert _PLAN_LABELS["essential"] == "Essential"
    assert _PLAN_LABELS["insider"] == "Essential"
    assert _PLAN_LABELS["pro"] == "Pro"


def test_brain_allowance_never_drops_a_pre_rename_paying_row_to_free():
    """The silent failure lib/tiers.py exists to prevent: _get_allowance selects
    quotas[tier] if tier in quotas else quotas['free'], so an unrecognised tier does not
    raise — it hands a paying customer the free 5-a-week bucket. After the flip the bucket
    is keyed `essential`, so the row that would land there is the grandfathered one."""
    from engine.neuralweb import brain_gateway as gw

    for lane in ("fast", "pro"):
        assert (gw._get_allowance("insider", "active", lane)
                == gw._get_allowance("essential", "active", lane))
    free_fast = gw._get_allowance("free", "active", "fast")
    assert gw._get_allowance("insider", "active", "fast") != free_fast
