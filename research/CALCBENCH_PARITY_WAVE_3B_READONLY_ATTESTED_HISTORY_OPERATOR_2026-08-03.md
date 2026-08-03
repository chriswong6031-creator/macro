# Calcbench Parity — Wave 3B Read-Only Attested-History Operator

**Canonical implementation handoff**

**Status:** foundation only. Dedicated-bucket read-only repository-secret names
have been verified, but there is no production issuer packet, enabled schedule,
live R2 preflight, publication path, or authority promotion. Presence of secret
names is not proof that any object has been read or written.

The verified read-only names are `R2_RESEARCH_READONLY_ENDPOINT`,
`R2_RESEARCH_READONLY_ACCESS_KEY_ID`,
`R2_RESEARCH_READONLY_SECRET_ACCESS_KEY`, and
`R2_RESEARCH_READONLY_BUCKET`. They are used only as the read-only side of the
controlled B4F activation; the seed writer never falls back to broad Research
Vault credentials.

## Outcome

`scripts/run_fundamental_forensics_attested_history.py` is the first operating
surface above B4D. It is intentionally an internal, read-only candidate factory:

```text
sealed ffqs_ + ffsecsrc_ packet
  -> B4D filing-package materialization
  -> B2 receipt-bound iXBRL extraction
  -> B3 source replay and attestation
  -> pinned Company Facts conversion
  -> B4D unique-candidate plan
  -> B4A prepare in memory
  -> bounded redacted Actions artifact
```

It has no source acquisition, SEC HTTP client, mutable latest lookup, storage
listing, state render, API route, public artifact, R2 write, immutable object
write, pointer update, notification, score, or Neural Web/Prophet authority.

## Sealed packet contract

The future production packet must live at
`config/fundamental_forensics/attested_history_operator.v1.json` and validate
against `contracts/fundamental_forensics_attested_history_operator.schema.json`.
It names exactly one v1 query snapshot, one source snapshot, and one issuer
filing packet. It must carry the complete archive member-state inventory, one
explicit iXBRL member, Company Facts paths, recent and every declared older
Submissions receipt/object pair, explicit conversion ceilings, and package
policy identity.

No packet is committed in this lane. Placeholder IDs are not a production
packet; a schedule must remain disabled until one real packet has been reviewed
and committed. In R2 mode the CLI accepts only that exact canonical repository
path; arbitrary packet paths are permitted only with the explicit hermetic
`--local-store` adapter. It captures the local file once, then compares those
captured bytes with bounded `git cat-file blob` reads of both `HEAD:path` and
`:path` before parsing. The parsed packet is therefore the exact byte sequence
bound to both authorities, rather than a later re-opened pathname. Git plumbing
is used by symbolic tree/index selector, so no SHA-1 versus SHA-256 assumption
is embedded in the operator.

## Read-only enforcement

The operator wraps the source store in `ReadOnlyStrictStore` before any B4D,
B2, B3, or B4A call. It permits only fail-closed exact reads. Listing, existence
checks, upload-time probes, and all writes fail. The receipt contains the
literal zero-write assertion:

```json
"publication": {
  "publication_performed": false,
  "pointer_advanced": false,
  "immutable_objects_written": false,
  "storage_write_attempts": 0
}
```

`prepared` means an in-memory B4A candidate was reconstructed and replayed. It
does not mean a snapshot was stored or published. Its candidate publication
clock is explicitly marked hypothetical; an eventual controlled publisher must
prepare again under its real clocks and its own authority.

An intercepted forbidden write is recorded as a nonzero *attempt* in a failed
receipt, while the backing write is never reached. Successful `prepared` and
`non_publishable` receipts require zero attempts.

The packet enters through an `O_NOFOLLOW` descriptor, regular-file `fstat`,
and max+1 bounded read with a post-read identity/size check. Both Git blob
streams are also bounded at max+1 bytes. The local receipt output path is
rejected if it resolves to or contains the local source-store root (or vice
versa). Successful workflow logs contain only a completion notice: the receipt
itself is never printed to logs.

Failure receipts are intentionally redacted but operationally useful. Their
stable phase enum is `packet_admission`, `packet_read`, `store_initialization`,
`materialization`, `binding_plan`, `candidate_prepare`, or `receipt_write`;
there is no generic execution bucket. The binding summary admits all eight
non-sensitive B4D materializer codes: `not_sec_companyfacts`,
`dimensions_known`, `selected_occurrence_not_in_companyfacts_conversion`,
`conversion_occurrence_differs_from_selected_leaf`,
`no_b3_attestation_binds_companyfacts_conversion`, `no_exact_b3_match`,
`ambiguous_exact_b3_matches`, and
`exact_b3_match_shared_by_selected_leaves`.

## Workflow state

`.github/workflows/attested-history-operator.yml` has only guarded manual
dispatch (`enable_readonly_preflight=false` by default), `contents: read`, and
review-only artifact upload. Because the repository is public, those Actions
artifacts are not confidential or canonical publication. There is deliberately
no `schedule:` trigger. The job can run only on `refs/heads/main`, so its R2
secrets are never exposed to a manually selected branch ref. It maps the verified repository
`R2_RESEARCH_READONLY_*` secret names only to
`FF_ATTESTED_R2_READONLY_*` runtime variables. It does not fall back to the
broad existing Research R2 credentials. No R2 write capability is used by this
operator.

The separate `.github/workflows/attested-history-aapl-seed.yml` workflow is the
only proposed bootstrap writer. It remains manual-only and main-only, has no
`schedule:`, and requires the protected `attested-history-seed` environment
before any dispatch. That environment now exists with one required reviewer
and a custom `main`-only deployment policy. It still lacks the only two new
writer secrets:
`R2_ATTESTED_HISTORY_SEED_ACCESS_KEY_ID` and
`R2_ATTESTED_HISTORY_SEED_SECRET_ACCESS_KEY`. Cloudflare's parent tokens may
include List under its dashboard Object Read/Object Read & Write roles. The
workflows locally mint at-most-30-minute children scoped to the single
`fundamental_forensics/` prefix; the writer child has exactly Get/Head/Put and
the reader child exactly Get/Head, with no List/Delete. The seed preflight must
use the separately issued `R2_RESEARCH_READONLY_*` parent against the same bucket
and prove conditional-write/readback behavior before SEC acquisition begins.

## Validation

`tests/test_fundamental_forensics_attested_history_operator.py` covers exact
packet shape, latest refusal, descriptor-bound packet ingress, production
canonical-path admission plus capture-before-replacement regression, exact
HEAD/index byte binding, local output/source-store separation, write/discovery
rejection, B4A in-memory prepare with the backing store write method
booby-trapped, a real B4D mixed-coverage plan (including its real
`selected_occurrence_not_in_companyfacts_conversion` diagnostic),
non-publishable zero-binding results,
bounded/redacted stable-subphase failures, exact receipt-schema conditionals
and count caps, non-leaking logs, and disabled workflow properties. The
existing B4D and B4A suites remain the deeper materialization, source-replay,
and binding correctness tests.

## Activation prerequisites

1. Merge the B4F code and CI wiring; do not dispatch from a branch or treat a
   local run as the production seed.
2. Confirm the existing protected `attested-history-seed` GitHub environment's
   reviewer and exact `main` branch policy, then add only the two
   environment-scoped writer secrets named above. Keep the already verified
   `R2_RESEARCH_READONLY_*` repository secrets read-only and separate.
3. Dispatch the manual AAPL seed on `main`. Its storage-control probe must
   prove absent-create conflict rejection, exact-version CAS, stale-CAS
   rejection, and separate read-only final-byte readback before it contacts the
   SEC.
4. Review the four non-confidential, review-only Actions files: seed receipt,
   zero-write preflight receipt, candidate operator packet, and bundle receipt
   binding their hashes to the exact GitHub run and dependency lock. A failure
   or an incomplete receipt stops here; no canonical/public serving state is
   permitted.
5. Review and commit one real issuer packet in a separate change, then run the
   existing manual read-only operator preflight against that committed packet.
6. Keep cron, API/UI exposure, Neural Web/Prophet authority, scores, and
   alerts disabled. Each would require its own policy, test, and promotion
   review; none follows automatically from a first issuer receipt.
