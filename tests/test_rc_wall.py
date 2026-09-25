from __future__ import annotations

import inspect
import math
import os
import pytest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog, QWizard

from openseespy_studio.generator import build_mefi_crack_specs, to_openseespy
from openseespy_studio.project import AnalysisSettingsData, ProjectDatabase
from openseespy_studio.rc_wall import RCWallSpec, build_rc_wall
import openseespy_studio.ui.main_window as main_window_module
from openseespy_studio.ui import viewport as viewport_module
from openseespy_studio.ui.main_window import MainWindow
from openseespy_studio.ui.rc_wall_wizard import RCWallWizard
from openseespy_studio.ui.rclms_section_dialog import RCLMSSectionDialog
from openseespy_studio.validation import validate_project


_APP = QApplication.instance() or QApplication([])


def _benchmark_project() -> tuple[ProjectDatabase, object]:
    project = ProjectDatabase()
    project.units = {
        "length": "mm",
        "force": "N",
        "time": "s",
    }
    spec = RCWallSpec(
        width=1220.0,
        height=2209.8,
        thickness=152.4,
        boundary_width=228.6,
        vertical_elements=7,
        macro_fibers=8,
        boundary_unconfined_thickness=50.8,
        boundary_confined_thickness=101.6,
    )
    return project, build_rc_wall(project, spec)


def test_rc_wall_builder_matches_rw_wall_only_topology():
    project, result = _benchmark_project()

    assert (project.model.ndm, project.model.ndf) == (2, 3)
    assert len(result.node_tags) == 16
    assert len(result.element_tags) == 7
    assert len(result.material_tags) == 5
    assert len(result.nd_material_tags) == 4
    assert len(result.section_tags) == 2

    first = project.model.elements[result.element_tags[0]]
    assert first.element_type == "MEFI"
    assert first.node_tags() == (1, 2, 4, 3)
    assert len(first.mefi_widths) == 8
    assert math.isclose(sum(first.mefi_widths), 1220.0)
    assert math.isclose(first.mefi_widths[0], 228.6)
    assert math.isclose(first.mefi_widths[-1], 228.6)
    for width in first.mefi_widths[1:-1]:
        assert math.isclose(width, 127.13333333333334)

    assert first.mefi_section_tags == (
        result.boundary_section_tag,
        result.web_section_tag,
        result.web_section_tag,
        result.web_section_tag,
        result.web_section_tag,
        result.web_section_tag,
        result.web_section_tag,
        result.boundary_section_tag,
    )
    assert project.model.nodes[1].fixity == (1, 1, 1)
    assert project.model.nodes[2].fixity == (1, 1, 1)


def test_rc_wall_builder_creates_named_analysis_selections():
    project, result = _benchmark_project()

    assert result.selection_set_names == (
        "RC Wall · Base",
        "RC Wall · Top",
        "RC Wall · MEFI",
    )
    base = project.selection_sets[result.selection_set_names[0]]
    top = project.selection_sets[result.selection_set_names[1]]
    wall = project.selection_sets[result.selection_set_names[2]]

    assert base.node_tags == {1, 2}
    assert top.node_tags == {15, 16}
    assert wall.element_tags == set(result.element_tags)


def test_rc_wall_append_mode_respects_origin_and_preserves_model():
    project = ProjectDatabase()
    project.model.ndm = 2
    project.model.ndf = 3
    project.model.add_node(1, -5.0, -5.0, 0.0)

    spec = RCWallSpec(
        width=1.2,
        height=2.4,
        thickness=0.2,
        boundary_width=0.2,
        origin_x=3.0,
        origin_y=4.0,
        vertical_elements=2,
        macro_fibers=4,
        boundary_unconfined_thickness=0.05,
        boundary_confined_thickness=0.15,
        replace_geometry=False,
        name="Appended Wall",
    )
    result = build_rc_wall(project, spec)

    assert 1 in project.model.nodes
    assert project.model.nodes[1].xyz == (-5.0, -5.0, 0.0)
    first_left = project.model.nodes[result.node_tags[0]]
    first_right = project.model.nodes[result.node_tags[1]]
    top_left = project.model.nodes[result.node_tags[-2]]
    assert first_left.xyz == (3.0, 4.0, 0.0)
    assert first_right.xyz == (4.2, 4.0, 0.0)
    assert top_left.xyz == (3.0, 6.4, 0.0)
    assert "Appended Wall · Top" in project.selection_sets


def test_rc_wall_append_mode_rejects_coordinate_overlap():
    project = ProjectDatabase()
    project.model.ndm = 2
    project.model.ndf = 3
    project.model.add_node(1, 0.0, 0.0, 0.0)
    before = project.to_dict()

    spec = RCWallSpec(
        width=1.2,
        height=2.4,
        thickness=0.2,
        boundary_width=0.2,
        vertical_elements=2,
        macro_fibers=4,
        boundary_unconfined_thickness=0.05,
        boundary_confined_thickness=0.15,
        replace_geometry=False,
    )

    try:
        build_rc_wall(project, spec)
    except ValueError as exc:
        assert "overlaps an existing model node" in str(exc)
    else:
        raise AssertionError(
            "Append mode should reject coincident wall/model nodes."
        )

    assert project.to_dict() == before


def test_rc_wall_rejects_invalid_material_input_before_mutation():
    project = ProjectDatabase()
    before = project.to_dict()
    spec = RCWallSpec(
        steel_E=0.0,
    )

    try:
        build_rc_wall(project, spec)
    except ValueError as exc:
        assert "steel_E" in str(exc)
    else:
        raise AssertionError("Non-positive steel modulus should be rejected.")

    assert project.to_dict() == before


def test_rc_wall_hybrid_boundary_rebar_deducts_smeared_ratio():
    project = ProjectDatabase()
    project.units = {
        "length": "mm",
        "force": "N",
        "time": "s",
    }
    spec = RCWallSpec(
        width=1220.0,
        height=2209.8,
        thickness=152.4,
        boundary_width=228.6,
        vertical_elements=7,
        macro_fibers=8,
        boundary_unconfined_thickness=50.8,
        boundary_confined_thickness=101.6,
        reinforcement_mode="hybrid",
        boundary_bar_count=4,
        boundary_bar_diameter=16.0,
        boundary_cover=30.0,
        boundary_layer_mode="front_back",
        boundary_truss_type="corotTruss",
    )

    result = build_rc_wall(project, spec)

    bar_area = math.pi * 16.0 ** 2 / 4.0
    discrete_area = 4.0 * bar_area
    discrete_ratio = discrete_area / (228.6 * 152.4)
    expected_remaining = 0.0323 - discrete_ratio

    # Four physical bars per boundary × two boundaries × seven MEFI rows.
    assert len(result.reinforcement_element_tags) == 56
    assert result.web_horizontal_element_tags == []
    assert result.boundary_bar_area == pytest.approx(bar_area)
    assert result.boundary_bar_spacing == pytest.approx(152.6)
    assert result.boundary_discrete_rho_y == pytest.approx(discrete_ratio)
    assert result.boundary_smeared_rho_y == pytest.approx(
        expected_remaining
    )
    assert result.reinforcement_selection_name in project.selection_sets

    boundary_steel = project.nd_materials[result.nd_material_tags[3]]
    assert boundary_steel.parameters["ratio2"] == pytest.approx(
        expected_remaining
    )

    boundary_material_tag = result.material_tags[2]
    left_tags = result.reinforcement_element_tags[:28]
    right_tags = result.reinforcement_element_tags[28:]
    assert len(left_tags) == len(right_tags) == 28
    for tag in result.reinforcement_element_tags:
        element = project.model.elements[tag]
        assert element.element_type == "corotTruss"
        assert element.group.startswith("rc-wall-rebar-")
        assert element.truss_area == pytest.approx(bar_area)
        assert element.truss_material_tag == boundary_material_tag

    left_groups = {
        project.model.elements[tag].group
        for tag in left_tags
    }
    right_groups = {
        project.model.elements[tag].group
        for tag in right_tags
    }
    assert left_groups == {
        "rc-wall-rebar-left-front-b01of02",
        "rc-wall-rebar-left-front-b02of02",
        "rc-wall-rebar-left-back-b01of02",
        "rc-wall-rebar-left-back-b02of02",
    }
    assert right_groups == {
        "rc-wall-rebar-right-front-b01of02",
        "rc-wall-rebar-right-front-b02of02",
        "rc-wall-rebar-right-back-b01of02",
        "rc-wall-rebar-right-back-b02of02",
    }

    first_left = project.model.elements[left_tags[0]]
    first_right = project.model.elements[right_tags[0]]
    assert first_left.node_tags() == (1, 3)
    assert first_right.node_tags() == (2, 4)


def test_rc_wall_hybrid_rejects_discrete_steel_above_total_ratio():
    project = ProjectDatabase()
    before = project.to_dict()
    spec = RCWallSpec(
        reinforcement_mode="hybrid",
        boundary_bar_count=20,
        boundary_bar_diameter=0.025,
    )

    with pytest.raises(
        ValueError,
        match=r"exceeds the specified boundary rho-y",
    ):
        build_rc_wall(project, spec)

    assert project.to_dict() == before


def test_rc_wall_hybrid_mesh_aligned_horizontal_bars_reduce_rho_x():
    project = ProjectDatabase()
    project.units = {
        "length": "mm",
        "force": "N",
        "time": "s",
    }
    spec = RCWallSpec(
        width=1220.0,
        height=2209.8,
        thickness=152.4,
        boundary_width=228.6,
        vertical_elements=7,
        macro_fibers=8,
        boundary_unconfined_thickness=50.8,
        boundary_confined_thickness=101.6,
        reinforcement_mode="hybrid",
        boundary_bar_count=4,
        boundary_bar_diameter=16.0,
        boundary_cover=30.0,
        web_horizontal_mode="mesh_aligned",
        web_horizontal_bar_diameter=8.0,
        web_horizontal_layer_mode="front_back",
    )

    result = build_rc_wall(project, spec)

    horizontal_area = math.pi * 8.0 ** 2 / 4.0
    expected_rho = (
        6 * 2 * horizontal_area / (2209.8 * 152.4)
    )
    assert len(result.web_horizontal_element_tags) == 12
    assert len(result.reinforcement_element_tags) == 68
    assert result.web_horizontal_discrete_rho_x == pytest.approx(
        expected_rho
    )
    assert result.web_smeared_rho_x == pytest.approx(
        0.0027 - expected_rho
    )
    assert result.boundary_smeared_rho_x == pytest.approx(
        0.0082 - expected_rho
    )

    web_steel = project.nd_materials[result.nd_material_tags[2]]
    boundary_steel = project.nd_materials[result.nd_material_tags[3]]
    assert web_steel.parameters["ratio1"] == pytest.approx(
        0.0027 - expected_rho
    )
    assert boundary_steel.parameters["ratio1"] == pytest.approx(
        0.0082 - expected_rho
    )
    for tag in result.web_horizontal_element_tags:
        element = project.model.elements[tag]
        assert element.group.startswith(
            "rc-wall-rebar-web-horizontal-"
        )
        assert element.truss_area == pytest.approx(horizontal_area)
        assert element.truss_material_tag == result.material_tags[0]


def test_rc_wall_hybrid_export_contains_corot_truss():
    project = ProjectDatabase()
    spec = RCWallSpec(
        reinforcement_mode="hybrid",
        boundary_bar_count=4,
        boundary_bar_diameter=0.016,
    )
    result = build_rc_wall(project, spec)

    script = to_openseespy(
        project.model,
        materials=project.materials,
        sections=project.sections,
        transformations=project.transformations,
        constraints=project.constraints,
        connections=project.connections,
        units=project.units,
        nd_materials=project.nd_materials,
    )

    first = result.reinforcement_element_tags[0]
    element = project.model.elements[first]
    assert (
        f"ops.element('corotTruss', {first}, {element.i}, {element.j}, "
        in script
    )


def test_rc_wall_builder_creates_expected_material_chain():
    project, result = _benchmark_project()

    material_types = [
        project.materials[tag].material_type
        for tag in result.material_tags
    ]
    assert material_types == [
        "Steel02",
        "Steel02",
        "Steel02",
        "Concrete02",
        "Concrete02",
    ]

    nd_types = [
        project.nd_materials[tag].material_type
        for tag in result.nd_material_tags
    ]
    assert nd_types == [
        "OrthotropicRAConcrete",
        "OrthotropicRAConcrete",
        "SmearedSteelDoubleLayer",
        "SmearedSteelDoubleLayer",
    ]

    web = project.sections[result.web_section_tag]
    boundary = project.sections[result.boundary_section_tag]
    assert web.section_type == "RCLMS"
    assert boundary.section_type == "RCLMS"
    assert len(web.shell_layers) == 1
    assert len(boundary.shell_layers) == 2
    assert math.isclose(web.shell_total_thickness(), 152.4)
    assert math.isclose(boundary.shell_total_thickness(), 152.4)


def test_rc_wall_export_contains_native_opensees_workflow():
    project, result = _benchmark_project()

    script = to_openseespy(
        project.model,
        materials=project.materials,
        sections=project.sections,
        transformations=project.transformations,
        constraints=project.constraints,
        connections=project.connections,
        units=project.units,
        nd_materials=project.nd_materials,
    )

    assert (
        "ops.nDMaterial('SmearedSteelDoubleLayer', "
        in script
    )
    assert (
        f"ops.section('RCLMS', {result.web_section_tag}, 1, 1"
        in script
    )
    assert (
        f"ops.section('RCLMS', {result.boundary_section_tag}, 1, 2"
        in script
    )

    first = result.element_tags[0]
    assert (
        f"ops.element('MEFI', {first}, 1, 2, 4, 3, 8, "
        in script
    )
    assert "'-width', 228.6, 127.133" in script
    assert (
        f"'-sec', {result.boundary_section_tag}, "
        f"{result.web_section_tag}"
        in script
    )



def test_rc_wall_builds_mefi_crack_specs_from_material_ecr():
    project, result = _benchmark_project()

    specs = build_mefi_crack_specs(
        project.model,
        sections=project.sections,
        nd_materials=project.nd_materials,
    )

    assert set(specs) == set(result.element_tags)
    first = specs[result.element_tags[0]]
    assert first["source"] == "MEFI RCPanel panel_strain"
    assert len(first["panels"]) == 8
    assert [panel["panel"] for panel in first["panels"]] == list(range(1, 9))
    assert math.isclose(
        sum(float(panel["width"]) for panel in first["panels"]),
        1220.0,
    )
    assert all(
        math.isclose(float(panel["cracking_strain"]), 8.0e-5)
        for panel in first["panels"]
    )


def test_rc_wall_analysis_script_captures_mefi_panel_strain_history():
    project, result = _benchmark_project()
    analysis = AnalysisSettingsData(
        1,
        "RC Wall Static",
        analysis_type="Static",
        steps=1,
        integrator="LoadControl",
        load_increment=1.0,
    )

    script = to_openseespy(
        project.model,
        materials=project.materials,
        sections=project.sections,
        transformations=project.transformations,
        constraints=project.constraints,
        connections=project.connections,
        units=project.units,
        nd_materials=project.nd_materials,
        analyses={1: analysis},
        active_analysis_tag=1,
    )

    assert "_studio_mefi_crack_specs" in script
    assert "'mefi_crack_specs':" in script
    assert "'mefi_panel_strains':" in script
    assert "'RCPanel'" in script
    assert "'panel_strain'" in script
    assert str(result.element_tags[0]) in script



def test_rc_wall_passes_core_model_validation():
    project, _result = _benchmark_project()

    errors = [
        issue
        for issue in validate_project(project)
        if issue.severity == "ERROR"
    ]
    assert errors == []


def test_rc_wall_project_roundtrip_preserves_mefi_arrays():
    project, result = _benchmark_project()
    restored = ProjectDatabase.from_dict(project.to_dict())

    first = result.element_tags[0]
    assert restored.model.elements[first].mefi_widths == (
        project.model.elements[first].mefi_widths
    )
    assert restored.model.elements[first].mefi_section_tags == (
        project.model.elements[first].mefi_section_tags
    )
    assert restored.sections[result.web_section_tag].section_type == "RCLMS"


def test_rc_wall_rejects_invalid_boundary_geometry():
    project = ProjectDatabase()
    spec = RCWallSpec(
        width=1.0,
        boundary_width=0.5,
    )

    try:
        build_rc_wall(project, spec)
    except ValueError as exc:
        assert "Boundary width" in str(exc)
    else:
        raise AssertionError("Oversized boundary zones should be rejected.")


def test_rclms_section_from_wizard_is_editable():
    project, result = _benchmark_project()
    section = project.sections[result.boundary_section_tag]

    dialog = RCLMSSectionDialog(
        section=section,
        nd_materials=project.nd_materials,
        units=project.units,
    )
    try:
        assert dialog.steel.currentData() == section.nd_material_tag
        assert dialog.table.rowCount() == 2
        updated = dialog.section_data()
        assert updated.section_type == "RCLMS"
        assert updated.nd_material_tag == section.nd_material_tag
        assert [
            layer.material_tag for layer in updated.shell_layers
        ] == [
            layer.material_tag for layer in section.shell_layers
        ]
        assert math.isclose(
            updated.shell_total_thickness(),
            152.4,
        )
    finally:
        dialog.close()
        dialog.deleteLater()
        _APP.processEvents()


def test_rc_wall_finish_reveals_generated_mefi_model():
    source = inspect.getsource(MainWindow._show_rc_wall_wizard)

    assert 'self.viewport.set_display_domain("fe")' in source
    assert "self._reset_sketch_plane_context()" in source
    assert "elements=set(result.element_tags)" in source
    assert 'self.viewport.set_view("xy", render=False)' in source
    assert "self.viewport.fit_view()" in source
    assert "expected_node_count" in source
    assert "expected_element_count" in source
    assert "missing_nodes" in source
    assert "missing_elements" in source
    assert "wrong_elements" in source
    assert "self._refresh_tree()" in source
    assert "self.viewport._visible_element_tags()" in source
    assert "self.viewport.show_all()" in source
    assert '"RC Wall Created · Viewport Error"' in source
    assert "The wall remains available under FE Model > Elements." in source


def test_rc_wall_wizard_custom_mode_and_origin_roundtrip():
    project = ProjectDatabase()
    project.model.ndm = 2
    project.model.ndf = 3
    dialog = RCWallWizard(project)
    try:
        assert dialog.preset.currentData() == "rw-a20"
        dialog.width.setValue(dialog.width.value() * 1.1)
        _APP.processEvents()
        assert dialog.preset.currentData() == "custom"

        dialog.wall_name.setText("Wall B")
        dialog.replace_geometry.setChecked(False)
        dialog.origin_x.setValue(3.5)
        dialog.origin_y.setValue(-1.25)
        _APP.processEvents()

        spec = dialog.data()
        assert spec.name == "Wall B"
        assert not spec.replace_geometry
        assert math.isclose(spec.origin_x, 3.5)
        assert math.isclose(spec.origin_y, -1.25)
        assert "Append to current 2D model" in dialog.review.text()
        assert "Named selections" in dialog.review.text()
    finally:
        dialog.close()
        dialog.deleteLater()
        _APP.processEvents()


def test_rc_wall_gui_exposes_reinforcement_tree_and_display_controls():
    tree_source = inspect.getsource(MainWindow._refresh_tree)
    selection_source = inspect.getsource(MainWindow._tree_selection_changed)
    root_source = inspect.getsource(MainWindow._show_tree_root_properties)
    group_source = inspect.getsource(
        MainWindow._show_reinforcement_group_properties
    )
    viewport_source = inspect.getsource(
        viewport_module.ModelViewport._combined_element_meshes
    )
    display_source = inspect.getsource(
        viewport_module.ModelViewport._show_display_options_menu
    )

    assert '"reinforcement_root"' in tree_source
    assert '"reinforcement_group"' in tree_source
    assert "Boundary Bars · Left · Front" in tree_source
    assert "Boundary Bars · Right · Back" in tree_source
    assert "Web Bars · Horizontal" in tree_source
    assert "rc-wall-rebar" in selection_source
    assert "Discrete Reinforcement" in root_source
    assert "Perfect Bond" in group_source
    assert '"reinforcement"' in viewport_source
    assert "_batched_reinforcement_mesh" in viewport_source
    assert "Discrete reinforcement" in display_source


def test_rc_wall_wizard_hybrid_mode_roundtrip():
    project = ProjectDatabase()
    project.units = {
        "length": "mm",
        "force": "N",
        "time": "s",
    }
    dialog = RCWallWizard(project)
    try:
        hybrid_index = dialog.reinforcement_mode.findData("hybrid")
        dialog.reinforcement_mode.setCurrentIndex(hybrid_index)
        dialog.boundary_bar_count.setValue(4)
        dialog.boundary_bar_diameter.setValue(16.0)
        dialog.boundary_cover.setValue(30.0)
        horizontal_index = dialog.web_horizontal_mode.findData(
            "mesh_aligned"
        )
        dialog.web_horizontal_mode.setCurrentIndex(horizontal_index)
        dialog.web_horizontal_bar_diameter.setValue(8.0)
        _APP.processEvents()

        spec = dialog.data()
        assert spec.reinforcement_mode == "hybrid"
        assert spec.boundary_bar_count == 4
        assert math.isclose(spec.boundary_bar_diameter, 16.0)
        assert spec.boundary_truss_type == "corotTruss"
        assert spec.boundary_layer_mode == "front_back"
        assert math.isclose(spec.boundary_cover, 30.0)
        assert spec.web_horizontal_mode == "mesh_aligned"
        assert math.isclose(spec.web_horizontal_bar_diameter, 8.0)
        assert dialog.boundary_bar_count.isEnabled()
        assert dialog.preview.reinforcement_mode == "hybrid"
        assert dialog.preview.boundary_bars == 4
        assert "As,total" in dialog.reinforcement_info.text()
        assert "center spacing" in dialog.reinforcement_info.text()
        assert "ρy,discrete" in dialog.reinforcement_info.text()
        assert "Horizontal discrete" in dialog.reinforcement_info.text()
        assert "ρy discrete" in dialog.review.text()
        assert "smeared remaining" in dialog.review.text()
        assert dialog.final_preview.reinforcement_mode == "hybrid"
        assert dialog.final_preview.boundary_bars == 4
        assert "Nodes: 16" in dialog.preview_object_summary.text()
        assert "MEFI elements: 7" in dialog.preview_object_summary.text()
        assert "Boundary bar elements: 56" in dialog.preview_object_summary.text()
        assert (
            "Horizontal web bar elements: 12"
            in dialog.preview_object_summary.text()
        )
        assert "Total elements: 75" in dialog.preview_object_summary.text()
        assert "Ready to create wall" in dialog.preview_validation_status.text()
    finally:
        dialog.close()
        dialog.deleteLater()
        _APP.processEvents()


def test_rc_wall_wizard_pages_are_vertically_scrollable():
    project = ProjectDatabase()
    dialog = RCWallWizard(project)
    try:
        scrolls = (
            dialog.geometry_scroll,
            dialog.concrete_scroll,
            dialog.reinforcement_scroll,
            dialog.preview_scroll,
        )
        for scroll in scrolls:
            assert scroll.widgetResizable()
            assert (
                scroll.horizontalScrollBarPolicy()
                == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
            )
            assert (
                scroll.verticalScrollBarPolicy()
                == Qt.ScrollBarPolicy.ScrollBarAsNeeded
            )
            assert scroll.widget() is not None

        bar = dialog.reinforcement_scroll.verticalScrollBar()
        bar.setRange(0, 100)
        bar.setValue(10)
        dialog._page_changed(2)
        _APP.processEvents()
        assert bar.value() == 0
    finally:
        dialog.close()
        dialog.deleteLater()
        _APP.processEvents()


def test_rc_wall_final_page_previews_objects_before_accept():
    project = ProjectDatabase()
    project.units = {
        "length": "mm",
        "force": "N",
        "time": "s",
    }
    dialog = RCWallWizard(project)
    try:
        dialog._update_review()
        counts = dialog._preview_object_counts()

        assert counts == {
            "nodes": 16,
            "mefi": 7,
            "boundary_rebar": 0,
            "horizontal_rebar": 0,
            "discrete_rebar": 0,
            "elements": 7,
            "uniaxial_materials": 5,
            "nd_materials": 4,
            "sections": 2,
            "selection_sets": 3,
            "fixed_nodes": 2,
        }
        assert dialog.final_preview.width_value == pytest.approx(1220.0)
        assert dialog.final_preview.height_value == pytest.approx(2209.8)
        assert dialog.final_preview.thickness_value == pytest.approx(152.4)
        assert "W × H × t" in dialog.preview_geometry_summary.text()
        assert "Objects to be created" in dialog.preview_object_summary.text()
        assert "Total elements: 7" in dialog.preview_object_summary.text()
        assert "Materials & Sections" in dialog.preview_material_summary.text()
        assert "Steel02 ×3" in dialog.preview_material_summary.text()
        assert "RCLMS Boundary (2 layers)" in dialog.preview_material_summary.text()
        assert "Selections & Boundary Conditions" in (
            dialog.preview_selection_summary.text()
        )
        assert "Base · Top · MEFI" in dialog.preview_selection_summary.text()
        assert "Legend" in dialog.preview_legend.text()
        assert dialog.final_preview.detailed_annotations
        assert dialog.final_preview.warning_keys == set()
        assert "Ready to create wall" in dialog.preview_validation_status.text()
        assert (
            dialog.button(QWizard.WizardButton.FinishButton).text()
            == "Create Wall"
        )
    finally:
        dialog.close()
        dialog.deleteLater()
        _APP.processEvents()


def test_rc_wall_final_preview_marks_boundary_error_and_locks_create():
    project = ProjectDatabase()
    project.units = {
        "length": "mm",
        "force": "N",
        "time": "s",
    }
    dialog = RCWallWizard(project)
    try:
        hybrid_index = dialog.reinforcement_mode.findData("hybrid")
        dialog.reinforcement_mode.setCurrentIndex(hybrid_index)
        dialog.boundary_bar_count.setValue(5)
        dialog.boundary_bar_diameter.setValue(16.0)
        dialog.boundary_cover.setValue(120.0)
        dialog._update_review()
        _APP.processEvents()

        assert "boundary" in dialog.final_preview.warning_keys
        assert "needs attention" in dialog.preview_validation_status.text()
        assert "Boundary / reinforcement" in (
            dialog.preview_validation_status.text()
        )
        finish = dialog.button(QWizard.WizardButton.FinishButton)
        assert finish is not None
        assert not finish.isEnabled()

        dialog.boundary_bar_count.setValue(4)
        dialog.boundary_cover.setValue(30.0)
        dialog._update_review()
        _APP.processEvents()

        assert dialog.final_preview.warning_keys == set()
        assert finish.isEnabled()
        assert "Ready to create wall" in dialog.preview_validation_status.text()
    finally:
        dialog.close()
        dialog.deleteLater()
        _APP.processEvents()


def test_rc_wall_final_preview_reports_materials_and_hybrid_formulation():
    project = ProjectDatabase()
    project.units = {
        "length": "mm",
        "force": "N",
        "time": "s",
    }
    dialog = RCWallWizard(project)
    try:
        hybrid_index = dialog.reinforcement_mode.findData("hybrid")
        dialog.reinforcement_mode.setCurrentIndex(hybrid_index)
        dialog._update_review()

        material_text = dialog.preview_material_summary.text()
        assert "OrthotropicRAConcrete ×2" in material_text
        assert "SmearedSteelDoubleLayer ×2" in material_text
        assert "CorotTruss" in material_text
        assert "Reinforcement" in dialog.preview_selection_summary.text()
    finally:
        dialog.close()
        dialog.deleteLater()
        _APP.processEvents()


def test_rc_wall_wizard_converts_benchmark_geometry_to_project_units():
    project = ProjectDatabase()
    project.units = {
        "length": "m",
        "force": "kN",
        "time": "s",
    }
    dialog = RCWallWizard(project)
    try:
        spec = dialog.data()
        assert math.isclose(spec.width, 1.220)
        assert math.isclose(spec.height, 2.2098)
        assert math.isclose(spec.thickness, 0.1524)
        assert math.isclose(spec.boundary_width, 0.2286)
        assert spec.vertical_elements == 7
        assert spec.macro_fibers == 8
        assert math.isclose(spec.rho_x_web, 0.0027)
        assert math.isclose(spec.rho_y_boundary, 0.0323)
        assert dialog.vertical_elements.value() == 7
        assert "Vertical MEFI elements: 7" in dialog.review.text()
    finally:
        dialog.close()
        dialog.deleteLater()
        _APP.processEvents()


def test_rc_wall_action_callback_accepts_qaction_checked_argument():
    signature = inspect.signature(MainWindow._show_rc_wall_wizard)
    parameters = list(signature.parameters.values())

    assert [parameter.name for parameter in parameters[:2]] == [
        "self",
        "checked",
    ]
    assert parameters[1].default is False


def test_rc_wall_wizard_finish_accepts_benchmark_preset():
    wizard = RCWallWizard(ProjectDatabase())
    try:
        wizard.show()
        _APP.processEvents()

        while wizard.currentId() < 3:
            previous = wizard.currentId()
            wizard.next()
            _APP.processEvents()
            assert wizard.currentId() == previous + 1

        finish = wizard.button(QWizard.WizardButton.FinishButton)
        assert finish is not None
        assert finish.isEnabled()

        finish.click()
        _APP.processEvents()

        assert wizard.result() == QDialog.DialogCode.Accepted
    finally:
        wizard.close()
        wizard.deleteLater()
        _APP.processEvents()


def test_rc_wall_replace_validation_ignores_preexisting_error_keys():
    source = inspect.getsource(MainWindow._show_rc_wall_wizard)

    generated_block = source.split(
        "generated_errors = [", 1
    )[1].split(
        "if generated_errors:", 1
    )[0]
    assert "existing_error_keys" in generated_block
    assert "not in existing_error_keys" in generated_block
    assert "spec.replace_geometry\n                        or" not in generated_block


def test_rc_wall_mainwindow_handler_builds_live_project(monkeypatch):
    project = ProjectDatabase()

    class _FakeWizard:
        def __init__(self, _project, parent=None):
            assert _project is project

        def exec(self):
            return int(QDialog.DialogCode.Accepted)

        def data(self):
            return RCWallSpec()

    class _FakeViewport:
        def __init__(self):
            self.domain = None
            self.view = None
            self.plotter = SimpleNamespace(render=lambda: None)

        def set_display_domain(self, domain):
            self.domain = domain

        def set_view(self, view, render=True):
            self.view = view

        def fit_view(self):
            return None

        def _visible_element_tags(self):
            return set(project.model.elements)

        def show_all(self):
            return None

    selected = {}
    selection = SimpleNamespace(
        clear=lambda: selected.clear(),
        set_selection=lambda **kwargs: selected.update(kwargs),
    )
    viewport = _FakeViewport()

    holder = SimpleNamespace(
        project=project,
        model=project.model,
        selection=selection,
        viewport=viewport,
        _reset_runtime_results=lambda: None,
        _reset_sketch_plane_context=lambda: None,
        _activate_select_tool=lambda: None,
        _refresh_tree=lambda: None,
        _refresh_all=lambda *_args, **_kwargs: None,
        _record_project_change=lambda *_args, **_kwargs: None,
        _log=lambda *_args, **_kwargs: None,
        status_message=SimpleNamespace(setText=lambda *_args: None),
        status_counts=SimpleNamespace(setText=lambda *_args: None),
    )

    monkeypatch.setattr(main_window_module, "RCWallWizard", _FakeWizard)

    MainWindow._show_rc_wall_wizard(holder)

    assert holder.model is project.model
    assert len(project.model.nodes) == 16
    assert len(project.model.elements) == 7
    assert {element.element_type for element in project.model.elements.values()} == {"MEFI"}
    assert viewport.domain == "fe"
    assert viewport.view == "xy"
    assert selected["elements"] == set(project.model.elements)


@pytest.mark.skipif(
    viewport_module.QtInteractor is None,
    reason="PyVista/pyvistaqt not installed in lightweight unit-test job",
)
def test_rc_wall_qaction_trigger_generates_wall_in_real_mainwindow(monkeypatch):
    class _FakeWizard:
        def __init__(self, project, parent=None):
            self.project = project

        def exec(self):
            return int(QDialog.DialogCode.Accepted)

        def data(self):
            return RCWallSpec()

    monkeypatch.setattr(main_window_module, "RCWallWizard", _FakeWizard)

    window = MainWindow()
    try:
        assert not window.project.model.nodes
        assert not window.project.model.elements

        window.actions["rc_wall_wizard"].trigger()
        _APP.processEvents()

        assert len(window.project.model.nodes) == 16
        assert len(window.project.model.elements) == 7
        assert {
            element.element_type
            for element in window.project.model.elements.values()
        } == {"MEFI"}
        assert window.viewport._display_domain == "fe"
    finally:
        window.close()
        window.deleteLater()
        _APP.processEvents()
