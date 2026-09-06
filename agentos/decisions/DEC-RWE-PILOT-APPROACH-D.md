---
key: RWE-PILOT-APPROACH-D
question: >
  Which environment approach carries the Reproducible Worker Environments pilot for
  the Mastermind repository test gate: strengthened hash-locked pip (D), devenv (A),
  Devbox (B), or a raw Nix flake (C)?
answer: >
  Approach D — per-platform pip-compile hash locks realized into fresh venvs with
  --require-hashes --only-binary=:all:, a fail-closed interpreter identity check, an
  explicit pinned cross-repo vendored input, and a secret-free
  mastermind.worker_environment/v1 receipt. Devbox is retained as the deferred
  conditional upgrade path (interpreter closure), gated on the not-yet-existing
  supply-chain admission program. devenv and the raw flake are REJECTED_BY_DESIGN as
  pilot approaches. This selects the pilot approach only; it is not a company-wide
  environment standard.
rationale: >
  Measured bakeoff, not preference. D proved the FULL 448-test gate green on a clean
  hosted runner from lock + pinned vendor step alone (run 33575841662: gate_exit=0,
  1012s), realized in ~28s cold / ~22s warm on the Mac with zero sdist or unsafe-flag
  exceptions, and was byte-identical under a hostile PATH (the I2/I3 drift classes
  closed mechanically). It requires zero new third-party tools — pip/PyPI is the
  estate's existing trust surface — so it is the only approach lawful to promote before
  supply-chain admission exists. Devbox realized python@3.12 in 1s and passed the
  bounded probe (strongest Nix-family showing) but buys only interpreter closure at the
  cost of a new vendor layer plus Nix plus admission burden. devenv worked only after
  pinning away a broken floating nixpkgs-unstable channel (invalid CVE-patch path) and
  cost 498s cold realize — dominated by Devbox on every measured axis. The raw flake
  failed structurally (nixpkgs python x manylinux wheels: libstdc++.so.6 missing;
  remediation known, unverified) with the highest maintenance surface.
alternatives:
  - option: devenv (A)
    why_not: >
      498s cold realize, floating-channel fragility (broken nixpkgs-unstable reference
      required an exact pin to measure at all), and no measured advantage over Devbox,
      which shares its Nix substrate at a fraction of the friction.
  - option: raw Nix flake (C)
    why_not: >
      Structural probe failure (numpy import -> libstdc++.so.6 missing under nix
      develop), the known remediation unverified, and the highest custom-engineering
      and expertise burden of the four — exactly the annex's predicted risk profile.
  - option: Devbox (B) now
    why_not: >
      Best Nix-family measurements (1s realize, probe green), but its only capability
      delta over D is pinning the interpreter itself, and adopting it now would install
      an unadmitted third-party manager ahead of the supply-chain program — the exact
      inversion the portfolio charter forbids. Deferred, not rejected: it is the named
      upgrade path if/when interpreter closure is worth the admission cost.
  - option: whole-company Nix migration
    why_not: >
      REJECTED_BY_DESIGN by the program charter itself (pilot-first law); never a
      candidate in this decision.
evidence:
  - "D0 baseline record: research/REPRODUCIBLE_WORKER_ENVIRONMENTS_D0_BASELINE_2026-09-01.md (local mac spike: lock 929s, realize 28.16s/21.78s, dirty-PATH byte-identical, vendored-input structural finding)"
  - "Bakeoff canonical run 33577410093 on mastermindx-market-intelligence/Mastermind (spike branch claude/rwe-d0-bakeoff-spike-20260901, deleted after capture, 404-verified): baseline-d gate 448/448 exit 0 in 1025s, lock compile 85s linux; devenv-a realize 498s + probe 35/35 + /nix 2.4G; devbox-b realize 1s + probe 35/35 + /nix 2.6G; flake-c probe exit 4 libstdc++"
  - "Pilot proof: Mastermind PR #342 merged 722f15d531a1 (independent review chain to PASS at 0a360b44; committed-lock shadow runs green; final CI-side full gate 452/452 exit 0 receipt d6234cec27cdeb3c)"
  - "Carrier rulings: Slack C0BSBM78V1N thread 1788258537.508239, ts 1788312118 (bakeoff ruling) and ts 1788321719 (review chain)"
reversibility: easy
affects: ["research/REPRODUCIBLE_WORKER_ENVIRONMENTS_MASTERPLAN_V1.md", "agentos/workstreams/WS-REPRODUCIBLE-WORKER-ENVIRONMENTS.md"]
confidence: high
decided_by: fable-coo
decided_at: 2026-09-02
---

The pilot is additive (new files only; the primary `pip install -e ".[dev]"` CI path is
untouched), the shadow lane is non-required, locks are plain committed files, and
rollback is deleting a venv directory. Superseding this decision requires only a new
bakeoff-grade measurement showing a different approach beats D on the measured job,
plus supply-chain admission for any Nix-family successor.
