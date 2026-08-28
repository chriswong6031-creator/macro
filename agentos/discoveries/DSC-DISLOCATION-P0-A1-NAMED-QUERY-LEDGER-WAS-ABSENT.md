---
key: DISLOCATION-P0-A1-NAMED-QUERY-LEDGER-WAS-ABSENT
claim: >
  The P0-A1 dispatch named DISLOCATION_P0_SOURCE_QUERY_LEDGER_V1.json at
  SHA-256 04d502e398a0f2ae65df7b2f9d5156305094f7b10ca104da08792d7219c1f83c
  and sample seed
  ec34136d9ed11f0070a5eed0a0225f465f8095d3f3cd228b752b3c27c9f1e876, but those
  bytes were not present on origin/main, PR #6068, or the attached handoff
  directory; the executable freeze is the Turn-5 lexicon
  c164b5b3d0cfa8365a685e88662b00d8ad338957886fd51771286bf3c137cb58 plus the
  Turn-5 selection seed DISLOCATION-P0-SOURCE-2026-08-20-v1.
falsifier: >
  Produce a file named DISLOCATION_P0_SOURCE_QUERY_LEDGER_V1.json whose
  canonical SHA-256 is 04d502e398a0f2ae65df7b2f9d5156305094f7b10ca104da08792d7219c1f83c
  from a committed or attached source that predates this reconstruction.
so_what: >
  Do not invent a ledger that hashes to 04d502e. Preserve the named SHA as
  UNVERIFIED_ABSENT_SOURCE_FILE and historical reconciliation evidence. For resumed
  P0-A1R it is non-authoritative: #6068 plus
  DEC:DISLOCATION-P0-A1R-SOURCE-LAW-RECONCILIATION control selection and sampling.
  A derived ledger may be retained only transparently and may never impersonate 04d.
kind: landmine
verified_at: 2026-08-20
verified_by: >
  find/git/gh search for DISLOCATION_P0_SOURCE_QUERY_LEDGER_V1.json and
  04d502e398a0f2ae65df7b2f9d5156305094f7b10ca104da08792d7219c1f83c on
  origin/main, PR 6068, and /var/folders/.../aionui/general/; python3 -c
  lexicon_sha256 == c164b5b3...
scope: [macro, alpha-intelligence, WS:ALPHA-INTELLIGENCE-INTEGRATION]
confidence: verified
---

The #6117 A1 handoff remains historical extraction evidence, not the resumed
commission. The missing named ledger is a provenance gap, not permission to unfreeze
phrases, join prices, or override the A1R source-law reconciliation.
