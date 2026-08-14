# R4 — independent verification of the R3 record's load-bearing claims

Before building against the R3 verdict, this session recomputed its central factual
claims from the committed fixture rather than trusting the receipts. Recorded here
because a closure pass that inherits a wrong number ships the wrong fix, and because
the R3 authority itself recorded precision corrections against its own critics —
that discipline should not stop at the cycle boundary.

Method: `board-data.js` executed under node with `board.js`'s own `rows()` sort and
`GRID_CAP = 40`; the reachability union computed over the default view plus all
seven lifecycle filters.

## Reproduced EXACTLY

| Claim (R3) | Recomputed | Verdict |
|---|---|---|
| union across default + 7 filters = **102/179** reachable, 77 unreachable | 102 / 77 | ✅ exact |
| canonical 40-card grid mix: blocked_data 13 · wait 15 · buy 11 · hold 1 | identical | ✅ exact |
| **20 of 40** canonical cards are chartless | 20 | ✅ exact |
| Ready filter renders 40, of which **23 chartless** | 23 | ✅ exact |
| count law closes: 62+95+0+0+2 = 159 = `live_total`; +20 = 179 | holds | ✅ exact |
| 27 rows are `life=entered` with `stance=wait` (PRC-312) | 27 | ✅ exact |
| FTI payload stance is `wait`, not the `pv-hold` compare.html renders (DA-003) | `wait` | ✅ exact |
| unreachable rows are the null-priority tail sorted last (PRC-306 causation) | 66 of 77 have `pri == null` | ✅ consistent |

The reachability finding is the one this cycle most needed to be right, and it
reproduces to the row.

## Precision correction — the record is imprecise on ONE number

Reviewer B's pass-2 `corrected_or_sharpened` states:

> "Ready filter: **23 of 40** rendered are chartless and **23 of 40 are no-read**"

The chartless half reproduces exactly (23). The no-read half does **not**:

```
Ready filter, rendered top-40:  chartless 23 · no-read (stance=blocked_data) 17
                               overlap (chartless AND no-read) 16
                               chartless BUT carrying a read 7
ALL 62 ready rows:             chartless 43 · no-read 38
```

The rendered no-read count is **17, not 23**. The `23` appears to be the chartless
figure carried into the adjacent slot.

**Materiality: none, and the finding is unaffected.** VTC-301 is a claim about
*chartless geometry*, and the verdict's own upheld text uses the chartless number
("20 of 40 canonical cards, 23 of 40 under the Ready filter, ~97px of uniform void
each"). Every condition rests on figures that reproduce. Corrected here only so the
next cycle does not inherit it.

**One fact this surfaced that the record does not state, and that the fix needs:**
7 of the 23 chartless Ready cards **do** carry a stance. So the chartless card is
*not* interchangeable with the no-read card — a VTC-301 remedy that routes "chartless"
rows to a de-emphasised no-read treatment would silently demote 7 rows that have a
real read. The equalised-hero remedy avoids this; a "collapse the chartless ones"
remedy would not have.

## Census correction — the freshness slot cites a DIFFERENT widget

PRC-305 requires reusing production's real freshness logic. A production census
established that the R3 artifact's freshness slot is not the board's:

- The mockup renders `.dtp-token` / `.dtp-asof` with `Settled close` / `收盘结算` and
  a `● Delayed` pill. Those are real production classes — belonging to the **intraday
  two-speed tape band** (`dashboard.html.j2:16656`, `_dtpState()`), an hours-scale
  basket-freshness widget whose states are `POST-MARKET · SETTLED CLOSE` and
  `DELAYED · ~Nh`.
- The board's own staleness capability is a different producer on a different time
  scale: `_compute_board_staleness()` (`scripts/build_stock_library.py:1469-1624`)
  → `sessions_behind` / `delayed` (True at ≥2 sessions) → the amber `.nb-stale-note`
  banner (`dashboard.html.j2:15784-15789`):
  - EN `Still ranked on prices as of {price_through} — {N} session{s} behind. We're updating it; check a live quote before you act.`
  - ZH `仍按截至 {price_through} 的价格排序，落后 {N} 个交易日。数据正在更新，操作前请先看一下实时报价。`

So the R3 artifact had spliced an hours-scale widget's chrome onto a sessions-scale
capability, and the product-safety half — the sessions-behind count and the
verify-a-live-price instruction — was absent rather than merely restyled. This
strengthens PRC-305 rather than weakening it: the capability was not "styled
differently", it was **not imported**. R4 binds the behind state to the board's real
producer and copy; the fresh state keeps `Settled close`, which the handoff expressly
permits.

## Verified as stated, adopted without change

The stance ramp in Reviewer B's `fix_exists_for_302` is adopted verbatim. Its key
insight is load-bearing and was checked before adoption: on a dark panel no
*deepening* mix of `--up` can out-contrast `#e0a030` amber (pure `--up` sits at 6.34
vs amber's 7.01), so R3's "deepen for distinctness" reading of the r2 condition could
not have produced a correct ordering by any amount of tuning. The free parameter is
the **direction** of the distinctness mix — toward `--text` — which raises salience and
creates distinctness in one move. R4 does not re-derive the ramp.
