from __future__ import annotations

from dataclasses import dataclass
import json
import math

from .generator import material_to_openseespy, ordered_material_tags
from .project import MaterialData
from .units import UnitSystem


MATERIAL_TEST_PROTOCOLS: tuple[tuple[str, str], ...] = (
    ("Symmetric cyclic", "symmetric_cyclic"),
    ("Compression cyclic", "compression_cyclic"),
    ("Monotonic positive", "monotonic_positive"),
    ("Monotonic negative", "monotonic_negative"),
)


@dataclass(slots=True)
class MaterialTestSpec:
    protocol: str = "symmetric_cyclic"
    amplitude: float = 0.02
    levels: int = 4
    cycles_per_level: int = 2
    steps_per_segment: int = 20

    def __post_init__(self) -> None:
        self.protocol = str(self.protocol)
        valid = {value for _, value in MATERIAL_TEST_PROTOCOLS}
        if self.protocol not in valid:
            raise ValueError(f"Unsupported material test protocol: {self.protocol}")
        self.amplitude = abs(float(self.amplitude))
        self.levels = int(self.levels)
        self.cycles_per_level = int(self.cycles_per_level)
        self.steps_per_segment = int(self.steps_per_segment)
        if self.amplitude <= 0.0:
            raise ValueError("Material test amplitude must be positive.")
        if self.levels < 1:
            raise ValueError("Material test levels must be at least 1.")
        if self.cycles_per_level < 1:
            raise ValueError("Cycles per level must be at least 1.")
        if self.steps_per_segment < 1:
            raise ValueError("Steps per segment must be at least 1.")


def _positive_extent(material: MaterialData) -> float:
    p = material.parameters
    if material.material_type == "Hysteretic":
        return max(abs(p["e1p"]), abs(p["e2p"]), abs(p["e3p"]))
    if material.material_type == "Pinching4":
        return max(abs(p[f"ePd{index}"]) for index in range(1, 5))
    return 0.0


def _negative_extent(material: MaterialData) -> float:
    p = material.parameters
    if material.material_type == "Hysteretic":
        return max(abs(p["e1n"]), abs(p["e2n"]), abs(p["e3n"]))
    if material.material_type == "Pinching4":
        return max(abs(p[f"eNd{index}"]) for index in range(1, 5))
    return 0.0


def default_material_test_spec(
    material: MaterialData,
    units: dict[str, str] | None = None,
    materials: dict[int, MaterialData] | None = None,
) -> MaterialTestSpec:
    """Choose a useful research-oriented protocol from the material family."""
    p = material.parameters
    unit_system = UnitSystem.from_mapping(units)
    material_type = material.material_type

    if material_type in {"MinMax", "Fatigue"} and materials:
        base = materials.get(int(material.base_material_tag or 0))
        if base is not None:
            return default_material_test_spec(base, units, materials)

    if material_type in {"Parallel", "Series"} and materials:
        for tag in material.material_tags:
            base = materials.get(int(tag))
            if base is not None:
                return default_material_test_spec(base, units, materials)

    if material_type in {
        "Concrete01",
        "Concrete02",
        "Concrete04",
        "FRPConfinedConcrete",
        "FRPConfinedConcrete02",
    }:
        strains: list[float] = []
        for key in ("epsc0", "epsU", "epsc", "epscu", "ec0", "ecu"):
            if key in p:
                strains.append(abs(float(p[key])))
        amplitude = max(strains or [0.006]) * 1.05
        return MaterialTestSpec(
            protocol="compression_cyclic",
            amplitude=max(amplitude, 0.003),
            levels=4,
            cycles_per_level=1,
            steps_per_segment=24,
        )

    if material_type == "ReinforcingSteel":
        amplitude = min(max(abs(float(p["eps_sh"])) * 2.0, 0.02), 0.06)
        return MaterialTestSpec(
            protocol="symmetric_cyclic",
            amplitude=amplitude,
            levels=4,
            cycles_per_level=2,
            steps_per_segment=20,
        )

    if material_type in {"Steel01", "Steel02", "Hardening"}:
        return MaterialTestSpec(
            protocol="symmetric_cyclic",
            amplitude=0.03,
            levels=4,
            cycles_per_level=2,
            steps_per_segment=20,
        )

    if material_type == "ElasticPP":
        amplitude = max(
            6.0 * max(
                abs(float(p["epsyP"])),
                abs(float(p["epsyN"])),
            ),
            0.01,
        )
        return MaterialTestSpec(
            protocol="symmetric_cyclic",
            amplitude=min(amplitude, 0.06),
            levels=4,
            cycles_per_level=2,
            steps_per_segment=20,
        )

    if material_type == "ElasticBilin":
        amplitude = max(
            6.0 * max(
                abs(float(p["epsP2"])),
                abs(float(p["epsN2"])),
            ),
            0.01,
        )
        return MaterialTestSpec(
            protocol="symmetric_cyclic",
            amplitude=min(amplitude, 0.06),
            levels=4,
            cycles_per_level=2,
            steps_per_segment=20,
        )

    if material_type == "HystereticSmooth":
        denominator = abs(float(p["ka"]) - float(p["kb"]))
        yield_scale = (
            abs(float(p["fbar"])) / denominator
            if denominator > 1.0e-15
            else 0.0
        )
        return MaterialTestSpec(
            protocol="symmetric_cyclic",
            amplitude=max(3.0 * yield_scale, 0.01),
            levels=4,
            cycles_per_level=2,
            steps_per_segment=18,
        )

    if material_type in {"Hysteretic", "Pinching4"}:
        amplitude = max(
            _positive_extent(material),
            _negative_extent(material),
            0.01,
        )
        return MaterialTestSpec(
            protocol="symmetric_cyclic",
            amplitude=amplitude,
            levels=4,
            cycles_per_level=2,
            steps_per_segment=18,
        )

    if material_type == "Bond_SP01":
        amplitude = unit_system.length_from_m(
            max(abs(float(p["Sy"])), abs(float(p["Su"])), 1.0e-6)
        )
        return MaterialTestSpec(
            protocol="symmetric_cyclic",
            amplitude=amplitude,
            levels=4,
            cycles_per_level=2,
            steps_per_segment=18,
        )

    if material_type == "ElasticPPGap":
        scale = max(abs(float(p["gap"])), 1.0)
        return MaterialTestSpec(
            protocol="symmetric_cyclic",
            amplitude=2.0 * scale,
            levels=4,
            cycles_per_level=1,
            steps_per_segment=18,
        )

    return MaterialTestSpec(
        protocol="monotonic_positive",
        amplitude=0.01,
        levels=1,
        cycles_per_level=1,
        steps_per_segment=50,
    )


def material_test_axis_labels(
    material: MaterialData,
    units: dict[str, str] | None = None,
) -> tuple[str, str]:
    """Return semantic axis labels for the material-point response."""
    unit_system = UnitSystem.from_mapping(units)
    material_type = material.material_type
    stress_label = (
        unit_system.engineering_stress_label
        if unit_system.is_us_customary
        else unit_system.stress_label
    )
    if material_type in {
        "Elastic",
        "Steel01",
        "Steel02",
        "Hardening",
        "ElasticPP",
        "ElasticBilin",
        "ReinforcingSteel",
        "Concrete01",
        "Concrete02",
        "Concrete04",
        "FRPConfinedConcrete02",
    }:
        return "Strain", f"Stress [{stress_label}]"
    if material_type == "Bond_SP01":
        return (
            f"Slip [{unit_system.length}]",
            f"Bond response [{stress_label}]",
        )
    return "Material deformation", "Material response"


def material_test_targets(spec: MaterialTestSpec) -> list[float]:
    """Return protocol turning points, including the initial zero."""
    amplitude = float(spec.amplitude)
    targets = [0.0]

    if spec.protocol == "monotonic_positive":
        return [0.0, amplitude]
    if spec.protocol == "monotonic_negative":
        return [0.0, -amplitude]

    for level in range(1, spec.levels + 1):
        value = amplitude * level / spec.levels
        for _ in range(spec.cycles_per_level):
            if spec.protocol == "symmetric_cyclic":
                targets.extend((value, -value))
            else:
                targets.extend((-value, 0.0))
    if not math.isclose(targets[-1], 0.0, abs_tol=1.0e-15):
        targets.append(0.0)
    return targets


def material_test_history(spec: MaterialTestSpec) -> list[float]:
    """Expand turning points into small constitutive trial increments."""
    targets = material_test_targets(spec)
    history = [float(targets[0])]
    for target in targets[1:]:
        start = history[-1]
        for step in range(1, spec.steps_per_segment + 1):
            ratio = step / spec.steps_per_segment
            history.append(start + (float(target) - start) * ratio)
    return history


def build_material_test_script(
    material: MaterialData,
    units: dict[str, str] | None,
    spec: MaterialTestSpec,
    materials: dict[int, MaterialData] | None = None,
) -> str:
    """Build an isolated OpenSees uniaxial material-point test script.

    OpenSees' testUniaxialMaterial/setStrain/getStress API exercises the same
    UniaxialMaterial constitutive object used by zeroLength and fiber models,
    without introducing a structural equilibrium problem into a material test.
    """
    material_map = dict(materials or {})
    material_map[material.tag] = material

    if material.material_type in {"MinMax", "Fatigue", "Parallel", "Series"}:
        required: set[int] = set()

        def collect(tag: int) -> None:
            if tag in required:
                return
            item = material_map.get(tag)
            if item is None:
                raise ValueError(
                    f"Material test needs referenced material tag {tag}."
                )
            required.add(tag)
            if item.material_type in {"MinMax", "Fatigue"}:
                if item.base_material_tag is not None:
                    collect(item.base_material_tag)
            elif item.material_type in {"Parallel", "Series"}:
                for dependency in item.material_tags:
                    collect(dependency)

        collect(material.tag)
        selected = {tag: material_map[tag] for tag in required}
        commands = [
            material_to_openseespy(selected[tag], units)
            for tag in ordered_material_tags(selected)
        ]
    else:
        commands = [material_to_openseespy(material, units)]

    history = material_test_history(spec)
    x_label, y_label = material_test_axis_labels(material, units)
    command_text = "\n".join(commands)

    return (
        "import openseespy.opensees as ops\n"
        "ops.wipe()\n"
        f"{command_text}\n"
        f"ops.testUniaxialMaterial({material.tag})\n"
        f"_studio_history = {json.dumps(history)}\n"
        "_studio_deformation = []\n"
        "_studio_response = []\n"
        "_studio_tangent = []\n"
        "for _studio_value in _studio_history:\n"
        "    ops.setStrain(float(_studio_value))\n"
        "    _studio_deformation.append(float(ops.getStrain()))\n"
        "    _studio_response.append(float(ops.getStress()))\n"
        "    _studio_tangent.append(float(ops.getTangent()))\n"
        "_studio_results = {\n"
        "    'material_test': {\n"
        f"        'material_tag': {material.tag},\n"
        f"        'material_type': {material.material_type!r},\n"
        f"        'protocol': {spec.protocol!r},\n"
        f"        'x_label': {x_label!r},\n"
        f"        'y_label': {y_label!r},\n"
        "        'deformation': _studio_deformation,\n"
        "        'response': _studio_response,\n"
        "        'tangent': _studio_tangent,\n"
        "    }\n"
        "}\n"
        "ops.wipe()\n"
    )
