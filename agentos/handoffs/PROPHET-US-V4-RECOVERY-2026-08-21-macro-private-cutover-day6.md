---
workstream: WS:PROPHET-US-V4-RECOVERY
session: macro-private-cutover-day6
model: fable
ended_because: blocked

mission: >
  Sol Day-6: prepare mastermindx-market-intelligence/macro to go PRIVATE (Waves
  A–F) so the §8b boundary can convert to PASS, WITHOUT flipping visibility
  (Chairman's isolated act). Return MACRO-PRIVATE-CUTOVER READY.

state_before: >
  Day-5 closed the R2 plane (DEC:B1-PROPHET-PUBLIC-SPLIT) but §8b WITHHELD:
  raw-git + Pages + jsDelivr + anonymous clone still serve the full plan book +
  premiumdata (DSC:PROPHET-BOOK-PUBLIC-GIT-TWIN). Repo is public.
changed:
  - {path: "VPS /opt/macro git remote", what: "switched from anonymous HTTPS to authenticated SSH via a dedicated READ-ONLY deploy key (gh key id 160889926, title vps-macro-ro-selfupdate-b1); core.sshCommand + remote.origin.url in /opt/macro/.git/config (persists across git reset --hard). Wave A."}
  - {path: "macro repo deploy keys", what: "registered TWO read-only deploy keys (160889926 VPS self-update, 160889927 Mastermind DR vendor) via the operator's own gh token; read_only=true; reversible. No PAT copied, no secret value handled."}
  - {path: "agentos/decisions/DEC-B1-MACRO-PRIVATE-CUTOVER.md", what: "Sol's private-cutover architecture ruling recorded (private canonical plane + explicit public-allowlist delivery plane; no history rewrite; flip gated on the READY receipt)."}
  - {path: "scripts/build_live_overlay.py + tests + workflows (PR #<CD>)", what: "Wave C guard: resolve_snapshot_url rejects GitHub-distribution hosts (raw.githubusercontent/*.github.io/jsdelivr). Wave D: Pages producer steps removed from daily/weekly/closing-bell/pages.yml + retirement guard test. (builder PR in flight at handoff-write.)"}
  - {path: "data_layer/macro_refresh.py (mastermind PR #<B>)", what: "Wave B DR seam: MACRO_GIT_REMOTE + MACRO_GIT_SSH_COMMAND env-configurable authenticated remote, public-HTTPS default, zero behavior change unset. (builder PR in flight.)"}
verified:
  - {claim: "Wave A: authenticated fetch works, read-only enforced, full deploy cycle clean, auth persists", command: "on VPS: full /usr/local/bin/macro-update rc=0 via SSH deploy key; `git push --dry-run` denied; git -C /opt/macro config remote.origin.url = git@github.com:… + core.sshCommand set"}
  - {claim: "Wave B production: VPS Mastermind reads macro via vendor/macro -> /opt/macro symlink (vendor/macro_src never materialized), so Wave A covers it; consumer read fresh", command: "readlink -f /opt/mastermind/vendor/macro/site/prophet/index.json → /opt/macro/…; python read source_asof=2026-08-20"}
  - {claim: "Wave C production already same-origin; Wave D consumers already zero", command: "curl live_config.js LIVE_SNAPSHOT_URL='live/quotes.json'; config.yml:671; old-owner Pages flow 404; Terminal flowSource no github.io ref"}
  - {claim: "All GitHub Actions workflows survive private (checkout uses the job GITHUB_TOKEN; none fetches macro anonymously at run time)", command: "grep .github/workflows: actions/checkout + token: secrets.GITHUB_TOKEN/ADMIN_GH_TOKEN; zero anonymous macro URLs / raw.githubusercontent-macro at run time"}
  - {claim: "Baseline exposure to be closed: jsDelivr/Pages/raw-git each 200/2,242,608B on site/prophet/index.json (2026-08-21)", command: "anonymous curl of the three hosts"}
unresolved:
  - "Chairman: the visibility flip PUBLIC→PRIVATE (the ONLY irreversible act; gated on MACRO-PRIVATE-CUTOVER READY, inside an operator window)."
  - "Cutover steps (post-READY, coordinated): (a) merge the two PRs; (b) `gh api -X DELETE repos/mastermindx-market-intelligence/macro/pages` after the Wave D PR merges; (c) jsDelivr purge POST https://purge.jsdelivr.net/gh/mastermindx-market-intelligence/macro@main/site/{prophet/index.json,prophet/plans/*,prophet/states/*,premiumdata/*}; (d) post-flip proof matrix + one more update cycle; (e) §8b re-review → BOUNDARY PASS."
  - "Wave A loud-fail hardening (RECOMMENDED, non-blocking): on-box freshness_sentinel detects staleness every 30 min but has no paging creds on the VPS (/etc/macro-sentinel.env absent). set -euo pipefail already prevents serving stale-as-fresh. Operator drops TELEGRAM/DISCORD creds to make the on-box dead-man page."
  - "M1 flow-ops-wt (OPERATOR): pinned a5f79c83 (#2760-era, no auto-pull), old marks code reads the deleted R2 → marks stale since Day-5 (the prophet_marks escalation, scoped OUT of B1). Advancing a deliberate months-old pin + provisioning M1 macro auth is an operator action; NOT a flip-blocker."
  - "Bootstrap caveat: app/deploy/setup.sh clones macro anonymously on a FRESH box build — a rebuilt VPS post-flip needs the deploy key in setup.sh (DR, like the Mastermind seam). Not a runtime dependency."
unverified:
  - "Every POST-FLIP proof (anonymous clone denied; raw/Pages/jsDelivr prophet paths inaccessible; R2 index stays 404; origin/hub denied; Terminal entitled read full book; /opt/macro keeps pulling; Mastermind authed refresh fresh; quotes healthy) — unverifiable until the Chairman flips visibility; the turnkey proof script is scratchpad/cutover_execute.sh."
  - "The natural nightly B1 producer receipt (health PUT + tombstone notice; index stays 404) — pending the next scheduled daily.yml run; do NOT dispatch an artificial nightly."
  - "The Mastermind DR authenticated clone (#102 merged) exercised end-to-end on a real non-symlink host — the VPS uses the symlink, so the clone path is proven only by unit test + the deploy-key canary, not a live DR clone."
next_actions:
  - "Merge PR #<CD> (macro Wave C+D) and PR #<B> (mastermind Wave B) on concluded-green; then finalize + return MACRO-PRIVATE-CUTOVER READY with the isolated Chairman action named."
  - "On the natural nightly: bank the B1 producer receipt (health PUT + tombstone notice; index stays 404) — do NOT dispatch an artificial nightly."
  - "After the Chairman flip: run the post-flip proof matrix + §8b re-review; then commission P-LAB-UI (both gates met)."
do_not_redo:
  - "Do not flip repo visibility — Chairman-only, gated on the READY receipt."
  - "Do not rewrite macro git history (Sol forbids in B1 — provenance across SHAs/receipts; record historical exposure as a disclosure fact)."
  - "Do not jump the M1 flow-ops-wt pin across thousands of commits unilaterally — operator action."
  - "Do not delete the deploy keys — they are Wave A/B load-bearing."
danger_areas:
  - "The /opt/macro auth switch is reversible (remote back to HTTPS) ONLY while the repo is public; after the flip, HTTPS-anon fails and the deploy key is the only path — verify the key before the flip window closes."
  - "Pages-site disable must come AFTER the Wave D producer-removal PR merges, else the next nightly's deploy-pages step reds trying to deploy to a disabled site."
  - "jsDelivr caches persist after the flip until purged — the purge is a required cutover step, not automatic."
---

# Handoff — Macro private-cutover prep (day 6) · 2026-08-21

Sol ruled the canonical macro repo goes PRIVATE. This session migrated every
load-bearing anonymous dependency to an authenticated replacement and PROVED the
ones that were live: the VPS self-update now pulls through a read-only deploy key
(Wave A), and the VPS Mastermind rides that same pull through a symlink (Wave B
production). The browser quote path was already same-origin (Wave C) and the
Pages consumers were already dead (Wave D); the code PR adds the guards and
retires the Pages producers. jsDelivr has no code dependency (purge-only). The
GitHub Actions estate survives the flip on its own job token. What remains is the
Chairman's isolated visibility flip plus the coordinated cutover steps
(Pages-disable, jsDelivr purge, post-flip proof, §8b re-review) — no visibility
change was taken here, no PAT copied, no secret value handled.
