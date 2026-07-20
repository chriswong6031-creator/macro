# Site Semantics: china_stocks.html

China A-share stock dashboard — washout → base → fresh-turn entry board.
Template: `templates/china.html.j2` (mode `stocks`).
Computing engine: `scripts/build_china.py` (same script, mode flag changes render path).

---

### T1–T4 Tier Cascade (stock cards, header)

- **Shown as:** A tier badge on each stock card: "T1", "T2", "T3", or "T4". In the screener table the "buy" column shows the tier label.
- **Means:** The validated confluence entry tier for this A-share name. T1 = the validated master take signal has fired on the 3D MACD × StochRSI confluence and is still fresh (the "just-crossed" trigger); T2 = the 2D MACD cross is fresh, the 3D StochRSI is constructive (confirmed, not topped); T3 = the 3D StochRSI has crossed but the 2D MACD hasn't fired yet (anticipation); T4 = 2D StochRSI only (earliest, weakest). Tier operator ranking: T2 > T1-held > T1-pending > T3 > T4.
- **Computed by:** `engine/signal_gate.py` `gate` and `blend_sorted` (the validated MACD-RSI × StochRSI confluence; validated to cut average max drawdown -23.7% → -15.5% on 110 held-out US names). `_CASCADE_RANK` dict for sort order; `BUYABLE_TIERS` constant.
- **So what:** T1/T2 = a confirmed entry window is open. T3 = get ready, not yet confirmed. T4 = context only, not a buy signal. A name only appears on the board if it passes the gate — a high-alpha leader that is downtrending is excluded regardless of momentum.

---

### Buy-Readiness Score on Stock Cards (china_stocks mode)

- **Shown as:** "ready 73" chip on each A-share stock card. Score 0–100. ZH: 就绪.
- **Means:** How close this name is to an actionable buy entry — not a win-rate. Blends the cycle trigger gate (is the turn happening now?), stored upside fuel (how washed-out the name is), a distress haircut (crowding / panic-vol subtract), tailwind from sector/theme, and a bounded confidence multiplier. A score of 70+ = "Primed" (green); 45–70 = "Setting up" (amber); 25–45 = "Watch" (neutral); below 25 = "No setup" (grey).
- **Computed by:** `engine/name_score.py` `potential_score`. Blends trigger, fuel, survive, tailwind, confidence, and edge_mult (CN = 1.0 — no validated cross-sectional name edge). `_TRIGGER` gate maps cycle state to a multiplier (0.0 for declining names, 1.0 for FRESH BUY).
- **So what:** Rank the shortlist by readiness to prioritize the cleanest entries. A high score means the pattern is set up; it does not guarantee a positive outcome. Compare against the board track record strip for context on how the board has performed historically.

---

### Board Track Record Strip — "Beating CSI300 so far" (track-record panel)

- **Shown as:** "Beating CSI300 so far: 67% CI 63–70%, Median excess +3.8%, n=660". Also separate 21d matured read. ZH: 暂时跑赢沪深300.
- **Means:** Of all picks logged on this board that have a measured return: the share that beat CSI300 (510300.SS ETF) on a fill-realistic, CSI300-relative basis. CI = Wilson 95% confidence interval on the hit rate. Median excess = median per-pick CSI300-relative outperformance in pp. n = count of graded picks. "So far" = unrealized interim marks; "21d" = matured 21-session forward graded rows only.
- **Computed by:** `engine/china_standout_track.py` `interim_grade` ("so far" row) and `grade` (21d row). `hit_vs_csi300` uses `_wilson_ci` for the Wilson 95% CI. `median_excess` is the median of CSI300-relative excess per pick. Benchmark = 510300.SS. Fill = T+1 mid-price proxy; `ENTRY_BASIS` and `_MIN_GRADED` control fill basis and minimum sample.
- **So what:** Evidence accruing. A hit rate CI lower bound above 50% means the board has added value vs random index exposure. Median excess tells you whether the magnitude matters. Use alongside n to judge how much data backs the number.

---

### Washout Chip on Stock Cards

- **Shown as:** A "Washout" chip (洗盘) on cards where the 2W StochRSI washout-reclaim pattern fired.
- **Means:** This A-share name recently experienced a sharp 2-week StochRSI washout followed by a reclaim — a pattern that historically precedes durable lows more often than a random entry. It is a category tag influencing board ranking, not a standalone buy signal.
- **Computed by:** `scripts/build_china.py` → `engine/china_reversal.py` `reversal_watch` feeds the watchlist. Stored in `engine/china_standout_track.py` `append_board` as the `washout_2w` column; determines species ("cn_washout" when it qualifies).
- **So what:** Adds context about the nature of the entry setup — a washout reclaim is typically a higher-quality entry than a name that has drifted to a low. Use as a tiebreaker when ranking similar-scored names.

---

### Entry Timing Chips: "Buy Now" / "Wait for Pullback" / "Hold"

- **Shown as:** A small chip on each stock card showing the entry timing verdict: "Buy now" (green), "Wait for pullback" (amber), "Hold" (blue). ZH: 立即买入 / 等待回调 / 持有.
- **Means:** The entry signal status from the confluence gate. "Buy now" = the T1/T2 signal is fresh and entry is open today. "Wait for pullback" = the signal is valid but the name is extended intra-entry; a small dip to the entry zone is preferred. "Hold" = already in, the position is intact.
- **Computed by:** `engine/signal_gate.py` `gate` produces the entry signal status. Maps to `engine/name_score.py` `_ENTRY_CONFIRM` (buy_now: 1.00, wait_pullback: 0.88, hold: 0.90, extended: 0.50).
- **So what:** "Buy now" means the window is open — act on a confirmed entry, not as a market order at any price. "Wait for pullback" means the opportunity exists but patience improves the risk-reward.

---

### Stage Labels: "ENTRY" / "RAN LATE" (stock cards, china_stocks mode)

- **Shown as:** A lifecycle stage label on each card: "ENTRY" (青绿) or "RAN LATE" (紫色). Absent for fresh setups.
- **Means:** ENTRY = this name is at or near the board-entry window, the cleanest stage for a position. RAN LATE = the name appeared on the board recently but has already moved substantially — the original entry window is past.
- **Computed by:** `scripts/build_china.py` → `engine/china_discovery.py` `build` populates stage assignments (W1-B rules 1–2). Stored in `engine/china_standout_track.py` `append_board` as the `stage` column.
- **So what:** Prioritize ENTRY-stage cards over RAN_LATE. A RAN_LATE card is still present because its technical picture is intact, but the risk-reward has deteriorated from the original signal.

---

### Sector Turn Boost Chip (table mode, stock screener)

- **Shown as:** A sector-turn chip (green tint, "sector turn") on table rows where the sector's first-tick-up has fired. ZH: 行业转向.
- **Means:** The sector this name belongs to has hit the first oscillator-slope positive bar at a trough (phase = Trough, osc_slope > 0 in the forward_log). This adds a row-tint bonus in the screener table to surface names that have the sector rotation tailwind as additional context. It is display-only and does not change the underlying score.
- **Computed by:** `scripts/build_china.py` via `engine/china_sector_cycles.py` `compute`. Stored in `engine/china_standout_track.py` `append_board` as `sector_turn` column (set to "bottoming" when the sector qualifies, else None).
- **So what:** A name with a sector-turn chip has a double confirmer: the individual setup AND the sector turning. Weight it as an additional filter when choosing between similar-ranked names.

---

### Coiled Cohort Chip on Stock Cards

- **Shown as:** "Coiled" chip (or star variant "Coiled ★") on cards where the cohort-washout pattern is active. ZH: 压缩蓄力.
- **Means:** This name is part of a coiled cohort — a group of names in the same sector or basket that have compressed together (low internal dispersion) following a washout. A coiled group that turns simultaneously often produces a stronger and cleaner move than isolated names.
- **Computed by:** `engine/coiled.py` `washout_ctx` and `assess` (cohort washout logic); result stored in `engine/china_standout_track.py` `append_board` as `coiled` and `coiled_star` columns. `coiled` = True triggers species "cn_coiled" (takes precedence over cn_tier if both could apply).
- **So what:** A Coiled chip alongside a T1/T2 signal is a higher-confidence setup than T1/T2 alone. The Coiled ★ variant means the setup quality is exceptionally clean within the cohort.
