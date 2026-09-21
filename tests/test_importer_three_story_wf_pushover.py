from __future__ import annotations

import math

from openseespy_studio.generator import to_openseespy
from openseespy_studio.importer import import_openseespy_source


THREE_STORY_WF_PUSHOVER = r"""
print("Start 2D Steel Frame Example")
from openseespy.opensees import *
import numpy as np
import matplotlib.pyplot as plt
import os

AnalysisType='Pushover'
wipe()
model('basic', '-ndm', 2, '-ndf', 3)
import math

inch = 1
kip = 1
sec = 1
sq_in = inch*inch
ksi = kip/sq_in
ft = 12*inch
g = 386.2*inch/(sec*sec)
pi = math.acos(-1)

H_story=10.0*ft
W_bayX=16.0*ft

matTag=1
Fy=60.0*ksi
Es=29000.0*ksi
v=0.2
Gs=Es/(1+v)
b=0.10
R0=18.0
cR1=0.925
cR2=0.15
a1=0.05
a2=1.00
a3=0.05
a4=1.0
sigInit=0.0
uniaxialMaterial(
    'Steel02', matTag, Fy, Es, b, R0, cR1, cR2,
    a1, a2, a3, a4, sigInit
)

colSecTag1=1
colSecTag2=2
beamSecTag1=3
beamSecTag2=4
beamSecTag3=5
section('WFSection2d', colSecTag1, matTag, 10.5*inch, 0.26*inch, 5.77*inch, 0.44*inch, 15, 16)
section('WFSection2d', colSecTag2, matTag, 10.5*inch, 0.26*inch, 5.77*inch, 0.44*inch, 15, 16)
section('WFSection2d', beamSecTag1, matTag, 8.3*inch, 0.44*inch, 8.11*inch, 0.685*inch, 15, 15)
section('WFSection2d', beamSecTag2, matTag, 8.2*inch, 0.40*inch, 8.01*inch, 0.650*inch, 15, 15)
section('WFSection2d', beamSecTag3, matTag, 8.0*inch, 0.40*inch, 7.89*inch, 0.600*inch, 15, 15)

node(1, 0.0, 0.0)
node(2, W_bayX, 0.0)
node(3, 2*W_bayX, 0.0)
node(11, 0.0, H_story)
node(12, W_bayX, H_story)
node(13, 2*W_bayX, H_story)
node(21, 0.0, 2*H_story)
node(22, W_bayX, 2*H_story)
node(23, 2*W_bayX, 2*H_story)
node(31, 0.0, 3*H_story)
node(32, W_bayX, 3*H_story)
node(33, 2*W_bayX, 3*H_story)
node(1101, 0.0, H_story)
node(1201, W_bayX, H_story)
node(1202, W_bayX, H_story)
node(1301, 2*W_bayX, H_story)
node(2101, 0.0, 2*H_story)
node(2201, W_bayX, 2*H_story)
node(2202, W_bayX, 2*H_story)
node(2301, 2*W_bayX, 2*H_story)
node(3101, 0.0, 3*H_story)
node(3201, W_bayX, 3*H_story)
node(3202, W_bayX, 3*H_story)
node(3301, 2*W_bayX, 3*H_story)

fix(1, 1, 1, 1)
fix(2, 1, 1, 1)
fix(3, 1, 1, 1)

ColIntTag1=1
ColIntTag2=2
BeamIntTag1=3
BeamIntTag2=4
BeamIntTag3=5
beamIntegration('Lobatto', ColIntTag1, colSecTag1, 4)
beamIntegration('Lobatto', ColIntTag2, colSecTag2, 4)
beamIntegration('Lobatto', BeamIntTag1, beamSecTag1, 4)
beamIntegration('Lobatto', BeamIntTag2, beamSecTag2, 4)
beamIntegration('Lobatto', BeamIntTag3, beamSecTag3, 4)

ColTransfTag=1
BeamTranfTag=2
geomTransf('PDelta', ColTransfTag)
geomTransf('Linear', BeamTranfTag)

element('forceBeamColumn', 1, 1, 11, ColTransfTag, ColIntTag1, '-mass', 0.0)
element('forceBeamColumn', 2, 2, 12, ColTransfTag, ColIntTag2, '-mass', 0.0)
element('forceBeamColumn', 3, 3, 13, ColTransfTag, ColIntTag1, '-mass', 0.0)
element('forceBeamColumn', 11, 11, 21, ColTransfTag, ColIntTag1, '-mass', 0.0)
element('forceBeamColumn', 12, 12, 22, ColTransfTag, ColIntTag2, '-mass', 0.0)
element('forceBeamColumn', 13, 13, 23, ColTransfTag, ColIntTag1, '-mass', 0.0)
element('forceBeamColumn', 21, 21, 31, ColTransfTag, ColIntTag1, '-mass', 0.0)
element('forceBeamColumn', 22, 22, 32, ColTransfTag, ColIntTag2, '-mass', 0.0)
element('forceBeamColumn', 23, 23, 33, ColTransfTag, ColIntTag1, '-mass', 0.0)
element('forceBeamColumn', 101, 1101, 1201, BeamTranfTag, BeamIntTag1, '-mass', 0.0)
element('forceBeamColumn', 102, 1202, 1301, BeamTranfTag, BeamIntTag1, '-mass', 0.0)
element('forceBeamColumn', 201, 2101, 2201, BeamTranfTag, BeamIntTag2, '-mass', 0.0)
element('forceBeamColumn', 202, 2202, 2301, BeamTranfTag, BeamIntTag2, '-mass', 0.0)
element('forceBeamColumn', 301, 3101, 3201, BeamTranfTag, BeamIntTag3, '-mass', 0.0)
element('forceBeamColumn', 302, 3202, 3301, BeamTranfTag, BeamIntTag3, '-mass', 0.0)

equalDOF(11, 1101, 1,2,3)
equalDOF(12, 1201, 1,2,3)
equalDOF(12, 1202, 1,2,3)
equalDOF(13, 1301, 1,2,3)
equalDOF(21, 2101, 1,2,3)
equalDOF(22, 2201, 1,2,3)
equalDOF(22, 2202, 1,2,3)
equalDOF(23, 2301, 1,2,3)
equalDOF(31, 3101, 1,2,3)
equalDOF(32, 3201, 1,2,3)
equalDOF(32, 3202, 1,2,3)
equalDOF(33, 3301, 1,2,3)

timeSeries("Linear", 1)
pattern("Plain", 1, 1)
load(11, 0.0, -5.0*kip, 0.0)
load(12, 0.0, -6.0*kip, 0.0)
load(13, 0.0, -5.0*kip, 0.0)
load(21, 0., -5.*kip, 0.0)
load(22, 0., -6.*kip,0.0)
load(23, 0., -5.*kip, 0.0)
load(31, 0., -5.*kip, 0.0)
load(32, 0., -6.*kip, 0.0)
load(33, 0., -5.*kip, 0.0)

NstepsGrav = 10
system("BandGEN")
numberer("Plain")
constraints("Plain")
integrator("LoadControl", 1.0/NstepsGrav)
algorithm("Newton")
test('NormUnbalance',1e-8, 10)
analysis("Static")
data = np.zeros((NstepsGrav+1,2))
for j in range(NstepsGrav):
    analyze(1)
    data[j+1,0] = nodeDisp(31,2)
    data[j+1,1] = getLoadFactor(1)*5

loadConst('-time', 0.0)
wipeAnalysis()

if AnalysisType=="Pushover":
    pattern("Plain", 2, 1)
    load(11, 1.61, 0.0, 0.0)
    load(21, 3.22, 0.0, 0.0)
    load(31, 4.83, 0.0, 0.0)

    ControlNode=31
    ControlDOF=1
    MaxDisp=0.15*H_story
    DispIncr=0.1
    NstepsPush=int(MaxDisp/DispIncr)

    system("ProfileSPD")
    numberer("Plain")
    constraints("Plain")
    integrator("DisplacementControl", ControlNode, ControlDOF, DispIncr)
    algorithm("Newton")
    test('NormUnbalance',1e-8, 10)
    analysis("Static")

    PushDataDir = r'PushoverOut'
    if not os.path.exists(PushDataDir):
        os.makedirs(PushDataDir)
    recorder('Node', '-file', "PushoverOut/Node2React.out", '-closeOnWrite', '-node', 2, '-dof',1, 'reaction')
    recorder('Node', '-file', "PushoverOut/Node31Disp.out", '-closeOnWrite', '-node', 31, '-dof',1, 'disp')
    recorder('Element', '-file', "PushoverOut/BeamStress.out", '-closeOnWrite', '-ele', 102, 'section', '4', 'fiber','1', 'stressStrain')

    dataPush = np.zeros((NstepsPush+1,5))
    for j in range(NstepsPush):
        analyze(1)
        dataPush[j+1,0] = nodeDisp(31,1)
        reactions()
        dataPush[j+1,1] = nodeReaction(1, 1) + nodeReaction(2, 1) + nodeReaction(3, 1)

    plt.plot(dataPush[:,0], -dataPush[:,1])
    plt.xlim(0, MaxDisp)
    plt.show()
"""


def _import_example():
    return import_openseespy_source(
        THREE_STORY_WF_PUSHOVER,
        source_name="ThreeStorySteel.py",
        units={"length": "in", "force": "kip", "time": "s"},
    )


def test_three_story_wf_pushover_imports_model_sections_and_analysis():
    result = _import_example()

    assert result.error_count == 0
    assert result.project.model.ndm == 2
    assert result.project.model.ndf == 3
    assert len(result.project.model.nodes) == 24
    assert len(result.project.model.elements) == 15
    assert len(result.project.constraints) == 12
    assert len(result.project.materials) == 1
    assert len(result.project.sections) == 5
    assert result.imported_counts["WF sections"] == 5
    assert len(result.project.load_patterns) == 2
    assert len(result.project.nodal_loads) == 12
    assert len(result.project.recorders) == 3

    steel = result.project.materials[1]
    units = result.project.units
    assert steel.material_type == "Steel02"
    # Internal storage is SI, but the imported OpenSees values are 60/29000 ksi.
    from openseespy_studio.units import UnitSystem
    unit_system = UnitSystem.from_mapping(units)
    assert math.isclose(
        unit_system.engineering_stress_from_pa(steel.parameters["Fy"]),
        60.0,
        rel_tol=1.0e-12,
    )
    assert math.isclose(
        unit_system.engineering_stress_from_pa(steel.parameters["E0"]),
        29000.0,
        rel_tol=1.0e-12,
    )

    col = result.project.sections[1]
    assert col.section_type == "Fiber"
    assert col.display_geometry["shape"] == "WideFlange"
    assert col.display_geometry["dimensions"]["d"] == 10.5
    assert col.display_geometry["dimensions"]["tw"] == 0.26
    assert col.display_geometry["dimensions"]["bf"] == 5.77
    assert col.display_geometry["dimensions"]["tf"] == 0.44
    fibers = col.compiled_fibers()
    assert len(fibers) == 15 + 2 * 16
    expected_area = 2.0 * 5.77 * 0.44 + (10.5 - 2.0 * 0.44) * 0.26
    assert math.isclose(
        sum(fiber.area for fiber in fibers),
        expected_area,
        rel_tol=1.0e-12,
    )
    area, centroid = col.fiber_area_and_centroid()
    assert math.isclose(area, expected_area, rel_tol=1.0e-12)
    assert math.isclose(centroid[0], 0.0, abs_tol=1.0e-12)
    assert math.isclose(centroid[1], 0.0, abs_tol=1.0e-12)

    analysis = result.project.analyses[result.project.active_analysis_tag]
    assert analysis.analysis_type == "Pushover"
    assert analysis.preload_gravity is True
    assert analysis.gravity_steps == 10
    assert analysis.deferred_pattern_tags == [2]
    assert analysis.steps == 180
    assert analysis.control_node == 31
    assert analysis.control_dof == 1
    assert analysis.displacement_increment == 0.1
    assert analysis.system == "ProfileSPD"
    assert analysis.numberer == "Plain"
    assert analysis.constraints_handler == "Plain"
    assert analysis.algorithm == "Newton"
    assert analysis.test == "NormUnbalance"
    assert math.isclose(analysis.tolerance, 1.0e-8)

    fiber_recorder = result.project.recorders[3]
    assert fiber_recorder.recorder_type == "Fiber"
    assert fiber_recorder.target_tags == [102]
    assert fiber_recorder.section_number == 4
    assert fiber_recorder.fiber_index == 1
    assert fiber_recorder.response == "stressStrain"


def test_three_story_wf_pushover_round_trip_generates_native_fiber_model():
    result = _import_example()
    project = result.project
    regenerated = to_openseespy(
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
        element_loads=project.element_loads,
        prescribed_displacements=project.prescribed_displacements,
        recorders=project.recorders,
        units=project.units,
    )

    assert "ops.section('Fiber', 1" in regenerated
    assert "ops.patch('rect', 1, 16, 1" in regenerated
    assert "ops.patch('rect', 1, 15, 1" in regenerated
    assert "WFSection2d" not in regenerated
    assert "ops.integrator('DisplacementControl', 31, 1, 0.1)" in regenerated
    assert "_studio_gravity_ok = ops.analyze(10)" in regenerated
    assert "'section', 4, 'fiber', 1, 'stressStrain'" in regenerated
    compile(regenerated, "<three-story-wf-roundtrip>", "exec")
