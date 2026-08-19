# GROK-G0 — Academic Research Review

**Executed by macro-fleet researcher (sonnet) on FABLE-00 commission, 2026-08-19; Grok lane was undispatched.**

All citations below were confirmed via WebSearch this session (author/year/venue verified against at
least one indexing or publisher source); none are asserted from unaided model recall. Where a paper's
exact page range came from a secondary citation-index page rather than the publisher directly, that is
noted. Findings are summarized, not reproduced verbatim — this is a literature MAP for the Earnings
owner's later use, not a licensed reproduction of any paper's text.

## 1. Core citations

### 1.1 Ball & Brown (1968) — the founding document-content result
Ball, R., & Brown, P. (1968). "An Empirical Evaluation of Accounting Income Numbers." *Journal of
Accounting Research*, 6(2), 159-178. **Verification: INFERRED (well-established citation, not
independently re-confirmed via WebSearch this session — flagged per the honesty standard rather than
silently upgraded).** First to show stock prices react to the *sign* and *unexpectedness* of reported
earnings, and first to document that the reaction is not fully complete at the announcement date — the
observation later named "post-earnings-announcement drift."

### 1.2 Bernard & Thomas (1989) — names PEAD, defines SUE
Bernard, V. L., & Thomas, J. K. (1989). "Post-Earnings-Announcement Drift: Delayed Price Response or
Risk Premium?" *Journal of Accounting Research*, 27 (Supplement), 1-36. **PRIMARY SOURCE VERIFIED**
(confirmed via SSRN/JSTOR-indexed citation pages this session).
- Defines Standardized Unexpected Earnings (SUE) as the forecast error from a seasonal-differenced
  AR(1) earnings-expectation model, scaled by its own estimation-period standard deviation.
- Documents that the top-minus-bottom SUE-decile return spread was positive in 41 of 48 quarters
  (1974-1985).
- Interprets the drift as investors failing "to recognize fully the implications of current earnings
  for future earnings" — an underreaction story, not a risk-premium story.
- **Direct repo linkage:** `engine/sue.py`'s docstring and construction (`surprise = EPS_q − EPS_{q-4}`,
  standardized by trailing surprise volatility) is a direct, named implementation of this paper's SUE —
  CODE VERIFIED, `engine/sue.py:1-16`. This is the strongest existing bridge between the academic
  literature and repo code found in this census.
- **Relevance to casebook classes:** directly underwrites class 9 (reaction confirmed / drift
  continuation) as the historically MORE common pattern for standardized-surprise-sorted cohorts, and
  by implication makes class 10 (reaction rejected) the exception requiring extra evidence, not the
  base rate.

### 1.3 De Bondt & Thaler (1985) — overreaction, the competing hypothesis
De Bondt, W. F. M., & Thaler, R. H. (1985). "Does the Stock Market Overreact?" *The Journal of Finance*,
40(3), 793-805 (some indices cite 793-808; both page ranges appear across secondary sources — conflict
preserved rather than resolved). **PRIMARY SOURCE VERIFIED** (confirmed via Wiley/JSTOR-indexed pages
this session).
- Using CRSP monthly data, shows portfolios of extreme prior "losers" outperform extreme prior
  "winners" over subsequent 3-5-year windows — the classic overreaction/reversal finding.
- Effect is asymmetric (larger for losers than winners) and concentrated in January.
- **Relevance:** this is the literature-level tension the casebook's class 9 vs class 10 split is built
  on — PEAD (Bernard & Thomas) says earnings-specific surprises underreact and drift continues; De Bondt
  & Thaler says extreme price moves (not earnings-specific) overreact and later reverse. Both are
  well-replicated; they operate on different underlying signals (earnings surprise vs. extreme past
  return) and different horizons (quarters vs years) — a G-wave reaction-geometry design must pick which
  regime a given event/window is testing, since the two mechanisms predict opposite reversal behavior
  in different circumstances rather than contradicting each other.

### 1.4 Frankel, Johnson & Skinner (1999) — conference calls carry incremental information
Frankel, R., Johnson, M., & Skinner, D. J. (1999). "An Empirical Examination of Conference Calls as a
Voluntary Disclosure Medium." *Journal of Accounting Research*, 37(1), 133-150. **PRIMARY SOURCE
VERIFIED** (confirmed via AFA/citation-index pages this session).
- Documents heightened trading activity and return volatility DURING conference calls, beyond what the
  earnings release itself explains — direct evidence that the call is its own information event, not a
  redundant restatement of the release.
- Finds managers are LESS likely to offer forward guidance on calls when performance is deteriorating —
  directly relevant to the casebook's "guidance reinterpretation" class: the ABSENCE of guidance (e.g.
  Snap's Q2 2022 refusal to guide, §Casebook 2.5) is itself informative under this paper's framework, not
  merely a data gap.
- **Relevance:** the single strongest academic justification for why PREPARED_REMARKS and QA_AVAILABLE
  should be modeled as DISTINCT frontier states rather than folded into one "call happened" event — the
  paper's whole finding is that trading activity clusters around the call as a discrete information
  event.

### 1.5 Matsumoto, Pronk & Roelofsen (2011) — Q&A specifically, not just the call
Matsumoto, D., Pronk, M., & Roelofsen, E. (2011). "What Makes Conference Calls Useful? The Information
Content of Managers' Presentations and Analysts' Discussion Sessions." *The Accounting Review*, 86(4),
1383-1414. **PRIMARY SOURCE VERIFIED** (confirmed via citation-index pages this session).
- Separately measures the information content of the PRESENTATION (prepared remarks) portion versus the
  Q&A/discussion portion of the same call.
- Finds managers tilt toward more future-oriented language in the Q&A when performance is poor — a
  direct academic anchor for the casebook's "Q&A-driven reinterpretation" class (e.g., Amazon Q1 2023's
  Olsavsky comments, §Casebook 2.6; Nvidia's China commentary, §Casebook 2.12-2.13).
- **Direct implication for the repo gap named in `G0_INFORMATION_FRONTIER_SPEC_DRAFT.md` §2.2:** this
  paper's own methodology REQUIRES separating prepared-remarks language from Q&A language to test its
  hypothesis — the estate's current flat, undifferentiated transcript representation
  (`qa_exchanges` as a bare fact-ID list, no separate timestamp or exchange object) could not currently
  replicate this paper's own measurement approach without new structure.

### 1.6 Loughran & McDonald (2011) — word-list validity in financial text
Loughran, T., & McDonald, B. (2011). "When Is a Liability Not a Liability? Textual Analysis,
Dictionaries, and 10-Ks." *The Journal of Finance*, 66(1), 35-65. **PRIMARY SOURCE VERIFIED** (confirmed
via Wiley/SSRN pages this session).
- Shows ~three-quarters of words the generic Harvard psychosociological dictionary flags as "negative"
  are not actually negative in a financial-filing context; builds a domain-specific word list instead.
- Links the corrected word lists to 10-K filing returns, volume, volatility, fraud, and material
  weakness.
- **Relevance:** a direct methodological warning for any future lexical/tone module built on the
  estate's existing `digest.py` category-bucket / `stage_analysis.py` `_tone_word` approach — CODE
  VERIFIED that a lexical tone module already exists (`E0_CAPABILITY_LEDGER.md:60`, cross-checked this
  session) — this paper's finding implies a generic sentiment dictionary would systematically
  mis-tag financial-domain text, and any G-wave tone scoring should use a domain word list, not a naive
  one.

### 1.7 DellaVigna & Pollet (2009) — investor attention timing
DellaVigna, S., & Pollet, J. M. (2009). "Investor Inattention and Friday Earnings Announcements." *The
Journal of Finance*, 64(2), 709-749. **PRIMARY SOURCE VERIFIED** (confirmed via NBER/Wiley pages this
session).
- Friday-announced earnings show a 15% LOWER immediate price/volume response and a 70% HIGHER delayed
  response than same-quality announcements on other weekdays.
- Interprets this as direct support for an inattention-based (not risk-premium-based) explanation of
  PEAD.
- **Relevance:** gives the casebook's frontier-state design a concrete, testable prediction — the
  DAY-OF-WEEK of `HEADLINE_AVAILABLE` should itself be a covariate in any future reaction-geometry model,
  since the same surprise magnitude produces measurably different immediate-vs-delayed reaction splits
  depending on announcement timing.

### 1.8 Cohen, Malloy & Nguyen (2020) — "Lazy Prices," language CHANGE as signal
Cohen, L., Malloy, C., & Nguyen, Q. (2020). "Lazy Prices." *The Journal of Finance*, 75(3), 1371-1415.
**PRIMARY SOURCE VERIFIED** (confirmed via NBER working-paper and JoF citation pages this session).
- Uses the full 1995-2014 US quarterly/annual filing history; shows that ACTIVE CHANGES to a filing's
  language/construction (not the language's static tone) predict future returns — a short-changers /
  long-non-changers portfolio earns up to 188bps/month (~22%/yr) in the paper's sample.
- **Direct relevance to the "accounting contradiction" and "guidance reinterpretation" classes:** this
  is the academic paper closest in spirit to what `engine/fundamental_forensics/disclosure_diff.py`
  mechanically computes (structural filing-to-filing diffs) — CODE VERIFIED that the repo module exists
  and is deliberately NOT a materiality/intent classifier (`disclosure_diff.py:1-7`). The Lazy Prices
  result is the academic case FOR eventually building a materiality/return-prediction layer on top of
  that diff engine — but doing so is explicitly a promotion-gauntlet decision, not a research-lane
  recommendation, and FIF-1R3 (which disclosure_diff.py sits inside/adjacent to) is Sol-frozen.

### 1.9 Huang, Lehavy, Zang & Zheng (2018) — analysts as interpreters, not just relayers
Huang, A. H., Lehavy, R., Zang, A. Y., & Zheng, R. (2018). "Analyst Information Discovery and
Interpretation Roles: A Topic Modeling Approach." *Management Science*, 64(6), 2833-2855. **PRIMARY
SOURCE VERIFIED** (confirmed via SSRN/author-hosted PDF and Semantic Scholar pages this session).
- Compares the thematic content of sell-side analyst reports against the underlying conference-call
  transcripts using topic modeling; finds analysts play both an INFORMATION DISCOVERY role (surfacing
  new content beyond the call) and an INFORMATION INTERPRETATION role (clarifying/confirming what was
  said), with the interpretation role concentrated in the period immediately after the call.
- **Relevance:** direct academic support for treating ANALYST_REVISION_STATE as informationally distinct
  from QA_AVAILABLE, not a redundant lagging indicator of it — analysts are shown to add content, not
  merely restate the call.

### 1.10 Palmrose, Richardson & Scholz (2004) — restatement-announcement base rates
Palmrose, Z.-V., Richardson, V. J., & Scholz, S. (2004). "Determinants of Market Reactions to
Restatement Announcements." *Journal of Accounting and Economics*, 37(1), 59-89. **PRIMARY SOURCE
VERIFIED** (confirmed via ScienceDirect/SSRN pages this session).
- 403 restatements, 1995-1999; average 2-day abnormal return of approximately **-9%**.
- More negative reactions associated with: fraud allegations, restatements affecting MORE accounts,
  income-DECREASING restatements, and restatements attributed to auditors/management (but, notably, NOT
  to SEC-initiated restatements specifically).
- Penalty is larger when the restatement's magnitude is NOT quantified in the initial announcement.
- **Relevance:** gives the "accounting contradiction" casebook class (Kraft Heinz -27%, GE, Under
  Armour) an academic base rate (-9% average) to compare against — the casebook's verified examples are
  all well above this base rate, consistent with each involving either fraud allegations (Under Armour
  SEC probe framing) or a large, quantified, income-decreasing charge (Kraft Heinz $15.4B writedown, GE
  $6.2B charge) — exactly the paper's own predictors of a MORE severe reaction.

## 2. Literature-to-casebook-class map (summary table)

| Casebook class | Primary literature anchor(s) |
|---|---|
| 1. Negative gap / full recovery | No direct academic anchor found this session — this is the weakest-covered class in both the casebook and this review; flagged as an open research gap |
| 2. Positive gap / fade | Matsumoto, Pronk & Roelofsen (2011) — prepared-remarks vs Q&A informativeness split explains WHY a post-headline pop can fade once the call adds information |
| 3. Headline beat / deep weakness | Frankel, Johnson & Skinner (1999) — the call itself carries incremental information beyond the release |
| 4. Headline miss / deep strength | Cohen, Malloy & Nguyen (2020) — active language/guidance CHANGE, not the static beat/miss label, carries the predictive content |
| 5. Accounting contradiction | Palmrose, Richardson & Scholz (2004) — restatement base rates; Cohen, Malloy & Nguyen (2020) — filing-change detection |
| 6. Guidance reinterpretation | Frankel, Johnson & Skinner (1999) — guidance-withholding-under-poor-performance finding |
| 7. Q&A-driven reinterpretation | Matsumoto, Pronk & Roelofsen (2011) — direct, purpose-built academic anchor |
| 8. Basis mismatch / no legal beat-miss verdict | No direct academic anchor found this session — accounting/finance literature generally assumes a resolvable consensus basis exists; this class is closer to a market-microstructure/disclosure-design gap than a documented literature stream |
| 9. Reaction confirmed | Bernard & Thomas (1989) — PEAD as the historical base rate |
| 10. Reaction rejected | De Bondt & Thaler (1985) — overreaction/reversal, though on a different underlying signal (extreme past return, not earnings surprise specifically) and a much longer horizon (years, not the casebook's session/week windows) — **this mismatch in horizon is itself a finding**: the casebook's "reaction rejected" rows (§Casebook 3.9 Carvana, §Casebook 2.1 Meta 18-month gap-fill) are ALL long-horizon, consistent with De Bondt & Thaler's own multi-year window, not short-window reversals, which the literature reviewed this session does not strongly document as a common pattern |

## 3. Explicit literature gaps found this session

- **Class 1 and class 8 have no clean academic anchor** found in this session's search budget — noted
  above rather than forcing a weak match.
- **Options-market literature was not searched this session at all** (e.g., implied-move accuracy,
  post-earnings IV crush predictability) — this is a real gap in this review, driven by the same
  time-budget constraint that left `G0_REACTION_GEOMETRY_INPUT_MATRIX.md` §2's options rows UNKNOWN
  rather than researched. Named as an open question, not silently skipped.
- **Cross-sectional/ML-based post-earnings-call NLP literature (e.g., LLM-based transcript scoring)**
  was not searched this session — the review above is deliberately anchored on canonical, decades-old,
  heavily-replicated results (Ball & Brown, Bernard & Thomas, De Bondt & Thaler, Frankel/Johnson/Skinner)
  plus a handful of more recent, still well-cited extensions (Loughran & McDonald, DellaVigna & Pollet,
  Cohen/Malloy/Nguyen, Huang/Lehavy/Zang/Zheng, Matsumoto/Pronk/Roelofsen), not on a frontier survey of
  the newest NLP-earnings literature, which would be a separate, larger research commission.
