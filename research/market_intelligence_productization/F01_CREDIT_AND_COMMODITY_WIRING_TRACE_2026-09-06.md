# F01 Credit and Commodity Data-Plane Wiring Trace — 2026-09-06

Packet B-A-F01-2 (lane F01, wave A-spare, Meta-CEO B). Ledger rows: MO-DELTA-008, MO-DELTA-013, MO-PAID-004.

## §0 Scope and authority ceiling

This is a **read pass, not a refactor**. No engine module is edited by this packet. `authority_ceiling = context_only`
for MO-DELTA-008, MO-DELTA-013, and MO-PAID-004: nothing named in this trace may be promoted to rank, size, gate, or
escalate authority. The existing display-only ceiling is already in code: `engine/credit_momentum.py:1940`
(`"authority": dict(AUTHORITY_V1)`) and `scripts/build_bonds.py:1116` (authority default
`{rank: False, size: False, gate: False, escalate: False}`).

## §1 Credit producers — machine-readable table

| module | emitting function (file:line) | artifact written (path, or NONE) | consumer (file:line) | rendered surface (file:line, or NONE) |
|---|---|---|---|---|
| engine/credit_momentum.py | `def snapshot(root: str \| Path \| None = None) -> dict` at engine/credit_momentum.py:1568 (data root `_data_root` :165; HY/IG aggregate load :1596-1597; velocity :1687; roster payload :1951-1956; ORCL watch builder :948; transition watch :1014; FINRA breadth :1250; own-store breadth :1437; confluence tags :1155 and :1183) | (a) `data/corp_bonds/credit_momentum.json` — `out_path = out_dir / "credit_momentum.json"` at :1995, `out_path.write_text(json.dumps(payload, …))` at :1997. (b) `data/corp_bonds/forward_log.jsonl` — `_upsert_forward_log` at :780, path `root / "corp_bonds" / "forward_log.jsonl"` at :812, keep-FIRST, nightly-lane gated (`COLLECT_LANE` skip at :803) | `scripts/build_bonds.py:550` (`cm_path = data_root / "corp_bonds" / "credit_momentum.json"`) inside `def build_corp_credit_vm(data_root: Path \| None = None) -> dict` at :507; independent second consumer `engine/bonds_alerts.py:278` (docstring: "Compute debounced state-flip events from credit_momentum.json"), path built at :303, absent-file skip at :306, read-failure warn at :313; third consumer `scripts/build_bonds.py:1083` `_build_corp_credit_bond_health(cc_vm)` → `data/bonds/bond_health.json` at :1637 | `templates/bonds.html.j2` — hero :691-704, spread gauges :707-726, theme tiles :730-733, ORCL chip :775-782, fallen-angel :792-802, new-issuance :809, FINRA :819-820, maturity wall :848-872. Render call `scripts/build_bonds.py:1547` (`env.get_template("bonds.html.j2").render(… cc_vm=cc_vm …)` at :1547-1552), page written `write_page(site / "bonds.html", html)` at :1554. Live page: bonds.html, nav entry templates/_navlinks.html.j2:209 |
| engine/bond_cross_asset.py | `def snapshot(f: pd.DataFrame) -> dict \| None` at engine/bond_cross_asset.py:165; `_beta` :54, `_drivers` :90, `_impulse` :145, `_verdict` :219. Credit leg is HY OAS as the equity canary — module docstring :94 | NONE. The module is a pure function over the caller's frame; it contains no `json.dump`, `write_text`, or path construction (verified by grep over the whole 229-line module). Its output is persisted only by its caller | `scripts/build_bonds.py:1485-1486` (`from engine import bond_cross_asset as _bx` / `xasset = _bx.snapshot(f)`), chart at :1462 (`xasset_betas`), persisted at :1572 (`snap["bond_cross_asset"] = xasset`) into `data/bonds/bond_health.json` (:1637); downstream reader `engine/neuralweb/world_state.py:2450-2478` | templates/bonds.html.j2:1023-1036 (`{% if xasset_vm %}`, `{% set xa = xasset_vm %}`, chart `charts.xasset_betas`) |
| engine/market_drivers.py | `def snapshot() -> dict` at engine/market_drivers.py:581; credit family spec `"credit_stress"` at :99-107 (defining leg `("hy_oas", "d", +1, 1.0, None)` at :105, `("hyg_lqd", "p", -1, 0.6, None)` at :107); `_cfg` :226; `assemble_frame` :246; `projections` :270; `classify_day` :340; `repricing_coherence` :454; label map :179-180; ZH labels :195 and :217 | (a) `site/live/market_drivers.json` — written by `scripts/build_risk_state.py:426-428` (`drivers_snap = market_drivers.snapshot()`, `drivers_out = out_dir / "market_drivers.json"`). (b) `data/regime/market_drivers_log.parquet` — `def append_log(snap, allow_write=True)` at :619, lane gate `_ledger_advance_enabled()` at :633, PS-R7 intraday guard at :635, path at :640 | `scripts/build_basket_pulse.py:662` `_load_market_drivers` (reads site/live/market_drivers.json, path at :669, used at :1014 and :1187-1189, family/primary read at :629-630); `scripts/build_site.py:6137` (`drivers=latest.get("market_drivers")`); `scripts/build_flip_confirmation.py:12`; preview CLI `scripts/market_drivers_preview.py:20`; intraday no-write call `scripts/build_risk_state.py:427` | NONE that is credit-labelled. `grep -rn "market_drivers" templates/` returns zero hits. The `credit_stress` family reaches a user only anonymously, folded inside the drivers rollup |

**This is the packet's principal null and must be printed in plain words**: the credit-stress driver reads a HY-spread
leg every night, but no page names it as credit — it only ever reaches the reader inside a combined "what moved
markets" summary.

## §2 Commodity pages — per-page binding (MO-PAID-004 acceptance_test, verbatim)

| page | builder (file:line render call) | engine module chain (file:line imports) | verified? |
|---|---|---|---|
| templates/commodities.html.j2 | scripts/build_commodities.py:1391 (`env.get_template("commodities.html.j2").render(`) | engine.commodity_supply_context :351, engine.commodity_carry_context :427, engine.commodity_mtf :497 and :1043, engine.commodity_conviction :530, engine.commodity_signals :536, engine.commodity_signals/commodity_inputs/commodity_conviction :1199, engine.commodity_alerts :1200, engine.commodity_index :1244, engine.commodity_cycle_state :1268, engine.commodity_confluence :1283, engine.commodity_news :1315, engine.i18n :1354, engine.trend_episode.current_episode :1376. Also writes data/commodity/latest.json for the hub card (module docstring :7) | **YES** |
| templates/commodity_strategies.html.j2 | scripts/build_commodity_strategies.py:111 (`env.get_template("commodity_strategies.html.j2").render(groups=groups, built=built, C=C)`) | `from engine import active_commodity as Ach` :30, `from engine import commodity_strategies as S` :31, engine.i18n :88 | **YES** |
| templates/spr.html.j2 | scripts/build_spr.py:261 (`env.get_template("spr.html.j2").render(`) | `from engine import strategic_reserves as sr` :35 (sole engine producer), engine.i18n :256 | **YES** |

Nav placement (all three already reachable, existing product family, no third header): templates/_navlinks.html.j2:201
sub-trigger, :203 Commodity Dashboard, :204 Strategies, :205 Strategic Reserves.

**Record explicitly: MO-PAID-004's "engine wiring UNVERIFIED" is now VERIFIED for all three pages.** No page is
recorded as unbound.

## §3 Source identity and vendor rights (the half of MO-PAID-004 that stays NULL)

- Credit: FRED/ICE BofA `BAMLH0A0HYM2` (HY OAS) and `BAMLC0A0CM` (IG OAS), mirrored data/archive/*.parquet +
  data/fred/*.parquet — engine/credit_momentum.py:28-29. Equity/ETF legs via Yahoo (`_load_yahoo_close` :207,
  `_load_equity_close` :228).
- Commodity: Yahoo via lib.store — engine/commodity_inputs.py:53 (`df = store.read("yahoo", ticker)`); FRED real
  yields/breakevens/rates/balance sheet + Yahoo DXY per docstring :11.
- SPR: EIA weekly US SPR series data/eia/spr_stocks (kbbl) — engine/strategic_reserves.py:6; only US (EIA weekly) and
  Japan (METI) break out government stocks — :19.

**Printed null, verbatim intent:** This pass identified where each series comes from. It did not read a single vendor
licence or terms-of-use page, so no redistribution right is established here for FRED/ICE BofA, Yahoo, EIA, or METI.
Anyone who needs that answer must read the terms — this record does not supply it. No licence status may be inferred,
including for EIA.

## §4 Single-issuer finding — confirmed narrowly, refuted at plane scope

The ledger's MO-DELTA-008 `missing` cell — "broad HY/IG aggregate credit surface (current instance single-issuer
only)" — is **FALSE AS WRITTEN**. The aggregate HY/IG surface already ships on bonds.html:

- templates/bonds.html.j2:707-726 — card "3. SPREAD GAUGES (4 chips)", `{% for g in cc_vm.gauges %}` at :711,
  plain-word null state at :723 ("Building history — check back soon.").
- scripts/build_bonds.py:748 `_build_spread_gauges(roster, market, ladder)`; roster keys read at :803-806 (`ig_oas`,
  `hy_oas`, `quality_spread`, `ccc_bb`); chip bodies :813-866; called at :581, placed into the VM at :607.
- engine/credit_momentum.py:1951-1956 `"roster": {"hy_oas": …, "ig_oas": …, "quality_spread": …, "moodys_spread": …,
  "ccc_bb": …}`, series loaded at :1596-1597 via `_load_archive_merged("BAMLH0A0HYM2", "hy_oas", …)` /
  `("BAMLC0A0CM", "ig_oas", …)`.
- Aggregate HY/IG also charted: scripts/build_bonds.py:221-222 (`_mser("HY OAS", …, _col(fr, "hy_oas"), years)` /
  "IG OAS").
- Aggregate breadth also ships: templates/bonds.html.j2:819 (`{% if cc_vm.finra %}`) from
  engine/credit_momentum.py:1250 `_load_finra_breadth` and :1437 `_build_own_store_breadth`.

What **is** single-issuer is the ORCL watch chip only: templates/bonds.html.j2:775-782,
`{% if cc_vm.watch.orcl and cc_vm.watch.orcl.g_spread_bp is not none %}` → scripts/build_bonds.py:1005-1025 →
engine/credit_momentum.py:948 `_build_orcl_watch`.

MO-DELTA-008's `missing` cell is wrong as written. The corrected gap is not "no aggregate HY/IG surface" — one
already ships — it is the surface-allocation and issuance-window reconciliation questions named in §5 and §6.

## §5 In-flight reconciliation — PR #6904

Verified 2026-09-06 via `gh pr view 6904 --json state,headRefName,title,files -R mastermindx-market-intelligence/macro`:
**OPEN**, head `claude/mo-b-b1-b-f09-2`, title "[MO-BB1] B-F09-2: Is the window open for new bond deals? HY/IG credit
issuance window gate parallel to the IPO leg", files include engine/credit_window.py, tests/test_credit_window.py,
scripts/build_ipo.py, templates/ipo.html.j2. **engine/credit_window.py does not exist on main** at the time of this
pass (verified absent in the working checkout).

- (a) On merge, the credit plane gains a **fourth** module.
- (b) Its HY/IG issuance-window read surfaces on **ipo.html**, not on a credit page — so a future "dedicated HY/IG
  page" child must not duplicate it.
- (c) This trace's module table is dated and will need one line added when #6904 merges.

This section is why the record does not ship stale.

## §6 The bounded build child now scopable

MO-DELTA-008 and MO-DELTA-013 are now scopable as ONE surface question, not two build orders: given that aggregate
HY/IG gauges already ship on bonds.html (§0) and that #6904 puts an HY/IG issuance-window read on ipo.html (§5), the
open question is whether a dedicated credit page is warranted at all, or whether the credit axis belongs in F00's
unified dashboard. That surface allocation is the Chairman's F00 unified-dashboard lane, owned by Meta-CEO A. This
packet hands the surface decision to A and scopes nothing.

**MO-DELTA-008 and MO-DELTA-013 are NOT closed by this packet. Their acceptance tests (an aggregate HY/IG panel; a
dedicated HY/IG dashboard page) are undischarged. Status: read pass done, build child now scopable.**

MO-PAID-004: binding trace discharged, vendor-rights record not discharged (§3).

## §7 What this pass could not verify (printed nulls, plain words)

- Vendor licences (§3).
- Whether market_drivers credit_stress reaches any credit-labelled surface — it does not (§1).
- Whether #6904 merges as inspected (§5).
- Runtime artifact presence (data/, site/) was not inspected because those trees are omitted in sparse worktrees, so
  this trace makes no claim that any artifact currently exists on disk — only that the named writer writes it at the
  named line.
