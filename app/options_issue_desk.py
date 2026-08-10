"""Bearer-authenticated private API for the operator-reviewed Options Issue Desk."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from engine import options_issue_desk as desk

_HEADERS = {
    "Cache-Control": "private, no-store",
    "Vary": "Authorization",
    "X-Content-Type-Options": "nosniff",
}
router = APIRouter(prefix="/api/options/issue-desk", tags=["options-issue-desk"])
_MAX_REVIEW_BYTES = 128 * 1024


def _repo() -> Path:
    return Path(os.environ.get("MACRO_REPO") or Path(__file__).resolve().parent.parent)


def require_operator(authorization: str | None = Header(default=None)) -> dict:
    """The bearer is verified first; the owner allowlist is an explicit hard gate."""
    from app.main import require_user

    user = require_user(authorization)
    expected = (
        os.environ.get("OPTIONS_ISSUE_DESK_OPERATOR_USER_ID", "").strip()
        or os.environ.get("SUPABASE_OPERATOR_USER_ID", "").strip()
    )
    from app.paywall import _operator_unlimited

    user_id = str(user.get("id") or "")
    if expected:
        allowed = user_id == expected
    else:
        allowed = _operator_unlimited(str(user.get("email") or ""))
    if not allowed:
        raise HTTPException(403, "Options Issue Desk is operator-only", headers=_HEADERS)
    return user


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    proposal_id: str = Field(min_length=5, max_length=64)
    proposal_revision: int = Field(ge=1)
    action: Literal["approve", "reject"]
    reason_codes: list[str] = Field(min_length=1, max_length=8)
    idempotency_key: str = Field(min_length=16, max_length=128)
    issue_receipt: dict[str, Any] | None = None


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def _decode_review_body(raw: bytes) -> ReviewRequest:
    if not raw or len(raw) > _MAX_REVIEW_BYTES:
        raise ValueError("review body is empty or too large")
    value = json.loads(
        raw.decode("utf-8"),
        parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)),
        object_pairs_hook=_strict_object,
    )
    if not isinstance(value, dict):
        raise TypeError("review body must be an object")
    return ReviewRequest.model_validate(value)


def _response(payload: dict[str, Any], status: int = 200) -> JSONResponse:
    return JSONResponse(payload, status_code=status, headers=_HEADERS)


_OPERATOR_DEP = Depends(require_operator)


@router.get("")
def issue_desk(_user: dict = _OPERATOR_DEP) -> JSONResponse:
    try:
        return _response(desk.document(repo=_repo(), reviewer=str(_user["id"])))
    except desk.IssueDeskError as exc:
        raise HTTPException(503, str(exc), headers=_HEADERS) from None


def _apply_review(body: ReviewRequest, _user: dict) -> JSONResponse:
    try:
        result = desk.review(
            proposal_id=body.proposal_id,
            proposal_revision=body.proposal_revision,
            action=body.action,
            reason_codes=body.reason_codes,
            idempotency_key=body.idempotency_key,
            issue_receipt=body.issue_receipt,
            reviewer=str(_user["id"]),
        )
        return _response(result)
    except desk.ConflictError as exc:
        raise HTTPException(409, str(exc), headers=_HEADERS) from None
    except desk.IssueDeskError as exc:
        status = 409 if body.action == "approve" else 400
        raise HTTPException(status, str(exc), headers=_HEADERS) from None


@router.post("/reviews")
async def review(request: Request, _user: dict = _OPERATOR_DEP) -> JSONResponse:
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type != "application/json":
        raise HTTPException(415, "application/json required", headers=_HEADERS)
    try:
        body = _decode_review_body(await request.body())
    except (TypeError, UnicodeDecodeError, ValueError, ValidationError, json.JSONDecodeError):
        raise HTTPException(422, "invalid strict review payload", headers=_HEADERS) from None
    return _apply_review(body, _user)
