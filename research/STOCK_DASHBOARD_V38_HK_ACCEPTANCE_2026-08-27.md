# Stock Dashboard V3.8 — HK acceptance record (PROVEN_LIVE 2026-08-27)

Carrier: `stock-dashboard-v38-hk-ca-fable-20260826-sol-001` (V38-R1) · WS:PROPHET-HK-CA-REVAMP
Authority: `research/STOCK_DASHBOARD_V38_ACTION_LEADERSHIP_ARCHITECTURE.md` (frozen, PR #6456)
+ `DEC:V38-ACTION-IS-NOT-LEADERSHIP`. Canonical law: **ACTION TIMING ≠ TREND LEADERSHIP**.

Bootstrap: protected Skillpack `Mastermind@e4e44867ace335ac9208a3990a10c163e199492d`
(`mastermind.sol_skillpack.v1`, 1.0.0, bootstrap-major 1). Pickup base:
macro `main@854c2764e8756c8ebc6640796bf98e724e2479b7`. Collision census at pickup:
zero open PRs touching either composer, zero `v38` branches — single carrier confirmed.

## Implementation identity

- PR **#6515**, branch `claude/v38-r1-hk-action-leadership`.
- Heads: `da456970f9de` (initial) → **`cd6c4657bc16`** (post-review repairs; the reviewed and merged head).
- Squash-merge: **`5dad2bd413268ece0ac2c49e645142b2d449e57f`** (2026-08-27 ~05:57Z; head re-read immediately pre-merge).
- Changed-file census: `site/hk-stock-v36.js`, `tests/test_hk_v37_composer.py` — **only**. No engine/template/data/loader write; `dashboard-icons.js` untouched (no re-stamp owed; `?v=20260825` token unchanged).
- CI: ci.yml run **33043046945** SUCCESS on `cd6c4657bc16` (12 packs + ci-plan + contract-delta). Only red: `ci-authority/codex/merge-queue-pilot`, non-binding (red on merged #6507/#6502 too).

## What shipped (capability delta)

Before: the V3.7 page carried group action only inside Expand Leadership; Leadership joined
an unlabeled RS rank to action stance (`01 · Reduce/Avoid` confusion); Canada-class traversal
rank synthesis existed for unranked HK sectors; the BOARD count label was ambiguous.

After: an entitled user sees the owner-native **What to Act On Now** map AT REST above
Prophet (4 exact `anv2` lanes, ≤3 rows per lane before View all, ~240px collapsed, per-row
group-research route `sectors/<id>.html`) and, separately below Prophet, **Leadership &
Rotation** with the explicit basis `Relative strength vs HSI / 相对恒生指数`, rows reading
`RS #N` from the owner's Sector Rotation rank only (no owner rank → `—`, and all rank
language hides if the rank owner is absent), action stance as an independent field, and
the count column labelled `Prophet/候选` rendered only where board rows publish canonical
sector membership (missing ≠ zero; known-zero gets the quiet §10 state + research route).
The Leading Now strip is absorbed; the sig-gated Southbound cue (sig-neu suppressed) rides
the Leadership header; the modal group-action band is gone (one home). Mobile: segmented
lane selector, one lane body at a time, election only when no lane chosen.

Unchanged (§13.7 verified): pv-featured Top Picks, zero fetches, no-LIVE, Grid/Table XOR
`[hidden]` specificity contract, `.sm-hidden` rescue, activate() population law, Evidence &
Record move, entitlement, Southbound sig-* materiality, research-tool toggles.

## Adversarial review (independent Opus, pre-merge, head `da456970f9de`)

Verdict REQUEST_CHANGES: 3 MAJOR, 7 NONBLOCKING, 0 BLOCKER. MAJORs repaired at
`cd6c4657bc16`: (1) mobile lane election guards on `state.anLane == null` only; (2) at-rest
rows render the harvested owner href as `.hk-v37-an-go` + known-zero empty state with
research route; (3) `state.hasRankOwner` gates every piece of rank language. Nonblocking
taken: action-owner lane order via `laneIdx`, pin-evasion test hardening, stale comment.
Clean bill: §11 no-rebuild boundaries, §13.4 population law, §13.7 invariants, live
contradiction case. Deferred follow-ups (bounded, nonblocking):

1. Per-group membership keying — `membershipKnown` is a global flag and the join key is the
   display name (`sectorMembers(x.name.en)` after rotation-name overwrite); a one-sided
   rename would render a false `0 · Prophet`. Stable key exists (`sectorIdFromHref`).
2. Lane header count is recomputed from harvested rows; owner publishes `.anv2-lane-count`.
3. Act-Now tablist focus management (re-render drops focus; no aria-controls/tabpanel) —
   design-system-level, same class as the V3.7 modal focus-trap residue; fix both markets at once.

## Test receipts

26/26 discriminating pins green; **18/18 in-file mutation kills** (population force-switch,
modal-only lanes, rank synthesis, dual-home basis removal, density cap, Board label,
zero-for-unknown, filter-on-lane-switch, RS-prefix strip, mobile one-lane rule, empty-lane
re-election, route strip, known-zero removal, unconditional basis, subscript rank mint,
count-guard short-circuit, rank-ordered lanes).

## Deploy receipts

- VPS `/opt/macro` at merge `5dad2bd4` ~4 min post-merge (ssh receipt).
- Byte identity: local == VPS == sha256 `f0befc369afdf0e7f70be70116418f12c2a5fcd414fe6c0b6cf3d6a36db1105b`.
- No render needed: direct `site/` asset, no template pair, served entitled.

## Production matrix (entitled Claude-in-Chrome, www.mastermind-x.com/hk_stocks.html, 2026-08-27)

| Item | Result |
|---|---|
| Entitled asset | **PASS** — `GET /hk-stock-v36.js?v=20260825` → 200 `private, no-store`, V3.8 body (59,857B); anonymous → **401**; page anonymous → 200 |
| Mount + §4 order | **PASS** — `__mmHKStockV36` + `hk-v37-mounted`; actnow → prophet → leadership → evidence strictly ordered |
| Act-Now at rest | **PASS** — Buy Now 6 (3 rows + View all), In Favour 2, Bottoming Watch 1, Reduce/Avoid 4 (3 + View all); panel 240px; 9 route links |
| Leadership | **PASS** — `RS #1..#5`, basis chip visible, stance separate, counts under `Prophet/候选` |
| Contradiction case | **PASS (live data)** — `RS #1 Healthcare & Pharma · Reduce/Avoid` beside `RS #3 Financials & Banks · Buy Now` |
| Flow cue | **PASS** — first `.sbah-card` is `sig-out`; cue renders ("Mainland is trimming — a liquidity drag.") |
| Group → Prophet filter | **PASS** — Insurance row: Top Picks stays selected, pill on, `1 shown · 8 on board`, dual is-active marks |
| Grid/Table XOR after filter | **PASS** — exact XOR; table filtered to 1 row; round trip clean |
| Zero Top Picks path | **PASS** — Consumer: explicit zero + invitation; deliberate switch reveals exactly `2020.HK` |
| Known-zero group | **PASS** — Healthcare: quiet "No current Prophet names…" + route `sectors/hk-healthcare-pharma.html` |
| View all round trip | **PASS** — buy lane 3→6→3 |
| Modal | **PASS** — no lane band, `RS #N` cells, basis in h4, headers Rank/Name/Action/Cycle state/Leaders/Prophet, 3 Southbound rows, Escape/× closes |
| sm-hidden rescue | **PASS (production)** — resize ×3 under All: theme.js re-added `.sm-hidden` to 1 moved card; all 8 stayed visible |
| Evidence & Record | **PASS** — trd chip + dialog opens with real ledger ("Hong Kong board · vs Hang Seng"); Methodology → measurement.html |
| Research toggles | **PASS** — one-at-a-time reveal round trip |
| Dark + light | **PASS** — screenshots at scrollY 0, both themes |
| ZH | **PASS** — `data-lang=zh`: 现在行动 / 领先与轮动 / 相对恒生指数 / 候选 / owner lane vocab; `Industrials & Transport` untranslated is the owner's own name_zh fallback (pre-existing) |
| No-LIVE / board vintage | **PASS** — zero LIVE text; chip `Board Aug 26, 2026` |
| Console | **PASS** — zero errors on plain reload |
| 390 px | **Residual (V3.7 class)** — OS ignores window resize on the automation tab (innerWidth stayed 1405); exact shipped bytes (hash above) passed the full 390px grammar in a local real browser (segment counts as fixed badges, one lane at a time, no overflow, full-width cards) |

## Ledger

**HK V3.8 presentation correction: PROVEN_LIVE (2026-08-27).**
Canada V38-R2 is the next wave on this carrier. China: separate later carrier after a
fresh census (unstarted). US: decoupled, unauthorized. No China/US writes occurred.
