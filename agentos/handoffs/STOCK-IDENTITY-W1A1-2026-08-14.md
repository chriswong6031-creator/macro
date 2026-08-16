---
workstream: WS:STOCK-IDENTITY
session: stock-identity-w1a1-gold-wrong-issuer
model: codex
ended_because: ci_handoff
mission: >
  Re-examine the sealed W1 miner-probe GOLD identity, apply the program-correct
  preregistration remedy without rewriting frozen artifacts, and ship the registered
  effective-roster overlay through PR #5660.
state_before: >
  PR #5612 sealed a historical W1 miner recipe containing GOLD. PR #5613 established
  that every US GOLD store is Gold.com/A-Mark dealer tape, not Barrick; PR #5632 repaired
  the current gold_miners roster and supplied curated B OHLCV. The frozen W1 GOLD
  fingerprint/state/episode/dossier surfaces therefore measured the right tape under
  the wrong miner role.
changed:
  - path: research/stock_identity/W1_IDENTITY_ATLAS_V0_REGISTRATION.md
    what: >
      Append-only Amendment A1 registers disclosure plus a B-only addendum, exact source
      and merge receipts, frozen hashes/reference context, pre-registration implementation
      exposure, and the two zero-publication heading failures before the successful run.
  - path: engine/stock_identity/pilot.py
    what: >
      Keeps the sealed historical tuple explicit and exposes the effective miner tuple
      only after fail-closed validation of the complete W1-A1 receipt and all governed
      artifacts.
  - path: scripts/stock_identity_build_w1a1.py
    what: >
      Dedicated transactional builder for the exact additive allowlist; binds to draft
      PR #5660 and exact prerequisite PR pairs, ranks only B against the frozen W1
      reference, publishes receipt last, and never rewrites a sealed measured artifact.
  - path: data/stock_identity/amendments/w1a1_gold_wrong_issuer.json
    what: >
      Governing receipt: effective roster NEM/AEM/PAAS/WPM/AG/B, all authority false,
      measured_rows_mutated false, B design-touched/nonconfirmatory, exact hashes and
      registration PR head.
  - path: data/stock_identity/{fingerprints,state,episodes}/amendments/
    what: >
      Additive B-only fingerprint (1 row), daily state history (3,172 rows), episode
      catalog (66 rows), and episode JSON using baskets_ohlcv_v1 through 2026-08-13.
  - path: research/stock_identity/dossiers/GOLD.md
    what: >
      Reversible marked disclosure only: the sealed figures are Gold.com/A-Mark dealer
      behavior and are withdrawn as miner-neighborhood evidence. Removing the envelope
      restores the original SHA256 exactly; GOLD.svg is unchanged.
  - path: research/stock_identity/dossiers/B.md + B.svg
    what: >
      Additive Barrick dossier/chart, visibly watermarked with the 2014-01-02 curated
      tape floor and all-false descriptive authority.
  - path: tests/test_stock_identity_atlas.py + tests/test_stock_identity_fingerprint.py
    what: >
      Folded fail-closed provenance, transaction, schema, rank, disclosure, hygiene,
      partition, and result-integrity guards into the already-wired stock-identity lane.
verified:
  - claim: Sealed W1 artifacts remain byte-identical; GOLD disclosure is reversible.
    command: python3 -m pytest tests/test_stock_identity_atlas.py -q
    result: result-integrity hash closure passes, including GOLD.md restoration and unchanged GOLD.svg
  - claim: Current miner consumers cannot silently fall back to GOLD.
    command: python3 -c 'from engine.stock_identity.pilot import current_miner_probe; print(current_miner_probe())'
    result: "('NEM', 'AEM', 'PAAS', 'WPM', 'AG', 'B') after complete receipt validation"
  - claim: B is outside every sealed W1 membership and permanently nonconfirmatory.
    command: python3 -m pytest tests/test_stock_identity_atlas.py -q
    result: B absent from snapshot/pilot/blind/calibration; receipt quarantine exact
  - claim: Published amendment has zero authority and exact additive schema/hash closure.
    command: python3 -m pytest tests/test_stock_identity_partition.py tests/test_stock_identity_fingerprint.py tests/test_stock_identity_state_episodes.py tests/test_stock_identity_atlas.py tests/test_audit_reused_tickers.py -q
    result: "172 passed; every result-dependent receipt/hash/schema/authority guard ran"
  - claim: Every collecting pytest suite remains reachable from CI.
    command: python3 scripts/audit_unrun_tests.py
    result: "exit 0 after wiring #5540's green Overtime reconciliation suite into its existing Prophet audit owner"
  - claim: G-8 protected execution paths are untouched.
    command: git diff --stat origin/main...HEAD -- engine/entry_signal.py engine/signal_gate.py engine/confluence_tiers.py engine/signal_quality.py 'engine/prophet_*.py' engine/washout_turn.py engine/mtf_upturn.py engine/stock_personality.py engine/oracle/personality_context.py scripts/build_stock_library.py
    result: empty
unverified:
  - "No public site surface is added by W1 law; production verification is repository SHA advancement, not a rendered Atlas page."
  - "The §16.9 operator has not yet reviewed the additive B dossier; that return remains the W2 gate."
unresolved:
  - "Dead-name coverage remains the sealed W1 survivor-only limitation; A1 does not widen planes or redraw cohorts."
  - "The frozen UNIV_EW/rank context contains GOLD dealer behavior as one small universe component. A1 preserves and discloses it for comparability; it is never miner evidence."
next_actions:
  - "Merge PR #5660 on green and verify the merge is an ancestor of production."
  - "Conduct the §16.9 operator return over the sealed Atlas plus B addendum before W2."
do_not_redo:
  - "Do not rewrite MINER_PROBE or any sealed W1 combined artifact; PR #5612 remains the historical receipt."
  - "Do not add GOLD to COMPUTE_BLOCKLIST: its dealer tape is valid and readable; the defect was role identity."
  - "Do not collect a duplicate program-owned B plane or use close-only Yahoo B for the amendment."
  - "Do not use B in blind, calibration, future blind extension, or confirmatory grading."
danger_areas:
  - "The historical GOLD dossier content below the marked annotation still contains superseded W1 text by sealing law; consumers must read the post-seal annotation and effective receipt."
  - "B percentiles are hypothetical insertion ranks against the frozen 2,780-row reference, not membership in the W1 universe."
  - "A future B source append is allowed only after 2026-08-13; any revision inside the registered prefix must fail the logical digest."
prs: [5612, 5613, 5632, 5660]
decisions:
  - DEC:SI-METHOD-LAW-CHANNELS
---

## Note

The ruling is disclosure plus amendment, not quarantine. Frozen W1 remains reproducible,
while the effective analytical miner roster no longer labels a bullion dealer as Barrick.
