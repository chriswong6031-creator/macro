#!/usr/bin/env bash
# EXTRACTED-VERBATIM-FROM: .github/workflows/daily.yml
# job `engine`, step `regional + desk builders (parallelised — independent clusters, barrier before the hub)`.
# 2026-08-12 512KB processing-cap diet (tests/test_workflow_file_size.py).
# Env comes from the step's `env:` block, which stays in the YAML.
# Invoked as: bash scripts/ci/daily_engine_regional_desk_builders.sh scripts.check_theme_graph_contracts
set -e  # mirror GitHub's default `bash -e {0}` step shell — daily.yml declares no shell:

THEME_GRAPH_GUARD_MODULE="scripts.check_theme_graph_contracts"
if [ "${1:-}" != "$THEME_GRAPH_GUARD_MODULE" ] || [ "$#" -ne 1 ]; then
  echo "::error title=regional builder wiring::expected the exact theme-graph guard module argument" >&2
  exit 2
fi

set +e
ART="$RUNNER_TEMP/band"; rm -rf "$ART"; mkdir -p "$ART"
# brun <slug> <label> <module> [args…] — run one builder resiliently into its
# OWN scratch files (never shared across the parallel subshells), recording the
# exit code + wall-seconds. Output (incl. stderr) is buffered, replayed later.
brun() {
  local slug="$1" label="$2" mod="$3"; shift 3
  local t0 t1 rc
  t0=$(date +%s)
  { echo "$label"; python -m "$mod" "$@" 2>&1; } > "$ART/$slug.log"; rc=$?
  t1=$(date +%s)
  echo "$rc"          > "$ART/$slug.rc"
  echo "$((t1 - t0))" > "$ART/$slug.sec"
}
# --- clusters: each internally ORDERED by its data deps; clusters mutually independent ---
cl_markets() {
  brun commodities  "build commodity vector (build_commodities)"         scripts.build_commodities
  brun spr          "build strategic reserves (build_spr)"               scripts.build_spr
  brun forex        "build forex vector (build_forex)"                   scripts.build_forex
  brun bonds        "build bonds & bond-health (build_bonds)"            scripts.build_bonds
  brun crossasset   "cross-asset vector (build_crossasset)"              scripts.build_crossasset
  brun transmission "rate & inflation transmission (build_transmission)" scripts.build_transmission
  # TXI W1: staged-cascade chain episode tracker. Runs AFTER build_transmission
  # (reads data/transmission/latest.json + forex/regime latest.json + the parquet
  # store). Display-only; nightly is the sole advancer of chain_episodes.jsonl.
  # Cheap (<10s wall). No-ops gracefully when upstream artifacts are absent.
  brun transmission_chains "TXI W1 — transmission chain episodes (run_transmission_chains)" scripts.run_transmission_chains
  brun discovery    "discovery leaderboard (build_discovery)"            scripts.build_discovery
}
# cl_china / cl_hk MOVED to .github/workflows/asia-close.yml — rebuilt after the
# Asia cash close (~08:30 UTC) so CN/HK render SETTLED marks, not the stale ones a
# US-evening run would lock in. They are self-recomputing (no US-regime dependency).
cl_gex() {
  brun gex_board    "GEX magnets board (build_gex_board)"        scripts.build_gex_board
  brun vol_regime   "index vol-regime (build_vol_regime)"        scripts.build_vol_regime
  # build_market_structure MOVED OUT of this band to just BEFORE build_site
  # (OEU M-FIX). It ran here, i.e. AFTER build_site had already rendered
  # market_structure.html from build_site.py's MSP block — so the page
  # always shipped the PREVIOUS run's data/market_structure/latest.json.
  # Its only inputs (data/cboe/gex_SPX.parquet, data/yahoo/_GSPC.parquet)
  # come from the collect job, so nothing in this band feeds it.
  # W4 EVW: event-window snapshot + forward-log stamp (RIC program, P3).
  # Runs AFTER vol_regime so site/vol/regime.json (gamma_regime proxy) is present.
  # No ThetaData reads; cheap committed-artifact join (~15s wall).
  brun event_windows "W4 EVW — event-window calendar (build_event_windows)" scripts.build_event_windows
  brun darkpool     "dark pool desk (build_darkpool_desk)"        scripts.build_darkpool_desk
  brun options_flow "options flow desk (build_options_flow)"     scripts.build_options_flow
  brun flow_desk    "group flow heatmap & market tide (build_flow_desk)" scripts.build_flow_desk
  brun options_skew "single-name IV skew (build_options_skew)"   scripts.build_options_skew
  brun options_ivspread "single-name IV spread (build_options_ivspread)" scripts.build_options_ivspread
  # AFTER skew+ivspread: it joins both ledgers into the neutralised feature panel.
  brun options_dislocation "options information-dislocation panel (build_options_dislocation)" scripts.build_options_dislocation
  brun options_screener "US options screener page (build_options_screener)" scripts.build_options_screener
  brun options_entry "options entry state fusion table (build_options_entry_state)" scripts.build_options_entry_state
  brun intraday_flow "intraday flow tracker nightly base (build_intraday_flow)" scripts.build_intraday_flow --mode nightly
}
cl_baskets() {
  brun baskets     "thematic baskets (build_baskets)"        scripts.build_baskets
  # GMI W1a: point-in-time US basket membership. data/baskets/membership.json is a
  # single MUTABLE document and basket_freeze stores only membership HASHES, so
  # before this there was no way to answer "who was in this basket on that date"
  # for the US suite at all. Content-deduped (a dated side-car only when membership
  # changed) + keep-first in the parquet, so a re-run is a no-op; the cadence stamp
  # is rewritten every run so a deduping writer and an unwired one look different
  # on disk. NIGHTLY ONLY — the PIT store is append-only and keep-FIRST per
  # snapshot_date, so whoever stamps a date owns it forever (COLLECT_LANE=nightly,
  # job-level env above, is the fail-closed gate). Deliberately NOT added to
  # closing-bell / earlyclose / engine-render / render: those are data/-discarding
  # lanes and nightly is the sole advancer.
  brun baskets_snapshot "US basket membership snapshot (build_baskets --snapshot)" scripts.build_baskets --snapshot
  # GMI W1b: the theme-graph semantic spine (nodes/edges/evidence). Runs AFTER
  # baskets_snapshot because it materializes from the membership documents that
  # step has just stamped, so tonight's graph describes tonight's membership.
  # Nightly diff mode: it recomputes the view and appends ONLY what changed,
  # era=observed, belief_time=today. NIGHTLY ONLY for the same reason as the
  # snapshot above — the store is append-only and bitemporal, and
  # COLLECT_LANE=nightly (job-level env) is the fail-closed gate; render,
  # closing-bell and earlyclose leave it unset and so compute and discard.
  # The guard follows immediately and is ADVISORY here (rc 0 on a breach, one
  # ::warning): the plane is display-tier with all six authority booleans
  # false, so a contract breach must not take the collect lane down. CI runs
  # the same guard with --strict.
  brun theme_graph "theme graph nightly materialization (build_theme_graph)" scripts.build_theme_graph
  brun theme_graph_guard "theme graph contract guard (check_theme_graph_contracts)" "$THEME_GRAPH_GUARD_MODULE"
  brun subsector_conf "subsector confluence desk + double-gated funnel (build_subsector_confluence)" scripts.build_subsector_confluence
  brun subsector_conf_ndx "nasdaq-100 subsector confluence desk (build_subsector_confluence --nasdaq)" scripts.build_subsector_confluence --nasdaq
  brun subsector_conf_rut "russell-2000 subsector confluence desk (build_subsector_confluence --russell)" scripts.build_subsector_confluence --russell
  # W0.4 Setup-Species: cohort-context metrics (display-only; reads committed subsector_confluence.json)
  brun cohort_metrics "W0.4 cohort metrics — peer washout/reclaim/MACD-turn + Rubber-Band Score (build_cohort_metrics)" scripts.build_cohort_metrics
  # Blocked-entry override A1b, RATIFIED @25% (prereg §5 / RATIFICATION_PACKET §4):
  # peer-median 252d drawdown per thematic basket + the per-name lookup, so a surface
  # can show the SAME number the study graded on. Display-tier support only — the live
  # enter-mask conditional stays behind its own two gates (production-feed re-grade +
  # signal-era fence). ~5s: reads only the names it needs, one close column each.
  brun basket_washout "blocked-entry basket washout state (build_basket_washout_state)" scripts.build_basket_washout_state
  # Rotation Command W1 (RC-R1/R6): first-class rotation events + sector-fragmentation board (display-only)
  brun rotation_events "Rotation Command W1 — rotation events + sector fragmentation (build_rotation_events)" scripts.build_rotation_events
  # RLT-R2 Rebalance Pulse: mechanical volume day-classifier (display/context, off render path)
  brun rebalance_pulse "RLT-R2 rebalance pulse — calendar × volume classifier (build_rebalance_pulse)" scripts.build_rebalance_pulse
  # build_news + news_calib moved BEFORE build_site (NWS-01 fix — see above)
  brun methodology "methodology page (build_methodology)"    scripts.build_methodology
  brun nasdaq_internals "nasdaq-100 archetype-group internals (build_nasdaq_internals)" scripts.build_nasdaq_internals
}
cl_special() { brun special "special situations desk (build_special_situations)" scripts.build_special_situations; }
cl_stage() {
  # SGA W1 (research/STAGE_ANALYSIS_MASTERPLAN.md): Weinstein stage engine over
  # the ~2.8k-name baskets/ohlcv ∪ SP1500 universe (~10 min at 4 cores), hidden
  # under the special-sits cluster's ~28-min ceiling — zero critical-path cost.
  # Reads TONIGHT's signal_gate.json (build_site above) for the T-tier chip and
  # joins earnings-call scores fetched from R2 (fail-open: absent scores just
  # print the plain-word null). Page renders from the fresh context artifact.
  python -m scripts.fetch_earnings_scores || echo "::warning title=fetch_earnings_scores::rc≠0 (non-fatal — earnings context absent this render)"
  brun stage_analysis "Stage Analysis context engine (build_stage_analysis)" scripts.build_stage_analysis
  brun stage_analysis_page "Stage Analysis page (build_stage_analysis_page)" scripts.build_stage_analysis_page
  # TOP ANATOMY W1 (research/TOP_ANATOMY_MASTERPLAN_BY_FABLE.md §5-W1):
  # Winner Health — the nightly maturation read over the massive_stock_day
  # tape, display tier with zero authority. Data builder FIRST (it writes
  # data/top_maturation/latest.json and advances the forward log), page
  # builder second (pure SSR from that artifact). Both fail-open: a bad
  # read writes a null_state artifact and the page renders its designed
  # warming-up state rather than failing the band. The panel is
  # incrementally cached under data/top_maturation/_panel_cache/
  # (gitignored), so only source files the store actually touched are
  # re-read. Engine is daily-only — nightly is the sole ledger advancer.
  brun top_maturation "Winner Health context engine (build_top_maturation)" scripts.build_top_maturation
  brun winner_health_page "Winner Health page (build_winner_health_page)" scripts.build_winner_health_page
}
cl_misc() {
  brun seasonality   "factor seasonality (build_seasonality)"      scripts.build_seasonality
  brun stock_seasonality_page "stock seasonality page (build_stock_seasonality_page)" scripts.build_stock_seasonality_page
  brun reports       "research reports section (build_reports)"     scripts.build_reports
  brun research_vault "research vault page (build_research_vault)"   scripts.build_research_vault
  brun cycle         "cycle intelligence page (build_cycle)"        scripts.build_cycle
  brun sectorcyc     "sector cycle intelligence (build_sector_cycles)" scripts.build_sector_cycles
  brun countrycyc    "country cycle intelligence (build_country_cycles)" scripts.build_country_cycles
  # markets_engine.js is a pure splice of country_cycles.json, so it must re-run
  # whenever countrycyc does — otherwise markets.html freezes on the previous
  # vintage and the cycle-consistency PR gate fails on same-tape pos/phase skew
  # (render.yml already pairs them; cl_misc is sequential so ordering holds).
  brun markets       "global market cycles shell (build_markets)"    scripts.build_markets
  brun sync_gauge    "sync gauge appender (append_sync_gauge)"      scripts.append_sync_gauge
  brun policy_intent "policy intent desk (policy_intent_desk)"      engine.policy_intent_desk
  brun policy_watch  "fed & policy watch (build_policy_watch)"      scripts.build_policy_watch
  brun index_changes "S&P index changes (build_index_changes)"     scripts.build_index_changes
  # CPI P2: live-view rebuild runs LAST in cl_misc so today's forward-log stamps
  # from build_sector_cycles and build_country_cycles (both above) are present.
  # Placement inside cl_misc (not post-band) is intentional: the dependency is
  # only on these two intra-cluster steps; the band barrier would be correct but
  # wastes the ~28-min special-situations wait. cl_misc is fully sequential so
  # the ordering guarantee holds without any additional wait.
  brun cycle_pattern_live "CPI live-view adapter (build_cycle_pattern_live)" scripts.build_cycle_pattern_live
  # CPI P6: the NW adapter artifact compacts the live view + hazard gate
  # ledger + truth registry, so it runs AFTER cycle_pattern_live (sequential
  # within cl_misc — same ordering guarantee as the live-view step above).
  brun cycle_pattern_state "CPI NW adapter (build_cycle_pattern_state)" scripts.build_cycle_pattern_state
  # Stock seasonality calendar clock (research/STOCK_SEASONALITY_LANE2_DESIGN_SPEC.md).
  # DAILY-ONLY and LAST in cl_misc: the 2645-window family and its independent
  # circular year-shift null (B=2000, raw + market-neutral) are the heavy leg, and
  # the render budget is law. The null is cached against the complete-year panel
  # hash, so a normal night is a panel re-fold plus a JSON rewrite (~1 min) and the
  # full recompute lands once a year when the panels roll over. Per-symbol entity
  # JSON is gitignored and rides the R2 publish below; index/methodology are the
  # committed half.
  brun stock_seasonality "stock seasonality calendar clock (build_stock_seasonality)" scripts.build_stock_seasonality
  brun biopharma_seasonality "seasonality methodology manifest (build_biopharma_seasonality)" scripts.build_biopharma_seasonality
  # Lane 6 shadow lobe + the SOLE nightly advancer of its forward ledger.
  # Must stay in this sequential cluster AFTER build_stock_seasonality: it
  # reads the fresh entity JSONs from the working tree, and those are
  # gitignored except SPY, so no other lane can supply them. Sub-minute —
  # it only reads artifacts (28 symbols, one baseline sweep each).
  brun seasonality_shadow "Lane 6 NW shadow state + forward ledger (build_seasonality_shadow_state)" scripts.build_seasonality_shadow_state
  # Measurement hub — moved AFTER seasonality_shadow (2026-08-07). It now
  # renders the seasonal forward-record line from
  # data/seasonality/nw_forward_ledger.jsonl, and seasonality_shadow is that
  # ledger's SOLE nightly advancer. Built earlier in this sequential cluster,
  # the public page carried the PREVIOUS night's counts: on the night the first
  # window is scored, measurement.html would still say "0 scored so far" for
  # another 24h while the same night's program_watch.json said otherwise — two
  # readings of one ledger disagreeing on the same commit. Nothing later in
  # cl_misc consumed measurement's outputs, so this is a pure ordering move; the
  # side effect is that measurement now reads the night's own sync gauge and
  # cycle-pattern artifacts instead of yesterday's, which is the same direction
  # of fix.
  brun measurement   "cycle measurement hub (build_measurement)"    scripts.build_measurement
  # Program watch — LAST in the seasonality run because it reads what the
  # two builders above just wrote (the forward ledger counts in
  # particular); earlier, it would report the PREVIOUS night's ledger.
  # Pure stdlib, sub-second: one JSON write plus a ::notice per fired
  # tripwire. Fail-open — it never takes the nightly down.
  brun program_watch "seasonality program watch (build_program_watch)" scripts.build_program_watch
}
# launch every cluster concurrently, then barrier before the hub (build_vector, below)
cl_markets & cl_gex & cl_baskets & cl_special & cl_misc & cl_stage &
wait
# --- replay each builder's output GROUPED + in a stable order (post-barrier, so
#     nothing interleaves), surface failures as annotations, summarise wall-times ---
# transmission_chains added 2026-07-25: it was brun'd at :1133 but absent
# here, and this loop is what prints a builder's log + raises its rc!=0
# ::error. Milder here than in the render lanes (this lane also runs
# check_builder_failstreaks, which globs *.rc and so catches a >=2-night
# streak regardless of ORDER) — but a FIRST failure still passed silently,
# with no log and no step-summary line for the TXI W1 chain tracker.
ORDER="commodities spr forex bonds crossasset transmission transmission_chains discovery gex_board vol_regime market_structure event_windows darkpool options_flow flow_desk options_skew options_ivspread options_dislocation options_screener options_entry intraday_flow baskets baskets_snapshot theme_graph theme_graph_guard subsector_conf subsector_conf_ndx subsector_conf_rut cohort_metrics basket_washout rotation_events rebalance_pulse methodology nasdaq_internals seasonality reports research_vault cycle sectorcyc countrycyc markets measurement sync_gauge policy_intent policy_watch special index_changes cycle_pattern_live cycle_pattern_state stock_seasonality stock_seasonality_page biopharma_seasonality seasonality_shadow program_watch stage_analysis stage_analysis_page top_maturation winner_health_page"
echo "### ⏱ parallel band — per-builder wall-time" >> "$GITHUB_STEP_SUMMARY"
for slug in $ORDER; do
  [ -f "$ART/$slug.log" ] || continue
  label=$(head -n1 "$ART/$slug.log")
  rc=$(cat "$ART/$slug.rc" 2>/dev/null || echo "?")
  sec=$(cat "$ART/$slug.sec" 2>/dev/null || echo "?")
  echo "::group::$label  [${sec}s, rc=$rc]"
  tail -n +2 "$ART/$slug.log"
  echo "::endgroup::"
  echo "- ${label} — ${sec}s (rc=${rc})" >> "$GITHUB_STEP_SUMMARY"
  if [ "$rc" != "0" ] && [ "$rc" != "?" ]; then
    echo "::error title=${label} failed (rc=${rc})::$(tail -n 2 "$ART/$slug.log" | tr '\n' ' ' | tail -c 600)"
    { echo "### ❌ ${label} failed (rc=${rc})"; echo '<details><summary>traceback</summary>'; echo; echo '```'; tail -n 40 "$ART/$slug.log"; echo '```'; echo '</details>'; } >> "$GITHUB_STEP_SUMMARY"
  fi
done
exit 0
