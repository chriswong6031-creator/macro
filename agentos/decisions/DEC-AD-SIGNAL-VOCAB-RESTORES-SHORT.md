---
key: AD-SIGNAL-VOCAB-RESTORES-SHORT
question: >
  Does the Advanced Data signal contract's direction vocabulary include SHORT, given the
  older Options Confluence law 17 (AVOID-not-SHORT) that forbade bear/short origination
  anywhere in the options program?
answer: >
  Yes. The Advanced Data architectural signal vocabulary is LONG / SHORT / VOLATILITY /
  RISK_ONLY / NEUTRAL (masterplan §6.2). SHORT is restored to the logical contract. The
  stronger inference law is kept: no raw call/put volume, premium, volume/OI, tick-rule
  flow, GEX, or other insufficiently directional observation may originate LONG or SHORT
  on its own; unsupported direction must abstain or express as RISK_ONLY/NEUTRAL. With
  today's entitled EOD sources the implementation may lawfully emit zero SHORT signals.
rationale: >
  Deleting SHORT from the contract structurally banned future defensible bearish evidence
  and created a bullish-only asymmetry in a lobe whose mission includes crowding/risk
  anticipation. The protection the old law was buying (no bear calls invented from
  ambiguous flow) is preserved by the direction-qualification law itself, which is
  evidence-gated rather than vocabulary-gated. CEO review on PR #5830 ordered the
  restoration explicitly.
alternatives:
  - option: Keep AVOID-not-SHORT (AD-1 enum omits SHORT), as AD-0 originally froze
    why_not: rejected by CEO review on #5830 — narrows the recovered architecture; asymmetry is structural, not evidence-driven
  - option: Allow SHORT with no extra qualification (symmetric to LONG)
    why_not: entitled sources cannot observe aggressor/open-close; direction from insufficiently directional observations would violate masterplan §3.18
affects:
  - "WS:ADVANCED-DATA-OPTIONS"
  - options-intelligence
  - research/ADVANCED_DATA_OPTIONS_EOD_AD1_DAILY_INTELLIGENCE_BRIEF_HANDOFF_2026-08-17.md
evidence:
  - "Sol (CEO) review on PR #5830, amendment 2 (2026-08-17)"
  - "research/ADVANCED_DATA_OPTIONS_EOD_DARK_POOL_INTELLIGENCE_OS_MASTERPLAN_2026-08-17.md §6.2 direction enum"
  - "research/OPTIONS_CONFLUENCE_PROGRAM_BY_FABLE.md §3 law 17 (the superseded-in-scope rule)"
confidence: high
reversibility: easy
decided_by: ceo-sol
decided_at: 2026-08-17
---

Scope note: this decision governs the Advanced Data signal contract (AD waves). It does
not repeal Options Confluence law 17 for the legacy confluence-program surfaces, which
keep their existing behavior until their own docs are amended; it prevents that law from
being carried INTO the new Advanced Data contract. Bearish evidence that fails the
direction-qualification law expresses as RISK_ONLY — the AVOID posture survives as the
fallback, not as a vocabulary ban.
