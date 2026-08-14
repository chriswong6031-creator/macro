"""PROBE B (2026-08-14 incident closure): a suite deliberately wired into no workflow.

This file exists to be REFUSED: ci-plan's unrun-audit preflight must red this
push in minutes, with zero packs launched — the defect class that took 67
minutes to surface on run 31763116872. It is reverted in the next commit.
"""


def test_probe_b_is_deliberately_unwired():
    assert True
