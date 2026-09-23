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
analyze(2, 0.01)
history = []
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
