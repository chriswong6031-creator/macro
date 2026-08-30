# Data → UI field mapping — Live Entry Radar W8

W8 fixtures are synthetic. W9 must replace fixture fields with live evaluator fields **only where the W4 contract exists**. Slots marked WAIT stay honest placeholders.

| UI slot | Fixture field | Glance / drawer | W9 source | Gate |
|---|---|---|---|---|
| Ticker | `ticker` | glance | episode.ticker | CAN COPY NOW |
| Name EN/ZH | `name_en` / `name_zh` | glance | security master | CAN COPY NOW (copy) / WAIT FOR W4 (live names) |
| Price | `price` | glance | session quote | WAIT FOR W4 |
| Change | `change` | glance | session quote | WAIT FOR W4 |
| Expert identity | `expert` + `expert_id` | glance | `detector_id` G0/C1/C2/C3/C5 | CAN COPY NOW (ids) / WAIT FOR W4 (live fires) |
| C2 variant | `c2_variant` | glance + drawer | C2 variant key | CAN COPY NOW (six keys) / WAIT FOR W4 |
| C4 context | `c4` | glance chip + drawer | C4 stratification features | CAN COPY NOW (treatment) / WAIT FOR W4 |
| Lifecycle | `lifecycle` | glance + ladder | episode.state user projection | CAN COPY NOW (words) / WAIT FOR W4 (transitions) |
| Bar state | `bar_state` | glance freshness | provisional vs confirmed | CAN COPY NOW (visual) / WAIT FOR W4 |
| Why probe | `why_probe_*` | drawer | `universe_admission` + lobe nominations | CAN COPY NOW (copy pattern) / WAIT FOR W4 |
| Why armed | `why_armed_*` | drawer | first_armed_at + detector evidence | WAIT FOR W4 |
| Why candidate | `why_candidate_*` | glance + drawer | candidate_at + fire evidence | WAIT FOR W4 |
| Invalidation | `invalidation_*` | drawer | risk_geometry / engine law | CAN COPY NOW (slot) / WAIT FOR W4 |
| Expiry | `expiry_*` | drawer | episode expiry law | CAN COPY NOW (slot) / WAIT FOR W4 |
| `known_at` | `known_at` | drawer | `signal_known_ts` / reading known_at | WAIT FOR W4 |
| as-of | `asof` | footer | reading as-of | WAIT FOR W4 |
| Freshness | `freshness.*` | footer + banner | age + kind | CAN COPY NOW (grammar) / WAIT FOR W4 (clock) |
| Stale | `stale` | card demotion | freshness.kind=stale | CAN COPY NOW / WAIT FOR W4 |
| Unavailable | `unavailable` | null treatment | condition_met is None | CAN COPY NOW / WAIT FOR W4 |
| Raw-basis | `raw_basis` | unavailable | basis mismatch | CAN COPY NOW / WAIT FOR W4 |
| Degraded | `degraded` | banner + demotion | evaluator liveness | WAIT FOR W4 |
| False starts | `false_starts[]` | glance count + drawer | ledger history | CAN COPY NOW (must not drop) / WAIT FOR W5 (real ledger) |
| Sibling lanes | `siblings[]` | glance count + drawer | other episodes on ticker | CAN COPY NOW / WAIT FOR W4 |
| Event id | `event_id` | drawer (C5) | `mastermind.entry_event.v1` | WAIT FOR W4 |
| Spark | `spark[]` | hero | mini path | CAN COPY NOW (null law) / WAIT FOR W4 (real path) |
| Featured | computed `inLane(best)` | aura | Best-lane live candidate (same set) | CAN COPY NOW (rule) |
| Research Priority | `research_priority` | board-level ACCRUING + card em-dash | W6 object | **WAIT FOR W6** |
| Glance component states | — | reserved UNAVAILABLE | 1D Stoch / MACD-RSI / Structure / Lobe | **BLOCKED_DATA until W4** |
| Glance zone + invalidation | — | reserved ACCRUING | risk geometry on the footer | **BLOCKED_DATA until W4** |
| Opportunity | `opportunity` | drawer NOT YET MEASURED | W7 object | **WAIT FOR W7** |

## Forbidden mappings

- Do not map any Radar episode onto a Prophet plan row or seven-cell lifecycle.
- Do not map C4 onto a firing `detector_id` or a Best-lane card.
- Do not map missing Priority/Opportunity onto a guessed number.
- Do not map ticker onto a `#ticker` hash. Cards are not links until a real `stock.html` exists (PRC-301 is not closed).
- Do not treat the W8 reduced card as contract §14 complete.
- Do not map unavailable/stale onto `condition_met=false`.
