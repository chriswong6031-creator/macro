---
workstream: WS:ALPHA-INTELLIGENCE-INTEGRATION
session: grok/p0-a1-blind-extraction
model: local
ended_because: complete
mission: >
  Produce a price-blind source-only candidate queue and first accepted-manifest
  draft from the frozen Turn-5 query lexicon, without joining market data.
state_before: >
  Turn 5 froze source architecture and a 20-packet S0/S1 pilot. The A1 dispatch
  named a query ledger SHA that was not on origin/main or in the attached files.
  No complete cross-issuer source queue existed.
changed:
  - path: research/dislocation_intelligence/DISLOCATION_P0_BLIND_SELECTION_FREEZE_CONTRACT.md
    what: "Executable A1 freeze; records missing named ledger SHA as UNVERIFIED_ABSENT_SOURCE_FILE."
  - path: research/dislocation_intelligence/contracts/DISLOCATION_P0_SOURCE_QUERY_LEDGER_V1.json
    what: "Reconstructed query ledger from Turn-5 lexicon + selection protocol."
  - path: scripts/research/dislocation_p0_a1_lib.py
    what: "Frozen lexicon, firewall, selection keys, dual-pass span extraction."
  - path: scripts/research/dislocation_p0_a1_harvest.py
    what: "SEC FTS harvest, receipt join, extraction, coverage report."
  - path: research/dislocation_intelligence/p0_a1/
    what: "Inventory, 320-row queue, 313-row accepted draft, refusal/disagreement/coverage artifacts."
  - path: agentos/discoveries/DSC-DISLOCATION-P0-A1-NAMED-QUERY-LEDGER-WAS-ABSENT.md
    what: "Named A1 ledger SHA was not reconstructable from attached/committed sources."
verified:
  - claim: "Turn-5 lexicon SHA-256 is c164b5b3d0cfa8365a685e88662b00d8ad338957886fd51771286bf3c137cb58"
    command: "python3 -c 'from scripts.research.dislocation_p0_a1_lib import lexicon_sha256; print(lexicon_sha256())'"
    result: "c164b5b3d0cfa8365a685e88662b00d8ad338957886fd51771286bf3c137cb58"
  - claim: "Reconstructed query ledger SHA-256 is 496537f5d3822c160c93afb3cbccf55f6334028e20094979e1de797e6aab3b36 and is not the named A1 SHA"
    command: "python3 scripts/research/dislocation_p0_a1_harvest.py inventory --root . --out research/dislocation_intelligence/p0_a1"
    result: "query_ledger_sha256=496537f5... a1_declared_ledger_status=UNVERIFIED_ABSENT_SOURCE_FILE"
  - claim: "Harvest selected 320 raw candidates; 48 per primary family before extraction"
    command: "python3 scripts/research/dislocation_p0_a1_harvest.py rebuild --root . --out research/dislocation_intelligence/p0_a1"
    result: "raw_selected=320; five primary families 48; structural 48; resolved 24; overbuild 8"
  - claim: "313 accepted rows have EXACT_SEC_ACCEPTANCE clocks, 313 episode origins, zero forbidden market fields, all authority flags false"
    command: "python3 scripts/research/dislocation_p0_a1_harvest.py extract --root . --out research/dislocation_intelligence/p0_a1"
    result: "accepted=313 episodes=313 draft_sha256=832ac650cf18bd31b593fbb0214d9f3ac1b85ccdda6d417e12e5d81a35b76d32"
  - claim: "Price firewall passed; banned-path reads empty; hosts limited to official SEC"
    command: "python3 -c 'from pathlib import Path; from scripts.research.dislocation_p0_a1_lib import present_forbidden_paths; print(present_forbidden_paths(Path(\".\")))'"
    result: "[] ; A1A_ACCESS_LOG_EXTRACT banned_reads=[] event_count=912"
  - claim: "Unit tests for lexicon hash, firewall, form filter, issuer cap, dual-pass disagreement"
    command: "python3 -m pytest tests/test_dislocation_p0_a1_blind_harvest.py -q"
    result: "11 passed"
unverified:
  - claim: "Independent Fable/Opus source audit of twenty rows"
    what_would_verify: "Replay twenty draft candidate_id spans against document hashes and emit an auditor disagreement matrix"
  - claim: "Byte-identical harvest rerun against live SEC FTS"
    what_would_verify: "Second harvest with empty cache producing the same pool_sha256 values"
unresolved:
  - "Named A1 query-ledger SHA 04d502e... remains UNVERIFIED_ABSENT_SOURCE_FILE"
  - "MACRO_OR_INDUSTRY_WIDE is SOURCE_CAPACITY_SHORTFALL; Turn-5 lexicon has no phrases"
  - "STRUCTURAL_IMPAIRMENT_CONTROL had 9 incomplete FTS cells after HTTP 500s; selected 48 from 189034 complete hits"
  - "Extract dropped 7 of 320 for NOT_AN_ADVERSE_EVENT, leaving EXTERNAL 47 / WEATHER 46 / TEMPORARY 45 versus harvest quota 48"
  - "Canadian non-SEC issuers remain rights-blocked (SEDAR+ DDS not connected)"
next_actions:
  - "Fable/Opus audits twenty accepted rows against source hashes; do not join prices"
  - "If audit repairs classification, mint P0-A1.v2 of the draft only; do not re-open EXK"
  - "A separate runner may join canonical prices only after the audited manifest is frozen"
do_not_redo:
  - "Do not invent a ledger that hashes to 04d502e"
  - "Do not scrape SEDAR+"
  - "Do not treat FTS hits as economic episodes"
  - "Do not open prices, DRL, Prophet, Radar, or EXK replay outputs in the extractor seat"
  - "Do not retune EXK from these candidates"
danger_areas:
  - "Query phrase is provenance, never family evidence"
  - "Amendments are not origins"
  - "US ticker EDR is not Endeavour Silver"
  - "A capped FTS cell is incomplete, not a large complete pool"
  - "work/fts_cache.json is local-only (~739MB) and must not be committed"
discoveries:
  - DSC:DISLOCATION-P0-A1-NAMED-QUERY-LEDGER-WAS-ABSENT
---

## Continuation packet

- Candidate queue path: `research/dislocation_intelligence/p0_a1/A1B_RAW_CANDIDATES.json` (320 rows)
- Accepted draft path: `research/dislocation_intelligence/p0_a1/A1_ACCEPTED_MANIFEST_DRAFT.json`
- Accepted draft SHA-256: `832ac650cf18bd31b593fbb0214d9f3ac1b85ccdda6d417e12e5d81a35b76d32`
- Queue SHA-256: `85f43bb6d73b3c53ba0b54b0064168262362be2baee0889a214cdbf7b6b306f6`
- Reconstructed query ledger SHA-256: `496537f5d3822c160c93afb3cbccf55f6334028e20094979e1de797e6aab3b36`
- Extract access-log SHA-256: `6648403ebf66bd8193a31a1131450bc46b0b6ba8f7d3f4f9d30b785d89df4321`
- Disagreements: 79 (pass1 vs pass2 structural-impairment threshold)
- Harvest refusals: 284392 (quota/amendment/design-touched counts)
- Extract refusals: 7
- Source-form coverage after extract: 8-K 214, 6-K 99
- Family coverage after extract: PHYSICAL 48, EXTERNAL 47, CYBER 48, WEATHER 46, TEMPORARY 45, STRUCTURAL 55, RESOLVED 24
- Exact quota shortfalls: EXTERNAL -1, WEATHER -2, TEMPORARY -3 versus harvest 48 after extract refusals; MACRO 0/24 blocked
- Contaminated/design-touched: 262 harvest refusals (EXK / Endeavour Silver / CIK 0001015647); zero accepted EXK rows
- Fable audit command: `python3 scripts/research/dislocation_p0_a1_harvest.py report --out research/dislocation_intelligence/p0_a1`

Stop before market-data join. Do not ask whether any candidate recovered.
