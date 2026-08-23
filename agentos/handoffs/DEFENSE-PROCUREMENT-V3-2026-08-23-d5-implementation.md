---
workstream: WS-DEFENSE-PROCUREMENT-V3
date: 2026-08-23
session: d5-implementation (Sol commission 2026-08-23; authorization receipt = macro PR #6247 comment 5384728488)
prs: [PENDING]
status: in_progress
---

# D5 implementation — Virginia-class Program Dossier (end-to-end vertical)

Sol accepted D5R (chain #6209 + #6219 + #6247) and authorized D5 implementation.
This session shipped the full vertical: frozen contracts → engine loader/derivations
→ propose/curate admission → REAL pilot admission with receipted evidence →
composed dossier bundle → workspace program_link → mode=programs surface →
T1–T17 merge-gating battery.

## What shipped

- `contracts/government_revenue/government_program_ontology.v1.schema.json` — the
  frozen seventeen-key skeleton (additionalProperties: false, const
  schema_version "1.0.0", strict `YYYY-MM-DDTHH:MM:SS+00:00` timestamp pin).
- `contracts/government_revenue/government_program_dossier.v1.schema.json` — the
  nine-key composed bundle contract (`gpd1-` content ids).
- `engine/government_revenue/program_ontology.py` — OntologyInputError
  accumulate-then-refuse loader; exhaustive sha12 preimage registry; temporal /
  succession / referential-closure / evidence-admissibility law; derivation
  layer (`derive_review_coverage`, `derive_workspace_program_link`).
- `engine/government_revenue/program_dossier.py` — read-only composer of the
  seven frozen rails (ontology + workspace freshness + identity atlas).
- `scripts/propose_government_program_ontology.py` /
  `scripts/curate_government_program_ontology.py` — two-script admission with
  the §3.1a evidence lifecycle (append-only, widening-only claim_scopes,
  `evidence_receipt_mismatch`), evidence applied same-act BEFORE dependent
  candidates; curate is the ONLY producer of `review_coverage` rows.
- `engine/government_revenue/workspace.py` — the single `program_link` field
  emission; `engine/government_revenue/award_events.py` — the one
  `unverified_supplier_language` annotation.
- `scripts/build_government_revenue.py` — composer wiring + D5 twins
  (program-dossier.json / program-ontology.json site twins).
- `templates/government_revenue.html.j2` + `templates/government-revenue-dossiers.js`
  — `mode=programs` Program Dossier view (first-screen six answers, typed
  states, EN/ZH, inspector tier, IRDM hostile-null rendering, entitlement
  teaser), inside the 296 KiB RAW_HTML_BUDGET_BYTES ratchet (NOT raised).
- `tests/test_government_program_ontology.py` +
  `tests/test_government_program_ontology_scripts.py` + frozen fixtures — the
  full T1–T17 adversarial battery as `gate: code`, wired via the
  `govrev-program-ontology` job in `.github/ci/legacy-jobs.yml`.
- `research/government_revenue/PROGRAM_ONTOLOGY_REVIEW_2026-08-23_virginia_pilot.json`
  — the pilot admission worksheet (6 evidence receipts, 8 canonical admits,
  1 deliberate reject, 6 coverage rows).
- `data/government_revenue/program_ontology.json` — the CANONICAL curate output
  (graph `program-ontology:reviewed:2026-08-23:virginia-pilot`; admitted=14,
  rejected=1, coverage_rows=6). Never hand-edit; re-admission goes through a
  new worksheet + curate.

## Pilot truth admitted (all evidence re-fetched with byte receipts)

- Program `acq-program:virginia-class-ssn` (phase production, sponsor
  "Department of the Navy"; P-1 + contract-announcement + CRS identities).
- Capability `acq-capability:undersea-warfare` + link `prog-cap:06be4ffa4506`.
- Platform `platform:virginia-block-vi` ("SSN 814-822 (Block VI)").
- Roles: GD/EB `prime_contractor` (`prog-role:c483832bff9d`), HII
  `teaming_partner` (`prog-role:11f019cb0e31`), BWXT NOG `supplier` with
  `shared_scope: true` (`prog-role:d9b93b4439c3`) — labels follow the
  re-fetched documents (CRS "the program's prime contractor"; BWXT release
  attributes work to BWXT Nuclear Operations Group, Inc.).
- Milestone `prog-milestone:a904b5338b54` — AUKUS Pillar 1 first boat sale,
  window FY2032 (2031-10-01..2032-09-30), from CRS RL32418 (2026-01-26):
  "The first two boats, which are to be sold in FY2032 and FY2035…".
- Evidence hosts: war.gov article 4559059 (sha 5c58e0261d10…, in-browser
  fetch — Akamai 403s ALL CLI fetches), CRS RL32418 2026-01-26 PDF
  (everycrsreport mirror; crsreports.congress.gov cited as host of record),
  GD IR (investorrelations.gd.com), BWXT (www.bwxt.com), Navy FY2011 SCN
  book (globalsecurity mirror; secnav FMB office of record), HII (www.hii.com).

## Verified claims (each names its command)

- `python3 -m pytest tests/test_government_program_ontology.py
  tests/test_government_program_ontology_scripts.py -q` → 82 passed, 1 skipped
  pre-surface (the T5 template stub; replaced by the surface packet).
- Fixture-id cross-check: every id in
  `research/defense_intelligence/evidence/fixtures/d5-representability-fixtures.json`
  recomputes byte-identically (test_representability_fixture_ids_recompute).
- Freeze §3.0 reference JSON validates against the schema and loads clean.
- `scripts/check_contract_delta.py --base 8dd65a56c29b` → 0 introduced.
- Real pilot: `curate … --check` → admitted=14 rejected=1 coverage_rows=6
  (pinned as a regression test); real run published the canonical artifact,
  loader certifies it, and:
  - IRDM P00032 (`govws-a6c70850a9cbdce9fa3e7f3b`) derives the EXACT
    five-key shape `{state: reviewed_none, reason_code:
    no_reviewed_program_link, program_id: null, program_event_link_id: null,
    ontology_graph_id: …}`.
  - Dossier bundle `gpd1-bc050c9d910dc64613e8146a`: program_identity reviewed
    (latest block "Virginia class Block VI (SSN 814-822)"), capability
    reviewed, awards `current`/`reviewed_none`, budget `projection_missing`,
    participants reviewed ×3 (all `verified_live`, central:GD/HII/BWXT),
    economic_relationships `not_asserted`, milestones reviewed (FY2032 window).
- Fresh-main Virginia event census (2026-08-23, head 59fed333): NO
  `government_procurement_event.v2` row for the July-29 Block VI award —
  workspace 500-event window + all four parquet tables + dossiers.json
  exhaustively searched; near-miss `govws-71970a2665b504ab4b4a10eb` adjudicated
  (2017-11-06 $1.7M historical action; rejected with ledger row).

## do_not_redo

- Do not re-run the pilot evidence fetches — receipts (sha256 + host + clock)
  are inside the committed worksheet; re-fetch only for NEW admissions.
- Do not hand-edit `data/government_revenue/program_ontology.json` — worksheet +
  curate is the only write path.
- Do not "fix" the awards-rail gap by building a DoD announcements collector
  (D6 source-rail gap, recorded) or by calling the July-29 announcement a
  GovRev event.
- The $42.1B figure is GD-IR truth, NOT war.gov-announcement truth — the
  official announcement carries no total; do not re-attribute.
- Do not reopen the D5R freeze (owner ruling, pilot, IRDM null, preimage law).

## danger_areas

- war.gov / defense.gov / comptroller / congress.gov 403 ALL CLI fetches (TLS
  fingerprint). Evidence re-fetch needs the entitled browser path (in-page
  fetch + crypto.subtle sha256). secnav.navy.mil rejects everything.
- `derive_*` APIs take a timezone-aware datetime `analysis_as_of` (end-of-day
  coerced), never a bare date string.
- Freeze under-specification recorded: `temporal_incompatible` for a link vs a
  multi-revision logical endpoint — implemented as "overlaps at least one
  revision of each endpoint" (builder deviation 2; candidate for a D5R
  clarification note, not silently reopened).
- The production `build_procurement_workspace` call lives in
  `engine/government_revenue/metrics.py` (unowned) — program_link wiring is
  post-processing in `scripts/build_government_revenue.py` instead.

## Next action

Surface packet review → PR → CI → same-day squash-merge → render coverage →
entitled production proof (Virginia route live at 1440/820/390 EN/ZH, IRDM
hostile null live, /api/health checkout covering the merge) → then WS D5 →
done / Sol acceptance pending, and return the complete receipt to Sol.
D6+ remains UNAUTHORIZED.
