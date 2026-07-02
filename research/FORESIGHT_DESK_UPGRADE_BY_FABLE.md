# Foresight Desk Upgrade — Fable Second Pass

*Fable 5, 2026-07-02. Successor to `FORESIGHT_DESK_PROBLEM_AUDIT_FOR_FABLE.md` (the Opus problem
pass — treated here as verified ground truth) and to the two design docs. This is the SOLUTION:
resolutions to the audit's open questions, concrete buildable designs for its P0–P3 directions,
and my own additions. Every reuse target named here was re-verified against the live repo before
citation. House contract holds throughout: free-data-first · display-only-first · forward-graded
vs SPY · crowding is NEGATIVE · no point-dates · text-only capped without a physical correlate ·
degrade to `None` · components+weights surfaced · append-only ledgers.*

---

## 0. Reframe

The Opus audit's deepest finding is not "the FRED series are missing." It is that **the desk has no
concept of its own operational state**, so a dead machine and a live machine render identically.
Every other failure — the unreachable PRECIPICE, the n=0 track record, the 37–50 "0–100" score, the
always-empty convergence board — is the same failure refracted through six surfaces. My program
therefore has one organizing principle: **make the desk self-aware before making it smarter.** The
order of operations is (1) instrument the darkness (data-health as a first-class output), (2) light
the cheapest genuine lead (the EDGAR text leg that already has data, then the FRED series),
(3) start grading *everything* immediately so the desk accrues falsifiability from day one even
while imperfect, (4) fix the arithmetic (saturation, circularity, shared-input double-counting),
and only then (5) add intelligence (calibration backtest, shadow thresholds, per-theme physical
fingerprints). A desk that knows what it doesn't know, and grades what it does, front-runs
narrative better than a desk with ten more legs — because it can be *believed*.

One disagreement of emphasis with the audit: it frames "log all stages" as an honesty fix. I frame
it as the desk's single largest *alpha* opportunity — the stage machine's negative calls
(RE-RATING = "do not chase") are testable claims with 9 live instances today, and validating the
do-not-chase rule is worth as much as any new leg. The control group *is* the product.

---

## 1. Resolutions to the audit's §12 open questions

### Q1 — FRED gap: operational or structural? → OPERATIONAL; fix by land-and-guard

The audit's evidence is conclusive (configured `config.yml:264-295`, enumerated by
`collectors/fred.py:73-77` `_all_series()`, keyless path live-verified reachable, parquets never
committed). Resolution:

1. **Land once, locally**: run the collector for the `bottleneck` + `power` groups and commit the
   parquets — the same "commit the deep-history seed" pattern used for new-market deploys. Daily CI
   then keeps them fresh like the other 125 series.
2. **Guard forever**: new `scripts/audit_fred_groups.py` in the end-of-collect audit suite — for
   every group under `fred.series`, assert ≥70% of its series have a parquet fresher than 45 days;
   below that, the group is flagged DARK in the health payload (§3.1) and the audit gate warns.
   The class of failure "configured but never landed" becomes impossible to repeat silently.
3. **Fix the id mismatch**: `engine/power_scarcity.py` probes fallback ids (`IPG2211A2N`,
   `CAPUTLG2211A2S`, `CAPUTLGMFS`, `PCU221122221122`) that `config.yml:288-295` never declares —
   add them to the config group so partial availability degrades gracefully instead of binarily.
4. **Root-cause note for CI**: if the daily collect job *still* fails to refresh these groups after
   a local landing, the audit gate will now say so explicitly — we stop guessing.

### Q2 — Per-theme physical resolution from 3 shared NAICS buckets → member-level fingerprints

The NAICS series can't be sliced finer for free. The fix is to stop leaning on them as the *only*
physical input and build each theme a **physical fingerprint** from its own members' primary
documents — per-theme by construction:

- **Member-level XBRL legs** (free, keyless, `data.sec.gov`): per-member `InventoryNet` days
  trend, `RevenueRemainingPerformanceObligation` growth (collector **exists**:
  `collectors/edgar_rpo.py:93` `fetch_rpo`), and gross-margin trend from `collectors/edgar_facts.py`
  company concepts. Roll up per theme (median of members, min 3 reporting). Memory vs WFE now read
  *different* numbers because MU/WDC/STX file different inventories than AMAT/LRCX/KLAC.
- **Ticker-scoped EDGAR language** (already per-theme): `_language_accel(tickers)`
  (`engine/bottleneck.py:122`) already filters by member tickers — once wired into the band (§2,
  P0-B) it differentiates the three semis themes today.
- **Re-weight**: shared NAICS legs drop to context weight (~0.35 combined); member-level legs +
  language carry the rest. When two themes still share >80% of their physical inputs, render a
  **"shared read: NAICS 3344" chip** on both cards — resolution honesty (feeds Q5's display).
- **Unconventional per-theme physical feeds** for the orphans — see §3.4 (FDA drug-shortage list
  for GLP-1, World Bank Pink Sheet for ag_fertilizer, EIA module prices for solar, LBNL queue for
  power/grid/nuclear, RPO backlog for defense).

### Q3 — An honest earliness signal that is not `1 − breadth` → the attention gap

Earliness should measure **attention**, not revisions (revisions are the thing being front-run;
attention is the thing that makes front-running pay). New composite, `engine/foresight_earliness.py`,
all inputs already in-repo, each rank-percentiled cross-sectionally (no absolute thresholds):

| Leg | Source (verified) | Reads |
|---|---|---|
| Coverage arrival | the NEW `n_covering` series (P1-A) once it accrues — **not** `n_analysts`, which is the audited saturated reviser count | analysts showing up = attention arriving; low+flat = early |
| News flow level | `engine/theme_activity.py` news_velocity level (`:10`) | quiet tape = early; loud = crowded |
| Ownership breadth | 13F add/held counts from existing altdata infra (`engine/altdata_confirmers.py` channels) | fund crowding level |
| Tape extension | theme-basket distance-from-high / MTF extension via existing basket engines | re-rated already = late |

`earliness = 1 − rank_pct(mean of available attention legs)`; missing legs shrink the denominator
(never default-fill) — in particular the coverage leg is simply ABSENT until P1-A's new collector
field accrues history; it must never fall back to the reviser count. Crowding stays NEGATIVE per
house rule. Revisions **exit** the earliness
definition entirely and return to their charter role: confirmation. This one change de-circularizes
the score's underpricing axis (§2, P1-C) *and* fixes convergence burying demand-confirmed themes
(§2, P2-A) — the audit's two circularity findings share one cure.

### Q4 — The 11 non-physical themes: keep or demote? → keep, two-tier, and shrink the orphan count

Keep them — they feed discovery and confirmers — but split the desk into **Tier P (physical desk)**
and **Tier W (watch shelf)**. Tier P: themes with a nameable choke-point and ≥1 live physical or
member-XBRL leg; full cards, eligible for every stage. Tier W: compact rows in a visually distinct
section, capped at 50 as today, labeled *"no physical correlate — cannot generate PRECIPICE"*, and
**excluded from the headline stage counts** so the hero numbers describe only the desk that can
actually fire. Judgement call: deletion would be self-harm (the HBM pattern says today's orphan is
tomorrow's PRECIPICE — you want it on the shelf when its correlate appears), but letting text-only
themes dilute the physical desk's headline is how the audit's "camouflage" happened.

And the orphan count is not really 11 — §3.4's unconventional feeds move ~5 of them (defense,
ag_fertilizer, solar, glp1_obesity, nuclear beyond the shared read) into Tier P at S–M effort each.

### Q5 — Displaying "one bet in N hats" → measured ENB + named driver clusters

Two layers, both computed from data the repo already has:

1. **Effective number of bets (ENB)**: member-equal-weight daily return series per theme from
   `data/yahoo/*.parquet` (reuse the grader's `_closes`/`_ret` machinery,
   `engine/foresight_grader.py:46,84`), 120d correlation matrix across constructive themes, ENB =
   (Σλ)²/Σλ² over its eigenvalues (participation ratio). Display in the sizing strip:
   **"9 constructive themes ≈ 2.7 independent bets."**
2. **Named driver clusters**: hierarchical clustering on the same matrix (threshold ρ≈0.7) with
   hand-named clusters ("hyperscaler-capex complex", "defense/geopolitics", "healthcare") — each
   cluster a card listing member themes + combined implied weight + ONE shared-driver sentence.
   Plus the Q2 "shared read" chips at pair level.

This is a risk *display*, not a signal — no grading needed, but the nightly ENB is logged so the
concentration history is auditable. It also feeds convergence de-duplication (§2, P2-A): heat that
lights several same-cluster themes renders as one meta-driver card, not six hot tiles.

### Q6 — Minimum viable falsifiability → three S-effort changes, first graded rows in ~30 days

1. **Log ALL stage rows** (`foresight_cascade.py:307` currently filters to the two unreachable
   stages). Every (theme, asof, stage) row goes to the ledger, deduped on stage *transitions* (log
   on change + weekly heartbeat, not daily re-fires — keeps the non-overlap gate meaningful).
   RE-RATING and WATCH become the control arms: the desk starts testing "do not chase" **today**,
   with 18 live rows on day one.
2. **Multi-horizon grading**: grade each flag at 30/60/90d vs SPY. The grader computes ONE fixed
   horizon today (`HORIZON_DAYS=90`, `foresight_grader.py:36`) — generalize it into a list and
   grade/report per-horizon (a real refactor of the maturity gate + ledger schema + per-slice
   Wilson/BY reporting, not a two-line change). First graded rows in ~30 days instead of ~90.
   **FDR-label reconciliation** while there: read the actual step-up implementation
   (`foresight_grader.py:141-146` — harmonic-number scaling = Benjamini-**Yekutieli**), then make
   the code docstring (`:18`, currently "Benjamini-Hochberg"), the template copy
   (`foresight.html.j2:432`, also "Benjamini-Hochberg"), and the methodology panel agree with what
   the code does. The fix is label-to-code agreement, not a template string in isolation.
3. **Text-grade PRECIPICE on probation** (with P0-B): when the wired language leg + ≥2 distinct
   filers produce a text-TIGHT read on a theme whose breadth is flat, emit stage
   **`PRECIPICE (text)`** — logged and graded like any flag, score still capped at 50, card badge
   visibly distinct. The desk can produce its first genuine early-thesis flag **within days of the
   text leg landing**, honestly labeled, before any FRED series arrives.

Fastest path to a real graded track record: Q6.1 + Q6.2 ship in one small PR and start the clock
immediately; Q6.3 gives the first *thesis-stage* flags the same week.

---

## 2. The prioritized buildable solution set

Each: mechanism → calibration → reuse → grading. LEAD/CONF tags per house taxonomy.

### P0-A · Light the furnace (data landing + guard) — **[Fk] S–M · LEAD**
As Q1. Files: run `collectors/fred.py` for the two groups (commit parquets); config fallback-id
additions; new `scripts/audit_fred_groups.py` wired into the existing end-of-collect audit suite;
optional `collectors/lbnl_queue.py` (annual LBNL "Queued Up" download → `data/eia/
interconnection_queue.json`, the file `engine/power_scarcity.py:48-51` already reads).
Calibration: none needed — this is plumbing. Grading: bottleneck/glut ledgers begin accruing the
moment bands go live.

### P0-B · Wire the dead text leg, with polarity — **[FK] M · LEAD**
The audit's "architecturally dead" leg becomes T1's first live input:
- **Collector** (`collectors/edgar_fts.py`): capture per-hit matched-text context for a polarity
  read. **Verify-at-build assumption (review-flagged)**: whether the `search-index` JSON response
  carries a highlight/excerpt field is NOT demonstrated by the current collector (`_parse_hit`
  reads only `_source` metadata, `:93-110`). Step 1 of the build is an empirical probe of the
  response shape. Fallback ladder if no excerpt field exists: (a) fetch the primary document for
  the ±snippet around the phrase — re-tags this item **L** and must respect the <10 req/s budget;
  or (b) ship with `polarity: null` (a matched-phrase-only heuristic) and let the ≥2-distinct-filers
  gate carry the noise burden until (a) lands. Polarity filter, once text is available: flag hits
  whose matched phrase sits within ~12 tokens of a negation/hypothetical marker (`not / no longer /
  if we / could become / risk that / may be` — lexicon extended from logged misfires). Keep the raw
  hit with a `polarity` column rather than deleting, so the filter itself is auditable.
- **Engine** (`engine/bottleneck.py`): add `leg6_language` (matching the module docstring's own
  numbering, `:16`) into `legs`/`WEIGHTS` (`:56-57,159-160`) at 0.25 weight (others rebalance to
  0.75/4). Language z-scored on its own 240d window. **Both the 0.25 weight and the z-cutoff are
  PROVISIONAL — declared "shadow-calibration pending" in the engine output and on the methodology
  panel, per §3.2's own rule** (the review correctly caught that shipping them silently would
  recreate the audited uncalibrated-literal pathology). Shadow variants of the z-cutoff are logged
  from Wave 1, not Wave 3 (§3.2 moves up for this leg). Band rule: language alone can lift a theme
  to at most **TIGHT (text)** — a `text_only: true` band variant requiring ≥2 distinct filers +
  positive accel; SOLD_OUT still requires a numeric leg. The TEXT_ONLY_CAP=50 stays until a numeric
  physical leg confirms — unchanged house rule.
- **Symmetric glut leg** — see §3.6 (capacity-ADDS language gives the exit clock its own text tier).
Calibration: replay the phrase sweep historically (EDGAR FTS covers 2001→present; the collector
already uses `startdt`/`enddt` window params, `edgar_fts.py:143-144` — §3.3) and set the
z-threshold where the 2019/2021-supply-crunch and 2024-HBM episodes flag without 2017/2019 false
fires; until that replay lands, the live cutoff stays provisional + shadow-logged. Grading:
text-band flags are emitted under a distinct stage value (`PRECIPICE (text)`), which gets its own
grader slice for free via the existing by-stage bucketing (`foresight_grader.py:196,220`); a
generic `text_only` tag dimension would be net-new grader code and is not required.

### P0-C · Log-all-stages + multi-horizon grading — **[FK] S–M**
As Q6.1/Q6.2. Files: `engine/foresight_cascade.py:286-317`, `engine/foresight_grader.py` (horizon
generalization per Q6.2 — the multi-horizon fan-out is why this is S–M, not S),
FDR label-to-code reconciliation (Q6.2). Also fix `n_pending` semantics so the track panel
distinguishes "0 logged" from "logged, immature" — the audit caught the current copy misdescribing.

### P0-D · Data-health surface (the anti-camouflage layer) — **[FK] S–M**
New `engine/foresight_health.py`: per-leg status from the payloads themselves —
`LIVE / PARTIAL(n/m) / DARK / DEGENERATE` for T1 FRED, T1 text, T2, T3, T4 level, T4 accel, glut,
power, confirmers, analyst (credential?), monitor (theses>0?). Emit into the cascade JSON + render
a status strip at the top of `foresight.html`. **Self-description downgrade**: when zero LEADING
legs are LIVE, the hero subtitle switches to *"running in CONFIRMER-ONLY mode — the leading legs
below are dark"* and stage pills render hollow. Health regressions (leg LIVE→DARK vs yesterday)
alert through the existing data-health circuit-breaker path. This is the audit §9.1 fix and the
precondition for trusting everything else.

### P1-A · Fix breadth measurement — **[FK] M · CONF**
`collectors/equity_revisions.py`: add `n_covering` (total forward-year analyst count) from the
yfinance **`earnings_estimate`** accessor (the Yahoo `earningsEstimate` module carries
`numberOfAnalysts`) — a **NEW accessor the collector does not currently read** (it reads only
`eps_revisions` + `eps_trend`, whose `n_analysts` counts *revisers*, per the audit's saturation
root cause — review-verified, `collectors/equity_revisions.py:33-34,55,69`). Emit
`breadth_cov = (up − down) / n_covering` alongside the legacy reviser-share. **Hard honesty rule:
if the coverage field proves unavailable at build, `breadth_cov` is not computable and the
de-saturation fix does NOT ship** — the legacy metric stays with an explicit saturation caveat in
the health surface; it must never silently substitute the reviser count. Theme rollup
(`engine/theme_revisions.py`) switches to coverage-weighted mean of `breadth_cov`, gated on
`n_covering ≥ 5`. **Threshold self-calibration**: replace `BROAD_HI=0.50` (lives in
`engine/foresight_cascade.py:32`, used at `:51,65,74`) with a daily cross-sectional percentile —
"already broad" = theme breadth above the ~80th percentile of all-theme breadth that day — so the
late-line adapts to tape-wide revision waves instead of classifying 44% of the universe as late.
Percentile choice itself validated by the shadow ledger (§3.2). Grading: unchanged ledger; the
stage distribution shift is the observable.

### P1-B · Resurrect the derivative without waiting for history — **[FK] S–M · LEAD**
`engine/theme_revisions.py:74-107`: (a) make `ACCEL_LOOKBACK_DAYS` adaptive — use the earliest
snapshot ≥10 days back when 21d isn't available, output `basis_days` so the read is honest about
its window; (b) until even 10d exists, emit `broadening_proxy` from `est_chg_30d` vs `est_chg_90d`
(both already collected per name — drift accelerating vs decelerating), clearly flagged
`proxy: true`. BROADENING becomes reachable now, on a proxy, honestly labeled — instead of
structurally dead for weeks.

### P1-C · De-circularize the score — **[FK] M**
`engine/foresight_score.py`: underpricing axis ← Q3 earliness composite; pricing-power axis ← PPI
trend when live, else member gross-margin trend from `edgar_facts` (per-theme, free), else `None`
and the axis drops out of the weighted sum (renormalize over live axes — no more 0.4-default
laundering; the audit's "absence fed as measurement"). Magnitude axis ← per-theme demand read
(P1-D), not the shared pool. Surface `n_axes_live / 7` on the score tooltip. Weight provenance
line becomes true via §3.2's shadow calibration; until then the docstring's "tuned via ledgers"
claim is corrected to "defaults; shadow-calibration pending" — never claim what hasn't happened.

### P1-D · Demand: per-tier, per-name, sign-checked — **[FK] M · LEAD**
Re-point T2 from the single pool onto the machinery that already exists:
- **Per-tier lag structure** from `engine/demand_chain.py:43-68` (`direct` now / `lagged` +1q /
  `indirect` +2q): the same pool read arrives at different tiers at different times instead of
  identically everywhere.
- **Per-name divergence** from the demand-desk chassis (`engine/demand_ledger.py` — divergence ∈
  {ahead_of_consensus, consensus_at_risk, aligned}): theme demand read = share of members
  ahead-of-consensus, min 3 covered. This is the discriminating signal the pool can't give.
- **Sign validation, not assertion**: demand-confirmed flags are graded against demand-absent flags
  in the ledger (two slices, same grader). If Cooper–Gulen–Schill dominates the beneficiary-chain
  effect, the grades will say so and the leg auto-downgrades to context. `demand_ledger` already
  runs falsifiable ±5%-vs-SPY theses on exactly this question — consume its track record rather
  than duplicating it.
- **Supplier-side confirmer**: theme RPO growth via `collectors/edgar_rpo.py:93` (supplier backlog
  leads its own revenue; directionally clean where buyer capex is not).

### P2-A · Convergence rebuilt on sources, not engines — **[FK] M**
`engine/foresight_convergence.py`: (a) merge `subsector_scarcity` + `discovery_echo` into one
"EDGAR scarcity" surface (they read the same parquet — audit-confirmed); (b) count **distinct data
sources** lit, not engines; (c) `earliness` ← Q3; (d) physical stops being a fixed ×0.75 penalty
when DARK — dark legs leave the denominator (heat = lit/available, with `available` displayed), so
the board measures agreement among what's live instead of punishing the desk for its own outages;
(e) heat threshold set by §3.3 replay (top-decile historical heat), not the current unreachable
0.55 guess; (f) same-cluster themes (Q5) share one meta-driver card.

### P2-B · Monitor decoupled from the LLM + citation contract — **[FK/Fk] M**
`engine/thesis_monitor.py`: theses come from **two** producers — (1) NEW deterministic
auto-theses: every PRECIPICE/BROADENING (incl. text-grade) flag instantiates a templated thesis
whose kill-criteria are machine-checkable functions of its own components ("text mentions accel
< 0 for 2 sweeps", "breadth_cov rolls negative", "PPI yoy < 0"); (2) LLM analyst theses when
credentialed — now an *enrichment*, not the sole source. THESIS-BROKEN can fire with zero LLM
involvement, as originally intended. LLM hardening per the blueprint §5 (implement, it never was):
exact-substring citation validation against the cached filing + forecast-clamp extended to ALL
output fields (`foresight_analyst.py:130` currently skips `kill_criteria`/`evidence`/`regime_read`).

### P2-C · Sizing that adds information — **[FK] S–M**
`engine/foresight_sizing.py`: ENB + driver clusters (Q5) into the sizing strip; `size_mult`
becomes `stage_cap × earliness-tilt × cluster-dilution` (a theme that is one of five hats on the
same bet gets its mult divided by its cluster's ENB share) so it finally carries information beyond
the stage badge; forced de-risk arms automatically once glut can fire (P0-A/§3.6 give it inputs).

### P3 · Sibling confirmers (thin adapters, correlation-penalized, graded) — **[FK] S each · CONF**
Per the audit §8 map: news-velocity **acceleration** (`engine/theme_activity.py:105`
`source_accel` — flag themes where activity accelerates while breadth is flat: the BROADENING
precursor); special-situations catalyst chips (`engine/special_situations.py` stage pipeline —
display + entry-urgency context, never a stage-changer); insider-into-quiet-tape (cross
`altdata_confirmers` counts with news-flow level — insider cluster + quiet tape = pre-narrative,
the earliest confirmer the repo can compute); cycle-regime durability gate on `entry_ready`
(`engine/cycles.py` position: BROADENING in late cycle renders an exhaustion caution); rotation
leadership cross-check (`engine/subsector_rotation.py`, needs the 18↔Finviz taxonomy bridge map).
Every adapter: inverse-to-breadth, ledger-logged, graded before it earns rationale space.

---

## 3. Fable add-ons (net-new, beyond the audit's roadmap)

### 3.1 The desk grades its own *machinery*, not just its calls
Extend the health surface (P0-D) into a nightly `data/foresight/health_log.jsonl`: per-leg status +
per-leg *contribution share* to that day's stages. The page shows "what would change if leg X went
dark" (recompute stages with the leg ablated — cheap, it's all pure functions). Institutional desks
know their P&L attribution; this desk should know its **verdict attribution**. Also the CI tripwire:
any leg LIVE→DARK regression fails the collect audit loudly.

### 3.2 Shadow-threshold ledger — self-recalibration without over-claiming
Every build, compute stages under the **live** thresholds AND under a small grid of **shadow**
candidates (e.g. BROAD_HI ∈ {p70, p80, p90}, text-z ∈ {1.0, 1.5, 2.0}); log shadow flags to a
separate ledger, graded identically. A threshold is **promoted only when its shadow slice beats the
live slice with BY-FDR significance** — and the promotion itself is a logged, dated event on the
methodology panel. This is the honest version of "self-recalibrating": parameters change only when
forward evidence clears the same bar the themes must clear. (Replaces the score docstring's false
"tuned via ledgers" with a mechanism that makes it true.)

### 3.3 Point-in-time calibration backtest — ship calibrated, not guessed
The audit says every threshold is a round-number guess; the repo already contains the cure:
**ALFRED vintage support exists** (`collectors/fred.py` `fetch_vintages`, `as_of_series()`,
`config.yml:60-70`) and EDGAR FTS queries historically with `dateRange` (2001→). One-off study
`scripts/research/backtest_foresight_cascade.py`: replay 2019→2025 monthly using vintage FRED
(what was knowable when) + dated EDGAR hits + dated 8-K guidance; emit stage flags; grade 30/60/90d
forward member-EW returns vs SPY. Deliverables: (a) band/threshold settings at max forward
discrimination, (b) the empirically-earned answer to "does PRECIPICE beat BROADENING beat
RE-RATING," (c) a validation exhibit for the page. Known-answer tests: 2020-Q3 semis tightening,
2021 supply-chain crunch, 2024 HBM, 2022 memory glut (exit side).

**Prerequisites the review surfaced (do not skip):** the vintage matrix currently covers ONLY the
macro/business-cycle set (`collectors/fred.py` `DEFAULT_VINTAGE_SERIES:42-61` + config overrides) —
**none of the bottleneck/power series** (`CAPUTLG*`, industry PPIs, `ISRATIO`, `NEWORDER`,
`IPG2211S`…) are in it. PIT replay of the cascade's own physical legs therefore requires:
(a) adding those ~8-12 series to `config fred.vintage_series`, (b) a `FRED_API_KEY`
(`fetch_vintages` returns empty without one), and (c) build-time confirmation that ALFRED actually
serves initial-release vintages for NAICS-detail CAPUTL/PPI series (plausible, unverified — some
detail series have short or no vintage history). **Until those vintages land, the bottleneck-side
replay is latest-revised data — look-ahead-contaminated — and must be labeled as such**; its
thresholds then calibrate only on the forward shadow ledger (§3.2), same as T4 (yfinance revisions
have no history pre-2026-06). Flag Wave 3a as the one item that can silently no-op absent the
key/vintages — the health surface should show its status too.

### 3.4 Unconventional per-theme physical feeds (the orphan-rescue kit) — my favorite
The audit treats 11 themes as physically unmappable because no FRED industry series exists. But
"physical correlate" ≠ "FRED series." Free, keyless, per-theme scarcity reads:

| Theme | Feed (free) | Physical read | Note |
|---|---|---|---|
| **glp1_obesity** | **FDA Drug Shortages** (openFDA — confirm endpoint + JSON schema at build, else scrape the published list) | semaglutide/tirzepatide on the shortage list = literal demand-exceeds-supply, with start/end dates | The GLP-1 shortage 2022-2025 was *the* thesis. A resolved shortage = the glut tell. |
| **ag_fertilizer** | World Bank Pink Sheet (monthly **.xlsx workbook** — parse; NOTE the existing `collectors/worldbank.py` is the *indicator* API, NOT the Pink Sheet, and is not reusable for this) | urea/DAP/potash price momentum | Direct pricing-power read, decades of history for calibration |
| **solar** | EIA module shipment/price series (open data, keyed-free) | module price deflation = permanent glut state | Also explains why solar should live in Tier W most of the time |
| **defense_aerospace** | member RPO via `edgar_rpo.py` (**pass theme tickers** — its default universe is software; verify members actually tag `RevenueRemainingPerformanceObligation`, many A&D names disclose funded backlog only in MD&A prose) + USAspending obligations (collector exists) as the fallback leg | funded backlog growth = physical order book | The audit's own §8 confirms `usaspending` collection exists |
| **nuclear_power / grid** | LBNL "Queued Up" (annual multi-sheet **.xlsx** — real parsing work into the `interconnection_queue.json` that `power_scarcity.py:48-52` already reads) + NRC docket counts | years-lead interconnection + licensing pipeline | The blueprint's queue engine; the reader exists, the collector does not |

All five feeds are **verify-at-build** — the repo demonstrates none of their formats; each degrades
to `None` per house rule, so a dead feed costs nothing but its absence must show in the health
surface. The three that need real parsers (FDA, Pink Sheet, LBNL) are **M** each, not S.

Pattern worth naming: **every theme must nominate its own scarcity observable** — the admission
rule from the blueprint, operationalized. A theme that can't name one lives on the watch shelf.

### 3.5 Meta-driver cards (concentration-aware convergence)
From Q5's clusters: when ≥3 same-cluster themes light the same surfaces, the convergence board
renders ONE "AI-capex complex" card (members listed, one heat, one earliness) instead of six tiles.
This is both truthful (it *is* one bet) and better UX (the board stops shouting six times about one
thing). Cluster membership is data-derived nightly (ρ matrix), names hand-curated.

### 3.6 Glut gets its own text tier (symmetric early-warning)
P0-B mirrored: a **capacity-ADDS phrase dictionary** ("capacity expansion", "new fab", "adding
capacity", "capacity coming online", "increased supply", "inventory normalization") swept by the
same `edgar_fts` collector into a `glut_hits` cache; `engine/glut_watch.py` gains a text leg so the
exit clock has an input that doesn't wait on FRED. The 2022 memory glut was preceded by exactly
this language wave through 2021 filings. Same polarity design as P0-B — including its
verify-at-build snippet caveat and fallback ladder — same text-only banding, same ledger.

### 3.7 Stage-transition intelligence (the desk learns its own clock)
With log-all-stages (P0-C), the ledger accumulates transition data: median dwell time in PRECIPICE,
P(PRECIPICE→BROADENING) vs P(→WATCH), realized lead from first text-TIGHT to breadth-broadening.
Render as a small transition strip on the methodology panel. No point-date forecasts — dwell-time
*bands* per house rule — but "PRECIPICE flags have historically resolved within 2–3 quarters"
is exactly the institutional-memory artifact a real desk accrues and this one currently can't.

---

## 4. Preservation note (do not break)

The cascade taxonomy (physical LEADS → demand/guidance pre-signal → revisions CONFIRM → entry
deferred to dislocation → glut = exit clock); STAGE-not-score ranked by edge-remaining;
PIT membership snapshots at flag time (`foresight_cascade.py:302-312` — correct and leak-free);
append-only ledgers; Wilson/BY-FDR machinery (fix only the label); TEXT_ONLY_CAP and stage caps
(they should *bind rarely*, not vanish); no point-dates; crowding-is-negative; display-only-first
for every new leg; degrade-to-None (now paired with health surfacing so None is visible, not
silent). The `None`-contract was never the bug — the invisibility was.

---

## 5. Phased build sequence

Waves sized to PR-able chunks, disjoint files where parallel. Per standing model-tier routing:
**Sonnet implements, Opus reviews/judges**; Fable owns design arbitration. Tags: [FK] free-keyless ·
[Fk] free-with-key · S/M/L effort · LEAD/CONF.

| Wave | Items | Files (primary) | Effort | Unlocks |
|---|---|---|---|---|
| **0a** | P0-C log-all-stages + 30/60/90 grading (single-horizon grader generalized) + FDR label-to-code fix + n_pending fix | `foresight_cascade.py`, `foresight_grader.py`, template | S–M | falsifiability clock starts TODAY |
| **0b** | P0-D health surface + self-description downgrade + §3.1 health log | new `engine/foresight_health.py`, `scripts/build_foresight.py`, template | S–M | anti-camouflage |
| **0c** | P0-A land FRED groups + audit gate + power fallback ids (+ LBNL queue if trivial) | `config.yml`, new `scripts/audit_fred_groups.py`, data commit | S–M [Fk] | T1/power/glut inputs exist |
| **1a** | P0-B text leg wiring + polarity (verify-at-build snippet probe first) + text-grade PRECIPICE (Q6.3) + **shadow z-cutoff logging from day one** (§3.2 moved up for this leg) | `edgar_fts.py`, `bottleneck.py`, cascade | M (L if snippet needs doc-fetch) | first genuine early flags, provisionally labeled |
| **1b** | §3.6 glut text tier | `edgar_fts.py` (shared), `glut_watch.py` | S | exit clock lights |
| **1c** | P1-B adaptive accel + drift proxy | `theme_revisions.py` | S–M | BROADENING reachable |
| **2a** | P1-A n_covering (new `earnings_estimate` accessor) + breadth_cov + percentile threshold | `equity_revisions.py`, `theme_revisions.py`, `foresight_cascade.py` | M | de-saturation |
| **2b** | P1-D demand re-point (tiers + divergence + RPO) | `demand_capex.py`, adapters over `demand_chain`/`demand_ledger`/`edgar_rpo` | M | per-theme demand |
| **2c** | Q3 earliness engine + P1-C score de-circularization (consumes 2a+2b; **magnitude axis renormalizes-out to None until 2b lands — must NOT fall back to a 0.4 default**) | new `engine/foresight_earliness.py`, `foresight_score.py` | M | real ranking discrimination |
| **3a** | §3.3 PIT calibration backtest (research) — prerequisite: bottleneck/power series added to `vintage_series` + `FRED_API_KEY` + ALFRED vintage-coverage check; else forward-shadow-only and labeled so | new `scripts/research/backtest_foresight_cascade.py`, `config.yml` | L [Fk] | thresholds earned, not guessed |
| **3b** | §3.2 shadow-threshold ledger (general grid — the text-leg slice already runs from 1a) | grader + cascade | M | honest self-recalibration |
| **4a** | P2-A convergence rebuild + §3.5 meta-driver cards + Q5 ENB/clusters + P2-C sizing | `foresight_convergence.py`, `foresight_sizing.py`, template | M | the marquee board means something |
| **4b** | P2-B monitor decoupling + LLM citation/clamp hardening | `thesis_monitor.py`, `foresight_analyst.py` | M | BROKEN fires without a credential |
| **5** | P3 sibling adapters + §3.4 orphan-rescue feeds + Q4 two-tier layout | thin adapters (S each) + new collectors FDA/Pink-Sheet/LBNL (M each — real parsers) + template | S–M | breadth of leading surfaces |

Sequencing logic: Wave 0 is pure unlock (falsifiability + visibility + data) and every later wave's
grading depends on it — nothing above Wave 0 should merge before it. Waves 1–2 make the desk
*produce and test* real calls. Wave 3 makes its parameters defensible. Waves 4–5 make it
institutional. Each wave: display-only first, ledger from day one, graded before promoted.

---

*Provenance: Fable 5 second pass, grounded on the Opus audit (six verified sub-audits) plus direct
re-verification of every reuse target cited here (`demand_chain.py`, `demand_ledger.py`,
`edgar_rpo.py`, `edgar_fts.py`, `theme_activity.py`, `foresight_grader.py` return machinery,
ALFRED vintage config). Then adversarially reviewed by a 3-lens Opus panel (repo-reality ~40
citations re-verified / audit-consistency / contract-feasibility red-team); the panel's 1 blocker
(coverage-count sourcing) and 7 fixes (FTS-snippet assumption, provisional text thresholds,
vintage-coverage gap, wave 2 sequencing, orphan-feed format certainty, grader horizon scope,
FDR label-to-code) are incorporated above. Verdicts: "no design rests on something false" /
"broadly consistent, no CRITICAL unaddressed" / "GO with fixes." No engine code changed by this
pass — design deliverable only.*
