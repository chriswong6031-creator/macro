# Signal Bus — Artifact Registry

The **signal bus** is the set of cross-engine data artifacts that flow between producers and consumers inside the Macro Dashboard engine. Each artifact is the single authoritative output of one producer (a script or engine module); every downstream reader — whether another engine module, a site-build script, or an external system — is listed explicitly. The registry lives in `config/synapse.yml` and is the single source of truth: it records each artifact's path, format, freshness SLA, storage backend, tier on the qualification ladder, and full consumer list derived from the W0 census (workflow wf_67ace3c1 + wf_dd79661a red-team, 2026-07-04). In W0 the registry is **passive** — it names what exists; read-gating and envelope stamping follow in W1 and W2.

> generated from `config/synapse.yml` — do not edit by hand; regenerate with `python -m scripts.gen_signal_bus_doc`

## Summary

### Artifacts by owner_program

| owner_program | count |
|---|---|
| active-build-map | 1 |
| btc-vector | 5 |
| causal-hypothesis-factory | 9 |
| china-alpha | 14 |
| china-intel-hub | 2 |
| china-pick-lab | 3 |
| china-system | 2 |
| codex-b5 | 1 |
| codex-docket-b6 | 3 |
| cycle-intelligence | 14 |
| dannytrades | 1 |
| engine-fix | 16 |
| entry-stack-expansion | 2 |
| factor-intelligence | 5 |
| fast-turn | 4 |
| flow-leaders-desk | 2 |
| hk-canada | 2 |
| hk-pick-lab | 3 |
| ignition-radar | 2 |
| institutional-sector-intelligence | 2 |
| intl-fix | 1 |
| intraday-flow-tracker | 3 |
| leader-radar | 2 |
| long-hold | 28 |
| macro-context-rail | 15 |
| macro-release-intel | 6 |
| mastermind-feedback-contract | 2 |
| metabolism-phase-a | 5 |
| metabolism-phase-v2a | 4 |
| metabolism-phase-v2b | 2 |
| metabolism-phase-v2c | 4 |
| metabolism-phase-v2d | 4 |
| metabolism-phase0 | 2 |
| momoedge | 8 |
| narrative-ignition | 5 |
| nasdaq-internals | 1 |
| neural-web | 51 |
| next3 | 3 |
| nw-context-intelligence | 3 |
| nw-mastermind-bridge | 5 |
| nw-rails | 7 |
| options-alpha | 7 |
| options-nw-entry-intelligence | 3 |
| oracle | 29 |
| pick-lab | 3 |
| policy-shock | 5 |
| qualitative-intelligence | 23 |
| research-factory | 3 |
| sector-pulse | 3 |
| setup-species | 6 |
| short-side | 1 |
| signal-commons | 8 |
| signal-foundry | 4 |
| stock-personality | 5 |
| tech-internals | 1 |
| thematic-intelligence | 12 |
| til-w10-clinical | 2 |
| til-w11-options-witness | 2 |
| til-w7-hiring-intent | 3 |
| til-w8-trade-flows | 2 |
| til-w9-discovery-v2 | 3 |
| turn-sensitivity | 1 |
| us-stocks-prebreakout | 2 |

### Artifacts by tier

| tier | count |
|---|---|
| display | 226 |
| infrastructure | 89 |
| scored | 4 |
| shadow | 63 |

### Artifacts by storage

| storage | count |
|---|---|
| git | 366 |
| gitignored-local | 10 |
| r2 | 6 |

## Artifacts by owner_program

### active-build-map

| id | path | format | cadence | tier | consumers | external consumers |
|---|---|---|---|---|---|---|
| active-builds | `data/governance/active_builds.json` | json | daily-engine | infrastructure | 0 | 0 |

### btc-vector

| id | path | format | cadence | tier | consumers | external consumers |
|---|---|---|---|---|---|---|
| vector-calibration | `data/vector/calibration.json` | json | on-demand | scored | 6 | 0 |
| regime-spvector-latest | `data/regime/spvector_latest.json` | json | daily-engine | display | 4 | 0 |
| btc-override-ledger | `data/vector/override_ledger.jsonl` | jsonl | daily-engine | shadow | 2 | 0 |
| btc-regime-ledger | `data/vector/regime_ledger.jsonl` | jsonl | daily-engine | shadow | 2 | 0 |
| btc-impulse-ledger | `data/vector/impulse_ledger.jsonl` | jsonl | daily-engine | shadow | 1 | 0 |

### causal-hypothesis-factory

| id | path | format | cadence | tier | consumers | external consumers |
|---|---|---|---|---|---|---|
| causal-confluence-audit | `data/neuralweb/causal_confluence_audit.json` | json | daily-engine | shadow | 2 | 0 |
| causal-nulls | `data/neuralweb/causal_nulls.jsonl` | jsonl | weekly | display | 2 | 0 |
| causal-edges | `data/neuralweb/causal_edges.jsonl` | jsonl | weekly | display | 1 | 0 |
| causal-frontier | `data/neuralweb/causal_frontier.json` | json | daily-engine | display | 1 | 0 |
| causal-llm-lane | `data/neuralweb/causal_llm_lane.json` | json | weekly | infrastructure | 1 | 0 |
| causal-brainstorm-runs | `data/neuralweb/causal_brainstorm_runs.jsonl` | jsonl | weekly | infrastructure | 0 | 0 |
| causal-lab-state | `data/neuralweb/causal_lab_state.json` | json | daily-engine | display | 0 | 0 |
| causal-surprise-queue | `data/neuralweb/causal_surprise_queue.jsonl` | jsonl | daily-engine | display | 0 | 0 |
| site-causal-lab-state | `site/neuralwebdata/causal_lab_state.json` | json | daily-engine | display | 0 | 0 |

### china-alpha

| id | path | format | cadence | tier | consumers | external consumers |
|---|---|---|---|---|---|---|
| china-sector-cycles-forward-log | `data/china_sector_cycles/forward_log.parquet` | parquet | asia-close | shadow | 6 | 0 |
| site-china-standouts | `site/factordata/china_standouts.json` | json | asia-close | display | 3 | 1 |
| name-score-calls | `data/name_score/us_calls.parquet` | parquet | daily-engine | shadow | 3 | 0 |
| china-basket-turn-cn | `site/chinabasketdata/basket_turn_cn.json` | json | daily-engine | display | 2 | 0 |
| china-board-ledger | `data/china_standout_track/board.parquet` | parquet | asia-close | shadow | 2 | 0 |
| site-china-altdata-mastermind | `site/chinaaltdata/mastermind.json` | json | asia-close | display | 2 | 0 |
| site-china-intel-briefing | `site/china_intel/briefing.json` | json | asia-close | display | 1 | 1 |
| china-mtf-upturn | `site/chinastockdata/mtf_upturn_cn.json` | json | daily-engine | display | 1 | 0 |
| china-radar-ledger | `data/china_radar/ledger.parquet` | parquet | asia-close | shadow | 1 | 0 |
| cn-reversal-sleeve-ledger | `data/cn_reversal_sleeve_track/sleeve.parquet` | parquet | asia-close | shadow | 1 | 0 |
| site-china-altdata-by-ticker | `site/chinaaltdata/by_ticker.json` | json | asia-close | display | 1 | 0 |
| china-basket-turn-ledger | `data/china_basket_turn/ledger.jsonl` | jsonl | daily-engine | display | 0 | 0 |
| china-mtf-upturn-ledger | `data/mtf_upturn_cn/ledger.jsonl` | jsonl | daily-engine | display | 0 | 0 |
| site-china-altdata-feed | `site/chinaaltdata/feed.json` | json | asia-close | display | 0 | 0 |

### china-intel-hub

| id | path | format | cadence | tier | consumers | external consumers |
|---|---|---|---|---|---|---|
| site-china-special-sits | `site/chinaspecialdata/special.json` | json | asia-close | display | 2 | 0 |
| site-china-intel-command | `site/china_intel/command.json` | json | asia-close | display | 1 | 0 |

### china-pick-lab

| id | path | format | cadence | tier | consumers | external consumers |
|---|---|---|---|---|---|---|
| cn-reversion-desk-artifact | `site/factordata/china_reversion_desk.json` | json | asia-close | display | 2 | 0 |
| cn-pick-lab-entry-ledger | `site/labdata/china_pick_lab.json` | json | asia-close | display | 1 | 0 |
| cn-pick-lab-snapshots | `data/china_pick_lab/snapshots/` | parquet | asia-close | infrastructure | 1 | 0 |

### china-system

| id | path | format | cadence | tier | consumers | external consumers |
|---|---|---|---|---|---|---|
| site-china-market-state | `site/chinastatedata/market_state.json` | json | asia-close | display | 4 | 1 |
| site-china-cycle-phase | `site/chinastatedata/cycle_phase.json` | json | asia-close | display | 1 | 1 |

### codex-b5

| id | path | format | cadence | tier | consumers | external consumers |
|---|---|---|---|---|---|---|
| event-windows | `embedded: event_windows block inside site/stockdata/<TICKER>.json` | json | daily-engine | display | 1 | 0 |

### codex-docket-b6

| id | path | format | cadence | tier | consumers | external consumers |
|---|---|---|---|---|---|---|
| watchlist-alerts-jsonl | `data/alerts/watchlist_alerts.jsonl` | jsonl | daily-engine | infrastructure | 2 | 0 |
| watchlist-sentinel-cooldown | `data/alerts/watchlist_sentinel_cooldown.json` | json | daily-engine | infrastructure | 1 | 0 |
| watchlist-sentinel-states | `data/alerts/watchlist_sentinel_states.json` | json | daily-engine | infrastructure | 1 | 0 |

### cycle-intelligence

| id | path | format | cadence | tier | consumers | external consumers |
|---|---|---|---|---|---|---|
| cycle-ontology-falsifiers | `data/cycle_ontology/falsifiers.json` | json | on-demand | infrastructure | 6 | 0 |
| country-cycles-forward-log | `data/country_cycles/forward_log.parquet` | parquet | daily-engine | shadow | 5 | 0 |
| sector-cycles-forward-log | `data/sector_cycles/forward_log.parquet` | parquet | daily-engine | shadow | 5 | 0 |
| hazard-model | `data/hazard/model_price_c4414dcb.json` | json | on-demand | scored | 4 | 0 |
| cycle-pattern-truths | `data/cycle_pattern/truths.jsonl` | jsonl | on-demand | display | 2 | 0 |
| fed-net-liquidity | `data/macro/fed_net_liquidity.parquet` | parquet | daily-engine | infrastructure | 2 | 0 |
| cycle-pattern-entities | `data/cycle_pattern/entities.parquet` | parquet | on-demand | infrastructure | 1 | 0 |
| cycle-pattern-state | `data/neuralweb/cycle_pattern_state.json` | json | daily-engine | display | 1 | 0 |
| cycle-pattern-state-monthly | `data/cycle_pattern/state_monthly.parquet` | parquet | on-demand | infrastructure | 1 | 0 |
| regime-v2-pit | `data/regime/regime_v2_pit.parquet` | parquet | on-demand | infrastructure | 1 | 0 |
| cycle-pattern-outcomes | `data/cycle_pattern/outcomes.parquet` | parquet | on-demand | infrastructure | 0 | 0 |
| cycle-pattern-state-daily-live | `data/cycle_pattern/state_daily_live.parquet` | parquet | daily-engine | infrastructure | 0 | 0 |
| hazard-panel-index-v0 | `data/hazard/panel_index_v0.parquet` | parquet | on-demand | infrastructure | 0 | 0 |
| signal-archive-context-daily | `data/signal_archive/context_daily.parquet` | parquet | daily-engine | infrastructure | 0 | 0 |

### dannytrades

| id | path | format | cadence | tier | consumers | external consumers |
|---|---|---|---|---|---|---|
| dt-contra-state | `data/neuralweb/dt_contra_state.json` | json | daily-engine | display | 1 | 0 |

### engine-fix

| id | path | format | cadence | tier | consumers | external consumers |
|---|---|---|---|---|---|---|
| regime-latest | `data/regime/latest.json` | json | daily-engine | infrastructure | 35 | 3 |
| regime-history | `data/regime/regime_history.parquet` | parquet | daily-engine | infrastructure | 19 | 0 |
| breadth-breadth | `data/breadth/breadth.parquet` | parquet | collect | infrastructure | 18 | 0 |
| breadth-sp1500-pit | `data/breadth/sp1500_pit_membership.parquet` | parquet | on-demand | infrastructure | 11 | 0 |
| market-state-latest | `data/market_state/latest.json` | json | daily-engine | display | 8 | 0 |
| trial-ledger | `data/trial_ledger.jsonl` | jsonl | on-demand | infrastructure | 6 | 0 |
| risk-radar-forward-log | `data/risk_radar/forward_log.jsonl` | jsonl | daily-engine | display | 5 | 0 |
| regime-vector | `data/regime/regime_vector.parquet` | parquet | daily-engine | infrastructure | 4 | 0 |
| site-regime-timeline | `site/regime_timeline.json` | json | daily-engine | display | 2 | 2 |
| archetypes-history | `data/archetypes/history.parquet` | parquet | on-demand | display | 3 | 0 |
| market-state-forward-log | `data/market_state/forward_log.jsonl` | jsonl | daily-engine | display | 3 | 0 |
| regime-base-effect-fwd | `data/regime/base_effect_fwd.jsonl` | jsonl | daily-engine | display | 3 | 0 |
| site-factors | `site/factordata/factors.json` | json | daily-engine | display | 3 | 0 |
| site-allocation | `site/allocationdata/allocation.json` | json | daily-engine | display | 1 | 1 |
| site-regime-prior-js | `site/regimedata/regime_prior.js` | js | daily-engine | display | 2 | 0 |
| site-macro-signals | `site/macrodata/macro_signals.json` | json | daily-engine | display | 0 | 1 |

### entry-stack-expansion

| id | path | format | cadence | tier | consumers | external consumers |
|---|---|---|---|---|---|---|
| bottom-sensors-json | `site/neuralwebdata/bottom_sensors.json` | json | daily-engine | display | 1 | 1 |
| bottom-sensors-parquet | `data/neuralweb/bottom_sensors.parquet` | parquet | daily-engine | display | 1 | 0 |

### factor-intelligence

| id | path | format | cadence | tier | consumers | external consumers |
|---|---|---|---|---|---|---|
| factor-intelligence-state | `data/neuralweb/factor_intelligence_state.json` | json | nightly-factor-panel | display | 5 | 0 |
| factor-contradictions-ledger | `data/neuralweb/factor_contradictions.jsonl` | jsonl | nightly-factor-panel | display | 2 | 0 |
| fire-coordinates | `data/factordata/fire_coordinates.jsonl` | jsonl | nightly-factor-panel | display | 2 | 0 |
| factor-state-history | `data/factordata/factor_state_history.jsonl` | jsonl | nightly-factor-panel | display | 0 | 0 |
| site-factor-intelligence-state | `site/neuralwebdata/factor_intelligence_state.json` | json | nightly-factor-panel | display | 0 | 0 |

### fast-turn

| id | path | format | cadence | tier | consumers | external consumers |
|---|---|---|---|---|---|---|
| site-basket-turn-watch | `site/basketdata/turn_watch.json` | json | daily-engine | display | 1 | 0 |
| basket-turn-cohort-claims-log | `data/basket_turn/cohort_claims_log.jsonl` | jsonl | daily-engine | display | 0 | 0 |
| basket-turn-cohort-grades | `data/basket_turn/cohort_grades.jsonl` | jsonl | daily-engine | display | 0 | 0 |
| tape-disagreement-ledger | `data/basket_turn/disagreement_ledger.jsonl` | jsonl | daily-engine | display | 0 | 0 |

### flow-leaders-desk

| id | path | format | cadence | tier | consumers | external consumers |
|---|---|---|---|---|---|---|
| site-flow-leaders | `site/flowleaders/leaders.json` | json | daily-engine | display | 2 | 0 |
| site-flow-leaders-page | `site/flow_leaders.html` | other | daily-engine | display | 0 | 0 |

### hk-canada

| id | path | format | cadence | tier | consumers | external consumers |
|---|---|---|---|---|---|---|
| board-ledger-ca | `data/board_ledger/ca_board.parquet` | parquet | daily-engine | shadow | 1 | 0 |
| board-ledger-hk | `data/board_ledger/hk_board.parquet` | parquet | daily-engine | shadow | 1 | 0 |

### hk-pick-lab

| id | path | format | cadence | tier | consumers | external consumers |
|---|---|---|---|---|---|---|
| hk-1d-velocity-desk-artifact | `site/factordata/hk_1d_velocity_desk.json` | json | asia-close | display | 2 | 0 |
| hk-pick-lab-entry-ledger | `site/labdata/hk_pick_lab.json` | json | asia-close | display | 1 | 0 |
| hk-pick-lab-snapshots | `data/hk_pick_lab/snapshots/` | parquet | asia-close | infrastructure | 1 | 0 |

### ignition-radar

| id | path | format | cadence | tier | consumers | external consumers |
|---|---|---|---|---|---|---|
| ignition-radar-latest | `data/ignition_radar/latest.json` | json | daily-engine | display | 4 | 0 |
| ignition-log-us | `data/ignition_log/us_ignition.jsonl` | jsonl | daily-engine | display | 2 | 0 |

### institutional-sector-intelligence

| id | path | format | cadence | tier | consumers | external consumers |
|---|---|---|---|---|---|---|
| china-sector-central-calls | `data/china_sector_central/calls.parquet` | parquet | asia-close | display | 2 | 0 |
| sector-central-calls | `data/sector_central/calls.parquet` | parquet | daily-engine | display | 2 | 0 |

### intl-fix

| id | path | format | cadence | tier | consumers | external consumers |
|---|---|---|---|---|---|---|
| intl-bridge-ledger | `data/intl_bridge/ledger.json` | json | on-demand | shadow | 6 | 0 |

### intraday-flow-tracker

| id | path | format | cadence | tier | consumers | external consumers |
|---|---|---|---|---|---|---|
| intraday-flow-base | `site/flowtracker/base.json` | json | daily-engine | display | 1 | 0 |
| intraday-flow-pulse | `site/live/flow_pulse.json` | json | intraday | display | 1 | 0 |
| intraday-flow-ledger | `data/intraday_flow/ledger.parquet` | parquet | daily-engine | display | 0 | 0 |

### leader-radar

| id | path | format | cadence | tier | consumers | external consumers |
|---|---|---|---|---|---|---|
| leader-radar-state-history | `data/leader_radar/state_history.parquet` | parquet | daily-engine | infrastructure | 1 | 0 |
| site-leader-radar | `site/leaderradar/radar.json` | json | daily-engine | display | 1 | 0 |

### long-hold

| id | path | format | cadence | tier | consumers | external consumers |
|---|---|---|---|---|---|---|
| breakaway-watch-states | `data/research/breakaway_watch.parquet` | parquet | daily-engine | display | 1 | 0 |
| capital-allocation-delta | `embedded: capital_allocation block inside site/stockdata/<TICKER>.json` | json | daily-engine | display | 1 | 0 |
| expect-drift-ruler-p-results | `data/research/expect_drift_ruler_p_results.parquet` | parquet | on-demand | display | 1 | 0 |
| great-company-trap | `embedded: great_company_trap fields inside site/stockdata/<TICKER>.json` | json | daily-engine | display | 1 | 0 |
| insider-lh-panel | `data/research/insider_lh_panel.parquet` | parquet | on-demand | display | 1 | 0 |
| insider-lh-panel-manifest | `data/research/insider_lh_panel_manifest.json` | json | on-demand | display | 1 | 0 |
| insider-lh-ruler-p-results | `data/research/insider_lh_ruler_p_results.parquet` | parquet | on-demand | display | 1 | 0 |
| long-hold-clocks | `embedded: entry_clock + thesis_clock inside site/stockdata/<TICKER>.json` | json | daily-engine | display | 1 | 0 |
| long-hold-compounder-features | `embedded: financials.multiyear.compounder inside site/stockdata/<TICKER>.json` | json | daily-engine | display | 1 | 0 |
| long-hold-dead-name-prices | `data/edgar/dead_name_prices.parquet` | parquet | on-demand | infrastructure | 1 | 0 |
| long-hold-expect-drift-manifest | `data/research/expect_drift_panel_manifest.json` | json | on-demand | display | 1 | 0 |
| long-hold-expect-drift-panel | `data/research/expect_drift_panel.parquet` | parquet | on-demand | display | 1 | 0 |
| long-hold-expectation-state | `embedded: expectation_state inside site/stockdata/<TICKER>.json` | json | daily-engine | display | 1 | 0 |
| long-hold-killtest-results | `data/research/missed_hold_study_results.parquet` | parquet | on-demand | display | 1 | 0 |
| long-hold-labels | `data/research/long_hold_labels.parquet` | parquet | on-demand | display | 1 | 0 |
| long-hold-labels-manifest | `data/research/long_hold_labels_manifest.json` | json | on-demand | display | 1 | 0 |
| long-hold-thesis-funnel-history | `data/research/thesis_funnel_history.parquet` | parquet | daily-engine | display | 1 | 0 |
| long-hold-thesis-funnel-panel | `embedded: thesis_funnel inside site/stockdata/<TICKER>.json` | json | daily-engine | display | 1 | 0 |
| long-hold-thesis-funnel-states | `data/research/thesis_funnel_states.parquet` | parquet | on-demand | display | 1 | 0 |
| long-hold-thesis-funnel-states-manifest | `data/research/thesis_funnel_states_manifest.json` | json | on-demand | display | 1 | 0 |
| moat-falsifier-sensors | `embedded: per-ticker moat sensor fields inside site/stockdata/<TICKER>.json` | json | daily-engine | display | 1 | 0 |
| per-fire-sector-benchmark | `data/research/per_fire_sector_benchmark.parquet` | parquet | on-demand | display | 1 | 0 |
| ticker-sectors | `data/breadth/ticker_sectors.parquet` | parquet | on-demand | display | 1 | 0 |
| winner-autopsy-panel | `data/research/winner_autopsy_panel.json` | json | daily-engine | display | 1 | 0 |
| winner-episodes | `data/research/winner_episodes.parquet` | parquet | on-demand | display | 1 | 0 |
| breakaway-watch-history | `data/research/breakaway_watch_history.parquet` | parquet | daily-engine | display | 0 | 0 |
| winner-autopsy-manifest | `data/research/winner_autopsy_manifest.json` | json | daily-engine | display | 0 | 0 |
| winner-episodes-manifest | `data/research/winner_episodes_manifest.json` | json | on-demand | display | 0 | 0 |

### macro-context-rail

| id | path | format | cadence | tier | consumers | external consumers |
|---|---|---|---|---|---|---|
| forex-latest | `data/forex/latest.json` | json | daily-engine | display | 6 | 0 |
| commodity-latest | `data/commodity/latest.json` | json | daily-engine | display | 4 | 0 |
| transmission-latest | `data/transmission/latest.json` | json | daily-engine | display | 4 | 0 |
| bond-health | `data/bonds/bond_health.json` | json | daily-engine | display | 2 | 0 |
| canada-regime-latest | `data/canada_regime/latest.json` | json | daily-engine | display | 2 | 0 |
| china-regime-latest | `data/china_regime/latest.json` | json | asia-close | display | 2 | 0 |
| crossasset-latest | `data/crossasset/latest.json` | json | daily-engine | display | 2 | 0 |
| hk-regime-latest | `data/hk_regime/latest.json` | json | asia-close | display | 2 | 0 |
| macro-snapshots-latest | `data/macro_snapshots/latest.json` | json | daily-engine | display | 2 | 0 |
| macro-snapshots-ledger | `data/macro_snapshots/ledger.parquet` | parquet | daily-engine | infrastructure | 2 | 0 |
| macro-transitions | `data/macro_snapshots/transitions.jsonl` | jsonl | daily-engine | display | 2 | 0 |
| site-factor-series | `site/factordata/factor_series.json` | json | daily-engine | display | 2 | 0 |
| site-alerts-triage | `site/factordata/alerts_triage.json` | json | daily-engine | display | 1 | 0 |
| site-intelligence-briefing | `site/intelligence/briefing.json` | json | daily-engine | display | 1 | 0 |
| macro-context-latest | `data/macro_context/latest.json` | json | daily-engine | display | 0 | 0 |

### macro-release-intel

| id | path | format | cadence | tier | consumers | external consumers |
|---|---|---|---|---|---|---|
| cleveland-nowcast-store | `data/cleveland_nowcast/nowcast.parquet` | parquet | collect | infrastructure | 1 | 0 |
| kalshi-releases-store | `data/prediction_markets/kalshi_releases.parquet` | parquet | collect | infrastructure | 1 | 0 |
| release-forecast-latest | `data/release_forecast/latest.json` | json | daily-engine | display | 0 | 1 |
| release-forecast-ledger | `data/release_forecast/forward_ledger.jsonl` | jsonl | daily-engine | shadow | 1 | 0 |
| site-release-forecast | `site/macrodata/release_forecast.json` | json | daily-engine | display | 0 | 1 |
| release-forecast-scoreboard | `data/release_forecast/scoreboard.json` | json | daily-engine | display | 0 | 0 |

### mastermind-feedback-contract

| id | path | format | cadence | tier | consumers | external consumers |
|---|---|---|---|---|---|---|
| site-mastermind-nw-feedback | `site/mastermind/nw_feedback.json` | json | on-demand | display | 1 | 0 |
| mastermind-feedback-summary | `data/governance/mastermind_feedback_summary.json` | json | daily-engine | display | 0 | 0 |

### metabolism-phase-a

| id | path | format | cadence | tier | consumers | external consumers |
|---|---|---|---|---|---|---|
| metabolism-journal | `data/metabolism/journal/` | json | on-demand | infrastructure | 4 | 0 |
| metabolism-budget-ledger | `data/metabolism/budget_ledger.json` | json | on-demand | infrastructure | 1 | 0 |
| metabolism-til-fitness | `data/metabolism/fitness/til.json` | json | daily-engine | shadow | 1 | 0 |
| metabolism-verify | `data/metabolism/verify/` | json | on-demand | infrastructure | 1 | 0 |
| metabolism-digest | `data/metabolism/digest/` | other | weekly | shadow | 0 | 0 |

### metabolism-phase-v2a

| id | path | format | cadence | tier | consumers | external consumers |
|---|---|---|---|---|---|---|
| metabolism-organism-state | `data/metabolism/organism_state.json` | json | daily-engine | shadow | 2 | 0 |
| metabolism-insight-bus | `data/metabolism/insight_bus.jsonl` | jsonl | daily-engine | shadow | 1 | 0 |
| metabolism-agenda | `data/metabolism/agenda/` | json | daily-engine | shadow | 0 | 0 |
| metabolism-trajectory | `data/metabolism/trajectory.jsonl` | jsonl | daily-engine | shadow | 0 | 0 |

### metabolism-phase-v2b

| id | path | format | cadence | tier | consumers | external consumers |
|---|---|---|---|---|---|---|
| metabolism-build-claims | `data/metabolism/claims.jsonl` | jsonl | on-demand | shadow | 2 | 0 |
| metabolism-key-ledger | `data/metabolism/key_ledger.jsonl` | jsonl | on-demand | infrastructure | 2 | 0 |

### metabolism-phase-v2c

| id | path | format | cadence | tier | consumers | external consumers |
|---|---|---|---|---|---|---|
| metabolism-lobe-charters | `config/lobe_charters.yml` | other | on-demand | shadow | 3 | 0 |
| metabolism-authority-audit | `data/metabolism/authority_audit/` | json | on-demand | shadow | 1 | 0 |
| metabolism-lifecycle-docket | `data/metabolism/lifecycle_docket/` | json | on-demand | shadow | 1 | 0 |
| metabolism-lifecycle-journal | `data/metabolism/lifecycle/` | jsonl | on-demand | shadow | 1 | 0 |

### metabolism-phase-v2d

| id | path | format | cadence | tier | consumers | external consumers |
|---|---|---|---|---|---|---|
| metabolism-fitness-history | `data/metabolism/fitness_history.jsonl` | jsonl | daily-engine | shadow | 2 | 0 |
| metabolism-lessons | `data/metabolism/lessons.jsonl` | jsonl | on-demand | shadow | 2 | 0 |
| metabolism-agenda-archive | `data/metabolism/agenda_archive/` | json | on-demand | shadow | 1 | 0 |
| metabolism-preference-prior | `data/metabolism/preference_prior.json` | json | weekly | shadow | 1 | 0 |

### metabolism-phase0

| id | path | format | cadence | tier | consumers | external consumers |
|---|---|---|---|---|---|---|
| capability-manifest | `config/capability_manifest.yml` | other | on-demand | infrastructure | 1 | 0 |
| capability-audit | `data/neuralweb/capability_audit.jsonl` | jsonl | on-demand | infrastructure | 0 | 0 |

### momoedge

| id | path | format | cadence | tier | consumers | external consumers |
|---|---|---|---|---|---|---|
| prophet-trade-plan | `prophet/trade_plan/<ID>.json` | json | daily-engine | display | 2 | 1 |
| options-flow-chain-heat | `live_flow/chain_heat_current.json` | json | collect | display | 1 | 1 |
| options-structure-gex-state | `options_structure/gex_state/<ROOT>.json` | json | daily-engine | display | 1 | 1 |
| options-structure-matrix | `options_structure/matrix/<ROOT>.json` | json | daily-engine | display | 1 | 1 |
| prophet-management-state | `prophet/state/<ID>.json` | json | daily-engine | display | 1 | 1 |
| options-structure-structural | `options_structure/structural/<ROOT>.json` | json | daily-engine | shadow | 1 | 0 |
| prophet-index | `site/prophet/index.json` | json | daily-engine | display | 0 | 1 |
| prophet-ledger | `data/prophet/ledger.jsonl` | jsonl | daily-engine | display | 0 | 0 |

### narrative-ignition

| id | path | format | cadence | tier | consumers | external consumers |
|---|---|---|---|---|---|---|
| stock-flare-persistence | `site/stockdata/flare_persistence.json` | json | daily-engine | display | 1 | 0 |
| stock-narrative-flares | `site/narrativedata/flares.json` | json | daily-engine | display | 1 | 0 |
| narrative-first-coverage | `data/narrative_flare/first_coverage.parquet` | parquet | daily-engine | infrastructure | 0 | 0 |
| stock-flare-persistence-history | `data/flare_persistence/state_hist.parquet` | parquet | daily-engine | display | 0 | 0 |
| stock-narrative-witness-history | `data/narrative_flare/witness_hist.parquet` | parquet | daily-engine | infrastructure | 0 | 0 |

### nasdaq-internals

| id | path | format | cadence | tier | consumers | external consumers |
|---|---|---|---|---|---|---|
| nasdaq-internals | `site/marketdata/nasdaq_internals.json` | json | daily-engine | display | 0 | 1 |

### neural-web

| id | path | format | cadence | tier | consumers | external consumers |
|---|---|---|---|---|---|---|
| world-state | `data/neuralweb/world_state.json` | json | daily-engine | infrastructure | 10 | 1 |
| spine-index | `data/neuralweb/spine_index.parquet` | parquet | daily-engine | infrastructure | 5 | 0 |
| liquidity-plumbing | `data/neuralweb/liquidity_plumbing.json` | json | daily-engine | shadow | 4 | 0 |
| mechanism-pathways | `data/neuralweb/mechanism_pathways.json` | json | daily-engine | display | 4 | 0 |
| confluence-graph | `data/neuralweb/confluence_graph.json` | json | daily-engine | display | 2 | 1 |
| cortex-memo | `data/neuralweb/cortex/memo.json` | json | nightly-cortex | shadow | 2 | 1 |
| cortex-probation | `data/neuralweb/cortex/probation.json` | json | nightly-cortex | infrastructure | 2 | 1 |
| feeds-plane | `site/feeds/` | json | daily-engine | infrastructure | 1 | 2 |
| governance-ledger | `data/neuralweb/governance.jsonl` | jsonl | daily-engine | infrastructure | 3 | 0 |
| kernel-families | `data/neuralweb/kernel_families.json` | json | daily-engine | infrastructure | 2 | 1 |
| machine-registry | `data/neuralweb/machine_registry.jsonl` | jsonl | nightly-cortex | infrastructure | 3 | 0 |
| neuralweb-health | `data/neuralweb/health.json` | json | daily-engine | infrastructure | 3 | 0 |
| rule-experiment-registry | `data/rule_experiments/registry.jsonl` | jsonl | on-demand | infrastructure | 3 | 0 |
| site-artifact-manifest | `site/factordata/contracts/artifact_manifest.json` | json | daily-engine | infrastructure | 1 | 2 |
| site-golden-signals | `site/factordata/contracts/golden_signals.json` | json | daily-engine | infrastructure | 1 | 2 |
| evidence-clock-reviews | `data/neuralweb/evidence_clock_reviews.jsonl` | jsonl | on-demand | display | 2 | 0 |
| kernel-decisions | `data/neuralweb/kernel_decisions.json` | json | on-demand | infrastructure | 1 | 1 |
| nw-health-run-history | `data/neuralweb/nw_health_run_history.jsonl` | jsonl | daily-engine | infrastructure | 2 | 0 |
| reflex-firings-pattern | `data/reflexes/<NAME>/firings.jsonl` | jsonl | on-demand | shadow | 2 | 0 |
| attention-deterministic | `data/neuralweb/attention_deterministic.json` | json | daily-engine | display | 1 | 0 |
| causal-mechanisms | `data/neuralweb/causal_mechanisms.jsonl` | jsonl | on-demand | shadow | 1 | 0 |
| claim-accountability | `data/governance/claim_accountability.json` | json | collect | infrastructure | 1 | 0 |
| cortex-attention-firings | `data/reflexes/cortex_attention/firings.jsonl` | jsonl | nightly-cortex | shadow | 1 | 0 |
| cortex-attention-grades | `data/reflexes/cortex_attention/grades.jsonl` | jsonl | nightly-cortex | shadow | 1 | 0 |
| evidence-clock | `data/neuralweb/evidence_clock.json` | json | daily-engine | display | 1 | 0 |
| fred-wresbal | `data/fred/WRESBAL.parquet` | parquet | collect | infrastructure | 1 | 0 |
| kernel-estimates | `data/neuralweb/kernel_estimates.parquet` | parquet | daily-engine | infrastructure | 1 | 0 |
| mechanism-pathways-history | `data/neuralweb/mechanism_pathways_history.jsonl` | jsonl | daily-engine | display | 1 | 0 |
| neuralweb-daily-brief | `data/neuralweb/daily_brief.json` | json | daily-engine | display | 1 | 0 |
| neuralweb-daily-brief-history | `data/neuralweb/daily_brief_history.jsonl` | jsonl | daily-engine | display | 1 | 0 |
| ops-push-basket-freeze | `data/alert_triage/push_sent_basket_freeze.jsonl` | jsonl | on-demand | infrastructure | 1 | 0 |
| ops-push-healthcheck | `data/alert_triage/push_sent_healthcheck.jsonl` | jsonl | on-demand | infrastructure | 1 | 0 |
| ops-push-nw-health | `data/alert_triage/push_sent_nw_health.jsonl` | jsonl | daily-engine | infrastructure | 1 | 0 |
| ops-push-signal-sanity | `data/alert_triage/push_sent_signal_sanity.jsonl` | jsonl | on-demand | infrastructure | 1 | 0 |
| reflex-firings-commodity-shock | `data/reflexes/commodity_shock/firings.jsonl` | jsonl | on-demand | shadow | 1 | 0 |
| reflex-firings-regime-selfheal | `data/reflexes/regime_stale_selfheal/firings.jsonl` | jsonl | on-demand | infrastructure | 1 | 0 |
| reflex-push-dedup-store | `data/alert_triage/push_sent.jsonl` | jsonl | on-demand | infrastructure | 1 | 0 |
| site-attention-deterministic | `site/neuralwebdata/attention_deterministic.json` | json | daily-engine | display | 1 | 0 |
| site-mechanism-pathways | `site/neuralwebdata/mechanism_pathways.json` | json | daily-engine | display | 1 | 0 |
| site-neuralweb-daily-brief | `site/neuralwebdata/daily_brief.json` | json | daily-engine | display | 1 | 0 |
| site-neuralweb-governance-recent | `site/neuralwebdata/governance_recent.json` | json | daily-engine | display | 1 | 0 |
| site-neuralweb-health-history | `site/neuralwebdata/health_history.json` | json | daily-engine | display | 1 | 0 |
| causal-feature-inventory | `data/neuralweb/causal_feature_inventory.json` | json | daily-engine | infrastructure | 0 | 0 |
| entity-thesis-mechanism-registry | `data/neuralweb/entity_thesis_mechanism_registry.json` | json | daily-engine | infrastructure | 0 | 0 |
| hypothesis-inbox | `data/neuralweb/cortex/hypothesis_inbox.jsonl` | jsonl | nightly-cortex | infrastructure | 0 | 0 |
| lagging-signals | `data/neuralweb/lagging_signals.json` | json | daily-engine | infrastructure | 0 | 0 |
| research-queue | `data/neuralweb/research_queue.json` | json | on-demand | infrastructure | 0 | 0 |
| risk-radar-review-log | `data/risk_radar/review_log.jsonl` | jsonl | weekly | display | 0 | 0 |
| rule-experiment-summaries | `data/rule_experiments/results/<EXP_ID>_summary.json` | json | on-demand | display | 0 | 0 |
| site-neuralweb-health | `site/neuralwebdata/health.json` | json | daily-engine | infrastructure | 0 | 0 |
| site-neuralweb-ruling-graph | `site/neuralwebdata/ruling_graph.json` | json | on-demand | display | 0 | 0 |

### next3

| id | path | format | cadence | tier | consumers | external consumers |
|---|---|---|---|---|---|---|
| operator-exposure-log | `data/operator/exposure_log.jsonl` | jsonl | daily-engine | infrastructure | 1 | 0 |
| operator-exposure-summary | `data/governance/operator_exposure_summary.json` | json | daily-engine | infrastructure | 0 | 0 |
| options-entry-coverage | `data/options_entry/coverage.json` | json | collect | infrastructure | 0 | 0 |

### nw-context-intelligence

| id | path | format | cadence | tier | consumers | external consumers |
|---|---|---|---|---|---|---|
| context-candidates | `data/neuralweb/context_candidates.jsonl` | jsonl | nightly-cortex | display | 1 | 0 |
| context-risk | `data/neuralweb/context_risk.json` | json | nightly-cortex | display | 1 | 0 |
| site-context-risk | `site/neuralwebdata/context_risk.json` | json | nightly-cortex | display | 0 | 0 |

### nw-mastermind-bridge

| id | path | format | cadence | tier | consumers | external consumers |
|---|---|---|---|---|---|---|
| neuralweb-mastermind-context | `data/neuralweb/mastermind_context.json` | json | daily-engine | display | 1 | 1 |
| site-neuralweb-market-plane | `site/neuralwebdata/market_plane.json` | json | daily-engine | display | 1 | 1 |
| analyst-targets | `data/analyst/targets.parquet` | parquet | collect | display | 1 | 0 |
| site-neuralweb-mastermind-context | `site/neuralwebdata/mastermind_context.json` | json | daily-engine | display | 0 | 1 |
| neuralweb-market-plane | `data/neuralweb/market_plane.json` | json | daily-engine | display | 0 | 0 |

### nw-rails

| id | path | format | cadence | tier | consumers | external consumers |
|---|---|---|---|---|---|---|
| dispersion-regime | `data/dispersion/regime.json` | json | daily-engine | display | 4 | 0 |
| covariance-spine | `data/neuralweb/covariance_spine.json` | json | daily-engine | infrastructure | 1 | 0 |
| grading-closure | `data/governance/grading_closure.json` | json | collect | infrastructure | 1 | 0 |
| covariance-spine-history | `data/neuralweb/covariance_spine_history.parquet` | parquet | daily-engine | infrastructure | 0 | 0 |
| operator-action-ledger | `data/operator/action_ledger.jsonl` | jsonl | on-demand | infrastructure | 0 | 0 |
| operator-grading | `data/governance/operator_grading.json` | json | on-demand | infrastructure | 0 | 0 |
| site-covariance-spine | `site/neuralwebdata/covariance_spine.json` | json | daily-engine | infrastructure | 0 | 0 |

### options-alpha

| id | path | format | cadence | tier | consumers | external consumers |
|---|---|---|---|---|---|---|
| polygon-gex-summaries | `data/polygon_gex/summary_*.parquet` | parquet | collect | display | 4 | 0 |
| vol-regime-gate | `data/vol_regime/gate.json` | json | on-demand | scored | 3 | 0 |
| gex-state-history | `data/index_gex_history/*.parquet` | parquet | weekly | display | 2 | 0 |
| options-skew-snapshots | `data/options_skew/snapshots.parquet` | parquet | collect | display | 2 | 0 |
| vol-regime-basket-overlay-gate | `data/vol_regime/basket_overlay_gate.json` | json | on-demand | scored | 2 | 0 |
| options-flow-index | `site/flow/index.json` | json | collect | display | 0 | 1 |
| options-ivspread-snapshots | `data/options_ivspread/snapshots.parquet` | parquet | collect | display | 1 | 0 |

### options-nw-entry-intelligence

| id | path | format | cadence | tier | consumers | external consumers |
|---|---|---|---|---|---|---|
| options-entry-state | `data/options_entry/state.parquet` | parquet | collect | display | 3 | 1 |
| options-entry-gate | `data/options_entry/gate.json` | json | collect | shadow | 1 | 1 |
| live-options-flow-current | `live_flow/feed_current.json` | json | collect | display | 0 | 1 |

### oracle

| id | path | format | cadence | tier | consumers | external consumers |
|---|---|---|---|---|---|---|
| radar-theses | `data/radar/theses.jsonl` | jsonl | daily-engine | display | 8 | 0 |
| site-radar-json | `site/basketdata/radar.json` | json | daily-engine | display | 7 | 0 |
| site-basketdata-radar-enriched | `site/basketdata/radar_enriched.json` | json | daily-engine | display | 6 | 0 |
| site-radar-ticker | `site/basketdata/radar_ticker.json` | json | daily-engine | display | 5 | 1 |
| site-basket-oracle-state | `site/basketdata/oracle_state.json` | json | daily-engine | display | 5 | 0 |
| site-basket-flow | `site/basketdata/flow.json` | json | daily-engine | display | 2 | 1 |
| index-leadership-snapshots | `data/index_leadership/snapshots.jsonl` | jsonl | daily-engine | shadow | 2 | 0 |
| oracle-operator-tape-outcomes | `data/oracle/operator_tape_outcomes.jsonl` | jsonl | daily-engine | infrastructure | 2 | 0 |
| oracle-qual-filter-accrual | `data/oracle/qual_filter_accrual.json` | json | daily-engine | display | 2 | 0 |
| oracle-qual-filter-stamps | `data/oracle/qual_filter_stamps.jsonl` | jsonl | daily-engine | shadow | 2 | 0 |
| oracle-reversion-forward-ledger | `data/oracle/reversion_forward/<compound_id>.jsonl` | jsonl | daily-engine | shadow | 2 | 0 |
| radar-track-record | `data/radar/track_record.json` | json | daily-engine | display | 2 | 0 |
| site-marketdata-subsector-rotation | `site/marketdata/subsector_rotation.json` | json | daily-engine | display | 2 | 0 |
| subsector-rotation-snapshots | `data/subsector_rotation/snapshots.jsonl` | jsonl | daily-engine | shadow | 2 | 0 |
| oracle-operator-scorecard | `data/oracle/operator_scorecard.json` | json | daily-engine | display | 1 | 0 |
| oracle-qual-filter-registry | `data/oracle/qual_filters/registry.jsonl` | jsonl | on-demand | infrastructure | 1 | 0 |
| oracle-reversion-authority | `data/oracle/reversion_authority.json` | json | daily-engine | infrastructure | 1 | 0 |
| oracle-reversion-kill-requeue | `data/oracle/reversion_kill_requeue.jsonl` | jsonl | on-demand | infrastructure | 1 | 0 |
| oracle-reversion-promotion-queue | `data/oracle/reversion_promotion_queue.json` | json | daily-engine | infrastructure | 1 | 0 |
| oracle-reversion-state | `site/basketdata/oracle_reversion_state.json` | json | daily-engine | display | 1 | 0 |
| oracle-tape-onset | `site/basketdata/oracle_tape_onset.json` | json | daily-engine | display | 1 | 0 |
| oracle-tape-onset-ledger | `data/oracle/tape_onset_ledger.jsonl` | jsonl | daily-engine | shadow | 1 | 0 |
| oracle-turn-desk | `site/basketdata/oracle_turn_desk.json` | json | daily-engine | display | 1 | 0 |
| oracle-turn-desk-ledger | `data/oracle/turn_desk_ledger.jsonl` | jsonl | daily-engine | shadow | 1 | 0 |
| site-basketdata-radar-news | `site/basketdata/radar_news.json` | json | daily-engine | display | 1 | 0 |
| site-member-context | `site/basketdata/member_context.json` | json | daily-engine | display | 1 | 0 |
| site-narrative-brain | `site/basketdata/narrative_brain.json` | json | daily-engine | display | 1 | 0 |
| oracle-ratio-lens-feed | `site/oracledata/ratio_lens.json` | json | daily-engine | display | 0 | 0 |
| oracle-ratio-lens-ledger | `data/oracle/ratio_lens_ledger.jsonl` | jsonl | daily-engine | display | 0 | 0 |

### pick-lab

| id | path | format | cadence | tier | consumers | external consumers |
|---|---|---|---|---|---|---|
| pick-lab-entry-ledger | `site/labdata/pick_lab.json` | json | daily-engine | display | 1 | 0 |
| pick-lab-longhold-ledger | `site/labdata/pick_lab_longhold.json` | json | daily-engine | display | 1 | 0 |
| pick-lab-snapshots | `data/pick_lab/snapshots/` | parquet | daily-engine | infrastructure | 1 | 0 |

### policy-shock

| id | path | format | cadence | tier | consumers | external consumers |
|---|---|---|---|---|---|---|
| shock-deescalation-state | `site/live/shock_state.json` | json | daily-engine | display | 3 | 0 |
| flip-confirmation-events | `data/flip_confirmation/events.jsonl` | jsonl | daily-engine | display | 1 | 0 |
| flip-confirmation-snapshot | `site/flip_confirmation_data.json` | json | daily-engine | display | 1 | 0 |
| shock-deescalation-firings | `data/reflexes/shock_deescalation/firings.jsonl` | jsonl | daily-engine | shadow | 1 | 0 |
| site-policy-lever | `site/policy_lever.json` | json | daily-engine | display | 1 | 0 |

### qualitative-intelligence

| id | path | format | cadence | tier | consumers | external consumers |
|---|---|---|---|---|---|---|
| altdata-by-ticker | `data/altdata/by_ticker.json` | json | daily-engine | display | 15 | 0 |
| qledger-claims | `data/qledger/claims.jsonl` | jsonl | daily-engine | shadow | 14 | 0 |
| qbus-items | `data/qbus/items.parquet` | parquet | daily-engine | infrastructure | 10 | 0 |
| site-altdata-mastermind | `site/altdata/mastermind.json` | json | daily-engine | display | 8 | 2 |
| site-altdata-by-ticker | `site/altdata/by_ticker.json` | json | daily-engine | display | 8 | 0 |
| site-qledger-track-record | `site/qledger/track_record.json` | json | daily-engine | display | 5 | 2 |
| spine-predictions | `data/spine/predictions.parquet` | parquet | daily-engine | shadow | 6 | 0 |
| ai-desk-theses | `data/ai_desk/theses.jsonl` | jsonl | daily-engine | shadow | 5 | 0 |
| altdata-theses | `data/altdata/theses.jsonl` | jsonl | daily-engine | shadow | 4 | 0 |
| foresight-log | `data/foresight/log.jsonl` | jsonl | daily-engine | shadow | 4 | 0 |
| policy-intent-theses | `data/policy_intent/theses.jsonl` | jsonl | daily-engine | shadow | 4 | 0 |
| site-intelligence-by-ticker | `site/intelligence/by_ticker.json` | json | daily-engine | display | 3 | 1 |
| demand-chain-theses | `data/demand_chain/theses.jsonl` | jsonl | daily-engine | shadow | 3 | 0 |
| site-experiments | `site/marketdata/experiments.json` | json | daily-engine | display | 2 | 1 |
| altdata-feed | `data/altdata/feed.json` | json | daily-engine | display | 2 | 0 |
| altdata-track-record | `data/altdata/track_record.json` | json | daily-engine | display | 2 | 0 |
| hub-signal-snapshots | `data/hub/signal_snapshots.jsonl` | jsonl | daily-engine | shadow | 2 | 0 |
| master-brain-theses | `data/master_brain/theses.jsonl` | jsonl | daily-engine | shadow | 2 | 0 |
| site-ai-desk-us | `site/allocationdata/ai_desk_us.json` | json | daily-engine | display | 1 | 1 |
| stock-desk-theses | `data/stock_desk/theses.jsonl` | jsonl | daily-engine | shadow | 2 | 0 |
| thematic-desk-theses | `data/thematic_desk/theses.jsonl` | jsonl | daily-engine | shadow | 2 | 0 |
| foresight-earliness-log | `data/foresight/earliness_log.jsonl` | jsonl | daily-engine | shadow | 1 | 0 |
| site-foresight-cascade | `site/basketdata/foresight_cascade.json` | json | daily-engine | display | 0 | 1 |

### research-factory

| id | path | format | cadence | tier | consumers | external consumers |
|---|---|---|---|---|---|---|
| research-factory-candidates | `data/research_factory/candidates.jsonl` | jsonl | on-demand | display | 1 | 0 |
| research-factory-paper-monitor | `data/research_factory/paper_monitor.jsonl` | jsonl | on-demand | display | 0 | 0 |
| research-factory-transitions | `data/research_factory/transitions.jsonl` | jsonl | on-demand | display | 0 | 0 |

### sector-pulse

| id | path | format | cadence | tier | consumers | external consumers |
|---|---|---|---|---|---|---|
| baskets-membership | `data/baskets/membership.json` | json | weekly | infrastructure | 16 | 0 |
| site-baskets-json | `site/basketdata/baskets.json` | json | daily-engine | display | 9 | 1 |
| site-sector-pulse | `site/basketdata/sector_pulse.json` | json | daily-engine | display | 3 | 2 |

### setup-species

| id | path | format | cadence | tier | consumers | external consumers |
|---|---|---|---|---|---|---|
| us-board-ledger-retro-grades | `data/us_board_ledger/retro_grades.parquet` | parquet | daily-engine | infrastructure | 9 | 0 |
| signal-archive-mtf | `data/signal_archive/mtf_signals_latest.json` | json | daily-engine | display | 6 | 0 |
| experiments-registry-seed | `data/experiments/registry_seed.json` | json | daily-engine | infrastructure | 5 | 0 |
| signal-archive-track-record | `data/signal_archive/track_record.parquet` | parquet | daily-engine | shadow | 5 | 0 |
| site-signals-per-ticker | `site/signals/<SYM>.json` | json | daily-engine | display | 3 | 2 |
| species-registry | `data/species/registry.json` | json | on-demand | infrastructure | 5 | 0 |

### short-side

| id | path | format | cadence | tier | consumers | external consumers |
|---|---|---|---|---|---|---|
| bd-avoid1-ledger | `data/research/bd_avoid1_ledger.parquet` | parquet | on-demand | infrastructure | 1 | 0 |

### signal-commons

| id | path | format | cadence | tier | consumers | external consumers |
|---|---|---|---|---|---|---|
| event-priors-clinicaltrials | `data/special_situations/event_priors/clinicaltrials.json` | json | weekly | display | 2 | 0 |
| event-priors-earnings | `data/special_situations/event_priors/earnings.json` | json | weekly | display | 2 | 0 |
| event-priors-ipo-lockup | `data/special_situations/event_priors/ipo_lockup.json` | json | weekly | display | 2 | 0 |
| event-priors-openfda | `data/special_situations/event_priors/openfda.json` | json | weekly | display | 2 | 0 |
| event-priors-sp-index-changes | `data/special_situations/event_priors/sp_index_changes.json` | json | weekly | display | 2 | 0 |
| kernel-half-lives | `data/neuralweb/half_life.json` | json | daily-engine | infrastructure | 1 | 0 |
| event-priors-gov-contract | `data/special_situations/event_priors/gov_contract.json` | json | weekly | display | 0 | 0 |
| reflexivity-n-eff-history | `data/reflexivity/n_eff_history.json` | json | daily-engine | infrastructure | 0 | 0 |

### signal-foundry

| id | path | format | cadence | tier | consumers | external consumers |
|---|---|---|---|---|---|---|
| signal-foundry-candidates | `data/signal_foundry/candidates.jsonl` | jsonl | weekly | display | 1 | 0 |
| signal-foundry-forward | `data/signal_foundry/forward` | jsonl | daily-engine | display | 1 | 0 |
| signal-foundry-lane-status | `data/signal_foundry/lane_status.json` | json | on-demand | display | 1 | 0 |
| signal-foundry-results | `data/signal_foundry/results` | json | weekly | display | 1 | 0 |

### stock-personality

| id | path | format | cadence | tier | consumers | external consumers |
|---|---|---|---|---|---|---|
| site-stock-personality | `site/factordata/stock_personality.json` | json | daily-engine | display | 4 | 0 |
| dna-class-ref | `site/factordata/dna_class.json` | json | nightly-factor-panel | infrastructure | 1 | 0 |
| stock-personality-panel | `data/stock_personality/panel/YYYY-MM/panel.parquet` | parquet | daily-engine | infrastructure | 1 | 0 |
| stock-personality-block | `embedded: personality block inside site/stockdata/<TICKER>.json` | json | daily-engine | display | 0 | 0 |
| stock-personality-forward-ledger | `data/stock_personality/forward_ledger.parquet` | parquet | daily-engine | shadow | 0 | 0 |

### tech-internals

| id | path | format | cadence | tier | consumers | external consumers |
|---|---|---|---|---|---|---|
| site-factordata-tech-lab | `site/factordata/tech_lab.json` | json | daily-engine | display | 1 | 0 |

### thematic-intelligence

| id | path | format | cadence | tier | consumers | external consumers |
|---|---|---|---|---|---|---|
| site-theme-thesis | `site/neuralwebdata/theme_thesis.json` | json | daily-engine | display | 4 | 0 |
| theme-state | `data/neuralweb/theme_state.json` | json | daily-engine | display | 4 | 0 |
| qledger-falsifier-evaluations | `data/qledger/falsifier_evaluations.jsonl` | jsonl | daily-engine | shadow | 1 | 0 |
| site-theme-pathways | `site/neuralwebdata/theme_pathways.json` | json | daily-engine | display | 1 | 0 |
| theme-phase-history | `data/neuralweb/theme_phase_history.jsonl` | jsonl | daily-engine | display | 1 | 0 |
| theme-placebo-tape | `data/foresight/theme_placebo_tape.jsonl` | jsonl | daily-engine | shadow | 1 | 0 |
| theme-thesis-ledger | `data/neuralweb/theme_thesis_ledger.jsonl` | jsonl | daily-engine | shadow | 1 | 0 |
| foresight-earliness-grades | `data/foresight/earliness_grades.json` | json | daily-engine | display | 0 | 0 |
| site-theme-asymmetry | `site/neuralwebdata/theme_asymmetry.json` | json | daily-engine | display | 0 | 0 |
| site-theme-state | `site/neuralwebdata/theme_state.json` | json | daily-engine | display | 0 | 0 |
| theme-asymmetry | `data/neuralweb/theme_asymmetry.json` | json | daily-engine | display | 0 | 0 |
| theme-pathways | `data/neuralweb/theme_pathways.json` | json | daily-engine | display | 0 | 0 |

### til-w10-clinical

| id | path | format | cadence | tier | consumers | external consumers |
|---|---|---|---|---|---|---|
| neuralweb-theme-clinical | `data/neuralweb/theme_clinical.json` | json | collect | display | 0 | 0 |
| site-clinical-pipeline | `site/basketdata/clinical_pipeline.json` | json | collect | display | 0 | 0 |

### til-w11-options-witness

| id | path | format | cadence | tier | consumers | external consumers |
|---|---|---|---|---|---|---|
| neuralweb-theme-options-witness | `data/neuralweb/theme_options_witness.json` | json | collect | display | 0 | 0 |
| site-options-witness | `site/basketdata/options_witness.json` | json | collect | display | 0 | 0 |

### til-w7-hiring-intent

| id | path | format | cadence | tier | consumers | external consumers |
|---|---|---|---|---|---|---|
| dol-certs-store | `data/dol_certs/certs.parquet` | parquet | collect | display | 1 | 0 |
| hiring-velocity | `data/dol_certs/hiring_velocity.json` | json | collect | display | 0 | 0 |
| site-hiring-intent | `site/basketdata/hiring_intent.json` | json | collect | display | 0 | 0 |

### til-w8-trade-flows

| id | path | format | cadence | tier | consumers | external consumers |
|---|---|---|---|---|---|---|
| neuralweb-theme-trade-flows | `data/neuralweb/theme_trade_flows.json` | json | collect | display | 1 | 0 |
| site-trade-flows | `site/basketdata/trade_flows.json` | json | collect | display | 0 | 0 |

### til-w9-discovery-v2

| id | path | format | cadence | tier | consumers | external consumers |
|---|---|---|---|---|---|---|
| site-github-adoption | `site/basketdata/github_adoption.json` | json | collect | display | 1 | 0 |
| site-phrase-velocity | `site/basketdata/phrase_velocity.json` | json | collect | display | 1 | 0 |
| neuralweb-discovery-confluence | `data/neuralweb/discovery_confluence.json` | json | collect | display | 0 | 0 |

### turn-sensitivity

| id | path | format | cadence | tier | consumers | external consumers |
|---|---|---|---|---|---|---|
| stock-mtf-upturn | `site/stockdata/mtf_upturn.json` | json | daily-engine | display | 1 | 0 |

### us-stocks-prebreakout

| id | path | format | cadence | tier | consumers | external consumers |
|---|---|---|---|---|---|---|
| site-us-standouts | `site/factordata/us_standouts.json` | json | daily-engine | display | 12 | 4 |
| site-signal-gate | `site/factordata/signal_gate.json` | json | daily-engine | display | 5 | 0 |

## Producer → Artifact → Consumer Graph

Flowchart covering the top 15 artifacts by total consumer count. Node count is capped — the full graph (64 artifacts, 200+ nodes) is unreadable.

```mermaid
flowchart LR
    P_engine_run_py(("engine/run.py"))
    A_regime_latest["regime-latest"]
    C_engine_alert_triage_py["engine/alert_triage.py"]
    C_engine_briefing_py["engine/briefing.py"]
    C_engine_china_intel_analysis_py["engine/china_intel_analysis.py"]
    C_engine_china_intel_bus_py["engine/china_intel_bus.py"]
    OVF_regime_latest["...+34 more"]
    A_regime_history["regime-history"]
    C_engine_alerts_py["engine/alerts.py"]
    C_engine_board_ledger_py["engine/board_ledger.py"]
    C_engine_neuralweb_context_api_py["engine/neuralweb/context_api.py"]
    C_engine_neuralweb_lagging_py["engine/neuralweb/lagging.py"]
    OVF_regime_history["...+15 more"]
    P_collectors_breadth_py(("collectors/breadth.py"))
    A_breadth_breadth["breadth-breadth"]
    C_engine_anticipation_py["engine/anticipation.py"]
    C_engine_basket_score_py["engine/basket_score.py"]
    C_engine_neuralweb_world_state_py["engine/neuralweb/world_state.py"]
    OVF_breadth_breadth["...+14 more"]
    P_scripts_seed_us_sector_baskets_py(("scripts/seed_us_sector_baskets.py"))
    A_baskets_membership["baskets-membership"]
    C_engine_demand_ledger_py["engine/demand_ledger.py"]
    C_engine_financial_news_py["engine/financial_news.py"]
    C_engine_froth_fragility_py["engine/froth_fragility.py"]
    C_engine_news_common_py["engine/news_common.py"]
    OVF_baskets_membership["...+12 more"]
    P_scripts_build_stock_library_py(("scripts/build_stock_library.py"))
    A_site_us_standouts["site-us-standouts"]
    C_engine_intelligence_py["engine/intelligence.py"]
    C_engine_risk_brain_py["engine/risk_brain.py"]
    C_engine_signal_sanity_py["engine/signal_sanity.py"]
    C_engine_stock_desk_py["engine/stock_desk.py"]
    OVF_site_us_standouts["...+12 more"]
    P_engine_altdata_signals_py(("engine/altdata_signals.py"))
    A_altdata_by_ticker["altdata-by-ticker"]
    C_engine_altdata_brain_py["engine/altdata_brain.py"]
    C_engine_altdata_confirmers_py["engine/altdata_confirmers.py"]
    C_engine_altdata_signals_py["engine/altdata_signals.py"]
    OVF_altdata_by_ticker["...+11 more"]
    P_engine_qledger_py(("engine/qledger.py"))
    A_qledger_claims["qledger-claims"]
    C_engine_communique_diff_py["engine/communique_diff.py"]
    C_engine_missing_tape_py["engine/missing_tape.py"]
    C_engine_neuralweb_query_py["engine/neuralweb/query.py"]
    C_engine_qledger_ui_py["engine/qledger_ui.py"]
    OVF_qledger_claims["...+10 more"]
    P_scripts_midsmall_pit_py(("scripts/midsmall_pit.py"))
    A_breadth_sp1500_pit["breadth-sp1500-pit"]
    C_engine_grading_py["engine/grading.py"]
    C_engine_group_flow_py["engine/group_flow.py"]
    C_engine_index_changes_py["engine/index_changes.py"]
    C_engine_intel_discovery_py["engine/intel_discovery.py"]
    OVF_breadth_sp1500_pit["...+7 more"]
    P_engine_neuralweb_world_state_py(("engine/neuralweb/world_state.py"))
    A_world_state["world-state"]
    C_scripts_build_feeds_py["scripts/build_feeds.py"]
    C_scripts_notify_py["scripts/notify.py"]
    C_scripts_build_impulse_py["scripts/build_impulse.py"]
    C_engine_etf_pulse_py["engine/etf_pulse.py"]
    OVF_world_state["...+7 more"]
    P_engine_qbus_py(("engine/qbus.py"))
    A_qbus_items["qbus-items"]
    C_engine_china_news_intel_py["engine/china_news_intel.py"]
    C_engine_importance_v0_py["engine/importance_v0.py"]
    OVF_qbus_items["...+6 more"]
    P_engine_altdata_emit_py(("engine/altdata_emit.py"))
    A_site_altdata_mastermind["site-altdata-mastermind"]
    C_engine_radar_plus_py["engine/radar_plus.py"]
    C_engine_radar_ticker_py["engine/radar_ticker.py"]
    OVF_site_altdata_mastermind["...+6 more"]
    P_scripts_build_baskets_py(("scripts/build_baskets.py"))
    A_site_baskets_json["site-baskets-json"]
    C_engine_conviction_accrual_py["engine/conviction_accrual.py"]
    C_engine_group_context_py["engine/group_context.py"]
    C_engine_oracle_panel_py["engine/oracle/panel.py"]
    C_engine_oracle_timemachine_py["engine/oracle/timemachine.py"]
    OVF_site_baskets_json["...+6 more"]
    P_scripts_grade_us_board_py(("scripts/grade_us_board.py"))
    A_us_board_ledger_retro_grades["us-board-ledger-retro-grades"]
    C_engine_china_standout_track_py["engine/china_standout_track.py"]
    C_engine_spine_py["engine/spine.py"]
    C_engine_track_record_py["engine/track_record.py"]
    OVF_us_board_ledger_retro_grades["...+5 more"]
    P_engine_market_state_py(("engine/market_state.py"))
    A_market_state_latest["market-state-latest"]
    C_engine_regime_prior_py["engine/regime_prior.py"]
    C_engine_market_state_audit_py["engine/market_state_audit.py"]
    C_engine_market_state_tune_py["engine/market_state_tune.py"]
    OVF_market_state_latest["...+4 more"]
    P_engine_radar_py(("engine/radar.py"))
    A_radar_theses["radar-theses"]
    C_engine_ai_desk_scorer_py["engine/ai_desk_scorer.py"]
    C_engine_hub_track_record_py["engine/hub_track_record.py"]
    C_engine_master_brain_py["engine/master_brain.py"]
    C_engine_qledger_py["engine/qledger.py"]
    OVF_radar_theses["...+4 more"]
    P_engine_run_py --> A_regime_latest
    A_regime_latest --> C_engine_alert_triage_py
    A_regime_latest --> C_engine_briefing_py
    A_regime_latest --> C_engine_china_intel_analysis_py
    A_regime_latest --> C_engine_china_intel_bus_py
    A_regime_latest --> OVF_regime_latest
    P_engine_run_py --> A_regime_history
    A_regime_history --> C_engine_alerts_py
    A_regime_history --> C_engine_board_ledger_py
    A_regime_history --> C_engine_neuralweb_context_api_py
    A_regime_history --> C_engine_neuralweb_lagging_py
    A_regime_history --> OVF_regime_history
    P_collectors_breadth_py --> A_breadth_breadth
    A_breadth_breadth --> C_engine_anticipation_py
    A_breadth_breadth --> C_engine_basket_score_py
    A_breadth_breadth --> C_engine_neuralweb_lagging_py
    A_breadth_breadth --> C_engine_neuralweb_world_state_py
    A_breadth_breadth --> OVF_breadth_breadth
    P_scripts_seed_us_sector_baskets_py --> A_baskets_membership
    A_baskets_membership --> C_engine_demand_ledger_py
    A_baskets_membership --> C_engine_financial_news_py
    A_baskets_membership --> C_engine_froth_fragility_py
    A_baskets_membership --> C_engine_news_common_py
    A_baskets_membership --> OVF_baskets_membership
    P_scripts_build_stock_library_py --> A_site_us_standouts
    A_site_us_standouts --> C_engine_intelligence_py
    A_site_us_standouts --> C_engine_risk_brain_py
    A_site_us_standouts --> C_engine_signal_sanity_py
    A_site_us_standouts --> C_engine_stock_desk_py
    A_site_us_standouts --> OVF_site_us_standouts
    P_engine_altdata_signals_py --> A_altdata_by_ticker
    A_altdata_by_ticker --> C_engine_altdata_brain_py
    A_altdata_by_ticker --> C_engine_altdata_confirmers_py
    A_altdata_by_ticker --> C_engine_altdata_signals_py
    A_altdata_by_ticker --> C_engine_briefing_py
    A_altdata_by_ticker --> OVF_altdata_by_ticker
    P_engine_qledger_py --> A_qledger_claims
    A_qledger_claims --> C_engine_communique_diff_py
    A_qledger_claims --> C_engine_missing_tape_py
    A_qledger_claims --> C_engine_neuralweb_query_py
    A_qledger_claims --> C_engine_qledger_ui_py
    A_qledger_claims --> OVF_qledger_claims
    P_scripts_midsmall_pit_py --> A_breadth_sp1500_pit
    A_breadth_sp1500_pit --> C_engine_grading_py
    A_breadth_sp1500_pit --> C_engine_group_flow_py
    A_breadth_sp1500_pit --> C_engine_index_changes_py
    A_breadth_sp1500_pit --> C_engine_intel_discovery_py
    A_breadth_sp1500_pit --> OVF_breadth_sp1500_pit
    P_engine_neuralweb_world_state_py --> A_world_state
    A_world_state --> C_scripts_build_feeds_py
    A_world_state --> C_scripts_notify_py
    A_world_state --> C_scripts_build_impulse_py
    A_world_state --> C_engine_etf_pulse_py
    A_world_state --> OVF_world_state
    P_engine_qbus_py --> A_qbus_items
    A_qbus_items --> C_engine_china_news_intel_py
    A_qbus_items --> C_engine_communique_diff_py
    A_qbus_items --> C_engine_financial_news_py
    A_qbus_items --> C_engine_importance_v0_py
    A_qbus_items --> OVF_qbus_items
    P_engine_altdata_emit_py --> A_site_altdata_mastermind
    A_site_altdata_mastermind --> C_engine_intelligence_py
    A_site_altdata_mastermind --> C_engine_radar_plus_py
    A_site_altdata_mastermind --> C_engine_radar_ticker_py
    A_site_altdata_mastermind --> C_engine_china_intel_analysis_py
    A_site_altdata_mastermind --> OVF_site_altdata_mastermind
    P_scripts_build_baskets_py --> A_site_baskets_json
    A_site_baskets_json --> C_engine_conviction_accrual_py
    A_site_baskets_json --> C_engine_group_context_py
    A_site_baskets_json --> C_engine_oracle_panel_py
    A_site_baskets_json --> C_engine_oracle_timemachine_py
    A_site_baskets_json --> OVF_site_baskets_json
    P_scripts_grade_us_board_py --> A_us_board_ledger_retro_grades
    A_us_board_ledger_retro_grades --> C_engine_board_ledger_py
    A_us_board_ledger_retro_grades --> C_engine_china_standout_track_py
    A_us_board_ledger_retro_grades --> C_engine_spine_py
    A_us_board_ledger_retro_grades --> C_engine_track_record_py
    A_us_board_ledger_retro_grades --> OVF_us_board_ledger_retro_grades
    P_engine_market_state_py --> A_market_state_latest
    A_market_state_latest --> C_engine_neuralweb_world_state_py
    A_market_state_latest --> C_engine_regime_prior_py
    A_market_state_latest --> C_engine_market_state_audit_py
    A_market_state_latest --> C_engine_market_state_tune_py
    A_market_state_latest --> OVF_market_state_latest
    P_engine_radar_py --> A_radar_theses
    A_radar_theses --> C_engine_ai_desk_scorer_py
    A_radar_theses --> C_engine_hub_track_record_py
    A_radar_theses --> C_engine_master_brain_py
    A_radar_theses --> C_engine_qledger_py
    A_radar_theses --> OVF_radar_theses
```

## Appendix — Known Extra Writers

Artifacts below have `known_extra_writers` — additional code paths that write to the same artifact outside the declared producer. These are flagged for eventual single-writer consolidation under the Neural Web architecture.

### archetypes-history

- **path:** `data/archetypes/history.parquet`
- **declared producer:** `engine/stock_fundamentals.py`
- **extra writers:**
  - scripts/build_archetype_history.py — alternative builder path

### baskets-membership

- **path:** `data/baskets/membership.json`
- **declared producer:** `scripts/seed_us_sector_baskets.py`
- **extra writers:**
  - scripts/promote_candidate.py — hand-curated edits to add/remove members; additive, idempotent

### board-ledger-ca

- **path:** `data/board_ledger/ca_board.parquet`
- **declared producer:** `engine/board_ledger.py`
- **extra writers:**
  - engine/canada_run.py — calls board_ledger via lane='CA'; store_df.to_parquet L83

### board-ledger-hk

- **path:** `data/board_ledger/hk_board.parquet`
- **declared producer:** `engine/board_ledger.py`
- **extra writers:**
  - engine/hk_run.py — calls board_ledger via lane='HK'; store_df.to_parquet L44

### canada-regime-latest

- **path:** `data/canada_regime/latest.json`
- **declared producer:** `engine/canada_run.py`
- **extra writers:**
  - scripts/build_vector.py — invokes build_canada.main() as a side-effect hook (build_canada is called from build_vector; see scripts/build_vector.py:3116-3117)

### capital-allocation-delta

- **path:** `embedded: capital_allocation block inside site/stockdata/<TICKER>.json`
- **declared producer:** `engine/capital_allocation.py`
- **extra writers:**
  - engine/stock_fundamentals.py — _compute_capital_allocation_block() calls compute_capital_allocation() inside panels()

### china-sector-central-calls

- **path:** `data/china_sector_central/calls.parquet`
- **declared producer:** `engine/china_sector_central.py`
- **extra writers:**
  - scripts/build_china_sector_central.py — runner that calls china_sector_central and persists output; additive append

### china-sector-cycles-forward-log

- **path:** `data/china_sector_cycles/forward_log.parquet`
- **declared producer:** `engine/china_sector_cycles.py`
- **extra writers:**
  - engine/china_sector_cycles_grader.py — grader also appends grade rows to the same parquet

### cn-pick-lab-snapshots

- **path:** `data/china_pick_lab/snapshots/`
- **declared producer:** `scripts/build_china_library.py`
- **extra writers:**
  - scripts/build_china_pick_lab.py — writes enriched snapshot back via write_snapshot (CNPL-R6)

### confluence-graph

- **path:** `data/neuralweb/confluence_graph.json`
- **declared producer:** `engine/neuralweb/confluence.py`
- **extra writers:**
  - scripts/build_confluence_graph.py — thin CLI wrapper; calls build_and_write() defined in the producer; no independent write logic

### event-windows

- **path:** `embedded: event_windows block inside site/stockdata/<TICKER>.json`
- **declared producer:** `engine/event_landmine.py`
- **extra writers:**
  - engine/stock_fundamentals.py — compose() called inside panels(); result keyed as 'event_windows'

### experiments-registry-seed

- **path:** `data/experiments/registry_seed.json`
- **declared producer:** `engine/species_registry.py`
- **extra writers:**
  - scripts/backfill_forward_logs.py — additive experiment entries from historical backfill
  - scripts/build_measurement.py — measurement entries; additive, idempotent

### gex-state-history

- **path:** `data/index_gex_history/*.parquet`
- **declared producer:** `scripts/build_index_gex_history.py`
- **extra writers:**
  - engine/market_gamma.py

### governance-ledger

- **path:** `data/neuralweb/governance.jsonl`
- **declared producer:** `engine/neuralweb/governance.py`
- **extra writers:**
  - engine/risk_radar_intl_audit.py — authority_grant / authority_lapse events when can_force changes
  - engine/market_state_tune.py — a6_auto_apply lane-i events on every tune() call
  - engine/risk_radar_intl_tune.py — a6_auto_apply lane-i events on every tune() call

### great-company-trap

- **path:** `embedded: great_company_trap fields inside site/stockdata/<TICKER>.json`
- **declared producer:** `engine/moat_falsifiers.py`
- **extra writers:**
  - engine/stock_fundamentals.py — _compute_trap_block() calls great_company_trap() inside panels()

### hk-1d-velocity-desk-artifact

- **path:** `site/factordata/hk_1d_velocity_desk.json`
- **declared producer:** `scripts/build_hk_library.py`
- **extra writers:**
  - scripts/build_hk_pick_lab.py — re-computes enriched second pass (two-pass contract)

### hk-pick-lab-snapshots

- **path:** `data/hk_pick_lab/snapshots/`
- **declared producer:** `scripts/build_hk_library.py`
- **extra writers:**
  - scripts/build_hk_pick_lab.py — writes enriched snapshot back via write_snapshot (HKPL-R7)

### hub-signal-snapshots

- **path:** `data/hub/signal_snapshots.jsonl`
- **declared producer:** `engine/hub_track_record.py`
- **extra writers:**
  - scripts/build_intel_hub.py — CLI runner; calls compute() then appends snapshot

### index-leadership-snapshots

- **path:** `data/index_leadership/snapshots.jsonl`
- **declared producer:** `engine/index_leadership_track.py`
- **extra writers:**
  - scripts/build_index_leadership.py — CLI runner; calls compute() then appends snapshot

### kernel-estimates

- **path:** `data/neuralweb/kernel_estimates.parquet`
- **declared producer:** `engine/neuralweb/kernel.py`
- **extra writers:**
  - scripts/build_kernel_estimates.py — thin CLI wrapper; calls write_estimates() defined in the producer; no independent write logic

### kernel-families

- **path:** `data/neuralweb/kernel_families.json`
- **declared producer:** `engine/neuralweb/decay.py`
- **extra writers:**
  - scripts/build_kernel_diagnostics.py — thin CLI wrapper; calls write_families() defined in the producer; no independent write logic

### kernel-half-lives

- **path:** `data/neuralweb/half_life.json`
- **declared producer:** `engine/neuralweb/half_life.py`
- **extra writers:**
  - scripts/build_kernel_half_lives.py — thin CLI wrapper; calls write_half_lives() defined in the producer; no independent write logic

### lagging-signals

- **path:** `data/neuralweb/lagging_signals.json`
- **declared producer:** `engine/neuralweb/lagging.py`
- **extra writers:**
  - scripts/build_kernel_diagnostics.py — thin CLI wrapper; calls write_lagging() defined in the producer; no independent write logic

### long-hold-clocks

- **path:** `embedded: entry_clock + thesis_clock inside site/stockdata/<TICKER>.json`
- **declared producer:** `engine/long_hold_clocks.py`
- **extra writers:**
  - scripts/build_stock_library.py — calls entry_clock() per name after sig_verdict build
  - engine/stock_fundamentals.py — calls thesis_clocks_from_parquet() inside panels()

### long-hold-dead-name-prices

- **path:** `data/edgar/dead_name_prices.parquet`
- **declared producer:** `scripts/research/fetch_dead_name_prices_polygon.py`
- **extra writers:**
  - collectors/edgar_deadname_prices.py — legacy collector (Stooq→Polygon→yfinance); may append rows from CI runs

### long-hold-expectation-state

- **path:** `embedded: expectation_state inside site/stockdata/<TICKER>.json`
- **declared producer:** `engine/expectation_state.py`
- **extra writers:**
  - engine/stock_fundamentals.py — expectation_states() called inside panels(); result keyed as 'expectation_state'

### long-hold-thesis-funnel-history

- **path:** `data/research/thesis_funnel_history.parquet`
- **declared producer:** `scripts/research/build_thesis_funnel_snapshot.py`
- **extra writers:**
  - scripts/research/build_thesis_funnel_history.py — append_history() called by snapshot main() under --write-history

### long-hold-thesis-funnel-panel

- **path:** `embedded: thesis_funnel inside site/stockdata/<TICKER>.json`
- **declared producer:** `engine/thesis_funnel.py`
- **extra writers:**
  - engine/stock_fundamentals.py — _compute_thesis_funnel_block() called inside panels(); result keyed as 'thesis_funnel'

### market-state-latest

- **path:** `data/market_state/latest.json`
- **declared producer:** `engine/market_state.py`
- **extra writers:**
  - scripts/build_site.py — calls market_state.persist() at line 1700; build_site is the runner, market_state.py is the author

### mastermind-feedback-summary

- **path:** `data/governance/mastermind_feedback_summary.json`
- **declared producer:** `scripts/build_mastermind_feedback_summary.py`
- **extra writers:**
  - engine/neuralweb/mastermind_feedback.py — build_and_write() writes the artifact

### metabolism-fitness-history

- **path:** `data/metabolism/fitness_history.jsonl`
- **declared producer:** `engine/metabolism/memory.py`
- **extra writers:**
  - scripts/build_organism_state.py

### metabolism-insight-bus

- **path:** `data/metabolism/insight_bus.jsonl`
- **declared producer:** `engine/metabolism/insight_bus.py`
- **extra writers:**
  - engine/metabolism/anomaly_monitor.py

### metabolism-journal

- **path:** `data/metabolism/journal/`
- **declared producer:** `scripts/metabolism_journal.py`
- **extra writers:**
  - scripts/metabolism_verify.py
  - scripts/metabolism_dispatch.py

### metabolism-key-ledger

- **path:** `data/metabolism/key_ledger.jsonl`
- **declared producer:** `engine/neuralweb/key_pool.py`
- **extra writers:**
  - scripts/metabolism_dispatch.py

### moat-falsifier-sensors

- **path:** `embedded: per-ticker moat sensor fields inside site/stockdata/<TICKER>.json`
- **declared producer:** `engine/moat_falsifiers.py`
- **extra writers:**
  - engine/stock_fundamentals.py — _compute_moat_block() calls compute_moat_falsifiers() inside panels()

### name-score-calls

- **path:** `data/name_score/us_calls.parquet`
- **declared producer:** `engine/name_score_grader.py`
- **extra writers:**
  - engine/name_score_grader.py — grade(market) writes per-market: hk_calls.parquet, ca_calls.parquet, intl_calls.parquet
  - data/china_name_score/calls.parquet — CN legacy path; same producer, separate file

### neuralweb-market-plane

- **path:** `data/neuralweb/market_plane.json`
- **declared producer:** `engine/neuralweb/mastermind_context.py`
- **extra writers:**
  - scripts/build_nw_mastermind_context.py — CLI lane; build_and_write() calls build_and_write_market_plane() defined in the producer; no independent write logic

### neuralweb-mastermind-context

- **path:** `data/neuralweb/mastermind_context.json`
- **declared producer:** `scripts/build_nw_mastermind_context.py`
- **extra writers:**
  - engine/neuralweb/mastermind_context.py — build_and_write() writes both canonical and site copy

### pick-lab-snapshots

- **path:** `data/pick_lab/snapshots/`
- **declared producer:** `scripts/build_stock_library.py`
- **extra writers:**
  - scripts/build_pick_lab.py — writes enriched snapshot back via write_snapshot (PL-R7b)

### qledger-claims

- **path:** `data/qledger/claims.jsonl`
- **declared producer:** `engine/qledger.py`
- **extra writers:**
  - scripts/backfill_qledger_us.py — historical backfill; additive append-only
  - scripts/backfill_qledger_cn.py — CN historical backfill; additive append-only

### regime-history

- **path:** `data/regime/regime_history.parquet`
- **declared producer:** `engine/run.py`
- **extra writers:**
  - engine/canada_run.py — writes data/canada_regime/regime_history.parquet (separate region path, not this path)
  - engine/china_run.py — writes data/china_regime/regime_history.parquet (separate region path)
  - engine/hk_run.py — writes data/hk_regime/regime_history.parquet (separate region path)

### regime-vector

- **path:** `data/regime/regime_vector.parquet`
- **declared producer:** `engine/regime_vector.py`
- **extra writers:**
  - engine/run.py — calls regime_vector.py:487 and stores result at line 681; run.py is the orchestrator

### research-factory-candidates

- **path:** `data/research_factory/candidates.jsonl`
- **declared producer:** `<RESEARCH_FACTORY_INGEST>`
- **extra writers:**
  - scripts/research_factory_ingest.py — W2 ingest writer (planned)

### research-factory-paper-monitor

- **path:** `data/research_factory/paper_monitor.jsonl`
- **declared producer:** `<RESEARCH_FACTORY_MONITOR>`
- **extra writers:**
  - scripts/research_factory_monitor.py — W6 nightly monitor writer (planned)

### research-factory-transitions

- **path:** `data/research_factory/transitions.jsonl`
- **declared producer:** `<RESEARCH_FACTORY_INGEST>`
- **extra writers:**
  - scripts/research_factory_ingest.py — W2 transition writer (planned)
  - scripts/research_factory_decide.py — W5 decision recorder (planned)

### research-queue

- **path:** `data/neuralweb/research_queue.json`
- **declared producer:** `engine/neuralweb/research_queue.py`
- **extra writers:**
  - scripts/build_research_queue.py — thin CLI wrapper; calls write_queue() defined in the producer; no independent write logic

### sector-central-calls

- **path:** `data/sector_central/calls.parquet`
- **declared producer:** `engine/sector_central.py`
- **extra writers:**
  - scripts/build_sector_central.py — runner that calls sector_central and persists output

### shock-deescalation-state

- **path:** `site/live/shock_state.json`
- **declared producer:** `engine/shock_deescalation.py`
- **extra writers:**
  - scripts/build_risk_state.py — intraday fast-path calls build_intraday() site/ only

### signal-archive-track-record

- **path:** `data/signal_archive/track_record.parquet`
- **declared producer:** `engine/track_record.py`
- **extra writers:**
  - scripts/build_track_record.py — CLI runner that calls update_track_record(); additive append

### signal-foundry-lane-status

- **path:** `data/signal_foundry/lane_status.json`
- **declared producer:** `scripts/run_signal_foundry_brainstorm.py`
- **extra writers:**
  - scripts/run_signal_foundry_harness.py
  - scripts/signal_foundry_accrue.py

### site-baskets-json

- **path:** `site/basketdata/baskets.json`
- **declared producer:** `scripts/build_baskets.py`
- **extra writers:**
  - scripts/build_baskets_canada.py — writes canadabasketdata/baskets.json (separate path)
  - scripts/build_baskets_china.py — writes chinabasketdata/baskets.json (separate path)
  - scripts/build_baskets_hk.py — writes hkbasketdata/baskets.json (separate path)
  - scripts/build_baskets_intl.py — writes intlbasketdata/baskets.json (separate path)

### site-github-adoption

- **path:** `site/basketdata/github_adoption.json`
- **declared producer:** `engine/theme_adoption.py`
- **extra writers:**
  - scripts/build_discovery_confluence.py

### site-neuralweb-market-plane

- **path:** `site/neuralwebdata/market_plane.json`
- **declared producer:** `engine/neuralweb/mastermind_context.py`
- **extra writers:**
  - scripts/build_nw_mastermind_context.py — CLI lane; build_and_write() calls build_and_write_market_plane() defined in the producer; no independent write logic

### site-neuralweb-mastermind-context

- **path:** `site/neuralwebdata/mastermind_context.json`
- **declared producer:** `scripts/build_nw_mastermind_context.py`
- **extra writers:**
  - engine/neuralweb/mastermind_context.py — build_and_write() writes both canonical and site copy

### site-phrase-velocity

- **path:** `site/basketdata/phrase_velocity.json`
- **declared producer:** `engine/edgar_phrase_velocity.py`
- **extra writers:**
  - scripts/build_discovery_confluence.py

### site-qledger-track-record

- **path:** `site/qledger/track_record.json`
- **declared producer:** `engine/qledger.py`
- **extra writers:**
  - scripts/grade_qledger.py — reads + merges ladder_states into track_record.json at line 576

### species-registry

- **path:** `data/species/registry.json`
- **declared producer:** `engine/species_registry.py`
- **extra writers:**
  - scripts/backfill_forward_logs.py — additive merge of historical entries

### spine-index

- **path:** `data/neuralweb/spine_index.parquet`
- **declared producer:** `engine/neuralweb/query.py`
- **extra writers:**
  - scripts/build_spine_index.py — thin CLI wrapper; calls write_index() defined in the producer; no independent write logic

### subsector-rotation-snapshots

- **path:** `data/subsector_rotation/snapshots.jsonl`
- **declared producer:** `engine/subsector_track_record.py`
- **extra writers:**
  - scripts/build_subsector_rotation.py — CLI runner; calls compute() then appends snapshot

### trial-ledger

- **path:** `data/trial_ledger.jsonl`
- **declared producer:** `engine/trial_ledger.py`
- **extra writers:**
  - scripts/intl_phase0.py — appends family='intl_bridge' entries

### world-state

- **path:** `data/neuralweb/world_state.json`
- **declared producer:** `engine/neuralweb/world_state.py`
- **extra writers:**
  - scripts/build_world_state.py — thin CLI wrapper; calls build_and_write() which is defined in the producer; no independent write logic
