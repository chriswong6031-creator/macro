---
key: BPC-JV-PREDECESSOR-WORKBOOKS-NOT-ON-DISK
claim: >
  Local operator state only: of the four originally supplied BioPharmCatalyst
  Excel captures, solely the 9-sheet W4 bytes were present in the operator
  filesystem locations searched on 2026-08-19 (two copies, SHA256
  946c5f725ebfd3b71d254f229e006ba055a868a1d5d02d3344a74efb3882b535, 353040
  bytes). This is not a global unrecovered or no-longer-exists claim. Sol
  independently verified from the Chairman's File Library that W1, W2, W3, and
  W4 all still exist and are members of the authorized licensed corpus.
  Relationship state is UNRESOLVED_PENDING_SNAPSHOT_ONBOARD_CENSUS.
falsifier: >
  Local half: ls or find recovering a 3-, 6-, or 8-sheet BioPharmCatalyst*.xlsx
  in the operator locations searched on 2026-08-19 would refute local absence.
  Global half: a later session hashing the Chairman's File Library members that
  fails to produce four captures with 3/6/8/9 tabs (filenames
  BioPharmCatalyst_Tables.xlsx, BioPharmCatalyst_Tables(1).xlsx,
  BioPharmCatalyst_Tables(2).xlsx, BioPharmCatalyst_Tables(3).xlsx) would refute
  Sol's File Library membership statement.
so_what: >
  Do not treat W1–W3 as lost or globally unrecovered. Do not call W4 a proven
  superset of W1–W3. Do not treat W1→W4 as four temporal vintages or as evidence
  of BPC row revisions unless a later deterministic comparison proves
  time-varying common-sheet content. Do not invent predecessor SHA-256 values
  from File Library metadata; hash only when actual bytes are available. When
  SNAPSHOT-ONBOARD receives the four workbook bytes, census each file and
  classify pairs; preserve any genuinely unique predecessor rows.
kind: data
verified_at: 2026-08-19
verified_by: >
  Local: ls and find over operator Downloads / Documents/Cluade this session
  recovered only two 9-sheet copies, same SHA256
  946c5f725ebfd3b71d254f229e006ba055a868a1d5d02d3344a74efb3882b535.
  Global: Sol FINAL REVIEW on PR #5909 (2026-08-19) independently verified
  Chairman's File Library membership of all four originally supplied Excel
  captures (3/6/8/9 tabs; created 2026-08-16T08:33:25Z through
  2026-08-16T08:38:14Z). Spot checks (Device Pipeline row 838; PDUFA rows
  71–77) agree across W1–W4; full common-sheet equality is unproven.
scope:
  - macro
  - biocatalyst
  - "WS:BPC-JV-RECON"
confidence: verified
---

## Notes

**Local operator state.** Search covered Spotlight `BioPharmCatalyst*`, content
search for sheet name `Device Catalysts`, all `Downloads/New Folder With Items*`,
`Mastermind/BioPharmCatalyst_Tables.xlsx`, Trash, recent `.xlsx` mtime
2026-08-01..19, and Mail/Slack/Cursor attachment paths. Only W4 bytes were
available there and hash-verified.

**Global corpus state.** Chairman's File Library still holds all four originally
supplied Excel captures (Sol 2026-08-19):

| Capture | Filename | Tabs | Created |
|---|---|---:|---|
| W1 | `BioPharmCatalyst_Tables.xlsx` | 3 | 2026-08-16T08:33:25Z |
| W2 | `BioPharmCatalyst_Tables(1).xlsx` | 6 | 2026-08-16T08:36:13Z |
| W3 | `BioPharmCatalyst_Tables(2).xlsx` | 8 | 2026-08-16T08:36:58Z |
| W4 | `BioPharmCatalyst_Tables(3).xlsx` | 9 | 2026-08-16T08:38:14Z |

No predecessor SHA-256 is recorded. File Library metadata is not a hash.

**Relationship state.** `UNRESOLVED_PENDING_SNAPSHOT_ONBOARD_CENSUS`. The open
question is whether W4 is a superset of W1–W3 with identical common-sheet
content, not whether missing predecessors are supersets of W4.

**Temporal law.** Creation timestamps span ~5 minutes and Sol's spot checks
(Device Pipeline reaches row 838 in W1/W2/W3/W4; PDUFA rows 71–77 agree) make
progressively broader export packages the leading hypothesis. W1→W4 must not be
treated as four temporal vintages or as evidence of BPC row revisions unless a
later deterministic comparison proves time-varying common-sheet content.
