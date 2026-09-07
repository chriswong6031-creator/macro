"""tests/test_support_tier_routing.py — plan-based support routing (packet B-F13-3).

Covers lib.help_directory.route_for_tier (pure) and app/support.py's threading of that
routing into the ticket receipt, the operator notification subject/kv, and row["meta"].
Follows the tests/test_support_api.py idiom: the route function is called directly with a
fake Request/BackgroundTasks so no HTTP client or heavy app.main import is needed.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi import BackgroundTasks

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import support  # noqa: E402
from app.main import _PLAN_LABELS  # noqa: E402
from lib.help_directory import (  # noqa: E402
    SUPPORT_PLANS,
    _check_banned_vocabulary,
    _TIER_TO_PLAN,
    route_for_tier,
)

UID = "22222222-2222-2222-2222-222222222222"


# ===========================================================================
# route_for_tier — pure function
# ===========================================================================
def test_free_routes_to_community() -> None:
    out = route_for_tier("free")
    assert out["plan_id"] == "free"
    assert out["queue"] == "community"
    assert out["plan_read"] is True
    assert out["note_en"] is None and out["note_zh"] is None


@pytest.mark.parametrize("tier", ["essential", "insider", "pro", "unlimited"])
def test_paid_tiers_route_to_priority(tier: str) -> None:
    out = route_for_tier(tier)
    assert out["queue"] == "priority"
    assert out["plan_read"] is True


def test_unreadable_plan_routes_as_free_and_says_so() -> None:
    out = route_for_tier(None, tier_known=False)
    assert out["plan_id"] == "free"
    assert out["queue"] == "community"
    assert out["plan_read"] is False
    assert out["note_en"] and out["note_zh"]
    assert out["note_en"] != out["note_zh"]


def test_signed_out_and_unrecognised_are_distinct_notes() -> None:
    signed_out = route_for_tier(None, tier_known=True)
    unreadable = route_for_tier(None, tier_known=False)
    unrecognised = route_for_tier("some-future-tier")
    no_plan = route_for_tier(None, tier_known=True, signed_in=True)
    notes = {signed_out["note_en"], unreadable["note_en"], unrecognised["note_en"], no_plan["note_en"]}
    assert len(notes) == 4


def test_signed_in_user_with_no_plan_is_never_told_they_were_signed_out() -> None:
    """Review finding B-F13-3 MAJOR-1 (RED before the fix): an anonymous submitter and a
    signed-in user whose account read succeeds but carries no plan value both call
    ``route_for_tier(None, tier_known=True)`` — without ``signed_in`` to disambiguate,
    the signed-in case silently reused the anonymous "you were not signed in" sentence,
    which is a false statement about the user's own account state in both languages."""
    anonymous = route_for_tier(None, tier_known=True, signed_in=False)
    signed_in_no_plan = route_for_tier(None, tier_known=True, signed_in=True)
    assert anonymous["note_en"] == "You were not signed in, so this went to the general queue."
    assert signed_in_no_plan["note_en"] != anonymous["note_en"]
    assert signed_in_no_plan["note_zh"] != anonymous["note_zh"]
    assert "signed in" not in signed_in_no_plan["note_en"].lower()
    assert signed_in_no_plan["note_en"] and signed_in_no_plan["note_zh"]
    assert signed_in_no_plan["plan_id"] == "free"
    assert signed_in_no_plan["plan_read"] is False


def test_every_known_tier_label_maps_to_a_plan() -> None:
    for tier in _PLAN_LABELS:
        assert tier in _TIER_TO_PLAN, f"tier {tier!r} has no plan route"


def test_promises_are_bilingual_plain_and_budgeted() -> None:
    # One shared vocabulary law (lib.help_directory._check_banned_vocabulary),
    # not a second local exception list (review finding M3: "queue" used to be
    # banned for help answers while a separate, shorter list here carved out an
    # exception so the promise text could say "priority queue" — two
    # incompatible laws on one page). "queue" is ordinary English and is not on
    # the production banned list at all, so no per-test carve-out is needed.
    for p in SUPPORT_PLANS:
        assert len(p.promise_en.split()) <= 26, p.promise_en
        assert len(p.promise_zh) <= 54, p.promise_zh
        assert p.promise_zh != p.promise_en
        _check_banned_vocabulary(f"support plan {p.id!r} promise", p.promise_en, p.promise_zh)


# ===========================================================================
# app/support.py wiring
# ===========================================================================
class _FakeRequest:
    def __init__(self, headers: dict | None = None):
        self.headers = {k.lower(): v for k, v in (headers or {}).items()}


class _Store:
    def __init__(self, ticket_id="8f000000-0000-4000-8000-000000000002"):
        self.tickets: list[dict] = []
        self.messages: list[dict] = []
        self.ticket_id = ticket_id

    def pg(self, method, path, body=None, prefer=None, timeout=6):
        if method == "POST" and path.startswith("support_tickets"):
            row = dict((body or [{}])[0])
            row["id"] = self.ticket_id
            self.tickets.append(row)
            return [row]
        if method == "POST" and path.startswith("support_ticket_messages"):
            self.messages.append(dict((body or [{}])[0]))
            return None
        raise AssertionError(f"unexpected PostgREST call {method} {path}")


@pytest.fixture
def wired(monkeypatch):
    store = _Store()
    monkeypatch.setattr(support, "_pg", store.pg)
    monkeypatch.setattr(support, "_client_ip", lambda request: "203.0.113.9")
    support._reset_rate_limiter()
    yield store
    support._reset_rate_limiter()


def _body(**kw):
    args = {"email": "ada@example.com", "topic": "billing",
            "subject": "Card declined", "message": "My card was declined at checkout."}
    args.update(kw)
    return support.TicketRequest(**args)


def _drain(bt: BackgroundTasks) -> None:
    for task in list(getattr(bt, "tasks", [])):
        task.func(*task.args, **task.kwargs)


def _post(store, mailer_calls):
    # _resolve_user, billing.read_entitlement, and the mailer seams are monkeypatched by
    # the caller before this runs — this helper only drives the route + background job.
    bt = BackgroundTasks()
    out = support.create_ticket(_body(), _FakeRequest(), bt, authorization=None)
    _drain(bt)
    return out


def test_receipt_carries_the_promise_when_the_plan_read_fails(wired, monkeypatch) -> None:
    from app import billing

    monkeypatch.setattr(support, "_resolve_user", lambda auth: {"id": UID, "email": "ada@example.com"})
    monkeypatch.setattr(billing, "read_entitlement", lambda uid: (_ for _ in ()).throw(RuntimeError("down")))
    out = _post(wired, [])
    assert out["routing"]["plan"] == "free"
    assert out["routing"]["note_en"]
    assert "queue" not in out


def test_signed_in_ticket_is_never_told_it_was_not_signed_in_when_plan_is_unreadable(wired, monkeypatch) -> None:
    """Review finding B-F13-3 MAJOR-1 (RED before the fix): a signed-in user whose
    ``billing.read_entitlement`` call SUCCEEDS but returns a dict with no usable
    ``tier`` key (``.get("tier")`` -> None) reached ``route_for_tier(None,
    tier_known=True)`` — the exact same inputs as an anonymous submitter — and the
    JSON receipt (both note_en and note_zh) falsely told a signed-in person they
    were not signed in."""
    from app import billing

    monkeypatch.setattr(support, "_resolve_user", lambda auth: {"id": UID, "email": "ada@example.com"})
    monkeypatch.setattr(billing, "read_entitlement", lambda uid: {})  # no "tier" key at all
    out = _post(wired, [])
    assert out["routing"]["plan"] == "free"
    assert out["routing"]["note_en"] != "You were not signed in, so this went to the general queue."
    assert "signed in" not in out["routing"]["note_en"].lower()
    assert out["routing"]["note_en"] and out["routing"]["note_zh"]


def test_priority_ticket_labels_the_operator_mail(wired, monkeypatch) -> None:
    from app import billing, mailer

    sent = []
    monkeypatch.setattr(mailer, "support_to", lambda: "ops@example.com")
    monkeypatch.setattr(mailer, "render_email", lambda *a, **kw: ("<html/>", "text"))
    monkeypatch.setattr(mailer, "send", lambda **kw: (sent.append(kw), "sent")[1])
    monkeypatch.setattr(support, "_resolve_user", lambda auth: {"id": UID, "email": "ada@example.com"})
    monkeypatch.setattr(billing, "read_entitlement", lambda uid: {"tier": "pro"})
    _post(wired, sent)
    operator_sends = [c for c in sent if c["template"] == "ticket_operator_notify"]
    assert operator_sends and operator_sends[0]["subject"].startswith("[support/priority/")


def test_free_ticket_labels_operator_mail_community(wired, monkeypatch) -> None:
    from app import mailer

    sent = []
    monkeypatch.setattr(mailer, "support_to", lambda: "ops@example.com")
    monkeypatch.setattr(mailer, "render_email", lambda *a, **kw: ("<html/>", "text"))
    monkeypatch.setattr(mailer, "send", lambda **kw: (sent.append(kw), "sent")[1])
    monkeypatch.setattr(support, "_resolve_user", lambda auth: None)
    _post(wired, sent)
    operator_sends = [c for c in sent if c["template"] == "ticket_operator_notify"]
    assert operator_sends and operator_sends[0]["subject"].startswith("[support/community/")


def test_meta_records_the_queue_without_a_new_table(wired, monkeypatch) -> None:
    monkeypatch.setattr(support, "_resolve_user", lambda auth: None)
    monkeypatch.setattr(support, "_notify_operator", lambda **kw: "sent")
    _post(wired, [])
    meta = wired.tickets[0]["meta"]
    assert "queue" in meta and "plan_read" in meta
    assert meta["queue"] == "community"
