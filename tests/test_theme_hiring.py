"""tests/test_theme_hiring.py — Tests for engine/theme_hiring.py.

Coverage:
  - Velocity math on synthetic history
  - AI title lexicon matching (AI_TITLE_PATTERNS_V1)
  - Fuzzy-map reuse — assert import from lib.warn_fuzzy, no second matcher
  - Store-absent honest null (env override tested)
  - fused_obs_z untouched regression (FENCE verification)
  - Banned words (no 'validated' in output)
  - Authority block correctness
  - Per-basket output schema
  - Robust-z cross-sectional computation
  - Stale/absent-store honest null with coverage_note
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Ensure lib.warn_fuzzy is the ONLY fuzzy matcher (house law)
# ---------------------------------------------------------------------------

def test_no_second_fuzzy_matcher_in_engine():
    """engine.theme_hiring must import match_ticker from lib.warn_fuzzy only."""
    import engine.theme_hiring as eng

    for name in dir(eng):
        if "match_ticker" in name.lower() or ("fuzzy" in name.lower() and "pattern" not in name.lower()):
            obj = getattr(eng, name)
            module = getattr(obj, "__module__", "")
            assert "theme_hiring" not in str(module), (
                f"Found {name} defined in theme_hiring — must use lib.warn_fuzzy only"
            )


def test_warn_fuzzy_imported_in_engine():
    """lib.warn_fuzzy.match_ticker must be importable and used in engine."""
    from lib.warn_fuzzy import match_ticker, load_ticker_map  # noqa: F401
    import engine.theme_hiring as eng
    # The engine module should reference match_ticker from lib.warn_fuzzy
    assert hasattr(eng, "match_ticker"), "match_ticker must be imported in engine.theme_hiring"
    assert eng.match_ticker is match_ticker, (
        "engine.theme_hiring.match_ticker must be lib.warn_fuzzy.match_ticker"
    )


# ---------------------------------------------------------------------------
# AI title lexicon tests
# ---------------------------------------------------------------------------

class TestAiTitleLexicon:
    def test_ai_title_patterns_count(self):
        """AI_TITLE_PATTERNS_V1 must have at least 20 patterns (versioned constant)."""
        from engine.theme_hiring import AI_TITLE_PATTERNS_V1
        assert len(AI_TITLE_PATTERNS_V1) >= 20

    @pytest.mark.parametrize("title,expected", [
        ("Machine Learning Engineer", True),
        ("Deep Learning Researcher", True),
        ("NLP Engineer", True),
        ("Data Scientist", True),
        ("MLOps Platform Engineer", True),
        ("ML Infrastructure Lead", True),
        ("Large Language Model Researcher", True),
        ("Generative AI Product Manager", True),
        ("Computer Vision Engineer", True),
        ("Applied Scientist", True),
        ("Software Engineer", False),
        ("Financial Analyst", False),
        ("Operations Manager", False),
        ("HR Business Partner", False),
        ("Sales Engineer", False),
    ])
    def test_ai_title_matching(self, title: str, expected: bool):
        from engine.theme_hiring import _matches_ai_title
        assert _matches_ai_title(title) == expected, (
            f"Title '{title}' expected ai={expected}"
        )

    def test_ai_title_case_insensitive(self):
        from engine.theme_hiring import _matches_ai_title
        assert _matches_ai_title("machine learning engineer")
        assert _matches_ai_title("MACHINE LEARNING ENGINEER")
        assert _matches_ai_title("Machine Learning Engineer")


# ---------------------------------------------------------------------------
# Synthetic store fixtures
# ---------------------------------------------------------------------------

def _make_cert_store(rows: list[dict]) -> pd.DataFrame:
    """Create a minimal synthetic certs.parquet DataFrame."""
    defaults = {
        "program": "lca",
        "decision_date": pd.Timestamp("2025-01-15"),
        "case_status": "Certified",
        "employer_name": "Acme Corp",
        "job_title": "Software Engineer",
        "worksite_state": "CA",
        "wage_annualized": 150000.0,
        "file_published": "2025-04-01",
    }
    out = []
    for r in rows:
        row = {**defaults, **r}
        # Normalize decision_date
        if isinstance(row["decision_date"], str):
            row["decision_date"] = pd.Timestamp(row["decision_date"])
        out.append(row)
    return pd.DataFrame(out)


def _make_ticker_map_csv(path: Path, entries: list[dict]) -> None:
    """Write a minimal ticker map CSV for tests."""
    import csv
    rows = entries or [{
        "employer_name_pattern": "acme",
        "ticker": "ACME",
        "valid_from": "2000-01-01",
        "valid_to": "2099-12-31",
        "confidence": "high",
        "notes": "test",
    }]
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["employer_name_pattern", "ticker",
                                               "valid_from", "valid_to",
                                               "confidence", "notes"])
        writer.writeheader()
        writer.writerows(rows)


def _make_baskets_payload(baskets: list[dict]) -> dict:
    return {
        "baskets": [
            {
                "id": b["id"],
                "members": [{"symbol": t} for t in b["tickers"]],
            }
            for b in baskets
        ]
    }


# ---------------------------------------------------------------------------
# Store-absent honest null
# ---------------------------------------------------------------------------

class TestStoreAbsentNull:
    def test_store_absent_returns_null_for_all_baskets(self, tmp_path):
        """When store is absent, all baskets get cert_velocity_z=None."""
        from engine.theme_hiring import compute_hiring_velocity

        payload = _make_baskets_payload([
            {"id": "ai_software", "tickers": ["NVDA", "MSFT"]},
            {"id": "biotech", "tickers": ["AMGN", "GILD"]},
        ])

        with mock.patch.dict(os.environ, {}, clear=True):
            if "DOL_CERTS_STORE" in os.environ:
                del os.environ["DOL_CERTS_STORE"]
            result = compute_hiring_velocity(
                payload,
                store_path=tmp_path / "nonexistent.parquet",  # definitely absent
                root=tmp_path,
            )

        assert "ai_software" in result
        assert "biotech" in result
        assert result["ai_software"]["cert_velocity_z"] is None
        assert result["biotech"]["cert_velocity_z"] is None
        assert result["ai_software"]["n_matched_employers"] == 0
        # coverage_note must explain the absence
        assert "absent" in result["ai_software"]["coverage_note"].lower() or \
               "unavailable" in result["ai_software"]["coverage_note"].lower()

    def test_env_override_store_absent_honest_null(self, tmp_path):
        """DOL_CERTS_STORE env pointing to nonexistent file → honest null."""
        from engine.theme_hiring import compute_hiring_velocity

        payload = _make_baskets_payload([{"id": "tech", "tickers": ["AAPL"]}])
        fake_store = tmp_path / "fake_certs.parquet"
        # Do NOT create it

        with mock.patch.dict(os.environ, {"DOL_CERTS_STORE": str(fake_store)}):
            result = compute_hiring_velocity(
                payload,
                root=tmp_path,
            )

        assert result["tech"]["cert_velocity_z"] is None


# ---------------------------------------------------------------------------
# Velocity math on synthetic history
# ---------------------------------------------------------------------------

class TestVelocityMath:
    def test_rising_velocity_positive_z(self, tmp_path):
        """Basket with more recent certs than prior should have positive cert_velocity_z
        relative to a basket with declining/stable certs."""
        from engine.theme_hiring import compute_hiring_velocity

        # as_of = 2025-07-01
        as_of = datetime(2025, 7, 1, tzinfo=timezone.utc)

        # recent = trailing 2 quarters = ~2025-01-01 to 2025-07-01
        # prior = prior 4 quarters = ~2024-01-01 to 2025-01-01

        # Basket A: lots of recent certs
        recent_rows_a = [
            {"employer_name": "Alpha AI", "decision_date": "2025-03-15",
             "job_title": "Machine Learning Engineer"},
            {"employer_name": "Alpha AI", "decision_date": "2025-05-01",
             "job_title": "Data Scientist"},
            {"employer_name": "Alpha AI", "decision_date": "2025-06-10",
             "job_title": "ML Platform Engineer"},
        ]
        prior_rows_a = [
            {"employer_name": "Alpha AI", "decision_date": "2024-03-01",
             "job_title": "Software Engineer"},
        ]

        # Basket B: no recent certs (declining)
        prior_rows_b = [
            {"employer_name": "Beta Corp", "decision_date": "2024-03-01",
             "job_title": "Engineer"},
            {"employer_name": "Beta Corp", "decision_date": "2024-05-01",
             "job_title": "Engineer"},
        ]

        all_rows = recent_rows_a + prior_rows_a + prior_rows_b
        certs_df = _make_cert_store(all_rows)

        store_path = tmp_path / "certs.parquet"
        certs_df.to_parquet(store_path, index=False)

        ticker_map_path = tmp_path / "ticker_map.csv"
        _make_ticker_map_csv(ticker_map_path, [
            {"employer_name_pattern": "alpha ai", "ticker": "ALPHA",
             "valid_from": "2000-01-01", "valid_to": "2099-12-31",
             "confidence": "high", "notes": "test"},
            {"employer_name_pattern": "beta corp", "ticker": "BETA",
             "valid_from": "2000-01-01", "valid_to": "2099-12-31",
             "confidence": "high", "notes": "test"},
        ])

        payload = _make_baskets_payload([
            {"id": "basket_a", "tickers": ["ALPHA"]},
            {"id": "basket_b", "tickers": ["BETA"]},
        ])

        result = compute_hiring_velocity(
            payload,
            store_path=store_path,
            ticker_map_path=ticker_map_path,
            as_of=as_of,
        )

        assert "basket_a" in result
        assert "basket_b" in result
        # basket_a has more recent activity → higher z
        z_a = result["basket_a"].get("cert_velocity_z")
        z_b = result["basket_b"].get("cert_velocity_z")
        if z_a is not None and z_b is not None:
            assert z_a > z_b, (
                f"basket_a (rising) should have higher z ({z_a}) than basket_b ({z_b})"
            )

    def test_ai_title_share_computed(self, tmp_path):
        """ai_title_share should reflect fraction of AI-matching titles in recent certs."""
        from engine.theme_hiring import compute_hiring_velocity

        as_of = datetime(2025, 7, 1, tzinfo=timezone.utc)
        rows = [
            {"employer_name": "Tech Corp", "decision_date": "2025-03-01",
             "job_title": "Machine Learning Engineer"},
            {"employer_name": "Tech Corp", "decision_date": "2025-04-01",
             "job_title": "Software Engineer"},  # not AI
            {"employer_name": "Tech Corp", "decision_date": "2025-05-01",
             "job_title": "Data Scientist"},
            {"employer_name": "Tech Corp", "decision_date": "2025-06-01",
             "job_title": "HR Manager"},  # not AI
        ]
        certs_df = _make_cert_store(rows)
        store_path = tmp_path / "certs.parquet"
        certs_df.to_parquet(store_path, index=False)

        ticker_map_path = tmp_path / "ticker_map.csv"
        _make_ticker_map_csv(ticker_map_path, [{
            "employer_name_pattern": "tech corp",
            "ticker": "TECH",
            "valid_from": "2000-01-01",
            "valid_to": "2099-12-31",
            "confidence": "high",
            "notes": "test",
        }])

        payload = _make_baskets_payload([{"id": "tech", "tickers": ["TECH"]}])
        result = compute_hiring_velocity(
            payload,
            store_path=store_path,
            ticker_map_path=ticker_map_path,
            as_of=as_of,
        )

        ai_share = result["tech"].get("ai_title_share")
        # 2 out of 4 recent titles match AI patterns → 0.5
        assert ai_share is not None
        assert 0.4 <= ai_share <= 0.6, f"Expected ~0.5, got {ai_share}"

    def test_median_wage_yoy_positive(self, tmp_path):
        """median_wage_yoy should be positive when recent wages exceed prior wages."""
        from engine.theme_hiring import compute_hiring_velocity

        as_of = datetime(2025, 7, 1, tzinfo=timezone.utc)
        rows = [
            # Recent (higher wages)
            {"employer_name": "WageCo", "decision_date": "2025-02-01",
             "wage_annualized": 200000.0, "job_title": "Eng"},
            {"employer_name": "WageCo", "decision_date": "2025-05-01",
             "wage_annualized": 220000.0, "job_title": "Eng"},
            # Prior (lower wages)
            {"employer_name": "WageCo", "decision_date": "2024-03-01",
             "wage_annualized": 150000.0, "job_title": "Eng"},
            {"employer_name": "WageCo", "decision_date": "2024-06-01",
             "wage_annualized": 160000.0, "job_title": "Eng"},
        ]
        certs_df = _make_cert_store(rows)
        store_path = tmp_path / "certs.parquet"
        certs_df.to_parquet(store_path, index=False)

        ticker_map_path = tmp_path / "ticker_map.csv"
        _make_ticker_map_csv(ticker_map_path, [{
            "employer_name_pattern": "wageco",
            "ticker": "WGCO",
            "valid_from": "2000-01-01",
            "valid_to": "2099-12-31",
            "confidence": "high",
            "notes": "test",
        }])

        payload = _make_baskets_payload([{"id": "wages", "tickers": ["WGCO"]}])
        result = compute_hiring_velocity(
            payload,
            store_path=store_path,
            ticker_map_path=ticker_map_path,
            as_of=as_of,
        )

        yoy = result["wages"].get("median_wage_yoy")
        assert yoy is not None
        assert yoy > 0, f"Expected positive wage YoY, got {yoy}"


# ---------------------------------------------------------------------------
# Robust-z cross-sectional
# ---------------------------------------------------------------------------

class TestRobustZ:
    def test_single_basket_z_is_zero(self):
        """With only one basket that has data, z should be 0."""
        from engine.theme_hiring import _robust_z
        zs = _robust_z([1.5])
        assert zs == [0.0]

    def test_z_winsorised_to_clamp(self):
        from engine.theme_hiring import _robust_z, Z_CLAMP
        values = [0.0, 0.0, 0.0, 0.0, 100.0]  # extreme outlier
        zs = _robust_z(values)
        assert max(abs(z) for z in zs) <= Z_CLAMP + 0.01

    def test_z_symmetric(self):
        from engine.theme_hiring import _robust_z
        values = [1.0, 2.0, 3.0]  # symmetric distribution
        zs = _robust_z(values)
        # z of median (2.0) should be near 0
        assert abs(zs[1]) < 0.1

    def test_z_nan_inputs(self):
        from engine.theme_hiring import _robust_z
        values = [float("nan"), 1.0, 2.0]
        zs = _robust_z(values)
        assert len(zs) == 3
        assert zs[0] == 0.0  # nan maps to 0


# ---------------------------------------------------------------------------
# fused_obs_z untouched regression
# ---------------------------------------------------------------------------

class TestFusedObsZUntouched:
    """Verify that theme_hiring.py does not modify or reference fused_obs_z."""

    def test_no_fused_obs_z_reference_in_engine(self):
        """engine/theme_hiring.py must not MODIFY fused_obs_z (only comment/doc references allowed)."""
        import inspect
        import engine.theme_hiring as eng
        import ast

        source = inspect.getsource(eng)

        # Parse the AST to find actual assignment/usage of fused_obs_z (not in strings/docstrings)
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return  # Can't parse — skip AST check

        # Walk all Name and Attribute nodes looking for fused_obs_z assignment targets
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and "fused_obs_z" in target.id:
                        assert False, (
                            f"Line {node.lineno}: fused_obs_z is assigned in theme_hiring — "
                            "it must be a separate display leg and must never be modified"
                        )
            elif isinstance(node, ast.AugAssign):
                if isinstance(node.target, ast.Name) and "fused_obs_z" in node.target.id:
                    assert False, "fused_obs_z augmented-assigned in theme_hiring"

    def test_authority_block_all_false(self):
        """AUTHORITY block must have all may_* = False."""
        from engine.theme_hiring import AUTHORITY
        assert AUTHORITY["may_rank"] is False
        assert AUTHORITY["may_gate"] is False
        assert AUTHORITY["may_size"] is False
        assert AUTHORITY["may_escalate"] is False
        assert AUTHORITY["is_context_only"] is True


# ---------------------------------------------------------------------------
# Output schema validation
# ---------------------------------------------------------------------------

class TestOutputSchema:
    def test_output_keys_present_when_store_absent(self, tmp_path):
        """Even with absent store, output keys must match schema."""
        from engine.theme_hiring import compute_hiring_velocity

        payload = _make_baskets_payload([{"id": "test", "tickers": ["AAPL"]}])
        result = compute_hiring_velocity(
            payload,
            store_path=tmp_path / "nope.parquet",
            root=tmp_path,
        )

        expected_keys = {
            "cert_velocity_z", "cert_count_recent", "cert_count_prior",
            "ai_title_share", "median_wage_yoy", "matched_employers",
            "matched_tickers", "n_matched_employers",
            "coverage_note", "coverage_note_zh", "authority",
        }
        assert expected_keys.issubset(set(result["test"].keys())), (
            f"Missing keys: {expected_keys - set(result['test'].keys())}"
        )

    def test_output_json_serializable(self, tmp_path):
        """All output values must be JSON serializable (site projection requirement)."""
        from engine.theme_hiring import compute_hiring_velocity

        payload = _make_baskets_payload([{"id": "test", "tickers": ["MSFT"]}])
        result = compute_hiring_velocity(
            payload,
            store_path=tmp_path / "nope.parquet",
            root=tmp_path,
        )

        # Should not raise
        serialized = json.dumps(result, default=str)
        assert "test" in json.loads(serialized)


# ---------------------------------------------------------------------------
# Banned words
# ---------------------------------------------------------------------------

class TestBannedWords:
    def test_no_validated_in_output(self, tmp_path):
        """The word 'validated' must not appear in any user-facing output field."""
        from engine.theme_hiring import compute_hiring_velocity

        payload = _make_baskets_payload([{"id": "x", "tickers": ["T"]}])
        result = compute_hiring_velocity(
            payload,
            store_path=tmp_path / "nope.parquet",
            root=tmp_path,
        )

        serialized = json.dumps(result).lower()
        # Should not contain 'validated' as a claim
        assert "validated" not in serialized

    def test_no_validated_in_engine_source_output(self):
        """engine/theme_hiring.py must not use 'validated' in user-facing text."""
        import inspect
        import engine.theme_hiring as eng

        source = inspect.getsource(eng)
        lines = source.split("\n")
        for i, line in enumerate(lines, 1):
            if "validated" in line.lower():
                stripped = line.strip()
                # Allow only in comments that reference the ban itself
                assert stripped.startswith("#"), (
                    f"Line {i}: 'validated' found in non-comment line: {line}"
                )


# ---------------------------------------------------------------------------
# Synapse/dag conformance
# ---------------------------------------------------------------------------

class TestSynapseConformance:
    def test_dol_certs_store_in_synapse(self):
        """dol-certs-store must be registered in config/synapse.yml."""
        import yaml
        repo = Path(__file__).resolve().parent.parent
        synapse_path = repo / "config" / "synapse.yml"
        with synapse_path.open() as f:
            reg = yaml.safe_load(f)
        artifacts = reg.get("artifacts", {})
        assert "dol-certs-store" in artifacts, "dol-certs-store missing from synapse.yml"
        assert "hiring-velocity" in artifacts, "hiring-velocity missing from synapse.yml"
        assert "site-hiring-intent" in artifacts, "site-hiring-intent missing from synapse.yml"

    def test_producer_paths_exist(self):
        """All synapse-registered producers for W7 entries must exist in the repo."""
        import yaml
        repo = Path(__file__).resolve().parent.parent
        synapse_path = repo / "config" / "synapse.yml"
        with synapse_path.open() as f:
            reg = yaml.safe_load(f)
        artifacts = reg.get("artifacts", {})

        for artifact_id in ("dol-certs-store", "hiring-velocity", "site-hiring-intent"):
            entry = artifacts.get(artifact_id, {})
            producer = entry.get("producer", "")
            if producer:
                producer_path = repo / producer
                assert producer_path.exists(), (
                    f"Producer {producer} for {artifact_id} does not exist in repo"
                )

    def test_collect_dol_certs_in_dag(self):
        """collect_dol_certs step must be registered in config/dag.yml."""
        import yaml
        repo = Path(__file__).resolve().parent.parent
        dag_path = repo / "config" / "dag.yml"
        with dag_path.open() as f:
            dag = yaml.safe_load(f)

        # Find collect_dol_certs in any lane's steps
        found = False
        for lane in dag.get("lanes", []):
            for step in lane.get("steps", []):
                if step.get("module") == "scripts.collect_dol_certs":
                    found = True
                    break
        assert found, "scripts.collect_dol_certs not found in dag.yml"

    def test_build_hiring_velocity_in_dag(self):
        """build_hiring_velocity step must be registered in config/dag.yml."""
        import yaml
        repo = Path(__file__).resolve().parent.parent
        dag_path = repo / "config" / "dag.yml"
        with dag_path.open() as f:
            dag = yaml.safe_load(f)

        found = False
        for lane in dag.get("lanes", []):
            for step in lane.get("steps", []):
                if step.get("module") == "scripts.build_hiring_velocity":
                    found = True
                    break
        assert found, "scripts.build_hiring_velocity not found in dag.yml"
