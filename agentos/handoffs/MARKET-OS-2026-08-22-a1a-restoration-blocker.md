---
workstream: "WS:MARKET-OS"
session: claude/a1a-restoration-blocker
model: codex
ended_because: blocked
mission: >
  Execute the remaining authenticated A1A production matrix under fresh Sol authority,
  but first prove that the sealed 13-row canonical Portfolio fixture can be restored
  exactly before deleting any canonical row.
state_before: >
  PD1 was accepted and closed. Terminal and Macro were signed into the designated test
  account and agreed on the sealed 13-row canonical Portfolio multiset. Terminal held
  four Watchlists with 134 symbol memberships and Macro held the same four registered
  Watchlists in its product-specific representation. Scene 9 and A1B were prohibited.
changed:
  - path: "Authenticated production restoration-capability probe"
    what: >
      Inserted exactly one owner-scoped temporary Portfolio probe through the already
      deployed authenticated Supabase client, requesting explicit identity and timestamp
      values. Production preserved the requested row id and every other supplied field but
      rewrote created_at and updated_at. The probe was then deleted with an exact returned-row
      receipt. No canonical row and no Watchlist row was mutated.
  - path: "agentos/handoffs/MARKET-OS-2026-08-22-a1a-restoration-blocker.md"
    what: >
      Preserves the single fail-closed defect packet required by the production commission.
      It records the blocker, containment proof, remaining unverified matrix, and the Sol
      decision required before any future destructive evacuation.
verified:
  - claim: "The action-time preflight matched the sealed private baselines before any write"
    command: >
      Authenticated in-app browser no-store Terminal GET /api/portfolio and /api/watchlist;
      Macro WatchStore.portfolio.list/readState and WatchStore.lists.all; SHA-256 comparison
      using the sealed product-specific canonicalizers
    result: >
      Terminal and Macro each returned 13 canonical Portfolio rows and the identical
      Portfolio fingerprint 11809e97eef33166c5834df20e967f572c2b47bbfaed64a34a1050942aa6d0a0.
      Macro was cloud/ready with no warning. Terminal's four-list/134-membership seal and
      Macro's independent four-list seal both matched their pre-write baselines.
  - claim: "The current authenticated production path cannot recreate the sealed fingerprint exactly"
    command: >
      Owner-scoped authenticated insert into portfolio_positions with explicit id,
      user_id, created_at, updated_at, and the remaining row fields; select-star single-row
      receipt compared field by field to the intended probe
    result: >
      The insert returned the exact requested row id and a single unambiguous affected row,
      but created_at and updated_at were the only mismatched fields because production
      rewrote both timestamps. The sealed Portfolio canonicalizer includes createdAt, and
      the commission also requires identical private field values; deleting the 13-row
      fixture would therefore make the authorized restoration postcondition unattainable.
  - claim: "The temporary probe was exactly removed and the original populations remained unchanged"
    command: >
      Owner-scoped delete filtered by the probe id and session user id with select-star
      single-row receipt; immediate authenticated Terminal and Macro authoritative rereads;
      probe-id absence check; sealed Portfolio and Watchlist fingerprint comparisons
    result: >
      Delete returned the exact inserted row. The probe is absent across Terminal and Macro.
      Both products again return exactly 13 canonical Portfolio rows with fingerprint
      11809e97eef33166c5834df20e967f572c2b47bbfaed64a34a1050942aa6d0a0 and agree with
      each other. Terminal's four-list/134-membership Watchlist seal and Macro's four-list
      Watchlist seal remain exact. No private fixture values were emitted.
  - claim: "The fail-safe boundary was honored"
    command: >
      Compare the production operation log to the Sol authorization and stop conditions
    result: >
      Zero canonical Portfolio rows were deleted. No broader A1A scene, authentication
      transition, Watchlist mutation, repair, Scene 9 path, or A1B work was executed.
unverified:
  - claim: "The remaining authenticated A1A production matrix passes"
    what_would_verify: >
      After the restoration blocker is resolved and Sol grants fresh action-time authority,
      execute the true-zero, one-position, all-unsized, mixed-sized, read-failure, continuous
      conformance, and privacy scenes with exact cleanup.
  - claim: "A sanctioned production path can restore the original 13 rows byte-for-byte"
    what_would_verify: >
      A bounded proof under an approved identity-preserving restoration mechanism must return
      the intended id, created_at, updated_at, and every other private field exactly, then remove
      its temporary row and reproduce the sealed baseline.
  - claim: "Sol accepts A1A as done"
    what_would_verify: >
      Sol reviews a complete authenticated acceptance packet after the remaining matrix and
      explicitly accepts A1A.
unresolved:
  - "A1A remains in_progress; production acceptance stopped before canonical evacuation."
  - "The authenticated writers preserve row identity only partially: production rewrites created_at and updated_at."
  - "A1B remains blocked and was not started."
next_actions:
  - >
    Sol chooses and authorizes one restoration contract: either an already-sanctioned
    identity-and-timestamp-preserving path, or an explicit revised fixture/fingerprint law
    that excludes server-generated metadata. Do not infer either choice from this packet.
  - >
    After that decision, repeat a one-row exact restoration probe and require every field plus
    both product fingerprints to match before requesting fresh destructive action-time authority.
  - >
    Only after the probe and fresh authority pass, execute the remaining A1A matrix. Continue
    to prohibit Scene 9 and A1B unless separately authorized.
do_not_redo:
  - "Do not delete any canonical Portfolio row under the current restoration contract."
  - "Do not treat matching ticker, sizing, notes, status, or duplicate multiplicity as exact restoration when created_at differs."
  - "Do not recreate the temporary restoration probe; it is deleted and its field-level result is conclusive for the current production path."
  - "Do not repeat PD1 mutation machinery; its durable mutation and failure-honesty proof remains accepted."
  - "Do not expose private Portfolio or Watchlist values; counts, field names, and fingerprints are sufficient."
danger_areas:
  - "Standard Terminal create and Macro portfolioUpsert do not accept caller-supplied id or created_at; their normal recreation path necessarily changes the sealed canonical multiset."
  - "Even the existing authenticated Supabase client accepted the explicit id but production rewrote both timestamp fields, so successful insertion is not proof of exact restoration."
  - "A broader production run without a proven restore path can satisfy its intermediate scenes yet irreversibly fail cleanup."
---

# A1A authenticated production matrix — exact-restoration blocker

Verdict: **FAIL-CLOSED / RETURN TO SOL.** The matrix stopped before canonical
evacuation because the live authenticated store rewrites `created_at` and `updated_at`
on insert. The sealed Portfolio fingerprint includes `createdAt`, and the commission
requires identical private fields, so the current writer cannot meet the cleanup law.

Containment is complete. The only temporary probe was deleted with an exact returned-row
receipt; Terminal and Macro both returned to the original 13-row fingerprint immediately;
both Watchlist baselines remained exact. No canonical row was deleted, no private fixture
value was disclosed, and no repair or prohibited scene was attempted.

The next move is a Sol contract decision, followed by a fresh one-row restoration proof and
fresh destructive action-time authorization. A1A remains `in_progress`; A1B remains blocked.
