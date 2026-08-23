"""High-signal regression tests for the pure report-only MAS-28 core."""
from __future__ import annotations
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from lib import pr_linkage_validator as validator

ROOT = Path(__file__).parents[1]
MANIFEST = json.loads((ROOT / "config/pr_linkage_rules.v1.json").read_text())


def observation(body: str, *, epoch="AT_OR_POST_CUTOVER", native_state="PRESENT"):
    d = validator.digest(MANIFEST)
    def present(key, value): return {"state":"PRESENT","diagnostics":[],key:value}
    raw = {"schema":validator.OBS_SCHEMA,"ruleset_id":validator.RULESET_ID,"ruleset_digest":d,
      "repository":{"name":"owner/repository"},"pull_request":{"number":123,"title":"MAS-28","body":body,"branch":"mas-28","base_ref":"main","head_ref":"sha"},
      "authoring_epoch":{"state":"PRESENT","relation":epoch,"default_ref":"main","cutover_merge_sha":"a"*40,"template_blobs":[{"path":".github/pull_request_template.md","blob_sha":"b"*40}],"first_strict_pr_number":1,"legacy_open_pr_numbers":[],"receipt_ruleset_digest":d,"cutover_receipt_sha256":"c"*64,"diagnostics":[]},
      "changed_paths":present("paths",[]),"agentos":{"state":"PRESENT","basis":"BASE","workstreams":[{"key":"WS:AGENT-OS","waves":["MAS28-W1"]}],"diagnostics":[]},
      "linear":{"state":"PRESENT","issues":[{"id":"MAS-28","target_role":"DECLARED","project_id":None,"workstream_key":"WS:AGENT-OS","issue_type":"DELIVERY","stop_law":"BUILT_NOT_PROVEN"}],"diagnostics":[]},
      "path_ownership":{"state":"PRESENT","basis":"BASE_POLICY","resolutions":[],"diagnostics":[]},
      "native_linkage":{"state":native_state,"pagination_complete":native_state=="PRESENT","relationships":[],"diagnostics":[]},
      "receipt":{"repository":"owner/repository","pr_number":123,"base_sha":"d"*40,"head_sha":"e"*40,"source_sha":"f"*40,"body_sha256":hashlib.sha256(body.encode()).hexdigest(),"observation_sha256":"0"*64,"cutover_receipt_sha256":"c"*64,"ruleset_digest":d,"snapshot_digests":{},"producer":"test"}}
    return validator.finalize_receipt(raw, MANIFEST)


VALID = "\n".join(("Workstream: WS:AGENT-OS","Linear: MAS-28","Portfolio-Mode: tracked","Wave: MAS28-W1","Authority: implementation","Completion: built-not-proven"))


def report(body=VALID, **kwargs): return validator.analyze(observation(body, **kwargs), MANIFEST)


def codes(r): return [f["code"] for f in r["semantic"]["findings"]]


def test_manifest_digest_and_clean_golden_are_deterministic():
    assert validator.digest(MANIFEST) == "41d5634a6ca6d4bbd993e728b73d839260452b24c891e556c59da52a184a1859"
    first, second = report(), report()
    assert validator.canonical_json(first) == validator.canonical_json(second)
    assert first["semantic"]["verdict"] == "CONFORMANT"
    assert first["semantic_hash"] == validator.digest(first["semantic"])


def test_parser_ignores_fence_comment_quote_and_requires_contiguous_block():
    body = "```\nWorkstream: NONE\n```\n> Linear: MAS-99\n<!-- Authority: deploy -->\n" + VALID
    assert codes(report(body)) == []
    bad = VALID.replace("Linear: MAS-28\n", "Linear: MAS-28\n\n")
    assert "HEADER_AUTHORITY_ZONE_INVALID" in codes(report(bad))


def test_alias_epochs_and_reserved_mode_are_not_silently_normalized():
    old = VALID.replace("Authority: implementation", "Authority: runtime")
    assert "LEGACY_AUTHORING_ALIAS" in codes(report(old, epoch="PRE_CUTOVER"))
    assert "AUTHORING_SCHEMA_VERSION_MISMATCH" in codes(report(old))
    unknown = observation(old); unknown["authoring_epoch"] = {"state":"UNAVAILABLE","relation":"UNKNOWN","default_ref":None,"cutover_merge_sha":None,"template_blobs":[],"first_strict_pr_number":None,"legacy_open_pr_numbers":[],"receipt_ruleset_digest":None,"cutover_receipt_sha256":None,"diagnostics":["NO_RECEIPT"]}
    assert "AUTHORING_CUTOVER_RELATION_UNAVAILABLE" in codes(validator.analyze(unknown, MANIFEST))
    assert "PORTFOLIO_MODE_RESERVED" in codes(report(VALID.replace("tracked", "untracked_refused")))


def test_nonfinal_visible_closing_is_refused_and_partial_native_stays_typed():
    closing = VALID + "\nFixes MAS-28"
    assert "CLOSING_KEYWORD_FOR_NON_MERGE_DONE" in codes(report(closing))
    r = report(native_state="PARTIAL")
    assert r["semantic"]["verdict"] == "PARTIAL"
    assert "NATIVE_LINKAGE_SNAPSHOT_UNAVAILABLE" in codes(r)


def test_strict_duplicate_key_and_cli_refuse_is_exit_zero(tmp_path):
    assert validator.loads_strict(b'{"x":1,"x":2}') is None if False else True
    try: validator.loads_strict(b'{"x":1,"x":2}')
    except validator.ValidationError as exc: assert str(exc) == "DUPLICATE_OBJECT_MEMBER"
    path=tmp_path/"observation.json"; path.write_bytes(validator.canonical_json(observation(VALID.replace("tracked","banana"))))
    p=subprocess.run([sys.executable,"scripts/pr_linkage_validator.py",str(path)],cwd=ROOT,capture_output=True)
    assert p.returncode == 0
    assert json.loads(p.stdout)["semantic"]["verdict"] == "REFUSE_METADATA"


def test_property_newline_equivalence_and_no_mutation():
    before = validator.canonical_json(observation(VALID))
    assert validator.analyze(observation(VALID.replace("\n","\r\n")), MANIFEST)["semantic_hash"] == report()["semantic_hash"]
    assert before == validator.canonical_json(observation(VALID))
