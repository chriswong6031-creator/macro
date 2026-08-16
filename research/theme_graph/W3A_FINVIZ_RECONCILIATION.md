# W3A — Finviz themes-map source reconciliation (directive §20; receipted)

**Date:** 2026-08-14. **Receipts:** `research/theme_graph/w3a_finviz/` (raw fetched bytes +
`receipts.json` with url/sha256/size/status/retrieved_at per fetch; `extracted_tree.json`;
`extraction_meta.json`; `diff_vs_committed.{json,md}`). **Ruling:** reconciliation PASSES —
every delta dispositioned, zero unexplained; tree promotion authorized for the build phase
(after plan review), through the new refresh contract only.

## 1. The three-view comparison the directive requires

| view | provenance | themes | subthemes | memberships | unique tickers | tree sha256 |
|---|---|---:|---:|---:|---:|---|
| A. committed tree | `data/themes_heatmap/themes_tree.json` (#579) | 40 | 268 | 2,356 | 941 | `e0f85510…` |
| B. old extraction | `finviz_themes/finviz_themes_map.json`, asof 2026-06-27 | 40 | 268 | 2,356 | 941 | (same content) |
| C. operator extraction 2026-08-14 | headline counts from the CEO directive §5 (contents not shipped to this session) | 40 | 268 | 2,339 | 924 | — |
| D. fresh W3A extraction | live re-trace 2026-08-14, receipts committed | 40 | 268 | 2,339 | 924 | `1d597c44…` |

**A ≡ B verified content-identical** (membership-set equality, 2,356 = 2,356, zero deltas) —
the committed tree IS the 2026-06-27 extraction, so the reconciliation reduces to A→D.
**C ≡ D on every reported count** — the fresh extraction reproduces the operator's numbers
exactly from the live source, which simultaneously (i) corroborates the operator extraction as
a faithful read and (ii) discharges directive §20's view-C obligation without inventing its
contents (§20's own alternative: "independently reproduce the current public map").

Extraction integrity: chunk id `6574` / module id `13014` unchanged since 2026-06-27 (only
file hashes rotated — `map.v1.6775885d.js`, `runtime.v1.f0939ef5.js`,
`6574.v1.6c9683c9.js`); all fetches HTTP 200, no bot-wall; every URL byte-identical across
repeated fetches; two independent parsers (strict recursive-descent object-literal reader with
no eval + a parser-free regex over the member CSVs) agree element-for-element on all 2,339
memberships. Parser-bug hypothesis: REFUTED for this extraction.

## 2. A→D delta and per-delta dispositions (no "looks close enough")

Structural plane: **zero** deltas — no theme added/removed/renamed/reordered; no subtheme
added/removed/renamed/moved; no key change; no description change; no member reordering.
The 06-27→08-14 drift is pure member churn in 32 of 268 subthemes: **26 removals, 9 additions**;
no surviving ticker changed its subtheme set (zero re-assignments).

Ticker plane: 18 departed, 1 arrived. Evidence for dispositions: the nightly perf lane's
committed `perf_snapshot.json` (asof **2026-08-13**, the session before this reconciliation)
queried every OLD-tree member against Finviz's own screener; a symbol the vendor no longer
prices returns null and is dropped. Result: **all 18 departed tickers are ABSENT** from the
vendor's own screener output (923 members priced = 941 − 18, exactly), while every surviving
member is present.

| disposition class | tickers | ruling |
|---|---|---|
| genuine source change — symbol dead at vendor (delisting/acquisition/symbol-retirement class) | UDMY, FDP, GTLS, MASI, ORGN, PSTG, SATS, CFLT, CTRA, CVGW, DVS, EXAS, LC, MEG, NVVE, SEE, STKL, UGRO (all 26 removals) | membership edges CLOSE at `valid_to=2026-08-14` (first observation without them), `date_provenance=raw_snapshot`; companies stay in the graph (survivorship law — dead members never vanish) |
| genuine source change — new listing at vendor | SNDK (9 additions, incl. taking PSTG's slot in `bigdatainfrastructure` + `hardwarestorage`) | edges OPEN at `valid_from=2026-08-14` |
| parser bug | — (none) | refuted per §1 |
| security-identity migration | — (none detected: no `.`↔`-` variant pairs among departures/arrivals; SNDK↔PSTG is a slot substitution of two DIFFERENT issuers, not a rename) | the corporate-action narrative behind each departure (who acquired whom) is deliberately NOT asserted — the receipted claim is "vendor stopped pricing the symbol by 2026-08-13", which is all the graph needs |
| source-key rename | — (none) | zero key changes |
| unverifiable | — (none) | — |

Arithmetic closure: 2,356 − 26 + 9 = **2,339** ✓; 941 − 18 + 1 = **924** ✓.

## 3. Findings beyond the diff

1. **Supergroup layer:** the source tree root carries SIX unlabelled level-1 groups
   ("1"–"6": 10/10/8/7/3/2 themes) above the 40 themes; the committed schema flattens them
   (flattening in group order reproduces committed ordering exactly, so nothing committed is
   wrong). Recorded in `extraction_meta.json`; W3A carries `supergroup_index` in node
   `source_meta`; NOT materialized as hierarchy (PARENT_OF is W4's).
2. **Crosswalk grain:** `config/theme_crosswalk.yml` `subsector_keys` are TOP-LEVEL Finviz
   theme NAMES (14 distinct; 0 of the 268 subtheme keys) — there is no concept-grain
   mechanical Finviz→canonical path, and none is minted (plan §0b).
3. **The 2026-06-27 extraction memory note** understates the tree by one level (it said
   Root → children[0] name "1"); corrected in this record and in the account-local memory at
   session end.

## 4. What promotion means (and when)

The fresh tree replaces `data/themes_heatmap/themes_tree.json` ONLY through the W3A refresh
contract (atomic, receipted, interlocked — plan §3) in the build phase, after the plan's
adversarial review. `tree_history.jsonl` gains the 2026-08-14 row; the graph's two-vintage
ladder (2026-06-27 → 2026-08-14) materializes memberships with the dispositions above. Until
that lands, nothing in `data/` moves — this document + receipts are the review artifact.
