# Site Semantics: us_stocks.html

US single-stock and sector signals board — Prophet signals, sector rotation, factor tilts, and regime context.
Template: `templates/dashboard.html.j2` (mode `stocks`).
Computing engine: `scripts/build_site.py`.

---

### Regime Badge (header)

- **Shown as:** "Regime: Goldilocks" badge in the stocks header. ZH: 周期: 金发姑娘.
- **Means:** The economic regime quadrant filtering the whole page — the same quad computed for the macro page. Q1 Goldilocks = growth up, inflation falling. Q2 Reflation = both up. Q3 Stagflation = growth falling, inflation up. Q4 Growth-scare/Deflation = both falling. This describes the economy, not the tape. It shifts slowly.
- **Computed by:** `engine/regime.py` `raw_quad` and `apply_hysteresis`. The `engine/run.py` `quad_name` key carries the display string; `engine/regime.py` `QUAD_NAMES` maps quad code to label.
- **So what:** Use for which sectors and factors are structurally favoured under the current macro backdrop. For whether the market itself is turning, use the macro dashboard Risk Radar, not this badge.

---

### Posture Chip (header)

- **Shown as:** "Posture: Careful" chip next to the regime badge. ZH: 姿态: 谨慎.
- **Means:** How aggressively to trade the current regime — a five-level dial: Defensive / Careful / Neutral / Constructive / Aggressive. Sizes risk exposure, not stock selection.
- **Computed by:** `engine/playbook.py` `build_playbook` via `exposure_dial`. Called in `engine/run.py` `build_playbook`. Posture stored under the `dial` key of the playbook dict; reads regime quad + market state color.
- **So what:** Defensive / Careful = lean cautious, smaller gross, favour entries with good risk-reward over chasing momentum. Constructive / Aggressive = scale into setups with regime support. The full posture dial and reasoning is on the Macro dashboard.

---

### Prophet Stock Signals Board (main section, hero card list)

- **Shown as:** A grid of stock cards under "Prophet Stock Signals" (先知选股). Each card shows the ticker, name, cycle state (BUY ZONE, BOTTOMING, TOPPING), an alpha chip (sector-neutral residual momentum rank), and entry timing dots.
- **Means:** A hard-gated, alpha-ranked shortlist of stocks from the sector ETF top-10 holdings whose price-cycle signal is decisive. A name appears only when the validated MACD-2D × StochRSI-3D confluence gate passes (T1/T2/T3 tier) AND the cycle state is a buy or bottoming state. Within the gate, names are ranked by α — the sector-neutral residual momentum (market + sector beta stripped), not by the cycle timing. The cycle state and buy-readiness score are risk-placement context.
- **Computed by:** `engine/signal_gate.py` `gate` and `blend_sorted`; alpha from `engine/stock_score.py` `_axis_selection` (US: event edge = insider net-buying 50%, analyst revisions 30%, SUE earnings surprise 10%, residual momentum 10% regime-conditional). Board ordering = cascade tier rank + conviction percentile blend. A soft per-sector cap prevents one hot sector from dominating.
- **So what:** A card on this board means the validated buy-filter is open and the name ranks high on sector-adjusted momentum. This is a research shortlist, not a buy list. Verify the entry price and the broader regime before acting.

---

### Alpha (α) Chip on Stock Cards

- **Shown as:** A chip labeled "α #3" or "α top 12%" on each stock card. ZH: 选股优势 α.
- **Means:** The name's sector-neutral residual momentum rank relative to its sector peers — market + sector beta stripped, 12-1 momentum residual. A rank of #1 means this name has the strongest alpha (beta-adjusted outperformance) within its sector ETF universe. This is the primary ordering lever for the board within each cycle-state lane.
- **Computed by:** `engine/stock_score.py` `_axis_selection` for US market. Edge weights in `_EDGE_W`: insider net-buying (0.50 — lone borderline FDR-surviving cross-sectional predictor, IC ~0.03 in mid-caps), analyst revisions (0.30 — literature-strong), SUE earnings surprise (0.10 — collapsed to near-zero IC on deep PIT panel, kept as PEAD confirmer), residual momentum (0.10 — regime-conditional: weight 0.28 in calm/risk-on tape, 0.04 in stressed tape). Alpha z-score converted to a within-sector rank.
- **So what:** Alpha is a selection filter, not a timing signal. A high alpha name with a poor entry timing (yellow dot / wait-for-pullback) means: good stock, wrong entry today. A low alpha name with great timing means: clean entry, weak selection edge. The best cards have both.

---

### Buy-Readiness / Setup Score on Stock Cards

- **Shown as:** A score chip on each card (e.g. "73") with a color band. ZH: 就绪 on the chip.
- **Means:** How ready this name looks to buy on a 0–100 scale. Blends: trigger (is the turn happening NOW — cycle state gate); fuel (how washed-out, room to recover from the 52-week high and 200-DMA); survive (distress haircut — crowding + panic-vol subtract); tailwind (bounded sector/theme tilt); confidence (bounded cone nudge); and edge_mult (the per-market validated selection edge z-score tilt). For US the edge_mult is the event-edge blend above. Score ≥ 70 = "Primed" (green); 45–70 = "Setting up" (amber); 25–45 = "Watch"; below 25 = "No setup".
- **Computed by:** `engine/name_score.py` `potential_score`. Blends trigger, fuel, survive, tailwind, confidence, and edge_mult. The 0.4 floor prevents a fresh buy with no drawdown fuel from scoring near zero. `_TRIGGER` maps cycle state (FRESH BUY=1.00, TURN SIGNALED=0.92, RALLY ON=0.70, BOTTOM WATCH=0.50, DECLINE=0.00). `_ENTRY_CONFIRM` modulates by entry timing status.
- **So what:** A high score means the setup pattern is clean. This is not a win-rate. Compare it against the alpha rank: the highest-conviction cards rank high on BOTH alpha and readiness.

---

### Insider Buy Chip (👤 chip on stock cards)

- **Shown as:** A "👤 insider buying" chip (or "N insiders") on cards where insider net-buying is detected. ZH: 内部人买入.
- **Means:** A cluster of Form-4 insider NET purchases was recently filed for this company — company insiders are buying more shares than they are selling. This is the lone borderline FDR-surviving cross-sectional predictor in the US name-selection edge (weight 0.50 in the event-edge blend, IC ~0.03 in mid-cap habitat). It is a confirmer, not a standalone alpha.
- **Computed by:** `engine/stock_score.py` `_axis_selection` (insider leg inline via `_EDGE_W`). Input field `insider_bps` (insider net-buying in basis points of market cap) z-scored cross-sectionally. Template chip fires when the insider_buyers count field is set on the card data.
- **So what:** An insider chip alongside a T1/T2 gate pass is a higher-confidence confluence. As a standalone chip without a buy-gate pass, it is context — insiders buy for many reasons and the timing advantage is modest.

---

### Entry Timing Dot (green / yellow / grey on stock cards)

- **Shown as:** A colored dot at the top of each stock card. Green = entry open ("Buy now"), yellow = "Wait for pullback", grey = "Hold / monitor". ZH: 绿点=入场窗口已开 / 黄点=等待.
- **Means:** The entry signal status from the validated confluence gate. Green (buy_now) = T1/T2 signal is fresh and the name is not extended — act on a defined entry. Yellow (wait_pullback) = the signal is valid but the current price is extended relative to the entry zone — wait for a dip back toward the trigger. Grey = the gate is not in buy_now or wait_pullback state.
- **Computed by:** `engine/signal_gate.py` `gate` produces the entry signal status. Maps to `engine/name_score.py` `_ENTRY_CONFIRM` (buy_now: 1.00, wait_pullback: 0.88, extended: 0.50).
- **So what:** A green dot is the actionable signal — it means an entry exists today at a defined level. A yellow dot means patience: the opportunity is real but the current price is suboptimal. Never chase an extended name just because the conviction is high.

---

### SUE Earnings Surprise Chip on Stock Cards

- **Shown as:** A blue chip labeled "SUE +3.2" or "beat" on cards where earnings surprise is positive. ZH: 超预期 or 业绩超预期.
- **Means:** Standardized Unexpected Earnings — how many standard deviations above analyst consensus this company's most recent earnings came in. A positive SUE means the company beat estimates; the PEAD (Post-Earnings Announcement Drift) literature suggests prices continue drifting in the surprise direction for weeks to months.
- **Computed by:** `engine/stock_score.py` `_axis_selection` (SUE leg via `_EDGE_W`); data from `collectors/edgar_eps.py` (real SEC filing dates, not synthetic). SUE = (actual EPS − consensus) / historical volatility of surprise. Cross-sectional IC on deep PIT panel (2011–2026) collapsed from 0.039 to ~0.0006 — demoted to PEAD confirmer, weight 0.10 in the edge blend.
- **So what:** SUE is display context, not a primary ranking signal. A fresh beat (filed recently) alongside a buy-gate pass is a supporting datum. A stale beat filed 90+ days ago carries little PEAD weight — the drift has already materialized.

---

### Sector Act-Now Board (confluence-gated table below cards)

- **Shown as:** A table with T1/T2/T3 columns showing sector ETFs and stocks that have passed the confluence gate, ranked by alpha within each tier. ZH: 板块动作榜.
- **Means:** The actionable setups from the gated board condensed into a table view. Only names where the MACD-2D × StochRSI-3D confluence has triggered appear. Within each tier, names sort by sector-neutral alpha (residual momentum z-score, same as the card grid).
- **Computed by:** `scripts/build_site.py` `action_board`; gating via `engine/signal_gate.py` `blend_sorted`. Cascade tier × conviction percentile blend for ordering.
- **So what:** The table view makes it fast to scan many names at once. T1 = highest-quality entry (most confirmed); T3 = anticipation only. Use the tier first, then the alpha rank within tier.

---

### Factor Seasonality Chip (header area, seasonal climate)

- **Shown as:** A chip like "July headwind: momentum fades" or "Aug tailwind: small-cap seasonality". ZH: 季节性风向.
- **Means:** A factor-seasonality read for the current calendar month, derived from 10-year and 30-year windows of sector/factor performance. A headwind chip means a historically weak month for momentum or growth factors; a tailwind chip means historical strength. This is display-only context, not a return forecast.
- **Computed by:** `scripts/build_site.py` `factor_season` chip via `engine/factor_seasonality.py` `compute_factor_seasonality`. 10-year window for the "now-block"; 30-year window for structural priors.
- **So what:** Seasonality is a weak, long-horizon bias — it can be overridden by any strong regime or risk-radar signal. Use it to add or subtract a small edge from a thesis already supported by the regime and entry timing.
