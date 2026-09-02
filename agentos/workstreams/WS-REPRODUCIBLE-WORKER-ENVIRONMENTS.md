---
key: REPRODUCIBLE-WORKER-ENVIRONMENTS
title: Reproducible worker environments and toolchain identity
objective: >
  Selected worker/build/test toolchains reproduce across approved hosts and CI with
  exact lock/receipt identity, without the environment system ever owning credentials,
  provider homes, Executive host services, worker identity, or deployment. Done for the
  pilot means the Mastermind repository test gate realizes from per-platform hash locks
  on macOS and hosted CI, emits a secret-free mastermind.worker_environment/v1 receipt,
  and the parity evidence plus adoption ruling are durable.
status: active
program: reproducible-worker-environments
repos: [macro, mastermind]
owner: fable-coo
class: build
blast_radius: reversible
ambiguity: specified
owns_paths:
  - "research/REPRODUCIBLE_WORKER_ENVIRONMENTS_MASTERPLAN_V1.md"
  - "research/REPRODUCIBLE_WORKER_ENVIRONMENTS_D0_BASELINE_2026-09-01.md"
  - "research/REPRODUCIBLE_WORKER_ENVIRONMENTS_P0_CI0_RESULTS_2026-09-02.md"
depends_on: []
next_action: >
  RWE-E0 value study once real workers use the runbook path; RWE-S0 held until the
  portfolio's Program 4 (supply-chain admission) has a carrier — never install
  devenv/Devbox/Nix on a production Mac before admission.
waves:
  - id: RWE-A0
    title: Estate environment census and drift-incident register
    status: done
    next_action: >
      Done — macro PR #6715 (masterplan V1 + census + incidents I1-I5) and PR #6722
      (D0 baseline record + DSC:SELFHOSTED-RUNNER-PATH-IS-A-CONFIGURE-TIME-SNAPSHOT).
  - id: RWE-D0
    title: Four-approach bakeoff (status-quo-D, devenv, Devbox, Nix flake)
    status: done
    depends_on: [RWE-A0]
    next_action: >
      Done — disposable spikes (local mac + Mastermind throwaway branch, deleted after
      capture). Ruling DEC:RWE-PILOT-APPROACH-D: D selected; Devbox deferred on
      supply-chain admission; devenv and raw flake rejected as pilot approaches.
  - id: RWE-P0
    title: Pilot implementation (locks + rwe_env + receipt + shadow CI + runbook)
    status: done
    depends_on: [RWE-D0]
    next_action: >
      Done — Mastermind PR #342 merged at 722f15d531a1 (2026-09-02) after a full
      independent adversarial review chain (REQUEST_REPAIR -> repairs -> delta review
      -> PASS at 0a360b44) and a green full-gate shadow run from the committed locks.
  - id: RWE-CI0
    title: Local/CI parity proof with explicit platform differences
    status: done
    depends_on: [RWE-P0]
    next_action: >
      Done — mac receipt (3.12.13/homebrew, env_id 45add2e16d4a1bfa) vs CI receipt
      (3.12.14/toolcache, env_id d6234cec27cdeb3c): same pyproject digest, 76 packages
      each, per-platform locks, vendored ref measured+matched in CI, full gate 452/452
      exit 0 in CI. Parity class SEMANTIC_EQUIVALENT with explicit platform differences.
  - id: RWE-S0
    title: Supply-chain admission of env managers (Devbox upgrade path)
    status: todo
    depends_on: [RWE-CI0]
    next_action: >
      BLOCKED on Program 4 (software supply-chain admission) which has no carrier yet.
      Do not install devenv/Devbox/Nix on production Macs before admission. The Devbox
      candidate's D0 measurements (1s realize, probe green) are in the D0 records.
  - id: RWE-E0
    title: Value study and wider adoption decision
    status: todo
    depends_on: [RWE-CI0]
    next_action: >
      After real workers use the runbook path: measure setup tokens/time, failure rate,
      and CI-mismatch incidents vs the pre-pilot baseline; then decide per-repo/task
      adoption widening (macro legacy-jobs.yml's ~194 unpinned pip lines are the
      largest candidate surface). Interpreter full closure remains the Devbox upsell.
---

# Reproducible worker environments

Program home: `research/REPRODUCIBLE_WORKER_ENVIRONMENTS_MASTERPLAN_V1.md` (macro).
Pilot implementation lives in Mastermind (`scripts/rwe_env.py`, `requirements/gate-*.lock`,
`.github/workflows/rwe-shadow.yml`, `docs/RWE_RUNBOOK.md`). Operation
`mastermind-reproducible-worker-environments-20260830-sol-pro-001`, Fable COO principal,
carrier Slack C0BSBM78V1N/1788258537.508239.
