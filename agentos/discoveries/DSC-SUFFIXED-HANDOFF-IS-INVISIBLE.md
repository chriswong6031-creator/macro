---
key: SUFFIXED-HANDOFF-IS-INVISIBLE
claim: >
  An Agent OS handoff whose filename carries anything after the date —
  agentos/handoffs/<WS-KEY>-<YYYY-MM-DD>-<suffix>.md — is silently dropped by the
  compiler as `older_handoff`, no matter how new it is, so a second same-day session
  that writes a suffixed sibling instead of amending the dated file leaves its record on
  disk and invisible in compiled state.
falsifier: >
  Write agentos/handoffs/<WS-KEY>-<today>-anything.md alongside an existing
  <WS-KEY>-<today>.md and run `python3 scripts/agentos.py compile-context --workstream
  WS:<KEY>`; if the suffixed file is served as the LATEST HANDOFF (rather than appearing
  under `excluded` with reason `older_handoff`), this record is false.
so_what: >
  A second (third, Nth) same-day session on a workstream AMENDS the existing
  <WS-KEY>-<YYYY-MM-DD>.md in place — extend `session:`, add its PR to `prs:`, append
  ADDENDUM-prefixed entries to changed/verified/unresolved/next_actions/do_not_redo/
  danger_areas, add a marked addendum block in the body — and never creates a suffixed
  sibling. When inheriting a workstream, `compile-context` is not proof the newest record
  was read: check `ls agentos/handoffs/<WS-KEY>-*` for suffixed strays and fold them in.
  Budget matters too — the handoff excerpt is clipped at EXCERPT_HANDOFF=1600 chars over
  mission + state_before + next_actions + do_not_redo + danger_areas + unresolved in that
  order, so a long mission/state_before evicts exactly the fields a cold start needs; keep
  addenda to those two fields short and put live items first in the lists.
kind: landmine
verified_at: 2026-08-14
verified_by: >
  scripts/agentos.py:2231 `HANDOFF_DATE_RE = re.compile(r"-(\d{4}-\d{2}-\d{2})$")` (anchored
  at end-of-stem) with :3314 `handoff_rank` returning ("", stem) on no-match, so any
  suffixed stem sorts below a bare-dated one at :3319 `max(mine, key=handoff_rank)` and is
  dropped at :3323. Observed live on WS:EVAL-OS-MEASUREMENT-LAW: with both
  WS-EVAL-OS-MEASUREMENT-LAW-2026-08-14.md and -2026-08-14-P0D.md present,
  compile-context excluded the P0D record with
  `older_handoff (latest: WS-EVAL-OS-MEASUREMENT-LAW-2026-08-14)` and served the PRE-P0d
  record, whose next_actions still asked for the ruling the P0d session had already
  executed. agentos/schema/handoff.schema.yml declares `file:
  agentos/handoffs/<WS-KEY>-<YYYY-MM-DD>.md` with no suffix form. Repaired in the same
  change that mints this record: the P0D content folded into the dated file, the suffixed
  sibling deleted, compile-context re-run to 0 exclusions.
scope: [macro, mastermind, terminal, agentos/handoffs/]
confidence: verified
---

## Detail

The ranking is the whole mechanism. `handoff_rank(stem)` returns `(date, stem)` when the
stem ENDS with `-YYYY-MM-DD`, and `("", stem)` otherwise. `max()` over that tuple puts
every properly-named handoff above every suffixed one, so the suffix does not merely sort
oddly — it removes the file from consideration entirely, and the compiler then reports the
loss in `excluded` rather than failing. Nothing is corrupted and nothing errors: the
record simply never reaches a reader.

The failure is worst in exactly the case that produces suffixes. A session naming its file
`-P0D`, `-mychip`, or `-wave2` is a SECOND session working the same workstream on the same
day — which is to say, the one holding the newest state. That is how a workstream can
carry a fully-written contract, `do_not_redo` list and danger areas on disk while a
cold-start session is handed the previous session's "open design question" as its
orientation.

Two adjacent facts a repairing session needs:

* **The schema already forbids it.** `agentos/schema/handoff.schema.yml` names the file
  form `agentos/handoffs/<WS-KEY>-<YYYY-MM-DD>.md`. The suffix is a schema deviation that
  `validate` does not currently catch, so the compiler's silent drop is the only signal.
* **Folding in is not appending.** Preserve the first session's fields verbatim and mark
  the second session's entries (`ADDENDUM #<pr>`), rather than rewriting the record in the
  newer session's voice — the older session's `verified:` claims name commands that were
  run, and a rewrite would quietly reattribute them.

Related: `DEC:AGENTOS-CLAIMS-ARE-NOT-LIVE-ACTIVITY` (a record is an author's note, never
evidence of a live worker) and `research/MASTERMIND_AGENT_HANDOFF_PROTOCOL.md` (the
protocol the filename is part of).
