# Blocked-entry conditional override — PRE-REGISTRATION

**Registration commit:** `98fe6113af617a7f37f6efce85c6945eaa37cff0` at
`2026-08-10T05:35:10Z`. Author attestation: frozen before any held-out results were
viewed; no study implementation or results artifact exists in the repository at that commit.
**Family:** `blocked_entry_conditional_v1` (Terminal `bear_block` override arm).
**Instrument:** scratchpad `blocked_entry_study/study.py` (committed with results doc on completion).
**Operator direction (2026-08-10):** no shadow-ledger delay; mine the full backtest history now;
distill WHEN blocked fires should be taken vs honored; grade with stop-based execution, not
fixed-horizon averages. This prereg freezes that study's gates so a passing result is immediately
ratifiable and a failing one closes cleanly.

## §0 Standing-law position (why this is legal to run tonight)

- `DNR:KILL-200DMA-RECLAIM-VETO-FLAT` bars a FLAT drop of Prophet's reclaim veto; its §9 ruling
  explicitly sanctions **regime-conditional constructions through their own prereg**. This is that,
  applied first to the Terminal's `bear_block` (a sibling gate, distinct era/fence). A passing
  verdict here does NOT flip Prophet — the Prophet arm gets its own prereg under `us_prophet_v1→v2`.
- Not a regime scorecard/fusion (`DNR:KILL-REGIME-SCORECARD`, `KILL-COMPOSITE-REGIME-RELIABILITY-MONITOR`):
  conditioning uses two plain, existing measures (SPY drawdown/200dma state; the name's own 2-week
  StochRSI) — no composite score, no positioning keys.
- Research tier: context-only, with no display or accrual authority; it cannot rank, gate, size,
  enter, issue, or alter Prophet/Neural Web. Any LIVE veto behavior change requires the operator
  era stamp (§4) — the LLM originates nothing (A7).

## §1 Cohort and execution construction (frozen)

Events: every raw CB/revBuy fire vetoed **only** by `bear_block` (would-enter with the veto off;
keeper-quality `block` bars excluded), replayed by the production `signal_layer` over full local
history, ~1,540-name US panel + HK/CN names where local OHLC exists. PIT entry at the first session
after the fire is knowable (`known_ts`).

Execution: stop = min(low, fire 3D bar + 2 prior) − 0.5×ATR14(daily) [design-era tunable ×only];
stopped on daily close < stop; graded (a) stop-only + 252d time exit, (b) breakeven trail at +1R,
(c) 63d fixed. Metrics: expectancy in R, win/stop-hit rates, bought-the-low rate, p90/p95, runup
capture 126/252d; arms: taken-entries, per-name-year matched random-date placebo.

## §2 Pre-registered hypotheses and gates (held-out era 2019+, parameters frozen on ≤2018)

- **H1 — ordinary washout override.** Blocked fires with the market NOT in systemic bear
  (SPY <15% off 252d high AND not >40 sessions below its 200dma; definition may be tuned only in
  the design era) have stop-execution expectancy **> 0** AND **> the matched placebo arm**, on the
  held-out era, with a date-clustered bootstrap 95% CI excluding 0 on the R-expectancy. Per-date
  weighting reported alongside pooled (both must be sign-positive; magnitude gate on pooled only).
- **H2 — systemic-bear total-washout timing.** Within systemic-bear windows, blocked fires with the
  **total-washout flag** (name 2W StochRSI %K turned up from <15 within the last 2 two-week bars)
  beat those without it: conditional expectancy difference > 0, date-clustered 95% CI excluding 0,
  held-out era. If either cell has <30 fires or <10 distinct dates, the verdict is **UNDERPOWERED —
  DISCLOSED**, not a pass or fail; the cell keeps accruing.
- **Sensitivities (no independent verdicts):** intrabar-low stops, entry-at-close basis, depth bands,
  fire-density breadth. Multiple-testing budget: H1+H2 are the only promotion-bearing tests.

## §3 Decision rule (what each outcome ships)

A study verdict is context-only: neither a display promotion nor an entry-mask change is automatic.
Both require the operator ratification and era fence in §4 before they can ship.

- **H1 PASS →** Terminal display promotion: non-systemic blocked fires render as a distinct
  "washout override candidate" class (amber→green-outline tier, plain-word copy; falsifier language
  stays off user surfaces), and the live `enter` mask change (take these fires) is queued behind the
  §4 era stamp — a one-line conditional in `confluence_v2`, shipped only with operator ratification.
- **H2 PASS →** the same, extended inside systemic bears gated on the total-washout flag.
- **H1 FAIL →** the override construction (this stop/entry definition) closes for the non-systemic
  cell; the ⊘ stays refusal-only there. Closes THIS construction, not the search space (ore law).
- **Any outcome →** results doc + tables commit next to this file; the six operator exemplars
  (UEC/HL/NEM/9988/600547/002716) reported as named rows regardless of verdict.

## §4 Era stamp and fences

Live Terminal behavior change requires: operator ratification recorded in this file's §5; a Terminal
signal-era fence (`signal_layer` emission version bump, mirroring `hk_prophet_v2`'s
`BOARD_DEFINITION` pattern) so pre/post events never pool; slice `schema` field carries the version.
Prophet-side reclaim-veto conditional: separate prereg, `us_prophet_v1→v2`, per packet §9.

## §5 Ratification log

- *(empty at freeze)*
