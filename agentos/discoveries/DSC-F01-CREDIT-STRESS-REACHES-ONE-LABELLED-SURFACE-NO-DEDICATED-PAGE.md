---
key: F01-CREDIT-STRESS-REACHES-ONE-LABELLED-SURFACE-NO-DEDICATED-PAGE
claim: >
  The F01 credit plane is not single-issuer-only: templates/bonds.html.j2:707-726 already
  renders four AGGREGATE spread gauges (ig_oas / hy_oas / quality_spread / ccc_bb) built at
  scripts/build_bonds.py:748 from engine/credit_momentum.py:1951-1956, whose HY/IG series load
  from ICE BofA BAMLH0A0HYM2 / BAMLC0A0CM at :1596-1597. Single-issuer is true only of the ORCL
  watch chip at templates/bonds.html.j2:775-782. Separately, the credit_stress AXIS reaches
  exactly one credit-labelled consumer surface today: templates/dashboard.html.j2:14029
  (`'E4_credit_stress': {'en':'Credit stress','zh':'信用压力'},`) and its bilingual blurb at
  templates/dashboard.html.j2:101-102, driven by engine/rates_inflation_command.py:557-575
  (`# E4 — credit_stress (weight 1)`, `hy_oas_z = _safe_get(tx, "breakeven_decomp", "costate",
  "hy_oas_z")`, `"key": "E4_credit_stress"`). `build_board()` (called at
  scripts/build_rates_command.py:129) only writes the artifact `data/rates_command/latest.json`;
  it renders nothing itself — the dashboard page is rendered by scripts/build_site.py:6802 after
  loading that artifact at :6077-6079 and placing it in the render context at :6701.
  engine/market_drivers.py's OWN credit_stress family
  (:99-107) still reaches no credit-labelled template under its own name (grep of templates/
  for market_drivers returns zero hits) — that null is unchanged — and engine/bond_cross_asset.py:165
  writes no artifact of its own, persisting only through scripts/build_bonds.py:1572 into
  data/bonds/bond_health.json. The corrected plane-level claim: no *dedicated* credit page
  exists, but the plane is not otherwise dark.
falsifier: >
  Run `grep -n 'cc_vm.gauges' templates/bonds.html.j2` and `grep -n 'hy_oas'
  scripts/build_bonds.py`. If the spread-gauges card or the roster keys disappear (or
  _build_spread_gauges stops reading hy_oas/ig_oas), the aggregate-surface half becomes false.
  Run `grep -n "E4_credit_stress" templates/dashboard.html.j2 engine/rates_inflation_command.py`;
  if that leg or its dashboard label disappears, the one-labelled-surface half becomes false.
  Conversely `grep -rn 'market_drivers' templates/` returning any hit refutes the
  market_drivers-still-dark half.
so_what: >
  A future F01 credit child must not build an aggregate HY/IG panel from scratch — one ships
  on bonds.html — and must not claim the credit_stress axis renders nowhere — E4 already
  renders on the rates/inflation command. The open work is a surface-allocation question
  (dedicated credit page vs relying on F00's unified dashboard's existing E4 chip, owned by
  Meta-CEO A) plus reconciliation with PR #6904's engine/credit_window.py, which lands an
  HY/IG issuance-window read on ipo.html.
kind: architecture
verified_at: 2026-09-06
verified_by: >
  templates/bonds.html.j2:707-726; scripts/build_bonds.py:748;
  engine/credit_momentum.py:1596-1597; templates/dashboard.html.j2:14029,101-102;
  engine/rates_inflation_command.py:557-575; scripts/build_rates_command.py:129;
  scripts/build_site.py:6077-6079,6701,6802;
  gh pr view 6904 --json state,headRefName,title,files
scope: [macro, engine/credit_*, engine/bond_cross_asset.py, engine/market_drivers.py, engine/rates_inflation_command.py, templates/bonds.html.j2, templates/dashboard.html.j2, scripts/build_rates_command.py, scripts/build_site.py, F01]
confidence: verified
---

**Supersedes DSC-F01-CREDIT-PLANE-IS-SINGLE-ISSUER-ONLY.md** (deleted): that key indexed a
refuted PREMISE ("single-issuer-only") under company memory rather than the corrected claim,
and it separately overstated the plane-wide null (it said the credit_stress axis reaches "no
credit-labelled surface at all", which is false once engine/rates_inflation_command.py's
E4_credit_stress leg on templates/dashboard.html.j2 is counted). This record corrects both.

See the full read pass at
`research/market_intelligence_productization/F01_CREDIT_AND_COMMODITY_WIRING_TRACE_2026-09-06.md`
for the complete producer/consumer/surface table (credit and commodity), the vendor-source
identification, and the PR #6904 reconciliation.
