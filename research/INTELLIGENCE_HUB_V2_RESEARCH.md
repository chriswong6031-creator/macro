# Intelligence Hub V2 — Findings Brief

**From "ranks already-run-up leaders by desk agreement" to an institutional engine that surfaces ASYMMETRIC, PRE-CONSENSUS, underpriced ideas.**

Status: research synthesis, decision-grade. Code mechanisms cited are verified against this checkout (`/tmp/macro_main`). Folklore is quarantined out of the BUILD list. Where two research lenses disagreed, the contradiction is resolved explicitly (§4.0).

---

## 1. The diagnosis — why today's hub only echoes consensus

The hub (`engine/intel_hub.py`, built by `scripts/build_intel_hub.py`, rendered by `templates/intelligence_hub.html.j2`) is a **pure fusion-and-ranking layer** over five feeder desks. It does not discover names — it re-reasons over already-published per-ticker artifacts and re-ranks them. Four compounding mechanisms force it toward consensus.

### 1.1 Universe selection bias — a name cannot enter until a desk already flagged it
The hub's universe is whatever `engine/intelligence.py` emitted, and that is a literal set-union of feeder outputs:

```
# engine/intelligence.py:242
universe = set(news_tickers) | set(mm_index) | set(alt_by_ticker) | set(ridx) | set(sidx)
```

then filtered to names where `any((news, alt, radar, standout))` is truthy (`intelligence.py:252`). The five feeders are each themselves a recognition gate:

- **News** (`site/news/by_ticker.json`) — only names with editorial headline flow (something already happened / is being reported).
- **Alt-data** (`site/altdata/mastermind.json` + `by_ticker.json`) — `_alt_for` admits a row only with an active convergence channel / `convergence_score` (`intelligence.py:64`).
- **Radar** (`site/basketdata/radar_ticker.json`) — `_radar_for` **drops any name whose `state == "QUIET"`** (`intelligence.py:79`), so only names already in POSITIVE/NEGATIVE_DIVERGENCE or CONFIRMED_UP/DOWN survive.
- **Buy-board** (`site/factordata/us_standouts.json["buy"]`) — `_standout_for` reads the `buy` key only (`intelligence.py:91`); the US buy-board ranks by sector-neutral residual-momentum (`engine/setups.py` → `engine/residual_alpha.py`), so membership means **RS/momentum already positive**.
- **Policy** — sector-proxy, default-off (needs a DEEPSEEK key); reaches names only via theme→sector dilution.

`intel_hub.build()` then iterates `bundle["tickers"].items()` (`intel_hub.py:364`) — no fresh screen, no cap-floor, no off-universe candidates. **The pre-event / pre-flow / pre-news name that nobody is writing about, that isn't on a buy-list, and whose tape hasn't moved is invisible by construction.**

### 1.2 Agreement = consensus ranking — agreement enters the score THREE times
Per ticker each desk is collapsed to a sign in {+1,0,−1} (`_dirs`, `intel_hub.py:166-184`). Then (`intel_hub.py:206-216`):

```
agreement   = abs(sum(nz)) / len(nz)                 # 1.0 unanimous, 0 split
base        = brain.priority OR (0.5*(n_present/5) + 0.5*agreement) * strength
conf_bonus  = min(1.25, 1 + 0.08*max(net_confirm-1, 0))   # up to +25%, grows per agreeing desk
composite   = 100 * base * conf_bonus * fals_pen * (0.6 + 0.4*agreement)
```

Agreement enters **(a)** inside `base`, **(b)** as the `0.6 + 0.4*agreement` multiplier, and **(c)** indirectly via `conf_bonus` on `net_confirm`. `brain.priority = confidence*strength`, and `confidence = 0.5*breadth + 0.5*agreement` (`intelligence.py:186`), so breadth/agreement dominate the base too. The final sort is:

```
# intel_hub.py:367
dossiers.sort(key=lambda d: (d["composite_conviction"], d["n_confirm"]), reverse=True)
```

High agreement is a **lagging** condition: it only forms once a move has been independently recognized by multiple observers. So the top of the command list is, by construction, the maximally-confirmed, maximally-broadcast cohort. The engine literally labels this cohort `"confirmed_trend → … consensus, less edge left."` (`_read_for`, `intel_hub.py:277`) — yet that is exactly what floats to the top. **Early-and-lonely is penalized twice:** low breadth shrinks `base`, and no agreeing peers means `conf_bonus` stays at 1.0 (needs `net_confirm ≥ 2`).

### 1.3 No priced-in axis — the data to build one is computed then discarded
The hub flattens every facet to a sign for the agreement count and throws away the magnitudes that measure *how much is already discounted*. Confirmed wasted fields, all present on the feeders, none used in ranking:

- `radar.rs_vs_spy_60d` and `alt.rs_vs_spy_60d` — relative strength vs SPY (the natural "how far has it run" input).
- `standout.off_high`, `standout.alpha_entry` — literal distance-from-high / entry-quality (remaining-upside proxies).
- `alt.extended`, `alt.clamped` — explicit upstream **anti-chase** flags, ignored by the dossier.
- `radar.edge_score` / `lifecycle` / `within_basket_pct` — graded edge magnitude + lifecycle stage, collapsed to ±1.
- `news.sentiment_score` magnitude — used only as a `loud_bull` gate, not as a crowdedness gauge.
- `alt.weighted_score` / convergence richness — thresholded to a binary at 65/35.

There is **no term anywhere** that rewards a name for being early/lonely or penalizes it for being extended/priced-in. The one `isolated` flag that marks idiosyncratic/early names is set in `_peer_confirm` **after** ranking (`intel_hub.py:319-323`), conflates "early" with "data-sparse", and never lifts a name's rank; `theme_wide` (≥2 confirming peers) is treated as the *preferred* state — the design philosophically prefers the crowded theme.

### 1.4 Lagging-to-coincident feeders
Of the five legs, only the divergence radar's activity-vs-price (POSITIVE_DIVERGENCE / `edge_score`) is genuinely **leading** — and even that is parasitic on the alt-data `signal_score`. News flow, news velocity/sentiment magnitude, factor buy-board membership (RS/momentum already up), and policy theses (react to announced intent) are coincident-to-lagging. The two genuinely leading desks (alt, radar) are stripped to a direction sign with their early magnitude discarded. Net: a name scores highest precisely when news + momentum + price have **already** confirmed.

---

## 2. The reframe — rank by EDGE REMAINING, not desk agreement

### 2.1 The lifecycle model
Every idea moves through four stages. Desk agreement is a **proxy for lifecycle stage**, and the current hub ranks the proxy in exactly the wrong direction:

| Stage | What's true | Desks firing | Edge remaining | Current hub treatment |
|---|---|---|---|---|
| **Emerging** | one leading desk hot, tape quiet, low run-up | 1 (radar/alt) | **highest** | sinks (low breadth, no `conf_bonus`) |
| **Early-confirmed** | leading desk + one corroborator, RS still modest | 2 | high | mid-pack |
| **Consensus** | news + momentum + price all agree | 4–5 | **low** ("less edge left") | **floats to top** |
| **Exhausted** | loud-bull tape, smart money fading, RS stretched | news loud, alt/radar negative | negative | flagged `crowded_top` but not demoted in rank |

### 2.2 The principle
**Rank by edge remaining, not by how many desks agree.** Concretely:

1. **Invert the agreement reward.** Replace the "more agreeing desks = more score" bonus with a term that pays a **leading desk firing while the lagging desks are still silent** — score the *gap* between leading and lagging legs, not total breadth. "Three desks quiet, one leading desk hot" should out-rank "five desks agree."
2. **Add an edge-remaining axis** (§5b) built from the already-computed-but-discarded fields, and sort on `(edge_remaining, conviction)` instead of `(conviction, n_confirm)`.
3. **Discount priced-in euphoria in the rank**, not just label it. High news velocity + high positive sentiment magnitude + stretched RS ⇒ haircut.
4. **Prove, don't assert, that a signal leads** (§5c) — measure each signal's forward IC and lead-time before it is allowed to promote a name.

---

## 3. The data substrate — available leading sources

Collectors wired via `scripts/collect.py`; nearly all degrade to "blocked" (never fatal) when a key is missing. Lead-time is vs price.

| Source | File | Keyless? | Cadence | Lead-time | Pre-consensus signal it powers |
|---|---|---|---|---|---|
| **SAM.gov pre-solicitations** | `collectors/sam_gov.py` | **No (gated, free key)** — currently dark | as posted | weeks → 12mo before award | First-mover federal-money: FOA/pre-sol count accelerating while RS flat |
| **Grants.gov FOAs** | `collectors/grants_gov.py` | **No (gated, free key)** — dark | as posted | weeks → months | Policy-driven demand before sector revenue (theme leg) |
| **USAspending obligations** | `collectors/usaspending.py` | **Yes** | monthly | award→revenue 1–4q | Contract-award velocity per supplier (definitive ≫ IDIQ) |
| **EDGAR 8-K material items** | `collectors/edgar_8k.py` | **Yes (UA only)** | filing-time | hours → ~4 biz days | Item 1.01/2.01/8.01 clusters before the news narrative |
| **EDGAR Schedule 13D/13G** | *not built* (same EFTS pattern) | **Yes** | filing-time | ~5 biz days, drift 12–18mo | Activist initiation — hard dated smart-money event |
| **EDGAR RPO** | `collectors/edgar_rpo.py` | **Yes** | quarterly | leads recognized rev several q | Forward-demand factor (currently unfused) |
| **SEC Form 4 (opportunistic)** | `engine/insider_factor.py` + `collectors/sec_insider.py` | **Yes** | ~2 biz-day lag | 63d | Opportunistic insider *clusters*, role-weighted, mcap-norm |
| **ClinicalTrials.gov v2** | *not built* | **Yes** | self-archived snapshot | weeks → months to readout | Phase-3 start / readout-due calendar |
| **openFDA + PDUFA calendar** | *not built* (openFDA keyless) | **Yes** | dated | months (calendar IS the lead) | Biotech catalyst risk-shape + confluence |
| **Analyst revisions** | `collectors/equity_revisions.py` | **Yes (yfinance)** | snapshot, PIT accruing | weeks → months pre-earnings | Revision breadth/momentum (needs ~1y PIT vintages first) |
| **Polygon options chain (per-strike)** | `collectors/polygon_options.py` | No (Polygon key) | EOD, PIT-persisted | days | Call-OI buildup, 25Δ risk-reversal steepening, IV-rank |
| **Cboe SKEW / VIX futures** | `collectors/cboe_indices.py`, `cboe_vix_futures.py` | **Yes** | daily | days | Tail-risk regime context |
| **Web traffic (free analogues)** | *not built* | **Yes** | daily | weeks → 1q | Wikipedia pageviews + Google Trends + Cloudflare Radar abnormal traffic |
| **Prediction markets** | `collectors/prediction_markets.py` | **Yes** | snapshot | forward-implied | Fed/recession odds, market-implied macro |
| **GitHub / HuggingFace velocity** | `collectors/github_repos.py`, `huggingface.py` | **Yes (opt token)** | daily | noisy | AI/dev-tool **theme** adoption only (gameable) |

The genuinely-leading sources (SAM/Grants FOAs, 8-K filing-time, RPO, 13D, `_first_seen` observation-latency) are mostly collected-but-unfused or dark. The wired path leans on coincident/lagging confirmation feeds.

---

## 4. The opportunity catalog (GRADED)

### 4.0 Resolved contradiction — Cohen-Frazzini supplier/customer-link momentum: DO NOT BUILD
The two research lenses disagreed sharply on this. The altdata-nowcast lens called it the #1 top-pick ("strong, scoreable, highest EV") citing Cohen-Frazzini (2008, JF, ~106-122 bps/mo). The cross-sectional lens graded the **same effect** "folklore / SEVERE / value-weighted L/S not significantly different from zero / NEGATIVE 2005-2018 / lowest-EV." **Resolution: the "strong" grade is the 2008 in-sample result; post-publication evidence (the value-weighted long-short return is insignificant and was negative 2005-2018) shows the attention gap was arbitraged away.** Equal-weight micro-cap versions that "work" are net-of-cost mirages. The 8-K-velocity refinement that was proposed on top of it is entirely unvalidated and sits on a dead foundation. **This goes to DO NOT BUILD.** (The 8-K *material-event-velocity* leg can still be built on its own merits as a filing-time recency signal — see BUILD — but **not** as a customer-supplier link-momentum factor.)

### 4.1 BUILD (real edge, accessible, honest grade)

| Framework | Grade | Mechanism | Data | Recipe | Decay / crowding |
|---|---|---|---|---|---|
| **Insider opportunistic-cluster buying** | moderate | Off-cadence (non-routine) distinct-insider clusters, role-weighted, mcap-normalized = direct pre-reprice conviction | `engine/insider_factor.py` (built, FDR-surviving) + `collectors/sec_insider.py` (keyless) | `net_usd/mcap`, `opp_buyers/n_buyers`, 6-mo filing window, sector-neutral z; **LONG-ONLY top-quintile confirmer**, never a standalone sizer | Moderate. Orthogonal to mom/size/reversal (corr ≈ −0.02/0.05/0.02). **Honest ceiling: L/S fails DSR (0.53–0.89); long-only sits ON the DSR boundary (0.82–0.85). A confirmer, not an alpha.** |
| **Analyst estimate-revision breadth & momentum** | moderate | Sell-side revisions are sticky/herd; breadth + consensus drift lead price pre-earnings | `collectors/equity_revisions.py` (live + `history.parquet` accruing PIT) | breadth = (up30−down30)/(up30+down30); est_chg_30/90d; sector-z. **Pre-earnings confluence tilt only.** | Moderate, slower decay than PEAD. **Blocked locally: yfinance is snapshot-only → backtest is lookahead-contaminated until ~1y of forward PIT vintages accrue + clear FDR/DSR.** Headline 7.6%/yr decile spread is an unverified external (Mill Street) number. |
| **13D/13G activist initiations** | moderate | Credible campaign (board seats/breakup/sale) underreacted initially → pop + multi-month drift | `collectors/edgar.py` EFTS pattern (reusable); `engine/smart_money.py` CUSIP→ticker. **Net-new collector.** | Poll EDGAR for SC 13D/13D-A daily; resolve target; tag vs curated activist list; emit event-driven desk (`ipo_radar.py` shape). **Event-study Phase-0 first; tilt/overlay, not a continuous factor.** | Low-moderate. Largest event AR in the set, BUT the **13D window shrank to 5 days (Feb-2024 SEC rule) — every pre-2024 AR estimate is from a different regime and overstates capturable drift. Re-event-study post-2024.** Edge concentrated in mid/small-caps + lesser-known activists. |
| **USAspending contract-award velocity** | moderate | Federal awards = funded backlog → revenue over 1–4q; no press coverage → limited-attention underreaction (~7mo persistence) | `collectors/usaspending.py` (keyless); `usaspending_assistance` leg already shipped (PR #337). **Net-new: definitive-contract obligated-$ velocity + UEI→ticker crosswalk.** | Trailing-3m obligated-$ summed over actual award dates (FLOW — never forward-fill), YoY/3m-accel, weight definitive ≫ IDIQ; CONTEXT chip + `theme_event` radar leg | Low-moderate. Large-cap defense primes crowded by vendors; residual in sub-$2B suppliers. **UEI→ticker crosswalk error rate is unquantified and load-bearing — audit it in Phase-0; a 20–30% misattribution erases the edge.** ~7mo figure is practitioner-sourced, not top-journal. |
| **EDGAR 8-K material-event velocity (filing-time recency)** | moderate | Item 1.01/2.01/8.01 filings hit at filing-time, before the news narrative crystallizes; rank by `_first_seen` observation-latency not event date | `collectors/edgar_8k.py` (keyless); `material_8k` channel on main | Weight fresh item-1.01/2.01/8.01 clusters; rank "days since WE first observed"; fuse as a 6th "filings" facet | Fresh / less crowded. **Stands on its own — NOT as customer-supplier link momentum (§4.0).** |
| **Special-situations event fusion** | moderate | 13D activist, 13G→13D flips, tender/going-private, S-4/Form-10 spins = hard dated catalysts orthogonal to momentum | `engine/special_situations.py` (built, full classifier + `site/special_situations.html`) — **verified NOT fused into intel_hub/intelligence/briefing** | Wire the existing classifier into the per-ticker hub as an event-driven catalyst leg | Low-moderate. Event-sparse → tilt/overlay. The classifier already exists standalone; this is plumbing, not new research. |
| **Web-traffic revenue nowcast (free proxies)** | mechanism strong / **free-proxy weak** | Digital traffic = near-real-time top-line demand; underreaction persists past quarter-end (Konchitchki et al., *The Accounting Review*) | Net-new: Wikipedia pageviews + Google Trends + Cloudflare Radar (all keyless; **Cloudflare CC BY-NC → private use only, never publish**) | Abnormal traffic vs de-seasonalized baseline → revenue-surprise CONTEXT signal; Phase-0 gate | **The STRONG grade is for PAID SimilarWeb and does NOT transfer.** Free proxies are far noisier; realistic IC modest-to-unknown. Treat as confluence, validate before any scoring. |

### 4.2 BUILD — pillar infrastructure (not a factor, the scaffolding §5 needs)
- **Resurrect `engine/predictive_signals.py`** — verified imported only by `scripts/conviction_v2_measure.py` / `conviction_v2_regime.py` (shelved in measurement scripts, not in any `build_*`). Its `near_52w_high` + `fip_continuity` (frog-in-the-pan) + `downside_asym` legs distinguish *continuous early leaders* from *parabolic late ones* — directly the edge-remaining axis. Gate through the existing validation battery; let it **down-rank high-RS-but-discontinuous** names (the run-up trap).
- **Generalize `engine/radar_ic.py` into a hub-wide discovery track-record** (§5c).

### 4.3 DO NOT BUILD (folklore / decayed / net-of-cost mirages)

| Framework | Grade | Why it's out |
|---|---|---|
| **Cohen-Frazzini supplier/customer-link momentum** | folklore | §4.0 — value-weighted L/S insignificant, negative 2005-2018; attention gap arbitraged away. Build cost (10-K link graph) high, edge dead. |
| **PEAD / SUE as a scored standalone** | weak→dead | Repo's own deep survivorship-clean panel killed it: IC 0.033 (shallow) → **0.0006 (deep), t_HAC 2.81 → 0.06, fails BH-FDR, dollar-neutral net Sharpe NEGATIVE (DSR≈0.001).** `engine/sue.py` keeps it as display/context. Do NOT let "freshness-decay" weighting resurrect a dead signal without a fresh deep-panel Phase-0. |
| **Short interest / days-to-cover / squeeze** | severe mirage | The alpha IS the borrow fee (paid away), concentrated in the illiquid hard-to-borrow short leg. Repo's FINRA factor **failed FDR (q=0.32, "size in disguise", sign-flips)**; free FINRA is snapshot-only. Risk-flag only. |
| **Naive aggregate insider net-$ buying** | folklore | Confounded size/noise gadget mixing routine grants + sales; "never IC-tested display gadget." Only the decomposed cluster build (§4.1) carries edge. |
| **13F "most-held / smart-money"** | weak | Structurally 45+ days stale, copycat-crowded. `engine/smart_money.py` is correctly CONTEXT-ONLY (never scored). Legitimate as "who owns this" + a CONTRARIAN crowding fragility flag, not a lead. |
| **Neglected-firm / low-coverage premium** | weak standalone | Nonstationary, decayed, largely size/illiquidity in disguise; S&P1500 has ~no truly-neglected breadth. Durable only as an **interaction conditioner** amplifying momentum/revisions among low-coverage names — never a standalone tilt. |
| **GitHub stars as adoption** | folklore | ~6M suspected fake stars, gamed for VC optics, stars ≠ installs ≠ revenue. If anything, commit/contributor velocity with a fake-star guard — theme-color only. |
| **HuggingFace trending as a per-name signal** | folklore | ~6-week engagement half-life; publishers (Alibaba/DeepSeek/Meta) mostly not cleanly tradeable US names. Theme-color only. |
| **Patent KPSS as a scored factor** | moderate but redundant | Overlaps existing quality/profitability/growth; marginal (net-of-incumbent) IC never measured and is the only number that matters. Slow quality overlay at most, low standalone Sharpe. |

---

## 5. The three new engine pillars

### (a) DISCOVERY / scan layer — bring in names NOT already in the desks
**The structural fix for §1.1.** Decouple universe membership from the lagging news/buy-board feeders by admitting names that clear a **leading-only pre-screen** even with zero news and no buy-board membership:
- Radar **QUIET-but-accumulating** (activity-z rising while price-z flat) — currently dropped at the `state == "QUIET"` gate.
- **Options positioning** mined from the persisted `polygon_options` per-strike chain (call-OI buildup, steepening 25Δ risk-reversal, IV-rank expansion) ahead of price.
- **Federal-money first-movers**: SAM.gov pre-solicitation / Grants.gov FOA acceleration (unblock the free keys) and USAspending definitive-contract velocity, before the award is price-visible.
- **EDGAR 8-K filing-time clusters + 13D initiations** (event-driven, name enters on the filing).

Feed `engine/theme_discovery.py` (forming-theme clusters, currently disconnected from the hub) gated by `theme_crowding.py` / `theme_extension.py` so the hub **prefers nascent low-crowding themes** and flags late/parabolic ones — an explicit early-vs-late axis at the universe level.

### (b) PRICED-IN / EDGE-REMAINING axis — and rank on it
**The structural fix for §1.2/§1.3.** Build an `edge_remaining ∈ [0,1]` per name entirely from fields the pipeline already computes and discards:
- run-up: `radar.rs_vs_spy_60d`, `alt.rs_vs_spy_60d`
- entry quality: `standout.off_high`, `standout.alpha_entry`
- anti-chase: `alt.extended`, `alt.clamped`
- lifecycle: `radar.lifecycle`, `radar.within_basket_pct`
- crowdedness: news velocity (`accel`, `prior_avg`) + `sentiment_score` magnitude as a **discount**, not a `crowded_top` label
- continuation quality: `predictive_signals` `fip_continuity` / `downside_asym` (§4.2)

High agreement + high run-up + extended ⇒ LOW edge_remaining (demote). Single leading desk + early lifecycle + not-extended + low run-up ⇒ HIGH edge_remaining (promote). **Change the sort key from `(composite_conviction, n_confirm)` to `(edge_remaining, composite_conviction)`** and **invert `conf_bonus`** into a leading-vs-lagging breadth-gap reward.

### (c) Falsifiable SIGNAL TRACK-RECORD — measure, don't assert
**The structural fix for §1.4 and the honesty gate.** The repo already has the machinery — it's just not generalized: `engine/radar_ic.py` snapshots `edge_score` per subject, matures against forward rel-return, computes Spearman IC + bucket hit-rate. **Verified state: 191 snapshots, 0 matured; `data/radar/track_record.json` scored_total=0** — the loop exists but has produced no graded signal yet.

Generalize it into a hub-wide discovery track-record:
- Snapshot **every** hub leading-signal's daily score per ticker → `data/hub/signal_snapshots.jsonl` (idempotent by `date|signal|subject`).
- Mature at **multiple horizons (5/10/21/63d)** to expose where each signal's IC *peaks* = its true lead-time (the current harness only blesses 63d-maturing signals after they've already led for a quarter).
- Reuse `engine/validation.py` `ic_summary` / `newey_west_tstat` verbatim; run a **lead/lag discriminator** (contemporaneous vs forward vs lagged IC over [−21..+21d]) and gate "leading" on a positive partial-IC controlling for 200dma + realized vol — the house's own anti-coincident-artifact test.
- **Auto-demote** scored→confirmer→display when rolling-90 IC drops below ~0 / HAC-t flips for K builds, turning the static `signal_lab` graveyard into a live one.
- Stand up the **outcome-labeling job** `engine/signal_archive.py` was built for (a PIT parquet of daily outputs exists but nothing joins it to forward returns) → feeds `brier_reliability` + `benjamini_hochberg` across the live signal panel.

A claimed edge that hasn't matured in this loop may **flag** a name but may **not promote** it in rank.

---

## 6. Quick wins vs heavy builds

**Quick wins (S — days):**
1. **Stop discarding the priced-in fields** — wire `rs_vs_spy_60d`, `off_high`, `alpha_entry`, `extended`/`clamped` into an edge_remaining score and re-sort. No new data; data is already on the feeders.
2. **Turn `loud_bull` into a rank discount** — high velocity + high positive sentiment magnitude haircuts conviction instead of only emitting a `crowded_top` flag.
3. **Make `isolated` a positive pre-ranking promoter** with a real proxy (leading desk hot + low run-up + peers not confirming) rather than a post-hoc 45-conviction leftover; keep `theme_wide` as a separate later-stage tag.
4. **Fuse the existing `engine/special_situations.py`** into the hub as an event leg — classifier already built, just plumbing.
5. **Unblock SAM.gov + Grants.gov** (register the free keys) and promote their already-wired radar legs to a first-mover score.

**Heavy builds (M/L — weeks):**
- (M) Generalized discovery signal track-record + multi-horizon maturation + lead/lag discriminator + auto-demote (§5c).
- (M) Edge-remaining axis as a first-class pillar + `predictive_signals` resurrection (§5b, §4.2).
- (M) Inverted agreement → leading-vs-lagging breadth-gap reward (§2.2).
- (M) USAspending definitive-contract velocity + UEI→ticker crosswalk with accuracy audit (§4.1).
- (M) 13D/13G collector + post-2024-regime event study (§4.1).
- (L) Full discovery universe expansion: radar QUIET-but-accumulating + options-positioning pre-screen + theme_discovery/crowding lifecycle gate (§5a).
- (L) Outcome-labeling job over `signal_archive.py` (§5c).
- (L) Web-traffic free-proxy nowcast collector + Phase-0 (§4.1).

---

## 7. Open questions for the user

1. **Scope** — US-only first (where the substrate is richest), or propagate the edge-remaining axis + discovery layer to China/HK/CA/Intl hubs in the same pass? (The CN/HK stacks already mirror much of the US engine.)
2. **Free vs paid data** — confirm the free-only doctrine holds. The strongest-evidenced nowcast sources (SimilarWeb web traffic, LinkUp job postings, Apptopia app data, single-name CDS) are **paid and already crowded among funds**; our edge is the noisier free analogues + PIT data-engineering moats. Are SAM.gov / Grants.gov free-key registrations approved (they need a SAM entity registration)?
3. **Daily vs intraday** — the hub is a once-daily static build. The options-positioning and 8-K filing-time signals have intraday lead-time that an EOD build partly wastes (`gex_engine.py`'s own docstring admits the free Cboe feed is EOD-delayed and misses 0DTE flow). Is intraday refresh in scope, or do we accept EOD and lean on filing-time/federal-money signals whose lead-time survives a daily cadence?
4. **Risk tolerance for unvalidated promotion** — the honest gate (§5c) means new signals can only *flag* until they mature (months). Acceptable, or do we want a provisional "candidate" tier that surfaces unvalidated leading signals with a loud "unproven, measuring" badge?
5. **Backfill the validation history** — several top signals (analyst revisions, web traffic, ClinicalTrials status) are snapshot-only and need ~1y of forward PIT vintages before they're trustworthy. Start the accrual clocks now even though they pay off later?

---

### Modalities flagged as missing by review (for a future pass, not this build)
Single-name credit/CDS-vs-equity lead-lag (repo only has macro credit-to-GDP via `engine/credit_cycle.py`); ETF primary-market creation/redemption flows (`etf_pulse.py` is ratio-return only); index reconstitution / float-rebalance forced-flow (Russell June, S&P add/delete); merger-arb deal spreads; sell-side **initiations** as distinct from revisions; options-implied skew as a cross-sectional *return* predictor (Xing-Zhang-Zhao) vs the current gamma-levels-only use; earnings-call transcript language signals; CFTC COT positioning for the macro overlays. **None graded here — listed so they aren't mistaken for analyzed-and-rejected.**
