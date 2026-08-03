# Calcbench Parity — Wave 3B Read-Only Attested-History Operator

**Canonical implementation handoff**

**Status:** foundation only. It has no production issuer packet, no enabled
schedule, no dedicated R2 read-only credential, and no publication path.

## Outcome

`scripts/run_fundamental_forensics_attested_history.py` is the first operating
surface above B4D. It is intentionally a private, read-only candidate factory:

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
private artifact upload. There is deliberately no `schedule:` trigger. The job
can run only on `refs/heads/main`, so its R2 secrets are never exposed to a
manually selected branch ref. It is ready to receive separate GitHub
`R2_RESEARCH_READONLY_*` secrets, mapped only to the
`FF_ATTESTED_R2_READONLY_*` runtime variables. It does not fall back to the
broad existing Research R2 credentials. The only existing protected environment
is the unrelated GitHub Pages deployment environment, so this inert lane does
not repurpose it as a credential boundary.

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

1. Create a separate R2 role restricted to exact GET/HEAD on the required
   private prefixes; deny put/delete/list.
2. Seal, review, and commit one real issuer packet with every listed source
   object and older-Submissions member.
3. Run manual preflight against that packet and inspect the private receipt.
4. Only then add a schedule trigger. Keep publication separate until its
   credential/lease/fencing policy is independently designed and tested.
