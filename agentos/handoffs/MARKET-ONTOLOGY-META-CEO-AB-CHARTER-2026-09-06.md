---
workstream: WS:MARKET-OS
session: claude/marketontology-meta-ceo-charter-20260906
model: fable
ended_because: ci_handoff
mission: >
  Record, for a cold successor in either Claude account, the Chairman's
  2026-09-05 PDT override placing two co-equal Claude "Meta-CEO" seats
  (Meta-CEO A = Claude8 Code session 5b29ad85-0490-42c8-b5e4-1e32b1922014;
  Meta-CEO B = Claude3, already hosting F08/F13) directly under Chairman
  Chris in command of the Market Ontology program, relieving the ChatGPT CEO
  ("Sol") and the Grok Secretary transport of authority over this program;
  the lane split between the two halves; the coordination protocol on
  macro#6819; and the exact state of the program's PR/ledger/cross-repo
  backlog at the moment of the override, so work can start without a further
  Sol/Chairman round-trip. This handoff is durable state for
  DEC:CHAIRMAN-OVERRIDE-CLAUDE-META-CEO-REGIME-2026-09-06, not a substitute
  for reading that DEC.
state_before: >
  Prior to this override the program's governing baseline was
  agentos/handoffs/MARKET-ONTOLOGY-F00-META-CEO-CONTINUITY-PRODUCT-RESET-2026-09-05.md
  (F00 principal = this same Code session 5b29ad85, bound after quarantined
  1727abca), additively updated by
  agentos/handoffs/MARKET-ONTOLOGY-F00-CONTINUITY-PRINCIPAL-RECONCILIATION-2026-09-05.md,
  under the layered Chairman -> Main Meta-CEO Sol -> Codex Work Program CEO
  -> Project CEO/Integrator/Auditor Sols -> COO/workers hierarchy recorded in
  agentos/handoffs/MARKET-ONTOLOGY-META-CEO-PROGRAM-CEO-HIERARCHY-AMENDMENT-2026-08-29.md.
  Under that hierarchy, 11 of the 13 tight-regex-matched open Market Ontology
  PRs in the macro repo carried an explicit HOLD-FOR-SOL (or HOLD-FOR-F13)
  body, unreleasable by any Meta-CEO/COO session, and F01-F13 lane sessions
  were individually bound (see do_not_redo below) but largely at
  census/spec-frozen readiness, not shipped-and-live. Chairman Chris then
  wrote, verbatim, in the Claude8 Code session chat: "I have overridden the
  ChatGPT CEO and placed you as Claude Meta-CEO for this project... First i
  want you to create a counterpart who can be responsible for half of the
  project tasks... Then i want you both to immediately intiiate fan out of
  building the complete build out of MarketOntology autonomously end to end
  without requiring ChatGPT orchestration or oversight..." (full quote in
  DEC:CHAIRMAN-OVERRIDE-CLAUDE-META-CEO-REGIME-2026-09-06). This handoff
  records the regime that quote establishes.
changed:
  - path: agentos/decisions/DEC-CHAIRMAN-OVERRIDE-CLAUDE-META-CEO-REGIME-2026-09-06.md
    what: >
      New decision record: question/answer/rationale/alternatives/evidence
      for the Chairman's override placing the two Claude Meta-CEO seats over
      Sol for this program, with verbatim Chairman quote, scope limited to
      Market Ontology, and explicit non-effect on Mastermind
      config/authority_map.yml / config/strategic_state.yml.
  - path: agentos/handoffs/MARKET-ONTOLOGY-META-CEO-AB-CHARTER-2026-09-06.md
    what: This handoff.
unresolved:
  - >
    research/MARKET_ONTOLOGY_META_CEO_CHARTER_2026_09_06.md (the prose charter
    §0-§9 that both the DEC's `affects` list and the Meta-CEO B pickup prompt
    point to) does NOT exist in this worktree as of this handoff — confirmed
    absent, not merely unread. Any reader following that path before it is
    authored will find nothing; treat this handoff + the DEC as the interim
    source of truth until it lands.
  - >
    Meta-CEO B's ACK comment on macro#6819 ("META-CEO B ACK — session
    <uuid>, account Claude3, taking half B") has not been observed in this
    drafting pass — do not assume half B is staffed until that comment is
    read fresh.
  - >
    The open MO-PAID-020 DECISION_REQUEST (ListingAlias->ListingKey renderer
    + CIK-leg ownership, blocking F05/F06 event->security continuation, per
    agentos/handoffs/MARKET-ONTOLOGY-F00-CONTINUITY-PRINCIPAL-RECONCILIATION-2026-09-05.md
    L235-241) was previously slated to route to Sol once; under this DEC that
    routing target no longer exists for this program and the request has not
    yet been re-ruled by either Meta-CEO.
  - >
    11 of the 13 tight-match open Market Ontology PR bodies (#6873, #6872,
    #6865, #6861, #6834, #6831, #6830, #6826, #6810, #6793, #6595) still carry
    literal "HOLD-FOR-SOL"/"HOLD-FOR-F13" text; none has been edited to
    reflect the override, so a non-Meta-CEO reader or a different program's
    sweeper could still misread them as an active Sol gate.
  - >
    Terminal (mastermind-terminal) PR #507 (supabase/migrations/0011_analytics_eid.sql)
    and PR #502 (supabase/migrations/0011_thesis_objects.sql) both claim
    migration number 0011; unresolved which merges first / how the loser
    renumbers.
  - >
    Whether agentos/decisions/DEC-SOL-HOLD-IS-A-MERGE-BARRIER.md and
    agentos/handoffs/MARKET-ONTOLOGY-META-CEO-PROGRAM-CEO-HIERARCHY-AMENDMENT-2026-08-29.md
    will carry a reciprocal `superseded_by` pointer is unresolved — those
    files were not edited by this commission (out of its owned-files scope).
verified:
  - claim: >
      86 pull requests are open in the macro repo as of this census; a tight
      Market-Ontology regex matched 13 of them for deep-dive, of which 11
      carry an explicit HOLD-FOR-SOL/HOLD-FOR-F13 phrase in the body and 2
      (#6892, #6526) do not.
    command: >
      gh pr list -R mastermindx-market-intelligence/macro --state open
      --limit 100 --json number,title,isDraft,labels,headRefName,headRefOid,
      updatedAt,mergeable,body
    result: >
      86 total open PRs saved to prs_open.json; tight-match table (13 rows)
      built and HOLD-phrase-scanned per-PR body (scratchpad census/prs.md
      Q1-Q2).
  - claim: >
      The program's closure ledger (the DONE denominator) is 130 unique ids
      (88 MO-PAID + 42 MO-DELTA) at origin/main commit 084848bd, with named
      per-lane counts and disposition totals.
    command: >
      Row/line count and column tabulation of
      research/market_intelligence_productization/MARKET_ONTOLOGY_F00C_GRANULAR_CLOSURE_LEDGER_2026-09-02.csv
      at origin/main 084848bd (as documented in
      agentos/handoffs/MARKET-ONTOLOGY-F00-FULL-SITE-RESTART-INTEGRATOR-2026-09-04.md
      L37-39,70).
    result: >
      131 lines / 130 unique ids; per-lane F01=12 F02=10 F03=16 F04=9 F05=4
      F06=3 F07=5 F08=7 F09=29 F10=5 F11=6 F12=18 F13=6; dispositions
      NEW_BOUNDED_BUILD 46, UPGRADE_EXISTING_OWNER 40, PROJECTION_ONLY 20,
      BLOCKED_RIGHTS 7, CONTEXT_ONLY 7, EXACT_EQUIVALENT 5. The separate
      1,556-row historical P1 corpus stays a gated denominator, not imported.
  - claim: >
      Terminal (mastermind-terminal) carries a live migration-number
      collision between two open draft PRs, each adding a new
      supabase/migrations/0011_*.sql file.
    command: >
      gh pr list -R mastermindx-market-intelligence/mastermind-terminal
      --state open --limit 50 --json number,title,isDraft,labels,headRefName
    result: >
      PR #507 adds supabase/migrations/0011_analytics_eid.sql; PR #502 adds
      supabase/migrations/0011_thesis_objects.sql; both open/draft with
      HOLD-bearing titles; same target number, different filenames — a
      numbering collision, unresolved as of this handoff.
  - claim: agentos validates clean (0 malformed records) on this branch.
    command: python3 scripts/agentos.py validate
    result: >
      "agentos: 1064 records (69 workstreams, 305 decisions, 252 discoveries,
      438 handoffs) — 0 error(s), 78 warning(s)"; exit 0 (warnings only,
      e.g. review-overdue on unrelated stale DEC records).
  - claim: >
      The in-repo workflow script the charter's execution recipe names
      already exists in this worktree.
    command: >
      Glob .claude/workflows/marketontology_vertical_build.js in this
      worktree
    result: >
      File found at .claude/workflows/marketontology_vertical_build.js;
      its contents were not diffed against the packet-shape contract
      described in the frozen decisions seed in this pass (gap, not a claim
      of correctness).
  - claim: >
      The prose charter file both the DEC and the Meta-CEO B pickup prompt
      point to does not exist in this worktree.
    command: >
      Glob research/MARKET_ONTOLOGY_META_CEO_CHARTER_2026_09_06.md in this
      worktree
    result: No files found.
unverified: []
next_actions:
  - >
    [Half A / Meta-CEO A, this session] Author
    research/MARKET_ONTOLOGY_META_CEO_CHARTER_2026_09_06.md (the prose
    charter, §0 Chairman authority quote through §9 packet examples) — it is
    referenced but does not yet exist; this handoff and the DEC are the
    interim source of truth until it lands.
  - >
    [Half A] Deliver the Meta-CEO B pickup prompt (verbatim block) to the
    Claude3 account via computer-use or an operator-relayed paste, then
    fresh-read macro#6819 for the "META-CEO B ACK" comment before treating
    half B as staffed.
  - >
    [Half A] Run Wave 0 in lane order: review+merge #6890 (F01 pack-5 main-red
    repair, already Ready) first so main is green; then #6873 (F01 hub R1,
    rebasing #6872 after, since they collide on
    .github/ci/legacy-jobs.yml, app/deploy/Caddyfile, config/site_access.yml,
    tests/test_site_access_boundary.py); then #6872 (F04 X1, owes a corrected
    B-1 body + RED-first nightly-hook test); then dispose #6865/#6809/#6604.
  - >
    [Half A] Re-rule the MO-PAID-020 DECISION_REQUEST directly (no more
    routing to Sol under this program) before F05/F06 event->security
    continuation resumes.
  - >
    [Half B / Meta-CEO B, once ACKed] Post the ACK comment on macro#6819
    naming native session id, account, and half-B lanes (F06 F07 F08 F09
    F11 F12 F13 + platform).
  - >
    [Half B] Run Wave 0: #6793 (F09-1), #6831 (F06 child), then #6830/#6834/
    #6826/#6810 by lane, then Terminal #490/#502/#507 disposition.
  - >
    [Half B] Settle the Supabase migration-namespace collision (#507 vs
    #502, both claim 0011) before either merges — grep every open
    charting-app PR for the next free number, do not merge on disk-only
    numbering.
  - >
    [Half B] Write agentos/handoffs/MARKET-ONTOLOGY-META-CEO-B-<date>.md at
    its own first wave boundary — never edit this (Meta-CEO A's) handoff.
do_not_redo:
  - >
    Never resume the quarantined F00 UUID 1727abca-4b22-4106-a498-6b83ad223a73
    or old F01 UUID 550dc8b0; never re-ACK/re-START an already-bound lane
    (F01 dd51ef8f, F04 d6317c9b, F05 cc2d9d31, F06 03200f5b, F09 641ca8f7,
    F10 9c9ac628, F11 d937f8bd, F12 local_abf9f882, F03 local_cc5baa49).
  - >
    Never create a second Market Ontology workstream/lifecycle/identity/
    evidence/graph/portfolio/tenant/scheduler plane, and never literal-clone
    Market Ontology proprietary code/data/corpora/assets/branding/hidden
    interfaces — this override changes WHO gates, not the standing
    no-proprietary-copying/no-duplicate-plane law.
  - >
    Never reconstruct the retained 1,556-row/460-finding historical P1
    corpus from model memory; admission stays byte-exact via the open F00A
    gate only.
  - >
    Never treat DEC:CHAIRMAN-OVERRIDE-CLAUDE-META-CEO-REGIME-2026-09-06 as
    repealing DEC:SOL-HOLD-IS-A-MERGE-BARRIER outside the Market Ontology
    program, and never treat it as license to skip a HOLD the Chairman
    himself names — a Chairman HOLD still binds every merge path.
  - >
    Never centralize all four Claude desktop accounts' execution into one
    account, and never mass-stop the fleet; the Chairman named Claude8+
    Claude3 as priority, the other two as auxiliary only when needed.
  - >
    Never fabricate a Meta-CEO B ACK, watcher registration, or receiver
    capacity from Slack DELIVERY_ONLY visibility, a GitHub review request,
    or a records-only merge alone — confirm the literal macro#6819 comment.
  - >
    Never add a third supabase/migrations/0011_*.sql file (or otherwise
    write DDL) in Terminal before the #507/#502 numbering collision is
    settled through a reviewed migration file in the settled namespace.
danger_areas:
  - >
    Two co-equal Meta-CEO seats operating under explicit "no permission
    needed" language can race or double-merge the same PR: #6873 and #6872
    already share real product files (app/deploy/Caddyfile,
    config/site_access.yml, macro_suite view + test files), and all 13
    tight-match PRs share `.github/ci/legacy-jobs.yml` — fresh-read the PR
    state immediately before every merge, the same discipline as any other
    fleet collision.
  - >
    HOLD-FOR-SOL/HOLD-FOR-F13 text embedded in 11 of the 13 open program PR
    bodies is now stale-for-this-program but has not been edited; a
    non-Meta-CEO session, a different program's sweeper, or a future audit
    could still read it as a live gate.
  - >
    Relieving Sol relieves ceremony (HOLD-FOR-SOL, DECISION_REQUEST-to-Sol,
    READ_ONLY_ARCHAEOLOGY-as-a-lane-state, exact-root Slack re-reads) — it
    does NOT relieve DNR, no-proprietary-copying, no-trade-authority,
    design doctrine/theme art direction, epistemics/gauntlet, or CI/ship-loop
    law. Treat "no permission needed" as scoped to the removed layer only.
  - >
    research/MARKET_ONTOLOGY_META_CEO_CHARTER_2026_09_06.md did not exist at
    drafting time; a reader who follows the path before it is authored will
    find nothing and may wrongly conclude the override itself is unrecorded.
  - >
    Terminal's supabase/migrations ledger is hand-applied and order-
    independent (no supabase_migrations schema, no CLI, per
    agentos/discoveries/DSC-TERMINAL-HAS-NO-MIGRATION-LEDGER.md) — a merged
    0011 file does not self-apply; an operator/API step is still required
    and is easy to assume happened when it did not.
prs: [490, 6335, 6508, 6514, 6595, 6769, 6778, 6793, 6809, 6810, 6819, 6820, 6826, 6827, 6828, 6829, 6830, 6831, 6833, 6834, 6836, 6841, 6843, 6844, 6845, 6846, 6847, 6848, 6849, 6861, 6864, 6865, 6872, 6873, 6876, 6890, 6892]
decisions:
  - "DEC:CHAIRMAN-OVERRIDE-CLAUDE-META-CEO-REGIME-2026-09-06"
  - "DEC:SOL-HOLD-IS-A-MERGE-BARRIER"
discoveries:
  - "DSC:MARKET-ONTOLOGY-K1-VOCABULARY-EXCLUDES-TXI-CHAIN-STATE"
  - "DSC:MARKET-ONTOLOGY-USER-STATE-STORE-IS-TERMINAL-WATCHLISTS"
  - "DSC:MARKET-ONTOLOGY-PUBLIC-P1-CORPUS-RETAINED-OUTSIDE-GITHUB"
  - "DSC:MACRO-SERVED-ORIGIN-IS-MASTERMIND-X-COM"
---

## Body

This handoff is the durable record backing
`DEC:CHAIRMAN-OVERRIDE-CLAUDE-META-CEO-REGIME-2026-09-06`. Read that DEC
first for the question/answer/rationale/verbatim-quote/alternatives; this
file exists so a cold successor in either Claude account (or a nightly
regenerator, or a nightly reader of `docs/AGENT_OS_STATE.md`) can find the
lane split, the coordination protocol, and the concrete backlog state
without re-deriving them from Slack or from this session's chat transcript,
which is not a durable citation surface.

### Lane split (§3 of the frozen decisions seed)

Meta-CEO A (Claude8, this session) owns F00 shared shell/nav/contract
freeze + integration, F01 (12 ledger rows), F02 (10), F03 (16), F04 (9),
F05 (4), F10 (5), plus the cross-cutting F01F13 Market Orientation project
(`DEC-MARKET-ONTOLOGY-MARKET-ORIENTATION-PROJECTION-2026-08-30`, currently
unplaced) — 56 ledger rows plus the shell. Meta-CEo B (Claude3) owns F06
(3), F07 (5), F08 (7, already resident), F09 (29), F11 (6), F12 (18), F13
(6, already resident), plus the Supabase migration-namespace settlement and
the Terminal identity/tenant contract freeze F11/F12 depend on — 74 ledger
rows plus the platform. Shared surfaces (Macro shell vs Terminal shell) are
each owned by the half whose repo they live in; a cross-half touch is
labelled `meta-ceo-shared` and reviewed at the owning half's next wave
boundary, not blocked on it.

### Coordination protocol (§4)

Running log = comments on macro#6819, one per wave boundary per Meta-CEO
(wave id, packets shipped with merge sha + live URL, packets failed, ledger
rows closed, next wave). Durable state = this handoff for half A and a
parallel `MARKET-ONTOLOGY-META-CEO-B-<date>.md` for half B, each written
only by its own owner. No new stores. A held-PR takeover requires a fresh
read of the PR, a wait of one wave if another live session commented within
2h, an Opus `reviewer` pass against fresh `origin/main`, then the normal
merge-on-green chain. No waiting protocols remain for this program: no
HOLD-FOR-SOL, no READ_ONLY_ARCHAEOLOGY as a lane state, no
DECISION_REQUEST-to-Sol, no exact-root Slack re-read before every act — a
fresh GitHub-state read before every push/merge is still required by
standing fleet law, independent of Sol.

### What DONE means for this program (§2)

Every one of the 130 ledger rows is terminal with proof: NEW_BOUNDED_BUILD /
UPGRADE_EXISTING_OWNER / PROJECTION_ONLY rows merged AND live-verified
(live URL + readback/screenshot in the PR body), ledger status updated in
the same or next PR; BLOCKED_RIGHTS rows carry a recorded Chairman/
commercial rejection, not a build; CONTEXT_ONLY / EXACT_EQUIVALENT rows
carry a pointer to the existing owner. "Done" for any single packet remains
merged + live-verified per standing fleet law — never "PR open."
