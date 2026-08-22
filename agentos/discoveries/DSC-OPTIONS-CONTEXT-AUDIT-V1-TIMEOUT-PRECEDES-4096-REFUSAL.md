---
key: OPTIONS-CONTEXT-AUDIT-V1-TIMEOUT-PRECEDES-4096-REFUSAL
claim: >
  The production Options Context Audit currently dies on O(N) corpus
  construction under TimeoutStartSec=180 and CPUQuota=50% (~90s CPU) before
  the frozen v1 4,096-reference refusal can fire; live episodes.jsonl is 3,897
  rows, projected references ~3,905, still below 4,096.
falsifier: >
  A completed production options-context-audit oneshot Result=success or
  journaled deterministic bound refusal at reference_count>4096 while
  TimeoutStartSec=180 and CPUQuota=50% remain unchanged, or a live
  episodes.jsonl row count ≤3,600 with the same timeout still firing first.
so_what: >
  Do not treat a context-unit timeout as a trusted-projection failure. Do not
  raise the timeout to "let v1 finish." Repair is preregistration v2 plus an
  independent audit unit. Recoupling the audit into
  macro-market-memory-context.service re-breaks W2C owner replay.
kind: runtime
verified_at: 2026-08-22
verified_by: >
  VPS read-only capture 2026-08-22T21:03Z–21:10Z: wc of
  /opt/macro/data/options_signal_episode/episodes.jsonl = 3897 rows / 6064140
  bytes; naturally scheduled context process 1608454 killed at 180s wall /
  90.134s CPU; trusted HEAD sha256
  8fa5f86b25dc47a7571ea5e790d1cf924b39cec256a031c666916a86daa14c08 unchanged;
  last successful audit HEAD 2026-08-21T02:19:03Z reference_count=1214.
scope:
  - macro
  - "WS:OPTIONS-CONTEXT-AUDIT-PREREG-V2"
  - "WS:MARKET-MEMORY-W2C"
  - scripts/project_market_memory_context.py
  - scripts/audit_options_market_memory_context.py
  - engine/options_market_memory_context.py
confidence: verified
---

The 4,096 wall is real and still ahead. The present production failure is the timeout in front of it.
