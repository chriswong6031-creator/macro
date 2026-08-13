---
key: PLAIN-COPY-ASSETS-SHIP-PAIRED
question: >
  How does a non-`.j2` asset under `templates/` that also ships verbatim as
  `site/<name>` get delivered — through the render lane, or as a paired commit?
answer: >
  As a paired commit: the byte-matching `site/` copy ships in the SAME pull request
  (`python -m scripts.check_template_site_sync --fix`; CI-guarded; render lanes self-heal
  the pairing post-rebase). Such a PR needs no render at all — the VPS pulls main every
  3 minutes, so the change is live within minutes whether render ever runs. The only
  forfeit is the `?v=` content-hash re-stamp, which matters only for the Caddyfile's
  enumerated `immutable` list, where warm caches keep the old body until a later render
  re-hashes the referencing pages. New visitors always get fresh bytes.
rationale: >
  `render.yml` produces exactly two things: re-baked `.j2` pages and the `?v=` re-stamp.
  For a plain byte copy neither is the delivery path — the VPS pull is. The render lane is
  shared and coalescing, so a session waiting on "its" render for a byte copy waits on a
  perpetually superseded run and reports a false blocker; fleet law now says do not wait
  and do not report it as one. The pairing guard exists for the other direction of the
  same fact: because `site/<name>` is served directly, an edit to `templates/<name>`
  without its `site/` twin silently ships nothing (or, worse, drifts the two). The guard
  enumerates the pairs (56 at last count) and CI enforces byte equality.
alternatives:
  - option: Deliver plain copies through the render lane like `.j2` pages
    why_not: >
      Blocks a byte copy behind a shared coalescing lane that may be superseded for hours;
      the artifact the lane produces (re-bake + re-stamp) is not the artifact being
      shipped. Sessions measurably stalled on this before the exemption entered fleet law.
  - option: Commit only the `site/` copy and treat `templates/` as dead
    why_not: >
      `templates/` is the authoring surface renders and sweeps read; a site-only edit
      resurrects drift the first time any lane rebuilds. The guard pins the pair for
      exactly this reason.
evidence:
  - "scripts/check_template_site_sync.py — added 2026-07-06 (git log --diff-filter=A); enumerates the pairs"
  - "Macro CLAUDE.md §Shared workspace + completion — 'A paired plain-copy asset PR needs no render at all'"
  - "Macro AGENTS.md §Shared render-lane safety — the Caddyfile immutable list, enumerated"
  - ".github/workflows/render.yml — the shared coalescing lane this decision routes around"
affects: ["templates/**", "site/**", "scripts/check_template_site_sync.py"]
confidence: high
reversibility: easy
decided_by: coo-fable
decided_at: 2026-07-06
---

## Grounds

Backfilled 2026-08-13 (Agent OS Phase 1). Dated to the guard's first commit (2026-07-06,
git-derived); the no-render exemption and the in-flight-render defer ruling (operator,
2026-07-27) refined the same law later and are part of the standing text cited above.
Attribution: CI-guarded fleet law with no single minting operator quote → coo-fable.

## What would reopen this

The VPS pull path changing (e.g. serving from a build artifact rather than the tree), or
the Caddyfile `immutable` list growing to cover most paired assets — at which point the
forfeited re-stamp would stop being a corner case and the render wait might earn its cost.
