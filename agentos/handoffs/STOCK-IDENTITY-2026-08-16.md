---
workstream: WS:STOCK-IDENTITY
session: heal-5643-w2-onto-w1a1
model: local
ended_because: ci_handoff
mission: >
  Unblock PR #5643: merge current origin/main (including W1-A1 #5660) into the W2
  replay branch and drop the program-blocked identity hunks so merge-on-green can
  lawfully proceed.
state_before: >
  PR #5643 sat merge-blocked and dirty for two days. Blocking comments (2026-08-14)
  required W1-A1 first: do not collect B onto data/stock_identity/ohlcv, do not
  rewrite sealed GOLD.md/svg, do not treat the issuer correction as W2. W1-A1
  merged as #5660 at 2026-08-14T21:05Z; #5643 never rebased onto it.
changed:
  - path: research/stock_identity/dossiers/GOLD.md + GOLD.svg
    what: Restored W1-A1 disclosure-only GOLD.md and sealed GOLD.svg (byte-identical to origin/main).
  - path: research/stock_identity/dossiers/B.md
    what: Kept the registered W1-A1 B dossier; dropped W2's B.png / regenerated identity table.
  - path: data/stock_identity/ohlcv/B.parquet + manifest.json
    what: Removed the duplicate program-owned B tape; manifest is BABA/WPM only. B stays on baskets_ohlcv_v1.
  - path: data/stock_identity/addendum/ + addendum_b_*.parquet
    what: Dropped W2's parallel B fingerprint/state/episode addendum; W1-A1 amendments/ is the overlay.
  - path: scripts/stock_identity_pilot_addendum.py
    what: Removed. Identity overlay builder is scripts/stock_identity_build_w1a1.py.
  - path: tests/test_stock_identity_replay.py
    what: Retargeted addendum tests at W1-A1 receipt + baskets B + sealed GOLD.svg hash.
  - path: research/stock_identity/W2_EXPERT_REPLAY_REGISTRATION.md
    what: §6/§8/§9.9 record the withdrawal and point at #5660.
verified:
  - claim: GOLD.svg matches origin/main sealed blob.
    command: git hash-object research/stock_identity/dossiers/GOLD.svg && git rev-parse origin/main:research/stock_identity/dossiers/GOLD.svg
    result: both aa78863b3b5d80c2b63342cc9a757caaeb525a61
  - claim: B.md matches the W1-A1 receipt hash.
    command: python3 -c 'import hashlib,pathlib; print(hashlib.sha256(pathlib.Path("research/stock_identity/dossiers/B.md").read_bytes()).hexdigest())'
    result: 8d26fe53eed78d0700a9346b647c201354827323ad352813c0f8060008889230
  - claim: Governed stock-identity lane including W2 replay tests is green against W1-A1.
    command: python3 -m pytest tests/test_stock_identity_replay.py tests/test_stock_identity_replay_leak.py tests/test_stock_identity_atlas.py tests/test_stock_identity_partition.py tests/test_stock_identity_fingerprint.py tests/test_stock_identity_state_episodes.py tests/test_audit_reused_tickers.py -q
    result: 249 passed in 25.31s
unverified:
  - "CI packs on the merged head are the remaining merge gate."
unresolved:
  - "W2 expert-event rows for symbol B remain in pilot_events_v0.parquet as descriptive inventory computed on the withdrawn yfinance plane. They are not confirmatory. A baskets-plane re-extract is a future registered act, not this heal."
  - "W3 still needs its own operator go."
next_actions:
  - "Push this heal onto PR #5643, comment the W1-A1 reconciliation, re-arm merge-on-green, own through merge."
do_not_redo:
  - "Do not re-collect Barrick into data/stock_identity/ohlcv/B.parquet."
  - "Do not regenerate sealed GOLD.md measured rows or GOLD.svg."
danger_areas:
  - "W1-A1 hash-closure tests in test_stock_identity_atlas.py fail closed if GOLD.svg or the GOLD.md envelope is rewritten."
prs: [5643, 5660]
decisions:
  - DEC:SI-METHOD-LAW-CHANNELS
---

## Heal

#5643 was not a stale-CI problem. W1-A1 landed on main the same afternoon the
program-block comments were written; the W2 branch never absorbed that overlay
and accumulated merge conflicts (GOLD.md, B.md, WS record) plus a dirty merge
state. This session merges `origin/main` and keeps W2's replay/provenance while
deleting the identity hunks the block named.
