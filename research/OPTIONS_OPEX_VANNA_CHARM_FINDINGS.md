# Options Expiry, Vanna, Charm, and Equity Pricing Findings

Date: 2026-07-06

Research artifact: deep options-cycle study for Neural Web / signal process.

Companion artifacts:
- `scripts/research/options_opex_vanna_charm_study.py`
- `reports/artifacts/options_opex_vanna_charm_results.json`
- `reports/artifacts/options_opex_vanna_charm_summary.md`

## Scope

This study asks how standard options expiration, vanna, charm, gamma, and the monthly options
cycle affect equity prices. The goal is not to create a new ungated score. The goal is to
produce theory and data-driven state variables that can improve Neural Web's read of entry
quality, holdability, stop placement, and post-expiry volatility risk.

Evidence used:
- Literature and institutional mechanics: OCC expiration mechanics, option-expiration week
  return studies, pinning studies, option-price monthly-cycle studies, retail option hedging
  pressure, and option-market-maker hedging/liquidity papers.
- Long calendar price study: 5,335 OPEX event rows across SPY/QQQ/IWM/DIA, sector SPDRs,
  and liquid industry ETFs from local Yahoo daily history.
- ThetaData contract study: 363,317 root-days across 171 roots from 2017-01-04 to 2026-07-02,
  using OI-shifted contract-level greeks and OI.
- Robustness: HAC t-stats with horizon-aware lags, era splits, BH-FDR at 10%, placebo
  calendar weeks, non-OPEX controls, and an ETF/index/sector-only robustness slice.

## First-Principles Model

Dealer hedging pressure can be written as a delta-change equation:

```text
dealer hedge demand ~= -[Gamma * dS + Vanna * dIV + Charm * dt + inventory_delta_change]
```

This gives four mechanisms:

1. Gamma: spot movement changes option delta. If dealers are effectively short gamma, hedging
   chases price and can amplify realized volatility. If effectively long gamma, hedging leans
   against price and can pin/suppress movement.
2. Vanna: implied-vol changes alter option delta. When IV falls, vanna can create a mechanical
   hedge adjustment that often looks like a volatility-compression or relief-flow state.
3. Charm: time passing changes option delta. Near expiry, delta can decay quickly even if spot
   and IV do not move. Charm is therefore the "clock pressure" in the options cycle.
4. Expiry: monthly OPEX removes/rolls a large part of near-dated open interest. The market can
   move from a hedging-dominated microstructure into a cleaner supply/demand state after expiry.

The central modeling lesson: total option exposure and front-expiry concentration are different
objects. Large total gamma/vanna/charm often means a liquid, deep, lower-volatility options
ecosystem. Large front-week concentration means the current equity price is more exposed to
expiry-clock mechanics.

## Pass 1: Theory And Literature

The literature supports the existence of options-cycle effects, but warns against treating
calendar OPEX alone as alpha. OCC states that monthly equity options expire on the third Friday
of the expiration month. Stivers and Sun find higher S&P 100 returns in option-expiration weeks
and modest underperformance in fourth-Friday weeks, with delta-hedge rebalancing and falling
implied risk as likely contributors. Ni, Pearson, and Poteshman find expiration-day clustering
near strikes, consistent with hedging and manipulation/incentive effects. Gao, He, and Hu show
a monthly IV cycle around third-Friday expiration, driven by rollover demand and intermediation
frictions. Recent work on retail option pressure and market-maker hedging/liquidity supports
the idea that hedging flows can affect price, volatility, and liquidity, especially when
intermediary balance sheet is constrained.

Pass-1 assessment: the theory was too calendar-heavy at first. The literature explains why
expiration matters, but the tradable object is not "third Friday good/bad." The tradable object
is the state of the chain going into and coming out of that date.

## Pass 2: Full Local Backtest

I built and ran `scripts/research/options_opex_vanna_charm_study.py`.

Important implementation choices:
- OI is shifted one observation within each contract before use.
- Dealer sign follows the repo's existing long-call / short-put convention; it is an assumption,
  not observed dealer inventory.
- GEX, vanna, and charm are OI-weighted at the contract level.
- Cross-sectional tests collapse to one daily Spearman IC, then use HAC t-stats.
- State tests collapse to one daily condition-vs-baseline spread, then use HAC t-stats.
- Multiple tests are controlled with BH-FDR at 10%.

Pass-2 assessment: the first run exposed a bug in OPEX tag alignment inside the Greek panel.
The non-OPEX Greek IC results were still useful, but OPEX interaction tests were not. I fixed
the tag join, reran the full 171-root study, and used only the corrected output below.

## Pass 3: Additional Checks

The corrected full run added usable OPEX-specific states. I also ran an ETF/index/sector-only
robustness slice across 20 broad roots. That slice confirmed the core compression findings
and showed that index/ETF OPEX behavior differs from the all-root universe:
- In the full 171-root panel, modern OPEX front-charm loading predicts higher future 5d
  absolute movement and realized vol.
- In the ETF-only slice, long-gamma plus high charm in OPEX behaves more like a pin/suppression
  state across eras.

Pass-3 assessment: this split is important. Single names and index ETFs should not share one
dealer-positioning interpretation. Neural Web should carry root-class labels before trusting
any OPEX/charm state.

## Findings

F-01. Raw monthly OPEX calendar is weak in modern data. The only calendar-only event that
survived BH-FDR was quad-expiration-week excess return in 2005-2016: +0.5675%, t=4.41,
adj-p=0.00114. Full OPEX-week and post-OPEX effects did not survive in the 2023-2026 era.

F-02. The options cycle is state-dependent, not date-dependent. The third Friday matters
because of what expires and rolls, not because the calendar date alone has stable direction.

F-03. Signed charm pressure is one of the strongest cross-sectional volatility predictors.
It ranked future 5d absolute move and realized vol positively in all eras. For realized vol:
Era1 IC=0.050, Era2 IC=0.102, Era3 IC=0.142; all survived BH-FDR.

F-04. Aggregate charm intensity is negatively related to future realized vol. This looks
counterintuitive until separated from concentration: high total charm often belongs to large,
liquid, heavily optioned names that have lower realized vol.

F-05. Front-week charm concentration is the cleanest expiry-clock feature. It ranked future
5d absolute move and realized vol positively in all eras, and the effect grew in the modern
era. For realized vol: Era1 IC=0.147, Era2 IC=0.241, Era3 IC=0.335.

F-06. Modern OPEX front-charm loading is a real volatility-warning state in the full universe.
In 2023-2026, `opex_front_charm_loaded` produced +2.36 percentage points of extra 5d absolute
move and +19.61 percentage points of annualized 5d realized vol versus baseline; both survived.

F-07. Vanna is mostly a volatility-compression/relief variable, not a directional equity-return
signal. The `vanna_relief_buy_pressure` state reduced 5d realized vol in all three eras:
- Era1: -2.42 percentage points annualized.
- Era2: -4.26 percentage points annualized.
- Era3: -3.83 percentage points annualized.

F-08. Vanna relief also reduced 5d absolute movement in Era1, Era2, and Era3, but did not
produce a robust relative-return edge. This is a holdability/risk-state feature, not an
entry-originating alpha.

F-09. Vanna intensity was negatively related to future 5d realized vol in every era
(Era1 IC=-0.226, Era2 IC=-0.221, Era3 IC=-0.210). This again says total options depth
is often stabilizing.

F-10. Front-week gamma concentration behaves like front-week charm concentration: it ranked
future 5d realized vol positively in all eras (Era1 IC=0.109, Era2 IC=0.196, Era3 IC=0.303).
Near-expiry concentration is the danger; total exposure is often the cushion.

F-11. Gamma intensity by itself ranked future realized vol negatively in all eras
(Era1 IC=-0.213, Era2 IC=-0.202, Era3 IC=-0.170). This supports the repo doctrine that
GEX is context/barrier/vol regime, not a simple directional signal.

F-12. Put/call OI ratio is not a simple fear gauge. It ranked future absolute move/realized
vol negatively in most full-universe tests. That likely reflects hedged/liquid root type and
mature options ecology more than bullish/bearish information.

F-13. Post-OPEX prior gamma loading is a modern vol-release state. In 2023-2026, when the
prior expiry had high front-week gamma loading, post-OPEX realized vol was +5.71 percentage
points annualized higher than baseline.

F-14. Quad OPEX high-charm states are not one-directional. In the full universe, quad/high-charm
states showed lower realized vol in Era1, relative underperformance in Era2/Era3, and mixed
absolute-move behavior. This should be a special "institutional rebalance/roll" state, not
a buy/sell rule.

F-15. The simple "long gamma + high charm + OPEX = pin" rule did not survive in the full
single-name-heavy universe. It became meaningful in the ETF-only robustness slice, where
long-gamma/high-charm OPEX reduced realized vol or absolute move across eras.

F-16. The simple "short gamma + high charm + OPEX = air pocket" rule is also not stable in
the full universe. In 2023-2026, it actually showed lower realized vol in the full panel. In
the ETF-only slice, it showed higher vol in earlier eras. Dealer sign and root class matter.

F-17. Index/ETF roots and single names need different passports. The ETF-only slice confirmed
many Greek effects but changed OPEX state signs. Neural Web should not pool index ETFs, sector
ETFs, and single-name roots without a root-class feature.

F-18. The 2023-2026 era strengthened front-week concentration effects. Both front-week charm
and front-week gamma concentration had much larger ICs versus realized vol in Era3 than Era1.
This is consistent with shorter-dated options and more frequent expiry ecosystems becoming
more important.

F-19. Calendar placebo weeks did not explain the strongest OPEX findings. The calendar-only
placebo prior week did not survive BH-FDR. The important effects came from chain state plus
calendar phase.

F-20. Non-OPEX long-gamma/high-charm placebo states can still suppress vol, especially in
ETF roots. This means charm is not purely an OPEX phenomenon; OPEX is where the clock becomes
concentrated and operationally actionable.

F-21. Directional return findings were much weaker than volatility/absolute-move findings.
Most strong survivors target realized vol or absolute move, not relative return. This should
feed stop/holdability/de-escalation logic before it feeds alpha.

F-22. Vanna and charm should enter Neural Web as "path-shape" features: pin, release,
compression, air-pocket risk, stop-width, and wait-through-expiry. They should not originate
standalone long entries.

F-23. The strongest buildable feature family is `front_expiry_pressure`: front7 charm share,
front7 gamma share, signed charm pressure, and OPEX phase.

F-24. The second strongest buildable feature family is `vanna_relief_state`: estimated vanna
hedge pressure after 1d/5d IV moves. It should modify expected realized vol and holdability.

F-25. The third buildable feature family is `post_opex_release_state`: post-OPEX days after
a loaded expiration. It should warn that realized vol may re-expand after the pin/roll clears.

F-26. The fourth buildable family is `quad_roll_state`: quarterly OPEX plus high charm/gamma.
It should be labeled as special institutional-flow context with mixed sign.

F-27. The model should store both "total Greek intensity" and "front-expiry concentration."
Using only total GEX/vanna/charm would invert important effects.

F-28. The model should expose root-class caveats: index ETF, sector ETF, single name, index
option, and high-retail-call single name likely have different dealer sign reliability.

F-29. The strongest immediate action is not scoring. It is display/shadow stamping of existing
fires with OPEX/vanna/charm state, then grading those states against existing entry ledger
primitives.

F-30. Promotion criteria should be path-based: lower stop-out, cleaner liftoff, improved MFE,
or better realized-vol forecast. Directional returns alone are the wrong first yardstick.

## Proposed Neural Web Integration

Add a raw display/shadow state table or extend `options_entry_state` with:
- `opex_phase`, `td_to_opex`, `td_since_opex`, `is_quad_cycle`.
- `front7_charm_share`, `front7_gex_share`, `front30_charm_share`, `front30_gex_share`.
- `signed_charm_pressure`, `charm_intensity`.
- `signed_vanna_pressure`, `vanna_hedge_pressure_1d`, `vanna_hedge_pressure_5d`.
- `post_opex_prior_gamma_loaded`.
- `root_class` and `dealer_sign_reliability`.

Register shadow buckets:
- `S-FRONT-CHARM`: OPEX week + front7 charm share high.
- `S-VANNA-RELIEF`: IV falling + vanna hedge pressure positive.
- `S-POST-OPEX-RELEASE`: post-OPEX + prior front7 gamma loading high.
- `S-QUAD-ROLL`: quad OPEX + high charm/gamma.
- `S-INDEX-PIN`: index/ETF only, OPEX + long gamma + high charm.

Every bucket should remain display/shadow until it earns authority through the existing
entry ledger. The first approved use should be caution/de-escalation and expected path shape,
not positive score origination.

## Sources

- OCC, equity options specifications: https://www.theocc.com/clearance-and-settlement/clearing/equity-options-product-specifications
- Stivers and Sun, "Returns and Option Activity over the Option-Expiration Week for S&P 100 Stocks": https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1571786
- Ni, Pearson, and Poteshman, "Stock Price Clustering on Option Expiration Dates": https://papers.ssrn.com/sol3/papers.cfm?abstract_id=519044
- Pearson, Poteshman, and White, "Does Option Trading Impact Underlying Stock Prices": https://www.ou.edu/dam/price/Finance/CFS/paper/pdf/pearsonPoteshmanWhite.pdf
- Gao, He, and Hu, "The Monthly Cycle of Option Prices": https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4637020
- Flynn, "Charming! Retail Option Volume, Delta Hedging, and the Impact on Stock Prices": https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5054370
- O'Donovan, Yu, and Zhang, "Option Market Maker Hedging and Stock Market Liquidity": https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4567604
- Egebjerg and Kokholm, "A Model for the Hedging Impact of Option Market Makers": https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4936978
