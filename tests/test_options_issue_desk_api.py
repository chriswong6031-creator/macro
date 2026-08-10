"""Private Issue Desk route policy tests (no live Supabase dependency)."""
from __future__ import annotations

import json

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app import options_issue_desk as api
from engine import options_issue_desk as desk


def test_repo_defaults_to_checked_out_module_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MACRO_REPO", raising=False)
    assert api._repo() == api.Path(api.__file__).resolve().parent.parent


def test_operator_uses_canonical_email_allowlist_without_new_env(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.main
    import app.paywall

    monkeypatch.delenv("OPTIONS_ISSUE_DESK_OPERATOR_USER_ID", raising=False)
    monkeypatch.delenv("SUPABASE_OPERATOR_USER_ID", raising=False)
    monkeypatch.setattr(app.main, "require_user", lambda _: {"id": "verified-id", "email": "operator@example.test"})
    monkeypatch.setattr(app.paywall, "_operator_unlimited", lambda email: email == "operator@example.test")
    assert api.require_operator("Bearer verified") ["id"] == "verified-id"
    monkeypatch.setattr(app.paywall, "_operator_unlimited", lambda _: False)
    with pytest.raises(HTTPException) as denied:
        api.require_operator("Bearer verified")
    assert denied.value.status_code == 403


def test_explicit_operator_uuid_is_exclusive(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.main
    import app.paywall

    monkeypatch.setenv("OPTIONS_ISSUE_DESK_OPERATOR_USER_ID", "configured-id")
    monkeypatch.setattr(app.paywall, "_operator_unlimited", lambda _: True)
    monkeypatch.setattr(app.main, "require_user", lambda _: {"id": "wrong-id", "email": "operator@example.test"})
    with pytest.raises(HTTPException) as denied:
        api.require_operator("Bearer verified")
    assert denied.value.status_code == 403
    monkeypatch.setattr(app.main, "require_user", lambda _: {"id": "configured-id", "email": "nobody@example.test"})
    monkeypatch.setattr(app.paywall, "_operator_unlimited", lambda _: False)
    assert api.require_operator("Bearer verified")["id"] == "configured-id"


def test_supabase_operator_uuid_fallback_is_exclusive(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.main
    import app.paywall

    monkeypatch.delenv("OPTIONS_ISSUE_DESK_OPERATOR_USER_ID", raising=False)
    monkeypatch.setenv("SUPABASE_OPERATOR_USER_ID", "supabase-operator-id")
    monkeypatch.setattr(app.paywall, "_operator_unlimited", lambda _: True)
    monkeypatch.setattr(app.main, "require_user", lambda _: {"id": "wrong-id", "email": "operator@example.test"})
    with pytest.raises(HTTPException) as denied:
        api.require_operator("Bearer verified")
    assert denied.value.status_code == 403
    monkeypatch.setattr(app.main, "require_user", lambda _: {"id": "supabase-operator-id", "email": "nobody@example.test"})
    monkeypatch.setattr(app.paywall, "_operator_unlimited", lambda _: False)
    assert api.require_operator("Bearer verified")["id"] == "supabase-operator-id"


def test_well_formed_approve_validation_failure_is_conflict(monkeypatch: pytest.MonkeyPatch) -> None:
    body = api.ReviewRequest(
        proposal_id="oidp_0123456789abcdef01234567", proposal_revision=1,
        action="approve", reason_codes=["EXECUTION_VERIFIED"],
        idempotency_key="well-formed-approve-001", issue_receipt={"bad": "receipt"},
    )
    monkeypatch.setattr(desk, "review", lambda **_: (_ for _ in ()).throw(desk.IssueDeskError("option NBBO is unordered")))
    with pytest.raises(HTTPException) as rejected:
        api._apply_review(body, _user={"id": "verified-id"})
    assert rejected.value.status_code == 409


def test_http_boundary_rejects_duplicate_keys_and_nonfinite_json() -> None:
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[api.require_operator] = lambda: {"id": "verified-id"}
    client = TestClient(app)
    duplicate = (
        b'{"proposal_id":"oidp_0123456789abcdef01234567",'
        b'"proposal_revision":1,"action":"reject","action":"approve",'
        b'"reason_codes":["ABSTAIN"],"idempotency_key":"duplicate-key-test-001"}'
    )
    response = client.post(
        "/api/options/issue-desk/reviews",
        content=duplicate,
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422

    nonfinite = duplicate.replace(b'"action":"reject","action":"approve"', b'"action":"reject","issue_receipt":{"x":NaN}')
    response = client.post(
        "/api/options/issue-desk/reviews",
        content=nonfinite,
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422


@pytest.mark.parametrize("invalid_revision", ["1", 1.0, True])
def test_review_decoder_rejects_coerced_proposal_revision(invalid_revision: object) -> None:
    payload = {
        "proposal_id": "oidp_0123456789abcdef01234567",
        "proposal_revision": invalid_revision,
        "action": "reject",
        "reason_codes": ["ABSTAIN"],
        "idempotency_key": "strict-revision-test-001",
    }
    with pytest.raises(ValidationError):
        api._decode_review_body(json.dumps(payload).encode("utf-8"))


@pytest.mark.parametrize("invalid_revision", ["1", 1.0, True])
def test_http_boundary_rejects_coerced_proposal_revision(invalid_revision: object) -> None:
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[api.require_operator] = lambda: {"id": "verified-id"}
    client = TestClient(app)
    response = client.post(
        "/api/options/issue-desk/reviews",
        json={
            "proposal_id": "oidp_0123456789abcdef01234567",
            "proposal_revision": invalid_revision,
            "action": "reject",
            "reason_codes": ["ABSTAIN"],
            "idempotency_key": "strict-revision-test-001",
        },
    )
    assert response.status_code == 422
