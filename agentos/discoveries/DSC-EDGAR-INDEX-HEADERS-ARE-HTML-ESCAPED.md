---
key: EDGAR-INDEX-HEADERS-ARE-HTML-ESCAPED
claim: >
  A live EDGAR `-index-headers.html` page is HTML-escaped SGML. Splitting the
  raw bytes on a literal `<DOCUMENT>` tag reports every exhibit as absent even
  when EX-99.1 is on the filing. Accession 0000320193-26-000018 declares
  EX-99.1 as a8-kex991q3202606272026.htm after html.unescape, which is the
  same seam collectors.edgar_8k._parse_sgml_manifest already uses.
falsifier: >
  GET https://www.sec.gov/Archives/edgar/data/320193/000032019326000018/0000320193-26-000018-index-headers.html
  contains a raw unescaped `<DOCUMENT>` block, or the unescaped document map
  for that accession no longer includes TYPE EX-99.1.
so_what: >
  Any production reader of `-index-headers.html` must unescape before parsing
  DOCUMENT/TYPE/FILENAME. Do not treat "EX-99.1 is absent from the SGML
  document map" as a missing source until that unescape has been applied.
  Do not fall back to index.json type (directory-listing icon names).
kind: landmine
verified_at: 2026-08-17
verified_by: >
  company-intelligence run 32039517591 failed with "EX-99.1 is absent from the
  SGML document map for 0000320193-26-000018"; curl of that index-headers.html
  is 5945 bytes with `&lt;DOCUMENT&gt;` only; html.unescape yields 14 documents
  including EX-99.1 a8-kex991q3202606272026.htm.
scope:
  - macro
  - earnings-intelligence
  - scripts/refresh_event_workspaces.py
  - collectors/edgar_8k.py
confidence: verified
---

The E1P production dispatch of merged #5835 hit this before the public marker
could exist. The exhibit was never missing; the parser was.
