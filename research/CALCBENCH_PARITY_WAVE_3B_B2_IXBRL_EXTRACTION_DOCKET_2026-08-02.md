# Calcbench Parity — Wave 3B-B2 iXBRL Extraction

**Canonical implementation handoff for Wave 3B-B2**

**Date:** 2026-08-02

**Status:** implementation complete; release candidate passed the local evidence
gates below

## Outcome

Wave 3B-B2 turns one exact, already-retained SEC filing-package member into a
bounded immutable XBRL extraction.  The output identity uses the `ffxbrl_`
namespace and commits the filing package, selected member receipt, parser
profile, byte spans, contexts, units, continuations, facts, diagnostics,
coverage, and explicit nonclaims.

This is a clean-room source-evidence layer.  It does not fetch a filing, resolve
a taxonomy, validate a calculation linkbase, mutate Company Facts, or assert
that one document represents a complete filing.  Unsupported Inline XBRL
transforms remain visible facts with no canonical value; they are never guessed
or silently discarded.

## Contract boundary

The public builder accepts exactly:

1. one validated `fundamental_forensics.filing_package/v1` object;
2. one safe member name whose package inventory state is `stored`; and
3. the exact retained member bytes.

Before parsing, the builder revalidates the package and requires the supplied
bytes to match the selected member's receipt-bound SHA-256 and byte length.
Parsing is offline and in memory.  It performs no network, filesystem, object
store, scheduler, API, UI, or raw-ledger work.

Canonical restore validates exact object shapes and content-derived IDs.  A
separate source-verification operation requires the external filing package and
exact retained bytes, reparses them, and compares the complete semantic
artifact.  Observed parser-library and runtime-version strings remain in the
artifact as provenance but are excluded from semantic replay; the pinned parser
profile, algorithm fingerprint, and transform registry remain replay authority.
The content ID is not a signature and cannot prove that an external archive
object still exists.

Deserializing an `ffxbrl_` record proves only canonical shape, internal
derivations, and content-addressed identity.  A caller can recompute an ID for
fabricated source-derived text just as it can for any unsigned content object.
Downstream attestation must therefore call source verification with the exact
package and retained member bytes; restore alone never upgrades an artifact to
source-verified authority.

## Parser and provenance laws

- Admit only bounded UTF-8 XML/XHTML.  Do not use HTML recovery.
- Reject DTDs, entities, external resolution, XInclude, NULs, duplicate
  attributes, malformed XML, unbound QNames, invalid references, and cap
  breaches.
- Never load schemas, linkbases, stylesheets, images, XSLT, or remote transform
  registries.
- Preserve the exact member SHA-256 and exact multibyte byte-range spans for
  emitted source objects, so every span can be sliced deterministically from the
  receipt-bound member.
- Preserve document-local context, unit, and continuation identities; bind
  stable internal IDs to the package, document, source digest, XML identity,
  and source span.
- Require one global document ID namespace across markup, contexts, units,
  facts, references, and continuations; valid period shapes; bounded dimensions
  and measures; and an acyclic single-owner continuation graph.
- Preserve XML-decoded fact text plus exact source spans, context/unit
  references, decimals/precision, Inline XBRL format, sign, scale, nil,
  language, hidden ancestry, excluded text, continuation chain, and fraction
  components.
- Apply only a pinned local transformation whitelist.  Any other transform has
  `unsupported_transform` status and a null canonical value.
- Derive every count and coverage boolean.  Caller-provided coverage is never
  trusted.

## Required nonclaims

The v1 artifact must keep these boundaries explicit:

- selected member byte verification does not prove the whole package is stored;
- selected member fact inventory does not prove filing completeness;
- parsed contexts and units do not establish taxonomy correctness;
- extracted dimensions do not establish presentation or relationship graphs;
- locally transformed values do not establish calculation consistency;
- no Company Facts match has been attested;
- no semantic XBRL attestation has been issued; and
- no trading, Prophet, or Neural Web authority is granted.

The admitted v1 envelope is deliberately narrower than general-purpose XBRL:
one UTF-8 document, Inline XBRL 1.1 only for inline documents, at most 5,000
contexts, 2,000 units, 10,000 continuations, 10,000 facts, and continuation
chains no longer than 16.  DTS, taxonomy, schema, linkbase, and Inline Document
Set validation are false nonclaims.  Native-instance fact inventory is not
declared complete without DTS semantics.  Fraction numerator/denominator
transforms and nested fraction-component content fail closed in this wave.

The local transformation authority is limited to eight pinned functions from
the official [Transformation Registry 3](https://www.xbrl.org/Specification/inlineXBRL-transformationRegistry/REC-2015-02-26/inlineXBRL-transformationRegistry-REC-2015-02-26.html)
and [Transformation Registry 4](https://www.xbrl.org/Specification/inlineXBRL-transformationRegistry/REC-2020-02-12/inlineXBRL-transformationRegistry-REC-2020-02-12.html).
The structural profile follows [XBRL 2.1](https://www.xbrl.org/Specification/xbrl-recommendation-2003-12-31.pdf),
[XBRL Dimensions 1.0](https://www.xbrl.org/specification/dimensions/per-2011-11-20/dimensions-per-2011-11-20.html),
and [Inline XBRL 1.1](https://www.xbrl.org/Specification/inlineXBRL-part1/REC-2013-11-18%2Berrata-2026-07-14/inlineXBRL-part1-REC-2013-11-18%2Bcorrected-errata-2026-07-14.html),
within the explicit subset above.

## Acceptance gates

The focused suite must prove:

- exact package/member/receipt binding and altered-byte rejection;
- canonical immutable serialization and forged-ID rejection;
- exact UTF-8 byte spans and receipt-bound member hashing;
- instant, duration, and forever contexts plus explicit/typed dimensions;
- simple and compound units;
- non-fraction, non-numeric, fraction, supported non-numeric nesting, explicit
  fail-closed numeric nesting, hidden, nil, sign/scale, exclude, and
  continuation behavior;
- supported transform vectors and explicit unsupported-transform behavior;
- missing, duplicate, shared, cyclic, orphaned, and over-depth continuations;
- DTD/entity/external/XInclude/malformed/no-recovery rejection;
- node, depth, attribute, text, fact, context, unit, scale, and output caps; and
- proof that parsing performs no source fetching or ledger mutation.

The active `collector-registry` PR gate owns the low-level parser and immutable
extraction tests.  Adjacent SEC document-spine and filing-package suites remain
part of the release evidence because B2 adds a semantic extraction boundary on
top of their provenance contracts rather than replacing them.

Local release evidence on 2026-08-02:

- 155 focused parser and immutable-extraction tests passed;
- 634 Fundamental Forensics, SEC spine, and parser tests passed;
- the exact minimal-dependency collector-registry lane passed all 155 tests;
- the 147-job CI manifest validated as four balanced packs and all 11 CI-pack
  contract tests passed; and
- two independent adversarial re-audits reported no remaining P0/P1 parser or
  source-independent restore blocker.

## Exact next lane

Wave 3B-B3 now implements sealed `ffatt_` attestations. Each attestation binds
one immutable `ffpkg_` package and one source-verified `ffxbrl_` extraction to
explicit fact evidence, coverage clocks, and controlled object-store authority.
Only that layer may assert narrowly scoped semantic or Company Facts matches.

After B3, `ffqsv2_` query snapshots can carry attested fact dependencies into a
Verified History API and provenance-first comparison UI.  Until then, the
existing `ffqs_` surface remains an immutable query snapshot—not a claim of
filing-complete history.
