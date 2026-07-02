# China Engine Reassessment — delta report

**Date:** 2026-07-01 · **Method:** 10-agent verification + gap-hunt + measurement workflow (2 verifiers, 3 measurers, 4 gap-hunters, synthesis) run against `research/CHINA_ENGINE_PROBLEM_BRAINSTORM.md` on current main. 83 pooled findings → 17 new problems, 15 corrections, 8 measurement results, evidence-based answers to all 10 §8 questions.

**Companions:** `research/CHINA_ENGINE_PROBLEM_BRAINSTORM.md` (the audit under test) · `research/ENGINE_FIX_MASTERPLAN.md` §W6-CN (the resulting design).

## Overall verdict

The doc STANDS and is current: it was written against post-#791 code (verifier item 7 confirms EXT_PENALTY/CN_TIER_FRAC/ledger/#806 is_buyable all present exactly as the doc assumes; zero pre-#791-stale claims found). All 8 root causes hold on today's code, several understated. R1 (graders never close the loop) holds and is WORSE than written — the #791 board ledger, the doc's honesty keystone, is structurally dead on arrival (engine/china_standout_track.py:82 reads store group 'china' = 30 ETFs; 0/120 board tickers resolve; n_graded=0 forever) — with one genuine exception the doc missed: risk_radar_intl runs a complete log→grade→bounded-tune→can_force loop (the template for closing every other loop). R2 (edge demoted, US momentum selects) holds and is slightly understated: live measurement shows the 110-name board overlaps the validated reversal watch 1/110 and the low-vol sleeve 0/110 — the acted-on surface and the validated edge are ~orthogonal sets; the sort's conviction leg is residual-alpha-led, a signal the code's own docstring says is dead for A-shares. R3 holds (two unreconciled regime engines; no board gate) with the nuance that §8.3's answer already exists in-repo unwired (risk_radar_intl CN gross_factor sleeve dial, currently 'caution/breadth 87' while boards run ungated). R4 holds overall but its flagship example is stale — the washout signature is now ONE formula (cycles delegates to pathway._position; desk copy byte-equivalent); the residual is an input-plane contract (7-code composite vs single Shenwan code on the same page), not a 3-way rewrite. R5 holds with the primary artifact verified: turn-confirmation flips the reversal edge to −0.29%/mo, Sharpe −0.29, maxDD −78.9% (research/CHINA_HK_STOCK_SIGNALS.md L98-123). R6 holds with a sign correction: the 'orthogonal leading signals sitting unused' are unused AND unvalidated, and measurement now shows raw LHB and premium-block legs would SUBTRACT alpha if fused as proposed (§8 contrarian #4 confirmed empirically), while the genuinely validated orthogonal legs (drawdown radar, #773 AI-semis→CPO weekly confirmer t=3.27) go unmentioned. R7 holds and is understated: no raw A-share price plane exists anywhere (both stores are auto_adjust=True), china_search retroactively DELETES dropped names' history columns each run, combine_first merges leave permanent adjustment seams that seasonally bias rev_z, and the entire gated Tushare plane is frozen at 2026-06-21 yet preferred over fresh free fallbacks. R8 holds; the factor measurement refines it — concentration is real (~10σ pairwise-correlation elevation) but it is a shared 'fresh bounce-cross' timing factor, not the extreme small-cap junk bet §8 suspected, so the fix is a sleeve-level correlation cap/sizing note, not per-name neutralization. Biggest blind spots the 91 missed: (a) the dead-on-arrival ledger; (b) cross-repo blast radius — the edge-less conviction score feeds an autonomous Opus PM's real-money paper books nightly via vendored china_standouts.json, so the fix surface is the published JSON contract, not just the pages; (c) two validated-but-unwired edges; (d) the nightly-vs-asia lane split that keeps sibling pages one CN session apart ~19.5h/day; (e) the retroactive universe-deletion mechanism. The doc's §8 adversarial layer is its best section and mostly survives measurement — with #4 (LHB anti-correlates) now CONFIRMED, the fillability overstatement (#2/under-scoped T+1) CORRECTED to a survivable ~1pp/entry ~2-3pp-hit haircut rather than a product-killer, and Q10 answered definitively (W1 covers zero of the china board path).

## Stale / refuted / corrected claims

### [refuted] §2 coherence table: subsectors_china track record benchmarked on SPY

engine/subsector_track_record.py (_BENCH='SPY' L47) is consumed only by US builders (scripts/build_subsector_rotation.py L48; engine/index_leadership_track.py BOARDS L36-45 — no china entry); scripts/build_subsector_confluence.py:main_china L234-249 makes no track-record call. There is NO China track record at all — the doc's own §3d 'no-china-track-record-grading' was the correct claim; its §2 cell is internally inconsistent with it. Fix task = CREATE a CN concept-board ledger (fork index_leadership_track with an explicit required _BENCH=510300.SS), not rebench an existing one.

### [corrected] R4/triple-signature-divergence: washout↔euphoria cycle position computed three different ways

Formula is now unified: engine/china_sector_cycles.py:_signature L108-117 delegates to china_sector_pathway._position (L118-138); engine/china_sector_desk.py:_cycle_position L76-99 is a byte-equivalent duplicate (drift hazard, not live divergence). The REAL residual is an input-plane contract: pathway_for() runs on csi.gs_index composites (e.g. Consumption = 7-code EW, china_sector_index.py L65,89-98) while the same page's cycles card runs the single Shenwan code — so the same-page card-vs-pathway split is real for composite sectors. Budget one import (desk→pathway._position) + one input-contract decision, not a 3-implementation rewrite.

### [corrected] Same THS concept on two price stores: dividend-adjusted china_search vs RAW china_stocks OHLC

The two-store split is confirmed, but BOTH stores are yfinance auto_adjust=True total-return (collectors/_stock_ohlc.py:49; collectors/china_universe.py:20). Divergence driver = independent pulls / different histories / different failure-coverage modes, not adjusted-vs-raw. Consequence: NO raw A-share price plane exists anywhere in the repo — the doc's 'store raw AND adjusted, use raw for level/limit logic' remedy requires a NEW collector plane, not picking one of the two existing (both-adjusted) ones.

### [corrected] northbound-frozen-still-in-frame (live signal harm)

engine/china_inputs.py L60-67 applies ffill_limit=5, so post-2024-08-16 the column reads NaN live, not frozen-fresh; downstream is disclosed (flow_velocity.py:57 NORTHBOUND_FROZEN + user-facing note; china_sector_central.py L125). Residual harm is historical only (a regime-shifted covariate in any fit over the frame). Dropping it is hygiene, not alpha — the real point (suite lost its only fast non-price flow input) survives and the replacement hunt is the priority.

### [corrected] hitrate-computed-never-shown: china_standout_track.grade output never surfaced anywhere

The grade IS attached to the shipped artifact (scripts/build_china_library.py L1156-1161 → site/factordata/china_standouts.json board_track{available:true, n_rows:120, n_graded:0}); no template renders it (grep across templates/ and site/ = zero consumers) — so 'publish it' is one Jinja block. But nothing has matured (ledger starts 2026-06-30, earliest 21d maturity ~2026-07-29) AND it can never mature as coded (wrong store group — see new problems #1). Sequence: fix store group + CSI300-relative + fill-realism BEFORE the first number renders.

### [corrected] §2 table: china_stocks regime source 'none at board level'

Right for gating/ranking, stale as a display row: china_stocks.html renders the risk-radar banner via the shared vm (scripts/build_china.py L841-861; templates/dashboard.html.j2:1115-1117, likely live today at CN caution/breadth 87), and the board carries per-name QVIX regime_stress (build_china_library.py L651-661, L887-888) + liquidity_overlay nudge (L142-155). None of it gates inclusion or sizes the list — the substantive claim holds; update the table so the masterplan isn't designed against a stale coherence map. Also note the display plumbing means threading gross_factor as a sleeve chip is a few-line change.

### [corrected] R1: 'no China surface consumes its own outcome ledger'

One real exception: the CN drawdown radar runs a complete closed loop — data/risk_radar_intl/cn_forward_log.jsonl → deterministic grade (≥5% drawdown within H bdays) → bounded tuner → can_force capability gate (risk_radar_intl_audit.py:214, consumed at engine/market_state.py:507). Still accruing (3 entries, can_force=False). R1 stands for all five pick surfaces, but reuse this exact 'earn the right to act' pattern when closing china_standout_track / sector_central_grader loops instead of inventing new machinery.

### [corrected] §0/R2: 'the ONE validated A-share edge' framing

The repo record holds ~5 validated findings, but only one NAME-SELECTION edge (3M within-sector reversal, Sharpe 0.58). The others operate at different units: forward-drawdown radar composite (market SIZING — validated, unwired, unnamed by the doc), global AI-semis→CN-CPO weekly confirmer (THEME slice, t=3.27, fully orphaned), low-vol defensive tilt (sleeve, wired), sector washout signature (phase CONTEXT, descriptive-only). This partially answers §8-Q8: no engine work needs to manufacture a second selection edge — the sizing/slice edges are real, validated, and merely unwired.

### [corrected] §5(a): qualifying leg requires 'washout-reclaim confirmation'

The only Phase-0-stable washout finding is the SECTOR-level descriptive state signature (research/CHINA_SECTOR_PATHWAY_PHASE0.md, explicitly labeled descriptive). Per-NAME washout/reclaim (name_score 2W-StochRSI boost, #748/#749) was never cross-sectionally validated, and Phase-0 REFUTED the adjacent confirmed-pullback/reclaim design. Requiring per-name reclaim in §5(a) re-imports exactly the confirmation gating that flips the edge negative. Correct form: top-quartile rev_z + SECTOR in the washout band of the canonical cycle position.

### [corrected] §5(d) / §4.4: fuse discovery LHB/block/attention + southbound/breadth as positive orthogonal confirmers

Measured signs refute the proposed list: raw LHB flag on dip names DRAINS (−1.43%/21d excess, cluster-t≈−2.2); block-trade PREMIUM (the leg as designed in china_discovery.py:14) drains (−0.60%/5d, t≈−2.8); southbound is sign-unstable (train −0.16 / test +0.49, Stock-Connect-era artifact); breadth is validated only as a DRAWDOWN/veto leg. Defensible replacements: deep-DISCOUNT blocks (+3.45%/21d, t≈3.4, inverted leg), global AI-semis slice confirmer (validated, leading), inst-seat LHB (weak-positive, probationary), guidance drift (accruing). For ~90% of the universe no validated positive confirmer exists — §5's AND-gate (d) would go dark almost everywhere, independently supporting §8's shrinkage-ensemble alternative.

### [corrected] R6: 'genuinely orthogonal LEADING signals sit unused (china_discovery…)'

They are unused AND unvalidated — every intel module self-declares leaf status, and data/china_validation/scorecard.json shows 0/6 families proven with fundflow (主力) and chips measuring WRONG-SIGN (fundflow t_hac −1.019). The intel layer's leaf-ness is an honesty feature; the deficit is validated-leg wiring (radar sizing dial, AI-semis confirmer), not intel-layer plumbing. Do not spend fix budget 'connecting' it before the §8.4 sign tests.

### [corrected] asof-utc-vs-cn-session [medium]

No live-firing mis-stamp on the current schedule: page as-ofs are data-derived (build_china_library.py:186; china_reversal.py:109), ledgers stamp the data-derived date, banners are tz-labeled. But ~20 CN/HK files use naive date.today() (china_flows.py:85-134, hk_ah_official, china_radar_ledger.py:37, china_alerts, event calendar…) and stamp correctly only via a two-way coincidence (PDT runner × 08:30 UTC asia cron). The nightly 02:00 UTC lane sits inside the danger window. Fix = one tz-aware cn_session_date() helper + a lint banning naive todays in china_*/hk_* — a contract, not per-site emergencies.

### [corrected] §8 under-scoped: 'T+1/limit-up unfillability is the single largest silent overstatement'

Direction confirmed, magnitude corrected for the post-#791 ADV-screened board: close-to-close grading overstates a realistic T+1 (H+L)/2 fill by ~0.9-1.1pp per entry and ~2pp hit-rate (5,393 events); buy-at-T+1-high worst bound −3.1pp/−10pp; truly unfillable (locked limit all day) only 0.22% of entries; pinned-at-limit reference closes 3.8-5.1% where the bias doubles (hit 50%→42.6%). A real, survivable calibration haircut — not the zero-fill regime the framing implies. The zero-fill story only holds for the locked-limit cohort the #791 ADV floor already mostly excludes.

### [stale-already-fixed] monthly-macro-ffilled-as-fast (TSF/PMI/CPI consumed as fresh)

PARTIALLY: #808 availability-stamps TSF (engine/china_strategies.py:_tsf_availability_stamp L67-101), covering strategies + masterminds (shared import). Still open exactly as the doc's broader claim implies: china_radar (_sig_credit_impulse L65-85, no lag), china_conditions (L285-295, ffill_limit=40, reference-stamped, plus a false 'reuses credit_tape' comment), china_sector_index (L264-269, crude shift(1)). #808 is the template to generalize, not the closure. Related: credit impulse is 3 distinct formulas across 5 sites (2nd-derivative vs 6m-growth vs YoY level) — doc understates at '3+ times'.

### [corrected] Phase-0 attribution: 'china_reversal.py Phase-0 found confirmation hurts'

The finding is real and verified at the primary artifact, but it lives in scripts/china_reversal_phase0.py → reports/china-reversal-phase0.md and research/CHINA_HK_STOCK_SIGNALS.md L98-123 — engine/china_reversal.py only implements the top-16 watch list. Numbers: no-gate deepest-quintile +0.56%/mo Sharpe 0.58 maxDD −37.6% hit 56%; + turn-confirmation (ret_5d>0) −0.29%/mo Sharpe −0.29 maxDD −78.9%; quality floors also hurt. Caveats in the same artifact: not net-of-cost, high turnover, needs ST/liquidity screen, size-small framing.

## New problems (missed by the 91)

### [critical] #791 board-order ledger is structurally dead on arrival — grades will never mature

**Evidence:** engine/china_standout_track.py:82 `store.read("china", ticker)` → data/china/ holds ~30 index/ETF parquets; 0/120 board.parquet tickers resolve there (all 89 unique names resolve in data/china_stocks). _fwd_return returns None for every stock row; grade() reports 'accruing' n=0 forever — matching the live artifact (china_standouts.json board_track n_rows=120, n_graded=0).

**Implication:** The honesty keystone of #791 reproduces the doc's R1 'perma-accruing' pattern in the newest ledger. One-line-class fix (read group 'china_stocks', fall back to 'china' for ETFs) — but land it in the SAME pass as CSI-300-relative returns and fill-realism corrections so the first number ever published is unbiased. Every 'close the grader loop' plan silently depends on this.

### [critical] china_search universe retroactively DELETES dropped names' price-history columns every run

**Evidence:** collectors/china_universe.py:306 `closes = closes[[t for t in tickers if t in closes.columns]]` — any name that falls out of the current Sina top-N (delisted, ST'd, shrank) has its entire history column physically removed. Universe is a current-day mktcap snapshot (L92-120).

**Implication:** Worse than snapshot survivorship: even a PIT membership ledger started today cannot recover deleted columns. Deletes exactly the deep-decliner failures the reversal signal buys — the 0.58 Sharpe's own data plane is optimistic, confirming §8's 'maximally destructive to reversal specifically'. Fix: stop the trim (append-only columns + dropped-date marker) and treat all existing china_search-based stats as upper bounds until re-run.

### [critical] Cross-repo blast radius: the edge-less score feeds an autonomous Opus PM's real-money paper books nightly — the doc's fix surface is scoped wrong

**Evidence:** Mastermind vendors the macro repo and reads 7 artifact families; brain/china_intake.py:99 converts conviction.score (= potential_score with edge_mult=1 after the L920-927 overwrite) directly to the funnel score; brain/china_mcp.py:212-233 hands it to the Brain as 'The desks' best ideas right now'; decisions.jsonl shows the tool used on 7/8 China and 7/9 HK turns. Verified live: row 1 of today's buy list carries conviction.score=32, band 'Watch' on a BUY list.

**Implication:** §3a fixes change what a ¥1M+HK$ autonomous book reads nightly, not just a dashboard. Any canonical-contract work (Appendix B) must treat the bot as a first-class consumer: renaming/reshaping conviction/size.bucket/cycle_blocked/buy-order silently breaks two books. Interim: fix the MCP tool copy that over-endorses a timing rank as 'best ideas'.

### [high] Adjusted-close seams from incremental combine_first merges bias rev_z seasonally and can fabricate indicator crosses

**Evidence:** collectors/_stock_ohlc.py:49 auto_adjust=True + '1mo' refresh window + lib/store.py:80 combine_first (same class in china_universe.py:299) → permanent basis step at the refresh edge after every ex-div. Measured: 17/300 names (5.7%) with >0.4% seam step in 250d (worst 40%, 688188.SS), clustered in May dividend season; panel vintage diff: 10/1,485 names revised ≤2d, median 1.4%, max 41.7%.

**Implication:** Live truth bug, not replay noise: rev_z's 63d window spans the refresh window, so recent dividend payers look ~div-yield more beaten-down than they are — a systematic seasonal tilt into the reversal rank; seams inside MACD/StochRSI lookbacks can fabricate cascade/washout crosses. Fix = the raw+adjusted price-plane contract with full-overwrite (not combine_first) for adjusted series.

### [high] Two validated edges are wired to NOTHING: risk_radar_intl CN sleeve dial and the #773 AI-semis→CPO weekly confirmer

**Evidence:** (a) engine/risk_radar_intl.py — validated forward-drawdown composite (breadth 1.97-3.13x, composite 2.07x p=0.01), emits gross_factor {calm 1.0…risk-off 0.62} (L51, L307); zero CN consumers of gross_factor; live state 2026-07-01 = caution/breadth/87 while all five boards run ungated. Meanwhile the board's ONLY stress input is an unvalidated QVIX-spike overlay from the class the radar's own research calls dead/mean-reverting (build_china_library.py:651-661). (b) scripts/china_global_theme_backtest.py — SMH/SOXX/TSM 4w momentum → next-week THS CPO t=3.27, survives horse-race; grep shows zero consumers; targets (ths_cpo/pcb/storage_chip) live on 2 of the 5 pages. Name hazard: engine/china_radar.py is display-only, NOT the validated radar.

**Implication:** §8-Q3 and part of Q4 are already answered in-repo: thread gross_factor into the five boards as a sleeve-size chip (display plumbing already shared — few-line change), and wire the AI-semis leg as a slice-scoped weekly confirmer chip on AI-supply THS concepts. Both sidestep the §8.3 objection because neither gates names. Fix plans must say risk_radar_intl.CN_PROFILE, not china_radar.

### [high] Discovery legs have measured WRONG signs as designed; one inverted leg is the best northbound replacement found

**Evidence:** engine/china_discovery.py:14 treats block-trade PREMIUM as accumulation: measured −0.60%/5d (t≈−2.8) on dip names; deep-DISCOUNT blocks (≤−15%) +3.45%/21d fill-realistic (t≈3.4, 669 obs). Raw hot-money LHB flag on dips: −1.43%/21d (t≈−2.2) — yet engine/china_altdata.py:33 weights lhb +0.10 positive. Limit-up continuation premium sits entirely in the unbuyable first session (fill-real diff +0.04%/5d, −1.16%/21d).

**Implication:** Invert before fusing: premium-block and raw-LHB become DEMOTIONS on reversal candidates (free precision levers from the same fetch); deep-discount blocks + inst-seat LHB go on the forward ledger as probationary confirmers. zt/连板 must never enter buy-rank with positive sign — chase-veto and froth-breadth only. All magnitudes carry survivorship/single-regime caveats: sign evidence, not sizing evidence.

### [high] Marker-date grading embeds ~+5.7pp/10d look-ahead via resolved 'take' quality labels

**Evidence:** engine/signal_quality.py:163 `held = bool(c.iloc[i+1] > c.iloc[i])` on the 3D frame — a marker carries quality 'take' only if the NEXT 3-day bar closed up. Measured: grading from marker dates +9.47%/10d 84.7% hit vs +3.77%/61.5% from confirmation-day close. The board ledger convention (board-date close, verified 60/60) is post-confirmation and safe.

**Implication:** Hard rule for every grader/backtest/chart-marker hit-rate: forward returns only from the first close at which the label was knowable. Add an explicit check to the W1-CN leakage harness — any future 'grade the cascade' work inherits this trap otherwise.

### [high] Fill-realistic ledger is blocked on data: no Open column collected, zt_pool keeps one day

**Evidence:** collectors/_stock_ohlc.py:26 _OHLC=[Close,High,Low,Volume] — Open dropped for the whole china_stocks/hk_stocks store; T+1-open fills only proxyable by (H+L)/2 with the high as bound (+4.41% vs +2.13% at 21d — the dominant uncertainty). data/china_zt_pool/pool.parquet holds exactly one date (2026-06-30).

**Implication:** Add "Open" (one line) + one-off full-history backfill BEFORE building the honest grader; make zt_pool append-only (it is the natural PIT record for the pinned-entry flag and any future 连板 veto — wiring a veto to an ungated one-day cache would be worse than none).

### [high] Lane-split session skew: baskets_china(_ths) build one full CN session behind their four sibling pages ~19.5h/day

**Evidence:** baskets_china/_ths built only via the build_vector hook (scripts/build_vector.py:2803-2812, 'TODO: promote to daily.yml') in the 02:00 UTC nightly lane on the PREVIOUS asia close; china_stocks/sector desk/cycles/central/subsectors build in asia-close.yml 08:30 UTC. Same membership.json shows signals one session apart across sibling pages for the whole US day + first 3h of the next CN session. Identical skew for baskets_hk.

**Implication:** A scheduling mechanism UNDERNEATH the doc's two-price-plane and asof-drift items that no engine canonicalization fixes. Cheap (move the hook to the asia lane — the TODO already exists) and a prerequisite for any cross-surface fusion intersecting baskets with subsectors.

### [high] Entire gated Tushare drip plane frozen at 2026-06-21, invisible to health, and PREFERRED over fresh free fallbacks

**Evidence:** All data/tushare/*.parquet asof stuck 2026-06-21/22 while free siblings read 2026-07-01. engine/china_crowding.py:88-91,148-153 prefer the tushare plane on file-presence only, never asof; consumers include china_extras stock-board chips and china_radar moneyflow_sector. Zero tushare entries in run_status.json; collector is a silent no-op without TUSHARE_TOKEN (tushare_client.py:41).

**Implication:** A sharper live instance of drip-caches-no-staleness-gate: inverted source preference (stale gated > fresh free). Register drips in run_status/health, make preference asof-aware, badge staleness at consume time, and root-cause the ~06-21 token failure before trusting any tushare-fed rows since.

### [high] Mastermind seam has no China staleness guard, a structural one-session lag, and independently re-encodes the doc's R2/R6 biases

**Evidence:** (a) macro_refresh.py:27 staleness anchors are 3 US files, warn-only (MACRO_STALE_BLOCK set nowhere) — an asia-lane failure freezes china artifacts undetected. (b) china_daily fires 08:00 UTC; asia engine commits land ~12-13 UTC — every decision reads the previous session; as_of is a BUILD date, not data-through (build_china_library.py:938), so no as_of gate could tell; fills queue to next open → ~2 sessions signal-to-fill. (c) brain/china_intake.py:146 caps reversal at 0.5 ('reversal alone is weak') while momentum legs score to 1.0 — R2 re-encoded by hand in a second codebase; L227-233 pays +0.08 per 'independent desk' across three same-close-derived legs — R6 re-fused at the consumer. (d) live as_of skew (CN=07-01, HK=06-30) merged silently with one misattributed as_of.

**Implication:** Latency/coherence fixes inside the engine are partially wasted at the consumer. Ship: china-anchored is_stale() block-by-default (copy the feed_health abort pattern, or Terminal's pull_macro_intel stale→abstain), a data_through field distinct from as_of, trigger the china turn on the asia commit, per-leg as_of in merged surfaces, and a downstream-consumer checklist so the funnel doesn't re-invert the Edge-vs-Timing fix.

### [high] Dual-listed A/H twins: zero cross-board reconciliation; ~190 per-pair premiums fetched and discarded; premium history biased by total-return closes + retroactive FX

**Evidence:** build_china_library.py never references .HK or any A/H input; the HK board carries a per-name A/H value leg for only 12 config pairs (config.yml:4287-4299) whose A twins are in the china universe — 1211.HK can read 'A/H cheap, edge+' the day 002594.SZ reads Standout BUY/SELL with nothing comparing them. Three unreconciled premium artifacts split CN/HK pages (hk_ah.py 12-pair vs hk_ah_official ~190-pair vs Sina HSAHP). collectors/hk_ah_official.py stores only the mean/median of the ~190-pair spot table, discarding per-pair columns. Both computed-premium legs are auto_adjust closes (H leg back-adjusts more on 6-8%-yield pairs → pctile reads structurally low, chg_1y structurally negative — the exact fields hk_stock_signals z-scores) and the FX leg mutates retroactively.

**Implication:** Add an A↔H crosswalk to the canonical contract (twin chip both boards, pair premium percentile as shared froth/value input, coherence assert); persist the per-pair spot table long-form (one-line storage change that unlocks full-universe coverage); compute premium from raw closes with fixed Asia-close FX before calibrating anything on its history.

### [medium] Ledger integrity rests on a keep-first accident: mid-session partial bars were committed pre-shard-split and daily.yml still builds the board mid-CN-session

**Evidence:** Commit 2400622159 (02:37Z = 10:37 CST) committed a mid-session 2026-06-30 row — 93.9% of names differ from settled close (median 1.2%, p90 4.3%). daily.yml still runs build_china_library mid-session; it survives only because the stale panel yields the prior as_of whose ledger keys exist, so keep-first (china_standout_track.py:69-70) discards it. Ledger verified clean so far (120/120 levels match settled closes).

**Implication:** Unguarded: any pre-07:00-UTC china collection (cron re-timing, cache restore) makes the partial-bar board win the date permanently. Stamp collection UTC into coverage, assert 'as_of row collected ≥07:00 UTC' at build, gate ledger appends to the asia lane explicitly.

### [medium] china_crowding 'fragility' legs are size proxies: margin froth ranks raw balance, rich_valuation top-quintiles a uniform rank

**Evidence:** engine/china_crowding.py:158 falls through to fin_balance (no fin_pct_float column exists in the tushare frame) → cross-sectional rank of raw 融资余额 = a large-cap detector; :216-232 flags top 20% of an exactly-uniform pe/pb rank (verified mean 50.0, std 28.87) → ~1,100 names 'rich' every day by construction. 2 of the 3 legs needed for the k-of-5 conjunction are quasi-static.

**Implication:** The fragility map (feeds china_altdata + sector_central froth context) is a 'big + expensive' screen in a froth costume. Normalize margin by circ_mv_yi (already in tushare/valuation.parquet) and make rich_valuation vs-own-history (china_valuation percentiles already computed) — never a constant-fraction cut.

### [medium] 46% placeholder market caps (30亿) feed Altman-Z distress zones and P/S with good/bad coloring; ST screen matches zero names and is unverifiable

**Evidence:** build_china_library.py:623-635,958 passes members.parquet mktcap_yi (46% == 30.0 exactly — a placeholder the same build distrusts at :742,:759-771) into china_fundamentals.build_all; _altman (L100-124) uses mktcap/TL at 0.6 weight and hard-labels zones; real caps sit unused in data/tushare/valuation.parquet total_mv_yi. Separately the ST screen keys on name_zh containing ZERO 'ST/退' matches across 1,483 names — pre-exclusion vs silent prefix-drop indistinguishable.

**Implication:** Half the analyzer's distress/PS readings are fabricated from a constant: thread the ==30.0 sentinel to None, prefer tushare total_mv_yi (with the asof gate). Run one adversarial known-ST ticker check — if the name field drops the prefix, the 5%-limit tier and delisting exclusion are silently blind. Also blocks any factor-neutralization claim (Q7).

### [medium] china_playbook exposure dial triple-counts co-derived monetary legs with asymmetric scissors bands

**Evidence:** engine/china_playbook.py:65-119 — liquidity_overlay (M2-YoY accel), M1−M2 scissors, and credit impulse (TSF momentum) are three legs from the same monthly PBoC aggregates, each +1; posture = 2+score, so the three co-moving money legs alone reach AGGRESSIVE with zero tape confirmation; scissors is +1 at ≥0 but −1 only below −5.

**Implication:** User-facing exposure advice on china.html systematically over-reads easing cycles. The canonical china_leads module should collapse these to ONE monetary-conditions vote and symmetrize the bands — an R6 instance on a surface the 91-item appendix never covers.

### [low] Low-severity cluster: NaN-denominator driver deflation; 2026-only event calendar; silent allocation sleeve renorm; unit-meaningless ETF-creation gauge; paper marks on adjusted closes

**Evidence:** china_market_drivers.py:281-292 divides by full weight sum while NaN legs drop from the numerator (patchy-leg drivers structurally lose the dominance contest; contaminates the gradeable log). china_event_calendar.py:78-93 CNY-slip table keyed month-only → silently misdates 2027 prints. china_allocation.py:131-143 renormalizes away missing sleeves under the same label. china_internals.py:279-286 sums raw share-count deltas across different-NAV ETFs over one day ('+158,800,000 shares') — matters because ETF create/redeem is a northbound-replacement candidate. Mastermind paper marks fall back to adjusted tech.price and still mark on feed-abort days (paper_account.py:293-340).

**Implication:** None urgent individually; the ETF-unit and driver-denominator fixes should land before either series is promoted from display to signal, and the calendar/allocation fixes are cheap silent-degradation closures in the masterplan's target class.

## Measurements

### Does the W1 PIT/leakage harness cover the live china_stocks board feature path, and what is the measured leakage tax? (§8 Q10)

ZERO coverage: engine/pit.py + config.yml vintage_series are all-US; scripts/shadow_pit_regime.py has no china refs; the only China as-of artifact is #808's TSF stamping on the GTAA path the board never consumes. Truncated-replay probes on board.parquet@2026-06-30 (60 rows): washout-2W reproduces 60/60 on the correct plane (deep store), 57/60 on the wrong plane (5% plane tax — universe() overlays the deep store so history depth shifts 2W bucket phase/RSI warmup), and flips 8.3%/day when graded on completed buckets (partial-bucket tax — a completed-bucket backtest grades a different signal than users saw). Price-vintage diffs (git-committed panels as ALFRED-analog vintages): 0.7% of names revised within 2d, median 1.4%, max 41.7%. rev_z is causally clean live (both ends observed closes) but replay-fragile and screened on CURRENT ST/mktcap/membership snapshots (9 columns churn / 2 days). Cascade tiers already compute a per-bucket 'known' date (confluence_tiers.py:79-80) — the PIT seed to persist.

*Confidence: High — direct replay probes run on the ledger rows; the harness spec (M7: plane-correct truncated replay + vintage matrix + bucket-completeness + session guard) is ~a day of work reusing the probe code and the tests/test_vector_pit.py template.*

### How much does the live board overlap the validated edge surfaces? (the doc's '2 real ideas invisible among 108')

Board (2026-07-01): 110 buys / 158 eligible / 1,429 scored universe. Overlap with reversal top-16 watch = 1/110; with low-vol sleeve = 0/110; the rev∩lv 'safer rebound' confluence flag fires on 0 rows (16×16 head-list intersection over ~1.5k names, empirically dead — watch∩sleeve is empty even among the 32 listed names, though rev_z_all covers 1,471 names so coverage is not the constraint). The board sort's conviction leg is residual-alpha-led (CN_ALPHA_WEIGHT=0.35, engine/setups.py L37,96-101); rev_z has zero weight in board order.

*Confidence: High — counted on the live artifacts. |board ∩ top-quartile rev_z| per build is the recommended before/after KPI for any redesign, computable from day one in the existing ledger.*

### What is the board's realized factor exposure? (§8 Q7)

Moderate, not extreme: median dist-from-252d-high −32.3% vs universe −26.1% (~1 decile more beaten-down; 1% in the least-beaten decile); small-ADV-tercile share 42.7% vs 33.3%; median ADV20 4.5亿 vs 6.2亿 CNY/day; 20d vol NOT elevated (the #791 extended-demote works); 0 ST names. The winner tail is systematically excluded (120d p90 +18% vs +127%). Factor concentration is real: avg pairwise 120d return corr 0.241 vs 0.168±0.007 for random 110-name baskets (~10σ), PC1 26.4% vs 20.3% — but the shared factor is the common 'fresh bounce-cross' timing, not small-cap junk.

*Confidence: Medium-high — ADV/drawdown/vol legs solid; mcap leg compromised (46% of universe / 49% of board carry the 30亿 placeholder — size exposure is unauditable until a real cap source lands).*

### How much does close-to-close grading overstate capturable returns under T+1/limit-up? (§8 Q2)

5,393 historical take-style entries (~5y, 1,403 names): 21d graded +5.19%/58.6% hit vs T+1 (H+L)/2 fill +4.41%/56.6% → ~0.9-1.1pp per entry, ~2pp hit; buy-the-T+1-high worst bound +2.13%/48.6%. Overnight gap to fill +0.90% (+1.07% beaten-down). Truly unfillable (locked limit all day): 0.22% of entries (5.3% conditional on pinned reference close). Pinned refs: 3.8-5.1% of entries, bias doubles there (10d +2.54%→+0.81%, hit 50%→42.6%). Universe base rates: locked-all-day 0.056%, close-pinned 1.0%. Live 06-30 cohort one-day check: +1.11% graded vs +0.60% fill, 4/60 pinned, 0 locked. Limit-up continuation is ~entirely uncapturable (dip+ZT naive +1.74%/5d collapses to +0.04% fill-realistic, −1.16%/21d).

*Confidence: Medium-high — large n and consistent across horizons, but computed on the survivorship-affected adjusted plane; treat as the honest correction schedule (grade T+1 (H+L)/2, exclude locked, flag pinned, CSI300-relative, never marker-dated), not exact truth. Net expected honest-headline drop: ~2-3pp hit, ~1pp mean at 21d — material, survivable.*

### Sign tests: do the proposed orthogonal confirmers agree with the reversal edge? (§8 contrarian #4)

Raw hot-money LHB flag on dip names: −1.43%/21d fill-realistic excess (cluster-t≈−2.2, 931 obs) — DRAINS; the apparent positive is all in survivorship-inflated up-day flags. Inst-seat LHB (≥2 seats, net buy): +1.57%/21d (t≈0.8, 140 obs) — weak-positive, never negative, probationary. Block-trade premium (the leg as designed): −0.60%/5d (t≈−2.8) — drains. Deep-discount blocks (≤−15%): +3.45%/21d (t≈3.4, 669 obs) — strongest tested dip confirmer. Aggregate gauges vs fwd CSI300: margin velocity +0.035, southbound z +0.022, A/H premium z ≈0 — all dead as timing legs. Southbound also sign-unstable in the pathway record (train −0.16/test +0.49).

*Confidence: Moderate — single 18-24mo regime (blocks 18mo), top-N survivorship universe (21-55% price match), cluster-t; sign evidence, not sizing evidence. Re-run on the W1 PIT universe before wiring weights.*

### Northbound-replacement candidates: availability + ranking (§8 Q4)

Ranked: (1) block-trade deep-discount tape — daily, per-name, genuinely non-secondary-price, 22,472 events fetched 2025-01→2026-06, measured +3.45%/21d t≈3.4; (2) LHB inst-seat net-buy — 21,008 events backfilled 2024-07→2026-06 in minutes, weak-positive, accrue and grade; (3) per-name margin velocity — daily and fast but local cache holds ONE day; ~250 akshare calls/yr/exchange to backfill; UNTESTED (top follow-up); (4) ETF create/redeem — most orthogonal but history starts 2026-06-13, not backfillable, and the current gauge is unit-meaningless (raw share-count sum); (5) A/H premium — 12y backfilled in one call, ≈0 IC, megacap overlap ~nil with the dip pool; (6) southbound — reject as timing; (7) zt/limit counts — froth/veto only. Plus two free levers: raw-LHB and premium-block flags as DEMOTIONS, and the already-validated global AI-semis→CPO weekly slice confirmer (t=3.27, orphaned). Availability correction: the 'no history so can't test' framing is FALSE for LHB/seats/blocks/AH — full-range akshare endpoints verified live from this machine; only attention, ETF shares, limit_breadth, per-name margin are genuinely accrual-gated. Also: northbound net confirmed dead 2024-08-16 (97.3% null since), turnover column still live.

*Confidence: High on availability (actually fetched); moderate on rankings (same caveats as the sign tests).*

### Data-plane integrity spot checks

Tushare plane frozen 2026-06-21 while free siblings are 2026-07-01, preferred unconditionally, invisible to run_status. Adjusted-close seams: 17/300 names >0.4% basis step in 250d (worst 40%), May-dividend clustered. Mid-session partial bars pre-shard-split: 93.9% of names differ from settled close (median 1.2%, p90 4.3%); ledger verified clean so far only via the keep-first accident (120/120 levels match settled). Both price planes adjusted; no raw store exists. zt_pool: 1 date; china_margin_detail: 1 date; LHB local: 5 sessions. Placeholder mktcap 46%; ST screen matches 0 names.

*Confidence: High — all directly measured in this worktree on 2026-07-01.*

### Phase-0 verification (does the §0/§8.1 empirical anchor hold?)

Verified at the primary artifact (research/CHINA_HK_STOCK_SIGNALS.md L98-123, ~790 names, 388 monthly rebalances, 1990→2026): no-gate deepest-quintile rev-3mo +0.56%/mo, Sharpe 0.58, maxDD −37.6%, hit 56%; + turn-confirmation −0.29%/mo, Sharpe −0.29, maxDD −78.9%; + quality floor −0.21%/mo. Every confirmation-style gate tested destroyed the edge with drawdown doubling — neither the current cascade gate nor the old bottoming screen described in the template copy is consistent with the validated construction.

*Confidence: High that the artifact says this; the artifact itself carries not-net-of-cost / high-turnover / survivorship-plane caveats now amplified by the retroactive-deletion finding — the 0.58 is an upper bound.*

## Evidence-based answers to the §8 ten questions

### Q1

Evidence favors the basket/sleeve reframing over the daily act-now unit: the validated construction is monthly-rebalanced, no-gate, EW-relative, and EVERY tested confirmation gate flips it negative (−0.29%/mo, maxDD −78.9%) — so no per-name 'act now' gate re-shuffle can be consistent with the edge. The fill haircut is survivable (~1pp/entry), so fills don't kill a daily surface; what kills it is that the current daily board is ~orthogonal to the edge (1/110 overlap) and the only other validated edges operate at the market-sizing and theme-slice units (GH2-5). Honest partial answer: reversal ships as a periodically-rebalanced, small-per-name-sized basket (its own product); the act-now board is reserved for signals actually validated at the name/day unit — of which there are currently none, which is itself the finding. Minimum name-count is unmeasured; the ~10σ pairwise-correlation elevation says a 5-name cut would be one bet on a bounce regime.

### Q2

Yes, buildable, and the haircut is now measured: T+1 (H+L)/2 entry costs ~0.9-1.1pp per entry and ~2pp hit-rate vs close-to-close (worst bound: buy-the-T+1-high, −3.1pp/−10pp); truly unfillable rows are rare (0.22%) but pinned-at-limit reference closes (4-5% of board-style rows) carry doubled bias (hit 50%→42.6%) and must be flagged/graded from fill only. Preconditions in order: (1) fix china_standout_track store group ('china'→'china_stocks') — nothing grades until then; (2) add Open to _OHLC + backfill, make zt_pool append-only; (3) grade CSI-300-relative on a consistent price basis; (4) never grade from §7 marker dates (+5.7pp/10d look-ahead — the confirmation-day close is the earliest legal anchor). Expected honest headline: ~2-3pp hit / ~1pp mean lower than naive — calibration-material, not product-fatal; §8.7's fear (the honest number kills the product) is not supported at the post-#791 ADV tier.

### Q3

Yes, and it is substantially already built: engine/risk_radar_intl CN_PROFILE is a validated forward-drawdown composite keying on EXTERNAL drivers (US rates/USD/yield-gap) plus breadth — not the internal dip-depth reversal buys — so it does not structurally cancel the edge; it emits a graded gross_factor (1.0→0.62), runs the suite's only closed grade→tune→can_force loop, and is wired into ZERO CN board sizing (live: caution/87 while boards run ungated). Thread gross_factor into the five boards as a sleeve-size chip (display plumbing already shared, few-line change); replace/augment the board's QVIX-only stress overlay (an internal leg from the class the radar's own research calls dead/mean-reverting). Before promoting beyond sizing, run the interaction test: condition reversal-watch forward returns on radar state with the existing ledger machinery. On the second half: name-level timing from close data alone remains unproven — but the seam adds ~2 sessions of latency at the real consumer (bot fires 08:00 UTC before the 12-13 UTC asia build; fills next open), so fix the consumer lag alongside any engine-side latency work.

### Q4

Ranked by measured sign × frequency × orthogonality × availability: (1) block-trade deep-DISCOUNT tape (+3.45%/21d fill-realistic, t≈3.4; daily, per-name, non-secondary-price, 18mo fetched + years backfillable); (2) LHB institutional-seat net-buy (+1.5%/21d, t≈0.8-1.1, never negative — accrue on the forward ledger, not scored yet); (3) per-name margin velocity (fast, untested, needs backfill — next measurer task); (4) ETF create/redeem (most orthogonal, but no history before 2026-06-13 and the current gauge sums unit-incommensurable share counts — fix units, accrue ~1y); reject A/H premium and southbound as timing legs (≈0 IC; southbound sign-unstable and arguably wrong-sign for A-shares in substitution regimes). Two free additions: the raw-LHB and premium-block flags flipped to DEMOTIONS (measured drains, −1.43%/21d and −0.60%/5d), and the already-validated global AI-semis→CPO weekly confirmer (t=3.27, orphaned) for the AI-supply slice. Key availability correction: LHB/seats/blocks/AH are deeply backfillable free via akshare (verified by live fetch) — 'we have no history' is false for the top candidates; upgrade the drip collectors from snapshot-overwrite to range-backfill+accrue. No single candidate breaks the structural lag alone, but #1+#2 are daily per-name event legs, which is the right shape.

### Q5

The cross-repo evidence reframes this: the highest-stakes consumer (Mastermind bot) sees only ONE regime engine (quad) — cross-page contradictions never reach it, but neither does the de-risk tilt or any cycle context, and it independently re-fuses correlated boards with a naive +0.08-per-'independent'-desk bonus. So the choice is not abstract: publish ONE canonical object that carries the disagreement explicitly (quad + tilt-as-sleeve-metadata + radar gross_factor + per-leg as_of + data_through), rather than either forcing one verdict or letting consumers re-fuse raw boards. The disagreement-as-signal idea has a ready-made arbitration template already in-repo: risk_radar_intl's can_force pattern (a leg earns the right to override only after its forward log matures) — apply it per-leg instead of hand-set precedence. Current graders cannot yet answer 'Trough+risk-off: setup or trap?' per historical instance because the pick-surface ledgers are dead/immature (M1) — that mining becomes possible only after the store-group fix and ~2 months of accrual.

### Q6

Three evidence-based design constraints for the partial-pooling scheme: (1) priors must admit NEGATIVE leg weights — two of the doc's proposed confirmer legs measured wrong-sign (raw LHB, premium blocks), so shrinkage toward a 'weakly positive' prior would institutionalize a drain; shrink toward zero, not toward optimism. (2) Effective-N inputs now exist to seed reliability weights: backfilled event legs carry n=140-931 dip-flagged obs with cluster-robust t's, and the leakage-tax probes give per-feature flip rates (5% plane, 8.3%/day bucket) that should enter as measurement-error inflation on each leg's IC. (3) Graceful degradation is empirically mandatory: for ~90% of the universe no validated positive confirmer exists, so an AND-gate goes dark almost everywhere (GH2-9) — the ensemble must degrade to the reversal-only prior with a widened interval, which is exactly what shrinkage does and AND-gating cannot. Reuse the risk_radar_intl bounded-tuner as the update mechanism (bounded steps, capability gates) rather than free-fitting weights on tiny n.

### Q7

Measured: the board is NOT the extreme small-cap junk bet suspected — #791's ADV floor + extended-demote already sanded the tail (median ADV 4.5亿 vs 6.2亿; vol not elevated; 0 ST). Residual exposures: ~1 decile more beaten-down than universe, 42.7% small-ADV tercile, systematic exclusion of the winner tail, and REAL factor concentration (pairwise corr 0.241 vs 0.168±0.007, ~10σ; PC1 26.4% vs 20.3%) — but the latent factor is the shared 'everyone just crossed' bounce-timing, not size. Verdict: size/liquidity-neutralization is NOT the top precision lever; a correlation/factor-spread cap or an explicit 'one bet on a bounce regime' sleeve-sizing note is. Per-name neutralization would forfeit the beaten-down tilt the edge lives in. Caveat: size exposure is formally unauditable until real mktcaps land (46-49% placeholder) — one akshare/tushare total_mv join away. Capacity at this tier: locked-limit entries are rare (0.22%), so the T+1 constraint taxes rather than blocks.

### Q8

Partial yes — but not at name selection. The repo record holds ~5 validated findings across DIFFERENT units: (1) 3M within-sector reversal — the only cross-sectional name-selection edge; (2) forward-drawdown radar composite — market-sizing unit, validated, unwired; (3) global AI-semis→CN-CPO weekly confirmer — theme-slice unit, t=3.27, survives the horse race pre-2024, fully orphaned; (4) low-vol tilt — defensive sleeve (Q1 Sharpe 0.98 vs 0.88 mkt), explicitly not long-short alpha; (5) sector washout↔euphoria signature — descriptive phase context only. Per-name washout/reclaim has NO cross-sectional validation (and adjacent confirmed-reclaim designs were refuted); no OOS test of low-vol/pathway independence from reversal on a survivorship-corrected universe exists — and cannot exist honestly until the china_search retroactive-deletion is stopped, since the current plane deletes reversal's worst outcomes. So the honest architecture falls out: reversal = selection; radar = sleeve size; AI-semis = slice confirmer; washout = context. §8.6's suspicion ('one thin edge + regime sizing') is right for selection; the doc's error was treating the sizing/slice edges as nonexistent rather than unwired.

### Q9

Least-measured question; no direct reflexivity test was run. Indirect evidence: post-#791 the board's liquidity tier is not fragile retail-nano — median ADV20 4.5亿 CNY/day (~US$60M), where plausible user-scale AUM cannot move names; the locked-limit cohort (the classic reflexive-trap tier) is 0.22% of entries and mostly excluded by the ADV floor. The measured capacity constraint is fill TIMING (~1pp overnight gap paid by everyone who waits for the same confirmation), not market impact — which argues the reflexivity risk is signal-crowding at the entry bar, mitigated by the basket/periodic-rebalance framing (Q1) that spreads entries. Flag honestly: no user-AUM threshold was computed; if the product grows, the right instrument is the forward ledger itself (slippage between reference close and realized fills widening over time is the reflexivity alarm), which requires the fill-realistic ledger to exist first.

### Q10

Answered definitively: NO — W1/#807/#809 cover US FRED/ALFRED macro legs only (engine/pit.py VINTAGED_SID_TO_COL all-US; shadow_pit_regime has zero china refs; #808 stamps TSF only on the GTAA path the board never consumes). Nothing replays rev_z, washout-2W, the cascade, or board order as-of. The harness is cheap to build: tests/test_vector_pit.py truncated-replay is the proven template, and the probes already reproduce the ledger 60/60 on the correct plane. Measured leakage-tax seeds to report: 5% row-flip if replayed on the wrong price plane (features must replay on their OWN store), 8.3%/day washout flag-flip on completed-vs-live 2W buckets (persist bucket_end next to asof; confluence_tiers already computes per-bucket 'known'), 0.7% of names/2d price-vintage revision (median 1.4%) — git-committed closes/members parquets form a free ALFRED-analog vintage matrix. Plus two guards: refuse/tag boards whose same-day panel row was collected before 07:00 UTC, and gate ledger appends to the asia lane explicitly (currently a keep-first accident). Build order: M1 store-group fix → replay harness + bucket-completeness → vintage/session guards → grader-bias fixes (relative returns, fill realism, marker-date rule) before any grader-feeds-rank change.
