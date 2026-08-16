- sweep/block direction and size;
- premium relative to normal;
- aggressor side;
- persistence across time;
- opening versus closing inference where possible;
- expiry and strike relationship to catalyst;
- flow-price confirmation;
- IV response;
- repeated participant behavior;
- dark-pool print concentration;
- print price versus VWAP and subsequent drift;
- unusual share volume;
- quote/flow freshness.

### 14.3 Do not equate call buying with bullish information

The lobe should classify possible motives:

- speculative long;
- stock-replacement;
- hedge;
- covered call;
- spread leg;
- dealer/gamma adjustment;
- event-volatility purchase;
- closing transaction.

When motive is unresolved, the feature should represent unusual positioning, not bullish direction.

### 14.4 Event-conditioned learning

Train and validate options features specifically around:

- clinical readouts;
- PDUFA;
- AdCom;
- FDA holds;
- label decisions;
- financings;
- earnings;
- conference presentations;
- M&A rumors/announcements.

The same options pattern can mean different things in different event classes.

### 14.5 Preserve the one-data-plane rule

- Terminal remains the intraday transport and alert owner.
- Macro remains the canonical research and nightly publication owner.
- BioCatalyst consumes point-in-time feature packets.
- Prophet consumes BioCatalyst contribution packets.
- The browser reads server-published order and explanations; it never computes rank.

---

## 15. Prophet integration

### 15.1 Use the existing `us_prophet_v3` evidence-family seam

The current canonical Prophet ranker is the C1 evidence-family fusion. It ranks already-admitted names by an equal-family, within-night evidence vote.

That is the correct integration seam.

Do not add a second “BioCatalyst total score” on top of Prophet. Do not duplicate the board ranker.

### 15.2 Map BioCatalyst members to evidence families

Potential members:

- **F4 catalyst/event:** event quality, timing, outcome, materiality, revision trajectory;
- **F7 quality/fundamental:** financing survival, dilution risk, asset economics, balance-sheet runway;
- **F5 flow/positioning:** event-conditioned options anticipation, dark-pool and unusual-flow confirmation;
- **F3 theme structure:** subsector breadth and catalyst concentration, only where independent from F4;
- **F6 macro/regime:** biotech risk regime, only if not already represented by existing market members.

The same underlying fact must not vote in multiple families under different names. Every member needs a lineage key so duplicate evidence can be detected.

### 15.3 Initial authority boundary

BioCatalyst should initially be allowed to:

- score only candidates already admitted by Prophet;
- contribute null or bounded values to named evidence families;
- reorder candidates inside the existing stage bucket only after shadow acceptance;
- publish a complete contribution trace.

It should not initially:

- admit a candidate;
- remove a candidate;
- change size;
- change entry price;
- change execution safeguards;
- bypass earnings/extension gates;
- create options trades;
- alter the browser order independently.

### 15.4 Proposed contribution contract

`biocatalyst_prophet_contribution.v1`

Fields:

- ticker/security/issuer IDs;
- Prophet board definition;
- as-of and known-at;
- source snapshot digest;
- lobe version;
- authority: display/shadow/rank;
- F4/F5/F7 member values;
- within-night percentile;
- contribution availability;
- freshness;
- completeness;
- evidence lineage IDs;
- abstentions and reasons;
- contradiction state;
- maximum permitted order effect;
- feature and model versions;
- forward-ledger registration ID.

### 15.5 Promotion stages

#### Stage 0 — display

Show BioCatalyst context on Prophet rows. No score effect.

#### Stage 1 — shadow

Compute family contributions and a shadow order. Record every night. No live order effect.

#### Stage 2 — bounded confirmer

Allow a capped contribution among already-admitted candidates. The cap and eligible families are frozen.

#### Stage 3 — earned rank authority

After prospective evidence, allow normal family participation. Still no selection or size authority.

#### Stage 4 — separate future decision

Only after substantial evidence should BioCatalyst be considered for candidate admission or sizing. That is not part of the initial program.

---

## 16. Validation and anti-look-ahead program

### 16.1 Point-in-time reconstruction

Every historical experiment must reconstruct what was knowable then:

- source version;
- entity relationship;
- security identity;
- asset owner;
- event date and date precision;
- capital structure;
- analyst estimate vintage;
- options snapshot;
- price basis;
- delisting and corporate action state.

A current ticker map or current pipeline page cannot be applied retroactively.

### 16.2 Event-study design

For catalyst impact:

- market and sector abnormal returns;
- pre-event and post-event windows;
- multiple event classes;
- clustered standard errors by issuer/event wave;
- overlapping-event controls;
- next-tradable-bar execution;
- after-hours handling;
- survivorship controls;
- correction and cancellation handling.

### 16.3 Outcome models

For clinical/regulatory outcomes:

- Brier score;
- log loss;
- reliability/calibration;
- calibration slope and intercept;
- subgroup calibration;
- decision-curve or expected-utility analysis;
- coverage and abstention rate.

### 16.4 Ranking and return models

For investment ranking:

- rank IC;
- top-k excess return;
- hit rate;
- MFE/MAE;
- drawdown;
- turnover;
- liquidity and slippage;
- deflated Sharpe;
- Newey-West/HAC where appropriate;
- issuer-cluster bootstrap;
- multiple-testing/FDR;
- simple baselines;
- ablations by evidence family.

### 16.5 Forward ledger

Every model or score version must be preregistered before it sees outcomes.

Record:

- model version;
- feature version;
- universe;
- eligibility gate;
- issue time;
- event horizon;
- forecast;
- abstention;
- later outcome;
- correction;
- evaluation version.

No model should be promoted because a retrospective notebook looked impressive.

---

## 17. Product and engineering roadmap

### Wave 0 — production rescue and observability

**Duration:** 2–3 focused days  
**Output:** current five modes render real data for an entitled user.

PR sequence:

1. request IDs and typed API errors;
2. auth diagnostic and token/entitlement tests;
3. signed-in Playwright gate;
4. projection/generation health split;
5. frontend typed state rendering;
6. freshness-clock adjudication.

No feature work begins until the browser gate is green.

### Wave 1 — re-charter, feature ledger, and product shell

**Duration:** 1 week

- new authority decision;
- new functional-parity ledger;
- modular navigation and routes;
- Catalyst Radar skeleton;
- Market Pulse skeleton;
- Explorer and dossier route model;
- operator console;
- user-facing completion telemetry.

Every feature row receives these states:

- unresearched;
- source identified;
- contract built;
- collector built;
- data populated;
- API served;
- UI surfaced;
- browser proven;
- forward-model eligible;
- shadow;
- promoted.

“Backend exists” is not “feature complete.”

### Wave 2 — temporal graph and identity

**Duration:** 2–3 weeks

- company/security/issuer graph;
- sponsor and subsidiary relationships;
- asset ownership history;
- asset × indication;
- trial-to-asset review queue;
- SEC identity and corporate actions;
- PIT read contracts;
- coverage dashboards.

This is the highest-leverage parity work. Most missing features depend on it.

### Wave 3 — parity core

**Duration:** 3–5 weeks, parallelized by source owner

- catalyst and regulatory calendars;
- company and asset dossiers;
- pipeline screeners;
- capital/cash/runway;
- biotech movers and market dashboard;
- historical catalyst outcomes;
- alerts/watchlists;
- API/export.

### Wave 4 — options, ownership, transactions, and advanced research

**Duration:** 3–5 weeks, overlapping

- options event-window features;
- intraday flow adapter;
- dark-pool adapter;
- insider/13F;
- M&A and partnerships;
- analyst estimates with vintages;
- medtech pack;
- patents/exclusivity;
- safety/label/recall.

### Wave 5 — asymmetry engine

**Duration:** 4–8 weeks, overlapping with data accrual

- scenario and materiality engine;
- timing model;
- financing survival;
- residual-price dislocation;
- options-implied dislocation;
- washout/turn model;
- shadow score;
- model browser and forward track record.

### Wave 6 — Prophet shadow and bounded contribution

**Duration:** dependent on evidence, not just code

- emit contribution contract;
- run shadow nightly and same-session provisional;
- compare v3 with and without members;
- cap contribution;
- canary;
- rollback;
- only then enable bounded order effect.

---

## 18. How to keep the next coding session out of another rabbit hole

### 18.1 Change the definition of done

A BioCatalyst PR is not done because:

- tests pass;
- a schema exists;
- a receipt exists;
- a service ran;
- a handoff says complete.

A product PR is done only when the commissioned user journey succeeds in a browser.

### 18.2 Require one visible acceptance artifact per product PR

Every UI or serving PR must include:

- before screenshot;
- after screenshot;
- actual production-equivalent response;
- nonzero row count;
- console/network summary;
- precise empty and failure states;
- mobile screenshot when relevant.

### 18.3 Limit work-in-progress

At most:

- one production-rescue lane;
- one data/graph lane;
- one product-surface lane;
- one research/shadow lane.

Do not let eight agents create eight interdependent contracts before one user journey works.

### 18.4 Small PRs, hard gates

Each PR should be independently valuable and revertible. Avoid another broad “complete parity” branch.

### 18.5 Product-first review cadence

No session should run longer than one working day without:

- opening the actual page;
- checking the actual endpoint;
- recording what changed for a user;
- reconciling against the parity ledger.

### 18.6 Budget the work

A practical allocation until the product is useful:

- 50% source/data and graph;
- 30% user-facing product;
- 15% testing/observability;
- 5% governance documentation.

The recent program effectively inverted that ratio.

---

## 19. Prioritized bug and upgrade backlog

### P0 — blocking

- signed-in API hydration failure;
- hidden auth-bootstrap failure;
- generic error collapse;
- missing request IDs;
- missing production browser proof;
- freshness-clock conflict;
- no nonzero canary;
- no direct edge/origin/local comparison;
- health endpoint conflates source, projection, API, and reader states.

### P1 — reliability and maintainability

- split monolithic `biocatalyst.js`;
- generate or validate API types;
- schema/version handshake;
- explicit session-ready gate before fetching;
- retry policy by error class;
- generation rollover tests;
- pagination and cursor rollover tests;
- stale-while-visible disclosure without stale-as-current;
- operator telemetry;
- source and projection coverage metrics;
- realistic load and large-cohort tests.

### P1 — product

- Catalyst Radar;
- company/asset dossiers;
- biotech market dashboard;
- calendars;
- saved watchlists;
- alert actions;
- rich empty states;
- light/dark and mobile acceptance;
- one-click source/evidence thread.

### P2 — parity and intelligence

- temporal entity graph;
- cash/runway/dilution;
- regulatory estate;
- ownership/transactions;
- options and dark-pool adapters;
- historical outcomes;
- event-response research;
- asymmetry score;
- Prophet shadow packet.

---

## 20. Completion gates

### Current product rescue is complete only when

