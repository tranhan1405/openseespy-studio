from __future__ import annotations

import math

from openseespy_studio.generator import (
    cyclic_displacement_steps,
    to_openseespy,
)
from openseespy_studio.importer import import_openseespy_source
from openseespy_studio.units import UnitSystem


FRP_CYCLIC = r"""
from openseespy.opensees import *

wipe()
model("basic", "-ndm", 2, "-ndf", 3)

uniaxialMaterial(
    "FRPConfinedConcrete", 1,
    27.5, 27.5, 0.002, 400., 35., 266000.,
    0.0, 0.222, 0.0163, 150., 374., 363.,
    16., 6., 200000., 0.2, 0.8, 1.
)
uniaxialMaterial("Elastic", 2, 30849000000.)
uniaxialMaterial("Steel02", 3, 374., 200000., 0., 1., 0.01, 0.01)

section("Fiber", 1)
patch("circ", 1, 20, 20, *[0., 0.], *[0., 200.], *[0., 360.])
patch("circ", 3, 10, 10, *[0., 157.], *[0., 8.], *[0., 360.])

node(1, *[0., 0.])
node(2, *[0., 0.])
node(3, *[0., 200.])
node(4, *[0., 1350.])
geomTransf("Linear", 1)
element("zeroLength", 1, *[1, 2], "-mat", 2, "-dir", 6)
beamIntegration("Legendre", 1, 1, 4)
element("dispBeamColumn", 2, 2, 3, 1, 1)
element(
    "elasticBeamColumn", 3, *[3, 4],
    125663.706143592, 31540., 1290800000., 1
)
fix(1, *[1, 1, 1])
equalDOF(1, 2, *[1, 2])

timeSeries("Linear", 1)
pattern("Plain", 1, 1)
load(4, *[0.0, -185000., 0.0])
integrator("LoadControl", 0.1)
system("SparseGeneral", "-piv")
test("NormUnbalance", 1.0e-6, 1000, 4)
numberer("Plain")
constraints("Plain")
algorithm("Newton")
analysis("Static")
analyze(10)
loadConst("-time", 0.0)

Hload = 1.
ControlNodeID = [4]
ControlDOFID = 1
timeSeries("Linear", 2)
pattern("Plain", 200, 2)
for ControlNode in ControlNodeID:
    load(ControlNode, *[Hload, 0.0, 0.0])

DisplacementStep = [
    -0.3090,
    -0.3541,
    -0.5368,
    -0.1000,
    0.2500,
    0.1000,
    -0.2000,
]

system("SparseGeneral", "-piv")
test("NormUnbalance", 1.0e-6, 1000, 4)
numberer("Plain")
constraints("Plain")
algorithm("NewtonLineSearch")
analysis("Static")

D0 = 0.0
for Dstep in DisplacementStep:
    D1 = Dstep
    Dincr = D1-D0
    integrator(
        "DisplacementControl",
        ControlNodeID[0],
        ControlDOFID,
        Dincr,
    )
    analysis("Static")
    ok = analyze(1)
    D0 = D1
    if ok != 0:
        print("Analysis failed")
"""


def test_frp_confined_cyclic_history_imports_as_cyclic_analysis():
    result = import_openseespy_source(
        FRP_CYCLIC,
        source_name="FRPColumnCyclic.py",
        units={"length": "mm", "force": "N", "time": "s"},
    )

    assert result.error_count == 0
    assert result.imported_counts["Cyclic drivers"] == 1
    assert result.imported_counts["Cyclic targets"] == 7
    assert result.project.model.ndm == 2
    assert result.project.model.ndf == 3
    assert len(result.project.model.nodes) == 4
    assert len(result.project.model.elements) == 2
    assert len(result.project.connections) == 1
    connection = result.project.connections[1]
    assert connection.connection_type == "zeroLength"
    assert connection.node_i == 1
    assert connection.node_j == 2
    assert len(result.project.materials) == 3
    assert len(result.project.sections) == 2  # Fiber + inline Elastic beam section
    assert len(result.project.load_patterns) == 2
    assert len(result.project.nodal_loads) == 2

    material = result.project.materials[1]
    assert material.material_type == "FRPConfinedConcrete"
    units = UnitSystem.from_mapping(result.project.units)
    p = material.parameters
    assert math.isclose(units.engineering_stress_from_pa(p["fpc1"]), 27.5)
    assert math.isclose(units.engineering_stress_from_pa(p["Ej"]), 266000.0)
    assert math.isclose(units.length_from_m(p["D"]), 400.0)
    assert math.isclose(units.length_from_m(p["tj"]), 0.222)
    assert p["useBuck"] == 1.0

    analysis = result.project.analyses[result.project.active_analysis_tag]
    assert analysis.analysis_type == "Cyclic"
    assert analysis.preload_gravity is True
    assert analysis.gravity_steps == 10
    assert analysis.gravity_algorithm == "Newton"
    assert analysis.deferred_pattern_tags == [200]
    assert analysis.control_node == 4
    assert analysis.control_dof == 1
    assert analysis.system == "SparseGeneral"
    assert analysis.system_pivoting is True
    assert analysis.algorithm == "NewtonLineSearch"
    assert analysis.test == "NormUnbalance"
    assert analysis.max_iterations == 1000
    assert analysis.recovery is False
    assert analysis.cyclic_targets == [
        -0.3090, -0.3541, -0.5368, -0.1000, 0.2500, 0.1000, -0.2000
    ]

    deltas = []
    current = 0.0
    for target in analysis.cyclic_targets:
        deltas.append(target-current)
        current = target
    assert analysis.cyclic_increment == max(abs(value) for value in deltas)
    assert cyclic_displacement_steps(
        analysis.cyclic_targets,
        analysis.cyclic_increment,
    ) == deltas


def test_frp_confined_cyclic_round_trip_preserves_material_and_protocol():
    result = import_openseespy_source(
        FRP_CYCLIC,
        source_name="FRPColumnCyclic.py",
        units={"length": "mm", "force": "N", "time": "s"},
    )
    project = result.project
    script = to_openseespy(
        project.model,
        materials=project.materials,
        sections=project.sections,
        transformations=project.transformations,
        constraints=project.constraints,
        connections=project.connections,
        time_series=project.time_series,
        load_patterns=project.load_patterns,
        nodal_loads=project.nodal_loads,
        analyses=project.analyses,
        active_analysis_tag=project.active_analysis_tag,
        recorders=project.recorders,
        units=project.units,
    )

    assert (
        "ops.uniaxialMaterial('FRPConfinedConcrete', 1, "
        "27.5, 27.5, 0.002, 400, 35, 266000, 0, 0.222, "
        "0.0163, 150, 374, 363, 16, 6, 200000, 0.2, 0.8, 1)"
        in script
    )
    assert "ops.system('SparseGeneral', '-piv')" in script
    assert "_studio_cyclic_increments =" in script
    assert "ops.integrator('DisplacementControl', 4, 1" in script
    assert "ops.algorithm('Newton')" in script
    assert "_studio_gravity_ok = ops.analyze(10)" in script
    compile(script, "<frp-cyclic-roundtrip>", "exec")
