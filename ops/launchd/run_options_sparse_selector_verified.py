#!/usr/bin/env python3
"""Sealed runtime carrier and explicit installer for the sparse selector.

This module deliberately does *not* install or load a launchd job, create a
selector state root, import a selector producer in this process, or advance a
ledger.  Its two operational surfaces are explicit: a disposable-root proof
and a persistent-runtime installation into one fixed private root.  A normal
invocation is permanently refused before it probes the host or performs any
external I/O.

The carrier is stdlib-only so the proof boundary itself does not depend on the
mutable conda environment it is measuring.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import socket
import stat
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any


# This is deliberately a source constant.  No environment variable, CLI flag,
# receipt, host fact, or proof result may turn it on.  Keep this module free of
# a selector import: even an import has no business occurring on an unarmed
# ordinary invocation.
SELECTOR_RUNTIME_ARMED = False

EXPECTED_HOST_MODEL = "Mac13,1"
EXPECTED_MACHINE = "arm64"
THETA_HOST = "127.0.0.1"
THETA_PORT = 25503
EXPECTED_RUNTIME_SOURCE = Path("/Users/chriswong/miniconda3/envs/plane")
CANONICAL_ORIGIN_URL = "git@github.com:mastermindx-market-intelligence/macro.git"
CANONICAL_ORIGIN_REF = "refs/remotes/origin/main"
DEPLOY_KEY = Path("/Users/chriswong/.ssh/macro_dashboard_deploy")
GIT_SSH_COMMAND = (
    f"/usr/bin/ssh -i {DEPLOY_KEY} -o IdentitiesOnly=yes -o BatchMode=yes"
)
RUNTIME_PYTHON_RELATIVE = Path("bin/python3.12")
RUNTIME_STDLIB_RELATIVE = Path("lib/python3.12")
RUNTIME_SITE_PACKAGES_RELATIVE = RUNTIME_STDLIB_RELATIVE / "site-packages"
RUNTIME_LIBPYTHON_RELATIVE = Path("lib/libpython3.12.dylib")
RUNTIME_TIMEZONE_RELATIVE = Path("share/zoneinfo")
RUNTIME_REQUIRED_IMPORTS = (
    "attr",
    "attrs",
    "dateutil",
    "idna",
    "jsonschema",
    "jsonschema_specifications",
    "numpy",
    "pandas",
    "pyarrow",
    "pytz",
    "referencing",
    "rpds",
    "six",
    "typing_extensions",
)
RUNTIME_DEPENDENCY_PATHS = (
    RUNTIME_SITE_PACKAGES_RELATIVE / "attr",
    RUNTIME_SITE_PACKAGES_RELATIVE / "attrs",
    RUNTIME_SITE_PACKAGES_RELATIVE / "dateutil",
    RUNTIME_SITE_PACKAGES_RELATIVE / "idna",
    RUNTIME_SITE_PACKAGES_RELATIVE / "jsonschema",
    RUNTIME_SITE_PACKAGES_RELATIVE / "jsonschema_specifications",
    RUNTIME_SITE_PACKAGES_RELATIVE / "numpy",
    RUNTIME_SITE_PACKAGES_RELATIVE / "pandas",
    RUNTIME_SITE_PACKAGES_RELATIVE / "pyarrow",
    RUNTIME_SITE_PACKAGES_RELATIVE / "pytz",
    RUNTIME_SITE_PACKAGES_RELATIVE / "referencing",
    RUNTIME_SITE_PACKAGES_RELATIVE / "rpds",
    RUNTIME_SITE_PACKAGES_RELATIVE / "six.py",
    RUNTIME_SITE_PACKAGES_RELATIVE / "typing_extensions.py",
)
RUNTIME_AUXILIARY_PATHS = (
    RUNTIME_SITE_PACKAGES_RELATIVE / "numpy.libs",
    RUNTIME_SITE_PACKAGES_RELATIVE / "pandas.libs",
    RUNTIME_SITE_PACKAGES_RELATIVE / "pyarrow.libs",
)
DISPOSABLE_MARKER = ".options_sparse_selector_disposable_root"
DISPOSABLE_MARKER_BODY = b"options.sparse_selector.disposable_root/v1\n"
PERSISTENT_RUNTIME_ROOT = Path(
    "/Users/chriswong/.mastermind_private/options_sparse_selector_runtime_v1"
)
PERSISTENT_REPO_ROOT = Path("/Users/chriswong/options-sparse-selector-ops-wt")
PERSISTENT_MARKER = ".options_sparse_selector_persistent_runtime_root"
PERSISTENT_MARKER_BODY = b"options.sparse_selector.persistent_runtime_root/v1\n"
MANIFEST_NAME = "runtime_closure.json"
RUNTIME_DIRECTORY = "runtime"
MANIFEST_SCHEMA = "options.sparse_selector_runtime_carrier/v2"
REPO_IMPORT_SOURCE_PATHS = (
    Path("engine/options_sparse_selector.py"),
    Path("engine/private_auth_dict.py"),
    Path("scripts/run_options_sparse_selector.py"),
    Path("ops/launchd/run_options_sparse_selector_verified.py"),
)
MAX_FILE_BYTES = 512 * 1024 * 1024
MAX_REPO_SOURCE_BYTES = 16 * 1024 * 1024
MAX_FILES = 100_000
MAX_TREE_BYTES = 8 * 1024 * 1024 * 1024
MIN_PERSISTENT_FREE_BYTES = 10 * 1024 * 1024 * 1024


class BootstrapError(RuntimeError):
    """The disposable proof cannot establish a sealed carrier."""


@dataclass(frozen=True)
class NativeRecord:
    """The narrow Mach-O facts needed for relocation/attestation."""

    install_id: str | None
    dependencies: tuple[str, ...]
    rpaths: tuple[str, ...] = ()


def _canonical_json(value: object) -> bytes:
    try:
        return json.dumps(
            value, allow_nan=False, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise BootstrapError("carrier receipt is not canonical JSON") from exc


def _identity(value: os.stat_result) -> tuple[int, int, int, int, int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_nlink,
        value.st_uid,
        value.st_gid,
        value.st_size,
        value.st_mtime_ns,
    )


def _lstat_regular(
    path: Path,
    *,
    label: str,
    owner_uid: int | None = None,
    require_single_link: bool = True,
) -> os.stat_result:
    try:
        metadata = os.lstat(path)
    except OSError as exc:
        raise BootstrapError(f"{label} is unavailable") from exc
    if (
        not stat.S_ISREG(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or (require_single_link and metadata.st_nlink != 1)
        or metadata.st_size > MAX_FILE_BYTES
        or stat.S_IMODE(metadata.st_mode) & 0o022
        or (owner_uid is not None and metadata.st_uid != owner_uid)
    ):
        raise BootstrapError(f"{label} metadata is unsafe")
    return metadata


def _lstat_directory(path: Path, *, label: str, owner_uid: int | None = None) -> os.stat_result:
    try:
        metadata = os.lstat(path)
    except OSError as exc:
        raise BootstrapError(f"{label} is unavailable") from exc
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) & 0o022
        or (owner_uid is not None and metadata.st_uid != owner_uid)
    ):
        raise BootstrapError(f"{label} metadata is unsafe")
    return metadata


def _read_exact(
    path: Path,
    *,
    label: str,
    maximum: int = MAX_FILE_BYTES,
    require_single_link: bool = True,
) -> bytes:
    before = _lstat_regular(
        path, label=label, require_single_link=require_single_link
    )
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
    except OSError as exc:
        raise BootstrapError(f"{label} cannot be opened safely") from exc
    try:
        opened = os.fstat(descriptor)
        if _identity(before) != _identity(opened):
            raise BootstrapError(f"{label} changed before copy")
        body = bytearray()
        while len(body) <= maximum:
            chunk = os.read(descriptor, min(1024 * 1024, maximum + 1 - len(body)))
            if not chunk:
                break
            body.extend(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    try:
        current = os.lstat(path)
    except OSError as exc:
        raise BootstrapError(f"{label} changed during copy") from exc
    if (
        len(body) > maximum
        or _identity(before) != _identity(opened)
        or _identity(opened) != _identity(after)
        or _identity(after) != _identity(current)
    ):
        raise BootstrapError(f"{label} changed during copy")
    return bytes(body)


def _safe_relative(relative: Path, *, label: str) -> Path:
    if (
        relative.is_absolute()
        or relative == Path(".")
        or not relative.parts
        or ".." in relative.parts
    ):
        raise BootstrapError(f"{label} is not a safe relative path")
    return relative


def _contains(parent: Path, child: Path) -> bool:
    try:
        child.relative_to(parent)
    except ValueError:
        return False
    return True


def _walk_regular_tree(
    root: Path, *, label: str, require_single_links: bool = True
) -> list[Path]:
    """Return only regular files; every directory and symlink is attested."""

    _lstat_directory(root, label=label)
    discovered: list[Path] = []
    pending = [root]
    while pending:
        current = pending.pop()
        try:
            children = sorted(current.iterdir(), key=lambda item: item.name)
        except OSError as exc:
            raise BootstrapError(f"{label} cannot be listed") from exc
        for child in children:
            relative = child.relative_to(root)
            metadata = os.lstat(child)
            if stat.S_ISLNK(metadata.st_mode):
                raise BootstrapError(f"{label} contains a symlink: {relative}")
            if stat.S_ISDIR(metadata.st_mode):
                _lstat_directory(child, label=f"{label}/{relative}")
                pending.append(child)
            elif stat.S_ISREG(metadata.st_mode):
                _lstat_regular(
                    child,
                    label=f"{label}/{relative}",
                    require_single_link=require_single_links,
                )
                discovered.append(child)
            else:
                raise BootstrapError(f"{label} contains a non-regular entry: {relative}")
            if len(discovered) > MAX_FILES:
                raise BootstrapError("runtime closure exceeds its file cap")
    return discovered


def _copy_file(source: Path, destination: Path) -> None:
    # Conda deliberately deduplicates immutable package payloads with hardlinks.
    # The source inode may therefore have multiple names, but its full identity
    # is fenced before/during/after the read and the sealed output is always a
    # newly created single-link file.
    source_metadata = _lstat_regular(
        source, label=f"runtime source {source}", require_single_link=False
    )
    body = _read_exact(
        source, label=f"runtime source {source}", require_single_link=False
    )
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        descriptor = os.open(
            destination,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
    except OSError as exc:
        raise BootstrapError(f"runtime target {destination} cannot be created") from exc
    try:
        view = memoryview(body)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise BootstrapError("runtime snapshot copy was short")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    if stat.S_IMODE(source_metadata.st_mode) & 0o111:
        destination.chmod(0o700)


def _write_exclusive(path: Path, body: bytes, *, mode: int = 0o600) -> None:
    if len(body) > MAX_FILE_BYTES:
        raise BootstrapError("carrier output exceeds its file cap")
    try:
        descriptor = os.open(
            path,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
            mode,
        )
    except OSError as exc:
        raise BootstrapError(f"carrier output {path} cannot be created") from exc
    try:
        view = memoryview(body)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise BootstrapError("carrier output write was short")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    try:
        directory = os.open(
            path.parent,
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0),
        )
    except OSError as exc:
        raise BootstrapError("carrier output directory cannot be opened safely") from exc
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def _copy_tree(source_root: Path, target_root: Path, *, exclude: frozenset[str] = frozenset()) -> None:
    files = _walk_regular_tree(
        source_root,
        label=f"runtime source {source_root}",
        require_single_links=False,
    )
    target_root.mkdir(mode=0o700, parents=True, exist_ok=False)
    for source in files:
        relative = source.relative_to(source_root)
        if relative.parts and relative.parts[0] in exclude:
            continue
        _copy_file(source, target_root / relative)


def _copy_component(source: Path, runtime_root: Path, relative: Path, *, exclude: frozenset[str] = frozenset()) -> None:
    _safe_relative(relative, label="runtime component")
    target = runtime_root / relative
    try:
        metadata = os.lstat(source)
    except OSError as exc:
        raise BootstrapError(f"runtime source component {relative} is unavailable") from exc
    if stat.S_ISDIR(metadata.st_mode):
        _copy_tree(source, target, exclude=exclude)
    elif stat.S_ISREG(metadata.st_mode):
        _lstat_regular(
            source,
            label=f"runtime source {relative}",
            require_single_link=False,
        )
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        _copy_file(source, target)
    else:
        raise BootstrapError(f"runtime source component {relative} is unsafe")


def _copy_native_alias(
    source: Path, runtime_root: Path, relative: Path, *, source_root: Path
) -> None:
    """Copy one named native dependency without reproducing a source symlink.

    Conda uses same-directory dylib aliases such as ``libz.1.dylib ->
    libz.1.3.2.dylib``.  The alias itself is load-bearing, so retain its name
    but copy the resolved regular bytes into a fresh single-link target.
    Multi-hop, absolute, parent-relative, or cross-directory aliases fail.
    """

    try:
        before = os.lstat(source)
    except OSError as exc:
        raise BootstrapError(f"native source alias {relative} is unavailable") from exc
    if not stat.S_ISLNK(before.st_mode):
        _copy_component(source, runtime_root, relative)
        return
    try:
        raw_target = os.readlink(source)
    except OSError as exc:
        raise BootstrapError(f"native source alias {relative} cannot be read") from exc
    target_name = Path(raw_target)
    if (
        target_name.is_absolute()
        or len(target_name.parts) != 1
        or target_name.name in {"", ".", ".."}
    ):
        raise BootstrapError("native source alias escapes its reviewed directory")
    resolved = source.parent / target_name
    try:
        resolved.relative_to(source_root)
    except ValueError as exc:
        raise BootstrapError("native source alias escapes the reviewed runtime") from exc
    _lstat_regular(
        resolved,
        label=f"native source alias target {relative}",
        require_single_link=False,
    )
    _copy_file(resolved, runtime_root / relative)
    try:
        after = os.lstat(source)
        current_target = os.readlink(source)
    except OSError as exc:
        raise BootstrapError("native source alias changed during copy") from exc
    if _identity(before) != _identity(after) or raw_target != current_target:
        raise BootstrapError("native source alias changed during copy")


def _selected_source_components(source_root: Path) -> tuple[tuple[Path, frozenset[str]], ...]:
    if source_root != EXPECTED_RUNTIME_SOURCE:
        raise BootstrapError("runtime source is not the reviewed plane environment")
    _lstat_directory(source_root, label="runtime source")
    return (
        (RUNTIME_PYTHON_RELATIVE, frozenset()),
        (RUNTIME_LIBPYTHON_RELATIVE, frozenset()),
        (RUNTIME_TIMEZONE_RELATIVE, frozenset({"posix", "right"})),
        (RUNTIME_STDLIB_RELATIVE, frozenset({"site-packages", "__pycache__"})),
        *((path, frozenset({"__pycache__"})) for path in RUNTIME_DEPENDENCY_PATHS),
        *((path, frozenset({"__pycache__"})) for path in RUNTIME_AUXILIARY_PATHS if (source_root / path).exists()),
    )


def _native_candidates(runtime_root: Path) -> list[Path]:
    """Inventory only the sealed closure; never scan arbitrary conda ``lib/``."""

    candidate_roots = [
        runtime_root / RUNTIME_PYTHON_RELATIVE,
        # ``lib/`` contains only libpython plus exact dependency edges learned
        # from a previously selected native object.  It is never an inventory of
        # the source conda prefix.
        runtime_root / "lib",
        runtime_root / RUNTIME_STDLIB_RELATIVE / "lib-dynload",
        *(runtime_root / path for path in RUNTIME_DEPENDENCY_PATHS),
        *(runtime_root / path for path in RUNTIME_AUXILIARY_PATHS if (runtime_root / path).exists()),
    ]
    files: list[Path] = []
    for root in candidate_roots:
        if root.is_file() and (
            root == runtime_root / RUNTIME_PYTHON_RELATIVE
            or root.suffix in {".dylib", ".so"}
        ):
            files.append(root)
        elif root.is_dir():
            for path in _walk_regular_tree(root, label="sealed native component"):
                if path.suffix in {".dylib", ".so"}:
                    files.append(path)
    return sorted(set(files), key=lambda path: path.as_posix())


def _parse_otool_l(output: str) -> tuple[str, ...]:
    names: list[str] = []
    for line in output.splitlines()[1:]:
        text = line.strip()
        if not text:
            continue
        name = text.split(" (compatibility version", 1)[0].strip()
        if not name:
            raise BootstrapError("Mach-O dependency line is malformed")
        names.append(name)
    return tuple(names)


def _parse_otool_rpaths(output: str) -> tuple[str, ...]:
    """Return every LC_RPATH path from deterministic ``otool -l`` output."""

    lines = output.splitlines()
    rpaths: list[str] = []
    for index, line in enumerate(lines):
        if line.strip() != "cmd LC_RPATH":
            continue
        for candidate in lines[index + 1 : index + 6]:
            text = candidate.strip()
            if not text.startswith("path "):
                continue
            value = text.removeprefix("path ").split(" (offset ", 1)[0].strip()
            if not value:
                raise BootstrapError("Mach-O LC_RPATH is malformed")
            rpaths.append(value)
            break
        else:
            raise BootstrapError("Mach-O LC_RPATH has no path")
    return tuple(rpaths)


def _native_record(path: Path) -> NativeRecord:
    def run(*arguments: str) -> str:
        try:
            result = subprocess.run(
                ["/usr/bin/otool", *arguments, str(path)],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
                env={"LANG": "C", "LC_ALL": "C", "PATH": "/usr/bin:/bin"},
            )
        except OSError as exc:
            raise BootstrapError("otool is unavailable for native attestation") from exc
        if result.returncode != 0:
            raise BootstrapError("otool rejected a sealed native object")
        return result.stdout

    ids = run("-D")
    id_lines = [line.strip() for line in ids.splitlines()[1:] if line.strip()]
    if len(id_lines) > 1:
        raise BootstrapError("Mach-O has more than one install ID")
    install_id = id_lines[0] if id_lines else None
    dependencies = _parse_otool_l(run("-L"))
    if install_id is not None:
        # ``otool -L`` reports a dylib's LC_ID_DYLIB as its first listed name;
        # it is identity metadata, not a load edge.
        dependencies = tuple(name for name in dependencies if name != install_id)
    return NativeRecord(
        install_id=install_id,
        dependencies=dependencies,
        rpaths=_parse_otool_rpaths(run("-l")),
    )


def _system_native_name(name: str) -> bool:
    return name.startswith("/usr/lib/") or name.startswith("/System/Library/")


def _loader_name(owner: Path, target: Path) -> str:
    relative = os.path.relpath(target, owner.parent).replace(os.sep, "/")
    if relative == ".":
        return "@loader_path"
    if relative == ".." or relative.startswith("../"):
        return "@loader_path/" + relative
    return "@loader_path/" + relative


def _resolve_loader_name(owner: Path, name: str, runtime_root: Path) -> Path | None:
    if name == "@loader_path":
        target = owner.parent.resolve(strict=False)
    elif name.startswith("@loader_path/"):
        target = (
            owner.parent / name.removeprefix("@loader_path/")
        ).resolve(strict=False)
    else:
        return None
    try:
        target.relative_to(runtime_root.resolve(strict=False))
    except ValueError as exc:
        raise BootstrapError("native dependency escapes sealed runtime") from exc
    return target


def _runtime_rpath_base(
    owner: Path,
    rpath: str,
    runtime_root: Path,
    source_prefix: Path,
) -> Path | None:
    if rpath == "@loader_path" or rpath.startswith("@loader_path/"):
        return _resolve_loader_name(owner, rpath, runtime_root)
    source_text = str(source_prefix)
    if rpath == source_text or rpath.startswith(source_text + "/"):
        suffix = Path(rpath).relative_to(source_prefix)
        target = (runtime_root / suffix).resolve(strict=False)
        try:
            target.relative_to(runtime_root.resolve(strict=False))
        except ValueError as exc:
            raise BootstrapError("native rpath escapes sealed runtime") from exc
        return target
    if rpath in {"/usr/lib", "/System/Library"} or _system_native_name(rpath):
        return None
    if rpath.startswith("/"):
        raise BootstrapError("native rpath is an unapproved external path")
    raise BootstrapError("native rpath uses an unapproved loader token")


def _resolve_rpath_dependency(
    owner: Path,
    dependency: str,
    rpaths: Sequence[str],
    runtime_root: Path,
    source_prefix: Path,
) -> Path | None:
    if not dependency.startswith("@rpath/"):
        return None
    suffix = _safe_relative(
        Path(dependency.removeprefix("@rpath/")), label="native @rpath dependency"
    )
    for rpath in rpaths:
        base = _runtime_rpath_base(
            owner.resolve(strict=False), rpath, runtime_root, source_prefix
        )
        if base is None:
            continue
        candidate = (base / suffix).resolve(strict=False)
        try:
            candidate.relative_to(runtime_root.resolve(strict=False))
        except ValueError as exc:
            raise BootstrapError("native dependency escapes sealed runtime") from exc
        # dyld uses LC_RPATH order.  Select the first declared location that is
        # already sealed or exists at the corresponding reviewed source path.
        source_candidate = source_prefix / candidate.relative_to(
            runtime_root.resolve(strict=False)
        )
        if candidate.exists() or source_candidate.exists():
            return candidate
    return None


def _native_relocation_plan(
    runtime_root: Path,
    records: Mapping[Path, NativeRecord],
    *,
    source_prefix: Path = EXPECTED_RUNTIME_SOURCE,
) -> dict[Path, tuple[tuple[str, str, str], ...]]:
    """Map every non-system native ID, edge, and rpath into the sealed tree.

    Bare install IDs are safe as *identity metadata*: they are never treated as
    absolute bindings or passed to ``install_name_tool -change``.  A bare
    dependency remains ambiguous and fails closed.
    """

    files = {path.resolve(strict=False) for path in records}
    plan: dict[Path, tuple[tuple[str, str, str], ...]] = {}
    for owner, record in records.items():
        changes: list[tuple[str, str, str]] = []
        owner_real = owner.resolve(strict=False)
        if record.install_id is not None:
            install_id = record.install_id
            if install_id.startswith("/") and not install_id.startswith(str(source_prefix) + "/"):
                raise BootstrapError("native install ID is an unapproved external path")
            if install_id.startswith("@loader_path/"):
                _resolve_loader_name(owner_real, install_id, runtime_root)
            elif install_id.startswith("@") and not install_id.startswith("@rpath/"):
                raise BootstrapError("native install ID uses an unapproved loader token")
            # A bare install ID is identity metadata, not a dependency.  Normalize
            # it nevertheless so no dyld search-path behavior is retained.
            desired_id = _loader_name(owner_real, owner_real)
            if install_id != desired_id:
                changes.append(("id", install_id, desired_id))
        for rpath in record.rpaths:
            target = _runtime_rpath_base(
                owner_real, rpath, runtime_root, source_prefix
            )
            if target is None:
                continue
            target_real = target.resolve(strict=False)
            try:
                target_real.relative_to(runtime_root.resolve(strict=False))
            except ValueError as exc:
                raise BootstrapError("native rpath escapes sealed runtime") from exc
            if not target.exists():
                raise BootstrapError("native rpath target is not in the sealed closure")
            rewritten = _loader_name(owner_real, target_real)
            if rpath != rewritten:
                changes.append(("rpath", rpath, rewritten))
        for dependency in record.dependencies:
            if _system_native_name(dependency):
                continue
            target: Path | None = None
            if dependency.startswith("@loader_path/"):
                target = _resolve_loader_name(owner_real, dependency, runtime_root)
            elif dependency == "@loader_path":
                target = _resolve_loader_name(owner_real, dependency, runtime_root)
            elif dependency.startswith("@rpath/"):
                target = _resolve_rpath_dependency(
                    owner_real,
                    dependency,
                    record.rpaths,
                    runtime_root,
                    source_prefix,
                )
            elif dependency.startswith(str(source_prefix) + "/"):
                suffix = Path(dependency).relative_to(source_prefix)
                candidate = runtime_root / suffix
                if candidate.resolve(strict=False) in files:
                    target = candidate
            elif dependency.startswith("/"):
                raise BootstrapError("native dependency is an unapproved external path")
            else:
                raise BootstrapError("native dependency has an unapproved bare binding")
            if target is None or target.resolve(strict=False) not in files:
                raise BootstrapError("native dependency is not in the sealed closure")
            rewritten = _loader_name(owner_real, target.resolve(strict=False))
            if dependency != rewritten:
                changes.append(("change", dependency, rewritten))
        plan[owner] = tuple(changes)
    return plan


def _apply_native_relocations(plan: Mapping[Path, Sequence[tuple[str, str, str]]]) -> None:
    for owner, changes in plan.items():
        for action, old, new in changes:
            if action == "id":
                command = ["/usr/bin/install_name_tool", "-id", new, str(owner)]
            elif action == "rpath":
                command = ["/usr/bin/install_name_tool", "-rpath", old, new, str(owner)]
            elif action == "change":
                command = ["/usr/bin/install_name_tool", "-change", old, new, str(owner)]
            else:
                raise BootstrapError("native relocation action is invalid")
            try:
                subprocess.run(
                    command,
                    check=True,
                    capture_output=True,
                    timeout=20,
                    env={"LANG": "C", "LC_ALL": "C", "PATH": "/usr/bin:/bin"},
                )
            except (OSError, subprocess.SubprocessError) as exc:
                raise BootstrapError("native relocation failed") from exc


def _seal_native_signatures(paths: Sequence[Path]) -> None:
    """Ad-hoc sign relocated Mach-O bytes, then strictly verify every object."""

    ordered = sorted(set(paths), key=lambda path: path.as_posix())
    environment = {"LANG": "C", "LC_ALL": "C", "PATH": "/usr/bin:/bin"}
    for path in ordered:
        try:
            subprocess.run(
                [
                    "/usr/bin/codesign",
                    "--force",
                    "--sign",
                    "-",
                    "--timestamp=none",
                    str(path),
                ],
                check=True,
                capture_output=True,
                timeout=30,
                env=environment,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise BootstrapError("sealed native object cannot be ad-hoc signed") from exc
    for path in ordered:
        try:
            subprocess.run(
                ["/usr/bin/codesign", "--verify", "--strict", str(path)],
                check=True,
                capture_output=True,
                timeout=20,
                env=environment,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise BootstrapError("sealed native signature verification failed") from exc


def _native_dyld_acceptance(
    *, python: Path, runtime_root: Path, natives: Sequence[Path]
) -> None:
    """Make dyld load every sealed library/bundle under the copied interpreter."""

    runtime_root = runtime_root.resolve(strict=True)
    relative = [
        path.resolve(strict=True).relative_to(runtime_root).as_posix()
        for path in sorted(set(natives), key=lambda item: item.as_posix())
        if path.resolve(strict=True) != python.resolve(strict=True)
    ]
    script = (
        "import ctypes\nimport json\nimport os\nimport pathlib\n"
        f"runtime = pathlib.Path({str(runtime_root)!r}).resolve()\n"
        f"relative = json.loads({json.dumps(relative)!r})\n"
        "for item in relative:\n"
        "    path = (runtime / item).resolve()\n"
        "    path.relative_to(runtime)\n"
        "    ctypes.CDLL(str(path), mode=os.RTLD_LOCAL | os.RTLD_LAZY)\n"
    )
    try:
        result = subprocess.run(
            [str(python), "-I", "-S", "-B", "-c", script],
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
            cwd="/",
            env={"LANG": "C", "LC_ALL": "C", "PATH": "/usr/bin:/bin"},
        )
    except OSError as exc:
        raise BootstrapError("sealed Python cannot start native dyld proof") from exc
    if result.returncode != 0:
        raise BootstrapError(f"sealed native dyld load failed: {result.stderr.strip()}")


def _discover_transitive_prefix_natives(
    source_root: Path,
    runtime_root: Path,
    *,
    native_reader: Callable[[Path], NativeRecord],
) -> dict[Path, NativeRecord]:
    """Copy only native edges named by a sealed object, then re-inspect.

    The source environment is not recursively scanned.  An ``@rpath`` edge can
    use the conventional, explicit ``lib/<basename>`` candidate; anything else
    unknown is an attestation failure rather than an ambient dependency.
    """

    while True:
        records = {path: native_reader(path) for path in _native_candidates(runtime_root)}
        known = {path.resolve(strict=False) for path in records}
        additions: list[tuple[Path, Path]] = []
        for owner, record in records.items():
            for dependency in record.dependencies:
                source: Path | None = None
                target: Path | None = None
                if dependency.startswith(str(source_root) + "/"):
                    source = source_root / Path(dependency).relative_to(source_root)
                    target = runtime_root / source.relative_to(source_root)
                elif dependency.startswith("@rpath/"):
                    target = _resolve_rpath_dependency(
                        owner,
                        dependency,
                        record.rpaths,
                        runtime_root,
                        source_root,
                    )
                    if target is not None:
                        source = source_root / target.relative_to(runtime_root)
                if source is None or target is None:
                    continue
                relative = _safe_relative(source.relative_to(source_root), label="native dependency")
                if target.resolve(strict=False) not in known:
                    if source.suffix not in {".dylib", ".so"}:
                        raise BootstrapError("native dependency is not a Mach-O library")
                    additions.append((source, relative))
        if not additions:
            return records
        for source, relative in additions:
            if (runtime_root / relative).exists():
                continue
            _copy_native_alias(
                source, runtime_root, relative, source_root=source_root
            )


def _seal_tree(runtime_root: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    total_bytes = 0
    for path in _walk_regular_tree(runtime_root, label="sealed runtime"):
        relative = path.relative_to(runtime_root)
        executable = bool(stat.S_IMODE(os.lstat(path).st_mode) & 0o111)
        mode = 0o555 if executable else 0o444
        os.chmod(path, mode)
        body = _read_exact(path, label=f"sealed runtime {relative}")
        total_bytes += len(body)
        if total_bytes > MAX_TREE_BYTES:
            raise BootstrapError("sealed runtime exceeds its byte cap")
        records.append(
            {
                "path": relative.as_posix(),
                "sha256": hashlib.sha256(body).hexdigest(),
                "bytes": len(body),
                "mode": mode,
            }
        )
    for path in sorted(runtime_root.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        if path.is_dir():
            os.chmod(path, 0o555)
    os.chmod(runtime_root, 0o555)
    return sorted(records, key=lambda item: item["path"])


def _attest_sealed_tree(runtime_root: Path, files: Sequence[Mapping[str, Any]]) -> None:
    expected = {str(item["path"]): dict(item) for item in files}
    observed: dict[str, dict[str, Any]] = {}
    total_bytes = 0
    for path in _walk_regular_tree(runtime_root, label="sealed runtime"):
        relative = path.relative_to(runtime_root).as_posix()
        metadata = os.lstat(path)
        mode = stat.S_IMODE(metadata.st_mode)
        if mode not in (0o444, 0o555) or metadata.st_nlink != 1:
            raise BootstrapError("sealed runtime file metadata is unsafe")
        body = _read_exact(path, label=f"sealed runtime {relative}")
        total_bytes += len(body)
        if total_bytes > MAX_TREE_BYTES:
            raise BootstrapError("sealed runtime exceeds its byte cap")
        observed[relative] = {
            "path": relative,
            "sha256": hashlib.sha256(body).hexdigest(),
            "bytes": len(body),
            "mode": mode,
        }
    if observed != expected:
        raise BootstrapError("sealed runtime closure differs from its manifest")


def attest_target_profile(
    *,
    model_probe: Callable[[], str] | None = None,
    machine_probe: Callable[[], str] | None = None,
    theta_probe: Callable[[], None] | None = None,
) -> None:
    """Verify the actual M1 host profile without starting any producer."""

    if model_probe is None:
        def model_probe() -> str:
            try:
                return subprocess.run(
                    ["/usr/sbin/sysctl", "-n", "hw.model"],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=5,
                    env={"LANG": "C", "LC_ALL": "C", "PATH": "/usr/bin:/bin:/usr/sbin"},
                ).stdout.strip()
            except (OSError, subprocess.SubprocessError) as exc:
                raise BootstrapError("cannot read host model") from exc
    if machine_probe is None:
        machine_probe = platform.machine
    if theta_probe is None:
        def theta_probe() -> None:
            try:
                with socket.create_connection((THETA_HOST, THETA_PORT), timeout=5):
                    return None
            except OSError as exc:
                raise BootstrapError("local Theta is unavailable") from exc
    model = model_probe()
    machine = machine_probe()
    if model != EXPECTED_HOST_MODEL or machine != EXPECTED_MACHINE:
        raise BootstrapError(
            f"wrong target host: expected {EXPECTED_HOST_MODEL}/{EXPECTED_MACHINE}, got {model}/{machine}"
        )
    theta_probe()


def _attest_disposable_root(root: Path) -> None:
    metadata = _lstat_directory(
        root, label="disposable target root", owner_uid=os.geteuid()
    )
    if stat.S_IMODE(metadata.st_mode) != 0o700:
        raise BootstrapError("disposable target root must have mode 0700")
    marker = root / DISPOSABLE_MARKER
    marker_metadata = _lstat_regular(
        marker, label="disposable target marker", owner_uid=os.geteuid()
    )
    if stat.S_IMODE(marker_metadata.st_mode) != 0o600:
        raise BootstrapError("disposable target marker must have mode 0600")
    if _read_exact(marker, label="disposable target marker", maximum=256) != DISPOSABLE_MARKER_BODY:
        raise BootstrapError("target root is not marked disposable")
    try:
        entries = sorted(path.name for path in root.iterdir())
    except OSError as exc:
        raise BootstrapError("disposable target root cannot be enumerated") from exc
    if entries != [DISPOSABLE_MARKER]:
        raise BootstrapError("disposable target root contains an unexpected entry")


def _attest_persistent_root(root: Path) -> None:
    """Accept only the caller-created, empty, fixed persistent runtime root."""

    if root != PERSISTENT_RUNTIME_ROOT:
        raise BootstrapError("persistent target is not the fixed reviewed root")
    if root.resolve(strict=True) != root:
        raise BootstrapError("persistent target path contains a redirect")
    metadata = _lstat_directory(
        root, label="persistent target root", owner_uid=os.geteuid()
    )
    if stat.S_IMODE(metadata.st_mode) != 0o700:
        raise BootstrapError("persistent target root must have mode 0700")
    marker = root / PERSISTENT_MARKER
    marker_metadata = _lstat_regular(
        marker, label="persistent target marker", owner_uid=os.geteuid()
    )
    if stat.S_IMODE(marker_metadata.st_mode) != 0o600:
        raise BootstrapError("persistent target marker must have mode 0600")
    if (
        _read_exact(marker, label="persistent target marker", maximum=256)
        != PERSISTENT_MARKER_BODY
    ):
        raise BootstrapError("persistent target marker is not exact")
    try:
        entries = sorted(path.name for path in root.iterdir())
    except OSError as exc:
        raise BootstrapError("persistent target root cannot be enumerated") from exc
    if entries != [PERSISTENT_MARKER]:
        raise BootstrapError("persistent target root contains an unexpected entry")


def _attest_staged_persistent_root(root: Path) -> None:
    """Recheck the fixed marker/root after sealing and before receipt commit."""

    if root != PERSISTENT_RUNTIME_ROOT:
        raise BootstrapError("persistent target is not the fixed reviewed root")
    if root.resolve(strict=True) != root:
        raise BootstrapError("persistent target path contains a redirect")
    metadata = _lstat_directory(
        root, label="staged persistent target root", owner_uid=os.geteuid()
    )
    if stat.S_IMODE(metadata.st_mode) != 0o700:
        raise BootstrapError("persistent target root must have mode 0700")
    marker = root / PERSISTENT_MARKER
    marker_metadata = _lstat_regular(
        marker, label="staged persistent target marker", owner_uid=os.geteuid()
    )
    if (
        stat.S_IMODE(marker_metadata.st_mode) != 0o600
        or _read_exact(marker, label="staged persistent target marker", maximum=256)
        != PERSISTENT_MARKER_BODY
    ):
        raise BootstrapError("persistent target marker changed during installation")
    runtime = root / RUNTIME_DIRECTORY
    runtime_metadata = _lstat_directory(
        runtime, label="staged sealed runtime", owner_uid=os.geteuid()
    )
    if stat.S_IMODE(runtime_metadata.st_mode) != 0o555:
        raise BootstrapError("staged sealed runtime mode is unsafe")
    try:
        entries = sorted(path.name for path in root.iterdir())
    except OSError as exc:
        raise BootstrapError("staged persistent target cannot be enumerated") from exc
    if entries != [PERSISTENT_MARKER, RUNTIME_DIRECTORY]:
        raise BootstrapError("staged persistent target contains an unexpected entry")


def _run_git(
    repo_root: Path, *arguments: str, timeout: int = 30
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            [
                "/usr/bin/git",
                "-C",
                str(repo_root),
                "-c",
                "core.hooksPath=/dev/null",
                "-c",
                "protocol.file.allow=never",
                "-c",
                f"core.sshCommand={GIT_SSH_COMMAND}",
                *arguments,
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd="/",
            env={"LANG": "C", "LC_ALL": "C", "PATH": "/usr/bin:/bin"},
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise BootstrapError("clean release provenance cannot be read") from exc


def _fetch_canonical_origin(repo_root: Path) -> str:
    """Fetch only canonical ``main`` through the fixed read-only deploy key."""

    key_before = _lstat_regular(
        DEPLOY_KEY, label="selector Git deploy key", owner_uid=os.geteuid()
    )
    if stat.S_IMODE(key_before.st_mode) not in {0o400, 0o600}:
        raise BootstrapError("selector Git deploy key mode is unsafe")
    key_body = _read_exact(
        DEPLOY_KEY, label="selector Git deploy key", maximum=64 * 1024
    )
    if not key_body:
        raise BootstrapError("selector Git deploy key is empty")
    key_after = _lstat_regular(
        DEPLOY_KEY, label="selector Git deploy key", owner_uid=os.geteuid()
    )
    if _identity(key_before) != _identity(key_after):
        raise BootstrapError("selector Git deploy key changed during attestation")
    origin = _run_git(repo_root, "remote", "get-url", "origin")
    if origin.returncode != 0 or origin.stdout.strip() != CANONICAL_ORIGIN_URL:
        raise BootstrapError("selector release origin is not canonical")
    fetched = _run_git(
        repo_root,
        "fetch",
        "--quiet",
        "--no-tags",
        "origin",
        f"+refs/heads/main:{CANONICAL_ORIGIN_REF}",
        timeout=120,
    )
    if fetched.returncode != 0:
        raise BootstrapError("canonical selector release fetch failed")
    origin_after = _run_git(repo_root, "remote", "get-url", "origin")
    if (
        origin_after.returncode != 0
        or origin_after.stdout.strip() != CANONICAL_ORIGIN_URL
    ):
        raise BootstrapError("selector release origin changed during fetch")
    final_key = _read_exact(
        DEPLOY_KEY, label="selector Git deploy key after fetch", maximum=64 * 1024
    )
    final_key_metadata = _lstat_regular(
        DEPLOY_KEY, label="selector Git deploy key after fetch", owner_uid=os.geteuid()
    )
    if (
        final_key != key_body
        or _identity(final_key_metadata) != _identity(key_after)
    ):
        raise BootstrapError("selector Git deploy key changed during fetch")
    return hashlib.sha256(key_body).hexdigest()


def _attest_clean_release(repo_root: Path, expected_release_sha: str) -> str:
    """Bind an installation to one clean checkout of exact ``origin/main``."""

    if re.fullmatch(r"[0-9a-f]{40}", expected_release_sha) is None:
        raise BootstrapError("expected release SHA must be 40 lowercase hex characters")
    _lstat_directory(
        repo_root, label="persistent release checkout", owner_uid=os.geteuid()
    )
    commands = (
        ("show-toplevel", ("rev-parse", "--show-toplevel")),
        ("origin-url", ("remote", "get-url", "origin")),
        ("HEAD", ("rev-parse", "--verify", "HEAD^{commit}")),
        (
            "origin/main",
            ("rev-parse", "--verify", "refs/remotes/origin/main^{commit}"),
        ),
        (
            "worktree",
            ("diff", "--no-ext-diff", "--quiet", "--ignore-submodules", "--"),
        ),
        (
            "index",
            (
                "diff",
                "--cached",
                "--no-ext-diff",
                "--quiet",
                "--ignore-submodules",
                "--",
            ),
        ),
        ("status", ("status", "--porcelain=v1", "--untracked-files=all")),
    )
    observed: dict[str, str] = {}
    for label, arguments in commands:
        result = _run_git(repo_root, *arguments)
        if result.returncode != 0:
            raise BootstrapError(f"clean release {label} attestation failed")
        observed[label] = result.stdout.strip()
    try:
        top = Path(observed["show-toplevel"]).resolve(strict=True)
    except OSError as exc:
        raise BootstrapError("clean release checkout root is unavailable") from exc
    repo_real = repo_root.resolve(strict=True)
    if repo_real != repo_root:
        raise BootstrapError("persistent release checkout path contains a redirect")
    if top != repo_real:
        raise BootstrapError("repo root is not the exact Git checkout root")
    if observed["origin-url"] != CANONICAL_ORIGIN_URL:
        raise BootstrapError("persistent release origin is not canonical")
    if observed["HEAD"] != expected_release_sha:
        raise BootstrapError("checkout HEAD differs from expected release SHA")
    if observed["origin/main"] != expected_release_sha:
        raise BootstrapError("expected release is not the fetched origin/main")
    if observed["status"]:
        raise BootstrapError("persistent installation requires a clean release checkout")
    return expected_release_sha


def _committed_release_source_sha256(
    repo_root: Path, release_sha: str
) -> dict[str, str]:
    """Hash the exact committed selector/runner sources without worktree trust."""

    hashes: dict[str, str] = {}
    for relative in REPO_IMPORT_SOURCE_PATHS:
        object_name = f"{release_sha}:{relative.as_posix()}"
        size_result = _run_git(repo_root, "cat-file", "-s", object_name)
        if size_result.returncode != 0:
            raise BootstrapError(
                f"release source {relative.as_posix()} is unavailable at expected SHA"
            )
        try:
            size = int(size_result.stdout.strip())
        except ValueError as exc:
            raise BootstrapError("release source size is not canonical") from exc
        if (
            size <= 0 or size > MAX_REPO_SOURCE_BYTES
        ):
            raise BootstrapError(
                f"release source {relative.as_posix()} exceeds its byte envelope"
            )
        try:
            result = subprocess.run(
                ["/usr/bin/git", "-C", str(repo_root), "cat-file", "blob", object_name],
                check=False,
                capture_output=True,
                timeout=30,
                cwd="/",
                env={"LANG": "C", "LC_ALL": "C", "PATH": "/usr/bin:/bin"},
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise BootstrapError("release source provenance cannot be read") from exc
        if result.returncode != 0 or len(result.stdout) != size:
            raise BootstrapError(
                f"release source {relative.as_posix()} is unavailable at expected SHA"
            )
        hashes[relative.as_posix()] = hashlib.sha256(result.stdout).hexdigest()
    return hashes


def _isolated_import_acceptance(
    *, python: Path, repo_root: Path, site_packages: Path
) -> dict[str, str]:
    """Accept the current selector core, private auth, and one-shot runner."""

    repo_root = repo_root.resolve(strict=True)
    _lstat_directory(repo_root, label="selector import root")
    source_paths = tuple(
        (relative, repo_root / relative) for relative in REPO_IMPORT_SOURCE_PATHS
    )
    before = {
        relative.as_posix(): hashlib.sha256(
            _read_exact(path, label=f"selector import source {relative.as_posix()}")
        ).hexdigest()
        for relative, path in source_paths
    }
    runtime_root = python.parent.parent.resolve(strict=True)
    site_packages = site_packages.resolve(strict=True)
    try:
        site_packages.relative_to(runtime_root)
    except ValueError as exc:
        raise BootstrapError("sealed site-packages escapes the runtime") from exc
    stdlib = runtime_root / RUNTIME_STDLIB_RELATIVE
    dynload = stdlib / "lib-dynload"
    timezone_data = (runtime_root / RUNTIME_TIMEZONE_RELATIVE).resolve(strict=True)
    try:
        timezone_data.relative_to(runtime_root)
    except ValueError as exc:
        raise BootstrapError("sealed timezone database escapes the runtime") from exc
    script = (
        "import importlib\nimport pathlib\nimport platform\nimport sys\n"
        f"runtime = pathlib.Path({str(runtime_root)!r}).resolve()\n"
        f"source = pathlib.Path({str(EXPECTED_RUNTIME_SOURCE)!r}).resolve()\n"
        f"repo = pathlib.Path({str(repo_root)!r}).resolve()\n"
        f"sealed = pathlib.Path({str(site_packages)!r}).resolve()\n"
        f"stdlib = pathlib.Path({str(stdlib)!r}).resolve()\n"
        f"dynload = pathlib.Path({str(dynload)!r}).resolve()\n"
        f"timezone_data = pathlib.Path({str(timezone_data)!r}).resolve()\n"
        f"required = {list(RUNTIME_REQUIRED_IMPORTS)!r}\n"
        "assert pathlib.Path(sys.executable).resolve() == runtime / 'bin/python3.12'\n"
        "assert pathlib.Path(sys.prefix).resolve() == runtime\n"
        "assert pathlib.Path(sys.base_prefix).resolve() == runtime\n"
        "assert all(str(source) not in item for item in sys.path)\n"
        "sys.path[:] = [str(sealed), str(repo), str(stdlib), str(dynload)]\n"
        "import zoneinfo\n"
        "zoneinfo.reset_tzpath([str(timezone_data)])\n"
        "assert zoneinfo.TZPATH == (str(timezone_data),)\n"
        "zoneinfo.ZoneInfo('America/New_York')\n"
        "assert sys.version_info[:2] == (3, 12)\n"
        f"assert platform.machine() == {EXPECTED_MACHINE!r}\n"
        "for name in required:\n"
        "    module = importlib.import_module(name)\n"
        "    location = pathlib.Path(module.__file__).resolve()\n"
        "    location.relative_to(sealed)\n"
        "from engine import options_sparse_selector as selector\n"
        "from engine import private_auth_dict\n"
        "from ops.launchd import run_options_sparse_selector_verified as carrier\n"
        "from scripts import run_options_sparse_selector as runner\n"
        "assert selector.SELECTOR_RUNTIME_ARMED is True\n"
        "assert selector.SELECTOR_PROPOSALS_ARMED is False\n"
        "assert carrier.SELECTOR_RUNTIME_ARMED is False\n"
        "assert runner.PROPOSALS_ARMED is False\n"
        "assert private_auth_dict.__name__ == 'engine.private_auth_dict'\n"
        "for module in tuple(sys.modules.values()):\n"
        "    raw = getattr(module, '__file__', None)\n"
        "    if raw is None:\n"
        "        continue\n"
        "    location = pathlib.Path(raw).resolve()\n"
        "    assert str(source) not in str(location)\n"
        "    assert location.is_relative_to(runtime) or location.is_relative_to(repo)\n"
    )
    try:
        result = subprocess.run(
            [str(python), "-I", "-S", "-B", "-c", script],
            check=False,
            capture_output=True,
            text=True,
            timeout=90,
            cwd="/",
            env={"LANG": "C", "LC_ALL": "C", "PATH": "/usr/bin:/bin"},
        )
    except OSError as exc:
        raise BootstrapError("sealed Python cannot start isolated import proof") from exc
    if result.returncode != 0:
        raise BootstrapError(f"isolated selector import failed: {result.stderr.strip()}")
    after = {
        relative.as_posix(): hashlib.sha256(
            _read_exact(path, label=f"selector import source {relative.as_posix()}")
        ).hexdigest()
        for relative, path in source_paths
    }
    if before != after:
        raise BootstrapError("selector import sources changed during isolated proof")
    return before


def _attest_distinct_target_roots(
    *, source_root: Path, target_root: Path, repo_root: Path
) -> None:
    if (
        not source_root.is_absolute()
        or not target_root.is_absolute()
        or not repo_root.is_absolute()
    ):
        raise BootstrapError("runtime source, target, and repo roots must be absolute")
    try:
        source_real = source_root.resolve(strict=True)
        target_real = target_root.resolve(strict=True)
        repo_real = repo_root.resolve(strict=True)
    except OSError as exc:
        raise BootstrapError("runtime source, target, or repo root is unavailable") from exc
    if (
        _contains(source_real, target_real)
        or _contains(target_real, source_real)
        or _contains(repo_real, target_real)
        or _contains(target_real, repo_real)
    ):
        raise BootstrapError("runtime target must be a distinct absolute root")


def _provision_runtime_target(
    *,
    source_root: Path,
    target_root: Path,
    repo_root: Path,
    installation: Mapping[str, str] | None = None,
    expected_repo_import_source_sha256: Mapping[str, str] | None = None,
    pre_manifest_attestor: Callable[[], None] | None = None,
    native_reader: Callable[[Path], NativeRecord] = _native_record,
) -> dict[str, Any]:
    """Copy and seal a runtime after its target and provenance were attested."""

    components = _selected_source_components(source_root)
    runtime_root = target_root / RUNTIME_DIRECTORY
    runtime_root.mkdir(mode=0o700)
    try:
        for relative, exclude in components:
            _copy_component(source_root / relative, runtime_root, relative, exclude=exclude)
        records = _discover_transitive_prefix_natives(
            source_root, runtime_root, native_reader=native_reader
        )
        plan = _native_relocation_plan(
            runtime_root, records, source_prefix=source_root
        )
        if any(plan.values()):
            _apply_native_relocations(plan)
            records = _discover_transitive_prefix_natives(
                source_root, runtime_root, native_reader=native_reader
            )
            if any(
                _native_relocation_plan(
                    runtime_root, records, source_prefix=source_root
                ).values()
            ):
                raise BootstrapError("native graph retains a mutable relocation binding")
        _seal_native_signatures(tuple(records))
        records = {
            path: native_reader(path) for path in _native_candidates(runtime_root)
        }
        if any(
            _native_relocation_plan(
                runtime_root, records, source_prefix=source_root
            ).values()
        ):
            raise BootstrapError("signed native graph differs from its sealed relocation")
        natives = sorted(records, key=lambda path: path.as_posix())
        _native_dyld_acceptance(
            python=runtime_root / RUNTIME_PYTHON_RELATIVE,
            runtime_root=runtime_root,
            natives=natives,
        )
        files = _seal_tree(runtime_root)
        _attest_sealed_tree(runtime_root, files)
        repo_import_source_sha256 = _isolated_import_acceptance(
            python=runtime_root / RUNTIME_PYTHON_RELATIVE,
            repo_root=repo_root,
            site_packages=runtime_root / RUNTIME_SITE_PACKAGES_RELATIVE,
        )
        if (
            expected_repo_import_source_sha256 is not None
            and repo_import_source_sha256
            != dict(expected_repo_import_source_sha256)
        ):
            raise BootstrapError("selector import sources differ from expected release")
        receipt = {
            "schema": MANIFEST_SCHEMA,
            "authority": False,
            "training": False,
            "profile": {
                "model": EXPECTED_HOST_MODEL,
                "machine": EXPECTED_MACHINE,
                "theta": f"{THETA_HOST}:{THETA_PORT}",
                "python": str(EXPECTED_RUNTIME_SOURCE / RUNTIME_PYTHON_RELATIVE),
            },
            "source_runtime": str(source_root),
            "runtime": RUNTIME_DIRECTORY,
            "timezone_database": RUNTIME_TIMEZONE_RELATIVE.as_posix(),
            "repo_import_source_sha256": repo_import_source_sha256,
            "files": files,
            "imports": list(RUNTIME_REQUIRED_IMPORTS),
            "native_signature": "adhoc",
            "native_dyld_loaded": len(natives) - 1,
            "native_files": [path.relative_to(runtime_root).as_posix() for path in natives],
        }
        if installation is not None:
            receipt["installation"] = dict(installation)
        if pre_manifest_attestor is not None:
            pre_manifest_attestor()
        manifest = target_root / MANIFEST_NAME
        _write_exclusive(manifest, _canonical_json(receipt))
        return receipt
    except Exception:
        # The caller owns deletion of its explicit disposable root.  The carrier
        # never recursively deletes a path supplied by an operator.
        raise


def prove_disposable_target(
    *,
    source_root: Path,
    target_root: Path,
    repo_root: Path,
    native_reader: Callable[[Path], NativeRecord] = _native_record,
) -> dict[str, Any]:
    """Snapshot and attest one caller-created disposable runtime target."""

    _attest_distinct_target_roots(
        source_root=source_root, target_root=target_root, repo_root=repo_root
    )
    _attest_disposable_root(target_root)
    attest_target_profile()
    return _provision_runtime_target(
        source_root=source_root,
        target_root=target_root,
        repo_root=repo_root,
        native_reader=native_reader,
    )


def install_persistent_target(
    *,
    source_root: Path,
    repo_root: Path,
    expected_release_sha: str,
    target_root: Path | None = None,
    native_reader: Callable[[Path], NativeRecord] = _native_record,
) -> dict[str, Any]:
    """Seal a clean exact release into the one caller-created private root.

    The installer writes only the runtime closure and its receipt.  It never
    creates selector state, installs/loads launchd, or invokes selector code.
    """

    target = PERSISTENT_RUNTIME_ROOT if target_root is None else target_root
    if repo_root != PERSISTENT_REPO_ROOT:
        raise BootstrapError("persistent repo is not the fixed dedicated checkout")
    _attest_distinct_target_roots(
        source_root=source_root, target_root=target, repo_root=repo_root
    )
    _attest_persistent_root(target)
    try:
        filesystem = os.statvfs(target)
    except OSError as exc:
        raise BootstrapError("persistent target capacity cannot be read") from exc
    if filesystem.f_bavail * filesystem.f_frsize < MIN_PERSISTENT_FREE_BYTES:
        raise BootstrapError("persistent target lacks the 10 GiB safety floor")
    attest_target_profile()
    deploy_key_sha256 = _fetch_canonical_origin(repo_root)
    release_sha = _attest_clean_release(repo_root, expected_release_sha)
    expected_source_sha256 = _committed_release_source_sha256(
        repo_root, release_sha
    )

    def attest_release_unchanged() -> None:
        _attest_clean_release(repo_root, expected_release_sha)
        _attest_staged_persistent_root(target)

    return _provision_runtime_target(
        source_root=source_root,
        target_root=target,
        repo_root=repo_root,
        installation={
            "kind": "persistent",
            "target_root": str(PERSISTENT_RUNTIME_ROOT),
            "repo_root": str(PERSISTENT_REPO_ROOT),
            "origin_url": CANONICAL_ORIGIN_URL,
            "deploy_key": str(DEPLOY_KEY),
            "deploy_key_sha256": deploy_key_sha256,
            "marker": PERSISTENT_MARKER,
            "marker_sha256": hashlib.sha256(PERSISTENT_MARKER_BODY).hexdigest(),
            "expected_release_sha": expected_release_sha,
            "release_sha": release_sha,
        },
        expected_repo_import_source_sha256=expected_source_sha256,
        pre_manifest_attestor=attest_release_unchanged,
        native_reader=native_reader,
    )


def _proof_parser(arguments: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="run_options_sparse_selector_verified.py")
    parser.add_argument("--prove-disposable-target", action="store_true")
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--target-root", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parsed = parser.parse_args(list(arguments))
    if not parsed.prove_disposable_target:
        raise BootstrapError("ordinary selector invocation is code-unarmed")
    return parsed


def _persistent_parser(arguments: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="run_options_sparse_selector_verified.py")
    parser.add_argument("--install-persistent-target", action="store_true")
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--expected-release-sha", required=True)
    parsed = parser.parse_args(list(arguments))
    if not parsed.install_persistent_target:
        raise BootstrapError("ordinary selector invocation is code-unarmed")
    return parsed


def main(argv: Sequence[str] | None = None) -> int:
    arguments = tuple(sys.argv[1:] if argv is None else argv)
    # Neither explicit carrier command is a selector invocation.  Every other
    # argv variant fails before a host probe, Git call, private-root creation,
    # producer import, or external write.
    if not arguments or arguments[0] not in {
        "--prove-disposable-target",
        "--install-persistent-target",
    }:
        print("options sparse selector runtime is code-unarmed", file=sys.stderr)
        return 3
    if arguments[0] == "--prove-disposable-target":
        parsed = _proof_parser(arguments)
        receipt = prove_disposable_target(
            source_root=parsed.source_root,
            target_root=parsed.target_root,
            repo_root=parsed.repo_root,
        )
    else:
        parsed = _persistent_parser(arguments)
        receipt = install_persistent_target(
            source_root=parsed.source_root,
            repo_root=parsed.repo_root,
            expected_release_sha=parsed.expected_release_sha,
        )
    print(_canonical_json(receipt).decode("utf-8"))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BootstrapError as exc:
        print(f"options sparse selector carrier refused: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
