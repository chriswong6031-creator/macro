# Support + email estate — operator setup (SEE W1)

The **code** ships in this repo and works today in **mail-off mode** — tickets file, threads
record, the operator console answers; nothing leaves the building until the relay below exists.

| Piece | Where |
|---|---|
| Schema (6 tables, deny-all RLS) | `scripts/deploy/0007_support_email.sql` |
| Mail transport + send ledger | `app/mailer.py` |
| Public ticket intake | `app/support.py` → `POST /api/support/ticket` (mounted in `app/main.py`) |
| Operator console | `admin/support_tickets.py` + admin console → **Support → Support Tickets** |
| Billing + lifecycle email (W3) | `app/billing_emails.py`, hooked from `app/billing.py::_handle_event` |
| Display preferences (W3) | `app/account_prefs.py` → `POST /api/account/prefs` |
| Secret delivery | `.github/workflows/deploy-api-secrets.yml` |
| Tests | `tests/test_mailer.py`, `tests/test_support_api.py`, `tests/test_admin_support_tickets.py` (CI job `support-email-spine`) · `tests/test_billing_emails.py`, `tests/test_account_prefs.py`, `tests/test_billing_webhook.py` (CI job `billing-emails`) |

Everything below is **operator ops** — one-time actions outside the repo.

---

## 1. Provider SMTP credentials + DNS

Pick a transactional relay (Resend, Postmark, SES, Mailgun — any authenticated SMTP submission
endpoint works; `app/mailer.py` is stdlib `smtplib`, no vendor SDK). Create a sending domain for
`mastermind-x.com`, then add the records the provider gives you.

**⚠️ ADD these records. Never REPLACE the existing `MX`.** The domain already receives mail
(see the `mastermind-x` DNS/mail notes); a sending provider only needs SPF/DKIM/DMARC, and
overwriting the MX would silently black-hole every inbound message including the support
replies users send back.

| Record | Type | Value | Note |
|---|---|---|---|
| `mastermind-x.com` | TXT (SPF) | merge the provider's `include:` into the **existing** SPF record | one SPF TXT per domain — merge, never add a second |
| `<selector>._domainkey.mastermind-x.com` | TXT/CNAME | as issued by the provider | DKIM |
| `_dmarc.mastermind-x.com` | TXT | `v=DMARC1; p=none; rua=mailto:dmarc@mastermind-x.com` | start at `p=none`, tighten to `quarantine` after a week of clean reports |

Verify in the provider's dashboard before step 2 — an unverified domain sends, but lands in spam.

## 2. Deliver the secrets to the droplet

Add these as **GitHub repository secrets**, then run the **deploy-api-secrets** workflow
(Actions → *deploy-api-secrets* → *Run workflow*). It writes them to `/etc/macro-api.env`
**and** `/etc/macro-admin.env` and restarts both services. Absent secrets are simply omitted —
that is mail-off mode, not an error.

| Secret | Required | Meaning |
|---|---|---|
| `MAIL_SMTP_HOST` | yes | relay hostname |
| `MAIL_SMTP_PORT` | no | defaults to `587` (STARTTLS). `465` selects implicit TLS |
| `MAIL_SMTP_USER` | yes | relay username / API key id |
| `MAIL_SMTP_PASS` | yes | relay password / API key |
| `MAIL_FROM` | yes | envelope + header From, e.g. `hello@mastermind-x.com` |
| `MAIL_REPLY_TO` | no | where user replies land, e.g. `support@mastermind-x.com` |
| `MAIL_SUPPORT_TO` | no | where NEW-ticket alerts go. Unset → no operator alert (tickets still file) |
| `MAIL_UNSUB_SECRET` | no | HMAC key for one-click unsubscribe tokens. **Also keys the ticket IP hash** — set it: without it the stored `meta.ip_hash` is a bare SHA-256 of an IPv4, which is a 2^32 brute force, i.e. not anonymisation |
| `MAIL_BILLING_ENABLED` | no | **default ON**, so receipts work the moment the relay lands. `0` silences billing receipts + the trial reminder **without** stopping support/ticket mail — the kill switch for a misbehaving receipt. Only `1/true/yes/on` and `0/false/no/off` are recognised; **anything else resolves to OFF** (a kill switch must not fail open on a typo), and the parsed verdict is logged once at startup |
| `MAIL_LIFECYCLE_ENABLED` | no | **default OFF.** `1` arms the in-process trial-ending sweeper (§5b). Leave unset until the relay is verified — the billing receipts do not need it |
| `MAIL_LIFECYCLE_INTERVAL_SEC` | no | sweeper wake interval, default `21600` (6h). Floor 60s. Only for a smoke test — the reminder window is 48h wide, so four wakes a day is plenty |
| `MAIL_SITE_BASE` | no | public host used in email links, default `https://www.mastermind-x.com`. Only set this if the public host moves |

All four SEE W3 switches ride the same **deploy-api-secrets** lane as the relay creds —
they are in the workflow's env block, its `_add` list, and its strip regex, so re-running
it replaces rather than duplicates their lines in `/etc/macro-api.env`.

Prefer a **bare address** for `MAIL_FROM` / `MAIL_REPLY_TO`. A display-name form
(`Mastermind <hello@…>`) is delivered intact — the workflow's `_addv` helper preserves inner
spaces where the older `_add` would strip them — but a bare address has no quoting edge cases in
a systemd `EnvironmentFile`.

`is_configured()` requires **host + user + pass + from**. A partial config counts as mail-off on
purpose: half a relay produces a slow timeout on every request, which is worse than an honest skip.

Both services need these because there are two senders: **macro-api** sends the operator's
new-ticket alert, and the **admin** console sends ticket replies.

Manual equivalent, if you would rather not use the workflow:

```bash
# on the droplet, then: systemctl restart macro-api admin
printf 'MAIL_SMTP_HOST=...\nMAIL_SMTP_USER=...\nMAIL_SMTP_PASS=...\nMAIL_FROM=hello@mastermind-x.com\n' \
  >> /etc/macro-api.env
```

## 3. Apply the migration

Supabase dashboard → **SQL editor** → paste and run `scripts/deploy/0007_support_email.sql`
(the 0005/0006 precedent — there is no migration runner on the render path). Idempotent, safe to
re-run. It creates `support_tickets`, `support_ticket_messages`, `email_log`, `email_prefs`,
`email_suppression`, `email_campaigns`, their indexes, and **deny-all RLS on all six** — no client
policy exists, so the browser can neither read nor write. Every reader/writer is server-side:

* `app/support.py` and `app/mailer.py` — service-role PostgREST (`SUPABASE_SERVICE_ROLE_KEY`,
  already present in `/etc/macro-api.env` for analytics/brain).
* `admin/support_tickets.py` — Supabase **Management-API SQL** with the `SUPABASE_ACCESS_TOKEN`
  PAT the admin already holds. **No new admin secret is needed.**

`SUPABASE_SERVICE_ROLE_KEY` is delivered to **both** envs by the same workflow, so operator
replies are ledgered like every other send. If it is ever missing from `/etc/macro-admin.env`,
`app/mailer.py` logs `ledger unavailable … sending WITHOUT idempotency` and sends anyway —
deliberate for transactional mail, because a lost support reply is a real product failure and a
rare duplicate is an annoyance. Grep for that line if you suspect the reply lane is unledgered.

## 3b. Caddy: the body cap and the unspoofable rate-limit key

Two edge-only protections for the public intake live in `app/deploy/Caddyfile`:

* `request_body /api/support/* { max_size 64KB }` — the REAL body cap. The app also refuses an
  oversized declared `Content-Length`, but a chunked request declares none, so only the edge —
  which sits before the body is read — can actually enforce a limit. Scoped to `/api/support/*`,
  deliberately not the whole `/api/*` tree, so it can never truncate a Stripe webhook or an
  analytics batch.
* `header_up X-MM-Peer {remote_host}` on the `/api/*` proxy — every real-client header the app can
  read (`EO-Client-IP`, `CF-Connecting-IP`, `X-Forwarded-For`) is attacker-suppliable at the
  origin, so a bot that rotates one gets a fresh rate-limit bucket per request. `header_up`
  **replaces** any inbound `X-MM-Peer` with the real TCP peer, giving `app/support.py` one key a
  client cannot forge. Same mechanic as `X-Admin-Client-IP` on the admin host.

**Getting it live:** `app/deploy/update.sh` — installed as `/usr/local/bin/macro-update` and run
by cron — compares the repo's Caddyfile to `/etc/caddy/Caddyfile` and, **only when it differs and
only if `caddy validate` passes**, installs it and runs `systemctl reload caddy` (falling back to
`restart`). So merging to `main` is enough; a broken config can never take the site down, it just
refuses to install. To apply immediately instead of waiting for cron, run `macro-update` on the
droplet.

## 4. Mail-off mode (what "not configured yet" looks like)

With no relay credentials the whole estate still works:

| Surface | Behaviour |
|---|---|
| `POST /api/support/ticket` | 200, ticket + first message written, `ok:true` with a `ticket_id` |
| Operator alert | `email_log` row with `status='skipped_no_smtp'`; no send attempted |
| Console reply | message appended, thread shows a **"not emailed"** pill, toast says so |
| Billing webhook | `POST /api/billing/webhook` still returns **200**, entitlement still written; one `email_log` row per event at `status='skipped_no_smtp'` |
| `MAIL_BILLING_ENABLED=0` | **NOT the same as mail-off.** The send is abandoned before the ledger is touched, so there is **no `email_log` row at all** — a suppressed receipt is invisible in the ledger, and `select status, count(*) from email_log` will not show it. The upside is that nothing is "already handled": flipping the switch back ON restores mail for every *future* event, with no rows to clean up. Only the receipts suppressed while it was off are unrecoverable |
| Trial sweeper | ledgers every candidate as `skipped_no_smtp` — the period is then "already handled", so turning the relay on later does NOT backfill that period. This is why `MAIL_LIFECYCLE_ENABLED` stays off until the relay is verified |
| `send()` return | `'skipped_no_smtp'` — never an exception, never a 500 at a caller |

One asymmetry to know about once campaigns exist (W4): **marketing mail is fail-closed on the
suppression lookup.** If `email_suppression` / `email_prefs` cannot be read, the message is NOT
sent — its ledger row is parked at `status='queued'` with `detail='suppression_lookup_failed'`,
and the W4 drain completes it later by PATCHing that row. Mailing someone who unsubscribed
because Supabase blinked is a compliance problem; a delayed campaign is not. Transactional mail
never consults those tables at all, so a ticket reply is never delayed by this.

Nothing is silently dropped: every attempt lands a ledger row, and the thread tells the truth about
what left the building.

## 5. Keep Stripe's own customer emails OFF (SEE-R8)

Stripe Dashboard → **Settings → Customer emails** → leave *Successful payments* and *Refunds*
**disabled**, and **Settings → Billing → Subscriptions and emails** → leave the dunning/renewal
reminders **disabled**.

We send our own receipts and dunning notices from this estate. Turning Stripe's on produces two
emails per event with different branding, different language (Stripe's are English-only — half our
audience reads 中文), and no `email_log` row, so the ledger stops being the record of what a user
received.

Those toggles are **dashboard-only** — there is no API to read or set them, so this is a step an
operator has to perform and re-check by eye. The full audit of what Stripe would send, and when,
is in `docs/ops/stripe-setup.md` (§ *Customer email*).

## 5b. Billing emails + the trial-ending reminder (SEE W3)

Four messages fire from the **Stripe webhook**, composed in `app/billing_emails.py` and hooked
into `app/billing.py::_handle_event` **after** the entitlement upsert — the database row is the
source of truth and mail is a side effect. Nothing about the money is hardcoded: amounts,
currencies and dates come off the Stripe objects, plan names and the tier ordering come from
`config/plans.yml`.

| Stripe event | Email | Notes |
|---|---|---|
| `customer.subscription.created` | purchase / trial confirmation | plan, price, trial end, first-charge date + amount, the period it covers |
| `customer.subscription.updated` (`cancel_at_period_end` true) | **cancellation scheduled** | the portal is configured `mode = at_period_end`, so this — not `deleted` — is what a user pressing *Cancel* actually emits. Access-until date + how to undo |
| `customer.subscription.updated` (tier/cadence up) | plan upgrade | only when the tier RANK rose or the cadence moved monthly → annual, and only from an already-paid tier |
| `invoice.payment_failed` | payment failed | **first attempt only** — see below. Amount, what still works and until when, the retry schedule |
| `customer.subscription.deleted` | **access ended** | the day the cancellation took effect. Distinct copy from the scheduled email, and how to resubscribe |

**Two cancellation emails is correct, not a bug.** A customer who cancels in the portal
gets "your plan is cancelled, you keep access until 1 Dec" on the day they press the
button, and "your access has ended" on 1 Dec. They are different facts at different
times. Both are keyed on the subscription (`…:cancel_sched:{date}` and `…:cancel_final`),
so the dozens of unrelated `subscription.updated` events in between send nothing, an
un-cancel is silent, and so is a re-cancel that does not move the date. An upgrade taken
*after* a cancellation is scheduled still gets its own receipt — the flag stays set on
the subscription, so the upgrade comparison is evaluated first.

**Dunning mails once per invoice, not once per retry.** Stripe emits
`invoice.payment_failed` again for every Smart Retry, each with its own event id, so the
event-scoped key cannot collapse them. We send on `attempt_count == 1` only, key the
ledger row on the **invoice** id, and the copy states the whole retry schedule up front —
so a customer with a dead card gets one honest message, not four identical ones. The
terminal outcome arrives as the cancellation email above.

**Upgrade copy never asserts an immediate charge.** `POST /api/billing/upgrade` bills the
proration on the spot (`always_invoice`); the customer portal is configured
`create_prorations`, where the same arithmetic settles on the NEXT invoice
(`scripts/stripe_bootstrap.py`, docs/ops/stripe-setup.md §5). Both arrive as the same
webhook event, so the email states *what* happens to the money and points at billing
history for the exact adjustment — it only says "charged … today" when the event carries
an expanded, paid, non-zero invoice proving it.

**`checkout.session.completed` deliberately sends nothing.** The estate has two buy lanes —
hosted Checkout and the Elements sheet (`POST /api/billing/subscribe/complete`) — and only the
first produces that event, while **both** produce exactly one `customer.subscription.created`.
Keying the receipt off `created` covers both lanes once; handling both events would send the
hosted-Checkout buyer two receipts, because the idempotency key is per *event id* and the two
events have different ones.

**Idempotency** is `email_log.idem_key = stripe:{event_id}:{template}`, written BEFORE the SMTP
attempt. A replayed webhook event therefore sends nothing a second time. This is a separate key
from the `stripe_events` ledger on purpose: that row is only written after a *successful* handle,
so a crash between the send and that write would otherwise re-send.

### The trial-ending reminder (T-2)

A sweeper finds `user_entitlements` rows with `status='trialing'` whose `current_period_end` lands
inside the next 48 hours and sends the "your trial ends" message, keyed
`trial_ending:{user_id}:{period_end_date}` — re-armable for a later trial, never twice for the
same period. It is **behaviour-triggered**, not a drip: no calendar chain, no follow-ups.

**Home: an in-process asyncio task in macro-api, default OFF.**

1. Set `MAIL_LIFECYCLE_ENABLED=1` as a repository secret and run **deploy-api-secrets** (§2). The
   value is read at mount time, so the workflow's `systemctl restart macro-api` is what arms it.
2. Confirm — the log says which state it booted in, so "off by choice" and "the env never
   reached the droplet" are never confused:
   ```
   journalctl -u macro-api -n 200 | grep 'lifecycle sweeper'
   ```
   | What you see | What it means |
   |---|---|
   | `lifecycle sweeper armed (every 21600s)` | armed — you are done |
   | `lifecycle sweeper not enabled (MAIL_LIFECYCLE_ENABLED='')` | the code is deployed and nothing was delivered. If you meant to arm it, the secret did not land — check step 1 |
   | `lifecycle sweeper not enabled (MAIL_LIFECYCLE_ENABLED='Y')` | the secret DID land but the value is not one we accept. Use `1`/`true`/`yes`/`on` and re-run the workflow. (The `grep -c` below would have said "delivered" — this line is what tells the two apart.) |
   | **no line at all** | this build predates SEE W3, or macro-api did not restart. `systemctl restart macro-api` and look again |

   The line always prints the RAW value, so an unrecognised setting is never mistaken for
   an absent one.

   Belt-and-braces, confirm the value actually reached the box:
   `ssh root@<vps> "grep -c '^MAIL_LIFECYCLE_ENABLED=' /etc/macro-api.env"` → `1`.
3. Watch it work: `journalctl -u macro-api | grep 'trial sweep'` prints a per-wake census
   (`scanned / sent / duplicate / skipped / failed`).
4. To run one sweep by hand at any time (it is the same function, and the ledger makes it safe to
   run alongside the loop):
   ```
   cd /opt/macro && /opt/macro-api/.venv/bin/python -m app.billing_emails --sweep
   ```

*Why in-process rather than a crontab line beside the nightly `--reconcile`:* the sweeper is
cursor-free and idempotent through `email_log`, so a restart mid-sweep costs nothing and there is
no state a cron lane would protect. `macro-api` runs as a single uvicorn process under systemd,
so the loop runs exactly once. The env var already rides the secrets lane you use in §2, which
makes arming it one workflow run instead of an ssh session and a crontab edit on a box whose
checkout is ephemeral (G7). The `--sweep` CLI stays available for a manual run and for recovery.

### `POST /api/account/prefs`

`templates/account.js` has always called this route on theme/language change and nothing answered.
`app/account_prefs.py` now does: bearer-authed (a `user_id` in the body is ignored), it validates
`lang ∈ {en, zh}` and `theme ∈ {light, dark}`, merges them into the Supabase auth `user_metadata`,
and mirrors `lang` into `email_prefs.lang`. Emails are dual-language today (SEE-R4); the mirror is
the plumbing that makes a single-language send possible later without a migration. `GET
/api/account` returns the stored values as `prefs`, so a signed-in visitor lands in their own theme
and language on any device. No operator step — it works as soon as the migration from §3 is applied.

## 5c. Marketing email — the eight W4 switches, and the volume they buy (SEE W4)

`app/marketing_emails.py` runs three legs on one in-process sweeper in macro-api: the
**welcome** mail, the **campaign** drain, and the **parked-row** drain that finishes rows the
fail-closed suppression check left behind. All three are **OFF by default** and every one of
them needs `MAIL_MARKETING_ENABLED` **plus** its own switch.

**Do not arm `MAIL_MARKETING_ENABLED` on a build that predates the W4 review fixes.** On the
merged-but-unreviewed W4 code, arming the welcome leg with the relay still off would have
claimed `welcome:{user_id}` in `email_log` for every account in the window and PATCHed each
row to the terminal `skipped_no_smtp` — spending the idempotency key without ever writing a
message, so those people could never be welcomed and the census would have said `sent: N`.
The current code **refuses to run either sending leg when `mailer.is_configured()` is false**
and returns `not_configured: true` instead, so nothing is claimed. Confirm you are past that
before arming: `journalctl -u macro-api | grep 'refusing to run'` prints the refusal, and
`python -m app.marketing_emails --window` reports the bound in force without sending anything.

| Secret | Default | What it does, and what happens when it is unset or malformed |
|---|---|---|
| `MAIL_MARKETING_ENABLED` | **OFF** | The master switch for all three legs. Off ⇒ the sweeper is never even mounted, and the startup log says so. Only `1/true/yes/on` count; anything else is OFF |
| `MAIL_WELCOME_ENABLED` | **OFF** | Arms the welcome leg. Needs the master switch too. Off ⇒ no welcome is sent **and** a parked welcome row is left alone rather than completed |
| `MAIL_CAMPAIGNS_ENABLED` | **OFF** | Arms the campaign drain, and likewise gates a parked *campaign* row |
| `MAIL_WELCOME_AFTER` | **unset ⇒ ZERO candidates** | **The deliberate arming switch, and the one with teeth.** An ISO date or datetime; only accounts created strictly after it are ever candidates. Unset means **nobody** — not "everyone", not "since boot" — so arming `MAIL_WELCOME_ENABLED` without setting it sends nothing at all, which is the correct behaviour for a half-finished rollout and the one that cannot be regretted. **A typo is treated exactly like unset**, for the same reason: a date that fails to parse must not silently become the epoch and mail every account that has ever existed. Set it to the day the feature went live. It rides `_addv` in the deploy workflow, so a value with a space (`2026-07-26 12:00:00`) survives delivery intact |
| `MAIL_WELCOME_LOOKBACK_HOURS` | `72` | The second bound, ANDed with the floor: the LATER of the two wins, so a sweeper that was off for a year still only looks at the last 72h. Clamped to 1h…30d; junk falls back to 72 |
| `MAIL_THROTTLE_PER_MIN` | `30` | **The only ceiling on volume.** One shared pacer across all three legs: every message that reaches the relay is followed by a `60 / MAIL_THROTTLE_PER_MIN` second gap. Clamped to 1…600; junk falls back to 30 |
| `MAIL_MARKETING_INTERVAL_SEC` | `900` | How long the sweeper sleeps between wakes (it sleeps FIRST, so a crash-restart loop can never become a send loop). Floor 60s; junk falls back to 900. See the volume note below — it no longer multiplies anything |
| `MAIL_UNSUB_MAILTO` | unset ⇒ the https URI alone | Adds a `<mailto:…>` alternative in front of the https one in `List-Unsubscribe`. Optional but real: it is the only route that still works for a reader whose client will not make the POST. Unset is not a defect — the header is then byte-identical to what W1 shipped |

Two pre-existing secrets from §2 become load-bearing the moment anything marketing-class is armed:

| Secret | Why it matters here |
|---|---|
| `MAIL_UNSUB_SECRET` | Keys the one-click unsubscribe token. Unset ⇒ `unsub_token` returns `""`, so marketing mail ships with **no `List-Unsubscribe` header and no footer link** — a CAN-SPAM problem, not a cosmetic one. Set it before arming. Rotating it invalidates every link already sent. The token is scoped to one ACTION, so the link in a footer authorises `unsubscribe` and can never be replayed as a re-subscribe |
| `MAIL_SITE_BASE` | The host in those links. A wrong value points every unsubscribe link in every marketing email at somewhere that cannot honour it |

### The worst-case volume, with the number that actually controls it

Per wake the caps are module constants, not env knobs (an operator who needs a bigger blast
radius should have to change code and get it reviewed): **200** welcomes, **500** campaign
recipients, **500** parked rows — 1,200 messages.

**As W4 merged**, only the campaign drain was throttled. The reviewer's arithmetic for the
defaults was therefore **≤4,600 messages/hour** (4 wakes × [200 welcome + 500 parked]
ungated = 2,800, plus 30/min × 60 = 1,800 throttled), of which **≤800 welcomes** — and
`MAIL_MARKETING_INTERVAL_SEC`, not `MAIL_THROTTLE_PER_MIN`, was the multiplier: dropping it
to its 60s floor took the ceiling to **~43,800/hour**. That is the number to know if you are
looking at an older build.

**Now the pacer is shared by all three legs**, so the wake interval no longer multiplies
anything and the ceiling is one multiplication:

> **messages/hour ≤ `MAIL_THROTTLE_PER_MIN` × 60**, whatever `MAIL_MARKETING_INTERVAL_SEC` is.

| `MAIL_THROTTLE_PER_MIN` | Hourly ceiling | Note |
|---|---|---|
| `30` (default) | **≤ 1,800** | ~1,310/h in practice at the default 900s interval, because a full 1,200-message wake takes 40 min of pacing and then still sleeps 15 min |
| `10` | ≤ 600 | what to use for the first armed night |
| `120` | ≤ 7,200 | only with a warmed sending domain |
| `600` (max) | ≤ 36,000 | effectively unpaced; do not |

`MAIL_MARKETING_INTERVAL_SEC` now only decides **latency** — how long a new signup waits for
its welcome — not throughput. Lowering it to 60s does not raise the ceiling.

### Arming order

1. `MAIL_UNSUB_SECRET`, then the relay creds from §2, then verify a real send lands (§6).
2. `MAIL_MARKETING_ENABLED=1` alone — nothing sends; confirm the sweeper armed:
   `journalctl -u macro-api | grep 'marketing: sweeper armed'`.
3. `MAIL_WELCOME_AFTER=<today, ISO>` **and** `MAIL_WELCOME_ENABLED=1`, with
   `MAIL_THROTTLE_PER_MIN=10` for the first night. Watch `grep 'welcome sweep'` — the census
   prints `scanned / sent / duplicate / skipped / skipped_no_smtp / failed`, and
   `skipped_no_smtp` has its own column precisely so mail-off can never read as success.
4. `MAIL_CAMPAIGNS_ENABLED=1` last, and only once a campaign has been previewed in the
   Email Center. A campaign that is larger than one wake stays `sending` across wakes and
   only becomes `done` when its audience is exhausted — `sent_n + skipped_n + failed_n`
   against the operator's `queued_n` is the progress read.

## 6. Verify

1. `curl -sS -X POST https://mastermind-x.com/api/support/ticket -H 'content-type: application/json' -d '{"email":"you@example.com","topic":"other","subject":"relay smoke test","message":"checking the support spine end to end"}'`
   → `{"ok":true,"ticket_id":"…"}`
2. Admin console → **Support → Support Tickets** → the ticket is listed, `open`, with a nav dot.
3. Open it, send a reply → the thread shows an **emailed** pill and the message arrives.
4. Supabase → `select status, count(*) from email_log group by 1;` → `sent`, not `failed`.

If step 3 shows **not emailed**, read `journalctl -u admin -n 50 | grep mailer` — the status
(`skipped_no_smtp`, `failed`) and the exception **class** are logged. Bodies and credentials never
are, by design.

---

## Appendix — what the operator console looks like

Captured against the real `admin` server with fixture rows (only the Management-API SQL seam
`admin.users._query` was stubbed; routes, `app.js`, and `styles.css` are production code).

**List** — status chips with live counts, search, and the tier/lang/topic snapshot columns.
The **Support** nav group sits between Growth and System, with an open-ticket count dot.

![Support Tickets list](img/support-console-list.png)

**Thread** — user and operator messages offset from each other, the `emailed` pill, the reply
composer, and only the actions that are legal for an `open` ticket.

![Support ticket thread](img/support-console-thread.png)

**Closed ticket** — no composer at all, a plain-word explanation, and only `Reopen`.

![Closed support ticket](img/support-console-closed.png)
