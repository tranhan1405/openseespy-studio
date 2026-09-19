from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
import json
import math
import re


@dataclass(frozen=True, slots=True)
class GroundMotionRecordPreset:
    key: str
    label: str
    event: str
    year: int | None
    station: str
    source: str
    notes: str = ""
    bundled_resource: str = ""


GROUND_MOTION_LIBRARY: tuple[GroundMotionRecordPreset, ...] = (
    GroundMotionRecordPreset(
        key="custom",
        label="Custom / Local Record",
        event="",
        year=None,
        station="",
        source="Local file",
        notes="Use any TXT, CSV, DAT or PEER AT2 acceleration record.",
    ),
    GroundMotionRecordPreset(
        key="el-centro-1940",
        label="El Centro 1940 · El Centro Array #9",
        event="Imperial Valley",
        year=1940,
        station="El Centro Array #9",
        source="PEER NGA-West2 / strong-motion archives",
        notes="Classic benchmark record. Built-in NS component is ready to use.",
        bundled_resource="resources/ground_motions/elCentro_1940_NS.at2",
    ),
    GroundMotionRecordPreset(
        key="loma-prieta-1989",
        label="Loma Prieta 1989 · Corralitos",
        event="Loma Prieta",
        year=1989,
        station="Corralitos",
        source="PEER NGA-West2 / strong-motion archives",
        notes="Common benchmark event/station combination.",
    ),
    GroundMotionRecordPreset(
        key="northridge-1994-rinaldi",
        label="Northridge 1994 · Rinaldi Receiving Station",
        event="Northridge-01",
        year=1994,
        station="Rinaldi Receiving Station",
        source="PEER NGA-West2 / USGS strong-motion archives",
        notes="Near-fault benchmark. Built-in 228 component is ready to use.",
        bundled_resource=(
            "resources/ground_motions/"
            "northridge_1994_rinaldi_228.json"
        ),
    ),
    GroundMotionRecordPreset(
        key="kobe-1995-kjma",
        label="Kobe 1995 · KJMA",
        event="Kobe, Japan",
        year=1995,
        station="KJMA / JMA Kobe",
        source="PEER NGA-West2 / Japanese strong-motion archives",
        notes="Widely used Kobe benchmark record.",
    ),
    GroundMotionRecordPreset(
        key="kocaeli-1999-duzce",
        label="Kocaeli 1999 · Duzce",
        event="Kocaeli, Turkey",
        year=1999,
        station="Duzce",
        source="PEER NGA-West2",
        notes="Common near-fault benchmark record.",
    ),
    GroundMotionRecordPreset(
        key="chi-chi-1999-tcu052",
        label="Chi-Chi 1999 · TCU052",
        event="Chi-Chi, Taiwan",
        year=1999,
        station="TCU052",
        source="PEER NGA-West2 / Taiwan strong-motion archives",
        notes="Common Chi-Chi benchmark station.",
    ),
)


def record_preset(key: str) -> GroundMotionRecordPreset:
    for item in GROUND_MOTION_LIBRARY:
        if item.key == str(key):
            return item
    raise KeyError(key)


@dataclass(frozen=True, slots=True)
class GroundMotionParseResult:
    values: list[float]
    dt: float | None = None
    input_unit: str | None = None
    npts: int | None = None
    format: str = "text"


_FLOAT_RE = re.compile(
    r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][-+]?\d+)?"
)


def _floats(text: str) -> list[float]:
    return [float(match.group(0)) for match in _FLOAT_RE.finditer(text)]


def parse_simcenter_json_text(text: str) -> GroundMotionParseResult:
    """Parse a SimCenter-style JSON ground-motion resource."""
    try:
        payload = json.loads(str(text))
    except json.JSONDecodeError as exc:
        raise ValueError("Ground-motion JSON is invalid.") from exc
    if not isinstance(payload, dict):
        raise ValueError("Ground-motion JSON must contain an object.")

    values = payload.get("accel_data")
    if not isinstance(values, list) or not values:
        raise ValueError("Ground-motion JSON contains no accel_data values.")
    try:
        accelerations = [float(value) for value in values]
    except (TypeError, ValueError) as exc:
        raise ValueError("Ground-motion JSON acceleration values are invalid.") from exc

    dt = payload.get("dT")
    try:
        dt_value = float(dt)
    except (TypeError, ValueError) as exc:
        raise ValueError("Ground-motion JSON dT is missing or invalid.") from exc
    if dt_value <= 0.0:
        raise ValueError("Ground-motion JSON dT must be positive.")

    info = str(payload.get("info", "")).upper()
    input_unit = "g" if "UNITS OF G" in info else None
    return GroundMotionParseResult(
        values=accelerations,
        dt=dt_value,
        input_unit=input_unit,
        npts=len(accelerations),
        format="SimCenter JSON",
    )


def parse_peer_at2_text(text: str) -> GroundMotionParseResult:
    """Parse a PEER-style AT2 file.

    The parser searches for the NPTS/DT header and then consumes all numeric
    acceleration values after that line, independent of how many values are
    written per row.
    """
    lines = str(text).splitlines()
    header_index: int | None = None
    npts: int | None = None
    dt: float | None = None

    for index, line in enumerate(lines):
        upper = line.upper()
        if "NPTS" not in upper or "DT" not in upper:
            continue
        header_index = index

        npts_match = re.search(
            r"NPTS\s*=\s*(\d+)",
            line,
            re.IGNORECASE,
        )
        dt_match = re.search(
            r"DT\s*=\s*(" + _FLOAT_RE.pattern + r")",
            line,
            re.IGNORECASE,
        )
        if npts_match:
            npts = int(npts_match.group(1))
        if dt_match:
            dt = float(dt_match.group(1))
        break

    if header_index is None:
        raise ValueError("PEER AT2 header with NPTS and DT was not found.")
    if npts is None or npts < 1:
        raise ValueError("PEER AT2 NPTS is missing or invalid.")
    if dt is None or dt <= 0.0:
        raise ValueError("PEER AT2 DT is missing or invalid.")

    values: list[float] = []
    for line in lines[header_index + 1 :]:
        values.extend(_floats(line))

    if len(values) < npts:
        raise ValueError(
            f"PEER AT2 declares {npts} points but only "
            f"{len(values)} acceleration values were found."
        )
    values = values[:npts]

    upper_text = str(text).upper()
    input_unit = (
        "g"
        if (
            "UNITS OF G" in upper_text
            or "UNITS ARE (G)" in upper_text
            or "UNITS ARE G" in upper_text
        )
        else None
    )
    return GroundMotionParseResult(
        values=values,
        dt=dt,
        input_unit=input_unit,
        npts=npts,
        format="PEER AT2",
    )


def parse_ground_motion_record_text(
    text: str,
    *,
    column: int = 1,
    filename: str = "",
) -> GroundMotionParseResult:
    """Auto-detect PEER AT2, otherwise parse one numeric text/CSV column."""
    upper = str(text).upper()
    suffix = str(filename).lower().rsplit(".", 1)[-1] if "." in filename else ""
    if suffix == "json" or (
        str(text).lstrip().startswith("{")
        and '"accel_data"' in str(text)
    ):
        return parse_simcenter_json_text(text)
    if suffix == "at2" or ("NPTS" in upper and "DT" in upper):
        return parse_peer_at2_text(text)

    column = int(column)
    if column < 1:
        raise ValueError("Ground-motion column is 1-based and must be positive.")

    values: list[float] = []
    for line_number, raw_line in enumerate(str(text).splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith(("#", "//", "%")):
            continue
        tokens = line.replace(",", " ").replace(";", " ").split()
        numeric: list[float] = []
        for token in tokens:
            try:
                numeric.append(float(token))
            except ValueError:
                continue
        if not numeric:
            continue
        if column > len(numeric):
            raise ValueError(
                f"Ground-motion line {line_number} has only "
                f"{len(numeric)} numeric column(s)."
            )
        values.append(numeric[column - 1])

    if not values:
        raise ValueError("Ground-motion file contains no numeric values.")
    return GroundMotionParseResult(
        values=values,
        format="text/CSV",
    )


def load_bundled_ground_motion_record(
    key: str,
) -> GroundMotionParseResult:
    """Load a packaged benchmark record by library key."""
    preset = record_preset(key)
    if not preset.bundled_resource:
        raise ValueError(
            f"{preset.label} is a reference preset and has no bundled record."
        )
    package_root = resources.files("openseespy_studio")
    target = package_root.joinpath(*preset.bundled_resource.split("/"))
    try:
        text = target.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError) as exc:
        raise ValueError(
            f"Bundled ground-motion resource is unavailable: "
            f"{preset.bundled_resource}"
        ) from exc
    return parse_ground_motion_record_text(
        text,
        filename=preset.bundled_resource,
    )


def pga_in_g(values: list[float], input_unit: str) -> float:
    if not values:
        return 0.0
    peak = max(abs(float(value)) for value in values)
    unit = str(input_unit)
    if unit == "g":
        return peak
    if unit == "m/s²":
        return peak / 9.80665
    if unit == "cm/s²":
        return peak / 980.665
    raise ValueError(f"Unsupported acceleration unit: {input_unit}")


def common_scale_factor_for_target_pga(
    component_values: list[list[float]],
    input_unit: str,
    target_pga_g: float,
) -> float:
    """Scale all components by one factor so the strongest reaches target PGA."""
    target = float(target_pga_g)
    if target <= 0.0:
        raise ValueError("Target PGA must be positive.")
    raw_peaks = [
        pga_in_g(values, input_unit)
        for values in component_values
        if values
    ]
    raw = max(raw_peaks, default=0.0)
    if raw <= 1.0e-15 or not math.isfinite(raw):
        raise ValueError("Ground-motion PGA is zero or invalid.")
    return target / raw


def scale_factor_for_target_pga(
    values: list[float],
    input_unit: str,
    target_pga_g: float,
) -> float:
    target = float(target_pga_g)
    if target <= 0.0:
        raise ValueError("Target PGA must be positive.")
    raw = pga_in_g(values, input_unit)
    if raw <= 1.0e-15 or not math.isfinite(raw):
        raise ValueError("Ground-motion PGA is zero or invalid.")
    return target / raw
