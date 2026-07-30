# Mastermind AI Superintelligence Masterplan — the Analyst OS

**Status:** RATIFIED · P0 ships with this PR · Waves W1–W3 chartered below
**Date:** 2026-07-29 · **Author:** Fable main loop (recon: 4 sweep agents over both repos)
**Trigger:** operator handoff `mastermind_ai_market_reasoning_fable_handoff.md` (ChatGPT Sol conversation, 2026-07-29) — a reference-quality cross-asset answer (bear-steepening stress day) plus ~15 proposed components to close the gap between generic frontier chat and Mastermind AI.
**Companion doctrine:** the handoff's own thesis, adopted as this program's north star — *the moat is not the backbone model; it is an analysis operating system that knows what to observe, what to retrieve, how to test competing explanations, and how to convert evidence into a concise market narrative.*

---

## §0 ACCEPTANCE GATES

**P0 (this PR) is not done unless:**
1. A market-analysis question on the chat surface receives the analyst treatment end-to-end: the system prompt carries the Market Analyst doctrine block (routed by triggers, protocol always-on), the per-turn grounding is the structured Live Market State Packet (TAPE/CURVE/FLAGS/EVENTS/DRIVERS/RATES DESK/VOL/BREADTH/DESK READ/WATCH with per-section freshness stamps), and the model can call `get_market_events` + `search_research` (tier-gated).
2. `tests/test_brain_gateway.py`, `tests/test_brain_doctrine.py`, `tests/test_ask_brain.py` pass UNCHANGED (additive-only prompt changes; existing pins intact), plus new suites `test_brain_analyst_doctrine.py`, `test_market_packet.py`, `test_brain_market_intel.py` green.
3. Leak law extended: analyst-doctrine sentinels join the gateway leak screen; a doctrine echo in an answer is filtered exactly like technician-doctrine echoes today.
4. No epistemics regressions, mechanically guarded: no numeric confidence in the packet render (`test_market_packet` regex guard), no effect-chain fields in events output (whitelist test), no invented odds in doctrine bodies (regex guard).
5. Fail-soft everywhere: every packet block and both tools degrade to absent/empty on missing artifacts — a dev checkout with no `site/live/` still boots and answers.
6. Live verification after merge + VPS deploy: macro-api restarted, a guest `POST /api/brain/stream` turn on "why is the market moving today" returns SSE with a grounded answer, and journalctl shows no new errors. Packet content verified present in the prompt path via a local build against the deployed checkout.
7. Token cost bounded: packet ≤4200 chars (~1.1k tokens) with budget-drop test; doctrine block ≤12.5k chars; both ride prompt-cache-friendly positions (system prompt cached; packet rides the user turn as today's digest does).

**Every later wave inherits:** gates INLINE in its spawn prompt; no child-agent self-merge of flagship surfaces; display-tier freely, gauntlet only at promotion; "validated" never in user-facing copy; falsifier language never front-facing (windows/conditions, "what would change the read").

---

## §1 Objective and reference standard

Make Mastermind AI answer live-market questions at or above the handoff's reference answer, using our proprietary estate as the edge. The reference behavior, distilled into testable properties:

1. Read the tape's *pattern* before naming a cause (regime from structure, not from one ticker).
2. Eliminate regime families explicitly ("bonds down too — kills the recession-panic story").
3. Verify the day's catalyst against a live events feed — never infer causes from prices alone, never start from a headline.
4. Explain the confusing leg mechanically (duration arithmetic: 13bp × ~16y duration ≈ −1.6% TLT).
5. Test the story cross-asset and name the leftovers (semis −4% = a second, independent driver).
6. Separate observed facts / desk-calibrated readings / the model's own inference.
7. End forward with conditional signposts, never certainty or odds.
8. Keep the house voice: plain words, user's numbers quoted back, stance line, [NEXT].

Benchmark case (frozen, from the handoff §12): indices −1.7..−2.3%, 1Y −5.1bp, 2Y −1.7bp, 5Y +4.6bp, 10Y +8.6bp, 20Y +12.9bp, TLT −1.65%, TIPS ~+1bp → expected: inflationary/term-premium stress family, front-vs-long split explained, TLT move mechanically reconciled, oil/news check performed, semis flagged as second story, conditional signposts. Gold-standard synthesis sentence: "the market is pricing weaker near-term growth but worse long-term inflation and fiscal credibility."

## §2 Ground truth (recon summary — what already exists)

- **One gateway, two surfaces.** `engine/neuralweb/brain_gateway.py` (6.4k lines) serves `/api/brain/*` for BOTH the dashboard widget (`mm_brain.js`) and the Terminal (BrainWidget proxies with Supabase auth). The Terminal-side copilot route is deprecated. All P0 work lands in this repo only.
- **Lanes:** fast = DeepSeek V4 Pro (haiku fallback), pro = GPT-5.6 Sol high (codex) → Opus 5 high (oauth) → anthropic; research mode = pro + tool_budget 20. Vision = Pro lane, Claude-routed, ≤4 images — screenshots already flow today on Pro.
- **Tools:** ~43 native tools (no MCP): 24 NW read tools (world_state, spine, contradictions, themes, china, factors, options…) + ~20 gateway tools (quote, symbol context/intel/backtest, screen, fundamentals, earnings, insiders, congress, smart money, movers, house view, watchlist, portfolio brief, charts). `ask_brain` (`/api/ask`, older sibling) has a deterministic question→seed-tools classifier with per-class budgets; the gateway does not (model picks freely under `tool_budget`).
- **Grounding today:** `_grounding_digest()` = ~10 lines of nightly master_brief prose + world_state regime label. No tape, no tenors, no cross-asset numbers, no events. This is the precise gap behind "ChatGPT knew about the oil shock and semis selloff and our AI wouldn't."
- **Doctrine infra:** trigger-routed markdown library with budgets, leak sentinels, fingerprints (`doctrine.py` + 11 technician modules) — fires only on Terminal chart sessions today.
- **Data estate (all display-tier, already computed):** live plane `site/live/` on VPS (`/var/lib/macro-live/public/live`, timers 60s–5min): quotes (indices/futures/VIX/^TNX/oil/gold/copper/DXY/crypto), breadth v1, live market_drivers (typed shock read, EN/ZH), risk_state, shock_state, wires.json (live news rail, wires.v1: ts/en/zh/salience/corroboration/source, 48h window). Nightly: full FRED curve (DGS1..30, T10Y2Y/T10Y3M, DFII5/10 real yields, T5YIE/T10YIE breakevens, THREEFYTP10 term premium), `rates_command.v1` board (policy rate, implied path, **curve_regime_key** e.g. `bear_steepener`, term_premium_dir), vol_regime (VIX/MOVE/VVIX/VRP/term structure state), credit (BAML IG/HY OAS + credit_momentum), crossasset regime, sector/basket/leader/breadth/rotation artifacts, world_state (40+ lobes), track_record with per-desk hit rates + Wilson CIs (news salience desks are GRADED).
- **Research vault:** committed catalog (346 items, ~70/day cap, 3–4 bullet summaries each, institution/side/date) + private-R2 FTS corpus + product API. Not wired to chat.
- **Neural Web:** signal-bus governance layer (516 registered artifacts, 128 NW lobes, 336k-row graded spine, 500-ruling case law, constitution A0–A7). Already feeds chat via read tools; retrieval is exact-field filter only (no ranking); content honest but uneven (0/35 causal edges validated; some thesis nodes empty). NW is absent from CLAUDE.md — a discoverability gap.
- **Telemetry:** `mastermind.response_log.v1` on R2 per answer (question/answer/tools/tokens/latency/thinking traces) + manual admin grading sidecar. No automated answer-quality harness.
- **User context:** watchlists/portfolio_positions/entitlements in Supabase + brain threads; no per-user prefs/memory beyond threads; OIP session-digest (Terminal→EOD) is PLAN ONLY; trade_episodes exist unwired.

## §3 Adjudication of the handoff, component by component

| # | Handoff proposal | Verdict | Ruling |
|---|---|---|---|
| 1 | Market Analyst Skill (investigation protocol) | **ADOPT — P0** | Highest-leverage gap. Implemented as a second doctrine library (`engine/neuralweb/analyst/`, 9 modules: protocol + 5 lenses + 3 playbooks), trigger-routed on ALL pages/modes, per-lane autonomy dial (fast = tight sequence; pro = same evidence bar, more exploration). Preserves stance/[NEXT]/language/proprietary/recommendations-enabled laws. |
| 2 | Live Market State Packet | **ADOPT — P0** (as aggregation, not new computation) | `engine/neuralweb/market_packet.py` aggregates EXISTING artifacts (live plane + nightly boards) into ≤4200 chars with per-section freshness stamps and deterministic FLAGS (curve shape from tenor Δbp; stocks+long-bonds-both-down; dollar+gold both up; oil shock day; VIX spike). Replaces `_grounding_digest` internals. NO fused regime score, NO new cron (per-request assembly, 60s cache). |
| 3 | Regime "confidence: 0.82" fields | **KILL** | CHF-R14/RF-16: LLM/authored numeric confidence forbidden. Regime candidates ride as named states + the evidence that fired them. The engine's own calibrated qualitative word (market_drivers `confidence: medium`) passes through unchanged. |
| 4 | Fresh 18-regime taxonomy | **ADAPT — crosswalk, don't re-vocabulary** | TI-R1 (parallel shock classifier REJECT-REDUNDANT) + MSP-R2 (regime authority chain = risk_radar→market_state→regime_vector; fusion forbidden). The doctrine's stress-day families are TEACHING structure for the LLM's narration, anchored to packet states; no new engine vocabulary, nothing persisted. |
| 5 | Event-normalized news w/ authored first/second/third-order effects + fit scores | **ADAPT — facts only** | TI-R5 kills shock→beneficiary maps as brain feeds; NAR-R4 keeps LLM frame tags display-only. Ship `get_market_events` over the EXISTING wires.v1 rail (ts/headline/salience/corroboration/source) + nightly news digests. Causal chains are narrated by the model at answer time (display), never shipped as feed fields — output field whitelist is test-enforced. |
| 6 | Research vault as retrieval layer (never wallpaper) | **ADOPT — P0** | `search_research` over the committed catalog (lexical score over title/summary/institution + recency decay + top_pick bonus, top-k summaries only). Insider/Pro tiers (mirrors vault product gating). Answers attribute views to institutions — "the street's view," never the desk's. Full-report escalation deferred (rights + quota; W2). |
| 7 | Historical analogue engine | **ADAPT — W2** | Substrate exists (regime_vector parquet with hysteresis history, chronicle timeline, 50y OHLC, sector_cycles.json). Deterministic feature-similarity over stored daily state → dated episodes + what followed, printed with honest N (display-tier). NEVER "8 of 9 times" authority claims; promotion needs the gauntlet. |
| 8 | Intent & freshness classifier | **ADAPT** | P0: the doctrine's freshness law (live questions → packet TAPE + events check; stable questions → no tool spend) + trigger routing IS the v1 classifier, zero latency. W1: port ask_brain's deterministic `_classify_question` seeding into the gateway so weak models get seed tools per question class. No LLM pre-classifier (cost/latency). |
| 9 | Three memory layers | **PARTIAL** | (a) Permanent doctrine = the analyst library (P0). (b) Rolling market-state = already the nightly artifacts + chronicle; intraday freshness = the packet; do NOT build a parallel narrative store (CXI-R12 names that degenerate form). (c) User/portfolio = watchlist/portfolio tools exist; session digest + trade-memory wiring + prefs = W3 (OIP E1 pattern, options lane owns its half). |
| 10 | Model-specific orchestration (DeepSeek constrained, Sol autonomous) | **ADOPT — P0 (light)** | One shared doctrine (same evidence standards) + `lane_dial()` one-liner per lane. Matches the handoff's "one spec, tuned autonomy." Deeper per-model gates (mandatory verification steps for fast lane) = W1 after response-log evidence. |
| 11 | ~40 new MCP endpoints | **MOSTLY ALREADY BUILT / KILL the sprawl** | ~70% exist as native tools. P0 adds exactly 2 (`get_market_events`, `search_research`); W2 adds ≤2 (analogues, curve detail). Tool sprawl degrades DeepSeek tool choice under budget 5 — curation beats coverage. No MCP protocol layer (native tools are the house shape). |
| 12 | Packet refreshed "every few minutes" server-side | **ADAPT** | Sources already refresh on their own timers (60s–5min live plane). Packet assembles per-request with a 60s cache — no new cron, no ledger writes (chronicle gate 5: intraday lanes never advance stores). |
| 13 | Screenshot/market-state extractor | **ALREADY EXISTS (Pro vision) + doctrine** | Vision rides Pro (Claude-routed). P0 adds the tape-reading playbook (yield-green-means-price-down law, futures-vs-cash, mechanical duration check). Deterministic OCR pipeline: NOT NEEDED v1; fast-lane vision = W3 if DeepSeek ships usable vision. |
| 14 | Evaluation rubric + benchmark + regression | **ADOPT — W2** | Offline harness over response_log + frozen benchmark days (handoff case + replayed sessions from chronicle/regime history). LLM-judge scores are internal QA telemetry only — never product copy (CI "validated" guard stands). Weekly regression per lane; rubric in §9. |
| 15 | "Most rising/falling baskets" intelligence layer | **ALREADY EXISTS** | `get_movers`, standouts/leaders artifacts, basket_pulse live. Packet surfaces breadth + (W1) leaders line; tool already answers depth. |

**Independent additions beyond the handoff (this program's own):**
- **Deterministic anomaly FLAGS in the packet** — the "very weird day" combos (stocks+long bonds down; gold+dollar up; curve shape) computed from tape arithmetic and named with their inputs. The user's exact confusion type answers itself from the grounding.
- **Provenance discipline** — every packet section carries its own asof stamp; stale sections say so; the doctrine's honesty law makes the model disclose staleness rather than dress it as live.
- **Graded-desk citation** — news salience desks carry track-record state (hit rate + Wilson CI in qledger); W1 surfaces desk reliability wording ("a desk with a real hit-rate record flags this as high-salience") without numeric invention.
- **Street-view clustering (W2)** — when N≥3 fresh vault reports hit one theme, `search_research` gains a "street clusters" mode (retrieval summary, not authority).
- **Bilingual state passthrough** — market_drivers ZH labels ride the packet so zh answers reuse the desk's own translations.
- **NW discoverability fix (W1, docs)** — CLAUDE.md gains a Neural Web pointer paragraph; the chat is NW's biggest consumer and future sessions keep rediscovering it from zero.

## §4 Architecture — the Mastermind Analyst OS

```
user turn (message [+ images, Pro] [+ page/symbol context])
   │
   ├─ system prompt  = BRAIN_SYSTEM_PROMPT (voice/honesty/stance — unchanged)
   │                   + CONTRADICTION directive (unchanged, de-escalation only)
   │                   + ANALYST DOCTRINE block (protocol always; ≤3 routed lenses/plays; all pages)
   │                   + lane dial (fast: tight sequence · pro: deeper pass)
   │                   + technician doctrine (terminal chart turns, unchanged)
   │                   + language directive (unchanged)
   ├─ user turn      = [CURRENT DASHBOARD STATE] ← market_packet.digest()
   │                   TAPE · CURVE · FLAGS · EVENTS · DRIVERS · RATES DESK · VOL ·
   │                   BREADTH · CROSS-ASSET · DESK READ · WATCH  (stamped, budget-dropped)
   │                   + [CURRENT TICKER STATE] when a symbol resolves (unchanged)
   ├─ tools          = existing 43 + get_market_events + search_research (tier-gated)
   └─ answer         = diagnosis → chain → cross-asset check → what to watch → STANCE → [NEXT]
```

**Boundaries that make this legal:** packet = pure aggregation of engine states with provenance (A0 observe); doctrine = HOW to investigate, never WHAT is true; the model may rank ITS OWN hypotheses and must de-escalate on desk-reading conflicts (contradiction directive unchanged); events/vault tools return facts/summaries with attribution; nothing the model produces persists into any organ state (NAR-R4); public surfaces never see repo internals (CXI-R23 — packet sources are all product artifacts).

**The Neural Web rework, precisely stated:** NW already computes the intelligence; the chat-facing rework is *curation + routing*, not graph rebuilding. P0 gives the always-on curated projection (packet) and two retrieval tools. W1 gives question-shaped tool seeding (port of ask_brain's classifier). W2 gives ranked retrieval (top-k relevance on spine/graph reads, symbol-scoped subgraphs) replacing whole-graph dumps. Content thinness (causal cards, thesis nodes) remains the metabolism program's lane — not chat's.

## §5 Waves

**P0 — this PR (built by 3 opus builders + main-loop integration):**
B-A analyst doctrine library + 9 modules + lane dial + tests · B-B market_packet (live-dir ladder MACRO_LIVE_DIR → /var/lib/macro-live/public/live → site/live; TAPE/CURVE/FLAGS + nightly boards + EVENTS line; ≤4200 chars; 60s cache) + ^IRX/^FVX/^TYX added to the live-quotes CORE universe + tests · B-C get_market_events + search_research + schemas + tests · main loop: gateway wiring (doctrine block all pages, lane dial, digest swap, 2 tool registrations + dispatch + tier gates, leak-screen extension), integration tests, masterplan, ship loop.

**W1 — routing + parity (1 session):** port `_classify_question` seeding into the gateway (per-class seed tools + budgets for the fast lane); wire the analyst doctrine into `ask_brain` (`/api/ask`); LEADERS line in packet (standouts/flow_leaders); graded-desk reliability wording on events; zh render audit of packet labels; CLAUDE.md NW pointer; register packet + tools in `config/synapse.yml` with consumers.
**W1 build-time amendment — curve-tenor feed diagnosis (2026-07-30, #4005):** the chartered "^TNX never resolves into quotes.json" premise was FALSE — a vintage skew (repo-committed snapshots froze 07-27 at the VPS-timer cutover; ^TNX entered DISPLAY_SYMBOLS only 07-29 via #3963). VPS probe: all five packet symbols (^IRX ^FVX ^TNX ^TYX ^VIX) resolve 5/5 via Yahoo spark; feed live 34/34 since P0 merged. The REAL defect was packet-side: `_YIELD_SCALE=10.0` assumed the CBOE ×10 convention while the spark feed delivers percent DIRECTLY — 10Y rendered 0.46% *inside* the 0–20 sanity band (silently wrong in every grounding turn) and bp moves understated 10× (FLAGS could not fire below a real ~30bp spread move). Fixed with pair-level `>15` scale detection (`_yield_pct_pair`, mirroring `templates/live.js tnxPct()`) + Δ×100. **Standing law:** yield-index units are FEED-DEPENDENT in this product (spark/quotes.json = percent-direct; /ws/tape relay = ×10) — every future consumer scale-detects at the pair level and tests BOTH conventions plus the 2026-07-29 probed numbers (see `tests/test_market_packet.py::test_yield_scale_detection_handles_both_conventions`).

**W1 SHIPPED (2026-07-30, #4009):** fast-lane TOOL PLAN seeding (ask_brain's `_classify_question` seeds + events/research nudges; gated lane=fast · mode=chat · page≠terminal — guidance, never enforcement); analyst doctrine on `/api/ask` PLUS that surface's first output leak screen (`_leak_screen_ask` — analyst sentinels + prompt-opener echo → the standard proprietary refusal, EN/zh by question; NOT the removed advice refusal, which stays a no-op per the operator's 2026-07-26 directive); LEADERS packet line from `site/live/basket_pulse.json` (the only group-grain source carrying a day move — sorted on `live_ew_chg_pct`, never `tape_rank`, which ships null on the eod fallback); `digest(root, lang)` zh rendering restricted to DESK-precomputed Chinese (drivers `_zh` fields, wire item `zh`, `curve_regime_label_zh` — the zh audit found no canonical desk vocabulary for the remaining phrases, so the LANGUAGE directive governs those); `mastermind:packet` registered in synapse `external_consumers` on the 5 registered sources + SIGNAL_BUS regen; CLAUDE.md Neural Web orientation bullet. **Governance finding:** the live plane is largely UNREGISTERED in synapse.yml (quotes/breadth/market_drivers/basket_pulse/risk_state and master_brief under either path have no entry) — a later governance pass, not a W1 blocker.

**W2 — depth (1–2 sessions):** historical analogue tool over regime_vector parquet + chronicle (feature vector: curve shape, driver type, vol regime, breadth; returns dated episodes + forward paths with honest N, display-tier); eval harness (frozen benchmark days incl. the §1 case; LLM-judge rubric §9 offline over response_log; weekly regression per lane; admin surface); vault full-report escalation ruling (operator: rights + quota); street-clusters mode; curve-detail tool (FRED tenors + spreads + real/breakeven decomposition on demand); **brain-only ranked wire sidecar** — the news desk DECLINED salience on public wires.v1 (correct: internal ranking numbers never ride user-fetchable payloads — their leak law, ruled 2026-07-30 in the Intelligence Desk V2 lane); the sanctioned shape is a daemon-written sidecar at a NON-public path (/var/lib/macro-live/state/…), spec'd jointly with that desk, consumed by get_market_events via its existing dir ladder. Until then wire events order by recency (honest); source_name ships additively on wires.v1 (#4006).
**W3 — memory (1–2 sessions):** chat session digest (OIP E1 pattern — privacy law: system events only); trade-memory read tool (`trade_episodes` — "you asked about TLT last week when…"); per-user prefs (depth/language) in profiles; fast-lane vision when DeepSeek supports it.
**Dependencies flagged, owned elsewhere:** earnings calendar staleness (3/1364 fresh — OIP W0 gate) degrades `get_earnings`; wires.json production health = E-waves lane; MOVE/SKEW collectors absent (vol packet line already flags what's missing).

## §6 Epistemics compliance (checked against the kill registry)

TI-R5 ✔ events carry no authored effect chains (whitelist test) · TI-R1 ✔ no parallel shock vocabulary; market_drivers is the shock read; LLM never writes classifications into calibrated keys · MSP-R2 ✔ no fused regime score anywhere; states ride side-by-side · CHF-R14/RF-16 ✔ no numeric confidence (regex-tested) · PS-R1/4 ✔ conditional signposts, no event probabilities · NAR-R4 ✔ model output never persists to organ state · CXI-R23 ✔ packet/tools read product artifacts only; context_search stays operator-allowlisted · CXI-R12 ✔ no parallel knowledge store; retrieval = existing canonical artifacts · Chronicle gate 5 ✔ no intraday ledger writes (read-only packet, in-process cache) · Recommendations-enabled (operator 2026-07-26) ✔ doctrine reinforces the direct call; no advice-refusal reintroduced · Falsifier language law ✔ doctrine says "what would change the read," never "refuted" · RUL-NW4 supersession respected (directional verbs allowed).

## §7 Cost & latency budget

Packet ≈ ≤1.1k tokens/turn (was ~0.3k digest) — fast lane worst case +$0.0002/turn at DeepSeek rates; Pro rides cached system prompt so marginal cost is the user-turn tokens only. Doctrine block ≈ ≤3.2k tokens system-side but participates in Anthropic prompt caching (system block cached; cache key changes only on doctrine edits). Two new tools add zero cost until called; both are local-disk reads (<5ms). No new crons, no render-path weight (packet assembles per request from artifacts other lanes already produce). Guard rails: existing per-lane tool budgets, monthly token ceilings, and the packet's own char budget.

## §8 Collision & dependency map (at ratification)

Open PRs: none touch gateway/NW/news/vault engines (#3965 touches theme.js chrome — watch only). news.html estate: consumed read-only via wires.v1 + site/news digests; the news.html upgrade session keeps surface ownership — this program is a consumer, coordinate only if wires.v1 schema changes. OIP masterplan owns options session-digest (E1) and the earnings freshness fix; this program reuses the pattern in W3, never builds a parallel digest. Mastermind trading bot (separate repo) consumes `nw_mastermind_context.json` — untouched by this program.

## §9 Evaluation rubric (W2 harness; internal QA only)

Regime identification 20 · use of user-supplied data 10 · catalyst verification (events checked before concluding) 10 · cross-asset consistency + leftovers named 15 · mechanical translation (duration/curve arithmetic) 10 · fact/desk/inference separation 10 · conditional signposts + invalidation 10 · voice compliance (stance, [NEXT], no machine text, language law) 15. Pass ≥80. Failure modes tracked as tags: headline-first, single-cause forcing, yield-direction misread, stale-as-live, invented odds, refusal regression, doctrine leak. Scores live in the response-eval sidecar; never in product copy.

## §10 Explicitly rejected forms (already covered by standing kills — no new registry rows)

Engine-authored beneficiary/casualty event maps (TI-R5) · a new regime classifier vocabulary or fused regime confidence (TI-R1, MSP-R2, CHF-R14) · LLM-emitted geopolitical probabilities (PS-R4) · always-inject research-vault wallpaper (context stuffing; retrieval only) · a second hand-curated knowledge store for chat memory (CXI-R12) · public internals retrieval (CXI-R23) · an LLM pre-classifier gate on every turn (cost/latency; deterministic routing suffices).
