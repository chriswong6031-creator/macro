# Merge coordination — `feat/signal-engine-buy-filter` → `main` (PAUSED, needs cross-session sign-off)

> Status as of this note: **NOT merged.** The branch is **405 commits behind `main`** and a direct
> merge produces **37 conflicts**. The owner asked to coordinate the one real product conflict
> (below) with whoever owns `main`'s board gate before changing the live board. `main` is untouched.

## TL;DR for the other session

This branch carries the **confluence tier cascade** for the Standout grids (US/CN/HK/CA/Intl):
the validated MACD-RSI × StochRSI buy-filter promoted to the board gate (`#544`), extended into the
owner's **weighted T1→T4 cascade** (`research/signal_engine/TIERED_CASCADE.md`, held-out validated):

| tier | weight | signal |
|---|---|---|
| T1 | 1.0 | 3D MACD-RSI × 3D StochRSI, buy-filter endorsed (master) |
| T2 | 0.8 | 2D MACD-RSI cross + 3D StochRSI crossed |
| T3 | 0.6 | 2D MACD-RSI projected ≤1–2d + 3D StochRSI already crossed |
| T4 | 0.4 | 2D MACD-RSI projected + 2D StochRSI + above-200MA |

Board ranking = weighted blend (`signal_gate.blend_sorted`: `0.45·tier + 0.55·conviction-pctile`).
Engine: `engine/signal_gate.py` + `engine/confluence_tiers.py` (new on this branch, **not on main**).

## The ONE blocker — the board gate diverged into two designs

Both sessions independently rebuilt the Standout board gate, differently:

| | `main` (live) — **bottoming-alignment** | this branch — **confluence cascade** |
|---|---|---|
| signal | `engine.cycles.mtf_alignment` (standard **price-MACD** MTF: weekly not-falling + 3D nearing cross + daily crossed) | faithful **RSI-MACD × StochRSI** confluence + buy-filter (charter §4) |
| gate | cycle-not-blocked + entry_z>0 + aligned/near | `signal_gate` eligible (take / T2 / T3 / T4) |
| tiers | aligned / near | weighted **T1→T4** |
| where | `build_stock_library.py` ~L1413 (`rank_by="bottoming-alignment"`) | `#544` + cascade (this branch) |

They overlap ("is the tape turning up at a good entry?") but use different math + tier schemes.
**Decision needed before merge** (owner is coordinating, not letting one override the other):
- **Combine** — keep bottoming-alignment as the inclusion gate, layer the confluence T1→T4 as the
  tier badge + weighted ranking on top (most additive; both preserved). ← *recommended*
- **Replace** — confluence cascade becomes the primary gate (faithful RSI-MACD, charter-compliant),
  retiring bottoming-alignment.
- **Off-board only** — land the per-stock confluence signal + §7 chart markers + the cascade engine,
  leave bottoming-alignment as the board gate.

## Everything else is mechanical (already analysed)

- **`engine/signal_quality.py` — RESOLVED, keep `main`'s.** `main`'s version is a strict **superset**:
  it has every cascade dependency (`early_now`, `early_markers`, `markers`, `quality:pending`,
  `risk_flags`, `trail_breach`, the buy-filter) AND the other session's `#540` OHLC-reconstruction
  (optional `daily_high`/`daily_low`). `main`'s `analyze()` returns the **identical §7 contract** the
  cascade reads, so `signal_gate`/`confluence_tiers` work against it unchanged. **Do not overwrite it.**
- **Clean adds** (`main` lacks them): `engine/signal_gate.py`, `engine/confluence_tiers.py`,
  `engine/buy_filters.py`, `research/signal_engine/{GRID_GATE,TIERED_CASCADE,CONFLUENCE_TUNING…}.md`,
  the `tuning_*.py` drivers.
- **`engine/setups.py`** — additive: the `gate=` param + `blend_sorted` use on `main`'s version.
- **Builders / templates / `build_site.py`** — re-apply the gate+cascade onto `main`'s *current*
  versions once the gate decision is made. (`build_site.py` also needs the `engine.market_gamma`
  import made optional — that module is main-only and absent on this branch.)
- **Docs / `config.yml` / `.github/workflows/daily.yml` / `.gitignore`** — take `main`'s; take the
  newest research docs.

## Why paused (not a blind merge)

Per the owner's `pr-conflict-prevention` rule: stale-stacked branch (405 behind) + fast bot-pushed
`main` ⇒ branch off `main` and re-apply, never merge the stale base. The signal_quality reconciliation
is done; the board-gate design is a product call that touches another session's live work, so it is
deferred to cross-session sign-off rather than decided here.
