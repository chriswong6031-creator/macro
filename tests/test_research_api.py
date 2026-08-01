"""Tests for the Research Vault serving API + download gate (RV W2).

SECURITY-CRITICAL surface — these tests are the executable spec the red-team
probes against. They exercise, with NO live R2/Supabase (LocalStore-backed store +
a dependency-overridden auth + a monkeypatched tier resolver):

  * auth: anon → 401 on every paid route.
  * paywall: free/unknown tier → 402 on view AND download (fails CLOSED).
  * view: PRO → 200 inline PDF (does NOT consume the download quota); insider/free
    → 402 paid_required (reading full PDFs is Pro-only; insider is a teaser tier).
  * download quota: PRO gets 10/day then 402 quota_exhausted; insider/free blocked
    (402 paid_required, before the quota check); the counter is server-authoritative
    (increments only on allow); peek() does NOT increment; the day period resets.
  * lifetime allowance: a PRO holding a lifetime (comp, no-period-end) grant gets
    50/day off the SAME day ledger — and the flag never lifts a free/insider 0, so
    it can only raise a cap, never open the paywall.
  * doc_id hardening: traversal / ``..`` / uppercase / slash / unknown id →
    400 or 404, and NEVER a raw R2 fetch of an unvalidated key.
  * watermark: download returns a body whether pypdf/reportlab are present OR
    monkeypatched-absent — never a 500.
  * search: returns rows from a seeded local corpus; catalog read-through returns
    the seeded items.

Requires fastapi + httpx (TestClient). Skips cleanly if either is absent so the
pure-``pytest`` W1 job never reds on this file.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

pytest.importorskip("fastapi", reason="research API tests need fastapi")
pytest.importorskip("httpx", reason="TestClient needs httpx")

from fastapi.testclient import TestClient  # noqa: E402

from engine.research_vault import catalog as catalog_mod  # noqa: E402
from engine.research_vault import corpus as corpus_mod  # noqa: E402
from engine.research_vault import download_quota, view_ratelimit  # noqa: E402
from engine.research_vault.r2_store import LocalStore  # noqa: E402


# ===========================================================================
# fixtures — seeded LocalStore, isolated state dir, stubbed auth + tier
# ===========================================================================

# A minimal valid single-page PDF (real enough for pypdf to parse + watermark).
_MINIMAL_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]>>endobj\n"
    b"trailer<</Root 1 0 R>>\n"
    b"%%EOF\n"
)

_DOC_ID = "bernstein-2026-07-21-dc-pipeline"
_DOC_TITLE = "Data Center Pipeline Probabilities"


def _seed_store(root) -> LocalStore:
    """Build a LocalStore seeded with a catalog, one PDF, and a corpus.sqlite."""
    store = LocalStore(root)

    # Catalog with one known item (existence gate keys off this).
    cat = catalog_mod.empty()
    catalog_mod.upsert_item(cat, {
        "id": _DOC_ID,
        "title": _DOC_TITLE,
        "institution": "Bernstein",
        "side": "sell",
        "desk": "Data Centers",
        "published_at": "2026-07-21T14:00:00Z",
        "summary_points": ["Only 33% of the pipeline is credible."],
        "tags": ["ai", "datacenters"],
        "tickers": ["EQIX"],
        "top_pick": True,
        "pages": 12,
        "needs_metadata": False,
    })
    catalog_mod.write(store, cat)

    # The promoted PDF at the canonical vault key.
    store.put_bytes(f"research_vault/{_DOC_ID}.pdf", _MINIMAL_PDF, "application/pdf")

    # A corpus.sqlite with one searchable body, published to the store key.
    corpus_path = root / "_build_corpus.sqlite"
    conn = corpus_mod.open_db(corpus_path)
    corpus_mod.upsert(
        conn,
        {"id": _DOC_ID, "title": _DOC_TITLE, "institution": "Bernstein",
         "side": "sell", "published_at": "2026-07-21T14:00:00Z",
         "summary_points": ["Only 33% of the pipeline is credible."]},
        "hyperscaler capacity dominates the credible datacenter pipeline in Texas",
    )
    conn.close()
    store.put_bytes("research_vault/corpus.sqlite",
                    corpus_path.read_bytes(), "application/octet-stream")
    return store


@pytest.fixture
def client(tmp_path, monkeypatch):
    """A TestClient with the vault wired to a LocalStore + stubbed auth/tier.

    Yields ``(client, ctl)`` where ``ctl`` lets a test set the current tier and
    the injected ``now`` for the quota routes.
    """
    # Isolate ALL file-based ledger state under tmp (download quota + view RL).
    monkeypatch.setenv("MACRO_API_STATE_DIR", str(tmp_path / "state"))

    store = _seed_store(tmp_path / "store")

    import app.main as main_mod
    import app.research as research_mod

    # Point the router's store factory at our seeded LocalStore (no R2).
    monkeypatch.setattr(research_mod, "_build_store", lambda: store)

    # Reset the module-level catalog/corpus caches between tests (they memoize).
    # The corpus cache moved into engine.research_vault.corpus in W4 (one local
    # copy per PROCESS, shared with the brain's report reader), so it is reset at
    # its new home — resetting it here would otherwise be a silent no-op and the
    # first seeded corpus of the session would decide what every later test reads.
    research_mod._CATALOG_CACHE.clear()
    corpus_mod.reset_cache()

    # Control knobs the tests flip.
    ctl = {"tier": "free", "lifetime": False,
           "user": {"id": "u-test", "email": "buyer@example.com"}}

    # Stub the tier resolver (no Supabase). Fail-closed default is 'free'.
    monkeypatch.setattr(research_mod, "_resolve_tier", lambda uid: ctl["tier"])

    # Stub the lifetime (comp grant / no period end) probe — no Supabase. Default
    # False = the standard Pro allowance, matching the resolver's fail-closed side.
    monkeypatch.setattr(research_mod, "_is_lifetime", lambda uid: ctl["lifetime"])

    # Override the auth dependency: a present stub bearer → ctl['user']; absent → 401.
    from fastapi import Header, HTTPException

    def _stub_require_user(authorization: str | None = Header(default=None)) -> dict:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(401, "missing bearer token")
        return ctl["user"]

    main_mod.app.dependency_overrides[research_mod.require_user] = _stub_require_user

    c = TestClient(main_mod.app)
    try:
        yield c, ctl
    finally:
        main_mod.app.dependency_overrides.pop(research_mod.require_user, None)


_AUTH = {"Authorization": "Bearer stub-token"}


# ===========================================================================
# PUBLIC routes — unauth
# ===========================================================================

def test_catalog_read_through_returns_items(client):
    c, _ = client
    r = c.get("/api/research/catalog")
    assert r.status_code == 200
    body = r.json()
    ids = [it["id"] for it in body.get("items", [])]
    assert _DOC_ID in ids
    assert body["count"] >= 1


def test_catalog_exposes_only_three_summaries_until_pro(client, monkeypatch):
    import app.research as research_mod

    c, _ = client
    catalog = {
        "items": [
            {
                "id": f"report-{i}",
                "title": f"Report {i}",
                "summary_points": [f"Summary {i}"],
            }
            for i in range(5)
        ],
        "count": 5,
    }
    monkeypatch.setattr(research_mod, "_load_catalog", lambda: catalog)

    public = c.get("/api/research/catalog")
    assert public.status_code == 200
    public_body = public.json()
    assert public_body["count"] == 5
    assert public_body["preview"] is True
    assert public_body["summary"]["total"] == 5
    assert public_body["summary"]["new_this_week"] == 0
    assert public_body["summary"]["institutions"] == []
    assert public_body["institutions"] == []
    assert [item["id"] for item in public_body["items"]] == [
        "report-0", "report-1", "report-2",
    ]

    monkeypatch.setattr(research_mod, "_optional_tier", lambda _authorization: "pro")
    pro = c.get("/api/research/catalog", headers=_AUTH)
    assert pro.status_code == 200
    pro_body = pro.json()
    assert pro_body["preview"] is False
    assert pro_body["summary"]["total"] == 5
    assert len(pro_body["items"]) == 5


def test_search_returns_body_hit_from_seeded_corpus(client):
    c, _ = client
    r = c.get("/api/research/search", params={"q": "hyperscaler"})
    assert r.status_code == 200
    body = r.json()
    assert body["available"] is True
    assert any(it["id"] == _DOC_ID for it in body["items"])


def test_search_is_unauth_and_never_500_on_junk(client):
    c, _ = client
    # FTS operators / special chars must degrade, not error.
    for q in ['"; DROP TABLE documents; --', "AND OR NOT (((", "\\\\\x00"]:
        r = c.get("/api/research/search", params={"q": q})
        assert r.status_code == 200
        assert "items" in r.json()


def test_search_limit_is_clamped(client):
    c, _ = client
    r = c.get("/api/research/search", params={"q": "pipeline", "limit": 9999})
    assert r.status_code == 200  # clamped server-side, no error


# ===========================================================================
# AUTH — anon rejected on every paid/authed route
# ===========================================================================

@pytest.mark.parametrize("method,path", [
    ("GET", f"/api/research/view/{_DOC_ID}"),
    ("POST", f"/api/research/download/{_DOC_ID}"),
    ("GET", "/api/research/quota"),
])
def test_anon_gets_401(client, method, path):
    c, _ = client
    r = c.request(method, path)  # no Authorization header
    assert r.status_code == 401


# ===========================================================================
# PAYWALL — free/unknown tier blocked (fails CLOSED)
# ===========================================================================

def test_free_tier_402_on_view(client):
    c, ctl = client
    ctl["tier"] = "free"
    r = c.get(f"/api/research/view/{_DOC_ID}", headers=_AUTH)
    assert r.status_code == 402
    assert r.json()["error"] == "paid_required"
    assert r.json()["upgrade"] == "/plans.html"


def test_free_tier_402_on_download(client):
    c, ctl = client
    ctl["tier"] = "free"
    r = c.post(f"/api/research/download/{_DOC_ID}", headers=_AUTH)
    assert r.status_code == 402
    assert r.json()["error"] == "paid_required"


def test_unknown_tier_treated_as_free_402(client):
    c, ctl = client
    ctl["tier"] = "gibberish-not-a-tier"
    assert c.get(f"/api/research/view/{_DOC_ID}", headers=_AUTH).status_code == 402
    assert c.post(f"/api/research/download/{_DOC_ID}", headers=_AUTH).status_code == 402


def test_effective_tier_status_gate_unit():
    """A paid tier only unlocks when status is active/trialing; else → free.

    (Regression for the paywall bypass where a canceled/lapsed subscriber whose
    entitlement row is flipped-not-deleted kept full vault access.)
    """
    import app.research as research_mod
    et = research_mod._effective_tier
    assert et("pro", "active") == "pro"
    assert et("insider", "trialing") == "insider"
    # Non-active statuses collapse a paid tier to free (fail closed).
    for bad in ("canceled", "past_due", "incomplete", "unpaid", "", None):
        assert et("pro", bad) == "free", f"status {bad!r} must not grant pro"
        assert et("insider", bad) == "free"
    # free stays free regardless of status.
    assert et("free", "active") == "free"
    assert et(None, "active") == "free"


def test_lapsed_paid_subscriber_blocked_via_real_status_gate(client, monkeypatch):
    """End-to-end: a row with tier='pro' but status='canceled' → 402 (not paid).

    The ``client`` fixture stubs ``_resolve_tier`` with a bare-string lambda that
    cannot express the ``{tier, status}`` shape, so it can't see the status bug.
    Here we install a resolver that mirrors the REAL one — it calls the canonical
    (monkeypatched) brain_gateway resolver and passes its result through the real
    ``_effective_tier`` status gate — proving the route honors ``status``.
    """
    import app.research as research_mod
    import engine.neuralweb.brain_gateway as bg

    def _real_like_resolver(user_id):
        ent = bg._resolve_tier(user_id) or {}
        return research_mod._effective_tier(ent.get("tier"), ent.get("status"))

    monkeypatch.setattr(research_mod, "_resolve_tier", _real_like_resolver)

    c, _ctl = client  # ctl['tier'] ignored now — the resolver above drives tier.

    # Lapsed pro (row present, status canceled) → blocked.
    monkeypatch.setattr(bg, "_resolve_tier",
                        lambda uid: {"tier": "pro", "status": "canceled",
                                     "current_period_end": None})
    assert c.get(f"/api/research/view/{_DOC_ID}", headers=_AUTH).status_code == 402
    assert c.post(f"/api/research/download/{_DOC_ID}", headers=_AUTH).status_code == 402

    # Active pro through the SAME real gate → allowed.
    monkeypatch.setattr(bg, "_resolve_tier",
                        lambda uid: {"tier": "pro", "status": "active",
                                     "current_period_end": None})
    assert c.get(f"/api/research/view/{_DOC_ID}", headers=_AUTH).status_code == 200


# ===========================================================================
# VIEW — PRO streams inline PDF (no quota consumed); insider/free → 402
# ===========================================================================

def test_pro_view_streams_pdf_inline(client):
    c, ctl = client
    ctl["tier"] = "pro"
    r = c.get(f"/api/research/view/{_DOC_ID}", headers=_AUTH)
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.headers["content-disposition"] == "inline"
    assert r.headers["cache-control"] == "private, no-store"
    assert "noindex" in r.headers["x-robots-tag"]
    assert r.content.startswith(b"%PDF")


def test_insider_view_402_pro_only(client):
    """Insider is a teaser tier — reading the full PDF requires PRO → 402."""
    c, ctl = client
    ctl["tier"] = "insider"
    r = c.get(f"/api/research/view/{_DOC_ID}", headers=_AUTH)
    assert r.status_code == 402
    body = r.json()
    assert body["error"] == "paid_required"
    assert body["tier"] == "insider"


def test_view_does_not_consume_download_quota(client, tmp_path):
    c, ctl = client
    ctl["tier"] = "pro"
    # Several views…
    for _ in range(3):
        assert c.get(f"/api/research/view/{_DOC_ID}", headers=_AUTH).status_code == 200
    # …leave the download quota fully intact.
    info = download_quota.peek(ctl["user"]["id"], "pro")
    assert info["used"] == 0
    assert info["remaining"] == 10


# ===========================================================================
# DOWNLOAD — PRO-only, metered 10/day, server-authoritative
# ===========================================================================

def test_insider_download_402_pro_only(client):
    """Insider cannot download — the Pro gate 402s before the quota check."""
    c, ctl = client
    ctl["tier"] = "insider"
    r = c.post(f"/api/research/download/{_DOC_ID}", headers=_AUTH)
    assert r.status_code == 402
    assert r.json()["error"] == "paid_required"


def test_pro_gets_10_downloads_then_402(client):
    c, ctl = client
    ctl["tier"] = "pro"
    for i in range(10):
        r = c.post(f"/api/research/download/{_DOC_ID}", headers=_AUTH)
        assert r.status_code == 200, f"download {i} should pass"
        assert r.headers["content-disposition"].startswith("attachment;")
        assert r.headers["cache-control"] == "private, no-store"
        assert "noindex" in r.headers["x-robots-tag"]
        assert r.content.startswith(b"%PDF")
    # 11th is refused server-side regardless of client.
    r11 = c.post(f"/api/research/download/{_DOC_ID}", headers=_AUTH)
    assert r11.status_code == 402
    body = r11.json()
    assert body["error"] == "quota_exhausted"
    assert body["remaining"] == 0
    assert body["limit"] == 10
    assert body["tier"] == "pro"
    assert body["upgrade"] == "/plans.html"


def test_download_attachment_filename_from_title(client):
    c, ctl = client
    ctl["tier"] = "pro"
    r = c.post(f"/api/research/download/{_DOC_ID}", headers=_AUTH)
    assert r.status_code == 200
    cd = r.headers["content-disposition"]
    assert cd.startswith('attachment; filename="')
    assert cd.endswith('.pdf"')


# ===========================================================================
# LIFETIME allowance — a comp/no-period-end PRO gets 50/day, and ONLY a raise
# ===========================================================================

def test_lifetime_pro_quota_reports_50(client):
    """The button's "N of 50 left today" copy reads this limit straight off peek."""
    c, ctl = client
    ctl["tier"], ctl["lifetime"] = "pro", True
    q = c.get("/api/research/quota", headers=_AUTH).json()
    assert q["limit"] == 50
    assert q["remaining"] == 50
    assert q["tier"] == "pro"      # the tier string stays canonical — no new tier leaks


def test_lifetime_pro_gets_50_downloads_then_402(client):
    """The 50th download passes and the 51st is refused server-side.

    The first 49 are spent through the engine API rather than 49 HTTP round-trips —
    same ledger, same day key — so the test proves the BOUNDARY without paying for
    49 PDF watermarks. The 50th and 51st go over HTTP, which is the contract.
    """
    c, ctl = client
    ctl["tier"], ctl["lifetime"] = "pro", True
    uid = ctl["user"]["id"]
    for i in range(49):
        allowed, _ = download_quota.check_and_increment(uid, "pro", lifetime=True)
        assert allowed, f"pre-spend {i} should pass under the lifetime cap"

    r50 = c.post(f"/api/research/download/{_DOC_ID}", headers=_AUTH)
    assert r50.status_code == 200, "the 50th download is still inside the lifetime cap"
    assert r50.content.startswith(b"%PDF")

    r51 = c.post(f"/api/research/download/{_DOC_ID}", headers=_AUTH)
    assert r51.status_code == 402
    body = r51.json()
    assert body["error"] == "quota_exhausted"
    assert body["remaining"] == 0
    assert body["limit"] == 50
    assert body["tier"] == "pro"


def test_lifetime_pro_passes_the_standard_10_download_wall(client):
    """The raise is real end-to-end: download 11 clears the wall a plain Pro hits."""
    c, ctl = client
    ctl["tier"], ctl["lifetime"] = "pro", True
    for i in range(11):
        r = c.post(f"/api/research/download/{_DOC_ID}", headers=_AUTH)
        assert r.status_code == 200, f"download {i} should pass on a lifetime grant"
    q = c.get("/api/research/quota", headers=_AUTH).json()
    assert q["used"] == 11
    assert q["remaining"] == 39


@pytest.mark.parametrize("tier", ["free", "insider"])
def test_lifetime_flag_never_unlocks_a_non_pro_tier(client, tier):
    """SECURITY: the lifetime flag raises a cap; it can never open the paywall.

    A comp row with a null period end is exactly what an admin DOWNGRADE writes, so
    'lifetime' and 'free' co-occur in production. Both the route (402 paid_required,
    ahead of the quota check) and the ledger (limit 0) must hold.
    """
    c, ctl = client
    ctl["tier"], ctl["lifetime"] = tier, True

    r = c.post(f"/api/research/download/{_DOC_ID}", headers=_AUTH)
    assert r.status_code == 402
    assert r.json()["error"] == "paid_required"

    q = c.get("/api/research/quota", headers=_AUTH).json()
    assert q["limit"] == 0
    assert q["remaining"] == 0


def test_lifetime_grant_mid_day_keeps_downloads_already_spent(client):
    """A grant that lands mid-day raises the cap without refunding the day's spend."""
    c, ctl = client
    ctl["tier"] = "pro"
    for _ in range(3):
        assert c.post(f"/api/research/download/{_DOC_ID}", headers=_AUTH).status_code == 200

    ctl["lifetime"] = True  # operator grants the pass; same UTC day, same ledger file
    q = c.get("/api/research/quota", headers=_AUTH).json()
    assert q["used"] == 3
    assert q["limit"] == 50
    assert q["remaining"] == 47


# --- unit level: the promotion rule itself --------------------------------------

@pytest.mark.parametrize("tier,lifetime,expected", [
    ("pro", False, 10),      # standard Pro is untouched
    ("pro", True, 50),       # the raise
    ("free", True, 0),       # …never promotes a zero allowance
    ("insider", True, 0),
    ("bogus", True, 0),      # unknown tier stays blocked
    ("PRO", True, 50),       # tier strings are normalized before the lookup
])
def test_limit_for_promotes_paid_tiers_only(tier, lifetime, expected):
    assert download_quota._limit_for(tier, lifetime) == expected


# --- unit level: the REAL lifetime probe (the route tests stub it) ---------------

_LIFETIME_ROW = {"tier": "pro", "status": "active", "source": "comp",
                 "current_period_end": None}


@pytest.mark.parametrize("row,expected,why", [
    (_LIFETIME_ROW, True, "grant_pass(kind='lifetime') — comp, active, null end"),
    ({**_LIFETIME_ROW, "current_period_end": "2026-08-25T00:00:00Z"}, False,
     "a dated comp pass (monthly/annual) is not lifetime"),
    ({**_LIFETIME_ROW, "source": "stripe"}, False,
     "a Stripe row with a null end is a mid-signup/lapsed row, never a grant"),
    ({**_LIFETIME_ROW, "status": "canceled"}, False,
     "canceled is excluded by the account-panel rule this mirrors"),
    ({"tier": "unlimited", "status": "active", "source": "stripe",
      "current_period_end": None}, True, "the 'unlimited' leg of the canonical rule"),
    ({"tier": "free", "status": "none", "source": "stripe",
      "current_period_end": None}, False, "read_entitlement's free default"),
    ({"tier": "free", "status": "none", "source": "comp",
      "current_period_end": None}, True,
     "an admin downgrade IS comp/no-end — _limit_for is what keeps it at 0"),
])
def test_is_lifetime_matches_the_account_panel_rule(monkeypatch, row, expected, why):
    """`_is_lifetime` must agree with site/theme.js `_sdPlanChip` row for row.

    The last case is the load-bearing one: the probe says True for a downgraded comp
    row (that IS the shape), and the paywall + zero-allowance guard — not this
    function — are what keep such a user at 0 downloads. Tested at the route level in
    ``test_lifetime_flag_never_unlocks_a_non_pro_tier``.
    """
    import app.research as research_mod
    monkeypatch.setattr("app.billing.read_entitlement", lambda uid: dict(row))
    assert research_mod._is_lifetime("u-x") is expected, why


def test_is_lifetime_fails_closed_when_the_lookup_breaks(monkeypatch):
    """A Supabase hiccup costs a holder headroom, never hands anyone access."""
    import app.research as research_mod

    def _boom(uid):
        raise RuntimeError("postgrest down")

    monkeypatch.setattr("app.billing.read_entitlement", _boom)
    assert research_mod._is_lifetime("u-x") is False
    assert research_mod._is_lifetime("") is False


def test_lifetime_for_skips_the_lookup_for_tiers_that_get_zero(monkeypatch):
    """Free/insider never pay for the entitlement read — the cap cannot move."""
    import app.research as research_mod
    calls = []
    monkeypatch.setattr("app.billing.read_entitlement",
                        lambda uid: calls.append(uid) or dict(_LIFETIME_ROW))
    assert research_mod._lifetime_for("free", "u-x") is False
    assert research_mod._lifetime_for("insider", "u-x") is False
    assert calls == []
    assert research_mod._lifetime_for("pro", "u-x") is True
    assert calls == ["u-x"]


def test_peek_and_increment_agree_on_the_lifetime_limit(tmp_path, monkeypatch):
    """peek() must report the same cap check_and_increment() enforces."""
    monkeypatch.setenv("MACRO_API_STATE_DIR", str(tmp_path / "state"))
    uid = "u-lifetime-unit"
    allowed, info = download_quota.check_and_increment(uid, "pro", lifetime=True)
    assert allowed and info["limit"] == 50 and info["used"] == 1
    peeked = download_quota.peek(uid, "pro", lifetime=True)
    assert peeked["limit"] == 50
    assert peeked["used"] == 1
    assert peeked["remaining"] == 49


# ===========================================================================
# QUOTA route — read-only (peek never increments)
# ===========================================================================

def test_quota_peek_does_not_increment(client):
    c, ctl = client
    ctl["tier"] = "pro"
    a = c.get("/api/research/quota", headers=_AUTH).json()
    b = c.get("/api/research/quota", headers=_AUTH).json()
    assert a["used"] == 0 and b["used"] == 0
    assert a["remaining"] == 10 and b["remaining"] == 10
    assert a["limit"] == 10 and a["tier"] == "pro"


def test_quota_reflects_spent_downloads(client):
    c, ctl = client
    ctl["tier"] = "pro"
    c.post(f"/api/research/download/{_DOC_ID}", headers=_AUTH)
    c.post(f"/api/research/download/{_DOC_ID}", headers=_AUTH)
    q = c.get("/api/research/quota", headers=_AUTH).json()
    assert q["used"] == 2
    assert q["remaining"] == 8


def test_quota_free_tier_zero_limit(client):
    c, ctl = client
    ctl["tier"] = "free"
    q = c.get("/api/research/quota", headers=_AUTH).json()
    assert q["limit"] == 0
    assert q["remaining"] == 0


# ===========================================================================
# doc_id hardening — traversal / bad shape / unknown id
# ===========================================================================

@pytest.mark.parametrize("bad", [
    "../../etc/passwd",
    "..%2f..%2fsecret",
    "UPPERCASE-ID",
    "has space",
    "has/slash",
    "-leadinghyphen",
    "with.dot",
    "under_score",
    "x" * 200,  # too long
])
def test_download_bad_doc_id_never_fetches_raw_key(client, monkeypatch, bad):
    c, ctl = client
    ctl["tier"] = "pro"

    # Trip-wire: if the router ever builds an R2 key from an unvalidated id, this
    # spy would see a get_bytes for a *.pdf key. A rejected id must NEVER reach it.
    import app.research as research_mod
    seen_keys = []
    real_store = research_mod._build_store()

    class SpyStore:
        def get_bytes(self, key):
            seen_keys.append(key)
            return real_store.get_bytes(key)

    monkeypatch.setattr(research_mod, "_build_store", lambda: SpyStore())

    r = c.post(f"/api/research/download/{bad}", headers=_AUTH)
    assert r.status_code in (400, 404), f"{bad!r} → {r.status_code}"
    assert not any(k.endswith(".pdf") for k in seen_keys), \
        f"UNVALIDATED id {bad!r} triggered a raw PDF fetch: {seen_keys}"


@pytest.mark.parametrize("bad", ["../../etc/passwd", "UPPER", "has space", "a/b"])
def test_view_bad_doc_id_rejected(client, bad):
    c, ctl = client
    ctl["tier"] = "pro"
    r = c.get(f"/api/research/view/{bad}", headers=_AUTH)
    assert r.status_code in (400, 404)


def test_doc_id_trailing_newline_rejected(client):
    """Regression: a ``$``-anchored regex would let 'id\\n' through (Python ``$``
    matches before a trailing newline) and leak a newline into the R2 key. The
    ``\\Z`` anchor rejects it → 400, never a key build."""
    from urllib.parse import quote
    c, ctl = client
    ctl["tier"] = "pro"
    # %0A is a raw newline appended to an otherwise-valid slug.
    path = "/api/research/view/" + quote(f"{_DOC_ID}\n", safe="")
    r = c.get(path, headers=_AUTH)
    assert r.status_code == 400, f"trailing-newline id must 400, got {r.status_code}"


def test_doc_id_regex_rejects_newline_unit():
    """Unit: the compiled doc_id pattern rejects any trailing-newline id."""
    import app.research as research_mod
    assert research_mod._DOC_ID_RE.match(_DOC_ID) is not None
    assert research_mod._DOC_ID_RE.match(_DOC_ID + "\n") is None
    assert research_mod._DOC_ID_RE.match("ok\n") is None


def test_download_filename_strips_header_injection(client, tmp_path, monkeypatch):
    """A malicious catalog title cannot inject CRLF / quotes into Content-Disposition."""
    import app.research as research_mod
    # Force the title lookup to return a hostile string.
    monkeypatch.setattr(research_mod, "_catalog_title",
                        lambda did: 'evil"\r\nSet-Cookie: x=1')
    c, ctl = client
    ctl["tier"] = "pro"
    r = c.post(f"/api/research/download/{_DOC_ID}", headers=_AUTH)
    assert r.status_code == 200
    cd = r.headers["content-disposition"]
    assert "\r" not in cd and "\n" not in cd
    assert "Set-Cookie" not in cd or ":" not in cd.split("Set-Cookie")[-1][:2]
    assert cd.startswith('attachment; filename="') and cd.endswith('.pdf"')


def test_wellformed_but_unknown_id_is_404(client):
    c, ctl = client
    ctl["tier"] = "pro"
    # Valid slug shape, but not in the catalog → 404, never a fetch attempt result.
    r = c.get("/api/research/view/goldman-2026-01-01-not-ingested", headers=_AUTH)
    assert r.status_code == 404
    r2 = c.post("/api/research/download/goldman-2026-01-01-not-ingested", headers=_AUTH)
    assert r2.status_code == 404


def test_unknown_id_does_not_consume_quota(client):
    c, ctl = client
    ctl["tier"] = "pro"
    c.post("/api/research/download/goldman-2026-01-01-not-ingested", headers=_AUTH)
    # A 404 (bad id) must not have debited the day counter.
    assert download_quota.peek(ctl["user"]["id"], "pro")["used"] == 0


# ===========================================================================
# watermark — libs present AND absent both return a body (never 500)
# ===========================================================================

def test_download_body_when_watermark_libs_present(client):
    c, ctl = client
    ctl["tier"] = "pro"
    r = c.post(f"/api/research/download/{_DOC_ID}", headers=_AUTH)
    assert r.status_code == 200
    assert r.content.startswith(b"%PDF")
    assert len(r.content) > 0


def test_download_body_when_watermark_libs_absent(client, monkeypatch):
    c, ctl = client
    ctl["tier"] = "pro"

    # Simulate pypdf/reportlab absent: force watermark.stamp to hit its degrade path
    # by making the lazy import fail. We patch the module's stamp to exercise the
    # real degrade contract (return original bytes) exactly as the lib-absent path.
    import app.research as research_mod

    def _degraded_stamp(pdf_bytes, text):
        # Mirror watermark.stamp's documented fallback: original bytes, never raise.
        return pdf_bytes

    monkeypatch.setattr(research_mod.watermark, "stamp", _degraded_stamp)
    r = c.post(f"/api/research/download/{_DOC_ID}", headers=_AUTH)
    assert r.status_code == 200
    assert r.content == _MINIMAL_PDF  # un-watermarked original, byte-for-byte


def test_watermark_stamp_unit_degrades_on_bad_pdf():
    """watermark.stamp on non-PDF bytes returns the input unchanged, never raises."""
    from engine.research_vault import watermark as wm
    junk = b"this is not a pdf"
    assert wm.stamp(junk, "footer") == junk
    assert wm.stamp(b"", "footer") == b""


# ===========================================================================
# quota ledger — unit: next-day period reset (injected now)
# ===========================================================================

def test_download_quota_day_period_resets(tmp_path, monkeypatch):
    monkeypatch.setenv("MACRO_API_STATE_DIR", str(tmp_path / "state"))
    day1 = datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc)
    day2 = datetime(2026, 7, 23, 0, 30, tzinfo=timezone.utc)

    # Exhaust pro (10) on day 1.
    for _ in range(10):
        ok, _info = download_quota.check_and_increment("u", "pro", now=day1)
        assert ok
    ok11, info11 = download_quota.check_and_increment("u", "pro", now=day1)
    assert ok11 is False and info11["remaining"] == 0

    # Next day → fresh allowance.
    ok_next, info_next = download_quota.check_and_increment("u", "pro", now=day2)
    assert ok_next is True
    assert info_next["remaining"] == 9
    assert info_next["used"] == 1


def test_download_quota_free_is_zero_and_never_touches_ledger(tmp_path, monkeypatch):
    monkeypatch.setenv("MACRO_API_STATE_DIR", str(tmp_path / "state"))
    ok, info = download_quota.check_and_increment("u", "free")
    assert ok is False
    assert info["limit"] == 0 and info["remaining"] == 0
    # No ledger file should have been created for a zero-limit tier.
    qdir = tmp_path / "state" / "research_download_quota"
    assert not qdir.exists() or not list(qdir.glob("*.json"))


def test_download_quota_fail_open_loud_on_unwritable_dir(tmp_path, monkeypatch, caplog):
    """A broken ledger must fail OPEN (allow) but LOUD (::error::) — availability.

    Exercises the REAL ``_write`` degrade branch: a FILE is planted where the
    quota subdir must live, so ``mkdir(parents=True)`` raises FileExistsError and
    the write's except path fires (fail-open + ``::error::`` log)."""
    import logging
    state = tmp_path / "state"
    state.mkdir()
    monkeypatch.setenv("MACRO_API_STATE_DIR", str(state))
    # Plant a file where research_download_quota/ must be → mkdir raises.
    (state / "research_download_quota").write_text("x")

    with caplog.at_level(logging.ERROR):
        ok, _info = download_quota.check_and_increment("u", "pro")
    assert ok is True  # fail-open: a paying subscriber is NOT locked out
    assert any("::error::" in rec.message and "QUOTA WRITE FAILED" in rec.message
               for rec in caplog.records), "the degrade must log LOUD (::error::)"


# ===========================================================================
# view rate-limit — unit: hourly cap trips, dual user+IP, IP hashed
# ===========================================================================

def test_view_ratelimit_trips_at_cap(tmp_path, monkeypatch):
    monkeypatch.setenv("MACRO_API_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("RESEARCH_VIEW_HOURLY", "3")
    for _ in range(3):
        ok, _info = view_ratelimit.allow("u", "1.2.3.4")
        assert ok
    ok4, info4 = view_ratelimit.allow("u", "1.2.3.4")
    assert ok4 is False
    assert info4["remaining"] == 0
    assert info4["limit"] == 3


def test_view_ratelimit_hashes_ip_in_filename(tmp_path, monkeypatch):
    monkeypatch.setenv("MACRO_API_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("RESEARCH_VIEW_HOURLY", "10")
    view_ratelimit.allow("u", "203.0.113.7")
    rl_dir = tmp_path / "state" / "research_view_rl"
    names = [p.name for p in rl_dir.glob("*.json")]
    # The raw IP must NEVER appear in any ledger filename.
    assert not any("203.0.113.7" in n for n in names), names
    assert any(n.startswith("vip_") for n in names)


def test_view_route_429_when_rate_limited(client, monkeypatch):
    c, ctl = client
    ctl["tier"] = "pro"
    import app.research as research_mod
    # Force the limiter to deny.
    monkeypatch.setattr(research_mod.view_ratelimit, "allow",
                        lambda uid, ip: (False, {"remaining": 0, "limit": 60}))
    r = c.get(f"/api/research/view/{_DOC_ID}", headers=_AUTH)
    assert r.status_code == 429
    assert r.json()["error"] == "rate_limited"


# ===========================================================================
# corpus read-through: serve-stale-while-revalidate (backfill hardening)
# ===========================================================================

def test_corpus_conn_nonblocking_refresh(monkeypatch, tmp_path):
    """A present local corpus is served immediately; a stale one triggers ONE
    background refresh instead of an inline re-download (a backfilled corpus is
    far too large to fetch inside a user's search request).

    The cache state lives in engine.research_vault.corpus since W4 (the router
    delegates so the brain's report reader shares the one local copy), so the
    knobs are pinned there; the route-side entry point under test is unchanged.
    """
    import time as _time
    from app import research as R
    from engine.research_vault import corpus as C

    fetches = {"n": 0}

    class FakeStore:
        def get_bytes(self, key):
            fetches["n"] += 1
            src = tmp_path / f"src{fetches['n']}.sqlite"
            conn = C.open_db(src)
            C.upsert(conn, {"id": f"d{fetches['n']}", "title": "t",
                            "institution": "GS", "published_at": "2026-07-01",
                            "summary_points": [], "side": "sell"}, "body text")
            conn.close()
            return src.read_bytes()

    monkeypatch.setattr(R, "_build_store", lambda: FakeStore())
    monkeypatch.setattr(C, "_corpus_path", None)
    monkeypatch.setattr(C, "_corpus_fetched_at", 0.0)
    monkeypatch.setattr(C, "_corpus_refreshing", False)

    # First call: no local copy -> blocks once, downloads (fetch #1).
    c1 = R._corpus_conn()
    assert c1 is not None
    c1.close()
    assert fetches["n"] == 1

    # Fresh within TTL: served locally, NO store hit.
    c2 = R._corpus_conn()
    assert c2 is not None
    c2.close()
    assert fetches["n"] == 1

    # Force stale: the call returns IMMEDIATELY (old copy) and kicks exactly one
    # background refresh (fetch #2).
    monkeypatch.setattr(C, "_corpus_fetched_at",
                        _time.monotonic() - C.CORPUS_TTL - 1)
    c3 = R._corpus_conn()
    assert c3 is not None
    c3.close()
    deadline = _time.time() + 5
    while _time.time() < deadline:
        with C.CORPUS_LOCK:
            if not C._corpus_refreshing:
                break
        _time.sleep(0.05)
    assert fetches["n"] == 2
