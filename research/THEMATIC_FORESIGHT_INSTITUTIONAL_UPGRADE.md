# Thematic Foresight Desk — Institutional-Grade Upgrade Blueprint

*Build document, mid-2026. Successor to `THEMATIC_FORESIGHT_DESK.md` (the desk as shipped, phases 0–5).
This is the NEXT phase: how to make it actually intelligent and as close to institutional-grade
as free data honestly allows. Produced by a 5-stream research workflow (methodology / alt-data /
LLM layer / themes / rerating factors) + a skeptical-CIO red-team, with every redundancy claim
verified against the real repo. Free-data-first, display-only-first, forward-graded.*

---

## 0. The honest premise (governs everything)

The desk's own validated finding rules this document: **detection edge is ~0 and negatively skewed;
entry defers to the dislocation overlay.** Nothing here changes that. We are not building an alpha
machine. We are building a **structured-detection + thesis-maintenance machine** that knows *what to
look for*, surfaces a falsifiable thesis the moment a physical bottleneck forms, and tells you the
instant that thesis breaks — leaving *when-to-pay-up* to the existing dislocation/anticipation overlay.

The honest three-part answer to *"how is it intelligent / how do we front-run with no boots on the ground":*

1. **We genuinely CAN lead on a narrow class:** hard physical-capacity series (FRED cap-U,
   supplier-deliveries diffusion, transformer/turbine PPI, FERC/LBNL interconnection-queue depth, NRC/HALEU
   capacity) that physically precede revenue by quarters-to-years, **plus the synthesis+sizing+holding** of an
   underpriced concentrated bottleneck (the HBM mechanism). The edge is in thesis-construction and discipline,
   NOT in seeing secret inputs.
2. **We CANNOT replicate channel checks / expert networks.** GLG sells a *private, pre-filing* phone call.
   Every public feed below is *post-event*. What we build is a **public-trace CORROBORATION panel** —
   cross-source agreement to raise/lower confidence and catch breaks — explicitly LAGGED vs a real expert call.
   Honest win = breadth-of-corroboration + break-detection, not lead time.
3. **The "intelligence" is the grading loop + physical-correlate caps + cross-source agreement** — not a
   model's opinion. The LLM layer makes the desk *articulate and self-monitoring*, not *smarter about returns*.
   It extracts, structures, and refutes; it is **forbidden to forecast a price.**

House contract (unchanged): display-only first · `None`/`unknown` on shortfall · surface components+weights ·
append-only forward-grade vs SPY · no point-dates (bands/hazards only) · text-only capped at 50 without a
physical correlate · **crowding/attention is NEGATIVE.**

---

## 1. LEADING vs CONFIRMER taxonomy (pin to the wall)

The single biggest analytical error would be treating a coincident confirmer as a lead.

| Signal | Lead | Verdict | Plug-in |
|---|---|---|---|
| Physical-capacity series (cap-U, supplier-deliveries, PPI, queue depth) | 1–3q / yrs | **LEADING (core moat)** | T1 `bottleneck.py` |
| Supplier backlog / order book (NOT buyer capex) | 2–4q | **LEADING** | T2 re-point |
| Bottleneck language ("on allocation","sold out") | read at filing | **on-time + structured**, not early | T1 text leg |
| Govt contract-award surge (w/ obligation→revenue lag model) | 1–2q | **LEADING** | wire existing `usaspending` |
| Insider open-market CLUSTER buys (Form-4 code P) | wks–mos | short-lead **confirmer** | wire existing `altdata_models` |
| 8-K off-cycle guidance-raise language | days–1q | **LEADING (T3 language leg)** | NEW `guidance_gap.py` |
| Pricing-power language **+ margin/PPI confirm** | 1–2q | LEADING **only if physically confirmed** | extend `bottleneck.py` |
| SUE / PEAD breadth | print → 1–3q drift | coincident→short-lead | wire existing `sue.py` |
| Revision-breadth LEVEL **and its acceleration** | — | **COINCIDENT** (runway gauge) | T4 (do NOT relabel "leading") |
| Coverage count ↑ / dispersion ↓ | — | coincident→lagging | T4 |
| Options skew / IV term-structure | days, decayed | **entry-overlay confirmer only** | reuse #629 |
| Short-interest change | bi-monthly | confirmer / contrarian | risk overlay |
| Google Trends / retail attention | — | **CONTRARIAN at extremes** | underpricing axis (inverse) |
| ETF launches / 13F co-holding clusters | — | coincident→LATE | discovery (tag LATE) |

**Hard rule:** insider buys, options skew, short-interest, rising coverage are partly the *same* "informed
attention" factor. **Orthogonalize / correlation-penalize, never sum**, and make each **inverse to current
revision breadth.** Summing them re-prices crowding as conviction — the exact failure the house forbids.

**Decay discipline:** McLean–Pontiff — ~58% of anomaly alpha decays post-publication; Cremers–Weinbaum and
buyback drift have both weakened. Never hard-code historical effect sizes as current truth; let the
forward-grader auto-down-weight any leg whose graded hit-rate fades.

---

## 2. ⚠️ Build-vs-reuse audit (verified against the repo — do NOT rebuild)

The first research pass proposed 15 new engines. A repo audit found ~6 are **re-skins of existing
infrastructure**. Verified present:

| Proposed as "new" | Reality (verified) | Correct action |
|---|---|---|
| `insider_cluster.py` | `altdata_models.py:81` already fires `insider_cluster` (≥3 code-P buyers, wt 1.00); collector `sec_insider.py` exists | **thin theme-level adapter**, not an engine |
| `gov_awards.py` | `altdata_models.py` `gov_contract_accel` (≥2× off base) + `collectors/usaspending.py` keeps trailing-window obligations history | **adapter + add obligation→revenue lag model** |
| `sue_breadth.py` | `engine/sue.py` computes PIT seasonal-RW SUE, FDR-gated via `scripts/validate_sue.py` | **few-line theme rollup** of existing |
| `supplier_backlog.py` | `collectors/edgar_rpo.py` already extracts RemainingPerformanceObligation | **re-point `demand_capex` onto RPO**, not new |
| `analyst_agent.py` + `thesis_adversary.py` + `analyst_grader.py` | `engine/altdata_brain.py` is already an Opus extractor+judge with falsifiable ledger, track-record-in-prompt, and a **de-escalate-only code clamp** (the adversary pattern); graded by `ai_desk_scorer.py` | **reuse `altdata_brain` harness**, point it at foresight filings/theses |
| `discover_agent.py` + `etf_nport_cluster_discovery.py` | `theme_discovery.py` + `narrative_emergence.py` already do co-movement/change-point clustering of non-basket names + IPO clusters + emergence scoring, and hand a forming narrative to the AI desk as a falsifiable watch-hypothesis | **~70% built**; genuine net-new piece is only the EDGAR-phrase-velocity generator + probation gate |

**Net:** the genuinely net-new engines are far fewer than the first pass implied:
`guidance_gap.py` (T3 language leg), the FERC/NRC **queue** engine, `power_scarcity.py`, an EDGAR
**phrase-velocity discovery** generator, a **sizing+staged-exit** layer, and **PIT-grading rigor** plumbing —
plus *adapters* over the altdata/SUE/RPO infra above, and *one reuse* of `altdata_brain` for the analyst layer.

---

## 3. T3 explained + a real free build

**What T3 is:** the **guidance-gap** tier — the days-to-one-quarter window where *management's own forward
guidance surprises the bar the market set.* It sits between T2 (demand) and T4 (revision breadth). It's the
biggest free-data hole because the *clean* version needs a paywalled expectation series (Visible Alpha /
Estimize whisper): the true gap = *management guidance − forward whisper*.

**Why it leads:** the 8-K guidance sentence hits the wire first; the consensus revision (T4) is the lagged
response over the following days-to-weeks. So a guidance-language event at t0 mechanically leads T4 breadth.

**The real free build — `engine/guidance_gap.py`:**
- Source: keyless `efts.sec.gov` FTS, `forms=8-K`, custom dateRange; CIK→ticker via keyless `company_tickers.json`.
  Collectors `edgar_8k.py` + `edgar_fts.py` already exist.
- Two curated lexicons: RAISE (`"raising our guidance"`, `"now expects"`, `"above the high end"`, …) /
  CUT (`"lowering guidance"`, `"below our prior"`, …).
- **High-signal subset:** **off-cycle 8-Ks** (Item 2.02 filed *not* on the scheduled earnings date) = the
  company front-running its own print. Tag separately — the sharp piece.
- Output: per-theme band `CUTTING / NEUTRAL / RAISING / BROAD-RAISE` + distinct-raiser count + off-cycle flag.
  **Band only, never a point prediction.** ≥2 distinct filers before leaving NEUTRAL.
- **Inverse tell → `glut_watch`:** *beat but NO upward revision* (the 2026 AI-capex "profitability cap"
  pattern) = early exhaustion. Wire `GAP-CLOSING` into `glut_watch.py`.
- **Honest limit:** language-event-only is NOT the numeric gap. **Only the language leg is "closable" free;**
  the whisper side stays a paid skeleton. Lexicon matching misses hedged guidance — the LLM extractor (§5)
  later replaces blind keyword counts with a closed-form `guidance_hint` enum + verbatim citation.

**Additional rerating legs, ranked by edge-per-effort × free-PIT-validatability:**

| Rank | Leg | Lead | Free + PIT now? | Action |
|---|---|---|---|---|
| 1 | **T3 guidance-language** `guidance_gap.py` | days–1q | ✅ | **BUILD (net-new)** |
| 2 | **Insider cluster-buy** | wks–mos | ✅ | **WIRE** existing `altdata_models` channel as confirmer |
| 3 | **Govt award momentum** + obligation→revenue lag | 1–2q | ✅ | **WIRE** `usaspending` + add lag model |
| 4 | **SUE breadth** (FDR, PIT — survivorship is the killer) | coincident→drift | ✅ | **WIRE** `sue.py` rollup |
| 5 | **Pricing-power language** + XBRL margin-vs-PPI confirm | 1–2q | ✅ | extend `bottleneck.py`, text-capped |
| 6 | Coverage dynamics (count↑, dispersion↓) | coincident | ✅ | belongs in T4, not a new lead |
| 7 | Options skew / IV term-structure (reuse #629) | days | entry-overlay confirmer only | — |
| 8 | Short-interest change (FINRA) | bi-monthly | contrarian/risk overlay | — |
| 9 | Buyback authorizations (8-K) | decayed | combine with insiders only | — |

---

## 4. "No boots on the ground" — the public-trace corroboration map

Honest framing: a **corroboration panel** (cross-source agreement + break-detection), NOT a channel-check
substitute. Each tile tagged LEADING / CONFIRMER / CONTRARIAN and `awaiting`/`unknown` when offline.

**Truly free-keyless (build/wire now):** SEC EDGAR FTS (`efts.sec.gov`, language) · SEC XBRL frames
(`data.sec.gov`: RPO backlog, inventory, deferred-rev, margin, capex breadth) · USAspending v2 (pre-revenue
federal demand) · **FERC/LBNL interconnection queue** (`emp.lbl.gov/queues`, years of grid/power lead) ·
Form-4 (insider clusters) · FINRA short interest · 13F/N-PORT (discovery, tag LATE) · OEC BACI HS trade flows
(coarse demand proxy — **not** a supplier-customer graph).

**Free-with-key:** FRED (cap-U/PPI/supplier-deliveries — blocked in sandbox, lights up on CI) · EIA Open Data
(hourly RTO demand+price → `power_scarcity.py`) · UN Comtrade (monthly HS) · USPTO PatentSearch (**keyless shut
May-2025; now needs a key; ~18mo lag → slow T0, never an entry signal, low priority**).

**Paid → SKELETON only (free proxy where one exists):** ImportYeti/Panjiva bill-of-lading supplier→customer
graph — *the one true channel-check analog we cannot do free* (free proxy = aggregate HS flows = magnitude,
not the graph; say so on the page) · LinkUp/Revelio jobs (free proxy = BLS JOLTS macro-only; live-postings
scraping already rejected as unreliable) · Visible Alpha/Estimize whisper · earnings-call transcripts (8-K
Ex-99 recovers press-release only, **misses the Q&A where guidance color lives**) · ORATS/LiveVol IV surface.

**Explicitly infeasible free** (state plainly so the user stops hoping): satellite at useful cadence, AIS
history, clean per-company job postings, the numeric guidance gap, the supplier-customer graph.

---

## 5. The LLM "synthetic-analyst" layer — scoped to REUSE, not 6 new engines

`altdata_brain.py` already is: an Opus(reasoning)+Haiku(tagging) client (OAuth token → `ANTHROPIC_API_KEY`
fallback, graceful no-op without a key), evidence-pack → strict-JSON falsifiable thesis, append-only ledger
(`data/altdata/brain_theses.jsonl`), track-record fed back into the next prompt, and a **hard code clamp that
only lets the model DE-escalate** (built-in adversary). **Copy this harness; do not clone it three times.**

**The one load-bearing constraint:** Claude's training data contains the future relative to any historical
thesis, so a "forecast" can be memorized retrieval. Therefore:

> The LLM MAY extract dated, cited, closed-form claims; structure a mechanism-only thesis with pre-registered
> machine-checkable kill-criteria; and refute. It is **FORBIDDEN** to output a price target, return %, or
> directional bet. The deterministic engines + forward grader remain the only oracle of return-truth.

**Scope to TWO net-new engines:**

1. **`engine/analyst_extract.py`** (Haiku, citation-grounded, free-with-key). PIT filings (8-K 2.02/7.01+Ex-99,
   10-Q MD&A) → closed-form claim objects `{theme, ticker, accession, filing_date(=as_of), claim_type
   (sold_out|lead_time|pricing_action|capacity_add|guidance_hint|utilization), value_enum, verbatim_quote,
   char_span, confidence_enum}` → `data/analyst/claims.jsonl`.
   **Citation contract:** a deterministic post-validator re-opens the cached filing and **DROPS any claim whose
   `verbatim_quote` is not an exact substring at `char_span`** (RAG fabricates cites ~81% on SEC Q&A; exact-substring
   is the only reliable defense). **PLUS a sampled second-model/human SEMANTIC audit** — substring validation
   catches fabricated quotes but NOT a real quote misread (e.g. *"we do not expect to be supply-constrained"*
   parsed as a bottleneck). Negation/context errors survive substring checks.
2. **`engine/thesis_monitor.py`** (deterministic, **NO LLM**, runs daily). Re-evaluates each open thesis's
   pre-registered machine-checkable kill-criteria against the latest deterministic artifacts + newest validated
   claims → `{status: intact|weakening|BROKEN, triggered_criteria[], days_open}`. Drives the **THESIS BROKEN**
   chip, fires *before* the tape confirms, keeps the expensive LLM out of the daily loop (cost + reproducibility).
   Unverifiable criteria → `UNVERIFIABLE`, never silently `intact`.

**Reuse (not rebuild)** for the thesis-synthesis + adversary + grader roles: `altdata_brain.py` harness +
`ai_desk_scorer.py`. The "what am I not looking at" discovery agent reuses `theme_discovery`/`narrative_emergence`
output; the only net-new generator is `edgar_phrase_velocity_discovery.py` (§6).

**Cost/repro:** ~30 themes × (1 Haiku batch/~6 filings) + cached-Opus synthesis = low-tens-of-cents/build IF
prompt-caching the stable glossary/rubric system blocks + a hard per-build call cap. Claims/theses logged at
fire-time with immutable `as_of`; only the deterministic monitor/grader touch them afterward → **the published
track record is reproducible from the ledger even though generation isn't.** Pin model id, temp=0. Every LLM
engine degrades to `None` and lets the deterministic cascade run unchanged when no credential — **the desk must
be fully functional with the LLM disabled.** Do NOT revive the deferred FinBERT/Word2Vec stack — a citation-grounded,
refusable, gradeable claim object beats a fixed-label sentiment classifier and adds no torch dependency.

**What the LLM is honestly worth:** articulation + self-monitoring + faster structuring + break-detection. It
adds **zero return-alpha** (its own constraint). Sell it as *"knows what to look for and tells you the moment a
thesis breaks,"* never as the highest-leverage addition.

---

## 6. More themes + systematic discovery

**Admission rule (so the desk doesn't bloat to a hand-curated 40):** a theme is admitted ONLY with a passing
physical-bottleneck read; cap at 50 until T1 lights up; weight members by **revenue-purity** (% revenue from the
theme, from 10-K segment text) NOT market-cap (avoids the ARK mega-cap-contamination failure); forward-grade
before display prominence.

**Highest-conviction adds (each has a nameable choke-point + a free bottleneck signal):**

| Theme | Members | Free bottleneck signal | Note |
|---|---|---|---|
| **gas_turbines** (gas-for-AI) | GEV, CW, CMI, PWR (+ Siemens/Mitsubishi watch) | EDGAR backlog/slot-reservation language + turbine PPI | Cleanest verifiable sold-out backlog (~to 2030). Not in `data_center_power`. PRECIPICE-grade. |
| **grid_hardware** (transformers/switchgear/HVDC) | ETN, HUBB, GEV, NVT, PWR, CLF (GOES) | **LIVE keyless FRED** `PCU335313335313`/`PCU335311335311P` + EDGAR lead-time velocity | Split from `grid_electrification`. 128–144wk lead times; GOES single-source CLF (concentration tell). Lights up TODAY. |
| **advanced_packaging** (CoWoS/ABF/glass) | TSM, AMKR, ASEH, CAMT, ONTO, KLAC, AEHR | EDGAR CoWoS/substrate-capacity phrase velocity | Split from `ai_semiconductors`. Packaging throughput, not logic die, is the binding constraint. Purity LOW (best plays foreign-listed). |
| **haleu_enrichment** | LEU, OKLO, SMR (+ CCJ/UEC/UUUU upstream) | EDGAR SWU/HALEU capacity + DOE award language | Split from `nuclear_power`. Enrichment leads reactors by years. Require a filed capacity number, not an LOI. WATCH cap 45 until deliveries. |
| **humanoid_actuators** | RRX, AME, ALNT, MP, USAR | Magnet export-license event flags + EDGAR roller-screw/actuator language | Split from `robotics_automation`. Ceiling is upstream (NdFeB ~90% China refining; roller screws acutest). Pre-revenue/hype — purity LOW, hold WATCH. |

**Secondary candidates (own probation, not merged baskets):** co-packaged optics (COHR/LITE/FN/CRDO),
liquid cooling (VRT/NVT/MOD), titanium (ATI/HWM/CRS), peptide-CDMO (WST/STVN), munitions (LMT/NOC/KTOS),
submarines (HII/GD/BWXT — welder bottleneck), Ga/Ge/Sb (NB/PPTA/UAMY — China ban to Nov-2026). **Tag the
well-traded/coincident ones LOW edge-remaining** (merchant IPPs VST/CEG/TLN, custom-ASIC AVGO/MRVL, stablecoins
CRCL/COIN). **Catalyst/event themes (license-expiry, GENIUS enforcement) are hazard flags, not standing PRECIPICE
reads** — respect no-point-date.

**Systematic discovery (stop being a hand-curated 18) — probation pipeline, not a publish button:**
1. **`engine/edgar_phrase_velocity_discovery.py`** (net-new, free-keyless) — z-score per-quarter velocity of
   supply-stress vocabulary by NAICS/SIC over EDGAR FTS; a spike in a cluster with no existing theme = candidate.
   Literally how HBM would have surfaced. Require velocity-z AND cross-firm breadth; display-only; ≤50 cap on text alone.
2. **`theme_discovery` / `narrative_emergence`** (reuse) — co-movement clustering of non-basket names + IPO clusters.
3. The LLM **names + structures** the anomalies these surface — it never ideates from world-knowledge (a 2026
   model asked "what's the next theme" just returns 2025's winners). Candidate → probation → promoted only when its
   one pre-registered physical correlate fires → forward-graded.

---

## 7. `site/foresight.html` — making it read as an institutional terminal

1. **Thesis card with kill-criteria + variant perception** — lead each card with *what we believe that consensus
   doesn't, and the specific observation that would kill it* `{claim, evidence_legs[], falsifier, confidence_tag}`.
   No physical leg ⇒ render *"no variant perception — text-only"*, never fabricate one (ties to TEXT-ONLY CAP).
2. **LLM analyst note, per theme** — `analyst` thesis sentence (mechanism only) + `contested`/`robust` badge +
   **THESIS BROKEN / WEAKENING / INTACT chip** from `thesis_monitor`. Every claim links to its **verbatim quote +
   EDGAR accession** (citation drill-down). Biggest "feels like a desk" upgrade.
3. **Evidence drill-down** — click a leg → underlying claims (quote+accession+date), FRED series, award records,
   insider cluster. Provenance visible (house "surface components" rule).
4. **Alt-data corroboration tiles** — power-scarcity gauge (EIA+LBNL), award-surge band, insider-cluster band,
   guidance-tilt band, supplier-deliveries band; each tagged LEADING/CONFIRMER/CONTRARIAN.
5. **Attention 2×2** — bottleneck-tightness × attention-level → PRECIPICE/RE-RATING/GLUT-RISK; makes the
   attention-penalty visible as a position on a map.
6. **Discovery feed** — probation candidates: theme, defining filers, the one physical correlate watched,
   days-in-probation, whether it fired. The page literally answering *"what should I be looking at that I'm not?"*
7. **Track-record rigor** — publish grader slices by `{robust vs contested, physical_confirmed, n_claims}`,
   with `n_pending` shown honestly while theses mature, no efficacy claim until graded.

---

## 8. Prioritized roadmap (re-weighted per red-team: physical core first, then honesty, then T3, then sizing)

Tags: **[FK]** free-keyless · **[Fk]** free-with-key · **[PS]** paid-skeleton · **S/M/L** · **LEAD**/**CONF**.

**Phase A — harden the physical core (the only real lead; cheapest genuine edge):**
- Make `bottleneck.py` production-grade on HARD series: supplier-deliveries/new-orders diffusion (FRED + regional
  Fed), transformer/turbine PPI velocity. **[Fk] M · LEAD.**
- **NEW `engine/queue_pipeline.py`** — FERC/LBNL interconnection queue + NRC/HALEU capacity dockets as a
  YEARS-of-lead engine (the single best free physical lead for power/grid/nuclear; its own engine, not a row). **[FK] M · LEAD.**
- **NEW `engine/power_scarcity.py`** — EIA RTO demand+price; feeds `bottleneck.py` where FRED is sandbox-blocked. **[Fk] M · LEAD.**
- Re-point T2 to **supplier backlog** via existing `edgar_rpo.py` (Cooper–Gulen–Schill: buyer capex predicts
  NEGATIVE returns; supplier backlog leads its own revenue — a directional fix). **[FK] M · LEAD.**

**Phase B — PIT forward-grading rigor (makes the track record not a lie; do BEFORE adding legs):**
- PIT basket-membership (when did a name JOIN the theme), dead-name/survivorship handling, **cross-theme FDR**
  across all legs. Without these the grader over-reports hit-rates. **[FK] M.**

**Phase C — the real T3 + wire existing altdata as confirmers:**
- **NEW `engine/guidance_gap.py`** (language-event-only; off-cycle Item-2.02 subset; GAP-CLOSING → `glut_watch`). **[FK] M · LEAD.**
- **Adapters** (not engines) wiring existing `altdata_models` insider-cluster + gov-award + `sue.py` rollup into
  `foresight_cascade` as **confirmer** legs, correlation-penalized + inverse-to-breadth. Add contract
  **obligation→revenue lag model** on `usaspending` history. **[FK] S each · CONF.**
- New themes `gas_turbines`, `grid_hardware` (grid_hardware lights up on keyless FRED today). **[FK] S each · LEAD.**

**Phase D — sizing + staged exit (the edge detection can't provide; where HBM actually won / ARK lost):**
- **NEW sizing layer** — position size ∝ bottleneck-tightness × dislocation-depth (vol-targeted), max-theme
  concentration, and an **"effective number of independent themes"** decomposition (memory/packaging/power/grid/
  semicap/turbines are largely ONE hyperscaler-capex bet). **[FK] M.**
- **Forced de-risk rule** when GLUT-RISK + extreme-attention co-occur, graded vs hold (fixes the ARK no-trim failure). **[FK] S.**

**Phase E — LLM synthetic-analyst layer (articulation + break-detection; reuse, don't clone):**
- **NEW `analyst_extract.py`** (Haiku, exact-substring citation contract + sampled semantic audit). **[Fk] M.**
- **NEW `thesis_monitor.py`** (deterministic, no-LLM, THESIS-BROKEN chip). **[FK] S · LEAD.**
- Reuse `altdata_brain.py` harness + `ai_desk_scorer.py` for synthesis/adversary/grading. Page: thesis cards,
  citation drill-downs, contested/robust badges.

**Phase F — systematic discovery + confirmers + paid skeletons:**
- **NEW `edgar_phrase_velocity_discovery.py`** + probation gate (reuse `theme_discovery`/`narrative_emergence`). **[FK] M · LEAD.**
- New themes `advanced_packaging`, `haleu_enrichment`, `humanoid_actuators` — admit only on a passing bottleneck read. **[FK] S–M.**
- Short-interest change, options skew (reuse #629), buyback auths — confirmers/overlays only. **[FK/Fk] S.**
- Paid skeletons (light up if a key arrives): ImportYeti/Panjiva supplier-customer graph, LinkUp/Revelio jobs,
  Visible Alpha/Estimize whisper, transcripts, ORATS IV surface. **[PS].**

---

## 9. The one-paragraph reconciliation (give to the user verbatim)

We will never have a person in the fab. What we will have: **(a)** a *leading* core that reads hard physical-capacity
and queue series straight out of primary documents, quarters-to-years before estimates move — the HBM mechanism,
free and real; **(b)** a public-trace corroboration panel (sold-out language, awards, queues, insider clusters,
customs flows) — honestly LAGGED vs an expert call, valuable for cross-source agreement and break-detection, with
the supplier-customer graph the one thing we genuinely can't buy free; **(c)** a real free T3 guidance-language leg
plus the validated rerating confirmers we mostly *already have* and just need to wire in; **(d)** an LLM synthetic
analyst that is intelligent in exactly one way — it knows what to look for, structures every thesis with
pre-registered kill-criteria, refutes itself, and tells you the moment a thesis breaks — while **forbidden to
forecast a single price**; **(e)** a discovery pipeline so themes grow themselves from anomalies, on probation,
promoted only when a physical correlate fires; and crucially **(f)** sizing + staged-exit discipline, because the
HBM win and the ARK failure were both about sizing and trimming, not detection. The intelligence is in the grading
loop, the physical-correlate caps, and cross-source agreement — not a model's opinion about the future. That is the
honest, buildable institutional grade.

---

*Provenance: 5-stream research workflow + skeptical-CIO red-team, mid-2026. Redundancy claims verified against the
live repo (`altdata_models.py`, `altdata_brain.py`, `sue.py`, `usaspending.py`, `edgar_rpo.py`, `sec_insider.py`,
`theme_discovery.py`, `narrative_emergence.py`). Supersedes the first-pass blueprint's effort accounting.*
