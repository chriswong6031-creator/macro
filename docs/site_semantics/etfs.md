# Site Semantics: etfs.html

Fund Flows — what the curated thematic/sector/active ETF universe is actually
buying and selling, read out of full daily holdings snapshots rather than
quarterly filings.
Template: `templates/etfs.html.j2` (+ partials `_etf_board_rows`,
`_etf_fresh_cards`, `_etf_accumulation_rows`, `_etf_trim_rows`, `_etf_macros`).
Computing engines: `engine/holdings_signals.py` (per fund-ticker decisions),
`engine/etf_consensus.py` (cross-fund roll-up), `engine/etf_board.py` (stance +
hero synthesis). Builder: `scripts/build_site.py`.

**Cadence.** Sponsors publish full holdings once a day; `collectors/etf_holdings.py`
writes one parquet per fund per date under `data/etf_holdings/<FUND>/<date>.parquet`
on the nightly collect lane. Every number on this page is recomputed from those
committed snapshots on each render — there is no intraday update, and the page's
own "as of" is the newest snapshot date across the tracked fleet, never a wall
clock. Funds do not all report on the same calendar, so the freshness column, not
the page timestamp, is what tells you whether a given fund's row is current.

**Tier.** Display-only. Nothing on this page feeds a rank, a score, a gate or a
position size anywhere else in the platform, and the forward ledger described at
the bottom of this file is read by no ranking here.

---

### The Consensus Board — "funds in" (n accumulating / n trimming)

- **Shown as:** The board's second column: an up-count and a down-count of funds, e.g. "4 ▲ · 1 ▼", with a `SPLIT` chip when both are non-zero. ZH: 参与基金.
- **Means:** How many separately-managed funds moved on the same stock inside the comparison window — the breadth of the decision, counted equal-weight. A name only reaches the board when at least two funds touched it. This is the page's PRIMARY read and it is deliberately the crudest one: a count cannot be inflated by one large fund, one large position, or one loud sponsor, which makes it the hardest number on the page to manipulate.
- **Computed by:** `engine/etf_consensus.py` `consensus_favored` groups every flagged fund decision by underlying ticker and increments `n_accum` / `n_trim` off each row's signed `conviction_pp`. The minimum fund count and the board length are `config.yml` `consensus_min_funds` and `consensus_top_n`. Rows arrive from `engine/holdings_signals.py` `all_etf_signals`.
- **So what:** Four funds adding is a different fact from one fund adding four times as much — breadth first, size second. One fund adding and one trimming (`SPLIT`) means the managers disagree; treat the name as unresolved rather than as a weak buy.

---

### Net conviction (pp)

- **Shown as:** A signed number with a `pp` suffix on each board row, plus a presence bar scaled to the board's own maximum, e.g. "+2.4pp". ZH: 净信念.
- **Means:** The sum, across every fund touching the name, of the percentage POINTS of that fund's weight the manager actively committed (positive) or released (negative). It is a share-based measure taken after flow normalization, so a position that only "grew" because the fund took in money does not count as conviction, and a whole-fund drawdown does not read as selling. A new position enters at its full weight; a full exit enters at minus its prior weight.
- **Computed by:** `engine/holdings_signals.py` `etf_signals` computes each fund-ticker `conviction_pp` from the active (flow-normalized) share change and the position's weight; `engine/etf_consensus.py` `consensus_favored` sums them into `net_conviction_pp` and the absolute sum into `gross_conviction_pp`. Thresholds live in `config.yml`: `active_change_alert_pct`, `min_position_pct`, `min_conviction_pp` and the window `active_change_window_d`.
- **So what:** Big (roughly ≥2pp net across funds) = several managers committed real fund weight, not a rounding change. Small (under ~0.5pp) = a real decision but a marginal one; the breadth count matters more than the size at that end. Net near zero with a high gross figure means the funds are trading against each other.

---

### Conviction (pp) — per fund row, "Every add, by fund"

- **Shown as:** The right-hand number on each row of the per-fund tables, e.g. "+0.8pp", with a `NEW` chip on brand-new positions and an `ACTIVE` chip on actively-managed funds. ZH: 信念.
- **Means:** The same measure as above for ONE fund's decision on one stock: percentage points of that fund's weight actively committed after flow normalization. This is the atom the consensus board sums; the tables exist so a reader can see whose decision it was, in what theme, and how large a slice of that fund it is.
- **Computed by:** `engine/holdings_signals.py` `etf_signals` (per fund) and `all_etf_signals` (whole universe); `split_by_conviction` splits the rows into the accumulation table and the smaller trims table using `config.yml` `page_top_n` and `trims_top_n`.
- **So what:** A 1pp add by a concentrated 40-holding thematic fund is a much bigger statement than 1pp from a 300-holding sector fund — read the number next to the fund's identity, never on its own. Trims are shown deliberately de-emphasised: managers sell for tax, redemption and mandate reasons far more often than for a view.

---

### Flow vs selection — which half of the move was investor money

- **Shown as:** A plain-word driver on the row detail: investor flow into the theme, versus the manager's own selection. ZH: 资金流 / 选股.
- **Means:** Two different signals that a raw share change conflates. When a fund creates or redeems units, EVERY constituent's share count moves by roughly one common factor — that is investor demand for the theme, which mechanically buys the constituents. Anything beyond that common factor is the manager choosing this name over the others. The decomposition estimates the common factor robustly (median share ratio across continuing constituents) and calls the residual selection. `driver` names whichever half is larger for that fund-ticker pair.
- **Computed by:** `engine/holdings_signals.py` `flow_selection` (the estimator) and `fund_flow_decomposition` (per fund, per snapshot pair); rolled up per ticker by `engine/etf_consensus.py` `_roll_decomposition` into `net_flow_pp`, `net_selection_pp`, `n_funds_flow` and `n_funds_selection`. Estimator settings are in `config.yml`: `flow_min_scale_n` and `flow_flat_frac`. Which half is a given fund's PRIMARY signal is decided structurally, never fitted, by `engine/etf_registry.py` `fund_registry` — `active` funds are read on selection, `thematic_passive` and `sector` funds on flow.
- **So what:** For a passive thematic fund (URA, SMH, NUKZ) the FLOW half is the meaningful signal — money arriving in the theme. For an active fund (ARKK, OZEM) the SELECTION half is the meaningful one — the manager's pick. A passive fund's "selection" is mostly index rebalancing and an active fund's "flow" is mostly marketing, so the mismatched half of any row is the noisier half. Flow and selection pointing OPPOSITE ways inside one stock (`contested_components`) is a real disagreement that the plain accumulating-vs-trimming split cannot see.

---

### Dollar estimates (total $, flow $, selection $)

- **Shown as:** Dollar figures beside the percentage-point columns, e.g. "$41M", with the same flow/selection split. ZH: 金额估算.
- **Means:** Share change × the price implied by the snapshot itself (market value ÷ shares), so the size of a decision is expressed in money rather than only in fund weight — a 0.5pp add by a $4bn fund and a 0.5pp add by a $30m fund are not the same event. `usd_complete` says whether every fund on the row supplied market values; when a sponsor publishes shares but no values, that fund contributes to the counts and the pp figures but not to the dollars, and the shortfall is disclosed rather than silently imputed.
- **Computed by:** `engine/holdings_signals.py` `fund_flow_decomposition` computes `flow_usd` / `selection_usd` / `total_usd` per fund-ticker from the implied price; `engine/etf_consensus.py` `_finish_decomposition` sums them per ticker and sets `usd_complete` from `n_funds_usd` against `n_funds_any`.
- **So what:** Use dollars to rank the SIZE of a decision and fund counts to rank its BREADTH; they answer different questions and they disagree often. A large dollar figure carried by one fund is a single manager's bet. An incomplete dollar figure (`usd_complete` false) is a floor, not a total — the true number is larger by however much the value-less sponsors moved.

---

### Persistence — streak, breadth and acceleration

- **Shown as:** Small chips on the board row (a streak count; a "picking up" read when the pace is rising). ZH: 连续 / 加速.
- **Means:** `streak` is how many consecutive snapshots one fund moved the same way on the name — one add is an event, four in a row is a program. `breadth` counts how many funds on the row are currently in a positive streak. `accel_pct_per_day` is the change in pace against the prior window, normalised per day so funds reporting on different calendars stay comparable.
- **Computed by:** `engine/holdings_signals.py` `_streaks` (per fund, over the `config.yml` `flow_streak_snaps` snapshot count); aggregated per ticker by `engine/etf_consensus.py` `_roll_decomposition` into `breadth`, `max_streak` and `accel_pct_per_day`.
- **So what:** A long streak with a rising pace is a manager still building, which is the read this page exists to surface early. A long streak that has just flattened is a position that may be finished — the flow information is already in the price by then.

---

### Fresh conviction (brand-new positions)

- **Shown as:** A row of cards above the tables: the stock, and "N funds opened it". ZH: 全新建仓.
- **Means:** Names that appeared in a fund's holdings for the first time in the comparison window — position opened from zero, not enlarged. A new position is the highest-information version of an add, because a manager who did not own a name and now does has made a decision that cannot be explained by drift, rebalancing or index maintenance.
- **Computed by:** `engine/etf_board.py` `_fresh_conviction` selects the `is_new` rows out of the accumulation list and groups them by ticker; the `is_new` flag itself is set in `engine/holdings_signals.py` `etf_signals` from the lifecycle comparison of the snapshot pair.
- **So what:** Two or more funds opening the same name in the same window is the single strongest cross-manager read on this page. One fund opening it is a lead, not a signal. Nothing here says the entry is timed — see the stance column for what to do about it.

---

### Stance — "what to do" (Act · Get ready · Watch — don't chase · Protect gains · Stand aside · Ignore)

- **Shown as:** The last column of the consensus board and of each fund table: a plain-word stance chip with a one-line reason. ZH: 行动 · 准备进场 · 观望·勿追 · 保护盈利 · 回避 · 忽略.
- **Means:** What a reader should do about this row, in the platform's shared stance vocabulary. Fund holdings are filed and lagged, so the honest FLOOR for any accumulation read here is "Watch — don't chase": somebody with better information already bought, and chasing their fill is not the same trade. The stance escalates to "Get ready" only when the name's own price-cycle read shows a setup forming, and to "Act" only in the rare case where a live buy setup and the fund flow agree. Distribution reads as "Protect gains" or "Stand aside"; funds split with no net edge reads as "Stand aside".
- **Computed by:** `engine/etf_board.py` `stance_for` maps (price-cycle ladder, confirmed, contested, direction, counts, net pp) onto the vocabulary in `_STANCE`; the ladder itself comes from `engine/holdings_signals.py` `_ladder_for`.
- **So what:** Take the stance literally. "Watch — don't chase" is not a soft buy — it means the information is real and the entry is yours to find. Most rows on most days will sit there, and that is the honest state of a lagged-filing signal.

---

### Hero verdict line

- **Shown as:** One sentence under the page title, e.g. "Fund managers are building conviction in Space, Nuclear and Semiconductors — into a risk-on tape." ZH: 一句话总结.
- **Means:** The themes drawing the most net cross-fund conviction right now, plus the rotation backdrop's risk lean, written as one sentence. It is a summary of the board directly below it and nothing else — it consults no macro engine, no regime score and no allocation model. When no theme carries positive net conviction the line says managers are quiet, rather than manufacturing a lead.
- **Computed by:** `engine/etf_board.py` `_verdict`, over the per-theme tally from `_theme_tally` and the risk label from `_rotation`; assembled for the template by `board_context`.
- **So what:** Read it as the board's headline, not as a market call. "Into a risk-on tape" means the accumulation has the tape behind it; "against a risk-off tape" means managers are buying into weakness, which is information about them, not a prediction about the market.

---

### Free-tier stance line (non-members)

- **Shown as:** On the gated shell only: "Risk-on tape — credit and cyclicals lead. Watch, don't chase." ZH: 风险偏好行情 …观望，勿追。
- **Means:** The hero verdict summarises graded rows, so it cannot ship to a free reader. This is its non-graded replacement, derived ONLY from the rotation backdrop's risk label — trailing ratio momentum over public ETF prices — which the free page renders in full a few hundred pixels below, so the reader can check the claim against the same data. Three deterministic outcomes, one per risk label; no ranking, no score, no name.
- **Computed by:** `engine/etf_board.py` `_T5_STANCE` selected by `board_context` off the rotation risk label; the tier split itself is `scripts/build_site.py` `build_etf_page` with `_etf_gated`.
- **So what:** A supportive tape is a reason to look, not a reason to buy — which is exactly what the line says. It is the same stance a member sees at the top of a quiet board.

---

### The rotation backdrop — "the market they're buying into"

- **Shown as:** A panel of style, risk and sector reads (e.g. growth vs value, cyclicals vs defensives, leading sectors) below the boards. ZH: 他们正买入的市场.
- **Means:** Trailing ratio momentum across public ETF pairs — what the market has been rewarding lately. It is CONTEXT for the fund decisions above, not an input to them: no consensus row is re-ranked because the backdrop is risk-on.
- **Computed by:** `engine/etf_board.py` `_rotation` `_RISK_READ` `_verdict` shape the committed pulse artifact into the panel's reads and the verdict's tape clause; the artifact itself is read by `scripts/build_site.py` `_load_etf_pulse`.
- **So what:** Accumulation with the backdrop is easier to hold; accumulation against it needs a longer horizon and a smaller size. This panel is fully public because it makes the verdict line checkable.

---

### Fund coverage table — snapshots, latest, freshness

- **Shown as:** A directory of every tracked fund: sponsor, theme, snapshot count, latest snapshot date, and a freshness read. ZH: 快照 / 最新 / 新鲜度.
- **Means:** How much history exists per fund and how current it is. Freshness is measured against the FLEET's newest snapshot, not against the clock — sponsors publish on different calendars and at different hours, so "days behind the freshest fund in the universe" is the only comparison that does not manufacture staleness out of a timezone. A fund past the staleness threshold is flagged and its rows are marked, so a name is never presented as "this cycle" on evidence that is a week old.
- **Computed by:** `engine/etf_consensus.py` `fund_coverage` (per-fund `n_snapshots`, `latest_asof`, `stale_days`); the fund's declared type and theme come from `engine/etf_registry.py` `fund_registry`; the per-row stale flag is `engine/holdings_signals.py` `is_stale`, thresholded by `config.yml` `flow_stale_days`. The universe itself is the `etf_holdings` block of the same file.
- **So what:** Zero snapshots means a broken feed, not a fund with no activity — read that row as missing data. A shallow history (a handful of snapshots) means the fund's conviction numbers exist but have no context yet; a deep one means a streak on that fund is meaningful.

---

### Data-quality guards — split adjustment, quarantine, duplicate snapshots

- **Shown as:** Mostly invisible: an affected position is normalised, or a corrupt snapshot is skipped and the row prints its null rather than a number. ZH: 数据质量.
- **Means:** Three failure modes that would otherwise fabricate conviction. A share SPLIT multiplies every share count while the position's market value stays flat — untreated, that reads as an enormous add; the guard requires both a re-denomination-shaped ratio and a roughly unchanged market value before it normalises, deliberately tight, because a false split deletes a real decision. A snapshot whose weights do not sum to roughly 100% is quarantined and the comparison steps to the nearest usable pair. Duplicate same-day snapshots are de-duplicated before any diff.
- **Computed by:** `engine/holdings_signals.py` `_split_adjust` for the split guard, `WEIGHT_SUM_BOUNDS` for the weight-sum sanity gate, `_usable_snapshots` for snapshot selection; the split thresholds are `config.yml` `flow_split_min_ratio`, `flow_split_mv_tol` and `flow_split_ratio_tol`.
- **So what:** When a stat is missing here it is missing on purpose — the guard fired and the honest answer is "we could not measure this", which is printed rather than back-filled with a zero.

---

### Weight trajectory sparkline

- **Shown as:** A small line on a fund row tracing the position's weight over the recent snapshots. ZH: 仓位走势.
- **Means:** The last N daily weight readings for one (fund, ticker) pair — whether the position has been growing, shrinking or flat, independent of any threshold. Only the top rows get one, because each sparkline costs a parquet read on the render path.
- **Computed by:** `engine/etf_consensus.py` `weight_trajectory`, attached to rows by `attach_trajectories`, capped by `config.yml` `sparkline_cap`.
- **So what:** A rising line under a positive conviction number is a manager still building. A spike followed by a flat line is a position that was established and then left alone — the decision is older than the number suggests.

---

### Tier wall counts — "N names sit on the board", "N buys across N funds"

- **Shown as:** On the gated shell: the number of names on the withheld board, and the number of individual buys across how many funds. ZH: 榜单名额 / 逐笔买入.
- **Means:** Honest totals describing exactly what the members-only payload contains — counted off the WITHHELD rows themselves, never off the tracked-fund universe, so the wall cannot over-claim when the top adds happen to come from a handful of funds. The shell literally does not contain the graded rows; the split is the gate.
- **Computed by:** `scripts/build_site.py` `build_etf_page` builds the `gate` dict (`total`, `n_buys`, `n_funds`, `n_fresh`) and `_write_etf_payload` writes the withheld rows to the payload; the split is controlled by `config.yml` `gated`.
- **So what:** The counts tell a non-member how much is behind the wall and nothing about which names — which is the intended trade. The rotation backdrop and the whole coverage directory stay public so the page can still be judged on its data.

---

### Forward windows (Calibration Lab) — what the board's names did next

- **Shown as:** Not on this page. The measurement lives below the fold on the Calibration Lab (`measurement.html`) as "Fund Flows Board — Forward Windows": per horizon, how many graded rows, the median move against SPY, and "x of y ahead of SPY". ZH: 前瞻窗口.
- **Means:** Every night the published consensus board's top rows are written to an append-only ledger exactly as they shipped; as each 5, 21 and 63 trading-session window closes, the ledger fills in what those names did, outright and against SPY, entering at the next session's close after the board date. Windows re-drawn nightly. Until a window closes the row stays open and unscored — never counted as flat — and the panel reports "collecting".
- **Computed by:** `engine/etf_board_ledger.py` `append_snapshot` (the fire log, keep-first per board date and ticker), `grade_snapshots` (forward returns, next-bar fill, adjusted-first price ladder) and `build_track` (the display projection); driven nightly by `scripts/grade_etf_board.py`. The panel payload is `scripts/build_measurement.py` `build_etf_board_windows`.
- **So what:** This is a record being accrued, not a claim being made. The board's own ranking does not read it, nothing here sizes or gates anything, and a thin record is reported as thin. It exists so that any future proposal to weight some funds more heavily than others has real forward evidence to be tested against instead of an assertion.
