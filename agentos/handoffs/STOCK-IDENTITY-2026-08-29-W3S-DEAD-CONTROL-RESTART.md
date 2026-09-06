---
workstream: WS:STOCK-IDENTITY
session: sol/stock-identity-w3ar-recovery-20260829
model: codex
mission: >
  Preserve the bounded W3S dead-instrument-control restart contract, current canonical owner
  collision law, AVB quarantine, and truthful WAITING_CAPACITY state so a later lawfully assigned
  worker can re-derive at least five lawful terminated controls or return the frozen typed blocker.
state_before: >
  W2 had registered the Dead Instrument Control Set as a hard W5/Q1 predecessor, but no lawful W3S
  receiver had started. Invalid Secretary placement produced unauthorized PR #6678 before the
  no-start edge was consumed; Sol contained it, rejected its cohort verdict, and returned W3S to
  PRE-START / WAITING_CAPACITY / needs_placement.
changed:
  - path: agentos/handoffs/STOCK-IDENTITY-2026-08-29-W3S-DEAD-CONTROL-RESTART.md
    what: >
      Freezes current W3S mission, receiver/routing state, identity-owner collision law, deterministic
      candidate/exclusion law, AVB quarantine and future acceptance/stop contract.
  - path: agentos/workstreams/WS-STOCK-IDENTITY.md
    what: >
      Projects W3S as waiting capacity, #6678 as inert/unaccepted evidence, and AVB as quarantined.
prs: [6672, 6678]
verified:
  - claim: Unauthorized W3S PR #6678 is closed, draft, unmerged and does not modify main.
    command: "gh pr view 6678 --repo mastermindx-market-intelligence/macro --json state,isDraft,mergedAt,headRefOid"
    result: "CLOSED/DRAFT/unmerged; preserved only as inert audit evidence."
  - claim: Canonical delisting/security-master owner work overlaps W3S identity authority.
    command: "Inspect current PRs #6668, #6643 and #6659 and their changed paths."
    result: "They own delisted-symbol/security-master identity changes; W3S must consume, not duplicate, that authority."
  - claim: AVB's registered last-session heal is not durably assumed after a later collector write.
    command: "Compare #6623 heal history with later commit 27aebb3606cb3b2095f808de917516ae31b7ea35 on data/stocks/AVB.parquet."
    result: "A later daily collection modified the tape after the heal; AVB remains quarantined pending independent current-byte proof."
unverified:
  - claim: At least five lawful identity-resolved terminated U.S. tapes are available through accepted current owners.
    what_would_verify: >
      A lawfully bound W3S worker must freeze the identity-only candidate/exclusion law first, then
      re-derive the cohort from current canonical identity/source owners and return complete receipts.
  - claim: Current AVB parquet bytes are clean or contaminated after the later collector write.
    what_would_verify: >
      Independent exact-file verification against canonical identity/last-session and collector behavior,
      including the hostile successor-bar regression required by this packet.
decisions:
  - DEC:SI-REPLAY-ELIGIBILITY-SEPARATE-FROM-LIVE-AVAILABILITY
unresolved:
  - W3S has no current lawful receiver and remains WAITING_CAPACITY / needs_placement.
  - Current identity/delisting owner PRs must be re-reconciled at actual pickup; unmerged rows do not count.
  - AVB is quarantined until independent current-source durability proof closes the registered-plane hazard.
  - The >=5-control feasibility question remains scientifically unresolved because #6678's unauthorized verdict is not accepted.
next_actions:
  - Bind one eligible receiver through current lawful placement/commissioning procedure; do not use generic pickup spam.
  - Re-pin current Skillpack, Macro main, canonical identity/data owners and all overlapping PRs before START.
  - Freeze the deterministic candidate/exclusion law before any tape-dependent acceptance decision.
  - Re-derive the cohort, verify AVB independently, reuse only accepted owners, and return >=5 complete controls or the precise typed blocker.
do_not_redo:
  - Do not reopen, merge, inherit or cite #6678's cohort verdict as accepted W3S science.
  - Do not write a parallel delisting/security-master identity authority or count unmerged owner rows as canonical.
  - Do not widen providers or create another generalized market-data plane if accepted owners cannot supply five controls.
  - Do not use outcome, episode, expert, localization or fit information to hand-pick controls.
  - Do not open W3AR/P2/W3B/Q1 or Prophet authority from this wave.
danger_areas:
  - Reused tickers, renames, OTC-live names and index exits can masquerade as termination without canonical identity hygiene.
  - AVB may contain a successor-security splice after its registered terminal session; a derived truncation cannot hide an unsafe canonical owner plane.
  - Active #6668/#6643/#6659-style owner work can move identity truth during W3S and requires fresh reconciliation before acceptance.
  - Raw/unadjusted or close-only history is not lawful fingerprint/episode control data.
ended_because: blocked
operation_key: SI-W3S-DEAD-CONTROL-V1
parent_operation: SI-FABLE-COO-PROGRAM-20260828
wave: W3S
repository: mastermindx-market-intelligence/macro
status: waiting_capacity
preferred_avenue: Terra
receiver_binding_mode: CAPACITY_SELECTABLE
placement_state: WAITING_CAPACITY / needs_placement
why: >
  W3S is bounded deterministic identity/data engineering with a hard scientific stop. Terra is
  preferred for cost/quality; CTO Sol is second for owner/collision-sensitive engineering; Opus
  is an acceptable bounded fallback if no Codex-backed eligible seat exists.
why_not_fable: >
  The source/data boundary is frozen. Fable principal capacity is unnecessary unless a new
  cross-owner architecture contradiction appears.
---

# W3S — Dead Instrument Control Set Restart

## Observable mission

Produce either:

1. a preregistered, identity-resolved control set of **at least five terminated U.S. instruments** with lawful full adjusted OHLCV compatible with the existing Stock Identity fingerprint/episode machinery; or
2. the typed terminal result `BLOCKED_NO_LAWFUL_DATA`.

Nothing less unblocks W5/Q1 survivorship. Do not wait for W3AR; W3S depends on W2 only.

## Why this matters

W1 proved its then-allowed planes could not supply the required terminated cohort, and W2 made W3S a hard predecessor to confirmatory Q1. This is survivorship truth, not an optional robustness appendix. A live/surviving universe cannot be silently treated as evidence about dead instruments.

## Authority / precedence

At pickup, re-pin current versions and apply in this order:

1. current Chairman end-to-end Stock Identity completion intent carried by Sol's deliberate receiver assignment;
2. current protected Sol Skillpack and universal routing/dialogue law;
3. frozen Stock Identity masterplan survivorship law;
4. W1 dead-name impossibility receipt;
5. W2 registration making Dead Instrument Control Set a hard W5/Q1 predecessor;
6. accepted W3 freeze/plan;
7. this handoff's current owner/collision ruling.

A genuinely new market-data/identity/source authority must return to Sol.

## Verified current truth at 2026-08-30 authoring

- W3S remains unstarted by a lawful receiver. Prior Secretary placements were non-operative.
- Unauthorized PR #6678 was produced before a no-start edge was consumed, then contained. It is CLOSED UNMERGED/inert and **not an accepted W3S result**. Future W3S must rederive; it may not inherit #6678's cohort verdict.
- Current `config/delisted_symbols.yml` on main contains CTRA, TPH and AVB as resolved exit-ledger rows.
- AVB is **quarantined** for Stock Identity use until independent current-byte/collector-durability verification: its ledger says last_session `2026-08-14`, #6623 healed/truncated the stocks tape, but later daily collection commit `27aebb3606cb3b2095f808de917516ae31b7ea35` modified `data/stocks/AVB.parquet` again.
- Open identity/delisting owners materially overlap the canonical authority plane:
  - PR #6668 `claude/reused-tickers-delist-adjudication` — adds resolved FBRX/TWO exit rows, STRS OTC ack, ISSC→IA key migration; touches `config/delisted_symbols.yml` and tests/config.
  - PR #6643 `claude/eqr-vmrk-key-migration` — EQR→VMRK migration, LEG exit row, OTC acks and security-master refresh repair; touches `config/delisted_symbols.yml`, security-master/identity paths and other canonical identity stores.
  - PR #6659 `claude/secmaster-same-id-refinement-carveout` — related security-master owner behavior.
- Those open PR descriptions are collision evidence only; W3S must not treat unmerged rows as canonical accepted identity truth.

Fresh pickup must re-check their current state and all newer overlapping PRs.

## Current collision / ownership ruling

**W3S must not become a third writer to canonical delisting/security-master identity authority while existing owner work is live.**

Therefore:

1. `config/delisted_symbols.yml`, security-master identities, rename/key-migration truth and their tests are **read/consume by default**, not W3S-owned write surfaces.
2. Resolve candidate identity from the canonical accepted owner state at the exact W3S evidence snapshot. Unmerged identity PRs may be noted as pending candidates but cannot count toward the accepted cohort until canonical reconciliation.
3. If the existing identity owner merges/changes while W3S is active, refresh/rebase the candidate census before final acceptance; do not carry stale identity conclusions forward.
4. If a truly missing terminated identity must be added to canonical truth to reach the cohort, stop with `SOURCE_OWNER_CONFLICT` / decision request rather than writing around an active identity owner. Sol may coordinate a bounded owner extension separately.
5. W3S-owned durable truth lives under Stock Identity control receipts/manifests, not in a replacement delisting ledger.

This preserves one canonical identity plane while allowing W3S data/compatibility work to proceed in parallel.

## Exact W3S-owned scope

After fresh archaeology confirms current names/paths:

- existing Polygon/Massive dead-name collection path **as owner reuse** for the bounded terminated cohort, never a new general price-history platform;
- a bounded `engine/stock_identity/dead_control.py` / `scripts/stock_identity_build_dead_control.py` or current equivalent if needed;
- focused tests;
- `data/stock_identity/control/**` derived manifest, source/content receipts and any program-owned compatible tapes that the accepted existing owner is authorized to persist there;
- `research/stock_identity/W3_DEAD_INSTRUMENT_CONTROL_REGISTRATION.md`;
- Agent OS continuation records.

Do not touch W3AR/P2, ruler constants, W3B, Q1, Prophet, Radar owner paths, Terminal internals or unrelated data platforms.

## Deterministic candidate/sampling law — freeze before tape-dependent inclusion

Before acquiring or inspecting candidate OHLCV for acceptance, commit the candidate-population and ordering law using **identity/source facts only**.

Canonical candidate population at evidence time = every current accepted canonical exit-ledger instrument satisfying the registered U.S.-instrument/termination criteria, plus any other terminated identities already exposed by the same accepted canonical identity owner through an existing machine-readable interface. Do not scrape a broad new provider to hand-find five names.

A candidate may be excluded based only on preregistered facts required by the contract, such as:

- not actually terminated / still trading / only index-exited / only OTC-directory-absent;
- identity/ticker lineage unresolved;
- lawful source rights unavailable;
- full adjusted OHLCV unavailable;
- insufficient history for the existing fingerprint/episode machinery;
- adjustment/corporate-action semantics unproven;
- registered-plane contamination such as unresolved successor splice.

It may **not** be included/excluded based on episodes, returns, drawdowns, expert fires, localization, fit or any downstream outcome. Preserve every candidate and typed exclusion reason. No hand-picked five.

## AVB quarantine rule

AVB does not count toward the accepted five unless an independent current-source proof establishes all of the following on the exact evidence snapshot:

1. current tape contains no successor-security continuation after the registered AvalonBay terminal session;
2. adjusted basis is the intended AvalonBay basis, not successor-rebased history;
3. collector/update path will not reintroduce the splice on the next run;
4. tests fail on deliberate post-last-session real-volume successor bars;
5. canonical identity/last-session truth remains aligned.

If not proven, exclude AVB as `PRICE_PLANE_CONTAMINATED` and continue. W3S is not authorized to hide the problem by truncating a derived copy while canonical collection keeps corrupting the owner plane.

## Required accepted-instrument receipt

Each accepted control must include:

- stable instrument/security identity and ticker-history/reuse hygiene;
- terminal reason/date + authoritative source receipt;
- price owner/source and rights note;
- adjusted OHLCV mode and corporate-action semantics;
- first/last real observation, row/session counts and termination-boundary checks;
- known-at/correction/replay behavior;
- immutable source/content/spec hashes;
- proof it is terminated rather than stale, renamed, OTC-live or index-exited;
- proof no successor-security splice crosses its last session;
- compatibility smoke through the current Stock Identity fingerprint and episode inputs.

Missing is not zero. A close-only or raw/unadjusted history is an exclusion, not a partial control.

## Source/data law

Reuse canonical owners. Prior Sol law permits the minimum bounded act of using the existing Polygon/dead-name owner to persist OHLCV fields it already returns for the preregistered terminated cohort. That does **not** authorize:

- a second generalized market-data platform;
- a hidden cache;
- a new identity authority;
- an alternate corporate-action truth;
- provider widening if the accepted owner cannot supply enough controls.

If fewer than five lawful compatible terminated tapes remain after the preregistered exclusions, return `BLOCKED_NO_LAWFUL_DATA`.

## Deterministic vs statistical/model-generated

Primary method is deterministic identity/data validation. No model, fit, expert ranking, calibration or outcome selection. LLM review cannot originate an identity/termination/data fact.

## Failure states

- `BLOCKED_NO_LAWFUL_DATA` — <5 lawful compatible tapes after frozen exclusions;
- `IDENTITY_UNRESOLVED` — security/ticker continuity insufficient;
- `PRICE_PLANE_CONTAMINATED` — successor splice or basis pollution unresolved;
- `ADJUSTMENT_UNPROVEN` — behavioral-math adjustment contract not proven;
- `RIGHTS_UNRESOLVED` — source cannot be lawfully persisted/used;
- `SOURCE_OWNER_CONFLICT` — required identity/data mutation belongs to a current canonical owner or active overlapping carrier;
- `WATCH_UNAVAILABLE` — worker cannot maintain the return loop.

## Ordered implementation sequence

1. Re-pin Skillpack, current Macro main, W2/masterplan, canonical delisting/security-master owners and open overlapping PRs.
2. Register deterministic candidate/exclusion law **before tape-dependent acceptance decisions**.
3. Snapshot canonical accepted identity candidate set; mark unmerged identity-PR candidates as pending/non-counting.
4. Verify/quarantine AVB independently; do not inherit #6678's value claim.
5. Reuse the existing Polygon/dead-name owner for bounded full adjusted OHLCV acquisition/persistence where already authorized.
6. Validate every candidate and emit complete exclusion/accepted receipts.
7. Run fingerprint/episode compatibility smoke on every accepted tape.
8. Independent adversarial review of identity, termination, adjustment, source rights and owner duplication.
9. Hosted CI exact head.
10. Return `RESULT SI-W3S-DEAD-CONTROL-V1` or typed blocker; wait for Sol.

## Acceptance tests / production proof

At minimum prove deliberate mutants fail:

- live/index-exited/OTC-live ticker labeled terminated;
- rename treated as death;
- reused ticker/successor security spliced after last_session;
- real-volume bars after terminal session accepted without correction proof;
- raw/unadjusted or close-only plane accepted as full adjusted OHLCV;
- a candidate selected only after favorable tape/outcome inspection;
- an unmerged identity PR row counted as canonical accepted identity;
- W3S writing a parallel exit/security-master authority;
- generic second collector/data-platform creation.

Real proof requires a deterministic build on current canonical inputs yielding either >=5 accepted instruments with full receipts and compatibility smoke or the typed blocker. CI alone is not acceptance.

## Stop condition

Return in the lawfully assigned W3S carrier with:

- actual receiver/avenue and pickup/start/watch receipts;
- current Skillpack/main/identity-owner/open-PR pins;
- exact branch/PR/head/changed paths;
- candidate/exclusion ledger and counts;
- every accepted-instrument receipt;
- AVB disposition;
- current collision proof;
- compatibility smoke;
- tests/hosted CI;
- exactly `RESULT SI-W3S-DEAD-CONTROL-V1` with >=5 controls or `BLOCKED_NO_LAWFUL_DATA` / precise typed blocker.

Then wait for Sol. Do not open W5/Q1 or absorb W3B. Any nonterminal return keeps/re-arms exact-carrier continuation. Sol explicitly CONTINUE/REQUEST_REPAIR/STOP.
