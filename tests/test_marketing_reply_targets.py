"""Reply-desk author register — curation guards for config/reply_targets.yml.

`tests/test_marketing_reply_desk.py::TestAuthorRegister` already pins the
SCHEMA: that the file parses, that a bad tier fails, that one author cannot be
registered to two desks. This file pins the CURATION, which is a different
subject with different failure modes:

  * a placeholder handle is a silently dark desk — `register_for_account`
    filters it, discovery polls nothing, and the tick reads as "quiet" rather
    than "unwired" (the exact failure the whole reply-desk audit named);
  * a handle with no WHY note is a curation decision nobody can review or
    revisit six months later;
  * an entry shipped `enabled: true` is a builder deciding who the company
    talks to in public, which is not a builder's call to make.

Stdlib + pyyaml only. Nothing here touches the network — the handles were
verified live against twitterapi.io once, at authoring time, and re-verifying
on every CI run would spend the shared twitterapi.io bucket to test a YAML file.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.marketing import reply_discovery as rd  # noqa: E402

REGISTER_PATH = ROOT / "config" / "reply_targets.yml"

#: Desks that must carry a curated starter list. `founder` is excluded on
#: purpose and pinned as empty below — the founder curates his own room.
CURATED_DESKS = ("kelly", "cici", "sophia", "meagan", "flagship")


@pytest.fixture(scope="module")
def register() -> dict:
    return rd.load_register(ROOT)


@pytest.fixture(scope="module")
def entries(register: dict) -> list[tuple[str, dict]]:
    """(desk, entry) for every author entry in the file, enabled or not.

    `register_for_account` cannot be used here: it drops disabled entries, and
    every entry in this file is disabled by design, so it would return an empty
    list and every assertion below would pass vacuously.
    """
    out: list[tuple[str, dict]] = []
    for desk, block in (register.get("accounts") or {}).items():
        for entry in (block or {}).get("authors") or []:
            out.append((desk, entry))
    return out


class TestRegisterIsCurated:
    def test_no_placeholder_handles_remain(self, entries):
        """A PLACEHOLDER_* handle is a dark desk that reports as a quiet one."""
        bad = [f"{d}:{e.get('handle')}" for d, e in entries
               if "PLACEHOLDER" in str(e.get("handle") or "").upper()]
        assert bad == [], f"placeholder handles still in the register: {bad}"

    def test_every_curated_desk_has_targets(self, register):
        empty = [d for d in CURATED_DESKS
                 if not ((register["accounts"].get(d) or {}).get("authors") or [])]
        assert empty == [], f"desks with no curated targets: {empty}"

    def test_founder_register_stays_empty(self, register):
        """Charter §1: the founder curates his own conversations."""
        assert (register["accounts"].get("founder") or {}).get("authors") == []

    def test_every_entry_carries_the_required_fields(self, entries):
        for desk, entry in entries:
            where = f"{desk}:{entry.get('handle')}"
            assert str(entry.get("handle") or "").strip(), f"{where}: empty handle"
            assert entry.get("tier") in rd.TIERS, f"{where}: bad tier {entry.get('tier')!r}"
            assert "enabled" in entry, f"{where}: must state `enabled` explicitly"
            assert isinstance(entry.get("notes"), str), f"{where}: missing notes"

    def test_every_handle_carries_a_one_line_why(self, entries):
        """The note answers "what is this audience, why this desk" — a bare
        label is not a curation record, it is a name."""
        for desk, entry in entries:
            note = str(entry.get("notes") or "")
            where = f"{desk}:{entry.get('handle')}"
            assert len(note) >= 60, f"{where}: WHY note too thin to review ({note!r})"
            assert "\n" not in note, f"{where}: note must stay one line"

    def test_handles_are_bare(self, entries):
        for desk, entry in entries:
            handle = str(entry.get("handle") or "")
            assert not handle.startswith("@"), f"{desk}:{handle}: leading '@'"
            assert " " not in handle, f"{desk}:{handle}: whitespace in handle"
            assert "/" not in handle, f"{desk}:{handle}: looks like a URL, not a handle"


#: The handles the OPERATOR ratified, 2026-08-02 ("enable all 21 handles, but
#: spread across accs"). This list is the editorial decision, written down.
#: It is not documentation of the file — it is the independent record the file
#: is checked against, which is the whole mechanism: a builder who enables a new
#: handle must come here to do it, and coming here is the review.
RATIFIED_2026_08_02: frozenset[str] = frozenset({
    # cici — China / FX / cross-border, her session
    "michaelxpettis", "Brad_Setser", "AxelMerk", "SantiagoAuFund",
    # sophia — the Fed narrative desk
    "DiMartinoBooth", "LizAnnSonders", "TimDuy", "SteveMatthews12",
    # kelly — rates, vol and the traders who answer levels
    "biancoresearch", "donnelly_brent", "options_insight", "MacroAlf",
    "TheBondFreak",
    # meagan — retail-facing explainers, high reply volume
    "KobeissiLetter", "StockMKTNewz", "Geiger_Capital", "amitisinvesting",
    # flagship — ETF / flow / quant analysts
    "unusual_whales", "EricBalchunas", "choffstein", "badcharts1",
})


class TestEnablingIsTheOperatorsCall:
    """THE gate on this file, in its post-ratification form.

    Before 2026-08-02 this class asserted that NOTHING was enabled: a builder
    proposes the room, the operator decides who we actually talk to, and an
    entry arriving `enabled: true` from a code change had skipped the only
    editorial review there is.

    The operator has now made that call for the 21 seeded handles. Deleting the
    gate would have been the wrong way to record it — the risk it guards
    (someone quietly widening the company we keep in public) is unchanged for
    handle 22. So the gate inverted rather than lifted: the live set must equal
    the ratified set EXACTLY. Enabling a new handle now fails until it is added
    to `RATIFIED_2026_08_02` above, and that edit is the review.
    """

    def test_the_live_set_is_exactly_what_the_operator_ratified(self, entries):
        live = {str(e.get("handle")) for _d, e in entries if e.get("enabled") is True}
        extra = sorted(live - RATIFIED_2026_08_02)
        missing = sorted(RATIFIED_2026_08_02 - live)
        assert not extra, (
            f"enabled without an operator decision: {extra} — add them to "
            "RATIFIED_2026_08_02 only when the operator has actually said so")
        assert not missing, (
            f"ratified but no longer enabled: {missing} — if the operator "
            "parked them, drop them from RATIFIED_2026_08_02 in the same change")

    def test_every_ratified_handle_is_real_and_placed(self, entries):
        """A ratified handle that is not in the file is a typo that reads as a
        decision. Both directions are checked because only one of them fails
        loudly on its own."""
        placed = {str(e.get("handle")): d for d, e in entries}
        for h in sorted(RATIFIED_2026_08_02):
            assert h in placed, f"{h} is ratified but absent from the register"

    def test_the_desks_carry_their_own_handles(self, register):
        """Spread, not a pile on one desk — the operator asked for it explicitly
        ("spread across accs"). founder is deliberately empty and is excluded."""
        counts = {d: len(rd.register_for_account(register, d))
                  for d in register["accounts"]}
        staffed = {d: n for d, n in counts.items() if n}
        assert len(staffed) >= 5, f"targets pooled onto too few desks: {counts}"
        assert max(staffed.values()) <= 8, f"one desk is carrying the register: {counts}"

    def test_header_states_who_owns_enabling(self):
        text = REGISTER_PATH.read_text(encoding="utf-8")
        assert "ENABLING IS THE OPERATOR'S EDITORIAL CALL" in text
        assert "STARTER PROPOSAL" in text


class TestTierPortfolio:
    def test_tiers_are_a_portfolio_not_a_pile(self, register):
        """Constitution §9.2 asks for all three tiers; the charter weights
        relationship and conversion above reach. A desk that is all breakout is
        a desk shouting under giant posts."""
        for desk in CURATED_DESKS:
            tiers = [e.get("tier") for e in register["accounts"][desk]["authors"]]
            assert "relationship" in tiers or "conversion" in tiers, (
                f"{desk}: no relationship or conversion target — reach only")
            assert tiers.count("breakout") <= 1, (
                f"{desk}: {tiers.count('breakout')} breakout targets; "
                "breakout is an occasional entry, not a strategy")

    def test_breakout_entries_are_rare_fleet_wide(self, entries):
        breakout = [f"{d}:{e['handle']}" for d, e in entries if e.get("tier") == "breakout"]
        total = len(entries)
        assert len(breakout) <= max(1, total // 8), (
            f"{len(breakout)}/{total} entries are breakout tier: {breakout}")


class TestRegisterMatchesTheFleet:
    def test_every_register_desk_is_a_real_account(self):
        cfg = yaml.safe_load((ROOT / "config" / "marketing.yml").read_text(encoding="utf-8"))
        known = {a["id"] for a in (cfg.get("desk_network") or {}).get("accounts") or []}
        reg = rd.load_register(ROOT)
        unknown = set(reg["accounts"]) - known
        assert unknown == set(), f"register blocks for unknown accounts: {sorted(unknown)}"

    def test_beats_are_present_for_scoring(self, register):
        """`reply_score.features` scores beat-fit off these; an empty list makes
        beat_fit constant and silently deletes a scoring dimension."""
        for desk in CURATED_DESKS:
            beats = register["accounts"][desk].get("beats") or []
            assert len(beats) >= 4, f"{desk}: only {len(beats)} beats for beat-fit scoring"
