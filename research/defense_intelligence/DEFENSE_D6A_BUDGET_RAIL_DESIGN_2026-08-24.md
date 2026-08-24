# Defense D6-A — DoD P-1/R-1 Budget Rail Activation: frozen design (2026-08-24)

Sol commission: PR #6355 comment 5395051048 (Chairman sequencing amendment; D6-A
authorized; D6-B+/D7+ unauthorized). Pickup main `571b48d497cd4e9b5d8be532aa1d4943485e16b7`
claimed 2026-08-24T14:33:45Z on branch `claude/dod-budget-d6a`.

D6-A activates the EXISTING budget plane. It does not build another budget system.
Owner chain (all pre-existing, Wave 8 / PR #4348): `collectors/dod_budget.py`
(hermetic receipt/parse/append core) → triad `data/government_revenue/{dod_budget_line_snapshots.jsonl,
dod_budget_collection_receipts.jsonl, dod_budget_projection_state.json}` →
`engine/government_revenue/budget_program.py` (`government_budget_program_graph.v1`,
`grbg1-` content id) → `scripts/build_government_revenue.py` twins
(`data/government_revenue/budget_program_graph.json` + `site/government-revenue-data/budget-program.json`)
→ `/api/government-revenue/budget-programs` family → Budget & Programs mode of
`government_revenue.html`. Publication lane: `.github/workflows/government-revenue-live.yml`
(the ONLY budget publisher — do not add another).

## 1. Source census results (verified 2026-08-24, this session)

- The DoD Comptroller's official host MIGRATED: `comptroller.defense.gov` now returns
  HTTP 403 (AkamaiGHost, no redirect). The live official surface is
  `comptroller.war.gov` (Department of War rebrand; same DNN CMS paths
  `/Portals/45/Documents/defbudget/…`, full 1998–2027 archive). Already allowlisted in
  `ALLOWED_SOURCE_HOSTS` (`collectors/dod_budget.py:39`) — no widening needed.
- Current cycle: FY2027 President's Budget (posted April 2026).
- **Frozen canary documents** (fetched + hashed this session; the production
  acquisition re-fetches independently — if the served bytes differ, that is a NEW
  observation, investigate before proceeding):
  - P-1: `https://comptroller.war.gov/Portals/45/Documents/defbudget/FY2027/FY2027_p1.pdf`
    — 2,796,050 bytes, sha256 `b8d5248257590856ee33ddb1b401ec2efcdfea219c05b5bc8ea1068d9000d0a6`,
    335 pages, last-modified 2026-04-03T19:56:57Z.
  - R-1: `https://comptroller.war.gov/Portals/45/Documents/defbudget/FY2027/FY2027_r1.pdf`
    — 3,127,023 bytes, sha256 `1aa8846edb69d4c3a54e03b383b0cabb77f93433162b8139ab8cbb55bcc7882a`,
    125 pages, last-modified 2026-04-03T19:56:57Z.
- Publisher self-identification INSIDE both documents: "Office of the Under
  Secretary of War (Comptroller)". The receipt publisher constant must change to
  this source-native string (a recorded, minimal contract edit).
- `verify_document_header` passes as-is against real page-1 text: exact
  "PROCUREMENT PROGRAMS (P-1)" / "RDT&E PROGRAMS (R-1)", "Fiscal Year 2027",
  "COMPTROLLER" all present.
- Local reference copies for build-time work (NEVER commit; not evidence — the R2
  object is the evidence):
  `/private/tmp/claude-501/-Users-chriswong-Documents-Cluade-Macro-Dashboard--claude-worktrees-dod-budget-rail-d6a-2ea4da/cf6ab34a-17e8-4af1-b784-d8c75105654d/scratchpad/FY2027_p1.pdf` and `FY2027_r1.pdf`.

## 2. Observed FY2027 layout (both exhibits)

Seven value columns (dollars in thousands; the unit marker "(Dollars in Thousands)"
is printed on every table page and MUST be verified before ×1000 normalization):

1. FY 2025 Actuals
2. FY 2026 Discretionary Enacted
3. FY 2026 PL 119-21 Spend Plan
4. FY 2026 Total
5. FY 2027 Discretionary Request
6. FY 2027 Mandatory Request
7. FY 2027 Total

- **R-1**: single-page-wide tables. Columns: Line No / Program Element Number
  (e.g. `0601102A`) / Item (name; wraps) / Act (budget activity, e.g. `01`) /
  Sec (`U`) / the 7 value columns. Appropriation header inline:
  `Appropriation: 2040A Research, Development, Test and Evaluation, Army`.
- **P-1**: wide tables SPLIT ACROSS PAGE PAIRS — left page carries Line No /
  Item Nomenclature / Ident Code / Sec / FY2025+FY2026 Qty/Cost columns; the
  continuation page repeats Line No + Item Nomenclature and carries the FY2027
  Qty/Cost columns. Detail tables are per appropriation (`2031A Detail` header);
  per-BA printed totals live on the `<code> Budget Activity Summary` page pairs;
  component/appropriation summaries print appropriation-level totals.
- P-1 quantity columns (Qty) accompany each value column; R-1 has none.
- Blank cells are REAL and frequent (line items with history but no FY2027
  request, or vice versa). Text-order extraction cannot attribute sparse cells —
  extraction MUST be coordinate-based (words + x/y), with column intervals
  derived from the header positions of each page, and any number that does not
  fall inside a known column interval refusing the whole document.
- Parenthesized numbers are negatives (e.g. `(9,500,534)` on SCN pages).
- Non-line rows exist and must be deterministically classified (closed set):
  page furniture (UNCLASSIFIED / department / page footer / `Apr 2026`), table
  headers, `Budget Activity NN:` headers, group labels (`Fixed Wing`),
  `Less: Advance Procurement (PY)` adjustment rows, `Advance Procurement (CY)`
  items, `C (FY x for FY y) (M)` schedule rows (SCN), `Completion PY Shipbuild…`
  / `Subsequent Full Funding…` rows, total rows, footnote rows (`*The FY27 P&F
  total…`). An unclassifiable row that carries numbers ⇒ refuse the document.
- P-1 canary present: Shipbuilding and Conversion, Navy — Line 6
  "Virginia Class Submarine" (pages 140/141 pair), Ident Code B.
- R-1 canary: select from REAL extracted lines after extraction runs (prefer a
  submarine/undersea-relevant Navy PE when one exists as an exact line; else any
  deterministic PE line) and record why. Do not invent one in advance.

## 3. Frozen semantic mapping (adjudicated by Fable this session)

The 5-member `AMOUNT_SEMANTICS` contract is PRESERVED EXACTLY (no enum widening):

| semantic (fiscal_year) | printed FY2027-exhibit column |
|---|---|
| `historical_actual` (2025) | FY 2025 Actuals |
| `prior_year_enacted_reference` (2026) | **FY 2026 Total** |
| `discretionary_request` (2027) | FY 2027 Discretionary Request |
| `reconciliation_request` (2027) | **FY 2027 Mandatory Request** |
| `president_budget_request_total` (2027) | FY 2027 Total |

Recorded consequences (named gaps, reported to Sol — not silent):
- The FY 2026 Discretionary-Enacted and FY 2026 PL 119-21 Spend Plan sub-cells
  are NOT representable in the frozen contract and are deliberately unextracted
  in D6-A. Future enum widening is a separate Sol decision.
- The FY2027 exhibits print "Mandatory Request" where FY2026 printed
  "Reconciliation"; the content is PL 119-21 (reconciliation act) funded budget
  authority. The mapping is frozen in the parser as an exact header match and
  recorded here. If the Budget & Programs UI label for this semantic would
  mislead against the source's own wording, report the exact rendered label to
  the orchestrator for adjudication — do not restyle it unilaterally.
- Quantities mirror amounts column-for-column (P-1 only).
- Blank cell ⇒ `None`, ALWAYS. Printed `0` ⇒ `0.0`. Coercion of blank to zero is
  a hard test-red. This requires relaxing `_amounts_from_fields` nullability
  (currently actual/enacted/total are non-nullable) for the production path, and
  the matching additive relaxation in `government_budget_line.v1.schema.json`
  if the schema pins non-null — verify and record.

## 4. Immutable acquisition (order is law)

1. GET the allowlisted official HTTPS URL (TLS verified, bounded timeout, size
   cap ≥ 8 MiB but bounded, no cross-host redirects; final_url must pass
   `_official_https_url`).
2. Verify `%PDF` magic; compute source sha256.
3. Write bytes to the EXISTING canonical R2 object store, key
   `government-revenue/dod-budget/pdf/sha256/<sha256>.pdf`
   (`IMMUTABLE_R2_PREFIX`, `collectors/dod_budget.py:42`). Reuse the existing
   store machinery — model on `engine/capital_structure/source_store.py`
   `ContentAddressedSourceStore` over `engine/research_vault/r2_store.py`
   (`build_store()`; standard `R2_BUCKET`/`R2_ENDPOINT`/`R2_ACCESS_KEY_ID`/
   `R2_SECRET_ACCESS_KEY` env ladder). DO NOT mint a new bucket/plane. If the
   key already exists, read back and require byte equality (idempotent
   re-observation).
4. Read the stored object back (strict bounded read); require readback bytes ==
   fetched bytes AND readback sha256 == source sha256. No fail-open fallback.
5. Only then build the collection receipt (`build_document_receipt`) and allow
   extraction. An HTTP 200 without durable write+readback proof is NOT
   acquisition; no receipt may exist for an unproven object.
6. Same URL + new bytes later = NEW observation/receipt appended (existing
   `merge_receipts` / `append_line_snapshot_versions` semantics); never
   overwrite. `known_at` = our verified acquisition clock; never labeled as an
   official publication clock; never manufacture `source_published_at`.
7. No credentials/headers/signed URLs in receipts (`_FORBIDDEN_RECEIPT_KEY`
   enforced already).

R2 credentials exist ONLY in GitHub Actions secrets (used by 60+ existing steps)
— the production acquisition runs as a MANUALLY DISPATCHED job on the
self-hosted runner against the PR branch (workflow_dispatch input-gated; no
schedule — this is an annual/supplemental source; no poll). The job commits the
triad to the PR branch. Publication stays with government-revenue-live.

## 5. Extraction & parsing (production path)

- Extractor: `pdfplumber` (MIT; pdfminer.six-based), version-pinned in
  `requirements.txt`. PyMuPDF was deliberately NOT chosen (AGPL). Deterministic
  settings (explicit tolerances) frozen as module constants.
- Per page emit BOTH: (a) a plain-text rendering — this is what receipts bind
  (`page_text_sha256s`), and (b) words with coordinates — parser input. Both
  derive from the same bytes; `extractor_version` records library+version+modes
  (e.g. `pdfplumber-<ver>-text+words.v1`).
- New production parser (`parse_official_p1_document` / `parse_official_r1_document`)
  in a NEW module `collectors/dod_budget_live.py`; the hermetic fixture parser
  and its tests remain untouched for the foundation suite. The live parser
  builds the same `fields` mappings and calls PUBLIC wrappers exported from
  `collectors/dod_budget.py` around `_normalized_line`/`_amounts_from_fields`/
  `_quantities_from_fields` so every identity/semantic/state-hash invariant is
  enforced by the same code. New `PARSER_VERSION` for the live path
  (e.g. `dod-budget-fy2027-official-text.v1`); receipts record it.
- Header anchoring: exact expected header text at expected relative positions on
  every table page; any deviation ⇒ refuse the WHOLE document (fail closed; no
  plausible partial rows).
- P-1 page-pair joining: join rows across the pair by (appropriation code from
  the `<code> Detail`/`Summary` header, budget activity, line number); the
  repeated Item Nomenclature must match (whitespace-normalized); any orphan or
  mismatch ⇒ refuse the document.
- Line identity: existing `_line_identity` grammar untouched. P-1
  `native_kind=p1_line_item`, value = printed Line No (within appropriation);
  R-1 `native_kind=program_element`, value = printed PE number. Component =
  the department/component the table belongs to; appropriation_code = the
  header code form (e.g. `2031A`, `2040A`) — one normalization rule, applied
  identically to both exhibits.
- Totals: printed BA-level totals feed `reconcile_line_totals` (unchanged
  hermetic math, exact to $0.01 after ×1000). ALSO cross-check printed
  appropriation-level and grand totals where present (extra guard). If the
  arithmetic model (which rows sum to which printed totals, incl. `Less:` and
  advance-procurement rows) has ANY unexplained residual, refuse — never bridge.
- OCR is FORBIDDEN this wave. Text-layer only.
- LLMs may not originate any number, identifier, code, page location, or date.

## 5b. FROZEN P-1 row model (adjudicated 2026-08-24 after the Stage 1/2a surveys)

Evidence: scratchpad `survey_p1.py` / `survey_p1_reconcile.py` / `survey_scn_1611.py`
(+ JSONs) — full-document classification with ONE remaining exception (the pinned
p.158 anomaly below), reconciliation 24/24 + 81/81 + 24/24 across all 22
appropriations, and exact $0.00 typed-model closure on all four SCN (1611) BAs
plus the appropriation total.

Closed row taxonomy: detail_line · group_label · nomenclature_wrap_fragment ·
less_advance_procurement · less_subsequent_full_funding · unlabeled_net_memo_row ·
advance_procurement_cy · completion_subsequent_row · schedule_row
(`C (FY x for FY y) (M)`) · memo_non_add_row (`(MEMO NON ADD)`) · BA headers ·
close/total rows · page furniture · footnotes. Any row carrying numbers that
does not classify ⇒ refuse the document.

Additive/publication law:
1. detail_line with NO Less-children → published line; amounts = its own row
   values.
2. detail_line WITH less_advance_procurement / less_subsequent_full_funding
   children → published amounts = the resolving `unlabeled_net_memo_row`
   (matched as the next net-memo row in the SAME side's event stream; printed,
   never derived — proven `net_memo = −(line) + Σ(less)` exact on every tested
   line, Virginia FY27 = p.143 `8,402,316`). Quantities come from the
   detail_line row itself (the only place the exhibit prints them).
   Provenance `page_number` = the line-identity row's page; `source_span`
   additionally names the resolving net row's page:line. Gross and Less values
   are NOT represented in v1 (named gap: full-funding structure).
3. advance_procurement_cy and completion_subsequent_row are ADDITIVE in the
   printed totals. Their published-line identity binding (own printed Line No
   or not) must be settled by the Stage 2b gate-zero census before the parser
   emits them — if any additive row lacks a printed source-native identity,
   STOP for adjudication; never mint an identity that is not printed.
4. schedule_row and memo_non_add_row are NEVER additive and NEVER published.
5. Column assignment is the exact boundary-bucket model (field left edge = its
   header word x0, right edge = next column's x0); a token outside every
   bucket ⇒ refuse the document. Zero-tolerance: no nearest-anchor matching.
6. BA-code state is tracked PER SIDE (left/right half-views are independent
   streams); joins are by appropriation CODE (caption form with letter suffix
   is the line-identity form, e.g. `2031A`; matching strips the suffix).
   Close-row label recognition uses the per-row, per-side ≥80% length-ratio
   prefix match (documented cases: clipped `…Vehic`, identical-name 0360D).
7. Pinned source-anomaly table (exact-match only; anything else refuses):
   (doc sha256 `b8d5248257590856ee33ddb1b401ec2efcdfea219c05b5bc8ea1068d9000d0a6`,
   page 158, literal caption `1612N Budget Activity Summary AApprr 22002266`)
   → accepted as `1612N Budget Activity Summary` + `Apr 2026`.
8. Totals fed to `reconcile_line_totals` = the BA-Summary pages' printed BA
   rows (the independent copy); the parser ADDITIONALLY hard-checks the Detail
   stream's own close rows against them (level-2) and the appropriation/grand
   totals (levels 1/3). BA/appropriation totals never print quantity sums
   (verified exhaustively) — no aggregate-quantity reconciliation exists.
9. R-1 (frozen from Stage 1): single-page rows, inline BA-close group rows +
   per-component recap pages as the printed totals; the Defense-Wide
   per-agency listings (pp.89+) are a NON-ADDITIVE re-itemization of money
   already counted once — the parser must prove no duplicate line_keys and
   never double-count those totals.

### 5b.1 Gate-zero rulings (adjudicated 2026-08-24, after the document-wide census)

Evidence: scratchpad `gate_zero_p1_typed_model.py` (+ fixed `survey_common.py`) —
document-wide typed-model closure at $0.00: P-1 81/81 BA groups vs BOTH printed
sources, R-1 103/103 + 28/28, after fixing a bare-minus sign-drop.

1. **Sign law (frozen):** recognized numeric forms are plain, `(paren)`,
   `(paren-minus)`, and bare-minus (P-1 p.108 TTNT lines print bare negatives);
   any other numeric form refuses the document.
2. **Zero-numbered-line partitions (1612N BA01):** publication stays
   numbered-lines-only. A totals partition containing ZERO numbered lines is
   excluded from the hermetic `reconcile_line_totals` input; the parser's own
   document-wide typed-model closure (which includes it) is a HARD in-parser
   gate — any residual refuses. Named product gap: NSBDF-style unnumbered
   full-funding rows are not at line grain.
3. **Printed-addend grain (dual parents / additive children):** a published
   record's amounts ALWAYS come from exactly ONE printed row — never a sum.
   - Numbered parent: amounts = resolving net-memo row when Less-children
     exist; else its own row's values; else ALL-NULL when its own row prints
     no values (blank stays null — e.g. SCN COLUMBIA line 2's parent row).
   - EVERY value-bearing additive child row (`advance_procurement_cy`,
     `completion_subsequent_row`) publishes as its OWN record: kind
     `p1_line_item`, native value `"<parent line no>--<printed child label
     slug>"` (both components printed; duplicate derived identity refuses),
     `program_name` = the child's printed label verbatim, same
     component/appropriation/BA, provenance = the child row's page.
   - Quantities bind to whichever published record's source row printed them.
   - Proven closure shape (COLUMBIA BA01): parent net 6,904,785 + completion
     child 3,329,047 + line-2 child 4,763,342 = printed 14,997,174 (FY27 disc).
   - Noted display gap: child records carry only their own printed label as
     the name; parent context lives in the line identity — a later UI pass
     may compose display naming, never this wave.
4. **Line identity gains the budget-activity slug** (BOTH exhibits, uniform):
   `_line_identity` line_key AND line_family_key include a BA segment —
   required because R-1 genuinely reuses one PE across BAs within one
   appropriation (29 real collisions, e.g. PE 999999999 per-BA, 0604776F in
   BA03+BA04). No production data exists anywhere yet, so this is the last
   zero-cost moment. Program-node grammar UNCHANGED; the graph must tolerate
   same-FY sibling lines under one program key (verify; stop if it refuses).
5. **R-1 Defense-Wide (0400D):** lines emit ONLY from the consolidated listing
   (pages < 89); the per-agency pp.89+ sections are verification-only (their
   printed totals must still close vs p.83 — hard check, no line emission).
6. Classification refinement: a bare two-number row matching the leading-digit
   line pattern (1507 p.121 `"20 20"`) — detail_line classification requires
   non-numeric nomenclature text after the leading line number.

## 6. Activation & publication

- `DOD_BUDGET_PRODUCTION_ACTIVATION_ENABLED = True` flips ONLY in the same PR
  that carries: live acquisition+readback code, production extraction, the real
  committed triad produced by the dispatched runner job, hostile suite, and
  passing graph build. Partial triad remains a hard refusal
  (`scripts/build_government_revenue.py:726`).
- `tests/test_build_government_revenue.py:244` (hard-disabled expectation)
  updates to prove the graph now BUILDS from the committed triad; add a fence
  test that activation with a missing/partial triad still refuses.
- Post-merge: government-revenue-live builds/validates/publishes the twins;
  VPS serves; production proof = nonzero API + served Budget & Programs bytes +
  exact canary lines + receipt/page provenance + anonymous entitlement boundary
  unchanged (401 behavior identical to pre-D6A).

## 7. Hostile suite (merge-binding; each mutation must be killed by a named test)

unallowlisted publisher host → refused · HTTP ok but object write failed → no
receipt/no publication · readback sha differs → refused · non-PDF bytes →
refused · header FY mismatch → refused · P-1/R-1 exhibit header mismatch →
refused · extraction page hashes differ from receipt → refused · printed-total
reconciliation fails → refused · same receipt id, different bytes → refused ·
same URL later serves different bytes → NEW observation appended, prior remains
replayable · request relabeled as authorization/appropriation/obligation/
revenue → test red · missing numeric cell coerced to zero → test red · partial
triad → publication hard-fails · unknown table/layout → no plausible partial
rows · reviewed edge via name/ticker matching → refused · economic_weight
non-null → refused · activation flag set without real acquisition/storage/
extraction receipts → test red.

Existing foundation tests (`tests/test_dod_budget_collector.py`,
`tests/test_government_revenue_budget_graph.py`, `tests/test_build_government_revenue.py`)
stay green (publisher-string updates aside) and the new tests are ordinary
`tests/` files so the CI pack lanes bind them automatically (verify with
`run_ci_pack.py --validate-only`).

## 8. Authority / firewall (unchanged)

request ≠ authorization ≠ appropriation ≠ execution ≠ obligation ≠ award ≠
backlog ≠ revenue ≠ cash. Display/evidence tier only: can_rank/can_gate/
can_size/can_add_candidates/can_originate_signal/can_set_entry/can_execute all
false. No D5 contract changes: `budget_program_keys` stays `const []`;
`government_budget_edge.v1` reviewed edges stay dual-evidence with
`economic_weight: null`; no name-matched Virginia/ticker/recipient bridge.
D5 dossier surfaces are NOT the D6-A consumer; Budget & Programs is.
