# Reply desk — operator runbook (XG-W4)

The reply desk drafts replies for the seven X accounts and hands the approved
ones to a **desktop session** that actually sends them. It is **DARK BY
DEFAULT**: every account ships at mode **M0**, which means the queue fills, the
critics run, drafts appear in the admin UI, and **nothing leaves this machine**.
Nothing sends until you flip a per-account dial.

**Full flow:** `discovery → scorer → drafter → critics → reply queue (queued) →
approve in admin → export (M1 only) → desktop session claims → sends → receipt →
sent`, with every transition recorded in `~/.mastermind/reply_desk/store/ledger.jsonl`.

Pieces:
- `engine/marketing/reply_discovery.py` — twitterapi.io target discovery (own provider, own sub-budget).
- `engine/marketing/reply_score.py` — deterministic opportunity scoring. No LLM.
- `engine/marketing/reply_drafter.py` — per-persona drafting, reply-family rotation, chart slot.
- `engine/marketing/reply_critics.py` — the independent critic pass.
- `engine/marketing/reply_queue.py` — the store, the mode dial, the caps, the one-owner lock.
- `engine/marketing/reply_export.py` — the M1 handoff to the desktop session.
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
to halt one account without halting seven, and today it cannot.

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

## 6. The desktop session contract

The session reads and writes three directories under
`~/.mastermind/reply_desk/` (override with `MASTERMIND_REPLY_DESK_DIR`):

```
~/.mastermind/reply_desk/
  queue/     <id>.json    approved items, ready to send
  claims/    <id>.json    your lease on an item
  receipts/  <id>.json    proof that a reply went out
  store/                  the queue's own ledgers (do not hand-edit)
  discovery/              cursors + spend (do not hand-edit)
```

### Protocol

1. **Read** `queue/`. Each file carries `draft`, `target_url`, `parent_author`,
   `parent_excerpt`, `chart` (`local_path` + `public_url`), `tier`, `not_before`,
   and `expires_at`. A file in `queue/` is a live instruction: the sweep deletes
   the mirror as soon as its item expires, is rejected, or loses its lease, so
   you are not relying on your own vigilance to avoid sending a dead draft.
2. **Check `expires_at` anyway.** Belt and braces — the sweep runs on a tick, and
   you may be reading between ticks.
3. **Claim before navigating.** Take the lease first, then open the thread:

   ```bash
   python3 -c "import yaml; from engine.marketing import reply_export as x; \
               print(x.claim_for_desktop('<item-id>', holder='desk-1', \
                     cfg=yaml.safe_load(open('config/marketing.yml'))))"
   ```

   This writes `claims/<id>.json` and takes the lease in one step. The default
   lease is **600 seconds** (`reply_desk.lease_s`). An expired lease returns the
   item to `queued` — deliberately *not* to `approved`, because a lease that
   timed out gives us no way to know whether the reply was posted. A human
   re-approves. That friction is the point; it is what prevents a double-post.

   **A claimed item is never expired out from under you.** The lease governs an
   in-flight item, so a TTL that lapses mid-send cannot orphan a reply you have
   already posted.
4. **Send the reply** in the account's own browser profile. Attach the chart from
   `chart.local_path` when present. The chart carries an as-of stamp — charts are
   EOD-only, and yesterday's bar must never be presented as live.
5. **Write a receipt** to `receipts/<id>.json`:

   ```json
   {
     "id": "rq-2026-07-28-92235b6304",
     "url": "https://x.com/mastermindkelly/status/1900000000000000123",
     "screenshot": "/path/to/screenshot.png",
     "holder": "desk-1",
     "sent_at": "2026-07-28T15:04:00Z"
   }
   ```

   **Always write both fields.** They are enforced differently on purpose:

   - **`url` is required.** A receipt without one is refused and parked as
     `.invalid` — an empty receipt is not evidence of anything.
   - **`screenshot` is expected but not blocking.** A receipt missing one warns
     and still records the send, because refusing it would leave a reply that is
     already public permanently uncounted — and an uncounted send silently buys
     back room under the daily cap. Fill it in anyway: it is the only artefact
     that lets a human audit how the reply rendered under the parent post.
6. The next sweep ingests receipts, records the send against the daily cap, and
   clears the queue mirror and the claim. A consumed receipt is renamed `.done`
   so a re-run never double-counts a send.

Run a full tick (ingest receipts, reclaim leases, expire, sweep mirrors, export):

```bash
python3 -c "import yaml; from engine.marketing import reply_export as x; \
            print(x.sweep(cfg=yaml.safe_load(open('config/marketing.yml'))))"
```

Ingest runs **first** so a send from the previous tick is on the books before
the cap is sized; otherwise the export step hands out headroom already spent.

### Receipts that cannot be resolved

A receipt for an item that can no longer record a send — already sent, rejected,
unknown, or belonging to a desk you disabled after it went out — is parked as
`.unresolved` with a `::warning title=reply-receipt-orphan::`. Read these: the
reply may be **public but unrecorded**, which means the daily cap is
under-counting and will hand out room that is already spent. Reconcile by hand
before raising any dial.

A receipt refused only because the account hit its cap is **kept**, and the
item keeps its lease so the send can still be recorded once the cap clears.

### If a send fails

Mark it failed rather than leaving the lease to rot:

```bash
python3 -c "from engine.marketing import reply_queue as q; \
            q.transition('<item-id>', 'failed', actor='desk-1')"
```

An item may be re-armed **twice**. After the second failure it is dead; do not
retry it by hand. Retry-spamming one thread is exactly the pattern that gets an
account actioned.

---

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

Every draft you see has already cleared eight critics (near-dup vs the parent,
near-dup vs our own corpus, satire/sensitivity blocklists + zero-cross-account
engagement, position consistency, the persona-label test, fact discipline, the
shared vocab guard, and the dignity rubric). What reaches you is a *taste*
decision, not a safety decision.

That is a **structural** guarantee, not a description of a pipeline: the queue
itself refuses any item whose critic stamp is missing, not a `pass`, or produced
by a partial run (`reply_queue.validate_critic_stamp`). It holds no matter which
producer built the item, including one written after this document.

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

## 9. What is deliberately not built yet

- **The producer chain.** Nothing in this wave calls
  discovery → scorer → drafter → critics → `enqueue` in sequence, so **the queue
  does not fill on its own yet**. Every piece is built, tested and callable; the
  connective tissue (the scheduled tick that walks discovery output through the
  scorer and drafter and enqueues what survives the critics) lands with the rest
  of the reply pipeline in **XG-W6**, alongside telemetry wiring. Until then the
  desk is a library plus an operator surface, not a running loop.

  This is why the critic guarantee is enforced at the STORE rather than in the
  producer: an item can only enter the queue with a full passing critic stamp,
  so the safety claim above is true for whatever eventually fills it.
- **Auto-approval (M2/M3)** — gated on XG-W6's per-account health monitor and
  network tripwire.
- **Parent-adjusted outcome labels** — the queue records `sent_at`,
  `author_replied`, `likes`, and `follower_delta`, and `poll_outcomes()` reads
  the replies under our sent posts. Turning those into a learning signal is
  XG-W6.
- **Chart pre-render sweep** — `reply_drafter.prerender_artillery()` exists and
  reuses the nightly render machinery, but nothing schedules it yet. Until it is
  scheduled, `attach_chart()` only references charts the nightly lane already
  produced.
