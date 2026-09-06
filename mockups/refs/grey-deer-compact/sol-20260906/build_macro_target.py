"""Proof harness: run the real builder through macro publication, then stop.
Does not alter its inputs, VM, renderer or writer. Later unrelated pages are not
built. This is a canonical MACRO TARGET proof, never a full-site build claim.
"""
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
os.environ["MACRO_DUMP_VM"] = "1"
from scripts import build_site

_original_write = build_site.write_page

def observe_write(path, html, *args, **kwargs):
    result = _original_write(path, html, *args, **kwargs)
    if Path(path).resolve() == ROOT / "site" / "macro.html":
        receipt = {"status": "MACRO_TARGET_WRITTEN", "full_site_build": False,
                   "utc": datetime.now(timezone.utc).isoformat(),
                   "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest()}
        Path(__file__).with_name("canonical-target-receipt.json").write_text(json.dumps(receipt, indent=2))
        print(json.dumps(receipt), flush=True)
        raise SystemExit(0)
    return result

build_site.write_page = observe_write
build_site.main()
