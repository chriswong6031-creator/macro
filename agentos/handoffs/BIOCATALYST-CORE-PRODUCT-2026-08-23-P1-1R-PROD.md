---
workstream: "WS:BIOCATALYST-CORE-PRODUCT"
session: claude/biocatalyst-p1-1r-prod-success
model: codex
ended_because: complete
mission: >
  Release and normally squash-merge Sol-approved P1-1R PR #6277, observe its
  automatic public-render and natural VPS updater without dispatching or
  restarting anything, then rerun the complete real authenticated production
  API/safety/2055/1280/390 EN/ZH/lineage matrix. On PASS, record P1-1 as
  PROVEN_LIVE_COHORT_LIMITED and done in a new records-only PR held for Sol.
state_before: >
  P1-1 was merged and deployed but its durable production verdict was FAIL:
  real desktop Radar cards shrank below their content and collided. Sol had
  approved exact repair head 0e48c8830b8a26050ccfae453f2b385118b1ea59,
  but #6277 was still held and P1-1 remained in_progress.
changed:
  - path: research/BIOCATALYST_P1_1R_PRODUCTION_ACCEPTANCE_2026-08-23.md
    what: >
      Added the new production-success receipt with the exact repair merge,
      automatic render run/commit, natural VPS/static-byte proof, current
      generation, authenticated and signed-out API matrix, safety walk, all six
      deployed-byte geometry cuts, real EN/ZH lineage, console status, bounded
      acceptance claim, and explicit non-claims.
  - path: agentos/workstreams/WS-BIOCATALYST-CORE-PRODUCT.md
    what: >
      Set wave P1-1 to done and recorded PROVEN_LIVE_COHORT_LIMITED while
      keeping broader parity PARTIAL. The only next action is Sol review of the
      held records-only closeout; P1-2 remains unauthorized.
  - path: agentos/handoffs/BIOCATALYST-CORE-PRODUCT-2026-08-23-P1-1R-PROD.md
    what: >
      Added this cold-stranger continuation handoff with the exact proof chain,
      settled state, next lawful gate, non-claims, and do-not-redo boundaries.
prs: [6191, 6271, 6277]
verified:
  - claim: >
      Sol-approved #6277 merged normally from the exact approved source head,
      without merge-on-green or native auto-merge.
    command: >-
      gh pr view 6277 --json state,isDraft,headRefOid,mergeCommit,mergedAt,
      autoMergeRequest,labels,title,url; git fetch origin immediately before
      merge; three-path and biocatalyst-serving collision audit
    result: >
      Source 0e48c8830b8a26050ccfae453f2b385118b1ea59; pre-merge main
      e7ae573bfe9580526cfd94ec6d705f5bdbb60afd; squash merge and immediate
      post-merge main 5ec3d9d34111643813baa4a2eea0ebd5ae49f4fd at
      2026-08-23T06:32:56Z; autoMergeRequest null; no labels.
  - claim: >
      The merge triggered the normal automatic public-render, which succeeded
      and pushed the canonical immutable page stamp.
    command: >-
      gh run view 32623216451 --json databaseId,event,headSha,conclusion,
      createdAt,updatedAt,url,jobs; git show -s and git show --stat
      456185ab3b94143d734aa05c2a8e20a43b633db8; inspect
      site/biocatalyst.html and both CSS hashes
    result: >
      Automatic push run 32623216451 on exact merge head succeeded; render job
      97154497178 succeeded; normal render-public commit
      456185ab3b94143d734aa05c2a8e20a43b633db8 changed the page stamp to
      biocatalyst.css?v=712a3a77. No manual dispatch occurred.
  - claim: >
      Natural VPS/static delivery serves the exact Sol-approved CSS bytes.
    command: >-
      read-only SSH with deploy identity: git -C /opt/macro rev-parse HEAD;
      grep the site.served page stamp; shasum -a 256 the served CSS; curl -IL
      and curl response-body SHA-256 for the exact public asset URL
    result: >
      First converged VPS checkout 456185ab3b94143d734aa05c2a8e20a43b633db8;
      final observed VPS checkout fc94d43ad4142e50ec808b2f1a8d6f922ff1fa7b;
      site.served references biocatalyst.css?v=712a3a77; exact public URL is
      HTTP 200, 58152 bytes, immutable, and SHA-256
      712a3a77307efbe9ec0b6c0cf40d4b35e4fcd8fadf9adff6384056e8f21c886f.
      No macro-update or API restart was run.
  - claim: >
      The final current pointer-bound production generation is real, fresh,
      current-only, and covers all four configured trials.
    command: >-
      /opt/macro-api/.venv Python import of app.biocatalyst._read_bundle() on
      /opt/macro, returning only public generation identity/clocks/schema and
      counts; authenticated Chrome Radar refresh and safe response extraction
    result: >
      ctgov_run_20260823T070024098061Z_e679bb3d2518; schema 1.6.0;
      published/last_success 2026-08-23T07:00:24.779012Z; source dataset
      2026-08-21T09:00:05; current_only; configured/observed/trials 4/4/4.
  - claim: >
      Authentication, entitlement, default Radar, invalid-horizon and unsigned
      controls meet the live private HTTP contract with no server error.
    command: >-
      authenticated standard-Chrome Network/Runtime probes for /api/me,
      default /api/biocatalyst/v1/catalyst-radar and invalid horizon; separate
      same-origin unsigned Radar fetch; captured production response-status
      audit
    result: >
      /api/me 200, active unlimited and features includes site_full; default
      Radar 200 with private no-store and Authorization vary; invalid horizon
      400; unsigned Radar 401 with private no-store and Authorization vary;
      zero 5xx and zero 524 in the captured matrix.
  - claim: >
      The current Radar response is populated, arithmetically honest,
      revision-rich, and public-safe.
    command: >-
      recursive walk over the actual final authenticated Radar JSON plus safe
      extraction of query, pagination, coverage.radar, timing, revisions,
      authority, public links and prohibited keys/values
    result: >
      4 rows; 3 upcoming + 1 occurred + 0 current + 4 beyond horizon = 8 total;
      cohort/with-events 4/4; zero absent/unusable/missing-identity rows; 2
      has_revisions + 2 history_not_collected and 6 lineage entries; zero
      private/probability/rank/token/path/R2/bare-hash leaks; source_fact and
      decision_authority=false.
  - claim: >
      The deployed repair closes the real desktop row-containment blocker and
      preserves standard/mobile geometry in both languages.
    command: >-
      authenticated standard Google Chrome after final generation refresh;
      exact inner viewports 2055x1270, 1280x900 and 390x844 in EN and ZH;
      measure every .bci-radar-card client/scroll box, every visible descendant
      rectangle, adjacent card rectangles, document/body/chip overflow and
      #bci-queue computed overflow
    result: >
      All six cuts have 4 real rows and zero row overflow, descendant escape,
      adjacent overlap, page/body horizontal overflow or chip overflow.
      Desktop queues remain overflow-y:auto with scrollHeight greater than
      clientHeight; mobile remains height-auto/overflow-visible. Every cut used
      biocatalyst.css?v=712a3a77 with zero candidate styles.
  - claim: >
      A real current Radar row exposes the complete public ClinicalTrials.gov
      lineage in EN and ZH, and the page has no page-origin error.
    command: >-
      standard-Chrome click of live NCT06602479 primary-completion row; read
      #bci-inspector-pane and public links in EN/ZH; compare the final natural
      generation row payload with the immediately prior generation; tab.dev
      warnings/errors walk
    result: >
      Public link https://clinicaltrials.gov/study/NCT06602479; all three
      recorded-date revisions render newest-first in EN and ZH. The final
      generation changed only public retrieved_at clocks across the four rows;
      lineage/title/date/source data and runtime assets were identical. Page-
      origin warnings/errors were empty; two unrelated chrome-extension
      LavaMoat warnings were excluded by origin.
  - claim: >
      Current main and the final records base preserve the accepted P1-1
      runtime/product/browser surfaces after the render commit.
    command: >-
      git diff --name-only 456185ab3b94143d734aa05c2a8e20a43b633db8..
      origin/main -- <P1-1 runtime/product/browser paths>; git merge-base
      --is-ancestor for repair merge and render commit against origin/main
    result: >
      Path diff empty; both ancestry checks exit 0. The sparse records branch
      began from fresh origin/main fc94d43ad4142e50ec808b2f1a8d6f922ff1fa7b
      and fast-forwarded without record-path overlap to final pre-commit base
      bdd8dffc18cd079dbd25e869a6b9afb910d70b2c.
unverified:
  - claim: BioCatalyst has full functional parity beyond the current four-NCT cohort.
    what_would_verify: >
      The separately governed post-soak breadth/parity program. P1-1 is only
      PROVEN_LIVE_COHORT_LIMITED and broader parity remains PARTIAL.
  - claim: P1-2 is authorized or started.
    what_would_verify: >
      A new explicit Sol/operator commission after this held records closeout.
      Neither P1-1 success nor the end of the soak window grants that authority.
unresolved:
  - >
    No P1-1 product or production blocker remains. The records-only closeout
    itself remains under Sol hold, and no later BioCatalyst wave has authority
    from this acceptance result.
next_actions:
  - >
    Sol reviews the new records-only P1-1R production-success closeout. Keep it
    DRAFT / HOLD-FOR-SOL, do not add merge-on-green, keep native auto-merge
    null, and do not self-merge it.
  - >
    If Sol releases that records hold, merge only the closeout through the
    normal path. The durable state on main will then record P1-1 done and
    PROVEN_LIVE_COHORT_LIMITED while broader parity remains PARTIAL.
  - >
    Stop after P1-1 closeout. Do not start P1-2, widen the cohort, change source
    cadence/soak law, or infer production-scale authority without a new ruling.
do_not_redo:
  - >
    Do not reopen #6191 substantive review, #6271's valid historical FAIL, or
    #6277's accepted Radar-only repair. The deployed falsifier is now green.
  - >
    Do not repeat static deployment by manually dispatching public-render,
    invoking macro-update, restarting macro-api, editing the page query/stamp,
    or injecting candidate CSS. The natural chain and exact bytes are receipted.
  - >
    Do not upgrade PROVEN_LIVE_COHORT_LIMITED to full parity or production-scale
    proof. The current cohort contains four configured/observed NCTs and parity
    remains PARTIAL.
  - >
    Do not expose browser credentials, private worker receipts, object keys,
    source pointers, filesystem paths, R2 keys, or hashes through the product.
danger_areas:
  - >
    templates/biocatalyst.css and site/biocatalyst.css remain paired plain-copy
    assets. The public page uses an immutable content stamp generated by the
    automatic render-public workflow; do not hand-edit the page stamp.
  - >
    Desktop queue scrolling is intentional. The accepted repair prevents only
    .bci-radar-card shrink; a global trial-row sizing change or queue
    rearchitecture would widen the product beyond the proved mechanism.
  - >
    Current-generation movement may advance public retrieved_at clocks without
    changing the underlying source dataset or row truth. Recheck the pointer
    and compare payload deltas before treating a clock-only move as semantic.
decisions:
  - "DEC:BIOCATALYST-P1-FIRST-VERTICAL-MILESTONE-RADAR"
  - "DEC:BPC-CATALYST-COMPOSES-WITH-COMPANY-EVENT-NOT-FISCAL-WORKSPACE"
---

## Current state

P1-1 is production accepted at `PROVEN_LIVE_COHORT_LIMITED`. The exact
Sol-approved repair bytes are on the natural static delivery path, the current
four-NCT generation passes every API/safety/geometry/evidence gate, and the
earlier desktop blocker is closed. Broader parity remains PARTIAL.

The only open action is Sol review of the records-only closeout containing this
handoff, the new PASS receipt, and the P1-1 done transition. No P1-2 work is
authorized or started.
