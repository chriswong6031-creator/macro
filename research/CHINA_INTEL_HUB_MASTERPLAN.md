# China Intelligence Hub — Masterplan (Fable program, 2026-07-06)

Status: ACTIVE — orchestrated build.
Source paper: `/Users/chriswong/.codex/worktrees/5173/Macro Dashboard/research/CHINA_INTELLIGENCE_HUB_FREE_DATA_RESEARCH.md` (Codex, 2026-07-06)
Prior art: `research/CHINA_INTEL_POWERHOUSE.md`, `research/INTELLIGENCE_HUB_V2_RESEARCH.md`, `research/CHINA_ENGINE_REASSESSMENT.md`
Model: `china_intel.html` becomes the China analog of `intelligence_hub.html` — a hub-and-spoke command page consolidating existing + new China subpage boards.

## 1. Verdict on the Codex paper

The paper's product thesis is right (provenance-heavy, validation-aware, "what changed in official language / disclosures, is it priced, does it historically matter"). Its repo awareness is badly stale — roughly half of its proposed build is already live:

| Codex proposal | Reality in repo |
|---|---|
| Phase 1: official policy phrase ledger (1 wk) | **~80% built.** `collectors/china_official_corpora` (State Council/PBoC/NDRC/CSRC/People's Daily, body hashes, layout rank) + `engine/communique_diff.py` (APPEARED/DROPPED/LEAD_SHIFT events, phrase book, qledger salience-only claims, registered accruing experiment `qledger-w6-communique_diff`). Gap: not wired into `china_intel_bus`, no UI card. |
| Phase 3: market tape / A-H / Connect / margin | **Data all collected.** `hk_ah_official` (~190 A/H pairs + reconstructed index), `china_connect` (southbound live; northbound curtailed 2024-08), `hk_southbound_holdings` (per-stock), `china_margin` + `china_margin_detail` (PIT per-name), `china_flows` (AH premium, limit breadth, ETF shares), QVIX. Gap: no venue-divergence surface consumes them. |
| GDELT narrative divergence (Phase 5) | **Built.** `engine/missing_tape_gdelt.py` onshore-zh vs offshore-en tone divergence z (`data/missing_tape/tone_divergence.parquet`) + GDELT wire in `china_news`. Gap: not surfaced on any China intel page. |
| Phase 4: bespoke validation ledger | **Duplicate — do not build.** qledger promotion gate (n_dates≥25, Wilson CI>0) + `data/experiments/registry_seed.json` hooks + `engine/desk_grader.py` are the house apparatus. New families REGISTER, they don't reinvent. |
| `china_intel.event.v1` bespoke event schema | **Drop.** qbus/qledger claims + per-surface JSON contracts already carry provenance/staleness. A parallel event spine would fork the epistemics. |
| "China lens inside `intelligence_hub.html`" as centerpiece | **Inverted.** Operator direction: `china_intel.html` is the hub, mirroring the US hub's anatomy. A small cross-link card on the US hub is a cheap late addition, not the product. |
| Satellite proxies (Sentinel-5P/FIRMS/VIIRS), Baidu Index, World Bank/IMF/BIS context | **Cut.** Off render budget, seasonal confounds, terms risk, or annual-frequency (not event timing). Revisit only after core hub proves usage. |
| CNInfo filing metadata ledger | **Real gap — build.** No CNInfo/inquiry-letter collector exists. But `china_buyback`, `china_pledge`, `china_earnings`, `china_analyst`, `china_block_trades`, `china_zt_pool` already cover most special-situation categories; the new build is unlocks + inquiry letters + a fusing desk, not a from-scratch filing plane. |

What the paper misses entirely: the 20+ existing China pages (stocks board, sector desk, baskets ×2, subsector rotation, cycles, strategies, allocation, heatmap, lookup) that the hub must consolidate; the V2 hub rulings (edge-remaining ranking, agreement≠consensus, discovery lanes); the Tushare freeze; and the dead-northbound gotcha.

## 2. Rulings (locked for this program)

- **R-1 (hub anatomy):** `china_intel.html` keeps its URL and becomes the full hub: command bar (regime/cycle/PBoC stance/liquidity), desk status board with qledger honesty chips, cross-surface conviction (existing), discovery queue, page directory of the whole China suite. Spokes stay separate pages.
- **R-2 (edge-remaining, not agreement):** any China command-list ranking follows INTELLIGENCE_HUB_V2 rulings — sort by (edge_remaining, conviction), leading-gap multiplier, priced-in penalty from already-collected RS/off-high/extension fields. Never triple-count agreement.
- **R-3 (epistemics):** every new surface is display/context-only. New signal families register in `data/experiments/registry_seed.json` (qledger salience-only claims where apt). The word "validated" never appears in new UI (BC-2 gate). LLM text may only de-escalate.
- **R-4 (no new event spine):** provenance/staleness ride the existing per-surface JSON contracts + bus `surface_asof`/`max_staleness_days`. Extend `china_intel.briefing.v3` additively (bump to v4 when new blocks land).
- **R-5 (pipeline):** collectors → `--group asia` (asia-close.yml 08:30 UTC, ~40-50 min headroom in 90-min budget). Builders append to asia-close sequence. Heavy per-ticker artifacts → R2, never git. Nothing new on the US-nightly critical path.
- **R-6 (data honesty):** northbound Connect labeled discontinued (2024-08); Tushare plane frozen 2026-06-21 — never prefer it over fresh free planes; zt_pool has no PIT history (display-only); CCTV/wire tone history is shallow (2026-06→).
- **R-7 (i18n/UI):** `t(en, zh)` spans, `data-tip-en/zh` (never translated `title=`), zh up/down flip via `--up/--down` tokens, self-hosted fonts, `report_base.html.j2` for new subpages, mobile progressive disclosure (cap rows + expanders).

## 3. Target architecture

```
site/china_intel.html            ← THE HUB (upgraded in place)
  spokes (existing):  china_news.html · china_policy_watch.html · china_altdata.html · china_radar.html
  spokes (new):       china_special_situations.html
  boards (existing, linked from hub directory):
     china.html · china_stocks.html · china_sector_desk.html · sector_central_china.html ·
     sector_cycles_china.html · baskets_china.html · baskets_china_ths.html ·
     subsector_rotation_china.html · subsectors_china.html · china_heatmap.html ·
     china_lookup.html · china_strategies.html · china_allocation.html · allocation_china.html

engine/china_intel_bus.py  briefing v4 = v3 + policy_phrase (communique_diff) + special_situations
                                        + venue_divergence + narrative_divergence (GDELT tone)
engine/china_special_situations.py   NEW desk engine → site/chinaspecialdata/special.json
engine/china_radar.py                + venue-divergence pair family (A/H, ADR-proxy, southbound)
engine/china_intel_hub.py            NEW command apparatus (per-ticker fusion, edge-remaining rank,
                                     discovery lanes, snapshot ledger data/china_hub/signal_snapshots.jsonl)
```

## 4. Waves

- **W1 — Hub v2 + wiring quick wins (PR-1).** Bus: add `policy_phrase` block (read `site/communique_diff/latest.json`) + `narrative_divergence` block (GDELT tone z). Template: hub header/command bar, 6-desk status board (news/policy/altdata/radar/stocks/sector) with staleness + qledger chips, communique-diff card, narrative-divergence chip, full China page directory grouped by family, keep conviction/chains/what-changed. Schema → `china_intel.briefing.v4`.
- **W2 — China Special Situations desk (PR-2).** New collectors: `china_unlocks` (restricted-release queue), `china_inquiry` (CNInfo/exchange inquiry-letter metadata; endpoints to be live-verified, akshare candidates first, degrade cleanly). Engine fuses unlocks + inquiry + buybacks + pledge stress + earnings preannouncements + block-trade anomalies → categorized event cards + per-ticker flags. New page (report_base), bus block, hub card, experiments-registry seed entry (salience-only qledger family `cn_special_sits`).
- **W3 — Venue divergence (PR-3).** Extend `china_radar` with venue pair family: A/H premium per-pair z (hk_ah_official), offshore-ETF-vs-onshore gap (KWEB/FXI/MCHI vs CSI300 — yfinance, US-nightly data OK read-only), southbound intensity vs HK sector RS. New radar section + bus passthrough (radar.json divergences list is additive). Ledger entries accrue in the existing radar ledger.
- **W4 — Command apparatus (PR-4).** `engine/china_intel_hub.py`: per-ticker fusion (chinanews/by_ticker + chinaaltdata/by_ticker + radar flags + stocks-board membership + special-sits flags) → command list ranked per R-2; discovery lanes (LHB first-time seat, margin-detail velocity, southbound-holdings delta, THS emerging concepts) — all off-desk-capable; daily snapshot ledger + registry seed entry (`track_record` hook, come-back ≥25 sessions). Hub command-table + discovery sections.
- **W5 — Polish + integration (PR-5).** Nav mega-menu China-intel family links; US hub cross-link card ("China Lens" routing card only); i18n sweep; CI guards green (check_validated_claims, check_title_i18n); mobile audit; memory + research doc updates.

Deferred (post-program docket): PDF text extraction for filings; phrase-polarity map (communique D9); attention proxies; physical proxies; NBS/DBnomics macro backfill; entity resolver hardening beyond the existing basket-spine crosswalk.

## 5. Verification per wave

Local render of touched pages (MACRO_DUMP_VM pattern where applicable) + pytest for new engines (fixtures: missing surface, stale surface, empty events) + `python scripts/check_validated_claims.py` + `python scripts/check_title_i18n.py`. Each PR same-day squash-merged; asia-close nightly is the sole forward-ledger advancer.
