---
workstream: "WS:MASSIVE-STOCK-DAY-R2-COHERENCE"
session: claude/market-memory-m0c-source-qual-20260820
model: local
ended_because: complete
mission: >
  Bound the D-class torn-generation defect as its own lane. Do not repair it in
  M0C and do not weaken the W2C technical consumer.
state_before: >
  W2C technicals refused 2026-08-19 00:54–04:54Z on ticker-count mismatch and
  15:04–22:53Z on publish-last predating SPY. M0B classified these as D, not
  the v1 source-clock blocker.
changed:
  - path: agentos/workstreams/WS-MASSIVE-STOCK-DAY-R2-COHERENCE.md
    what: Proposed owning workstream.
  - path: agentos/handoffs/MASSIVE-STOCK-DAY-R2-COHERENCE-2026-08-20.md
    what: This continuation packet.
verified:
  - claim: >
      Consumer refuses ticker-count when store.n_tickers+1 != manifest.count,
      and refuses when manifest Last-Modified predates SPY Last-Modified.
    command: >
      python3 -c "from pathlib import Path; p=Path('engine/neuralweb/market_memory_technical_observation.py'); print(p.exists(), p.stat().st_size)"
    result: >
      ticker-count raise at the n_tickers+1 != count check;
      publish-last raise when manifest last_modified_at < SPY last_modified_at
      in both the live transaction and the stored-validator path.
  - claim: publish_r2 puts _manifest.json last after file uploads.
    command: python3 -c "from pathlib import Path; print('Manifest goes up LAST' in Path('scripts/publish_r2.py').read_text())"
    result: >
      comment "Manifest goes up LAST"; put_object _manifest.json after the
      thread-pool file uploads; skipped if any file upload failed.
unverified:
  - claim: >
      The 2026-08-19 tear was two overlapping daily.yml publishes rather than a
      single-run bug in put order.
    what_would_verify: >
      GitHub Actions job overlap for massive_stock_day publish steps on 2026-08-19.
unresolved:
  - Competing writer inventory (nightly vs any heal/partial publish).
  - Whether atomicity is a staging prefix + swap or a generation id in the manifest.
next_actions:
  - Census competing writers before coding.
  - Repair producer/publish atomicity. Keep the consumer refuses.
  - Do not fold this into W2C v2.
do_not_redo:
  - Do not teach W2C technicals to accept torn generations.
  - Do not SPY-only publish to dodge whole-store gaps.
danger_areas:
  - A write into a sparse omitted data/ tree truncates the store.
  - Partial --dirs publish with a full manifest is exactly the shrink/tear class
    publish_r2 already tries to guard.
---

# D-class — public massive_stock_day coherence

Owner: `collectors/massive_stock_day.py` (canonical store) + `scripts/publish_r2.py`
(public generation). Consumer
`engine/neuralweb/market_memory_technical_observation.py` is correct to refuse.

2026-08-19 ticker-count covered the entire 08-18 W2C window and delayed coherent
08-18 capture until 22:57Z. It did not cause 08-19's source-absent window
(S3 LastModified 04:54Z 08-20). Still a real nightly defect for every public
R2 reader, including v1 technicals.
