# V4-D2B1 FROZEN CONTRACT — Data OS Issuer Authority Hardening (2026-08-19)

Status: FROZEN by Fable (COO) after Workers A–D census, under the Sol D2B1 commission.
Parent: `WS:PROPHET-US-V4-RECOVERY`, wave V4-D2, child D2B1. Sol authorized ONE explicit
issuer-identity correction era. This document is the binding builder spec. Text below the
FROZEN line changes only via an appended `## AMENDMENTS` section (D2A precedent).

Main pinned at start: `11b87a5b1b9ad30ebc2a03941787e36f55f856fe`.

---

## 1. Issuer definition and evidence law

- **Issuer = economic entity** (spec `research/MASTERMIND_SECURITY_MASTER_SPEC.md` §2):
  one issuer can own multiple securities. BRK.A/BRK.B, GOOG/GOOGL: one issuer each.
- **Issuer-equality evidence (US, this wave) = identical SEC registrant CIK** from the
  receipted CIK rail `data/symbol_directory/cik_map/<latest>.parquet` (weekly; rows
  `ticker,cik,title` from SEC company_tickers.json). Measured 2026-08-18 map: 10,398 rows,
  7,998 CIKs, ticker is a UNIQUE key (zero ticker→multi-CIK).
- **CIK means the registrant, never the parent** (commission §7): no subsidiary, sponsor,
  ADR-ordinary, or conglomerate collapse. Grouping happens ONLY between securities already
  in the master whose evidence CIKs are identical. ETFs/trusts group to the fund's own CIK
  (IBIT → 1980994 iShares Bitcoin Trust ETF), never the sponsor.
- **Forbidden resolution vocabulary** (commission §6): name similarity, embeddings,
  industry, ticker-root heuristics, LLM judgment. Issuer resolution is deterministic.

### Evidence join law (two-clock safe)

For each master security: join key = the security's **CURRENT symbol** — the inception
code transformed through the master's OWN dated rename chain (`_receipt.json`
rename_events + open-bounded membership aliases) to today — normalized **dot→dash**
(CIK map uses `BRK-B`; master uses `BRK.B`). NEVER join historical/dated alias symbols
against the current-observation CIK map (two-clock violation: a reused ticker would bind
the wrong registrant). A join miss is an evidence gap, not an error (heals on a later
weekly map). A hit yields `(cik, title, snapshot_date)` as the evidence triple.

## 2. Grammar, canonical member, mint-once

- **Grammar unchanged**: `issuer-id = "ISS:" listing-key` (spec §3.2).
  `lib/dataos/identity.py::issuer_id(listing_key)` stays a pure renderer; `parse_id`
  untouched; `tests/test_dataos_identity.py:115,118` remain green as written.
  What changes is WHICH listing key the builder passes: the issuer's **canonical member**.
- **Canonical member of a CIK group** = spec §3.2 tie-break, extended:
  1. earliest `list_date` (no in-repo source today — skip when unsourced, never guess);
  2. venue in the issuer's country of incorporation;
  3. lexicographically lowest MIC;
  4. **(D2B1 extension)** lexicographically lowest full listing key — needed because
     rules 1–3 cannot discriminate same-venue share classes with unsourced list dates.
  GOOG/GOOGL → rule 4 → `ISS:US-XNAS-GOOG`.
- **Mint-once for issuers**: the tie-break applies only when an issuer id is FIRST
  assigned to a group. A security later joining an existing evidenced group ADOPTS the
  existing issuer id — the id is never re-derived because membership grew. Post-era,
  committed issuer assignments never rewrite; later evidence disagreement becomes a typed
  state (`EVIDENCE_CONFLICT`), executed only by a future authorized correction era.
- Single-security issuers keep their existing value (own listing key) — for the vast
  majority of the 703 rows the issuer_id VALUE is unchanged; only its evidentiary status
  becomes explicit.

## 3. Schema changes

### security_master.parquet — new issuer axis columns
| column | type | law |
|---|---|---|
| `issuer_id` | str, **nullable** (registry flips nullable:true) | existing minted values RETAINED (mint-once; Sol: "previous issuer values are not erased"); repointed only via migration receipt; NEW post-era rows with no evidence get **NULL**, never a fresh per-listing mint (the abolished fallback) |
| `issuer_state` | str, non-null, closed enum | `RESOLVED` \| `NO_ISSUER_EVIDENCE` \| `AMBIGUOUS` \| `EVIDENCE_CONFLICT` \| `DEFERRED_IDENTITY_EXCEPTION` |
| `issuer_cik` | str, nullable | evidence CIK (zero-padded 10-digit) when state=RESOLVED |
| `issuer_evidence_snapshot` | str date, nullable | CIK-map observation date backing the link |

State semantics:
- `RESOLVED`: CIK evidence backs the link; issuer_id non-null; only these rows are lawful
  for issuer-level aggregation/rollups.
- `NO_ISSUER_EVIDENCE` + non-null issuer_id: legacy mint retained under mint-once,
  unevidenced — **aggregation-forbidden**, disclosed. + NULL issuer_id: post-era row,
  never minted. The value column itself makes the two sub-cases observable.
- `AMBIGUOUS`: current symbol maps to >1 CIK (impossible on the measured map; reserved,
  fail-closed, fixture-tested).
- `EVIDENCE_CONFLICT`: later evidence disagrees with a committed assignment (recorded,
  never executed).
- `DEFERRED_IDENTITY_EXCEPTION`: rows named in `_receipt.json` identity_exceptions
  (GOLD today; B has no row) — excluded from grouping entirely (commission §16: do not
  resolve B/GOLD merely because issuer machinery improved).

### data/reference/issuer_master.parquet — NEW (spec §8.1 minimal cut)
One row per distinct non-null issuer_id in the master: `issuer_id` (pk), `cik` (nullable),
`legal_name` (SEC title verbatim, nullable), `n_securities` (int),
`evidence_source` (`sec_company_tickers` | `legacy_mint`), `evidence_snapshot` (nullable),
`status` (`active`), `era` (`issuer_semantic_correction_v1` | `legacy`).
Registered in `config/dataset_registry.yml` in the same reference plane; covered by
`_receipt.json`. NOT a second identity system: minted only via `identity.py::issuer_id`,
pointed into by `security_master.issuer_id`, one semantic owner (lib/dataos).

### data/reference/issuer_migrations.parquet — NEW durable migration receipt
One row per security whose issuer_id VALUE changed in the era: `security_id`,
`listing_key`, `old_issuer_id`, `new_issuer_id`, `reason`
(`issuer_semantic_correction_v1`), `evidence_cik`, `evidence_snapshot`, `migrated_at`.
Append-only; registered; asserted non-empty iff any value changed.

### Reader API (one canonical reader)
`lib/dataos/identity.py` gains pure, no-I/O helpers in the house style
(`VendorAliasTable` precedent): an `IssuerMaster.from_records(...)` (or equivalent) with
`securities_of_issuer(issuer_id)` and `issuer_of_security(security_id)` — the §9.7
canonical query. No competing issuer allocator or reader anywhere else. Docstring states
the historical limitation (below).

## 4. Migration law (the one authorized era)

- Executed INSIDE `scripts/build_security_master.py` as a versioned deterministic stage
  (era constant `issuer_semantic_correction_v1`), not a one-off script: re-running is
  idempotent (era already applied ⇒ byte-stable no-op).
- `security_id` and `listing_key`: **byte-identical before/after** (tested).
- Vendor aliases: preserved untouched.
- Every changed issuer value ⇒ one `issuer_migrations.parquet` row. Old ids whose groups
  emptied are visible in the receipt (never silently erased from history).
- Consumer migration in the SAME PR (§8 below) — after it, exactly one canonical issuer
  identity exists in the Data OS plane. Pre-existing DIFFERENT-plane issuer namespaces
  (capital_structure `issuer:<CIK>`, golden-corpus `iss_<hash>`, share_class_equiv 13F
  collapse) are out of scope and must be registered/confirmed KNOWINGLY-DIFFERENT in
  `config/identity_seams.yml` (additive documentary rows where missing).

## 5. Historical limitation (§18)

CIK evidence is a current-registrant observation. Issuer resolution is canonical for
CURRENT identity only; historical issuer lineage is explicitly unavailable (no asof
parameter on the issuer reader; docstring says so). The latest CIK map never proves what
the issuer mapping was in 2015. Security/listing historical clocks (MMC/MRSH 2026-01-14,
SATS/ECHO 2026-06-24 boundaries) are untouched and must remain test-proven.

## 6. Receipt authority decomposition (§12)

`data/reference/_receipt.json` `authority` becomes semantically decomposed:
`identity_authority: canonical_exact_identity`, `signal_authority: none`,
`ranking_authority: none`, `trade_authority: none`, plus a `consumers` note naming
`gmi.identity_resolution/v1` (the "nothing reads it as authority yet" sentence is false
since D2A and must go). Receipt gains an `issuer` section: counts by issuer_state,
multi-security group census, era record, evidence snapshot ids.

## 7. Live-refresh seam (§13)

- Seam = ONE new step in the existing `daily.yml` collect job, after
  `python -m scripts.collect …` and its audits, before the market-commit-push band:
  runs the canonical builder in nightly mode (non-fatal house pattern: `|| echo
  "::warning…"`). No new workflow, timer, cron, or control plane.
- Fail-closed laws: (a) missing/unreadable identity inputs ⇒ refuse, keep last-good,
  `::warning`, exit 0, generated_at NOT re-stamped; (b) inputs unchanged since last
  generation ⇒ deterministic no-op, byte-stable artifacts, generated_at NOT re-stamped;
  (c) inputs advanced ⇒ regenerate, stamp, receipt pins the exact snapshot ids consumed.
  A source failure can never produce a falsely fresh identity generation (§23.24).
- Downstream: `gmi.identity_resolution/v1` re-derives from the master on EVERY theme-graph
  materialization (D2A docstring guarantee) — the chain source→master→projection needs no
  manual identity edits. This PR re-derives and commits the sidecar once itself.

## 8. Consumer migration set (same PR; from Workers A/D)

1. `tests/test_theme_graph_identity_resolution.py:136` — flip to assert GOOG/GOOGL SAME
   issuer_id, still distinct security_id (the regression D2B1 exists to make possible).
2. `tests/test_dataos_security_master.py:404-407` — replace the `SEC:→ISS:` prefix-swap
   assertion with the new law (state-aware; RESOLVED groups share canonical ids).
3. `engine/theme_graph/identity_resolution.py` — passthrough unchanged in shape; module
   docstring + schema description updated for issuer-axis semantics; regenerated sidecar
   committed (derive from committed nodes.parquet — NEVER the full pipeline in a worktree,
   `DSC:THEME-GRAPH-FULL-REBAKE-DIVERGES-LOCALLY`).
4. `scripts/check_theme_graph_contracts.py` biconditional amended: RESOLVED sidecar rows
   require non-null security_id/listing_key always; issuer_id may be null ONLY when the
   master's issuer_state for that security is NO_ISSUER_EVIDENCE (guard already reads the
   master read-only).
5. `contracts/theme_graph/identity_resolution.v1.schema.json` — issuer_id description
   updated (issuer axis semantics + nullability law); 19-column shape unchanged.
6. `research/prophet_v4/d2/D2A_FROZEN_CONTRACT_2026-08-18.md` — appended AMENDMENTS note.
7. `config/identity_seams.yml` — master block prose updated; KNOWINGLY-DIFFERENT rows
   confirmed/added for capital_structure CIK namespace and golden-corpus hashes.
8. Disclosed (no code change): `engine/seasonality/event_study.py:1098` groups events by
   issuer_id — GOOG/GOOGL events will newly group together. That is the intended corrected
   semantics; named in the PR body.

## 9. RDDT and EQR→VMRK (§11)

- **RDDT**: closed by canonical regeneration — current seeds resolve `US-XNYS-RDDT`
  (the committed staleness test `test_the_committed_artifact_is_not_stale_against_the_
  current_seeds` is RED ON MAIN today on exactly this; this PR's regenerated master is
  the lawful heal). No hand-written rows.
- **EQR→VMRK**: CONDITIONAL. Repair ONLY with affirmative evidence in committed sources
  at build time: a post-#5936 listing snapshot showing the flip (EQR present@08-10 →
  absent; VMRK absent@08-10 → present) AND **CIK continuity** (fresh CIK map maps VMRK to
  EQR's registrant CIK). Name similarity is forbidden evidence. If confirmed: a dated
  `RenameEvent` through the existing canonical mechanism (MMC→MRSH precedent), master
  keeps `SEC:US-XNYS-EQR`, dated alias rows added, both clocks stay valid. If evidence is
  absent when the PR finalizes: NOT repaired, disclosed in receipt/PR as pending-evidence.
  Never a timeless `"VMRK": "EQR"` dictionary entry anywhere.

## 10. Freshness gate for production proof (§10)

Pre-implementation work proceeds now. Before the FINAL committed regeneration is called
production-proven: latest listing snapshot date > 2026-08-10, snapshot row count above
source floor (read the snapshot parquet + its completion receipt — the manifest's
`n_symbols:0` under-reports and is display-only), completion receipt exists. Never
hand-create a snapshot, never restamp the manifest. If still stale at final-proof time:
D2B1 verdict = `BLOCKED_SOURCE_FRESHNESS`.

## 11. Hostile-case expected states

| Case | Expected end state |
|---|---|
| GOOG/GOOGL | 2 securities (ids unchanged); ONE issuer `ISS:US-XNAS-GOOG` (rule 4); GOOGL row in issuer_migrations; both RESOLVED, CIK 1652044 |
| BRK.B | dot→dash join hits `BRK-B`→1067983; RESOLVED; single-member group (BRK.A not in master — no fabricated second security) |
| MMC/MRSH | one security `SEC:US-XNYS-MMC`; rename chain gives current symbol MRSH for the join; 2026-01-14 boundary untouched; state per measured evidence |
| SATS/ECHO | one security; current symbol ECHO joins (hit on 08-18 map); one issuer; 2026-06-24 boundary untouched |
| FI/FISV | one security `SEC:US-XNAS-FISV`; current symbol FI; state per measured evidence (FI missed the 08-18 map — if still missing: NO_ISSUER_EVIDENCE with legacy value retained, self-heals on a later map) |
| B / GOLD | B: no master row (deferred_no_mint) — untouched. GOLD: `DEFERRED_IDENTITY_EXCEPTION`, excluded from grouping, value retained |
| IBIT | RESOLVED to the trust's own CIK 1980994; D2A `ENTITY_TYPE_CONFLICT` REMAINS in the sidecar (graph-side kind defect, D2B3's) |
| AEP/CTRA/TPH (measured 08-18 misses) | NO_ISSUER_EVIDENCE, legacy value retained, aggregation-forbidden, disclosed in receipt census |
| RDDT | new security row from seeds; RESOLVED if CIK map hits (expected); new single-member issuer |

## 12. Tests and mutation controls

**Extend EXISTING suites only — no new test files** (avoids the unrun-suite guard and the
legacy-jobs.yml global invalidator): `tests/test_dataos_identity.py`,
`tests/test_dataos_security_master.py`, `tests/test_theme_graph_identity_resolution.py`,
`tests/test_theme_graph_contracts.py`.

Commission §24 mutation controls, all must provably die (mutate-and-observe or
fixture-driven): (1) GOOG/GOOGL different issuers again; (2) GOOG/GOOGL collapsed to one
security; (3) per-listing issuer fallback restored for evidence-less NEW rows; (4) no-CIK
security fabricated into a RESOLVED issuer; (5) two different CIKs force-merged; (6)
SATS/ECHO dated boundary removed; (7) overlapping timeless aliases for a rename pair
(existing ambiguity guard); (8) security_id changed during migration; (9) old issuer ids
mutated without a migration receipt row; (10) stale snapshot stamped fresh; (11) build
completes with missing identity source yet claims current; (12) sidecar ticker-equality
after Data OS refusal (existing D2A test retained); (13) IBIT conflict disappears merely
because an issuer record exists; (14) broad C0 names injected as identity authority
(master row count stays ≈703+seed-natural additions; no cohort injection).

## 13. File scope

ALLOWED: `lib/dataos/identity.py`, `scripts/build_security_master.py`,
`config/dataset_registry.yml`, `config/identity_seams.yml`, `data/reference/*`,
`tests/test_dataos_identity.py`, `tests/test_dataos_security_master.py`,
`engine/theme_graph/identity_resolution.py`, `scripts/check_theme_graph_contracts.py`,
`contracts/theme_graph/identity_resolution.v1.schema.json`,
`tests/test_theme_graph_identity_resolution.py`, `tests/test_theme_graph_contracts.py`,
`data/theme_graph/identity_resolution.parquet` (+ `_meta.json`), `.github/workflows/daily.yml`
(ONE step), `research/prophet_v4/d2/*`, `research/prophet_v4/CONTRACT_AND_OWNER_MAP.md`,
`research/MASTERMIND_SECURITY_MASTER_SPEC.md` (tie-break rule 4 note only),
`agentos/*` records.

FORBIDDEN (commission §20): Prophet rank/admission/availability, Fusion, Radar, B5A,
ThemeState, theme mappings, GMI membership edges, Earnings, Stock Identity, qledger,
alt-data, UI/templates/site, unrelated CI work, graph node_id generation,
`data/symbol_directory/*` (collector-owned — read-only), broad D2B2 expansion (the 1,869
NOT_IN_MASTER queue stays open).

— FROZEN —
