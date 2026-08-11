"""Voice doctrine v5 — the census-by-content ratchet (2026-08-11).

WHAT THIS FILE IS FOR. The v4 register was not a drift, it was COMMANDED: the
system prompt ordered "Mix 'I' and 'we'... Give a stance: watching, leaning,
respecting, fading", `CORPUS_EXEMPLARS` fed first-person lines, the persona
cards registered "mixes 'I' for the read", and `validate_copy` REQUIRED a
theme_list body to end on "?". Measured on the 679-item shipped corpus
(2026-08-11): first person in 175 items (25.8%), "so far today" in 79, and
"Watching, no position." / "Levels, not advice." dominating the 72 items that
end on a short closer. Across 205 posts from 12 real reference accounts,
rhetorical-question hooks, topic hashtags and exclamation emphasis appear zero
times. Doctrine: docs/marketing_voice_doctrine_v5.md.

WHY A CENSUS BY CONTENT rather than a grep over filenames. The register lives in
DATA — template banks, exemplar tuples, persona `example_lines` in YAML — and a
new bank is one dict away. This suite IMPORTS those objects and walks their
values, so a lane that adds a seventh voice, an eighth persona or a new kind is
covered the night it is written, with no test edit. That is the house rule
(memory: census-by-content-not-by-filename) and it is the only mechanism that
stops v4 re-entering through a bank nobody thought to grep.

Deps: stdlib + pytest + pyyaml. No pandas, no numpy.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from engine.marketing import content_studio as cs
from engine.marketing import copywriter as cw
from engine.marketing import movers_source as ms
from engine.marketing import weekend_levels as wl


def _repo_root() -> Path:
    p = Path(__file__).resolve()
    for candidate in (p.parent, p.parent.parent, p.parent.parent.parent):
        if (candidate / "engine").is_dir():
            return candidate
    raise RuntimeError(f"could not locate repo root from {p}")


ROOT = _repo_root()

#: The seven accounts on a live rail (config/marketing.yml desk_network). The
#: wire desk deliberately has no `copywriter.personas` block — a wire relay
#: takes no stance and its register is engine/marketing/wire_voice.py, pinned by
#: tests/test_marketing_news_arming.py — so it is named here and skipped below
#: rather than silently absent.
LIVE_ACCOUNTS = ("flagship", "founder", "mastermind_news", "kelly", "sophia",
                 "meagan", "cici")
WIRE_ACCOUNTS_WITHOUT_A_CARD = ("mastermind_news",)

#: First person, uppercase branch: the pronoun "I" is uppercase in English, and
#: a case-insensitive form fires on "i.e." and on stray list markers.
FIRST_PERSON_UPPER = re.compile(r"\bI(?:'m|'d|'ll|'ve)?\b")
#: The rest of the family. "us" and "mine" are deliberately absent: "US" is the
#: country in every macro post this house writes, and "mine" is a noun on a
#: commodities desk.
FIRST_PERSON_LOWER = re.compile(r"\b(?:my|me|we|our|ours)\b", re.IGNORECASE)
#: The one first-person phrase the house keeps: it states what the business
#: DOES, which is a fact about the product rather than a narrator's feeling.
FIRST_PERSON_EXEMPT = ("we publish",)

BANNED_CLOSERS = ("watching, no position", "levels, not advice", "not advice")
BANNED_SUBSTRINGS = ("so far today",)

#: THE ORACLE TEASE (CMO review, 2026-08-11). The second degenerate register the
#: doctrine produced: banning the narrator left portentous vagueness as the lazy
#: optimum, and ~4 of 10 samples in the first v5 pass gestured at a payoff while
#: withholding it. Written out INDEPENDENTLY of `copywriter._V5_TEASE_PATTERNS`
#: on purpose — a census that just calls the guard it is auditing proves only
#: that the guard runs, and deleting a pattern there would silently disarm this
#: file too (memory: mirrored-guard-test-is-vacuous-on-indirection).
TEASE_FAMILIES: tuple[tuple[str, str], ...] = (
    ("carries the rest",
     r"(?:charts?|pictures?|frames?)\s+(?:carries|carry|says|does)\s+the rest"
     r"|carries the rest of it|the rest is on the (?:chart|frame|picture)"),
    ("withheld condition",
     r"\bthe missing piece\b|\bone thing is (?:still )?(?:absent|missing|carrying)\b"
     r"|\bone thing left to do\b"),
    ("provides it or it does not", r"\bor it does not\b"),
    ("a particular way", r"\ba (?:particular|certain) way\b"),
    ("reads differently", r"\breads? differently\b"),
    ("says which", r"\bsays which\b|\bpicks the direction\b|\bwhich is which\b"),
    ("that is the part", r"\bthat is the part\b|\bthe part that matters\b"),
    ("worth knowing", r"\bworth (?:knowing|a look)\b"),
    ("tells you something", r"\b(?:saying|says|tells you|meant|means) something\b"),
    ("filler tail",
     r"\bwhere it stands right now\b|\blive right now\b|\bon the tape right now\b"),
    ("that is all of it", r"\bgenuinely all\b|\ball there is so far\b"),
    ("vague deixis", r"\bdifferent fact from\b|\bhave not answered it\b"),
)


def _strings(value, depth: int = 0):
    """Every string inside a nested bank/tuple/dict/list, flattened."""
    if depth > 6:
        return
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _strings(v, depth + 1)
    elif isinstance(value, (list, tuple, set, frozenset)):
        for v in value:
            yield from _strings(v, depth + 1)


def _v5_hits(text: str) -> list[str]:
    """Every v5 ban this string breaks, named. [] = clean."""
    screened = text
    for phrase in FIRST_PERSON_EXEMPT:
        screened = re.sub(re.escape(phrase), " ", screened, flags=re.IGNORECASE)
    out: list[str] = []
    m = FIRST_PERSON_UPPER.search(screened) or FIRST_PERSON_LOWER.search(screened)
    if m:
        out.append(f"first person {m.group(0)!r}")
    if "?" in text:
        out.append("question mark")
    if "!" in text:
        out.append("exclamation mark")
    low = text.lower()
    for closer in BANNED_CLOSERS:
        if closer in low:
            out.append(f"banned closer {closer!r}")
    for phrase in BANNED_SUBSTRINGS:
        if phrase in low:
            out.append(f"banned phrase {phrase!r}")
    for ch, name in (("—", "em dash"), ("–", "en dash")):
        if ch in text:
            out.append(name)
    for label, pattern in TEASE_FAMILIES:
        if re.search(pattern, text, re.IGNORECASE):
            out.append(f"oracle tease {label!r}")
    return out


# ─────────────────────────────────────────────────────────────────────────────
# 1. The banks, walked as DATA
# ─────────────────────────────────────────────────────────────────────────────

def _bank_cases():
    """(label, string) for every literal in every post-lane bank."""
    for key, variants in cw._TEMPLATES.items():
        for i, variant in enumerate(variants):
            for text in variant[:2]:
                yield f"copywriter._TEMPLATES{key}#{i}", text
    for register, posts in cw.CORPUS_EXEMPLARS.items():
        for i, post in enumerate(posts):
            yield f"copywriter.CORPUS_EXEMPLARS[{register!r}]#{i}", post
    for bank_name in ("_CHART_VOICE_FILLER", "_THEME_VOICE_FILLER",
                      "_MOVER_VOICE_FILLER", "_RECEIPT_VOICE_PENDING"):
        for voice, text in getattr(cw, bank_name).items():
            yield f"copywriter.{bank_name}[{voice!r}]", text
    for key, pair in cs._COPY_TEMPLATES.items():
        for text in _strings(pair):
            yield f"content_studio._COPY_TEMPLATES{key}", text
    for state, frames in wl._FRAMES.items():
        for i, frame in enumerate(frames):
            yield f"weekend_levels._FRAMES[{state!r}]#{i}", frame
    for state, heads in wl._HEADLINES.items():
        for i, head in enumerate(heads):
            yield f"weekend_levels._HEADLINES[{state!r}]#{i}", head
    for i, tail in enumerate(wl._TAILS):
        yield f"weekend_levels._TAILS#{i}", tail
    for name in ("_TAIL_UP", "_TAIL_DOWN"):
        for i, tail in enumerate(getattr(ms, name)):
            yield f"movers_source.{name}#{i}", tail


BANK_CASES = list(_bank_cases())


def test_the_census_actually_walked_something():
    """ANTI-VACUOUS. A census that resolves to zero rows is a green light.

    The floor is the shape of the banks as they stand (275 template variants,
    31 exemplars, 36 weekend frames, 8 theme tails and the fillers), minus
    room to shrink a family. A bank that is DELETED rather than fixed must turn
    this red, because a deleted bank is a silently darkened lane.
    """
    assert len(BANK_CASES) >= 400, len(BANK_CASES)
    sources = {label.split("[")[0].split("(")[0].split("#")[0]
               for label, _ in BANK_CASES}
    for required in ("copywriter._TEMPLATES", "copywriter.CORPUS_EXEMPLARS",
                     "content_studio._COPY_TEMPLATES", "weekend_levels._FRAMES",
                     "weekend_levels._TAILS", "movers_source._TAIL_UP",
                     "movers_source._TAIL_DOWN"):
        assert any(s.startswith(required) for s in sources), required


def test_no_bank_literal_carries_the_v4_register():
    offenders = [f"{label}: {hits} in {text[:70]!r}"
                 for label, text in BANK_CASES
                 if (hits := _v5_hits(text))]
    assert not offenders, (
        "voice doctrine v5 bans these in every post lane "
        "(docs/marketing_voice_doctrine_v5.md). A bank literal that carries one "
        "ships it on every name it renders over:\n  " + "\n  ".join(offenders)
    )


# ─────────────────────────────────────────────────────────────────────────────
# 2. The persona cards, walked as DATA
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def marketing_cfg() -> dict:
    with open(ROOT / "config" / "marketing.yml", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def test_every_live_account_has_a_card_or_a_documented_reason(marketing_cfg):
    personas = ((marketing_cfg.get("copywriter") or {}).get("personas") or {})
    for account in LIVE_ACCOUNTS:
        if account in WIRE_ACCOUNTS_WITHOUT_A_CARD:
            assert account not in personas, (
                f"{account} is a wire relay: a desk persona here is the "
                f"editorializing the charter bans (masterplan §4)"
            )
            continue
        card = personas.get(account)
        assert card, f"{account} has no copywriter.personas block"
        assert str(card.get("voice_notes") or "").strip(), account
        assert list(card.get("example_lines") or []), account


def test_no_persona_card_teaches_the_v4_register(marketing_cfg):
    """The card OUTRANKS the house defaults inside the caps it names, so a card
    that registers first person beats every prompt edit upstream of it. That is
    exactly how v4 survived three prompt rewrites."""
    personas = ((marketing_cfg.get("copywriter") or {}).get("personas") or {})
    offenders = []
    for account in LIVE_ACCOUNTS:
        card = personas.get(account)
        if not card:
            continue
        for i, line in enumerate(card.get("example_lines") or []):
            if hits := _v5_hits(str(line)):
                offenders.append(f"{account}.example_lines#{i}: {hits}")
        # The prose card may NAME a ban ("no first person") without breaking it,
        # so the voice_notes screen is scoped to the tokens a post would carry.
        notes = str(card.get("voice_notes") or "")
        for closer in BANNED_CLOSERS[:2]:
            if closer in notes.lower():
                offenders.append(f"{account}.voice_notes registers {closer!r}")
    assert not offenders, offenders


def test_no_persona_spec_registers_first_person_as_a_quirk():
    """config/personas/<id>.yml voice_codex.quirks is the machine-readable half
    of the card. "mixes 'I' for the read and 'we' for the shop's calls" was a
    REGISTERED LICENCE, and expression_dial reads this file, not the prose."""
    offenders = []
    for account in LIVE_ACCOUNTS:
        path = ROOT / "config" / "personas" / f"{account}.yml"
        if not path.exists():
            continue
        with open(path, encoding="utf-8") as fh:
            spec = yaml.safe_load(fh) or {}
        codex = spec.get("voice_codex") or {}
        for quirk in codex.get("quirks") or []:
            text = str(quirk)
            if re.search(r"'I'|\bfirst person\b", text) and "no first person" not in text.lower():
                offenders.append(f"{account}: quirk {text!r}")
        register = str(codex.get("register") or "")
        # A register may NAME the ban ("no first person") without registering
        # it; only a register that GRANTS the habit is the defect.
        if (re.search(r"\bfirst person\b", register, re.IGNORECASE)
                and not re.search(r"\bno first person\b", register, re.IGNORECASE)):
            offenders.append(f"{account}: register {register[:60]!r}")
    assert not offenders, offenders


# ─────────────────────────────────────────────────────────────────────────────
# 3. The gate itself: it must REJECT v4 and ACCEPT the doctrine's exemplars
# ─────────────────────────────────────────────────────────────────────────────

def _ctx(**over) -> dict:
    ctx = {
        "type": "chart", "ticker": "NVDA", "account": "flagship",
        "emoji_budget": 1,
        "numbers_whitelist": ["209", "3", "four", "41.20", "8", "9", "14",
                              "2020", "211.40"],
    }
    ctx.update(over)
    return ctx


V4_SYNTHETIC = (
    "$NVDA back above 209",
    "I'm leaning on that history unless the rebound stalls here. "
    "Watching, no position.",
)


def test_validate_copy_rejects_a_synthetic_v4_post():
    hits = cw.validate_copy(V4_SYNTHETIC[0], V4_SYNTHETIC[1], _ctx())
    assert any("first person" in h for h in hits), hits
    assert any("banned closer" in h for h in hits), hits


TEASE_SYNTHETIC = (
    "$NVDA is close",
    "One thing is missing here. The market provides it or it does not.",
)


def test_validate_copy_rejects_a_synthetic_oracle_tease_post():
    """The second degenerate register, and the reason a style law needs a
    POSITIVE requirement: removing the narrator made vagueness the lazy
    optimum. This is the CMO's own sample line."""
    hits = cw.validate_copy(TEASE_SYNTHETIC[0], TEASE_SYNTHETIC[1],
                            _ctx(type="watchlist"))
    assert any("oracle tease" in h for h in hits), hits


@pytest.mark.parametrize("tail", [
    "The chart carries the rest of it.",
    "The closest matches went a particular way.",
    "The group reads differently from that starting point.",
    "209 is the level, and it is live right now.",
    "The level picks the direction.",
    "There is a parallel worth knowing before the crowd rediscovers it.",
    "Big number, and that is genuinely all of it so far.",
    "A whole group going at once is a different fact from one name going.",
])
def test_each_tease_family_is_rejected_wherever_it_lands(tail):
    assert cw.voice_v5_violations(f"$NVDA held 209. {tail}",
                                  {"type": "chart"}) != [], tail


def test_the_tease_screen_is_phrase_families_not_a_digit_rule():
    """NO blanket "the last sentence must carry a number" rule, and this is the
    fixture that would break under one: doctrine exemplar 1 closes on "The
    most-traded price of the summer is now underneath" — digit-free, and the
    strongest line in the set. A shape rule here would delete the target."""
    digit_free_closer = (
        "$NVDA closed above 209 for the first time in three weeks. That level "
        "capped four rallies since June. The most-traded price of the summer "
        "is now underneath."
    )
    assert cw.voice_v5_violations(digit_free_closer, {"type": "chart"}) == []
    assert not re.search(r"\d", digit_free_closer.rsplit(".", 2)[-2])


def test_the_tease_screen_applies_to_the_wire_too():
    """The wire's exemption is scoped to the pronoun and the question mark: a
    relay carries a source's words, and nothing licenses the DESK's own copy to
    point at a payoff it is not printing."""
    tease = "Guidance cut. The chart carries the rest of it."
    assert any("oracle tease" in h
               for h in cw.voice_v5_violations(tease, {"type": "breaking"})), tease


def test_validate_copy_rejects_a_rhetorical_question_on_every_analytical_kind():
    for kind in ("chart", "signal", "theme_list", "mover", "event", "macro",
                 "watchlist", "insider"):
        hits = cw.validate_copy(
            "$NVDA back above 209",
            "The level capped four rallies since June. Does it hold this time?",
            _ctx(type=kind))
        assert any("question mark" in h for h in hits), (kind, hits)


def test_the_theme_list_question_requirement_is_inverted_not_merely_deleted():
    """It used to be a REQUIREMENT ("body must end with a question mark"), which
    is why every theme post the desk ever shipped ended on reply-bait."""
    ctx = _ctx(type="theme_list",
               cashtags=["$NVDA", "$AMD", "$AVGO", "$SMCI"],
               numbers_whitelist=["7.2%", "19", "22"])
    body = "$NVDA $AMD $AVGO $SMCI\nThe group averaged +7.2%. Am I getting a second session out of this?"
    hits = cw.validate_copy("Metals did the work today", body, ctx)
    assert any("question" in h for h in hits), hits
    assert not any("must end with a question mark" in h for h in hits), hits


def test_validate_copy_accepts_doctrine_exemplar_one():
    """The gate has to ACCEPT the target register, or it just blocks the lane."""
    ctx = _ctx(numbers_whitelist=["209", "four", "three"])
    headline = "$NVDA closed above 209 for the first time in three weeks."
    body = ("That level capped four rallies since June. The most-traded price "
            "of the summer is now underneath.")
    assert cw.validate_copy(headline, body, ctx) == []


@pytest.mark.parametrize("register,index", [(r, i)
                                            for r, posts in cw.CORPUS_EXEMPLARS.items()
                                            for i in range(len(posts))])
def test_every_shipped_exemplar_clears_the_v5_screen(register, index):
    post = cw.CORPUS_EXEMPLARS[register][index]
    ctx = {"type": "breaking"} if "wire" in register else {"type": "chart"}
    assert cw.voice_v5_violations(post, ctx) == [], post[:80]


def test_the_wire_exemption_is_scoped_and_does_not_leak():
    """A relayed source headline may carry "?" or a quoted "I" (2 of the 4
    breaking items with "?" in the census are relayed headlines). No analytical
    kind gets that, and every OTHER v5 ban still applies to the wire."""
    relayed = "$400 Billion Pharma Megadeal? Jefferies Calls It A Head Scratcher"
    assert cw.voice_v5_violations(relayed, {"type": "breaking"}) == []
    assert cw.voice_v5_violations(relayed, {"type": "chart"}) != []
    wire_ctx = {"type": "breaking"}
    assert cw.voice_v5_violations("Nasdaq is up. Watching, no position.",
                                  wire_ctx) != []
    assert cw.voice_v5_violations("Nasdaq is up 2% so far today.", wire_ctx) != []


def test_the_screen_rejects_an_unhumanized_dollar_figure():
    raw = "The move erased $7,639,791,784 in market cap."
    assert any("raw dollar figure" in h
               for h in cw.voice_v5_violations(raw, {"type": "breaking"})), raw
    ok = "The move erased $7.64B in market cap."
    assert cw.voice_v5_violations(ok, {"type": "breaking"}) == []


def test_the_prompt_and_the_gate_state_the_same_law():
    """A prompt that orders what the validator kills is the self-cancelling
    failure the 2026-07-31 autopsy class exists to catch, and v4's stance
    bullets were exactly that shape once the screen landed."""
    prompt = cw._v2_system_prompt({})
    assert "THE STANCE LIVES IN THE SELECTION" in prompt
    assert "no 'I', no 'my', no 'we'" in prompt
    assert "NO question marks" in prompt
    for retired in ("Mix 'I' and 'we'",
                    "Give a stance: watching, leaning, respecting, fading"):
        assert retired not in prompt, retired
