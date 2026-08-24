---
key: W2C-M0D-EXPERIENCE-V2-TMPFS-OPTIONAL-V1-INACCESSIBLE
claim: >
  On systemd 255, TemporaryFileSystem=/var/lib/macro-market-memory:ro is
  applied before nested InaccessiblePaths. Unbound v1 siblings
  (state/sources, state/technicals-v1, state/experience-v1) are therefore
  absent inside the experience-v2 namespace even when those directories
  exist on the host. Mandatory InaccessiblePaths for any one of those three
  aborts setup with 226/NAMESPACE before ExecStart. The optional '-' prefix
  on that exact class lets namespace construction succeed; the tmpfs remains
  the default deny, and a present target is still masked.
falsifier: >
  A disposable oneshot with the same TemporaryFileSystem plus BindReadOnlyPaths
  / BindPaths as experience-v2, and mandatory InaccessiblePaths for one of
  those three siblings, reaches ExecStart=/bin/true instead of 226/NAMESPACE;
  or the same unit with the optional '-' prefix can ls a v1 sibling or the
  spy-rest credential directory from inside the namespace.
so_what: >
  Do not restore mandatory InaccessiblePaths for tmpfs-hidden unbound v1
  siblings on experience-v2. Optionalizing that class is not an isolation
  weakening. Do not optionalize paths outside the tmpfs that still exist at
  setup (credential dir, options stores). Do not start the real
  experience-v2 writer to prove this.
kind: runtime
verified_at: 2026-08-24
verified_by: >
  Host path ls showed experience-v1, sources, and technicals-v1 present.
  Sunday and Monday 04:32Z journals: status=226/NAMESPACE at
  /var/lib/macro-market-memory/state/experience-v1. Disposable canaries
  mm-ns-canary-a/b/c each failed 226 on one mandatory sibling; mm-ns-canary-d
  with all three optional reached /bin/true. Exact repaired-sandbox isolation
  canary: v2 inputs readable/not writable, experience-v2 writable, v1
  siblings and spy-rest credentials inaccessible, AF_INET unavailable.
  Real experience-v2.service was not started.
scope:
  - macro
  - "WS:MARKET-MEMORY-W2C"
  - app/deploy/macro-market-memory-experience-v2.service
confidence: verified
---

# experience-v2 226/NAMESPACE is tmpfs-hidden mandatory InaccessiblePaths

v1 experience already documents this: the root tmpfs is mounted before
nested defence-in-depth masks, so unbound siblings are absent and need `-`.
M0D v2 copied the masks without the optional prefix. systemd reports
`experience-v1` first because it sorts paths; `sources` and `technicals-v1`
fail the same way.
