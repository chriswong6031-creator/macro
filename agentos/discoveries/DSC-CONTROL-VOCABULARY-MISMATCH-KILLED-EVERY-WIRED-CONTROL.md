---
key: CONTROL-VOCABULARY-MISMATCH-KILLED-EVERY-WIRED-CONTROL
claim: >
  The only qledger producer that ever wired a matched control
  (scripts/backfill_qledger_intel_hub.py) has been passing ETF tickers (QQQ, XLV,
  SMH, ITA...) from the hub's `sectors` field into control_for_sector(), which is a
  GICS-NAME->ETF map — so every lookup returned None and every intel_hub claim
  registered uncontrolled; and the repo's only broad ticker->sector source
  (data/universe/membership.parquet) mixes TWO sector vocabularies (GICS
  "Information Technology"/"Health Care" beside Yahoo-style
  "Technology"/"Healthcare"/"Consumer Cyclical"), so any naive join through
  control_for_sector silently nulls on roughly half the universe.
falsifier: >
  Read scripts/backfill_qledger_intel_hub.py (`control=control_for_sector(sector)`
  where `sector = item["sectors"][0]`) against engine/ai_desk._GICS_ETF's keys; or
  re-run the census check: python3 -c "import pandas as pd;
  print(pd.read_parquet('data/universe/membership.parquet')['sector']
  .value_counts().head(20))" — the mixed vocabulary refutes/confirms directly. A
  live intel_hub claim carrying a non-null `control` would falsify the first half.
so_what: >
  Any future control (or sector-keyed) wiring MUST normalise vocabulary explicitly
  and COUNT its refusals — a lookup that returns None on mismatch is a legal state,
  so nothing ever alarms (this stayed dead four months). engine/qledger now ships
  sector_gics_etf() (alias-normalised, P0d C2.3) and the census
  (research/EVAL_OS_P0D_CONTROL_CENSUS.md D0-1/D0-2) records the measured
  coverage ceilings: intel_hub 72%, altdata* 89% — below the 0.95 coverage bar,
  which is WHY those families are classified benchmark_only, not
  matched_control_required. Do not re-propose "wire control_for_sector everywhere";
  the census refuted it by measurement.
kind: landmine
verified_at: 2026-08-14
verified_by: >
  research/EVAL_OS_P0D_CONTROL_CENSUS.md §2-§3 (derivation commands inline);
  scripts/backfill_qledger_intel_hub.py:101-103,170; live-store count 2026-08-14:
  454 sector-stamped intel_hub rows, 0 with a control, top values QQQ/XLV/XLK/SMH.
scope:
  - macro
  - engine/qledger.py
  - scripts/backfill_qledger_intel_hub.py
  - data/universe/membership.parquet
confidence: verified
---

## The shape of the defect, for the next wiring attempt

Two vocabularies and one silent None:

- The hub's `sectors` field holds **proxy ETF tickers** — already the answer, and
  often sharper than GICS (SMH semis, ITA defense, JETS airlines). Feeding an
  answer into a name→answer map yields None every time.
- `membership.parquet` rows carry `"Technology"` (Yahoo) and `"Information
  Technology"` (GICS) for different names; `control_for_sector` knows only GICS
  names. The alias set that closes it is exactly six entries
  (engine/qledger._SECTOR_ALIASES).

The general law: **a control construction that can return None on vocabulary it
does not recognise must count that refusal at the caller** (P0d contract C2.4).
Null-tolerance is correct for display tiers and lethal for evidence wiring —
indistinguishable from "no control exists" unless counted.
