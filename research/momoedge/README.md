# MomoEdge Competitive Study — Reverse-Engineering + Build Docket

Competitive study of **MomoEdge** (momoedge.ai), an "Oracle Terminal" options product, to guide MomoEdge-parity builds in **our Terminal** (`charting-app`) and a future **Prophet** desk (Macro Dashboard; named Prophet because "Oracle" is our rotation lobe). Produced 2026-07-07 from (a) full public JS/HTML source reverse-engineering and (b) ~142 authenticated in-app screenshots. Raw competitor source archived outside git at `~/Documents/Cluade/momoedge_source_archive/` (3.9 MB, 65 JS files) for re-reference.

This bundle supersedes/extends the earlier single-file study `research/MOMOEDGE_ORACLE_COMPETITIVE_FEATURE_STUDY_FOR_FABLE.md` (which was screenshot-less and inferred structure). Here we have the **actual client code**, so scoring formulas, the confidence model, and gate thresholds are extracted verbatim.

## Start here
- **`MASTER_BUILD_DOCKET.md`** — the spine. Parity matrix (8 surfaces × NOW/NOW-SOFT/NEW-DATA/PAID-TAPE), the shared-R2 data-bridge design + new JSON schemas, the sequenced build packages (A→Flow→Heatmap→GEX→PRISM→Tutorial→Prophet+Alerts), epistemics guardrails, and 7 operator questions.

## Source-RE specs (extracted from MomoEdge client JS — exact formulas/thresholds)
- `oracle_spec.md` — **the crown jewel.** Full V1 (9-factor) + V2 (7-phase weighted) live-confidence engine, signal schema, client/server split, T2 gating (SOFI pattern), OCC option construction, 7-gate flow auto-logger, performance engine.
- `flow_spec.md` — flow card schema, score generations (score…score_v5), tiers, badge logic, filter taxonomy, Smart Money Radar, Flow Gauge, Ask-Oracle.
- `chain_heat_spec.md` — contract-day accumulation (≥$3M, 2-min refresh) — signing-free, best fit for our data.
- `gex_spec.md` / `gex_ui_spec.md` — per-strike gamma math, walls/flip/magnet/regime (6-state), market-state card, UI.
- `structural_spec.md` — flow+GEX squeeze/cascade detector (the "can flow feed the picker" module).
- `prism_spec.md` — strike×expiry matrix, lens math (GEX/VEX/OI/VOL/UNUSUAL), Heat Seeker gates, confluence.
- `heatmap_spec.md` — dual-layer price/flow treemap, divergence.
- `alerts_infra_spec.md` — alert taxonomy/channels/presets + Supabase/websocket/Railway infra.
- `tutorial_spec.md` — learning.html guided-course engine (coach, lessons, fixtures).

## Screenshot specs (UI-focused, from ~142 in-app captures)
- `*_FEATURE_SPEC.md` — `flow` / `gex` / `heatmap` / `oracle` / `prism` / `tutorial`. Component trees, control inventories, field/column lists, verbatim guide copy. Source-RE specs close their "needs source confirmation" gaps.

## Our-stack maps (where the build plugs in)
- `our_terminal_map.md` — charting-app `/flow` = `OptionsHubView.tsx` (6 tabs), `/api/flow` R2 read path, tab-add recipe, VPS deploy (`146.190.142.17:/opt/terminal`, rsync + `systemctl restart terminal`).
- `our_data_contracts.md` — every options artifact we already produce (`site/flow`, `site/gex`, `live_flow/*`, `options_hub/*`), its JSON schema, and its **reliability/authority tier**.

## The three load-bearing conclusions
1. **We can match almost all of it on data we already ship.** Their GEX/PRISM/structural math = formulas already in our `engine/gex_engine.py`/`gex_model.py`. The one thing we structurally cannot match honestly is per-print BUY/SELL (`trade_dir`) — needs NBBO tape; our tick-rule direction recovery is 0.41. Present **magnitude-forward, direction-as-soft-lean**.
2. **The biggest net-new win — the Oracle trade-management confidence engine — needs zero paid tape.** Fully reverse-engineered in `oracle_spec.md`; runs on price + geometry + macro (all inputs we have). Their picker (base signal creation) is **server-side**; the confidence/lifecycle engine is **client-side** and now fully specified.
3. **One shared R2 options contract, two readers.** Terminal reads it interactively; the Oracle/Neural Web (Macro Dashboard, nightly) consumes the same objects as gated context sensors + ledger writers. No forked pipeline.

## Doctrine (non-negotiable, per `CLAUDE.md`)
Every new surface ships **display → shadow → confirmer → scored**, each gated by a pre-registered forward ledger. LLM (Ask-Oracle / tutor) may **narrate/de-escalate only, never originate** a score, direction, or escalation. Direction stays soft without NBBO. Index vs single-name GEX separated; regime passport preserved. "Validated" is CI-enforced. Bilingual EN/ZH, no translated `title=`.
