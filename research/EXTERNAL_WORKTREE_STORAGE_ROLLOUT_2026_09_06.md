# External worktree storage — 2026-09-06

Chris approved placing new Codex and Claude worktrees on the external 4 TB SSD.
This policy reduces internal disk growth; it does not increase RAM or limit
running agents. Existing active worktrees and shared Git object stores stay put.

## Host layout and identity

The host policy is `~/.config/mastermind/worktree-storage.json`. It records a
volume UUID, mount point, workspace root and minimum available bytes. The verified
Mac Studio target is APFS `/Volumes/Mastermind`, volume UUID
`7EE5D196-8BB6-4E6D-B1D7-AFEA5DEB172A`. The initial free-space floor is 100 GiB.
The similarly named 1 TB NTFS Worktrees volume is not this target.

| Consumer | Location below `/Volumes/Mastermind/agent-workspaces` |
| --- | --- |
| Codex native Worktree root | `codex/` |
| Claude Desktop custom location | `claude/` |
| Shared creation helper | `claude/<repository-hash>/<name>-<session-hash>/` |
| Isolated maintenance | `maintenance/.claude/worktrees/` |
| Verification and reversible installation receipts | `audit/`, `backups/` |

The helper is installed at
`~/.local/lib/mastermind/worktree-storage/worktree_storage.py`. Its small host
policy and hook files remain internal so they can report a missing SSD. Git's
existing common directories remain the single worktree registries. The helper's
small receipts identify repeated creation requests; they are not leases,
workstream ownership, an agent scheduler or an additional control plane.

## Creation contract

```sh
python3 ~/.local/lib/mastermind/worktree-storage/worktree_storage.py check
python3 ~/.local/lib/mastermind/worktree-storage/worktree_storage.py create < request.json
```

`request.json` contains `cwd`, `name`, and the actual current `session_id` supplied
by the caller. `cwd` is an existing Git checkout; `name` is an alphanumeric slug
with dots, underscores or hyphens, up to 100 characters. Never use another
session's identity. A caller without an identity gets a new random carrier;
identity-less repeats are not reuse proof. The final stdout line is the absolute
worktree path; errors go to stderr and return nonzero.

The helper verifies the mount's UUID, external APFS identity, writeability,
available space, path containment and device identity before directory creation.
It rejects symlinks and parent traversal. No unavailable, wrong, read-only or
low-space volume permits an internal fallback. Directory creation walks open
directory descriptors with `O_NOFOLLOW`.

The repository's origin default branch is fetched into a request-specific ref
and resolved to an immutable commit. `pr-N` names select the requested PR head.
Repositories without origin use local HEAD. An origin with no identifiable
default branch fails rather than silently using a stale HEAD. Worktrees are
created `--no-track --no-checkout`, then sparsified according to the donor's
`config/sparse_worktree.json` before file checkout. A per-repository flock only
serializes this Git transaction; it does not limit running work.

Repeated requests reuse a path only when the receipt, Git registration, common
directory, branch and session-derived identity agree. Dirty work in that exact
carrier is preserved. Foreign directories, missing receipted carriers and failed
partial creations are retained for inspection; they are never force-deleted.

## Native apps and lifecycle protection

Codex exposes **Settings → Worktrees → Worktree root**. Set it to
`/Volumes/Mastermind/agent-workspaces/codex`. Codex creates the checkout before
setup/SessionStart, so it may briefly materialize a full checkout on the SSD.
The Macro setup command `worktree_sparse.py auto` now both protects the external
Git registration and preserves the sparse profile. A global user SessionStart
hook supplies the same protection for other projects and older snapshots.
Codex requires review/trust of a new exact hook definition through `/hooks`.
Installation does not edit its private setting or trust stores.

Claude Desktop exposes **Settings → Claude Code → Worktree location → Custom**.
The installer sets only `preferences.chillingSlothLocation.customPath` in each
existing `Claude*/claude_desktop_config.json`, preserving other preferences and
account fields. Profiles already running may need their settings reloaded or a
new session; file readback alone is not proof of a native creation.

Claude's WorktreeCreate hook takes precedence over its native custom location.
The checked-in Macro hook delegates to the host policy when installed, while
retaining portable behavior on unconfigured hosts. The global CLI hook uses the
installed helper. Older project-hook snapshots must be reconciled before
enabling the global creator: different settings layers can expose multiple
creators, and a legacy creator can still write internally. Never restore the
duplicate local WorktreeCreate wiring removed by the existing F00 owner.

Both clients' startup protection adds a removable-volume Git lock, preserves any
existing operator lock, and sparsifies only a clean checkout without an existing
sparse selection. Existing internal checkouts are grandfathered. Raw Git commands
and independent launchers must use the helper by policy; this implementation is
not an OS sandbox preventing arbitrary filesystem writes.

## Installation and staged activation

Report first from an accepted source checkout:

```sh
python3 scripts/install_worktree_storage.py \
  --mount /Volumes/Mastermind \
  --volume-uuid 7EE5D196-8BB6-4E6D-B1D7-AFEA5DEB172A
```

Add `--apply --without-create-hook` to install the helper, policy, native Claude
preferences and both clients' startup hooks while preserving creation wiring.
After each launching donor is reconciled, run `--apply` to install the global
Claude creator. Installation records PREPARED before mutations and APPLIED after
readback; it compares original settings bytes before atomic replacement and
refuses concurrent edits. Receipts contain only changed preference fields/hooks,
not entire account configurations. Previous helper/policy files are backed up.

The 2026-09-06 activation audit found two shared Macro launch donors with other
work in progress: the historical `Macro Dashboard` primary and `macro-main`.
Neither may be fast-forwarded or overwritten as part of an unowned deployment.
F00 handed off further creation-hook edits at #6894 head `a637a648`, whose
contention fixes are preserved here. It may update its own clean session carrier
after source acceptance. First-mint donor activation still needs a specifically
reconciled narrow host change. Manual release/Cursor launchers also need to call
the accepted helper; their existing work stays in place.

Proof is per plane: merged source, installed helper hash, native preference
readback, trusted hooks, and actual app-created SSD worktrees are distinct.
Do not describe staged installation or a CLI fixture as full native activation.

## Cleanup and rollback

External registrations use lock reason
`mastermind-external-storage: removable volume protection`. The existing GC
recognizes this reason but still applies live-process, age, clean-tree,
unpushed/open-PR and recoverability gates. Other locks retain their usual force.
External app grouping directories are not treated as orphan worktrees.

GC rechecks the volume and registration immediately before removal, uses
non-forced removal, and restores the storage lock from the surviving registration
on failure—even when the worktree directory has disappeared. It stops before
prune after that failure. An unverified SSD blocks deletion and pruning.
Existing arming and retention settings are not changed by this rollout. The existing
launchd wrapper must also be updated from accepted source: it extracts the GC
script, storage helper and config together from one resolved `origin/main` commit.
Missing bundle members refuse the sweep. Preserve its schedule and repo binding;
verify the installed preimage and keep a backup before replacing only this wrapper.

To roll back, use the installation receipt to restore only the specific native
preference and hook fields changed by this task, checking they still match the
installed values first. Restore the backed-up helper/policy, or remove those
files only when the receipt proves this installer created them. Keep all Git
registrations and worktree directories. Preserve unrelated settings written
since installation. Do not restore the removed duplicate legacy creator.

## Verification

Focused tests use real small Git repositories, with the volume probe faked only
for unavailable/wrong-volume cases. They cover sparse creation, same-session
parallel repeats, foreign/dirty carrier preservation, failed fetches, native
Codex's actual auto entry point, operator locks, safe GC removal, work becoming
dirty after classification, and drive disappearance during removal. Installer
tests cover unrelated settings, staged hooks and concurrent-update refusal.

Live smoke evidence belongs under the SSD `audit/` directory and must include
volume/device identity, actual hook command, clean sparse Git status and locked
registration. Simulate a wrong UUID in a separate test policy; never disconnect
the live SSD to test failure. These host changes do not require a website render
or VPS service restart.

References: [Codex worktrees](https://learn.chatgpt.com/docs/environments/git-worktrees),
[Codex hooks](https://learn.chatgpt.com/docs/hooks),
[Claude Desktop](https://code.claude.com/docs/en/desktop#work-in-parallel-with-sessions),
[Claude WorktreeCreate](https://code.claude.com/docs/en/hooks#worktreecreate),
[Git worktree](https://git-scm.com/docs/git-worktree).
