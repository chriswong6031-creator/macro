"""gex_state_index tests (MSC R3.2/R3.3) — the cross-root positioning aggregate.

Pins the contracts the Terminal consumers depend on: row shape (glance-tier
fields only — no pin_probability/triggers), per-row asof dates with the index
asof = max, underscore/malformed-file exclusion, and the never-blank rule
(no rows → None, prior index left untouched by the writer).
"""

from __future__ import annotations

import json
import plistlib
from datetime import date
from io import BytesIO
from pathlib import Path

from lib.gex_state_index import SCHEMA, build_index, write_index
import scripts.mirror_gex_state_r2 as gex_mirror
from scripts.mirror_gex_state_r2 import load_bundle, public_anchors_match


def _state(root: str, **over) -> dict:
    base = {
        "schema": "options_structure.gex_state/v1",
        "asof": "2026-08-01T20:00:00+00:00",
        "root": root,
        "spot": 100.0,
        "net_gex_bn": 1.5,
        "gamma_regime": "PIN",
        "stability_pct": 82.0,
        "gamma_flip": 97.0,
        "dist_to_flip_pct": -3.0,
        "call_wall": 110.0,
        "put_wall": 90.0,
        "pin_probability": 0.61,
        "cascade_trigger": 88.0,
        "authority_tier": "display",
    }
    base.update(over)
    return base


def _write(d: Path, name: str, payload) -> None:
    (d / name).write_text(payload if isinstance(payload, str) else json.dumps(payload))


def test_index_shape_and_field_subset(tmp_path: Path) -> None:
    _write(tmp_path, "NVDA.json", _state("NVDA"))
    _write(tmp_path, "SPY.json", _state("SPY", gamma_regime="TREND", asof="2026-08-02T20:00:00+00:00"))
    idx = build_index(tmp_path)
    assert idx is not None
    assert idx["schema"] == SCHEMA
    assert idx["n_roots"] == 2
    row = idx["rows"]["NVDA"]
    assert row["gamma_regime"] == "PIN"
    assert row["call_wall"] == 110.0
    assert row["asof"] == "2026-08-01"
    # Tier-C / desk-only fields must NOT be distributed through the index.
    assert "pin_probability" not in row
    assert "cascade_trigger" not in row
    # Index asof = max of the row stamps (SPY's newer session wins).
    assert idx["asof"] == "2026-08-02T20:00:00+00:00"


def test_underscore_and_malformed_files_are_skipped(tmp_path: Path) -> None:
    _write(tmp_path, "AMD.json", _state("AMD"))
    _write(tmp_path, "_index.json", {"schema": SCHEMA, "rows": {"STALE": {}}})
    _write(tmp_path, "BROKEN.json", "{not json")
    _write(tmp_path, "NOROOT.json", {"asof": "2026-08-01T00:00:00+00:00", "spot": 5})
    idx = build_index(tmp_path)
    assert idx is not None
    assert set(idx["rows"]) == {"AMD"}


def test_missing_fields_are_omitted_not_faked(tmp_path: Path) -> None:
    s = _state("XLE")
    del s["call_wall"]
    s["put_wall"] = None
    _write(tmp_path, "XLE.json", s)
    row = build_index(tmp_path)["rows"]["XLE"]
    assert "call_wall" not in row
    assert "put_wall" not in row
    assert row["gamma_flip"] == 97.0


def test_root_key_is_uppercased(tmp_path: Path) -> None:
    _write(tmp_path, "brk-b.json", _state("brk-b"))
    assert "BRK-B" in build_index(tmp_path)["rows"]


def test_empty_dir_returns_none_and_writer_preserves_prior(tmp_path: Path) -> None:
    prior = {"schema": SCHEMA, "asof": "x", "n_roots": 1, "rows": {"OLD": {"spot": 1}}}
    _write(tmp_path, "_index.json", prior)
    assert build_index(tmp_path) is None  # _index itself never counts as a row
    assert write_index(tmp_path) is None
    # the never-blank rule: the failed aggregation left the prior file untouched
    assert json.loads((tmp_path / "_index.json").read_text()) == prior


def test_write_index_roundtrip(tmp_path: Path) -> None:
    _write(tmp_path, "QQQ.json", _state("QQQ", gamma_regime="TRANSITION"))
    out = write_index(tmp_path)
    assert out is not None and out.name == "_index.json"
    idx = json.loads(out.read_text())
    assert idx["rows"]["QQQ"]["gamma_regime"] == "TRANSITION"
    # writer output must itself be excluded on a rebuild (idempotent)
    idx2 = build_index(tmp_path)
    assert set(idx2["rows"]) == {"QQQ"}


def test_missing_dir_is_nonfatal(tmp_path: Path) -> None:
    assert write_index(tmp_path / "nope") is None


def _mirror_state(root: str, asof: str = "2026-08-10T16:00:00-04:00") -> dict:
    payload = _state(root, asof=asof)
    payload["regime_passport"] = {
        "basis": "assumption",
        "verdict": "display-only",
    }
    payload["reliability"] = {"levels": "display-only-until-gate"}
    return payload


def _write_mirror_bundle(directory: Path) -> None:
    roots = ("SPY", "QQQ", "NVDA", "AMD")
    for root in roots:
        _write(directory, f"{root}.json", _mirror_state(root))
    assert write_index(directory) == directory / "_index.json"


def test_r2_mirror_bundle_requires_fresh_liquid_roots_and_exact_index(tmp_path: Path) -> None:
    _write_mirror_bundle(tmp_path)
    bundle = load_bundle(tmp_path, expected_session=date(2026, 8, 10))
    assert bundle.roots == ("AMD", "NVDA", "QQQ", "SPY")
    assert bundle.required_roots == ("SPY", "QQQ", "NVDA")
    assert len(bundle.objects) == 5
    assert len(bundle.manifest_sha256) == 64

    _write(tmp_path, "NVDA.json", _mirror_state("NVDA", "2026-08-07T16:00:00-04:00"))
    assert write_index(tmp_path) == tmp_path / "_index.json"
    try:
        load_bundle(tmp_path, expected_session=date(2026, 8, 10))
    except ValueError as exc:
        assert "NVDA" in str(exc)
        assert "expected settled session" in str(exc)
    else:  # pragma: no cover - the fail-closed assertion above must fire.
        raise AssertionError("stale required root was accepted")


def test_r2_mirror_rejects_semantically_corrupt_index_row(tmp_path: Path) -> None:
    _write_mirror_bundle(tmp_path)
    index_path = tmp_path / "_index.json"
    index = json.loads(index_path.read_text())
    index["rows"]["AMD"]["spot"] = 999.0
    _write(tmp_path, "_index.json", index)
    try:
        load_bundle(tmp_path, expected_session=date(2026, 8, 10))
    except ValueError as exc:
        assert "deterministic per-root reconstruction" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("semantically corrupt index row was accepted")


def test_r2_mirror_preserves_display_assumption_authority(tmp_path: Path) -> None:
    _write_mirror_bundle(tmp_path)
    payload = _mirror_state("QQQ")
    payload["regime_passport"]["basis"] = "observed"
    _write(tmp_path, "QQQ.json", payload)
    try:
        load_bundle(tmp_path, expected_session=date(2026, 8, 10))
    except ValueError as exc:
        assert "dealer-sign basis is not assumption" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("non-assumption GEX state was accepted")


def test_r2_mirror_public_probe_is_byte_exact_for_anchors_and_index(tmp_path: Path) -> None:
    _write_mirror_bundle(tmp_path)
    bundle = load_bundle(tmp_path, expected_session=date(2026, 8, 10))

    def exact_fetch(url: str) -> bytes:
        name = url.split("?", 1)[0].rsplit("/", 1)[-1]
        return bundle.body(name)

    assert public_anchors_match(bundle, "https://public.example", fetch=exact_fetch)

    def stale_fetch(url: str) -> bytes:
        name = url.split("?", 1)[0].rsplit("/", 1)[-1]
        return b"stale" if name == "SPY.json" else bundle.body(name)

    assert not public_anchors_match(bundle, "https://public.example", fetch=stale_fetch)


def test_r2_mirror_publishes_complete_prefix_then_index_and_verifies(
    tmp_path: Path, monkeypatch
) -> None:
    _write_mirror_bundle(tmp_path)
    bundle = load_bundle(tmp_path, expected_session=date(2026, 8, 10))

    class FakeR2:
        def __init__(self) -> None:
            self.objects: dict[str, bytes] = {}
            self.put_order: list[str] = []

        def put_object(self, *, Bucket, Key, Body, ContentType, Metadata):  # noqa: N803
            assert Bucket == "bucket"
            assert ContentType == "application/json"
            assert Metadata["authority-tier"] == "display"
            self.objects[Key] = Body
            self.put_order.append(Key)

        def list_objects_v2(self, *, Bucket, Prefix, **_kwargs):  # noqa: N803
            assert Bucket == "bucket"
            return {
                "IsTruncated": False,
                "Contents": [
                    {"Key": key} for key in sorted(self.objects) if key.startswith(Prefix)
                ],
            }

        def get_object(self, *, Bucket, Key):  # noqa: N803
            assert Bucket == "bucket"
            return {"Body": BytesIO(self.objects[Key])}

        def delete_objects(self, *, Bucket, Delete):  # noqa: N803
            assert Bucket == "bucket"
            for row in Delete["Objects"]:
                self.objects.pop(row["Key"], None)
            return {}

    fake = FakeR2()
    monkeypatch.setattr(gex_mirror, "_r2_client", lambda: (fake, "bucket"))
    monkeypatch.setattr(gex_mirror, "public_anchors_match", lambda *_args, **_kw: True)
    monkeypatch.setattr(
        gex_mirror,
        "public_content_manifest_matches",
        lambda *_args, **_kw: True,
    )
    state_file = tmp_path / "runtime" / "state.json"

    receipt = gex_mirror.publish_bundle(
        bundle,
        public_base="https://public.example",
        state_file=state_file,
        source_commit="a" * 40,
    )
    assert receipt["status"] == "published"
    assert receipt["n_roots"] == 4
    assert receipt["source_object_count"] == 5
    assert receipt["published_object_count"] == 6
    assert receipt["direct_verified_count"] == 6
    assert receipt["public_verified"] is True
    assert fake.put_order[-2].endswith("/_index.json")
    assert fake.put_order[-1].endswith("/_content_manifest.json")
    assert len(fake.objects) == 6
    assert json.loads(state_file.read_text())["manifest_sha256"] == bundle.manifest_sha256

    # A concurrent/stale overwrite of even a non-anchor root must defeat the
    # unchanged fast path and force a complete repair.
    amd_key = f"{gex_mirror.PREFIX}/AMD.json"
    fake.objects[amd_key] = b'{"stale":true}'
    stale_extra_key = f"{gex_mirror.PREFIX}/RETIRED.json"
    fake.objects[stale_extra_key] = b'{"stale":true}'
    repaired = gex_mirror.publish_bundle(
        bundle,
        public_base="https://public.example",
        state_file=state_file,
        source_commit="a" * 40,
    )
    assert repaired["status"] == "published"
    assert fake.objects[amd_key] == bundle.body("AMD.json")
    assert stale_extra_key not in fake.objects

    unchanged = gex_mirror.publish_bundle(
        bundle,
        public_base="https://public.example",
        state_file=state_file,
        source_commit="a" * 40,
    )
    assert unchanged["status"] == "unchanged"
    assert unchanged["direct_verified_count"] == 6


def test_r2_mirror_publisher_lock_rejects_a_concurrent_writer(tmp_path: Path) -> None:
    lock = tmp_path / "publisher.lock"
    with gex_mirror.exclusive_lock(lock):
        for _attempt in range(2):
            try:
                with gex_mirror.exclusive_lock(lock):
                    raise AssertionError("concurrent publisher acquired the same lock")
            except RuntimeError as exc:
                assert "publisher lock is already held" in str(exc)


def test_gex_state_mirror_launchd_uses_clean_standalone_clone_contract() -> None:
    root = Path(__file__).parents[1]
    deploy = "/Users/chriswong/gexstate-ops-wt"
    plist = plistlib.loads(
        (root / "ops/launchd/com.mastermind.gexstate-mirror.plist").read_bytes()
    )
    assert plist["Label"] == "com.mastermind.gexstate-mirror"
    assert plist["WorkingDirectory"] == deploy
    assert plist["StartInterval"] == 900
    assert plist["RunAtLoad"] is True
    assert plist["KeepAlive"] is False
    assert all(argument.startswith(deploy) for argument in plist["ProgramArguments"])
    assert plist["EnvironmentVariables"]["PYTHONPATH"] == deploy

    runner = (root / "ops/launchd/run_gex_state_mirror.sh").read_text()
    assert 'merge --ff-only origin/main' in runner
    assert '--require-expected-session' in runner
    assert '--required-root SPY' in runner
    assert '--required-root QQQ' in runner
    assert '--required-root NVDA' in runner
    assert '--lock-file "$STATE_DIR/publisher.lock"' in runner
    assert 'rev-list -1 HEAD -- site/options_structure/gex_state' in runner
    assert 'reset --hard' not in runner
    assert 'flow-ops-wt' not in runner

    matrix_runner = (root / "ops/launchd/run_options_matrix.sh").read_text()
    assert "GEX_STATE_PUBLICATION_OWNER=com.mastermind.gexstate-mirror" in matrix_runner
    assert "options_structure/gex_state/" not in matrix_runner
    assert "s3.upload_file" not in matrix_runner

    runbook = (root / "ops/GEX_STATE_R2_MIRROR_RUNBOOK.md").read_text()
    assert "never recomputes GEX" in runbook
    assert "ranking, scoring, Prophet, sizing, or trading authority" in runbook
    assert "SPY/QQQ/NVDA" in runbook
    assert "compares every source object" in runbook
    assert "inline writer is" in runbook and "retired" in runbook
