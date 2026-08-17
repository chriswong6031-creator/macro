# E0 Experience Architecture

**Wave:** E0 · **Verified:** 2026-08-16 · **UI implementation:** none this session  
**Grammar:** extend existing Terminal / dossier / Wire. Do not redesign the Terminal shell.  
**Doctrine:** `docs/DESIGN_DOCTRINE.md` — glance = state + stance + next action.  
**Specimen:** `compositions/e0_real_data_specimen.html` (AAPL Q3 FY2026 real CI facts).  
**Sizes:** 1440 / 820 / 390 are composition rules below, not a 240-screenshot dump. E2 freezes the screenshot set.

Real data used (live CI 2026-08-16, **not yet span-bound** — that is the E1 gap the UI must make visible):

- Apple · `AAPL` · FY2026 Q3 · call 2026-07-30 · `cie_98e318c37ec1a2a1f83c45e1`
- Revenue $109.4B +16% · iPhone +22% · Mac +29% · Services $30.7B
- Supply constraints up sequentially in Q4 · memory “100-year flood” · FX −2.5 ppt
- `claim_citations_pending: true` · transcript present at **document** precision

Until E1 binds spans, every glance number must carry a **pending / overlay** chip. Shipping these numbers as if they were Exhibit 99.1 facts is a defect.

---

## 1. Information architecture

One Research OS, several lenses, one event object.

```
Earnings Command Center          (season / today)     [E11]
        │
        ▼
Company Event Workspace          (one event)          [E2]
   Brief │ Results │ Guidance │ Q&A │ Timeline │ Peers │ Sources
        │
        ├── dossier glance module                    [E2]
        ├── public Wire excerpt archive              [keep]
        └── Ask Mastermind (cited)                   [E2/E13]
```

Persistent while navigating an event: issuer, fiscal period, canonical event id, source-completeness chips, correction chip, authority `context_only`.

Source text vs analysis:

| Layer | Label in UI | Example |
|---|---|---|
| Source | “Transcript” / “8-K Exhibit 99.1” | IEX live quote with byte span |
| Deterministic | “Reported” | Revenue from the bound table |
| Overlay / inferred | “Wording not yet checked” | AAPL CI summary today |
| Model | “Cited analysis” | E12 only; never on Wire |

Ask Mastermind sits in the right rail of the Event Workspace (existing Terminal grammar), not a third header.

---

## 2. Ten surfaces — real-data hierarchy

Each surface answers: glance · evidence path · next research action · what persists · source vs analysis · deterministic vs inferred · Ask Mastermind.

### 2.1 Earnings Command Center — E11 (compose in E0, do not build)

- **Glance (1440):** “US reporting week · 16 Aug 2026” · freshness chip (calendar coverage **degraded** 17.9%) · “GOOGL printed Cloud +82% · AAPL printed devices + memory squeeze · N names still silent.”
- **Evidence:** tap a chip → that event’s Sources.
- **Next:** open AAPL Event Workspace.
- **390:** one column: today / needs attention / my watchlist. No heatmap.
- **820:** scoreboard + watchlist; waves in a second block.
- **Do not ship in E1/E2.**

### 2.2 Company Event Brief — E2 flagship

- **Glance:** `AAPL · Q3 FY2026 · 30 Jul` · state `partial` · “Devices ran hot; supply and memory are the constraint.” ≤14 words.
- **Stance:** Watch the Q4 supply commentary — do not treat overlay wording as the 8-K.
- **Evidence path:** each metric row → Sources rail (span or typed absence).
- **Next:** Results if the user wants numbers; Q&A if they want pressure.
- **Persists:** event id, completeness chips (transcript present · release missing · slides missing).
- **Ask Mastermind:** “What did Cook say about memory costs?” must return a locator or decline.

### 2.3 Results / Guidance — E2

- **Results glance:** Revenue $109.4B · +16% · GM 50.1%. Pending chip until E1 binds.
- **Guidance glance:** AAPL CI does **not** currently carry a structured guide. UI must show `typed_absence: guidance_item` rather than inventing a beat/miss.
- **IEX control (already live as source):** “Q3: 5–7% organic · adj. EBITDA 27–27.5% · adj. EPS $2.20–$2.25” as a **quote**, then E1 promotes to `guidance_item.v1`.
- **Next:** open Exhibit 99.1 table or transcript span.

### 2.4 Q&A Intelligence — E2 shell, E6 depth

- **Glance:** 14 questions (AAPL metric). Pressure tags from CI: supply, memory, FX — labelled **tags, not Q&A topics**.
- **Next:** open transcript search for “memory”.
- **390:** list of 3 hardest questions once E6 exists; until then, “Open transcript”.

### 2.5 Narrative Timeline / Commitments — E4

- **Glance:** tag timeline added/persistent (AAPL: `supply_constraints` added vs prior).
- **Honest empty:** `narrative_deltas: []` and no commitment ledger — show empty state, not fake history.
- **Next:** prior event Brief.

### 2.6 Peer / Read-Through Wave — E8

- **Glance:** “AI infra wave · GOOGL printed · AAPL printed · NVDA/TSM not in this workspace yet.”
- **Mechanism:** demand vs memory/foundry cost. Not “all peers bullish.”
- **Do not ship in E1/E2** except a disabled chip pointing at the golden wave note.

### 2.7 Global Search — E5

- **Glance:** one box. Scopes: this event · this issuer · corpus.
- **Today:** Terminal ticker transcript search only. UI must not advertise filings/slides.
- **Next:** open hit at segment.

### 2.8 Evidence / source rail — E2 (already a Terminal rail)

- **Glance:** three rows for AAPL today: history metadata · overlay metadata · transcript document.
- **Target after E1:** 8-K (cik, accession) · Exhibit 99.1 table cell · transcript spans · typed absences for slides/consensus.
- **Persists:** always visible at 1440; a drawer at 390.
- **IEX live proof** of the target grammar: claim id, kind, segment, byte span, text hash.

### 2.9 Dossier glance module — E2

- **Glance:** same 14-word stance as Brief. One row of 3 metrics. Completeness chips.
- **Forbidden:** leading with overlay summary once E1 claims exist.
- **Next:** “Open event” → Terminal workspace (existing deep link pattern from Wire).
- **390:** chips + one sentence + Open.

### 2.10 Mobile event research flow — E2

```
390:
  header: AAPL Q3 · partial · 30 Jul
  stance: Devices hot; supply/memory tight
  metrics: 3 numbers with pending chips
  tabs: Brief | Results | Sources | Transcript
  rail: Sources as bottom sheet
  Ask: icon in header, not a second nav
```

---

## 3. Breakpoints

| Width | Rule |
|---|---|
| 1440 | Workspace grid: main lens + evidence rail + Ask. Command Center three columns. |
| 820 | Rail becomes a collapsible column. Command Center two blocks. |
| 390 | Single column. Rail is a sheet. No hover. Touch targets ≥ 44px. Existing Terminal shell. |

Do not add a third global header. `nav_prefix` only.

---

## 4. Required states (every surface)

| State | How it looks on AAPL Brief | Honest copy |
|---|---|---|
| complete/current | All chips `present`; no pending | Not available today |
| partial | Today’s actual AAPL/LMND CI | “Partial · wording not span-checked” |
| stale | LMND: Wire is Q2, CI latest is Q1 | “CI behind the live call record” |
| corrected | Wire already has a banner template | “Corrected source revision” |
| conflicting sources | Release vs transcript number | Show both + typed conflict (E1 if seen) |
| blocked rights | Reserved, not mintable | Do not fake this chip |
| empty | GOOG CI 404 | “No event object for this listing” |
| provider down | API/R2 miss | Last-good + `degraded` |

Skeletons only while a bounded fetch runs. Never as a terminal state.

---

## 5. Interactions frozen for E2 screenshots

These are the E2 acceptance interactions (flagship AAPL):

1. Open Terminal `/analysis?symbol=AAPL&page=intelligence` → Brief shows Q3 FY2026, not an older quarter.
2. Click revenue $109.4B → Sources rail opens the bound span or typed absence (not a no-op).
3. Switch to Transcript → reader opens the same event’s body.
4. Switch to Sources → 8-K row present or explicit `not_ingested`.
5. Dossier module on `AAPL` stock page matches Brief stance and event id.
6. Repeat at 1440, 820, 390; EN and ZH; dark and light.

Until E1 lands, step 2 **must fail** on current production — that failure is the proof E2 is gated on E1.

---

## 6. What E0 is not

- No new CSS in `templates/` or Terminal.
- No Command Center page.
- No Peers/Slides lenses.
- Specimen HTML is a construction drawing, not a product route.
