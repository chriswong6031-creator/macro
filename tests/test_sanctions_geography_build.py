from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

import scripts.build_sanctions_geography as sanctions_builder
from collectors.ofac_sanctions import make_receipt
from engine.ofac_sanctions import ProjectionBoundsError
from scripts.build_sanctions_geography import (
    BuildUnavailableError,
    _load_previous,
    build_data,
    degraded_projection,
    render,
)


CURRENT_NS = "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/XML"


def _current_xml() -> bytes:
    return f'''<?xml version="1.0"?>
<sdnList xmlns="{CURRENT_NS}">
  <publshInformation><Publish_Date>09/03/2026</Publish_Date><Record_Count>1</Record_Count></publshInformation>
  <sdnEntry>
    <uid>101</uid><lastName>ACME SHIPPING</lastName><sdnType>Entity</sdnType>
    <programList><program>TEST-PROGRAM</program></programList>
    <addressList><address><uid>501</uid><city>New York</city><country>United States</country></address></addressList>
  </sdnEntry>
</sdnList>'''.encode()


def _receipt(key: str, body: bytes) -> dict:
    return make_receipt(
        source_key=key,
        requested_url="https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN.XML",
        final_url="https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN.XML",
        payload=body,
        acquired_at="2026-09-04T09:00:00Z",
        published_at="2026-09-03T00:00:00Z",
        schema_revision=CURRENT_NS,
        rights_url="https://ofac.treasury.gov/sanctions-list-service",
    )


def _root(tmp_path: Path) -> Path:
    site = tmp_path / "site"
    site.mkdir()
    topology = {
        "type": "Topology",
        "objects": {
            "countries": {
                "type": "GeometryCollection",
                "geometries": [
                    {"type": "Polygon", "id": "840", "properties": {"name": "United States of America"}}
                ],
            }
        },
        "arcs": [],
    }
    (site / "world-110m.json").write_text(json.dumps(topology), encoding="utf-8")
    return tmp_path


def _bundle() -> dict:
    body = _current_xml()
    return {
        "current_xml": body,
        "current_receipt": _receipt("ofac_sdn_current", body),
        "schema_receipts": [],
        "delta_documents": [],
    }


def test_build_data_writes_bounded_machine_consumer_and_reuses_last_good_bytes(tmp_path: Path) -> None:
    root = _root(tmp_path)
    output = build_data(root=root, bundle=_bundle(), as_of="2026-09-04T09:30:00Z")
    first = output.read_bytes()
    payload = json.loads(first)
    assert output == root / "site" / "sanctions-geography-data.json"
    assert payload["schema_version"] == "mastermind.sanctions_geography.v1"
    assert payload["capability_state"] == "BUILT_NOT_PROVEN"
    assert payload["production_state"] == "PRODUCTION_INERT"
    assert payload["method"]["geography_basis"] == "published_address_country_only"
    assert payload["summary"]["current_entries"] == 1
    assert payload["countries"][0]["geo_id"] == "840"
    assert "entries" not in payload, "the first-load consumer must not carry the full entry corpus"
    shard_record = payload["entry_shards"]["by_geo"]["840"]
    assert shard_record["path"] == "sanctions-geography-entries/840.json"
    shard_path = root / "site" / shard_record["path"]
    assert shard_path.stat().st_size == shard_record["bytes"]
    assert hashlib.sha256(shard_path.read_bytes()).hexdigest() == shard_record["sha256"]
    shard = json.loads(shard_path.read_text())
    assert shard["projection_id"] == payload["projection_id"]
    assert shard["source_identity"] == payload["source_identity"]
    assert [entry["uid"] for entry in shard["entries"]] == ["101"]
    assert len(shard["entries"]) == shard_record["entries"]
    assert _load_previous(output)["entries"][0]["uid"] == "101"
    assert len(first) < 20_000

    later = _bundle()
    later["current_receipt"]["acquired_at"] = "2026-09-04T10:00:00Z"
    build_data(root=root, bundle=later, as_of="2026-09-04T10:00:00Z")
    assert output.read_bytes() == first
    assert hashlib.sha256(output.read_bytes()).hexdigest() == hashlib.sha256(first).hexdigest()


def test_last_good_reconstruction_fails_closed_on_tampered_shard(tmp_path: Path) -> None:
    root = _root(tmp_path)
    output = build_data(root=root, bundle=_bundle(), as_of="2026-09-04T09:30:00Z")
    payload = json.loads(output.read_text(encoding="utf-8"))
    shard = root / "site" / payload["entry_shards"]["by_geo"]["840"]["path"]
    shard.write_bytes(shard.read_bytes() + b" ")
    with pytest.raises(BuildUnavailableError, match="byte count mismatch"):
        _load_previous(output)


def test_build_removes_only_stale_owned_shards(tmp_path: Path) -> None:
    root = _root(tmp_path)
    shard_dir = root / "site" / "sanctions-geography-entries"
    shard_dir.mkdir()
    stale = shard_dir / "999.json"
    stale.write_text("stale", encoding="utf-8")
    foreign = shard_dir / "README.txt"
    foreign.write_text("keep", encoding="utf-8")
    build_data(root=root, bundle=_bundle(), as_of="2026-09-04T09:30:00Z")
    assert not stale.exists()
    assert foreign.read_text(encoding="utf-8") == "keep"


def test_degraded_projection_keeps_last_good_facts_and_exposes_failure_state(tmp_path: Path) -> None:
    root = _root(tmp_path)
    output = build_data(root=root, bundle=_bundle(), as_of="2026-09-04T09:30:00Z")
    last_good = _load_previous(output)
    assert last_good is not None
    degraded = degraded_projection(last_good, state="SOURCE_UNAVAILABLE", error_code="official_source_timeout")
    assert degraded["source_state"] == "SOURCE_UNAVAILABLE"
    assert degraded["degraded"]["last_good_projection_id"] == last_good["projection_id"]
    assert degraded["entries"] == last_good["entries"]
    assert degraded["summary"] == last_good["summary"]
    assert "traceback" not in json.dumps(degraded).casefold()


def test_degraded_projection_refuses_empty_success_without_last_good() -> None:
    with pytest.raises(BuildUnavailableError, match="no last-good"):
        degraded_projection(None, state="SOURCE_UNAVAILABLE", error_code="official_source_timeout")


def test_projection_bound_failure_becomes_a_named_last_good_degraded_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _root(tmp_path)
    output = build_data(root=root, bundle=_bundle(), as_of="2026-09-04T09:30:00Z")

    def bounded_failure(**_kwargs):
        raise ProjectionBoundsError("synthetic reviewed bound")

    rendered: dict = {}

    def capture_render(_root: Path, projection: dict) -> Path:
        rendered.update(projection)
        return _root / "site" / "sanctions-geography.html"

    monkeypatch.setattr(sanctions_builder, "build_data", bounded_failure)
    monkeypatch.setattr(sanctions_builder, "render", capture_render)
    rebuilt, page = sanctions_builder.build(root=root, bundle=_bundle())
    assert rebuilt == output
    assert page == root / "site" / "sanctions-geography.html"
    degraded = json.loads(output.read_text())
    assert degraded["source_state"] == "PARSER_SHAPE_CHANGED"
    assert degraded["degraded"]["error_code"].startswith("ProjectionBoundsError:")
    assert rendered["source_state"] == "PARSER_SHAPE_CHANGED"


def test_build_has_no_data_only_split_that_can_break_page_projection_parity() -> None:
    import inspect

    assert "data_only" not in inspect.signature(sanctions_builder.build).parameters
    assert "--data-only" not in inspect.getsource(sanctions_builder.main)


def test_build_data_rejects_tampered_boundary_receipt(tmp_path: Path) -> None:
    root = _root(tmp_path)
    with pytest.raises(BuildUnavailableError, match="boundary SHA-256"):
        build_data(
            root=root,
            bundle=_bundle(),
            as_of="2026-09-04T09:30:00Z",
            expected_boundary_sha256="0" * 64,
        )


def test_render_emits_only_the_canonical_hyphenated_page_and_exact_assets(tmp_path: Path) -> None:
    root = _root(tmp_path)
    source_templates = Path(__file__).resolve().parents[1] / "templates"
    templates = root / "templates"
    templates.mkdir()
    for name in (
        "sanctions_geography.html.j2",
        "sanctions_geography.css",
        "sanctions_geography.js",
        "_site_nav.html.j2",
        "_navlinks.html.j2",
        "_seo_head.html.j2",
    ):
        shutil.copyfile(source_templates / name, templates / name)

    page = render(
        root,
        {
            "source_state": "CURRENT",
            "projection_id": "sha256:test-projection",
        },
    )

    assert page == root / "site" / "sanctions-geography.html"
    assert page.is_file()
    assert not (root / "site" / "sanctions_geography.html").exists()
    for source_name, site_name in (
        ("sanctions_geography.css", "sanctions-geography.css"),
        ("sanctions_geography.js", "sanctions-geography.js"),
    ):
        assert (root / "site" / site_name).read_bytes() == (
            root / "templates" / source_name
        ).read_bytes()
        assert not (root / "site" / source_name).exists()
