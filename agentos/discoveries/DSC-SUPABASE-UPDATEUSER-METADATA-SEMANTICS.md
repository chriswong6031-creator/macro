---
key: SUPABASE-UPDATEUSER-METADATA-SEMANTICS
claim: >
  Two supabase-js behaviours drive a whole family of silent account-data defects, and both
  were mis-assumed in shipped code on both properties.
  (1) `auth.updateUser({ data })` MERGES top-level `user_metadata` keys but REPLACES a nested
  object WHOLESALE. Writing `{ prefs: { lang } }` therefore deletes `prefs.theme`, and two
  writers of one nested blob lose each other's updates no matter how carefully either one
  serialises its OWN writes — the race is between the writers, and a fresh-read-before-write
  only shrinks the window because read and write are not atomic.
  (2) `auth.getUser()` and `auth.updateUser()` RESOLVE with `{ data, error }` on an auth
  failure rather than rejecting. A `.catch()` never fires, so `updateUser(...).catch(() => {})`
  reports a failed write as success, and `getUser().then(({data}) => data.user?.user_metadata)`
  reads a FAILED read as "this account has no metadata" — which then supplies an EMPTY merge
  base to (1) and deletes every sibling key on the next edit.
falsifier: >
  A supabase-js release that makes a partial nested `data` object merge server-side, or that
  rejects the promise on an auth error instead of resolving `{ error }`. Concretely: assert
  that `updateUser({ data: { prefs: { lang: "zh" } } })` against an account holding
  `prefs.theme` leaves `theme` present, or that a `getUser()` with an invalid token rejects.
  Either result retires the corresponding half of this record.
so_what: >
  Three rules for any client that writes user_metadata. FIRST, a field written by more than one
  product must be its own TOP-LEVEL key — that is the only structural fix, and it is why
  `prefs.{theme,themeAuto,lang}` became `theme` / `theme_auto` / `lang`
  (DEC:SHARED-USER-PREFS-ARE-TOP-LEVEL-ATOMICS). SECOND, a nested blob with a SINGLE writer is
  still fine, but every write must carry the whole blob from a merge base that a read actually
  answered — track "the UI may paint" separately from "a merge-and-push is safe", or a failed
  read silently authorises a sibling-deleting write. THIRD, never treat a resolved promise as a
  successful write: check `{ error }` explicitly, and never report "Saved" from anything weaker
  than an acknowledgement.
kind: landmine
scope: [macro, terminal]
confidence: verified
verified_at: 2026-08-21
verified_by: >
  mastermind-terminal PR #441 (`{ data: { user: null }, error }` was being read as an empty
  account; `ready` vs `baseLoaded` split), PR #443
  (terminal/lib/prefDelivery.ts + lib/__tests__/prefDelivery.test.ts — 12 cases including
  `{error}`-as-failure and the reordering stale-write race, mutation-verified: treating
  `{ error }` as success reddens 7, allowing concurrent writes reddens 4), and
  macro PR #6170 + mastermind-terminal PR #446, which retire the nested `prefs` blob on both
  writers. The wholesale-replace half was already documented in
  terminal/lib/accountPrefs.ts `metaObject()` before this wave.
---

Scope note: (1) is a documented supabase-js behaviour that the Terminal's own
`terminal/lib/accountPrefs.ts` already commented on — the gap was that knowing it is not
enough when a SECOND product writes the same object. (2) is the less obvious half and the one
that produced the worst outcome: a preference pane that said "Saved" for writes that never
landed, and an account whose sibling keys were deleted by the next edit after any auth hiccup.

The two interact. Either alone is survivable; together they turn one transient auth failure
into permanent data loss, because the failed read supplies the empty base that the wholesale
nested replace then commits.
