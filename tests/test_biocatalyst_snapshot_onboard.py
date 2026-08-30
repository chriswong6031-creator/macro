from __future__ import annotations

from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path

from openpyxl import Workbook
import pandas as pd

from engine.biocatalyst.storage import BinaryObjectStore
from engine.biocatalyst.historical_events import HistoricalEventPublisher
from engine.biocatalyst.jv_snapshot import AUTHORIZED_INPUTS, InputSpec, admit_files
from scripts.biocatalyst_snapshot_onboard import (
    build_onboard_artifacts,
    private_object_keys,
    publish_private_artifacts,
    safe_summary,
)


class MemoryStore(BinaryObjectStore):
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def get_bytes(self, key: str) -> bytes | None:
        return self.objects.get(key)

    def put_if_absent(self, key: str, data: bytes, *, content_type: str = "application/octet-stream") -> bool:
        if key in self.objects:
            return False
        self.objects[key] = data
        return True


def test_private_keys_are_content_addressed_and_separate() -> None:
    keys = private_object_keys(
        raw_inputs={"workbook_w4": ("BioPharmCatalyst_Tables.xlsx", b"xlsx"), "historical_fda": ("history.csv", b"csv")},
        manifest=b"manifest",
        normalized=b"event\n",
    )
    assert keys["workbook_w4"].startswith("biopharmcatalyst_jv_snapshot/raw/")
    assert keys["historical_fda"].startswith("biopharmcatalyst_jv_snapshot/raw/")
    assert keys["manifest"].startswith("biopharmcatalyst_jv_snapshot/manifests/")
    assert keys["normalized"].startswith("biopharmcatalyst_jv_snapshot/normalized/")
    assert len(set(keys.values())) == 4


def test_private_publication_reads_back_every_immutable_object() -> None:
    store = MemoryStore()
    receipts = publish_private_artifacts(
        store,
        raw_inputs={"workbook_w4": ("BioPharmCatalyst_Tables.xlsx", b"xlsx")},
        manifest=b"manifest",
        normalized=b"event\n",
    )
    assert len(receipts) == 3
    assert all(store.get_bytes(receipt.object_key) is not None for receipt in receipts)


def _fixture_artifacts(tmp_path: Path):
    workbook = Workbook()
    device_history = workbook.active
    device_history.title = "Device History"
    device_history.append(["Ticker", "Name", "Catalyst Price Movement", "Price at Catalyst Date", "Device", "Indication", "Device Stage", "Catalyst Date", "Catalyst"])
    device_history.append(["DEV", "Device Co", "+4%", "$12", "Device X", "Cardiology", "510(k)", "05/06/2022 ET", "Clearance"])
    pipeline = workbook.create_sheet("Device Pipeline")
    pipeline.append(["Ticker", "Name", "Price", "30 Day Price Change", "Device", "Indication", "Stage", "Catalyst Date", "Catalyst", "Options"])
    pipeline.append(["DEV", "Device Co", "$99", "+30%", "Device Y", "Surgery", "Approved", "01/02/2020 ET", "Approval", "View"])
    workbook_stream = BytesIO()
    workbook.save(workbook_stream)
    history = (
        "row,ticker,name,catalyst_price_movement,price_at_catalyst_date,drug,indication,stage,catalyst_date,catalyst,conference,company_url,catalyst_url\r\n"
        "1,ABC,Alpha,+5%,$10,Drug A,Cancer,Approved,01/02/2020 ET,Approved.,,https://private/company,https://private/catalyst\r\n"
    ).encode()
    payloads = {
        "workbook_w4": workbook_stream.getvalue(),
        "all_companies": b"ticker,name\r\nABC,Alpha\r\n",
        "historical_fda": history,
        "mergers_acquisitions": b"target,status\r\nAlpha,closed\r\n",
        "hedge_funds": b"fund,position\r\nFund A,ABC\r\n",
    }
    specs = {
        key: InputSpec(key, AUTHORIZED_INPUTS[key].safe_name, sha256(data).hexdigest(), len(data), AUTHORIZED_INPUTS[key].media_type, AUTHORIZED_INPUTS[key].role)
        for key, data in payloads.items()
    }
    paths = {}
    for key, data in payloads.items():
        path = tmp_path / specs[key].safe_name
        path.write_bytes(data)
        paths[key] = path
    aliases = BytesIO()
    pd.DataFrame([{"vendor": "store", "vendor_symbol": "ABC", "security_id": "SEC:US-XNAS-ABC", "valid_from": None, "valid_to": None, "ingested_at": None}]).to_parquet(aliases, index=False)
    master = BytesIO()
    pd.DataFrame([{"security_id": "SEC:US-XNAS-ABC", "issuer_id": "ISS:US-XNAS-ABC", "issuer_state": "RESOLVED", "listing_key": "US-XNAS-ABC", "security_state": None, "superseded_by": None}]).to_parquet(master, index=False)
    admitted = admit_files(paths, specs=specs)
    return admitted, master.getvalue(), aliases.getvalue()


def test_closed_build_and_public_projection_are_fixed_points(tmp_path: Path) -> None:
    admitted, master, aliases = _fixture_artifacts(tmp_path)
    kwargs = {
        "security_master": master,
        "vendor_aliases": aliases,
        "observed_at": "2026-08-17T07:55:47Z",
        "expected_fda_rows": 1,
        "expected_fda_shifted": 0,
    }
    first = build_onboard_artifacts(admitted, **kwargs)
    second = build_onboard_artifacts(admitted, **kwargs)
    assert first.manifest_bytes == second.manifest_bytes
    assert first.normalized_bytes == second.normalized_bytes
    assert first.coverage == {"state": "partial", "source_rows": 3, "normalized_rows": 3, "identity_resolved": 1, "identity_unresolved": 2, "duplicates_collapsed": 0, "families": {"device_history": 1, "device_pipeline_history": 1, "historical_fda": 1}, "family_source_rows": {"historical_fda": 1, "device_history": 1, "device_pipeline_history": 1}}

    publisher = HistoricalEventPublisher(tmp_path / "public")
    published_first = publisher.publish(first.events, coverage=first.coverage, capture_observed_at="2026-08-17T07:55:47Z", published_at="2026-08-24T20:00:00Z")
    pointer_first = (tmp_path / "public" / "current.json").read_bytes()
    published_second = publisher.publish(second.events, coverage=second.coverage, capture_observed_at="2026-08-17T07:55:47Z", published_at="2026-08-24T20:00:00Z")
    assert published_first.generation_id == published_second.generation_id
    assert pointer_first == (tmp_path / "public" / "current.json").read_bytes()


def test_operator_summary_never_emits_payload_or_private_locator(tmp_path: Path) -> None:
    admitted, master, aliases = _fixture_artifacts(tmp_path)
    artifacts = build_onboard_artifacts(
        admitted,
        security_master=master,
        vendor_aliases=aliases,
        observed_at="2026-08-17T07:55:47Z",
        expected_fda_rows=1,
        expected_fda_shifted=0,
    )
    rendered = json.dumps(safe_summary(artifacts, mode="check"), sort_keys=True)
    assert '"raw_payload_emitted": false' in rendered
    for forbidden in ("Alpha", "Drug A", "https://private", "object_key", "SEC:US-XNAS-ABC"):
        assert forbidden not in rendered
