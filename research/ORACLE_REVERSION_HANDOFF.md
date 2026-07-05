# Oracle Reversion Signal-Discovery — HANDOFF / CONTEXT (paste to a fresh Claude session)

You are continuing an autonomous signal-discovery loop for the **Oracle** sector-rotation research factory. Your job: brainstorm first-principles reversion-entry signals, backtest them on the REVERSION metric, gauntlet the winners, and grow a validated base. **Delegate screening/gauntlet/generation to Sonnet subagents (model routing law); you orchestrate + adjudicate.** Read this whole file, then read the two prereg docs it points to, then start looping.

## THE MISSION (and the trap to avoid)
The operator trades ROTATION, not factors: enter at a **basing low** (their real engine is a MACD + StochRSI 2D/3D bullish confluence), ride the bounce, **exit near the 2D-StochRSI top — average hold ~20-30 sessions.** They do NOT hold 3 months.

**DO NOT measure 63-day forward excess.** That is a value/factor ruler and it *selects against* fast reversions (a +7% bounce that mean-reverts by day 63 scores ~0). A whole prior search on 63d returned "nothing" for exactly this reason. The correct ruler is **short-horizon reversion-capture** (see `research/ORACLE_REVERSION_GATE_PREREG.md`):
- Per entry, ABSOLUTE (NOT excess-vs-SPY — SPY is ~50% tech and hides defensive rotation): **MFE** (25-session max up-excursion), **MAE** (25-session max drawdown = safety), **ret_exit** (~21-session time-exit ≈ the operator's hold), split by **risk_on/risk_off**.
- **Safety (asym = MFE/|MAE|) and win-rate are the criteria, NOT mean return. Drawdown-avoidance > gain size.**

## THE APPARATUS (all built + merged; commands)
Worktree/data conventions: work in a merged-main worktree; run with `--data-dir "<MAIN>/data"` where `<MAIN>` = `/Users/chriswong/Documents/Cluade/Macro Dashboard`. Panels (`data/oracle/panel_s.parquet`, `episodes_s.parquet`) are gitignored and get PURGED by R2 cleanup — if missing, rebuild (deterministic, ~few min):
```
python -m scripts.build_oracle_panel --tier s --data-dir "<MAIN>/data"
python -m scripts.build_oracle_episodes --tier s --data-dir "<MAIN>/data"
```
Reconcile after rebuild: A15 reversion screen must show ~ n=2357, MFE +7.15%, MAE −3.90%, ret_exit +3.05%, WR 0.737.

Loop commands:
1. **Generate specs.** Either (a) brainstorm first-principles specs YOURSELF (grammatically valid JSON per the grammar — the pack prints it), or (b) `python -m scripts.oracle_brainstorm_pack --reversion --explore` for the copy-paste prompt. Grammar = `{"col":<c>,"op":<crossed_above|crossed_below|ge|gt|le|lt>,"value":<n>|"value_col":<c>}` and `{"episode_event":{direction,tier,complex_scope,within_sessions,min_count}}`, combined with `all`/`any`. Columns: read them + their SCALES/COVERAGE from the `--reversion` pack (stochrsi 0-100; breadth/cohesion/turnover_z/cohesion_rebuild are 2021+-ONLY so avoid as the primary trigger; hy_oas_chg_10d/yc_slope/oil_ret_10d/dollar_chg_10d/fin_conditions are full-history cross-asset regime cols).
2. **Ingest** (dedup vs registry + validate + flag scale/coverage): save specs as `<dir>/batch.json`, then `python -m scripts.oracle_ingest_brainstorm --inbox <dir> --out /tmp/ing`. (Sanitize first: strip BOM + U+2028; if RTF, `textutil -convert txt`. Operator's Codex saves land in `/Users/chriswong/.codex/worktrees/*/Macro Dashboard/research/oracle_inbox/`.)
3. **Reversion-screen** (gate legs 1-4): `python -m scripts.oracle_reversion_screen --all-pending --compounds-dir /tmp/ing/compounds --data-dir "<MAIN>/data" --dry-run`. Legs 1-4: n>=100, WR>=0.62, asym>=1.5, ret_exit>=1% AND >0 in BOTH regimes.
4. **Gauntlet** the legs-1-4 passers (adds OOS + placebo, legs 5-6): `python -m scripts.oracle_reversion_screen --gauntlet --exit-mode time --compound <ID> --compounds-dir /tmp/ing/compounds --data-dir "<MAIN>/data"`. `--exit-mode time` (21d) is the FROZEN primary (≈ operator hold). `--exit-mode stochrsi2d` is a v2 sensitivity — it exits on the FIRST 2D-StochRSI cross (~12d hold), which is TOO EARLY vs the operator's ~20-30d and clips WR by ~0.10 on everything; report it but the frozen verdict is the time-exit.
5. A FULL 6-leg PASS = a new validated candidate → append to `research/ORACLE_REVERSION_VALIDATED.md` and grow the base.

## VALIDATED BASE SO FAR (full 6-leg reversion-gauntlet PASS, time-exit)
- **A15_WASHOUT_OPP_OUT_2NODE** — washout + ≥2 opposite-complex outflow. asym 1.83, WR 0.74, ret +3.05%, OOS holdout +4.60%/78%.
- **B4_WASHOUT_DOLLAR_RELIEF** — `washout_w>0 AND dollar_chg_10d crossed_below 0 AND rs>-0.04`. asym 1.55, WR 0.68, ret +2.07%, n=641, OOS holdout +3.57%/73%.
- **B4_EP_SAME_OUT_CREDIT_EASE** — `same-complex out/onset within20 AND hy_oas_chg_10d crossed_below 0 AND stochrsi_w_k<60`. asym 1.56, WR 0.72, ret +2.12%, n=392, OOS holdout +2.28%/72%.
(All display-only, need a transaction-cost haircut before any live weight — short-horizon signals are cost-sensitive.)

## WHAT WORKS (steer the brainstorm here; DIVERSIFY beyond it)
Dominant winning shape = **capitulation/washout + a macro-relief timer** (credit spread peaking `hy_oas_chg_10d crossed_below 0`; dollar relief; oil relief; rate relief) and **oscillator turns from oversold** (`stochrsi_w_k crossed_above 20`, K>D cross) in a mid-VIX band. Defensive-in-risk-off is the genuine cross-sectional pocket. UNDER-EXPLORED first-principles families to diversify into: multi-timeframe oscillator confluence (StochRSI turn + vel_1w turn = the operator's own engine); V-bottom (sharp `ret` down then `accel` crossing up); volatility-compression → expansion; rate-sensitive-sector bottoms (`tlt_ret_10d`>0 + washout); yield-curve/credit regime gates on oscillator turns.

## LOOP DISCIPLINE
- **The current validated base + near-misses live in `research/ORACLE_REVERSION_VALIDATED.md` (source of truth — read it each round).** As of 2026-07-05 it is 6 published rows ≈ 4 independent mechanisms (episode-routing · dollar-relief · credit-relief · V-bottom).
- Each round: pick 2-3 signal FAMILIES (rotate so the union diversifies — don't re-mill washout+credit+dollar-relief every round; those are mapped — steer toward orthogonal: yield-curve, credit-non-dollar, oil-relief, V-bottom-depth), have a Sonnet subagent GENERATE ~30-50 grammatically-valid first-principles specs + ingest + reversion-screen + gauntlet the passers, and REPORT the full-pass validated ones. You adjudicate, append passes, choose next round's families.
- **MANDATORY REDUNDANCY AUDIT before publishing any pass: gauntlet-PASS ≠ additive.** Compute the pass's entry-set overlap vs every published base signal using `get_entry_dates` (the gauntlet's own entry definition). If ≥85% of its entries are contained in a single existing signal it is a REDUNDANT subset — do NOT publish (it inflates apparent breadth). Publish only if a meaningful fraction (~≥15%) of entries are novel; flag correlated members with their overlap %. Two real examples already caught this way: `E_DOLLAR_EASE_TLT_POS_WASHOUT` (100% subset of B4_WASHOUT_DOLLAR_RELIEF) and `R3_B6_ACCELZ_NEG2_K30_VIX40` (100% subset of R16) — both gauntlet-PASS, both correctly NOT published.
- **Publish = append to `data/oracle/compounds/registry.jsonl`** (durable compound store) with a `reversion` block (gauntlet=PASS + regime + OOS + placebo, re-verified on a fresh panel — never stamp a number you haven't just re-observed) + full schema (mechanism_en/zh, entry_rule, family, universe, status `screened`, lineage). Then update `ORACLE_REVERSION_VALIDATED.md`. Match the file's `ensure_ascii=True` compact JSON style. Status stays `screened` (display-only); the 63d `promotion_scan` is the WRONG ruler for reversion signals — a reversion promotion track is a separate build (do NOT route these through the 63d queue).
- The ingest hard-dedups exact rules, so re-proposals are cheap/safe. Log honestly.
- Pre-registration is sacred: the gate thresholds are FROZEN — do not tune them to pass a candidate. **PENDING human/Fable ruling:** the bear-tape family (`spy_above_200d==0 ∧ …`) is risk-off-only by construction and cannot pass Leg-4's dual-regime test; whether to admit structurally-single-regime signals (e.g. via the Leg-6 placebo as within-regime control) is an escalation-enabling gate amendment = a human call, NOT an LLM's. Keep the family blocked until ruled.
- Model routing (CLAUDE.md): Sonnet = generate/screen/gauntlet; Haiku = trivial extraction; orchestrator (you) = design families + adjudicate + merge. Never let subagents inherit a frontier model.

## GIT / OPS
Branch off FRESH `origin/main`; finish via commit→push→PR→same-day squash-merge; work only in a worktree, never touch the main checkout's git state; never reuse a squash-merged branch. Validated-base + doc updates are commits; the screening scratch (`/tmp/*`) is not. "Workers Builds: macro" red CI X is known-spurious. End commits with the Co-Authored-By trailer.

## MEMORY (account-local — the other account won't have these; the facts above are the summary)
Key memories: `oracle-reversion-metric-reframe`, `backtest-horizon-swing-2-4-weeks` (STANDING: ~2-4wk bounce + drawdown, not 3-6mo), `oracle-panel-column-coverage`, `oos-fail-regime-change-vs-overfit`, `user-trades-conviction-low-n`, `model-tier-routing`.
