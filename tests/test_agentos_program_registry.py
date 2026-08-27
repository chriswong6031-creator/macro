from __future__ import annotations

from pathlib import Path

from scripts import agentos


def _write_registry(
    path: Path,
    *,
    lifecycle_states: tuple[str, ...] = ("operating", "building"),
    programs_yaml: str,
) -> None:
    lifecycle = "\n".join(f"    - {value}" for value in lifecycle_states)
    path.write_text(
        "schema: mastermind_programs.v1\n"
        "ontology:\n"
        "  lifecycle_states:\n"
        f"{lifecycle}\n"
        "programs:\n"
        f"{programs_yaml}",
        encoding="utf-8",
    )


def test_program_registry_normalizes_exact_keys_and_sorts_them(tmp_path: Path) -> None:
    path = tmp_path / "mastermind_programs.yml"
    _write_registry(
        path,
        programs_yaml=(
            "  beta-program:\n"
            "    name: Beta\n"
            "    category: market_intelligence\n"
            "    kind: intelligence_program\n"
            "    lifecycle_state: building\n"
            "    scope: project\n"
            "  alpha-program:\n"
            "    name: Alpha\n"
            "    category: project_infrastructure\n"
            "    kind: infrastructure\n"
            "    lifecycle_state: operating\n"
            "    scope: project\n"
        ),
    )

    got = agentos._load_program_registry(path)

    assert got["schema"] == "agentos.program_registry.v1"
    assert got["available"] is True
    assert [row["key"] for row in got["programs"]] == ["alpha-program", "beta-program"]
    assert got["programs"][1]["lifecycle_state"] == "building"


def test_program_registry_lifecycle_membership_comes_from_authored_ontology(tmp_path: Path) -> None:
    path = tmp_path / "mastermind_programs.yml"
    _write_registry(
        path,
        lifecycle_states=("operating", "building", "evidence_wait"),
        programs_yaml=(
            "  alpha-program:\n"
            "    name: Alpha\n"
            "    category: market_intelligence\n"
            "    kind: research_program\n"
            "    lifecycle_state: evidence_wait\n"
            "    scope: project\n"
        ),
    )

    got = agentos._load_program_registry(path)

    assert got["available"] is True
    assert got["programs"][0]["lifecycle_state"] == "evidence_wait"


def test_program_registry_rejects_lifecycle_absent_from_authored_ontology(tmp_path: Path) -> None:
    path = tmp_path / "mastermind_programs.yml"
    _write_registry(
        path,
        lifecycle_states=("operating", "building"),
        programs_yaml=(
            "  alpha-program:\n"
            "    name: Alpha\n"
            "    category: market_intelligence\n"
            "    kind: research_program\n"
            "    lifecycle_state: evidence_wait\n"
            "    scope: project\n"
        ),
    )

    got = agentos._load_program_registry(path)

    assert got["available"] is False
    assert got["reason"] == "program_registry_malformed"
    assert got["programs"] == []


def test_richer_metadata_failure_does_not_delete_legacy_program_key(
    tmp_path: Path, monkeypatch,
) -> None:
    path = tmp_path / "mastermind_programs.yml"
    _write_registry(
        path,
        programs_yaml=(
            "  alpha-program:\n"
            "    category: market_intelligence\n"
            "    kind: research_program\n"
            "    lifecycle_state: building\n"
            "    scope: project\n"
        ),
    )
    monkeypatch.setattr(agentos, "_PROGRAMS", path)

    assert agentos._load_programs() == {"alpha-program"}
    got = agentos._load_program_registry(path)
    assert got["available"] is False
    assert got["reason"] == "program_registry_malformed"


def test_program_registry_missing_source_is_explicit_unavailable(tmp_path: Path) -> None:
    got = agentos._load_program_registry(tmp_path / "missing.yml")

    assert got == {
        "schema": "agentos.program_registry.v1",
        "available": False,
        "reason": "program_registry_unavailable",
        "source": "config/mastermind_programs.yml",
        "programs": [],
    }


def test_program_identity_is_mapping_key_not_display_name(tmp_path: Path) -> None:
    path = tmp_path / "mastermind_programs.yml"
    _write_registry(
        path,
        programs_yaml=(
            "  alpha-program:\n"
            "    name: Totally Different Display Name\n"
            "    category: market_intelligence\n"
            "    kind: research_program\n"
            "    lifecycle_state: building\n"
            "    scope: project\n"
        ),
    )

    got = agentos._load_program_registry(path)

    assert got["available"] is True
    assert [row["key"] for row in got["programs"]] == ["alpha-program"]
    assert got["programs"][0]["name"] == "Totally Different Display Name"
