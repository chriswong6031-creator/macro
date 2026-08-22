---
workstream: WS:PROPHET-US-V4-RECOVERY
session: cutover-hardening-day6-amendment
model: fable
ended_because: blocked

mission: >
  Execute Sol's Day-6 AMENDMENT (clauses A-G) on top of the private-macro cutover:
  distinguish credential-wiring from private-access proof, make the clean-bootstrap
  path private-safe, give GitHub Pages an explicit terminal disposition, add a
  pre-flip fork/network gate, turn Wave B into a real credential lifecycle, convert
  the anonymous-dependency census into a permanent regression fence, make the
  /api/hub/prophet topology assumption executable, and fix the Prophet product
  completion boundary. Return the nineteen-row MACRO-PRIVATE-CUTOVER READY.

state_before: >
  Day-6 returned MACRO-PRIVATE-CUTOVER READY on a nine-row matrix. Sol accepted the
  direction and amended it with seven binding clarifications, several of which
  identified claims that were stronger than their evidence (Wave A "private access
  proven"), assumptions held only in prose (the Caddy hub topology), and a census
  that had ended as a one-time grep.
changed:
  - {path: "app/deploy/bootstrap_repo.sh", what: "NEW — governed authenticated acquisition of the Macro repo. SSH remote + read-only deploy key, IdentitiesOnly=yes, GIT_TERMINAL_PROMPT=0, fail-closed when the key is absent (explicitly refuses to fall back to anonymous HTTPS), persists core.sshCommand into the checkout so it survives update.sh's `git reset --hard`."}
  - {path: "app/deploy/setup.sh + app/deploy/README.md", what: "the `curl -fsSL raw.githubusercontent.com/.../setup.sh | bash` bootstrap is GONE; APP_DIR is MACRO_APP_DIR-overridable; the [3/6] clone block delegates to bootstrap_repo.sh."}
  - {path: "scripts/build_prophet_option_shadow_lifecycle.py", what: "the anonymous `git ls-remote` + `curl raw.githubusercontent.com/...` canonical-ledger legs are GONE; commit resolution and the ledger read now go through the local checkout's already-authenticated origin, mirroring build_prophet_marks.py::_load_index_canonical_git()."}
  - {path: "scripts/check_macro_anon_dependency.py + tests + config/macro_anon_dependency_allowlist.json", what: "NEW permanent regression fence (clause E): bans the five anonymous canonical-Macro distribution shapes keyed on the two Macro owners, catches assembled/multiline constructions, and by construction does not touch lawful third-party GitHub/raw/jsDelivr URLs."}
  - {path: "scripts/check_caddy_hub_boundary.py + tests", what: "NEW topology guard (clause F): every :8000 reverse_proxy in the production Caddyfile must either stamp X-MM-Peer or rewrite to a fixed non-hub path; a future generic `reverse_proxy 127.0.0.1:8000` block fails the check."}
  - {path: ".github/ci/legacy-jobs.yml", what: "the three new suites ride the existing rescue-lane step (the manifest's narrow-diff ceiling reds a 181st job)."}
  - {path: "research/migration_packets/MP-1-prophet-board.md", what: "P-MP1-DENSE completion boundary recorded (clause G) with its frozen observable mission."}
  - {path: "agentos/decisions/DEC-B1-CUTOVER-HARDENING.md", what: "the amendment recorded as a decision with its evidence."}
  - {path: "data_layer/macro_refresh.py (mastermind)", what: "three remote-facing git call sites were missing env=_remote_env(); in a --filter=blob:none partial clone `sparse-checkout set` and `reset --hard` fetch from the promisor remote, so the seam failed on first private use. Also makes the quiet promisor failure loud."}
  - {path: "terminal/lib/flowSource.ts (mastermind-terminal)", what: "the flow_idx GitHub Pages last-resort fallback retired; backend -> R2 only, fails closed."}
verified:
  - {claim: "Wave A credential SELECTION is deterministic — the provisioned key is what authenticates, not an agent identity, another ~/.ssh key, or anonymous HTTPS", command: "on the VPS: `GIT_SSH_COMMAND='ssh -v -i /root/.ssh/macro_ro_selfupdate -o IdentitiesOnly=yes' git -C /opt/macro ls-remote origin main` -> single 'Offering public key: … explicit' then 'Authenticated to github.com'; `git config --get-regexp url..*insteadOf` and `credential` both empty; SSH_AUTH_SOCK unset; /root/.ssh/config has no `Host github.com`"}
  - {claim: "Wave A failure is LOUD and cannot silently stale-serve", command: "with a bogus key path: `git fetch --depth 1 origin main` rc=128; traced `bash -x /usr/local/bin/macro-update` rc=128 at line `git -C /opt/macro fetch --depth 1 -q origin main`; HEAD unchanged, site.served mtime unchanged"}
  - {claim: "clean bootstrap is private-safe and works on the machine identity", command: "on the VPS in /tmp: missing key -> rc=1 with an explicit refusal and no target created; governed clone with the deploy key rc=0; the SHIPPED bootstrap_repo.sh end-to-end rc=0 (fetch main, reset to 6dd24ff, site/index.html verified); core.sshCommand persisted"}
  - {claim: "Wave B: the credential seam had a real defect — sparse-checkout set/reset --hard are remote-facing in a blobless clone", command: "on the VPS: `env -u GIT_SSH_COMMAND git -C <clone> sparse-checkout set site …` -> 'fatal: could not fetch <sha> from promisor remote', site/ absent, EXIT 0; with GIT_SSH_COMMAND set -> site/prophet/index.json 2,242,608B, data/regime/latest.json 857,277B"}
  - {claim: "Wave B acceptance: authenticated sync, projection, a real consumer, and a failure path that cannot read as fresh", command: "on the authenticated DR tree: asof()=2026-08-20, anchors_report() us_standouts/regime_latest/sector_cycles, is_stale()=False; with a broken credential refresh()->None and asof() unchanged"}
  - {claim: "clause C: no public fork, no detached company-controlled twin", command: "gh api repos/…/macro -> forks_count=0 network_count=0; /forks empty; chriswong6031-creator/macro resolves by rename-redirect to the same repo; org siblings Mastermind + mastermind-terminal carry no committed Macro mirror (vendor/macro is a symlink)"}
  - {claim: "clause B: Pages disposition is unambiguous and has no DNS consequence", command: "gh api repos/…/macro/pages -> cname=null, source main:/, build_type=workflow, public=true; disable = `gh api -X DELETE …/pages`; repo homepage still advertises the mirror and is cleared at cutover"}
unresolved:
  - "Chairman: the visibility flip PUBLIC->PRIVATE — the only irreversible act, gated on this receipt, inside an operator window."
  - "Cutover sequence (scratchpad/cutover_execute.sh): precheck (re-census forks) -> flip -> pages-disable (+ homepage clear) -> jsdelivr-purge -> proof -> vps-proof -> §8b re-review."
  - "M1 flow-ops-wt: does not exist on this host (it lives on the operator's other Mac), so it cannot be advanced or verified from here. It is a pinned developer checkout, not production, and does not gate the flip."
  - "On-box freshness sentinel has no paging creds (/etc/macro-sentinel.env absent) — operator hardening, non-blocking; `set -euo pipefail` already prevents serving stale-as-fresh."
  - "Pre-existing audit item: deploy key id 154241382 'key1' is read_only=FALSE — a WRITE-capable key on the macro repo predating this program. Authenticated, so not an anonymous-exposure blocker; the Chairman should confirm it is still wanted."
unverified:
  - "Every POST-FLIP proof (a NEW /opt/macro authenticated fetch; a NEW Mastermind refresh rather than a stale vendor read; a real consumer seeing the refreshed generation; anonymous clone denied incl. the pre-rename alias; raw current AND historical-commit blobs denied; Pages unavailable; jsDelivr purged; forks re-censused; the hub attack path re-tested; one more ordinary update/deploy) — unverifiable until the Chairman flips visibility."
  - "The natural nightly B1 producer receipt (health PUT + tombstone notice; public index stays 404) — pending the next scheduled daily.yml run; do NOT dispatch an artificial nightly."
  - "A full 26 GiB clean clone was NOT materialized on the VPS: /opt/macro is 26 G against 17 G free, so it would have risked ENOSPC on production. The clone leg was exercised blobless/no-checkout — same remote, same credential, only blob materialization differs."
next_actions:
  - "Deliver MACRO-PRIVATE-CUTOVER READY on the nineteen-row matrix and STOP. Do not perform the visibility mutation."
  - "After the Chairman flip: run cutover_execute.sh precheck (pre-flip), then pages-disable, jsdelivr-purge, proof, vps-proof; then the §8b re-review requiring the exact verdict 'BOUNDARY PASS — no unauthenticated production path to withheld Prophet plan rows is constructible.'"
  - "Only after BOTH that verdict and the natural nightly producer receipt: commission P-LAB-UI. Then STOP and return to Sol with 'P-MP1-DENSE OWED — current Setups Grid/Table parity defect remains'."
do_not_redo:
  - "Do not flip repo visibility — Chairman-only."
  - "Do not claim Wave A proves private-repo access pre-flip; the decisive read is the post-flip fetch."
  - "Do not rewrite macro git history in B1."
  - "Do not run a full clean clone on the VPS — 17 G free against a 26 G checkout."
  - "Do not weaken the §8b verdict wording to make the certification pass."
  - "Do not smuggle P-MP1-DENSE into P-LAB-UI, and do not start it without Sol review."
danger_areas:
  - "The /opt/macro auth switch is reversible to anonymous HTTPS ONLY while the repo is public; after the flip the deploy key is the only path."
  - "Pages-site disable must come AFTER the producer-removal PRs merged (#6174) — otherwise a nightly deploy-pages step reds against a disabled site."
  - "jsDelivr caches persist after the flip until purged — the purge is a required cutover step, not automatic."
  - "A blobless partial clone makes locally-shaped git commands (sparse-checkout set, reset --hard) remote-facing. Any future credential seam must cover them, not just clone+fetch."
---

# Handoff — Day-6 amendment: cutover hardening · 2026-08-21

Sol's amendment did not change the destination; it changed what may be claimed on
the way there. Three of its clauses turned out to be load-bearing rather than
procedural. Clause A's insistence that the intended credential be *selected*, not
merely present, is what made `IdentitiesOnly=yes` and the absent
`insteadOf`/credential-helper into evidence rather than assumptions. Clause A's
loud-failure requirement produced a first measurement that looked like a defect
(`macro-update` exited 0 with a broken credential) and turned out to be the cron
lock — the traced retry gave the real answer, rc=128. And clause D's demand for a
real lifecycle rather than an installed token exposed an actual defect in the Wave
B seam: a `--filter=blob:none` clone makes `sparse-checkout set` and `reset --hard`
remote-facing, they were not carrying the credential, and they fail *quietly* —
exit 0 with `could not fetch … from promisor remote` on stderr and no `site/`.

What remains is the Chairman's single act. Everything repository-side is merged;
the post-flip proof is scripted; the §8b re-review is the gate after it.
