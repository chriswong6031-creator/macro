# Marketing Rollout Dockets — Master Index

**Author:** Fable (main loop), 2026-07-19. **Purpose:** the Marketing lobe's content stack is built; the rest of the org is chartered scaffolding. Each docket below is a self-contained writeup that a **fresh session can execute cold** — hand one docket to one session. Read this index + the docket + `CLAUDE.md` before building anything.

**Distribution-first acquisition authority:** when the goal is the fastest credible path from zero audience to the first 1,000 qualified leads, read `research/MARKETING_FASTEST_PATH_TO_FIRST_1000_QUALIFIED_LEADS_FOR_FABLE.md` and its named target book, `research/marketing_dockets/MKT_FIRST_1000_DISTRIBUTION_TARGETS.md`. They override generic channel emphasis, not docket build status or standing platform rules; they do not impose an arbitrary one-week deadline.

---

## 1. State of the lobe (what is BUILT — do not rebuild)

| Capability | Receipts (merged PRs) | Where |
|---|---|---|
| Growth-OS substrate: 11 depts, G0–G7 authority ladder, CMO self-improve loop, governor, contracts | #2916 #2926 | `engine/marketing/` (departments, cmo, authority, state, publication, economics, ledgers, claims, provenance, charter, events, experiments, opportunity_bus, campaign_compiler), `config/marketing.yml`, `scripts/build_marketing.py`, daily.yml step ~L2721 |
| Admin cockpit: legible per-dept + per-engine pages, short dept names | #2926 #2950 | `admin/marketing.py`, `admin/server.py`, `admin/nw_lobe_descriptions.py` |
| Content Studio: mixed-tilt 6-account plan, live-signal gate, stub-strip | #2950 #2961 #2994 | `engine/marketing/content_studio.py` → `data/marketing/content_plan.json` |
| Copywriter: 6 personas, `validate_copy`, deterministic floor + **LLM ceiling** (llm_auth waterfall, double-guarded) | #2994 #3032 | `engine/marketing/copywriter.py`, `config/marketing.yml copywriter:`, `config.yml llm_models.marketing_copy` |
| Chart engine v2/v3: candles, ticker logomarks, MACD/VOL panels, SETUP highlight, CTA footer ("free 14-day trial · mastermind-x.com") | #2994 #3003 | `engine/marketing/chart_render.py`, `logo_cache.py` |
| Facts engines: chart facts, macro/sector/breadth facts, graded receipts, earnings cards | #2994 #3003 | `chart_facts.py`, `market_facts.py`, `receipt_source.py`, `earnings_card.py` |
| Momentum cross signals: weekly MACD+RSI, weekly/biweekly StochRSI | #2971 | `engine/momentum_events.py` |
| Confluence miner → win-rate hooks in posts | #2994 | `engine/tech_confluence.py`, `engine/tech_catalog.py`, `site/tech_lab.html#combos`, `engine/marketing/confluence_source.py` |
| Movers/Attention Desk: multi-cashtag theme lists, round-robin reach injection | #3020 | `engine/marketing/movers_source.py` |
| Beacon (seo_organics): ~1,500 SEO ticker dossiers | #2980 #3000 #3017 | `templates/` + engine-internal render |

Department roster (`engine/marketing/departments.py`): **Command** (office_cmo), **Engine Room** (growth_os, the only one `building`), **Radar** (intelligence), **Workshop** (products), **Studio**, **Broadcast** (distribution), **Funnel** (lifecycle), **Allies** (ecosystem), **Lab** (growth_science), **Sentinel** (trust_office), **Beacon** (seo_organics). Everything except Engine Room + the Studio-adjacent content stack + Beacon's dossiers is **chartered, not built**.

Strategy corpus (read the one your docket cites): `research/MARKETING_FASTEST_PATH_TO_FIRST_1000_QUALIFIED_LEADS_FOR_FABLE.md`, `research/NEURAL_WEB_AUTONOMOUS_MARKETING_LOBE_GRANDMASTER_PLAN_FOR_FABLE.md`, `MARKETING_LOBE_GUERRILLA_GROWTH_AND_OPERATIONS_BY_FABLE.md`, `MARKETING_TRENDSPIDER_PLAYBOOK_AND_CHART_ENGINE_BY_FABLE.md`, `MARKETING_REALTIME_FASTLANE_ARCHITECTURE_BY_FABLE.md`, `MARKETING_ZERO_FOLLOWER_TRACTION_PLAYBOOK_BY_FABLE.md`, `TRENDSPIDER_GROWTH_SEO_AND_GUERRILLA_MARKETING_INTELLIGENCE_FOR_FABLE.md`.

---

## 2. Docket table

| ID | Title | Dept | Priority | Depends on | Blocked on operator? |
|---|---|---|---|---|---|
| [D01](D01_REALTIME_FASTLANE.md) | Real-time fast lane (earnings/breaking instant publish) | Engine Room + Broadcast | **P0** | — | W1 host; W0 buildable now |
| [D02](D02_X_ACTUATION_COMPUTER_CONTROL.md) | X actuation: outbox + computer-control posting loop | Broadcast | **P0** | — | W1 accounts; **W0 merged #3056** |
| [D08](D08_SENTINEL_TRUST_OFFICE_W1.md) | Sentinel W1: pre-publication policy gate + ban-risk rails | Sentinel | **P0** | — | No — build before launch |
| [D03](D03_ENGAGEMENT_TELEMETRY_LAB.md) | Engagement telemetry → Lab learning loop | Lab | P1 | D02 live | Analytics access for W1 |
| [D04](D04_INDICATORS_M2_VWAP_VOLUME_PROFILE.md) | Indicators M2: VWAP / AVWAP / Volume Profile / POC — **COMPLETE 2026-07-19 (#3088 + terminal#147)** | Workshop + Studio | P1 | — | No |
| [D05](D05_BREAKING_DESKS.md) | Breaking desks: news / policy-feed ingestion + cite cards | Radar + Studio | P1 | feeds D01 | No for W0 |
| [D06](D06_RADAR_INTELLIGENCE_W1.md) | Radar W1: real opportunity feeds + cashtag traffic tiers | Radar | P2 | — | No |
| [D07](D07_FUNNEL_LIFECYCLE_MNZ.md) | Funnel W1: UTM attribution + trial-conversion join (MNZ) | Funnel | P2 | D02 live for real data | Analytics/Supabase join |
| [D09](D09_STUDIO_FORMATS_WAVE2.md) | Studio W2: heatmap cards, day-recap, threads, weekly receipts | Studio | P2 | — | No |
| [D10](D10_WORKSHOP_PUBLIC_TOOLS_W1.md) | Workshop W1: free public tools as lead magnets | Workshop | P3 | — | No |
| [D11](D11_ALLIES_ECOSYSTEM_W1.md) | Allies W1: creator/partner/community scaffold | Allies | P3 | — | Mostly operator outreach |

**Sequencing:** D08 → D02(W0) → D01(W0) unlocks launch the moment the operator provides accounts + host. D04/D05/D09 fatten content quality in parallel. D03 turns on the learning loop once posts are live. D06/D07 make the CMO loop real. D10/D11 are later waves.

---

## 3. Standing laws for EVERY marketing session (non-negotiable)

1. **Read first:** `CLAUDE.md` (from origin/main, not a stale worktree copy), this index, your docket, `docs/ACTIVE_BUILD_MAP.md` (collisions), `research/DO_NOT_REBUILD.md`.
2. **Model routing:** Sonnet `builder` agents build; Opus `reviewer` reviews; user-facing surfaces (admin pages count) go through the `designer` agent or main loop — **never sonnet designs**. Tell every builder explicitly: **NO GIT COMMANDS** — builders have self-created and self-merged PRs twice in this program. Audit `git log` after every builder lane.
3. **Git:** fresh branch off `origin/main`; finish the full chain same-day: commit → push → PR → `gh pr merge <n> --squash --delete-branch --admin`. Never reuse a squash-merged branch. Never bare `git stash`.
4. **Verify the artifact, not the code:** after ANY `content_studio.py` / pipeline edit, run the builder and inspect `data/marketing/content_plan.json` — fail-soft catches have silently killed charts before. Local runs of site builders touch many files: restore everything except your target.
5. **Copy discipline:** every user-visible post text passes `validate_copy` (numbers whitelist, banned vocab, cashtags, invalidation disclosure). Never post an invalidated/stale/underwater signal — `is_postable_signal` + `verify_signal_live` are law (the QCOM incident). Confluence win-rate hooks and movers/theme-list copy are kept verbatim — don't route them through rewrite.
6. **Epistemics:** the lobe is **display-tier, off the scored path**. LLMs never originate signals/scores — copy voice only, over deterministic facts. "Validated" in user-facing text is CI-enforced.
7. **Render budget:** heavy compute (per-ticker sweeps, profile calcs, LLM calls) goes off the nightly render path or is cached/gated. The nightly is ~67 min, 4-core-bound, and is the sole advancer of forward ledgers; intraday lanes must not advance ledgers or commit data/.
8. **Secrets:** credentials never enter the repo. Env + runner secrets only (the CXI credential sweep pattern).
9. **When done:** update `~/.claude/.../memory/marketing-lobe-genesis.md` (append a round line) and mark the docket's status line in this index via a PR.

## 4. Delegation prompt template

> Read `research/marketing_dockets/INDEX.md` and `research/marketing_dockets/<DOCKET>.md` in this repo, plus `CLAUDE.md`. Execute the docket's next unbuilt wave end-to-end: build with sonnet builders (NO GIT for builders), review with opus, design surfaces with the designer agent, verify the acceptance criteria, then finish the full git chain (branch off fresh origin/main → PR → same-day squash-merge). Update the docket status line + memory when merged.
