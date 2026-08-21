# IMCE-HB-0 — Cohort and identity census (frozen roster)

**Wave:** A3 / IMCE-HB-0. Records-only.
**Authority:** merged freeze §7.2 (homebuilders CONDITIONAL_GO), D6 (roster frozen pre-outcome,
"never after outcome inspection"), contract §2 Homebuilders.
**Evidence:** `evidence/L1_cohort_survivorship.md`. CIKs independently re-verified against EDGAR
company search by the commissioning session. No price, return, or market-cap data appears here.

---

## 1. The frozen inferential roster

Six issuers. **Unchanged by this wave** — see the survivorship census §6 for the explicit inclusion
decision and its reasoning.

| Issuer | CIK | Legal name (EDGAR) | State | Exchange / tickers | FYE | Earliest 10-K on EDGAR |
|---|---|---|---|---|---|---|
| D.R. Horton | **882184** | HORTON D R INC /DE/ | DE | NYSE: DHI | Sep 30 | period 1996-09-30, filed 1996-12-20 |
| Lennar | **920760** | LENNAR CORP /NEW/ | DE | NYSE: **LEN (Class A), LEN-B (Class B)** | Nov 30 | period 1996-12-31, filed 1997-02-11 |
| PulteGroup | **822416** | PULTEGROUP INC/MI/ | MI | NYSE: PHM | Dec 31 | period 1996-12-31, filed 1997-03-06 |
| NVR | **906163** | NVR INC | VA | NYSE: NVR | Dec 31 | period 1996-12-31, filed 1997-03-12 |
| KB Home | **795266** | KB HOME | DE | NYSE: KBH | Nov 30 | period 1994-11-30, filed 1995-02-28 |
| Toll Brothers | **794170** | Toll Brothers, Inc. | DE | NYSE: TOL | Oct 31 | period 1994-10-31, filed 1995-01-24 |

**Window coverage: complete.** Every issuer's EDGAR 10-K series begins 1994–1997, comfortably before
the 2005-01-01 study-window start. No roster member has a coverage gap inside the window — which is
precisely what makes it a survivor roster (survivorship census §6.1).

---

## 2. Name lineage — three roster members have changed names inside or near the window

| Issuer | Former name(s) on the same CIK | Dates |
|---|---|---|
| **PulteGroup** | PULTE CORP → PULTE HOMES INC/MI/ → PULTEGROUP INC/MI/ | 1994-02-14 → 2001-05-02 → **2010-03-23** |
| **KB Home** | KAUFMAN & BROAD HOME CORP | until **2001-01-05** |
| **Lennar** | PACIFIC GREYSTONE CORP /DE/ | 1996-06-27 → 1997-09-26 |
| **Toll Brothers** | TOLL BROTHERS INC (no comma) | until 2019-03-28 — punctuation only, not substantive |

PulteGroup's final rename (2010-03-23) falls **inside the window and immediately after the Centex
merger** — a name search restricted to "Pulte Homes" would silently truncate the series at 2010.
Always key on **CIK**, never on name.

---

## 3. Identity traps found (record these; they are how a census goes wrong quietly)

### 3.1 A second Lennar-named CIK exists and is not Lennar

The definition lane flagged **CIK 0000058696** — a near-dormant shell with a confusingly similar name.
**The correct Lennar registrant is CIK 920760.** Note also that 920760 itself carried the name
*Pacific Greystone Corp* until 1997, so neither name-matching nor a naive "oldest Lennar-ish CIK"
heuristic resolves this. CIK 920760 is the only correct answer.

### 3.2 Lennar has two share classes

EDGAR's `tickers`/`exchanges` arrays carry `["LEN","LEN-B"]` on `["NYSE","NYSE"]` — verified fact,
not inference. Any recognition-clock construct must state which class it means. Class A is the
liquid listing; Class B is a separate registered security.

### 3.3 A Form 15 deregisters a security class, not necessarily a registrant

Established on Hovnanian (survivorship census §5.2): HOV filed a Form 15-12G in 2021 and **kept
filing 10-Ks through 2026**. Any pipeline treating a Form 15 as a terminal event will mis-date
issuer deaths. See also MDC (§5.1 there): equity terminated, registrant still filing.

### 3.4 EDGAR's structured period-of-report can be wrong

Lennar's FY2005 10-K carries `reportDate` **2005-01-30** in EDGAR metadata; the cover page reads
**"fiscal year ended November 30, 2005"**. A pipeline trusting the raw field mis-keys a full fiscal
year — inside the GFC-bust block — by ten months. Correct value: **2005-11-30**. Frozen in the
fiscal/calendar map §8.

### 3.5 Pre-1994 history is not on EDGAR at all

Electronic filing phased in 1993–1996, so each issuer's earliest EDGAR 10-K postdates its actual IPO
by 1–25 years. Paper-only annual reports are `not_reconstructable` from EDGAR. **Irrelevant to this
study** (the window opens 2005) but fatal to any future attempt to extend the window backward without
NYSE/SEC paper archives.

---

## 4. Structural roles within the roster (frozen by the architecture, not chosen here)

| Issuer | Role | Source of the rule |
|---|---|---|
| DHI | full pooling member | — |
| PHM | full pooling member | — |
| KBH | full pooling member | — |
| TOL | full pooling member | — |
| **NVR** | **separate stratum or designated transfer test — never pooled to raise n** | freeze §7.2(2): ~100%-option land model, mechanism outlier |
| **LEN** | **excluded from cancellation-rate cells**; carries a Feb-2025 Millrose break flag | freeze §7.2(1) — **but see §5, the stated reason needs correction** |

So the maximum poolable count is **m = 5** for a general cell, and **m = 4** for a cancellation cell
(LEN excluded, NVR held out). Six tickers never means six independent contributors.

---

## 5. A correction owed to the freeze — the LEN cancellation exclusion

The freeze states the exclusion as:

> **LEN** is excluded from cancellation-rate cells (**no press-release cancellation rate**; its
> missingness is era-correlated by construction — a missing-indicator would be an era proxy)

**The census found this is half right, and the half that is wrong matters.**

**Confirmed:** Lennar publishes **no cancellation rate in its earnings press releases.** Verified by
direct search of three FY2025 EX-99.1 exhibits (Q1, Q2, Q4) — zero occurrences of "cancel" in any of
them. (Q3 was not checked; recorded as a gap.)

**Refuted:** Lennar is *not* silent on cancellations in its public record. **Lennar discloses a
cancellation rate of 14% for both FY2025 and FY2024 in its 10-K MD&A.** The rate is not missing; it
is missing *from one channel*.

**Why this matters rather than being a quibble.** "Missing" and "disclosed later, elsewhere" imply
different exclusions:
- On the **recognition clock**, Lennar's cancellation rate is genuinely unavailable at `reported_at`
  (the 8-K), becoming available only at the 10-K filing date — weeks later, and only annually.
- On the **operating clock**, Lennar has a cancellation rate like everyone else.

**The stronger and correct ground for exclusion is a different one the freeze did not state:** Lennar
**publishes no formula**. DHI states its denominator explicitly ("cancelled sales orders divided by
gross sales orders"); PHM and NVR state theirs; **Lennar states none anywhere the census could find.**
Freeze condition (4) requires "one canonical cancellation-rate denominator per issuer … frozen with a
printed conversion." For Lennar there is nothing to freeze without inventing an assumption — and an
assumed denominator silently imported into a cross-issuer comparison is precisely the flattening this
census exists to prevent.

**Proposed disposition for A4 adjudication:** keep the LEN exclusion; **restate its reason** as
*"no disclosed cancellation-rate denominator, and no press-release disclosure — so neither a canonical
denominator nor a recognition-clock-timely value can be frozen"*. The era-correlated-missingness
concern and the missing-indicator ban [A18] both survive unchanged and are, if anything, better
supported by the precise reason than by the imprecise one.

This is a **correction to a binding freeze condition's stated rationale** and requires an
amendment-log entry. It is not applied unilaterally here.

---

## 6. Gaps

| Gap | What would verify it |
|---|---|
| IPO/listing dates for all six are SOURCE CLAIM (EDGAR carries no structured IPO field) | Exchange listing records or prospectus filings; not load-bearing for a window opening in 2005 |
| CIK 0000058696's actual identity (§3.1) | Open its submissions JSON and read its filing history |
| Lennar Q3 FY2025 EX-99.1 not checked for cancellation-rate absence (3 of 4 quarters verified) | Fetch the Q3 FY25 8-K EX-99.1 and search for "cancel" |
| Whether Lennar ever stated a cancellation formula in pre-2010 10-Ks | Full-text search LEN 10-Ks 2005–2010 for "cancellation rate is calculated" |
| Toll Brothers' 2019 comma rename treated as non-substantive (INFERENCE) | Open the 2019 filing that effected the name change |
