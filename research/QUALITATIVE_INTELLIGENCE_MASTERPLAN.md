# Qualitative-Intelligence Masterplan — the shared spine for Fable

*This is an Opus adversarial audit of what SHIPS TODAY across the Mastermind dashboard's ~15 qualitative-intelligence desks (US + China), written 2026-07-02. It is the unifying framework that the two region audits (`research/QUALITATIVE_SIGNAL_US_AUDIT_FOR_FABLE.md`, `research/QUALITATIVE_SIGNAL_CHINA_AUDIT_FOR_FABLE.md`) and the news-feed audit (`research/NEWS_FEED_PROBLEM_AUDIT_FOR_FABLE.md`) both reference. It is built from parallel deep-read audits of each desk plus an adversarial verification pass, an acquisition/methodology/architecture strategy pass, and a dedicated news-core diagnosis; verifier verdicts are folded in (REFUTED findings dropped, citations the verifier corrected are corrected here, and CONFIRMED missed problems are added). Every claim is cited `file:line` or quoted as an artifact byte, and was checked against the live repo. Where a vendor fact is unverified, it is marked so — a fabricated-looking figure is worse than none.*

---

## 0. The one-sentence diagnosis

**The dashboard runs ~15 qualitative desks as forked silos that each ingest headline/artifact-only inputs, reduce them to a hand-authored, never-backtested "importance" number, and render that number with quantitative authority — but not one desk has ever closed the loop from a qualitative call to a graded outcome, so the system is structurally incapable of learning what matters, and the "calibrated by the ledger" framing is aspirational everywhere.**

Concrete shipped state, quantified:

- **The one scored news→signal hop has zero matured observations.** `site/basketdata/radar_ic.json`: `n_snapshots: 2489, n_matured: 0, ic_all: null`; `radar_track_record.json`: `scored_total: 0, open: 95`. After 2,489 accrued snapshots, no news-derived call has ever been graded.
- **The Alt-Data brain ships DARK while the header still sells conviction.** Artifact shows `theses:[]`, `degraded_reason:"llm_error"`, all 30 signals deterministic-WATCH; the `signal_score→radar` path has `n_scored:0`, yet the desk header advertises "AI conviction, graded vs SPY."
- **Every accountability ledger is empty by construction.** Alt-Data: 132 open theses, earliest `check_by` 2026-09-18, `scored_total:0`. Policy Watch: every prediction perpetually "open" (`scored_total:0, open:7` on the 2026-07-02 main ledger). White House: zero activated alerts in all git history; ledger/state dirs never existed. Congress: no forward grader at all.
- **China News ships a dead render freezing live data.** `build_china_news.py:73` passes `news=` but the template reads `china_news`, so the intel engine's render is dead and `chinanews/{sentiment,feed,by_ticker}.json` are frozen at 2026-06-22 while the parquet is fresh to 07-01.
- **Every noise/importance threshold is a hand-authored constant, none fit.** `macro_news.py:461-492` (base 22, `+min(40,14*len(hits_hi))`, bands high≥72/medium≥48); `news_common.quality_score` `_TIER_WEIGHT{1:1.0,2:.82,3:.58}`; `altdata_models.py:124-126` (`_GOV_FLOOR=$5M`, MSPR≥20, options mult 3.0); `build_congress.py:45-52` (`W_CLUSTER/TECH/ZONE=0.40/0.35/0.25`). A grep for `backtest|calibrat|IC` across the importance scorers returns nothing.
- **Importance is defined N times, learned zero times.** `event_id`/`norm_title`/`source_tier` exist twice (`news_common.py` for US, `china_news_intel.py` for China); `build_entity_map` has exactly one downstream consumer (`financial_news`); 7+ ledger dirs (`data/ai_desk`, `data/altdata`, `data/policy_intent`, `data/radar`, `data/master_brain`, `data/thematic_desk`, `data/narrative_brain`) never join.

---

## 1. The keystone — no outcome-feedback loop, so the system can never learn what matters

The single deepest problem is not any one dark brain or frozen constant. It is that **the entire qualitative suite is architecturally incapable of learning "what matters" from results.** Every symptom in every desk cascades from this one absence.

Trace the intended pathway and watch it break at the same accountability point in every desk:

1. **The raw material is capped at artifacts, not facts.** The US news core has no article body anywhere — GDELT artlist returns only `{title,url,domain,seendate}` (`news_common.py:594`), Google-News descriptions are discarded (`news_rss.py:177` `summary=""`), and the template concedes "no article body exists in the feed" (`templates/news.html.j2:16-17`). China's state-media tone is `(pos−neg)/items` over 35/32 hand-picked words (`collectors/china_news.py:47-58`, self-labeled "deliberately CRUDE"). Every "importance" score downstream operates on ~10-15 words of headline or a bag-of-words count.

2. **"Importance" is asserted, never measured.** The core "signal vs noise" decision is a static additive keyword scorer in every desk (`macro_news.py:461-492`; `news_common.quality_score`; `china_news_intel.importance_score` = tier×theme×keywords×proximity×novelty, explicitly flagged "never an input to any score, signal or allocation"). All literals are hand-authored 2024 opinions frozen in code.

3. **The desks that DO grade are graded on their picks, never on their importance ranking.** Alt-Data convergence and Policy leans get a `check_by` and a proxy-vs-SPY falsifier — but they grade *which stock was picked*, never *whether the importance/relevance judgment was right*. So the system can never learn that (say) a tier-3 congressional-trade cluster predicts better than a tier-1 wire headline. The relevance model is unfalsifiable by construction.

4. **The scoreboard is empty by construction, and the clocks disagree.** `radar_ic.json` reads `n_matured:0` over 2,489 snapshots because `edge_snapshots.jsonl` began 2026-06-20 (12 days before as-of) against a 21-day maturation horizon (`radar_ic.py:50` `_HORIZON_D=21`) — maturation is mathematically impossible yet. Separately the falsifiable theses carry `HORIZON_D=63` (`radar.py:44`) with `check_by = asof + 91d` (`radar.py:241`), so the two clocks disagree and both read n=0.

5. **There is no leg-level attribution even in principle.** `radar_ic.py` grades the *fused* `edge_score`, never the news leg's marginal contribution over the hard-data legs. Even after maturation, you could never learn whether qualitative text ADDS edge.

The result is definitive: **the suite can DECIDE what to show and can LOG a promise to grade it, but it has never once closed the loop from a qualitative call to a graded outcome.** Because nothing is graded, the hand-authored importance weights cannot improve, the fusion weights cannot be earned, and "noise" remains defined as "matched no keyword" rather than "did not precede a move." The user's whole thesis — filter noise, use what's useful, translate qual→quant — is foreclosed at the foundation. `news_vector.py:5-8` says it out loud: the substrate "makes no forward-return claim, so it cannot be falsified by one." Everything built on it inherits that unfalsifiability.

→ **Light solution directions for Fable:** make outcome-labeling a first-class stage, not a per-desk afterthought; grade *relevance judgments* (did high-importance events actually move?) alongside picks; log false-positive-importance labels (ranked-high, moved-nothing) and sampled low-rank events (misses), or the model only ever sees its own confirmations.

---

## 2. Headline/artifact-only inputs — the hard ceiling before any modeling

**Severity: CRITICAL (US news core) / CRITICAL (China state-media).**

Every qual→quant ambition is capped at "keyword-in-artifact" because no desk holds the underlying fact. You cannot extract a magnitude, disambiguate negation/sarcasm, or verify that a headline maps to a market-relevant event when you only have the headline.

- **No article body exists anywhere in the US pipeline.** `news_common.py:594` (GDELT title/url/domain/seendate only); `news_rss.py:177` (`summary = ""` deliberately); `templates/news.html.j2:16-17` ("no article body exists in the feed"). The narrative "extraction spine" is a permanent no-op stub: `news_vector.py:467-479` `extract_structured` returns `surprise:None, direction_claimed:'unknown', reversibility:'unknown', llm_extracted:False`; `config.yml:2496` `llm_extract: false`.
- **The one LLM that reads news headlines contributes zero bytes.** `news_llm.py:216-217` sets `llm_importance`/`llm_tone`, but `grep -rl 'llm_importance|llm_tone' site/` is empty; `macro.json` headlines carry only deterministic `importance_score`/`intelligence_score`, `summary:None`.
- **China state-media tone is a symmetric bag-of-words that confuses control-signaling with crisis.** `collectors/china_news.py:47-58` scores `(pos−neg)/items` over hand-picked lexicons; a pro-Party crackdown headline ("坚决打击违规") scores negative because 打击/违规 are in `_NEG`. It models none of what carries actual policy signal: lead-item ordering, slogan first-appearance (新质生产力/稳增长), formula shifts (稳中求进→稳增长), byline tier.
- **The event store feeding the scored velocity leg is stale.** `data/news_vector/events.parquet`: 60 rows, newest 2026-06-20 (12 days stale), zero events in the live 7-day window, 46/60 (77%) bucketed "geopolitics," only 4/60 tier-1.

→ **Light solution directions for Fable:** decide per-desk whether the ambition is "sentiment/velocity of headlines" (weak, unvalidatable) or "discrete, dated, verifiable EVENTS whose market mapping can be backtested" (guidance cut, plant fire, contract award, phrase-diff); acquire bodies (or a body-bearing licensed feed / EDGAR full-text / transcripts) where per-asset alpha is the goal; for China, replace bag-of-words tone with a canonical-phrase-diff engine (ordering + slogan appearance/disappearance).

---

## 3. Hand-authored, uncalibrated "importance" — fiat, not fit

**Severity: HIGH (systemic).**

The "what matters vs noise" decision is a static additive keyword scorer in every desk, and no literal has ever been regressed against a realized forward move.

- US news importance: `macro_news.py:461-492` (base 22; `+min(40,14*len(hits_hi))`; `+min(18,7*len(hits_med))`; theme bonuses +16/+8; bands high≥72/medium≥48; floor `min_importance_score=34` at `config.yml:2461`).
- Shared quality: `news_common.quality_score = _TIER_WEIGHT{1:1.0,2:.82,3:.58} × (relevance−clickbait) × recency` — no outcome/learning/retrain path in the module.
- Per-desk noise floors: Alt-Data `_GOV_FLOOR=$5M`, MSPR≥20, options mult 3.0 (`altdata_models.py:124-126`); Congress `W_CLUSTER/TECH/ZONE=0.40/0.35/0.25`, `MIN_DISTINCT_MEMBERS=2` (`build_congress.py:45-52`); Policy `rel_return:0.05`, rotation ±0.02 (`config.yml:2889`; `policy_rotation_check.py:25-26`); White House `min_importance:60` (`whitehouse_brain.py:55`); China News/edge round-number literals throughout.
- The keyword-count uncertainty index was TESTED for a scored role and FAILED: `reports/narrative-regime-phase0.md` verdict "NO-GO for a scored leg → DISPLAY-ONLY"; incremental IC over VIX = −0.064/−0.084/−0.088/−0.129 at h=5/10/21/63, all FDR-reject on the wrong side; `narrative_regime.py:130-131` `gate_multiplier:1.0, gate_status:"pinned_off"`. This is the one place a hand-formula was falsified — and it failed.

→ **Light solution directions for Fable:** keep the frozen hand-formula as an explicit *cold-start prior*, not a shipped truth; add source_tier / novelty / entity-centrality / corroboration-count as FEATURES rather than a frozen product of constants; freeze all bands as provisional until a sample matures; make the learned challenger shadow-only until its graded edge beats the prior on a Wilson-CI gate.

---

## 4. Ad-hoc per-desk logic with no shared entity/event model

**Severity: CRITICAL (architectural).**

Fragmentation is the core structural problem: importance is defined N times and learned zero times, and the single most valuable qualitative signal — cross-source corroboration on one entity — is structurally unreachable.

- **Duplicated primitives that will drift.** `event_id`, `norm_title`, `source_tier` all exist twice (`news_common.py` US, `china_news_intel.py` CN, which re-implements its own from scratch including CN_BASKETS and `importance_score`). A per-desk dedup key means the same Reuters wire is counted once in `macro_news` and again in `financial_news`, and a White House action and a Policy lean about the same executive order never collapse into one event.
- **No shared entity/event model.** `build_entity_map` (baskets+sector holdings→ticker/group resolution) is imported by exactly ONE other module. `smart_money`, `special_situations`, `whitehouse`, `congress` each roll their own ticker extraction. So "NVDA appeared in a 13F AND a policy tailwind AND three wires today" is invisible.
- **Forked feedback.** A good grading substrate exists (`ai_desk_scorer` + `scored.jsonl` proxy-vs-SPY with `check_by`, reused by `altdata_ledger`, `policy_intent_desk`, `foresight_grader`, several China graders) — but each desk re-derives its own falsifier logic and writes to its own dir, so there is no unified outcome table to train on and no common yardstick to compare desks.
- **Macro invisibility.** With per-asset silos there is no place to aggregate "many entities in one sector all lit today" into a regime read; fusion happens (if at all) by hand in templates.

→ **Light solution directions for Fable:** extract ONE shared kernel (`event_id`/`norm_title`/`source_tier`/dedup) used by every desk and delete the China duplicates in favor of a bilingual resolver; promote `build_entity_map` from a 1-consumer helper to THE resolver, extended to people/agencies/policies with CN aliases so corroboration is a group-by; emit a macro/regime aggregate the shared store, which nothing produces today.

---

## 5. The firewall leaks — un-graded outputs move pages users trade

**Severity: CRITICAL (Alt-Data, Policy Watch, China News-fed conviction).**

Desks self-label "context-only," then quietly feed a number downstream — and the two desks whose firewall leaks are the two whose scored input is *least* validated (n=0 ledgers).

- **Alt-Data:** the docstring says "nothing writes into a scored axis" (`altdata.py:18-20`), but `signal_score` drives `radar_ticker act=(score-50)/25` (`radar_ticker.py:133`), `radar_plus` lean≥60 (`radar_plus.py:89`), AND a third consumer the first audit missed (verifier-confirmed) — `intelligence.py:99-106` score≥65→directional label. All while the brain is dark and `n_scored:0`.
- **Policy Watch:** the "NEVER-SCORED" lean moves `intel_hub` `gap_mult` and opportunity (`intel_hub.py:413-414`) plus early_edge/stage flags, with zero gating on its own `confidence:'low'`; the rotation check is blind — 17/27 proxies unpriced.
- **China News feeds displayed conviction.** All four China desks are honestly `is_context_only` and walled from allocation (grep confirms zero load-bearing consumers), BUT News sentiment z and by_basket hits feed `china_intel_analysis._conviction` → the `context_conviction`/`flagged_tickers` board the user reads. **Verifier correction:** the "ZERO live consumers" framing was wrong — `china_policy_watch.py:74`, `china_validation.py:232`, and `china_intel_bus/analysis` all consume the module and its frozen JSON, which makes the stale-artifact defect *worse*, not moot.
- Where the number is honest (13F track-record, White House), the *contract copy* over-sells — AI conviction "graded vs SPY" while the brain is dark.

→ **Light solution directions for Fable:** hard `n>0` gate before any un-graded desk output moves a ranking, OR down-weight by the artifact's own confidence value (already computed and thrown away at the `intel_hub` policy consumption boundary); make the firewall explicit and code-enforced, not a docstring.

---

## 6. The costume problem and dead/dark legs

**Severity: HIGH (narrative), CRITICAL (dark brains).**

- **Price momentum in a narrative costume.** The flagship "narrative" signal that reaches allocation is price momentum relabeled; the one genuine qual→weight path (`spvector_overlay` knife-veto) is dormant on neutral data, not architecturally firewalled. The Narrative Brain ships degraded: `narrative_brain.json` `assessments:[], rotation:null, degraded_reason:"no_usable_reply"`.
- **Dark shells.** White House is a fully dark shell — banner `{alerts:[]}`, ledger/state dirs never existed in git; nothing has ever executed against a live post. China Alt-Data's LHB/block alpha-draining sign-flip demotion is DEAD CODE (overridden by `_PRIORS`), so ~92% of convergence weight sits on untested/wrong-sign/ungradeable legs.
- **Polluted quant output.** Special Situations' merger-arb book has top entries UROY +1308%/yr, MCHX +979%/yr, 8 entries with impossible positive break-downside — garbage sorted to the top the brain reads. (Verifier correction: the backtest is negative-excess but NOT uniformly — Issuer Tenders·live n=55 and Divestitures·closed n=47 are positive; do NOT repeat "all positive cells n≤4," REFUTED. Real CRITICAL surfaced by verifier: the destination Top-Pick composite is itself DSR-failing and cites a non-existent report, `top_picks.py:9,40`.)
- **Coverage artifacts read as signal.** Smart-Money/Insider: 76% of insider tickers ship `bps=None` (mcap-join artifact), so the size-normalized leg is dark for most names and skews large-cap. (Verifier: the audit's SMI-1/SMI-2 CRITICALs were REFUTED/PARTIAL — the shipped sector-neutral leg IS the FDR survivor and its long-only-confirmer use is what phase1 recommended; do NOT repeat "wrong construction shipped.")
- **Congress is live but stale.** Off paid Quiver (the memory "data-dead" note is stale for this desk), but "act now" copies trades ~76 days stale (verifier corrected the audit's 86d), and the composite is 100% hand-authored; #1 name AAPL is 6B/7S — rewards attention, not conviction.

→ **Light solution directions for Fable:** reserve "narrative" for the text pipeline, not price momentum relabeled; make dark-brain fallbacks non-monotone-bullish (Alt-Data AVOID guards are dead when the brain is dark); make fail-open wrappers (`altdata.py:973`, `build_congress.py:434`) distinguish "broken" from "quiet" uniformly.

---

## 7. China-specific structural gaps — state-media-as-signal and censorship survivorship

**Severity: CRITICAL (both are unmodeled today).**

The China gap is not "faster/cleaner US things" — it is qualitatively different, and the difference is the whole point.

- **Policy language IS the driver, not commentary about it.** In China a phrase reappearing (适度宽松 "moderately loose" monetary stance) or dropping moves whole sectors; a missing/late Politburo readout is itself a regime-uncertainty signal. The only machine-derived China policy quantity (`_classify`) reads rate levels only and would be identical if every Politburo readout were deleted — a rate-corridor dashboard wearing a "policy intent" label (CPW-1).
- **Censorship survivorship is entirely unmodeled across all four desks.** Pipelines are keep-first, append-only; negative signal removed at source reads as neutral/positive. A rising tone can be suppression, not easing — and the contrarian leg then fades at exactly the wrong moment. The one place survivorship was *identified* (alt-data LHB up-day inflation, F1/F6) was sign-flipped and then dead-coded.
- **Load-bearing sign with no evidence.** China Intel's "news is contrarian in China" sign (`sign_expected=-1`) has `n_obs=0`, and its z=−2.06 is computed over ~19 days against a 90-day window (CI-1/CI-2). The tone series is ~19 days; validation needs ≥25 pooled obs (`_MIN_PROVEN_N_TS`), so `n_obs=0` persists unless a multi-year tone backfill is built.
- **Free-tier ceiling is hard.** News events are 97.9% tier-2 retail scrapes (Eastmoney/Futu/THS via akshare), 2.1% state RSS, 0 tier-3 — so the tier-weight model is inert. Grep across `collectors/`+`engine/` for Wind/Choice/iFinD/CSMAR/CNInfo full-text/expert networks = zero. (Verifier nuance: `ak.stock_dividend_cninfo` exists but is dividend history, not full-text filing parsing — ceiling claim holds. Verifier corrections also applied: CN-NEWS-06's "56%" is the scheduled_ref rate not the surprise rate; sentiment band did NOT flip cautious→steady, only z drifted −2.06→−0.79; CN-QUAL-7 tiering is official-vs-flash not English-vs-Chinese; the sina wire is dead via an empty-title adapter bug, not theme-gating.)

→ **Light solution directions for Fable:** a canonical-phrase-diff engine over free official corpora (State Council/PBOC/NDRC/CSRC/Politburo readouts/People's Daily front page) treating phrase presence/absence/reorder as the signal, with ABSENCE as a regime-uncertainty flag; a first-class censorship/survivorship guard (deletion-rate / URL-liveness, or an onshore-CCTV vs offshore-GDELT tone *divergence* index where a widening gap = suppression = risk-off) — the highest-conviction novel edge every desk currently ignores.

---

## 8. Institutional-grade data acquisition — the honest thesis

**Severity: framing, not defect.**

The unifying acquisition claim, which survives adversarial scrutiny: **the entire institutional qualitative tier is priced AND compliance-gated out of a solo shop's reach, so the only winnable lane is free/cheap public text run through our OWN LLM extraction.** The MNPI supervision burden alone rules out expert networks and card panels — not merely the price.

The one frontier a solo shop can genuinely win: pull raw transcripts + 8-Ks/10-Ks cheaply and run *own* LLM extraction (guidance tone, hedging density, topic drift YoY, analyst-pushback intensity) → proprietary quant features instead of buying RavenPack's pre-computed scores. Published-news + official-filing + licensed-transcript NLP is by construction the MNPI-safe lane.

**Verifier-critical correction folded in:** FMP earnings-transcript API is NOT free — the 250-req/day free tier is market-data only; transcripts require a PREMIUM/paid plan (exact current price UNVERIFIED, 403 on doc URL). The frontier thesis holds, but at a modest monthly fee, not $0 — re-check the cost math wherever "free transcripts" appears.

### Tiered acquisition table — US

| Source | Category | What it provides | Cost | Realism | Legality |
|---|---|---|---|---|---|
| **SEC EDGAR** (full-text + XBRL + 8-K) | filings-NLP | Every US filing as text + XBRL; 8-K item codes (1.03 bankruptcy, 2.02 results, 5.02 exec); real-time stream | **free** (keyless, ~10 req/s) | **acquire now** | Public regulatory disclosure; zero MNPI. Declared UA + fair-access limit only. |
| **GDELT 2.0** (DOC API + BigQuery + GKG) | event-data | Global news tone/events/entity graph since 1979, 15-min, 100+ langs | **free** (BigQuery egress only) | **acquire now** | Aggregated published-news metadata; public. |
| **Benzinga Pro** (news + Audio Squawk) | wire | Real-time equity/options feed, movers, live squawk | **low** ($37 Basic / $147 +Squawk / $197) | **acquire now** | Published wire; low MNPI. *Verifier: drop the "resold via Polygon/Massive ~25ms" claim unless sourced.* |
| **FMP / API-Ninjas transcripts** | transcripts | Full earnings-call transcripts + speakers, 8,000+ US names | **low PAID** (NOT free — verifier fix) | **acquire now (paid)** | Public-call transcripts; ToS on redistribution. |
| **Tiingo / Marketaux / Finnhub / Alpha Vantage** | wire | Ticker-tagged news + per-entity sentiment | **free/freemium** | **acquire now** | Published news; ToS history/redistribution limits vary. |
| Smartkarma | sell-side | 450+ independent-research providers, event-driven/Asia-EM | **mid** (quote-based, *verifier: "transparent pricing" UNVERIFIED*) | **stretch** | Published research; low MNPI. |
| Seeking Alpha / Motley Fool transcripts | transcripts | Human-published transcripts | low (bulk scrape = ToS flag) | **stretch** | Public; systematic scraping likely violates ToS. |
| Satellite / web-scrape panels (DIY) | alt-data | Physical-activity nowcasts | mid ($ cheap, eng+legal expensive) | **stretch** | Scraping legality fact-specific; ToS/survivorship risk. |
| RavenPack / Bigdata.com | filings-NLP | Pre-computed sentiment/event/novelty | **institutional-only** | **avoid** (approximate via GDELT+EDGAR+own-LLM) | Licensed; contract minimums. |
| Bloomberg Terminal + EDF | wire | Lowest-latency machine-readable events | **institutional-only** (~$31,980/yr, verifier VERIFIED) | **avoid** | Tight redistribution; entry cost prohibitive. |
| Dow Jones / LSEG (Reuters) MRN | wire | Structured wire tape, archive to 1996 | **institutional-only** | **avoid** | Heavy licensing. |
| AlphaSense (+Tegus) | expert-network | Search + transcript + expert-call corpus | **high** (~$15-20k/seat; expert tier $40k+; *"$45k SMB avg" UNVERIFIED*) | **avoid** | Expert-transcript layer MNPI-adjacent; needs compliance we lack. |
| Expert networks (GLG/Third Bridge/AlphaSights/Guidepoint) | expert-network | 1:1 practitioner calls | **institutional-only** | **avoid — MNPI** | Highest insider-trading exposure (Martoma/SAC conduit); off-limits for a solo shop. |
| Card/transaction panels (Yipit/Earnest/Consumer Edge) | alt-data | Revenue nowcasts | **institutional-only** (six-figure) | **avoid** | Privacy/consent supervision load a solo shop can't carry. |
| Visible Alpha | sell-side | KPI-level consensus | **institutional-only** | **avoid** (approximate coarsely w/ Finnhub/FMP EPS) | Licensed. |

### Tiered acquisition table — China

| Source | Category | What it provides | Cost | Realism | Legality |
|---|---|---|---|---|---|
| **Official policy corpora** (gov.cn, PBOC, NDRC, CSRC, Politburo readouts, People's Daily front page) | policy-corpus | Verbatim policy language — the price driver; presence/absence of stock phrases | **free** | **acquire now** | Public gov text; no MNPI, low PIPL (impersonal). |
| **Tushare Pro mid points tier** | structured confirmer | 业绩预告 / 龙虎榜 / broker coverage / chip distribution | **low** (*~RMB 200→2,000 pts UNVERIFIED, zhihu-sourced*) | **acquire now** | Domestic vendor, aggregated public-market data; low PIPL. |
| **CNInfo (巨潮) + SSE/SZSE/HKEX portals** | filings full-text | Full-text disclosure, incl. regulator inquiry letters (问询函) + IR Q&A (互动易) | **free** | **acquire now** | Public disclosure; throttle for anti-bot ToS. |
| **THS concept-boards + Baidu Index + Weibo hot-search** | attention alt-data | Narrative-rotation + demand/attention nowcast | **free/low** | **acquire now** | Aggregate indices impersonal (low PIPL); censorship survivorship structural — needs a suppressed-term flag. |
| Choice (东方财富) | terminal | Clean consensus/guidance confirmers | **low** (*~RMB 3-5k/yr UNVERIFIED*) | **stretch** | Domestic; API redistribution + offshore-use clauses. |
| CSMAR | academic panels | Point-in-time clean history to BACKTEST policy/phrase signals | **mid** | **stretch** | Academic license often bars commercial use — gating for a paid product. |
| iFinD (同花顺) | terminal | Wind alt at 50-70% | low-mid (*UNVERIFIED*) | **stretch** | Contract redistribution restrictions. |
| Wind (万得) | terminal | Domestic Bloomberg; cleaned everything | **high** (quote-based) | **stretch** | Offshore-use + DSL "important data" clauses; marginal edge is convenience not narrative alpha. |
| Wisers | media analytics | Chinese-language sentiment/entity/share-of-voice | **high** | **avoid** | Social ingestion → PIPL/DSL cross-border exposure; overkill vs free Baidu/Weibo. |
| China satellite / e-commerce panels | alt-data | Physical-activity nowcast | **high** | **avoid** (prefer free official proxies: express-parcel/electricity/freight) | Geospatial/mapping-law + PIPL exposure. |
| Expert networks on China (Capvision/凯盛, GLG, Third Bridge) | expert-network | Channel checks / policy interpretation | **institutional-only** | **avoid — HARD COMPLIANCE LINE** | 2023 Capvision raids, Bain questioning, Mintz $1.5M fine, expanded anti-espionage law (verifier: best-VERIFIED part). A legal no-go for a small foreign shop regardless of budget. |

→ **Light solution directions for Fable:** treat every signal as a REGIME measure not a level and gate it through a forward track-record/DSR harness before it drives allocation; impose point-in-time / survivorship discipline on GDELT + EDGAR so the home-built corpus doesn't inherit look-ahead the vendors engineered out; standardize the LLM-extraction tier for cost control and guard against LLM-scoring drift (same transcript scored differently across model versions) contaminating a multi-year forward log; write the MNPI/expert-network exclusion as a deliberate documented scope boundary, not an oversight.

---

## 9. The one centralized engine — hub-and-spoke, feedback loop as keystone

**Severity: framing — this is the net-new build.**

Today's ~15 desks are forked silos (§4). The fix is not a monolith (which would couple failure domains — a THS scrape timeout shouldn't stall the US news desk and fights the already-spoke-shaped architecture) but **hub-and-spoke**: centralize the three things that MUST be shared (entity model, importance model, outcome ledger); leave ingestion and presentation as independently-failing spokes to preserve the existing degrade-never-raise discipline.

**The unified engine — seven stages, degrade-never-raise per stage:**

1. **INGEST** — thin spokes adapt each source (RSS/GDELT/Quiver/13F/whitehouse/FRED/Tushare/akshare/THS) into a common raw ITEM `{source, source_tier, url, lang, seendate, raw_text, vintage}`. Spokes stay independently failable.
2. **NORMALIZE** — one text pipeline: language detect, translate-for-matching (not display), `norm_title`, clickbait/low-value filter — folding today's per-desk `is_low_value` + `clickbait_penalty` into one pass.
3. **ENTITY/EVENT RESOLUTION** — ONE resolver over a unified entity graph (tickers/baskets/sectors + people/agencies/policies + CN aliases) replacing today's two entity maps; emits `event_key` clustering multi-source reports of one happening. **This is the highest-risk, longest-pole item** — bilingual resolution (中国平安↔601318↔Ping An) and generic NER over Chinese policy text is a research problem, not a build task; the current `$TICKER` regex + stopword list won't cut it.
4. **DEDUP + NOVELTY** — global `event_id` dedup (keep-first) across ALL desks, then a novelty score (new information vs an echo of the trailing window for this entity/theme, z-vs-trailing-volume as `china_news_intel` already gestures at).
5. **IMPORTANCE/RELEVANCE SCORING** — the single importance model scores `(item, entity, event, context)→importance∈[0,1]` with source_tier, novelty, entity-centrality, event-proximity, corroboration-count as FEATURES. Cold-start = today's hand-formula; **learning is DEFERRED / shadow-only** until label volume clears a Wilson-CI gate (verifier reconciliation — the near-term win is unification + a common yardstick, not learning).
6. **PER-ASSET + MACRO EMIT** — one emit contract: per-entity signal (direction/conviction/horizon) AND a macro/regime aggregate ("many entities in one sector lit today" → sector/theme pressure), which nothing produces today. Signals are the cross-desk JOIN on an entity, so corroboration raises conviction automatically.
7. **ACCOUNTABILITY / FORWARD-GRADING** — ONE outcomes ledger (generalize `scored.jsonl` + `ai_desk_scorer` proxy-vs-SPY + `check_by`), unifying the 7+ scattered dirs into one table keyed by `(entity, date, desk, signal_id)`.

**The keystone feedback loop:** turn frozen importance into learned importance by grading RELEVANCE judgments, not just picks. (a) OUTCOME LABELING — snapshot PIT entry levels at detection, derive falsifier + `check_by` via existing `ai_desk._derive_check`; on window elapse grade realized forward return of the resolved entity vs benchmark → one ledger row. Crucially log a label even for high-ranked events that moved NOTHING (false-positive importance) and sample LOW-ranked events (misses), or the model only ever sees its own confirmations. (b) FORWARD GRADING — one common yardstick lets you compute hit-rate/edge PER FEATURE-SLICE (does tier-3 congress-cluster beat tier-1 wire? does high-novelty beat echo?), directly answering "which desk actually predicts." (c) IMPORTANCE-MODEL RETRAINING — fit `importance(features)→P(forward move | horizon)` on accumulated labels; deploy champion-challenger against the frozen prior (reuse `promotion_gate`/`meta_label`), promote only on a Wilson-CI gate. Keep the model simple (logistic/GBM on a handful of features) given solo-shop n.

**US and China share the engine but respect different information content:** US filings/wires are informative and legally clean; China state-media tone, THS scrapes and policy signaling are noisier and partly *intentional* signaling with censorship survivorship. The open design tension (§payload) is whether importance is ONE model with region features or two models sharing a schema — and how to stop a China-specific frozen prior (state-media z-score) being learned as spurious edge on a small, regime-dominated n.

→ **Light solution directions for Fable:** extract the shared kernel first and migrate desks onto one outcomes ledger before any learning; add novelty as a first-class stage (cheapest highest-value missing feature); emit the macro/regime aggregate; add a one-line MNPI caveat inside the methodology layer so the corroboration engine is not read as license to assemble a mosaic that behaves like MNPI.

---

## 10. How it all fits — the light roadmap frame

This is deliberately light; Fable designs the novel solution.

- **Fix in the existing suites (stop the bleeding):** dark-brain contract copy that over-sells (Alt-Data "graded vs SPY," AI conviction); the China News dead render (`build_china_news.py:73`) freezing artifacts; the leaking firewalls (Alt-Data/Policy un-graded outputs re-ranking traded pages — hard `n>0` gate or confidence down-weight); the polluted arb book sorting impossible returns to the top; monotone-bullish dark-brain fallbacks and fail-open wrappers that hide "broken" as "quiet."
- **Build net-new (the missing capability):** discrete dated EVENT extraction over bodies (US) and a canonical-phrase-diff engine (China); a first-class novelty stage; a censorship/survivorship guard (deletion-rate or onshore-vs-offshore tone divergence); a macro/regime aggregate; the outcome-labeling stage including false-positive-importance and sampled-miss labels.
- **Centralize (the architecture):** one shared kernel (`event_id`/`norm_title`/`source_tier`/dedup), one bilingual entity resolver promoted from `build_entity_map`, one outcomes ledger keyed `(entity,date,desk,signal_id)` — hub-and-spoke, learning deferred until the ledger is large enough to beat the prior with statistical confidence.

The sequencing principle: **unification + a common yardstick is the near-term win; learned importance is the long-term keystone, shipped in shadow only.** Every current "calibrated by the ledger" claim is a promise the system cannot yet keep — the roadmap's job is to make that promise honest for the first time.

---

## The Fable payload — the hard open questions

These are the genuinely unresolved tensions across US + China. The findings above exist to ground them.

1. **Can a headline/artifact-only feed EVER support importance modeling, or is body/event acquisition a hard precondition?** The no-body ceiling (§2) caps everything. Is any headline-only signal worth validating, or does the whole "turn news into signal" thesis require bodies (or a body-bearing licensed feed) first — and if bodies are out of reach, should the ambition collapse to discrete, dated, backtestable EVENTS ("events over vibes") rather than sentiment/velocity of headlines?

2. **Labeling the counterfactual without grading the firehose.** Importance is a ranking over ALL items, but you only ever see outcomes for the ones you emit. How do you get negative/low-importance labels — sampled low-rank events? synthetic negatives? — and how much survivorship bias does the cheap path bake into the learned importance model? What is the minimal viable outcome-labeled dataset to learn "what matters" at solo-shop label velocity?

3. **Attribution for diffuse events.** Cross-source corroboration on one entity is the prize, but forward return is measured on a ticker while the highest-value qualitative events (policy, macro narrative) have diffuse, lagged, multi-asset effects. What is the right label target for a macro/narrative event with no clean single-ticker proxy — and does forcing everything through proxy-vs-SPY quietly discard exactly the events with the most institutional value?

4. **One model or two, and the China spurious-edge trap.** Should importance be ONE model with region features or two models sharing a schema? How do you stop a China-specific frozen prior (state-media z-score, contrarian sign) being learned as spurious edge on a small, regime-dominated n (~19-day tone series, `n_obs=0`) — and can Chinese state-media tone ever become a real signal, or only a formula-diff / phrase-appearance detector given only a few readouts per year?

5. **Censorship survivorship as a first-class leg.** Every China desk reads suppressed negative signal as neutral/positive (§7). How do you operationally separate a collapsing Baidu term / rising tone that is *suppression* from genuine demand collapse or easing — deletion-rate tracking, URL-liveness, onshore-CCTV vs offshore-GDELT tone divergence, timing vs known policy events — and what confidence do you attach when you can't? This is the highest-conviction novel edge the suite currently ignores.

6. **The minimum forward-grading protocol that licenses moving a leg from display to weight.** The accountability chassis is total-vacuum (n_matured:0 over 2,489 snapshots, degraded brains, contradictory 21d/63d clocks, even the "validated" vendor family n_obs:0). What is the minimum protocol (regime not level, incremental over price+VIX, block-bootstrap, Wilson-CI gate) that would license a bounded scored weight — and should it be a hard, code-enforced precondition? How do you represent "promise-to-grade" vs "actually-graded" so the UI never launders one as the other? For China, given clean point-in-time history is the exact thing we lack, should policy-language signals be display-only until an out-of-sample forward log accrues — or is China structurally a context/overlay layer, not a standalone alpha source?

7. **Sample-starvation vs model complexity, and the costume problem.** Is a learned importance model even justified over a well-calibrated frozen prior at realistic solo-shop label volume, or is unification + a common yardstick the correct near-term ceiling with learning deferred? And: is there ANY defensible definition of "narrative signal" in this codebase that is neither price momentum relabeled (§6) nor a display-only text panel — and what does a controlled, forward-graded experiment that lets ONE qualitative feature bind a small capped weight look like, so the qual→quant claim is finally tested rather than perpetually deferred?

8. **The MNPI/mosaic boundary as centralization deepens.** As corroboration and filing/transcript ingestion deepen, where is the line between "aggregating public info into novel signal" (fine) and assembling a mosaic that behaves like MNPI — and does centralizing everything into one entity-resolved store *raise* that risk versus keeping desks siloed? The China expert-network line is already a hard compliance no-go; does the US corroboration engine need the same explicit boundary written into the methodology layer?

---

*Companion documents: `research/QUALITATIVE_SIGNAL_US_AUDIT_FOR_FABLE.md` (per-desk US findings), `research/QUALITATIVE_SIGNAL_CHINA_AUDIT_FOR_FABLE.md` (per-desk China findings), `research/NEWS_FEED_PROBLEM_AUDIT_FOR_FABLE.md` (the news-core qual→quant diagnosis). This masterplan is the unifying framework both region audits reference.*

---

## Appendix: subsystem map

| Subsystem | Shipped-state one-liner | Role | Validated? |
|---|---|---|---|
| News core (macro/financial) | Headline-only; no article body anywhere; financial.json silently oscillates dark↔rich (`degraded_reason:null` even with finnhub dark) | feeds-signal (velocity) | NO — radar_ic n_matured:0 / 2489 |
| News importance scorer | Static additive keyword score (base 22 + keyword hits + theme bonus), never regressed | feeds-signal (gates inclusion) | NO |
| Narrative Brain (LLM durability) | Degraded: `assessments:[], degraded_reason:"no_usable_reply"` | feeds-signal | NO |
| Narrative-regime (uncertainty index) | Tested for scored role, FAILED; `gate_status:"pinned_off"` | display-only | YES — falsified, correctly demoted |
| Alt-Data / Signal Intelligence | Opus brain DARK (theses:[], llm_error), 30 deterministic-WATCH; header sells "AI conviction" | feeds-signal (leaks) | NO — n_scored:0 |
| Special Situations (merger-arb) | Book polluted (UROY +1308%/yr, impossible positive break-downside); Top-Pick composite DSR-failing, cites non-existent report | display-only + brain reads summary | NO |
| Congress Trades | Live off Quiver but ~76d stale; composite 100% hand-authored; #1 AAPL 6B/7S | display-only (table) | NO — no forward grader |
| Smart-Money 13F | Track-record explicitly never imported | display-only | 13F leg: never scored |
| Smart-Money / Insider leg | 76% tickers bps=None (mcap-join artifact); sector-neutral leg IS FDR survivor | feeds-signal (Top-Pick conviction_z, TILT_W=0.4) | leg: PARTIAL (FDR survivor); coverage broken |
| White House | Fully dark shell — `{alerts:[]}`, ledger/state dirs never existed | display-only (context) | NO — never executed |
| Policy Watch (US) | Well-engineered empty skeleton; ungraded low-conf LLM lean re-ranks traded page; rotation blind (17/27 unpriced) | feeds-signal (leaks: intel_hub gap_mult) | NO — scored_total:0 |
| Intel Hub | Consumes Alt-Data + Policy leans | feeds-signal | NO |
| China News (china_news.html) | Dead render (`build_china_news.py:73`) freezes artifacts at 2026-06-22 vs parquet 07-01 | feeds-signal (displayed conviction) | NO |
| China Intel (china_intel.html) | Fresh fusion; contrarian sign `sign_expected=-1` has n_obs=0; z over ~19d | feeds-signal (context_conviction board) | NO |
| China Alt-Data | LHB/block sign-flip demotion is DEAD CODE (overridden by _PRIORS); 92% weight on untested legs | display-only (radar candidates) | NO |
| China Policy Watch | Rate-corridor dashboard labeled "policy intent"; `_classify` reads rate levels only | display-only (context block) | NO |
| State-media tone (collector) | `(pos−neg)/items` over 35/32 hand-picked words; control-signaling scores as crisis | feeds-signal (into intel z) | NO — self-labeled "deliberately CRUDE" |
| Shared kernel (news_common) | `event_id`/`norm_title`/`source_tier`/`quality_score`/`build_entity_map` — build_entity_map has 1 consumer | partial spine | quality_score frozen, unlearned |
| Forward-grading substrate (ai_desk_scorer + scored.jsonl) | Good proxy-vs-SPY chassis, forked across 7+ ledger dirs, none join | accountability | NO — no matured loop anywhere |
