from __future__ import annotations

import ast
import math
from dataclasses import dataclass, field
from typing import Any

from .model import StructuralModel
from .project import (
    MATERIAL_DEFAULTS,
    MATERIAL_PARAMETER_KINDS,
    MATERIAL_PARAMETER_ORDER,
    AnalysisSettingsData,
    ConnectionData,
    ConstraintData,
    ElementLoadData,
    FiberComponentData,
    FiberData,
    LoadPatternData,
    MaterialData,
    NodalLoadData,
    PrescribedDisplacementData,
    ProjectDatabase,
    RecorderData,
    SectionData,
    TimeSeriesData,
    TransformationData,
)
from .units import UnitSystem


@dataclass(slots=True)
class ImportIssue:
    severity: str
    line: int
    construct: str
    message: str


@dataclass(slots=True)
class OpenSeesImportResult:
    project: ProjectDatabase
    issues: list[ImportIssue] = field(default_factory=list)
    imported_counts: dict[str, int] = field(default_factory=dict)
    source_name: str = ""

    @property
    def error_count(self) -> int:
        return sum(item.severity == "ERROR" for item in self.issues)

    @property
    def warning_count(self) -> int:
        return sum(item.severity == "WARNING" for item in self.issues)

    @property
    def unsupported_count(self) -> int:
        return sum(item.severity == "UNSUPPORTED" for item in self.issues)

    @property
    def imported_total(self) -> int:
        return sum(self.imported_counts.values())


class _Unresolved(Exception):
    pass


class _SafeEvaluator:
    def __init__(self, env: dict[str, Any]):
        self.env = env

    def eval(self, node: ast.AST) -> Any:
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            if node.id in self.env:
                return self.env[node.id]
            raise _Unresolved(node.id)
        if isinstance(node, ast.List):
            return [self.eval(item) for item in node.elts]
        if isinstance(node, ast.Tuple):
            return tuple(self.eval(item) for item in node.elts)
        if isinstance(node, ast.Dict):
            return {
                self.eval(key): self.eval(value)
                for key, value in zip(node.keys, node.values)
                if key is not None
            }
        if isinstance(node, ast.UnaryOp):
            value = self.eval(node.operand)
            if isinstance(node.op, ast.UAdd):
                return +value
            if isinstance(node.op, ast.USub):
                return -value
            if isinstance(node.op, ast.Not):
                return not value
        if isinstance(node, ast.BinOp):
            left = self.eval(node.left)
            right = self.eval(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                return left / right
            if isinstance(node.op, ast.FloorDiv):
                return left // right
            if isinstance(node.op, ast.Mod):
                return left % right
            if isinstance(node.op, ast.Pow):
                return left ** right
        if isinstance(node, ast.Subscript):
            return self.eval(node.value)[self.eval(node.slice)]
        if isinstance(node, ast.Attribute):
            if (
                isinstance(node.value, ast.Name)
                and node.value.id in {"math", "np", "numpy"}
                and node.attr in {"pi", "e"}
            ):
                return getattr(math, node.attr)
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in {
                "int", "float", "abs", "round", "min", "max", "len"
            }:
                fn = {
                    "int": int,
                    "float": float,
                    "abs": abs,
                    "round": round,
                    "min": min,
                    "max": max,
                    "len": len,
                }[node.func.id]
                return fn(*(self.eval(arg) for arg in node.args))
        raise _Unresolved(type(node).__name__)


class _Importer:
    OPS_COMMANDS = {
        "model", "wipe", "wipeAnalysis", "node", "fix", "mass",
        "uniaxialMaterial", "section", "fiber", "patch", "layer",
        "geomTransf", "beamIntegration", "element",
        "equalDOF", "rigidLink", "rigidDiaphragm",
        "timeSeries", "pattern", "load",
        "constraints", "numberer", "system", "test", "algorithm",
        "integrator", "analysis", "analyze", "eigen",
        "rayleigh", "loadConst", "reactions", "recorder", "eleLoad", "sp",
    }

    def __init__(
        self,
        source: str,
        source_name: str,
        units: dict[str, str] | None,
    ):
        self.source = str(source)
        self.source_name = str(source_name)
        self.units = UnitSystem.from_mapping(units)
        stem = self.source_name.rsplit(".", 1)[0] or "Imported"
        self.project = ProjectDatabase(
            name=stem,
            model=StructuralModel(stem),
        )
        self.project.units = self.units.as_mapping()
        self.issues: list[ImportIssue] = []
        self.counts: dict[str, int] = {}
        self.env: dict[str, Any] = {"pi": math.pi}
        self.eval = _SafeEvaluator(self.env)
        self.ops_aliases = {"ops"}
        self.direct_ops = False
        self.current_pattern: int | None = None
        self.current_fiber_section: int | None = None
        self.integrations: dict[int, dict[str, Any]] = {}
        self.analysis_state: dict[str, Any] = {}
        self.analysis_metadata: dict[str, Any] = {}
        self._next_constraint = 1
        self._next_load = 1
        self._next_element_load = 1
        self._next_prescribed = 1
        self._next_recorder = 1
        self._studio_source = "Model generated by OpenSeesPy Studio" in self.source

    def issue(
        self,
        severity: str,
        node: ast.AST | None,
        construct: str,
        message: str,
    ) -> None:
        self.issues.append(
            ImportIssue(
                severity,
                int(getattr(node, "lineno", 0) or 0),
                construct,
                message,
            )
        )

    def count(self, name: str, amount: int = 1) -> None:
        self.counts[name] = self.counts.get(name, 0) + amount

    def stress_to_pa(self, value: float) -> float:
        return (
            float(value)
            * self.units.force_to_n
            / (self.units.length_to_m ** 2)
        )

    def length_to_m(self, value: float) -> float:
        return float(value) * self.units.length_to_m

    def call_args(self, call: ast.Call) -> list[Any]:
        result: list[Any] = []
        for arg in call.args:
            if isinstance(arg, ast.Starred):
                values = self.eval.eval(arg.value)
                if not isinstance(values, (tuple, list)):
                    raise _Unresolved("starred value")
                result.extend(values)
            else:
                result.append(self.eval.eval(arg))
        if call.keywords:
            raise _Unresolved("keyword arguments")
        return result

    def command_name(self, call: ast.Call) -> str | None:
        if (
            isinstance(call.func, ast.Attribute)
            and isinstance(call.func.value, ast.Name)
            and call.func.value.id in self.ops_aliases
            and call.func.attr in self.OPS_COMMANDS
        ):
            return call.func.attr
        if (
            self.direct_ops
            and isinstance(call.func, ast.Name)
            and call.func.id in self.OPS_COMMANDS
        ):
            return call.func.id
        return None

    @staticmethod
    def flag_value(values: list[Any], flag: str, default: Any = None) -> Any:
        try:
            index = values.index(flag)
        except ValueError:
            return default
        if index + 1 >= len(values):
            return default
        return values[index + 1]

    @staticmethod
    def flag_values(values: list[Any], flag: str) -> list[Any]:
        try:
            index = values.index(flag) + 1
        except ValueError:
            return []
        result: list[Any] = []
        while index < len(values):
            value = values[index]
            if isinstance(value, str) and value.startswith("-"):
                break
            result.append(value)
            index += 1
        return result

    def add_material(self, node: ast.Call, args: list[Any]) -> None:
        if len(args) < 2:
            raise ValueError("uniaxialMaterial needs type and tag")
        kind = str(args[0])
        tag = int(args[1])
        values = list(args[2:])
        if kind not in MATERIAL_PARAMETER_ORDER:
            self.issue(
                "UNSUPPORTED", node, f"uniaxialMaterial {kind}",
                f"Material {kind!r} is not supported by Studio yet.",
            )
            return
        if kind in {"MinMax", "Fatigue"}:
            if not values:
                raise ValueError(f"{kind} needs a base material tag")
            base_tag = int(values[0])
            params = dict(MATERIAL_DEFAULTS[kind])
            flags = (
                {"-min": "min", "-max": "max"}
                if kind == "MinMax"
                else {"-E0": "E0", "-m": "m", "-min": "min", "-max": "max"}
            )
            for flag, key in flags.items():
                value = self.flag_value(values, flag)
                if value is not None:
                    params[key] = float(value)
            self.project.add_material(
                MaterialData(
                    tag,
                    f"Imported {kind} {tag}",
                    kind,
                    parameters=params,
                    base_material_tag=base_tag,
                )
            )
            self.count("Materials")
            return

        if kind in {"Parallel", "Series"}:
            material_tags: list[int] = []
            for value in values:
                if isinstance(value, str):
                    break
                material_tags.append(int(value))
            factors: list[float] = []
            if kind == "Parallel" and "-factors" in values:
                factors = [
                    float(value)
                    for value in values[values.index("-factors") + 1:]
                    if not isinstance(value, str)
                ]
            self.project.add_material(
                MaterialData(
                    tag,
                    f"Imported {kind} {tag}",
                    kind,
                    material_tags=material_tags,
                    factors=factors,
                )
            )
            self.count("Materials")
            return

        params = dict(MATERIAL_DEFAULTS[kind])
        if kind == "FRPConfinedConcrete02":
            if len(values) < 3:
                raise ValueError("FRPConfinedConcrete02 has too few arguments")
            params["fc0"] = self.stress_to_pa(values[0])
            params["Ec"] = self.stress_to_pa(values[1])
            params["ec0"] = float(values[2])
            if "-JacketC" in values:
                p = values[values.index("-JacketC") + 1:]
                if len(p) >= 6:
                    params.update({
                        "mode": 0.0,
                        "tfrp": self.length_to_m(p[0]),
                        "Efrp": self.stress_to_pa(p[1]),
                        "erup": float(p[2]),
                        "R": self.length_to_m(p[3]),
                        "ft": self.stress_to_pa(p[4]),
                        "Ets": self.stress_to_pa(p[5]),
                    })
            elif "-Ultimate" in values:
                p = values[values.index("-Ultimate") + 1:]
                if len(p) >= 4:
                    params.update({
                        "mode": 1.0,
                        "fcu": self.stress_to_pa(p[0]),
                        "ecu": float(p[1]),
                        "ft": self.stress_to_pa(p[2]),
                        "Ets": self.stress_to_pa(p[3]),
                    })
        else:
            if kind == "ElasticPPGap" and values and isinstance(values[-1], str):
                params["damage"] = (
                    1.0 if str(values.pop()).lower() == "damage" else 0.0
                )
            if kind == "Pinching4" and values and isinstance(values[-1], str):
                params["dmgType"] = (
                    0.0 if str(values.pop()).lower() == "cycle" else 1.0
                )
            for key, value in zip(MATERIAL_PARAMETER_ORDER[kind], values):
                if isinstance(value, str):
                    continue
                number = float(value)
                dimension = MATERIAL_PARAMETER_KINDS.get(kind, {}).get(key)
                if dimension == "stress":
                    number = self.stress_to_pa(number)
                elif dimension == "length":
                    number = self.length_to_m(number)
                params[key] = number

        self.project.add_material(
            MaterialData(
                tag,
                f"Imported {kind} {tag}",
                kind,
                parameters=params,
            )
        )
        self.count("Materials")

    def add_section(self, node: ast.Call, args: list[Any]) -> None:
        if len(args) < 2:
            raise ValueError("section needs type and tag")
        kind = str(args[0])
        tag = int(args[1])
        if kind == "Elastic":
            if len(args) < 8:
                raise ValueError("Elastic section has too few arguments")
            self.project.add_section(
                SectionData(
                    tag,
                    f"Imported Elastic {tag}",
                    "Elastic",
                    parameters={
                        "E": self.stress_to_pa(args[2]),
                        "A": float(args[3]),
                        "Iz": float(args[4]),
                        "Iy": float(args[5]),
                        "G": self.stress_to_pa(args[6]),
                        "J": float(args[7]),
                    },
                )
            )
            self.current_fiber_section = None
            self.count("Sections")
            return
        if kind == "Fiber":
            gj = self.flag_value(args[2:], "-GJ", 1.0e6)
            self.project.add_section(
                SectionData(
                    tag,
                    f"Imported Fiber {tag}",
                    "Fiber",
                    parameters={"GJ": float(gj)},
                )
            )
            self.current_fiber_section = tag
            self.count("Sections")
            return
        self.issue(
            "UNSUPPORTED", node, f"section {kind}",
            f"Section {kind!r} is not supported by Studio yet.",
        )

    def fiber_section(self) -> SectionData:
        if self.current_fiber_section is None:
            raise ValueError("fiber/patch/layer appears outside a Fiber section")
        return self.project.sections[self.current_fiber_section]

    def add_fiber(self, args: list[Any]) -> None:
        if len(args) < 4:
            raise ValueError("fiber needs y, z, area and material tag")
        self.fiber_section().fibers.append(
            FiberData(
                float(args[0]),
                float(args[1]),
                float(args[2]),
                int(args[3]),
            )
        )
        self.count("Fibers")

    def add_patch(self, node: ast.Call, args: list[Any]) -> None:
        if not args:
            raise ValueError("patch needs a type")
        kind = str(args[0]).lower()
        section = self.fiber_section()
        if kind == "rect" and len(args) >= 8:
            yi, zi, yj, zj = map(float, args[4:8])
            section.fiber_components.append(
                FiberComponentData(
                    "RectPatch",
                    "Imported rect patch",
                    int(args[1]),
                    {
                        "n_y": int(args[2]),
                        "n_z": int(args[3]),
                        "y_center": (yi + yj) / 2.0,
                        "z_center": (zi + zj) / 2.0,
                        "width_y": abs(yj - yi),
                        "depth_z": abs(zj - zi),
                    },
                )
            )
            self.count("Fiber components")
            return
        if kind == "circ" and len(args) >= 8:
            section.fiber_components.append(
                FiberComponentData(
                    "CircPatch",
                    "Imported circular patch",
                    int(args[1]),
                    {
                        "n_circum": int(args[2]),
                        "n_radial": int(args[3]),
                        "y_center": float(args[4]),
                        "z_center": float(args[5]),
                        "r_inner": float(args[6]),
                        "r_outer": float(args[7]),
                        "start_angle": float(args[8]) if len(args) > 8 else 0.0,
                        "end_angle": float(args[9]) if len(args) > 9 else 360.0,
                    },
                )
            )
            self.count("Fiber components")
            return
        self.issue(
            "UNSUPPORTED", node, f"patch {kind}",
            f"Patch {kind!r} is not supported by the importer yet.",
        )

    def add_layer(self, node: ast.Call, args: list[Any]) -> None:
        if not args:
            raise ValueError("layer needs a type")
        kind = str(args[0]).lower()
        section = self.fiber_section()
        if kind == "straight" and len(args) >= 8:
            section.fiber_components.append(
                FiberComponentData(
                    "StraightLayer",
                    "Imported straight layer",
                    int(args[1]),
                    {
                        "n_bars": int(args[2]),
                        "bar_area": float(args[3]),
                        "y_i": float(args[4]),
                        "z_i": float(args[5]),
                        "y_j": float(args[6]),
                        "z_j": float(args[7]),
                    },
                )
            )
            self.count("Fiber components")
            return
        if kind == "circ" and len(args) >= 7:
            section.fiber_components.append(
                FiberComponentData(
                    "CircLayer",
                    "Imported circular layer",
                    int(args[1]),
                    {
                        "n_bars": int(args[2]),
                        "bar_area": float(args[3]),
                        "y_center": float(args[4]),
                        "z_center": float(args[5]),
                        "radius": float(args[6]),
                        "start_angle": float(args[7]) if len(args) > 7 else 0.0,
                        "end_angle": float(args[8]) if len(args) > 8 else 360.0,
                    },
                )
            )
            self.count("Fiber components")
            return
        self.issue(
            "UNSUPPORTED", node, f"layer {kind}",
            f"Layer {kind!r} is not supported by the importer yet.",
        )

    def add_transformation(self, args: list[Any]) -> None:
        if len(args) < 2:
            raise ValueError("geomTransf needs type and tag")
        vector = (
            tuple(float(value) for value in args[2:5])
            if len(args) >= 5
            else (0.0, 0.0, 1.0)
        )
        self.project.add_transformation(
            TransformationData(
                int(args[1]),
                f"Imported {args[0]} {args[1]}",
                str(args[0]),
                vector,
            )
        )
        self.count("Transformations")

    def add_integration(self, node: ast.Call, args: list[Any]) -> None:
        if len(args) < 4:
            raise ValueError("beamIntegration has too few arguments")
        kind = str(args[0])
        tag = int(args[1])
        if kind in {"Lobatto", "Legendre", "Radau"}:
            self.integrations[tag] = {
                "type": kind,
                "section": int(args[2]),
                "points": int(args[3]),
            }
            self.count("Beam integrations")
            return
        if (
            kind in {"HingeRadau", "HingeRadauTwo", "HingeMidpoint", "HingeEndpoint"}
            and len(args) >= 7
        ):
            self.integrations[tag] = {
                "type": kind,
                "hinge_i": int(args[2]),
                "length_i": float(args[3]),
                "hinge_j": int(args[4]),
                "length_j": float(args[5]),
                "interior": int(args[6]),
            }
            self.count("Beam integrations")
            return
        if kind == "ConcentratedPlasticity" and len(args) >= 5:
            self.integrations[tag] = {
                "type": kind,
                "hinge_i": int(args[2]),
                "hinge_j": int(args[3]),
                "interior": int(args[4]),
                "length_i": 0.0,
                "length_j": 0.0,
            }
            self.count("Beam integrations")
            return
        self.issue(
            "UNSUPPORTED", node, f"beamIntegration {kind}",
            f"Beam integration {kind!r} is not supported yet.",
        )

    def elastic_section_for(
        self,
        a: float,
        e: float,
        g: float,
        j: float,
        iy: float,
        iz: float,
    ) -> int:
        for tag, section in self.project.sections.items():
            if section.section_type != "Elastic":
                continue
            p = section.parameters
            current = (
                p["A"],
                self.units.stress_from_pa(p["E"]),
                self.units.stress_from_pa(p["G"]),
                p["J"],
                p["Iy"],
                p["Iz"],
            )
            target = (a, e, g, j, iy, iz)
            if all(
                math.isclose(x, y, rel_tol=1e-9, abs_tol=1e-12)
                for x, y in zip(current, target)
            ):
                return tag
        tag = max(self.project.sections, default=0) + 1
        self.project.add_section(
            SectionData(
                tag,
                f"Imported inline elastic section {tag}",
                "Elastic",
                parameters={
                    "A": a,
                    "E": self.stress_to_pa(e),
                    "G": self.stress_to_pa(g),
                    "J": j,
                    "Iy": iy,
                    "Iz": iz,
                },
            )
        )
        self.count("Sections")
        return tag

    def add_element(self, node: ast.Call, args: list[Any]) -> None:
        if len(args) < 4:
            raise ValueError("element has too few arguments")
        kind = str(args[0])
        tag, ni, nj = map(int, args[1:4])

        if kind == "elasticBeamColumn":
            if len(args) < 11:
                self.issue(
                    "UNSUPPORTED", node, kind,
                    "Only the 3D elasticBeamColumn signature is imported in this pass.",
                )
                return
            a, e, g, j, iy, iz = map(float, args[4:10])
            section_tag = self.elastic_section_for(a, e, g, j, iy, iz)
            rest = args[11:]
            self.project.model.add_element(
                tag,
                ni,
                nj,
                "elasticBeamColumn",
                section_tag=section_tag,
                transf_tag=int(args[10]),
                mass_per_length=float(self.flag_value(rest, "-mass", 0.0) or 0.0),
                consistent_mass="-cMass" in rest,
            )
            self.count("Elements")
            return

        if kind in {"forceBeamColumn", "dispBeamColumn"}:
            if len(args) < 6:
                raise ValueError(f"{kind} needs transformation and integration tags")
            integration = self.integrations.get(int(args[5]))
            if integration is None:
                raise ValueError(f"Unresolved beamIntegration tag {args[5]}")
            kwargs: dict[str, Any] = {
                "element_type": kind,
                "transf_tag": int(args[4]),
                "integration_type": integration["type"],
            }
            if integration["type"] in {"Lobatto", "Legendre", "Radau"}:
                kwargs["section_tag"] = integration["section"]
                kwargs["integration_points"] = integration["points"]
            else:
                kwargs.update({
                    "section_tag": integration["interior"],
                    "hinge_i_section_tag": integration["hinge_i"],
                    "hinge_j_section_tag": integration["hinge_j"],
                    "interior_section_tag": integration["interior"],
                    "hinge_i_length": integration["length_i"],
                    "hinge_j_length": integration["length_j"],
                })
            rest = args[6:]
            kwargs["mass_per_length"] = float(
                self.flag_value(rest, "-mass", 0.0) or 0.0
            )
            kwargs["consistent_mass"] = "-cMass" in rest
            if kind == "forceBeamColumn" and "-iter" in rest:
                index = rest.index("-iter")
                if index + 2 < len(rest):
                    kwargs["force_max_iter"] = int(rest[index + 1])
                    kwargs["force_tolerance"] = float(rest[index + 2])
            self.project.model.add_element(tag, ni, nj, **kwargs)
            self.count("Elements")
            return

        if kind in {"zeroLength", "twoNodeLink"}:
            rest = args[4:]
            mats = [int(value) for value in self.flag_values(rest, "-mat")]
            dirs = [int(value) for value in self.flag_values(rest, "-dir")]
            if not mats or len(mats) != len(dirs):
                raise ValueError(f"{kind} needs matching -mat and -dir lists")
            orient_x = (1.0, 0.0, 0.0)
            orient_y = (0.0, 1.0, 0.0)
            if "-orient" in rest:
                index = rest.index("-orient") + 1
                orientation: list[float] = []
                while index < len(rest):
                    value = rest[index]
                    if isinstance(value, str):
                        break
                    orientation.append(float(value))
                    index += 1
                if len(orientation) >= 6:
                    orient_x = tuple(orientation[:3])
                    orient_y = tuple(orientation[3:6])
            self.project.add_connection(
                ConnectionData(
                    tag,
                    f"Imported {kind} {tag}",
                    kind,
                    ni,
                    nj,
                    materials_by_dof=dict(zip(dirs, mats)),
                    orient_x=orient_x,
                    orient_y=orient_y,
                    do_rayleigh=bool(
                        int(self.flag_value(rest, "-doRayleigh", 0) or 0)
                    ),
                )
            )
            self.count("Connections")
            return

        if kind == "zeroLengthSection":
            rest = args[4:]
            if not rest:
                raise ValueError("zeroLengthSection needs a section tag")
            orient_x = (1.0, 0.0, 0.0)
            orient_y = (0.0, 1.0, 0.0)
            if "-orient" in rest:
                index = rest.index("-orient") + 1
                orientation: list[float] = []
                while index < len(rest):
                    value = rest[index]
                    if isinstance(value, str):
                        break
                    orientation.append(float(value))
                    index += 1
                if len(orientation) >= 6:
                    orient_x = tuple(orientation[:3])
                    orient_y = tuple(orientation[3:6])
            self.project.add_connection(
                ConnectionData(
                    tag,
                    f"Imported zeroLengthSection {tag}",
                    "zeroLengthSection",
                    ni,
                    nj,
                    section_tag=int(rest[0]),
                    orient_x=orient_x,
                    orient_y=orient_y,
                    do_rayleigh=bool(
                        int(self.flag_value(rest, "-doRayleigh", 0) or 0)
                    ),
                )
            )
            self.count("Connections")
            return

        self.issue(
            "UNSUPPORTED", node, f"element {kind}",
            f"Element {kind!r} is not supported by the importer yet.",
        )

    def add_constraint(self, command: str, args: list[Any]) -> None:
        tag = self._next_constraint
        self._next_constraint += 1
        if command == "equalDOF":
            item = ConstraintData(
                tag,
                f"Imported equalDOF {tag}",
                "equalDOF",
                int(args[0]),
                [int(args[1])],
                dofs=tuple(int(value) for value in args[2:]),
            )
        elif command == "rigidLink":
            item = ConstraintData(
                tag,
                f"Imported rigidLink {tag}",
                "rigidLink",
                int(args[1]),
                [int(args[2])],
                link_type=str(args[0]),
            )
        else:
            item = ConstraintData(
                tag,
                f"Imported rigidDiaphragm {tag}",
                "rigidDiaphragm",
                int(args[1]),
                [int(value) for value in args[2:]],
                perp_dirn=int(args[0]),
            )
        self.project.add_constraint(item)
        self.count("Constraints")

    def add_time_series(self, node: ast.Call, args: list[Any]) -> None:
        if len(args) < 2:
            raise ValueError("timeSeries needs type and tag")
        kind, tag = str(args[0]), int(args[1])
        rest = args[2:]
        if kind in {"Linear", "Constant"}:
            item = TimeSeriesData(
                tag,
                f"Imported {kind} {tag}",
                kind,
                factor=float(self.flag_value(rest, "-factor", 1.0) or 1.0),
            )
        elif kind == "Path":
            dt = self.flag_value(rest, "-dt")
            values = self.flag_values(rest, "-values")
            if dt is None or not values:
                self.issue(
                    "UNSUPPORTED", node, "timeSeries Path",
                    "Path import currently requires inline -dt and -values; "
                    "external files are never opened automatically.",
                )
                return
            item = TimeSeriesData(
                tag,
                f"Imported Path {tag}",
                "Path",
                factor=float(self.flag_value(rest, "-factor", 1.0) or 1.0),
                dt=float(dt),
                values=[float(value) for value in values],
            )
        else:
            self.issue(
                "UNSUPPORTED", node, f"timeSeries {kind}",
                f"Time series {kind!r} is not supported yet.",
            )
            return
        self.project.add_time_series(item)
        self.count("Time series")

    def add_pattern(self, node: ast.Call, args: list[Any]) -> None:
        if len(args) < 3:
            raise ValueError("pattern needs type, tag and timeSeries tag")
        kind, tag = str(args[0]), int(args[1])
        if kind == "Plain":
            item = LoadPatternData(
                tag,
                f"Imported Plain {tag}",
                "Plain",
                int(args[2]),
            )
        elif kind == "UniformExcitation" and len(args) >= 4:
            direction = int(args[2])
            rest = args[3:]
            accel_tag = self.flag_value(rest, "-accel")
            if accel_tag is None:
                raise ValueError(
                    "UniformExcitation requires an -accel timeSeries tag"
                )
            item = LoadPatternData(
                tag,
                f"Imported UniformExcitation {tag}",
                "UniformExcitation",
                int(accel_tag),
                direction=direction,
                vel0=float(self.flag_value(rest, "-vel0", 0.0) or 0.0),
                factor=float(self.flag_value(rest, "-fact", 1.0) or 1.0),
            )
        else:
            self.issue(
                "UNSUPPORTED", node, f"pattern {kind}",
                f"Pattern {kind!r} is not supported yet.",
            )
            return
        self.project.add_load_pattern(item)
        self.current_pattern = tag
        self.count("Load patterns")

    def add_load(self, args: list[Any]) -> None:
        if self.current_pattern is None:
            raise ValueError("load appears before a supported pattern")
        values = [float(value) for value in args[1:]]
        values = (values + [0.0] * 6)[:6]
        item = NodalLoadData(
            self._next_load,
            f"Imported nodal load {self._next_load}",
            self.current_pattern,
            int(args[0]),
            tuple(values),
        )
        self._next_load += 1
        self.project.add_nodal_load(item)
        self.count("Nodal loads")

    def add_prescribed_displacement(self, args: list[Any]) -> None:
        if self.current_pattern is None:
            raise ValueError("sp appears before a supported Plain pattern")
        if len(args) < 3:
            raise ValueError("sp needs node tag, DOF and value")
        item = PrescribedDisplacementData(
            self._next_prescribed,
            f"Imported prescribed displacement {self._next_prescribed}",
            self.current_pattern,
            int(args[0]),
            int(args[1]),
            float(args[2]),
        )
        self._next_prescribed += 1
        self.project.add_prescribed_displacement(item)
        self.count("Prescribed displacements")

    def add_element_load(self, node: ast.Call, args: list[Any]) -> None:
        if self.current_pattern is None:
            raise ValueError("eleLoad appears before a supported Plain pattern")
        if "-ele" not in args or "-type" not in args:
            raise ValueError("eleLoad needs -ele and -type")
        ele_index = args.index("-ele") + 1
        type_index = args.index("-type")
        element_tags = [
            int(value)
            for value in args[ele_index:type_index]
            if not isinstance(value, str)
        ]
        if not element_tags or type_index + 1 >= len(args):
            raise ValueError("eleLoad target/type could not be resolved")
        load_type = str(args[type_index + 1])
        payload = list(args[type_index + 2:])
        for element_tag in element_tags:
            if load_type == "-beamUniform":
                if len(payload) < 2:
                    raise ValueError("beamUniform needs Wy and Wz")
                wy = float(payload[0])
                wz = float(payload[1])
                wx = float(payload[2]) if len(payload) > 2 else 0.0
                item = ElementLoadData(
                    self._next_element_load,
                    f"Imported uniform load {self._next_element_load}",
                    self.current_pattern,
                    element_tag,
                    "Uniform",
                    wx=wx,
                    wy=wy,
                    wz=wz,
                )
            elif load_type == "-beamPoint":
                if len(payload) < 3:
                    raise ValueError("beamPoint needs Py, Pz and x/L")
                item = ElementLoadData(
                    self._next_element_load,
                    f"Imported point load {self._next_element_load}",
                    self.current_pattern,
                    element_tag,
                    "Point",
                    py=float(payload[0]),
                    pz=float(payload[1]),
                    x_over_l=float(payload[2]),
                    px=float(payload[3]) if len(payload) > 3 else 0.0,
                )
            else:
                self.issue(
                    "UNSUPPORTED", node, "eleLoad",
                    f"Element load type {load_type!r} is not supported yet.",
                )
                return
            self._next_element_load += 1
            self.project.add_element_load(item)
            self.count("Element loads")

    def add_recorder(self, node: ast.Call, args: list[Any]) -> None:
        if not args:
            raise ValueError("recorder needs a type")
        kind = str(args[0])
        rest = list(args[1:])
        file_name = str(
            self.flag_value(
                rest,
                "-file",
                f"recorders/imported_{self._next_recorder}.out",
            )
        )
        include_time = "-time" in rest

        if kind == "Node":
            if "-node" not in rest or "-dof" not in rest:
                raise ValueError("Node recorder needs -node and -dof")
            node_index = rest.index("-node") + 1
            dof_flag = rest.index("-dof")
            targets = [int(v) for v in rest[node_index:dof_flag]]
            response = str(rest[-1])
            dofs = [int(v) for v in rest[dof_flag + 1:-1]]
            item = RecorderData(
                self._next_recorder,
                f"Imported Node recorder {self._next_recorder}",
                "Node",
                target_tags=targets,
                response=response,
                dofs=dofs,
                file_name=file_name,
                include_time=include_time,
            )
        elif kind == "Element":
            if "-ele" not in rest:
                raise ValueError("Element recorder needs -ele")
            ele_index = rest.index("-ele") + 1
            marker_indices = [
                index
                for index, value in enumerate(rest)
                if value in {"section", "fiber"} and index >= ele_index
            ]
            target_end = (
                min(marker_indices)
                if marker_indices
                else len(rest) - 1
            )
            targets = [int(v) for v in rest[ele_index:target_end]]
            response = str(rest[-1])

            if "fiber" in rest:
                section_index = rest.index("section")
                fiber_index = rest.index("fiber")
                material_tag = None
                cursor = fiber_index + 3
                if (
                    cursor < len(rest) - 1
                    and isinstance(rest[cursor], (int, float))
                ):
                    material_tag = int(rest[cursor])
                item = RecorderData(
                    self._next_recorder,
                    f"Imported Fiber recorder {self._next_recorder}",
                    "Fiber",
                    target_tags=targets,
                    response=response,
                    file_name=file_name,
                    include_time=include_time,
                    section_number=int(rest[section_index + 1]),
                    fiber_y=float(rest[fiber_index + 1]),
                    fiber_z=float(rest[fiber_index + 2]),
                    material_tag=material_tag,
                )
            elif "section" in rest:
                section_index = rest.index("section")
                item = RecorderData(
                    self._next_recorder,
                    f"Imported Section recorder {self._next_recorder}",
                    "Section",
                    target_tags=targets,
                    response=response,
                    file_name=file_name,
                    include_time=include_time,
                    section_number=int(rest[section_index + 1]),
                )
            else:
                item = RecorderData(
                    self._next_recorder,
                    f"Imported Element recorder {self._next_recorder}",
                    "Element",
                    target_tags=targets,
                    response=response,
                    file_name=file_name,
                    include_time=include_time,
                )
        else:
            self.issue(
                "UNSUPPORTED", node, f"recorder {kind}",
                f"Recorder {kind!r} is not supported yet.",
            )
            return

        self._next_recorder += 1
        self.project.add_recorder(item)
        self.count("Recorders")

    def analysis_command(self, command: str, args: list[Any]) -> None:
        if command == "wipeAnalysis":
            self.analysis_state.clear()
        elif command in {"constraints", "numberer", "system", "algorithm"} and args:
            self.analysis_state[command] = str(args[0])
        elif command == "test" and args:
            self.analysis_state["test"] = str(args[0])
            if len(args) > 1:
                self.analysis_state["tolerance"] = float(args[1])
            if len(args) > 2:
                self.analysis_state["max_iterations"] = int(args[2])
        elif command == "integrator" and args:
            self.analysis_state["integrator"] = str(args[0])
            self.analysis_state["integrator_args"] = list(args[1:])
        elif command == "analysis" and args:
            self.analysis_state["analysis_kind"] = str(args[0])
        elif command == "analyze" and args:
            self.analysis_state["steps"] = int(args[0])
            if len(args) > 1:
                self.analysis_state["dt"] = float(args[1])
        elif command == "eigen" and args:
            self.analysis_state["modal"] = True
            self.analysis_state["num_modes"] = int(args[-1])
            if len(args) > 1 and isinstance(args[0], str):
                self.analysis_state["eigen_solver"] = str(args[0])

    def handle_call(self, command: str, node: ast.Call) -> None:
        try:
            args = self.call_args(node)
            if command in {"wipe", "rayleigh", "loadConst", "reactions"}:
                return
            if command == "model":
                ndm = int(self.flag_value(args, "-ndm", 3))
                ndf = int(self.flag_value(args, "-ndf", 6))
                self.project.model = StructuralModel(
                    self.project.model.name,
                    ndm=ndm,
                    ndf=ndf,
                )
                self.count("Model definitions")
            elif command == "node":
                coords = [float(value) for value in args[1:4]]
                coords = (coords + [0.0] * 3)[:3]
                self.project.model.add_node(int(args[0]), *coords)
                self.count("Nodes")
            elif command == "fix":
                values = [int(value) for value in args[1:]]
                values = (values + [0] * self.project.model.ndf)[:self.project.model.ndf]
                self.project.model.set_fixity(int(args[0]), values)
                self.count("Supports")
            elif command == "mass":
                values = [float(value) for value in args[1:]]
                values = (values + [0.0] * self.project.model.ndf)[:self.project.model.ndf]
                self.project.model.set_mass(int(args[0]), values)
                self.count("Mass assignments")
            elif command == "uniaxialMaterial":
                self.add_material(node, args)
            elif command == "section":
                self.add_section(node, args)
            elif command == "fiber":
                self.add_fiber(args)
            elif command == "patch":
                self.add_patch(node, args)
            elif command == "layer":
                self.add_layer(node, args)
            elif command == "geomTransf":
                self.add_transformation(args)
            elif command == "beamIntegration":
                self.add_integration(node, args)
            elif command == "element":
                self.add_element(node, args)
            elif command in {"equalDOF", "rigidLink", "rigidDiaphragm"}:
                self.add_constraint(command, args)
            elif command == "timeSeries":
                self.add_time_series(node, args)
            elif command == "pattern":
                self.add_pattern(node, args)
            elif command == "load":
                self.add_load(args)
            elif command == "sp":
                self.add_prescribed_displacement(args)
            elif command == "eleLoad":
                self.add_element_load(node, args)
            elif command == "recorder":
                self.add_recorder(node, args)
            elif command in {
                "constraints", "numberer", "system", "test", "algorithm",
                "integrator", "analysis", "analyze", "eigen", "wipeAnalysis",
            }:
                self.analysis_command(command, args)
        except _Unresolved as exc:
            self.issue(
                "UNSUPPORTED", node, command,
                f"Expression could not be resolved safely: {exc}.",
            )
        except (IndexError, KeyError, TypeError, ValueError) as exc:
            self.issue("ERROR", node, command, str(exc))

    def assign(self, target: ast.AST, value: Any) -> None:
        if isinstance(target, ast.Name):
            self.env[target.id] = value
            if target.id == "_studio_results" and isinstance(value, dict):
                data = value.get("analysis")
                if isinstance(data, dict):
                    self.analysis_metadata = dict(data)
            return
        if isinstance(target, (ast.Tuple, ast.List)) and isinstance(value, (tuple, list)):
            for child, child_value in zip(target.elts, value):
                self.assign(child, child_value)
            return
        raise _Unresolved("assignment target")

    def statement(self, stmt: ast.stmt) -> None:
        if isinstance(stmt, ast.Import):
            for alias in stmt.names:
                if alias.name == "openseespy.opensees":
                    self.ops_aliases.add(alias.asname or "ops")
            return
        if isinstance(stmt, ast.ImportFrom):
            if stmt.module == "openseespy.opensees":
                if any(alias.name == "*" for alias in stmt.names):
                    self.direct_ops = True
            return
        if isinstance(stmt, ast.Assign):
            try:
                value = self.eval.eval(stmt.value)
                for target in stmt.targets:
                    self.assign(target, value)
            except _Unresolved:
                names = [
                    target.id for target in stmt.targets
                    if isinstance(target, ast.Name)
                ]
                if (
                    not self._studio_source
                    and (
                        not names
                        or not all(name.startswith("_studio_") for name in names)
                    )
                ):
                    self.issue(
                        "WARNING", stmt, "assignment",
                        "Assignment could not be resolved safely.",
                    )
            return
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
            command = self.command_name(stmt.value)
            if command is not None:
                self.handle_call(command, stmt.value)
            elif not self._studio_source:
                self.issue(
                    "UNSUPPORTED", stmt, "function call",
                    "Custom Python function calls are not executed during import.",
                )
            return
        if isinstance(stmt, ast.For):
            if isinstance(stmt.target, ast.Name) and stmt.target.id.startswith("_studio_"):
                return
            if not (
                isinstance(stmt.iter, ast.Call)
                and isinstance(stmt.iter.func, ast.Name)
                and stmt.iter.func.id == "range"
            ):
                self.issue(
                    "UNSUPPORTED", stmt, "for loop",
                    "Only for ... in range(...) loops are expanded safely.",
                )
                return
            try:
                values = list(
                    range(*(int(self.eval.eval(arg)) for arg in stmt.iter.args))
                )
            except Exception:
                self.issue(
                    "UNSUPPORTED", stmt, "for range",
                    "range bounds could not be resolved safely.",
                )
                return
            if len(values) > 20000:
                self.issue(
                    "UNSUPPORTED", stmt, "for range",
                    "Loop exceeds the 20,000-iteration safe import limit.",
                )
                return
            for value in values:
                try:
                    self.assign(stmt.target, value)
                except _Unresolved:
                    self.issue(
                        "UNSUPPORTED", stmt, "for target",
                        "Loop target is not a simple resolvable variable.",
                    )
                    return
                for child in stmt.body:
                    self.statement(child)
            return
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if not getattr(stmt, "name", "").startswith("_studio_"):
                self.issue(
                    "UNSUPPORTED", stmt, "definition",
                    "Custom function/class bodies are not executed in safe import mode.",
                )
            return
        if isinstance(stmt, (ast.Try, ast.While, ast.With, ast.If)):
            if not self._studio_source:
                self.issue(
                    "UNSUPPORTED", stmt, type(stmt).__name__,
                    "This control-flow construct is not executed in safe import mode.",
                )
            return

    def finish_analysis(self) -> None:
        meta = dict(self.analysis_metadata)
        state = dict(self.analysis_state)
        if not meta and not state:
            return

        analysis_type = str(meta.get("type", ""))
        if not analysis_type:
            if state.get("modal"):
                analysis_type = "Modal"
            elif state.get("analysis_kind") == "Transient":
                analysis_type = "Transient"
            elif state.get("integrator") == "DisplacementControl":
                analysis_type = "Pushover"
            else:
                analysis_type = "Static"

        kwargs: dict[str, Any] = {
            "tag": int(meta.get("tag", 1) or 1),
            "name": str(meta.get("name", "Imported Analysis")),
            "analysis_type": analysis_type,
            "constraints_handler": str(state.get("constraints", "Transformation")),
            "numberer": str(state.get("numberer", "RCM")),
            "system": str(state.get("system", "UmfPack")),
            "test": str(state.get("test", "NormDispIncr")),
            "tolerance": float(state.get("tolerance", 1e-8)),
            "max_iterations": int(state.get("max_iterations", 50)),
            "algorithm": str(state.get("algorithm", "Newton")),
            "steps": max(1, int(meta.get("planned_steps", state.get("steps", 1)) or 1)),
            "control_node": int(
                meta.get("control_node", min(self.project.model.nodes, default=1)) or 1
            ),
            "control_dof": int(meta.get("control_dof", 1) or 1),
            "live_convergence": False,
        }

        integrator = state.get("integrator")
        values = list(state.get("integrator_args", []))
        if analysis_type == "Static" and integrator == "LoadControl" and values:
            kwargs["load_increment"] = float(values[0])
        elif analysis_type == "Pushover" and integrator == "DisplacementControl":
            if len(values) >= 3:
                kwargs["control_node"] = int(values[0])
                kwargs["control_dof"] = int(values[1])
                kwargs["displacement_increment"] = float(values[2])
        elif analysis_type == "Cyclic":
            if meta.get("cyclic_targets"):
                kwargs["cyclic_targets"] = [
                    float(value) for value in meta["cyclic_targets"]
                ]
            kwargs["cyclic_increment"] = float(meta.get("cyclic_increment", 0.001))
        elif analysis_type == "Transient":
            kwargs["dt"] = float(state.get("dt", 0.01))
            if integrator == "Newmark" and len(values) >= 2:
                kwargs["gamma"] = float(values[0])
                kwargs["beta"] = float(values[1])
        elif analysis_type == "Modal":
            kwargs["num_modes"] = int(state.get("num_modes", 1))
            kwargs["eigen_solver"] = str(
                meta.get(
                    "eigen_solver",
                    state.get("eigen_solver", "-genBandArpack"),
                )
            )

        try:
            analysis = AnalysisSettingsData(**kwargs)
            self.project.add_analysis(analysis)
            self.count("Analyses")
        except (TypeError, ValueError) as exc:
            self.issue(
                "WARNING", None, "analysis",
                f"Analysis settings were only partially recoverable: {exc}",
            )

    def run(self) -> OpenSeesImportResult:
        try:
            tree = ast.parse(self.source, filename=self.source_name or "<import>")
        except SyntaxError as exc:
            self.issue(
                "ERROR", None, "Python syntax",
                f"Line {exc.lineno}: {exc.msg}",
            )
            return OpenSeesImportResult(
                self.project, self.issues, self.counts, self.source_name
            )

        for stmt in tree.body:
            self.statement(stmt)
        self.finish_analysis()

        if self.project.model.ndm != 3 or self.project.model.ndf != 6:
            self.issue(
                "WARNING", None, "model dimensions",
                f"Imported ndm={self.project.model.ndm}, ndf={self.project.model.ndf}. "
                "Review 2D re-export carefully because Studio is strongest on "
                "its 3D/6-DOF backend.",
            )

        return OpenSeesImportResult(
            self.project,
            self.issues,
            self.counts,
            self.source_name,
        )


def import_openseespy_source(
    source: str,
    *,
    source_name: str = "imported.py",
    units: dict[str, str] | None = None,
) -> OpenSeesImportResult:
    """Parse OpenSeesPy source without executing arbitrary Python."""
    return _Importer(source, source_name, units).run()
