---
workstream: WS:DEFENSE-PROCUREMENT-V3
session: claude/d5-implementation
model: fable
ended_because: complete
prs: []
decisions: []
discoveries: []

mission: >
  Sol commission 2026-08-23 (authorization receipt = macro PR 6247 comment
  5384728488): D5R accepted (chain 6209 + 6219 + 6247), D5 implementation
  AUTHORIZED, D6+ unauthorized. Ship one independently useful
  Virginia-class Program Dossier end to end — reviewed
  government_program_ontology.v1 → composed government_program_dossier.v1
  → workspace program_link → real mode=programs GovRev surface → entitled
  browser proof — with IRDM/P00032 the live hostile null and D1-D4 truth
  unchanged. T1-T17 as merge-gating gate: code tests. No page-budget
  ratchet raise.

state_before: >
  D5R sealed on main (freeze + implementation handoff + fixtures A-I,
  PR 6247 = 0ea350fb1946). Zero D5 production code existed: no contracts,
  no engine loader/composer, no admission scripts, no program_link, no
  programs surface, no canonical artifact. Fresh-main preflight
  (head 59fed333c063): no changes to D5-owned paths since 6247, zero open-PR
  collisions, main proven green, and the re-run Virginia census found NO
  government_procurement_event.v2 row for the 2026-07-29 Block VI award
  (workspace 500-event window + all four parquet tables + dossiers.json,
  exhaustive).

changed:
  - path: contracts/government_revenue/government_program_ontology.v1.schema.json
    what: >
      NEW — the frozen seventeen-key skeleton (additionalProperties false,
      const schema_version 1.0.0, graph_id grammar, strict
      YYYY-MM-DDTHH:MM:SS+00:00 timestamp pin, closed enums).
  - path: contracts/government_revenue/government_program_dossier.v1.schema.json
    what: NEW — the nine-key composed bundle contract (gpd1- content ids).
  - path: engine/government_revenue/program_ontology.py
    what: >
      NEW — OntologyInputError accumulate-then-refuse loader; exhaustive
      sha12 preimage registry; temporal/succession/referential-closure/
      evidence-admissibility law; derivation layer (derive_review_coverage,
      derive_workspace_program_link).
  - path: engine/government_revenue/program_dossier.py
    what: >
      NEW — read-only composer of the seven frozen rails from certified
      ontology + workspace freshness + identity atlas.
  - path: scripts/propose_government_program_ontology.py
    what: NEW — discovery script; candidate JSON only; forbidden-provenance rejection.
  - path: scripts/curate_government_program_ontology.py
    what: >
      NEW — worksheet admission (curate is the ONLY producer of
      review_coverage rows) with the §3.1a evidence lifecycle: evidence
      rows admitted same-act BEFORE dependent candidates, widening-only
      claim_scopes union, evidence_receipt_mismatch refusal. Two defects
      (missing evidence admission path; predicate computed pre-act) were
      caught by orchestrator adjudication against the REAL pilot worksheet
      and repaired with regression tests.
  - path: engine/government_revenue/workspace.py
    what: ONLY the single program_link field emission capability.
  - path: engine/government_revenue/award_events.py
    what: ONLY the unverified_supplier_language annotation in the closed _action_text_annotations family.
  - path: scripts/build_government_revenue.py
    what: >
      Composer wiring only — certify canonical ontology, attach
      program_link to workspace award-change events, write the
      program-dossier + program-ontology site twins.
  - path: templates/government_revenue.html.j2
    what: >
      mode=programs Program Dossier view inside the existing page family
      (first-screen six answers, typed states, EN/ZH via t()/tr(),
      inspector tier, IRDM hostile-null rendering, entitlement teaser);
      RAW_HTML_BUDGET_BYTES 296 KiB ratchet NOT raised.
  - path: templates/government-revenue-dossiers.js
    what: programs-mode module beside the budget-mode precedent; site twin synced.
  - path: tests/test_government_program_ontology.py
    what: >
      T1-T17 adversarial battery as gate-code with frozen fixtures (+ render-law halves).
  - path: tests/test_government_program_ontology_scripts.py
    what: propose/curate battery incl. evidence-lifecycle regressions + the pilot-worksheet pin (admitted=14 rejected=1 coverage_rows=6).
  - path: .github/ci/legacy-jobs.yml
    what: >
      NEW govrev-program-ontology job, gate-code, merge-binding.
  - path: research/government_revenue/PROGRAM_ONTOLOGY_REVIEW_2026-08-23_virginia_pilot.json
    what: >
      The pilot admission worksheet — 6 evidence receipts (war.gov article
      4559059 sha 5c58e0261d10, CRS RL32418 2026-01-26, GD IR, BWXT, Navy
      FY2011 SCN book, HII), program + capability + platform records,
      prog-cap link, 3 role assertions (GD prime_contractor, HII
      teaming_partner, BWXT NOG supplier shared_scope), AUKUS FY2032
      milestone, near-miss event reject, 6 coverage rows.
  - path: data/government_revenue/program_ontology.json
    what: >
      CANONICAL curate output (graph
      program-ontology:reviewed:2026-08-23:virginia-pilot; admitted=14
      rejected=1 coverage_rows=6). Never hand-edited.
  - path: agentos/workstreams/WS-DEFENSE-PROCUREMENT-V3.md
    what: D5R done/Sol-accepted; D5 in_progress under authorization; fixtures shorthand A-H corrected to A-I.
  - path: research/defense_intelligence/DEFENSE_D5_PROGRAM_GRAPH_IMPLEMENTATION_HANDOFF.md
    what: >
      §3 registry war.gov row upgraded to VERIFIED with the browser-fetch
      sha receipt; combined Columbia+Virginia award reality recorded (no
      $42.1B figure in the official announcement — that figure is GD-IR
      truth).

verified:
  - claim: T battery green
    command: python3 -m pytest tests/test_government_program_ontology.py tests/test_government_program_ontology_scripts.py -q
  - claim: every fixture id in d5-representability-fixtures.json recomputes byte-identically
    command: pytest tests/test_government_program_ontology.py -k representability_fixture_ids -q
  - claim: freeze §3.0 reference JSON validates against the schema and loads clean
    command: pytest tests/test_government_program_ontology.py -k reference_object_validates -q
  - claim: contract-delta clean
    command: python3 scripts/check_contract_delta.py --base 8dd65a56c29b
  - claim: pilot admission published and certified
    command: python3 scripts/curate_government_program_ontology.py --worksheet research/government_revenue/PROGRAM_ONTOLOGY_REVIEW_2026-08-23_virginia_pilot.json --graph-id program-ontology:reviewed:2026-08-23:virginia-pilot --graph-known-at 2026-08-23T07:50:00+00:00 --graph-effective-at 2026-08-23T07:50:00+00:00 --workspace data/government_revenue/workspace.json
  - claim: >
      IRDM P00032 derives the exact five-key reviewed_none shape with
      no_reviewed_program_link
    command: python3 -c derive_workspace_program_link(graph, event_id=govws-a6c70850a9cbdce9fa3e7f3b, ...) (see session transcript; also T1)
  - claim: >
      dossier bundle composes — gpd1-bc050c9d910dc64613e8146a; program_identity
      reviewed (latest block Virginia class Block VI), capability reviewed,
      awards current/reviewed_none, budget projection_missing, participants
      reviewed x3 all verified_live (central GD/HII/BWXT),
      economic_relationships not_asserted, milestones reviewed (AUKUS FY2032 window)
    command: python3 -c compose_program_dossier_bundle(...) (see session transcript)
  - claim: no Virginia Block VI v2 event exists on fresh main
    command: census over git show origin/main data/government_revenue/{workspace.json,4 parquet tables,dossiers.json} (scout packet in session transcript)
  - claim: every pilot deciding quote exists in the receipted bytes
    command: grep over the saved evidence files (crs_pdf.txt line 1145 AUKUS, GD $42.1B, BWXT NOG, HII Block VI title, P-1 lines 27-28)

unverified:
  - Production proof items pending merge + render: entitled Virginia route live, IRDM null live, /api/health checkout covering the merge, 1440/820/390 EN/ZH crops.

unresolved:
  - Freeze under-specification (recorded, not silently decided): temporal_incompatible for a link vs a multi-revision logical endpoint — implemented as "overlaps at least one revision of each endpoint"; candidate for a one-line D5R clarification.
  - FY2026 SCN book parsing stays a D6 dependency (PDF portfolio); MSAR identity stays NOT LOCATED (candidate source_identity only).
  - Awards-rail source gap for the July-29 Block VI award recorded for D6 (no announcements collector in D5 by law).

next_actions:
  - Complete the ship loop on the implementation PR (CI green → same-day squash-merge → render coverage → entitled production proof), then set WS D5 = done / Sol acceptance pending and return the complete receipt to Sol. D6+ stays unauthorized.

do_not_redo:
  - Do not re-run the pilot evidence fetches — receipts (sha256 + host + clock) are in the committed worksheet; re-fetch only for NEW admissions.
  - Do not hand-edit data/government_revenue/program_ontology.json — worksheet + curate is the only write path.
  - Do not build a DoD announcements collector or call the July-29 announcement a GovRev event — the awards-rail gap is the honest state.
  - Do not attribute the $42.1B figure to the official announcement — it is GD-IR truth; the war.gov paragraph enumerates ~$11.878B obligated at award.
  - Do not reopen the D5R freeze (owner ruling, pilot choice, IRDM null, preimage law).

danger_areas:
  - war.gov/defense.gov/comptroller/congress.gov 403 ALL CLI fetches (TLS fingerprint); secnav.navy.mil rejects everything. Evidence re-fetch needs the entitled browser path (in-page fetch + crypto.subtle sha256); memory akamai-gov-hosts-need-in-browser-fetch-receipts.
  - derive_* APIs take a timezone-aware datetime analysis_as_of (end-of-day coerced), never a bare date string.
  - The production build_procurement_workspace call lives in engine/government_revenue/metrics.py (unowned) — program_link wiring is post-processing in scripts/build_government_revenue.py.
  - Curate applies evidence rows same-act BEFORE dependent candidates; reordering that breaks the dual-scope predicate law.
---

# D5 implementation — Virginia-class Program Dossier (end-to-end vertical)

Body intentionally brief: the frontmatter carries the record. The engine +
admission + surface vertical shipped in one PR (number in `prs:`); the pilot
truth was admitted from re-fetched, byte-receipted documents only; the IRDM
hostile null and every typed gap render from artifact-derived states, never
from prose.
