#!/usr/bin/env bash
# EXTRACTED-VERBATIM-FROM: .github/workflows/daily.yml
# job `engine`, step `run regime engine + build dashboard + daily brief (resilient)`.
# 2026-08-12 512KB processing-cap diet (tests/test_workflow_file_size.py).
# Env comes from the step's `env:` block, which stays in the YAML.
# Invoked as: bash scripts/ci/daily_engine_regime_dashboard.sh
set -e  # mirror GitHub's default `bash -e {0}` step shell — daily.yml declares no shell:

set +e
# Marker for the libraries-rebuild guard further down. The four non-US search
# libraries are each built by their dashboard step (build_china / build_hk /
# build_canada, and build_intl via build_vector) AND again by the resilient rebuild
# step at the end — duplicate per-name analyze() work (~11m/run). Any
# <mkt>stockdata/index.json newer than this marker was (re)built FRESH this run,
# so the rebuild step skips it; a market whose dashboard failed keeps its older
# (pulled) index.json and is still rebuilt. Set BEFORE any builder runs.
touch "$RUNNER_TEMP/engine_libs_marker"
run_py() {
  local label="$1"; local mod="$2"
  echo "::group::$label"
  python -m "$mod" > "$RUNNER_TEMP/step.log" 2>&1; local rc=$?
  cat "$RUNNER_TEMP/step.log"
  echo "::endgroup::"
  if [ "$rc" -ne 0 ]; then
    echo "::error title=$label failed (rc=$rc)::$(tail -n 2 "$RUNNER_TEMP/step.log" | tr '\n' ' ' | tail -c 600)"
    { echo "### ❌ $label failed (rc=$rc)"; echo '<details><summary>traceback</summary>'; echo; echo '```'; tail -n 60 "$RUNNER_TEMP/step.log"; echo '```'; echo '</details>'; } >> "$GITHUB_STEP_SUMMARY"
  fi
}
run_py "regime engine (engine.run)" engine.run
# Shock de-escalation protocol (policy-shock W2-E / D3) — must run AFTER engine.run
# so market_drivers.append_log has written coherence_state to the log.  Writes
# data/reflexes/shock_deescalation/firings.jsonl (keep-first) + site/live/shock_state.json.
# Non-fatal: exits 0 on any error so this can NEVER break the render. PS-R7 guard
# is enforced inside engine.shock_deescalation.build_nightly().
run_py "shock de-escalation (shock_deescalation)" engine.shock_deescalation
# S&P allocation deep-dive (spvector.html) + data/regime/spvector_latest.json,
# BEFORE build_site so the macro page's allocation card reads live numbers.
run_py "S&P allocation vector (build_spvector)" scripts.build_spvector
# Deep-history (2011-2026) leak-free IC scorecard -> data/edgar/ic_scorecard.json, read by
# build_site's factors page. --deep reads the offline deep close panel (data/edgar/
# sue_deep_closes.parquet — gitignored, NOT rebuilt in daily CI); when it is absent the step
# exits WITHOUT writing, keeping the committed deep scorecard rather than clobbering it with a
# shallow ~3y run. Regenerate offline: python -m scripts.sue_deep_phase0 (backfill the panel)
# then python -m scripts.factor_ic_scorecard --deep --start 2011. Additive (never blocks build).
python -m scripts.factor_ic_scorecard --deep || echo "ic scorecard skipped (additive)"
# NOTE: build_factor_series (the ~22-min month-end walk = compute_factors x ~38
# month-ends x 2 universes) was MOVED to its own parallel `factor_series` job
# below — it, NOT residual-alpha, was the real engine bottleneck. build_site reads
# the COMMITTED factor_series.json (degrade-never-raise), so a <=1-run-old series
# is fine and the deep walk no longer gates the daily dashboard/deploy.
# Alt-data desk BEFORE build_site so today's convergence alerts are already in
# data/altdata/alerts.jsonl when build_site assembles the Alert Center. Reads the
# collect job's committed data/quiver/* (no API key needed here); returns 0 on error.
run_py "alternative data desk (build_alt_data)" scripts.build_alt_data
# 13F Smart-Money Trade Tracker — grades curated super-investor 13F moves by
# SPY-relative forward return (engine.manager_trades). Reads the committed
# data/smart_money/* snapshots + the breadth/yahoo price caches; returns 0 on error.
run_py "13F smart-money tracker (build_smart_money)" scripts.build_smart_money
# Policy-Shock W2-F — ARMED/QUIET conditions-arming card (site artifact only, PS-R7).
# Reads CL=F via yahoo store + data/whitehouse/alerts.jsonl (READ ONLY).
# Non-fatal: main() always returns 0; a missing artifact degrades gracefully on the page.
run_py "policy-lever card (build_policy_lever)" scripts.build_policy_lever
# NWS-01 fix: build_news must run BEFORE build_site so that build_site
# renders news.html against the CURRENT macro_releases.json (not the
# previous run's artifact).  build_news is display-tier/leaf (context-only);
# measured 4.3–5.9 min serial wall-time here (W3 re-measure 2026-08-06:
# feeds + DeepSeek enrichment ~2-3m, plus ~2m of GDELT 429 ladder — the
# one arming pass per night that opens gdelt_client's circuit breaker;
# everything after it short-circuits).  Do NOT relocate this into the
# parallel band to chase those minutes — that re-creates the desync'd
# board NWS-01 fixed, for a ~5m saving.  The site no longer ships a
# desync'd board.
# news_calib (grade_news_events) runs immediately after — it writes
# site/news/calibration.json which build_site also reads (W3 side-artifact).
run_py "news suite (build_news)" scripts.build_news
run_py "news event calibration (grade_news_events)" scripts.grade_news_events
# OEU M-FIX (same class as the NWS-01 fix above): MSP W1 data spine must
# run BEFORE build_site, because build_site renders market_structure.html
# from data/market_structure/latest.json. It used to sit in the parallel
# cl_gex band AFTER build_site, so the page was always one generation
# stale — the Weekly Range / gamma / systematic blocks described the
# previous night. Cheap (<10s wall); reads gex_SPX.parquet + _GSPC.parquet,
# both committed by the collect job, so it has no dependency on the band.
# Lane-gated ledger (COLLECT_LANE=nightly) is unaffected by the move.
run_py "MSP W1 — market structure data spine (build_market_structure)" scripts.build_market_structure
# Filing Forensics broad-universe projection — deterministic, display/context only.
# Reads the committed SEC quarterly/annual panels, atomically writes a gitignored
# private state plus public shell/assets, and never fetches network data here. The
# accession-aware raw engine is advanced separately once object storage is bound.
run_py "filing forensics workbench (build_fundamental_forensics)" scripts.build_fundamental_forensics
run_py "macro dashboard + US stocks (build_site)" scripts.build_site
# Ticker dossier pages (v2) — engine-internal, reads fresh site/stockdata/*.json
# written by build_site above; rides the engine "commit engine outputs" git add.
# Non-fatal: ::warning on failure, never aborts the render.
python -m scripts.build_ticker_pages || echo "::warning title=ticker_pages::dossier render failed (non-fatal)"
# Index Leadership rotation board — DEAD-WIRE FIX 2026-07-16: this builder had NO
# workflow caller since its 2026-07-01 hand-run, so site/marketdata/index_leadership.json
# (subsectors.html client fetch + group_context's 0.10-weight rotation source + the
# tolerant readers in build_stock_board_v2 below) froze 15 days stale. SIDECAR FIX
# 2026-08-03: the 07-16 wiring was STILL dead — this comment used to claim the
# subsectorohlc sidecars "are written by build_site's render pass", which is false
# (only build_subsector_confluence's heavy main/main_index entrypoints in the
# parallel band BELOW emit them; the render-lane build/build_nasdaq/build_russell
# never do), so on this job's fresh checkout the gitignored sidecar dirs were empty,
# compute() found zero tabs, and the builder skipped silently for 18 more nightlies
# (snapshots.jsonl frozen at its 2026-06-30 seed). Its inputs are the PREVIOUS
# night's generation: subsector_confluence*.json + regime_timeline.json (committed)
# and the subsectorohlc* sidecars (restored from R2 by the "restore subsector OHLC
# sidecars" step above). Runs AFTER build_site and BEFORE build_stock_board_v2
# (consumer). Reads committed/restored artifacts only — no APIs, no keys.
# COLLECT_LANE=nightly arms its snapshots.jsonl forward-ledger append (the writer
# self-gates per house law; provisional lanes leave the env unset and no-op).
# A skip now exits rc=1 -> run_py raises ::error + a step-summary row.
COLLECT_LANE=nightly run_py "index leadership rotation board (build_index_leadership)" scripts.build_index_leadership
# Buy Board 2.0 — SHADOW (W6-US, us_standouts_v2). AFTER build_site: it REUSES the
# freshly-written factordata/us_standouts.json + setups.json (no recompute, ~0.4s) and
# the rotation artifacts (sector_central / subsector_confluence / index_leadership /
# subsector_rotation / baskets) through tolerant readers. Writes an UNLINKED preview
# (us_stocks_v2.html) + the shadow JSON — nothing live consumes it. main() swallows all
# failures and returns 0, so this can NEVER break the render.
run_py "buy board 2.0 shadow (build_stock_board_v2)" scripts.build_stock_board_v2
# Flow Leaders Desk — BEFORE pick-lab (plab_flow_leader/plab_flow_washout consume
# leaders.json artifact). Reads flow_store/tape_flow/chains/options-entry stores;
# writes site/flowleaders/leaders.json + renders site/flow_leaders.html.
# Display-only; exit 0 always; never breaks the render.
run_py "flow leaders desk (build_flow_leaders)" scripts.build_flow_leaders
# L3 dispersion regime lens — NW Rails W2 PR-4 (§5). Emits data/dispersion/regime.json
# from the breadth close caches (same panel as build_stock_library). Display-only;
# gross_mult_live clamped 1.0. Seconds. build() never raises, but a DEGRADED emit
# (state=null — it overwrites the committed regime.json that leader radar reads
# same-night) now exits rc=1 -> run_py raises ::error + a step-summary row, plus
# bare-print ::warning at each quiet degrade site (the logger-only warnings here
# were invisible to Actions — same silent-skip shape as index_leadership, #4363).
# ORDERING NOTE: moved BEFORE build_leader_radar (LR PR-A Item 8) so that
# regime.json is same-night data when build_leader_radar reads it.
# build_dispersion_regime reads only breadth close caches (no dependency on
# any intervening step between its original position and here).
run_py "L3 dispersion regime lens (build_dispersion_regime)" scripts.build_dispersion_regime
# Leader Radar — LR W2a. AFTER build_flow_leaders + build_dispersion_regime
# (plab_leader_precipice/plab_leader_onset consume radar.json).
# Resolves universe (mag7+AI+Dow-30+NDX ∩ ohlcv); builds/appends
# data/rs_series/<T>.parquet (full-history backfill on first run);
# persists data/leader_radar/state_history.parquet + revisions_history.parquet;
# writes site/leaderradar/radar.json (schema leader_radar.v2).
# Absent stores → honest nulls. Always exits 0; never breaks the render.
# ALSO RUNS IN BOTH EXPRESS RENDER LANES at scope=all (#3612, 2026-07-26) —
# serial post-band, after spine(). The 2026-07-25 "deliberately absent" verdict
# that stood here is DEAD: the two bake-side blockers it named were FIXED in
# #3578, not accepted as risks. (1) pick_lab's _load_radar_json
# (engine/pick_lab/candidates.py) gates radar.json on as_of ==
# data/yahoo/SPY.parquet's data-through — the same anchor this builder derives
# as_of from — so a stale express artifact resolves to [] and express-computed
# fires can never advance the forward pick ledger. (2) Off-nightly,
# built_at/elapsed_s are carried from the committed artifact when the payload is
# otherwise byte-identical, so an untouched rebake commits nothing and the
# dead-man reading of built_at stays honest. (#3578 also added the rs_series lag
# disclosure + the PIT state/fire view caps that make a rebake reproduce the
# nightly bake.) data/ writes stay COLLECT_LANE=nightly-gated (HOUSE-U5) and the
# express lanes commit site/ ONLY, so this nightly remains the sole advancer of
# the radar's forward stores.
# LIVE-VERIFICATION: the 22:30 UTC nightly is NOT the only path to a fresh
# site/leaderradar/radar.json. render.yml's region_of maps both
# scripts/build_leader_radar.py (via scripts/build_*.py) and
# templates/leader_radar.html.j2 (via templates/*) to `all`, and one `all`-mapped
# dirty file forces scope=all — so a leader-radar change always carries its own
# express rebake. engine-render.yml has no scope picker: an engine/** push (e.g.
# engine/leader_lifecycle.py) runs with the default scope=all, which calls
# leaderradar too. Narrow scopes do NOT call it — an unrelated
# scope=china/hk/markets/… render leaves radar.json at its last bake.
run_py "leader radar (build_leader_radar)" scripts.build_leader_radar
# Pick Lab nightly runner — AFTER build_stock_board_v2 (producer-core snapshot already
# written by build_stock_library, which runs inside build_site above). Enriches the
# snapshot from tonight's regime/latest.json, fires all 27 books with refire lockout,
# grades matured picks from the breadth close caches, computes scoreboards, and writes
# site/labdata/pick_lab.json + pick_lab_longhold.json + renders site/us_stocks_lab.html.
# Outputs are covered by the existing `git add data/ site/` commit step.
# main() swallows all failures and returns 0, so this can NEVER break the render.
run_py "pick lab nightly runner (build_pick_lab)" scripts.build_pick_lab
# Options Prophet shadow projection — immediately after Pick Lab so the
# artifact can expose only ledger-admitted plab_flow_leader / flow_washout
# fires. Reuses Flow Leaders ordering; creates no score, direction, contract,
# trajectory, or Macro weight. Missing inputs publish explicit not-ready gates.
run_py "options prophet shadow (build_options_prophet)" scripts.build_options_prophet
# Reflexivity overlay — W4, Signal Commons. Runs AFTER build_stock_board_v2 (reads
# us_standouts_v2.json) and AFTER build_site (reads factor_betas.json). Writes
# site/factordata/reflexivity_overlay.json — display-only duplicate-exposure read.
# returns 0 always, never breaks the render.
run_py "reflexivity overlay (build_reflexivity_overlay)" scripts.build_reflexivity_overlay
# Impulse Tracker — AFTER build_site (a US-stocks sibling page): writes impulse.html +
# factordata/impulse.json from the breadth close/volume caches + the regime read
# (engine.run, above). Reactive early-ignition momentum screen; display/context only.
# Reads only committed/cached data; returns 0 on error so it can never break the site.
run_py "impulse tracker (build_impulse)" scripts.build_impulse
# DT-NW-1: aggregate per-ticker dt_contra chip state into data/neuralweb/dt_contra_state.json.
# AFTER build_site (which calls build_stock_library to write site/stockdata/*.json).
# Display-only NW artifact. Seconds. build() never raises, but an absent/empty
# stockdata dir HERE is a real fault (build_site just wrote it, and the degraded
# JSON empties the committed census) — that now exits rc=1 -> run_py raises
# ::error + a step-summary row, plus bare-print ::warning at each quiet degrade
# site (logger-only warnings are invisible to Actions — #4363 sibling sweep).
run_py "DT-NW-1 dt_contra state aggregator (build_dt_contra_state)" scripts.build_dt_contra_state
# Congressional / politician disclosed-trades desk — AFTER build_alt_data (refreshes
# data/quiver/congress.parquet) + build_site (refreshes per-name stockdata + regime +
# allocation that the watchlist scores against). Reads only committed data; returns 0 on error.
run_py "congressional trades desk (build_congress)" scripts.build_congress
# Odds Desk — historical base-rate analyzer + factor match (research/ODDS_DESK.md).
# Backfills/upserts the data/odds_ohlcv store (yfinance; the preamble's R2 restore
# step materialises it first, so the normal path is a cheap 1mo upsert — the cold
# 119×period="max" backfill runs only when the restore came up empty), recomputes the
# per-ticker factor matrices (site/oddsmatrix -> R2) + site/oddsdata catalog/factor_match
# JSON, and renders odds.html. Display-only; returns 0 on error — never breaks the render.
# DELIBERATELY absent from the render/engine-render express lanes (vetted 2026-07-25):
# it is a network collector every run, its store is gitignored + R2-restored only
# in this job, and its R2 matrices only publish here — see the omission comments in both lanes.
run_py "odds desk (build_odds)" scripts.build_odds
# Technical Lab hub — screener + lab profile page. Reads site/factordata/tech_screener.json
# + tech_lab.json (written by nightly tech signal engine). Falls back to sample fixture if
# absent; returns 0 on error — never breaks the build.
run_py "technical lab hub (build_tech_lab)" scripts.build_tech_lab
# Thematic Foresight Desk — AFTER build_site (regime latest.json carries the
# dislocation entry-overlay) + the engines' bottleneck/revision/demand leaves.
# Reads only committed data; returns 0 on error.
run_py "thematic foresight desk (build_foresight)" scripts.build_foresight
exit 0
