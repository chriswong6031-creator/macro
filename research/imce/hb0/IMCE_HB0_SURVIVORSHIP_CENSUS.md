# IMCE-HB-0 — Survivorship census (mandatory deliverable)

**Wave:** A3 / IMCE-HB-0. Records-only.
**Authority:** merged freeze §7.2 condition **(5)** [G8-B4], mirrored into contract §2 Homebuilders:

> the roster is a 2026-survivor roster over a window containing the 2006–2011 sector mortality event…
> IMCE-HB-0 **must produce a named census of delisted/bankrupt/acquired homebuilders** for the study
> window with an explicit inclusion decision; until then, every homebuilder cell readout carries a
> mandatory survivorship-bias disclosure, and no cohort mean is quoted without it.

**This document discharges that obligation.** It does not lift the disclosure — see §6.
**Evidence:** `evidence/L1_cohort_survivorship.md` (research/sonnet, 2026-08-21; every CIK, form type
and date opened directly from EDGAR submissions JSON or company search). No price, return, deal-value
or market-cap figure appears in this census or its evidence packet.

---

## 1. Headline

| Question | Answer |
|---|---|
| Named mortality/absorption cases | **16** |
| …with EDGAR documents still available | **14** (2 were never SEC registrants at all) |
| Deaths strictly inside 2006–2011 | **7** |
| Full-window survivors **outside** the frozen six | **4 clean + 1 conditional** |
| Post-2011 entrants (structurally cannot span early blocks) | **7** |
| Is the survivorship correction constructible? | **Partially — and the part that fails is the part that matters most (§3)** |

---

## 2. The named mortality census

Terminal-event types: `CH11` Chapter 11 · `ACQ-PUB` acquired by a public issuer · `ACQ-PRIV` acquired
by a private buyer · `PRIV` recapitalized/taken private · `REORG` internal reorganization ·
`PIVOT` ceased to be a homebuilder.

| # | Entity | CIK | Terminal event | Date | Acquirer / outcome | EDGAR documents |
|---|---|---|---|---|---|---|
| 1 | TOUSA (Technical Olympic USA) | 1046578 | `CH11` → liquidated | 2008-01-29 | none | **Partial — no FY2008 10-K ever filed** |
| 2 | WCI Communities (2008 entity) | 1137778 | `CH11` → `PRIV` recap | 2008-08 | none | Partial, through FY2008 10-K/A |
| 3 | WCI, LLC (2013 re-listing) | 1574532 | `ACQ-PUB` | 2017-02-15 | **Lennar** | Through FY2015; no FY2016 10-K |
| 4 | Standard Pacific → CalAtlantic | 878560 | `ACQ-PUB` | 2018-02-12 | **Lennar** | **Clean, FY1996–FY2016, single CIK** |
| 5 | Ryland Group | 85974 | merged into #4 | 2015-10-01 | CalAtlantic | **Clean, FY1993–FY2014** |
| 6 | Orleans Homebuilders | 38570 | `CH11` → `PRIV` | 2010-03-01 | none | **Partial — no FY2009 10-K ever filed** |
| 7 | Dominion Homes | 917857 | delist 2008 → `PRIV` 2010 | 2008 / 2010 | none | **Partial — filings stop mid-2008; wind-down ~2013 unobservable** |
| 8 | Kimball Hill | 1357062 | `CH11` | 2008-04-23 | none | Narrow — debt-only filer, 2 10-Ks total |
| 9 | Avatar Holdings → AV Homes | 39677 | `ACQ-PUB` | 2018-10-02 | Taylor Morrison | **Clean, FY1993–FY2017** |
| 10 | William Lyon Homes | 1095996 | `PRIV` 2006 → relist ~2013 → `ACQ-PUB` | 2020-02-06 | Taylor Morrison | Two eras; 2006–~2012 private gap |
| 11 | Comstock Homebuilding | 1299969 | `PIVOT` (renamed, exited homebuilding) | 2012-06-26 | n/a — still files | Full, but not a homebuilder post-2012 |
| 12 | Levitt Corp → Woodbridge | 1218320 | homebuilding sub `CH11` | 2007-11-09 | none | **Parent only — see §4** |
| 13 | Brookfield Homes → Brookfield Residential | 1202157 / 1502554 | `REORG` → `PRIV` | 2011-04 / 2015-03-27 | Brookfield Asset Mgmt | **Present but 40-F/6-K, not 10-K — see §4** |
| 14 | UCP, Inc. | 1572684 | `ACQ-PUB` | 2017-08-04 | Century Communities | Clean, but entirely post-2013 |
| 15 | Landsea Homes | 1721386 | `ACQ-PRIV` | 2025-06-25 | The New Home Company | FY2018–FY2024 |
| 16 | MDC Holdings → Sekisui House U.S. | 773141 | equity `ACQ-PUB`, **registrant still filing** | 2024-04-19 | Sekisui House | **Full and current — see §5** |

**Never SEC registrants — uncorrectable from EDGAR by any amount of searching:** *Mercedes Homes* and
*John Wieland Homes*. Full-text search returns only third-party mentions; company search returns no
registrant. Both were privately held throughout. Their absence is `not_applicable`, not a coverage
gap — closing it would require state corporate and bankruptcy-court records, outside this wave's
source standard.

---

## 3. The finding that matters most — the terminal-year blind spot

The obvious form of survivorship bias is "the dead are missing from the roster." The census found a
**second, sharper** form that no roster change can fix:

> **TOUSA, Orleans Homebuilders and Dominion Homes each stopped filing before their final annual
> report. The 10-K covering the period immediately before failure was never filed.**

- TOUSA: last annual period **2007-12-31**; Chapter 11 filed 2008-01-29; **no FY2008 10-K exists**.
- Orleans: last annual period **2008-06-30**; Chapter 11 filed 2010-03-01; **no FY2009 10-K exists**.
- Dominion Homes: filings stop **mid-2008**; the reported wind-down runs to ~2013 — a multi-year
  post-EDGAR-exit period that is `not_reconstructable`.

**Companies stop reporting exactly when the collapse they are undergoing becomes the interesting
observation.** EDGAR's record has a built-in blind spot at precisely the worst quarter of each firm's
life. So:

- The correction is **constructible for identity and timeline** on 14 of 16 names.
- It is **NOT constructible for terminal-year operating detail** on at least 3 bankruptcy cases.

A "survivorship-corrected" homebuilder panel is therefore still censored — it would contain the dead
firms' *healthy* years and lose their *dying* years. Adding the dead builders back would **understate**
distress, in the same direction as excluding them. This is not a reason to skip the correction; it is
a reason never to describe a corrected panel as unbiased.

---

## 4. Identity continuity — what resolves and what does not

**Resolvable at entity level:** Ryland → Standard Pacific/CalAtlantic (a *single unbroken CIK*,
878560) → Lennar · WCI(2013) → Lennar · Avatar/AV Homes → Taylor Morrison · William Lyon → Taylor
Morrison · UCP → Century Communities.

**Not resolvable:**

| Case | Why |
|---|---|
| **Levitt and Sons, LLC** — the entity that actually built homes and filed Chapter 11 (Nov 2007) | **Never an independent SEC registrant.** Only the diversified parent (Levitt Corp/Woodbridge, which retained non-homebuilding assets) is on EDGAR. There is no subsidiary-level filer to take metrics from. |
| **Brookfield Homes → Brookfield Residential** | The successor is a Canadian foreign private issuer filing **40-F/6-K, not 10-K/10-Q** (verified: 3× 40-F, 80× 6-K, **0× 10-K**). Documents exist for both entities through 2015, but the line items are not comparable without an explicit accounting translation. |

**Systematically unresolved across every "resolvable" case:** whether post-merger *segment metrics*
survive separately. Whether Lennar's post-2018 filings break out legacy-CalAtlantic operations, or
Taylor Morrison's break out legacy-AV Homes, was **not checked**. Entity continuity is not metric
continuity, and this census establishes only the former.

**A caveat on Avatar Holdings (#9):** it was a diversified Florida land and real-estate company for
much of its 1994–2012 history, not a pure homebuilder. Treating its full run as homebuilder data would
be an inference, not a fact.

---

## 5. Two definitional forks this census surfaces rather than buries

### 5.1 MDC Holdings — filer-continuous, equity-terminated

MDC's **equity** was acquired by Sekisui House on 2024-04-19, but the **registrant keeps filing**
10-Ks and 10-Qs through August 2026 under a public-debt (Section 15(d)) obligation. Two Form 15s on
record cover the common-equity registration only.

So MDC is simultaneously a mortality case and a full-window survivor, depending on the definition.

**Ruling.** The fork is resolved by clock, not by preference:
- **Operating clock** — MDC's disclosures are continuous and admissible as mechanism records to the present.
- **Recognition clock** — the equity a market participant could hold **ends 2024-04-19**. No
  recognition-clock construct may include MDC after that date.

Since IMCE's entire subject is mechanism → market recognition, MDC's usable recognition history ends
in 2024. Recorded so the choice is visible rather than implicit.

### 5.2 Hovnanian — a Form 15 that does not mean what it looks like

HOV filed a Form 15-12G on 2021-11-04 **while continuing to file 10-Ks, 10-Qs and 8-Ks through August
2026**. HOV has multiple registered securities (common, Class B, preferred); which class the 2021
deregistration covers was not resolved.

**Do not read the 2021 Form 15 as "Hovnanian stopped being a public filer." It did not.** Recorded as
a named trap: a Form 15 deregisters a *security class*, not necessarily a *registrant*.

---

## 6. The explicit inclusion decision (what condition (5) requires)

**Decision: the frozen inferential roster is UNCHANGED — DHI, LEN, PHM, NVR, KBH, TOL.**

Rationale, in order:
1. **Roster changes are frozen pre-outcome and may never follow outcome inspection** (freeze D6). This
   wave has inspected no outcome and has no basis on which to re-open the roster.
2. Adding dead builders would not deliver an unbiased panel anyway, because of the §3 terminal-year
   censoring — it would trade one known bias for a subtler one.
3. Amending the roster is an A4 act requiring an amendment-log entry, not a census act.

**But the decision to keep the roster does not make the roster representative, and two facts must
travel with every use of it:**

### 6.1 Four full-window survivors sit outside the frozen six

| Issuer | CIK | Spans 2005–2026? |
|---|---|---|
| Meritage Homes (MTH) | 833079 | **Yes** — clean, continuous |
| M/I Homes (MHO) | 799292 | **Yes** — clean, continuous |
| Beazer Homes (BZH) | 915840 | **Yes** — clean, single CIK, never deregistered |
| Hovnanian (HOV) | 357294 | **Yes** — continuous filer, restructuring flag (§5.2) |
| MDC Holdings | 773141 | Conditional (§5.1) |

CIKs independently re-verified against EDGAR by the commissioning session.

**A second-order survivorship effect, and it runs the same direction as the first.** The frozen six is
not "the U.S. public homebuilders that span the window" — at least four others do. And the two most
financially distressed survivors of the GFC era, **Beazer and Hovnanian**, are among the excluded. So
the roster is not merely a survivor roster; it is a roster biased toward the *strongest* survivors,
**even within the surviving population**. Excluding the walking wounded compounds the exclusion of the
dead. This was not previously documented and is the census's main contribution to roster construction.

### 6.2 Seven post-2011 entrants can contribute nothing to the early blocks

TPH, UCP, CCS, LGIH, TMHC, LSEA, DFH — none existed as public filers before 2012. Any construction
that samples "today's homebuilder roster" for pre-2012 history silently changes the sample's
composition mid-window. (UCP and Landsea both *entered and exited* inside the study window — the
survivorship trap recurring in miniature.)

---

## 7. What becomes impossible if the gap is not closed

Required by the commission, stated as named claim classes rather than a generality:

| # | Claim class | Why it fails |
|---|---|---|
| 1 | **Cohort means/medians of any operating metric, 2006–2011** | Mechanically excludes every firm that failed; biases the "typical builder" upward through the worst years. |
| 2 | **Cross-issuer dispersion** (variance, IQR, tail characterizations) | The tail is not observed at all in a six-survivor roster; dispersion is structurally understated. |
| 3 | **Cycle-trough severity** — "how bad it got" | The six are the strongest balance sheets of the era. Any trough read from them understates 2007–2009. §6.1 makes this worse: the strongest *survivors*, not merely survivors. |
| 4 | **Mortality or hazard rates** | This census supplies a numerator (named deaths) and **no denominator** (the full population of public homebuilders at each date). A hazard rate is **not constructible** from this packet. |
| 5 | **Time-series continuity past a merger date** | "CalAtlantic FY2017" cannot be traced into Lennar's post-merger segments without a purchase-accounting/segment bridge that does not exist here (§4). |
| 6 | **"The sector survived the GFC intact"** | False on its face once ≥9 failure/distress-absorption cases are counted. |
| 7 | **Any backtest sampling today's roster for pre-2012 history** | The classic survivorship construction; §6.2 quantifies who is missing. |

---

## 8. The mandatory disclosure — text, and why it stays

Condition (5) lifts the disclosure only when the census "lands with an explicit inclusion decision."
The census has landed and §6 records the decision. **The disclosure nonetheless stays**, because §3
and §6.1 establish that the underlying bias is *not cured* by the decision: the roster remains a
survivor roster, the dead builders' terminal years remain unobservable, and four full-window
survivors remain excluded.

Discharging an obligation to *document* a bias is not the same as *removing* it. Binding text:

> **Survivorship disclosure (IMCE-HB-0).** This roster comprises six issuers that survived to 2026,
> over a window containing the 2006–2011 homebuilder mortality event. Sixteen delisted, bankrupt or
> acquired builders are named in the HB-0 survivorship census and are **not** in this sample; four
> further full-window survivors (MTH, MHO, BZH, HOV) are also excluded, including the two most
> distressed GFC-era survivors. Three failed builders never filed a final annual report, so their
> collapse periods are unobservable even in principle. **No cohort mean, dispersion statistic, or
> trough-severity characterization may be quoted without this notice.**

---

## 9. Falsifiers

| # | Falsifier | Effect |
|---|---|---|
| F-1 | A failed builder's terminal-year financials are found in a non-EDGAR source (bankruptcy-court filings, state records). | §3's censoring weakens for that name; a corrected panel becomes more nearly complete. |
| F-2 | Post-merger segment disclosures are found that separately track legacy CalAtlantic/Ryland/WCI inside Lennar. | §4's metric-continuity gap closes for the largest chain in the census. |
| F-3 | A defensible denominator (public homebuilder population by date) is constructed. | Claim class 4 becomes possible; a genuine mortality rate could be quoted. |
| F-4 | The roster is deliberately widened at A4 to include MTH/MHO/BZH/HOV via an amendment-log entry. | §6.1's second-order bias is reduced. **Note: this does not raise `n_effective_blocks`** — more issuers inside the same shocks add correlated rows, not independent draws (block list §7). |
| F-5 | Mercedes Homes / John Wieland are found to have had SEC-registered public debt. | Two `not_applicable` verdicts become coverage gaps that could be closed. |

**F-4 deserves emphasis, because it is the most tempting mistake available here.** Widening the roster
improves *representativeness*; it does **not** improve *power*. The two are separate problems and only
the first is addressable by adding issuers.

---

## 10. Gaps

| Gap | What would verify it |
|---|---|
| Scope of Hovnanian's 2021 Form 15-12G (which security class) | Open the Form 15-12G and read its Rule/class fields |
| Whether post-merger segment metrics survive separately for any chain in §4 | Open Lennar FY2018+ and Taylor Morrison FY2019+ MD&A segment sections |
| William Lyon's 2006–2012 private interval | Locate re-registration filings on the same CIK |
| Taylor Morrison's pre-2015 Up-C predecessor CIK | EDGAR company search for the 2013 IPO vehicle |
| Denominator for a mortality rate | A separate, harder population census — explicitly not attempted |
| Terminal-event narratives (bankruptcy chapters, deal closes) | Several are labeled SOURCE CLAIM from search, not opened as primary court/EDGAR documents |
