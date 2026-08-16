# Options sparse selector — bounded paper-only canary

## Activation contract

This revision permits one narrowly bounded, private research canary on the exact
`Mac13,1` / `arm64` M1 host. Code eligibility is not proof that the service is
installed, loaded, advancing, or healthy. Only the install and live-proof
receipts below establish those facts.

The canary is paper-only and proposal-disabled. Its W1A input is deliberately
forbidden rather than silently absent, so it cannot create a proposal. It may
authenticate the committed prospective source prefix and local mark/lifecycle
evidence, persist selector candidates, and settle the first manifest as honest
abstentions.
It has no handoff consumer and no signal, score, rank, issue, sizing, trading,
public-output, publication, training, Prophet, Neural Web, or completion
authority. The preregistration receipt and its frozen retrospective boundary
remain unchanged.

All of these bounds are fail-closed and conjunctive:

- expiry for new transition authority is exactly `2026-08-21T20:00:00Z`;
- at most 128 selector generations may be attempted across this activation;
- one 300-second launchd fire may grant at most one new generation, and fires
  outside regular NYSE trading hours grant no new selector work;
- a WAL transition sealed inside RTH before expiry may be adopted exactly after
  a crash even when the retry is outside RTH or after expiry; it retains the
  original slot and logical clocks, cannot replan, and grants no second
  generation;
- the first decision-bearing generation may atomically settle one authenticated
  manifest of 1–128 one-to-one abstention decisions; once the durable selector
  head reports any settled decision, every later invocation exits without
  advancing;
- `w1a_receipt_root` is always null/forbidden and proposal capability remains
  false; and
- rollback unloads the service but never deletes, truncates, rewrites, or
  reinitializes the durable selector root.

The first-decision-bearing-generation stop dominates the 128-generation
ceiling. Raising either bound, extending the expiry, enabling W1A, admitting
proposals, or attaching a consumer requires a separately reviewed activation
change.

## Fixed M1 layout

No path is configurable by environment or launchd arguments in this canary:

- reviewed checkout: `/Users/chriswong/options-sparse-selector-ops-wt`;
- sealed runtime: `/Users/chriswong/.mastermind_private/options_sparse_selector_runtime_v2`;
- durable selector store: `/Users/chriswong/.mastermind_private/options_sparse_selector_v1`;
- operational receipts: `/Users/chriswong/.mastermind_private/options_sparse_selector_ops_v2`;
- mark evidence: `/Users/chriswong/.mastermind_private/prophet_option_mark_observations_v1`;
- lifecycle evidence: `/Users/chriswong/.mastermind_private/prophet_option_shadow_lifecycle_v1`; and
- launchd label: `com.mastermind.optionssparseselector`.

For a fresh source epoch, the runner reads the canonical episode ledger,
campaign-revision ledger, and campaign checkpoint as exact Git blobs from the
currently fetched `origin/main`. While that epoch remains active, every later
transition re-reads the same authenticated ancestor commit rather than mixing
in a newer ref. It does not execute the nightly producers or mutate their
checkout paths. Source commit, blob object IDs, byte hashes, record counts, and
checkpoint bindings enter the selector's authenticated source snapshot.

## Install on the fixed host

Installation is a supervised operation, never a daily-workflow step. Start from
a clean standalone checkout whose `origin/main` contains the reviewed activation
merge. Do not install from the dirty `flow-ops-wt` checkout and do not trigger,
rerun, or backfill the daily workflow.

For the v1-to-v2 replacement, first stop the existing label before changing the
checkout or installed plist. Retain the v1 runtime and operational roots exactly
as incident evidence; never reuse, copy into, or delete them. The durable
`options_sparse_selector_v1` selector root is the final production root and is
also never removed.

```sh
set -eu
if /bin/launchctl print gui/501/com.mastermind.optionssparseselector >/dev/null 2>&1; then
  /bin/launchctl bootout gui/501/com.mastermind.optionssparseselector
fi
/bin/chmod 700 /Users/chriswong/.mastermind_private
/usr/bin/stat -f '%Su %Lp' /Users/chriswong/.mastermind_private
/usr/bin/test -d /Users/chriswong/options-sparse-selector-ops-wt/.git
/bin/chmod 755 /Users/chriswong/options-sparse-selector-ops-wt
cd /Users/chriswong/options-sparse-selector-ops-wt
/usr/bin/test -z "$(/usr/bin/git status --porcelain)"
/usr/bin/git fetch --prune origin
/usr/bin/git sparse-checkout set \
  engine lib scripts ops/launchd contracts/options research/options_estate
/usr/bin/git checkout --detach origin/main
/usr/bin/git status --porcelain
release_sha="$(/usr/bin/git rev-parse --verify 'refs/remotes/origin/main^{commit}')"

/bin/mkdir /Users/chriswong/.mastermind_private/options_sparse_selector_runtime_v2
/bin/chmod 700 /Users/chriswong/.mastermind_private/options_sparse_selector_runtime_v2
/usr/bin/printf 'options.sparse_selector.persistent_runtime_root/v2\n' > \
  /Users/chriswong/.mastermind_private/options_sparse_selector_runtime_v2/.options_sparse_selector_persistent_runtime_root
/bin/chmod 600 \
  /Users/chriswong/.mastermind_private/options_sparse_selector_runtime_v2/.options_sparse_selector_persistent_runtime_root

/bin/mkdir /Users/chriswong/.mastermind_private/options_sparse_selector_ops_v2
/bin/chmod 700 /Users/chriswong/.mastermind_private/options_sparse_selector_ops_v2

install_receipt="/Users/chriswong/.mastermind_private/options_sparse_selector_ops_v2/runtime_install_receipt.json"
install_receipt_tmp="${install_receipt}.tmp"
/usr/bin/python3 ops/launchd/run_options_sparse_selector_verified.py \
  --install-persistent-target \
  --source-root /Users/chriswong/miniconda3/envs/plane \
  --repo-root /Users/chriswong/options-sparse-selector-ops-wt \
  --expected-release-sha "$release_sha" > \
  "$install_receipt_tmp"
/bin/chmod 600 "$install_receipt_tmp"
/bin/mv "$install_receipt_tmp" "$install_receipt"
manifest_receipt="/Users/chriswong/.mastermind_private/options_sparse_selector_ops_v2/runtime_closure.sha256"
manifest_receipt_tmp="${manifest_receipt}.tmp"
/usr/bin/shasum -a 256 \
  /Users/chriswong/.mastermind_private/options_sparse_selector_runtime_v2/runtime_closure.json > \
  "$manifest_receipt_tmp"
/bin/chmod 600 "$manifest_receipt_tmp"
/bin/mv "$manifest_receipt_tmp" "$manifest_receipt"

/usr/bin/install -m 600 ops/launchd/com.mastermind.optionssparseselector.plist \
  /Users/chriswong/Library/LaunchAgents/com.mastermind.optionssparseselector.plist
/usr/bin/shasum -a 256 \
  /Users/chriswong/Library/LaunchAgents/com.mastermind.optionssparseselector.plist > \
  /Users/chriswong/.mastermind_private/options_sparse_selector_ops_v2/installed_plist.sha256
/bin/chmod 600 \
  /Users/chriswong/.mastermind_private/options_sparse_selector_ops_v2/installed_plist.sha256
/bin/launchctl enable gui/501/com.mastermind.optionssparseselector
/bin/launchctl bootstrap gui/501 \
  /Users/chriswong/Library/LaunchAgents/com.mastermind.optionssparseselector.plist
/usr/bin/printf '0\n' > \
  /Users/chriswong/.mastermind_private/options_sparse_selector_ops_v2/launchctl_bootstrap.exit
/bin/chmod 600 \
  /Users/chriswong/.mastermind_private/options_sparse_selector_ops_v2/launchctl_bootstrap.exit
```

Do not kickstart the job for acceptance. Let the next normal 300-second fire
exercise the runner; outside exact NYSE RTH that fire records no selector
generation and performs no backfill.

The installer accepts only that caller-created, otherwise-empty `0700` fixed
root with the exact `0600` marker. It refuses an existing closure or any extra
entry; an upgrade therefore needs a separately reviewed immutable runtime-root
version. It must not create or erase the durable selector store. Preserve the
install receipt, exact `origin/main` commit, plist SHA-256, sealed-runtime
manifest SHA-256, and bootstrap exit code under the operational root.
The supervised parent `chmod` is a prerequisite on the M1 host: it only removes
group/other traversal from the caller-owned private namespace and does not
change or delete any existing producer object.

The first v1 operational fire on 2026-08-14 refused before reading source or
creating the selector root because the runner treated manifest-sealed,
non-executable native libraries as executable-only files. Retain the v1 runtime
and operational roots unchanged as incident evidence; never reuse or copy them.
This v2 installation accepts only the carrier-sealed native modes while still
requiring the copied Python executable itself to be `0555`.

## Rollback

Rollback stops future attempts and preserves all evidence:

```sh
/bin/launchctl bootout gui/501/com.mastermind.optionssparseselector
/bin/launchctl disable gui/501/com.mastermind.optionssparseselector
```

Retain the plist, checkout, sealed runtime, operational receipts/logs, and the
entire `/Users/chriswong/.mastermind_private/options_sparse_selector_v1` durable
store. Never remove the selector root to make a retry appear fresh. A restart or
replacement activation must authenticate and continue that same head.

## Live proof

After bootstrap, prove the loaded job and the private authenticated store without
calling the nightly producers:

```sh
/bin/launchctl print gui/501/com.mastermind.optionssparseselector > \
  /Users/chriswong/.mastermind_private/options_sparse_selector_ops_v2/launchctl_print.txt
/bin/chmod 600 \
  /Users/chriswong/.mastermind_private/options_sparse_selector_ops_v2/launchctl_print.txt
/Users/chriswong/.mastermind_private/options_sparse_selector_runtime_v2/runtime/bin/python3.12 \
  -I -S -B \
  /Users/chriswong/options-sparse-selector-ops-wt/scripts/run_options_sparse_selector.py --status
```

The fixed private `options_sparse_selector_ops_v2/launchd.{stdout,stderr}.log`
files opened by launchd are supporting diagnostics only, never canonical
receipts. The runner-owned records under the fixed operational root are the
retained proof: `status.json`, `halt.json`, `slot_claim.json`, and immutable
`transitions/<head_id>.json` receipts; `launchctl_print.txt` is the separately
retained loaded-job observation.

Acceptance has two honest stages. An after-hours loaded-service proof is a
normal `SKIPPED` fire: it binds the plist, process result, target host, sealed
runtime, Theta reachability, and evidence-root identities, while the selector
root, source, slot claim, HEAD, and transition receipt remain absent until RTH.
The first RTH generation proof additionally binds the exact source commit and
three Git blob IDs, authenticated selector HEAD, immutable per-HEAD transition,
generation (maximum 128), expiry, W1A-forbidden/proposal-disabled flags, and
separate cycle/candidate/decision counts. Both stages show no handoff
destination or public artifact. When decision count first becomes nonzero (at
most 128, from one fully settled manifest), the proof must also show that the
service's advance fence is closed; a subsequent status-only invocation must
leave the head and object census unchanged.

The normal repository deployment proof at `https://mastermind-x.com/api/health`
establishes that the merged code reached the web production checkout. It does not
replace the separate M1 launchd and durable-store proof.

## Required target profile

The only acceptable proof and operational host is:

- hardware model `Mac13,1`, machine `arm64`;
- local Theta at `127.0.0.1:25503`;
- Python source `/Users/chriswong/miniconda3/envs/plane/bin/python3.12`.

The current Studio is not this host and has no reviewed `plane` environment.
Do not substitute a Homebrew/Cask Python, a symlink into another checkout, or
an existing option/NBBO root. A fresh target-host execution is required before
any installation or live claim.

## What the disposable proof does

The explicit proof API copies only the selector's current import closure:

- Python, its standard library, and `libpython3.12.dylib`;
- the reviewed IANA timezone database, excluding its duplicate `posix/` and
  `right/` trees;
- `attr`, `attrs`, `dateutil`, `idna`, `jsonschema`, `jsonschema_specifications`,
  `numpy`, `pandas`, `pyarrow`, `pytz`, `referencing`, `rpds`, `six.py`, and
  `typing_extensions.py`;
- native files directly in that closure plus a dependency named by one of those
  files. It never inventories the whole mutable conda `lib/` directory.

Every source object is checked for a regular, non-symlink,
non-group/world-writable identity before and after copying. Reviewed Conda
package hardlinks are read under that exact inode/size/mode/time fence, while
every copied target is newly created and single-link. The carrier seals the
target read-only, hashes its exact files, rejects unexpected files, target
symlinks/hardlinks and unsafe modes. A named, same-directory Conda dylib alias
is identity-fenced and copied as regular bytes under the alias name; absolute,
multi-hop, or escaping aliases fail and no symlink is reproduced. The carrier
rewrites source-prefix native IDs/edges
and `LC_RPATH` entries to target-relative `@loader_path` bindings, and
re-attests the graph. Because Mach-O rewriting invalidates prior signatures,
the disposable copies are ad-hoc signed and every native object is then
strictly verified before sealing. The copied Python must also dyld-load every
sealed library/bundle—not merely the subset reached by one package import.
System
dependencies are limited to `/usr/lib` and `/System/Library`; all other native
escapes fail closed.

The proof then starts the copied Python with `-I -S -B`, imports every listed
dependency from the sealed site-packages directory, and imports the bounded
selector core, operational runner, and `engine.private_auth_dict`. It records only a
zero-authority, zero-training closure manifest inside the caller-created
disposable root.

The import proof also replaces `sys.path` with the sealed runtime and the exact
review checkout, then rejects any imported module that resolves outside those
two roots or back into the mutable source environment. It resets stdlib
`zoneinfo` to the sealed database before importing the selector and proves an
`America/New_York` lookup, so timezone rules cannot fall back to the mutable
Conda prefix.

The import check binds and hashes `engine/options_sparse_selector.py`,
`engine/private_auth_dict.py`, `scripts/run_options_sparse_selector.py`, and
`ops/launchd/run_options_sparse_selector_verified.py` across that check. The v2
manifest persists those exact bytes under
`repo_import_source_sha256`. The persistent installer also proves the clean
checkout is the exact supplied `origin/main` release commit; do not transplant
the pre-activation source hashes into a new receipt.

These byte hashes make a receipt self-binding to the imported sources. A
disposable receipt alone does **not** prove Git/release provenance; the
persistent installer adds the separate clean exact-`origin/main` release fence.

## Historical v1 disposable Mac13,1 proof — 2026-08-14

The proof below used the v1 manifest. It transiently checked that the two repo
sources did not change across the isolated import, but discarded their hashes
instead of persisting them. It is retained as historical closure evidence only
and does not satisfy the v2 source-binding gate for a future arm review.

The exact carrier SHA-256
`ae187f271985c8c1d37aa7ed60bf6c542c2b34d5dbbbdbfb8c13866dab7acd33`
completed the explicit proof on the reviewed `Mac13,1`/`arm64` host with local
Theta reachable. The command exited `0` with zero stderr. Its canonical
`runtime_closure.json` is 1,432,354 bytes, SHA-256
`6bae097c5d7d841379c3e3d2e50896bc7d09c919777beeb653c0ee8e3cd06dfa`;
the printed JSON is the identical object plus its terminal newline.

The historical receipt binds 8,007 files / 294,750,046 bytes, 197 strictly verified
ad-hoc-signed native objects, 196 successful in-carrier dyld loads, all 14
declared isolated dependency imports, the sealed timezone database, and exact
`authority=false` / `training=false`. Independent post-proof inspection found
zero symlinks, zero multi-link files, and no mutable source-prefix value in any
native ID, dependency, or `LC_RPATH`. The copied runtime was then removed to
restore host disk; the stdout and manifest receipts were retained under the
caller-owned disposable proof parent.

This is historical carrier evidence only. It is not a production install,
release-provenance receipt, selector cycle, producer invocation, or activation
gate. At the time it was produced, it did not change the then-code-unarmed state;
it does not prove that this bounded canary is installed or live.

## Historical disposable-proof procedure

For a new closure audit, on the actual Mac13,1 host, create a disposable
directory—not a private selector/NBBO root—and mark it:

```sh
proof_root="$(mktemp -d /private/tmp/options-sparse-selector-disposable.XXXXXX)"
chmod 700 "$proof_root"
printf 'options.sparse_selector.disposable_root/v1\n' > "$proof_root/.options_sparse_selector_disposable_root"
chmod 600 "$proof_root/.options_sparse_selector_disposable_root"

/usr/bin/python3 \
  /path/to/macro/ops/launchd/run_options_sparse_selector_verified.py \
  --prove-disposable-target \
  --source-root /Users/chriswong/miniconda3/envs/plane \
  --target-root "$proof_root" \
  --repo-root /path/to/macro
```

The only intentional writes are under `proof_root`: `runtime/` and
`runtime_closure.json`. The command checks Mac13,1 and the local Theta TCP
endpoint but does not issue a Theta request. It has no selector/NBBO producer
imports, private-root creation, network Git access, or external publication
path.

Retain the manifest and command output for independent review. If copying,
relocation, native re-attestation, or isolated imports fail, stop: add no
ambient library or exception. The exact missing edge must be reviewed as a new
closure change. Caller-owned disposable roots may be removed only by the
operator after retaining the receipt; the carrier deliberately never recurses
over or deletes a caller-provided directory.

## Scope that remains outside this activation

This canary does not satisfy any of the following later gates:

1. authenticated, bounded W1A replication and a new proposal-capable review;
2. executable NBBO lifecycle/cohort evidence;
3. any handoff or downstream consumer;
4. any public surface, trade, portfolio, model-training, Prophet, or Neural Web
   authority; and
5. operation after the first settled decision, after 128 generations, or after
   `2026-08-21T20:00:00Z`.

The frozen preregistration remains historical evidence only. The private canary
may establish operational liveness and one fully settled manifest of honest
abstentions; it cannot establish selection utility or promotion readiness.
