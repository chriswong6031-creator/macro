"""Unit tests for the nightly reconciler + mode-scoped customer verification in app/billing.py.

Same offline idiom as tests/test_billing_webhook.py and tests/test_billing_subscribe.py: no
network, no real Stripe, no Supabase — `billing._pg` and `billing._stripe` are monkeypatched and
the module-level helpers are called directly.

What these pin (the test→live switch, docs/ops/stripe-setup.md §"Go-live checklist"):

  Stripe customer ids are MODE-SCOPED. The moment STRIPE_SECRET_KEY becomes an `sk_live_` key,
  every `cus_…` minted in test mode is a `resource_missing`. Two things must not happen then:

  1. A stored ghost id must never be handed back to a billing lane — checkout, portal,
     subscribe, and upgrade all pass it straight to Stripe, so one stale row wedges that user
     permanently. `_existing_customer` verifies and self-heals, but ONLY on a proven absence:
     a timeout must not be read as "customer gone" or an outage would erase every mapping and
     mint duplicate customers against live cards.

  2. An operator comp must not be silently revoked. `_compute_entitlement` returns no `source`,
     so an unguarded `_upsert_entitlement` rewrites a lifetime pass to tier=free/source=stripe.
     The reconciler yields to Stripe only when Stripe holds an ENTITLING subscription — which is
     exactly the boundary admin/entitlements.py documents (a comp over a live sub is transient;
     a comp with no live sub is durable, which is why force-comp cancels the sub first).

Run:
    python -m pytest tests/test_billing_reconcile.py -v
"""
from __future__ import annotations

import types

import pytest

from app import billing


# --------------------------------------------------------------------------- #
# fakes
# --------------------------------------------------------------------------- #
class _NoSuchCustomer(Exception):
    """Shaped like the stripe-python error the live key raises on a test-mode id."""

    def __init__(self, cid: str = "cus_test") -> None:
        super().__init__(f"No such customer: '{cid}'; a similar object exists in test mode, "
                         "but a live mode key was used to make this request.")


class _PgRecorder:
    """Stands in for the PostgREST helper; records writes, serves one canned row set."""

    def __init__(self, rows: list[dict] | None = None) -> None:
        self.rows = rows or []
        self.calls: list[tuple[str, str, object]] = []

    def __call__(self, method, path, body=None, prefer=None, timeout=6):
        self.calls.append((method, path, body))
        if method == "GET":
            return self.rows
        return None

    def patched(self) -> list[tuple[str, str, object]]:
        return [c for c in self.calls if c[0] == "PATCH"]


def _stripe_with_customer(customer):
    """A fake stripe module whose Customer.retrieve returns `customer` or raises it."""
    def retrieve(cid):
        if isinstance(customer, Exception):
            raise customer
        return customer
    return types.SimpleNamespace(Customer=types.SimpleNamespace(retrieve=retrieve))


@pytest.fixture
def upserts(monkeypatch):
    """Capture every entitlement write + cache bust the reconciler performs."""
    seen: list[dict] = []
    monkeypatch.setattr(billing, "_upsert_entitlement",
                        lambda uid, cid, ent: seen.append({"user_id": uid, "customer_id": cid, "ent": ent}))
    monkeypatch.setattr(billing, "_invalidate", lambda uid: None)
    return seen


# --------------------------------------------------------------------------- #
# reconciler — comp durability
# --------------------------------------------------------------------------- #
def test_lifetime_comp_survives_a_customer_that_vanished_with_the_mode_switch(monkeypatch, upserts):
    """The friends-and-family case: comped user whose test-mode customer is gone under a live key.

    Pre-fix this row silently became tier=free/source=stripe on the first nightly run after
    go-live — the pass revoked by a cron, with no operator action and no audit trail.
    """
    pg = _PgRecorder([{"user_id": "u_friend", "stripe_customer_id": "cus_test", "source": "comp"}])
    monkeypatch.setattr(billing, "_pg", pg)
    monkeypatch.setattr(billing, "_compute_entitlement",
                        lambda cid: (_ for _ in ()).throw(_NoSuchCustomer(cid)))

    out = billing.reconcile_entitlements()

    assert upserts == [], "a comp must never be rewritten from a customer Stripe does not have"
    assert out == {"reconciled": 0, "total": 1, "comps_preserved": 1}
    # The ghost mapping is still cleared, so the user's next subscribe mints a live customer.
    assert pg.patched() and pg.patched()[0][2]["stripe_customer_id"] is None


def test_comp_survives_when_stripe_has_no_entitling_subscription(monkeypatch, upserts):
    pg = _PgRecorder([{"user_id": "u_friend", "stripe_customer_id": "cus_1", "source": "comp"}])
    monkeypatch.setattr(billing, "_pg", pg)
    monkeypatch.setattr(billing, "_compute_entitlement", lambda cid: {
        "tier": "free", "status": "canceled", "current_period_end": None, "features": [],
    })

    out = billing.reconcile_entitlements()

    assert upserts == []
    assert out["comps_preserved"] == 1
    assert pg.patched() == [], "a live customer with no sub is not a dead mapping"


def test_comp_yields_to_a_live_stripe_subscription(monkeypatch, upserts):
    """The other half of the contract — Stripe still wins when it has something to say.

    admin/entitlements.py blocks comping over a live sub precisely because this reconciler
    reverts it; preserving comps must not quietly turn that guarantee off.
    """
    pg = _PgRecorder([{"user_id": "u_paid", "stripe_customer_id": "cus_1", "source": "comp"}])
    monkeypatch.setattr(billing, "_pg", pg)
    monkeypatch.setattr(billing, "_compute_entitlement", lambda cid: {
        "tier": "pro", "status": "active", "current_period_end": "2027-01-01T00:00:00+00:00",
        "features": ["site_full"],
    })

    out = billing.reconcile_entitlements()

    assert [u["ent"]["tier"] for u in upserts] == ["pro"]
    assert out == {"reconciled": 1, "total": 1, "comps_preserved": 0}


# --------------------------------------------------------------------------- #
# reconciler — stripe rows
# --------------------------------------------------------------------------- #
def test_stripe_row_with_a_vanished_customer_downgrades_and_drops_the_mapping(monkeypatch, upserts):
    pg = _PgRecorder([{"user_id": "u_buyer", "stripe_customer_id": "cus_test", "source": "stripe"}])
    monkeypatch.setattr(billing, "_pg", pg)
    monkeypatch.setattr(billing, "_compute_entitlement",
                        lambda cid: (_ for _ in ()).throw(_NoSuchCustomer(cid)))

    out = billing.reconcile_entitlements()

    assert out["reconciled"] == 1
    assert upserts[0]["ent"]["tier"] == "free"
    # None, not "cus_test": _upsert_entitlement writes the column whenever it is truthy, so
    # passing the ghost id here would re-write the mapping the PATCH just cleared.
    assert upserts[0]["customer_id"] is None
    assert pg.patched() and pg.patched()[0][2]["stripe_customer_id"] is None


def test_transient_stripe_error_never_touches_the_row(monkeypatch, upserts):
    """A timeout is not evidence of absence — skip, don't downgrade and don't unmap."""
    pg = _PgRecorder([{"user_id": "u_buyer", "stripe_customer_id": "cus_1", "source": "stripe"}])
    monkeypatch.setattr(billing, "_pg", pg)
    monkeypatch.setattr(billing, "_compute_entitlement",
                        lambda cid: (_ for _ in ()).throw(TimeoutError("request timed out")))

    out = billing.reconcile_entitlements()

    assert upserts == []
    assert pg.patched() == []
    assert out == {"reconciled": 0, "total": 1, "comps_preserved": 0}


def test_reconciler_selects_source_so_comp_rows_are_distinguishable(monkeypatch, upserts):
    """Guards the query itself: without `source` in the select every row looks like a stripe row."""
    pg = _PgRecorder([])
    monkeypatch.setattr(billing, "_pg", pg)

    billing.reconcile_entitlements()

    get_path = next(path for method, path, _ in pg.calls if method == "GET")
    assert "source" in get_path


# --------------------------------------------------------------------------- #
# _existing_customer — mode-scoped verification
# --------------------------------------------------------------------------- #
def test_foreign_mode_customer_is_dropped_and_reported_absent(monkeypatch):
    pg = _PgRecorder([{"stripe_customer_id": "cus_test"}])
    monkeypatch.setattr(billing, "_pg", pg)
    monkeypatch.setattr(billing, "_stripe", lambda: _stripe_with_customer(_NoSuchCustomer()))

    assert billing._existing_customer("u_1") is None
    assert pg.patched() and pg.patched()[0][2]["stripe_customer_id"] is None


def test_deleted_customer_is_dropped(monkeypatch):
    """Stripe returns a deleted customer as a flagged object rather than raising."""
    pg = _PgRecorder([{"stripe_customer_id": "cus_1"}])
    monkeypatch.setattr(billing, "_pg", pg)
    monkeypatch.setattr(billing, "_stripe",
                        lambda: _stripe_with_customer({"id": "cus_1", "deleted": True}))

    assert billing._existing_customer("u_1") is None
    assert pg.patched()


def test_transient_verify_failure_keeps_the_mapping(monkeypatch):
    """Fail SAFE: an outage must not erase mappings or mint duplicate live customers."""
    pg = _PgRecorder([{"stripe_customer_id": "cus_1"}])
    monkeypatch.setattr(billing, "_pg", pg)
    monkeypatch.setattr(billing, "_stripe",
                        lambda: _stripe_with_customer(TimeoutError("request timed out")))

    assert billing._existing_customer("u_1") == "cus_1"
    assert pg.patched() == []


def test_live_customer_passes_through(monkeypatch):
    pg = _PgRecorder([{"stripe_customer_id": "cus_1"}])
    monkeypatch.setattr(billing, "_pg", pg)
    monkeypatch.setattr(billing, "_stripe",
                        lambda: _stripe_with_customer(types.SimpleNamespace(id="cus_1", deleted=None)))

    assert billing._existing_customer("u_1") == "cus_1"
    assert pg.patched() == []


def test_no_stored_customer_never_touches_stripe(monkeypatch):
    """Keeps `portal`'s 404 ordering: a user with no mapping shouldn't 503 on an unset key."""
    monkeypatch.setattr(billing, "_pg", _PgRecorder([]))
    monkeypatch.setattr(billing, "_stripe", lambda: pytest.fail("must not call Stripe with no mapping"))

    assert billing._existing_customer("u_1") is None
