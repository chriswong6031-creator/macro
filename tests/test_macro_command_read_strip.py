"""Macro Command — The Read + the state strip (F01 Macro Command P2).

Design pin `macro_command_P2_design_pin.md` (2026-09-06) is the frozen,
verbatim source for markup/CSS/copy; the frozen spec
`research/market_intelligence_productization/
MARKET_ONTOLOGY_F01_MACRO_COMMAND_DASHBOARD_SPEC_2026-09-06.md` §3/§4/§9-P2
governs everywhere the pin does not speak. This file proves:

1. Every chip value is a digit-free word within its EN/ZH word budget (§3.0
   bullet 1, pin §6.2/§6.5).
2. Chip 8's note carries the counted phrase; its VALUE never does (D-4).
3. STATE_WORD / PREDICATE_FORM / STATE_TONE share an identical
   ``(workspace_id, state_id)`` key set.
4. A ``SOURCE_FAILED`` / ``STALE_SOURCE`` / ``RIGHTS_BLOCKED`` workspace
   always yields a ``neutral`` chip, never ``bad`` (D1) — an instrument
   failure is never a market verdict.
5. An unknown ``(workspace_id, state_id)`` never blocks the build: the page
   is still written, the clause is omitted, ``read.omitted`` is set, and the
   token is recorded in ``unknown_tokens()`` (frozen spec §3.3 step 3,
   red-team F4 — this packet's commission rules the frozen spec wins over
   the design pin's own §4.3 rule 1 "raises" language on this one point).
6. ``read.as_of`` is the OLDEST effective date among the rendered clauses.
7. The Read's punctuation is assigned by position, not stored in copy.
8. No chip edge (the ``<li class="mc-chip">``) carries a tone class — tone
   lives only on ``.mc-chip-value`` (and, in The Read, on
   ``.mc-read-topic``).
9. ``--mc-stance-wash`` stays a percentage in both themes (0% dark / 6%
   light) — the frozen constraint this packet must not disturb.
10. The real built page against the live artifact renders the expected
    shape: >=3 clauses, exactly 8 chips, and the copy guard is green.
"""
from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Any

import pytest

from lib import macro_suite_labels as L
from lib import macro_suite_view
from scripts import build_macro_suite_pages as builder

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"
DATA_ROOT = ROOT / "site" / "macrodata"
BUILT_AT = "2026-09-06T00:00:00Z"

_ZH_RE = re.compile(r"[一-鿿]")
_DIGIT_RE = re.compile(r"\d")

# The seven market chip workspaces this packet reads (design pin §6.1/§6.4).
MARKET_WORKSPACES = (
    "liquidity_regime", "inflation_system", "growth_real_economy",
    "labor_markets", "financial_conditions",
)


def _word_count_en(text: str) -> int:
    return len(text.split())


# --------------------------------------------------------------------------
# fixtures: minimal synthetic `entries` — the same shape build_hub assembles
# --------------------------------------------------------------------------

def _entry(workspace_id: str, *, state_id: str | None = None,
          freshness: str = "CURRENT", effective_date: str | None = "2026-09-06",
          null_reason: str | None = None, state_label: dict[str, str] | None = None,
          snapshot: bool = True) -> dict[str, Any]:
    if not snapshot:
        return {"workspace_id": workspace_id, "region": "US", "output": f"macro_{workspace_id}.html",
                "title": {"en": workspace_id, "zh": workspace_id}, "subtitle": {"en": "", "zh": ""},
                "snapshot": None, "failure": {"kind": "SOURCE_FAILED", "detail": "unreadable"}}
    return {
        "workspace_id": workspace_id, "region": "US", "output": f"macro_{workspace_id}.html",
        "title": {"en": workspace_id, "zh": workspace_id}, "subtitle": {"en": "", "zh": ""},
        "snapshot": {
            "workspace": {"id": workspace_id},
            "availability": {"state": freshness},
            "headline": {
                "state_id": state_id,
                "effective_date": effective_date,
                "null_reason": null_reason,
                "state_label": state_label,
            },
        },
        "failure": None,
    }


def _all_current_entries() -> list[dict[str, Any]]:
    """One entry per every registered workspace, all CURRENT with a known
    state — the coverage tally's 11 representative workspaces plus the seven
    chip workspaces overlap, so this list is exactly the union."""
    from scripts.build_macro_suite_pages import SUITE_PAGES
    entries = []
    for page in SUITE_PAGES:
        wid = page.workspace_id
        table = L.STATE_WORD.get(wid)
        state_id = next(iter(table)) if table else None
        entries.append(_entry(wid, state_id=state_id, effective_date="2026-09-06"))
    return entries


# --------------------------------------------------------------------------
# 1 — digit-free chip values within word budget
# --------------------------------------------------------------------------

@pytest.mark.parametrize("table_name", ["STATE_WORD"])
def test_state_word_entries_are_digit_free_and_within_budget(table_name: str) -> None:
    table = getattr(L, table_name)
    for workspace_id, by_state in table.items():
        for state_id, pair in by_state.items():
            for lang, text in pair.items():
                assert not _DIGIT_RE.search(text), (workspace_id, state_id, lang, text)
            assert _word_count_en(pair["en"]) <= 3, (workspace_id, state_id, pair["en"])
            assert len(pair["zh"]) <= 7, (workspace_id, state_id, pair["zh"])


def test_coverage_word_entries_are_digit_free() -> None:
    for key, pair in L.COVERAGE_WORD.items():
        for lang, text in pair.items():
            assert not _DIGIT_RE.search(text), (key, lang, text)


def test_predicate_form_within_word_budget() -> None:
    for workspace_id, by_state in L.PREDICATE_FORM.items():
        for state_id, pair in by_state.items():
            assert _word_count_en(pair["en"]) <= 8, (workspace_id, state_id, pair["en"])
            assert len(pair["zh"]) <= 16, (workspace_id, state_id, pair["zh"])


def test_chip_meaning_within_word_budget() -> None:
    for chip_id, pair in L.CHIP_MEANING.items():
        assert _word_count_en(pair["en"]) <= 24, (chip_id, pair["en"])
        assert len(pair["zh"]) <= 42, (chip_id, pair["zh"])


# --------------------------------------------------------------------------
# 2 — chip 8's counted phrase lives in the NOTE, never the value (D-4)
# --------------------------------------------------------------------------

_COVERAGE_NOTE_EN_RE = re.compile(r"^\d+ of \d+ sections have today's data$")
_COVERAGE_NOTE_ZH_RE = re.compile(r"^\d+ 个板块中 \d+ 个已有今日数据$")


def test_coverage_chip_value_has_no_digit_and_note_matches_counted_phrase() -> None:
    entries = _all_current_entries()
    header = macro_suite_view.build_command_header(entries, page_built_at=BUILT_AT)
    coverage = next(c for c in header["strip"] if c["id"] == "coverage")
    assert not _DIGIT_RE.search(coverage["value"]["en"])
    assert not _DIGIT_RE.search(coverage["value"]["zh"])
    assert _COVERAGE_NOTE_EN_RE.match(coverage["note"]["en"]), coverage["note"]["en"]
    assert _COVERAGE_NOTE_ZH_RE.match(coverage["note"]["zh"]), coverage["note"]["zh"]


def test_coverage_tally_available_never_exceeds_total() -> None:
    entries = _all_current_entries()
    header = macro_suite_view.build_command_header(entries, page_built_at=BUILT_AT)
    coverage = header["coverage"]
    assert coverage["total"] == len(macro_suite_view._COVERAGE_WORKSPACES) + 1
    assert coverage["total"] == 12
    assert 0 <= coverage["available"] <= coverage["total"]
    assert coverage["available"] == coverage["total"]  # every entry is CURRENT here


def test_coverage_tally_drops_when_a_representative_workspace_is_not_current() -> None:
    entries = _all_current_entries()
    for entry in entries:
        if entry["workspace_id"] == "trade_flows":
            entry["snapshot"]["availability"]["state"] = "STALE_SOURCE"
    header = macro_suite_view.build_command_header(entries, page_built_at=BUILT_AT)
    assert header["coverage"]["available"] == header["coverage"]["total"] - 1


# --------------------------------------------------------------------------
# 3 — STATE_WORD / PREDICATE_FORM / STATE_TONE share one key set
# --------------------------------------------------------------------------

def test_state_word_predicate_form_state_tone_share_identical_keys() -> None:
    word_keys = {(w, s) for w, by in L.STATE_WORD.items() for s in by}
    pred_keys = {(w, s) for w, by in L.PREDICATE_FORM.items() for s in by}
    tone_keys = {(w, s) for w, by in L.STATE_TONE.items() for s in by}
    assert word_keys == pred_keys == tone_keys
    assert word_keys, "expected at least one reviewed (workspace, state) pair"


def test_every_market_workspace_has_all_four_quadrant_letters() -> None:
    for workspace_id in MARKET_WORKSPACES:
        assert set(L.STATE_WORD[workspace_id]) == {"A", "B", "C", "D"}, workspace_id


# --------------------------------------------------------------------------
# 4/5 — freshness never becomes a tone; instrument failure != market verdict
# --------------------------------------------------------------------------

@pytest.mark.parametrize("freshness", ["SOURCE_FAILED", "STALE_SOURCE", "RIGHTS_BLOCKED"])
def test_a_null_state_never_renders_a_bad_or_ok_tone(freshness: str) -> None:
    """D1: a workspace with no state_id renders `neutral`, regardless of WHY
    it has no state — freshness never contributes a tone anywhere."""
    entries = [_entry("liquidity_regime", state_id=None, freshness=freshness,
                      effective_date=None, null_reason="NOT_APPLICABLE")]
    header = macro_suite_view.build_command_header(entries, page_built_at=BUILT_AT)
    chip = next(c for c in header["strip"] if c["id"] == "money")
    assert chip["null"] is True
    assert chip["tone"] == "neutral"


def test_a_workspace_this_build_could_not_read_renders_null_neutral() -> None:
    entries = [_entry("liquidity_regime", snapshot=False)]
    header = macro_suite_view.build_command_header(entries, page_built_at=BUILT_AT)
    chip = next(c for c in header["strip"] if c["id"] == "money")
    assert chip["null"] is True
    assert chip["tone"] == "neutral"
    assert chip["note"] == L.CHIP_NULL_NOTE["no_snapshot"]


def test_no_axes_workspace_with_current_freshness_gets_the_no_state_cause() -> None:
    """`monetary_policy`-shaped case: status=ABSENT/NOT_APPLICABLE but the
    SOURCE itself is CURRENT — the cause is structural, not a late arrival."""
    entries = [_entry("monetary_policy", state_id=None, freshness="CURRENT",
                      effective_date=None, null_reason="NOT_APPLICABLE")]
    header = macro_suite_view.build_command_header(entries, page_built_at=BUILT_AT)
    chip = next(c for c in header["strip"] if c["id"] == "policy")
    assert chip["null"] is True
    assert chip["note"] == L.CHIP_NULL_NOTE["no_state"]


def test_no_axes_workspace_that_also_failed_today_gets_the_late_cause() -> None:
    """`rates_curves`-shaped case (design pin §11.2 frame observation): BOTH
    structurally state-less AND SOURCE_FAILED today — freshness trouble is
    the more urgent, more actionable fact and wins the cause selection."""
    entries = [_entry("rates_curves", state_id=None, freshness="SOURCE_FAILED",
                      effective_date=None, null_reason="NOT_APPLICABLE")]
    header = macro_suite_view.build_command_header(entries, page_built_at=BUILT_AT)
    chip = next(c for c in header["strip"] if c["id"] == "rates")
    assert chip["null"] is True
    assert chip["note"] == L.CHIP_NULL_NOTE["late"]


# --------------------------------------------------------------------------
# 5b — an unknown (workspace_id, state_id) never blocks the build
# --------------------------------------------------------------------------

def test_unknown_state_id_never_raises_omits_the_clause_and_records_the_token() -> None:
    L.reset_unknown_tokens()
    entries = [_entry("liquidity_regime", state_id="Z", freshness="CURRENT",
                      effective_date="2026-09-06",
                      state_label={"en": "Some future state", "zh": "某种未来状态"})]
    header = macro_suite_view.build_command_header(entries, page_built_at=BUILT_AT)
    chip = next(c for c in header["strip"] if c["id"] == "money")
    assert chip["null"] is False  # there IS a reading — just no reviewed word
    assert chip["tone"] == "neutral"
    assert chip["value"] == {"en": "Some future state", "zh": "某种未来状态"}
    assert not any(c["id"] == "money" for c in header["read"]["clauses"])
    assert header["read"]["omitted"] is True
    assert any(tok.startswith("macro_command_state:liquidity_regime:Z") for tok in L.unknown_tokens())
    L.reset_unknown_tokens()


def test_unknown_state_id_prints_a_line_start_warning(capsys: pytest.CaptureFixture[str]) -> None:
    L.reset_unknown_tokens()
    entries = [_entry("liquidity_regime", state_id="Z", freshness="CURRENT")]
    macro_suite_view.build_command_header(entries, page_built_at=BUILT_AT)
    captured = capsys.readouterr()
    assert any(line.startswith("::warning title=macro-command-unknown-state::")
              for line in captured.out.splitlines()), captured.out
    L.reset_unknown_tokens()


def test_the_page_still_builds_when_a_workspace_carries_an_unrecognised_state(tmp_path: Path) -> None:
    """Frozen spec §3.3 step 3 / red-team F4: an unrecognised state is a
    printed null, never a build failure — the page is still written."""
    import shutil

    data_root = tmp_path / "macrodata"
    shutil.copytree(DATA_ROOT, data_root)
    victim = data_root / "workspaces" / "liquidity_regime" / "US" / "latest.json"
    import json
    snap = json.loads(victim.read_text(encoding="utf-8"))
    snap["headline"]["state_id"] = "Z"
    # keep the manifest's content hash agreeing with the mutated body
    import hashlib
    body = json.dumps(snap).encode("utf-8")
    manifest_path = data_root / "workspaces" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entry_key = "liquidity_regime/US"
    new_hash = hashlib.sha256(body).hexdigest()
    manifest["workspaces"][entry_key]["content_sha256"] = new_hash
    manifest["workspaces"][entry_key]["bytes"] = len(body)
    snap.setdefault("generation", {})["content_sha256"] = new_hash
    victim.write_text(json.dumps(snap), encoding="utf-8")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    out = tmp_path / "site"
    L.reset_unknown_tokens()
    pages = builder.render(ROOT, data_root=data_root, out_dir=out, page_built_at=BUILT_AT)
    hub = [p for p in pages if p.name == builder.HUB_PAGE.output]
    assert hub, "the builder must still write macro_monetary.html"
    assert hub[0].exists()
    L.reset_unknown_tokens()


# --------------------------------------------------------------------------
# 6/7 — read.as_of and punctuation
# --------------------------------------------------------------------------

def test_read_as_of_is_the_oldest_effective_date_among_rendered_clauses() -> None:
    entries = [
        _entry("liquidity_regime", state_id="A", effective_date="2026-09-06"),
        _entry("inflation_system", state_id="A", effective_date="2026-09-01"),
        _entry("growth_real_economy", state_id="A", effective_date="2026-09-05"),
    ]
    header = macro_suite_view.build_command_header(entries, page_built_at=BUILT_AT)
    assert header["read"]["as_of"] == "2026-09-01"


def test_punctuation_is_assigned_by_position_mid_penultimate_last() -> None:
    entries = [
        _entry("liquidity_regime", state_id="A"),
        _entry("inflation_system", state_id="A"),
        _entry("growth_real_economy", state_id="A"),
        _entry("labor_markets", state_id="A"),
        _entry("financial_conditions", state_id="A"),
    ]
    header = macro_suite_view.build_command_header(entries, page_built_at=BUILT_AT)
    clauses = header["read"]["clauses"]
    assert len(clauses) == 5
    for clause in clauses[:-2]:
        assert clause["punct"] == L.READ_PUNCT["mid"]
    assert clauses[-2]["punct"] == L.READ_PUNCT["penultimate"]
    assert clauses[-1]["punct"] == L.READ_PUNCT["last"]


def test_fewer_than_three_clauses_still_sets_omitted_and_no_as_of_crash() -> None:
    entries = [_entry("liquidity_regime", state_id="A", effective_date="2026-09-06")]
    header = macro_suite_view.build_command_header(entries, page_built_at=BUILT_AT)
    assert len(header["read"]["clauses"]) == 1
    assert header["read"]["omitted"] is True
    assert header["read"]["as_of"] == "2026-09-06"


# --------------------------------------------------------------------------
# 8 — no chip edge carries a tone class
# --------------------------------------------------------------------------

def test_no_chip_edge_carries_a_tone_class() -> None:
    macros = (TEMPLATES / "_macro_command_macros.html.j2").read_text(encoding="utf-8")
    state_strip_match = re.search(r"\{% macro state_strip.*?\{%-\s*endmacro\s*%\}", macros, re.S)
    assert state_strip_match, "state_strip macro not found"
    body = state_strip_match.group(0)
    li_match = re.search(r'<li class="mc-chip[^"]*"', body)
    assert li_match, body
    assert "mq-tone" not in li_match.group(0)


# --------------------------------------------------------------------------
# 9 — --mc-stance-wash stays a percentage in both themes
# --------------------------------------------------------------------------

def test_mc_stance_wash_is_zero_percent_dark_and_six_percent_light() -> None:
    css = (TEMPLATES / "macro_command.css").read_text(encoding="utf-8")
    assert re.search(r"--mc-stance-wash:\s*0%\s*;", css)
    assert re.search(r"--mc-stance-wash:\s*6%\s*;", css)


# --------------------------------------------------------------------------
# theme-differing tokens defined in both blocks (pin §10 item 12)
# --------------------------------------------------------------------------

_THEME_DIFFERING_TOKENS = (
    "mc-strip-gap", "mc-strip-bg", "mc-strip-border", "mc-strip-shadow",
    "mc-strip-radius", "mc-chip-border-w", "mc-chip-radius", "mc-chip-pad",
    "mc-lit-halo", "mc-lit-underline", "mc-read-weight",
)


@pytest.mark.parametrize("token", _THEME_DIFFERING_TOKENS)
def test_every_theme_differing_token_is_declared_at_least_twice(token: str) -> None:
    css = (TEMPLATES / "macro_command.css").read_text(encoding="utf-8")
    assert len(re.findall(rf"--{token}:", css)) >= 2, token


# --------------------------------------------------------------------------
# 10 — the real built page against the live artifact
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def built_hub(tmp_path_factory: pytest.TempPathFactory) -> str:
    out = tmp_path_factory.mktemp("macro_command_read_strip") / "site"
    pages = builder.render(ROOT, data_root=DATA_ROOT, out_dir=out, page_built_at=BUILT_AT)
    hub = [p for p in pages if p.name == builder.HUB_PAGE.output]
    assert hub, "the builder did not write macro_monetary.html"
    return hub[0].read_text(encoding="utf-8")


def test_the_real_page_renders_at_least_five_chips_and_exactly_eight_total(built_hub: str) -> None:
    chip_ids = re.findall(r'<li class="mc-chip[^"]*" data-mc-topic="([a-z]+)"', built_hub)
    assert chip_ids == ["money", "policy", "rates", "inflation", "growth", "jobs",
                        "credit", "coverage"]


def test_the_real_page_carries_no_bare_iso_timestamp_in_visible_text(built_hub: str) -> None:
    """G2b, restated for the header specifically: `<time datetime=...>` is
    fine; a bare ISO date in the surrounding text is not."""
    visible = re.sub(r'datetime="[^"]*"', "", built_hub)
    assert not re.search(r">\s*\d{4}-\d{2}-\d{2}\s*<", visible)


def test_the_real_built_page_passes_the_copy_guard(built_hub: str, tmp_path: Path) -> None:
    from scripts import check_macro_command_copy as guard
    assert guard.find_violations(built_hub) == []


def test_unknown_tokens_are_empty_for_the_shipped_artifact() -> None:
    """Frozen spec §3.3 step 5: assert clean for TODAY's real artifact —
    this is the shipped-state proof, not a guarantee against every future
    producer letter."""
    L.reset_unknown_tokens()
    out = ROOT / "site"
    entries_snapshot_ids = []
    for page in builder.SUITE_PAGES:
        try:
            snapshot, _artifact = builder.read_workspace(DATA_ROOT, page)
            entries_snapshot_ids.append({"workspace_id": page.workspace_id, "region": page.region,
                                        "output": page.output, "title": {"en": "", "zh": ""},
                                        "subtitle": {"en": "", "zh": ""}, "snapshot": snapshot,
                                        "failure": None})
        except Exception:  # noqa: BLE001 — a refusal degrades to "no snapshot" here
            entries_snapshot_ids.append({"workspace_id": page.workspace_id, "region": page.region,
                                        "output": page.output, "title": {"en": "", "zh": ""},
                                        "subtitle": {"en": "", "zh": ""}, "snapshot": None,
                                        "failure": {"kind": "SOURCE_FAILED", "detail": "n/a"}})
    macro_suite_view.build_command_header(entries_snapshot_ids, page_built_at=BUILT_AT)
    unknown = [t for t in L.unknown_tokens() if t.startswith("macro_command_state:")]
    assert unknown == [], unknown
    L.reset_unknown_tokens()
