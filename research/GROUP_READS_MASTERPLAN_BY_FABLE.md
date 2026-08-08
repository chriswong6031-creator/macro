# Group Reads — basket participation, episodes, and earnings co-movement (MASTERPLAN BY FABLE)

**Date:** 2026-08-08 · **Status:** RATIFIED (operator directive 2026-08-08: match and exceed Jodie.ai's theme/basket engine; integrate with the earnings intelligence data plane) · **Program home:** extension waves inside the Thematic Intelligence Layer (`research/THEMATIC_INTELLIGENCE_MASTERPLAN_BY_FABLE.md`, rulings R-TIL-1..9) and the Company Event Intelligence Spine docket (`research/COMPANY_EVENT_INTELLIGENCE_SPINE_AND_PREMIUM_IR_SUITE_BUILD_DOCKET_2026-08-01.md` §3.1/§4.1 `theme_state.v1` charter). This is an **organ-cluster extension, not a new lobe** (DNR:KILL-THESIS-LOBE, R-TIL-1).

---

## §0 ACCEPTANCE GATES (binding on every wave; PR is not done unless)

**G0-1 (contract validity).** Every artifact this program ships validates against its frozen schema in §4 (unknown keys rejected, `authority: "context_only"` stamped, coverage counts present on every cross-sectional stat). A pytest exercises the validator against a golden artifact AND a mutated artifact that must fail.

**G0-2 (no fused score).** No wave may mint a composite/weighted cross-basket score, rank, or "heat" number (R-TIL-3; DNR:KILL-COMPOSITE-REGIME-RELIABILITY-MONITOR). Radar ordering is a deterministic disclosed RULE over named legs, printed on the surface it orders. A grep-able tripwire test asserts the pulse artifact contains no key matching `(score|rank|heat)` outside the documented allowlist.

**G0-3 (display tier, honest nulls).** Every group read ships display/context tier. Washout/turn group constructions carry the Oracle P8 null disclosure in their Tier-2 hover ("sector-grain washout→turn printed NULL standalone; context only, forward-graded"). No entry/rank/size/gate/alert authority anywhere (DNR:KILL-PSS-SR3-PARTICIPATION, DNR:HOLD-IGNITION-SURFACES). The words "igniting/ignition" are banned on these surfaces. The word "validated" is banned (CI-enforced repo-wide).

**G0-4 (nightly sole advancer).** The episode ledger and sympathy ledger advance ONLY in the nightly lane; intraday lanes discard `data/` writes. Append-only with a replay-determinism test (same inputs → byte-identical ledger tail).

**G0-5 (CI registration).** Every new module lands with tests registered as a job in `.github/ci/legacy-jobs.yml` (with the required `if: ${{ false }}` boilerplate) so a pack executes them. Registering the guard is proven by a pack run, not by the file edit.

**G0-6 (render budget).** New nightly compute is an ASSEMBLER over existing artifacts (`data/baskets/ohlcv`, breadth caches, existing organ outputs). Measured wall-clock for the full US basket sweep ≤ 90s on the render host, printed in the PR body. Anything heavier moves off the render path.

**G0-7 (surfaces).** UI waves: per-step visual crops (light + dark + zh) posted in the PR body; banned-vocab scan clean (no internal state names, no untranslated stats, no raw slugs at glance tier); plain-word stance line answers "so what do I do" even when the answer is "watch — don't chase"; graceful absence (a missing JSON renders a quiet null state, never a broken panel); no new header family; `?v=` stamping via the render lane.

**G0-8 (no self-merge on first-pass flagship UI).** Surface-wave builders return PR + crops to the commissioning session for review before merge (spawn-handoff law §4).

**G0-9 (bilingual).** EN/ZH from day one on every new user-facing string, in templates AND builders where copy originates. No translated text in `title=` attributes.

**G0-10 (coverage floors).** Every cross-sectional stat over basket members declares `n_members`, `n_covered`, and refuses (renders null with a plain-word reason) below its floor rather than computing over survivors (nullable-input coverage-floor law; gap-refusal law).

---

## §1 Verdict — Jodie.ai teardown vs. this repo (2026-08-08)

Teardown source: live walk of jodie.ai (landing, `/theme/lin_e4aa24a058493242f958`, Group Radar, Today feed), 2026-08-08.

| Jodie capability | Their form | Ours today | Gap |
|---|---|---|---|
| Group discovery | Market-discovered co-movement "connected sets" (~40), auto-named, noisy (preferred shares as members; misfiled tickers) | `engine/theme_discovery.py` (co-movement candidate generator) + **48 curated PIT baskets** (`data/baskets/membership.json`) + regional twins | **We exceed** — curated + discovered + PIT membership hygiene |
| Participation | % members with **unusual activity** (attention, separated from price direction) | `theme_scoring._breadth_leg` (% above 50d/200d, live on basket pages) — **trend** participation only | **Gap: activity axis** — attention-based participation not computed |
| Direction agreement | "% agreement — not a clean directional move" | `group_flow.cohesion` (mean pairwise member correlation, computed nightly, **dark** — no UI) | **Gap: sign-agreement % + surfacing** |
| Capital flow | Inflow/Outflow + conviction | `theme_flow_rollup.accumulating_pct` (computed, not wired); options `flow_cohorts` (4 cohorts) | Gap: surfacing only |
| Outside confirmation | Filing-linked outsiders (customers/suppliers/partners) confirm/not, with receipts | Issuer-evidence graph EXISTS (`collectors/issuer_evidence.py`, `engine/government_revenue/issuer_graph_expansion.py`) but **govrev-scoped** | **Gap: generalize + join to baskets** |
| Episode history | Discrete co-movement episodes + per-episode persistence % | `basket_history.py` (score history); **no episode ledger** | **Gap: episode state machine + persistence** |
| Arc / washout state | **Absent** — Jodie never answers "is the washout done at group level" | Validated per-name capitulation (`coiled.washout_ctx`, gauntlet-passed), `cycles.cycle_state` (days-since-low), list-agnostic `sector_bottom.member_breadth`, `basket_turn_watch` K-of-N, Weinstein stage + `stage_flows` | **We exceed** once assembled — this is the operator's core ask and Jodie's biggest hole |
| Earnings integration | **Absent** | `earnings_release/` figures+binding (per-event structured data — the dependency `theme_catalyst_binder` declared missing, now shipped), `guidance_gap` (18 themes), `theme_revisions`, `equity_earnings` surprise history | **We exceed** once rolled up per basket — the moat |
| Plain-word reads | Stance lines, strengthens/weakens-if, honest nulls | House design doctrine mandates exactly this | Parity of intent; ours must be assembled |

**Verdict:** the measurement layer is already integrated — in several axes beyond Jodie — but it ships as score legs and dark artifacts, not as a *read*. Five engines compute group participation nightly with zero or partial UI. The product gaps are: activity-participation axis, sign-agreement, episode ledger, outside confirmation at basket grain, per-basket earnings status, and the assembled per-basket READ surface.

## §2 Anti-duplication map (extend these; build nothing parallel)

| Existing organ | Role in this program |
|---|---|
| `engine/theme_scoring._breadth_leg` | Trend-participation input (reuse output, do not recompute) |
| `engine/basket_breadth_divergence.py` | Participation-crack / stealth-deterioration input (currently DARK — GR1 lights it) |
| `engine/group_flow.py` | Cohesion/broadening/leadership + cluster map input (DARK — GR1 lights it); sign-agreement % lands HERE as a new field, not a new module |
| `engine/coiled.py` (`washout_ctx`) | Per-member capitulation leg (gauntlet-passed); extended to expose capitulation date/age |
| `engine/cycles.py` (`cycle_state`) | Days-since-low per member |
| `engine/sector_bottom.member_breadth` | List-agnostic member aggregation shape (washed_out_share/turning_share) |
| `engine/basket_turn_watch.py` / `basket_turn_cohort.py` | K-of-N turn confluence + qledger grading (unchanged; pulse LINKS to its read) |
| `engine/weinstein_stage.py` + `engine/stage_flows.py` | Stage share per basket (stage2_share/stage4_share) |
| `engine/guidance_gap.py` | Guidance-direction rollup pattern (generalized 18 themes → 48 baskets, ≥2-filer law preserved) |
| `engine/theme_revisions.py` | Revision-breadth rollup pattern (same generalization) |
| `collectors/equity_earnings.py` / `edgar_eps.py` | Beat-rate + report-date inputs |
| `engine/earnings_release/` (figures, binding) | Per-event structured figures for beat/guide classification |
| `collectors/issuer_evidence.py` + `engine/government_revenue/issuer_graph_expansion.py` | Relationship-graph machinery to generalize for outside confirmation (GR3) |
| `templates/basket_detail.html.j2` + `templates/baskets.html.j2` + `_baskets_desk.html.j2` | THE surfaces. No new page family (DNR:KILL-ROTATION-SCHEDULE analog: no parallel surface) |
| `engine/ai_desk.py` | May NARRATE from pulse artifacts (A7: de-escalate only, never originate) |

## §3 Inherited rulings (binding)

- **DNR:KILL-PSS-SR3-PARTICIPATION** — participation-recovery as a directional/timing signal is killed. Group Reads ships participation as *description*, never as a buy/sell read.
- **DNR:KILL-PSS-SR2-PEER-DIFFUSION**, **DNR:KILL-RS-DISPERSION-GATES** — no peer-diffusion bottom-timing, no RS-based dispersion gates.
- **DNR:HOLD-PSS-CD1-CROWDING** — co-movement/dispersion overlays accrue prospectively; no authority.
- **DNR:KILL-ROTATION-SCHEDULE** — rotation context folds into Turn Desk artifacts; no parallel rotation surface.
- **DNR:HOLD-IGNITION-SURFACES** — no "igniting" claims; arc states are descriptive with honest nulls.
- **R-TIL-3** — no fused cross-basket number. **R-TIL-9** — new evidence lands into existing organs.
- **Oracle P8 null** — sector-grain washout→turn printed NULL standalone; all arc reads disclose this in Tier-2.
- **Company Event docket §0.2** — LLMs extract/de-escalate only; residual-theme constructs reach Prophet/Neural Web only via point-in-time accrual + pre-registered promotion.

## §4 Frozen contracts

### 4.1 `group_pulse.v1` (per basket, nightly; `site/basketdata/pulse.json`, one object per basket_id)

```json
{
  "schema": "group_pulse.v1",
  "authority": "context_only",
  "generated_at": "<iso8601>",
  "basket_id": "ai_infra",
  "as_of": "2026-08-07",
  "n_members": 14, "n_covered": 13,
  "participation": {
    "activity_share": 0.62, "activity_n": 8,
    "trend_share_50d": 0.71, "trend_share_200d": 0.57,
    "breadth_divergence": {"present": true, "fields": "mirror of basket_breadth_divergence output"}
  },
  "direction": {
    "agreement_pct": 0.31, "sign": "up", "median_move_spy_adj": 0.0019,
    "cohesion": 0.44, "leader": {"ticker": "NVDA", "kind": "activity"},
    "strongest": {"ticker": "...", "ret": 0.021}, "weakest": {"ticker": "...", "ret": -0.008}
  },
  "arc": {
    "state": "washout_complete_awaiting_reclaim",
    "washed_out_share": 0.83, "washed_out_n": 10,
    "reclaimed_20d_share": 0.25, "capitulation_median_age_d": 7,
    "stage2_share": 0.17, "stage4_share": 0.5,
    "drawdown_pctile_own_history": 0.91,
    "null_disclosure": "oracle_p8"
  },
  "episode": {
    "active_now": true, "current_start": "2026-08-04", "sessions_active": 3,
    "state_change": "strengthening|steady|cooling|quiet"
  },
  "coverage_warnings": ["..."]
}
```

Arc `state` ladder (deterministic, disclosed; evaluated in order, first match wins; floors: `n_covered ≥ 5` and `n_covered/n_members ≥ 0.6`, else `state: "insufficient_coverage"`):
1. `washout_in_progress` — washed_out_share ≥ 0.5 AND capitulation_median_age_d ≤ 5
2. `washout_complete_awaiting_reclaim` — washed_out_share ≥ 0.5 AND age > 5 AND reclaimed_20d_share < 0.5
3. `turning` — washed_out_share ≥ 0.5 AND reclaimed_20d_share ≥ 0.5
4. `advancing` — stage2_share ≥ 0.5 AND trend_share_50d ≥ 0.6
5. `distributing` — stage4_share ≥ 0.4 AND trend_share_50d < 0.5
6. `quiet` — otherwise

### 4.2 Episode ledger (`data/group_pulse/episodes.parquet`, append-only, nightly-advanced)

Columns: `basket_id, episode_id, start_date, end_date (null while open), sessions_active, sessions_span, members_ever_active, members_persisted, persistence_share, closed (bool), advanced_at`.
Rules (disclosed on-surface): a basket-day is ACTIVE when `activity_share ≥ 0.5` and `activity_n ≥ 3`; an episode joins active days separated by ≤ 2 inactive sessions; an episode closes after 3 consecutive inactive sessions; hysteresis exit threshold 0.35. `persistence_share` = members active in every active session ÷ members active in ≥ 1 session. Provisional current-episode rows are recomputed until `closed`; closed rows are immutable (provisional-bucket law: a closed row is never edited by a later advance).

`activity` per member-day: |SPY-adjusted return| z ≥ 1.5 vs own trailing 63d, OR volume ratio ≥ 1.5× own 63d median (missing volume → return leg only, disclosed via `activity_basis` count fields).

### 4.3 `group_earnings_pulse.v1` (per basket, nightly; `site/basketdata/earnings_pulse.json`)

```json
{
  "schema": "group_earnings_pulse.v1", "authority": "context_only",
  "basket_id": "ai_infra", "as_of": "2026-08-07",
  "season": {"n_members": 14, "n_reported": 9, "n_upcoming_14d": 3, "next": [{"ticker": "...", "date": "...", "session": "amc"}]},
  "results": {"n_beat": 7, "n_miss": 2, "n_inline": 0, "n_no_data": 5, "beat_basis": "eps_surprise; floor n_reported>=4"},
  "guidance": {"band": "RAISING|NEUTRAL|CUTTING|BROAD-RAISE|null", "n_filers": 3, "basis": "guidance_gap generalized; >=2 distinct filers else null"},
  "revisions": {"net_up_share": 0.58, "n_covered": 11},
  "drift": {"pos_share_5d": 0.67, "n": 9},
  "sympathy": {"ratio": 1.8, "n_events": 22, "window_q": 8, "basis": "median |SPY-adj move| of non-reporters on member report days ÷ their unconditional baseline; floors: >=4 members with >=4 events",
               "directional": {"beat_day_median": 0.004, "miss_day_median": -0.006, "n_beat_days": 14, "n_miss_days": 8}}
}
```

`sympathy.ratio` is THE "do earnings move together in this basket" stat. It ships with N everywhere, floors enforced, null below floor.

## §5 Waves

**GR0 — group pulse plane** (opus builder, fresh worktree): `engine/group_pulse.py` assembler + episode ledger + `coiled.washout_ctx` date-exposure extension + capitulation→20dma-reclaim pairing primitive + sign-agreement field added to `group_flow.py` + nightly wiring + tests + CI registration. US 48 baskets. Gates: G0-1..6, G0-10.

**GR1 — Basket Read surfaces** (designer/opus after GR0+GR2 PRs exist): upgrade `basket_detail.html.j2` with a top READ band — plain-word stance line; four tiles (Participation / Direction / Arc / Earnings); "What we're watching" strengthens/weakens conditions; "Has this happened before" episode section; member table separating unusual-activity from direction. Upgrade `baskets.html.j2` board with state/change chips + disclosed ordering rule (state-change first, then activity_share, then agreement; rule printed on page). Gates: G0-2, G0-3, G0-7, G0-8, G0-9. Falsifier language backstage per operator law.

**GR2 — group earnings pulse** (opus builder, parallel with GR0): `engine/group_earnings.py` per §4.3 — clock, beat rollup, guidance generalization, revision breadth, drift, sympathy ledger (`data/group_pulse/sympathy.parquet`, nightly-advanced, append-only closed rows). Tests + CI registration. Gates: G0-1, G0-3, G0-4, G0-5, G0-6, G0-10.

**GR3 — outside confirmation** (follow-on): generalize issuer-evidence relationship extraction beyond govrev scope; per-basket filing-linked outsiders with confirm/not-confirm state + receipts. Off-render-path collection; nightly join only. Separate contract `group_linked_outsiders.v1` to be frozen at wave start.

**GR4 — radar/rotation integration + zh sweep + glossary**: fold basket state-change events into Turn Desk artifacts (no parallel surface); `docs/site_semantics/` glossary rows for every new stat; regional twins (CN/HK) after US proves.

Sequencing: GR0 ∥ GR2 now → GR1 on their real schemas → GR3/GR4. GR0 and GR2 touch disjoint files (`group_pulse.py`+`group_flow.py`+`coiled.py` vs `group_earnings.py`); no shared-file collisions.

## §6 Promotion path (later, not now)

Everything display/context tier. IF the operator later wants authority (e.g., arc state as a Prophet confluence input), the path is: point-in-time accrual from ledgers (already append-only), pre-registered gates, its own gauntlet — same bar as `basket_turn_cohort` (promotion question not before 2027). Nothing in GR0-4 pre-commits to promotion.

## §7 Competitive rubric pointer

The operator's post-build audit ("does this beat Jodie/Struct/Quartr/EarningsCall.ai/EquityDesk individually") grades this program on: read assembly quality, membership hygiene vs Jodie's noise, arc answers Jodie lacks, earnings integration Jodie lacks, honest-null discipline, bilingual reach. Rubric doc to be written at audit time.
