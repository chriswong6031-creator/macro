"""Regression for the active-build map's nullable GitHub file-list boundary.

The September 6, 2026 nightly (run 33932499255, job 101406428605)
received ``{"files": null}`` from ``gh pr view``.  The generator must mark that
PR's collision evidence unknown without aborting the entire nightly map.
"""
from __future__ import annotations

from unittest import mock

from scripts import build_active_build_map


def test_collect_pr_files_treats_null_files_as_typed_error() -> None:
    """A nullable files field must degrade one PR, not crash the map."""
    response = {"files": None, "mergeStateStatus": "UNKNOWN"}

    with mock.patch.object(build_active_build_map, "_run_gh", return_value=response):
        result = build_active_build_map._collect_pr_files(123)

    assert result == ([], False, True, "UNKNOWN")
