"""tests/test_marketing_expression_dial.py — the expression dial + codex quirk pass (XG-W1).

Deps: stdlib + pytest + pyyaml only (runs in the ``marketing-engine`` CI lane,
which installs exactly that). No pandas, no numpy — engine/marketing/
expression_dial.py keeps stdlib + personas at module level, and a heavy top-level
import there must turn this suite red at collection. Nothing here is
``importorskip``-gated, so the suite cannot become a silent no-op.

Test list:
  1.  The dial map covers every known kind explicitly; nothing exceeds the ceiling.
  2.  CALIBRATION SET — the four pinned masterplan §5 dial-1 examples pass
      VERBATIM, and a dial-3 fixture is rejected.
  3.  The whitelist binds: one persona may not wear another's signature.
  4.  Dark canon is BANNED, and the loader refuses a spec that switches one on.
  5.  Frequency caps (per-post / per-day / per-7d / share-of-7d).
  6.  AM-R1 detectors fire, key off the pinned prose, and do not false-positive
      on the committed first-person example_lines.
  7.  apply_pass strips only what it may, and is a no-op off the dial.
  8.  DRY RUN — one item per employee through the real copy pipeline with the
      quirk pass ON, zero AM-R1 violations (the XG-W1 §0 acceptance gate).
  9.  Anti-vacuous tripwires: the index is non-empty, every marker is declared by
      someone, and the whole deterministic template bank is dial-clean.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from engine.marketing import expression_dial as ED
from engine.marketing import personas as P


def _worktree_root() -> Path:
    p = Path(__file__).resolve()
    for candidate in [p.parent, p.parent.parent, p.parent.parent.parent]:
        if (candidate / "engine").is_dir():
            return candidate
    raise RuntimeError(f"Could not locate repo root from {p}")


ROOT = _worktree_root()

_EMPLOYEES = ("meagan", "sophia", "kelly", "cici")
#: Every account the dial governs: the four employees plus the founder — the
#: five REAL named humans on official rails.
_DIAL_ACCOUNTS = _EMPLOYEES + ("founder",)

#: THE CALIBRATION SET. Verbatim from
#: research/agentic_media/INTELLIGENCE_SUITE_MASTERPLAN_BY_FABLE.md §5, which
#: pins these as each codex's dial-1 example. They are the frozen fixture the
#: dial is tuned against: if a lexicon edit makes one of them illegal, the edit
#: is wrong, not the example.
#:
#: NOTE the Meagan and Cici lines carry an EM DASH. The dial passes them (that is
#: this gate); the house no-em-dash copy law (copy_laws #2, banned_language())
#: independently rejects the notation, which is why config/marketing.yml carries
#: those two example_lines with house-legal punctuation. Both facts are asserted
#: below rather than left as a surprise for whoever ships the first post.
PINNED_DIAL_1 = {
    "meagan": "okay so the Fed did the thing everyone swore they wouldn't — and the 2-year believed it instantly.",
    "sophia": "Three headlines, one thread: rates, oil, and the dollar spent the afternoon telling the same story.",
    "kelly": "three things the close said. 1) breadth narrowed again 2) oil didn't believe the headline 3) vix still isn't paying attention.",
    "cici": "While New York slept, Beijing did two things: a firmer yuan fix and a quiet OMO drain. One matters more — 先看这个 (start with this one).",
}

#: A dial-3 post: three-plus personality devices stacked on an analysis kind.
#: Exactly what "cannot be too cute or overboard" means in copy.
DIAL_3_FIXTURE = (
    "okay so this tape is WILD! \U0001F680 matcha in hand, tabs everywhere "
    "(honestly obsessed), and the whole desk is just vibes today!"
)


@pytest.fixture(scope="module")
def specs() -> dict:
    return P.load_all(ROOT)


@pytest.fixture(scope="module")
def marketing_cfg() -> dict:
    return yaml.safe_load(
        (ROOT / "config" / "marketing.yml").read_text(encoding="utf-8")) or {}


@pytest.fixture(autouse=True)
def _fresh_cache():
    """The codex index is cached per root; a tmp-root test must not poison it."""
    ED.clear_cache()
    yield
    ED.clear_cache()


def _dial_violations(account: str, text: str, kind: str = "macro", **kw) -> list[str]:
    """Dial-only view: the house vocab guard is a separate law, tested separately."""
    return ED.violations("", text, account=account, kind=kind,
                         include_house_bans=False, **kw)


# ---------------------------------------------------------------------------
# 1. The dial map
# ---------------------------------------------------------------------------

def test_every_known_kind_has_an_explicit_dial():
    """Enumerated, not defaulted.

    UNLISTED_KIND_DIAL exists so an unknown kind cannot crash a nightly, but a
    kind we KNOW about must be adjudicated into PROFILES. Listing them here means
    a new outbox kind (or content type) that nobody dialled turns this red
    instead of silently inheriting a personality budget.
    """
    from engine.marketing.outbox import KINDS

    known = set(KINDS) | set(P.content_type_ids()) | {
        "wire", "news", "breaking", "reply",
    }
    for profile, table in ED.PROFILES.items():
        missing = sorted(known - set(table))
        assert missing == [], f"profile {profile!r} has no dial for {missing}"


def test_no_dial_exceeds_the_ceiling():
    """Masterplan §5: 'Never >2'."""
    for profile, table in ED.PROFILES.items():
        for kind, dial in table.items():
            assert 0 <= dial <= ED.DIAL_CEILING, f"{profile}.{kind} = {dial}"


def test_wire_and_news_are_zero_personality_in_every_profile():
    for profile in ED.PROFILES:
        for kind in ("wire", "news", "breaking", "event"):
            assert ED.dial_for(kind, profile=profile) == 0, f"{profile}/{kind}"


def test_analysis_is_one_and_the_playful_formats_are_two():
    for kind in ("signal", "macro", "education"):
        assert ED.dial_for(kind, profile="employee") == 1
    for kind in ("chart", "watchlist", "receipt"):
        assert ED.dial_for(kind, profile="employee") == 2


def test_reply_is_the_one_kind_the_two_profiles_disagree_on():
    """Charter §2 amendment 3 — replies are persona-forward for the employees,
    and the flagship/founder desks stay evidence desks in someone else's thread."""
    disagree = {
        k for k in ED.PROFILES["employee"]
        if ED.PROFILES["employee"][k] != ED.PROFILES["flagship"].get(k)
    }
    assert disagree == {"reply"}
    assert ED.dial_for("reply", profile="employee") == 2
    assert ED.dial_for("reply", profile="flagship") == 1


def test_unknown_profile_raises_rather_than_defaulting():
    with pytest.raises(KeyError):
        ED.dial_for("macro", profile="mascot")


def test_unlisted_kind_never_lands_on_the_playful_dial():
    assert ED.dial_for("a_kind_nobody_wrote", profile="employee") == ED.UNLISTED_KIND_DIAL
    assert ED.UNLISTED_KIND_DIAL < ED.DIAL_CEILING


# ---------------------------------------------------------------------------
# 2. The calibration set
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("account", sorted(PINNED_DIAL_1))
def test_the_pinned_dial_1_examples_pass_verbatim(account):
    """The frozen fixture. A lexicon edit that fails one of these is the bug."""
    assert _dial_violations(account, PINNED_DIAL_1[account]) == []


@pytest.mark.parametrize("account", sorted(PINNED_DIAL_1))
def test_each_pinned_example_actually_fires_its_signature(account):
    """Guard the guard: four examples that trip NOTHING would pass vacuously."""
    codex = ED.codex_for(account, root=ROOT)
    hits = ED.marker_hits(PINNED_DIAL_1[account], codex=codex)
    assert hits, f"{account}: the pinned example fires no marker at all"
    assert set(hits) <= codex.granted, f"{account}: {sorted(set(hits) - codex.granted)}"


def test_kellys_three_item_list_counts_as_one_device():
    """A list is one quirk, not one per bullet — her pinned example has three."""
    codex = ED.codex_for("kelly", root=ROOT)
    assert ED.marker_hits(PINNED_DIAL_1["kelly"], codex=codex) == {
        "numbered_micro_list": 1}


def test_cicis_zh_gloss_is_not_double_charged_as_an_aside():
    """The English gloss belongs to the zh marker; counting the parenthetical a
    second time would make obeying her own codex cost her the dial twice."""
    codex = ED.codex_for("cici", root=ROOT)
    hits = ED.marker_hits(PINNED_DIAL_1["cici"], codex=codex)
    assert "parenthetical_aside" not in hits
    assert hits == {"zh_gloss": 1, "session_handoff": 1}


def test_precision_markers_are_not_charged_to_the_dial():
    """zh+gloss is beat SUBSTANCE, not seasoning — Cici's dial-1 example carries
    a frame AND a zh phrase and is still a legal dial-1 post."""
    assert ED.MARKERS["zh_gloss"].cls == "precision"
    assert ED.dial_for("macro", profile="employee") == 1
    assert _dial_violations("cici", PINNED_DIAL_1["cici"], kind="macro") == []


def test_the_dial_3_fixture_is_rejected():
    out = _dial_violations("meagan", DIAL_3_FIXTURE, kind="education")
    assert out, "a dial-3 post sailed through the dial"
    blob = " | ".join(out)
    assert "expression dial 1" in blob
    assert "off-signature emoji" in blob


def test_the_dial_3_fixture_is_rejected_even_at_the_top_of_the_dial():
    """'Never >2' is the ceiling, not a loophole: dial 2 still refuses a pile-up."""
    assert _dial_violations("meagan", DIAL_3_FIXTURE, kind="chart") != []


def test_the_pinned_examples_carry_em_dashes_the_house_law_rejects():
    """A pinned example is not automatically a shippable post.

    Two of the four §5 lines contain an em dash, which copy_laws #2 bans at both
    generation and post time. That is why config/marketing.yml carries those two
    example_lines with house-legal punctuation instead. Pinned here so the
    discrepancy is a recorded fact rather than a surprise in the first post.
    """
    from engine.marketing.copywriter import banned_language

    dashed = {a for a, line in PINNED_DIAL_1.items() if banned_language(line)}
    assert dashed == {"meagan", "cici"}


def test_the_shipped_example_lines_are_house_legal(marketing_cfg):
    """The copy the LLM prompt actually shows the model must be postable."""
    from engine.marketing.copywriter import banned_language

    for account in _EMPLOYEES:
        for line in marketing_cfg["copywriter"]["personas"][account]["example_lines"]:
            assert banned_language(line) == [], f"{account}: {line[:60]}"
            assert _dial_violations(account, line) == [], f"{account}: {line[:60]}"


# ---------------------------------------------------------------------------
# 3. The whitelist binds
# ---------------------------------------------------------------------------

def test_a_persona_may_not_wear_another_personas_signature():
    """Kelly opening with Meagan's "okay so" is an unwhitelisted quirk."""
    out = _dial_violations("kelly", "okay so the close said one thing.")
    assert any("unwhitelisted quirk 'okay_so_opener'" in v for v in out), out


def test_the_signature_emoji_of_another_desk_is_off_signature():
    out = _dial_violations("kelly", "breadth narrowed again \U0001F58B️")
    assert any("off-signature emoji" in v for v in out), out


def test_sophia_may_not_carry_an_exclamation_at_any_dial():
    """§5: 'zero exclamations'. Meagan is the only desk granted one."""
    for kind in ("macro", "chart"):
        out = _dial_violations("sophia", "The dollar agreed!", kind=kind)
        assert any("unwhitelisted quirk 'exclamation'" in v for v in out), out
    assert "exclamation" in ED.codex_for("meagan", root=ROOT).granted


def test_the_founders_whitelist_is_deliberately_empty():
    """His register is plainness itself, so any marker firing on him is a defect."""
    codex = ED.codex_for("founder", root=ROOT)
    assert codex is not None, "the founder must be ON the dial (real named human)"
    assert codex.granted == frozenset()
    assert _dial_violations("founder", "okay so I'm watching this level.") != []


def test_an_account_with_no_codex_is_untouched():
    """The six desks that predate the dial keep exactly the bar they had."""
    assert ED.codex_for("receipts", root=ROOT) is None
    assert ED.violations("h", "okay so matcha! \U0001F680", account="receipts",
                         kind="macro", include_house_bans=False) == []
    assert ED.violations("h", "b", account="", kind="macro") == []


def test_untranslated_chinese_is_a_violation_at_every_dial():
    for kind in ("wire", "macro", "chart"):
        out = _dial_violations("cici", "先看这个 and watch the fix.",
                               kind=kind)
        assert any("untranslated Chinese" in v for v in out), (kind, out)


def test_chinese_from_a_non_zh_desk_is_flagged_not_silently_allowed():
    """Precision markers are whitelisted like any other; only the DIAL ignores them."""
    out = _dial_violations("meagan", "the fix landed 先看这个 (look here).")
    assert any("zh_gloss" in v for v in out), out


def test_a_codex_banned_term_is_rejected():
    out = _dial_violations("cici", "China up on the session, nothing else moved.")
    assert any("codex-banned term" in v for v in out), out


def test_codex_banned_terms_are_word_bounded():
    """'wine' must not fire on 'twine'; a substring scan would."""
    assert not any("codex-banned term" in v
                   for v in _dial_violations("sophia", "The twine industry is fine."))
    assert any("codex-banned term" in v
               for v in _dial_violations("sophia", "A wine analogy would be lazy here."))


# ---------------------------------------------------------------------------
# 4. Dark canon
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("account,token", [
    ("meagan", "matcha in hand and the tape is quiet."),
    ("sophia", "a museum-quality chart, honestly."),
    ("kelly", "a marathon, not a sprint, for this breadth read."),
    ("cici", "tea first, then the yuan fix."),
])
def test_canon_lifestyle_tokens_are_banned_not_merely_ungranted(account, token):
    """The AM-R1 blocker: nothing in this repo verifies these people's private
    lives, so unverified personal texture on a real name may not ship."""
    out = _dial_violations(account, token)
    assert any("codex-dark quirk" in v for v in out), out
    assert any("canon dark pending employee confirmation" in v for v in out), out


@pytest.mark.parametrize("account", _EMPLOYEES)
def test_every_employee_declares_its_canon_slots_dark(account, specs):
    codex = ED.codex_for(account, root=ROOT)
    declared_canon = set(codex.declared) & ED.CANON_MARKERS
    assert declared_canon, f"{account}: declares no canon slot at all"
    assert declared_canon <= codex.dark, f"{account}: a canon slot is switched on"
    # And the spec's human-readable canon block is populated even while dark —
    # the texture is DECLARED and not usable, which is the whole point.
    assert specs[account].canon


def test_the_loader_refuses_a_spec_that_switches_a_canon_marker_on(tmp_path):
    raw = yaml.safe_load(
        (ROOT / "config" / "personas" / "meagan.yml").read_text(encoding="utf-8"))
    raw["voice_codex"]["quirk_markers"]["lifestyle_matcha_tabs"]["enabled"] = True
    errors = P.validate_spec(raw, expect_id="meagan")
    assert any("canon markers ship DARK" in e for e in errors), errors


def test_canon_markers_are_exactly_the_lifestyle_slots():
    assert ED.CANON_MARKERS == {
        "lifestyle_matcha_tabs", "lifestyle_museum_wine",
        "lifestyle_running", "lifestyle_tea_travel",
    }


def test_sophias_canon_nouns_are_also_on_her_banned_list(specs):
    """Belt and braces: her own §5.4 voice law forbids art/wine references in
    copy even if the canon is later confirmed, so the nouns are banned outright."""
    banned = {b.lower() for b in specs["sophia"].voice_codex["banned"]}
    assert {"museum", "wine"} <= banned


# ---------------------------------------------------------------------------
# 5. Frequency caps
# ---------------------------------------------------------------------------

def test_per_post_cap_rejects_a_repeated_quirk():
    out = _dial_violations("meagan", "Big move! Bigger move!")
    assert any("max_per_post is 1" in v for v in out), out


def test_per_day_cap_counts_the_days_other_posts():
    codex = ED.codex_for("meagan", root=ROOT)
    recent = [{"text": "okay so the open was quiet.", "date": "2026-07-28"}]
    out = ED.frequency_violations(
        "okay so the close was not.", codex=codex,
        as_of="2026-07-28", recent=recent)
    assert any("max_per_day" in v for v in out), out


def test_a_prior_day_does_not_spend_todays_budget():
    codex = ED.codex_for("meagan", root=ROOT)
    recent = [{"text": "okay so the open was quiet.", "date": "2026-07-27"}]
    out = ED.frequency_violations(
        "okay so the close was not.", codex=codex,
        as_of="2026-07-28", recent=recent)
    assert not any("max_per_day" in v for v in out), out


def test_share_cap_rejects_an_over_used_signature():
    codex = ED.codex_for("meagan", root=ROOT)
    # 4 of the last 7 days already opened this way; 30% of 8 allows 2.
    recent = [{"text": "okay so a thing happened.", "date": f"2026-07-2{d}"}
              for d in (2, 3, 4, 5)]
    recent += [{"text": "a plain post.", "date": f"2026-07-2{d}"} for d in (6, 7)]
    out = ED.frequency_violations(
        "okay so another thing.", codex=codex, as_of="2026-07-28", recent=recent)
    assert any("max_share_7d" in v for v in out), out


def test_the_share_cap_always_grants_a_first_use():
    """A quiet week must never make the first use of a signature illegal."""
    codex = ED.codex_for("meagan", root=ROOT)
    out = ED.frequency_violations(
        "okay so here we are.", codex=codex, as_of="2026-07-28",
        recent=[{"text": "a plain post.", "date": "2026-07-28"}])
    assert not any("max_share_7d" in v for v in out), out


def test_frequency_caps_are_not_evaluated_without_history():
    """Honest state at W1: no rolling store yet, so the cap is skipped rather
    than silently passing on an empty window."""
    codex = ED.codex_for("meagan", root=ROOT)
    assert ED.frequency_violations("okay so.", codex=codex, as_of="2026-07-28",
                                   recent=None) == []
    assert ED.frequency_violations("okay so.", codex=codex, as_of=None,
                                   recent=[{"text": "okay so.", "date": "2026-07-28"}]) == []


def test_a_dark_marker_never_consumes_a_frequency_budget():
    """Dark quirks are rejected outright; they must not also be rate-limited."""
    codex = ED.codex_for("meagan", root=ROOT)
    out = ED.frequency_violations(
        "matcha and tabs.", codex=codex, as_of="2026-07-28",
        recent=[{"text": "matcha again.", "date": "2026-07-28"}])
    assert out == []


@pytest.mark.parametrize("account", _EMPLOYEES)
def test_every_granted_signature_carries_a_frequency_cap(account):
    """A signature with no cap is the anti-sameness discipline turned off."""
    codex = ED.codex_for(account, root=ROOT)
    uncapped = [
        m for m in sorted(codex.granted)
        if m != "signature_emoji"
        and ED.MARKERS[m].cls == "frame"
        and codex.declared[m].max_per_day is None
        and codex.declared[m].max_share_7d is None
    ]
    assert uncapped == [], f"{account}: uncapped signature frame(s) {uncapped}"


# ---------------------------------------------------------------------------
# 6. AM-R1
# ---------------------------------------------------------------------------

def test_the_detector_keys_are_exactly_the_pinned_prose_lines():
    """Rename a pinned line without writing its detector and this goes red,
    instead of a third of the gate quietly disarming."""
    assert set(ED.AM_R1_DETECTORS) == set(P.AM_R1_BANNED_PATTERNS)


@pytest.mark.parametrize("text,expected", [
    ("I bought $NVDA at 118 this morning.", "first-person trade/position/P&L claims"),
    ("my position is underwater but I like it here.", "first-person trade/position/P&L claims"),
    ("I'm long $AAPL into the print.", "first-person trade/position/P&L claims"),
    ("I got stopped out and moved on.", "first-person trade/position/P&L claims"),
    ("I had coffee with a PM who said the same.", "fabricated personal experience"),
    ("I met with Treasury staff last week.", "fabricated personal experience"),
    ("A source at Goldman texted me the number.", "fabricated personal experience"),
    ("This platform changed my life.", "testimonial-style product claims"),
    ("Since I started using it my reads got sharper.", "testimonial-style product claims"),
])
def test_am_r1_fires_on_each_class(text, expected):
    assert expected in ED.am_r1_hits(text), (text, ED.am_r1_hits(text))


@pytest.mark.parametrize("text", [
    # The founder's and flagship's committed register: first person everywhere,
    # and not one of these is an AM-R1 claim.
    "Watched this level hold three times since March. Fourth test today. I don't get braver with each test, just more curious.",
    "We flagged the group Monday. I did nothing. This morning's gap is the tuition for that.",
    "Semis led again, breadth sat it out again. Generals without soldiers. I'm watching the soldiers.",
    "I'm watching for a bottom setup, not catching it yet.",
    "We flagged it at 41.20 and it held.",
])
def test_am_r1_does_not_fire_on_the_house_first_person_register(text):
    assert ED.am_r1_hits(text) == [], text


def test_am_r1_reaches_copy_through_the_dial(marketing_cfg):
    out = _dial_violations("kelly", "I bought the dip at 118 and I'm long it.")
    assert any("AM-R1 violation" in v for v in out), out


@pytest.mark.parametrize("account", _DIAL_ACCOUNTS)
def test_every_committed_example_line_is_am_r1_clean(account, marketing_cfg):
    persona = marketing_cfg["copywriter"]["personas"].get(account)
    if not persona:
        pytest.skip(f"{account} has no copywriter block")
    for line in persona["example_lines"]:
        assert ED.am_r1_hits(line) == [], f"{account}: {line[:60]}"


# ---------------------------------------------------------------------------
# 7. apply_pass
# ---------------------------------------------------------------------------

def test_apply_pass_strips_off_signature_emoji_and_keeps_the_signature():
    hl, bd = ED.apply_pass("Close \U0001F680", "Breadth narrowed \U0001F50D",
                           account="kelly", kind="chart")
    assert "\U0001F680" not in hl
    assert "\U0001F50D" in bd


def test_apply_pass_strips_every_emoji_for_a_none_policy_persona():
    _hl, bd = ED.apply_pass("h", "the level held \U0001F4C8",
                            account="founder", kind="chart")
    assert "\U0001F4C8" not in bd


def test_apply_pass_downgrades_an_ungranted_exclamation():
    _hl, bd = ED.apply_pass("h", "The dollar agreed!", account="sophia", kind="chart")
    assert bd.endswith("agreed.")


def test_apply_pass_leaves_a_granted_exclamation_alone():
    _hl, bd = ED.apply_pass("h", "The dollar agreed!", account="meagan", kind="chart")
    assert bd.endswith("agreed!")


def test_apply_pass_is_a_no_op_off_the_dial():
    pair = ("Close \U0001F680", "Breadth narrowed!")
    assert ED.apply_pass(*pair, account="receipts", kind="chart") == pair


def test_apply_pass_never_rewrites_a_claim():
    """It may delete a glyph and soften a '!'. It may not touch a number, a
    ticker or a word — a validator that reshapes prose is how a post ends up
    claiming something nobody wrote."""
    body = "$NVDA held 118.40 into the close, up 2.1% on the week \U0001F680"
    _hl, out = ED.apply_pass("h", body, account="kelly", kind="chart")
    assert out == "$NVDA held 118.40 into the close, up 2.1% on the week"


# ---------------------------------------------------------------------------
# 8. Dry run through the real copy pipeline (the XG-W1 §0 acceptance gate)
# ---------------------------------------------------------------------------

_DRY_RUN_KINDS = ("macro", "education", "watchlist", "chart")


def _dry_run_posts(account: str, voice: str, kind: str, cfg: dict) -> list[dict]:
    from engine.marketing.copywriter import build_context, write_posts_deterministic

    persona = cfg["copywriter"]["personas"][account]
    item = {"ticker": "NVDA" if kind == "chart" else "", "type": kind,
            "account": account}
    ctx = build_context(item, persona=persona, facts=None)
    ctx["voice"] = voice
    ctx["type"] = kind
    ctx["slot"] = "D1-AM"
    ctx["as_of"] = "2026-07-28"
    return write_posts_deterministic([ctx])


@pytest.mark.parametrize("account", _EMPLOYEES)
def test_one_dry_run_item_per_employee_renders_clean(account, marketing_cfg):
    """The §0 gate: one item per employee through the real pipeline with the
    quirk pass ON, zero AM-R1 violations. No network, no LLM — the deterministic
    floor is the path under test."""
    voice = {a["id"]: a["voice"]
             for a in marketing_cfg["desk_network"]["accounts"]}[account]

    for kind in _DRY_RUN_KINDS:
        posts = _dry_run_posts(account, voice, kind, marketing_cfg)
        assert posts, f"{account}/{kind}: the pipeline produced nothing"
        post = posts[0]
        blob = f"{post['headline']} {post['body']}"
        assert ED.am_r1_hits(blob) == [], f"{account}/{kind}: {blob[:80]}"
        dial = [v for v in post["violations"]
                if "quirk" in v or "expression dial" in v or "AM-R1" in v
                or "off-signature" in v]
        assert dial == [], f"{account}/{kind}: {dial}"


@pytest.mark.parametrize("account", _EMPLOYEES)
def test_the_dry_run_actually_produced_copy(account, marketing_cfg):
    """Guard the guard: empty copy would pass every assertion above."""
    voice = {a["id"]: a["voice"]
             for a in marketing_cfg["desk_network"]["accounts"]}[account]
    posts = _dry_run_posts(account, voice, "macro", marketing_cfg)
    assert len(posts[0]["headline"].strip()) > 8
    assert len(posts[0]["body"].strip()) > 20


def test_the_whole_deterministic_bank_is_dial_clean_for_every_codex_account():
    """The template bank must not violate the dial it now runs under.

    Every (type, voice) variant for every voice a dial account uses, RENDERED and
    then checked against that account's codex. A template that trips the dial
    would silently demote a live account's copy to a fallback every night.

    Rendering is load-bearing, not cosmetic: the raw templates carry "({gain})"
    and "({loss})" placeholders which look like prose parentheticals until the
    numbers land in them. Sweeping raw strings would flag a receipt template that
    ships perfectly legal copy — the first run of this test did exactly that.
    """
    from engine.marketing.copywriter import (
        _RECEIPT_VOICE_PENDING, _TEMPLATES, _render_template, build_context,
    )

    cfg = yaml.safe_load(
        (ROOT / "config" / "marketing.yml").read_text(encoding="utf-8"))
    voices = {a["id"]: a.get("voice", "") for a in cfg["desk_network"]["accounts"]}

    checked = 0
    cleaned_by_the_pass: list[tuple[str, str]] = []
    for account in _DIAL_ACCOUNTS:
        voice = voices[account]
        for (type_id, tpl_voice), variants in _TEMPLATES.items():
            if tpl_voice != voice:
                continue
            item = {
                "ticker": "NVDA", "type": type_id, "account": account,
                "_plan": {"entry": 118.40, "targets": [126.10, 133.00],
                          "invalidation": 112.75, "direction": "BULL"},
                "_receipt": {"kind": "win", "gain_pct_str": "+9.6%",
                             "loss_pct_str": "-3.1%", "target_label": "T1",
                             "stop": 112.75, "target": 126.10},
                "cashtags": ["$NVDA", "$AMD", "$SMCI", "$AVGO"],
            }
            ctx = build_context(item, persona=None, facts=None)
            ctx.update(voice=voice, type=type_id, slot="D1-AM", as_of="2026-07-28")
            for variant in variants:
                for text in variant[:2]:
                    rendered = _render_template(text, ctx)
                    # Production order: apply_pass THEN validate. Skipping the
                    # pass here would flag the shared "fast, reactive" theme_list
                    # template, whose 👀 is off-signature for Meagan and is
                    # stripped before it ever reaches the validator.
                    cleaned, _ = ED.apply_pass(rendered, "", account=account,
                                               kind=type_id)
                    if cleaned != rendered:
                        cleaned_by_the_pass.append((account, type_id))
                    assert _dial_violations(account, cleaned, kind=type_id) == [], \
                        f"{account} ({voice}) {type_id}: {cleaned[:70]}"
                    checked += 1
        pending = _RECEIPT_VOICE_PENDING.get(voice)
        if pending:
            cleaned, _ = ED.apply_pass(pending, "", account=account, kind="receipt")
            assert _dial_violations(account, cleaned, kind="receipt") == []
    assert checked > 100, f"only {checked} templates checked — the sweep is thin"
    # The pass is not decorative on this bank: the shared voice pools carry
    # glyphs that belong to other desks, and stripping them is what makes an
    # employee's copy legal. If this ever empties, the pass stopped doing work.
    assert cleaned_by_the_pass, "the quirk pass changed nothing across the bank"


# ---------------------------------------------------------------------------
# 9. Anti-vacuous tripwires + the house-guard seam
# ---------------------------------------------------------------------------

def test_the_codex_index_on_the_real_tree_is_the_five_real_humans():
    """A refactor that empties this index would turn every assertion above into
    a pass. Pin the membership, not just non-emptiness."""
    assert set(ED.codex_index(ROOT)) == set(_DIAL_ACCOUNTS)


def test_every_marker_in_the_lexicon_is_declared_by_someone():
    """A marker no spec declares is dead code that enforces nothing."""
    declared = set()
    for rules in ED.codex_index(ROOT).values():
        declared |= set(rules.declared)
    orphans = sorted(set(ED.MARKERS) - declared)
    assert orphans == [], f"lexicon markers nobody declares: {orphans}"


def test_every_marker_cites_the_codex_line_it_encodes():
    """Assembly provenance: a marker with no pin is an invented quirk."""
    for marker_id, marker in ED.MARKERS.items():
        assert marker.pins.strip(), f"{marker_id} cites no pinned source"


def test_the_house_vocab_guard_is_called_not_forked():
    """One guard, two callers. include_house_bans=True inherits copywriter's
    list; the dial keeps no copy of it."""
    out = ED.violations("", "this read is validated by the tape.",
                        account="kelly", kind="macro", include_house_bans=True)
    assert any("validated" in v for v in out), out
    assert ED.violations("", "this read is validated by the tape.",
                         account="kelly", kind="macro",
                         include_house_bans=False) == []


def test_validate_copy_does_not_double_report_a_house_ban():
    """validate_copy already ran banned_language; the dial must not repeat it."""
    from engine.marketing.copywriter import build_context, validate_copy

    ctx = build_context({"ticker": "", "type": "macro", "account": "kelly"},
                        persona={"name": "Kelly", "voice_notes": "Emoji budget: 1",
                                 "example_lines": []}, facts=None)
    ctx["voice"] = "dry, receipts-forward"
    ctx["type"] = "macro"
    out = validate_copy("A read", "this one is validated by the tape.", ctx)
    assert sum(1 for v in out if "validated" in v) == 1, out


def test_validate_copy_surfaces_a_dial_violation():
    """The seam actually fires from inside the copy validator, not just in
    unit tests of this module."""
    from engine.marketing.copywriter import build_context, validate_copy

    ctx = build_context({"ticker": "", "type": "macro", "account": "kelly"},
                        persona={"name": "Kelly", "voice_notes": "Emoji budget: 1",
                                 "example_lines": []}, facts=None)
    ctx["voice"] = "dry, receipts-forward"
    ctx["type"] = "macro"
    out = validate_copy("okay so", "okay so the close said one thing.", ctx)
    assert any("unwhitelisted quirk" in v for v in out), out


def test_importing_expression_dial_stays_cheap():
    """Module level is stdlib + personas. pandas or content_studio appearing here
    would break the thin marketing-engine lane at collection."""
    probe = (
        "import sys; import engine.marketing.expression_dial; "
        "print(int('pandas' in sys.modules), "
        "int('numpy' in sys.modules), "
        "int('engine.marketing.content_studio' in sys.modules))"
    )
    proc = subprocess.run([sys.executable, "-c", probe], cwd=str(ROOT),
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "0 0 0", proc.stdout


def test_a_missing_spec_dir_disables_the_dial_instead_of_crashing(tmp_path):
    assert ED.codex_index(tmp_path) == {}
    assert ED.codex_for("meagan", root=tmp_path) is None
    assert ED.violations("h", "okay so!", account="meagan", kind="macro",
                         root=tmp_path) == []


def test_a_broken_spec_annotates_at_line_start_and_does_not_raise(tmp_path, capsys):
    """A malformed codex is CI's problem (the --check step). The nightly must not
    crash on it, and the warning must START its line or GitHub drops it."""
    spec_dir = tmp_path / "config" / "personas"
    spec_dir.mkdir(parents=True)
    (spec_dir / "broken.yml").write_text("id: broken\n", encoding="utf-8")

    assert ED.codex_for("meagan", root=tmp_path) is None
    lines = [ln for ln in capsys.readouterr().out.splitlines() if "::warning" in ln]
    assert lines, "no annotation emitted for a broken spec tree"
    assert all(ln.startswith("::") for ln in lines), lines
