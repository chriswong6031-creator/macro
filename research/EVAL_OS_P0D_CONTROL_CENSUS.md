# Eval OS P0d — Phase D0: the matched-control census

**Authored** 2026-08-14 · **Workstream** WS:EVAL-OS-MEASUREMENT-LAW (wave 5, the control-leg
decision) · **Companion** `PREREG_P0D_MATCHED_CONTROL_CONTRACT.md` (the contract this census
grounds), `EVAL_OS_SITREP_2026-08-14.md` §7.1/§11 (the finding and the decision request),
`agentos/discoveries/DSC-NO-QLEDGER-CLAIM-EVER-CARRIED-A-CONTROL-LEG.md`.

**CEO ruling being executed (P0d):** benchmark evidence is the universal baseline;
matched-control evidence is a stricter second evidence basis *where a defensible matched
counterfactual exists*. No family is forced to invent a control; no family may claim
matched-control evaluation without prospectively accrued, control-carrying claims.

---

## 0. How this census was derived (recompute, never pin)

Every count below is **nightly-moving** and was measured on `origin/main` at
`91c3c64afff` (2026-08-14). The invariant is the *finding*, not the number. Recompute:

```
python3 - <<'EOF'
import json
from collections import Counter, defaultdict
claims = [json.loads(l) for l in open('data/qledger/claims.jsonl', encoding='utf-8')
          if l.strip() and not l.startswith('#')]
print(len(claims), 'claims;',
      sum(1 for c in claims if c.get('control')), 'with a control leg')
EOF
```

At measurement: **46,695 claims, 0 with a `control`; 59,929 grade rows, 0 with a
non-null `control_ret`; all 59,929 carry `bench_ret`.** (The DSC's zero-control finding
re-verified on today's store; counts grew from the 46,630/59,929 in the sitrep, the zeros
did not move.)

## 1. Every live claim family, derived from the store

Live corpus by `claim_family` (placebo rows excluded from the live columns; `dir` is
direction mix −1/0/+1; `unit` is the declared horizon-unit mix; `sector%` = share of rows
carrying a `sector` stamp; `ctrl` = rows with a control leg):

| family | rows | dir −1/0/+1 | scope | bench | horizons | unit | sector% | ctrl | last asof |
|---|---|---|---|---|---|---|---|---|---|
| altdata (legacy) | 169 | 0/0/169 | entity | SPY | 63 | LEGACY | 0 | 0 | 2026-07-11 |
| altdata_event | 102 | 0/0/102 | entity | SPY | 21 | LEGACY | 0 | 0 | 2026-08-09 |
| altdata_flow | 48 | 0/0/48 | entity | SPY | 21 | LEGACY | 0 | 0 | 2026-08-07 |
| altdata_mid | 46 | 0/0/46 | entity | SPY | 63 | LEGACY | 0 | 0 | 2026-08-07 |
| altdata_slow | 103 | 0/0/103 | entity | SPY | 63 | LEGACY | 0 | 0 | 2026-08-09 |
| basket_turn.v1 | 2 | 0/0/2 | basket | SPY | 21 | mixed | 0 | 0 | 2026-08-13 |
| china_news | 812 | 0/812/0 | entity | 510300.SS | 5,21 | LEGACY | 0 | 0 | 2026-07-02 |
| cn_importance_v0(_pit) | 2×2,422 | all 0 | entity | 510300.SS | 5,21 | LEGACY | 0 | 0 | 2026-08-12 |
| cn_special_sits | 70 | 0/70/0 | entity | 510300.SS | 21 | LEGACY | 0 | 0 | 2026-08-12 |
| intel_hub | 2,562 | 838/132/1,592 | entity | SPY | 5,21 | LEGACY + trading_days | 18 | 0 | 2026-08-14 |
| narrative_flare_state | 2 | 0/2/0 | entity | SPY | 21,63 | trading_days | 0 | 0 | 2026-08-13 |
| narrative_source_call | 331 | 0/331/0 | entity | SPY | 26–28 | LEGACY | 0 | 0 | 2026-08-09 |
| policy | 34 | 4/9/21 | entity | SPY | 42–126 | LEGACY | 0 | 0 | 2026-08-09 |
| radar | 9,482 | 5,626/175/3,681 | entity+basket | SPY | 63 | LEGACY | 0 | 0 | 2026-08-07 |
| us_importance_v0(_pit) | 2×13,528 | all 0 | entity | SPY | 5,21 | LEGACY | 0 | 0 | 2026-08-10 |
| whitehouse | 92 | 46/0/46 | entity+macro | SPY | 3–7 | LEGACY | 0 | 0 | 2026-08-12 |
| placebo (+ per-family placebo twins) | 342 + 598 | — | — | — | — | — | — | — | — |

Registered families with **zero rows to date** (producers exist, forward logs not yet
started or refusing): `flip_confirmation.v1`, `communique_diff`, `missing_tape`,
`extraction_8k`, plus the qual_ladder-declared families with no adapter yet. The three P3
families (`stock_desk`, `thematic_desk`, `demand_chain`) have zero rows **by design** —
forward-only registration ships in #5577 and every historical desk row correctly refuses
(sitrep §9).

Producer map (derived from the registrars): `scripts/backfill_qledger_us.py` → altdata\*,
radar, policy (nightly, `daily.yml`); `scripts/backfill_qledger_intel_hub.py` → intel_hub
(nightly, `collect.py`); `scripts/build_whitehouse.py` → whitehouse;
`scripts/shadow_importance_v0*.py` → \*_importance_v0\*; `engine/china_special_situations.py`
→ cn_special_sits; `engine/source_registry.py` → narrative\*; `engine/basket_turn_cohort.py`
→ basket_turn.v1; `engine/flip_confirmation.py` → flip_confirmation.v1;
`engine/communique_diff.py`, `engine/missing_tape.py`, `collectors/special_situations.py` →
their namesakes; `engine/qledger_desk_adapter.py` (#5577) → stock_desk, thematic_desk,
demand_chain; `scripts/sample_qledger_placebo.py` → placebo.

## 2. Three defects found by this census (all silent, all in the control path)

**D0-1 — intel_hub's control wiring has been dead since it shipped.**
`scripts/backfill_qledger_intel_hub.py` already passes
`control=control_for_sector(sector)` — the one producer that ever tried. But the hub's
`sectors` field holds **ETF tickers** (QQQ 176, XLV 38, XLK 36, SMH 28, ITA 28, CIBR,
JETS, IBIT…), and `control_for_sector` is a *GICS-name*→ETF map, so every lookup returned
None and every claim registered uncontrolled. The producer had the control answer in hand
— often more specific than GICS (SMH, ITA, JETS) — and lost it in a vocabulary mismatch.
A null control is a legal state, so nothing alarmed, ever.

**D0-2 — the canonical universe file speaks two sector vocabularies.**
`data/universe/membership.parquet` (the only broad ticker→sector source in the repo) mixes
GICS names ("Information Technology", "Health Care", "Financials") with Yahoo-style names
("Technology", "Healthcare", "Financial", "Consumer Cyclical", "Basic Materials",
"Consumer Defensive"). A naive join through `control_for_sector` silently nulls on roughly
half the universe — D0-1's defect class, one file over. Any control construction that
reads this file MUST normalise the alias set explicitly and count what it refuses.

**D0-3 — the production gate projects a controlled subset onto the full cohort's N.**
`promotion_check(control_only=True)` computes the control-only hit *rate* over rows that
carry control legs, then projects it onto `n_dates` counted over the **whole family**
(`cluster_hits = round(hits/graded_hits * n_dates)`). With partial coverage this states a
Wilson interval at full-cohort N for a rate measured on the controlled subset — the exact
denominator-integrity failure P0d's D4 forbids ("n=37 reported as though the whole
cohort"). Latent today only because coverage is exactly zero everywhere (`ci_low=None`).

## 3. Per-family control feasibility (measured, not asserted)

The two questions the CEO's contract turns on: is a stable matched counterfactual
**economically meaningful**, and is it **choosable at registration time with no future
information** from an existing canonical source?

| family | counterfactual meaningful? | constructible at registration? | measured coverage |
|---|---|---|---|
| stock_desk (P3) | **yes** — single-stock 20td calls; sector ETF isolates name-vs-sector skill | **yes** — picks carry `identity.sector` from `site/stockdata/*.json`, which validates against `GICS_SECTORS` (`build_stock_library.py` drops non-GICS rows); #5577 already threads `sector_of` | **95%** of 102 historical subjects GICS-mappable (unmappable: BIDU, GPCR, NET, SGML, VALE — ADR/off-index tail) |
| demand_chain (P3) | **yes** — single-stock 126td rel-return calls on chain names | **yes** — membership.parquet + alias normalisation (D0-2) | **100%** of 50 historical subjects |
| thematic_desk (P3) | **no** — the subject IS the theme's proxy ETF; a sector control nets the claim against itself | — | **0%** of 31 subjects sector-mappable (159928.SZ, 3033.HK, GDX, CIBR, IBIT…) — empirical confirmation of the economic reading |
| intel_hub | partially — per-name stage/lean calls vs the hub's own declared peer basket would be meaningful | only 72%: own `sectors[0]` proxy 24% of Aug flow + membership fallback 48%; **28% unresolvable** (NVS, RHHBY ADRs; MSTR, RKLB, HTGC, BRK.B off-index) | **72%** — below any honest coverage bar; see §5 re-class path |
| altdata_event/flow/mid/slow | yes in principle (name-specific event/flow calls) — note these families already carry a **matched placebo twin tape** (2 per claim), a different and live control design | 89% via membership+alias; ADR/foreign tail (BABA, AZN, BEKE) unresolvable | **89%** of 240 distinct tickers |
| radar | **no for basket-scope** (5,626+ rows): `scope_key` is itself a basket/theme proxy — control self-cancels; entity-scope rows carry no sector metadata and the family mixes both scopes | no registration-time source wired | — |
| policy | **no** — subjects are the policy theme's OWN proxy ETFs (ITA, GLD, BIL); the theme bet is the claim | — | — |
| whitehouse | mixed — entity rows could in principle sector-match; the family also holds macro-scope rows, runs 3–7d on the legacy clock, N=92 | no sector source wired | — |
| basket_turn.v1 / flip_confirmation.v1 | **no** — basket-cohort constructs; no per-name counterfactual | — | — |
| all direction=0 families | **not applicable** — salience/descriptive species have no directional skill proposition; they grade magnitude against the placebo tape (standards §4.2) | — | — |

## 4. The classification (Phase D0 output; contract in the prereg)

Three semantic states, exactly the CEO's:

- **`matched_control_required`** — `stock_desk`, `demand_chain`.
  The only families where the counterfactual is both economically defensible and
  constructible ≥95% from existing canonical sources at registration. Both are
  prospective-only families (#5577's forward gate), so their matched-control record is
  born clean: no historical rows exist to be tempted by.
- **`benchmark_only`** — `intel_hub`, `altdata`, `altdata_event`, `altdata_flow`,
  `altdata_mid`, `altdata_slow`, `radar`, `policy`, `whitehouse`, `thematic_desk`,
  `basket_turn.v1`, `flip_confirmation.v1`.
  Legitimate benchmark-relative evidence, labelled as such, never marketed as
  matched-control. For radar/policy/thematic_desk this is the *permanently correct*
  economics (self-cancelling control), not a data gap.
- **`not_applicable`** — `china_news`, `cn_importance_v0`, `cn_importance_v0_pit`,
  `us_importance_v0`, `us_importance_v0_pit`, `cn_special_sits`,
  `narrative_source_call`, `narrative_flare_state`, `communique_diff`, `missing_tape`,
  `extraction_8k`, `placebo`.
  Salience/descriptive; no directional matched-control contract can apply. (`placebo`
  is itself the control arm.)

**Default for a family not in the table:** benchmark mechanics with an explicit
`unclassified` label. Matched-control authority is opt-in by a governed table edit only —
never by a control field appearing on rows (adversarial control #7).

**No fourth semantic state was needed** — the census surfaced no family that fails to fit
required / benchmark-only / not-applicable, so no CEO escalation on taxonomy.

## 5. Re-classification paths (governed, named, not implied)

A `benchmark_only` → `matched_control_required` move is a code change to the policy table
plus its pinning test, citing new evidence. The concrete openable paths, recorded so they
are not re-derived:

- **intel_hub** — becomes classifiable when a registration-time sector/peer source covers
  ≥95% of its real flow (today 72%). Options: extend the hub to stamp `sectors` on every
  name it surfaces (its own peer-basket declaration, preferable), or a broader
  ticker→sector collector. Building either is outside P0d (no new control-selection
  engine).
- **altdata_event/flow/mid/slow** — 89% today; the ADR/foreign tail needs a sector
  source. Same condition. Their placebo-twin tape remains their live control design
  meanwhile.
- **radar** — only if the family is first split by scope (entity vs basket); a mixed
  family cannot carry one control policy honestly.
- **whitehouse** — only if entity and macro rows stop sharing one family, and it migrates
  off the legacy clock.

## 6. What this census kills

- Wiring `control_for_sector()` into every producer (the "recommendation (1)" shape in
  sitrep §11) is **refuted by measurement**: for radar, policy and thematic_desk the
  construction is self-cancelling; for intel_hub and altdata it silently under-covers
  (72% / 89%). Universal wiring would have manufactured exactly the ambiguous
  sometimes-controlled state the ruling forbids.
- Any coverage accounting that computes over "rows that have controls" rather than the
  registered prospective cohort (D0-3 is the live instance of this defect class).
