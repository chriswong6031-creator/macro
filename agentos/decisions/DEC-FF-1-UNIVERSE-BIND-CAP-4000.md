---
key: FF-1-UNIVERSE-BIND-CAP-4000
question: >
  The live canonical parquet has 2837 issuers and merged MAX_UNIVERSE_ISSUERS=2500
  fail-closes the production lane. What is the smallest FF-1 repair that unblocks
  commissioning without redesigning the source plane or shrinking the universe?
answer: >
  Raise MAX_UNIVERSE_ISSUERS from 2500 to 4000. Keep the bind fence. Do not alter
  data/edgar/fundamentals.parquet. Do not raise MAX_AFFECTED_ISSUERS or the
  Company Facts byte budget. Do not start FF-2. Return the repair PR to Sol;
  do not merge from this session and do not resume July recovery until the new
  cap is on main.
rationale: >
  The parquet IS the universe. 2500 was a safety fence, not a product census.
  2837 unique ticker/CIK pairs with zero duplicates is a legal bind. 4000 admits
  the measured census with growth room and still fail-closes an accidental
  full-EDGAR dump. At the 0.12s SEC pacing floor, 2837 Submissions requests imply
  roughly 5.7 minutes of minimum pacing time before network latency, response
  transfer, retries and durable publication. Actual fit inside the 90-minute
  workflow remains a production-commissioning fact to measure, not assume.
  Recovery Company Facts remains bounded by the existing 64-issuer / 32MiB
  continuation design.
alternatives:
  - option: Shrink or filter the parquet to <=2500
    why_not: Commission forbids altering the universe. DNR forbids a second
      hand-maintained name list.
  - option: Raise the cap to 3000 (minimum that admits 2837)
    why_not: 163 names of headroom will trip again on the next parquet growth.
      4000 is still a fence.
  - option: Remove the hard max
    why_not: Architecture expansion. The fence exists so a wrong file cannot
      become an unbounded SEC crawl.
  - option: Raise MAX_AFFECTED_ISSUERS so recovery finishes in one run
    why_not: Commission forbids increasing continuation limits because recovery
      takes several runs. Bounded continuation is the designed path.
evidence:
  - DSC:FF-1-LIVE-UNIVERSE-EXCEEDS-2500
  - GitHub Actions run 32097495749
  - engine/fundamental_forensics/broad_sec_store.py MAX_UNIVERSE_ISSUERS
  - collectors/edgar_forensics.py min_interval_seconds default 0.12
affects:
  - WS:FUNDAMENTAL-FORENSICS
  - engine/fundamental_forensics/broad_sec_store.py
  - tests/test_fundamental_forensics_broad_sec.py
confidence: high
reversibility: easy
decided_by: ceo-sol
decided_at: 2026-08-18
---

Sol accepted MAX_UNIVERSE_ISSUERS=4000 on 2026-08-18. Do not restore 2500, do
not shrink the parquet, and do not start FF-2. July recovery stays stopped
until this repair is on main and production commissioning resumes.
