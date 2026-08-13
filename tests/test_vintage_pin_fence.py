"""Vintage-pin fence: tests must not equality-pin a live nightly store.

The three 2026-08-13 detonations (govrev ``assert 23 == 8``, options
``episodes.jsonl`` 384→1206 used as a closed replay, prophet open-keys
10→11) hostage every armed PR through merge-on-green.  This suite pins
the fence's detector, not the product heals — those stay on #5524.

Synthetic live-store path literals below are names fed to the scanner,
never opened.  # ci-trigger-closure: data
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from scripts.check_vintage_pin_fence import (
    BASELINE_FINGERPRINTS,
    LIVE_STORES,
    iter_test_files,
    main,
    scan_text,
)

ROOT = Path(__file__).resolve().parents[1]

# ci-trigger-closure: data — scanner fixtures, not inputs this suite opens
_GOVREV_LATEST = "data/government_revenue/latest.json"
_PLANS = "site/prophet/plans"


def test_selftest_catches_the_three_detonation_classes() -> None:
    assert main(["--selftest"]) == 0


def test_spine_parquet_len_pin_is_caught() -> None:
    source = '''
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
def test_pins_live_parquet_len():
    df = pd.read_parquet(ROOT / "data" / "spine" / "predictions.parquet")
    assert len(df) == 58
'''
    found = scan_text(source, rel="tests/test_spine_named_pin.py")
    assert any(
        f.kind == "eq-literal" and f.literal == "58" and f.store == "spine-predictions"
        for f in found
    ), found


def test_spine_default_root_reader_pin_is_caught() -> None:
    source = '''
from engine import altdata_signals as a
def test_convergence_tier_accrual_aware_basis():
    t = a.convergence_tier(["material_8k", "congress_buy"], trump=False)
    assert t["n_scored"] == 0
'''
    found = scan_text(source, rel="tests/test_spine_reader_pin.py")
    assert any(
        f.kind == "eq-literal" and f.literal == "0" and f.store == "spine-predictions"
        for f in found
    ), found


def test_cold_data_dir_fixture_is_legal() -> None:
    source = '''
import pytest
from lib import config
from engine import altdata_signals as a
@pytest.fixture()
def spine_root(tmp_path, monkeypatch):
    (tmp_path / "data").mkdir()
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path / "data")
    return tmp_path
def test_convergence_tier_accrual_aware_basis(spine_root):
    t = a.convergence_tier(["material_8k", "congress_buy"], trump=False)
    assert t["n_scored"] == 0
'''
    assert scan_text(source, rel="tests/test_spine_cold_ok.py") == []


def test_mutation_dropping_the_data_dir_bind_reds_the_cold_census() -> None:
    """The #5547 isolation is load-bearing: same pin without the bind must red."""
    source = '''
from engine import altdata_signals as a
def test_convergence_tier_accrual_aware_basis(spine_root):
    t = a.convergence_tier(["material_8k", "congress_buy"], trump=False)
    assert t["n_scored"] == 0
'''
    found = scan_text(source, rel="tests/test_spine_cold_mutated.py")
    assert any(f.literal == "0" and f.store == "spine-predictions" for f in found), found


def test_mutation_dropping_spine_from_live_stores_misses_the_parquet_pin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import scripts.check_vintage_pin_fence as fence

    monkeypatch.setattr(
        fence,
        "LIVE_STORES",
        tuple(row for row in fence.LIVE_STORES if row[1] != "spine-predictions"),
    )
    source = '''
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
def test_pins_live_parquet_len():
    df = pd.read_parquet(ROOT / "data" / "spine" / "predictions.parquet")
    assert len(df) == 58
'''
    found = fence.scan_text(source, rel="tests/test_spine_named_pin.py")
    assert not any(f.store == "spine-predictions" for f in found), found


def test_release_forecast_latest_pin_is_caught() -> None:
    source = '''
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
def test_live_latest_release_count():
    latest = json.loads((ROOT / "data/release_forecast/latest.json").read_text())
    assert len(latest["releases"]) == 12
'''
    found = scan_text(source, rel="tests/test_release_pin.py")
    assert any(
        f.kind == "eq-literal" and f.literal == "12" and f.store == "release-forecast"
        for f in found
    ), found


def test_inflation_truth_directory_pin_is_caught() -> None:
    source = '''
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
def test_live_cpi_truth_files():
    files = list((ROOT / "data/release_forecast/cpi_truth").glob("*.json"))
    assert len(files) == 4
'''
    found = scan_text(source, rel="tests/test_inflation_truth_pin.py")
    assert any(
        f.kind == "eq-literal" and f.literal == "4" and f.store == "inflation-truth"
        for f in found
    ), found


def test_live_stores_cover_the_post_5515_detonations() -> None:
    stores = {label: path for path, label in LIVE_STORES}
    assert stores["spine-predictions"] == "data/spine/predictions.parquet"
    assert stores["release-forecast"].startswith("data/release_forecast/")
    assert stores["inflation-truth"] == "data/release_forecast/cpi_truth"
    assert "data/vector/alerts.jsonl" in {path for path, _ in LIVE_STORES}
    assert "data/alerts/alerts_log.parquet" in {path for path, _ in LIVE_STORES}
    assert "data/cycle_ontology/tripwire_state.json" in {path for path, _ in LIVE_STORES}


def test_govrev_candidate_census_pin_is_caught() -> None:
    source = f'''
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
def test_current_source_truth_is_eight_candidates():
    latest = json.loads((ROOT / "{_GOVREV_LATEST}").read_text())
    queue = build_candidate_queue(latest)
    assert queue["counts"]["total"] == 8
'''
    found = scan_text(source, rel="tests/test_govrev_pin.py")
    assert any(
        f.kind == "eq-literal" and f.literal == "8" and f.store == "govrev-latest"
        for f in found
    ), found


def test_options_live_ledger_as_closed_replay_is_caught() -> None:
    source = f'''
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "options_signal_episode" / "episodes.jsonl"
def test_live_ledger_as_closed_replay():
    body = SOURCE.read_text()
    assert len(body.splitlines()) == 384
'''
    found = scan_text(source, rel="tests/test_options_pin.py")
    assert any(
        f.kind == "eq-literal" and f.literal == "384" and f.store == "options-episodes"
        for f in found
    ), found


def test_prefix_in_the_function_name_does_not_legalize_a_whole_ledger_pin() -> None:
    source = f'''
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "options_signal_episode" / "episodes.jsonl"
def test_frozen_owner_prefix_matches_the_reviewed_384_rows():
    body = SOURCE.read_text()
    assert len(body.splitlines()) == 384
'''
    found = scan_text(source, rel="tests/test_options_named_prefix.py")
    assert any(f.kind == "eq-literal" and f.literal == "384" for f in found), found


def test_prophet_open_keys_count_ratchet_is_caught() -> None:
    source = f'''
from pathlib import Path
_REPO = Path(__file__).resolve().parents[1]
REAL_PLANS_DIR = _REPO / "{_PLANS}"
_LEGACY_DOUBLED_KEYS = 10
def _open_keys():
    keys = {{}}
    for path in REAL_PLANS_DIR.glob("*.json"):
        keys.setdefault(path.stem, []).append(path)
    return keys
def test_the_legacy_duplicate_open_keys_do_not_grow():
    doubled = {{k: v for k, v in _open_keys().items() if len(v) > 1}}
    assert len(doubled) <= _LEGACY_DOUBLED_KEYS
    assert len(doubled) == 10
'''
    found = scan_text(source, rel="tests/test_prophet_pin.py")
    assert any(f.kind == "upper-bound-literal" and f.literal == "10" for f in found), found
    assert any(f.kind == "eq-literal" and f.literal == "10" for f in found), found


def test_watermarked_prefix_slice_is_legal() -> None:
    source = '''
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "options_signal_episode" / "episodes.jsonl"
ACTIVATION_PREFIX_ROWS = 384
def test_frozen_prefix():
    lines = SOURCE.read_text().splitlines()[:ACTIVATION_PREFIX_ROWS]
    assert len(lines) == ACTIVATION_PREFIX_ROWS
'''
    assert scan_text(source, rel="tests/test_options_prefix.py") == []


def test_census_derived_from_a_committed_receipt_is_legal() -> None:
    source = f'''
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
def canonical_candidate_census():
    return json.loads((ROOT / "research" / "govrev_receipt.json").read_text())["n"]
def test_derived_census():
    latest = json.loads((ROOT / "{_GOVREV_LATEST}").read_text())
    assert len(latest["candidates"]) == canonical_candidate_census()
'''
    assert scan_text(source, rel="tests/test_govrev_census.py") == []


def test_named_disclosure_set_is_legal() -> None:
    source = f'''
from pathlib import Path
_REPO = Path(__file__).resolve().parents[1]
REAL_PLANS_DIR = _REPO / "{_PLANS}"
DISCLOSED_DUPLICATE_KEYS = frozenset({{"FCX-BULL-20260731", "MDB-BULL-20260731"}})
def _open_keys():
    return {{p.stem: [p] for p in REAL_PLANS_DIR.glob("*.json")}}
def test_named_disclosure_set():
    doubled = {{k for k, v in _open_keys().items() if len(v) > 1}}
    assert doubled <= DISCLOSED_DUPLICATE_KEYS
'''
    assert scan_text(source, rel="tests/test_prophet_disclosure.py") == []


def test_a_floor_against_the_live_store_is_not_a_pin() -> None:
    source = f'''
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
def test_census_is_nonempty():
    latest = json.loads((ROOT / "{_GOVREV_LATEST}").read_text())
    assert len(latest["companies"]) >= 1
'''
    assert scan_text(source, rel="tests/test_govrev_floor.py") == []


def test_chained_floor_then_constant_eq_is_not_a_live_count_pin() -> None:
    source = '''
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "options_signal_episode" / "episodes.jsonl"
ACTIVATION_PREFIX_ROWS = 384
def test_live_is_at_least_the_frozen_prefix():
    live = SOURCE.read_text().splitlines()
    assert len(live) >= ACTIVATION_PREFIX_ROWS == 384
'''
    assert scan_text(source, rel="tests/test_options_floor_chain.py") == []


def test_one_test_reading_the_ledger_does_not_hostage_a_sibling_synthetic_count() -> None:
    source = '''
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "options_signal_episode" / "episodes.jsonl"
def test_reads_the_live_ledger():
    rows = SOURCE.read_text().splitlines()
    assert len(rows) == 384
def test_synthetic_pair_has_two_rows():
    rows = [{"id": 1}, {"id": 2}]
    assert len(rows) == 2
'''
    found = scan_text(source, rel="tests/test_options_isolate.py")
    assert any(f.literal == "384" for f in found), found
    assert not any(f.literal == "2" for f in found), found


def test_new_pin_reds_even_when_the_filename_already_has_a_baseline_row(
    tmp_path: Path,
) -> None:
    """Grandfathering is by fingerprint, never by filename."""
    tests_root = tmp_path / "tests"
    tests_root.mkdir()
    (tests_root / "test_government_revenue_candidates.py").write_text(
        f'''
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
def test_a_brand_new_pin():
    latest = json.loads((ROOT / "{_GOVREV_LATEST}").read_text())
    assert len(latest["companies"]) == 99
''',
        encoding="utf-8",
    )
    assert main(["--root", str(tmp_path)]) == 1


def test_watermarked_prefix_tree_is_green(tmp_path: Path) -> None:
    tests_root = tmp_path / "tests"
    tests_root.mkdir()
    (tests_root / "test_frozen_prefix.py").write_text(
        '''
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "options_signal_episode" / "episodes.jsonl"
ACTIVATION_PREFIX_ROWS = 384
def test_frozen_prefix():
    lines = SOURCE.read_text().splitlines()[:ACTIVATION_PREFIX_ROWS]
    assert len(lines) == ACTIVATION_PREFIX_ROWS
''',
        encoding="utf-8",
    )
    assert main(["--root", str(tmp_path)]) == 0


def test_live_tree_gate_is_baseline_gated_not_a_product_heal() -> None:
    """Existing detonations are shrink-only; the fence must not red this PR for them."""
    assert main([]) == 0
    assert BASELINE_FINGERPRINTS, "baseline must freeze the live detonations, not be empty"


def test_fingerprints_omit_line_numbers_so_a_shift_is_not_a_new_pin() -> None:
    for fp in BASELINE_FINGERPRINTS:
        rel, store, kind, literal, compact = fp.split("|", 4)
        assert rel.startswith("tests/")
        assert kind in {"eq-literal", "upper-bound-literal"}
        assert literal.isdigit()
        assert compact
        assert not compact[:8].isdigit()


def test_iter_test_files_rglobs_so_ci_scope_owns_tests() -> None:
    """The rglob is load-bearing: pack inference claims tests/**/*.py from it."""
    source = (ROOT / "scripts" / "check_vintage_pin_fence.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    rglobs = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "rglob"
    ]
    assert rglobs, "iter_test_files must rglob tests/test_*.py for CI scope inference"
    found = iter_test_files(ROOT)
    assert any(path.name == "test_vintage_pin_fence.py" for path in found)
