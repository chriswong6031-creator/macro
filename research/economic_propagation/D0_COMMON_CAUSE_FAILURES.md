# D0 — Common-cause failures

**Purpose:** catalog ways a “transfer” read is actually a shared factor, a shared basket, or an instrument verdict. These are first-class cases, not footnotes.  
**SHA:** `3d12412e561ef77c0a9618c9d9b18871d7344209`.

Commission class: **false transfer caused by common factor**. Sister class: **relationship existed but company-specific offset dominated** (kept here when the offset is the lesson).

---

## 1. Failure modes

| Mode | What you thought | What it actually was | House object that invites it |
|---|---|---|---|
| **M1 Co-membership** | A leads B | A and B are the same index/basket | SMH/SOXX/TSM; GMI `MEMBER_OF`; GR baskets |
| **M2 Residual beta** | Economic hop | shared duration / risk-on / USD | C1 gold→XGD NO-GO; luxury→FXI lag-0 |
| **M3 Spender-pool** | capex raise helps suppliers | the spenders de-rate together | GOOGL 2026-07-22; Demand Desk spender list |
| **M4 Theme vocabulary** | same theme ⇒ Graph 1 | Graph 2 only | GMI `EXPRESSES`; 商品联动 display |
| **M5 Agreement-without-role** | 8-K ⇒ customer | undirected form | GR `supply_agreement` |
| **M6 Instrument-as-world** | chain `failed` ⇒ thesis false | window miss | TXI gold 2026-08 |
| **M7 Contagion-as-customer** | Korea → Mag7 is a supplier hop | residual-market hop, sometimes narrow | CSP 2026-07-16 |
| **M8 Protocol-as-peer** | same indication ⇒ commercial peer | protocol comparability | Bio `trial_peer_set.v1` |
| **M9 Ownership-as-customer** | agency HHI ⇒ customer graph | awarding-agency mix | GovRev metrics |
| **M10 Narrative-without-contract** | LOI / partner headline ⇒ BINDING | unsigned / ATM / own-print miss | APLD, CRDO |
| **M11 Substitution** | boom node stays BINDING | customers left | US Silica Northern White |
| **M12 Attention common factor** | two names move on the same war/AI word | geography/product mismatch | D0R E16 Taiwan Strait vs US ammo; E22 Hamas mixed US |

---

## 2. Documented instances

### F01 — TSM / ASML / SMH co-membership (M1)

`reports/intl-semi-readthrough-phase0.md`: lag-0 HAC t +15.9, corr +0.82; lag-1 t −1.67; **kill=True**.

This is the cleanest in-repo proof that contemporaneous residual movement is not a lead and is not Graph 1. Any EP join that admits “historical transmission neighbor” from lag-0 correlation repeats this failure.

### F02 — Gold → XGD C1 NO-GO vs live gold tape (M2)

`reports/c1-commodity-sector-phase0.md`: gold→`XGD.TO` −0.04%, sign-flip. Exploratory bear flip: gold down, XGD **+1.85%**.

Same week the estate has a real gold/miners episode (P01) and a 2016 GDX episode (P12). The construction (4w slope_z excess) is the crux. **Do not merge these into “gold transmits.”**

### F03 — Mag7 sympathy 0.93× (M1 / M3)

First live GR sympathy: regional_banks 1.23× (n=102), mag7 **0.93×**. Mega-cap prints do **not** lift non-reporters in that basket. Using “Mag7” as a read-through peer set is a common-factor basket, not a mechanism.

### F04 — GOOGL 2026-07-22 capex bind (M3)

Capex guide up, spenders down after hours, hardware **not** up. Cooper–Gulen–Schill is already cited in-repo: spender capex can be a negative for the spender and still not a supplier gift that day. Demand Desk `ai_datacenter` spenders are exactly this pool. Scoring theses off that list without an incorporation state repeats F04.

### F05 — TSMC 2026-07 print, no follow (M2 / M3)

Record profit + capex raise, semis kept falling. “Excellent news” is not Graph 3 incorporation and is not Graph 1 transfer.

### F06 — 2026-07-16 Korea unwind as “index crash” (M7)

US session: only Tech/Comms down; 358/503 SPX names green. The hop Korea→memory→tech is dated. The hop “therefore de-risk the index” is a common-factor over-read. CSP’s own postmortem already says this.

### F07 — TXI gold chain FAILED while gold passed (M6)

`research/CASE_STUDY_GOLD_REAL_RATE_PEAK_2026_08.md`. 63d falsifier red; 22d Δ was already decelerating inside the receipts; miners were already long in scored organs. Teaching case for “instrument verdict ≠ market verdict,” which EP must inherit if it ever grades hops.

### F08 — CRDO after NVDA 2023-05-24 (M10)

Same source event that immediately incorporated in VRT. CRDO printed −40.9% sequential and lagged SOXX. Relationship-shaped narrative (AEC/interconnect) with a company-specific offset. Graph 1/2 similarity without transfer.

### F09 — APLD unsigned LOI (M10)

Together AI / Blackwell / 400MW language. Lease unsigned. ATM broke the tape. Binding was asserted from narrative.

### F10 — US Silica Northern White (M11)

Customers left for in-basin sand. Impairments $266m then $364m. The economic relationship **existed** and then the node went EXCESS_CAPACITY. Transfer in the wrong direction.

### F11 — Healthcare XLV → CN pharma NO-GO (M2 / M8)

`reports/c-hc-readthrough-phase0.md`: XLV mom → Shenwan pharma t −0.48 while the semis→CPO control stayed live. Clinical/theme similarity does not travel. This is why Bio `trial_peer_set` must stay protocol comparison.

### F12 — Luxury → FXI contemporaneous only (M2)

Thesis directionally pretty, temporally wrong. Lag-1 wrong-signed. Common factor at lag 0.

### F13 — CN block-trade peers null (M2)

Informed-holder pessimism on blocked names does not spread to non-blocked peers. A “peer set” generated from residual or theme membership would have predicted a hop that the tape refused.

### F14 — 2024+ only China AI legs (M1 / M4)

Storage / adv_pkg / liquid_cool leads vs US semis mom weaken or die pre-2024. The AI-era common factor is doing the work. S08 in the casebook.

### F15 — Defense “war beta” (M12)

D0R academic review + E16/E21/E22: conflict is often vol/attention; Wagner coup reversed the bid next session; Taiwan Strait is not a US munitions print; Hamas mixed for US primes. A Graph-3 defense residual is not Graph-1 contractor exposure.

### F16 — IRDM P00032 non-material (M9 cousin)

Live GovRev golden row: $18.4M FUNDING ONLY, late `known_at`. Relationship and award exist. No material transfer. Teaching case that Graph 1 presence is not a hop.

---

## 3. Generator hygiene (how EP must not repeat these)

From architecture §4.3, every target must carry the **admitting generator**. Recommended refusals:

| Generator | Refuse when |
|---|---|
| residual / lag-0 corr | always, as Graph 1; allowed only as Graph 3 incorporation context (F01) |
| theme / basket membership | used alone (F03, F14) |
| spender list | no incorporation state, no company_specificity (F04) |
| 8-K agreement | role not disclosed (M5) |
| NCT / indication | no reviewed commercial relationship (F11, M8) |
| TXI / CSP state | attached to a ticker as if it were a supplier hop (F06, F07) |
| award / ownership | dollars immaterial vs mkt cap (F16) |

Alternative explanations already required on `earnings_readthrough_hypothesis/v1`: common factor, company-specific offset, already incorporated, insufficient coverage.

---

## 4. What this file does **not** claim

It does not claim transfers are rare. VRT, VST/TLN, LITE/FN, SMMT-as-licensee, C1 oil→XEG at 4–8w are in the positive book.

It claims the **failure modes are already measured in this estate**, so a new graph that emits a single `RELATED` or `co_movement` `SUPPLIES` edge would be rebuilding the failures as data.
