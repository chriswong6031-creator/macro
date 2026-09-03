---
key: BREADTH-TICKER-FIXUPS-PIN-THE-FETCH-SYMBOL-TOO
claim: >
  config.yml breadth.ticker_fixups pins not just the STORE key but the FETCH symbol:
  collectors/breadth.py applies the fixup in _repair (scraped symbol -> stored key) and
  then downloads closes for the STORED keys — it never imports lib/ticker_aliases, so
  there is no vendor-symbol translation on the breadth lane at all. A fixup row
  therefore only works while the vendor still serves the OLD symbol (true for MRSH->MMC
  and FISV->FI). Pinning a rename whose old symbol the vendor KILLED silently freezes
  the constituent out of S&P breadth entirely: measured for VMRK->EQR (added 08-20 per
  D2B1-R1 AMENDMENT M6), the live VMRK cache column stopped being written 08-19, the
  EQR column advanced only on 0-volume 63.66 ghost bars through 08-21, then nothing —
  the S&P 500 breadth lost the constituent's live tape for 8+ days with no warning.
  M6's stated premise ("consistent with YAHOO_FETCH_ALIASES['EQR']='VMRK'") assumed a
  translation layer the breadth collector does not have.
falsifier: >
  collectors/breadth.py._download_closes translating tickers through
  lib.ticker_aliases.fetch_symbol before the yfinance call (or any equivalent
  vendor-symbol seam on the breadth lane). With that seam, an old-key pin would keep
  fetching live bars under the new vendor symbol and this trap disappears.
so_what: >
  Before adding a ticker_fixups row for a rename, verify with a live pull that the
  vendor still serves the OLD symbol; if it does not (vendor followed the exchange),
  the old-key pin is not available on the breadth lane — migrate the stored key
  instead (the EQR->VMRK migration, 2026-08-28, removed the VMRK->EQR pin, re-keyed
  constituents/caches to VMRK, and spliced the EQR column history across at ratio 1.0).
  When auditing breadth staleness, a constituent whose cache column ends in flat
  0-volume repeats is this trap's signature, not a vendor outage.
kind: landmine
scope: [macro]
confidence: verified
verified_at: 2026-08-28
verified_by: >
  collectors/breadth.py:329-380 (_repair applies cfg ticker_fixups; no ticker_aliases
  import anywhere in the file) and :381+ (_download_closes fetches the repaired
  symbols); parquet probe of data/breadth/_closes_cache.parquet (VMRK column last
  2026-08-19 real bars, EQR column 63.66 ghosts 08-19..21 then frozen);
  data/breadth/_volume_cache.parquet EQR tail volume 0.0.
---

Found while executing the EQR->VMRK key migration. The MMC/FISV rows remain valid
(vendor still serves those old symbols). Related:
[[QLEDGER-GRADING-NEVER-CONSULTS-TICKER-KEY-MIGRATIONS]],
[[NIGHTLY-SECMASTER-REFRESH-WEDGES-SILENTLY-ON-PRUNE-CONFLICT]].
