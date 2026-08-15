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

**Review 1 (plan, PRE-BUILD, opus reviewer, 2026-08-14): PASS-WITH-CHANGES.** All fifteen §55
questions answered explicitly (report retained in the session record; §55.11 was UNANSWERED in
the draft — resolved by §9.8's null baseline; §55.13/§55.9 N/A-by-scope confirmed). Four
challenged rulings UPHELD: (a) MEMBER_OF company→local_theme is a first-party source claim, not
the refused derived composition — structural proof: the Finviz plane carries zero ltheme→theme
edges, so no composition path to canonical exists; (e) `valid_to` = extraction-observation date
is correct semantics (the perf lane observes a different predicate); (f) the zero-Finviz-EXPRESSES
/ 61-THS-EXPRESSES asymmetry is evidence-based; (h) no backward laundering. Eight binding
conditions C1–C8 + strongly-recommended items — ALL adopted (two adopted-with-modification,
reasons in §9): resolutions are §9 below, which SUPERSEDES the named §2–§5 clauses. Reviewer
independently reproduced every reconciliation headline (923 priced members, 18/18 departures
absent, arithmetic closure, 14 subsector_keys, 373 unique THS codes).
**Review 2 (diff, PRE-PR):** [to be filled]

## §9 Review-1 amendments (BINDING — supersede the named clauses above)

1. **Growth interlocks (C1/F1, supersedes §3 interlock list):** symmetric walls — total
   membership INCREASE >10% ⇒ refuse without `--allow-growth`; any single subtheme growing
   beyond max(2× prior, prior+15) ⇒ refuse; unique-ticker increase >10% ⇒ refuse. Hostile test:
   a mis-nesting fixture (theme-level member lists smeared onto every subtheme, ~6×) must refuse
   with bytes unchanged. Rationale: observed genuine adds 0.4%/7wk; the catastrophic direction
   in an append-only store is growth (false edges are permanent; closes at least carry dates).
2. **Shrink constants re-derived against parser failure modes (C7/F2, supersedes §3's 25%/5%):**
   total membership removals >10% ⇒ refuse (catches the last-member-of-every-subtheme truncation
   = 11.5%; manual-cadence genuine churn ~1.1%/7wk keeps 10% ≥4× any plausible gap's drift);
   ANY theme or subtheme DELETION ⇒ refuse without `--allow-shrink` (zero-tolerance, symmetric —
   the "structure empirically frozen" rationale applies at both levels); any single subtheme
   losing >50% of members ⇒ refuse; co-occurrence rule: >30% of subthemes losing ≥1 member in
   one refresh ⇒ refuse (the distributed-truncation fingerprint — 2026-08-14 genuine churn
   touched 12% of subthemes; a real vendor restructure that legitimately exceeds this arrives
   with structural changes and is handled by receipt + explicit flags). Boundary tests at the
   walls (9.9%/10.1%), not only far-field.
3. **Capability moves OFF the node row (C2/F3, supersedes §2's node columns for capability):**
   node rows are keep-first write-once (`NODE_KEY=("node_id",)`) — so `capability`/
   `capability_basis` live in a re-derived append-only sidecar `data/theme_graph/capability.parquet`
   (`node_id`, `capability`, `capability_basis`, `computed_at`, `engine_version`; current view =
   max `computed_at` per node; recomputed nightly with the graph build). This kills the one-way
   ratchet: substrate improvements re-derive automatically, and **W3B may promote a
   `semantic_only` node** whose substrate improved — stated here explicitly (F12's question).
   Synapse: the sidecar registers as `theme-graph-capability` (4th GMI entry, display, six-false)
   — F15's registration demand adopted for GMI's OWN artifacts; the probation queue and refresh
   receipts remain unregistered as curation/audit sidecars with no signal consumers (justified on
   own reasoning — the drafted `basket_membership_pit` precedent citation was WRONG, that module's
   artifacts ARE registered, citation withdrawn); registering the OWNER's `themes_tree.json` is
   not GMI's act (G0.3) — its freshness instrumentation is §9.6's coverage tripwire + receipts,
   and the sweep addendum records this reasoning.
   `name_en`/`name_zh`/`source_meta` are MINT-TIME snapshots (write-once with the row);
   the graph is a join spine, never the display-label authority — current labels resolve from
   the live tree (source of record); a displayName rename lands in the refresh receipt's
   identity report, changes no node bytes, and test C asserts exactly that (supersedes §5 test
   C's "label update only" phrasing, which keep-first makes impossible).
4. **Rights single-authority (C3/F4+F19+F20, supersedes §4 rights mechanics):** the REGISTRY
   (`config/theme_sources.yml`) is the sole rights authority; per-row evidence licensing
   booleans are mint-time snapshots with zero enforcement power (README amended to say so);
   `rights.py` consults the registry only. New vendor evidence mints booleans DERIVED from the
   registry ((True, False, False) while `unresolved` — never `LICENSE_VENDOR`'s display-True).
   The three committed W1b vendor rows carrying `licensing_display_ok=True` stay as historical
   snapshots (append-only store); the guard emits a WARNING naming any row whose snapshot
   disagrees with its family's current class (never an error — history is not editable).
   **F19 resolution (label vs structure):** the vendor's LABELS are already-public vocabulary
   and ride `name_*` lawfully; the subtheme→member STRUCTURE as a dataset is what rights
   govern and stays internal-only — this exact distinction lands in the README and the
   `name_en` schema description (same PR). **F20:** the grandfather is an enumerated
   `grandfathered_surfaces:` path list in the registry with a review row per entry + a test
   pinning that the list cannot grow without one; the full public-emitter CI walk is recorded
   as a W6 entry ticket (structural enforcement at the wave that creates new emitters).
5. **Vintage ladder mechanics (C4/F5 + F21, supersedes §2 era/PIT paragraph's tape claim):**
   vintage 1 is a DECLARED SEED — `finviz_themes/finviz_themes_map.json` (asof 2026-06-27,
   commit `04e45a3da046`), named as such in code; the tape (`tree_history.jsonl`) supplies
   vintages from the W3A promotion on. Ladder ordering strictly by asof; dedupe
   ADJACENT-identical vintages only (an A→B→A revert keeps all three — a re-appearance is a new
   open interval). `--refresh-tree` stamps the UTC extraction DATE (wall clock) — never
   `_asof_stamp()` session dates, which belong to the EOD perf board (a Saturday structure
   refresh must not stamp Friday).
6. **Coverage tripwire upgraded (F14, extends §3's key-drift tripwire):** the nightly perf path
   additionally warns (line-start `::warning`, non-fatal) when member-perf coverage drops ≥5
   members or ≥1% vs the tree (the 923/941 pattern would have flagged all 18 departures near
   their true dates); §3's cadence ruling gains the disclosure that `valid_to` under manual
   cadence is INTERVAL-CENSORED (bounded by refresh gaps) — W3B must not read it as a point
   observation.
7. **Ticker-continuity across departures×arrivals (C5/F6, new §3 obligation):** before
   dispositions, every (departed, arrived) pair is tested for identity continuity — subtheme-set
   signature match = SYMMETRIC DIFFERENCE ≤1 between the departed ticker's subtheme set and the
   arrived ticker's (a true rename preserves the set, ±1 for co-occurring churn) ⇒ suspected
   ticker rename ⇒ REFUSE auto-promotion + probation `kind=identity_continuity` proposal
   (ratified outcome uses the existing `SAME_AS`/`merged_into` machinery). Containment alone is
   WRONG here — PSTG(2)⊂SNDK(9) has containment 1.0 yet is a substitution of different issuers
   (symmetric difference 7 ⇒ correctly unflagged); SNDK/PSTG is the pinned negative fixture, a
   same-set rename the positive.
   Key-rename continuity (C7/F13, supersedes J=0.8): containment of the SMALLER member set
   ≥0.6 with one-member slack below n=9 (a rename + 1 swap at n=7 MUST flag — that negative
   control replaces the trivially-passing J=0.9 fixture).
8. **Null baseline for relation proposals (F8, extends §4):** every basket↔subtheme proposal
   file prints the containment floor's yield under k=20 basket-label shuffles (mechanical,
   LLM-free) so curators see the false-positive rate; this is also the recorded W3A answer to
   §55.11 (the honest form: W3A emits no measurements, and its one derived-pair surface now
   carries its own null).
9. **Coverage-gap case A is the CO-OCCURRENCE form (F9, supersedes §4 case A):** pairwise
   shared-membership counts among supplied ids + ids sharing no concept with any other id —
   the motivating lithium exemplar (names WITH memberships that no concept jointly explains)
   must fire it; zero-membership ids remain reported as a sub-case. §56.D coverage reads boards
   READ-ONLY with artifact paths named (`site/factordata/{us,china}_standouts.json`), nothing
   written — C6/F10 resolved (numbers already computed in the operator report).
10. **Capability substrate (F12, supersedes §4's price-store rule):** price coverage resolves
    against the union `data/baskets/ohlcv/` ∪ `data/stocks/` ∪ the whole-market
    `massive_stock_day` store where present (builder verifies the CN store path
    `engine/cn_global_beta` reads and RECORDS it — W2 precedent); `capability_basis` names the
    substrate that satisfied the rule (self-describing). THS concepts resolve members via the
    basket join (the only membership path this wave) and `capability_basis` says so.
11. **Spec pins (F16):** finviz MEMBER_OF: `source_class="scrape"`,
    `confidence_basis="finviz_tree.v1"`, evidence = the extraction/refresh receipts; basket→ltheme
    EXPRESSES: `membership_doc.v1`; ltheme→theme: `crosswalk`. `market_scope`: `us`/`cn` per
    family. THS node ids use the CODE (ASCII digits; `concept_map.json` name→code resolved at
    build; zh names never enter ids). Future dangling `ths_concept` names: report-only via
    `_meta` unknown-list idiom, edge minted only on resolution. Rights guard scopes to rows
    whose `source_meta.rights_family` is non-null (pre-existing nodes exempt by construction).
    Guard additionally REFUSES any `basket:finviz_themes:*` id (the suite exists for company
    identity only — F18's optic closed structurally). `status=canonical` is lifecycle
    vocabulary, not an epistemic claim (F18 sentence).
12. **Join law + census grain (F7/F23/F22/F17):** README states the join law — canonical
    expression is ONE-hop (basket→theme); `ltheme→theme` is vocabulary resolution, never a
    second expression path — and the guard asserts the two paths agree over the 61 shared
    crosswalk rows. §56.B census carries membership-grain columns per market (direct company
    edges / basket-mediated / none) so the CN plane's two-hop shape is visible; counts are
    PER-LISTING (cross-listing issuer twins exist — SHOP/RIO/TSM class; `SAME_AS` across
    listings is W4's; disclosed, not resolved). Reconciliation table header hedged to the
    receipted claim ("vendor stopped pricing the symbol by 2026-08-13" — halts/suspensions
    share the footprint; F17).
13. **Company-node mint count corrected (C8/F11):** ~**512** new `co:us:*` nodes (924 fresh-tree
    tickers, 412 already present), store → ~3,860 nodes; build prints the actual resolution
    table and the receipt asserts against it, not against the withdrawn "~250".
14. **Addendum completeness (F24):** the sweep addendum lists every directive-§19-named organ
    with either its drift entry or an explicit "no commits since 2026-08-11, wiring/synapse
    verified" line.
