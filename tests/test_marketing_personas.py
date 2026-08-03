"""tests/test_marketing_personas.py — Persona spec v1 loader + roster (W1, docket D13).

Deps: stdlib + pytest + pyyaml only (runs in the ``marketing-engine`` CI lane,
which installs exactly that). No pandas, no numpy — a top-level heavy import in
engine/marketing/personas.py must turn this suite red at collection.

Test list:
  1.  All 18 committed specs load; the ``--check`` CLI exits 0 on the real tree.
  2.  Every loader rejection class is rejected (11 named classes + the extras).
  3.  control_v3.tilt IS content_studio._DEFAULT_TILT — the control arm is pinned.
  4.  The 11 desk-derived specs agree with config/marketing.yml (drift fails here).
  5.  Importing engine.marketing.personas mutates no content_studio/copywriter
      module state, and does not even import content_studio (lazy-import contract).
  6.  _get_copy never falls back for a configured persona's voice key.
  7.  The admin roster renders with specs and is fail-soft with the dir absent.
  8.  Exactly ONE generation-side module reads a persona spec (XG-W1 seam).
"""
from __future__ import annotations

import copy
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from engine.marketing import personas as P


def _worktree_root() -> Path:
    p = Path(__file__).resolve()
    for candidate in [p.parent, p.parent.parent, p.parent.parent.parent]:
        if (candidate / "engine").is_dir():
            return candidate
    raise RuntimeError(f"Could not locate repo root from {p}")


ROOT = _worktree_root()

#: The 18 committed specs, in three groups.
#:
#: _DERIVED_IDS — a desk_network entry AND a copywriter.personas block back this
#: spec, so config drift in either must fail here. The 6 W1 desks + the founder's
#: personal account (2026-07-27) + the four employee desks (XG-W1, 2026-07-28).
#: _WIRED_DARK_IDS — a desk_network entry but NO copywriter block: the two
#: publication properties' registers are the house wire / analyst voice rather
#: than a desk persona.  mastermind_news is disabled until the XG-W2 cadence
#: resolver lands; mastermind_research joined at W2R (XG-W8) and is darker still
#: — its X account does not exist yet, so it carries no `handle` and no Buffer
#: channel on top of `enabled: false` + `disabled: true`.
#: _AUTHORED_IDS — spec-only, no account behind them.
_DERIVED_IDS = ("flagship", "receipts", "theme_desk", "research_a", "research_b",
                "research_c", "founder", "meagan", "sophia", "kelly", "cici")
_EMPLOYEE_IDS = ("meagan", "sophia", "kelly", "cici")
_WIRED_DARK_IDS = ("mastermind_news", "mastermind_research")
_AUTHORED_IDS = ("corp_desk", "chart_gremlin", "zh_navigator", "control_v3",
                 "news_flash")
_ALL_IDS = _DERIVED_IDS + _WIRED_DARK_IDS + _AUTHORED_IDS


@pytest.fixture(scope="module")
def specs() -> dict:
    return P.load_all(ROOT)


@pytest.fixture(scope="module")
def marketing_cfg() -> dict:
    return yaml.safe_load((ROOT / "config" / "marketing.yml").read_text(encoding="utf-8")) or {}


def _base_spec() -> dict:
    """A known-good spec dict, read from a committed file.

    Every rejection test mutates ONE field of this, so a failure names exactly
    the rule that stopped firing rather than "the fixture is stale".
    """
    raw = yaml.safe_load((ROOT / "config" / "personas" / "flagship.yml").read_text(encoding="utf-8"))
    return copy.deepcopy(raw)


# ---------------------------------------------------------------------------
# 1. The committed specs load
# ---------------------------------------------------------------------------

def test_all_eighteen_specs_load(specs):
    assert set(specs) == set(_ALL_IDS), f"unexpected spec id set: {sorted(specs)}"
    assert len(specs) == 18


def test_base_spec_fixture_is_valid():
    assert P.validate_spec(_base_spec(), expect_id="flagship") == []


def test_check_cli_is_green_on_the_committed_tree():
    """The exact command CI runs, run the way CI runs it."""
    proc = subprocess.run(
        [sys.executable, "-m", "engine.marketing.personas", "--check"],
        cwd=str(ROOT), capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "18 checked, 0 invalid" in proc.stdout
    assert P.check(ROOT) == {}


def test_check_cli_exits_1_on_a_bad_spec(tmp_path):
    good = _base_spec()
    bad = _base_spec()
    bad["id"] = "broken"
    bad["memory"] = "data/marketing/personas/broken/theses.jsonl"
    bad["tilt"].pop("chart")
    spec_dir = tmp_path / "config" / "personas"
    spec_dir.mkdir(parents=True)
    (spec_dir / "flagship.yml").write_text(yaml.safe_dump(good), encoding="utf-8")
    (spec_dir / "broken.yml").write_text(yaml.safe_dump(bad), encoding="utf-8")

    assert P.main(["--check", "--root", str(tmp_path)]) == 1
    failures = P.check(tmp_path)
    assert set(failures) == {str(Path("config/personas/broken.yml"))}


def test_check_cli_exits_1_when_the_spec_dir_is_absent(tmp_path):
    assert P.main(["--check", "--root", str(tmp_path)]) == 1


def test_check_cli_annotates_up_to_five_errors_per_file(tmp_path, capsys):
    """Annotations must START their line (a logger prefix makes GitHub drop them),
    and one line per file would hide the rest of a multi-fault spec."""
    bad = _base_spec()
    bad["persona_kind"] = "mascot"
    bad["pipeline"] = "telepathy"
    bad["model_tier"] = "haiku"
    bad["voice"] = "gravelly narrator"
    bad["archetype"] = ""
    bad["beat"] = ""
    bad["cadence"]["weekend_shape"] = "heavy"
    spec_dir = tmp_path / "config" / "personas"
    spec_dir.mkdir(parents=True)
    (spec_dir / "flagship.yml").write_text(yaml.safe_dump(bad), encoding="utf-8")

    assert len(P.check(tmp_path)[str(Path("config/personas/flagship.yml"))]) > 5
    assert P.main(["--check", "--root", str(tmp_path)]) == 1

    annotations = [ln for ln in capsys.readouterr().out.splitlines() if ln.startswith("::")]
    assert len(annotations) == P._MAX_ANNOTATIONS_PER_FILE + 1  # + the "and N more" line
    assert all(ln.startswith("::error file=config/personas/flagship.yml,") for ln in annotations)
    assert "more error(s)" in annotations[-1]


def test_load_all_raises_on_an_invalid_spec(tmp_path):
    bad = _base_spec()
    bad["pipeline"] = "telepathy"
    spec_dir = tmp_path / "config" / "personas"
    spec_dir.mkdir(parents=True)
    (spec_dir / "flagship.yml").write_text(yaml.safe_dump(bad), encoding="utf-8")
    with pytest.raises(P.PersonaSpecError):
        P.load_all(tmp_path)


def test_load_all_on_an_absent_dir_is_empty_not_fatal(tmp_path):
    assert P.load_all(tmp_path) == {}


# ---------------------------------------------------------------------------
# 2. Rejection classes — one test per class the brief names
# ---------------------------------------------------------------------------

def _errors_after(mutate) -> list[str]:
    raw = _base_spec()
    mutate(raw)
    return P.validate_spec(raw, expect_id="flagship")


def _assert_rejected(mutate, needle: str):
    errors = _errors_after(mutate)
    assert errors, f"expected a rejection mentioning {needle!r}, got none"
    joined = " | ".join(errors)
    assert needle in joined, f"expected {needle!r} in errors, got: {joined}"


def test_reject_missing_voice():
    _assert_rejected(lambda r: r.pop("voice"), "missing key(s) ['voice']")


def test_reject_empty_voice():
    _assert_rejected(lambda r: r.update(voice=""), "voice")


def test_reject_unknown_voice_key():
    _assert_rejected(lambda r: r.update(voice="gravelly narrator"),
                     "not a live template-pool voice key")


def test_reject_tilt_missing_key():
    """A partial tilt inherits _DEFAULT_TILT at consumption — omit != disable."""
    _assert_rejected(lambda r: r["tilt"].pop("watchlist"), "missing content type(s)")


def test_reject_tilt_extra_key():
    _assert_rejected(lambda r: r["tilt"].update(podcast=0.0), "unknown content type(s)")


def test_reject_tilt_sum_not_one():
    _assert_rejected(lambda r: r["tilt"].update(signal=0.50), "sum to")


def test_reject_signal_not_max():
    def mutate(r):
        r["tilt"].update(signal=0.30, chart=0.32, mover=0.10, theme_list=0.09,
                         receipt=0.08, event=0.06, education=0.05, macro=0.05,
                         watchlist=0.05)
    _assert_rejected(mutate, "must be strictly the largest weight")


def test_reject_signal_ties_the_max():
    """Strictly the max: an exact tie is a rejection, not a pass."""
    def mutate(r):
        r["tilt"].update(signal=0.30, chart=0.30, mover=0.10, theme_list=0.08,
                         receipt=0.07, event=0.05, education=0.04, macro=0.03,
                         watchlist=0.03)
    _assert_rejected(mutate, "must be strictly the largest weight")


def test_reject_signal_below_the_floor():
    def mutate(r):
        r["tilt"].update(signal=0.20, chart=0.15, mover=0.15, theme_list=0.12,
                         receipt=0.10, event=0.08, education=0.08, macro=0.07,
                         watchlist=0.05)
    _assert_rejected(mutate, f"below the {P.SIGNAL_TILT_FLOOR} floor")


def test_reject_bad_persona_kind():
    _assert_rejected(lambda r: r.update(persona_kind="mascot"), "persona_kind")


def test_reject_bad_pipeline():
    _assert_rejected(lambda r: r.update(pipeline="telepathy"), "pipeline")


def test_reject_bad_model_tier():
    _assert_rejected(lambda r: r.update(model_tier="haiku"), "model_tier")


def test_reject_bad_emoji_policy():
    _assert_rejected(lambda r: r["voice_codex"].update(emoji_policy="lots"),
                     "voice_codex.emoji_policy")


@pytest.mark.parametrize("field,value", [
    ("posts_per_day", 0),
    ("posts_per_day", -1),
    ("min_spacing_min", 0),
    ("min_spacing_min", -30),
    ("jitter_min", -1),
])
def test_reject_non_positive_cadence(field, value):
    _assert_rejected(lambda r: r["cadence"].update({field: value}), f"cadence.{field}")


def test_reject_boolean_cadence_int():
    """bool is an int in Python; posts_per_day: true must not read as 1."""
    _assert_rejected(lambda r: r["cadence"].update(posts_per_day=True),
                     "cadence.posts_per_day")


def test_reject_bad_weekend_shape():
    _assert_rejected(lambda r: r["cadence"].update(weekend_shape="heavy"),
                     "cadence.weekend_shape")


def test_reject_unknown_top_level_key():
    _assert_rejected(lambda r: r.update(handle="@somebody"), "unknown key(s)")


def test_reject_id_that_does_not_match_the_filename():
    _assert_rejected(lambda r: r.update(id="not_flagship"), "does not match the file name")


def test_reject_memory_path_for_another_persona():
    """Two personas sharing one thesis ledger is a data-corruption class (§0)."""
    _assert_rejected(lambda r: r.update(memory="data/marketing/personas/receipts/theses.jsonl"),
                     "memory")


def test_reject_missing_am_r1_banned_pattern():
    """Masterplan §1: the fabricated-claim ban is a validator rule, not prose."""
    _assert_rejected(lambda r: r["voice_codex"]["banned_patterns"].remove(
        "first-person trade/position/P&L claims"), "AM-R1 hard lines")


def test_reject_signature_set_without_a_signature():
    _assert_rejected(lambda r: r["voice_codex"].update(emoji_policy="signature-set",
                                                       emoji_signature=[]),
                     "emoji_signature")


def test_reject_missing_isolation_slot():
    _assert_rejected(lambda r: r["isolation"].pop("egress"), "isolation")


def test_reject_unknown_chronicle_pack():
    _assert_rejected(lambda r: r["context_packs"].update(chronicle=["yesterday"]),
                     "context_packs.chronicle")


def test_reject_bad_scorecard_rate():
    _assert_rejected(lambda r: r["scorecard"]["promote_after"].update(
        engagement_rate_ci_lower_above=1.5), "engagement_rate_ci_lower_above")


def test_reject_non_mapping_spec():
    assert P.validate_spec(["not", "a", "mapping"])


# ---------------------------------------------------------------------------
# 3. The control arm is pinned to the engine default
# ---------------------------------------------------------------------------

def test_control_v3_tilt_is_exactly_the_engine_default(specs):
    """If _DEFAULT_TILT moves, the control arm must go red, not drift."""
    from engine.marketing.content_studio import _DEFAULT_TILT

    assert specs["control_v3"].tilt == _DEFAULT_TILT
    assert specs["control_v3"].pipeline == "engine"


def test_control_v3_voice_is_the_engine_lane_default(specs):
    """content_studio._get_copy's fallback voice IS the engine lane's default."""
    from engine.marketing.content_studio import _COPY_TEMPLATES, _get_copy

    default_voice = specs["control_v3"].voice
    assert _get_copy("signal", "no such voice") == _COPY_TEMPLATES[("signal", default_voice)]


def test_tilt_key_set_is_read_from_content_studio_not_copied():
    from engine.marketing.content_studio import CONTENT_TYPES

    assert P.content_type_ids() == tuple(t["id"] for t in CONTENT_TYPES)
    assert len(P.content_type_ids()) == 9


# ---------------------------------------------------------------------------
# 4. The desk-derived specs agree with config/marketing.yml
# ---------------------------------------------------------------------------

_KIND_MAP = {"branded": "branded", "generic": "specialist", "employee": "employee"}


def _desk_accounts(cfg: dict) -> dict:
    return {a["id"]: a for a in cfg["desk_network"]["accounts"]}


@pytest.mark.parametrize("acct_id", _DERIVED_IDS)
def test_derived_spec_matches_config(acct_id, specs, marketing_cfg):
    """The spec derives FROM config — so a config edit without a spec edit fails."""
    from engine.marketing.content_studio import _DEFAULT_TILT

    acct = _desk_accounts(marketing_cfg)[acct_id]
    spec = specs[acct_id]

    assert spec.voice == acct["voice"]
    assert spec.beat == acct["beat"]
    assert spec.persona_kind == _KIND_MAP[acct["kind"]]

    effective = dict(_DEFAULT_TILT)
    effective.update({k: float(v) for k, v in (acct.get("tilt") or {}).items()
                      if k in _DEFAULT_TILT})
    assert spec.tilt == effective
    # The equivalence above is only "verbatim" while the config tilt is complete
    # and already normalised; pin that so a partial config tilt is not silently
    # absorbed into a passing assertion.
    assert abs(sum(effective.values()) - 1.0) <= P.TILT_SUM_TOL


def test_every_desk_network_account_has_a_spec(specs, marketing_cfg):
    """W1 allows an account without a spec; today none exists, and we pin that.
    (13 desks since 2026-07-28: the W1 six, the founder's personal account, the
    four employee desks, and the two wired-but-dark publication properties.)"""
    wired = set(_DERIVED_IDS) | set(_WIRED_DARK_IDS)
    assert set(_desk_accounts(marketing_cfg)) == wired
    assert wired <= set(specs)


def test_authored_specs_are_spec_only(specs, marketing_cfg):
    """No W1 spec creates an account: the authored ids are NOT in desk_network."""
    accounts = set(_desk_accounts(marketing_cfg))
    assert accounts.isdisjoint(_AUTHORED_IDS)


#: "Emoji budget: 0", "Emoji budget: 0-1 (a rare 📌 or 👀)", "Emoji budget: 1 (🧾)"
_EMOJI_BUDGET_RE = re.compile(r"Emoji\s+budget:\s*(\d)(?:\s*-\s*(\d))?([^.]*)", re.IGNORECASE)
#: Pictographs only — the parenthetical names the persona's signature glyphs.
_EMOJI_CHAR_RE = re.compile(r"[\U0001F300-\U0001FAFF☀-➿]")
#: Variation selectors and ZWJ.  The probe above matches the BASE codepoint only,
#: so "☕️" (U+2615 U+FE0F) is extracted as "☕" while the codex declares the full
#: sequence.  Comparing raw would make every signature containing U+FE0F — Meagan's
#: ☕️ and Sophia's 🖋️ — fail on a difference that is invisible and meaningless.
#: Both sides are normalised instead; a genuinely different GLYPH still fails.
_EMOJI_MODIFIERS = "️‍⃣"


def _bare_glyphs(glyphs) -> list[str]:
    return ["".join(c for c in g if c not in _EMOJI_MODIFIERS) for g in glyphs]


@pytest.mark.parametrize("acct_id", _DERIVED_IDS)
def test_derived_codex_emoji_matches_the_copywriter_block(acct_id, specs, marketing_cfg):
    """The codex is an OVERLAY on copywriter.personas — it may not contradict it.

    copywriter.personas.<id>.voice_notes carries the shipped "Emoji budget:" line
    and, where one exists, the signature glyph set. W2 deletes that block and the
    codex becomes canonical; a silent disagreement now would be inherited then, so
    the agreement is asserted mechanically rather than eyeballed once.
    """
    voice_notes = marketing_cfg["copywriter"]["personas"][acct_id]["voice_notes"]
    match = _EMOJI_BUDGET_RE.search(voice_notes)
    assert match, f"{acct_id}: copywriter.personas voice_notes has no 'Emoji budget:' line"

    lo, hi, tail = match.group(1), match.group(2), match.group(3)
    max_budget = int(hi if hi else lo)
    named = _EMOJI_CHAR_RE.findall(tail)

    codex = specs[acct_id].voice_codex
    policy = codex["emoji_policy"]
    signature = codex.get("emoji_signature")

    if max_budget == 0:
        assert policy == "none", f"{acct_id}: budget 0 but emoji_policy {policy!r}"
        assert not signature, f"{acct_id}: budget 0 but signature {signature!r}"
    else:
        assert policy in ("sparse", "signature-set"), \
            f"{acct_id}: budget {max_budget} but emoji_policy {policy!r}"

    if named:
        assert signature is not None, \
            f"{acct_id}: copywriter names {named} but the codex declares no emoji_signature"
        assert _bare_glyphs(signature) == _bare_glyphs(named), \
            f"{acct_id}: codex signature {list(signature)} != copywriter's {named}"
    else:
        assert signature is None, \
            f"{acct_id}: codex declares {signature!r} but copywriter names no glyphs"


def test_the_emoji_budget_probe_actually_finds_every_desk_line(marketing_cfg):
    """Guard the guard: a voice_notes rewording that drops the budget line would
    otherwise make the drift test vacuous for that desk."""
    found = {i for i in _DERIVED_IDS
             if _EMOJI_BUDGET_RE.search(marketing_cfg["copywriter"]["personas"][i]["voice_notes"])}
    assert found == set(_DERIVED_IDS)
    # At least one desk must name explicit glyphs, or the signature half is vacuous.
    named = [i for i in _DERIVED_IDS
             if _EMOJI_CHAR_RE.findall(
                 _EMOJI_BUDGET_RE.search(
                     marketing_cfg["copywriter"]["personas"][i]["voice_notes"]).group(3))]
    assert named, "no desk names signature glyphs — the signature assertion is vacuous"


def test_every_spec_memory_path_follows_the_ledger_pattern(specs):
    for spec_id, spec in specs.items():
        assert spec.memory == P.MEMORY_PATH_TEMPLATE.format(id=spec_id)


def test_scorecard_gates_are_identical_across_arms(specs):
    """Identical RAW thresholds across arms are a PREREQUISITE for the W4
    correction, not the correction itself. Nothing at W1 adjusts for
    multiplicity — the W4 grading engine does that, and it can only do it
    cleanly if every arm was pre-registered against the same raw gate."""
    gates = {(s.scorecard["min_impressions"],
              s.scorecard["promote_after"]["weeks"],
              s.scorecard["promote_after"]["engagement_rate_ci_lower_above"],
              s.scorecard["kill_after"]["weeks"],
              s.scorecard["kill_after"]["engagement_rate_ci_upper_below"])
             for s in specs.values()}
    assert gates == {(20000, 4, 0.015, 8, 0.005)}


def test_alpha_note_does_not_claim_machinery_w1_lacks(specs):
    """W1 computes no correction and knows no arm size — the note must say so."""
    expected = (
        "pre-registered thresholds; the W4 grading engine applies the multiplicity "
        "correction (Bonferroni across live arms) and prints arm size/power on the "
        "report card; two looks (4w promote / 8w kill); no lane grades itself"
    )
    assert {s.scorecard["alpha_note"] for s in specs.values()} == {expected}


def test_the_zh_personas_are_exactly_zh_navigator_and_cici(specs):
    """Cici is the one BILINGUAL employee desk (XG-W1); zh_navigator (D13) stays
    spec-only. Two zh specs is the expected state, not a duplicate — pin it so a
    third appears deliberately."""
    zh = {i for i, s in specs.items() if s.voice_codex["zh"]}
    assert zh == {"zh_navigator", "cici"}


# ---------------------------------------------------------------------------
# 5. Zero side effects on the generation modules
# ---------------------------------------------------------------------------

def test_importing_personas_does_not_mutate_content_studio_or_copywriter():
    from engine.marketing import content_studio as cs
    from engine.marketing import copywriter as cw

    before = (
        copy.deepcopy(cs._DEFAULT_TILT),
        copy.deepcopy(cs.CONTENT_TYPES),
        dict(cs._COPY_TEMPLATES),
        set(cw._BANNED_VOCAB),
        tuple(cw._BANNED_SUBSTRINGS),
    )

    import importlib
    importlib.reload(P)
    P.load_all(ROOT)

    after = (
        cs._DEFAULT_TILT,
        cs.CONTENT_TYPES,
        dict(cs._COPY_TEMPLATES),
        set(cw._BANNED_VOCAB),
        tuple(cw._BANNED_SUBSTRINGS),
    )
    assert before == after


def test_importing_personas_does_not_import_content_studio():
    """The type-id read is LAZY — the module stays cheap for minimal-deps lanes."""
    probe = (
        "import sys; import engine.marketing.personas; "
        "print(int('engine.marketing.content_studio' in sys.modules), "
        "int('engine.marketing.copywriter' in sys.modules), "
        "int('pandas' in sys.modules))"
    )
    proc = subprocess.run([sys.executable, "-c", probe], cwd=str(ROOT),
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "0 0 0", proc.stdout


#: Does a source file reach the persona spec layer?
#:
#: A substring scan for "config/personas" alone misses every import form, which
#: is how a spec would actually reach a generation path. The alternatives below
#: are anchored to real import SYNTAX (line-initial from/import, the parenthesised
#: continuation idiom admin/server.py uses, importlib) rather than to the bare
#: word, because ``copywriter.personas`` is a legitimate CONFIG BLOCK that half
#: the marketing engine names in prose and in ``cfg.get("personas", ...)``.
#: Those must never trip — see test_spec_reference_predicate_ignores_the_config_block.
_SPEC_REF_RE = re.compile(
    r"config/personas"                                              # dir read, any form
    r"|^[ \t]*from[ \t]+[\w\.]*\bpersonas\b"                        # from .personas import X
    r"|^[ \t]*from[ \t]+[\w\.]+[ \t]+import\b[^\n]*\bpersonas\b"    # from . import personas
    r"|^[ \t]*import[ \t]+[\w\.]*\bpersonas\b"                      # import ...personas [as P]
    r"|import_module\([^)]*personas"                                # importlib indirection
    r"|^[ \t]*personas[,)]"                                         # from . import (\n personas,\n)
    # Path("config") / "personas" — BOTH forms, deliberately (review F16).
    #
    # The config-anchored alternative catches the literal idiom. The BROAD one
    # after it catches the VARIABLE-TARGET case — `base = Path("config"); ... base
    # / "personas"` — which the anchored form is blind to, and variable-target
    # blindness is a known house trap (`source-guard-regex-blind-to-variable-
    # target`). Narrowing to the anchored form ALONE, as the first XG-W3 cut did,
    # traded one false positive for that whole blind spot.
    #
    # The false positive it was avoiding (the XG-W3 persona MEMORY ledger at
    # `data/marketing/personas/`, which holds emitted-post counters and is not a
    # spec) is excluded in `_references_persona_specs` by LINE CONTEXT instead —
    # a match whose own line names the data tree is a ledger reference, not a
    # spec read. That keeps the broad pattern's coverage and still tells the two
    # trees apart.
    r"|config['\"]?[ \t]*\)?[ \t]*/[ \t]*['\"]personas['\"]"
    r"|/[ \t]*['\"]personas['\"]",
    re.MULTILINE,
)

#: A matched line that names the DATA tree is the XG-W3 memory ledger, not the
#: spec dir. Kept as an explicit, greppable exclusion rather than lookbehind
#: gymnastics (Python `re` has no variable-length lookbehind anyway).
_LEDGER_LINE_RE = re.compile(r"\bmarketing\b|\bdata\b", re.I)

#: The three files W1 permits to reach the spec layer: the loader, the read-only
#: roster panel, and the one route registration that serves it.
_SPEC_CONSUMERS_ALLOWED = {
    "engine/marketing/personas.py", "admin/personas.py", "admin/server.py",
    # XG-W1 opened exactly ONE generation-side seam. A spec layer nothing reads
    # is decorative, and the expression dial has to be enforceable, so this
    # module (and ONLY this module) resolves voice_codex at copy time. The copy
    # layer calls expression_dial, never personas — which is why copywriter.py
    # and content_studio.py must still be absent from this set.
    "engine/marketing/expression_dial.py",
    # XG-W2 opened the SECOND, and for the same reason: the specs' `cadence:`
    # blocks were decorative until something read them, and a per-account
    # posting law cannot be enforced from a layer nothing reads. This module
    # (and ONLY this module) resolves cadence at POST time. The publisher calls
    # cadence_resolver, never personas — which is why scripts/
    # marketing_publisher.py must still be absent from this set.
    "engine/marketing/cadence_resolver.py",
    # ── XG-W3 (charter §4 + §6 XG-W3 row) — THE ADJUDICATED WIDENING ─────────
    # This wave is the adjudication this fence was waiting for. Charter §4 is
    # explicit: "Every generation call receives: context packs ..., persona
    # memory ..., and the codex", and config/marketing.yml's own note says
    # "TRUE quirk INJECTION (franchise-shaped generation from persona memory)
    # lands with XG-W3 desk feeds". Until now the codex was SUBTRACTIVE — the
    # dial could strip a quirk it was never granted but nothing wrote a
    # persona's worldview INTO the prompt, which is why two desks sharing a
    # voice landed near-identical copy on the deterministic floor.
    #
    # What each of the three reads, and nothing more:
    #   franchises.py  cross-checks the register against the specs' `franchises:`
    #                  prose (spec_drift) so a code register cannot drift from
    #                  its YAML source of record.
    #   desk_feed.py   reads `worldview`/`franchises`/`restraint`/`context_packs`
    #                  /`cadence.session` to build the per-account context pack.
    #   copywriter.py  grafts the COGNITIVE layers onto the LLM persona cards.
    #                  The `canon` (lifestyle texture) is deliberately NOT read —
    #                  it ships dark under charter §2 amendment 8 until each real
    #                  employee confirms it, and handing it to a model is exactly
    #                  the fabricated-personal-texture failure AM-R1 prevents.
    #
    # content_studio.py must still be ABSENT from this set: it reaches voice
    # through copywriter, never through the spec layer directly.
    "engine/marketing/franchises.py",
    "engine/marketing/desk_feed.py",
    "engine/marketing/copywriter.py",
}


def _references_persona_specs(blob: str) -> bool:
    """Does this source read the persona SPEC layer (`config/personas/`)?

    A match whose own line names the data tree is the XG-W3 memory LEDGER
    (`data/marketing/personas/`) — emitted-post counters, not specs — so it does
    not count. An explicit `config/personas` match always counts, whatever else
    is on the line.
    """
    for m in _SPEC_REF_RE.finditer(blob):
        hit = m.group(0)
        # An IMPORT of the personas module is a spec read, full stop — the word
        # "marketing" appearing in `from engine.marketing import personas` says
        # nothing about the data tree. Same for an explicit `config` anchor.
        if ("import" in hit) or ("from" in hit) or ("config" in hit):
            return True
        # Only the BARE path form (`… / "personas"`) is ambiguous between the
        # spec dir and the XG-W3 memory ledger; that one is judged on its line.
        line_start = blob.rfind("\n", 0, m.start()) + 1
        line_end = blob.find("\n", m.end())
        line = blob[line_start : line_end if line_end != -1 else len(blob)]
        if not _LEDGER_LINE_RE.search(line):
            return True
    return False


@pytest.mark.parametrize("snippet", [
    "from . import personas",
    "from .personas import load_all",
    "import engine.marketing.personas",
    "import engine.marketing.personas as P",
    "importlib.import_module('engine.marketing.personas')",
    "from admin import personas",
    "Path('config') / 'personas'",
    'Path("config") / "personas"',
    "from engine.marketing import personas as _personas",
    "from . import (actions,\n               personas,\n               prophet)",
    "spec_dir = root / 'config/personas'",
    # VARIABLE TARGET (review F16) — the anchored-only form was blind to this.
    "spec_dir = base / 'personas'",
    'spec_dir = cfg_root / "personas"',
])
def test_spec_reference_predicate_catches_every_consumption_form(snippet):
    """Guard the guard: a substring scan for 'config/personas' misses all of these."""
    assert _references_persona_specs(snippet), f"predicate missed: {snippet!r}"


@pytest.mark.parametrize("snippet", [
    'personas_cfg = cfg.get("personas", {}) or {}',
    "    persona: persona card from marketing.yml copywriter.personas.<id>",
    '    then by voice, from cfg copywriter.personas."""',
    "for k, v in personas_cfg.items() if k in used_accounts",
    'if path == "/api/personas/roster":',
    "    voice_notes from the copywriter personas block",
    # The XG-W3 persona MEMORY ledgers live under data/marketing/personas/ —
    # emitted-post counters, not specs. Reading that tree is not a spec read.
    'return _root_path(root) / "data" / "marketing" / "personas" / str(account)',
    "base = root / 'data' / 'marketing' / 'personas'",
    # XG-W4 reads the same tree for the opinion ledger and relationship context.
    'path = base / "data" / "marketing" / "personas" / account / "theses.jsonl"',
    "path = base / 'data' / 'marketing' / 'personas' / acct / 'relations.jsonl'",
])
def test_spec_reference_predicate_ignores_the_config_block(snippet):
    """copywriter.personas is a CONFIG BLOCK, not this module — it must not trip."""
    assert not _references_persona_specs(snippet), f"false positive: {snippet!r}"


def test_the_ledger_line_exemption_does_not_hide_a_real_spec_read():
    """Guard the guard: judging the ambiguous path form line-by-line must not
    let a genuine spec read through elsewhere in the same file."""
    blob = (
        'mem = base / "data" / "marketing" / "personas" / acct / "theses.jsonl"\n'
        'specs = root / "config" / "personas"\n'
    )
    assert _references_persona_specs(blob)


def test_no_generation_module_reads_a_persona_spec():
    """The spec layer has exactly four readers, and that is a fence, not a policy.

    Persona-Network W1 shipped with three (loader, roster panel, its route).
    XG-W1 added the fourth — engine/marketing/expression_dial.py — because the
    employee expression dial cannot be enforced from a layer nothing reads.
    Anything ELSE appearing here means a spec reached a generation path without
    an adjudication.
    """
    hits = []
    for directory in ("engine", "scripts", "app", "admin", "collectors", "lib"):
        for path in (ROOT / directory).rglob("*.py"):
            rel = str(path.relative_to(ROOT))
            if rel in _SPEC_CONSUMERS_ALLOWED:
                continue
            try:
                blob = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if _references_persona_specs(blob):
                hits.append(rel)
    assert hits == [], f"a non-overlay module reads persona specs: {hits}"


def test_every_allowed_consumer_actually_references_the_spec_layer():
    """A stale allow-list entry would silently widen the guard."""
    for rel in sorted(_SPEC_CONSUMERS_ALLOWED):
        blob = (ROOT / rel).read_text(encoding="utf-8")
        assert _references_persona_specs(blob), f"{rel} no longer touches specs — drop it"


# ---------------------------------------------------------------------------
# 6. _get_copy never falls back for a configured persona
# ---------------------------------------------------------------------------

def test_get_copy_never_falls_back_for_a_configured_persona(specs):
    """Test the ACTUAL join _get_copy uses, not a re-derived one."""
    from engine.marketing.content_studio import _COPY_TEMPLATES, _get_copy

    voiced = P.voiced_type_ids()
    assert voiced, "the copy template pool is empty — the join test would be vacuous"

    for spec_id, spec in specs.items():
        for type_id in sorted(voiced):
            key = (type_id, spec.voice)
            assert key in _COPY_TEMPLATES, f"{spec_id}: no template for {key}"
            assert _get_copy(type_id, spec.voice) == _COPY_TEMPLATES[key]


def test_the_no_fallback_carve_out_is_exactly_mover_and_theme_list():
    """mover/theme_list have NO voice-keyed template for ANY voice — including the
    six shipped desks. If that ever stops being true the carve-out must shrink,
    so pin it rather than letting the join test quietly narrow."""
    from engine.marketing.content_studio import _COPY_TEMPLATES

    unvoiced = set(P.content_type_ids()) - P.voiced_type_ids()
    assert unvoiced == {"mover", "theme_list"}
    for voice in P.live_voice_keys():
        for type_id in unvoiced:
            assert (type_id, voice) not in _COPY_TEMPLATES


def test_every_live_voice_covers_every_voiced_type():
    from engine.marketing.content_studio import _COPY_TEMPLATES

    for voice in P.live_voice_keys():
        missing = [t for t in P.voiced_type_ids() if (t, voice) not in _COPY_TEMPLATES]
        assert missing == [], f"voice {voice!r} is missing {missing}"


# ---------------------------------------------------------------------------
# 7. Admin roster panel
# ---------------------------------------------------------------------------

def test_roster_renders_with_the_committed_specs():
    from admin import personas as panel

    d = panel.roster(root=ROOT)
    assert d["ok"] is True
    assert d["counts"]["total"] == 18
    assert d["counts"]["invalid"] == 0
    # LIVE = flagship + founder + the four employee desks + mastermind_news,
    # ARMED 2026-08-02 (masterplan §8.2 W4f — the publication wire's desk_network
    # entry flipped to enabled: true with an explicit created: date).
    assert d["counts"]["live"] == 7
    # CONFIGURED = the five planned W1 desks + the one remaining wired-but-dark
    # publication property (mastermind_research, which additionally has no handle
    # and no Buffer channel — W2R / XG-W8).  `configured` here is the roster's
    # word for "has a desk_network entry but is not live".
    assert d["counts"]["configured"] == 6
    assert d["counts"]["planned"] == 5

    by_id = {r["id"]: r for r in d["personas"]}
    assert set(by_id) == set(_ALL_IDS)
    for spec_id in _AUTHORED_IDS:
        assert by_id[spec_id]["status"] == "PLANNED"
        assert by_id[spec_id]["provisioned"] is False
    assert by_id["flagship"]["status"] == "LIVE"
    assert by_id["founder"]["status"] == "LIVE"
    assert by_id["receipts"]["status"] == "CONFIGURED"
    for spec_id in _EMPLOYEE_IDS:
        assert by_id[spec_id]["status"] == "LIVE"
        assert by_id[spec_id]["persona_kind"] == "employee"
    # Channel bound AND armed 2026-08-02 (W4f) — the XG-W2 cadence resolver it
    # was waiting on armed 2026-07-28.  mastermind_research is the last
    # wired-but-dark publication property (no handle, no channel).
    assert by_id["mastermind_news"]["status"] == "LIVE"
    assert by_id["mastermind_research"]["status"] == "CONFIGURED"


def test_roster_cadence_and_isolation_labels():
    from admin import personas as panel

    by_id = {r["id"]: r for r in panel.roster(root=ROOT)["personas"]}
    assert by_id["corp_desk"]["cadence_label"] == "3/d · 110m+~20m · wknd light"
    iso = by_id["corp_desk"]["isolation"]
    assert iso["label"] == "0/6"
    assert iso["total"] == 6 and iso["done"] == 0
    # The sixth §2 item has no spec field at W1 — surfaced, not silently dropped.
    unrecordable = [i for i in iso["items"] if i["note"] == "no spec field at W1"]
    assert len(unrecordable) == 1


def test_roster_health_and_arm_size_are_honest_skeletons():
    from admin import personas as panel

    row = panel.roster(root=ROOT)["personas"][0]
    assert row["health"]["state"] == "no data yet"
    assert all(s["value"] is None for s in row["health"]["signals"])
    assert row["scorecard"]["arm_size_label"] == "arm size: n/a until live (W4 report card)"
    assert row["scorecard"]["min_impressions_label"] == "20,000"
    assert row["scorecard"]["promote_label"] == "promote: 4w · ER CI-lower > 1.5%"
    assert row["scorecard"]["kill_label"] == "kill: 8w · ER CI-upper < 0.5%"


def test_roster_is_fail_soft_when_the_spec_dir_is_absent(tmp_path):
    from admin import personas as panel

    d = panel.roster(root=tmp_path)
    assert d["ok"] is True
    assert d["personas"] == []
    assert "config/personas/" in d["note"]
    assert d["counts"]["total"] == 0


def test_roster_is_fail_soft_when_the_spec_dir_is_empty(tmp_path):
    from admin import personas as panel

    (tmp_path / "config" / "personas").mkdir(parents=True)
    d = panel.roster(root=tmp_path)
    assert d["ok"] is True
    assert d["personas"] == []
    assert "empty" in d["note"]


def test_roster_shows_a_bad_spec_as_a_row_not_a_blank_panel(tmp_path):
    from admin import personas as panel

    spec_dir = tmp_path / "config" / "personas"
    spec_dir.mkdir(parents=True)
    good = _base_spec()
    (spec_dir / "flagship.yml").write_text(yaml.safe_dump(good), encoding="utf-8")
    (spec_dir / "broken.yml").write_text("id: broken\n", encoding="utf-8")

    d = panel.roster(root=tmp_path)
    assert d["ok"] is True
    assert d["counts"]["invalid"] == 1
    broken = [r for r in d["personas"] if r["id"] == "broken"][0]
    assert broken["status"] == "INVALID"
    assert broken["errors"]
    assert any(r["id"] == "flagship" and r["ok"] for r in d["personas"])


def test_roster_lists_accounts_that_have_no_spec(tmp_path):
    from admin import personas as panel

    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "marketing.yml").write_text(
        yaml.safe_dump({"desk_network": {"accounts": [
            {"id": "flagship", "enabled": True},
            {"id": "ghost_desk", "enabled": False},
        ]}}), encoding="utf-8")
    spec_dir = tmp_path / "config" / "personas"
    spec_dir.mkdir()
    (spec_dir / "flagship.yml").write_text(yaml.safe_dump(_base_spec()), encoding="utf-8")

    d = panel.roster(root=tmp_path)
    assert d["accounts_without_spec"] == ["ghost_desk"]


def test_roster_never_raises_on_a_hostile_root(tmp_path):
    from admin import personas as panel

    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "marketing.yml").write_text("{[not yaml", encoding="utf-8")
    d = panel.roster(root=tmp_path)
    assert d["ok"] is True
