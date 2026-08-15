---
key: SEALED-RUNTIME-WINS-OVER-MODULE-LOAD-PIN
question: >
  When a new `scripts/**` entry script imports repo packages but must not pin
  the checkout at module load — because it starts under `python -I -S` and
  authenticates the sealed runtime plus the exact clean checkout before any
  repository path is installed — which contract wins: the #5046 import-pin
  ratchet, or the sealed-runtime auth-before-path invariant?
answer: >
  The sealed-runtime auth-before-path invariant wins for a named, reasoned
  exception. The #5046 ratchet remains shrink-only for every other
  `scripts/**` entry script. The exception is a first-class waiver registry
  (`config/script_import_pin_sealed_runtime_waivers.yml`, same shape as
  `config/unrun_test_waivers.yml`: path → non-empty reason), not a T2
  baseline extension and not a silent frozenset. Each waived path must stay
  in the T2 affected set (still no strong pin), must not appear in the T2
  baseline, and is proved by a stronger delayed-import contract (attestation
  before path install; `python -I -S` module load adds no repo path and
  imports no repo package).
rationale: >
  The two contracts look like they ask for the same pin. They do not. #5046
  exists because `python3 scripts/foo.py` puts `scripts/` at sys.path[0] and
  the repo root nowhere, so a top-level `engine`/`lib`/`scripts` import
  resolves from ambient PYTHONPATH or a foreign editable install — observed
  executing another repository's code from inside a CI guard. The prescribed
  fix is an unconditional module-load `sys.path.insert(0, <__file__-derived>)`
  before any repo import. Conditional or in-function inserts are rejected as
  weak pins because a root already present further down sys.path still loses
  to a foreign package ahead of it.

  The sparse-selector canary (`scripts/run_options_sparse_selector.py`, PR
  #5696) has the opposite threat model. It is launched as
  `exec "$SEALED_PYTHON" -I -S -B "$RUNNER" --run-once`. Isolate mode ignores
  PYTHONPATH; `-S` installs no site-packages. The module docstring states
  that stdlib-only imports run at load, and that "the sealed runtime and
  clean, receipted checkout are authenticated before repository paths and
  site-packages are added for the delayed selector imports. That ordering is
  load-bearing for python -I -S operation." Path *presence* is the boundary,
  not merely import statements: `_load_runtime` inserts the attested
  `RUNTIME_SITE_PACKAGES` and `EXPECTED_REPO_ROOT` only after
  `_attest_runtime_carrier` has proved the carrier and that `sys.executable`
  is the sealed Python. A `__file__`-derived module-load pin would add
  whichever tree the file was launched from *before* that attestation — an
  unauthenticated checkout, which is exactly the object the runner refuses
  to trust. Option (a) — "a pin form the sealed design can tolerate" — is
  therefore not available: the ratchet's required pin *is* the forbidden
  act. Option (c) — relocate the canary out of `scripts/**` so the census
  cannot see it — would hide the file without a stronger proof and let the
  next sealed runner land the same way. Option (b) is the only honest
  reconciliation: keep the ratchet's teeth, and replace the generic pin for
  this one named path with a stronger, reviewed exception.

  #5701 taught T2 about the exception via a hardcoded frozenset so CI would
  go green. That was the right ruling and the wrong registry: `--emit-baseline`
  still emitted the canary, so regenerating the T2 list would silently
  grandfather it and let the frozenset be deleted later. The waiver file
  closes that hole the same way `config/unrun_test_waivers.yml` closed the
  unrun-census hole: a reason is mandatory, the row is printed as an
  exception, and the burn-down list cannot absorb it.
alternatives:
  - option: >
      Add the ratchet's module-load `__file__`-derived pin to the canary
      (option a — a pin the sealed design can tolerate)
    why_not: >
      The sealed docstring names path installation, not just imports, as
      post-attestation. A `__file__` pin adds an unauthenticated tree at
      import time and inverts the `-I -S` boundary. Verified: under
      `python -I -S`, module load of the current runner leaves the repo root
      off sys.path and imports no repo package; a module-load pin would
      invert both observations.
  - option: >
      Relocate the canary out of `scripts/**` so the T2 census cannot see it
      (option c)
    why_not: >
      The launchd unit invokes a path under the dedicated checkout's
      `scripts/`. Moving the file is a deployment change that hides the
      conflict instead of ruling on it, and the next sealed runner under
      `scripts/**` would trip the same red.
  - option: >
      Extend the T2 baseline with the canary
    why_not: >
      The T2 assertion message forbids baseline extension. A baseline row
      is an unpinned leftover awaiting a pin, not a reviewed exception.
      Regenerating would also let the exception disappear later with no
      reason left behind.
  - option: >
      Leave #5701's in-test frozenset as the registry
    why_not: >
      A frozenset has no reason string, and `--emit-baseline` still listed
      the canary, so a later regenerate would move it into the shrink-only
      list and un-teach T2. Same failure mode the unrun census closed with
      a path→reason file.
evidence:
  - "scripts/run_options_sparse_selector.py:11-15 — sealed docstring: stdlib-only at load; paths added after auth; load-bearing for python -I -S"
  - "scripts/run_options_sparse_selector.py:752-760 — _load_runtime inserts RUNTIME_SITE_PACKAGES then EXPECTED_REPO_ROOT, then imports engine/lib"
  - "scripts/run_options_sparse_selector.py:1672-1683 — _static_preflight calls _attest_runtime_carrier before _load_runtime"
  - "ops/launchd/run_options_sparse_selector_loop.sh:32 — exec \"$SEALED_PYTHON\" -I -S -B \"$RUNNER\" --run-once"
  - "tests/test_check_script_import_pinning.py::_strong_pin — conditional or in-function insert is not a strong pin"
  - "tests/test_check_script_import_pinning.py::_repo_imports — deferred imports inside functions still count as 'imports repo packages'"
  - "PR #5046 — T0–T4 ratchet; T2 shrink-only; no waiver mechanism at birth"
  - "PR #5696 — sealed-runtime v2 runner that created the conflict"
  - "PR #5698 — first classified ci-pack red on the unrun-import-hygiene pin step"
  - "PR #5701 — hotfix frozenset exemption + AST proof; correct ruling, incomplete registry"
  - "config/unrun_test_waivers.yml — the path→reason shape this exception copies"
affects:
  - "tests/test_check_script_import_pinning.py"
  - "config/script_import_pin_sealed_runtime_waivers.yml"
  - "scripts/run_options_sparse_selector.py"
  - "tests/fixtures/script_import_pin_baseline.txt"
confidence: high
reversibility: easy
decided_by: session
decided_at: 2026-08-15
---

## Grounds

The conflict is structural, not a missing pin. Deferred `engine`/`lib` imports
inside `_load_runtime` still place the canary in T2's affected set
(`_repo_imports` walks every statement, not just the module body). The
ratchet then demands a top-level unconditional `__file__` insert the sealed
design forbids. Owning one design means naming the exception and proving the
stronger contract, not weakening `_strong_pin` and not extending the
baseline.

## What would reopen this

A rewrite of the canary that can attest the checkout *and* still carry a
strong module-load pin (then delete the waiver row and pin the file). A
second sealed runner under `scripts/**` (then add a waiver row with a
reason *and* a dedicated proof test — the singleton assertion will red
until both exist). A finding that `-I -S` is no longer how the canary is
launched (then the generic pin becomes the right contract again).
