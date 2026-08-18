# E0 Open Questions

Research questions only. No Opportunity Score, no weights, no new store.

---

## 1. Ownership (resolve before any build)

| # | Question | Why it forks the next step | Default if unanswered |
|---|---|---|---|
| Q1 | Is the Opportunity Evidence Vector a **view over** `data/us_prophet_rank/candidates/` plus DRL/revisions/CS, or a new artifact? | A new store would duplicate the US Context Vector (commission: do not create a new truth store). | **View / research join.** Do not mint `data/opportunity_vector/`. |
| Q2 | Who is allowed to *consume* the vector? Radar RP1, Prophet, neither? | Radar P-9 keeps detector, Research Priority, and Opportunity **separate**. Prophet gating is untouchable. W7 is **do not start**. | **Neither consumes.** Accrue research docs only. |
| Q3 | Does W6 RP1 already occupy the “look here first” slot so hard that a vector is redundant for operators? | RP1 is an attention order, not edge. A vector is typed evidence, not an order. | Keep both concepts; do not merge numbers. |

---

## 2. Measurement holes that block honest historical staging

| # | Question | Current bound | What would close it |
|---|---|---|---|
| Q4 | Can I3 (estimate revisions) be joined to winner t0 for any 2026-06+ case (MRNA, later 2025 leftovers)? | Revisions history exists 2026-06-16→08-18, **1,539** names latest, but **not joined** this session. | A PIT join script reading `data/revisions/history.parquet` at `asof ≤ t0`. Still unlicensed pre-June. |
| Q5 | Is there any in-repo path to pre-2026 consensus revisions? | Earnings Intelligence: `consensus: unlicensed_absent`. PEAD research uses seasonal random walk on purpose. | Licensed vendor **or** stay unavailable. Do not scrape. |
| Q6 | Can NEGLECTED be made a data state? | `n_covering` born 2026-06; attention 59.4% absent on 2026-08-17; Hot Tape has no `data/` artifact. | Spool Hot Tape (Radar PR-1 already required this for nominations) + revisions coverage. Pre-2026 stays UNRESOLVED. |
| Q7 | What share of DRL “idiosyncratic” shocks are actually `peer_basis=market`? | Latest snapshot: market **47.21%**, sector **52.79%**. | Already disclosed; any study must stratify on `peer_basis`. |
| Q8 | Why is context-vector `factor__absent` **100%** on 2026-08-17? | Slot exists; producer not populating. | Open `engine/us_context_vector.py` join — **out of scope** unless a later wave is commissioned. Do not invent a parallel factor residual. |
| Q9 | Where does current Prophet **entry** state live if `prophet_entry` / `prophet_signal` are empty on the latest stamp? | Lane/buyable/eligible **are** populated (65 buy / 127 buyable). Entry columns empty. Track C points at `site/stockdata/<T>.json` + `engine/entry_signal.py`. | One dossier peek + entry_signal schema. Not done this session → **UNKNOWN**. |
| Q10 | When will Radar leave `WAITING_FOR_LIVE_SOURCE`? | `data/entry_radar/ledger_state.json` 2026-08-18: 0 forward rows; W4 STAGED NOT ARMED. | Operator `ENTRY_RADAR_LIVE_ENABLE` + live source. Not this lane. |

---

## 3. Casebook honesty

| # | Question | Bound |
|---|---|---|
| Q11 | For same-t0 pairs where both are winners (AVGO/APH, VST/TLN/NRG, PDD years, MP years), who dominated? | **UNKNOWN** until someone computes PIT excess on a frozen pair list. Do not pick from memory. |
| Q12 | Is the 42-row peer book a representative same-theme panel? | No. It is winner-library convenience sampling. Mechanical census is blow_off-dominated 5.5:1. |
| Q13 | Did CCJ 2025 dominate uranium peers or only SPY? | Case itself: beat SPY, **lagged XME full-year**. URA/URNM absent from `data/yahoo/`. |
| Q14 | Which failed_breakaways are capital-supply **as of t0** vs as of later dilution? | Cases APLD/NBIS/LUNR/CLSK/CIFR state financing at t0. Not joined to `dilution_events.parquet`. |

---

## 4. Rights / PIT / ethics

| # | Question | Standing answer |
|---|---|---|
| Q15 | May we backfill options or revisions before store birth? | **No.** Disclosed-null eras (`us_prophet_rank/disclosed_gaps.json` analog). |
| Q16 | May 13F explain a 21d t0 move? | **No** unless the filing was already public (ReportPeriod+45d ≤ t0). |
| Q17 | May GEX be treated as observed dealer demand? | **No.** Modeled. Signed flow forbidden without NBBO. |
| Q18 | May ownership be a positive Opportunity input? | **No.** WA-R2 / NEXTL-U13. Crowding hazard only. |

---

## 5. Questions explicitly **not** opened

- What weights should an Opportunity Score use? **Not asked. Do not answer.**  
- Should Radar W7 start? **No.** `WS:LIVE-ENTRY-RADAR` next_action: do not start W7.  
- Should residual_alpha be promoted? **No.** Context only; modern-era FDR/DSR not cleared.  
- Should DRL become an entry system? **No.** Charter refusal + `DNR:KILL-LIQUIDITY-SHOCK-REVERSAL-CLASSIFIER`.  
- Should we rebuild a sponsorship or regime scorecard? **No.** `DNR:KILL-SPONSORSHIP-SCORE`, `DNR:KILL-REGIME-SCORECARD`.

---

## 6. Cheapest next measurements (if a later wave is commissioned)

1. Join `data/revisions/history.parquet` to MRNA/HIMS 2026 dates (I3 existence proof).  
2. Stratify DRL open events by `peer_basis` × `edgar_covered` (Cell A–E counts).  
3. Compute PIT excess for the **same-t0 winner-winner** pairs (PR-02, PR-13, PR-17) and leave the rest UNKNOWN.  
4. Peek one `site/stockdata/<T>.json` for `entry_signal` to close Q9.  
5. Do **not** start a score search on W5 Radar tables (already contaminated for RP1 weights).
