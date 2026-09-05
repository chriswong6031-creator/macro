---
operation_key: marketontology-f01-macro-markets-20260826-fable-001
lane: F01
workstream: WS:MARKET-OS
status: RECORDS_ONLY / HOLD-FOR-SOL
product_effect: NONE
runtime_effect: NONE
data_effect: NONE
supersedes: MARKET_ONTOLOGY_MACRO_MONETARY_SUITE_ARCHITECTURE_2026-09-04.md §1.3 (product-surface placement)
date: 2026-09-04
---

# F01 Macro & Monetary — Chairman scope override + reference taxonomy

This is a **records-only freeze pending Sol review**. It is not an implementation, a
worker assignment, a runtime change, or an acceptance. It records a Chairman scope
override to the Sol architecture freeze and the findings of an authenticated reference
pass, so that later sessions inherit the corrected boundary without re-deriving it.

## 1. Chairman scope override (2026-09-04)

The complete twelve-workspace Macro & Monetary suite — **the producer AND the
user-facing UI** — is built in the **macro repository (the macro dashboard site)**, not
the Terminal repository.

This **supersedes architecture §1.3**, which placed the premium suite UI in Terminal and
declared a second implementation in the static Macro site out of scope. Basis: direct
Chairman intent expressed in the active F01 session. In the authority order frozen by the
continuation packet, current Chairman intent is authority #1 and outranks the architecture
document (authority #4).

## 2. What stays unchanged

The override moves the UI's home only. It does not touch the substance of the architecture:

- **R1A is unaffected** — it was always a macro-side producer vertical.
- The `mastermind.macro_workspace_snapshot.v1` contract (§7) — envelope, metric law,
  clock law, freshness/null vocabularies, correction law, composite/axis law — stands.
- The twelve workspace blueprints (§10), the canonical owner / no-rebuild map (§4), the
  method / evidence / scenario / alert / AI laws (§7–9), and the production-proof law
  (§15) stand.
- The first-vertical ruling stands: **US Liquidity Regime Monitor**, then the Minimum
  Coherent Suite (Liquidity Regime, Growth, Inflation, Monetary Policy, Financial
  Conditions).

## 3. What re-freezes (R1B and the shared shell)

R1B becomes a **macro-native template family**, not a Terminal route. The pattern anchor
is the repository's existing per-page family — e.g. `templates/capital_structure.html.j2`
+ `capital_structure.css` + `capital_structure.js` + `capital_structure_boot.js`,
rendered by `scripts/build_capital_structure_page.py` and registered in `render.yml`'s
explicit scope map. The twelve workspaces follow that precedent:

- per-workspace template set producing a flat published page under the site's convention;
- a shared suite-shell partial implementing the §6.3 page grammar (context header →
  causal implications ribbon → headline state → Current/Drivers/History/Scenario/Alerts
  tabs → dominant visualization → diagnostics → what-changed → component histories →
  evidence drawer → Analyst action);
- chrome via the existing partials `_public_nav` / `_site_nav` / `_navlinks` and
  `account.js`;
- bilingual `L()` / `.l-en` / `.l-zh` law; dark/light; template pushes fire the express
  render lane.

## 4. Integration deltas the override creates (flagged for Sol; not resolved here)

The architecture bound several seams to Terminal owners in §4.1. Moving the UI to the
macro site opens these, which Sol must rule on before the affected verticals build:

1. **Signed-in / entitlement journey now runs on the macro site.** Standing trap: an edge
   paywall is not authentication. The architecture's auth/entitlement law needs an
   explicit macro-site binding.
2. **Alerts / Analyst / portfolio-context seams** that §4.1 pointed at Terminal services
   need macro-side equivalents or explicit per-workspace deferral (the shared grammar
   already permits withholding the Alerts / Scenario tabs until the capability is real).
3. **§1.3's duplicate-product law inverts:** "no second implementation in the static Macro
   site" becomes "macro is primary; Terminal must not later re-implement these pages."

## 5. Reference taxonomy finding (authenticated marketontology.com pass, 2026-09-04)

An authenticated pass over the reference product's Macro section captured jobs / hierarchy
/ states / interactions only (no assets, code, or proprietary text). Full detail:
`MARKET_ONTOLOGY_F01_MACRO_MONETARY_REFERENCE_EXTRACTION_2026-09-04.md` (working copy).
Headline facts:

- The reference product exposes **14** Macro workspaces = our 12 **plus** "Rates & Curves"
  (we fold rate structure into Monetary Policy §10.7) and "Trade Balance & Cross-Border
  Flows" (a future MO-DELTA candidate after a source/rights census; public FRED/BEA/TIC
  family).
- The reference product's **"Structure" workspace = global wealth composition**
  (UBS/Forbes/SWF asset stocks, wealth-tier attribution, corporate concentration) — a
  **name collision**, not our corporate Capital Structure (§10.3). Our §10.3 remains
  reference-absent and an original Mastermind-native composition by design.
- The reference **National Debt page is thinner** than our §10.12 blueprint (no
  auction/TIC/maturity-schedule composition). Our §10.12 exceeds the reference.
- The observed **shared page grammar matches our §6.3** (causal ribbon with evidence-class
  + confidence → per-cell-dated KPI band → chart stack with snapshot + source clocks → MoM
  heatmap), and the observed **honest degraded states** (bare "—" Chicago NFCI null, "TED
  DISCONTINUED", BoJ rate as-of 2023-12, Fed-only central-bank table) validate our §7 clock
  / null / freshness law with no contract rework.
- **Quality traps to beat, not copy:** naive month-over-month % heatmaps over level/rate
  series produce absurd cells (e.g. −5,603%, +10,450%) — exactly what our method law
  refuses; and raw source series IDs (ECIWAG, DRTSCILM) leak into the reference's chart
  legends where our Reference law requires reviewed public labels.

## 6. Status

Records freeze only. No product, runtime, or data path changed. This carrier does not ACK,
START, merge, deploy, or grant any authority. It exists to make the architecture and the
override durable in the macro repository for Sol review, per architecture §19.1.
