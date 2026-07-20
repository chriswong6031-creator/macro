# Site Semantics: china.html

China A-share macro regime dashboard. Template: `templates/china.html.j2` (mode `macro`).
Computing engine: `scripts/build_china.py`.

---

### Market State Score (hero)

- **Shown as:** A 0–100 gauge with a needle; numeric score next to a verdict word: "Risk-on", "Mixed", or "Risk-off". ZH: 市场状态分 with 风险偏好 / 混合 / 避险.
- **Means:** A composite read of the A-share market's current posture — green (risk-on, trend-following supported), yellow (mixed, trade smaller), red (risk-off, defend capital first). It blends trend, volatility, breadth, liquidity, and drawdown-risk legs. It is display-only telemetry and never feeds the scored path.
- **Computed by:** `engine/market_state.py` `market_state_snapshot` via `engine/market_state_cn.py` `CN_PROFILE`. Legs weighted (trend 0.24, risk 0.18, vol 0.16, breadth 0.16, liquidity 0.14, stress 0.12). Raw score renormalized over resolved legs; forced into band by overrides. Score 0–100.
- **So what:** Green = trend-follow and add on strength; yellow = size smaller and watch for resolution; red = defend capital, reduce risk first. This is a present-state read, not a forecast.

---

### Regime Quadrant Pill (hero)

- **Shown as:** A small pill in the hero, e.g. "Goldilocks · early" or "Stagflation · mid". ZH: 金发姑娘 · 早期.
- **Means:** The growth × inflation quadrant the A-share macro backdrop sits in, with a cycle position tag. Q1 Goldilocks = growth up, inflation falling; Q2 Reflation = both up; Q3 Stagflation = growth falling, inflation up; Q4 Growth-scare = both falling. The cycle tag (early/mid/late) places the regime within its current leg.
- **Computed by:** `engine/regime.py` `raw_quad` (growth score ≥0 vs <0, inflation score ≥0 vs <0, both z-scored axes); `apply_hysteresis` requires a new quad to hold `hysteresis_days` consecutive days or a shock-override. Quad names from `QUAD_NAMES`.
- **So what:** Use for which sectors and factors are favoured structurally, not for market timing. Shifts slowly (days to weeks). The market state score beside it is the faster, tape-level read.

---

### 11-Session Path Chart (hero)

- **Shown as:** A line chart showing the market state score over the last 11 trading sessions, right panel of the hero. ZH: 11交易日走势.
- **Means:** Recent trend of the composite market-state score — whether the A-share posture has been improving or deteriorating over the past two weeks.
- **Computed by:** `scripts/build_china.py` `ms_history` key (assembles the last 11 rows from the persisted score_log; the template maps score 0–100 to SVG y-axis 22–190, inverted). Score values produced by `engine/market_state_cn.py` `_cn_risk` and sibling leg functions, fused by `engine/market_state.py` `market_state_snapshot`.
- **So what:** A rising path towards green = a regime improving in real time; a falling path into red = conditions deteriorating. Context only — do not act on a single-session move.

---

### Pullback Risk Radar (hero button / popover)

- **Shown as:** "Pullback risk · [score]" button in the hero, expanding to a popover with a score /100 and per-scare-type bars. ZH: 回撤风险.
- **Means:** A calibrated leading-risk signal measuring the probability of a ≥5% pullback within the next ~21 sessions. Sub-scores measure credit stress, rates shock, bubble unwind, growth scare, volatility event, and global breadth breakdown, then fused. An "elevated" or "risk-off" state fires a loud banner.
- **Computed by:** `engine/risk_radar_intl.py` `snapshot` and `CN_PROFILE` (CN-market profile); wired via `engine/market_state.py` `_radar_override_intl`. Calibrated P(≥5% pullback, 21 sessions) from A-share history: calm ~27%, watch ~32%, caution ~35%, elevated ~40%, risk-off ~50%. Base rate ~30.5% (h21, from CN_PROFILE). These are per-market CN calibration values; the US radar uses different odds.
- **So what:** Elevated/risk-off = take the alert seriously, size down, protect open gains. The signal is loud-and-early by design: it fires before the pullback starts, so some alerts precede moves that don't materialize. Read every alert alongside its stated lift.

---

### What To Do Card (row 1)

- **Shown as:** A card labeled "What To Do" (该怎么做) with a posture dial word (Defensive / Careful / Neutral / Constructive / Aggressive) and bullet reasons.
- **Means:** The playbook-derived trading posture for the current China regime — how aggressive or defensive to be with position sizing and new entries.
- **Computed by:** `scripts/build_china.py` via `engine/china_playbook.py` `build`. Dial label and reasons list stored in the playbook dict under the `dial` key. The playbook reads the regime quad and risk state.
- **So what:** The posture sizes risk, not selections. "Careful" = favour quality entries, keep gross moderate. "Constructive" = lean into setups with regime support. It does not tell you which stocks to buy.

---

### Market Tiles — SSE / CSI300 / ChiNext / Hang Seng (row below hero)

- **Shown as:** Four price tiles showing index level and day change for Shanghai Composite (000001.SS), CSI300 ETF (510300.SS), ChiNext ETF (159915.SZ), and Hang Seng Index.
- **Means:** Glance-tier price tiles for the four major A-share and HK benchmarks, updated each build from the OHLC store.
- **Computed by:** `scripts/build_china.py` `_china_market_tiles` — reads the OHLC store for each symbol; day change and percent are last close vs prior close.
- **So what:** Quick orientation — are the main indexes up or down today? Do not use single-day moves to override the regime or risk-radar read.

---

### Board Track Record Strip — "Beating CSI300 so far" (china_stocks mode, track-record panel)

- **Shown as:** "Beating CSI300 so far: 67% CI 63–70%, Median excess +3.8%, n=660" (ZH: 暂时跑赢沪深300). Also a matured 21d read: "Hit vs CSI300 (21d): XX% CI …".
- **Means:** Of all board picks that have been logged and had a forward return measured so far, this share beat the CSI300 index (510300.SS) on a CSI300-relative, fill-realistic basis. The CI is a Wilson 95% confidence interval on the hit rate. Median excess is the median per-pick CSI300-relative outperformance in percentage points. n is the count of graded picks (unrealized marks included for the "so far" strip; only matured 21d rows for the "21d" strip). This is telemetry for the board ordering, not a win-rate guarantee.
- **Computed by:** `engine/china_standout_track.py` `grade` (matured 21d strip) and `interim_grade` (unrealized "so far" strip). `hit_vs_csi300` and `hit_ci` use `_wilson_ci` (Wilson 95% CI). `median_excess` = median of CSI300-relative excess values. Benchmark = 510300.SS. Entry = T+1 mid-price proxy; `ENTRY_BASIS` and `_MIN_GRADED` control fill and minimum sample size.
- **So what:** A hit rate above 50% with a CI lower bound above 50% means the board ordering has been adding value beyond a random guess vs the index. This is evidence accruing, not a guarantee of future performance. The median excess shows whether the edge is economically meaningful. The n shows how much data is behind the number.

---

### Sector Rotation Act-Now Board (china.html macro mode, four-lane table)

- **Shown as:** Four-lane table: "Buy Now / In Favour / Bottoming Watch / Reduce & Avoid". Each lane mixes investment themes (scored 0–100 by the basket engine) and sectors (timed by the cycle ladder). ZH: 立即买入 / 看好 / 洗盘观察 / 减仓回避.
- **Means:** Where to look (and where to avoid) in the A-share universe right now. Buy Now = an entry point exists today; In Favour = still good but has run, wait for a dip; Bottoming Watch = first signs of turning up, watch only — never a buy signal; Reduce/Avoid = trend weakening. A name can appear in two lanes simultaneously when trend and timing diverge.
- **Computed by:** `scripts/build_china.py` `assemble_act_now` via `engine/china_act_now.py`. Baskets scored by `engine/baskets_china.py` `compute_china_baskets`; sectors timed by `engine/china_sector_cycles.py` `compute` cycle ladder.
- **So what:** Glance-tier action board. Use Buy Now + In Favour as the starting list for the stock screener. Bottoming Watch is speculative context. Reduce/Avoid means existing positions need a thesis review.

---

### Sector Flow Velocity (internals section)

- **Shown as:** A row of sector tiles with a flow direction chip (e.g. "accelerating in", "decelerating") and a velocity number. ZH: 资金流速度.
- **Means:** How fast capital is flowing into or out of each A-share sector, derived from ETF and composite A-share flow proxies. Acceleration = money is entering the sector faster than last week; deceleration = the inflow is slowing even if the direction is still positive.
- **Computed by:** `scripts/build_china.py` `_internals_vm` via `engine/china_internals.py` `margin_meter` and sibling flow functions. Flow velocity from `engine/china_liquidity.py` `profile`.
- **So what:** Confirms or contradicts the sector rotation read. A Buy Now sector with decelerating inflows may be near a pause. A Bottoming Watch sector with accelerating inflows may be earlier than the price signals suggest.

---

### China Setup Score on Stock Cards (china_stocks mode)

- **Shown as:** "ready 73" chip on each stock card. ZH: 就绪. Score 0–100.
- **Means:** Buy-readiness score: how close this A-share name is to an actionable entry, not a win-rate. Combines the cycle trigger (is the turn happening now?), stored upside (how washed out), distress haircut, and tailwind from sector and theme. A score of 70+ = "primed"; 45–70 = "setting up"; 25–45 = "watch"; below 25 = no setup.
- **Computed by:** `engine/name_score.py` `potential_score`. Blends trigger, fuel, survive, tailwind, confidence, and edge_mult (CN = 1.0 — no validated cross-sectional name edge; reversal edge lives in the cycle/washout trigger). Trigger gate from `_TRIGGER` dict.
- **So what:** A high score means the setup is clean and the timing looks right; it does not mean the stock will go up. Use it to rank the shortlist, not to override the cycle state or the board track record.
