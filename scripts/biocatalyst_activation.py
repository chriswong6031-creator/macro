#!/usr/bin/env python3
"""Operator-only dark B4E R2 retention check, seal, and heartbeat command.

The command does not collect source data, accrue any ledger, or publish a
pointer.  Its external boundaries are injectable for hermetic tests.  In
normal use the data-plane adapter exposes only HeadBucket/GetObject/conditional
PutObject; heartbeat never invokes the last of those operations.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat
import sys
from typing import Any, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from engine.biocatalyst.activation import (
    ActivationError,
    CloudflareControlPlane,
    ControlPlane,
    ControlPlaneConfig,
    HttpTransport,
    ObjectPlane,
    check_activation,
    heartbeat_activation,
    seal_activation,
    validate_local_activation,
)
from engine.biocatalyst.storage import DedicatedR2Config, DedicatedR2Store, StorageError
from engine.sector_intelligence import canonical_json_bytes


class UrllibTransport:
    """Small GET-only transport used only by the explicit command entrypoint."""

    def request(self, method: str, url: str, *, headers: Mapping[str, str]) -> tuple[int, bytes]:
        if method != "GET":
            raise ValueError("GET only")
        request = Request(url, headers=dict(headers), method="GET")
        try:
            with urlopen(request, timeout=20) as response:  # nosec B310: URL is fixed by core
                return int(response.status), response.read(1024 * 1024 + 1)
        except HTTPError as exc:
            return int(exc.code), b""
        except (URLError, OSError, ValueError):
            raise ActivationError("BIOCATALYST_R2_CONTROL_PLANE_UNAVAILABLE") from None


class DedicatedR2ObjectPlane:
    """Adapt the existing dedicated store without expanding its worker surface."""

    def __init__(self, config: DedicatedR2Config) -> None:
        self._config = config
        self._store = DedicatedR2Store(config)

    def head_bucket(self) -> None:
        try:
            self._store._client.head_bucket(Bucket=self._config.bucket)  # type: ignore[attr-defined]
        except Exception:
            raise ActivationError("BIOCATALYST_R2_DATA_PLANE_INVALID") from None

    def get_bytes(self, key: str) -> bytes | None:
        return self._store.get_bytes(key)

    def put_if_absent(self, key: str, data: bytes, *, content_type: str) -> bool:
        return self._store.put_if_absent(key, data, content_type=content_type)


def _artifact_from_file(path_value: str, code: str) -> Mapping[str, Any]:
    path = Path(path_value)
    file_fd: int | None = None
    try:
        flags = os.O_RDONLY | os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        file_fd = os.open(os.fspath(path), flags)
        metadata_before = os.fstat(file_fd)
        if (
            not stat.S_ISREG(metadata_before.st_mode)
            or metadata_before.st_nlink != 1
            or metadata_before.st_size <= 0
            or metadata_before.st_size > 65536
        ):
            raise ValueError
        raw = os.read(file_fd, 65537)
        metadata_after = os.fstat(file_fd)
        if (
            len(raw) != metadata_before.st_size
            or metadata_after.st_dev != metadata_before.st_dev
            or metadata_after.st_ino != metadata_before.st_ino
            or metadata_after.st_size != metadata_before.st_size
            or metadata_after.st_mtime_ns != metadata_before.st_mtime_ns
            or metadata_after.st_ctime_ns != metadata_before.st_ctime_ns
            or metadata_after.st_mode != metadata_before.st_mode
            or metadata_after.st_uid != metadata_before.st_uid
            or metadata_after.st_gid != metadata_before.st_gid
            or metadata_after.st_nlink != metadata_before.st_nlink
        ):
            raise ValueError
        def reject_constant(_: str) -> None:
            raise ValueError("non-finite JSON")

        def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            decoded: dict[str, Any] = {}
            for key, item in pairs:
                if key in decoded:
                    raise ValueError("duplicate JSON key")
                decoded[key] = item
            return decoded

        decoded = json.loads(
            raw.decode("utf-8"),
            parse_constant=reject_constant,
            object_pairs_hook=reject_duplicates,
        )
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        ValueError,
        RecursionError,
    ):
        raise ActivationError(code) from None
    finally:
        if file_fd is not None:
            os.close(file_fd)
    if not isinstance(decoded, Mapping):
        raise ActivationError(code)
    return decoded


def _gate_path(arguments: argparse.Namespace, values: Mapping[str, str]) -> str:
    return (
        arguments.gate_file
        or values.get("BIOCATALYST_R2_ACTIVATION_GATE_PATH", "")
        or values.get("BIOCATALYST_R2_ACTIVATION_GATE_FILE", "")
    )


def _heartbeat_path(arguments: argparse.Namespace, values: Mapping[str, str]) -> str:
    return arguments.heartbeat_file or values.get("BIOCATALYST_R2_ACTIVATION_HEARTBEAT_PATH", "")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", required=True, choices=("check", "seal", "heartbeat", "validate"))
    parser.add_argument(
        "--gate-file",
        help=(
            "existing immutable activation gate for heartbeat; defaults to "
            "BIOCATALYST_R2_ACTIVATION_GATE_PATH"
        ),
    )
    parser.add_argument(
        "--heartbeat-file",
        help=(
            "existing read-only activation heartbeat for validate; defaults to "
            "BIOCATALYST_R2_ACTIVATION_HEARTBEAT_PATH"
        ),
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    transport: HttpTransport | None = None,
    control_plane: ControlPlane | None = None,
    object_plane: ObjectPlane | None = None,
) -> int:
    """Run one explicit activation operation; injectable planes make it hermetic."""

    values = os.environ if environ is None else environ
    arguments = _parser().parse_args(argv)
    try:
        config = ControlPlaneConfig.from_environment(values)
        if arguments.mode == "validate":
            gate_file = _gate_path(arguments, values)
            heartbeat_file = _heartbeat_path(arguments, values)
            if not gate_file or not heartbeat_file:
                raise ActivationError("BIOCATALYST_R2_ACTIVATION_GATE_INVALID")
            gate = _artifact_from_file(
                gate_file, "BIOCATALYST_R2_ACTIVATION_GATE_INVALID"
            )
            heartbeat = _artifact_from_file(
                heartbeat_file, "BIOCATALYST_R2_ACTIVATION_HEARTBEAT_INVALID"
            )
            validate_local_activation(config, gate, heartbeat)
            result = {
                "activation_id": gate["activation_id"],
                "state": "ready",
                "target_binding_sha256": config.binding_sha256,
            }
        else:
            result = _run_remote_mode(arguments, values, config, transport, control_plane, object_plane)
    except ActivationError as exc:
        print(f"biocatalyst-activation: {exc.code}", file=sys.stderr)
        return 2
    except StorageError:
        print("biocatalyst-activation: BIOCATALYST_R2_DATA_PLANE_INVALID", file=sys.stderr)
        return 2
    print(canonical_json_bytes(result).decode("utf-8"))
    return 0


def _run_remote_mode(
    arguments: argparse.Namespace,
    values: Mapping[str, str],
    config: ControlPlaneConfig,
    transport: HttpTransport | None,
    control_plane: ControlPlane | None,
    object_plane: ObjectPlane | None,
) -> Mapping[str, Any]:
    """Run a mode that intentionally contacts independently injected planes."""

    if arguments.mode == "validate":  # main handles the no-I/O local mode.
        raise ActivationError("BIOCATALYST_R2_ACTIVATION_GATE_INVALID")
    try:
        if control_plane is None:
            control_token = values.get("BIOCATALYST_R2_CONTROL_API_TOKEN", "")
            control_plane = CloudflareControlPlane(
                config,
                control_token,
                transport=transport if transport is not None else UrllibTransport(),
            )
        if object_plane is None:
            data_config = DedicatedR2Config.from_environment(values)
            if (
                data_config.endpoint != config.endpoint
                or data_config.bucket != config.bucket
                or data_config.access_key_id != config.worker_token_id
            ):
                raise ActivationError("BIOCATALYST_R2_CONTROL_CONFIG_INVALID")
            object_plane = DedicatedR2ObjectPlane(data_config)
        if arguments.mode == "check":
            result = check_activation(config, control_plane, object_plane)
        elif arguments.mode == "seal":
            preflight = check_activation(config, control_plane, object_plane)
            result = seal_activation(config, preflight, object_plane)
        else:
            gate_file = _gate_path(arguments, values)
            if not gate_file:
                raise ActivationError("BIOCATALYST_R2_ACTIVATION_GATE_INVALID")
            result = heartbeat_activation(
                config,
                _artifact_from_file(
                    gate_file, "BIOCATALYST_R2_ACTIVATION_GATE_INVALID"
                ),
                control_plane,
                object_plane,
            )
    except StorageError:
        raise ActivationError("BIOCATALYST_R2_DATA_PLANE_INVALID") from None
    return result


if __name__ == "__main__":
    raise SystemExit(main())
