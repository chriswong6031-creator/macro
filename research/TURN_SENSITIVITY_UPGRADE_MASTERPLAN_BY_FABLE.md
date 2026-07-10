# Turn-Sensitivity Upgrade (TSU) — per-stock MTF turn detection + dashboard reach masterplan

**Status:** ADJUDICATED 2026-07-09 — builds dispatched same evening (operator directive)
**Owner program:** `turn-sensitivity` (direct successor to `fast-turn`/FTR; composes over FTR W0–W10, all merged 2026-07-09)
**Method:** 6-lane forensic fan-out (price-store technicals ×2 sources, dashboard decision-chain trace, FTR shipped-state audit, MTF machinery census, case-law envelope, operator UX walk) + Opus design brainstorm (14 candidates) → Fable synthesis → Opus adversarial review (12 findings; 2 blockers dissolved on evidence, 4 amendments applied) → this adjudication.
**Operator directive (2026-07-09 evening):** "Mag 7 is about to rip and semis are rebounding hard, yet our system does not detect this… Need to implement highly more sensitive systems able to detect these turns… THIS IS [THE] MOST IMPORTANT UPGRADE."

---

## §0 Executive ruling

The operator's tape read is **confirmed** (fresh-pull ground truth, 2026-07-09 close): META +4.7%, TSLA +3.2%, SOXX +3.5%, SMH +2.5%, AMD +5.7%, MRVL +5.0%, MU +4.5%, WDC +5.0%, STX +3.5%; AAPL −0.6% from its all-time high (+7.4%/5d). Daily MACD bullish crosses printed on AAPL/META/AMZN/TSLA between 06-30 and 07-02 — a per-stock multi-timeframe confluence board would have shown the turn building a week before the operator's complaint.

The system missed it through **five stacked failures**, none of them data availability:

1. **EOD wall.** Every EOD store ends 07-08 all day; the 07-09 session enters engines only at tonight's nightly. The dashboard's "1d" reads were yesterday's moves (META **−2.0%** on 07-08 — the site was not merely silent, it was contra-signalling).
2. **Tape blackout (dominant fast-lane defect).** FTR's `basket_pulse` never populated once all day — including mid-RTH: the 20-min stale gate is structurally incompatible with the live-quotes feed (median delayMin ≈ 238; only ~157/1963 symbols ≤20min). After the close every tape surface renders "data absent" (no last-good persistence). The two-speed tape shipped this afternoon and stayed dark through the very turn it was built for.
3. **Dashboard out of scope.** FTR wired baskets/allocation/basket-detail. `site/us_stocks.html` — the page the operator actually reads (rendered from `templates/dashboard.html.j2`, `mode="stocks"`, build_site.py:3521) — got nothing: no tape band, no turn-watch chips, no pulse fetch.
4. **Slow constructions, confidently framed, foldaway UX.** mag7/ai_semiconductors/memory_storage all carry reco=`avoid` (07-08 theme-scoring) → routed to the **collapsed** hold/avoid fold (cap-6 + "Show more", build_site.py:1204-1238) — invisible above the fold; XLK cycle state TOP WATCH hard-routes to TAKE PROFITS (cycles.py:569 → build_site.py:1312) on the same viewport where the setups table prints XLK **SETUP** ("approaching an up-cross — get ready"); the donor label's bullish-entry meaning ("historically better entry odds") is buried in a tooltip under a bearish-reading "starting to crack" headline.
5. **No per-stock MTF turn machinery.** The house 3D MACD+StochRSI confluence is per-stock, live, and backtested (signal_quality/confluence_tiers) but stops at 3D; weekly MACD crosses exist only as alert-timeline events (ticker_alerts `macd_w`) and cycle tf_state fields; the only 2W machinery for US equities is the PIT-safe epoch-anchored resampler inside `engine/htf_durability.py` (#1984) — **orphaned, zero callers**. Nothing combines W/2W MACD with the 3D confluence into a turn state, anywhere, for any US stock.

Also of record: turn-watch (FTR W4) simulated on 07-08 data fires **0 WATCH/IGNITION** (ai_semiconductors impulse leg 2/4 members ≥3%) — the basket organ alone, even fully live, likely under-fires on a Mag7-class melt-up whose thrust is concentrated in mega-caps. Per-stock granularity is not a nice-to-have; it is the missing instrument.

**What the house must keep saying honestly:** flip-day chase is the minority trade (58% fade at T+1, n=26); confirmed-tier rotation continuation is NULL both directions; FRESH BUY is the *worst* state on the Act-Now board (the reduce-gate is its only measured edge). Detection speed with printed error rates is the product. Nothing in this program ranks, gates, sizes, or escalates.

## §1 Verified incident tape (2026-07-09, fresh-pull vs store)

| Fact | Value | Source |
|---|---|---|
| Store last bar (all groups) | 2026-07-08 | data/stocks, data/yahoo, data/baskets/ohlcv |
| basket_pulse population today | 0 baskets non-null at every tick incl. 14:16 ET RTH | origin/main file history |
| Discord pings today | 0 (webhook armed; no sources: turn_watch.json absent pre-nightly, shock inactive, pulse null) | shipped-state audit |
| mag7 / ai_semiconductors / memory_storage reco (07-08) | avoid / avoid / avoid → collapsed fold | theme_intel + build_site.py:1204-1238 |
| Daily MACD bull crosses | AAPL 07-02, META 07-01, AMZN 07-01, TSLA 06-30, NVDA 07-08 | fresh pull 07-09 |
| Weekly MACD hist (07-09) | AAPL +2.3 (cross 04-17), SOXX +10.3, XLK +1.9, QQQ +4.6; META −1.7 (narrowing) | fresh pull 07-09 |
| Member OHLCV coverage | 682/683 US members in data/baskets/ohlcv (missing: MMC) | verified this adjudication |
| earlyclose stamps | second run labeled "2026-07-10" for the 07-09 session (UTC-date bug); same class in basket_turn_watch as_of + notify dedup key | engine/basket_turn_watch.py:195,849,866; notify_turn_events.py:442 |
| allocation latest_us.json | still as_of 2026-07-06 — W0 (#2039) fix merged today but unexercised until tonight's nightly | VERIFY-TONIGHT |

## §2 Rulings (TS-R1 … TS-R8)

| # | Ruling |
|---|---|
| TS-R1 | **Honest-delay law.** A delayed quote displayed with its true age and as_of stamp beats a null. The 20-min blanket null-out is repealed: tape surfaces render graded modes `live / delayed(~Nmin) / last_rth / eod`, each stamped. Disagreement chips remain fresh-gated (suppress-never-invert, FT-R12 scope unchanged). No tape surface may go "data absent" while a stamped last-good read exists (FT-R8 extension). |
| TS-R2 | **Session-date law.** Every artifact stamps the NYSE session date it describes (lib/nyse_calendar), never the UTC wall-clock date. Alert dedup keys use session dates. (Fixes: earlyclose stamp, basket_turn_watch as_of, notify dedup.) |
| TS-R3 | **`mtf_upturn.v1` charter.** Per-stock multi-TF upturn-confluence organ over all US basket members (+Mag7+SPDRs, store: data/baskets/ohlcv). Legs: daily MACD bull cross; house 3D MACD+StochRSI confluence (signal_quality reused verbatim); weekly MACD cross (cycles._tf_state); 2W MACD cross (htf_durability._biweekly_close reused as import — engine untouched); monthly-phase context flag displayed as anti-trap context, never a gate. States NONE / UPTURN_WATCH (K≥2) / UPTURN_CONFIRMED (K≥3 incl ≥1 weekly-or-2W leg), 2-day hysteresis. Display tier; authority may_rank/gate/size/escalate=false. This is NOT a revival of the killed "Washout × turn (2W operator seed)" (different construction: no washout precondition, no operator seed, per-stock granularity, K-of-N legs) and is registered as an **expected-NULL forward meter** citing Oracle P8 P-W1/S-W3 + DO_NOT_REBUILD §2. |
| TS-R4 | **Grading law.** mtf_upturn forward ledger accrues from ship date, nightly writer only (FT-R5). Grading unit = catalyst-day cohort (co-firing names share catalysts; DT-R14). Pre-declared ruler: 21d horizon_role, excess-vs-SPY. Promotion question earliest 2027 (PS-R8 inheritance). Backscans are descriptive site artifacts only. |
| TS-R5 | **Salience-not-rank law.** The Act-Now board may add turn/tape context chips and auto-expand chip-carrying rows above the collapsed fold **with lane assignment and sort order unchanged and the slow reco label intact**. Fold-caps are UI truncation, not calibrated keys. No copy may present a turn state as a buy edge (FRESH-BUY refutation stands); the T+1 fade base rate rides inline. |
| TS-R6 | **Two-reads reconciliation law.** Where two house constructions disagree on one instrument in one viewport (XLK cycle TAKE PROFITS vs setups SETUP), the page must say so explicitly (different instrument, different horizon), not leave the contradiction mute. Applies likewise to verdict-vs-evidence contradictions on basket detail pages (coherence chip; verdict untouched). |
| TS-R7 | **Reach law.** us_stocks.html is a first-class tape surface: pulse band, turn-watch chips, per-stock Turn Setups section, staleness banner. Alerts (notify_turn_events) cover mtf_upturn UPTURN_CONFIRMED cohorts under FT-R13 copy (state name + legs + as_of + fade base rate; no direction words). |
| TS-R8 | **Inheritance.** All FTR rulings FT-R1…R13 bind this program unchanged. LLM-origination ban (A7), no beneficiary routing (TI-R5), no fused tape score (WA-R1 shape), "validated" word ban, EN/ZH + title= i18n laws, plain-copy sync where applicable. |

## §3 Waves (U0–U4; Sonnet builds, Opus reviews, per house routing)

| Wave | PR | Contents | Deps |
|---|---|---|---|
| **U0 honesty & persistence** | 1 | build_basket_pulse graded modes per TS-R1 (live/delayed/last_rth/eod + as_of + delay note + last-good persistence w/ FT-R8 stamp); baskets/allocation/basket_detail template suppression rework (render last-good, never "data absent"); basket-detail staleness banner ("as of {close} — today's session not yet ingested; nightly pending") + verdict-evidence coherence chip (TS-R6); donor-cracking headline carries the bullish-entry meaning inline EN/ZH | none |
| **U1 session-date integrity** | 2 | TS-R2 fixes: earlyclose stamp, basket_turn_watch as_of (×3 sites), notify_turn_events dedup date → NYSE session date; tests | none |
| **U2 mtf_upturn.v1** | 3 | engine/mtf_upturn.py + nightly call via build_baskets (no daily.yml edit) → site/stockdata/mtf_upturn.json + data/mtf_upturn/ledger.jsonl + synapse registration (tier=display, notes cite P8/DO_NOT_REBUILD nulls); tests; **lands alone, synapse regen immediately pre-merge** (registry-drift law) | none |
| **U3 dashboard turn surfaces** | 4 | us_stocks.html (dashboard.html.j2 mode="stocks", mode-aware): two-speed tape band; TURN WATCH disagreement strip (turn_watch WATCH/IGNITION or ≥2 members UPTURN_CONFIRMED while reco hold/avoid; reco label intact + fade base rate + as_of); chip-carrying rows auto-expanded per TS-R5; per-stock Turn Setups section (setups visual idiom); XLK two-reads reconciliation chip (TS-R6); browser-verified w/ synthetic-turn + stale-quote fixtures, screenshots in PR | U2 (schema) |
| **U4 alert reach** | 5 | notify_turn_events += mtf_upturn UPTURN_CONFIRMED cohort event source (existing #2044 transport; one ping per state-day cohort; FT-R13 copy) | U1+U2 merged |

Contract-first schema (U2↔U3): `site/stockdata/mtf_upturn.json` = `{schema:"mtf_upturn.v1", as_of:<NYSE session date>, universe_n, tickers:{<SYM>:{state, k, legs:{d_macd, d3_confluence, w_macd, w2_macd}, monthly_phase, since, basket_ids:[...]}}, cohort:{confirmed:[...], watch:[...]}}`.

## §4 Deferred / conditional (surfaced, not built tonight)

1. **LIVE_QUOTES_WORKER_URL + cron */5** — dominant *feed* root cause (quotes 10-15min+ effective, median 238min observed). OPEN-OPERATOR: confirm the 60s-edge-cache Worker is deployed on the Cloudflare account, then wire the repo variable. Until then TS-R1 modes keep surfaces honest rather than dark.
2. **W8b macro-prior prereg** (semicap/AI-complex `_MACRO_PRIOR`) — FT-R7 scored-construction change; needs printed before/after deltas + operator ratification. The "semicap always hold/avoid" structural bias stands until ruled.
3. **Landing-hub tape chip** — OPEN-OPERATOR placement question (public page).
4. **Overlay single-stock spine** (680 member strips) — ties to (1); build after Worker ruling.
5. **htf_durability standalone wiring** — owned by #1984's program; U2 imports its resampler only.
6. **CN/HK/CA mtf_upturn parity** — after US v1 read.

## §5 VERIFY-TONIGHT checklist (first nightly after FTR+TSU merges, ~02:00 UTC 07-10)

- [ ] data/allocation/latest_us.json advances to as_of 2026-07-09 (W0 #2039 exercised) — if not, reopen W0 root-cause with nightly logs.
- [ ] data/basket_turn/ledger.jsonl first rows exist; as_of correct (07-09 session if U1 landed pre-nightly; else amend row + note).
- [ ] turn_watch states on 07-09 session: expect WATCH on ai-complex baskets plausible, IGNITION uncertain (impulse legs: META/TSLA/AVGO/AMD/MRVL/MU/WDC ≥3% — richer than 07-08).
- [ ] mtf_upturn.json first artifact (if U2 lands pre-nightly): expect UPTURN_WATCH/CONFIRMED cluster across Mag7/semis/memory names.
- [ ] Oracle tape-onset panel post-nightly rebuild: does the unconfirmed tier print for tech/semis?
- [ ] Discord: IGNITION/CONFIRMED pings fire once each with correct session date.
- [ ] basket_pulse renders `last_rth`/`eod` mode with stamps on baskets/allocation/us_stocks (post-U0/U3).

## §6 Clocks

- **U7 2026-07-10:** additive trend-state display fields shipped (mid-trend visibility); cross-window construction unchanged.
- **2026-07-16** — one-week read: mtf_upturn firing rates (board-noise check; thresholds amendment-logged), pulse mode distribution (how often live vs delayed vs last_rth), alert counts.
- **2026-08-15** — joint with FTR clock: freshness sentinel zero-silent-stale, pulse p95.
- **2026-10-09** — joint with FTR: turn_watch + mtf_upturn ledger n-counts; threshold re-derivation window.
- **2027 (earliest)** — promotion questions (PS-R8/TS-R4), catalyst-cohort N.

## §7 Rejected in adjudication (recorded; not DO_NOT_REBUILD rows)

Reco/lane changes from turn states (FT-R1/TS-R5 violation); relaxing disagreement-chip fresh-gating (FT-R12 stands); a fused per-stock "turn score" (WA-R1 shape — the panel stays per-leg); building a new per-stock daily-bar fetcher (data/baskets/ohlcv already covers 682/683); U4 as a new notify script (transport exists, #2044); us_stocks_v2.html as the target surface (the live board is us_stocks.html ← dashboard.html.j2 mode="stocks"); blocking U2 on a store backfill (blocker dissolved on evidence — reviewer had audited data/stocks, the 229-name library store, not the member store).
