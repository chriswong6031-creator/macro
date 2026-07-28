# Intelligence Suite — ingestion, scoring brain, Content Studio pathways, employee desks (masterplan)

**Program:** Agentic Media / Intelligence Suite (IS) · **Author:** Fable · **Date:** 2026-07-27 · **Status:** CHARTERED (operator directive, fourth ruling of 2026-07-27)
**Umbrella:** `AGENTIC_MEDIA_PROGRAM_BY_FABLE.md` · **Extends:** D05 + Addendum 2 (wire spine #3838, B2-COPY #3861), Media D14 (PRESS-FEEDS), Persona D13, Content Studio (`engine/marketing/content_studio.py`), Markets News B4. **Absorbs** Addendum-2 §6 B4b–d as IS-W6.
**Operator directive (verbatim intent):** deep-research the source estate; build an ML engine that separates garbage from good data, scores usefulness + virality potential, ranks hot keywords; integrate the Trump wire + top-X-account relay + all news into Content Studio; per-kind pathways that ingest → digest → create original content ready to post through the Outbox; four employee accounts with fixed, subtle personalities; plan intricately.

---

## §0 ACCEPTANCE GATES (top of file by law)

**IS-W1 (source estate + spine hardening) not done unless:** every provider emits into ONE statements store (statement.v1 rows; VPS-local hot store, nightly-consolidated ledger — pollers make zero repo writes); `wire`/`breaking` kinds admitted to `outbox.KINDS` **through `make_item`** (the census-verified bypass in `press_lane._write_outbox_item` is CLOSED — wire items get schema validation, id-idempotency, the 7-day text-dedup window, and sentinel near-dup coverage like every other kind); GDELT + Alpaca providers live behind config with fixture tests; thin CI lane (pytest+pyyaml) green across the full marketing set.

**IS-W2 (scoring brain v1) not done unless:** deterministic features computed for 100% of ingested items with a persisted `_components` breakdown (transparent, greppable); a **200-item golden set** (operator/Fable-labeled: garbage / useful / post-worthy / viral-grade) exists and the scorer's precision@20 beats the current salience-only ordering on it; scores REORDER and deprioritize only — a score can never force-post an item that fails corroboration/sentinel/language gates, and no score ever surfaces user-facing; the ML ranker (v2) trains only after ≥3 weeks of real telemetry labels and its eval report is reviewed by the `reviewer` lane before it influences ordering.

**IS-W3 (Content Studio router) not done unless:** the pathway registry is config-driven; every pathway has validators + fixture tests + a media policy; one end-to-end fixture proves raw feed item → dedupe/cluster → score → route → generated post → outbox item with validator report; the event-language contract (#3836) holds on every pathway (no machinery vocab user-facing); digest pathway revives the deferred B1 digest sink (single-source hearsay becomes a morning roundup, not a dropped log line).

**IS-W4 (employee desks) not done unless:** each account's codex is committed + versioned and the **expression dial** is validator-enforced (news/wire = 0 personality — byte-level house wire voice; analysis = ≤1 personality-inflected clause; charts/watchlist = ≤1 playful line); AM-R1 banned patterns (no personal trade/P&L claims) test-pinned per account — these are REAL NAMES, testimonial risk is maximal; desk_network + Buffer channel wiring per account; cadence follows the zero-follower traction playbook phases; news/wire kinds stay blocked on Persona-W2 cadence resolver (unchanged precondition); manual-post coexistence documented (engine never posts first-person claims; near-dup radar + text-dedup guard cover collisions with the human's own posts).

**IS-W5 (feedback loop) not done unless:** per-post telemetry rows flow per account (poller #3346 pattern); weekly hook/format/register scorecard renders in admin; ranker retrain is an off-render scheduled job with versioned model artifacts.

---

## §1 Shape — one spine, one brain, many hands

```
sources (§2) ──▶ statements store ──▶ L0 dedupe/cluster ──▶ L1+L2 scoring brain (§3)
                                                                  │ ranked, classified, componentized
                                                                  ▼
                                                    Content Studio router (§4)
                     ┌──────────┬───────────┬──────────┬──────────┬───────────┬──────────┐
                     ▼          ▼           ▼          ▼          ▼           ▼          ▼
                  P1 flash   P2 deep    P3 chart-  P4 thread  P5 digest   P6 site    P7 press
                  wire       wire       backed     explainer  roundup     rail only  Brief cand.
                     └──────────┴───── outbox (make_item, gates, approve flow) ─────┘
                                          │                         │
                                     X accounts (§5)          news.html rail / terminal (IS-W6)
```

The Trump wire (D05 Addendum 2) was the vanguard; this masterplan is the same spine generalized. Nothing here replaces the outbox/sentinel/publisher machinery — the suite feeds it.

## §2 Source estate (IS-W1) — verified numbers, tiered adoption

**Free spine (adopt now, $0):**
| Source | What it adds | Verified facts (2026-07-27 research sweep) |
|---|---|---|
| Existing: trumpstruth, x_follow (twitterapi.io), WH RSS, 6-source RSS register, Alpaca/Benzinga (keys installed) | the live wire | probes in Addendum 2 |
| **GDELT GKG 2.0** | the free NLP powerhouse: V2Tone (7-field tone incl. polarity), **GCAM incl. Loughran-McDonald financial sentiment**, 2,500+ themes (ECON_*, WB_*), entities, **15-min updates**, 65 languages; plus the entity-velocity trending files (15-min anomaly JSONs) | free; TLS quirk on data domain (curl flag); BigQuery mirror |
| **twitterapi.io trends endpoint** | X trend velocity per geo (`/twitter/trends?woeid=`) | $0.00015/req ≈ $5–40/mo depending on geos×cadence — same key we installed |
| **Wikipedia pageviews API** | daily attention spikes per entity (keyless) | data by 05:00 UTC daily — slow lane |
| **Finlight** (connector already in-repo, dark) | enriched WS financial feed | free tier 5k req/mo 12-h delay; **$99/mo Pro Standard for sentiment + real-time WS** — arm free first |

**First paid add (operator approval, after IS-W2 shows coverage gaps):** **NewsAPI.ai (EventRegistry)** — $90/mo entry, 150k+ sources, 60+ languages (feeds Cici's Asia beat), **pre-computed Wikidata entities, entity-level sentiment, clustering/dedup in the response** — the highest value-per-dollar upgrade found; free tier (2k tokens) lets us evaluate before paying. Alternative if it disappoints: **Perigon** (~$150–250/mo, 150–200k sources, <1 min majors, knowledge-graph entities). Rule: add ONE, measure scorer-coverage lift for two weeks, then decide the second.

**Rejected (recorded so nobody re-proposes):** CC-News (retrospective corpus; hours-to-days latency, 900+ publishers now blocking CCBot — structurally declining; fine for model training corpora only); newsapi.org ($449/mo with ZERO NLP and no article body — poor value); Webz.io/Quantexa-Aylien/NewsCatcher News API (enterprise-opaque pricing; revisit at scale); Feedly API ($3,200/mo tier, UI-layer NLP not exposed); Google Trends (official API still gated alpha without Trending-Now; pytrends dead/archived — our keyword heat comes from our own corpus + GDELT + X trends instead).

## §3 The scoring brain (IS-W2, "Signal Desk") — marketing-internal, never a market signal

**L0 — identity & story spine.** URL normalize → `datasketch` v2 MinHash-LSH (`affine32`) for wire-copy near-dups → semantic pass with **Model2Vec `potion-base`** static embeddings (CPU-native — sidesteps the MPS fp16 limit; 500× faster than SBERT, right for the VPS) with MiniLM-L6/BGE-M3 upgrades on the Mac Studio for quality passes → incremental-DBSCAN/HDBSCAN story clustering (the AWS FSI 1M-articles/day pattern). A **story** carries: cluster id, first_seen, source count, tier mix, engagement observed. Trump-wire cross-mirror dedupe (#3838) is a special case of this general layer.

**L1 — deterministic features (extends `breaking_relevance.score_item`; every feature lands in `_components`):** existing (event_class base salience, source-tier bonus, entity/ticker match, market-hours weight, keyword bonus) **plus**: `corroboration_velocity` (distinct independent sources per story per 15/60 min — the Techmeme insight; also the ≥2-source law's evidence), `keyword_heat` (rolling z-score burst on our own ingest terms — Kleinberg-lite, ~50-line reimplementation since both PyPI packages are dead; joined with GDELT entity-velocity files and X trends), `novelty` (temporal-IDF vs our trailing 30-day corpus — arXiv 1401.1456 method), `source_authority` (per-source prior from observed engagement), `tone_extremity` (GDELT V2Tone/GCAM join incl. Loughran-McDonald where the story matches), `headline_shape` (numbers present, entity count, length band). **Garbage gate** (pre-score drop): satire blocklist (exists), source blocklist, promo/spam lexicon, paywalled-stub detector (boilerplate/body-length), non-story detector (horoscope-class themes).

**L2 — learned ranker (v2, only after labels accrue).** Gradient-boosted trees (LightGBM/XGBoost — the consistent winner in the virality literature; multimodal XGBoost beat BERT-class content models on Reddit/meme corpora) over L0/L1 features, two heads: **reach_potential** — labels from (a) our own posts' impressions/engagement telemetry and (b) **observed engagement on x_follow items we did NOT post** (twitterapi.io returns like/RT/view counts — a free virality ground-truth stream over exactly our content distribution); **usefulness** — golden-set labels + site-rail click-through later. Honest ceiling, stated up front: the literature caps content-feature-only virality prediction at ~30–40% of variance (the rest is network/timing) — the ranker's job is **triage quality, not an oracle**; the top L1 feature class in every benchmark (historical engagement of similar keywords/stories) is exactly what our label loop accrues. Nightly retrain on the Mac Studio off-render; versioned model artifact to R2; VPS inference is trivial (trees). **Governance:** LLM never scores (de-escalate/veto + summarize-with-citation only — standing law); scores are display-tier marketing internals; if any score is ever proposed for a user-facing authority surface, the epistemics gauntlet applies at THAT promotion, not before.

## §4 Content Studio upgrade (IS-W3) — pathway router

**Intake bus:** scored stories → `wire_router` → pathway by (event_class, register, salience band, corroboration class, source-body richness, media availability):

| Pathway | Output | Status |
|---|---|---|
| **P1 flash wire** | ≤2-sentence house wire post (+ tape stamp) | BUILT (B1+B2) |
| **P2 wire_deep** | two-paragraph explanatory post (HormuzLetter tier) | BUILT (B2) |
| **P3 chart-backed reaction** | entity→ticker→`render_chart_v2` with event annotation + wire copy | NEW — the auto-chart lane; reuses the full chart engine + media_publish path |
| **P4 thread explainer** | macro prints: flash + educational reply chain | NEW (needs Buffer threading capability check) |
| **P5 digest roundup** | morning "what mattered overnight" from sub-floor + uncorroborated items | NEW — revives B1's deferred digest sink |
| **P6 site rail only** | wires.json entry, no post | BUILT (B4a in #3861) |
| **P7 press Brief candidate** | long-form story → `engine/press` planner | seam exists (PRESS-FEEDS charter) |
| P0 drop | logged with reason | exists |

**Hardening (from the census):** admit `wire`/`breaking` into `outbox.KINDS` via `make_item` — today's raw-file bypass skips schema validation, id-dedup, the 7-day text-dedup window AND sentinel's cross-account near-dup radar: a real duplicate-content hole once volume grows. Migrate `press_lane._write_outbox_item` onto the standard path (IS-W1 gate).

**Recycle/rewrite lane:** top-performer recycling with fresh tape stamps + "second-wave" posts (story matured → analysis take), using the #3824 rotation+dedup precedent. **Value-add registry** (attachable by router per pathway): tape stamps (B2), our-engine stats (options flow / darkpool / breadth joins by ticker — stats no relay account owns), chart renders, zh line, prediction-market odds stamp (later; a flavor, not a source).

## §5 Employee desks (IS-W4) — four fixed personalities, subtle by law

**Mechanism (all machinery exists):** new `persona_kind: employee` — real named humans on official rails, founder-precedent wiring (#3851): `config/personas/<name>.yml` spec + `desk_network` account entry + Buffer channel (discovery workflow #3848). NO isolation checklist (rev-4 anchor posture). Humans post manually at will; the engine never emits first-person claims (AM-R1 banned patterns, doubly critical on real names), and the near-dup radar + text-dedup guard prevent engine/manual collisions.

**The expression dial (operator's subtlety law, encoded):** per-kind personality intensity in each codex — `wire/news: 0` (house wire voice, zero personality), `analysis (macro/education/signal): 1` (≤1 personality-inflected clause; vocabulary tilt only), `charts/watchlist/receipt: 2` (one playful line allowed; finance value still the meal). Never >2. Enforced by a per-account quirk-lexicon validator + max-quirk-count, fixture-tested. Personality is seasoning, never the meal; "cannot be too cute or overboard" is a validator, not a vibe.

**Codex drafts v1 (Fable-authored; pinned here so the builder assembles, never invents — spawn-handoff law):**

- **Meagan** — Growth Manager, ENFP. Voice base: `fast, reactive`. Register: upbeat, quick, human. Quirks (whitelist): "okay so —" openers, em-dash asides, ≤1 exclamation/post, matcha/open-tabs references ≤1/week. Emoji: signature-set 📈☕️✨, sparing. Banned: finance-bro irony, ALL-CAPS (non-ticker), slang pileups. Dial-1 example: *"okay so the Fed did the thing everyone swore they wouldn't — and the 2-year believed it instantly."*
- **Sophia** — Marketing Lead, INFJ. Voice base: `authoritative desk`. Register: polished, narrative, measured; zero exclamations. Quirks: story-shaped openers ("Three headlines, one story:"), craft/composition metaphors ≤1/week. Emoji: rare, 🖋️ only. Banned: hype verbs, rocket/fire emoji. Dial-1 example: *"Three headlines, one thread: rates, oil, and the dollar spent the afternoon telling the same story."*
- **Kelly** — Growth Lead, INTJ. Voice base: `dry, receipts-forward` (+ pattern/history tilt). Register: terse, analytical, internet-native dry wit; lowercase asides allowed. Quirks: numbered micro-lists, "chart detective" framing, running metaphors ≤1/week. Emoji: 🔍📊 sparing. Banned: cutesy emoji, hedging softeners ("kinda", "maybe"). Dial-1 example: *"three things the close said. 1) breadth narrowed again 2) oil didn't believe the headline 3) vix still isn't paying attention."*
- **Cici** — Asia Markets Lead, ENFP, multicultural. Voice base: `specialist`, `zh: true`. Register: bright, worldly, precise on Asia hours. Quirks: session-handoff framing ("While New York slept…"), tea ≤1/week, occasional zh phrase WITH instant EN gloss; timezone humor light. Emoji: 🌏🍵 sparing. Banned: stereotype-adjacent cutesiness, untranslated zh in EN posts. Cadence: weighted to HK/Asia session (the overnight-US slot nobody else covers — pairs with china_alpha/sector-desk organs). Dial-1 example: *"While New York slept, Beijing did two things: a firmer yuan fix and a quiet OMO drain. One matters more — 先看这个 (start with this one)."*

**Plumbing:** employees ride the existing 6-voice template pools with a **codex quirk-injection pass** at copy generation (no 4 new template pools day one — quirks differentiate; fork a pool only where measurement later demands). Tilts: standard 9-kind tilt with signal ≥0.28 law; Cici's beat joins the China desks. **Sequencing:** specs+codexes commit as spec-only now (news_flash precedent); each account goes live when its Buffer channel id lands; non-news kinds may start on the ladder immediately (founder precedent); wire/news kinds blocked on Persona-W2 cadence resolver; cold-start cadence per the zero-follower traction playbook (reach formats first, quiet-conviction formats later).

## §6 Feedback loop (IS-W5) + surfaces (IS-W6)

Per-post telemetry per account → labels store → weekly admin scorecard (hook family × format × register × account) → ranker retrain + template-pool tuning; ties into the Persona health monitor when the pseudonymous cohort arrives. IS-W6 = Addendum-2 B4b–d unchanged (designed news.html rail via `designer`, zh items + tier gate, terminal hub feed).

## §7 Sequencing, routing, collisions

| Wave | Contents | Lane |
|---|---|---|
| IS-W1 | statements store unification + outbox KINDS hardening + GDELT/Alpaca/Finlight-free providers + trends/pageviews pollers | Opus `builder` |
| IS-W2 | L0 dedupe/cluster + L1 features + garbage gate + golden set + eval harness; L2 ranker after ≥3 wks labels | Opus `builder`; stats review by `reviewer`; golden-set labels Fable/operator |
| IS-W3 | wire_router + P3 chart-reaction + P4 thread + P5 digest + recycle lane | Opus `builder`; P3 card look via `designer` |
| IS-W4 | 4 employee specs/codexes (this doc pins content) + desk wiring + expression-dial validator | Opus `builder`; codexes are FROZEN here |
| IS-W5 | telemetry loop + scorecards + retrain job | Opus `builder` |
| IS-W6 | B4b–d surfaces | `designer` + builder |

**Collisions checked:** publish-time daily read (#3849, dark) — router complements, does not replace; W2R vault triage — P7 feeds it, no overlap; Chronicle statements adapter — deferred, reads the consolidated ledger; event-language contract — law on every pathway; cadence masterplan — floors/ladders unchanged; cold-start playbook — governs employee ramp; DO_NOT_REBUILD — no standing kills touched (CC-News rejection recorded in §2).

## §8 Operator-blocking

1. **Buffer channels** for Meagan/Sophia/Kelly (+ confirm the Cici account exists) — `buffer-channels` workflow discovers ids.
2. **Golden-set session** (~1–2 h): label ~200 items so IS-W2 has ground truth.
3. **NewsAPI.ai $90/mo** approval when IS-W2 coverage data justifies (free tier evaluation first).
4. Optional: Finlight Pro Standard ($99/mo) if its enriched WS proves out; Newsquawk stays optional from Addendum 2.
