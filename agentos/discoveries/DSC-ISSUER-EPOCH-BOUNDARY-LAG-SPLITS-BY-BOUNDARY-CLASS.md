---
key: ISSUER-EPOCH-BOUNDARY-LAG-SPLITS-BY-BOUNDARY-CLASS
claim: >
  Issuer mechanism-epoch boundaries fall into two classes with sharply different
  recognition lags, and the split is structural rather than issuer-specific. A
  CORPORATE-EVENT boundary (a dated contract, closing, or termination) is disclosed on
  an 8-K within ~0-4 days of the event, so its operating-clock date and its
  `available_at` are effectively the same date. An OPERATING-ACTION boundary (a
  destock, a demand rollover, an assortment reset) is discovered only when the quarter
  containing it is reported, which is ~125-127 days after the operating-clock start.
  Measured on CELH 2018-2026: corporate events M0a/M1/M4/M5 lagged 4/0/0/1 days;
  operating actions M2/M3/M6 lagged 127/125/127 days. Consequence: an epoch table that
  carries ONE date per boundary is wrong for one of its two uses. Dating an
  operating-action epoch at its operating start and then using that date to partition a
  recognition-outcome statistic is look-ahead by roughly one quarter, because no market
  participant could know the boundary existed.
falsifier: >
  Build the same two-column table (operating-clock start vs first `available_at`) for a
  second issuer with both boundary classes in-window - the IMCE-HB-0 homebuilder census
  is the natural test - and show operating-action lags clustering materially away from
  the reporting cadence (i.e. not ~1 quarter), or corporate-event lags materially above
  the 8-K filing deadline. Either result breaks the class split. Reproduce the CELH
  measurement from research/imce/celh/celh_mechanism_epochs.csv columns
  start_event_time, boundary_available_at, boundary_lag_days.
so_what: >
  Every IMCE mechanism-epoch record must carry BOTH dates and a `boundary_class`, and
  any partition of a recognition statistic must use the `available_at` column. This is
  the concrete, table-level form of the freeze's G8-M2 epoch-clock rule: the rule says
  "recognition partitions use available_at"; this discovery says WHICH rows will bite
  (the operating-action ones, by about a quarter) and gives the field names that make
  the error impossible to make silently. It also supplies a cheap early sensor: because
  corporate-event boundaries are near-zero-lag and machine-readable, an 8-K Item 1.01
  distribution-agreement event is observable roughly a quarter before the operating
  action it presages shows up in a filing - at CELH the 2024-03-23 Pepsi Amendment No. 1
  (available 2024-03-26) preceded the first destock disclosure (2024-05-07) by 42 days.
kind: constraint
verified_at: 2026-08-21
verified_by: >
  research/imce/celh/celh_mechanism_epochs.csv (8 rows, boundary_class +
  boundary_lag_days); SEC submissions index https://data.sec.gov/submissions/CIK0001341766.json;
  8-K accessions 0001213900-19-021402 (M0a), 0001829126-22-014925 (M1),
  0001341766-25-000069 (M4), 0001193125-25-192888 (M5), 0001628280-24-013122
  (Pepsi Amendment No. 1); press releases 0001341766-24-000031 (M2),
  0001341766-25-000081 (M3), 0001341766-26-000047 (M6).
scope:
  - macro
  - research/imce/
  - WS:CYCLE-PATTERN-ISSUER-MECHANISM
confidence: probable
---

# Why this is `probable` and not `verified`

The lag arithmetic is exact and reproducible for CELH, but the CLASS SPLIT is a
one-issuer observation. The ~125-127 day figure is really "the issuer's reporting
cadence plus its filing lag", so it should generalize to any quarterly reporter — but
that is an inference, not a measurement, until a second family is drawn.

The 42-day contract-lead figure is a single instance and carries no forecast authority
of any kind. It is recorded as an OBSERVABILITY property (the event is dated, public,
and machine-readable early), not as a signal.

Related: [[DSC-ACCRUED-PROMO-ALLOWANCE-IS-INVISIBLE-TO-XBRL-COMPANYFACTS]].
Parent: `DEC:CPI-ISSUER-MECHANISM-RESEARCH-EXTENSION-NOT-NEW-ENGINE`.
