# MARKET ONTOLOGY F01 — Macro & Monetary Suite COMPLETION RECORD (2026-09-04)

Op key: `marketontology-f01-macro-markets-20260826-fable-001`
Schema: `mastermind.market_ontology_completion_record.v1` (records-only; no executable authority)
Status: SUITE COMPLETE — twelve of twelve workspaces live (producer + validated artifact + page), nightly-refreshed.
Authority: Chairman full-autonomy grant (Claude-CEO/Meta-CEO, 2026-09-04, in-chat); architecture `…suite_architecture.v1` (SOL_ARCHITECTURE_FREEZE_FOR_REVIEW) as amended by the Chairman's macro-repo placement override (recorded in `MARKET_ONTOLOGY_F01_MACRO_UI_OVERRIDE_2026-09-04.md`).

## 1. Carrier chain (all merged to macro main, 2026-09-04)

| Carrier | Scope | Squash |
|---|---|---|
| #6829 | Records plane: architecture freeze copy + UI override + census records | `2ac958f2` |
| #6833 | R1A: contract + liquidity_regime producer + machine consumer (adversarial review, F1–F11 fix wave) | `7b59eeff` |
| #6843 | R2: six MCS/cycle producers (growth, inflation, monetary_policy, financial_conditions, business_activity, labor) | `23cf73e9` |
| #6844 | RRP disclosure prose-leak fix + all-7 artifact second prints | `a9d6f9eb` |
| #6836 | R1B: reusable §6.3 suite shell + labels + view model + fail-closed page builder + page 1 | `8e59a413` |
| #6845 | Pages 2–7 (MCS complete) + two pre-existing registry-row heals | `642c34f8` |
| #6846 | R3: liquidity_central_banks producer + page (GLT + cb_desk; WALCL refuse-not-rescale proven live) | `6304e1b4` |
| #6847 | R4+R5: capital_structure + housing producers + pages; suite-wide freshness-law correction | `9304b62a` |
| #6848 | R6: consumer_payments + national_debt producers + pages + `consumer_household` collector appends — 12/12 | `bd55844c` |
| #6849 | R7: nightly artifact lane (build_macro_workspaces before build_site in the engine shell) | `b4968933` |

## 2. Workspace census (real-build states as of 2026-09-04)

| # | workspace id | producer module | tests | real availability | headline |
|---|---|---|---|---|---|
| 1 | liquidity_regime | liquidity_regime.py | 51 | CURRENT | C (easy/weak), PRESENT |
| 2 | growth_real_economy | growth.py | R2 suite | CURRENT | B, PRESENT (+ nowcast DISAGREEMENT) |
| 3 | business_activity | business_activity.py | R2 suite | CURRENT | COMPUTATION_REFUSED (owner publishes only blended composites — permanent, disclosed) |
| 4 | labor_markets | labor.py | R2 suite | CURRENT | B, PRESENT |
| 5 | inflation_system | inflation.py | R2 suite | LATE_WITHIN_TOLERANCE (CPI-lag law — never CURRENT, test-pinned) | A, PRESENT (+ sticky-led contradiction) |
| 6 | monetary_policy | monetary_policy.py | R2 suite | CURRENT | NOT_APPLICABLE (no two-axis blueprint exists) |
| 7 | financial_conditions | financial_conditions.py | R2 suite | CURRENT | B, PRESENT |
| 8 | liquidity_central_banks | liquidity_central_banks.py | 51 | CURRENT | NOT_APPLICABLE; WALCL level leg refuses on the known cb_desk unit mislabel (refuse-not-rescale, live-proven) |
| 9 | capital_structure | capital_structure.py | 53 | CURRENT | COMPUTATION_REFUSED (owner projection cannot fill the blueprint) |
| 10 | housing_real_estate | housing.py | 87 | CURRENT (post freshness-law fix) | COMPUTATION_REFUSED |
| 11 | consumer_payments | consumer_payments.py | 122 | LATE_WITHIN_TOLERANCE (honest UMCSENT verdict) | COMPUTATION_REFUSED — computable blueprint, self-heals as `consumer_household` parquets land |
| 12 | national_debt_liabilities | national_debt.py | 108 | CURRENT ×7 components | COMPUTATION_REFUSED — unconditional (no architecture-named axis pair; debt-stock census gap disclosed, never fabricated) |

Headline null-reason law held throughout: NOT_APPLICABLE = no blueprint exists; COMPUTATION_REFUSED = blueprint exists but data cannot fill it.

## 3. The suite-wide freshness law (corrected mid-campaign, R5)

Cadence must equal the WORST-CASE age of the newest print the agency can possibly have published — publication lag at release PLUS one full release interval — measured from the reference-period date each source is stamped with. A shorter cadence mislabels a maximally-fresh source as stale (proven live: the June Case-Shiller print, published late August and the newest possible on Sept 4, read STALE_SOURCE under a naive 62d law; the construction series would have flipped false-STALE one day later). Applied across housing (construction 80d, Case-Shiller 124d, ZORI 50d), consumer (UMCSENT 61d — hand-corrected DOWN by the composer so a superseded July print honestly reads LATE), national debt (DTS 5d, auctions 10d, BIS 260d — the 2025Q4 print at age 247d correctly CURRENT, attribution-only).

## 4. Parity ledger vs the reference product (marketontology.com, §17.3 extraction 2026-09-04)

- Reference has **14** workspaces; ours is the architecture's closed **12**. The two extras: **Rates & Curves** and **Trade Flows** — both named as beyond-F01 expansion candidates, neither in the F01 closed set.
- Reference "Structure" = global wealth composition, NOT corporate capital structure; our capital_structure (§10.3) is deliberately a different, owner-projected surface — parity here is by design NOT sought.
- Their Debt page is thinner than our §10.12 spec; ours exceeds it on flows (DTS daily, auction demand, BIS DSR/gap) while disclosing the stock gap they also do not fill with primary data.
- Shared grammar parity (causal ribbon → dated KPI band → chart stack with clocks → MoM heatmap): our §6.3 shell covers context header, ribbon, headline band, quadrant map, diagnostics, what-changed, metrics, drivers, lineage, withheld, evidence drawer. Honest-degradation display parity confirmed (they show "—"/DISCONTINUED; we render typed refusals).
- Divergence noted at R1A and standing: same-day regime quadrant C (ours) vs B (theirs) — lawful composition difference (no narrow SOFR-EFFR gauge in ours; NFCI/OFR-FSI/HY-OAS percentiles), sign/direction hand-verified.

## 5. R7 rulings (bounded scope — decisions, with reasons)

- **Alerts tabs: OMITTED** until a real alert service exists (architecture's own gate). The contract carries declared-not-executable alert blocks; no fake tab ships.
- **Analyst seam: DEFERRED** to the existing W-AI lobe integration decision — not fabricated as a static widget.
- **Scenario engine: DEFERRED** — census found scenario engines absent in all source domains; a client-side scenario toy over honest-null artifacts would violate the falsifiability doctrine. Declared-not-executable contract blocks stand.
- **Nightly refresh: SHIPPED** (#6849) — the one R7 item that was operational truth rather than new surface: artifacts now rebuild in the engine lane before build_site, so pages are same-night.

## 6. Operational notes & standing follow-ups

- **Pack starvation waiver posture** (all merges): runner fleet degraded (5/8 offline at campaign start); every carrier merged on fast-gates-all-green + full local receipts (battery, contract-delta 0/0, ci_pack 117) + documented waiver comment. `ci-authority/codex/merge-queue-pilot` red = known non-gating flake. Operator: restoring the fleet re-arms the full hosted battery.
- **Pre-existing red** (outside F01): `test_render_builder_ownership.py::test_direct_and_transitive_render_dependencies_are_owned` — render.yml push filter misses `build_risk_envelope`. Tracked as a follow-up chip; reproduces on origin/main.
- **cb_desk WALCL unit mislabel** (owner-side): tracked as a follow-up chip; the LCB workspace refuses rather than rescales until the owner heals it.
- **consumer_household parquets**: land on the next nightly keyed collect; consumer_payments self-heals (its credit-stress axis and 7 metrics flip from typed absence to PRESENT with zero code change).
- **Debt-stock collectors** (Debt-to-the-Penny/MTS/TIC/MSPD): the census-named gap; a future collector wave unblinds 11 NOT_COVERED metrics in national_debt.
- **First accepted second print**: series blocks / 1M vectors / changes upgrade as publication history accrues (R1A law) — now automatic via the nightly lane.

## 7. Beyond-F01 expansion candidates (Chairman-authorized, next)

Trade-Flows workspace; Rates & Curves workspace (both reach reference-product 14/14 parity); F13 cheap projections; the F04 Explorer lane (held on the F00 receiver ruling).
