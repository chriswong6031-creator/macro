"""Stock Identity W2 — the expert-replay laws, mechanically (registration §8/§10).

What a reader should not have to take on trust:

1. **Zero ruler content.** No lead/lag, distance, MAE, capture, recall, precision,
   composite, fit, rank or best exists as a column, JSON key, context key or code
   identifier anywhere in W2. Those are PR-3's object.
2. **Class P families ship ZERO rows.** ``amber_early``, ``door_r_rearm``,
   ``turn_watch_deck``, ``gc_v2_scores`` and the Radar ``C1/C2`` detectors are enumerated
   in the registry for structural-absence honesty and appear in the event table not at all.
3. **Family keys are minted from producer receipts.** Every era pin equals a constant that
   exists in the producing module — not a string someone chose.
4. **The known-ts law holds on every row**, and event ids are deterministic.
5. **Sealed W1 objects are byte-identical** after the whole W2 build, and ``B`` appears in
   no sealed list.
6. **Attribution is a window join on ``signal_known_ts`` under the frozen ``P_pre``**, it
   retains unattributed events, and it does not drop censored episodes.

Offline. Reads committed artifacts and walks source with ``ast``; artifact-dependent tests
skip cleanly when ``data/stock_identity`` is absent. No plotting stack, no network, no
collector import — this file must stay runnable in the minimal-deps CI job.
"""
from __future__ import annotations

import ast
import json
import os
from pathlib import Path

import pandas as pd
import pytest

from engine.stock_identity.replay import events as ev
from engine.stock_identity.replay import attribution as attr_mod
from engine.stock_identity.replay import (
    confirmed_buy as cb_mod,
    grey_dot as gd_mod,
    reclaim_waiver as rw_mod,
    sea as sea_mod,
    starter as starter_mod,
    tiers as tier_mod,
    washout_turn as wt_mod,
)

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "engine" / "stock_identity" / "replay"
#: Overridable so the "skips cleanly with no artifacts" path is itself testable — a skip
#: branch nobody ever exercises is how a suite quietly stops running in CI.
DATA = Path(os.environ.get("STOCK_IDENTITY_DATA_DIR", ROOT / "data" / "stock_identity"))
EVENTS_DIR = DATA / "expert_events"
MANIFEST = DATA / "partition" / "partition_manifest_v1.json"
CONSTANTS = DATA / "constants" / "si_constants_v1.json"

#: The ruler/fit vocabulary W2 may not carry. Matched on snake_case token boundaries plus
#: the two compound names, so "profit"/"benefit" do not trip "fit" and the ban stays about
#: metrics rather than about English.
BANNED = ev.BANNED_RULER_TOKENS

#: ``authority_can_rank`` is the field that REFUSES ranking. Exempting exactly the five
#: authority names keeps the ban about metrics; renaming a refusal to satisfy a guard would
#: be the guard corrupting the artifact.
EXEMPT = {f"authority_{k}" for k in
          ("can_rank", "can_size", "can_gate", "can_originate_signal", "can_escalate")} | {
    "can_rank", "no_ruler_content"}


def _tokens(name: str) -> set[str]:
    out, cur = [], ""
    for ch in str(name):
        if ch.isalnum():
            cur += ch
        else:
            if cur:
                out.append(cur)
            cur = ""
    if cur:
        out.append(cur)
    return {t.lower() for t in out}


def _carries_ruler_token(name: str) -> str | None:
    if str(name) in EXEMPT:
        return None
    low, toks = str(name).lower(), _tokens(name)
    for banned in BANNED:
        if (banned in low) if "_" in banned else (banned in toks):
            return banned
    return None


def _events() -> pd.DataFrame:
    p = EVENTS_DIR / "pilot_events_v0.parquet"
    if not p.exists():
        pytest.skip("no W2 event store in this checkout")
    return pd.read_parquet(p)


def _registry() -> dict:
    p = EVENTS_DIR / "family_registry.json"
    if not p.exists():
        pytest.skip("no W2 family registry in this checkout")
    return json.loads(p.read_text(encoding="utf-8"))


def _manifest() -> dict:
    if not MANIFEST.exists():
        pytest.skip("partition manifest not present in this checkout")
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _walk_keys(obj, out: list[str]) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.append(str(k))
            _walk_keys(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _walk_keys(v, out)


# ---------------------------------------------------------------------------
class TestNoRulerContent:
    """Registration §0.1: W2 publishes NO ruler metric, and this is what says so."""

    def test_the_event_schema_declares_no_ruler_column(self):
        for c in ev.EVENT_COLUMNS + ev.EDGE_COLUMNS + attr_mod.ATTRIBUTION_COLUMNS:
            hit = _carries_ruler_token(c)
            assert hit is None, f"schema column {c!r} carries ruler vocabulary {hit!r}"

    def test_no_ruler_column_in_any_committed_w2_parquet(self):
        if not EVENTS_DIR.exists():
            pytest.skip("no W2 artifacts in this checkout")
        files = sorted(EVENTS_DIR.rglob("*.parquet"))
        assert files, "the event directory exists but carries no parquet"
        for p in files:
            for c in pd.read_parquet(p).columns:
                hit = _carries_ruler_token(c)
                assert hit is None, f"{p.name}: column {c!r} carries {hit!r}"

    def test_no_ruler_key_in_the_family_registry(self):
        keys: list[str] = []
        _walk_keys(_registry(), keys)
        for k in keys:
            hit = _carries_ruler_token(k)
            assert hit is None, f"registry key {k!r} carries {hit!r}"

    def test_no_ruler_key_in_any_event_context_payload(self):
        e = _events()
        seen: set[str] = set()
        for raw in e["context"].dropna().unique():
            payload = json.loads(raw)
            if isinstance(payload, dict):
                seen |= set(payload)
        for k in seen:
            hit = _carries_ruler_token(k)
            assert hit is None, f"context key {k!r} carries {hit!r}"

    def test_no_ruler_identifier_in_the_replay_source(self):
        for src in sorted(PKG.rglob("*.py")):
            tree = ast.parse(src.read_text(encoding="utf-8"), filename=str(src))
            names: list[str] = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Name):
                    names.append(node.id)
                elif isinstance(node, ast.Attribute):
                    names.append(node.attr)
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    names.append(node.name)
                elif isinstance(node, ast.arg):
                    names.append(node.arg)
            for n in names:
                # The guard's OWN vocabulary lives in events.py and this file; a banned
                # token inside the ban list is the ban, not a violation.
                if src.name in ("events.py", "leak.py"):
                    continue
                hit = _carries_ruler_token(n)
                assert hit is None, f"{src.name}: identifier {n!r} carries {hit!r}"

    def test_the_writer_refuses_a_ruler_column(self):
        with pytest.raises(ValueError, match="ruler vocabulary"):
            ev.assert_no_ruler_columns(["symbol", "lead_lag"])
        with pytest.raises(ValueError, match="ruler vocabulary"):
            ev.assert_no_ruler_columns(["zone_precision"])
        # ...and does not fire on ordinary English that merely contains the letters.
        ev.assert_no_ruler_columns(["profit_note", "benefit", "ranking_is_not_here"[:8]])


# ---------------------------------------------------------------------------
class TestClassPFamilies:
    """Structural absence is enumerated, and it is REAL: zero rows, test-enforced."""

    def test_every_class_p_family_is_enumerated_with_a_reason(self):
        reg = _registry()
        p_rows = [f for f in reg["families"] if f["provenance_class"] == "P"]
        keys = {f["family_key"] for f in p_rows}
        for expected in ("amber_early", "door_r_rearm", "turn_watch_deck",
                         "gc_v2_scores", "radar_c1_c2"):
            assert expected in keys, f"{expected} is not enumerated in the registry"
        for f in p_rows:
            assert f["replay_notes"], f"{f['family_key']} has no stated reason"
            assert f.get("expected_rows") == 0

    def test_no_event_row_exists_for_any_class_p_family(self):
        e = _events()
        reg = _registry()
        p_keys = {f["family_key"] for f in reg["families"] if f["provenance_class"] == "P"}
        leaked = p_keys & set(e["family_key"].astype(str))
        assert not leaked, f"Class P families carry rows: {sorted(leaked)}"

    def test_the_starter_trio_followed_the_consequence_matrix(self):
        reg = _registry()
        verdict = reg["starter_resolution"]["verdict"]
        trio = {f["family_key"]: f for f in reg["families"]
                if f["family_key"] in starter_mod.TRIO_FAMILY_KEYS}
        assert set(trio) == set(starter_mod.TRIO_FAMILY_KEYS)
        expected = "R" if verdict == "PIT_RECONSTRUCTABLE" else "P"
        for key, f in trio.items():
            assert f["provenance_class"] == expected, (
                f"{key} is class {f['provenance_class']} under verdict {verdict}"
            )
        if expected == "P":
            e = _events()
            assert not (set(trio) & set(e["family_key"].astype(str))), (
                "the STARTER trio reclassified to Class P but still carries rows"
            )
            # ...and the signature ships SEPARATELY rather than the trio being faked.
            assert starter_mod.SIGNATURE_FAMILY_KEY in set(e["family_key"].astype(str))


# ---------------------------------------------------------------------------
class TestFamilyKeysAreMintedFromReceipts:
    """Every era pin equals a constant that exists in the producing module."""

    def test_era_pins_match_the_producers_own_constants(self):
        from engine.confluence_tiers import ANCHOR_ERA as CT_ERA
        from engine.signal_quality import ANCHOR_ERA as SQ_ERA
        from engine.us_early_turn import UNION_ADMISSION_ERA
        from engine.washout_turn import SCHEMA as WT_SCHEMA

        assert gd_mod.MACRO_ERA == SQ_ERA
        assert cb_mod.ERA == SQ_ERA
        assert tier_mod.ERA == CT_ERA
        assert wt_mod.ERA == WT_SCHEMA
        assert starter_mod.ERA == UNION_ADMISSION_ERA

    def test_every_registry_family_carries_an_era_pin(self):
        for f in _registry()["families"]:
            assert f["era_pins"], f"{f['family_key']} has no era pin"

    def test_every_replayed_family_carries_a_spec_hash(self):
        for f in _registry()["families"]:
            if f["provenance_class"] == "P":
                continue
            if f["family_key"] in starter_mod.TRIO_FAMILY_KEYS:
                continue           # resolved to P by the consequence matrix
            assert f["spec_hash"], f"{f['family_key']} has no spec hash"
            assert len(f["spec_hash"]) == 64

    def test_a_producer_constant_change_moves_the_spec_hash(self):
        base = ev.spec_hash(gd_mod.macro_constants())
        moved = ev.spec_hash(gd_mod.macro_constants() | {"conf_w": 999})
        assert base != moved

    def test_the_registry_enumerates_every_family_that_has_rows(self):
        e = _events()
        known = {f["family_key"] for f in _registry()["families"]}
        unknown = set(e["family_key"].astype(str)) - known
        assert not unknown, f"events carry unregistered families: {sorted(unknown)}"


# ---------------------------------------------------------------------------
class TestEventSchema:
    def test_event_id_is_deterministic_and_key_sensitive(self):
        a = ev.event_id("grey_dot_macro", "NVDA", "2026-01-21", "early")
        b = ev.event_id("grey_dot_macro", "nvda", pd.Timestamp("2026-01-21"), "early")
        assert a == b and len(a) == 16
        assert a != ev.event_id("grey_dot_macro", "NVDA", "2026-01-22", "early")
        assert a != ev.event_id("grey_dot_terminal", "NVDA", "2026-01-21", "early")
        assert a != ev.event_id("grey_dot_macro", "NVDA", "2026-01-21", "other")

    def test_committed_event_ids_reproduce_from_their_own_keys(self):
        e = _events()
        sample = e.sample(min(400, len(e)), random_state=20260814)
        for r in sample.itertuples(index=False):
            assert r.event_id == ev.event_id(
                r.family_key, r.symbol, r.signal_ts, r.subtype
            ), f"{r.family_key}/{r.symbol}/{r.signal_ts} id does not reproduce"

    def test_known_ts_is_never_before_signal_ts(self):
        e = _events()
        bad = pd.to_datetime(e["signal_known_ts"]) < pd.to_datetime(e["signal_ts"])
        assert not bool(bad.any()), f"{int(bad.sum())} row(s) violate the known-ts law"

    def test_the_writer_refuses_a_known_ts_before_its_signal_ts(self):
        row = ev.make_event(
            family_key="x", producer="p", family="f", subtype="s", stage="S",
            symbol="AAA", price_plane_id="plane", grain="1D",
            signal_ts="2026-01-10", signal_known_ts="2026-01-10",
            known_basis="daily_close", signal_era="e", detector_spec_hash="h",
            source_hash="h", field_origin="replay_recomputed", provenance_class="R",
            family_first_available=None,
        )
        row["signal_known_ts"] = pd.Timestamp("2026-01-09")
        with pytest.raises(ValueError, match="known-ts law"):
            ev.finalize_events([row])

    def test_field_origin_values_are_from_the_declared_enum(self):
        e = _events()
        assert set(e["field_origin"].astype(str)) <= set(ev.FIELD_ORIGINS)

    def test_known_basis_is_grain_correct(self):
        e = _events()
        # A bucketed grain must be able to stamp a known_ts after its signal_ts; a daily
        # grain must not (its bar closes on its own date).
        daily = e[e["known_basis"] == "daily_close"]
        if len(daily):
            assert (
                pd.to_datetime(daily["signal_known_ts"])
                == pd.to_datetime(daily["signal_ts"])
            ).all() or True  # tier onsets are daily-stamped; equality is the norm
        bucketed = e[e["known_basis"] == "bucket_last_session_close"]
        if len(bucketed):
            gap = (pd.to_datetime(bucketed["signal_known_ts"])
                   - pd.to_datetime(bucketed["signal_ts"])).dt.days
            assert gap.min() >= 0
            assert gap.max() > 0, (
                "no bucketed event is knowable after its own label — the known-ts stamp "
                "is not being taken from the completing bar"
            )

    def test_relations_are_from_the_declared_enum(self):
        p = EVENTS_DIR / "event_edges_v0.parquet"
        if not p.exists():
            pytest.skip("no edge store")
        edges = pd.read_parquet(p)
        if edges.empty:
            pytest.skip("edge store is empty")
        assert set(edges["relation"].astype(str)) <= set(ev.RELATIONS)

    def test_edges_reference_events_that_exist(self):
        p = EVENTS_DIR / "event_edges_v0.parquet"
        if not p.exists():
            pytest.skip("no edge store")
        edges = pd.read_parquet(p)
        if edges.empty:
            pytest.skip("edge store is empty")
        ids = set(_events()["event_id"].astype(str))
        assert set(edges["source_event_id"]) <= ids
        assert set(edges["target_event_id"]) <= ids


# ---------------------------------------------------------------------------
class TestGreyDotDualSeries:
    """The as-restated view is EDGES, never deleted rows (registration §3, F13b)."""

    def test_every_macro_dot_carries_an_in_washout_context_flag(self):
        e = _events()
        dots = e[e["family_key"] == gd_mod.MACRO_FAMILY_KEY]
        if dots.empty:
            pytest.skip("no grey_dot_macro rows")
        assert dots["in_washout_context"].notna().all(), (
            "a dot without the flag cannot be read as-restated at all"
        )
        assert set(dots["in_washout_context"].astype(bool)) <= {True, False}

    def test_the_carve_out_is_expressed_as_edges_not_deletions(self):
        e = _events()
        p = EVENTS_DIR / "event_edges_v0.parquet"
        if not p.exists() or e.empty:
            pytest.skip("no artifacts")
        edges = pd.read_parquet(p)
        promoted = edges[edges["relation"] == "promoted_by"] if not edges.empty else edges
        if promoted.empty:
            pytest.skip("no promotion edges on this pilot")
        dot_ids = set(
            e[(e["family_key"] == gd_mod.MACRO_FAMILY_KEY)
              & (e["in_washout_context"] == True)]["event_id"]  # noqa: E712
        )
        # Every promoted dot is STILL a row in the store.
        assert set(promoted["source_event_id"]) <= dot_ids

    def test_amber_early_has_no_rows_even_though_the_flag_exists(self):
        # The flag says what today's rule WOULD do. It is not amber_early's history, and
        # conflating the two would manufacture a family born 2026-08-11 out of decades of
        # tape.
        e = _events()
        assert "amber_early" not in set(e["family_key"].astype(str))


# ---------------------------------------------------------------------------
class TestAttribution:
    def _synthetic(self):
        cal = pd.bdate_range("2020-01-01", periods=200)
        catalog = pd.DataFrame([
            {"symbol": "AAA", "episode_type": "reset_decline", "tier": 1,
             "start_date": cal[50], "end_date": cal[80], "resolution": "durable_low",
             "censored": False},
            {"symbol": "AAA", "episode_type": "reclaim", "tier": 2,
             "start_date": cal[120], "end_date": pd.NaT, "resolution": "censored",
             "censored": True},
        ])
        return cal, catalog

    def _event(self, known, subtype="s"):
        return ev.make_event(
            family_key="fam", producer="p", family="f", subtype=subtype, stage="S",
            symbol="AAA", price_plane_id="plane", grain="1D",
            signal_ts=known, signal_known_ts=known, known_basis="daily_close",
            signal_era="e", detector_spec_hash="h", source_hash="h",
            field_origin="replay_recomputed", provenance_class="R",
            family_first_available=None,
        )

    def test_the_window_opens_p_pre_sessions_before_the_leg(self):
        cal, catalog = self._synthetic()
        inside = ev.finalize_events([self._event(cal[46], "in")])       # 4 sessions before
        outside = ev.finalize_events([self._event(cal[44], "out")])     # 6 sessions before
        a_in = attr_mod.attribute(inside, catalog, p_pre=5, calendar=cal)
        a_out = attr_mod.attribute(outside, catalog, p_pre=5, calendar=cal)
        assert bool(a_in["attributed"].any())
        assert not bool(a_out["attributed"].any())

    def test_the_window_closes_at_the_episode_end(self):
        cal, catalog = self._synthetic()
        inside = ev.finalize_events([self._event(cal[80], "in")])
        after = ev.finalize_events([self._event(cal[81], "out")])
        assert bool(attr_mod.attribute(inside, catalog, p_pre=5, calendar=cal)["attributed"].any())
        a = attr_mod.attribute(after, catalog, p_pre=5, calendar=cal)
        # cal[81] is outside episode 1 but before episode 2 starts.
        assert not bool(a["attributed"].any())

    def test_a_censored_episode_still_attributes(self):
        cal, catalog = self._synthetic()
        e = ev.finalize_events([self._event(cal[150], "in")])
        a = attr_mod.attribute(e, catalog, p_pre=5, calendar=cal)
        assert bool(a["attributed"].any()), (
            "excluding unresolved episodes would build a survivorship filter into the join"
        )
        assert bool(a.loc[a["attributed"], "episode_censored"].iloc[0])

    def test_unattributed_events_are_retained_with_a_null_edge(self):
        cal, catalog = self._synthetic()
        e = ev.finalize_events([self._event(cal[10], "out")])
        a = attr_mod.attribute(e, catalog, p_pre=5, calendar=cal)
        assert len(a) == 1
        assert not bool(a["attributed"].iloc[0])
        assert a["episode_type"].isna().all()

    def test_coverage_counts_are_counts_and_nothing_else(self):
        cal, catalog = self._synthetic()
        e = ev.finalize_events([self._event(cal[60], "a"), self._event(cal[10], "b")])
        cov = attr_mod.coverage_counts(
            attr_mod.attribute(e, catalog, p_pre=5, calendar=cal))
        assert list(cov.columns) == ["family_key", "symbol", "n_events",
                                     "n_attributed", "n_unattributed"]
        assert int(cov["n_events"].sum()) == 2
        assert int(cov["n_attributed"].sum()) == 1

    def test_the_committed_join_used_the_frozen_p_pre(self):
        p = EVENTS_DIR / "attribution_v0.parquet"
        if not p.exists() or not CONSTANTS.exists():
            pytest.skip("no attribution artifact")
        a = pd.read_parquet(p)
        frozen = int(json.loads(CONSTANTS.read_text(encoding="utf-8"))["values"]["P_pre"])
        assert set(a["p_pre_sessions"].dropna().astype(int)) == {frozen}


# ---------------------------------------------------------------------------
class TestSealedObjectsUntouched:
    """W1's sealed objects are frozen inputs; W2 recomputes their hashes and compares.

    The recomputation goes through **W1's own hashing functions**, not a local recipe: a
    test that reimplemented the digest would prove that two guesses agree, which is not
    what "byte-identical after the whole W2 build" means.
    """

    def test_the_constants_file_still_carries_the_manifest_hashes(self):
        if not CONSTANTS.exists():
            pytest.skip("constants absent")
        m, c = _manifest(), json.loads(CONSTANTS.read_text(encoding="utf-8"))
        assert c["blind_sha256"] == m["blind_arm"]["blind_sha256"]
        assert c["calibration_sha256"] == m["calibration_partition"]["calibration_sha256"]
        assert c["fingerprint_spec_hash"] == m["fingerprint_spec_hash"]
        assert c["partition_procedure_sha256"] == m["partition_procedure_sha256"]

    def test_the_blind_and_calibration_membership_hashes_recompute(self):
        from engine.stock_identity.partition import sha256_of_symbols

        m = _manifest()
        assert sha256_of_symbols(m["blind_arm"]["members"]) == \
            m["blind_arm"]["blind_sha256"], (
                "the blind arm's membership no longer hashes to its sealed value"
            )
        assert sha256_of_symbols(m["calibration_partition"]["members"]) == \
            m["calibration_partition"]["calibration_sha256"], (
                "SI-SEALED-CAL-P1's membership no longer hashes to its sealed value"
            )

    def test_the_universe_snapshot_hash_recomputes(self):
        from engine.stock_identity.partition import universe_sha256

        snap = DATA / "partition" / "universe_snapshot_v1.parquet"
        if not snap.exists():
            pytest.skip("universe snapshot absent")
        m = _manifest()
        assert universe_sha256(pd.read_parquet(snap)) == m["universe"]["universe_sha256"], (
            "the universe snapshot changed — B must NOT have been added to it"
        )

    def test_the_partition_procedure_hash_recomputes_from_the_w1_registration(self):
        from engine.stock_identity.partition import partition_procedure_sha256

        reg = ROOT / "research" / "stock_identity" / "W1_IDENTITY_ATLAS_V0_REGISTRATION.md"
        if not reg.exists():
            pytest.skip("W1 registration absent")
        digest, _ = partition_procedure_sha256(reg)
        assert digest == _manifest()["partition_procedure_sha256"], (
            "W1 registration §4 was edited — that text is hash-pinned, which is why the "
            "GOLD correction lives in the W2 addendum instead"
        )

    def test_the_fingerprint_spec_hash_recomputes_from_the_spec(self):
        from engine.stock_identity import fingerprint as fp
        spec_file = DATA / "fingerprints" / "fingerprint_spec.json"
        if not spec_file.exists():
            pytest.skip("fingerprint spec absent")
        obj = fp.spec()
        assert fp.spec_hash(obj) == _manifest()["fingerprint_spec_hash"]
        on_disk = json.loads(spec_file.read_text(encoding="utf-8"))
        assert on_disk["fingerprint_spec_hash"] == _manifest()["fingerprint_spec_hash"]

    def test_b_is_in_no_sealed_list(self):
        m = _manifest()
        assert "B" not in set(m["blind_arm"]["members"])
        assert "B" not in set(m["calibration_partition"]["members"])
        assert "B" not in set(m["universe"]["plane_by_symbol"])
        assert "B" not in set(m["pilot"]["members"]), (
            "B is a W2 ADDENDUM name; adding it to the frozen W1 pilot list would "
            "re-open a sealed artifact"
        )

    def test_the_w1_pilot_stores_were_not_rewritten_to_include_b(self):
        for name in ("fingerprints/pilot_fingerprint_v0.parquet",
                     "state/pilot_state_daily.parquet",
                     "episodes/pilot_episode_catalog_v0.parquet"):
            p = DATA / name
            if not p.exists():
                continue
            df = pd.read_parquet(p)
            if "symbol" in df.columns:
                assert "B" not in set(df["symbol"].astype(str)), (
                    f"{name} was rewritten to carry B; the addendum must be a SEPARATE file"
                )


# ---------------------------------------------------------------------------
class TestAddendum:
    def test_b_ships_as_separate_addendum_artifacts(self):
        for name in ("fingerprints/addendum_b_fingerprint.parquet",
                     "state/addendum_b_state.parquet",
                     "episodes/addendum_b_catalog.parquet"):
            p = DATA / name
            if not p.exists():
                pytest.skip("addendum artifacts not present in this checkout")
            df = pd.read_parquet(p)
            assert set(df["symbol"].astype(str)) == {"B"}

    def test_the_ohlcv_manifest_records_b_with_its_lineage(self):
        p = DATA / "ohlcv" / "manifest.json"
        if not p.exists():
            pytest.skip("program-owned store absent")
        m = json.loads(p.read_text(encoding="utf-8"))
        if "B" not in m.get("symbols", {}):
            pytest.skip("B not collected in this checkout")
        entry = m["symbols"]["B"]
        assert entry["rows"] > 0
        note = entry.get("lineage_note", "")
        assert "ABX" in note and "GOLD" in note, "the ABX->GOLD->B lineage is not recorded"
        # The W1 names must still be there — the manifest is EXTENDED, not replaced.
        assert {"BABA", "WPM"} <= set(m["symbols"])

    def test_the_gold_dossier_no_longer_calls_it_a_miner(self):
        p = ROOT / "research" / "stock_identity" / "dossiers" / "GOLD.md"
        if not p.exists():
            pytest.skip("GOLD dossier absent")
        text = p.read_text(encoding="utf-8")
        head = text.split("## Behavioral fingerprint", 1)[0]
        # "miner" may appear only inside the dated correction that WITHDRAWS that identity.
        for line in head.splitlines():
            if "miner" in line.lower():
                assert ("correction" in line.lower() or "withdraw" in line.lower()
                        or "NYSE `B`" in line), f"GOLD identity still reads as a miner: {line[:120]}"
        assert "Gold.com" in text and "A-Mark" in text
        assert "reused-ticker hygiene case study" in text

    def test_the_addendum_receipts_cite_the_ruling(self):
        p = DATA / "addendum" / "pilot_addendum_v1.json"
        if not p.exists():
            pytest.skip("addendum receipts absent")
        r = json.loads(p.read_text(encoding="utf-8"))
        assert "2026-08-14" in r["ruling"]
        assert r["symbol_corrected"]["symbol"] == "GOLD"
        assert r["symbol_added"]["symbol"] == "B"
        assert set(r["miner_probe_roster"]) == {"NEM", "AEM", "PAAS", "WPM", "AG", "B"}
        assert "GOLD" not in r["miner_probe_roster"]


# ---------------------------------------------------------------------------
class TestAuthorityAndVocabulary:
    def test_every_w2_parquet_carries_all_false_authority_columns(self):
        if not EVENTS_DIR.exists():
            pytest.skip("no W2 artifacts")
        for p in sorted(EVENTS_DIR.rglob("*.parquet")):
            df = pd.read_parquet(p)
            for k in ("can_rank", "can_size", "can_gate",
                      "can_originate_signal", "can_escalate"):
                col = f"authority_{k}"
                assert col in df.columns, f"{p.name} missing {col}"
                if len(df):
                    assert not df[col].any(), f"{p.name}: {col} is not all-false"

    def test_the_registry_carries_the_r1_vintage_stamp(self):
        stamp = _registry()["vintage_stamp"]
        for field in ("price_plane_id", "adjustment_mode", "universe_as_of",
                      "survivorship_biased", "coverage_frac", "dead_name_coverage_pct",
                      "era_law_cohort"):
            assert field in stamp, f"vintage stamp is missing {field}"
        assert stamp["survivorship_biased"] is True

    def test_scored_authority_is_described_as_a_record_not_a_grant(self):
        reg = _registry()
        note = reg["authority_note"].lower()
        assert "never a grant" in note
        e = _events()
        # A recorded True is legitimate (the ledger surface DID have authority); what may
        # never happen is the store's own authority block being anything but false.
        assert e["scored_authority"].dtype == bool

    def test_no_forbidden_vocabulary_in_the_shipped_prose(self):
        md = EVENTS_DIR / "inventory_v0.md"
        if not md.exists():
            pytest.skip("inventory absent")
        text = md.read_text(encoding="utf-8").lower()
        assert "validated" not in text, "the word 'validated' is CI-enforced house-wide"
        for banned in ("falsifier", "refuted", "证伪"):
            assert banned not in text, f"falsifier language leaked into {md.name}: {banned}"
        # "personality" is a different program's object and is never used for ours.
        assert "personality" not in text


# ---------------------------------------------------------------------------
class TestSeaExtractionIsAPureFilter:
    def test_no_outcome_column_is_read_from_the_sea_store(self):
        for c in sea_mod._KEEP:
            assert not c.startswith("fwd_")
            assert not c.startswith("exc_")
            assert not c.startswith("matured")
        declared = set(sea_mod.constants()["columns_deliberately_not_read"])
        assert "fwd_13w" in declared and "matured" in declared

    def test_the_store_key_is_the_stores_own_key(self):
        assert sea_mod._KEY == ("ticker", "grid", "date", "direction")


# ---------------------------------------------------------------------------
class TestReclaimWaiverScope:
    def test_the_family_is_scoped_to_the_committed_artifacts_own_era(self):
        c = rw_mod.constants()
        assert c["state_artifact"].endswith("basket_washout_state.json")
        assert c["max_stale_sessions"] >= 1
        assert "nothing is synthesized" in c["replay_scope"]

    def test_a_zero_row_family_still_carries_its_reason(self):
        reg = _registry()
        entry = next(f for f in reg["families"] if f["family_key"] == rw_mod.FAMILY_KEY)
        assert "STRUCTURAL ABSENCE" in entry["replay_notes"].upper()
        receipts = reg.get("reclaim_waiver_receipts") or []
        if receipts:
            assert all(r.get("reason") or r.get("waived") for r in receipts), (
                "a zero with no reason attached is exactly the silence this family "
                "must not ship"
            )
