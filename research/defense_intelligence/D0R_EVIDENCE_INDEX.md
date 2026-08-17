# D0R Evidence Index

**Wave:** D0R (in progress, not complete)  
**Date:** 2026-08-17 continuation  
**Branch:** `claude/defense-procurement-d0r-cont-20260816`  
**Canonical architecture:** `research/DEFENSE_PROCUREMENT_INTELLIGENCE_OS_V3_FINANCIAL_ALPHA_SUPERINTELLIGENCE_MASTERPLAN_2026-08-16.md`  
**Canonical handoff:** `research/DEFENSE_PROCUREMENT_D0R_FINANCIAL_ALPHA_RECONNAISSANCE_HANDOFF_2026-08-16.md`

Kickoff (#5812) is not acceptance. This continuation adds entitled production-browser proof and architecture B–H.

## Continuation packets

| Packet | Path |
|---|---|
| Browser acceptance (unentitled + entitled) | `research/defense_intelligence/D0R_ENTITLED_BROWSER_ACCEPTANCE.md` |
| Golden award-change lineage | `research/defense_intelligence/D0R_GOLDEN_AWARD_CHANGE_LINEAGE.md` |
| Capability/authority ledger | `research/defense_intelligence/D0R_CAPABILITY_AUTHORITY_LEDGER.md` |
| Benchmark / workflow matrix | `research/defense_intelligence/D0R_BENCHMARK_AND_WORKFLOW_MATRIX.md` |
| Archetype router / drivers | `research/defense_intelligence/D0R_DEFENSE_EQUITY_DRIVER_TAXONOMY.md` |
| Historical casebook | `research/defense_intelligence/D0R_HISTORICAL_EVENT_CASEBOOK.md` |
| Source / rights / PIT | `research/defense_intelligence/D0R_SOURCE_RIGHTS_AND_PIT_REGISTRY.md` |
| Graph / contract freeze | `research/defense_intelligence/D0R_GRAPH_AND_CONTRACT_FREEZE.md` |
| Golden universe | `research/defense_intelligence/D0R_GOLDEN_UNIVERSE_AND_ARCHETYPE_ROSTER.md` |
| Experience architecture | `research/defense_intelligence/D0R_EXPERIENCE_ARCHITECTURE.md` |
| Discoveries / blockers | `research/defense_intelligence/D0R_DISCOVERY_AND_BLOCKERS.md` |
| Remaining work | `research/defense_intelligence/D0R_REMAINING_WORK.md` |
| Screenshots | `evidence/d0r-unentitled-*.png`, `evidence/d0r-entitled-*.png` |

## Repository ancestry

| Claim | Command | Result |
|---|---|---|
| V3/D0R architecture merged | `gh pr view 5803 --json state,mergedAt,mergeCommit` | MERGED 2026-08-16T19:05:39Z; merge `455284b7beaefee4743c8e925d8000361f0d4cb8` |
| D0R kickoff merged | `gh pr view 5812` | MERGED; squash `4ba12adcabf4` |
| Continuation worktree HEAD | `git rev-parse HEAD` in `.claude/worktrees/defense-procurement-d0r-cont` | `e7cdfa257322` at capture |
| Open GovRev graph PR | `gh pr view 5424 --json state` | still open (`defense20-v1`). Do not fold in. |

## Production / live (re-recorded 2026-08-17T04:45Z entitled)

| Claim | Command | Result |
|---|---|---|
| VPS checkout | `curl https://www.mastermind-x.com/api/health` | `{"status":"ok","commit":"a0b2aba13b5","checkout":"8b5cd60f706"}` |
| Underscore page | GET `government_revenue.html` | HTTP 200, 256555 bytes, title Government Revenue Foresight |
| Hyphenated twin | GET `government-revenue.html` | HTTP 404 (not re-litigated; still 404) |
| Anonymous latest.json | GET `government-revenue-data/latest.json` from the page | HTTP 401 locked `authentication_required` |
| Paid API | GET `/api/government-revenue/latest` from the page | HTTP 401 `missing bearer token` |
| Compact workspace | `#gov-data` | schema v1; workspace v2 bundle `grw2-dd9d7af893a7f3c773909351`; 2 events; `total` 500; `next_cursor` `djI6Mg`; `as_of` 2026-08-13 |
| Unentitled UI | Cursor browser + Chrome headless | membership banner; Changes 2; Award tape 2; Candidate Radar 0; Opportunities 0; Recompete 0; Budget 0; Companies 21 |

## Lineage (HC101319C0006 P00032)

| Claim | Command / source | Result |
|---|---|---|
| Official action | POST `https://api.usaspending.gov/api/v2/transactions/` award 306425727 | `CONT_TX_9700_-NONE-_HC101319C0006_P00032_-NONE-_0`; action_type C FUNDING ONLY ACTION; obligation 18416666.66; action_date 2026-05-12 |
| Receipt | `collection_receipts.jsonl` line with IRDM actions 2026-08-12 | `usaspending:usaspending-3be22546a4a9a6b9a46a7469:actions:1d52f66cfa31a196:2a07ba19681a3c9d`; record_count 33 (was 32) |
| Action version | `award_action_versions.parquet` | event_eligible true; known_at=first_seen_at 2026-08-12T23:50:04.442107Z; `is_late_discovery` true on workspace event |
| Graph | `recipient_entity_graph.json` | defense19-v1; UEI S77SW52LCR57 → Iridium Government Services LLC → wholly_owned Iridium Communications Inc. → IRDM |
| Browser | compact Changes row | same PIID, IRDM, obligation diff, official source link |

## HEAD artifacts (git, sparse-safe)

Unchanged clocks from kickoff for candidate status / latest.json (`generated_at` 2026-08-13T09:24:42Z, graph defense19-v1). Budget graph files remain **absent** from `data/government_revenue/` and `site/government-revenue-data/`.

## Explicitly unverified

- VPS data-dir vs git HEAD after 2026-08-14 collection receipts.
- Live Prophet annotation / Neural Web packet for this event.
- Whether a hard reload would clear the Radar lock on the same session.
- Workstream I (exact D1–D4 implementation handoffs).

## Next evidence to collect

1. Operator review of A–H. D1 only if ordered (Radar rehydrate is the first product defect).
2. Do not start D1 from this packet alone.
