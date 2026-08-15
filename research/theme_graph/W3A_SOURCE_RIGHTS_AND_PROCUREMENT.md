# W3A — Source rights inventory + procurement evaluation (directive §13–§15)

**Date:** 2026-08-14. **Law:** G0.13 — rights are stated, never assumed; unresolved ⇒ the
source family is internal-only evidence for every GMI emission. Machine-readable registry:
`config/theme_sources.yml`; enforcement: `engine/theme_graph/rights.py` + guard + test L.
This note prepares operator escalations; it draws **no legal conclusions**.

## 1. Finviz (family `finviz_themes`) — inventory + rights posture

**What is consumed today (pre-W3A, owner = US theme analytics):**
1. Nightly perf: `scripts/fetch_finviz_themes.py` in daily.yml pulls `/api/map_perf` +
   `/api/map_perf_screener` (keyless public endpoints the map page itself calls; browser UA;
   non-fatal on failure) → `perf_snapshot.json` + append-only
   `subsector_perf_history.jsonl` (PIT, subsector aggregates only — member perf deliberately
   not archived).
2. Structure: committed `themes_tree.json` (source of record; manual traced extraction of a
   lazy webpack data chunk — not a documented API), PIT `tree_history.jsonl`.
3. Downstream: themes heatmap page, subsector rotation (+track record), oracle
   timemachine/panel, fund_intelligence, special_sits_intel (blast-radius census in the sweep
   Addendum 1). These are pre-existing owner surfaces that predate GMI.

**Auth class:** keyless public web (no login, no API key, no ToS-gated endpoint accepted).
**Known vendor facts (recorded, not interpreted):** Finviz advertises export/API as an Elite
(paid) capability; its FAQ notes restrictions around reselling raw historical data. Neither
fact is extrapolated here into a conclusion about theme-membership display rights.

**W3A ruling (fail-closed):** `rights_class: unresolved` → treated as **internal_only** for
every GMI artifact. Concretely: local-theme nodes/edges/evidence derived from Finviz live in
`data/theme_graph/` (internal product data plane) and may NOT be emitted into any public/site
artifact until the operator resolves rights (the W6 surface wave is the natural forcing point).
The pre-existing heatmap/rotation surfaces are the owner's product shipped long before GMI;
they are inventoried here and left to their owner — GMI neither extends nor gates them.

**What resolution needs (operator escalation, prepared):** decide the intended use tier —
(a) internal analysis only (current posture, no action needed); (b) derived display (e.g.
"cohort shares a battery-materials neighborhood" with GMI-authored labels, no raw Finviz tree
republication) — plausibly distinct from raw-data redistribution but needs an explicit
operator/legal call, possibly an Elite subscription as good-faith commercial relationship;
(c) raw republication — assume NO absent written permission. Recommendation: hold posture (a)
through W3B (no user surface exists to need more); decide (b) before W6 design work begins.

## 2. THS / 同花顺 (family `ths_concepts`)

Receipted scraper (complete-or-fail, politeness-paced, receipt contract v1), weekly cadence
from 2026-08-15. Concept names/memberships already render on existing cn owner surfaces.
**W3A ruling:** `rights_class: unresolved` → internal-only for NEW GMI emissions; existing cn
surfaces are grandfathered owner products (same posture as Finviz). Escalation bundled with
the Finviz (b) decision at W6.

## 3. Mastermind curated baskets (family `mastermind_curated`)

Our own curation. `rights_class: direct_display_ok`. No action.

## 4. S&P / Kensho — corroboration posture (directive §14)

Usable: public methodology documents, public index descriptions, lawfully public constituent
evidence — as `external_classification` evidence rows (provider-labeled, claim-typed,
rights-tagged) once someone actually ingests them (NOT in W3A; the class ships empty).
Not usable: any undocumented bulk download route as a production dependency; daily
constituent/index data are subscription products. If systematic constituent use is wanted,
that is a procurement decision — prepare it only when a wave actually needs the evidence.

## 5. Theia — procurement evaluation (directive §13 question list, answered for the ask)

W3 does not depend on Theia; this section only frames the buy/no-buy question for the operator.
**What a license would have to include to be worth routing into GMI** (each maps to a
directive question): Level-4/5 taxonomy access (not just factor endpoints); company↔theme
exposure WEIGHTS (the one thing we structurally lack — W2's economic axis is an honest null
precisely because no segment-grain source exists on either market); historical vintages with
point-in-time availability stamps (without which G0.2 forbids using it for any backfilled
claim — a current-snapshot-only feed would be display-context only); security/company
identifiers robust to ticker churn (our identity law needs issuer-grain ids, not bare
tickers); evidence/provenance fields + model-derived-vs-sourced labeling (G0.13 provenance;
their model outputs would land as `external_classification` claims, never as our own
assertions); update cadence (monthly company exposures per their public docs — fine for the
economic axis, useless for trading state, which stays ours); redistribution/display rights for
Mastermind customers (the whole ballgame for W6 — an internal-only license still unlocks the
economic axis internally); API/bulk delivery; geographic coverage incl. A-shares (a US-only
matrix halves the value — the program is dual-market by charter); public/private split; and
license limits on derived models (our capability/eligibility classifications derive from
membership — a license that taints derivatives is unusable).
**Routing if licensed:** through `engine/company_theme_exposure/`'s owner contract (the
economic-exposure organ, per W2's ruling and the existing `DNR:HOLD-TICKER-EXPOSURE-TAGS`
adjacency), landing in the graph only as evidence-refs + separately adjudicated
`economic_share` formula — never as direct graph truth.
**Recommendation:** worth a commercial conversation IF the answers to (vintages, identifiers,
A-share coverage, internal-use derivative rights) are all yes; otherwise the native path
(segment-axis XBRL ingestion, W2 ore ledger) remains the plan of record. No urgency: nothing
in W3A/W3B blocks on it.

## 6. Registry mechanics

`config/theme_sources.yml` rows: `family`, `rights_class ∈ {internal_only, derived_display_ok,
direct_display_ok, unresolved}`, `auth_class`, `source_route`, `review` (date/by/outcome),
`notes`. Guard fails closed on any store `source_meta.rights_family` without a registry row.
`unresolved` and `internal_only` behave identically at the emission gate (refuse); `unresolved`
additionally signals "operator decision pending" in the §56 report.
