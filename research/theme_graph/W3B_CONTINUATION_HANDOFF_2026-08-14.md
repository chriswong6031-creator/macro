# GMI Theme Graph — W3B continuation handoff (emitted by the W3A session, 2026-08-14)

**For:** the next session, which owns W3B (Dual-market ThemeState behind measurement
eligibility) and NOTHING ELSE — one sub-wave per session (G0.7; directive §16).
**Read first:** masterplan §0 gates (incl. G0.12/G0.13) + §7 W3B bullet + §11 (2026-08-14
entries); directive `CEO_W3_CONTINUATION_DIRECTIVE_2026-08-14.md` §§32–38 (W3B pre-charter,
verbatim); `W3A_LOCAL_THEME_PLANE_PLAN.md` (what now exists and why); sweep Addendum 1.
Current tree outranks this handoff on conflict — verify, then adjudicate discrepancies openly.

## 1. What W3A shipped (the substrate you inherit)

Store after the W3A materialization (verify against live `_meta.json`, not this snapshot):
**3,878 nodes** (641 `local_theme` = 268 finviz + 373 ths; 529 new `co:us:*`) / **8,292 edges**
(2,365 finviz MEMBER_OF incl. 26 closed; 237 basket→ltheme + 61 ltheme→theme EXPRESSES; zero
finviz→canonical) / 11 evidence / **641 capability rows (499 candidate / 142 semantic_only)**.
Suites: test_finviz_tree_refresh (120) + test_theme_graph_local_plane (54) +
test_theme_sources_registry (5) + theme-graph regression (141) all green; guard `--strict` rc 0.
- Local-theme plane in `data/theme_graph/`: `kind=local_theme` nodes — `ltheme:finviz:<key>`
  (268) + `ltheme:ths:<code>` (373) — with mint-time `source_meta`; capability lives in the
  **sidecar `data/theme_graph/capability.parquet`** (nightly re-derived, anti-ratchet — NOT a
  node column); MEMBER_OF company→ltheme (two-vintage ladder: declared seed 2026-06-27 +
  promoted 2026-08-15 UTC; 2,330 v1 rows era=reconstruction, the 35 v2 changes era=observed);
  EXPRESSES basket→ltheme (237) and ltheme→theme (61); ZERO mechanical Finviz→canonical.
- Finviz refresh contract: `scripts/fetch_finviz_themes.py --refresh-tree` — receipted,
  interlocked BOTH directions (growth walls included), atomic promote-or-rollback, ticker- and
  key-continuity detection refusing to auto-promote suspected renames; manual cadence by ruling
  + TWO nightly advisory tripwires (subsector-key drift; member-perf coverage drop). First live
  receipt: `tree_refresh_receipts/20260815T020134Z.json` (promoted, sha 1d597c44c8ce).
- Rights plane: `config/theme_sources.yml` (SOLE authority; per-row evidence booleans are
  mint-time snapshots with no enforcement power) + `engine/theme_graph/rights.py` emission gate
  + F20 grandfathered path list with growth-pinned test.
- Corroboration class: evidence kind `external_classification` (+provider/claim_type) — EMPTY
  by design; probation queue seeded with 234 basket↔subtheme `mapping` proposals (k=20 shuffle
  null attached, mean 3.85); nothing ratified; the build ignores non-ratified rows.
- Docs: reconciliation + receipts, rights/procurement note, sweep Addendum 1, plan §9 (review
  amendments — READ IT, several constants and semantics changed there), operator report,
  masterplan §11 entries (directive adjudication + W3A-shipped).

## 2. W3B objective (directive §32, unchanged)

Determine which local nodes support DEFENSIBLE ThemeState and begin nightly PIT accrual.
Never state-over-everything: eligibility gates first (§33 — thresholds preregistered or baked
from history, never "sound reasonable"; coverage-floor abstention mandatory), named legs only
(§34), dual-plane output (local survives independently; canonical never overwrites local, §36),
consequence-ledger prep through the TIL W6 pack (§37; R-TIL-6 excess-over-placebo).

## 3. Entry tickets (verify each before writing code)

1. **Attention primitives are still synapse-UNREGISTERED** (`china_comment`, `china_lhb`,
   `china_zt_pool` — verified absent 2026-08-14). W2 filed them to owners; W3B may consume an
   attention leg ONLY once its owner registers it. If still unregistered, W3B ships without
   attention legs (honest nulls) — do not register them yourself (G0.3).
2. **qledger moved under you:** 9 eval-os commits 2026-08-13→14 (matched-control evidence
   contract, PIT replay clock, no-pooled-mixed-direction). Sweep row #42's ruling stands — the
   GMI expectation-ledger home is decided WITH the QI owner; re-read `engine/qledger.py` state
   and the eval-os program docs before deciding.
3. **Market Memory:** rubric #5346 scored Theme/GMI 16/35 (rejected) because edge identity /
   ThemeState history / grading didn't exist. W3B builds exactly those; a theme record class is
   still a SEPARATE, later, Konseki-side reviewed contract — not a W3B deliverable.
4. **W2 constraints bind unredefined** (masterplan §11 W2): trading legs = decomposed
   corr + vol-ratio, never raw beta as "co-movement"; CN quarter-horizon caveat; economic null;
   LHB refused as attention; era disclosure everywhere.
5. **2026-11 attention re-probe** (prereg §6) may overlap W3B's session window — if you charter
   attention eligibility, coordinate with that re-probe rather than duplicating it.
6. **First THS weekly scrape** fires Saturday 2026-08-15 UTC (receipts dir created then;
   tripwire loud-by 2026-08-25). W3B inherits whatever cadence reality the receipts show —
   check `data/baskets_china_ths/receipts/` + `_cadence.json` before trusting CN freshness.

## 4. Eligibility substrate W3A hands you

`capability=measurement_candidate` marks nodes passing the DEFINITIONAL floor only (≥3
price-covered live members — `capability.v1`, existence check, not an eligibility judgment).
Tonight: **499 candidates / 142 semantic_only** across both markets (the 142 = all 136 unseeded
THS concepts + 6 substrate-thin US subthemes; per-row `capability_basis` names the substrate —
US = ohlcv∪stocks stores, CN = `data/china_search/closes.parquet`, the panel
`scripts/c1_cn_global_beta.py::_panel()` reads; `cn_global_beta` itself is pure compute).
Your gates re-test every node — candidates AND `semantic_only` (the sidecar re-derives nightly;
promotion on improved substrate is automatic by design, review C2). If eligibility work
genuinely needs membership for unseeded concepts, extend it through the OWNER pipeline
(seeder/snapshots — raw side-cars carry members for all 373 concepts) as a chartered W3B step;
do not read snapshots directly into the graph without that charter (residue, plan §0b).

## 5. Known residue (named, non-blocking)

- **US action-board as-of asymmetry:** `site/basketdata/action_board.json` carries no
  board-level as-of (CN board has one). W3C's input contract needs it; file to the board owner
  when W3C's charter opens (or earlier if the owner is already in the file).
- **Finviz/THS display rights unresolved** — internal-only stands; the W6 design wave is the
  forcing point (rights note §1). Nothing in W3B needs resolution (no user surface in W3B).
- **Finviz→canonical mappings:** zero exist by ruling (40-grain names insufficient). 234
  probation `mapping` proposals (null baseline attached) await curation — ratification is an
  operator/delegated act, never a build step.
- Two probation-writer implementations (refresh inline + engine module) pinned equal by a
  contract test — reconcile when the collector may lawfully import the engine (cosmetic).

## 6. Verification commands (cold-stranger test)

```bash
python3 scripts/check_theme_graph_contracts.py --strict          # store lawful
python3 - <<'EOF'                                                # plane census
import json; m = json.load(open('data/theme_graph/_meta.json'))
print(json.dumps({k: m[k] for k in ('counts','per_suite') if k in m}, indent=1))
EOF
python -m pytest tests/test_theme_graph_local_plane.py tests/test_finviz_tree_refresh.py -q
```
Expected: guard rc 0 (one licensing-snapshot ::notice on 3 W1b vendor rows is DESIGNED);
_meta counts 3,878 nodes / 8,292 edges / 641 capability; suites 120+54+5 green.

## 7. Do-not-redo (binding unless refuted with new evidence)

- No ThemeState before eligibility gates exist and pass review (that IS W3B — but gates first).
- No LLM anywhere in eligibility/state (G0.6 unchanged; coverage-gap LLM proposals remain
  out-of-scope until someone charters them WITH curation).
- No new synapse entries for W3B state without the conscious-census toll; the three
  `theme-graph-*` entries extend additively.
- The zero-mechanical-Finviz-canonical ruling stands until concept-grain curation exists.
- Do not "fix" W2's nulls by redefinition (directive §35). Economic stays null.
- One sub-wave per session; W3C does not start in the W3B session.
