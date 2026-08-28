---
key: DELETE-BEFORE-ACK-NEEDS-AN-IN-FLIGHT-ASSERTION
claim: >
  A test suite that asserts only the FINAL state of a durable record cannot distinguish
  "cleared after the write was acknowledged" from "cleared before the write and rewritten
  on the failure path" — even though only the first is correct. Demonstrated directly:
  an eleven-test suite covering the Terminal onboarding preference outbox (success clears,
  failure keeps, throw keeps, result-error keeps, bounded retry, exhausted-record revival,
  legacy-shape tolerance, blocked storage) PASSED UNCHANGED against a mutation that moved
  `clearPendingPrefs()` to before the `updateUser` call. It passed because the failure
  branch re-writes the record at the end, so every post-hoc observation is identical. The
  difference is nonetheless the whole defect: with an up-front delete, a tab closed
  mid-request, a hung socket, or a process death loses the user's choice permanently. Only
  an assertion taken WHILE the write is in flight — reading the store from inside the
  injected writer, before resolving it — fails the mutation.
falsifier: >
  Exhibit a purely final-state assertion that distinguishes the two orderings without
  observing an intermediate moment: e.g. a durable store that records write ORDER (an
  append-only log or a version counter the test can read afterwards), which would make the
  early delete visible post-hoc. In that design this claim does not apply. It also does not
  apply where the failure path deliberately leaves the record absent, since then the final
  states genuinely differ.
so_what: >
  When reviewing or writing tests for ANY acknowledge-before-delete contract — outboxes,
  idempotency keys, offline queues, optimistic-UI rollback, two-phase local state — do not
  accept "the record is still there after a failure" as proof of ordering. Require one test
  that observes the store DURING the in-flight window, by injecting a writer that reads the
  store and returns a promise the test resolves manually. Cost is about ten lines. Without
  it a suite can look thorough, pass a mutation check on every other property, and still not
  pin the single invariant the module exists to enforce. Generally: mutation-test the
  ORDERING of side effects, not only their presence — and when a mutation passes, treat that
  as a hole in the tests rather than evidence the mutation was harmless.
kind: landmine
verified_at: 2026-08-19
verified_by: >
  terminal/lib/onboardingPrefsOutbox.ts (deliverPendingPrefs: read -> attempt -> clear only
  on confirmed success) and terminal/lib/__tests__/onboardingPrefsOutbox.test.ts. Measured
  in mastermind-terminal PR #434: with `clearPendingPrefs()` inserted before the retry loop,
  the eleven original tests reported "Tests 11 passed (11)". After adding the test
  "the record is still present WHILE the write is in flight" (which reads the store from
  inside the injected updateUser and asserts before resolving a manually-held promise), the
  same mutation reports "Tests 1 failed | 11 passed (12)", failing exactly that test.
scope: [terminal, method]
confidence: verified
---

## Detail

This was found by accident, which is the point. The mutation was run expecting a confirmation and
returned a clean pass — and the honest reading of a passing mutation is *"my tests do not cover
this"*, not *"the mutation was benign"*.

The mechanism is worth stating precisely, because it generalises past this module. The correct
implementation is `read → attempt → clear-on-success`; the defective one is
`read → clear → attempt → rewrite-on-failure`. After either sequence terminates:

| terminal state | correct impl | defective impl |
|---|---|---|
| success | record absent | record absent |
| failure | record present | record present |

Identical. The sequences differ **only during the await**, and that window is exactly where the real
failures live — a closed tab, a hung request, a killed process. A test that never looks inside the
window is structurally incapable of telling them apart, no matter how many properties it checks.

The technique that closes it is small and reusable: inject the writer, have it read the durable store
and stash what it saw, return a promise the test controls, assert the stash *before* resolving.

```
let release; const inFlight = new Promise(r => { release = r; });
let seen = "not-observed";
const p = deliver(() => { seen = readStore(); return inFlight; });
await Promise.resolve();          // let the call happen
expect(seen).toEqual(RECORD);     // survives an interruption at this instant
release(OK);
expect((await p).status).toBe("delivered");
expect(readStore()).toBeNull();   // …and only now is it gone
```

A related trap sits one layer up and was caught the same way: the first version of the outbox used a
*lifetime* attempt cap, so a record that failed three times could never be delivered again. That
reads as "bounded retry" and behaves as "silently abandoned after three failures" — the same class of
loss the module exists to prevent, merely slower. The cap belongs to a delivery PASS; a later mount
must always get a fresh budget.
