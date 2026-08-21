---
key: BPC-HISTORICAL-FDA-CSV-LEFT-SHIFT
claim: >
  The authorized Historical FDA CSV (SHA256 f3852d34aad9b65d95e31db807f9509cfb84770eb91998533cb3687cea3d9002)
  has 4404 of 15700 data rows (28.1%) left-shifted because the row index is
  missing, so the stage column holds a date.
falsifier: >
  Re-read /Users/chriswong/Downloads/New Folder With Items 26/biopharmcatalyst_historical_fda_all_verified_2009_2026.csv
  (or any byte-identical copy of that SHA256). If csv.reader shows the first
  field of every data row is a digit, or if shifted/n != 4404/15700, this claim
  is false.
so_what: >
  Any reconstruction matcher must unshift before comparing stage or catalyst_date.
  Matching the raw CSV will treat dates as stages and silently drop 28% of rows
  from the Approved spine.
kind: data
verified_at: 2026-08-18
verified_by: >
  python3 csv.reader count this session: HEADER 13 cols starting row,ticker,name,…;
  ROWS 15700 SHIFTED 4404 PCT 28.1 (first field not digit)
scope:
  - macro
  - biocatalyst
  - "WS:BPC-JV-RECON"
confidence: verified
---

## Notes

Header is `row,ticker,name,catalyst_price_movement,price_at_catalyst_date,drug,indication,stage,catalyst_date,catalyst,conference,company_url,catalyst_url`.
Shifted rows are missing `row`, so every subsequent field slides left and `stage`
parses as a date. Unshift is a seed-hygiene step, not a source-system bug.
