# K3-D — Economic Propagation hypothesis contract freeze

**Operation key:** `alpha-k3d-economic-propagation-20260826-sol-001`
**Wave:** K3-D under `WS:ALPHA-INTELLIGENCE-INTEGRATION` (runtime authority NONE, permanently)
**Pickup Macro SHA:** `13b9660f3188ed9915e750515c1502cfd33c9bf1` (`origin/main`, 2026-08-27)
**Carrier:** one implementation branch `claude/k3d-economic-propagation`; no other K3-D carrier exists (open-PR census run at pickup: none matched)
**Authority of this document:** NONE. Dated freeze/adoption receipt. Canonical ownership stays in `config/mastermind_programs.yml`, WS records and DNR.

---

## 0. Acceptance gates (§0 per spawn-handoff law)

This wave is not done unless:

1. The record/schema ownership ruling below is receipted (prior-art census of `earnings_readthrough_hypothesis/v1`).
2. The four binding kills are carried **in-body, const** in every record, with the corrected SR3 summary, plus a hook-level generator refusal closing participation/breadth-as-target-generator (c0 §4.2 rider repair).
3. Laundering attacks red in tests: theme→supplier, sympathy→economic path, co-movement→SUPPLIES, generic agreement→customer, ownership→customer, protocol peer→commercial peer, participation→generator.
4. Real current-owner read-only proof exists: at least one typed abstention composed from canonical data with exact owner refs (§5). No fabricated Graph-1 row.
5. Zero authority: all axes const-false; no scalar propagation strength/score/rank/grade anywhere; `economic_share` const-null.
6. No new graph/store/grader/ranker; the module is a pure in-memory validator/composer.
7. Focused suite + hosted CI/fences green on the exact head; independent adversarial review performed and repaired on the same carrier.

## 1. Ownership ruling (record/schema archaeology)

**Question:** does current Earnings Intelligence (or anyone) already own `earnings_readthrough_hypothesis/v1` or an equivalent join record?

**Census (2026-08-27, `origin/main` @ `13b9660f3188`):**

- `grep -rn "earnings_readthrough" contracts/ engine/ lib/ config/ scripts/` → **zero hits**. The name exists only in research architecture docs (`research/EARNINGS_NEURAL_GRAPH_READTHROUGH_AND_CATALYST_ARCHITECTURE_2026-08-16.md` §2.6) and the D0 census rows that call it "architecture only / not built".
- `config/mastermind_programs.yml` read-through mentions are the known group-grain wording (`group-reads` owns participation/sympathy/read-through **context**; the `earnings-intelligence` "read-through context" clause is the stale wording already prescribed for repair by `DEC:EARNINGS-INTELLIGENCE-PROGRAM-OWNERSHIP` — cited, not performed here).
- No open PR or branch implements the record (PR census at pickup).

**Ruling:** the general Economic Propagation record class is **unowned**. Per the commission's branch: freeze one canonical general name under the existing Alpha program. The frozen name is
`economic_propagation.propagation_hypothesis/v1`
(`contracts/economic_propagation/propagation_hypothesis.v1.schema.json` + `generator_registry.v1.json`, compiled by `lib/economic_propagation.py`).

**No semantic twin:** `earnings_readthrough_hypothesis/v1` is hereby recorded as the **earnings-grain species** of this general record class. If Earnings Intelligence later builds it, it must compose **through** this contract (specializing `source_event.event_class=earnings_event`), not fork a parallel schema. Economic propagation remains a **record class, not a program key** (c0 §4.2 ruling 3): no `economic-propagation` registry entry is minted, and this contract is a consumer/honesty layer over Graph 1/2/3 owners, never a fourth spine.

## 2. Three-graph law as implemented

- Every evidence leg and every generator admission carries a `graph` tag (`graph_1|graph_2|graph_3`) and a `construct` from a closed vocabulary; `generator_registry.v1.json construct_vocabulary` fixes each construct's graph. A Graph-1 leg carrying a Graph-2/3 construct is refused by name (`K3D_R032`) — there is no `RELATED` flattening and no way to express one.
- Graph-1 roles are a closed enum; role-specific roles (customer/supplier/partner/…) require `role_evidence_class ∈ {disclosed_role_specific, strongly_evidenced_role}` (`K3D_R031`). `disclosed_agreement_role_unknown` (the GR linked-outsider construct; 8-K counterparties are financing-agent-dominated — receipted in §5) can only carry `role_unknown`, so a generic agreement can never become a customer/supplier claim. Ownership counts only as `ownership_cashflow` on `ownership_cashflow_change` evidence.
- Summary states are **compiler-derived only** (`K3D_R051/R052/R053` recompute-and-compare): `graph_1 ∈ {supported, insufficient_role, rights_blocked_only, unknown_unavailable}`; absence is `unknown_unavailable`, never a false relationship, never zero.
- A mechanism may be hypothesized **only** when derived Graph-1 is `supported` (`K3D_R042`; composer refuses earlier). Its prediction is an **operating** direction over a closed operating-metric enum; trade/price vocabulary in mechanism prose is refused (`K3D_R041`).
- Typed abstention is a first-class, complete record: `hypothesis_state=abstained` + closed `abstention.reasons`, with alternatives, falsifiers and expiry still mandatory. Falsifier language stays research-tier (never user-facing, operator 2026-07-27).

## 3. DNR / rider compliance

`binding_kills` is a **const 4-item field of every record** (schema-enforced, test-pinned):

- `DNR:KILL-PSS-SR2-PEER-DIFFUSION` — peer adjacency is not transfer; the exact diffusion construction stays closed.
- `DNR:KILL-PSS-SR3-PARTICIPATION` — **corrected summary carried in the registry** (c0 rider repair): the participation target-generator construction was KILLED, not demoted to display; any future peer-state species must measure an orthogonal source. Enforcement: `gen_peer_participation_breadth` is an `admits_target:false` refusal row; its appearance in `generator_admissions` is refused (`K3D_R021`, composer raise).
- `DNR:KILL-CN-SUPPLY-ABSORPTION` — absorption cannot be reconstituted from broad participation/co-movement; participation/co-movement constructs are Graph-3-locked in the vocabulary.
- `DNR:KILL-CAUSAL-DAG-ALPHA` — no discovered-graph causal alpha: no score/rank/grade/weight field exists; a forbidden-key scan (`K3D_R071`) refuses smuggled scalars; all authority axes are const-false; `economic_share` is const-null until its canonical owner mints a formula (GMI W2 inheritance).

Also inherited: Data OS/Stock Identity exact identity is mandatory — the c0 identity clause (~25% GMI company-node resolution; production census in §5 shows 12,393 `NOT_IN_MASTER` rows on the live resolution surface) is honored by a hard abstention gate: any `resolution_state ≠ RESOLVED` forces a typed abstention **before any semantic inference**; legs/admissions on an unresolved target are refused (`K3D_R010/R011`, composer raise). Grading routes through `engine/grading.py` + existing forward ledgers only — this wave builds **no** grade ledger ("its PIT grade" wording from D0 is struck per c0 §4.2 ruling 4).

## 4. Adoption map (read/compose vs must-not-own)

| Surface | Status in K3-D |
|---|---|
| `gmi.identity_resolution/v1` (`data/theme_graph/identity_resolution.parquet`) | READ — identity verdicts carried verbatim (owner vocabulary incl. `NOT_IN_MASTER`, `UNSUPPORTED_MARKET`, `DEFERRED_IDENTITY_EXCEPTION`, `ENTITY_TYPE_CONFLICT` widened into the contract enum from production observation) |
| `theme_graph.edges.v1` MEMBER_OF/EXPRESSES | READ as Graph-2 vocabulary; `era=reconstruction` never used as historically-known membership |
| `group_linked_outsiders.v1` / `data/edgar/material_8k_events.parquet` counterparty | READ as Graph-1 **candidate** (`disclosed_agreement_role_unknown` only) |
| `group_pulse.v1` / sympathy / residual organs | READ as Graph-3 context (constructs locked to graph_3) |
| GovRev award facts, Bio trial peer sets, TXI chain state | READ-eligible via registry generators; no owner file touched this wave |
| Demand Desk `ai_datacenter` scored theses | **OUT OF SCOPE** (named exclusion; the estate's one live scored propagation path is not absorbed) |
| K2-C, K3-E, K3E Expectation↔Market Dynamics, K5/OpportunityCase, Prophet/Fusion | **NOT ABSORBED** (explicit confirmation per stop condition) |
| Owner modules (`engine/theme_graph`, `engine/group_*`, `engine/biocatalyst`, GovRev, Data OS, `engine/grading.py`) | UNTOUCHED — zero writes; read/factor territory only |

New surfaces owned by this wave: `contracts/economic_propagation/**`, `lib/economic_propagation.py`, `tests/test_economic_propagation_hypothesis_contract.py`, `tests/fixtures/economic_propagation/**`, `research/economic_propagation/K3D_*` + `k3d_real_proof_records/**`.

## 5. Real current-owner read-only proof

Reads executed against `origin/main` blobs (`git show origin/main:<path>`; sparse worktree, no live VPS probe). Receipts:

- `data/edgar/material_8k_events.parquet`: 51,017 rows; **1,966 counterparty rows** (`counterparty_ok=True`). The recent population is financing agents/trustees on items 1.01/2.03 debt filings (Wells Fargo Bank, U.S. Bank Trust, BNY Mellon, Morgan Stanley Senior Funding) — confirming the c0 finding that this surface cannot self-upgrade to supply-chain relations.
- `data/theme_graph/identity_resolution.parquet`: 39,273 rows; states `RESOLVED` 23,587 / `NOT_IN_MASTER` 12,393 / `UNSUPPORTED_MARKET` 3,262 / `DEFERRED_IDENTITY_EXCEPTION` 20 / `ENTITY_TYPE_CONFLICT` 11.
- `data/theme_graph/edges.parquet`: 12,172 rows, types MEMBER_OF/EXPRESSES/TRACKS only — **zero Graph-1-type rows have ever been written**, re-confirming D0/c0 past its pin.

**Proof record 1 — honest no-Graph-1 abstention (the flagship refusal):**
`k3d_real_proof_records/real_abstention_tsn_adm_no_graph1.json` (`record_id eph1:00af09cb1ce455b9`, `content_sha256 0a1db4f3…`). Source event: real TSN 8-K `0001140361-26-034195` (filed 2026-08-24, items 1.01/2.03/8.01, `_first_seen 2026-08-25T00:02:11Z`). Target `co:us:ADM`, RESOLVED to `ISS:US-XNYS-ADM` (join `master_inception_exact`, asof 2026-08-18). Admitted by `gen_theme_membership` on the real shared edges `member_of:co:us:{TSN,ADM}->ltheme:finviz:agricultureprocessing@2026-06-27` (era=reconstruction, belief 2026-08-15). Result: `graph_states = {graph_1: unknown_unavailable, graph_2: present, graph_3: absent}`, `hypothesis_state=abstained`, reasons `[no_graph1_evidence]`, mechanism abstained-null. A naive system reads "same agriculture theme + an event" as read-through; the contract emits a complete research object that refuses the economic claim. Zero validator findings.

**Proof record 2 — identity abstention before inference:**
`k3d_real_proof_records/real_abstention_tsn_counterparty_unresolved.json` (`record_id eph1:e9bad2ac4cbed771`). Target = the filing's actual counterparty string "Bank of New York Mellon Trust Company": **no row** on the canonical resolution surface → `UNRESOLVED` → typed abstention `[unresolved_identity]` with zero evidence legs. The tempting fuzzy alias-map to ticker BK is exactly the guess the contract forbids (a financing trustee is not a commercial counterparty anyway — recorded as the alternative explanation). Zero validator findings.

**Full positive composition:** honestly **unavailable on current real data** — the estate has no live role-specific firm-level Graph-1 row anywhere (receipts above). Per the commission ("do not widen scope to manufacture a full positive example"), the positive path is proven by the synthetic golden fixture in the test suite (`disclosed_customer_supplier` + `disclosed_role_specific` → `supported_hypothesis` with operating-direction mechanism), and the data gap is left visible: the first real positive requires GMI W4 / GR3b role-specific extraction / GovRev CATALYST_OF to land a role-specific owner row.

## 6. Capability state (no production inflation)

`BUILT / CONTRACT-FROZEN / REAL-ABSTENTION-PROVEN` on the carrier head. **Not** PROVEN_LIVE, not deployed, not a product surface, not wired to any consumer. Merge/CI green is not production proof (this is a research/display contract wave; no deployment is owed or authorized). No nightly, no store, no UI, no Prophet/Fusion/K5 wiring exists or is permitted by this contract.
