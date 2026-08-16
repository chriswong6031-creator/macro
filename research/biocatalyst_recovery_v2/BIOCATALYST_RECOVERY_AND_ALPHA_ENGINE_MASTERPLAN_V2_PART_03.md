1. **No new product feature until the current hydration incident is classified and fixed.**
2. **No new source, model, contract family, or architecture document during P0 unless the incident itself requires it.**
3. If the root cause is not identified after the first focused diagnostic block, stop coding and produce an evidence table of each layer/status instead of beginning a refactor.
4. If the API returns valid 200 JSON and only the client validator fails, fix exactly that contract mismatch. Do not redesign the workbench in the same PR.
5. If the API returns 503 because the current generation is invalid, do not edit evidence files in place and do not widen source policy.
6. If auth is the failure, do not make the private API public and do not bypass `site_full`.
7. Do not touch `theme.js` merely because auth exists there. It is a shared estate asset. Prove a shared-runtime defect first.
8. Do not count a static page 200, a unit test, a worker success, or a screenshot of chrome as hydration proof.
9. Do not merge a “fix” without a browser showing a real nonzero record from the same deployed bytes.
10. After each rescue PR, verify the changed production surface before starting the next slice.

---

## G. Definition of done for P0 — strengthened

P0 is complete only when all of the following are simultaneously true:

### Identity and deployment

- exact `origin/main`, production checkout, API checkout, served asset hashes, and active generation are recorded;
- no stale deployment ambiguity remains.

### Authentication

- signed-out browser -> explicit locked/sign-in state;
- signed-in unentitled browser -> explicit entitlement state;
- signed-in entitled browser -> bearer observed on private calls;
- auth SDK/bootstrap failure -> auth-specific degraded state, never anonymous silent fallback.

### API

- `/health` 200 for entitled user;
- Milestones 200 with expected nonzero proof rows;
- Trial Screen 200 with expected nonzero proof rows;
- Change Tape 200 with expected historical rows where the proof cohort supports them;
- First-seen returns its true prospective coverage state and any lawful rows;
- Peer Matrix exact cohort invariant passes;
- dossier returns covered trial;
- private headers intact;
- anonymous control remains 401.

### Client

- no generic source-outage copy for a contract mismatch;
- no contract-invalid row is rendered;
- valid zero and system failure are visually distinct;
- no page errors;
- no unexpected console errors;
- refresh, mode switch, back/forward, and dossier open do not lose auth.

### Evidence

- sanitized network summary attached;
- screenshots attached;
- verifier receipt attached;
- request/generation/asset identity attached;
- rollback path identified.

“118 passed,” “1377 passed,” “worker success,” or “page/CSS/JS 200” alone do not satisfy any of the above.

---

## H. Functional-parity build ledger — expanded for future sessions

Once P0 is green, replace the coarse 32-row tally with a user-job ledger that separates **source**, **backend**, **product**, and **investment-intelligence** completion.

Each row should contain these independent stages:

1. benchmark job documented;
2. clean-room source identified;
3. rights/retention/redistribution state decided;
4. PIT identity dependencies available;
5. collector/read-adapter built;
6. historical/backfill strategy defined;
7. current data populated;
8. API/read model served;
9. UI surfaced;
10. browser user journey proven;
11. saved/watch/export action available where applicable;
12. PIT research feature eligible;
13. shadow model registered where applicable;
14. forward outcomes accruing;
15. promoted or explicitly refused.

This prevents “backend exists” from being counted as “feature shipped.”

### H1. Benchmark jobs visible in the supplied BioPharmCatalyst material

Treat these as clean-room **user jobs**, not pages to copy:

| User job | BioCatalyst target | Primary owner/dependency | Priority after P0 |
|---|---|---|---|
| FDA catalyst calendar | Catalyst Radar saved lens | Regulatory source plane | P1 |
| PDUFA calendar | Catalyst Radar saved lens | Regulatory + corporate evidence | P1 |
| Clinical readout calendar | Catalyst Radar | Trial graph + date-confidence engine | P1 |
| Historical catalysts | Event History / study lab | Event graph + market PIT | P1 |
| IPO calendar | Financing lens | Capital/Corporate | P2 |
| Medical-device calendar | MedTech pack | Separate device source pack | P2 |
| Conference calendar | Catalyst/Corporate events | Corporate evidence | P2 |
| Earnings calendar | Company/catalyst lens | Existing earnings plane | P1 |
| Foreign approvals | Regulatory dossier | Foreign regulator sources | P2 |
| Drug pipeline DB/screener | Explorer | Asset/indication graph | P1 |
| Med-device pipeline | Explorer/MedTech | Device graph | P2 |
| Company pages | Company Dossier | Company/security PIT identity | P1 |
| Trial Insights | Trial Dossier/Workbench | Existing trial spine + graph | P1 |
| Historical probability of success | Research & Models | Mature PIT outcome cohorts | P3 |
| Cash database | Company Dossier/Explorer | Capital Structure PIT | P1 |
| Burn/runway | Financing survival | Capital Structure PIT | P1 |
| Analyst ratings/targets | Expectations lens | Licensed vintage data | P2/licensed |
| Insider trades | Ownership lens | Existing ownership plane | P2 |
| Hedge funds/13F | Ownership lens | Existing 13F plane | P2 |
| M&A | Transactions lens | Corporate + asset graph | P2 |
| Model portfolios | Portfolio product | Terminal/user-state + strategy governance | P3 |
| Catalyst impact table | Event Study | Event graph + market/options PIT | P2 |
| Options data | Catalyst/options lens | Existing options estate | P1 |
| Notifications/alerts | Alerts | Terminal/Supabase tenant state | P1 |
| Historical notifications | Alert history | Tenant event ledger | P2 |
| API access | Data/API | Expand existing Bio API | P1 |
| Biotech stocks dashboard | Market Pulse | Existing market-data plane | P1 |
| Premarket advancers/decliners | Market Pulse | Existing Massive/Polygon | P1 |
| Top gainers/losers | Market Pulse | Existing market-data plane | P1 |
| Unusual volume | Market Pulse | Existing volume/flow estate | P1 |
| Advancer/decliner treemap | Market Pulse | Existing market-data plane | P1 |
| Daily movers scatter | Market Pulse | price + relative volume | P1 |
| XBI/IBB context | Market Pulse | ETF/subsector context | P1 |

### H2. Parity should be built as vertical slices

A useful slice is not “build FDA schemas.” It is:

> source -> temporal event -> company/asset join -> API -> Catalyst Radar row -> source evidence -> alert/watch -> browser proof.

Likewise, “Options Data” is not a raw chain table. It is:

> catalyst -> relevant expiries -> implied move/skew/term structure -> historical realized-vs-implied context -> execution quality -> evidence -> browser.

---

## I. Alpha-lobe implementation details — expanded

### I1. Keep the lobe multidimensional

Do not invent `biocatalyst_score = 87.4` first and explain it later. Store orthogonal member outputs first:

- `event_quality`;
- `event_timing_readiness`;
- `outcome_probability` when calibrated;
- `asset_materiality`;
- `financing_survival`;
- `dilution_overhang`;
- `fundamental_dislocation`;
- `price_residual_dislocation`;
- `options_implied_dislocation`;
- `flow_anticipation`;
- `washout_turn_quality`;
- `subsector_regime`;
- `evidence_quality`;
- `freshness`;
- `uncertainty`.

A composite can exist later as a research view, but every member must remain independently inspectable and ablatable.

### I2. “Information not priced in” is a model hypothesis, not a fact field

Use multiple independent tests:

1. new material fact appeared but ticker residual return is small;
2. catalyst date tightened but IV term structure did not reprice;
3. model event distribution diverges from options-implied move;
4. peer/subsector rerating occurred but the ticker lagged for no identified idiosyncratic reason;
5. washout occurred on a non-fundamental/sector-wide shock while catalyst economics remained intact;
6. positioning/flow moved before price while motive classification remains compatible;
7. enterprise value remains low relative to scenario-weighted asset economics after dilution survival.

Do not label a fact “unpriced” merely because it is new.

### I3. Catalyst proximity should not mechanically inflate opportunity

A nearer catalyst can mean:

- more realizable information edge;
- less time for the thesis to mature;
- higher IV and worse entry pricing;
- greater financing urgency;
- higher gap risk.

Therefore `days_to_event` should interact with event confidence, IV, financing runway, price state, and liquidity rather than being a monotone bonus.

### I4. Washout/mean-reversion logic should be residualized

Calculate the stock move relative to:

- broad market;
- XLV/healthcare;
- XBI/IBB biotech;
- market-cap cohort;
- modality/theme basket;
- volatility/liquidity state.

Then distinguish:

- sector beta decline;
- theme decline;
- idiosyncratic decline;
- catalyst-specific de-risking;
- financing/dilution event;
- true unexplained washout.

The “turn” model should use residual price/volume state, not raw RSI-style oversold alone.

### I5. Options should be event-conditioned

Required research groups:

- clinical readout;
- PDUFA/FDA decision;
- AdCom;
- clinical hold/release;
- financing;
- conference presentation;
- earnings;
- M&A/strategic transaction.

Features should include:

- event-window implied move;
- expiry immediately before/after event;
- IV term-structure kink;
- call/put and downside skew;
- OI/gamma concentration;
- unusual premium relative to ticker baseline;
- flow persistence;
- price/IV confirmation;
- dark-pool concentration;
- realized-vs-implied history by event class;
- spread/slippage quality.

An unusual call is **positioning evidence**, not automatically a bullish vote. Motive unresolved -> direction null.

---

## J. Prophet integration — updated implementation guardrails

The live US board is now `us_prophet_v3`, whose C1 fusion orders the already-selected population from evidence-family votes. This is the seam BioCatalyst should eventually use.

### J1. BioCatalyst must contribute members, not a second ranker

Potential homes:

- **F4 event/catalyst:** event quality, timing, revision direction, materiality, calibrated event outcome;
- **F7 quality/fundamental:** cash-through-catalyst, financing survival, dilution, asset economics;
- **F5 flow/positioning:** event-conditioned options/dark-pool anticipation;
- **F3 or F6 only when the evidence is genuinely distinct** from existing theme/regime members.

### J2. Duplicate evidence must carry one lineage ID

If one fact drives event quality and the options model, both descendants should reference the same source-event lineage. The fusion layer can then prevent the same information from receiving multiple votes under different labels.

### J3. Sparse biotech nights must abstain honestly

The C1 construction relies on within-night evidence-family variation. If the Prophet candidate pool has only one eligible biotech name or a BioCatalyst member is constant across eligible names, do not manufacture a percentile. Return null/unavailable and let the family vote without it.

### J4. First authority remains order-only among admitted names

The first live BioCatalyst authority, if earned, should preserve:

- candidate population;
- stage/gate eligibility;
- entry status;
- sizing;
- entry geometry;
- execution safeguards;
- extension/earnings vetoes.

Only ordering within the existing eligible population may change, and every movement must have a contribution trace.

### J5. Shadow comparison packet

For every night in shadow, store:

