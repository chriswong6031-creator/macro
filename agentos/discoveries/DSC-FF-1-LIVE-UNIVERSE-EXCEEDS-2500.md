---
key: FF-1-LIVE-UNIVERSE-EXCEEDS-2500
claim: >
  The canonical FF-1 universe data/edgar/fundamentals.parquet currently binds
  2837 unique tickers and 2837 unique CIKs, SHA-256
  84bc9a713314b20f5803a65f353bcf89b1ad82f45683757b0f5e6b1fe4394190 (303563 bytes),
  with zero duplicate/malformed rows. Merged MAX_UNIVERSE_ISSUERS=2500 therefore
  rejects the live census before any private R2 write. The first production
  scheduled incremental after PR #5820 (run 32097495749, 2026-08-18T03:59:58Z,
  head 0823b0daced1ec2a713de75531f00533b1ffb0ef) failed in two seconds with
  reason_code=universe_invalid and detail "universe has 2837 issuers; hard max
  is 2500".
falsifier: >
  Re-run load_universe on the current tracked data/edgar/fundamentals.parquet
  from a full checkout and observe issuer_count <= 2500, or re-read GitHub
  Actions run 32097495749 and find a different reason_code than universe_invalid.
so_what: >
  Do not dispatch July recovery or treat FF-1 as PROVEN_LIVE while the live
  parquet exceeds the bind cap. Do not shrink or replace the parquet to fit
  2500. Raise MAX_UNIVERSE_ISSUERS (or an equivalent bind fence) and add a
  regression that 2837 issuers bind. FF-1 tests used tmp parquet and left the
  live count unverified because that session was sparse.
kind: runtime
verified_at: 2026-08-18
verified_by: >
  Full checkout load of data/edgar/fundamentals.parquet (sha256sum + pandas unique
  ticker/CIK = 2837/2837); gh run view 32097495749 --log-failed (scheduled
  incremental, MODE=incremental, universe_invalid, expected_issuers=0); kernel
  path engine/fundamental_forensics/broad_sec_store.py load_universe raise then
  run_broad_sec_poll return PollResult before any store put.
scope: [macro, fundamental-forensics]
confidence: verified
---

The FF-1 implementation handoff recorded the live parquet size as unverified
because that session was sparse and did not open `data/`. Production is the
check. The canonical universe is the parquet (DNR: do not invent a second
1,500-name JSON). 2837 is a valid census, not a malformed file.
