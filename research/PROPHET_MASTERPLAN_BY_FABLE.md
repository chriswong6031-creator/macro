# Prophet — standout governance, per-pick self-assessment, and the unified pick brain

Status: MASTERPLAN (W0). Author: Fable, 2026-07-17. Operator directive 2026-07-17:
move the us_stocks Track Record to its own sub-page with real statistics and history;
give the responsible lobe direct access to its own performance metrics with granular
one-by-one pick postmortems (why each failure failed, whether it was mitigable, why
each success succeeded and which engines deserve credit); establish a governing lobe —
**Prophet** — under the Neural Web that manages the standout systems across US, China,
HK, Canada and the international dashboard, runs self-improvement loops on its boards,
engines and candidate pipelines, audits its own dashboards for accuracy, and
communicates suggestions to Master Brain; add Prophet to the admin panel directly under
Master Brain; grant Prophet, Master Brain, and the Mastermind AI top layers the ability
to reason on Fable with token conservation.

Grounding: 10-lane census 2026-07-17 (track-record UI, pick lab, neural web, Master
Brain/metabolism, admin panel, SA program, standout engines, LLM lanes, winner-autopsy
/CRX, Mastermind repo). This charter EXTENDS the shipped Standout Accountability
program (`research/STANDOUT_ACCOUNTABILITY_MASTERPLAN_BY_FABLE.md`, SA-R1..R16, all
six waves merged 2026-07-12) — it duplicates none of it. Where the operator directive
revives an SA deferral (HK/CA extension, SA-R12; armed-caller decision, W6 docket
item 2), this document is the explicit ruling SA required.

---

## 0. Executive ruling — the reading layer exists; Prophet is the governor above it

The census found the per-pick accountability substrate ALREADY BUILT and accruing:
deterministic two-axis attribution (outcome-cause × process-fault) on US+CN matured
picks (`engine/standout_audit.py`, `engine/china_standout_audit.py`), an Opus audit
lane writing cohort postmortems (`engine/metabolism/standout_auditor.py`), fitness
sensors with anti-reward-hacking clamps, a shadow-first improvement lane
(`engine/standout_review.py`), experiment books (Pick Lab, 28 US + 20 CN + HK), and
lab Accountability surfaces. What the operator asked for and does NOT exist:

1. a real Track Record page (today: a collapsible strip on us_stocks reading
   `us_board_outcomes.json`; the deeper `us_board_track.json` hit-rate/Wilson record
   is built nightly and barely surfaced);
2. per-pick, one-by-one LLM postmortems (SA writes cohort prose only);
3. any cross-market read — five boards, five heterogeneous ledgers, no unified
   governor ("no unified cross-market performance reader" — census verdict);
4. HK/CA/intl accountability (SA-R12 deferred it; operator now orders it);
5. a lobe-to-Master-Brain suggestion surface mirroring what the Mastermind bot
   already has (nudges via the reverse bridge);
6. an admin Prophet page;
7. any Fable model grant (no `claude-fable-5` anywhere in config, pricing, or lanes).

**The ruling:** charter **Prophet** as the standout-governance program and a single
new NW lobe that federates the existing accountability machinery, extends it
per-pick and cross-market, and surfaces it to the operator — reusing every SA rail
and inventing no new authority path.

## 1. Rulings

**PR-R1 — Prophet is ONE new NW lobe; it federates, it does not replace.** A new
synapse artifact `prophet-status` (`data/neuralweb/prophet_status.json`, producer
`engine/neuralweb/prophet_governor.py`, owner_program=neural-web, tier=display,
horizon_role=context) plus a `prophet` charter in `config/lobe_charters.yml` with
dict-form fitness_sensors. The existing loop-manageable lobes `site-us-standouts` and
`site-china-standouts` KEEP their charters, sensors, and clamps — Prophet is the
governor that reads their cards, not their replacement. HK/CA/intl accountability
rides UNDER Prophet's charter (per-market blocks inside `prophet_status.json`), NOT
as new per-market lobes. Roster: this takes `max_active_nonscored_lobes` 65 → **66 of
66 — the roster is FULL**. Stated plainly for the next charter: any further lobe
genesis requires an operator cap raise in `config/metabolism_budget.yml` (operator-tap
file). The operator directive of 2026-07-17 is the explicit ruling SA-R12 required to
extend accountability to HK/CA.

**PR-R2 — Naming: Prophet is the internal/program/admin name; public copy is
unchanged this program.** The existing `prophet-trade-plan` / `prophet-management-state`
artifacts (owner_program=momoedge; US buy-lane → trade-plan envelopes with options
recs, forward ledger `data/prophet/ledger.jsonl`) become Prophet's first
cross-connected member — they are exactly the "Mastermind Charts options picks
integrated with the dashboard" end-state the operator described, already living in
this repo. They keep their program tag and schemas; Prophet reads them display-only.
The public-facing "Standout" vocabulary on the country dashboards does NOT change in
this program: a public rebrand is a design wave of its own (mockups-first law,
DESIGN_DOCTRINE §5.6; precedent: the deferred public Breakaway Desk,
WINNER_AUTOPSY masterplan §8). Follow-up docket row, not a wave.

**PR-R3 — Per-pick autopsies: deterministic numbers, LLM prose, extremes-first,
capped.** The SA §3 two-axis attribution (loop-IMMUTABLE constants, untouched)
remains the sole numeric attribution. On top of it, the audit lane
(`engine/metabolism/standout_auditor.py`) gains a per-pick postmortem stage: for each
audit cycle it selects matured picks extremes-first — top-K winners by 21d excess,
bottom-K losers, all `gate_suppressed` near-misses, all `data_fault` rows (K and a
per-cycle hard cap in the `prophet:` config block; default cap 12 picks/cycle —
token economy) — and writes ONE prose artifact per pick to
`data/standout_audit/pick_autopsies/<market>/<pick_id>.json`: the deterministic
attribution row verbatim, an LLM root-cause narrative (what drove the outcome; was
the failure mitigable with information available AT ENTRY, or external/irreducible;
which upstream organ states were concordant/discordant), a mitigation verdict from a
CLOSED enum (`mitigable_process` / `mitigable_conditioning` / `external_unforeseeable`
/ `external_foreseeable_unpriced` / `not_a_failure`), and a lesson line tagged with
which engines/books surfaced or missed the name. Success-side narratives may use the
winner-autopsy descriptive vocabulary (mechanism taxonomy, 5-stage anatomy) as PROSE
fields. **WA-R10 fence respected:** no join of pick outcomes into `winner_episodes`
aggregates; where a winner-autopsy case file exists for the same ticker/window, the
autopsy carries a display-only crosslink, never a merged statistic. NW-ART1/SA-R2
unamended: the LLM writes prose and hypothesis tags; every rendered number is
deterministic; nothing escalates.

**PR-R4 — Prophet speaks to Master Brain on the existing rails.** Emissions are
(a) `insight_bus.jsonl` rows (the sole inter-lobe channel — stigmergy law) carrying
evidence-pack-backed findings, and (b) a committed suggestions artifact
`data/neuralweb/prophet_suggestions.json` mirroring the Mastermind nudge schema
(kind ∈ {contract_drift, coverage_gap, staleness, lobe_request, other}; detail ≤160
chars; ≤10 rows), rendered on both the Master Brain and Prophet admin pages.
Suggestions that target OTHER lobes' domains (e.g. "sector-rotation ranker lagged
this cohort's failures") route through AGENDA to those lobes; **Prophet never edits
another lobe's code, config, or state directly.** This is the in-repo mirror of the
Mastermind reverse bridge the operator cited, built on channels that already exist.

**PR-R5 — Cross-market honesty: no pooling across fill conventions.** CN grades at
T+1 HL2 fill; US/HK/CA at next-bar close; intl has no stock ledger and its residual-
alpha base score is self-described context, not a validated ranker. Therefore
`prophet_status.json` carries per-market blocks with each market's own benchmark,
fill basis, and maturity state; cross-market cells are counts/coverage/process-fault
rates with per-market receipts — never pooled return statistics. The intl block
prints its unvalidated-base-score disclosure. Effective-N law (SA-R10) binds every
cell; ACCRUING printed, "validated" CI-banned.

**PR-R6 — Dashboard-integrity audits are first-class (SA-R11 extended).** The
auditor context gains a deterministic dashboard-integrity block per market: artifact
staleness vs SLA, data_gap sentinels, dead-wire probes (registered artifacts with no
reader), act-now/board copy drift flags. LLM findings become `data_fault`-class
proposals or `prophet_suggestions` rows. Autonomous changes to Prophet's own
dashboards ride the EXISTING metabolism BUILD lane (sonnet draft PRs, adversary
two-key, fenced merge) under the federated charters — no new write path, no new
autonomy tier.

**PR-R7 — Candidate/signal authority: the SA-R5 three-speed ladder, verbatim.**
Prophet may spawn Pick Lab experiment books (new engine_id, PL-R2/R4), request
replay counterfactuals, and propose shadow config variants. Promotion of ANY signal,
book result, or "past good result" into board authority requires the gauntlet at the
pre-registered ruler. Onboarding a signal because its ledger looks good is exactly
the laundering SA-R5/HOUSE-U4 forbid — the path is replay → experiment book →
gauntlet → operator-visible promotion, and nothing shorter.

**PR-R8 — Fable grant (macro side), token-conserving.** `config.yml llm_models`
gains `deliberation: claude-fable-5`; `config/ai_pricing.yml` gains the matching
prefix row so spend is metered from call one. Granted lanes — and ONLY these:
(a) the Prophet/standout auditor reasoning stage (cohort + per-pick postmortems);
(b) Master Brain's orchestrator top stages (PROPOSE orchestrator + ADJUDICATE
adversary). Each reads the deliberation tier through its `_LLM_CFG`/config with an
explicit model-not-found fallback to `claude-opus-4-8` (the waterfall handles
401/429, not 404s). BUILD stays sonnet; extraction/classify stay haiku; the fable-
doctrine preamble is auto-omitted for Fable models (`_is_opus_class` already
handles this). Budget honesty: OAuth subscription usage does NOT advance the $25
metered breaker — the grant therefore ships with a per-cycle deliberation-token cap
in the `prophet:` config block and a usage_lane so the AI Cost hub shows Fable spend
separately. The Mastermind-bot top-layer grant is a **Mastermind-repo change** and is
chartered as a follow-up there (PRD-R1 boundary respected).

**PR-R9 — The Track Record sub-page is Tier-3, off-render, honest.** New page
`site/us_track_record.html` (template `templates/us_track_record.html.j2`), baked by
a read-only builder running in the `standout_audit_us` off-render job (the render
path gets zero new work — SA-R9). Content, all from committed artifacts: headline
glance block (state + plain-word stance); rolling win-rate / average- and
median-excess history with a new nightly-appended rollup artifact
`site/factordata/us_track_history.json` (time series of board size, win rate, avg/
median pct, lane mix, failure-mode mix once attribution rows mature); return
distribution; horizon ladder from `us_board_track.json` (5/10/21/63d, Wilson CIs,
precision@k); the two loss ledgers side by side (SA-R3); coverage monitor; per-pick
outcomes table (from `us_board_outcomes.json` + attribution joins) with autopsy
digests as they accrue; survivorship and accrual disclosures in plain words. The
us_stocks strip slims to a glance chip (state + one line + link). Trend verdicts
("improving / flat / degrading") appear ONLY once the SA-R10 effective-N floors are
met for the compared windows; before that the page prints the accrual clock in plain
words. Bilingual EN/ZH dual-span; no internal vocab at glance tier; one as-of; CN/HK
/CA page ports are follow-ups after the US page settles.

**PR-R10 — Hygiene inherited wholesale.** SA-R14 (store hygiene, one-grader law),
SA-R15 (committed stores only; absent store ⇒ data_gap, never zero), SA-R16
(never-raise + freshness stamps + corrupt-artifact tests), lane gates fail-closed.
W2 also FIXES the census-found gap that HK/CA `board_ledger.append_board` writes on
every render (no lane gate — duplicate-row risk on re-renders): both get the
canonical `ledger_lane` gate with tests, as a data_fault repair Prophet's own audit
would have filed.

## 2. Architecture (one picture)

```
 five standout engines (UNTOUCHED)          existing SA organs (UNTOUCHED)
 us/cn/hk/ca/intl builders                  standout_audit.py (US) · china_standout_audit.py (CN)
   │ boards + forward ledgers                 │ attribution parquet + evidence + fitness cards
   ▼                                          ▼
 NEW engine/neuralweb/prophet_governor.py  (off-render + asia-lane readers, committed inputs only)
 ├─ per-market performance blocks (PR-R5)  data/neuralweb/prophet_status.json   [prophet lobe]
 ├─ dashboard-integrity blocks (PR-R6)
 ├─ suggestions artifact (PR-R4)           data/neuralweb/prophet_suggestions.json
 └─ Track Record page payload (PR-R9)      site/factordata/us_track_history.json → site/us_track_record.html
   ▼
 engine/metabolism/standout_auditor.py — EXTENDED: per-pick autopsies (PR-R3, Fable-granted PR-R8)
   → data/standout_audit/pick_autopsies/<market>/<pick_id>.json
   → insight_bus rows + prophet_suggestions → AGENDA → Master Brain (orchestrator)
   ▼
 improvement lanes (EXISTING, unmodified law): standout_review.py A6 lane-(ii) ·
 Pick Lab experiment books · plain data_fault fix PRs · metabolism BUILD (sonnet)
   ▼
 admin: NEW Prophet page directly under Master Brain (NAV_GROUPS[1] index 3) —
 cross-market record, autopsy digests, suggestions, loop status, Fable spend, settings
```

## 3. What Prophet's postmortems must reason about (operator taxonomy, seeded)

The LLM stage is prompted with (and free to extend, as prose only) the operator's
cause families. Failures: missed/late sector-rotation read; extended-sector rollover;
fake breakout / failed cycle (mostly irreducible — but check whether a weak-sector or
rotation read was available at entry); external news/event (was the RISK visible ex
ante — earnings proximity, event-window flags — even if the event itself was not);
process faults (chased late, gate margin thin, stale data). Successes: rotation
identified early; T1–T4 confluence timing; momentum preceding news (the SBUX
pattern — technicals front-running announcements); external re-rating with visible
ex-ante accumulation. Every narrative must separate outcome from process (SA-R13
verbatim in the prompt) and name which engines/books were role models vs laggards
for THAT pick — this engine-credit line is the raw material for cross-engine
improvement hypotheses, and it stays prose until a gauntleted study says otherwise.

## 4. Wave docket

Hygiene binding on every wave: fresh worktree off origin/main; sonnet builds, opus
adversarial review, Fable (main loop) merges; synapse count-pin bump + SIGNAL_BUS
regen + lobe-prose `--update` in the same PR as any registry change; dag.yml
declarations for new scripts; tests in ci.yml whitelist; never-raise + freshness
stamps; `$RUNNER_TEMP`; no `validated`; bilingual dual-span; template/site pairing
rules; local builders must be read-only over committed artifacts before being run
for the initial bake.

| Wave | Contents | Primary files |
|---|---|---|
| PR-W0 | this charter | `research/PROPHET_MASTERPLAN_BY_FABLE.md` |
| PR-W1 | US Track Record sub-page (PR-R9): history rollup emitter in the off-render audit job; page builder + template; strip slimmed to glance chip + link; synapse/dag/pins/tests | `scripts/build_track_record_page.py` (new), `engine/standout_audit.py` (additive emitter), `templates/us_track_record.html.j2` (new), `templates/dashboard.html.j2`, `.github/workflows/daily.yml`, `config/synapse.yml` |
| PR-W2 | Prophet lobe + governor (PR-R1/R4/R5/R6): `prophet_governor.py`, `prophet_status.json`, `prophet_suggestions.json`, charter + sensors, per-pick autopsy stage in `standout_auditor.py` (PR-R3), HK/CA `append_board` lane gates (PR-R10), insight emissions, prose + pins | `engine/neuralweb/prophet_governor.py` (new), `config/synapse.yml`, `config/lobe_charters.yml`, `engine/metabolism/standout_auditor.py`, `engine/board_ledger.py`, `admin/nw_lobe_descriptions.py` |
| PR-W3 | Admin Prophet page under Master Brain + Fable grants (PR-R8): panel module, route, SPA nav/render, `prophet:` config block + settings spec, `llm_models.deliberation`, pricing row, auditor/orchestrator model wiring with opus fallback, update.sh lazy-import globs | `admin/prophet.py` (new), `admin/server.py`, `admin/static/app.js`, `config.yml`, `config/ai_pricing.yml`, `engine/metabolism/standout_auditor.py`, `engine/metabolism/propose.py`, `engine/metabolism/adjudicate.py`, `app/deploy/update.sh` |

Dependencies: W1 → W2 → W3 sequential (shared synapse pins and config surfaces).

Follow-up docket (chartered, not built here): (1) Mastermind-repo Fable grant for
its top orchestration/assessment layers; (2) CN/HK/CA Track Record page ports;
(3) public Prophet rebrand design wave (mockups-first); (4) intl stock-level forward
ledger + pick lab (prerequisite for intl accountability parity); (5) armed caller
for the audit lane (SA W6 docket item 2 — still requires its own two-key when the
loop arms); (6) Prophet↔Mastermind-Charts options cross-connect (options data joined
into pick context at entry).

## 5. Refusals of record

- No LLM-originated signals, scores, or escalations; no LLM numeric confidence
  (NW-ART1, TI-R1, CHF-R14 extension). Autopsies are prose + closed-enum tags.
- No pooled cross-market return statistics across fill conventions (PR-R5).
- No promotion or live config flip on replay/ledger evidence (SA-R5 ladder).
- No new autonomy tier, no arming changes, no edits to other lobes by Prophet
  (PR-R4); AUTONOMY_PAUSED and the fences stand.
- No public rebrand this program (PR-R2). No winner_episodes joins (WA-R10).
- No new render-path compute (everything off-render or asia-lane-ticked).
- No held-position/live-book monitoring in this repo (PRD-R1/R2).
- No Fable on BUILD/extraction lanes; deliberation lanes only, capped (PR-R8).

## 6. Clocks

- First per-pick autopsies: first audit-lane fire after matured 21d rows cross the
  SA-R9 trigger (US expected ~2026-08; the deterministic page and governor ship
  useful state immediately).
- US sensor maturity (trend verdicts unlock): ~2026-09-15; CN ~2026-10-15 (SA §10).
- Track Record trend module honesty gate: same floors; before that, accrual clock
  in plain words (PR-R9).
- Quarterly review of the Fable grant spend vs value: first due 2026-10-15,
  alongside the lane-(ii) re-audit clock.

## PR-R2 Amendment 1 (2026-07-18, operator order)

Public rebrand initiated by operator order 2026-07-18. The original PR-R2 refusal
("No public rebrand this program") is superseded for branding surfaces only;
internal identifiers are fully unchanged (see below).

### Naming table

| Surface | EN short | EN full | ZH short | ZH full |
|---|---|---|---|---|
| Brand | Prophet | Prophet Stock Signals | 先知 | 先知选股信号 |
| Board headers | Prophet | — | 先知选股 | — |

#### Per-market display labels (engine_label / engine_label_zh)

| Internal key | EN display | ZH display |
|---|---|---|
| us | Prophet US | 先知美股 |
| cn | Prophet China | 先知A股 |
| hk | Prophet HK | 先知港股 |
| ca | Prophet CA | 先知加股 |
| intl | Prophet Intl | 先知国际 |

### Internal identifiers — UNCHANGED

All of the following are NOT renamed and must never be renamed:
- File paths: us_standouts.json, china_standouts.json, canada_standouts.json,
  hk_standouts.json, intl_setups.json, us_standouts_v2.json
- Synapse ids: site-us-standouts, site-china-standouts, prophet-*
- Engine/module/role names: standout_audit, standout_auditor, standout_review
- CSS ids/classes: #standouts, #us-standouts, sb-*, .fac-standout
- Jinja/JS variable names, payload field keys: standouts.buy, standout_label,
  r.standout, schema strings, ledger paths, config keys
- Research doc titles: STANDOUT_ACCOUNTABILITY masterplan name stays

### Generic-adjective exemption

"standout" used as a plain English adjective is NOT the brand and stays:
- engine/stock_score.py:1012,1025 ("Relative-strength standout — screen, not a
  validated pick")
- dashboard.html.j2 SUE chip tooltip (~:13130, :13227 "Standout on the shallow
  recent window...")

### Landing-hub card labels (found post-census)

The landing-hub card label fields written to `data/us_stocks/latest.json`
(`scripts/build_site.py`) and `data/canada_stocks/latest.json`
(`scripts/build_canada.py`) were not caught in the initial census. Both are
user-facing EN `label` strings consumed by the landing hub and fall within
the rebrand scope of Amendment 1. Updated in the same PR:
`build_site.py` → `"{n} Prophet stock signals" / "Prophet · sectors · flows"`;
`build_canada.py` → `"{n} Prophet TSX signals" / "Prophet TSX · alpha · setups"`.
The baked latest.json files heal on the next nightly render.

### Site copies

Site copies of edited templates (site/*.html) are RENDER-OWNED and heal on the
next nightly/asia render. Only source templates were edited; no site/*.html were
hand-edited (per source-only law, check_template_site_sync).
