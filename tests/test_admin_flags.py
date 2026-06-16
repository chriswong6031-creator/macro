"""admin.flags — registry integrity against the real config.yml."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from admin import config_store, flags


def test_every_managed_flag_resolves_to_a_bool_in_config():
    """Catches a typo'd dotted path in the registry: each managed flag must point at
    an actual boolean in config.yml (all our toggles are on/off booleans)."""
    cfg = config_store.read_config()
    bad = []
    for f in flags.FLAGS:
        v = config_store.get_value(f["path"], cfg)
        if not isinstance(v, bool):
            bad.append((f["path"], v))
    assert not bad, f"flag paths not resolving to a bool: {bad}"


def test_flag_registry_shape():
    for f in flags.FLAGS:
        assert f["path"] and "." in f["path"]
        assert f["label"] and f["note"]
        assert isinstance(f.get("requires", []), list)
        assert f["category"]


def test_snapshot_groups_and_inert_detection():
    snap = flags.snapshot()
    assert snap["order"] and snap["groups"]
    rows = [r for g in snap["groups"].values() for r in g]
    assert len(rows) == len(flags.FLAGS)
    for r in rows:
        # inert == ON but a required secret is missing
        assert r["inert"] == (bool(r["value"]) and bool(r["missing_secrets"]))


if __name__ == "__main__":
    for fn in [v for k, v in sorted(globals().items()) if k.startswith("test_")]:
        fn(); print("PASS", fn.__name__)
