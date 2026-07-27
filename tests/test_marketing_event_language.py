"""tests/test_marketing_event_language.py — the 2026-07-27 event-post incident.

The flagship "My read on today's move" post shipped three stacked defects:

  1. market_facts.event_facts() passed a market_drivers DASHBOARD label
     ("hawkish repricing — cuts priced out, front-end up") through a dash
     stripper instead of a translation, so subject-less desk shorthand
     became the post body.
  2. It cited internal machinery as evidence: "The cross-checks back it up."
     — a reference to the pipeline's own coherence flag, meaningless to a
     reader.
  3. The deterministic template contradicted its own headline: "My read on
     today's move" followed by "I wait for the second one" announces a read
     and then disowns it.

This suite pins the fixes: every driver label the engine can emit has a full
plain-English translation (unknown labels are DROPPED, never sanitized), the
coherence flag renders as tape language, the incoherent/fact-asserting
templates are gone, and the validator rejects internal-machinery vocabulary.

Kept stdlib-only so it runs in the marketing-engine minimal lane: the driver
label census parses engine/market_drivers.py SOURCE with a regex instead of
importing it (the import needs pandas/numpy). A count floor guards the regex
itself — if the source format changes and the regex goes blind, the census
fails loudly instead of passing on zero labels.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent

# The label count in engine/market_drivers.py DRIVERS as of 2026-07-27
# (9 drivers x pos/neg). A census below this floor means the parse regex
# went blind, not that drivers were removed.
_MIN_DRIVER_LABELS = 18


def _driver_labels_from_source() -> list[str]:
    src = (_REPO / "engine" / "market_drivers.py").read_text(encoding="utf-8")
    return re.findall(r'"(?:pos|neg)":\s*"([^"]+)"', src)


def _norm(label: str) -> str:
    return " ".join(label.strip().lower().split())


# ─────────────────────────────────────────────────────────────────────────────
# 1. Driver-label translation coverage
# ─────────────────────────────────────────────────────────────────────────────

def test_every_driver_label_has_a_plain_translation():
    """Adding a driver to market_drivers.DRIVERS without a plain-English
    translation must fail here — an untranslated label would silently drop
    the event fact every day that driver leads."""
    from engine.marketing.market_facts import _DRIVER_PLAIN

    labels = _driver_labels_from_source()
    assert len(labels) >= _MIN_DRIVER_LABELS, (
        f"label census found only {len(labels)} labels — the parse regex "
        "no longer matches engine/market_drivers.py; fix the census, do not "
        "lower the floor"
    )
    missing = [lb for lb in labels if _norm(lb) not in _DRIVER_PLAIN]
    assert not missing, f"driver labels with no plain translation: {missing}"

    # Bidirectional: a table entry no driver can emit is dead weight or a typo.
    live = {_norm(lb) for lb in labels}
    dead = [k for k in _DRIVER_PLAIN if k not in live]
    assert not dead, f"translations for labels no driver emits: {dead}"


def test_translations_read_as_plain_full_sentences():
    """Every translation is a complete sentence a scrolling reader can parse:
    no dashboard shorthand, no desk jargon, no internal vocabulary — and it
    passes the same banned-vocab lists the copy validator enforces."""
    from engine.marketing.copywriter import _BANNED_SUBSTRINGS, _BANNED_VOCAB
    from engine.marketing.market_facts import _DRIVER_PLAIN

    jargon = ("front-end", "cross-check", "repricing", "de-rating",
              "breakeven", "duration", "—", "–")
    for key, text in _DRIVER_PLAIN.items():
        low = text.lower()
        assert text[0].isupper() and text.endswith("."), (key, text)
        assert len(text.split()) >= 10, f"fragment, not a sentence: {text!r}"
        for term in jargon:
            assert term not in low, f"{term!r} leaked into {text!r}"
        for phrase in _BANNED_SUBSTRINGS:
            assert phrase not in low, f"banned substring {phrase!r} in {text!r}"
        for word in _BANNED_VOCAB:
            assert not re.search(rf"\b{re.escape(word)}\b", low), (
                f"banned vocab {word!r} in {text!r}")


def test_coherence_tails_never_cite_machinery():
    from engine.marketing.market_facts import _COHERENCE_PLAIN

    assert set(_COHERENCE_PLAIN) == {"supported", "conflicted", "mixed",
                                     "unsupported"}
    for tail in _COHERENCE_PLAIN.values():
        assert tail.startswith(" ") and tail.endswith(".")
        assert "cross-check" not in tail.lower()
        assert "data" not in tail.lower() or "tape" in tail.lower()


# ─────────────────────────────────────────────────────────────────────────────
# 2. event_facts / macro_facts behavior
# ─────────────────────────────────────────────────────────────────────────────

def _write_brief(root: Path, direction: str, coherence: str = "supported") -> None:
    p = root / "site" / "neuralwebdata"
    p.mkdir(parents=True, exist_ok=True)
    (p / "daily_brief.json").write_text(json.dumps({
        "why_the_tape_moved": {
            "available": True,
            "as_of": "2026-07-27",
            "primary": {
                "family": "rates",
                "direction": direction,
                "coverage": 1.0,
                "coherence": coherence,
                "evidence_legs": ["2y yield", "rate-path (2y−FF)", "10y yield"],
                "stale_legs_count": 0,
            },
            "alternates": ["inflation", "rates"],
        },
    }), encoding="utf-8")


def _write_regime(root: Path) -> None:
    p = root / "data" / "regime"
    p.mkdir(parents=True, exist_ok=True)
    (p / "latest.json").write_text(json.dumps({
        "growth_score": -0.4, "inflation_score": 0.2,
    }), encoding="utf-8")


def test_event_facts_translates_the_incident_payload(tmp_path):
    """The exact 2026-07-27 payload must now render as plain English."""
    from engine.marketing.market_facts import event_facts

    _write_brief(tmp_path, "hawkish repricing — cuts priced out, front-end up")
    out = event_facts(tmp_path)

    assert len(out["facts"]) == 1
    text = out["facts"][0]["text"]
    assert out["facts"][0]["id"] == "event_catalyst"
    assert text == (
        "Rates are doing the driving today. Traders are pricing out Fed cuts "
        "and short-term yields are climbing. The rest of the tape lines up "
        "with that."
    )
    low = text.lower()
    for relic in ("cross-check", "front-end", "repricing", "what's driving today"):
        assert relic not in low, f"incident language {relic!r} survived: {text!r}"


def test_event_facts_unknown_label_falls_back_to_macro(tmp_path):
    """A label with no translation must NOT ship as shorthand — the event post
    falls back to macro context instead."""
    from engine.marketing.market_facts import event_facts

    _write_brief(tmp_path, "flurble surging — gizmos up, widgets pressured")
    _write_regime(tmp_path)
    out = event_facts(tmp_path)

    ids = [f["id"] for f in out["facts"]]
    assert "event_catalyst" not in ids
    assert "growth_inflation" in ids          # macro fallback carried the post
    joined = " ".join(f["text"] for f in out["facts"]).lower()
    assert "flurble" not in joined and "gizmos" not in joined


def test_macro_facts_drops_untranslatable_tape_fact(tmp_path):
    from engine.marketing.market_facts import macro_facts

    _write_regime(tmp_path)
    _write_brief(tmp_path, "flurble surging — gizmos up")
    ids = [f["id"] for f in macro_facts(tmp_path)["facts"]]
    assert "tape_direction" not in ids

    _write_brief(tmp_path, "net liquidity draining — risk headwind")
    facts = {f["id"]: f["text"] for f in macro_facts(tmp_path)["facts"]}
    assert facts.get("tape_direction") == (
        "Liquidity is the drag today. Money is draining out of the system "
        "and risk assets are fighting it."
    )


# ─────────────────────────────────────────────────────────────────────────────
# 3. Template coherence
# ─────────────────────────────────────────────────────────────────────────────

def test_templates_carry_no_incident_language():
    """The self-contradicting aphorism and the fact-asserting template
    sentences are gone from BOTH template banks, and no template anywhere
    cites internal machinery."""
    from engine.marketing.content_studio import _COPY_TEMPLATES
    from engine.marketing.copywriter import _TEMPLATES

    incident = (
        "i wait for the second one",     # read announced, then disowned
        "the board barely moved",        # unconditional claim about the day
        "not much drama",                # unconditional claim about the day
        "the data says one thing",       # unconditional divergence claim
        "cross-check",                   # internal machinery
    )
    for bank_name, bank in (("copywriter", _TEMPLATES),
                            ("content_studio", _COPY_TEMPLATES)):
        for key, entry in bank.items():
            variants = entry if isinstance(entry, list) else [entry]
            for variant in variants:
                blob = " ".join(str(part) for part in variant[:2]).lower()
                for phrase in incident:
                    assert phrase not in blob, (
                        f"{bank_name} template {key} still carries "
                        f"{phrase!r}: {variant[:2]}")


def test_validator_rejects_internal_machinery_vocab():
    from engine.marketing.copywriter import validate_copy

    ctx = {"type": "event", "ticker": "", "numbers_whitelist": []}
    violations = validate_copy(
        "My read on today's move",
        "Hawkish repricing, front-end up. The cross-checks back it up.",
        ctx,
    )
    joined = " ".join(violations).lower()
    assert "cross-check" in joined
    assert "front-end" in joined


# ─────────────────────────────────────────────────────────────────────────────
# 4. banned_language — the shared screen behind validate_copy AND the
#    publisher's post-time gate (2026-07-27 $AVGO "POC held" incident)
# ─────────────────────────────────────────────────────────────────────────────

def test_banned_language_flags_study_names_and_tells():
    from engine.marketing.copywriter import banned_language

    hits = banned_language("$AVGO retested the POC at 379.32 and held.")
    assert any("poc" in h for h in hits)
    hits = banned_language("Sitting right at the point of control today.")
    assert any("point of control" in h for h in hits)
    hits = banned_language("VWAP holds — watching the close.")
    assert any("vwap" in h for h in hits)
    assert any("em dash" in h for h in hits)


def test_banned_language_passes_plain_speech():
    from engine.marketing.copywriter import banned_language

    assert banned_language(
        "$AVGO held 379.32, the price where the most shares changed hands "
        "lately. Up 0.8% in four weeks. Watching, no position.") == []


def test_validate_copy_and_gate_share_one_bar():
    """validate_copy must flag a superset of banned_language on the same text —
    the generation bar and the post-time bar cannot drift apart."""
    from engine.marketing.copywriter import banned_language, validate_copy

    text = "POC held, waiting. The cross-checks back it up — front-end up."
    gate = set(banned_language(text))
    gen = set(validate_copy("h", text, {"type": "event", "ticker": ""}))
    assert gate and gate <= gen
