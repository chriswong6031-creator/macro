# Standout Accountability — rolling track-record audits + self-improvement for the standout boards (US + CN)

Status: MASTERPLAN v2 (W0). Author: Fable, 2026-07-12. Operator directive 2026-07-12:
the standout top-stocks systems (US + China dashboards) must be assessed on a rolling
basis once their forward ledgers mature; the responsible lobe must audit its own track
record — why picks succeeded, why picks failed, whether the failure was macro, sector
rotation, gating/timing (signaled too late), an upstream lobe feeding wrong signals,
or a bug in the systems that feed it — and, with adversarial Opus review, autonomously
propose and land improvements, including forward-test experiment portfolios in the
stocks labs. Speed matters: improvement must not be hostage to slow forward accrual
where honest faster evidence exists.

v2 incorporates a three-lens Opus red-team (incentive/statistics, house-law/
integration, operational robustness; 2026-07-12). Verdicts absorbed: 5 blockers
(effective-N overlap, in-sample-circular do-no-harm gate, CN charter NW-scope,
grade_us_board render-job placement, uncommitted US pick-lab stores) and 15 majors.
Rulings: SA-R1 … SA-R16. Waves: SA-W1 … SA-W6 (§8).

---

## 0. Executive ruling — the ledgers exist, the mind that reads them does not

The census (9-lane, 2026-07-12) found every raw ingredient already built and accruing:

| Ingredient | Where it lives | State |
|---|---|---|
| US board forward ledger | `scripts/grade_us_board.py` → `data/us_board_ledger/retro_grades.parquet` (80 cols, PIT regime stamps, 5/10/21/63d vs SPY + sector) + `snapshots.jsonl` | accruing nightly since 2026-06-15 (committed) |
| CN board forward ledger | `engine/china_standout_track.py` → `data/china_standout_track/board.parquet` (T+1 HL2 fill, CSI300 excess) + `ripening.parquet` | accruing in asia lane since 2026-06-30 (committed) |
| Experiment harness | Pick Lab (`engine/pick_lab/`, 27 US + 20 CN + HK books, fires/grades JSONL, PL-R1..R12) + lab pages | accruing; first CN grades ~2026-07-29; **US stores runner-local, NOT in git (§SA-R15)** |
| Production replay harness | `scripts/replay_standout_pipeline.py` (P0.1): replays the full production signal stack over the yahoo store 2012→present, species-law grading, resumable | built; the Tier-0 substrate for SA-R5 |
| Self-learning loop | metabolism SENSE→AGENDA→PROPOSE→ADJUDICATE (orchestrator + adversary two-key, Opus)→BUILD (sonnet, draft PR)→MERGE (fenced)→VERIFY→DREAM; multi-lobe propose landed in #2341 | armed-gated, shadow-first, TIL sole loop-manageable lobe |
| A6 lane-(ii) precedent | `engine/risk_radar_review.py`: Opus proposes bounded deltas → code clamp → do-no-harm backtest → apply/reject → `a6_llm_proposed`/`a6_auto_apply` governance events | live; the legal template for §6 |
| Attribution raw material | PIT regime stamps on every ledger row; near-miss rows (blocked-by-one-gate) in `engine/track_record.py`; `stock_dossier` no_buy_reasons; `market_state_audit.py` per-corroborator pattern; Winner Autopsy episode census | present, unread |

What does **not** exist — anywhere — is the reading layer: no failure-mode taxonomy,
no per-pick attribution, no upstream-lobe concordance measurement, no fitness sensors
on the standout lobes (they are SENSE-only), no maturity-gated audit trigger, no path
from an audit finding to an experiment book or a bounded parameter change, and no
guard against the loop learning to stop surfacing risky picks.
`engine/metabolism/propose.py` cannot see pick outcomes at all.

**The ruling:** build the reading layer on the existing rails; duplicate none of them.
The standout lobes become the second and third loop-manageable lobes (R-V4-10 charter
mechanism, multi-lobe propose from #2341). Attribution is deterministic; the LLM
reads evidence packs and writes post-mortems and proposals; the existing adversary/
two-key stage is the operator-requested "Opus reviews Opus" gate; parameter changes
land only through A6 lane (ii) (machine-registered, clamp-checked, forward-confirmed),
with code-level coverage floors so the loop cannot buy hit-rate by going quiet.

## 1. Rulings

**SA-R1 — Accountability is charter-based; no new NW program-lobe.** The accountable
entities are the existing artifact lobes: `site-us-standouts` (owner
`us-stocks-prebreakout`) and a new sibling charter **`site-china-standouts`** (exact
synapse id; owner `china-alpha`). Both gain dict-form `fitness_sensors` (each sensor
a dict with `id` + `store`, stores = COMMITTED paths) so
`_discover_loop_managed_lobes()` admits them (verified: propose is lobe-parameterized
since #2341; TIL is only the fallback default). NW-scope prerequisite: the tier-mirror
check requires the synapse entry to be NW-scope; `site-china-standouts` today carries
only `mastermind:vendored`. SA-W3 therefore wires `china_standouts.json` into the
Mastermind candidate intake (`engine/neuralweb/mastermind_context.py` — true parity
with the `us_standouts` read at its candidate-universe block) and tags
`mastermind:context` truthfully in the same PR. The binding roster cap is
`max_active_nonscored_lobes: 66` (current active non-scored count: 64; this program
takes it to 65, leaving ONE slot — stated so the next charter knows). The NW two-lobe
program-lobe cap (RUL-P1) is untouched but is not the binding constraint here.

**SA-R2 — Attribution is deterministic; the LLM only reads and writes prose.** Every
number in an evidence pack, scoreboard, or fitness card is computed by engine code
from PIT-stamped ledger columns. The attribution taxonomy (§3) is a CLOSED two-axis
set; extending it requires a §11 status row. The LLM auditor reads packs and writes
post-mortem narratives, hypotheses, and proposals — artifacts only; it never emits a
number any surface renders as a score, never re-labels a row, never escalates
(NW-ART1/CONST-ART1 unamended). **Disjointness invariant:** no parameter tunable by
any improvement lane (§6 whitelist) may be an input to any attribution threshold or
fitness-sensor definition; the §3 taxonomy constants and §4 sensor definitions are
loop-IMMUTABLE (registered in the self-mod fence; operator PR to change) — the loop
may never move its own ruler.

**SA-R3 — Balanced-fitness law (the anti-reward-hacking core).** The standout fitness
card carries NO single fused score. Every precision-rewarding sensor is paired with a
coverage/recall-rewarding sensor, and the card prints both loss ledgers in the same
units (excess pp lost on surfaced losers vs excess pp forgone on unsurfaced winners).
The pairings are enforced in CODE, not prose: the SA-R4 clamp set floors
`coverage_health`, `upside_capture`, AND `missed_mover_rate` — not just buy-lane
count — so a composition shift toward safe-only names (count constant, boldness
gutted) trips a clamp, not a debate. A proposal that improves a precision sensor
while degrading a paired coverage sensor is rejected by the clamp unless the operator
taps an explicit override.

**SA-R4 — Coverage clamps are code, anchored to a frozen baseline.** The clamp set
(values in `config/standout_review.yml`, loop-IMMUTABLE):
(a) buy-lane surfaced count: trailing 4-week median may not fall >15% below the
FROZEN baseline (median of the 8 weeks ending at each market's first sensor-maturity
date — not a trailing window a slow ratchet can walk down), nor below an absolute
floor of 5 buy-lane names/day median; (b) cumulative-drift trip: total decline vs the
frozen baseline >25% at any horizon = hard trip regardless of rate; (c)
`upside_capture` and `missed_mover_rate` trailing reads may not regress beyond their
frozen-baseline bands. Any lane-(ii) delta whose replay projects, or whose post-apply
forward window shows, a clamp breach is auto-REJECTED/auto-reverted. The metabolism
`adversary` role prompt (config/metabolism_roles.yml) gains a standing anti-narrowing
instruction; a matching global warn rule is added to `config/adjudication_rubrics.yml`
as a numbered warn_rule (it is a GLOBAL class-keyed rule set — there is no per-lobe
slot; the packet checker is updated in the same PR).

**SA-R5 — Three-speed evidence ladder; replay authorizes experiments and shadow
applies, never promotions and never live flips.** Tier-0 (same-day): deterministic
replay — US: extend `scripts/replay_standout_pipeline.py` (production-stack replay,
2012→present); board/book-config counterfactuals over accrued PIT snapshots — selects
hypotheses and sizes deltas. Tier-1 (weeks): Pick Lab experiment books (new engine_id
per PL-R2; PL-R4 floors; registered in the experiments registry for come-back
alerts) and SHADOW config variants (§6). Tier-2: gauntlet at the pre-registered ruler
+ operator tap for any scored-path/board change. Replay evidence may spawn an
experiment or a shadow apply; it may never justify promotion OR a live config flip
(HOUSE-U4 stands; the lane-(ii) forward-confirmation gate in §6 closes the "config
auto-apply isn't a promotion" loophole).

**SA-R6 — All parameter changes are A6 lane (ii).** `risk_radar_review.py` — the
template — is itself the case law's canonical lane-(ii) mechanism (its governance
events are `a6_llm_proposed`; NW-U5 reserves lane (i) for deterministic pre-registered
tuners like `market_state_tune`). An Opus-proposed delta is lane (ii) by definition:
machine-registered experiment entry, pre-committed gates, clamps, governance events,
quarterly re-audit. `engine/standout_review.py` implements this for the standout
boards (§6). A genuinely deterministic lane-(i) tuner (calibration-from-ledger, no
LLM in the loop) is chartered as follow-up docket, not built here. standout_review
inherits risk_radar_review's arming precondition: it arms only with its writes routed
through lane-(ii) registration and logging. Weight changes by fiat are forbidden.

**SA-R7 — CN PIT regime store is a prerequisite, stamped forward-only.** A
daily-append PIT CN regime store (`data/china_regime/regime_daily.parquet`, asia lane,
keep-first) is built first; `own_market_regime` on CN board rows is stamped from it
from store birth forward. No retroactive backfill from the overwrite-style
`regime_history.parquet`. Pre-store CN rows form a distinct **"US-proxy" regime
stratum that is never pooled with own-market cells** in any significance claim; the
seam date is printed on the surface.

**SA-R8 — Upstream blame is measured concordance, not accusation.** For each matured
pick, the audit emits `upstream_concordance` rows: {organ, state_at_entry,
realized_outcome, concordant}. Aggregated per-organ discordance rates (raw n,
effective cluster n, Wilson CI on the cluster unit) are printed on the audit
scoreboard. A discordance trip (insight_bus emission) requires: cell effective-n ≥
floor AND the discordance surviving a DT-R14 within-month permutation null AND
BH-FDR across all scoreboard cells tested that run. Trips route investigation via the
agenda; they never change any organ's state or score.

**SA-R9 — Cadence: rolling, maturity-gated, off the render path.** US attribution
runs in a NEW off-render job (`needs: engine, if: always()`, ~40m timeout, own
narrow-commit — the `oracle_offrender` pattern) reading the COMMITTED
`retro_grades.parquet`; it does NOT ride inside the engine render job
(`grade_us_board` lives in the engine job at daily.yml — adding compute there is
render-budget-relevant and forbidden here; the render path gets zero new work). CN
attribution rides `china_standout_track.grade()` in the asia lane WITH `[timing]`
ticks, a stated runtime bound (target lane steady-state ~110m preserved), and a
fail-closed `CN_LANE=asia` write-gate test. The audit reasoning lane fires on a
deterministic trigger computed at SENSE: `newly_matured_graded_rows_since_last_audit
≥ 15` OR (≥5 AND ≥14 days elapsed). Trigger state (`data/standout_audit/
audit_state.json`) is stateless-cattle: derived from the ledger's max graded `as_of`
+ the last written post-mortem's cycle_id (keep-first), advanced ONLY when a
post-mortem artifact is committed — a mid-audit crash re-derives and re-fires the
same cohort idempotently; nothing is lost or double-counted. The LLM stage runs
inside the existing metabolism workflows (armed-gated, shadow-exercisable), never in
nightly render jobs.

**SA-R10 — Statistical honesty at board-shaped effective N.** A rolling board's rows
are overlapping and correlated — effective N is far below row count
(ticker-cluster time-confound law). Therefore: every scoreboard/fitness cell prints
BOTH raw row n AND effective cluster n, where the inference unit is the entry-date
collapse (one observation per entry date, equal-weight across that date's picks)
blocked into non-overlapping 21d windows; Wilson CIs are computed on the cluster
unit, never raw rows. Stratified significance claims and discordance trips use
within-month episode-label permutation (DT-R14) + BH-FDR across cells; cells below
the effective-n floor print ACCRUING and may not trip anything. ACCRUING states are
printed, never hidden; "validated" never appears (CI-enforced). Fitness verdicts read
at the pre-declared ruler only: 21d benchmark-excess primary (tactical_entry
horizon_role); 5/10/63d descriptive. Attributions carry their OWN maturity stamps
(§3): a row matured for the 21d ruler may be immature for `premature_stop_noise`
(needs +21 post-stop sessions) or for the missed-mover census (needs the episode
window) — immature-for-that-attribution rows are excluded from that sensor, never
counted as negatives. Sensors are `accruing: true` until floors (§4); proposals
against accruing sensors carry `check_by ≥` maturity (R-V4-10).

**SA-R11 — Process faults are first-class audit output.** `data_fault` process
attributions (stale store at entry, junk facts, dead wire, missing feed) route to
normal metabolism fix proposals — finding bugs in the systems that feed the board is
as much the audit's job as grading picks. Every audit run re-checks its own inputs'
freshness and prints a process-integrity line.

**SA-R12 — Scope is US + CN.** HK/CA extend trivially (`board_ledger.py` already
accrues both) but are deferred: each needs its own PIT regime store and charter, and
the HK lane is mid-flight under other programs. Follow-up docket row, not a wave.

**SA-R13 — Outcome-vs-process separation (the operator's tightening worry, restated
as law).** The two-axis taxonomy (§3) assigns an outcome-cause AND a process-fault
independently, so "chased late into a macro drop" records both truths — the process
fault is never masked by the outcome cause. Post-mortems must respond to each axis
with its own remedy class: outcome-cause failures with clean process demand
conditioning evidence (e.g. regime-cell analysis), NEVER gate tightening; process
faults demand the specific fix (timing, gate margin, data repair). A winner entered
late is a process fail despite the P&L. The LLM auditor prompt carries this law
verbatim; the adversary checks proposals against it.

**SA-R14 — Store hygiene.** New stores are small committed parquet/JSONL
(size-audited) with keep-first dedup keys; US writes gated on the nightly lane
sentinel, CN writes on `CN_LANE=asia` (fail-closed, tested); forward-ledger
advancement stays nightly-only; one-grader law (all forward returns via
`engine.grading.forward_metrics` or the ledger's established fill convention).

**SA-R15 — No reads from uncommitted stores; commit the US pick-lab ledgers.** The
US pick-lab stores (`data/pick_lab/fires.jsonl`, `grades.jsonl`, `snapshots/`) are
runner-local and NOT in git (CN's already are). Any job other than the producing
nightly job — metabolism propose (fetch-depth-1 checkout), build worktrees, CI —
sees an absent store. Therefore: (a) SA-W1 adds a narrow-commit of the US pick-lab
stores in the producing nightly job (they are small, monthly-partitioned parquets —
CN precedent); (b) fitness cards and evidence packs are COMPUTED in the jobs where
their inputs live and COMMITTED (like `data/metabolism/fitness/til.json`), so the
metabolism loop reads committed cards, never raw runner-local stores; (c) every
reader implements the CNPL-R9 degraded mode — absent store ⇒ explicit `data_gap`
flag + null sensor with reason, never a fabricated zero (a missing store must never
read as "0 missed movers").

**SA-R16 — Silent-death immunity.** Every new hook is never-raise with its own
try/except so it can never suppress the artifact it rides beside; every producing
step writes a freshness stamp consumed by the heartbeat/organism-state freshness
sensors, so a persistently-failing audit shows up as a stale-store breach instead of
riding green under `|| true` forever. Corrupt-artifact tests ship with every new
module (ci.yml whitelist updated). New parquet-reading one-shots end with
`lib.procutil.hard_exit()` (Arrow shutdown-hang law).

## 2. Architecture (one picture)

```
 nightly render path (UNTOUCHED)          asia lane (additive, [timing]-ticked)
 grade_us_board ─► retro_grades.parquet   china_standout_track.grade() ─► board.parquet
        │ (committed)                            │ + CN attribution cols (committed)
        ▼                                        ▼
 NEW off-render job: standout_audit_us    (same lane) standout_audit_cn
 engine/standout_audit.py (deterministic, SA-R2; never-raise, SA-R16)
 ├─ two-axis attribution sidecar   data/standout_audit/{us,cn}_attribution.parquet
 ├─ evidence packs                 data/standout_audit/{us,cn}_evidence.jsonl
 ├─ stratified scoreboard          site/factordata/{us,cn}_audit_scoreboard.json
 ├─ coverage monitor + missed-mover census (buy-lane credit only)
 ├─ upstream concordance           (per-organ discordance; SA-R8 trips)
 └─ fitness cards                  data/metabolism/fitness/standouts_{us,cn}.json
        ▼                                   (all committed by the producing job)
 metabolism loop (existing rails): SENSE (audit_due trigger) → AGENDA → PROPOSE
 (charter-driven, #2341 multi-lobe) → standout_auditor reading lane (Opus, own
 context assembler — NOT a build_prompt_context edit) → ADJUDICATE (adversary Opus
 + two-key; anti-narrowing warn rule) → BUILD (sonnet draft PR) → VERIFY → DREAM
        ▼
 improvement lanes (§6, all A6 lane (ii)):
 • standout_review.py — clamped deltas, leave-newest-out replay gate, SHADOW-first
   apply, forward-confirm before live flip, governance events, auto-revert
 • Pick Lab experiment books (new engine_id, PL-R2/R4) + replay-harness selection;
   experiments-registry come-back alerts
 • plain code-fix PRs for data_fault / dead-wire / discordance findings
```

## 3. The attribution taxonomy (CLOSED, two orthogonal axes, v2)

Per matured pick, `engine/standout_audit.py` assigns **one outcome-cause AND one
process-fault**, independently, from deterministic thresholds on already-stamped
columns. This two-axis structure is what makes SA-R13 mechanical: "late chase into a
macro drop" = (`macro_headwind`, `signaled_too_late`) — neither truth masks the other.

**Axis 1 — outcome cause** (precedence order resolves overlap; most-specific first):

| Code | Meaning | Deterministic basis (v1 constants; loop-IMMUTABLE per SA-R2) |
|---|---|---|
| `idio_break` | stock-specific failure (selection miss) | excess vs own sector ≤ −4pp |
| `sector_rotated_out` | sector turned against the pick | sector-ETF excess vs benchmark ≤ −2.5pp AND pick idio within ±2pp of sector |
| `macro_headwind` | market fell; pick fell with it | benchmark ≤ −3% over horizon AND pick idio within ±2pp of sector |
| `idio_alpha` | success driven by selection | excess vs own sector ≥ +4pp |
| `beta_tailwind` | success was tape/sector beta | pick positive, idio within ±2pp, sector/market strongly positive |
| `mixed` | none of the above tiles | residual — printed honestly on the scoreboard, never hidden |

Precedence: `idio_break` > `sector_rotated_out` > `macro_headwind` (and
`idio_alpha` > `beta_tailwind`); rows satisfying multiple take the highest-precedence
code with the others recorded as secondary context flags. The bands deliberately
over-tile rather than gap: anything unclassifiable is `mixed`.

**Axis 2 — process fault** (independent of outcome):

| Code | Meaning | Deterministic basis |
|---|---|---|
| `signaled_too_late` | chased an extended setup | entry extension percentile ≥ 85 OR ticks-since-cross > fresh window OR board_tenure_days > 7 at first buy-lane appearance |
| `gate_suppressed` | a gate blocked a winner | near-miss row (blocked by exactly one gate) with realized 21d excess ≥ +4pp — the false-negative gating error, per-row from the near-miss store |
| `premature_stop_noise` | stopped, then recovered | terminal_state stopped/cut AND post-window MFE ≥ +4pp above stop within 21 sessions (own maturity stamp; SA-R10) |
| `data_fault` | inputs broken at entry | staleness flag at as_of, junk-fact repair on the name, missing upstream artifact, or store-freshness breach logged that night |
| `clean` | no process fault detected | default |

Secondary context flags (either axis): `regime_discordant`, `rotation_discordant`,
`gate_margin_thin` (passed its binding gate in the bottom margin decile),
plus the outcome-cause codes not selected as primary. Each attribution carries its
own maturity stamp; rows immature for a given attribution are excluded from sensors
that read it (SA-R10). Attribution rows are keep-first per (ledger key,
taxonomy_version). CN mirrors both axes with CSI300/sector-proxy benchmarks, T+1 HL2
fill respected, locked-limit exclusions inherited, and `species_id` disambiguation
stamped at append time going forward (SA-W2).

## 4. Fitness sensors (both lobes; all `accruing: true` until floors)

| Sensor | Definition (21d ruler; cluster-unit CIs per SA-R10) | Direction | Guarded by |
|---|---|---|---|
| `hit_quality` | Wilson-LB of P(excess>0), buy lane, entry-date-collapsed clusters | ↑ precision | paired coverage clamps |
| `upside_capture` | mean surfaced buy-lane excess ÷ winsorized mean universe-top-decile realized excess; denominator floored (no read printed when top-decile excess ≤ +2pp — flat-tape guard); always printed WITH surfaced count so concentration cannot masquerade as boldness | ↑ boldness | SA-R4 clamp (c) |
| `coverage_health` | trailing 4-week buy-lane surfaced count vs FROZEN baseline + n_buy/n_eligible pass-through slope + cumulative-drift check | ↑ recall | SA-R4 clamps (a)+(b) |
| `missed_mover_rate` | fraction of universe clean-big-winner episodes never reaching the BUY lane within 10 sessions of episode start (buy-lane credit ONLY — watch/ripening listing does not count; a separate capped `pipeline_recall` diagnostic tracks watch/ripening so the lists can't be flooded for credit) | ↓ | SA-R4 clamp (c) |
| `timing_quality` | median entry-extension percentile + share of matured rows with process fault `signaled_too_late`; orthogonality to count is CONDITIONAL on the SA-R4 count clamps (dropping late entries to game the median hits the coverage floor) | ↓ lateness | count clamps |
| `process_integrity` | share of matured rows with `data_fault` + audit-input freshness breaches | ↓ | — |

Maturity floor (per market): ≥25 matured rows AND ≥10 distinct entry dates AND ≥3
non-overlapping 21d entry windows spanning ≥3 calendar months. This is when sensors
flip from `accruing` and the audit lane may cite them — NOT a verdict grade; at these
floors the cluster-unit CIs remain wide, the card says so, and any promotion-grade
claim still requires the DT-R14 permutation machinery and the gauntlet. Realistic
first reads: US ~2026-09-15; CN ~2026-10-15 (thinner, later ledger birth). The
fitness card prints per-sensor raw n, effective cluster n, and state. Budget:
`lobe_caps` rows for both lobes in `config/metabolism_budget.yml` (operator-ratified
in this program's PR — a human PR is legal there; the self-mod fence blocks only
loop-authored edits; no grader-manifest regen needed). Roster: 64 → 65 of 66.

## 5. The audit reasoning lane (what the LLM actually does)

New role `standout_auditor` in `config/metabolism_roles.yml` (inert-writer contract
preserved: writes artifacts only, dispatches nothing, grants nothing, inert under
AUTONOMY_PAUSED). It gets its OWN context assembler (`engine/metabolism/
standout_auditor.py`, mirroring `risk_radar_review`'s evidence-pack pattern) — the
shared `build_prompt_context` in propose.py is NOT modified (it is TIL-shaped and
hot; #2341 seam verified at build time). Context: the stratified scoreboard, newest
evidence packs (matured since last audit), coverage monitor, upstream concordance
table, current fitness card, prior post-mortems (anti-repetition), the mission block,
and SA-R13 verbatim. It writes ONE artifact:
`data/standout_audit/postmortems/<market>-<cycle_id>.json` containing (a) per-cohort
post-mortem prose — why failures failed on BOTH axes, why winners won, what would
have mitigated which, process separated from outcome; (b) ranked improvement
hypotheses, each tagged with its intended lane (§6) and a falsifiable fitness
contract (which sensor should move, by when — respecting accrual honesty); (c) an
honesty section: what cannot be concluded at current effective n. Docket-eligible
hypotheses flow into the normal PROPOSE output for the lobe (max_docket_size
respected). ADJUDICATE runs unchanged — the orchestrator + adversary two-key IS the
operator-requested opus-to-opus adversarial approval; the adversary role text and a
global warn rule carry the anti-narrowing check (SA-R4). BUILD (sonnet) drafts the
actual PRs. VERIFY grades realized sensor deltas when contracts mature. Everything is
exercisable under `AUTONOMY_PAUSED` via the shadow harness (R-V4-1); shadow runs are
this program's arming evidence.

While the loop stays paused, the deterministic layer (attribution, scoreboards,
fitness cards, coverage monitor, concordance) ships and accrues regardless —
display-tier, build-free (HOUSE-U4). Operator sessions read the same evidence packs
and can act manually; the program does not wait for arming to be useful.

## 6. Improvement lanes (all A6 lane (ii); SA-R6)

**Clamped config deltas** (`engine/standout_review.py` + `config/standout_review.yml`):
whitelisted parameters only (v1: extension-penalty scale, tier-fraction,
washout/coiled bonus magnitudes, board-width guard, per-sector cap — each with
min/max/step; the whitelist is DISJOINT from every attribution threshold and sensor
definition per SA-R2's invariant); per-cycle max delta; SA-R4 clamp set. The
do-no-harm gate is built for honesty at tiny n:
1. **Temporal split:** hypothesis selection and delta sizing use accrued history
   EXCLUDING the most recent non-overlapping month; the gate must hold on that
   held-out newest month (leave-newest-out).
2. **Trial accounting:** the replay grid searched (whitelist × steps) is a known
   trial count; the non-regression threshold takes a trial-count haircut and the
   count is logged to `governance.jsonl` with the proposal.
3. **Noise band = permutation null:** "no regression beyond noise" is defined against
   the DT-R14 within-month permutation null of the metric delta — not a fixed pp. At
   current effective n this will authorize almost nothing; that is the honest answer,
   stated on the card. The lane is expected to be largely DORMANT until the SA-R10
   floors mature.
4. **Shadow-first, forward-confirm:** a passing delta applies to a SHADOW config
   variant (parallel scored artifact, display-dark), never live. The live flip
   requires the shadow variant's forward window to confirm the fitness contract at
   contract maturity (VERIFY), or an explicit operator tap to flip early. Quarterly
   re-audit evaluates each still-applied delta on data accrued STRICTLY AFTER its
   apply date (true forward evidence) and auto-reverts regressions via the fenced
   revert path.
Every proposal + verdict appended to `data/neuralweb/governance.jsonl`
(`a6_llm_proposed` / `a6_auto_apply` / `a6_rejected` events, risk_radar_review
schema). Applies config, never code. Arms only after its writes are routed through
lane-(ii) registration and logging (NW-U5 precondition, inherited).

**Experiment books:** the replay harness (US: extend
`scripts/replay_standout_pipeline.py`; snapshot-level counterfactual re-ranking via a
new `scripts/replay_standout_books.py` for board/book configs, `hard_exit()` at end)
selects hypotheses worth forward-testing; BUILD drafts the registry PR (new
`engine_id`, frozen config_hash, pre-declared ruler, PL-R9 kill-adjacency citation).
All pick-lab books (existing + new) get registered in
`data/experiments/registry_seed.json` so SCOREABLE transitions raise come-back alerts
on the admin Experiments tab — closing today's gap where books mature silently.

**Plain fixes:** `data_fault`/dead-wire/discordance findings become ordinary
metabolism proposals (or operator-session PRs) with no special machinery.

## 7. Surfaces (Tier-3, bilingual, doctrine-compliant)

An **Accountability** section on `us_stocks_lab.html` and `china_stocks_lab.html`
(the labs are the sanctioned Tier-3 depth surfaces): stratified scoreboard (each cell
raw n + effective cluster n + Wilson CI + ACCRUING badges), two-axis failure-mode mix
over time, the two loss ledgers side by side (SA-R3), coverage monitor sparkline
with the frozen baseline drawn in, upstream concordance table, and the latest
post-mortem digest (plain-word summary up top per DESIGN_DOCTRINE; technicals below).
Committee page gets a one-card operator read. No new public top-nav page; no
"validated"; EN/ZH pairs; no translated `title=` attributes.

## 8. Wave docket

Each wave: fresh worktree off `origin/main` → sonnet build → opus adversarial review
→ fix → PR → same-day squash-merge. Hygiene laws binding on every wave: new tests
into the ci.yml pytest whitelist; dag.yml + synapse.yml regenerated in the same PR as
any new wiring (every new artifact has a named caller — dead-wire law); never-raise
modules with corrupt-artifact tests (SA-R16); freshness stamps on every producer;
`$RUNNER_TEMP` not `/tmp`; lane sentinels fail-closed and tested; `engine/metabolism/*`
is hot (v6 #2339/#2341 merged 07-12) — re-verify seams against fresh main at build
time, not against this document.

| Wave | Lane | Contents | Primary files |
|---|---|---|---|
| SA-W1 | US attribution organ (off-render) | `engine/standout_audit.py` (two-axis taxonomy §3, evidence packs, stratified scoreboard, coverage monitor, missed-mover census with buy-lane-only credit, upstream concordance, US fitness card); NEW off-render job `standout_audit_us` (needs: engine, if: always(), own narrow-commit) reading committed `retro_grades.parquet`; narrow-commit of US pick-lab stores in the producing nightly job (SA-R15); synapse + dag regen; tests | `engine/standout_audit.py`, `.github/workflows/daily.yml` (new job + pick-lab commit), `config/synapse.yml`, `config/dag.yml` |
| SA-W2 | CN foundations + attribution (asia lane) | PIT CN regime daily store (SA-R7); `species_id` stamping at append; CN two-axis attribution enrichment in `china_standout_track.grade()` with `[timing]` ticks + stated runtime bound; CN evidence packs + scoreboard + fitness card; fail-closed lane-gate test | `engine/china_regime_store.py` (new), `engine/china_standout_track.py`, `scripts/build_china_library.py` (hook) |
| SA-W3 | metabolism wiring | charter upgrades: dict-form sensors (id+store, committed paths) for `site-us-standouts` + NEW `site-china-standouts` charter; NW-scope fix: wire `china_standouts.json` into mastermind candidate intake + truthful `mastermind:context` tag (SA-R1); `metabolism_budget.yml` lobe_caps; `standout_auditor` role + own context assembler (`engine/metabolism/standout_auditor.py`); SENSE audit_due trigger (stateless-cattle state per SA-R9); adversary-role anti-narrowing text + global warn rule in `adjudication_rubrics.yml` + packet-checker update; test asserting `_discover_loop_managed_lobes()` returns both lobes; shadow-cycle coverage | `config/lobe_charters.yml`, `config/synapse.yml`, `engine/neuralweb/mastermind_context.py`, `config/metabolism_roles.yml`, `config/metabolism_budget.yml`, `config/adjudication_rubrics.yml`, `engine/metabolism/standout_auditor.py` |
| SA-W4 | improvement lanes | `engine/standout_review.py` + `config/standout_review.yml` (whitelist disjointness invariant, SA-R4 clamp set, leave-newest-out + trial-haircut + permutation-null do-no-harm, shadow-first apply + forward-confirm + auto-revert, governance events); `scripts/replay_standout_books.py` (snapshot counterfactuals, `hard_exit()`); experiments-registry registration of all pick-lab books (come-back alerts) | `engine/standout_review.py`, `config/standout_review.yml`, `scripts/replay_standout_books.py`, `data/experiments/registry_seed.json` |
| SA-W5 | surfaces + v2 hook | lab-page Accountability sections (US + CN, bilingual); committee card; `us_standouts_v2` grader hook (register `us_standouts_v2.json` per the ledger-hook note at `scripts/build_stock_board_v2.py:577-583` so the v2 flip gate can ever be satisfied); calibration-hub ingestion of board tracks | `templates/us_stocks_lab.html.j2`, `templates/china_stocks_lab.html.j2`, `scripts/grade_us_board.py`, `engine/calibration_hub.py` |
| SA-W6 | verification + evidence | end-to-end wiring check (grep callers for every new artifact); shadow-cycle run showing the standout lobes discovered + audit trigger exercised; follow-up docket; memory write | `scripts/metabolism_shadow_cycle.py` evidence, docs |

Dependencies: SA-W1 ∥ SA-W2 (disjoint files/lanes); SA-W3 needs W1+W2 artifacts to
exist (sensor stores must resolve); SA-W4 after W1 (∥ W3); SA-W5 after W1/W2; SA-W6
closes.

## 9. What this program refuses (refusals of record)

- **No LLM-originated signals, scores, or escalations** anywhere (NW-ART1). The
  auditor writes prose and proposals; every rendered number is deterministic.
- **No board re-weighting by fiat** — A6 lane (ii) only; clamps, whitelist, and
  taxonomy/sensor constants are loop-IMMUTABLE; the loop may never move its own ruler
  (SA-R2 disjointness invariant).
- **No live config flip on replay evidence** — shadow-first, forward-confirm (§6);
  no promotion on replay evidence (SA-R5).
- **No single fused fitness score** (SA-R3) and no direction-probability constructs
  (NW-U29: threshold-cascade adjustments and AND-gates only).
- **No new NW program-lobe** (RUL-P1 stands); binding roster constraint is
  `max_active_nonscored_lobes` (65/66 after this program). No held-position/live-book
  monitoring (Mastermind repo, PRD-R1/R2).
- **No new render-path compute** (the engine job gets zero new work; RUL-C8
  respected off-render); LLM stages never run in nightly render jobs.
- **No reads from uncommitted stores; no fabricated zeros on absent stores** (SA-R15).
- **No arming changes** — `AUTONOMY_PAUSED` and the six Acts remain the operator's;
  this program ships shadow-exercisable machinery and arming evidence only.
- **No HK/CA scope** this program (SA-R12). **No retro-fabricated CN regime stamps**
  (SA-R7).

## 10. Clocks

- **First CN pick-lab grades:** ~2026-07-29 (21d from first fires).
- **First US sensor maturity read:** ~2026-09-15 (SA-R10 floors on cluster units).
- **First CN sensor maturity read:** ~2026-10-15.
- **First scheduled audit-lane fire:** first SENSE after either market crosses the
  SA-R9 trigger (expected ~2026-08 for US at current board width — the audit lane can
  fire on the trigger before sensor maturity; it just cannot cite immature sensors).
- **Lane-(ii) quarterly re-audit:** first due 2026-10-15 (post-apply forward data
  only; aligns with metabolism dream/kernel clocks).
- **HK/CA extension decision:** revisit after first US+CN audit cycle completes.

## §11. Taxonomy status rows (append-only)

| Date | Change | Ruling |
|---|---|---|
| 2026-07-12 | v1 taxonomy established (single-primary) | SA-R2 |
| 2026-07-12 | v2: restructured to two orthogonal axes (outcome-cause × process-fault) per red-team F11–F15; `gate_suppressed` + `mixed` added; precedence order published; per-attribution maturity stamps | SA-R2/SA-R13 |
