---
workstream: WS:DEFENSE-PROCUREMENT-V3
session: claude/dod-budget-d6a
model: fable
ended_because: complete
prs: [6377, 6378]
decisions: []
discoveries:
  - DSC:DOD-COMPTROLLER-HOST-MIGRATED-TO-WAR-GOV
mission: >
  Sol commission D6-A (authorization: macro PR #6355 comment 5395051048,
  Chairman sequencing amendment): activate the EXISTING DoD budget plane —
  official Comptroller FY2027 P-1/R-1 PDF → canonical R2 immutable store with
  readback proof → deterministic receipt-bound extraction → append-only source
  triad → government_budget_program_graph.v1 → existing Budget & Programs
  API/UI → production proof. No new budget system; no D5 contract widening;
  semantic firewall absolute (request ≠ authorization ≠ appropriation ≠
  execution ≠ obligation ≠ award ≠ revenue).
state_before: >
  Pickup main 571b48d497cd4e9b5d8be532aa1d4943485e16b7 claimed
  2026-08-24T14:33:45Z. Budget plane deliberately PROJECTION_MISSING: hermetic
  fixture-only foundation (Wave 8), DOD_BUDGET_PRODUCTION_ACTIVATION_ENABLED =
  False at collectors/dod_budget.py:37, triad absent at HEAD, no live
  acquisition/extraction, publication hard-raising. Fresh collision census
  clean. D5 closed for sequencing at BUILT_NOT_PROVEN per the Chairman
  amendment.
changed:
  - path: research/defense_intelligence/DEFENSE_D6A_BUDGET_RAIL_DESIGN_2026-08-24.md
    what: >
      Frozen design: source census (war.gov host migration; FY2027 canaries
      with pinned sha256s), semantic mapping (5-member enum preserved; FY2027
      "Mandatory Request" → reconciliation_request; "FY 2026 Total" →
      prior_year_enacted_reference; two FY2026 sub-cells deliberately
      unextracted), acquisition order law, §5b/§5b.1 row model (survey-proven;
      E-7 shape revised to all-null after adversarial review).
  - path: collectors/dod_budget_live.py
    what: >
      NEW production module: allowlisted fetch (no redirects, size cap, %PDF
      magic), R2 put + strict bounded readback + byte/sha equality before any
      receipt, deterministic pdfplumber text+words extraction, production
      P-1/R-1 parsers per §5b/§5b.1 (boundary buckets, closed row taxonomy,
      per-side BA tracking, keyed page-pair joins, printed-addend grain,
      positional component capture, 0400D consolidated-only), idempotence
      gate, all-or-nothing atomic triad CLI.
  - path: collectors/dod_budget.py
    what: >
      Publisher constant → "Office of the Under Secretary of War
      (Comptroller)" (source-native FY2027 self-identification); all five
      amount semantics nullable (blank ⇒ None, printed 0 ⇒ 0.0); public
      normalization wrappers; line identity gains the budget-activity slug
      (both exhibits; R-1 genuinely reuses one PE across BAs — 29 real
      collisions); DOD_BUDGET_PRODUCTION_ACTIVATION_ENABLED = True.
  - path: data/government_revenue/ (triad)
    what: >
      REAL production triad committed by the dispatched runner acquisition
      (run 32764547804, commit 94ab73114336): 2 receipts, 2,172 line
      snapshots (P-1 1,009/81 totals; R-1 1,163/48 totals),
      projection_generation_id dod-budget-401e0479c00c449c3b4bd7e0.
  - path: .github/workflows/dod-budget-acquire.yml (PR 6378, merged separately)
    what: >
      Dispatch-only acquisition lane (no schedule; annual source), canary
      URLs in reviewed code, triad-files-only commit guard, shared
      government-revenue-live concurrency group; publishes nothing.
  - path: engine/government_revenue/budget_program.py
    what: limitations[0] rewritten to the truth of the activated rail.
  - path: app/government_revenue.py
    what: >
      _public_budget_line passes through the receipt-validated publisher
      instead of a hardcoded Defense-era literal.
  - path: templates/government-revenue-dossiers.js (+ site twin)
    what: >
      reconciliation_request card label → "Mandatory request / 强制性请求"
      (source-native FY2027 column); semantic key unchanged.
  - path: tests/ (test_dod_budget_live.py new; collector/build/api updates)
    what: >
      Hostile law battery per commission §7 + §5b.1 rulings, wired
      merge-binding into .github/ci/legacy-jobs.yml unrun-government-revenue
      (contract-delta gate satisfied); 114 passing in the budget selection.
  - path: agentos/ + research/defense_intelligence/D0R_SOURCE_RIGHTS_AND_PIT_REGISTRY.md
    what: >
      WS record amended per the Chairman sequencing amendment (D5 closed for
      sequencing, BUILT_NOT_PROVEN, D5P deferred/nonblocking; D6-A
      in_progress); DSC minted for the host migration; D0R registry re-census
      row added.
verified:
  - claim: Production acquisition fetched the exact pinned canaries and proved R2 readback
    command: gh run view 32764547804 --log (acquire step)
    result: >
      success; p1 content_sha256 b8d5248257590856ee33ddb1b401ec2efcdfea219c05b5bc8ea1068d9000d0a6,
      r1 1aa8846edb69d4c3a54e03b383b0cabb77f93433162b8139ab8cbb55bcc7882a —
      byte-identical to the design-doc pins; object keys
      government-revenue/dod-budget/pdf/sha256/<sha>.pdf; both NEW.
  - claim: Committed triad carries both canary lines with lawful values
    command: python3 json scan of data/government_revenue/dod_budget_line_snapshots.jsonl
    result: >
      Virginia dod:p1:department-of-the-navy:1611n:p1-line-item:6:02:fy2027
      FY27 disc/total 8,402,316,000 (printed net-memo row); New Design SSN
      dod:r1:department-of-the-navy:1319n:program-element:0604558n:05:fy2027
      FY27 total 237,103,000.
  - claim: Budget graph builds and validates from the committed triad
    command: scripts.build_government_revenue._build_budget_program_graph_if_ready(root, as_of=<date>, dossier=...)
    result: >
      content_id grbg1-125cd95cc0e78c5f459c1ad2; 2,143 programs / 2,172
      lines / 2,172 edges; truthful limitations text; Virginia program nodes
      (line 6 + AP line 7) and 0604558N present.
  - claim: Budget test battery green
    command: python3 -m pytest -q tests/test_dod_budget_collector.py tests/test_dod_budget_live.py tests/test_build_government_revenue.py tests/test_government_revenue_budget_graph.py tests/test_government_revenue_api.py
    result: 114 passed.
  - claim: Adversarial review completed and every finding repaired or ruled
    command: opus reviewer packet + repair commit e0095c1299f1 (mutation proofs quoted therein)
    result: >
      2 blockers (component leakage; E-7 implicit-zero) + 8 findings fixed
      with biting tests; component census now {Department of the
      Army/Navy/Air Force, Defense-Wide, Defense Health Agency, Inspector
      General}, zero "War"; retraction path deliberately deferred (see
      unresolved).
  - claim: Idempotent re-observation is a no-op
    command: local rehearsal double-run + runner NOOP path
    result: second run byte-identical, both exhibits NOOP, counts unchanged.
unverified:
  - claim: Production API serves nonzero budget programs and the Budget & Programs page renders the canaries
    what_would_verify: >
      post-merge government-revenue-live run commits the graph twins; then
      GET /api/government-revenue/budget-programs (nonzero) +
      /api/government-revenue/budget-line/<canary keys> + served
      site/government-revenue-data/budget-program.json bytes + anonymous 401
      boundary unchanged. Owned by this session immediately after merge.
unresolved:
  - >
    NO RETRACTION PATH for superseded parser generations (review MEDIUM 9,
    ruled a named unresolved): append_line_snapshot_versions is append-only
    and the graph serves the newest version per line_key, so a line a future
    parser generation stops emitting would persist. Binding constraint: any
    future parser_version bump must first design generation
    scoping/tombstones. Zero production risk today (first and only
    generation).
  - >
    FY2026 Discretionary-Enacted and PL 119-21 Spend Plan sub-cells are not
    representable in the frozen 5-semantic contract (deliberately
    unextracted). Enum widening is a separate Sol decision.
  - >
    E-7-shape (§5b.1(7)) publishes all-null amounts; the implicit-zero
    alternative was rejected as a computed sum. Both rationales go to Sol
    for ratification.
  - >
    Zero-numbered-line partitions (1612N BA01 NSBDF full-funding rows) are
    verification-only, not at line grain — named product gap.
  - >
    P-1 wrapped-nomenclature names that break BACKWARD onto a prior line
    render truncated (display-only; identity/amounts unaffected).
next_actions:
  - Post-merge: watch government-revenue-live publish the twins; production-prove API + page + anonymous boundary; report receipts to Sol.
  - Return to Sol with the full acceptance package (this handoff + PR #6377 + run 32764547804 receipts). D6-B+ and D7+ remain unauthorized.
do_not_redo:
  - Do not re-census the Comptroller surface from scratch; verify against the 2026-08-24 receipted census (war.gov; comptroller.defense.gov 403s permanently, no redirect).
  - Do not widen AMOUNT_SEMANTICS, touch D5 budget_program_keys (const []), or create a second budget publisher/store plane.
  - Do not bump the live parser/extractor version without first designing the retraction/generation-scoping mechanism (unresolved #1).
  - Do not use PyMuPDF in the production path (AGPL ruling; pdfplumber is frozen).
  - Do not re-run the acquisition expecting changes — same bytes are an idempotent NOOP by design; new official bytes append a NEW observation.
danger_areas:
  - The SCN/shipbuilding row model (§5b.1) is the load-bearing subtlety — parenthesized gross values are memo, the printed net-memo row on the FOLLOWING page carries the additive value; never "fix" a parenthesized value into a negative amount.
  - government-revenue-live shares one concurrency group with dod-budget-acquire; never cancel its runs (hook-enforced).
  - The p.158 pinned anomaly table is exact-tuple-scoped to document sha b8d52482…; a NEW FY document with text glitches must mint its own pinned entries, never widen matching.
---
