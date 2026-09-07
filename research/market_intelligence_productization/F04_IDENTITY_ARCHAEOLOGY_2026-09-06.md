# F04 Identity Archaeology - no canonical ETF identity owner exists (2026-09-06)

In plain words: we went looking for the one place in this codebase that
decides "this is fund X" for an ETF, so later work can attach new rows to a
stable id instead of guessing. We did not find one: the nearest candidate
only mints a graph-node label, and the standing identity gate already
refuses to treat that as security identity. We name that nearest candidate,
record the gap as an explicit open row, and separately confirm an older
question (`MO-DELTA-005`, about Decision Zones) that had already been
answered but was marked stale in the ledger. Both are settled here; they
are different capabilities, closed in the same pass.

## 1. Search surface

| # | Candidate | Anchor | What it actually owns | Verdict |
|---|---|---|---|---|
| 1 | `etf_node_id` | `engine/theme_graph/identity.py:234-237` | Mints `etf:<SYMBOL>`. Docstring: "ETFs are market-agnostic in the id - the proxy relationship to a basket carries the market". | **GRAPH-NODE SLUG MINTER ONLY - NOT SECURITY IDENTITY** (closure map §2.4:135,151) |
| 2 | Sole producer call site | `engine/theme_graph/materialize.py:440-452` | TRACKS edge minting: `e_id = identity.etf_node_id(etf)` per basket `etf_proxy`. | Sole producer |
| 3 | K1 evidence validator | `lib/evidence_foundation.py:309-310` | `if value.startswith("etf:"): return theme_identity.etf_node_id(value.removeprefix("etf:")) == value` - the K1 EvidenceRef layer **validates against candidate 1 rather than minting its own**. | Decisive corroboration |
| 4 | `identity_resolution` | `engine/theme_graph/identity_resolution.py:13-14`, `:270-277`, `:430-441` | "ONE ROW PER COMPANY-KIND NODE ... `etf`/other kinds carry no rows in v1." ETF nodes appear only as a company-identity **conflict source** (rule 4). | Explicitly NOT an ETF identity owner |
| 5 | `engine/stock_identity/` (plane, authority, census, fingerprint, dossier, episodes, hygiene, partition, pilot, state) | `engine/stock_identity/plane.py:5-14` (three price planes); `engine/stock_identity/authority.py:17-27` (all-false authority block) | `grep -rni etf engine/stock_identity/ --include=*.py` returns **0 hits**. Company/stock-scoped only. | **REFUTES** the F04 closure map's "Stock Identity/Data OS security identity" owner route |
| 6 | `fund_registry` | `engine/etf_registry.py:40-74`, config at `config.yml:2033` | Roster + typing: 106 `etf_holdings.universe` funds, 108 `registry` rows, 2 `holdings.watchlist`; returns `{type, sponsor, theme}` keyed on the **bare ticker**; fail-soft `DEFAULT_TYPE = "thematic_passive"` (`:30`). No id minted, no epoch, no authority stamp. | **CANONICAL ETF ROSTER/TYPING OWNER - a different role, NOT identity** |
| 7 | Flow-board consumers: `engine/etf_board.py`, `engine/etf_consensus.py`, `engine/etf_flows.py`, `engine/etf_perfund.py`, `engine/etf_pulse.py`, `engine/etf_board_ledger.py`, `engine/holdings_signals.py:917,1080,1157` | as listed | All key on the bare fund ticker; none mints an identity. | Consumers only |
| 8 | Published surface | `docs/site_semantics/etfs.md:1-22` | Display-only tier; snapshots at `data/etf_holdings/<FUND>/<date>.parquet`; keyed by fund ticker. | Consumer, display-only |
| 9 | Every other `etf:`-literal site | `engine/theme_graph/identity_resolution.py:433,439`; `engine/theme_graph/materialize.py:1020`; `scripts/correct_gmi_identity_lineage.py:155`; `scripts/check_theme_graph_contracts.py:1510,1524` | Conflict receipts and test fixtures. | Not minters - confirms candidate 1 is the **sole** minter |
| 10 | `lib/dataos/identity.py` (Data OS security-identity spine - the other half of the closure map's composite route) | `lib/dataos/identity.py:1-32` | Docstring: "a symbol is NEVER an identity (Data OS §D2)"; shapes `ISS:<inception listing key>`, `SEC:<inception listing key>`, bare `<CC>-<MIC>-<CODE>` listing, venue+time-scoped Symbol. `grep -rniI "etf" lib/dataos/ --include="*.py"` returns **0 hits** (run 2026-09-06). | **REFUTES** the Data OS half of the composite owner route; reconciled against candidate 1 in section 2 |

## 2. The answer: no canonical owner

**NO canonical ETF security-identity owner exists today.** The 2026-09-04
F04 closure map already ruled this out and this record upholds that ruling
rather than reopening it:
`MARKET_ONTOLOGY_F04_EXACT_CAPABILITY_CLOSURE_MAP_2026-09-04.md:135` -
"A graph node slug is not sufficient canonical listing/security identity" -
and `:151` - "No `etf:<ticker>` or `co:us:<ticker>` label alone is treated
as security identity."

`engine/theme_graph/identity.py::etf_node_id` (`:234-237`) mints the
graph-node slug `etf:<SYMBOL>` **only** - a graph-side id for TRACKS-edge
construction. Verified producer/consumer call sites are graph-side only -
`engine/theme_graph/materialize.py:445` (TRACKS-edge minting) and
`lib/evidence_foundation.py:310` (K1 validation, round-tripping through the
same minter rather than minting its own) - both keyed on basket
`etf_proxy` symbols. `etf_node_id` is not identity under the standing gate
("identity only via Stock Identity + Data OS + Supabase auth"); every
statement in this record about `etf_node_id` is scoped to that graph-side
id and none claims coverage over the flow-board/holdings estate.

**The join contract `etf:<SYMBOL>` <-> `data/etf_holdings/<FUND>/` does not
exist.** This absence is recorded as an explicit OPEN row, not a silent
gap: the owning programs are F04 identity (Stock Identity/Data OS security
master and instrument-type fields, closure map §2.4 steps 1-4) and Data OS
(the inception-listing-key discipline that a join contract would have to
extend to ETFs).

Two roles are named separately and must not be conflated: the graph-node
slug minter (candidate 1, `etf_node_id`) and **roster/typing** (candidate 6,
`engine/etf_registry.py::fund_registry`) - neither is security identity.

The 2026-09-04 F04 closure map printed a COMPOSITE owner route: "Stock
Identity/Data OS security identity + GMI ETF nodes/TRACKS + lawful holdings
owner" (line 40). Both named halves of that route were searched, not just
one: `engine/stock_identity/` (`grep -rni etf engine/stock_identity/
--include=*.py` = 0 hits - candidate 5) and `lib/dataos/identity.py` (`grep
-rniI "etf" lib/dataos/ --include="*.py"` = 0 hits - candidate 10). Both
are absent of ETF code, so the composite route is refuted on both halves -
consistent with there being no current owner, not evidence for one.

**Why the shape mismatch matters.** `lib/dataos/identity.py`'s §D2 doctrine
issues `ISS:<inception listing key>` / `SEC:<inception listing key>` ids and
states a symbol is *never* an identity, precisely so a rename (its own
motivating case: MMC->MRSH) cannot silently drop history. `etf_node_id`
mints the opposite shape - a bare, unepoched `etf:<SYMBOL>` - and would
suffer the identical failure mode Data OS was built to prevent if a fund
ticker were ever reused after a closure. This is exactly the failure
closure map §2.4 refuses to license, which is why `etf_node_id` is named
here only as a graph-node slug minter, never as canonical identity. The
missing inception-key/epoch discipline stays an explicit, disclosed null in
section 3; closing it - and building any holdings-to-identity join
contract - is a future hardening pass under F04 identity/Data OS, not this
archaeology pass.

## 3. What we do not know

- **No epoch discipline for ETF ids.** Company ids carry a ratified epoch
  from `config/theme_graph_identity_breaks.yml` (`engine/theme_graph/identity.py:11-16`);
  `etf_node_id` carries none. If a fund closes and someone else later uses
  the same ticker, our records would treat them as one fund. We have not
  fixed that and we are not pretending it is fixed.
- **The two owners cover different populations, and the store-side overlap
  has not been counted in this pass.** `etf_node_id` mints only for tickers
  reachable as a basket `etf_proxy` (`materialize.py:441`); the roster
  carries 106 universe funds plus 2 watchlist funds. The count of
  `etf`-kind nodes actually built in the graph store is **NOT MEASURED** -
  no cause is claimed for that gap beyond that it has not been done. We do
  not know how many of the 106 funds on the flow board also have a graph
  identity. We did not count it, and we are not guessing.
  **What we DID count, source-side:** `engine/theme_graph/materialize.py:166`
  documents `etf_proxy` declared on 76 baskets (75 as a bare string, 1 as the
  two-item list on `defensives`). A literal-value grep
  (`grep -rhoE "etf_proxy['\"]?\s*[:=]\s*['\"][A-Z0-9.]+['\"]" engine/ scripts/`)
  matches only **29 of those 76 declaration sites** - all in
  `scripts/seed_china_baskets.py`, `scripts/seed_canada_baskets.py` and
  `scripts/seed_hk_baskets.py` - resolving to **25 distinct symbols**. This
  is a floor bound biased toward the CN/HK/CA basket families, not a
  resolution of all 76 declarations: the pattern is blind to any
  declaration assigned from a variable rather than a literal string/list,
  which is how the entire 11-basket US-sector family is written
  (`scripts/seed_us_sector_baskets.py:78`, `"etf_proxy": etf,` for XLK, XLF,
  XLV, XLY, XLC, XLI, XLP, XLE, XLU, XLRE, XLB) and how at least three other
  baskets declare a `None` proxy (`scripts/seed_intl_baskets.py:277`,
  `scripts/seed_china_ths_baskets.py:474,522`). The 25-symbol figure is
  printed with this bias disclosed; it answers "what a literal-value grep
  finds," not "how many symbols the 76 declarations name," and it is NOT a
  substitute for the store-side overlap count above, which stays NOT
  MEASURED. Defensible denominators that MAY be printed: 106 config
  `universe` funds, 108 `registry` rows, 2 `holdings.watchlist` funds - all
  read from `config.yml`, not from `data/`.
- **No holdings-to-identity join contract exists.** `docs/site_semantics/etfs.md`
  keys on the fund ticker; nothing maps `etf:<SYMBOL>` to
  `data/etf_holdings/<FUND>/`.

## 4. No new store

No new identity store is proposed. ETF treatment is a row type over the existing baseline.

## 5. MO-DELTA-005 - ALIAS (confirmed, not re-opened)

The F00C ledger row (`MARKET_ONTOLOGY_F00C_GRANULAR_CLOSURE_LEDGER_2026-09-02.csv:41`)
says the archaeology is "still unperformed". **That row is stale.**
`MARKET_ONTOLOGY_F04_EXACT_CAPABILITY_CLOSURE_MAP_2026-09-04.md:37` and
section 2.2 already adjudicate `MO-DELTA-005` ("Decision Zones - downstream
research/action surface from macro catalyst") as `ALIAS_OR_PROJECTION`:
"not a new canonical intelligence owner or separate database ... an
alias/projection for the downstream research-action composition inside
Ontology Explorer and Market OS", with the explicit non-goal "Do not create
`decision_zones.json`, a Decision Zones engine, a second task/alert queue or
a model-generated action ranker."

**Disposition recorded: ALIAS. Target = the Ontology Explorer / Market OS
composition over existing path, dislocation, evidence and (later)
opportunity owners, per that memo section 2.2.** This memo cites that
adjudication and does not re-open it. The alias target inherits
`MO-DELTA-005`'s `research_only` authority ceiling - **no competitor
direction, confidence, expected-impact or priced-% fields** attach to it
(Sol amendment, ledger row 41 `authority_ceiling`).

Honesty note: `MO-DELTA-005` is a **Decision Zones** row, not an ETF row.
This memo settles both rows in one pass, but they are different
capabilities - nothing here implies Decision Zones is an ETF concern.

## 6. MO-DELTA-009 - half open

Ledger acceptance (`:43`) is two-part: "ETF identity owner named (or
ratified absent) **and** ETF event rows render over the existing
baseline." Part 1 closes here as **RATIFIED ABSENT** (section 2 above): no
canonical ETF security-identity owner exists, upholding closure map §2.4
rather than contradicting it. Part 2 is deliberately **not shipped**: its
baseline is the MO-PAID-016/017 substrate and PR `#6896` is editing it now.
Verified 2026-09-06 on this checkout: `engine/chronicle/impact.py` does not
exist (`ls: engine/chronicle/impact.py: No such file or directory`).

**Resumption condition:** the ETF-event-row half of `MO-DELTA-009` resumes
when `PR #6896` is squash-merged to `origin/main` and
`engine/chronicle/impact.py` is present on main with a stable public
signature; the row type is then folded over that baseline as a row type
only - no new store.

## 7. Authority

This memo ranks nothing, sizes nothing, gates nothing, originates no signal
and escalates nothing. It records a naming at the `research_only` (for the
`MO-DELTA-005` alias) and `context_only` (for `MO-DELTA-009`'s identity
half) ceilings the two ledger rows carry.

## 8. Record

See [`../../agentos/decisions/DEC-F04-CANONICAL-ETF-IDENTITY-OWNER-2026-09-06.md`](../../agentos/decisions/DEC-F04-CANONICAL-ETF-IDENTITY-OWNER-2026-09-06.md)
for the frozen decision record.
