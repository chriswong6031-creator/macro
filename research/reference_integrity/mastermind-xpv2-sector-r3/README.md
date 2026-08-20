# XPV2-SC-R3A — Sector Central (US) binding pack

Program: `WS:INSTITUTIONAL-PRODUCT-EXPERIENCE-V2` · Wave: `XPV2-SC-R3A`
Status as of 2026-08-20: **archaeology + adjudication + binding pack
complete.** R3 visual design is NOT started — `R3B_HANDOFF_DRAFT.md` is a
draft commission for that next wave, marked DO NOT START pending
commissioning-session review.

## Why this pack exists

Four critics BLOCKED the R2 Sector Central mockup for inventing and mixing
authority and for losing capabilities present in production. This pack makes
it impossible for the R3 designer to guess what any number, action, row,
route, clock, access behavior, or failure state means: every claim in it
cites production code (`file:line`) or a committed payload, never inference,
and every gap the archaeology found is carried forward as a GAP rather than
filled by guessing.

## Inputs (read-only — do not edit)

- `archaeology/lane_A_action_overview.md` — Overview / Action-board authority
  contract (six lane keys, five columns, premium split, Bottoming Watch).
- `archaeology/lane_B_routing_capability.md` — SI Workspace V2 router: six
  views, 21 `LEGACY_ANCHORS`, `#theme-*`/`#read-*` families, scroll mechanics.
- `archaeology/lane_C_map_moving_money.md` — Map/Moving/Money producer
  binding matrix source, including the A2 handoff-deviation finding.
- `archaeology/lane_D_explore_history.md` — Explore: table/chart/Time
  Machine/Forming Narratives/Track Record, access trace end-to-end.
- `archaeology/lane_E_confluence.md` — four-universe Confluence archaeology
  (S&P/Baskets/Nasdaq/Russell), row-identity detector, tab-order refutation.
- `archaeology/lane_F_state_matrix.md` — ten-state census (loading, zero,
  empty, stale, partial, error, 401/403, correction, overflow, cardinality).
- `ADJUDICATIONS.md` — the frozen Fable rulings (A1–A10 + capability ledger
  priors) resolving every conflict the six dossiers surfaced. Binding on
  every deliverable below; a builder may not soften, reinterpret, or extend
  it.

## The A2 handoff-deviation note (read before trusting anything about Moving)

**The commission's original premise — that `si_handoff.json` binds the
Moving view — is REFUTED by code (`ADJUDICATIONS.md` §A2, lane C §2a).**
`si_handoff.json` has exactly one writer (`scripts/build_baskets.py:590-597`)
and one reader (`scripts/build_sector_central.py:379-384`), both server-side
at build time. Its four fields (`theme_context`, `factor_season`, `flow`,
`basket_member_syms`) feed:

- `theme_context` / `factor_season` → **Overview hero only**.
- `flow.cluster.regime` → **Money's `#si-read-money` strip only** (one
  field, baked into a `data-regime` attribute).
- `basket_member_syms` → **Explore's member-symbol registry only**.
- `generated_utc` → footer only.

**Moving does NOT bind `si_handoff.json` at all.** Grepping Moving's three
mounted JS files (`rotation_events.js`, `subsector_rotation.js`,
`desk_watch.js`) for `si_handoff` returns zero matches. Moving's canonical
binding is **five nightly artifacts**: `marketdata/rotation_events.json`,
`marketdata/sector_fragmentation.json`, `marketdata/subsector_rotation.json`,
`basketdata/oracle_turn_desk.json`, `basketdata/oracle_tape_onset.json` — all
five are in `fixture/`. Every deliverable in this pack (the binding matrix,
the design brief, the fixture set, the attack tests) records THIS binding,
not the original premise. If the commissioning session's mental model of
"Moving reads the handoff" predates this pack, that model is stale as of
2026-08-20 — trust the binding matrix, not the premise.

## Deliverable pointer map

| # | File | What it is |
|---|---|---|
| 1 | `capability_disposition_ledger.md` | Every production capability from the six dossiers, one disposition each (90 RETAIN, 2 BLOCKED_DATA, 0 REMOVE/RELOCATE), cited to its dossier section |
| 2 | `producer_binding_matrix.md` | One consolidated table per view: field → producer → path/key → authority → transform → clock → access → destination → state/null behavior |
| 3 | `fixture/` | Byte-for-byte frozen copies of every producer artifact this page reads, captured commit `4c55fe433490adfd75fd901ef25f5793db2202db` (2026-08-20), with `PROVENANCE.md` and SHA-256 `receipts.json` |
| 4 | `routing_contract.md` | Six views, verbatim 21-entry `LEGACY_ANCHORS`, `#theme-*`/`#read-*` families, unknown/empty-hash fallback, instant-scroll mechanics, per-view destination inventory, three recorded-not-repaired seams (A7) |
| 5 | `access_hydration_contract.md` | The one premium wall, full-count-vs-preview-row mechanics, the authenticated hydrate flow, the 401/403/offline collapse, nightly-sole-advancer rule for Track Record |
| 6 | `R3_DESIGN_BRIEF.md` | Bounded brief: page answer job, context/action dual-read law, view-by-view capability law, mobile reduction, required accessible equivalents, forbidden local recomputation, required evidence matrix |
| 7 | `README.md` | This file |
| 8 | `R3B_HANDOFF_DRAFT.md` | **DRAFT — DO NOT START.** Next-wave commission draft for the actual R3 visual design, pending commissioning-session review |
| 9 | `tests/test_xpv2_sector_r3_fixture.py` | Attack-test suite asserting ONLY against the frozen fixture and code constants (never live `site/`/`data/`), per `ADJUDICATIONS.md` §A10 |

## Authority precedence (unchanged from the archaeology)

Production producers/payloads > production behavior > R2 review bundle >
doctrine. The rejected R2 candidate HTML is never source authority — it was
consulted by the archaeology only to know what to verify, never as truth on
its own.

## What is explicitly NOT in this wave

Per `ADJUDICATIONS.md`: nothing is REMOVE or RELOCATE. The recorded defects
(A3 Map reco/context conflation, A6 Overview stale-guard fail-open, A7
routing seams) are flagged and filed separately — repairing them is a
different, not-yet-commissioned wave. This pack also makes no production
code changes: it is research + a test suite only.
