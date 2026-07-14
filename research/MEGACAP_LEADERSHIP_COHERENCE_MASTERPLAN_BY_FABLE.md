# Megacap & Leadership Coherence (MLC) — grandmaster plan (W0)

**Chartered:** 2026-07-14, from `research/POSTMORTEM_20260714_ROTATION_MISS_BY_FABLE.md` (the 07-14 rotation miss).
**Goal:** the US surfaces must (a) track each megacap as a first-class beast *and* as a cohort, (b) speak with one reconciled voice at the glance tier, (c) de-escalate stale bullish calls as fast as momentum actually breaks, and (d) accrue the PIT context needed to eventually promote leadership signals through the gauntlet. Display-tier ships freely; authority changes only through pre-registered gates (house law).

---

## 1. Rulings (MLC-R1..R10)

- **MLC-R1 — consume, don't rebuild.** MLC consumes `mag7_regime` (M7C owns cohort state), `leader_lifecycle` + `data/rs_series/` (LRV owns per-name RS states), `rotation_events.jsonl` (RC owns detection), IHM index states, VSB AI-breadth split, Oracle Tier-F panel, Ratio Lens pairs (`data/oracle/ratio_pairs.json`). Any new pair math routes through the Ratio Lens registry, not a parallel implementation.
- **MLC-R2 — display-tier first.** Every wave below ships display/context freely (nulls printed). Nothing in MLC gains rank/size/gate authority without its pre-registered study in §5 passing at the frozen ruler.
- **MLC-R3 (inherited kill)** — no rotation × cycle-position entry confluence, at any tier (DO_NOT_REBUILD row; W0.4 keystone).
- **MLC-R4 (inherited kill)** — no RS-dispersion gates (zero-sum tautology, R-4). Dispersion may be *displayed*, never gate.
- **MLC-R5 (inherited null)** — no timing-into-rank blending on the US board (Phase-0 cosmetic/dilutive verdict stands).
- **MLC-R6 — glance tier per DESIGN_DOCTRINE.** Plain-word state + stance, hard word budgets, no internal organ names, technicals demoted to hover/detail. Bilingual; CJK via Write/Edit tools only; no translated `title=`.
- **MLC-R7 — disagreement is disclosed, never silently averaged.** When organs split on an asset, the glance tier says so in plain words ("our trend read likes this; our entry read doesn't — split view"). Silent averaging manufactures false confidence; hiding the split manufactured this postmortem.
- **MLC-R8 — de-escalation is display-legal, escalation is not.** Overlays in W2/W4 may demote/dampen a displayed BUY (with the receipt shown); they may never originate or upgrade a buy. Mirrors the standing LLM de-escalation law.
- **MLC-R9 — every megacap tile answers "so what do I do."** Even when the honest answer is "watch — don't chase."
- **MLC-R10 — earnings chip is disclosure, not a gate.** "Reports in N days" informs; it does not suppress or trigger signals (pre-event conviction dampeners are RIC-excluded territory).

## 2. Boundary map (who owns what — MLC touches none of these cores)

| Program | Owns | MLC's relationship |
|---|---|---|
| M7C (#2273-79) | Mag7 cohort trend×structure state | consume `data/mag7_regime/latest.json`; W1 re-surfaces it |
| Leader Radar (LRV) | per-name lifecycle states, RS series store | consume states for tiles; never re-derive |
| Rotation Command (RC) | rotation events, fragmentation index; **RC-R9 S1/S2 = only legal stance-override path** | consume events; MLC does NOT build stance overrides — it waits for RC W2 |
| IHM (#2298) | index-grain RSI-MACD hybrid | consume; sector-grain hybrid momentum is open space if ever needed (not in MLC W1-W5) |
| VSB (W0-W6 built) | vol/implied-corr organs, AI-vs-rest breadth split | consume for suction context |
| Oracle Tier-F (#2550) | style-factor rotation display (honest-null prior) | consume as context row |
| Ratio Lens | pair-ratio machines (qqq_vs_rsp live) | new rungs (e.g. NVDA/mag7-ex-NVDA) registered THROUGH it |
| RIC (#2527) | event-window engines, yield momentum | MLC stays out; earnings chip is date disclosure only |

Killed display artifact honored: `sector_rotation_schedule.v1` (DO NOT BUILD — duplicates Turn Desk; kill recorded in `ORACLE_ROTATION_TM_CODEX_ADJUDICATION.md`, though absent from DO_NOT_REBUILD §1-4 / the compiled registry — a pre-existing hygiene gap flagged separately). The W1 Leadership Board is a megacap/leadership surface, not a rotation schedule; it displays states, not a calendar of sector turns.

## 3. Waves

### W1 — Leadership Board (display; the "look backward" fix)
A single glance surface, present on BOTH us_stocks.html and the macro dashboard (the M7C panel today renders only behind `mode=='stocks'` — `dashboard.html.j2:1738`):
- **Seven individual megacap tiles** (AAPL MSFT NVDA AMZN GOOGL META TSLA): plain-word state from LRV lifecycle + M7C member fields (run state, vs 50/200dma, RS trend, contrib to cohort run), one-line "so what" per MLC-R9, earnings-date chip (W5 dependency). Each name is a beast of its own — the operator's core ask.
- **Cohort strip**: M7C trend_state in plain words, generals line, cw-vs-ew spread rung (from existing M7C fields), day-count of run.
- **Sector RS rank strip** (surfacing, NOT a new organ): `engine/sectors.py:rs_table` already ranks the 11 SPDR sector ETFs (cap-weighted by construction) on 20d/60d RS, and sector_central already renders "RS #N — leading/lagging" inside its detail view. W1 lifts that existing rank to the Leadership Board glance tier with leader/laggard words. No new ranking math, no gating, no dispersion math. (The W0 census claim that "no program owns this" was wrong — adversarial review caught it; the gap is *glance-tier surfacing*, not a missing organ.)
- Null honesty: when M7C inputs are absent (mtf/flow/mags fail-open nulls), tiles say "no trend read" per current idiom, not blank.

### W2 — Coherence layer (display; the #1 root-cause fix)
- **Stance matrix organ**: nightly, per asset/basket/sector, collect the verdicts already emitted (sector_central conviction, theme reco, basket_confluence class, allocation membership, M7C state where applicable) into one artifact with an agreement grade.
- **Disagreement disclosure** (MLC-R7): glance chips on baskets/allocation/us_stocks show "split view" + hover receipt when organs disagree ≥2 tiers.
- **ACT-NOW demotion** (MLC-R8): a basket whose parent sector sits at Reduce cannot render in the clean-BUY list; it moves — visibly, with the reason printed ("sector conviction is Reduce — demoted") — to a "conflicted" shelf. This is a change to an explicitly display-only focus list (`theme_scoring.py:1039` comment; the existing `add_on_pullback` split is the precedent), so it ships display-tier; no `_reco()` logic touched (M7C-R4 respected). Known downstream consumer: `engine/china_act_now.py:74` reads `act_now.buy` into its action lane — the demotion propagates there by design (verified: that lane carries no size/gross/gate authority); the build PR greps all `act_now` consumers before merge.
- **Clock disclosure**: allocation page states its ruler in plain words ("slow book — reacts over months, held through single weeks"), killing the managed_care-style surprise.

### W3 — Megacap suction organ + field guide (display + PIT accrual; the operator's thesis, instrumented)
Per `understanding-before-backtest` law, field guide FIRST:
- **Field guide**: catalog historical megacap suction episodes (NVDA 2023-2025 runs, AAPL 2020, MSFT 1999…): how index, equal-weight, rest-of-Mag7, and laggard sectors behaved during monster runs; institutional practice notes; a playbook with per-regime behavior. Rulers for any later study derive FROM this playbook.
- **Concentration series organ** (display): NVDA and Mag7 share of SPX market cap; share of composite dollar volume; cw-vs-ew suction ladder — NVDA vs Mag7-ex-NVDA vs SPX-ex-Mag7 vs RSP — new rungs registered through Ratio Lens (MLC-R1); breadth-under-rally divergence read consuming the VSB AI-split.
- **PIT ledger columns** for all of the above so the promotion studies in §5 have honest history from day one. A null on any of these as a standalone signal is retained as confluence context (house law), not deleted.

### W4 — Fix the momentum-fade texture family (display; the 07-07 detector)
A fade texture already exists — `rollover_risk` (`engine/basket_score.py:176-210`, surfaced as the baskets-page rollover watch). On 07-13 it printed big_pharma/insurance at **0.0/low** while flagging the AI/semis complex (which rallied next day) as high — an anti-signal that night, because its legs are extension/deceleration-centric and a non-extended sector rolling off a top scores ~0. W4 therefore **extends the existing texture, not a parallel one**:
- Add a **histogram-fade-off-peak leg** (N-session MACD-histogram fade from a local peak + MA10 slope decay — exactly what XLV printed from 07-07) to `rollover_risk`, parameters frozen in the build PR, per-leg values printed on hover.
- **Wire the texture into ACT-NOW demotion** (via the W2 coherence layer): today `rollover_risk` feeds only a separate watch list; even when it fires, nothing demotes a clean-BUY. Effect per MLC-R8: demote to the conflicted shelf with the plain-word chip ("momentum cooling — N sessions of fade"); never generates sells; sector_central untouched.
- Guard: fade legs are descriptive display, not a new thrust/rollover *signal* (no radar leg, honoring the MCO-thrust kill's spirit until §5 says otherwise). Retro-check in the build PR: replay the new leg over the 07-07→07-13 window and print what it would have said (nulls included).

### W5 — Earnings-proximity wiring (display)
`engine/earnings_blackout.py` + `data/earnings/` already exist, and the standouts board already consumes them as a suppress-only veto — which was **stale-inert on 07-13** (`store_stale: true, count: 0`). W5 = (a) fix the store-freshness defect (root-cause why it was stale; add a freshness tripwire), (b) wire "reports in N days" *display* chips into: action board popovers, standout cards, ACT-NOW rows, W1 megacap tiles. Disclosure only (MLC-R10). GS would have carried "reports tomorrow" on 07-13.

### W6 — Pre-registered promotion studies (queued; gates AUTHORITY, never builds)
Registered before any trainer/scanner exists; frozen rulers; nulls published:
- **S-MLC-1 — leadership continuation**: does M7C `turning_up`/`running_*` predict forward cw excess vs SPY at the 10-80d ladder? (Time-preserving nulls; episode-permutation per DT-R14 law; overlap-corrected.)
- **S-MLC-2 — suction regime conditionality**: conditional on W3 suction ladder state, do laggard-sector bounce entries underperform their unconditional base rates? (This is the operator's "liquidity gets sucked away" claim, made falsifiable.)
- **S-MLC-3 — weekly-confirmation cost on leaders**: for sectors at RS #1-2 within 2% of 52wk highs, what did the HALF SIZE weekly-wait cost vs full entry, historically? (Directly interrogates the XLF construction; outcome may justify a leaders-exception prereg, or print a null and close it.)
- Any stance-override ambition routes through RC-R9 S1/S2 (RC W2), not MLC.

## 4. Explicitly out of scope
- Rebuilding cohort state, RS series, rotation detection, vol organs, factor rotation (all owned — §2).
- Any entry gating from RS ranks, dispersion, or cycle-position confluence (MLC-R3/R4/R5).
- Touching `sector_central` fusion weights or theme `_label()/_reco()` semantics (M7C-R4 standing; W2 demotion operates on the display list downstream of reco, not on reco).
- Pre-event conviction dampeners (RIC-excluded).
- LLM-originated signals anywhere (LLMs may only de-escalate calibrated keys).

## 5. Sequencing & acceptance
- **W1+W5 first** (pure surfacing of existing organs + existing earnings data; biggest user-visible fix per token). Then **W2** (coherence artifact + demotions), **W4** (cooling texture), **W3** (organ + field guide can run parallel to W2/W4), **W6** registrations land with W3's PIT columns.
- Nightly-budget: all new organs are cheap pandas passes over existing stores; anything heavier goes off the render path per house law. New accrual steps go in `collect_tail`, not `collect`.
- Every build PR: no git ops by builder agents beyond their branch; grep call sites so nothing lands as a dead wire (new-organ nightly wiring check); come-back item = first-nightly artifact check.
- Acceptance for the program (the postmortem's counterfactual): had MLC been live on 07-13, the user would have seen — Mag7 cohort "turning up, day 8, NVDA/META/AAPL leading" on the macro page (W1); big_pharma/insurance demoted from clean-BUY with "sector conviction is Reduce" receipts (W2); healthcare carrying "momentum cooling since Jul 7" chips (W4); XLF entry carrying "GS reports tomorrow" (W5); and a suction ladder showing whether the run was draining the rest of the tape (W3).
