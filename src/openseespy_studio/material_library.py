from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json
from importlib import resources
from typing import Any

from .project import MaterialData


_LIBRARY_RESOURCE = (
    "resources",
    "materials",
    "verified_library.json",
)


@dataclass(frozen=True, slots=True)
class MaterialLibraryRecord:
    id: str
    family: str
    material: str
    grade: str
    standard: str
    model: str
    preset_name: str
    parameters_si: dict[str, float]
    verified_parameters: tuple[str, ...]
    applicability: tuple[str, ...]
    limitations: tuple[str, ...]
    primary_reference: dict[str, Any]
    parameter_evidence: dict[str, Any]
    verification: dict[str, Any]
    response_quantity: str
    source_units: dict[str, str]

    @property
    def doi(self) -> str:
        return str(self.primary_reference.get("doi", "")).strip()

    @property
    def is_verified(self) -> bool:
        return (
            str(self.verification.get("status", "")).lower() == "verified"
            and bool(self.verification.get("parameter_location_identified"))
            and bool(self.verification.get("units_checked"))
        )

    def source_metadata(self) -> dict[str, Any]:
        return {
            "library": "SARE verified material library",
            "record_id": self.id,
            "status": "verified" if self.is_verified else "unverified",
            "family": self.family,
            "material": self.material,
            "grade": self.grade,
            "standard": self.standard,
            "model": self.model,
            "verified_parameters": list(self.verified_parameters),
            "primary_reference": deepcopy(self.primary_reference),
            "parameter_evidence": deepcopy(self.parameter_evidence),
            "applicability": list(self.applicability),
            "limitations": list(self.limitations),
            "verification": deepcopy(self.verification),
            "response_quantity": self.response_quantity,
            "source_units": deepcopy(self.source_units),
        }


def _resource_text() -> str:
    root = resources.files("openseespy_studio")
    resource = root
    for part in _LIBRARY_RESOURCE:
        resource = resource.joinpath(part)
    return resource.read_text(encoding="utf-8")


def _validate_reference(reference: dict[str, Any], record_id: str) -> None:
    source_type = str(reference.get("type", "")).strip().lower()
    if source_type == "journal" and not str(reference.get("doi", "")).strip():
        raise ValueError(
            f"Verified material record {record_id!r} has a journal source "
            "without a DOI."
        )
    if not str(reference.get("title", "")).strip():
        raise ValueError(
            f"Verified material record {record_id!r} has no source title."
        )


def _record_from_dict(raw: dict[str, Any]) -> MaterialLibraryRecord:
    record_id = str(raw.get("id", "")).strip()
    if not record_id:
        raise ValueError("Material library record has no id.")

    reference = dict(raw.get("primary_reference", {}))
    evidence = dict(raw.get("parameter_evidence", {}))
    verification = dict(raw.get("verification", {}))
    _validate_reference(reference, record_id)

    if str(verification.get("status", "")).lower() != "verified":
        raise ValueError(
            f"Official material library record {record_id!r} is not verified."
        )
    if not bool(verification.get("parameter_location_identified")):
        raise ValueError(
            f"Official material library record {record_id!r} has no exact "
            "parameter-evidence location."
        )

    parameters = {
        str(key): float(value)
        for key, value in dict(raw.get("parameters_si", {})).items()
    }
    verified = tuple(
        str(value)
        for value in raw.get("verified_parameters", [])
    )
    missing = [key for key in parameters if key not in verified]
    if missing:
        raise ValueError(
            f"Official material library record {record_id!r} contains "
            "unverified parameter(s): " + ", ".join(missing)
        )

    return MaterialLibraryRecord(
        id=record_id,
        family=str(raw.get("family", "")).strip(),
        material=str(raw.get("material", "")).strip(),
        grade=str(raw.get("grade", "")).strip(),
        standard=str(raw.get("standard", "")).strip(),
        model=str(raw.get("model", "")).strip(),
        preset_name=str(raw.get("preset_name", "")).strip(),
        parameters_si=parameters,
        verified_parameters=verified,
        applicability=tuple(
            str(value) for value in raw.get("applicability", [])
        ),
        limitations=tuple(
            str(value) for value in raw.get("limitations", [])
        ),
        primary_reference=reference,
        parameter_evidence=evidence,
        verification=verification,
        response_quantity=str(
            raw.get("response_quantity", "")
        ).strip().lower(),
        source_units={
            str(key): str(value)
            for key, value in dict(
                raw.get("source_units", {})
            ).items()
        },
    )


def load_verified_material_library() -> tuple[MaterialLibraryRecord, ...]:
    payload = json.loads(_resource_text())
    if int(payload.get("schema_version", 0)) != 1:
        raise ValueError("Unsupported SARE material-library schema version.")
    records = tuple(
        _record_from_dict(dict(raw))
        for raw in payload.get("records", [])
    )
    ids = [record.id for record in records]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate material-library record id.")
    return records


def material_from_library_record(
    record: MaterialLibraryRecord,
    *,
    tag: int,
    name: str | None = None,
) -> MaterialData:
    if not record.is_verified:
        raise ValueError(
            "Only verified library records can be added to a project."
        )
    return MaterialData(
        tag=tag,
        name=name or f"{record.grade} · {record.model}",
        material_type=record.model,
        parameters=dict(record.parameters_si),
        source=record.source_metadata(),
    )
