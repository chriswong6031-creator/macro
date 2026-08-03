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

### Install the live plane

After the base site/API is provisioned:

```bash
ssh -i ~/.ssh/macro_dashboard_deploy_v2 root@146.190.142.17 \
  'bash /opt/macro/app/deploy/live-setup.sh'
```

This installs three resource-bounded systemd lanes and publishes their browser
artifacts under `/var/lib/macro-live/public`. See
[`docs/VPS_LIVE_ORCHESTRATION.md`](../../docs/VPS_LIVE_ORCHESTRATION.md) for
ownership, capacity, validation, and cutover details. Do not set the repository
variable `VPS_LIVE_PRIMARY=true` until the timers have passed a full-session soak.

### Attach Codex to the production provider pool

`api-setup.sh` and `macro-update` install the pinned official Codex CLI through
`codex-runtime-setup.sh`. Authentication is machine-local state, not a repository
secret. Each ChatGPT account gets its own root-only `CODEX_HOME`; authorize the
primary and second accounts independently:

```bash
ssh -tt -i ~/.ssh/macro_dashboard_deploy_v2 root@146.190.142.17 \
  'CODEX_HOME=/var/lib/macro-codex codex login --device-auth'

ssh -tt -i ~/.ssh/macro_dashboard_deploy_v2 root@146.190.142.17 \
  'CODEX_HOME=/var/lib/macro-codex-2 codex login --device-auth'
```

Complete the one-time code at `https://auth.openai.com/codex/device`, then verify:

```bash
ssh -i ~/.ssh/macro_dashboard_deploy_v2 root@146.190.142.17 \
  'CODEX_HOME=/var/lib/macro-codex codex login status && \
   CODEX_HOME=/var/lib/macro-codex-2 codex login status'
```

The deployed services expose both stores through `CODEX_ACCOUNT_HOMES`. Model
Desk reports them as `codex_account` and `codex_account_2`, and the provider
router prefers the healthy account with the lower observed quota-window load.
Their Claude OAuth credentials remain in their respective root-only environment
files; no login cache or refresh token is copied from the Mac or into Git.

## Step 4 — verify

```bash
# origin answers (self-signed -> -k):
curl -ksI https://146.190.142.17/ | head -5
# public domain via Cloudflare:
curl -sI https://mastermind-x.com/ | head -10        # expect 200 + x-robots-tag: noindex
```

## Press properties (W1.5) — cutover runbook

The two press publications (`mastermindx.ai`, `blog.mastermind-x.com`) ship
**dark**: the static trees are built and synced to the box, and nothing serves
them until the cutover. The serving half lives in `Caddyfile` between the
`PRESS-CUTOVER-BEGIN` / `PRESS-CUTOVER-END` marker lines, fully commented out.

`update.sh` already rsyncs `properties/news` → `/opt/macro/press_news.served`
and `properties/research` → `/opt/macro/press_research.served` on every repo
update (same atomic-rename + `--min-size=1` protections as `site.served`), so by
cutover day the content is already on disk.

**Do these in order. DNS first — the config half without the DNS half is a
claim nobody verified.**

1. **DNS (Spaceship, the registrar for both zones).** Add A records pointing at
   the droplet:

   | Host | Type | Value |
   |---|---|---|
   | `mastermindx.ai` (`@`) | A | `146.190.142.17` |
   | `www.mastermindx.ai` | A | `146.190.142.17` |
   | `blog.mastermind-x.com` | A | `146.190.142.17` |

   `www` still needs its own A record even though it only redirects — it has to
   terminate TLS before it can serve the 301, so Caddy needs to reach it over
   HTTP-01 to issue a certificate. The apex is the canonical host (it is what
   `config/press.yml` `base_url` names); www 301s to it.

   These are **grey-cloud / direct** records — no CDN in front, exactly like
   `admin.mastermind-x.com`. Caddy will therefore issue **real Let's Encrypt**
   certificates over HTTP-01 (never `tls internal` for these hosts). Verify
   before moving on:

   ```bash
   dig +short mastermindx.ai www.mastermindx.ai blog.mastermind-x.com
   # expect 146.190.142.17 three times
   ```

2. **The cutover PR — one commit, both halves.** `config/press.yml` `cutover:`
   flips to `true` **and** the marked Caddyfile block gets uncommented, in the
   same commit. `tests/test_press_properties.py` asserts the pairing in both
   directions, so a PR carrying only one half goes red.

   Uncomment mechanically rather than by hand (this strips one leading `#` from
   every line *between* the markers and leaves the marker lines themselves
   commented, which is what the guard expects):

   ```bash
   python3 - <<'PY'
   import pathlib
   p = pathlib.Path("app/deploy/Caddyfile")
   lines = p.read_text(encoding="utf-8").splitlines()
   b = lines.index("# PRESS-CUTOVER-BEGIN")
   e = lines.index("# PRESS-CUTOVER-END")
   lines[b+1:e] = [l[1:] if l.startswith("#") else l for l in lines[b+1:e]]
   p.write_text("\n".join(lines) + "\n", encoding="utf-8")
   PY
   caddy validate --config app/deploy/Caddyfile --adapter caddyfile
   ```

3. **Merge.** The box's `macro-update` cron pulls within 3 minutes.
   `update.sh` gates the Caddy reload on `caddy validate`, so a bad config can
   never take the site down — it refuses the install and logs why. ACME issues
   the two certificates within seconds of the reload, because DNS already points
   here (step 1).

4. **Verify live.**

   ```bash
   curl -sI https://mastermindx.ai/ | head -5              # expect 200
   curl -sI https://blog.mastermind-x.com/ | head -5       # expect 200
   curl -sI http://mastermindx.ai/ | head -3               # expect 301 -> https
   curl -sI https://www.mastermindx.ai/ | head -3          # expect 301 -> apex
   curl -s  https://mastermindx.ai/robots.txt              # expect the Sitemap line
   ```

5. **HSTS ramp — a week later, not on cutover day.** Both vhosts ship
   `Strict-Transport-Security "max-age=300"`. That is deliberate: HSTS is the
   one header a browser will not let you withdraw — a client that has cached a
   long `max-age` refuses plain http for that host until it expires, so a cert
   or DNS mistake on a brand-new domain becomes unreachable-by-design. Five
   minutes is real protection and a survivable mistake.

   After the properties have served a clean week (valid certs, no mixed
   content, no redirect loops), raise **both** blocks — and the `www` redirect
   block — to `max-age=31536000` in a follow-up PR. This step is not paired to
   anything; it is a one-line change with no config counterpart.

**Rollback:** revert the cutover PR. That re-comments the Caddy block and puts
`cutover: false` back in one move — which is exactly why the two halves are
pinned together. The DNS records can stay pointed at the box; with the block
commented, those hosts fall through to the port-80 catch-all and serve nothing.

**What flipping `cutover` changes on the publishing side:** `scripts/run_press.py
--emit` stops writing new pieces to `content/seo/blog` + the `/blog/` estate for
any publication that carries a `property_tree`, and writes them to that
publication's `content_dir` + property tree instead. Historic ledger rows are
never migrated — each row carries the URL it was actually published at.

## Files

| File | Role |
|---|---|
| `setup.sh` | idempotent provisioning (run as root on the droplet) |
| `Caddyfile` | serves `/opt/macro/site.served` plus the external live plane; carries the commented press-cutover vhosts |
| `update.sh` | `git pull` + Caddy reload (installed as `/usr/local/bin/macro-update`, cron'd); publishes `site.served` and the two `press_*.served` trees |
| `codex-runtime-setup.sh` | pins the official Codex CLI and prepares its root-only VPS state directory |
| `live-setup.sh` | installs the fast, full-snapshot, and intraday-bar systemd lanes |
| `live-rollback.sh` | disables the live lanes, restores legacy cron, and preserves artifacts in a backup |

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
