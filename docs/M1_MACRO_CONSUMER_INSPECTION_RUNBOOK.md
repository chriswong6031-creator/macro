# M1 Macro Consumer Inspection Runbook

## Purpose and authority boundary

This procedure produces a bounded, read-only evidence packet for the M1 Macro
consumers enumerated in one operator-supplied scope manifest. It does not change
launchd state, Git state, repository remotes, credentials, files inside a
checkout, runners, storage, or repository visibility.

The output is evidence for canonical carrier #6432. It does not decide
`KEEP_AUTHENTICATE`, `RETIRE_DUPLICATE`, or any other organizational action.
Those remain Sol/operator decisions. The inspector reports only whether every
row in the supplied manifest was inspected without an error; it cannot prove
that the manifest covers the entire cutover estate.

## Preflight

Before every real-host observation:

1. Re-pin the protected Sol Skillpack named by #6432 and record its exact SHA.
2. Fetch and record the exact current Macro `origin/main` SHA containing this
   inspector.
3. Re-read the current issue #6432 in full and verify that the bounded read-only
   host observation is still released.
4. Obtain a separate, receipted read-only scope census covering the selected
   current-user and system launchd domains, cron or other scheduler surfaces,
   and recently active jobs. Map every discovered Macro consumer one-to-one to
   a manifest row.
5. Stop on any scope collision, hostname mismatch, ambiguous consumer mapping,
   missing authority, or request for a persistent credential.

Do not repeat broad host archaeology. Do not infer completeness from the
illustrative manifest below.

## Ephemeral scope manifest

The manifest is temporary evidence input with schema
`macro.m1_consumer_scope.v1`. It is not a checked-in registry, scheduler,
authority map, or durable source of truth. Its top-level keys and every service
row are strict; unknown, missing, relative-path, wrong-host, foreign-user, or
duplicate values fail closed.

```json
{
  "schema": "macro.m1_consumer_scope.v1",
  "hostname": "EXACT_OUTPUT_OF_HOSTNAME_ON_M1",
  "services": [
    {
      "service_id": "com.example.macro-consumer",
      "domain": "gui/EXACT_DECIMAL_UID",
      "plist_path": "/absolute/path/to/com.example.macro-consumer.plist",
      "recent_evidence_paths": [
        "/absolute/path/to/an/operator-attested-receipt"
      ]
    },
    {
      "service_id": "com.example.system-macro-consumer",
      "domain": "system",
      "plist_path": "/absolute/path/to/com.example.system-macro-consumer.plist",
      "recent_evidence_paths": []
    }
  ],
  "scheduler_surfaces_checked": [
    "launchd-current-user",
    "launchd-system",
    "cron-and-other-schedulers"
  ],
  "recent_job_sources_checked": [
    "declared-launchd-streams",
    "operator-attested-receipts"
  ]
}
```

Only exact `system` or `gui/<current decimal uid>` domains are accepted. Plist
and recent-evidence paths must be absolute. Both coverage arrays must be
non-empty. Example rows are illustrative and are never an exhaustive consumer
inventory.

## Exact invocation

Create a mode-0600 temporary file, populate it from the separately receipted
scope census, and choose where the sanitized report is written:

```bash
scope_file="$(mktemp /tmp/m1-macro-consumer-scope.XXXXXX.json)"
chmod 0600 "$scope_file"
# Populate this 0600 temporary file from the separately receipted read-only
# launchd/scheduler/recent-job scope census; do not assume example rows are exhaustive.
python3 scripts/inspect_m1_macro_consumers.py \
  --scope-manifest "$scope_file" \
  --format json > /tmp/m1-macro-consumer-census.json
```

Use `--format table` only as a projection for human review. JSON is the
canonical machine-readable receipt. After recording the manifest digest and
sanitized return packet, remove the temporary manifest; never commit it.

## Evidence fields

- `schema`: always `macro.m1_consumer_census.v1`.
- `observed_at`, `hostname`: offset-aware observation time and bound host.
- `supplied_scope_sha256`: SHA-256 of the exact manifest bytes.
- `services`: deterministic service-ID order with launchd, plist, local Git,
  metadata-only recent evidence, hazard, and inspection-error fields.
- `environment_names`: names only; environment values are never reported.
- `remote_states`: bounded enums only: `canonical_ssh`,
  `canonical_https_anon`, `wrong_owner`, `other`, or `unknown`. Raw URLs and
  Git configuration values are discarded before report construction.
- `last_execution` and `last_execution_source`: the newest timestamp from an
  explicitly declared path's metadata. This is metadata-derived activity
  evidence, not proof of a successful job.
- `complete_for_supplied_scope`: true only when every manifest row was
  inspected without an error. There is deliberately no `complete_for_cutover`
  field.
- `scope_coverage_errors` and each service's `inspection_errors`: bounded error
  codes that require adjudication.

Exit `0` means the supplied rows were completely inspected. Exit `65` means
incomplete, malformed, missing, or ambiguous evidence: stop and return the
receipt to Sol. Hazards such as `wrong_owner` are evidence, not an automatic
migration decision.

## Secret and preservation law

Never put private-key bytes, tokens, `.env` contents, credential-helper values,
raw remote URLs, arbitrary environment values, SSH stderr, or complete process
environments into the manifest, report, issue, or chat. The inspector reads
environment names only and uses file metadata only for declared recent-evidence
paths; it never opens their contents.

The only child commands are exact read-only `/usr/bin/git` probes and exact
`/bin/launchctl print-disabled` / `print` probes. Mutation verbs, network Git
operations, foreign user domains, malformed labels, excessive output, and
timeouts are refused or fail closed before evidence can be accepted.

`/Users/chriswong/flow-ops-wt` is inspect-only. Its deliberate detached and
dirty state must never be normalized, cleaned, checked out, reset, fetched, or
otherwise changed. `com.macro.live-breadth` remains a retired-state evidence
subject, not a migration target. Native persistent-disabled spellings `true`
and `disabled` are both accepted; a missing or nonzero service-state probe does
not prove that a service is unloaded.

## #6432 return packet

Return exactly one sanitized packet containing:

1. protected Skillpack SHA and exact Macro code head;
2. exact inspector command, host, and offset-aware observation time;
3. supplied scope-manifest SHA-256;
4. independent scope-attestation receipt and digest;
5. census JSON SHA-256;
6. selected current-user/system domains;
7. scheduler surfaces and recently active job sources checked;
8. services discovered and one-to-one manifest mapping;
9. last-execution timestamp/source for each service, labeled metadata-derived;
10. unresolved inspection and coverage errors;
11. evidence-only hazards;
12. explicit confirmation that no service, Git, credential, runtime, runner,
    storage, or repository-visibility mutation occurred.

Only after Sol accepts this combined packet may #6432 decide the next bounded
migration wave. The inspector alone never authorizes private cutover.
