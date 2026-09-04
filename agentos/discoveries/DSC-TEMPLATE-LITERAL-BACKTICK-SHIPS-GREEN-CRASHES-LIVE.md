---
key: TEMPLATE-LITERAL-BACKTICK-SHIPS-GREEN-CRASHES-LIVE
claim: >
  A markdown-style backtick inside a comment WITHIN a JavaScript template
  literal in a shipped asset terminates the string, turns the tail into a
  property access plus a tagged-template CALL of the string, and crashes the
  asset at load ("TypeError: <string> is not a function") — while `node
  --check`, syntax linting, and the entire Python CI suite stay green, because
  the construct is syntactically valid and no CI job executes the asset's
  runtime. Proven in production 2026-08-25: mm_brain.js's CSS template literal
  (templates/mm_brain.js:674/677) took the whole Brain widget down on every
  page for ~50 minutes behind a fully green merge (#6421), healed by #6428.
falsifier: >
  Reintroduce a backtick into the CSS template literal body of
  templates/mm_brain.js on a branch and run python3 -m pytest
  tests/test_mm_brain_asset.py -q — if that guard passes on the broken bytes,
  or a jsdom execution of the file mounts MMBrain anyway, this discovery's
  detection claim is wrong.
so_what: >
  Syntax-validity checks are NOT runtime proof for shipped JS assets. Any edit
  inside a template literal must use quotes, never backticks, in comments; any
  wave touching mm_brain.js (or a similar template-literal-heavy asset) should
  run the file under jsdom (node + jsdom from the terminal repo's node_modules
  suffices: eval the file, assert the mount flag) before merging, and the
  dependency-free span guard tests/test_mm_brain_asset.py must stay registered
  in the unrun-brain-gateway CI job. Real browser verification against the
  deployed surface is the only proof that catches this class end-to-end.
kind: constraint
verified_at: 2026-08-26
verified_by: >
  Production console TypeError at mm_brain.js?v=a87bf605:3837 with the CSS
  string as callee; byte-equal served-vs-merged comparison; jsdom execution
  crashing pre-heal and mounting post-heal (#6428 merge d00ca51e0f0c); guard
  test failing on pre-heal bytes (span closes at line 674, terminal anchor
  absent) and passing post-heal.
scope:
  - macro
  - "WS:DEEPVUE-INTELLIGENCE-WORKSPACE"
  - templates/mm_brain.js
  - tests/test_mm_brain_asset.py
confidence: verified
---

# Green CI ships a runtime-dead JS asset when a template literal eats a backtick

The failure is invisible to every static gate the repo runs; only executing the
asset (jsdom or a real browser) or the span guard catches it. Comments inside
template literals are shipped bytes with string semantics, not comments.
