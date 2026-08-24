---
key: GITHUB-DIR-CASE-COLLISION-IS-PHANTOM-WORKTREE-DIRT
claim: >
  The Mastermind repo tracks two paths that differ only by case —
  `.github/PULL_REQUEST_TEMPLATE.md` (short "## Change" template, blob md5
  49679816fd61cef038ebc460ee642f86) and `.github/pull_request_template.md`
  (long Mastermind-X tracked-work template, blob md5
  ff7b15b65fb439085f4a067f06f6309f) — so on macOS's case-insensitive
  filesystem a checkout materializes BOTH tracked paths onto ONE on-disk file
  (last writer wins, the lowercase long template), and `git status` then
  reports the OTHER path (`.github/PULL_REQUEST_TEMPLATE.md`) as permanently
  ` M` modified in every fresh worktree. It is a filesystem aliasing artifact,
  not any session's uncommitted work: the on-disk md5 equals the lowercase blob
  exactly, and four independent sibling Mastermind worktrees (mas109-c1,
  mas108-b1-freshness, macro-credential-seam, ccr-h0) show the identical
  ` M .github/PULL_REQUEST_TEMPLATE.md` at the identical md5.
falsifier: >
  In a fresh Mastermind worktree on macOS, `git ls-files | grep -i
  pull_request` shows only one path (not both case variants), OR
  `md5 -q .github/PULL_REQUEST_TEMPLATE.md` does NOT equal the blob md5 of
  `git show HEAD:.github/pull_request_template.md`. Either refutes the
  case-collision attribution and means the dirt is a real edit to investigate.
so_what: >
  A session inspecting a Mastermind worktree must NOT treat this ` M` entry as
  another session's abandoned work, must NOT delete/overwrite it, and must NOT
  block a stop or a commission on it — restore it with
  `git checkout -- .github/PULL_REQUEST_TEMPLATE.md` and proceed. This exact
  phantom was mis-flagged as a mystery "uncommitted PR template" at the
  MAS-125 A0 security stop and had to be re-diagnosed from scratch on the A0
  recovery run before a clean worktree could be established. The durable
  root-cause fix (a separate, non-ASD bounded wave, since `.github/` on the ASD
  carrier is hot) is to drop one of the two case-colliding tracked paths so only
  a single `pull_request_template` path is tracked.
kind: landmine
verified_at: 2026-08-23
verified_by: "MAS-125 A0 recovery run: git ls-files + md5 blob comparison across 5 Mastermind worktrees; Sol review 5001858914 recovery gate 1"
scope:
  - mastermind
  - WS:CHAIRMAN-CONTROL-ROOM
  - MAS-125
  - .github/**
confidence: verified
---

## Why this crosses the account boundary

The MAS-125 A0 security stop (Mastermind PR #125) flagged an "uncommitted
`.github/PULL_REQUEST_TEMPLATE.md`" as unexplained dirt requiring reconciliation
before recovery. Two independent sessions spent investigation effort deciding
whether it was another session's work. It is not — it is a deterministic macOS
case-insensitive-filesystem artifact that reappears in every Mastermind worktree
and will keep costing reconciliation time until one of the colliding paths is
removed. Recording it here (the cross-repo knowledge plane) stops the next
session from re-litigating it.

## Non-goal

This record does not itself remove either path. Editing `.github/` on the live
ASD carrier (`sol/asd-a0a1-20260823`) risks colliding with active Active-Session
Dialogue work; the deduplication belongs to a separately scoped wave against
protected Mastermind master.
