# Owner And Reuse Matrix

## Rule

K3E composes over owner-native truth. If a needed input already has a canonical
owner, K3E reads it or routes a bounded owner-lane wave. It does not fork it.

`K3E-0` is the Expectation Market Dynamics freeze label. Canonical `K3-E`
remains the Opportunity Evidence Vector contract; same-name convenience never
grants replacement authority.

| concern | canonical owner / lane | K3E reuse rule | forbidden duplicate |
|---|---|---|---|
| analyst expectation observations | `collectors/equity_revisions.py` in the existing revisions owner lane | `SRC-A1` adds the named additive raw artifacts under `data/revisions/`; K3E consumes later | third generic analyst-history store |
| price targets / recommendation snapshots | `collectors/yf_analyst.py` | remains its price-target/rating lane; it is not the raw prospective EPS/revenue owner | diverting EPS/revenue expectation accrual into `yf_analyst.py` |
| common `ExpectationBaseline` semantics | MAS-119 | wait for MAS-119 for shared cross-domain envelope | universal K3E expectation schema |
| family-specific incorporation science | MAS-118 | consume later as separate object where accepted | universal `gap_score` or family rewrite |
| earnings event facts / clocks | WS:EARNINGS-INTELLIGENCE-OS and WS:EARNINGS-EVENT-INTELLIGENCE-COMPILER | read canonical event and Q&A objects | second earnings event store |
| financial statement / revision semantics | WS:FINANCIAL-INTELLIGENCE-FABRIC | reuse FIF packet / query / revision objects | second financial semantic model |
| price residuals / market decomposition | existing DRL / residual-alpha owners | import residual outputs where lawful | new residual engine |
| options-implied uncertainty | existing options owners | read existing options outputs with honest coverage | duplicate options plane |
| issuer-security identity | existing identity owners | reuse current identity contracts only | new identity plane |
| product security projection | WS:MARKET-OS | downstream composition only | new product truth object |
| OpportunityCase synthesis | WS:ALPHA-INTELLIGENCE-INTEGRATION K5 | future episodic synthesis only after K5 | one truth object per projection |

## Additional owner laws

1. `security_state.v1` and future K3E outputs are not substitutes for one
   another. `security_state.v1` is the compact universal security projection;
   K3E is a descriptive expectation/market dynamics family.
2. `OpportunityCase` is a future K5 synthesis identity, not a replacement for
   compact K3E emissions.
3. Market OS may consume K3E outputs later, but K3E does not own product
   execution or private-user state.
4. K3E may not become a workaround around `DNR:KILL-FUSED-COMPOSITE` or
   `DNR:KILL-LIQUIDITY-SHOCK-REVERSAL-CLASSIFIER`.

## SRC-A1 physical-owner amendment (K3E-0R)

The source owner is not a choice left to the builder:

- `collectors/equity_revisions.py` owns prospective EPS/revenue observation
  collection. `collectors/yf_analyst.py` continues to own price-target and rating
  snapshots only.
- The additive physical owner is `data/revisions/`. Its canonical SRC-A1
  artifacts are `expectation_observations.parquet` and
  `expectation_attempts.parquet`.
- `latest.parquet`, `history.parquet`, and `engine/theme_revisions.py` retain
  their current revision-breadth/live-score semantics. SRC-A1 neither renames,
  rewrites, nor makes them its historical source of truth.
- The two additive parquet artifacts are source-owner records, not a K3E store,
  `ExpectationBaseline`, ranker, identity plane, residual plane, event plane,
  lifecycle plane, evaluation plane, or publication plane.
