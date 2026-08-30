---
key: DEEPVUE-INTELLIGENCE-WORKSPACE
title: DeepVue clean-room intelligence workspace
objective: >
  Build the bounded DeepVue-inspired intelligence workspace on Mastermind's existing
  identity, typed datapoint, owner, Brain and Terminal architecture. Done through the
  current boundary means W0-B, W1-A, W1-B and W1-C are merged and production-proven
  with immutable receipts — W1-C proven for the accepted guest production boundary,
  with signed-in persistence/resume BUILT_NOT_PROVEN behind the authorized-principal
  gate — while W2 remains explicitly unstarted and requires a new Chairman/Sol
  commission.
status: parked
program: macro-mastermind-ai
p0: PRODUCT_TRUST_COHERENCE
repos: [macro, terminal]
owner: ceo-sol
class: build
blast_radius: user_facing
ambiguity: specified
owns_paths:
  - research/DEEPVUE_*
  - engine/intelligence_workspace/
  - contracts/intelligence_workspace/
  - config/intelligence_workspace/
  - engine/neuralweb/native_facts.py
  - scripts/brain_latency_bench.py
  - tests/test_datapoint_registry.py
  - tests/test_intelligence_workspace_*
  - tests/test_brain_instant_lane.py
waves:
  - id: W0-B
    title: Frozen before-state production benchmark
    status: done
    pr: 6359
    next_action: >
      Done. Preserve the private mode-0600 prompt, answer, receipt and score artifacts by
      digest; never overwrite or retrospectively rescore the before state.
  - id: W1-A
    title: Typed datapoint registry and resolver
    status: done
    pr: 6321
    next_action: >
      Done. The twelve-field registry, entity identity, status/null/stale/rights law and
      owner references are frozen at semantic digest
      7dff09b790f9f789dfeed80781a7fb62bc138ad4bf801d81664d471c4508d4cf.
  - id: W1-B
    title: Instant native facts through Brain
    status: done
    pr: [6359, 6368]
    depends_on: [W1-A]
    next_action: >
      Done. Preserve the exact live receipt in
      research/DEEPVUE_W0B_W1B_NATIVE_FACTS_VALIDATION_RECEIPT_2026-08-24.md;
      do not hide the warm-p95 or multi-field assembly misses.
  - id: W1-C
    title: Visible context compiler and effective-context receipt
    status: done
    depends_on: [W1-B]
    pr: [6421, 6428, 6430]
    next_action: >
      Done under the explicit Sol commission of 2026-08-25 (Macro merges cdd2b99dcdde,
      d00ca51e0f0c, e79586728194; Terminal mastermind-terminal#473 merge 580de03e7a75).
      Contract frozen in research/DEEPVUE_W1C_CONTEXT_ENVELOPE_CONTRACT_2026-08-25.md;
      delivery receipt in research/DEEPVUE_W1C_VALIDATION_RECEIPT_2026-08-26.md.
      Signed-in production persistence/resume remains BUILT_NOT_PROVEN behind the
      external principal gate. W2 stays unstarted pending a new explicit commission.
  - id: W2-A
    title: Versioned workspace schema and lossless migration
    status: done
    depends_on: [W1-C]
    pr: [6473]
    next_action: >
      Done under the explicit Sol commission of 2026-08-26 (Macro #6473 merge
      f507a25aee69; Terminal mastermind-terminal#480 merge b1b21a17f843; deployed
      2026-08-27T06:11Z). Contract + Amendments A1-A3 frozen in
      research/DEEPVUE_W2A_WORKSPACE_LAYOUT_CONTRACT_2026-08-26.md; delivery
      receipt research/DEEPVUE_W2A_VALIDATION_RECEIPT_2026-08-27.md; golden-vector
      digest 3e7c1c50faf8b03b4fa2f3ad2c66db3ebf9ba3ebd93bbb15b228654c382ff339
      pinned in both repos. Guest production surface PROVEN_LIVE; the signed-in
      persisted-user journeys remain BUILT_NOT_PROVEN behind the external
      authorized-principal gate. W2-B stays unstarted pending a new explicit
      commission.
landmines:
  - >-
    The W1-A architecture freeze is binding: no second registry, resolver, identity
    system, owner, rights plane, result store, persistent fact cache, Brain service or
    retry/control plane.
  - >-
    Industry rank is a fact about the current industry entity; member RS percentile is
    a fact about the security. Their typed entities, fingerprints and relationship proof
    cannot be swapped.
  - >-
    Production checkout advances every three minutes and main moves frequently. The W0-B
    harness correctly writes no evidence if checkout changes during a corpus.
  - >-
    A green single latency is not p95 acceptance. W1-B measured a 3,999 ms warm TTFV p95
    and 4,006 ms completion p95 against targets of 1.5 s and 3 s.
do_not_redo:
  - Do not rebuild the twelve-field W1-A registry or copy its owner calculations into Brain.
  - Do not add a value cache to make the W1-B latency table look green.
  - Do not overwrite, append to, reveal or silently rescore the private W0-B artifacts.
  - Do not treat W1-B as authority to begin W1-C, W2, screener AST, ratings, alerts, Prophet or Fusion work.
  - Do not answer unsupported history, comparisons, forecasts, targets or multi-symbol ambiguity with partial native facts.
artifacts:
  - research/DEEPVUE_COMPETITIVE_TEARDOWN_AND_MASTERMIND_BUILD_DOCKET_2026-08-01.md
  - research/DEEPVUE_CLEAN_ROOM_REMAINING_WAVES_HANDOFF_FOR_CLAUDE.md
  - research/DEEPVUE_W1A_TYPED_DATAPOINT_CONTRACT_2026-08-23.md
  - research/DEEPVUE_W1A_TYPED_DATAPOINT_VALIDATION_RECEIPT_2026-08-23.md
  - research/DEEPVUE_W0B_W1B_NATIVE_FACTS_VALIDATION_RECEIPT_2026-08-24.md
  - research/DEEPVUE_W2A_WORKSPACE_LAYOUT_CONTRACT_2026-08-26.md
  - research/DEEPVUE_W2A_VALIDATION_RECEIPT_2026-08-27.md
next_action: >
  Return W2-A to Sol and remain parked. W2-B (semantic link-group propagation)
  and later waves require their own explicit Chairman/Sol commission. Open
  external gate: an authorized signed-in production principal (plus a second
  account for the cross-account half) to execute the persisted-user production
  journeys for both the W1-C resume residual and the W2-A save/reopen/rename/
  duplicate/import/export/stale-fork/isolation proofs. The W1-B latency and
  deep-provider residuals remain separate bounded authorities.
---

## Parked boundary

W0-B, W1-A, W1-B, W1-C and W2-A are complete. W2-B is a named future wave, not
live authority. The live capability set (deterministic visible context with
receipts; one versioned `workspace_layout.v1` law with lossless migration, CAS
persistence over the single `chart_layouts` owner, and a generic chart+brain
widget graph with workspace management UX) is production-proven for guest
principals; every signed-in persisted-user journey is BUILT_NOT_PROVEN behind
the external authorized-principal gate. Latency residuals remain visible rather
than converted into a second owner or cache.
