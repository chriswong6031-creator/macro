from __future__ import annotations

from copy import deepcopy
from itertools import combinations

import pytest

from scripts.research.dislocation_p0_a1_lib import selection_key
from scripts.research.dislocation_p0_s1f_measurement import exact_binomial_95, measure
from scripts.research.dislocation_p0_s1f_selection import STRATA, SelectionBlocked, exact70_manifest, manifest_bytes, selection_margins_ok, solve_exact70, validate_candidates
from scripts.research.dislocation_p0_s1f_triage import TriageBlocked, load_ruleset, triage_packet
from scripts.research.dislocation_p0_s1f_runner import RunnerBlocked, _file_sha256, run


def row(stratum, era, form, n, cik=None, accession=None):
    cik = cik or f"{n:010d}"
    accession = accession or f"{n:010d}-24-{n:06d}"
    return {"stratum": stratum, "era": era, "form": form, "base_form": form, "filed_on": "2024-02-01" if era == "modern" else "2020-02-01", "cik": cik, "accession": accession, "selection_key": selection_key(family=stratum, era=era, base=form, cik=cik, accession=accession), "query_edges": [{"phrase": "disruption", "query_cell_id": f"q{n}"}]}


def rows70():
    result=[]; n=1
    for stratum in STRATA:
        # legal table x=7: 7 modern/8K, 3 development/6K
        for era, form in [("modern", "8-K")]*7 + [("development", "6-K")]*3:
            result.append(row(stratum, era, form, n)); n += 1
    return result


def packet(content, *, form="8-K", date="2024-02-01", phrase="disruption", item_codes=()):
    import hashlib
    digest=hashlib.sha256(content).hexdigest()
    return {"packet_id":"p", "form":form, "filed_on":date, "accepted_at":f"{date}T00:00:00Z", "item_codes":list(item_codes), "query_edges":[{"filename":"matched.htm","phrase":phrase}], "exact_matched_documents":[{"filename":"matched.htm","document_sha256":digest,"query_phrases":[phrase]}], "source_documents":{digest:content}}


def test_joint_margins_same_cik_different_accession_and_byte_identity():
    items=rows70(); items[0]["cik"] = items[1]["cik"]; items[0]["selection_key"] = selection_key(family=items[0]["stratum"],era=items[0]["era"],base=items[0]["form"],cik=items[0]["cik"],accession=items[0]["accession"])
    selected=solve_exact70(items)
    assert selection_margins_ok(selected)
    assert len({(x["cik"],x["accession"]) for x in selected}) == 70
    m=exact70_manifest(items, design_ciks=[], frozen_universe_sha256="a"*64)
    assert manifest_bytes(m)==manifest_bytes(exact70_manifest(deepcopy(items),design_ciks=[],frozen_universe_sha256="a"*64))


def test_duplicate_pair_forbidden_and_design_cik_excluded_and_infeasible_fails_closed():
    items=rows70(); duplicate=deepcopy(items[0]); duplicate["stratum"]=STRATA[1]; duplicate["selection_key"]=selection_key(family=duplicate["stratum"],era=duplicate["era"],base=duplicate["form"],cik=duplicate["cik"],accession=duplicate["accession"]); items.append(duplicate)
    assert len({(x["cik"],x["accession"]) for x in solve_exact70(items)})==70
    with pytest.raises(SelectionBlocked): solve_exact70(items,design_ciks=[items[0]["cik"]])
    with pytest.raises(SelectionBlocked): solve_exact70(items[:-2])


def test_lexicographic_small_fixture_proof():
    # Full frozen shape with one optional earlier replacement must retain earlier key.
    items=rows70(); first=items[0]; alternative=row(first["stratum"],first["era"],first["form"],999)
    # Manufacture a higher key by CIK/accession while key remains valid; sorted solver must retain the true smaller.
    items.append(alternative); selected=solve_exact70(items)
    assert min(first["selection_key"],alternative["selection_key"]) in {x["selection_key"] for x in selected}


def test_milp_matches_bruteforce_with_cross_stratum_duplicate_identities():
    items = rows70()
    for source_index, target_index in ((0, 10), (1, 11)):
        source, target = items[source_index], items[target_index]
        alternative = row(
            target["stratum"], target["era"], target["form"], 800 + source_index,
            cik=source["cik"], accession=source["accession"],
        )
        items.append(alternative)
    candidates = validate_candidates(items)
    actual = solve_exact70(items)
    feasible = []
    for indexes in combinations(range(len(candidates)), 70):
        option = [candidates[index] for index in indexes]
        if selection_margins_ok(option):
            feasible.append(tuple(row["selection_key"] for row in option))
    assert feasible
    assert tuple(row["selection_key"] for row in actual) == min(feasible)


def test_amendment_exk_and_supplied_design_ciks_are_excluded():
    items = rows70()
    amendment = row(STRATA[0], "modern", "8-K", 901)
    amendment["form"] = "8-K/A"
    exk = row(
        STRATA[0], "modern", "8-K", 902,
        cik="0001015647", accession="0001015647-24-000902",
    )
    design = row(
        STRATA[0], "modern", "8-K", 903,
        cik="0000051143", accession="0000051143-24-000903",
    )
    eligible = validate_candidates(items + [amendment, exk, design], design_ciks=["0000051143"])
    identities = {(candidate["cik"], candidate["accession"]) for candidate in eligible}
    assert (amendment["cik"], amendment["accession"]) not in identities
    assert (exk["cik"], exk["accession"]) not in identities
    assert (design["cik"], design["accession"]) not in identities


@pytest.mark.parametrize("content,category,disposition",[
    (b"CERTIFICATION under Section 302; this disruption statement.","CERTIFICATION_ONLY","HARD_REFUSAL"),
    (b"For purposes of this agreement, disruption shall mean a covenant term.","AGREEMENT_COVENANT_DEFINITION_ONLY","HARD_REFUSAL"),
    (b"Risks include disruption that could adversely affect operations.","HYPOTHETICAL_RISK_ONLY","HARD_REFUSAL"),
    (b"The at-the-market offering describes a disruption in ordinary transactions.","ORDINARY_FINANCING_OR_TRANSACTION_CONTEXT","DEFER"),
    (b"Results of operations for the quarter ended include a disruption.","COMPLETED_PERIOD_RESULTS_CONTEXT","DEFER"),
])
def test_triage_false_positive_contexts(content,category,disposition):
    result=triage_packet(packet(content)); assert result["source_context_category"]==category and result["shadow_disposition"]==disposition


def test_triage_realized_and_items_time_and_missing_and_all_occurrences():
    assert triage_packet(packet(b"Item 2.04 actual disruption occurred.",item_codes=("2.04",)))["shadow_disposition"]=="RETAIN"
    assert triage_packet(packet(b"Item 1.05 cybersecurity disruption occurred.",item_codes=("1.05",)))["shadow_disposition"]=="RETAIN"
    assert triage_packet(packet(b"Item 1.05 cybersecurity disruption occurred.",date="2023-12-17",item_codes=("1.05",)))["shadow_disposition"]=="DEFER"
    assert triage_packet(packet(b"A disruption has occurred. operations were suspended."))["shadow_disposition"]=="RETAIN"
    assert triage_packet(packet(b"agreement disruption;" + b"x" * 1600 + b" unrelated disruption"))["shadow_disposition"]=="DEFER"
    bad=packet(b"disruption"); del bad["exact_matched_documents"]; assert triage_packet(bad)["shadow_disposition"]=="DEFER"


def test_triage_replays_all_exact_matched_documents_and_has_no_semantic_output():
    one=b"For purposes of this agreement, disruption shall mean a term."
    two=b"unrelated bytes without the phrase"
    import hashlib
    p=packet(one)
    p["query_edges"].append({"filename":"second.htm","phrase":"disruption"})
    p["exact_matched_documents"]=[{"filename":"matched.htm","document_sha256":hashlib.sha256(one).hexdigest(),"query_phrases":["disruption"]},{"filename":"second.htm","document_sha256":hashlib.sha256(two).hexdigest(),"query_phrases":["disruption"]}]
    p["source_documents"][hashlib.sha256(two).hexdigest()]=two
    result=triage_packet(p)
    assert result["shadow_disposition"]=="DEFER"
    assert not ({"event_family","episode","price","outcome","score","rank"} & set(result))


def test_ruleset_hash_is_frozen_and_signature_mutation_fails_closed():
    ruleset, digest = load_ruleset()
    assert len(digest) == 64
    mutated = deepcopy(ruleset)
    for rule in mutated["rules"]:
        if rule["id"] == "S1F-REALIZED-CURRENT-CONTEXT":
            rule["realized_signatures_ascii"] = ["changed after freeze"]
    with pytest.raises(TriageBlocked, match="HASH_MISMATCH"):
        triage_packet(packet(b"A disruption has occurred."), ruleset=mutated)


def test_measurement_boundaries_and_suppressed_admission_safety():
    assert exact_binomial_95(0,10)["lower"]=="0.000000000000" and exact_binomial_95(10,10)["upper"]=="1.000000000000"
    assert exact_binomial_95(0,0)["status"]=="UNDEFINED_ZERO_DENOMINATOR"
    items=[]
    for original in rows70():
        one=dict(original, audit_verdict="REJECT", audited_episode_origin=False, audited_false_positive_mechanism={"value":"AUDITED_NO_EPISODE", "evidence":{"document_sha256":"fixture", "start":0, "end":1, "excerpt":"x"}}, shadow_disposition="DEFER", matched_document_role="ARCHIVE_ONLY", reviewed_documents=[])
        items.append(one)
    items[0].update(audit_verdict="ACCEPT",audited_episode_origin=True,
                    economic_episode_id="s1f_episode_001",
                    shadow_disposition="HARD_REFUSAL",
                    triage_rule_ids=["S1F-CERTIFICATION-ONLY"])
    report=measure(items)
    assert report["hard_refusal_safety"]=="UNSAFE_FOR_PROMOTION"
    assert report["unsafe_hard_refusal_rules"] == {
        "S1F-CERTIFICATION-ONLY": [f"{items[0]['cik']}:{items[0]['accession']}"]
    }
    assert report["source_feasibility"]=="OBSERVED"
    assert report["p0_s2_sector_partition_blocker"] is True


def test_additive_primary_does_not_relabel_archive_only_match():
    items=[]
    for original in rows70():
        items.append(dict(original, audit_verdict="REJECT", audited_episode_origin=False, audited_false_positive_mechanism={"value":"AUDITED_NO_EPISODE", "evidence":{"document_sha256":"fixture", "start":0, "end":1, "excerpt":"x"}}, shadow_disposition="DEFER", reviewed_documents=[{"exact_fts_matched":True,"canonical_owner_role":"archive","sha256":"a","byte_length":1},{"exact_fts_matched":False,"canonical_owner_role":"primary","sha256":"b","byte_length":1}]))
    report=measure(items)
    assert set(report["by_document_role"]) == {"ARCHIVE_ONLY"}


def _write_json(path, value):
    import json
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


def _runner_fixture(tmp_path):
    universe = tmp_path / "complete_candidate_universe.json"
    _write_json(universe, rows70())
    universe_sha256 = _file_sha256(universe)
    design_ciks = [f"0000009{n:03d}" for n in range(20)]
    design = tmp_path / "A1R_EXACT20_SOURCE_SELECTION.json"
    _write_json(design, {
        "manifest_sha256": "e436c6e87870468d0df0449c86cc9b69a9d23aa1396885fffdfcbfcf6398852e",
        "candidates": [{"cik": cik} for cik in design_ciks],
    })
    completion = tmp_path / "A1R_QUERY_COMPLETION_AND_POOL_RECEIPT.json"
    _write_json(completion, {
        "status": "COMPLETE",
        "query_ledger": {"logical_cells": 146, "complete_cells": 146, "complete_cell_sha256": "c" * 64},
        "candidate_universe": {"count": 70, "raw_sha256": universe_sha256, "count_by_family": {}, "pool_sha256_by_family": {}},
        "completed_cache": {"record_count": 70, "incomplete_records": 0, "raw_sha256": "d" * 64},
    })
    freeze = tmp_path / "S1F_PROSPECTIVE_FREEZE_RECEIPT.json"
    _write_json(freeze, {
        "status": "FROZEN_PROSPECTIVE",
        "frozen_candidate_universe": {"candidate_universe_file_sha256": universe_sha256, "candidate_count": 70, "complete_cells": 146, "complete_cell_sha256": "c" * 64},
        "a1r_immutable_design_evidence": {"exact20_selection_file_sha256": _file_sha256(design), "design_ciks": design_ciks},
    })
    return universe, freeze, completion, design, universe_sha256


def test_runner_binds_completion_and_design_ciks_and_reruns_byte_identically(tmp_path):
    universe, freeze, completion, design, universe_sha256 = _runner_fixture(tmp_path)
    policy = __import__("pathlib").Path("research/dislocation_intelligence/p0_s1f/S1F_AUDIT_BATCH_POLICY.json")
    output = tmp_path / "out"
    kwargs = dict(
        universe_path=universe, freeze_path=freeze, completion_path=completion,
        design_manifest_path=design, policy_path=policy, output_dir=output,
        expected_universe_sha256=universe_sha256, expected_universe_rows=70,
        expected_complete_cells=146, expected_design_manifest_sha256=_file_sha256(design),
    )
    first = run(**kwargs)
    first_bytes = {name: path.read_bytes() for name, path in first["outputs"].items()}
    second = run(**kwargs)
    assert {name: path.read_bytes() for name, path in second["outputs"].items()} == first_bytes
    assert first["receipt"]["selection_count"] == first["receipt"]["selection_identity_count"] == 70
    assert first["receipt"]["a1r_completion"]["complete_cells"] == 146
    assert all(candidate["cik"] not in first["receipt"]["design_ciks_excluded"] for candidate in first["manifest"]["candidates"])
    assert [len(batch["packets"]) for batch in first["batch_plan"]["batches"]] == [10] * 7


def test_runner_fails_closed_when_146_of_146_completion_binding_is_broken(tmp_path):
    import json
    universe, freeze, completion, design, universe_sha256 = _runner_fixture(tmp_path)
    damaged = json.loads(completion.read_text(encoding="utf-8"))
    damaged["query_ledger"]["complete_cells"] = 145
    _write_json(completion, damaged)
    with pytest.raises(RunnerBlocked, match="S1F_A1R_COMPLETION_146_OF_146_REQUIRED"):
        run(
            universe_path=universe, freeze_path=freeze, completion_path=completion,
            design_manifest_path=design,
            policy_path=__import__("pathlib").Path("research/dislocation_intelligence/p0_s1f/S1F_AUDIT_BATCH_POLICY.json"),
            output_dir=tmp_path / "blocked", expected_universe_sha256=universe_sha256,
            expected_universe_rows=70, expected_complete_cells=146,
            expected_design_manifest_sha256=_file_sha256(design),
        )


def test_runner_fails_closed_when_completed_cache_has_incomplete_records(tmp_path):
    import json
    universe, freeze, completion, design, universe_sha256 = _runner_fixture(tmp_path)
    damaged = json.loads(completion.read_text(encoding="utf-8"))
    damaged["completed_cache"]["incomplete_records"] = 1
    _write_json(completion, damaged)
    with pytest.raises(RunnerBlocked, match="S1F_A1R_COMPLETED_CACHE_INCOMPLETE"):
        run(
            universe_path=universe, freeze_path=freeze, completion_path=completion,
            design_manifest_path=design,
            policy_path=__import__("pathlib").Path("research/dislocation_intelligence/p0_s1f/S1F_AUDIT_BATCH_POLICY.json"),
            output_dir=tmp_path / "blocked", expected_universe_sha256=universe_sha256,
            expected_universe_rows=70, expected_complete_cells=146,
            expected_design_manifest_sha256=_file_sha256(design),
        )
