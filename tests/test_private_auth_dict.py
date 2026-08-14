from __future__ import annotations

import copy

import pytest

from engine import private_auth_dict as auth


DOMAIN = "test.auth_dict/v1"


def _store(nodes: list[dict]) -> dict[str, dict]:
    return {node["node_id"]: copy.deepcopy(node) for node in nodes}


def _load(store: dict[str, dict]):
    return lambda pointer: copy.deepcopy(store[pointer["id"]])


def test_patricia_insert_only_conflict_and_authenticated_nonmembership() -> None:
    root = auth.root_receipt(domain=DOMAIN, root=None, entry_count=0)
    root, nodes = auth.insert_many(
        root,
        [(["alpha"], {"value": 1}), (["beta"], {"value": 2})],
        domain=DOMAIN,
        load_node=lambda _pointer: (_ for _ in ()).throw(AssertionError()),
    )
    store = _store(nodes)
    assert auth.lookup(root, ["alpha"], domain=DOMAIN, load_node=_load(store)).binding == {
        "value": 1
    }
    missing = auth.lookup(root, ["gamma"], domain=DOMAIN, load_node=_load(store))
    assert missing.found is False and missing.terminal is not None and missing.path
    with pytest.raises(auth.AuthDictError, match="conflicting binding"):
        auth.insert_many(
            root,
            [(["alpha"], {"value": 9})],
            domain=DOMAIN,
            load_node=_load(store),
        )


def test_sharded_insert_lookup_and_binding_copy_isolation() -> None:
    root = auth.sharded_root_receipt(domain=DOMAIN, root=None, entry_count=0)
    root, nodes = auth.sharded_insert_many(
        root,
        [(["alpha"], {"nested": [1]}), (["beta"], {"nested": [2]})],
        domain=DOMAIN,
        load_node=lambda _pointer: (_ for _ in ()).throw(AssertionError()),
    )
    store = _store(nodes)
    cache = auth.ShardedLookupCache.empty(DOMAIN)
    first = auth.sharded_lookup(
        root, ["alpha"], domain=DOMAIN, load_node=_load(store), cache=cache
    )
    assert first.found is True
    first.binding["nested"].append(9)
    second = auth.sharded_lookup(
        root, ["alpha"], domain=DOMAIN, load_node=_load(store), cache=cache
    )
    assert second.binding == {"nested": [1]}
    assert auth.sharded_lookup(
        root, ["missing"], domain=DOMAIN, load_node=_load(store), cache=cache
    ).found is False


@pytest.mark.parametrize("operation", ["lookup", "insert"])
@pytest.mark.parametrize("target", ["directory", "bucket"])
def test_sharded_cache_rejects_same_id_pointer_drift(
    operation: str, target: str
) -> None:
    logical_key = ["alpha"]
    root = auth.sharded_root_receipt(domain=DOMAIN, root=None, entry_count=0)
    root, nodes = auth.sharded_insert_many(
        root,
        [(logical_key, {"value": 1})],
        domain=DOMAIN,
        load_node=lambda _pointer: (_ for _ in ()).throw(AssertionError()),
    )
    store = _store(nodes)
    cache = auth.ShardedLookupCache.empty(DOMAIN)
    assert auth.sharded_lookup(
        root, logical_key, domain=DOMAIN, load_node=_load(store), cache=cache
    ).found
    forged_root = copy.deepcopy(root)
    if target == "directory":
        forged_root["root"]["sha256"] = "0" * 64
        match = "cached directory pointer drifted"
    else:
        directory = store[root["root"]["id"]]
        shard = int(auth.key_sha256(logical_key, domain=DOMAIN)[:2], 16)
        directory["buckets"][shard]["sha256"] = "0" * 64
        forged_directory = copy.deepcopy(directory)
        forged_directory["node_id"] = ""
        forged_directory["node_id"] = auth._node_id(forged_directory)
        store[forged_directory["node_id"]] = forged_directory
        forged_root["root"] = auth.pointer(forged_directory)
        cache.nodes[forged_directory["node_id"]] = forged_directory
        match = "cached bucket pointer drifted"
    with pytest.raises(auth.AuthDictError, match=match):
        if operation == "lookup":
            auth.sharded_lookup(
                forged_root,
                logical_key,
                domain=DOMAIN,
                load_node=_load(store),
                cache=cache,
            )
        else:
            auth.sharded_insert_many(
                forged_root,
                [(["new"], {"value": 2}), (logical_key, {"value": 1})],
                domain=DOMAIN,
                load_node=_load(store),
                cache=cache,
            )
