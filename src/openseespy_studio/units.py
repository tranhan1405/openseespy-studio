from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


DEFAULT_PROJECT_UNITS: dict[str, str] = {
    "length": "m",
    "force": "kN",
    "time": "s",
}

_LENGTH_TO_M = {
    "m": 1.0,
    "mm": 1.0e-3,
    "in": 0.0254,
}
_FORCE_TO_N = {
    "N": 1.0,
    "kN": 1.0e3,
    "kip": 4448.2216152605,
}
_TIME_TO_S = {
    "s": 1.0,
}


@dataclass(frozen=True)
class UnitSystem:
    """Consistent OpenSees model units plus SI engineering-input conversion.

    OpenSees itself is unitless. Studio stores material stress/modulus inputs
    in Pa and material density in kg/m^3, then converts those physical inputs
    to the selected consistent model units when generating OpenSeesPy.
    """

    length: str = "m"
    force: str = "kN"
    time: str = "s"

    def __post_init__(self) -> None:
        if self.length not in _LENGTH_TO_M:
            raise ValueError(
                f"Unsupported length unit {self.length!r}. "
                f"Supported: {', '.join(_LENGTH_TO_M)}."
            )
        if self.force not in _FORCE_TO_N:
            raise ValueError(
                f"Unsupported force unit {self.force!r}. "
                f"Supported: {', '.join(_FORCE_TO_N)}."
            )
        if self.time not in _TIME_TO_S:
            raise ValueError(
                f"Unsupported time unit {self.time!r}. "
                f"Supported: {', '.join(_TIME_TO_S)}."
            )

    @classmethod
    def from_mapping(
        cls,
        units: Mapping[str, str] | None = None,
    ) -> "UnitSystem":
        source = DEFAULT_PROJECT_UNITS if units is None else units
        return cls(
            length=str(source.get("length", "m")),
            force=str(source.get("force", "kN")),
            time=str(source.get("time", "s")),
        )

    @property
    def length_to_m(self) -> float:
        return _LENGTH_TO_M[self.length]

    @property
    def force_to_n(self) -> float:
        return _FORCE_TO_N[self.force]

    @property
    def time_to_s(self) -> float:
        return _TIME_TO_S[self.time]

    @property
    def mass_unit_kg(self) -> float:
        # F = M L / T^2
        return (
            self.force_to_n
            * self.time_to_s**2
            / self.length_to_m
        )

    @property
    def mass_label(self) -> str:
        value = self.mass_unit_kg
        if abs(value - 1.0) <= 1.0e-12:
            return "kg"
        if abs(value - 1000.0) <= 1.0e-9:
            return "t"
        return f"{value:g} kg"

    @property
    def stress_label(self) -> str:
        return f"{self.force}/{self.length}²"

    @property
    def is_us_customary(self) -> bool:
        return (
            self.length == "in"
            and self.force == "kip"
            and self.time == "s"
        )

    @property
    def engineering_stress_label(self) -> str:
        # Keep the existing research-friendly SI convention, but do not
        # force US-customary projects through MPa in the editor.
        return "ksi" if self.is_us_customary else "MPa"

    @property
    def engineering_density_label(self) -> str:
        return "lb/in³" if self.is_us_customary else "kg/m³"

    @property
    def line_load_label(self) -> str:
        return f"{self.force}/{self.length}"

    @property
    def acceleration_label(self) -> str:
        return f"{self.length}/{self.time}²"

    @property
    def mass_per_length_label(self) -> str:
        return f"{self.mass_label}/{self.length}"

    def length_from_m(self, value_m: float) -> float:
        """Convert SI metres to the active model length unit."""
        return float(value_m) / self.length_to_m

    def length_to_m_value(self, value: float) -> float:
        """Convert a value in the active model length unit to SI metres."""
        return float(value) * self.length_to_m

    def stress_from_pa(self, value_pa: float) -> float:
        """Convert Pa=N/m² to model force/length²."""
        return (
            float(value_pa)
            * self.length_to_m**2
            / self.force_to_n
        )

    def stress_to_pa(self, value: float) -> float:
        """Convert model force/length² to Pa=N/m²."""
        return (
            float(value)
            * self.force_to_n
            / self.length_to_m**2
        )

    def engineering_stress_from_pa(self, value_pa: float) -> float:
        """Display engineering stress in MPa or ksi for the active preset."""
        if self.is_us_customary:
            return self.stress_from_pa(value_pa)
        return float(value_pa) / 1.0e6

    def engineering_stress_to_pa(self, value: float) -> float:
        """Store engineering stress entered in MPa or ksi as Pa."""
        if self.is_us_customary:
            return self.stress_to_pa(value)
        return float(value) * 1.0e6

    def engineering_density_from_kg_per_m3(self, value: float) -> float:
        """Display density in kg/m³ (SI) or lb/in³ (US customary)."""
        if not self.is_us_customary:
            return float(value)
        # lbm/in^3; 1 lbm = 0.45359237 kg, 1 in = 0.0254 m.
        return (
            float(value)
            * (0.0254 ** 3)
            / 0.45359237
        )

    def engineering_density_to_kg_per_m3(self, value: float) -> float:
        """Store density entered in kg/m³ or lb/in³ as kg/m³."""
        if not self.is_us_customary:
            return float(value)
        return (
            float(value)
            * 0.45359237
            / (0.0254 ** 3)
        )

    def density_from_kg_per_m3(self, density: float) -> float:
        """Convert physical kg/m³ to model mass/model-length³."""
        return (
            float(density)
            * self.length_to_m**3
            / self.mass_unit_kg
        )

    def acceleration_from_m_per_s2(self, value: float) -> float:
        """Convert m/s² to model length/model-time²."""
        return (
            float(value)
            * self.time_to_s**2
            / self.length_to_m
        )

    def line_force_from_density_area_gravity(
        self,
        density_kg_per_m3: float,
        area_model_units: float,
        gravity_model_units: float,
    ) -> float:
        """Return force/length from rho[kg/m³], A[L²], g[L/T²]."""
        density_model = self.density_from_kg_per_m3(
            density_kg_per_m3
        )
        return (
            density_model
            * float(area_model_units)
            * float(gravity_model_units)
        )

    def as_mapping(self) -> dict[str, str]:
        return {
            "length": self.length,
            "force": self.force,
            "time": self.time,
        }


def normalize_project_units(
    units: Mapping[str, str] | None = None,
) -> dict[str, str]:
    return UnitSystem.from_mapping(units).as_mapping()
