# Thematic Foresight Desk — Problem Audit for Fable

*Opus problem-finding + deep-reasoning pass, 2026-07-01. Companion to `THEMATIC_FORESIGHT_DESK.md`
(the desk as designed) and `THEMATIC_FORESIGHT_INSTITUTIONAL_UPGRADE.md` (the aspirational build
blueprint). This document is neither — it is an adversarial audit of **what actually ships today**
(`site/foresight.html` / `site/basketdata/foresight_cascade.json`, asof 2026-07-01), so Fable can do a
second-pass solution/implementation/interpretation. Every claim is cited to `file:line` and verified
against the live repo + the committed output artifact. Findings were produced by six parallel deep-read
audits (T1+guidance / T4+demand+glut / score+sizing / convergence+LLM+monitor / grader+discovery+power /
supporting-signal map) and this synthesis.*

---

## 0. The one-sentence diagnosis

**The desk is architected as a leading, physically-anchored, forward-graded, self-monitoring machine —
but in its shipped state every leading input and every self-monitoring loop is dark, so it runs as a
single-input coincident revision-breadth screener wearing the costume of an institutional 7-axis
physically-graded rubric.** The architecture is sound; the machine is unplugged, and the "honesty"
guardrails have quietly become the entire product.

Concretely, in the committed 2026-07-01 artifact (18 themes):
- **0 PRECIPICE, 0 BROADENING** themes. 9 RE-RATING, 9 WATCH. The desk's flagship output — "catch the
  theme at the precipice" — is structurally unreachable and has never once been emitted.
- **Every** theme: `bottleneck_band ∈ {AWAITING_DATA, null}`, `tightness: null`, `physical_confirmed: false`.
- **Every** theme: `broadening_state: INSUFFICIENT_HISTORY` and `glut_band ∈ {AWAITING_DATA, null}`.
- **Every** AI theme: `capex_yoy: 69.0` — the identical number, six times.
- Scores span **36.9–50.0** on a "0–100" scale; four themes tie at the 50 ceiling.
- Track record: `n_total: 0, n_graded: 0, n_pending: 0` — and, as shown in §5, can never become non-zero.
- The convergence "🔥 What's heating up early" marquee, the "🧠 AI analyst read", and the THESIS-BROKEN
  monitor all render their empty/absent state. The top of the page is dark.

---

## 1. The keystone: one missing data layer collapses the whole desk

There is a single point of failure, and it fails silently.

**The dependency:** the T1 physical-bottleneck leg (and the power-scarcity leg) require per-industry FRED
series — capacity-utilization (`CAPUTLG3344S/334S/331S`), industry PPI (`PCU334413…`, `PCU331110…`),
inventory/sales (`MNFCTRIRSA`), unfilled orders/shipments (`AMTMUO`/`AMTMVS`), regional-Fed delivery-time,
and the power group (`IPG2211S`, `CAPUTLG2211S`, `WPU0543`, …).

**The failure:** of the ~19-series `fred.series.bottleneck` group (`config.yml:264-287`) and the
`fred.series.power` group (`config.yml:288-295`), **only `ISRATIO` and `NEWORDER` actually land in
`data/fred/`** (125 other FRED parquets are present and fresh). Every per-industry cap-U / PPI / delivery /
power series is absent. The series *are* enumerated for fetch — `collectors/fred.py:73-77` flattens every
group including `bottleneck`/`power` — and they are **not** WAF-blocked (the keyless `fredgraph.csv?id=CAPUTLG3344S`
path returns valid CSV under the library UA the collector already sends; cf. memory `fred-keyless-ua-waf`).
So this is an **operational collection gap**, not a config or WAF problem: the series are reachable,
configured, and enumerated, but have never populated `data/fred/` in this repo (`git log` shows the
`CAPUTLG*` parquets were never committed).

**The cascade of consequences** (each verified downstream):

1. `engine/bottleneck.py:108-119` `_band()` returns `AWAITING_DATA` whenever `composite is None`, which
   happens whenever no leg resolves (`bottleneck.py:161-163`). All four legs read the absent series → all
   `None` → `AWAITING_DATA` for the 7 mapped themes; the other 11 are unmapped (`THEME_MAP`,
   `bottleneck.py:40-48`) → `band = null`. **No theme can ever reach TIGHT/SOLD_OUT.**
2. `foresight_cascade.py:45,71-78` gates PRECIPICE/BROADENING on `bn_known` (a TIGHT/SOLD_OUT band).
   Unreachable → **no thesis stage ever fires.**
3. `foresight_cascade.py:307` `_append_ledger` only logs PRECIPICE/BROADENING rows → `data/foresight/log.jsonl`
   **is never created** → the grader (`foresight_grader.py:195`) reads zero rows → `n_graded = 0` **in
   perpetuity** (§5).
4. `foresight_score.py:83-84,124` sets the bottleneck axis to a `0.4` placeholder and `physical_confirmed=False`
   → the `TEXT_ONLY_CAP=50` (`foresight_score.py:29,134-136`) **always binds** → the "0–100" score is really
   a **~37–50 band** (§4).
5. `foresight_sizing.py:59-64` de-risk/EXIT requires a firing glut band → glut is dark → **the entire
   exit-discipline half of the sizing overlay can never activate** (§4).
6. `foresight_convergence.py:106-109` multiplies heat by `1.15 if physical else 0.75`; with physical dead the
   multiplier is fixed at 0.75, and the live max heat across all themes is **0.157 vs a 0.55 bar** → the
   marquee board **always renders its empty state** (§6).

**The deeper problem is not the missing data — it is that the failure is invisible.** The design contract
("additive, never fatal, return `None`/`AWAITING` on shortfall") is locally honest but globally misleading:
the page still renders a polished 7-axis score, a convergence board, a discovery feed, and a
"forward-graded track record" panel, giving a user no way to know that five of six surfaces are structurally
inert and the sixth is a coincident confirmer. **The honesty machinery has become camouflage.** There is no
data-health surface that says, in plain terms, *"T1 is dark — you are looking at a revision-breadth screener,
not a bottleneck desk."*

---

## 2. The physical moat (T1 + power) — dark, and coarse even when lit

Severity: **CRITICAL** (dark) + **HIGH** (coarse-by-design).

- **Dark today** (§1): 0/18 themes have a live physical read.
- **Only 7 of 18 themes are even mappable** (`bottleneck.py:40-48`). The other 11 (nuclear_power,
  cybersecurity, glp1_obesity, defense_aerospace, solar, robotics_automation, fintech_payments,
  medical_devices, diagnostics_lifesci, ag_fertilizer, space_satellite) have no per-industry series by
  design → permanently `null`. Half the desk can never have a physical thesis.
- **Non-discrimination even when lit:** the 7 mapped themes resolve to only **3 distinct physical reads**.
  `memory_storage`, `ai_semiconductors`, `semicap_equipment` all share `CAPUTLG3344S`+`PCU334413334413`;
  `data_center_power`+`grid_electrification` share `CAPUTLG334S`; `copper_steel_electrify`+`rare_earth_critical_min`
  share `CAPUTLG331S`. Because leg2/leg3 are economy-wide constants shared across every theme
  (`bottleneck.py:153-154,197`), these themes would show **byte-identical** tightness/band/regime. A NAICS-3344
  cap-U reading cannot tell HBM from WFE — different points in the same supply chain with opposite lead/lag.
- **The one leg with real data is architecturally dead.** `_language_accel()` (EDGAR "sold out / on
  allocation" full-text velocity) is computed (`bottleneck.py:157`) and **has real data**
  (`data/edgar/bottleneck_hits.parquet`, 59 rows, NVDA "sold out", AVGO "on allocation", ANET "extended lead
  times", fetched 2026-06-28) — but it is **not added to `legs`** (`bottleneck.py:159-160`), has no weight
  (`WEIGHTS`, `bottleneck.py:56-57`), and is not read by the score. It feeds neither band, tightness, regime,
  nor score. The docstring advertises it as a fifth physical leg; it wires into nothing.
- **Uncalibrated thresholds:** band cutoffs (SOLD_OUT>1.5 / TIGHT>0.75 / TIGHTENING>0.25 / LOOSE<-0.25,
  `bottleneck.py:111-118`), z-window (`Z_WIN=120`, `bottleneck.py:35-36`), and leg weights (0.28/0.22/0.25/0.25,
  `bottleneck.py:56-57`) are all round-number literals with no provenance and no backtest tie to the HBM episode.
- **Power leg entirely dark:** `power_scarcity.py:65-79` returns `None` because its FRED series
  (`IPG2211S`, `CAPUTLG2211S`, `WPU0543`, `APU000072610`, …) are absent and the LBNL interconnection-queue file
  (`data/eia/interconnection_queue.json`) doesn't exist. Config declares the series (`config.yml:288-295`) but
  the engine's fallback ids (`IPG2211A2N`, `CAPUTLG2211A2S`, `CAPUTLGMFS`, `PCU221122221122`) are **not** in
  config — a config/engine id mismatch, so even a partial collection would resolve only primaries. The
  convergence "physical gate" for the five power themes therefore never lights.

**The irony:** the desk's own upgrade blueprint calls the physical-capacity + queue read "the only real lead"
and "the desk's actual moat." That moat is 0% live.

---

## 3. The one live signal (T4 revision breadth) is measurement-broken

Severity: **CRITICAL**. This is the only leg driving the shipped output, and it is broken three ways.

**(a) Saturated by construction.** `breadth = (up − down) / (up + down)` over the analysts who *revised* in
the last 30 days (`collectors/equity_revisions.py:53-66`). The denominator is **revisers only, not coverage** —
so a name with 4 up / 0 down = breadth **1.0** whether it has 4 or 40 analysts. Across the whole 1,454-name
universe, **44% of names have breadth ≥ 0.50 and 27% pin at exactly 1.0**. `memory_storage`'s 0.955 is just
MU/WDC/SNDK/STX all at 1.0 — a near-universal condition in any up-tape, not theme signal. The metric carries
almost no cross-theme discrimination at the top end. (Secondary: `MIN_ANALYSTS≥3`, `theme_revisions.py:34,68`,
counts *revisers* not coverage, so it admits the noisiest 3-up/0-down names rather than filtering them.)

**(b) Level, where change is required.** `broadening_state` is **always `INSUFFICIENT_HISTORY`** because the
derivative needs a prior snapshot ≥21 days back (`ACCEL_LOOKBACK_DAYS=21`, `theme_revisions.py:36,89-93`) but
the entire PIT archive (`data/revisions/history.parquet`) spans only **~15 calendar days** (it began accruing
2026-06-16; the yfinance source gives only a live snapshot with no history — `equity_revisions.py:6-7`). The
`breadth_accel` leg is **the only leg that reads direction/change** — the desk's actual thesis instrument — and
it is dead. So the desk runs on breadth **level**, which its own charter calls the *lagging* read, and cannot
distinguish BROADENING (rising, early runway) from RE-RATING (already broad, late). Worse, the drip cadence
(≤200 names/build, 6-day freshness) means most members will not have a usable 21-day-back snapshot for weeks.

**(c) Uncalibrated threshold does the classifying.** `BROAD_HI = 0.50` (`foresight_cascade.py:32`) is a
hardcoded guess with no derivation. Because (a) makes 44% of the universe clear it and (b) kills the only other
input, the stage machine collapses to: **`breadth > 0.50` → RE-RATING → "do not chase" → entry hard-blocked**
(`foresight_cascade.py:51,65,74,110-112`). All 9 RE-RATING verdicts in the shipped artifact are driven purely
by a saturated snapshot level crossing an arbitrary line — with zero change/direction input.

**Net:** the desk enters on nothing and dismisses everything, using a single lagging, saturated, uncalibrated
variable — and (see §4) it then re-uses that same variable two more times.

---

## 4. The composite outputs are hollow

### 4a. The 0–100 score is a 37–50 band with ~1.5 real axes — **CRITICAL**

- **Range collapse:** `base = Σ(weight·axis)·100` (`foresight_score.py:130`) computes 55–64 for AI themes, then
  `min(base, 50)` always binds because `physical_confirmed=False` for all (`:134-136`). The top half of the
  scale (50–100) is unreachable; the `verdict` thresholds "high-conviction ≥70 / constructive ≥55" (`:143-150`)
  are dead code. Four themes tie at exactly 50.
- **2 of 7 axes are frozen defaults, and they are the same absent data counted twice:** bottleneck axis = `0.4`
  placeholder (`:124`) and pricing_power = `0.4` default (`:90-94`, reads the null `tightness`). That is 0.35 of
  total weight fed as if measured.
- **Magnitude is a binary membership flag:** `_magnitude()` = `clamp(capex_yoy/60, 0.35, 1.0)` (`:37-44`); every
  capex theme carries the identical `capex_yoy=69` → 1.0 for all six, 0.2 for everything else. It is
  `AI-capex ? 1.0 : 0.2`, not a magnitude estimate, and it cannot separate the AI themes from each other.
- **Underpricing is circular with T4:** `_underpricing() = clamp(1 − 0.9·breadth, …)` (`:97-104`) — a
  deterministic inverse of the *same* revision_breadth that sets the stage and the cap. So breadth penalizes the
  score **three times** (stage → cap → underpricing axis). Since underpricing is the only materially-varying,
  non-degenerate axis, **the "7-axis score" is effectively `f(revision_breadth)` in a costume.**
- **"Tuned via ledgers" is false:** the docstring (`:16-19`) claims weights are tuned only via the
  forward-grading ledger; the weights are hardcoded literals (`:27-28`), the ledger doesn't exist, and no code
  path reads `track_record.json` back into `WEIGHTS`. The loop is not wired even in principle.

### 4b. Sizing is stage relabelled; the exit discipline can never fire — **HIGH**

- `size_mult`/`size_band` are a pure function of `stage` (`foresight_sizing.py:29-31,50-98`); the stage caps
  (RE-RATING 0.25, WATCH 0.10) always dominate the score term (≤0.50). Sizing carries zero information beyond
  the stage badge — the same stage encoded twice more.
- **The forced de-risk rule — sold as "where HBM won / ARK lost" — can never activate.** EXIT needs
  `stage==GLUT-RISK`; TRIM needs `glut_on and crowded` (`:59-64`); both need a firing glut band, which is always
  `AWAITING_DATA`. `n_derisk=0` in perpetuity.
- **The "effective number of independent themes" decomposition is unreachable.** `constructive = thesis-stage or
  score≥55` (`:101-121`) — both conditions impossible — so it degenerates to `"no constructive themes"`
  (`:117`), and the concentration-truth output (the desk's own stated defense against the ARK failure) never
  renders. The desk both *suffers from* extreme concentration (§7) and *fails to measure it*.

---

## 5. The "intelligence" is unfalsifiable theater

Severity: **CRITICAL**. This is the cluster that most undermines the institutional claim.

**(a) The grading deadlock — the keystone of the keystone.** The forward-grading loop, which every doc calls
"the intelligence," grades exactly zero flags and structurally cannot grade any:
`T1 dark → no TIGHT band → no PRECIPICE/BROADENING → `_append_ledger` writes nothing (`foresight_cascade.py:307`)
→ `data/foresight/log.jsonl` never created → grader reads zero (`foresight_grader.py:195`) → n_graded=0 forever.`
The desk publishes a "Forward-graded track record" panel (`templates/foresight.html.j2:430-456`) that
**can never show a hit-rate**. The one thing that would make it institutional — a real, honest, accruing track
record — is architecturally impossible in the current state. Note `n_pending=0` too: nothing is even pending,
which contradicts the panel's own "flags logged, grading forward" framing.

**(b) The loop isn't a loop.** Even if flags accrued, `grade()` output (`track_record.json`) is never read by any
scoring/weighting/thresholding code — it is a pure display counter (only readers: `build_foresight.py:88-89,30-54`).
Nothing recalibrates. "Closed learning loop" (per the design doc's Phase-5 "god-tier" claim) is not wired.

**(c) The LLM analyst is dark and its one safety rule is porous.** `foresight_analyst.py:167-175` returns `None`
without an Anthropic credential (`altdata_brain.py:133-146`) → the "🧠 AI analyst read" block never renders
(`template:254`). And the load-bearing "FORBIDDEN to forecast a price" rule is a regex *dropper* that scans only
`mechanism`/`non_obvious`/`dissent` (`foresight_analyst.py:128-133`) — **not** `kill_criteria`, `evidence`, or
`regime_read` — and there is **no citation/substring grounding** of quotes anywhere (the "cites the surface behind
every claim" contract is prompt text only). So the safety guarantee is both incomplete and untested in production.

**(d) The thesis monitor is circularly dependent on the LLM.** `thesis_monitor.py:31,62-63` reads open theses
from `data/foresight/analyst_theses.jsonl`, which only the LLM analyst writes. No credential → no ledger →
monitor returns `None` → the THESIS-BROKEN chip can never fire. The *deterministic* break-detector's existence
is entirely contingent on the *non-deterministic* LLM having run — the exact inversion of the stated design
(deterministic monitor keeps the expensive model out of the daily loop).

**(e) A published-copy correctness bug.** The grader implements Benjamini-**Yekutieli** (`foresight_grader.py:141-146`)
but the user-facing panel advertises "Benjamini-**Hochberg** FDR gate" (`template:432`). BY is materially more
conservative; the page names the wrong (weaker) test. The survivorship "bankruptcy-imputation" path is also dead
(`_dead_closes` needs `data/edgar/dead_name_prices.parquet`, which doesn't exist, `foresight_grader.py:63-81`),
so the headline "survivorship-free, delisted members graded at their loss" overstates what the data supports.

---

## 6. Correlated legs sold as independent (the convergence board)

Severity: **HIGH**. The marquee "🔥 What's heating up early" board is the page's headline visual and its
credibility claim ("independent leading surfaces converging"). Two problems:

- **It is always empty.** `heat = (n_signals/6)·earliness·(0.75 physical-dead)` (`foresight_convergence.py:109`);
  live max heat is **0.157** against a **0.55** bar (`:40,125`). The grid never populates; the page shows the
  "Nothing is converging hot right now" copy plus a strip of sub-0.16 chips.
- **`earliness = 1 − breadth`** (`:105`) is anti-correlated with signal strength: the themes with the most lit
  surfaces are the saturated-breadth AI themes, whose earliness is ~0 (memory 0.045, semicap 0.074). So even if
  the board fired, its own weighting **buries exactly the themes with the strongest confirmed demand** and floats
  thin, low-signal names (defense, medical devices) to the top.
- **The "surfaces" are not independent.** Demand is one shared capex number replicated across six themes
  (`demand_capex.py:5-12`; all six = 69.0). `subsector_scarcity` and `discovery_echo` read the **same**
  `data/edgar/emergence_hits.parquet` (`subsector_scan.py:65` + `theme_emergence.py:72`) — one EDGAR phrase sweep
  counted as two independent corroborating surfaces. A theme can light 3 of 6 surfaces from effectively **2
  sources**. "Multi-surface agreement raises precision" overstates the independence.

This is the apex of a desk-wide pattern: **shared/correlated inputs presented as per-theme differentiated,
independent reads** — the demand pool (1 number × 6), the physical map (3 NAICS × 7), the guidance filers
(GEV drives both nuclear_power and grid_electrification), the convergence surfaces (2 sources → 6 "surfaces").

---

## 7. The leading confirmers are degenerate

Severity: **HIGH**.

- **Demand (T2) gives zero cross-theme discrimination and may have the sign backwards.** One
  `demand_chain.compute_signals()["ai_datacenter"]` number is written identically onto every AI theme
  (`demand_capex.py:61-92`); the only per-theme field is a static `strength` string (direct/lagged/indirect,
  `:29-36`). And the desk uses accelerating *buyer* capex as a *bullish* confirmer (`foresight_cascade.py:198-199`),
  which inverts the best-documented capex anomaly (Cooper–Gulen–Schill: high asset/capex growth → **negative**
  forward returns for the spender). The beneficiary-chain argument is defensible but **asserted, never validated**,
  and +69% YoY is simultaneously the desk's bullish "demand confirms" signal *and* precisely the late-cycle
  over-investment the (dark) glut leg is meant to fear — an internal contradiction. Also fragile: `_trend()`
  flips the +69% narrative from "accelerating" (bullish) to "peaking" (cautionary) on the mere presence of a
  third annual data point (`demand_chain.py:109-118`).
- **Guidance (T3) has a category error and a 2-filer gate.** `"above the high end"` is in the RAISE lexicon
  (`edgar_guidance.py:52`) but is an *earnings-beat* phrase, not a forward guidance raise — and it is 4 of the 9
  hits, including both filers (FORM, MKSI) behind `semicap_equipment`'s only RAISING tilt. A whole theme's
  guidance verdict flips on **two 8-Ks** (`MIN_FILERS=2`), with no negation handling (the docstring admits "not
  raising guidance would match") and no off-cycle Item-2.02 detection (advertised as the leading edge, never
  implemented — no `items=` filter anywhere). GEV double-counts across two themes.
- **The live discovery legs rest on fragile text.** `theme_emergence` does produce 5 candidates, but they include
  SIC 2834 (Pharmaceutical Preparations, with `velocity:0` — clearing on filer-count alone) and 3841 (Surgical &
  Medical Instruments) — exactly the false positives the manufacturing-phrase gate claims to exclude.
  `subsector_scan` synthesizes a `TIGHT` band whenever ≥2 members appear in the EDGAR phrase table
  (`subsector_scan.py:110-111`) — making it **the desk's only source of any TIGHT/actionable stage**
  (12 PRECIPICE/BROADENING rows in its log vs 0 in the curated cascade), all of it text-only, negation-blind
  ("we are *not* capacity constrained" counts), and double-counting the same parquet as discovery.

---

## 8. Untapped leading signals sitting idle in sibling pages

The repo already computes richer, more genuinely-leading signals than anything the cascade consumes — they are
built, displayed, and never wired in. This is the clearest upgrade surface.

| Signal (page / engine) | Character | Wired? | Highest-value contribution to foresight |
|---|---|---|---|
| **Per-name demand divergence** (`demand.html` / `demand_chain.py`, `demand_ledger.py`) | LEADING | Only the scalar pool | 3 independent chains (capex / housing / RPO) + **per-tier + per-name** divergence (ahead-of-consensus vs aligned). Replaces the single +69% applied to all six AI themes with *which members are truly early*. **The single biggest fix to §7's non-discrimination.** |
| **News-velocity acceleration** (`radar.html` / `radar.py`, `theme_activity.py`) | LEADING (short) | No | Activity *acceleration* (not state) as a pre-revision turn: theme where news/activity is rising while breadth is still flat = the BROADENING precursor the dead `breadth_accel` was meant to catch. |
| **Deal / activist catalysts** (`special_situations.html` / `special_situations.py`) | LEADING (event) | No | 18 event categories with stage pipelines (activist 13D, M&A, go-private). Catalyst clocks for theme members — urgency + asymmetric deal-failure risk the entry overlay is blind to. |
| **Insider-into-quiet-tape divergence** (`intelligence_hub.html` / `intelligence.py`) | LEADING | Only the count | Foresight gets the insider/award *count* but not the news backdrop. Insider cluster *while tape is quiet* = pre-**narrative** entry (earlier than pre-revision) — a true inverse-to-attention timing signal. |
| **Asset-class cycle regime** (`cycle.html` / `cycles.py`) | Context/durability | No | Gate `entry_ready` on cycle position: BROADENING in early cycle = runway; in late cycle = exhaustion. The HBM tariff-flush entry worked partly because HBM was in an early-cycle pivot. |
| **Rotation leadership** (`subsector_rotation.html` / `subsector_rotation.py`) | LEADING (momentum) | No (parallel taxonomy) | RS-ratio/momentum + velocity screen for micro-leadership shifts pre-consensus. Needs reconciling the Finviz 40-theme taxonomy with the 18-theme cascade. |

**Duplication to resolve, not just gaps:** `subsector_scan` (foresight's engine) and `subsector_rotation.html`
run *parallel, unreconciled* sub-industry taxonomies (one bottleneck-proxy, one momentum). And within foresight,
`theme_emergence` + `subsector_scan` + the convergence "discovery echo" are three views of one EDGAR parquet.

---

## 9. Deep-reasoning synthesis — the meta-problems Fable should solve *for*

Beyond the itemized bugs, five structural pathologies explain *why* the desk drifted from its design. These are
the real targets.

1. **Silent single-point-of-failure + camouflage.** The whole desk hinges on one data feed that isn't landing,
   and the "return None on shortfall" contract hides it behind a complete-looking page. **A foresight desk needs
   a first-class data-health/"what's live" surface** that states, per leg, LIVE / AWAITING / DEGENERATE — and
   that visibly downgrades the desk's self-description when its leading legs are dark. Honesty at the leg level is
   not honesty at the page level.

2. **The guardrails became the product.** Caps (text-only 50, WATCH 45) and gates (PRECIPICE-requires-TIGHT) were
   designed as occasional guardrails against over-claiming. With the physical layer absent they are *unconditional*
   and dominate every output — the desk's product *is* the caps. Any redesign must ensure the guardrails bind
   rarely (i.e. the leading legs must actually be live) or the desk is just a clamp.

3. **The leading/coincident inversion.** The founding charter says LEAD on bottleneck/capex/pricing; treat
   revision breadth as a coincident confirmer; never enter on it. The shipped desk does the exact opposite — it
   runs on breadth *level* (worse than its change), and uses that one lagging variable three times (stage, cap,
   underpricing). Fixing this is not a tuning problem; it requires *actual leading inputs* (§2, §8) so breadth can
   return to its intended confirming-only role.

4. **"One bet in N hats" — undiagnosed concentration.** The desk repeatedly re-uses shared inputs as if they were
   independent per-theme reads (§6), and the very tool meant to expose this (effective-N) is unreachable (§4b).
   Memory / packaging / power / grid / semicap / turbines are largely **one hyperscaler-capex bet**; the desk
   neither resolves them to distinct signals nor tells the user they're correlated. Genuine institutional grade
   means measuring and *displaying* the effective number of independent bets.

5. **Unfalsifiability.** The desk cannot currently be proven right or wrong (§5) and does not learn from its own
   record even in principle. The path to "intelligent" is not more legs — it is (a) making at least one leading
   leg live so flags accrue, (b) logging *all* stages (not just the unreachable ones) so the grader has data,
   (c) wiring the grader back into the weights/thresholds, and (d) grounding the LLM in citations with a real
   forecast clamp. Until then, "forward-graded" and "learning loop" are aspirational labels on empty machinery.

---

## 10. Prioritized upgrade directions (problem → direction; leave the unique design to Fable)

Ordered by *unlock-per-effort*. Each is a problem statement + a direction, not a finished spec.

**P0 — Make the leading core actually live (unblocks §1→§5 simultaneously).**
- Land the `fred.series.bottleneck` + `fred.series.power` series in `data/fred/` (operational: confirm they fetch
  in CI, are committed, and resolve in `_series`). This single fix flips T1/power on, which un-caps the score,
  makes PRECIPICE reachable, starts the ledger accruing, and lets the convergence board fire.
- **But do not stop there** — even lit, T1 is coarse (3 NAICS × 7 themes) and 11 themes are unmappable. Fable's
  unique work: a *per-theme* physical read (queue depth for power/grid/nuclear; packaging-throughput vs logic-die
  for semis; supplier backlog via `edgar_rpo` rather than buyer capex) and a physical proxy for the 11 orphan
  themes or an explicit "no physical correlate — text-only" class that the UI states honestly.

**P0 — Wire the dead EDGAR language leg into the band/score.** It has real data (§2) and is the closest free
analog to the "sold-out" HBM tell. Direction: add it as a weighted leg *with* negation/context handling (the
current substring match counts "not capacity constrained" as tightness). This is likely the single fastest way to
get a genuine PRECIPICE flag while FRED lands.

**P1 — Fix the revision-breadth measurement (§3).** Direction: (a) normalize breadth by *coverage*, not just
revisers, to kill the saturation; (b) accrue enough PIT history (or shorten the accel lookback with a documented
minimum-n) so `breadth_accel` — the leading piece — actually computes; (c) recalibrate or replace the arbitrary
`BROAD_HI=0.50`; (d) stop using breadth three times — pick one role (confirmer) and give underpricing a *real*
inverse-attention input (ownership/coverage/search), not `1−breadth`.

**P1 — Replace the demand scalar with per-name/per-tier divergence (§7, §8).** The richest, already-built,
highest-leverage fix. Consume `demand_chain.py` divergence so themes get distinct demand reads, and *validate the
sign* (Cooper–Gulen–Schill) before treating capex acceleration as bullish.

**P2 — Make the desk falsifiable and self-monitoring for real (§5).** Log *all* stage flags (not just
PRECIPICE/BROADENING) so the grader accrues immediately; wire `track_record.json` back into weights/thresholds;
fix the BY/BH label; ground the LLM in exact-substring citations and extend the forecast clamp to all output
fields (and clamp, don't just drop). Give the deterministic monitor a non-LLM source of theses so BROKEN can fire
without a credential.

**P2 — Rebuild convergence around genuine independence + honest earliness (§6).** De-duplicate the shared
sources, weight surfaces by their true (low) independence, and reconsider `earliness` so it does not bury the
demand-confirmed themes. Consider replacing the count-based heat with an information-weighted score.

**P3 — Wire the untapped sibling signals (§8) as *confirmers/timers*, not stage-changers.** News-velocity
acceleration (pre-revision turn), special-situations catalysts (entry clocks), insider-into-quiet-tape (pre-narrative
timing), cycle regime (durability gate for `entry_ready`), rotation leadership. Keep the house rule: correlation-
penalize and make each inverse-to-breadth.

---

## 11. What is genuinely good — preserve it

So Fable doesn't throw out the architecture with the bugs:

- **The cascade *taxonomy* is correct and rare.** Lead-time tiers (physical LEADS → demand/guidance pre-signal →
  revisions CONFIRM → entry deferred to dislocation → glut = exit clock) is exactly the right mental model for
  front-running a theme. The problem is empty inputs, not the frame.
- **STAGE-not-score, ranked by edge-remaining** is the right primitive (elevated agreement = late, not better).
- **The honesty *instincts*** (display-only, None-on-shortfall, text-only caps, forward-grading, no point-dates,
  crowding-is-negative, snapshot membership at flag time for leak-free grading, `foresight_cascade.py:302-312`)
  are institutional-grade *intentions*. They just need to bind rarely (live legs) and be surfaced at the page level.
- **The statistical machinery** (Wilson CI, BY-FDR step-up, survivorship handling) is competently coded and ready
  the moment data flows — it is moot, not wrong.

---

## 12. Handoff to Fable — open questions to solve uniquely

1. **Is P0 purely operational (land the FRED series) or is the collector genuinely unable to fetch them in
   production CI?** Resolve this first — it changes whether this is a one-line config fix or a collector rebuild.
   (Evidence says reachable + configured + not committed → operational, but confirm in CI.)
2. **How to get *per-theme* physical resolution** where free data gives only 3 NAICS buckets for 7 themes — the
   queue-pipeline / RPO-backlog / packaging-throughput directions in the upgrade blueprint are the candidates;
   which are real and free?
3. **What is the honest earliness signal** that isn't `1−breadth`? (Coverage growth, ownership breadth, search
   attention, options positioning — each with its own decay and crowding caveat.)
4. **Should the 11 orphan (non-physical) themes stay in the desk at all**, or move to a clearly-labelled "text-only
   watch" tier so the physical desk isn't diluted?
5. **How to display "one bet in N hats"** — the effective-independent-themes decomposition — so the user sees the
   concentration truth even when (especially when) everything is an AI-capex derivative.
6. **What is the minimum viable falsifiability**: which single leg, made live, starts the track record accruing
   fastest, and how to log *all* stages without over-claiming on the un-actionable ones?

---

*Provenance: six parallel deep-read audits (Opus-orchestrated) of the shipped `foresight.html` engine stack +
committed `foresight_cascade.json` + `track_record.json`, cross-verified against `data/fred/`,
`data/revisions/`, `data/edgar/*`, `config.yml`, and the sibling signal pages. All `file:line` citations verified
against the live worktree at HEAD `8ea5c60f3d`. This audit describes the desk as it ships on 2026-07-01; it does
not modify any engine. Solution design, unique implementation, and add-ons are Fable's second pass.*
