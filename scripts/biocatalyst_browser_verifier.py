"""Independent browser verifier for the BioCatalyst D0b acceptance matrix.

Why this module exists
----------------------
``tests/test_biocatalyst_d0a_design_contract.py`` proves that a fully materialized
D0a manifest -- real files, real hashes, every approval/performance/per-cell field
set to approved-and-passed, plus a well-formed fabricated measurement receipt --
still fails on exactly one code:
``product_acceptance.trusted_browser_verifier_unavailable``. No self-authored
artifact can clear it, because the check demands an observer whose trust does not
come from the document it is judging.

This module is that observer. Its trust properties, in order:

1. It owns the gate constants. The thresholds of the named design ruling
   (research/BIOCATALYST_D0A_DESIGN_ADJUDICATION_2026-08-06.md sections 3.1-3.3)
   are module constants here. A manifest never supplies them; the acceptance
   contract must *agree* with this module, not the other way round.
2. It computes its receipt over the bytes it observed, hashes its own source, and
   writes the receipt to a path it chooses. A manifest can only bind that path and
   digest afterwards -- it can never author them.
3. It cannot report a pass for a page it could not load. ``_receipt_state`` derives
   the run state from the observations alone, and an unloaded cell fails every check.
4. It never imports a browser at module import time. ``playwright`` is imported
   lazily inside ``playwright_page_driver``; when the browser binary is missing the
   run degrades to state ``verifier_unavailable`` and never to a pass.

Authority boundary: this verifier observes a rendered page. It originates no
probability, ranking, signal, score, sizing, or escalation, activates no source,
mutates no production pointer, and authorizes nothing.

Usage::

    python scripts/biocatalyst_browser_verifier.py --url http://127.0.0.1:8000/biocatalyst.html \\
        --output-dir mockups/refs/biocatalyst/d0b/artifacts
    python scripts/biocatalyst_browser_verifier.py --self-check   # constants only, no browser
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Callable, Mapping, Protocol, Sequence


VERIFIER_MODULE_REF = "scripts/biocatalyst_browser_verifier.py"
VERIFIER_VERSION = "1.0.0"
RECEIPT_ARTIFACT_ID = "biocatalyst_browser_verification_receipt.v1"
DESIGN_ADJUDICATION_REF = "research/BIOCATALYST_D0A_DESIGN_ADJUDICATION_2026-08-06.md"

# The six named checks the successor contract must require. This tuple is the
# authority: a manifest that lists a different set disagrees with its verifier.
REQUIRED_CHECKS: tuple[str, ...] = (
    "bilingual_gate",
    "decision_sentence_budget",
    "temporal_braid_two_clock_text_equivalent",
    "no_hover_only_meaning",
    "visible_keyboard_focus",
    "reduced_motion_information_parity",
)

# Ruling section 3.1 -- Decision Sentence budget.
DECISION_SENTENCE_SEPARATOR = "—"  # em dash
DECISION_SENTENCE_MAX_WORDS_EN = 14
DECISION_SENTENCE_MAX_CHARACTERS_ZH = 24

# Ruling section 2/D2 -- the only legal stance vocabulary.
RESEARCH_STANCES: Mapping[str, tuple[str, ...]] = {
    "en": (
        "Read the record",
        "Check the source",
        "Wait for the record",
        "Reconcile the conflict",
        "Treat as historical",
        "Nothing here",
    ),
    "zh": (
        "记录可直接看",
        "去核对来源",
        "等记录更新",
        "两处对不上",
        "这是当时的记录",
        "暂无内容",
    ),
}

# Ruling section 3.1 -- banned inside the Decision Sentence. The falsifier family is
# the operator ruling of 2026-07-27: tripwires keep evaluating in the background,
# but no refutation language is ever front-facing.
BANNED_DECISION_SENTENCE_TOKENS_EN: tuple[str, ...] = (
    "signal", "signals", "score", "scores", "scored", "rank", "ranks", "ranked",
    "ranking", "forecast", "forecasts", "probability", "odds", "buy", "sell",
    "hold", "overweight", "underweight", "target price", "position", "falsifier",
    "refuted", "refutation", "thesis refuted", "validated",
)
BANNED_DECISION_SENTENCE_SUBSTRINGS_ZH: tuple[str, ...] = (
    "证伪",      # falsified
    "信号",      # signal
    "评分",      # score
    "排名",      # rank
    "预测",      # forecast
    "概率",      # probability
    "买入",      # buy
    "卖出",      # sell
    "已验证",  # "validated"
)

# The 12 machine state codes are internal vocabulary; they may never surface in a
# Decision Sentence (ruling section 3.1, "never a state enum").
INTERNAL_STATE_CODES: tuple[str, ...] = (
    "catalyst_radar", "explorer_dense", "trial_peer_matrix", "company_partial",
    "asset_ambiguous_identity", "regulatory_mixed_sources", "change_tape_correction",
    "evidence_thread_expanded", "historical_mode", "source_outage", "locked", "empty",
)

# Ruling section 3.3 -- the only Latin-script runs allowed inside a ZH Tier-1 string.
ZH_TIER1_LATIN_WHITELIST: tuple[str, ...] = (
    "ClinicalTrials.gov",
    "FDA",
    "NCT########",
    "ISO-8601 date or time",
    "measurement unit token",
    "record version token",
)
# A ZH string welds Latin runs directly onto Han characters ("版本v9"), where \b does not
# fire: Han characters are word characters too. The boundaries below are therefore
# Latin/digit lookarounds, not \b, so a legal token stays legal next to Chinese text.
_L = r"(?<![A-Za-z0-9])"
_R = r"(?![A-Za-z0-9])"
_ZH_LATIN_ALLOWED_PATTERNS: tuple[str, ...] = (
    rf"{_L}ClinicalTrials\.gov{_R}",
    rf"{_L}FDA{_R}",
    rf"{_L}NCT[0-9]{{8}}{_R}",
    rf"{_L}[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}(?:T[0-9]{{2}}:[0-9]{{2}}(?::[0-9]{{2}})?Z?)?{_R}",
    rf"{_L}[0-9]+(?:\.[0-9]+)?\s?(?:mg|g|kg|mL|L|mm|ms|min|h|d|wk|mo|yr|%){_R}",
    rf"{_L}UTC{_R}",
    rf"{_L}v[0-9]+{_R}",
)
_ZH_LATIN_ALLOWED = re.compile("|".join(_ZH_LATIN_ALLOWED_PATTERNS))
_LATIN_RUN = re.compile(r"[A-Za-z]+")

# Ruling section 3.2 -- a braid mark's text equivalent must name both clocks.
TWO_CLOCK_LABELS: Mapping[str, tuple[str, ...]] = {
    "en": ("effective", "known at"),
    "zh": ("生效", "获知"),
}
_ISO_TIMESTAMP = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}(?:T[0-9]{2}:[0-9]{2}(?::[0-9]{2})?Z?)?")

VIEWPORTS: tuple[tuple[str, int, int], ...] = (
    ("desktop", 1440, 900),
    ("tablet", 820, 1180),
    ("mobile", 390, 844),
)
THEMES: tuple[str, ...] = ("dark", "light")
LANGUAGES: tuple[str, ...] = ("en", "zh")
MOTIONS: tuple[str, ...] = ("standard", "reduced")
MATRIX_CELL_ID_PREFIX = "d0b"

RUN_STATE_PASSED = "passed"
RUN_STATE_FAILED = "failed"
RUN_STATE_UNAVAILABLE = "verifier_unavailable"


class VerifierUnavailable(RuntimeError):
    """Raised when no real browser is reachable. Never downgraded to a pass."""


@dataclass(frozen=True)
class MatrixCell:
    """One frozen capture cell: axes plus the page state to set up."""

    cell_id: str
    viewport_name: str
    width: int
    height: int
    theme: str
    language: str
    motion: str
    ui_state: str

    def as_payload(self) -> dict[str, Any]:
        return {
            "cell_id": self.cell_id,
            "viewport": {"name": self.viewport_name, "width": self.width, "height": self.height},
            "theme": self.theme,
            "language": self.language,
            "motion": self.motion,
            "ui_state": self.ui_state,
        }


@dataclass(frozen=True)
class BraidMark:
    """One Temporal Braid mark as observed in the page."""

    mark_id: str
    keyboard_reachable: bool
    text_equivalent: str


@dataclass(frozen=True)
class FocusObservation:
    """The computed focus indicator of one keyboard-reachable element."""

    selector: str
    outline_style: str = "none"
    outline_width_px: float = 0.0
    box_shadow: str = "none"


@dataclass(frozen=True)
class CellObservation:
    """Exactly what the verifier saw in one cell. Checks read only this."""

    cell_id: str
    language: str
    loaded: bool = True
    load_error: str | None = None
    decision_sentence: str | None = None
    tier1_strings: tuple[str, ...] = ()
    braid_marks: tuple[BraidMark, ...] = ()
    focus_observations: tuple[FocusObservation, ...] = ()
    hover_only_meaning_nodes: tuple[str, ...] = ()
    information_units_standard: tuple[str, ...] = ()
    information_units_reduced: tuple[str, ...] = ()
    screenshot_png: bytes = b""
    dom_text: str = ""
    computed_styles: Mapping[str, str] = field(default_factory=dict)

    def observed_payload(self) -> dict[str, Any]:
        """The observation, minus raw screenshot bytes, as canonical JSON data."""

        return {
            "cell_id": self.cell_id,
            "language": self.language,
            "loaded": bool(self.loaded),
            "load_error": self.load_error,
            "decision_sentence": self.decision_sentence,
            "tier1_strings": list(self.tier1_strings),
            "braid_marks": [
                {
                    "mark_id": mark.mark_id,
                    "keyboard_reachable": bool(mark.keyboard_reachable),
                    "text_equivalent": mark.text_equivalent,
                }
                for mark in self.braid_marks
            ],
            "focus_observations": [
                {
                    "selector": focus.selector,
                    "outline_style": focus.outline_style,
                    "outline_width_px": float(focus.outline_width_px),
                    "box_shadow": focus.box_shadow,
                }
                for focus in self.focus_observations
            ],
            "hover_only_meaning_nodes": list(self.hover_only_meaning_nodes),
            "information_units_standard": sorted(set(self.information_units_standard)),
            "information_units_reduced": sorted(set(self.information_units_reduced)),
            "dom_text_sha256": _sha256_text(self.dom_text),
            "computed_styles": {str(key): str(value) for key, value in sorted(self.computed_styles.items())},
            "screenshot_sha256": hashlib.sha256(self.screenshot_png).hexdigest(),
        }


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class VerifierRun:
    """What a caller gets back. The digest is over the bytes actually written."""

    state: str
    receipt_path: Path | None
    receipt_sha256: str | None
    failed_checks: tuple[str, ...]
    unavailable_reason: str | None = None


class PageDriver(Protocol):
    """The injected observer seam. Tests supply a fake; production supplies playwright."""

    def capture(self, *, url: str, cell: MatrixCell) -> CellObservation:  # pragma: no cover - protocol
        ...


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def canonical_receipt_bytes(payload: Mapping[str, Any]) -> bytes:
    """Serialize a receipt deterministically. The digest is over exactly these bytes."""

    return (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2, separators=(",", ": "))
        + "\n"
    ).encode("utf-8")


def matrix_cell_id(viewport_name: str, theme: str, language: str, motion: str) -> str:
    return f"{MATRIX_CELL_ID_PREFIX}_{viewport_name}_{theme}_{language}_{motion}"


def matrix_from_axes(state_codes: Sequence[str]) -> tuple[MatrixCell, ...]:
    """Derive the frozen 3x2x2x2 matrix here, never from the document under review.

    ``state_codes`` must be the 12 required state codes. Each is assigned to exactly
    two cells in a fixed order, so the mapping is reproducible without a manifest.
    """

    codes = tuple(state_codes)
    if len(codes) != 12 or len(set(codes)) != 12:
        raise ValueError("the frozen matrix requires exactly 12 unique state codes")
    cells: list[MatrixCell] = []
    index = 0
    for viewport_name, width, height in VIEWPORTS:
        for theme in THEMES:
            for language in LANGUAGES:
                for motion in MOTIONS:
                    cells.append(
                        MatrixCell(
                            cell_id=matrix_cell_id(viewport_name, theme, language, motion),
                            viewport_name=viewport_name,
                            width=width,
                            height=height,
                            theme=theme,
                            language=language,
                            motion=motion,
                            ui_state=codes[index % 12],
                        )
                    )
                    index += 1
    return tuple(cells)


def zh_tier1_latin_violations(value: str) -> tuple[str, ...]:
    """Return the non-whitelisted Latin runs in one ZH Tier-1 string (ruling 3.3)."""

    residue = _ZH_LATIN_ALLOWED.sub(" ", value)
    return tuple(sorted(set(_LATIN_RUN.findall(residue))))


def _check_bilingual_gate(observation: CellObservation) -> CheckResult:
    name = "bilingual_gate"
    if observation.language != "zh":
        return CheckResult(name, True, "not a ZH locale cell; gate does not apply")
    if not observation.tier1_strings:
        return CheckResult(name, False, "ZH cell reported no Tier-1 strings to inspect")
    offenders: list[str] = []
    for value in observation.tier1_strings:
        violations = zh_tier1_latin_violations(value)
        if violations:
            offenders.append(f"{value!r}: {', '.join(violations)}")
    if offenders:
        return CheckResult(name, False, "non-whitelisted Latin run in ZH Tier-1 string: " + "; ".join(offenders))
    return CheckResult(name, True, f"{len(observation.tier1_strings)} ZH Tier-1 strings carry only whitelisted Latin runs")


def _decision_sentence_word_count(sentence: str, language: str) -> int:
    body = sentence.replace(DECISION_SENTENCE_SEPARATOR, " ")
    if language == "zh":
        return len("".join(body.split()))
    return len(body.split())


def _check_decision_sentence_budget(observation: CellObservation) -> CheckResult:
    name = "decision_sentence_budget"
    sentence = observation.decision_sentence
    if not isinstance(sentence, str) or not sentence.strip():
        return CheckResult(name, False, "no Decision Sentence rendered above the fold")
    language = observation.language
    if DECISION_SENTENCE_SEPARATOR not in sentence:
        return CheckResult(name, False, "Decision Sentence must be '<stance> — <one reason>'")
    stance, _, reason = sentence.partition(DECISION_SENTENCE_SEPARATOR)
    stance = stance.strip()
    reason = reason.strip()
    legal = RESEARCH_STANCES.get(language, ())
    if stance not in legal:
        return CheckResult(name, False, f"stance {stance!r} is outside the research-stance vocabulary")
    if not reason:
        return CheckResult(name, False, "Decision Sentence carries a stance with no reason")
    budget = DECISION_SENTENCE_MAX_CHARACTERS_ZH if language == "zh" else DECISION_SENTENCE_MAX_WORDS_EN
    measured = _decision_sentence_word_count(sentence, language)
    unit = "characters" if language == "zh" else "words"
    if measured > budget:
        return CheckResult(name, False, f"Decision Sentence is {measured} {unit}; budget is {budget}")
    lowered = sentence.lower()
    if language == "zh":
        hits = [token for token in BANNED_DECISION_SENTENCE_SUBSTRINGS_ZH if token in sentence]
    else:
        hits = [token for token in BANNED_DECISION_SENTENCE_TOKENS_EN if re.search(rf"(?<![a-z]){re.escape(token)}(?![a-z])", lowered)]
    hits.extend(code for code in INTERNAL_STATE_CODES if code in lowered)
    if hits:
        return CheckResult(name, False, "banned vocabulary in Decision Sentence: " + ", ".join(sorted(set(hits))))
    return CheckResult(name, True, f"{measured} {unit} within the {budget} budget, stance and reason legal")


def _check_temporal_braid(observation: CellObservation) -> CheckResult:
    name = "temporal_braid_two_clock_text_equivalent"
    marks = observation.braid_marks
    if not marks:
        return CheckResult(name, False, "no Temporal Braid mark was reachable in this cell")
    labels = TWO_CLOCK_LABELS.get(observation.language, ())
    if not labels:
        return CheckResult(name, False, f"no two-clock label set for locale {observation.language!r}")
    offenders: list[str] = []
    for mark in marks:
        if not mark.keyboard_reachable:
            offenders.append(f"{mark.mark_id}: not keyboard reachable")
            continue
        text = mark.text_equivalent or ""
        missing = [label for label in labels if label.lower() not in text.lower()]
        if missing:
            offenders.append(f"{mark.mark_id}: text equivalent omits {', '.join(missing)}")
        elif len(_ISO_TIMESTAMP.findall(text)) < 2:
            offenders.append(f"{mark.mark_id}: text equivalent does not carry both clock times")
    if offenders:
        return CheckResult(name, False, "; ".join(offenders))
    return CheckResult(name, True, f"{len(marks)} braid marks are keyboard reachable and name both clocks")


def _check_no_hover_only_meaning(observation: CellObservation) -> CheckResult:
    name = "no_hover_only_meaning"
    if observation.hover_only_meaning_nodes:
        return CheckResult(name, False, "meaning available only on hover: " + ", ".join(sorted(observation.hover_only_meaning_nodes)))
    return CheckResult(name, True, "no node carries meaning that exists only on hover")


def _check_visible_keyboard_focus(observation: CellObservation) -> CheckResult:
    name = "visible_keyboard_focus"
    focuses = observation.focus_observations
    if not focuses:
        return CheckResult(name, False, "no keyboard-focusable element was observed")
    offenders = [
        focus.selector
        for focus in focuses
        if not (
            (focus.outline_style not in ("", "none") and float(focus.outline_width_px) >= 1.0)
            or (focus.box_shadow not in ("", "none"))
        )
    ]
    if offenders:
        return CheckResult(name, False, "no visible focus indicator on: " + ", ".join(sorted(offenders)))
    return CheckResult(name, True, f"{len(focuses)} focusable elements paint a visible focus indicator")


def _check_reduced_motion_parity(observation: CellObservation) -> CheckResult:
    name = "reduced_motion_information_parity"
    standard = set(observation.information_units_standard)
    reduced = set(observation.information_units_reduced)
    if not standard:
        return CheckResult(name, False, "no information units were observed with motion enabled")
    lost = sorted(standard - reduced)
    if lost:
        return CheckResult(name, False, "information exists only in motion: " + ", ".join(lost))
    return CheckResult(name, True, f"all {len(standard)} information units survive reduced motion")


_CHECKS: Mapping[str, Callable[[CellObservation], CheckResult]] = {
    "bilingual_gate": _check_bilingual_gate,
    "decision_sentence_budget": _check_decision_sentence_budget,
    "temporal_braid_two_clock_text_equivalent": _check_temporal_braid,
    "no_hover_only_meaning": _check_no_hover_only_meaning,
    "visible_keyboard_focus": _check_visible_keyboard_focus,
    "reduced_motion_information_parity": _check_reduced_motion_parity,
}


def evaluate_cell(observation: CellObservation) -> tuple[CheckResult, ...]:
    """Run every required check. A cell that did not load fails all of them."""

    if not observation.loaded:
        reason = observation.load_error or "page did not load"
        return tuple(
            CheckResult(name, False, f"page not loaded: {reason}") for name in REQUIRED_CHECKS
        )
    return tuple(_CHECKS[name](observation) for name in REQUIRED_CHECKS)


def _receipt_state(cell_payloads: Sequence[Mapping[str, Any]], expected_cell_ids: Sequence[str]) -> str:
    """Derive the run state from observations only -- never from a caller's claim."""

    if not cell_payloads:
        return RUN_STATE_FAILED
    if [payload["cell"]["cell_id"] for payload in cell_payloads] != list(expected_cell_ids):
        return RUN_STATE_FAILED
    for payload in cell_payloads:
        if not payload["observed"]["loaded"]:
            return RUN_STATE_FAILED
        if not all(check["passed"] for check in payload["checks"]):
            return RUN_STATE_FAILED
        if len(payload["checks"]) != len(REQUIRED_CHECKS):
            return RUN_STATE_FAILED
    return RUN_STATE_PASSED


def module_source_sha256() -> str:
    """Hash this module's own committed bytes so the receipt names its producer."""

    return hashlib.sha256(Path(__file__).resolve().read_bytes()).hexdigest()


def _utc_now() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_matrix(
    *,
    url: str,
    cells: Sequence[MatrixCell],
    driver: PageDriver,
    output_dir: Path | str,
    now_fn: Callable[[], str] = _utc_now,
) -> VerifierRun:
    """Drive every cell, write the receipt this verifier authored, return its digest."""

    started_at = now_fn()
    expected_cell_ids = [cell.cell_id for cell in cells]
    cell_payloads: list[dict[str, Any]] = []
    for cell in cells:
        try:
            observation = driver.capture(url=url, cell=cell)
        except VerifierUnavailable:
            raise
        except Exception as exc:  # a hostile or broken page is an observation, not a crash
            observation = CellObservation(
                cell_id=cell.cell_id,
                language=cell.language,
                loaded=False,
                load_error=f"{type(exc).__name__}: {exc}",
            )
        if observation.cell_id != cell.cell_id:
            observation = CellObservation(
                cell_id=cell.cell_id,
                language=cell.language,
                loaded=False,
                load_error="driver returned an observation for a different cell",
            )
        checks = evaluate_cell(observation)
        cell_payloads.append(
            {
                "cell": cell.as_payload(),
                "observed": observation.observed_payload(),
                "checks": [
                    {"name": check.name, "passed": bool(check.passed), "detail": check.detail}
                    for check in checks
                ],
            }
        )

    state = _receipt_state(cell_payloads, expected_cell_ids)
    failed = tuple(
        sorted(
            {
                check["name"]
                for payload in cell_payloads
                for check in payload["checks"]
                if not check["passed"]
            }
        )
    )
    receipt = _receipt_payload(
        state=state,
        url=url,
        started_at=started_at,
        completed_at=now_fn(),
        cell_payloads=cell_payloads,
        failed_checks=failed,
        unavailable_reason=None,
    )
    path, digest = _write_receipt(receipt, output_dir)
    return VerifierRun(state=state, receipt_path=path, receipt_sha256=digest, failed_checks=failed)


def unavailable_run(*, url: str, reason: str, output_dir: Path | str, now_fn: Callable[[], str] = _utc_now) -> VerifierRun:
    """Record an honest 'no browser here' outcome. This is never a pass."""

    stamp = now_fn()
    receipt = _receipt_payload(
        state=RUN_STATE_UNAVAILABLE,
        url=url,
        started_at=stamp,
        completed_at=stamp,
        cell_payloads=[],
        failed_checks=REQUIRED_CHECKS,
        unavailable_reason=reason,
    )
    path, digest = _write_receipt(receipt, output_dir)
    return VerifierRun(
        state=RUN_STATE_UNAVAILABLE,
        receipt_path=path,
        receipt_sha256=digest,
        failed_checks=REQUIRED_CHECKS,
        unavailable_reason=reason,
    )


def _receipt_payload(
    *,
    state: str,
    url: str,
    started_at: str,
    completed_at: str,
    cell_payloads: Sequence[Mapping[str, Any]],
    failed_checks: Sequence[str],
    unavailable_reason: str | None,
) -> dict[str, Any]:
    if state == RUN_STATE_PASSED and (unavailable_reason is not None or not cell_payloads):
        # Defence in depth: a pass with no observations is a contradiction.
        state = RUN_STATE_FAILED
    return {
        "artifact": RECEIPT_ARTIFACT_ID,
        "verifier_module_ref": VERIFIER_MODULE_REF,
        "verifier_module_sha256": module_source_sha256(),
        "verifier_version": VERIFIER_VERSION,
        "design_adjudication_ref": DESIGN_ADJUDICATION_REF,
        "state": state,
        "page_url": url,
        "started_at": started_at,
        "completed_at": completed_at,
        "required_checks": list(REQUIRED_CHECKS),
        "gate_parameters": gate_parameters(),
        "cells": list(cell_payloads),
        "failed_checks": list(failed_checks),
        "unavailable_reason": unavailable_reason,
        "non_authorizing": True,
        "authorizes": [],
    }


def gate_parameters() -> dict[str, Any]:
    """The ruling's machine-checkable gate constants, owned here."""

    return {
        "decision_sentence_max_words_en": DECISION_SENTENCE_MAX_WORDS_EN,
        "decision_sentence_max_characters_zh": DECISION_SENTENCE_MAX_CHARACTERS_ZH,
        "decision_sentence_separator": DECISION_SENTENCE_SEPARATOR,
        "research_stances_en": list(RESEARCH_STANCES["en"]),
        "research_stances_zh": list(RESEARCH_STANCES["zh"]),
        "zh_tier1_latin_whitelist": list(ZH_TIER1_LATIN_WHITELIST),
        "two_clock_labels_en": list(TWO_CLOCK_LABELS["en"]),
        "two_clock_labels_zh": list(TWO_CLOCK_LABELS["zh"]),
    }


def _write_receipt(receipt: Mapping[str, Any], output_dir: Path | str) -> tuple[Path, str]:
    raw = canonical_receipt_bytes(receipt)
    digest = hashlib.sha256(raw).hexdigest()
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"biocatalyst_browser_verification_{digest[:24]}.json"
    path.write_bytes(raw)
    return path, digest


def playwright_page_driver(*, headless: bool = True) -> PageDriver:  # pragma: no cover - needs a browser
    """Build the real driver. Imported lazily; missing browser raises, never passes."""

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise VerifierUnavailable(f"playwright is not importable: {exc}") from exc

    try:
        manager = sync_playwright().start()
    except Exception as exc:
        raise VerifierUnavailable(f"playwright runtime is unavailable: {exc}") from exc
    try:
        browser = manager.chromium.launch(headless=headless)
    except Exception as exc:
        manager.stop()
        raise VerifierUnavailable(f"no chromium binary is installed: {exc}") from exc
    return _PlaywrightDriver(manager, browser)


class _PlaywrightDriver:  # pragma: no cover - needs a browser
    """Thin adapter. It reports what it saw; it never decides whether that passes."""

    def __init__(self, manager: Any, browser: Any) -> None:
        self._manager = manager
        self._browser = browser

    def capture(self, *, url: str, cell: MatrixCell) -> CellObservation:
        context = self._browser.new_context(
            viewport={"width": cell.width, "height": cell.height},
            locale="zh-CN" if cell.language == "zh" else "en-US",
            color_scheme=cell.theme,
            reduced_motion="reduce" if cell.motion == "reduced" else "no-preference",
        )
        page = context.new_page()
        try:
            response = page.goto(f"{url}?state={cell.ui_state}&lang={cell.language}", wait_until="load")
            if response is None or not response.ok:
                status = "no response" if response is None else f"HTTP {response.status}"
                return CellObservation(
                    cell_id=cell.cell_id, language=cell.language, loaded=False, load_error=status
                )
            observed = page.evaluate(_OBSERVER_SCRIPT)
            screenshot = page.screenshot(full_page=False)
            return CellObservation(
                cell_id=cell.cell_id,
                language=cell.language,
                loaded=True,
                decision_sentence=observed.get("decision_sentence"),
                tier1_strings=tuple(observed.get("tier1_strings") or ()),
                braid_marks=tuple(
                    BraidMark(
                        mark_id=str(item.get("mark_id")),
                        keyboard_reachable=bool(item.get("keyboard_reachable")),
                        text_equivalent=str(item.get("text_equivalent") or ""),
                    )
                    for item in observed.get("braid_marks") or ()
                ),
                focus_observations=tuple(
                    FocusObservation(
                        selector=str(item.get("selector")),
                        outline_style=str(item.get("outline_style") or "none"),
                        outline_width_px=float(item.get("outline_width_px") or 0.0),
                        box_shadow=str(item.get("box_shadow") or "none"),
                    )
                    for item in observed.get("focus_observations") or ()
                ),
                hover_only_meaning_nodes=tuple(observed.get("hover_only_meaning_nodes") or ()),
                information_units_standard=tuple(observed.get("information_units_standard") or ()),
                information_units_reduced=tuple(observed.get("information_units_reduced") or ()),
                screenshot_png=screenshot,
                dom_text=str(observed.get("dom_text") or ""),
                computed_styles={str(k): str(v) for k, v in (observed.get("computed_styles") or {}).items()},
            )
        finally:
            context.close()

    def close(self) -> None:
        self._browser.close()
        self._manager.stop()


_OBSERVER_SCRIPT = """
() => {
  const text = (node) => (node ? (node.innerText || node.textContent || '').trim() : '');
  const tier1 = Array.from(document.querySelectorAll('[data-tier="1"]')).map(text).filter(Boolean);
  const braid = Array.from(document.querySelectorAll('[data-braid-mark]')).map((node) => ({
    mark_id: node.getAttribute('data-braid-mark'),
    keyboard_reachable: node.tabIndex >= 0 || ['A', 'BUTTON'].includes(node.tagName),
    text_equivalent: node.getAttribute('data-text-equivalent') || text(node),
  }));
  const focusables = Array.from(
    document.querySelectorAll('a[href], button, [tabindex]:not([tabindex="-1"]), input, select, textarea')
  ).map((node, index) => {
    node.focus();
    const style = getComputedStyle(node);
    return {
      selector: node.getAttribute('data-focus-id') || `${node.tagName.toLowerCase()}#${index}`,
      outline_style: style.outlineStyle,
      outline_width_px: parseFloat(style.outlineWidth) || 0,
      box_shadow: style.boxShadow,
    };
  });
  const hoverOnly = Array.from(document.querySelectorAll('[data-hover-only-meaning]')).map(
    (node) => node.getAttribute('data-hover-only-meaning')
  );
  const units = Array.from(document.querySelectorAll('[data-information-unit]'));
  return {
    decision_sentence: text(document.querySelector('[data-decision-sentence]')) || null,
    tier1_strings: tier1,
    braid_marks: braid,
    focus_observations: focusables,
    hover_only_meaning_nodes: hoverOnly,
    information_units_standard: units.map((node) => node.getAttribute('data-information-unit')),
    information_units_reduced: units
      .filter((node) => node.getAttribute('data-motion-only') !== 'true')
      .map((node) => node.getAttribute('data-information-unit')),
    dom_text: text(document.body),
    computed_styles: {
      'body.background-color': getComputedStyle(document.body).backgroundColor,
      'body.color': getComputedStyle(document.body).color,
    },
  };
}
"""


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", help="served page URL for the D0b acceptance matrix")
    parser.add_argument("--output-dir", default="mockups/refs/biocatalyst/d0b/artifacts")
    parser.add_argument("--headed", action="store_true", help="run the browser headed")
    parser.add_argument("--self-check", action="store_true", help="print the owned gate constants; opens no browser")
    args = parser.parse_args(argv)

    if args.self_check:
        print(json.dumps({
            "verifier_module_ref": VERIFIER_MODULE_REF,
            "verifier_version": VERIFIER_VERSION,
            "verifier_module_sha256": module_source_sha256(),
            "required_checks": list(REQUIRED_CHECKS),
            "gate_parameters": gate_parameters(),
        }, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if not args.url:
        parser.error("--url is required unless --self-check is given")

    cells = matrix_from_axes(INTERNAL_STATE_CODES)
    try:
        driver = playwright_page_driver(headless=not args.headed)
    except VerifierUnavailable as exc:
        run = unavailable_run(url=args.url, reason=str(exc), output_dir=args.output_dir)
        print(f"::warning title=biocatalyst-browser-verifier::{RUN_STATE_UNAVAILABLE}: {exc}", flush=True)
        print(f"receipt: {run.receipt_path} sha256={run.receipt_sha256}")
        return 4

    try:
        run = run_matrix(url=args.url, cells=cells, driver=driver, output_dir=args.output_dir)
    finally:
        close = getattr(driver, "close", None)
        if callable(close):
            close()

    print(f"state: {run.state}")
    print(f"receipt: {run.receipt_path} sha256={run.receipt_sha256}")
    if run.state != RUN_STATE_PASSED:
        print(f"::warning title=biocatalyst-browser-verifier::failed checks: {', '.join(run.failed_checks)}", flush=True)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
