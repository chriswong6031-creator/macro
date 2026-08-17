# E0 Golden Universe and Acceptance Cases

**Wave:** E0 · **Verified:** 2026-08-16  
The golden universe is the acceptance set for E1–E8. E1/E2 prove **one** flagship event end-to-end. The rest are regression cases, not this session’s build.

Corpus CIKs in `tests/fixtures/company_intelligence/golden_corpus_issuers.v1.json` are **`cik_synthetic`**. Production `company_id` must use real EDGAR CIKs.

R0-D corpus remains the identity/citation **fixture** set: 130 issuers, 234 difficult events, 17 classes (`research/company_intelligence/GOLDEN_CORPUS_MANIFEST.json`).

---

## 1. Five companies

| Company | Why it is in | Live 2026-08-16 | Corpus role |
|---|---|---|---|
| **AAPL** | Profitable mega-cap; release + transcript + slides exist in the world; CI already has FY2026 Q3 | CI `cie_98e318c37ec1a2a1f83c45e1` call 2026-07-30; Wire article 404 | `fiscal_year_ambiguity` / speaker-role cases |
| **SNOW** | Unprofitable / growth-KPI operating model | Use next reported event; corpus name reserved | general growth |
| **CAT** | Industrial / supply-chain; amendment class | Corpus `amendment` + `edgar_identity_join` | `CIE-GC-0025` |
| **BAC** | Bank basis (NII / CET1 / provisions ≠ GAAP EPS) | Corpus `bank_basis` | `CIE-GC-0113` |
| **GOOGL** | Dual-class identity; AI/cloud reporting wave | CI 200 on GOOGL Q2 FY2026; **GOOG 404** | `share_class` 16 cases |

Finance flavor extras (not a sixth company, available if BAC is blocked): **AIG** insurer, **AMT** REIT.

---

## 2. Eight events

| # | Coverage need | Event | Acceptance |
|---|---|---|---|
| 1 | Mega-cap release/transcript/slides | **AAPL FY2026 Q3** call 2026-07-30 · live `cie_98e318c37ec1a2a1f83c45e1` · canonical `evt_cik0000320193_2026q3_results` | **E1/E2 flagship.** Bind 8-K/Exhibit 99.1 + transcript. Glance facts must reverse to spans or typed absence. |
| 2 | Unprofitable growth KPIs | **SNOW** latest completed quarter in corpus + next live print | Operating KPIs (RPO, cRPO, NRR) with units; no fake GAAP profitability |
| 3 | Industrial / supply-chain | **CAT** amendment `CIE-GC-0025` plus latest live print | Correction replay: same event_id, new source SHA, consumers invalidate |
| 4 | Bank basis | **BAC** `CIE-GC-0113` | Refuse GAAP-vs-NII cross-basis beat/miss |
| 5 | Dual-class identity | **GOOGL** Q2 FY2026 `cie_e7b4b160257b99936851ece0` + **GOOG** alias | One canonical event; GOOG must not 404 *or* must typed-absence as alias, not a second issuer |
| 6 | Corrected source | **CAT** / **BA** amendment class (2 revisions) | `correction_status=corrected`; Wire banner; CI rebuild |
| 7 | Missing transcript or slides | Corpus `NET` `CIE-GC-0147` (`missing_transcript`); `UAL` `CIE-GC-0187` (`changed_slide_family`) | Typed absence, not a fabricated receipt. Freeze Q3: 51 typed absences in corpus is the grading key |
| 8 | Speaker-role + Q&A pressure | **XOM** `CIE-GC-0199` (freeze worked example) | Byte range verifies; speaker/role on locator may be asserted (Freeze Q6) |

---

## 3. Golden reporting wave (E8, not E1)

**Wave theme:** AI infrastructure / cloud / memory / power.

| Role | Name | Why |
|---|---|---|
| Early announcer | **GOOGL** Q2 FY2026 call 2026-07-22 | Cloud +82%, backlog $514B, CapEx $195–205B, supply constrained |
| Peer, later / overlapping | **AAPL** Q3 FY2026 call 2026-07-30 | Memory “100-year flood”; SoC supply constraints — **negative/competitive** read on memory and foundry, **positive** on device demand |
| Peer, not-yet-reporting at GOOGL print | **NVDA**, **AVGO**, **TSM**, selected utilities / cooling names | Mechanism: AI capex and memory tightness. Direction is **not** “announcer beat → every peer bullish” |
| Operating mechanism | Cloud backlog + capex + memory cost + SoC supply | Must be explicit on the wave object |
| Positive interpretation | Hyperscale demand still in front of supply | GOOGL Cloud, AAPL device units |
| Negative / competitive interpretation | Memory and foundry costs, supply constraint, FCF | AAPL gross-margin pressure; GOOGL FCF −$5.9B |
| Market incorporation | Tape already moved vs still catching up | E8 field; not E1 |
| Later grading events | Subsequent NVDA / TSM / memory prints | Grade the hypothesis; do not promote |

This wave is recorded so E8 does not invent a toy example. E1 does **not** build the wave.

---

## 4. Flagship glance facts (AAPL Q3 FY2026) — real data, not placeholders

These are **CI overlay facts as of 2026-08-16**. E1 must either bind each to an Exhibit 99.1 / transcript span or mark typed absence. They are the E2 glance payload.

| Fact | CI text | Lineage today | E1 required outcome |
|---|---|---|---|
| Revenue | Record June quarter revenue $109.4B (+16% YoY) | `earnings_history` highlight | Span or typed absence |
| iPhone | +22% | history | Span or typed absence |
| Mac | +29% | history | Span or typed absence |
| Services | $30.7B (+12%) | history | Span or typed absence |
| Install base | 2.5B active devices | history | Span or typed absence |
| Demand vs supply | iPhone and Mac “remarkably better than we thought”; Q4 supply constraints increase sequentially | `score_overlay` summary + history | Overlay prose **cannot** remain the glance |
| Memory | “100-year flood”; costs higher next quarter | history | Span |
| FX | Additional 2.5 ppt sequential YoY growth headwind in Q4 | history | Span |
| Questions | 14 | history metric | Count from structured Q&A or typed absence |

Authority: `context_only`. No beat/miss vs consensus unless the basis matches (Freeze / Wire L3).

---

## 5. Control events (not flagship)

| Event | Role |
|---|---|
| **IEX Q2 FY2026** live Wire | Receipt grammar already works (guidance quote + 45 spans) |
| **LMND Q2 FY2026** live Wire vs CI Q1 | Freshness-split diagnostic; CI must not be called “current” |

---

## 6. What would fail the universe

- Resolving materially more than 155 corpus cases to `exact_receipt` (manufactured citations).
- Minting GOOG and GOOGL as two issuer events.
- Using synthetic corpus CIKs in production.
- Declaring AAPL **E1** done without `read_event_workspace` observing the canonical payload and a correction replay.
- Declaring the **E1+E2 arc** done while the dossier still leads with `score_overlay` wording.
