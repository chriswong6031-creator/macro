# RWE-D0 Baseline — Approach D Spike Record + Bakeoff Adjudication Inputs (2026-09-01)

Program: mastermind-reproducible-worker-environments-20260830-sol-pro-001 (masterplan:
research/REPRODUCIBLE_WORKER_ENVIRONMENTS_MASTERPLAN_V1.md §5). This record preserves the
Approach-D disposable-spike measurements verbatim (spike executed and destroyed 2026-09-01;
kept artifact: hash lock sha256 01f3987ce4af8648…, 136,858 bytes, not committed — the P0
pilot mints its own per-platform locks in the Mastermind repo). Principal ruling: ACCEPTED
as the D0 baseline (carrier C0BSBM78V1N/1788260968). Rubric consequence: 'can the manager
express a pinned cross-repo vendored source input natively' is a discriminating row for
every candidate; Approach D requires an explicit companion vendor step (Mastermind ci.yml
already performs it: pinned checkout of macro @256c757b3c4f0ec759571c29a30a71387d0a18f8,
sparse engine+lib, into vendor/macro_src). Approach D's second boundary: the interpreter
itself stays ambient (Homebrew python3.12) — the I2 icu4c incident class remains open;
A/B/C candidates pin the interpreter by digest and are measured against exactly that gap.

---

# RWE-D0 Approach D disposable spike — measurement report

Date: 2026-09-01. Host: this Mac Studio. Source: Mastermind repo, disposable
`--no-hardlinks` clone at pinned commit `524b6dc8071d6ea0b484819630e9de846e1df93e`
("BSC-A1: protect Business OAuth resource-server library (#310)"). Interpreter
for every venv: `/opt/homebrew/bin/python3.12` (3.12.13). Lock compiled with
`pip-compile` (pip-tools 7.6.1) from `pyproject.toml` with `--extra dev`,
`--generate-hashes`.

All steps below ran in order per the frozen spec; the clone, both gate venvs,
the tools venv, and the fakebin dir were destroyed after measurement. Only
`rwe-d-spike.lock` (this report's sibling) survives from this spike.

## Timing table

| Stage | Wall time (`total` from `time`) | Notes |
|---|---|---|
| T_tools (venv + pip-tools install) | 7.12s | quiet pip install |
| T_lock (pip-compile --generate-hashes --extra dev) | **929s (≈15.5 min)** | dominated by hashing every wheel variant for every supported platform/Python tag per package (e.g. `websockets` alone contributed ~100+ `Hashing …` lines covering linux/musl/win/macos across cp311–cp315, s390x/ppc64le/riscv64 etc.) — see Findings |
| T_realize_cold (fresh venv, `--require-hashes --only-binary=:all:`) | 28.16s | + `pip install -e mm-spike --no-deps` (a few more seconds, wheel build for the editable shim); `pip check`: "No broken requirements found." |
| T_realize_warm (second fresh venv, warm pip cache) | 21.78s | ~23% faster than cold; both are wheel-cache-only installs (no compilation), so the warm/cold delta is modest |
| T_gate (full `scripts/ci_pytest.py`) | 45.72s wall, but **INTERRUPTED, exit 2** | see Findings — 2 collection errors, 0 tests actually executed |
| T_gate bounded-subset equivalence probe (`pytest tests/test_executive_service.py -q`) | 22.08s | 35/35 passed, exit 0 |
| T_gate dirty-PATH probe (same bounded subset) | 21.22s | 35/35 passed, exit 0, byte-identical output to the clean run |

## Package / lock facts

- 70 top-level pinned packages (direct + transitive from `dev` extra), 1,556
  total `--hash=sha256:` lines (cross-platform superset — pip-compile hashes
  every distributable wheel/sdist for the resolved version, not just the
  current platform's).
- Required pins present and exact: `mcp==1.28.1`, `pyjwt[crypto]==2.13.0`
  (dev extra), `pytest==9.1.1`.
- **Zero no-binary-wheel exceptions.** `pip install --require-hashes
  --only-binary=:all:` against the lock installed all 70 packages from cached
  wheels with no sdist fallback needed on macOS arm64 (cp312). No `--allow-unsafe`
  flag was needed for pip-compile either — it completed on the first try with
  only `--quiet --generate-hashes --extra dev`.
- `pip check` after both `-r lock` and `-e mm-spike --no-deps`: "No broken
  requirements found."

## Gate outcome (the central finding)

`scripts/ci_pytest.py` reported `discovered=416 excluded=0 running=416`, then:

```
==================================== ERRORS ====================================
___________________ ERROR collecting tests/test_self_tune.py ___________________
...
E   ImportError: cannot import name 'signal_archive' from 'engine' (unknown location)
______________ ERROR collecting tests/test_single_name_factor.py _______________
...
E   ModuleNotFoundError: No module named 'lib'
=========================== short test summary info ============================
ERROR tests/test_self_tune.py
ERROR tests/test_single_name_factor.py
!!!!!!!!!!!!!!!!!!! Interrupted: 2 errors during collection !!!!!!!!!!!!!!!!!!!!
```

Exit code 2. **This is a collection-time abort, not a small red count: pytest's
default behavior with no `--continue-on-collection-errors` runs zero of the 416
discovered tests once collection fails.** This is not a >10-minute timeout (it
failed in 45.7s), so the spec's ">10min → bounded subset" trigger technically
did not fire; I ran the named bounded-subset command anyway as the best
available equivalence probe, since the full gate produced no pass/fail signal
at all. Flagging this explicitly as a deviation from the literal trigger
condition (see DEVIATIONS in the final response).

**Root cause, confirmed by inspection (read-only, no repo edits):** `engine`
and `lib` do not exist as directories anywhere in the Mastermind clone —
`.gitignore` lists `vendor/macro` and `vendor/macro_src/`, i.e. Mastermind's
test gate expects a **non-pip, non-declarative, cross-repo vendoring step**
(populating a gitignored `vendor/macro[_src]` directory from this macro repo,
presumably via a symlink or sync script run outside `pyproject.toml`/pip)
before `loop/paper.py` (`from engine import signal_archive as sa`) and
`loop/single_name_panel.py` (`from lib import store  # noqa: E402 (vendored
macro parquet store)`) can import. A hash-pinned, `pip`-only "Approach D"
environment — however faithfully it reproduces the Python package graph —
does **not** close this gap, because the dependency is not a package at all;
it's an out-of-band filesystem vendoring convention this spike's frozen
9-step procedure never invokes (doing so would require reaching into the
occupied macro repo and/or running a Mastermind-side sync script not named
in scope, which is exactly the kind of scope expansion this commission
prohibits me from taking unilaterally).

Bounded-subset equivalence probe (`tests/test_executive_service.py`, one of
the explicitly protected prefixes in `ci_pytest.py`'s `PROTECTED_PREFIXES`):
**35 collected, 35 passed, exit 0** — clean, and does not touch `engine`/`lib`.

## Dirty-PATH resistance probe

`$SP/fakebin/python3` was a symlink to the ambient `/opt/homebrew/bin/python3`
(resolves to Python 3.14.7, confirmed via `readlink`). Running the bounded
subset via `env PATH="$SP/fakebin:/usr/bin:/bin" $SP/venv-gate/bin/python -m
pytest tests/test_executive_service.py -q` produced **byte-identical output**
to the clean run (`diff` of both logs, output-lines only: empty diff), same
35 passed / exit 0. A direct check under the same hostile PATH:

```
$ env PATH="$SP/fakebin:/usr/bin:/bin" $SP/venv-gate/bin/python -c "import sys; print(sys.version); print(sys.executable)"
3.12.13 (main, Mar  3 2026, ...) 
/private/tmp/.../scratchpad/venv-gate/bin/python
```

confirms the venv's own interpreter and site-packages fully determined the
outcome; the ambient 3.14 on a hostile PATH had zero effect. **Verdict:
identical — PATH-drift-resistant for the part of the gate this environment
can actually run.**

## Disk

- `venv-gate` (populated, before cleanup): 622M
- `mm-spike` clone (before cleanup): 101M
- `~/Library/Caches/pip` (shared, pre-existing + this run's downloads): 1.7G
- `rwe-d-spike.lock`: 136,858 bytes (~134K)

## Cleanup confirmation

`rm -rf` removed `mm-spike`, `venv-tools`, `venv-gate`, `venv-gate2` (already
removed after the warm-realization measurement per spec step 5), and
`fakebin`. All intermediate timing logs used to build this report were also
deleted (not requested as keepers). Final `$SP` listing:

```
total 464
-rw-r--r--  1 chriswong  wheel   35298  pr6715_checks.log   <- pre-existing, not from this spike
-rw-r--r--@ 1 chriswong  wheel  136858  rwe-d-spike.lock    <- KEPT (this spike)
-rw-r--r--  1 chriswong  wheel   60152  tree.txt            <- pre-existing, not from this spike
```

(`rwe-d-spike-report.md`, this file, is also kept, as instructed.)
`pr6715_checks.log` and `tree.txt` predate this spike (present at the very
first `ls` before any spike command ran) and were left untouched.
