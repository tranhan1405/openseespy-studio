from openseespy_studio.importer import import_openseespy_source


def test_legacy_moment_curvature_example_imports_model_not_runtime_postcheck():
    source = r"""
from openseespy.opensees import *

def MomentCurvature(secTag, axialLoad, maxK, numIncr=100):
    node(1, 0.0, 0.0)
    node(2, 0.0, 0.0)
    fix(1, 1, 1, 1)
    fix(2, 0, 1, 0)
    element('zeroLengthSection', 1, 1, 2, secTag)

    timeSeries('Constant', 1)
    pattern('Plain', 1, 1)
    load(2, axialLoad, 0.0, 0.0)

    integrator('LoadControl', 0.0)
    system('SparseGeneral', '-piv')
    test('NormUnbalance', 1e-9, 10)
    numberer('Plain')
    constraints('Plain')
    algorithm('Newton')
    analysis('Static')
    analyze(1)

    timeSeries('Linear', 2)
    pattern('Plain', 2, 2)
    load(2, 0.0, 0.0, 1.0)

    dK = maxK / numIncr
    integrator('DisplacementControl', 2, 3, dK, 1, dK, dK)
    analyze(numIncr)

wipe()
print("Start MomentCurvature.py example")
model('basic', '-ndm', 2, '-ndf', 3)

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

d = colDepth-cover
epsy = fy/E
Ky = epsy/(0.7*d)
print("Estimated yield curvature: ", Ky)

P = -180.0
mu = 15.0
numIncr = 100
MomentCurvature(1, P, Ky*mu, numIncr)

results = open('results.out', 'a+')
u = nodeDisp(2, 3)
if abs(u-0.00190476190476190541) < 1e-12:
    results.write('PASSED : MomentCurvature.py\n')
    print("Passed!")
else:
    results.write('FAILED : MomentCurvature.py\n')
    print("Failed!")
results.close()
"""

    result = import_openseespy_source(
        source,
        source_name="MomentCurvature.py",
        units={"length": "in", "force": "kip", "time": "s"},
    )

    assert result.error_count == 0
    assert result.unsupported_count == 0
    assert result.imported_counts.get("Elements") == 1
    assert result.imported_counts.get("Connections", 0) == 0

    assert result.project.model.ndm == 2
    assert result.project.model.ndf == 3
    assert set(result.project.model.nodes) == {1, 2}
    assert result.project.model.nodes[1].xyz == (0.0, 0.0, 0.0)
    assert result.project.model.nodes[2].xyz == (0.0, 0.0, 0.0)

    assert set(result.project.materials) == {1, 2, 3}
    section = result.project.sections[1]
    assert section.section_type == "Fiber"
    assert len(section.fiber_components) == 7

    assert set(result.project.connections) == {1}
    connection = result.project.connections[1]
    assert connection.connection_type == "zeroLengthSection"
    assert connection.section_tag == 1
    assert connection.node_i == 1
    assert connection.node_j == 2

    assert set(result.project.time_series) == {1, 2}
    assert set(result.project.load_patterns) == {1, 2}
    assert len(result.project.nodal_loads) == 2

    assert len(result.project.analyses) == 1
    analysis = next(iter(result.project.analyses.values()))
    assert analysis.analysis_type == "Pushover"
    assert analysis.system == "SparseGeneral"
    assert analysis.test == "NormUnbalance"
    assert analysis.control_node == 2
    assert analysis.control_dof == 3
    assert analysis.steps == 100

    assert any(
        issue.construct == "runtime value"
        for issue in result.issues
    )
    assert any(
        issue.construct == "runtime condition"
        for issue in result.issues
    )
