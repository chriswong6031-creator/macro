---
key: MACRO-SERVED-ORIGIN-IS-MASTERMIND-X-COM
claim: >
  The production Caddy on the Macro VPS loads only the hosts mastermind-x.com and
  www.mastermind-x.com (served through TencentEdgeOne), so a Cloudflare 525 on any
  mastermindx.ai hostname is a separate, unqualified edge→origin mapping and is not
  evidence that the site is down.
falsifier: >
  `curl -sI https://www.mastermind-x.com/ | head -1` returning anything but an HTTP
  200 while `curl -sI https://mastermindx.ai/` returns 525; or the installed
  /etc/caddy/Caddyfile on the host listing a mastermindx.ai site block.
so_what: >
  Probe the .com hostnames before relaying an outage; a 525 on .ai never
  re-scopes a host-diagnosis child as critical path (F00 did exactly that at
  1788633512.480849 and had to correct itself at 1788637058.742439). Live
  readbacks of merged pages are taken on www.mastermind-x.com by body hash; the
  .ai mapping is its own unowned item, not part of any publication-lag repair.
kind: runtime
verified_at: 2026-09-05
verified_by: >
  HOST_DIAGNOSIS_RESULT 1788635437 on Slack root C0BSBM78V1N/1788600409.396209
  (read-only host child, accepted and closed by Sol 1788636103.500379): loaded Caddy
  hosts, installed /etc/caddy/Caddyfile byte-equal to the checkout copy; F00 curl
  2026-09-05 ~19:30Z: www.mastermind-x.com 200 (TencentEdgeOne), /help.html 404,
  mastermindx.ai 525 (cloudflare).
scope:
  - mastermindx-market-intelligence/macro
  - app/deploy/Caddyfile
  - WS:MARKET-OS
confidence: verified
---

# What the host actually serves

The read-only host diagnosis (Slack root 1788600409.396209) reported the Caddy
process's loaded hosts as `mastermind-x.com` and `www.mastermind-x.com` only, with
the installed `/etc/caddy/Caddyfile` byte-equal to the repository copy at the
checkout's HEAD. The same result located the real publication blocker elsewhere:
`/opt/macro` at `available_bytes=0`, updater runs failing on no space, the checkout
at `761a4df8` (108 commits behind main at the time), Help absent from both
`/opt/macro/site` and the served root, and no `macro-update.service`/`.timer`
unit loaded (`LoadState=not-found`) — so the "3-minute VPS pull" is not evidenced
on this host until the storage lane reports the scheduler it finds.

# Why the trap fires

Two independent observers (the F01 worker at 1788630186.076589 and F00 at
~18:34Z) probed `mastermindx.ai` hostnames, saw 525 on every path including the
immutable assets, and concluded the origin TLS handshake was failing site-wide.
The .com hostnames were up the whole time. A 525 is the edge failing to reach an
origin for THAT hostname; it says nothing about a hostname the origin does serve.
