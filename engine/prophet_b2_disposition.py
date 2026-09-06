"""Frozen B-15..B-19 disposition matrix + correction/replay/mutation law (V4 B2-0).

This module deliberately has no file writes and no source-system imports.  It is a
RECORDS surface: a frozen, append-only matrix of launch-review finding dispositions
with deterministic classification, correction/supersession lineage, and point-in-time
replay.  It carries NO authority — nothing in engine/ or scripts/ may import it (the
suite's tree-scan test pins that boundary); the deciders it describes never read it.

The evidence law (macro issue #6805, v4 masterplan B2-0):

* Every record cites BOTH sides of the audit: the audit-pin citation (the readiness
  review's own line refs, measured against PR #5370 head ``edaf501a``) and the HEAD
  citation (re-verified at ``fdaf4091``).  The audit's line numbers are stale by
  design — the readiness doc says so itself (:212-217) — so neither citation is ever
  "corrected" into the other; they are two pins on one finding.
* PROVEN_CLOSED is never granted from code reading alone: it requires a discriminating
  test that was actually RUN, with its output cited in the record.
* FUTURE_KNOWLEDGE: replay at ``as_of`` sees only records with ``known_at <= as_of``.
  A record learned later can never leak backward, and the absence of a knowable record
  is answered ``UNKNOWN_EVIDENCE_REQUIRED`` — never silently read as closed.
"""
from __future__ import annotations

from datetime import date
import re
from types import MappingProxyType
from typing import Mapping, Sequence

#: The six disposition classes, verbatim from macro issue #6805.
DISPOSITION_CLASSES = frozenset({
    "PROVEN_CLOSED",
    "BUILT_NOT_PROVEN",
    "STILL_LIVE",
    "SUPERSEDED_BY_ACCEPTED_OWNER",
    "REJECTED_BY_DESIGN",
    "UNKNOWN_EVIDENCE_REQUIRED",
})

#: Rule lineage stamp (modeled on UNION_ADMISSION_ERA / DEFAULT_DEFINITION_ERA):
#: every outcome this module returns is comparable only within this rule version.
DISPOSITION_RULE_VERSION = "b2-disposition-v1-2026-09-04"

#: The launch-review findings this matrix is TOTAL over.
FINDING_IDS = ("B-15", "B-16", "B-17", "B-18", "B-19")

#: The two evidence pins every baked record must carry (see module docstring).
AUDIT_PIN = "edaf501ae7e4e1547e6124d50dd1b59e3cb17954"
HEAD_PIN = "fdaf40910809de8da38e91c4696abfa22d2199e0"

_PIN_RE = re.compile(r"^[0-9a-f]{7,40}$")


class DispositionContractError(ValueError):
    """Raised when disposition-matrix contract data is malformed or mutated."""


def _require(condition: bool, code: str, detail: str) -> None:
    if not condition:
        raise DispositionContractError(f"{code}: {detail}")


def _iso_date(value: object, *, code: str, field: str) -> str:
    _require(isinstance(value, str), code, f"{field} must be an ISO date string")
    try:
        date.fromisoformat(value)  # type: ignore[arg-type]
    except ValueError as exc:
        raise DispositionContractError(f"{code}: {field} is not an ISO date: {value!r}") from exc
    return str(value)


def _freeze_record(record: Mapping[str, object]) -> Mapping[str, object]:
    """Validate one record and return an immutable (read-only) copy of it."""
    _require(isinstance(record, Mapping), "RECORD_INVALID", "record must be a mapping")
    finding_id = record.get("finding_id")
    _require(finding_id in FINDING_IDS, "DISPOSITION_UNTOTAL",
             f"unknown finding id {finding_id!r}; the matrix is total over {FINDING_IDS}")
    owner = record.get("owner")
    _require(isinstance(owner, str) and bool(owner), "OWNER_UNKNOWN",
             f"{finding_id} record has a missing or empty finding owner")
    clazz = record.get("disposition")
    _require(clazz in DISPOSITION_CLASSES, "DISPOSITION_CLASS_UNKNOWN",
             f"{finding_id} record carries unknown class {clazz!r}")
    reason = record.get("reason")
    _require(isinstance(reason, str) and bool(reason), "REASON_MISSING",
             f"{finding_id} record has no stable reason string")
    rule_version = record.get("rule_version")
    _require(rule_version == DISPOSITION_RULE_VERSION, "RULE_VERSION_UNKNOWN",
             f"{finding_id} record stamped {rule_version!r}, this lineage is "
             f"{DISPOSITION_RULE_VERSION!r}")
    _require("known_at" in record and record.get("known_at") is not None, "SOURCE_UNKNOWN",
             f"{finding_id} record has no known_at — evidence with no knowability date "
             f"cannot participate in point-in-time replay")
    known_at = _iso_date(record.get("known_at"), code="SOURCE_UNKNOWN", field="known_at")
    recorded_at = _iso_date(record.get("recorded_at"), code="RECORD_CLOCK_INVALID",
                            field="recorded_at")
    _require(known_at <= recorded_at, "RECORD_CLOCK_INVALID",
             f"{finding_id} record recorded_at {recorded_at} precedes known_at {known_at}")
    evidence = record.get("evidence")
    _require(isinstance(evidence, Sequence) and not isinstance(evidence, (str, bytes))
             and len(evidence) > 0, "EVIDENCE_UNCITED",
             f"{finding_id} record carries no evidence citations")
    frozen_evidence = []
    for entry in evidence:  # type: ignore[union-attr]
        _require(isinstance(entry, Mapping), "EVIDENCE_UNCITED",
                 f"{finding_id} evidence entry must be a mapping")
        cite, pin = entry.get("cite"), entry.get("pin")
        _require(isinstance(cite, str) and bool(cite), "EVIDENCE_UNCITED",
                 f"{finding_id} evidence entry has no cite")
        _require(isinstance(pin, str) and bool(_PIN_RE.match(pin)), "EVIDENCE_UNCITED",
                 f"{finding_id} evidence cite {cite!r} has no commit pin")
        frozen_evidence.append(MappingProxyType({"cite": cite, "pin": pin}))
    seq = record.get("seq")
    _require(isinstance(seq, int) and not isinstance(seq, bool) and seq >= 1,
             "CORRECTION_CHAIN_BROKEN", f"{finding_id} record seq must be a positive integer")
    supersedes = record.get("supersedes")
    _require(supersedes is None or (isinstance(supersedes, int)
                                    and not isinstance(supersedes, bool) and supersedes >= 1),
             "CORRECTION_CHAIN_BROKEN",
             f"{finding_id} supersedes must be null or a positive integer")
    return MappingProxyType({
        "finding_id": finding_id,
        "owner": owner,
        "disposition": clazz,
        "reason": reason,
        "rule_version": rule_version,
        "evidence": tuple(frozen_evidence),
        "known_at": known_at,
        "recorded_at": recorded_at,
        "seq": seq,
        "supersedes": supersedes,
    })


def _validate_lineage(records: Sequence[Mapping[str, object]]) -> None:
    """Correction chains must be gapless, fork-free, and never backdated."""
    latest: dict[str, Mapping[str, object]] = {}
    for record in records:
        finding_id = str(record["finding_id"])
        prior = latest.get(finding_id)
        if prior is None:
            _require(record["seq"] == 1 and record["supersedes"] is None,
                     "CORRECTION_CHAIN_BROKEN",
                     f"{finding_id} chain must start at seq=1 with supersedes=null, "
                     f"got seq={record['seq']} supersedes={record['supersedes']}")
        else:
            _require(record["seq"] == int(prior["seq"]) + 1,  # type: ignore[arg-type]
                     "CORRECTION_CHAIN_BROKEN",
                     f"{finding_id} chain gap: seq {record['seq']} after seq {prior['seq']}")
            _require(record["supersedes"] == prior["seq"], "CORRECTION_CHAIN_BROKEN",
                     f"{finding_id} record seq={record['seq']} must supersede the current "
                     f"head seq={prior['seq']}, claims {record['supersedes']}")
            _require(str(record["known_at"]) >= str(prior["known_at"]),
                     "CORRECTION_CHAIN_BROKEN",
                     f"{finding_id} correction backdated: known_at {record['known_at']} "
                     f"precedes its predecessor's {prior['known_at']}")
        latest[finding_id] = record


def build_matrix(records: Sequence[Mapping[str, object]]) -> tuple[Mapping[str, object], ...]:
    """Validate + freeze a full record sequence into an immutable matrix."""
    frozen = tuple(_freeze_record(record) for record in records)
    _validate_lineage(frozen)
    return frozen


def supersede(matrix: Sequence[Mapping[str, object]],
              new_record: Mapping[str, object]) -> tuple[Mapping[str, object], ...]:
    """Append-only correction: returns a NEW matrix; never mutates or deletes.

    The base matrix is re-validated first, so a tampered or gapped base fails closed
    before any append; the new record must extend its finding's chain exactly
    (seq = head+1, supersedes = head, known_at not backdated).  Replay at any earlier
    ``as_of`` reproduces the earlier answer after the supersession — see
    :func:`disposition`.
    """
    base = build_matrix(matrix)
    appended = build_matrix(tuple(base) + (new_record,))
    return appended


def disposition(finding_id: str, *, as_of: str,
                matrix: Sequence[Mapping[str, object]] | None = None) -> dict[str, object]:
    """The disposition of ``finding_id`` as it was knowable at ``as_of``.

    TOTAL over :data:`FINDING_IDS` — an unknown id raises DISPOSITION_UNTOTAL rather
    than returning anything.  Only records with ``known_at <= as_of`` are visible
    (FUTURE_KNOWLEDGE exclusion); the chain head among the visible records answers.
    With no knowable record the answer is ``UNKNOWN_EVIDENCE_REQUIRED`` — never a
    silent default to closed.
    """
    _require(finding_id in FINDING_IDS, "DISPOSITION_UNTOTAL",
             f"unknown finding id {finding_id!r}; the matrix is total over {FINDING_IDS}")
    cut = _iso_date(as_of, code="AS_OF_INVALID", field="as_of")
    source = DISPOSITION_MATRIX if matrix is None else build_matrix(matrix)
    chain = [record for record in source if record["finding_id"] == finding_id]
    visible = [record for record in chain if str(record["known_at"]) <= cut]
    if not visible:
        excluded = len(chain)
        return {
            "finding_id": finding_id,
            "disposition": "UNKNOWN_EVIDENCE_REQUIRED",
            "reason": (f"no record knowable at {cut} (FUTURE_KNOWLEDGE: {excluded} "
                       f"record(s) known only later are excluded); absence of evidence "
                       f"is never read as closed"),
            "rule_version": DISPOSITION_RULE_VERSION,
            "evidence": (),
            "known_at": None,
            "seq": None,
            "as_of": cut,
        }
    head = max(visible, key=lambda record: int(record["seq"]))  # type: ignore[arg-type]
    return {**dict(head), "as_of": cut}


# ─────────────────────────────────────────────────── the baked v1 matrix ────
#
# Dispositions are EVIDENCE-TRUE, not spec-true: every PROVEN_CLOSED row cites the
# discriminating run actually performed on 2026-09-04 against a clean tree at exact
# HEAD fdaf4091 (transcripts frozen in
# research/prophet_v4/B2_0_DISPOSITION_AND_MUTATION_PACKET_2026-09-04.md).

_OWNER = "WS:PROPHET-US-V4-RECOVERY.b2"

_V1_RECORDS: tuple[dict[str, object], ...] = (
    {
        "finding_id": "B-15",
        "owner": _OWNER,
        "disposition": "PROVEN_CLOSED",
        "reason": (
            "Open-bucket union repaint healed and the walk-forward ghost discriminator "
            "was RUN green at exact HEAD: _completed_bucket_mask excludes the still-open "
            "3D bucket until its deterministic final session slot, and the 150-session "
            "walk-forward replay (STLD+NEM) demands every fire stay put and identically "
            "dated. Proof scope: the committed fixtures, local py3.14.7 run of "
            "2026-09-04; CI re-proof rides the prophet-anticipation-intake "
            "union-admission step on every push."
        ),
        "rule_version": DISPOSITION_RULE_VERSION,
        "evidence": [
            {"cite": ("research/US_PROPHET_COMMERCIAL_LAUNCH_READINESS_2026-08.md:184 — "
                      "B-15 audit row (PR #5370 ships a NEW repaint; STLD 8→4 live fires, "
                      "NEM 20→7; audit refs engine/us_early_turn.py:651-653,:835,"
                      ":1102-1103 at the review pin)"),
             "pin": AUDIT_PIN},
            {"cite": ("engine/us_early_turn.py:662-696 _completed_bucket_mask (a row is "
                      "admissible iff its bucket closed, or it IS asof on the bucket's "
                      "final session slot), applied at :721-722 inside "
                      "_union_relaxed_cross_fires"),
             "pin": HEAD_PIN},
            {"cite": ("RUN 2026-09-04, clean tree at HEAD: python3 -m pytest "
                      "tests/test_us_early_turn_union_admission.py::"
                      "test_a_live_fire_never_disappears_or_re_dates_itself -v => "
                      "PASSED[STLD] + PASSED[NEM] (suite tally '7 passed in 19.21s'; "
                      "full-file run '80 passed in 27.13s')"),
             "pin": HEAD_PIN},
        ],
        "known_at": "2026-09-04",
        "recorded_at": "2026-09-04",
        "seq": 1,
        "supersedes": None,
    },
    {
        "finding_id": "B-16",
        "owner": _OWNER,
        "disposition": "PROVEN_CLOSED",
        "reason": (
            "Schema/manifest consistency restored and BOTH discriminating checks were "
            "RUN at exact HEAD: (1) the scheduled hard-fail gate command itself "
            "(scripts/check_contract_drift.py) exits 0 with the per_stock_signal entry "
            "live-sampled; (2) the regeneration diff — build_manifest().artifacts vs the "
            "committed artifact_manifest.json — is byte-identical, so the manifest is "
            "provably regenerated, not stale. early_signal_dates is registered OPTIONAL "
            "under schema_version 1.3.0, which the live tape proves correct: 245/246 "
            "site/signals files carry the stamp and SATS.json lawfully omits it "
            "(all-or-nothing emitter). Caveat recorded, not a leg: the drift gate "
            "samples only the FIRST wildcard file, and that file now carries the field, "
            "so a planted pre-heal manifest no longer re-reds the gate on today's tape "
            "— a gate-sensitivity note for a future wave, outside this finding's claim."
        ),
        "rule_version": DISPOSITION_RULE_VERSION,
        "evidence": [
            {"cite": ("research/US_PROPHET_COMMERCIAL_LAUNCH_READINESS_2026-08.md:185 — "
                      "B-16 audit row (conditional early_signal_dates registered "
                      "ALWAYS-PRESENT, schema_version unbumped, manifest not regenerated; "
                      "audit refs engine/signal_quality.py:937-949, "
                      "scripts/export_signal_contracts.py:170-180,:223, "
                      ".github/ci/legacy-jobs.yml:2172 at the review pin)"),
             "pin": AUDIT_PIN},
            {"cite": ("scripts/export_signal_contracts.py:231-245 — per_stock_signal "
                      "schema_version 1.3.0 with optional_fields=[early_signal_dates]; "
                      "pairing validated by scripts/validate_signals.py:153-197 (length "
                      "register + knowability order, stamp never before its own label)"),
             "pin": HEAD_PIN},
            {"cite": ("RUN 2026-09-04 at HEAD: python3 scripts/check_contract_drift.py "
                      "=> 'contract drift: 0 drift(s), 10 clean, 1 skipped (no live "
                      "sample) [11 entries total]', exit 0 — the same command the "
                      "hard-fail gates run (.github/workflows/ci-main-heartbeat.yml:96-97; "
                      "pack-lane twin .github/ci/legacy-jobs.yml:4310-4336)"),
             "pin": HEAD_PIN},
            {"cite": ("RUN 2026-09-04 at HEAD: regeneration diff — "
                      "export_signal_contracts.build_manifest()['artifacts'] vs committed "
                      "site/factordata/contracts/artifact_manifest.json 'artifacts': "
                      "byte-identical canonical JSON (11 = 11 entries); live census "
                      "245/246 site/signals/*.json carry early_signal_dates, SATS.json "
                      "omits it"),
             "pin": HEAD_PIN},
        ],
        "known_at": "2026-09-04",
        "recorded_at": "2026-09-04",
        "seq": 1,
        "supersedes": None,
    },
    {
        "finding_id": "B-17",
        "owner": _OWNER,
        "disposition": "STILL_LIVE",
        "reason": (
            "The measurement leg is open: the 60.6% recall / 12-session-lead numbers "
            "describe the NAKED union over the whole panel, while the shipped deck is "
            "union ∩ select_candidates — the shipped roster has never been re-measured "
            "(J-16), and §8.1 claim 1 stays SUSPENDED at HEAD. The disclosure leg alone "
            "is closed (the code states the deck is not the naked universe, and a test "
            "pins the strings), but a disclosure cannot close a measurement gap. "
            "Promote-condition: a frozen re-measurement of the shipped "
            "union ∩ select_candidates roster's coverage/lead on the bake-off panel, "
            "superseding this record via the append-only chain."
        ),
        "rule_version": DISPOSITION_RULE_VERSION,
        "evidence": [
            {"cite": ("research/US_PROPHET_COMMERCIAL_LAUNCH_READINESS_2026-08.md:186 — "
                      "B-17 audit row (shipped deck is not the measured object; audit "
                      "refs engine/prophet_bridge.py:4018,:4318-4319,:1127-1132 and "
                      "engine/us_early_turn.py:1096-1099 at the review pin)"),
             "pin": AUDIT_PIN},
            {"cite": ("MEASUREMENT LEG OPEN at HEAD: readiness doc :211-217 (the "
                      "05d24b60 repair 'does not close J-16/B-17') and :841-847 (§8.1 "
                      "claim 1 'SUSPENDED until B-17 is fixed or re-measured'); no "
                      "re-measurement artifact of the shipped roster exists at fdaf4091"),
             "pin": HEAD_PIN},
            {"cite": ("DISCLOSURE LEG CLOSED at HEAD: engine/us_early_turn.py:1196-1203 "
                      "(deck = union ∩ select_candidates; bake-off coverage/lead are "
                      "NAKED-UNION numbers and NOT a property of this deck) pinned by "
                      "tests/test_us_early_turn_union_admission.py:598-609; RUN "
                      "2026-09-04: PASSED (disclosure strings only — the pin itself "
                      "says it cannot claim the measurement)"),
             "pin": HEAD_PIN},
        ],
        "known_at": "2026-09-04",
        "recorded_at": "2026-09-04",
        "seq": 1,
        "supersedes": None,
    },
    {
        "finding_id": "B-18",
        "owner": _OWNER,
        "disposition": "PROVEN_CLOSED",
        "reason": (
            "Deck ⊇ plan inversion healed by scope-not-nulls and the discriminators "
            "were RUN green at exact HEAD: a confirmed-lane row carries NO early-lane "
            "keys at all (absence, never nulls), every early-lane row is era-stamped "
            "unconditionally with UNION_ADMISSION_ERA, and a 120-session two-fixture "
            "sweep proves union fire ⇒ deck row and licensed plan ⇒ deck row with both "
            "surfaces populated (non-vacuous). Proof scope: committed fixtures, local "
            "py3.14.7 run of 2026-09-04; CI re-proof rides the union-admission step."
        ),
        "rule_version": DISPOSITION_RULE_VERSION,
        "evidence": [
            {"cite": ("research/US_PROPHET_COMMERCIAL_LAUNCH_READINESS_2026-08.md:187 — "
                      "B-18 audit row (114 STLD sessions with fired=True, "
                      "deck_admitted=False and admission_era: None; audit refs "
                      "engine/us_early_turn.py:1047-1058,:1102-1103, "
                      "engine/prophet_bridge.py:4181-4182 at the review pin)"),
             "pin": AUDIT_PIN},
            {"cite": ("engine/us_early_turn.py:1186-1218 — confirmed lane returns with "
                      "no early-lane block (:1186-1194, absence never nulls); early lane "
                      "stamps admission_era: UNION_ADMISSION_ERA unconditionally at "
                      ":1211 (#4942 era-stamp law), deck_admitted True at :1218"),
             "pin": HEAD_PIN},
            {"cite": ("RUN 2026-09-04, clean tree at HEAD: "
                      "tests/test_us_early_turn_union_admission.py:526-539 (no "
                      "early-lane key leaks onto a confirmed row) PASSED; :542-567 "
                      "(120-session sweep, fire⇒deck and plan⇒deck, fires>0 and "
                      "plans>0) PASSED; :570-577 (era present iff early lane, never "
                      "None) PASSED — tally '7 passed in 19.21s'"),
             "pin": HEAD_PIN},
        ],
        "known_at": "2026-09-04",
        "recorded_at": "2026-09-04",
        "seq": 1,
        "supersedes": None,
    },
    {
        "finding_id": "B-19",
        "owner": _OWNER,
        "disposition": "PROVEN_CLOSED",
        "reason": (
            "Dead-fire chase verdict healed and the discriminator was RUN green at "
            "exact HEAD: the chase/age leg keys on a LIVE union fire (fired AND "
            "fire_date), never on the mere presence of a fire_date, and the pin test "
            "drives a 2.5-month-dead fire through the geometry read — chase_pct None, "
            "age_bars None, no chase/turned chip, and no setup_geometry on the "
            "confirmed lane at all. Proof scope: committed fixtures, local py3.14.7 "
            "run of 2026-09-04; CI re-proof rides the union-admission step."
        ),
        "rule_version": DISPOSITION_RULE_VERSION,
        "evidence": [
            {"cite": ("research/US_PROPHET_COMMERCIAL_LAUNCH_READINESS_2026-08.md:188 — "
                      "B-19 audit row (chase verdict fires off a DEAD union fire on "
                      "every plan incl. confirmed-lane buy_now; audit refs "
                      "engine/us_early_turn.py:948 keying on fire_date, "
                      "engine/prophet_bridge.py:300-302,:4536-4569 at the review pin)"),
             "pin": AUDIT_PIN},
            {"cite": ("engine/us_early_turn.py:1024-1039 — the chase leg is gated at "
                      ":1031 on union.get('fired') AND union.get('fire_date'); the "
                      "comment names the healed failure (a fire expired 2.5 months "
                      "earlier put the chip on rows it had no claim on)"),
             "pin": HEAD_PIN},
            {"cite": ("RUN 2026-09-04, clean tree at HEAD: "
                      "tests/test_us_early_turn_union_admission.py:580-595 "
                      "test_a_dead_fire_never_emits_a_chase_chip (dead 2026-03-25 fire, "
                      "age_bars>50 ⇒ chase_pct None, age None, chip text clean, "
                      "confirmed row has no setup_geometry) PASSED — tally "
                      "'7 passed in 19.21s'"),
             "pin": HEAD_PIN},
        ],
        "known_at": "2026-09-04",
        "recorded_at": "2026-09-04",
        "seq": 1,
        "supersedes": None,
    },
)

#: The frozen v1 matrix — validated and deep-frozen at import time.
DISPOSITION_MATRIX: tuple[Mapping[str, object], ...] = build_matrix(_V1_RECORDS)
