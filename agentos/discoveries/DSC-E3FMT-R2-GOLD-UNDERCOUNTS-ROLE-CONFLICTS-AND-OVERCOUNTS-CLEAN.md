---
key: E3FMT-R2-GOLD-UNDERCOUNTS-ROLE-CONFLICTS-AND-OVERCOUNTS-CLEAN
claim: >
  The ratified TFG-1 R2 development gold disagrees with its own frozen source at the
  respondent-role layer: it declares 2 calls with explicit same-revision management role
  conflicts where the source carries 5, and its 9-call source-clean set includes 2 calls
  whose management the revision never gives an office, so the true clean count is 7.
falsifier: >
  Run `python3 research/earnings_intelligence/e3/tfg1_separator_falsifier_measurement.py`
  to byte-replay the 16 frozen development revisions, then read each call's segment #1
  declaration against that speaker's segment role tags. Refuted if BANR/LTH/HTGC carry no
  contradictory same-revision role evidence, or if ARQQ's Nick Pointon or FANG's Chad
  McAllaster is given an office anywhere in their own exact revision, or if either speaker
  never answers inside a Q&A window. Compiler behaviour at
  engine/company_intelligence/qa_reconstruction.py:1 and the measured matrix in #6591.
so_what: >
  The gate "9/9 source-clean calls produce non-empty reconstruction" is unsatisfiable
  without a forbidden move, so R2 cannot reach implementation freeze on the gold as
  ratified, and the fix is a Sol amendment rather than code. It also endangers the
  single-use holdout: the holdout's source-only slot adjudication must freeze a
  QNA_SOURCE_CLEAN definition BEFORE compiler output, and the gold's working definition
  is "no unresolved questioner AND no contradictory role evidence" -- which accounts for
  role CONFLICT but not role ABSENCE. Freezing that definition would adjudicate
  untitled-executive slots clean, the frozen compiler would miss them, and the power
  ruling would calibrate on the wrong denominator. The holdout is non-replaceable, so a
  future session must settle this before unseal, never after.
kind: data
verified_at: 2026-08-28
verified_by: "PR #6591 head bf012bad18a92961596dbc236945feaeec880c89; 16-call replay of research/earnings_intelligence/e3/tfg0_transcript_format_development_corpus_selection.json"
scope:
  - macro
  - WS:EARNINGS-EVENT-INTELLIGENCE-COMPILER
  - E3-FMT
  - research/earnings_intelligence/e3/**
confidence: verified
---

The five explicit role conflicts, each declared in segment #1 of its own revision beside
correctly-tagged colleagues: ARRY and CTRE (both already declared in the gold), plus BANR
declaring Jill Rice "our Chief Credit Officer" while every one of her segments is tagged
CFO, LTH declaring Erik Weaver "Executive Vice President and CFO" while his segments are
tagged CEO, and HTGC declaring Seth Meyer "President" while his segments are tagged CEO.
This does not move the 9/7 partition, since all five already refuse; it moves the frozen
refusal REASON for three of the seven.

The two overcounted clean calls: ARQQ's Nick Pointon speaks eight times with a blank role
and is only ever introduced as "let me turn the call over to Nick Pointon"; FANG's Chad
McAllaster speaks once with a blank role and is only ever referenced as "I'll let Chad or
Danny give the details". Both answer inside a Q&A window, and the frozen amendment makes
missing role support a refusal.

Separators were exact at the measuring head — 16/16 sets, 113/113 — so the disagreement is
isolated to the respondent-role layer and is not contaminated by boundary error.

This is the second time this programme's ratified gold has failed against its own source.
The v1 wave stopped on a separator undercount (110 declared, 113 measured); this is the
same shape one layer down. The lesson v1 already paid for generalises: measure a frozen
gold against source before encoding it, and treat a disagreement as a ruling for the
authority rather than something to implement around.

Related: [[DSC-E3FMT-ROSTER-DECLARATION-ORDERS-ARE-FALSE-FRIENDS]] — the parser bugs that
had to be cleared first, because each produced a fabricated conflict that would have been
mistaken for exactly this finding.
