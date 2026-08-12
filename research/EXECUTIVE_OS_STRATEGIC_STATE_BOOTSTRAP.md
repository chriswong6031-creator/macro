# EXECUTIVE OS — STRATEGIC STATE BOOTSTRAP (pointer)

**The document and the implementation live in the Mastermind repo:**
`/Users/chriswong/Documents/Cluade/Mastermind/research/EXECUTIVE_OS_STRATEGIC_STATE_BOOTSTRAP.md`
· Mastermind PR #21 · branch `claude/executive-os-strategic-state-f9a207`.

This is a signpost, not a copy. Duplicating the content here would violate charter P7
(one source of truth per concept) and start the drift the Executive OS exists to stop.

## Why the artifact is not in this repo

Phase 1 of the Executive OS shipped `config/strategic_state.yml`,
`control_plane/strategic_state.py`, `tests/test_strategic_state.py`, and the
`AGENTS.md`/`CLAUDE.md` § "Executive contract" — all in **Mastermind**, because:

- every reuse target named in the commission is there (Charter V2, `DOCTRINE.md`,
  `config/authority_map.yml`, `config/agents.yml`, `brain/improvement_agenda.py`,
  `control_plane/governance.py`);
- the future consumer is there (Phase 1A's `control_plane/worker_runtime.py`, on
  Mastermind `master`; Phase 1B extends it);
- `research/EXECUTIVE_OS_PHASE0_CENSUS.md` §5 item 2 — the predecessor to this work,
  still open as PR #5356 — already named `Mastermind/config/strategic_state.yml`;
- a strategic state *here* read by a runtime *there* is a cross-repo authority hop,
  which is the literal shape of the `duplicate_control_planes: prohibited` constraint
  the file itself declares.

## What this repo got

A cross-reference only, per census §5 item 10: `CLAUDE.md` § "House laws" and
`AGENTS.md` § "Required context at the start of every task" now point at the
Mastermind strategic state and executive contract, and state the standing prohibition
on building a second one here.

**Macro fleet law is unchanged** — ship loop, model routing, merge-on-green,
worktree-per-session, and every guard in `.claude/hooks/` still govern sessions in
this repository exactly as before. The executive contract sits above that layer; it
does not replace it.
