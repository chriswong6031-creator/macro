# A-share Signal Research — external evidence mapped to our data

*research/china_alpha/phase1/ashare-signal-research.md · 2026-07-03 · reader agent (A-share signal research task)*

**Owner ask:** "we do not understand A-shares that well; look further into what quantitative signals
can surface stocks about to run — sector about to run, mean reversion after complete washout,
catalysts." This doc maps published + practitioner evidence for each candidate signal onto **our own
data stores**, and ranks by *(expected value × buildability-with-our-data)*, marking what is already
validated / falsified in-repo so nothing dead gets re-recommended.

**Scope note / method.** Every internal claim is cited to `file:line` or a command I ran with its
output. Every external claim is cited to a URL. Where our own data was insufficient to *confirm* an
external claim I say so explicitly rather than laundering the external number as ours. All A-share
effect sizes carry the same survivorship / single-regime / not-net-of-cost caveats the repo already
attaches (below).

---

## 0. The load-bearing data discovery (changes the design space)

**`data/china_stocks_raw/*.parquet` carries full OHLC + VOLUME, ~4,300 rows back to 2008, per name,
fresh to 2026-07-02 — and covers 1,495 / 1,495 of the board universe.** This contradicts the standing
premise in `research/CHINA_STOCKS_OVERHAUL.md:64` ("A-shares are **close-only** per stock → no
ATR/ADX/volume/Donchian"). The overhaul doc's constraint is FALSE for the raw store; it is true only
for the *close-only panel* the board actually consumes (`data/china_search/closes.parquet`).

Evidence (commands run):
- `china_stocks_raw/002273.SZ` cols = `['open','close','high','low','volume']`, shape `(4325, 5)`,
  index `2008-09-05 .. 2026-07-02`.
- coverage: `raw tickers: 1506 | board universe: 1495 | overlap: 1495`; sample last-250 volume
  non-null fraction = `1.0`.
- BUT: `grep -rl china_stocks_raw engine/ scripts/` → only `scripts/collect.py`. **No engine and not
  the board builder consume it.** The volume data exists on disk and is unused by the signal pipeline.

**Consequence:** every volume/turnover-shape signal below (abnormal turnover, volume-price divergence,
turnover concentration) is *buildable on real per-name volume with deep history* — not a close-only
proxy. This is the single biggest lever this research surfaces. **Caveat:** `open` is dropped from the
*collected* `china_stocks`/`hk_stocks` store used by the grader
(`research/CHINA_ENGINE_REASSESSMENT.md:119`, `collectors/_stock_ohlc.py:26`), but the *raw* store
above DOES have `open` — so a T+1-open fill model is buildable from raw even though the grader plane
can't see it yet.

---

## 1. The known verdicts I must not re-litigate (the dedup spine)

From `engine/china_signal_lab.py:103-210` (the in-repo registry), `research/CHINA_HK_STOCK_SIGNALS.md`,
and `research/CHINA_ENGINE_REASSESSMENT.md`. All effect sizes below are quoted from those artifacts.

**VALIDATED (survived Phase-0 / measured positive):**
- **3-month within-sector reversal, deepest quintile, NO gates** — the *only* cross-sectional
  name-selection edge. +0.56%/mo, Sharpe 0.58, maxDD −37.6%, hit 56% (~790 names, 388 monthly
  rebalances, 1990→2026). `CHINA_HK_STOCK_SIGNALS.md:104-114`; `CHINA_ENGINE_REASSESSMENT.md:223`.
  **Turn-confirmation, quality floors, and market-regime timing gates ALL flip it negative**
  (−0.29%/mo, Sharpe −0.29, maxDD −78.9% with ret_5d>0 gate) — `CHINA_HK_STOCK_SIGNALS.md:109`,
  `CHINA_ENGINE_REASSESSMENT.md:71`.
- **Low-vol defensive sleeve** — Q1 Sharpe 0.98 vs 0.88 mkt; wired confirmer, *not* long-short alpha.
  `CHINA_ENGINE_REASSESSMENT.md:259`, `china_signal_lab.py:122`.
- **Deep-DISCOUNT block trades (≤−15% discount): +3.45%/21d fill-realistic, t≈3.4 (669 obs)** — the
  strongest tested dip confirmer, the best northbound replacement found. Currently probationary,
  ZERO score weight until the forward ledger matures. `china_altdata.py:250-266`,
  `CHINA_ENGINE_REASSESSMENT.md:205,211`.
- **Credit impulse (TSF), realized-vol regime, margin euphoria** — the three SCORED regime de-risk
  legs (market-SIZING unit). `china_signal_lab.py:105-116`.
- **Forward-drawdown radar composite** (market sizing, validated, unwired) and **global AI-semis→CN-CPO
  weekly confirmer** (theme slice, t=3.27, orphaned). `CHINA_ENGINE_REASSESSMENT.md:43,259`.

**FALSIFIED / KILLED (tested, no edge or wrong-sign):**
- **Cross-sectional momentum** (total AND residual) over deep history — IC negative/zero, nothing
  clears FDR. `CHINA_HK_STOCK_SIGNALS.md:36-47`; `china_signal_lab.py:205`.
- **Cross-sectional value** — Sharpe −0.46, display-only. `china_signal_lab.py:208`.
- **Acceleration** — anti-predictive, killed. `CHINA_HK_STOCK_SIGNALS.md:80`.
- **Raw hot-money LHB flag on dip names: −1.43%/21d fill-realistic, cluster-t≈−2.2 (931 obs)** —
  DRAINS alpha; fires *after* the move. `china_signal_lab.py:31-34`, `CHINA_ENGINE_REASSESSMENT.md:205`.
- **Block-trade PREMIUM leg (as designed): −0.60%/5d, t≈−2.8** — premium = institutional unload.
  `CHINA_ENGINE_REASSESSMENT.md:107`.
- **Limit-up continuation as a BUY: naive dip+ZT +1.74%/5d collapses to +0.04% fill-realistic,
  −1.16%/21d** — the continuation premium lives entirely in the unbuyable first (locked) session.
  `CHINA_ENGINE_REASSESSMENT.md:107,199`.
- **"Volume dry-up" and "quiet base" filters — FALSIFIED** (prior basing-doc H4, carried in
  `CHINA_STOCK_PIPELINE_PROBLEM_AUDIT_FOR_FABLE.md:305`). *The naive dry-up thesis is already dead.*
- **Northbound net flow — CONFIRMED DEAD.** `data/china_connect/northbound.parquet` last 60 `net`
  values all NaN (command output below); real-world disclosure stopped 2024-08-16, 97.3% null since
  (`CHINA_ENGINE_REASSESSMENT.md:211`). **Turnover column still live.**
- **Southbound / A-H premium / margin-velocity aggregate — dead as TIMING legs** (fwd-CSI300 IC
  +0.022 / ≈0 / +0.035; southbound sign-unstable train −0.16/test +0.49).
  `CHINA_ENGINE_REASSESSMENT.md:205`.

Freshness snapshot (my probes, all `asof` 2026-07-01/02 unless noted):
`ZT_POOL` 385 rows but only **3 dates** 06-30..07-02 (`consec_boards` up to 4; 170 `failed_seals`);
`LHB` inst net-buy + seat reasons present; `MARGIN detail` monthly (06-30 vs prior 06-01);
`QVIX300` ends **2026-06-26** (4 td stale); `SOUTHBOUND` live; `NORTHBOUND` NaN; `ETF shares` live but
only 20 days deep (510300 shares 28.6B→18.4B = real redemptions); `LIMIT breadth` 27 days;
`CREDIT/TSF` monthly, latest 2026-04-01 available 2026-05-16.

---

## 2. Candidate signals — mechanism → A-share evidence → our data → verdict

Each entry: **mechanism · external A-share evidence (source, rough effect, period) · data required · do
WE have it · frequency + decay · failure modes · repo status.**

### A. Abnormal-turnover / turnover-shape cross-sectional signal  ★ TOP NEW CANDIDATE

- **Mechanism.** In a retail tape, a spike in turnover marks the peak of an attention/overreaction
  cycle; names with *abnormally high* recent turnover subsequently underperform (the demand shock
  unwinds), and *stable/low* abnormal turnover outperforms. This is the microstructure sibling of the
  reversal edge, on the volume plane instead of the price plane.
- **A-share evidence.** "Anomalies in the China A-share market" (2000–2019): **abnormal turnover
  NEGATIVELY predicts returns; a low-abnormal-turnover long leg earns +1.24%/mo, t=3.35 (EW), turnover
  254%** ([ScienceDirect S0927538X21001141](https://www.sciencedirect.com/science/article/pii/S0927538X21001141)).
  "Turnover premia in China's stock markets" documents a turnover premium
  ([S0927538X20306995](https://www.sciencedirect.com/science/article/abs/pii/S0927538X20306995)).
  "Stable Turnover Momentum Enhanced by Idiosyncratic Volatility" (CSI300/CSI1000, 2019–2024) shows
  turnover-*stability* + IVOL enhances momentum survivably under daily costs
  ([ResearchGate 391504090](https://www.researchgate.net/publication/391504090)).
- **Data required.** Per-name daily volume + shares-outstanding (for turnover ratio) OR volume-z as a
  proxy.
- **Do WE have it?** YES — `china_stocks_raw` (volume, 1,495/1,495 coverage, deep history, verified
  above). Turnover ratio needs float shares; volume-z is a clean fallback that needs nothing else. The
  ADV screen the board already applies (`CHINA_ENGINE_REASSESSMENT.md:255`, median ADV 4.5亿) proves we
  can compute rolling volume today.
- **Frequency + decay.** Daily; short decay (days–weeks), same family as reversal.
- **Failure modes.** Correlated with the existing reversal factor (~10σ pairwise-corr elevation on the
  bounce-timing latent factor, `CHINA_ENGINE_REASSESSMENT.md:255`) → test orthogonality before fusing.
  Break-even transaction cost is high (turnover 254%). T+1 taxes it ~1pp/entry. High-abnormal-turnover
  names include limit-up froth → interacts with the (dead) continuation signal.
- **Repo status.** UNTESTED as a standalone leg; the registry has no `turnover_shape` entry. Buildable
  with data we already have. **This is the highest-EV × highest-buildability new item.**

### B. MAX / lottery effect — as an AVOID screen  ★ HIGH (cheap, buildable, defensive)

- **Mechanism.** Retail lottery demand overprices stocks with a recent extreme daily gain; high-MAX
  names carry a *negative* forward premium. Used as a *screen to exclude*, not a long leg.
- **A-share evidence.** Documented and robust in A-shares: long-high/short-low MAX yields significant
  **negative** monthly returns ≈ **−0.66% to −1.03%/mo**; strongest in most-overpriced groups
  ([tandfonline 2175471](https://www.tandfonline.com/doi/full/10.1080/23322039.2023.2175471),
  [SIAM.000608](https://crimsonpublishers.com/siam/pdf/SIAM.000608.pdf)). Important A-share nuance:
  **"MAX is not the max under the interference of daily price limits"** — the ±10%/±20% limit truncates
  MAX, so a raw MAX must be limit-aware
  ([S1059056021000149](https://www.sciencedirect.com/science/article/abs/pii/S1059056021000149)).
- **Data required.** Per-name daily returns (max daily return over trailing month). Close-only suffices.
- **Do WE have it?** YES — trivially, from either the close panel or raw. No new data.
- **Frequency + decay.** Monthly formation, ~1-month horizon.
- **Failure modes.** Price limits truncate MAX (must exclude/limit-flag ±9.5%+ days — we already flag
  `|ret|>9.5%` per `CHINA_STOCKS_OVERHAUL.md:35`). Correlated with IVOL. As an *avoid* screen it only
  helps if it de-selects names the reversal signal would otherwise buy (a deep-dip name that had one
  limit-up spike) — measure the overlap first.
- **Repo status.** Not in the registry. **Best use = negative screen layered on the reversal pool**
  (removes lottery-froth from the deep-dip buy list). Cheap, defensive, buildable today.

### C. Volume-price divergence at bottoms  ★ MEDIUM (buildable, but adjacent thesis is dead)

- **Mechanism.** A washed-out name where price makes a lower low but volume does NOT confirm (selling
  exhaustion) is the classic capitulation-bottom read.
- **A-share evidence.** Indirect: A-shares overreact to bad news / negative-return days
  ([alphatalon substack](https://alphatalon.substack.com/p/two-markets-one-narrative-and-a-structural)),
  which is the reversal mechanism. No clean A-share paper isolates *bottom volume divergence* as a
  standalone cross-sectional edge in what I found.
- **Data required.** Per-name volume + price. **We have it** (`china_stocks_raw`).
- **Frequency + decay.** Daily; timing-overlay horizon.
- **Failure modes.** **The closest already-tested cousins are DEAD:** "volume dry-up" and "quiet base"
  filters were FALSIFIED (§1), and turn-confirmation HURTS the reversal edge
  (`CHINA_HK_STOCK_SIGNALS.md:109`). So a *confirmation*-flavoured volume read is likely a precision
  drain. The only non-dead framing is exhaustion *at the dip itself* (not a bounce confirmer) — must be
  designed to be the feature that "isn't already dead" (`..._PIPELINE_...:305`).
- **Repo status.** UNTESTED in the surviving framing; adjacent framings falsified. MEDIUM — build only
  as a dip-exhaustion feature, forward-ledger first, and expect it may fail.

### D. Deep-DISCOUNT block trades  ★ ALREADY-VALIDATED (accruing) — surface it, don't re-derive

- **Mechanism.** An off-market block sold at a *deep discount* (≤−15%) is a motivated institutional
  handoff to a strategic buyer at a washed-out price — a leading accumulation tell orthogonal to price.
- **Evidence.** Measured **+3.45%/21d fill-realistic, t≈3.4 (669 obs)** — best northbound replacement
  (`china_altdata.py:250`, `CHINA_ENGINE_REASSESSMENT.md:205,211`). 22,472 events fetched
  2025-01→2026-06; deeply backfillable free via akshare.
- **Data.** `data/china_block_trades/detail.parquet` — LIVE, `avg_premium_pct`/`block_amt_yi` present,
  fresh to 07-01 (probe output above).
- **Frequency + decay.** Daily events; ~21d horizon.
- **Failure modes.** Single-regime sample; sign evidence not sizing evidence; the *premium* side of the
  same feed DRAINS (−0.60%/5d) so it must be sign-split. Survivorship caveat.
- **Repo status.** VALIDATED, probationary, ZERO score weight pending ledger. **Action = keep accruing,
  then promote when the forward ledger matures — not new research.**

### E. LHB institutional-seat net-buy (龙虎榜 seat intelligence)  ★ ALREADY-VERDICTED — sign-split

- **Mechanism.** The Dragon-Tiger board publishes the top-5 buy/sell *seats* on abnormal-move names.
  Institutional (机构专用) seats accumulating = smart-money tell; hot-money (游资) seats = chasers.
- **Evidence (already measured, do NOT re-recommend naively).** **Raw LHB flag on dip names DRAINS:
  −1.43%/21d, cluster-t≈−2.2 (931 obs).** Inst-seat net-buy (≥2 seats): **+1.57%/21d, t≈0.8
  (140 obs)** — weak-positive, never negative, probationary (`CHINA_ENGINE_REASSESSMENT.md:205`,
  `china_altdata.py:270-290`). External: LHB/seat evidence is thin academically; the "up-limit herding /
  leading-stock" literature shows chasing consecutive boards earns *negative* abnormal returns post-2020
  reform ([S1544612320317232](https://www.sciencedirect.com/science/article/abs/pii/S1544612320317232)).
- **Data.** `data/china_lhb/{detail,events}.parquet` — LIVE (`inst_net_buy_yi`, `n_inst_buy`, `reasons`,
  fresh to 07-01). 21,008 seat events backfilled 2024-07→2026-06.
- **Frequency + decay.** Daily; ~21d, but fires AFTER the move (structural lag) → confirmer at best.
- **Failure modes.** LHB is by construction lagging (a name only appears after an abnormal move) → it
  anti-correlates with a "buy before the bounce" thesis (`CHINA_ENGINE_PROBLEM_BRAINSTORM.md` §8-#4,
  confirmed). Raw flag = DEMOTION; only the inst-seat *positive* leg is a weak accrual candidate.
- **Repo status.** VERDICTED. **Raw LHB → demotion; inst-seat → weak probationary confirmer.** No new
  research; grade the accruing ledger.

### F. Lianban / limit-up ladder continuation (连板)  ★ FROTH-VETO ONLY (buy-side dead)

- **Mechanism.** 连板 (consecutive limit-ups) is the retail momentum-chasing ladder; first-board vs
  multi-board and open-limit ("炸板"/failed-seal) fades are the day-trader's core reads.
- **Evidence.** Our own: **continuation is ~entirely UNCAPTURABLE** for a close-to-close/T+1 taker —
  naive dip+ZT +1.74%/5d → +0.04% fill-realistic, −1.16%/21d (`CHINA_ENGINE_REASSESSMENT.md:107,199`);
  the premium sits in the locked first session. External: post-2020 reform, main-board consecutive-board
  leading stocks show **significant NEGATIVE abnormal returns**
  ([S1544612320317232](https://www.sciencedirect.com/science/article/abs/pii/S1544612320317232)).
- **Data.** `data/china_zt_pool/pool.parquet` has `consec_boards`, `seal_fund_yi`, `failed_seals` —
  BUT only **3 dates** (06-30..07-02); it is a snapshot-overwrite drip, **not append-only**
  (`CHINA_ENGINE_REASSESSMENT.md:117-121`). So we can read *today's* ladder but cannot backtest it
  ourselves without first making the store append-only.
- **Frequency + decay.** Daily, extremely short retention (the whole edge is intraday-fill).
- **Failure modes.** Limit-up unfillability (locked seal → zero retail fill); the open-limit fade needs
  intraday data we don't have; reflexivity (everyone chases the same board). **T+1 makes the buy-side
  literally unbuyable when sealed.**
- **Repo status.** Buy-side DEAD. **Only surviving use: a chase-VETO / froth thermometer** (don't buy a
  reversal name that's simultaneously on a hot 连板 ladder) — and even that needs the store made
  append-only first. Do NOT wire a veto to a one-day cache (`CHINA_ENGINE_REASSESSMENT.md:121`).

### G. Margin-balance velocity (融资余额)  ★ VALIDATED as a RISK/regime leg (not a positive)

- **Mechanism.** Surging market-wide margin financing = retail leverage euphoria → fire-sale fragility;
  the 2015 crash mechanism. Contrarian RISK, not a demand positive.
- **Evidence.** External is definitive on the mechanism: leverage-induced fire sales drove the 2015
  crash; margin debt rose ~0→3T RMB (4.5% GDP) into the peak then collapsed
  ([NBER w25040](https://www.nber.org/system/files/working_papers/w25040/w25040.pdf),
  [NBER digest](https://www.nber.org/digest/nov18/leverage-fire-sales-and-2015-chinese-stock-market-crash)).
  Our own: margin-euphoria is a SCORED de-risk regime leg (`china_signal_lab.py:113`); **per-name margin
  velocity is UNTESTED** and the local per-name cache holds one day (`CHINA_ENGINE_REASSESSMENT.md:211`,
  item 3 — "top follow-up"). Aggregate margin velocity vs fwd-CSI300 = +0.035 (dead as a timing leg).
- **Data.** Market: `china_margin/balance.parquet` (daily, 2010→07-01, deep). Per-name:
  `china_margin_detail/detail.parquet` — **MONTHLY** (06-30 vs prior 06-01), thin; needs ~250 akshare
  calls/yr/exchange to backfill a daily per-name series.
- **Frequency + decay.** Market series daily; per-name monthly (slow positioning read).
- **Failure modes.** Wrong-sign if used as a positive; crowding is a tail-risk not a timer; per-name
  detail too infrequent to time entries.
- **Repo status.** Market-level VALIDATED (de-risk). Per-name velocity = the **top untested follow-up**
  but needs a daily backfill first; treat as RISK ordering, not a buy leg.

### H. THS concept-rotation half-life / theme breadth thrust  ★ MEDIUM (data live, short retention)

- **Mechanism.** A-share themes (概念板块) rotate on policy/attention with short half-life; a breadth
  *thrust* (share of theme members reclaiming a fast MA, dispersion compressing) is an early-rotation
  feeder — the owner's verbal "many members washed out and starting to tick up together"
  (`..._PIPELINE_...:299-306`, design D2).
- **Evidence.** External: A-share industry/theme rotation is documented **short-term and reversal-prone**
  ([atlantis-press 125972430](https://www.atlantis-press.com/article/125972430.pdf),
  [alphatalon](https://alphatalon.substack.com/p/two-markets-one-narrative-and-a-structural)); investors
  are "compensated more quickly for reading policy/liquidity/crowd psychology than long-term
  fundamentals." Our own: the **global AI-semis→CN-CPO weekly slice confirmer is VALIDATED (t=3.27)**
  but ORPHANED (`CHINA_ENGINE_REASSESSMENT.md:43,259`) — proof a theme-slice edge exists at the weekly
  unit.
- **Data.** THS concept baskets (curated, `china-ths-concept-baskets` in memory); per-name volume/price
  for breadth-thrust (`china_stocks_raw`); `LIMIT breadth` (`china_flows/limit_breadth.parquet`, 27d) as
  a market-wide speculation thermometer.
- **Frequency + decay.** Daily-to-weekly; short half-life (the retention is the risk).
- **Failure modes.** THS truncated-scrape fabricates removals (`ths-truncated-scrape` memory); themes
  overlap/double-count; a *breadth-thrust* feeder must be the surviving early-turn feature, not the
  falsified dry-up/quiet-base one; retention decays fast so it's a timing feeder not a holding.
- **Repo status.** The weekly AI-semis slice is VALIDATED-but-unwired (wire it, don't re-derive). The
  general breadth-thrust feeder is proposed (D2) and UNTESTED — MEDIUM, validate as a theme-return lead.

### I. Sector-rotation lead: credit impulse → cyclicals + policy-window seasonality  ★ MEDIUM (macro-slow)

- **Mechanism.** China credit impulse (TSF) leads cyclicals/industrial-metal-exposed sectors; the
  policy calendar (Two Sessions in March, CNY/February) creates seasonal windows.
- **Evidence.** External: credit impulse hits **Chinese industrial metals FIRST** (copper/zinc/lead
  co-move most), broader growth-sensitive assets lag ~4–5 quarters
  ([EBC](https://www.ebc.com/forex/when-beijings-credit-taps-open-commodity-markets-listen),
  [seekingalpha zinc](https://seekingalpha.com/article/4340896)). Seasonality: **February
  turn-of-year / CNY holiday effect is the strongest calendar anomaly**
  ([IMF WP0604](https://www.imf.org/external/pubs/ft/wp/2006/wp0604.pdf),
  [S1544612321002919 mood seasonality](https://www.sciencedirect.com/science/article/abs/pii/S1544612321002919)),
  which is exactly WHY momentum is measured "**ex-February**" (see §J). Our own: credit impulse is a
  SCORED regime leg already (`china_signal_lab.py:105`).
- **Data.** `china_credit/tsf.parquet` (monthly, ~2mo lag); sector indices (`china_sectors`,
  `china_sector_cycles`); event calendar / policy watch (`china_policy`, `china_earnings`).
- **Frequency + decay.** Monthly/quarterly (macro-slow); multi-quarter lead → SIZING/tilt, not entry.
- **Failure modes.** ~2-month publication lag on TSF; credit-impulse→equity lead is noisy and
  regime-dependent; "Two Sessions" as a discrete tradable window is weakly evidenced (I found strong CNY
  evidence but no clean Two-Sessions premium paper) — flag as HYPOTHESIS, not validated.
- **Repo status.** Credit impulse VALIDATED (regime). Sector-lead application UNTESTED at the
  sector-rotation unit; seasonality is a known-modulator, not a standalone edge. MEDIUM, slow.

### J. 52-week-high momentum (ex-February)  ★ LOW (EM-weak; already effectively dead)

- **Mechanism.** Anchoring: names near their 52w-high underreact to good news → drift up (George-Hwang).
- **Evidence.** External is DISCOURAGING for EM: **"the 52-week-high strategy is unprofitable in
  emerging-market indices and significantly less profitable than momentum"**
  ([S106297690700021X](https://www.sciencedirect.com/science/article/abs/pii/S106297690700021X)). The
  China-specific paper is **"February, share turnover, and momentum in China"**
  ([S0927538X23002445](https://www.sciencedirect.com/science/article/abs/pii/S0927538X23002445)) — i.e.
  A-share momentum is contaminated by February/turnover, which is why the overhaul doc says "ex-February"
  (`CHINA_STOCKS_OVERHAUL.md:33`). Our own: cross-sectional momentum is KILLED on deep history (§1).
- **Data.** Close panel (52w-high proximity) — we have it.
- **Failure modes.** Momentum is dead on A-shares (killed leg); 52w-high is EM-weak; February distortion.
- **Repo status.** Effectively subsumed by the killed-momentum verdict. LOW — do not build as a
  standalone edge; at most a context chip.

### K. ETF creation/redemption + southbound as flow proxies (northbound dead)  ★ LOW-MEDIUM

- **Mechanism.** With northbound dead, ETF share creations (national-team / broad demand tell) and
  southbound net flow are the surviving cross-border/flow proxies.
- **Evidence.** Our own: **northbound CONFIRMED DEAD** (last-60 `net` all NaN, my probe;
  `CHINA_ENGINE_REASSESSMENT.md:211`). **Southbound LIVE** but sign-unstable/dead as a timing leg
  (train −0.16/test +0.49; fwd-CSI300 z +0.022). ETF create/redeem is "most orthogonal but no history
  before 2026-06-13, not backfillable, current gauge sums unit-incommensurable share counts"
  (`CHINA_ENGINE_REASSESSMENT.md:211,243`).
- **Data.** `china_flows/etf_shares.parquet` (LIVE, 20d, moving — 510300 28.6B→18.4B); `china_connect/
  southbound.parquet` (LIVE); `northbound.parquet` (DEAD).
- **Failure modes.** ETF gauge units are meaningless as-is (fix to net-creation-value); ~1y accrual
  needed; southbound is arguably wrong-sign for A-shares in substitution regimes.
- **Repo status.** ETF = fix units + accrue (LOW-MED, most orthogonal); southbound = reject as timing.

### L. QVIX / vol regime (anti-leverage, inverted vs US)  ★ VALIDATED as regime overlay (not selection)

- **Mechanism.** A-shares show a POSITIVE return-volatility correlation (anti-leverage): a high QVIX is
  NOT a fear-bottom. Use `qvix_z` inverted — panic-spike (z>+2) → halt chases; suppressed (z<−1) →
  size-up. The GEX-analog (no per-stock options in A-shares).
- **Evidence.** External: **"a positive return-volatility correlation … the anti-leverage effect … the
  Chinese market is the unique one with an anti-leverage effect, positive up to 10 days"**
  ([arxiv 1511.01824](https://arxiv.org/pdf/1511.01824),
  [arxiv 1202.0342](https://arxiv.org/pdf/1202.0342)); positive volatility risk premium predicts returns
  ([S1062976923000789](https://www.sciencedirect.com/science/article/abs/pii/S1062976923000789)). This
  validates the overhaul doc's inversion premise (`CHINA_STOCKS_OVERHAUL.md:29`). **My own-data check was
  underpowered: on 510300.SS a crude 5d-realized-vol proxy gave corr(ret_t, dVol_t)=+0.006 (near-zero,
  inconclusive) — I do NOT claim this confirms anti-leverage; the external literature does.**
- **Data.** `china_qvix/qvix300.parquet` + `qvix50.parquet` (2019→2026-06-26, **4td stale**).
- **Failure modes.** QVIX only goes back to 2019 (short); it's a MARKET regime not a name selector;
  staleness (fix the collector). It is an overlay/tax, never a stock picker.
- **Repo status.** VALIDATED direction (external); wired-ish as a vol-regime overlay. Keep as regime
  tax/size dial. Fix the 4-day staleness.

### M. Catalyst legs from existing stores (policy / events / guidance)  ★ MIXED — one live positive

- **Mechanism.** Post-catalyst drift: which catalyst types show documented A-share drift?
- **Evidence & data (per store):**
  - **Earnings-guidance surprise (业绩预告):** our own `china_validation` finds a **real ~3-month forward
    drift, accruing toward proven** (`china_signal_lab.py:171-174`). Data: `china_analyst/forecast.parquet`
    (2,776 names, LIVE). **This is the most promising catalyst leg — a genuine A-share PEAD analog.**
  - **Buybacks (回购):** insider-conviction / valuation-floor confirmer; display-tier, no forward edge
    proven (`china_signal_lab.py:188`). Data: `china_buyback/buyback.parquet` (5,226 rows, LIVE).
  - **Broker gold-stock picks (券商金股):** discrete conviction, display-only
    (`china_signal_lab.py:167`).
  - **Policy watch / news tone:** `china_policy/intel.json`, `china_news/*_tone.parquet` — context; the
    news_sentiment family has a validation harness (`china_signal_lab.py:34`). No clean per-name drift
    measured.
- **Frequency + decay.** Guidance = event-driven, ~3mo drift; buyback = slow; policy/news = fast-decay.
- **Failure modes.** Guidance direction × magnitude must be sign-clean; A-share sell-side is ~97% "buy"
  so consensus level is near-useless (`china_signal_lab.py:141`); news RSS cache masks scrape fixes
  (memory); policy is regime-context, not per-name.
- **Repo status.** Guidance-surprise = accruing/validating (PROMOTE candidate). Buyback/broker/news =
  context. **The catalyst type with documented A-share drift = earnings-guidance surprise.**

---

## 3. Ranked list — EV × buildability-with-our-data

| # | Signal | EV | Buildable now? | Status | Unit |
|---|---|---|---|---|---|
| 1 | **Abnormal-turnover / turnover-shape** (§A) | high | YES (raw volume, 1495/1495) | **UNTESTED — build** | name/day |
| 2 | **Deep-discount block trades** (§D) | high | YES (live store) | VALIDATED +3.45%/21d, accruing | name/event |
| 3 | **Earnings-guidance surprise drift** (§M) | med-high | YES (live) | validating, real ~3mo drift | name/event |
| 4 | **MAX/lottery AVOID screen** (§B) | med (defensive) | YES (close-only) | UNTESTED — cheap screen | name/month |
| 5 | **Per-name margin velocity** (§G) | med | needs daily backfill | UNTESTED (top follow-up) | name (risk) |
| 6 | **THS theme breadth-thrust / AI-semis slice** (§H) | med | AI-semis YES (wire it) | slice VALIDATED t=3.27, orphaned | theme/week |
| 7 | **Volume-price divergence at dip** (§C) | med | YES (raw volume) | UNTESTED; adjacent framings DEAD | name/day |
| 8 | **Credit-impulse→cyclicals + seasonality** (§I) | med | YES (slow) | credit VALIDATED (regime); app untested | sector/month |
| 9 | **QVIX anti-leverage vol regime** (§L) | med | YES (fix staleness) | VALIDATED direction (external) | market |
| 10 | **Inst-seat LHB net-buy** (§E) | low-med | YES (live) | weak-positive, probationary | name/event |
| 11 | **ETF create/redeem flow** (§K) | low-med | fix units + accrue | most orthogonal, no history | market/sector |
| 12 | **52w-high momentum ex-Feb** (§J) | low | YES | EM-weak; momentum killed | name (context) |
| — | **Raw LHB flag** (§E) | NEG | — | DEMOTION (−1.43%/21d) | veto |
| — | **Block PREMIUM leg** (§D) | NEG | — | DEMOTION (−0.60%/5d) | veto |
| — | **Lianban continuation as BUY** (§F) | dead | store not append-only | froth-VETO only | veto |
| — | **Northbound flow** (§K) | dead | store NaN | CONFIRMED DEAD | — |
| — | **Southbound / A-H / margin-agg as TIMING** | dead | live but ≈0 IC | KILLED as timing | — |
| — | **X-sectional momentum / value / acceleration** | dead | — | KILLED | — |
| — | **Volume dry-up / quiet base** | dead | — | FALSIFIED (H4) | — |
| — | **Turn-confirmation / quality floor on reversal** | dead | — | FALSIFIED (flips edge neg) | — |

---

## 4. Structural failure modes that tax EVERY candidate (do not re-derive per-signal)

1. **T+1 + limit-up fill haircut.** Close-to-close overstates a realistic T+1 (H+L)/2 fill by
   ~0.9–1.1pp/entry and ~2pp hit (5,393 events); truly unfillable (locked-limit all day) only 0.22% of
   entries; buy-the-T+1-high worst bound −3.1pp/−10pp (`CHINA_ENGINE_REASSESSMENT.md:63,199`). Survivable
   for a basket, fatal for limit-up chasing.
2. **Survivorship is MAXIMALLY destructive to reversal-family signals specifically** —
   `china_search` *retroactively deletes* dropped names' history columns each run, deleting exactly the
   deep-decliner failures these signals buy; all `china_search`-based stats are UPPER BOUNDS
   (`CHINA_ENGINE_REASSESSMENT.md:85`). Build volume signals off `china_stocks_raw` (append-only, 2008→)
   not the trimmed panel.
3. **Adjusted-close seams bias rev_z seasonally** (combine_first merges; div-payers look ~div-yield more
   beaten-down) — `CHINA_ENGINE_REASSESSMENT.md:93-97`. Any price-plane signal inherits this until the
   raw+adjusted full-overwrite contract lands.
4. **Reflexivity / capacity.** Post-#791 the board tier is median ADV 4.5亿 (~US$60M), not fragile nano;
   the binding constraint is fill-TIMING crowding at the entry bar, not market impact
   (`CHINA_ENGINE_REASSESSMENT.md:263`). Basket/periodic-rebalance framing mitigates.
5. **The edge is a BASKET, not an act-now single name.** Every confirmation gate flips reversal negative;
   the only validated selection edge is a monthly-rebalanced EW-relative small-per-name basket
   (`CHINA_ENGINE_REASSESSMENT.md:231`). The current daily board overlaps the validated edge 1/110 — the
   acted-on surface and the validated edge are ~orthogonal sets (`CHINA_ENGINE_REASSESSMENT.md:187`).
6. **The forward grader is structurally dead** (reads store group 'china' = 30 ETFs; 0/120 board tickers
   resolve; n_graded=0 forever — `CHINA_ENGINE_REASSESSMENT.md:9`). Any "promote when the ledger matures"
   plan is blocked until the grader is fixed. **Fix the grader before closing any loop.**

---

## 5. Honest limitations of THIS research

- **No new backtests were run.** Every effect size is quoted from a prior in-repo artifact or an
  external paper. My contribution is the mapping (external evidence ↔ our data ↔ verdict) + the
  data-inventory verification, not fresh IC/Sharpe numbers.
- **My own-data QVIX anti-leverage check was underpowered and INCONCLUSIVE** (corr ≈ +0.006 on a crude
  5d proxy) — I rely on the external literature for that direction, not my own probe.
- **The abnormal-turnover +1.24%/mo, MAX −0.66..−1.03%/mo, credit-lead 4–5q, guidance ~3mo-drift figures
  are EXTERNAL** (or, for guidance, in-repo-validating) — none has been reproduced by me on our panel.
  They justify *building and testing*, not deploying.
- **Fallback data note:** all data files read were present in the worktree at
  `.../lucid-knuth-523979/data/`; I did NOT need the main-checkout fallback. No writes were made.
- **ZT_POOL depth (3 days) and per-name margin (monthly) mean two named signals (§F, §G) cannot be
  self-validated from our current stores** without a collector change (append-only / daily backfill).

---

## Sources (external)

- MAX / lottery, A-share: [tandfonline 2175471](https://www.tandfonline.com/doi/full/10.1080/23322039.2023.2175471), [SIAM.000608](https://crimsonpublishers.com/siam/pdf/SIAM.000608.pdf), [MAX-under-price-limits S1059056021000149](https://www.sciencedirect.com/science/article/abs/pii/S1059056021000149)
- A-share anomalies / abnormal turnover / reversal: [Anomalies in the China A-share market S0927538X21001141](https://www.sciencedirect.com/science/article/pii/S0927538X21001141), [Turnover premia S0927538X20306995](https://www.sciencedirect.com/science/article/abs/pii/S0927538X20306995), [Stable Turnover Momentum + IVOL 391504090](https://www.researchgate.net/publication/391504090), [Short-term reversal & liquidity S1544612322004251](https://www.sciencedirect.com/science/article/pii/S1544612322004251)
- Limit-up herding / consecutive boards: [Up-limit herding & reform S1544612320317232](https://www.sciencedirect.com/science/article/abs/pii/S1544612320317232), [ChiNext price limits PMC10289463](https://pmc.ncbi.nlm.nih.gov/articles/PMC10289463/)
- Margin / 2015 fire sales: [NBER w25040](https://www.nber.org/system/files/working_papers/w25040/w25040.pdf), [NBER digest](https://www.nber.org/digest/nov18/leverage-fire-sales-and-2015-chinese-stock-market-crash)
- Seasonality (CNY/February): [IMF WP0604](https://www.imf.org/external/pubs/ft/wp/2006/wp0604.pdf), [Mood seasonality S1544612321002919](https://www.sciencedirect.com/science/article/abs/pii/S1544612321002919), [February/turnover/momentum S0927538X23002445](https://www.sciencedirect.com/science/article/abs/pii/S0927538X23002445)
- Anti-leverage / return-vol correlation / QVIX: [arxiv 1511.01824](https://arxiv.org/pdf/1511.01824), [arxiv 1202.0342](https://arxiv.org/pdf/1202.0342), [VIX & VRP in China S1062976923000789](https://www.sciencedirect.com/science/article/abs/pii/S1062976923000789)
- Credit impulse → cyclicals/metals: [EBC](https://www.ebc.com/forex/when-beijings-credit-taps-open-commodity-markets-listen), [SeekingAlpha zinc](https://seekingalpha.com/article/4340896)
- 52-week high (EM-weak): [52wk-high international indexes S106297690700021X](https://www.sciencedirect.com/science/article/abs/pii/S106297690700021X), [George-Hwang SSRN 1104491](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1104491)
- Theme rotation short-term: [Industry rotation 125972430](https://www.atlantis-press.com/article/125972430.pdf), [alphatalon substack](https://alphatalon.substack.com/p/two-markets-one-narrative-and-a-structural)
