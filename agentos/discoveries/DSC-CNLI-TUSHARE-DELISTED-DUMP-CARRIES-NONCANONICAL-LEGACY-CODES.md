---
key: CNLI-TUSHARE-DELISTED-DUMP-CARRIES-NONCANONICAL-LEGACY-CODES
claim: >
  TuShare's stock_basic universe returns rows whose ts_code is outside the
  canonical NNNNNN.SH/SZ/BJ scheme. The first live bounded canary of the
  full-A spine (workflow run 32914960162, 2026-08-26T00:24Z, window
  2024-01-02, 12-request cap) died on its first stock_basic reference call
  with `SpineError: not a canonical SH/SZ/BJ TuShare code: 'T600018.SS'` —
  a T-prefixed, legacy-`.SS`-suffixed vendor code shape. These rows are
  permanent vendor payloads, not transient glitches: any fail-closed
  identity validator that treats one such row as fatal kills the whole
  reference stage forever, and any accounting gate that requires
  quarantined_unknown_row_count == 0 for unit done-ness (as
  `_unit_done` in collectors/china_tushare_spine.py does) turns a
  quarantine-only repair into a permanent generation-promotion stall that
  also re-pays the same requests on every resume.
falsifier: >
  Run `python3 -m pytest tests/test_china_tushare_spine.py -q -k non_canonical`
  after replaying a fresh full stock_basic dump through the collector: if the
  per-call receipts (`non_canonical_identity_row_count`, emitted by
  collectors/china_tushare_spine.py `_call`) are zero across every
  exchange/list_status unit of a real reference generation, the family is
  transient or gone and this record is wrong. The narrow classification claim
  is falsified if a ts_code matching ^T\d{6}\.[A-Z]{2}$ is ever shown to be a
  canonical, currently tradable A-share identity that belongs in the master.
so_what: >
  Non-canonical vendor rows must be classified, not crashed on and not
  blanket-quarantined. The shipped design (branch
  claude/cnli-spine-noncanonical-quarantine) draws one three-way split
  everywhere: canonical rows land; the tight observed family
  ^T\d{6}\.[A-Z]{2}$ lands known_excluded with the narrow provenance
  "official_A_code_scheme_excludes_T_prefixed_legacy_vendor_code" (the only
  claim made is code-format law — no assertion about what the security is,
  no identity inference, raw payload preserved); every other non-canonical
  shape stays quarantined_unknown and deliberately blocks `_unit_done` as a
  tripwire for genuinely unknown payloads. Daily-cadence endpoints keep
  their own accounting, so if this family ever intersects in-range session
  data it surfaces loudly there instead of being silently lost. Future
  DEP-ID-ELIG work that needs pre-canonical-era delisted identities must
  route through the Data OS/GMI owner contract — the known_excluded rows
  carry the raw codes to start from.
scope:
  - macro
  - collectors/china_tushare_spine.py
  - WS:CN-LIMIT-ALPHA
kind: data
confidence: verified
verified_at: 2026-08-26
verified_by: >
  Live canary workflow run 32914960162 (tushare-spine-backfill mode=canary,
  2026-08-26T00:24Z) failed with the exact SpineError naming 'T600018.SS';
  reproduced and pinned by tests/test_china_tushare_spine.py stock_basic
  non-canonical suite on branch claude/cnli-spine-noncanonical-quarantine.
---

# TuShare delisted universe carries non-canonical legacy codes

Found by the first live DEP-EXACT canary under
`DEC:CNLI-FABLE-COO-AUTONOMOUS-EXECUTION`. See `WS:CN-LIMIT-ALPHA` and the
carrier PR for the three-way classification implementation and its tests
(`tests/test_china_tushare_spine.py`, stock_basic non-canonical suite).
