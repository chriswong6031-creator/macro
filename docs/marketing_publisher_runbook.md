# Marketing live publisher — operator runbook

The D02 W1 publisher posts APPROVED, DUE outbox items to X through **Buffer**
(official X OAuth). It is **DARK BY DEFAULT**: nothing posts until you set two
secrets and a channel id. Every step below is reversible; the kill switch
(step 7) instantly reverts every path to dry-run.

**Full flow:** `content_studio → outbox(queued) → approve (manual, or auto_approve) → publisher(--live) → posted`, with receipts recorded in `data/marketing/outbox/status_ledger.jsonl`.

Pieces:
- `engine/marketing/social_publisher.py` — `BufferPublisher` (send one post, return a `Receipt`).
- `scripts/marketing_publisher.py` — the runner (dark by default; dry-run unless armed).
- `.github/workflows/marketing-publish.yml` — the scheduled runner (ubuntu, off the render path).
- Admin → **Marketing → Publisher** — status, receipts, stuck/quarantined callout, and a "Run dry-run" button.

---

## 1. Create a Buffer personal API token

Buffer dashboard → **Settings → API → Personal Keys → + New Key**. Paid accounts
allow up to 5 keys. Pick scopes for **post creation** and **channel read**
(the publisher needs both: it lists channels to find the id, then creates posts).
Copy the token — you will not see it again.

## 2. Connect the X account as a Buffer channel

In Buffer, connect your X (Twitter) account as a channel. Buffer publishes via
X's official OAuth, so this is approved automation (not scraping).

## 3. Discover the channel id

```
BUFFER_TOKEN=<your-token> python -m scripts.marketing_publisher --list-channels
```

This prints `service  id  name` for every connected channel. Copy the **id** of
the X channel you connected in step 2. (No network happens without the token;
this is the only command that queries Buffer for discovery.)

## 4. Put the id in config

Edit `config/marketing.yml`:

```yaml
publish:
  channels:
    flagship: "<the-channel-id-from-step-3>"
```

`publish.links_allowed.flagship` and `require_approval` are already set; leave
`auto_approve: false` for now (step below on full automation).

## 5. Dry-run (no network, no writes)

```
python -m scripts.marketing_publisher --account flagship
```

The default is dry-run. It prints `WOULD POST` lines for every APPROVED, DUE
item — exactly what a live run would send, with zero network calls and zero
ledger writes. You can also click **Run dry-run** on the admin Publisher panel.

## 6. Arm live

Going live is **two clicks in the admin Publisher panel** (Marketing → Publisher
→ Go-live checklist) — no GitHub UI steps:

1. **Paste the Buffer token** into the token row's paste-box and click **Save
   token**. The panel writes it straight to the `BUFFER_TOKEN` repo secret (it
   shells out to `gh secret set BUFFER_TOKEN`, passing the value on stdin — the
   token is never shown, logged, or committed). `gh` must be installed and
   authenticated on the admin host (this is a local-only action; see the
   fallback below if you run the admin deployed).
2. **Click Arm** on the ARM/DISARM toggle. This sets the `MARKETING_PUBLISH_ENABLED`
   repo **variable** to `1` (via the GitHub API). That variable is the single
   source of truth the workflow reads — `1` = armed, `0`/absent = dark.

The scheduled workflow (`marketing-publish.yml`, weekday 14:00 / 17:30 / 20:15
UTC) then posts approved, due items at the next slot.

**Manual / fallback (no panel):** set the repo **variable** by hand at
**Settings → Secrets and variables → Actions → Variables tab** →
`MARKETING_PUBLISH_ENABLED` = `1`, and set the `BUFFER_TOKEN` **secret** on the
Secrets tab (or `gh secret set BUFFER_TOKEN`). To run once locally instead:

```
MARKETING_PUBLISH_ENABLED=1 BUFFER_TOKEN=<token> \
    python -m scripts.marketing_publisher --live --account flagship
```

The runner only posts when **both** the `--live` flag AND
`MARKETING_PUBLISH_ENABLED` (in `{1,true,yes}`) are set — the flag alone
downgrades to dry-run (`scripts/marketing_publisher.py`:
`live = bool(args.live) and kill_on`). That is why the workflow can pass `--live`
unconditionally and stay dark until you arm it.

> **Note — the kill-switch moved from a SECRET to a VARIABLE.** The workflow
> reads `vars.MARKETING_PUBLISH_ENABLED`, with **no fallback to the old secret**.
> Any lingering repo *secret* named `MARKETING_PUBLISH_ENABLED` is now **ignored**
> by the publisher — delete it to avoid confusion. Only the *variable* controls
> arming. (One source of truth: a stale secret must never keep the publisher live
> after you disarm.)

## 7. KILL SWITCH / rollback

**Click Disarm** in the admin Publisher panel — it sets the
`MARKETING_PUBLISH_ENABLED` repo **variable** to `0`. Every path — workflow,
local runner, admin dry-run — instantly reverts to dry-run and creates no NEW
posts. No code change, no deploy. This is the first thing to reach for if
anything looks wrong.

Manual fallback: set the `MARKETING_PUBLISH_ENABLED` **variable** to `0` (or
delete it) at **Settings → Secrets and variables → Actions → Variables**, or
unset the env var locally. (It is a variable now, not a secret — see the note in
§6.)

### 7a. The variable alone does NOT stop posts already booked

Read this part before you need it. `publish.max_forward_book_min` (§8) lets one
sweep hand Buffer several posts at once as `customScheduled` sends, up to an hour
ahead. Those posts live in **Buffer's** queue, not ours. The variable governs
what our runner does next; it has no reach into a post Buffer has already
accepted, and Buffer will send it on schedule regardless.

This is not hypothetical. On **2026-07-28** a sweep at 16:25:46Z booked five
posts for 16:31 / 16:41 / 16:56 / 17:12 / 17:27Z. The operator found quality
defects and disarmed at 16:26:47Z — **61 seconds later** — and it changed
nothing. All five were already in Buffer's queue and all five went out, three of
them posts that had already been identified as defective.

**Disarm now dispatches the recall for you.** Clicking Disarm writes the variable
AND starts a `marketing-publish` run with `recall_pending`, which cancels every
booked post that has not sent yet. The panel's response says whether that
dispatch succeeded — if it did not, it tells you so explicitly, because those
posts are still going out.

Run it by hand any time (it is **not** gated on the arm variable — recall has to
work while the publisher is off):

```bash
# see what would be pulled back — no network, no writes
python -m scripts.marketing_recall --recall-pending

# actually cancel them
BUFFER_TOKEN=... python -m scripts.marketing_recall --recall-pending --live

# or name specific items
BUFFER_TOKEN=... python -m scripts.marketing_recall --ids ob-2026-07-28-abc123 --live
```

What it will and will not do:

* It cancels a post **only** if the send time it was booked for is still in the
  future and Buffer confirms the delete. Those items move `posted → recalled`,
  which is terminal — they can never re-send, and the copy is replaced with a new
  item, not retried.
* A post that **already went out** is never touched. It stays `posted`, it keeps
  counting against the day's cap, and it is reported as `already_sent`. Nothing
  here can un-send a live post — for that, delete it on X.
* A cancel that fails leaves the item `posted` and turns the Actions run **red**.
  That means those posts are still scheduled: delete them by hand in the Buffer
  queue.

The run's ledger changes are committed even though the variable is `0` — that is
a deliberate exception in `marketing-publish.yml`, otherwise the recall would
cancel the posts and then throw away the record of having done so.

## 8. Raise the daily cap for warm-up

The per-account daily cap lives in `config/marketing.yml`:

```yaml
sentinel:
  max_posts_per_account_per_day: 2
```

**Start at 2/day on an aged account and ramp slowly.** The cap bounds the whole
pipeline (auto-approve and posting both respect it). Raising it is an
operator decision; do it in small steps over weeks, not all at once.

## 9. Full automation (optional): auto-approve

By default a human approves each post on the admin **Outbox** panel before the
publisher can send it. To let the publisher approve gate-clean items itself,
set `publish.auto_approve: true` in `config/marketing.yml` (or pass
`--auto-approve` to the runner). When on, the runner auto-advances
`queued → approved` for items that pass **all** gates — clean `validate_postable`
(280 cap, link policy, non-empty), under the daily cap, and a channel id is set.
In dry-run it only reports what it *would* approve; it mutates nothing. Keep it
**off** during the aged-account warm-up and turn it on only once you trust the
pipeline.

### 9b. Scoped exception: publish-time mover/theme posts

`publish.auto_approve_kinds: [mover, theme_list]` (default ON in config) is a
NARROW carve-out from `require_approval`: it auto-approves **only** items the
publisher itself generated seconds earlier at the posting slot
(`engine/marketing/publish_time_content.py`, provenance
`publisher_live_movers`). These are descriptive live-tape posts — "$X -8% today"
/ "Theme Tape" member lists — with **no entry advice**, rendered from the same
v3 template banks, capped by every Sentinel limit, and re-verified against the
live tape by the post-time gate before sending. There is no operator in the loop
for them BY DESIGN: a human approving a "+7% right now" claim an hour later
defeats the freshness that makes the post honest.

Nightly/operator-authored items of **every** kind (including nightly `mover`
drafts) still require approval — the carve-out keys on the publish-time
provenance, not just the kind.

Levers:
- `publish.publish_time_movers.enabled: false` — stop generating them at all.
- `publish.auto_approve_kinds: []` — keep generating, but they queue for manual
  approval like everything else (they will usually be stale by the time a human
  gets there; expect the tape gate to quarantine some at the next slot).
- The global kill switch (§7) stops everything, as always.

## 10. COMPLIANCE

- Buffer posts via X's **official OAuth** — approved automation, not scraping.
- Keep content **genuinely differentiated per account** and **cadence varied**.
  Identical content across accounts is platform manipulation and the single
  biggest ban trigger. The desk-network personas (`config/marketing.yml
  copywriter.personas`) and the Sentinel near-duplicate gate exist to enforce
  this — do not defeat them.
- New accounts posting links, or the same link twice, is a documented X
  suspension trip; `sentinel.links_allowed` is false until the ramp allows it.

## 11. Post metrics (analytics read-back)

Posts are fire-and-forget by default — Buffer's `createPost` returns only a post
id, no permalink and no analytics. `scripts/marketing_metrics_poll.py` closes the
loop: it reads back per-post impressions/likes/reposts/comments/clicks/engagement
rate **and the public x.com permalink** (`externalLink`, which `createPost` never
returns) via Buffer's `post(input:{id})` query, and appends them to
`data/marketing/post_metrics.jsonl`.

- **When it runs:** automatically, right after the publish step in
  `marketing-publish.yml`, every posting slot (metrics refresh ~daily, so
  re-polling keeps the console current). It also runs standalone:
  `BUFFER_TOKEN=… python -m scripts.marketing_metrics_poll` (add `--dry-run` to
  list what it would poll without any network call).
- **What it needs:** only `BUFFER_TOKEN`. It is **independent of the publish
  kill-switch** — with `BUFFER_TOKEN` unset it prints one line and exits 0 (no
  network, no write), so it is harmless while the publisher is dark. (Note: the
  workflow commits `post_metrics.jsonl` back only when `MARKETING_PUBLISH_ENABLED`
  is set — the same "don't spam main with dark-run commits" gate as the outbox
  ledger. If you set only `BUFFER_TOKEN`, metrics are fetched locally each run but
  not committed until the publisher is armed.)
- **What it polls:** every item posted in the last 7 days — from
  `status_ledger.jsonl` (`posted` rows, keyed by the receipt's `external_id`) and
  from `publications.jsonl` (`remote_id`), deduped by id.
- **Follower counts are NOT available** from Buffer's API and are intentionally
  not collected (a masterplan tracks the paid X-API option).
- **Where it shows up:** Admin → Marketing → Publisher joins the latest metrics
  row per post into the recent-posted table (`metrics` + `external_url`).
- **Row shape** (`data/marketing/post_metrics.jsonl`, append-only, one row per
  poll): `{remote_id, account, external_url, metrics:{impressions, likes,
  reposts, comments, clicks, engagement_rate}, metrics_raw:[…], metrics_updated_at,
  polled_at, ok, note?}`. An item Buffer has not yet refreshed produces an honest
  row with `metrics: {}` and a `metrics_empty` note — never a fabricated zero.

## 12. Images on posts

By default posts are text-only. When enabled, each single-name signal card also
posts as a **PNG chart** (price line, BUY marker, min/max/last, MASTERMIND brand
mark). X rejects SVG, so a PNG is required — and Buffer hosts no uploads, so the
PNG must sit at a public https URL.

**How it works (where each step happens):**

1. **Render (nightly, on the Mac):** `content_studio` renders the PNG at
   content-plan build time — where the price closes are in scope — via
   `chart_render.render_signal_chart_png`, and writes it to
   `data/marketing/outbox/media/<as_of>/<chart_id>.png`.
2. **Upload (nightly, on the Mac):** if R2 creds are present,
   `media_publish.publish_chart_png` uploads that PNG to the **existing public R2
   data plane** (`config.yml r2_data_plane.public_base`, the same
   `pub-…​.r2.dev` bucket every `build_*` script reads) under
   `marketing/charts/<as_of>/<chart_id>.png`, and stamps the public URL onto the
   outbox item (`media_url`). No R2 creds → the PNG stays local, `media_url` is
   null, and the post degrades to text-only.
3. **Attach (post time, GitHub Actions):** the publisher passes `media_url` to
   Buffer as a post asset. No public URL on the item → text-only.

**The local PNG is ephemeral, R2 is the hosting plane.** The file at
`data/marketing/outbox/media/<as_of>/<chart_id>.png` is a throwaway render input,
not a delivery artifact — the post attaches the R2 public URL (`media_url`), never
the local file. Local chart PNGs are therefore **git-ignored by design**
(`.gitignore` → `data/marketing/outbox/media/**/*.png`); only the `.svg` chart
snapshots stay committed (the admin console previews render from SVG). Do not "fix"
a missing PNG in git — it was never meant to be there. If a post is text-only,
check the R2 upload (creds on the Mac, `media_url` on the item), not the repo.

**Kill switch / gate:** `config/marketing.yml publish.media_enabled` (top-level).
`false` → never render, never upload, never attach. The Sentinel
`max_media_posts_per_account_per_day` cap still governs how many chart items may
post per account per day.

**What the operator must provide for public images:** the same R2 env the
oracle/data lanes use — `R2_ENDPOINT`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`,
`R2_BUCKET` — **on the nightly Mac** (that is where the plan is built and the
upload happens). These are not needed in the GitHub Actions publisher: by post
time the public URL is already on the item. Without them, everything works
text-only. (The bucket already serves its objects publicly at
`r2_data_plane.public_base`; no new bucket and no ACL change is introduced — but
if you would rather not expose chart images on that domain, leave
`publish.media_enabled: false` and the whole path stays dark.)

---

## 13. "Post now" — breaking dispatch

Normally a post waits for its slot on the 2-hour Pacific ladder, and the publisher
sweeps every 2 hours to send whatever is due. **Post now** skips that wait.

**Where:** Admin → Marketing → Outbox → the **Post now** button on any card that
is still going out (undecided, held, or approved-and-waiting). Not offered on
posts that already went out, were quarantined, or are out of retries.

**What happens:** the admin dispatches `marketing-publish.yml` with the
`post_now_item` input. That run:

1. restricts itself to that one item — nothing else in the queue goes out with it;
2. approves it regardless of `publish.auto_approve` (your click is the approval);
3. skips the humanizing jitter (a breaking post should not sit out a random sleep);
4. hands Buffer a concrete **share-now** `dueAt` instead of `addToQueue` — the
   latter parks the post in *Buffer's own* queue at whatever slot it next offers,
   which is exactly the latency a breaking post cannot afford.

**It jumps the queue, not the checks.** Copy validation, the live tape gate, the
channel check, the daily cap and the 10-minute global floor all still run. If a
post went out 3 minutes ago, this one is booked for the 10-minute mark rather than
sent immediately — breaking budges in *under* the floor, it never overrides it.
How far ahead that booking may reach is `publish.immediate_defer_max_minutes`
(default 60); past that horizon the item defers to the next sweep as usual.

**Reading the result:** a breaking dispatch that posts nothing exits **non-zero**,
so the run shows RED in Actions rather than a silent green no-op. Open the run log
and read the gate lines (`held by tape gate`, `failed validation`, `no configured
channel id`, `deferred`). The publisher must be **armed** — the admin refuses the
dispatch outright while the kill-switch is off, because that run would dry-run and
post nothing.

**CLI equivalent** (same code path, for a local dry-run check):

```
python -m scripts.marketing_publisher --post-now ob-2026-07-25-15098c35f1
```

**Earnings auto-detect is NOT live.** The fast-lane daemon
(`scripts/marketing_fastlane_daemon.py` → `engine/marketing/fastlane.py`) is built
and emits `immediate` outbox items, and this dispatch path sends them the moment
they land — but its only event provider (`earnings_feed.FreePollProvider`, a
finviz RSS URL) now returns **HTTP 404**, and no runner is scheduled for the
daemon. There is also no source of earnings *actuals* in the repo
(`data/earnings/earnings.parquet` is a forward calendar: next date + EPS forecast).
Until a working earnings-results provider is wired, breaking is operator-driven
via the button above.

---

## 14. PRESS-FEEDS — Trump/markets wire ingestion spine (D05 Addendum 2, B1)

The **press lane** is the automated feed side of the "post now" rail: it detects
market-moving statements (Trump Truth-Social posts, wire headlines, allowlisted X
relays), scores them deterministically, gates them on corroboration, summarizes
them with citation, and emits `kind="breaking"` outbox items with
`scheduled_at: "immediate"` — which section 13's dispatch then sends. It is built
**dark**; nothing arms without the operator.

**Sources** (`config/press_sources.yml`):
- **wire_rss** — the six Fed/BLS/BEA/WH/CNBC/MarketWatch feeds, canonically
  configured in `config/marketing.yml` `breaking:` (`breaking_feed.poll_all`).
- **truth_mirrors** — `trumpstruth.org/feed` RSS (hot poll ~75 s, conditional GET,
  honest UA) as the primary Truth-Social detector; the CNN archive JSON
  (`ix.cnn.io/.../truth_archive.json`, 19 MB) as **backfill/corroboration only**
  (6 h cadence, conditional GET mandatory — never the hot loop).
- **x_follow** — the twitterapi.io read relay over an allowlist of wire/OSINT
  handles, tiered fast/mid/slow. **Requires `TWITTERAPI_IO_KEY`**; with the key
  unset the lane skips cleanly (no account is created for the build). Per-request
  accounting enforces the monthly `spend.twitterapiio_monthly_cap_usd` cap (default
  **$75**); at the cap the lane STOPS and emits a `::warning` in the Actions log.
- **alpaca** — WS wire slot, `enabled: false` until a key exists (build gate).

**Corroboration law** (`engine/marketing/press_corroboration.py`, addendum §3):
- **direct-quote** (Trump's own post, mirror-verified via the status URL) — a single
  primary source instant-publishes, attributed "on Truth Social".
- **hearsay** ("Trump told reporters…", bank-call/geopolitical relays) — needs **≥2
  independent sources within a window** to instant-publish, else it is downgraded to
  attributed "…reporting:" phrasing.
- A **single-wire uncorroborated political/geopolitical** claim NEVER
  instant-publishes — it is routed to the **digest** gate (see below).
- Satire/parody accounts (seed: **HalfwayPost**) are hard-blocked at ingestion.

> **Digest is logged-only in B1 (no sink yet).** A claim gated to `digest` is
> written to the tick log (`[press] -> digest (logged-only, no sink — m4) …`) and
> nothing more. There is **no next-morning digest surface** — no digest ledger, no
> roll-up post. A real digest sink is a **chartered follow-on**, not part of this
> spine. Read "falls to the digest" as "does NOT instant-publish", not as "queued
> for a digest that exists".

**Flagship interim lane.** Only the top **`wire.flagship_top_k_per_day`** (default 3)
highest-salience items/day, above `wire.flagship_salience_floor` (default 70), may
emit for the flagship account. The counter is persisted in the daemon's LOCAL state,
never the repo.

**Kill-switches (BOTH gate press emission).**
- `MARKETING_FASTLANE_ENABLED=1` — drives the daemon loop at all. Unset → the daemon
  prints a note and exits 0 (no work).
- `MARKETING_PUBLISH_ENABLED=1` — allows the press lane to WRITE outbox items. Unset
  → the pipeline still reads, scores, corroborates, and advances the Intelligence
  Desk/live rail, but emits nothing to the social outbox.

**Dry-run (no spend, no state writes, no billed reads — safe with switches off):**
```
python -m scripts.marketing_fastlane_daemon --lane press --once --dry-run
```
Prints the full would-emit pipeline (emitted/skipped/digest/blocked counts + a line
per would-emit item with salience + corroboration gate). `--dry-run` bypasses the
hard kill-switch exit precisely so the operator can inspect the pipeline while dark.

A dry-run is **non-consuming but not fully offline** (M2 clarification). Precisely:
- **No billed reads.** The twitterapi.io lane is billed per request and its spend
  is not persisted in a dry-run, so a dry-run **never touches** it
  (`poll_all(offline=True)` returns `[]` for it) — repeated dry-runs cost $0.
- **Free feeds still poll.** The wire RSS lane and the trumpstruth/CNN mirror feeds
  are free (no per-request charge); a dry-run may read them to preview the pipeline.
- **No state writes.** Provider cursors, spend accounting, the flagship counter,
  the seen-ledger, and the wire lane's own ledger are all left untouched (the wire
  ledger is snapshotted and restored), so a dry-run never dedupes items away from a
  later live run.
- **Disarmed parity.** With `MARKETING_FASTLANE_ENABLED` unset, a `--dry-run` of the
  **earnings** lane likewise does NOT reach `earnings_feed.fetch_events` (m1) — a
  disarmed inspection stays on offline-safe paths only.

**Local-only state** lives under `data/marketing/press/` (gitignored): provider
cursors, conditional-GET ETags, twitterapi.io spend accounting, the flagship
counter, the corroboration window, the development Intelligence Desk database,
and the seen-ledger. Production desk/rail snapshots live under
`/var/lib/macro-live/`, also outside Git. The poller makes **zero** git/repo writes
(D05 W0 law); the nightly is the sole advancer of any tracked forward ledger.

**Arming (operator, on the VPS):**
1. For the registered-user `news.html` Intelligence Desk + wire, add
   `MARKETING_FASTLANE_ENABLED=1` to `/etc/macro-live.env` and leave
   `MARKETING_PUBLISH_ENABLED` unset. The daemon polls the free sources plus the
   budget-capped twitterapi.io relay when its key is present, merges arrivals
   into a host-local SQLite story graph, and atomically publishes both
   `intelligence.json` and `wires.json`. It cannot write an outbound post.
   Add `MARKETING_PUBLISH_ENABLED=1` only when the outbound social-post lane is
   separately approved. `TWITTERAPI_IO_KEY=…` expands live intelligence coverage
   independently of that outbound switch; the configured monthly cap still
   fails closed. Explicit `--dry-run` is the non-consuming mode and therefore
   keeps the billed relay offline.
2. **For Chinese wire items on the news.html rail (B4c), also add `DEEPSEEK_API_KEY=…`.**
   It is NOT provisioned on the VPS today. Without it the lane still runs: items
   ship English-only and the rail marks them 「英文原文」 rather than faking a
   translation — but the daemon logs one `wires zh armed but DEEPSEEK_API_KEY is
   not set` warning per tick so the gap is visible instead of silent. The pass is
   also disarmable in config (`wire.zh_enabled: false` in `config/press_sources.yml`,
   which defaults to OFF in code — deleting the key disarms the spend).
   The lane keeps its translation cache under the gitignored
   `data/marketing/press/zh_cache/` and does NOT append to `data/ai_costs/usage.jsonl`
   (nightly is the sole ledger advancer); per-tick counts appear in the log line and
   in the `zh` block of the published `wires.json`.
3. Install the unit: `cp app/deploy/marketing-press-feeds.service /etc/systemd/system/`
   then `systemctl daemon-reload && systemctl enable --now marketing-press-feeds`.
   Once installed, `macro-update` keeps the reviewed unit aligned with `main` and
   restarts an active daemon when its import-cached press-lane code changes. It
   never installs, enables, or starts the service by itself, so the arming choice
   remains explicit.
4. Watch: `journalctl -u marketing-press-feeds -f` — one `[press] tick …` line per
   tick; emitted items appear in the outbox and ride section 13's dispatch.
5. Disarm the daemon/desk by unsetting `MARKETING_FASTLANE_ENABLED` (or with
   `systemctl disable --now marketing-press-feeds`). Unsetting only
   `MARKETING_PUBLISH_ENABLED` leaves intelligence ingestion, the story desk, and
   the wire running but stops outbound posts.

**Intelligence Desk V2 (2026-07-29) operator notes:**
- The same `DEEPSEEK_API_KEY` from step 2 also powers the desk's story-level
  Chinese twins (`headline_zh`/`brief_zh`, and the phrased why-line when the LLM
  pass produced one). Absent key → labeled-English fallback on every surface,
  same as the rail.
- **Alpaca/Benzinga news lane**: armed purely by env presence — add
  `ALPACA_API_KEY_ID=…` and `ALPACA_API_SECRET_KEY=…` to `/etc/macro-live.env`
  for the daemon; add the same two as GitHub repo secrets to arm the Actions
  wire lane (`marketing-press-wire.yml` already forwards them; unset secrets
  resolve to empty and the poller no-ops with one preflight notice). Free REST
  endpoint, one page per tick, cursor-primed so the first poll never floods.
- **Desk LLM drafts/why-phrasing** resolve `marketing_copy` through the same
  llm_models waterfall as the breaking summarizer — no new credentials, and the
  same two-key arming: config `wire.intelligence.llm.enabled` AND
  `MARKETING_LLM_ENABLED=1` in the daemon env (absent → the pass ships dark
  with one log notice, exactly like the press summarizer). Keyless hosts keep
  the deterministic drafts; every model output passes numeric / call-language /
  hedge / banned-language / AI-tell gates or is discarded, and gate-rejected
  phrasings are cached so the 75s tick never re-buys a known rejection.
- **Story-store self-heal**: a corrupted SQLite desk store is quarantined aside
  as `intelligence.db.corrupt-<utcstamp>` and rebuilt automatically (the desk
  re-accrues from live ticks; the wire is unaffected). Stray `.corrupt-*` files
  under `/var/lib/macro-live/state/intelligence/` are safe to delete after a
  look.
- **Content Studio "Queue for X"**: the operator click on a review draft runs
  the full outbox gate chain server-side and — on the deployed admin — delivers
  the queued row to `main` through the GitHub Contents API (the
  `accounts_toggle` precedent), so the Actions publisher sees it on its next
  sweep. `delivered: false` in the response means the item did NOT reach main
  (the note names why); nothing posts until a later approve lands it. Posting
  itself remains governed by the sentinel/publisher arm state, unchanged.
- **Code pickup**: `macro-update` already restarts the daemon when
  `engine/marketing/*` or the daemon script changes on main — no manual
  `systemctl restart` is needed after a merge.
- **`wire_rank.json` sidecar (Mastermind brain)**: the served rail
  (`live/wires.json`) deliberately carries no ranking number, so the brain's
  ranked view of the SAME window ships as a separate non-public file the daemon
  rewrites on every real tick, immediately after the wires sink. It lands at
  `$MACRO_LIVE_STATE_DIR/wire_rank.json` when that override is set, otherwise
  `/var/lib/macro-live/state/wire_rank.json` on the VPS and the gitignored
  `data/marketing/press/wire_rank.json` on a dev box — never the public live
  dir. It contains exactly `{schema, updated_at, ids}` and **no numbers at all**:
  element order is the entire ranking, so there is nothing leakable in it even
  at a non-public path. The reader ignores the file when `updated_at` is older
  than 45 minutes and falls back to recency, which is also what happens to any
  id the file does not list — so a stale or missing sidecar degrades quietly
  rather than blanking the brain's wire. Kill switch:
  `wire.rank_sidecar_enabled` in `config/press_sources.yml` (ships `true`;
  setting it false or deleting the key stops the write, the rail is unaffected).
  The ordering numbers themselves live only in the daemon's gitignored
  `data/marketing/press/state.json` under `wire_rank_order`.

The live-plane venv includes `datasketch`; without it the daemon still runs but
the scoring brain reports `story-spine-no-datasketch` and falls back to exact
story identity. Existing hosts provisioned before this dependency landed need
one `pip install datasketch` in `/opt/macro/.venv`.

**Twitterapi.io spend cap.** A `::warning title=twitterapiio-spend-cap::…` line in the
log means the monthly cap was hit and the X relay stopped for the month; the mirror
and wire lanes keep running. Raise `spend.twitterapiio_monthly_cap_usd` to lift it.

---

### Where to look when something is off

- **Admin → Marketing → Publisher** — arm state, status counts, recent posts +
  their Buffer receipt (`external_id`), and a prominent callout for anything
  stuck in `posting` (a crashed in-flight post — reported, never auto-reposted)
  or `quarantined` (with the reason). The dry-run button previews the next run.
- **`data/marketing/outbox/status_ledger.jsonl`** — the transition ledger
  (`approved → posting → posted`), each `posted` row carrying its receipt.
- **`data/marketing/outbox/activity.jsonl`** — per-run tallies
  (`publisher_live` / `publisher_dry_run`).
