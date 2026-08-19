---
key: AD1C0-FIRST-WRITER-QUALITY-RULE
question: >
  The polygon_gex chain store's first-writer-wins law (2026-08-06) made the first
  same-session snapshot immutable to protect close-proximate PIT capture — but a first
  attempt that is nonempty yet materially below the source-health floor then masquerades
  as the session's truth forever. What replaces bare first-writer-wins?
answer: >
  A first-writer QUALITY rule, receipt-arbitrated (data/polygon_gex_health/<session>.json
  sidecar): (1) a stored capture recorded HEALTHY (coverage >= SOURCE_HEALTH_FLOOR 0.90
  of the dynamic gex_symbols() universe) is IMMUTABLE; (2) with no file stored, any
  nonempty capture writes; (3) a stored PARTIAL may be replaced ONLY by a capture with
  strictly more successful underlyings AND (healthy OR +0.10 coverage), taken on the
  SAME ET calendar day as the session (no weekend/pre-open tape under a prior session's
  stamp), atomically and whole-file (single vintage; same-session orphan summary rows
  dropped); (4) legacy files with no receipt are treated healthy — never retro-replaced;
  (5) a corrupt receipt is preserved aside and the store becomes immutable with health
  unknown_receipt_corrupt — corruption can neither unlock an overwrite nor mislabel as
  healthy; (6) chain writes are write-ahead-receipted (write_pending) and atomic
  (tmp+os.replace), and a trailing write_pending is trusted only when the on-disk
  parquet matches it on BOTH underlying count and row count, else health degrades to
  unknown_write_interrupted (replaceable, never healthy); (7) --force keeps full
  diagnostic override, recorded as decision "forced".
rationale: >
  The evening run closest to the close still wins when it is healthy — the PIT
  rationale of the 2026-08-06 law is preserved (and strengthened: replacement is
  restricted to the session's own ET day, closing the mixed-tape vector the old law
  left open via --date/dispatch runs). What changes is that an unhealthy partial can no
  longer freeze a session: it is visibly partial in the receipt, downstream gates
  (AD-1's SOURCE_COVERAGE_GATE) refuse it, and a strictly better same-day capture may
  replace it. Fail directions were chosen deliberately: receipt corruption and crash
  windows fail toward IMMUTABILITY (protecting PIT bytes) but never toward a healthy
  label (protecting recovery).
alternatives:
  - option: Keep bare first-writer-wins (file-exists = immutable)
    why_not: a 3-of-375 capture (universe collapse, auth outage tail) locks the session at garbage forever; the 2026-08-13+ outage proved partial states occur in production
  - option: Last-writer-wins / always retry to a better capture
    why_not: destroys close-proximate PIT — later same-session runs are weekend/pre-open snapshots; exactly the mixed-tape class the 2026-08-06 migration quarantined
  - option: Replaceability decided by coverage alone without the same-ET-day window
    why_not: a Saturday broad capture would overwrite a Friday-evening partial with staler tape under Friday's stamp (reviewer finding M7)
affects:
  - "WS:ADVANCED-DATA-OPTIONS"
  - scripts/build_polygon_gex.py
  - collectors/polygon_options.py
  - data/polygon_gex_health/ (runtime sidecar, nightly-written)
evidence:
  - "Adversarial review rounds 1-4 on claude/ad1c0-options-source-recovery (session 25dc7757): findings B2/B3/M7/M8/W1/C1 and their flip-verified repairs"
  - "tests/test_polygon_gex.py first-writer decision matrix + TestW1VerifiedWriteAhead + TestC1TwoFieldVerificationMatch"
  - "scripts/build_polygon_gex.py docstring lineage: M7 2026-07-29, session re-scope 2026-08-06, AD-1C0 2026-08-19"
confidence: high
reversibility: costly
decided_by: fable-orchestrator
decided_at: 2026-08-19
---

Scope note: governs the polygon_gex chain store only. The receipt sidecar lives at
data/polygon_gex_health/ (a SIBLING of data/polygon_gex/ — nesting a health/ dir inside
the store violates the pinned stray-files invariant in
tests/test_polygon_gex_session_stamps.py). Supersedes the bare first-writer-wins
behavior of 2026-08-06 while preserving its PIT objective.
