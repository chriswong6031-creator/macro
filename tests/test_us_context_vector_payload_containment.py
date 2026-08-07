"""No entitlement-gated payload may reach the committed candidates store.

`data/us_prophet_rank/candidates/*.parquet` is tracked in a PUBLIC repository.
`engine.neuralweb.context_api.context_frame` flattens each Context Snapshot
dimension's whole ``value`` dict into columns with no allowlist, and
`engine.us_context_vector.context_dimension_frame` merges the result into the
row that gets committed. That pair put the compact Filing Forensics findings —
the same rows `/api/forensics/state` serves only behind `require_site_full_user`
— into a tracked parquet for 722 tickers, where `git clone` reads them.

Two guards here, and the second is the one that lasts:

1. the named paid columns are dropped at the committing seam; and
2. EVERY non-scalar column in the stamped frame is explicitly classified as
   either forbidden or reviewed. The flatten is generic, so without (2) the next
   dimension to grow a paid body leaks in exactly the way forensics did — the
   defect would recur under a different column name and this file would still
   pass.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytest.importorskip("pandas")
pytest.importorskip("pyarrow")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.us_context_vector import (  # noqa: E402
    STAMP_FORBIDDEN_COLUMNS,
    STAMP_REVIEWED_NONSCALAR_COLUMNS,
    context_dimension_frame,
)

ROOT = Path(__file__).resolve().parents[1]


def _is_nonscalar(value: object) -> bool:
    """True for a container-valued cell, however pandas materialised it.

    ``numpy.ndarray`` is the load-bearing member. A parquet round-trip turns a
    list column into an ndarray, NOT a list, so an ``isinstance(v, (list, dict))``
    predicate silently sees nothing on disk and the sweep below passes
    unconditionally — it would not even flag `spine__records`, which is on the
    reviewed list precisely because it IS non-scalar. In-memory frames keep
    their lists, so a test built only in memory never exposes the hole.
    """
    return isinstance(value, (list, dict, set, tuple, np.ndarray))


def _fake_context_frame(monkeypatch, columns: dict) -> None:
    """Stand in for context_api.context_frame with an exact column set."""
    import engine.us_context_vector as ucv

    class _FakeContextApi:
        @staticmethod
        def context_frame(tickers, date=None, root=None):
            del date, root
            rows = {"ticker": list(tickers), "date": ["2026-07-31"] * len(tickers)}
            for name, value in columns.items():
                rows[name] = [value] * len(tickers)
            return pd.DataFrame(rows)

    real_import = __import__

    def _fake_import(name, *args, **kwargs):
        if name == "engine.neuralweb":
            class _Mod:
                context_api = _FakeContextApi
            return _Mod
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", _fake_import)
    return ucv


def test_the_paid_forensics_body_is_dropped_at_the_committing_seam(monkeypatch) -> None:
    ucv = _fake_context_frame(
        monkeypatch,
        {
            "forensics__findings": [{"id": "x", "title": "PAID TITLE", "summary": "PAID SUMMARY"}],
            "forensics__disclosure_changes": [{"accession": "0000-00-000000"}],
            "forensics__action": "review_now",
            "forensics__latest_period": "FY2026Q2",
            "forensics__absent": False,
        },
    )
    frame = ucv.context_dimension_frame(["AAPL"], "2026-07-31")

    assert "forensics__findings" not in frame.columns
    assert "forensics__disclosure_changes" not in frame.columns
    rendered = frame.to_json()
    assert "PAID TITLE" not in rendered
    assert "PAID SUMMARY" not in rendered

    # The zero-authority telemetry survives: this must not become a blanket
    # "drop everything forensics", which would remove the seam's whole value.
    for kept in ("forensics__action", "forensics__latest_period", "forensics__absent"):
        assert kept in frame.columns


def test_every_forbidden_column_is_actually_dropped(monkeypatch) -> None:
    """Pins the drop to the declared set rather than to two hard-coded names."""
    ucv = _fake_context_frame(
        monkeypatch, {name: [{"leak": True}] for name in sorted(STAMP_FORBIDDEN_COLUMNS)}
    )
    frame = ucv.context_dimension_frame(["AAPL"], "2026-07-31")
    assert not (set(frame.columns) & STAMP_FORBIDDEN_COLUMNS)


def test_an_unclassified_payload_column_is_a_hard_failure(monkeypatch) -> None:
    """The durable guard: a NEW paid body must not ride in unclassified.

    This is what makes the fix survive. Dropping two names by hand protects
    against today's leak; the flatten in context_api is generic, so the next
    dimension to carry a payload would reproduce it under a different name.
    """
    ucv = _fake_context_frame(
        monkeypatch,
        {"somenewdim__records": [{"secret": "payload"}], "scalar__ok": "fine"},
    )
    frame = ucv.context_dimension_frame(["AAPL"], "2026-07-31")

    unclassified = []
    for column in frame.columns:
        series = frame[column].dropna()
        if not len(series):
            continue
        if _is_nonscalar(series.iloc[0]):
            if (
                column not in STAMP_FORBIDDEN_COLUMNS
                and column not in STAMP_REVIEWED_NONSCALAR_COLUMNS
            ):
                unclassified.append(column)

    assert unclassified == ["somenewdim__records"], (
        "the classification sweep must SEE an unclassified payload column; "
        f"got {unclassified}"
    )


def test_the_committed_store_is_swept_for_unclassified_payloads() -> None:
    """Every non-scalar column already on disk must be classified.

    Skips when the store is absent (thin CI lanes do not check out data/).
    This asserts CLASSIFICATION only — that no non-scalar column is unaccounted
    for. It deliberately does NOT assert absence, because a column named in
    STAMP_FORBIDDEN_COLUMNS counts as classified and would sail through:
    for as long as the payload sat in the part, this test passed WITH the leak
    on disk. ABSENCE is a separate, stronger guard —
    :func:`test_no_committed_parquet_carries_a_paid_payload_column` below.
    """
    store = ROOT / "data" / "us_prophet_rank" / "candidates"
    parts = sorted(store.glob("*.parquet")) if store.is_dir() else []
    if not parts:
        pytest.skip("candidates store not present in this checkout")

    unclassified: list[str] = []
    for part in parts:
        frame = pd.read_parquet(part)
        for column in frame.columns:
            series = frame[column].dropna()
            if not len(series):
                continue
            if _is_nonscalar(series.iloc[0]):
                if (
                    column not in STAMP_FORBIDDEN_COLUMNS
                    and column not in STAMP_REVIEWED_NONSCALAR_COLUMNS
                ):
                    unclassified.append(f"{part.name}:{column}")

    assert not unclassified, (
        "unclassified payload column(s) in the committed store — classify each as "
        "forbidden (paid body) or reviewed (deliberately carried) in "
        f"engine/us_context_vector.py: {sorted(set(unclassified))}"
    )


#: Payload FIELD suffixes, matched across every dimension prefix. The flatten in
#: context_api.context_frame is generic — ``f"{dim_name}__{k}"`` — so the same
#: paid body reaches a committed row under a new name the moment a different
#: dimension grows a ``findings`` or ``disclosure_changes`` key. Pinning the
#: suffix rather than the exact column is what makes this survive that rename;
#: pinning `forensics__findings` alone would let `earnings__findings` through.
PAID_PAYLOAD_SUFFIXES = ("__findings", "__disclosure_changes")


def _tracked_parquets() -> list[Path]:
    """Every parquet COMMITTED under data/, via git — not a filesystem glob.

    The contract is about what `git clone` hands a stranger, so the file list
    has to come from the index. A glob would also sweep untracked local scratch
    parquets and report a leak that was never published.
    """
    import subprocess

    try:
        out = subprocess.run(
            ["git", "ls-files", "-z", "data/"],
            cwd=ROOT, capture_output=True, text=True, timeout=120, check=True,
        ).stdout
    except Exception:  # noqa: BLE001 — no git / no checkout is a skip, not a red
        return []
    return [ROOT / p for p in out.split("\0") if p.endswith(".parquet")]


def test_no_committed_parquet_carries_a_paid_payload_column() -> None:
    """No tracked parquet under data/ may carry an entitlement-gated body.

    This is the durable half of the fix, and the one the seam allowlist cannot
    provide. `STAMP_FORBIDDEN_COLUMNS` stops the CURRENT writer; this stops the
    ARTIFACT, whatever wrote it. That distinction is load-bearing here, because
    `append_candidates` unions its schema with the prior part on purpose ("a
    column retired tonight is preserved for the nights that had it"), so closing
    the seam alone would have carried the 722 tickers' findings forward for the
    life of the store.

    Scans schemas only (~4s over ~14k files), so it never materialises a body it
    is asserting the absence of.
    """
    parquets = _tracked_parquets()
    if not parquets:
        pytest.skip("no tracked parquets under data/ in this checkout")

    import pyarrow.parquet as pq

    offenders: list[str] = []
    for path in parquets:
        if not path.exists():  # sparse/partial checkout
            continue
        try:
            names = pq.read_schema(path).names
        except Exception:  # noqa: BLE001 — an unreadable part is another test's problem
            continue
        rel = path.relative_to(ROOT).as_posix()
        offenders += [
            f"{rel}:{c}" for c in names
            if c.endswith(PAID_PAYLOAD_SUFFIXES) or c in STAMP_FORBIDDEN_COLUMNS
        ]

    assert not offenders, (
        "entitlement-gated payload is committed to a PUBLIC repository — "
        "`git clone` bypasses require_site_full_user entirely. Drop the column "
        "at the committing seam (engine/us_context_vector.context_dimension_frame) "
        "and purge it from the part:\n  " + "\n  ".join(sorted(offenders))
    )
