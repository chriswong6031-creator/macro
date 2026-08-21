---
key: SHARED-USER-PREFS-ARE-TOP-LEVEL-ATOMICS
question: >
  Two products (Macro Dashboard templates/theme.js and the Mastermind Terminal) both write the
  shared appearance/language preference. supabase `auth.updateUser` REPLACES a nested object
  wholesale, so each product's write silently discarded the other's newer field. Where do the
  shared fields live, and under what names?
answer: >
  They move out of the nested `user_metadata.prefs` blob and become independently mergeable
  TOP-LEVEL `user_metadata` keys: `theme`, `theme_auto`, `lang`. `updateUser` MERGES top-level
  keys, so a writer that touches only the field it changed cannot clobber a sibling it never
  read. Both products now WRITE only the changed atomic(s) and READ "atomic if valid, else the
  legacy nested sibling" PER FIELD (not per blob). Nothing writes the nested blob any more; it
  survives as a read-only fallback. `theme` and `lang` reuse the names lib/user_prefs.py already
  treats as canonical rather than minting a parallel `ui_*` namespace. `theme_auto` is
  browser-only and deliberately stays OUT of `lib/user_prefs.PREF_VALUES`.
rationale: >
  The lost update is a race BETWEEN the products, so serializing either product's own writes
  cannot fix it, and a fresh-read-before-write only shrinks the window — read and write are not
  atomic. Removing the shared mutable container is the only repair that makes the invariant
  structural. The naming follows from an existing fact: app/account_prefs.py already writes
  top-level `lang`/`theme` and lib/user_prefs.py is documented as "the ONE reader/writer for a
  signed-in user's stored preferences" with the same closed value sets — so the browsers had a
  canonical representation available and were simply not using it. Adding `ui_*` would have left
  three representations of one preference.
alternatives:
  - option: keep the nested blob and have each product re-read it immediately before writing
    why_not: read and write are not atomic; this shrinks the window instead of closing it, and cannot be tested for
  - option: mint a fresh `ui_theme` / `ui_theme_auto` / `ui_lang` namespace (as the E handoff suggested)
    why_not: app/account_prefs.py already writes top-level `theme`/`lang`; a new namespace makes a THIRD representation of one preference
  - option: add `theme_auto` to lib/user_prefs.PREF_VALUES so all three share one table
    why_not: PREF_KEYS widens the chat tool's write surface; theme_auto is a browser presentation flag no server route writes
affects:
  - macro-dashboard
  - mastermind-terminal
  - templates/theme.js
  - lib/user_prefs.py
evidence:
  - "macro PR #6170 (templates/theme.js + tests/test_shared_pref_atomics.py)"
  - "mastermind-terminal PR #446 (lib/accountPrefs.ts readSharedPrefs / sharedPrefsPatch)"
  - "lib/user_prefs.py module docstring — top-level lang/theme, closed value sets"
  - "tests/test_account_prefs.py::test_metadata_write_merges_and_does_not_drop_other_keys"
confidence: high
reversibility: costly
decided_by: claude-opus-5
decided_at: 2026-08-21
---

Rollout note: both halves must ship together. A product still reading only the legacy nested
blob would miss the other product's v2 write, so the reader migration is what makes the writer
migration safe. The per-FIELD fallback is what makes a half-migrated account — the normal state
during the rollout, and the permanent state for any field a user never touches again — read
correctly; a per-blob fallback reads one of its fields wrong.

Scope note: this covers only the SHARED fields. The Terminal's own `user_metadata.terminal`
blob (`start_tf`, `updown`) stays nested, because the Terminal is its only writer — there is no
second product to race with, and its writes are serialized by terminal/lib/prefDelivery.ts.
