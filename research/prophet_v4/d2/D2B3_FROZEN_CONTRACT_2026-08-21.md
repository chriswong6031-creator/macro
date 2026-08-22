# V4-D2B3 — GMI Identity Correction Lineage: GOLD Reuse + IBIT Entity Kind (FROZEN CONTRACT)

Frozen by the Fable orchestration seat, 2026-08-21 (V4-D2B3 commission, `WS:PROPHET-US-V4-RECOVERY`).
Archaeology basis: two read-only census packets (graph/edge plane; Data OS + source evidence plane)
executed at `origin/main` = `12467e2d5e9d`, plus the orchestrator's independent verification of every
load-bearing mechanics claim cited below. This contract freezes the correction design. **No
implementation may begin until the §0 precondition is met.**

## §0 PRECONDITION GATE (binding)

The commission requires D2B2-US to be **DONE / PROVEN_LIVE from a natural GMI generation consuming
the Aug-22-or-later Data OS generation** before implementation.

State measured at freeze (one-shot checks, no polling, 2026-08-22T0x:xxZ):

- **Data OS half PROVEN.** The natural nightly (run head `e3665e6476d9`, a main descendant of the
  D2B2 merge `71b4813266c1`) committed `data: daily collection 2026-08-22` (`2509329de74f`):
  `data/reference/_receipt.json` `generated_at=2026-08-22T01:07:17`, `us_gmi_admission`
  `target_n=1236 / resolved_total=1210 / resolved_this_run=0` — the predicted natural steady state
  from an Aug-22 Data OS generation.
- **GMI projection half NOT YET PROVEN.** `data/theme_graph/` was last written by the D2B2 merge
  itself; no natural GMI generation consuming the Aug-22 Data OS generation had landed at freeze
  time (the nightly's graph phase historically concludes ~03:47Z).

**Therefore this session delivers archaeology + this frozen contract ONLY and stops.** The
implementing session must FIRST verify, one-shot: (a) a natural theme-graph bake with
`data/theme_graph/_meta.json` `computed_at` ≥ 2026-08-22 whose consumed master `generated_at` is
≥ 2026-08-22, and (b) sidecar us-scope counts holding the D2B2 steady state (us RESOLVED 1210 /
NOT_IN_MASTER 25 modulo rail drift recorded in that night's receipt). If absent: stop and report,
do not poll, do not code.

## §1 VERIFIED STARTING STATE (all claims re-verified by the orchestrator or quoted from the two packets)

Graph plane (`data/theme_graph/`, 3,878 nodes / 8,292 edges / 28,056 sidecar rows):

- `co:us:GOLD` — kind=company, status=canonical, epoch=1, minted 2026-08-11T12:12:07Z,
  provenance `membership_doc:baskets`. The pre-reuse (Barrick/Randgold-era) symbol node the
  ratified break says must be retired. NO `co:us:GOLD#2` exists.
- `co:us:B` — canonical epoch-1, minted 2026-08-15T02:32:46Z (the nightly after the 2026-08-14
  gold_miners roster repair), 3 latest-belief edges (gold_miners + two finviz themes).
- `co:us:IBIT` (kind=company) AND `etf:IBIT` (kind=etf) coexist, both canonical epoch-1.
- NO `co:us:ABX` node exists (only `co:ca:ABX.TO`, out of scope — the US break row's own note).
- Zero nodes anywhere with `status="retired"` or `identity_epoch>=2`; `retire_date`/`merged_into`
  are None on all 3,878 rows.
- Edges touching the targets (7): `MEMBER_OF co:us:GOLD→basket:baskets:gold_miners`
  (belief_time=2026-08-11, era=reconstruction, valid_from=2023-05-09, valid_to=NaN — **still the
  latest belief**: the 2026-08-14 roster repair added `co:us:B`'s edge but never closed this one);
  `MEMBER_OF co:us:B→` ×3 (belief 2026-08-15, era=observed); `MEMBER_OF
  co:us:IBIT→basket:baskets:crypto_rails` (the company-plane leak, evidence
  `ev:2fbc0291090881d1`); `TRACKS etf:IBIT→basket:baskets:{crypto,crypto_rails}` (lawful,
  preserved). Every one of the 8,292 edge_ids currently has exactly ONE belief row
  (`edges == edges_latest_belief` in `_meta.json`) — the closure lineage has never yet been used
  in production data.
- Sidecar (`identity_resolution.parquet`, append-only generations, KEY=(node_id, computed_at)):
  `co:us:B` DEFERRED_IDENTITY_EXCEPTION ×10 gens; `co:us:GOLD` DEFERRED_IDENTITY_EXCEPTION ×6;
  `co:us:IBIT` ENTITY_TYPE_CONFLICT ×10 (receipts name `etf:IBIT` and
  `SEC:US-XNAS-IBIT`); `etf:IBIT` no rows ever (derive_rows filters kind=="company",
  `engine/theme_graph/identity_resolution.py:535-536`); `co:us:ABX` no rows (no node).

Store mechanics (`engine/theme_graph/store.py`) — the decisive constraints:

- `NODE_KEY=("node_id",)` (:103) with `append_rows` keep-FIRST dedup (:296, prior-first concat
  :292): **node rows are write-once; a same-id retirement append is silently dropped.**
  `read_nodes()` (:203-204) applies no collapse and no status filter; a repo-wide sweep found NO
  consumer anywhere filtering `status`.
- `EDGE_KEY=("edge_id","belief_time")` (:104) + `read_edges(latest_belief=True)` collapse
  (:211-223): **edges already have a working, tested append-only correction lineage** — append a
  later-belief row for the same edge_id; the current view moves; history stays queryable via
  `latest_belief=False`; nightly re-emission of the original row is a keep-first no-op
  (`tests/test_theme_graph_materialize.py:480-496` pins closure surviving a rebuild).
- `CAPABILITY_KEY`/`IDENTITY_RESOLUTION_KEY = ("node_id","computed_at")` with latest-by-computed_at
  read collapses — the store's established pattern for per-node append-only fact lineages.
- `materialize.py` hardcodes `"status": "canonical", "merged_into": None, "retire_date": None` on
  every minted node (:279-280); NO code path emits retirement.
- Epoch law is LIVE at mint time: `materialize.py:252` loads `identity.load_breaks()`; :458/:466
  and :627/:645 mint through `identity.company_node_id(suite, symbol, breaks=...)`
  (`engine/theme_graph/identity.py:122-138`) — any current-source evidence for symbol GOLD or ABX
  (market us) mints `#2` today (`tests/test_theme_graph_identity.py:110-121`). The reason no `#2`
  exists is that no current GMI source references either symbol: the 2026-08-14 repair removed
  GOLD from gold_miners, and Finviz lists neither.
- Breaks registry consumers: mint path (identity.py via materialize) is load-bearing;
  `scripts/check_theme_graph_contracts.py:544-565` enforces node⇒row only (epoch≥2 requires a
  ratified row). Valid statuses `{candidate, canonical, retired, merged}` (:137).

Data OS + rails (evidence vintages: Nasdaq directory snapshot 2026-08-22, 13,169 rows; SEC CIK map
2026-08-18, 10,398 rows; both pinned inside `_receipt.json`):

- **B**: zero rows in security_master / vendor_aliases / issuer_master / migrations —
  `DEFERRED_IDENTITY_KEYS["B"]` (`scripts/build_security_master.py:517-532`) fail-closes it
  pending "a registered identity-scoped continuation+reuse amendment". Directory: `B` = "Barrick
  Mining Corporation Common Shares" (NYSE), CIK rail 756894.
- **GOLD**: one legacy row `SEC:US-XNYS-GOLD` (issuer_state DEFERRED_IDENTITY_EXCEPTION, no CIK,
  legacy mint 2026-08-13) — the disclosed open historical alias
  (`DISCLOSED_IDENTITY_EXCEPTIONS["GOLD"]`, :540-553), NOT issuer-safe across 2025-12-02.
  Directory: `GOLD` = "Gold.com, Inc. Common Stock" (NYSE), CIK rail 1591588 — matches the
  ratified break row exactly.
- **ABX**: zero Data OS rows. Directory: "Abacus Global Management, Inc. Class A Common Stock"
  (NYSE), CIK 1814287 — matches the break row. `data/baskets/ohlcv/ABX.parquet` spans
  2020-09-14→2026-08-21 (Abacus only, zero Barrick rows — verified), `GOLD.parquet` spans
  2014-03-17→ (A-Mark/Gold.com lineage — verified).
- **IBIT**: `SEC:US-XNAS-IBIT` RESOLVED, issuer `ISS:US-XNAS-IBIT` CIK 0001980994 legal_name
  "iShares Bitcoin Trust ETF" (evidence sec_company_tickers 2026-08-18). Directory row:
  `etf=True`. Membership source: `data/baskets/membership.json` basket `crypto_rails` member IBIT
  (added 2023-05-09, curated_added 2026-07-03). **Data OS's IBIT row is lawful — an ETF is a
  security; the defect is exclusively the graph's company-KIND node.**

## §2 CORRECTION MECHANISM (the freeze's central ruling)

**R-D2B3-1 — Node lifecycle lineage table.** Node retirement/correction is expressed in a NEW
sibling table in the same store, `data/theme_graph/node_lifecycle.parquet`, written via the
existing `store.append_rows` machinery with KEY `("node_id","computed_at")` and a
latest-by-computed_at read collapse — the exact key/collapse pattern capability and
identity_resolution already use. `nodes.parquet` stays write-once and is NEVER rewritten: the
original `co:us:GOLD` / `co:us:IBIT` rows remain bit-identical forever. Rationale (adjudicated
against the alternatives): (a) extending NODE_KEY with a time column would make every nightly
re-mint append a fresh canonical row — ~3,878 rows/night of bloat AND automatic resurrection of
any retirement on the next bake; (b) in-place status flips on the keep-first row are exactly the
history rewrite the commission forbids; (c) a lifecycle sibling table reuses the store's existing
append-only/latest-belief pattern, leaves every existing reader byte-stable by default, and makes
the correction itself an auditable, append-only record. Columns (exact set is the builder's to
finalize within this shape; the guard's schema must pin it in the same PR): `schema`
("gmi.node_lifecycle/v1"), `node_id`, `status` (target state, from the existing enum), `retire_date`,
`merged_into`, `reason` (closed enum: `identity_break` | `entity_type_conflict`), `evidence`
(verbatim pointer: breaks-registry key or conflicting node id + master security id), `ratified_by`,
`computed_at`, `engine_version`. Writes go through a lane-gated `store.write_node_lifecycle()`
sibling of the existing writers.

**R-D2B3-2 — Current-view projection.** `store.read_nodes` gains `current: bool = False`. Default
False returns the raw table (zero behavior change for every existing consumer). `current=True`
overlays the latest lifecycle row per node_id: a node whose latest lifecycle status is `retired`
(or `merged`) carries that status and its `retire_date` in the returned frame. The collapse is
latest `computed_at` per node_id, ties broken deterministically and never on a value (G0.11
discipline, same as :226-253). Every existing `read_nodes()`/direct-parquet consumer is enumerated
in §11 with an explicit, recorded flip/no-flip decision — no silent default changes.

**R-D2B3-3 — Edge corrections use the EXISTING edge lineage only.** Closing/annulling an edge =
appending a later-`belief_time` row for the same `edge_id` with the corrected interval and
`evidence_refs` naming the correction evidence. No edge row is ever rewritten or deleted;
`read_edges(latest_belief=False)` keeps the full history; nightly re-emission of the original row
stays a keep-first no-op. After D2B3, `_meta.json` `edges` > `edges_latest_belief` for the first
time — the builder must sweep tests/guards for any equality assumption and fix them in the same PR.

**R-D2B3-4 — Bake becomes conflict-aware and retirement-aware (resurrection-proofing).**
`materialize` gains two deterministic rules, both structural, neither name-based:
  (a) **Entity-kind conflict refusal**: when a company-suite membership source would mint a
  company node for a symbol that also exists as an `etf:<SYMBOL>` node in the same build, the
  company mint is REFUSED and a typed refusal receipt is emitted into the bake's `_meta.json`
  (e.g. `company_mint_refusals: [{symbol, suite, reason: "etf_conflict", conflicting_node}]`).
  The ETF node and its lawful TRACKS edges are unaffected. This is the same structural evidence
  D2A's rule 4 already uses (same-generation etf-kind node set) — no Data OS read, no name
  heuristics, no LLM.
  (b) **Retired-node re-mint refusal**: minting a node whose latest lifecycle status is
  retired/merged RAISES (fail-closed, loud). For GOLD/ABX this is defense-in-depth — the live
  epoch law already routes any new evidence to `#2` so the epoch-1 ids are structurally
  unmintable; for IBIT rule (a) is the primary fence and this is the backstop.

**R-D2B3-5 — One-shot curated correction, no new timer.** The corrections themselves (lifecycle
appends + edge-closure appends + their evidence rows) are performed ONCE by a curated correction
script (checked in under `scripts/`, breaks-registry-driven, no ticker literals in its logic),
run by the implementing session; the artifacts are committed in the same PR. The nightly bake
never re-runs corrections — it only respects them (R-D2B3-4). No new allocator, no new timer, no
new issuer namespace.

## §3 GOLD OUTCOME (bound to the ratified 2025-12-02 break row)

- Lifecycle append: `co:us:GOLD` → status=retired, `retire_date=2025-12-02` (verbatim
  `break_date` from the ratified row; **no other date may be invented** — see §9),
  reason=`identity_break`, evidence=`config/theme_graph_identity_breaks.yml` GOLD row,
  ratified_by carried over from that row.
- Edge correction: the stale `MEMBER_OF co:us:GOLD→basket:baskets:gold_miners` edge is closed by
  a later-belief row with `valid_to=2025-12-02` (truncation: the pre-break node's membership claim
  was true in the world and ENDS at the ratified break). Its original 2026-08-11 belief row
  remains queryable forever.
- `co:us:GOLD#2` is NOT pre-minted. The live epoch law mints it automatically if and when a
  current source presents symbol GOLD evidence; today none does (gold_miners lists B; Finviz
  lists neither). Pre-minting an evidence-less node would be exactly the hand-written-row act
  the house forbids. Acceptance covers the ROUTING law (any future GOLD evidence can only reach
  `#2`), which is provable by test without a production node.
- Barrick/B lineage: NOTHING may link `co:us:B` to `co:us:GOLD` (any epoch) — no edge, no
  lifecycle reference, no alias. Data OS refuses that continuity (`DEFERRED_IDENTITY_KEYS["B"]`);
  GMI preserves the typed uncertainty. The sidecar's DEFERRED_IDENTITY_EXCEPTION states for both
  symbols are the LAWFUL post-correction end-state and are not to be "fixed" (§7).

## §4 IBIT OUTCOME (structural entity-kind correction)

- Lifecycle append: `co:us:IBIT` → status=retired, `retire_date` = the correction date (there is
  no world-event break date; the company-plane interpretation was never true — the date records
  when the graph's active interpretation ended), reason=`entity_type_conflict`, evidence =
  `etf:IBIT` + `SEC:US-XNAS-IBIT` + directory `etf=True` (the same machine-visible receipts the
  D2A sidecar already emits).
- Edge correction: `MEMBER_OF co:us:IBIT→basket:baskets:crypto_rails` is ANNULLED — later-belief
  row with `valid_to = valid_from` (empty interval: the company-plane membership was never valid;
  distinct from GOLD's truncation, and the distinction is part of the law). The membership FACT
  is not lost: `etf:IBIT`'s TRACKS edges to crypto/crypto_rails remain untouched, and the source
  document itself is untouched.
- Forward path: bake rule R-D2B3-4(a) turns the still-present crypto_rails source row for IBIT
  into a typed refusal receipt every night instead of a company mint. The historical
  `co:us:IBIT` node row, its edge history, and all 10 historical ENTITY_TYPE_CONFLICT sidecar
  generations remain queryable forever — the conflict counter is NOT made to disappear by
  deletion (commission law).
- `etf:IBIT` and its lawful ETF relationships are preserved bit-identical.

## §5 ABX — THE GENERALITY CONTROL

The mechanism must be registry-driven with zero ticker special-casing (no GOLD/IBIT/ABX literals
in any correction/bake logic — literals may appear only in tests and in the curated evidence
fields). ABX proves generality on the "prior node ABSENT" shape:

- `co:us:ABX` does not exist → the correction script mints NOTHING for ABX (retirement of an
  absent node is a no-op, not an error, and never fabricates a prior node).
- The guard invariant (§6) must hold for ABX exactly as for GOLD: a ratified break whose prior
  node is absent passes; if ABX evidence ever appears in a source, the live epoch law routes it
  to `co:us:ABX#2` (already pinned by the identity tests).
- Tests must cover both shapes: prior-present (GOLD: retired required) and prior-absent (ABX:
  nothing minted, nothing breached), driven from the real registry file.

## §6 GUARD (make the ratified law load-bearing)

`scripts/check_theme_graph_contracts.py` gains, in the same PR as the mechanism:

- Schema + enum validation for `node_lifecycle.parquet` (closed `reason` enum; status from the
  existing enum; required evidence fields non-empty; fail-closed).
- **Break-retirement invariant**: for every ratified break row, if the `prior_node_retired_as`
  node EXISTS in nodes.parquet, its latest lifecycle status MUST be `retired` — a canonical prior
  node with a ratified break is a breach. (Absent prior node passes — ABX shape.)
- **Retired-consistency invariant**: a node whose latest lifecycle status is retired must not be
  the `src` of any latest-belief MEMBER_OF edge with an open interval (`valid_to` null) — a
  retired company with live memberships is a breach.
- Existing epoch law (:549-565) unchanged. Selftest fixtures extended for every new breach class.

## §7 D2A SIDECAR STANCE (frozen: UNCHANGED in D2B3)

`identity_resolution.derive_rows` keeps its population (every kind=="company" node from the raw
table, including retired ones) and its rules verbatim. Consequences, stated so nobody "fixes"
them: `co:us:GOLD` and `co:us:B` keep deriving DEFERRED_IDENTITY_EXCEPTION (Data OS still
registers both symbols; GMI must not manufacture what Data OS refuses); `co:us:IBIT` keeps
deriving ENTITY_TYPE_CONFLICT (the historical conflict stays machine-visible);
`identity_resolution_state_counts` in `_meta.json` remain {DEFERRED: 2, ENTITY_TYPE_CONFLICT: 1}
on the us plane. "No active company-plane interpretation" is proven by node lifecycle status +
closed latest-belief edges + the bake refusal receipt — NOT by zeroing sidecar counters. This
also keeps the D2B2-US nightly proof numbers (1210/25, target_n 1236) completely undisturbed.
Any future re-scoping of the derivation population or the admission target set to
active-only nodes is a SEPARATE wave's diff with its own accounting contract.

## §8 DATA OS NON-INTERFERENCE (binding)

Read-only joins only. NOTHING in `data/reference/`, `scripts/build_security_master.py`
(including `load_gmi_us_seeds`, `DEFERRED_IDENTITY_KEYS`, `DISCLOSED_IDENTITY_EXCEPTIONS`), the
receipt schema, or any Data OS artifact may change. The B/GOLD identity exceptions are Data OS's
typed uncertainty; their resolution is a future registered identity-scoped DOS amendment that is
NOT D2B3. The existence of the ratified graph break is NOT permission to override Data OS
(commission law, restated as a test-guarded invariant: the correction script must not import or
write anything under `data/reference/`).

## §9 DATES LAW

Every date in a correction row comes verbatim from its evidence: `retire_date`/`valid_to` for a
reuse break = the ratified row's `break_date`; the IBIT annulment's `valid_to` = the edge's own
`valid_from` (empty interval); `computed_at`/`belief_time` on every appended row = the actual
correction execution time, NEVER backdated (belief clocks record when the graph's belief changed;
validity clocks record what the evidence says was true in the world). Any other date is invented
evidence and a breach.

## §10 HOSTILE TEST MATRIX (the implementing PR is not done unless each is a test)

1. Original `co:us:GOLD` / `co:us:IBIT` node rows bit-identical after correction (write-once
   proof; silent-history-edit attack).
2. Gold_miners current view (`read_edges(latest_belief=True)`) contains `co:us:B`'s edge and NOT
   an open `co:us:GOLD` edge; `latest_belief=False` still shows the original open row (history
   queryable).
3. Nightly re-bake after correction (run `build_theme_graph` twice): no resurrection — retired
   statuses stand, closed/annulled edges stay closed (keep-first no-op proof), no new
   `co:us:IBIT` company mint, refusal receipt present both runs (idempotent).
4. Epoch routing: a synthetic membership doc naming GOLD (market us) mints ONLY `co:us:GOLD#2`;
   same for ABX→`co:us:ABX#2` (registry-driven, no literals in the code path).
5. ABX absent-prior shape: correction script + guard pass with nothing minted and nothing
   breached.
6. Two ratified epochs never merge: no edge, alias, or lifecycle row links `co:us:B` to any
   GOLD-symbol node (Barrick/Gold.com merge attack).
7. Epoch backdating attack: a lifecycle row whose `computed_at` predates the ratified row's
   ratification, or a correction date not derived per §9, is rejected by the guard.
8. ETF-plane preservation: `etf:IBIT` node + both TRACKS edges bit-identical.
9. Sidecar laundering attack: sidecar generation counts monotone; historical
   ENTITY_TYPE_CONFLICT/DEFERRED rows untouched; `derive_rows` output for the five target keys
   unchanged pre/post correction.
10. Blast radius: total diff to `nodes.parquet` = 0 rows; `edges.parquet` = exactly the
    correction appends (+2 rows); `node_lifecycle.parquet` = exactly 2 rows; every other node
    (3,876) and edge (8,290) untouched.
11. Guard breach classes each fire on a synthetic fixture (canonical-prior-with-break;
    retired-with-open-member-edge; invalid reason enum; missing evidence).
12. `read_nodes(current=False)` byte-stable for all existing consumers; `current=True` overlay
    correct on a mixed fixture.
13. `_meta.json` `edges` (8,294) vs `edges_latest_belief` (8,292) divergence tolerated by every
    test/guard (first production use of the closure lineage).
14. Lane law: lifecycle/edge-correction writes refused outside the sanctioned lanes
    (`lane_ok`), same as every other store writer.

## §11 OWNED FILES + CONSUMER DECISION TABLE

Implementation owns: `engine/theme_graph/store.py` (lifecycle table, writer, `read_nodes(current=)`),
`engine/theme_graph/materialize.py` (R-D2B3-4 rules + refusal receipt), the one-shot correction
script (new, under `scripts/`), `scripts/check_theme_graph_contracts.py` (§6),
`scripts/build_theme_graph.py` (receipt plumbing only if needed), `data/theme_graph/
{node_lifecycle.parquet, edges.parquet(+2), evidence.parquet(+correction evidence), _meta.json}`,
tests (`tests/test_theme_graph_*`). Every existing nodes reader gets a recorded decision in the
implementing PR: `materialize` known_ids (current=True — must not resolve variants onto retired
ids), `check_theme_graph_contracts` (audits raw AND current), `theme_coverage_gaps.py:239`
(current=True — retired nodes are not coverage gaps), `identity_resolution.derive_rows` (raw —
frozen §7), `build_security_master.load_gmi_us_seeds` (raw, UNCHANGED — frozen §7/§8), probation
reader (raw; validation-only). A consumer not on this list found during implementation gets its
decision added to the PR body, not silently defaulted.

## §12 ACCEPTANCE (restating the commission, bound to mechanics)

Current company view cannot merge Barrick-era GOLD with Gold.com (matrix 2, 6); ratified epoch
rule is load-bearing (mint routing test 4 + guard invariant §6 — a canonical prior with a
ratified break now BREACHES CI); ABX proves generality (5); IBIT no longer contributes as an
active company (retired status + annulled edge + nightly refusal receipt; matrix 3, 8); no
unrelated node id changes (10); historical edges queryable (2); corrected current edges cite
correction lineage evidence (§3/§4 evidence law); D2A projection and strict graph guards pass
with sidecar counts UNCHANGED (§7, matrix 9); D2B2-US current-resolution counts do not regress
(§7/§8 — untouched by construction).

## §13 OPERATOR MODEL + COMPLETION

One Sonnet `builder` implements this contract after the §0 gate opens; a fresh Opus `reviewer`
attacks the implementation against §10 explicitly including: silent-history edits, epoch
backdating, Barrick/Gold.com merging, ETF-to-company leakage, sidecar laundering, accidental
broad graph rewrites. Merge = **BUILT_NOT_PROVEN**. DONE only when a natural production GMI cycle
runs with the correction live and shows: retired statuses standing, gold_miners current view
without the GOLD edge, the IBIT refusal receipt in that night's `_meta.json`, and green guards —
measured on the real nightly artifacts, not a local run.

## §14 NON-GOALS

Canada (`co:ca:ABX.TO` explicitly untouched); any Data OS security-master change (§8); resolving
the B/GOLD continuity (future registered DOS amendment); pre-minting `co:us:GOLD#2`/`co:us:ABX#2`;
re-scoping the D2A derivation population or the GMI-US admission target set to active-only nodes;
sidecar schema/state changes; Prophet admission/rank/buyability, Radar, Fusion, Earnings,
ThemeState, ontology, PIT membership history, rights policy; D2C/D2D/D2E/D3/D5.

---

# AMENDMENT §1 (2026-08-21, pre-implementation design review — Opus reviewer verdict FAIL, all findings adjudicated and adopted; re-frozen by the commissioning seat)

The reviewer ran the real bake and falsified three frozen claims. Every ruling below SUPERSEDES the
conflicting §2-§12 text.

**R-A1 (supersedes R-D2B3-3's no-op claim + re-shapes R-D2B3-4(a); reviewer B1/M4).**
`belief_time` is the RUN DATE (`materialize.build(... belief_time or utc_today())`,
materialize.py:943, stamped :338) — a re-emission on a later day is a NEW `(edge_id, belief_time)`
key, so write-side keep-first protects nothing across days, and `changed_edges`
(materialize.py:1055-1069) re-appends any row differing on `MATERIAL_EDGE_FIELDS` (whose first
member is `valid_to`). The store test cited in §1 passes only because its SOURCE document carries
the removal. **A curated correction therefore survives only if the bake stops COMPUTING the
corrected row.** R-D2B3-4(a) is re-frozen as a POST-PASS structural filter: after all suites and
local planes are computed (the etf node set is only complete then — single-pass ordering is luck,
not design), remove every company node whose symbol exists in the final same-build etf node symbol
set AND every edge whose `src` is a removed node, emitting one typed refusal receipt per
suppression into the bake receipt. Mandatory new tests: (i) the annulled IBIT edge stays closed
across two simulated consecutive-day bakes (belief_time d, d+1); (ii) on the day after the
correction, `changed_edges` proposes NO row for any corrected edge_id.

**R-A2 (rewrites §7's population claim; reviewer B2).** `derive_rows` runs over THIS BUILD'S
computed node list (materialize.py:918-923), never `nodes.parquet`. Store fossils gain sidecar
rows only through wave-driven DIRECT rebakes that derive from the committed store table (the
2026-08-18→08-21 GOLD generations — including the D2B2 wave's own rebakes — which resolves the
reviewer's open attribution gap: store-derived rebakes include fossils; natural computed
generations do not). `co:us:GOLD` is ALREADY absent from the natural computed population (measured:
3,877 nodes), so the next natural generation reads us-scope DEFERRED_IDENTITY_EXCEPTION = 1 (B
only) regardless of D2B3 — `{DEFERRED: 2}` was never freezable. Frozen post-correction natural
expectation (us scope, newest generation): computed us company rows 1,236 (1,238 − GOLD already
absent − IBIT suppressed) = RESOLVED 1,210 + NOT_IN_MASTER 25 + DEFERRED_IDENTITY_EXCEPTION 1 (B);
ENTITY_TYPE_CONFLICT 0 with the typed refusal receipt present.

**R-A3 (adjudicates the §4/§7/§10.9 contradiction; reviewer B3).** The LIVE conflict counter
lawfully drops to 0 after the correction: the cause is corrected and the typed refusal receipt is
its machine-visible replacement. What the commission's "do not delete historical evidence" clause
protects is HISTORY: every prior ENTITY_TYPE_CONFLICT/DEFERRED sidecar generation remains
append-only and queryable, and no sidecar row is ever deleted or rewritten. §10.9 is restated:
sidecar HISTORY byte-untouched; the first post-correction generation contains no `co:us:IBIT` row
and the refusal receipt is present. §12's "sidecar counts UNCHANGED" is struck in favor of the
R-A2 expectation table.

**R-A4 (makes matrix 7 implementable; reviewer B4).** The breaks registry gains an ADDITIVE
`ratified_at: "2026-08-14"` field on both existing rows in the implementing PR — the value is the
ratification date already documented in each row's `ratified_by` prose and cross-verifiable
against the merge date of PR #5613; both loaders read named keys only and ignore unknown fields
(identity.py:76-89; check_theme_graph_contracts.py:544-548), so this is an additive metadata
disclosure, not a semantic edit of a ratified break. Matrix 7 is restated against `ratified_at`:
a lifecycle row whose `computed_at` predates its cited break row's `ratified_at` is a guard
breach. New break rows MUST carry `ratified_at`.

**R-A5 (fixes the §11 consumer table; reviewer M1).** The "materialize known_ids (current=True)"
entry is DELETED — materialize is pure (reads no store; materialize.py:955), and
`resolve_symbol_variant`'s `known_ids` is this build's in-memory dict. Added consumers with
recorded decisions: `scripts/probe_theme_exposure_axes.py:415-416` (direct nodes.parquet read →
adopts the current-view overlay, excluding retired nodes from symbol maps);
`scripts/build_theme_graph.py:156` (`counts.nodes` → stays RAW total store rows; the receipt may
additionally disclose lifecycle-aware counts but the raw count's meaning is unchanged).

**R-A6 (defuses the RAISE; reviewer M2).** R-D2B3-4(b) emits a typed refusal receipt exactly like
(a) — it NEVER raises: a raise inside the nightly bake is an outage weapon, not a fence.
Materialize purity is preserved: lifecycle state is read by `scripts/build_theme_graph.py` (the
impure orchestrator) and passed into `build()` as an input.

**R-A7 (fixes the §0 gate recipe; reviewer M3).** `_meta.json` and the sidecar are not
co-advanced. Gate (b) reads `data/theme_graph/identity_resolution.parquet` directly: newest
`computed_at` generation filtered `market_scope=='us'`, expecting the PRE-correction natural shape
RESOLVED 1,210 / NOT_IN_MASTER 25 / DEFERRED_IDENTITY_EXCEPTION 1 / ENTITY_TYPE_CONFLICT 1
(1,237 rows — GOLD already absent per R-A2), from a generation whose consumed master
`master_generated_at` ≥ 2026-08-22. The D2B2-US natural-proof grader must likewise expect
DEFERRED 1, not 2 — GOLD's disappearance from the natural sidecar is R-A2 population mechanics,
NOT a regression.

**R-A8 (minor corrections; reviewer minors).** §10.10 wording: 0 node rows added/changed; ALL
3,878 node rows untouched. §10.13: under R-A1's suppression the post-correction `_meta` counts are
edges 8,294 / edges_latest_belief 8,292 and STABLE (the bake computes no row for either corrected
edge afterward). §1's derive_rows filter cite corrected to identity_resolution.py:536-537. §0's
"last written by the D2B2 merge" refers to the last COMMIT touching the sidecar; the 08-21 03:47Z
natural bake ran and appended zero edge rows (`_meta.json rows_appended.edges: 0`).
