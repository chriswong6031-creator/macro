"""Hermetic tests for the independent BioCatalyst browser verifier.

No test here opens a browser, a socket, or a file outside ``tmp_path``. The page
driver is an injected fake, exactly the way ``test_biocatalyst_clinicaltrials_discovery``
injects a scripted transport. What is under test is the verifier's *judgement*: which
observations it calls a pass, and -- more importantly -- which it refuses to.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
VERIFIER_PATH = ROOT / "scripts" / "biocatalyst_browser_verifier.py"


def _load_verifier():
    spec = importlib.util.spec_from_file_location("biocatalyst_browser_verifier_under_test", VERIFIER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # ``dataclasses`` resolves ``cls.__module__`` through ``sys.modules``; a file-loaded
    # module that is not registered there raises on the first ``@dataclass``.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


bv = _load_verifier()


STATE_CODES = (
    "catalyst_radar", "explorer_dense", "trial_peer_matrix", "company_partial",
    "asset_ambiguous_identity", "regulatory_mixed_sources", "change_tape_correction",
    "evidence_thread_expanded", "historical_mode", "source_outage", "locked", "empty",
)


class FrozenClock:
    """A deterministic stamp so a receipt digest is reproducible in a test."""

    def __init__(self) -> None:
        self._ticks = 0

    def __call__(self) -> str:
        self._ticks += 1
        return f"2026-08-06T00:00:{self._ticks:02d}Z"


def _good_observation(cell, **overrides: Any):
    if cell.language == "zh":
        payload: dict[str, Any] = {
            "decision_sentence": "去核对来源 — 完成日期本周改了两次",
            "tier1_strings": ("完成日期本周改了两次", "NCT01234567 · 2026-08-06 · v9", "来源 ClinicalTrials.gov"),
            "braid_marks": (
                bv.BraidMark(
                    mark_id="mark_1",
                    keyboard_reachable=True,
                    text_equivalent="生效 2026-07-30T00:00:00Z · 获知 2026-08-05T15:42:00Z",
                ),
            ),
        }
    else:
        payload = {
            "decision_sentence": "Check the source — the completion date moved twice this week.",
            "tier1_strings": ("The completion date moved twice this week.",),
            "braid_marks": (
                bv.BraidMark(
                    mark_id="mark_1",
                    keyboard_reachable=True,
                    text_equivalent="effective 2026-07-30T00:00:00Z, known at 2026-08-05T15:42:00Z",
                ),
            ),
        }
    payload.update(
        focus_observations=(
            bv.FocusObservation(selector="braid_mark_1", outline_style="solid", outline_width_px=2.0),
        ),
        hover_only_meaning_nodes=(),
        information_units_standard=("effective_clock", "known_at_clock", "reporting_lag"),
        information_units_reduced=("effective_clock", "known_at_clock", "reporting_lag"),
        screenshot_png=b"\x89PNG\r\n\x1a\n" + cell.cell_id.encode("utf-8"),
        dom_text=f"{cell.ui_state} {cell.theme} {cell.language}",
        computed_styles={"body.color": "rgb(16, 20, 24)"},
    )
    payload.update(overrides)
    return bv.CellObservation(cell_id=cell.cell_id, language=cell.language, **payload)


class FakeDriver:
    """A strict fake page driver. It observes; it never judges."""

    def __init__(self, builder=_good_observation) -> None:
        self._builder = builder
        self.visited: list[str] = []

    def capture(self, *, url: str, cell):
        self.visited.append(cell.cell_id)
        return self._builder(cell)


def _run(tmp_path: Path, driver: FakeDriver, cells=None):
    return bv.run_matrix(
        url="http://127.0.0.1:0/biocatalyst.html",
        cells=cells if cells is not None else bv.matrix_from_axes(STATE_CODES),
        driver=driver,
        output_dir=tmp_path / "artifacts",
        now_fn=FrozenClock(),
    )


def _receipt(run) -> dict[str, Any]:
    return json.loads(run.receipt_path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------------------
# CI safety: the verifier must be importable and testable with no browser present.
# --------------------------------------------------------------------------------------


def test_verifier_never_imports_a_browser_at_module_scope() -> None:
    tree = ast.parse(VERIFIER_PATH.read_text(encoding="utf-8"))
    top_level_imports: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            top_level_imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            top_level_imports.append(node.module)
    assert not any(name.split(".")[0] == "playwright" for name in top_level_imports)
    assert "playwright" in VERIFIER_PATH.read_text(encoding="utf-8"), "the lazy import must still exist"


def test_self_check_prints_owned_constants_without_a_browser(capsys: pytest.CaptureFixture[str]) -> None:
    assert bv.main(["--self-check"]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["required_checks"] == list(bv.REQUIRED_CHECKS)
    assert printed["gate_parameters"]["decision_sentence_max_words_en"] == 14
    assert printed["gate_parameters"]["decision_sentence_max_characters_zh"] == 24
    assert printed["verifier_module_sha256"] == hashlib.sha256(VERIFIER_PATH.read_bytes()).hexdigest()


def test_missing_browser_degrades_to_verifier_unavailable_never_to_a_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def _no_browser(*, headless: bool = True):
        raise bv.VerifierUnavailable("no chromium binary is installed")

    monkeypatch.setattr(bv, "playwright_page_driver", _no_browser)
    exit_code = bv.main(["--url", "http://127.0.0.1:0/x.html", "--output-dir", str(tmp_path / "artifacts")])
    assert exit_code == 4
    written = sorted((tmp_path / "artifacts").glob("*.json"))
    assert len(written) == 1
    receipt = json.loads(written[0].read_text(encoding="utf-8"))
    assert receipt["state"] == bv.RUN_STATE_UNAVAILABLE
    assert receipt["state"] != bv.RUN_STATE_PASSED
    assert receipt["cells"] == []
    assert receipt["failed_checks"] == list(bv.REQUIRED_CHECKS)
    assert "::warning title=biocatalyst-browser-verifier::" in capsys.readouterr().out


def test_unavailable_receipt_can_never_be_relabelled_as_a_pass(tmp_path: Path) -> None:
    payload = bv._receipt_payload(
        state=bv.RUN_STATE_PASSED,
        url="http://127.0.0.1:0/x.html",
        started_at="2026-08-06T00:00:01Z",
        completed_at="2026-08-06T00:00:02Z",
        cell_payloads=[],
        failed_checks=(),
        unavailable_reason="no chromium binary is installed",
    )
    assert payload["state"] == bv.RUN_STATE_FAILED


# --------------------------------------------------------------------------------------
# The matrix and the receipt digest.
# --------------------------------------------------------------------------------------


def test_matrix_is_the_frozen_twenty_four_cell_product_derived_here() -> None:
    cells = bv.matrix_from_axes(STATE_CODES)
    assert len(cells) == 24
    assert len({cell.cell_id for cell in cells}) == 24
    assert {(c.viewport_name, c.theme, c.language, c.motion) for c in cells} == {
        (viewport, theme, language, motion)
        for viewport in ("desktop", "tablet", "mobile")
        for theme in ("dark", "light")
        for language in ("en", "zh")
        for motion in ("standard", "reduced")
    }
    assert {cell.ui_state for cell in cells} == set(STATE_CODES)
    assert cells[0].cell_id == "d0b_desktop_dark_en_standard"
    with pytest.raises(ValueError):
        bv.matrix_from_axes(STATE_CODES[:11])


def test_receipt_digest_is_over_the_bytes_the_verifier_wrote(tmp_path: Path) -> None:
    run = _run(tmp_path, FakeDriver())
    assert run.state == bv.RUN_STATE_PASSED
    raw = run.receipt_path.read_bytes()
    assert run.receipt_sha256 == hashlib.sha256(raw).hexdigest()
    assert run.receipt_path.name == f"biocatalyst_browser_verification_{run.receipt_sha256[:24]}.json"
    receipt = json.loads(raw.decode("utf-8"))
    assert receipt["verifier_module_sha256"] == hashlib.sha256(VERIFIER_PATH.read_bytes()).hexdigest()
    assert receipt["non_authorizing"] is True
    assert receipt["authorizes"] == []
    assert [cell["cell"]["cell_id"] for cell in receipt["cells"]] == [c.cell_id for c in bv.matrix_from_axes(STATE_CODES)]
    assert all(len(cell["checks"]) == len(bv.REQUIRED_CHECKS) for cell in receipt["cells"])
    assert all(cell["observed"]["screenshot_sha256"] for cell in receipt["cells"])


# --------------------------------------------------------------------------------------
# A page it could not load can never produce a pass.
# --------------------------------------------------------------------------------------


def test_a_page_that_did_not_load_fails_every_check_and_the_run(tmp_path: Path) -> None:
    def _broken(cell):
        if cell.cell_id == "d0b_tablet_light_zh_reduced":
            return bv.CellObservation(cell_id=cell.cell_id, language=cell.language, loaded=False, load_error="HTTP 502")
        return _good_observation(cell)

    run = _run(tmp_path, FakeDriver(_broken))
    assert run.state == bv.RUN_STATE_FAILED
    receipt = _receipt(run)
    assert receipt["state"] == bv.RUN_STATE_FAILED
    broken = next(cell for cell in receipt["cells"] if cell["cell"]["cell_id"] == "d0b_tablet_light_zh_reduced")
    assert broken["observed"]["loaded"] is False
    assert [check["passed"] for check in broken["checks"]] == [False] * len(bv.REQUIRED_CHECKS)
    assert all("page not loaded: HTTP 502" in check["detail"] for check in broken["checks"])
    assert set(run.failed_checks) == set(bv.REQUIRED_CHECKS)


def test_a_driver_that_raises_is_recorded_as_unloaded_not_crashed(tmp_path: Path) -> None:
    def _raising(cell):
        if cell.cell_id == "d0b_mobile_dark_en_standard":
            raise RuntimeError("navigation timeout")
        return _good_observation(cell)

    run = _run(tmp_path, FakeDriver(_raising))
    assert run.state == bv.RUN_STATE_FAILED
    receipt = _receipt(run)
    failed = next(cell for cell in receipt["cells"] if cell["cell"]["cell_id"] == "d0b_mobile_dark_en_standard")
    assert failed["observed"]["loaded"] is False
    assert "RuntimeError: navigation timeout" in failed["observed"]["load_error"]


def test_a_driver_that_answers_for_the_wrong_cell_is_treated_as_unloaded(tmp_path: Path) -> None:
    cells = bv.matrix_from_axes(STATE_CODES)[:1]

    def _substituted(cell):
        other = bv.MatrixCell(
            cell_id="d0b_desktop_dark_zh_standard",
            viewport_name=cell.viewport_name,
            width=cell.width,
            height=cell.height,
            theme=cell.theme,
            language="zh",
            motion=cell.motion,
            ui_state=cell.ui_state,
        )
        return _good_observation(other)

    run = _run(tmp_path, FakeDriver(_substituted), cells=cells)
    assert run.state == bv.RUN_STATE_FAILED
    receipt = _receipt(run)
    assert receipt["cells"][0]["observed"]["load_error"] == "driver returned an observation for a different cell"


def test_receipt_state_refuses_a_pass_when_the_matrix_is_short() -> None:
    payload = [
        {
            "cell": {"cell_id": "d0b_desktop_dark_en_standard"},
            "observed": {"loaded": True},
            "checks": [{"name": name, "passed": True} for name in bv.REQUIRED_CHECKS],
        }
    ]
    assert bv._receipt_state(payload, ["d0b_desktop_dark_en_standard"]) == bv.RUN_STATE_PASSED
    assert bv._receipt_state(payload, ["d0b_desktop_dark_en_standard", "d0b_desktop_dark_en_reduced"]) == bv.RUN_STATE_FAILED
    assert bv._receipt_state([], []) == bv.RUN_STATE_FAILED


# --------------------------------------------------------------------------------------
# Ruling section 3.3 -- the bilingual gate.
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [
        "完成日期本周改了两次",
        "NCT01234567 · 2026-08-06 · v9",
        "来源 ClinicalTrials.gov",
        "FDA 已受理",
        "剂量 250 mg",
        "记录版本v9于2026-08-05T15:42:00Z获知",
    ],
)
def test_whitelisted_latin_runs_are_legal_in_a_zh_tier1_string(value: str) -> None:
    assert bv.zh_tier1_latin_violations(value) == ()


@pytest.mark.parametrize(
    ("value", "offender"),
    [
        ("状态 CHANGE TAPE CORRECTION", "CHANGE"),
        ("之前: Week 12 response", "Week"),
        ("Primary endpoint 主要终点", "Primary"),
        ("之前: Earlier value retained", "Earlier"),
    ],
)
def test_untranslated_english_in_a_zh_tier1_string_is_a_violation(value: str, offender: str) -> None:
    assert offender in bv.zh_tier1_latin_violations(value)


def test_bilingual_gate_fails_a_zh_cell_and_leaves_en_cells_alone(tmp_path: Path) -> None:
    def _english_shaped_zh(cell):
        if cell.language == "zh":
            return _good_observation(cell, tier1_strings=("状态 / CHANGE TAPE CORRECTION", "之前: 160 estimated"))
        return _good_observation(cell)

    run = _run(tmp_path, FakeDriver(_english_shaped_zh))
    assert run.state == bv.RUN_STATE_FAILED
    receipt = _receipt(run)
    zh_cells = [cell for cell in receipt["cells"] if cell["cell"]["language"] == "zh"]
    en_cells = [cell for cell in receipt["cells"] if cell["cell"]["language"] == "en"]
    assert zh_cells and en_cells
    for cell in zh_cells:
        gate = next(check for check in cell["checks"] if check["name"] == "bilingual_gate")
        assert gate["passed"] is False
    for cell in en_cells:
        gate = next(check for check in cell["checks"] if check["name"] == "bilingual_gate")
        assert gate["passed"] is True


def test_a_zh_cell_with_no_tier1_strings_cannot_pass_the_bilingual_gate() -> None:
    cell = bv.matrix_from_axes(STATE_CODES)[2]
    assert cell.language == "zh"
    observation = _good_observation(cell, tier1_strings=())
    gate = next(check for check in bv.evaluate_cell(observation) if check.name == "bilingual_gate")
    assert gate.passed is False


# --------------------------------------------------------------------------------------
# Ruling section 3.1 -- the Decision Sentence.
# --------------------------------------------------------------------------------------


def _sentence_check(language: str, sentence: str | None):
    cell = next(c for c in bv.matrix_from_axes(STATE_CODES) if c.language == language)
    observation = _good_observation(cell, decision_sentence=sentence)
    return next(check for check in bv.evaluate_cell(observation) if check.name == "decision_sentence_budget")


def test_a_compliant_decision_sentence_passes_in_both_locales() -> None:
    assert _sentence_check("en", "Check the source — the completion date moved twice this week.").passed
    assert _sentence_check("zh", "去核对来源 — 完成日期本周改了两次").passed
    assert _sentence_check("en", "Nothing here — the registry has posted no record for this asset.").passed


@pytest.mark.parametrize(
    ("language", "sentence", "fragment"),
    [
        ("en", None, "no Decision Sentence"),
        ("en", "Check the source", "must be"),
        ("en", "Act now — the completion date moved twice this week.", "outside the research-stance vocabulary"),
        ("en", "Check the source — ", "no reason"),
        (
            "en",
            "Check the source — the source reported completion timing twice this week and again this morning.",
            "budget is 14",
        ),
        ("en", "Check the source — the signal moved twice this week.", "banned vocabulary"),
        ("en", "Check the source — the falsifier fired on this record.", "banned vocabulary"),
        ("en", "Check the source — change_tape_correction posted twice.", "banned vocabulary"),
        ("zh", "去核对来源 — 完成日期本周改了两次，登记方在今天早上又提交了一版新的记录", "budget is 24"),
        ("zh", "去核对来源 — 结论已证伪", "banned vocabulary"),
        ("zh", "立即行动 — 完成日期本周改了两次", "outside the research-stance vocabulary"),
    ],
)
def test_a_non_compliant_decision_sentence_fails_with_its_reason(language: str, sentence: str | None, fragment: str) -> None:
    result = _sentence_check(language, sentence)
    assert result.passed is False
    assert fragment in result.detail


def test_the_decision_sentence_budget_is_the_rulings_number() -> None:
    assert bv.DECISION_SENTENCE_MAX_WORDS_EN == 14
    assert bv.DECISION_SENTENCE_MAX_CHARACTERS_ZH == 24
    assert len(bv.RESEARCH_STANCES["en"]) == 6
    assert len(bv.RESEARCH_STANCES["zh"]) == 6


# --------------------------------------------------------------------------------------
# Ruling section 3.2 -- Temporal Braid accessibility.
# --------------------------------------------------------------------------------------


def _cell_check(name: str, language: str = "en", **overrides: Any):
    cell = next(c for c in bv.matrix_from_axes(STATE_CODES) if c.language == language)
    observation = _good_observation(cell, **overrides)
    return next(check for check in bv.evaluate_cell(observation) if check.name == name)


def test_a_braid_mark_must_be_keyboard_reachable_and_name_both_clocks() -> None:
    name = "temporal_braid_two_clock_text_equivalent"
    assert _cell_check(name).passed is True
    assert _cell_check(name, braid_marks=()).passed is False
    unreachable = (bv.BraidMark("mark_1", False, "effective 2026-07-30T00:00:00Z, known at 2026-08-05T15:42:00Z"),)
    assert "not keyboard reachable" in _cell_check(name, braid_marks=unreachable).detail
    one_clock = (bv.BraidMark("mark_1", True, "effective 2026-07-30T00:00:00Z"),)
    assert _cell_check(name, braid_marks=one_clock).passed is False
    no_times = (bv.BraidMark("mark_1", True, "effective and known at are shown"),)
    assert "does not carry both clock times" in _cell_check(name, braid_marks=no_times).detail


def test_hover_only_meaning_is_a_failure() -> None:
    assert _cell_check("no_hover_only_meaning").passed is True
    result = _cell_check("no_hover_only_meaning", hover_only_meaning_nodes=("reporting_lag_tooltip",))
    assert result.passed is False
    assert "reporting_lag_tooltip" in result.detail


def test_a_focusable_element_without_a_visible_indicator_fails() -> None:
    assert _cell_check("visible_keyboard_focus").passed is True
    assert _cell_check("visible_keyboard_focus", focus_observations=()).passed is False
    invisible = (bv.FocusObservation(selector="braid_mark_1", outline_style="none", outline_width_px=0.0, box_shadow="none"),)
    assert "no visible focus indicator" in _cell_check("visible_keyboard_focus", focus_observations=invisible).detail
    hairline = (bv.FocusObservation(selector="braid_mark_1", outline_style="solid", outline_width_px=0.4, box_shadow="none"),)
    assert _cell_check("visible_keyboard_focus", focus_observations=hairline).passed is False
    shadow_only = (bv.FocusObservation(selector="braid_mark_1", outline_style="none", box_shadow="0 0 0 2px rgb(255,255,255)"),)
    assert _cell_check("visible_keyboard_focus", focus_observations=shadow_only).passed is True


def test_information_that_exists_only_in_motion_fails_reduced_motion_parity() -> None:
    assert _cell_check("reduced_motion_information_parity").passed is True
    result = _cell_check(
        "reduced_motion_information_parity",
        information_units_standard=("effective_clock", "known_at_clock", "reporting_lag"),
        information_units_reduced=("effective_clock", "known_at_clock"),
    )
    assert result.passed is False
    assert "reporting_lag" in result.detail
    assert _cell_check(
        "reduced_motion_information_parity",
        information_units_standard=(),
        information_units_reduced=(),
    ).passed is False


def test_every_required_check_is_evaluated_for_every_cell() -> None:
    cell = bv.matrix_from_axes(STATE_CODES)[0]
    names = [check.name for check in bv.evaluate_cell(_good_observation(cell))]
    assert names == list(bv.REQUIRED_CHECKS)
    assert len(set(names)) == 6
