"""tests/test_marketing_anchor_law.py — the 2026-08-01 anchorless-macro kill.

Three macro/event posts cleared every deterministic gate, cleared the batch
auditor, were APPROVED, and were then pulled off the queue by hand:

    "4 of 11 sectors green on a day growth data firmed and inflation stayed
     warm. Not a clean enough read to lean on yet."                (flagship)
    "Not a clearcut tape. Growth firming a bit, inflation still warm, and only
     4 of 11 sectors managed green. I'm watching, not deciding."   (founder)
    "growth data firmed a touch while inflation stayed warm. 4 of 11 sectors
     closed green. steady liquidity is the part i'm watching..."   (kelly)

Operator verdict: "too bland, too weak, no real value, so esoteric no one knows
what it's talking about, zero engagement, people might even report us cuz only
bots/llm write garbage like this."

THE DEFECT WAS UPSTREAM OF THE COPY. All three are faithful renderings of the
fact packet they were handed, and the packet's lead fact was a pre-baked
abstraction minted by ``market_facts._growth_words`` / ``_inflation_words``.
So this suite pins both halves of the fix:

  * the PACKET now names the print (``market_facts`` §Named prints), and
  * the VALIDATOR refuses an abstraction that carries no print
    (``copywriter.anchorless_macro_violations``), wired at generation time AND
    at post time, because the queue is a bypass around every generation law.

Every negative fixture below is one of the three killed posts, verbatim.

Kept stdlib-only so it runs in the thin marketing-engine CI lane.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def _worktree_root() -> Path:
    p = Path(__file__).resolve()
    for candidate in [p.parent, p.parent.parent, p.parent.parent.parent]:
        if (candidate / "engine").is_dir():
            return candidate
    raise RuntimeError(f"Could not locate repo root from {p}")


ROOT = _worktree_root()
sys.path.insert(0, str(ROOT))

from engine.marketing import copywriter as cw  # noqa: E402
from engine.marketing import market_facts as mf  # noqa: E402

# ─────────────────────────────────────────────────────────────────────────────
# The corpses, verbatim from data/marketing/outbox/items.jsonl (2026-08-01)
# ─────────────────────────────────────────────────────────────────────────────

CORPSE_FLAGSHIP = (
    "4 of 11 sectors green on a day growth data firmed and inflation stayed "
    "warm. Not a clean enough read to lean on yet."
)
CORPSE_FOUNDER = (
    "Not a clearcut tape. Growth firming a bit, inflation still warm, and only "
    "4 of 11 sectors managed green. I'm watching, not deciding."
)
CORPSE_KELLY = (
    "growth data firmed a touch while inflation stayed warm. 4 of 11 sectors "
    "closed green.\nsteady liquidity is the part i'm watching. if credit isn't "
    "tightening into this, the soft-landing crowd gets another data point. if "
    "spreads widen next week, the whole read flips."
)
CORPSES = (
    ("macro", CORPSE_FLAGSHIP),
    ("event", CORPSE_FOUNDER),
    ("macro", CORPSE_KELLY),
)


# ─────────────────────────────────────────────────────────────────────────────
# 1-3. The killed posts are refused, by name
# ─────────────────────────────────────────────────────────────────────────────

def test_every_killed_post_is_refused_by_the_anchor_rule():
    for kind, text in CORPSES:
        hits = cw.anchorless_macro_violations(text, kind)
        assert hits, f"{kind} corpse still passes: {text[:60]!r}"
        assert hits[0].startswith("anchorless macro"), hits


def test_the_refusal_quotes_the_rule_it_enforces():
    """A gate that says 'rejected' teaches nothing. This one says what to do."""
    hits = cw.anchorless_macro_violations(CORPSE_FLAGSHIP, "macro")
    msg = hits[0].lower()
    assert "name the print" in msg, hits
    assert "drop the claim" in msg, hits
    # And it names the abstraction it actually found, not a generic class.
    assert "growth data" in msg, hits


def test_the_gate_is_not_a_number_gate():
    """All three corpses contain '4 of 11'. A count of our own sectors is not a
    print, and the rule must not be satisfiable by any digit at all — that is
    the difference between this gate and the denominator law."""
    for _kind, text in CORPSES:
        assert re.search(r"\d", text), text
    assert not cw._has_named_print_anchor(
        "4 of 11 sectors closed green today. The tape is not clean.")


# ─────────────────────────────────────────────────────────────────────────────
# 4-6. What must keep passing (a gate that cries wolf gets disarmed)
# ─────────────────────────────────────────────────────────────────────────────

def test_a_concretized_packet_fact_passes():
    """The brief's own acceptance string, plus the abstraction it is allowed to
    carry once the print is named."""
    assert cw.anchorless_macro_violations(
        "Michigan sentiment 55.2, beat. Growth data is firming.", "macro") == []
    assert cw.anchorless_macro_violations(
        "Jobless claims are averaging 203 thousand a week this month, 8.6% "
        "below a year ago. Growth data's firming up a little while inflation "
        "readings are still warm.", "macro") == []


def test_the_anchor_survives_a_decimal_percent():
    """MUTATION PIN. A naive `[.!?\\n]+` sentence split cuts '5.0%' into '5' and
    '0%', which strips the number out of the only sentence that had it and
    turns this gate into a blanket ban on the word 'the tape'. The helper must
    use the module's decimal-guarded splitter."""
    text = ("The Atlanta Fed's GDPNow estimate has the economy growing at a "
            "5.0% annual rate this quarter. The tape does not act like it.")
    assert cw._has_named_print_anchor(text)
    assert cw.anchorless_macro_violations(text, "macro") == []
    # 55.2 is the same trap one decimal place to the left.
    assert cw._has_named_print_anchor("Michigan sentiment 55.2, a beat.")


def test_kinds_outside_the_macro_family_are_untouched():
    """A ticker post is anchored by its packet; an education post is about a
    concept. Neither is in scope, and widening the blast radius of a new gate
    is how a lane goes dark."""
    for kind in ("signal", "chart", "receipt", "education", "watchlist", ""):
        assert cw.anchorless_macro_violations(CORPSE_FLAGSHIP, kind) == [], kind


def test_a_concrete_driver_read_with_no_abstraction_still_passes():
    """The rule fires on the ABSTRACTION, not on the absence of a number. An
    event post that names what moved keeps shipping."""
    assert cw.anchorless_macro_violations(
        "Credit is the story today. Spreads are widening, which is the bond "
        "market getting nervous.", "event") == []


# ─────────────────────────────────────────────────────────────────────────────
# 7-8. Dual wiring — generation time AND post time
# ─────────────────────────────────────────────────────────────────────────────

def test_the_rule_is_wired_into_validate_copy_v2():
    ctx = cw.build_context({"type": "macro", "account": "flagship"})
    ctx["shape"] = "one_liner"
    hits = cw.validate_copy_v2(CORPSE_FLAGSHIP, ctx)
    assert any(h.startswith("anchorless macro") for h in hits), hits


def test_the_rule_is_wired_into_the_post_time_queued_screen():
    """THE QUEUE IS A BYPASS. All three corpses were already queued and
    approved when the rule was written, so a generation-only gate would have
    shipped them the following night regardless of what the writer does."""
    for kind, text in CORPSES:
        hits = cw.queued_voice_violations(text, kind)
        assert any(h.startswith("anchorless macro") for h in hits), (kind, hits)


def test_the_two_screens_agree_on_kind():
    """Both read the same field the number budget reads, so the generation bar
    and the last-gate bar cannot drift apart on scope."""
    ctx = cw.build_context({"type": "signal"})
    ctx["shape"] = "one_liner"
    assert not any(h.startswith("anchorless macro")
                   for h in cw.validate_copy_v2(CORPSE_FLAGSHIP, ctx))
    assert not any(h.startswith("anchorless macro")
                   for h in cw.queued_voice_violations(CORPSE_FLAGSHIP, "signal"))


# ─────────────────────────────────────────────────────────────────────────────
# 9-13. The packet half: named prints minted from the artifact
# ─────────────────────────────────────────────────────────────────────────────

#: Every field the named-print builders read, with the live 2026-07-31 values.
#: Pinned as a fixture so a UNIT change upstream (percent vs basis points,
#: level vs change) fails here instead of shipping a mislabelled print.
FULL_REGIME = {
    "growth_score": 0.133,
    "inflation_score": 0.72,
    "conditions": {
        "labor_nowcast": {"initial_claims_4wk": 202750.0,
                          "claims_yoy_pct": -8.568207440811726},
        "growth_nowcast": {"gdpnow": 4.9543},
        "inflation_nowcast": {"median_cpi": 2.10961524352649,
                              "umich_1y_exp": 4.6},
        "style_tilt": {"yield_chg_1m_bp": 19.0},
    },
    "liquidity_quality": {"stress_overlay": {"hy_oas_pct": 2.84,
                                             "hy_oas_chg_20d": 0.1}},
    "fed_path": {"policy_rate": 3.63, "implied": {"m12": 4.18}},
    "yield_curve": {"shape": {"slope_2s10s": {"value": 0.47}}},
}

EXPECTED_PRINTS = {
    "print_jobless_claims":
        "Jobless claims are averaging 203 thousand a week this month, 8.6% "
        "below a year ago.",
    "print_gdpnow":
        "The Atlanta Fed's GDPNow has the economy growing at a 5.0% annual "
        "rate this quarter.",
    "print_median_cpi":
        "The Cleveland Fed's median CPI is running at a 2.1% annual rate.",
    "print_umich_infl_exp":
        "The Michigan survey has households expecting 4.6% inflation a year out.",
    "print_hy_spread":
        "High-yield credit spreads are at 2.8%, wider than a month ago.",
    "print_10y_move":
        "The 10-year Treasury yield is up 19 basis points over the past month.",
    "print_fed_pricing":
        "Fed funds futures put the policy rate at 4.2% a year out, up from "
        "3.6% today.",
    "print_curve_2s10s":
        "The 10-year Treasury yield sits 47 basis points above the 2-year.",
}


def test_every_builder_renders_its_documented_units():
    """UNITS ARE THE WHOLE GAME. Each builder is exercised on its own so the
    rank cap cannot hide a broken one behind the three that ship."""
    for build in mf._NAMED_PRINT_BUILDERS:
        out = build(FULL_REGIME)
        assert out is not None, build.__name__
        assert out["text"] == EXPECTED_PRINTS[out["id"]], (out["id"], out["text"])


def test_a_print_never_quotes_a_number_it_does_not_whitelist():
    """The whitelist is the invented-number gate; a fact whose text carries a
    figure its `numbers` omits licenses nothing and breaks the gate."""
    num_re = re.compile(r"\d{1,3}(?:,\d{3})*(?:\.\d+)?%?")
    for build in mf._NAMED_PRINT_BUILDERS:
        out = build(FULL_REGIME)
        wl = set(out["numbers"])
        for tok in num_re.findall(out["text"]):
            if re.fullmatch(r"\d{1,2}", tok):
                continue  # bare small integers are prose ("2-year", "4-week")
            assert tok in wl, (out["id"], tok, out["numbers"])


def test_an_empty_artifact_mints_nothing():
    """Fail-soft, and never fabricate: no artifact means no anchor, not a
    plausible-looking print."""
    assert mf._named_prints({}) == []
    assert mf._named_prints(None) == []
    assert mf.named_print_facts("/nonexistent-root")["facts"] == []


def test_a_builder_that_raises_costs_one_anchor_not_the_packet():
    """One missing anchor costs a post its digit; a traceback costs the plan
    every non-ticker post it had."""
    poison = {"conditions": {"labor_nowcast": {"initial_claims_4wk": "not a number"}},
              "fed_path": {"policy_rate": 3.63, "implied": {"m12": 4.18}}}
    out = mf._named_prints(poison)
    assert [p["id"] for p in out] == ["print_fed_pricing"], out


def test_the_packet_carries_no_more_prints_than_the_writer_can_see():
    """COUPLING PIN. `build_context` hands the writer `all_facts[:3]`. A fourth
    print would never be shown to the model but WOULD enter the numbers
    whitelist, licensing a digit nobody put in the prompt."""
    assert mf._NAMED_PRINT_MAX == 3
    assert len(mf._named_prints(FULL_REGIME)) == 3
    src = (ROOT / "engine" / "marketing" / "copywriter.py").read_text(encoding="utf-8")
    assert "all_facts[:3]" in src, (
        "build_context no longer shows the writer three facts; "
        "_NAMED_PRINT_MAX has to move with it")


# ─────────────────────────────────────────────────────────────────────────────
# 14-17. The fold: the packet's LEAD fact names a print
# ─────────────────────────────────────────────────────────────────────────────

def _write(root: Path, rel: str, payload: dict) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload), encoding="utf-8")


def test_the_macro_lead_fact_leads_with_the_print(tmp_path):
    _write(tmp_path, "data/regime/latest.json", FULL_REGIME)
    facts = mf.macro_facts(tmp_path)["facts"]
    lead = facts[0]
    assert lead["id"] == "growth_inflation", [f["id"] for f in facts]
    # PRINT FIRST, STANCE SECOND — the killed posts opened on the abstraction.
    assert lead["text"].startswith(EXPECTED_PRINTS["print_jobless_claims"]), lead
    assert "growth data" in lead["text"].lower()
    # And the post built on it is legal, abstraction and all.
    assert cw.anchorless_macro_violations(lead["text"], "macro") == []


def test_the_folded_print_is_not_also_shipped_standalone(tmp_path):
    """One packet must not say the same sentence twice — a duplicate burns one
    of the three slots the writer can see."""
    _write(tmp_path, "data/regime/latest.json", FULL_REGIME)
    facts = mf.macro_facts(tmp_path)["facts"]
    ids = [f["id"] for f in facts]
    assert "print_jobless_claims" not in ids, ids
    assert ids[1:3] == ["print_gdpnow", "print_median_cpi"], ids


def test_the_top_three_facts_the_writer_sees_all_carry_a_number(tmp_path):
    """The three facts `build_context` shows the model. All three anchored is
    what makes an anchorless macro post hard to write rather than merely
    illegal."""
    _write(tmp_path, "data/regime/latest.json", FULL_REGIME)
    fd = mf.macro_facts(tmp_path)
    for f in fd["facts"][:3]:
        assert cw._has_named_print_anchor(f["text"]), f


def test_an_artifact_with_no_prints_falls_back_to_the_breadth_clause(tmp_path):
    """The pre-2026-08-01 behaviour is the FALLBACK, not deleted: where the
    artifact has no named print, the fact still says the concrete observable it
    does have."""
    _write(tmp_path, "data/regime/latest.json",
           {"growth_score": -0.4, "inflation_score": 0.2})
    _write(tmp_path, "site/marketdata/sp500_heatmap.json", {"tiles": [
        {"t": "AAA", "name": "AAA", "sector": "Energy", "perf": {"1D": 1.1}},
        {"t": "BBB", "name": "BBB", "sector": "Utilities", "perf": {"1D": -1.3}},
    ]})
    lead = mf.macro_facts(tmp_path)["facts"][0]
    assert lead["id"] == "growth_inflation"
    assert "1 of 2 sectors closed green today." in lead["text"], lead
    assert lead["salience"] == 10, "unanchored lead must not claim the anchor rank"


def test_the_anchor_ships_standalone_when_there_is_no_read_to_fold_it_into(tmp_path):
    """No growth/inflation scores means no lead fact to fold into. The anchor
    must not vanish with it."""
    regime = {k: v for k, v in FULL_REGIME.items()
              if k not in ("growth_score", "inflation_score")}
    _write(tmp_path, "data/regime/latest.json", regime)
    facts = mf.macro_facts(tmp_path)["facts"]
    assert facts[0]["id"] == "print_jobless_claims", [f["id"] for f in facts]
    assert facts[0]["salience"] == mf._ANCHORED_LEAD_SALIENCE


def test_the_event_driver_read_is_anchored_too(tmp_path):
    """Several driver translations lean on exactly the vocabulary that was
    killed ('carrying the tape', 'liquidity is doing the lifting'), so the
    event lane needs the anchor as much as the macro one."""
    _write(tmp_path, "data/regime/latest.json", FULL_REGIME)
    _write(tmp_path, "site/neuralwebdata/daily_brief.json", {
        "why_the_tape_moved": {
            "available": True,
            "primary": {"direction": "net liquidity expanding — broad risk-on tailwind",
                        "coherence": "supported"},
        },
    })
    facts = mf.event_facts(tmp_path)["facts"]
    lead = facts[0]
    assert lead["id"] == "event_catalyst", [f["id"] for f in facts]
    assert "liquidity" in lead["text"].lower()
    assert lead["text"].endswith(EXPECTED_PRINTS["print_jobless_claims"]), lead
    assert cw.anchorless_macro_violations(lead["text"], "event") == []


def test_the_unanchored_event_read_is_exactly_the_post_that_was_killed(tmp_path):
    """MUTATION CHECK on the test above: without the fold, that same driver
    read is a violation. If this ever goes green with an empty regime, the fold
    has stopped being what makes the event lane legal."""
    _write(tmp_path, "site/neuralwebdata/daily_brief.json", {
        "why_the_tape_moved": {
            "available": True,
            "primary": {"direction": "net liquidity expanding — broad risk-on tailwind",
                        "coherence": "supported"},
        },
    })
    lead = mf.event_facts(tmp_path)["facts"][0]
    assert lead["id"] == "event_catalyst"
    assert cw.anchorless_macro_violations(lead["text"], "event"), lead


# ─────────────────────────────────────────────────────────────────────────────
# 18-20. The prints have to survive the gates that read them
# ─────────────────────────────────────────────────────────────────────────────

def test_no_print_trips_a_gate_downstream_of_it():
    """A packet that mints copy its own validators refuse is the
    gate-rejects-obedience failure this house has already paid for once."""
    for build in mf._NAMED_PRINT_BUILDERS:
        text = build(FULL_REGIME)["text"]
        hits = (cw.jargon_violations(text)
                + cw.banned_language(text)
                + cw.fake_precision_violations(text)
                + cw.headless_counts(text)
                + cw.lecture_violations(text)
                + cw.machine_risk_violations(text)
                + cw.dangling_levels(text))
        assert not hits, (text, hits)


def test_a_percent_print_carries_one_decimal():
    """`fake_precision_violations` rejects a two-decimal percent at every
    magnitude, so a '2.84%' minted here would be refused by the validator that
    reads it. hy_oas_pct is 2.84 in the artifact and 2.8% in the fact."""
    out = mf._print_hy_spread(FULL_REGIME)
    assert "2.84" not in out["text"], out
    assert "2.8%" in out["text"], out


def test_the_folded_lead_fits_the_macro_number_budget():
    """A macro post is allowed two distinct numbers. The lead fact carries the
    anchor's pair and nothing else, so the writer can quote it whole."""
    text = EXPECTED_PRINTS["print_jobless_claims"]
    assert cw.number_soup_violations(text, kind="macro") == []


# ─────────────────────────────────────────────────────────────────────────────
# 21-23. The auditor rubric
# ─────────────────────────────────────────────────────────────────────────────

def test_the_auditor_can_cut_for_esoterica():
    from engine.marketing import copy_auditor as ca
    codes = {c for c, _ in ca.AUDIT_CRITERIA}
    assert "esoteric" in codes, sorted(codes)


def test_the_esoteric_criterion_carries_the_operators_own_words():
    """The paraphrase is what let it through the first time: `no_value` was
    already in the rubric and did not catch a post that carries a fact and a
    stance."""
    from engine.marketing import copy_auditor as ca
    desc = dict(ca.AUDIT_CRITERIA)["esoteric"].lower()
    assert "no one knows what it's talking about" in desc, desc
    assert "growth data" in desc and "the tape" in desc, desc
    assert "esoteric" in ca._system_prompt()


def test_the_new_cut_code_has_a_plain_word_on_the_operator_surface():
    """A raw slug on an operator surface is the banned vocabulary the design
    doctrine names."""
    import importlib
    fl = importlib.import_module("admin.marketing_floor")
    src = Path(fl.__file__).read_text(encoding="utf-8")
    assert '"esoteric": "gestures at macro without naming a print"' in src


def test_the_adjective_first_form_is_caught_too():
    """ONE DIRECTION OF A SYMMETRIC CONSTRUCTION IS HALF A GATE. Found by
    running the finished rule over the live queue: the verb patterns read
    "growth firming", and ob-2026-07-30-6003875d0e writes it the other way
    round."""
    text = ("5 of 11 sectors closed green today as tech led the selloff.\n"
            "With 5 of 11 sectors green, soft growth, warm inflation and "
            "looser liquidity aren't giving me much to chase.")
    hits = cw.anchorless_macro_violations(text, "macro")
    assert hits, text
    for phrase in ("soft growth", "warm inflation", "sticky inflation",
                   "firmer growth", "cooler inflation"):
        assert cw.anchorless_macro_violations(
            f"{phrase} and nothing much else to say.", "macro"), phrase


def test_a_negative_print_reads_as_english_not_as_a_minus_sign():
    """The month a series goes negative is the month the post matters most, and
    a signed format would ship "running at a -1.2% annual rate" on it."""
    deflation = {"conditions": {"inflation_nowcast": {"median_cpi": -1.2}}}
    out = mf._print_median_cpi(deflation)
    assert out["text"] == (
        "The Cleveland Fed's median CPI is falling at a 1.2% annual rate."), out
    assert "-1.2" not in out["text"]
    contraction = {"conditions": {"growth_nowcast": {"gdpnow": -2.4}}}
    assert mf._print_gdpnow(contraction)["text"] == (
        "The Atlanta Fed's GDPNow has the economy shrinking at a 2.4% annual "
        "rate this quarter.")
    surge = {"conditions": {"labor_nowcast": {"initial_claims_4wk": 5_800_000.0,
                                              "claims_yoy_pct": 420.0}}}
    assert "5.8 million a week" in mf._print_jobless_claims(surge)["text"]


def test_the_anchored_lead_still_fits_a_deterministic_post(tmp_path):
    """REGRESSION PIN, and it caught a real one. The first draft of the anchor
    sentences ran 183 chars in the lead fact, and `{top_fact}` is interpolated
    whole into the deterministic templates: the live macro post came out at 279
    against a 275-char cap, so every macro slot would have failed
    `validate_copy` on LENGTH and dropped to nothing. A packet that mints copy
    its own templates cannot render is not a fix.

    Exercised on the LONGEST print rather than the top-ranked one, because rank
    and length are independent and the cap is about the worst case.
    """
    longest = max((mf._NAMED_PRINT_BUILDERS[i](FULL_REGIME)["text"]
                   for i in range(len(mf._NAMED_PRINT_BUILDERS))), key=len)
    assert len(longest) <= 90, (len(longest), longest)

    _write(tmp_path, "data/regime/latest.json", FULL_REGIME)
    for kind in ("macro", "event"):
        fd = mf.macro_facts(tmp_path) if kind == "macro" else mf.event_facts(tmp_path)
        assert len(fd["facts"][0]["text"]) <= 170, fd["facts"][0]
        for slot in ("D1-AM", "D2-PM", "D3-AM"):
            ctx = cw.build_context(
                {"ticker": "", "type": kind, "account": "flagship"},
                persona={"name": "T", "voice_notes": "Emoji budget: 0",
                         "example_lines": []},
                facts=fd)
            ctx.update(voice="authoritative desk", slot=slot, type=kind,
                       as_of="2026-08-01")
            post = cw.write_posts_deterministic([ctx])[0]
            headline, body = post.get("headline", ""), post.get("body", "")
            assert cw.validate_copy(headline, body, ctx) == [], (kind, slot,
                                                                headline, body)
            assert cw.anchorless_macro_violations(
                f"{headline} {body}", kind) == [], (kind, slot)
