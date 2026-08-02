# Reply desk — operator runbook (XG-W4 · arming + handoff contract XG-W7)

The reply desk drafts replies for the seven X accounts and hands the approved
ones to a **desktop session** that actually sends them. It is **DARK BY
DEFAULT**: every account ships at mode **M0**, which means the queue fills, the
critics run, drafts appear in the admin UI, and **nothing leaves this machine**.
Nothing sends until you flip a per-account dial.

**Full flow:** `discovery → scorer → drafter → critics → reply queue (queued) →
approve in admin → export (M1 only) → desktop session claims → sends → receipt →
sent`, with every transition recorded in `~/.mastermind/reply_desk/store/ledger.jsonl`.

**If you are here to turn it on, read §9 first** — arming is four independent
switches, and `--lane reply --preflight` reports all four in one command.
**If you are here to write the sending side, §6 is your interface** — it is a
versioned contract (`marketing.reply.handoff/v1`), and a test compares its worked
examples against what the code actually writes.

Pieces:
- `engine/marketing/reply_discovery.py` — twitterapi.io target discovery (own provider, own sub-budget).
- `engine/marketing/reply_score.py` — deterministic opportunity scoring. No LLM.
- `engine/marketing/reply_drafter.py` — per-persona drafting, reply-family rotation, chart slot.
- `engine/marketing/reply_critics.py` — the independent critic pass.
- `engine/marketing/reply_queue.py` — the store, the mode dial, the caps, the one-owner lock.
- `engine/marketing/reply_producer.py` — the tick that fills the queue (§9), plus the heartbeat.
- `engine/marketing/reply_export.py` — the M1 handoff to the desktop session (§6).
- `app/deploy/marketing-reply-desk.service` — the sibling unit that runs the producer on the VPS.
- `config/reply_targets.yml` — the author register **you curate**.
- Admin → **Marketing → Reply Queue** — approve / hold / reject with reasons.

---

## 0. Why a desktop session exists at all

Buffer cannot post replies. `social_publisher._CREATE_POST_MUTATION` has no
reply-target field, so a reply cannot ride the sanctioned posting rail no matter
how we write it. Rather than hide a sender inside the repo, the queue ends at a
directory and a human-supervised browser session picks it up.

That boundary is the honest one, and it is also the cheap one: when an official
X write API becomes available, it replaces the desktop session without touching
discovery, scoring, drafting, critics, or the queue.

**X's automation rules require API-based automation.** Browser-driven posting is
outside them. That is why the dial exists, why M3 is opt-in per account, and why
every account starts at M0. The residual risk at M2 and above is
single-machine device/IP correlation across seven profiles; profile isolation,
staggering, per-persona voice divergence, hard caps, and zero cross-account
engagement reduce it but cannot eliminate it.

---

## 1. Curate the author register

Edit `config/reply_targets.yml`. It ships with placeholder entries marked
`enabled: false` — the schema and the validator are the engineering deliverable,
but **who is worth talking to is your editorial call**, not a builder's.

For each desk, list authors under one of three tiers (constitution §9.2):

| Tier | Who | Why |
|---|---|---|
| `relationship` | smaller/mid-sized experts who answer good replies | repeated recognition, community credibility |
| `conversion` | niche accounts with highly relevant audiences | fewer impressions, better qualified follows |
| `breakout` | very large or fast-accelerating posts | enter only with a fast chart, correction, or mechanism |

Rules the validator enforces:
- bare handles, no leading `@`
- one author belongs to **one desk only** (a shared author guarantees a
  same-thread collision later)
- every entry needs a valid tier

Validate after editing:

```bash
python3 -c "from engine.marketing import reply_discovery as r; \
            print(r.validate_register(r.load_register()) or 'OK')"
```

Only `relationship` threads are read *including replies* — that is where a
conversation actually starts, and it is the expensive read. Breakout targets are
read top-level only.

---

## 2. Spend: one bucket, two lanes

twitterapi.io is a single account with a single **$75/month** cap, and the Trump
wire depends on it. Reply discovery carves a **$15 sub-budget**
(`config/press_sources.yml` → `reply_discovery.monthly_usd_cap`) and the
enforcement is deliberately asymmetric:

- Reply spend increments only the reply counter, never the wire's, so the wire's
  cap check cannot see this lane at all. **Reply polling can never stop the wire.**
- Reply polling additionally stops when the combined spend it can observe hits
  the shared cap. **Reply yields to the wire; the wire never yields to reply.**

At either stop the lane prints a start-of-line `::warning` and returns nothing.
Cursors and spend live in `~/.mastermind/reply_desk/discovery/state.json` — never
in the repo, because the M1 is the nightly render host and an intraday writer in
the render checkout collides with render-lane resets.

**Poll through `run_tick`, never `fetch` directly.** `run_tick` loads that state,
reads the wire's spend, polls once, and saves. Calling `fetch` with a bare dict
does none of that: it skips persistence (silently resetting the monthly counter
every process, which makes the sub-cap vacuous, and resetting the since-id
cursors so every author's whole timeline is re-read and re-billed), and it
leaves the shared-bucket stop inert, because the wire's counter lives in a
different file (`data/marketing/press/state.json`, read-only from here) and is
not in the reply lane's state at all:

```bash
python3 -c "import yaml; from engine.marketing import reply_discovery as d; \
            p = d.build_provider(yaml.safe_load(open('config/press_sources.yml')), \
                                 yaml.safe_load(open('config/marketing.yml'))); \
            print(d.run_tick(p))"
```

The returned `wire_spend` is what the shared stop was sized against. If it reads
`0.0` while the wire lane is known to be running, the two lanes are looking at
different checkouts and the combined ceiling is not being enforced — pass
`repo_root=` explicitly.

Desks are polled in rotation, so a `max_requests_per_tick` smaller than the fleet
does not starve the tail of the list; a truncated tick prints
`::warning title=reply-discovery-tick-cap::`.

---

## 3. The mode dial

Per account, in `config/marketing.yml` → `reply_desk.mode.accounts`.

| Mode | Behaviour | Ships? |
|---|---|---|
| **M0** | Draft-only. Queue fills, nothing exports. | ✅ launch state |
| **M1** | Assisted. Items **you approved** export to the desktop lane. | ✅ |
| **M2** | Auto-approve inbound (replies on our own posts). | ❌ gated off |
| **M3** | Auto-approve outbound within caps. | ❌ gated off |

M2 and M3 exist as keys so the escalation path is legible, but `modes_enabled`
may not contain them: `reply_queue.resolve_mode()` clamps to M0 and prints a
warning if a config asks. **The XG-W6 per-account health monitor and network
tripwire are a hard precondition for any flip above M1** — a failure must be able
to halt one account without halting seven.

**That precondition is now BUILT (XG-W6).** `engine/marketing/health_monitor.py`
grades every account nightly on four deterministic monitors, runs the fleet
tripwire, and writes per-account halt rows that both rails enforce (see §10).
The dial itself is unchanged: `SHIPPABLE_MODES` still admits only M0/M1, and
widening it is a separate, explicit decision with its own record — the
precondition being met is not the same as the flip being made.

**A SECOND precondition, still open: halts trip NIGHTLY ONLY.** Every monitor
input is daily-cadence telemetry (the Buffer metrics poll refreshes about once a
day), so an incident starting at 10:00 is caught that night, not that hour. At
M0/M1 you approve every send, so a nightly halt is proportionate. **At M2/M3 it
is not** — auto-approval means an account can keep sending for a full day after
the signal that should have stopped it. **Intraday halt evaluation is a
precondition for any flip above M1**, alongside the monitor itself (charter §5).

M3 additionally requires, per account: ≥100 M1/M2 sends with zero incidents,
passing blind-identity and anti-sameness evals, and an explicit operator flip.

### Daily caps

The standing reply cap is **0** (D08). Your 2026-07-28 directive opened it *per
the dial only*. At M0 the cap is 0 no matter what config says. At M1+ it is
`reply_desk.daily_caps.per_account_target` (default 18, the charter's 15-20
quality bar), clamped to a **hard ceiling of 30** that is a code constant in
`sentinel.py` — config can lower it, never raise it.

The cap binds in **two** places, and both matter:

1. **At export.** Headroom is `cap - sends already made today - mirrors still in
   flight`, so ten approved items against a cap of one export exactly one. This
   is the gate that matters — enforcing the cap only on the way back would gate
   bookkeeping, because by then the reply is already public.
2. **At receipt ingest.** Re-checked because the desktop session runs on its own
   clock and a cap enforced only upstream is one a slow queue walks through.

Held-back items stay approved and are exported on a later tick if their window
has not closed. When the cap holds items back, the tick prints a
`::warning title=reply-cap-export::` naming the remaining headroom.

---

## 4. Flip an account to M1

1. Edit `config/marketing.yml`:

   ```yaml
   reply_desk:
     mode:
       accounts:
         kelly: M1        # was M0
   ```

2. Commit and merge as normal. No render is required — nothing about this is
   rendered into the site.

3. Confirm the dial:

   ```bash
   python3 -c "import yaml; from engine.marketing import reply_queue as q; \
               cfg=yaml.safe_load(open('config/marketing.yml')); \
               print({a: q.resolve_mode(cfg,a) for a in cfg['reply_desk']['mode']['accounts']})"
   ```

To revert, set it back to `M0`. Reverting is instant and total: the next export
tick writes nothing, and anything already exported can be deleted from
`~/.mastermind/reply_desk/queue/`.

---

## 5. Browser profiles (one per account)

Set up **seven separate browser profiles**, one per account. Never sign two
accounts into one profile, and never sign one account into two profiles.

- **Credentials live only in the browser profile.** Nothing in this repo reads,
  stores, or writes an account password or session cookie, and nothing may. If a
  runbook step ever asks you to put a credential in a file we read, it is wrong.
- Give each profile its own persistent directory so cookies, local storage, and
  fingerprint surface stay stable per persona.
- Keep each profile signed in to exactly one account, permanently. Signing in
  and out repeatedly is itself a signal.
- Do not install the same extension set across all seven.

### Session hygiene

- Warm a new profile with normal reading before it ever replies.
- Do not open all seven profiles simultaneously.
- Do not reply from a profile immediately after signing it in.
- **Zero cross-account engagement, ever** — no mutual likes, reposts, follows, or
  replies between our own accounts. This is a hard fleet-linkage law
  (charter §2 amendment 6), not a preference.

### Staggering and never-synchronized windows

- Work one account at a time. Finish or abandon its item before switching.
- Leave an irregular gap between accounts. Do not use a fixed interval — a
  metronome is more detectable than volume.
- Never have two accounts active in the same minute.
- Respect each persona's natural session: Cici runs Asia hours, the others US
  hours. A desk replying at 3am in its own time zone reads as a bot.
- The one-owner lock already guarantees two accounts never appear under the same
  thread. Do not work around it manually.

---

## 6. The desktop session contract (`marketing.reply.handoff/v1`)

This section is a **versioned interface**, not a description of our internals.
The consumer is your own system, written outside this repo and updated on its
own schedule, so the shapes below are a promise:

- Every file we write carries `"contract": "marketing.reply.handoff/v1"`. Read
  it. A consumer that does not recognise the version should refuse the file
  rather than half-act on it.
- **Adding** a field is not a version bump — read by key, never by position, and
  ignore keys you do not know. **Removing or retyping** one is a major bump, and
  the version string changes with it.
- The contract ends at these three directories. Nothing in this repo drives a
  browser, synthesises input, or times a keystroke, and nothing in it ever will
  — that is your side of the boundary.

`tests/test_marketing_reply_arming.py` parses the worked examples below out of
this file and compares them against what the code actually writes, so this
document cannot drift away from the interface it documents.

### 6.1 The directories

```
~/.mastermind/reply_desk/          (override with MASTERMIND_REPLY_DESK_DIR)
  queue/     <id>.json    WE write, YOU read     — approved items, ready to send
  claims/    <id>.json    WE write, YOU read     — your lease on an item
  receipts/  <id>.json    YOU write, WE consume  — what actually happened
  store/                  ours; never hand-edit  — items + ledger
  discovery/              ours; never hand-edit  — cursors + spend
  producer_heartbeat.json ours; read-only for you — lane liveness (§9.5)
```

Who writes what is the whole design. You never edit `store/`; we never invent a
receipt. Every state change is an append to `store/ledger.jsonl` with an actor.

### 6.2 Protocol

1. **Read `queue/`.** A file there is a live instruction: the sweep deletes the
   mirror as soon as its item expires, is rejected, fails, or loses its lease.
2. **Check `expires_at` anyway.** The sweep runs on a tick and you may be
   reading between ticks. Charter §3: a reply lives in a 5–15 minute window, and
   a late reply under a cold thread is the automation tell we are avoiding.
3. **Claim before navigating** (§6.4). Take the lease, then open the thread.
4. **Send the reply** in that account's own browser profile. Attach the chart
   from `chart.local_path` when present; it carries an as-of stamp, and charts
   are EOD-only, so yesterday's bar must never be presented as live.
5. **Write a receipt** (§6.5) — success *or* failure. Both are file-level
   outcomes; neither needs you to import our Python.
6. The next `sweep()` ingests it, records the send against the daily cap,
   escalates the author's relation row, and clears the mirror and the claim.

### 6.3 What you receive

#### `queue/<id>.json`

```json
{
  "contract": "marketing.reply.handoff/v1",
  "id": "rq-2026-08-01-9f3c55f112",
  "as_of": "2026-08-01",
  "account": "kelly",
  "target_url": "https://x.com/somequant/status/1900000000000000042",
  "target_status_id": "1900000000000000042",
  "thread_key": "1900000000000000042",
  "parent_author": "somequant",
  "parent_excerpt": "Hyperscaler capex keeps climbing but credit spreads are widening.",
  "draft": "IG spreads widened 12.5% while capex guidance held.",
  "chart": null,
  "tier": "relationship",
  "mode": "M1",
  "not_before": "2026-08-01T15:00:00Z",
  "expires_at": "2026-08-01T15:45:00Z",
  "exported_at": "2026-08-01T15:00:00Z"
}
```

| Field | Meaning |
|---|---|
| `id` | the item id. Use it as the receipt's `id` and as the claim/receipt filename. |
| `account` | which browser profile must send this. Never send from another. |
| `target_status_id` / `target_url` | the post being replied to. |
| `thread_key` | the conversation. One conversation has exactly one owning desk, enforced in the store — you do not need to check it, but do not work around it. |
| `parent_excerpt` | the parent's text, for eyeball confirmation you are under the right post. |
| `draft` | the text to send, verbatim. Edits are a taste decision and belong in the admin rail, not here. |
| `chart` | `null`, or `{local_path, public_url, chart_id}`. Attach `local_path`. |
| `tier` | `relationship` / `conversion` / `breakout` / `inbound`. |
| `mode` | the dial **stamped at enqueue time**, not now. Informational. |
| `not_before` / `expires_at` | the send window, UTC. |

Deliberately absent: scores, score components, alternates, the critic stamp, the
drafting family, and anything resembling a credential. A leaked queue file leaks
no strategy and no secret.

#### `claims/<id>.json`

```json
{
  "contract": "marketing.reply.handoff/v1",
  "id": "rq-2026-08-01-9f3c55f112",
  "holder": "desk-1",
  "lease_until": "2026-08-01T15:10:00Z",
  "reclaimed": false
}
```

### 6.4 Claiming — lease semantics and double-claim

```bash
python3 -c "import yaml; from engine.marketing import reply_export as x; \
            print(x.claim_for_desktop('<item-id>', holder='desk-1', \
                  cfg=yaml.safe_load(open('config/marketing.yml'))))"
```

- The default lease is **600 s** (`reply_desk.lease_s`).
- **Double claim by the same holder while the lease is live** returns the *same*
  lease with `"reclaimed": true`. It is safe to retry: the lease is **not**
  extended, so a crash-loop cannot hold an item forever.
- **Claim by a different holder** returns `null`. Two sessions on one item is the
  collision the lease exists to stop.
- **A lapsed lease is never handed back**, not even to its own holder. We cannot
  know whether the dead session posted, so the item returns to `queued` on the
  next sweep and a human re-approves. That friction is what prevents a
  double-post.
- **A claimed item is never expired out from under you.** The lease governs an
  in-flight item, so a TTL that lapses mid-send cannot orphan a reply you have
  already posted.
- Claiming is refused for an item past `expires_at`, for an account at **M0**,
  and for a **halted** account — in that order, before any file is written.

**Abandoned item:** lease lapses → next `sweep()` returns it to `queued`, and
both `queue/<id>.json` and `claims/<id>.json` are deleted. Nothing to clean up
by hand.

**Unclaimed item:** stays `approved` with its mirror in `queue/` until
`expires_at`, then it is expired and the mirror is swept.

### 6.5 What you send back

A receipt says exactly one of two things. `status` is the discriminator; an
**absent** `status` means `"sent"` (the pre-v1 shape, still accepted forever), and
an **unrecognised** `status` is refused rather than guessed — reading a field you
got wrong as the charitable case is how a failed send becomes a recorded one.

#### `receipts/<id>.json` — success

```json
{
  "id": "rq-2026-08-01-9f3c55f112",
  "status": "sent",
  "url": "https://x.com/mastermindkelly/status/1900000000000000999",
  "screenshot": "/path/to/screenshot.png",
  "holder": "desk-1",
  "sent_at": "2026-08-01T15:04:00Z"
}
```

- **`url` is required** and must be the URL of *our* posted reply — it is where
  the posted reply id comes from, and the nightly outcome poll reads that id to
  ask whether the author answered. A receipt without it is refused and parked
  `.invalid`.
- **`screenshot` is expected but not blocking.** Missing it warns and still
  records the send: refusing would leave a reply that is already public
  permanently uncounted, and an uncounted send silently buys back room under the
  daily cap. Fill it in anyway — it is the only artefact a human can audit by eye.
- `holder` and `sent_at` are advisory; `sent_at` defaults to ingest time.

#### `receipts/<id>.json` — failure

```json
{
  "id": "rq-2026-08-01-9f3c55f113",
  "status": "failed",
  "reason": "compose box never loaded",
  "holder": "desk-1",
  "sent_at": "2026-08-01T15:06:00Z"
}
```

- **No `url`** — there is no URL when nothing was posted, and requiring one would
  force you to fabricate evidence of a send that did not happen.
- `reason` is free text and lands in the ledger note. Write something a human can
  act on; it is the only record of why this thread went unanswered.
- The item moves to `failed`. It may be re-armed **twice**; after the second
  failure it is dead. Do not retry it by hand — retry-spamming one thread is
  exactly the pattern that gets an account actioned.

### 6.6 Idempotency, in one table

| You do this twice | What happens |
|---|---|
| Claim, same holder, live lease | second call returns the same lease, `reclaimed: true`. No lease extension. |
| Claim, different holder | second call returns `null`. |
| Write a success receipt | first records the send; second is retired `.duplicate` with **no** orphan warning and **no** second count against the cap. |
| Write a failure receipt after a send | retired `.duplicate` — the send is already terminal and wins. |
| Run `sweep()` | fully idempotent. Consumed receipts are renamed, so nothing is re-read. |

Receipt files are consumed by renaming, never deleting, and the rename never
clobbers (a second `.done` becomes `.done.1`). The suffix tells you what happened:

| Suffix | Meaning |
|---|---|
| `.done` | recorded — a send or a reported failure |
| `.duplicate` | already on the books; no action needed |
| `.invalid` | malformed (no URL, or an unknown `status`) |
| `.unresolved` | **read these.** The reply may be public but unrecorded, which means the daily cap is under-counting and will hand out room that is already spent. Reconcile by hand before raising any dial. |

A receipt refused only because the account hit its **cap** is *kept*, not retired,
and the item keeps its lease so the send can still be recorded once the cap
clears at midnight.

### 6.7 What a receipt changes

1. **The ledger.** `store/ledger.jsonl` gains a row (`to: "sent"` or
   `to: "failed"`) with the actor, plus an outcome row carrying `sent_at`. The
   item file itself is never mutated — it stays an immutable record of what we
   drafted.
2. **The daily cap.** `sends_today` counts ledger `sent` rows, so the cap is
   sized against real sends and nothing else.
3. **Relationship memory.** A recorded send writes a relation row for the parent
   author on that persona (`stage: "engaged"`); the nightly outcome poll upgrades
   it to `"reciprocal"` when the author answers. The scorer reads that store for
   its `relationship_stage` feature, which is how talking to someone changes who
   we talk to next. The write goes to the gitignored persona host spool and is
   folded into the tracked ledger by the nightly consolidation, so it takes
   effect on the next nightly, not the next tick.

### 6.8 Who runs the sweep

**The reply lane runs it every tick** (§9), on the host that owns the store — so
a receipt you write is ingested within `tick_interval_s` and you do not have to
trigger anything. Ingest runs **first** in the sweep so a send from the previous
tick is on the books before the cap is sized; otherwise the export step hands out
headroom already spent.

To force one by hand (a fixture store, or the lane is stopped):

```bash
python3 -c "import yaml; from engine.marketing import reply_export as x; \
            print(x.sweep(cfg=yaml.safe_load(open('config/marketing.yml'))))"
```

The sweep is fully idempotent, so running it by hand while the lane is up is
harmless — consumed receipts are already renamed.

## 7. Approving drafts

> **Which machine runs the admin matters.** The reply queue lives in host state
> on the M1 Mac Studio (`~/.mastermind/reply_desk`). The deployed admin on the
> VPS resolves *its own* home directory, so it renders an empty queue — there is
> no sync between the two. Approve from an admin running **on the M1**:
>
> ```bash
> MACRO_ADMIN_ROOT=<repo> python3 -m admin      # on the M1, not the VPS
> ```
>
> To point an admin elsewhere at a shared or mounted store, set
> `MASTERMIND_REPLY_DESK_DIR` in that service's environment. **Do not** relocate
> the store into the repo checkout to work around this — the M1 is the nightly
> render host and an intraday writer there collides with render-lane resets.
> A proper VPS-side approval surface needs a sync or an API and is not built.

Admin → **Marketing → Reply Queue**, two zones per account:

- **Awaiting your approval** — approve, hold, or reject.
- **Approved** — waiting for export (M1) or parked (M0).

**Reject with a reason whenever the draft is wrong.** Rejections are the taste
corpus: they are the training signal for what this desk should sound like, and a
rejection with no reason teaches nothing. Hold is reversible and keeps the item
in the rail; reject is terminal and releases the thread so a sibling desk may
legitimately take it.

Every draft you see has already cleared nine critics (near-dup vs the parent,
near-dup vs our own corpus, satire/sensitivity blocklists + zero-cross-account
engagement, position consistency, the persona-label test, the reply-value
doctrine bar, fact discipline, the shared vocab guard, and the dignity rubric).
What reaches you is a *taste* decision, not a safety decision.

That is a **structural** guarantee, not a description of a pipeline: the queue
itself refuses any item whose critic stamp is missing, not a `pass`, or produced
by a partial run (`reply_queue.validate_critic_stamp`). It holds no matter which
producer built the item, including one written after this document.

### The bar you are approving against (E4 reply doctrine)

**Read `research/MARKETING_REPLY_DOCTRINE_BY_FABLE.md` once before your first
approval session.** It is the same doctrine the machine is held to — the drafter
phrases from it (`engine/marketing/reply_voice.py`), the `reply_value` critic
kills its anti-patterns, and it is distilled from a harvested corpus of 180 top
replies under 12 large finance posts
(`research/marketing_dockets/reply_corpus_2026_07_29/`), not from taste alone.

The short version, for the rail:

- **A reply is rent paid for someone else's audience.** The rent is a gift the
  thread did not already have.
- **It must carry one of five things**: a data drop, a sharp read, dry wit, a
  useful reframe, or a missing-number correction. None of the five → reject.
- **Length**: the corpus median winning reply is **11 words**; two-thirds are
  under 16. If a draft needs 40 words to land one thought, it is not finished.
- **Questions**: a question aimed at *the room* is fine. A question aimed at the
  *poster* ("what do you think of X?") is the shape that reliably scores zero —
  reject it unless the draft also carries a fact that stands without it.
- **Never approve the moral-outrage pattern.** It has the highest ceiling in the
  corpus and it is a standing brand exclusion: no information, borrowed anger,
  and one screenshot next to our profile costs more than the likes.
- **A good line is necessary, not sufficient.** The corpus contains a genuinely
  sharp reply that earned zero because it arrived late from a small account.
  Judge the draft, not the outcome you imagine for it.

Reject reasons that name which of the five was missing are worth several that
say "meh" — the rejection corpus is what teaches this desk your taste.

---

## 8. Kill switches

| Scope | Action | Effect |
|---|---|---|
| One account | set its mode back to `M0` | that desk exports nothing; cap 0 |
| One account, keep the dial | `reply_desk.daily_caps.accounts.<id>: null` | cap 0 for that desk |
| The whole desk | `reply_desk.enabled: false` in `config/marketing.yml` | every account forced to M0, every cap 0, nothing exports |
| Discovery only | `reply_discovery.enabled: false` in `config/press_sources.yml` | no polling, no spend; the queue drains |
| Everything in flight | delete `~/.mastermind/reply_desk/queue/*.json` | the desktop lane has nothing to send |

All four are verified by tests, not just documented — a kill switch that reads
as off while the desk keeps exporting is worse than no switch.

Nothing in this system posts on a schedule of its own. Every send is a human in
a browser acting on an item a human approved.

---

## 9. The producer (XG-W6) — arming it (XG-W7), and how the queue fills

`engine/marketing/reply_producer.py` is the connective tissue XG-W4 deliberately
left out: discovery → score → draft → critics → `enqueue`, in one tick.

Each reply-lane tick runs **two** halves:

1. **the producer** — fill the queue (this section);
2. **the desk sweep** — `reply_export.sweep`: ingest receipts, reclaim abandoned
   leases, expire, sweep stale mirrors, export at M1 (§6.8). It runs even while
   the producer is dark, because items already in flight still have to be swept
   and receipts already written still have to be read.

**It sends nothing.** Output lands in the M0 queue for you to review in §7.
Arming this lane means **drafts appear**, not that anything leaves; the dial
(§3, §4) is a separate and later decision.

### 9.1 Four switches, and each one used to fail as silence

The lane was fully built and never ran, because four independent gates each turn
it off and **all four look identical in the log** — a tick reporting zeroes.

| # | Switch | Where | Ships |
|---|---|---|---|
| 1 | `MARKETING_FASTLANE_ENABLED=1` | `/etc/macro-live.env` | already set for the wire |
| 2 | a process actually running `--lane reply` | `app/deploy/marketing-reply-desk.service` | unit ships **disabled** |
| 3 | `reply_desk.producer.enabled: true` | `config/marketing.yml` | `false` |
| 4 | `TWITTERAPI_IO_KEY` | `/etc/macro-live.env` | already set for the wire |

Switch 1 is shared with the wire daemon (`main()` exits 0 without it). Switch 3
is **not** inherited from the wire's arming, deliberately: this lane bills
twitterapi.io against its own sub-budget, so arming it is a separate act.

### 9.2 Preflight — run this first

```bash
python -m scripts.marketing_fastlane_daemon --lane reply --preflight
```

Zero network, zero spend, zero writes, and it runs *even when switch 1 is off*,
because "switch 1 is off" is the answer it most often has to give. It reports all
four switches, the register, each desk's dial and curated-author count, and the
last heartbeat; it exits `1` while any blocker stands. Read the first `BLOCKER`
line, fix it, re-run.

`warning` lines are not blockers. Two are expected at launch and are correct:
every desk at **M0** (the launch state), and a **placeholder register** (only
inbound mentions can produce a target until you curate §1).

### 9.3 The arming walk, in order

1. **Curate `config/reply_targets.yml`** (§1). Until real handles are enabled,
   the curated-timeline half of discovery is structurally dark and the lane
   spends money polling mentions for essentially nothing. This is editorial work
   and it comes first.
2. **Flip `reply_desk.producer.enabled: true`** in `config/marketing.yml`. Commit
   and merge as normal; no render is required.
3. **Dry-run once, on the host, before installing the unit:**

   ```bash
   python -m scripts.marketing_fastlane_daemon --lane reply --once --dry-run
   ```

   `--dry-run` maps to the producer's `offline=True`: zero network, zero spend,
   **zero targets**, and no heartbeat write. It proves the wiring, config load
   and account resolution — not discovery.
4. **Install and start the unit:**

   ```bash
   sudo cp app/deploy/marketing-reply-desk.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now marketing-reply-desk
   journalctl -u marketing-reply-desk -f
   ```

   It is a **sibling** of `marketing-press-feeds`, not a widening of it. The wire
   runs `--interval 75` to stay inside the Truth-mirror hot-poll window; the
   reply desk's own window is 5–15 minutes and its bar is 15–20 replies a day.
   One `--interval` cannot serve both, a shared process makes a reply-lane crash
   restart the Trump wire, and `systemctl stop marketing-reply-desk` must leave
   the wire alone.
5. **Watch the first hour** (§9.5). Then, and only then, consider §4 (M1).

### 9.4 Cadence

The unit passes **no** `--interval`. The reply lane reads
`reply_desk.producer.tick_interval_s` (default **300 s**) from
`config/marketing.yml`, so retuning the cadence is a PR that CI sees rather than
a hand-edit to a unit file on one host. An explicit `--interval` still wins if
you are driving it by hand.

### 9.5 What to watch

**The heartbeat** — `~/.mastermind/reply_desk/producer_heartbeat.json`, rewritten
every live tick:

```bash
python3 -c "from engine.marketing import reply_producer as p; \
            print(p.read_heartbeat())"
```

| Field | Read it as |
|---|---|
| `at` / `tick` | frozen ⇒ the **daemon is dead**. Check `systemctl status`. |
| `consecutive_empty` | climbing ⇒ the daemon is **alive and finding nothing**. |
| `diagnosis` | why the last tick was empty, naming the first stage that zeroed. |
| `last` | the stage counts: curated authors, targets, eligible, drafted, abstained, critic-rejected, enqueued, refused. |
| `last_enqueued_at` | `null` after arming means the lane has never produced. |

Those first two need **opposite** responses, which is exactly what the old shared
`fastlane_heartbeat.txt` could not tell you: it proves the daemon is alive and
nothing more.

**The silent-desk warning** — after `silent_tick_warn_after` consecutive ticks
that enqueued nothing (default **12**, i.e. one hour at 300 s), the lane prints a
start-of-line annotation and repeats it once per further full run:

```
::warning title=reply-desk-silent::the reply desk has enqueued nothing for 12
consecutive ticks (last enqueue: never) — config/reply_targets.yml has no
ENABLED authors for any live desk …
```

The text names the **first** stage that zeroed, not the fact that the total is
zero. A quiet desk is legal — Law 1, value before activity, and a tick reporting
`drafted=0 abstained=7` is the system working. An *hour* of it with no diagnosis
is not.

**`::warning title=reply_voice_mute::`** in the journal means the LLM phrasing
pass found no provider and every reply is shipping the deterministic template.
That failure class shipped dark for months in a sibling lane. Preflight flags it
when `reply_desk.voice.enabled` is true and `MARKETING_LLM_ENABLED` is unset.

**The desk sweep line** — one per tick, beside the producer line:

```
[reply] desk sweep | recorded=0 failed=0 duplicates=0 refused=0 released=0 \
        expired=2 exported=0 swept_mirrors=2
```

`refused` climbing is the one to chase: those are receipts parked `.unresolved`
or `.invalid` (§6.6). `exported=0` at M0 is correct and permanent.

**Where the drafts appear:** admin → Marketing → Reply Queue, on the machine that
can read the store (§7). A queue that stays empty while the heartbeat says
`enqueued` is climbing means you are looking at the wrong host, not at a broken
producer.

### 9.6 How to stop it

| Scope | Action |
|---|---|
| This lane, now | `sudo systemctl stop marketing-reply-desk` (the wire is unaffected) |
| This lane, permanently | `sudo systemctl disable --now marketing-reply-desk` |
| Keep the unit, stop producing | `reply_desk.producer.enabled: false` — the next tick is a logged no-op |
| Stop the spend, keep the queue | `reply_discovery.enabled: false` in `config/press_sources.yml` |
| Everything, both lanes | unset `MARKETING_FASTLANE_ENABLED` in `/etc/macro-live.env` |

Stopping the producer does not touch anything already queued, and it can never
cause a send: sending is the dial, and the dial is §3.

### 9.7 Spend

Unchanged from §2. The producer calls `reply_discovery.run_tick`, which owns the
cursors, the monthly counter, the reply sub-cap and the shared-bucket stop that
makes reply polling yield to the Trump wire and never the reverse. The producer
adds no second budget and no second counter.

### 9.8 Per-tick knobs

| Key | Default | Meaning |
|---|---|---|
| `max_drafts_per_account_per_tick` | 3 | the daily bar is 15–20; the daemon ticks often |
| `max_draft_attempts_per_account` | 12 | stop drafting after this many scored targets |
| `family_history` | 20 | how far back the LRU family rotation looks |
| `n_alts` | 2 | alternates, composed from **different** families |
| `tick_interval_s` | 300 | seconds between ticks (§9.4) |
| `silent_tick_warn_after` | 12 | empty ticks before the silence warning (§9.5) |

### 9.9 What it does when it has nothing to say

Abstains, and counts the abstention. An empty own-feed fact list produces an
empty draft and no queue item — Law 1, value before activity. A tick reporting
`drafted=0 abstained=7` is the system working, not failing.

## 10. Per-account halt (XG-W6)

A halted account is blocked on **both** rails while every other desk runs
untouched. There is no global halt switch anywhere in the module — a halt is
always a row keyed by one account id, so "halt one, not seven" is the only shape
the registry can hold.

| Rail | Enforcement site |
|---|---|
| Posts | `scripts/marketing_publisher.py` — auto-approve pass **and** the post loop |
| Replies | `engine/marketing/reply_export.py` — `export_approved` **and** `claim_for_desktop` |
| Producer | `engine/marketing/reply_producer.py` — before any billed request for that desk |

**What trips one.** The nightly (`scripts/marketing_learning_nightly.py`) grades
each account on four deterministic monitors — operator approval rate, rejection
reason mix, engagement trend, and the last-nine-post profile diagnostic — and
runs the fleet tripwire (simultaneous engagement collapse; cross-account
**per-post** engagement correlation).

**Both actions default to `warn` at launch, so nothing halts automatically yet:**

| Config key | Default | Arming step |
|---|---|---|
| `learning.health.account_action` | `warn` | `halt` |
| `learning.health.network_tripwire.action` | `warn` | `halt_implicated` |

The tripwire is deliberately unarmed because there is **no correlation baseline
yet**. `implicated` is every account in any correlated pair, and 3 of 21 pairs
is enough to fire — one confounded reading would halt the fleet and cost you
seven manual clears. Measure the wire for a few weeks, then arm it. (Correlation
runs on engagement *per post*, not summed: one nightly plan drives all seven
desks, so their post counts move together by construction and summed engagement
would correlate on our own scheduler.)

Every input is deterministic telemetry. No model scores anything here.

**Cadence:** nightly. See §3 — intraday evaluation is a precondition for M2/M3.

**What clears one.** You do, from the admin health panel
(`POST /api/marketing/health/clear-halt`), or:

```bash
python -c "from engine.marketing import health_monitor as h; \
from datetime import datetime,timezone; \
print(h.clear('cici', actor='chris', now=datetime.now(timezone.utc)))"
```

The monitor **cannot** clear its own trip. An intermittent condition would
otherwise let a desk flap between halted and live with nobody ever seeing it,
which is indistinguishable from the monitor not working.

`data/marketing/learning/halts.json` is a tracked file because both rails run on
different machines and both must see it. A clear made in a local checkout must be
**pushed** — until it reaches main, the VPS's next pull restores the halt. The
admin says so in its return rather than reporting a success it did not achieve.

**Reading a halt:** `data/marketing/learning/health.json` carries the evidence
that tripped it, and the registry's `log` carries every halt/clear with an actor.

---

## 11. What is deliberately not built yet

- **Auto-approval (M2/M3)** — the health monitor and tripwire precondition is now
  met, but widening `SHIPPABLE_MODES` is a separate, explicit decision.
- **The L2 ranker retrain** — there is no labels corpus yet. The label store is
  *shaped* for it (`features` / `label` / `weight` / `label_version`) and nothing
  more; building the retrain against an empty corpus would be fitting noise.
- **Learned-rule consumption** — the store, the version log, the reversibility
  gate and the admin surface ship armed; applying a rule is a promotion, so
  `learning.learned_rules.enabled` is `false` and the one wired reader (reply
  family restriction in the producer) reads nothing until you flip it.
- **The blind-identity eval** — pre-registered
  (`docs/blind_identity_eval_prereg.md`), harness built, **not run**. The ≥80%
  figure gates nothing.
- **Chart pre-render sweep** — `reply_drafter.prerender_artillery()` exists and
  reuses the nightly render machinery, but nothing schedules it yet. Until it is
  scheduled, `attach_chart()` only references charts the nightly lane already
  produced.
- **The relationship-stage FEATURE, as opposed to the store.** A recorded send
  now writes a relation row and an author reply-back upgrades it (§6.7), so the
  store finally fills. The scorer's half is still inert: `reply_score._STAGE_SCALE`
  grades `cold / seen / liked / replied / recurring`, while
  `persona_memory.RELATION_STAGES` — the vocabulary the store will accept, and
  the only one it will accept — is `cold / engaged / reciprocal / declined`. Only
  `cold` overlaps, so every written row currently scores `0.0` while reporting
  `source: "relations.jsonl"`, which reads as measured. Until the two
  vocabularies are reconciled, treat `relationship_stage` in a score breakdown as
  a null, not a zero. The weight is 0.04, so nothing else is distorted.
- **Follower-cohort retention** — the north-star metric needs a follower series
  the Buffer poller does not return. The denominator is live; the numerator is
  not, so the metric stays inactive and the bottleneck table on raw counts is
  what the admin renders.
