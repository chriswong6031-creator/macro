#!/usr/bin/env python3
"""One-time public-SEC capture of the FIF-3A1 AAPL 2025 10-K package.

Capture is NOT on the HTTP request path. The committed fixture is the
offline source of truth. Re-run only if the golden accession changes.
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from engine.fundamental_forensics.statement_graph import mint_fixture_recorded_at

CIK = "0000320193"
ACCESSION = "0000320193-25-000079"
PRIMARY = "aapl-20250927.htm"
USER_AGENT = "MastermindX FIF-3A1 data@mastermind-x.com"
ARCHIVE_DIR = (
    f"https://www.sec.gov/Archives/edgar/data/{int(CIK)}/{ACCESSION.replace('-', '')}"
)
RETAIN_ROLES = {
    PRIMARY: "primary",
    "aapl-20250927.xsd": "schema",
    "aapl-20250927_pre.xml": "presentation",
    "aapl-20250927_cal.xml": "calculation",
    "aapl-20250927_def.xml": "definition",
    "aapl-20250927_lab.xml": "label",
}


def _get(url: str) -> tuple[bytes, str | None]:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        last_modified = resp.headers.get("Last-Modified")
        return resp.read(), last_modified


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    dest = root / "tests" / "fixtures" / "fundamental_forensics" / "aapl_10k_2025"
    members_dir = dest / "members"
    members_dir.mkdir(parents=True, exist_ok=True)

    index_bytes, index_lm = _get(f"{ARCHIVE_DIR}/index.json")
    index_path = dest / "index.json"
    index_path.write_bytes(index_bytes)
    payload = json.loads(index_bytes.decode("utf-8"))
    items = payload["directory"]["item"]
    inventory = [str(item["name"]) for item in items]

    retained: dict[str, dict] = {}
    for name, role in RETAIN_ROLES.items():
        if name not in inventory:
            raise SystemExit(f"required member missing from archive index: {name}")
        time.sleep(0.15)
        content, last_modified = _get(f"{ARCHIVE_DIR}/{name}")
        path = members_dir / name
        path.write_bytes(content)
        retained[name] = {
            "name": name,
            "state": "stored",
            "role": role,
            "content_sha256": hashlib.sha256(content).hexdigest(),
            "byte_length": len(content),
            "path": f"members/{name}",
            "archive_url": f"{ARCHIVE_DIR}/{name}",
            "http_last_modified": last_modified,
        }

    members = []
    for item in items:
        name = str(item["name"])
        if name in retained:
            members.append(retained[name])
            continue
        members.append(
            {
                "name": name,
                "state": "not_requested",
                "role": "archive",
                "declared_reason": "not required for XBRL statement reconstruction",
                "index_size": item.get("size"),
                "index_type": item.get("type"),
                "archive_url": f"{ARCHIVE_DIR}/{name}",
            }
        )

    time.sleep(0.15)
    submissions_bytes, _ = _get(f"https://data.sec.gov/submissions/CIK{CIK}.json")
    submissions = json.loads(submissions_bytes.decode("utf-8"))
    recent = submissions["filings"]["recent"]
    acc_list = recent["accessionNumber"]
    idx = acc_list.index(ACCESSION)
    source_accepted_at = recent["acceptanceDateTime"][idx]
    filing_date = recent["filingDate"][idx]
    report_date = recent["reportDate"][idx]
    form = recent["form"][idx]
    primary_document = recent["primaryDocument"][idx]
    if primary_document != PRIMARY or form != "10-K":
        raise SystemExit(
            f"submissions identity mismatch: form={form} primary={primary_document}"
        )

    witness = {
        "source_url": f"https://data.sec.gov/submissions/CIK{CIK}.json",
        "source_path": f"filings.recent[accessionNumber={ACCESSION}]",
        "accessionNumber": ACCESSION,
        "form": form,
        "filingDate": filing_date,
        "reportDate": report_date,
        "acceptanceDateTime": source_accepted_at,
        "primaryDocument": primary_document,
    }
    witness_bytes = (json.dumps(witness, indent=2, sort_keys=True) + "\n").encode("utf-8")
    (dest / "sec_submissions_witness.json").write_bytes(witness_bytes)

    manifest = {
        "schema": "fundamental_forensics.golden_filing_package/v1",
        "entity_id": "ISS:US-XNAS-AAPL",
        "cik": CIK,
        "security_id": "SEC:US-XNAS-AAPL",
        "listing_key": "US-XNAS-AAPL",
        "legal_name": "Apple Inc.",
        "accession": ACCESSION,
        "form": form,
        "primary_document": PRIMARY,
        "period_of_report": report_date,
        "filing_date": filing_date,
        "source_accepted_at": source_accepted_at,
        "fixture_recorded_at": mint_fixture_recorded_at(datetime.now(timezone.utc)),
        "acceptance_witness": {
            "path": "sec_submissions_witness.json",
            "source_url": witness["source_url"],
            "content_sha256": hashlib.sha256(witness_bytes).hexdigest(),
            "byte_length": len(witness_bytes),
        },
        "archive_index_url": f"{ARCHIVE_DIR}/index.json",
        "index_sha256": hashlib.sha256(index_bytes).hexdigest(),
        "index_byte_length": len(index_bytes),
        "index_http_last_modified": index_lm,
        "member_count": len(inventory),
        "retained_count": len(retained),
        "members": members,
    }
    (dest / "package_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(
        {
            "dest": str(dest),
            "member_count": len(inventory),
            "retained_count": len(retained),
            "index_sha256": manifest["index_sha256"],
            "source_accepted_at": source_accepted_at,
            "retained": {name: row["content_sha256"] for name, row in retained.items()},
        },
        indent=2,
    ))


if __name__ == "__main__":
    main()
