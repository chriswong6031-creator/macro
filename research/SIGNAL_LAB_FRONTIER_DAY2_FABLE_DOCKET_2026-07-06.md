# Fable Day-2 docket — 50 mechanism-first candidates — 2026-07-06

Authored by Fable from first principles under the wave-5 rules (receipts required, PO-1..4,
PO-1b latent-factor orthogonality declared AT GENERATION). Each row: mechanism / forced-or-slow
counterparty / why the edge survives arbitrage / data path / payoff set / latent group /
known-territory flags. Excluded by construction: all wave-1..5 families, dead feeds, paid-only
constructs, program-owned preregs (flagged where adjacency exists).

## Declared latent-factor groups (PO-1b — one build slot per group)
LG-CN-SUPPLY (CN-A forced supply): D2-06, D2-26 [+F5-01 currently holds this slot]
LG-CN-SENT (CN-A retail sentiment): D2-39, D2-40
LG-CN-INFO (CN fundamental/info transmission): D2-15, D2-16, D2-18, D2-19, D2-43
LG-HK-FLOW (HK structural flows): D2-07, D2-08, D2-32, D2-34
LG-US-RATES-CAL (rates calendar flows): D2-11, D2-12, D2-13
LG-US-IDX (US index/fund mechanics): D2-03, D2-14, D2-22
LG-INSIDER-SUPPLY: D2-27, D2-28, D2-29 [+ESX A2 reserve adjacency]
LG-SHORT-CONSTRAINT: D2-24, D2-25, D2-30 [+slf001 FTD family adjacency]

## CLASS A — Forced & mechanical flows (14)
D2-01 HSCEI/KOSPI2 autocallable barrier-zone hedging. Structured-product dealers' gamma flips near knock-in clusters -> index drift/vol regime shifts. Counterparty: SP hedging desks (mechanical). Survives: only SP desks map barrier density; equity managers don't. Data: KSD/Korean issuance stats + HSCEI strike clustering (receipt needed). Payoff: HK index book.
D2-02 Vol-target/CTA deleveraging estimator. Realized-vol jump -> next 1-5d mechanical equity supply, replicable from public vol + AUM estimates. Counterparty: rule-bound funds. Honest prior: banks publish versions -> DE-ESCALATION GATE only. Payoff: SPY/TLT timing.
D2-03 Russell reconstitution deletion overshoot. Forced index-fund selling in illiquid deletes each June -> reversion. Counterparty: index trackers. Survives via capacity (too small for institutions). Data: free (recon lists/rank proxies). Payoff: US microcaps. LG-US-IDX.
D2-04 Buyback-blackout breadth. % of SPX in pre-earnings blackout -> corporate-bid drought windows amplify drawdowns. Data: derived free from earnings calendar. Conditioner. Payoff: SPY timing.
D2-05 OPEX gamma-unpinning week. Post-expiry dealer-gamma release -> drift/vol expansion conditional on pinning distance. ROUTE-FLAG: options program owns GEX plumbing.
D2-06 CN major-holder sale pre-announcement calendar (减持预披露). Since the 2023-08+ tightening, planned sales require 15-day pre-disclosure = a FREE forward supply calendar. Counterparty: mandated sellers. Survives: new-ish regime, Western coverage thin. Data: exchange announcements (akshare/eastmoney; receipt). Payoff: CN-A names. LG-CN-SUPPLY.
D2-07 HK IPO cornerstone-lockup expiry. 6-month cliffs create dated forced supply; FINI-era data cleaner. Data: HKEX prospectus/lockup calendars (receipt). Payoff: HK names. LG-HK-FLOW.
D2-08 CN-ADR vs HK-line premium mechanics. Fungible pairs (9988/BABA etc.); conversion frictions bound premium; deviations mean-revert with flow-direction info. Data: both legs on disk/free. Payoff: pairs. LG-HK-FLOW.
D2-09 BTC miner-outflow spikes. Miners = structurally forced sellers (opex in fiat); outflow bursts -> pressure windows. Data: checkonchain ON DISK. ROUTE-FLAG: BTC vector program conditioning.
D2-10 Turn-of-month flow overlay. Payroll/401k mechanical buying window. Ancient/published; persists per recent lit. Entry-TIMING conditioner only, never signal. Data: none needed. Payoff: US entry timing.
D2-11 Quarter-end pension rebalance estimator. Intra-quarter equity-bond relative move -> estimable rebalance flow at quarter-end. Published (banks) -> conditioner with honest prior. Payoff: SPY/TLT week. LG-US-RATES-CAL.
D2-12 Month-end bond-index duration-extension day. Index extension buying on last business day -> TLT/IEF timing. Documented; test persistence honestly. LG-US-RATES-CAL.
D2-13 Treasury auction-cycle CALENDAR overlay. Supply-week concession/rebound (Lou-Yan-Zhang price-pressure cycle) — the CALENDAR timing construct, distinct from the killed absorption SIGNAL (slf006 tested demand metrics, not the supply-cycle overlay). Data: free auction calendar on disk. Payoff: TLT/IEF timing. LG-US-RATES-CAL.
D2-14 ETF closure forced liquidation. Delisting ETFs must sell holdings on a schedule; micro events. Data: free closure announcements. Payoff: micro; likely display. LG-US-IDX.

## CLASS B — Segmented / slow diffusion (8)
D2-15 CN supplier -> US customer link map. Customer-concentration disclosures in CN annual reports; LLM-built static link graph (our qual-intel capability = the moat); US customer news -> CN supplier transmission. Payoff: CN-A names. LG-CN-INFO.
D2-16 Local CN disclosure -> ADR 6-K lag. cninfo timestamp vs EDGAR 6-K arrival; venue/language segmentation window. Payoff: CN ADRs. LG-CN-INFO.
D2-17 TSMC monthly revenue surprise -> US semis residual drift. Free, 10th of month, leads fundamentals. Honest prior: priced same-day by every semi analyst; test the 5-21d RESIDUAL only.
D2-18 CN customs product-level exports -> mapped names (solar modules, EVs, batteries). akshare free monthly detail; underused outside CN. Payoff: CN/US names by product. LG-CN-INFO.
D2-19 Input-cost mechanical chains. CN spot commodity tapes (lithium carbonate, polysilicon, urea — free daily via akshare) -> producer/consumer margin nowcasts with known pass-through lags. Payoff: CN/US material names. LG-CN-INFO.
D2-20 Freight spot -> container shippers. SCFI/FBX moves -> ZIM/MATX EBITDA nowcast; mechanical, tiny capacity (our niche). Payoff: 2-3 shippers.
D2-21 GAO contract-protest resolutions. Award -> protest -> re-award events; free GAO dockets. Payoff: defense names.
D2-22 MSCI/FTSE country reclassification watchlists. Dated index flows into country ETFs. ROUTE-FLAG: intl program surface. LG-US-IDX.

## CLASS C — Constrained agents (7)
D2-23 Fallen-angel EQUITY boundary. IG-mandate holders force bond sales at the junk cut; equity of near-boundary issuers shows pre-downgrade pressure/post overshoot. Data: free ratings actions (receipt: coverage). Payoff: US equities.
D2-24 Reg SHO threshold-list entry/exit. Free daily lists since 2005; persistent-FTD constraint events. FLAG: slf001 family adjacency (same latent: short-constraint). LG-SHORT-CONSTRAINT.
D2-25 SSR Rule-201 trigger natural experiment. -10% day triggers next-day short restriction — trigger derivable ENTIRELY from our price store (no new data). Day-2 constrained-shorting bounce/fade vs matched non-SSR -10% days. Payoff: US names. DATA-READY TODAY. LG-SHORT-CONSTRAINT.
D2-26 CN share-pledge fragility (股权质押). CSDC weekly pledge ratios free; high-pledge names have margin-call cascade zones = AVOID lens. Payoff: CN-A AVOID. LG-CN-SUPPLY.
D2-27 Form 144 electronic filings (regime: electronic-only since 2023-04). Pre-announced restricted-stock supply, machine-readable only ~3y — new-regime moat like 10b5-1. Payoff: US names. LG-INSIDER-SUPPLY.
D2-28 Insider blackout-expiry buy clustering. Timing structure in Form 4 store. ROUTE-FLAG: ESX/insider family territory. LG-INSIDER-SUPPLY.
D2-29 Insider SALES at 52w lows as distress tell. AVOID-not-alpha lens. ROUTE-FLAG: insider family. LG-INSIDER-SUPPLY.

## CLASS D — New / changed disclosure regimes (6)
D2-30 SEC 13f-2 / Form SHO aggregated short positions (LIVE 2025 — the newest dataset in US markets). Monthly gross short by security from large managers. Receipt: publication start, lag, format, coverage. Payoff: US short-side confirmers. LG-SHORT-CONSTRAINT.
D2-31 CSRC dividend-mandate wave. 2024 rules push non-payers to initiate -> CN dividend-initiation drift. Payoff: CN-A. (Cross-check LG-CN clusters.)
D2-32 HK daily buyback tape. HKEX discloses per-day, per-name repurchases — granularity the US lacks entirely. Buyback initiation/intensity events. Payoff: HK names. LG-HK-FLOW.
D2-33 Offshore CN ETF create/redeem tape (KWEB/ASHR/MCHI — ON DISK since #1612). Foreign-flow proxy replacing dead northbound; distinct latent from onshore state flows. Payoff: CN/HK book conditioning.
D2-34 Southbound dividend-tax ex-date clientele flows. 20% dividend tax on southbound holders (vs exempt locals) -> mechanical pre-ex selling in HK high-yielders. Data: ex-date calendar + southbound holdings (on disk). Payoff: HK yield names. LG-HK-FLOW.
D2-35 CN new-delisting-regime ST/shell-death events. 2024 delisting rules killed shell value. ROUTE-FLAG: china-intel ST watch (#1627) extension.

## CLASS E — Proprietary-asset fusions (3)
D2-36 Oracle episode onset x member options positioning. Grade rotation-episode quality by member IV/OI state from massive_options_day. Joint oracle/options program build; only we have both assets.
D2-37 Entry-stack fire x trade-size tape. FLAG: likely folds into w5_trade_size_capitulation as a variant — census to confirm, else drop.
D2-38 NW de-escalation x funding-dispersion composite. FLAG: wiring proposal for the SLF-056 confirmer, not a new family — expected verdict: route to NW rails, not a candidate.

## CLASS F — Calendar / behavioral (3)
D2-39 A-share pre-holiday effect (CNY/Golden Week). Documented in CN lit, retail market. Conditioner with crowding prior. LG-CN-SENT.
D2-40 CN fund new-issuance boom/bust cycle. Monthly issuance totals as contrarian sentiment marker (classic domestic indicator). Conditioner. LG-CN-SENT.
D2-41 13D activist-stake drift. Crowded but persistently documented; EDGAR free. Honest prior: heavily arbitraged; test residual in small caps only.

## CLASS G — Event microstructure & filings (9)
D2-42 LULD halt-reopen drift by halt type. Free NASDAQ/NYSE halt feeds; post-halt day patterns. Payoff: US names.
D2-43 CN abnormal-move mandatory disclosures (异常波动公告). Forced information events after 3-day moves. Payoff: CN-A. LG-CN-INFO.
D2-44 CFO departures differentiated (8-K 5.02 by role). ROUTE-FLAG: special-situations taxonomy extension.
D2-45 FDA AdComm calendar/vote windows. ROUTE-FLAG: healthcare program.
D2-46 SEC comment-letter RESOLUTION release. Letters go public ~20 business days after resolution — dated dissemination lag. Re-derived with mechanism from W3 quarantine (W3 verdicts void, construct legal to re-screen). Payoff: US names.
D2-47 Utility rate-case decision calendar. Real single-name events; 50-state docket scrape = HEAVY flag (same class as WARN ruling: consolidated source or bust).
D2-48 ASR announcements (committed repurchase, distinct from killed authorization family — variant flag vs SLF-028 kill; census to rule).
D2-49 Dividend-cut early warning. Payout coverage + funding gap from fundamentals panel -> pre-cut AVOID lens. Data on disk.
D2-50 ETF primary-market creation halts. Premium blowout events; rare; expected display/context only.
