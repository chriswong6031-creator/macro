# TuShare wiring takeover — operator authority + plane architecture (2026-08-09)

**Authority: operator orders, 2026-08-09 (driver's seat), three rulings in sequence:**
1. The Codex session conducting the Tushare wiring FAILED; this (Claude) lane conducts the
   wiring.
2. The account's entitlements as stated by the operator: 常规数据无上限 (regular data:
   unlimited), 特色数据 300次/分钟 (premium 300/min, scope per tushare doc_id=291 — 盈利预测,
   每日筹码和胜率, 筹码分布, 券商每月金股), A股历史分钟 (doc_id=370), 盘前股本 (doc_id=329),
   and the 集合竞价成交 trio enumerated explicitly: `stk_auction_o`, `stk_auction_c`,
   `stk_auction`.
3. **The license topic is CLOSED and carries NO machinery.** The operator's final ruling on
   the #5161 revert of the pilot foundation: *"I only objected to the license text,
   everything else is fine… please recover and keep everything other than license text."*
   Accordingly: no license-authority env gates, no allowlists, no license nonclaim blocks —
   anywhere. Collection and use proceed on operator order; receipts carry plain provenance
   (operator-ordered wiring, this document) and the EPISTEMIC honesty set only (access
   observed at request time, no complete-history fabrication, no Level-2/order-book/queue
   authority, nulls printed). The pilot surface was recovered minus license text by the
   recovery PR (#5177, merged) with the operator's own foundation-doc text verbatim as its
   doc. (An intermediate version of THIS document described an attestation-SHA gate mode;
   that mechanism is DEAD under ruling 3 — this rewrite is the authoritative form.)

## What already exists (do NOT rebuild)

The premium daily plane RUNS in asia-close/daily behind `TUSHARE_TOKEN`: `tushare_chips.py`
(cyq_perf 每日筹码/胜率 summary), `tushare_broker.py` (broker_recommend 金股),
`tushare_forecast.py` (forecast_vip + report_rc 盈利预测), `tushare_moneyflow.py`
(moneyflow_dc/ind_dc), `tushare_margin.py` (margin_detail), `tushare_valuation.py`
(daily_basic), `tushare_history.py` (accruing history), the full-A spine
(`china_tushare_spine.py`, #5116), and — post-recovery — the add-on pilot machinery
(contracts, clocks, receipts, token hygiene; #5177) minus its former license gates.

## The build lanes (all landed 2026-08-09/10)

| Lane | Scope | State |
|---|---|---|
| **Recovery (ex-A)** | Pilot surface minus license machinery + auction o/c contracts (docs 353/354, units measured shares/CNY) + CLI + tests + live TP-0 probe witness (all six historical probes green) | **#5177 MERGED** |
| **B** | `stk_mins` bulk minute plane: resumable manifest, governor (true floor ~171/min via client throttle), keep-first store `data/tushare_minutes/`, event-catalog-first backfill (~11.1h plan) | **#5163 MERGED** |
| **C** | `cyq_chips` 筹码分布 collector + history accrual + M2/M4 aggregation contract | **#5162 MERGED** |

CI test wiring for the new suites: #5178 (operator chip session). Nightly cadence wiring:
one integration PR after backfills begin — still deliberately deferred off the hot lanes.

## Sequencing law (TP-0) — SATISFIED for historical endpoints

Live probe receipts exist for stk_mins, stk_premarket, stk_auction_o, stk_auction_c
(witness: `research/TUSHARE_PROBE_WITNESS_2026-08-09.md`). o/c serve history ≥3.4y with
date ranges — the §8.5 realtime 9:25 collector is SUPERSEDED for backfill use (an intraday
09:2x read would still need a realtime path; none is currently chartered). The realtime
`stk_auction` window probe remains pending a Monday 09:26–09:29 Asia/Shanghai session.
Local `.env` token was dead (40101 account-wide), operator-refreshed and verified in-session.

## Rate budget adjudication

The 300/min premium budget is ONE shared pool: bulk backfills run SEQUENTIALLY (minute
backfill before chip-history accrual), each governor margined ≤240/min (true single-endpoint
floor ~171/min); nightly incrementals and the running premium lanes must never starve.
Regular-tier calls keep existing throttles — "unlimited" is a vendor statement, not an
invitation to hammer.

## Consumers (recorded so the wiring lands where needed)

1. CN limit-alpha intraday battery (masterplan §8; sized target +2.03%/t 3.55): consumes
   `data/tushare_minutes/` once coverage spans the event catalog.
2. True turnover ratio + float-normalized walls (v0's f2 null): consumes `stk_premarket`.
3. The 9:25 fill model + auction conditioning: consumes the auction trio.
4. M2/M4 chip-concentration footprints: consumes `cyq_chips` + existing cyq_perf.
5. **The Prophet scoring layer (masterplan §10)** — the chartered primary consumer of every
   propensity feature this plane unlocks.
6. Terminal/dashboard product surfaces: commissioned separately through the design lane
   (quality discipline; the license topic is closed per ruling 3).
