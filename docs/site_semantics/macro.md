# Site Semantics: macro.html

US macro regime dashboard — the primary market state and risk read.
Template: `templates/dashboard.html.j2` (mode `macro`).
Computing engine: `scripts/build_site.py`.

---

### Market State Score / Verdict (hero)

- **Shown as:** A large 0–100 dial with a needle, a label ("Risk-on", "Mixed", "Risk-off"), and a tick marker at the current score. ZH: 市场状态分 with 风险偏好 / 混合 / 避险.
- **Means:** A composite confirmation-over-prediction read of the current US equity market posture, blending six legs: Trend (0.24 weight) = US index multi-timeframe tape; Risk (0.18) = cross-asset risk appetite; Vol (0.16) = volatility regime (term structure, VRP); Breadth (0.16) = participation across stocks; Liquidity (0.14) = money tide + credit; Stress (0.12) = drawdown-risk guard. GREEN = trend, breadth, cross-asset line up. YELLOW = signals disagree or in transition. RED = tape under stress, trend down. Display-only — never feeds a scored path.
- **Computed by:** `engine/market_state.py` `market_state_snapshot` with `US_PROFILE`. Component weights in `WEIGHTS`. Overrides cap or force the verdict: an act-level alert caps at MIXED; NEW_REGIME caps at MIXED; high/extreme drawdown band or acute systemic stress forces RISK_OFF; dislocation "stand_aside" forces RISK_OFF. Risk Radar override applies last and only tightens (never loosens). Score clamped into band: RISK_OFF ≤ 41, MIXED ≤ 59, RISK_ON uncapped but ceiling from radar.
- **So what:** Green = trend-follow and add on strength. Yellow = size smaller, wait for resolution. Red = defend capital, reduce risk. Tick at today's score; score yesterday vs today = direction of travel.

---

### Macro Regime Quadrant (hero sub-line + stocks header badge)

- **Shown as:** Sub-line under the verdict: e.g. "Goldilocks · stable". On us_stocks.html: a "Regime: Goldilocks" badge. ZH: 金发姑娘 · 稳定.
- **Means:** The economic regime quadrant: growth axis sign × inflation axis sign. Q1 Goldilocks = G≥0, I<0 (growth up, inflation falling, the best equity backdrop); Q2 Reflation = G≥0, I≥0; Q3 Stagflation = G<0, I≥0; Q4 Growth-scare/Deflation = G<0, I<0. Hysteresis requires a new quad to hold a configured number of consecutive days or to exceed a shock threshold. The transition_state (STABLE/TRANSITIONING/WEAKENING/NEW_REGIME) describes how settled the current quad is.
- **Computed by:** `engine/regime.py` `raw_quad` (sign rules on g, i floats); `apply_hysteresis` for the confirmation state machine. `QUAD_NAMES` dict. Growth and inflation axes z-scored via `engine/axes.py` `score_axis`.
- **So what:** The regime describes the economy, not the tape. Use it for sector and factor tilts (e.g. in Q1 growth and tech favoured). For whether the market itself is turning, use the Market State Score. The transition_state signals whether the regime is stable enough to lean on.

---

### Transition State / Stability Sub-line (hero)

- **Shown as:** Plain-word stance in the hero sub-line: "stable", "shifting — backdrop fading, not all-clear; see the risk read →", "weakening — early cracks, not all-clear; see the risk read →". ZH: 稳定 / 转换中 / 走弱.
- **Means:** How settled the current regime quad is. STABLE = confirmed and holding. TRANSITIONING = the prior quad is fading but the new one is not yet confirmed. WEAKENING = early cracks in the current quad (leading indicators turning). NEW_REGIME = just flipped; the dashboard caps the market state at Mixed until it settles.
- **Computed by:** `engine/regime.py` `apply_hysteresis` pending/confirmed state machine; `engine/run.py` `transition_state` key. Template maps the raw enum to plain-word EN/ZH labels via Jinja dict lookups in `templates/dashboard.html.j2`.
- **So what:** "Stable" = trust the regime read for sector/factor positioning. "Shifting" or "Weakening" = hold positions lightly, expect rotation volatility. "New regime" = wait for a confirmed new quad before making structural bets.

---

### Risk Radar (hero context line / click-through dialog)

- **Shown as:** In the hero: "Pullback risk" label with a score and a "do" instruction (e.g. "Stay hedged / reduce gross"). Expanded dialog shows per-scare-type bars and calibrated pullback probability. ZH: 回撤风险雷达.
- **Means:** A validated leading-risk signal. Measures seven scare types: credit stress, rates/inflation shock, bubble blow-off, growth scare/defensive rotation, volatility event, global breadth breakdown, and breadth internals deterioration. Each scare-type sub-score is a weighted mean of causal-percentile legs. The top scare score determines the state: calm/watch/caution/elevated/risk-off. An elevated or risk-off state fires a loud banner. Calibrated P(SPY ≥ 5% pullback, 21 sessions): calm 13%, watch 13%, caution 16%, elevated 25%, risk-off 33%.
- **Computed by:** `engine/risk_radar.py` `snapshot` (sole public entry point). States in `_STATE_ORDER`. Band thresholds (default): watch 55, caution 68, elevated 78, risk-off 88. Probability calibration from `_PROB_CAL` table; conjunction bump (`_CONJ_BUMP`) when multiple scare-types fire. Lift = conditional probability / `_PROB_BASE` base rate (h21 base: 17.8%).
- **So what:** At calm/watch: no action needed. At caution: tighten stops, reduce concentration. At elevated or risk-off: de-risk sizing (NOT necessarily exit — de-risk = sizing, not selection). The radar is loud-and-early by design; every alert prints its measured lift, and a forward-outcome log grades every call.

---

### Fired Alerts Pill (hero)

- **Shown as:** "Fired alerts N" pill (hover to expand popover listing individual alerts). ZH: 已触发警报 N.
- **Means:** Count of live alerts that have triggered on a state change — level escalation, a crossing, a sign flip. Alerts are rare by design: they fire only once on a change, not on a sustained state. Each alert links to its evidence panel.
- **Computed by:** `scripts/build_site.py` calls `engine/alerts.py` `alert_views` to build the alert list. Alert severity: info / warn / act. An act-level alert caps the market state at Mixed. `transition_state_change` is the most common act-level alert.
- **So what:** Zero alerts = unchanged conditions. N alerts = read every one immediately. An act-level alert (red) is the most urgent: it has caused the market state to cap at Mixed regardless of the component scores.

---

### Macro Backdrop — Six-Factor Evidence Matrix (card / dialog)

- **Shown as:** Six rows with a factor name (Trend, Risk Appetite, Volatility, Breadth, Liquidity, Stress), a score bar, and a text read. Accessed via the hero "Factor breakdown" button or the dialog. ZH: 因子分解.
- **Means:** The six weighted legs that compose the market state score, each scored 0–100 (0 = fully risk-off for that leg, 100 = fully risk-on). Each leg resolves independently; absent legs are omitted and remaining weights renormalized.
- **Computed by:** `engine/market_state.py` `market_state_snapshot`. Trend leg: `_build_tape` over SPY/QQQ/IWM at D/3D/W/M timeframes (weights 0.15/0.15/0.40/0.30). Risk leg: cross-asset RORO via `_comp_risk`. Vol leg: `_comp_vol`. Breadth leg: `_comp_breadth`. Liquidity leg: `_comp_liquidity`. Stress leg: `_comp_stress`. Each returns a dict with `score`, `label_en`, `label_zh`, `read_en`.
- **So what:** Each leg can be read independently to understand why the composite is where it is. A high trend score but low breadth score means the move is narrow — a warning sign. A low liquidity score means the money tide is against the market.

---

### Multi-Timeframe Tape Table (inside regime panel)

- **Shown as:** A table with columns: Index / Daily / 3-Day / Weekly / Monthly, showing arrow direction and RSI14 for SPY, QQQ, IWM. ZH: 多周期技术面.
- **Means:** The technical posture of the three US equity indexes across four timeframes. Arrow up = MACD positive and RSI ≥ 50; arrow down = MACD negative and RSI < 50; sideways = mixed. Weekly and Monthly carry the most weight in the trend leg (0.40 and 0.30 respectively).
- **Computed by:** `engine/market_state.py` `_build_tape` and `_tf_sign`. Indexes from `_INDEXES` constant. Timeframe weights from `_TF_W` constant. MACD from pre-computed feature frame.
- **So what:** A table fully green = all timeframes aligned bullish; a mixed table = short-term vs longer-term divergence. Never trade the daily alone without checking the weekly direction first.

---

### Posture Dial (stocks mode header / macro page hero)

- **Shown as:** A badge or chip: "Posture: Careful" (谨慎). Values: Defensive / Careful / Neutral / Constructive / Aggressive.
- **Means:** How to trade the current regime — an aggression dial set by the playbook engine. "Careful" = lean cautious, favour quality entries, keep gross moderate. "Constructive" = lean into setups with regime support, size up on confirmation. This sizes risk exposure, not stock selection.
- **Computed by:** `engine/playbook.py` `build_playbook` via `exposure_dial`. Called in `engine/run.py` `build_playbook`. Dial posture stored under the `dial` key of the playbook dict; derived from regime quad and market state color.
- **So what:** This answers "how much risk should I be taking" not "which stocks". Defensive + Red market state = reduce gross aggressively. Aggressive + Green state = scale into strong setups.

---

### Sector Heat Strip (macro hero area)

- **Shown as:** A compact strip of up to 4 sector chips below the hero, labeled with sector names and a directional tint. ZH: 板块热力.
- **Means:** A glance-tier read of which GICS sectors are leading (heating) vs lagging (cooling) under the current regime — a rotation snapshot, not a buy signal.
- **Computed by:** `scripts/build_site.py` `_sector_heat_view`. Reads sector rotation output; up to 4 "heating" themes surfaced. Display-only context (coincident ~base-rate forward returns; render kwarg only).
- **So what:** Use as context to understand which rotation narrative the market is pricing. Pairs with the Macro Backdrop factor matrix; if breadth is weak but a sector chip is heating, the move may be narrow.
