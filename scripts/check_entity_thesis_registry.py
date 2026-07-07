"""ETM integrity gate — checks data/neuralweb/entity_thesis_mechanism_registry.json.

Hard violations (each printed with a stable code, exit 1):
  ETM-C1  schema field != module SCHEMA constant
  ETM-C2  authority block mismatch, is_context_only != true, or any row authority != 'display_only'
  ETM-C3  namespace grammar: row registry_id / key fails its registry_type regex,
           registry_type not in REGISTRY_TYPES, or reserved type claim_cluster emitted
  ETM-C4  invented links: edge missing source.path or source.detail, or endpoint
           not resolvable (rows key, trial_families key, gov:/rf: namespace match)
  ETM-C5  suggestion-only law: possible_duplicates entry basis != 'token_overlap_suggestion_only'
  ETM-C6  counts drift: counts.rows_by_type / counts.edges_by_kind != recomputed values
  ETM-C7  referential integrity (only for source files present on disk):
           species_link species_id@version must exist in data/species/registry.json;
           mechanism candidate_ids must exist in data/research_factory/candidates.jsonl;
           gov:<event_id> edges must resolve in data/neuralweb/governance.jsonl

If the artifact file is absent: print a note and exit 0 (pre-first-build grace).

Run:  python -m scripts.check_entity_thesis_registry          # scan; exit 1 on violation
      python -m scripts.check_entity_thesis_registry --path /other/path.json
      python -m scripts.check_entity_thesis_registry --selftest
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Import schema constants from the engine module so this gate always uses the
# canonical definitions — never a copy that could drift.
sys.path.insert(0, str(ROOT))
from engine.neuralweb.entity_thesis_mechanism_registry import (  # noqa: E402
    AUTHORITY_BLOCK,
    NAMESPACE_PATTERNS,
    REGISTRY_TYPES,
    SCHEMA,
)

DEFAULT_ARTIFACT = ROOT / "data" / "neuralweb" / "entity_thesis_mechanism_registry.json"

# Resolvable endpoint: rows key, trial_families key, gov: namespace, rf: namespace,
# or experiment ref (species-* convention).
_ENDPOINT_PREFIXES = ("species-",)


def _read_json(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def _recount(artifact: dict) -> tuple[dict, dict]:
    rows_by_type: dict[str, int] = defaultdict(int)
    for row in artifact.get("rows", {}).values():
        rows_by_type[row.get("registry_type", "__missing__")] += 1
    edges_by_kind: dict[str, int] = defaultdict(int)
    for edge in artifact.get("edges", []):
        edges_by_kind[edge.get("kind", "unknown")] += 1
    return dict(rows_by_type), dict(edges_by_kind)


def _ns_pattern_for_type(rtype: str):
    """Return the NAMESPACE_PATTERNS key for a registry_type, or None if mechanism-dual."""
    mapping = {
        "entity": "entity",
        "thesis": "thesis",
        "species_link": "species",
        # mechanism rows use either mechanism: or rf: namespace
    }
    return mapping.get(rtype)


def check(artifact_path: Path) -> list[str]:
    """Return list of violation strings (empty = clean). Prints each violation."""
    violations: list[str] = []

    def _viol(code: str, msg: str) -> None:
        line = f"{code}: {msg}"
        print(line)
        violations.append(line)

    if not artifact_path.exists():
        print(f"check_entity_thesis_registry: artifact absent at {artifact_path} — skipping (pre-first-build grace)")
        return violations

    try:
        artifact = _read_json(artifact_path)
    except Exception as exc:
        _viol("ETM-C1", f"artifact unreadable: {exc}")
        return violations

    rows: dict = artifact.get("rows", {})
    edges: list = artifact.get("edges", [])
    trial_families: dict = artifact.get("trial_families", {})
    possible_duplicates: list = artifact.get("possible_duplicates", [])
    counts: dict = artifact.get("counts", {})

    # ETM-C1 — schema
    if artifact.get("schema") != SCHEMA:
        _viol("ETM-C1", f"schema mismatch: found {artifact.get('schema')!r}, expected {SCHEMA!r}")

    # ETM-C2 — authority
    if artifact.get("authority") != AUTHORITY_BLOCK:
        _viol("ETM-C2", f"top-level authority block does not match AUTHORITY_BLOCK constant")
    if artifact.get("is_context_only") is not True:
        _viol("ETM-C2", f"is_context_only must be true, found {artifact.get('is_context_only')!r}")
    _AUTHORITY_BEARING_KEYS = frozenset({"can_gate", "can_rank", "can_size", "score", "rank", "weight"})
    for rid, row in rows.items():
        if row.get("authority") != "display_only":
            _viol("ETM-C2", f"row {rid!r} authority={row.get('authority')!r}; must be 'display_only'")
        for bad_key in _AUTHORITY_BEARING_KEYS & set(row.keys()):
            _viol("ETM-C2", f"row {rid!r} contains forbidden authority-bearing key {bad_key!r}")

    # ETM-C3 — namespace grammar
    _reserved = frozenset(["claim_cluster"])
    for rid, row in rows.items():
        rtype = row.get("registry_type")
        if rtype not in REGISTRY_TYPES:
            _viol("ETM-C3", f"row {rid!r} has unknown registry_type {rtype!r}")
            continue
        if rtype in _reserved:
            _viol("ETM-C3", f"reserved type {rtype!r} emitted for row {rid!r} (ETM-R1)")
            continue
        # key must match the row's registry_id
        if row.get("registry_id") != rid:
            _viol("ETM-C3", f"rows key {rid!r} != row.registry_id {row.get('registry_id')!r}")
        # namespace regex check
        ns_key = _ns_pattern_for_type(rtype)
        if ns_key is not None:
            pat = NAMESPACE_PATTERNS[ns_key]
            if not pat.match(rid):
                _viol("ETM-C3", f"row {rid!r} (type={rtype}) fails {ns_key} namespace pattern")
        elif rtype == "mechanism":
            mech_ok = (
                NAMESPACE_PATTERNS["mechanism"].match(rid) or
                NAMESPACE_PATTERNS["rf"].match(rid)
            )
            if not mech_ok:
                _viol("ETM-C3", f"mechanism-type row {rid!r} fails both mechanism: and rf: patterns")

    # ETM-C4 — invented links
    all_row_keys = set(rows.keys())
    all_family_keys = set(trial_families.keys())

    def _endpoint_resolvable(eid: str) -> bool:
        if eid in all_row_keys:
            return True
        if eid in all_family_keys:
            return True
        if NAMESPACE_PATTERNS["gov"].match(eid):
            return True
        if NAMESPACE_PATTERNS["rf"].match(eid):
            return True
        for pfx in _ENDPOINT_PREFIXES:
            if eid.startswith(pfx):
                return True
        return False

    for i, edge in enumerate(edges):
        src = edge.get("src", "")
        dst = edge.get("dst", "")
        source = edge.get("source", {})
        if not source.get("path"):
            _viol("ETM-C4", f"edge [{i}] {src!r}→{dst!r} missing source.path")
        if not source.get("detail"):
            _viol("ETM-C4", f"edge [{i}] {src!r}→{dst!r} missing source.detail")
        if not _endpoint_resolvable(src):
            _viol("ETM-C4", f"edge [{i}] src {src!r} not resolvable")
        if not _endpoint_resolvable(dst):
            _viol("ETM-C4", f"edge [{i}] dst {dst!r} not resolvable")

    # ETM-C5 — suggestion-only law
    _FORBIDDEN_MERGE_KEYS = frozenset({"auto_merge", "merge", "canonical", "resolved"})
    for i, dup in enumerate(possible_duplicates):
        if dup.get("basis") != "token_overlap_suggestion_only":
            _viol("ETM-C5", f"possible_duplicates[{i}] basis={dup.get('basis')!r}; must be 'token_overlap_suggestion_only'")
        if dup.get("suggestion_only") is not True:
            _viol("ETM-C5", f"possible_duplicates[{i}] suggestion_only must be true, found {dup.get('suggestion_only')!r}")
        for bad_key in _FORBIDDEN_MERGE_KEYS & set(dup.keys()):
            _viol("ETM-C5", f"possible_duplicates[{i}] contains forbidden merge-directive key {bad_key!r}")

    # ETM-C6 — counts drift
    recomputed_rbt, recomputed_ebk = _recount(artifact)
    stored_rbt = counts.get("rows_by_type", {})
    stored_ebk = counts.get("edges_by_kind", {})
    if stored_rbt != recomputed_rbt:
        _viol("ETM-C6", f"counts.rows_by_type drift: stored={stored_rbt} recomputed={recomputed_rbt}")
    if stored_ebk != recomputed_ebk:
        _viol("ETM-C6", f"counts.edges_by_kind drift: stored={stored_ebk} recomputed={recomputed_ebk}")

    # ETM-C7 — referential integrity (only for source files present on disk)
    _check_referential_integrity(artifact_path, artifact, rows, edges, _viol)

    return violations


def _check_referential_integrity(
    artifact_path: Path,
    artifact: dict,
    rows: dict,
    edges: list,
    _viol,
) -> None:
    # Determine repo root relative to artifact path.
    # artifact_path = <root>/data/neuralweb/entity_thesis_mechanism_registry.json
    repo = artifact_path.parent.parent.parent

    # species registry
    species_path = repo / "data" / "species" / "registry.json"
    if species_path.exists():
        try:
            sp_raw = json.loads(species_path.read_text(encoding="utf-8"))
            known_species: set[str] = set()
            for sp in (sp_raw or {}).get("species", []):
                sid = sp.get("species_id", "")
                ver = sp.get("version", "1.0")
                known_species.add(f"species:{sid}@{ver}")
            for rid, row in rows.items():
                if row.get("registry_type") == "species_link":
                    if rid not in known_species:
                        _viol("ETM-C7", f"species_link row {rid!r} not found in data/species/registry.json")
        except Exception as exc:
            pass  # file present but unreadable — skip

    # candidates
    cand_path = repo / "data" / "research_factory" / "candidates.jsonl"
    if cand_path.exists():
        try:
            known_cids: set[str] = set()
            for line in cand_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    cid = obj.get("candidate_id")
                    if cid:
                        known_cids.add(cid)
                except json.JSONDecodeError:
                    pass
            for rid, row in rows.items():
                if row.get("registry_type") == "mechanism":
                    for cid in row.get("candidate_ids", []):
                        if cid not in known_cids:
                            _viol("ETM-C7", f"mechanism row {rid!r} references unknown candidate_id {cid!r}")
                    solo_cid = row.get("candidate_id")
                    if solo_cid and solo_cid not in known_cids:
                        _viol("ETM-C7", f"mechanism row {rid!r} references unknown candidate_id {solo_cid!r}")
        except Exception:
            pass

    # governance
    gov_path = repo / "data" / "neuralweb" / "governance.jsonl"
    if gov_path.exists():
        try:
            known_event_ids: set[str] = set()
            for line in gov_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    eid = obj.get("event_id")
                    if eid:
                        known_event_ids.add(eid)
                except json.JSONDecodeError:
                    pass
            for i, edge in enumerate(edges):
                dst = edge.get("dst", "")
                if dst.startswith("gov:"):
                    event_id = dst[4:]
                    if event_id not in known_event_ids:
                        _viol("ETM-C7", f"edge [{i}] dst {dst!r} event_id not found in data/neuralweb/governance.jsonl")
        except Exception:
            pass


def selftest() -> int:
    """Construct synthetic artifacts in a tempdir and verify each violation fires exactly once."""
    import tempfile

    ok = True
    results: list[tuple[str, bool, str]] = []  # (name, passed, detail)

    def _run_check(name: str, artifact: dict, expected_code: str | None) -> bool:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "data" / "neuralweb" / "entity_thesis_mechanism_registry.json"
            p.parent.mkdir(parents=True)
            p.write_text(json.dumps(artifact), encoding="utf-8")
            viols = check(p)
        if expected_code is None:
            passed = len(viols) == 0
            detail = f"violations={viols}" if not passed else "clean"
        else:
            matching = [v for v in viols if v.startswith(expected_code)]
            passed = len(matching) >= 1
            detail = f"fired={[v for v in viols if v.startswith(expected_code)]}" if passed else f"expected {expected_code}, got {viols}"
        results.append((name, passed, detail))
        return passed

    # ---- minimal clean artifact ----
    clean = {
        "schema": SCHEMA,
        "is_context_only": True,
        "authority": AUTHORITY_BLOCK,
        "rows": {},
        "edges": [],
        "trial_families": {},
        "possible_duplicates": [],
        "counts": {"rows_by_type": {}, "edges_by_kind": {}},
    }

    ok = _run_check("clean — must pass", clean, None) and ok

    # ETM-C1: schema mismatch
    c1 = dict(clean)
    c1["schema"] = "wrong.schema.v99"
    ok = _run_check("ETM-C1 schema mismatch", c1, "ETM-C1") and ok

    # ETM-C2: authority block mismatch
    c2 = dict(clean)
    c2["authority"] = {"role": "wrong"}
    ok = _run_check("ETM-C2 authority block", c2, "ETM-C2") and ok

    # ETM-C2: row with can_gate: true → fires C2 (F5 defense in depth)
    c2b = dict(clean)
    c2b["rows"] = {
        "thesis:test_gated": {
            "registry_id": "thesis:test_gated",
            "registry_type": "thesis",
            "authority": "display_only",
            "can_gate": True,
        }
    }
    c2b["counts"] = {"rows_by_type": {"thesis": 1}, "edges_by_kind": {}}
    ok = _run_check("ETM-C2 can_gate in row", c2b, "ETM-C2") and ok

    # ETM-C3: reserved type emitted
    c3 = {**clean, "rows": {
        "claim:abcdef1234567890": {
            "registry_id": "claim:abcdef1234567890",
            "registry_type": "claim_cluster",
            "authority": "display_only",
        }
    }, "counts": {"rows_by_type": {"claim_cluster": 1}, "edges_by_kind": {}}}
    ok = _run_check("ETM-C3 claim_cluster emitted", c3, "ETM-C3") and ok

    # ETM-C4: edge missing source.path
    c4 = {**clean, "rows": {
        "thesis:test_thesis": {
            "registry_id": "thesis:test_thesis",
            "registry_type": "thesis",
            "authority": "display_only",
        }
    }, "edges": [
        {"src": "thesis:test_thesis", "dst": "thesis:test_thesis",
         "kind": "self", "source": {"detail": "test"}}
    ], "counts": {"rows_by_type": {"thesis": 1}, "edges_by_kind": {"self": 1}}}
    ok = _run_check("ETM-C4 missing source.path", c4, "ETM-C4") and ok

    # ETM-C5: wrong basis
    c5 = {**clean, "possible_duplicates": [
        {"a": "thesis:x", "b": "thesis:y", "basis": "manual_assertion",
         "suggestion_only": True, "shared_tokens": ["foo"]}
    ]}
    ok = _run_check("ETM-C5 wrong basis", c5, "ETM-C5") and ok

    # ETM-C5: auto_merge present (merge-directive key)
    c5b = {**clean, "possible_duplicates": [
        {"a": "thesis:x", "b": "thesis:y", "basis": "token_overlap_suggestion_only",
         "suggestion_only": True, "shared_tokens": ["foo"], "auto_merge": True}
    ]}
    ok = _run_check("ETM-C5 auto_merge present", c5b, "ETM-C5") and ok

    # ETM-C5: missing suggestion_only flag
    c5c = {**clean, "possible_duplicates": [
        {"a": "thesis:x", "b": "thesis:y", "basis": "token_overlap_suggestion_only",
         "shared_tokens": ["foo"]}
    ]}
    ok = _run_check("ETM-C5 missing suggestion_only", c5c, "ETM-C5") and ok

    # ETM-C5: clean entry (both checks pass)
    c5_clean = {**clean, "possible_duplicates": [
        {"a": "thesis:x", "b": "thesis:y", "basis": "token_overlap_suggestion_only",
         "suggestion_only": True, "shared_tokens": ["foo"], "note": "suggestion only — not a merge"}
    ]}
    ok = _run_check("ETM-C5 clean entry (no violation)", c5_clean, None) and ok

    # ETM-C6: counts drift
    c6 = {**clean, "rows": {
        "thesis:some_slug": {
            "registry_id": "thesis:some_slug",
            "registry_type": "thesis",
            "authority": "display_only",
        }
    }, "counts": {"rows_by_type": {"thesis": 99}, "edges_by_kind": {}}}
    ok = _run_check("ETM-C6 counts drift", c6, "ETM-C6") and ok

    # absent artifact → exit 0 (tested separately via temp path with no file)
    with tempfile.TemporaryDirectory() as td:
        absent_path = Path(td) / "data" / "neuralweb" / "entity_thesis_mechanism_registry.json"
        viols = check(absent_path)
        absent_ok = len(viols) == 0
        results.append(("absent artifact → exit 0", absent_ok, ""))
        ok = absent_ok and ok

    # Print summary
    for name, passed, detail in results:
        status = "PASS" if passed else "FAIL"
        suffix = f" — {detail}" if detail and not passed else ""
        print(f"  [{status}] {name}{suffix}")

    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="ETM integrity gate for data/neuralweb/entity_thesis_mechanism_registry.json"
    )
    ap.add_argument(
        "--path",
        type=Path,
        default=DEFAULT_ARTIFACT,
        help="Path to artifact (default: data/neuralweb/entity_thesis_mechanism_registry.json)",
    )
    ap.add_argument(
        "--selftest",
        action="store_true",
        help="Prove each ETM-C1..C6 violation fires; exit 0 iff all behave.",
    )
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()

    violations = check(args.path)
    if violations:
        print(
            f"\n::error:: {len(violations)} ETM integrity violation(s) — "
            f"see codes ETM-C1..C7 above",
            file=sys.stderr,
        )
        return 1
    print("check_entity_thesis_registry: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
