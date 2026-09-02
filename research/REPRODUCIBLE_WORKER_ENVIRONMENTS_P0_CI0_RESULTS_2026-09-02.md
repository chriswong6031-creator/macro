# RWE-P0 / RWE-CI0 Results + Adoption Ruling (2026-09-02)

Program `mastermind-reproducible-worker-environments-20260830-sol-pro-001` (masterplan:
`research/REPRODUCIBLE_WORKER_ENVIRONMENTS_MASTERPLAN_V1.md`; D0 baseline:
`research/REPRODUCIBLE_WORKER_ENVIRONMENTS_D0_BASELINE_2026-09-01.md`; approach ruling:
`DEC:RWE-PILOT-APPROACH-D`). Fable COO principal under the 2026-09-01 Chairman
full-completion override. Carrier: Slack `C0BSBM78V1N/1788258537.508239`.

## P0 — what shipped (Mastermind PR #342, squash `722f15d531a1`, 2026-09-02T04:58Z)

- `requirements/gate-macos-arm64-py312.lock` + `requirements/gate-linux-x86_64-py312.lock`
  — pip-compile `--generate-hashes --extra dev` locks (73 pins / 1,556 hash lines each;
  bodies currently identical across platforms — expected and disclosed), each header
  carrying platform, interpreter, source-`pyproject.toml` sha256, and regeneration command.
- `scripts/rwe_env.py` — stdlib-only `lock` / `realize` / `receipt` / `gate` CLI.
  Fail-closed: non-CPython-3.12 interpreter refuses on realize AND receipt AND gate;
  missing platform lock refuses; out-of-repo `--lock` refuses; recomputed lock digest
  mismatch vs the receipt refuses; stale lock (pyproject digest header ≠ live file)
  refuses realize. Realize = fresh venv, `--require-hashes --only-binary=:all:`, then
  `-e . --no-deps --no-build-isolation` with pinned `setuptools==84.0.0`/`wheel==0.48.0`
  recorded under `build_backend`.
- `mastermind.worker_environment/v1` receipt — secret-free by construction and by test:
  path CLASSES (`homebrew`/`framework`/`toolcache`/`other`), `<env>`/`<subset>`
  placeholders, scrubbed+truncated `pip_check`, split-case forbidden-token guard.
  Identity: `environment_id = f(lock digest, platform triple, full interpreter version
  incl. patch)`. Vendored input is first-class: `{repo, ref (parsed from ci.yml at
  runtime), resolved_ref (git rev-parse of the actual tree), match, present}`.
- `.github/workflows/rwe-shadow.yml` — non-displacing shadow lane (ci.yml untouched,
  never required): realizes from the committed linux lock, materializes the pinned
  vendor checkout with the ref parsed out of ci.yml at runtime, runs the FULL
  repository gate, uploads the receipt artifact.
- `docs/RWE_RUNBOOK.md` — fresh-worker one-command path per platform + regeneration,
  refusal semantics, rollback (delete the venv; locks are additive files).

**Review chain (independent, opus):** REQUEST_REPAIR at `29caa02a` (5 major / 6 minor /
3 nit — including a probe-demonstrated receipt path leak, fail-open interpreter checks
on receipt/gate, an interpreter-blind environment_id, pyproject-drift blindness, and an
unmeasured vendor ref) → repairs `add91c5d` → delta review caught 2 repair-introduced
regressions (HOME/homebrew false-positive; unanchored summary parser hijackable by
traceback lines) → fixes `0a360b44` → **PASS re-probing every major, zero findings,
63/63 unit tests.** Merge waited additionally for a green full-gate shadow run at the
final code and the required CI check (one rerun consumed by the known rotating
master-side Node flake `test_web_sol_extension_reconstitution.py`).

## CI0 — parity evidence (receipts, same merged code)

| Field | mac (local) | CI (ubuntu, run 33590301387) |
|---|---|---|
| environment_id | `45add2e16d4a1bfa` | `d6234cec27cdeb3c` |
| pyproject sha256 | `d5d346c445dfce58…` | `d5d346c445dfce58…` (equal) |
| lock | `gate-macos-arm64-py312.lock` | `gate-linux-x86_64-py312.lock` |
| interpreter | CPython **3.12.13** / homebrew | CPython **3.12.14** / toolcache |
| packages | 76 (freeze sha `2358c541…`) | 76 (freeze sha `4966b0f5…`) |
| vendored input | pinned ref recorded; absent → `degraded: full_gate_unavailable:vendor_absent` | `resolved_ref == ref` (`256c757b…`), `match: true` |
| proof | bounded subset 35/35 exit 0 | **FULL gate `discovered=452 exit=0` in 1063.7s** |
| build_backend | setuptools 84.0.0 / wheel 0.48.0 | identical |

**Parity class: `SEMANTIC_EQUIVALENT` with explicit platform differences** — the
charter's bar. The historically silent drift classes are now visible receipts: the
hosted tool-cache is already one patch ahead of the Mac (3.12.14 vs 3.12.13 — the exact
I1 incident shape), and the receipt exposes it instead of letting a sealed runtime
discover it the hard way. Dirty-PATH resistance was proven byte-identical in D0 and the
mechanism (venv-pinned interpreter) is unchanged.

## Adoption ruling (principal, under the Chairman override)

- **PROMOTE, pilot scope:** the hash-locked receipted environment is the accepted way
  to realize the Mastermind test-gate toolchain (runbook path + shadow lane). The
  existing `pip install -e ".[dev]"` CI path is intentionally untouched.
- **Wider adoption deferred to RWE-E0** (value study with real workers); the largest
  candidate surface is macro `.github/ci/legacy-jobs.yml`'s ~194 unpinned pip lines.
- **Devbox = deferred conditional upgrade path** (interpreter closure; 1s realize in
  D0), **gated on Program 4 supply-chain admission** — which still has no carrier;
  sequencing surfaced to the portfolio principal.
- **devenv and raw Nix flake: `REJECTED_BY_DESIGN` as pilot approaches** per
  `DEC:RWE-PILOT-APPROACH-D`.

## Honest residuals (nonblocking, recorded)

1. Mac-side FULL gate needs a local `vendor/macro_src` materialization (runbook'd, not
   yet exercised locally; CI proves the full path).
2. `check_pyproject_not_stale` refuses on ANY pyproject byte change until locks are
   regenerated — deliberate fail-closed sharpness to know before adoption widens.
3. Hash-mismatch refusal rests on pip's `--require-hashes` enforcement; not separately
   falsified with a tampered lock.
4. The interpreter itself remains ambient (Homebrew/tool-cache) — mitigated by
   fail-closed identity verification + receipt visibility; full closure is the Devbox
   upsell, gated on admission.
5. Master's test gate carries rotating Node-side flakes unrelated to this program; the
   shadow lane inherits them (two rerun-consumed instances during this program).
