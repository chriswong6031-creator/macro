# D0 — Open questions

**SHA:** `3d12412e561ef77c0a9618c9d9b18871d7344209`.  
**Rule:** if a question is a true canonical-owner conflict, stop rather than mint a duplicate. This file names the conflicts. It does not resolve them.

---

## Blocking (must be a DEC before any build)

### Q1. Who owns Economic Propagation?

There is no program key. Candidates that already occupy the space:

| Candidate | What they already own | Why they cannot silently absorb EP |
|---|---|---|
| `gmi-theme-graph` | reserved Graph-1 edge types; W4 planned | W3B ThemeState is merge-order blocked; W4 inputs (GR3, GovRev catalyst) are empty/identity |
| `group-reads` | group-grain sympathy + 8-K outsiders | refuses CS roles; no issuer mechanism object |
| `earnings-intelligence` | event/claim truth; architecture of the hypothesis object | E2 is workspace render; registry `owns` “read-through context” **conflicts** with DEC |
| `government-revenue-foresight` | identity graph; D5/D10 spec | must not become a second theme/identity/earnings plane (`WS:DEFENSE-PROCUREMENT-V3` do_not_redo) |
| `causal-hypothesis-factory` | idea immune system | `DNR:KILL-CAUSAL-DAG-ALPHA`; program-not-lobe |
| `neural-web` | bus | must not originate edges |

**Recommended default (not decided):** EP is a **record class** (`read-through hypothesis` + PIT grade) that **joins** existing graphs. Owner is a later DEC. Do not mint `economic-propagation` in `mastermind_programs.yml` from this census.

### Q2. Heal the EI vs GR “read-through” wording

`DEC:EARNINGS-INTELLIGENCE-PROGRAM-OWNERSHIP` vs `earnings-intelligence.owns: “…and read-through context”`.

Until a registry PR expands `owns`/`does_not_own`, any EP builder can honestly cite **both** and ship a duplicate.

### Q3. ThemeState merge order

`WS:GMI-THEME-GRAPH` TRANSMISSION wave waits on a ruling with Prophet V4 D-lane (`research/prophet_v4/WAVE_GRAPH_AND_MERGE_ORDER.md`). `#5894` is the open identity bridge.

Starting GMI W4 `SUPPLIES`/`ENABLES` from this lane would jump that ruling.

---

## Non-blocking but load-bearing

### Q4. Is Evidence Mesh a missing name or a missing system?

Zero hits in Macro + Mastermind under `evidence_mesh` / `Evidence Mesh`. Either it never landed, or it lives under another title (CHF lab? EI claim graph? NW evidence attention?).

**Do not create Evidence Mesh** until a session finds the other title or a DEC asks for it.

### Q5. When may GMI emit `SUPPLIES` / `ENABLES` / `BOTTLENECK_OF`?

Contract allows the types. W1b does not emit them. Planned sources:

- GR3b 8-K names — currently 0 counterparties; even then role is unknown
- XBRL fingerprints — foresight legs, not firm pairs
- GovRev `CATALYST_OF` — award facts, not supplier BOM

**Question:** is an undirected `supply_agreement` allowed as `SUPPLIES` with `role=unknown`, or is that the GR collapse?

**Recommended default:** no GMI Graph-1 write until role is evidenced. Store the GR edge as Graph-1-**candidate** only.

### Q6. Demand Desk scored theses

`engine/demand_chain.py` `ai_datacenter` emits scored ledger theses. Housing is display-only.

**Question:** is that already a stealth Economic Propagation scored path? If EP is display/context, this chain is either (a) out of scope or (b) a rights/authority leak to disclose in the DEC.

### Q7. GR3b vs GMI W4 vs Defense D5/D10 vs Bio partnerships

Four ramps, one temptation to build a fifth store. Who sequences them?

**Recommended default:** GR3b (unblock names) → GMI W4 typed edges from those names + XBRL → Defense D5/D10 industrial nodes → Bio reviewed partnerships. EP consumes; does not sequence by writing a new parquet.

### Q8. Clinical peer transfer is empty

In-repo CLIN hops are licensee (SMMT) or no-transfer (XLV→CN pharma) or own-name (ALNY/VKTX/HIMS). D0A forbids auto competitor cohorts.

**Question:** is “clinical event → peers” even an EP v1 family, or is it Bio Cycle / BCI (`#5821`) only?

### Q9. Production numbers this session could not see

Sparse omit of `data/`:

- theme-graph row counts and whether any reserved edge type has a row
- whether counterparties populated after 2026-08-08
- GovRev IDV/subaward live proof vs `BUILT_NOT_PROVEN`
- Bio ontology instance beyond the fixture

A later session with `python3 scripts/worktree_sparse.py add data` can close these without a design change.

### Q10. Stale `gmi-theme-graph` registry text

`implementation: []` and “runtime roots are absent at the audited baseline” are false as of W3A #5718. Same class of drift as Q2. Not this PR (generated map / registry regenerate is out of scope).

### Q11. CHF lobe-charter contradiction

Nine raw lobe-charter rows still name CHF as owner; the program is not a lobe. Named in `mastermind_programs.yml`. Do not resolve by making EP a lobe.

### Q12. `#5424` defense20-v1

Open. Not live. `DNR:LAW-REVIEWED-MANIFEST-CENSUS`. EP must pin `defense19-v1` until that PR merges.

---

## Explicitly out of scope (do not turn into work)

- Graph rewrite
- Alpha score / Prophet member / gate / size
- Inventing 40 `VERIFIED_CASE` primaries
- Inferring causality from co-movement
- A second Stock Identity, theme, earnings, recipient, or synapse plane
- LLM-originated edges or confidence (`DNR:KILL-LLM-CONFIDENCE`, NW A7)
- Starting Defense D2–D10 or GMI W4 from this census

---

## Suggested next command for a cold session

```text
# 1. Fast-forward the local root, then open this folder
git -C /Users/chriswong/Documents/Cluade/macro-main fetch origin
git -C /Users/chriswong/Documents/Cluade/macro-main merge --ff-only origin/main
# 2. Read these seven files, then DEC Q1/Q2 before any engine work
# 3. Optional measurement only:
python3 scripts/worktree_sparse.py add data
git show HEAD:data/theme_graph/_meta.json
# inspect edges.parquet type value_counts — do not write
```

No Agent OS workstream was minted. Minting `WS-ECONOMIC-PROPAGATION` would look like an owner. That is Q1.
