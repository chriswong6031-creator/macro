# China System Masterplan — by Fable (2026-07-08)

*Adjudicates `research/A_SHARE_MARKET_MECHANICS_AND_CHINA_SYSTEM_UPGRADE_FOR_CLAUDE.md`
(Codex, 2026-07-08) and merges it with Fable's first-principles design, grounded in a 7-lane
census of the China stack (engines / data / UI / NW / verdicts / collisions / pipeline,
2026-07-08). Program: the sovereign China market brain — spine, lobes, historical PIT tapes,
NW integration, cockpit UI.*

---

## 0. Mission and the operator's standing directive

**Mission:** make the China section intelligent — a system that can say, with evidence and
humility: what phase mainland A-shares are in, whose money is moving, what policy/liquidity
impulse is priced, which sectors/themes are early vs late, which names are fillable at good
entries, and when cash beats cleverness.

**Operator's standing directive (context-accrual doctrine, per the 2026-07-08 operator ruling
— memory `context-accrual-fundamental-goal`):** data and infrastructure FIRST.
Context/tagging/accrual/detection infrastructure ships display-tier WITHOUT edge gauntlets;
gauntlets only at promotion. This program ships **zero new backtest studies**. It ships
deterministic engines, historical PIT tapes, forward accrual ledgers, and NW context plumbing.
The brain learns later, from the data this program starts collecting today.

Three binding corollaries:
1. **Confluence retention.** A factor that printed null as a STANDALONE signal (margin impulse
   SLF-051, northbound flow, policy-event CARs, export nowcast, abnormal turnover W3-A…) is NOT
   discarded — it is retained as a context/confluence layer that can help CONFIRM other signals
   when aligned. The participation, policy, and external lobes are built exactly from such
   factors, legally, at context tier.
2. **Kills are construction-specific.** Standing kills close the tested construction — limit-up
   chase as a BUY trigger, LHB copying as alpha — never the data layer. Limit-up data as
   market-structure/theme-breadth context is sanctioned by the same rulings that killed the
   chase trade.
3. **Detection is never blocked, only promotion is.** Lobes emit candidates/contradictions/
   falsifiers freely; nothing here ranks, sizes, gates, or originates until a future
   pre-registered promotion.

## 1. Census-grounded diagnosis (what the 7 lanes found)

~56 China engine modules, ~50 data stores, 21 rendered pages — and no sovereign brain:

- **No spine.** Regime is a macro-generic quad; conditions are legs without a phase verdict; no
  page or artifact answers phase + participation + entry-quality together. The only synthesis is
  an external-LLM brief (deepseek), buried behind a redirect.
- **NW is nearly blind to China.** Only `china_quad` reaches `world_state`; conditions,
  standouts, sector-central calls, radar ledger, special-sits, command.json are all ORPHANED
  from NW. `cycles_china` spine rows carry `region=None` (query.py `_derive_market` bug). No
  ask-brain China routing, no decision packet.
- **The richest data plane is unused.** `data/china_stocks_raw` (1,587 names, RAW OHLCV, fresh
  to 07-07) is consumed by zero live engines; live engines run on the ADJUSTED store which is
  **5 days stale** (07-02). Microstructure knowledge (limit widths, chase veto) sits in
  `china_signals.py` detached from any per-name packet or market tape.
- **Two flagged bugs turned out already fixed** (red-team verification vs HEAD, 2026-07-08):
  the LHB/block wrong-sign legs were corrected in W6-CN Fix 2 (`_W_DEFAULT` lhb −0.10 /
  block −0.05, sign-pinned by `tests/test_cn_edge_wiring.py`), and the `china_standout_track`
  store-group bug was fixed in #820 (`_PRICE_GROUPS = ("china_stocks", "china")`; ledger live,
  301 rows / 241 graded). No repair wave needed for these — recorded here so future sessions
  don't re-flag stale research docs.
- **Validated edges are orphaned.** Drawdown radar CN_PROFILE (2.07× lift, p=0.01), the
  AI-semis→CPO weekly confirmer (t=3.27), and low-vol tilt have ZERO live consumers.
- **Data gaps behind Codex's assumptions.** No per-name margin history (7-day window), no
  free-float store, THS concept PIT snapshots EMPTY (look-ahead hazard), no fund-issuance/
  new-accounts store, northbound dead since 2024-08, Tushare intermittent/frozen,
  `china_yield` + `china_cgb_curve` accruing with no consumer.
- **Lane misplacement.** `subsector_rotation_china`, `china_masterminds`, `china_strategies`
  build in the US-evening lane → ~19.5h staleness vs the settled Asia close.

## 2. Architecture: one spine, N lobes, historical tapes

```
 existing engines                 NEW lobes                      spine
 china_regime (quad)      ┌ china_microstructure ┐   ┌──────────────────────────┐
 china_conditions (legs)  │ china_participation  │   │  china_market_state.v1   │
 china_sector_cycles      │ china_cycle_phase    ├──▶│ phase · who_controls ·    │──▶ NW packets
 china_allocation         │ china_policy_        │   │ microstructure · policy · │    world_state
 china_intel_bus (CYCLES) └   transmission       ┘   │ rotation · external ·     │    ask-brain
                                                     │ evidence · contradictions │    brief/admin
 NEW historical PIT tapes (the learning substrate)   │ · falsifiers · authority  │    UI cockpit
   limit-state tape 2011→ (from RAW OHLCV)           └──────────────────────────┘
   participation tape (turnover/margin/zt/connect)
   phase tape (backfilled + forward-accruing)
   falsifier auto-grading ledger (self-scoring, no studies)
```

Design laws: deterministic lobes only (LLMs never originate state); every new artifact is
`authority: context_only`; contradictions are first-class outputs, never averaged into a fused
score (positioning-fusion illegal; WA-R1 precedent); heavy backfills run once off the render
path; nightly increments are cheap appends.

## 3. Adjudication of the Codex plan

| Codex item | Ruling | Grounds |
|---|---|---|
| §9.1 `china_market_state.v1` spine | **BUILD** (W6) | genuinely missing; the keystone |
| §9.2 participation lobe | **BUILD** (W2) | stores exist, no reader; SLF-051 killed margin-impulse as SIGNAL — participation REGIME as display context is a different, legal object (corollary 1) |
| §9.5 microstructure lobe | **BUILD + EXTEND** (W1) | limit/chase knowledge exists in `china_signals.py` but no per-name packet or market tape; Codex missed the 2011→ backfill opportunity from RAW OHLCV |
| §9.4 cycle phase classifier | **BUILD** (W3) | quad ≠ A-share phase; rule-based, evidence+falsifiers, backfilled phase tape |
| §9.6 stock lifecycle shelves | **ALREADY BUILT** — china_alpha F1/W1 (RIPENING/ENTRY/RAN live) | delta only: join W1 microstructure fields onto existing shelves (W8) |
| §9.7 theme rotation | **PARTIAL — DEFER core to china_alpha** | china_alpha W2 shipped narrative-confluence; THS PIT snapshots are EMPTY (look-ahead hazard) — start snapshot accrual NOW (W1 side-car), defer theme_phase engine until membership history accrues |
| §9.3 policy transmission | **UNIFY, don't duplicate** (W4) | pboc_stance, policy_watch, official corpora, event calendar, phrase-diff F-C all exist; build the unifying deterministic `policy_impulse` reader + append-only event ledger; CYCLES-owned files untouched |
| §9.8 allocation cockpit | **EXTEND lightly** (W8) | `china_allocation.py` + two overlapping pages exist; add scenario-matrix panel; consolidation of the two pages is a separate declutter wave (not this program) |
| §11 NW adapter | **BUILD** (W7) | lobe packets, world_state china sub-block, decision packet, ask-brain routing; follow R5 macro-rail precedent |
| §13-14 measurement waves | **REFRAME** (W9) | no new gauntlets; forward accrual ledgers + falsifier auto-grading + come-back clocks only |
| §15 do-not-build list | **ADOPTED** | matches DO_NOT_REBUILD + phase-0 verdict rows |

**Fable additions Codex lacked** (census-driven):
- **W5a repairs/ops**: diagnose + fix the ADJUSTED price store's 5-day collection lag
  (`china_stocks` 07-02 vs `china_stocks_raw` 07-07 — every live engine runs on stale prices);
  extract `build_china.py`'s nine inline intel sub-builders into discrete, timed asia-close
  steps (+ dag.yml rows) so per-step timing becomes visible and headroom is reclaimed before
  new lobes are added.
- **W5b validated-edge wiring**: CN_PROFILE drawdown-radar sleeve chip (Tier-1 de-escalation,
  already validated) + AI-semis→CPO confirmer chip (validated confirmer) onto live surfaces.
- **Historical PIT tapes as the primary deliverable class** (operator directive: the DATA is
  the point).
- **Falsifier auto-grading ledger** — every phase print is a tiny machine-graded forecast;
  calibration accrues from day one without a study.
- **THS membership snapshot accrual starts now** — every future theme study is look-ahead-dead
  until PIT membership history exists.
- **Lane unification** (W9): move the three US-evening China builders into asia-close.

## 4. Rulings

- **CN-SYS-R1** — Every artifact this program ships is `context_only`. No rank, size, gate, or
  origination. The word "validated" appears only on the pre-existing validated members it wires.
- **CN-SYS-R2** — Confluence retention (operator ruling 2026-07-08) applies: standalone-null
  factors are legal lobe inputs at context tier; the lobe prints which inputs carry
  standalone-null verdicts.
- **CN-SYS-R3** — Limit-up/zt data is market-structure/breadth context and AVOID/chase-veto
  input only; any BUY-direction use is forbidden (standing kill).
- **CN-SYS-R4** — `who_controls` must print data-gap honesty: northbound is DEAD post-2024-08
  (never read as live zero), Tushare plane is intermittent (0-row days), ETF-flow history is
  ~5 weeks. Unknown is a legal, printed state.
- **CN-SYS-R5** — Every daily phase print embeds machine-checkable falsifiers; the next run
  grades them into `data/china_cycle_phase/falsifier_ledger.parquet`. Auto-grading is not a
  study; promotion from its statistics requires a future pre-registered ruling.
- **CN-SYS-R6** — Ownership fences: `engine/china_intel_bus.py`, `templates/china_intel.html.j2`
  (CYCLES W4), `communiques.parquet` + `filings.parquet` schemas (additive-only, CYCLES
  contracts), `data/china_news/cctv_archive` (live backfill process) are READ-ONLY to this
  program.
- **CN-SYS-R7** — Board rank weights are UNTOUCHED (china_alpha F3/W6 owns recalibration via
  the matured ledger ~07-29). Known tension, recorded not fixed here: `setups.py`
  `CN_ALPHA_WEIGHT=0.35` (residual momentum, a killed signal family) remains the dominant rank
  term until that recalibration; W5b's chips are per-name context and must not be framed as
  endorsing the board's sort order.
- **CN-SYS-R8** — Sign changes to live legs are the owning program's re-registration, never a
  side-effect of this program. (The two wrong-sign legs the census flagged were verified
  already corrected and test-pinned on main — W6-CN Fix 2.)
- **CN-SYS-R9** — Tapes are append-only PIT from their creation date; backfilled history is
  stamped `backfill=true` with the backfill code version. Committed artifacts stay small:
  market-day aggregates + event-level rows, never full name×day matrices.
- **CN-SYS-R10** — New pages follow: `theme.js` include, EN/ZH via `t()` macro, no translated
  `title=` attributes, `inject_data_base` coverage. (Rendered `.j2` pages are exempt from the
  byte-sync law — it binds only plain-copy non-`.j2` assets.) Any edit to the dual-mode
  `china.html.j2` must render-verify BOTH `site/china.html` and `site/china_stocks.html`.
- **CN-SYS-R11** — New asia-close builders are added as `run_py` lines inside the build block
  (before `exit 0`), after the `build_cn_reversal_sleeve` line and before the library-rebuild
  step, WITH a matching `config/dag.yml` asia-lane row each (dag-conformance CI reds
  otherwise). Each new step budgets ≤ ~2 min nightly, degrades gracefully on cache-miss
  stores, and follows the `CN_LANE=asia` gate for any ledger append.
- **CN-SYS-R12** — Raw-plane semantics VERIFIED by red-team (collector fetches
  `auto_adjust=False`; raw/adjusted ratio 1.0 at spot, back-adjustment drift historical) —
  limit reconstruction is legal on `china_stocks_raw`. The tape must handle limit-width eras
  BOARD-AWARE: main 10%; STAR 20% (2019-07→); ChiNext 20% (2020-08-24→, 10% before); BSE 30%
  (2021-11-15→); ST/*ST 5% on MAIN boards only (ST names on STAR/ChiNext keep 20%); IPO
  no-limit windows (STAR/ChiNext first 5 sessions; pre-2014 first-day 44% cap regime)
  EXCLUDED and stamped; price tick rounding limit = round(prev_close × (1±width), 2);
  ex-div-day caveats documented in the tape.
- **CN-SYS-R13** — The spine never averages lobes into one score. It publishes per-lobe states,
  agreements, and contradictions. A single "China score" is a forbidden design (fused-score
  precedents).
- **CN-SYS-R14** — LLM surfaces (deepseek brief, intel narratives) may be DISPLAYED next to the
  spine but never feed it. The spine is closed under deterministic inputs.

## 5. Frozen schema contracts (so waves build in parallel without drift)

**`data/china_microstructure/limit_tape.parquet`** (market-day aggregates, 2011→):
`date, limit_up_count, limit_down_count, sealed_up_close, failed_up_seal_count,
lianban_2plus, lianban_max, limit_up_breadth_pct, limit_down_breadth_pct, st_excluded_counts,
universe_n, backfill(bool)`.
**`data/china_microstructure/limit_events.parquet`** (event rows): `date, ticker, board,
limit_width, event ∈ {sealed_up, failed_up_seal, sealed_down, failed_down_seal, touched_up,
touched_down}, lianban_count, close_off_limit_pct`.
**`site/chinastatedata/microstructure.json`**: latest aggregates + per-name packet fields for
board names: `board, limit_width, limit_state, fillable(bool|context), t_plus_one_risk,
chase_veto{flag, reason}`.

**`data/china_participation/tape.parquet`**: `date, turnover_total, turnover_z20/60,
margin_balance, margin_chg_5d, margin_to_mcap, southbound_net, southbound_z,
etf_share_chg(nullable), zt_breadth, failed_seal_ratio, qvix, qvix_z, broker_rs,
regime ∈ {dormant, institutional_accumulation, retail_ignition, margin_acceleration,
broad_mania, distribution, forced_deleveraging, unclear}, who_controls ∈ {retail, institutional,
margin, state_proxy, offshore, mixed, unclear}, risk ∈ {low, normal, frothy, fire_sale},
data_gaps(list)`.
**`site/chinastatedata/participation.json`**: latest row + evidence/contradiction lists.

**`data/china_cycle_phase/phase_tape.parquet`**: `date, phase ∈ {CAPITULATION, POLICY_PUT,
LIQUIDITY_IGNITION, THEME_LEADERSHIP, BROADENING, EUPHORIA, DISTRIBUTION, DELEVERAGING,
GRINDING_BEAR, REPAIR}, confidence, evidence(list), contradictions(list), falsifiers(list of
{id, expr, horizon_d}), backfill(bool)`.
**`data/china_cycle_phase/falsifier_ledger.parquet`**: `printed_date, falsifier_id, expr,
due_date, outcome ∈ {held, fired, indeterminate}, graded_date`.

**`data/china_policy_transmission/events.jsonl`** (append-only): `{ts, source ∈ {pboc, state_council,
csrc, ndrc, mof, politburo, cewc, other}, kind ∈ {rrr, lpr, omo_mlf, fiscal, property,
capital_market, industrial, rhetoric}, title, url, sectors(list), phrase_diff_ref(nullable)}`.
**`site/chinastatedata/policy_transmission.json`**: `policy_impulse ∈ {easing, neutral,
tightening, targeted_support, market_rescue}, transmission_channel(list), recent_events,
staleness{per_source_days}`.

**`data/china_state/market_state.json` + `site/chinastatedata/market_state.json`**
(`schema: china_market_state.v1`): Codex §9.1 shape, with `phase` from W3, `participation` from
W2, `microstructure` from W1, `policy` from W4, `rotation` from existing sector-cycles/THS
surfaces, `external` consuming the orphaned `china_yield`/`china_cgb_curve` + USDCNH + DXY,
`allocation` from existing china_allocation context, plus top-level `evidence`,
`contradictions`, `falsifiers`, `data_gaps`, `authority: {tier: "context_only", …}`.
Lobe blocks are nullable — the spine degrades gracefully while waves land.

**NW lobe packet** (`neuralweb_lobe_packet.v1`): per Codex §11.1, `may_de_escalate: false`,
`may_originate: false` on every new packet.

## 6. Build waves

Batch 1 (parallel, independent files; every new builder = asia-close `run_py` line + dag.yml row):
- **W1 — Microstructure lobe + limit tape** (`engine/china_microstructure.py`,
  `scripts/build_china_microstructure.py`, one-shot `scripts/backfill_china_limit_tape.py`,
  asia-close step + dag.yml, tests). Includes THS membership snapshot side-car: run the
  existing snapshot appender nightly so PIT membership starts accruing (empty dir today).
- **W2 — Participation lobe + tape** (`engine/china_participation.py`,
  `scripts/build_china_participation.py`, asia-close step + dag.yml, tests). Backfill from
  margin/turnover/QVIX/connect history where it exists.
- **W4 — Policy transmission unifier** (`engine/china_policy_transmission.py`,
  `scripts/build_china_policy_transmission.py`, event ledger, asia-close step + dag.yml,
  tests).
- **W5a — Repairs/ops** (adjusted-store 5-day-lag diagnosis + fix; extract `build_china.py`
  inline intel sub-builders into discrete timed asia-close steps + dag.yml rows — behavior-
  preserving, ordering kept: validation → news → policy_watch → altdata → radar → synthesis
  (intel_analysis) → analogs → special_sits → intel_hub → intel_bus).
- **W5b — Validated-edge wiring** (CN_PROFILE gross_factor chip on CN boards; AI-semis→CPO
  confirmer chip on THS/AI-supply surfaces; both with validation-tier labels; chips are
  per-name/per-sleeve context, not board-sort endorsements per CN-SYS-R7).

Batch 2 (parallel, degrade on missing inputs):
- **W3 — Cycle phase lobe + phase tape + falsifier ledger** (`engine/china_cycle_phase.py`,
  builder, backfill, asia-close step, tests).
- **W6 — Spine** (`engine/china_market_state.py`, `scripts/build_china_market_state.py`,
  asia-close step, SIGNAL_BUS + synapse.yml registration, tests).

Batch 3 (parallel):
- **W7 — NW adapter** (world_state china sub-block, lobe packets, decision packet, ask-brain
  China routing, daily-brief block, admin observatory row; synapse-count pins + dag
  conformance). Also owns the `query.py` `cycles_* → region` question: routing `cycles_china`
  to CN surfaces ungraded projection rows into region-filtered queries — decide WITH the NW/R5
  spine owner, don't slip it in as a "fix".
- **W8 — UI** (china.html market-state hero strip preserving #1896 three-branch logic; NEW
  `china_mechanics.html` cockpit page; cycle-memory block on `china_history.html` reading phase
  tape + `site/china_intel/analogs.json` read-only; lifecycle-board microstructure chips).

Batch 4:
- **W9 — Ops + close-out** (move masterminds/strategies/subsector_rotation_china to asia-close;
  R2 dirs additions if any; accrual come-back clocks in experiments registry; memory; build-map
  regen). **Sequencing law:** W9 edits `daily.yml`/`build_site.py`/`build_vector.py`, which
  collide with open PRs #1891/#1840 — W9 branches off fresh origin/main LAST, after batch 3,
  and rebases if those PRs land mid-day; dag.yml daily-lane rows move with the builders.

## 7. Authority ladder (adopted from Codex §11.3, hardened)

Tier 0 display/context: everything this program ships. Tier 1 de-escalation: only
already-validated members (drawdown radar CN_PROFILE, chase/fillability veto). Tier 2+ requires
future pre-registered promotion under estimator laws (no ticker-cluster CIs without time
control; era splits across the 2010 break; T+1 fills; locked-limit exclusion; effective-N).

## 8. Accrual clocks (registered in W9)

- Falsifier ledger first read: **2026-10-08** (90d of phase prints).
- Participation-tape first descriptive review: **2026-10-08**.
- THS membership snapshots sufficient for first PIT theme study: **~2027-01** (6 months).
- Limit-tape × lifecycle-board confluence candidates (detection print, no verdicts): **2026-09-15**.
- china_alpha W6 rank recalibration (their clock, unblocked by W5a): ~2026-07-29.

## 9. Execution record (2026-07-08)

### Wave → PR map

| Wave | Description | PR |
|---|---|---|
| W0 | Census + adjudication + masterplan skeleton | #1935 |
| W1 | Microstructure lobe + limit tape + THS PIT snapshot side-car | #1938 |
| W2 | Participation lobe + tape | #1939 |
| W4 | Policy transmission unifier | #1940 |
| W5b | Validated-edge wiring (CN_PROFILE + AI-semis→CPO chips) | #1941 |
| W5a | Repairs/ops: adjusted-store lag fix + intel sub-builder extraction + Batch-1 lobe wiring | #1942 |
| W3 | Cycle phase lobe + phase tape + falsifier ledger | #1947 |
| W6 | Spine — china_market_state.v1 | #1948 |
| W7 | NW adapter (world_state china sub-block + lobe packets + decision packet + ask-brain routing) | #1954 |
| W8 | UI — china.html hero strip + china_mechanics.html cockpit + lifecycle-board microstructure chips | #1955 |
| W9 | Ops close-out — CN lane unification + accrual clocks + program record (this PR) | this PR |

### Open questions carried forward

- **`query.py` `cycles_* → region` routing**: `cycles_china` spine rows carry `region=None` (documented `_derive_market` bug); routing them to CN surfaces ungraded projection rows into region-filtered queries. Decision requires NW/R5 spine owner ruling — do NOT slip in as a "fix" (CN-SYS W7 scope, §6 W7 note).
- **Per-date `policy_impulse` reconstruction for pre-series dates**: the policy_transmission lobe can reconstruct impulse only from the `events.jsonl` coverage date; pre-series dates are stamped `null` (honest). A backfill requiring archival PBOC/CSRC records is a future CYCLES-adjacent task.
- **DXY store absent**: the `external` lobe block in the spine reads USDCNH + DXY; DXY is available via the yahoo cross-asset series but no dedicated store exists. Currently degraded gracefully (DXY `null` in external block). Flag for a follow-up store-add.
- **`china_setups.json` written before sleeve_chip assignment**: W5b's CN_PROFILE + AI-semis→CPO chips are per-name context chips; the setup JSON is written by the board builder before sleeve assignments are resolved. Chip display depends on the render-layer join, not the JSON write order. Verify the join is correct in the cockpit (build_china_mechanics) and flag for a follow-up if the chip appears blank on any lifecycle shelf.
- **W8 deferred**: committed pages re-render tonight with the new template (china.html hero strip + china_mechanics.html). The board builder (china_alpha) runs on the US-evening lane and is not blocked.

### Accrual clocks

All four clocks registered in `data/experiments/registry_seed.json` (W9, 2026-07-08):

| Clock | Date | Registry id |
|---|---|---|
| Falsifier-ledger first calibration read | 2026-10-08 | `cn-sys-falsifier-ledger` |
| Participation-tape first descriptive review | 2026-10-08 | `cn-sys-participation-tape` |
| THS PIT membership sufficient for first look-ahead-safe theme study | 2027-01-08 | `cn-sys-ths-pit-membership` |
| Limit-tape × lifecycle-board confluence detection print (no verdicts) | 2026-09-15 | `cn-sys-limit-lifecycle-confluence` |

All clocks are display/context framing; no promotion authority at these reads.
