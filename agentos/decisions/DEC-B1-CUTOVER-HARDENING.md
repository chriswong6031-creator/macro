---
key: B1-CUTOVER-HARDENING
question: >
  Sol's Day-6 AMENDMENT raised seven binding clarifications on the private-macro
  cutover. What exactly do they change about what may be CLAIMED pre-flip, what
  must become executable rather than prose, and where the Prophet product
  completion boundary sits?
answer: >
  Seven rulings, all binding, none of which reopen DEC:B1-MACRO-PRIVATE-CUTOVER:
  (A) A pre-flip Wave A claim is "VPS PRIVATE-CREDENTIAL WIRING PASS", NOT proof
  that private contents have been read — the decisive read is the first
  post-flip authenticated fetch, inside the rollback window. Wiring must prove
  the INTENDED credential is actually selected (not anonymous HTTPS, not an
  ssh-agent fallback, not a human key). The clean-bootstrap path must also be
  private-safe: no `curl raw.githubusercontent.com/.../macro/... | bash` may
  remain, and a fresh box must bootstrap on the machine identity.
  (B) GitHub Pages needs an explicit TERMINAL disposition — "runtime dependency
  zero" is necessary but not sufficient. Pages is RETIRED/unpublished at cutover;
  repo-private is NOT assumed to imply Pages-private.
  (C) A public fork / detached-copy census runs IMMEDIATELY before the flip and
  again in §8b. An exact company-controlled public twin defeats a boundary pass.
  (D) Wave B must be a real machine-credential SEAM with lifecycle, not a token
  dropped into .git/config: least-privilege read, never in the remote URL, never
  logged, fresh clone works, sparse fetch works, failure loud, staleness intact,
  and an auth failure can never read as "fresh Macro data".
  (E) The dependency census becomes a permanent REGRESSION FENCE across all
  repos, precise (never a blanket ban on GitHub/raw/jsDelivr, which lawful third
  parties use) and covering assembled/multiline constructions.
  (F) The `/api/hub/prophet` edge/internal topology assumption becomes an
  executable guard, including that a future generic `reverse_proxy :8000` block
  cannot silently bypass it.
  (G) Neither P-LAB-UI completion nor B1 closure authorizes calling the US
  Prophet redesign complete while P-MP1-DENSE is open. After B1 CLOSED + §8b
  BOUNDARY PASS + P-LAB-UI production-proven, STOP and return to Sol with
  "P-MP1-DENSE OWED — current Setups Grid/Table parity defect remains".
rationale: >
  Each clause closes a way the cutover could have been declared safe while an
  unproven assumption carried it. (A) exists because a credential that
  authenticates today against a PUBLIC repo proves nothing about tomorrow's
  private one, and because ssh silently falls back to other identities unless
  IdentitiesOnly=yes pins the one we provisioned. (D) exists because a clone made
  with --filter=blob:none is a PARTIAL clone, so `sparse-checkout set` and
  `reset --hard` are remote-facing; a seam that credentials only clone+fetch
  looks correct and fails on first private use. (E) exists because the prior
  single-file grep (templates/live.js) missed four other constructions, two of
  them assembled from a module constant plus a runtime path. (F) exists because
  the hub guard's safety was a true fact about Caddy held only in a comment.
alternatives:
  - option: Claim Wave A proves private access because the deploy key authenticates today
    why_not: >
      The repo is still public, so a successful read proves the credential works
      against a PUBLIC repo. Sol: "Do not call it proof that the future-private
      Macro repository has already been read." The decisive test is post-flip.
  - option: Assume repo PRIVATE implies Pages PRIVATE and skip the explicit disable
    why_not: >
      Sol forbids the assumption. Pages is a separate publication surface with its
      own visibility; leaving it ambiguous risks premium generated material still
      being served independently of repository visibility.
  - option: Ban every raw.githubusercontent / jsDelivr / github.com URL in the fence
    why_not: >
      Lawful third-party assets use those hosts (google/fonts, fja05680/sp500,
      nvstly/icons, the Supabase SDK). A blanket ban would either be disabled or
      routed around. The fence is keyed on the canonical Macro owners + repo, so
      third parties pass by construction.
  - option: Fold the Setups Grid/Table parity defect into P-LAB-UI
    why_not: >
      Sol keeps P-MP1-DENSE separate and explicitly forbids smuggling it into
      P-LAB-UI, while ALSO forbidding calling the redesign complete with it open.
      The completion boundary is a report obligation, not a scope expansion.
evidence:
  - "Wave A credential selection: `ssh -v` on the VPS shows exactly one identity offered — 'Offering public key: /root/.ssh/macro_ro_selfupdate ED25519 SHA256:zfKoqwyhk0S3vWGsb+IjaZxGfQAe9dpsIkh6NYAcrNU explicit' then 'Authenticated to github.com'; core.sshCommand carries IdentitiesOnly=yes; no url.*.insteadOf and no credential helper, so anonymous HTTPS cannot be silently substituted; `git push --dry-run` denied"
  - "Wave A loud failure: with a bogus key path, `git fetch --depth 1 origin main` exits 128 and a traced end-to-end `/usr/local/bin/macro-update` run exits 128 with HEAD unchanged and site.served mtime unchanged — no silent stale-serve. (A first attempt returned rc=0 having never reached the fetch: the run had short-circuited on `flock -n 9` under a live cron tick; the traced retry is the valid measurement.)"
  - "Wave D defect proven live (clause D): `git sparse-checkout set` in the blobless clone WITHOUT the credential prints 'fatal: could not fetch <sha> from promisor remote' and leaves site/ absent while EXITING 0; with the credential the projection materializes (site/prophet/index.json 2,242,608B, data/regime/latest.json 857,277B). Three call sites in data_layer/macro_refresh.py lacked env=_remote_env()."
  - "Wave B acceptance on the authenticated DR tree: asof()=2026-08-20, anchors_report() returns us_standouts/regime_latest/sector_cycles dates, is_stale()=False; with a broken credential refresh() returns None and asof() is unchanged — an auth failure can never present as a fresh pull."
  - "Clause C pre-cutover census 2026-08-21: forks_count=0, network_count=0, forks list empty; `chriswong6031-creator/macro` resolves by rename-redirect to the same repo (not a detached copy); org repos Mastermind and mastermind-terminal carry no committed Macro mirror (Mastermind's vendor/macro is a symlink)."
  - "Clause B Pages disposition: pages API shows cname=null (no custom domain, so no DNS consequence), source branch main path /, build_type=workflow, public=true; disable mechanism `gh api -X DELETE repos/mastermindx-market-intelligence/macro/pages`; repo `homepage` still advertises the Pages URL and is cleared at cutover."
affects:
  - "app/deploy/setup.sh"
  - "app/deploy/bootstrap_repo.sh"
  - "scripts/build_prophet_option_shadow_lifecycle.py"
  - "scripts/check_macro_anon_dependency.py"
  - "scripts/check_caddy_hub_boundary.py"
  - "data_layer/macro_refresh.py (mastermind)"
  - "terminal/lib/flowSource.ts (mastermind-terminal)"
confidence: high
reversibility: costly
decided_by: sol
decided_at: 2026-08-21
related:
  - "DEC:B1-MACRO-PRIVATE-CUTOVER"
  - "DEC:B1-PROPHET-PUBLIC-SPLIT"
  - "DSC:PROPHET-BOOK-PUBLIC-GIT-TWIN"
  - "WS:PROPHET-US-V4-RECOVERY"
---

Amendment to the Day-6 directive, recorded by the session executing it. It does
not replace DEC:B1-MACRO-PRIVATE-CUTOVER; it constrains what that cutover may
claim before the flip, converts two prose assumptions (the anonymous-dependency
census, the Caddy hub topology) into executable guards, and fixes the Prophet
product completion boundary so P-MP1-DENSE cannot be silently inherited.

The readiness matrix this amendment expands to nineteen rows, and the post-flip
proof list it extends, live in the day-6 handoff under `agentos/handoffs/`.
