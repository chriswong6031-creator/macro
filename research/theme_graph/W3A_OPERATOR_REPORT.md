# W3A — Operator report (directive §56)

**Session:** 2026-08-14→15 UTC, branch `claude/gmi-theme-graph-w3a`. [PR # at open; merged per
merge-on-green chain]

## A. Verdict

**PASS.** All eleven §31 stop conditions met: law amended; sweep current (Addendum 1);
Finviz reconciled + receipted + promoted through the new contract; both local planes live in
the graph; PIT/provenance enforced (era spot-checks below); capability split exists (sidecar,
anti-ratchet); coverage-gap mechanism live (co-occurrence form); hostile tests A–M green
(120 refresh + 54 plane + 5 registry suites); TWO adversarial reviews (plan PASS-WITH-CHANGES,
8 conditions folded pre-build; diff review pre-PR). No ThemeState was built (W3B's).

## B. Taxonomy census (membership grain shown per market — review F23)

**United States** — local semantic nodes: 268 (`ltheme:finviz:*`, subtheme grain; 40 top-level
themes + 6 supergroups ride node metadata, not nodes); memberships: **DIRECT company→ltheme**
— 2,339 open + 26 closed (two-vintage ladder 2026-06-27 → 2026-08-15 UTC); unique securities:
924 per-listing (529 newly minted `co:us:*`, 413 resolved to existing, 0 dot-dash twins;
cross-listing issuer twins vs ca/hk/intl suites are disclosed, `SAME_AS` = W4); canonical-mapped:
**0 by ruling** (crosswalk's Finviz reference is 40-grain display names — mechanically
insufficient; 234 basket↔subtheme mapping proposals sit in probation with a k=20 shuffle null
(mean 3.85) for curation); capability: 268 subthemes → within the 641-row sidecar, US+CN split
below; source families: `finviz_themes` (vendor, rights unresolved), `mastermind_curated`
(49 baskets, first-class, untouched).

**China** — local semantic nodes: 373 (`ltheme:ths:*`, concept grain, `concept_map.json` asof
2026-06-27); memberships: **BASKET-MEDIATED only** (3,532 company→basket edges pre-existing;
237 baskets → their concepts via EXPRESSES, 0 unresolved names; **zero direct company→concept
edges** — the two-hop join is deliberate, and 136 unseeded concepts carry NO membership
substrate at all); unique securities: 919 (via THS baskets); canonical-mapped: 61 concepts
(W1b concept-grain curation — the honest asymmetry vs the US 0 reflects real curation, not
preference); source family: `ths_concepts` (receipted scraper, weekly cadence live from
2026-08-15, rights unresolved).

**Capability (both markets, `capability.v1` = ≥3 price-covered live members, substrate named
per row):** 641 local-theme rows — **499 `measurement_candidate` / 142 `semantic_only`**
(the 142 includes all 136 unseeded THS concepts + 6 substrate-thin subthemes). Re-derived
nightly; W3B's preregistered gates re-test every node and may promote `semantic_only` nodes
whose substrate improves (anti-ratchet by design, review C2).

## C. Finviz reconciliation (full doc: `W3A_FINVIZ_RECONCILIATION.md` + receipts)

Committed tree ≡ old extraction (both 2026-06-27, verified). Fresh receipted extraction
2026-08-14 = **exactly** the operator's counts (40/268/2,339/924), byte-identical re-fetches,
two independent parsers element-identical. Delta 06-27→08-14: zero structural changes; pure
member churn (26 removals, 9 additions across 32 subthemes). **All 18 departed tickers are
dead-at-vendor-class** (absent from Finviz's own screener perf asof 2026-08-13: 923 = 941 − 18;
the receipted claim is "vendor stopped pricing the symbol" — halts/suspensions share the
footprint); 1 arrival (SNDK, taking PSTG's slot in both storage subthemes; ticker-continuity
symdiff 7 ⇒ correctly a substitution, not a rename). Zero parser artifacts, zero renames, zero
unverifiable. Arithmetic closes exactly. **Promoted through the new refresh contract:** receipt
`data/themes_heatmap/tree_refresh_receipts/20260815T020134Z.json` (exit 0, zero refusals, sha
`1d597c44c8ce` — byte-identical to the session's earlier receipted extraction), tree_history
row 2 asof **2026-08-15** (UTC extraction date; the 07-05 tape row is content-identical to the
declared seed and adjacent-deduped in the ladder). Store spot-checks: PSTG's two storage
memberships closed `[2026-06-27, 2026-08-15)` era=observed; SNDK's nine open at 2026-08-15;
2,330 surviving vintage-1 memberships era=reconstruction; guard `--strict` rc 0.

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
5. Two probation-writer implementations exist by design boundary (the refresh contract's inline
   emitter and `engine/theme_graph/probation.py`); a contract test pins their `proposal_id`
   hashes equal — reconcile onto the module whenever the collector may lawfully import the
   graph engine (cosmetic; drift is test-stopped).
6. Board coverage names 23 US isolates / 9 zero-membership names (banks/REITs/utilities
   shaped) — the coverage-gap queue's standing population; a curation session may propose
   local concepts for them (probation path exists), or they remain honestly outside thematic
   maps.

## G. W3B continuation handoff

`research/theme_graph/W3B_CONTINUATION_HANDOFF_2026-08-14.md` (entry tickets: attention
registration check, eval-os qledger re-read, Market Memory 16/35 posture, W2 constraints,
2026-11 re-probe coordination, first THS weekly receipt check). W3B does NOT start in this
session (directive §56.G).
