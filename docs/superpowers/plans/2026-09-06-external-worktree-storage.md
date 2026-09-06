# External SSD worktree storage implementation plan

Approved design: current task, 2026-09-06. New local agent worktrees belong on the verified 4 TB SSD. Existing worktrees and shared Git stores remain in place.

Goal: configure Codex and every installed Claude profile, install one host storage-policy helper, and integrate the existing Macro lifecycle and cleanup tools.

Constraints: UUID 7EE5D196-8BB6-4E6D-B1D7-AFEA5DEB172A; mount /Volumes/Mastermind; root /Volumes/Mastermind/agent-workspaces; no internal fallback; no process/runner/concurrency-policy changes; preserve all unrelated settings; no live-drive disconnect test. Creation-hook edits wait for #6894 owner reconciliation. Codex self-UI is blocked by the tool; the user has the native setting instruction.

- [ ] Implement scripts/worktree_storage.py with a host JSON policy reader, volume UUID/read-write/space/containment checks, destination derivation, exact-session creation idempotency, and generic sparse Git creation. Test using real small Git repositories and mocked diskutil only.
- [ ] Verify refusal before mutation for unavailable/wrong/read-only/full disks, symlink/path escapes and foreign destinations; verify clean sparse creation, repeat invocation and parallel exact-session calls.
- [ ] Integrate the existing creation hook after owner reconciliation; extend sparse recognition and GC scope without changing retention gates or unrelated locks.
- [ ] Install the tested helper and host policy with backups. Preserve the existing duplicate-hook removal. Apply only the Claude native custom-path preference to each installed profile, and wire one canonical CLI hook for new sessions.
- [ ] Verify native settings readback, live SSD creation and device identity, clean Git state and failure behavior. Record per-profile proof and any pending activation.
- [ ] Review source diff, run focused tests, commit/push/PR, resolve CI, merge and verify installed host bytes against accepted source. Keep app proof separate from source proof.

Verification commands: python3 -m unittest discover -s tests -p test_worktree_storage.py; focused pytest for tests/test_worktree_placement.py, tests/test_sparse_worktree_profile.py, tests/test_agent_worktree_roots.py and tests/test_worktree_gc.py. Store live receipts below the SSD audit directory; do not include profile secrets in commits.
