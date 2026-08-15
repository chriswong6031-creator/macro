# W3A — Operator report (directive §56)

**Session:** 2026-08-14, branch `claude/gmi-theme-graph-w3a`. [FILL-AT-SHIP: PR #, merge SHA]

## A. Verdict

[FILL-AT-SHIP: PASS / PARTIAL / BLOCKED — set after tests + adversarial reviews conclude]

## B. Taxonomy census

**United States** — local semantic nodes: 268 (`ltheme:finviz:*`, subtheme grain; 40 top-level
themes + 6 supergroups ride node metadata, not nodes); memberships: 2,339 open + 26 closed
(two-vintage 2026-06-27→2026-08-14 ladder); unique securities: 924 (≈250 newly minted company
nodes beyond the curated-basket 708); canonical-mapped: **0 by ruling** (the crosswalk's
Finviz reference is 40-grain display names — mechanically insufficient; mapping proposals go to
probation for curation); semantic-only vs measurement-candidate: [FILL-AT-SHIP counts, rule
`capability.v1` = ≥3 price-covered live members]; source families: `finviz_themes` (vendor,
rights unresolved), `mastermind_curated` (49 baskets, first-class, untouched).

**China** — local semantic nodes: 373 (`ltheme:ths:*`, concept grain, from `concept_map.json`
asof 2026-06-27); memberships: basket-mediated (3,532 company→basket edges already in the
graph; 237 baskets → their concepts via EXPRESSES); unique securities: 919 (via THS baskets);
canonical-mapped: 61 concepts (W1b crosswalk curation, concept-grain — the honest asymmetry vs
the US 0 reflects real curation, not preference); semantic-only: includes all 136 unseeded
concepts (no graph membership substrate — W3B may extend through the owner seeder/snapshots if
eligibility needs it); measurement candidates: [FILL-AT-SHIP]; source family: `ths_concepts`
(receipted scraper, weekly cadence live from 2026-08-15, rights unresolved).

## C. Finviz reconciliation (full doc: `W3A_FINVIZ_RECONCILIATION.md` + receipts)

Committed tree ≡ old extraction (both 2026-06-27, verified). Fresh receipted extraction
2026-08-14 = **exactly** the operator's counts (40/268/2,339/924), byte-identical re-fetches,
two independent parsers element-identical. Delta 06-27→08-14: zero structural changes; pure
member churn (26 removals, 9 additions across 32 subthemes). **All 18 departed tickers are
dead-at-vendor** (absent from Finviz's own screener perf asof 2026-08-13: 923 = 941 − 18);
1 arrival (SNDK, taking PSTG's slot in both storage subthemes). Zero parser artifacts, zero
renames, zero unverifiable. Arithmetic closes exactly. Promotion runs only through the new
refresh contract ([FILL-AT-SHIP: promotion receipt id + new tree_history row]).

## D. Coverage audit (fraction attachable to ≥1 meaningful local theme)

| population | n | covered | note |
|---|---:|---:|---|
| US Prophet board (buy lane, asof 08-13) | 69 | **64%** | finviz hits 35, curated 34 (overlapping); uncovered = banks/REITs/utilities-shaped names — the coverage-gap case-A population |
| CN Prophet board (featured, asof 08-14) | 24 | **71%** | more_actionable lane (83): 64% |
| US Prophet universe (S&P1500+R2000, 2,839) | 2,839 | **34%** | small-cap breadth sits outside thematic maps — expected, reported not engineered |
| CN Prophet universe (top-1,711 A-shares) | 1,711 | **52%** | rises if W3B charters unseeded-concept membership (137 concepts still unmapped to members in-graph) |

Reading: the local planes concentrate exactly where selection activity is (boards ≫ universes).
Uncovered board names are the coverage-gap diagnostic's standing work queue.

## E. Rights/provenance status (registry: `config/theme_sources.yml`; note: `W3A_SOURCE_RIGHTS_AND_PROCUREMENT.md`)

- `mastermind_curated` — **direct display** (house content).
- `finviz_themes` — **unresolved ⇒ internal-only** for every GMI emission (vendor Elite-export
  + resale-restriction facts recorded without legal conclusions; pre-existing heatmap/rotation
  surfaces are owner products, inventoried not retro-gated). Decision needed before W6:
  internal-only vs derived-display; escalation prepared in the note.
- `ths_concepts` — **unresolved ⇒ internal-only** for NEW GMI emissions (existing cn owner
  surfaces grandfathered). Bundle with the Finviz decision at W6.
- S&P/Kensho — corroboration class only, ships EMPTY; no undocumented download dependency.
- Theia — procurement evaluation delivered (note §5): worth a commercial conversation iff
  vintages + issuer-grain identifiers + A-share coverage + internal-derivative rights all
  answer yes; nothing in W3A/W3B blocks on it.

## F. Residue (genuine unresolved items only)

1. Finviz/THS display-rights decision (operator, before W6 — nothing earlier needs it).
2. Attention primitives (`china_comment`/`china_lhb`/`china_zt_pool`) still
   synapse-unregistered by owners — W3B consumes attention legs only if registered by then.
3. US action-board carries no board-level as-of (CN board does) — W3C's input contract needs
   one; file to the board owner at W3C charter.
4. 136 unseeded THS concepts are semantic-only — W3B decides whether eligibility work charters
   snapshot-direct membership through the owner pipeline.
5. [FILL-AT-SHIP: anything the diff review or promotion surfaces]

## G. W3B continuation handoff

`research/theme_graph/W3B_CONTINUATION_HANDOFF_2026-08-14.md` (entry tickets: attention
registration check, eval-os qledger re-read, Market Memory 16/35 posture, W2 constraints,
2026-11 re-probe coordination, first THS weekly receipt check). W3B does NOT start in this
session (directive §56.G).
