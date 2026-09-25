import pytest

from openseespy_studio.generator import to_openseespy
from openseespy_studio.importer import import_openseespy_source
from openseespy_studio.model import StructuralModel
from openseespy_studio.project import (
    AnalysisSettingsData,
    LoadPatternData,
    NodalLoadData,
    SectionData,
    TimeSeriesData,
    TransformationData,
)


def test_safe_import_resolves_variables_and_range_loops():
    source = """
import openseespy.opensees as ops

L = 3.0
E = 200.0e9
ops.model('basic', '-ndm', 3, '-ndf', 6)
for i in range(3):
    ops.node(i + 1, 0.0, 0.0, i * L)
ops.fix(1, 1, 1, 1, 1, 1, 1)
ops.uniaxialMaterial('Elastic', 1, E)
ops.section('Elastic', 1, E, 0.02, 8e-5, 8e-5, 80e9, 1e-4)
ops.geomTransf('Linear', 1, 1.0, 0.0, 0.0)
ops.element('elasticBeamColumn', 1, 1, 2, 0.02, E, 80e9, 1e-4, 8e-5, 8e-5, 1)
ops.element('elasticBeamColumn', 2, 2, 3, 0.02, E, 80e9, 1e-4, 8e-5, 8e-5, 1)
"""

    result = import_openseespy_source(
        source,
        source_name="loop_model.py",
        units={"length": "m", "force": "N", "time": "s"},
    )

    assert result.error_count == 0
    assert set(result.project.model.nodes) == {1, 2, 3}
    assert set(result.project.model.elements) == {1, 2}
    assert result.project.model.nodes[3].xyz == (0.0, 0.0, 6.0)
    assert result.project.materials[1].parameters["E"] == 200.0e9
    assert result.project.model.elements[1].section_tag == 1
    assert result.project.model.elements[2].transf_tag == 1


def test_safe_import_reconstructs_fiber_section_primitives():
    source = """
from openseespy.opensees import *
model('basic', '-ndm', 3, '-ndf', 6)
node(1, 0, 0, 0)
node(2, 0, 0, 3)
fix(1, 1, 1, 1, 1, 1, 1)
uniaxialMaterial('Concrete02', 1, -30e6, -0.002, -6e6, -0.006, 0.1, 3e6, 2e8)
uniaxialMaterial('Steel02', 2, 500e6, 200e9, 0.01, 20.0, 0.925, 0.15)
section('Fiber', 10, '-GJ', 1e6)
patch('rect', 1, 8, 8, -0.2, -0.2, 0.2, 0.2)
layer('straight', 2, 4, 0.0002, -0.15, -0.15, 0.15, -0.15)
geomTransf('PDelta', 1, 1, 0, 0)
beamIntegration('Lobatto', 20, 10, 5)
element('forceBeamColumn', 1, 1, 2, 1, 20, '-iter', 20, 1e-10)
"""

    result = import_openseespy_source(
        source,
        source_name="fiber.py",
        units={"length": "m", "force": "N", "time": "s"},
    )

    assert result.error_count == 0
    section = result.project.sections[10]
    assert section.section_type == "Fiber"
    assert len(section.fiber_components) == 2
    element = result.project.model.elements[1]
    assert element.element_type == "forceBeamColumn"
    assert element.section_tag == 10
    assert element.integration_points == 5
    assert element.force_max_iter == 20


def test_studio_generated_static_script_round_trips_to_project():
    model = StructuralModel("roundtrip")
    model.add_node(1, 0.0, 0.0, 0.0)
    model.add_node(2, 0.0, 0.0, 3.0)
    model.set_fixity(1, (1, 1, 1, 1, 1, 1))
    model.add_element(1, 1, 2, section_tag=1, transf_tag=1)

    sections = {
        1: SectionData(
            1,
            "Column",
            "Elastic",
            parameters={
                "E": 200e9,
                "A": 0.02,
                "Iz": 8e-5,
                "Iy": 8e-5,
                "G": 80e9,
                "J": 1e-4,
            },
        )
    }
    transformations = {
        1: TransformationData(1, "Column", "Linear", (1.0, 0.0, 0.0))
    }
    time_series = {
        1: TimeSeriesData(1, "Load", "Linear", factor=1.0)
    }
    patterns = {
        1: LoadPatternData(1, "Load", "Plain", time_series_tag=1)
    }
    loads = {
        1: NodalLoadData(
            1,
            "Top load",
            1,
            2,
            (1000.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        )
    }
    analysis = AnalysisSettingsData(
        1,
        "Static",
        "Static",
        constraints_handler="Plain",
        numberer="Plain",
        system="BandGeneral",
        steps=1,
        load_increment=1.0,
        live_convergence=False,
    )

    script = to_openseespy(
        model,
        sections=sections,
        transformations=transformations,
        time_series=time_series,
        load_patterns=patterns,
        nodal_loads=loads,
        analyses={1: analysis},
        active_analysis_tag=1,
        units={"length": "m", "force": "N", "time": "s"},
    )

    imported = import_openseespy_source(
        script,
        source_name="studio_export.py",
        units={"length": "m", "force": "N", "time": "s"},
    )

    assert imported.error_count == 0
    assert len(imported.project.model.nodes) == 2
    assert len(imported.project.model.elements) == 1
    assert len(imported.project.sections) == 1
    assert len(imported.project.transformations) == 1
    assert len(imported.project.nodal_loads) == 1
    assert imported.project.active_analysis_tag == 1
    restored_analysis = imported.project.analyses[1]
    assert restored_analysis.analysis_type == "Static"
    assert restored_analysis.constraints_handler == "Plain"
    assert restored_analysis.numberer == "Plain"
    assert restored_analysis.system == "BandGeneral"
    assert restored_analysis.steps == 1
    assert restored_analysis.load_increment == 1.0

    regenerated = to_openseespy(
        imported.project.model,
        imported.project.materials,
        imported.project.sections,
        imported.project.transformations,
        imported.project.constraints,
        imported.project.connections,
        imported.project.time_series,
        imported.project.load_patterns,
        imported.project.nodal_loads,
        imported.project.analyses,
        imported.project.active_analysis_tag,
        units=imported.project.units,
    )
    assert "# ERROR:" not in regenerated
    compile(regenerated, "<roundtrip>", "exec")


def test_importer_recovers_loads_recorders_and_wrapper_materials():
    source = """
import openseespy.opensees as ops
ops.model('basic', '-ndm', 3, '-ndf', 6)
ops.node(1, 0, 0, 0)
ops.node(2, 0, 0, 3)
ops.fix(1, 1, 1, 1, 1, 1, 1)
ops.uniaxialMaterial('Elastic', 1, 200e9)
ops.uniaxialMaterial('MinMax', 2, 1, '-min', -0.01, '-max', 0.01)
ops.section('Elastic', 1, 200e9, 0.02, 8e-5, 8e-5, 80e9, 1e-4)
ops.geomTransf('Linear', 1, 1, 0, 0)
ops.element('elasticBeamColumn', 1, 1, 2, 0.02, 200e9, 80e9, 1e-4, 8e-5, 8e-5, 1)
ops.timeSeries('Linear', 1, '-factor', 1.0)
ops.pattern('Plain', 1, 1)
ops.load(2, 10, 0, 0, 0, 0, 0)
ops.eleLoad('-ele', 1, '-type', '-beamUniform', -2.0, 0.0, 0.0)
ops.recorder('Node', '-file', 'top.out', '-time', '-node', 2, '-dof', 1, 'disp')
"""

    result = import_openseespy_source(
        source,
        source_name="loads.py",
        units={"length": "m", "force": "N", "time": "s"},
    )

    assert result.error_count == 0
    assert result.project.materials[2].material_type == "MinMax"
    assert result.project.materials[2].base_material_tag == 1
    assert len(result.project.nodal_loads) == 1
    assert len(result.project.element_loads) == 1
    assert result.project.element_loads[1].wy == -2.0
    assert len(result.project.recorders) == 1
    recorder = result.project.recorders[1]
    assert recorder.recorder_type == "Node"
    assert recorder.target_tags == [2]
    assert recorder.dofs == [1]
    assert recorder.response == "disp"


def test_importer_recovers_zero_length_section_orientation():
    source = """
import openseespy.opensees as ops
ops.model('basic', '-ndm', 3, '-ndf', 6)
ops.node(1, 0, 0, 0)
ops.node(2, 0, 0, 0)
ops.fix(1, 1, 1, 1, 1, 1, 1)
ops.section('Elastic', 10, 1000, 1, 1, 1, 1000, 1)
ops.element('zeroLengthSection', 20, 1, 2, 10,
            '-orient', 0, 0, 1, 0, 1, 0, '-doRayleigh', 1)
"""

    result = import_openseespy_source(
        source,
        source_name="zero_length_section.py",
        units={"length": "m", "force": "N", "time": "s"},
    )

    assert result.error_count == 0
    connection = result.project.connections[20]
    assert connection.connection_type == "zeroLengthSection"
    assert connection.section_tag == 10
    assert connection.orient_x == (0.0, 0.0, 1.0)
    assert connection.orient_y == (0.0, 1.0, 0.0)
    assert connection.do_rayleigh is True


def test_importer_never_executes_custom_python(tmp_path):
    target = tmp_path / "must-not-exist.txt"
    source = f"""
import openseespy.opensees as ops
ops.model('basic', '-ndm', 3, '-ndf', 6)
ops.node(1, 0, 0, 0)
open({str(target)!r}, 'w').write('unsafe')
"""

    result = import_openseespy_source(
        source,
        source_name="unsafe.py",
        units={"length": "m", "force": "N", "time": "s"},
    )

    assert not target.exists()
    assert len(result.project.model.nodes) == 1
    assert result.unsupported_count >= 1


def test_safe_import_preserves_truss_material_assignment():
    source = """
import openseespy.opensees as ops
ops.model('basic', '-ndm', 2, '-ndf', 2)
ops.node(1, 0.0, 0.0)
ops.node(2, 2.0, 0.0)
ops.uniaxialMaterial('Elastic', 3, 200.0e9)
ops.element('Truss', 9, 1, 2, 0.005, 3)
"""

    result = import_openseespy_source(
        source,
        source_name="truss.py",
        units={"length": "m", "force": "N", "time": "s"},
    )

    assert result.error_count == 0
    element = result.project.model.elements[9]
    assert element.element_type == "truss"
    assert element.truss_area == 0.005
    assert element.truss_material_tag == 3
    assert 3 in result.project.materials


def test_safe_import_preserves_corot_truss():
    source = """
import openseespy.opensees as ops
ops.model('basic', '-ndm', 2, '-ndf', 3)
ops.node(1, 0.0, 0.0)
ops.node(2, 0.0, 3.0)
ops.uniaxialMaterial('Steel02', 3, 500.0e6, 200.0e9, 0.01, 20.0, 0.925, 0.15)
ops.element('corotTruss', 9, 1, 2, 0.0008, 3)
"""

    result = import_openseespy_source(
        source,
        source_name="corot_truss.py",
        units={"length": "m", "force": "N", "time": "s"},
    )

    assert result.error_count == 0
    element = result.project.model.elements[9]
    assert element.element_type == "corotTruss"
    assert element.truss_area == pytest.approx(0.0008)
    assert element.truss_material_tag == 3


def test_importer_rejects_frame_tag_already_used_by_connection():
    source = """
import openseespy.opensees as ops
ops.model('basic', '-ndm', 3, '-ndf', 6)
ops.node(1, 0.0, 0.0, 0.0)
ops.node(2, 0.0, 0.0, 0.0)
ops.node(3, 0.0, 0.0, 3.0)
ops.uniaxialMaterial('Elastic', 1, 1000.0)
ops.element('zeroLength', 10, 1, 2, '-mat', 1, '-dir', 1)
ops.element('elasticBeamColumn', 10, 2, 3, 0.02, 200e9, 80e9, 1e-4, 8e-5, 8e-5, 1)
"""

    result = import_openseespy_source(
        source,
        source_name="duplicate_element_tag.py",
        units={"length": "m", "force": "N", "time": "s"},
    )

    assert result.error_count == 1
    assert 10 in result.project.connections
    assert 10 not in result.project.model.elements
    assert any(
        "already used by a connection" in issue.message
        for issue in result.issues
    )


def test_importer_preserves_full_steel02_isotropic_hardening_parameters():
    source = """
import openseespy.opensees as ops
ops.model('basic', '-ndm', 2, '-ndf', 3)
ops.uniaxialMaterial(
    'Steel02', 7, 480.0, 202000.0, 0.02,
    20.0, 0.9, 0.08, 0.039, 1.0, 0.029, 1.0
)
"""
    result = import_openseespy_source(
        source,
        source_name="steel02_full.py",
        units={"length": "mm", "force": "N", "time": "s"},
    )

    assert result.error_count == 0
    material = result.project.materials[7]
    assert material.parameters["Fy"] == 480.0e6
    assert material.parameters["E0"] == 202.0e9
    assert material.parameters["b"] == 0.02
    assert material.parameters["R0"] == 20.0
    assert material.parameters["cR1"] == 0.9
    assert material.parameters["cR2"] == 0.08
    assert material.parameters["a1"] == 0.039
    assert material.parameters["a2"] == 1.0
    assert material.parameters["a3"] == 0.029
    assert material.parameters["a4"] == 1.0


def test_importer_reads_relative_path_time_series_file(tmp_path):
    motion_path = tmp_path / "A10000.dat"
    motion_path.write_text(
        "0.0\n0.10 -0.20\n3.0e-2\n",
        encoding="utf-8",
    )
    source_path = tmp_path / "cantilever_eq.py"
    source = """
from openseespy.opensees import *

model('basic', '-ndm', 2, '-ndf', 3)
G = 386.0
timeSeries(
    'Path', 2,
    '-dt', 0.005,
    '-filePath', 'A10000.dat',
    '-factor', G,
)
pattern('UniformExcitation', 2, 1, '-accel', 2)
"""
    source_path.write_text(source, encoding="utf-8")

    result = import_openseespy_source(
        source,
        source_name=source_path.name,
        source_path=source_path,
        units={"length": "in", "force": "kip", "time": "s"},
    )

    assert result.error_count == 0
    assert result.unsupported_count == 0

    series = result.project.time_series[2]
    assert series.series_type == "Path"
    assert series.dt == 0.005
    assert series.factor == 386.0
    assert series.values == [0.0, 0.10, -0.20, 3.0e-2]

    pattern = result.project.load_patterns[2]
    assert pattern.pattern_type == "UniformExcitation"
    assert pattern.time_series_tag == 2
    assert pattern.direction == 1


def test_importer_rejects_path_time_series_file_outside_script_tree(tmp_path):
    script_dir = tmp_path / "model"
    script_dir.mkdir()
    outside_path = tmp_path / "outside.dat"
    outside_path.write_text("0.0 0.1", encoding="utf-8")

    source_path = script_dir / "unsafe_eq.py"
    source = """
from openseespy.opensees import *

model('basic', '-ndm', 2, '-ndf', 3)
timeSeries(
    'Path', 2,
    '-dt', 0.01,
    '-filePath', '../outside.dat',
)
"""
    source_path.write_text(source, encoding="utf-8")

    result = import_openseespy_source(
        source,
        source_name=source_path.name,
        source_path=source_path,
        units={"length": "m", "force": "N", "time": "s"},
    )

    assert 2 not in result.project.time_series
    assert any(
        issue.severity == "UNSUPPORTED"
        and issue.construct == "timeSeries Path -filePath"
        and "outside the imported script directory tree" in issue.message
        for issue in result.issues
    )


def test_importer_recovers_single_mode_committed_stiffness_rayleigh():
    source = """
from openseespy.opensees import *

model('basic', '-ndm', 2, '-ndf', 3)
node(1, 0.0, 0.0)
node(2, 0.0, 432.0)
fix(1, 1, 1, 1)
mass(2, 5.18, 0.0, 0.0)
geomTransf('Linear', 1)
element('elasticBeamColumn', 1, 1, 2, 3600.0, 3225.0, 1080000.0, 1)

timeSeries('Linear', 1)
pattern('Plain', 1, 1)
load(2, 0.0, -2000.0, 0.0)
constraints('Plain')
numberer('Plain')
system('BandGeneral')
algorithm('Linear')
integrator('LoadControl', 0.1)
analysis('Static')
analyze(10)
loadConst('-time', 0.0)

timeSeries('Path', 2, '-dt', 0.005, '-values', 0.0, 0.1, -0.2)
pattern('UniformExcitation', 2, 1, '-accel', 2)

freq = eigen('-fullGenLapack', 1)[0]**0.5
dampRatio = 0.02
rayleigh(0.0, 0.0, 0.0, 2*dampRatio/freq)

wipeAnalysis()
constraints('Plain')
numberer('Plain')
system('BandGeneral')
algorithm('Linear')
integrator('Newmark', 0.5, 0.25)
analysis('Transient')
analyze(10, 0.01)
"""

    result = import_openseespy_source(
        source,
        source_name="cantilever_eq.py",
        units={"length": "in", "force": "kip", "time": "s"},
    )

    assert result.error_count == 0
    assert not any(
        issue.construct in {"assignment", "rayleigh"}
        for issue in result.issues
    )

    analysis = next(iter(result.project.analyses.values()))
    assert analysis.analysis_type == "Transient"
    assert analysis.rayleigh_model == "SingleModeCommittedStiffness"
    assert analysis.rayleigh_damping_ratio == 0.02
    assert analysis.rayleigh_mode_i == 1
    assert analysis.eigen_solver == "-fullGenLapack"
    assert analysis.preload_gravity is True
    assert analysis.gravity_steps == 10
    assert analysis.deferred_pattern_tags == [2]

    generated = to_openseespy(
        result.project.model,
        result.project.materials,
        result.project.sections,
        result.project.transformations,
        result.project.constraints,
        result.project.connections,
        result.project.time_series,
        result.project.load_patterns,
        result.project.nodal_loads,
        result.project.analyses,
        result.project.active_analysis_tag,
        result.project.element_loads,
        result.project.prescribed_displacements,
        result.project.recorders,
        result.project.units,
    )
    assert "_studio_beta_k_comm = 2.0 * _studio_zeta / _studio_omega_i" in generated
    assert "ops.rayleigh(0.0, 0.0, 0.0, _studio_beta_k_comm)" in generated


def test_importer_exposes_safe_constants_from_sibling_module(tmp_path):
    gravity = tmp_path / "RCFrameGravity.py"
    gravity.write_text(
        """
from openseespy.opensees import *
model('basic', '-ndm', 2, '-ndf', 3)
node(1, 0.0, 0.0)
node(3, 0.0, 120.0)
fix(1, 1, 1, 1)
P = 2000.0
""",
        encoding="utf-8",
    )
    source_path = tmp_path / "earthquake.py"
    source = """
from openseespy.opensees import *
import RCFrameGravity
g = 400.0
m = RCFrameGravity.P/g
mass(3, m, m, 0.0)
"""
    source_path.write_text(source, encoding="utf-8")

    result = import_openseespy_source(
        source,
        source_name=source_path.name,
        source_path=source_path,
        units={"length": "in", "force": "kip", "time": "s"},
    )

    assert result.error_count == 0
    assert result.project.model.nodes[3].mass[:3] == (5.0, 5.0, 0.0)
    assert not any(
        issue.construct == "assignment"
        and issue.line == 5
        for issue in result.issues
    )


def test_importer_recognizes_peer_readrecord_without_executing_helper(tmp_path):
    (tmp_path / "ReadRecord.py").write_text(
        """
def ReadRecord(inFilename, outFilename):
    raise RuntimeError("safe importer must never execute this function")
""",
        encoding="utf-8",
    )
    (tmp_path / "elCentro.at2").write_text(
        """PEER NGA RECORD
ACCELERATION TIME HISTORY IN UNITS OF G
NPTS= 4, DT= .00500 SEC
0.10 -0.20
0.30 0.00
""",
        encoding="utf-8",
    )
    source_path = tmp_path / "earthquake.py"
    source = """
from openseespy.opensees import *
import ReadRecord
record = 'elCentro'
dt, nPts = ReadRecord.ReadRecord(record+'.at2', record+'.dat')
timeSeries('Path', 2, '-filePath', record+'.dat', '-dt', dt, '-factor', 386.4)
"""
    source_path.write_text(source, encoding="utf-8")

    result = import_openseespy_source(
        source,
        source_name=source_path.name,
        source_path=source_path,
        units={"length": "in", "force": "kip", "time": "s"},
    )

    assert result.error_count == 0
    series = result.project.time_series[2]
    assert series.dt == 0.005
    assert series.factor == 386.4
    assert series.values == [0.10, -0.20, 0.30, 0.00]
    assert result.imported_counts["Ground-motion records"] == 1


def test_importer_recovers_bounded_transient_loop_and_direct_rayleigh(tmp_path):
    (tmp_path / "ReadRecord.py").write_text(
        "def ReadRecord(inFilename, outFilename):\n    return 0.0, 0\n",
        encoding="utf-8",
    )
    (tmp_path / "elCentro.at2").write_text(
        """HEADER
NPTS= 4, DT= .00500 SEC
0.10 -0.20 0.30 0.00
""",
        encoding="utf-8",
    )
    source_path = tmp_path / "earthquake.py"
    source = """
from openseespy.opensees import *
model('basic', '-ndm', 2, '-ndf', 3)
node(1, 0.0, 0.0)
node(2, 0.0, 120.0)
fix(1, 1, 1, 1)
mass(2, 1.0, 1.0, 0.0)
timeSeries('Linear', 1)
pattern('Plain', 1, 1)
load(2, 0.0, -10.0, 0.0)
constraints('Plain')
numberer('Plain')
system('BandGeneral')
algorithm('Linear')
integrator('LoadControl', 0.1)
analysis('Static')
analyze(10)
loadConst('-time', 0.0)

import ReadRecord
record = 'elCentro'
dt, nPts = ReadRecord.ReadRecord(record+'.at2', record+'.dat')
timeSeries('Path', 2, '-filePath', record+'.dat', '-dt', dt, '-factor', 386.4)
pattern('UniformExcitation', 2, 1, '-accel', 2)
rayleigh(0.0, 0.0, 0.0, 0.000625)
wipeAnalysis()
system('BandGeneral')
constraints('Plain')
test('NormDispIncr', 1.0e-12, 10)
algorithm('Newton')
numberer('RCM')
integrator('Newmark', 0.5, 0.25)
analysis('Transient')
tFinal = nPts*dt
tCurrent = getTime()
ok = 0
while ok == 0 and tCurrent < tFinal:
    ok = analyze(1, .01)
    if ok != 0:
        test('NormDispIncr', 1.0e-12, 100, 0)
        algorithm('ModifiedNewton', '-initial')
        ok = analyze(1, .01)
    tCurrent = getTime()
"""
    source_path.write_text(source, encoding="utf-8")

    result = import_openseespy_source(
        source,
        source_name=source_path.name,
        source_path=source_path,
        units={"length": "in", "force": "kip", "time": "s"},
    )

    assert result.error_count == 0
    assert not any(issue.construct == "While" for issue in result.issues)
    analysis = next(iter(result.project.analyses.values()))
    assert analysis.analysis_type == "Transient"
    assert analysis.steps == 2
    assert analysis.dt == 0.01
    assert analysis.preload_gravity is True
    assert analysis.gravity_steps == 10
    assert analysis.deferred_pattern_tags == [2]
    assert analysis.recovery is True
    assert analysis.rayleigh_model == "DirectCoefficients"
    assert analysis.rayleigh_alpha_m == 0.0
    assert analysis.rayleigh_beta_k == 0.0
    assert analysis.rayleigh_beta_k_init == 0.0
    assert analysis.rayleigh_beta_k_comm == 0.000625

    generated = to_openseespy(
        result.project.model,
        result.project.materials,
        result.project.sections,
        result.project.transformations,
        result.project.constraints,
        result.project.connections,
        result.project.time_series,
        result.project.load_patterns,
        result.project.nodal_loads,
        result.project.analyses,
        result.project.active_analysis_tag,
        result.project.element_loads,
        result.project.prescribed_displacements,
        result.project.recorders,
        result.project.units,
    )
    assert "ops.rayleigh(0, 0, 0, 0.000625)" in generated


def test_importer_recovers_node_response_queries_as_probes():
    source = """
from openseespy.opensees import *
model('basic', '-ndm', 2, '-ndf', 3)
node(1, 0.0, 0.0)
node(2, 0.0, 120.0)
fix(1, 1, 1, 1)
mass(2, 1.0, 1.0, 0.0)
constraints('Plain')
numberer('Plain')
system('BandGeneral')
algorithm('Linear')
integrator('Newmark', 0.5, 0.25)
analysis('Transient')
tFinal = 0.02
tCurrent = getTime()
ok = 0
history = []
while ok == 0 and tCurrent < tFinal:
    ok = analyze(1, 0.01)
    tCurrent = getTime()
    history.append(nodeDisp(2, 1))
reaction_x = nodeReaction(1, 1)
"""

    result = import_openseespy_source(
        source,
        source_name="probe_example.py",
        units={"length": "in", "force": "kip", "time": "s"},
    )

    probes = [
        item
        for item in result.project.solution_results.values()
        if bool(item.settings.get("probe", False))
    ]
    assert len(probes) == 2

    by_quantity = {
        str(item.settings["quantity"]): item
        for item in probes
    }
    disp = by_quantity["Displacement"]
    assert disp.result_type == "TimeHistory"
    assert disp.node_scope == [2]
    assert disp.settings["node"] == 2
    assert disp.settings["dof"] == 1

    reaction = by_quantity["Reaction"]
    assert reaction.node_scope == [1]
    assert reaction.settings["node"] == 1
    assert reaction.settings["dof"] == 1
    assert result.imported_counts["Node probes"] == 2


def test_importer_recovers_1d_zero_length_mdof_with_node_zero_and_inline_mass():
    source = """
import openseespy.opensees as ops

m1 = 0.1
m2 = 0.2
m3 = 0.3
ops.wipe()
ops.model('basic', '-ndm', 1, '-ndf', 1)
ops.node(0, 0)
ops.node(1, 0, '-mass', m1)
ops.node(2, 0, '-mass', m2)
ops.node(3, 0, '-mass', m3)
ops.fix(0, 1)
ops.uniaxialMaterial('Steel01', 1, 0.55, 60.0, 0.01)
ops.uniaxialMaterial('Steel01', 2, 0.45, 50.0, 0.01)
ops.uniaxialMaterial('Steel01', 3, 0.30, 30.0, 0.01)
ops.element('zeroLength', 1, 0, 1, '-mat', 1, '-dir', 1, '-doRayleigh', 1)
ops.element('zeroLength', 2, 1, 2, '-mat', 2, '-dir', 1, '-doRayleigh', 1)
ops.element('zeroLength', 3, 2, 3, '-mat', 3, '-dir', 1, '-doRayleigh', 1)
ops.recorder(
    'Node', '-file', './Absolute_accel.out',
    '-timeSeries', 1, '-time', '-dT', 0.001,
    '-node', 0, 1, 2, 3, '-dof', 1, 'accel'
)
ops.wipe()
"""

    result = import_openseespy_source(
        source,
        source_name="nonlinear_mdof.py",
        units={"length": "m", "force": "kN", "time": "s"},
    )

    assert result.error_count == 0
    assert result.project.model.ndm == 1
    assert result.project.model.ndf == 1
    assert set(result.project.model.nodes) == {0, 1, 2, 3}
    assert result.project.model.nodes[0].fixity == (1,)
    assert result.project.model.nodes[1].mass == (0.1,)
    assert result.project.model.nodes[2].mass == (0.2,)
    assert result.project.model.nodes[3].mass == (0.3,)
    assert set(result.project.connections) == {1, 2, 3}
    assert result.project.connections[1].node_i == 0
    assert result.project.connections[1].materials_by_dof == {1: 1}
    assert result.project.connections[1].do_rayleigh is True
    assert len(result.project.recorders) == 1
    assert result.project.recorders[1].target_tags == [0, 1, 2, 3]


def test_importer_recovers_numpy_eigen_two_mode_rayleigh_pattern():
    source = """
import openseespy.opensees as ops
import numpy as np

ops.model('basic', '-ndm', 1, '-ndf', 1)
ops.node(0, 0)
ops.node(1, 0, '-mass', 0.1)
ops.node(2, 0, '-mass', 0.1)
ops.node(3, 0, '-mass', 0.1)
ops.fix(0, 1)
ops.uniaxialMaterial('Steel01', 1, 0.55, 60.0, 0.01)
ops.uniaxialMaterial('Steel01', 2, 0.45, 50.0, 0.01)
ops.uniaxialMaterial('Steel01', 3, 0.30, 30.0, 0.01)
ops.element('zeroLength', 1, 0, 1, '-mat', 1, '-dir', 1)
ops.element('zeroLength', 2, 1, 2, '-mat', 2, '-dir', 1)
ops.element('zeroLength', 3, 2, 3, '-mat', 3, '-dir', 1)

h = 0.05
w1, w2, w3 = np.array(ops.eigen('-fullGenLapack', 3))**0.5
a0 = 2*h*w1*w2/(w1+w2)
a1 = 2*h/(w1+w2)
ops.rayleigh(a0, 0.0, 0.0, a1)

ops.wipeAnalysis()
ops.algorithm('Newton')
ops.system('BandGen')
ops.numberer('Plain')
ops.constraints('Plain')
ops.integrator('Newmark', 0.5, 0.25)
ops.analysis('Transient')
ops.test('NormUnbalance', 1.0e-12, 100)
ops.analyze(100, 0.001)
"""

    result = import_openseespy_source(
        source,
        source_name="nonlinear_mdof_rayleigh.py",
        units={"length": "m", "force": "kN", "time": "s"},
    )

    assert result.error_count == 0
    analysis = next(iter(result.project.analyses.values()))
    assert analysis.analysis_type == "Transient"
    assert analysis.rayleigh_model == "TwoMode"
    assert analysis.rayleigh_damping_ratio == 0.05
    assert analysis.rayleigh_mode_i == 1
    assert analysis.rayleigh_mode_j == 2
    assert analysis.eigen_solver == "-fullGenLapack"


def test_importer_reads_nonlinear_mdof_example_with_companion_motion(tmp_path):
    motion = tmp_path / "el_centro.th"
    motion.write_text(
        "0.0\n0.10\n-0.05\n0.02\n",
        encoding="utf-8",
    )
    source_path = tmp_path / "nonlinear_mdof.py"
    source = """
import openseespy.opensees as ops
import numpy as np

m = 1
s = 1
kN = 1
g = 9.81*m/s**2
mm = 1e-3*m
Ton = kN*s**2/m

N = 3
h = 0.05
dt = 0.02
dt_out = 0.001
tFinal = 35
m1 = 0.1*Ton
m2 = 0.1*Ton
m3 = 0.1*Ton
Py1 = 0.55*kN
Py2 = 0.45*kN
Py3 = 0.30*kN
K1 = 60*kN/m
K2 = 50*kN/m
K3 = 30*kN/m
b = 0.01

ops.wipe()
ops.model('basic', '-ndm', 1, '-ndf', 1)
ops.node(0, 0)
ops.node(1, 0, '-mass', m1)
ops.node(2, 0, '-mass', m2)
ops.node(3, 0, '-mass', m3)
ops.fix(0, 1)
ops.uniaxialMaterial('Steel01', 1, Py1, K1, b)
ops.uniaxialMaterial('Steel01', 2, Py2, K2, b)
ops.uniaxialMaterial('Steel01', 3, Py3, K3, b)
ops.element('zeroLength', 1, 0, 1, '-mat', 1, '-dir', 1, '-doRayleigh', 1)
ops.element('zeroLength', 2, 1, 2, '-mat', 2, '-dir', 1, '-doRayleigh', 1)
ops.element('zeroLength', 3, 2, 3, '-mat', 3, '-dir', 1, '-doRayleigh', 1)

w1, w2, w3 = np.array(ops.eigen('-fullGenLapack', 3))**0.5
a0 = 2*h*w1*w2/(w1+w2)
a1 = 2*h/(w1+w2)
ops.rayleigh(a0, 0.0, 0.0, a1)

load_tag = 1
pattern_tag = 1
direc = 1
ops.timeSeries(
    'Path', load_tag, '-dt', dt,
    '-filePath', r'./el_centro.th', '-factor', g
)
ops.pattern('UniformExcitation', pattern_tag, direc, '-accel', load_tag)

ops.recorder(
    'Node', '-file', r'./Relative_disp.out',
    '-time', '-dT', dt_out, '-node', 1, 2, 3, '-dof', 1, 'disp'
)
ops.recorder(
    'Node', '-file', r'./Relative_accel.out',
    '-time', '-dT', dt_out, '-node', 1, 2, 3, '-dof', 1, 'accel'
)
ops.recorder(
    'Node', '-file', r'./Absolute_accel.out',
    '-timeSeries', load_tag, '-time', '-dT', dt_out,
    '-node', 0, 1, 2, 3, '-dof', 1, 'accel'
)
ops.recorder(
    'Element', '-file', r'./Element_force.out',
    '-time', '-dT', dt_out, '-ele', 1, 2, 3, 'force'
)

ops.wipeAnalysis()
ops.algorithm('Newton')
ops.system('BandGen')
ops.numberer('Plain')
ops.constraints('Plain')
ops.integrator('Newmark', 0.5, 0.25)
ops.analysis('Transient')
ops.test('NormUnbalance', 1.0e-12, 100)
num_steps = int(tFinal/dt_out+1)
ops.analyze(num_steps, dt_out)
ops.wipe()

rD = np.genfromtxt(r'./Relative_disp.out', usecols=[1, 2, 3]).T
"""
    source_path.write_text(source, encoding="utf-8")

    result = import_openseespy_source(
        source,
        source_name=source_path.name,
        source_path=source_path,
        units={"length": "m", "force": "kN", "time": "s"},
    )

    assert result.error_count == 0
    assert result.project.model.ndm == 1
    assert result.project.model.ndf == 1
    assert set(result.project.model.nodes) == {0, 1, 2, 3}
    assert set(result.project.connections) == {1, 2, 3}
    assert result.project.model.nodes[1].mass == (0.1,)
    assert result.project.time_series[1].dt == 0.02
    assert result.project.time_series[1].factor == 9.81
    assert result.project.time_series[1].values == [0.0, 0.10, -0.05, 0.02]
    assert result.project.load_patterns[1].pattern_type == "UniformExcitation"
    assert len(result.project.recorders) == 4
    assert result.project.recorders[3].target_tags == [0, 1, 2, 3]

    analysis = next(iter(result.project.analyses.values()))
    assert analysis.analysis_type == "Transient"
    assert analysis.integrator == "Newmark"
    assert analysis.steps == 35001
    assert analysis.dt == 0.001
    assert analysis.rayleigh_model == "TwoMode"
    assert analysis.rayleigh_damping_ratio == 0.05
    assert analysis.rayleigh_mode_i == 1
    assert analysis.rayleigh_mode_j == 2


def test_importer_recovers_additional_nd_material_types():
    source = """
import openseespy.opensees as ops

ops.uniaxialMaterial(
    'Concrete02', 4,
    -30.0e6, -0.002, -6.0e6, -0.006,
    0.1, 3.0e6, 2.0e8
)
ops.nDMaterial(
    'ElasticOrthotropic', 21,
    40.0e9, 12.0e9, 8.0e9,
    0.25, 0.30, 0.20,
    5.0e9, 3.0e9, 4.0e9,
    600.0
)
ops.nDMaterial(
    'J2Plasticity', 22,
    166.67e9, 76.923e9,
    250.0e6, 350.0e6,
    16.0, 1.0e9
)
ops.nDMaterial(
    'DruckerPrager', 23,
    100.0e6, 50.0e6, 0.10e6,
    0.10, 0.08,
    0.0, 0.0, 0.0, 0.0, 0.0,
    1.0, 1800.0, 101.325e3
)
ops.nDMaterial(
    'DruckerPrager', 24,
    120.0e6, 60.0e6, 0.12e6,
    0.12, 0.10,
    0.0, 0.0, 0.0, 0.0, 0.0,
    0.5, 1900.0
)
ops.nDMaterial(
    'PressureIndependMultiYield', 25,
    2, 1500.0, 60.0e6, 300.0e6, 37.0e3, 0.10
)
ops.nDMaterial(
    'PressureIndependMultiYield', 26,
    3, 1800.0, 150.0e6, 750.0e6, 75.0e3, 0.10,
    0.0, 80.0e3, 0.0, 30
)
ops.nDMaterial(
    'PressureDependMultiYield', 27,
    2, 1900.0, 75.0e6, 200.0e6,
    33.0, 0.10, 80.0e3, 0.5, 27.0,
    0.07, 0.4, 2.0, 10.0e3, 0.01, 1.0
)
ops.nDMaterial(
    'PressureDependMultiYield', 28,
    3, 2000.0, 100.0e6, 300.0e6,
    37.0, 0.10, 80.0e3, 0.5, 27.0,
    0.05, 0.6, 3.0, 5.0e3, 0.003, 1.0,
    30, 0.55, 0.95, 0.03, 0.65, 101.0e3, 0.5e3
)
ops.nDMaterial(
    'ASDConcrete3D', 29,
    30.0e9, 0.2,
    '-rho', 2400.0,
    '-fc', 30.0e6,
    '-ft', 3.0e6,
    '-implex',
    '-Kc', 0.7,
    '-cdf', 0.0
)
ops.nDMaterial(
    'OrthotropicRAConcrete', 30,
    4, 0.00008, -0.002, 0.0,
    '-damageCte1', 0.175,
    '-damageCte2', 0.5
)
"""

    result = import_openseespy_source(
        source,
        source_name="ndmaterials.py",
        units={"length": "m", "force": "N", "time": "s"},
    )

    assert result.error_count == 0
    assert result.unsupported_count == 0

    orthotropic = result.project.nd_materials[21]
    assert orthotropic.material_type == "ElasticOrthotropic"
    assert orthotropic.parameters["Ex"] == 40.0e9
    assert orthotropic.parameters["nu_xy"] == 0.25
    assert orthotropic.parameters["Gzx"] == 4.0e9
    assert orthotropic.parameters["rho"] == 600.0

    j2 = result.project.nd_materials[22]
    assert j2.material_type == "J2Plasticity"
    assert j2.parameters["K"] == 166.67e9
    assert j2.parameters["sig0"] == 250.0e6
    assert j2.parameters["sigInf"] == 350.0e6
    assert j2.parameters["delta"] == 16.0
    assert j2.parameters["H"] == 1.0e9

    drucker = result.project.nd_materials[23]
    assert drucker.material_type == "DruckerPrager"
    assert drucker.parameters["K"] == 100.0e6
    assert drucker.parameters["rho"] == 0.10
    assert drucker.parameters["rhoBar"] == 0.08
    assert drucker.parameters["density"] == 1800.0
    assert drucker.parameters["atmPressure"] == 101.325e3

    drucker_default_atm = result.project.nd_materials[24]
    assert drucker_default_atm.material_type == "DruckerPrager"
    assert drucker_default_atm.parameters["theta"] == 0.5
    assert drucker_default_atm.parameters["density"] == 1900.0
    assert drucker_default_atm.parameters["atmPressure"] == 101325.0

    pimy_default = result.project.nd_materials[25]
    assert pimy_default.material_type == "PressureIndependMultiYield"
    assert pimy_default.parameters["nd"] == 2.0
    assert pimy_default.parameters["rho"] == 1500.0
    assert pimy_default.parameters["refShearModul"] == 60.0e6
    assert pimy_default.parameters["frictionAng"] == 0.0
    assert pimy_default.parameters["refPress"] == 100.0e3
    assert pimy_default.parameters["pressDependCoe"] == 0.0
    assert pimy_default.parameters["noYieldSurf"] == 20.0

    pimy_full = result.project.nd_materials[26]
    assert pimy_full.parameters["nd"] == 3.0
    assert pimy_full.parameters["rho"] == 1800.0
    assert pimy_full.parameters["refPress"] == 80.0e3
    assert pimy_full.parameters["noYieldSurf"] == 30.0
    assert any(
        issue.construct == "PressureIndependMultiYield material stage"
        for issue in result.issues
    )

    pdmy_default = result.project.nd_materials[27]
    assert pdmy_default.material_type == "PressureDependMultiYield"
    assert pdmy_default.parameters["nd"] == 2.0
    assert pdmy_default.parameters["rho"] == 1900.0
    assert pdmy_default.parameters["refShearModul"] == 75.0e6
    assert pdmy_default.parameters["liquefac1"] == 10.0e3
    assert pdmy_default.parameters["noYieldSurf"] == 20.0
    assert pdmy_default.parameters["e"] == 0.6
    assert pdmy_default.parameters["cs1"] == 0.9
    assert pdmy_default.parameters["cs2"] == 0.02
    assert pdmy_default.parameters["cs3"] == 0.7
    assert pdmy_default.parameters["pa"] == 101.0e3
    assert pdmy_default.parameters["c"] == 300.0

    pdmy_full = result.project.nd_materials[28]
    assert pdmy_full.parameters["nd"] == 3.0
    assert pdmy_full.parameters["rho"] == 2000.0
    assert pdmy_full.parameters["noYieldSurf"] == 30.0
    assert pdmy_full.parameters["e"] == 0.55
    assert pdmy_full.parameters["cs1"] == 0.95
    assert pdmy_full.parameters["pa"] == 101.0e3
    assert pdmy_full.parameters["c"] == 500.0
    assert any(
        issue.construct == "PressureDependMultiYield material stage"
        for issue in result.issues
    )

    asd = result.project.nd_materials[29]
    assert asd.material_type == "ASDConcrete3D"
    assert asd.parameters["E"] == 30.0e9
    assert asd.parameters["rho"] == 2400.0
    assert asd.parameters["fc"] == 30.0e6
    assert asd.parameters["ft"] == 3.0e6
    assert asd.parameters["implex"] == 1.0
    assert asd.parameters["Kc"] == 0.7
    assert asd.parameters["cdf"] == 0.0

    ra = result.project.nd_materials[30]
    assert ra.material_type == "OrthotropicRAConcrete"
    assert ra.parameters["conc"] == 4.0
    assert ra.parameters["ecr"] == 0.00008
    assert ra.parameters["ec"] == -0.002
    assert ra.parameters["DamageCte1"] == 0.175
    assert ra.parameters["DamageCte2"] == 0.5
    assert result.project.nd_materials_using_material(4) == [30]


def test_importer_rejects_advanced_asd_concrete_backbone():
    source = """
import openseespy.opensees as ops

ops.nDMaterial(
    'ASDConcrete3D', 64,
    30.0e9, 0.2,
    '-fc', 30.0e6,
    '-ft', 3.0e6,
    '-Te', [0.0, 0.0001, 0.001],
    '-Ts', [0.0, 3.0e6, 0.0]
)
"""

    result = import_openseespy_source(
        source,
        source_name="advanced_asd_concrete.py",
        units={"length": "m", "force": "N", "time": "s"},
    )

    assert 64 not in result.project.nd_materials
    assert result.unsupported_count == 1
    issue = next(
        item
        for item in result.issues
        if item.construct == "ASDConcrete3D advanced options"
    )
    assert "Custom backbone" in issue.message


def test_importer_rejects_missing_orthotropic_ra_dependency():
    source = """
import openseespy.opensees as ops
ops.nDMaterial(
    'OrthotropicRAConcrete', 65,
    99, 0.00008, -0.002, 0.0
)
"""

    result = import_openseespy_source(
        source,
        source_name="missing_ra_dependency.py",
        units={"length": "m", "force": "N", "time": "s"},
    )

    assert 65 not in result.project.nd_materials
    assert result.error_count >= 1
    assert any(
        "missing uniaxial material" in issue.message
        for issue in result.issues
    )


def test_importer_rejects_custom_pressure_independ_surfaces():
    source = """
import openseespy.opensees as ops

ops.nDMaterial(
    'PressureIndependMultiYield', 61,
    2, 1500.0, 60.0e6, 300.0e6, 37.0e3, 0.10,
    0.0, 80.0e3, 0.0, -3,
    0.001, 0.9, 0.01, 0.5, 0.10, 0.1
)
"""

    result = import_openseespy_source(
        source,
        source_name="custom_pimy.py",
        units={"length": "m", "force": "N", "time": "s"},
    )

    assert 61 not in result.project.nd_materials
    assert result.unsupported_count == 1
    issue = next(
        item
        for item in result.issues
        if "custom yield surfaces" in item.construct
    )
    assert "automatic-surface form only" in issue.message


def test_importer_rejects_custom_pressure_depend_surfaces():
    source = """
import openseespy.opensees as ops

ops.nDMaterial(
    'PressureDependMultiYield', 62,
    2, 1900.0, 75.0e6, 200.0e6,
    33.0, 0.10, 80.0e3, 0.5, 27.0,
    0.07, 0.4, 2.0, 10.0e3, 0.01, 1.0,
    -3, 0.001, 0.9, 0.01, 0.5, 0.10, 0.1
)
"""

    result = import_openseespy_source(
        source,
        source_name="custom_pdmy.py",
        units={"length": "m", "force": "N", "time": "s"},
    )

    assert 62 not in result.project.nd_materials
    assert result.unsupported_count == 1
    issue = next(
        item
        for item in result.issues
        if "PressureDependMultiYield custom yield surfaces"
        in item.construct
    )
    assert "automatic-surface form only" in issue.message


def test_importer_rejects_pressure_depend_extra_arguments():
    source = """
import openseespy.opensees as ops

ops.nDMaterial(
    'PressureDependMultiYield', 63,
    2, 1900.0, 75.0e6, 200.0e6,
    33.0, 0.10, 80.0e3, 0.5, 27.0,
    0.07, 0.4, 2.0, 10.0e3, 0.01, 1.0,
    20, 0.7, 0.9, 0.02, 0.7, 101.0e3, 0.3e3,
    999.0
)
"""

    result = import_openseespy_source(
        source,
        source_name="extra_pdmy.py",
        units={"length": "m", "force": "N", "time": "s"},
    )

    assert 63 not in result.project.nd_materials
    assert result.unsupported_count == 1
    assert any(
        issue.construct == "PressureDependMultiYield extra arguments"
        for issue in result.issues
    )


def test_importer_recovers_set_num_threads():
    source = """
import openseespy.opensees as ops
ops.model('basic', '-ndm', 2, '-ndf', 3)
ops.node(1, 0.0, 0.0)
ops.fix(1, 1, 1, 1)
ops.setNumThreads(6)
ops.constraints('Plain')
ops.numberer('RCM')
ops.system('UmfPack')
ops.test('NormDispIncr', 1e-8, 20)
ops.algorithm('Newton')
ops.integrator('LoadControl', 1.0)
ops.analysis('Static')
ops.analyze(1)
"""
    imported = import_openseespy_source(
        source,
        source_name="threaded_static.py",
    )

    assert imported.error_count == 0
    analysis = imported.project.analyses[
        imported.project.active_analysis_tag
    ]
    assert analysis.execution_mode == "Multi-thread"
    assert analysis.num_threads == 6
