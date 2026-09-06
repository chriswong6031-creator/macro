#!/bin/bash
set -euo pipefail
umask 027

cache=${1:-/var/cache/mastermind-ci/macro.git}
lock=${2:-/run/lock/mastermind-ci-cache.lock}
seal="$cache/.last-update-ok"

# The validation seal is acceleration evidence only. It never weakens the
# per-job GIT_NO_LAZY_FETCH exact-tree materialization boundary.
seal_tool() {
  /usr/bin/python3 -I - "$@" <<'PY'
import datetime
import hashlib
import json
import os
import re
import stat
import sys
import tempfile
from pathlib import Path


SCHEMA = "mastermind.ci_git_cache_validation_seal.v1"
RECEIPT_SCHEMA = "mastermind.ci_git_cache_validation_receipt.v1"
VALIDATOR_REVISION = "reachable-main-batch-check.v2"
KEYS = {
    "schema",
    "validator_revision",
    "cache_instance",
    "main_oid",
    "identity_sha256",
    "shallow_boundary",
    "lookup_context_sha256",
    "object_context_sha256",
    "full_validated_at",
}


class UnsafeState(RuntimeError):
    pass


def fail(message):
    print("unsafe cache validation seal state: " + message, file=sys.stderr)
    raise SystemExit(78)


def owned(path, *, directory=False, regular=False, owner_writable=False):
    try:
        value = os.lstat(path)
    except OSError as exc:
        raise UnsafeState("%s: %s" % (path, exc)) from exc
    if stat.S_ISLNK(value.st_mode):
        raise UnsafeState("symlink refused: %s" % path)
    if directory and not stat.S_ISDIR(value.st_mode):
        raise UnsafeState("directory required: %s" % path)
    if regular and not stat.S_ISREG(value.st_mode):
        raise UnsafeState("regular file required: %s" % path)
    if regular and value.st_nlink != 1:
        raise UnsafeState("hard-linked file refused: %s" % path)
    if value.st_uid != os.geteuid():
        raise UnsafeState("owner uid mismatch: %s" % path)
    if value.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise UnsafeState("group/world-writable path refused: %s" % path)
    if owner_writable and not value.st_mode & stat.S_IWUSR:
        raise UnsafeState("owner-writable directory required: %s" % path)
    return value


def digest_file(path):
    value = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def optional_file(path):
    if not os.path.lexists(path):
        return {"present": False, "sha256": None}
    owned(path, regular=True)
    return {"present": True, "sha256": digest_file(path)}


def lookup_guard(cache):
    owned(cache / "config", regular=True)
    shallow_boundary = optional_file(cache / "shallow")
    for relative in ("objects/info", "info"):
        ancestor = cache / relative
        if os.path.lexists(ancestor):
            owned(ancestor, directory=True)
    files = {}
    for relative in (
        "objects/info/alternates",
        "objects/info/http-alternates",
        "info/grafts",
    ):
        path = cache / relative
        files[relative] = optional_file(path)
        if relative in (
            "objects/info/alternates",
            "objects/info/http-alternates",
        ) and files[relative]["present"]:
            if owned(path, regular=True).st_size != 0:
                raise UnsafeState(
                    "nonempty external alternate lookup refused: %s" % path
                )
    return files, shallow_boundary


def cache_guard(cache):
    absolute = Path(os.path.abspath(str(cache)))
    try:
        resolved = absolute.resolve(strict=True)
    except OSError as exc:
        raise UnsafeState("cache path cannot be resolved: %s" % exc) from exc
    if resolved != absolute:
        raise UnsafeState("cache path traverses a symlink: %s" % absolute)
    owned(absolute.parent, directory=True, owner_writable=True)
    cache_stat = owned(absolute, directory=True, owner_writable=True)
    objects_stat = owned(absolute / "objects", directory=True, owner_writable=True)
    identity = absolute / ".mastermind-cache-identity.json"
    owned(identity, regular=True)
    seal = absolute / ".last-update-ok"
    if os.path.lexists(seal):
        owned(seal, regular=True)
    lookup_files, shallow_boundary = lookup_guard(absolute)
    return absolute, cache_stat, objects_stat, lookup_files, shallow_boundary


def object_context(cache, objects_stat):
    records = [
        ["objects", objects_stat.st_dev, objects_stat.st_ino, objects_stat.st_mtime_ns]
    ]
    for entry in sorted(os.scandir(cache / "objects"), key=lambda item: item.name):
        if entry.name == "pack" or re.fullmatch(r"[0-9a-f]{2}", entry.name):
            value = owned(Path(entry.path), directory=True)
            records.append(
                ["directory", entry.name, value.st_dev, value.st_ino, value.st_mtime_ns]
            )
            if entry.name == "pack":
                for packed in sorted(
                    os.scandir(entry.path), key=lambda item: item.name
                ):
                    packed_stat = owned(Path(packed.path), regular=True)
                    records.append(
                        [
                            "pack-entry",
                            packed.name,
                            packed_stat.st_dev,
                            packed_stat.st_ino,
                            packed_stat.st_size,
                            packed_stat.st_mtime_ns,
                        ]
                    )
    encoded = json.dumps(records, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def expected_state(cache_arg, main_oid, lookup_digest):
    if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", main_oid):
        raise UnsafeState("invalid main object id")
    if not re.fullmatch(r"[0-9a-f]{64}", lookup_digest):
        raise UnsafeState("invalid lookup-context digest")
    cache, cache_stat, objects_stat, lookup_files, shallow_boundary = cache_guard(
        Path(cache_arg)
    )
    identity = cache / ".mastermind-cache-identity.json"
    lookup_context = json.dumps(
        {"git_context_sha256": lookup_digest, "files": lookup_files},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        "schema": SCHEMA,
        "validator_revision": VALIDATOR_REVISION,
        "cache_instance": {
            "path": str(cache),
            "device": cache_stat.st_dev,
            "inode": cache_stat.st_ino,
            "objects_device": objects_stat.st_dev,
            "objects_inode": objects_stat.st_ino,
        },
        "main_oid": main_oid,
        "identity_sha256": digest_file(identity),
        "shallow_boundary": shallow_boundary,
        "lookup_context_sha256": hashlib.sha256(lookup_context).hexdigest(),
        "object_context_sha256": object_context(cache, objects_stat),
    }


def timestamp():
    return (
        datetime.datetime.now(datetime.timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def valid_timestamp(value):
    if not isinstance(value, str) or not value.endswith("Z"):
        return False
    try:
        datetime.datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return False
    return True


def receipt(mode, main_oid, full_validated_at, reused_at):
    return json.dumps(
        {
            "schema": RECEIPT_SCHEMA,
            "mode": mode,
            "main_oid": main_oid,
            "full_validated_at": full_validated_at,
            "reused_at": reused_at,
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def state_fingerprint(state):
    encoded = json.dumps(
        state, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def invalidate(cache_arg):
    cache, _, _, _, _ = cache_guard(Path(cache_arg))
    seal = cache / ".last-update-ok"
    if os.path.lexists(seal):
        os.unlink(seal)
        directory_fd = os.open(cache, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)


def probe(cache_arg, main_oid, lookup_digest):
    expected = expected_state(cache_arg, main_oid, lookup_digest)
    seal = Path(cache_arg) / ".last-update-ok"
    if not os.path.lexists(seal):
        raise SystemExit(10)
    try:
        with open(seal, "r", encoding="utf-8") as handle:
            prior = json.load(handle)
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise SystemExit(10)
    if not isinstance(prior, dict) or set(prior) != KEYS:
        raise SystemExit(10)
    full_validated_at = prior.get("full_validated_at")
    if not valid_timestamp(full_validated_at):
        raise SystemExit(10)
    if any(prior.get(key) != value for key, value in expected.items()):
        raise SystemExit(10)
    print(
        receipt(
            "PRIOR_VALIDATION_REUSED",
            main_oid,
            full_validated_at,
            timestamp(),
        )
    )


def settle_failed_publication(cache, seal, published_identity, directory_fd):
    try:
        os.lstat(seal)
    except FileNotFoundError:
        return
    current = owned(seal, regular=True)
    if (current.st_dev, current.st_ino) != published_identity:
        raise UnsafeState(
            "foreign seal replaced this publication; settlement refused"
        )
    os.unlink(seal)
    try:
        os.fsync(directory_fd)
    except OSError:
        # The failed publication is no longer usable in the current namespace.
        # The caller still returns failure because its durability was not proven.
        pass


def publish(cache_arg, main_oid, lookup_digest, validated_state_fingerprint):
    state = expected_state(cache_arg, main_oid, lookup_digest)
    if state_fingerprint(state) != validated_state_fingerprint:
        raise UnsafeState("cache validation input changed during full validation")
    cache = Path(cache_arg)
    seal = cache / ".last-update-ok"
    if os.path.lexists(seal):
        raise UnsafeState("seal appeared after invalidation")
    full_validated_at = timestamp()
    state["full_validated_at"] = full_validated_at
    descriptor = None
    directory_fd = None
    temporary = None
    published_identity = None
    try:
        directory_fd = os.open(
            cache, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        )
        directory_stat = os.fstat(directory_fd)
        cache_instance = state["cache_instance"]
        if (
            not stat.S_ISDIR(directory_stat.st_mode)
            or directory_stat.st_dev != cache_instance["device"]
            or directory_stat.st_ino != cache_instance["inode"]
        ):
            raise UnsafeState("cache directory identity changed before publication")
        descriptor, temporary = tempfile.mkstemp(
            prefix=".last-update-ok.tmp.", dir=str(cache)
        )
        os.fchmod(descriptor, 0o640)
        temporary_stat = os.fstat(descriptor)
        if (
            not stat.S_ISREG(temporary_stat.st_mode)
            or temporary_stat.st_uid != os.geteuid()
            or temporary_stat.st_nlink != 1
        ):
            raise UnsafeState("temporary seal ownership/type/link state is unsafe")
        payload = (
            json.dumps(state, sort_keys=True, separators=(",", ":")) + "\n"
        ).encode("utf-8")
        written = os.write(descriptor, payload)
        if written != len(payload):
            raise UnsafeState(
                "short seal payload write: wrote %s of %s bytes"
                % (written, len(payload))
            )
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        os.replace(temporary, seal)
        temporary = None
        published_identity = (temporary_stat.st_dev, temporary_stat.st_ino)
        installed = owned(seal, regular=True)
        if (installed.st_dev, installed.st_ino) != published_identity:
            raise UnsafeState("foreign seal appeared during publication")
        os.fsync(directory_fd)
    except Exception as exc:
        if published_identity is not None and directory_fd is not None:
            try:
                settle_failed_publication(
                    cache, seal, published_identity, directory_fd
                )
            except UnsafeState as settlement_error:
                raise settlement_error from exc
            raise UnsafeState(
                "seal publication failed before directory durability: %s" % exc
            ) from exc
        if isinstance(exc, UnsafeState):
            raise
        raise UnsafeState("seal publication failed: %s" % exc) from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary is not None:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
        if directory_fd is not None:
            os.close(directory_fd)
    print(receipt("FULL_VALIDATION", main_oid, full_validated_at, None))


try:
    action = sys.argv[1]
    cache_arg = sys.argv[2]
    if action == "guard":
        cache_guard(Path(cache_arg))
    elif action == "invalidate":
        invalidate(cache_arg)
    elif action == "probe":
        probe(cache_arg, sys.argv[3], sys.argv[4])
    elif action == "fingerprint":
        print(state_fingerprint(expected_state(cache_arg, sys.argv[3], sys.argv[4])))
    elif action == "publish":
        publish(cache_arg, sys.argv[3], sys.argv[4], sys.argv[5])
    else:
        raise UnsafeState("unknown seal action")
except UnsafeState as exc:
    fail(str(exc))
PY
}

sha256_stream() {
  /usr/bin/python3 -I -c \
    'import hashlib, sys; print(hashlib.sha256(sys.stdin.buffer.read()).hexdigest())'
}

for forbidden_git_context in \
  GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES GIT_COMMON_DIR \
  GIT_DIR GIT_NAMESPACE GIT_REPLACE_REF_BASE GIT_SHALLOW_FILE; do
  if test -n "${!forbidden_git_context+x}"; then
    printf 'unsafe inherited Git object lookup context: %s\n' \
      "$forbidden_git_context" >&2
    exit 78
  fi
done

export GIT_NO_LAZY_FETCH=1
export GIT_NO_REPLACE_OBJECTS=1

exec 9>"$lock"
flock -w 120 9

seal_tool guard "$cache"
test "$(git --git-dir="$cache" rev-parse --is-bare-repository)" = true
git --git-dir="$cache" config gc.auto 0
git --git-dir="$cache" config maintenance.auto false

# No prune, repack, or gc belongs in the migration window. The only mutation is an
# atomic main-ref advance plus the objects reachable from it.
if git --git-dir="$cache" fetch --no-auto-maintenance --no-tags origin \
  +refs/heads/main:refs/heads/main; then
  :
else
  fetch_status=$?
  seal_tool invalidate "$cache"
  exit "$fetch_status"
fi

main_oid=$(git --git-dir="$cache" rev-parse --verify refs/heads/main^{commit})
lookup_context_sha256=$(
  {
    git --version &&
    git --git-dir="$cache" rev-parse --show-object-format &&
    git --git-dir="$cache" config --null --list --show-origin
  } | sha256_stream
)

if validation_receipt=$(
  seal_tool probe "$cache" "$main_oid" "$lookup_context_sha256"
); then
  printf 'CI_CACHE_VALIDATION=%s\n' "$validation_receipt"
  exit 0
else
  probe_status=$?
  if test "$probe_status" -ne 10; then
    exit "$probe_status"
  fi
fi

# A stale or malformed safe seal is made unusable before full validation. A
# fetch/scan/publication failure therefore cannot leave prior success reusable.
seal_tool invalidate "$cache"
validation_state_sha256=$(
  seal_tool fingerprint "$cache" "$main_oid" "$lookup_context_sha256"
)

# The peer seed is intentionally shallow at the audited bootstrap commit. Its
# unreachable object estate may contain inert fragments from the M2's historical
# partial clone, so whole-object-store fsck would judge objects CI cannot reach.
# Validate every object reachable from the maintained shallow main ref instead.
set +e
missing=$(
  git --git-dir="$cache" rev-list --objects --no-object-names refs/heads/main |
    git --git-dir="$cache" cat-file --batch-check |
    awk '$2 == "missing" {count += 1} END {print count + 0}'
)
scan_status=$?
set -e
if test "$scan_status" -ne 0; then
  seal_tool invalidate "$cache"
  exit "$scan_status"
fi
if test "$missing" -ne 0; then
  seal_tool invalidate "$cache"
  printf 'reachable main object validation found %s missing objects\n' "$missing" >&2
  exit 1
fi

validation_receipt=$(
  seal_tool publish \
    "$cache" "$main_oid" "$lookup_context_sha256" "$validation_state_sha256"
)
printf 'CI_CACHE_VALIDATION=%s\n' "$validation_receipt"
