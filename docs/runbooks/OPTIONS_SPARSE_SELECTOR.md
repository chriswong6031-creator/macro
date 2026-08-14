# Options sparse selector — sealed runtime carrier

## Current state

The selector is code-unarmed. `SELECTOR_RUNTIME_ARMED` is the literal `False`
constant in both the selector core and this carrier. No environment value, CLI
argument, receipt, host fact, marker, or successful proof can change it.

This change does **not** install a plist, create a production/private root,
load launchd, call Git/SSH, contact a producer, append a ledger, or run a
selector cycle. It does not cover NBBO collection or handoff. It grants no
signal, ranking, sizing, trading, publication, training, or completion
authority.

The carrier is a preparation artifact only. A successful disposable proof is
not an activation receipt and is not permission to change the code-only arm.

## Required target profile

The only acceptable proof host is:

- hardware model `Mac13,1`, machine `arm64`;
- local Theta at `127.0.0.1:25503`;
- Python source `/Users/chriswong/miniconda3/envs/plane/bin/python3.12`.

The current Studio is not this host and has no reviewed `plane` environment.
Do not substitute a Homebrew/Cask Python, a symlink into another checkout, or
an existing option/NBBO root. A fresh target-host execution is required before
any activation review.

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
dependency from the sealed site-packages directory, and imports the current
unarmed selector core plus `engine.private_auth_dict`. It records only a
zero-authority, zero-training closure manifest inside the caller-created
disposable root.

The import proof also replaces `sys.path` with the sealed runtime and the exact
review checkout, then rejects any imported module that resolves outside those
two roots or back into the mutable source environment. It resets stdlib
`zoneinfo` to the sealed database before importing the selector and proves an
`America/New_York` lookup, so timezone rules cannot fall back to the mutable
Conda prefix.

The import check binds and hashes `engine/options_sparse_selector.py` and
`engine/private_auth_dict.py` across that check. It is **not** a Git/release
provenance verifier: production checkout/release authentication remains a
separate, later reviewed installation slice.

## Disposable Mac13,1 proof — 2026-08-14

The exact carrier SHA-256
`ae187f271985c8c1d37aa7ed60bf6c542c2b34d5dbbbdbfb8c13866dab7acd33`
completed the explicit proof on the reviewed `Mac13,1`/`arm64` host with local
Theta reachable. The command exited `0` with zero stderr. Its canonical
`runtime_closure.json` is 1,432,354 bytes, SHA-256
`6bae097c5d7d841379c3e3d2e50896bc7d09c919777beeb653c0ee8e3cd06dfa`;
the printed JSON is the identical object plus its terminal newline.

The receipt binds 8,007 files / 294,750,046 bytes, 197 strictly verified
ad-hoc-signed native objects, 196 successful in-carrier dyld loads, all 14
declared isolated dependency imports, the sealed timezone database, and exact
`authority=false` / `training=false`. Independent post-proof inspection found
zero symlinks, zero multi-link files, and no mutable source-prefix value in any
native ID, dependency, or `LC_RPATH`. The copied runtime was then removed to
restore host disk; the stdout and manifest receipts were retained under the
caller-owned disposable proof parent.

This is prospective carrier evidence only. It is not a production install,
release-provenance receipt, selector cycle, producer invocation, or activation
gate, and it does not change the code-unarmed state.

## Later Mac13,1 procedure (read-only of production state)

Only after this carrier is independently reviewed, on the actual Mac13,1 host,
create a new disposable directory—not a private selector/NBBO root—and mark it:

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

## Gates still outstanding

Before any future arm review, all of the following remain required:

1. independent audit of this carrier and its target-host proof;
2. exact clean-checkout/release provenance and a separately reviewed private
   runtime installation (without producer advance);
3. authenticated producer adapter and restricted W1A-export proof;
4. separate NBBO lifecycle/cohort/handoff evidence; and
5. a new, exact reviewed code change to arm anything.

Until every gate passes, selector coverage remains zero by design.
