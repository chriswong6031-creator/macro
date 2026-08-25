from __future__ import annotations
import json
import subprocess
import sys
from tests.test_pr_linkage_validator import ROOT, VALID, observation
from lib import pr_linkage_validator as validator


def invoke(tmp_path, raw: bytes, *args):
    path=tmp_path/"input.json"; path.write_bytes(raw)
    return subprocess.run([sys.executable,"scripts/pr_linkage_validator.py",str(path),*args],cwd=ROOT,capture_output=True)


def test_duplicate_json_is_a_typed_exit_two(tmp_path):
    p=invoke(tmp_path,b'{"schema":"x","schema":"y"}')
    assert p.returncode == 2
    e=json.loads(p.stderr); assert e["schema"] == "mastermind.pr_linkage_execution_error.v1"
    assert e["error"]["reason_code"] == "DUPLICATE_OBJECT_MEMBER"


def test_invalid_utf8_and_unknown_key_are_typed(tmp_path):
    assert json.loads(invoke(tmp_path,b'\xff').stderr)["error"]["reason_code"] == "INVALID_UTF8"
    o=observation(VALID); o["unexpected"]=True
    p=invoke(tmp_path,validator.canonical_json(o)); assert p.returncode == 2
    assert json.loads(p.stderr)["error"]["reason_code"] == "UNKNOWN_KEY"


def test_output_is_atomic_path_and_formats_are_nonblocking(tmp_path):
    o=observation(VALID.replace("tracked","banana")); path=tmp_path/"report.json"
    p=invoke(tmp_path,validator.canonical_json(o),"--output",str(path)); assert p.returncode == 0
    assert json.loads(path.read_bytes())["semantic"]["verdict"] == "REFUSE_METADATA"
    assert not list(tmp_path.glob(".report.json.*"))
    p=invoke(tmp_path,validator.canonical_json(o),"--format","github"); assert p.returncode == 0
    assert b"::warning" in p.stdout


def test_native_relationship_resource_receipt_has_exact_limit_and_observed(tmp_path):
    o=observation(VALID)
    o["native_linkage"]["relationships"]=[
        {"issue_id":f"MAS-{n+1}","kind":"CLOSING","source":"BODY","state":"PRESENT","completion_transition":"ELIGIBLE"}
        for n in range(257)
    ]
    o=validator.finalize_receipt(o, json.loads((ROOT/"config/pr_linkage_rules.v1.json").read_text()))
    p=invoke(tmp_path,validator.canonical_json(o)); assert p.returncode == 2 and p.stdout == b""
    error=json.loads(p.stderr)["error"]
    assert error["reason_code"] == "RESOURCE_LIMIT" and error["limit"] == 256 and error["observed"] == 257
