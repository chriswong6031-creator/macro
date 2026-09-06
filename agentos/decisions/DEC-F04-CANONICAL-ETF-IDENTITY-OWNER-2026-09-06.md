---
schema: agentos.decision.v1
key: F04-CANONICAL-ETF-IDENTITY-OWNER-2026-09-06
question: >
  Does macro have a canonical ETF identity owner that later ETF rows may join
  against, and does MO-DELTA-005 resolve to an alias target or to a ratified
  NOT_BUILT?
answer: >
  Yes, an owner exists and is named: engine/theme_graph/identity.py::etf_node_id
  (:234-237) is the sole minter of the `etf:<SYMBOL>` id in this repo, and the K1
  evidence foundation already validates ETF refs against it
  (lib/evidence_foundation.py:309-310). Later ETF rows join on that id and on
  nothing else. engine/etf_registry.py::fund_registry (:40-74) is named separately
  as the ETF ROSTER/TYPING owner - a different role, not identity.
  engine/stock_identity/ is recorded as NOT an ETF owner (zero ETF references),
  which refutes the "Stock Identity/Data OS security identity" owner route printed
  in the 2026-09-04 F04 closure map. No new identity store is proposed; ETF
  treatment is a row type over the existing baseline. MO-DELTA-005 resolves to
  ALIAS - already adjudicated 2026-09-04 as ALIAS_OR_PROJECTION onto the Ontology
  Explorer / Market OS composition - and the alias target inherits MO-DELTA-005's
  research_only ceiling. MO-DELTA-009 closes only its identity half; its
  ETF-event-row half stays open, blocked on the MO-PAID-016/017 substrate.
rationale: >
  The naming is not "nearest module": etf_node_id is the only construction site of
  an `etf:` id in engine/, scripts/ and lib/ - every other occurrence is a conflict
  receipt or a test fixture - and an independent layer (K1 EvidenceRef) already
  treats it as the authority by round-tripping refs through it rather than minting
  its own. Naming the roster instead would have been wrong: fund_registry keys on a
  bare ticker, mints nothing, and fails soft to a default type, so joins against it
  would silently absorb unknown funds. Naming Stock Identity would have been wrong
  on evidence: it contains no ETF code at all. Two disclosed nulls keep confidence
  at medium rather than high: ETF ids carry no epoch discipline (company ids do),
  and the overlap between the id namespace and the 106-fund flow roster was not
  counted because data/ is absent in the sparse worktree.
alternatives:
  - option: Record ABSENT (no canonical ETF identity owner)
    why_not: >
      Defensible before this pass, but refuted by lib/evidence_foundation.py:309-310,
      where an independent contract layer already binds ETF refs to etf_node_id. An
      ABSENT record would have left that live binding undocumented.
  - option: Name engine/etf_registry.py::fund_registry as the identity owner
    why_not: >
      It is a roster/typing reader keyed on a bare ticker with a fail-soft default
      (engine/etf_registry.py:30,63-67); it mints no id and carries no epoch or
      authority stamp. Joining later rows against it would absorb unknown funds
      silently.
  - option: Name engine/stock_identity/ (the security-identity plane)
    why_not: >
      `grep -rni etf engine/stock_identity/ --include=*.py` returns zero hits; the
      plane is company/stock-scoped over three price planes
      (engine/stock_identity/plane.py:5-14).
  - option: Propose a new canonical ETF identity store spanning graph + flow board
    why_not: >
      MO-DELTA-009's bounded child says "no new store", and a competing identity
      store is an architecture change requiring its own adjudication. The coverage
      gap between the two owners is recorded as a printed null instead.
evidence:
  - "engine/theme_graph/identity.py:234-237 - etf_node_id mints `etf:<SYMBOL>`; market-agnostic by docstring."
  - "engine/theme_graph/materialize.py:440-452 - the sole producer call site (TRACKS edges from basket etf_proxy)."
  - "lib/evidence_foundation.py:309-310 - K1 EvidenceRef validates `etf:` refs by round-tripping through theme_identity.etf_node_id."
  - "engine/theme_graph/identity_resolution.py:13-14 - 'ONE ROW PER COMPANY-KIND NODE ... etf/other kinds carry no rows in v1'; :270-277,:430-441 ETF nodes are only a company-identity conflict source."
  - "engine/stock_identity/plane.py:5-14 and engine/stock_identity/authority.py:17-27; grep -rni etf engine/stock_identity/ = 0 hits (run 2026-09-06)."
  - "engine/etf_registry.py:29-30,40-74 and config.yml:2033 - roster/typing owner; 106 universe funds, 108 registry rows, 2 holdings.watchlist funds."
  - "docs/site_semantics/etfs.md:1-22 - published ETF surface is display-only and keyed on the fund ticker."
  - "research/market_intelligence_productization/MARKET_ONTOLOGY_F04_EXACT_CAPABILITY_CLOSURE_MAP_2026-09-04.md:37 and section 2.2 - MO-DELTA-005 already adjudicated ALIAS_OR_PROJECTION."
  - "research/market_intelligence_productization/MARKET_ONTOLOGY_F00C_GRANULAR_CLOSURE_LEDGER_2026-09-02.csv:41 (MO-DELTA-005) and :43 (MO-DELTA-009) - the two rows this record answers."
  - "`ls engine/chronicle/impact.py` -> No such file or directory on this checkout 2026-09-06: the MO-PAID-016/017 substrate is mid-flight under PR #6896."
affects:
  - "WS:MARKET-OS"
  - "WS:GMI-THEME-GRAPH"
  - "research/market_intelligence_productization/**"
  - "engine/theme_graph/identity.py"
  - "engine/etf_registry.py"
confidence: medium
reversibility: easy
decided_by: "session 7cd4fae1-1ed9-41c2-adb4-1e5c6b0fbc5b (Meta-CEO B, F04 lane)"
decided_at: 2026-09-06
---

## Summary

This record settles two ledger rows in one archaeology pass: `MO-DELTA-005` and
`MO-DELTA-009`.

`MO-DELTA-005` is a **Decision Zones** row, not an ETF row. It resolves to
**ALIAS**: it was already adjudicated on 2026-09-04 as `ALIAS_OR_PROJECTION`
onto the Ontology Explorer / Market OS composition over existing path,
dislocation, evidence and (later) opportunity owners. This record does not
re-open that adjudication - it cites it and confirms it. The alias target
inherits `MO-DELTA-005`'s `research_only` authority ceiling: no competitor
direction, confidence, expected-impact or priced-% fields may attach to it.
The Decision Zones question and the ETF identity question below are two
different capabilities settled in the same pass; nothing here implies
Decision Zones is an ETF concern.

`MO-DELTA-009` is an ETF row. Its acceptance is two-part: (1) name the
canonical ETF identity owner, and (2) render ETF event rows over the
existing baseline. Part 1 closes with this record:
`engine/theme_graph/identity.py::etf_node_id` is the canonical ETF identity
owner. Part 2 stays open by design.

## What we do not know

- **No epoch discipline for ETF ids.** Company ids carry a ratified epoch
  from `config/theme_graph_identity_breaks.yml`; `etf_node_id` carries none.
  If a fund closes and someone else later uses the same ticker, our records
  would treat them as one fund. We have not fixed that and we are not
  pretending it is fixed.
- **The two owners cover different populations, and we did not count the
  overlap.** `etf_node_id` mints only for tickers reachable as a basket
  `etf_proxy`; the roster carries 106 universe funds plus 2 watchlist funds.
  The count of `etf`-kind nodes in the store is a build artifact under
  `data/`, absent in this sparse worktree, so the overlap is **NOT
  MEASURED**. We do not know how many of the 106 funds on the flow board
  also have a graph identity. We did not count it, and we are not guessing.
  Defensible denominators that may be printed: 106 config `universe` funds,
  108 `registry` rows, 2 `holdings.watchlist` funds - all read from
  `config.yml`, not from `data/`.
- **No holdings-to-identity join contract exists.** `docs/site_semantics/etfs.md`
  keys on the fund ticker; nothing maps `etf:<SYMBOL>` to
  `data/etf_holdings/<FUND>/`.

## No new store

No new identity store is proposed. ETF treatment is a row type over the
existing baseline.

## Resumption condition

The ETF-event-row half of `MO-DELTA-009` resumes when PR #6896 is
squash-merged to `origin/main` and `engine/chronicle/impact.py` is present
on main with a stable public signature; the row type is then folded over
that baseline as a row type only - no new store.

## Record

See `research/market_intelligence_productization/F04_IDENTITY_ARCHAEOLOGY_2026-09-06.md`
for the full archaeology (search surface table, naming rationale, and
plain-word nulls).
