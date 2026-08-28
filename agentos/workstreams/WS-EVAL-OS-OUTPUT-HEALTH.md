---
key: EVAL-OS-OUTPUT-HEALTH
title: Intelligence Evaluation OS — T4 output-level health contract (derived per-output substrate + admin surface)
objective: >
  One honest health verdict per engine output artifact — healthy / degraded / stale /
  unavailable — or the explicit admission that Eval OS could not determine it
  (assessment_status=could_not_look), derived on demand over the T1 engine registry and the
  Synapse artifact estate, with reader-side evidence outranking producer-side freshness,
  dependency-bound honesty (exact vs upper), lawful time-basis handling (no calendar
  guessing), and zero committed generated state. Exposed read-only through the existing
  admin console as the Intelligence OS surface. Done only after the exact merged implementation
  is exercised on the real deployed admin path and real Synapse estate, including negative/blind
  states, without creating persisted health state.
status: active
program: qualitative-intelligence
repos:
  - macro
owner: Eval-OS program (CEO Sol; Fable COO execution lane)
class: build
blast_radius: reversible
ambiguity: specified
depends_on:
  - "WS:EVAL-OS-T1-ENGINE-REGISTRY"
owns_paths:
  - engine/output_health.py
  - scripts/build_output_health.py
  - tests/test_output_health.py
  - admin/intelligence_os.py
  - tests/test_admin_intelligence_os.py
decisions:
  - "DEC:EVAL-OS-T4-ADMIN-SURFACE"
  - "DEC:EVAL-OS-RECOVERY-ARCHITECTURE-FREEZE"
waves:
  - id: W1
    title: Pure resolver + CLI adapter + acceptance/mutation suite + admin Intelligence OS page
    status: done
    next_action: >
      None — PR #5721 merged 2026-08-15 as a77d874a1c23c7e4e2db0000db75164fcc56bcc2
      after an Opus HOLD and bounded repair. The former claude/eval-os-t4-output-health branch no
      longer exists; do not recreate it.
  - id: W2
    title: Real deployed admin + estate proof
    status: in_progress
    next_action: >
      Execute H1 from research/EVAL_OS_RECOVERY_ARCHITECTURE_FREEZE_2026-08-27.md: verify the
      exact merged T4 behavior on the deployed admin API/UI and real Synapse estate; return a
      browser/API receipt plus representative healthy/degraded/stale/unavailable/could_not_look
      evidence and negative proof that no generated/persisted health store was introduced.
do_not_redo:
  - "Do not build another monitor/registry/graph/dead-man switch — Neural Web health, Foresight health, provider health, the external freshness sentinel and R2 audit are EVIDENCE PROVIDERS; T4 only normalizes their evidence."
  - "Do not commit a generated health artifact or add a --check/equality mode — the resolver is a derived on-demand view."
  - "Do not generalize Neural Web's weekend staleness shortcut or its _AS_OF_KEYS fallback list estate-wide — date-only watermarks without a lawful calendar resolve could_not_look, never a guessed verdict."
  - "Do not let the sentinel import or depend on T4 — dependency direction is sentinel → evidence, T4 reads evidence."
  - "Do not hand-author complete input lists — upstream sets derive mechanically from config/synapse.yml consumers; health_optional_upstreams is only a validated optional delta."
  - "Do not treat support_map.upstream() bound='exact' as globally true for multi-output producers — T4 computes its own dependency_bound."
  - "Do not create T7/T8 score authority inside T4 proof. The admin page is a read-only health window; performance/evidence answer layers are separate waves."
landmines:
  - "asof_field is free-form; staleness_from overrides which field freshness is measured from and must be honored."
  - "Artifacts whose declared asof_field is absent must surface promised_asof_field_absent/could_not_look behavior; healing declaration quality is separate registry curation unless a specific defect prevents truthful proof."
  - "mtime is lawful evidence only under the write-time contract and only when trusted on the live deployed estate. Fresh-checkout mtimes are not production freshness proof."
  - "Local fixture/CI success is not H1 production proof. The acceptance receipt must identify the deployed admin release/path and real estate inputs."
next_action: >
  H1 production proof: prove #5721's T4 resolver and existing Intelligence OS admin page against
  real deployed state, including at least one truthful negative/blind state. Keep the workstream
  active until Sol accepts that receipt.
---

## Reconciliation — 2026-08-27

The 2026-08-14 next action was stale. T4 did not remain stranded on its old branch: PR #5721
merged as `a77d874a1c23c7e4e2db0000db75164fcc56bcc2` after an independent Opus adversarial review
returned HOLD and the builder repaired the findings. GitHub shows the former branch is gone and
no later implementation carrier is open. That makes the implementation `BUILT_NOT_PROVEN`, not
`PROVEN_LIVE`: no accepted real deployed admin/browser/operator proof was found in the recovered
records. W1 is therefore done and W2 owns the remaining real-use proof.

T1 remains the single engine-registry substrate; T4 remains a pure view over T1 + Synapse +
evidence providers. T4 grants no authority and persists no health state. T7/T8 must extend this
same Intelligence OS surface rather than creating another score/admin product.
