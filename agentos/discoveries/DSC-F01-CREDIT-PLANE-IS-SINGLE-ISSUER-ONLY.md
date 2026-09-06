---
key: F01-CREDIT-PLANE-IS-SINGLE-ISSUER-ONLY
claim: >
  Refuted as stated: the F01 credit plane is NOT single-issuer-only.
  templates/bonds.html.j2:707-726 already renders four AGGREGATE spread gauges
  (ig_oas / hy_oas / quality_spread / ccc_bb) built at scripts/build_bonds.py:748 from
  engine/credit_momentum.py:1951-1956, whose HY/IG series load from ICE BofA
  BAMLH0A0HYM2 / BAMLC0A0CM at :1596-1597. Single-issuer is true only of the ORCL watch
  chip at templates/bonds.html.j2:775-782. Separately, engine/market_drivers.py's
  credit_stress family (:99-107) reaches NO credit-labelled template — grep of
  templates/ for market_drivers returns zero hits — and engine/bond_cross_asset.py:165
  writes no artifact of its own, persisting only through scripts/build_bonds.py:1572
  into data/bonds/bond_health.json.
falsifier: >
  Run `grep -n 'cc_vm.gauges' templates/bonds.html.j2` and `grep -n 'hy_oas'
  scripts/build_bonds.py`. If the spread-gauges card or the roster keys disappear (or
  _build_spread_gauges stops reading hy_oas/ig_oas), the aggregate surface is gone and
  the single-issuer claim becomes true as stated. Conversely `grep -rn 'market_drivers'
  templates/` returning any hit refutes the no-credit-surface half.
so_what: >
  A future F01 credit child must not build an aggregate HY/IG panel from scratch — one
  ships. The open work is a surface-allocation question (dedicated credit page vs F00's
  unified dashboard, owned by Meta-CEO A) plus reconciliation with PR #6904's
  engine/credit_window.py, which lands an HY/IG issuance-window read on ipo.html.
kind: architecture
verified_at: 2026-09-06
verified_by: >
  templates/bonds.html.j2:707-726, scripts/build_bonds.py:748,
  engine/credit_momentum.py:1596-1597, and `gh pr view 6904 --json
  state,headRefName,title,files -R mastermindx-market-intelligence/macro` (confirmed
  OPEN, engine/credit_window.py absent on main at time of read).
scope: [macro, "engine/credit_*", engine/bond_cross_asset.py, engine/market_drivers.py, templates/bonds.html.j2, F01]
confidence: verified
---

Full trace: research/market_intelligence_productization/F01_CREDIT_AND_COMMODITY_WIRING_TRACE_2026-09-06.md
