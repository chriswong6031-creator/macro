---
key: ACCOUNT-IDENTITY-HARDENING
title: Account identity, preference delivery and entitlement authority (Handoff E)
objective: >
  Every owner-scoped client surface keys on the immutable auth uuid rather than the email;
  account preferences are delivered by one serialized, acknowledged pump instead of
  fire-and-forget writes; there is ONE client reader of /api/me that keeps "unverified"
  distinct from "free"; and the shared appearance/language fields stop being a nested blob
  two products overwrite. Done when all five waves are merged, deployed and verified on
  app.mastermind-x.com and mastermind-x.com.
status: blocked
program: shared-auth-entitlements
repos: [terminal, macro]
owner: terminal-platform
class: build
blast_radius: user_facing
ambiguity: specified
blocked_by:
  - >
    The Terminal responsive e2e merge gate is unreliable. E-3/E-4/E-5 are complete and
    verified but cannot merge; see next_actions[0] and DSC:TERMINAL-E2E-GATE-COLD-COMPILE.
waves:
  - id: E-1
    title: Immutable shell identity + preference owner boundary
    status: done
    pr: 441
  - id: E-2
    title: Serialized account-preference delivery pump
    status: done
    pr: 443
  - id: E-3
    title: Canonical owner-scoped EntitlementStore
    status: awaiting_ci
    pr: 444
    depends_on: [E-2]
  - id: E-4
    title: Settings freshness (plan + usage revalidation)
    status: awaiting_ci
    pr: 445
    depends_on: [E-3]
  - id: E-5
    title: Shared preference v2 atomics (Macro + Terminal)
    status: in_progress
    pr: [446, 6170, 6175]
    depends_on: [E-4]
    next_action: >
      Macro half is merged and verified live; Terminal half (#446) is queued behind E-3/E-4.
decisions: ["DEC:SHARED-USER-PREFS-ARE-TOP-LEVEL-ATOMICS"]
discoveries: ["DSC:SUPABASE-UPDATEUSER-METADATA-SEMANTICS"]
landmines:
  - >
    site/theme.js is a COMMITTED build product and is what mastermind-x.com serves. A
    template-only edit merges green and changes nothing live (that is what #6170 did).
    Regenerate through lib.site_assets.copy_asset, never a plain cp — it bakes the Supabase
    config and the Terminal overlay. tests/test_shared_pref_atomics.py now guards this.
  - >
    Editing .github/ci/legacy-jobs.yml is a GLOBAL INVALIDATOR: the PR runs the FULL legacy
    matrix and inherits any pre-existing red (options-nbbo-cohort's 0600 race hit #6170).
  - >
    ci-authority/codex/merge-queue-pilot is red on every main-based PR (inactive base
    context, its own payload says allowed:true). It is not a genuine red.
do_not_redo:
  - >
    Do not re-key any owner-scoped store on the email. lib/accountIdentity.ts is the single
    contract; watchlistOwnerKey is an alias of ownerKeyFor.
  - >
    Do not try to make the nested user_metadata.prefs blob safe by serializing one product's
    writes or by re-reading before writing. The race is BETWEEN products and read/write is
    not atomic. Settled by DEC:SHARED-USER-PREFS-ARE-TOP-LEVEL-ATOMICS.
  - >
    Do not mint a ui_theme / ui_lang namespace. theme / theme_auto / lang are the canonical
    top-level keys (lib/user_prefs.py) and both browsers now use them.
  - >
    Do not raise timeouts on whichever e2e spec failed last. The victim set ROTATES; three
    attempts of one SHA produced three different sets.
next_action: >
  Decide the CI gate fix (parallel viewport jobs vs build-once + next start), coordinating
  the required-check contexts with branch protection and merge-on-green.yml.
---

Scope note: this workstream owns the CLIENT side of account identity. The server authority is
unchanged — macro-api `user_entitlements` still decides entitlement, and `terminal/lib/
entitlement.ts` still resolves it server-side. E-3 only stops the UI from offering what the
server will refuse, and from telling a paying customer they are Free when billing is briefly
unreachable.

The five waves are sequential by construction: E-2's pump needs E-1's owner generation, E-4's
freshness policy needs E-3's states, and E-5's atomics need E-2's delivery lane. They were
delivered as separate PRs rather than one, so each defect and its repair stay legible.

Deployment is per-wave: `origin/master` is the only source of truth and ships through the
git-gated `/opt/terminal/terminal-build.sh`. E-1 and E-2 are live and verified
(`mm.marketPrefs.legacy.v1` written on a fresh production guest proves E-1's sweep ran; the
deployed CSS carries the east-safe `.acs-msg.ok{color:var(--brand-2)}` for E-2). The Macro half
of E-5 is live and verified by reading the served theme.js.
