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
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol, runtime_checkable

log = logging.getLogger("research_vault.r2_store")

_MAX_STRICT_STREAM_READ_CALLS = 8_192


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


def _validate_bounded_read_limit(maximum_bytes: int) -> int:
    """Validate a byte cap without silently coercing surprising caller input."""
    if isinstance(maximum_bytes, bool) or not isinstance(maximum_bytes, int):
        raise ValueError("maximum_bytes must be a non-negative integer")
    if maximum_bytes < 0:
        raise ValueError("maximum_bytes must be a non-negative integer")
    return maximum_bytes


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


class R2Store:
    """boto3-backed store for the private research bucket."""

    def __init__(self, bucket: str, client=None):
        self.bucket = bucket
        self._s3 = client if client is not None else _r2_client()

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

    def get_bytes_strict_bounded(self, key: str, maximum_bytes: int) -> bytes | None:
        """Strictly read at most ``maximum_bytes`` without unbounded buffering.

        ``ContentLength`` is used only as an early rejection optimization: the
        body is still read with ``maximum + 1`` so a lying or absent header
        cannot evade the cap.  The stream is closed on every path, including
        a rejected header or a read error.  This deliberately does *not* turn
        permission/network/body errors into a missing object.
        """
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

    def put_bytes(self, key: str, data: bytes,
                  content_type: str = "application/octet-stream") -> bool:
        if not self.available:
            return False
        try:
            self._s3.put_object(Bucket=self.bucket, Key=key, Body=data,
                                ContentType=content_type)
            return True
        except Exception as e:  # noqa: BLE001
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

    def get_bytes_strict_bounded(self, key: str, maximum_bytes: int) -> bytes | None:
        """Strict local read with a hard ``maximum + 1`` streaming cap.

        This mirrors the remote bounded method exactly: a missing path alone
        maps to ``None``; traversal, permissions, and oversize content remain
        hard failures for immutable-source consumers.
        """
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

    def put_bytes(self, key: str, data: bytes,
                  content_type: str = "application/octet-stream") -> bool:
        try:
            p = self._p(key)
            p.parent.mkdir(parents=True, exist_ok=True)
            tmp = p.with_suffix(p.suffix + ".tmp")
            tmp.write_bytes(data)
            os.replace(tmp, p)
            return True
        except Exception as e:  # noqa: BLE001
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
