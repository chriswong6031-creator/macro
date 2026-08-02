#!/usr/bin/env python3
"""No-follow provisioning and runtime trust checks for BioCatalyst deploys."""
from __future__ import annotations

import argparse
import os
import stat
import sys
from collections.abc import Sequence


class SafetyError(RuntimeError):
    """A managed path failed its no-follow trust contract."""


_DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW


def _parts(path: str) -> list[str]:
    if not os.path.isabs(path):
        raise SafetyError(f"managed path must be absolute: {path}")
    parts = [part for part in path.split(os.sep) if part]
    if not parts or any(part in {".", ".."} for part in parts):
        raise SafetyError(f"managed path is not canonical: {path}")
    return parts


def _open_dir_at(parent_fd: int, name: str, label: str) -> int:
    try:
        return os.open(name, _DIRECTORY_FLAGS, dir_fd=parent_fd)
    except OSError as exc:
        raise SafetyError(f"{label} is a symlink, missing, or not a directory") from exc


def _require_trusted_ancestor(
    metadata: os.stat_result,
    *,
    label: str,
    trusted_uids: set[int],
) -> None:
    if not stat.S_ISDIR(metadata.st_mode):
        raise SafetyError(f"managed ancestor is not a directory: {label}")
    if metadata.st_uid not in trusted_uids:
        raise SafetyError(f"managed ancestor has unsafe ownership: {label}")
    if stat.S_IMODE(metadata.st_mode) & 0o022:
        raise SafetyError(f"managed ancestor is group/world writable: {label}")


def _open_absolute_parent(path: str, *, trusted_uids: set[int]) -> tuple[int, str]:
    parts = _parts(path)
    current_fd = os.open(os.sep, _DIRECTORY_FLAGS)
    try:
        _require_trusted_ancestor(
            os.fstat(current_fd),
            label=os.sep,
            trusted_uids=trusted_uids,
        )
        for ordinal, component in enumerate(parts[:-1]):
            label = os.sep + os.path.join(*parts[: ordinal + 1])
            next_fd = _open_dir_at(
                current_fd,
                component,
                label,
            )
            _require_trusted_ancestor(
                os.fstat(next_fd),
                label=label,
                trusted_uids=trusted_uids,
            )
            os.close(current_fd)
            current_fd = next_fd
        return current_fd, parts[-1]
    except BaseException:
        os.close(current_fd)
        raise


def _secure_directory_at(
    parent_fd: int,
    name: str,
    *,
    label: str,
    uid: int,
    gid: int,
    mode: int,
) -> int:
    try:
        directory_fd = os.open(name, _DIRECTORY_FLAGS, dir_fd=parent_fd)
    except FileNotFoundError:
        try:
            os.mkdir(name, mode=mode, dir_fd=parent_fd)
        except FileExistsError:
            pass
        directory_fd = _open_dir_at(parent_fd, name, label)
    except OSError as exc:
        raise SafetyError(f"{label} is a symlink or not a directory") from exc

    metadata = os.fstat(directory_fd)
    if not stat.S_ISDIR(metadata.st_mode):
        os.close(directory_fd)
        raise SafetyError(f"{label} is not a directory")
    os.fchown(directory_fd, uid, gid)
    os.fchmod(directory_fd, mode)
    return directory_fd


def _secure_absolute_directory(path: str, *, uid: int, gid: int, mode: int) -> int:
    parent_fd, name = _open_absolute_parent(path, trusted_uids={0, uid})
    try:
        return _secure_directory_at(
            parent_fd,
            name,
            label=path,
            uid=uid,
            gid=gid,
            mode=mode,
        )
    finally:
        os.close(parent_fd)


def _secure_regular_file(path: str, *, uid: int, gid: int, mode: int) -> None:
    parent_fd, name = _open_absolute_parent(path, trusted_uids={0, uid})
    file_fd: int | None = None
    flags = os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
    try:
        try:
            file_fd = os.open(name, flags, dir_fd=parent_fd)
        except FileNotFoundError:
            try:
                file_fd = os.open(
                    name,
                    flags | os.O_CREAT | os.O_EXCL,
                    mode,
                    dir_fd=parent_fd,
                )
            except FileExistsError:
                file_fd = os.open(name, flags, dir_fd=parent_fd)
        except OSError as exc:
            raise SafetyError(f"{path} is a symlink or not a regular file") from exc

        metadata = os.fstat(file_fd)
        if not stat.S_ISREG(metadata.st_mode):
            raise SafetyError(f"{path} is not a regular file")
        if metadata.st_nlink != 1:
            raise SafetyError(f"{path} must not be hard-linked")
        os.fchown(file_fd, uid, gid)
        os.fchmod(file_fd, mode)
    finally:
        if file_fd is not None:
            os.close(file_fd)
        os.close(parent_fd)


def provision_state(args: argparse.Namespace) -> None:
    # The top-level anchor is root-owned and not service-writable. Only its
    # state/public children are owned by the worker identity.
    root_fd = _secure_absolute_directory(
        args.state_root,
        uid=args.root_uid,
        gid=args.service_gid,
        mode=0o750,
    )
    state_fd: int | None = None
    public_fd: int | None = None
    try:
        state_fd = _secure_directory_at(
            root_fd,
            "state",
            label=f"{args.state_root}/state",
            uid=args.service_uid,
            gid=args.service_gid,
            mode=0o700,
        )
        public_fd = _secure_directory_at(
            root_fd,
            "public",
            label=f"{args.state_root}/public",
            uid=args.service_uid,
            gid=args.service_gid,
            mode=0o700,
        )
        for child in ("staging", "committed", "dead-letter"):
            child_fd = _secure_directory_at(
                state_fd,
                child,
                label=f"{args.state_root}/state/{child}",
                uid=args.service_uid,
                gid=args.service_gid,
                mode=0o700,
            )
            os.close(child_fd)
    finally:
        if public_fd is not None:
            os.close(public_fd)
        if state_fd is not None:
            os.close(state_fd)
        os.close(root_fd)

    _secure_regular_file(
        args.env_file,
        uid=args.env_uid,
        gid=args.env_gid,
        mode=0o600,
    )


def provision_runtime_root(args: argparse.Namespace) -> None:
    root_fd = _secure_absolute_directory(
        args.runtime_root,
        uid=args.owner_uid,
        gid=args.service_gid,
        mode=0o750,
    )
    try:
        runtimes_fd = _secure_directory_at(
            root_fd,
            "runtimes",
            label=f"{args.runtime_root}/runtimes",
            uid=args.owner_uid,
            gid=args.service_gid,
            mode=0o750,
        )
        os.close(runtimes_fd)
    finally:
        os.close(root_fd)


def _require_safe_owned(
    metadata: os.stat_result,
    *,
    label: str,
    uid: int,
    gid: int,
    directory: bool | None = None,
) -> None:
    if directory is True and not stat.S_ISDIR(metadata.st_mode):
        raise SafetyError(f"{label} is not a directory")
    if directory is False and not stat.S_ISREG(metadata.st_mode):
        raise SafetyError(f"{label} is not a regular file")
    if metadata.st_uid != uid or metadata.st_gid != gid:
        raise SafetyError(f"{label} has unsafe ownership")
    if stat.S_IMODE(metadata.st_mode) & 0o022:
        raise SafetyError(f"{label} is group/world writable")
    if directory is True and stat.S_IMODE(metadata.st_mode) & 0o050 != 0o050:
        raise SafetyError(f"{label} is not service-readable/traversable")
    if directory is False and not stat.S_IMODE(metadata.st_mode) & 0o040:
        raise SafetyError(f"{label} is not service-readable")


def _walk_runtime_tree(
    directory_fd: int,
    *,
    relative: str,
    uid: int,
    gid: int,
) -> None:
    with os.scandir(directory_fd) as entries:
        for entry in entries:
            label = f"{relative}/{entry.name}" if relative else entry.name
            metadata = entry.stat(follow_symlinks=False)
            if metadata.st_uid != uid or metadata.st_gid != gid:
                raise SafetyError(f"runtime entry has unsafe ownership: {label}")
            if stat.S_ISLNK(metadata.st_mode):
                target = os.readlink(entry.name, dir_fd=directory_fd)
                if os.path.isabs(target):
                    raise SafetyError(f"runtime symlink escapes tree: {label}")
                resolved = os.path.normpath(os.path.join(os.path.dirname(label), target))
                if resolved == os.pardir or resolved.startswith(os.pardir + os.sep):
                    raise SafetyError(f"runtime symlink escapes tree: {label}")
                continue
            if stat.S_IMODE(metadata.st_mode) & 0o022:
                raise SafetyError(f"runtime entry is group/world writable: {label}")
            if stat.S_ISDIR(metadata.st_mode):
                if stat.S_IMODE(metadata.st_mode) & 0o050 != 0o050:
                    raise SafetyError(f"runtime directory is not service-traversable: {label}")
                child_fd = _open_dir_at(directory_fd, entry.name, label)
                try:
                    _walk_runtime_tree(child_fd, relative=label, uid=uid, gid=gid)
                finally:
                    os.close(child_fd)
            elif stat.S_ISREG(metadata.st_mode):
                if not stat.S_IMODE(metadata.st_mode) & 0o040:
                    raise SafetyError(f"runtime file is not service-readable: {label}")
            else:
                raise SafetyError(f"runtime entry is not a regular file or directory: {label}")


def verify_runtime(args: argparse.Namespace) -> None:
    runtime_root = os.path.normpath(args.runtime_root)
    runtime_path = os.path.normpath(args.runtime_path)
    runtimes_root = os.path.join(runtime_root, "runtimes")
    if os.path.dirname(runtime_path) != runtimes_root:
        raise SafetyError("runtime target must be a direct child of the runtimes root")

    root_fd = _open_existing_absolute_directory(runtime_root, trusted_uid=args.owner_uid)
    runtimes_fd: int | None = None
    runtime_fd: int | None = None
    try:
        _require_safe_owned(
            os.fstat(root_fd),
            label=runtime_root,
            uid=args.owner_uid,
            gid=args.service_gid,
            directory=True,
        )
        runtimes_fd = _open_dir_at(root_fd, "runtimes", runtimes_root)
        _require_safe_owned(
            os.fstat(runtimes_fd),
            label=runtimes_root,
            uid=args.owner_uid,
            gid=args.service_gid,
            directory=True,
        )
        runtime_fd = _open_dir_at(runtimes_fd, os.path.basename(runtime_path), runtime_path)
        _require_safe_owned(
            os.fstat(runtime_fd),
            label=runtime_path,
            uid=args.owner_uid,
            gid=args.service_gid,
            directory=True,
        )

        if args.current_link:
            if os.path.dirname(os.path.normpath(args.current_link)) != runtime_root:
                raise SafetyError("current pointer must live directly under runtime root")
            link_name = os.path.basename(args.current_link)
            link_metadata = os.stat(link_name, dir_fd=root_fd, follow_symlinks=False)
            if not stat.S_ISLNK(link_metadata.st_mode):
                raise SafetyError("current runtime pointer is not a symlink")
            if link_metadata.st_uid != args.owner_uid or link_metadata.st_gid != args.service_gid:
                raise SafetyError("current runtime pointer has unsafe ownership")
            link_target = os.readlink(link_name, dir_fd=root_fd)
            selected = (
                os.path.normpath(link_target)
                if os.path.isabs(link_target)
                else os.path.normpath(os.path.join(runtime_root, link_target))
            )
            if selected != runtime_path:
                raise SafetyError("current runtime pointer target changed during verification")

        stamp_metadata = os.stat(
            ".requirements.sha256",
            dir_fd=runtime_fd,
            follow_symlinks=False,
        )
        _require_safe_owned(
            stamp_metadata,
            label=f"{runtime_path}/.requirements.sha256",
            uid=args.owner_uid,
            gid=args.service_gid,
            directory=False,
        )
        bin_fd = _open_dir_at(runtime_fd, "bin", f"{runtime_path}/bin")
        try:
            python_metadata = os.stat("python", dir_fd=bin_fd, follow_symlinks=False)
            _require_safe_owned(
                python_metadata,
                label=f"{runtime_path}/bin/python",
                uid=args.owner_uid,
                gid=args.service_gid,
                directory=False,
            )
            if stat.S_IMODE(python_metadata.st_mode) & 0o050 != 0o050:
                raise SafetyError("runtime Python is not service-readable/executable")
        finally:
            os.close(bin_fd)

        _walk_runtime_tree(runtime_fd, relative="", uid=args.owner_uid, gid=args.service_gid)
    finally:
        if runtime_fd is not None:
            os.close(runtime_fd)
        if runtimes_fd is not None:
            os.close(runtimes_fd)
        os.close(root_fd)


def _open_existing_absolute_directory(path: str, *, trusted_uid: int) -> int:
    parent_fd, name = _open_absolute_parent(path, trusted_uids={0, trusted_uid})
    try:
        return _open_dir_at(parent_fd, name, path)
    finally:
        os.close(parent_fd)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    state_parser = subparsers.add_parser("provision-state")
    state_parser.add_argument("--state-root", required=True)
    state_parser.add_argument("--env-file", required=True)
    state_parser.add_argument("--service-uid", type=int, required=True)
    state_parser.add_argument("--service-gid", type=int, required=True)
    state_parser.add_argument("--root-uid", type=int, required=True)
    state_parser.add_argument("--env-uid", type=int, required=True)
    state_parser.add_argument("--env-gid", type=int, required=True)
    state_parser.set_defaults(handler=provision_state)

    runtime_parser = subparsers.add_parser("provision-runtime")
    runtime_parser.add_argument("--runtime-root", required=True)
    runtime_parser.add_argument("--owner-uid", type=int, required=True)
    runtime_parser.add_argument("--service-gid", type=int, required=True)
    runtime_parser.set_defaults(handler=provision_runtime_root)

    verify_parser = subparsers.add_parser("verify-runtime")
    verify_parser.add_argument("--runtime-root", required=True)
    verify_parser.add_argument("--runtime-path", required=True)
    verify_parser.add_argument("--current-link")
    verify_parser.add_argument("--owner-uid", type=int, required=True)
    verify_parser.add_argument("--service-gid", type=int, required=True)
    verify_parser.set_defaults(handler=verify_runtime)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        args.handler(args)
    except (OSError, SafetyError) as exc:
        print(f"biocatalyst-secure-paths: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
