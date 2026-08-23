---
workstream: "WS:BIOCATALYST-CORE-PRODUCT"
session: claude/biocatalyst-p1-1-prod-acceptance
model: codex
ended_because: blocked
mission: >
  Adjudicate P1-1 against the naturally deployed #6191 process and current
  public generation using the #6090 receipt standard: exact source/process
  identity, signed-out and real site_full controls, entitled Radar and safety
  walks, and a real Google Chrome desktop/390px EN/ZH evidence-and-lineage
  journey. On failure, leave P1-1 in progress, record the exact blocker and
  smallest falsifiable repair, open only a records PR, and stop for Sol.
state_before: >
  PR #6191 was merged at a7e09a974eac26a3cdf5f85491962b19013e122e
  from Sol-approved source head 35988aa7e8f859a291da35dbfbe8369133d22952.
  Production deployment and public/API truth had not yet been accepted, so
  P1-1 remained in_progress and PROVEN_LIVE_COHORT_LIMITED was not available.
changed:
  - path: research/BIOCATALYST_P1_1_PRODUCTION_ACCEPTANCE_2026-08-22.md
    what: >
      Added the complete FAIL receipt: fresh main and natural process identity,
      current generation, signed-out and site_full API matrix, real live safety
      walk, exact row/coverage/revision counts, real source evidence, screenshot
      hashes and measured desktop/mobile EN/ZH geometry. It records the desktop
      flex-row clipping blocker, a bounded cause hypothesis, repair falsifier,
      and every non-claim.
  - path: agentos/workstreams/WS-BIOCATALYST-CORE-PRODUCT.md
    what: >
      Removed the stale #6191 review/merge next action. P1-1 remains
      in_progress; the next gate is Sol review of the production blocker and
      any bounded repair authorization. PROVEN_LIVE_COHORT_LIMITED remains
      unclaimed and parity remains PARTIAL.
  - path: agentos/handoffs/BIOCATALYST-CORE-PRODUCT-2026-08-22-P1-1-PROD.md
    what: >
      Added this cold-stranger production-failure handoff with exact commands,
      evidence, smallest next repair, and scope barriers.
prs: [6191]
verified:
  - claim: >
      Fresh main and the natural production process contain the #6191 merge,
      with no P1-1 runtime/product/browser touch at the proof cut and no P1-1
      product diff in the running process commit. A later records-branch
      fast-forward carried an unrelated legacy CI manifest change only among
      #6191 paths.
    command: >-
      git ls-remote origin refs/heads/main; git log --name-only
      a7e09a974eac26a3cdf5f85491962b19013e122e..0bcfef045517bcaae23271b1218f37c59bcaa864
      -- <all 21 #6191 paths>; git diff --name-only a7e09a9 e922382 --
      <all non-CI #6191 paths>; git merge-base --is-ancestor for
      a7e09a9 -> e922382 -> de66109 -> 0bcfef0
    result: >
      Remote main at the proof cut exactly
      0bcfef045517bcaae23271b1218f37c59bcaa864; proof-cut post-merge path log
      empty; process product diff empty; all three ancestry checks exit 0.
      Records branch then fast-forwarded without record/product overlap to
      facbaa29c5467ce55bd3a18816fb7731ad4f245c; its only #6191-path movement
      was the administrative .github/ci/legacy-jobs.yml. It then fast-forwarded
      to final records base fa73271632a7cf5eb214e4e68bdfcb96c22422b0;
      facbaa2..fa7327 touched neither #6191 paths nor this PR's three records.
  - claim: >
      The process was naturally deployed and healthy without a manual updater,
      restart or redeploy.
    command: >-
      curl -L https://www.mastermind-x.com/api/health?cb=p1_1_prod_final;
      ssh root@146.190.142.17 systemctl show macro-api -p ActiveState -p MainPID
      -p ExecMainStartTimestamp; git -C /opt/macro rev-parse HEAD
    result: >
      HTTP 200 in 0.960156s; health commit e92238244f0, checkout
      de66109a7ac; active MainPID 1659274 started 2026-08-22 22:06:09 UTC;
      /opt/macro checkout de66109a7aca4ef41324b54dda14041ccef05941.
  - claim: >
      The current pointer-bound public generation is real, current-only, and
      carries the four configured/observed trials.
    command: >-
      production /opt/macro-api/.venv Python import of
      app.biocatalyst._read_bundle() on /opt/macro, returning only public
      generation identity/clocks/schema and trial count
    result: >
      ctgov_run_20260822T220030672261Z_e679bb3d2518; schema 1.6.0;
      last_success_at/published_at 2026-08-22T22:00:31.310115Z;
      source dataset 2026-08-21T09:00:05; 4 trials.
  - claim: >
      Authentication, site_full entitlement, default Radar, invalid-query and
      signed-out controls meet the live HTTP contract on the exact process.
    command: >-
      real Chrome page-world MDXAuth session -> authenticated fetch /api/me,
      /api/biocatalyst/v1/catalyst-radar and invalid horizon; separate unsigned
      curl of the default Radar route
    result: >
      /api/me 200 in 0.981s, site_full=true; default Radar 200 in 5.002s;
      invalid horizon 400 in 0.191s; signed-out 401 in 1.049154s. Private
      no-store and Authorization vary fences present; no token/user identity
      returned from page world.
  - claim: >
      The live Radar payload is populated, arithmetically honest, revision-rich
      and public-safe.
    command: >-
      recursive page-world walk over the actual entitled Radar JSON plus safe
      extraction of query, pagination, coverage.radar, timing and revision
      denominators
    result: >
      4 rows; 3 upcoming + 1 occurred; 4 beyond horizon; 8 total events; 4
      cohort trials and 4 with events; revision states 2 has_revisions + 2
      history_not_collected; 6 lineage entries. Zero score/authority-like keys,
      private keys, path/R2 values or bare hashes; source_fact and
      decision_authority=false.
  - claim: >
      A real production row opens a public source inspector and its full real
      milestone-date lineage in both languages and at 390px.
    command: >-
      authenticated Google Chrome click of the live NCT06602479
      primary-completion row; read #bci-inspector-body and
      .bci-radar-revision-section; exact 390px geometry and screenshots
    result: >
      ClinicalTrials.gov link is https://clinicaltrials.gov/study/NCT06602479
      and resolves 200 in 0.666399s; all 3 real revisions render newest-first in
      EN and ZH; mobile dialog has no horizontal overflow and each 344px
      lineage card has scrollWidth==clientWidth. Full-lineage screenshot
      sha256 abcd98a7cec688389b0fdcc44528871bea97220ca9555678dc556b84b5f2bb72.
  - claim: >
      The exact 390px EN and ZH Radar journeys pass the requested mobile
      geometry and language checks.
    command: >-
      Chrome viewport override calibrated for browser zoom until innerWidth=390
      and innerHeight=844; DOM rectangle/client/scroll measurements; EN/ZH UI
      language control; screenshots; page-origin console walk
    result: >
      No page horizontal overflow; every row has scrollHeight==clientHeight and
      no tracked chip/date descendant outside its row; only the intentional
      two-line title clamp truncates title text. EN sha256
      16a9b45820d2965d08350c841f87fc894b94eeb98ca016a3c2c49dd0265d46c8;
      ZH sha256 5f49b818760bd52f6f986114bd72d473863f6d1c94e6e141346f58ae906885c3;
      page-origin warnings/errors empty.
  - claim: >
      Real desktop EN and ZH fail the commissioned no-clipping/no-collision
      production-acceptance gate.
    command: >-
      Google Chrome DOM rectangle/client/scroll measurements for all live
      .bci-radar-card descendants at the default 2055x1270 viewport plus EN/ZH
      screenshots
    result: >
      Every row clientHeight=94; EN scrollHeight [150,120,116,116], ZH
      [120,120,116,116]. Titles/meta/date descendants escape their card and
      visually collide with the following row. EN screenshot sha256
      3a2e95ecd77d665295fd1d42aa0e198ae703ac1c4102780668e2704b0eb87226;
      ZH sha256 66d5798ceb42cd41033989d4f1bebcd79bc21676c8e147c0fdc5698291dc2b30.
  - claim: >
      The authenticated proof window contains no backend 5xx and no browser/API
      524.
    command: >-
      journalctl -u macro-api --since 2026-08-22T22:08:00Z filtered to /api/me
      and /api/biocatalyst/v1 routes, paired with exact browser response status
    result: >
      Only expected 200 and invalid-horizon 400 entries for the matrix and NCT
      detail requests; signed-out control 401; no 5xx or 524.
unverified:
  - claim: P1-1 is production accepted.
    what_would_verify: >
      A Sol-authorized desktop row repair merged and naturally deployed, then a
      new real site_full production matrix in which every desktop EN/ZH Radar
      row contains its title/meta/date descendants without collisions while
      the exact 390px, evidence, lineage, safety, 401/400 and API gates remain
      green.
  - claim: >
      Preventing Radar cards from flex-shrinking is sufficient by itself.
    what_would_verify: >
      A narrow implementation and real browser regression proving every
      desktop row has scrollHeight<=clientHeight and every tracked descendant
      rectangle remains inside the row. If that fails, the cause hypothesis is
      falsified and renewed diagnosis is required.
  - claim: BioCatalyst has functional parity beyond the current four-NCT cohort.
    what_would_verify: >
      The separately governed post-soak breadth/parity program. Even a later
      P1-1 acceptance remains PROVEN_LIVE_COHORT_LIMITED, not full parity.
unresolved:
  - >
    Sol has not authorized a runtime repair. Production evidence points to
    shrinkable desktop Radar flex children inside the fixed-height scroll
    queue; `.bci-radar-card` lacks Radar-only shrink protection while mobile's
    height-auto queue does not reproduce the defect.
  - >
    The initial pre-claim browser tab showed temporary unavailable, but the
    normal post-connection reload hydrated from a real 200 and stayed stable.
    This was recorded but is not the acceptance blocker; no 5xx/524 or repeat
    outage was observed.
next_actions:
  - >
    Sol reviews the records-only FAIL receipt and this handoff. Keep the PR
    draft/HOLD-FOR-SOL with no merge-on-green and native auto-merge null.
  - >
    If Sol authorizes repair, start a fresh narrow implementation branch from
    then-current main. Test a Radar-only desktop flex-size correction, likely
    preventing `.bci-radar-card` shrink, and change only
    templates/biocatalyst.css, its paired site/biocatalyst.css copy, and the
    focused tests/browser proof necessary to pin the regression. Do not
    re-architect P1-1 or the queue.
  - >
    The repair falsifier is exact: desktop EN and ZH rows must each have
    scrollHeight<=clientHeight; title/meta/date rectangles must remain inside
    the row; adjacent rows must not collide; page/chip horizontal overflow must
    remain absent; exact 390px EN/ZH and the three-entry inspector lineage must
    remain green.
  - >
    After an authorized repair merges and naturally deploys, rerun the complete
    #6090-standard production matrix. Only that new real journey may set P1-1
    done and claim PROVEN_LIVE_COHORT_LIMITED. Do not start P1-2 beforehand.
do_not_redo:
  - >
    Do not repeat #6191 implementation review or re-architect Catalyst Radar.
    Sol already accepted the substantive P1-1 product at source head 35988aa7.
  - >
    Do not treat the passing API, safety, source link, real lineage or mobile
    matrix as a waiver for the desktop clipping gate. The production verdict is
    FAIL until the desktop falsifier passes.
  - >
    Do not use the controlled pre-merge Chromium fixture as production truth.
    This handoff's browser evidence is from the real authenticated production
    page and current public generation.
  - >
    Do not manually redeploy/restart to manufacture a receipt, expose browser
    credentials, expand the cohort, alter CT.gov cadence/source registry or
    soak law, raise authority, add scoring/ranking/gating, or start P1-2.
danger_areas:
  - >
    templates/biocatalyst.css and site/biocatalyst.css are paired plain-copy
    assets. Any later authorized CSS repair must keep them byte-identical and
    rerun template/site sync.
  - >
    The desktop queue is intentionally scrollable and fixed-height; the smallest
    repair must preserve that workspace architecture. A global `.bci-trial`
    sizing change would affect Trial Screen/Peer/Change/Prospective modes and is
    wider than the evidence authorizes.
  - >
    Browser zoom was 90%. The mobile override was calibrated to the page's
    actual reported `innerWidth=390`; do not cite the raw override input as the
    viewport proof.
  - >
    The visible human phrase `Primary completion` is lawful. Machine-state
    leakage checks target underscored/raw states such as `primary_completion`,
    `has_revisions`, and `history_not_collected`, not the translated product
    labels.
decisions:
  - "DEC:BIOCATALYST-P1-FIRST-VERTICAL-MILESTONE-RADAR"
  - "DEC:BPC-CATALYST-COMPOSES-WITH-COMPANY-EVENT-NOT-FISCAL-WORKSPACE"
---

## Current state

The implementation is merged and naturally deployed. The API and current
four-trial generation are healthy, entitled, private, populated and safe. The
real source inspector and three-entry revision lineage work in production. The
exact 390 px EN/ZH journey is clean. None of those facts overrules the measured
desktop row-content collision, so wave P1-1 remains `in_progress` and this
session ends blocked on Sol authority for the smallest repair.

The durable evidence packet is
`research/BIOCATALYST_P1_1_PRODUCTION_ACCEPTANCE_2026-08-22.md`. Continue from
that packet and this handoff; do not rebuild the already accepted P1-1 vertical
or repeat the pre-merge review.
