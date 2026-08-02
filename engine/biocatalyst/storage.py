"""Dedicated, verified private-object storage for the BioCatalyst worker.

BioCatalyst evidence is deliberately not allowed to inherit the shared R2
credentials used by unrelated product lanes.  A successful write means more
than an S3 ``put_object`` response: this module reads the exact bytes back and
checks their SHA-256 before the caller is allowed to advance a public pointer.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import mimetypes
from pathlib import Path, PurePosixPath
import re
from typing import Mapping, Protocol, runtime_checkable
from urllib.parse import urlsplit


_REQUIRED_R2_ENV = (
    "BIOCATALYST_R2_ENDPOINT",
    "BIOCATALYST_R2_BUCKET",
    "BIOCATALYST_R2_ACCESS_KEY_ID",
    "BIOCATALYST_R2_SECRET_ACCESS_KEY",
)
_HOSTNAME_RE = re.compile(
    r"(?!.*\.\.)(?!.*\.-)(?!.*-\.)[a-z0-9](?:[a-z0-9.-]{1,251})?[a-z0-9]"
)


class StorageError(RuntimeError):
    """A deliberately bounded storage failure code; never includes secrets."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class DedicatedR2Config:
    """The only credential shape accepted by the BioCatalyst worker."""

    endpoint: str
    bucket: str
    access_key_id: str = field(repr=False)
    secret_access_key: str = field(repr=False)

    @classmethod
    def from_environment(cls, environ: Mapping[str, str]) -> "DedicatedR2Config":
        missing = [name for name in _REQUIRED_R2_ENV if not environ.get(name, "").strip()]
        if missing:
            raise StorageError("BIOCATALYST_R2_CONFIG_MISSING")
        config = cls(
            endpoint=environ["BIOCATALYST_R2_ENDPOINT"].strip(),
            bucket=environ["BIOCATALYST_R2_BUCKET"].strip(),
            access_key_id=environ["BIOCATALYST_R2_ACCESS_KEY_ID"].strip(),
            secret_access_key=environ["BIOCATALYST_R2_SECRET_ACCESS_KEY"].strip(),
        )
        config.validate()
        return config

    def validate(self) -> None:
        # The worker only accepts a bare HTTPS S3 endpoint.  Accepting paths,
        # query strings, fragments, or userinfo makes the endpoint ambiguous
        # (and can quietly route signed requests somewhere unexpected).  We do
        # not hard-code an account hostname here: R2 supports account endpoints
        # and operator-owned custom hostnames, but their shape must remain a
        # root HTTPS authority.
        if not isinstance(self.endpoint, str):
            raise StorageError("BIOCATALYST_R2_ENDPOINT_INVALID")
        try:
            parsed = urlsplit(self.endpoint)
            port = parsed.port
        except (TypeError, ValueError):
            raise StorageError("BIOCATALYST_R2_ENDPOINT_INVALID") from None
        if (
            parsed.scheme.lower() != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
            # An explicit port has no valid R2 S3 endpoint use here.  Keeping
            # it out prevents a typo or a local proxy from becoming an
            # unreviewed production storage target.
            or port is not None
            or not _HOSTNAME_RE.fullmatch(parsed.hostname.lower())
        ):
            raise StorageError("BIOCATALYST_R2_ENDPOINT_INVALID")
        if not isinstance(self.bucket, str) or not re.fullmatch(
            r"(?!.*\.\.)(?!.*\.-)(?!.*-\.)[a-z0-9](?:[a-z0-9.-]{1,61})[a-z0-9]",
            self.bucket,
        ):
            raise StorageError("BIOCATALYST_R2_BUCKET_INVALID")


@runtime_checkable
class BinaryObjectStore(Protocol):
    """Small injectable surface used by the worker and its hermetic tests."""

    def get_bytes(self, key: str) -> bytes | None: ...

    def put_if_absent(
        self,
        key: str,
        data: bytes,
        *,
        content_type: str = "application/octet-stream",
    ) -> bool: ...


class DedicatedR2Store:
    """Thin R2 client that uses only ``BIOCATALYST_R2_*`` credentials."""

    def __init__(self, config: DedicatedR2Config, *, client: object | None = None) -> None:
        config.validate()
        self._config = config
        self._client = client if client is not None else self._build_client(config)
        self._assert_conditional_create_available(self._client)

    @staticmethod
    def _build_client(config: DedicatedR2Config) -> object:
        try:
            import boto3
            from botocore.config import Config
        except Exception:  # pragma: no cover - deployment dependency guard
            raise StorageError("BIOCATALYST_R2_CLIENT_UNAVAILABLE") from None

        options = dict(
            region_name="auto",
            signature_version="s3v4",
            max_pool_connections=8,
            retries={"max_attempts": 3, "mode": "standard"},
            connect_timeout=10,
            read_timeout=45,
        )
        try:
            client_config = Config(
                **options,
                request_checksum_calculation="when_required",
                response_checksum_validation="when_required",
            )
        except TypeError:  # Older botocore supports the same safe baseline.
            client_config = Config(**options)
        try:
            client = boto3.client(
                "s3",
                endpoint_url=config.endpoint,
                aws_access_key_id=config.access_key_id,
                aws_secret_access_key=config.secret_access_key,
                config=client_config,
            )
        except Exception:  # pragma: no cover - external client guard
            raise StorageError("BIOCATALYST_R2_CLIENT_UNAVAILABLE") from None
        return client

    @staticmethod
    def _assert_conditional_create_available(client: object) -> None:
        """Reject any SDK model that cannot issue an immutable conditional PUT."""

        try:
            service_model = client.meta.service_model
            operation = service_model.operation_model("PutObject")
            input_shape = operation.input_shape
            input_members = input_shape.members
        except Exception:  # pragma: no cover - deployment/model capability guard
            raise StorageError("BIOCATALYST_R2_CONDITIONAL_CREATE_UNAVAILABLE") from None
        try:
            supported = "IfNoneMatch" in input_members
        except Exception:  # pragma: no cover - malformed SDK model guard
            raise StorageError("BIOCATALYST_R2_CONDITIONAL_CREATE_UNAVAILABLE") from None
        if not supported:
            raise StorageError("BIOCATALYST_R2_CONDITIONAL_CREATE_UNAVAILABLE")

    @staticmethod
    def _provider_error_details(exc: BaseException) -> tuple[str, int | None]:
        """Extract only classification fields from an SDK error.

        Provider exceptions can embed request URLs, account IDs, and other
        operational detail.  Callers receive only a bounded ``StorageError``
        code, never this provider message.
        """

        response = getattr(exc, "response", None)
        if not isinstance(response, Mapping):
            return "", None
        error = response.get("Error", {})
        code = str(error.get("Code", "")) if isinstance(error, Mapping) else ""
        metadata = response.get("ResponseMetadata", {})
        raw_status = metadata.get("HTTPStatusCode") if isinstance(metadata, Mapping) else None
        try:
            status = int(raw_status)
        except (TypeError, ValueError):
            status = None
        return code, status

    def get_bytes(self, key: str) -> bytes | None:
        validated_key = validate_object_key(key)
        try:
            response = self._client.get_object(
                Bucket=self._config.bucket,
                Key=validated_key,
            )
        except Exception as exc:
            code, status = self._provider_error_details(exc)
            if code in {"NoSuchKey", "NoSuchObject", "NotFound", "404"} or status == 404:
                return None
            raise StorageError("BIOCATALYST_R2_READ_FAILED") from None
        try:
            raw = response["Body"].read()
        except Exception as exc:
            raise StorageError("BIOCATALYST_R2_READ_FAILED") from None
        if not isinstance(raw, (bytes, bytearray)):
            raise StorageError("BIOCATALYST_R2_READ_FAILED")
        return bytes(raw)

    def put_if_absent(
        self,
        key: str,
        data: bytes,
        *,
        content_type: str = "application/octet-stream",
    ) -> bool:
        """Conditionally create one immutable key; ``False`` means it already exists."""

        validated_key = validate_object_key(key)
        if not isinstance(data, bytes):
            raise StorageError("PRIVATE_ARTIFACT_INVALID")
        try:
            self._client.put_object(
                Bucket=self._config.bucket,
                Key=validated_key,
                Body=data,
                ContentType=content_type,
                IfNoneMatch="*",
            )
            return True
        except Exception as exc:
            code, status = self._provider_error_details(exc)
            if code in {"PreconditionFailed", "ConditionalRequestConflict", "412", "409"} or status in {409, 412}:
                return False
            raise StorageError("BIOCATALYST_R2_CONDITIONAL_CREATE_FAILED") from None


@dataclass(frozen=True)
class MirrorReceipt:
    """Non-secret proof that one immutable private object was read back."""

    object_key: str
    sha256: str
    byte_count: int


def validate_object_key(key: str) -> str:
    """Return a normalized private object key or reject traversal/ambiguity."""

    if not isinstance(key, str) or not key or "\\" in key:
        raise StorageError("UNSAFE_OBJECT_KEY")
    parsed = PurePosixPath(key)
    if parsed.is_absolute() or not parsed.parts or any(part in {"", ".", ".."} for part in parsed.parts):
        raise StorageError("UNSAFE_OBJECT_KEY")
    normalized = parsed.as_posix()
    if normalized != key or len(normalized) > 1024:
        raise StorageError("UNSAFE_OBJECT_KEY")
    return normalized


def content_type_for_path(path: Path) -> str:
    """Use a stable conservative content type for immutable evidence objects."""

    if path.suffix.lower() == ".json":
        return "application/json"
    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or "application/octet-stream"


def mirror_bytes_verified(
    store: BinaryObjectStore,
    *,
    object_key: str,
    payload: bytes,
    content_type: str = "application/octet-stream",
) -> MirrorReceipt:
    """PUT then read back the exact bytes before returning a retention receipt."""

    key = validate_object_key(object_key)
    if not isinstance(payload, bytes):
        raise StorageError("PRIVATE_ARTIFACT_INVALID")
    try:
        existing = store.get_bytes(key)
    except StorageError:
        raise
    except Exception:
        raise StorageError("BIOCATALYST_R2_READBACK_FAILED") from None
    digest = sha256(payload).hexdigest()
    if existing is not None:
        if existing != payload or sha256(existing).hexdigest() != digest:
            raise StorageError("IMMUTABLE_OBJECT_COLLISION")
        return MirrorReceipt(object_key=key, sha256=digest, byte_count=len(payload))
    try:
        created = store.put_if_absent(key, payload, content_type=content_type)
    except StorageError:
        raise
    except Exception:
        raise StorageError("BIOCATALYST_R2_CONDITIONAL_CREATE_FAILED") from None
    if created is False:
        try:
            winner = store.get_bytes(key)
        except StorageError:
            raise
        except Exception:
            raise StorageError("BIOCATALYST_R2_READBACK_FAILED") from None
        if winner is None:
            raise StorageError("BIOCATALYST_R2_CONDITIONAL_CREATE_FAILED")
        if winner != payload or sha256(winner).hexdigest() != digest:
            raise StorageError("IMMUTABLE_OBJECT_COLLISION")
        return MirrorReceipt(object_key=key, sha256=digest, byte_count=len(payload))
    if created is not True:
        raise StorageError("BIOCATALYST_R2_CONDITIONAL_CREATE_FAILED")
    try:
        readback = store.get_bytes(key)
    except StorageError:
        raise
    except Exception:
        raise StorageError("BIOCATALYST_R2_READBACK_FAILED") from None
    if readback is None:
        raise StorageError("BIOCATALYST_R2_READBACK_FAILED")
    if readback != payload or sha256(readback).hexdigest() != digest:
        raise StorageError("BIOCATALYST_R2_READBACK_MISMATCH")
    return MirrorReceipt(object_key=key, sha256=digest, byte_count=len(payload))


def mirror_tree_verified(
    store: BinaryObjectStore,
    *,
    root: Path,
    required_prefix: str = "biocatalyst/",
) -> tuple[MirrorReceipt, ...]:
    """Mirror every regular file below one fresh private staging root.

    The worker allocates a new root for every collector invocation, so this is
    intentionally a complete set—not a modification-time heuristic that could
    forget a reused immutable object.
    """

    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise StorageError("PRIVATE_ARTIFACTS_MISSING")
    try:
        root = root.resolve(strict=True)
    except OSError as exc:
        raise StorageError("PRIVATE_ARTIFACTS_MISSING") from exc
    entries = list(root.rglob("*"))
    # Check the entire tree before the first R2 PUT.  Filtering with is_file()
    # first would follow a symlink and could partially mirror an unsafe stage.
    if any(
        path.is_symlink() or (not path.is_dir() and not path.is_file())
        for path in entries
    ):
        raise StorageError("UNSAFE_PRIVATE_ARTIFACT")
    receipts: list[MirrorReceipt] = []
    files = sorted(path for path in entries if path.is_file())
    if not files:
        raise StorageError("PRIVATE_ARTIFACTS_MISSING")
    for path in files:
        try:
            relative = path.resolve().relative_to(root).as_posix()
        except ValueError as exc:
            raise StorageError("UNSAFE_PRIVATE_ARTIFACT") from exc
        if not relative.startswith(required_prefix):
            raise StorageError("UNSAFE_PRIVATE_ARTIFACT")
        try:
            payload = path.read_bytes()
        except OSError as exc:
            raise StorageError("PRIVATE_ARTIFACT_UNREADABLE") from exc
        receipts.append(
            mirror_bytes_verified(
                store,
                object_key=relative,
                payload=payload,
                content_type=content_type_for_path(path),
            )
        )
    return tuple(receipts)


__all__ = [
    "BinaryObjectStore",
    "DedicatedR2Config",
    "DedicatedR2Store",
    "MirrorReceipt",
    "StorageError",
    "content_type_for_path",
    "mirror_bytes_verified",
    "mirror_tree_verified",
    "validate_object_key",
]
