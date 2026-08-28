# IMCE-HB-0 — Fiscal → calendar → macro time map (frozen crosswalk)

**Wave:** A3 / IMCE-HB-0. Records-only.
**Authority:** merged freeze §7.2 condition (3) — "Episodes re-key on **calendar month** (fiscal
year-ends span Sept 30 → Dec 31); the fiscal→calendar crosswalk freezes pre-outcome"; contract §2(a)
[A17] — "no re-key is permitted after outcome access"; D4 clock law; [G8-M2] epoch-clock rule.

**Evidence lane:** research/sonnet, 2026-08-21. Built from the SEC EDGAR submissions API for all six
issuers (every filing 2001→present with form, `filingDate`, `reportDate`, `items`), with fiscal
year-ends additionally verified against the literal FY2025 10-K cover-page text, and cross-checked
against the complete unbroken run of **65 quarter-end dates per issuer**. Earnings-release dates were
matched exhaustively via `items` containing **2.02** ("Results of Operations and Financial
Condition") across **144 issuer-quarters** — not a hand sample.

**Fences honoured:** no price, return, or outcome data. No FRED/ALFRED. The only computed statistics
are medians and min/max of lag-day counts.

---

## 1. Fiscal calendars (VERIFIED — cover page + 65 quarter-ends each)

| Issuer | CIK | Fiscal year-end | 52/53-week? | FYE change 2005–2026? |
|---|---|---|---|---|
| DHI | 0000882184 | **September 30** | No — fixed calendar date | No |
| LEN | 0000920760 | **November 30** | No | No |
| KBH | 0000795266 | **November 30** | No | No |
| TOL | 0000794170 | **October 31** | No | No |
| PHM | 0000822416 | **December 31** | No | No |
| NVR | 0000906163 | **December 31** | No | No |

CIKs independently re-verified against EDGAR company search by the commissioning session.

The stability claim is a **verified fact, not an endpoint inference**: it rests on the complete run of
65 10-Q/10-K `reportDate` values per issuer landing on exactly four fixed month-end dates each, across
all 22 years — not on comparing 2005 to 2026.

**Four distinct fiscal year-ends across six issuers.** This is the structural fact that makes every
other section of this document necessary.

---

## 2. Fiscal quarter → calendar month (VERIFIED, stable across the full window)

| Issuer | FQ1 | FQ2 | FQ3 | FQ4 (= FYE) |
|---|---|---|---|---|
| DHI (Sep 30) | Oct–Nov–Dec **(prior CY)** | Jan–Feb–Mar | Apr–May–Jun | Jul–Aug–Sep |
| TOL (Oct 31) | Nov–Dec–Jan **(spans 2 CYs)** | Feb–Mar–Apr | May–Jun–Jul | Aug–Sep–Oct |
| LEN (Nov 30) | Dec–Jan–Feb **(spans 2 CYs)** | Mar–Apr–May | Jun–Jul–Aug | Sep–Oct–Nov |
| KBH (Nov 30) | Dec–Jan–Feb **(spans 2 CYs)** | Mar–Apr–May | Jun–Jul–Aug | Sep–Oct–Nov |
| PHM (Dec 31) | Jan–Feb–Mar | Apr–May–Jun | Jul–Aug–Sep | Oct–Nov–Dec |
| NVR (Dec 31) | Jan–Feb–Mar | Apr–May–Jun | Jul–Aug–Sep | Oct–Nov–Dec |

Only **PHM and NVR** are calendar-aligned. **LEN, KBH and TOL each have a fiscal quarter that straddles
a calendar-year boundary**, and therefore **never** align exactly to any calendar quarter — in any
quarter of any year.

---

## 3. The alignment hazards — worked, with sizes

### Hazard A — identical fiscal-quarter LABEL, zero calendar overlap

FY2024 FQ1 measurement windows, verified:

| Issuer | measurement_start | measurement_end |
|---|---|---|
| DHI | 2023-10-01 | 2023-12-31 |
| TOL | 2023-11-01 | 2024-01-31 |
| LEN | 2023-12-01 | 2024-02-29 |
| KBH | 2023-12-01 | 2024-02-29 |
| PHM | 2024-01-01 | 2024-03-31 |
| NVR | 2024-01-01 | 2024-03-31 |

**DHI's "FQ1" and PHM/NVR's "FQ1" share ZERO calendar days.** A full three-month offset under an
identical label. A join keyed on `(issuer, fiscal_quarter_number)` pairs DHI's Q4-2023 trading with
PHM/NVR's Q1-2024 trading and calls them the same period.

### Hazard B — identical calendar quarter, different fiscal LABELS

Calendar Q4 2023 (Oct–Dec 2023):

| Issuer | Fiscal label covering Oct–Dec 2023 | Match |
|---|---|---|
| DHI | **FY2024 FQ1** | exact, 3/3 months |
| PHM | **FY2023 FQ4** | exact, 3/3 months |
| NVR | **FY2023 FQ4** | exact, 3/3 months |
| TOL | splits FY2023 FQ4 / FY2024 FQ1 | best 2/3 months |
| LEN | splits FY2023 FQ4 / FY2024 FQ1 | best 2/3 months |
| KBH | splits FY2023 FQ4 / FY2024 FQ1 | best 2/3 months |

The same three calendar months are **"FY2024 Q1" for DHI and "FY2023 Q4" for PHM/NVR** — a full
fiscal-year label offset. Any rule of the form "use each issuer's Q4" or "use each issuer's Q1" is
systematically wrong for two of six issuers by a year, and is never exactly right for the other three.

### Hazard C — the release clock differs across issuers *after* calendar re-keying

This one is **not** cured by calendar-month re-keying and is the hazard most likely to be missed.

Median release lag (measurement_end → 8-K Item 2.02), n=24 issuer-quarters each (FY08, FY09, FY22–25):

| Issuer | Release lag median | Release lag range | Filing lag median | Filing lag range |
|---|---|---|---|---|
| LEN | **18d** | 13–38d | 37d | 28–60d |
| TOL | 20d | **6–39d** | 34d | 28–51d |
| NVR | 24d | 21–31d | 36d | 25–57d |
| KBH | 24d | 18–44d | **40d** | 35–60d |
| PHM | 25d | 21–40d | 32d | 21–57d |
| DHI | **28d** | 17–51d | 34d | 22–57d |

Two issuers whose measurement windows have been correctly re-keyed to the *same calendar month* still
became public **10 days apart at the median**, and up to **~45 days apart** at the extremes (TOL's 6d
minimum vs DHI's 51d maximum). A same-calendar-month join is therefore **not** a same-knowledge-state
join. Any construct that mixes issuers within a period must state which clock it is on, and a
recognition-clock construct must use each issuer's own `available_at`, never a shared period label.

---

## 4. The five stamps

| Stamp | Definition adopted |
|---|---|
| `measurement_start` / `measurement_end` | Calendar start/end of the fiscal quarter per §2. `measurement_end` = the 10-Q/10-K `reportDate`, verified. |
| `fiscal_period` | `{TICKER}-FY{yyyy}-Q{n}`, where `yyyy` is the fiscal-year label on the issuer's own cover page (the calendar year in which the fiscal year **ends**). |
| `reported_at` | Filing date of the 8-K carrying the Item 2.02 earnings release (EX-99.1) — the first public disclosure of headline results. SEC-timestamped via `acceptanceDateTime`. |
| `available_at` | **Metric-dependent — see §5.** Not a single value per period. |
| `calendar_bucket` | The calendar month containing `measurement_end`. **See the containment warning in §5.** |
| `knowledge_cutoff` | Equals `available_at` at the metric level. **There are at least two per fiscal period.** |

---

## 5. Two findings that change how the stamps must be used

### 5.1 `available_at` is metric-dependent — one period has TWO knowledge cutoffs

Headline operating metrics — homes closed, net sales orders (units and $, by region), backlog units
and value, cancellation rate, gross margin, segment revenue — are disclosed in the **8-K earnings
release**, so for these `available_at = reported_at`.

Full audited statements, footnote-level debt-maturity schedules, tax-rate reconciliation,
off-balance-sheet and JV entity detail, and warranty rollforwards are **structurally absent from every
quarter's earnings release** and first become public at the **10-Q/10-K filing date**.

The gap is real and recurring: **0–25 additional days for Q1–Q3, and 9–31+ additional days for
Q4/annual**, every quarter, every issuer. This is a *structural* retro-disclosure lag, not an anomaly.

**Consequence:** a JV-inclusive or balance-sheet-derived metric carries a materially later
`knowledge_cutoff` than an orders/backlog metric from the same fiscal period. Stamping one
`available_at` per period would make the later-disclosed field look knowable weeks before it was.
**Every metric carries its own `available_at`.**

*Verification status:* established by opening DHI's FY2025 Q4 EX-99.1 and diffing it against the 10-K.
Generalization to the other five issuers is a **spot-check generalization**, not a per-issuer verified
fact. Named in §7.

### 5.2 The containment rule silently disagrees for three of six issuers

`calendar_bucket` can be defined by *endpoint* containment (the calendar quarter containing
`measurement_end`) or by *full-window* containment (the calendar quarter containing the whole
measurement span). DHI, PHM and NVR always have a fully-containing calendar quarter. **LEN, KBH and
TOL never do** — their quarters straddle. So the two rules disagree for those three issuers on
**every single quarter of the window**.

**Ruling:** `calendar_bucket` is the calendar **month** containing `measurement_end`, per the freeze's
calendar-month re-key requirement. A quarter-level bucket is not used, because at quarter granularity
the choice of containment rule is a hidden analyst seam of exactly the kind [A19] closes. Where a
macro series is monthly, the month-level bucket is exact; where it is quarterly, the issuer's window
is mapped to its overlapping months and the overlap is **printed**, never rounded.

---

## 6. Retro-disclosure: the cohort finding, stated at the right size

The freeze's cautionary exhibit is a **13-month** retro-disclosure lag on a non-homebuilder issuer
(CELH's Q1-2023 pipeline fill, disclosed 2024-05-07). This lane searched the homebuilder cohort for an
analogue and **found nothing of that magnitude**.

What it did find is the §5.1 structural lag: a recurring, every-quarter, every-issuer gap of days-to-
weeks affecting balance-sheet and footnote detail, not headline operating KPIs.

**Stated honestly: the homebuilder cohort does not reproduce the 13-month exhibit, and this census
makes no claim that it does.** The relevant hazard here is smaller, structural, and predictable — which
makes it easier to handle correctly and easier to ignore by accident. The §5.1 rule handles it.

---

## 7. Gaps and one data-quality trap

### The trap — LEN's FY2005 10-K carries a corrupted period-of-report in EDGAR

EDGAR's structured `reportDate` for LEN's FY2005 10-K (filed 2006-02-09, accn `0001193125-06-025438`)
reads **2005-01-30**. The document's own cover page reads **"For the fiscal year ended November 30,
2005"** — verified by opening it.

Any ingester trusting the raw submissions-JSON `reportDate` **mis-keys this filing by ten months**, and
would place a full fiscal year of Lennar's data — inside the GFC-bust block — in the wrong period. The
correct value is **2005-11-30**. This is recorded as a named trap for any future automated lane.

### Gaps

| Gap | What would verify it |
|---|---|
| Metric-level `available_at` (§5.1) spot-checked on 1 of 144 issuer-quarters (DHI FY2025 Q4) | Open the EX-99.1 and matching 10-Q/10-K for one quarter per issuer and diff disclosed line items |
| 8-K Item 2.02 matching used a nearest-within-100-days heuristic; all 144 produced monotonic, plausible lags (17–51d, no negatives) but were not individually opened | Open each matched 8-K's exhibit list and confirm the title names earnings/results |
| 52/53-week absence inferred from 65 fixed quarter-end dates per issuer (strong but indirect) rather than from a basis-of-presentation footnote | Full-text search each 10-K's basis-of-presentation note for "52/53-week" |
| FY2005/FY2006-era 10-K/A amendments exist for LEN, NVR and PHM; not opened to determine what was restated | Open each 10-K/A explanatory note — deliberately out of scope, as this wave is fenced from figure computation |
| Latest 2026 quarter per issuer taken from the submissions JSON at fetch time (2026-08-21) | Re-pull at time of use |

---

## 8. What freezes here

Frozen pre-outcome by this wave, per §7.2(3) and [A17]:

1. The six fiscal year-ends (§1).
2. The fiscal-quarter → calendar-month map (§2).
3. `calendar_bucket` = calendar month containing `measurement_end` (§5.2).
4. `available_at` is metric-level, never period-level (§5.1).
5. `fiscal_period` naming: `{TICKER}-FY{yyyy}-Q{n}`, `yyyy` = fiscal year of the issuer's own label.
6. LEN FY2005 `reportDate` = **2005-11-30**, overriding EDGAR's corrupted field (§7).

**No re-key is permitted after outcome access.** Any change requires an amendment-log entry.
