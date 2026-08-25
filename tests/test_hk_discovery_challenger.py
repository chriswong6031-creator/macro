"""hk-discovery wave (WS:PROPHET-HK-CA-REVAMP) — engine/hk_discovery_challenger.py.

research/PROPHET_SHADOW_CONTRACT_V1.md §3/§4 is the binding storage/isolation
contract this challenger registers against; this file's kills are named
K-D1..K-D9 per the build commission that registered the FIRST real HK Lane-B
discovery challenger (``hk_discovery_v1``) into that substrate.

Every writer-exercising kill carries a POSITIVE CONTROL arm (the substrate
standing clause, mirrored from tests/test_board_shadow.py): asserts the
control path actually wrote/produced something, so a lane-gated no-op could
never pass every kill vacuously.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine import board_shadow as bs  # noqa: E402
from engine import hk_board_rank as hbr  # noqa: E402
from engine import hk_discovery_challenger as hkdc  # noqa: E402
from lib import config  # noqa: E402


# ---------------------------------------------------------------------------
# Shared session date
# ---------------------------------------------------------------------------
# Same wall-clock hazard as tests/test_board_shadow.py: the substrate stamps
# itself from the real clock and refuses any row whose ``session_date`` trails
# that stamp by more than ``bs.SETTLE_WINDOW_DAYS`` (K8b/F10).  A hard-coded
# session date therefore passes only until it ages out, then every registration
# these K-D kills exercise is refused and the whole ``board-shadow-substrate``
# job reds with no commit near this lane.  A literal ``2026-08-21`` did exactly
# that at 2026-08-25T00:00Z.  The ancient ``2020-01-01`` backfill-refusal arm is
# deliberately NOT derived, so the fence stays under test in both directions.
ASOF = (dt.date.today() - dt.timedelta(days=1)).isoformat()


# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _isolated_registry(tmp_path, monkeypatch):
    data_root = tmp_path / "data"
    monkeypatch.setattr(config, "data_dir", lambda: data_root)
    bs.CHALLENGER_REGISTRY.clear()
    monkeypatch.delenv("CN_LANE", raising=False)
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    yield data_root
    bs.CHALLENGER_REGISTRY.clear()


def _hk_on(monkeypatch) -> None:
    monkeypatch.setenv("CN_LANE", "asia")
    monkeypatch.delenv("COLLECT_LANE", raising=False)


def _ca_on(monkeypatch) -> None:
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    monkeypatch.delenv("CN_LANE", raising=False)


def _verdict(**kw) -> dict:
    base = {"eligible": False, "ticks": None, "above200": None,
            "weekly_bull": None, "last": {}, "fresh_bars": None}
    base.update(kw)
    return base


def _discovery_fn_ok(asof_arg: str) -> list[dict]:
    return [{
        "session_date": asof_arg, "security_ref_raw": "AAA",
        "candidate_origin": "washout_reclaim",
        "availability_status": hkdc.WAIT_CONFLUENCE,
        "availability_source": "hk_signal_gate",
    }]


# ---------------------------------------------------------------------------
# K-D1 — producer-cap kill
# ---------------------------------------------------------------------------
def test_k_d1_no_producer_cap_on_the_candidate_population():
    """Every firing name reaches build_candidates output — MORE names than
    every display cap constant (RAN_CAP/VETOED_CAP/RIPENING_CAP/LEADERS_CAP)
    combined, proving this module applies no producer cap of its own."""
    n = max(hbr.RAN_CAP, hbr.VETOED_CAP, hbr.RIPENING_CAP, hbr.LEADERS_CAP) + 25
    tickers = [f"T{i}.HK" for i in range(n)]
    evidence = {"washout_2w": {t: True for t in tickers}}
    rows = hkdc.build_candidates(evidence, ASOF)
    assert len(rows) == n, (
        f"expected all {n} firing names uncapped, got {len(rows)} — a cap "
        "was applied to the candidate population"
    )
    assert {r["security_ref_raw"] for r in rows} == set(tickers)


# ---------------------------------------------------------------------------
# K-D2 — origin-laundering kill
# ---------------------------------------------------------------------------
def test_k_d2_output_invariant_under_permuted_board_fields():
    """A bundle carrying board rank/featured/membership-shaped fields must
    not change the output when those fields are permuted — this module reads
    only its own named evidence keys."""
    evidence_a = {
        "washout_2w": {"AAA": True},
        "sig_verdict": {"AAA": _verdict(eligible=True)},
        "board_pos": {"AAA": 1},          # hostile extra — must be ignored
        "featured": {"AAA": True},        # hostile extra — must be ignored
        "membership": ["AAA"],            # hostile extra — must be ignored
    }
    evidence_b = {
        **evidence_a,
        "board_pos": {"AAA": 99},
        "featured": {"AAA": False},
        "membership": [],
    }
    rows_a = hkdc.build_candidates(evidence_a, ASOF)
    rows_b = hkdc.build_candidates(evidence_b, ASOF)
    assert rows_a == rows_b


def test_k_d2_source_fence_no_featured_board_pos_or_hk_standouts_tokens():
    source = (ROOT / "engine" / "hk_discovery_challenger.py").read_text()
    assert "featured" not in source
    assert "board_pos" not in source
    assert "hk_standouts" not in source


# ---------------------------------------------------------------------------
# K-D3 — missing != 0 kill
# ---------------------------------------------------------------------------
def test_k_d3_no_ah_twin_fires_nothing_no_fabricated_zero():
    """AAA has a resolvable A/H twin (present in ah_value); BBB is never
    mentioned anywhere (no twin) — BBB must not appear as a candidate at all,
    and must never fire ah_dislocation."""
    evidence = {"ah_value": {"AAA": {"cheap": True, "z": 1.2}}}
    rows = hkdc.build_candidates(evidence, ASOF)
    tickers = {r["security_ref_raw"] for r in rows}
    assert "AAA" in tickers
    assert "BBB" not in tickers
    aaa = next(r for r in rows if r["security_ref_raw"] == "AAA")
    assert "ah_dislocation" in aaa["candidate_origin"]


def test_k_d3_ah_present_but_not_cheap_never_fires():
    """A name WITH a twin whose read is not 'cheap' fires no ah_dislocation —
    the leg is a strict boolean read, never a fabricated near-miss."""
    evidence = {"ah_value": {"AAA": {"cheap": False, "z": -0.2}}}
    rows = hkdc.build_candidates(evidence, ASOF)
    assert rows == []


# ---------------------------------------------------------------------------
# K-D4 — unknown-availability kill
# ---------------------------------------------------------------------------
def test_k_d4_no_gate_verdict_is_never_entry_open():
    evidence = {"washout_2w": {"AAA": True}, "sig_verdict": {}}
    rows = hkdc.build_candidates(evidence, ASOF)
    aaa = next(r for r in rows if r["security_ref_raw"] == "AAA")
    assert aaa["availability_status"] == hkdc.UNAVAILABLE_DATA
    assert aaa["availability_status"] != hkdc.ENTRY_OPEN
    assert aaa["availability_source"] == "missing_inputs(gate_verdict)"


# All three whole-read availability flags EXPLICITLY True — the ONLY shape
# from which ENTRY_OPEN is reachable (Sol pre-settlement repair 2026-08-22:
# an omitted flag must never default to available).
_ALL_READS_AVAILABLE = {
    "plc_available": True,
    "knife_available": True,
    "extension_available": True,
}


def _entry_open_base_evidence():
    return {
        "washout_2w": {"AAA": True},
        "sig_verdict": {"AAA": _verdict(eligible=True)},
        **_ALL_READS_AVAILABLE,
    }


def _aaa_row(evidence):
    rows = hkdc.build_candidates(evidence, ASOF)
    return next(r for r in rows if r["security_ref_raw"] == "AAA")


def test_k_d4_all_reads_explicitly_available_is_entry_open():
    """POSITIVE CONTROL (Sol regression 4): with every required whole-read
    availability flag explicitly True, an eligible unblocked name reaches
    ENTRY_OPEN exactly as before."""
    aaa = _aaa_row(_entry_open_base_evidence())
    assert aaa["availability_status"] == hkdc.ENTRY_OPEN
    assert aaa["availability_source"] == "hk_signal_gate"


def test_k_d4_placement_gate_unavailable_demotes_would_be_entry_open():
    aaa = _aaa_row({**_entry_open_base_evidence(), "plc_available": False})
    assert aaa["availability_status"] == hkdc.UNAVAILABLE_DATA
    assert aaa["availability_source"] == "placement_gate_unavailable"


def test_k_d4_knife_read_unavailable_demotes_would_be_entry_open():
    """R4 (F4): when the falling-knife pass never stamped this render
    (knife_available=False), a name that would otherwise reach ENTRY_OPEN
    gets UNAVAILABLE_DATA/knife_read_unavailable instead — never a silent
    ENTRY_OPEN pass-through just because knife_risk happened to be empty."""
    aaa = _aaa_row({**_entry_open_base_evidence(), "knife_available": False})
    assert aaa["availability_status"] == hkdc.UNAVAILABLE_DATA
    assert aaa["availability_source"] == "knife_read_unavailable"


def test_k_d4_omitted_plc_available_is_never_entry_open():
    """Sol regression 1: an evidence bundle that OMITS plc_available must
    fail closed — unknown required availability never defaults to pass."""
    evidence = _entry_open_base_evidence()
    del evidence["plc_available"]
    aaa = _aaa_row(evidence)
    assert aaa["availability_status"] == hkdc.UNAVAILABLE_DATA
    assert aaa["availability_source"] == "placement_gate_unavailable(unstated)"


def test_k_d4_omitted_knife_available_is_never_entry_open():
    """Sol regression 2: omitting knife_available (the pre-repair
    default-true hole) must fail closed to UNAVAILABLE_DATA."""
    evidence = _entry_open_base_evidence()
    del evidence["knife_available"]
    aaa = _aaa_row(evidence)
    assert aaa["availability_status"] == hkdc.UNAVAILABLE_DATA
    assert aaa["availability_source"] == "knife_read_unavailable(unstated)"


def test_k_d4_omitted_extension_available_is_never_entry_open():
    """Sol regression 3: omitting extension_available must fail closed."""
    evidence = _entry_open_base_evidence()
    del evidence["extension_available"]
    aaa = _aaa_row(evidence)
    assert aaa["availability_status"] == hkdc.UNAVAILABLE_DATA
    assert aaa["availability_source"] == "extension_read_unavailable(unstated)"


def test_k_d4_explicit_none_availability_flag_is_never_entry_open():
    """Explicit None is as unknown as omitted — fail closed for each flag."""
    for key, source in (
        ("plc_available", "placement_gate_unavailable(unstated)"),
        ("knife_available", "knife_read_unavailable(unstated)"),
        ("extension_available", "extension_read_unavailable(unstated)"),
    ):
        aaa = _aaa_row({**_entry_open_base_evidence(), key: None})
        assert aaa["availability_status"] == hkdc.UNAVAILABLE_DATA, key
        assert aaa["availability_source"] == source


def test_k_d4_absent_flag_does_not_weaken_per_name_blockers():
    """Sol repair scope guard: a known conservative per-name blocker
    (RIGHTS_BLOCKED / WAIT_PULLBACK / RAN_DONT_CHASE) still wins even when a
    DIFFERENT read's availability flag is absent — an unknown read demotes
    only the would-be ENTRY_OPEN pass, never a known blocker."""
    evidence = _entry_open_base_evidence()
    del evidence["extension_available"]
    evidence["knife_risk"] = {"AAA": True}
    aaa = _aaa_row(evidence)
    assert aaa["availability_status"] == hkdc.WAIT_PULLBACK
    assert aaa["availability_source"] == "knife_read"


def test_k_d4_knife_read_true_still_wins_over_availability():
    """A knife_available=True map that also fires knife_risk for this ticker
    must still return WAIT_PULLBACK/knife_read — availability is a SEPARATE
    ladder rung below the actual knife/extension reads, never a substitute
    for them."""
    evidence = {
        "washout_2w": {"AAA": True},
        "sig_verdict": {"AAA": _verdict(eligible=True)},
        "knife_available": True,
        "knife_risk": {"AAA": True},
    }
    rows = hkdc.build_candidates(evidence, ASOF)
    aaa = next(r for r in rows if r["security_ref_raw"] == "AAA")
    assert aaa["availability_status"] == hkdc.WAIT_PULLBACK
    assert aaa["availability_source"] == "knife_read"


def test_k_d4_extension_read_unavailable_demotes_would_be_entry_open():
    """R4 (F4): the extension-map mirror of the knife-availability test above
    — extension_signals() returns an empty map by construction whenever
    `closes` is absent, and per-name absence within that empty map must not
    be read as 'not extended' when the whole read never ran."""
    aaa = _aaa_row({**_entry_open_base_evidence(), "extension_available": False})
    assert aaa["availability_status"] == hkdc.UNAVAILABLE_DATA
    assert aaa["availability_source"] == "extension_read_unavailable"


def test_k_d4_extension_read_true_still_wins_over_availability():
    """extension_available=True with the name's own extended read True must
    still return RAN_DONT_CHASE/extension_read."""
    evidence = {
        "washout_2w": {"AAA": True},
        "sig_verdict": {"AAA": _verdict(eligible=True)},
        "extension_available": True,
        "extended": {"AAA": True},
    }
    rows = hkdc.build_candidates(evidence, ASOF)
    aaa = next(r for r in rows if r["security_ref_raw"] == "AAA")
    assert aaa["availability_status"] == hkdc.RAN_DONT_CHASE
    assert aaa["availability_source"] == "extension_read"


# ---------------------------------------------------------------------------
# R2 (F2) — blocked_signal shares build_vetoed_rows's staleness bound
# ---------------------------------------------------------------------------
def test_r2_ancient_veto_does_not_fire_blocked_signal():
    """An 80-session-old veto (past VETOED_MAX_SESSIONS=63) must not fire
    blocked_signal — the same bound build_vetoed_rows applies to the display
    lane."""
    evidence = {
        "sig_verdict": {"AAA": _verdict(
            eligible=False, weekly_bull=True, fresh_bars=80,
            last={"type": "buy", "quality": "block", "reason": "counter_trend"},
        )},
        "dir_by_ticker": {"AAA": "up"},
    }
    rows = hkdc.build_candidates(evidence, ASOF)
    origins = next((r["candidate_origin"] for r in rows if r["security_ref_raw"] == "AAA"), "")
    assert "blocked_signal" not in origins


def test_r2_fresh_veto_fires_blocked_signal():
    """POSITIVE CONTROL: a fresh (10-session) veto still fires, carrying the
    slugged reason sub-token."""
    evidence = {
        "sig_verdict": {"AAA": _verdict(
            eligible=False, weekly_bull=True, fresh_bars=10,
            last={"type": "buy", "quality": "block", "reason": "counter_trend"},
        )},
        "dir_by_ticker": {"AAA": "up"},
    }
    rows = hkdc.build_candidates(evidence, ASOF)
    aaa = next(r for r in rows if r["security_ref_raw"] == "AAA")
    assert "blocked_signal(counter_trend)" in aaa["candidate_origin"]


def test_r2_unknown_age_veto_still_fires_blocked_signal():
    """Unknown age (no marker date at all, and fresh_bars absent) must still
    fire — only a KNOWN-stale veto is excluded, matching
    build_vetoed_rows's own conditional (`sessions is not None and sessions >
    bound`)."""
    evidence = {
        "sig_verdict": {"AAA": _verdict(
            eligible=False, weekly_bull=True, fresh_bars=None,
            last={"type": "buy", "quality": "block", "reason": "counter_trend"},
        )},
        "dir_by_ticker": {"AAA": "up"},
    }
    rows = hkdc.build_candidates(evidence, ASOF)
    aaa = next(r for r in rows if r["security_ref_raw"] == "AAA")
    assert "blocked_signal(counter_trend)" in aaa["candidate_origin"]


# ---------------------------------------------------------------------------
# K-D5 — historical-backfill kill (via the REAL substrate refusal)
# ---------------------------------------------------------------------------
def test_k_d5_historical_backfill_refused_by_the_substrate(monkeypatch):
    _hk_on(monkeypatch)

    def _backdated(_asof_arg: str) -> list[dict]:
        return [{
            "session_date": "2020-01-01", "security_ref_raw": "AAA",
            "candidate_origin": "washout_reclaim",
            "availability_status": hkdc.WAIT_CONFLUENCE,
            "availability_source": "hk_signal_gate",
        }]

    bs.register_challenger("HK", hkdc.DEFINITION, discovery_fn=_backdated)
    result = bs.write_shadow([], market="HK", asof=ASOF)
    assert result["registry_state"] == "wrote_n_rows n=0"
    assert not bs._lane_b_path("HK").exists()

    # POSITIVE CONTROL: a same-session row lands.
    bs.CHALLENGER_REGISTRY.clear()
    bs.register_challenger("HK", hkdc.DEFINITION, discovery_fn=_discovery_fn_ok)
    result2 = bs.write_shadow([], market="HK", asof=ASOF)
    assert result2["written"] == 1
    assert bs._lane_b_path("HK").exists()


# ---------------------------------------------------------------------------
# K-D6 — market re-derivation fence
# ---------------------------------------------------------------------------
def test_k_d6_module_has_no_market_parameter_env_read_or_ca_token():
    source = (ROOT / "engine" / "hk_discovery_challenger.py").read_text()
    assert "os.environ" not in source
    assert "getenv(" not in source
    assert not re.search(r'''["']CA["']''', source), "quoted market-code literal 'CA' found"
    assert not re.search(r"canada", source, re.IGNORECASE)
    for match in re.finditer(r"def\s+\w+\(([^)]*)\)", source, re.DOTALL):
        params = [
            p.strip().split(":")[0].split("=")[0].strip().lstrip("*")
            for p in match.group(1).split(",") if p.strip()
        ]
        assert "market" not in params, f"a def carries a 'market' parameter: {match.group(0)}"


def test_k_d6_output_identical_under_a_mutated_ambient_market_env_var(monkeypatch):
    evidence = {
        "washout_2w": {"AAA": True},
        "sig_verdict": {"AAA": _verdict(eligible=True)},
    }
    before = hkdc.build_candidates(evidence, ASOF)
    monkeypatch.setenv("CN_LANE", "asia")
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    monkeypatch.setenv("MACRO_MARKET", "CA")
    after = hkdc.build_candidates(evidence, ASOF)
    assert before == after


# ---------------------------------------------------------------------------
# K-D7 — foreign-market isolation with the REAL registration
# ---------------------------------------------------------------------------
def test_k_d7_foreign_market_isolation_with_the_real_registration(monkeypatch):
    calls_seen: list[str] = []

    def _discovery_fn(asof_arg: str) -> list[dict]:
        calls_seen.append(asof_arg)
        return _discovery_fn_ok(asof_arg)

    bs.register_challenger("HK", hkdc.DEFINITION, discovery_fn=_discovery_fn)

    _ca_on(monkeypatch)
    result_ca = bs.write_shadow([], market="CA", asof=ASOF)
    assert result_ca["registry_state"] == "no_challenger_for_market"
    assert calls_seen == [], "the HK-only discovery_fn must never be invoked during a CA pass"
    assert not bs._lane_b_path("CA").exists()
    assert not (config.data_dir() / "prophet_shadow" / "ca_discovery_receipt.json").exists()

    # POSITIVE CONTROL: the same registration fires and writes under HK.
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    _hk_on(monkeypatch)
    result_hk = bs.write_shadow([], market="HK", asof=ASOF)
    assert result_hk["written"] == 1
    assert calls_seen == [ASOF]
    assert (config.data_dir() / "prophet_shadow" / "hk_discovery_receipt.json").exists()


# ---------------------------------------------------------------------------
# K-D8 (referenced here too, canonical home is tests/test_check_surface_
# freshness.py): a sanity import check that the two modules' constants agree.
# ---------------------------------------------------------------------------
def test_definition_constant_matches_the_registration_site():
    source = (ROOT / "scripts" / "build_hk_library.py").read_text()
    assert "hk_discovery_challenger.DEFINITION" in source
    assert hkdc.DEFINITION == "hk_discovery_v1"


# ---------------------------------------------------------------------------
# K-D9 — publication-isolation kill
# ---------------------------------------------------------------------------
def test_k_d9_registration_runs_after_the_hk_standouts_persist():
    """Structural guarantee: the registration block must sit AFTER the
    hk_standouts.json persist in scripts/build_hk_library.py's source, so the
    evidence-bundle assembly can never race or read the payload before it is
    fully serialized. MUTATION THIS KILLS: hoisting the registration block
    above the persist call.

    R3 (build commission) strengthens this pin: the evidence-ASSEMBLY BLOCK
    itself must start strictly between the persist and the registration
    call — a token at the very TOP of the assembly block (before the mutation
    this test's ORIGINAL two-point pin could not see: hoisting only the
    assembly block, leaving register_challenger's own call site untouched,
    would have passed the old i_persist < i_registration check vacuously)."""
    source = (ROOT / "scripts" / "build_hk_library.py").read_text()
    i_persist = source.index('(fdir / "hk_standouts.json").write_text(')
    i_evidence_assembly_start = source.index("HK-DISCOVERY EVIDENCE ASSEMBLY START")
    i_registration = source.index(
        'hk_discovery_challenger.DEFINITION, discovery_fn=_hk_discovery_fn'
    )
    i_shadow = source.index('board_shadow.write_shadow(calls, market="HK"')
    assert i_persist < i_evidence_assembly_start < i_registration < i_shadow


def test_k_d9_evidence_assembly_block_deep_copies_before_binding():
    """R3 (F3+F7): the assembled evidence bundle must be deep-copied ONCE
    before it is bound into the registration closure — nothing later in
    scripts/build_hk_library.py (today or after a future edit) may then
    mutate a live object the closure still holds a reference to.
    MUTATION THIS KILLS: deleting the deepcopy call."""
    source = (ROOT / "scripts" / "build_hk_library.py").read_text()
    i_evidence_assembly_start = source.index("HK-DISCOVERY EVIDENCE ASSEMBLY START")
    i_registration = source.index(
        'hk_discovery_challenger.DEFINITION, discovery_fn=_hk_discovery_fn'
    )
    block = source[i_evidence_assembly_start:i_registration]
    assert "deepcopy" in block


def test_k_d1_evidence_ripening_call_is_uncapped():
    """R7 (F9): the ripening evidence leg inside build_hk_library's evidence
    block must call build_ripening_rows with cap=10**9 and ready_cap=10**9 —
    the DISPLAY call elsewhere in the same file legitimately uses the real
    RIPENING_CAP/RIPENING_READY_CAP; only the discovery-evidence call must be
    uncapped (K-D1's producer-cap law, contract §4).
    MUTATION THIS KILLS: deleting either kwarg from the discovery-evidence
    call."""
    source = (ROOT / "scripts" / "build_hk_library.py").read_text()
    marker = "_hk_disc_ripening_rows = hk_board_rank.build_ripening_rows("
    i = source.index(marker)
    call_src = source[i:i + 400]
    assert "cap=10**9" in call_src
    assert "ready_cap=10**9" in call_src


def test_k_d1_evidence_assembly_never_passes_a_raw_set_for_ripening_tickers():
    """R5 (F5): the evidence-assembly source must hand build_candidates a
    SORTED list for ripening_tickers, never the raw
    `_hk_disc_ripening_tickers` set — set iteration order is not stable
    across process runs. MUTATION THIS KILLS: reverting
    '"ripening_tickers": sorted(_hk_disc_ripening_tickers)' back to the bare
    set variable."""
    source = (ROOT / "scripts" / "build_hk_library.py").read_text()
    assert '"ripening_tickers": sorted(_hk_disc_ripening_tickers)' in source


# ---------------------------------------------------------------------------
# R5 (F5) — deterministic candidate emission
# ---------------------------------------------------------------------------
def test_r5_build_candidates_rejects_a_raw_set_for_ripening_tickers():
    """build_candidates()/_candidate_universe() must fail loudly, not
    silently accept, a raw set for ripening_tickers — the defensive half of
    R5's fix, independent of the build_hk_library source pin above."""
    evidence = {"ripening_tickers": {"AAA", "BBB"}}
    with pytest.raises(AssertionError):
        hkdc.build_candidates(evidence, ASOF)


def test_r5_candidate_row_order_is_deterministic_across_repeated_calls():
    """Two calls in one process, given a SORTED ripening_tickers list, must
    produce identical row order — the positive control for the fix (a raw
    set could still happen to look ordered within one process; this pins the
    list-based contract that survives across processes too)."""
    evidence = {
        "washout_2w": {f"T{i}.HK": True for i in range(30)},
        "ripening_tickers": sorted(f"R{i}.HK" for i in range(30)),
    }
    rows_a = hkdc.build_candidates(evidence, ASOF)
    rows_b = hkdc.build_candidates(evidence, ASOF)
    order_a = [r["security_ref_raw"] for r in rows_a]
    order_b = [r["security_ref_raw"] for r in rows_b]
    assert order_a == order_b
    assert len(order_a) == 60


def test_k_d9_publication_isolation_with_the_real_challenger(monkeypatch):
    """Registering the REAL hk_discovery_v1 challenger and running a full
    write_shadow pass must never touch a hk_standouts-shaped payload dict
    that is already live in scope — the exact shape scripts/
    build_hk_library.py's registration block sits inside, downstream of the
    hk_standouts.json persist (fixture-level deep-equality, contract §4/K1
    idiom)."""
    _hk_on(monkeypatch)
    out = {
        "buy": [{"ticker": "AAA", "edge_z": 1.1}],
        "watch": [{"ticker": "BBB", "edge_z": -0.2}],
        "board_definition": "hk_prophet_v2",
    }
    before = json.dumps(out, sort_keys=True, default=str)

    evidence = {
        "sig_verdict": {"AAA": _verdict(eligible=True)},
        "washout_2w": {"AAA": True},
    }

    def _discovery_fn(asof_arg: str) -> list[dict]:
        return hkdc.build_candidates(evidence, asof_arg)

    bs.register_challenger("HK", hkdc.DEFINITION, discovery_fn=_discovery_fn)
    calls = [{"ticker": "AAA", "group": "entry_open", "board_definition": "hk_prophet_v2"},
             {"ticker": "BBB", "group": "watch", "board_definition": "hk_prophet_v2"}]
    result = bs.write_shadow(calls, market="HK", asof=ASOF)
    assert result["written"] >= 1  # POSITIVE CONTROL — the substrate actually ran

    after = json.dumps(out, sort_keys=True, default=str)
    assert before == after, "the hk_standouts-shaped payload must be byte-identical"


# ---------------------------------------------------------------------------
# Regression: the shared session date must never age out of the settle window
# ---------------------------------------------------------------------------
def test_shared_session_date_can_never_age_out_of_the_settle_window():
    """Companion to the same guard in tests/test_board_shadow.py.

    Both steps of the ``board-shadow-substrate`` job share one substrate and one
    wall-clock fence, so a literal that ages out here reds the job just as surely
    as one in the K1-K20 suite -- and healing only one file leaves the job red.
    """
    today = dt.date.today().isoformat()
    age = (dt.date.today() - dt.date.fromisoformat(ASOF)).days
    assert 0 <= age <= bs.SETTLE_WINDOW_DAYS
    assert not bs._settle_violation(ASOF, today)
    assert bs._settle_violation("2020-01-01", today)


def test_no_bare_session_date_literal_reintroduces_the_time_bomb():
    """Guard the repair: only the ancient backfill arm may be a bare literal."""
    source = (ROOT / "tests/test_hk_discovery_challenger.py").read_text()
    code = "\n".join(
        line.split("#", 1)[0] for line in source.splitlines()
        if not line.lstrip().startswith("#")
    )
    literals = set(re.findall(r'"(20\d{2}-\d{2}-\d{2})"', code))
    assert literals <= {"2020-01-01"}, (
        f"bare session-date literal(s) {sorted(literals - {'2020-01-01'})} will age out of "
        "SETTLE_WINDOW_DAYS and red board-shadow-substrate on a date rollover -- use ASOF"
    )
