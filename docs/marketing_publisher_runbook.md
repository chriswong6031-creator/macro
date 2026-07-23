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

## 10. COMPLIANCE

- Buffer posts via X's **official OAuth** — approved automation, not scraping.
- Keep content **genuinely differentiated per account** and **cadence varied**.
  Identical content across accounts is platform manipulation and the single
  biggest ban trigger. The desk-network personas (`config/marketing.yml
  copywriter.personas`) and the Sentinel near-duplicate gate exist to enforce
  this — do not defeat them.
- New accounts posting links, or the same link twice, is a documented X
  suspension trip; `sentinel.links_allowed` is false until the ramp allows it.

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
