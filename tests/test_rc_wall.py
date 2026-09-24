from __future__ import annotations

import inspect
import math
import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QDialog, QWizard

from openseespy_studio.generator import build_mefi_crack_specs, to_openseespy
from openseespy_studio.project import AnalysisSettingsData, ProjectDatabase
from openseespy_studio.rc_wall import RCWallSpec, build_rc_wall
import openseespy_studio.ui.main_window as main_window_module
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
