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
