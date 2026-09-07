---
schema: agentos.decision.v1
key: F04-CANONICAL-ETF-IDENTITY-OWNER-2026-09-06
question: >
  Does macro have a canonical ETF identity owner that later ETF rows may join
  against, and does MO-DELTA-005 resolve to an alias target or to a ratified
  NOT_BUILT?
answer: >
  NO canonical ETF security-identity owner exists today. The 2026-09-04 F04
  closure map already ruled this out, and this record upholds that ruling
  rather than reopening it: MARKET_ONTOLOGY_F04_EXACT_CAPABILITY_CLOSURE_MAP_2026-09-04.md:135,
  "A graph node slug is not sufficient canonical listing/security identity",
  and :151, "No `etf:<ticker>` or `co:us:<ticker>` label alone is treated as
  security identity". engine/theme_graph/identity.py::etf_node_id
  (:234-237) mints the graph-node slug `etf:<SYMBOL>` only - the sole such
  minter in this repo, validated (not independently re-minted) by the K1
  evidence foundation (lib/evidence_foundation.py:309-310) - and is not
  identity under the standing gate ("identity only via Stock Identity + Data
  OS + Supabase auth"). Verified producer/consumer call sites are graph-side
  only - engine/theme_graph/materialize.py:445 and
  lib/evidence_foundation.py:310 - minting/validating for basket `etf_proxy`
  symbols; every statement here about etf_node_id is scoped to that
  graph-side id, none claims coverage over the flow-board/holdings estate.
  The join contract `etf:<SYMBOL>` <-> `data/etf_holdings/<FUND>/` does not
  exist and is recorded as an explicit OPEN row (owning programs: F04
  identity - Stock Identity/Data OS security master and instrument-type
  fields, closure map §2.4 steps 1-4 - and Data OS - inception-listing-key
  discipline). engine/etf_registry.py::fund_registry (:40-74) is named
  separately as the ETF ROSTER/TYPING owner - a different role, not
  identity. The composite owner route printed in the 2026-09-04 F04 closure
  map ("Stock Identity/Data OS security identity + GMI ETF nodes/TRACKS +
  lawful holdings owner") is refuted on BOTH halves after searching both:
  engine/stock_identity/ (zero ETF references, company/stock-scoped) and
  lib/dataos/identity.py (zero ETF references; its Data OS §D2 doctrine
  issues Issuer/Security ids off an inception listing key and treats a bare
  symbol as never an identity - the opposite shape from etf_node_id's bare,
  unepoched `etf:<SYMBOL>`). No new identity store is proposed; this record
  settles a NAMING question, not an architecture change. MO-DELTA-005
  resolves to ALIAS - already adjudicated 2026-09-04 as ALIAS_OR_PROJECTION
  onto the Ontology Explorer / Market OS composition - and the alias target
  inherits MO-DELTA-005's research_only ceiling. MO-DELTA-009 resolves to
  RATIFIED ABSENT on its identity half (the OPEN row above); its
  ETF-event-row half stays open, blocked on the MO-PAID-016/017 substrate.
rationale: >
  This record upholds, not revisits, the 2026-09-04 F04 closure map §2.4
  ruling: a graph node slug is not sufficient canonical security identity
  (:135), and no `etf:<ticker>` label alone is treated as identity (:151).
  Naming etf_node_id canonical would have repeated exactly the naming
  closure map §2.4 refuses; recording the join contract ABSENT with the
  enumerated search surface, as an explicit OPEN row, is the licensed exit
  (closure map acceptance line, :151) and the disposition closure map §2.4
  step 7 prescribes when no current owner can support the row. etf_node_id
  is still the only construction site of an `etf:` id in engine/, scripts/
  and lib/ - every other occurrence is a conflict receipt or a test fixture
  - which is why it is named here as the graph-node slug minter, not
  because that shape qualifies as security identity. Naming the roster
  instead would have been wrong for a different reason: fund_registry keys
  on a bare ticker, mints nothing, and fails soft to a default type, so
  joins against it would silently absorb unknown funds. Naming Stock
  Identity or Data OS as the owner would have been wrong on evidence:
  neither module contains any ETF code (grep -rni etf
  engine/stock_identity/ = 0 hits; grep -rniI "etf" lib/dataos/
  --include="*.py" = 0 hits). Confidence stays medium rather than high
  because two nulls remain printed rather than resolved: ETF ids carry no
  epoch discipline (company ids do), and the STORE-SIDE overlap between the
  id namespace and the 106-fund flow roster has not been counted in this
  pass - no cause is claimed for that gap beyond that it has not been done.
  The SOURCE-SIDE figure (25 distinct symbols) is a floor bound, not a
  resolution: a literal-value grep over the 76 declared `etf_proxy` sites
  matches only 29 of them, and the entire US-sector family (11 baskets)
  assigns from a variable and is structurally invisible to that pattern
  (scripts/seed_us_sector_baskets.py:78), so the figure is printed with
  that bias disclosed rather than offered as a count of all 76.
alternatives:
  - option: Name engine/theme_graph/identity.py::etf_node_id as the canonical
      ETF identity owner (this record's own first-draft naming, R1)
    why_not: >
      Refuted by the ratified 2026-09-04 F04 closure map §2.4: "A graph node
      slug is not sufficient canonical listing/security identity" (:135) and
      "No `etf:<ticker>` ... label alone is treated as security identity"
      (:151). etf_node_id mints exactly that bare, unepoched `etf:<SYMBOL>`
      label - naming it canonical would contradict a standing ruling this
      record has no authority to overturn. lib/evidence_foundation.py:309-310
      binding ETF refs to etf_node_id is real and disclosed, but it is a
      graph-side validation contract, not evidence the bound id is security
      identity.
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
  - option: Name lib/dataos/identity.py (the Data OS security-identity half of
      the composite "Stock Identity/Data OS security identity" route)
    why_not: >
      `grep -rniI "etf" lib/dataos/ --include="*.py"` returns zero hits; the
      module's own §D2 doctrine (lib/dataos/identity.py:1) issues Issuer/Security
      ids off an inception listing key and states a symbol is never an identity -
      the opposite shape from etf_node_id's bare, unepoched `etf:<SYMBOL>`. Both
      halves of the composite route were searched and both are absent of ETF
      code; the mismatch in shape is disclosed, not silently reconciled.
  - option: Propose a new canonical ETF identity store spanning graph + flow board
    why_not: >
      MO-DELTA-009's bounded child says "no new store", and a competing identity
      store is an architecture change requiring its own adjudication. The coverage
      gap between the two owners is recorded as a printed null instead.
evidence:
  - "research/market_intelligence_productization/MARKET_ONTOLOGY_F04_EXACT_CAPABILITY_CLOSURE_MAP_2026-09-04.md:135 - 'A graph node slug is not sufficient canonical listing/security identity' - and :151 - 'No `etf:<ticker>` or `co:us:<ticker>` label alone is treated as security identity'. Ratified 2026-09-04, upheld (not reopened) by this record."
  - "engine/theme_graph/identity.py:234-237 - etf_node_id mints `etf:<SYMBOL>`; market-agnostic by docstring; a graph-node slug only, per the closure map row above."
  - "engine/theme_graph/materialize.py:440-452 - the sole producer call site (TRACKS edges from basket etf_proxy)."
  - "lib/evidence_foundation.py:309-310 - K1 EvidenceRef validates `etf:` refs by round-tripping through theme_identity.etf_node_id (graph-side validation, not an independent identity mint)."
  - "engine/theme_graph/identity_resolution.py:13-14 - 'ONE ROW PER COMPANY-KIND NODE ... etf/other kinds carry no rows in v1'; :270-277,:430-441 ETF nodes are only a company-identity conflict source."
  - "engine/stock_identity/plane.py:5-14 and engine/stock_identity/authority.py:17-27; grep -rni etf engine/stock_identity/ = 0 hits (run 2026-09-06)."
  - "lib/dataos/identity.py:1-32 - Data OS §D2 identity spine; grep -rniI \"etf\" lib/dataos/ --include=\"*.py\" = 0 hits (run 2026-09-06)."
  - "engine/theme_graph/materialize.py:166-170 - `etf_proxy` is declared on 76 baskets (75 bare string, 1 two-item list on `defensives`); a literal-value grep (`grep -rhoE \"etf_proxy['\"]?\\s*[:=]\\s*['\"][A-Z0-9.]+['\"]\" engine/ scripts/`) matches only 29 of those 76 sites, resolving to 25 distinct symbols across scripts/seed_china_baskets.py, scripts/seed_canada_baskets.py, scripts/seed_hk_baskets.py only (run 2026-09-06) - a floor bound biased toward CN/HK/CA; scripts/seed_us_sector_baskets.py:78 assigns `\"etf_proxy\": etf` from a variable (11 baskets: XLK, XLF, XLV, XLY, XLC, XLI, XLP, XLE, XLU, XLRE, XLB) and is structurally invisible to the pattern."
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
canonical ETF identity owner (or ratify it absent), and (2) render ETF
event rows over the existing baseline. Part 1 closes here as **RATIFIED
ABSENT**: no canonical ETF security-identity owner exists today, upholding
the 2026-09-04 closure map §2.4 ruling that a graph node slug is not
security identity. `engine/theme_graph/identity.py::etf_node_id` mints the
graph-node slug `etf:<SYMBOL>` only and is not identity under the standing
gate; the join contract `etf:<SYMBOL>` <-> `data/etf_holdings/<FUND>/` does
not exist and is recorded as an explicit OPEN row (owning programs: F04
identity, Data OS). Part 2 stays open by design.

## What we do not know

- **No epoch discipline for ETF ids.** Company ids carry a ratified epoch
  from `config/theme_graph_identity_breaks.yml`; `etf_node_id` carries none.
  If a fund closes and someone else later uses the same ticker, our records
  would treat them as one fund. We have not fixed that and we are not
  pretending it is fixed.
- **The two owners cover different populations, and the store-side
  overlap has not been counted in this pass.** `etf_node_id` mints only for
  tickers reachable as a basket `etf_proxy`; the roster carries 106
  universe funds plus 2 watchlist funds. The count of `etf`-kind nodes
  actually built in the graph store is **NOT MEASURED** - no cause is
  claimed for that gap beyond that it has not been done. We do not know
  how many of the 106 funds on the flow board also have a graph identity.
  We did not count it, and we are not guessing. What we DID count,
  source-side: `etf_proxy` is declared on 76 baskets (75 as a bare string,
  1 as the two-item list on `defensives`); a literal-value grep matches
  only 29 of those 76 declaration sites (scripts/seed_china_baskets.py,
  scripts/seed_canada_baskets.py, scripts/seed_hk_baskets.py), resolving to
  25 distinct symbols. That figure is a floor bound biased toward the
  CN/HK/CA basket families: the entire 11-basket US-sector family assigns
  its `etf_proxy` from a variable (`scripts/seed_us_sector_baskets.py:78`)
  and is structurally invisible to the pattern. It is printed with this
  bias disclosed; it is NOT a substitute for the store-side overlap count,
  which stays NOT MEASURED. Defensible denominators that may be printed:
  106 config `universe` funds, 108 `registry` rows, 2 `holdings.watchlist`
  funds - all read from `config.yml`, not from `data/`.
- **No holdings-to-identity join contract exists.** `docs/site_semantics/etfs.md`
  keys on the fund ticker; nothing maps `etf:<SYMBOL>` to
  `data/etf_holdings/<FUND>/`. This absence is recorded as an explicit OPEN
  row, owning programs named: F04 identity (Stock Identity/Data OS
  security master and instrument-type fields) and Data OS (the
  inception-listing-key discipline a join contract would have to extend to
  ETFs).

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
