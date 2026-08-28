# Stock Dashboard V3.8 — Canada acceptance record (PROVEN_LIVE 2026-08-27)

Carrier: `stock-dashboard-v38-hk-ca-fable-20260826-sol-001` (V38-R2) · WS:PROPHET-HK-CA-REVAMP
Authority: `research/STOCK_DASHBOARD_V38_ACTION_LEADERSHIP_ARCHITECTURE.md` §8.2 (frozen, #6456)
+ `DEC:V38-ACTION-IS-NOT-LEADERSHIP`. Follows HK V38-R1
(`research/STOCK_DASHBOARD_V38_HK_ACCEPTANCE_2026-08-27.md`, PROVEN_LIVE before this wave began).

## Implementation identity

- PR **#6545**, branch `claude/v38-r2-canada-action-leadership`.
- Heads: `8c86aef24c0c` (initial) → **`b924678a87a9`** (post-review repairs; reviewed and merged).
- Squash-merge: **`1276333b37b9131ed77c97bc6ffaa63a1ca9be72`** (2026-08-27; head re-read pre-merge).
- Changed-file census: `site/canada-stock-v36.js`, `tests/test_canada_v36_composer.py` — **only**. Loader untouched.
- CI: ci.yml run **33059279089** SUCCESS on `b924678a87a9`; only red = the non-binding `ci-authority/codex/merge-queue-pilot`.

## What shipped (capability delta)

Before: group action lived only inside the Expand-leadership modal; the composer minted a
sector "rank" from lane-traversal position; the count column wore the ambiguous BOARD label;
a page-global membership assumption could mark every lane group known.

After: the owner-native **What to Act On Now** map renders AT REST above Prophet (4 exact
`anv2` lanes, ≤3 rows per lane before View all, ~240px collapsed, per-row owner
`sectors/<id>.html` research routes, mobile one-lane segmented grammar with the null-only
lane election). **No presentation-owned rank exists anywhere**: sectors carry no number on
any surface, and **Leadership & Rotation renders THEMES ONLY** (§8.2.4) — `Theme #N` from
the owner's `themes[].rank` under a visible `Theme rank/主题排名` basis, all theme-rank
language gated on `state.hasThemeRank`, action stance a separate field. **Membership is
per-group** via the board's own sector vocabulary: in-vocabulary groups carry real
`N · Prophet/候选` counts and filter; out-of-vocabulary groups are disabled research
destinations (no false zeros, no no-op filters); themes without a basket entry likewise
lose the filter affordance. Known-zero groups get the quiet §10 state + route.

Frozen and verified byte-identical to pre-change behavior: first-five Top Picks accepted
projection, LIVE quote plane + table enhancement, Grid/Table XOR + `.sm-hidden` rescue,
Track Record `.trk` move, Terminal routes, the two `canadabasketdata` fetches with the
2.5s degrade.

## Adversarial review (independent Opus, pre-merge, head `8c86aef24c0c`)

Verdict REQUEST_CHANGES: 2 MAJOR, 2 NONBLOCKING, 0 BLOCKER — all repaired at `b924678a87a9`:

1. (MAJOR) Global membership flag rendered **false zeros** across the lane/board taxonomy
   mismatch (lane `Communication Services` vs board `Communication`: 9 of 12 rows would
   read `0 · Prophet`, one while TELUS + Cogeco sat on the board). → per-group
   `sectorVocab.has(name.en)` gate; global flag deleted.
2. (MAJOR) The Leadership sector column was an action-ordered, truncated list — §6.2's
   "numbering rows because they happen to be rendered first" with the digit removed. →
   themes-only Leadership surface incl. modal (architecture §8.2.4 is the sanctioned shape);
   `Sector Leadership` pane and sector-context rank language removed.
3. (NONBLOCKING) Unknown-membership groups offered a no-op filter that painted the full
   board as matching. → activation attributes gated on `x.members != null` on all three
   surfaces; unknown rows render disabled with the route as their affordance.
4. (NONBLOCKING) A tautological test assertion. → replaced with a full-scan all-null pin.

Review clean bill: traversal-rank deletion, owner-only theme rank, hasThemeRank gating,
frozen surfaces byte-identical, election guard, XSS clean, §11 boundaries (2 files only).
Reviewer watch-item honored during proof: composer fetched with `cache:'reload'` before
probing (loader `?v=20260823` stamp is house practice; asset served `max-age=60,
must-revalidate` / entitled `private, no-store`).

## Test receipts

17/17 discriminating pins green; **20/20 in-file mutation kills** (traversal rank,
positional theme fallback, unconditional rank language ×2, Board label, vocabulary-gate
removal, count-guard short-circuit, modal-only lanes, activation-affordance
unconditional ×2, sector pane restored, leadership-consumes-sectors, density cap, election
hijack, filter-on-lane-switch, route/known-zero strips, mobile one-lane, fresh-cue
zero-hide, population force-switch, at-rest strip).

## Deploy receipts

- VPS `/opt/macro` at merge `1276333b37b9` within the pull cycle (ssh receipt).
- Byte identity: local == VPS == sha256 `ff38a3cc33e58023b4b7f3004409629ce6f1ebd2b5157218de17353a4f7f5d81`.

## Production matrix (entitled Claude-in-Chrome, www.mastermind-x.com/canada_stocks.html, 2026-08-27)

| Item | Result |
|---|---|
| Entitled asset | **PASS** — `GET /canada-stock-v36.js?v=20260823` with `cache:'reload'` → 200 `private, no-store`, V3.8 body (51,090B) |
| Mount + §4 order | **PASS** — actnow → prophet → leadership → evidence strictly ordered; panel 240px |
| Act-Now lanes | **PASS** — Buy Now 0 (truthful `—` body), In Favour 4 (3+View all), Bottoming 3, Reduce/Avoid 5 (3+View all); 9 route links |
| Per-group membership | **PASS (live)** — Real Estate/Financials/Energy actionable with `1 · Prophet` counts; Gold Miners/Communication Services/Banks etc. disabled, no count, route only |
| Leadership themes-only | **PASS** — one column, `Theme #1..#5` + `Theme rank` basis, owner stance separate (`Theme #5 Oil & Gas · Trim` beside `#1 Uranium · Accumulate` — rank/action disagreement rendered honestly); no sector list at any depth |
| Sector filter → Prophet | **PASS** — Real Estate: Top Picks preserved, pill on, `1 shown · 6 on board`; Grid/Table XOR exact, table filtered to 1 row, 6 live quote cells intact |
| Theme filter | **PASS** — Uranium & Nuclear under Top: population preserved; honest filter-miss state (membership known + non-zero, zero board overlap — no false invitation) |
| View all round trip | **PASS** |
| Modal | **PASS** — single theme pane, `Theme #1`, headers Rank/Name/Action/Leaders/Names, no Sector Leadership |
| Evidence & Record | **PASS** — trd chip present in the moved section |
| Fresh cue | **PASS** — zero `.pv-mk-new` today → cue hidden (no placeholder) |
| LIVE / clocks | **PASS** — LIVE chip with live date beside the separate `Board Aug 26, 2026` vintage chip |
| Dark + light, EN + ZH | **PASS** — screenshots at scroll 0; ZH: 现在行动 / 领先与轮动 / 主题排名 / 候选 / owner lane vocab |
| Console | **PASS** — zero errors on plain reload with composer mounting |
| No overflow | **PASS** at 1440-class width |
| 390 px | **Residual (V3.7/HK class)** — OS ignores automation-tab window resize; the exact shipped bytes (hash above) passed the full 390px grammar (segmented selector, one lane at a time, empty-lane tap keeps the lane, no overflow) in a local real browser |

## Ledger

**Canada V3.8 presentation correction: PROVEN_LIVE (2026-08-27).**
HK V3.8 + Canada V3.8 both PROVEN_LIVE — the regional V3.8 correction is COMPLETE.
China: separate later carrier after a fresh census. US: decoupled, unauthorized.
No China/US writes occurred on this carrier.
