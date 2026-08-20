---
key: W2C-V1-TRUSTED-CAPTURES-THREE-PER-WINDOW
claim: >
  The W2C v1 trusted-macro generation grew 12 → 15 → 18 captures across the
  first three sealed windows (2026-08-17/18/19), about +3 per window, against a
  hard reader pin budget of 256 that the accrual writer passes on every
  technical/trusted observe. Linear continuation would exhaust that budget
  mid-pilot and convert remaining v1 windows to missed via
  owner_pin_cap_exceeded_by_deadline, independent of any v2 work.
falsifier: >
  python3 read of the live trusted HEAD capture_count on
  /var/lib/macro-market-memory/state after the next three v1 windows showing a
  rate of ≤1 new capture per window, or a checkpoint/delta generation that
  resets the active count before 256.
so_what: >
  Do not treat v2 as the threat to the v1 control arm. Do not write v2
  captures into technicals-v1 or trusted-v1. v2 may raise its own reader
  budget on its own roots; it must contribute zero captures to any store v1
  reads. A trusted checkpoint/delta capability is a v1-survival item, not an
  M0D source-plane task.
kind: constraint
verified_at: 2026-08-20
verified_by: >
  python3 counts from agentos/handoffs/MARKET-MEMORY-W2C-2026-08-20.md windows
  2026-08-17/18/19 (trusted 12/15/18, technical 9/10/13) plus
  engine/neuralweb/market_memory_technical_store.py pin refusal above the
  caller-supplied maximum_capture_count and
  engine/neuralweb/market_memory_experience_accrual.py MAX_OWNER_GENERATION_CAPTURES=256.
scope:
  - macro
  - "WS:MARKET-MEMORY-W2C"
  - engine/neuralweb/market_memory_experience_accrual.py
  - engine/neuralweb/market_memory_technical_store.py
confidence: probable
---

# v1's nearest death is its own trusted pin budget

Three windows is a short sample. Verify live capture_count before treating the December breach date as a schedule.
