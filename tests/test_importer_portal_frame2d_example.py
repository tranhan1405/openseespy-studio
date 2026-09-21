from openseespy_studio.generator import to_openseespy
from openseespy_studio.importer import import_openseespy_source


PORTAL_FRAME_2D = r"""
from openseespy.opensees import *
from math import asin, sqrt

wipe()
model('Basic', '-ndm', 2)

numBay = 2
numFloor = 7
bayWidth = 360.0
storyHeights = [162.0, 162.0, 156.0, 156.0, 156.0, 156.0, 156.0]
E = 29500.0
massX = 0.49
M = 0.
coordTransf = "Linear"
massType = "-lMass"

beams = ['W24X160', 'W24X160', 'W24X130', 'W24X130', 'W24X110', 'W24X110', 'W24X110']
eColumn = ['W14X246', 'W14X246', 'W14X246', 'W14X211', 'W14X211', 'W14X176', 'W14X176']
iColumn = ['W14X287', 'W14X287', 'W14X287', 'W14X246', 'W14X246', 'W14X211', 'W14X211']
columns = [eColumn, iColumn, eColumn]

WSection = {
    'W14X176': [51.7, 2150.],
    'W14X211': [62.1, 2670.],
    'W14X246': [72.3, 3230.],
    'W14X287': [84.4, 3910.],
    'W24X110': [32.5, 3330.],
    'W24X130': [38.3, 4020.],
    'W24X160': [47.1, 5120.]
}

nodeTag = 1

def ElasticBeamColumn(eleTag, iNode, jNode, sectType, E, transfTag, M, massType):
    found = 0
    prop = WSection[sectType]
    A = prop[0]
    I = prop[1]
    element('elasticBeamColumn', eleTag, iNode, jNode, A, E, I, transfTag, '-mass', M, massType)

yLoc = 0.
for j in range(0, numFloor + 1):
    xLoc = 0.
    for i in range(0, numBay + 1):
        node(nodeTag, xLoc, yLoc)
        xLoc += bayWidth
        nodeTag += 1
    if j < numFloor:
        storyHeight = storyHeights[j]
    yLoc += storyHeight

fix(1, 1, 1, 1)
fix(2, 1, 1, 1)
fix(3, 1, 1, 1)

nodeTagR = 5
nodeTag = 4
for j in range(1, numFloor + 1):
    for i in range(0, numBay + 1):
        if nodeTag != nodeTagR:
            equalDOF(nodeTagR, nodeTag, 1)
        else:
            mass(nodeTagR, massX, 1.0e-10, 1.0e-10)
        nodeTag += 1
    nodeTagR += numBay + 1

geomTransf(coordTransf, 1)
eleTag = 1
for j in range(0, numBay + 1):
    end1 = j + 1
    end2 = end1 + numBay + 1
    thisColumn = columns[j]
    for i in range(0, numFloor):
        secType = thisColumn[i]
        ElasticBeamColumn(eleTag, end1, end2, secType, E, 1, M, massType)
        end1 = end2
        end2 += numBay + 1
        eleTag += 1

for j in range(1, numFloor + 1):
    end1 = (numBay + 1) * j + 1
    end2 = end1 + 1
    secType = beams[j - 1]
    for i in range(0, numBay):
        ElasticBeamColumn(eleTag, end1, end2, secType, E, 1, M, massType)
        end1 = end2
        end2 = end1 + 1
        eleTag += 1

numEigen = 7
eigenValues = eigen(numEigen)
PI = 2 * asin(1.0)

timeSeries('Linear', 1)
pattern('Plain', 1, 1)
load(22, 20.0, 0., 0.)
load(19, 15.0, 0., 0.)
load(16, 12.5, 0., 0.)
load(13, 10.0, 0., 0.)
load(10, 7.5, 0., 0.)
load(7, 5.0, 0., 0.)
load(4, 2.5, 0., 0.)

integrator('LoadControl', 1.0)
algorithm('Linear')
analysis('Static')
analyze(1)

ok = 0
comparisonResults = [[1.2732, 0.4313, 0.2420, 0.1602, 0.1190, 0.0951, 0.0795],
                     [1.2732, 0.4313, 0.2420, 0.1602, 0.1190, 0.0951, 0.0795]]
print("\n\nPeriod Comparisons:")
for i in range(0, numEigen):
    lamb = eigenValues[i]
    period = 2 * PI / sqrt(lamb)
    print(i + 1, period, comparisonResults[0][i], comparisonResults[1][i])

comparisonResults = [["Disp Top", "Axial Force Bottom Left", "Moment Bottom Left"],
                     [1.45076, 69.99, 2324.68],
                     [1.451, 70.01, 2324.71]]
tolerances = [9.99e-6, 9.99e-3, 9.99e-3]
for i in range(3):
    response = eleResponse(1, 'forces')
    if i == 0:
        result = nodeDisp(22, 1)
    elif i == 1:
        result = abs(response[1])
    else:
        result = response[2]
    resultOther = comparisonResults[1][i]
    tol = tolerances[i]
    if abs(result - resultOther) > tol:
        ok - 1
"""


def test_portal_frame_2d_verification_example_imports_model_and_static_analysis():
    result = import_openseespy_source(
        PORTAL_FRAME_2D,
        source_name="PortalFrame2d.py",
        units={"length": "in", "force": "kip", "time": "s"},
    )

    assert result.error_count == 0
    assert result.project.model.ndm == 2
    assert result.project.model.ndf == 3
    assert len(result.project.model.nodes) == 24
    assert len(result.project.model.elements) == 35
    assert len(result.project.sections) == 7
    assert len(result.project.constraints) == 14
    assert sum(
        1
        for node in result.project.model.nodes.values()
        if any(abs(value) > 0.0 for value in node.mass)
    ) == 7
    assert len(result.project.nodal_loads) == 7

    assert result.project.model.nodes[22].xyz[:2] == (0.0, 1104.0)
    assert result.project.model.nodes[24].xyz[:2] == (720.0, 1104.0)

    first = result.project.model.elements[1]
    assert first.element_type == "elasticBeamColumn"
    assert first.i == 1
    assert first.j == 4
    assert first.transf_tag == 1
    first_section = result.project.sections[first.section_tag]
    assert first_section.parameters["A"] == 72.3
    assert first_section.parameters["Iz"] == 3230.0

    center = result.project.model.elements[8]
    center_section = result.project.sections[center.section_tag]
    assert center_section.parameters["A"] == 84.4
    assert center_section.parameters["Iz"] == 3910.0

    beam = result.project.model.elements[22]
    beam_section = result.project.sections[beam.section_tag]
    assert beam_section.parameters["A"] == 47.1
    assert beam_section.parameters["Iz"] == 5120.0

    assert len(result.project.analyses) == 1
    analysis = next(iter(result.project.analyses.values()))
    assert analysis.analysis_type == "Static"
    assert analysis.integrator == "LoadControl"
    assert analysis.algorithm == "Linear"
    assert analysis.steps == 1

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
        element_loads=result.project.element_loads,
        prescribed_displacements=result.project.prescribed_displacements,
        recorders=result.project.recorders,
        units=result.project.units,
    )

    assert "ops.model('basic', '-ndm', 2, '-ndf', 3)" in regenerated
    assert "ops.geomTransf('Linear', 1)" in regenerated
    assert (
        "ops.element('elasticBeamColumn', 1, 1, 4, "
        "72.3, 29500, 3230, 1)"
    ) in regenerated
    assert "ops.section('Elastic', " in regenerated
    assert "_studio_primary_algorithm = 'Linear'" in regenerated
    assert "ops.test(" not in regenerated
    assert ", 0, 0, 0)" not in regenerated
    compile(regenerated, "<portal-frame-2d-roundtrip>", "exec")


def test_model_command_uses_native_opensees_default_ndf_when_omitted():
    # StructuralModel currently supports the frame/structural 2D and 3D
    # builders. OpenSees' native omitted-ndf defaults are 3 and 6 respectively.
    for ndm, expected_ndf in ((2, 3), (3, 6)):
        result = import_openseespy_source(
            "from openseespy.opensees import *\n"
            f"model('Basic', '-ndm', {ndm})\n",
            source_name=f"ndm_{ndm}.py",
            units={"length": "m", "force": "N", "time": "s"},
        )
        assert result.error_count == 0
        assert result.project.model.ndf == expected_ndf
