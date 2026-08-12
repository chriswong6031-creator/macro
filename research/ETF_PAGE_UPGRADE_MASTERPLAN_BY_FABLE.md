# ETF Page Upgrade Masterplan — by Fable

**Date:** 2026-08-12 · **Status:** ACTIVE (this session) · **Owner:** etfs.html surface (blanket `macro` program; no dedicated sub-program — this file is now its program record)
**Operator mandate:** the Fund Flows page (mastermind-x.com/etfs.html) has been an outstanding early-surface for names that later ran (operator cites SPCX, CRWV, NVDA, TSM, uranium complex, CRCL). Invest heavily: more funds for granularity, investigate fund weighting, advanced calculations/engine upgrades for accuracy+robustness, then a full UI/UX pass aligned with macro.html design taste.

---

## §0 ACCEPTANCE GATES (not done unless)

1. **Existing suites green**: `tests/test_etfs_gate.py`, `test_etf_board.py`, `test_etf_new_sponsors.py`, `test_etf_pulse.py` all pass, plus new unit tests for every new engine function (synthetic fixtures, incl. adversarial ones listed in §3).
2. **Tier contract intact**: free shell carries zero graded rows; shell ≤130KiB budget holds; `site/premiumdata/etfs.json` gate untouched (`config/site_access.yml`); partials remain the single source for gated/ungated builds.
3. **Display-tier epistemics intact**: `may_rank/gate/size: false` blocks stay; stance vocabulary unchanged (Act · Get ready · Watch — don't chase · Protect gains · Stand aside · Ignore); NO composite regime/allocation verdict (DNR:KILL-REGIME-SCORECARD); no "validated"/accuracy claims in user-facing copy (CI-guarded); falsifier language never front-facing; plain-word null disclosure for every new stat (banned-vocab tests extended to new copy).
4. **Universe expansion proven, not asserted**: every added fund ships with a real fetched snapshot receipt (collector run in this worktree) or is dropped; no silent parse failures — coverage table renders every fund with cadence + history depth.
5. **Decomposition correctness pinned by tests**: pure creation/redemption fixture → selection ≈ 0; pure rebalance fixture → flow ≈ 0; share-split fixture → guarded (no fake accumulation); duplicate-snapshot fixture → deduped; weight-sum sanity guard fires on corrupt snapshot.
6. **Weighting is a lens, not a promotion**: equal-weight fund counts remain the primary read; any weighting shown is secondary, structural (not fitted), disclosed in plain words, and red-teamed by an opus reviewer before ship (adjudication coverage gate). No predictive-weight claims without gauntlet — this session explicitly does NOT promote.
7. **Render budget respected**: zero new network calls in `build_etf_page` render path; new computation stays O(snapshots already loaded); heavy work (backfill, fetches) lives in collectors/nightly only. Ledger writes happen on the nightly path only (nightly is the sole advancer of forward ledgers).
8. **Local proof**: `build_etf_page` runs on real `data/` in this worktree via a scratch harness; rendered HTML screenshots (light + dark + zh) attached to the PR body.
9. **i18n parity**: every new EN string has a zh dual-span (`.l-en`/`.l-zh` page-local pattern); no translated text in `title=` attributes.
10. **Ship loop complete**: commit → push → PR (screenshots in body) → `merge-on-green` → post-merge render covers → live verification of https://www.mastermind-x.com/etfs.html.

---

## §1 Current architecture (census 2026-08-12)

- **Template:** `templates/etfs.html.j2` (728 ln) + partials `_etf_board_rows`, `_etf_fresh_cards`, `_etf_accumulation_rows`, `_etf_trim_rows`, `_etf_macros` (tier-wall parity via shared partials). All CSS inline; zh via page-local dual spans.
- **Builder:** `scripts/build_site.py::build_etf_page` (L3056-3161) → writes `site/etfs.html`, `site/premiumdata/etfs.json`, `site/stockdata/fund_flows.json`.
- **Engines:** `engine/holdings_signals.py::etf_signals/all_etf_signals` (share-based conviction_pp per fund-ticker, D71), `engine/etf_board.py` (stance, hero verdict, fresh conviction), `engine/etf_consensus.py` (consensus_favored: n_accum/n_trim/n_new/n_exit + net/gross conviction_pp, min 2 funds, top 40; weight_trajectory sparklines; fund_coverage).
- **Data:** `data/etf_holdings/<TICKER>/<date>.parquet` (75 funds) + `data/holdings/` (ARKK/ARKW) = 77 funds; schema `ticker,name,weight_pct,shares,market_value,as_of`; collectors `collectors/etf_holdings.py` (SSGA/GlobalX/Roundhill/VanEck/FirstTrust/Sprott/Amplify/Defiance/Bitwise/Invesco/Procure/ETC + stockanalysis.com fallback), nightly via `scripts/collect.py`.
- **Known gaps:** consensus is an equal-weight count+sum; conviction is %-of-fund-weight only (no $ magnitude — a 0.5pp add by a $4B fund reads the same as by a $30M fund); passive-fund weight changes conflate price drift/index rebalance with true investor flow; no split/dup/cadence guards; no measurement loop; no site_semantics glossary entry.

## §2 Design principle — two signals, not one

Fund holdings changes carry **two distinct signals** that the current engine conflates:
- **FLOW** (works for passive thematic funds — URA, SMH, NUKZ…): creation/redemption scales all constituents' shares roughly pro-rata → Δ(common scale factor) = investor demand into the theme, which mechanically buys constituents. This is the "fund flows" the operator prizes.
- **SELECTION** (works for active funds — ARKK, OZEM…): per-constituent share changes beyond the common scale factor = manager conviction.

**W1 centerpiece:** decompose each fund's snapshot-pair diff into `flow_component + selection_component` per constituent (robust common-scale estimator, e.g. median share ratio across continuing constituents; residual = selection). Aggregate per ticker across funds: flow-$ and selection-$ separately, with implied price = market_value/shares. Everything stays inside the holdings lens (no cross-organ composite).

## §3 Backend waves

### W1 — Decomposition + dollars + robustness (engine core)
- `engine/holdings_signals.py`: add flow/selection decomposition on the existing snapshot-pair diff path; keep `conviction_pp` untouched for compatibility.
- **$ estimates:** per fund-ticker event: `Δshares × implied_price` split into flow-$/selection-$; per-ticker cross-fund aggregates: `total_$`, `flow_$`, `selection_$`, `n_funds_flow`, `n_funds_selection`.
- **Robustness guards (each with a test fixture):** share-split guard (shares jump k× while market_value ≈ flat → normalize, never fake accumulation); duplicate same-day snapshot dedup; cadence normalization (per-day rates when funds report at different intervals; stale-fund flag past N days); weight-sum sanity (sum(weight_pct) far from 100 → quarantine snapshot + printed null); missing-constituent continuity (ticker rename/absence ≠ full exit unless persistent).
- **Persistence/breadth:** per fund-ticker streak (consecutive snapshots same direction), acceleration (Δ conviction vs prior window); per-ticker breadth = distinct funds adding within lookback.
- `engine/etf_consensus.py`: extend consensus rows with the new fields; `contested` logic aware of flow-vs-selection disagreement.
- Payload/template: add fields to `premiumdata/etfs.json` + minimal row wiring (real presentation deferred to UI wave); `stockdata/fund_flows.json` enriched (n_funds, net $, breadth).

### W2 — Universe expansion + fund registry + weighting lens
- **Registry:** new `config` block per fund: `{type: active|thematic_passive|sector, sponsor, theme_tags}` — drives which component (flow vs selection) is the fund's primary signal, and the coverage table.
- **Expansion:** consult `research/ETF_DATA_SOURCES.md` (D72) + `collectors/etf_holdings.py` sponsor support; add ~25-40 funds prioritizing operator themes (space, AI/datacenter/compute, nuclear/uranium, robotics, defense, crypto infrastructure, semis, biotech, rare-earths/critical minerals, drones, grid/power) where the sponsor is parseable or the stockanalysis fallback covers it. Each add proven per §0.4; backfill history where the feed allows (Roundhill/GlobalX claim 2024+), committed under `data/etf_holdings/`.
- **Weighting investigation (§4 outcome lands here):** structural weighting lens only.

### W3 — Measurement ledger + semantics (accuracy earns receipts)
- Nightly-path writer: each night append consensus-board top-N (ticker, rank, net conviction, flow/selection split, as-of price) to `data/etf_board_ledger/` (append-only, one file per date). Grader fills forward returns (5/21/63d) as they mature; summary artifact for the Calibration Lab (below-the-fold; windows language, never "accuracy/validated" front-facing).
- `docs/site_semantics/etfs.md`: glossary for every published stat (closes the semantics gap).
- This ledger is what earns any FUTURE predictive fund-weighting promotion; not consumed by rankings now.

## §4 Weighting investigation (decision)

Question (operator): should some funds count more in consensus?
- **Predictive weighting (fit weights to forward returns): REJECTED for now** — history depth is weeks-to-months for most funds (honest-N far too small per fund; episode-level N smaller still), and any fitted weighting is a promotion-to-authority move requiring prereg + gauntlet. The W3 ledger accrues exactly the evidence a future gauntlet needs.
- **Structural weighting (no fitting): ADOPTED as a secondary lens** — three transparent, mechanical factors: (a) signal-type match: selection events from `active` funds and flow events from `thematic_passive` funds count fully; the mismatched component of each fund is discounted (it is mechanically noisier — passive "selection" is mostly index rebalance; active "flow" is mostly firm-level marketing); (b) $ magnitude: aggregate real dollars, not just fund counts — a $4B fund's 0.5pp is not a $30M fund's 0.5pp; (c) freshness/cadence: stale funds (no snapshot ≥ N days) flagged and excluded from "this cycle" reads.
- **Primary read stays equal-weight fund counts** (breadth is the most manipulation-resistant stat); the weighted lens is presented beside it, plainly labeled. Red-team gate (§0.6) before ship.

## §5 UI/UX wave (after backend merges locally, same PR)

- Designer (opus) pass, doctrine + frontend-design skill loaded, aligned with macro.html's design language; I (Fable) pin the spec before build.
- Keep: partial architecture (tier-wall parity), stance system, zh dual-span, ≤130KiB shell, premium gate, disclosure footer.
- Elevate: glance-tier hero (state + plain-word stance); consensus board readability (the $ and breadth columns become first-class); flow-vs-selection presented as plain words ("investors are pouring in" vs "managers are picking it"); persistence chips; coverage table → fund registry view; hover receipts for every stat (Tier-2, own banned-list).
- Proof: light/dark/zh screenshots in PR body (§0.8).

## §6 Constraints (standing)

- DNR:KILL-REGIME-SCORECARD (no composite regime/allocation verdict on this page), DNR:KILL-LLM-ORIGINATION (no LLM-originated scores), display-tier Authority blocks stay verbatim.
- Access contract `config/site_access.yml` (shell public exact; `/premiumdata/` enforced early) — do not touch.
- Render lane: `build_etf_page` is on `build_site.py` spine (render.yml region `macro`; template edits → scope=all). No new I/O on that path.
- Bilingual EN/ZH; no zh in `title=` attrs (CI-guarded).
- `data/` writes only on nightly path; intraday lanes discard them.

## §7 Rollout & verification

1. W1 → W2 → W3 built sequentially by opus `builder` agents in this worktree (branch `claude/etf-page-upgrade-20260812`), each wave with tests green before the next starts.
2. Opus `reviewer` red-team on weighting/claims/copy + code review of the full diff.
3. Designer wave (§5), then local harness render + screenshots.
4. One PR: engine+collectors+config+templates+tests+this file (+ backfilled parquets if modest). `merge-on-green` label; live verify after the covering render.
5. Post-merge: first nightly collects expanded universe; coverage table verifies day-2. Ledger begins accruing; revisit predictive weighting only when the ledger has real depth (explicitly out of scope now).
