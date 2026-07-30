"""BC-2: the three enforcement gaps the 2026-07-29 dislocation-panel audit found.

GAP 1 — `surfaces` was decorative. Every allowlist entry has carried a `surfaces` list
naming the page/study its justification was written for, and the matcher never read it.
Matching was phrase-scoped only, so an affirmative claim on ANY page passed as long as
its wording matched an entry justified for a DIFFERENT page. Live case: the dashboard's
dislocation panel said "the validated gate governs" / "the validated Fed-put gate
governs" and rode entries backed by the sector_central absolute-trend gate and the
spvector re-deploy overlay — two studies that say nothing about the Fed-put master
switch. The panel's real backing (research/DISLOCATION_VALIDATION.md) was never named,
which is exactly the traceability BC-2 exists to force.

GAP 2 — the zh token list was '已验证' only. The script's own header flagged 经验证
("having been validated") as a KNOWN GAP; the dislocation panel's zh copy
以经验证的一道闸为准 (engine/dislocation.py) was therefore not gated at all while its EN
twin was. 经过验证 had the same hole (gex.html), and 已经验证 is covered through 经验证.

GAP 3 — a hyphen was read as a CSS selector. The structural skip for selector / DOM
identifier tokens was written `[.\\-]validated\\b` — "a dot OR A HYPHEN before the token".
A hyphen before the token is also how English writes an adjective, so
"backtest-validated", "Holdout-validated", "FDR-validated", "drawdown-validated" all
matched it; and because a _STRUCTURAL hit kills the WHOLE LINE, those claims were
invisible to BC-2 — no allowlist entry, no CI failure, no trace. 21 lines reached the gate
only through that rule: 7 genuine selectors and 14 carrying prose claims. The rule now
requires a DOT-PREFIXED identifier (_IDENT_MASK) and MASKS that identifier in place
instead of killing its line, so copy sharing a line with a selector is still gated.

All three are pinned here through the REAL gate (scan_text / scan_python_copy / _scan_line
+ the live allowlist), never a substring match, so negation, structural and surface
semantics stay in one place.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.check_validated_claims import (
    TOKEN,
    _allow_match,
    _load_allowlist,
    _scan_line,
    _surfaces_of,
    scan,
    scan_python_copy,
    scan_text,
)

ROOT = Path(__file__).resolve().parent.parent
ALLOW = _load_allowlist()
ALLOWLIST_PATH = ROOT / "data" / "regime" / "validated_claims_allowlist.json"

# An affirmative claim whose wording IS allowlisted — for the discovery/us_stocks_v2
# confluence gate, and nowhere near the pages used as the "wrong surface" below.
ALLOWLISTED_LINE = "Gated by the validated MACD-2D × StochRSI-3D confluence."


# ── GAP 1: surfaces are enforced ─────────────────────────────────────────────────────

def test_allowlisted_phrase_passes_on_a_listed_surface():
    _, hits = _scan_line(ALLOWLISTED_LINE, ALLOW, _surfaces_of("templates/discovery.html.j2"))
    assert hits and all(backed for backed, _ in hits)


def test_same_phrase_fails_on_an_unlisted_surface():
    """The defect itself: a justification written for one page must not license another."""
    _, hits = _scan_line(ALLOWLISTED_LINE, ALLOW, _surfaces_of("templates/forex.html.j2"))
    assert hits and not any(backed for backed, _ in hits)


def test_an_entry_without_surfaces_backs_nothing():
    """Fail closed: a new entry must declare where it applies, or it earns no claim."""
    entry = [{"match": "validated probe phrase", "backing": "none"}]
    _, hits = _scan_line("This is a validated probe phrase.", entry, frozenset({"anything"}))
    assert hits and not any(backed for backed, _ in hits)
    assert _allow_match("a validated probe phrase", entry, frozenset({"anything"})) is None


def test_every_allowlist_entry_declares_surfaces():
    dead = [e["match"] for e in ALLOW if not (e.get("surfaces") or [])]
    assert dead == [], f"entries that can never back a claim: {dead}"


def test_the_unearned_report_says_when_the_miss_is_the_surface():
    """A wrong-surface finding must not read like a missing-justification finding."""
    found, _ = scan_text("site/forex.html", f"<p>{ALLOWLISTED_LINE}</p>", ALLOW)
    assert len(found) == 1
    assert "phrase matches entry" in found[0]["text"]
    assert "`surfaces`" in found[0]["text"]


@pytest.mark.parametrize("rel,expected", [
    # one template written out under several names — folded together on purpose
    ("templates/dashboard.html.j2", {"dashboard", "macro", "us_stocks"}),
    ("site/macro.html", {"dashboard", "macro"}),
    ("site/us_stocks.html", {"dashboard", "us_stocks"}),
    ("site/allocation_canada.html", {"allocation_canada", "allocation"}),
    # site subdirectories are per-item render families
    ("site/sectors/XLB.html", {"sectors", "sector"}),
    ("site/basket_china/cn_autos.html", {"basket_china", "basket_detail"}),
    # partial templates ARE their own surface, minus the leading underscore
    ("templates/_desk_grader_panel.html.j2", {"desk_grader_panel"}),
    # engine modules are the surface that authors the copy
    ("engine/dislocation.py", {"dislocation"}),
])
def test_surface_derivation(rel, expected):
    assert _surfaces_of(rel) == frozenset(expected)


def test_a_shared_partial_does_not_launder_scope_through_the_derivation():
    """_SURFACE_EXTRA is identity-only. The pages that INCLUDE a partial must be named in
    the entry's `surfaces`, so adding a new include site is a visible allowlist edit rather
    than a silent widening in code."""
    assert _surfaces_of("site/alt_data.html") == frozenset({"alt_data"})
    assert "desk_grader_panel" not in _surfaces_of("site/alt_data.html")
    entry = next(e for e in ALLOW if e["match"] == "dg-badge dg-proven")
    assert {"desk_grader_panel", "alt_data", "congress_trades"} <= set(entry["surfaces"])


# ── GAP 2: the zh token variants ─────────────────────────────────────────────────────

@pytest.mark.parametrize("zh", [
    "该策略具备经验证的方向性优势。",          # 经验证 — the gap the audit found live
    "该引擎经过验证。",                        # 经过验证
    "该信号已经验证具备优势。",                # 已经验证 (matched inside 经验证)
    "该信号是已验证的方向性优势。",            # 已验证 — the variant that always worked
])
def test_affirmative_zh_variants_are_claims(zh):
    _, hits = _scan_line(zh, ALLOW, frozenset({"_probe"}))
    assert hits and not any(backed for backed, _ in hits), f"ungated zh claim: {zh}"


@pytest.mark.parametrize("zh", [
    "该构造未经验证，仅供参考。",              # 未经验证
    "香港没有经验证的选股阿尔法。",            # 没有 — hk_lookup's honest disclaimer
    "该效应尚未被经验证的框架覆盖。",          # 尚未
    "该主题缺乏经验证的前瞻优势。",            # 缺乏
    "非经验证的超额收益",                      # 非 — narrative_radar's disclaimer
])
def test_negated_zh_variants_are_not_claims(zh):
    """Widening TOKEN without widening _NEG_ZH would have made deleting the disclaimer the
    cheapest way out of the red — the inversion this gate exists to prevent."""
    n_neg, hits = _scan_line(zh, ALLOW, frozenset({"_probe"}))
    assert n_neg >= 1 and not hits, f"honest disclaimer flagged as a claim: {zh}"


# ── the dislocation panel: the audited claim, now naming its own study ───────────────

_DISLOCATION_CLAIMS = [
    # (engine source string, the phrase the allowlist must cover)
    ("Divergence — the Fed-put switch reads BUYABLE WASHOUT, but the catalyst text reads "
     "PERSISTENT (structural). The validated gate governs; treat the narrative as a caution "
     "flag worth a look.", "validated gate governs"),
    ("背离 —— 美联储托底开关判定为「可买入错杀」。以经验证的一道闸为准；将该叙述视为值得留意的警示信号。",
     "以经验证的一道闸为准"),
]


@pytest.mark.parametrize("copy,phrase", _DISLOCATION_CLAIMS)
def test_dislocation_panel_claims_are_backed_on_their_own_surface(copy, phrase):
    found, _ = scan_python_copy("engine/dislocation.py", f'{{"note_zh": {copy!r}}}', ALLOW)
    assert found == [], f"dislocation copy unearned: {found}"
    entry = next(e for e in ALLOW if e["match"] == phrase)
    assert "DISLOCATION_VALIDATION.md" in entry["backing"], (
        "the dislocation panel's gate must cite its OWN validation, not sector_central's "
        "trend gate or the spvector overlay")
    assert "dislocation" in entry["surfaces"]


def test_the_borrowed_entries_stay_scoped_to_their_own_studies():
    """The two entries the panel used to ride keep their original scope, and the panel's own
    entries do not leak back the other way.

    Note the EN sentence "the validated gate governs" still passes on sector_central — via
    sector_central's OWN 'validated gate' entry, whose trend-breadth gate really is called
    that there. What must not travel is the justification: the dislocation entries are
    scoped to the panel, and the panel's zh wording (unique to it) earns nothing elsewhere.
    """
    for match in ("validated gate", "validated fed-put gate"):
        entry = next(e for e in ALLOW if e["match"] == match)
        assert "dislocation" not in entry["surfaces"]
        assert "DISLOCATION_VALIDATION.md" not in entry["backing"]
    for match in ("validated gate governs", "以经验证的一道闸为准"):
        entry = next(e for e in ALLOW if e["match"] == match)
        assert set(entry["surfaces"]) == {"dashboard", "dislocation"}
    zh = "以经验证的一道闸为准；将该叙述视为值得留意的警示信号。"
    for rel in ("templates/sector_central.html.j2", "templates/spvector.html.j2",
                "templates/anticipation.html.j2"):
        found, _ = scan_text(rel, zh, ALLOW)
        assert found, f"{rel} must not inherit the dislocation gate's justification"


def test_dislocation_validation_artifact_exists():
    """An entry is a claim of record: the doc it names has to be there."""
    doc = ROOT / "research" / "DISLOCATION_VALIDATION.md"
    assert doc.exists()
    text = doc.read_text(encoding="utf-8")
    assert "PUT-ABSENT" in text and "split-half" in text


# ── GAP 3: a hyphen is not a selector ────────────────────────────────────────────────

_PROBE = frozenset({"_probe"})


@pytest.mark.parametrize("line", [
    "  .nbb-validated { color: var(--up); }",                    # CSS class selector
    "  .val-chip.validated   { color:var(--ok); }",              # chained class
    "  .ai-chip .ai-tag.validated{color:var(--green)}",          # descendant + chained
    "{%- if x.validated %}",                                     # dotted attribute access
    "  /* micro-style — .et-validated / .et-accruing / .et-context. */",
])
def test_selector_and_identifier_tokens_are_not_claims(line):
    _, hits = _scan_line(line, ALLOW, _PROBE)
    assert hits == [], f"selector read as prose: {line}"


@pytest.mark.parametrize("line", [
    "Epoch: 2026-Q3 · backtest-validated OOS; live cohort accruing",
    "Holdout-validated, leak-free; act early — the edge decays in ~2-4 days.",
    "is a real FDR-validated bounce ALERT (63d P-up 75% vs 72% base)",
    "Anticipation stop-width (drawdown-validated): avg close-path adverse excursion",
    "requires two mature cohorts and holdout-validated incrementality",
    "  /* COILED wave-2-validated cohort-washout ranking bonus chip */",
])
def test_hyphenated_prose_is_a_claim(line):
    """The defect itself. Each of these shipped invisible to BC-2 — the hyphen made the rule
    read an English adjective as a CSS class, and a _STRUCTURAL hit kills the whole line."""
    _, hits = _scan_line(line, ALLOW, _PROBE)
    assert hits and not any(backed for backed, _ in hits), f"ungated prose claim: {line}"


def test_a_selector_no_longer_suppresses_copy_sharing_its_line():
    """The other half of the defect: one selector used to hide every claim beside it.
    _IDENT_MASK excises the identifier and scans the rest of the line normally."""
    line = '{%- if x.validated %}<span data-tip-en="This edge is validated on every desk.">'
    _, hits = _scan_line(line, ALLOW, _PROBE)
    assert len(hits) == 1 and not hits[0][0]


def test_a_sentence_boundary_is_not_an_identifier():
    """'. Validated' is a full stop, not a class token — the lookahead requires the character
    after the dot to start an identifier."""
    _, hits = _scan_line("The gate passed. Validated on the 2024+ holdout.", ALLOW, _PROBE)
    assert hits and not any(backed for backed, _ in hits)


def test_excising_an_identifier_cannot_break_the_negation_beside_it():
    """The cut sentinel sits outside every character class in TOKEN / _NEG_EN / _NEG_ZH, so an
    excision can neither splice a new token together nor let a negation lookback cross it."""
    n_neg, hits = _scan_line("there is no .nbb-validated edge and no validated edge",
                             ALLOW, _PROBE)
    assert hits == [] and n_neg == 1


# The prose claims GAP 3 surfaced, each as it ships, with the entry that now earns it.
_ADJUDICATED = [
    ("site/alerts.html",
     '<span class="l-en">Forward de-risk window from a verified LEADING precursor cross '
     '(impulse radar). Holdout-validated, leak-free; act early</span>',
     "Holdout-validated, leak-free"),
    ("site/alerts.html",
     '<span class="l-zh">来自经验证的领先前兆突破的前瞻减仓窗口（脉冲雷达）。</span>',
     "经验证的领先前兆突破"),
    ("site/cycle_app.js",
     "' · backtest-validated OOS; live cohort accruing (come-back: n_matured≥40 per cell)')",
     "backtest-validated OOS; live cohort accruing"),
    ("templates/sector_cycles.js",
     '"Epoch: " + epoch + revOpt + " · backtest-validated OOS; live cohort accruing")',
     "backtest-validated OOS; live cohort accruing"),
    ("site/signal_lab.html",
     "The capitulation gauge (VRP-extreme + VIX&gt;30 + COT-washout) is a real "
     "FDR-validated bounce ALERT (63d P-up 75% vs 72% base)",
     "FDR-validated bounce ALERT"),
    ("templates/dashboard.html.j2",
     "  /* COILED wave-2-validated cohort-washout ranking bonus chip (display-only) */",
     "wave-2-validated cohort-washout ranking bonus"),
]


@pytest.mark.parametrize("rel,line,phrase", _ADJUDICATED)
def test_the_surfaced_claims_are_backed_on_their_own_surface(rel, line, phrase):
    found, _ = scan_text(rel, line, ALLOW)
    assert found == [], f"{rel} unearned: {found}"
    entry = next(e for e in ALLOW if e["match"] == phrase)
    assert set(entry["surfaces"]) & set(_surfaces_of(rel)), entry["surfaces"]


@pytest.mark.parametrize("rel,line,phrase", _ADJUDICATED)
def test_those_justifications_do_not_travel_to_another_page(rel, line, phrase):
    """Each new entry is scoped to the surfaces its study covers — none of them licenses a page
    the study says nothing about."""
    found, _ = scan_text("templates/forex.html.j2", line, ALLOW)
    assert found, f"{phrase!r} must not back a page outside its study"


def test_the_btc_impulse_edge_line_is_backed_at_its_engine_source():
    """EN and zh halves of one sentence: the zh half was already backed, the EN half rode the
    hyphen. Both are now claims of record on the module that authors them."""
    found, _ = scan_python_copy(
        "engine/btc_alerts.py",
        '{"edge": "Forward de-risk window from a verified LEADING precursor cross '
        '(impulse radar). Holdout-validated, leak-free; act early.",\n'
        ' "edge_zh": "来自经验证的领先前兆突破的前瞻减仓窗口（脉冲雷达）。"}\n', ALLOW)
    assert found == [], f"btc_alerts conviction line unearned: {found}"


def test_the_de_escalated_copy_stays_de_escalated():
    """Two lines were reworded, not allowlisted, because no study backs them: the anticipation
    stop-width is dd_avg (a descriptive average close-path adverse excursion, and the unscored
    branch claimed it for a horizon the same parenthesis called unscored), and the marketing
    north-star note has no data at all. If the word returns, it must return with a study."""
    dash = (ROOT / "templates" / "dashboard.html.j2").read_text(encoding="utf-8")
    assert "drawdown-validated" not in dash
    state = (ROOT / "engine" / "marketing" / "state.py").read_text(encoding="utf-8")
    assert "holdout-validated" not in state


@pytest.mark.parametrize("doc", [
    "research/VECTOR_IMPULSE_PREDICTION.md",
    "research/cycle_masterplan/PREREGISTRATION.md",
    "research/cycle_masterplan/W42_HAZARD_VERDICT.md",
    "research/entry_timing/WAVE2_REPORT.md",
    "reports/capitulation-overlay-phase0.md",
])
def test_the_backings_named_by_the_new_entries_exist(doc):
    """An entry is a claim of record: the artifact it names has to be there."""
    assert (ROOT / doc).exists(), doc


# ── wiring + no-debt ────────────────────────────────────────────────────────────────

def test_the_live_tree_is_clean():
    """Ships with zero pre-existing debt under BOTH new rules."""
    assert scan(list_all=False) == []


def test_the_allowlist_is_valid_json_with_the_documented_contract():
    d = json.loads(ALLOWLIST_PATH.read_text(encoding="utf-8"))
    assert "`surfaces` is ENFORCED" in d["notes"]
    for e in d["allow"]:
        assert e.get("match") and e.get("backing"), e
        assert isinstance(e.get("surfaces"), list) and e["surfaces"], e


def test_token_covers_every_zh_variant_the_estate_uses():
    for v in ("validated", "已验证", "经验证", "经过验证", "已经验证"):
        assert TOKEN.search(v), v
