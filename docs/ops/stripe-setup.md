# Stripe billing spine — operator setup (MNZ W2)

The **code** for the billing spine ships in this repo and is verified in Stripe **test mode**:

| Piece | Where |
|------|------|
| Stripe products/prices/features bootstrap | `scripts/stripe_bootstrap.py` (idempotent; reads `config/plans.yml`) |
| Pricing catalog (single source of truth) | `config/plans.yml` |
| Checkout + webhook + portal + reconciler | `app/billing.py` (mounted in `app/main.py`) |
| Entitlement store + RLS + event ledger | `scripts/deploy/0005_user_entitlements.sql` |
| Entitlement read path (already live) | `engine/neuralweb/brain_gateway.py::_resolve_tier` |
| Plan/entitlement API | `GET /api/me`, `GET /api/account` |
| Admin visibility | admin console → **Users** panel → *Subscribers* |

Everything below is **operator ops** — one-time actions outside the repo. Do it all in **test
mode** first; live-mode is gated by **W-LEGAL** (business entity, tax registrations, disclaimers).

---

## 1. Create the Stripe objects (already done in test mode)

`scripts/stripe_bootstrap.py` was run against the test key and created (re-run any time — idempotent):

| lookup_key | product | price |
|---|---|---|
| `insider_monthly` | Insider | $69 / month |
| `insider_annual`  | Insider | $588 / year ($49/mo equivalent) |
| `pro_monthly`     | Pro     | $99 / month |
| `pro_annual`      | Pro     | $828 / year ($69/mo equivalent) |

Features `site_full`, `terminal_live_options`, `chat_opus` are created and attached to the products.
Application code addresses prices by **lookup_key**, so the same code works against the live objects
you create later. To (re)create in any account:

```bash
STRIPE_SECRET_KEY=sk_test_... python scripts/stripe_bootstrap.py            # test
STRIPE_SECRET_KEY=sk_live_... python scripts/stripe_bootstrap.py --allow-live   # live (after W-LEGAL)
```

## 2. Run the Supabase migration

Supabase dashboard → **SQL editor** → paste and run `scripts/deploy/0005_user_entitlements.sql`.
Creates `public.user_entitlements` (+ RLS: user reads own row, only service-role writes) and
`public.stripe_events` (webhook idempotency ledger). Idempotent — safe to re-run.

## 3. Add secrets to the droplet

Append to `/etc/macro-api.env` (NOT git), then `systemctl restart macro-api`:

```
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...          # from step 4
SUPABASE_SERVICE_ROLE_KEY=...            # likely already present (analytics/brain use it)
MM_SITE_BASE=https://mastermind-x.com
STRIPE_AUTOMATIC_TAX=1                    # or 0 until Stripe Tax origin is configured (step 6)
```

The **publishable key is not needed** anywhere — the hosted-Checkout redirect flow never loads
Stripe.js in the browser.

## 4. Create the webhook endpoint

Stripe Dashboard → **Developers → Webhooks → Add endpoint**:

- **URL:** `https://<macro-api-host>/api/billing/webhook` (the macro-api origin behind Caddy, e.g. `https://api.mastermind-x.com/api/billing/webhook`).
- **Events to send:**
  `checkout.session.completed`, `customer.subscription.created`, `customer.subscription.updated`,
  `customer.subscription.deleted`, `invoice.payment_succeeded`, `invoice.payment_failed`,
  `charge.refunded`, `charge.dispute.created`, `entitlements.active_entitlement_summary.updated`.
- Copy the **Signing secret** (`whsec_...`) → `STRIPE_WEBHOOK_SECRET` (step 3) → restart the service.

## 5. Configure the Customer Portal

Dashboard → **Settings → Billing → Customer portal**: allow the Insider/Pro products, enable
cancel + plan switching. `GET /api/billing/portal` returns a portal session for the signed-in user.

## 6. Stripe Tax

Dashboard → **Settings → Tax**: set the origin address + registrations. Until configured, set
`STRIPE_AUTOMATIC_TAX=0` so Checkout sessions don't error; flip to `1` once Tax is live.

## 7. Deploy + reconciler cron

- On the droplet: `pip install -r app/requirements.txt` in the macro-api venv (adds `stripe`), then `systemctl restart macro-api`.
- Nightly reconciler (backstop for missed webhooks) — add to the VPS crontab (off the render path):
  ```
  17 4 * * *  cd /opt/macro && /opt/macro-api/.venv/bin/python -m app.billing --reconcile >> /var/log/macro-billing-reconcile.log 2>&1
  ```

---

## Verify (test mode)

1. Signed-in user opens `/plans.html` → **Subscribe** → Stripe Checkout. Pay with test card
   `4242 4242 4242 4242`, any future expiry/CVC.
2. Webhook fires → a row appears in `user_entitlements` (tier `insider`/`pro`, status `trialing`).
3. `GET /api/me` (with the user's bearer token) reflects the new `tier` + `features`.
4. Customer Portal → cancel → within seconds `/api/me` downgrades to `free` (cache-bust on the
   `subscription.deleted`/`updated` event).
5. Admin console → Users → **Subscribers** lists the row.

Local webhook testing without deploying: `stripe listen --forward-to localhost:8000/api/billing/webhook`
then `stripe trigger checkout.session.completed`.

## Go-live checklist (after W-LEGAL clears)

- [ ] W-LEGAL done (entity, tax registrations, ToS/privacy/disclaimer, vendor redistribution).
- [ ] Re-run `scripts/stripe_bootstrap.py --allow-live` with the **live** secret key.
- [ ] Live webhook endpoint + live `whsec_` in `/etc/macro-api.env`.
- [ ] Swap `STRIPE_SECRET_KEY` to `sk_live_...`; restart.
- [ ] **Rotate** any test key that was ever pasted into a chat/log (Dashboard → API keys → roll).
