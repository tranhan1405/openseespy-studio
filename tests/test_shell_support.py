from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest

from openseespy_studio.generator import (
    recorder_to_openseespy,
    section_to_openseespy,
    to_openseespy,
)
from openseespy_studio.importer import import_openseespy_source
from openseespy_studio.mass_source import evaluate_mass_source
from openseespy_studio.model import (
    SHELL_ELEMENT_TYPES,
    StructuralModel,
    shell_surface_geometry,
)
from openseespy_studio.project import (
    AnalysisSettingsData,
    ElementLoadData,
    LoadPatternData,
    MassSourceData,
    ProjectDatabase,
    RecorderData,
    SectionData,
    SolutionResultData,
    TimeSeriesData,
)
from openseespy_studio.result_catalog import result_choices_for_analysis
from openseespy_studio.shell_mesh import ShellMeshSpec, build_shell_mesh
from openseespy_studio.ui.main_window import MainWindow
from openseespy_studio.ui.results_panel import ResultsPanel
from openseespy_studio.ui.shell_dialog import ShellMeshDialog
from openseespy_studio.ui.viewport import ModelViewport
from openseespy_studio.validation import validate_project


def _shell_model(*, corotational: bool = False) -> StructuralModel:
    model = StructuralModel("shell", ndm=3, ndf=6)
    model.add_node(1, 0.0, 0.0, 0.0)
    model.add_node(2, 2.0, 0.0, 0.0)
    model.add_node(3, 2.0, 1.0, 0.0)
    model.add_node(4, 0.0, 1.0, 0.0)
    model.add_element(
        10,
        1,
        2,
        element_type="ASDShellQ4",
        section_tag=7,
        group="shell",
        k=3,
        l=4,
        shell_corotational=corotational,
    )
    return model


def _shell_section(*, rho: float = 0.0) -> SectionData:
    return SectionData(
        7,
        "Elastic shell",
        "ElasticMembranePlate",
        parameters={
            "E": 30.0e9,
            "nu": 0.2,
            "h": 0.18,
            "rho": rho,
            "EpModifier": 1.0,
        },
    )


def test_shell_element_round_trip_preserves_four_node_topology():
    model = _shell_model(corotational=True)

    restored = StructuralModel.from_dict(model.to_dict())
    element = restored.elements[10]

    assert element.element_type == "ASDShellQ4"
    assert element.node_tags() == (1, 2, 3, 4)
    assert element.section_tag == 7
    assert element.transf_tag is None
    assert element.shell_corotational is True
    assert restored.to_dict() == model.to_dict()


def test_shell_requires_3d_six_dof_model_and_four_distinct_nodes():
    model = StructuralModel("2d", ndm=2, ndf=3)
    for tag, x, y in (
        (1, 0.0, 0.0),
        (2, 1.0, 0.0),
        (3, 1.0, 1.0),
        (4, 0.0, 1.0),
    ):
        model.add_node(tag, x, y)

    with pytest.raises(ValueError, match=r"requires a 3D/6DOF model"):
        model.add_element(
            1,
            1,
            2,
            element_type="ASDShellQ4",
            k=3,
            l=4,
        )

    model3d = StructuralModel("3d", ndm=3, ndf=6)
    for tag, xyz in {
        1: (0.0, 0.0, 0.0),
        2: (1.0, 0.0, 0.0),
        3: (1.0, 1.0, 0.0),
    }.items():
        model3d.add_node(tag, *xyz)

    with pytest.raises(ValueError, match=r"four distinct node tags"):
        model3d.add_element(
            1,
            1,
            2,
            element_type="ASDShellQ4",
            k=3,
            l=3,
        )


def test_shell_node_delete_cascades_surface_element():
    model = _shell_model()

    model.remove_node(3, cascade=True)

    assert 3 not in model.nodes
    assert 10 not in model.elements


def test_elastic_membrane_plate_section_validates_and_generates():
    section = _shell_section()

    line = section_to_openseespy(
        section,
        units={"length": "m", "force": "N", "time": "s"},
    )[0]

    assert line.startswith(
        "ops.section('ElasticMembranePlateSection', 7, 3e+10, 0.2, 0.18"
    )
    assert line.endswith(", 0, 1)")

    with pytest.raises(ValueError, match=r"Poisson ratio"):
        SectionData(
            8,
            "Bad shell",
            "ElasticMembranePlate",
            parameters={
                "E": 30.0e9,
                "nu": 0.5,
                "h": 0.18,
                "rho": 0.0,
                "EpModifier": 1.0,
            },
        )


def test_shell_generator_emits_asd_shell_q4_without_transformation():
    model = _shell_model(corotational=True)
    section = _shell_section()

    code = to_openseespy(
        model,
        sections={7: section},
        units={"length": "m", "force": "N", "time": "s"},
    )

    assert "# ERROR:" not in code
    assert "ops.geomTransf(" not in code
    assert (
        "ops.element('ASDShellQ4', 10, 1, 2, 3, 4, 7, '-corotational')"
        in code
    )


@pytest.mark.parametrize(
    "formulation",
    sorted(SHELL_ELEMENT_TYPES),
)
def test_all_initial_quad_shell_formulations_generate(formulation: str):
    model = _shell_model()
    model.elements[10].element_type = formulation
    model.elements[10].shell_corotational = False

    code = to_openseespy(
        model,
        sections={7: _shell_section()},
        units={"length": "m", "force": "N", "time": "s"},
    )

    assert (
        f"ops.element('{formulation}', 10, 1, 2, 3, 4, 7)"
        in code
    )


def test_model_check_accepts_shell_without_geometric_transformation():
    project = ProjectDatabase(
        name="shell-check",
        model=_shell_model(),
    )
    project.add_section(_shell_section())
    project.model.set_fixity(1, (1, 1, 1, 1, 1, 1))
    project.model.set_fixity(4, (1, 1, 1, 1, 1, 1))

    issues = validate_project(project)
    shell_errors = [
        issue
        for issue in issues
        if issue.severity == "ERROR"
        and issue.entity_kind == "element"
        and issue.entity_tag == 10
    ]

    assert not shell_errors


def test_shell_section_density_counts_as_dynamic_mass():
    project = ProjectDatabase(
        name="shell-mass",
        model=_shell_model(),
    )
    project.add_section(_shell_section(rho=2500.0))

    holder = SimpleNamespace(
        project=project,
        model=project.model,
    )

    assert MainWindow._has_dynamic_mass(holder) is True


def test_shell_ui_routes_exist_and_are_frame_safe():
    create_source = inspect.getsource(MainWindow._create_shell)
    assert "_ensure_node_count(4" in create_source
    assert "_create_shell_section" in create_source
    assert "ShellElementDialog" in create_source

    tree_source = inspect.getsource(MainWindow._show_tree_context_menu)
    assert 'kind == "surfaces_root"' in tree_source
    assert "is_shell_group" in tree_source
    assert "_assign_shell_section_to_selection" in tree_source

    viewport_source = inspect.getsource(ModelViewport._combined_element_meshes)
    assert "_batched_shell_mesh" in viewport_source
    assert 'combined["shell"]' in viewport_source


def test_shell_generated_script_round_trips_through_importer():
    model = _shell_model(corotational=True)
    script = to_openseespy(
        model,
        sections={7: _shell_section(rho=2500.0)},
        units={"length": "m", "force": "N", "time": "s"},
    )

    imported = import_openseespy_source(
        script,
        source_name="shell-roundtrip.py",
        units={"length": "m", "force": "N", "time": "s"},
    )

    assert imported.error_count == 0
    section = imported.project.sections[7]
    assert section.section_type == "ElasticMembranePlate"
    assert section.parameters["E"] == pytest.approx(30.0e9)
    assert section.parameters["h"] == pytest.approx(0.18)
    assert section.parameters["rho"] == pytest.approx(2500.0)

    element = imported.project.model.elements[10]
    assert element.element_type == "ASDShellQ4"
    assert element.node_tags() == (1, 2, 3, 4)
    assert element.section_tag == 7
    assert element.shell_corotational is True


def test_structured_shell_mesh_reuses_corners_and_builds_quads():
    model = StructuralModel("mesh", ndm=3, ndf=6)
    model.add_node(1, 0.0, 0.0, 0.0)
    model.add_node(2, 4.0, 0.0, 0.0)
    model.add_node(3, 4.0, 2.0, 0.0)
    model.add_node(4, 0.0, 2.0, 0.0)
    project = ProjectDatabase(name="mesh", model=model)
    project.add_section(_shell_section())

    result = build_shell_mesh(
        project,
        ShellMeshSpec(
            corner_nodes=(1, 2, 3, 4),
            divisions_u=2,
            divisions_v=2,
            formulation="ASDShellQ4",
            section_tag=7,
        ),
    )

    assert len(result.element_tags) == 4
    assert len(result.node_tags) == 5
    assert len(project.model.nodes) == 9
    assert len(project.model.elements) == 4
    assert result.grid[0][0] == 1
    assert result.grid[0][-1] == 2
    assert result.grid[-1][-1] == 3
    assert result.grid[-1][0] == 4

    center = project.model.nodes[result.grid[1][1]]
    assert center.xyz == pytest.approx((2.0, 1.0, 0.0))

    for element in project.model.elements.values():
        assert element.element_type == "ASDShellQ4"
        assert len(element.node_tags()) == 4
        assert element.section_tag == 7


def test_structured_shell_mesh_handles_warped_surface_bilinearly():
    model = StructuralModel("warped", ndm=3, ndf=6)
    model.add_node(1, 0.0, 0.0, 0.0)
    model.add_node(2, 2.0, 0.0, 0.0)
    model.add_node(3, 2.0, 2.0, 1.0)
    model.add_node(4, 0.0, 2.0, 0.0)
    project = ProjectDatabase(name="warped", model=model)
    project.add_section(_shell_section())

    result = build_shell_mesh(
        project,
        ShellMeshSpec(
            corner_nodes=(1, 2, 3, 4),
            divisions_u=2,
            divisions_v=2,
            formulation="ASDShellQ4",
            section_tag=7,
        ),
    )

    center = project.model.nodes[result.grid[1][1]]
    assert center.xyz == pytest.approx((1.0, 1.0, 0.25))


def test_shell_mesh_ui_route_is_exposed():
    source = inspect.getsource(MainWindow._create_shell_mesh)
    assert "_ensure_node_count(4" in source
    assert "_create_shell_section" in source
    assert "ShellMeshDialog" in source
    assert "build_shell_mesh" in source


def test_shell_mesh_failure_rolls_back_generated_nodes_and_elements():
    model = StructuralModel("bad-mesh", ndm=3, ndf=6)
    # Collinear corners force zero-area generated shell elements.
    model.add_node(1, 0.0, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0, 0.0)
    model.add_node(3, 2.0, 0.0, 0.0)
    model.add_node(4, 3.0, 0.0, 0.0)
    project = ProjectDatabase(name="bad-mesh", model=model)
    project.add_section(_shell_section())

    before_nodes = set(project.model.nodes)
    before_elements = set(project.model.elements)

    with pytest.raises(ValueError, match=r"zero or near-zero area"):
        build_shell_mesh(
            project,
            ShellMeshSpec(
                corner_nodes=(1, 2, 3, 4),
                divisions_u=2,
                divisions_v=2,
                formulation="ASDShellQ4",
                section_tag=7,
            ),
        )

    assert set(project.model.nodes) == before_nodes
    assert set(project.model.elements) == before_elements



def test_shell_result_catalog_includes_force_and_deformation_only_nonmodal():
    static_choices = result_choices_for_analysis("Static")
    static_types = {choice.result_type for choice in static_choices}
    assert "ShellForce" in static_types
    assert "ShellDeformation" in static_types

    modal_types = {
        choice.result_type
        for choice in result_choices_for_analysis("Modal")
    }
    assert "ShellForce" not in modal_types
    assert "ShellDeformation" not in modal_types


def test_shell_deformation_result_request_validates_scope_and_component():
    project = ProjectDatabase(
        name="shell-result",
        model=_shell_model(),
    )
    project.add_section(_shell_section())
    project.add_analysis(
        AnalysisSettingsData(
            1,
            "Static shell",
            analysis_type="Static",
        )
    )

    result = SolutionResultData(
        tag=1,
        analysis_tag=1,
        name="Shell Exx",
        result_type="ShellDeformation",
        element_scope=[10],
        settings={"component": "Exx"},
    )
    project.add_solution_result(result)
    assert project.solution_results[1].result_type == "ShellDeformation"

    with pytest.raises(
        ValueError,
        match=r"Unsupported ShellDeformation component",
    ):
        project.add_solution_result(
            SolutionResultData(
                tag=2,
                analysis_tag=1,
                name="Bad shell deformation",
                result_type="ShellDeformation",
                element_scope=[10],
                settings={"component": "BAD"},
            )
        )


def test_shell_generator_captures_force_and_deformation_gauss_points():
    code = to_openseespy(
        _shell_model(),
        sections={7: _shell_section()},
        analyses={
            1: AnalysisSettingsData(
                1,
                "Static shell capture",
                analysis_type="Static",
                steps=1,
                load_increment=1.0,
            )
        },
        active_analysis_tag=1,
        units={"length": "m", "force": "N", "time": "s"},
    )

    assert "_studio_shell_section_forces" in code
    assert "_studio_shell_section_deformations" in code
    assert "'material', _studio_gp, 'force'" in code
    assert "'material', _studio_gp, 'deformation'" in code
    assert "'shell_section_forces': _studio_shell_section_forces" in code
    assert (
        "'shell_section_deformations': "
        "_studio_shell_section_deformations"
    ) in code


def test_shell_deformation_ui_routes_and_tables_exist():
    prepare_source = inspect.getsource(
        MainWindow._prepare_solution_result_prerequisites
    )
    assert '{"ShellForce", "ShellDeformation"}' in prepare_source

    render_source = inspect.getsource(
        MainWindow._render_result_data
    )
    assert "show_shell_deformation_contour" in render_source

    viewport_source = inspect.getsource(
        ModelViewport.show_shell_deformation_contour
    )
    assert "shell_section_deformations" in viewport_source
    assert "Kxx" in viewport_source

    build_source = inspect.getsource(ResultsPanel._build_shell_tab)
    populate_source = inspect.getsource(
        ResultsPanel._populate_shell_results
    )
    assert "shell_deformation_gp_table" in build_source
    assert "Membrane Strain" in build_source
    assert "shell_section_deformations" in populate_source


def test_shell_deformed_and_mode_shape_use_four_node_surface_topology():
    source = inspect.getsource(ModelViewport._show_vector_overlay)
    assert "element.node_tags()" in source
    assert "element.element_type in SHELL_ELEMENT_TYPES" in source
    assert "shell_points" in source
    assert "faces=np.asarray" in source
    assert "scoped_nodes.update(element.node_tags())" in source

    zoom_source = inspect.getsource(ModelViewport.zoom_to_selection)
    assert "for node_tag in element.node_tags()" in zoom_source


def test_shell_recorder_generates_and_round_trips_native_material_gp_query():
    project = ProjectDatabase(
        name="shell-recorder",
        model=_shell_model(),
    )
    project.add_section(_shell_section())
    recorder = RecorderData(
        tag=1,
        name="Shell GP2 deformation",
        recorder_type="Shell",
        target_tags=[10],
        response="deformation",
        section_number=2,
        file_name="recorders/shell_gp2.out",
        include_time=True,
    )
    project.add_recorder(recorder)

    lines = recorder_to_openseespy(recorder)
    command = lines[-1]
    assert "'material', 2, 'deformation'" in command
    assert "'-ele', 10" in command

    script = to_openseespy(
        project.model,
        sections=project.sections,
        recorders=project.recorders,
        units={"length": "m", "force": "N", "time": "s"},
    )
    imported = import_openseespy_source(
        script,
        source_name="shell-recorder-roundtrip.py",
        units={"length": "m", "force": "N", "time": "s"},
    )

    assert imported.error_count == 0
    restored = next(iter(imported.project.recorders.values()))
    assert restored.recorder_type == "Shell"
    assert restored.target_tags == [10]
    assert restored.section_number == 2
    assert restored.response == "deformation"


def test_shell_recorder_rejects_non_shell_targets_and_invalid_gp():
    project = ProjectDatabase(
        name="shell-recorder-validation",
        model=_shell_model(),
    )
    project.add_section(_shell_section())

    with pytest.raises(ValueError, match=r"Gauss point"):
        RecorderData(
            tag=1,
            name="Bad GP",
            recorder_type="Shell",
            target_tags=[10],
            response="force",
            section_number=5,
        )

    project.model.add_node(5, 0.0, 0.0, 2.0)
    project.model.add_element(
        20,
        1,
        5,
        element_type="truss",
        group="truss",
        truss_area=0.01,
        truss_material_tag=1,
    )
    recorder = RecorderData(
        tag=2,
        name="Wrong target",
        recorder_type="Shell",
        target_tags=[20],
        response="force",
        section_number=1,
    )
    with pytest.raises(ValueError, match=r"Shell recorders require Shell"):
        project.add_recorder(recorder)


def _shell_pressure_project(
    pressure: float = -1000.0,
) -> ProjectDatabase:
    project = ProjectDatabase(
        name="shell-pressure",
        model=_shell_model(),
    )
    project.units = {"length": "m", "force": "N", "time": "s"}
    project.add_section(_shell_section())
    project.add_time_series(
        TimeSeriesData(1, "Linear", "Linear", factor=1.0)
    )
    project.add_load_pattern(
        LoadPatternData(
            1,
            "Pressure",
            "Plain",
            time_series_tag=1,
        )
    )
    project.add_element_load(
        ElementLoadData(
            1,
            "Pressure",
            1,
            10,
            "SurfacePressure",
            pressure=pressure,
        )
    )
    return project


def test_shell_surface_pressure_round_trip_and_native_generation():
    project = _shell_pressure_project(-1250.0)
    restored = ProjectDatabase.from_dict(project.to_dict())
    load = restored.element_loads[1]
    assert load.load_type == "SurfacePressure"
    assert load.pressure == pytest.approx(-1250.0)

    script = to_openseespy(
        project.model,
        sections=project.sections,
        time_series=project.time_series,
        load_patterns=project.load_patterns,
        element_loads=project.element_loads,
        units=project.units,
    )
    assert "ops.element('SurfaceLoad', 11, 1, 2, 3, 4, -1250)" in script
    assert "ops.eleLoad('-ele', 11, '-type', '-surfaceLoad')" in script

    imported = import_openseespy_source(
        script,
        source_name="surface-pressure-roundtrip.py",
        units=project.units,
    )
    assert imported.error_count == 0
    assert len(imported.project.element_loads) == 1
    imported_load = next(iter(imported.project.element_loads.values()))
    assert imported_load.load_type == "SurfacePressure"
    assert imported_load.element_tag == 10
    assert imported_load.pressure == pytest.approx(-1250.0)


def test_shell_surface_pressure_reverses_sign_when_helper_orientation_reverses():
    source = """
import openseespy.opensees as ops
ops.model('basic', '-ndm', 3, '-ndf', 6)
ops.node(1, 0, 0, 0)
ops.node(2, 2, 0, 0)
ops.node(3, 2, 1, 0)
ops.node(4, 0, 1, 0)
ops.section('ElasticMembranePlateSection', 7, 30000000000, 0.2, 0.18, 0)
ops.element('ASDShellQ4', 10, 1, 2, 3, 4, 7)
ops.timeSeries('Linear', 1, '-factor', 1)
ops.pattern('Plain', 1, 1)
ops.element('SurfaceLoad', 11, 4, 3, 2, 1, -1000)
ops.eleLoad('-ele', 11, '-type', '-surfaceLoad')
"""
    imported = import_openseespy_source(
        source,
        source_name="reverse-pressure.py",
        units={"length": "m", "force": "N", "time": "s"},
    )
    assert imported.error_count == 0
    load = next(iter(imported.project.element_loads.values()))
    assert load.pressure == pytest.approx(1000.0)


def test_shell_pressure_and_shell_self_mass_feed_mass_source():
    project = _shell_pressure_project(-1000.0)
    project.update_section(
        7,
        _shell_section(rho=2500.0),
    )
    source = MassSourceData(
        1,
        "Shell mass",
        include_self_mass=True,
        load_factors={1: 1.0},
        gravity_axis=3,
        directions=(1, 2),
    )
    summary = evaluate_mass_source(project, source)

    area = 2.0
    expected_self = 2500.0 * 0.18 * area
    expected_load = 1000.0 * area / 9.80665
    assert summary.self_mass == pytest.approx(
        expected_self,
        rel=1.0e-10,
    )
    assert summary.load_mass == pytest.approx(
        expected_load,
        rel=1.0e-10,
    )
    assert summary.total_mass == pytest.approx(
        expected_self + expected_load,
        rel=1.0e-10,
    )
    assert all(
        value == pytest.approx(summary.total_mass / 4.0)
        for value in summary.nodal_mass.values()
    )


def test_shell_pressure_ui_and_viewport_routes_exist():
    source = inspect.getsource(MainWindow._create_shell_pressure)
    assert 'allowed_load_types={"SurfacePressure"}' in source
    assert "SHELL_ELEMENT_TYPES" in source

    context_source = inspect.getsource(
        MainWindow._show_tree_context_menu
    )
    assert "Create Surface Pressure..." in context_source

    viewport_source = inspect.getsource(ModelViewport._draw_element_loads)
    assert 'load.load_type == "SurfacePressure"' in viewport_source
    assert "shell_surface_geometry" in viewport_source
    assert "+outward / -inward" in viewport_source


def test_structured_shell_mesh_propagates_asd_local_x():
    model = StructuralModel("mesh-local-x", ndm=3, ndf=6)
    model.add_node(1, 0.0, 0.0, 0.0)
    model.add_node(2, 2.0, 0.0, 0.0)
    model.add_node(3, 2.0, 2.0, 0.0)
    model.add_node(4, 0.0, 2.0, 0.0)
    project = ProjectDatabase(name="mesh-local-x", model=model)
    project.add_section(_shell_section())

    result = build_shell_mesh(
        project,
        ShellMeshSpec(
            corner_nodes=(1, 2, 3, 4),
            divisions_u=2,
            divisions_v=1,
            formulation="ASDShellQ4",
            section_tag=7,
            local_x=(0.0, 1.0, 0.0),
        ),
    )

    assert len(result.element_tags) == 2
    assert all(
        project.model.elements[tag].shell_local_x == (0.0, 1.0, 0.0)
        for tag in result.element_tags
    )

    script = to_openseespy(
        project.model,
        sections=project.sections,
        units={"length": "m", "force": "N", "time": "s"},
    )
    assert script.count("'-local', 0, 1, 0") == 2


def test_shell_local_x_parallel_to_normal_is_rejected():
    project = ProjectDatabase(
        name="invalid-local-x",
        model=_shell_model(),
    )
    project.add_section(_shell_section())
    element = project.model.elements[10]
    element.shell_local_x = (0.0, 0.0, 1.0)

    with pytest.raises(
        ValueError,
        match=r"parallel to the shell normal",
    ):
        project.validate_element_state(10)



def test_asd_shell_advanced_options_round_trip_generate_and_import():
    model = StructuralModel("advanced-asd-shell", ndm=3, ndf=6)
    model.add_node(1, 0.0, 0.0, 0.0)
    model.add_node(2, 2.0, 0.0, 0.0)
    model.add_node(3, 2.0, 1.0, 0.0)
    model.add_node(4, 0.0, 1.0, 0.0)
    model.add_element(
        10,
        1,
        2,
        element_type="ASDShellQ4",
        section_tag=7,
        group="shell",
        k=3,
        l=4,
        shell_corotational=True,
        shell_local_x=(0.0, 1.0, 0.0),
        shell_no_eas=True,
        shell_drilling_stab=0.025,
        shell_drilling_nl=True,
    )

    restored = StructuralModel.from_dict(model.to_dict())
    element = restored.elements[10]
    assert element.shell_corotational is True
    assert element.shell_local_x == (0.0, 1.0, 0.0)
    assert element.shell_no_eas is True
    assert element.shell_drilling_stab == pytest.approx(0.025)
    assert element.shell_drilling_nl is True

    code = to_openseespy(
        restored,
        sections={7: _shell_section()},
        units={"length": "m", "force": "N", "time": "s"},
    )
    shell_line = next(
        line for line in code.splitlines()
        if "ops.element('ASDShellQ4', 10" in line
    )
    assert "'-corotational'" in shell_line
    assert "'-noeas'" in shell_line
    assert "'-drillingStab', 0.025" in shell_line
    assert "'-drillingNL'" in shell_line
    assert "'-local', 0, 1, 0" in shell_line

    imported = import_openseespy_source(
        code,
        source_name="advanced-asd-shell.py",
        units={"length": "m", "force": "N", "time": "s"},
    )
    assert imported.error_count == 0
    imported_element = imported.project.model.elements[10]
    assert imported_element.shell_no_eas is True
    assert imported_element.shell_drilling_stab == pytest.approx(0.025)
    assert imported_element.shell_drilling_nl is True
    assert imported_element.shell_local_x == (0.0, 1.0, 0.0)


def test_structured_shell_mesh_propagates_advanced_asd_options():
    model = StructuralModel("advanced-mesh", ndm=3, ndf=6)
    model.add_node(1, 0.0, 0.0, 0.0)
    model.add_node(2, 2.0, 0.0, 0.0)
    model.add_node(3, 2.0, 2.0, 0.0)
    model.add_node(4, 0.0, 2.0, 0.0)
    project = ProjectDatabase(name="advanced-mesh", model=model)
    project.add_section(_shell_section())

    result = build_shell_mesh(
        project,
        ShellMeshSpec(
            corner_nodes=(1, 2, 3, 4),
            divisions_u=2,
            divisions_v=2,
            formulation="ASDShellQ4",
            section_tag=7,
            no_eas=True,
            drilling_stab=0.02,
            drilling_nl=True,
        ),
    )

    assert len(result.element_tags) == 4
    for tag in result.element_tags:
        element = project.model.elements[tag]
        assert element.shell_no_eas is True
        assert element.shell_drilling_stab == pytest.approx(0.02)
        assert element.shell_drilling_nl is True


def test_non_asd_shell_discards_asd_only_options():
    model = StructuralModel("mitc-shell", ndm=3, ndf=6)
    model.add_node(1, 0.0, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0, 0.0)
    model.add_node(3, 1.0, 1.0, 0.0)
    model.add_node(4, 0.0, 1.0, 0.0)
    element = model.add_element(
        1,
        1,
        2,
        element_type="ShellMITC4",
        section_tag=7,
        k=3,
        l=4,
        shell_corotational=True,
        shell_local_x=(1.0, 0.0, 0.0),
        shell_no_eas=True,
        shell_drilling_stab=0.02,
        shell_drilling_nl=True,
    )

    assert element.shell_corotational is False
    assert element.shell_local_x is None
    assert element.shell_no_eas is False
    assert element.shell_drilling_stab is None
    assert element.shell_drilling_nl is False


def test_asd_shell_rejects_invalid_drilling_stabilization():
    model = StructuralModel("invalid-drilling", ndm=3, ndf=6)
    model.add_node(1, 0.0, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0, 0.0)
    model.add_node(3, 1.0, 1.0, 0.0)
    model.add_node(4, 0.0, 1.0, 0.0)

    with pytest.raises(ValueError, match=r"drilling stabilization"):
        model.add_element(
            1,
            1,
            2,
            element_type="ASDShellQ4",
            section_tag=7,
            k=3,
            l=4,
            shell_drilling_stab=-0.01,
        )


def _invalid_shell_project(points) -> ProjectDatabase:
    model = StructuralModel("invalid-shell-order", ndm=3, ndf=6)
    for tag, point in enumerate(points, start=1):
        model.add_node(tag, *point)
    model.add_element(
        10,
        1,
        2,
        element_type="ASDShellQ4",
        section_tag=7,
        group="shell",
        k=3,
        l=4,
    )
    project = ProjectDatabase(name="invalid-shell-order", model=model)
    project.add_section(_shell_section())
    return project


def test_shell_core_rejects_self_intersecting_quadrilateral_order():
    project = _invalid_shell_project([
        (0.0, 0.0, 0.0),
        (2.0, 0.0, 0.0),
        (0.5, 1.0, 0.0),
        (2.0, 1.5, 0.0),
    ])

    with pytest.raises(
        ValueError,
        match=r"self-intersecting|crossed or degenerate",
    ):
        project.validate_element_state(10)


def test_shell_core_rejects_concave_quadrilateral_order():
    project = _invalid_shell_project([
        (0.0, 0.0, 0.0),
        (2.0, 0.0, 0.0),
        (0.7, 0.4, 0.0),
        (0.0, 1.5, 0.0),
    ])

    with pytest.raises(ValueError, match=r"concave"):
        project.validate_element_state(10)


def test_model_check_reports_invalid_shell_boundary_ordering():
    project = _invalid_shell_project([
        (0.0, 0.0, 0.0),
        (2.0, 0.0, 0.0),
        (0.5, 1.0, 0.0),
        (2.0, 1.5, 0.0),
    ])

    issues = validate_project(project)
    shell_geometry = [
        issue for issue in issues
        if issue.category == "Shell geometry"
    ]
    assert shell_geometry
    assert any(
        "quadrilateral boundary" in issue.message
        for issue in shell_geometry
    )
    assert any(
        "clockwise or counter-clockwise" in issue.suggestion
        for issue in shell_geometry
    )


def test_shell_properties_expose_advanced_asd_controls_and_safe_edits():
    source = inspect.getsource(MainWindow._show_entity_properties)
    assert '"Enhanced assumed strain"' in source
    assert '"Drilling stabilization"' in source
    assert '"Nonlinear drilling"' in source
    assert '"id": "shell_corotational"' in source
    assert '"id": "shell_local_x"' in source
    assert '"id": "shell_no_eas"' in source
    assert '"id": "shell_drilling_stab"' in source
    assert '"id": "shell_drilling_nl"' in source

    edit_source = inspect.getsource(MainWindow._apply_direct_property_edit)
    assert '"shell_corotational"' in edit_source
    assert '"shell_local_x"' in edit_source
    assert '"shell_no_eas"' in edit_source
    assert '"shell_drilling_stab"' in edit_source
    assert '"shell_drilling_nl"' in edit_source
    assert "Edit shell topology and formulation" in edit_source


def test_model_check_warns_on_high_shell_aspect_ratio():
    model = StructuralModel("shell-quality-aspect", ndm=3, ndf=6)
    model.add_node(1, 0.0, 0.0, 0.0)
    model.add_node(2, 20.0, 0.0, 0.0)
    model.add_node(3, 20.0, 1.0, 0.0)
    model.add_node(4, 0.0, 1.0, 0.0)
    model.add_element(
        10, 1, 2,
        element_type="ASDShellQ4",
        section_tag=7,
        group="shell",
        k=3,
        l=4,
    )
    project = ProjectDatabase(name="shell-quality-aspect", model=model)
    project.add_section(_shell_section())

    issues = validate_project(project)
    quality = [
        issue for issue in issues
        if issue.category == "Shell quality"
    ]
    assert any("aspect ratio" in issue.message for issue in quality)


def test_model_check_warns_on_shell_warpage():
    model = StructuralModel("shell-quality-warpage", ndm=3, ndf=6)
    model.add_node(1, 0.0, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0, 0.0)
    model.add_node(3, 1.0, 1.0, 0.0)
    model.add_node(4, 0.0, 1.0, 0.5)
    model.add_element(
        10, 1, 2,
        element_type="ASDShellQ4",
        section_tag=7,
        group="shell",
        k=3,
        l=4,
    )
    project = ProjectDatabase(name="shell-quality-warpage", model=model)
    project.add_section(_shell_section())

    issues = validate_project(project)
    quality = [
        issue for issue in issues
        if issue.category == "Shell quality"
    ]
    assert any("warpage angle" in issue.message for issue in quality)


def _two_shell_orientation_project(*, inconsistent: bool) -> ProjectDatabase:
    model = StructuralModel("shell-orientation", ndm=3, ndf=6)
    coordinates = {
        1: (0.0, 0.0, 0.0),
        2: (1.0, 0.0, 0.0),
        3: (1.0, 1.0, 0.0),
        4: (0.0, 1.0, 0.0),
        5: (2.0, 0.0, 0.0),
        6: (2.0, 1.0, 0.0),
    }
    for tag, xyz in coordinates.items():
        model.add_node(tag, *xyz)
    model.add_element(
        10, 1, 2,
        element_type="ASDShellQ4",
        section_tag=7,
        group="shell",
        k=3,
        l=4,
    )
    if inconsistent:
        nodes = (3, 6, 5, 2)
    else:
        nodes = (2, 5, 6, 3)
    model.add_element(
        20, nodes[0], nodes[1],
        element_type="ASDShellQ4",
        section_tag=7,
        group="shell",
        k=nodes[2],
        l=nodes[3],
    )
    project = ProjectDatabase(name="shell-orientation", model=model)
    project.add_section(_shell_section())
    return project


def test_model_check_detects_adjacent_shell_normal_inconsistency():
    inconsistent = _two_shell_orientation_project(inconsistent=True)
    issues = validate_project(inconsistent)
    orientation = [
        issue for issue in issues
        if issue.category == "Shell orientation"
    ]
    assert len(orientation) == 1
    assert "shared edge 2-3" in orientation[0].message
    assert "surface normals are inconsistent" in orientation[0].message

    consistent = _two_shell_orientation_project(inconsistent=False)
    assert not [
        issue for issue in validate_project(consistent)
        if issue.category == "Shell orientation"
    ]


def test_reverse_shell_orientation_flips_order_and_clears_orientation_warning():
    project = _two_shell_orientation_project(inconsistent=True)
    element = project.model.elements[20]
    before = element.node_tags()

    updated = project.model.reverse_shell_orientation([20])
    project.validate_element_state(20)

    assert updated == [20]
    assert project.model.elements[20].node_tags() == (
        before[0], before[3], before[2], before[1]
    )
    assert not [
        issue for issue in validate_project(project)
        if issue.category == "Shell orientation"
    ]


def test_shell_axis_viewport_and_reverse_normal_ui_routes_exist():
    axes_source = inspect.getsource(ModelViewport._draw_section_axes)
    assert "shell_x_records" in axes_source
    assert "shell_y_records" in axes_source
    assert "shell_n_records" in axes_source
    assert "display-shell-axis-x" in axes_source
    assert "display-shell-axis-y" in axes_source
    assert "display-shell-axis-normal" in axes_source

    display_source = inspect.getsource(ModelViewport._update_display_option)
    assert "display-shell-axis-normal" in display_source

    reverse_source = inspect.getsource(
        MainWindow._reverse_selected_shell_normals
    )
    assert "reverse_shell_orientation_preserving_pressure" in reverse_source
    assert "pressure_load_tags" in reverse_source

    tree_source = inspect.getsource(MainWindow._show_tree_context_menu)
    viewport_source = inspect.getsource(
        MainWindow._show_viewport_context_menu
    )
    assert "Reverse Shell Normal" in tree_source
    assert "Reverse Shell Normal" in viewport_source


def test_shell_mesh_reuses_existing_shared_edge_nodes():
    model = StructuralModel("adjacent-shell-mesh", ndm=3, ndf=6)
    coordinates = {
        1: (0.0, 0.0, 0.0),
        2: (1.0, 0.0, 0.0),
        3: (1.0, 1.0, 0.0),
        4: (0.0, 1.0, 0.0),
        5: (2.0, 0.0, 0.0),
        6: (2.0, 1.0, 0.0),
    }
    for tag, xyz in coordinates.items():
        model.add_node(tag, *xyz)
    project = ProjectDatabase(name="adjacent-shell-mesh", model=model)
    project.add_section(_shell_section())

    left = build_shell_mesh(
        project,
        ShellMeshSpec(
            corner_nodes=(1, 2, 3, 4),
            divisions_u=1,
            divisions_v=2,
            formulation="ASDShellQ4",
            section_tag=7,
        ),
    )
    shared_midpoint = left.grid[1][-1]

    right = build_shell_mesh(
        project,
        ShellMeshSpec(
            corner_nodes=(2, 5, 6, 3),
            divisions_u=1,
            divisions_v=2,
            formulation="ASDShellQ4",
            section_tag=7,
        ),
    )

    assert right.grid[1][0] == shared_midpoint
    assert shared_midpoint in right.reused_node_tags
    assert project.model.nodes[shared_midpoint].xyz == pytest.approx(
        (1.0, 0.5, 0.0)
    )


def test_shell_mesh_can_disable_existing_node_reuse():
    model = StructuralModel("no-reuse-shell-mesh", ndm=3, ndf=6)
    coordinates = {
        1: (0.0, 0.0, 0.0),
        2: (1.0, 0.0, 0.0),
        3: (1.0, 1.0, 0.0),
        4: (0.0, 1.0, 0.0),
        5: (2.0, 0.0, 0.0),
        6: (2.0, 1.0, 0.0),
    }
    for tag, xyz in coordinates.items():
        model.add_node(tag, *xyz)
    project = ProjectDatabase(name="no-reuse-shell-mesh", model=model)
    project.add_section(_shell_section())

    left = build_shell_mesh(
        project,
        ShellMeshSpec(
            corner_nodes=(1, 2, 3, 4),
            divisions_u=1,
            divisions_v=2,
            formulation="ASDShellQ4",
            section_tag=7,
        ),
    )
    shared_midpoint = left.grid[1][-1]

    right = build_shell_mesh(
        project,
        ShellMeshSpec(
            corner_nodes=(2, 5, 6, 3),
            divisions_u=1,
            divisions_v=2,
            formulation="ASDShellQ4",
            section_tag=7,
            reuse_existing_nodes=False,
        ),
    )

    assert right.grid[1][0] != shared_midpoint
    assert right.reused_node_tags == []
    assert (
        project.model.nodes[right.grid[1][0]].xyz
        == pytest.approx(project.model.nodes[shared_midpoint].xyz)
    )


def test_shell_mesh_target_size_resolves_actual_divisions():
    model = StructuralModel("target-size-shell", ndm=3, ndf=6)
    model.add_node(1, 0.0, 0.0, 0.0)
    model.add_node(2, 4.0, 0.0, 0.0)
    model.add_node(3, 4.0, 2.0, 0.0)
    model.add_node(4, 0.0, 2.0, 0.0)
    project = ProjectDatabase(name="target-size-shell", model=model)
    project.add_section(_shell_section())

    result = build_shell_mesh(
        project,
        ShellMeshSpec(
            corner_nodes=(1, 2, 3, 4),
            target_size=1.1,
            formulation="ASDShellQ4",
            section_tag=7,
        ),
    )

    assert result.divisions_u == 4
    assert result.divisions_v == 2
    assert len(result.element_tags) == 8


def test_shell_mesh_target_size_respects_division_limit():
    model = StructuralModel("tiny-target-shell", ndm=3, ndf=6)
    model.add_node(1, 0.0, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0, 0.0)
    model.add_node(3, 1.0, 1.0, 0.0)
    model.add_node(4, 0.0, 1.0, 0.0)
    project = ProjectDatabase(name="tiny-target-shell", model=model)
    project.add_section(_shell_section())

    with pytest.raises(ValueError, match=r"limited to 500"):
        build_shell_mesh(
            project,
            ShellMeshSpec(
                corner_nodes=(1, 2, 3, 4),
                target_size=0.001,
                formulation="ASDShellQ4",
                section_tag=7,
            ),
        )


def test_model_check_warns_on_coincident_shell_node_tags():
    model = StructuralModel("coincident-shell-nodes", ndm=3, ndf=6)
    coordinates = {
        1: (0.0, 0.0, 0.0),
        2: (1.0, 0.0, 0.0),
        3: (1.0, 1.0, 0.0),
        4: (0.0, 1.0, 0.0),
        5: (1.0, 0.0, 0.0),
        6: (2.0, 0.0, 0.0),
        7: (2.0, 1.0, 0.0),
        8: (1.0, 1.0, 0.0),
    }
    for tag, xyz in coordinates.items():
        model.add_node(tag, *xyz)
    model.add_element(
        10, 1, 2,
        element_type="ASDShellQ4",
        section_tag=7,
        group="shell",
        k=3,
        l=4,
    )
    model.add_element(
        20, 5, 6,
        element_type="ASDShellQ4",
        section_tag=7,
        group="shell",
        k=7,
        l=8,
    )
    project = ProjectDatabase(name="coincident-shell-nodes", model=model)
    project.add_section(_shell_section())

    issues = validate_project(project)
    connectivity = [
        issue for issue in issues
        if issue.category == "Shell connectivity"
    ]

    assert any("nodes 2 and 5" in issue.message for issue in connectivity)
    assert any("nodes 3 and 8" in issue.message for issue in connectivity)


def test_shell_mesh_dialog_exposes_sizing_and_reuse_controls():
    init_source = inspect.getsource(ShellMeshDialog.__init__)
    info_source = inspect.getsource(ShellMeshDialog._update_info)
    spec_source = inspect.getsource(ShellMeshDialog.spec)

    assert "By divisions" in init_source
    assert "By target element size" in init_source
    assert "reuse_existing_nodes" in init_source
    assert "resolve_shell_mesh_divisions" in info_source
    assert "target_size" in spec_source
    assert "reuse_existing_nodes" in spec_source


def _adjacent_patch_mesh_project() -> ProjectDatabase:
    model = StructuralModel("adjacent-conformity", ndm=3, ndf=6)
    coordinates = {
        1: (0.0, 0.0, 0.0),
        2: (1.0, 0.0, 0.0),
        3: (1.0, 1.0, 0.0),
        4: (0.0, 1.0, 0.0),
        5: (2.0, 0.0, 0.0),
        6: (2.0, 1.0, 0.0),
    }
    for tag, xyz in coordinates.items():
        model.add_node(tag, *xyz)
    project = ProjectDatabase(name="adjacent-conformity", model=model)
    project.add_section(_shell_section())
    return project


def test_model_check_detects_shell_hanging_node_t_junction():
    project = _adjacent_patch_mesh_project()
    build_shell_mesh(
        project,
        ShellMeshSpec(
            corner_nodes=(1, 2, 3, 4),
            divisions_u=1,
            divisions_v=2,
            formulation="ASDShellQ4",
            section_tag=7,
        ),
    )
    right = build_shell_mesh(
        project,
        ShellMeshSpec(
            corner_nodes=(2, 5, 6, 3),
            divisions_u=1,
            divisions_v=3,
            formulation="ASDShellQ4",
            section_tag=7,
            conform_existing_edges=False,
        ),
    )

    assert right.divisions_v == 3
    conformity = [
        issue for issue in validate_project(project)
        if issue.category == "Shell conformity"
    ]
    assert conformity
    assert any(
        "lies on the interior of edge" in issue.message
        for issue in conformity
    )


def test_shell_mesh_auto_conforms_to_existing_shared_edge_divisions():
    project = _adjacent_patch_mesh_project()
    left = build_shell_mesh(
        project,
        ShellMeshSpec(
            corner_nodes=(1, 2, 3, 4),
            divisions_u=1,
            divisions_v=2,
            formulation="ASDShellQ4",
            section_tag=7,
        ),
    )
    shared_midpoint = left.grid[1][-1]

    right = build_shell_mesh(
        project,
        ShellMeshSpec(
            corner_nodes=(2, 5, 6, 3),
            divisions_u=1,
            divisions_v=3,
            formulation="ASDShellQ4",
            section_tag=7,
        ),
    )

    assert right.divisions_u == 1
    assert right.divisions_v == 2
    assert right.conformed_u is False
    assert right.conformed_v is True
    assert right.grid[1][0] == shared_midpoint
    assert shared_midpoint in right.reused_node_tags
    assert not [
        issue for issue in validate_project(project)
        if issue.category == "Shell conformity"
    ]


def test_shell_mesh_conformity_can_be_disabled_explicitly():
    project = _adjacent_patch_mesh_project()
    build_shell_mesh(
        project,
        ShellMeshSpec(
            corner_nodes=(1, 2, 3, 4),
            divisions_u=1,
            divisions_v=2,
            formulation="ASDShellQ4",
            section_tag=7,
        ),
    )

    result = build_shell_mesh(
        project,
        ShellMeshSpec(
            corner_nodes=(2, 5, 6, 3),
            divisions_u=1,
            divisions_v=3,
            formulation="ASDShellQ4",
            section_tag=7,
            conform_existing_edges=False,
        ),
    )

    assert result.divisions_v == 3
    assert result.conformed_v is False


def test_shell_mesh_dialog_exposes_edge_conformity_controls():
    init_source = inspect.getsource(ShellMeshDialog.__init__)
    sync_source = inspect.getsource(
        ShellMeshDialog._sync_conformity_options
    )
    spec_source = inspect.getsource(ShellMeshDialog.spec)

    assert "Conform divisions to existing shared-edge shell mesh" in init_source
    assert "conform_existing_edges" in init_source
    assert "reuse_existing_nodes.setChecked(True)" in sync_source
    assert "conform_existing_edges.setChecked(False)" in sync_source
    assert "conform_existing_edges=" in spec_source


def test_shell_mesh_creation_status_reports_actual_conformity_and_reuse():
    source = inspect.getsource(MainWindow._create_shell_mesh)

    assert "result.divisions_u" in source
    assert "result.divisions_v" in source
    assert "result.reused_node_tags" in source
    assert "result.conformed_u" in source
    assert "result.conformed_v" in source
    assert "U conformed" in source
    assert "V conformed" in source


def _stitchable_shell_project() -> ProjectDatabase:
    model = StructuralModel("shell-stitch", ndm=3, ndf=6)
    coordinates = {
        1: (0.0, 0.0, 0.0),
        2: (1.0, 0.0, 0.0),
        3: (1.0, 1.0, 0.0),
        4: (0.0, 1.0, 0.0),
        5: (1.0, 0.0, 0.0),
        6: (2.0, 0.0, 0.0),
        7: (2.0, 1.0, 0.0),
        8: (1.0, 1.0, 0.0),
    }
    for tag, xyz in coordinates.items():
        model.add_node(tag, *xyz)
    model.add_element(
        10, 1, 2,
        element_type="ASDShellQ4",
        section_tag=7,
        group="shell",
        k=3,
        l=4,
    )
    model.add_element(
        20, 5, 6,
        element_type="ASDShellQ4",
        section_tag=7,
        group="shell",
        k=7,
        l=8,
    )
    project = ProjectDatabase(name="shell-stitch", model=model)
    project.add_section(_shell_section())
    return project


def test_project_finds_coincident_shell_node_groups():
    project = _stitchable_shell_project()

    groups = project.coincident_shell_node_groups()

    assert groups == [[2, 5], [3, 8]]


def test_project_stitches_coincident_shell_nodes_and_removes_connectivity_warning():
    project = _stitchable_shell_project()

    result = project.stitch_coincident_shell_nodes()

    assert result["merged_nodes"] == [5, 8]
    assert result["kept_nodes"] == [2, 3]
    assert result["remapped_elements"] == [20]
    assert 5 not in project.model.nodes
    assert 8 not in project.model.nodes
    assert project.model.elements[20].node_tags() == (2, 6, 7, 3)
    assert project.coincident_shell_node_groups() == []
    assert not [
        issue for issue in validate_project(project)
        if issue.category == "Shell connectivity"
    ]


def test_shell_stitch_rejects_incompatible_support_state():
    project = _stitchable_shell_project()
    project.model.set_fixity(5, (1, 1, 1, 1, 1, 1))

    with pytest.raises(ValueError, match=r"support/fixity states differ"):
        project.stitch_coincident_shell_nodes()

    assert 5 in project.model.nodes
    assert project.model.elements[20].node_tags() == (5, 6, 7, 8)


def test_shell_stitch_rejects_removed_node_with_node_recorder_reference():
    project = _stitchable_shell_project()
    project.recorders[1] = RecorderData(
        tag=1,
        name="Seam node",
        recorder_type="Node",
        target_tags=[5],
        response="disp",
        dofs=[1],
    )

    with pytest.raises(ValueError, match=r"node recorder"):
        project.stitch_coincident_shell_nodes()

    assert 5 in project.model.nodes
    assert project.model.elements[20].node_tags() == (5, 6, 7, 8)


def test_shell_stitch_ui_and_model_check_repair_route_are_exposed():
    method_source = inspect.getsource(
        MainWindow._stitch_coincident_shell_nodes
    )
    tree_source = inspect.getsource(MainWindow._show_tree_context_menu)
    viewport_source = inspect.getsource(
        MainWindow._show_viewport_context_menu
    )
    from openseespy_studio import validation as validation_module
    validation_source = inspect.getsource(
        validation_module._element_geometry_checks
    )

    assert "coincident_shell_node_groups" in method_source
    assert "stitch_coincident_shell_nodes" in method_source
    assert "Stitch Coincident Shell Nodes" in tree_source
    assert "Stitch Coincident Shell Nodes" in viewport_source
    assert "Stitch Coincident" in validation_source


def test_shell_surface_geometry_uses_ordered_newell_normal_on_warped_quad():
    model = StructuralModel("warped-pressure-normal", ndm=3, ndf=6)
    model.add_node(1, 0.0, 0.0, 0.0)
    model.add_node(2, 2.0, 0.0, 0.0)
    model.add_node(3, 2.0, 2.0, 1.0)
    model.add_node(4, 0.0, 2.0, 0.0)
    model.add_element(
        10, 1, 2,
        element_type="ASDShellQ4",
        section_tag=7,
        group="shell",
        k=3,
        l=4,
    )
    element = model.elements[10]

    center, normal, area = shell_surface_geometry(model, element)

    assert center == pytest.approx((1.0, 1.0, 0.25))
    assert sum(value * value for value in normal) == pytest.approx(1.0)
    assert normal[2] > 0.0
    assert area > 4.0

    model.reverse_shell_orientation([10])
    reversed_center, reversed_normal, reversed_area = shell_surface_geometry(
        model,
        model.elements[10],
    )
    assert reversed_center == pytest.approx(center)
    assert reversed_area == pytest.approx(area)
    assert reversed_normal == pytest.approx(
        tuple(-value for value in normal)
    )


def test_reverse_shell_normal_preserves_global_surface_pressure_vector():
    project = _shell_pressure_project(-1250.0)
    element = project.model.elements[10]
    _center, normal_before, _area = shell_surface_geometry(
        project.model,
        element,
    )
    pressure_before = project.element_loads[1].pressure
    vector_before = tuple(
        pressure_before * value for value in normal_before
    )

    result = project.reverse_shell_orientation_preserving_pressure([10])

    element_after = project.model.elements[10]
    _center, normal_after, _area = shell_surface_geometry(
        project.model,
        element_after,
    )
    pressure_after = project.element_loads[1].pressure
    vector_after = tuple(
        pressure_after * value for value in normal_after
    )

    assert result["element_tags"] == [10]
    assert result["pressure_load_tags"] == [1]
    assert element_after.node_tags() == (1, 4, 3, 2)
    assert pressure_after == pytest.approx(1250.0)
    assert normal_after == pytest.approx(
        tuple(-value for value in normal_before)
    )
    assert vector_after == pytest.approx(vector_before)


def test_reverse_shell_normal_without_pressure_needs_no_pressure_adjustment():
    project = ProjectDatabase(
        name="shell-reverse-no-pressure",
        model=_shell_model(),
    )
    project.add_section(_shell_section())

    result = project.reverse_shell_orientation_preserving_pressure([10])

    assert result["element_tags"] == [10]
    assert result["pressure_load_tags"] == []
    assert project.model.elements[10].node_tags() == (1, 4, 3, 2)


def test_shell_pressure_viewport_and_properties_use_shared_surface_geometry():
    viewport_source = inspect.getsource(ModelViewport._draw_element_loads)
    property_source = inspect.getsource(
        MainWindow._show_element_load_properties
    )

    assert "shell_surface_geometry" in viewport_source
    assert "shell_surface_geometry" in property_source
    assert "Shell normal XYZ" in property_source
    assert "Global pressure vector" in property_source


def test_reverse_shell_normal_ui_preserves_pressure_and_reports_adjustment():
    source = inspect.getsource(MainWindow._reverse_selected_shell_normals)

    assert "reverse_shell_orientation_preserving_pressure" in source
    assert 'result["pressure_load_tags"]' in source
    assert "preserved" in source
    assert "surface pressure load(s)" in source
