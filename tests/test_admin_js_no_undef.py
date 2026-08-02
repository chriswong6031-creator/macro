"""The admin console's JavaScript must have no out-of-scope references.

`admin/static/app.js` is a flat top-level browser script, and nothing in CI ran
any scope analysis over it. PR #3693 shipped `ReferenceError: rejBox is not
defined` — a `let rejBox` declared inside `RENDER.marketing_outbox`, read from
the separate top-level `obxRenderLive` — and the admin Outbox panel rendered
BLANK in production for ~2 days before #3871 module-scoped it as `OBX_REJ`.
`node --check` cannot see this: an undefined identifier is valid syntax.

This suite drives `scripts/check_admin_js.py` (eslint, one rule: `no-undef`)
over the real tree, and plants the #3693 defect shape in a temp file so the
guard can never silently stop detecting the thing it exists to detect.

Run: python3 -m pytest tests/test_admin_js_no_undef.py -q
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CHECKER = ROOT / "scripts" / "check_admin_js.py"

# Generous: the checker itself allows 180s for a cold `npx` fetch of eslint.
RUN_TIMEOUT_S = 300

TOOLING_UNAVAILABLE = 2


def _run_checker(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CHECKER), *args],
        capture_output=True,
        text=True,
        timeout=RUN_TIMEOUT_S,
        cwd=str(ROOT),
    )


def _tooling_unavailable(reason: str) -> None:
    """Abort loudly — and in CI, RED.

    A skip-if-missing tripwire is not a tripwire. `pytest.importorskip`-shaped
    availability gates have already disarmed guards in this repo's minimal CI
    lanes, which install a narrow dependency set rather than requirements.txt
    (memory: `ci-packs-install-minimal-deps-not-requirements`) — the suite reads
    green while checking nothing. That is the precise failure mode of #3693: no
    signal, so the defect shipped. If this guard cannot run inside CI, the guard
    is broken and the pack must go red; only a developer machine without node
    gets the skip.
    """
    if os.environ.get("CI"):
        pytest.fail(
            "admin-js no-undef guard could not run IN CI — a skip here would "
            "disarm the guard exactly the way #3693 shipped unseen. Fix the "
            f"runner (node 20 + npx must be on PATH), do not skip.\n{reason}"
        )
    pytest.skip(
        "SKIPPING A REAL GUARD: node/npx unavailable locally, so the admin-js "
        f"no-undef check did not run. This would FAIL, not skip, in CI.\n{reason}"
    )


def _require_tooling() -> None:
    for tool in ("node", "npx"):
        if shutil.which(tool) is None:
            _tooling_unavailable(f"`{tool}` is not on PATH.")


def _check(*args: str) -> subprocess.CompletedProcess:
    """Run the checker, converting its exit-2 tooling failure into fail-or-skip."""
    _require_tooling()
    proc = _run_checker(*args)
    if proc.returncode == TOOLING_UNAVAILABLE:
        _tooling_unavailable(
            f"checker exited {TOOLING_UNAVAILABLE}.\n"
            f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}"
        )
    return proc


def test_admin_static_js_has_no_undefined_references():
    proc = _check()
    assert proc.returncode == 0, (
        "admin/static/*.js references a name that is not in scope. Every hit "
        "throws a ReferenceError the moment its code path runs, blanking the "
        "admin panel (PR #3693 → #3871). Declare the binding where all its "
        "readers can see it (module scope, like `OBX_LAST`/`OBX_REJ`).\n"
        f"--- checker exit {proc.returncode} ---\n"
        f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}"
    )


def test_guard_catches_a_planted_offender(tmp_path):
    """The #3693 shape verbatim: a function-local `let` read by a sibling function.

    Nothing needs to execute — the defect is visible to scope analysis alone,
    which is the whole reason a guard can catch what code review did not.
    """
    planted = tmp_path / "planted_offender.js"
    # Everything except the cross-function reference is properly declared, so a
    # single finding proves the guard catches THIS shape and not merely any
    # unknown global.
    planted.write_text(
        '"use strict";\n'
        "\n"
        "async function api(path) { return path; }\n"
        "function rejectionBox(payload) { return String(payload); }\n"
        "\n"
        "async function renderMarketingOutbox() {\n"
        "  let rejBox = null;\n"
        '  try { rejBox = await api("/api/marketing/rejections"); } catch (e) { rejBox = null; }\n'
        "  return rejectionBox(rejBox);\n"
        "}\n"
        "\n"
        "function obxRenderLive() {\n"
        "  // Out of scope: rejBox lives in renderMarketingOutbox, not here.\n"
        "  return rejectionBox(rejBox);\n"
        "}\n",
        encoding="utf-8",
    )

    proc = _check(str(planted))
    combined = proc.stdout + proc.stderr
    assert proc.returncode == 1, (
        "guard did NOT flag the planted #3693 offender — it has stopped "
        "detecting the defect class it exists for.\n"
        f"--- checker exit {proc.returncode} ---\n{combined}"
    )
    assert "no-undef" in combined, f"finding is not a no-undef report:\n{combined}"
    assert "rejBox" in combined, f"finding does not name rejBox:\n{combined}"
