# Thematic Foresight Desk

*Anticipate themes "at the precipice of induction," convert them to investable calls
BEFORE estimate revisions explode, and defer the entry to a dislocation. Worked case
throughout: the June-2024 13D HBM/DRAM call.*

## 0. The thesis as an engineering contract

The 13D HBM call (released 2024-06, free sample `TBR_USVI_Automation.pdf`) is the north
star because it isolates exactly what this desk must do that the dashboard does not:

- It was **right and ~9 months early**, built on **physical-supply + concentration +
  underpricing** reasoning with **zero estimate-revision numbers** ("HBM chips are sold
  out for the next two years… manufacturers are investing to increase capacity"; supply
  ~100% in SK Hynix/Samsung/Micron; "HBM production may reduce DRAM availability"; the
  market had "largely eclipsed its appeal" by chasing GPUs).
- The names rallied summer-2024, **faded into Q1-2025**, and the **best entry was the
  early-2025 tariff-tantrum macro flush** — not the day estimates finally ticked up.

Three commitments follow:

**(1) Reconcile the lagging-revision objection — do not dodge it.** Two distinct games,
run in order: *front-running the revision* = nowcast the fundamental (bottleneck /
pricing / capex) the analyst will eventually capitulate to — the only genuinely LEADING
signal, the **entry thesis**; *trading the revision itself* = revision-breadth momentum
(Mill Street: ~83% one-month persistence, IC≈0.23, top-vs-bottom decile 15.6% vs 8.0%) —
COINCIDENT-to-confirmation, the **runway / exit-clock gauge**, never the entry. So:
**bottleneck/pricing/capex LEAD revisions; revision-breadth broadening CONFIRMS; entry is
timed by the existing dislocation/anticipation/drawdown layer.**

**(2) Two separable jobs, never conflated.** Job A = *detect* a real, durable theme early
(prove durability via a physical bottleneck). Job B = *time entry* to a dislocation.
Detection tells you **what** and **that it's durable**; it does NOT tell you **when to pay
up**. `engine/narrative_emergence.py` already states the hard truth — detection is noisy
(~half of flags real) and the early-entry return edge is ~0 and negatively skewed — so
detection stays display-only and entry defers to the validated overlay.

**(3) Code-enforced honesty everywhere.** Every new engine is display-only first, returns
`None`/`"unknown"` on shortfall (never raises), surfaces components+weights in its JSON,
and writes an append-only forward-grading ledger `data/<engine>/log.jsonl` graded forward.
**No point-dates** (turn-detection is measured coincident — band hazard reads). Text-only
never promotes a theme above a capped score without a physical correlate.

## 1. The cascade — lead-time tiers → engines

| Tier | Lead | Answers | Engine | New/Reuse |
|---|---|---|---|---|
| **T0** emergence | 1–3q | Is a new theme *accelerating* across independent corpora? | `narrative_emergence`, `theme_discovery`, `emergence_alerts`; NEW `theme_corpus` | reuse + Ph3 |
| **T1** physical bottleneck | 3–9mo | Is the industry physically full (cap-U↑, inv↓, lead-times↑, PPI↑)? | NEW `bottleneck` (+ `edgar_fts` collector, FRED series) | **Ph0** |
| **T2** customer-capex / demand | 1–4q | Who forces the demand (hyperscaler capex, RPO>rev)? | `demand_chain`/`demand_ledger` (exist), NEW `demand_capex` | reuse + Ph1 |
| **T3** guidance-gap | days–1q | Has management pre-signaled above consensus? | NEW `guidance_gap` (paid-limited skeleton) | Ph2 |
| **T4** revision-breadth broadening | coincident | Has the revision wave started, how wide/persistent? | NEW `theme_revisions` (reuse `data/revisions/*`, `baskets`) | **Ph0** |
| **T5** tape / re-rating | coincident | Is price re-rating ahead of estimates? | `basket_index`, `basket_mtf`, `theme_extension` | reuse |
| **entry overlay** | event | Clean (non-extended) entry NOW, ideally on a flush? | `dislocation`, `anticipation`, `drawdown` | reuse (Ph1) |
| **exit-risk** | 2–6q fwd | Is supply responding (glut forming)? | NEW `glut_watch` (inverts `bottleneck`) | Ph4 |

**Composite (`foresight_cascade`, finalized Ph2):** a per-theme **stage** label, not one number —
```
PRECIPICE  : T1 bottleneck TIGHT + T4 breadth FLAT/low      -> thesis; watchlist; size small   (= June-2024 HBM)
BROADENING : T1 TIGHT + T4 breadth RISING + dispersion narrowing -> revision wave underway; runway confirmed
RE-RATING  : T5 tape extended + T4 breadth high             -> late; await dislocation, do not chase
GLUT-RISK  : exit-risk firing (capacity response)           -> trim / exit clock
```
The HBM lesson made mechanical: PRECIPICE = the desk flags it, sizes small, holds on a
graded watchlist; BROADENING/RE-RATING through H2-2024→Q1-2025; the **dislocation overlay**
fires the actual buy on the early-2025 tariff flush.

## 2. Free-data honesty table

| Signal | Free & sufficient | Paid edge (skeleton only) |
|---|---|---|
| Capacity / inventory / backlog / PPI | **Yes** — FRED `CAPUTLG3344S`, `ISRATIO`, `AMTMUO`, `PCU334413334413`, regional-Fed delivery-time/prices-received | — |
| "Sold-out" / lead-time language | **Yes** — SEC EDGAR full-text search (keyless, 2001→) | earnings-call transcripts (richer) |
| Hyperscaler capex / RPO | **Yes** — SEC XBRL frames + `edgar_rpo` | sell-side capex models |
| DRAM/NAND/HBM spot | proxy-only (PPI direction) | TrendForce contract (Gold+), HBM history |
| Revision breadth | **partial** — yfinance snapshot; `data/revisions/history.parquet` accrues PIT forward | I/B/E/S, Visible Alpha deep history |
| Guidance-gap | weak — Estimize whisper, 8-K pre-announce scrape | Visible Alpha guidance DB |

**Punchline: FRED PPI/capacity + EDGAR language + EDGAR capex/RPO get the DRAM trade ~80%
of the way on free data.** Spot/contract memory prices, deep revision history and clean
guidance feeds are the paid edge — built as skeletons that light up if a key arrives.

## 3. Phases

- **Phase 0 (this PR):** `engine/theme_revisions.py` (T4 broadening, pure reuse of
  `data/revisions/*` + `config themes`) + `engine/bottleneck.py` (T1, FRED capacity/inv/
  orders/PPI + keyless `collectors/edgar_fts.py` language) + `engine/foresight_cascade.py`
  v1 (PRECIPICE/BROADENING stage from T1×T4). The two legs that caught DRAM. Display-only,
  forward-graded. Surfaced on the theme add-ons panel.
- **Phase 1:** `engine/demand_capex.py` (T2: hyperscaler capex QoQ-accel + RPO−rev via
  `edgar_facts`/`edgar_rpo`) + entry-overlay wiring (cascade consumes `dislocation`).
- **Phase 2:** `engine/guidance_gap.py` (T3 partial) + cascade v2 (all tiers, underpricing
  = inverse-attention axis) + `site/foresight.html` desk page (+ Research-nav link).
- **Phase 3:** `engine/theme_corpus.py` — Word2Vec vocab discovery → FinBERT sentence-sign
  → mention-share + acceleration + multi-corpus breadth (Fed FEDS-Note SCB method, Soto
  2023), validated vs ISM supplier-deliveries. T0 becomes genuinely leading.
- **Phase 4:** `engine/glut_watch.py` (exit) + `collectors/patents.py` (USPTO PatentsView
  CPC-class accel, 18–36mo lead) + `engine/scurve.py` (Gompertz inflection, banded).
- **Phase 5 (god-tier):** `engine/foresight_score.py` 7-axis investability rubric
  (magnitude .15 / acceleration .20 / bottleneck .20 / pricing-power .15 /
  underpricing-inverse-attention .15 / purity .08 / timing-gate .07; weights tuned ONLY
  via forward-grading ledgers) + auto-theme-discovery (promote novel-vocabulary
  first-mentions to candidate themes not yet in `membership.json`) + closed learning loop
  (grader recalibrates thresholds quarterly; track record public + immutable).

## 4. Verified data sources (live-tested)

FRED (keyless `fredgraph.csv?id=`): `CAPUTLG3344S` (semis cap-U), `CAPUTLG334S`,
`CAPUTLG331S` (primary metal), `CAPUTLG325SQ` (chem, quarterly), `CAPUTLG211S` (oil&gas),
`IPG3344S`/`CAPG3344S`, `ISRATIO`+`MNFCTRIRSA` (inv/sales), `AMTMUO` (unfilled orders),
`AMTMVS` (shipments), `DGORDER`/`NEWORDER` (orders/capex-proxy), `PCU334413334413` (semi
PPI), `PCU331110331110` (steel PPI), `DTCISA156MSFRBPHI`/`DTMUAMFRBDAL` (delivery times),
`PFGIUAMFRBDAL` (prices-received). **Dead IDs:** `AMTUO`→`AMTMUO`, `AMDMNO`→`DGORDER`,
`CAPUTLG2111S`→`CAPUTLG211S`, `BACKLOG` (not a series).

EDGAR full-text (keyless, UA header, 10 req/s): `https://efts.sec.gov/LATEST/search-index?q="PHRASE"&forms=10-K,10-Q,8-K`.
Phrase dictionary: `"sold out"`, `"capacity constrained"`, `"supply constrained"`,
`"on allocation"`, `"longer lead times"`, `"extended lead times"`, `"record backlog"`,
`"unable to meet demand"`, `"demand exceeds"`, `"tight supply"`. (Live: "capacity
constrained" 731 10-K hits; "sold out" 19 10-Q/2024.)

EDGAR XBRL capex (keyless): frames `PaymentsToAcquirePropertyPlantAndEquipment`; CIKs
MSFT 789019, Alphabet 1652044, Amazon 1018724, Meta 1326801, NVIDIA 1045810.

**Timing caveat (worked case):** this engine is a **watchlist-builder / thesis-confirmer,
NOT an entry-timer** — 13D was right and ~9mo early; defer the buy to the dislocation
overlay rather than chasing the first rally.
