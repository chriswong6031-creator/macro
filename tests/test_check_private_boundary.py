"""Tests for scripts/check_private_boundary.py.

Covers:
  1. Forbidden-key violations — each key class fires independently.
  2. Host-path violation (/Users/ and /home/).
  3. Dollar-amount violation.
  4. Secret env-var violation (MASTERMIND_<NAME>).
  5. Clean counts-only fixture passes with zero violations.
  6. mastermind_snapshot.json is exempt from key scan but not host-path scan.
  7. Data-governance and site/mastermind broad host-path scan (non-key-scan paths).
  8. Nested key violation (key nested inside a list/dict).
  9. Ignore-rail check: data/private/ and data/operator/ are gitignored.
 10. Selftest runner exits 0 (gate proves itself on planted violations).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Import the module under test
# ---------------------------------------------------------------------------
sys.path.insert(0, str(ROOT))
from scripts.check_private_boundary import (
    _scan_artifact,
    _check_ignore_rail,
    scan,
    _FORBIDDEN_KEYS,
)


# ---------------------------------------------------------------------------
# Helper: make JSON text from a dict
# ---------------------------------------------------------------------------
def _j(obj: dict) -> str:
    return json.dumps(obj)


# ---------------------------------------------------------------------------
# 1. Forbidden key violations
# ---------------------------------------------------------------------------
class TestForbiddenKeys:
    """Each forbidden key class must trigger a forbidden_key violation."""

    @pytest.mark.parametrize("key", sorted(_FORBIDDEN_KEYS))
    def test_each_forbidden_key_fires(self, key: str) -> None:
        text = _j({"schema": "test.v1", key: "somevalue", "run_count": 1})
        violations = _scan_artifact(
            "site/mastermind/nw_feedback.json", text, check_keys=True
        )
        key_violations = [v for v in violations if v["violation_type"] == "forbidden_key"]
        assert len(key_violations) >= 1, (
            f"Expected forbidden_key violation for key={key!r}, got none. "
            f"All violations: {violations}"
        )
        assert any(key.lower() in v["detail"].lower() for v in key_violations)

    def test_no_forbidden_key_violation_when_check_keys_false(self) -> None:
        """When check_keys=False (exempt artifact), key scan is skipped."""
        text = _j({"ticker": "AAPL", "weight": 0.15})
        violations = _scan_artifact(
            "site/mastermind/mastermind_snapshot.json", text, check_keys=False
        )
        key_violations = [v for v in violations if v["violation_type"] == "forbidden_key"]
        assert len(key_violations) == 0, (
            f"Key scan should be skipped when check_keys=False; got {key_violations}"
        )


# ---------------------------------------------------------------------------
# 2. Host-path violation
# ---------------------------------------------------------------------------
class TestHostPath:
    def test_users_path_in_value_fires(self) -> None:
        text = _j({
            "schema": "operator_grading.v1",
            "ledger_path": "/Users/chris/Documents/data/ledger.jsonl",
        })
        violations = _scan_artifact(
            "data/governance/operator_grading.json", text, check_keys=False
        )
        host_violations = [v for v in violations if v["violation_type"] == "host_path_in_value"]
        assert len(host_violations) >= 1, (
            f"Expected host_path_in_value for /Users/ path, got: {violations}"
        )

    def test_home_path_in_value_fires(self) -> None:
        text = _j({
            "schema": "operator_grading.v1",
            "ledger_path": "/home/ubuntu/data/ledger.jsonl",
        })
        violations = _scan_artifact(
            "data/governance/operator_grading.json", text, check_keys=False
        )
        host_violations = [v for v in violations if v["violation_type"] == "host_path_in_value"]
        assert len(host_violations) >= 1, (
            f"Expected host_path_in_value for /home/ path, got: {violations}"
        )

    def test_relative_path_no_violation(self) -> None:
        text = _j({
            "schema": "operator_grading.v1",
            "ledger_file": "action_ledger.jsonl",
        })
        violations = _scan_artifact(
            "data/governance/operator_grading.json", text, check_keys=False
        )
        host_violations = [v for v in violations if v["violation_type"] == "host_path_in_value"]
        assert len(host_violations) == 0, (
            f"Relative path should not trigger host_path violation; got: {host_violations}"
        )


# ---------------------------------------------------------------------------
# 3. Dollar-amount violation
# ---------------------------------------------------------------------------
class TestDollarAmount:
    def test_dollar_amount_fires(self) -> None:
        text = _j({
            "schema": "operator_exposure_summary.v1",
            "note": "Total NAV: $12,345 today",
        })
        violations = _scan_artifact(
            "data/governance/operator_exposure_summary.json", text, check_keys=False
        )
        dollar_violations = [v for v in violations if v["violation_type"] == "dollar_amount_in_value"]
        assert len(dollar_violations) >= 1, (
            f"Expected dollar_amount_in_value, got: {violations}"
        )

    def test_small_dollar_no_violation(self) -> None:
        """$12 (two digits) should not fire — the pattern requires 3+ digit/comma chars."""
        text = _j({"note": "Cost: $12 per unit"})
        violations = _scan_artifact(
            "data/governance/operator_exposure_summary.json", text, check_keys=False
        )
        dollar_violations = [v for v in violations if v["violation_type"] == "dollar_amount_in_value"]
        assert len(dollar_violations) == 0, (
            f"Short dollar string should not fire, got: {dollar_violations}"
        )


# ---------------------------------------------------------------------------
# 4. Secret env-var violation
# ---------------------------------------------------------------------------
class TestSecretEnvPattern:
    def test_mastermind_token_fires(self) -> None:
        text = _j({
            "schema": "grading_closure.v1",
            "debug": "MASTERMIND_TOKEN=abc123",
        })
        violations = _scan_artifact(
            "data/governance/grading_closure.json", text, check_keys=False
        )
        secret_violations = [v for v in violations if v["violation_type"] == "secret_env_pattern"]
        assert len(secret_violations) >= 1, (
            f"Expected secret_env_pattern, got: {violations}"
        )

    def test_mastermind_api_key_fires(self) -> None:
        text = _j({"key_hint": "MASTERMIND_API_KEY"})
        violations = _scan_artifact(
            "data/governance/grading_closure.json", text, check_keys=False
        )
        assert any(v["violation_type"] == "secret_env_pattern" for v in violations), (
            f"Expected secret_env_pattern for MASTERMIND_API_KEY, got: {violations}"
        )

    def test_non_mastermind_env_no_violation(self) -> None:
        text = _j({"note": "NW_FEEDBACK_SCHEMA=v1"})
        violations = _scan_artifact(
            "data/governance/grading_closure.json", text, check_keys=False
        )
        secret_violations = [v for v in violations if v["violation_type"] == "secret_env_pattern"]
        assert len(secret_violations) == 0, (
            f"Non-MASTERMIND env var should not fire, got: {secret_violations}"
        )


# ---------------------------------------------------------------------------
# 5. Clean counts-only fixture passes
# ---------------------------------------------------------------------------
class TestCleanFixture:
    def test_counts_only_fixture_no_violations(self) -> None:
        text = _j({
            "schema": "mastermind_nw_feedback.v1",
            "generated_at": "2026-07-06T12:00:00+00:00",
            "state": "present",
            "window_days": 30,
            "n_runs": 42,
            "n_context_present": 35,
            "n_context_absent": 7,
            "context_seen_rate": 0.833,
        })
        violations = scan(
            ROOT,
            extra_artifacts={"site/mastermind/nw_feedback.json": text},
            skip_ignore_rail=True,
        )
        assert len(violations) == 0, (
            f"Clean fixture should produce zero violations; got: {violations}"
        )

    def test_operator_grading_scrubbed_fixture_no_violations(self) -> None:
        """The ledger_file basename (not ledger_path) should pass clean."""
        text = _j({
            "schema": "operator_grading.v1",
            "harness_version": "v1",
            "state": "accruing",
            "ledger_file": "action_ledger.jsonl",
            "ledger_present": False,
            "n_actions_total": 0,
        })
        violations = scan(
            ROOT,
            extra_artifacts={"data/governance/operator_grading.json": text},
            skip_ignore_rail=True,
        )
        assert len(violations) == 0, (
            f"Scrubbed operator_grading fixture should pass; got: {violations}"
        )


# ---------------------------------------------------------------------------
# 6. mastermind_snapshot.json exemptions
# ---------------------------------------------------------------------------
class TestSnapshotExemption:
    def test_ticker_key_exempt_from_key_scan(self) -> None:
        """mastermind_snapshot.json may contain tickers (FB-R1); key scan skipped."""
        text = _j({
            "schema": "mastermind_snapshot.v1",
            "ticker": "NVDA",
            "weight": 0.15,
        })
        violations = scan(
            ROOT,
            extra_artifacts={"site/mastermind/mastermind_snapshot.json": text},
            skip_ignore_rail=True,
        )
        key_violations = [v for v in violations if v["violation_type"] == "forbidden_key"]
        assert len(key_violations) == 0, (
            f"mastermind_snapshot.json should be exempt from key scan; got: {key_violations}"
        )

    def test_host_path_not_exempt_in_snapshot(self) -> None:
        """mastermind_snapshot.json is NOT exempt from host-path scan."""
        text = _j({
            "schema": "mastermind_snapshot.v1",
            "debug_path": "/Users/chriswong/docs/run.log",
        })
        violations = scan(
            ROOT,
            extra_artifacts={"site/mastermind/mastermind_snapshot.json": text},
            skip_ignore_rail=True,
        )
        host_violations = [v for v in violations if v["violation_type"] == "host_path_in_value"]
        assert len(host_violations) >= 1, (
            f"Host path should be caught in mastermind_snapshot.json; got: {violations}"
        )


# ---------------------------------------------------------------------------
# 7. Broader host-path scan for governance/ and site/mastermind/
# ---------------------------------------------------------------------------
class TestBroadHostPathScan:
    def test_governance_json_host_path_caught(self) -> None:
        """data/governance/*.json outside the explicit key-scan list are host-path scanned."""
        text = _j({
            "schema": "some_artifact.v1",
            "config_path": "/Users/chris/config.json",
        })
        # Use a path not in the key-scan list to confirm broad scan coverage.
        violations = scan(
            ROOT,
            extra_artifacts={"data/governance/some_artifact.json": text},
            skip_ignore_rail=True,
        )
        host_violations = [v for v in violations if v["violation_type"] == "host_path_in_value"]
        assert len(host_violations) >= 1, (
            f"data/governance/*.json should be host-path scanned; got: {violations}"
        )


# ---------------------------------------------------------------------------
# 8. Nested key violation
# ---------------------------------------------------------------------------
class TestNestedKeyViolation:
    def test_nested_forbidden_key_fires(self) -> None:
        text = _j({
            "schema": "test.v1",
            "meta": {
                "positions": [
                    {"ticker": "MSFT", "shares": 100},
                ]
            },
        })
        violations = _scan_artifact(
            "site/mastermind/nw_feedback.json", text, check_keys=True
        )
        key_violations = [v for v in violations if v["violation_type"] == "forbidden_key"]
        keys_found = {v["json_path"].split(".")[-1].rstrip("]").lstrip("[") for v in key_violations}
        # Both 'ticker' and 'shares' should be caught
        assert "ticker" in keys_found or any("ticker" in jp for jp in [v["json_path"] for v in key_violations])
        assert "shares" in keys_found or any("shares" in jp for jp in [v["json_path"] for v in key_violations])


# ---------------------------------------------------------------------------
# 9. Ignore-rail check: data/private/ and data/operator/ must be gitignored
# ---------------------------------------------------------------------------
class TestIgnoreRail:
    def test_data_private_is_gitignored(self) -> None:
        """data/private/ must be gitignored so CI catches a missing rail."""
        try:
            result = subprocess.run(
                ["git", "check-ignore", "-q", "data/private/__probe__"],
                cwd=str(ROOT),
                capture_output=True,
            )
            assert result.returncode == 0, (
                "data/private/ is NOT gitignored. The nightly blanket 'git add data/' "
                "would stage raw feedback data. Add 'data/private/' to .gitignore (FB-R12)."
            )
        except FileNotFoundError:
            pytest.skip("git not available in this environment")

    def test_data_operator_is_gitignored(self) -> None:
        """data/operator/ must remain gitignored (existing rail must not regress)."""
        try:
            result = subprocess.run(
                ["git", "check-ignore", "-q", "data/operator/__probe__"],
                cwd=str(ROOT),
                capture_output=True,
            )
            assert result.returncode == 0, (
                "data/operator/ is NOT gitignored. This regresses the existing rail "
                "(NW Rails PR-8 / RUL-P10). Restore 'data/operator/' in .gitignore."
            )
        except FileNotFoundError:
            pytest.skip("git not available in this environment")

    def test_check_ignore_rail_returns_no_violations_for_this_repo(self) -> None:
        """_check_ignore_rail() must return no violations on the current repo."""
        violations = _check_ignore_rail(ROOT)
        missing_rail = [v for v in violations if v["violation_type"] == "missing_ignore_rail"]
        assert len(missing_rail) == 0, (
            f"Ignore-rail violations found: {missing_rail}"
        )


# ---------------------------------------------------------------------------
# 10. Selftest exits 0
# ---------------------------------------------------------------------------
class TestSelftest:
    def test_selftest_exits_zero(self) -> None:
        """The --selftest flag must exit 0 (all planted violations are caught)."""
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "check_private_boundary.py"), "--selftest"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"--selftest exited {result.returncode}.\nstdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
        assert "selftest PASSED" in result.stdout, (
            f"Expected 'selftest PASSED' in stdout.\nstdout:\n{result.stdout}"
        )

    def test_normal_run_exits_zero_on_fixed_repo(self) -> None:
        """Normal run (no --selftest) must exit 0 on the fixed repo."""
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "check_private_boundary.py")],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"Normal run exited {result.returncode}.\nstdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )


# ---------------------------------------------------------------------------
# 11. F2 — broader _FORBIDDEN_KEYS and id/uid-suffix pattern
# ---------------------------------------------------------------------------
class TestF2BroaderKeys:
    """F2: positions, fills, cost_basis, avg_price, entry_price, position_uids
    must all trigger forbidden_key.  count-keys must stay clean."""

    @pytest.mark.parametrize("key", [
        "positions", "fills", "cost_basis", "avg_price", "entry_price", "position_uids",
    ])
    def test_f2_new_direct_keys_fire(self, key: str) -> None:
        text = _j({"schema": "test.v1", key: "somevalue", "run_count": 1})
        violations = _scan_artifact(
            "data/governance/operator_grading.json", text, check_keys=True
        )
        key_violations = [v for v in violations if v["violation_type"] == "forbidden_key"]
        assert len(key_violations) >= 1, (
            f"Expected forbidden_key for key={key!r}; got none. violations={violations}"
        )

    @pytest.mark.parametrize("key", [
        "order_id", "order_ids", "order_uid", "order_uids",
        "fill_ids", "fill_uid", "fill_uids",
        "position_id", "position_ids",
        "decision_ids", "decision_uid",
        "rejection_id", "rejection_ids", "rejection_uid",
    ])
    def test_f2_id_uid_suffix_variants_fire(self, key: str) -> None:
        text = _j({"schema": "test.v1", key: "val-abc", "run_count": 1})
        violations = _scan_artifact(
            "data/governance/operator_grading.json", text, check_keys=True
        )
        key_violations = [v for v in violations if v["violation_type"] == "forbidden_key"]
        assert len(key_violations) >= 1, (
            f"Expected forbidden_key for id/uid-suffix key={key!r}; "
            f"got none. violations={violations}"
        )

    @pytest.mark.parametrize("key", [
        "n_tickers", "ticker_count", "shares_traded_total",
        "venue_count", "account_count", "fill_convention_split",
    ])
    def test_f2_count_keys_stay_clean(self, key: str) -> None:
        """Count-like keys must NOT trigger forbidden_key."""
        text = _j({"schema": "test.v1", key: 42, "run_count": 1})
        violations = _scan_artifact(
            "data/governance/operator_grading.json", text, check_keys=True
        )
        key_violations = [v for v in violations if v["violation_type"] == "forbidden_key"]
        assert len(key_violations) == 0, (
            f"Count-key {key!r} should not fire forbidden_key; "
            f"got violations: {key_violations}"
        )


# ---------------------------------------------------------------------------
# 12. F1b — end-to-end disk-traversal test via real scan(root)
# ---------------------------------------------------------------------------
class TestF1DiskTraversalE2E:
    """Proves scan(root) traverses the filesystem and applies the full suite
    of checks to every governance/*.json file, not just the old hard-coded 5.
    Also proves the snapshot exemption end-to-end on disk."""

    def test_e2e_evil_governance_file_all_four_violation_types(
        self, tmp_path: "Path"
    ) -> None:
        """Write a real-shaped violation file under data/governance/__evil__.json
        containing all four violation classes and assert all four are reported."""
        import json as _json
        from scripts.check_private_boundary import scan as _scan

        # Build a minimal repo tree under tmp_path
        (tmp_path / "data" / "governance").mkdir(parents=True)
        (tmp_path / "site" / "mastermind").mkdir(parents=True)

        evil = {
            "schema": "evil.v1",
            "ticker": "EVIL",                                 # forbidden_key
            "path": "/Users/attacker/data/ledger.jsonl",      # host_path_in_value
            "note": "budget $12,345 stolen",                  # dollar_amount_in_value
            "creds": "MASTERMIND_TOKEN=leaked",               # secret_env_pattern
        }
        evil_path = tmp_path / "data" / "governance" / "__evil__.json"
        evil_path.write_text(_json.dumps(evil), encoding="utf-8")

        violations = _scan(tmp_path, skip_ignore_rail=True)

        vtypes = {v["violation_type"] for v in violations}
        assert "forbidden_key" in vtypes, (
            f"forbidden_key not caught. violations={violations}"
        )
        assert "host_path_in_value" in vtypes, (
            f"host_path_in_value not caught. violations={violations}"
        )
        assert "dollar_amount_in_value" in vtypes, (
            f"dollar_amount_in_value not caught. violations={violations}"
        )
        assert "secret_env_pattern" in vtypes, (
            f"secret_env_pattern not caught. violations={violations}"
        )
        # scan must signal failure (violations non-empty)
        assert len(violations) > 0

    def test_e2e_snapshot_exemption_yields_only_host_path(
        self, tmp_path: "Path"
    ) -> None:
        """Same content at site/mastermind/mastermind_snapshot.json yields
        ONLY host_path violations (key/dollar/secret are exempt)."""
        import json as _json
        from scripts.check_private_boundary import scan as _scan

        (tmp_path / "data" / "governance").mkdir(parents=True)
        (tmp_path / "site" / "mastermind").mkdir(parents=True)

        # All four violation classes in the snapshot
        snap = {
            "schema": "mastermind_snapshot.v1",
            "ticker": "EVIL",                                  # would be forbidden_key but EXEMPT
            "path": "/Users/attacker/data/ledger.jsonl",       # host_path_in_value -- NOT exempt
            "note": "budget $12,345 stolen",                   # would be dollar_amount but EXEMPT
            "creds": "MASTERMIND_TOKEN=leaked",                # would be secret_env but EXEMPT
        }
        snap_path = tmp_path / "site" / "mastermind" / "mastermind_snapshot.json"
        snap_path.write_text(_json.dumps(snap), encoding="utf-8")

        violations = _scan(tmp_path, skip_ignore_rail=True)

        vtypes = {v["violation_type"] for v in violations}
        # Only host_path should fire
        assert "host_path_in_value" in vtypes, (
            f"host_path_in_value should be caught in snapshot; violations={violations}"
        )
        # These must NOT fire on the snapshot
        assert "forbidden_key" not in vtypes, (
            f"forbidden_key must be exempt in snapshot; violations={violations}"
        )
        assert "dollar_amount_in_value" not in vtypes, (
            f"dollar_amount_in_value must be exempt in snapshot; violations={violations}"
        )
        assert "secret_env_pattern" not in vtypes, (
            f"secret_env_pattern must be exempt in snapshot; violations={violations}"
        )
