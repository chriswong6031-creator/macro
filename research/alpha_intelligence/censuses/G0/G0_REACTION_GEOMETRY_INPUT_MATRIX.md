# GROK-G0 — Reaction Geometry Input Matrix

**Executed by macro-fleet researcher (sonnet) on FABLE-00 commission, 2026-08-19; Grok lane was undispatched.**

Purpose: enumerate the candidate INPUTS a future "reaction geometry" (how a stock/options complex
actually moved around an event, across the frontier states in `G0_EVENT_CLOCK_AND_CONTRACT_CENSUS.md`)
would need, cross-referenced against what exists in this repository today. This is an input census, not
a design — it does not propose a scoring formula, and per the commission's OUT OF SCOPE clause, no
trading signal or Prophet input is proposed here.

## Legend

`CODE VERIFIED` = module/field read this session. `PARTIAL` = the E0 ledger's own state vocabulary,
reused verbatim where this census independently confirmed the underlying row. `NOT_BUILT` = no
implementation found (grep + targeted reads). `UNKNOWN` = a grep-level search found nothing but a
deeper module-by-module read (out of this session's budget) could still surface something —
distinguished explicitly from `NOT_BUILT` per the commission's honesty requirement.

## 1. Price inputs

| Input | Repo capability | Authority / status | Verification |
|---|---|---|---|
| Pre-event price level (prior close) | Not located as an earnings-joined field; presumably derivable from general price store (`data/stocks/*.parquet` per `pead_sue_pit.py`'s scratch script) | Would need a join to `event_id`/CIK, which does not exist for this purpose | CODE VERIFIED (scratch script pattern exists) / NOT_BUILT (no production join) |
| Overnight/after-hours gap (open vs prior close, or AH price vs prior close) | `digest.py.market_reaction` is a forced-empty typed absence (`status: not_joined`) | Explicitly `SPEC_ONLY` per E0 ledger row 40; explicitly forbidden as a promotion input (`promotion.py:52`) | CODE VERIFIED |
| First-session close vs prior close | Same as above — no computation found | Same | CODE VERIFIED (absence) |
| Multi-day drift (event+1 to event+N) | `engine/expectation_state.py` computes `pead_drift_20d` = stock-minus-SPY cumulative return from event+1 session to min(event+20 sessions, today); display-only, `_horizon_role='hold_thesis'`, must not feed rank/size/gate | context_only, display-tier, disconnected from the Earnings claim graph (different directory, no shared `event_id`) | CODE VERIFIED, `expectation_state.py:1-70` |
| SUE (standardized unexpected earnings) | `engine/sue.py`, seasonal-random-walk proxy, strictly PIT-gated | Feeds `expectation_state.py`; Phase-0 IC/FDR gating owned by `scripts/validate_sue.py` per its own docstring | CODE VERIFIED, `sue.py:1-20` |
| PEAD long/short portfolio construction | `scripts/research/pead_sue_pit.py` — a scratch research script, hardcoded path to an unrelated worktree (`agitated-nightingale-3cf266`), explicit survivorship-bias disclosure (114 survivors / 95 with EPS coverage) | Research-only, not production, not gauntleted for promotion | CODE VERIFIED, `pead_sue_pit.py:1-27` |
| Bad-news absorption / good-news hold (binary reversal-vs-continuation flags) | `expectation_state.py` — `bad_news_absorption`, `good_news_hold`, defined in `research/long_hold/EXPECT_DRIFT_FAMILY_PREREG.md` §2 | Display-only, `_display_only=True` | CODE VERIFIED (field existence) / UNKNOWN (this session did not open the prereg doc's full definitions) |

## 2. Options inputs

| Input | Repo capability | Authority / status | Verification |
|---|---|---|---|
| Implied move (straddle-priced expected % move into the print) | No earnings-specific join found via `git grep` for `options_reaction`, `earnings_gap`, `overnight_gap` across `engine/`, `scripts/`, `collectors/` | N/A | UNKNOWN — grep-only search, not an exhaustive module-by-module read of the ~20 `engine/options_*.py` files |
| Pre/post-print IV crush | `engine/options_ivspread.py`, `engine/options_skew.py`, `engine/options_surface.py` exist as general options-surface modules | Not confirmed joined to earnings event dates this session | UNKNOWN |
| Options flow/positioning around the print | `engine/options_flow.py`, `engine/options_market_memory_*.py`, `engine/options_signal_episode*.py` exist | Not confirmed joined to earnings event dates this session | UNKNOWN |
| Options-implied basis for a "beat/miss" reinterpretation (i.e., did the options market imply a different outcome than the cash-equity move) | No evidence of this concept anywhere in the estate | Not found | NOT_BUILT (as a NAMED concept; underlying primitives may partially exist per the row above, unconfirmed) |

**Explicit scope note:** the commission asked this census to audit "options reaction capabilities."
This session ran a targeted grep across `engine/`, `scripts/`, `collectors/` for the obvious literal
names and found a large general-purpose options engine (20+ modules under `engine/options_*.py`,
enumerated in `G0_EVENT_CLOCK_AND_CONTRACT_CENSUS.md` §1.6) but did NOT open each module to confirm or
rule out an earnings-adjacent computation living under a different name. This is named as an open
question rather than resolved by inference — a false `NOT_BUILT` claim would be worse than an honest
`UNKNOWN` here.

## 3. Analyst-revision inputs

| Input | Repo capability | Authority / status | Verification |
|---|---|---|---|
| Point-in-time analyst consensus (mean target, rating) at/before the event | `collectors/yf_analyst.py` — CURRENT snapshot at fetch time only, not historically reconstructable before the collector existed | `allowed_behavior: annotate_only`, never feeds scoring | CODE VERIFIED |
| Post-event revision velocity (how fast/far targets move after the print) | `data/narrative/analyst_snapshots.parquet` — forward-accruing since the W2 addition (`_append_analyst_snapshots`) | Additive, non-fatal on failure, does not change `targets.parquet`'s contract | CODE VERIFIED (code path); UNKNOWN (actual accrual depth/start date — `data/` is off disk in this sparse worktree) |
| Licensed/vendor consensus with a legal basis for beat/miss | Explicitly absent — E0 ledger: "Licensed estimates; CEI `consensus: unlicensed_absent`" | This is the root cause of the `basis_match` legal gate in `event_workspace.py` | CODE VERIFIED |

## 4. Filing/accounting inputs

| Input | Repo capability | Authority / status | Verification |
|---|---|---|---|
| 8-K Item 2.02 body (the release) | `engine/earnings_release/binding.py` — full body binding with byte-exact receipts | `context_only`; not yet joined to `event_workspace.v1`'s `deltas`/`claims` per this session's reading of `event_workspace_build.py`'s one live path | CODE VERIFIED |
| 10-Q/10-K structural diff (disclosure changes) | `engine/fundamental_forensics/disclosure_diff.py` — deterministic, offline, byte-coordinate-preserving; explicitly not a materiality/intent classifier | FIF-1R3 frozen (Sol, 2026-08-18) — read-only contact for any G-wave, not a build target | CODE VERIFIED |
| Bitemporal fact ledger (source vs recorded cutoff) | `engine/fundamental_forensics/financial_intelligence_packet.py` — `GOLDEN_SOURCE_CUTOFF`/`GOLDEN_RECORDED_CUTOFF`, `BitemporalPolicy.LATEST_KNOWN_AS_OF` | FIF-1R3 frozen; read-only contact | CODE VERIFIED |
| Restatement/amendment detection | `engine/earnings_release/binding.py`'s `is_amendment` (form-based, `/A` suffix) and `ReleaseEvent.amended` | Correction-stability is a tested property of the release-binding layer | CODE VERIFIED |

## 5. Summary judgment (INFERRED synthesis, not a repo claim)

The estate has strong, receipt-grade PIT infrastructure for **document identity and text** (release
binding, disclosure diffs, bitemporal facts) and a genuinely separate, weaker, display-only plane for
**price reaction** (`expectation_state.py`/`sue.py`), with **no production join between them** and
**no confirmed options-reaction capability at all**. A G-wave reaction-geometry build would be
assembling three largely disconnected planes (document evidence, price/PEAD, options) rather than
extending one existing pipeline — this is a scope/sequencing fact the Earnings owner should weigh before
authorizing any build, not a recommendation from this research lane (out of scope per commission).
