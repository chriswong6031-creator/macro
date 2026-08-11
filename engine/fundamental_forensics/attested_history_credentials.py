"""Locally signed, narrowly scoped R2 child credentials for attested history.

These primitives used to live in
``scripts/run_fundamental_forensics_attested_history.py``.  They moved here
unchanged because the production receipt API must never import from
``scripts/``: the long-running server needs the same credential narrowing the
one-shot operator CLI uses, and two implementations of a security boundary is
exactly the drift this repository forbids.  The CLI and the seed writer now
import these names from this module, so there is a single validation order,
a single JWT payload construction, and a single set of error messages.

The long-lived parent credential may carry a broader Cloudflare policy.  The
enforceable child boundary is the locally signed session JWT: one bucket, the
single ``fundamental_forensics/`` prefix, an exact action list, and at most a
thirty-minute lifetime.  No Cloudflare API is called to mint one.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass, field
from hashlib import sha256
import hmac
import json
import re
import time
from typing import Sequence
from urllib.parse import urlsplit


R2_TEMPORARY_CREDENTIAL_MAX_TTL_SECONDS = 30 * 60
R2_ATTESTED_HISTORY_PREFIX = "fundamental_forensics/"
_R2_ENDPOINT_HOST_RE = re.compile(
    r"^(?P<account_id>[a-f0-9]{32})\.r2\.cloudflarestorage\.com$"
)
_R2_ACCESS_KEY_RE = re.compile(r"^[A-Za-z0-9]{16,128}$")
_R2_BUCKET_RE = re.compile(r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")
_R2_TEMPORARY_ACTIONS = frozenset(
    {
        "GetObject",
        "HeadObject",
        "PutObject",
    }
)


class R2TemporaryCredentialError(ValueError):
    """A parent R2 credential cannot be narrowed into an admitted child."""


_VALUE_FREE_CREDENTIAL_ERRORS = frozenset(
    {
        "R2 endpoint is invalid",
        "R2 endpoint host is invalid",
        "R2 parent access key ID is invalid",
        "R2 parent secret access key is invalid",
        "R2 bucket is invalid",
        "R2 child scope is invalid",
        "R2 child actions are invalid",
        "R2 child actions exceed the exact role",
        "R2 child prefix is invalid",
        "R2 child TTL is invalid",
        "R2 child issue clock is invalid",
    }
)


def value_free_credential_error(exc: R2TemporaryCredentialError) -> str:
    """Return an operator-safe reason without echoing credential material.

    Every current minter rejection is a fixed literal. Keep an explicit
    allow-list anyway: a future validation message that interpolates an
    endpoint, bucket, key, or secret collapses to the generic reason until it
    receives an intentional security review.
    """
    reason = str(exc)
    if reason in _VALUE_FREE_CREDENTIAL_ERRORS:
        return reason
    return "R2 parent credential is invalid"


@dataclass(frozen=True)
class R2TemporaryCredentials:
    """Short-lived R2 S3 credential derived without calling Cloudflare APIs.

    ``secret_access_key`` and ``session_token`` are excluded from ``repr``.  A
    frozen dataclass renders every field by default, so one ``log.warning("%s",
    creds)``, one pytest assertion diff, or one traceback frame holding this
    object would print the derived child secret and the whole signed JWT.  The
    access key ID and the expiry are safe and stay visible, because those are
    what a diagnosis actually needs.
    """

    access_key_id: str
    secret_access_key: str = field(repr=False)
    session_token: str = field(repr=False)
    expires_at: int


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _canonical_r2_endpoint(endpoint: str) -> tuple[str, str, str]:
    """Return the exact endpoint, host, and account ID admitted for local signing."""
    if not isinstance(endpoint, str) or len(endpoint) > 256:
        raise R2TemporaryCredentialError("R2 endpoint is invalid")
    try:
        parsed = urlsplit(endpoint)
        port = parsed.port
    except ValueError as exc:
        raise R2TemporaryCredentialError("R2 endpoint is invalid") from exc
    host = parsed.hostname
    if (
        parsed.scheme != "https"
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or host is None
        or endpoint not in {f"https://{host}", f"https://{host}/"}
    ):
        raise R2TemporaryCredentialError("R2 endpoint is invalid")
    match = _R2_ENDPOINT_HOST_RE.fullmatch(host)
    if match is None:
        raise R2TemporaryCredentialError("R2 endpoint host is invalid")
    return f"https://{host}", host, match.group("account_id")


def mint_r2_temporary_credentials(
    *,
    endpoint: str,
    parent_access_key_id: str,
    parent_secret_access_key: str,
    bucket: str,
    scope: str,
    actions: Sequence[str],
    ttl_seconds: int = R2_TEMPORARY_CREDENTIAL_MAX_TTL_SECONDS,
    prefix: str = R2_ATTESTED_HISTORY_PREFIX,
    issued_at: int | None = None,
) -> R2TemporaryCredentials:
    """Mint one Cloudflare-documented HS256 child credential locally.

    The long-lived parent may include List permission.  The session JWT is the
    enforceable child boundary: it carries an exact action set, one bucket,
    the single Fundamental Forensics prefix, and a maximum 30-minute lifetime.
    Credential separation alone is not evidence that either parent has the
    intended Cloudflare IAM policy.
    """
    _endpoint, host, account_id = _canonical_r2_endpoint(endpoint)
    if not isinstance(parent_access_key_id, str) or _R2_ACCESS_KEY_RE.fullmatch(
        parent_access_key_id
    ) is None:
        raise R2TemporaryCredentialError("R2 parent access key ID is invalid")
    if (
        not isinstance(parent_secret_access_key, str)
        or not parent_secret_access_key
        or len(parent_secret_access_key.encode("utf-8")) > 512
    ):
        raise R2TemporaryCredentialError("R2 parent secret access key is invalid")
    if (
        not isinstance(bucket, str)
        or _R2_BUCKET_RE.fullmatch(bucket) is None
        or ".." in bucket
    ):
        raise R2TemporaryCredentialError("R2 bucket is invalid")
    if scope not in {"object-read-only", "object-read-write"}:
        raise R2TemporaryCredentialError("R2 child scope is invalid")
    if isinstance(actions, (str, bytes)):
        raise R2TemporaryCredentialError("R2 child actions are invalid")
    action_list = list(actions)
    if (
        not action_list
        or len(action_list) != len(set(action_list))
        or any(action not in _R2_TEMPORARY_ACTIONS for action in action_list)
        or action_list != sorted(action_list)
    ):
        raise R2TemporaryCredentialError("R2 child actions are invalid")
    allowed = (
        ["GetObject", "HeadObject"]
        if scope == "object-read-only"
        else ["GetObject", "HeadObject", "PutObject"]
    )
    if action_list != allowed:
        raise R2TemporaryCredentialError("R2 child actions exceed the exact role")
    if prefix != R2_ATTESTED_HISTORY_PREFIX:
        raise R2TemporaryCredentialError("R2 child prefix is invalid")
    if (
        isinstance(ttl_seconds, bool)
        or not isinstance(ttl_seconds, int)
        or not 60 <= ttl_seconds <= R2_TEMPORARY_CREDENTIAL_MAX_TTL_SECONDS
    ):
        raise R2TemporaryCredentialError("R2 child TTL is invalid")
    observed = int(time.time()) if issued_at is None else issued_at
    if isinstance(observed, bool) or not isinstance(observed, int) or observed < 1:
        raise R2TemporaryCredentialError("R2 child issue clock is invalid")

    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "actions": action_list,
        "aud": host,
        "bucket": bucket,
        "exp": observed + ttl_seconds,
        "iat": observed,
        "iss": parent_access_key_id,
        "paths": {"objectPaths": [], "prefixPaths": [prefix]},
        "scope": scope,
        "sub": account_id,
    }
    unsigned = ".".join(
        _base64url(
            json.dumps(
                item,
                ensure_ascii=True,
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        )
        for item in (header, payload)
    )
    signature = hmac.digest(
        parent_secret_access_key.encode("utf-8"), unsigned.encode("ascii"), "sha256"
    )
    signed_jwt = f"{unsigned}.{_base64url(signature)}"
    return R2TemporaryCredentials(
        access_key_id=parent_access_key_id,
        secret_access_key=sha256(signed_jwt.encode("ascii")).hexdigest(),
        session_token=base64.b64encode(f"jwt/{signed_jwt}".encode("ascii")).decode(
            "ascii"
        ),
        expires_at=observed + ttl_seconds,
    )
