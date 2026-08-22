---
key: CI-SELF-MOD-FENCE-ARGV-BYPASSES-BOUNDED-TRANSPORT
claim: >
  A file-backed upstream list does not close execve risk if a terminal policy
  invocation rematerializes that list or another unbounded input in argv: at FF
  PR 5898 head 47d3b4b49e7191e72576ebc6e7495748ab1c8164, fences run 32546500471
  expanded both changed paths and full commit-message text into
  check_self_mod_fence.py argv and died with E2BIG before Python started, while
  the semantic CI and the fence test suite were green. The fork live path
  retained the same unbounded transport shape.
falsifier: >
  Re-read run 32546500471 and show that check_self_mod_fence.py started and
  emitted its own policy verdict before exit 126, or inspect the workflow bytes
  used by that run and show that both live self-mod paths passed only bounded
  file, stream, or digest handles rather than expanding the complete changed-file
  or commit-message populations into argv.
so_what: >
  Treat DSC:CI-CHANGED-FILES-ENV-HAS-AN-EXECVE-CEILING as the general transport
  law, but audit every workflow that independently recomputes or forwards an
  unbounded population. Changed files stay in the canonical JSON file
  representation, complete commit-message text stays file-backed, only bounded
  handles cross argv or the environment, and both source wiring and real
  process-launch regressions must forbid restoration of either population.
kind: landmine
verified_at: 2026-08-21
verified_by: >
  GitHub fences run 32546500471 at subject
  47d3b4b49e7191e72576ebc6e7495748ab1c8164 (self-mod live exit 126,
  "Argument list too long", before checker output); source inspection of both
  live paths in .github/workflows/fences.yml; and python3 -m pytest
  tests/test_self_mod_fence.py tests/test_fence_checkout_contract.py -q
  (retired argv raises errno E2BIG, both file-backed workflow paths launch,
  and all 73 tests pass).
scope:
  - macro
  - ci-merge-control-plane
  - ".github/workflows/fences.yml"
  - "scripts/check_self_mod_fence.py"
confidence: verified
---
