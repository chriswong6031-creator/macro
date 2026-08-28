---
workstream: "WS:ALPHA-INTELLIGENCE-INTEGRATION"
session: claude/k2c-institutional-adapter-20260827
model: fable
ended_because: complete
mission: >
  Execute operation alpha-k2c-institutional-adapter-20260826-sol-001: one
  bounded, read-only K2-C vertical from the canonical institutional 13F owner
  into accepted K1 EvidenceRef + K2-B Manager Research Intent, proving a real
  two-period manager-complex × security observation without a second
  institutional store, reader, identity plane, correction plane, scheduler,
  ranker, grader, or authority surface.
state_before: >
  K2-B contract-only on main (squash 7211d0cd); K2-C NOT_BUILT; commission
  packet merged as 6758a506. Pickup main 13b9660f; collision census clean (no
  K2-C PR/branch; only the merged commission branch mentioned K2-C). The
  rolling census lane was failing on SEC filing-index parses since ~08-25
  (separate outage, flagged separately) — historical catalog generations remain
  immutable and readable.
changed:
  - path: lib/institutional_intelligence.py
    what: >
      K2-B v1.1.0: new closed evidence_basis source_backed_owner_row with
      owner_row_binding semantic law (four listed-ref equality-checked
      sub-bindings, per-store PINNED availability clocks, freshness clock-field
      pinning, per-ref PIT states via owner_row_reference_states, primary-ref =
      current raw receipt, subject/cusip parity, strictly increasing periods).
  - path: contracts/institutional_intelligence/manager_intent_recipe.v1.schema.json
    what: >
      Additive schema for the new basis + ownerRowBinding defs; if/then/else
      forbids the binding on every other basis; existing fixtures byte-unchanged.
  - path: lib/institutional_13f_adapter.py
    what: >
      New read-only adapter composing ONLY existing owner APIs
      (load_catalog_generation, load_raw_evidence, read-side models) into a
      deterministic institutional_intelligence.owner_read_receipt/v1 with an
      embedded re-compilable recipe; typed refusal states; CLI matching the
      proof lane. No store writes, no persistence, no compiler-field authorship.
  - path: .github/workflows/smart-money-13f-k2c-pilot.yml
    what: >
      Dispatch-only, main-gated, read-only production owner-read proof lane
      (census-style pinned venv; own lock file
      requirements/institutional-13f-k2c-pilot-macos-arm64-py312.lock). SCOPE
      ADDITION beyond the commission's named surface, flagged to Sol: the only
      authorized production-read principal is repo CI (verified no local
      credential store exists).
  - path: tests/test_institutional_manager_intent_contract.py
    what: "K2-B suite 50→71 tests (owner-row falsifiers incl. forged-clock attacks)."
  - path: tests/test_institutional_13f_adapter_contract.py
    what: "New 30-test adapter suite over owner-published LocalStore fixtures."
  - path: research/alpha_intelligence/K2C_INSTITUTIONAL_ADAPTER_PILOT_2026-08-27.md
    what: "Design freeze, adoption map, adversarial-review record, proof-receipt section."
  - path: agentos/decisions/DEC-K2C-SECURITY-BINDING-IS-OWNER-NATIVE-CUSIP.md
    what: "Identity ruling: owner-native CUSIP subject; Data OS axis typed unresolved."
verified:
  - claim: "No second store/reader/identity/correction plane; adapter composes owner APIs only."
    command: "Adversarial review axis G: no publish_*/put/create/delete call path in lib/institutional_13f_adapter.py; only get_bytes_strict_bounded via owner readers."
    result: "cleared"
  - claim: "Forged availability clocks can no longer compile hindsight positives."
    command: "Review reproductions repro_a1/repro_a2 re-run after 51ffcc242801"
    result: "validate()-rejected with owner_row_binding_available_clock_conflict:*"
  - claim: "Focused + combined K1/K2-B/K2-C suites green."
    command: "python3 -m pytest <13 focused institutional/K1/K2 test files> -q"
    result: "333 passed (run twice); zero pre-existing test weakened"
  - claim: "Two-period pilot compiles end-to-end on owner-shaped fixtures."
    command: "CLI --local-dir fixture run"
    result: "state PILOT_COMPILED, MANAGER_RESEARCH_INTENT_ELIGIBLE_CONTEXT, exit 0"
unverified:
  - claim: "Real production owner-read (two usable report periods for the chosen subject)."
    what_would_verify: >
      Post-merge dispatch of smart-money-13f-k2c-pilot.yml on main (positive:
      filer 0001792167 Meeder × CUSIP 67066G104 NVIDIA, periods 2026-03-31 /
      2026-06-30 — EDGAR shows clean single-row SOLE/SH holdings both quarters;
      negative: an absent CUSIP). Until that receipt exists the capability is
      BUILT_NOT_PROVEN.
unresolved:
  - "K2-B's closed vehicle_class enum has no truthful class for a generic 13F reporting vehicle; the adapter uses a documented MIXED_OR_UNKNOWN placeholder. Future K2-B vocabulary amendment candidate — deliberately not smuggled into this wave."
  - "No authoritative CUSIP→Data OS security_id plane exists (DEC:K2C-SECURITY-BINDING-IS-OWNER-NATIVE-CUSIP); receipts carry the Data OS axis as typed unresolved."
  - "Rolling census ingestion outage (SEC filing-index parse failures since ~08-25) degrades amendment freshness until repaired; separate lane, chip filed."
next_actions:
  - >
    After squash-merge: dispatch a main ci.yml baseline (workflow edit makes the
    merged head authority-frozen; the main-descendant SUCCESS run is the only
    clearing lever — preflight for an in-flight baseline first).
  - >
    Dispatch smart-money-13f-k2c-pilot.yml on main: positive subject filer_cik
    0001792167 / cusip 67066G104 / periods 2026-03-31 + 2026-06-30; negative
    subject an absent CUSIP. Append both receipts to the design doc §7 and
    return them to Sol on operation key
    alpha-k2c-institutional-adapter-20260826-sol-001.
do_not_redo:
  - "Do not re-derive generation knowability from source_cutoff_at — the pinned catalog availability clock is published_at (review BLOCKER 1)."
  - "Do not present a non-positive compile as PILOT_COMPILED or surface a q-pair the compiler refused (review MAJOR 2)."
  - "Do not emit pointer currency fields on the explicit-generation path (review MAJOR 3)."
  - "Do not enumerate the object-store prefix as generation discovery; historical reads take an explicit caller-retained generation_id."
danger_areas:
  - "The proof lane runs only on main (workflow_dispatch, main-gated). A historical-cutoff production proof requires pinned generation-id inputs."
  - "Combined-suite runs must stay on the 13 focused files; a sparse-tree full pytest run yields mass artifacts."
---

# K2-C implementation carrier handoff

Carrier: branch `claude/k2c-institutional-adapter-20260827` (this PR). Commits:
wave A `2e602e5c` (K2-B basis), session infra `98156272`/`39dcc739` (proof
lane, design freeze, DEC, README), wave B `ffee8e11` (adapter), review repairs
`51ffcc24`, plus final doc/handoff commits. Independent adversarial review ran
against `ffee8e11` (1 BLOCKER / 3 MAJOR, all repaired on-carrier — see design
doc §6b). Post-merge sequence for the resuming session or Sol: (1)
`gh workflow run ci.yml --ref main` after the squash lands (workflow edit ⇒
authority-frozen merged head; the main-descendant baseline is the one clearing
lever — preflight for an in-flight baseline first); (2) dispatch
`smart-money-13f-k2c-pilot.yml` on main for the positive and negative subjects
above; (3) append both receipts to design doc §7 and return them to Sol on
operation key alpha-k2c-institutional-adapter-20260826-sol-001. Only that real
receipt upgrades the capability from BUILT_NOT_PROVEN.
