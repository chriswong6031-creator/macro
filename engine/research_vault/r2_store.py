"""research_vault.r2_store — object store for the PRIVATE research bucket.

Two interchangeable backends behind one small interface
(``get_bytes / get_bytes_strict / get_bytes_strict_bounded / put_bytes /
list_prefix / exists / upload_time``):

  - :class:`R2Store` — boto3 wrapper on the private bucket ``R2_RESEARCH_BUCKET``.
    Reuses the account access key (env ``R2_ENDPOINT / R2_ACCESS_KEY_ID /
    R2_SECRET_ACCESS_KEY``) exactly like ``scripts/publish_r2._client`` but
    targets a DIFFERENT bucket. Degrades to ``None`` (no-op) when creds absent.
  - :class:`LocalStore` — a filesystem backend rooted at a dir. Selected when
    env ``RESEARCH_LOCAL_STORE=<dir>`` is set. REQUIRED for tests + local
    dry-runs so nothing needs live R2 credentials.

The masterplan (§4) keeps these keys in the private bucket:
    research_inbox/<id>.pdf, research_inbox/<id>.json
    research_inbox/top_picks/…               (optional top-pick routing)
    research_inbox/_processed/<id>.json       (ingest receipts / idempotency)
    research_vault/<id>.pdf                    (promoted canonical PDF)
    research_vault/catalog.json, research_vault/corpus.sqlite

``get_bytes`` never raises on a missing object — get/exists return None/False.
It remains deliberately fail-open for the existing ingest/read paths.
``get_bytes_strict`` is the separate fail-closed primitive used where an
immutable publication must not confuse an unavailable store with a genuinely
absent object: it returns ``None`` only for an authoritative not-found result.
"""
from __future__ import annotations

import errno
import fcntl
import logging
import os
import stat
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Protocol, runtime_checkable

log = logging.getLogger("research_vault.r2_store")

_MAX_STRICT_STREAM_READ_CALLS = 8_192
HARD_MAX_STRICT_CONDITIONAL_OBJECT_BYTES = 16 * 1024


@runtime_checkable
class Store(Protocol):
    """The minimal object-store surface the ingest pipeline depends on."""

    def get_bytes(self, key: str) -> bytes | None: ...
    def put_bytes(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> bool: ...
    def list_prefix(self, prefix: str) -> list[str]: ...
    def exists(self, key: str) -> bool: ...
    def upload_time(self, key: str) -> str | None: ...


@runtime_checkable
class StrictReadStore(Store, Protocol):
    """An object store that supports fail-closed immutable-object reads.

    Kept separate from :class:`Store` because the legacy protocol is used as a
    runtime structural check by fail-open callers with deliberately smaller
    custom store implementations.
    """

    def get_bytes_strict(self, key: str) -> bytes | None: ...


@runtime_checkable
class StrictBoundedReadStore(StrictReadStore, Protocol):
    """A strict store which can cap an immutable-object read before buffering it.

    ``None`` retains the narrow meaning from :class:`StrictReadStore`: the
    backing service authoritatively reported that the object does not exist.
    A response that is too large, malformed, unavailable, unauthorized, or
    fails while closing its body must raise.  Snapshot consumers use this
    protocol for untrusted remote manifest and source-object bytes; the older
    strict method remains available for compatible callers that do not yet
    have a defensible byte ceiling.
    """

    def get_bytes_strict_bounded(self, key: str, maximum_bytes: int) -> bytes | None: ...


@dataclass(frozen=True)
class VersionedBytes:
    """One bounded object value and its opaque exact-predecessor token."""

    data: bytes | None
    version: str | None

    def __post_init__(self) -> None:
        missing = self.data is None
        if missing != (self.version is None):
            raise ValueError("versioned bytes must be wholly present or wholly absent")
        if not missing and (
            type(self.data) is not bytes
            or not isinstance(self.version, str)
            or not self.version
        ):
            raise ValueError("present versioned bytes require exact bytes and a non-empty version")


@runtime_checkable
class StrictConditionalWriteStore(StrictBoundedReadStore, Protocol):
    """A strict store with an atomic opaque-version compare-and-swap primitive.

    ``False`` from the write has exactly one meaning: the backing authority
    rejected the supplied predecessor. Operational and protocol failures raise.
    ``expected_version=None`` means the key must still be absent.
    """

    def get_bytes_strict_bounded_versioned(
        self, key: str, maximum_bytes: int,
    ) -> VersionedBytes: ...

    def validate_strict_conditional_write_capability(self) -> None: ...

    def put_bytes_strict_conditional(
        self,
        key: str,
        data: bytes,
        *,
        expected_version: str | None,
        content_type: str = "application/octet-stream",
    ) -> bool: ...


def _validate_bounded_read_limit(maximum_bytes: int) -> int:
    """Validate a byte cap without silently coercing surprising caller input."""
    if isinstance(maximum_bytes, bool) or not isinstance(maximum_bytes, int):
        raise ValueError("maximum_bytes must be a non-negative integer")
    if maximum_bytes < 0:
        raise ValueError("maximum_bytes must be a non-negative integer")
    return maximum_bytes


class BoundedReadError(RuntimeError):
    """A strict bounded object read could not establish exact bytes."""


class BoundedReadTooLarge(BoundedReadError):
    """An object exceeded its caller-authorized allocation boundary."""


class BoundedReadLengthMismatch(BoundedReadError):
    """An object's authoritative or observed length was not exact."""


class BoundedReadProtocolError(BoundedReadError):
    """A backend response or filesystem object violated the read protocol."""


@runtime_checkable
class BoundedStrictReadStore(Protocol):
    """Opt-in fail-closed reader with a pre-allocation byte boundary."""

    def get_bytes_strict_bounded(
        self, key: str, *, expected_byte_length: int, max_byte_length: int,
    ) -> bytes | None: ...


def _validate_bounded_lengths(*, expected_byte_length: int, max_byte_length: int) -> None:
    if (
        isinstance(expected_byte_length, bool)
        or not isinstance(expected_byte_length, int)
        or expected_byte_length < 0
        or isinstance(max_byte_length, bool)
        or not isinstance(max_byte_length, int)
        or max_byte_length < 0
        or expected_byte_length > max_byte_length
    ):
        raise ValueError("bounded object lengths must satisfy 0 <= expected <= maximum")


# ---------------------------------------------------------------------------
# boto3 client (mirrors scripts/publish_r2._client, private bucket)
# ---------------------------------------------------------------------------

def _r2_client():
    """S3 client for R2, or None when creds are absent (graceful no-op).

    Copies scripts/publish_r2._client construction verbatim (region 'auto',
    s3v4, when_required checksum). A SEPARATE Cloudflare account for the research
    vault is supported via R2_RESEARCH_ENDPOINT / R2_RESEARCH_ACCESS_KEY_ID /
    R2_RESEARCH_SECRET_ACCESS_KEY (+ R2_RESEARCH_BUCKET); each falls back to the
    shared R2_* var when unset (the same-account case).
    """
    ep = os.environ.get("R2_RESEARCH_ENDPOINT") or os.environ.get("R2_ENDPOINT")
    ak = os.environ.get("R2_RESEARCH_ACCESS_KEY_ID") or os.environ.get("R2_ACCESS_KEY_ID")
    sk = os.environ.get("R2_RESEARCH_SECRET_ACCESS_KEY") or os.environ.get("R2_SECRET_ACCESS_KEY")
    if not (ep and ak and sk):
        return None
    import boto3
    from botocore.config import Config
    kw = dict(region_name="auto", signature_version="s3v4",
              max_pool_connections=32, retries={"max_attempts": 5, "mode": "adaptive"},
              connect_timeout=15, read_timeout=60)
    try:  # newer botocore: R2 rejects the default CRC32 trailer
        cfg = Config(**kw, request_checksum_calculation="when_required",
                     response_checksum_validation="when_required")
    except TypeError:
        cfg = Config(**kw)
    return boto3.client("s3", endpoint_url=ep, aws_access_key_id=ak,
                        aws_secret_access_key=sk, config=cfg)


def _is_authoritative_r2_not_found(error: Exception) -> bool:
    """Whether *error* is the S3/R2 not-found response we may safely soften.

    The strict read path must not infer absence from a generic exception.  In
    particular, a 403, timeout, malformed response, or credential failure is
    operationally distinct from a key that R2 authoritatively says is absent.
    ``ClientError`` is imported lazily so the local-only test/runtime path does
    not acquire a boto3 dependency.
    """
    try:
        from botocore.exceptions import ClientError
    except ImportError:
        return False
    if not isinstance(error, ClientError):
        return False
    response = getattr(error, "response", None)
    if not isinstance(response, dict):
        return False
    details = response.get("Error")
    if not isinstance(details, dict):
        return False
    return str(details.get("Code", "")) in {"404", "NoSuchKey", "NotFound"}


def _is_authoritative_r2_conditional_conflict(error: Exception) -> bool:
    """Whether R2 authoritatively rejected an exact-predecessor PUT."""
    try:
        from botocore.exceptions import ClientError
    except ImportError:
        return False
    if not isinstance(error, ClientError):
        return False
    response = getattr(error, "response", None)
    if not isinstance(response, dict):
        return False
    details = response.get("Error")
    metadata = response.get("ResponseMetadata")
    code = str(details.get("Code", "")) if isinstance(details, dict) else ""
    status = metadata.get("HTTPStatusCode") if isinstance(metadata, dict) else None
    return code in {
        "409", "412", "ConditionalRequestConflict", "PreconditionFailed",
    } or status in {409, 412}


class R2Store:
    """boto3-backed store for the private research bucket."""

    def __init__(self, bucket: str, client=None):
        self.bucket = bucket
        self._s3 = client if client is not None else _r2_client()
        self.last_put_error: BaseException | None = None

    @property
    def available(self) -> bool:
        return self._s3 is not None and bool(self.bucket)

    def get_bytes(self, key: str) -> bytes | None:
        if not self.available:
            return None
        try:
            r = self._s3.get_object(Bucket=self.bucket, Key=key)
            return r["Body"].read()
        except Exception as e:  # noqa: BLE001 — missing key / transient error
            log.debug("r2 get miss %s: %s", key, e)
            return None

    def get_bytes_strict(self, key: str) -> bytes | None:
        """Read an immutable object without converting operational failure to a miss.

        ``None`` means R2 returned one of its explicit not-found ``ClientError``
        codes (404, ``NoSuchKey``, or ``NotFound``).  Missing credentials, a
        permission error, network/service failure, or body read failure all
        propagate so snapshot publication cannot silently publish from an
        incomplete view of the object store.
        """
        if not self.available:
            raise RuntimeError("R2 store unavailable: missing bucket or credentials")
        try:
            response = self._s3.get_object(Bucket=self.bucket, Key=key)
        except Exception as error:
            if _is_authoritative_r2_not_found(error):
                return None
            raise
        if not isinstance(response, dict):
            raise RuntimeError("R2 get_object returned a malformed response")
        body = response.get("Body")
        if body is None or not callable(getattr(body, "read", None)):
            raise RuntimeError("R2 get_object response is missing a readable body")
        close = getattr(body, "close", None)
        if not callable(close):
            raise RuntimeError("R2 get_object response body is not closeable")
        try:
            content = body.read()
        finally:
            close()
        if not isinstance(content, bytes):
            raise RuntimeError("R2 object body returned non-bytes")
        return content

    def get_bytes_strict_bounded(
        self,
        key: str,
        maximum_bytes: int | None = None,
        *,
        expected_byte_length: int | None = None,
        max_byte_length: int | None = None,
    ) -> bytes | None:
        """Read a capped object in legacy-cap or exact-length mode.

        The positional ``maximum_bytes`` mode is the pre-existing generic
        strict-cap contract.  Company Facts additionally needs a HEAD/ETag
        bound exact-length read, selected only by the two keyword arguments.
        Keeping both prevents a rebase from weakening either established
        caller's fail-closed boundary.
        """
        if maximum_bytes is not None:
            if expected_byte_length is not None or max_byte_length is not None:
                raise ValueError("bounded read modes are mutually exclusive")
            limit = _validate_bounded_read_limit(maximum_bytes)
            if not self.available:
                raise RuntimeError("R2 store unavailable: missing bucket or credentials")
            try:
                response = self._s3.get_object(Bucket=self.bucket, Key=key)
            except Exception as error:
                if _is_authoritative_r2_not_found(error):
                    return None
                raise
            if not isinstance(response, dict):
                raise RuntimeError("R2 get_object returned a malformed response")
            body = response.get("Body")
            if body is None or not callable(getattr(body, "read", None)):
                raise RuntimeError("R2 get_object response is missing a readable body")
            close = getattr(body, "close", None)
            if not callable(close):
                raise RuntimeError("R2 get_object response body is not closeable")
            try:
                announced_length = response.get("ContentLength")
                if announced_length is not None:
                    if (
                        isinstance(announced_length, bool)
                        or not isinstance(announced_length, int)
                        or announced_length < 0
                    ):
                        raise RuntimeError("R2 get_object returned an invalid ContentLength")
                    if announced_length > limit:
                        raise ValueError(
                            f"R2 object exceeds bounded read limit ({announced_length} > {limit})"
                        )
                chunks: list[bytes] = []
                observed = 0
                read_calls = 0
                while observed <= limit:
                    read_calls += 1
                    if read_calls > _MAX_STRICT_STREAM_READ_CALLS:
                        raise RuntimeError("R2 object body exceeded strict read iteration limit")
                    requested = limit + 1 - observed
                    chunk = body.read(requested)
                    if not isinstance(chunk, bytes):
                        raise RuntimeError("R2 object body returned non-bytes")
                    if not chunk:
                        break
                    if len(chunk) > requested:
                        raise RuntimeError("R2 object body returned more bytes than requested")
                    chunks.append(chunk)
                    observed += len(chunk)
                content = b"".join(chunks)
            finally:
                close()
            if len(content) > limit:
                raise ValueError(
                    f"R2 object exceeds bounded read limit ({len(content)} > {limit})"
                )
            return content

        if expected_byte_length is None or max_byte_length is None:
            raise ValueError("expected and maximum byte lengths are required")
        _validate_bounded_lengths(
            expected_byte_length=expected_byte_length, max_byte_length=max_byte_length,
        )
        if not self.available:
            raise RuntimeError("R2 store unavailable: missing bucket or credentials")
        try:
            head = self._s3.head_object(Bucket=self.bucket, Key=key)
        except Exception as error:
            if _is_authoritative_r2_not_found(error):
                return None
            raise
        head_length = head.get("ContentLength") if isinstance(head, dict) else None
        if (
            isinstance(head_length, bool)
            or not isinstance(head_length, int)
            or head_length != expected_byte_length
            or head_length > max_byte_length
        ):
            if isinstance(head_length, int) and not isinstance(head_length, bool) and head_length > max_byte_length:
                raise BoundedReadTooLarge("R2 bounded object exceeds maximum length")
            raise BoundedReadLengthMismatch("R2 bounded object HEAD length mismatch")
        etag = head.get("ETag") if isinstance(head, dict) else None
        if not isinstance(etag, str) or not etag:
            raise BoundedReadProtocolError("R2 bounded object HEAD lacks a valid ETag")
        request = {"Bucket": self.bucket, "Key": key}
        if expected_byte_length > 0:
            request["Range"] = f"bytes=0-{expected_byte_length}"
        request["IfMatch"] = etag
        try:
            response = self._s3.get_object(**request)
        except Exception as error:
            if _is_authoritative_r2_not_found(error):
                return None
            raise
        body = response.get("Body") if isinstance(response, dict) else None
        if body is None or not callable(getattr(body, "read", None)):
            raise BoundedReadProtocolError("R2 bounded object response has no readable body")
        try:
            response_etag = response.get("ETag")
            if response_etag != etag:
                raise BoundedReadProtocolError("R2 bounded object GET/HEAD ETag mismatch")
            response_length = response.get("ContentLength")
            if (
                isinstance(response_length, bool)
                or not isinstance(response_length, int)
                or response_length < 0
                or response_length > max_byte_length
                or response_length > expected_byte_length + 1
            ):
                raise BoundedReadTooLarge("R2 bounded object GET length exceeds read boundary")
            chunks: list[bytes] = []
            observed = 0
            boundary = expected_byte_length + 1
            while observed < boundary:
                chunk = body.read(min(1024 * 1024, boundary - observed))
                if not isinstance(chunk, bytes):
                    raise BoundedReadProtocolError("R2 bounded object body returned non-bytes")
                if not chunk:
                    break
                chunks.append(chunk)
                observed += len(chunk)
            payload = b"".join(chunks)
            if len(payload) != expected_byte_length:
                raise BoundedReadLengthMismatch("R2 bounded object body length mismatch")
            if response_length != expected_byte_length:
                raise BoundedReadLengthMismatch("R2 bounded object GET length mismatch")
            return payload
        finally:
            close = getattr(body, "close", None)
            if callable(close):
                close()

    def get_bytes_strict_bounded_versioned(
        self, key: str, maximum_bytes: int,
    ) -> VersionedBytes:
        """Read one capped R2 object together with its exact service ETag."""
        limit = _validate_bounded_read_limit(maximum_bytes)
        if not self.available:
            raise RuntimeError("R2 store unavailable: missing bucket or credentials")
        try:
            response = self._s3.get_object(Bucket=self.bucket, Key=key)
        except Exception as error:
            if _is_authoritative_r2_not_found(error):
                return VersionedBytes(data=None, version=None)
            raise
        if not isinstance(response, dict):
            raise RuntimeError("R2 get_object returned a malformed response")
        body = response.get("Body")
        if body is None or not callable(getattr(body, "read", None)):
            raise RuntimeError("R2 get_object response is missing a readable body")
        close = getattr(body, "close", None)
        if not callable(close):
            raise RuntimeError("R2 get_object response body is not closeable")
        try:
            etag = response.get("ETag")
            if not isinstance(etag, str) or not etag:
                raise RuntimeError("R2 versioned get_object response lacks a valid ETag")
            announced_length = response.get("ContentLength")
            if announced_length is not None:
                if (
                    isinstance(announced_length, bool)
                    or not isinstance(announced_length, int)
                    or announced_length < 0
                ):
                    raise RuntimeError("R2 get_object returned an invalid ContentLength")
                if announced_length > limit:
                    raise ValueError(
                        f"R2 object exceeds bounded read limit ({announced_length} > {limit})"
                    )
            chunks: list[bytes] = []
            observed = 0
            read_calls = 0
            while observed <= limit:
                read_calls += 1
                if read_calls > _MAX_STRICT_STREAM_READ_CALLS:
                    raise RuntimeError("R2 object body exceeded strict read iteration limit")
                requested = limit + 1 - observed
                chunk = body.read(requested)
                if not isinstance(chunk, bytes):
                    raise RuntimeError("R2 object body returned non-bytes")
                if not chunk:
                    break
                if len(chunk) > requested:
                    raise RuntimeError("R2 object body returned more bytes than requested")
                chunks.append(chunk)
                observed += len(chunk)
            content = b"".join(chunks)
        finally:
            close()
        if len(content) > limit:
            raise ValueError(
                f"R2 object exceeds bounded read limit ({len(content)} > {limit})"
            )
        if announced_length is not None and len(content) != announced_length:
            raise BoundedReadLengthMismatch(
                "R2 versioned object ContentLength/body length mismatch"
            )
        return VersionedBytes(data=content, version=etag)

    def _require_conditional_put_capability(self) -> None:
        """Fail before I/O when the active botocore model cannot sign CAS headers."""
        try:
            operation = self._s3.meta.service_model.operation_model("PutObject")
            members = operation.input_shape.members
            supported = "IfMatch" in members and "IfNoneMatch" in members
        except Exception as exc:
            raise RuntimeError("R2 conditional PutObject capability is unavailable") from exc
        if not supported:
            raise RuntimeError("R2 conditional PutObject capability is unavailable")

    def validate_strict_conditional_write_capability(self) -> None:
        """Validate CAS support from the local SDK model without remote I/O."""
        self._require_conditional_put_capability()

    def put_bytes_strict_conditional(
        self,
        key: str,
        data: bytes,
        *,
        expected_version: str | None,
        content_type: str = "application/octet-stream",
    ) -> bool:
        """Atomically create or replace an R2 object at one exact predecessor."""
        if type(data) is not bytes:
            raise TypeError("conditional object data must be exact bytes")
        if expected_version is not None and (
            not isinstance(expected_version, str) or not expected_version
        ):
            raise ValueError("expected_version must be None or a non-empty string")
        if not isinstance(content_type, str) or not content_type:
            raise ValueError("content_type must be a non-empty string")
        if not self.available:
            raise RuntimeError("R2 store unavailable: missing bucket or credentials")
        self.validate_strict_conditional_write_capability()
        arguments = {
            "Bucket": self.bucket,
            "Key": key,
            "Body": data,
            "ContentType": content_type,
        }
        if expected_version is None:
            arguments["IfNoneMatch"] = "*"
        else:
            arguments["IfMatch"] = expected_version
        try:
            self._s3.put_object(**arguments)
        except Exception as error:
            if _is_authoritative_r2_conditional_conflict(error):
                return False
            raise
        return True

    def put_bytes(self, key: str, data: bytes,
                  content_type: str = "application/octet-stream") -> bool:
        self.last_put_error = None
        if not self.available:
            return False
        try:
            self._s3.put_object(Bucket=self.bucket, Key=key, Body=data,
                                ContentType=content_type)
            return True
        except Exception as e:  # noqa: BLE001
            self.last_put_error = e
            log.warning("r2 put failed %s: %s", key, e)
            return False

    def list_prefix(self, prefix: str) -> list[str]:
        if not self.available:
            return []
        out: list[str] = []
        tok = None
        try:
            while True:
                kw = {"Bucket": self.bucket, "Prefix": prefix}
                if tok:
                    kw["ContinuationToken"] = tok
                r = self._s3.list_objects_v2(**kw)
                out.extend(o["Key"] for o in r.get("Contents", []))
                if not r.get("IsTruncated"):
                    break
                tok = r.get("NextContinuationToken")
        except Exception as e:  # noqa: BLE001
            log.warning("r2 list failed %s: %s", prefix, e)
        return out

    def exists(self, key: str) -> bool:
        if not self.available:
            return False
        try:
            self._s3.head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception:  # noqa: BLE001 — 404 or transient
            return False

    def upload_time(self, key: str) -> str | None:
        """ISO-8601 UTC LastModified of the object, or None if absent."""
        if not self.available:
            return None
        try:
            r = self._s3.head_object(Bucket=self.bucket, Key=key)
            lm = r.get("LastModified")
            if lm is None:
                return None
            if lm.tzinfo is None:
                lm = lm.replace(tzinfo=timezone.utc)
            return lm.astimezone(timezone.utc).isoformat()
        except Exception:  # noqa: BLE001
            return None


class LocalStore:
    """Filesystem-backed store rooted at ``root`` (keys are relative paths).

    Mirrors the R2 semantics (fail-open reads, atomic-ish writes). Used by tests
    and ``--local`` dry-runs so no R2 credentials are needed.
    """

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.last_put_error: BaseException | None = None

    @property
    def available(self) -> bool:
        return True

    def _p(self, key: str) -> Path:
        # Keys are posix-style; join under root. Reject traversal escapes.
        rel = Path(key)
        if rel.is_absolute() or ".." in rel.parts:
            raise ValueError(f"unsafe key: {key!r}")
        return self.root / rel

    def _open_strict_read(self, key: str):
        """Open a key descriptor-relative without following swappable symlinks."""
        candidate = self._p(key)
        relative = candidate.relative_to(self.root)
        parts = relative.parts
        if not parts:
            raise ValueError(f"unsafe empty key: {key!r}")
        directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        nofollow = getattr(os, "O_NOFOLLOW", 0)
        directory_fd = os.open(self.root, directory_flags)
        try:
            for part in parts[:-1]:
                next_fd = os.open(
                    part,
                    directory_flags | nofollow,
                    dir_fd=directory_fd,
                )
                os.close(directory_fd)
                directory_fd = next_fd
            file_fd = os.open(parts[-1], os.O_RDONLY | nofollow, dir_fd=directory_fd)
        except OSError as exc:
            if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
                raise ValueError(f"unsafe key traverses symlink: {key!r}") from exc
            raise
        finally:
            os.close(directory_fd)
        return os.fdopen(file_fd, "rb", closefd=True)

    def get_bytes(self, key: str) -> bytes | None:
        try:
            p = self._p(key)
            return p.read_bytes() if p.is_file() else None
        except Exception as e:  # noqa: BLE001
            log.debug("local get miss %s: %s", key, e)
            return None

    def get_bytes_strict(self, key: str) -> bytes | None:
        """Read a local object, softening only an actual missing-path result.

        Unlike ``get_bytes``, unsafe keys and filesystem/read failures are not
        folded into ``None``.  That preserves the lexical traversal guard in
        :meth:`_p` and lets immutable snapshot callers fail closed when a local
        backing volume becomes unreadable.
        """
        try:
            with self._open_strict_read(key) as handle:
                return handle.read()
        except FileNotFoundError:
            return None

    def get_bytes_strict_bounded(
        self,
        key: str,
        maximum_bytes: int | None = None,
        *,
        expected_byte_length: int | None = None,
        max_byte_length: int | None = None,
    ) -> bytes | None:
        """Strict local read with a hard ``maximum + 1`` streaming cap.

        This mirrors the remote bounded method exactly: a missing path alone
        maps to ``None``; traversal, permissions, and oversize content remain
        hard failures for immutable-source consumers.
        """
        if maximum_bytes is not None:
            if expected_byte_length is not None or max_byte_length is not None:
                raise ValueError("bounded read modes are mutually exclusive")
            limit = _validate_bounded_read_limit(maximum_bytes)
            try:
                with self._open_strict_read(key) as handle:
                    content = handle.read(limit + 1)
            except FileNotFoundError:
                return None
            if len(content) > limit:
                raise ValueError(
                    f"local object exceeds bounded read limit ({len(content)} > {limit})"
                )
            return content

        if expected_byte_length is None or max_byte_length is None:
            raise ValueError("expected and maximum byte lengths are required")
        """Read a regular local object through no-follow descriptors, with a cap."""
        _validate_bounded_lengths(
            expected_byte_length=expected_byte_length, max_byte_length=max_byte_length,
        )
        parts = key.split("/")
        if (
            not key
            or key.startswith("/")
            or any(part in {"", ".", ".."} or "\\" in part for part in parts)
        ):
            raise ValueError(f"unsafe key: {key!r}")
        directory_flags = (
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        )
        descriptors: list[int] = []
        try:
            # ``abspath`` is lexical (it does not resolve symlinks), letting the
            # descriptor walk reject every linked component itself.
            root = Path(os.path.abspath(self.root))
            anchor_fd = os.open("/", directory_flags)
            descriptors.append(anchor_fd)
            parent_fd = anchor_fd
            for part in root.parts[1:]:
                try:
                    checked = os.stat(part, dir_fd=parent_fd, follow_symlinks=False)
                except FileNotFoundError as exc:
                    raise BoundedReadProtocolError("local bounded store root is missing") from exc
                if stat.S_ISLNK(checked.st_mode) or not stat.S_ISDIR(checked.st_mode):
                    raise BoundedReadProtocolError(
                        "local bounded store root cannot follow a symlink"
                    )
                opened = os.open(part, directory_flags, dir_fd=parent_fd)
                metadata = os.fstat(opened)
                if (metadata.st_dev, metadata.st_ino) != (checked.st_dev, checked.st_ino):
                    os.close(opened)
                    raise BoundedReadProtocolError(
                        "local bounded store root changed during secure open"
                    )
                descriptors.append(opened)
                parent_fd = opened
            for part in parts[:-1]:
                try:
                    checked = os.stat(part, dir_fd=parent_fd, follow_symlinks=False)
                except FileNotFoundError:
                    return None
                if stat.S_ISLNK(checked.st_mode) or not stat.S_ISDIR(checked.st_mode):
                    raise BoundedReadProtocolError(
                        "local bounded object parent is not a no-follow directory"
                    )
                opened = os.open(part, directory_flags, dir_fd=parent_fd)
                metadata = os.fstat(opened)
                if (metadata.st_dev, metadata.st_ino) != (checked.st_dev, checked.st_ino):
                    os.close(opened)
                    raise BoundedReadProtocolError(
                        "local bounded object parent changed during open"
                    )
                descriptors.append(opened)
                parent_fd = opened
            try:
                checked = os.stat(parts[-1], dir_fd=parent_fd, follow_symlinks=False)
            except FileNotFoundError:
                return None
            if stat.S_ISLNK(checked.st_mode) or not stat.S_ISREG(checked.st_mode):
                raise BoundedReadProtocolError("local bounded object is not a regular file")
            object_fd = os.open(
                parts[-1], os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=parent_fd,
            )
            descriptors.append(object_fd)
            metadata = os.fstat(object_fd)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or (metadata.st_dev, metadata.st_ino) != (checked.st_dev, checked.st_ino)
            ):
                raise BoundedReadProtocolError("local bounded object changed during secure open")
            if metadata.st_size > max_byte_length:
                raise BoundedReadTooLarge("local bounded object exceeds maximum length")
            if metadata.st_size != expected_byte_length:
                raise BoundedReadLengthMismatch("local bounded object length mismatch")
            payload = bytearray()
            boundary = expected_byte_length + 1
            while len(payload) < boundary:
                chunk = os.read(object_fd, min(1024 * 1024, boundary - len(payload)))
                if not chunk:
                    break
                payload.extend(chunk)
            if len(payload) != expected_byte_length:
                raise BoundedReadLengthMismatch("local bounded object changed during read")
            return bytes(payload)
        finally:
            for descriptor in reversed(descriptors):
                os.close(descriptor)

    @staticmethod
    def _local_version(data: bytes) -> str:
        return "sha256:" + sha256(b"research-vault-local-version-v1\0" + data).hexdigest()

    @staticmethod
    def _conditional_key_parts(key: str) -> tuple[str, ...]:
        if (
            not isinstance(key, str)
            or not key
            or key.startswith("/")
            or "\\" in key
        ):
            raise ValueError(f"unsafe key: {key!r}")
        parts = tuple(key.split("/"))
        if any(part in {"", ".", ".."} for part in parts):
            raise ValueError(f"unsafe key: {key!r}")
        return parts

    @staticmethod
    def _version_at(parent_fd: int, name: str) -> str | None:
        try:
            descriptor = os.open(
                name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=parent_fd,
            )
        except FileNotFoundError:
            return None
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                raise BoundedReadProtocolError("local conditional object is not a regular file")
            if metadata.st_size > HARD_MAX_STRICT_CONDITIONAL_OBJECT_BYTES:
                raise BoundedReadTooLarge(
                    "local conditional predecessor exceeds its byte safety limit"
                )
            digest = sha256(b"research-vault-local-version-v1\0")
            observed = 0
            while observed <= HARD_MAX_STRICT_CONDITIONAL_OBJECT_BYTES:
                requested = HARD_MAX_STRICT_CONDITIONAL_OBJECT_BYTES + 1 - observed
                chunk = os.read(descriptor, min(1024 * 1024, requested))
                if not chunk:
                    break
                if len(chunk) > requested:
                    raise BoundedReadProtocolError(
                        "local conditional predecessor read exceeded its requested boundary"
                    )
                observed += len(chunk)
                digest.update(chunk)
            if observed > HARD_MAX_STRICT_CONDITIONAL_OBJECT_BYTES:
                raise BoundedReadTooLarge(
                    "local conditional predecessor exceeds its byte safety limit"
                )
            if observed != metadata.st_size:
                raise BoundedReadLengthMismatch(
                    "local conditional predecessor changed during version read"
                )
            return "sha256:" + digest.hexdigest()
        finally:
            os.close(descriptor)

    def get_bytes_strict_bounded_versioned(
        self, key: str, maximum_bytes: int,
    ) -> VersionedBytes:
        """Read bounded local bytes and derive a portable opaque value token."""
        data = self.get_bytes_strict_bounded(key, maximum_bytes)
        if data is None:
            return VersionedBytes(data=None, version=None)
        return VersionedBytes(data=data, version=self._local_version(data))

    def validate_strict_conditional_write_capability(self) -> None:
        """Local conditional writes are implemented directly by this adapter."""

    def put_bytes_strict_conditional(
        self,
        key: str,
        data: bytes,
        *,
        expected_version: str | None,
        content_type: str = "application/octet-stream",
    ) -> bool:
        """Cross-process exact-predecessor replacement for the local test lane."""
        if type(data) is not bytes:
            raise TypeError("conditional object data must be exact bytes")
        if expected_version is not None and (
            not isinstance(expected_version, str) or not expected_version
        ):
            raise ValueError("expected_version must be None or a non-empty string")
        if not isinstance(content_type, str) or not content_type:
            raise ValueError("content_type must be a non-empty string")
        del content_type
        parts = self._conditional_key_parts(key)
        directory_flags = (
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        )
        root_fd = os.open(self.root, directory_flags)
        lock_fd: int | None = None
        parent_fd: int | None = None
        temporary: str | None = None
        try:
            # Open-or-create without a check/create race.  On a missing key one
            # contender creates with O_EXCL; all losers retry the no-follow open
            # of that exact regular file.
            while lock_fd is None:
                try:
                    lock_fd = os.open(
                        ".strict-conditional-write.lock",
                        os.O_RDWR | getattr(os, "O_NOFOLLOW", 0),
                        dir_fd=root_fd,
                    )
                except FileNotFoundError:
                    try:
                        lock_fd = os.open(
                            ".strict-conditional-write.lock",
                            os.O_RDWR | os.O_CREAT | os.O_EXCL
                            | getattr(os, "O_NOFOLLOW", 0),
                            0o600,
                            dir_fd=root_fd,
                        )
                    except FileExistsError:
                        continue
            if not stat.S_ISREG(os.fstat(lock_fd).st_mode):
                raise BoundedReadProtocolError("local conditional lock is not a regular file")
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            parent_fd = os.dup(root_fd)
            for part in parts[:-1]:
                try:
                    os.mkdir(part, 0o700, dir_fd=parent_fd)
                except FileExistsError:
                    pass
                opened = os.open(part, directory_flags, dir_fd=parent_fd)
                if not stat.S_ISDIR(os.fstat(opened).st_mode):
                    os.close(opened)
                    raise BoundedReadProtocolError(
                        "local conditional object parent is not a directory"
                    )
                os.close(parent_fd)
                parent_fd = opened
            current_version = self._version_at(parent_fd, parts[-1])
            if current_version != expected_version:
                return False
            temporary = f".{parts[-1]}.cas.{os.getpid()}.{time.time_ns()}"
            staged_fd = os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                0o600,
                dir_fd=parent_fd,
            )
            try:
                offset = 0
                while offset < len(data):
                    written = os.write(staged_fd, data[offset:])
                    if written <= 0:
                        raise OSError("local conditional write made no progress")
                    offset += written
                os.fsync(staged_fd)
            finally:
                os.close(staged_fd)
            os.replace(
                temporary, parts[-1], src_dir_fd=parent_fd, dst_dir_fd=parent_fd,
            )
            temporary = None
            os.fsync(parent_fd)
            return True
        finally:
            if temporary is not None and parent_fd is not None:
                try:
                    os.unlink(temporary, dir_fd=parent_fd)
                except FileNotFoundError:
                    pass
            if parent_fd is not None:
                os.close(parent_fd)
            if lock_fd is not None:
                try:
                    fcntl.flock(lock_fd, fcntl.LOCK_UN)
                finally:
                    os.close(lock_fd)
            os.close(root_fd)

    def put_bytes(self, key: str, data: bytes,
                  content_type: str = "application/octet-stream") -> bool:
        self.last_put_error = None
        try:
            p = self._p(key)
            p.parent.mkdir(parents=True, exist_ok=True)
            tmp = p.with_suffix(p.suffix + ".tmp")
            tmp.write_bytes(data)
            os.replace(tmp, p)
            return True
        except Exception as e:  # noqa: BLE001
            self.last_put_error = e
            log.warning("local put failed %s: %s", key, e)
            return False

    def list_prefix(self, prefix: str) -> list[str]:
        try:
            base = self.root
            out: list[str] = []
            for p in base.rglob("*"):
                if not p.is_file():
                    continue
                rel = p.relative_to(base).as_posix()
                if rel.startswith(prefix):
                    out.append(rel)
            return out
        except Exception as e:  # noqa: BLE001
            log.warning("local list failed %s: %s", prefix, e)
            return []

    def exists(self, key: str) -> bool:
        try:
            return self._p(key).is_file()
        except Exception:  # noqa: BLE001
            return False

    def upload_time(self, key: str) -> str | None:
        try:
            p = self._p(key)
            if not p.is_file():
                return None
            ts = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
            return ts.isoformat()
        except Exception:  # noqa: BLE001
            return None


# ---------------------------------------------------------------------------
# factory
# ---------------------------------------------------------------------------

def build_store(local_dir: str | Path | None = None) -> Store | None:
    """Build the active store.

    Precedence:
      1. explicit ``local_dir`` arg → :class:`LocalStore`.
      2. env ``RESEARCH_LOCAL_STORE`` set → :class:`LocalStore` at that dir.
      3. env ``R2_RESEARCH_BUCKET`` + R2 creds → :class:`R2Store`.
      4. otherwise → ``None`` (no store available; caller no-ops like publish_r2).
    """
    if local_dir:
        return LocalStore(local_dir)
    env_local = os.environ.get("RESEARCH_LOCAL_STORE")
    if env_local:
        return LocalStore(env_local)
    bucket = os.environ.get("R2_RESEARCH_BUCKET")
    if bucket:
        store = R2Store(bucket)
        if store.available:
            return store
        log.info("R2_RESEARCH_BUCKET set but R2 creds absent — no store")
        return None
    return None
