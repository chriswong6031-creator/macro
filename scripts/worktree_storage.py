#!/usr/bin/env python3
"""Host-scoped external worktree storage. No scheduler or workload admission policy.

The optional host file is ~/.config/mastermind/worktree-storage.json. An installed
policy is mandatory: invalid/unavailable storage never falls back to local disk.
Git remains the worktree registry; receipts only identify repeat hook invocations.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import subprocess
import sys
import uuid

POLICY_PATH = Path.home() / '.config/mastermind/worktree-storage.json'
LOCK_REASON = 'mastermind-external-storage: removable volume protection'


class StorageError(RuntimeError):
    pass


def load_policy(path: Path | None = None) -> dict | None:
    path = Path(path or POLICY_PATH)
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text())
        if value['version'] != 1 or not isinstance(value['volume_uuid'], str) or not value['volume_uuid']:
            raise ValueError('invalid version or volume identity')
        for key in ('mount_point', 'root'):
            if not isinstance(value[key], str) or not Path(value[key]).is_absolute():
                raise ValueError(f'{key} must be absolute')
        floor = value['min_free_bytes']
        if not isinstance(floor, int) or isinstance(floor, bool) or floor < 0:
            raise ValueError('invalid free-space floor')
        return value
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise StorageError(f'invalid storage policy: {path}: {exc}') from exc


def volume_info(mount: Path) -> dict:
    try:
        result = subprocess.run(['diskutil', 'info', '-plist', str(mount)], capture_output=True, check=True, timeout=15)
        return plistlib.loads(result.stdout)
    except (OSError, subprocess.SubprocessError, plistlib.InvalidFileException) as exc:
        raise StorageError('SSD volume identity is unavailable') from exc


def _contained(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def check_storage(policy: dict, target: Path | None = None, *, check_space: bool = True) -> Path:
    mount, root = Path(policy['mount_point']), Path(policy['root'])
    target = Path(target or root)
    for item in (mount, root, target):
        if not item.is_absolute() or '..' in item.parts or item.resolve() != item:
            raise StorageError(f'unsafe storage path or symlink: {item}')
    if root == mount or not _contained(root, mount) or not _contained(target, root):
        raise StorageError('destination escapes the configured SSD workspace root')
    if not mount.is_dir():
        raise StorageError('SSD mount is unavailable; refusing internal fallback')
    info = volume_info(mount)
    if (info.get('VolumeUUID') != policy['volume_uuid'] or info.get('MountPoint') != str(mount)
            or info.get('Internal') is not False or info.get('Writable') is not True
            or info.get('FilesystemType') != 'apfs'):
        raise StorageError('SSD identity, mount, filesystem or writeability check failed')
    ancestor = target
    while not ancestor.exists():
        ancestor = ancestor.parent
    if ancestor.stat().st_dev != mount.stat().st_dev:
        raise StorageError('destination is on another filesystem')
    if check_space and shutil.disk_usage(mount).free < policy['min_free_bytes']:
        raise StorageError('SSD free space is below the storage policy floor')
    return root


def _mkdir_on_volume(policy: dict, target: Path) -> None:
    """Walk using directory descriptors: never follow a replaced path component."""
    check_storage(policy, target)
    mount = Path(policy['mount_point'])
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    fd = os.open(mount, flags)
    try:
        device = os.fstat(fd).st_dev
        for part in target.relative_to(mount).parts:
            try:
                os.mkdir(part, mode=0o700, dir_fd=fd)
            except FileExistsError:
                pass
            child = os.open(part, flags, dir_fd=fd)
            if os.fstat(child).st_dev != device:
                os.close(child)
                raise StorageError('workspace component crosses filesystems')
            os.close(fd)
            fd = child
    finally:
        os.close(fd)
    check_storage(policy, target)


def prepare_root(policy: dict) -> Path:
    root = check_storage(policy)
    _mkdir_on_volume(policy, root)
    return root


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(['git', '-c', 'maintenance.auto=false', '-c', 'gc.auto=0', '-C', str(repo), *args],
                            text=True, capture_output=True)
    if result.returncode:
        raise StorageError(f'git {args[0]} failed: {result.stderr.strip()[-1000:]}')
    return result.stdout.strip()


def destination(policy: dict, repo: Path, name: str, session: str) -> tuple[Path, str]:
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,99}', name):
        raise StorageError('unsafe worktree name')
    if not session:
        raise StorageError('session identity is required')
    common = git(repo, 'rev-parse', '--path-format=absolute', '--git-common-dir')
    key = hashlib.sha256((common + '\0' + session + '\0' + name).encode()).hexdigest()
    repo_key = hashlib.sha256(common.encode()).hexdigest()[:16]
    return Path(policy['root']) / 'claude' / repo_key / f'{name}-{key[:16]}', key


def _default_base(repo: Path) -> tuple[str, bool]:
    try:
        git(repo, 'remote', 'get-url', 'origin')
    except StorageError:
        return 'HEAD', False
    try:
        ref = git(repo, 'symbolic-ref', 'refs/remotes/origin/HEAD')
        return ref.removeprefix('refs/remotes/origin/'), True
    except StorageError:
        for branch in ('main', 'master'):
            try:
                git(repo, 'show-ref', '--verify', f'refs/remotes/origin/{branch}')
                return branch, True
            except StorageError:
                pass
    raise StorageError('origin default branch is unknown; refusing a stale-base fallback')


def create_worktree(policy: dict, repo: Path, name: str, session: str, *, base: str | None = None, fetch: bool = True) -> Path:
    repo = Path(repo).resolve()
    root = prepare_root(policy)
    dest, key = destination(policy, repo, name, session)
    common = git(repo, 'rev-parse', '--path-format=absolute', '--git-common-dir')
    repo_key = hashlib.sha256(common.encode()).hexdigest()[:16]
    lock_dir, receipt_dir = root / '.storage-locks', root / '.storage-receipts'
    _mkdir_on_volume(policy, lock_dir)
    _mkdir_on_volume(policy, receipt_dir)
    # Serialization only for this repository's short Git metadata transaction.
    # It is not a limit on running agents, builds, or host concurrency.
    fd = os.open(lock_dir / (repo_key + '.lock'), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        check_storage(policy, dest)
        receipt = receipt_dir / (key + '.json')
        branch = f'claude/ssd-{name}-{key[:16]}'
        expected = dict(key=key, common=common, path=str(dest), branch=branch)
        if dest.exists():
            try:
                if receipt.is_symlink() or json.loads(receipt.read_text()) != expected:
                    raise ValueError('receipt mismatch')
            except (OSError, ValueError):
                raise StorageError(f'unreceipted or foreign destination retained: {dest}') from None
            registered = git(repo, 'worktree', 'list', '--porcelain').splitlines()
            if (f'worktree {dest}' not in registered or git(dest, 'rev-parse', '--path-format=absolute', '--git-common-dir') != common
                    or git(dest, 'symbolic-ref', '--short', 'HEAD') != branch):
                raise StorageError('existing worktree identity changed; refusing adoption')
            return dest
        if receipt.exists():
            raise StorageError('receipted worktree is missing; refusing replacement')
        if base is None:
            base, fetch = _default_base(repo)
        if fetch:
            if re.fullmatch(r'pr-[0-9]+', name):
                base_ref = f'refs/mastermind-worktrees/base/{key}'
                git(repo, 'fetch', 'origin', f'+refs/pull/{name[3:]}/head:{base_ref}')
            else:
                remote_branch = base.removeprefix('refs/remotes/origin/').removeprefix('origin/')
                base_ref = f'refs/mastermind-worktrees/base/{key}'
                git(repo, 'fetch', 'origin', f'+refs/heads/{remote_branch}:{base_ref}')
        else:
            base_ref = base
        # A transaction-specific ref prevents unrelated fetches from changing the base.
        commit = git(repo, 'rev-parse', '--verify', base_ref + '^{commit}')
        _mkdir_on_volume(policy, dest.parent)
        git(repo, 'worktree', 'add', '--lock', '--reason', LOCK_REASON, '--no-checkout', '--no-track', '-b', branch, str(dest), commit)
        try:
            profile_path = repo / 'config/sparse_worktree.json'
            if profile_path.exists():
                profile = json.loads(profile_path.read_text())
                if profile.get('enabled'):
                    dirs = git(repo, 'ls-tree', '-d', '--name-only', commit).splitlines()
                    selected = [p for p in dirs if p not in profile.get('exclude_dirs', [])]
                    git(dest, 'sparse-checkout', 'set', '--cone', '--', *selected)
            git(dest, 'read-tree', '-mu', 'HEAD')
            check_storage(policy, dest)
            with receipt.open('x') as out:
                json.dump(expected, out, sort_keys=True)
                out.write('\n')
        except Exception as exc:
            # Preserve failed partial work and its lock. Never force-delete a
            # directory that another actor might already have entered.
            raise StorageError(f'creation incomplete; locked worktree preserved at {dest}: {exc}') from exc
        return dest


def protect_worktree(policy: dict, cwd: Path, *, sparsify: bool = True) -> bool:
    """Protect a newly opened external linked checkout; grandfather internal ones."""
    root = Path(policy['root'])
    cwd = Path(cwd).resolve()
    if root not in cwd.parents:
        return False
    check_storage(policy, cwd)
    common = git(cwd, 'rev-parse', '--path-format=absolute', '--git-common-dir')
    gitdir = git(cwd, 'rev-parse', '--path-format=absolute', '--git-dir')
    if common == gitdir:
        return False
    # Preserve all pre-existing lock reasons, including operator holds.
    lock = Path(gitdir) / 'locked'
    if not lock.exists():
        git(cwd, 'worktree', 'lock', '--reason', LOCK_REASON, str(cwd))
    profile = cwd / 'config/sparse_worktree.json'
    sparse = subprocess.run(['git', '-C', str(cwd), 'config', '--get', 'core.sparseCheckout'], capture_output=True, text=True).stdout.strip()
    if sparsify and sparse != 'true' and profile.exists() and not git(cwd, 'status', '--porcelain'):
        config = json.loads(profile.read_text())
        if config.get('enabled'):
            dirs = git(cwd, 'ls-tree', '-d', '--name-only', 'HEAD').splitlines()
            selected = [p for p in dirs if p not in config.get('exclude_dirs', [])]
            git(cwd, 'sparse-checkout', 'set', '--cone', '--', *selected)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path)
    parser.add_argument('command', choices=['check', 'create', 'check-path', 'session-start'])
    parser.add_argument('path', nargs='?', type=Path)
    args = parser.parse_args()
    try:
        policy = load_policy(args.config)
        if policy is None:
            raise StorageError('host storage policy is not installed')
        if args.command == 'session-start':
            payload = json.load(sys.stdin)
            protected = protect_worktree(policy, Path(payload['cwd']))
            print('External SSD worktree verified and protected.' if protected else 'Existing checkout retained. Create new worktrees through the required external SSD storage helper; no internal fallback.')
        elif args.command == 'create':
            payload = json.load(sys.stdin)
            result = create_worktree(policy, Path(payload['cwd']), payload['name'], payload.get('session_id') or str(uuid.uuid4()))
            print(result)
        else:
            root = check_storage(policy, args.path)
            print(json.dumps(dict(status='SSD_VERIFIED', root=str(root), volume_uuid=policy['volume_uuid'])))
        return 0
    except (StorageError, OSError, ValueError, KeyError, TypeError) as exc:
        print(f'worktree-storage: REFUSED: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
