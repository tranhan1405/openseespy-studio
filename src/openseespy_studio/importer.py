from __future__ import annotations

import ast
import math
from dataclasses import dataclass, field
from pathlib import Path
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
    NDMaterialData,
    NodalLoadData,
    PrescribedDisplacementData,
    ProjectDatabase,
    RecorderData,
    SectionData,
    ShellLayerData,
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


class _ReturnSignal(Exception):
    def __init__(self, value: Any = None):
        super().__init__()
        self.value = value


class _BreakSignal(Exception):
    pass


class _ContinueSignal(Exception):
    pass


class _SafeEvaluator:
    SAFE_NOOP_CALLS = {"print"}

    SAFE_CALLS = {
        "int": int,
        "float": float,
        "bool": bool,
        "str": str,
        "abs": abs,
        "round": round,
        "min": min,
        "max": max,
        "len": len,
        "range": range,
        "enumerate": enumerate,
        "zip": zip,
        "list": list,
        "tuple": tuple,
        "sum": sum,
        "sorted": sorted,
    }

    def __init__(
        self,
        env: dict[str, Any],
        call_handler: Any = None,
    ):
        self.env = env
        self.call_handler = call_handler

    @staticmethod
    def _binary(op: ast.operator, left: Any, right: Any) -> Any:
        if isinstance(op, ast.Add):
            return left + right
        if isinstance(op, ast.Sub):
            return left - right
        if isinstance(op, ast.Mult):
            return left * right
        if isinstance(op, ast.Div):
            return left / right
        if isinstance(op, ast.FloorDiv):
            return left // right
        if isinstance(op, ast.Mod):
            return left % right
        if isinstance(op, ast.Pow):
            return left ** right
        raise _Unresolved(type(op).__name__)

    @staticmethod
    def _compare(op: ast.cmpop, left: Any, right: Any) -> bool:
        if isinstance(op, ast.Eq):
            return left == right
        if isinstance(op, ast.NotEq):
            return left != right
        if isinstance(op, ast.Lt):
            return left < right
        if isinstance(op, ast.LtE):
            return left <= right
        if isinstance(op, ast.Gt):
            return left > right
        if isinstance(op, ast.GtE):
            return left >= right
        if isinstance(op, ast.In):
            return left in right
        if isinstance(op, ast.NotIn):
            return left not in right
        if isinstance(op, ast.Is):
            return left is right
        if isinstance(op, ast.IsNot):
            return left is not right
        raise _Unresolved(type(op).__name__)

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
        if isinstance(node, ast.Set):
            return {self.eval(item) for item in node.elts}
        if isinstance(node, ast.Dict):
            return {
                self.eval(key): self.eval(value)
                for key, value in zip(node.keys, node.values)
                if key is not None
            }
        if isinstance(node, ast.Slice):
            return slice(
                self.eval(node.lower) if node.lower is not None else None,
                self.eval(node.upper) if node.upper is not None else None,
                self.eval(node.step) if node.step is not None else None,
            )
        if isinstance(node, ast.UnaryOp):
            value = self.eval(node.operand)
            if isinstance(node.op, ast.UAdd):
                return +value
            if isinstance(node.op, ast.USub):
                return -value
            if isinstance(node.op, ast.Not):
                return not value
            raise _Unresolved(type(node.op).__name__)
        if isinstance(node, ast.BinOp):
            return self._binary(
                node.op,
                self.eval(node.left),
                self.eval(node.right),
            )
        if isinstance(node, ast.BoolOp):
            if isinstance(node.op, ast.And):
                value: Any = True
                for child in node.values:
                    value = self.eval(child)
                    if not value:
                        return value
                return value
            if isinstance(node.op, ast.Or):
                value = False
                for child in node.values:
                    value = self.eval(child)
                    if value:
                        return value
                return value
            raise _Unresolved(type(node.op).__name__)
        if isinstance(node, ast.Compare):
            left = self.eval(node.left)
            for op, comparator in zip(node.ops, node.comparators):
                right = self.eval(comparator)
                if not self._compare(op, left, right):
                    return False
                left = right
            return True
        if isinstance(node, ast.IfExp):
            branch = node.body if self.eval(node.test) else node.orelse
            return self.eval(branch)
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
            if (
                isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "math"
                and node.func.attr in {
                    "acos", "asin", "atan", "cos", "sin", "tan",
                    "sqrt", "exp", "log", "log10",
                }
            ):
                fn = getattr(math, node.func.attr)
                if node.keywords:
                    raise _Unresolved("math keyword arguments")
                return fn(*(self.eval(arg) for arg in node.args))
            if isinstance(node.func, ast.Name):
                name = node.func.id
                if name in self.SAFE_NOOP_CALLS:
                    return None
                if name in self.SAFE_CALLS:
                    if any(keyword.arg is None for keyword in node.keywords):
                        raise _Unresolved("**kwargs")
                    fn = self.SAFE_CALLS[name]
                    return fn(
                        *(self.eval(arg) for arg in node.args),
                        **{
                            keyword.arg: self.eval(keyword.value)
                            for keyword in node.keywords
                            if keyword.arg is not None
                        },
                    )
                if self.call_handler is not None:
                    return self.call_handler(node)
        raise _Unresolved(type(node).__name__)


class _Importer:
    RUNTIME_ONLY_CALLS = {
        "open",
        "nodeDisp",
        "nodeVel",
        "nodeAccel",
        "nodeReaction",
        "eleResponse",
        "sectionForce",
        "sectionDeformation",
        "getTime",
        "getLoadFactor",
        "getNodeTags",
        "getEleTags",
    }

    RUNTIME_ONLY_METHODS = {"write", "writelines", "flush", "close"}

    MAX_LOOP_ITERATIONS = 20_000
    MAX_CALL_DEPTH = 50
    MAX_STATEMENT_STEPS = 100_000

    OPS_COMMANDS = {
        "model", "wipe", "wipeAnalysis", "node", "fix", "mass",
        "uniaxialMaterial", "nDMaterial", "section", "fiber", "patch", "layer",
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
        source_path: str | Path | None = None,
    ):
        self.source = str(source)
        self.source_name = str(source_name)
        self.source_path = (
            Path(source_path).resolve()
            if source_path is not None
            else None
        )
        self.source_dir = (
            self.source_path.parent
            if self.source_path is not None
            else None
        )
        self._imported_local_modules: set[Path] = set()
        if self.source_path is not None:
            self._imported_local_modules.add(self.source_path)
        self.units = UnitSystem.from_mapping(units)
        stem = self.source_name.rsplit(".", 1)[0] or "Imported"
        self.project = ProjectDatabase(
            name=stem,
            model=StructuralModel(stem),
        )
        self.project.units = self.units.as_mapping()
        self.issues: list[ImportIssue] = []
        self.counts: dict[str, int] = {}
        self.env: dict[str, Any] = {
            "pi": math.pi,
            "__name__": "__main__",
        }
        self.functions: dict[str, ast.FunctionDef] = {}
        self.runtime_only_names: set[str] = set()
        self._call_depth = 0
        self._statement_steps = 0
        self.eval = _SafeEvaluator(self.env, self._call_custom_function)
        self.ops_aliases = {"ops"}
        self.direct_ops = False
        self.current_pattern: int | None = None
        self.current_fiber_section: int | None = None
        self.integrations: dict[int, dict[str, Any]] = {}
        self.analysis_state: dict[str, Any] = {}
        self.analysis_metadata: dict[str, Any] = {}
        self.analysis_events: list[dict[str, Any]] = []
        self._deferred_modal_frequencies: dict[str, dict[str, Any]] = {}
        self._next_constraint = 1
        self._next_load = 1
        self._next_element_load = 1
        self._next_prescribed = 1
        self._next_recorder = 1
        self.surface_load_helpers: dict[
            int, tuple[tuple[int, int, int, int], float]
        ] = {}
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
        if kind == "FRPConfinedConcrete":
            self.issue(
                "WARNING",
                node,
                "FRPConfinedConcrete runtime",
                "Imported faithfully for editing/export. Some stock OpenSeesPy "
                "builds, including 3.8.0 used by Studio CI, report this legacy "
                "material as temporarily removed from compiled runtimes; "
                "execution requires a compatible/custom OpenSees build.",
            )

    def add_nd_material(self, node: ast.Call, args: list[Any]) -> None:
        if len(args) < 4:
            raise ValueError(
                "nDMaterial needs type, tag, E and Poisson ratio"
            )
        kind = str(args[0])
        tag = int(args[1])
        if kind != "ElasticIsotropic":
            self.issue(
                "UNSUPPORTED",
                node,
                f"nDMaterial {kind}",
                f"nDMaterial {kind!r} is not supported by Studio yet.",
            )
            return
        density_model = float(args[4]) if len(args) >= 5 else 0.0
        density_kg_m3 = (
            density_model
            * self.units.mass_unit_kg
            / (self.units.length_to_m ** 3)
        )
        self.project.add_nd_material(
            NDMaterialData(
                tag,
                f"Imported ElasticIsotropic {tag}",
                "ElasticIsotropic",
                parameters={
                    "E": self.stress_to_pa(args[2]),
                    "nu": float(args[3]),
                    "rho": density_kg_m3,
                },
            )
        )
        self.count("nD Materials")

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
        if kind == "ElasticMembranePlateSection":
            if len(args) < 5:
                raise ValueError(
                    "ElasticMembranePlateSection needs E, nu and thickness"
                )
            self.project.add_section(
                SectionData(
                    tag,
                    f"Imported Elastic Membrane Plate {tag}",
                    "ElasticMembranePlate",
                    parameters={
                        "E": self.stress_to_pa(args[2]),
                        "nu": float(args[3]),
                        "h": float(args[4]),
                        "rho": (
                            float(args[5])
                            if len(args) >= 6
                            else 0.0
                        ),
                        "EpModifier": (
                            float(args[6])
                            if len(args) >= 7
                            else 1.0
                        ),
                    },
                )
            )
            self.current_fiber_section = None
            self.count("Sections")
            return
        if kind == "PlateFiber":
            if len(args) < 4:
                raise ValueError(
                    "PlateFiber needs nDMaterial tag and thickness"
                )
            self.project.add_section(
                SectionData(
                    tag,
                    f"Imported PlateFiber {tag}",
                    "PlateFiber",
                    parameters={"h": float(args[3])},
                    nd_material_tag=int(args[2]),
                )
            )
            self.current_fiber_section = None
            self.count("Sections")
            return
        if kind == "LayeredShell":
            if len(args) < 5:
                raise ValueError(
                    "LayeredShell needs nLayers and material/thickness pairs"
                )
            layer_count = int(args[2])
            expected = 3 + 2 * layer_count
            if layer_count < 1 or len(args) < expected:
                raise ValueError(
                    "LayeredShell material/thickness pair count does not "
                    "match nLayers."
                )
            layers = [
                ShellLayerData(
                    int(args[3 + 2 * index]),
                    float(args[4 + 2 * index]),
                )
                for index in range(layer_count)
            ]
            self.project.add_section(
                SectionData(
                    tag,
                    f"Imported LayeredShell {tag}",
                    "LayeredShell",
                    shell_layers=layers,
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
        if kind == "WFSection2d":
            if len(args) < 9:
                raise ValueError(
                    "WFSection2d needs secTag, matTag, d, tw, bf, tf, Nfw, Nff"
                )
            mat_tag = int(args[2])
            d = float(args[3])
            tw = float(args[4])
            bf = float(args[5])
            tf = float(args[6])
            nfw = int(args[7])
            nff = int(args[8])
            if d <= 0.0 or tw <= 0.0 or bf <= 0.0 or tf <= 0.0:
                raise ValueError("WFSection2d dimensions must be positive")
            if 2.0 * tf >= d:
                raise ValueError("WFSection2d needs d > 2*tf")
            if nfw < 1 or nff < 1:
                raise ValueError("WFSection2d fiber counts must be positive")

            web_depth = d - 2.0 * tf
            section = SectionData(
                tag,
                f"Imported WFSection2d {tag}",
                "Fiber",
                parameters={"GJ": 1.0e6},
                fiber_components=[
                    FiberComponentData(
                        "RectPatch",
                        "Lower flange",
                        mat_tag,
                        {
                            "n_y": nff,
                            "n_z": 1,
                            "y_center": -0.5 * d + 0.5 * tf,
                            "z_center": 0.0,
                            "width_y": tf,
                            "depth_z": bf,
                        },
                    ),
                    FiberComponentData(
                        "RectPatch",
                        "Web",
                        mat_tag,
                        {
                            "n_y": nfw,
                            "n_z": 1,
                            "y_center": 0.0,
                            "z_center": 0.0,
                            "width_y": web_depth,
                            "depth_z": tw,
                        },
                    ),
                    FiberComponentData(
                        "RectPatch",
                        "Upper flange",
                        mat_tag,
                        {
                            "n_y": nff,
                            "n_z": 1,
                            "y_center": 0.5 * d - 0.5 * tf,
                            "z_center": 0.0,
                            "width_y": tf,
                            "depth_z": bf,
                        },
                    ),
                ],
                display_geometry={
                    "shape": "WideFlange",
                    "dimensions": {
                        "d": d,
                        "tw": tw,
                        "bf": bf,
                        "tf": tf,
                        "Nfw": float(nfw),
                        "Nff": float(nff),
                    },
                },
            )
            self.project.add_section(section)
            self.current_fiber_section = None
            self.count("Sections")
            self.count("WF sections")
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

        if kind == "SurfaceLoad":
            if len(args) != 7:
                raise ValueError(
                    "SurfaceLoad needs four node tags and pressure."
                )
            nk = int(args[4])
            nl = int(args[5])
            pressure = float(args[6])
            if tag in self.surface_load_helpers:
                raise ValueError(
                    f"SurfaceLoad helper tag {tag} already exists."
                )
            self.surface_load_helpers[tag] = (
                (ni, nj, nk, nl),
                pressure,
            )
            self.count("Surface load helpers")
            return

        if (
            kind not in {"zeroLength", "twoNodeLink", "zeroLengthSection"}
            and tag in self.project.connections
        ):
            raise ValueError(
                f"Element tag {tag} is already used by a connection."
            )

        if kind in {
            "ASDShellQ4",
            "ShellMITC4",
            "ShellDKGQ",
            "ShellNLDKGQ",
        }:
            if len(args) < 7:
                raise ValueError(
                    f"{kind} needs four node tags and a section tag"
                )
            nk = int(args[4])
            nl = int(args[5])
            section_tag = int(args[6])
            rest = args[7:]
            local_values = (
                self.flag_values(rest, "-local")
                if kind == "ASDShellQ4"
                else []
            )
            local_x = (
                tuple(float(value) for value in local_values[:3])
                if len(local_values) >= 3
                else None
            )
            drilling_stab = (
                self.flag_value(rest, "-drillingStab", None)
                if kind == "ASDShellQ4"
                else None
            )
            self.project.model.add_element(
                tag,
                ni,
                nj,
                element_type=kind,
                section_tag=section_tag,
                group="shell",
                k=nk,
                l=nl,
                shell_corotational=(
                    kind == "ASDShellQ4"
                    and "-corotational" in rest
                ),
                shell_local_x=local_x,
                shell_no_eas=(
                    kind == "ASDShellQ4"
                    and "-noeas" in rest
                ),
                shell_drilling_stab=(
                    float(drilling_stab)
                    if drilling_stab is not None
                    else None
                ),
                shell_drilling_nl=(
                    kind == "ASDShellQ4"
                    and "-drillingNL" in rest
                ),
            )
            self.count("Elements")
            return

        if kind.lower() == "truss":
            if len(args) < 6:
                raise ValueError("truss needs area and material tag")
            rest = args[6:]
            self.project.model.add_element(
                tag,
                ni,
                nj,
                element_type="truss",
                group="truss",
                mass_per_length=float(
                    self.flag_value(rest, "-rho", 0.0) or 0.0
                ),
                consistent_mass=bool(
                    int(self.flag_value(rest, "-cMass", 0) or 0)
                )
                if "-cMass" in rest
                else False,
                truss_area=float(args[4]),
                truss_material_tag=int(args[5]),
                truss_do_rayleigh=bool(
                    int(self.flag_value(rest, "-doRayleigh", 0) or 0)
                ),
            )
            self.count("Elements")
            return

        if kind == "elasticBeamColumn":
            if int(self.project.model.ndm) == 2:
                if len(args) < 8:
                    raise ValueError(
                        "2D elasticBeamColumn needs A, E, Iz and transfTag"
                    )
                a = float(args[4])
                e = float(args[5])
                iz = float(args[6])
                transf_tag = int(args[7])
                # G, J and Iy are not part of the native 2D signature.
                # Store neutral placeholders; the 2D generator never emits
                # them back into the elasticBeamColumn command.
                section_tag = self.elastic_section_for(
                    a,
                    e,
                    0.0,
                    0.0,
                    0.0,
                    iz,
                )
                rest = args[8:]
            else:
                if len(args) < 11:
                    raise ValueError(
                        "3D elasticBeamColumn needs A, E, G, J, Iy, Iz "
                        "and transfTag"
                    )
                a, e, g, j, iy, iz = map(float, args[4:10])
                transf_tag = int(args[10])
                section_tag = self.elastic_section_for(
                    a,
                    e,
                    g,
                    j,
                    iy,
                    iz,
                )
                rest = args[11:]

            self.project.model.add_element(
                tag,
                ni,
                nj,
                "elasticBeamColumn",
                section_tag=section_tag,
                transf_tag=transf_tag,
                mass_per_length=float(
                    self.flag_value(rest, "-mass", 0.0) or 0.0
                ),
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
            self.count("Elements")
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
            self.count("Elements")
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

    def _read_path_time_series_file(
        self,
        node: ast.Call,
        file_value: Any,
    ) -> list[float] | None:
        if self.source_dir is None:
            self.issue(
                "UNSUPPORTED",
                node,
                "timeSeries Path -filePath",
                "Relative Path time-series files can only be resolved when "
                "the imported Python source has a source_path.",
            )
            return None

        raw_path = Path(str(file_value))
        if raw_path.is_absolute():
            self.issue(
                "UNSUPPORTED",
                node,
                "timeSeries Path -filePath",
                "Absolute Path time-series files are not opened automatically; "
                "use a path relative to the imported Python script.",
            )
            return None

        base_dir = self.source_dir.resolve()
        data_path = (base_dir / raw_path).resolve()
        try:
            data_path.relative_to(base_dir)
        except ValueError:
            self.issue(
                "UNSUPPORTED",
                node,
                "timeSeries Path -filePath",
                "Path time-series files outside the imported script directory "
                "tree are not opened automatically.",
            )
            return None

        try:
            text = data_path.read_text(encoding="utf-8-sig")
        except OSError as exc:
            self.issue(
                "ERROR",
                node,
                "timeSeries Path -filePath",
                f"Could not read ground-motion file {str(file_value)!r}: {exc}",
            )
            return None

        tokens: list[str] = []
        for line in text.splitlines():
            body = line.split("#", 1)[0].replace(",", " ")
            tokens.extend(body.split())

        if not tokens:
            self.issue(
                "ERROR",
                node,
                "timeSeries Path -filePath",
                f"Ground-motion file {str(file_value)!r} contains no numeric values.",
            )
            return None

        try:
            return [float(token) for token in tokens]
        except ValueError as exc:
            self.issue(
                "ERROR",
                node,
                "timeSeries Path -filePath",
                f"Ground-motion file {str(file_value)!r} contains a non-numeric "
                f"value: {exc}",
            )
            return None

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
            file_path = self.flag_value(rest, "-filePath")

            if dt is None:
                self.issue(
                    "UNSUPPORTED",
                    node,
                    "timeSeries Path",
                    "Path import currently requires -dt.",
                )
                return

            if not values and file_path is not None:
                file_values = self._read_path_time_series_file(node, file_path)
                if file_values is None:
                    return
                values = file_values

            if not values:
                self.issue(
                    "UNSUPPORTED",
                    node,
                    "timeSeries Path",
                    "Path import requires either inline -values or a relative "
                    "-filePath that can be resolved from the imported script.",
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
            elif load_type in {"-surfaceLoad", "-SurfaceLoad"}:
                helper = self.surface_load_helpers.get(element_tag)
                if helper is None:
                    raise ValueError(
                        f"Surface-load helper element {element_tag} "
                        "was not defined before eleLoad."
                    )
                helper_nodes, helper_pressure = helper
                candidates = [
                    element
                    for element in self.project.model.elements.values()
                    if (
                        element.element_type in {
                            "ASDShellQ4",
                            "ShellMITC4",
                            "ShellDKGQ",
                            "ShellNLDKGQ",
                        }
                        and set(element.node_tags()) == set(helper_nodes)
                    )
                ]
                if len(candidates) != 1:
                    raise ValueError(
                        "SurfaceLoad helper could not be mapped uniquely "
                        "to one Shell element."
                    )
                shell = candidates[0]
                shell_nodes = shell.node_tags()
                forward = [
                    shell_nodes[index:] + shell_nodes[:index]
                    for index in range(4)
                ]
                reverse_base = tuple(reversed(shell_nodes))
                reverse = [
                    reverse_base[index:] + reverse_base[:index]
                    for index in range(4)
                ]
                if helper_nodes in forward:
                    orientation = 1.0
                elif helper_nodes in reverse:
                    orientation = -1.0
                else:
                    raise ValueError(
                        "SurfaceLoad node order is not a cyclic Shell "
                        "boundary ordering."
                    )
                item = ElementLoadData(
                    self._next_element_load,
                    f"Imported shell pressure {self._next_element_load}",
                    self.current_pattern,
                    shell.tag,
                    "SurfacePressure",
                    pressure=helper_pressure * orientation,
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
                if value in {"section", "fiber", "material"} and index >= ele_index
            ]
            target_end = (
                min(marker_indices)
                if marker_indices
                else len(rest) - 1
            )
            targets = [int(v) for v in rest[ele_index:target_end]]
            response = str(rest[-1])

            if "material" in rest and "fiber" not in rest:
                material_index = rest.index("material")
                gp = int(rest[material_index + 1])
                shell_targets = [
                    tag
                    for tag in targets
                    if (
                        tag in self.project.model.elements
                        and self.project.model.elements[tag].element_type
                        in {
                            "ASDShellQ4",
                            "ShellMITC4",
                            "ShellDKGQ",
                            "ShellNLDKGQ",
                        }
                    )
                ]
                if len(shell_targets) != len(targets):
                    self.issue(
                        "UNSUPPORTED",
                        node,
                        "Element material recorder",
                        "Studio currently imports material-point recorders "
                        "as Shell recorders only when every target is a "
                        "supported Shell element.",
                    )
                    return
                item = RecorderData(
                    self._next_recorder,
                    f"Imported Shell recorder {self._next_recorder}",
                    "Shell",
                    target_tags=targets,
                    response=response,
                    file_name=file_name,
                    include_time=include_time,
                    section_number=gp,
                )
            elif "fiber" in rest:
                section_index = rest.index("section")
                fiber_flag = rest.index("fiber")
                selector = list(rest[fiber_flag + 1:-1])
                if not selector:
                    raise ValueError("Fiber recorder needs an index or y-z coordinates")

                recorder_kwargs: dict[str, Any] = {}
                if len(selector) == 1:
                    recorder_kwargs["fiber_index"] = int(selector[0])
                else:
                    recorder_kwargs["fiber_y"] = float(selector[0])
                    recorder_kwargs["fiber_z"] = float(selector[1])
                    if len(selector) >= 3:
                        recorder_kwargs["material_tag"] = int(selector[2])

                item = RecorderData(
                    self._next_recorder,
                    f"Imported Fiber recorder {self._next_recorder}",
                    "Fiber",
                    target_tags=targets,
                    response=response,
                    file_name=file_name,
                    include_time=include_time,
                    section_number=int(rest[section_index + 1]),
                    **recorder_kwargs,
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
            preserved = {
                key: self.analysis_state[key]
                for key in (
                    "rayleigh_model",
                    "rayleigh_damping_ratio",
                    "rayleigh_mode_i",
                    "rayleigh_mode_j",
                    "eigen_solver",
                )
                if key in self.analysis_state
            }
            self.analysis_state.clear()
            self.analysis_state.update(preserved)
        elif command in {"constraints", "numberer"} and args:
            self.analysis_state[command] = str(args[0])
        elif command == "system" and args:
            system_name = str(args[0])
            normalized_system = {
                "BandGEN": "BandGeneral",
                "BandGen": "BandGeneral",
                "SparseGEN": "SparseGeneral",
                "SparseGen": "SparseGeneral",
            }.get(system_name, system_name)
            self.analysis_state["system"] = normalized_system
            self.analysis_state["system_pivoting"] = (
                normalized_system == "SparseGeneral"
                and "-piv" in args[1:]
            )
        elif command == "algorithm" and args:
            self.analysis_state["algorithm"] = str(args[0])
            self.analysis_state["algorithm_initial"] = (
                str(args[0]) == "ModifiedNewton"
                and "-initial" in args[1:]
            )
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
            self.analysis_events.append({
                "steps": int(args[0]),
                "dt": (
                    float(args[1])
                    if len(args) > 1
                    else self.analysis_state.get("dt")
                ),
                "integrator": self.analysis_state.get("integrator"),
                "integrator_args": list(
                    self.analysis_state.get("integrator_args", [])
                ),
                "analysis_kind": self.analysis_state.get("analysis_kind"),
                "pattern_tags": sorted(self.project.load_patterns),
                "current_pattern": self.current_pattern,
                "algorithm": self.analysis_state.get("algorithm"),
            })
        elif command == "eigen" and args:
            self.analysis_state["modal"] = True
            self.analysis_state["num_modes"] = int(args[-1])
            if len(args) > 1 and isinstance(args[0], str):
                self.analysis_state["eigen_solver"] = str(args[0])

    def handle_call(self, command: str, node: ast.Call) -> None:
        try:
            if command == "rayleigh":
                if self._recognize_single_mode_rayleigh(node):
                    return
                args = self.call_args(node)
                self.issue(
                    "WARNING",
                    node,
                    "rayleigh",
                    "Rayleigh damping was not mapped to a supported Studio damping model.",
                )
                return

            args = self.call_args(node)
            if command in {"wipe", "loadConst", "reactions"}:
                return
            if command == "model":
                ndm = int(self.flag_value(args, "-ndm", 3))
                default_ndf = {1: 1, 2: 3, 3: 6}.get(ndm, 6)
                ndf = int(self.flag_value(args, "-ndf", default_ndf))
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
            elif command == "nDMaterial":
                self.add_nd_material(node, args)
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

    def _recognize_eigen_frequency_assignment(self, stmt: ast.Assign) -> bool:
        if len(stmt.targets) != 1 or not isinstance(stmt.targets[0], ast.Name):
            return False

        value = stmt.value
        subscript: ast.Subscript | None = None

        if (
            isinstance(value, ast.BinOp)
            and isinstance(value.op, ast.Pow)
            and isinstance(value.right, ast.Constant)
            and isinstance(value.right.value, (int, float))
            and float(value.right.value) == 0.5
            and isinstance(value.left, ast.Subscript)
        ):
            subscript = value.left
        elif (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Attribute)
            and isinstance(value.func.value, ast.Name)
            and value.func.value.id == "math"
            and value.func.attr == "sqrt"
            and len(value.args) == 1
            and isinstance(value.args[0], ast.Subscript)
        ):
            subscript = value.args[0]

        if subscript is None or not isinstance(subscript.value, ast.Call):
            return False
        if self.command_name(subscript.value) != "eigen":
            return False

        try:
            args = self.call_args(subscript.value)
        except _Unresolved:
            return False
        if not args:
            return False

        index_node = subscript.slice
        if not isinstance(index_node, ast.Constant):
            return False
        try:
            index = int(index_node.value)
            num_modes = int(args[-1])
        except (TypeError, ValueError):
            return False
        if index < 0 or index >= num_modes:
            return False

        solver = (
            str(args[0])
            if len(args) > 1 and isinstance(args[0], str)
            else "-genBandArpack"
        )
        self._deferred_modal_frequencies[stmt.targets[0].id] = {
            "mode": index + 1,
            "solver": solver,
            "num_modes": num_modes,
        }
        return True

    def _recognize_single_mode_rayleigh(self, node: ast.Call) -> bool:
        if len(node.args) != 4:
            return False

        try:
            first_three = [float(self.eval.eval(arg)) for arg in node.args[:3]]
        except (_Unresolved, TypeError, ValueError):
            return False
        if any(abs(value) > 1.0e-15 for value in first_three):
            return False

        beta_expr = node.args[3]
        if (
            not isinstance(beta_expr, ast.BinOp)
            or not isinstance(beta_expr.op, ast.Div)
            or not isinstance(beta_expr.right, ast.Name)
        ):
            return False

        frequency_name = beta_expr.right.id
        spec = self._deferred_modal_frequencies.get(frequency_name)
        if spec is None:
            return False

        try:
            numerator = float(self.eval.eval(beta_expr.left))
        except (_Unresolved, TypeError, ValueError):
            return False
        if not math.isfinite(numerator) or numerator <= 0.0:
            return False

        self.analysis_state["rayleigh_model"] = "SingleModeCommittedStiffness"
        self.analysis_state["rayleigh_damping_ratio"] = numerator / 2.0
        self.analysis_state["rayleigh_mode_i"] = int(spec["mode"])
        self.analysis_state["eigen_solver"] = str(spec["solver"])
        self.count("Rayleigh damping")
        return True

    def _runtime_call_name(self, call: ast.Call) -> str | None:
        if isinstance(call.func, ast.Name):
            return (
                call.func.id
                if call.func.id in self.RUNTIME_ONLY_CALLS
                else None
            )
        if (
            isinstance(call.func, ast.Attribute)
            and isinstance(call.func.value, ast.Name)
            and call.func.value.id in self.ops_aliases
            and call.func.attr in self.RUNTIME_ONLY_CALLS
        ):
            return call.func.attr
        return None

    def _runtime_calls_in(self, node: ast.AST) -> list[str]:
        names: list[str] = []
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                name = self._runtime_call_name(child)
                if name is not None:
                    names.append(name)
        return names

    @staticmethod
    def _simple_target_names(target: ast.AST) -> set[str]:
        if isinstance(target, ast.Name):
            return {target.id}
        if isinstance(target, (ast.Tuple, ast.List)):
            result: set[str] = set()
            for child in target.elts:
                result.update(_Importer._simple_target_names(child))
            return result
        return set()

    def _call_custom_function(self, call: ast.Call) -> Any:
        if not isinstance(call.func, ast.Name):
            raise _Unresolved("custom call target")
        name = call.func.id
        function = self.functions.get(name)
        if function is None:
            raise _Unresolved(name)
        if self._call_depth >= self.MAX_CALL_DEPTH:
            raise _Unresolved(
                f"function call depth exceeds {self.MAX_CALL_DEPTH}"
            )

        arguments = [
            *function.args.posonlyargs,
            *function.args.args,
        ]
        if (
            function.args.vararg is not None
            or function.args.kwarg is not None
            or function.args.kwonlyargs
        ):
            raise _Unresolved(
                f"function {name} uses unsupported variadic/keyword-only arguments"
            )
        if any(keyword.arg is None for keyword in call.keywords):
            raise _Unresolved("**kwargs")

        positional = [self.eval.eval(arg) for arg in call.args]
        if len(positional) > len(arguments):
            raise _Unresolved(f"too many arguments for {name}")

        bindings: dict[str, Any] = {}
        for argument, value in zip(arguments, positional):
            bindings[argument.arg] = value

        valid_names = {argument.arg for argument in arguments}
        for keyword in call.keywords:
            assert keyword.arg is not None
            if keyword.arg not in valid_names:
                raise _Unresolved(
                    f"unknown argument {keyword.arg!r} for {name}"
                )
            if keyword.arg in bindings:
                raise _Unresolved(
                    f"multiple values for argument {keyword.arg!r}"
                )
            bindings[keyword.arg] = self.eval.eval(keyword.value)

        default_offset = len(arguments) - len(function.args.defaults)
        for index, argument in enumerate(arguments):
            if argument.arg in bindings:
                continue
            default_index = index - default_offset
            if default_index < 0:
                raise _Unresolved(
                    f"missing argument {argument.arg!r} for {name}"
                )
            bindings[argument.arg] = self.eval.eval(
                function.args.defaults[default_index]
            )

        saved_env = dict(self.env)
        self._call_depth += 1
        self.env.update(bindings)
        try:
            try:
                for child in function.body:
                    self.statement(child)
            except _ReturnSignal as signal:
                return signal.value
            return None
        finally:
            self.env.clear()
            self.env.update(saved_env)
            self._call_depth -= 1

    def assign(self, target: ast.AST, value: Any) -> None:
        if isinstance(target, ast.Name):
            self.env[target.id] = value
            if target.id == "_studio_results" and isinstance(value, dict):
                data = value.get("analysis")
                if isinstance(data, dict):
                    self.analysis_metadata = dict(data)
            return
        if (
            isinstance(target, (ast.Tuple, ast.List))
            and isinstance(value, (tuple, list))
        ):
            if len(target.elts) != len(value):
                raise _Unresolved("unpacking target length")
            for child, child_value in zip(target.elts, value):
                self.assign(child, child_value)
            return
        raise _Unresolved("assignment target")

    def _import_local_module(
        self,
        module_name: str,
        stmt: ast.Import,
    ) -> bool:
        """Safely inline a sibling Python module for OpenSees side effects."""
        if (
            self.source_dir is None
            or not module_name
            or "." in module_name
            or not module_name.isidentifier()
        ):
            return False

        candidate = (self.source_dir / f"{module_name}.py").resolve()
        if candidate.parent != self.source_dir or not candidate.is_file():
            return False
        if candidate in self._imported_local_modules:
            return True

        try:
            module_source = candidate.read_text(encoding="utf-8")
            module_tree = ast.parse(
                module_source,
                filename=str(candidate),
            )
        except (OSError, UnicodeError, SyntaxError) as exc:
            self.issue(
                "WARNING",
                stmt,
                f"import {module_name}",
                f"Could not safely read sibling module {candidate.name}: {exc}",
            )
            return True

        self._imported_local_modules.add(candidate)
        saved_env = dict(self.env)
        saved_functions = dict(self.functions)
        saved_direct_ops = self.direct_ops
        saved_source_name = self.source_name
        self.env["__name__"] = module_name
        self.source_name = candidate.name
        try:
            for child in module_tree.body:
                self.statement(child)
        finally:
            self.env.clear()
            self.env.update(saved_env)
            self.functions.clear()
            self.functions.update(saved_functions)
            self.direct_ops = saved_direct_ops
            self.source_name = saved_source_name

        self.count("Local modules")
        return True

    def _recognize_cyclic_history_for(self, stmt: ast.For) -> bool:
        """Recognize absolute-target cyclic DisplacementControl histories."""
        if not isinstance(stmt.target, ast.Name):
            return False

        try:
            raw_targets = list(self.eval.eval(stmt.iter))
        except (TypeError, _Unresolved):
            return False
        if len(raw_targets) < 2:
            return False
        try:
            targets = [float(value) for value in raw_targets]
        except (TypeError, ValueError):
            return False
        if any(not math.isfinite(value) for value in targets):
            return False

        integrator_call: ast.Call | None = None
        analyze_call: ast.Call | None = None
        analyze_targets: set[str] = set()
        for child in ast.walk(stmt):
            if isinstance(child, ast.Call):
                command = self.command_name(child)
                if command == "integrator":
                    if len(child.args) >= 4:
                        try:
                            integrator_kind = self.eval.eval(child.args[0])
                        except _Unresolved:
                            integrator_kind = None
                        if str(integrator_kind) == "DisplacementControl":
                            integrator_call = child
                elif command == "analyze":
                    analyze_call = child
            elif isinstance(child, ast.Assign) and isinstance(child.value, ast.Call):
                if self.command_name(child.value) == "analyze":
                    for target in child.targets:
                        analyze_targets.update(self._simple_target_names(target))

        if integrator_call is None or analyze_call is None:
            return False
        try:
            control_node = int(self.eval.eval(integrator_call.args[1]))
            control_dof = int(self.eval.eval(integrator_call.args[2]))
            analyze_args = self.call_args(analyze_call)
        except (_Unresolved, TypeError, ValueError):
            return False
        if not analyze_args or int(analyze_args[0]) != 1:
            return False

        deltas: list[float] = []
        current = 0.0
        directions: list[int] = []
        nonzero_steps = 0
        for target in targets:
            delta = target - current
            deltas.append(delta)
            if abs(delta) > 1.0e-15:
                nonzero_steps += 1
                directions.append(1 if delta > 0.0 else -1)
            current = target
        has_reversal = any(
            left != right
            for left, right in zip(directions, directions[1:])
        )
        if not has_reversal:
            return False

        max_increment = max(
            (abs(delta) for delta in deltas if abs(delta) > 1.0e-15),
            default=1.0,
        )
        self.analysis_state.update({
            "recognized_cyclic": True,
            "integrator": "DisplacementControl",
            "integrator_args": [
                control_node,
                control_dof,
                deltas[0] if deltas else 0.0,
            ],
            "control_node": control_node,
            "control_dof": control_dof,
            "cyclic_targets": targets,
            "cyclic_increment": max_increment,
            "steps": max(1, nonzero_steps),
            "recovery": False,
        })
        self.runtime_only_names.update(analyze_targets)
        self.analysis_events.append({
            "steps": max(1, nonzero_steps),
            "dt": None,
            "integrator": "DisplacementControl",
            "integrator_args": [
                control_node,
                control_dof,
                deltas[0] if deltas else 0.0,
            ],
            "analysis_kind": self.analysis_state.get(
                "analysis_kind",
                "Static",
            ),
            "pattern_tags": sorted(self.project.load_patterns),
            "current_pattern": self.current_pattern,
            "algorithm": self.analysis_state.get("algorithm"),
            "recognized_cyclic": True,
        })
        self.count("Cyclic drivers")
        self.count("Cyclic targets", len(targets))
        return True

    def _recognize_pushover_while(self, stmt: ast.While) -> bool:
        """Recognize common OpenSees displacement-control pushover loops."""
        if self.analysis_state.get("integrator") != "DisplacementControl":
            return False

        displacement_name: str | None = None
        control_node: int | None = None
        control_dof: int | None = None
        runtime_targets: set[str] = set()

        for child in ast.walk(stmt):
            if not isinstance(child, ast.Assign):
                continue
            if not isinstance(child.value, ast.Call):
                continue
            runtime_name = self._runtime_call_name(child.value)
            if runtime_name == "nodeDisp":
                args = self.call_args(child.value)
                if len(args) >= 2:
                    for target in child.targets:
                        if isinstance(target, ast.Name):
                            displacement_name = target.id
                            runtime_targets.add(target.id)
                            control_node = int(args[0])
                            control_dof = int(args[1])
            if self.command_name(child.value) == "analyze":
                for target in child.targets:
                    if isinstance(target, ast.Name):
                        runtime_targets.add(target.id)

        if (
            displacement_name is None
            or control_node is None
            or control_dof is None
        ):
            return False

        has_analyze = any(
            isinstance(child, ast.Call)
            and self.command_name(child) == "analyze"
            for child in ast.walk(stmt)
        )
        if not has_analyze:
            return False

        limit: float | None = None
        for child in ast.walk(stmt.test):
            if not isinstance(child, ast.Compare):
                continue
            if (
                isinstance(child.left, ast.Name)
                and child.left.id == displacement_name
                and len(child.ops) == 1
                and isinstance(child.ops[0], (ast.Lt, ast.LtE))
                and len(child.comparators) == 1
            ):
                try:
                    limit = float(self.eval.eval(child.comparators[0]))
                except (TypeError, ValueError, _Unresolved):
                    limit = None
                if limit is not None:
                    break

        values = list(self.analysis_state.get("integrator_args", []))
        if len(values) < 3 or limit is None:
            return False
        increment = float(values[2])
        if abs(increment) <= 1.0e-30:
            return False

        current = float(self.env.get(displacement_name, 0.0) or 0.0)
        travel = limit - current
        if travel * increment <= 0.0:
            return False
        steps = max(
            1,
            int(math.ceil(abs(travel / increment) - 1.0e-12)),
        )

        self.analysis_state.update({
            "recognized_pushover": True,
            "steps": steps,
            "control_node": control_node,
            "control_dof": control_dof,
            "displacement_increment": increment,
            "pushover_max_displacement": limit,
            "recovery": False,
        })
        self.runtime_only_names.update(runtime_targets)
        self.analysis_events.append({
            "steps": steps,
            "dt": None,
            "integrator": "DisplacementControl",
            "integrator_args": list(values),
            "analysis_kind": self.analysis_state.get(
                "analysis_kind",
                "Static",
            ),
            "pattern_tags": sorted(self.project.load_patterns),
            "current_pattern": self.current_pattern,
            "algorithm": self.analysis_state.get("algorithm"),
            "recognized_pushover": True,
        })
        self.count("Pushover drivers")
        return True

    def _statement_budget_available(self, stmt: ast.stmt) -> bool:
        if self._statement_steps >= self.MAX_STATEMENT_STEPS:
            if self._statement_steps == self.MAX_STATEMENT_STEPS:
                self.issue(
                    "UNSUPPORTED",
                    stmt,
                    "safe import limit",
                    "Safe import exceeded the 100,000-statement limit.",
                )
            self._statement_steps += 1
            return False
        self._statement_steps += 1
        return True

    def statement(self, stmt: ast.stmt) -> None:
        if not self._statement_budget_available(stmt):
            return

        if isinstance(stmt, ast.Import):
            for alias in stmt.names:
                if alias.name == "openseespy.opensees":
                    self.ops_aliases.add(alias.asname or "ops")
                    continue
                self._import_local_module(alias.name, stmt)
            return

        if isinstance(stmt, ast.ImportFrom):
            if stmt.module == "openseespy.opensees":
                if any(alias.name == "*" for alias in stmt.names):
                    self.direct_ops = True
            return

        if isinstance(stmt, ast.Assign):
            if self._recognize_eigen_frequency_assignment(stmt):
                return
            runtime_calls = self._runtime_calls_in(stmt.value)
            if runtime_calls:
                target_names: set[str] = set()
                for target in stmt.targets:
                    target_names.update(self._simple_target_names(target))
                self.runtime_only_names.update(target_names)
                self.issue(
                    "WARNING",
                    stmt,
                    "runtime value",
                    "Skipped runtime-only value from "
                    + ", ".join(sorted(set(runtime_calls)))
                    + "; model reconstruction continues.",
                )
                return
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
                        "WARNING",
                        stmt,
                        "assignment",
                        "Assignment could not be resolved safely.",
                    )
            return

        if isinstance(stmt, ast.AnnAssign):
            if stmt.value is None:
                return
            try:
                self.assign(stmt.target, self.eval.eval(stmt.value))
            except _Unresolved:
                self.issue(
                    "WARNING",
                    stmt,
                    "annotated assignment",
                    "Annotated assignment could not be resolved safely.",
                )
            return

        if isinstance(stmt, ast.AugAssign):
            if not isinstance(stmt.target, ast.Name):
                self.issue(
                    "UNSUPPORTED",
                    stmt,
                    "augmented assignment",
                    "Only simple-name augmented assignments are supported.",
                )
                return
            try:
                if stmt.target.id not in self.env:
                    raise _Unresolved(stmt.target.id)
                value = _SafeEvaluator._binary(
                    stmt.op,
                    self.env[stmt.target.id],
                    self.eval.eval(stmt.value),
                )
                self.assign(stmt.target, value)
            except _Unresolved:
                self.issue(
                    "WARNING",
                    stmt,
                    "augmented assignment",
                    "Augmented assignment could not be resolved safely.",
                )
            return

        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
            command = self.command_name(stmt.value)
            if command is not None:
                self.handle_call(command, stmt.value)
                return

            runtime_name = self._runtime_call_name(stmt.value)
            if runtime_name is not None:
                self.issue(
                    "WARNING",
                    stmt,
                    "runtime call",
                    f"Skipped runtime-only call {runtime_name} during model import.",
                )
                return

            if (
                isinstance(stmt.value.func, ast.Attribute)
                and isinstance(stmt.value.func.value, ast.Name)
                and stmt.value.func.value.id in self.runtime_only_names
                and stmt.value.func.attr in self.RUNTIME_ONLY_METHODS
            ):
                return

            try:
                self.eval.eval(stmt.value)
            except _Unresolved as exc:
                if not self._studio_source:
                    self.issue(
                        "UNSUPPORTED",
                        stmt,
                        "function call",
                        f"Function call could not be resolved safely: {exc}.",
                    )
            except (IndexError, KeyError, TypeError, ValueError) as exc:
                self.issue("ERROR", stmt, "function call", str(exc))
            return

        if isinstance(stmt, ast.If):
            # SARE-generated scripts contain runtime-only _studio_* control
            # flow. Metadata already reconstructs those analyses, so preserve
            # the existing behavior and do not symbolically execute it.
            if self._studio_source:
                return

            runtime_dependencies = {
                child.id
                for child in ast.walk(stmt.test)
                if isinstance(child, ast.Name)
                and child.id in self.runtime_only_names
            }
            if runtime_dependencies:
                self.issue(
                    "WARNING",
                    stmt,
                    "runtime condition",
                    "Skipped runtime/post-processing condition depending on "
                    + ", ".join(sorted(runtime_dependencies))
                    + ".",
                )
                return

            try:
                condition = bool(self.eval.eval(stmt.test))
            except _Unresolved as exc:
                self.issue(
                    "UNSUPPORTED",
                    stmt,
                    "if",
                    f"If condition could not be resolved safely: {exc}.",
                )
                return
            branch = stmt.body if condition else stmt.orelse
            for child in branch:
                self.statement(child)
            return

        if isinstance(stmt, ast.For):
            if self._recognize_cyclic_history_for(stmt):
                return
            if (
                isinstance(stmt.target, ast.Name)
                and stmt.target.id.startswith("_studio_")
            ):
                return
            try:
                iterable = self.eval.eval(stmt.iter)
                iterator = iter(iterable)
            except (TypeError, _Unresolved) as exc:
                if not self._studio_source:
                    self.issue(
                        "UNSUPPORTED",
                        stmt,
                        "for loop",
                        f"Loop iterable could not be resolved safely: {exc}.",
                    )
                return

            values: list[Any] = []
            try:
                for index, value in enumerate(iterator):
                    if index >= self.MAX_LOOP_ITERATIONS:
                        self.issue(
                            "UNSUPPORTED",
                            stmt,
                            "for loop",
                            "Loop exceeds the 20,000-iteration safe import limit.",
                        )
                        return
                    values.append(value)
            except Exception as exc:
                self.issue(
                    "UNSUPPORTED",
                    stmt,
                    "for loop",
                    f"Loop iterable failed during safe expansion: {exc}.",
                )
                return

            broke = False
            for value in values:
                try:
                    self.assign(stmt.target, value)
                except _Unresolved:
                    self.issue(
                        "UNSUPPORTED",
                        stmt,
                        "for target",
                        "Loop target is not a simple resolvable variable.",
                    )
                    return
                try:
                    for child in stmt.body:
                        self.statement(child)
                except _ContinueSignal:
                    continue
                except _BreakSignal:
                    broke = True
                    break
            if not broke:
                for child in stmt.orelse:
                    self.statement(child)
            return

        if isinstance(stmt, ast.FunctionDef):
            if stmt.name.startswith("_studio_"):
                return
            if stmt.decorator_list:
                self.issue(
                    "UNSUPPORTED",
                    stmt,
                    "function definition",
                    "Decorated functions are not executed in safe import mode.",
                )
                return
            self.functions[stmt.name] = stmt
            return

        if isinstance(stmt, ast.Return):
            value = (
                self.eval.eval(stmt.value)
                if stmt.value is not None
                else None
            )
            raise _ReturnSignal(value)

        if isinstance(stmt, ast.Break):
            raise _BreakSignal()

        if isinstance(stmt, ast.Continue):
            raise _ContinueSignal()

        if isinstance(stmt, ast.Pass):
            return

        if isinstance(stmt, (ast.AsyncFunctionDef, ast.ClassDef)):
            if not getattr(stmt, "name", "").startswith("_studio_"):
                self.issue(
                    "UNSUPPORTED",
                    stmt,
                    "definition",
                    "Async functions and classes are not executed in safe import mode.",
                )
            return

        if isinstance(stmt, ast.While):
            if self._recognize_pushover_while(stmt):
                return
            if not self._studio_source:
                self.issue(
                    "UNSUPPORTED",
                    stmt,
                    "While",
                    "This while loop is not a recognized bounded OpenSees "
                    "analysis driver and was not executed.",
                )
            return

        if isinstance(stmt, (ast.Try, ast.With)):
            if not self._studio_source:
                self.issue(
                    "UNSUPPORTED",
                    stmt,
                    type(stmt).__name__,
                    "This control-flow construct is not executed in safe import mode.",
                )
            return

    def finish_analysis(self) -> None:
        meta = dict(self.analysis_metadata)
        state = dict(self.analysis_state)
        if not meta and not state:
            return

        staged_displacement = False
        staged_driver_tags: list[int] = []
        staged_preload_steps = 1
        staged_preload_algorithm = "Auto"
        final_stage_steps = max(
            1,
            int(state.get("steps", 1) or 1),
        )

        def _event_signature(event: dict[str, Any]) -> tuple[Any, ...]:
            return (
                event.get("analysis_kind"),
                event.get("integrator"),
                tuple(event.get("integrator_args", [])),
                tuple(int(tag) for tag in event.get("pattern_tags", [])),
            )

        if not meta and self.analysis_events:
            final_event = self.analysis_events[-1]
            final_signature = _event_signature(final_event)
            final_start = len(self.analysis_events) - 1
            while (
                final_start > 0
                and _event_signature(self.analysis_events[final_start - 1])
                == final_signature
            ):
                final_start -= 1
            final_stage_steps = sum(
                max(1, int(event.get("steps", 1) or 1))
                for event in self.analysis_events[final_start:]
            )

            if (
                final_start > 0
                and state.get("integrator") == "DisplacementControl"
            ):
                prior_event = self.analysis_events[final_start - 1]
                prior_signature = _event_signature(prior_event)
                prior_start = final_start - 1
                while (
                    prior_start > 0
                    and _event_signature(self.analysis_events[prior_start - 1])
                    == prior_signature
                ):
                    prior_start -= 1

                prior_patterns = {
                    int(tag)
                    for tag in prior_event.get("pattern_tags", [])
                }
                final_patterns = {
                    int(tag)
                    for tag in final_event.get("pattern_tags", [])
                }
                new_patterns = sorted(final_patterns - prior_patterns)
                if prior_patterns and new_patterns:
                    staged_displacement = True
                    staged_driver_tags = new_patterns
                    staged_preload_steps = sum(
                        max(1, int(event.get("steps", 1) or 1))
                        for event in self.analysis_events[
                            prior_start:final_start
                        ]
                    )
                    staged_preload_algorithm = str(
                        prior_event.get("algorithm") or "Auto"
                    )

        analysis_type = str(meta.get("type", ""))
        analysis_type_hint = str(
            state.get(
                "analysis_type_hint",
                self.env.get(
                    "AnalysisType",
                    self.env.get("analysisType", ""),
                ),
            )
            or ""
        ).strip()
        if not analysis_type:
            if state.get("recognized_cyclic"):
                analysis_type = "Cyclic"
            elif (
                state.get("recognized_pushover")
                or analysis_type_hint.lower() == "pushover"
            ):
                analysis_type = "Pushover"
            elif state.get("modal"):
                analysis_type = "Modal"
            elif state.get("analysis_kind") == "Transient":
                analysis_type = "Transient"
            elif state.get("integrator") == "DisplacementControl":
                analysis_type = (
                    "Static"
                    if staged_displacement
                    else "Pushover"
                )
            else:
                analysis_type = "Static"

        kwargs: dict[str, Any] = {
            "tag": int(meta.get("tag", 1) or 1),
            "name": str(meta.get("name", "Imported Analysis")),
            "analysis_type": analysis_type,
            "integrator": str(
                meta.get(
                    "integrator",
                    state.get("integrator", "Auto"),
                )
            ),
            "constraints_handler": str(
                meta.get(
                    "constraints_handler",
                    state.get("constraints", "Transformation"),
                )
            ),
            "numberer": str(meta.get("numberer", state.get("numberer", "RCM"))),
            "system": str(meta.get("system", state.get("system", "UmfPack"))),
            "system_pivoting": bool(
                meta.get(
                    "system_pivoting",
                    state.get("system_pivoting", False),
                )
            ),
            "test": str(meta.get("test", state.get("test", "NormDispIncr"))),
            "tolerance": float(
                meta.get("tolerance", state.get("tolerance", 1e-8))
            ),
            "max_iterations": int(
                meta.get(
                    "max_iterations",
                    state.get("max_iterations", 50),
                )
            ),
            "algorithm": str(
                meta.get("algorithm", state.get("algorithm", "Newton"))
            ),
            "algorithm_initial": bool(
                meta.get(
                    "algorithm_initial",
                    state.get("algorithm_initial", False),
                )
            ),
            "steps": max(
                1,
                int(
                    meta.get(
                        "steps",
                        final_stage_steps,
                    )
                    or 1
                ),
            ),
            "load_increment": float(meta.get("load_increment", 0.1)),
            "control_node": int(
                meta.get(
                    "control_node",
                    state.get(
                        "control_node",
                        min(self.project.model.nodes, default=1),
                    ),
                )
                or 1
            ),
            "control_dof": int(
                meta.get(
                    "control_dof",
                    state.get("control_dof", 1),
                )
                or 1
            ),
            "displacement_increment": float(
                meta.get(
                    "displacement_increment",
                    state.get("displacement_increment", 0.001),
                )
            ),
            "cyclic_increment": float(
                meta.get(
                    "cyclic_increment",
                    state.get("cyclic_increment", 0.001),
                )
            ),
            "dt": float(meta.get("dt", state.get("dt", 0.01)) or 0.01),
            "gamma": float(meta.get("gamma", 0.5)),
            "beta": float(meta.get("beta", 0.25)),
            "rayleigh_damping_ratio": float(
                meta.get(
                    "rayleigh_damping_ratio",
                    state.get("rayleigh_damping_ratio", 0.0),
                )
            ),
            "rayleigh_model": str(
                meta.get(
                    "rayleigh_model",
                    state.get("rayleigh_model", "TwoMode"),
                )
            ),
            "rayleigh_mode_i": int(
                meta.get("rayleigh_mode_i", state.get("rayleigh_mode_i", 1))
            ),
            "rayleigh_mode_j": int(
                meta.get("rayleigh_mode_j", state.get("rayleigh_mode_j", 3))
            ),
            "preload_gravity": bool(
                meta.get(
                    "preload_gravity",
                    staged_displacement,
                )
            ),
            "gravity_steps": int(
                meta.get(
                    "gravity_steps",
                    staged_preload_steps if staged_displacement else 10,
                )
            ),
            "gravity_algorithm": str(
                meta.get(
                    "gravity_algorithm",
                    (
                        staged_preload_algorithm
                        if staged_displacement
                        else "Auto"
                    ),
                )
            ),
            "deferred_pattern_tags": [
                int(value)
                for value in meta.get(
                    "deferred_pattern_tags",
                    staged_driver_tags if staged_displacement else [],
                )
            ],
            "num_modes": int(meta.get("num_modes", state.get("num_modes", 1))),
            "eigen_solver": str(
                meta.get(
                    "eigen_solver",
                    state.get("eigen_solver", "-genBandArpack"),
                )
            ),
            "recovery": bool(
                meta.get("recovery", state.get("recovery", True))
            ),
            "adaptive_step": bool(meta.get("adaptive_step", False)),
            "adaptive_cutback_factor": float(
                meta.get("adaptive_cutback_factor", 0.5)
            ),
            "adaptive_min_factor": float(
                meta.get("adaptive_min_factor", 0.125)
            ),
            "adaptive_growth_factor": float(
                meta.get("adaptive_growth_factor", 1.5)
            ),
            "adaptive_easy_iterations": int(
                meta.get("adaptive_easy_iterations", 4)
            ),
            "adaptive_growth_after": int(
                meta.get("adaptive_growth_after", 3)
            ),
            "live_convergence": bool(meta.get("live_convergence", False)),
        }

        integrator = state.get("integrator")
        values = list(state.get("integrator_args", []))
        if analysis_type == "Static" and integrator == "LoadControl" and values:
            if "load_increment" not in meta:
                kwargs["load_increment"] = float(values[0])
        elif (
            analysis_type in {"Static", "Pushover"}
            and integrator == "DisplacementControl"
        ):
            if len(values) >= 3:
                if "control_node" not in meta:
                    kwargs["control_node"] = int(values[0])
                if "control_dof" not in meta:
                    kwargs["control_dof"] = int(values[1])
                if "displacement_increment" not in meta:
                    kwargs["displacement_increment"] = float(values[2])
        elif analysis_type == "Cyclic":
            cyclic_targets = meta.get(
                "cyclic_targets",
                state.get("cyclic_targets"),
            )
            if cyclic_targets:
                kwargs["cyclic_targets"] = [
                    float(value) for value in cyclic_targets
                ]
        elif analysis_type == "Transient":
            if integrator == "Newmark" and len(values) >= 2:
                if "gamma" not in meta:
                    kwargs["gamma"] = float(values[0])
                if "beta" not in meta:
                    kwargs["beta"] = float(values[1])

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
    source_path: str | Path | None = None,
) -> OpenSeesImportResult:
    """Parse OpenSeesPy source without executing arbitrary Python.

    With source_path, simple sibling-module imports may be reconstructed from
    Python files in the same directory. Relative Path time-series -filePath
    inputs within that directory tree may also be read as numeric data. Python
    source is parsed by the same restricted AST interpreter and is never
    executed through exec.
    """
    return _Importer(
        source,
        source_name,
        units,
        source_path=source_path,
    ).run()
