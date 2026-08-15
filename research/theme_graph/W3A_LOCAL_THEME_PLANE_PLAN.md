# W3A — Dual-market Local Theme Plane: implementation plan (pre-build, adversarially reviewed)

**Status:** PLAN — reviewed by opus `reviewer` BEFORE any production taxonomy/graph mutation
(directive §61.7); findings folded, review record in §8 below.
**Program:** GMI Theme Graph — `research/GLOBAL_MARKET_INTELLIGENCE_MASTERPLAN_BY_FABLE.md`
(§0 gates all bind, incl. new G0.12/G0.13; §7 W3A charter; §11 2026-08-14 entry).
**Directive:** `research/theme_graph/CEO_W3_CONTINUATION_DIRECTIVE_2026-08-14.md` (verbatim source).
**Session:** 2026-08-14, branch `claude/gmi-theme-graph-w3a`.

## §0 What W3A ships (and §0b what it refuses)

Ships: (1) masterplan amendment [DONE pre-plan, commit `85b0c0479ef6`]; (2) disposition-sweep
re-census addendum; (3) Finviz reconciliation doc + committed receipts; (4) Finviz structure
refresh contract implementing the reserved `--refresh-tree` in the OWNER collector
`scripts/fetch_finviz_themes.py` (G0.3 EXTEND, no second collector) + a nightly advisory
key-drift tripwire; (5) local-theme plane in the existing graph stores: `kind=local_theme`
nodes for Finviz subthemes (268) + THS concepts (373), memberships/expressions per §2;
(6) capability classification columns; (7) rights registry `config/theme_sources.yml` +
emission gate; (8) corroboration evidence class (schema + gate only, zero external rows);
(9) coverage-gap diagnostic (mechanical cases) + probation queue contract; (10) basket↔subtheme
relation PROPOSALS (probation only, zero promoted edges); (11) hostile tests A–M;
(12) rights/procurement notes (Finviz + Theia); (13) operator report + W3B handoff.

Refuses (in-scope temptations, each with the law): ThemeState of any kind (W3B); new synapse
entries (extends the three existing `theme-graph-*` artifacts; probation/receipts are data-plane
sidecars like `basket_membership_pit`); mechanical Finviz-subtheme→canonical EXPRESSES edges
(the crosswalk's `subsector_keys` are TOP-LEVEL Finviz theme names — 14 distinct, 0 of 268
subtheme keys — so any mechanical mapping would smear application-tier subthemes onto
infrastructure-tier canonical themes, the exact forced-mapping G0.12 bans); snapshot-direct THS
memberships for unseeded concepts (basket-mediated only this wave; residue for W3B); LLM
involvement anywhere (coverage-gap runs mechanical cases only); user surfaces; S&P/Theia
ingestion; weights of any kind (G0.13); PARENT_OF edges (W4 owns hierarchy — source parents ride
metadata); mutations to the 49 curated baskets or any THS membership document.

## §1 Reconciliation results (input facts, receipted)

Fresh live extraction 2026-08-14 (receipts committed under `research/theme_graph/w3a_finviz/`):
40 themes / 268 subthemes / 2,339 memberships / 924 unique tickers — EXACTLY the operator's
2026-08-14 extraction counts, so operator view (C) ≡ fresh view (D). Committed tree (A) ≡ old
extraction (B) verified content-identical (2,356 memberships, both 2026-06-27 vintage, tree
sha `e0f85510…`). A→D delta: ZERO structural changes (themes/subthemes/keys/names/descriptions/
ordering all identical); 26 membership removals + 9 additions across 32 subthemes; 18 tickers
departed, 1 arrived (SNDK, taking PSTG's slot in `bigdatainfrastructure` + `hardwarestorage`).
Disposition (per-delta, no "looks close enough"): all 18 departures are **dead-at-source** —
each is ABSENT from Finviz's own screener perf in the committed `perf_snapshot.json`
asof 2026-08-13 (923 = 941 − 18 priced), i.e. the vendor itself no longer prices the symbol;
zero curation removals; SNDK's 9 additions = new listing at vendor; zero renames; zero parser
artifacts (two independent parsers element-identical; byte-identical re-fetches; counts match
operator independently). Arithmetic closes exactly: 2,356 − 26 + 9 = 2,339; 941 − 18 + 1 = 924.
Discovery: the source carries an unlabelled 6-supergroup layer above themes (10/10/8/7/3/2)
that the committed schema flattens — recorded in `extraction_meta.json` and carried as
`source_meta` on nodes, NOT resurrected as hierarchy (W4's).

## §2 Graph representation (the design pinned for builders)

**Node kind `local_theme`** (nodes.v1 enum extended additively). Node id grammar:
`ltheme:<source_family>:<source_local_id>` — `ltheme:finviz:<subtheme_key>` (268; keys verified
globally unique in-tree) and `ltheme:ths:<concept_code>` (373, from
`data/baskets_china_ths/concept_map.json` asof 2026-06-27). Guard learns the grammar
`^ltheme:(finviz|ths):[A-Za-z0-9_.\-]+$` (source families extend deliberately, like
SUITE_MARKET). NO nodes for the 40 top-level Finviz themes and NO nodes for supergroups —
both ride `source_meta` as parent references (directive §26: hierarchy stays metadata until W4).

**New nodes.v1 columns (additive, nullable):** `capability`
(`semantic_only|measurement_candidate|measurable` — internal, never user-facing, never a market
state), `capability_basis` (rule id string), `source_meta` (JSON string: `source_family`,
`source_local_id`, `market`, `source_label` — the source's own display name; zh for THS,
en for Finviz — `grain` (`finviz_subtheme|ths_concept`), `parent_source_label`/`parent_source_key`
(Finviz theme; null for THS), `supergroup_index` (Finviz only), `key_aliases` (list, empty
unless a ratified continuity act), `rights_family` (join key into `config/theme_sources.yml`)).
G0.9 name ruling (charter interpretation recorded here for review): the no-name rule governs
GMI-MINTED vocabulary; a source-native local node carries its source's own label because the
source vocabulary is already user-visible (Finviz names render on the live themes heatmap;
THS concept names on cn surfaces) — `name_en`/`name_zh` populate from `source_label` for those,
while future GMI-minted candidates (coverage-gap/probation) stay name-null until ratified AND
resolved. Status: all W3A local nodes `status=canonical` (they are canonical AS source-local
concepts — not as global vocabulary; kind+source_meta carry that distinction).

**New edges (edges.v1 types unchanged; guard pairing table extended):**
- `MEMBER_OF company→local_theme` — Finviz only this wave: 2,339 open + 26 closed edges from the
  two-vintage ladder (below). This is NOT the W1b-refused derived company→theme edge: it is the
  SOURCE'S OWN direct claim at the source's own grain, carried with source provenance (G0.13);
  the refusal of DERIVED company→canonical-theme composition stands unchanged (consumers still
  compose joins). Contract README gains a paragraph saying exactly this.
- `EXPRESSES basket→local_theme` — 237 `thsc*` baskets → their concept node, provenance =
  membership doc's own `ths_concept` field (the mechanical join W1b §11 already blessed).
- `EXPRESSES local_theme→theme` — THS ONLY: the 61 crosswalk-curated `ths_concept_ids`
  (concept-grain curation from W1b, provenance `crosswalk`). Finviz: ZERO (no concept-grain
  curation exists; §0b). Null canonical mapping everywhere else is the lawful steady state.
- Company nodes minted for Finviz tickers not yet in the graph (~250 expected) via
  `company_node_id(suite="finviz_themes")` — `SUITE_MARKET` gains `"finviz_themes": "us"`
  deliberately; ratified identity breaks (e.g. the 2026-08-14 ABX/GOLD rows) apply automatically.
  **Symbol-variant collision rule:** before minting, a Finviz symbol whose `.`↔`-` variant
  already exists as a company node resolves to the EXISTING node (never a variant twin); the
  build prints the resolution table into the reconciliation receipts.

**Era/PIT (G0.2, README `date_provenance` table reused exactly):** initial materialization is
`era=reconstruction`, `date_provenance=raw_snapshot`, `belief_time=` build date. Two-vintage
ladder from the OWNER PIT tape `tree_history.jsonl` (deduped by content hash): vintage 1 =
2026-06-27 content (evidence: committed `finviz_themes/finviz_themes_map.json`, asof field
2026-06-27); vintage 2 = 2026-08-14 promoted tree (evidence: the W3A extraction receipts).
Membership in both → `valid_from=2026-06-27`, open. In v1 only → closes `valid_to=2026-08-14`
(the date the source was first observed WITHOUT it — never an invented mid-window date). In v2
only → `valid_from=2026-08-14`, open. `valid_from` means FIRST OBSERVED, never "joined" —
the raw_snapshot provenance row already says this; no backdating anywhere. THS concept nodes:
`birth_date=2026-06-27` (concept_map asof, raw_snapshot). Future refreshes append
observed-era changes through the same ladder (the materializer reads the tape, so the graph
inherits every future vintage with no new code path).

**Materializer-level shrink wall (2nd wall behind the refresh interlock):** a nightly diff that
would close >25% of a source family's live memberships refuses without an explicit
`--allow-source-shrink <family>` (MAX_AUTO_SHRINK precedent; test B proves the refresh wall,
a companion test proves this wall catches a hand-edited bad tree that bypassed refresh).

## §3 Finviz refresh contract (implements the reserved `--refresh-tree`)

In `scripts/fetch_finviz_themes.py` (owner pipeline; the perf path is untouched):
re-trace map JS → runtime → chunk (never hardcode hashes; module/chunk ids re-derived each run);
strict object-literal parser (no eval; raises on unknown node shapes); complete-or-fail (any
non-200, any parse failure, any theme with zero subthemes, or an empty member CSV ⇒ REFUSE —
partial trees never promote; test A). Receipts: `data/themes_heatmap/tree_refresh_receipts/
<UTC-ts>.json` — urls, sha256s, byte sizes, http statuses, retrieved_at, parser_version,
traced module/chunk ids+hashes, counts (themes/subthemes/memberships/tickers), previous-tree
hash, new-tree hash, structural diff summary, shrink stats, identity-resolution report
(key renames flagged via member-Jaccard ≥ **J=0.8** between a removed and an added key —
flagged renames REFUSE auto-promotion and emit a probation proposal `kind=key_rename` for
curation, so neither a silent fake break nor a silent auto-merge can happen; test C),
`promoted: true|false` + reason. Interlocks (preregistered, rationale in-line): membership
removals >**25%** of prior memberships ⇒ refuse without `--allow-shrink` (observed genuine
churn is 1.1% per 7 weeks — 26/2,356; 25% is ≥20× any observed drift and still trips test B's
40% parser catastrophe); ANY decrease in theme count or >**5%** decrease in subtheme count ⇒
refuse the same way (structure empirically frozen since June; a structural shrink is
presumptively a parse failure). Promotion is atomic (tmp+rename of `themes_tree.json`, then
`tree_history.jsonl` append via the existing `append_tree_history`, then receipt) and a failed
run leaves the committed tree BYTE-IDENTICAL (tests A/B assert bytes). **Cadence ruling
(directive §21 requires justification):** MANUAL/receipted-on-demand, not scheduled — because
(1) the rights review (§6) is unresolved and an unattended mutation cadence on an undocumented
vendor route deepens exactly the dependency §15 says to escalate first; (2) the structure is
empirically frozen (zero structural changes in 7 weeks; member churn 1.1%) so a weekly pull buys
nothing the perf lane doesn't already reveal; (3) DETECTION is automated instead: the nightly
perf fetch now compares the 268 subsector keys returned by `map_perf` against the committed
tree's keys and emits a line-start `::warning` on any symmetric difference (advisory tripwire,
non-fatal, no mutation) — so a source restructure goes loud within one night while mutation
stays a receipted human-triggered act. Revisit cadence when rights resolve.

## §4 Capability classification + rights + corroboration + coverage-gap

**Capability (preregistered rule `capability.v1`, definitional not evaluative):**
`measurement_candidate` iff ≥**3** live members resolve to a price store file
(US: `data/baskets/ohlcv/` else `data/stocks/`; CN: the store `engine/cn_global_beta` reads) —
3 is the definitional minimum for a cross-sectional aggregate to be an aggregate, NOT an
eligibility judgment; W3B's preregistered gates re-test every candidate and may demote freely.
Everything else `semantic_only` (incl. all 136 unseeded THS concepts — no graph membership
substrate; `capability_basis` says so). `measurable` is UNREACHABLE in W3A (W3B mints it).
CANONICAL_MAPPED is NOT a fourth enum value — it is derivable (an EXPRESSES edge to `theme:*`
exists) and storing it would drift from the edges (single-source-of-truth).

**Rights registry `config/theme_sources.yml`:** rows for `finviz_themes`, `ths_concepts`,
`mastermind_curated` (+ reserved `sp_kensho`, `theia`, commented): `rights_class ∈
{internal_only, derived_display_ok, direct_display_ok, unresolved}`, `auth_class`
(keyless_public/entitled/…), `source_route`, `review` (date + who + outcome), `notes`.
Initial classes: finviz_themes=**unresolved** (⇒ treated as internal_only for every GMI
emission; the pre-existing themes-heatmap surface is the OWNER's product predating GMI and is
inventoried in the rights note, not retro-gated by GMI), ths_concepts=**unresolved** (same
posture; existing cn surfaces grandfathered as owner products), mastermind_curated=
**direct_display_ok**. Enforcement: `engine/theme_graph/rights.py` —
`rights_class(family)` + `assert_public_emission_allowed(family)` raising unless
{derived_display_ok, direct_display_ok}; guard checks every `source_meta.rights_family` in the
store has a registry row (unknown family = hard error, fail-closed); test L proves refusal.

**Corroboration class:** evidence.v1 gains kind `external_classification` + nullable columns
`provider`, `claim_type ∈ {membership, exposure, ecosystem_role, description}`, `rights_class`.
ZERO external rows minted in W3A; test J proves coexistence + no netting on a fixture pair.

**Coverage-gap diagnostic `scripts/theme_coverage_gaps.py` (mechanical only, LLM-free):**
case A — given instrument ids (file/stdin; no board coupling in W3A), report ids with zero live
local-theme membership; case D signal — ids whose ONLY memberships are themes above a breadth
REPORTING floor (floor is a report parameter, printed, never a truth claim). Output: report
JSON + optional probation proposals. Cases B/C are documented with their data dependencies
(theme_discovery clusters; co-movement) and deferred to W3B where those inputs have state.
**Probation queue contract** `data/theme_graph/probation/proposals.jsonl` (append-only):
`proposal_id`, `kind ∈ {new_theme, merge, split, mapping, key_rename}`, `evidence_refs`,
`proposed_by ∈ {coverage_gap, overlap_stats, refresh_identity, llm_proposed}`, `created`,
`status ∈ {proposed, ratified, rejected}`, `ratified_by` — nothing in the queue is production
vocabulary; ratification is a curated act (G0.6); the graph build ignores non-ratified rows.

**Basket↔subtheme relation proposals `scripts/propose_basket_ltheme_relations.py` (one-shot):**
member-overlap stats (Jaccard + containment both directions) between the 49 curated baskets and
268 Finviz subthemes; pairs above a REPORTING floor (containment ≥0.5, a visibility cutoff
labeled as such) land as `kind=mapping` proposals with the stats as evidence fields. ZERO edges
minted (G0.13 bans string/overlap auto-promotion; a human ratifies specific pairs later).

## §5 Hostile acceptance tests (A–M → concrete tests)

`tests/test_finviz_tree_refresh.py`: **A** half-tree fixture → refusal + byte-identical tree +
no history append + `promoted:false` receipt; **B** 45%-removal fixture → interlock + receipt
records shrink + byte-identical store (companion: materializer 2nd-wall on a hand-edited tree);
**C** displayName rename (key stable) → same node id, label update only, zero membership churn;
key-rename fixture (old key out, new key in, Jaccard 0.9) → refusal + `key_rename` proposal,
NO silent break, NO silent merge.
`tests/test_theme_graph_local_plane.py`: **D** one ticker leaves one subtheme, stays in another
→ exactly one edge closes (live case exists: the 08-14 vintage does this 26 times); **E**
identity break — a finviz symbol carrying a ratified break row minted at the correct epoch
(fixture uses the real 2026-08-14 ABX/GOLD rows); **F** SNDK-class member of ≥5 subthemes →
all edges coexist, no single-label collapse; **G** Finviz node with zero canonical refs →
node+memberships survive, guard green; **H** same for an unmapped THS concept (312 live cases);
**I** unseeded THS concept + a 4-member fixture failing capability.v1 → `semantic_only`, no
state fields anywhere; **J** finviz membership + counter `external_classification` row →
both survive latest-belief, nothing netted; **K** as-known-at(T) with `belief_time≤T` excludes
a membership learned T+5 (store-semantics fixture); **L** `assert_public_emission_allowed`
raises for `unresolved`/`internal_only` and passes for display classes; **M** the three
`theme-graph-*` synapse entries carry all six authority booleans literal false (regression pin).
Suite registered in `.github/ci/legacy-jobs.yml`.

## §6 Rights + procurement notes (separate doc)

`research/theme_graph/W3A_SOURCE_RIGHTS_AND_PROCUREMENT.md`: Finviz inventory (what is consumed
today, routes, auth class, Elite-export/FAQ facts WITHOUT legal conclusions, the
internal-until-resolved ruling, what resolution would take); Theia procurement question list
(directive §13 verbatim) + recommendation posture; S&P/Kensho corroboration posture (no
undocumented download dependency). Escalation: rights questions go to the operator — the note
prepares the ask, it does not guess an answer (G0.13).

## §7 Build/model routing

Opus `builder` ×2 sequential in this worktree on my pinned spec: builder-1 = refresh contract +
tripwire + tests A–C (touches `scripts/fetch_finviz_themes.py`, new receipts dir, fixtures);
builder-2 = graph plane (identity/materialize/store/guard/schemas/rights/coverage/proposals +
tests D–M). Main loop (Fable) = this plan, reconciliation adjudication, masterplan/sweep/docs,
review adjudication, merge. Reviewer = opus, §8. Sonnet = census only (done). Docs/receipts
committed by main loop.

## §8 Adversarial review record

Review 1 (plan, PRE-BUILD): [to be filled — reviewer verdict + findings + resolutions]
Review 2 (diff, PRE-PR): [to be filled]
The reviewer must answer the directive §55's fifteen questions explicitly; §55.13 (byte-identical
boards) is N/A-by-scope in W3A (no board contact) and becomes W3C's GATE-1; §55.9 (user-facing
claims) is N/A (no user surface); every other question has a W3A answer.
