"""Tests for the shared A-share code->ticker mapper (collectors/china_analyst.to_ticker).

`to_ticker` is NOT private to the analyst forecast store: thirteen Eastmoney collectors
import it (china_lhb, china_zt_pool, china_block_trades, china_buyback, china_unlocks,
china_preannounce, china_margin_detail, china_pledge, china_st, china_comment,
china_earnings, china_cgb_curve, plus engine/china_special_situations), so every bad
suffix it mints is written into a tracked store and rendered.

The defect this file pins: the Beijing Stock Exchange has issued 920xxx codes since the
2023 renumbering. A bare `c[0] == "9"` Shanghai test swallowed them and stamped `.SS` —
a ticker that does not exist — and the function's own `.BJ` branch could never see them.
Eastmoney itself labels these BEIJING (see the captured 920178 锐翔智能 row in
tests/test_china_reports_collector.py, `"market": "BEIJING"`).

BOTH halves are pinned deliberately. The naive repair — deleting `"9"` from the Shanghai
test — silently drops 900xxx Shanghai B-shares, which are real and DO belong on `.SS`
(237 of them sit in data/china_lhb/events.parquet today). A fix that routes 920xxx
correctly while dropping or misrouting 900xxx is not a fix.

Pure/offline: the mapper is a total function of its argument, no network, no storage.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors.china_analyst import to_ticker  # noqa: E402
from collectors.china_ths_concepts import to_suffixed  # noqa: E402
from engine.entity_resolver import cn_code_to_ticker  # noqa: E402


# --- the defect: Beijing's 920xxx code space -------------------------------------- #
# Real BSE listings under the post-2023 numbering.
BEIJING_920 = ["920045", "920178", "920807", "920914", "920002", "920008"]


@pytest.mark.parametrize("code", BEIJING_920)
def test_920xxx_is_beijing_not_shanghai(code):
    """920xxx is Beijing Stock Exchange. Stamping `.SS` mints a nonexistent ticker."""
    assert to_ticker(code) == f"{code}.BJ"


@pytest.mark.parametrize("code", BEIJING_920)
def test_920xxx_never_maps_to_shanghai_or_shenzhen(code):
    """The specific corruption found in nine tracked stores: 920xxx.SS (and a legacy
    920xxx.SZ era). Neither suffix may ever come back."""
    got = to_ticker(code)
    assert got is not None, f"{code} must resolve, not drop"
    assert not got.endswith(".SS"), f"{code} -> {got}: 920xxx is not Shanghai"
    assert not got.endswith(".SZ"), f"{code} -> {got}: 920xxx is not Shenzhen"


# --- the other half: 900xxx Shanghai B-shares must SURVIVE the fix ---------------- #
# Deleting "9" from the Shanghai test to kill the 920xxx bug would drop all of these.
SHANGHAI_900 = ["900001", "900932", "900957"]


@pytest.mark.parametrize("code", SHANGHAI_900)
def test_900xxx_b_shares_stay_shanghai(code):
    """900xxx are Shanghai B-shares — real, present in the live tape, and `.SS`."""
    assert to_ticker(code) == f"{code}.SS"


def test_the_two_nine_prefixed_spaces_do_not_collide():
    """One assertion holding both halves at once, so a regression on either fails here."""
    assert to_ticker("900001") == "900001.SS"
    assert to_ticker("920178") == "920178.BJ"


# --- the rest of the code space must not drift ------------------------------------ #
@pytest.mark.parametrize("code,want", [
    ("600000", "600000.SS"),   # Shanghai main
    ("601398", "601398.SS"),
    ("688981", "688981.SS"),   # STAR (already covered by the 6 test)
    ("000001", "000001.SZ"),   # Shenzhen main
    ("002415", "002415.SZ"),
    ("300750", "300750.SZ"),   # ChiNext
    ("200011", "200011.SZ"),   # Shenzhen B-share
    ("430047", "430047.BJ"),   # Beijing, legacy 4xxxxx
    ("830799", "830799.BJ"),   # Beijing, legacy 8xxxxx
])
def test_known_code_space(code, want):
    assert to_ticker(code) == want


@pytest.mark.parametrize("bad", ["1234567", "910000", "999999", "980000"])
def test_unassigned_nine_space_and_overlong_codes_return_none(bad):
    """Narrowing Shanghai from `9xxxxx` to `900xxx` closes the unassigned 9-interior:
    910000/999999 used to mint `.SS` tickers for codes no exchange has issued. The only
    real 9-prefixed A-share spaces are 900xxx (Shanghai B) and 92xxxx (Beijing).

    Thirteen collectors rely on the None to skip non-stock rows (index codes and header
    junk carried in the same Eastmoney frames)."""
    assert to_ticker(bad) is None


def test_short_codes_are_zero_padded_like_the_collectors_expect():
    """Eastmoney sometimes serves codes with the leading zeros stripped."""
    assert to_ticker("1") == "000001.SZ"
    assert to_ticker(600000) == "600000.SS"


@pytest.mark.parametrize("blank", ["", "abcdef", None])
def test_blank_codes_keep_their_pre_existing_zero_padded_behaviour(blank):
    """CHARACTERISATION, not an endorsement. A blank/undigited code zfills to '000000'
    and resolves to a real-looking `000000.SZ` rather than None — a latent defect that
    predates the Beijing fix and is deliberately NOT changed here (it would move row
    counts in all thirteen importing collectors).

    It is pinned so the Beijing fix provably does not disturb it, and so the day someone
    does repair it, this assertion is what tells them the blast radius. Currently inert:
    zero `000000.*` rows exist in any tracked china store — the Eastmoney frames these
    collectors read always carry a real code."""
    assert to_ticker(blank) == "000000.SZ"


# --- cross-mapper agreement -------------------------------------------------------- #
# collectors/china_ths_concepts.to_suffixed is the landed house reference; it has mapped
# 92xxxx -> .BJ correctly all along. The two must not disagree on the shared code space.
@pytest.mark.parametrize("code", BEIJING_920 + SHANGHAI_900 + [
    "600000", "688981", "000001", "300750", "200011", "430047", "830799",
])
def test_agrees_with_house_reference_to_suffixed(code):
    assert to_ticker(code) == to_suffixed(code)


# --- engine/entity_resolver: the same root cause, as a quiet MISS ------------------ #
@pytest.mark.parametrize("code", BEIJING_920)
def test_entity_resolver_resolves_920xxx(code):
    """A 920xxx code in free text returned None — the Beijing space is 4/8/92, not 4/8.
    A miss here is silent: the name simply fails to resolve."""
    assert cn_code_to_ticker(code) == f"{code}.BJ"


@pytest.mark.parametrize("code,want", [
    ("600000", "600000.SS"), ("000001", "000001.SZ"), ("300750", "300750.SZ"),
    ("430047", "430047.BJ"), ("830799", "830799.BJ"),
])
def test_entity_resolver_known_space_unchanged(code, want):
    assert cn_code_to_ticker(code) == want


@pytest.mark.parametrize("bad", ["", "12345", "abcdef", "1234567"])
def test_entity_resolver_rejects_junk(bad):
    assert cn_code_to_ticker(bad) is None


# --- the stores themselves must stay clean ----------------------------------------- #
# The mapper fix stops NEW corruption; scripts/heal_cn_beijing_tickers.py re-keyed the
# 6,278 rows already written. This guard is what keeps both from silently regressing —
# it reads the tracked stores, so a reintroduced mapper bug fails here on the first
# nightly commit rather than after another month of accrual.
_HEALED_STORES = [
    "data/china_analyst/forecast.parquet",
    "data/china_block_trades/detail.parquet",
    "data/china_buyback/buyback.parquet",
    "data/china_lhb/detail.parquet",
    "data/china_lhb/events.parquet",
    "data/china_lhb/history.parquet",
    "data/china_preannounce/forecast.parquet",
    "data/china_unlocks/detail.parquet",
    "data/china_zt_pool/pool.parquet",
]

_REPO = Path(__file__).resolve().parent.parent


def test_no_store_carries_a_beijing_code_on_a_wrong_exchange():
    """No tracked china store may key a 92xxxx Beijing code as `.SS` or `.SZ`.

    FAIL-CLOSED: if not one of the stores is readable the test FAILS rather than skips —
    a guard that quietly finds nothing to check is a guard that has gone dark."""
    import pandas as pd

    checked, offenders = 0, {}
    for rel in _HEALED_STORES:
        p = _REPO / rel
        if not p.exists():
            continue
        try:
            tick = pd.read_parquet(p, columns=["ticker"])["ticker"].astype(str)
        except Exception:  # unreadable is not "clean" — leave it uncounted
            continue
        checked += 1
        bad = tick[tick.str.match(r"^92\d{4}\.(SS|SZ)$", na=False)]
        if len(bad):
            offenders[rel] = (len(bad), sorted(bad.unique())[:5])

    assert checked, (
        "fail-closed: none of the china stores were readable, so this guard proved "
        f"nothing. Expected at least one of: {_HEALED_STORES}"
    )
    assert not offenders, (
        "Beijing 92xxxx codes keyed to a Shanghai/Shenzhen suffix — the mapper "
        f"regressed or a store was written by an unfixed path: {offenders}"
    )
