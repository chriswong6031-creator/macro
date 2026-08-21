---
workstream: "WS:BIOCATALYST-CORE-PRODUCT"
session: claude/biocatalyst-p1-1-catalyst-radar
model: fable
ended_because: complete
mission: >
  Wave P1-1 — turn the existing Milestones experience into Catalyst Radar —
  Trial Milestones: pointer-bound CT.gov truth to deterministic milestone-event
  projection, reviewed sponsor attribution with typed identity absence, one
  entitled Radar API, glance-tier rows, revision/evidence expansion, and
  production-shaped browser proof. Implementation PR only; no merge — returned
  to Sol for adversarial review per the P1-0R stop-for-review charter.
state_before: >
  P0 was PROVEN_LIVE but cohort-limited (4 NCTs). The Milestones tab was a
  lawful-empty monitor whose own docstring declared it "deliberately not a
  catalyst calendar". No catalyst-event projection module existed; no radar
  endpoint existed; sponsor attribution stopped at ticker with no consumer.
changed:
  - path: engine/biocatalyst/catalyst_events.py
    what: >
      New pure request-local projection. Source-native ids nct:<NCT>:<kind>;
      honest date precision (day/month/year intervals, never a fake point
      estimate); total timing classification (occurred/current/upcoming/
      beyond_horizon) with overlap semantics on all three live branches; exact
      trial-status preservation (SUSPENDED is paused, never terminal); typed
      issuer absence; revision lineage with predecessor pointers; public-safe
      pointer-bound evidence via a key allowlist. No score, probability,
      materiality, rank, confidence, weight, or composite anywhere.
  - path: app/biocatalyst.py
    what: >
      New entitled GET /api/biocatalyst/v1/catalyst-radar through the existing
      seam (require_site_full_user, request-local _read_bundle, _meta envelope,
      private no-store headers, generation-and-query-bound cursor with its own
      domain). Sponsor map loaded at most once per request inside try/except so
      a map failure degrades every row to sponsor_map_unavailable and never
      503s. Revision lineage read from projection.change_tapes_by_nct — already
      in memory from the same _read_bundle() call, zero extra I/O.
  - path: templates/biocatalyst.js
    what: >
      Milestones mode graduated in place into Catalyst Radar. Glance tier, group
      segmentation, evidence drill-down through the existing inspector drawer,
      EN/ZH, honest denominators. Dead MILESTONE_API/MILESTONE_WINDOWS removed.
  - path: templates/biocatalyst.html.j2
    what: Tab label, queue title, registry-date select gains "All milestones".
  - path: templates/biocatalyst.css
    what: Radar row, group, issuer/status/revision chip classes.
  - path: site/biocatalyst.js
    what: Byte-identical paired plain-copy asset.
  - path: site/biocatalyst.css
    what: Byte-identical paired plain-copy asset.
  - path: tests/test_biocatalyst_catalyst_radar.py
    what: New engine suite incl. the frozen four-NCT acceptance arithmetic.
  - path: tests/test_biocatalyst_catalyst_radar_api.py
    what: New endpoint/entitlement/no-score/evidence-safety/UI-contract suite.
  - path: tests/test_biocatalyst_hydration.py
    what: >
      Fixtures retargeted from the retired /trials/milestones envelope to
      catalyst_radar/effective_horizon. No assertion weakened; the harness
      tests/biocatalyst_hydration_harness.js was NOT edited.
  - path: tests/test_biocatalyst_page.py
    what: Three fossil source-text pins retargeted to live behavior.
  - path: .github/ci/legacy-jobs.yml
    what: >
      Both new suites registered in biocatalyst-serving (gate: code, on the
      merge gate), plus templates/biocatalyst.html.j2, templates/biocatalyst.css
      and site/biocatalyst.css added to its curated scope so the wording guard
      cannot go dark.
verified:
  - claim: The engine + API + page + UI + hydration suites all pass.
    command: "python3 -m pytest tests/test_biocatalyst_catalyst_radar.py tests/test_biocatalyst_catalyst_radar_api.py tests/test_biocatalyst_page.py tests/test_biocatalyst_d0b_ui.py tests/test_biocatalyst_hydration.py -q"
    result: "100 passed, 4 warnings in 55.89s"
  - claim: The rest of the biocatalyst-serving command is unregressed.
    command: "python3 -m pytest tests/test_biocatalyst_api.py tests/test_biocatalyst_peer_api_contract.py tests/test_biocatalyst_deploy.py -q"
    result: "171 passed, 9 warnings in 249.83s — zero failures, zero new errors"
  - claim: >
      The real app over a genuinely published generation carrying the four real
      cohort NCTs returns the frozen acceptance arithmetic — 4 rows at
      next_365d (3 upcoming + 1 occurred), 2 at next_180d, 4 beyond horizon.
    command: "curl -s http://127.0.0.1:8977/api/biocatalyst/v1/catalyst-radar (real app.main:app, real worker-published generation, anchor 2026-08-20)"
    result: "HTTP 200 in 0.578s; rows=4; coverage.radar events_in_horizon=3 events_occurred=1 events_beyond_horizon=4 events_total=8 trials_in_cohort=4"
  - claim: No score-like key, no private key, no filesystem path and no bare hash appears anywhere in the live payload.
    command: "python3 recursive key/value walk over the live /catalyst-radar response (regex score|probabilit|materialit|rank|composite|confidence|weight and object_key|receipt|manifest_sha|canonical_content|source_json_path|snapshot_id|query_sha|raw_object)"
    result: "score-like keys NONE; private keys NONE; path/hash values NONE; authority.classification=source_fact decision_authority=False"
  - claim: The glance tier states the in-horizon count truthfully and discloses the beyond-horizon omission.
    command: "browser read of #bci-queue-pane innerText on the running production-shaped server"
    result: "'3 trial milestones within the selected horizon · 1 already reached · Beyond horizon: 4 milestones not shown · Current cohort: 4 registered trials, 4 with a recorded milestone date.'"
  - claim: The horizon control's accessible names match its visible labels after first paint.
    command: "browser read of .bci-window aria-label/aria-checked after load"
    result: "180 days/365 days/730 days/All with aria-checked=true on 365"
  - claim: The surface is bilingual at the glance tier and in the evidence drill-down.
    command: "browser: set data-lang=zh, dispatch langchange on document, read row + #bci-inspector-body"
    result: "row '主要完成 … 距里程碑 120 天'; inspector '证据与可信度 … 记录日期沿革'"
  - claim: Paired plain-copy assets are byte-identical and no title= i18n violation exists.
    command: "python3 -m scripts.check_template_site_sync && python3 scripts/check_title_i18n.py"
    result: "template↔site sync OK (91 pairs checked); check_title_i18n OK"
  - claim: The CI manifest still parses after the biocatalyst-serving edits.
    command: "python3 scripts/run_ci_pack.py --workflow .github/ci/legacy-jobs.yml --pack-index 0 --pack-count 12 --validate-only"
    result: "exit 0 — Validated 199 legacy jobs; 199 in scope"
  - claim: The frozen soak surface was not mutated.
    command: "git status --porcelain config/biocatalyst_sources.yml config/biocatalyst_launch_slo_manifest.yml engine/sector_intelligence/launch_slo_verifier.py"
    result: "empty"
unverified:
  - claim: The radar renders correctly against the REAL deployed macro-api process on the VPS.
    what_would_verify: >
      An entitled Chrome session against the deployed process after merge and
      deploy, capturing served process/commit identity and route timings to the
      #6090 receipt standard. Deliberately not done: this PR is held for Sol and
      must not merge, so no deploy exists to verify against.
  - claim: Entitlement behaves correctly for a real signed-in paid user end to end.
    what_would_verify: >
      A real Supabase-authenticated session. The local proof overrode ONLY the
      require_site_full_user dependency; the unsigned-401 boundary was proven on
      the same running server before the override was applied, and 401/400 paths
      are covered by tests/test_biocatalyst_catalyst_radar_api.py.
  - claim: Revision lineage renders has_revisions against the live four-NCT cohort.
    what_would_verify: >
      A cohort generation carrying a milestone-date change tape. The wiring is
      proven by an endpoint-level test on a constructed generation; the served
      canary cohort currently reports history_not_collected for every row.
unresolved:
  - >
    The public change-tape model's field_class ("milestone_date_constraint")
    does not distinguish primary_completion from completion — the json_path
    granularity is stripped upstream of the serving plane. A tape row is
    therefore attributed to a kind only when the trial records exactly one of
    the two radar kinds; a trial carrying both is left no_revisions_recorded
    rather than guessed onto the wrong kind. Widening this needs a change in
    engine/biocatalyst/change_classification.py, which this wave does not own.
  - >
    Pre-existing on main and NOT touched here: the stale-health notice borrows
    the restarted-pagination wording ("the register moved while this page
    loaded") whenever healthState == 'stale'. Byte-identical to origin/main at
    templates/biocatalyst.js; spun off as a separate task.
next_actions:
  - Sol adversarially reviews the PR; this session holds it unmerged by charter.
  - >
    On Sol approval: squash-merge, let the shared render lane cover the merge,
    then run the entitled production journey against the deployed macro-api and
    record the receipt to the #6090 standard (served process/commit identity,
    route timings, no 524/5xx, unsigned 401 intact).
  - >
    Record acceptance as PROVEN_LIVE_COHORT_LIMITED — never as parity. The
    parity ledger stays PARTIAL until post-soak breadth exists.
  - >
    Done in this PR (#6138 merged 2026-08-21T09:42Z, 6590e678c604, mid-session):
    the three new paths were added to owns_paths and the P1-1 wave moved to
    in_progress. Nothing outstanding on that dependency.
do_not_redo:
  - >
    Do not re-adjudicate the first vertical. Sol ratified Catalyst Radar —
    Trial Milestones (P1-0R, 2026-08-20).
  - >
    Do not look for a PIT Company/Stock Identity seam to join sponsors to
    company ids. There is none that is populated: the ONLY non-test
    IssuerRegistry construction in the repo is a hardcoded single-company
    fixture at engine/company_intelligence/event_workspace.py:160, and
    engine/biocatalyst/sponsor_identity.py's SponsorResolution carries no
    company_id/cik/security_id field at all. ticker_only /
    company_identity_not_joined is the correct terminal answer today.
  - >
    Do not "fix" the hydration suite by changing the client. Its 9 failures were
    a stale harness whose fixtures still stubbed the retired
    /trials/milestones URL, so every scenario fell through to the harness's 503
    default. The client was correct throughout.
  - >
    Do not add a process or global cache for the sponsor map. It is loaded once
    per request by design (816 ms cold, 67-99 ms warm, measured); the no-cache
    rule is deliberate.
  - >
    Do not restore whole-interval containment on the forward horizon. It was
    changed to overlap on purpose so a coarse-precision milestone STARTING
    inside the horizon cannot vanish; the acceptance arithmetic is unchanged
    by the switch.
danger_areas:
  - >
    load_sponsor_ticker_map() transitively reads data/baskets/membership.json
    and runs full semantic validation, so it CAN raise where data/ is absent.
    The radar wraps it and degrades to sponsor_map_unavailable. Never let that
    call escape a try/except into the request path.
  - >
    templates/biocatalyst.{js,css} are PAIRED plain-copy assets — site/ copies
    must stay byte-identical or check_template_site_sync fails CI.
  - >
    These DOM ids and state keys are test-pinned and must not be renamed:
    bci-mode-milestones, data-mode="milestones", aria-labelledby on
    bci-queue-pane, the JS state default mode:'milestones', bci-queue-pane,
    bci-queue, bci-inspector-body, bci-queue-title, bci-mode-control, and the
    DOM order of bci-queue-title before bci-decision.
  - >
    biocatalyst-serving uses scope: exclusive, so its paths: list REPLACES
    inference. A new test file that is not listed there does not run, and a new
    closure path that is not covered reds contract-delta.
  - >
    The projection must stay pure — no wall clock. The anchor is
    generation.last_success_at, never datetime.now(); a wall-clock anchor would
    silently break determinism and the acceptance arithmetic.
prs: [6191]
decisions:
  - "DEC:BIOCATALYST-P1-FIRST-VERTICAL-MILESTONE-RADAR"
  - "DEC:BPC-CATALYST-COMPOSES-WITH-COMPANY-EVENT-NOT-FISCAL-WORKSPACE"
---

## Context

Wave P1-1 of `WS:BIOCATALYST-CORE-PRODUCT`, executing the frozen spec in
`research/BIOCATALYST_P1_CONTINUATION_HANDOFF_2026-08-20.md` under the
architecture constitution
`research/BIOCATALYST_P1_RECHARTER_AND_FIRST_VERTICAL_ARCHITECTURE_2026-08-20.md`
(§0 gates, §6 spine, §9 experience, §10 slice).

The vertical is the catalyst-event spine whose designed second tenant is
Regulatory/PDUFA. What shipped is deliberately narrow: registry schedule facts
with provenance, ordered by chronology, with revision lineage and evidence
drill-down. No approval, outcome, or market-signal claim is made anywhere, and
the public wording law is enforced by a test — rows say "Trial milestone",
"Primary completion", "Study completion", "days to milestone", and never
"readout", "catalyst date", or "cancelled".

An opus review returned DO NOT SHIP on the first checkpoint with one blocker and
five major findings. Two of them put factually false statements on the flagship
surface: the subtitle counted already-reached rows as "within the selected
horizon", and four of the cohort's eight events were dropped as beyond-horizon
with no disclosure at all — the partial-coverage notice was suppressed because
`trials_with_events` equalled `trials_in_cohort`. Both are fixed and both fixes
are verified in the browser, not merely in tests. A seventh defect the review
missed was found separately: the API carried `issuer.issuer_relationship` but
the UI never rendered it, so a `parent_of_subsidiary_sponsor` row would have
shown the parent's ticker as if it were the sponsor's own listing — latent on
today's all-`direct_issuer` cohort, which is exactly why it would have shipped
unnoticed.

Acceptance state is `PROVEN_LIVE_COHORT_LIMITED` on a production-shaped run,
not parity, and not yet the deployed process — this PR is held unmerged for Sol
by the P1-0R charter.
