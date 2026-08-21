# IMCE-HB-0 — Structural-break ledger

**Wave:** A3 / IMCE-HB-0. Records-only.
**Authority:** freeze §4–6 structural-break law — epochs frozen **before any outcome inspection**
(strengthened from "before fitting" [G8-M2]); no cross-epoch transfer without a registered test.
**Evidence:** `evidence/L6_structural_breaks.md` — 28 dated ledger rows, a 7-row common-break table,
and a 13-item gaps table, built from EDGAR 8-Ks, 10-K business-combination notes, and
significant-accounting-policy notes.

**Fence honoured — and it was checked, not assumed.** This ledger contains **no market-derived,
price-derived, or behavioural epoch**. The lane verified this by grep over its own output. Per the
freeze, a behavioural Stock Identity epoch may not be inferred here, and none is. Every row is a
documented business or reporting event with a filing citation. The three macro-regime windows in §3
are carried strictly as **documented filing context**, never as measured regimes.

---

## 1. The universal restatement rule — the ledger's most useful single finding

Across every transaction and every accounting-standard adoption in this cohort, the answer to
"was prior-period history restated?" is the **same**:

> **No. History is left on the old basis — by construction, not by choice.**

Two independent mechanisms produce it:

| Mechanism | Why it never restates | Verified on |
|---|---|---|
| **Acquisition-method (purchase) accounting** under ASC 805 | The acquirer's prior-period financials are never restated to include the target; results enter from the closing date forward. Pooling-of-interests is not permitted in this era. | PHM/Centex (FY2009 10-K Note 2, VERIFIED) |
| **Modified-retrospective / prospective adoption** of a new standard | A cumulative-effect catch-up entry is booked at the transition date instead of restating comparatives. | DHI ASC 606 (FY2019 10-K, +$27.1M cumulative-effect, prior periods **not** restated, VERIFIED) |

**Consequence for A4.** Every break date is a genuine discontinuity in the reported series — there is
no restated history hiding behind it that would smooth the join. A comparison spanning any break in §2
or §3 is comparing two different measurement bases and **requires a registered test**, not an
assumption of continuity.

### The one documented exception — and it proves the rule's shape

**PulteGroup, FY2009: the active-community-count criteria were modified, and prior periods WERE
recalculated to conform** (FY2009 10-K, VERIFIED).

This lands in the *same fiscal year* as the Centex merger, which was **not** restated. Two PHM events,
one year, opposite restatement treatments. They were nearly conflated in the evidence lane's first
draft and are carried as separate rows precisely because conflating them would corrupt the FY2009
boundary — which is also the block-1 → block-2 boundary (block list §D5).

**The generalizable pattern:** *transactions* never restate; *definitional changes* sometimes do. When
auditing a break, ask which kind it is.

---

## 2. Idiosyncratic breaks — one issuer, one date

These affect a single issuer's series. **A break test registered against one issuer's data may not
assume the same date applies to a peer.**

| Issuer | Event | Date | Restated? | What it changes |
|---|---|---|---|---|
| **PHM** | Centex merger | closed **2009-08-18** | **No** — prospective from close | Orders, backlog, community count, inventory all step-change. Centex contributed 435 active communities at 2009-12-31. |
| **PHM** | Active-community-count criteria reset | during **2009** | **YES — prior periods recalculated** | Community count only. The sole restating event in the ledger. |
| **LEN** | CalAtlantic acquisition | closed **2018-02-12** | **No** | Orders, backlog, community count. |
| **LEN** | WCI Communities acquisition | **2017-02-15** | Unclear — filing not opened | Florida/luxury operations enter. |
| **LEN** | **Millrose Properties spin-off** | **Feb 2025** | `missing` | **The largest single-metric break in the ledger — see §4.** |
| **DHI** | Forestar merger / consolidation | **2017-10-05** | **No** | Adds a reportable segment; lots owned/controlled mechanics change (§4). |
| **DHI** | Vidler Water acquisition | 2022 | Unclear | Water-asset segment. |
| **TOL** | Shapell acquisition | 2014 | **No** | California communities enter. |
| **TOL** | Coleman Homes | — | Company-flagged **backlog-composition adjustment** | Backlog composition — a "counts" break (§5). |
| **NVR** | FIN 46R / VIE note | FY2009–10 | Prospective | Consolidated inventory and lots (§3). |
| **KBH** | Geographic market exits | 2006–2011 era | Unclear | Community count, lots. |

---

## 3. Common breaks — all six issuers, same or clustered dates

A common break is a **different statistical problem** from an idiosyncratic one: it cannot be
differenced away against a peer, because every peer moves at once.

| Common break | Effective | What it changes fleet-wide | Tier |
|---|---|---|---|
| **ASU 2009-17 / ASC 810 VIE-consolidation rewrite** | FY2010 for all six | **What counts as consolidated "inventory" and "lots owned" versus merely controlled/optioned.** NVR's own filing frames it as entities that "would no longer be required to be consolidated." | VERIFIED (NVR); INFERENCE (other five) |
| **ASC 606 revenue recognition** | FY2018–19 | Home/land sale revenue recognition timing and presentation; contract-asset line. Modified retrospective — **no restatement**. | VERIFIED (DHI, LEN); INFERENCE (four) |
| **ASC 842 leases** | FY2019–20 | Balance-sheet ROU assets/liabilities. No material income-statement effect disclosed. | VERIFIED (DHI); INFERENCE (five) |
| **ASU 2016-13 CECL** | FY2020–21 | Captive mortgage subsidiaries' loan-loss allowance methodology. | VERIFIED (DHI); INFERENCE (five) |
| 2006–2011 housing bust | fiscal 2006–2011 | Impairments, goodwill write-offs, DTA valuation allowances, cancellation rates | **documented filing context only** |
| 2020 pandemic disruption | calendar 2020 | Cost inputs, process changes | **documented filing context only** |
| 2022–2023 rate shock | calendar 2022–2023 | Cancellation rates, spec inventory, incentive cost | **documented filing context only** |

**ASU 2009-17 (FY2010) is the most consequential row in this document.** It is a common break that
changes *what a metric counts* — specifically "inventory" and "lots owned", the two concepts most
central to a land-mechanism study — for **all six issuers simultaneously**, and it lands **inside
block 2** (`hb_gfc_recovery`, 2010–2013). Any lots-owned or inventory series crossing FY2010 crosses a
definitional change common to the whole cohort, with no restated history behind it and no peer to
difference against.

---

## 4. Two breaks that gut a specific metric

### 4.1 Lennar / Millrose (Feb 2025) — an 89% collapse in reported owned lots, with no business collapse

| LEN homesites | Before | After |
|---|---|---|
| **Owned** | 85,428 (18%) | **9,525 (2%)** |
| **Controlled** | 393,649 (82%) | **496,250 (98%)** |

Lennar's owned-homesite count fell by ~89% in one quarter. **Nothing about Lennar's access to land
changed** — the land moved to a spun-off entity and is optioned back. A lots-owned time series read
across Feb 2025 registers a catastrophic land liquidation that did not occur.

Restatement treatment: `missing` — not stated in the filings opened. The balance-sheet inventory-dollar
delta was not isolated. Both are named gaps.

### 4.2 D.R. Horton / Forestar — "controlled" means something different at DHI

DHI's controlled-lot bucket is populated partly by lots owned by **Forestar, DHI's own majority-owned,
consolidated subsidiary**, once under contract or right-of-first-offer to a DHI homebuilding division.
That is an intercompany relationship reported as "controlled".

Lennar's controlled bucket is populated by third-party options, unconsolidated-JV options, and — post
Feb 2025 — overwhelmingly by options back from a **former subsidiary**.

**A raw "% lots controlled" comparison between DHI and LEN conflates a consolidated-subsidiary contract
with a spun-off-affiliate option.** Same column name, different economic relationship, different
balance-sheet exposure. Preserved as a divergence, never normalized.

---

## 5. Which breaks change what is COUNTED (not merely the level)

Required by the commission as a named subset:

1. **ASU 2009-17 / ASC 810 VIE consolidation** — redefines consolidated inventory and lots owned. Common to all six.
2. **Every merger that adds a reportable segment or new-market communities** — DHI/Forestar, PHM/Centex, LEN/CalAtlantic.
3. **ASC 606** — redefines the revenue-recognition rule itself.
4. **Toll / Coleman** — company-flagged backlog-composition adjustment.
5. **Lennar / Millrose** — redefines which lots are "owned" versus "controlled" (§4.1).
6. **PulteGroup FY2009 community-count criteria reset** — redefines what an "active community" is, and is the one case where history moved to match.

Everything else in §2 changes levels. **The distinction is operational:** a level break may sometimes
be absorbed by a control; a counts break cannot, because the pre- and post-break series measure
different things.

---

## 6. Interaction with the block grid

Breaks do not respect block boundaries, and three collisions matter (block list §D5):

| Break | Date | Block position | Consequence |
|---|---|---|---|
| PHM / Centex | 2009-08 | **on the block 1 → 2 boundary** | PHM's block-1 and block-2 entities are not the same business. PHM does not cleanly span that boundary. |
| ASU 2009-17 | FY2010 | **inside block 2** | Fleet-wide counts break with no peer to difference against. |
| LEN / CalAtlantic | 2018-02 | inside block 3 | Mid-block composition change. |
| LEN / Millrose | 2025-02 | inside block 6 (OPEN) | Lots-owned series breaks inside the open era. |

**No epoch drawn here may be used to partition a recognition-outcome statistic without re-deriving it
on the recognition clock** [G8-M2]. These are operating-clock dates: the Centex close date is when the
business combined, not when the market could first see combined operating metrics — that is the
subsequent earnings release (fiscal/calendar map §4).

---

## 7. Evidence tiers and gaps

**Tiering is honest and uneven, and that is stated rather than smoothed.** Core events (DHI, LEN, NVR,
PHM primary sources) were verified by opening filings. Several fleet-wide accounting-standard rows are
VERIFIED for one or two issuers and **INFERENCE for the rest** — the inference is strong (a FASB
mandatory-adoption window applies to every SEC filer identically) but it is not the same as having
opened each issuer's adoption note.

**Eight rows carry unclear or unverified restatement treatment:** WCI, Millrose, Vidler, Coleman,
Sabal/Sharp/Thrive, Rialto sale, KB Home market exits, KB Home mortgage JV.

**Two named events could not be confirmed to exist as SEC-filed material events** under PHM's CIK —
*American West* and *John Wieland* acquisitions. They are marked `missing`, **not invented and not
silently dropped**. (John Wieland Homes was separately confirmed never to have been an SEC registrant
in its own right — survivorship census §2.)

Full 13-item gaps table: `evidence/L6_structural_breaks.md` Table 3.

---

## 8. Falsifiers

| # | Falsifier | Effect |
|---|---|---|
| F-1 | Any acquisition in §2 is found to have restated prior-period operating metrics. | §1's universal rule breaks; that break becomes joinable across. |
| F-2 | An issuer's ASC 606 or ASU 2009-17 adoption is found to use **full** retrospective adoption. | That issuer's comparatives *were* restated; §1 needs a per-issuer qualifier. |
| F-3 | Millrose restatement language is located. | §4.1's `missing` closes; the lots-owned break becomes bridgeable. |
| F-4 | A dated business or reporting event affecting a roster issuer is found that is absent from this ledger. | The ledger is incomplete; epochs must be re-frozen before any outcome inspection. |
| F-5 | Post-merger segment disclosures separately track legacy CalAtlantic/Centex operations. | Cross-break continuity becomes partially reconstructible. |
