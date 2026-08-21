"""Boundary tests for DEC:B1-PROPHET-PUBLIC-SPLIT.

The full US Prophet plan book (site/prophet/index.json — 262+ plans with
entries/targets/invalidations/theses) must never be reachable from public R2
again: the origin 401s the path (premium/private), but public R2 answered it
anonymously.  Sol's closure ruling makes the producer structurally closed —
this file pins that closure at the boundary, not the behavior underneath it.

Deterministic only: no subprocess, no network, no fixture repo.  Every test
here must also run in a sparse worktree (no site/ or data/ dependency).

Run: python3 -m pytest tests/test_prophet_r2_boundary.py -q
"""
from __future__ import annotations

import json
from glob import glob
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DAILY = ROOT / ".github" / "workflows" / "daily.yml"

FORBIDDEN_KEY = "prophet/index.json"
FORBIDDEN_KEY_QUOTED = f'"{FORBIDDEN_KEY}"'
_R2_WRITE_MARKERS = ("put_object", "upload_file", "upload_fileobj")

_THIS_FILE = Path(__file__).resolve()
_EXEMPT_FROM_LITERAL_SWEEP = {
    (ROOT / "scripts" / "build_prophet.py").resolve(),
    _THIS_FILE,
}


# ---------------------------------------------------------------------------
# (a) daily.yml as TEXT — the publisher step publishes the health receipt,
#     and the forbidden key literal never pairs with an R2-write construct
#     anywhere in the file (the tombstone's head_object/delete_object block
#     and comments are the only permitted occurrences).
# ---------------------------------------------------------------------------
def _daily_text() -> str:
    return DAILY.read_text(encoding="utf-8")


def _publisher_step_text(daily_text: str) -> str:
    """The raw TEXT (comments included) of the R2 publisher step, sliced
    between its own `- name:` line and the next step's `- name:` line."""
    marker = "- name: publish Prophet public health receipt to R2"
    start = daily_text.index(marker)
    next_step = daily_text.index("\n      - name:", start + len(marker))
    return daily_text[start:next_step]


def test_publisher_step_publishes_the_health_receipt_key() -> None:
    step_text = _publisher_step_text(_daily_text())
    assert "prophet/health.json" in step_text
    assert "R2_HEALTH_KEY" in step_text
    assert "build_public_health_projection" in step_text


def test_forbidden_index_key_never_pairs_with_an_r2_write_construct() -> None:
    """A reintroduced ``put_object``/``upload_file``/``upload_fileobj`` call
    naming the forbidden key on the SAME LINE fails this test loudly — the
    only lines allowed to carry the literal are path references (git show,
    checkpoint manifest allowlist), the tombstone's head_object/delete_object
    calls, and comments/docstrings."""
    offenders = []
    for lineno, line in enumerate(_daily_text().splitlines(), start=1):
        if FORBIDDEN_KEY not in line:
            continue
        if any(marker in line for marker in _R2_WRITE_MARKERS):
            offenders.append(f"daily.yml:{lineno}: {line.strip()}")
    assert not offenders, (
        "a put/upload call references the forbidden public key "
        f"{FORBIDDEN_KEY!r} — DEC:B1-PROPHET-PUBLIC-SPLIT closure regressed: "
        + "; ".join(offenders)
    )


def test_the_tombstone_block_is_the_only_r2_read_write_of_the_forbidden_key() -> None:
    """Positive control for the assertion above: the tombstone's own
    head_object/delete_object calls DO carry the literal (via
    FORBIDDEN_INDEX_KEY), proving the negative assertion isn't vacuous."""
    step_text = _publisher_step_text(_daily_text())
    assert 'FORBIDDEN_INDEX_KEY = "prophet/index.json"' in step_text
    assert "client.head_object(Bucket=bucket, Key=FORBIDDEN_INDEX_KEY)" in step_text
    assert "client.delete_object(Bucket=bucket, Key=FORBIDDEN_INDEX_KEY)" in step_text


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
# (d) repo-executable sweep — no file outside scripts/build_prophet.py (and
#     this test) may reference the forbidden literal key in an R2-write
#     construct.
# ---------------------------------------------------------------------------
def _swept_files() -> list[Path]:
    patterns = ("scripts/*.py", "engine/**/*.py", "app/*.py")
    paths: list[Path] = []
    for pattern in patterns:
        for hit in glob(str(ROOT / pattern), recursive=True):
            p = Path(hit).resolve()
            if p not in _EXEMPT_FROM_LITERAL_SWEEP:
                paths.append(p)
    assert paths, "the repo-executable sweep matched nothing — the glob is broken"
    return paths


def test_no_repo_executable_outside_build_prophet_writes_the_forbidden_key() -> None:
    offenders = []
    for path in _swept_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if FORBIDDEN_KEY not in line:
                continue
            if any(marker in line for marker in _R2_WRITE_MARKERS):
                rel = path.relative_to(ROOT)
                offenders.append(f"{rel}:{lineno}: {line.strip()}")
    assert not offenders, (
        "a repo executable outside scripts/build_prophet.py writes the "
        f"forbidden public key {FORBIDDEN_KEY!r} to R2 — "
        "DEC:B1-PROPHET-PUBLIC-SPLIT closure regressed: " + "; ".join(offenders)
    )


def test_sweep_exemption_is_named_precisely() -> None:
    """Pins the exemption list itself — a future edit that widens it silently
    (e.g. exempting a whole directory) should fail review, not just tests."""
    assert _EXEMPT_FROM_LITERAL_SWEEP == {
        (ROOT / "scripts" / "build_prophet.py").resolve(),
        Path(__file__).resolve(),
    }
