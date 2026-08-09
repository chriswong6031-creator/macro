# TuShare wiring takeover — operator attestation + plane architecture (2026-08-09)

**Authority: operator order, 2026-08-09 (driver's seat).** Verbatim substance: the Codex
session that owned Tushare wiring FAILED; this (Claude) lane now conducts the wiring. The
account's entitlements as stated by the operator:

- 常规数据无上限 (regular data: unlimited call volume)
- 特色数据 300 次/分钟 (premium data: 300 calls/min), scope per
  https://tushare.pro/document/2?doc_id=291 — includes 盈利预测数据 (earnings forecasts),
  每日筹码和胜率 (daily chip & win-rate), 筹码分布 (chip distribution), 券商每月金股
  (broker monthly golden stocks)
- A股历史分钟 (historical minute bars — doc_id=370)
- 盘前股本 (pre-market share capital — doc_id=329)
- 集合竞价成交 (auction transactions), explicitly enumerated by the operator as THREE APIs:
  `stk_auction_o` (股票开盘集合竞价数据), `stk_auction_c` (股票收盘集合竞价数据),
  `stk_auction` (当日集合竞价)

This document IS the dated, SHA-pinnable operator attestation the addons foundation's
blocked-state asked for: the auction o/c block reason `blocked_pending_written_entitlement_
confirmation` is satisfied at the OPERATOR-ATTESTATION tier (still `operator_reported`, to be
upgraded to `access_observed_at_request_time` by live probe receipts, per the foundation's
own honesty ladder). It is NOT a vendor-signed license artifact and grants nothing the
two-tier model below does not grant.

## Two-tier authority model (adjudicated this session)

- **Tier 1 — private research collection: AUTHORIZED.** Collection into licensed-private
  stores (gitignored `data/tushare_*` roots on the collection host) and in-repo research
  consumption (`research/cn_prophet_audit/` and engine display artifacts that publish only
  DERIVED aggregates). Authority = this attestation. Mechanism: the addons gate gains a
  second accepted mode (`operator_attestation_private_research_use`) whose allowlist pins
  THIS file's SHA-256; the original vendor-authorization mode and its EMPTY allowlist are
  untouched.
- **Tier 2 — product publication (Terminal / dashboard subscriber surfaces): STILL GATED.**
  Raw-row redistribution, team sharing, and product publication remain behind the original
  `written_vendor_authorization_or_institutional_contract_verified` gate (allowlist
  deliberately empty). Per-surface derived-display rulings happen with the design lane when
  product waves are commissioned. Nothing in this takeover self-attests Tier 2.

## What already exists (do NOT rebuild)

The premium daily plane RUNS in asia-close/daily behind `TUSHARE_TOKEN`: `tushare_chips.py`
(cyq_perf 每日筹码/胜率 summary), `tushare_broker.py` (broker_recommend 金股),
`tushare_forecast.py` (forecast_vip + report_rc 盈利预测), `tushare_moneyflow.py`
(moneyflow_dc/ind_dc), `tushare_margin.py` (margin_detail), `tushare_valuation.py`
(daily_basic), `tushare_history.py` (accruing history for cyq_perf + moneyflow_dc), plus the
full-A spine (`china_tushare_spine.py`, #5116) and the ultraconservative addons pilot
(`tushare_addons.py`, #5098). The operator's rate headroom (300/min premium, unlimited
regular) means those lanes' historical budgets are no longer the binding constraint — noted
for their owners; this takeover does not retune running lanes.

## The four genuine gaps → three build lanes (this session)

| Lane | Scope | Files (collision-owned) |
|---|---|---|
| **A — entitlement + auction/premarket** | Gate mode + attestation SHA pin; UNBLOCK `stk_auction_o`/`stk_auction_c` with pinned doc contracts; live probes (stk_mins 1-ticker, stk_premarket, auction o/c historical-depth probe); receipts | `collectors/tushare_addons.py`, `scripts/collect_tushare_addons.py`, `.gitignore` (all new store lines), probe receipts under `data/tushare_addons/` metadata mirrors in `research/` |
| **B — bulk minute plane** | `stk_mins` full-history plane: resumable manifest, coverage ledger, per-minute rate governor, keep-first immutable partitions, backfill runner (mac studio, OFF the render path); store `data/tushare_minutes/` (gitignored, local-first — R2 promotion is a later reviewed step; the Massive R2-first law binds USER-FACING tick planes, not private research stores) | NEW module `collectors/tushare_minutes_plane.py` + `scripts/backfill_tushare_minutes.py` + contract JSON + tests (no shared-file edits) |
| **C — chip distribution** | `cyq_chips` (筹码分布 full distribution — confirmed zero references repo-wide): collector + store + history accrual per the `tushare_history.py` pattern; 300/min governor shared-budget discipline | NEW `collectors/tushare_chips_distribution.py` + tests; `tushare_history.py` extension (sole owner this session) |

**Workflow wiring is deliberately DEFERRED:** no lane touches `asia-close.yml`/`daily.yml`
this session. Nightly cadence wiring is one integration PR AFTER collectors + probe receipts
land — avoids three-way conflicts on the fleet's hot lane and keeps the render budget
untouched until stores exist to wire.

## Sequencing law (TP-0, binding)

No bulk backfill executes until that endpoint's live probe receipt exists (access + schema
witnessed at request time). Tonight (Sunday 21:30+ Beijing): historical probes are legal
(stk_mins on 2026-08-07; stk_premarket 2026-08-07; auction o/c historical-depth probe — the
docs' history claim is verified BY the probe). Session-window captures (realtime
`stk_auction` 09:26–09:29; true ex-ante premarket) begin Monday; the §8.5 "9:25 auction
snapshot" need is largely superseded by `stk_auction_o` if (and only if) the probe shows
same-day availability with history — record the answer in the probe receipt.

## Rate budget adjudication

The 300/min premium budget is ONE shared pool: bulk backfills run SEQUENTIALLY (one lane at
a time, Lane B before Lane C's history accrual), each with its own governor margined to
≤240/min so nightly incrementals and the running premium lanes never starve. Regular-tier
calls (trade_cal, daily plane) are unlimited per the attestation but keep existing
throttles — "unlimited" is a vendor statement, not an invitation to hammer.

## Consumers (recorded so the wiring lands where needed)

1. CN limit-alpha intraday battery (masterplan §8, sized target +2.03%/t 3.55): consumes
   `data/tushare_minutes/` the session after coverage spans the event catalog's window.
2. True turnover ratio + float-normalized walls (v0's f2 null): consumes `stk_premarket`.
3. The 9:25 fill model + auction conditioning (§8.5 collectors item): consumes auction o/c.
4. M2/M4 chip-concentration footprints: consumes `cyq_chips` + existing cyq_perf.
5. Terminal/dashboard product surfaces: Tier 2 — design-lane waves, gated as above.
