# Deploy runbook — mastermind-x.com static origin (Slice 1)

Stands up the existing prebuilt `site/` on the DigitalOcean droplet
(`146.190.142.17`), served by Caddy behind Cloudflare, on **mastermind-x.com**.
This is the *additive serving tier* from `research/SAAS_MVP_PLAN.md` — it reads the
nightly build artifacts and changes nothing in the build pipeline.

**Status:** Slice 1 = serve the site over HTTPS (pre-launch, `noindex`). Product login
(Supabase) + API are Slice 2.

---

## Step 1 — grant SSH access (the one manual unblock)

The droplet only accepts SSH keys and none of the local keys are authorized yet.
Authorize the deploy key via the DigitalOcean **web console** (no SSH needed):

1. DigitalOcean → **Droplets** → your droplet → **Access** → **Launch Droplet Console**
   (opens a root terminal in the browser). If it asks for a root password you don't
   have, click **Reset Root Password** first (DO emails a new one), then log in.
2. In that console, paste this one line (this is the public half of
   `~/.ssh/macro_dashboard_deploy_v2` — safe to share; the private key never leaves the Mac):

   ```bash
   mkdir -p ~/.ssh && chmod 700 ~/.ssh && echo 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIEvwuDp7Wk+GYlooJjQl/0OPfubiCtSKswsNbIqQibX7 macro-dashboard-local-20260611' >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys && echo KEY_ADDED
   ```

That's it — once it prints `KEY_ADDED`, the agent can SSH in with
`ssh -i ~/.ssh/macro_dashboard_deploy_v2 root@146.190.142.17` and run everything below.

## Step 2 — Cloudflare settings (in the CF dashboard)

1. **DNS** → ensure an **A record**: `mastermind-x.com` → `146.190.142.17`, **Proxied**
   (orange cloud). Add `www` the same way (or a CNAME `www` → `mastermind-x.com`).
2. **SSL/TLS → Overview** → set encryption mode to **Full**
   (NOT "Full (strict)" — the origin uses Caddy's self-signed cert; strict would reject it).
3. (Optional, recommended for a private beta) **Zero Trust → Access → Applications** →
   add `mastermind-x.com` as a self-hosted app with an email-OTP policy. Instant
   zero-code login wall until the Supabase product auth ships in Slice 2.

## Step 3 — provision (agent runs this once Step 1 is done)

Public repo, so the droplet self-clones:

```bash
ssh -i ~/.ssh/macro_dashboard_deploy_v2 root@146.190.142.17 \
  'curl -fsSL https://raw.githubusercontent.com/chriswong6031-creator/macro/main/app/deploy/setup.sh | bash'
```

`setup.sh` is idempotent: installs Caddy, clones the repo to `/opt/macro`, installs the
Caddyfile, opens the firewall, starts Caddy, and adds a nightly `macro-update` cron that
`git pull`s the freshly-built site (~23:30 UTC weekdays, after the daily build lands).

## Step 4 — verify

```bash
# origin answers (self-signed -> -k):
curl -ksI https://146.190.142.17/ | head -5
# public domain via Cloudflare:
curl -sI https://mastermind-x.com/ | head -10        # expect 200 + x-robots-tag: noindex
```

## Files

| File | Role |
|---|---|
| `setup.sh` | idempotent provisioning (run as root on the droplet) |
| `Caddyfile` | serves `/opt/macro/site` with self-signed TLS + `noindex` |
| `update.sh` | `git pull` + Caddy reload (installed as `/usr/local/bin/macro-update`, cron'd) |

## Notes / gotchas

- **DO cloud firewall:** if the droplet is attached to a DO *cloud* firewall (separate
  from `ufw`), open 22/80/443 there too — `setup.sh` can't change that (dashboard only).
- **CF "Full" vs "Full (strict)":** self-signed origin needs **Full**. Upgrade path:
  install a Cloudflare Origin Certificate and switch `tls internal` →
  `tls /etc/ssl/cf-origin.pem /etc/ssl/cf-origin.key`, then set CF to "Full (strict)".
- **Disk:** the public repo carries `site/` (~395 MB) + `data/` (~367 MB); a depth-1
  clone is ~1 GB. Fine on a standard droplet; `data/` is already there for the Slice-2 API.
- **Pre-launch exposure:** the site is `noindex` but still publicly reachable until you add
  the Cloudflare Access gate (Step 2.3) or the Supabase login (Slice 2). Add the gate before
  sharing the URL if you don't want the full product open.
