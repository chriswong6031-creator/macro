---
workstream: WS:PROPHET-US-V4-RECOVERY
session: "Fable orchestrator (V4-D2B2-US wave: census scout, builder, 3-pass opus review)"
model: fable
ended_because: complete
mission: >
  V4-D2B2-US (Sol commission 2026-08-21): starting from the current GMI U.S.
  company population still NOT_IN_MASTER, admit every source-supported U.S.
  security through the existing Data OS security-master builder, or issue an
  explicit typed refusal for every target; re-derive gmi.identity_resolution/v1;
  prove the expansion through the natural nightly path.
state_before: >
  At pin 0c097d0f9621 (origin/main): master 1,836 rows (US 704 active + 1 VMRK
  tombstone, CN 984, HK 147). GMI U.S. company field 1,238 nodes = 702 RESOLVED
  + 533 NOT_IN_MASTER + 2 DEFERRED_IDENTITY_EXCEPTION (GOLD/B) + 1
  ENTITY_TYPE_CONFLICT. Root cause of the 533: load_universe()'s curated
  breadth+baskets seed set (710 keys) was never wired to the theme graph's U.S.
  company nodes — a seed-scope gap, not a resolution defect. Rails at pin:
  symbol directory snapshot 2026-08-21 (13,168 rows incl. otherlisted), SEC CIK
  map 2026-08-18 (10,398 rows).
changed:
  - path: research/prophet_v4/d2/D2B2_US_FROZEN_CONTRACT_2026-08-21.md
    what: >
      Fable-frozen contract + AMENDMENT §1 (12 rulings from review pass 1) +
      AMENDMENT §2 (4 rulings from pass 2, incl. the resolved_total semantics
      ruling: a target covered by an ACTIVE master row IS resolved; rail
      non-rederivability is staleness, never a refusal).
  - path: scripts/build_security_master.py
    what: >
      load_gmi_us_seeds() (nodes.parquet, kind=company, market_scope=us; the
      derived sidecar is never read); structural common-equity eligibility for
      GMI-ONLY targets (etf/test_issue/is_preferred → typed refusals; legacy
      curated keys NEVER gated — from-empty rebuild keeps AEP/CTRA/EQR/FI/
      ETHA/IBIT); closed EXCHANGE_MIC untouched (unsupported venue → typed
      refusal); CIK mandatory fail-closed (no_registrant_cik /
      ambiguous_registrant); not-listed splits by CIK presence;
      _collapse_duplicate_claims generalized to all rendered listing keys
      (deterministic winner; legacy pairs NEVER collapse; non-winners disclosed
      typed); structural venue_mapped field discriminates unsupported_venue vs
      unrenderable_code; us_gmi_admission receipt block with in-build
      fail-closed invariant resolved_total + refusals + disclosed_exclusions ==
      target_n, plus resolved_not_rederivable and
      identity_exception_excluded/structural_check_exempt_exit_ledger
      disclosures; seed_counts.universe_keys stays legacy-only (710), new
      gmi_seed_keys (1,238).
  - path: data/reference/
    what: >
      Canonical regeneration: security_master.parquet 1,836 → 2,344 rows (+508
      US active; 257 XNAS / 246 XNYS / 5 XASE); all 1,836 pre-existing rows
      byte-identical; vendor_aliases 3,954 → 5,986; _receipt.json gains
      us_gmi_admission (target_n 1,236 = resolved_total 1,210 + 25 named typed
      refusals + 1 disclosed FISV→FI duplicate-claim exclusion;
      resolved_not_rederivable = WBS, SATS); code_version = ea917aeacc01
      (a commit whose tree byte-produces these artifacts).
  - path: data/theme_graph/identity_resolution.parquet
    what: >
      Append-only rebake via direct derive_rows()+write_identity_resolution()
      (never the full pipeline): us RESOLVED 702 → 1,210, us NOT_IN_MASTER 533
      → 25 (strict set equality with receipt refusals); cn/hk/ca/intl states
      unchanged; GMI node ids/memberships untouched. Three new generations
      across the wave's bakes (ratified — indistinguishable from double nightly
      bakes; append-only law forbids rewriting).
  - path: data/theme_graph/_meta.json
    what: identity_resolution_state_counts only (sums 2,806).
  - path: tests/test_dataos_security_master.py
    what: >
      §9 hostile-case matrix + R-ruling pins: ETF/test-issue/preferred
      masquerade, unsupported venue (real CBOE), CIK-absent, ambiguous
      registrant, reused-ticker-through-fence, mint-once, class shares,
      same-CIK sponsor/trust, LP common unit (real ET), from-EMPTY composition
      (legacy∩GMI codes mint), transition-from-pin-baseline (resolved_this_run
      == 508), NEWA/NEWAOLD duplicate-claim fixture, legacy-pair no-collapse,
      accounting completeness via real build(), run-2 stability
      (listing_continuity steady set, zero pending/resurrection refusals).
  - path: tests/test_theme_graph_identity_resolution.py
    what: >
      Strict equality sidecar NOT_IN_MASTER set == receipt refused set; closed
      -set RESOLVED reconciliation naming the only two divergence classes
      (disclosed exclusions the sidecar resolves; ENTITY_TYPE_CONFLICT nodes) —
      a third class fails the test.
verified:
  - claim: >
      Acceptance accounting closes with zero silent drops: 1,210 + 25 + 1 =
      1,236, enforced fail-closed in-build at two IdentityError raise sites;
      refusals named per code (21 not_listed_no_cik; 3 not_listed_cik_present =
      EA, GGRP, NVVE; 1 unsupported_venue = CBOE); resolved_this_run == 508
      when run against the true pre-D2B2 baseline.
    command: >
      3-pass opus adversarial review, final pass: rebuilt from fresh
      0c097d0f9621:data/reference/* copies through the real build(); committed
      receipt re-derived independently.
  - claim: >
      All 1,836 pre-existing master rows byte-identical; from-EMPTY rebuild
      mints AEP/CTRA/TPH/FISV/EQR/AVB/ETHA/IBIT/SATS with zero
      eligibility-class refusals (the pass-1 blocker killed); superseded rows
      cannot confer R13 coverage (hostile ZOMBIE probe refused).
    command: reviewer's pin-row column diff + from-empty composition probe +
      synthetic superseded/cross-row/no-row build() probe.
  - claim: >
      Idempotency both modes (seeded-from-committed and from-empty):
      byte-identical parquets across two runs; run 2 resolved_this_run=0, zero
      pending-transition/resurrection refusals, listing_continuity steady
      (['WBS', GOLD identity-exception]).
    command: reviewer-re-run double-build byte comparisons (final closure pass).
  - claim: 407 targeted tests green; --strict contract check exit 0; agentos
      validate 0 errors.
    command: >
      python3 -m pytest tests/test_dataos_identity.py
      tests/test_dataos_security_master.py tests/test_dataos_registry.py
      tests/test_theme_graph_identity_resolution.py
      tests/test_theme_graph_contracts.py tests/test_identity_seam_agreement.py
      -q; python3 scripts/check_theme_graph_contracts.py --strict;
      python3 scripts/agentos.py validate
next_actions:
  - >
    SURVIVAL/PRODUCTION PROOF (contract §12, Sol's completion law): the next
    natural production nightly must show source → canonical master → fresh GMI
    projection with measured before/after U.S. resolution counts (sidecar us
    RESOLVED 702-era → 1,210; us_gmi_admission.resolved_total 1,210 with
    resolved_this_run 0 at steady state). Record the run id and delta in the
    WS d2 row. Neither this wave nor D2B2 flips to done before that.
  - >
    The 25 refusals are rail-staleness misses (directory snapshot lacks BLD,
    CFLT, EXAS, PSTG, MASI, SEE, … and OTC ADRs; EA/GGRP/NVVE CIK-only; CBOE
    unmapped venue) — they self-heal as the rails move; a future run's mint of
    a healed code is mint-once-safe and appears in resolved_this_run. No action
    needed.
  - >
    Sol reviews after this child returns: D2B2-Canada (167 ca nodes), D2B3+
    remain NOT authorized.
unresolved:
  - >
    NIT N1 (reviewer, ratified no-repair): R13 coverage is bare inception-code
    equality — a genuine ticker-reuse shape would be disclosed pointing at the
    wrong security (cannot mint or move rows; same inference sidecar rule 5
    already makes; inherited property, not new defect).
  - >
    NIT N2: resolved_not_rederivable/refused counts are master-state-dependent
    by design (from-EMPTY gives nr=[SATS]/refused 26 — WBS has no row there);
    both partitions close; 25 is not an invariant.
unverified:
  - >
    The exact date the production nightly first regenerates under this code —
    this wave's bakes were local canonical-builder runs, not the nightly's own.
do_not_redo:
  - >
    Do not re-litigate the LP common-unit ruling: ARLP/BEP/CQP/ET/UAN/XIFR are
    admissible common equity (structural flags + CIK); name-substring screening
    is FORBIDDEN identity inference (contract §3).
  - >
    Do not widen EXCHANGE_MIC to admit CBOE (Z/BATS) — closed-list law; a
    human widens it in its own diff, then the refusal self-heals next run.
  - >
    Do not "fix" WBS/SATS by minting or by re-typing them as refusals — they
    are resolved (active rows) with rail-staleness disclosed via
    resolved_not_rederivable + listing_continuity (AMENDMENT §2 R13).
  - >
    Do not gate legacy curated-universe keys with the GMI eligibility law
    (pass-1 blocker: from-empty rebuild lost AEP/EQR/ETHA/IBIT). Gate =
    GMI-only targets.
  - >
    Do not read the derived sidecar in the builder (target law is
    nodes.parquet + committed master only), and do not run the full
    theme-graph pipeline for the sidecar bake
    (DSC:THEME-GRAPH-FULL-REBAKE-DIVERGES-LOCALLY).
  - >
    Do not treat the sidecar's extra generations per wave as a defect —
    append-only; "one new generation" reads per-bake.
danger_areas:
  - >
    _collapse_duplicate_claims: legacy claimant pairs NEVER collapse (dated
    dual-alias shapes like EQR/VMRK are legal); dropping a legacy resolution
    reintroduces reviewer finding 13. Any future edit must keep the "dropped
    claimant is ALWAYS GMI-only" guarantee.
  - >
    The strict sidecar==receipt equality test and the closed-set RESOLVED
    reconciliation are the tripwires for accounting drift — do not weaken
    equality to containment (that exact weakening hid the pass-2 blocker).
  - >
    A future market expansion (Canada) must repeat BOTH the CN/HK
    country-split-before-fence pattern AND this wave's GMI-only gate scoping;
    the fence and eligibility laws are market- and provenance-scoped, not
    global.
---

# V4-D2B2-US handoff — canonical U.S. identity coverage expansion

PR #6190, branch `claude/v4-d2b2-us`, base pin `0c097d0f9621` (immutable squash
SHA recorded in the WS d2 row once merged). Contract
`research/prophet_v4/d2/D2B2_US_FROZEN_CONTRACT_2026-08-21.md` + AMENDMENTS
§1-§2 (16 adjudicated rulings across a 3-pass opus adversarial review:
FAIL → fix → FAIL residual → fix → PASS mergeable-as-is).

Merge state: **BUILT_NOT_PROVEN**. DONE requires the next natural production
nightly showing source → canonical master → fresh GMI projection with measured
before/after U.S. resolution counts (702-era → 1,210 RESOLVED; 533 → 25
NOT_IN_MASTER), per Sol's completion law restated in contract §12.
