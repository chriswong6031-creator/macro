# Reproducible Worker Environments — Program Masterplan V1 + RWE-A0 Census (2026-09-01)

## §0 Program identity and acceptance gates

- **Operation:** `mastermind-reproducible-worker-environments-20260830-sol-pro-001` (annex 5 of the
  Fable COO seven-programs portfolio, parent
  `mastermind-autonomy-intelligence-robustness-portfolio-fable-coo-20260901-001`).
- **Delegated principal op:** `mastermind-reproducible-worker-environments-fable-coo-end-to-end-20260901`.
- **Principal:** Fable COO (Chairman direct delivery 2026-09-01, session `e0901edc…`).
- **Carrier root:** Slack `#agent-dispatch` `C0BSBM78V1N/1788258537.508239` (ACK → START → WATCH_ARMED posted).
- **Terminal states allowed:** `PROVEN_LIVE` pilot with measured value, or `REJECTED_BY_DESIGN`
  with a tested accepted alternative. Open PRs, green CI, installed tools, and specs are not completion.
- **NOT DONE UNLESS (program):** exact environment source/lock identity; two-host or host+CI
  realization with equivalent declared binary versions/digests; explicit platform differences;
  cache/offline behavior evidence; zero credentials/provider homes inside the environment;
  upgrade/rollback generation proven; documented adoption scope.

### Hard boundary (charter §15, non-negotiable)

The environment system may own user-space build/test packages, language runtimes, compilers,
package-manager versions, deterministic task commands, secret-free env vars, cache inputs,
lock/digest identity, disposable test processes. It must NEVER own: Job/Attempt/Worker lifecycle,
worker/Sol identity, provider accounts/homes, OAuth/keys/Keychain, browser profiles, launchd
production services (Executive host install stays with `ops/executive_os/HOST_PREREQUISITES.md`),
privileged users/sockets, deployment, RuntimeBinding, network authority, or code/source truth.

### Cross-program gate

External environment managers (devenv / Devbox / Nix) are third-party artifacts and require
**Program 4 (supply-chain admission)** before becoming trusted dependencies. No Program 4 carrier
exists yet (verified 2026-09-01). Until admission exists, bakeoff work runs only as **disposable,
isolated, destroyed-after research spikes** (portfolio charter §10) and nothing installed in a spike
may be mistaken for an admitted production dependency.

## §1 Capability ledger (RWE-A0 verdicts, 2026-09-01)

| Capability | State | Evidence anchor |
|---|---|---|
| Hash-pinned isolated env for narrow proof lanes | `PROVEN_LIVE` (macro only, 4 lanes) | `requirements/*.lock` installed `--require-hashes --only-binary=:all:`; header states isolation intent |
| Root dependency manifests | `PARTIAL` (range-pinned) | macro `requirements.txt` (2 exact pins of 24); Mastermind `pyproject.toml` (1 exact base pin) |
| Hosted-CI Python pin discipline | `PARTIAL` | macro `ci.yml` exact `3.12.13` (post-incident); `legacy-jobs.yml` still floating `"3.12"` at ~30 sites |
| Legacy CI dependency management | `BROKEN`-adjacent | `.github/ci/legacy-jobs.yml`: ~194 ad-hoc unpinned `pip install <list>` lines, no manifest |
| Production (self-hosted) env provisioning | `PARTIAL`, drift-accumulating | persistent `$HOME/.cache/mm-venv-${RUNNER_NAME}` venvs, never rebuilt fresh; `/opt/homebrew/bin/python3.12` hardcoded |
| Local/CI parity | `PARTIAL`, receipted-broken twice | incidents I1, I2 below |
| Cross-host reproducible environment (coherent system) | `NOT_BUILT` | no flake/devenv/devbox/pixi file in any repo |
| Exact environment receipt | `NOT_BUILT` (proto-receipts exist) | lockfile headers + `_PARSER_V1_1_0_RUNTIME_ALLOWLIST` sealed-runtime check are partial precedents |
| Nix on the Mac Studio host | verified **absent** | `which nix` empty; `/nix` does not exist |
| Whole-company Nix migration | `REJECTED_BY_DESIGN` | charter §15.2 (pilot-first law) |
| Candidate pilot toolchains (Inspect/promptfoo/Quint/TLC/Apalache/Z3) | `SPEC_ONLY` | zero code/manifest references in Mastermind; prose only in two `docs/superpowers/specs/` files |
| Worker setup runbook (Mastermind) | `NOT_BUILT` | zero `.md` files contain "pip install"/"venv"; only executable truth is `ci.yml` |

## §2 Estate census (condensed; full scout packets in session record)

**Macro** (97 workflows + `legacy-jobs.yml`): production runs on self-hosted `macstudio` /
`macstudio-light` labels (49 + 14 `runs-on` sites) with hand-rolled persistent venvs off Homebrew
CPython 3.12.13; hosted `ci.yml` pins `3.12.13` exactly; Node split across majors 20 and 22 by
lane; `render.yml` assumes an unpinned `python3.12` on two different runner OSes; host-installed
CLIs CI never installs: poppler/`pdftotext` (runtime-warned in `asia-close.yml:267`), `gh`, `codex`
(absolute Homebrew path). Four fully hash-pinned lockfiles under `requirements/` deliberately
isolate canonical-receipt-byte lanes from the shared venv. `admin/requirements.txt` is outside all
CI. No pyproject/poetry anywhere.

**Mastermind** (1 workflow, `ubuntu-latest`): whole worker environment = `setup-python "3.12"` +
`pip install -e ".[dev]"`; test gate `scripts/ci_pytest.py` is discovery-first (~406 tests) with
constitutional non-excludable prefixes. `pyproject.toml`: `requires-python >=3.11`, ranges, dev
extras exact-pinned (`mcp==1.28.1`, `PyJWT[crypto]==2.13.0`). Production Executive host uses a
notarized Python.org **3.12.10** framework (root-owned, SHA-256-recorded, privileged two-stage
install) — a third distinct Python from CI's tool-cache 3.12 and Homebrew's 3.12.13. One Node dep
(`@playwright/mcp 0.0.79`, locked). `duckdb>=1.0` declared with zero discovered code usage.

**Terminal** (hosted `ubuntu-latest` CI): node 20 + python 3.12 in CI; npm lockfile committed;
`hub` pins `engines.node >=20`; `terminal` has no engines pin; VPS builds on node 20 while the
build Mac is on node 26 (standing divergence since I2).

**Mac Studio host** (production CI runner): Homebrew 6.0.20 arm64, 175 formulae; ambient
`python3` = **3.14.7** (production lanes survive only because they hardcode
`/opt/homebrew/bin/python3.12`); full Xcode selected; 427 GiB free; **four live runner services
with one-time-captured `.path` snapshots that materially diverge** — `mac-builder-3`
(re-registered 2026-08-14) lacks `/opt/homebrew/bin` entirely while its three siblings carry it.

## §3 Drift-incident register (receipted motivating exemplars)

- **I1 — floating Python pin vs sealed runtime** (2026-08-19,
  `agentos/discoveries/DSC-FLOATING-PYTHON-PIN-BREAKS-A-SEALED-RUNTIME.md`): hosted tool cache
  moved 3.12.13→3.12.14 under a floating `"3.12"` pin; the sealed-runtime allowlist correctly
  refused the unreviewed interpreter; 22 tests red on two independent PR heads; production
  unaffected. Class: *unpinned provisioning under an exactness contract*.
- **I2 — Homebrew auto-upgrade breaks a linked runtime** (2026-07-26, charting-app memory
  `deploy-topology.md`): `icu4c` 78.3 upgrade broke `node 22.8.0` via dyld mid-session; recovery
  forced node→26 locally while the VPS builds on node 20; divergence still standing. Class:
  *ambient host mutation reaches through PATH into a runtime*.
- **I3 — same-host runner PATH divergence** (observed 2026-09-01, latent): `mac-builder-3`'s
  configure-time `.path` snapshot omits `/opt/homebrew/bin`; siblings include it. Any job relying
  on ambient Homebrew tools behaves differently by runner lottery on one physical machine.
- **I4 — persistent venv drift** (structural): `$HOME/.cache/mm-venv-*` venvs are created once and
  `pip install -r` over them forever; package state is never rebuilt fresh, so resolved versions
  depend on venv age, not on the manifest.
- **I5 — environment-by-convention production tree** (
  `agentos/discoveries/DSC-M1-PUBLISHER-RUNTIME-IS-HOST-LOCAL-AND-DELIBERATELY-PINNED.md`): the M1
  publisher runs a dirty, detached-HEAD, deliberately pinned working tree — an environment no
  manifest describes.

## §4 Pilot selection ruling (census-driven revision of the annex seed)

The annex proposed the formal-verification or evaluation toolchain as first pilot. The census
falsifies that ordering **for now**: those toolchains are `SPEC_ONLY` (no Quint/TLC/Apalache/Z3/
Inspect/promptfoo dependency exists anywhere), and EVAL-R0 is stdlib-only by accepted amendment.
Piloting an environment for a toolchain that does not exist proves nothing and would invert the
dependency (installing tools ahead of both their owning program and Program 4 admission).

**Selected pilot (RWE-P0 target): the Mastermind repository test-gate environment** — annex
candidate 4 ("one normal Mastermind test subset with Python and shell tools").
Justification against the annex's own criteria: meaningful but not production-host-critical (the
gate runs on hosted CI and worker Macs, never the Executive install); currently affected by real
variation (three distinct Pythons in the estate: CI tool-cache 3.12.x floating, Homebrew 3.12.13,
notarized 3.12.10; no prose setup runbook at all); bounded (one `pyproject.toml`, one gate script);
useful to every other program (every Mastermind wave runs this gate; the eval/formal verticals will
inherit whatever this pilot proves). Measurable end-to-end: `discovered=N` and pass/fail of the
gate is a crisp equivalence check across environments.
**Second vertical (deferred):** the eval/formal toolchain environment, once Program 4 admits those
tools and their owning programs actually adopt them.

## §5 RWE-D0 bakeoff design (frozen spec)

Compare four approaches on the same pilot task (Mastermind test gate, or a bounded subset able to
run without secrets):

- **D — strengthened status quo** (baseline, already partially in-estate): compiled hash-pinned
  lock (pip-tools-style `--generate-hashes`) from `pyproject.toml`, per-platform, installed
  `--require-hashes --only-binary=:all:` into a fresh venv — generalizing macro's proven
  `requirements/*.lock` pattern.
- **A — devenv**, **B — Devbox**, **C — direct Nix flake**: disposable spikes only.

**Spike isolation law (binding until Program 4 admission):** no system-level or daemon Nix install
on any production Mac. Nix-backed spikes run where they cannot mutate a production host: hosted CI
(`ubuntu-latest`) jobs on a throwaway branch, or a disposable Linux container/VM. The Mac-side leg
of D0 is measured only for approach D (which needs no new host software). macOS Nix measurement is
deferred to a post-admission decision with its own host-mutation gate (Determinate vs official
installer question belongs there, not in D0).

**Measurement rubric (per approach):** first setup time; warm setup time; disk; CI parity class
(`EXACT` / `SEMANTIC_EQUIVALENT` / `PLATFORM_SPECIFIC` / `UNPROVEN`); gate pass equivalence
(`discovered=N` and outcomes identical); dirty-host resistance (wrong python3/node first in PATH —
the I2/I3 classes — must not change the selected toolchain); offline/cache behavior; lock-change →
identity-change proof; worker instruction size (tokens to a fresh worker); maintenance complexity;
supply-chain evidence surface. Decide on measurements, not preference; `REJECTED_BY_DESIGN` for
options that lose to D is valid completion.

**Environment receipt (tentative contract, refined in P0):** `mastermind.worker_environment/v1`
per the annex schema — definition kind + content digest, lock digest + input revisions, platform
triple, resolved package versions/digests, task results, realization digest. No secrets, no raw
host names, no provider identity.

## §6 Program phases and current state

| Phase | Content | State (2026-09-01) |
|---|---|---|
| RWE-A0 | environment census + drift register | **DONE** (this document) |
| RWE-D0 | 4-way bakeoff on the pilot task under spike-isolation law | designed above; commissioning next |
| RWE-P0 | first real pilot with chosen approach + receipt + runbook | pending D0 |
| RWE-CI0 | clean/dirty/CI/second-OS parity proof | pending P0 |
| RWE-H0 | optional harness attestation (env identity in execution profile) | deferred |
| RWE-S0 | supply-chain admission of manager/caches/packages | **gated on Program 4 (no carrier yet)** |
| RWE-E0 / PROMOTE | value study; per-repo adoption decision | pending |

**Registry note:** no Agent OS workstream covers this program (gap surfaced at pickup; nearest
adjacent owners `WS:RUNNER-FLEET-RESILIENCE`, `WS:EXECUTIVE-CAPACITY-FABRIC` — no collision).
Parent registration is routed through current procedure on the carrier rather than invented here.

**Next actions:** (1) land this record; (2) commission RWE-D0 spike children (approach D first —
it is admission-free and directly extends a proven in-estate pattern; A/B/C spikes on hosted CI
throwaway branches); (3) surface the Program 4 dependency to the portfolio principal on the
carrier so admission work can be sequenced before any P0 promotion of a Nix-backed option.
