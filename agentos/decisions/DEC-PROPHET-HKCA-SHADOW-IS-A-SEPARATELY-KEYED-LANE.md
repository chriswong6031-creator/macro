---
key: PROPHET-HKCA-SHADOW-IS-A-SEPARATELY-KEYED-LANE
question: >
  Should the HK/CA challenger substrate store rank pairs as paired columns on
  board_ledger rows (the US precedent DEC:PROPHET-SHADOW-GRAIN-IS-A-PAIRED-ROW
  ratifies) or as separately keyed sidecar stores — and where do discovery
  (population-changing) observations live?
answer: >
  Separately keyed sidecar stores, both lanes:
  data/prophet_shadow/{hk,ca}_rank_pairs.parquet keyed
  (date, ticker, challenger_definition) for Lane A same-population rank
  challengers, and data/prophet_shadow/{hk,ca}_discovery.parquet keyed
  (session_date, security_ref, challenger_definition) for Lane B discovery
  observations. board_ledger's keep-FIRST (date,ticker) identity is untouched.
  This is lawful under the paired-row DEC's own fallback clause: that DEC keys
  its acceptance to same-population + same-outcome + zero-authority holding on
  ONE row of an existing complete-universe store; HK/CA have no such
  complete-universe candidate store (board_ledger holds only the ~18-row board,
  and a challenger_definition column on it would demand either widening the key
  — forbidden by packet §8 — or overwriting canonical rows). The paired row's
  for-free guarantee (no copy divergence) is replaced by an explicit
  compensating invariant: a cross-store validator asserts every Lane-A
  (date,ticker) exists in board_ledger with matching board_pos and
  board_definition, and incumbent_rank is READ BACK from the board parquet
  after append_board — never re-derived.
rationale: >
  The store's contract decides the grain (the paired-row DEC's own principle).
  US pairing was correct because us_context_vector already persisted the
  complete candidate universe nightly and the shadow only added two numbers per
  existing row. HK/CA have no candidate-universe store to pair onto: pairing
  onto board_ledger would put challenger columns inside the single
  authority-bearing artifact every grader, scorecard, and era fence reads —
  maximizing blast radius exactly where zero-authority isolation is the
  commissioned property — and the board_ledger key cannot carry a second
  definition without the migration packet §8 forbids. A sidecar keyed by
  challenger_definition keeps the incumbent plane byte-untouched (mutation-
  killed: K1/K6/K7), lets N challengers accrue without touching production
  builders, and keeps Lane B (whose population by definition diverges from the
  board) out of any paired construction — the paired-row DEC itself requires a
  separately keyed lane the moment the population differs.
alternatives:
  - option: Paired columns on board_ledger rows (US shape)
    why_not: No complete-universe host store exists for HK/CA; board_ledger is
      the authority artifact (worst-possible leak surface) and its key cannot
      express challenger identity without the forbidden migration. Lane B
      populations diverge by design, which the paired-row DEC itself rules out.
  - option: One combined store for both lanes
    why_not: Lane A rows are pairings against an incumbent rank; Lane B rows
      have no incumbent pairing and a different clock (session_date,
      security_ref). One schema would force nullable pseudo-pairings and make
      the same-population claim untestable — the exact silent-divergence attack
      class the wave was commissioned to kill.
  - option: Reuse candidate_episode/v1
    why_not: Planned only — frozen schema name, zero code, US-first
      (CAPABILITY_LEDGER row candidate_episode, NOT_BUILT). Contract §0 carries
      the adopt/migrate obligation for when it lands cross-market.
evidence:
  - "research/PROPHET_SHADOW_CONTRACT_V1.md — frozen contract; §0 records the
    fallback-clause reliance and the compensating cross-store validator (F15)"
  - "Opus adversarial pre-implementation review 2026-08-21: draft verdict FAIL
    (5 merge-blocking / 9 major); all amendments incorporated before freeze —
    K-suite K1-K14 with positive-control, non-vacuity, and repo-wide static
    reader fence"
  - "engine/board_shadow.py + tests/test_board_shadow.py (36 tests) implement
    the contract; executed mutation kills recorded in the shadow-contract wave
    review"
  - "engine/board_ledger.py append_board — board_pos minted internally after a
    ticker-less skip; why incumbent_rank must be read back, never re-derived"
affects:
  - WS:PROPHET-HK-CA-REVAMP
  - engine/board_shadow.py
  - engine/board_ledger.py
  - scripts/build_canada.py
  - scripts/build_hk_library.py
confidence: high
reversibility: easy
reversibility_detail: >
  Forward-only and additive. If candidate_episode/v1 lands cross-market, the
  sidecar rows migrate into it by schema mapping (both are keyed on
  session/security/definition grains); nothing in production reads the sidecar,
  so the migration has zero consumer blast radius. Registering or retiring a
  challenger is a registry edit, never a schema migration.
decided_by: fable-program-owner (WS:PROPHET-HK-CA-REVAMP autonomous grant 2026-08-20)
decided_at: 2026-08-21
---
