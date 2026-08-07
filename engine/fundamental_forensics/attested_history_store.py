"""Read-only store for the DEDICATED attested-history bucket.

The sealed Fundamental Forensics receipts do not live in the Research Vault
bucket.  They live in their own bucket addressed only by
``FF_ATTESTED_R2_READONLY_{ENDPOINT,ACCESS_KEY_ID,SECRET_ACCESS_KEY,BUCKET}``.
This module is the only way the production HTTP API reaches them.  It never
reads ``R2_RESEARCH_*``, generic ``R2_*``, or ``RESEARCH_LOCAL_STORE``, and it
never imports ``engine.research_vault.r2_store.build_store``: a bucket
mismatch there would silently serve — or silently fail to serve — from the
wrong object namespace, which is worse than a bounded 503.

The credential handed to boto is always a locally signed, short-lived child
scoped to ``object-read-only`` with exactly ``GetObject``/``HeadObject`` on the
single ``fundamental_forensics/`` prefix.  A 30-minute child cannot simply be
cached forever in a long-running server, so this store re-mints under a lock
before the child expires and rebuilds its client with the new session token.

DESIGN NOTE — why the parent secrets are NOT popped from ``os.environ``.
The operator CLI (``scripts/run_fundamental_forensics_attested_history.py``)
deliberately pops ``FF_ATTESTED_R2_READONLY_ACCESS_KEY_ID`` and
``..._SECRET_ACCESS_KEY`` after minting, because it is a one-shot process
inside a scoped CI step that will never need to mint again.  This API is the
opposite case and must not copy that behaviour.  ``/etc/macro-api.env`` is
re-read by systemd on every restart, so popping buys nothing durable; what it
would buy is a store that can never renew its own child and a surprising,
order-dependent environment for anything else in a forking server.  The parent
material therefore stays in private instance attributes, is never logged, and
never leaves this module — ``__repr__`` is overridden so a traceback or log
line cannot print it.
"""
from __future__ import annotations

import os
import threading
import time
from collections.abc import Mapping
from typing import Any, Callable

from engine.fundamental_forensics.attested_history_credentials import (
    R2_ATTESTED_HISTORY_PREFIX,
    R2_TEMPORARY_CREDENTIAL_MAX_TTL_SECONDS,
    R2TemporaryCredentialError,
    R2TemporaryCredentials,
    _canonical_r2_endpoint,
    _R2_ACCESS_KEY_RE,
    _R2_BUCKET_RE,
    mint_r2_temporary_credentials,
)
from engine.research_vault.r2_store import R2Store, StrictBoundedReadStore


ATTESTED_HISTORY_ENV_NAMES = (
    "FF_ATTESTED_R2_READONLY_ENDPOINT",
    "FF_ATTESTED_R2_READONLY_ACCESS_KEY_ID",
    "FF_ATTESTED_R2_READONLY_SECRET_ACCESS_KEY",
    "FF_ATTESTED_R2_READONLY_BUCKET",
)
ATTESTED_HISTORY_CHILD_SCOPE = "object-read-only"
ATTESTED_HISTORY_CHILD_ACTIONS = ("GetObject", "HeadObject")
DEFAULT_REFRESH_MARGIN_SECONDS = 300

# The minted child is a JWT whose ``exp`` claim Cloudflare evaluates against
# real wall-clock time, so this store's clock MUST be epoch seconds.  Swapping
# the default to ``time.monotonic`` — a plausible "harden against clock steps"
# edit — would keep every renewal test green while minting credentials R2
# rejects outright, presenting as a total receipt-route outage misdiagnosed as
# bad credentials.  1_600_000_000 is 2020-09-13; any real deployment clock is
# far past it and no monotonic clock reaches it.
_MIN_PLAUSIBLE_EPOCH_SECONDS = 1_600_000_000


class AttestedHistoryStoreError(RuntimeError):
    """The dedicated attested-history reader refused an operation."""


def _default_client_factory(
    *,
    endpoint: str,
    access_key_id: str,
    secret_access_key: str,
    session_token: str,
):
    """Build the GET/HEAD-only boto3 client for one short-lived child."""
    try:
        import boto3
        from botocore.config import Config
    except ImportError as exc:  # pragma: no cover - boto3 is installed in prod
        raise AttestedHistoryStoreError(
            "boto3 is unavailable for the dedicated attested-history reader"
        ) from exc
    settings = dict(
        region_name="auto",
        signature_version="s3v4",
        max_pool_connections=8,
        retries={"max_attempts": 3, "mode": "adaptive"},
        connect_timeout=15,
        read_timeout=60,
    )
    try:  # newer botocore: R2 rejects the default CRC32 trailer
        config = Config(
            **settings,
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        )
    except TypeError:
        config = Config(**settings)
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
        aws_session_token=session_token,
        config=config,
    )


class DedicatedAttestedHistoryStore:
    """A renewing, read-only reader over the dedicated attested-history bucket.

    Only :meth:`get_bytes_strict_bounded` reaches storage.  Every other member
    of the ``StrictBoundedReadStore`` protocol — and every write/discovery
    method a mistaken caller might reach for — is DEFINED so the runtime
    ``isinstance`` structural check still admits this object, and raises
    :class:`AttestedHistoryStoreError` so a mutation or a discovery call is
    loud rather than silently possible.
    """

    def __init__(
        self,
        *,
        endpoint: str,
        parent_access_key_id: str,
        parent_secret_access_key: str,
        bucket: str,
        ttl_seconds: int = R2_TEMPORARY_CREDENTIAL_MAX_TTL_SECONDS,
        refresh_margin_seconds: int = DEFAULT_REFRESH_MARGIN_SECONDS,
        clock: Callable[[], float] | None = None,
        client_factory: Callable[..., Any] | None = None,
        minter: Callable[..., R2TemporaryCredentials] | None = None,
    ) -> None:
        # Validate before anything can construct a client or open a socket.
        # An unusable endpoint/key/bucket is a configuration failure, not a
        # transient one, and must be visible at construction time.
        try:
            canonical_endpoint, _host, _account = _canonical_r2_endpoint(endpoint)
        except R2TemporaryCredentialError as exc:
            raise AttestedHistoryStoreError(
                "dedicated attested-history endpoint is invalid"
            ) from exc
        if (
            not isinstance(parent_access_key_id, str)
            or _R2_ACCESS_KEY_RE.fullmatch(parent_access_key_id) is None
        ):
            raise AttestedHistoryStoreError(
                "dedicated attested-history access key ID is invalid"
            )
        if (
            not isinstance(parent_secret_access_key, str)
            or not parent_secret_access_key
            or len(parent_secret_access_key.encode("utf-8")) > 512
        ):
            raise AttestedHistoryStoreError(
                "dedicated attested-history secret access key is invalid"
            )
        if (
            not isinstance(bucket, str)
            or _R2_BUCKET_RE.fullmatch(bucket) is None
            or ".." in bucket
        ):
            raise AttestedHistoryStoreError(
                "dedicated attested-history bucket is invalid"
            )
        if (
            isinstance(ttl_seconds, bool)
            or not isinstance(ttl_seconds, int)
            or not 60 <= ttl_seconds <= R2_TEMPORARY_CREDENTIAL_MAX_TTL_SECONDS
        ):
            raise AttestedHistoryStoreError(
                "dedicated attested-history child TTL is invalid"
            )
        if (
            isinstance(refresh_margin_seconds, bool)
            or not isinstance(refresh_margin_seconds, int)
            or refresh_margin_seconds < 1
            or refresh_margin_seconds >= ttl_seconds
        ):
            # A margin at or above the TTL would re-mint on every single read.
            # A margin of ZERO is the opposite failure: the store would hand a
            # caller a backing whose credential expires during the very request
            # it was handed to, so the read 403s instead of being renewed.
            raise AttestedHistoryStoreError(
                "dedicated attested-history refresh margin is invalid"
            )

        self.bucket = bucket
        self.endpoint = canonical_endpoint
        self.ttl_seconds = ttl_seconds
        self.refresh_margin_seconds = refresh_margin_seconds
        self.write_attempts = 0
        self._parent_access_key_id = parent_access_key_id
        self._parent_secret_access_key = parent_secret_access_key
        self._clock = clock if clock is not None else time.time
        self._client_factory = (
            client_factory if client_factory is not None else _default_client_factory
        )
        self._minter = minter if minter is not None else mint_r2_temporary_credentials
        self._lock = threading.Lock()
        self._backing: R2Store | None = None
        self._child_expires_at: int | None = None
        self._refresh_count = 0

    # -- introspection ------------------------------------------------------

    def __repr__(self) -> str:
        """Never render credential material, not even truncated.

        A store instance reaches tracebacks, ``repr()`` in logs, and pytest
        assertion output.  Print only the non-secret addressing facts.
        """
        return (
            f"<DedicatedAttestedHistoryStore bucket={self.bucket!r} "
            f"endpoint={self.endpoint!r} scope={ATTESTED_HISTORY_CHILD_SCOPE!r}>"
        )

    __str__ = __repr__

    @property
    def child_expires_at(self) -> int | None:
        """Expiry of the currently held child, or ``None`` before the first mint."""
        return self._child_expires_at

    @property
    def refresh_count(self) -> int:
        """How many times an expiring child was replaced (the first mint is not one)."""
        return self._refresh_count

    # There is deliberately no ``available`` property.  R2Store has one, but
    # this store cannot answer it without talking to R2, and an unconditional
    # ``True`` would be a claim it has not earned.  A caller that reaches for
    # it gets a loud AttributeError instead of a comforting wrong answer.

    # -- the one storage path ----------------------------------------------

    def _active_backing(self) -> R2Store:
        """Return a backing store whose child credential is not near expiry."""
        with self._lock:
            now = self._clock()
            if not isinstance(now, (int, float)) or now < _MIN_PLAUSIBLE_EPOCH_SECONDS:
                raise AttestedHistoryStoreError(
                    "dedicated attested-history clock is not epoch seconds"
                )
            expires_at = self._child_expires_at
            fresh = (
                self._backing is not None
                and expires_at is not None
                and now < expires_at - self.refresh_margin_seconds
            )
            if fresh:
                return self._backing  # type: ignore[return-value]
            first = self._backing is None
            try:
                # ``issued_at`` is passed explicitly so the mint and the
                # freshness comparison above read the SAME clock.  Left to its
                # default the minter stamps expiry from its own
                # ``time.time()``, and an injected non-epoch ``clock`` (say
                # ``time.monotonic``) would then compare a small ``now``
                # against a ~1.8e9 expiry, making ``fresh`` permanently true:
                # the store would pin its first child forever and keep serving
                # an expired session token with no self-heal.
                credentials = self._minter(
                    endpoint=self.endpoint,
                    parent_access_key_id=self._parent_access_key_id,
                    parent_secret_access_key=self._parent_secret_access_key,
                    bucket=self.bucket,
                    scope=ATTESTED_HISTORY_CHILD_SCOPE,
                    actions=ATTESTED_HISTORY_CHILD_ACTIONS,
                    ttl_seconds=self.ttl_seconds,
                    prefix=R2_ATTESTED_HISTORY_PREFIX,
                    issued_at=int(now),
                )
            except R2TemporaryCredentialError as exc:
                raise AttestedHistoryStoreError(
                    "dedicated attested-history parent credential cannot mint a scoped child"
                ) from exc
            except AttestedHistoryStoreError:
                raise
            except Exception as exc:  # noqa: BLE001 - the class advertises one error type
                raise AttestedHistoryStoreError(
                    "dedicated attested-history child could not be minted"
                ) from exc
            minted_expires_at = credentials.expires_at
            if (
                isinstance(minted_expires_at, bool)
                or not isinstance(minted_expires_at, int)
                or not now < minted_expires_at <= now + self.ttl_seconds
            ):
                # Range, not just type.  An expiry outside this window means the
                # minter answered on a different clock, and the renewal
                # comparison would silently degrade into "re-mint on every
                # read" or "never re-mint again".
                raise AttestedHistoryStoreError(
                    "dedicated attested-history child expiry is invalid"
                )
            try:
                client = self._client_factory(
                    endpoint=self.endpoint,
                    access_key_id=credentials.access_key_id,
                    secret_access_key=credentials.secret_access_key,
                    session_token=credentials.session_token,
                )
            except AttestedHistoryStoreError:
                raise
            except Exception as exc:  # noqa: BLE001 - the class advertises one error type
                raise AttestedHistoryStoreError(
                    "dedicated attested-history reader client could not be built"
                ) from exc
            backing = R2Store(self.bucket, client=client)
            if not isinstance(backing, StrictBoundedReadStore):  # defensive contract guard
                raise AttestedHistoryStoreError(
                    "dedicated attested-history reader lacks strict bounded reads"
                )
            self._backing = backing
            self._child_expires_at = minted_expires_at
            if not first:
                self._refresh_count += 1
            return backing

    def get_bytes_strict_bounded(
        self,
        key: str,
        maximum_bytes: int | None = None,
        *,
        expected_byte_length: int | None = None,
        max_byte_length: int | None = None,
    ) -> bytes | None:
        """Mirror :meth:`R2Store.get_bytes_strict_bounded` and forward verbatim.

        Both the positional-cap mode and the exact-length keyword mode belong
        to the wrapped store; re-deriving either ETag/HEAD check here would
        create a second, weaker copy of a fail-closed boundary.
        """
        return self._active_backing().get_bytes_strict_bounded(
            key,
            maximum_bytes,
            expected_byte_length=expected_byte_length,
            max_byte_length=max_byte_length,
        )

    # -- denied surface -----------------------------------------------------
    #
    # ``StrictBoundedReadStore`` is a runtime-checkable Protocol, and a runtime
    # ``isinstance`` check tests METHOD PRESENCE ONLY.  Exactly the seven
    # members of that protocol chain (``Store`` -> ``StrictReadStore`` ->
    # ``StrictBoundedReadStore``) are defined here so the receipt reader's
    # ``_require_store`` guard admits this object; the six that are not the
    # bounded read raise, so no caller can quietly open a legacy, unbounded,
    # discovery, or mutation side channel on a bucket this process may only read.
    #
    # The three members unique to ``StrictConditionalWriteStore``
    # (``get_bytes_strict_bounded_versioned``,
    # ``validate_strict_conditional_write_capability``, and
    # ``put_bytes_strict_conditional``) are DELIBERATELY ABSENT rather than
    # present-and-raising.  Defining them — even to raise — would make
    # ``isinstance(store, StrictConditionalWriteStore)`` return True, and six
    # production call sites read exactly that as "may this store write?":
    # source_sync.py:1018 and :1220, query_snapshots.py:1287,
    # attested_query_snapshots.py:2516 (the Wave 1 publication path), and
    # seed_fundamental_forensics_attested_history.py:680 and :821.  Omission
    # makes the type system itself refuse this store at those admission gates,
    # which is strictly stronger than a runtime raise after admission.  The
    # codebase already treats protocol non-membership as a meaningful refusal —
    # see tests/test_research_vault_strict_store.py:159.

    def get_bytes(self, key: str) -> bytes | None:
        del key
        raise AttestedHistoryStoreError(
            "attested-history reads must be bounded, not legacy unbounded reads"
        )

    def get_bytes_strict(self, key: str) -> bytes | None:
        del key
        raise AttestedHistoryStoreError(
            "attested-history reads must be bounded, not unbounded strict reads"
        )

    def list_prefix(self, prefix: str) -> list[str]:
        del prefix
        raise AttestedHistoryStoreError("attested-history serving forbids storage discovery")

    def exists(self, key: str) -> bool:
        del key
        raise AttestedHistoryStoreError("attested-history serving forbids storage discovery")

    def upload_time(self, key: str) -> str | None:
        del key
        raise AttestedHistoryStoreError("attested-history serving forbids storage discovery")

    def put_bytes(
        self,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> bool:
        del key, data, content_type
        self.write_attempts += 1
        raise AttestedHistoryStoreError("attested-history serving attempted a storage write")

    def delete(self, key: str) -> None:
        del key
        self.write_attempts += 1
        raise AttestedHistoryStoreError("attested-history serving attempted a storage delete")


def build_attested_history_store(
    *, env: Mapping[str, str] | None = None
) -> DedicatedAttestedHistoryStore | None:
    """Build the dedicated reader, or ``None`` when it is not configured.

    ``None`` means the four dedicated names are not all present: the caller
    turns that into a bounded 503 rather than reaching for another bucket.
    Values that ARE present but unusable raise
    :class:`AttestedHistoryStoreError`, because a typo in a deployed endpoint
    or bucket is a configuration defect the operator must see, not a silent
    "not configured yet".
    """
    source = os.environ if env is None else env
    values = {name: source.get(name, "") for name in ATTESTED_HISTORY_ENV_NAMES}
    if any(not isinstance(value, str) or not value for value in values.values()):
        return None
    return DedicatedAttestedHistoryStore(
        endpoint=values["FF_ATTESTED_R2_READONLY_ENDPOINT"],
        parent_access_key_id=values["FF_ATTESTED_R2_READONLY_ACCESS_KEY_ID"],
        parent_secret_access_key=values["FF_ATTESTED_R2_READONLY_SECRET_ACCESS_KEY"],
        bucket=values["FF_ATTESTED_R2_READONLY_BUCKET"],
    )
