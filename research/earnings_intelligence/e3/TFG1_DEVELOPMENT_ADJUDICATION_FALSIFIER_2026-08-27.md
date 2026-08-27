# TFG-1 — development adjudication falsifier (wave stopped at the development gate)

**Operation:** `tfg1-deterministic-transcript-format-hardening-20260827-v1`
**Canonical handoff:** `TFG1_DETERMINISTIC_TRANSCRIPT_FORMAT_HARDENING_HANDOFF_R1_2026-08-27.md`
**Outcome:** STOP — named falsifier returned to Sol. Holdout NOT unsealed.
**Runtime effect:** none. No compiler source changed, no production admission changed, zero model calls.
**Measurement receipt:** `tfg1_development_separator_falsifier_receipt.json`
**Reproduce:** `python3 research/earnings_intelligence/e3/tfg1_separator_falsifier_measurement.py` (~11s from a clean fetch; reads only the 16 already-open development revisions, never the holdout)

## 1. What was asked and what happened

TFG-1 was to implement the frozen source-native separator/identity law, prove it against the
frozen 16-call development adjudication, freeze the implementation head, and only then unseal the
eight-slot unseen holdout.

Implementing the frozen law faithfully and measuring it against the frozen gold shows the gold
itself is internally inconsistent. The development gate therefore cannot be certified green, and
under the dispatch's own stop conditions the holdout must not be opened.

## 2. Corpus is intact — no revision moved

All 16 exact development revisions byte-replay to their frozen SHAs, **16/16**.

Replay is only reproducible under TFG-0's canonical-JSON convention:

```text
sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',',':')).encode('utf-8'))
```

Hashing the raw decompressed body instead reports `COF/2026Q2` as a moved revision. It has not
moved. 15 of the 16 stored files already happen to be in canonical form so both conventions agree;
`COF/2026Q2` is not, which is the whole of the difference. Corroboration: the live
`mastermind.tx-index/v1` is byte-identical to the TFG-0 snapshot (`raw_sha256 58f15ff0…`, same
`generated_at`); the served COF object matches every attribute the index publishes for it
(22131 bytes, 133 segments, 15 named speakers, `word_count` 11256, `qa_start` 20); all 11 frozen COF
separator indices land exactly on Operator question handoffs; and a 60-record sample of 2026Q2/Q3
index entries agreed 60/60. This is a serialization convention, not a source defect, and it is
recorded here because the wrong convention produces a false `SOURCE_REVISION_MISMATCH`.

## 3. The falsifier

A structural separator, per `TFG0_R1_…_AMENDMENT` §2.1, is an Operator/housekeeping handoff that is
unambiguously question-bearing and is immediately followed by a non-housekeeping source turn.
Opening prepared-speaker handoffs, generic queue instructions and closing returns are excluded.

Implementing exactly that predicate over the 16 exact revisions yields **113** structural
separators. The frozen receipt records **110**.

- recall against the frozen gold: **110/110**
- false negatives: **0**
- direct-name extraction on the frozen 95 direct handoffs: **95/95 exact**, 0 failures
- residual detections not in the gold: **3**

The three are each the segment in which the Operator both opens the Q&A session and names the first
questioner:

- `MBLY/2026Q2` #21 — names Joshua Buchalter; next source turn is the analyst
- `ARRY/2026Q2` #31 — names Joe Osha; next source turn is Joe Osha
- `KREF/2026Q2` #15 — names Tom Catherwood; next source turn is Tom Catherwood

**These are not a detector artifact.** Thirteen of the sixteen calls contain a structurally
identical combined Q&A-opener-plus-first-question segment, and the frozen receipt counts all
thirteen as separators (OCSL #29, GEF #25, ARQQ #22, TRVI #12, CTRE #17, LTH #10, UPBD #32,
SCCO #53, AGM #30, BANR #20, FANG #4, HTGC #33, COF #20). The same construction is counted in
thirteen calls and omitted in three.

Two alternative explanations were tested and falsified:

- **Probe truncation.** The TFG-0 probe clipped Operator text at 650 characters. The three omitted
  segments are 463 / 421 / 482 characters, and their handoff clauses begin at offsets 372 / 351 /
  412 — all well inside the clip. Counted segments run longer (LTH #10 at 557, OCSL #29 at 490).
- **A deliberate "first handoff is not a separator" convention.** Contradicted by the thirteen
  counted first handoffs, and by the architecture freeze §4.3, which explicitly admits a
  first-question handoff before Q&A is established.

The measurement is reproducible end to end from a clean network fetch by
`research/earnings_intelligence/e3/tfg1_separator_falsifier_measurement.py`, which re-derives
16/16 canonical byte replay, 110 frozen vs 113 detected separators, 0 false negatives, and the
three omissions with their questioner class. It is measurement evidence only — nothing imports
it, it is not the TFG-1 compiler implementation, and it never reads a holdout revision.

A completeness sweep confirms nothing else is missed: every housekeeping segment the predicate
rejects is followed by IR or management at call open or close, never by an analyst.

## 4. Why this stops the wave

Correcting the omission changes the frozen development truth:

- structural separators **110 → 113**
- direct questioners **95 → 97** (ARRY #31 → Joe Osha, KREF #15 → Tom Catherwood, both exact)
- explicit full-name proxy **6** (unchanged)
- source-supported questioners **101 → 103**
- unresolved questioners **9 → 10**
- source-clean calls **10 → 9**

`MBLY/2026Q2` leaves the source-clean set. Its first question handoff (#21) names Joshua Buchalter,
but the next structured speaker is the placeholder `Speaker 4` whose first utterance is
"This is Lanny on for Josh" — a structured placeholder with first-name-only self-identification.
That is precisely the frozen unresolved class already recorded for TRVI #46/#58/#65 and BANR #71,
and the frozen proxy law admits a proxy only when the next structured speaker is a **full name**.
Under the all-or-nothing publication law TFG-1 is explicitly denied authority to relax, MBLY must
therefore refuse.

So a call the frozen receipt lists as source-clean cannot produce non-empty full-call
reconstruction under the correctly implemented frozen law. The dispatch's stop condition — *"If any
dev source-clean call fails, separator precision/recall misses … STOP and return the falsifier. Do
not rescue."* — is met.

Implementing the gold literally would also be actively wrong: segments preceding the first admitted
boundary fall outside every exchange window, so treating #21/#31/#15 as non-separators silently
discards the entire first analyst exchange of those three calls — the span loss across a real
question handoff that the separator law exists to prevent.

## 5. Not rescued

No exclusion rule was invented to make MBLY pass. No edit distance, nickname map, initials
expansion, first-handoff exemption, external biography or model call was added. No compiler source
was modified. Production revision admission remains AAPL-only.

## 6. Holdout preserved

The eight frozen ranks 17–24 remain **unopened**: no body, speaker metadata, Operator text or
derived feature has been fetched or inspected, and no compiler has been run against them. The
implementation head was never frozen, so unsealing would have been unlawful regardless.

This matters beyond bookkeeping: the holdout is single-use and explicitly non-replaceable. Spending
it against a development baseline whose own gold is inconsistent would destroy the only unseen
format evidence TFG owns, with no lawful substitute.

## 7. What Sol is asked to rule

1. Whether the frozen development adjudication is amended to 113 separators / 97 direct / 6 proxy /
   10 unresolved / 103 supported, with the source-clean set reduced to the nine calls listed in the
   receipt.
2. Whether `MBLY/2026Q2` is reclassified source-conflicted, with its expected TFG-1 failure being
   the unresolved-questioner class at #21.
3. Whether TFG-1 then re-runs as a fresh implementation wave against the amended gold, holdout still
   sealed.

Until that ruling, no implementation is frozen, the holdout stays sealed, E3-C remains open and
E3-P remains locked.
