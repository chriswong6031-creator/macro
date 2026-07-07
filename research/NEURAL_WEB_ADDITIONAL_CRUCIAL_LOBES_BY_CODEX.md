# Neural Web Additional Crucial Lobes

**Prepared:** 2026-07-06  
**Status:** Third-pass lobe gap assessment.  
**Scope:** Three more crucial lobes that should sit after the first five in `research/NEURAL_WEB_NEXT_LOBES_PRIORITY_BY_CODEX.md`. These are not junk-drawer ideas; each owns a distinct decision question, labels, and falsifiers.

---

## Executive Verdict

After the first five missing lobes:

1. Sponsorship and Forced-Flow Absorption
2. Fragility, Solvency, and Event-Hazard
3. Cash-Patience and Abstention
4. Long-Term Thesis and Expectations-Drift
5. Realized Decision, Execution, and Operator-Feedback

the next three crucial lobes should be:

6. **Claim Reliability and Narrative Truth Lobe**
7. **Macro and Policy Transmission Fingerprints Lobe**
8. **Portfolio and Thesis-Independence Lobe**

These are crucial because they answer three questions the first five do not fully answer:

```text
Can we trust the story?
What macro world must be true?
Are we accidentally making the same bet five times?
```

Those are institutional questions. They are not cosmetic. A system that lacks them can be rich, fast, and still wrong in the exact way humans and models are usually wrong: believing a persuasive story, ignoring the macro precondition, or mistaking many correlated names for diversification.

---

## What Makes These Real Lobes

Each passes the lobe bar:

- owns its own objective function;
- has labels that can mature;
- has falsifiers;
- can plug into spine/qledger/replay/kernel rails;
- improves a specific decision;
- does not need to originate trades or escalate authority.

Each should begin display/shadow and mostly de-escalate, annotate, or demand patience until earned evidence exists.

---

## 6. Claim Reliability and Narrative Truth Lobe

### Killer Question

Which stories, qualitative claims, AI-desk statements, news vectors, and foresight theses actually deserve trust?

### Why This Is Crucial

Neural Web already has many qualitative and AI-adjacent narrators: qledger, altdata, ai desk, foresight, policy intent, news vector, cortex, master brain, risk brain, and narrative/radar surfaces. That is useful, but also dangerous.

Local evidence from the current worktree:

- `data/qledger/claims.jsonl` has 9,069 claims.
- `data/qledger/grades.jsonl` has 2,815 grades.
- Most qledger claims carry `direction=0`, meaning a large share are state/context claims rather than simple directional bets.
- `falsifier` is `None` for 8,923 of 9,069 claims.
- The claim rows have useful core fields such as `desk`, `claim_family`, `scope`, `direction`, `horizon_d`, `check_by`, and `claim_id`, but source/channel-like dimensions are not yet a real reliability ontology in the rows I inspected.

That means qledger is a strong substrate, but not yet a full narrative-trust lobe.

Without this lobe, Neural Web will eventually do a very human thing: overweight the most coherent story, the newest story, or the story repeated by multiple desks that all share the same hidden source.

### What It Owns

Objective:

```text
claim_reliability_by_shape_source_regime_and_horizon
```

It owns:

- `claim_hit_probability`
- `claim_decay`
- `source_reliability`
- `falsifier_quality`
- `story_redundancy`
- `contradiction_resolution`
- `earliness_value`
- `narrative_overconfidence`

### Current Substrates

- `data/qledger/claims.jsonl`
- `data/qledger/grades.jsonl`
- `site/qledger/track_record.json`
- `data/news_vector/events.parquet`
- `data/foresight/log.jsonl`
- `data/policy_intent/theses.jsonl`
- `data/altdata/mastermind.json`
- cortex memo/hypothesis metabolism
- `engine/falsifier_tripwires.py`

### First Labels

- claim graded hit/miss by horizon;
- falsifier present vs absent;
- falsifier fired before price damage;
- claim repeated across desks with no independent source;
- claim contradicted by price/factor/options state;
- claim was early enough to matter;
- claim decayed before action.

### First Experiments

1. **NARR-1: Falsifier quality**
   - Compare claims with explicit machine-checkable falsifiers versus claims without them.
   - Output: source/channel trust context, not board rank.

2. **NARR-2: Story decay**
   - Measure how claim usefulness changes after 5, 21, and 63 sessions.
   - Print decay by `claim_family`, `desk`, and horizon.

3. **NARR-3: Contradiction arbitration**
   - When narrative says one thing and price/factor/options says another, who historically wins?
   - Output: de-escalation rule candidates only.

### Website Surface

First surface should be `measurement.html` and qledger diagnostics:

- claims with no falsifier;
- claims by family/horizon;
- matured vs unmatured;
- repeated story clusters;
- narrative families with poor or thin history.

### Why Institutions Would Build It

Institutions do not only gather information. They grade informants, analysts, channels, documents, and research motifs. This lobe is Neural Web's defense against persuasive but unearned intelligence.

---

## 7. Macro and Policy Transmission Fingerprints Lobe

### Killer Question

What macro or policy condition must be true for this name, sector, or thesis to work?

### Why This Is Crucial

The repo has macro data and event context, but not a mature lobe that says:

```text
this stock needs rates down;
this basket needs USD weakness;
this sector needs credit stress easing;
this China/HK setup needs policy impulse;
this commodity name needs oil/copper confirmation;
this long-duration growth basket dies if real yields rise.
```

Local evidence:

- Macro stores exist: `data/cot/*.parquet`, `data/ofr_fsi/*.parquet`, `data/fred_vintage/vintages.parquet`, `data/rate_futures/*.parquet`, and many `data/fred/*.parquet` series.
- `engine/event_risk.py` already creates event-risk context and logs/resolves event banners.
- `engine/hk_global_beta.py` shows the right shape for a market-specific transmission read: beta to global risk as context, not a buy list.
- The future-lobes docket correctly costed per-name macro fingerprints as green-field and warned that the nearest sector-level precedent was noisy.

That warning is right. This lobe should begin at sector/basket/regional level, not with overfit per-name regressions.

### What It Owns

Objective:

```text
macro_precondition_and_transmission_risk_for_each_signal_family
```

It owns:

- `rate_sensitive`
- `usd_sensitive`
- `oil_sensitive`
- `credit_sensitive`
- `inflation_sensitive`
- `liquidity_sensitive`
- `policy_impulse_sensitive`
- `global_risk_beta`
- `macro_relief_required`
- `macro_headwind_active`

### Current Substrates

- `data/fred/`
- `data/fred_vintage/vintages.parquet`
- `data/ofr_fsi/`
- `data/ofr/`
- `data/cot/`
- `data/rate_futures/`
- `engine/event_risk.py`
- `engine/hk_global_beta.py`
- macro/regime blocks inside `data/neuralweb/world_state.json`
- country/sector/basket ledgers

### First Labels

- setup worked only when macro precondition was favorable;
- setup failed during hostile macro condition;
- sector/basket drawdown after macro shock;
- signal family base rate by rate/USD/credit/liquidity/stress regime;
- macro relief before forward improvement;
- macro contradiction present at fire date.

### First Experiments

1. **MACRO-TX-1: Sector-first transmission**
   - Start with sectors/baskets, not single names.
   - Measure whether rates, USD, credit stress, oil, and liquidity state condition forward outcomes after existing fires.

2. **MACRO-TX-2: Macro contradiction**
   - If entry/bottom fires while macro precondition is hostile, does wait/skip improve outcomes?
   - This feeds the Abstention Lobe.

3. **MACRO-TX-3: Long-thesis preconditions**
   - For thesis candidates, store "what must remain true" macro conditions.
   - Feed Long-Term Thesis Lobe falsifiers.

### Website Surface

- `committee.html`: "macro precondition" line on thesis candidates.
- `measurement.html`: macro-transmission base rates by sector/basket.
- Regional pages: context only, especially HK/China/Canada.

### Why Institutions Would Build It

Institutions do not treat a stock as isolated. They ask what factor, macro, and policy world the thesis implicitly requires. Without this lobe, Neural Web can buy a beautiful micro setup in a hostile macro tape and only realize afterward that the setup was a disguised rate, USD, credit, or policy bet.

---

## 8. Portfolio and Thesis-Independence Lobe

### Killer Question

Are we making independent decisions, or accidentally expressing the same thesis through many tickers?

### Why This Is Crucial

This is the lobe that keeps a strong signal system from quietly becoming one crowded book.

Local evidence:

- `engine/reflexivity.py` already computes held-agnostic candidate similarity and `N_eff` over high-tier factors.
- `engine/foresight_enb.py` has effective-number-of-bets style theme clustering.
- `data/neuralweb/mastermind_context.json` exists and includes a `book_context` concept.
- The Neural Web -> Mastermind linking study found the clean design should be context-only at birth, because Mastermind owns held book, sizing, and execution.

So this lobe is not fully Macro-only. It is a cross-repo lobe: Macro can describe candidate/thesis overlap; Mastermind must eventually provide held-book positions and realized exposure.

### What It Owns

Objective:

```text
independent_thesis_count_and_hidden_exposure_before_action
```

It owns:

- `thesis_cluster`
- `effective_independent_bets`
- `hidden_factor_concentration`
- `theme_crowding`
- `same_trade_many_tickers`
- `new_candidate_adds_diversification`
- `new_candidate_duplicates_existing_thesis`
- `book_context_only`

### Current Substrates

- `engine/reflexivity.py`
- `engine/foresight_enb.py`
- `data/neuralweb/mastermind_context.json`
- `research/NEURAL_WEB_MASTERMIND_LINKING_STUDY.md`
- `data/strategies/capacity_curve.json`
- `data/strategies/construction_divergence.json`
- sector/basket membership artifacts
- factor exposure artifacts
- Mastermind held-book data, once explicitly bridged

### First Labels

At first, labels are not trade PnL. They are exposure and decision-quality labels:

- candidate added new thesis;
- candidate duplicated existing thesis;
- top-N board collapsed into one factor/theme;
- realized drawdown came from hidden common exposure;
- operator dismissed duplicate exposure and avoided concentration;
- operator added duplicate exposure and increased drawdown.

### First Experiments

1. **BOOK-1: Candidate-set independence**
   - Use Macro-only candidate boards.
   - Measure top-N effective independent bets by day and by regime.

2. **BOOK-2: Thesis cluster tags**
   - Cluster candidates by sector, theme, factor, macro sensitivity, and ownership/sponsorship mechanism.
   - Output: "same thesis" tags, not sizing.

3. **BOOK-3: Mastermind held-book bridge**
   - Add an explicit contract where Mastermind sends holdings or exposure summary back to Macro/Neural Web.
   - Neural Web remains context/de-escalation only.

### Website Surface

- `committee.html`: cluster warnings on candidate sets.
- Mastermind bridge: held-book overlap context.
- `measurement.html`: top-N N_eff history and drawdown episodes by hidden cluster.

### Why Institutions Would Build It

Institutions care about independent bets. Five great AI infrastructure stocks can still be one trade. Ten China recovery names can still be one policy bet. Without this lobe, Neural Web can be accurate name by name and still fail at the book level.

---

## Updated Lobe Map

If the first five are the immediate missing organs, these three are the next layer:

```text
6. Claim Reliability / Narrative Truth
7. Macro and Policy Transmission
8. Portfolio and Thesis Independence
```

Together with the first five:

```text
entry fire
  -> sponsorship says whether demand is real
  -> fragility says what can break
  -> macro transmission says what world must be true
  -> claim reliability says whether the story is trustworthy
  -> abstention says take now / wait / skip
  -> thesis layer says trade-only / hold-candidate
  -> portfolio independence says whether this adds a new bet
  -> operator/execution lobe says whether the real decision improved
```

That is much closer to an institutional organism.

---

## Bottom Line

The next three crucial lobes are:

1. **Claim Reliability and Narrative Truth** - because a smart system must learn which stories to distrust.
2. **Macro and Policy Transmission Fingerprints** - because every thesis has hidden macro preconditions.
3. **Portfolio and Thesis-Independence** - because many good names can still be one bad book.

If these are missing, Neural Web can still be impressive. But it will remain vulnerable to narrative overconfidence, macro-blind micro picks, and accidental concentration. Those are not edge cases. They are exactly how sophisticated systems get humbled.
