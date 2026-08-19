---
key: FLOATING-PYTHON-PIN-BREAKS-A-SEALED-RUNTIME
claim: >
  ci.yml pinned `python-version: "3.12"`, so a GitHub hosted tool-cache bump to
  CPython 3.12.14 produced a runtime fingerprint that
  engine/capital_structure/document_terms.py's
  _PARSER_V1_1_0_RUNTIME_ALLOWLIST does not carry; the parser fails closed and
  reds 22 tests in whichever pack currently owns capital-structure-intelligence,
  on every PR at once, regardless of its diff.
falsifier: >
  A ci-pack log showing `pythonLocation: /opt/hostedtoolcache/Python/3.12.13`
  (or any version_info tuple present in _PARSER_V1_1_0_RUNTIME_ALLOWLIST) while
  tests/test_capital_structure_document_terms.py still raises
  "document-term parser runtime fingerprint is not released" — that would show
  the trigger is something other than the interpreter version.
so_what: >
  Do NOT bisect a "document-term parser runtime fingerprint is not released" red
  against the PR's diff, and do NOT widen the allowlist to make CI pass: read
  `pythonLocation` in the failing pack log first. The allowlist is a
  tamper-detection seal owned by the Capital Structure Intelligence lane, and
  adding a release to it is a review act with provenance, not a CI fix. The CI
  fix is to pin an exact patch release the allowlist already carries.
kind: landmine
verified_at: 2026-08-19
verified_by: >
  ci-pack-8 on PR #5737 head 578234b44016 (run 32212339287) and on PR #5903 head
  820187f1511d (run 32212323109) — two independent heads, identical failure list
  headed by
  tests/test_capital_structure_document_terms.py::test_complete_submission_is_the_fee_table_parser_path_and_preserves_decimal_strings
  with "ValueError: document-term parser runtime fingerprint is not released".
  Both logs report `pythonLocation: /opt/hostedtoolcache/Python/3.12.14/x64` and
  `platform linux -- Python 3.12.14`. The allowlist at
  engine/capital_structure/document_terms.py:2404 carries only 3.12.2, 3.12.3,
  3.12.4 and 3.12.13. engine/capital_structure/document_terms.py itself has not
  changed since 2026-08-05 (3af1bb411c0d).
scope:
  - macro
  - .github/workflows/ci.yml
  - engine/capital_structure/document_terms.py
confidence: verified
---

## Why the seal is doing its job

`ParserRuntimeFingerprint` is `(implementation, version_info, cache_tag, stdlib_source_sha256)` — the CPython ABI identity plus the SHA-256 of specific stdlib source files on disk (`_markupbase.py`, `html/*.py`, `re/__init__.py`). Its whole purpose is to refuse a stdlib it has not reviewed. A patch bump changes both `version_info.micro` and every stdlib digest, so an unreviewed interpreter is exactly what it is built to reject. Nothing was broken; CI simply started running something nobody had reviewed.

## Why production stayed green

The self-hosted lanes run Homebrew CPython **3.12.13**, which the allowlist carries — the existing entry's comment even says "Homebrew and GitHub Actions setup-python CPython 3.12.13". So the nightly kept generating `data/capital_structure/*` normally while hosted CI was red. The floating pin had quietly made hosted CI test a runtime **production does not use**.

## The ordering rule

Moving the pin is a two-step act, in this order:

1. Add the target release to `_PARSER_V1_1_0_RUNTIME_ALLOWLIST` with provenance — the 3.12.13 entry records `actions/python-versions 3.12.13-27650778726, archive SHA-256 ce7d511228f095b5ea1ad5568543388870f5964688303f9ddc24ba06c336bfba`. The bundle values (`implementation_sha256`) differ per release and can only be produced by RUNNING that interpreter, so this cannot be done from source inspection alone.
2. Then bump `python-version` in `.github/workflows/ci.yml`.

`tests/test_ci_pack.py::test_ci_python_is_pinned_to_a_released_parser_runtime` enforces that order: it parses the allowlist out of `document_terms.py` with `ast` (never importing it — importing seals against the *running* interpreter, so on an unreleased CPython the import is the very thing under test) and fails if ci.yml's pin is floating or names an unreleased release.
