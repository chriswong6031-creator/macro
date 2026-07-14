# Postmortem — 2026-07-14 rotation miss (US surfaces)

**Status:** adjudicated postmortem, evidence-verified (5-lane census + main-loop code verification, 2026-07-14).
**Companion:** `research/MEGACAP_LEADERSHIP_COHERENCE_MASTERPLAN_BY_FABLE.md` (the upgrade program this postmortem charters).
**Scope:** what the US-facing surfaces said as of the 2026-07-13 nightly, what actually happened on 2026-07-14, which mechanisms produced the miss, and what is structural vs. incidental.

---

## 1. The day, verified

Web-verified 2026-07-14 US close (local stores end 07-13):

| Asset | 07-14 move | Note |
|---|---|---|
| GS | **+7.70%** | Q2 beat: profit +80% YoY, record $7.42B equities trading |
| SMH (semis) | **+3.18%** | semis led tech |
| NVDA | **~+2.0%** close-to-close | intraday high larger; operator observed +4% |
| XLV (health) | **−1.88%** | BIIB −8.6%, SYK −6.5%, ISRG −6.2% |
| XLU (utilities) | **+0.13%** | flat, not down, at the close |
| SPY / Nasdaq | −0.8% / −1.6% | index drag incl. IBM −25.1% (earnings miss) |

The operator's account is directionally right where it matters — banks and semis ripped, healthcare was destroyed, and no actionable surface anticipated either side — with two numeric nuances: NVDA's close was ~+2% (not +4%), and XLU closed flat. Neither nuance changes the verdict below.

## 2. What the system actually said on 07-13 — the contradiction matrix

The single most important finding: **the system did not have one opinion. It had four or five, they disagreed, and the most actionable surface was the most wrong.**

### Mag 7 / NVDA (same night, same asset):

| Organ | Verdict as of 07-13 | Where it renders |
|---|---|---|
| `engine/mag7_regime.py` (M7C) | `turning_up`, "Get ready", generals AAPL/META/NVDA, run day 8, cw r10 **+7.65%** (was **+9.9%** on 07-10, its first-ever ledger row) | one panel on us_stocks.html only (`dashboard.html.j2:1738` gates on `mode=='stocks'`); never on the macro page |
| theme scorer (baskets page) | EMERGING / **ENTER**, score 52, rank 21/46 — but demoted out of ACT-NOW buy because `clean_entry=False` | baskets.html, sorted rank 2-of-4 in its category by trailing 20d rel (+1.67%) |
| `basket_confluence` | class=**headwind**, entry reason **"flat: sell"**, buyable=False | subsectors surface |
| allocation (`narrative_rotation.py`) | score −0.06, rank 17/46, **not held** | allocation.html |
| standout stocks | NVDA **absent** (below 50dma → no bottoming or continuation lane can hold it) | us_stocks.html |

The cohort organ that was built precisely for this (M7C, merged 07-11) fired `turning_up` on its very first run, three sessions before the move, with NVDA named a general. Its output was buried in one soft panel and contradicted by three sibling organs on other pages.

### Healthcare (same night, same sector):

| Organ | Verdict as of 07-13 |
|---|---|
| `sector_central` | XLV **Reduce, 24/100** — the lowest tier band (XLRE at 16 scored lower) — driven by cycle position (Peak, pos 81.6); its momentum confirmer was actually *positive* (RS #3, "leading") |
| baskets ACT-NOW | **buy list = [insurance, big_pharma, us_sector_utilities]** — clean BUY on big_pharma and insurance; us_sector_health ACCUMULATE (add-on-pullback); managed_care HOLD/DOMINANT |
| allocation | managed_care held at 25% weight (rank 6, 12m ret +60.7%, gate wide open) |
| standouts | 3 healthcare names in the Bottoming lane (PAHC 87, ZTS 71, AHCO 61) with honest "Sector: Reduce" chips |
| `basket_confluence` | managed-care "flat: sell", us-sector-health "flat: cut" |

So the operator's complaint "it told everyone to keep buying healthcare" is **confirmed for the surfaces a user acts on** (baskets ACT-NOW, allocation book) even though the sector conviction engine had already called Reduce. The glance tier shipped the buy and the reduce simultaneously, on different pages, with no reconciliation and no disclosure of the disagreement.

### Financials:

- Action board: XLF **HALF SIZE** — "clean entry · today" (`engine/cycles.py:726-739`: daily cycle turn in, price above 10-day MA, weekly MACD not yet confirming → half-conviction entry).
- `sector_central`: **Cautious 36/100** — *because* XLF was at Peak position (pos=70.2) — while it sat **0.1% from its 52-week high, RS rank #2, r20 +5.5% vs SPY +1.3%** (engine's 20-point window; +6.9%/+1.8% over 20 full bars).
- Standouts continuation lane did carry MS and EWBC (banks).

Note the irony: HALF SIZE was actually a *correct entry signal the day before GS +7.7%*. The failure is not that it fired — it's that the system's strongest conviction language is structurally unavailable for a sector at highs (see §4.3), and the entry chip didn't know GS reported the next morning (see §4.5).

### Tech: XLK chip = **AVOID / downtrend** (gate override), stance COUNTERTREND ONLY — the night before semis +3.2%.

### Utilities: sector_central **Accumulate 72/100** (Trough/bottoming logic, RS rank #11 = worst) and in the ACT-NOW buy list. XLU closed +0.13% — not punished, but this is the buy-the-laggard bias in its purest form.

## 3. What was knowable, and when

From local stores alone (no hindsight):

- **Healthcare rollover was visible from 07-07/07-08.** XLV MACD histogram peaked 07-07 at 0.947 and faded monotonically to 0.149 by 07-13; MA10 slope decayed 1.44 → 0.11; JNJ histogram 2.47 → 0.38 off its 07-07 high. The operator's claim that bearish momentum was printed "multiple days ago" is **confirmed**. Critically, **no organ acted on that fade**: `sector_central` was at Reduce for cycle-*position* reasons (Peak) while its momentum confirmer still read "leading"; and the dedicated momentum-fade texture (`rollover_risk`) printed **risk 0.0, band "low"** on big_pharma and insurance that same night. The basket surfaces stayed bullish because their rulers are trailing 20d/60d returns and a DOMINANT label — still glowing (+3.0% to +9.6% 20d rel) at the exact moment momentum broke.
- **The Mag7 run was visible from 07-10 at the latest** (M7C first row: cw r10 +9.9%, turning_up, NVDA a general). NVDA itself closed 07-13 *below its 50dma*, −13.6% off its May high, after a −3.5% down day — on trailing-return rulers it was mid-pullback inside a fresh run, which is exactly the state the ACT-NOW "clean entry" machinery claims to want and still didn't surface.
- **Bank strength was visible**: XLF r20 +5.5% vs SPY, 3 up days into 07-13, MACD histogram positive. GS's +7.7% specifically was an **earnings catalyst** — not knowable from price, but the *date* was knowable: an earnings layer exists (`engine/earnings_blackout.py`, `data/earnings/`) and is even wired into the standouts board as a per-name fresh-buy veto (`build_stock_library.py` W1.5, `earnings_blackout_note`) — but its store was **stale on this run** (`store_stale: true, count: 0`), so even that veto was inert. No sector/basket/action-board entry surface displays report dates at all.

## 4. Root causes (ranked, each code-verified)

**4.1 No coherence layer (the #1 failure).** Five independent organs emit stances per asset with no arbitration and no disagreement disclosure. `engine/theme_scoring.py` contains zero references to sector conviction — the ACT-NOW builder (`theme_scoring.py:1039-1071`) is *incapable* of knowing XLV is at Reduce when it prints big_pharma as a clean BUY. The comment says "Display-only: a focus list, not an order," but the glance tier IS the product; users read it as the house view. The house had no view — it had five.

**4.2 The actionable surfaces run on the laggiest clocks.** ACT-NOW = theme reco (trailing 5/20/60d blends + DOMINANT labels) × clean-entry texture (pullback shape). Allocation = 63/126/252d momentum ensemble + binary gate (above 200dma AND 12m>0 — managed_care needed **−37.8%** cumulative to exit). Meanwhile every fast organ that saw the turn — M7C, Leader Radar lifecycle states, IHM hybrid momentum, rotation_events, Tier-F — is display-dark, buried on one page, or feeds nothing actionable. The system's reflexes exist; they're not connected to its hands.

**4.3 The cycle-position ontology structurally fades leaders and buys laggards.** `sector_central._state_score` scores setup as `(50 − pos)/50`: position 81.6 (strength) → −0.63; position 20.8 (weakness) → +0.58, plus phase_dir bonuses for Trough. This is why XLF at all-time highs = Cautious 36 while XLU at RS #11 = Accumulate 72. The repo's own keystone evidence (W0.4, 8,344 PIT stamps: cycle position predicts nothing at any decile/horizon; FRESH BUY = worst ladder state) already refutes position-as-signal for entries — yet position still drives the sector conviction score and the glance-tier chips. A megacap-led tape is the worst case for this ontology: leaders live at "Peak" permanently. And note the stopped-clock character of its one good call: XLV's Reduce came from the same fade-everything-at-Peak bias that was simultaneously wrong on XLF and XLK — its momentum confirmer still read "leading" on XLV as healthcare broke.

**4.3b The shipped momentum-fade texture missed the break — and flagged the wrong side.** `rollover_risk` (engine/basket_score.py:176-210, surfaced as the baskets-page "rollover watch") printed big_pharma **0.0/low** and insurance **0.0/low** on 07-13, while flagging memory_storage / ai_semiconductors / ai_infra / semicap as **high** rollover risk — the complex that rallied +3.2% the next session. Its legs are extension/deceleration-centric (RS percentile, accel decay, below-50d), so a *non-extended* sector rolling off a top scores ~0. The MACD-histogram fade that was unambiguous on XLV from 07-07 is not one of its legs. It also feeds only a separate watch list — even when it fires, nothing demotes an ACT-NOW buy.

**4.4 Megacap-narrowness blindness.** The theme scorer's impulse leg scored mag7 −0.516 because GOOGL/TSLA fell >3% while NVDA/META led — i.e., it punished the *narrowness signature that defines megacap suction rallies* (operator's thesis: NVDA's monster runs drain the rest of the tape, including the rest of Mag7). Breadth leg likewise (2/7 above 50dma = −0.047). Nothing in the stack tracks megacap concentration as a first-class object: no NVDA-share-of-index-mktcap/volume series, no cap-weighted-vs-equal-weighted suction ladder (`absorption=0.37` is all-basket PC1 variance, a different animal). M7C computes cw vs ew composites internally but nothing consumes the spread.

**4.5 Event awareness exists but was stale-inert and disclosure-free.** GS reported 07-14. `earnings_blackout` is wired into the standouts board as a suppress-only hygiene veto (don't fresh-buy a name right before its own print), but on this run the store was stale (`store_stale: true, count: 0`) so even that was inert — and no surface anywhere *displays* "reports in N days" as context. The theme ACT-NOW, allocation book, and sector action board never consult earnings at all.

**4.6 The good organs are newborn and quarantined.** M7C: 2 ledger rows. Leader Radar: engine + stores shipped, feeds nothing. IHM: display-dark. RC-R9 S1/S2 (the *only* legal path for rotation events to change sector stances) — not yet built. Promotion discipline is house law and correct; the failure is that the display tier never aggregated what already exists at display tier.

## 5. Honest scoring of the operator's account

| Claim | Verdict |
|---|---|
| "Told everyone to continue buying healthcare/pharma" | **CONFIRMED** on baskets ACT-NOW (big_pharma+insurance clean BUYs) and allocation book; sector engine simultaneously said Reduce — incoherence, not unanimity |
| "Didn't surface NVDA / megacap leadership at all" | **CONFIRMED** for every actionable surface; M7C panel knew but is one soft buried panel |
| "Mag7 basket should be #1, shows +1.7% 20d" | **CONFIRMED** mechanism: baskets sort on trailing 20d EW rel — structurally cannot rank a fresh cap-weighted run first |
| "Financials HALF SIZE is crazy" | **PARTLY** — it was a correct-direction entry signal, but conviction language is capped for leaders-at-highs by construction, and no surface flagged GS earnings |
| "Utilities down and recommended" | Recommendation confirmed; XLU actually closed +0.13% |
| "NVDA +4%, up multiple sessions into 07-14" | Close was ~+2.0%; the multi-session run was real but peaked 07-10 and pulled back −3.5% on 07-13 — the *system* still failed to show any of it |
| "Failure to look backward" | **CONFIRMED** — XLV momentum break visible from 07-07, basket surfaces still glowing on 20d trailing |

## 6. What this does NOT conclude

- It does not conclude the cycle engines are worthless — sector_central's Reduce on XLV was the single best call in the building. The indictment is the *absence of reconciliation* and the *ruler choice on actionable surfaces*.
- It does not conclude we should chase momentum with authority-tier signals tomorrow. House epistemics stand: display/context first, gauntlet at promotion. The remediation program (see masterplan) ships display-tier immediately and pre-registers the promotion studies.
- It does not re-open killed constructions: rotation×cycle-position entry confluence (DON'T-TEST), RS-dispersion gates (zero-sum kill), timing-into-rank blending (Phase-0 cosmetic) all stay dead. The fix is coherence + megacap tracking + faster de-escalation, none of which touch those graves.

## 7. Remediation

Chartered as the **Megacap & Leadership Coherence program (MLC)** — see `research/MEGACAP_LEADERSHIP_COHERENCE_MASTERPLAN_BY_FABLE.md`. One-line summary of waves: W1 Leadership Board (megacaps as individual first-class objects + cohort, macro-page visibility); W2 coherence/arbitration layer (disagreement disclosure + sector-conviction demotion of ACT-NOW buys); W3 megacap suction organ + field guide (concentration shares, cw/ew ladder, PIT accrual); W4 momentum-fade de-escalation textures (the 07-07 XLV detector); W5 earnings-proximity wiring on entry surfaces; W6 pre-registered promotion studies.
