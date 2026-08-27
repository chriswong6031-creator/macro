---
key: SEALED-PC-CI-REPLAY-AND-PORTABILITY-NEED-EXPLICIT-RUNTIME-BINDINGS
claim: >
  An attested setup-python 3.12.13 pack can still fail on a sealed PC without
  interpreter drift: re-executing its dynamic binary under a scrubbed environment
  loses the shared-library directory; RestrictSUIDSGID=true refuses a test fixture's
  real set-ID chmod; Git 2.43 does not demonstrate the same diff.trustExitCode
  poisoning result as newer Git; and a detached exact-SHA checkout has no branch
  name unless the main-defined executor explicitly projects the PR metadata.
falsifier: >
  Show the exact run using a non-3.12.13 pack interpreter before the logical step,
  a successful set-ID chmod inside RestrictSUIDSGID=true, identical poisoned-diff
  behavior on Git 2.43 and the hosted Git client, or a detached reusable-workflow
  pack that receives the PR branch identity without an explicit environment binding.
so_what: >
  Keep the sealed service and exact detached checkout. Derive LD_LIBRARY_PATH from
  the selected interpreter's contained LIBDIR/LDLIBRARY for replay and keyless
  subprocess probes; never inherit ambient loader state or credentials. Simulate
  set-ID descriptor metadata against the exact fixture inode instead of weakening
  RestrictSUIDSGID. Reject the malicious Git config even on clients that cannot yet
  demonstrate the bypass. Project CI_BASE_REF/CI_HEAD_REF from GitHub's caller
  metadata in the protected-main executor.
kind: landmine
verified_at: 2026-08-27
verified_by: >
  PR #6505 exact-head run 33043922465 at eb2c7758c9cdefc42638ce5b5d92379950fcb41c;
  complete twelve-pack census and job logs for 98424740048, 98424740142 and
  98424740051; systemd transient-unit reproduction returning EPERM for chmod 2444
  with RestrictSUIDSGID=true; local executed regression tests for contained loader
  derivation, credential stripping, exact-inode mode injection, Git 2.43 behavior
  and detached branch metadata.
scope: [macro, "scripts/run_ci_pack.py", ".github/workflows/trusted-ci-executor.yml", "tests/**", "ops/runner-host/pc/**"]
confidence: verified
---

## Exact incident receipt

Run 33043922465 proved the production topology itself: hosted plan and contract
delta passed, all twelve trusted jobs acquired pc-ci-1/2/3 in groups of three,
nine packs passed, and packs 5, 6 and 9 were the complete red set. The pack
runner attested Python 3.12.13 before logical execution. The later 3.12.3 message
came from exact-base replay re-executing the same dynamic interpreter after its
small child environment discarded the setup-python loader binding.

Pack 5's two `chmod` failures were modes 04444 and 02444 only. A host probe under
`RestrictSUIDSGID=true` reproduced EPERM exactly; ordinary macroci chmod outside
that restriction succeeded. The security boundary is correct, so the test now
injects unsafe descriptor mode metadata only for the captured `active.json`
device+inode.

Pack 6 deliberately invoked `sys.executable` with only PATH and HOME. The shared
3.12.13 binary then loaded Ubuntu's 3.12.3 libpython and `_ctypes` failed with
`_PyErr_SetLocaleString`. The keyless subprocess now derives its own library
directory from sysconfig, and exact-base replay uses the same contained derivation
while stripping GitHub, OIDC, artifact and cache credentials.

Pack 9 proved two separate portability seams: Git 2.43 preserved the staged-diff
return code despite the malicious config, while the guard still had to reject that
config; and the self-mod fence received an empty branch because protected-main
execution intentionally checked out a detached immutable candidate. The executor
now supplies the base/head metadata contract already used by the hosted pack path.
