"""BC-2: a claim authored in a registry ROW is gated at the row, not a render later.

THE GAP (found 2026-08-11 while fixing the landing breach in #5413). BC-2 scanned
rendered surfaces and engine/ display copy, but NO data/ file. That left a whole class of
authored claim gated only on the generated half:

    data/cycle_pattern/truths.jsonl   —  `notes` / `statement` / `ci_summary`
      → scripts/build_measurement.py publishes them VERBATIM into the null_library of
    site/measurementdata/measurement_data.js   —  a user-facing payload

So a banned claim written into a registry row passed its own PR and only reddened CI once
a nightly render carried it onto the page — a day late, on somebody else's PR. That is
precisely the failure #3765 → #3790 added the engine-source scan to prevent; registry
DATA files were simply never brought into the same bargain. #5413 had to reword one claim
TWICE — in truths.jsonl AND in the generated measurement_data.js — because only the
generated half was gated.

Compounding it, the `_COPY_BARE` comment justified excluding `notes` as "research-registry
bookkeeping, all internal". True of a `notes=` binding in engine/ Python, false as a
general claim about the word: build_measurement publishes exactly that field. A stale
justification comment is how the next person re-opens a closed gap, so the comment is
scoped and this suite pins the behaviour it now describes.

Everything here runs through the REAL gate (scan_json_copy + the live allowlist), never a
re-implementation, so negation, structural and surface semantics stay in one place.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

import scripts.check_validated_claims as gate
from scripts.check_validated_claims import (
    DATA_COPY_SPECS,
    DataSpec,
    _load_allowlist,
    _surfaces_of,
    scan_json_copy,
)

ROOT = Path(__file__).resolve().parent.parent

# A phrase no allowlist entry backs, on any surface. If this ever becomes a real claim of
# record the suite fails loudly rather than silently testing nothing.
UNEARNED = "validated moon-phase rotation gate"

TRUTHS = "data/cycle_pattern/truths.jsonl"
MEASUREMENT_PAYLOAD = "site/measurementdata/measurement_data.js"


@pytest.fixture(scope="module")
def allow() -> list[dict]:
    return _load_allowlist()


def _spec(glob: str) -> DataSpec:
    for s in DATA_COPY_SPECS:
        if s.glob == glob:
            return s
    raise AssertionError(f"no DATA_COPY_SPECS entry for {glob!r} — "
                         f"have {[s.glob for s in DATA_COPY_SPECS]}")


def test_the_unearned_probe_is_really_unearned(allow):
    """Guard the guard: the probe phrase must match no allowlist entry anywhere."""
    for entry in allow:
        assert entry["match"].lower() not in UNEARNED.lower(), (
            f"probe phrase is now backed by {entry['match']!r} — pick another probe, "
            "otherwise every assertion below passes for the wrong reason")


def test_registry_row_claim_fails_at_its_source(allow):
    """THE SHAPE. A claim in a published field of a registry row is reported at the row."""
    row = json.dumps({"truth_id": "T-99", "status": "promoted_null",
                      "notes": f"Sizing follows the {UNEARNED} in the null library."},
                     ensure_ascii=False)
    found, stats = scan_json_copy(TRUTHS, row, allow, _spec(TRUTHS))
    assert len(found) == 1, f"registry-row claim not reported at source: {found}"
    assert found[0]["file"] == TRUTHS
    assert found[0]["line_no"] == 1
    assert "[notes]" in found[0]["text"]
    # the finding must name where the row is published, or a reader cannot judge it
    assert MEASUREMENT_PAYLOAD in found[0]["text"]
    assert stats["claims"] == 1 and stats["backed"] == 0


def test_statement_and_ci_summary_are_gated_too(allow):
    """build_measurement publishes three prose fields, not just `notes`."""
    for field in ("statement", "ci_summary"):
        row = json.dumps({"truth_id": "T-98", "status": "promoted_null",
                          field: f"The {UNEARNED} carries the size."}, ensure_ascii=False)
        found, _ = scan_json_copy(TRUTHS, row, allow, _spec(TRUTHS))
        assert len(found) == 1, f"published field {field!r} is not gated: {found}"
        assert f"[{field}]" in found[0]["text"]


def test_unpublished_field_in_the_same_row_is_out_of_scope(allow):
    """Field-restricted, not whole-file — the PY_COPY_GLOBS bargain, re-derived.

    `falsifiers` is registry bookkeeping the builder never copies out, so a token there is
    not a displayed claim. Scanning it would re-litigate internal research prose, which is
    the scope creep the field scope exists to prevent.
    """
    row = json.dumps({"truth_id": "T-97", "status": "promoted_null",
                      "falsifiers": f"Refit against the {UNEARNED} before promotion."},
                     ensure_ascii=False)
    found, stats = scan_json_copy(TRUTHS, row, allow, _spec(TRUTHS))
    assert found == [] and stats["claims"] == 0, (
        f"unpublished bookkeeping field was scanned: {found}")


def test_ascii_escaped_zh_claim_is_still_caught(allow):
    """A zh claim stored as \\uXXXX escapes is invisible to every text-scanning guard.

    json.dumps(..., ensure_ascii=True) is the estate default in several writers, and a
    grep for 已验证 never matches \\u5df2\\u9a8c\\u8bc1. Parsing the record instead of
    grepping the file is what closes that hole — pin it, because a future refactor to a
    line scan would silently reopen it.
    """
    row = json.dumps({"truth_id": "T-96", "status": "promoted_null",
                      "notes": "已验证的月相轮动门槛：减小仓位。"}, ensure_ascii=True)
    assert "已验证" not in row, "fixture is not actually ascii-escaped — test is vacuous"
    found, _ = scan_json_copy(TRUTHS, row, allow, _spec(TRUTHS))
    assert len(found) == 1, f"ascii-escaped zh claim not caught: {found}"


def test_backing_earned_on_the_payload_carries_to_the_source(allow):
    """The claim's surface is the PAYLOAD's, not the registry basename's.

    Otherwise moving the gate earlier would force a second, duplicate allowlist entry for
    every sentence already justified on the page a reader sees it on.
    """
    spec = _spec("data/sector_cycles/cycle_dna*.json")
    assert "sector_cycles_dna_data" in _surfaces_of(spec.payload)
    backed_phrase = "SMH领先每一次复苏(2016、2019、2020、2023、2026年均已验证)"
    doc = json.dumps({"xlk": {"bottom_signals_zh": backed_phrase}}, ensure_ascii=False)
    found, stats = scan_json_copy(spec.glob, doc, allow, spec)
    assert found == [], f"a claim already earned on the payload was re-flagged: {found}"
    assert stats["backed"] == 1


def test_a_phrase_justified_for_another_surface_still_fails(allow):
    """Surface scoping is not weakened by the payload indirection."""
    # 'validated absolute-trend drawdown gate' is backed only for sector_central/allocation
    doc = json.dumps({"xlk": {"body": "The validated absolute-trend drawdown gate held."}},
                     ensure_ascii=False)
    spec = _spec("data/sector_cycles/narratives*.json")
    found, _ = scan_json_copy(spec.glob, doc, allow, spec)
    assert len(found) == 1, (
        "a phrase justified for a DIFFERENT surface was accepted at the registry row")


def test_unparseable_registry_fails_closed(allow):
    """A registry the gate cannot read is a finding, never a skip."""
    found, _ = scan_json_copy(TRUTHS, '{"truth_id": "T-95", "notes": ', allow, _spec(TRUTHS))
    assert len(found) == 1 and "UNPARSEABLE" in found[0]["text"]

    found, _ = scan_json_copy("data/sector_cycles/narratives.json", "{not json",
                              allow, _spec("data/sector_cycles/narratives*.json"))
    assert len(found) == 1 and "UNPARSEABLE" in found[0]["text"]


def test_every_spec_glob_resolves_against_the_tree():
    """A renamed registry must red CI, not quietly narrow the gate.

    scan() skips a glob that matches nothing, so a spec left pointing at a moved file
    would go dark exactly like an unrun test suite. This is the only thing that notices.
    """
    for spec in DATA_COPY_SPECS:
        assert sorted(ROOT.glob(spec.glob)), (
            f"DATA_COPY_SPECS entry {spec.glob!r} matches NO file — the registry moved or "
            "was renamed, and its rows are no longer gated at source")


def test_every_spec_payload_exists_and_is_scanned():
    """The payload must be a real artifact on a surface BC-2 already scans.

    If the payload path rots, the surface derivation silently changes and allowlist
    matching goes with it.
    """
    for spec in DATA_COPY_SPECS:
        payload = ROOT / spec.payload
        assert payload.exists(), f"{spec.glob}: payload {spec.payload} does not exist"
        assert spec.payload.endswith((".js", ".html")), (
            f"{spec.glob}: payload {spec.payload} is not one of the site file types "
            "SCAN_GLOBS covers, so the source scan would be the ONLY gate on it")


def test_measurement_channel_is_registered():
    """The motivating case stays wired: truths.jsonl → the measurement payload."""
    spec = _spec(TRUTHS)
    assert spec.payload == MEASUREMENT_PAYLOAD
    assert spec.fields is not None
    assert {"notes", "statement", "ci_summary"} <= spec.fields


def _fields_build_measurement_publishes() -> set[str]:
    """Every truth-row key scripts/build_measurement.py copies into its payload.

    Read from the builder's AST rather than hard-coded, so the pin tracks the builder.
    """
    src = (ROOT / "scripts" / "build_measurement.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    out: set[str] = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "get"
                and isinstance(node.func.value, ast.Name) and node.func.value.id == "t"
                and node.args and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)):
            out.add(node.args[0].value)
    return out


# Keys build_measurement publishes that are NOT prose: enums, ids, dates and reference
# lists carry no claim language, so the spec deliberately leaves them out of scope.
_NON_PROSE = {"truth_id", "status", "effect_class", "pit_class", "next_review_due",
              "evidence_refs"}


def test_spec_fields_track_what_the_builder_actually_publishes():
    """If build_measurement starts publishing a NEW field, a human must classify it.

    The failure mode this catches: a builder gains a prose field, the spec does not, and
    the gate quietly stops covering the channel it was written for.
    """
    published = _fields_build_measurement_publishes()
    assert published, "could not read the published fields out of build_measurement.py"
    spec = _spec(TRUTHS)
    assert spec.fields <= published, (
        f"spec gates {sorted(spec.fields - published)} which build_measurement no longer "
        "publishes — the spec drifted off the builder")
    unclassified = published - spec.fields - _NON_PROSE
    assert not unclassified, (
        f"build_measurement publishes {sorted(unclassified)}, which is neither gated by "
        "DATA_COPY_SPECS nor listed as non-prose. Classify it: add prose fields to the "
        "spec, non-prose keys to _NON_PROSE.")


def test_specs_are_actually_wired_into_scan(tmp_path, monkeypatch):
    """Declaring a spec is not running it — pin the WIRING, through scan() itself.

    Every assertion above calls scan_json_copy directly, so dropping the DATA_COPY_SPECS
    loop out of scan() would leave them all green while the gate went dark on data/ — the
    same shape as a registered-but-unrun test suite. This drives the real entry point over
    a throwaway tree (a full scan of the estate takes ~60s, far too slow for a suite).
    """
    reg = tmp_path / TRUTHS
    reg.parent.mkdir(parents=True)
    reg.write_text(json.dumps({"truth_id": "T-94", "status": "promoted_null",
                               "notes": f"Sizing follows the {UNEARNED}."},
                              ensure_ascii=False) + "\n", encoding="utf-8")
    monkeypatch.setattr(gate, "ROOT", tmp_path)

    found = gate.scan()

    assert [r["file"] for r in found] == [TRUTHS], (
        f"scan() did not reach the registry specs — DATA_COPY_SPECS is declared but not "
        f"consumed by the code path CI runs. got: {found}")


def test_the_committed_registries_are_clean(allow):
    """The widened gate ships with zero pre-existing debt (CLAUDE.md census rule).

    A widened guard that reddens main pins the whole fleet, so this asserts the real
    committed rows — not a fixture — scan clean.
    """
    findings: list[dict] = []
    for spec in DATA_COPY_SPECS:
        for f in sorted(ROOT.glob(spec.glob)):
            rel = f.relative_to(ROOT).as_posix()
            found, _ = scan_json_copy(rel, f.read_text(encoding="utf-8"), allow, spec)
            findings.extend(found)
    assert findings == [], "\n".join(
        f"{r['file']}:{r['line_no']}  {r['text'][:160]}" for r in findings)
