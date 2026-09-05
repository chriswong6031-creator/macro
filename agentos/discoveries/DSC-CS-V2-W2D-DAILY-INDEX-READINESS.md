---
key: CS-V2-W2D-DAILY-INDEX-READINESS
claim: >
  The daily-index 403s in natural run 32786919396 were primarily publication-
  readiness observations caused by a UTC/New-York clock mismatch, not proof of
  SEC rate limiting or a general outage: the collector probed August 24 at
  20:04 ET before the documented nightly build and probed future New York filing
  day August 25; a later exact-header canary retrieved August 24 with a 22:01:43
  ET Last-Modified while August 25 remained absent and returned XML
  AccessDenied. Separately, a 30-page Latest Filings canary did not exhaust the
  same-day boundary, proving a one-page overlay cannot claim market-wide
  completeness.
falsifier: >
  Run `gh run view 32786919396`, inspect generation a6ff3b6b47db coverage,
  and repeat the exact-header Python canaries against the dated index objects
  and QTR3 listing. Disprove this by showing the original run instant was after the accepted
  August 24 index readiness boundary, the later August 24 object remained
  unavailable, its Last-Modified preceded the original probe, the quarterly
  listing already contained August 25, or an exact production-identity canary
  showed the same access failure on published historical indexes. Disprove the
  traversal finding by showing the official feed exposes a trustworthy total or
  next-link that bounds all entries, or that a one-page scan crossed the prior
  durable watermark in the captured high-volume cohort.
so_what: >
  Future sessions must classify a daily-index 403 using New York filing-day and
  object-readiness evidence before calling SEC down or changing pacing. They
  must keep separate same-day and daily-reconciliation health watermarks, page
  Latest Filings to a proven durable boundary, discard partial scans, and never
  promote feed metadata into W1 filing evidence.
kind: runtime
verified_at: 2026-08-25
verified_by: >
  GitHub run/job logs and committed coverage for 32786919396/97620633216 at
  generation a6ff3b6b47db; exact production-header read-only canaries for
  form.20260824.idx, form.20260825.idx, QTR3 index.json, and 30 pages of Latest
  Filings Atom; official SEC Accessing EDGAR Data, Developer Resources, RSS,
  Submit Filings, filing-status, and EDGAR Calendar documentation; hostile
  America/New_York clock and traversal fixtures.
scope:
  - macro
  - capital-structure-intelligence
  - collectors/sec_capital_structure.py
  - engine/capital_structure/sec_discovery_clock.py
  - engine/capital_structure/ingestion_health.py
confidence: verified
---

The observation is specific to the measured object/time pair. It does not turn
all SEC 403 responses into readiness signals; exact response, publication time,
archive listing, identity, and pacing remain part of classification.
