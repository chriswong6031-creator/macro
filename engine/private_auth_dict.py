"""Insert-only content-addressed Patricia dictionary for private runtimes.

The dictionary makes deterministic-path membership and non-membership part of
the transactional HEAD.  Mutable filename indexes may remain as accelerators,
but never carry authority.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, NoReturn

SCHEMA = "private.auth_dict_node/v1"
ROOT_SCHEMA = "private.auth_dict_root/v1"
ALGORITHM = "sha256-patricia-msb/v1"
SHARDED_ALGORITHM = "sha256-sharded-sorted/v1"
NAMESPACE = "auth_dict_nodes"
MAX_DEPTH = 256
SHARD_COUNT = 256

_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_NODE_RE = re.compile(r"^padn_[0-9a-f]{64}$")


class AuthDictError(RuntimeError):
    pass


def _fail(message: str) -> NoReturn:
    raise AuthDictError(message)


def canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise AuthDictError("auth dictionary value is not canonical JSON") from exc


def key_sha256(logical_key: Any, *, domain: str) -> str:
    return hashlib.sha256(canonical_bytes([domain, logical_key])).hexdigest()


def _node_id(value: Mapping[str, Any]) -> str:
    payload = copy.deepcopy(dict(value))
    payload["node_id"] = ""
    domain = payload.get("domain")
    return (
        "padn_"
        + hashlib.sha256(
            canonical_bytes(["private_auth_dict_node", domain, payload])
        ).hexdigest()
    )


def pointer(value: Mapping[str, Any]) -> dict[str, Any]:
    body = canonical_bytes(value)
    node_id = value.get("node_id")
    if not isinstance(node_id, str) or _NODE_RE.fullmatch(node_id) is None:
        _fail("auth dictionary node identity is malformed")
    return {
        "id": node_id,
        "key": f"{NAMESPACE}/{node_id}.json",
        "sha256": hashlib.sha256(body).hexdigest(),
        "bytes": len(body),
    }


def _validate_pointer(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {
        "id",
        "key",
        "sha256",
        "bytes",
    }:
        _fail("auth dictionary pointer fields are malformed")
    clean = copy.deepcopy(dict(value))
    if (
        not isinstance(clean["id"], str)
        or _NODE_RE.fullmatch(clean["id"]) is None
        or clean["key"] != f"{NAMESPACE}/{clean['id']}.json"
        or not isinstance(clean["sha256"], str)
        or _SHA_RE.fullmatch(clean["sha256"]) is None
        or type(clean["bytes"]) is not int
        or not 0 < clean["bytes"] <= 8 * 1024 * 1024
    ):
        _fail("auth dictionary pointer is malformed")
    return clean


def validate_node(value: Any, *, domain: str | None = None) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        _fail("auth dictionary node is not an object")
    clean = copy.deepcopy(dict(value))
    common = {"schema", "node_id", "kind", "domain", "authority"}
    node_domain = clean.get("domain")
    if (
        not isinstance(node_domain, str)
        or not re.fullmatch(r"[a-z0-9_.:/-]{1,120}", node_domain)
        or (domain is not None and node_domain != domain)
    ):
        _fail("auth dictionary node domain drifted")
    kind = clean.get("kind")
    if kind == "leaf":
        if set(clean) != common | {"key_sha256", "logical_key", "binding"}:
            _fail("auth dictionary leaf fields are malformed")
        if (
            not isinstance(clean.get("key_sha256"), str)
            or _SHA_RE.fullmatch(clean["key_sha256"]) is None
            or clean["key_sha256"]
            != key_sha256(clean["logical_key"], domain=node_domain)
        ):
            _fail("auth dictionary leaf key is malformed")
    elif kind == "branch":
        if set(clean) != common | {"bit", "left", "right"}:
            _fail("auth dictionary branch fields are malformed")
        if type(clean.get("bit")) is not int or not 0 <= clean["bit"] < MAX_DEPTH:
            _fail("auth dictionary branch bit is malformed")
        clean["left"] = _validate_pointer(clean["left"])
        clean["right"] = _validate_pointer(clean["right"])
        if clean["left"] == clean["right"]:
            _fail("auth dictionary branch children are identical")
    elif kind == "bucket":
        if set(clean) != common | {"shard", "entries"}:
            _fail("auth dictionary bucket fields are malformed")
        shard = clean.get("shard")
        entries = clean.get("entries")
        if (
            not isinstance(shard, str)
            or re.fullmatch(r"[0-9a-f]{2}", shard) is None
            or not isinstance(entries, list)
        ):
            _fail("auth dictionary bucket is malformed")
        prior: tuple[str, bytes] | None = None
        for entry in entries:
            if not isinstance(entry, Mapping) or set(entry) != {
                "key_sha256",
                "logical_key",
                "binding",
            }:
                _fail("auth dictionary bucket entry is malformed")
            digest = entry.get("key_sha256")
            if (
                not isinstance(digest, str)
                or _SHA_RE.fullmatch(digest) is None
                or not digest.startswith(shard)
                or digest
                != key_sha256(entry.get("logical_key"), domain=node_domain)
            ):
                _fail("auth dictionary bucket key is malformed")
            order = (digest, canonical_bytes(entry.get("logical_key")))
            if prior is not None and order <= prior:
                _fail("auth dictionary bucket is not strictly ordered")
            prior = order
    elif kind == "directory":
        if set(clean) != common | {"buckets", "entry_count"}:
            _fail("auth dictionary directory fields are malformed")
        buckets = clean.get("buckets")
        if (
            not isinstance(buckets, list)
            or len(buckets) != SHARD_COUNT
            or type(clean.get("entry_count")) is not int
            or clean["entry_count"] < 1
        ):
            _fail("auth dictionary directory is malformed")
        clean["buckets"] = [
            None if item is None else _validate_pointer(item) for item in buckets
        ]
    else:
        _fail("auth dictionary node kind is malformed")
    if (
        clean.get("schema") != SCHEMA
        or clean.get("authority") is not False
        or not isinstance(clean.get("node_id"), str)
        or _NODE_RE.fullmatch(clean["node_id"]) is None
        or clean["node_id"] != _node_id(clean)
    ):
        _fail("auth dictionary node identity is malformed")
    return clean


def root_receipt(
    *, domain: str, root: Mapping[str, Any] | None, entry_count: int
) -> dict[str, Any]:
    if (
        not isinstance(domain, str)
        or not re.fullmatch(r"[a-z0-9_.:/-]{1,120}", domain)
        or type(entry_count) is not int
        or entry_count < 0
        or (entry_count == 0) != (root is None)
    ):
        _fail("auth dictionary root receipt is malformed")
    return {
        "schema": ROOT_SCHEMA,
        "algorithm": ALGORITHM,
        "domain": domain,
        "root": None if root is None else _validate_pointer(root),
        "entry_count": entry_count,
    }


def validate_root(value: Any, *, domain: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {
        "schema",
        "algorithm",
        "domain",
        "root",
        "entry_count",
    }:
        _fail("auth dictionary root receipt fields are malformed")
    if (
        value.get("schema") != ROOT_SCHEMA
        or value.get("algorithm") != ALGORITHM
        or value.get("domain") != domain
    ):
        _fail("auth dictionary algorithm drifted")
    return root_receipt(
        domain=domain,
        root=value.get("root"),
        entry_count=value.get("entry_count"),
    )


def sharded_root_receipt(
    *, domain: str, root: Mapping[str, Any] | None, entry_count: int
) -> dict[str, Any]:
    clean = root_receipt(domain=domain, root=root, entry_count=entry_count)
    clean["algorithm"] = SHARDED_ALGORITHM
    return clean


def validate_sharded_root(value: Any, *, domain: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {
        "schema",
        "algorithm",
        "domain",
        "root",
        "entry_count",
    }:
        _fail("auth dictionary root receipt fields are malformed")
    if (
        value.get("schema") != ROOT_SCHEMA
        or value.get("algorithm") != SHARDED_ALGORITHM
        or value.get("domain") != domain
    ):
        _fail("auth dictionary sharded algorithm drifted")
    return sharded_root_receipt(
        domain=domain,
        root=value.get("root"),
        entry_count=value.get("entry_count"),
    )


def _bit(digest: str, index: int) -> int:
    return (int(digest[index // 4], 16) >> (3 - (index % 4))) & 1


def _first_differing_bit(left: str, right: str) -> int:
    if left == right:
        _fail("auth dictionary logical-key digest collision")
    for index in range(MAX_DEPTH):
        if _bit(left, index) != _bit(right, index):
            return index
    _fail("auth dictionary digest collision is impossible")


LoadNode = Callable[[Mapping[str, Any]], Mapping[str, Any]]


@dataclass(frozen=True)
class Lookup:
    found: bool
    binding: Any | None
    terminal: dict[str, Any] | None
    path: tuple[tuple[dict[str, Any], int], ...]


@dataclass
class ShardedLookupCache:
    """Ephemeral cache of nodes fully authenticated in this process."""

    domain: str
    nodes: dict[str, dict[str, Any]]

    @classmethod
    def empty(cls, domain: str) -> "ShardedLookupCache":
        if not isinstance(domain, str) or not re.fullmatch(
            r"[a-z0-9_.:/-]{1,120}", domain
        ):
            _fail("auth dictionary cache domain is malformed")
        return cls(domain=domain, nodes={})


def lookup(
    receipt: Mapping[str, Any],
    logical_key: Any,
    *,
    domain: str,
    load_node: LoadNode,
) -> Lookup:
    clean_root = validate_root(receipt, domain=domain)
    current = clean_root["root"]
    if current is None:
        return Lookup(False, None, None, ())
    digest = key_sha256(logical_key, domain=domain)
    path: list[tuple[dict[str, Any], int]] = []
    prior_bit = -1
    while True:
        clean_pointer = _validate_pointer(current)
        node = validate_node(load_node(clean_pointer), domain=domain)
        if pointer(node) != clean_pointer:
            _fail("auth dictionary pointer bytes drifted")
        if node["kind"] == "leaf":
            logical_bytes = canonical_bytes(logical_key)
            found = (
                node["key_sha256"] == digest
                and canonical_bytes(node["logical_key"]) == logical_bytes
            )
            if node["key_sha256"] == digest and not found:
                _fail("auth dictionary logical-key digest collision")
            return Lookup(
                found,
                copy.deepcopy(node["binding"]) if found else None,
                node,
                tuple(path),
            )
        branch_bit = node["bit"]
        if branch_bit <= prior_bit:
            _fail("auth dictionary branch bits are not strictly increasing")
        direction = _bit(digest, branch_bit)
        path.append((node, direction))
        current = node["right"] if direction else node["left"]
        prior_bit = branch_bit


def _leaf(logical_key: Any, binding: Any, *, domain: str) -> dict[str, Any]:
    node = {
        "schema": SCHEMA,
        "node_id": "",
        "kind": "leaf",
        "domain": domain,
        "key_sha256": key_sha256(logical_key, domain=domain),
        "logical_key": copy.deepcopy(logical_key),
        "binding": copy.deepcopy(binding),
        "authority": False,
    }
    node["node_id"] = _node_id(node)
    return validate_node(node, domain=domain)


def _branch(
    bit: int,
    left: Mapping[str, Any],
    right: Mapping[str, Any],
    *,
    domain: str,
) -> dict[str, Any]:
    node = {
        "schema": SCHEMA,
        "node_id": "",
        "kind": "branch",
        "domain": domain,
        "bit": bit,
        "left": _validate_pointer(left),
        "right": _validate_pointer(right),
        "authority": False,
    }
    node["node_id"] = _node_id(node)
    return validate_node(node, domain=domain)


def _bucket(
    shard: str, entries: Sequence[Mapping[str, Any]], *, domain: str
) -> dict[str, Any]:
    node = {
        "schema": SCHEMA,
        "node_id": "",
        "kind": "bucket",
        "domain": domain,
        "shard": shard,
        "entries": [copy.deepcopy(dict(item)) for item in entries],
        "authority": False,
    }
    node["node_id"] = _node_id(node)
    return validate_node(node, domain=domain)


def _directory(
    buckets: Sequence[Mapping[str, Any] | None],
    *,
    entry_count: int,
    domain: str,
) -> dict[str, Any]:
    node = {
        "schema": SCHEMA,
        "node_id": "",
        "kind": "directory",
        "domain": domain,
        "buckets": [
            None if item is None else copy.deepcopy(dict(item)) for item in buckets
        ],
        "entry_count": entry_count,
        "authority": False,
    }
    node["node_id"] = _node_id(node)
    return validate_node(node, domain=domain)


def _load_sharded_directory(
    receipt: Mapping[str, Any],
    *,
    domain: str,
    load_node: LoadNode,
    cache: ShardedLookupCache | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any] | None]]:
    clean_root = validate_sharded_root(receipt, domain=domain)
    if clean_root["root"] is None:
        return clean_root, [None] * SHARD_COUNT
    if cache is not None and cache.domain != domain:
        _fail("auth dictionary cache crossed domains")
    root_pointer = clean_root["root"]
    identity = root_pointer["id"]
    directory = None if cache is None else cache.nodes.get(identity)
    if directory is None:
        directory = validate_node(load_node(root_pointer), domain=domain)
        if pointer(directory) != root_pointer:
            _fail("auth dictionary sharded directory pointer drifted")
        if cache is not None:
            cache.nodes[identity] = directory
    elif pointer(directory) != root_pointer:
        _fail("auth dictionary cached directory pointer drifted")
    if directory["kind"] != "directory" or directory["entry_count"] != clean_root[
        "entry_count"
    ]:
        _fail("auth dictionary sharded directory drifted")
    return clean_root, list(directory["buckets"])


def sharded_lookup(
    receipt: Mapping[str, Any],
    logical_key: Any,
    *,
    domain: str,
    load_node: LoadNode,
    cache: ShardedLookupCache | None = None,
) -> Lookup:
    _clean_root, buckets = _load_sharded_directory(
        receipt, domain=domain, load_node=load_node, cache=cache
    )
    digest = key_sha256(logical_key, domain=domain)
    bucket_pointer = buckets[int(digest[:2], 16)]
    if bucket_pointer is None:
        return Lookup(False, None, None, ())
    identity = bucket_pointer["id"]
    bucket = None if cache is None else cache.nodes.get(identity)
    if bucket is None:
        bucket = validate_node(load_node(bucket_pointer), domain=domain)
        if pointer(bucket) != bucket_pointer:
            _fail("auth dictionary sharded bucket pointer drifted")
        if cache is not None:
            cache.nodes[identity] = bucket
    elif pointer(bucket) != bucket_pointer:
        _fail("auth dictionary cached bucket pointer drifted")
    if bucket["kind"] != "bucket" or bucket["shard"] != digest[:2]:
        _fail("auth dictionary sharded bucket drifted")
    logical_bytes = canonical_bytes(logical_key)
    target = (digest, logical_bytes)
    for entry in bucket["entries"]:
        order = (entry["key_sha256"], canonical_bytes(entry["logical_key"]))
        if order == target:
            return Lookup(True, copy.deepcopy(entry["binding"]), bucket, ())
        if order > target:
            break
    return Lookup(False, None, bucket, ())


def sharded_insert_many(
    receipt: Mapping[str, Any],
    entries: Sequence[tuple[Any, Any]],
    *,
    domain: str,
    load_node: LoadNode,
    replace_existing: bool | Callable[[Any], bool] = False,
    cache: ShardedLookupCache | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Insert a batch by rewriting only touched 8-bit hash buckets."""

    if len(entries) > 4096:
        _fail("auth dictionary insertion batch exceeds 4096 entries")
    current, bucket_pointers = _load_sharded_directory(
        receipt, domain=domain, load_node=load_node, cache=cache
    )
    pending: dict[int, list[tuple[str, bytes, bytes, Any, Any]]] = {}
    for logical_key, binding in entries:
        digest = key_sha256(logical_key, domain=domain)
        pending.setdefault(int(digest[:2], 16), []).append(
            (
                digest,
                canonical_bytes(logical_key),
                canonical_bytes(binding),
                logical_key,
                binding,
            )
        )
    created: list[dict[str, Any]] = []
    entry_count = current["entry_count"]
    for shard_index in sorted(pending):
        prior_pointer = bucket_pointers[shard_index]
        prior_entries: list[dict[str, Any]] = []
        if prior_pointer is not None:
            identity = prior_pointer["id"]
            prior_bucket = None if cache is None else cache.nodes.get(identity)
            if prior_bucket is None:
                prior_bucket = validate_node(load_node(prior_pointer), domain=domain)
                if pointer(prior_bucket) != prior_pointer:
                    _fail("auth dictionary sharded bucket pointer drifted")
                if cache is not None:
                    cache.nodes[identity] = prior_bucket
            elif pointer(prior_bucket) != prior_pointer:
                _fail("auth dictionary cached bucket pointer drifted")
            if (
                prior_bucket["kind"] != "bucket"
                or prior_bucket["shard"] != f"{shard_index:02x}"
            ):
                _fail("auth dictionary sharded bucket drifted")
            prior_entries = [copy.deepcopy(item) for item in prior_bucket["entries"]]
        by_key = {
            (item["key_sha256"], canonical_bytes(item["logical_key"])): item
            for item in prior_entries
        }
        seen: dict[tuple[str, bytes], bytes] = {}
        for digest, logical_bytes, binding_bytes, logical_key, binding in sorted(
            pending[shard_index], key=lambda item: (item[0], item[1], item[2])
        ):
            key = (digest, logical_bytes)
            allow_replace = (
                replace_existing(logical_key)
                if callable(replace_existing)
                else replace_existing
            )
            prior_binding = seen.get(key)
            if prior_binding is not None and prior_binding != binding_bytes:
                if not allow_replace:
                    _fail("auth dictionary batch repeats a key with conflicting binding")
            seen[key] = binding_bytes
            existing = by_key.get(key)
            if existing is not None:
                if canonical_bytes(existing["binding"]) == binding_bytes:
                    continue
                if not allow_replace:
                    _fail("auth dictionary key already has a conflicting binding")
            else:
                entry_count += 1
            by_key[key] = {
                "key_sha256": digest,
                "logical_key": copy.deepcopy(logical_key),
                "binding": copy.deepcopy(binding),
            }
        bucket = _bucket(
            f"{shard_index:02x}",
            [by_key[key] for key in sorted(by_key)],
            domain=domain,
        )
        bucket_pointers[shard_index] = pointer(bucket)
        created.append(bucket)
    if entry_count == 0:
        return sharded_root_receipt(domain=domain, root=None, entry_count=0), []
    directory = _directory(
        bucket_pointers, entry_count=entry_count, domain=domain
    )
    created.append(directory)
    return (
        sharded_root_receipt(
            domain=domain, root=pointer(directory), entry_count=entry_count
        ),
        created,
    )


def insert_many(
    receipt: Mapping[str, Any],
    entries: Sequence[tuple[Any, Any]],
    *,
    domain: str,
    load_node: LoadNode,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Insert a deterministic batch and return a new root plus reachable nodes."""

    current = validate_root(receipt, domain=domain)
    base_count = current["entry_count"]
    if len(entries) > 4096:
        _fail("auth dictionary insertion batch exceeds 4096 entries")
    overlay: dict[str, dict[str, Any]] = {}
    loaded: dict[str, Mapping[str, Any]] = {}

    def load(pointer_value: Mapping[str, Any]) -> Mapping[str, Any]:
        node_id = str(pointer_value.get("id"))
        if node_id in overlay:
            return overlay[node_id]
        if node_id not in loaded:
            loaded[node_id] = load_node(pointer_value)
        return loaded[node_id]

    ordered = sorted(
        (
            (
                key_sha256(logical_key, domain=domain),
                canonical_bytes(logical_key),
                canonical_bytes(binding),
                logical_key,
                binding,
            )
            for logical_key, binding in entries
        ),
        key=lambda item: (item[0], item[1], item[2]),
    )
    seen: dict[str, tuple[bytes, bytes]] = {}
    inserted = 0
    for digest, logical_bytes, binding_bytes, logical_key, binding in ordered:
        prior = seen.get(digest)
        if prior is not None:
            if prior[0] != logical_bytes:
                _fail("auth dictionary logical-key digest collision")
            if prior[1] != binding_bytes:
                _fail("auth dictionary batch repeats a key with conflicting binding")
            continue
        seen[digest] = (logical_bytes, binding_bytes)
        existing = lookup(current, logical_key, domain=domain, load_node=load)
        if existing.found:
            if canonical_bytes(existing.binding) != binding_bytes:
                _fail("auth dictionary key already has a conflicting binding")
            continue
        new_leaf = _leaf(logical_key, binding, domain=domain)
        overlay[new_leaf["node_id"]] = new_leaf
        if existing.terminal is None:
            current = root_receipt(domain=domain, root=pointer(new_leaf), entry_count=1)
            inserted += 1
            continue
        terminal = existing.terminal
        split_bit = _first_differing_bit(digest, terminal["key_sha256"])
        full_path = list(existing.path)
        insertion_index = 0
        while (
            insertion_index < len(full_path)
            and full_path[insertion_index][0]["bit"] < split_bit
        ):
            insertion_index += 1
        if (
            insertion_index < len(full_path)
            and full_path[insertion_index][0]["bit"] == split_bit
        ):
            _fail("auth dictionary split bit already exists on search path")
        parent_path = full_path[:insertion_index]
        displaced_pointer = (
            pointer(terminal)
            if insertion_index == len(full_path)
            else pointer(full_path[insertion_index][0])
        )
        if _bit(digest, split_bit):
            split = _branch(
                split_bit, displaced_pointer, pointer(new_leaf), domain=domain
            )
        else:
            split = _branch(
                split_bit, pointer(new_leaf), displaced_pointer, domain=domain
            )
        overlay[split["node_id"]] = split
        child_pointer = pointer(split)
        for branch, direction in reversed(parent_path):
            left = child_pointer if direction == 0 else branch["left"]
            right = child_pointer if direction == 1 else branch["right"]
            rebuilt = _branch(branch["bit"], left, right, domain=domain)
            overlay[rebuilt["node_id"]] = rebuilt
            child_pointer = pointer(rebuilt)
        current = root_receipt(
            domain=domain,
            root=child_pointer,
            entry_count=current["entry_count"] + 1,
        )
        inserted += 1

    # Only nodes reachable from the final root need publication. This discards
    # intermediate path-copy roots built while applying a large batch.
    reachable: dict[str, dict[str, Any]] = {}

    def collect(pointer_value: Mapping[str, Any] | None) -> None:
        if pointer_value is None or pointer_value["id"] in reachable:
            return
        node = validate_node(load(pointer_value), domain=domain)
        if node["node_id"] not in overlay:
            return
        reachable[node["node_id"]] = node
        if node["kind"] == "branch":
            collect(node["left"])
            collect(node["right"])

    collect(current["root"])
    if current["entry_count"] != base_count + inserted:
        _fail("auth dictionary entry count drifted during insertion")
    return current, [reachable[key] for key in sorted(reachable)]


__all__ = [
    "ALGORITHM",
    "NAMESPACE",
    "ROOT_SCHEMA",
    "SCHEMA",
    "SHARDED_ALGORITHM",
    "ShardedLookupCache",
    "AuthDictError",
    "canonical_bytes",
    "insert_many",
    "key_sha256",
    "lookup",
    "pointer",
    "root_receipt",
    "sharded_insert_many",
    "sharded_lookup",
    "sharded_root_receipt",
    "validate_node",
    "validate_root",
    "validate_sharded_root",
]
