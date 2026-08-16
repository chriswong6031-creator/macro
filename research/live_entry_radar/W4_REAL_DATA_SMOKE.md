# W4 real-data bounded smoke — receipts

Two halves: (A) the frozen-substrate pack + inversion proof on REAL store shapes; (B) the
bounded vendor minute-aggregate fetch (the W3 `unverified` item). No new vendor contract, no
new credential mechanism, no bulk crawl — §7.2's episode-windowed law throughout.

## A. Pack + proof on real store frames (run 2026-08-15, this session)

**Substrate:** `data/stocks/{NVDA,TSLA,NFLX,AAPL,INTC,PFE}.parquet` at branch-base commit
`b8e236bb` (materialized via `git show` — sparse-safe; store tip 2026-08-13; columns
close/high/low/volume — no `open`, exactly as contract §10 records). `as_of=2026-08-13`
matching the tip.

| ticker | K(conf) | close | ATR14 | bars | c1_arm_price | c2a_cross_price |
|---|---|---|---|---|---|---|
| AAPL | 5.41 | 305.26 | 8.197 | 11,509 | **320.0362** (in-washout name: solvable) | 304.4716 (boundary False) |
| INTC | 93.61 | 104.56 | 7.384 | 11,697 | `never_true` | 98.2008 (boundary True) |
| NFLX | 80.48 | 78.24 | 2.437 | 6,095 | `never_true` | 77.1200 (boundary True) |
| NVDA | 87.89 | 225.30 | 7.229 | 6,932 | `never_true` | 217.5955 (boundary True) |
| PFE | 56.42 | 26.80 | 0.553 | 13,663 | `never_true` | 27.7676 (boundary False) |
| TSLA | 96.18 | 339.96 | 13.725 | 4,056 | `never_true` | `never_true` |

Findings, all consistent with frozen law:
- `never_true` on high-K names is the honest §7.1 degeneracy, not a defect: K = SMA(3) of
  rawk, so with the two prior confirmed rawks frozen high, no single provisional close can
  put K under 20 (floor = (rawk₋₁+rawk₋₂)/3). C1 arms are structurally rare states — matching
  §17's ~30-in-washout-of-900 product shape. The deeply-washed name (AAPL, K=5.4) solves a
  real, finite arm boundary and both directions verify at the boundary.
- **Inversion proof on real shapes: 47/47 cases pass** (`threshold_boundary` 18,
  `state_micro_path` 7, `rearm` 7, `c3_turn` 5, `c2f_rebound` 5, `basis_tolerance` 5).
- **Timing (operational):** ~1.18 s/name single-threaded on 4k–13.7k-bar histories (6 names,
  7.07 s) → a ~1,500-name probe set ≈ 30 min. Acceptable for the off-RTH pack window
  (10:00–13:20 UTC attempts); parallelizing the per-name loop is the follow-up if the window
  ever tightens. The RTH evaluator is unaffected (pack is read-only at RTH).
- Store-freshness: `build_pack` at `as_of` ahead of a name's store tip flows into the
  per-name freshness law (stale ⇒ downstream null); the script-level store-staleness refusal
  (exit 5) is the operator-facing gate, and the RTH stale-pack gate
  (`as_of == expected_last_session`) is the runtime protection.

## B. Vendor minute-aggregate smoke (run 2026-08-15, same session — resolves the W3 `unverified` item)

**Path:** `vendor_minutes.VendorMinuteReader` with the real transport (the already-entitled
Massive/Polygon-compatible key from the host env — no new vendor contract, no new credential
mechanism), NVDA + AAPL × sessions 2026-08-10..08-14. Episode-windowed per-session fetches
(~0.4–0.5 s each), never a bulk crawl. Full receipt JSON archived in the session scratchpad;
summary here.

| receipt | measured |
|---|---|
| minutes/session | 829–939 rows (vendor returns the full day from 08:00Z = 04:00 ET premarket) |
| extended hours | present in the raw tape, EXCLUDED by the RTH filter — proven by bucket geometry below |
| 4H grid | bucket 0: 09:30–13:30, `effective_minutes=240`, confirmed; bucket 1: 13:30–16:00, `effective_minutes=150`, `clipped=True`, confirmed — exactly A5.4's session-open-anchored grid, DST-correct (EDT) |
| basis | `adjusted=true` aggregates vs the adjusted daily store: session-final 4H close vs official store close gap **0.32–2.66 bp** across 8 name-sessions — same basis (the residual is last-continuous-trade vs closing-auction, not an adjustment seam) |
| freshness | Friday 2026-08-14's full session available on the Saturday fetch; per-session timestamps tz-aware UTC, `knowable_at = start+60s` law intact on real rows |
| cache | completed sessions cached under the state dir on first fetch (steady-state = 1 tail fetch/name/pass) |

**Verdict:** the real-vendor minute path supports C3's completed-4H semantics as designed —
grid, clipping, confirmation, basis, and freshness all behave on real data exactly as the
synthetic battery assumed. The W3 handoff's `unverified` row is closed by this receipt.
