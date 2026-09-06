"""Country political / policy-stance dossier leaf (context_only).

Deterministic over a curated, source-cited YAML substrate under
``knowledge/policy_geo/country_dossier/``. Never raises into the build —
malformed input returns ``state="invalid"``; ``validate_view`` is the
fail-closed gate. No network I/O, no LLM, no scoring-core imports.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from lib import config

SCHEMA = "country_dossier.v1"
STANCE_KEYS = ("tightening_bias", "easing_bias", "on_hold", "mixed", "not_stated")
SEAT_KEYS = ("head_of_government", "central_bank", "finance", "legislature")
CLAIMS = ("FACT", "INFERENCE")
MAX_SEATS = 4
DOSSIER_DIRNAME = ("knowledge", "policy_geo", "country_dossier")

_MONTH_EN = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)


def dossier_path(cc: str, *, root: Path | None = None) -> Path:
    """Path to the curated dossier YAML for a region key (e.g. ``JP`` → ``jp.yaml``)."""
    base = root if root is not None else config.ROOT
    stem = str(cc or "").strip().lower()
    return base.joinpath(*DOSSIER_DIRNAME, f"{stem}.yaml")


def build_dossier_block(
    cc: str,
    *,
    today: date | None = None,
    root: Path | None = None,
) -> dict[str, Any]:
    """Total producer: always returns a dict with ``state``; never raises."""
    today = today or datetime.now(timezone.utc).date()
    cc_up = str(cc or "").strip().upper()
    empty = _empty_block(cc_up)

    try:
        path = dossier_path(cc_up, root=root)
    except Exception:  # noqa: BLE001 — total contract
        return {**empty, "state": "invalid", "reason": "path_error"}

    if not path.is_file():
        return {**empty, "state": "no_coverage", "reason": "file_absent"}

    try:
        raw_text = path.read_text(encoding="utf-8")
    except Exception:  # noqa: BLE001
        return {**empty, "state": "invalid", "reason": "unreadable"}

    try:
        data = yaml.safe_load(raw_text)
    except yaml.YAMLError:
        return {**empty, "state": "invalid", "reason": "unreadable"}
    except Exception:  # noqa: BLE001
        return {**empty, "state": "invalid", "reason": "unreadable"}

    if not isinstance(data, dict):
        return {**empty, "state": "invalid", "reason": "unreadable"}

    return _validate_and_build(data, path=path, cc_up=cc_up, today=today)


def _empty_block(cc_up: str) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "state": "no_coverage",
        "cc": cc_up or None,
        "rev": None,
        "reviewed_at": None,
        "reviewed_at_human_en": None,
        "reviewed_at_human_zh": None,
        "age_days": None,
        "review_interval_days": None,
        "stance": None,
        "seats": [],
        "reason": None,
    }


def _validate_and_build(
    data: dict[str, Any],
    *,
    path: Path,
    cc_up: str,
    today: date,
) -> dict[str, Any]:
    empty = _empty_block(cc_up)

    def fail(reason: str) -> dict[str, Any]:
        return {**empty, "state": "invalid", "reason": reason}

    stem = path.stem.lower()
    dossier_key = data.get("dossier")
    if not isinstance(dossier_key, str) or dossier_key.lower() != stem:
        return fail("dossier")

    if data.get("schema") != SCHEMA:
        return fail("schema")

    rev = data.get("rev")
    if not isinstance(rev, int) or isinstance(rev, bool) or rev < 1:
        return fail("rev")

    region = data.get("region")
    if not isinstance(region, str) or len(region) != 2 or not region.isalpha() or region != region.upper():
        return fail("region")
    if region != cc_up:
        # Join is checked in validate_view; here require a plain uppercase 2-letter key.
        # Mismatch with the requested cc is still invalid for this build.
        return fail("region")

    if data.get("tier") != "context_only":
        return fail("tier")

    reviewed_at = _parse_date(data.get("reviewed_at"))
    if reviewed_at is None:
        return fail("reviewed_at")
    if reviewed_at > today:
        return fail("reviewed_at")

    interval = data.get("review_interval_days")
    if not isinstance(interval, int) or isinstance(interval, bool) or interval < 1:
        return fail("review_interval_days")

    rights = data.get("rights")
    if rights not in {"public", "attribution_only", "suppressed"}:
        return fail("rights")

    if rights == "suppressed":
        return {
            "schema": SCHEMA,
            "state": "rights_suppressed",
            "cc": cc_up,
            "rev": rev,
            "reviewed_at": reviewed_at.isoformat(),
            "reviewed_at_human_en": _human_en(reviewed_at),
            "reviewed_at_human_zh": _human_zh(reviewed_at),
            "age_days": (today - reviewed_at).days,
            "stance": None,
            "seats": [],
            "reason": "rights_suppressed",
        }

    stance_raw = data.get("stance")
    stance, stance_err = _parse_stance(stance_raw, today=today)
    if stance_err:
        return fail(stance_err)

    seats_raw = data.get("seats")
    if not isinstance(seats_raw, list):
        return fail("seats")
    if not seats_raw or len(seats_raw) > MAX_SEATS:
        return fail("seats")

    seen_keys: set[str] = set()
    seats: list[dict[str, Any]] = []
    for i, seat_raw in enumerate(seats_raw):
        seat, seat_err = _parse_seat(seat_raw, today=today, index=i)
        if seat_err:
            return fail(seat_err)
        assert seat is not None
        if seat["key"] in seen_keys:
            return fail(f"seats[{i}].key")
        seen_keys.add(seat["key"])
        seats.append(seat)

    age_days = (today - reviewed_at).days
    state = "stale" if age_days > interval else "ok"

    return {
        "schema": SCHEMA,
        "state": state,
        "cc": cc_up,
        "rev": rev,
        "reviewed_at": reviewed_at.isoformat(),
        "reviewed_at_human_en": _human_en(reviewed_at),
        "reviewed_at_human_zh": _human_zh(reviewed_at),
        "age_days": age_days,
        "review_interval_days": interval,
        "stance": stance,
        "seats": seats,
        "reason": "stale" if state == "stale" else None,
    }


def _parse_stance(
    raw: Any, *, today: date
) -> tuple[dict[str, Any] | None, str | None]:
    if not isinstance(raw, dict):
        return None, "stance"
    key = raw.get("key")
    if key not in STANCE_KEYS:
        return None, "stance.key"
    claim = raw.get("claim")
    if claim not in CLAIMS:
        return None, "stance.claim"
    known_at = _parse_date(raw.get("known_at"))
    if known_at is None:
        return None, "stance.known_at"
    if known_at > today:
        return None, "stance.known_at"
    evidence, ev_err = _parse_evidence(raw.get("evidence"), path="stance.evidence", rights="public")
    if ev_err:
        return None, ev_err
    return (
        {
            "key": key,
            "claim": claim,
            "known_at": known_at.isoformat(),
            "known_at_human_en": _human_en(known_at),
            "known_at_human_zh": _human_zh(known_at),
            "evidence": evidence,
        },
        None,
    )


def _parse_seat(
    raw: Any, *, today: date, index: int
) -> tuple[dict[str, Any] | None, str | None]:
    prefix = f"seats[{index}]"
    if not isinstance(raw, dict):
        return None, prefix
    key = raw.get("key")
    if key not in SEAT_KEYS:
        return None, f"{prefix}.key"

    role = _bilingual(raw.get("role"), f"{prefix}.role")
    if isinstance(role, str):
        return None, role
    institution = _bilingual(raw.get("institution"), f"{prefix}.institution")
    if isinstance(institution, str):
        return None, institution

    seat_rights = raw.get("rights")
    if seat_rights not in {"public", "suppressed"}:
        return None, f"{prefix}.rights"
    jurisdiction = raw.get("jurisdiction")
    if jurisdiction not in {"settled", "ambiguous"}:
        return None, f"{prefix}.jurisdiction"

    claim = raw.get("claim")
    if claim not in CLAIMS:
        return None, f"{prefix}.claim"
    known_at = _parse_date(raw.get("known_at"))
    if known_at is None:
        return None, f"{prefix}.known_at"
    if known_at > today:
        return None, f"{prefix}.known_at"

    evidence, ev_err = _parse_evidence(
        raw.get("evidence"), path=f"{prefix}.evidence", rights=seat_rights
    )
    if ev_err:
        return None, ev_err

    since_raw = raw.get("since")
    since: date | None
    if since_raw is None:
        if key != "legislature":
            return None, f"{prefix}.since"
        since = None
    else:
        since = _parse_date(since_raw)
        if since is None:
            return None, f"{prefix}.since"
        if since > today:
            return None, f"{prefix}.since"

    note = _bilingual(raw.get("note"), f"{prefix}.note")
    if isinstance(note, str):
        return None, note
    # Length budgets (EN ≤ 90, ZH ≤ 42) — fail closed if exceeded.
    if len(note["en"]) > 90 or len(note["zh"]) > 42:
        return None, f"{prefix}.note"

    if seat_rights == "suppressed":
        return (
            {
                "key": key,
                "role": role,
                "institution": institution,
                "claim": claim,
                "known_at": known_at.isoformat(),
                "known_at_human_en": _human_en(known_at),
                "known_at_human_zh": _human_zh(known_at),
                "jurisdiction": jurisdiction,
                "rights": seat_rights,
                "evidence": evidence,
                "state": "rights_suppressed",
            },
            None,
        )

    if jurisdiction == "ambiguous":
        return (
            {
                "key": key,
                "role": role,
                "institution": institution,
                "note": note,
                "since": since.isoformat() if since else None,
                "since_human_en": _human_en(since) if since else None,
                "since_human_zh": _human_zh(since) if since else None,
                "claim": claim,
                "known_at": known_at.isoformat(),
                "known_at_human_en": _human_en(known_at),
                "known_at_human_zh": _human_zh(known_at),
                "jurisdiction": jurisdiction,
                "rights": seat_rights,
                "evidence": evidence,
                "state": "ambiguous_jurisdiction",
            },
            None,
        )

    holder = _bilingual(raw.get("holder"), f"{prefix}.holder")
    if isinstance(holder, str):
        return None, holder

    return (
        {
            "key": key,
            "role": role,
            "institution": institution,
            "holder": holder,
            "since": since.isoformat() if since else None,
            "since_human_en": _human_en(since) if since else None,
            "since_human_zh": _human_zh(since) if since else None,
            "note": note,
            "claim": claim,
            "known_at": known_at.isoformat(),
            "known_at_human_en": _human_en(known_at),
            "known_at_human_zh": _human_zh(known_at),
            "jurisdiction": jurisdiction,
            "rights": seat_rights,
            "evidence": evidence,
            "state": "ok",
        },
        None,
    )


def _parse_evidence(
    raw: Any, *, path: str, rights: str
) -> tuple[dict[str, Any] | None, str | None]:
    if rights == "suppressed":
        if raw is None:
            return None, path
        if not isinstance(raw, dict):
            return None, path
        source_url = raw.get("source_url")
        if not isinstance(source_url, str) or not source_url.startswith("https://"):
            return None, f"{path}.source_url"
        publisher = _bilingual(raw.get("publisher"), f"{path}.publisher")
        if isinstance(publisher, str):
            return None, publisher
        document = raw.get("document")
        version = raw.get("version")
        doc_out: dict[str, str] | None
        if document is None:
            doc_out = None
        else:
            parsed = _bilingual(document, f"{path}.document")
            if isinstance(parsed, str):
                return None, parsed
            doc_out = parsed
        if version is not None and not isinstance(version, str):
            return None, f"{path}.version"
        return (
            {
                "source_url": source_url,
                "publisher": publisher,
                "document": doc_out,
                "version": version,
            },
            None,
        )

    if not isinstance(raw, dict):
        return None, path
    source_url = raw.get("source_url")
    if not isinstance(source_url, str) or not source_url.startswith("https://"):
        return None, f"{path}.source_url"
    publisher = _bilingual(raw.get("publisher"), f"{path}.publisher")
    if isinstance(publisher, str):
        return None, publisher
    document = _bilingual(raw.get("document"), f"{path}.document")
    if isinstance(document, str):
        return None, document
    version = raw.get("version")
    if not isinstance(version, str) or not version:
        return None, f"{path}.version"
    return (
        {
            "source_url": source_url,
            "publisher": publisher,
            "document": document,
            "version": version,
        },
        None,
    )


def _bilingual(raw: Any, path: str) -> dict[str, str] | str:
    if not isinstance(raw, dict):
        return path
    en = raw.get("en")
    zh = raw.get("zh")
    if not isinstance(en, str) or not en.strip():
        return path
    if not isinstance(zh, str) or not zh.strip():
        return path
    return {"en": en, "zh": zh}


def _parse_date(raw: Any) -> date | None:
    if isinstance(raw, date) and not isinstance(raw, datetime):
        return raw
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, str):
        try:
            return date.fromisoformat(raw)
        except ValueError:
            return None
    return None


def _human_en(d: date) -> str:
    return f"{d.day} {_MONTH_EN[d.month - 1]} {d.year}"


def _human_zh(d: date) -> str:
    return f"{d.year}年{d.month}月{d.day}日"
