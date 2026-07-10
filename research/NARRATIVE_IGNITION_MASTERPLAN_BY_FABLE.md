# Narrative Ignition Program — masterplan (W0) — NAR-R1..R14

**Status:** ADJUDICATED MASTERPLAN (Fable, 2026-07-10). Program id: `narrative-ignition`.
**Trigger:** the META 2026-07-09 miss — SemiAnalysis "Future of Meta Superintelligence" + Citrini
+ KOL cascade flipped the mega-cap narrative in ~24h; no radar, hub, or board surfaced anything.
**Method:** 11-lane recon (6 repo census + 5 external research), 3 independent Opus designs under
distinct priors (deterministic-maximalist / intelligence-desk / market-confirmation-first),
2-judge adversarial panel (house-law lens + practical-alpha lens), Fable adjudication.
Recon and design transcripts: session artifacts 2026-07-10 (wf_138fc517, wf_24debe17).

---

## 1. The forensic finding that anchors everything

The META miss was **NOT a data gap**. Verified against committed artifacts:

| Evidence (all present, all stored) | Where | When |
|---|---|---|
| 12 consecutive alt-data convergence alerts (7 HIGH; 4-channel HIGH on the eve) | `data/altdata/alerts.jsonl` | 06-20 → 07-08 |
| HuggingFace model-momentum channel firing repeatedly (100M+ dl/mo, +8.1% WoW) | `site/altdata/feed.json` | all window |
| GEX regime flip to long; call wall 700; upside trigger 650 | `data/cboe/gex_META.parquet` | 07-01 |
| +8.7% blowout on 45.5M vol (3x norm); candidate DCL 06-25 at $542.87 | price store | 07-01 |
| $511.67M net call premium, top prints all call buys (600/620/700C) | `data/options_flow/summary_META.parquet` | 07-09 |
| Anticipation index 64.9 (high), 7 go-legs | `site/anticipationdata/META.json` | 07-08 |

What failed:

1. **No persistence aggregation.** 20 days of multi-channel flaring never compounded into any
   state. `site/altdata/mastermind.json` sat at `action: WATCH, direction: neutral` the whole
   window; the alerts fired daily and evaporated daily.
2. **No narrative ingestion.** SemiAnalysis / Citrini / the 07-01 Morgan Stanley "neocloud"
   reframe appear in **zero** artifacts before 07-09. `site/stockbrief/META.json` was
   `degraded_reason: no_context`. The news surface had only post-event headlines.
3. **No surfacing.** The US intel hub has no dedicated page (unlike `china_intel.html`); the
   alt-data alert reached `alerts_triage` at priority 60 and was never seen.
4. **Mechanical gates correctly held rank** (HTF-MACD unconfirmed, earnings blackout T-19,
   RS laggard 42/45) — defensible by their own rules, but no surface existed to say
   "narrative-regime candidate; the mechanical gates structurally lag this class of event."

**Miss classification: aggregation + persistence + surfacing failure, plus a narrative-channel
ingestion gap.** The design must fix the first three with the tape we already have, and add the
narrative channel as confirmation-of-WHY — not depend on it.

## 2. External research digest (what the build stands on)

- **Novelty is the alpha carrier; repetition is echo.** RavenPack: filtering to first-hit novelty
  (ENS=100) or similarity-gap >90d restores the alpha naive sentiment studies can't find
  (Sharpe 1.03→1.43 on R2K). Event-Buzz (article-count z vs 90d baseline) × novelty × relevance
  is the institutional workhorse construct.
- **Change, not level.** Sentiment/attention momentum (first derivative) predicts; levels don't
  (raw-level R²≈0.0006). Attention LEVEL is crowding hazard (consistent with house R-TIL-4).
- **Horizons exist for a nightly system.** Large-cap narrative drift persists 4–8 weeks via the
  analyst-revision channel; news-driven momentum ~1 week (large caps) to 4–6 weeks (post-headline
  drift). Retail attention spikes (SVI/wiki) = ~2 weeks continuation then reversal — and are
  small/mid-cap phenomena; StockTwits attention *negatively* predicts for large caps.
- **Case anatomy (8 rips reconstructed):** earnings-call phrase novelty leads by 1–3 quarters
  (PLTR AIP, APP AXON, ORCL RPO); supply-chain breadcrumbs 4–8 weeks (NVDA, SMCI); KOL/newsletter
  crystallization 1–14 days (META, VST/CEG); pure-KOL rips 24–72h (DeepSeek, quantum). META was a
  **synthesis rip**: public facts for weeks, crystallization sudden. The tape confirmed same-day.
- **Fusion math for "one credible source vs consensus":** intelligence/fraud/ensemble fields all
  converge on *source track record as a Bayesian prior* (Beta-Bernoulli per-source hit rate,
  Admiralty-code pattern), novelty gates, burst detection (Kleinberg), CUSUM persistence
  (Lorden-optimal spike-vs-takeover), and **cross-modal confirmation** (price/volume/options —
  the one channel a coordinated-inauthentic campaign cannot fake on day one).
- **Data that backfills for calibration TODAY:** Polygon news (2016→, we already pay),
  Wikipedia pageviews (2015→, already collected in `data/attention/`), HN Algolia (2007→),
  EDGAR FTS (2001→). Substack RSS / podcasts are forward-only. X API is cost-prohibitive
  ($42k/mo full archive) — the KOL signal is captured cheaper via newsletter RSS + HN.

## 3. Adjudication record

Three designs, two judges; both judges independently ranked **Market-First (flare-persistence
organ)** first (8.6 and 8.0 weighted), because its theory-of-the-miss matches §1's ground truth.

**ADOPTED skeleton:** `flare_persistence.v1` (FPO) — a persistence-aggregation organ over
already-stored tape witnesses, with a DORMANT→PRIMED→ARMED→CONFIRMED-CANDIDATE→FADING ladder.

**GRAFTED:**
- Page-CUSUM as the persistence engine (from deterministic design) — replaces a loose
  "≥3 sessions" counter with Lorden-optimal spike-vs-takeover discrimination.
- Pre-registered null honesty + SIR-deceleration posture (from deterministic design), verbatim
  in §9.
- Side-by-side **Flare read vs Hub read** reconciler display, never fused (from analyst-desk
  design; CITR-5 contradiction-record precedent).
- Deterministic novelty leg — but **TF-IDF-cosine vs trailing corpus + similarity-gap days**, not
  neural embeddings (respects the standing FinBERT/Word2Vec rejection: no torch-class dependency;
  neural embedding novelty may be proposed later as its own pre-registered leg).
- Cortex post-fire WHY-blurb + A3 de-escalation AND-ed with deterministic screen (R-AUT-1 shape).

**REJECTED (both judges concurring; DO_NOT_REBUILD rows appended in this PR):**
1. **LLM frame-tag classification feeding any organ state** (analyst-desk Leg D). Runtime
   per-document LLM bin-assignment whose output moves an escalation-eligible state is TI-R1 /
   CONST-ART1 origination; the char-span receipt validates the *quote*, not the *classification*.
   Frame reclassification ships only as R-TIL-5 receipt-validated display annotation. The frame
   construct itself (the actual META mechanism) belongs to the RUL-C5 narrative-arbitration
   come-back (~2026-10-01) — deferred, not forgotten.
2. **Chatter-only promotion to the top state** (any credibility-alone / C_s-alone escalation).
   Cold-start credibility is inert exactly when needed, and a pre-tape fire is a chatter-only
   escalation. Cross-modal tape veto is unconditional (NAR-R2). Single credible flare = high
   *salience* (ARMED, on the radar, alert-eligible), never high *authority*.
3. **Seeding source credibility from curated historical calls** — survivorship-prone small-n
   origination. Skeptical seed only; credibility is earned forward from the graded ledger.
4. **Reading `intel_hub` opportunity_score / dossier composites as FPO inputs** — RUL-N2
   (consuming another organ's escalation). FPO reads raw measurable legs only (alert channel
   bits, net-call-premium z, GEX regime bit, counts). CI assertion in W1.
5. **GDELT DOC as a live leg** — stays coded-but-dark (stale phantom −1.0 defect, 3-month window
   can't build a baseline). Unchanged from the news-feed audit.
6. **BOCPD / narrative-regime dating in the nightly path** — that is narrative-vs-price
   arbitration territory (RUL-C5 no-build before ~2026-10-01). Offline retro study only.

**Also ruled here:** public-tier Substack RSS polling (titles/teasers of public posts, keyless,
no auth, no paywall circumvention) is **legal** under R-TIL-9 as a new public-trace leg via a
PR-reviewed feed registry. The **Citrini feeds are excluded** — Citrini ingestion is owned end-to-
end by the CITR program (`research/CITRINI_HANDOFF_FOR_NEW_SESSION.md`) and its operator gates.

## 4. Architecture (what ships)

All new organs: authority block `tier=display, may_rank=False, may_gate=False, may_size=False`;
synapse-registered; bilingual surfaces; off the 67-min render path except the cheap organ pass.

**4.1 `flare_persistence.v1` (FPO)** — `engine/flare_persistence.py`, hooked in
`scripts/build_baskets.py` beside `mtf_upturn.py` (TS-U2 pattern, the ratified new-organ
template). Per US ticker nightly, reads **raw measurable tape witnesses** (each a binary
present/absent bit + printed magnitude; never a weighted score — FT-R3 shape):

- T1 alt-data convergence: ≥3 channels on a HIGH alert day (`data/altdata/alerts.jsonl` bits)
- T2 options net-call-premium z ≥ 2 vs own 90d baseline (`data/options_flow/summary_*.parquet`)
- T3 GEX regime long AND flipped within window (`data/cboe/gex_*.parquet` regime bit)
- T4 news-sentiment bull_ratio z ≥ 2 (`data/polygon/news_sentiment.parquet`)
- T5 analyst-revision velocity (from W2 accrual; joins when history exists)

State ladder (own-evidence K-of-N, RUL-N2-clean):
- **PRIMED**: ≥2 tape witnesses with CUSUM persistence (S⁺ = max(0, S⁺+z−0.5), fire at h=5) —
  the "12 straight days of flaring" detector META needed.
- **ARMED**: PRIMED + ≥1 narrative witness (4.2) — confirmation-of-WHY.
- **CONFIRMED-CANDIDATE**: ARMED + cross-modal confirmation (vol_ratio>1.5×20d OR |ret|>0.5σ) —
  the unconditional anti-manipulation veto (NAR-R2).
- **FADING**: witness decay / mention-velocity second derivative < 0 (SIR-deceleration posture:
  peak virality = overbought-on-narrative; card copy flips to caution).

Artifacts: `site/stockdata/flare_persistence.json` + PIT `data/flare_persistence/state_hist.parquet`.

**4.2 `narrative_flare.v1` (NFO)** — collect-lane (`collectors/narrative_sources.py` →
`engine/narrative_flare.py`). Deterministic math on keyless feeds (TI-R1-legal: counts/z/burst on
measurable data): per-ticker news-count z (Event-Buzz analog, Polygon counts, PIT baselines
≤T−1, robust median/MAD, MIN_BASELINE_OBS=30, young-series excluded); similarity-gap
(days-since-prior-coverage, >90d = novel); TF-IDF-cosine novelty vs trailing 90d headline corpus;
Kleinberg burst (s=2, γ=1) per source channel; first-coverage-in-source flags (a graded source
covering a ticker for the first time in 90d). Output: per-ticker `narrative_witness`
(present/absent + magnitudes + join-confidence). Wiki/HN velocity computed but carried as
**crowding-hazard context** for large caps (R-TIL-4), and as reversal-frame for small caps (§9).
Every row stores `fetch_date` AND `published_date`.

**4.3 `source_registry.v1`** — per-source Beta-Bernoulli credibility
(`cred = (hits+2)/(calls+2+5)`, skeptical seed), updated ONLY by the nightly deterministic grader
from resolved qledger claims (`narrative_source_call` family: did the covered name move
|excess| > threshold within 20d of first coverage — unsigned resolution, graded not trusted).
Feed registry `config/narrative_sources.yml` is PR-reviewed curation (TI-R2-legal taxonomy).

**4.4 Surfaces & alerts** —
- **Narrative Radar** strip on `us_stocks.html` (client-fetch like mtf_upturn): rows ordered by
  state then persistence-days; each card shows the lit witnesses, as-of, crowding-hazard
  percentile, join-confidence, source credibility of the driving flare, and — per the
  over-trading hazard — **the mechanical blocking reasons printed beside the arming state**
  (earnings blackout, RS rank, gate status), so salience never masquerades as a buy signal.
- **Flare vs Hub side-by-side**: two independent display columns (FPO state | intel_hub read);
  divergence itself is the insight; never fused, `may_rank=False`.
- Standout-card chip when a board name is also ARMED+ (parallel display column).
- Discord alert on ARMED→CONFIRMED-CANDIDATE via `notify_turn_events.py` (FT-R13 copy contract:
  state name, evidence legs, as-of, T+1 fade base rate, no direction verbs; once per subject/day).

**4.5 LLM contract (NAR-R4)** — zero LLM anywhere in the detection/state/alert path. Allowed:
(a) Haiku extraction-with-receipts for entity→ticker joins on RSS/HN text (R-TIL-5: verbatim
quote + char_span, deterministically validated, reject on mismatch) — W7, after the deterministic
alias-table join ships first; (b) cortex WHY-blurb after a deterministic fire
(`is_context_only=True`); (c) A3 de-escalation of the (future) calibrated key, AND-ed with a
deterministic screen. All via `engine/llm_auth.make_call()`. No new QS-U2 budget consumption.

## 5. The reconciliation doctrine (the operator's direct question)

The hub's consensus weighting is not the enemy — it answers "how crowded/mature is this trade?"
The flare channel answers a different question — "did something just change?" — and needs
different evidence *in kind*, not more of the same evidence:

1. **Source track record replaces source count.** One graded, high-credibility source
   (SemiAnalysis after its ledger fills) satisfies the narrative leg alone. A no-track-record
   viral account contributes ~nothing (skeptical Beta seed). Nobody votes; sources are graded.
2. **Novelty replaces agreement.** First-frame/first-coverage fires; the 40th echo article is
   worth less than the 1st, exactly inverse to consensus logic.
3. **Cross-MODAL confirmation replaces cross-source confirmation.** The second key is the tape
   (volume/price/options) — independent of the chatter channel and unfakeable by coordinated
   posting. Chatter alone never reaches candidate state (NAR-R2).
4. **Persistence replaces intensity.** CUSUM accumulation catches 20 quiet-flare days
   (META) that no single-day threshold sees, and ignores one-day spikes that revert.
5. **Salience ≠ authority.** The fast channel gets a loud display + alert lane immediately
   (display tier ships freely); rank/gate influence is earned through the same gauntlet as
   everything else. The hub keeps its job; the radar gets its own lane; the side-by-side view
   makes their disagreement — the actual information — visible instead of averaging it away.

META replay under this design: **PRIMED from ~06-20** (T1 persistence via CUSUM), radar-visible
daily with rising persistence-days; **ARMED 07-01** (GEX flip + news-count z on the Morgan
Stanley neocloud story) with alert; **CONFIRMED-CANDIDATE 07-09** ($511M call session =
cross-modal confirm; SemiAnalysis first-coverage lights the flare leg once RSS accrual exists);
blackout/RS blockers printed alongside throughout.

## 6. Data plan

**W2 (keyless / already-paid, BUILD-NOW):** Polygon news-count per-ticker daily store +
one-shot 2016→ backfill (off-render); Wikipedia pageviews z (reuse `data/attention/` +
`wiki_attention_phase0.py` math; extend universe); HN Algolia counts/points for tech names;
EDGAR 8-K velocity per CIK (reuse `collectors/edgar_fts.py` plumbing); public Substack RSS
poller over `config/narrative_sources.yml` (SemiAnalysis, Doomberg, et al; **no Citrini** —
CITR program owns it; forward-only, start day 1); yfinance analyst snapshot **append-only
accrual** → PT-revision velocity after ~4 weeks of history.
**Operator-gated (listed, not built):** Tiingo Power $10/mo (12y cross-validation backfill);
FMP $15/mo (historical PT-revision velocity now instead of in 4 weeks); Google Trends official
API application; podcast RSS + local Whisper (compute-only, later wave). **SKIP:** X API
(cost), Reddit/StockTwits (API access dead/paused 2026), GDELT DOC live leg (dark).

## 7. Wave plan (each = one PR, branch off fresh origin/main, same-day squash-merge)

| Wave | Build | Notes |
|---|---|---|
| W0 | this masterplan + DO_NOT_REBUILD rows | this PR |
| W1 | FPO spine: `engine/flare_persistence.py` (tape witnesses T1–T4, CUSUM, ladder w/o narrative leg) + PIT history + authority block + synapse reg + tests | sonnet build; CI assert: no intel_hub composite reads |
| W2 | `collectors/narrative_sources.py` + PIT stores + Polygon backfill job + analyst-snapshot accrual + feed registry | collect lane only |
| W3 | NFO math (`engine/narrative_flare.py`): news-z, similarity-gap, TF-IDF novelty, Kleinberg, join-confidence; deterministic alias-table entity→ticker join | |
| W4 | `source_registry.v1` + qledger `narrative_source_call` + `narrative_flare_state` claim families (21d/63d grades) | skeptical seed only |
| W5 | ARMED + cross-modal veto + FADING/SIR + small-cap reversal frame + crowding read | opus review on the veto gate |
| W6 | Narrative Radar strip + Flare-vs-Hub view + standout chip (EN/ZH) | mockups-first; browser-verified w/ prod-shaped data |
| W7 | Discord alert lane (FT-R13) + dedup | |
| W8 | LLM waves: R-TIL-5 char-span join (Haiku, news_llm consumer registration); cortex WHY read-tool | opus review |
| W9 | Calibration freeze: backfilled baselines, threshold pre-registration record, **META replay harness** asserting §5's replay against stored artifacts | opus review |

## 8. Rulings (NAR-R1..R14)

- **NAR-R1** — FPO/NFO compute their own K-of-N states from their own evidence legs; no
  consumption of another organ's escalation or composite (restates RUL-N2). Tape witnesses enter
  as binary present/absent bits with printed magnitudes, never weighted scores (restates the
  positioning-fusion ban; FT-R3 shape).
- **NAR-R2** — the cross-modal price/volume/options veto is an unconditional gate below
  CONFIRMED-CANDIDATE. No chatter-only candidate, regardless of source credibility.
- **NAR-R3** — source credibility is earned exclusively from the graded forward ledger, seeded
  skeptically (Beta α=2, β=5). No hand-set weights, no historical-call seeding. The tape-
  persistence path is the primary catch mechanism; the credibility-flare path is a forward-
  accruing enhancement — this asymmetry is the correct epistemic posture, not a defect.
- **NAR-R4** — LLM roles: R-TIL-5 receipt-validated extraction, post-fire explanation
  (`is_context_only`), A3 de-escalation AND-ed with a deterministic screen. No origination, no
  frame→state, no shock-type classification into calibrated keys (TI-R1), zero LLM in the
  detection/state/alert path.
- **NAR-R5** — display-only until CONFIRMER (n_dates≥25, Wilson CI-low>0 vs matched control,
  DT-R14 **time-preserving** inference — never ticker-cluster CIs). Nulls printed; on a null the
  organ is retained as confluence/context input (context-accrual law), never silently removed.
- **NAR-R6** — no narrative-vs-price arbitration grader, no story-decay curves, no BOCPD
  regime-dating in the nightly path (RUL-C5/C6 come-back ~2026-10-01 owns those questions).
- **NAR-R7** — attention legs carry the crowding-hazard read on every card; below a
  market-cap/liquidity floor they flip to a reversal/hazard frame and can never arm continuation
  (R-TIL-4, Da/Cookson small-cap literature).
- **NAR-R8** — every radar card prints the mechanical blocking reasons (blackout, RS rank, gate
  state) beside the arming state. Display salience must never manufacture conviction the
  gauntlet has not granted (GAP-U8: display-only ≠ weak-but-usable).
- **NAR-R9** — entity→ticker joins print join-confidence on every narrative witness; the
  deterministic alias-table join ships before the LLM-assisted join; a mis-join must be visible,
  not indistinguishable from a real flare.
- **NAR-R10** — stale feeds drop the leg (witness absent + staleness printed); never inject a
  phantom value (the GDELT −1.0 lesson).
- **NAR-R11** — public-tier RSS polling via the PR-reviewed feed registry is legal (R-TIL-9);
  no auth, no paywall circumvention, no credential handling; Citrini feeds excluded (CITR
  program property).
- **NAR-R12** — alert copy per FT-R13: state name, evidence legs, as-of, T+1 fade base rate, no
  direction verbs; alerts read already-computed states only.
- **NAR-R13** — rolling IC of the qledger families is tracked and printed (adoption/decay
  monitoring per Lopez-Lira); decay is surfaced, not hidden.
- **NAR-R14** — frame-shift detection (the "capex-liability → AI-winner" reclassification
  construct) is explicitly deferred to the RUL-C5 come-back with this program's accrued corpus
  as its substrate. The deferral is recorded so the sharpest construct is not lost.

## 9. Pre-registered honesty (expected nulls & failure modes)

- Prior: **narrative rank-IC ≈ 0 for large caps as a standalone ranker** (news resolves in days
  for mega-caps). FPO may end display-only forever; that outcome is acceptable and pre-declared —
  its job is salience and context accrual first (the META miss was salience, not rank).
- Retail-attention legs (wiki/HN) may show zero standalone signal — retained as confluence.
- Cold-start: the flare leg is under-powered until the source ledger fills (~25 resolved calls
  per source). Stated on the surface (`accruing` badge), not hidden.
- Small-cap attention = pump/reversal regime; handled by NAR-R7, never continuation-armed.
- SIR-peak: deceleration flips posture to FADING/caution; acceleration, not virality, arms.
- Entity-join errors are the silent failure point; NAR-R9 makes them visible.
- Over-trading: NAR-R8. The radar tells the operator *where to look and why*, prints why the
  mechanical system abstains, and grades itself in public.

## 10. Clocks & come-backs

- First qledger read: ~2026-08-25 (21d grades on ~4 weeks of firings).
- CONFIRMER question earliest: ~2026-10 (n_dates≥25 on the state family).
- RUL-C5/C6 narrative-arbitration come-back (~2026-10-01): revisit NAR-R14 frame-shift with this
  program's accrued corpus + the qledger tape.
- Source-credibility first useful weights: ~25 resolved calls per source (SemiAnalysis likely
  first, given cadence).
- Ops note (outside this program): `collectors/hk_gdelt.py` is coded but its store has never
  populated — HK lane bootstrap flagged separately.
