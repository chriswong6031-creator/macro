---
workstream: "WS:ACCOUNT-IDENTITY-HARDENING"
session: "claude/account-identity-hardening-67cd05 (terminal worktree)"
model: opus
ended_because: blocked
mission: >
  Handoff E: key every owner-scoped client surface on the immutable auth uuid, replace
  fire-and-forget preference writes with one serialized acknowledged pump, collapse two
  /api/me readers into one store that keeps "unverified" distinct from "free", add
  plan/usage freshness, and retire the shared nested user_metadata.prefs blob that two
  products overwrite.
state_before: >
  app/(shell)/layout.tsx called getClaims() and kept only the email, discarding the subject.
  lib/useMarketPrefs.ts keyed loadedFor on that email, set ready=false WITHOUT publishing on
  an owner change, wrote market prefs to one unscoped mm.marketPrefs slot, treated Supabase's
  {data:{user:null},error} as an empty account, and pushed nested blobs fire-and-forget.
  lib/useEntitlement.ts and SettingsPanel each fetched /api/me independently with opposite
  failure semantics (authenticated failure -> free; never revalidated). Macro
  templates/theme.js and the Terminal both wrote the whole user_metadata.prefs object.
changed:
  - path: terminal/lib/accountIdentity.ts
    what: NEW frozen contract; guest | account{userId,email}; ownerKeyFor is the one owner namespace.
  - path: terminal/lib/ownerStorage.ts
    what: NEW shared envelope primitives; watchlistOwner.ts now delegates to them.
  - path: terminal/lib/useMarketPrefs.ts
    what: >
      Owner-keyed with a generation token; beginOwner publishes the incoming owner's not-ready
      snapshot synchronously; mm.marketPrefs.v2 envelope with a one-shot legacy sweep into guest;
      ready split from baseLoaded so a failed read cannot authorise a sibling-deleting write;
      writes routed through the pump; shared prefs written as top-level atomics.
  - path: terminal/lib/prefDelivery.ts
    what: NEW serialized pump — revision, one write in flight, coalesced desired state, {error} as failure, bounded retry, dispose as the owner boundary.
  - path: terminal/lib/entitlementStore.ts
    what: NEW canonical /api/me store; six states; displayEntitlement may show same-owner stale, gateEntitlement fails closed.
  - path: terminal/lib/usageStore.ts
    what: NEW /api/brain/me store; verified on Usage entry and past a 60s TTL.
  - path: terminal/lib/useEntitlement.ts
    what: DELETED — two readers was the defect.
  - path: terminal/e2e/globalSetup.ts
    what: NEW route warm-up for the CI gate (PR #452), merged separately from the E waves.
  - path: templates/theme.js
    what: Macro writer sends only the changed atomics; reader resolves atomic-then-legacy per field.
  - path: site/theme.js
    what: The DEPLOYED artifact, regenerated through lib.site_assets.copy_asset (#6175).
  - path: tests/test_shared_pref_atomics.py
    what: NEW 11 cases pinning the JS contract on BOTH the template and the deployed artifact.
verified:
  - claim: The Terminal unit suite passes on the stack tip.
    command: "cd terminal && npx vitest run"
    result: "3054 passed, 4 todo, 173 files"
  - claim: The full responsive suite passes on the stack tip at all three contract viewports.
    command: "cd terminal && rm -rf .next && TERMINAL_E2E_PORT=3198 CI=1 npx playwright test"
    result: "523 passed, 0 failed, 0 retried errors, 4.8 min (cold build, with the #452 warm-up)"
  - claim: E-1 is live on production and its code actually executed there.
    command: "browser JS on https://app.mastermind-x.com/terminal: localStorage.getItem('mm.marketPrefs.legacy.v1')"
    result: "\"1\" — the sweep receipt; unscoped mm.marketPrefs absent; chart true, 7 canvases, 6 rows, 0 console errors"
  - claim: E-2's east-safe status colours are live.
    command: "ssh root@146.190.142.17 grep -o '\\.acs-msg[^{]*{[^}]*}' /opt/terminal/terminal/.next/static/chunks/33v9b891ue5ez.css"
    result: ".acs-msg.ok{color:var(--brand-2)} .acs-msg.err{color:var(--danger)} — no longer --up/--down"
  - claim: The Macro half of E-5 is live in the artifact the site actually serves.
    command: "curl -s https://www.mastermind-x.com/theme.js | grep -c 'data: { prefs: prefs }'"
    result: "0 (was 1 before #6175); patch.theme_auto present; _sharedPref per-field reader present"
  - claim: The E-4 freshness contract holds in a real browser, not only in unit tests.
    command: "playwright spec intercepting /api/me to 503 after one success, firing window focus inside and past the 60s TTL"
    result: "callsInsideTtl=1, callsAfterTtl=2; hero stays Pro; note 'Couldn't refresh your plan — showing the last confirmed one.' + Retry"
  - claim: The CI e2e gate fails on a ROTATING spec set, so it is not a code regression.
    command: "gh api .../actions/runs/32453739453/attempts/{1,2,3}/jobs then check-runs/<id>/annotations"
    result: "3 attempts of one SHA -> 3 different failing sets; only live-candle recurred"
  - claim: The gate's cause is per-route dev-server compilation inside spec timeouts.
    command: "cd terminal && rm -rf .next && CI=1 npx playwright test  (vs a warm .next)"
    result: "warm: 0 flaky ~5.5min; cold: 5 flaky ~8.5min; cold+warm-up: 0 flaky ~5.0min (twice)"
unverified:
  - claim: The #452 warm-up is sufficient to make the CI gate reliable.
    what_would_verify: >
      It is NOT sufficient — refuted after the fact. #444/#445/#446 all failed WITH the warm-up
      active on master (warm-up confirmed running in their logs: "12 routes compiled in 6s"),
      on drawing-system, pine-editor-integrity, watchlist-bulk-actions and marker-tooltip.
      #452 passing its own CI was probably luck. What would settle the remaining cause is
      measuring CI wall time under a built server (next build + next start) or under the
      viewport-split matrix; the e2e step is 41 min on CI against 5 min locally.
  - claim: A browser-based warm-up pass fixes the residual by compiling next/dynamic chunks.
    what_would_verify: >
      Plausible mechanism (the surviving failures are exactly the lazily-loaded surfaces) but
      NOT supported by measurement: two local cold runs with a browser pass gave 1 flaky each,
      against 0 flaky for the HTTP-only warm-up. Discarded rather than shipped. Re-test with
      more runs, or on CI directly, before adopting.
unresolved:
  - "E-3/E-4/E-5 (PRs #444/#445/#446) cannot merge until the e2e gate is trustworthy."
  - "The 41-minute CI e2e step is unaddressed; #452 made the gate honest, not fast."
  - "options-nbbo-cohort has a real 0600 race (tests/test_options_nbbo_cohort.py:1853) that blocks any macro PR touching the global CI invalidator."
next_actions:
  - >
    Decide and implement the CI gate fix. Recommended: split the three viewport projects into
    three parallel GitHub jobs so each gets a whole runner and ~1/3 the specs. This CHANGES the
    required-check contexts, so per terminal/AGENTS.md it must update branch protection,
    .github/workflows/merge-on-green.yml and the controller tests in the SAME PR. The
    alternative is next build + next start, which removes per-route compilation entirely but
    changes /dev route gating, NEXT_PUBLIC_ inlining and the ANALYSIS_LOCAL_PREVIEW seam.
  - >
    Once the gate is reliable: rebase #444 onto master, let it merge, then rebase #445, then
    #446 (each merge changes the base). Only ever arm the HEAD of the queue — arming a stacked
    PR early squashes two waves into one commit and orphans its predecessor.
  - >
    After each merge run: ssh -i ~/.ssh/macro_dashboard_deploy_v2 root@146.190.142.17
    'bash /opt/terminal/terminal-build.sh' and confirm the reported SHA equals origin/master.
  - >
    Verify the Terminal half of E-5 live: sign-in-free check is that the served bundle contains
    sharedPrefsPatch's top-level keys; the behavioural check needs an account, so confirm a
    language change writes user_metadata.lang and NOT prefs.lang.
  - >
    Fix the options-nbbo-cohort 0600 race: create the private ledger with its final mode
    atomically (os.open(..., O_CREAT|O_EXCL, 0o600) or fchmod before any write and before the
    rename), holding the lock across create->write->rename.
do_not_redo:
  - "Do not re-key any owner-scoped store on the email; lib/accountIdentity.ts is the one contract."
  - "Do not try to make the nested prefs blob safe by serializing one writer or by re-reading before writing — settled by DEC:SHARED-USER-PREFS-ARE-TOP-LEVEL-ATOMICS."
  - "Do not mint ui_theme/ui_lang; theme/theme_auto/lang are canonical (lib/user_prefs.py)."
  - "Do not raise timeouts on whichever e2e spec failed last — the victim set rotates."
  - "Do not edit site/theme.js by hand; regenerate via lib.site_assets.copy_asset."
  - "Do not treat ci-authority/codex/merge-queue-pilot as a genuine red; it is an inactive base context and is red on every main-based PR."
danger_areas:
  - "auth.updateUser REPLACES nested objects and getUser RESOLVES {error} rather than rejecting — see DSC:SUPABASE-UPDATEUSER-METADATA-SEMANTICS. Both bit this wave."
  - "site/theme.js is a committed build product; a template-only change merges green and ships nothing."
  - ".github/ci/legacy-jobs.yml is a global CI invalidator: editing it runs the full legacy matrix and inherits unrelated reds."
  - "Owner transitions must be adjusted DURING RENDER, never in an effect — an effect runs after paint, so the outgoing owner renders for a frame under the incoming one."
prs: [441, 443, 444, 445, 446, 452, 6170, 6175]
decisions: ["DEC:SHARED-USER-PREFS-ARE-TOP-LEVEL-ATOMICS"]
discoveries: ["DSC:SUPABASE-UPDATEUSER-METADATA-SEMANTICS"]
---

Three of the five waves are live and verified on production; two are complete, verified and
blocked purely on CI. Nothing is lost: every wave is a pushed PR, and the branches are
refreshed onto current master.

The one thing a continuing session should not repeat is the CI investigation. It is finished
and the answer is written down: the failures are infrastructural (rotating victim set across
attempts of one SHA, reproduced locally by deleting .next), the per-route compile half is
already fixed and merged as #452, and the remaining half is wall time — 41 minutes on CI
against 5 locally. What is left is a decision about the gate's shape, not more diagnosis.
