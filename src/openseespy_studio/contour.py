from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Iterable


@dataclass(frozen=True)
class ContourDisplayOptions:
    range_mode: str = "auto"
    minimum: float | None = None
    maximum: float | None = None
    symmetric: bool = True
    bands: int = 11
    palette: str = "auto"
    show_minimum: bool = True
    show_maximum: bool = True
    deformed_geometry: bool = False
    deformation_scale: float = 1.0

    def cache_key(self) -> tuple[object, ...]:
        return (
            self.range_mode,
            self.minimum,
            self.maximum,
            self.symmetric,
            self.bands,
            self.palette,
            self.show_minimum,
            self.show_maximum,
            self.deformed_geometry,
            self.deformation_scale,
        )


def contour_display_options(
    settings: dict[str, Any] | None,
    *,
    magnitude: bool = False,
) -> ContourDisplayOptions:
    raw = dict(settings or {})
    range_mode = str(raw.get("contour_range_mode", "auto")).strip().lower()
    if range_mode not in {"auto", "user"}:
        range_mode = "auto"

    def optional_float(name: str) -> float | None:
        value = raw.get(name)
        if value is None:
            return None
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError):
            return None
        return number if math.isfinite(number) else None

    try:
        bands = int(raw.get("contour_bands", 11))
    except (TypeError, ValueError, OverflowError):
        bands = 11
    bands = max(3, min(64, bands))

    palette = str(raw.get("contour_palette", "auto")).strip().lower()
    if palette not in {"auto", "sequential", "diverging"}:
        palette = "auto"

    try:
        deformation_scale = float(raw.get("contour_deformation_scale", 1.0))
    except (TypeError, ValueError, OverflowError):
        deformation_scale = 1.0
    if not math.isfinite(deformation_scale) or deformation_scale < 0.0:
        deformation_scale = 1.0

    return ContourDisplayOptions(
        range_mode=range_mode,
        minimum=optional_float("contour_min"),
        maximum=optional_float("contour_max"),
        symmetric=(
            False if magnitude else bool(raw.get("contour_symmetric", True))
        ),
        bands=bands,
        palette=palette,
        show_minimum=bool(raw.get("contour_show_min", True)),
        show_maximum=bool(raw.get("contour_show_max", True)),
        deformed_geometry=bool(raw.get("contour_deformed_geometry", False)),
        deformation_scale=deformation_scale,
    )


def resolve_contour_range(
    values: Iterable[float],
    options: ContourDisplayOptions,
    *,
    magnitude: bool = False,
) -> tuple[float, float] | None:
    finite: list[float] = []
    for value in values:
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError):
            continue
        if math.isfinite(number):
            finite.append(number)
    if not finite:
        return None

    if (
        options.range_mode == "user"
        and options.minimum is not None
        and options.maximum is not None
    ):
        low = float(options.minimum)
        high = float(options.maximum)
        if low > high:
            low, high = high, low
    else:
        low = min(finite)
        high = max(finite)

    if options.symmetric and not magnitude:
        limit = max(abs(low), abs(high))
        if limit <= 1.0e-15:
            limit = max(max(abs(value) for value in finite), 1.0) * 0.05
        return -limit, limit

    if abs(high - low) <= 1.0e-15:
        pad = max(abs(high), 1.0) * 0.05
        low -= pad
        high += pad
    return low, high


def contour_colormap(
    options: ContourDisplayOptions,
    *,
    magnitude: bool = False,
) -> str:
    if options.palette == "diverging":
        return "coolwarm"
    if options.palette == "sequential":
        return "viridis"
    return "viridis" if magnitude else "coolwarm"
