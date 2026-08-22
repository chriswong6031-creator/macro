# DEFENSE D5 — Program Graph Implementation Handoff

**Status:** D5 implementation is **NOT AUTHORIZED**. This handoff arms a future Sol-authorized D5 session. D6+ not authorized.
**Architecture authority:** `DEFENSE_D5_PROGRAM_GRAPH_ARCHITECTURE_FREEZE.md` (same directory) — precedence is total: freeze > this handoff > DEC records > reference composition; the freeze wins on any conflict, and a discovered conflict is a defect to report, never a silent choice.
**Frozen against:** `origin/main` `33d70f5ce4b36329e8acfb285557f4c9d3c72589` (2026-08-22T02:28Z). Re-fetch fresh main at D5 start; re-check open lanes on the owned paths before writing a line.

---

## §0. Acceptance gates — D5 is NOT DONE UNLESS

1. **Contract + producer shipped under the frozen names** (freeze §3): `government_program_ontology.v1` schema, `propose_/curate_government_program_ontology.py`, `engine/government_revenue/program_ontology.py` — closed keys, `additionalProperties: false`, const `schema_version`, all-false display `AUTHORITY` block, temporal quadruple on every row, `conflicts`/`overrides` collections, propose→curate two-script admission with the output-path guard.
2. **All fourteen adversarial tests T1–T14** (freeze §8) implemented as `gate: code` tests with committed frozen fixtures — never reading nightly-rewritten `site/`/`data/` artifacts (D4 CI-wiring law). T1 (IRDM program-null), T2 (rename byte-identity), T13 (host refusal), and T14 (role-id collision) are the ones that most often die in review: implement them first.
3. **Virginia-class pilot admitted end-to-end with receipted evidence**: program + capability + platform (Block VI variant) + three role assertions + the milestones rail in a **valid state** — a reviewed FORWARD milestone (candidate: the AUKUS Pillar-1 early-2030s window, per freeze §7.1) if an admissible source survives review, else `not_reviewed`/`reviewed_none` as an honest production outcome. **The 2026-07-29 Block VI award is the GovRev/D3 "what changed" event and is NEVER admitted as a D5 milestone** (freeze §3.1 forward-only law). Every admission backed by an actually-fetched document with sha256 + `source_url` (host of record) + `retrieved_from_url` + retrieved_at receipt and a human-review worksheet, under the freeze §3.1a admissibility gates. **Role labels are whatever the re-fetched documents support** — the evidence-based expectation is GD/EB `prime_contractor` on `legal:gd:electric-boat-corp`, HII `teaming_partner` on `legal:hii:huntington-ingalls-inc` (NNS is a division — `role_scope` prose, never an entity id), BWXT `supplier` with `shared_scope: true` on the entity the document names as performing the work (parent `legal:bwxt:bwx-technologies-inc` vs `legal:bwxt:bwxt-nuclear-operations-group-inc` — the worksheet records the deciding sentence) — but a re-fetched document that supports a different closed-enum label wins. **Search-synthesis evidence from D5R (§3 below) is NOT admissible** — re-fetch each document (entitled browser path for 403-hostile .mil hosts) before review.
4. **IRDM negative control live**: the production IRDM route renders `Program relationship: unresolved / not asserted` with `reason_code: no_reviewed_program_link` (the new program-rail-scoped code — NEVER the atlas's `no_reviewed_exact_path`, whose bound copy is recipient-identity prose); every D1–D4 rail byte-unchanged (T1 as a production check, not only a fixture test).
5. **Dossier read model + surface shipped**: `government_program_dossier.v1` composed by `engine/government_revenue/program_dossier.py`; surface = a `mode=programs` view inside the existing `government_revenue.html` page family (underscore route; no new header; nav via the existing family only). Anonymous = locked/teaser per the existing paywall plane; entitled = full dossier. The 296 KiB `RAW_HTML_BUDGET_BYTES` ratchet on `government_revenue.html` is live — bake locally (`scripts/build_government_revenue._write_site_projection`) before merging template edits; D3's first cut left 65 bytes of headroom.
6. **Typed states rendered, never blanks** (freeze §4/§6): budget `projection_missing`, GMI rail `not_asserted`, review-gated rails split `not_reviewed` vs `reviewed_none` (never coerced), `conflicted` on conflict rows, BOTH participants-rail limitation strings verbatim (freeze §4: `participation_limitation` + `allocation_limitation`), plain-word EN/ZH copy keyed off machine enums in the template with rail-scoped copy keys (program rail and atlas rail must never share a copy string).
7. **Visual acceptance vs the frozen composition**: per-width (1440/820/390) crops of the real entitled page posted in the PR body against `evidence/compositions/d5-program-dossier-virginia.html` — compared **per rail, in the state production actually reached**: the composition shows each rail's reviewed variant, and a rail honestly in `not_reviewed`/`reviewed_none` (e.g. milestones if the AUKUS source does not survive review) must match the freeze §4/§6 typed-state law, not the composition's reviewed variant. First screen answers the six questions; no horizontal overflow; inspector-tier IDs below the fold; EN/ZH parity; no translated `title=`.
8. **Production proof closes the wave**: entitled browser proof on the live route (program dossier renders reviewed participants with receipts; IRDM stays null), `/api/health` checkout covering the merge, plus the D2-style accounting line (counts of records admitted / proposed-held / rejected, all reconciling). PR merged same-day, render covered, live-verified — one session owns commit → push → PR → CI → merge → live verification.
9. **AgentOS closure in the same PR**: WS wave row D5 → done with PR list; handoff record; any new DEC minted for deviations taken during implementation.
10. **No boundary breach**: zero new tickers/security-master rows, zero recipient-graph edits (a needed identity → hand a worksheet to the recipient-graph lane, do not fork), zero P-1/R-1 parsing, zero GMI edge writes, zero facility/BOM objects, zero LLM-originated IDs/dates/roles, no numeric confidence anywhere.

If any decision appears unfrozen, that is a D5R defect — stop and record it; do not decide silently (freeze §10).

---

## §1. Build order (one PR is preferred; if split, each PR independently green)

1. Contract schema + engine loader with the temporal/certification refusals (freeze §5 — reuse the `entity_resolution.py` refusal vocabulary: `future_known_claim`, `future_effective_claim`, `missing_evidence_refs`, `claim_validity_window_inverted`, `evidence_known_after_claim`).
2. Propose script (discovery → candidate JSON only; forbidden-provenance rejection at the door; rejection ledger).
3. Curate script (worksheet admission; atomic write; refuses candidates as canonical; refuses `proposed` rows).
4. T1–T14 test battery green on fixtures.
5. Pilot worksheet: fetch + receipt the §3 sources, human-review, admit via curate.
6. Dossier composer + workspace `program_link` field + template `mode=programs` view (budget bake check).
7. Composition-matched visual pass, EN/ZH.
8. Production proof + AgentOS closure.

## §2. Owned paths (D5 build may touch ONLY these; anything else is a boundary breach to justify explicitly)

`contracts/government_revenue/government_program_ontology.v1.schema.json` · `contracts/government_revenue/government_program_dossier.v1.schema.json` · `engine/government_revenue/program_ontology.py` · `engine/government_revenue/program_dossier.py` · `scripts/propose_government_program_ontology.py` · `scripts/curate_government_program_ontology.py` · `scripts/build_government_revenue.py` (composer wiring only) · `engine/government_revenue/workspace.py` (the single `program_link` field) · `engine/government_revenue/award_events.py` (ONLY the one `unverified_supplier_language` addition to the closed `_action_text_annotations` family — nothing else in that module) · `templates/government_revenue.html.j2` + `templates/government-revenue-dossiers.js` (mode view; site twin sync law applies) · `tests/test_government_program_ontology*.py` · `.github/ci/legacy-jobs.yml` (declaring the new `gate: code` law jobs) plus the curated-scope closure file the `contract-delta` heal requires · `research/government_revenue/PROGRAM_ONTOLOGY_REVIEW_*.json/md` (worksheets) · `data/government_revenue/program_ontology.json` (curate output; never hand-edited) · AgentOS records.

## §3. Pilot evidence registry (D5R census; verification level binding)

VERIFIED = document body direct-read during D5R. SOURCE CLAIM = located via search synthesis; **must be re-fetched + receipted before admission**. NOT LOCATED = a D6 dependency or honest gap.

| Claim | Source | Level |
|---|---|---|
| P-1 identity: Appropriation 1611N SCN, BA-02, line "Virginia Class Submarine" + Advance Procurement sibling | Navy FY2011 President's Budget Exhibit P-1 (2010-01-26); public-domain USG work | **VERIFIED** (direct extraction; globalsecurity.org used as file host only — cite the Navy exhibit) |
| GD/EB is "the program's prime contractor"; boats built jointly with HII/NNS ~50-50 | CRS RL32418 (2025-03-28 update), congress.gov CRS product | **VERIFIED** (direct read via EveryCRSReport mirror; cite CRS) |
| Production ~1/yr vs 2/yr target | CRS RL32418 (2026-01 update) | SOURCE CLAIM |
| Block VI: $42.1B, 9 boats SSN 814-822 + material for a 10th; contract numbers N00024-12-C-2115 / -17-C-2100 / -17-C-2117 | Official contracts page "Contracts for July 29, 2026" (war.gov) | SOURCE CLAIM (403 to plain fetch — use entitled browser) |
| GD first-party: 14 submarines, $76.6B total | investorrelations.gd.com release 2026-07-29 | SOURCE CLAIM |
| BWXT supplier role: naval nuclear reactor components for "Virginia-class and Columbia-class … as well as … Ford-class" (SHARED SCOPE) | investors.bwxt.com release 2025-02-19 ($2.1B) | SOURCE CLAIM |
| AUKUS Pillar-1 forward window (sale of up to 3 in-service Virginia-class boats to Australia, early 2030s) — the milestones-rail candidate | CRS RL32418 (congress.gov CRS product, 2025-03-28 update) | SOURCE CLAIM (document access VERIFIED in D5R; the AUKUS sentence held as paraphrase — re-fetch + receipt + human review before admission; if it does not survive review, `milestones.state = not_reviewed \| reviewed_none` is the valid outcome) |
| MSAR identity "SSN 774 Virginia Class Submarine" | esd.whs.mil FOIA reading room MSAR Dec 2023 | NOT LOCATED (content; URL confirmed, 403) |
| FY2026 SCN book | secnav.navy.mil 26pres SCN_Book.pdf | NOT LOCATED (content; HTTP 200 but PDF-portfolio format defeated pdftotext/PyMuPDF — tooling gap, record as D6 dependency; render historical identity + gap note) |
| HII first-party Block VI statement | — | NOT LOCATED (render HII via CRS-verified teaming evidence; do not fabricate a first-party claim) |

Runner-up pilot (recorded, not authorized): PAC-3 MSE — Army MYP-1 exhibit (comptroller FY2024 MYP exhibits) **VERIFIED** direct-extracted ("2032 Missile Procurement – Army / BA-02", "P-1 Item Nomenclature: PATRIOT Advanced Capability (PAC-3) Missile Segment Enhancement (MSE)"). GEM-T has no located official budget identity; "Patriot/GEM-T" is two programs / two primes — do not resurrect it as a single pilot.

## §4. Danger areas (learned; do not re-learn)

- **Sparse worktrees:** never write into omitted `data/`; curate output in a sparse tree requires `worktree_sparse.py add data` first, else the committed artifact truncates.
- **`government_revenue.html` byte ratchet** (296 KiB) — see gate 5.
- **`grep -a`** for `government-revenue-dossiers.js` (BSD grep hides the budget module).
- **Graph republish re-times candidate clocks** (`DSC:GRAPH-REPUBLISH-RETIMES-EVERY-CANDIDATE-CLOCK`) — never re-stamp manifests; merge behind any freeze.
- **`gate: data` jobs are off the merge gate** — law tests must be `gate: code` with fixtures (D4 spec §4; memory `gate-data-ci-jobs-are-off-the-merge-gate`).
- **A new module reds `contract-delta`** on the PR that adds it — expected; heal the curated-scope closure in the same PR (memory `new-module-reds-contract-delta-via-curated-scope-closure`).
- **Host note (2026-08-22):** the Mac Studio's `Documents/Cluade` clone suffered an iCloud dataless-pack kernel stall during D5R (git object reads blocked in U-state; fileproviderd restart insufficient). If git wedges with fast index reads but hanging `cat-file`, check `ls -lO .git/objects/pack` for dataless flags before blaming git; escalate to operator for reboot/materialization rather than re-cloning per session.

## §5. do_not_redo

- Do not reopen the owner adjudication (A/B/C/E rejected on estate evidence — `DEC:D5-OWNER-IS-GOVREV-ONTOLOGY-PLUS-COMPOSED-DOSSIER`).
- Do not re-run the pilot bake-off (`DEC:D5-PILOT-IS-VIRGINIA-CLASS-SSN`); PAC-3 MSE is the recorded runner-up for a later wave.
- Do not mint `BUDGET_PROJECTION_MISSING`, `CONFLICTING_EVIDENCE`, or any uppercase enum into artifacts — §6 of the freeze maps every commission code onto existing vocabulary.
- Do not reuse `no_reviewed_exact_path` (or any atlas/recipient reason code) on a program rail — its bilingual copy is recipient-identity prose (freeze §4; the #6188 shared-copy trap).
- Do not reuse the recipient graph's evidence classes/publisher hosts for D5 evidence — freeze §3.1a owns D5 admissibility.
- `economic_weight` is REQUIRED and `const: null` on every v1 role assertion (it names the absence of an earned economic share). Do not derive, estimate, populate, rank, or otherwise make it non-null — no ratio or exposure share exists in D5.
- Do not parse the FY2026 SCN PDF portfolio inside D5 — D6 dependency, rendered as a gap.
- Do not build a program→award edge table in D5 v1 — award references ride role-assertion/milestone evidence; the general reviewed program↔award edge shape belongs to `government_budget_edge.v1` when the budget plane lives.
