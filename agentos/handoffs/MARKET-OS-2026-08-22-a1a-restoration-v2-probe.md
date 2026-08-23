---
workstream: "WS:MARKET-OS"
session: claude/a1a-restoration-v2-receipt
model: codex
ended_because: complete
mission: >
  Under Sol's semantic-v2 restoration ruling, execute exactly one authenticated
  owner-scoped temporary Portfolio create, exact-receipt delete, same-id semantic
  restore without timestamp inputs, and permanent cleanup; then prove the sealed
  canonical Portfolio and Watchlist baselines remain exact across Macro and Terminal.
state_before: >
  DEC:MARKET-OS-A1A-RESTORATION-EQUALITY-EXCLUDES-SERVER-TIMESTAMPS was merged in
  PR #6280, but its required production probe had not run. The designated authenticated
  account held the sealed 13-row canonical Portfolio fixture, all 13 rows open, one
  duplicate group with one extra row, and four Watchlists with 134 memberships. No
  canonical Portfolio deletion was authorized; Scene 9 and A1B remained prohibited.
changed:
  - path: "Authenticated production semantic-v2 restoration probe"
    what: >
      Created one controlled explicit-id temporary Portfolio row, sealed it, deleted it
      with an exact returned-row receipt, restored the same identity and semantic fields
      through the existing authenticated owner-scoped path while omitting created_at and
      updated_at, proved that only those server timestamps changed, and permanently
      deleted the probe with another exact returned-row receipt. No canonical Portfolio
      row and no Watchlist row was mutated.
  - path: "agentos/workstreams/WS-MARKET-OS.md"
    what: >
      Records the successful semantic-v2 probe, exact immediate and delayed cleanup,
      and the remaining fresh Sol authorization gate without advancing A1A to done.
  - path: "agentos/handoffs/MARKET-OS-2026-08-22-a1a-restoration-v2-probe.md"
    what: >
      Preserves the privacy-safe production receipt, verifier caveats, authority boundary,
      and exact next action for a fresh session.
verified:
  - claim: "The semantic-v2 ruling was durable before any production write"
    command: >
      git log -1 --oneline --
      agentos/decisions/DEC-MARKET-OS-A1A-RESTORATION-EQUALITY-EXCLUDES-SERVER-TIMESTAMPS.md;
      inspect WS:MARKET-OS restoration law on fresh origin/main
    result: >
      PR #6280 is merged at 4c7a45ad2236. The decision and workstream require exact id,
      owner, semantic fields, multiplicity, product conformance, Watchlists, and ordered
      row ids while excluding only created_at and updated_at from A1A restoration equality.
  - claim: "The action-time authenticated baseline was exact before the temporary write"
    command: >
      Macro WatchStore authenticated cloud read plus Terminal no-store GET /api/portfolio
      and /api/watchlist; SHA-256 comparison with the sealed product-specific canonicalizers
    result: >
      Both products returned 13 Portfolio rows, 13 open and zero closed. Macro's authoritative
      semantic-v2 seal was d854b4ec4269587eeec5e681af3c8c786e4cd7c34f475598eab9c60bc4df3870;
      the shared Macro-Terminal semantic multiset seal was
      98150c7ad9e542572c7c43803eafe38a6528ce8a3f99e7348e85bd185d629a42;
      and the separate ordered-id seal was
      3acc460d78a53c7b7118fdd05b5bfb94ec47273a49d11c7644613c8e0bb71384.
      Duplicate multiplicity was one group and one extra row. Macro was cloud/ready with
      no warning and every row owner matched the authenticated user.
  - claim: "One temporary row was created with exact owner and semantic identity"
    command: >
      Existing authenticated owner-scoped Supabase insert into portfolio_positions with
      one chosen explicit id and known semantic fields, omitting both server timestamps;
      exact single-row receipt, durable reread, and cross-product canonical comparison
    result: >
      The insert and durable reread each returned exactly one row, population became 14,
      owner matched, and the semantic fingerprint was
      28784656ca7accdc34ce4a4060e8321882b7517712c3718f4db274f6fe8a3071.
      Macro and Terminal agreed on the 14-row semantic seal
      51bd46da7d481b4c234a40c0e5c8ee2b1f57a390d5af89a30229ec57904850bf
      and ordered-id seal fa27c45fc3a223ae4cd1fe8816d5d40c24a11f1d05b9d8987586b5495193e14d;
      removing the probe from either product reproduced the sealed canonical 13-row
      semantic and ordering baselines. Both Watchlist seals remained exact.
  - claim: "The temporary row passed exact delete and semantic-v2 same-id restoration"
    command: >
      First owner-and-id-scoped delete with select-star one-row receipt; direct absence
      and population checks; authenticated insert with the same explicit id and semantic
      fields but no created_at or updated_at; exact receipt, durable reread, and field-key
      comparison to the sealed create
    result: >
      The first delete returned exactly the created row, direct absence was zero, and
      population returned to 13. Restore returned exactly one row with the same id, owner,
      and semantic fingerprint 28784656ca7accdc34ce4a4060e8321882b7517712c3718f4db274f6fe8a3071.
      The returned field set differed from the intended input set only by the two generated
      timestamp fields; both timestamp values changed and the full row changed, while every
      v2 identity and semantic field stayed exact. Macro and Terminal reproduced the original
      14-row shared semantic seal, ordered-id seal, and probe index exactly.
  - claim: "A verifier-only hash-order false red was identified without masking product drift"
    command: >
      Compare the direct restore fingerprint canonical key order with the first Macro probe
      verifier's object insertion order, then rerun a read-only SHA-256 over the exact
      semantic-v2 key order
    result: >
      The first verifier serialized the same fields in a different JSON key order and alone
      reported a different hash. Row count, owner, product semantic multiset, ordered ids,
      probe index, canonical remainder, timestamps, and both Watchlist seals were already
      exact. The corrected read-only canonicalizer returned the sealed probe fingerprint
      exactly; no production field or product disagreement existed.
  - claim: "Every harness failure before final cleanup was explicit and non-destructive"
    command: >
      Inspect the browser-side exception before a client method call; inspect the Supabase
      schema-cache error and empty mutation receipt for the non-canonical table name; verify
      the restored probe remained present before using the product adapter's canonical
      portfolio_positions table
    result: >
      One local invocation stopped before any database request because the async client
      accessor was not awaited. The next request named a nonexistent public.portfolio table
      and returned an exact schema-cache error with no row receipt and no mutation. The probe
      remained exactly present. Neither result was ambiguous or partial, and neither changed
      Portfolio or Watchlist population.
  - claim: "The restored probe was permanently deleted with an exact receipt"
    command: >
      Authenticated delete from portfolio_positions filtered by both the sealed temporary id
      and authenticated owner id, returning select-star; compare the returned full-row and
      semantic hashes to the restored row; direct id absence and exact population counts
    result: >
      Exactly one row returned. Its full-row receipt hash
      6a526ca49a333b4faac028a74bbdff42f2f6ae1a2783d617e8a77400ade29873
      matched the restored row, its semantic fingerprint matched the sealed create, direct
      absence count was zero, and authenticated Portfolio population was exactly 13.
  - claim: "Immediate cleanup reproduced every Portfolio and Watchlist baseline across both products"
    command: >
      Fresh Macro WatchStore cloud pull and Terminal no-store /api/portfolio plus
      /api/watchlist reads; compare counts, probe absence, semantic-v2 multiset, ordered ids,
      duplicate multiset, owner, authority state, and independent Watchlist seals
    result: >
      PASS: Macro and Terminal each returned 13 open and zero closed rows with the probe
      absent. Macro semantic-v2 was d854b4ec4269587eeec5e681af3c8c786e4cd7c34f475598eab9c60bc4df3870;
      both products shared 98150c7ad9e542572c7c43803eafe38a6528ce8a3f99e7348e85bd185d629a42,
      ordered ids 3acc460d78a53c7b7118fdd05b5bfb94ec47273a49d11c7644613c8e0bb71384,
      and duplicate seal 6b8dc6973f35731d213875d640c3a53216368c833ce3d19f8bfa3532620d1c87.
      Macro's four-list/134-membership seal was
      06f696f072d6ccc3db939081064f900af73179ef49183ca5720f202353ca0fac;
      Terminal's independent four-list/134-membership seal was
      0c018c4a04bd13e3af5969e824f17da1407fd4711622dc445ad49d31b973800b.
      Macro remained cloud/ready with no warning and exact ownership.
  - claim: "The normal reconciliation window did not reveal delayed drift"
    command: >
      Wait 15 seconds, then repeat the full authenticated Macro pull and Terminal no-store
      Portfolio and Watchlist matrix with the same canonicalizers
    result: >
      PASS: every delayed count, state, semantic seal, ordered-id seal, duplicate seal,
      owner check, probe-absence check, and product-specific Watchlist seal was identical to
      the immediate cleanup receipt.
  - claim: "The production authority and privacy boundary was preserved"
    command: >
      Compare the action log to Sol's authorization and scan the durable receipt for private
      fixture values, authentication material, Watchlist membership, and prohibited actions
    result: >
      No canonical Portfolio row, Watchlist row, product code, schema, authentication state,
      or private fixture value was changed or published. Scene 9 was not executed, A1B was
      not started, and A1A was not marked done. This receipt contains only counts, state,
      public field names, and cryptographic seals.
  - claim: "The durable Agent OS receipt satisfies the fail-closed record contract"
    command: >
      python3 scripts/agentos.py validate; python3 scripts/agentos.py compile-context
      --workstream MARKET-OS --json; python3 -m json.tool on the compiled bundle;
      git diff --check
    result: >
      Agent OS validated 574 records with zero errors, the compiled context_bundle.v1
      resolved this new handoff, the bundle parsed as valid JSON, and the two-file records
      diff had no whitespace error. Existing cross-store and phantom-path warnings remained
      advisory and outside this Market OS receipt.
unverified:
  - claim: "The remaining authenticated A1A production matrix passes"
    what_would_verify: >
      After fresh action-time Sol authorization, recapture the sealed baselines, evacuate the
      13 canonical rows, execute the true-zero, one-position, all-unsized, mixed-sized,
      degraded-last-good, first-read-failure, conformance, and privacy states, then restore
      the fixture under semantic-v2 and repeat immediate plus delayed cleanup proof.
  - claim: "Sol accepts A1A as done"
    what_would_verify: >
      Sol reviews the final complete authenticated production matrix and explicitly accepts
      A1A. This probe receipt alone does not advance the workstream to done.
unresolved:
  - "A1A remains in_progress; no canonical row has been deleted under this probe authority."
  - "Fresh Sol action-time destructive authorization is required before canonical evacuation."
  - "A1B remains blocked and was not started."
next_actions:
  - >
    Return this semantic-v2 probe receipt to Sol and request fresh action-time authority to
    delete exactly the sealed 13 canonical Portfolio rows for the remaining A1A matrix and
    restore them under DEC:MARKET-OS-A1A-RESTORATION-EQUALITY-EXCLUDES-SERVER-TIMESTAMPS.
  - >
    After authority, recapture Macro and Terminal semantic-v2, ordered-id, duplicate, and
    independent Watchlist seals before the first canonical delete; stop on any discrepancy.
  - >
    Execute only the remaining commissioned A1A states, clean every temporary row, restore
    the canonical fixture, prove immediate and delayed conformance, and return the final
    acceptance packet to Sol without marking A1A done or starting A1B.
do_not_redo:
  - "Do not repeat this semantic-v2 restoration probe; it passed and the temporary row is durably absent."
  - "Do not repeat PD1 mutation machinery; its accepted durable mutation and failure-honesty proof remains sufficient."
  - "Do not delete a canonical Portfolio row without fresh Sol action-time authority."
  - "Do not broaden the v2 exception beyond created_at and updated_at, or attempt to preserve either timestamp."
  - "Do not treat JSON key insertion order as product field drift; use the exact sealed canonicalizer before adjudication."
  - "Do not expose private Portfolio or Watchlist values; counts and fingerprints are sufficient."
danger_areas:
  - "The production table is portfolio_positions; a similarly named public.portfolio table does not exist."
  - "Semantic-v2 and product-conformance hashes require fixed field names, field order, numeric normalization, and multiset sorting; a different JSON insertion order produces a false mismatch."
  - "Macro and Terminal expose different field casing and independent Watchlist representations; normalize only through the sealed product-specific canonicalizers."
  - "Timestamp regeneration can affect incidental product order, so the authoritative ordered-id seal remains a separate hard invariant during canonical restoration."
prs: [6257, 6280]
decisions:
  - "DEC:MARKET-OS-A1A-RESTORATION-EQUALITY-EXCLUDES-SERVER-TIMESTAMPS"
---

# A1A authenticated production — semantic-v2 restoration probe

Verdict: **PASS / CLEAN / RETURN TO SOL.** The bounded one-row restoration proof
required by Sol's semantic-v2 ruling passed under the existing authenticated
owner-scoped production path. Identity, ownership, every semantic field, product
order, duplicate multiplicity, and both product-specific Watchlist baselines remained
exact; only the two server-generated timestamps changed, as the ruling requires.

The temporary row is durably absent. Immediate and delayed authenticated reads both
returned the original sealed 13-row canonical Portfolio fixture across Macro and
Terminal. No canonical Portfolio row was deleted, and no Watchlist mutation occurred.

This proves the restoration contract; it does not authorize the broader evacuation.
Return to Sol for fresh action-time destructive authority. Scene 9 remains prohibited,
A1B remains blocked, and A1A remains `in_progress` until the full production matrix is
executed and Sol explicitly accepts it.
