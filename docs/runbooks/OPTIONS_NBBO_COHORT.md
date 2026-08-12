# Host-private same-basis OPRA NBBO cohort

Status: accrual infrastructure only. It grants no signal, score, rank, issue,
size, trade, publication, Prophet, Neural Web, training, or completion authority.

## Frozen basis

Do not change these rules in place. Entry is the first valid OPRA NBBO ask at or
after the immutable trigger. Exit is the first valid bid at or after the
immutable terminal. Open contracts receive an expiry terminal at exactly 15:55
America/New_York on the last tradable session. The 600-second fence measures
quote event to actual response completion; it is not a time-to-first-quote cap.
One contract and a $0.65 fee per side are fixed. Raw source and competitor bytes
remain under the private root; git may receive aggregate receipts only.

## Producer contract

This prerequisite ships with every event producer and every successful capture
producer **unarmed**. There is no environment variable, host config, or
first-seen digest that can arm one. Until a reviewed adapter pins the exact
per-system rule digest, source schema, authentication basis, and evidence
validator in code, event append and successful capture append fail closed. The
scheduled lane can therefore record only explicit `unavailable` receipts and
cannot claim an eligible outcome.

The future adapter interface does not infer event clocks from date-only history,
page text, file mtime, or the poll clock. An audited producer must first write a canonical
`options.prospective_nbbo_cohort_event/v1` object with an exact `event_at`, its
actual `available_at`, exact OCC contract, unchanged decision/lifecycle rule
digests, and a receipt for exact private evidence bytes. Its private envelope
replays the event ID, system, stable signal ID, exact OCC contract, event and
availability clocks, rule digests, terminal/enrollment linkage, and exact
source-object pointer. Once that adapter is armed in reviewed code, append it
with:

```sh
PRIVATE_ROOT="$HOME/.mastermind_private/options_nbbo_cohort_v1"
python -m scripts.capture_options_nbbo_cohort \
  --private-root "$PRIVATE_ROOT" \
  --append-event "$PRIVATE_ROOT/inbox/event.json" \
  --event-evidence "$PRIVATE_ROOT/inbox/event-evidence.json"
```

Both JSON inputs must already be owned `0600` regular files with one hard link
under the private root (normally its owned `0700` `inbox/`). Symlinks,
world-readable files, repository paths, and inputs outside the private root are
rejected before any bytes are parsed.

Date-only Prophet or competitor history is ineligible. A canonical lifecycle
row without a precise terminal clock is also ineligible. The internal expiry
producer derives its event clock only from the frozen calendar rule; its
availability clock is always the real runtime clock. With event producers
unarmed, there can be no admitted enrollment for it to terminalize.

Each five-minute producer poll also emits one
`options.prospective_nbbo_capture_receipt/v1` per comparison system. A successful
receipt binds its receipt ID, exact clocks, disposition, exact private source
object, and either new enrollment event IDs, an
authenticated zero-new-call observation, or a source-proven selector abstention.
MomoEdge silence must be `no_new_calls_observed`, never inferred abstention.
Append a producer receipt with:

```sh
python -m scripts.capture_options_nbbo_cohort \
  --private-root "$PRIVATE_ROOT" \
  --append-capture-receipt "$PRIVATE_ROOT/inbox/capture.json" \
  --capture-evidence "$PRIVATE_ROOT/inbox/capture-evidence.json"
```

The empty-safe scheduled lane records `unavailable` for both systems when no
precise/authenticated producer is installed. Those rows prove scheduler
liveness but do not cover a slot, do not count as abstention, and cannot make an
outcome eligible.

MomoEdge remains deliberately unarmed in this slice. Anonymous signal access is
not an authenticated producer. The next adapter must be a user-session browser
companion running beside the subscribed page: it may export debranded exact
result bytes (stable active-card identity, exact option fields, event clock, and
actual availability clock) only to a private localhost receiver. It must never
export or persist tokens, cookies, localStorage, or credentials. Until that
adapter and its evidence validator are reviewed, every MomoEdge slot remains
unavailable and competitor coverage stays zero.

## Coverage and eligibility

The private snapshot enumerates every 300-second RTH slot for both MastermindX
and MomoEdge. A finalized session is covered only when the intersection of
authenticated successful slots is at least 95%, its maximum gap is no more than
900 seconds using actual authenticated completion clocks plus the RTH open and
close edges, and every observed new call reconciles exactly once to an enrollment
event. A gap over 900 seconds excludes that session from both systems. A fully
silent finalized session is still materialized and excluded. Quote-
complete outcomes from uncovered sessions remain visible as incomplete with
`UNCOVERED_CAPTURE_SESSION`; they never enter the completion denominator.

Theta v3 requests use `interval=tick` and retain the exact top-level flat JSON
row array. Interval buckets are forbidden because an interval returns its last
quote and could skip the true first OPRA NBBO after the boundary. Validity is
role-side specific: entry requires a positive ask and ask size with an official
firm condition and known non-empty exchange; exit applies the same checks to the
bid. A missing/non-firm opposite side does not discard an otherwise valid
selected side, while a genuinely crossed two-sided row is rejected.
Every attempted quote request must carry its real pre-request clock and exact
HTTP response bytes. Re-serializing a parsed JSON value is not raw retention and
is rejected.

The prerequisite runner's unconditional `--record-unavailable-cycle` action
must not run beside a later authenticated producer. The adapter slice replaces
that action with a deadline settler: append exact event objects first, then one
capture receipt per system and slot; only at the settlement deadline may it
append `unavailable` for a system/slot with no durable producer receipt. A
browser response cache or fallback object cannot cover a slot.

## Install and verify on M1

Use the dedicated clean checkout `/Users/chriswong/options-nbbo-ops-wt`; never
install this lane into the shared `/Users/chriswong/flow-ops-wt`. The private
root must be an owned `0700` directory outside the repository; ledgers and
objects are owned `0600` regular files. Theta Terminal must serve v3 locally at
`127.0.0.1:25503`.

After the PR merges, set `MERGE_SHA` to its exact merge commit and build a clean
adjacent checkout. Do not reuse or update the active directory in place:

```sh
MERGE_SHA=<exact-40-character-merge-sha>
SOURCE_REPO="$(git config --get remote.origin.url)"
STAGE="$(mktemp -d /Users/chriswong/options-nbbo-ops-stage.XXXXXX)"
git clone --filter=blob:none --no-checkout "$SOURCE_REPO" "$STAGE"
git -C "$STAGE" fetch origin main
git -C "$STAGE" checkout --detach origin/main
git -C "$STAGE" merge-base --is-ancestor "$MERGE_SHA" HEAD
test -z "$(git -C "$STAGE" status --porcelain)"
git -C "$STAGE" rev-parse HEAD
shasum -a 256 \
  "$STAGE/ops/launchd/run_options_nbbo_cohort_loop.sh" \
  "$STAGE/ops/launchd/com.mastermind.optionsnbbocohort.plist" \
  "$STAGE/engine/options_nbbo_cohort.py" \
  "$STAGE/contracts/options/options.prospective_nbbo_cohort.v1.schema.json"
```

Stop the label before the adjacent swap. Preserve the prior checkout as a
rollback directory; do not delete it during installation:

```sh
LABEL=com.mastermind.optionsnbbocohort
AGENT="$HOME/Library/LaunchAgents/$LABEL.plist"
launchctl bootout "gui/$(id -u)" "$AGENT" 2>/dev/null || true
if test -e /Users/chriswong/options-nbbo-ops-wt; then
  mv /Users/chriswong/options-nbbo-ops-wt \
    "/Users/chriswong/options-nbbo-ops-wt.rollback.$(date +%Y%m%d%H%M%S)"
fi
mv "$STAGE" /Users/chriswong/options-nbbo-ops-wt
install -m 600 \
  /Users/chriswong/options-nbbo-ops-wt/ops/launchd/com.mastermind.optionsnbbocohort.plist \
  "$AGENT"
plutil -lint "$AGENT"
launchctl bootstrap "gui/$(id -u)" "$AGENT"
launchctl kickstart -k "gui/$(id -u)/$LABEL"
```

Prove the installed checkout is the exact merge or a descendant, remains clean,
and that the installed plist/runner bytes match git. Save this output with the
private deployment receipt:

```sh
OPS=/Users/chriswong/options-nbbo-ops-wt
INSTALLED_SHA="$(git -C "$OPS" rev-parse HEAD)"
git -C "$OPS" merge-base --is-ancestor "$MERGE_SHA" "$INSTALLED_SHA"
test -z "$(git -C "$OPS" status --porcelain)"
test "$(shasum -a 256 "$OPS/ops/launchd/run_options_nbbo_cohort_loop.sh" | awk '{print $1}')" = \
  "$(git -C "$OPS" show "$INSTALLED_SHA:ops/launchd/run_options_nbbo_cohort_loop.sh" | shasum -a 256 | awk '{print $1}')"
test "$(shasum -a 256 "$AGENT" | awk '{print $1}')" = \
  "$(git -C "$OPS" show "$INSTALLED_SHA:ops/launchd/com.mastermind.optionsnbbocohort.plist" | shasum -a 256 | awk '{print $1}')"
launchctl print "gui/$(id -u)/com.mastermind.optionsnbbocohort"
tail -f /tmp/optionsnbbocohort.stdout.log /tmp/optionsnbbocohort.stderr.log
```

Verify `HEAD.json` and its referenced snapshot only inside the private root.
The initial honest state is zero covered sessions and zero eligible outcomes.
Do not publish raw ledgers, snapshots, evidence, provider responses, or exact
competitor rows.
