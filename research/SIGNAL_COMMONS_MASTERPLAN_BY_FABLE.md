# Signal Commons & Event Intelligence — masterplan (by Fable)

**Status:** ACTIVE (dispatched 2026-07-05). **Owner:** Fable main loop (adjudication/merges); Sonnet builds; Opus reviews.
**Provenance:** external ChatGPT site-review memo (2026-07-05, blind to codebase) → 5-lane codebase census → Opus scorecard → Fable adjudication. This document is the ruling of record; the chat transcript is not.

---

## 1. Verdict on the external memo

The memo proposed 8 "vectors" + a unified signal object. Ground-truthing found:

- Its 8 proposals are **35–70% already built** (per-cluster census results summarized in §5).
- Its headline architecture — "force every desk to emit one shared object" — **already exists** as `engine/spine.py` (the spine row contract) + `config/synapse.yml` (artifact contract). The gap is narrower: role taxonomy, per-row half-life, falsifier passthrough.
- Its central move — fuse positioning ingredients into one escalating composite ("Positioning Pressure +74 / Accumulation") — is the **forbidden shape** under house epistemics: composites may not originate escalation from ingredients that are un-backtestable (short interest has no PIT history), stale-mismatched (13F 45-day lag vs daily short volume), or already killed (narrative momentum, IC≈0, family retired).
- What survives adjudication: the **meta-instincts** — make signals commensurable (spine roles), measure decay instead of assuming it (half-lives), make events scoreable priors (event-study extension), stop hidden duplicate bets (reflexivity), and **start the PIT tapes now** so future gauntlets become possible.

## 2. Rulings

- **R1 — Kernel-as-conditioner: DENIED for now.** Neural Web standing clocks govern (kernel-FDR 2026-10, weight authority ~2027-05). The kernel's own estimates are the thing on probation; conditioning live signals on them before their gate matures is an ungauntleted layer changing behavior. No parallel effort; the NW program owns the flip when the clock matures.
- **R2 — Price-memory bundle stays parked.** AVWAP distance, volume-at-price shelves, gap-fill maps, overhead supply, float turnover remain parked behind the Entry-Intelligence P1.3 trio ablation (existing EI masterplan §2 ruling). On P1.3 completion they run as ONE bundled phase-0 **inside the EI program**, not here. A fresh external memo is not evidence; the ruling stands.
- **R3 — Positioning fusion is illegal as proposed.** Legal path: (a) W0 starts PIT accrual for every latest-only ingredient; (b) each ingredient gets its own measured-lead phase-0 once history accrues; (c) survivors become **de-escalation / conditioning gates**, never a fused escalating score.
- **R4 — Reflexivity overlay is a mastermind-fix wave, not a new engine.** It addresses that program's documented pathology ("Brains overbuy semis/AI, lose to defensive book") and rides existing `engine/factor_exposure.py` betas + theme membership + earnings-date clustering. Coordinate with the mastermind-fix wave plan at dispatch.
- **R5 — "Expectation Drift" is not a program.** Data-blocked legs (transcripts, revenue-revision direction, per-analyst accuracy, implied-vs-historical move) go to the W6 paid-data memo. The buildable leg — per-name event-response memory — merges into W3 Event Intelligence (same harness, same event tables).
- **R6 — Options flow classification parked.** Every label the memo wants (sweep/block, buyer/seller-initiated, open/close attribution, call-buy vs put-sell) requires the per-trade NBBO tape, which is not entitled. Revisit only through the W6 decision. EOD positioning reads (ΔOI, Vol>OI, measured dealer gamma) already exist and stay as-is.
- **R7 — Everything here lands display-only** (`is_context_only=true`). Promotion happens only through pre-registered gates. Nightly remains the sole advancer of forward ledgers. Nothing added to the nightly render path unless trivially cheap; heavy compute runs off-path with artifacts to R2.
- **R8 — Spine v2 is descriptive, not behavioral.** New columns are additive with conservative defaults (context-only unless already `size_binding`); the migration must not flip any signal's effective authority; no behavioral code may read the new flags until a separate, gated change proposes it.

## 3. Waves

| Wave | Scope | Acceptance gate | Status |
|---|---|---|---|
| **W0 — PIT tape-rolling** | Audit every display-only ingredient store for latest-only collectors; add append-only PIT accrual (FINRA short interest mandatory; other small/low-risk gaps opportunistic). Engines keep reading "latest" unchanged. | Idempotent appends keyed by as-of AND capture date; sentinel staging covers any new tracked path; zero render-budget delta; nulls/gaps documented. | DISPATCHED |
| **W1 — Spine v2** | Additive spine columns: 5-way role flags (`is_alpha/is_timing/is_veto/is_sizing/is_context`), `falsifier` passthrough from claim layer, nullable `half_life`. Contract tests; minimal committee.html role/falsifier chips (templates source, bilingual, data-tip pattern). | All adapters emit the contract; old-schema parquet loads with defaults; kernel/decay/ask_brain unaffected; R8 holds (no authority flips). | DISPATCHED |
| **W2 — Measured half-lives** | Fit per-family decay curves from graded spine outcomes (age-at-fire vs realized excess). Print nulls where n under floor. Fills W1's `half_life` slot, display-only. | Opus stats review mandatory; n-floors pre-stated; no smoothing that manufactures signal. | QUEUED (after W1) |
| **W3 — Event Intelligence** | (a) Extend event-study priors from corporate events to FDA/clinical, index add/remove, lockups, gov-contract awards, earnings — existing Newey-West/BH-FDR/DSR harness + existing collectors; add max-drawdown and pre-event-drift ("already reacted") columns. (b) Per-name event-response fingerprints (beat-and-fade memory) where n ≥ floor. | Priors carry n, CI, and null prints; weekly regen off render path; R2 for heavy artifacts; display-only integration into special-situations + stock pages. | QUEUED |
| **W4 — Reflexivity overlay** | Duplicate-exposure matrix (factor betas + theme membership + earnings-date clustering) + candidate-card context chips. Dispatched INTO mastermind-fix per R4. | Risk-clustering read only — no alpha claim, so beta OOS-instability caveats are printed, not hidden. | QUEUED |
| **W5 — Small lanes** | (a) Committee-dissent study: do unanimous vs contested spine calls grade differently? Research memo off existing parquet, nulls printed. (b) Days-to-build liquidity chip from Massive ADV. | Memo pre-registers its cut before looking; chip is display-only. | QUEUED |
| **W6 — Paid-data decision memo** | One document: every data-blocked leg (earnings-call transcripts, revenue-revision direction, per-analyst accuracy, NBBO options tape) with cost, what it unlocks, and which parked builds it would revive. Single consolidated user decision. | User decides once; no drip requests. | QUEUED |

Sequencing: W0 → W1 → W2 on the spine track; W3, W4, W5 parallel; W6 anytime. One wave = one branch off fresh origin/main = one PR = same-day squash-merge.

## 4. Parked list (with unblock conditions)

| Item | Why parked | Unblocks when |
|---|---|---|
| Positioning fusion ("+74") | Forbidden composite shape (R3) | W0 tapes accrue → per-ingredient phase-0s → conditioning gates only |
| Options flow classification | NBBO tape not entitled (R6) | W6 decision buys the tape |
| Cross-asset beta expansion | Existing secondary betas fail OOS (persist 0.02–0.22) — evidence against | A consumer program demands a specific beta and funds its stability test |
| Narrative-to-money extra legs | `foresight_divergence` ledger still in phase-0 accrual | Ledger grades out |
| Kernel-as-conditioner | NW standing clocks (R1) | 2026-10 / ~2027-05 clocks |
| AVWAP / volume-profile bundle | EI §2 ruling (R2) | EI P1.3 completes → bundled phase-0 in EI program |
| Edge-budget gauge; expected-but-absent anti-signals | Good ideas, vague consumers | Backlog; revisit post-W3 |
| ETF creation/redemption flows | No data source | W6 memo if a vendor is worth it |

## 5. Census anchors (what already exists — abbreviated)

- **Positioning ingredients:** 13F + accumulation trend + manager grades (`engine/smart_money.py`, context-only), Congress via paid Quiver (live 2026-06-19, per-member tiers in `engine/congress_members.py`), activist/13D track records (`engine/activist.py`), FINRA off-exchange/ATS (labeled honestly), insider factor at DSR boundary. All separate; zero fusion — by design.
- **Entry quality:** eq_score + T1–T4 confluence cascade + COILED washout-reclaim + late-chase decay all live and gauntleted; species registry 17 species; replay infra active (EI program).
- **Expectations:** EPS revision breadth/dispersion (T4, yfinance PIT accrual recently started), RPO/backlog solid, 8-K guidance tilt coarse; revenue-revision direction structurally unavailable on yfinance.
- **Events:** corporate-event priors (20D/60D + win rate) already live on special-situations; NW/BH-FDR/DSR event-study scripts exist; collectors exist for FDA/trials/gov-contracts/index-changes/IPO-lockups with no priors yet.
- **Options:** EOD/T+1 positioning reads live (signed premium, ΔOI, 0DTE share, measured dealer gamma); minute-bar sign recovery 0.41 → direction published soft.
- **Spine/grammar:** `engine/spine.py` COLUMNS contract + `is_context_only` + `size_binding` + synapse tiers + signal-lab tiers; missing only role taxonomy, per-row half-life, falsifier passthrough.

## 6. Build-law reminders bound into every dispatch

Branch off fresh origin/main; never bare `git stash`; no data/ commits from build lanes; sentinel git-add staging must cover any new nightly-written tracked path; numpy scalars cast to python natives before any json write; tests copy real call shapes; site pages edited via templates/ + builders, never site/*.html; bilingual EN/ZH with no translated text in title= attributes; render budget ~67 min is law.
