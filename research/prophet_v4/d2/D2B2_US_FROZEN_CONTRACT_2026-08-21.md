# V4-D2B2-US — Frozen contract: canonical U.S. identity coverage expansion

**Status: FROZEN 2026-08-21 (Fable, WS:PROPHET-US-V4-RECOVERY). Binding on the D2B2-US builder.**
Commission: Sol V4-D2B2-US (2026-08-21). Parent: `research/prophet_v4/d2/D2B2_CN_HK_FROZEN_CONTRACT_2026-08-20.md`
(pattern precedent) and `research/prophet_v4/d2/D2B1_R1_FROZEN_CONTRACT_2026-08-20.md` (fence/supersession law).
Start-pin: `origin/main = 0c097d0f9621342264ab7523050db213fc3e1fe1`.

Authority: Data OS remains sole exact issuer/security/listing authority. GMI node ids remain topology only.
Stock Identity remains behavioral. Prophet output is never identity evidence.

## §0 Verdict — the gap is seed scope, not resolution defect

The 533 U.S. GMI company nodes still `NOT_IN_MASTER` are unaddressed because the builder's U.S. seed set
(`load_universe()`, scripts/build_security_master.py:649-688) is the curated breadth-constituents ∪ basket-members
union (710 keys) and was never wired to the theme graph's 1,238 U.S. company nodes. The resolution, mint, fence,
supersession, and issuer machinery downstream of the seed set is proven (D2B1, R1, D2B2-CN-HK) and is NOT redesigned
here. The repair is a **tagged GMI-U.S. seed intake feeding the EXISTING U.S. resolution/mint path**, plus the
structural common-equity eligibility law the curated universe never needed, plus complete per-target accounting.

This is deliberately NOT a CN/HK-style separate mint stage: U.S. targets have both evidence rails
(listing directory + SEC CIK), so they must flow through `resolve_universe()` → `mint_master_rows()` including the
R1 pending-transition fence. Reused/renamed tickers therefore hit the R1 supersession/fence machinery structurally,
as the commission requires.

## §1 Census facts at the pin (binding; remeasured, not inherited)

- Target population: **target_n = 533** distinct U.S. GMI company nodes `NOT_IN_MASTER`
  (latest sidecar generation = per-node max `master_generated_at`; sidecar total 2,806 rows = nodes.parquet
  company rows). U.S. company field: 1,238 = 702 RESOLVED + 533 NOT_IN_MASTER + 2 DEFERRED_IDENTITY_EXCEPTION
  (GOLD/B) + 1 ENTITY_TYPE_CONFLICT.
- Eligibility buckets (sum 533): 503 admissible (listed, non-ETF, non-test, CIK resolves) — of which
  **502 on mapped venues** (256 NASDAQ, 241 N, 5 A) and **1 on Z (CBOE)**; 21 absent from both rails;
  6 LP common-unit issuers (ARLP, BEP, CQP, ET, UAN, XIFR — all listed on mapped venues, all with CIKs);
  3 CIK-present-not-listed (EA, GGRP, NVVE). Zero directory-ETF, zero test-issue, zero is_preferred,
  zero ambiguous-ticker→CIK among targets today.
- Evidence rails: `data/symbol_directory/snapshots/2026-08-21.parquet` (13,168 rows, nasdaqlisted + otherlisted,
  schema incl. `etf`, `test_issue`, `is_preferred`, `exchange`); `data/symbol_directory/cik_map/2026-08-18.parquet`
  (10,398 rows). Consumed by `load_directory()` (:699) and `load_cik_map()` (:722; pre-drops tickers with ≥2 CIKs
  into `ambiguous_tickers`).
- Master at pin: 1,836 rows — US 704 active + 1 SUPERSEDED_DUPLICATE_MINT (VMRK), CN 984, HK 147.
  Receipt: `symbol_directory_snapshot=2026-08-21`, `cik_map_snapshot=2026-08-18`, legacy `coverage`
  block 712/702/10 named unresolved.
- Regression floors (latest-generation RESOLVED): us 702, cn 984, hk 147, total 1,833.
- The census scratch CSVs are evidence for THIS contract only. The builder derives its target set from
  `data/theme_graph/nodes.parquet` at build time — never from the census CSVs, never from the derived sidecar.

## §2 Repair A — GMI-U.S. seed stage (tagged, additive)

1. `load_gmi_us_seeds()`: distinct normalized codes from `data/theme_graph/nodes.parquet` where
   `kind == "company"` and `market_scope == "us"` (upstream graph truth; the derived sidecar is NEVER read by the
   builder). Codes already covered by the legacy universe simply union in (key-level dedup); provenance is tracked
   so accounting can scope to GMI targets.
2. **Admission target set** (receipt accounting scope): GMI-U.S. seed codes with NO active committed master
   resolution at run start, MINUS codes present in the registered identity-exception set (today: the GOLD/B
   exception — its excluded codes are disclosed in the receipt, mirroring the existing `listing_continuity`
   `identity_exception` disclosure pattern; they are NOT targets and NOT touched). Expected at pin: exactly the
   533 census set; `B` (Barrick) is expected in the exception-excluded disclosure, not in the target set.
3. Seeds flow into the EXISTING pipeline: structural eligibility (§3) → `resolve_universe()` → `mint_master_rows()`
   (unchanged, fence included) → existing supersession/issuer passes. No parallel resolution logic, no second mint
   path, no new allocator, no new timer, no new issuer namespace.

## §3 Common-equity eligibility law (structural flags only)

Before a GMI-seeded candidate reaches minting, it must pass the directory's STRUCTURAL flags:

- `etf == True` → typed refusal `not_common_equity_etf`
- `test_issue == True` → typed refusal `not_common_equity_test_issue`
- `is_preferred == True` → typed refusal `not_common_equity_preferred`

These checks are implemented even though all three are empirically zero among today's 533 — the law is structural,
not empirical (hostile case: ETF/trust masquerading as a GMI company node). **Name-substring/keyword screening is
FORBIDDEN as a refusal basis** — it is name inference. RULING (Fable, 2026-08-21): the six LP common-unit issuers
(ARLP, BEP, CQP, ET, UAN, XIFR) are the primary listed equity of real GMI-tracked companies, carry all-false
structural flags and registrant CIKs, and are ADMISSIBLE through the same gates as every other candidate.
The census's name-evidence bucket was a census lens, never a refusal class.

Eligibility applies to GMI-seeded candidates. Legacy universe seed behavior is unchanged this wave (its 710-key
curated set has no ETFs; retrofitting the flag check to legacy seeds is NOT in scope and must not alter the
committed 704 active US rows).

## §4 Resolution, venue, and registrant law

- `resolve_universe()` unchanged: exit-ledger walk first, then directory match incl. class-notation variants,
  else unresolved-with-named-reason.
- **The closed MIC list stays closed.** `EXCHANGE_MIC` (NASDAQ/N/A only, :318-322) is not widened. A target whose
  only listing venue is unmapped (P/Z/V/M) becomes typed refusal `unsupported_venue`. Expected single live
  instance: CBOE (Z). Widening the MIC list is a human decision in its own diff — out of scope.
- **Registrant CIK is mandatory for minting** (fail-closed, R1 law): listed candidate with no CIK-map row →
  typed refusal `no_registrant_cik` (empirically 0 today; law still ships). Candidate in `ambiguous_tickers`
  (≥2 CIKs for one ticker) → typed refusal `ambiguous_registrant`.
- Not listed in the current directory snapshot and absent from the exit-ledger path: CIK present → typed refusal
  `not_listed_cik_present` (expected: EA, GGRP, NVVE); CIK absent → typed refusal `not_listed_no_cik`
  (expected: the 21 not-in-either-rail codes — OTC ADRs and post-M&A stale nodes). No listing evidence = no mint;
  a registrant CIK alone is registrant evidence, not listing evidence.
- Reused/renamed/pending-transition cases: NO new law. Candidates hit the unchanged R1 fence
  (`_compute_lost` + mint-refusal classes `pending_transition_refusals` / `resurrection_refusals`) inside
  `mint_master_rows()`. A fence refusal of a GMI-seeded candidate is surfaced in the GMI accounting with its
  existing typed reason — never silently dropped, never force-minted.
- Mint-once holds: every new row gets its `SEC:US-<MIC>-<CODE>` id once; subsequent runs re-derive, never re-mint.

## §5 Issuer axis — existing machinery only

New master rows enter the unchanged `apply_issuer_correction` pass. Registrant-CIK evidence resolves issuers under
the EXISTING evidence law; multi-security issuer grouping happens only where that existing law already allows it
(no allowlist additions this wave). Candidates whose issuer evidence fails settle to the existing
`NO_ISSUER_EVIDENCE` / `AMBIGUOUS` states. No new issuer namespace, no new grouping rule, no hand-set issuer ids.

## §6 Receipt accounting — `us_gmi_admission`

New receipt block mirroring `china_hk_admission`, plus the sum invariant the commission demands:

- `target_n` (expected 533 at pin), `resolved_total`, `resolved_this_run`, `refused_this_run` — refusals NAMED
  per code with typed reason (small enough to inline in full, like CN's 37).
- Invariant enforced in-build: `resolved_total + len(refusals) == target_n`. Zero silent drops — a candidate that
  falls out anywhere (eligibility, resolution, venue, CIK, fence) lands in exactly one typed refusal bucket.
- `identity_exception_excluded`: the registered-exception codes removed from the target set (expected: B).
- Refusal reason classes are the closed set defined in §3-§4 plus the existing fence/mint reason strings.
  Steady state on later runs: `resolved_this_run=0`, refusals stable until source state moves (CN/HK precedent).

## §7 Canonical regeneration + GMI sidecar rederivation

- `data/reference/*` regenerated ONLY via `scripts/build_security_master.py` (canonical builder; no hand-written
  rows, no manifest re-stamping). Expected: security_master 1,836 → ~2,344 (+~508 US active rows; exact number
  recorded in the receipt and the handoff); existing 1,836 rows byte-identical (checked per §9); issuer datasets
  updated only by the existing issuer pass; `security_migrations.parquet` unchanged unless a real supersession
  fires (expected: none).
- Sidecar: ONE new generation via direct `engine.theme_graph.identity_resolution.derive_rows()` +
  `engine.theme_graph.store.write_identity_resolution()` over the COMMITTED `nodes.parquet` and the new master —
  never the full theme-graph pipeline in a worktree (`DSC:THEME-GRAPH-FULL-REBAKE-DIVERGES-LOCALLY`).
- Expected sidecar deltas: us RESOLVED 702 → 702 + (mint count) (~1,210); us NOT_IN_MASTER 533 → 533 − (mint
  count) (~25); cn/hk/ca/intl states unchanged (984 RESOLVED / 147 RESOLVED / 167 NOT_IN_MASTER /
  233 UNSUPPORTED_MARKET); GOLD/B DEFERRED_IDENTITY_EXCEPTION (2) and ENTITY_TYPE_CONFLICT (1) unchanged.
  New U.S. resolutions join via the existing rules (expected rule 5 exact inception-code match; no new
  `theme_graph_native` aliases for US — that vendor space is CN/HK-only).
- `data/theme_graph/_meta.json`: update ONLY `identity_resolution_state_counts` (CN-HK precedent; other fields
  describe the last full pipeline run and are not touched).
- GMI node ids and theme memberships: byte-unchanged (`nodes.parquet` is read-only graph truth).

## §8 Idempotency and second-run stability

Two consecutive `build()` runs (empty-scratch and seeded-from-committed-baseline, house standard) produce
byte-identical `security_master.parquet` / `vendor_aliases.parquet`. Run 2 with the widened seed set must
re-derive EVERY pre-existing and newly-minted active U.S. row (the fence must not flag any of them lost) and
report `resolved_this_run=0` with stable refusals. This is the direct guard against the CN/HK wave's
false-"lost" regression class.

## §9 Hostile-case test matrix (extend EXISTING suites only — no new test files)

In `tests/test_dataos_security_master.py` (fixtures may use real committed data, CN-HK precedent):

1. ETF masquerade: GMI-seeded code with directory `etf=True` → `not_common_equity_etf`, never minted.
2. Test issue → `not_common_equity_test_issue`.
3. Preferred → `not_common_equity_preferred`.
4. Unsupported venue: real-data CBOE (Z) → `unsupported_venue`; closed MIC list asserted unchanged.
5. Listing present, CIK absent → `no_registrant_cik` (fixture).
6. CIK present, listing absent → `not_listed_cik_present` (real-data EA).
7. Neither rail → `not_listed_no_cik` (real-data exemplar from the 21).
8. Ambiguous ticker→CIK → `ambiguous_registrant` (fixture forcing the ambiguous_tickers path).
9. Reused ticker / pending transition via the GMI seed path → R1 fence refusal surfaces in `us_gmi_admission`
   accounting (no silent mint, no silent drop).
10. New clean IPO fixture → mints once; second run re-derives, does not re-mint (mint-once).
11. Class shares: two codes → one CIK, both listed → two securities, issuer grouping per existing law only.
12. Same-CIK sponsor/trust pair (common + ETF) → common mints, ETF refused, no issuer fabrication.
13. LP common unit (real-data, e.g. ET) → mints (structural flags all false), pinning the §3 ruling.
14. Accounting completeness: invariant `resolved_total + refusals == target_n`; identity-exception exclusion
    disclosed (B); zero targets unaccounted.
15. Regression pins: CN 984 + HK 147 + existing US 705 rows byte-identical after the expansion run;
    legacy `coverage` block semantics unchanged (712-scope).
16. Idempotency + run-2 stability (§8), asserting the fence fired zero times on run 2.

In `tests/test_theme_graph_identity_resolution.py`: new-generation assertions — us RESOLVED/NOT_IN_MASTER match
the master receipt's accounting; prior generations untouched (append-only history); ca-only NOT_IN_MASTER law
still holds; cn/hk unchanged.

## §10 File scope (owned files — anything else requires STOP + return)

- `scripts/build_security_master.py` (seed stage, eligibility, accounting; additive)
- `tests/test_dataos_security_master.py`, `tests/test_theme_graph_identity_resolution.py` (extend only)
- `data/reference/*` (canonical regeneration only), `data/theme_graph/identity_resolution.parquet`,
  `data/theme_graph/_meta.json` (state-counts key only)
- This contract file (builder may append an IMPLEMENTATION NOTES section; never edit frozen sections)

Expected ZERO edits: `lib/dataos/*`, `engine/theme_graph/identity_resolution.py`, `config/*`, `collectors/*`,
`data/theme_graph/nodes.parquet`, price stores. If the builder believes any of these requires an edit, STOP and
return with the reason — that is a contract-change decision, not an implementation detail.

## §11 Acceptance gates (NOT DONE UNLESS)

1. `us_gmi_admission` present with the §6 invariant holding; refusals named per code; expected magnitudes
   (mints ≈ 508, refusals ≈ 25 across the §4 classes) either met or every deviation explained by a typed refusal.
2. All §9 tests green; the full targeted suite list green
   (`tests/test_dataos_identity.py tests/test_dataos_security_master.py tests/test_dataos_registry.py
   tests/test_theme_graph_identity_resolution.py tests/test_theme_graph_contracts.py
   tests/test_identity_seam_agreement.py`).
3. Idempotency + run-2 stability proofs (§8) executed and reported.
4. `python3 scripts/check_theme_graph_contracts.py --strict` clean on the regenerated artifacts.
5. Sidecar regression floors: us ≥ 702→(702+mints), cn = 984, hk = 147; node ids/memberships unchanged.
6. `python3 scripts/agentos.py validate` exit 0 (at ship time, with the wave records).
7. Zero edits outside §10 owned files (verified by diff --stat against the pin).

## §12 Completion law (Sol, verbatim)

Merge = **BUILT_NOT_PROVEN**. DONE requires the next natural production nightly showing
source → canonical master → fresh GMI projection with measured before/after U.S. resolution counts.
No session declares this wave done before that proof is recorded.

## §13 Non-goals (binding)

Canada; GOLD/B; IBIT graph-kind correction; PIT vintages; ontology/probation; rights closure; ThemeState;
Prophet ranking/admission/UI; EQR/VMRK duplicate price-store cleanup; MIC-list widening; legacy-universe
eligibility retrofit; any CN/HK issuer-evidence class.

---

## AMENDMENT §1 — post-review rulings (Fable, 2026-08-21; binding on the fix pass)

Adversarial review verdict FAIL (1 blocker, 3 majors, 8 minors). Rulings R1-R12 map to the reviewer's findings 1-12.

**R1 (blocker — fix).** The §3/§4 eligibility+CIK gate applies to GMI-ONLY admission targets. A candidate whose key
is in the legacy curated universe (`legacy_keys`, the 710-key set) is NEVER gated by this wave's law, regardless of
master state — legacy mint law is untouched, exactly as §3's closing line intended (its "no ETFs" premise was
false: ETHA/IBIT are curated seeds AND ETFs AND committed rows; they must keep minting on a from-scratch rebuild).
Gate condition: GMI target ∧ NOT legacy. Regression pin required: from-empty `build()` mints AEP, CTRA, EQR, FI,
FISV-chain, ETHA, IBIT (composition test, R4).

**R2 (major — fix).** `us_gmi_admission` becomes the true `china_hk_admission` mirror: `target_n` = FULL GMI-U.S.
company population net of registered identity exceptions (expected 1,236 at pin); `resolved_total` = CUMULATIVE
count of target codes with an active master resolution post-run (expected 1,210 = 702 pre + 508 new);
`resolved_this_run` (expected 508 on this bake, 0 at steady state); `refused_this_run` named per code (expected
25); plus explicit disclosure entries for every code excluded by the root-code-equality path (R6) so the partition
is COMPLETE and STANDING: `resolved_total + refusals + disclosed_exclusions == target_n`, enforced in-build. A
future lost US row re-enters as a refusal and moves the counts — the invariant must be able to see it. §12's
nightly proof reads before/after from this block.

**R3 (major — fix).** Generalize the duplicate-claim guard to ALL rendered listing keys, not only pre-existing
ones: when ≥2 target codes render to one key, exactly ONE claimant wins (deterministic: spelling equal to the
resolved row's current symbol, else lexicographically smallest), one mint, one alias-row set; every non-winning
claimant lands in the receipt as a typed disclosure naming the winning id. `build()` must be structurally unable
to hand `VendorAliasTable.from_records` duplicate coverage from this path. Fixture test: the reviewer's
NEWA/NEWAOLD same-root pair on a NEW key — build() completes, one row, disclosed duplicate, invariant holds.

**R4 (major — fix).** End-to-end `build()` tests are mandatory: (a) from-EMPTY composition test asserting the R1
names mint and the master's US row count matches the legacy+GMI union expectation; (b) seeded-from-pin-baseline
transition test asserting `resolved_this_run == 508`, the 25 named refusals, and the R2 block shape. The
`load_gmi_us_seeds → []` monkeypatch stays only in tests whose subject is explicitly legacy-only behavior.

**R5 (minor — fix).** Structural-flag law: a GMI candidate resolved via the DIRECTORY is always flag-checked
(missing flags for a directory-resolved candidate = hard `IdentityError`, never a skip). A GMI candidate resolved
via the EXIT LEDGER is eligibility-EXEMPT BY LAW: the hand-curated ledger (authored from SEC filings) is itself
the human-verified security-type evidence; the exemption is documented in code and disclosed in the receipt entry.

**R6 (minor — fix).** Root-code-equality exclusion is valid ONLY when the code's own resolution outcome lands on
the matching existing active row (rename-chain/current-symbol coverage verified), else the code is a genuine
target. All exclusions taken by this path are disclosed per R2.

**R7 (minor — fix).** Re-run the canonical regeneration AFTER the final fix-pass code commit so
`_receipt.json.code_version` names a commit whose builder actually produces these bytes. The sidecar rebake and
its `computed_at`-pinned test constant update accordingly.

**R8 (minor — fix within bounds).** §9 item 9's test must exercise the REAL `build()` accounting path (no
re-implemented loop in the test body); items 4/6/7/13/14/15 may remain artifact-pinned per house precedent, with
item 14's completeness now also covered end-to-end by R4(b).

**R9 (minor — contract correction, then fix).** §8/§9.16's "fence fired zero times on run 2" was wrongly phrased
(the pin's own steady state carries `listing_continuity: [WBS, GOLD-identity-exception]`). Corrected law: run-2
stability = `listing_continuity` identical to the expected steady set, zero pending-transition and resurrection
refusals, `resolved_this_run == 0`, byte-identical artifacts. Test asserts exactly that.

**R10 (minor — fix within bounds).** Where a new test's intent is CROSS-ARTIFACT CONSISTENCY, derive expected
numbers from the committed receipt rather than hardcoding; hardcode only where the intent is pinning this wave's
delivered magnitude. The 25 refusals are directory-staleness misses and WILL heal — tests must not make rail
healing a merge-gate red beyond the existing house exposure.

**R11 (minor — fix).** Receipt scoping: `symbol_directory.universe_keys` reverts to the legacy curated count
(710); the GMI seed population gets its own named field (e.g. `gmi_seed_keys: 1238`). No reader of the existing
field changes meaning.

**R12 (nit — fix).** A venue-resolved candidate whose `ListingKey` construction fails is typed
`unrenderable_code` (added to the §4 closed set), not `unsupported_venue`.

Fix-pass order: code (R1, R2, R3, R5, R6, R11, R12) → tests (R4, R8, R9, R10) → regeneration + rebake LAST (R7)
→ full §11 gates re-run. The reviewer re-verifies findings 1-12 individually (CONFIRMED/NOT-CONFIRMED per
finding) before the ship loop starts.
