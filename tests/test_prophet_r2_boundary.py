"""Boundary tests for DEC:B1-PROPHET-PUBLIC-SPLIT.

The full US Prophet plan book (site/prophet/index.json — 262+ plans with
entries/targets/invalidations/theses) must never be reachable from public R2
again: the origin 401s the path (premium/private), but public R2 answered it
anonymously.  Sol's closure ruling makes the producer structurally closed —
this file pins that closure at the boundary, not the behavior underneath it.

Two §8b reviewer findings on the first closure are pinned here too:

  1. The tombstone that deletes a reappeared prophet/index.json used to live
     inside the R2 health-publisher step, gated
     ``if: steps.prophet_checkpoint.outputs.r2_ready == 'true'`` — true ONLY
     on a night the index content actually changed.  On an unchanged-index
     night the whole step was skipped, so NO tombstone ran.  The tombstone is
     now a dedicated step (`enforce Prophet R2 index tombstone
     (unconditional)`) gated only `if: ${{ !cancelled() }}`, so it runs on
     every nightly wake the R2 creds exist, independent of the health-publish
     gate.
  2. The old repo-wide "reintroduction sweep" matched the forbidden key
     literal and an R2-write marker (``put_object`` etc.) on the SAME LINE.
     Every real ``put_object`` call in this repo is written multi-line
     (``client.put_object(\\n    Key=...,\\n)`` — see
     scripts/build_prophet_marks.py), so a reintroduced write in the house
     idiom passed CI undetected.  The sweep is now AST-based
     (``find_forbidden_key_writes``), which is line-break-insensitive because
     ``ast.parse`` does not care where a call's argument list wraps.

Deterministic only: no subprocess, no network, no fixture repo.  Every test
here must also run in a sparse worktree (no site/ or data/ dependency, and
admin/tools may not be checked out at all — the AST sweep skips missing
dirs).

Run: python3 -m pytest tests/test_prophet_r2_boundary.py -q
"""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DAILY = ROOT / ".github" / "workflows" / "daily.yml"

FORBIDDEN_KEY = "prophet/index.json"

_THIS_FILE = Path(__file__).resolve()
_EXEMPT_FROM_LITERAL_SWEEP = {
    (ROOT / "scripts" / "build_prophet.py").resolve(),
    _THIS_FILE,
}


# ---------------------------------------------------------------------------
# AST-based, line-break-insensitive detector (reviewer finding #2). Shared by
# the repo-executable sweep below and its own non-vacuity self-test.
# ---------------------------------------------------------------------------
#: boto3/S3 client method names that write an object. ``put`` covers
#: file-like ``Object(...).put(...)`` call sites in addition to the client
#: method spellings.
_R2_WRITE_CALL_NAMES = {"put_object", "upload_file", "upload_fileobj", "copy_object", "put"}


def find_forbidden_key_writes(code: str, forbidden_key: str = FORBIDDEN_KEY) -> list[str]:
    """Scan ``code`` for a ``Key=<forbidden_key>`` (or a path ending in
    ``/<forbidden_key>``) keyword argument on any R2/S3-write-shaped call.

    Unlike a same-line text sweep, this is immune to how the call wraps
    across lines: ``ast.parse`` builds one ``Call`` node for
    ``client.put_object(\\n    Bucket=b,\\n    Key="prophet/index.json",\\n)``
    regardless of line breaks, so the ``Key`` keyword is found by walking
    that node's ``keywords``, not by re-matching text.

    Returns ``"lineno:call_name"`` strings for every offending call; an empty
    list means clean. Input that is not valid Python (e.g. a YAML file, or a
    shell fragment) raises ``SyntaxError`` from ``ast.parse``, which is
    treated as "no Python call sites found" here rather than propagated —
    callers that need to check non-Python text (daily.yml) use a text-level
    regex instead, see ``test_no_workflow_contains_a_literal_forbidden_key_assignment``.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute):
            call_name = func.attr
        elif isinstance(func, ast.Name):
            call_name = func.id
        else:
            continue
        if call_name not in _R2_WRITE_CALL_NAMES:
            continue
        for kw in node.keywords:
            if kw.arg != "Key":
                continue
            value = kw.value
            if not (isinstance(value, ast.Constant) and isinstance(value.value, str)):
                continue
            key_value = value.value
            if key_value == forbidden_key or key_value.endswith("/" + forbidden_key):
                offenders.append(f"{node.lineno}:{call_name}")
    return offenders


def test_ast_detector_flags_the_multiline_put_object_idiom() -> None:
    """Non-vacuity self-test: the exact house idiom that broke the OLD
    line-local sweep (scripts/build_prophet_marks.py:1282-style — a
    multi-line ``put_object`` call whose ``Key=`` keyword sits on its own
    line, below the call) MUST be flagged. A future regression of this test
    file back to a line-local sweep fails HERE first, loudly, rather than
    silently passing an estate sweep that never runs on real multi-line
    code."""
    code = (
        "client.put_object(\n"
        "    Bucket=b,\n"
        '    Key="prophet/index.json",\n'
        "    Body=x,\n"
        ")\n"
    )
    offenders = find_forbidden_key_writes(code)
    assert offenders == ["1:put_object"], (
        "the AST detector failed to flag a multi-line forbidden put_object call "
        f"(got {offenders!r})"
    )


def test_ast_detector_does_not_flag_the_permitted_health_key() -> None:
    """Negative control: the same multi-line shape, writing the PERMITTED
    health key, must not be flagged."""
    code = (
        "client.put_object(\n"
        "    Bucket=b,\n"
        '    Key="prophet/health.json",\n'
        "    Body=x,\n"
        ")\n"
    )
    assert find_forbidden_key_writes(code) == []


def test_ast_detector_flags_a_nested_key_path() -> None:
    """A forbidden key reached via a namespaced/prefixed path (e.g. a future
    per-region prefix) must still be caught."""
    code = (
        "client.upload_fileobj(\n"
        "    fileobj,\n"
        "    bucket,\n"
        '    Key="us/prophet/index.json",\n'
        ")\n"
    )
    offenders = find_forbidden_key_writes(code)
    assert offenders == ["1:upload_fileobj"]


# ---------------------------------------------------------------------------
# (a) daily.yml as TEXT/AST — the publisher step publishes the health
#     receipt; the tombstone is a dedicated step that runs unconditionally
#     (reviewer finding #1); no workflow anywhere carries a literal
#     Key="prophet/index.json" assignment.
# ---------------------------------------------------------------------------
def _daily_text() -> str:
    return DAILY.read_text(encoding="utf-8")


def _step_text(daily_text: str, marker: str) -> str:
    """The raw TEXT (comments included) of one step, sliced between its own
    ``- name:`` line and the next step's ``- name:`` line."""
    start = daily_text.index(marker)
    next_step = daily_text.index("\n      - name:", start + len(marker))
    return daily_text[start:next_step]


def _publisher_step_text(daily_text: str) -> str:
    return _step_text(daily_text, "- name: publish Prophet public health receipt to R2")


def _tombstone_step_text(daily_text: str) -> str:
    return _step_text(
        daily_text, "- name: enforce Prophet R2 index tombstone (unconditional)"
    )


def test_publisher_step_publishes_the_health_receipt_key() -> None:
    step_text = _publisher_step_text(_daily_text())
    assert "prophet/health.json" in step_text
    assert "R2_HEALTH_KEY" in step_text
    assert "build_public_health_projection" in step_text


def test_publisher_step_no_longer_owns_the_tombstone() -> None:
    """The tombstone has exactly ONE owner post-fix: the dedicated
    unconditional step below. The publisher step going back to owning only
    the health put is the whole point of decoupling — a lingering second
    (still gated) copy here would defeat reviewer finding #1."""
    step_text = _publisher_step_text(_daily_text())
    assert "FORBIDDEN_INDEX_KEY" not in step_text
    assert "enforce_index_tombstone" not in step_text


def _step_condition_line(step_text: str) -> str:
    """The step's own `if:` line (not its comments/prose, which may
    legitimately discuss the gate it is decoupled from)."""
    for line in step_text.splitlines():
        if line.strip().startswith("if:"):
            return line.strip()
    raise AssertionError("step carries no `if:` line")


def test_tombstone_step_runs_unconditionally_on_every_wake() -> None:
    """Reviewer finding #1, pinned directly: the tombstone step's `if` must
    not reference r2_ready (or any other index-changed gate) — it must run
    whenever the job reaches it, `!cancelled()` only, so an unchanged-index
    night still self-heals a reappeared public index object."""
    step_text = _tombstone_step_text(_daily_text())
    condition = _step_condition_line(step_text)
    assert condition == "if: ${{ !cancelled() }}"
    assert "r2_ready" not in condition
    assert "prophet_checkpoint" not in condition


def test_tombstone_step_is_the_sole_head_delete_owner_of_the_forbidden_key() -> None:
    """Positive control: the dedicated step DOES carry the literal (via
    FORBIDDEN_INDEX_KEY) and performs the head/delete pair, proving the
    negative assertion above isn't vacuous — the tombstone moved, it wasn't
    deleted outright."""
    step_text = _tombstone_step_text(_daily_text())
    assert 'FORBIDDEN_INDEX_KEY = "prophet/index.json"' in step_text
    assert "client.head_object(Bucket=bucket, Key=FORBIDDEN_INDEX_KEY)" in step_text
    assert "client.delete_object(Bucket=bucket, Key=FORBIDDEN_INDEX_KEY)" in step_text


def test_enforce_index_tombstone_function_no_longer_exists() -> None:
    """The inline function the fix replaces must be fully gone, not just
    call-site-removed — a lingering unused definition would be dead code
    masking a partial fix."""
    assert "enforce_index_tombstone" not in _daily_text()


#: Text-level check across every workflow that could plausibly write an R2
#: object (not just daily.yml) — a reintroduction in a sibling nightly lane
#: is just as much a regression as one in daily.yml.
_SWEPT_WORKFLOWS = ("daily.yml", "closing-bell.yml", "asia-close.yml", "weekly.yml", "render.yml")

#: A boto3 keyword assignment ``Key=<value>`` is always written on ONE
#: physical source line even inside a multi-line call — only the surrounding
#: parens/other kwargs span lines, never the ``name=value`` pair itself — so
#: a whole-file (not line-local, not same-line-as-a-write-marker) regex
#: search already catches the multi-line idiom that broke the old sweep,
#: without needing to extract and per-language-parse every embedded
#: `run: |` heredoc in a YAML file that mixes bash and python across
#: hundreds of steps (extraction was judged too fragile against this file's
#: many step shapes to be worth it here; AST extraction IS used for the
#: pure-Python repo sweep below, where every swept file is uniformly valid
#: Python).
_INDEX_KEY_ASSIGNMENT_RE = re.compile(r'Key\s*=\s*[\'"]' + re.escape(FORBIDDEN_KEY) + r'[\'"]')


def test_no_workflow_contains_a_literal_forbidden_key_assignment() -> None:
    swept = 0
    for name in _SWEPT_WORKFLOWS:
        path = ROOT / ".github" / "workflows" / name
        if not path.is_file():
            continue
        swept += 1
        text = path.read_text(encoding="utf-8")
        match = _INDEX_KEY_ASSIGNMENT_RE.search(text)
        assert match is None, (
            f"{name} contains a literal Key=\"{FORBIDDEN_KEY}\" assignment — "
            "DEC:B1-PROPHET-PUBLIC-SPLIT closure regressed"
        )
    assert swept >= 1, "no workflow files were found to sweep — check _SWEPT_WORKFLOWS/paths"


def test_daily_yml_publishes_health_key_not_index_key() -> None:
    text = _daily_text()
    assert "prophet/health.json" in text
    assert "R2_HEALTH_KEY" in text


# ---------------------------------------------------------------------------
# (b) scripts.build_prophet — the old key is gone, the forbidden set names
#     it, and the guarded-put helper actually refuses it.
# ---------------------------------------------------------------------------
def test_r2_index_key_no_longer_exists() -> None:
    import scripts.build_prophet as build_prophet

    with pytest.raises(AttributeError):
        build_prophet.R2_INDEX_KEY  # noqa: B018 — the point IS the access


def test_forbidden_public_keys_names_the_full_plan_book() -> None:
    import scripts.build_prophet as build_prophet

    assert "prophet/index.json" in build_prophet.R2_PUBLIC_FORBIDDEN_KEYS
    assert build_prophet.R2_HEALTH_KEY == "prophet/health.json"
    assert build_prophet.R2_HEALTH_KEY not in build_prophet.R2_PUBLIC_FORBIDDEN_KEYS


def test_guarded_put_object_refuses_a_forbidden_key() -> None:
    import scripts.build_prophet as build_prophet

    class _ExplodingClient:
        """put_object must never even be CALLED for a forbidden key — a
        client that raises if reached proves the refusal happens before any
        network attempt, not merely that the call site returns an error."""

        def put_object(self, **kwargs):  # pragma: no cover - must not run
            raise AssertionError("put_object must not be called for a forbidden key")

    with pytest.raises(ValueError):
        build_prophet.guarded_put_object(
            _ExplodingClient(),
            bucket="mastermindx",
            key="prophet/index.json",
            Body=b"{}",
        )


def test_guarded_put_object_forwards_a_permitted_key() -> None:
    import scripts.build_prophet as build_prophet

    calls = []

    class _RecordingClient:
        def put_object(self, **kwargs):
            calls.append(kwargs)
            return {"ok": True}

    result = build_prophet.guarded_put_object(
        _RecordingClient(),
        bucket="mastermindx",
        key="prophet/health.json",
        Body=b"{}",
        ContentType="application/json",
    )
    assert result == {"ok": True}
    assert calls == [{
        "Bucket": "mastermindx",
        "Key": "prophet/health.json",
        "Body": b"{}",
        "ContentType": "application/json",
    }]


# ---------------------------------------------------------------------------
# (c) build_public_health_projection — a strict allowlist, proven against an
#     ADVERSARIAL index carrying every decision-bearing field name.
# ---------------------------------------------------------------------------
ALLOWED_HEALTH_KEYS = {
    "schema", "source_asof", "published_at", "checkpoint", "index_sha256", "note",
}

# Field names that must NEVER survive into the public projection, plus a
# canary secret string planted deep in plan-shaped content to prove the
# projection is built field-by-field and never dict-copies/spreads the index.
_FORBIDDEN_FIELD_NAMES = (
    "plans", "entry", "targets", "invalidation", "trigger", "thesis",
    "_priority_score",
)
_CANARY_SECRET = "SECRET-ALPHA-THESIS-DO-NOT-LEAK-3f9a"


def _adversarial_index() -> dict:
    return {
        "schema": "prophet.index/v1",
        "asof": "2026-08-21",
        "source_asof": "2026-08-20T00:00:00Z",
        "recorded_at": "2026-08-21",
        # top-level decision-bearing fields a lazy dict-copy would leak
        "entry": 12.34,
        "targets": [13.0, 14.0],
        "invalidation": 11.0,
        "trigger": "cross above 20dma",
        "thesis": _CANARY_SECRET,
        "_priority_score": 97,
        "plans": [
            {
                "id": "AAPL-BULL-20260820",
                "asset": "AAPL",
                "entry": 220.0,
                "targets": [230.0, 240.0],
                "invalidation": 210.0,
                "trigger": "breakout",
                "thesis": _CANARY_SECRET,
                "_priority_score": 88,
            },
        ],
    }


def test_health_projection_returns_exactly_the_six_allowlisted_keys() -> None:
    from scripts.build_prophet import build_public_health_projection

    result = build_public_health_projection(
        _adversarial_index(),
        checkpoint_sha="c0ffee" * 6 + "cafe",
        index_sha256="deadbeef" * 8,
        published_at="2026-08-21T04:00:00Z",
    )
    assert set(result.keys()) == ALLOWED_HEALTH_KEYS
    assert "plans" not in result
    assert result["source_asof"] == "2026-08-20"
    assert result["schema"] == "prophet.public_health/v1"


def test_health_projection_leaks_no_forbidden_field_name_or_canary_secret() -> None:
    from scripts.build_prophet import build_public_health_projection

    result = build_public_health_projection(
        _adversarial_index(),
        checkpoint_sha="c0ffee" * 6 + "cafe",
        index_sha256="deadbeef" * 8,
        published_at="2026-08-21T04:00:00Z",
    )
    dumped = json.dumps(result)
    assert _CANARY_SECRET not in dumped, "plan thesis content leaked into the public receipt"
    for forbidden in _FORBIDDEN_FIELD_NAMES:
        assert f'"{forbidden}"' not in dumped, (
            f"forbidden field name {forbidden!r} appears as a JSON key in the "
            "public health projection"
        )


def test_health_projection_is_never_built_by_dict_copy_or_spread() -> None:
    """A ``{**index}`` or ``dict(index)`` construction would pass the two
    tests above by luck whenever the adversarial fixture's extra keys happen
    not to collide — this proves the allowlist holds even when the index
    carries a field share the SAME NAME as an allowed key but a forbidden,
    decision-bearing value."""
    from scripts.build_prophet import build_public_health_projection

    index = _adversarial_index()
    # A dict-copy/spread bug would let this poisoned value win.
    index["note"] = _CANARY_SECRET
    index["schema"] = "prophet.index/v1"  # the real index schema, not the health one

    result = build_public_health_projection(
        index,
        checkpoint_sha="c0ffee" * 6 + "cafe",
        index_sha256="deadbeef" * 8,
        published_at="2026-08-21T04:00:00Z",
    )
    assert result["schema"] == "prophet.public_health/v1"
    assert result["note"] != _CANARY_SECRET
    assert _CANARY_SECRET not in result["note"]


# ---------------------------------------------------------------------------
# (d) repo-executable AST sweep (reviewer finding #2) — no file outside
#     scripts/build_prophet.py (and this test) may write the forbidden
#     literal key to R2, regardless of how the call wraps across lines.
# ---------------------------------------------------------------------------
_SWEEP_DIRS = ("scripts", "engine", "app", "admin", "tools")


def _swept_python_files() -> list[Path]:
    """Every *.py under _SWEEP_DIRS, skipping any dir not checked out in a
    sparse worktree (admin/ and tools/ are commonly omitted — see
    scripts/worktree_sparse.py) and the exempt paths."""
    paths: list[Path] = []
    for dirname in _SWEEP_DIRS:
        base = ROOT / dirname
        if not base.is_dir():
            continue
        for hit in base.rglob("*.py"):
            p = hit.resolve()
            if p not in _EXEMPT_FROM_LITERAL_SWEEP:
                paths.append(p)
    assert paths, "the repo-executable AST sweep matched nothing — check _SWEEP_DIRS/ROOT"
    return paths


def test_no_repo_executable_outside_build_prophet_writes_the_forbidden_key() -> None:
    offenders = []
    for path in _swept_python_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for hit in find_forbidden_key_writes(text):
            rel = path.relative_to(ROOT)
            offenders.append(f"{rel}:{hit}")
    assert not offenders, (
        "a repo executable outside scripts/build_prophet.py writes the "
        f"forbidden public key {FORBIDDEN_KEY!r} to R2 (AST-detected, "
        "line-break-insensitive) — DEC:B1-PROPHET-PUBLIC-SPLIT closure "
        "regressed: " + "; ".join(offenders)
    )


def test_sweep_exemption_is_named_precisely() -> None:
    """Pins the exemption list itself — a future edit that widens it silently
    (e.g. exempting a whole directory) should fail review, not just tests."""
    assert _EXEMPT_FROM_LITERAL_SWEEP == {
        (ROOT / "scripts" / "build_prophet.py").resolve(),
        Path(__file__).resolve(),
    }
