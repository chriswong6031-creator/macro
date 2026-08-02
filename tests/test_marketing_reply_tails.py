"""tests/test_marketing_reply_tails.py — the reply TAIL register acceptance suite.

Program: X Growth reply desk, the WELDED-TAIL fix (2026-08-01).
Doctrine: research/MARKETING_REPLY_DOCTRINE_BY_FABLE.md §11.8 (the doorway,
re-ranked) and §12 (the warmth amendment).

THE DEFECT THIS SUITE PINS. ``reply_drafter.compose()`` builds
``[warmth opener] + [gift] + [body/doorway]``. The warmth register differentiated
only the OPENER; the body's closing sentence was ONE FIXED STRING PER FAMILY,
byte-identical across every persona, every warmth move and every thread. Measured
on the pre-fix code with four personas x every family x every lawful warmth move:

    missing_variable        "The price move is the reaction. Credit is the test."   x33
    second_order            "If that holds, the pressure shows up in credit ..."    x33
    respectful_disagreement "That reads like credit, not semis."                    x33
    human_reaction          "That is the part I'd watch."                           x33

NINE distinct tails for the nine tail-bearing families, full stop. sophia, kelly,
cici and meagan reply into OVERLAPPING fintwit audiences from accounts presented
as different real women, so a byte-identical second sentence across those
accounts is the single most legible bot-farm signature available. It is also the
same welded-tail defect ``copywriter.repeated_closer_violations`` was built for
one lane over (autopsy defect 6: 27% of a week's posts closing on one of nine
sentences) — this desk simply had no equivalent gate.

WHY THE CENSUS TESTS DRIVE ``compose`` AND NOT THE POOL TABLE. A census over
``FAMILY_TAILS`` would be a test of a literal, and would have stayed green on the
pre-fix code only because the symbol did not exist (an AttributeError, not a
finding). Driving the composer means the same assertions were RED against the
shipped code for the right reason: the product surface welded, not a name
missing.

Fixture-driven; ZERO network, ZERO LLM. Import closure is stdlib + pyyaml.
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.marketing import expression_dial as ed  # noqa: E402
from engine.marketing import reply_critics as rc  # noqa: E402
from engine.marketing import reply_drafter as rd  # noqa: E402
from engine.marketing.copywriter import banned_language  # noqa: E402

#: The four real named humans who share an audience. The flagship desk carries no
#: warmth register (charter §2 amendment 3) but DOES draw a tail, so it joins the
#: cross-account collision test below as the fifth live lane.
EMPLOYEES = ("sophia", "kelly", "cici", "meagan")
LIVE_DESKS = EMPLOYEES + ("founder",)

PARENT = "Strong session today, breadth looked fine to me and the tape held up."
GIFT = "Equal weight closed flat while the index added 0.9% and semis added 2.4%."
WHITELIST = ["0.9%", "2.4%"]

#: Distinct parent/thread ids. Real status ids, in shape: the selector keys on
#: this string, so a set of near-identical ids is the HARDER case and is the one
#: worth testing (a weak hash would bucket them all together).
THREADS: tuple[str, ...] = tuple(f"18571234567890{n:02d}" for n in range(40))


@pytest.fixture(scope="module")
def cfg() -> dict:
    return yaml.safe_load((ROOT / "config" / "marketing.yml").read_text(encoding="utf-8"))


def _ctx(account: str, thread_id: str = "", **over) -> dict:
    out = {"subject": "the tape", "mechanism": "breadth", "account": account,
           "detail": "breadth", "thread_id": thread_id}
    out.update(over)
    return out


def _critic_ctx(account: str, cfg: dict, **over) -> dict:
    out = {"account": account, "parent_text": PARENT, "parent_author": "somequant",
           "numbers_whitelist": WHITELIST, "corpus": [], "theses": [], "cfg": cfg,
           "family": "missing_variable"}
    out.update(over)
    return out


def _tail_after_gift(text: str, gift: str = GIFT) -> str:
    """The composed copy that follows the gift, or "" when the family has none.

    Case-insensitive because a ``fuse: "conjunction"`` warmth opener
    decapitalises the gift it runs into.
    """
    low = str(text or "").lower()
    idx = low.find(gift.lower())
    if idx < 0:
        return ""
    return text[idx + len(gift):].strip()


def _lawful_moves(account: str, family: str) -> list[str | None]:
    """``None`` plus every warmth move this desk may ride on this family."""
    moves = rd.warmth_moves_for(
        account, parent_shape="analysis_claim", family=family,
        has_thesis=True, has_detail=True,
    )
    return [None, *moves]


def _compose(family: str, account: str, thread_id: str,
             warmth: str | None = None, **over) -> str:
    return rd.compose(family, GIFT, _ctx(account, thread_id, **over), warmth=warmth)


def _tail_bearing_families() -> list[str]:
    """Families whose composed body carries a doorway sentence after the gift.

    DERIVED FROM ``compose``, never from ``FAMILY_TAILS``. Gates (b) and (c) are
    claims about the PRODUCT, and reading the pool table to decide what to test
    would have made them fail on the pre-fix code with an AttributeError — a
    missing name, not a finding. Driven this way they failed on their own
    assertions, which is the only kind of red that proves a defect.
    """
    return [f for f in rd.family_ids()
            if _tail_after_gift(_compose(f, "kelly", THREADS[0]))]


def _census() -> tuple[Counter, dict[tuple[str, str], Counter]]:
    """(family, tail) counts over personas x families x warmth moves x threads."""
    pairs: Counter = Counter()
    per_desk: dict[tuple[str, str], Counter] = {}
    for family in rd.family_ids():
        for account in EMPLOYEES:
            for move in _lawful_moves(account, family):
                for thread in THREADS[:24]:
                    try:
                        text = _compose(family, account, thread, move)
                    except ValueError:
                        continue          # over-budget opener: a real refusal
                    tail = _tail_after_gift(text)
                    if not tail:
                        continue          # family with no doorway sentence
                    pairs[(family, tail)] += 1
                    per_desk.setdefault((family, account), Counter())[tail] += 1
    return pairs, per_desk


# ===========================================================================
# 1. The census — GATE (a)
# ===========================================================================
class TestTailCensus:
    def test_the_desk_does_not_weld_one_tail_per_family(self):
        """GATE (a). RED on the pre-fix code at every one of the three arms.

        Measured against the shipped composer: 9 distinct (family, tail) pairs,
        every family a single tail, every (family, desk) share 1.00.
        """
        pairs, per_desk = _census()
        assert pairs, "the census drew nothing — the extractor or the grid is broken"

        # (a1) FLOOR on distinct tails. Pre-fix: 9.
        distinct = len(pairs)
        assert distinct >= 100, (
            f"only {distinct} distinct (family, tail) pairs across four desks — "
            "the doorway is welded"
        )

        # (a2) Every tail-bearing family offers a real pool, not a line.
        by_family: dict[str, set[str]] = {}
        for family, tail in pairs:
            by_family.setdefault(family, set()).add(tail)
        assert len(by_family) >= 9, sorted(by_family)
        for family, tails in sorted(by_family.items()):
            assert len(tails) >= 10, (family, len(tails))

        # (a3) BOUND on repeats. Within one desk's draws on one family no single
        # tail may take more than 0.60 of them. Pre-fix: 1.00 everywhere.
        #
        # WHY THE BOUND IS 0.60 AND NOT 0.40. Uniform over a three-line lane is
        # 0.33, but this arm exercises the HASH ALONE over 24 parents: three
        # buckets and 24 draws is a small sample, and a fair hash lands a 14/8/2
        # split often enough that a tighter bar would be a flake, not a finding.
        # The MEASURED worst cell here is cici/callback at 28/48 = 0.583; with a
        # one-deep rotation window (what ``recent_tails`` supplies) the same cell
        # falls to 22/48 = 0.458, which is what the second arm pins. Read the two
        # together: the hash buys divergence, the rotation buys balance, and
        # ``test_a_desk_reaches_every_entry_in_its_own_lane`` separately pins that
        # no entry is unreachable.
        for (family, account), counts in sorted(per_desk.items()):
            total = sum(counts.values())
            top, hits = counts.most_common(1)[0]
            assert hits / total <= 0.60, (
                f"{account}/{family}: {hits}/{total} draws land on {top!r}"
            )

    def test_a_rotation_window_flattens_what_the_hash_leaves_lumpy(self):
        """The second half of the anti-sameness claim, measured.

        The hash alone can leave one lane entry on 0.58 of a desk's draws for one
        family. Feeding back even a ONE-DEEP window — the shallowest history a
        caller can keep — pulls the worst cell under half. This is the arm that
        says what ``recent_tails`` is FOR, so a later "simplification" that drops
        the rotation and keeps the hash has to argue with a number.
        """
        worst = 0.0
        for family in sorted(rd.FAMILY_TAILS):
            for account in EMPLOYEES:
                for move in _lawful_moves(account, family):
                    counts: Counter = Counter()
                    recent: list[str] = []
                    for thread in THREADS[:24]:
                        pick = rd.select_tail(account, family, thread_id=thread,
                                              recent_tails=recent[-1:])
                        counts[pick] += 1
                        recent.append(pick)
                    worst = max(worst, counts.most_common(1)[0][1] / sum(counts.values()))
        assert worst <= 0.50, worst

    def test_the_extractor_sees_a_tail_on_the_families_that_have_one(self):
        """Guards the census against a silently-empty grid.

        A census whose extractor returns "" everywhere passes any floor by
        vacuum. These four families are the ones the defect report measured.
        """
        for family in ("missing_variable", "second_order",
                       "respectful_disagreement", "human_reaction"):
            tail = _tail_after_gift(_compose(family, "kelly", THREADS[0]))
            assert tail, family


# ===========================================================================
# 2. Divergence across desks and threads — GATES (b) and (c)
# ===========================================================================
class TestDivergence:
    def test_two_desks_on_the_same_parent_never_draw_the_same_tail(self):
        """GATE (b). The bot-farm signature, pinned.

        Pre-fix this failed on the first pair of the first family: every desk
        drew the identical sentence.
        """
        families = _tail_bearing_families()
        assert len(families) >= 9, families
        for family in families:
            for thread in THREADS:
                drawn: dict[str, str] = {}
                for account in LIVE_DESKS:
                    tail = _tail_after_gift(_compose(family, account, thread))
                    assert tail, (family, account)
                    clash = [a for a, t in drawn.items() if t == tail]
                    assert not clash, (
                        f"{account} and {clash[0]} both drew {tail!r} on "
                        f"{family} / thread {thread}"
                    )
                    drawn[account] = tail

    def test_one_desk_on_different_parents_draws_different_tails(self):
        """GATE (c). One persona must not wear one sentence all week.

        Driven through ``compose`` alone (pre-fix: 1 tail over 40 parents).
        """
        for family in _tail_bearing_families():
            for account in LIVE_DESKS:
                seen = {_tail_after_gift(_compose(family, account, t))
                        for t in THREADS}
                assert len(seen) >= 3, (
                    f"{account}/{family} drew {len(seen)} distinct tail(s) over "
                    f"40 distinct parents: {sorted(seen)}"
                )

    def test_a_desk_reaches_every_entry_in_its_own_lane(self):
        """The pool-table half of gate (c): 40 parents must not leave an entry
        permanently unreachable, which is how a five-line lane silently becomes
        a two-line one."""
        for family in sorted(rd.FAMILY_TAILS):
            for account in LIVE_DESKS:
                pool = rd.tails_for(account, family)
                assert len(pool) >= 3, (account, family, pool)
                seen = {_tail_after_gift(_compose(family, account, t))
                        for t in THREADS}
                assert len(seen) == len(pool), (
                    f"{account}/{family} reached {len(seen)} of {len(pool)} "
                    "lane entries over 40 distinct parents"
                )

    def test_selection_is_deterministic_for_one_desk_and_one_parent(self):
        """Determinism is the other half of the contract: same desk, same
        parent, same tail, or the desk cannot be reasoned about at all."""
        for family in _tail_bearing_families():
            first = _compose(family, "cici", THREADS[3])
            assert _compose(family, "cici", THREADS[3]) == first

    def test_the_selector_does_not_use_the_randomised_builtin_hash(self):
        """PYTHONHASHSEED randomises ``hash(str)`` per process, so a selector
        built on it would draw a different tail on every nightly run and no
        rotation history could ever match. Pinned by running the selection in a
        SEPARATE interpreter with a hostile seed."""
        import json
        import subprocess

        probe = (
            "import json,sys;sys.path.insert(0,%r);"
            "from engine.marketing import reply_drafter as rd;"
            "print(json.dumps([rd.select_tail(a,'missing_variable',thread_id=t)"
            " for a in ('sophia','kelly','cici','meagan')"
            " for t in ('1857123456789000','1857123456789001')]))" % str(ROOT)
        )
        here = [rd.select_tail(a, "missing_variable", thread_id=t)
                for a in ("sophia", "kelly", "cici", "meagan")
                for t in ("1857123456789000", "1857123456789001")]
        for seed in ("1", "12345"):
            out = subprocess.run(  # noqa: S603
                [sys.executable, "-c", probe], capture_output=True, text=True,
                env={"PATH": "/usr/bin:/bin", "PYTHONHASHSEED": seed},
                check=True,
            )
            assert json.loads(out.stdout) == here, seed


# ===========================================================================
# 3. Rotation — GATE (d)
# ===========================================================================
class TestRotationWindow:
    def test_a_tail_cannot_repeat_inside_its_rotation_window(self):
        """GATE (d). The hash alone cannot promise this: two parents can land on
        one lane entry, and an account that draws the same closer three nights
        running has welded its own tail without any help from its siblings.

        Driven through ``compose`` on ONE fixed thread, which is the hardest
        case: without the rotation the hash returns the identical tail forever.

        HONEST NOTE ON ITS RED. Unlike gates (a), (b) and (c) this one cannot be
        expressed against the pre-fix composer at all — ``recent_tails`` did not
        exist, so the old code fails it on a missing name rather than on the
        assertion. Its real proof is the MUTATION: deleting the rotation branch
        from ``select_tail`` and leaving the hash in place turns this red on
        ``assert tail not in drawn`` while every other test in the suite stays
        green.
        """
        for family in sorted(rd.FAMILY_TAILS):
            for account in LIVE_DESKS:
                pool = rd.tails_for(account, family)
                recent: list[str] = []
                drawn: list[str] = []
                for _ in range(len(pool)):
                    text = _compose(family, account, THREADS[0],
                                    recent_tails=list(recent))
                    tail = _tail_after_gift(text)
                    assert tail not in drawn, (account, family, tail, drawn)
                    drawn.append(tail)
                    recent.append(rd.select_tail(
                        account, family, thread_id=THREADS[0],
                        recent_tails=list(recent)))
                assert len(set(drawn)) == len(pool), (account, family, drawn)

    def test_a_saturated_window_falls_back_to_least_recently_used(self):
        """A window wider than the lane must not raise, return "", or pin one
        entry: it degrades to least-recently-used.

        THE SECOND CASE SEPARATES LRU FROM ``recent.index``. On a window that
        REPEATS an entry, "first occurrence" (the idiom ``rotate_family`` uses)
        hands back the tail used a moment ago; only "last occurrence" is LRU. A
        rotation that re-picks the most recent entry is the weld coming back
        through the mechanism that was supposed to prevent it.
        """
        pool = rd.tails_for("kelly", "missing_variable")
        assert len(pool) >= 3, pool
        pick = rd.select_tail("kelly", "missing_variable", thread_id=THREADS[0],
                              recent_tails=list(pool) * 2)
        assert pick == pool[0], (pick, pool[0])

        repeated = [pool[1], pool[2], pool[0], pool[1], pool[2]]
        assert rd.select_tail("kelly", "missing_variable", thread_id=THREADS[0],
                              recent_tails=repeated) == pool[0]

    def test_draft_reply_reports_the_tail_it_used(self, cfg):
        """Rotation history is only recordable if the drafter says what it drew,
        exactly as it already reports ``family`` and ``warmth``."""
        target = {"subject": "the tape", "mechanism": "breadth", "text": PARENT,
                  "author": "somequant", "thread_root_id": THREADS[5]}
        facts = {"facts": [{"id": "f1", "text": GIFT, "salience": 1.0}],
                 "numbers_whitelist": WHITELIST}
        out = rd.draft_reply(account="kelly", target=target, facts=facts,
                             cfg=cfg, n_alts=2)
        assert out["tail"] in rd.tails_for("kelly", out["family"])
        assert isinstance(out["alt_tails"], list)
        assert len(out["alt_tails"]) == len(out["alt_drafts"])
        # THE REPORT MUST BE THE COPY. `draft_reply` selects once for the record
        # and `compose` selects again for the text; if those two ever disagree
        # the rotation history would record a doorway that never shipped.
        ctx = {"subject": target["subject"], "mechanism": target["mechanism"]}
        for tail, draft in zip([out["tail"], *out["alt_tails"]],
                               [out["draft"], *out["alt_drafts"]]):
            assert rd.render_tail(tail, ctx) in draft, (tail, draft)
        # ... and one item never closes two of its drafts on the same line.
        drawn = [t for t in [out["tail"], *out["alt_tails"]] if t]
        assert len(set(drawn)) == len(drawn), drawn

    def test_draft_reply_honours_recent_tails(self, cfg):
        """The parameter is threaded, not decorative."""
        target = {"subject": "the tape", "mechanism": "breadth", "text": PARENT,
                  "author": "somequant", "thread_root_id": THREADS[6]}
        facts = {"facts": [{"id": "f1", "text": GIFT, "salience": 1.0}],
                 "numbers_whitelist": WHITELIST}
        first = rd.draft_reply(account="kelly", target=target, facts=facts,
                               cfg=cfg, n_alts=0)
        again = rd.draft_reply(account="kelly", target=target, facts=facts,
                               cfg=cfg, n_alts=0,
                               recent_tails=[first["tail"]],
                               family=first["family"])
        assert again["tail"] != first["tail"], first["tail"]


# ===========================================================================
# 4. The pools themselves — register fit, the doorway law, GATE (e)
# ===========================================================================
class TestPoolShape:
    def test_every_tail_bearing_family_declares_a_pool(self):
        for family in sorted(rd.FAMILY_TAILS):
            assert family in rd.FAMILIES, family
            lanes = rd.FAMILY_TAILS[family]
            assert rd.TAIL_DEFAULT_LANE in lanes, family
            for account in EMPLOYEES:
                assert account in lanes, (family, account)
            for lane, pool in sorted(lanes.items()):
                assert 3 <= len(pool) <= 5, (family, lane, len(pool))
                assert len(set(pool)) == len(pool), (family, lane)

    def test_the_lanes_are_pairwise_disjoint(self):
        """THE GUARANTEE BEHIND GATE (b), stated where it is created.

        Cross-desk divergence is NOT a property of the hash: with a shared pool
        of five and four desks, two desks collide on ~19% of threads by simple
        counting. It holds because the lanes share no string, so the collision
        is unreachable rather than unlikely.
        """
        for family, lanes in sorted(rd.FAMILY_TAILS.items()):
            seen: dict[str, str] = {}
            for lane, pool in sorted(lanes.items()):
                for tail in pool:
                    assert tail not in seen, (family, tail, lane, seen[tail])
                    seen[tail] = lane

    def test_no_template_appears_under_two_families(self):
        """THE INVARIANT THAT KEEPS ONE ITEM'S DRAFTS APART.

        `draft_reply` builds its alternates from DIFFERENT families, so its
        primary and alternates cannot close on the same line — but only while the
        pools are family-scoped. An earlier version of the loop fed each drawn
        tail back into the rotation window to enforce this; a mutation test showed
        that branch was unreachable, so the guarantee is pinned HERE, where it
        actually lives, rather than by dead code that looked like it was working.
        """
        owner: dict[str, str] = {}
        for family, lanes in sorted(rd.FAMILY_TAILS.items()):
            for pool in lanes.values():
                for tail in pool:
                    assert owner.get(tail, family) == family, (
                        tail, family, owner[tail])
                    owner[tail] = family

    def test_the_doorway_law_holds_and_question_form_stays_capped(self):
        """§11.8: the question is the WEAKEST doorway form and the verdict the
        strongest. Only ``author_question`` — the family whose whole move is one
        precise question — may close on a question mark."""
        for family, lanes in sorted(rd.FAMILY_TAILS.items()):
            for lane, pool in sorted(lanes.items()):
                for tail in pool:
                    if family == "author_question":
                        assert tail.rstrip().endswith("?"), (family, lane, tail)
                    else:
                        assert "?" not in tail, (family, lane, tail)

    def test_no_rendered_tail_doubles_an_article(self):
        """"a the tape story" is a typo with our name on it.

        A slot value may carry its own determiner ("the tape", "the curve", and
        the subject fallback "the move" itself), so a template that reads
        naturally before a bare noun doubles the article. Pinned across the
        determiner-carrying values a real target actually supplies. NOT a
        regression this build introduced: it fires on the two lines the shipped
        composer already used, which is why the guard sits at the render layer.
        """
        doubled = re.compile(r"\b(?:an?|the)\s+(?:an?|the)\b", re.IGNORECASE)
        for family, lanes in sorted(rd.FAMILY_TAILS.items()):
            for lane, pool in sorted(lanes.items()):
                for tail in pool:
                    for subject in ("the tape", "the move", "capex", "NVDA"):
                        for lead in ("credit", "the curve", "breadth"):
                            out = rd.render_tail(
                                tail, {"subject": subject, "mechanism": lead})
                            assert not doubled.search(out), (family, lane, out)

    def test_the_article_guard_does_not_eat_a_share(self):
        """MUTATION PIN. Written with ``re.IGNORECASE`` the guard swallows the
        "the" in "the A-share market" — live China-desk vocabulary, and the exact
        false positive that makes a cleanup guard cost more than it fixes."""
        assert rd._fix_article_collision(
            "the A-share market held") == "the A-share market held"
        assert rd._fix_article_collision("a the tape story") == "the tape story"
        assert rd._fix_article_collision("The the curve side") == "The curve side"

    def test_no_tail_introduces_a_figure(self):
        """``fact_discipline`` is satisfiable by construction only while grip and
        doorway carry no number of their own."""
        for family, lanes in sorted(rd.FAMILY_TAILS.items()):
            for lane, pool in sorted(lanes.items()):
                for tail in pool:
                    rendered = rd.render_tail(tail, _ctx("kelly"))
                    assert not rc.number_tokens(rendered), (family, lane, tail)

    def test_every_tail_clears_the_house_ban_the_dial_and_am_r1(self):
        """The same three guards ``openers_for`` runs on warmth copy.

        A tail its own persona guards reject is worse than the constant it
        replaced: it would cost a whole item at critic time instead of reading
        cold.
        """
        for family, lanes in sorted(rd.FAMILY_TAILS.items()):
            for account in LIVE_DESKS:
                lane = rd.tail_lane(account)
                for tail in lanes[lane]:
                    probe = rd.render_tail(tail, _ctx(account))
                    assert not banned_language(probe), (account, family, tail)
                    assert not ed.am_r1_hits(probe), (account, family, tail)
                    assert not ed.violations("", probe, account=account,
                                             kind="reply", include_house_bans=False), \
                        (account, family, tail)

    def _ban_words(self, monkeypatch, account: str, *words: str) -> None:
        """Add *words* to this desk's codex ``banned`` list, live."""
        import dataclasses
        real = ed.codex_index().get(account)
        assert real is not None, account
        patched = dataclasses.replace(
            real, banned=(*real.banned, *(w.lower() for w in words)))
        monkeypatch.setattr(
            ed, "codex_for",
            lambda a, **k: patched if a == account else ed.codex_index().get(a))
        rd.clear_tail_cache()

    def test_the_guard_sweep_is_what_decides_availability(self, monkeypatch):
        """Same mechanism as the warmth openers: a word added to a codex
        ``banned`` list withdraws the offending tail the same night, with no code
        change here. Driven by BANNING A WORD a shipped tail actually uses.
        """
        family, account = "missing_variable", "kelly"
        pool = rd.tails_for(account, family)
        rendered = [rd.render_tail(t, _ctx(account)) for t in pool]
        # A word in exactly ONE entry, so the assertion is about that entry and
        # not about the whole-lane fallback below.
        word = next(w.strip(".,:") for w in rendered[0].split()
                    if w.isalpha() and len(w) > 4
                    and sum(w in r for r in rendered) == 1)
        try:
            self._ban_words(monkeypatch, account, word)
            after = rd.tails_for(account, family)
            assert pool[0] not in after, (word, pool[0])
            assert len(after) == len(pool) - 1, after
        finally:
            monkeypatch.undo()
            rd.clear_tail_cache()

    def test_a_wiped_lane_falls_to_the_default_lane_not_to_unswept_copy(
            self, monkeypatch, capsys):
        """THE FAIL DIRECTION, pinned.

        Shipping the unswept lane so the reply keeps a doorway would put copy the
        persona's own guard just rejected in front of a hostile audience under a
        real woman's name — strictly worse than the welded constant this build
        replaced. So: the neutral ``_default`` lane first (swept against THIS
        account), and if that is gone too, no doorway at all plus a GitHub
        annotation.
        """
        family, account = "missing_variable", "kelly"
        # One word per entry of kelly's lane, none of which the `_default` lane
        # uses — so this wipes her lane and leaves the neutral one standing.
        try:
            self._ban_words(monkeypatch, account,
                            "symptom", "nobody", "downstream")
            fallback = rd.tails_for(account, family)
            assert fallback, "the default lane should have covered this"
            assert set(fallback) <= set(
                rd.FAMILY_TAILS[family][rd.TAIL_DEFAULT_LANE])
            assert not set(fallback) & set(rd.FAMILY_TAILS[family][account])
        finally:
            monkeypatch.undo()
            rd.clear_tail_cache()

        # ... and when the default lane is gone too: no doorway, and it SAYS so
        # at the start of the line, where GitHub can see it.
        try:
            self._ban_words(monkeypatch, account, "the")
            assert rd.tails_for(account, family) == []
            assert rd.compose(family, GIFT, _ctx(account, THREADS[0])) == GIFT
            line = capsys.readouterr().out.strip().splitlines()[-1]
            assert line.startswith("::warning title=reply_tail_pool_empty::"), line
        finally:
            monkeypatch.undo()
            rd.clear_tail_cache()


# ===========================================================================
# 5. GATE (e) — the real critics, not a copy of their rules
# ===========================================================================
class TestEveryTailClearsTheCriticRoster:
    def test_every_drawable_tail_clears_the_whole_roster(self, cfg):
        """GATE (e), driven through ``reply_critics.run_critics`` itself.

        Not a re-implementation of the rules: the roster is imported and run, so
        a critic added or tightened upstream binds this copy the same night.
        """
        assert len(rc.CRITICS) == 13, rc.CRITICS
        checked = 0
        for family, lanes in sorted(rd.FAMILY_TAILS.items()):
            for account in LIVE_DESKS:
                for tail in lanes[rd.tail_lane(account)]:
                    body = f"{GIFT}\n\n{rd.render_tail(tail, _ctx(account))}"
                    verdict = rc.run_critics(
                        body, _critic_ctx(account, cfg, family=family))
                    assert verdict["verdict"] == "pass", (
                        account, family, tail, verdict["reasons"])
                    checked += 1
        assert checked >= 100, checked

    def test_every_composed_draft_clears_the_whole_roster(self, cfg):
        """The tail in situ, with the warmth opener in front of it — where a
        register collision (two framing devices, an over-budget dial) would
        actually fire."""
        for family in sorted(rd.FAMILY_TAILS):
            for account in EMPLOYEES:
                for move in _lawful_moves(account, family):
                    for thread in THREADS[:4]:
                        try:
                            text = _compose(family, account, thread, move)
                        except ValueError:
                            continue
                        verdict = rc.run_critics(
                            text, _critic_ctx(account, cfg, family=family,
                                              warmth=move))
                        assert verdict["verdict"] == "pass", (
                            account, family, move, verdict["reasons"])


# ===========================================================================
# 6. The seam back into the composer
# ===========================================================================
class TestComposerSeam:
    def test_the_composed_body_actually_carries_the_selected_tail(self):
        for family in sorted(rd.FAMILY_TAILS):
            for account in LIVE_DESKS:
                picked = rd.select_tail(account, family, thread_id=THREADS[9])
                rendered = rd.render_tail(picked, _ctx(account, THREADS[9]))
                text = _compose(family, account, THREADS[9])
                assert rendered in text, (account, family, rendered)

    def test_an_unknown_desk_falls_to_the_default_lane_and_still_varies(self):
        """A desk with no codex is a REAL case (the pseudonymous D13 specs), and
        it must not crash, blank the doorway, or weld to one line."""
        seen = {_tail_after_gift(_compose("missing_variable", "nobody", t))
                for t in THREADS}
        assert len(seen) == len(rd.FAMILY_TAILS["missing_variable"][rd.TAIL_DEFAULT_LANE])

    def test_a_callback_tail_still_carries_the_prior_when_there_is_one(self):
        with_prior = _compose("callback", "sophia", THREADS[2],
                              callback="short rates lead credit")
        assert "short rates lead credit" in with_prior
        without = _compose("callback", "sophia", THREADS[2])
        assert "short rates lead credit" not in without
        assert without.rstrip().endswith(".")

    def test_the_families_with_no_doorway_sentence_are_unchanged(self):
        """SCOPE PIN. The fix is the welded TAIL. The families whose frame is a
        PREFIX (``compression``'s "Short version:", ``correction``'s "One thing
        worth fixing in the thread:") are a separate weld and are deliberately
        not touched here — a later build must not read this suite as covering
        them."""
        for family in ("compression", "correction", "original_chart",
                       "acknowledgment_plus_one", "micro_framework"):
            assert family not in rd.FAMILY_TAILS
            assert _tail_after_gift(_compose(family, "kelly", THREADS[0])) == ""
