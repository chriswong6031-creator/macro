---
key: BPC-JV-PREDECESSOR-WORKBOOKS-NOT-ON-DISK
claim: >
  Of the four originally supplied BioPharmCatalyst Excel workbooks (3-sheet,
  6-sheet, 8-sheet, 9-sheet), only the 9-sheet capture is recoverable on disk.
  Two filesystem copies share SHA256
  946c5f725ebfd3b71d254f229e006ba055a868a1d5d02d3344a74efb3882b535 (353040 bytes).
  The 3→6→8→9 sequence cannot be proven as strict supersession, overlapping
  snapshots, or unique predecessor rows because W1–W3 bytes are absent.
falsifier: >
  ls or find recovering a second distinct BioPharmCatalyst_Tables.xlsx (or
  similarly named workbook) whose SHA256 differs from
  946c5f725ebfd3b71d254f229e006ba055a868a1d5d02d3344a74efb3882b535, or whose
  openpyxl sheet count is 3, 6, or 8. Any such file would refute "not on disk"
  and reopen the supersession question.
so_what: >
  Designate the recovered 9-sheet workbook as the canonical surviving capture,
  not a proven exact superset. Do not discard a later-found 3/6/8-sheet file as
  redundant. Licensed snapshot onboarding must preserve predecessor captures if
  they reappear; it must not invent a supersession proof from W4 alone.
kind: data
verified_at: 2026-08-19
verified_by: >
  ls "/Users/chriswong/Downloads/New Folder With Items 26/BioPharmCatalyst_Tables.xlsx"
  "/Users/chriswong/Documents/Cluade/Mastermind/BioPharmCatalyst_Tables.xlsx";
  find /Users/chriswong/Downloads /Users/chriswong/Documents/Cluade -name 'BioPharmCatalyst*.xlsx'
  this session recovered only those two copies, both 9 sheets, same SHA256
scope:
  - macro
  - biocatalyst
  - "WS:BPC-JV-RECON"
confidence: verified
---

## Notes

Search also covered Spotlight `BioPharmCatalyst*`, content search for sheet
name `Device Catalysts`, all `Downloads/New Folder With Items*`, Trash, recent
`.xlsx` mtime 2026-08-01..19, and Mail/Slack/Cursor attachment paths. Absence
is not proof the predecessors never existed; it is proof they are not in the
operator-held locations searched on 2026-08-19. Freeze §1 records W1–W3 as
not recovered.
