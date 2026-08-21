# IMCE-HB-0 — Homebuilder source & definition census: FROZEN

**Wave:** A3 of the merged IMCE-00 architecture freeze (`ec44ae7d1659`, PR #6127, merged
2026-08-21T03:55Z). **Records-only.** Census date **2026-08-21**.

**Authorization:** freeze §13 — *"A3 — IMCE-HB-0, homebuilder source/definition census freeze
(records-only): fixed roster, denominator crosswalk, fiscal→calendar re-key, structural-break ledger,
frozen block list, cell budget confirmation. **Stop before any fitting.**"*

**Stop honoured.** This wave stops at the frozen census and returns to Fable for adjudication. It does
not proceed to A4.

---

## 0. The census in six sentences

The frozen roster of six survivors is kept, and is now documented as a survivor roster in **two**
senses rather than one — sixteen dead builders are named, and four full-window survivors including the
two most distressed GFC-era names sit outside it. Six issuers turn out to have six mutually
incompatible cancellation-rate regimes, so the "denominator crosswalk, not a standardized column"
instruction was not a stylistic preference but a description of the data. The honest historical block
count resolves to **B = 5**, at the bottom of the freeze's 5–7 range, because one listed block overlaps
another and one is still open — and B = 5 is the only basis on which the freeze's own published
come-back headline (~2145) reproduces. Two of the four D5 mechanism states have no cohort-wide
measurable basis at all, which the 6-cell budget was set before anyone knew. Only one macro context
leg — Treasury constant-maturity yields — is confirmed point-in-time, public-domain and
archive-complete, while NAR's terms bar storage outright. Every historical cell's predetermined
`underpowered_accruing` status is confirmed on this census's own arithmetic rather than inherited.

---

## 1. Artifact index

| # | Artifact | What it settles |
|---|---|---|
| 1 | [`IMCE_HB0_COHORT_IDENTITY_CENSUS.md`](IMCE_HB0_COHORT_IDENTITY_CENSUS.md) | Frozen roster, CIKs, name lineage, five identity traps, structural roles, the LEN-exclusion correction |
| 2 | [`IMCE_HB0_METRIC_DEFINITION_CROSSWALK.md`](IMCE_HB0_METRIC_DEFINITION_CROSSWALK.md) | Six cancellation regimes; 14 named cross-issuer incompatibilities; the era finding |
| 3 | [`IMCE_HB0_FISCAL_CALENDAR_MAP.md`](IMCE_HB0_FISCAL_CALENDAR_MAP.md) | Verified FYEs, quarter→month map, three alignment hazards, the five stamps, the EDGAR date trap |
| 4 | [`IMCE_HB0_SOURCE_PIT_VINTAGE_MATRIX.md`](IMCE_HB0_SOURCE_PIT_VINTAGE_MATRIX.md) | 17 series audited; vintage-class vocabulary adjudication; the NAR storage bar |
| 5 | [`IMCE_HB0_SURVIVORSHIP_CENSUS.md`](IMCE_HB0_SURVIVORSHIP_CENSUS.md) | 16 mortality cases; the terminal-year blind spot; explicit inclusion decision; mandatory disclosure |
| 6 | [`IMCE_HB0_STRUCTURAL_BREAK_LEDGER.md`](IMCE_HB0_STRUCTURAL_BREAK_LEDGER.md) | 28 events; the universal no-restatement rule and its one exception; counts-vs-level breaks |
| 7 | [`IMCE_HB0_INDEPENDENT_BLOCK_LIST.md`](IMCE_HB0_INDEPENDENT_BLOCK_LIST.md) | B = 5 hardened; five defects in the frozen list; the pseudoreplication ceiling |
| 8 | [`IMCE_HB0_A4_CELL_BUDGET_INPUTS.md`](IMCE_HB0_A4_CELL_BUDGET_INPUTS.md) | Exact A4 inputs; the two unmeasurable mechanism states; six open elections |
| 9 | [`IMCE_HB0_BLOCKERS_AND_FALSIFIERS.md`](IMCE_HB0_BLOCKERS_AND_FALSIFIERS.md) | 7 hard blockers, 12 soft, 19 falsifiers, 3 likely misreadings, 2 corrections owed upward |
| — | [`evidence/`](evidence/) | Seven lane packets preserved verbatim, with their own verification tiering and gaps tables |

---

## 2. Acceptance criteria, audited against what was produced

| Criterion | Verdict | Where |
|---|---|---|
| Each proposed variable has a real source and definition | **PASS with typed absences** — ~21 metrics × 6 issuers × 12 definition fields. Where an issuer does not disclose a concept it is typed `not_applicable` / `missing` / `not_reconstructable`, **never zeroed, never imputed, never substituted from a peer** | Artifact 2 + evidence |
| Cross-company differences are not flattened | **PASS** — 14 named incompatibilities preserved; the census explicitly refuses to build a single cancellation-rate column | Artifact 2 §1, §3 |
| Fiscal/calendar joins are explicit | **PASS** — all six FYEs verified from cover pages *and* 65 quarter-ends each; misalignment measured at up to a full quarter; release lags from 144 issuer-quarters | Artifact 3 |
| Survivorship addressed, not footnoted | **PASS** — 16 named cases, explicit inclusion decision, a second-order finding (the excluded distressed survivors), and a named claim-impossibility list | Artifact 5 |
| PIT/vintage state explicit | **PASS** — 17 series classed; vocabulary defect adjudicated without minting a CPI enum value; rights gate placed before vintage gate | Artifact 4 |
| Block count cannot be inflated by issuer-quarter pseudoreplication | **PASS** — 522 naive rows vs `n_eff` ≈ 5–6, an ~87× factor, with four compounding mechanisms named | Artifact 7 §7–8 |
| No outcome was read | **PASS** — verified by grep across every artifact and every lane packet | §4 below |
| No fitting occurred | **PASS** — ρ appears only as a pre-registered sensitivity grid; no parameter estimated | Artifact 7 §8 |

---

## 3. What changed relative to the freeze's expectations

| Freeze expectation | Census result |
|---|---|
| 5–7 honest blocks | **Resolved to B = 5** — the lower bound. Both corrections reduce the count. |
| n_eff ≈ 6–10 | **Reproduced at the lower end, ≈ 5.4–6.7**, and it is an **upper bound** (block-to-block dependence is unmodelled) |
| ~2145 come-back date | **Reproduced at ~2146 — and only at B = 5**, independently confirming the freeze's arithmetic |
| "Three cancellation denominators" (G4 census) | **Six regimes, no two alike**; one issuer (LEN) states none at all |
| LEN excluded — "no press-release cancellation rate" | Press-release absence confirmed; **but LEN discloses 14% in its 10-K MD&A**. Correction C1 |
| Fully public-source (confirmed) | **Confirmed for the issuer legs.** For macro context: NAR is **rights-blocked for storage**, Case-Shiller licensed, MBA paywalled, Freddie Mac ambiguous, NAHB unverified |
| Homebuilders are the first *quantitative* family | **Qualified** — two of four mechanism states are not cohort-measurable, and the signature metric has no verifiable denominator in the two GFC-era blocks |

---

## 4. Fence compliance

Verified by grep across all nine artifacts and all seven evidence packets:

- **No price, return, market-cap or performance figure** anywhere — including deal values surfaced
  incidentally during survivorship research, which were deliberately excluded.
- **No model, fit, p-value, alpha claim or cycle prediction.**
- **No FRED or ALFRED content** fetched, quoted, cached or stored — clause (q) binds all use classes.
- **No behavioural or market-derived epoch** in the structural-break ledger.
- **No `data/`, `engine/`, `scripts/`, `site/`, `templates/`, `app/`, `.github/` or test path touched.**
  This wave writes only under `research/imce/hb0/` and `agentos/`.
- **No trial-ledger registration**, no source purchase, no runtime, no UI.

---

## 5. Frozen by this wave

Changing any of these requires an amendment-log entry, not a session decision:

1. The roster: DHI, LEN, PHM, NVR, KBH, TOL — with NVR as a separate stratum and LEN excluded from
   cancellation cells.
2. The fiscal→calendar crosswalk, `calendar_bucket` = calendar month of `measurement_end`, and
   metric-level `available_at`. LEN FY2005 `reportDate` = **2005-11-30**, overriding EDGAR's corrupted field.
3. Per-issuer canonical cancellation denominators where stated; **none freezable for LEN**; **TOL
   requires an election between two**.
4. The 14 preserved incompatibilities — no standardized cross-issuer column for any of them.
5. `source_vintage_class` as an HB-0-local vocabulary with a fixed crosswalk down to the three-value
   CPI `pit_class`. **No new CPI enum value is proposed.**
6. The mandatory survivorship disclosure text.
7. The missing-indicator ban [A18] extended to every era-correlated metric.

---

## 6. Proposed, NOT applied — for Fable/Sol adjudication

This census **does not amend the frozen block list or any freeze condition.** Two corrections are
owed upward and are submitted, not enacted:

- **C1** — restate the LEN cancellation exclusion's *reason* (keep the exclusion).
- **C2** — resolve the block list's overlap and open-block defects to **B = 5**.

Both are detailed in artifact 9 §5. Both reduce the census's own numbers.

---

## 7. Stop

**A3 is complete and stops here.** No fitting, no outcome access, no A4 work has begun. The next wave
in the authorized order is **A4 — IMCE-03 preregistration finalization**, which needs its own wave
approval and must make the six elections listed in artifact 8 §8 before any criteria commit.

Per the two-commit discipline [G8-B1], the criteria commit must strictly precede any outcome access.
Nothing in this census brings that boundary closer.
