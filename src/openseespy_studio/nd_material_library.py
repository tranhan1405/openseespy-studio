from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json
import math
from datetime import date
from importlib import resources
from typing import Any

from .project import (
    ND_MATERIAL_PARAMETER_ORDER,
    NDMaterialData,
)


_LIBRARY_RESOURCE = (
    "resources",
    "materials",
    "verified_nd_library.json",
)


@dataclass(frozen=True, slots=True)
class NDMaterialLibraryRecord:
    id: str
    family: str
    material: str
    model: str
    preset_name: str
    parameters_si: dict[str, float]
    verified_parameters: tuple[str, ...]
    behavior: tuple[str, ...]
    compatibility: tuple[str, ...]
    applicability: tuple[str, ...]
    limitations: tuple[str, ...]
    primary_reference: dict[str, Any]
    parameter_evidence: dict[str, Any]
    verification: dict[str, Any]
    source_units: dict[str, str]

    @property
    def source_url(self) -> str:
        return str(self.primary_reference.get("url", "")).strip()

    @property
    def doi(self) -> str:
        return str(self.primary_reference.get("doi", "")).strip()

    @property
    def is_verified(self) -> bool:
        return (
            str(self.verification.get("status", "")).lower() == "verified"
            and bool(self.verification.get("model_definition_checked"))
            and bool(self.verification.get("compatibility_checked"))
            and bool(self.verification.get("units_checked"))
        )

    @property
    def is_starter_template(self) -> bool:
        return (
            str(self.verification.get("parameter_status", "")).lower()
            == "starter_template"
        )

    @property
    def verification_date(self) -> str:
        return str(self.verification.get("checked_on", "")).strip()

    @property
    def searchable_text(self) -> str:
        reference = self.primary_reference
        evidence = self.parameter_evidence
        parts = (
            self.id,
            self.family,
            self.material,
            self.model,
            self.preset_name,
            *self.behavior,
            *self.compatibility,
            *self.applicability,
            *self.limitations,
            reference.get("title", ""),
            reference.get("authors", ""),
            reference.get("doi", ""),
            reference.get("url", ""),
            evidence.get("location", ""),
            evidence.get("note", ""),
        )
        return " ".join(str(value) for value in parts).lower()

    @property
    def citation_text(self) -> str:
        reference = self.primary_reference
        title = str(reference.get("title", "")).strip()
        authors = str(reference.get("authors", "")).strip()
        doi = str(reference.get("doi", "")).strip()
        url = self.source_url
        parts = [value for value in (authors, title) if value]
        citation = ". ".join(parts)
        if doi:
            citation += (". " if citation else "") + "DOI: " + doi
        elif url:
            citation += (". " if citation else "") + url
        return citation

    def source_metadata(self) -> dict[str, Any]:
        return {
            "library": "SARE verified nD material library",
            "record_id": self.id,
            "status": "verified" if self.is_verified else "unverified",
            "family": self.family,
            "material": self.material,
            "model": self.model,
            "preset_name": self.preset_name,
            "behavior": list(self.behavior),
            "compatibility": list(self.compatibility),
            "applicability": list(self.applicability),
            "limitations": list(self.limitations),
            "verified_parameters": list(self.verified_parameters),
            "primary_reference": deepcopy(self.primary_reference),
            "parameter_evidence": deepcopy(self.parameter_evidence),
            "verification": deepcopy(self.verification),
            "source_units": deepcopy(self.source_units),
        }


def _resource_text() -> str:
    root = resources.files("openseespy_studio")
    resource = root
    for part in _LIBRARY_RESOURCE:
        resource = resource.joinpath(part)
    return resource.read_text(encoding="utf-8")


def _validate_reference(
    reference: dict[str, Any],
    record_id: str,
) -> None:
    if not str(reference.get("title", "")).strip():
        raise ValueError(
            f"Verified nD material record {record_id!r} has no source title."
        )
    if not str(reference.get("url", "")).strip():
        raise ValueError(
            f"Verified nD material record {record_id!r} has no source URL."
        )
    source_type = str(reference.get("type", "")).strip().lower()
    if source_type == "journal" and not str(reference.get("doi", "")).strip():
        raise ValueError(
            f"Verified nD material record {record_id!r} has a journal "
            "source without a DOI."
        )


def _validate_parameter_values(
    model: str,
    parameters: dict[str, float],
    record_id: str,
) -> None:
    for key, value in parameters.items():
        if not math.isfinite(value):
            raise ValueError(
                f"Official nD material record {record_id!r} has "
                f"non-finite parameter {key!r}."
            )

    positive = {
        "ElasticIsotropic": ("E",),
        "ElasticOrthotropic": (
            "Ex", "Ey", "Ez", "Gxy", "Gyz", "Gzx",
        ),
        "J2Plasticity": ("K", "G"),
    }.get(model, ())
    for key in positive:
        if parameters[key] <= 0.0:
            raise ValueError(
                f"Official nD material record {record_id!r} requires "
                f"{key} > 0."
            )

    if "rho" in parameters and parameters["rho"] < 0.0:
        raise ValueError(
            f"Official nD material record {record_id!r} requires rho >= 0."
        )

    if model == "ElasticIsotropic":
        nu = parameters["nu"]
        if not (-1.0 < nu < 0.5):
            raise ValueError(
                f"Official nD material record {record_id!r} requires "
                "-1 < nu < 0.5."
            )

    if model == "J2Plasticity":
        for key in ("sig0", "sigInf", "delta", "H"):
            if parameters[key] < 0.0:
                raise ValueError(
                    f"Official nD material record {record_id!r} requires "
                    f"{key} >= 0."
                )


def _record_from_dict(raw: dict[str, Any]) -> NDMaterialLibraryRecord:
    record_id = str(raw.get("id", "")).strip()
    if not record_id:
        raise ValueError("nD material library record has no id.")

    family = str(raw.get("family", "")).strip()
    material = str(raw.get("material", "")).strip()
    model = str(raw.get("model", "")).strip()
    preset_name = str(raw.get("preset_name", "")).strip()
    for label, value in (
        ("family", family),
        ("material", material),
        ("preset_name", preset_name),
    ):
        if not value:
            raise ValueError(
                f"nD material library record {record_id!r} has no {label}."
            )

    expected = ND_MATERIAL_PARAMETER_ORDER.get(model)
    if expected is None:
        raise ValueError(
            f"nD material library record {record_id!r} uses unsupported "
            f"model {model!r}."
        )

    reference = dict(raw.get("primary_reference", {}))
    verification = dict(raw.get("verification", {}))
    _validate_reference(reference, record_id)

    if str(verification.get("status", "")).lower() != "verified":
        raise ValueError(
            f"Official nD material record {record_id!r} is not verified."
        )
    for flag in (
        "model_definition_checked",
        "compatibility_checked",
        "units_checked",
    ):
        if not bool(verification.get(flag)):
            raise ValueError(
                f"Official nD material record {record_id!r} is missing "
                f"verification flag {flag!r}."
            )
    checked_on = str(verification.get("checked_on", "")).strip()
    if not checked_on:
        raise ValueError(
            f"Official nD material record {record_id!r} has no "
            "verification checked_on date."
        )
    try:
        date.fromisoformat(checked_on)
    except ValueError as exc:
        raise ValueError(
            f"Official nD material record {record_id!r} has invalid "
            "verification checked_on date."
        ) from exc

    parameters = {
        str(key): float(value)
        for key, value in dict(raw.get("parameters_si", {})).items()
    }
    _validate_parameter_values(model, parameters, record_id)

    expected_set = set(expected)
    actual_set = set(parameters)
    if actual_set != expected_set:
        missing = sorted(expected_set - actual_set)
        extra = sorted(actual_set - expected_set)
        details: list[str] = []
        if missing:
            details.append("missing " + ", ".join(missing))
        if extra:
            details.append("unexpected " + ", ".join(extra))
        raise ValueError(
            f"Official nD material record {record_id!r} does not exactly "
            f"match {model} parameters: " + "; ".join(details)
        )

    verified_parameters = tuple(
        str(value)
        for value in raw.get("verified_parameters", [])
    )
    if set(verified_parameters) != expected_set:
        raise ValueError(
            f"Official nD material record {record_id!r} must list every "
            "active model parameter as verified."
        )

    behavior = tuple(
        str(value).strip()
        for value in raw.get("behavior", [])
        if str(value).strip()
    )
    if not behavior:
        raise ValueError(
            f"Official nD material record {record_id!r} has no "
            "behavior metadata."
        )

    compatibility = tuple(
        str(value).strip()
        for value in raw.get("compatibility", [])
        if str(value).strip()
    )
    if not compatibility:
        raise ValueError(
            f"Official nD material record {record_id!r} has no "
            "compatibility metadata."
        )

    applicability = tuple(
        str(value).strip()
        for value in raw.get("applicability", [])
        if str(value).strip()
    )
    if not applicability:
        raise ValueError(
            f"Official nD material record {record_id!r} has no "
            "applicability metadata."
        )

    limitations = tuple(
        str(value).strip()
        for value in raw.get("limitations", [])
        if str(value).strip()
    )
    if not limitations:
        raise ValueError(
            f"Official nD material record {record_id!r} has no "
            "limitations metadata."
        )

    source_units = {
        str(key): str(value).strip()
        for key, value in dict(raw.get("source_units", {})).items()
    }
    if set(source_units) != expected_set:
        raise ValueError(
            f"Official nD material record {record_id!r} source_units "
            "must exactly match active model parameters."
        )
    if any(not value for value in source_units.values()):
        raise ValueError(
            f"Official nD material record {record_id!r} contains an "
            "empty source unit."
        )

    return NDMaterialLibraryRecord(
        id=record_id,
        family=family,
        material=material,
        model=model,
        preset_name=preset_name,
        parameters_si=parameters,
        verified_parameters=verified_parameters,
        behavior=behavior,
        compatibility=compatibility,
        applicability=applicability,
        limitations=limitations,
        primary_reference=reference,
        parameter_evidence=dict(raw.get("parameter_evidence", {})),
        verification=verification,
        source_units=source_units,
    )


def load_verified_nd_material_library(
) -> tuple[NDMaterialLibraryRecord, ...]:
    payload = json.loads(_resource_text())
    if int(payload.get("schema_version", 0)) != 1:
        raise ValueError(
            "Unsupported SARE nD-material-library schema version."
        )
    records = tuple(
        _record_from_dict(dict(raw))
        for raw in payload.get("records", [])
    )
    ids = [record.id for record in records]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate nD-material-library record id.")
    return records


def nd_material_library_facets(
    records: tuple[NDMaterialLibraryRecord, ...] | None = None,
) -> dict[str, tuple[str, ...]]:
    source = (
        load_verified_nd_material_library()
        if records is None
        else records
    )
    return {
        "family": tuple(sorted({record.family for record in source})),
        "model": tuple(sorted({record.model for record in source})),
        "behavior": tuple(sorted({
            value
            for record in source
            for value in record.behavior
        })),
        "compatibility": tuple(sorted({
            value
            for record in source
            for value in record.compatibility
        })),
    }


def filter_verified_nd_material_library(
    records: tuple[NDMaterialLibraryRecord, ...] | None = None,
    *,
    query: str = "",
    family: str = "",
    model: str = "",
    behavior: str = "",
    compatibility: str = "",
) -> tuple[NDMaterialLibraryRecord, ...]:
    source = (
        load_verified_nd_material_library()
        if records is None
        else records
    )
    query_tokens = tuple(
        token
        for token in str(query).strip().lower().split()
        if token
    )
    family_text = str(family).strip()
    model_text = str(model).strip()
    behavior_text = str(behavior).strip()
    compatibility_text = str(compatibility).strip()

    return tuple(
        record
        for record in source
        if (
            not query_tokens
            or all(
                token in record.searchable_text
                for token in query_tokens
            )
        )
        and (not family_text or record.family == family_text)
        and (not model_text or record.model == model_text)
        and (
            not behavior_text
            or behavior_text in record.behavior
        )
        and (
            not compatibility_text
            or compatibility_text in record.compatibility
        )
    )


def nd_material_from_library_record(
    record: NDMaterialLibraryRecord,
    *,
    tag: int,
    name: str | None = None,
) -> NDMaterialData:
    if not record.is_verified:
        raise ValueError(
            "Only verified nD material library records can be inserted."
        )
    return NDMaterialData(
        tag=tag,
        name=name or record.preset_name or f"{record.material} · {record.model}",
        material_type=record.model,
        parameters=dict(record.parameters_si),
        source=record.source_metadata(),
    )
