---
operation_key: marketontology-f01-product-experience-hub-r1-20260904-sol-001
lane: F01
workstream: WS:MARKET-OS
status: RECORDS_ONLY / ACCOMPANIES_R1_BUILD
product_effect: NONE
runtime_effect: NONE
data_effect: NONE
amends: MARKET_ONTOLOGY_MACRO_MONETARY_SUITE_ARCHITECTURE_2026-09-04.md §6.3 (page-grammar ORDERING only)
authority: Sol ruling / CONTINUE, Slack C0BSBM78V1N/1788593558.145159 (2026-09-05)
date: 2026-09-05
---

# F01 R1 — decision-first ordering amendment (narrow)

This record exists so that a reader of the merged architecture, and any independent
reviewer of the R1 pull request, can see that the reordering below is an **authorized
supersession** rather than an implementation that wandered away from its spec.

## 1. What is amended

Architecture §6.3 "Shared page grammar" freezes this order:

```text
1 context header  2 causal implications ribbon  3 headline state  4 tabs
5 dominant visualization  6 diagnostics  7 what changed
8 component histories  9 evidence drawer
```

For **the Macro & Monetary hub and the Liquidity Regime pattern-setter only**, the
reading order becomes:

```text
State  →  What changed  →  Why it matters  →  Next action
       →  expanded diagnostics, drivers, history, components and evidence on demand
```

The effective date and a concise, truthful freshness/coverage statement remain visible
in the default reading path. Hashes, clocks, method versions, component health and the
full diagnostic set move behind progressive disclosure — they are demoted, never removed
and never made harder to obtain than one deliberate action.

## 2. What is NOT amended

- **§6.2 production navigation law stands in full.** No broad top-level navigation item
  is created by R1; global admission remains held under its existing gates. The beta
  clause in §6.2 is the final-sidebar carve-out and is **not** a waiver of broad-nav
  production proof.
- **Producer semantics are untouched.** No change to `engine/market_os/macro_workspaces/`
  math, `registry.py`, `contract.py`, the snapshot schema, source configuration, or any
  domain owner's formulas, clocks or freshness rules.
- **§7 contract law, §8 evidence classes, §15 production-proof law** are unchanged. R1
  surfaces the contract's existing `evidenceClass`, `freshnessState`, `nullReason` and
  `presenceState` vocabularies; it does not invent, widen or blend them.
- The other twelve workspace bodies keep the §6.3 grammar in this PR.

## 3. Why the amendment is necessary

The architecture's own **§10.1 user job** for this workspace reads:

> Understand whether funding is becoming easier or tighter, whether balance sheets are
> supplying or withdrawing support, what changed, and which component could force the
> next regime transition.

That job is already *state → what changed → what could move it next*. The §6.3 rendering
order places required-source availability, coverage and three clocks ahead of the state
itself, so the page as frozen answers its own stated user job only after the reader
scrolls. Measured on the shipped artifact at `443fe9a6`:

| viewport | state appears at | "what changed" appears at |
|---|---|---|
| 1440 × 900 | y = 1033 (133 px below the fold) | — |
| 768 × 1024 | y = 1183 (159 px below the fold) | y = 2941 |
| 390 × 844 | y = 1600 (≈ 1.9 viewports) | y = 3624 (≈ 4.3 viewports) |

The conflict is therefore **internal to the architecture** — §6.3's ordering against
§10.1's user job — and is resolved in favour of the user job by the Chairman/F00 product
correction, which outranks the architecture document in the lane's authority order.

## 4. The previous implementation was correct

`templates/_macro_suite_shell.html.j2` renders §6.3's nine regions in exactly the frozen
order. The backend-first reading experience is **architecture compliance, not drift**.
Nothing in this amendment should be read as a defect finding against the R1B builder.

## 5. Mechanism, so the supersession stays narrow

The shell keeps one entry point. Every page still calls `shell.body(view)` and
`shell.degraded_body(view)`, preserving the reuse contract asserted by
`test_adding_a_workspace_page_needs_only_a_registry_entry_and_a_template`. The ordering
is selected by a deterministic view-model field, `view.layout`, which the builder sets to
the decision-first value for `liquidity_regime` alone. The other thirteen generated
bodies are byte-identical to their pre-change output apart from the shared in-suite
navigation insert, and the R1 test suite asserts that.

Extending the pattern in a later wave is one flag per workspace. No second shell, no
forked template family, and no new navigation, registry, evidence or correction plane is
created by this amendment.
