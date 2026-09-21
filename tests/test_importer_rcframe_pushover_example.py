from pathlib import Path

from openseespy_studio.generator import to_openseespy
from openseespy_studio.importer import import_openseespy_source


GRAVITY = r"""
from openseespy.opensees import *
model('basic', '-ndm', 2, '-ndf', 3)
width = 360.0
height = 144.0
node(1, 0.0, 0.0)
node(2, width, 0.0)
node(3, 0.0, height)
node(4, width, height)
fix(1, 1, 1, 1)
fix(2, 1, 1, 1)
uniaxialMaterial('Concrete01', 1, -6.0, -0.004, -5.0, -0.014)
uniaxialMaterial('Concrete01', 2, -5.0, -0.002, 0.0, -0.006)
fy = 60.0
E = 30000.0
uniaxialMaterial('Steel01', 3, fy, E, 0.01)
colWidth = 15
colDepth = 24
cover = 1.5
As = 0.60
y1 = colDepth / 2.0
z1 = colWidth / 2.0
section('Fiber', 1)
patch('rect', 1, 10, 1, cover-y1, cover-z1, y1-cover, z1-cover)
patch('rect', 2, 10, 1, -y1, z1-cover, y1, z1)
patch('rect', 2, 10, 1, -y1, -z1, y1, cover-z1)
patch('rect', 2, 2, 1, -y1, cover-z1, cover-y1, z1-cover)
patch('rect', 2, 2, 1, y1-cover, cover-z1, y1, z1-cover)
layer('straight', 3, 3, As, y1-cover, z1-cover, y1-cover, cover-z1)
layer('straight', 3, 2, As, 0.0, z1-cover, 0.0, cover-z1)
layer('straight', 3, 3, As, cover-y1, z1-cover, cover-y1, cover-z1)
geomTransf('PDelta', 1)
np = 5
beamIntegration('Lobatto', 1, 1, np)
eleType = 'forceBeamColumn'
element(eleType, 1, 1, 3, 1, 1)
element(eleType, 2, 2, 4, 1, 1)
geomTransf('Linear', 2)
element('elasticBeamColumn', 3, 3, 4, 360.0, 4030.0, 8640.0, 2)
P = 180.0
timeSeries('Linear', 1)
pattern('Plain', 1, 1)
load(3, 0.0, -P, 0.0)
load(4, 0.0, -P, 0.0)
system('BandGeneral')
constraints('Transformation')
numberer('RCM')
test('NormDispIncr', 1.0e-12, 10, 3)
algorithm('Newton')
integrator('LoadControl', 0.1)
analysis('Static')
analyze(10)
u3 = nodeDisp(3, 2)
results = open('results.out', 'a+')
if abs(u3 + 0.0183736) < 1e-6:
    results.write('PASSED')
results.close()
"""


PUSHOVER = r"""
from openseespy.opensees import *
wipe()
import RCFrameGravity
loadConst('-time', 0.0)
H = 10.0
pattern('Plain', 2, 1)
load(3, H, 0.0, 0.0)
load(4, H, 0.0, 0.0)
dU = 0.1
integrator('DisplacementControl', 3, 1, dU, 1, dU, dU)
maxU = 15.0
currentDisp = 0.0
ok = 0
test('NormDispIncr', 1.0e-12, 1000)
algorithm('ModifiedNewton', '-initial')
while ok == 0 and currentDisp < maxU:
    ok = analyze(1)
    if ok != 0:
        break
    currentDisp = nodeDisp(3, 1)
results = open('results.out', 'a+')
if ok == 0:
    results.write('PASSED')
else:
    results.write('FAILED')
results.close()
"""


def test_rcframe_pushover_resolves_sibling_gravity_and_while_driver(
    tmp_path: Path,
):
    gravity_path = tmp_path / "RCFrameGravity.py"
    pushover_path = tmp_path / "RCFramePushover.py"
    gravity_path.write_text(GRAVITY, encoding="utf-8")
    pushover_path.write_text(PUSHOVER, encoding="utf-8")

    result = import_openseespy_source(
        PUSHOVER,
        source_name=pushover_path.name,
        source_path=pushover_path,
        units={"length": "in", "force": "kip", "time": "s"},
    )

    assert result.error_count == 0
    assert result.unsupported_count == 0
    assert result.imported_counts["Local modules"] == 1
    assert result.imported_counts["Pushover drivers"] == 1

    assert result.project.model.ndm == 2
    assert result.project.model.ndf == 3
    assert len(result.project.model.nodes) == 4
    assert len(result.project.model.elements) == 3
    assert len(result.project.materials) == 3
    assert len(result.project.sections) == 2
    assert result.project.sections[1].section_type == "Fiber"
    assert any(
        section.section_type == "Elastic"
        for section in result.project.sections.values()
    )
    assert len(result.project.load_patterns) == 2
    assert len(result.project.nodal_loads) == 4

    analysis = result.project.analyses[result.project.active_analysis_tag]
    assert analysis.analysis_type == "Pushover"
    assert analysis.integrator == "DisplacementControl"
    assert analysis.control_node == 3
    assert analysis.control_dof == 1
    assert analysis.displacement_increment == 0.1
    assert analysis.steps == 150
    assert analysis.preload_gravity is True
    assert analysis.gravity_steps == 10
    assert analysis.deferred_pattern_tags == [2]
    assert analysis.algorithm == "ModifiedNewton"
    assert analysis.algorithm_initial is True
    assert analysis.recovery is False

    # US customary stresses are stored internally in Pa but should round-trip
    # back to the original ksi values in generated OpenSees input.
    steel = result.project.materials[3]
    assert result.project.units == {
        "length": "in",
        "force": "kip",
        "time": "s",
    }

    regenerated = to_openseespy(
        result.project.model,
        materials=result.project.materials,
        sections=result.project.sections,
        transformations=result.project.transformations,
        constraints=result.project.constraints,
        connections=result.project.connections,
        time_series=result.project.time_series,
        load_patterns=result.project.load_patterns,
        nodal_loads=result.project.nodal_loads,
        analyses=result.project.analyses,
        active_analysis_tag=result.project.active_analysis_tag,
        units=result.project.units,
    )
    assert "ops.uniaxialMaterial('Steel01', 3, 60, 30000, 0.01" in regenerated
    assert "ops.algorithm('ModifiedNewton', '-initial')" in regenerated
    assert "ops.integrator('DisplacementControl', 3, 1, 0.1)" in regenerated
    compile(regenerated, "<rcframe-pushover-roundtrip>", "exec")
