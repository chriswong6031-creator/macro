#!/usr/bin/env bash
# EXTRACTED-VERBATIM-FROM: .github/workflows/daily.yml
# job `engine`, step `commit engine outputs`.
# 2026-08-26 512KB processing-cap headroom diet (tests/test_workflow_file_size.py;
# PR #6499 left ~36 bytes of headroom). Env comes from the step's `env:` block,
# which stays in the YAML.
# Invoked as: bash scripts/ci/daily_engine_commit_outputs.sh
set -e  # mirror GitHub's default `bash -e {0}` step shell — daily.yml declares no shell:

. "${GITHUB_WORKSPACE:-.}/scripts/ci/push_retry.sh"
git config user.name "dashboard-bot"
git config user.email "actions@users.noreply.github.com"
# normalize the EXACT tree this always() commit stages (P0 2026-08-04,
# 9a997e9da3f): the engine job hit its 200m cap at 04:28Z; the cancel skipped
# every success()-gated step INCLUDING the White House step above — the only
# normalize pass in this job — while this always() step still committed 5,895
# raw pages (inline workspace scripts, stale ?v= stamps): 7 shipped-page
# guards red on every PR head in the repo until #4484 re-ran the passes by
# hand. The builders' partial output IS safe to commit ("committing what
# built beats shipping nothing"); a tree the NORMALIZERS never touched is
# not partial output — it is a sitewide regression. All three passes are
# idempotent, ~35s total when the White House step already ran them.
python -m scripts.inject_data_base || echo "data-base shim inject skipped (additive)"
python -m scripts.externalize_css || echo "::warning::pre-commit css externalize FAILED — pages may ship un-externalized (9a997e9da3f)"
python -m scripts.optimize_assets || echo "::warning::asset optimize FAILED — ?v= stamps may be stale"
# pre-commit template↔site re-sync (ui.template_site_sync): the shim/externalize
# step above rewrites the site/ copies of the ~48 templates/-paired plain-copy
# assets, and only the post-rebase --fix in the push loop heals the divergence —
# a cancellation/failure between this commit and that heal ships it (engine-render
# 2026-07-24: run 30057066815 cancelled mid-push-loop landed b6386adb4af, sync gate
# red on every PR until #3358). Heal BEFORE staging so the first commit is never
# diverged; the post-rebase --fix stays for the -X theirs mid-render-merge case.
python -m scripts.check_template_site_sync --fix || true
python3 scripts/check_conflict_markers.py --file site/start.html
# start runtimes single-instance (ui.start_runtime_single_instance): a stale-
# checkout render re-emits doubled live tags with ZERO markers (adad513bdfe),
# so the marker gate above can't see it — heal from HEAD (the last committed
# page, at most one render old) rather than forfeit the whole render.
python3 scripts/check_start_runtime.py --heal-from HEAD
# templates/ too, and ONLY for the plain-copy HTML pairs (index.html, chat.html):
# optimize_assets re-stamps their templates/ side because the --fix above rewrites
# their site copy FROM templates/ — a stamp staged site-only is reverted before it
# reaches main (#3617's fix never reached one returning browser), and staging site/
# alone would land the pair diverged and red the publish gate. Nothing else in the
# build path writes templates/. See render.yml.
# refuse stash/rebase wreckage (2026-08-01 d29e4dd44d: a conflicted
# autostash apply from an earlier push loop in THIS job was staged
# wholesale — 1,704 pages shipped markers)
bash "${GITHUB_WORKSPACE:-.}/scripts/ci/strip_conflict_markers.sh"
bash scripts/ci/options_signal_nightly.sh exclude-broad
bash scripts/ci/options_signal_nightly.sh require-clean-broad-start
git add data/ site/ reports/
# separate + tolerant: `git add site/ templates/` exits 128 when a pathspec
# matches nothing, and this step runs under `-eo pipefail` — a missing
# templates/ would abort the commit and lose the whole render rather than
# just the stamp. Staging site/ keeps its hard-fail semantics.
git add templates/ 2>/dev/null || true
# Prophet has an earlier, provenance-checked SOLE git publisher. Never
# let this broad commit re-stage its local tree: if the checkpoint
# withheld on an off-main/provenance/same-path race, a later `-X theirs`
# engine rebase would otherwise defeat that refusal; even without a
# commit, the always() Pages upload would serve the stale local index.
# Restore HEAD (the known main-ancestry checkout) into both index and
# worktree, unstage every Prophet-owned root, then clean builder-owned
# additions that did not exist in HEAD. Using origin/main
# here would leave an unstaged A->B Prophet delta when main advanced;
# the broad push loop's later autostash/rebase could replay that delta
# over a still-newer correction and a follow-up `git add site/` could
# accidentally commit it. HEAD is deliberately conservative: the
# checkpoint/VPS path carries the new publication, while the Pages
# mirror can serve the prior safe copy for this run. Correction ledgers
# under data/prophet are inputs and are unstaged but never cleaned or
# overwritten here.
if ! git checkout HEAD -- \
  site/prophet \
  data/prophet/ledger.jsonl \
  data/prophet/ledger_quarantine.json \
  data/prophet/origination_receipts \
  data/prophet/legacy_shadow \
  data/prophet_arena \
  data/prophet_stage_shadow; then
  echo "::error title=Prophet safe restore failed::could not restore checkout-time Prophet publications; aborting the broad commit rather than publishing an uncheckpointed tree"
  exit 1
fi
git reset -q -- \
  site/prophet \
  data/prophet \
  data/prophet_arena \
  data/prophet_stage_shadow
# New plan/state/arena files do not exist in the safe ref, so checkout
# cannot remove them. Reset first converts broad-staged additions back
# to untracked files; this scoped clean then removes only those refused
# builder outputs while preserving correction inputs under data/prophet.
git clean -fd -- \
  site/prophet \
  data/prophet_arena \
  data/prophet_stage_shadow
# Refused receipts and legacy-shadow day parts are build-owned and may
# now be untracked after the reset above. Remove only these dedicated
# directories; correction ledgers elsewhere under data/prophet remain
# untouched.
git clean -fd -- \
  data/prophet/origination_receipts \
  data/prophet/legacy_shadow
# Re-exclude both exact-published namespaces after the broad add.
bash scripts/ci/options_signal_nightly.sh exclude-broad
# W0b (2026-07-08 stale-HK incident): US engine job must NOT commit asia-owned
# data/ paths — asia-close.yml is the sole writer of all china*/hk* stores.
# The GHA cache restore above (data/hk_stocks, restore-keys: hk-stocks-ohlc-)
# can overlay stale parquets on top of what asia-close committed; combined with
# -X theirs on the rebase-push, the US job would overwrite fresh HK data with
# its stale checkout-time copy.  Unstage all asia-owned paths immediately after
# the broad git add so they are never included in the engine commit.
# Path derivation: asia group = adapters starting with `china` or `hk`
# (scripts/collect.py group_members); data/hkma adapter key `hkma` also starts
# with `hk`.  US fallback builders (build_vector: baskets_china/hk idempotent
# by as_of) write data/ only when asia lane skipped — those writes ride inside
# data/china_* / data/hk_* so they are protected by asia-close on normal runs
# and correctly excluded here on a fallback run (no double-commit hazard since
# asia-close won't push a commit for those paths on a fallback day).
git reset -q -- data/hk data/hk_* data/hkma data/china data/china_* 2>/dev/null || true
# W6b per-lane push dedup ledgers: covered by 'git add data/' above since
# data/alert_triage/ is under data/. Explicit add as staging-law documentation:
# basket_freeze lane (single-writer: engine/basket_freeze.py),
# signal_sanity lane (single-writer: scripts/signal_sanity.py),
# healthcheck lane (single-writer: scripts/healthcheck.py).
# SENTINEL STAGING LAW: all three per-lane JSONL paths are synapse-registered
# (ops-push-basket-freeze, ops-push-signal-sanity, ops-push-healthcheck).
git add data/alert_triage/ 2>/dev/null || true
# SA-R15: US pick-lab ledgers — fires.jsonl, grades.jsonl, monthly snapshot
# parquets. These are runner-local today (CN's equivalents are committed).
# Force-add so they ride the engine commit and are visible to the off-render
# standout_audit_us job (which reads committed stores only, SA-R15).
git add data/pick_lab/fires.jsonl 2>/dev/null || true
git add data/pick_lab/grades.jsonl 2>/dev/null || true
git add data/pick_lab/etf_closes.parquet 2>/dev/null || true
# m1 fix: long-hold ledgers written by engine/pick_lab/profile.py:186-190
git add data/pick_lab/lh_fires.jsonl 2>/dev/null || true
git add data/pick_lab/lh_grades.jsonl 2>/dev/null || true
git add data/pick_lab/snapshots/ 2>/dev/null || true
# LLM stock briefs (site/stockbrief) are gitignored for local-dev cleanliness
# but must be TRACKED on main so the committed-tree deploy (pages.yml) ships
# them — same as the force-tracked stock-search libraries. -f overrides the
# ignore; || true so an empty/absent dir (feature off) never fails the commit.
git add -f site/stockbrief 2>/dev/null || true
# FTR W10: persist nightly dedup state so the first intraday tick of the same day
# does not double-fire an IGNITION/shock alert that the nightly already sent.
# notify_state.json is site/live/ (gitignored); force-add with || true so an
# absent file (no alert fired, dark mode) never fails the commit.
git add -f site/live/notify_state.json 2>/dev/null || true
# China stock-search library: gitignored like the other markets' libraries —
# force-add it so the committed-tree deploy ships every indexed A-share detail
# JSON, not just the old tracked subset.
# Canada stock-search library: gitignored like the other markets' libraries,
# but (unlike them) force-added here so the committed-tree deploy ships it —
# otherwise canada_stock.html's search 404s on canadastockdata/index.json.
# International stock-search library: same gitignore situation — force-add so
# the committed-tree deploy ships it (else intl_stock.html search 404s).
# US stock-search library (built by build_site -> build_stock_library): only a
# ~534-name legacy subset was ever tracked while the index lists ~1595, so the
# untracked long tail 404'd on click. Force-add the whole dir so every name ships.
# Bespoke single-stock chart OHLC (built by build_site -> build_chart_data):
# gitignored like the search libraries, so force-add it or the committed-tree
# deploy ships no price data and every stock chart renders empty.
# Non-US bespoke chart OHLC (built by build_{china,canada,intl}_library): same
# gitignore + force-add situation as their stockdata libraries. HK now also ships
# reconstructed candles (build_hk_library -> build_chart_data.build_hk -> site/hkohlc),
# imputed from its close-only per-stock JSON so the chart draws candlesticks.
# US 4H intraday chart data (built by build_site -> build_chart_data.emit_intraday
# from the cached data/intraday) — gitignored, force-add so the deploy ships it.
if git diff --cached --quiet; then echo "no engine output changes"; exit 0; fi
# Fail-closed conflict gate (P0 2026-08-01, d29e4dd44d / #4167): a conflicted
# autostash apply anywhere upstream of this step leaves `Updated upstream /
# Stashed changes` blocks that the broad `git add` above stages VERBATIM —
# 1,707 pages reached main exactly that way. push_staged_heal restores
# display-tier offenders (site/, templates/, reports/) wholesale from HEAD
# (same restore semantic as #4167) and FAILS CLOSED on ledger-tier data/
# offenders or a still-dirty re-scan — sweeping the polluted files from the
# tree first, because the Pages artifact upload below runs on always() and
# must never ship marker bytes.
if ! push_staged_heal data/ site/ reports/ templates/; then
  exit 1
fi
if git diff --cached --quiet; then echo "no engine output changes after conflict heal"; exit 0; fi
bash scripts/ci/options_signal_nightly.sh commit-broad-candidate \
  "engine: regime update $(date -u +%F)"
# best-effort push (see commit-data). The deploy below uses the uploaded
# artifact, so it never depends on this commit landing.
PUSH_ALARM=420
PUSH_BUDGET_SECS=600   # a dropped push here costs the nightly's forward-ledger DAY (sole-advancer law) — worth waiting 10 min for the ref
PUSH_MAX_ATTEMPTS=20   # let the 600s DEADLINE stop this loop, not the attempt count: 10 contention
                       # retries burn only ~2 min, so the raised budget above would never bind
push_retry_init "engine outputs"
while push_attempt; do
  # Fetch the exact named ref before rebasing. The shared helper sees normal
  # AND ignored untracked collisions, quarantines only paths tracked by that
  # exact target under RUNNER_TEMP, and never removes unrelated runner data.
  if ! push_fetch_main_for_rebase; then
    push_abort_rebase
    push_backoff
    continue
  fi
  # rename/rename on content-hashed site/assets/css/* is deterministic across
  # retries (path conflict; -X theirs can't settle it — 2026-07-22 asia-close
  # run 29904079071 dropped a day's outputs this way). The autoresolver keeps
  # both sides' hashed files (next externalize_css prunes the orphan) and
  # finishes the rebase; anything else is left for the abort+retry below.
  if { perl -e 'alarm 420; exec @ARGV or die' -- git rebase --autostash -X theirs origin/main || bash scripts/rebase_autoresolve_hashed_css.sh; } && push_autostash_ok; then
    # post-rebase template↔site re-sync (ui.template_site_sync): -X theirs can
    # resurrect this run's checkout-time template copies over a reword that merged
    # mid-nightly (2026-07-07: engine-render commit 2ae709f9f0 reverted #1793's
    # site-side de-escalation in sector_cycles.js this way). templates/ is now
    # fresh post-rebase main — re-copy and fold any delta into a follow-up commit.
    # re-shim + re-externalize POST-rebase (P0 2026-08-04, 9a997e9da3f): the
    # rebase can inherit RAW pages from main — a cancelled nightly's always()
    # commit shipped 5,895 un-normalized pages, and every later lane's replay
    # merged its small deltas INTO those fat pages (clean merge, no conflict,
    # so -X theirs never engaged) while its re-stamp-only heal pushed the
    # poison onward re-stamped. Running the FULL normalize chain here makes
    # the next lane push self-heal the whole tree instead. Same order as the
    # normalizer step: shim → externalize → stamp; all idempotent.
    python -m scripts.inject_data_base || echo "data-base shim inject skipped (additive)"
    python -m scripts.externalize_css || echo "::warning::post-rebase css externalize FAILED — inherited raw pages stay un-externalized (9a997e9da3f)"
    # re-stamp POST-rebase (ui.asset_stamp): the tree this loop PUSHES is not the tree
    # the normalizer step stamped — pages a sibling lane lands mid-run arrive here
    # un-stamped and unseen by that pass (2026-07-26 render 6260e5ac8c0 shipped
    # site/us_track_record.html with a bare `theme.css` this way). Idempotent, ~11s over
    # 3.2k pages, and BEFORE the --fix so the pairs heal from a re-stamped templates/.
    python -m scripts.optimize_assets || echo "::warning::post-rebase asset optimize FAILED — ?v= stamps may be stale"
    python -m scripts.check_template_site_sync --fix || true
    # ms-board coherence guard (ui.ms_board_coherence): -X theirs resolves whole
    # conflict REGIONS toward this run's replayed render, so racing a mid-nightly
    # render can stitch a hybrid Market State board (2026-07-07: commit 5bf116a3b3
    # baked upstream's score 56/"Mixed" beside a stale "Risk Radar forces
    # Risk-off." note). Restore any incoherent page WHOLESALE from post-rebase
    # origin/main (coherent, at most one render old).
    python3 scripts/check_ms_board_coherence.py --heal-from origin/main \
      || echo "::warning::ms-board coherence heal incomplete (incoherent board may predate this run)"
    # refuse stash/rebase wreckage (2026-08-01 d29e4dd44d: a conflicted
    # autostash apply was staged wholesale — 1,704 pages shipped markers)
    bash "${GITHUB_WORKSPACE:-.}/scripts/ci/strip_conflict_markers.sh"
    python3 scripts/check_conflict_markers.py --file site/start.html
    python3 scripts/check_start_runtime.py --heal-from origin/main
    if ! git diff --quiet -- site/ templates/; then
      # push_staged_clean: never bake conflict markers into the follow-up
      # commit (P0 d29e4dd44d/#4167). On a dirty scan: unstage and push the
      # guarded engine commit alone — same forfeit as a failed render-sync.
      git add site/
      git add templates/ 2>/dev/null || true
      if push_staged_clean site/ templates/; then
        bash scripts/ci/options_signal_nightly.sh commit-render-sync \
          "render-sync: post-rebase guards (template re-copy + ms-board coherence)" \
          || echo "::warning::render-sync commit failed (non-fatal — pages publish gate backstops divergence)"
      else
        git reset -q -- site/ templates/ || true
        # restore the offenders' worktree bytes too — the always()
        # Pages artifact below ships the WORKING TREE, not the commit
        # (word-split is safe: no tracked path contains whitespace)
        for f in $PUSH_STAGED_OFFENDERS; do git checkout HEAD -- "$f" 2>/dev/null || true; done
        echo "::warning title=render-sync skipped::post-rebase site/templates scanned dirty (conflict markers) — follow-up commit skipped and offenders restored from HEAD; pushing the guarded engine commit only"
      fi
    fi
    if push_do; then echo "pushed engine outputs on attempt $PUSH_ATTEMPT"; push_won; exit 0; fi
  fi
  push_abort_rebase
  push_backoff
done
push_lost
# A lost runner-only commit must turn the run red. Every remaining engine
# delivery step and every downstream job that needs engine uses always(),
# so Pages/R2/off-render delivery still runs after this failure.
echo "::error title=nightly engine outputs NOT pushed::$PUSH_ATTEMPT rebase/push attempts failed ($PUSH_STOP) — the nightly's data/ forward ledgers + rendered site/ exist only on this runner and are lost at the next checkout (the LEDGER DAY does not advance and the VPS/origin deploy does not get this render; the Pages-artifact fallback was retired pre-private-cutover). See scripts/rebase_autoresolve_hashed_css.sh."
echo "### ❌ nightly engine outputs NOT pushed after $PUSH_ATTEMPT attempts ($PUSH_STOP) — forward-ledger day at risk (no Pages-artifact fallback anymore)" >> "$GITHUB_STEP_SUMMARY"
exit 1
