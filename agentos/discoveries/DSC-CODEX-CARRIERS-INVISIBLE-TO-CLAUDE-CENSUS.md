---
key: CODEX-CARRIERS-INVISIBLE-TO-CLAUDE-CENSUS
claim: >
  A LIVE Codex worker holding a lane is invisible to every Claude-side collision instrument.
  Codex writes no `~/.claude/projects/<slug>/` directory for its working tree, so a session
  transcript census reports "no owner"; its exec shells are short-lived, so `lsof` (both
  `-d cwd` and unfiltered) returns ZERO handles on an actively-edited worktree; and grepping
  `~/.claude/projects/**.jsonl` for the worktree name hits only incidental `git worktree list`
  output in unrelated sessions, which reads exactly like nobody owning it. The owner lives in
  `~/.codex/sessions/<YYYY>/<MM>/<DD>/rollout-*.jsonl`. Two traps in reading those: the DATE IN
  THE FILENAME is the session START, not its activity - a file named
  `rollout-2026-08-25T19-00-47-*.jsonl` was actively writing at 2026-08-26T07:58Z, so only
  `mtime` is the liveness clock; and "zero commits, clean status" is NOT abandonment - the
  observed carrier went from uncommitted WIP to a clean single commit in the four minutes
  between two checks, then amended it, then opened a PR.
falsifier: >
  Finding a `~/.claude/projects/` entry whose slug matches a worktree only a Codex session has
  ever occupied, or `lsof | grep <worktree>` returning a live handle for an actively-editing
  Codex worker. Either would mean the Claude-side instruments do see Codex after all.
so_what: >
  A collision census MUST cross the vendor boundary or it is a self-portrait, not a census.
  Run all four planes before declaring a lane free: (1) `git worktree list` on the TARGET repo -
  a worktree named for your task is itself the warning; (2) that worktree's `git status`,
  `git log origin/<base>..HEAD`, and file mtimes vs `date`; (3)
  `grep -rl '<name>|issues/<N>' ~/.codex/sessions/<YYYY>/<MM> ~/.grok ~/.warp ~/.claude/projects`;
  (4) `ls -l` the matching rollout and judge liveness by mtime alone. This is the concrete
  mechanism behind the Terminal AGENTS.md line "facts that live only in one chat's memory are
  lost to the next session and to Codex".
kind: runtime
verified_at: 2026-08-26
verified_by: "mastermind-terminal #474/#475/#477 collision; owner located as codex rollout 01a03bcc-6a5b-7283-8285-e54a162892ea with 1736 mentions of the worktree name and mtime equal to the current minute"
scope:
  - macro
  - mastermind-terminal
  - Mastermind
confidence: verified
---

Recorded because the census very nearly returned CLEAR against an occupied lane: issue
unassigned, zero comments, no remote branch, zero path collisions across nine open PRs, no
`~/.claude/projects` entry, and no `lsof` handle. Every one of those signals was true and
every one of them was irrelevant. The single instrument that answered correctly was a grep of
another vendor's session store.
