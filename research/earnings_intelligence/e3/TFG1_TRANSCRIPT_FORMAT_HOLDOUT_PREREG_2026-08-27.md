# TFG-1 — Unseen transcript-format holdout pre-registration

**Parent operation:** `tfg0-transcript-format-census-20260827-v1`  
**Future implementation operation:** TFG-1 (not yet commissioned)  
**State:** HOLDOUT LAW FROZEN BEFORE HOLDOUT BODY INSPECTION

TFG-0 has inspected its deterministic 16-revision development corpus. To prevent TFG-1 from becoming a phrase-fitting exercise over those same calls, this record freezes a separate source-format holdout before implementation begins.

## Holdout selection law

Use the exact TFG-0 eligibility and exclusion law against the same production `mastermind.tx-index/v1` snapshot used by the TFG-0 development corpus:

- advertised 64-hex transcript revision SHA required;
- call date 2026-05-01 through 2026-08-26 inclusive;
- transcript id `2026Q2` or `2026Q3`;
- exclude `AAPL`, `GOOGL`, `GOOG`, `CAT`, `BAC`, `SNOW`;
- compute `sha256("TFG0|" + pair + "|" + body_sha256)`;
- sort ascending `(selection_hash, pair)`.

The TFG-0 development corpus consumed ranks **1–16**. The TFG-1 unseen format holdout is ranks **17–24**, exactly eight revisions. Freeze their pair + advertised SHA in a selection receipt using index metadata only.

## Embargo

Neither the TFG-1 implementation worker nor Sol may inspect the eight holdout bodies, role vocabulary, Operator text, speaker metadata, current compiler output, or any derived structural feature before the TFG-1 implementation head is frozen and its development tests are green.

Metadata needed to freeze identity (pair, call date, revision SHA, selection hash) is allowed and does not count as body inspection.

If a holdout body later fails byte replay or its advertised SHA has changed, that slot records `SOURCE_REVISION_MISMATCH`; do not replace it with rank 25 or another cleaner source.

## Holdout use

After TFG-1 implementation is frozen:

1. byte-replay the eight exact held revisions;
2. run the frozen deterministic compiler without tuning;
3. report non-empty reconstruction/refusal per call plus hard safety results;
4. no repair may be made on the same implementation carrier after holdout results are observed and then call that same holdout an untouched pass. A failed holdout returns to Sol for a new method-hardening wave.

This holdout is **method-format validation only**. It is not the successor E3-C second-issuer production acceptance event and cannot unlock E3-P. The later full OOS event must still be selected under a fresh pre-registered completeness receipt after TFG-1 is accepted.
