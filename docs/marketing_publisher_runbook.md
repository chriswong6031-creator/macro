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

Two secrets arm it. In the GitHub repo settings (**Settings → Secrets and
variables → Actions**):

- `BUFFER_TOKEN` = the token from step 1
- `MARKETING_PUBLISH_ENABLED` = `1`

The scheduled workflow (`marketing-publish.yml`, weekday 14:00 / 17:30 / 20:15
UTC) then posts. To run once locally instead:

```
MARKETING_PUBLISH_ENABLED=1 BUFFER_TOKEN=<token> \
    python -m scripts.marketing_publisher --live --account flagship
```

The runner only posts when **both** the `--live` flag AND
`MARKETING_PUBLISH_ENABLED` are set — the flag alone downgrades to dry-run
(`scripts/marketing_publisher.py`: `live = bool(args.live) and kill_on`). That is
why the workflow can pass `--live` unconditionally and stay dark until you set
the secret.

## 7. KILL SWITCH / rollback

**Unset `MARKETING_PUBLISH_ENABLED`** (delete the repo secret, or unset the env
var locally). Every path — workflow, local runner, admin dry-run — instantly
reverts to dry-run and posts nothing. No code change, no deploy. This is the
first thing to reach for if anything looks wrong.

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

### Where to look when something is off

- **Admin → Marketing → Publisher** — arm state, status counts, recent posts +
  their Buffer receipt (`external_id`), and a prominent callout for anything
  stuck in `posting` (a crashed in-flight post — reported, never auto-reposted)
  or `quarantined` (with the reason). The dry-run button previews the next run.
- **`data/marketing/outbox/status_ledger.jsonl`** — the transition ledger
  (`approved → posting → posted`), each `posted` row carrying its receipt.
- **`data/marketing/outbox/activity.jsonl`** — per-run tallies
  (`publisher_live` / `publisher_dry_run`).
