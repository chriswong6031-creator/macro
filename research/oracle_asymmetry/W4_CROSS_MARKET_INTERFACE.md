# OTA W4.c — Cross-Market Replication Interface (registered)

**Authored by Fable 2026-07-06 (masterplan §W4.5).** This registers WHAT a CN/HK replication of a US-validated Oracle reversion signal must produce to count as out-of-universe evidence. EXECUTION is deferred to the domain-owner programs (china-alpha, hk-canada) — this doc is the contract, so a future replication cannot move its own goalposts.

## Why replication, and why it can lie
Same mechanism tested on a structurally different tape is the strongest cheap robustness test AND an n-multiplier for slow-accruing families. But "agreement" can be a correlated echo: if the CN/HK events co-move with the US events (global risk episodes), a replicated pass adds far less than independent evidence. The interface therefore requires the correlation disclosure with every claim.

## The interface (all six required for a replication to count)
1. **Same grammar, market-local panel.** The compound's `entry_rule` runs UNCHANGED through `engine/oracle/compounds.py` against a market-local panel built with the same column definitions (local index benchmark replaces SPY for rs; local cross-asset columns substituted only via a logged mapping table). Any rule edit = a different compound = its own registration.
2. **The reversion ruler, frozen constants.** Grading per `ORACLE_REVERSION_GATE_PREREG.md` (window 25, exit 21 sessions, ABSOLUTE local-currency returns, WR/asym/ret_exit, regime split via local risk proxy declared ex-ante). Gate thresholds identical; no market-local tuning.
3. **Coverage + era honesty.** Column coverage table by year for the local panel printed first (the 2021+-column lesson); local OOS split date declared ex-ante and justified by local data depth, not by results.
4. **Correlated-echo disclosure (mandatory).** For the compound's entry sets: cross-market correlation of monthly entry counts AND the share of local entries within ±10 sessions of any US entry on the same mechanism. Every agreement claim prints both numbers next to it; a replication with >60% within-±10-session overlap is labeled ECHO, not independent replication.
5. **Costs.** Local transaction-cost haircut table (CN/HK costs differ materially from US ETFs); cost-robustness at the local haircut is part of the pass.
6. **Counting.** Each market's run is its own counted trial in that program's ledger; results append to a shared `research/oracle_asymmetry/CROSS_MARKET_LEDGER.md` (created by the first replication) — agreement/divergence/echo per compound per market. Divergence is regime information, reported not hidden.

## Status
- 2026-07-06 — Interface registered. No replication executed. Pointers filed to [[china-alpha-program]] / [[hk-canada-stocks-program]] dockets.
