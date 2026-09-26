from __future__ import annotations

import inspect
import math
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QComboBox, QWizard

from openseespy_studio.frame_setup import prepare_frame_grid
from openseespy_studio.generator import (
    FrameGridSpec,
    frame_brace_element_count,
    frame_brace_panel_count,
    frame_brace_panels,
    frame_brace_storeys,
    frame_brace_x_bays,
    frame_brace_x_grid_lines,
    frame_brace_y_bays,
    frame_brace_y_grid_lines,
    frame_diaphragm_count,
    frame_diaphragm_levels,
    frame_floor_levels,
    frame_foundation_count,
    frame_foundation_profile_assignments,
    frame_foundation_profiles,
    frame_grid_coordinates,
    frame_slab_count,
    frame_joint_connection_count,
    frame_load_storeys,
    generate_frame_grid,
    generate_frame_project,
    to_openseespy,
    validate_frame_grid_spec,
)
from openseespy_studio.model import StructuralModel
from openseespy_studio.project import MaterialData, ProjectDatabase, SectionData
from openseespy_studio.ui.frame_wizard import FrameWizard
from openseespy_studio.ui.main_window import MainWindow


_APP = QApplication.instance() or QApplication([])


def test_frame_wizard_starts_as_regular_2d_frame_with_live_preview():
    project = ProjectDatabase()
    project.units = {"length": "m", "force": "kN", "time": "s"}
    wizard = FrameWizard(project)
    try:
        assert wizard.dimension.currentData() == "2D"
        assert wizard.x_bays.value() == 3
        assert wizard.storeys.value() == 3
        assert not wizard.y_bays.isEnabled()
        assert not wizard.y_spacing.isEnabled()
        assert not wizard.create_beams_y.isEnabled()
        assert wizard.base_support.isEnabled()
        assert wizard.preview.objectName() == "frame-wizard-live-preview"
        assert "Nodes: 16" in wizard.summary.text()
        assert "Columns: 12" in wizard.summary.text()
        assert "X beams: 9" in wizard.summary.text()

        spec = wizard.spec()
        assert spec.planar_2d
        assert spec.nx == 3
        assert spec.nz == 3
        assert spec.dx == 5.0
        assert spec.dz == 3.5
        assert spec.create_columns
        assert spec.create_beams_x
        assert not spec.create_beams_y
        assert spec.planar_base_support == "Fixed"
    finally:
        wizard.close()
        wizard.deleteLater()
        _APP.processEvents()


def test_frame_wizard_switches_to_3d_and_updates_counts_and_spec():
    wizard = FrameWizard(ProjectDatabase())
    try:
        wizard.dimension.setCurrentIndex(
            wizard.dimension.findData("3D")
        )
        wizard.x_bays.setValue(2)
        wizard.y_bays.setValue(2)
        wizard.storeys.setValue(2)
        _APP.processEvents()

        assert wizard.y_bays.isEnabled()
        assert wizard.y_spacing.isEnabled()
        assert wizard.create_beams_y.isEnabled()
        assert not wizard.base_support.isEnabled()
        assert wizard.create_beams_y.isChecked()
        assert "Nodes: 27" in wizard.summary.text()
        assert "Columns: 18" in wizard.summary.text()
        assert "X beams: 12" in wizard.summary.text()
        assert "Y beams: 12" in wizard.summary.text()
        assert "Total frame elements: 42" in wizard.summary.text()

        spec = wizard.spec()
        assert not spec.planar_2d
        assert (spec.nx, spec.ny, spec.nz) == (2, 2, 2)
        assert spec.create_beams_y
    finally:
        wizard.close()
        wizard.deleteLater()
        _APP.processEvents()


def test_frame_wizard_geometry_page_is_scrollable():
    wizard = FrameWizard(ProjectDatabase())
    try:
        assert wizard.geometry_scroll.widgetResizable()
        assert (
            wizard.geometry_scroll.horizontalScrollBarPolicy()
            == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        assert wizard.geometry_scroll.widget() is not None
    finally:
        wizard.close()
        wizard.deleteLater()
        _APP.processEvents()


def test_main_window_exposes_frame_wizard_action_and_handler():
    handler = inspect.getsource(MainWindow._show_frame_wizard)
    actions = inspect.getsource(MainWindow)
    assert "FrameWizard(self.project" in handler
    assert "dialog.spec()" in handler
    assert "self._generate_frame_grid(spec)" in handler
    assert '"frame_wizard"' in actions
    assert '"Frame Wizard"' in actions

def _set_spacing(editor, row: int, value: float) -> None:
    widget = editor.cellWidget(row, 0)
    assert widget is not None
    widget.setValue(value)


def test_frame_wizard_individual_spacing_and_origin_flow_to_spec():
    wizard = FrameWizard(ProjectDatabase())
    try:
        wizard.dimension.setCurrentIndex(
            wizard.dimension.findData("3D")
        )
        wizard.spacing_mode.setCurrentIndex(
            wizard.spacing_mode.findData("Individual")
        )
        wizard.x_bays.setValue(3)
        wizard.y_bays.setValue(2)
        wizard.storeys.setValue(3)

        for row, value in enumerate((4.0, 5.5, 6.0)):
            _set_spacing(wizard.x_spacing_editor, row, value)
        for row, value in enumerate((3.0, 4.5)):
            _set_spacing(wizard.y_spacing_editor, row, value)
        for row, value in enumerate((3.2, 3.4, 3.8)):
            _set_spacing(wizard.z_spacing_editor, row, value)

        wizard.origin_x.setValue(10.0)
        wizard.origin_y.setValue(-2.0)
        wizard.origin_z.setValue(1.5)
        _APP.processEvents()

        spec = wizard.spec()
        assert spec.x_bay_widths == (4.0, 5.5, 6.0)
        assert spec.y_bay_widths == (3.0, 4.5)
        assert spec.storey_heights == (3.2, 3.4, 3.8)
        assert (spec.origin_x, spec.origin_y, spec.origin_z) == (
            10.0,
            -2.0,
            1.5,
        )

        x, y, z = frame_grid_coordinates(spec)
        assert x == [10.0, 14.0, 19.5, 25.5]
        assert y == [-2.0, 1.0, 5.5]
        assert z == pytest.approx([1.5, 4.7, 8.1, 11.9])
        assert "overall X=15.5" in wizard.summary.text()
        assert "Y=7.5" in wizard.summary.text()
        assert "H=10.4" in wizard.summary.text()
        assert "Geometry ready" in wizard.validation_status.text()
    finally:
        wizard.close()
        wizard.deleteLater()
        _APP.processEvents()


def test_generate_frame_grid_uses_individual_coordinates_in_2d():
    model = StructuralModel()
    spec = FrameGridSpec(
        nx=2,
        ny=1,
        nz=2,
        dx=5.0,
        dy=6.0,
        dz=3.5,
        x_bay_widths=(4.0, 6.0),
        storey_heights=(3.0, 4.0),
        origin_x=10.0,
        origin_z=2.0,
        planar_2d=True,
        create_columns=True,
        create_beams_x=True,
        create_beams_y=False,
        planar_base_support="Pinned",
    )
    generate_frame_grid(model, spec)

    coordinates = {
        tuple(node.xyz)
        for node in model.nodes.values()
    }
    assert coordinates == {
        (10.0, 0.0, 2.0),
        (14.0, 0.0, 2.0),
        (20.0, 0.0, 2.0),
        (10.0, 0.0, 5.0),
        (14.0, 0.0, 5.0),
        (20.0, 0.0, 5.0),
        (10.0, 0.0, 9.0),
        (14.0, 0.0, 9.0),
        (20.0, 0.0, 9.0),
    }
    base = [
        node
        for node in model.nodes.values()
        if node.xyz[2] == 2.0
    ]
    assert len(base) == 3
    assert all(node.fixity == (1, 1, 1, 1, 0, 1) for node in base)


def test_generate_frame_grid_uses_individual_coordinates_in_3d():
    model = StructuralModel()
    spec = FrameGridSpec(
        nx=2,
        ny=2,
        nz=1,
        x_bay_widths=(4.0, 6.0),
        y_bay_widths=(3.0, 7.0),
        storey_heights=(3.5,),
        origin_x=1.0,
        origin_y=2.0,
        origin_z=-1.0,
    )
    generate_frame_grid(model, spec)

    coordinates = {
        tuple(node.xyz)
        for node in model.nodes.values()
    }
    assert (1.0, 2.0, -1.0) in coordinates
    assert (11.0, 12.0, 2.5) in coordinates
    assert len(model.nodes) == 18
    assert len(model.elements) == 21


def test_frame_grid_validation_rejects_bad_individual_spacing_and_empty_members():
    bad_count = FrameGridSpec(
        nx=3,
        x_bay_widths=(4.0, 5.0),
    )
    try:
        validate_frame_grid_spec(bad_count)
    except ValueError as exc:
        assert "spacing count" in str(exc)
    else:
        raise AssertionError("Expected bad spacing count to fail")

    no_members = FrameGridSpec(
        planar_2d=True,
        create_columns=False,
        create_beams_x=False,
        create_beams_y=False,
    )
    try:
        validate_frame_grid_spec(no_members)
    except ValueError as exc:
        assert "at least one member family" in str(exc)
    else:
        raise AssertionError("Expected empty frame topology to fail")


def test_frame_wizard_validation_blocks_empty_member_topology():
    wizard = FrameWizard(ProjectDatabase())
    try:
        wizard.create_columns.setChecked(False)
        wizard.create_beams_x.setChecked(False)
        wizard.create_beams_y.setChecked(False)
        _APP.processEvents()

        assert not wizard.validateCurrentPage()
        assert "at least one member family" in (
            wizard.validation_status.text()
        )
    finally:
        wizard.close()
        wizard.deleteLater()
        _APP.processEvents()

def _member_project() -> ProjectDatabase:
    project = ProjectDatabase()
    project.units = {"length": "m", "force": "N", "time": "s"}
    project.add_section(
        SectionData(
            1,
            "Elastic Frame",
            "Elastic",
            parameters={
                "E": 2.0e11,
                "A": 0.03,
                "Iz": 1.2e-4,
                "Iy": 9.0e-5,
                "G": 7.7e10,
                "J": 6.0e-5,
                "Avy": 0.025,
                "Avz": 0.025,
            },
        )
    )
    project.add_section(
        SectionData(
            2,
            "Fiber Frame",
            "Fiber",
            parameters={"GJ": 1.0e6},
        )
    )
    return project


def test_frame_wizard_member_page_filters_sections_by_formulation():
    wizard = FrameWizard(_member_project())
    try:
        assert wizard.pageIds() == [
            wizard.geometry_page_id,
            wizard.members_page_id,
            wizard.joints_page_id,
            wizard.floors_page_id,
            wizard.foundation_page_id,
            wizard.bracing_page_id,
            wizard.loads_page_id,
            wizard.mass_page_id,
            wizard.review_page_id,
        ]
        assert wizard.column_section.findData(1) >= 0
        assert wizard.column_section.findData(2) < 0
        assert wizard.beam_section.findData(1) >= 0
        assert wizard.beam_section.findData(2) < 0

        wizard.column_formulation.setCurrentIndex(
            wizard.column_formulation.findData("forceBeamColumn")
        )
        wizard.beam_formulation.setCurrentIndex(
            wizard.beam_formulation.findData("dispBeamColumn")
        )
        _APP.processEvents()

        assert wizard.column_section.findData(1) >= 0
        assert wizard.column_section.findData(2) >= 0
        assert wizard.beam_section.findData(1) >= 0
        assert wizard.beam_section.findData(2) >= 0
        assert wizard.column_integration.isEnabled()
        assert wizard.column_integration_points.isEnabled()
        assert wizard.beam_integration.isEnabled()
        assert wizard.beam_integration_points.isEnabled()
    finally:
        wizard.close()
        wizard.deleteLater()
        _APP.processEvents()


def test_frame_wizard_member_page_requires_sections_when_members_exist():
    wizard = FrameWizard(ProjectDatabase())
    try:
        wizard.show()
        _APP.processEvents()
        wizard.setCurrentId(wizard.members_page_id)
        _APP.processEvents()

        assert wizard.currentId() == wizard.members_page_id
        assert not wizard.validateCurrentPage()
        assert "require a compatible primary section" in (
            wizard.member_validation_status.text()
        )
    finally:
        wizard.close()
        wizard.deleteLater()
        _APP.processEvents()


def test_frame_wizard_member_settings_flow_to_grid_spec():
    wizard = FrameWizard(_member_project())
    try:
        wizard.column_formulation.setCurrentIndex(
            wizard.column_formulation.findData("forceBeamColumn")
        )
        wizard.beam_formulation.setCurrentIndex(
            wizard.beam_formulation.findData("dispBeamColumn")
        )
        wizard.column_section.setCurrentIndex(
            wizard.column_section.findData(2)
        )
        wizard.beam_section.setCurrentIndex(
            wizard.beam_section.findData(1)
        )
        wizard.column_integration.setCurrentIndex(
            wizard.column_integration.findData("Radau")
        )
        wizard.beam_integration.setCurrentIndex(
            wizard.beam_integration.findData("Legendre")
        )
        wizard.column_integration_points.setValue(4)
        wizard.beam_integration_points.setValue(6)
        _APP.processEvents()

        spec = wizard.spec()
        assert spec.column_element_type == "forceBeamColumn"
        assert spec.beam_element_type == "dispBeamColumn"
        assert spec.column_section_tag == 2
        assert spec.beam_section_tag == 1
        assert spec.column_transf_tag is None
        assert spec.beam_transf_tag is None
        assert spec.column_integration_type == "Radau"
        assert spec.beam_integration_type == "Legendre"
        assert spec.column_integration_points == 4
        assert spec.beam_integration_points == 6
    finally:
        wizard.close()
        wizard.deleteLater()
        _APP.processEvents()


def test_frame_grid_backend_assigns_member_formulations_and_integrations():
    project = _member_project()
    spec = FrameGridSpec(
        nx=1,
        ny=1,
        nz=1,
        planar_2d=True,
        create_columns=True,
        create_beams_x=True,
        create_beams_y=False,
        column_section_tag=1,
        beam_section_tag=1,
        column_element_type="forceBeamColumn",
        beam_element_type="dispBeamColumn",
        column_integration_type="Radau",
        beam_integration_type="Legendre",
        column_integration_points=4,
        beam_integration_points=6,
    )

    prepare_frame_grid(project, spec)
    generate_frame_grid(project.model, spec)

    columns = [
        element
        for element in project.model.elements.values()
        if element.group == "column-2d"
    ]
    beams = [
        element
        for element in project.model.elements.values()
        if element.group == "beam-2d"
    ]
    assert len(columns) == 2
    assert len(beams) == 1
    assert all(
        element.element_type == "forceBeamColumn"
        for element in columns
    )
    assert all(
        element.integration_type == "Radau"
        and element.integration_points == 4
        for element in columns
    )
    assert all(
        element.element_type == "dispBeamColumn"
        for element in beams
    )
    assert all(
        element.integration_type == "Legendre"
        and element.integration_points == 6
        for element in beams
    )
    assert spec.column_transf_tag in project.transformations
    assert spec.beam_transf_tag in project.transformations
    assert (
        project.transformations[spec.column_transf_tag].transformation_type
        == "PDelta"
    )
    assert (
        project.transformations[spec.beam_transf_tag].transformation_type
        == "Linear"
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
    )
    assert "ops.beamIntegration('Radau'" in script
    assert "ops.element('forceBeamColumn'" in script
    assert "ops.beamIntegration('Legendre'" in script
    assert "ops.element('dispBeamColumn'" in script
    assert "# ERROR:" not in script


def test_frame_grid_validation_rejects_unsupported_member_formulation():
    spec = FrameGridSpec(
        planar_2d=True,
        column_element_type="notAFrameElement",
    )
    with pytest.raises(ValueError, match="Column formulation"):
        validate_frame_grid_spec(spec)

def test_frame_wizard_hinge_integration_controls_and_defaults():
    wizard = FrameWizard(_member_project())
    try:
        wizard.column_formulation.setCurrentIndex(
            wizard.column_formulation.findData("forceBeamColumn")
        )
        wizard.column_section.setCurrentIndex(
            wizard.column_section.findData(1)
        )
        wizard.column_integration.setCurrentIndex(
            wizard.column_integration.findData("HingeRadau")
        )
        _APP.processEvents()

        assert wizard.column_hinge_i_section.isEnabled()
        assert wizard.column_hinge_j_section.isEnabled()
        assert wizard.column_interior_section.isEnabled()
        assert wizard.column_hinge_i_length.isEnabled()
        assert wizard.column_hinge_j_length.isEnabled()
        assert not wizard.column_integration_points.isEnabled()
        assert wizard.column_hinge_i_section.currentData() == 1
        assert wizard.column_hinge_j_section.currentData() == 1
        assert wizard.column_interior_section.currentData() == 1

        wizard.column_integration.setCurrentIndex(
            wizard.column_integration.findData(
                "ConcentratedPlasticity"
            )
        )
        _APP.processEvents()
        assert not wizard.column_hinge_i_length.isEnabled()
        assert not wizard.column_hinge_j_length.isEnabled()

        wizard.column_formulation.setCurrentIndex(
            wizard.column_formulation.findData("elasticBeamColumn")
        )
        _APP.processEvents()
        assert not wizard.column_integration.isEnabled()
        assert not wizard.column_hinge_i_section.isEnabled()
    finally:
        wizard.close()
        wizard.deleteLater()
        _APP.processEvents()


def test_frame_wizard_force_based_disables_consistent_mass():
    wizard = FrameWizard(_member_project())
    try:
        wizard.column_consistent_mass.setChecked(True)
        wizard.column_formulation.setCurrentIndex(
            wizard.column_formulation.findData("forceBeamColumn")
        )
        _APP.processEvents()

        assert not wizard.column_consistent_mass.isEnabled()
        assert not wizard.column_consistent_mass.isChecked()

        wizard.beam_formulation.setCurrentIndex(
            wizard.beam_formulation.findData("dispBeamColumn")
        )
        wizard.beam_consistent_mass.setChecked(True)
        _APP.processEvents()
        assert wizard.beam_consistent_mass.isEnabled()
        assert wizard.spec().beam_consistent_mass
    finally:
        wizard.close()
        wizard.deleteLater()
        _APP.processEvents()


def test_frame_wizard_advanced_hinge_and_mass_settings_flow_to_spec():
    wizard = FrameWizard(_member_project())
    try:
        wizard.column_formulation.setCurrentIndex(
            wizard.column_formulation.findData("forceBeamColumn")
        )
        wizard.beam_formulation.setCurrentIndex(
            wizard.beam_formulation.findData("dispBeamColumn")
        )
        wizard.column_section.setCurrentIndex(
            wizard.column_section.findData(1)
        )
        wizard.beam_section.setCurrentIndex(
            wizard.beam_section.findData(1)
        )
        wizard.column_integration.setCurrentIndex(
            wizard.column_integration.findData("HingeRadauTwo")
        )
        wizard.beam_integration.setCurrentIndex(
            wizard.beam_integration.findData(
                "ConcentratedPlasticity"
            )
        )

        for combo in (
            wizard.column_hinge_i_section,
            wizard.column_hinge_j_section,
            wizard.column_interior_section,
            wizard.beam_hinge_i_section,
            wizard.beam_hinge_j_section,
            wizard.beam_interior_section,
        ):
            combo.setCurrentIndex(combo.findData(1))

        wizard.column_hinge_i_length.setValue(0.25)
        wizard.column_hinge_j_length.setValue(0.35)
        wizard.beam_mass_per_length.setValue(12.5)
        wizard.column_mass_per_length.setValue(15.0)
        wizard.beam_consistent_mass.setChecked(True)
        _APP.processEvents()

        spec = wizard.spec()
        assert spec.column_integration_type == "HingeRadauTwo"
        assert spec.column_hinge_i_section_tag == 1
        assert spec.column_hinge_j_section_tag == 1
        assert spec.column_interior_section_tag == 1
        assert spec.column_hinge_i_length == pytest.approx(0.25)
        assert spec.column_hinge_j_length == pytest.approx(0.35)
        assert spec.beam_integration_type == "ConcentratedPlasticity"
        assert spec.beam_hinge_i_section_tag == 1
        assert spec.beam_hinge_j_section_tag == 1
        assert spec.beam_interior_section_tag == 1
        assert spec.column_mass_per_length == pytest.approx(15.0)
        assert spec.beam_mass_per_length == pytest.approx(12.5)
        assert not spec.column_consistent_mass
        assert spec.beam_consistent_mass
    finally:
        wizard.close()
        wizard.deleteLater()
        _APP.processEvents()


def test_frame_grid_backend_assigns_hinges_mass_and_consistent_mass():
    project = _member_project()
    spec = FrameGridSpec(
        nx=1,
        ny=1,
        nz=1,
        planar_2d=True,
        create_columns=True,
        create_beams_x=True,
        create_beams_y=False,
        column_section_tag=1,
        beam_section_tag=1,
        column_element_type="forceBeamColumn",
        beam_element_type="dispBeamColumn",
        column_integration_type="HingeRadau",
        beam_integration_type="ConcentratedPlasticity",
        column_hinge_i_section_tag=1,
        column_hinge_j_section_tag=1,
        column_interior_section_tag=1,
        beam_hinge_i_section_tag=1,
        beam_hinge_j_section_tag=1,
        beam_interior_section_tag=1,
        column_hinge_i_length=0.25,
        column_hinge_j_length=0.30,
        column_mass_per_length=10.0,
        beam_mass_per_length=8.0,
        beam_consistent_mass=True,
    )
    prepare_frame_grid(project, spec)
    generate_frame_grid(project.model, spec)

    columns = [
        element
        for element in project.model.elements.values()
        if element.group == "column-2d"
    ]
    beams = [
        element
        for element in project.model.elements.values()
        if element.group == "beam-2d"
    ]
    assert columns
    assert beams
    assert all(
        element.integration_type == "HingeRadau"
        and element.hinge_i_section_tag == 1
        and element.hinge_j_section_tag == 1
        and element.interior_section_tag == 1
        and element.hinge_i_length == pytest.approx(0.25)
        and element.hinge_j_length == pytest.approx(0.30)
        and element.mass_per_length == pytest.approx(10.0)
        for element in columns
    )
    assert all(
        element.integration_type == "ConcentratedPlasticity"
        and element.hinge_i_section_tag == 1
        and element.hinge_j_section_tag == 1
        and element.interior_section_tag == 1
        and element.mass_per_length == pytest.approx(8.0)
        and element.consistent_mass
        for element in beams
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
    )
    assert "ops.beamIntegration('HingeRadau'" in script
    assert "ops.beamIntegration('ConcentratedPlasticity'" in script
    assert "'-mass', 10" in script
    assert "'-cMass'" in script
    assert "'-mass', 8" in script
    assert "# ERROR:" not in script


@pytest.mark.parametrize(
    "integration",
    [
        "HingeRadau",
        "HingeRadauTwo",
        "HingeMidpoint",
        "HingeEndpoint",
    ],
)
def test_frame_grid_validation_accepts_supported_hinge_integrations(
    integration: str,
):
    spec = FrameGridSpec(
        planar_2d=True,
        column_element_type="forceBeamColumn",
        column_integration_type=integration,
        column_hinge_i_section_tag=1,
        column_hinge_j_section_tag=1,
        column_interior_section_tag=1,
        column_hinge_i_length=0.20,
        column_hinge_j_length=0.20,
    )
    validate_frame_grid_spec(spec)


def test_frame_grid_validation_rejects_incomplete_hinge_definition():
    missing = FrameGridSpec(
        planar_2d=True,
        column_element_type="forceBeamColumn",
        column_integration_type="HingeRadau",
    )
    with pytest.raises(ValueError, match="I-end, J-end"):
        validate_frame_grid_spec(missing)

    zero_length = FrameGridSpec(
        planar_2d=True,
        column_element_type="forceBeamColumn",
        column_integration_type="HingeMidpoint",
        column_hinge_i_section_tag=1,
        column_hinge_j_section_tag=1,
        column_interior_section_tag=1,
        column_hinge_i_length=0.0,
        column_hinge_j_length=0.20,
    )
    with pytest.raises(ValueError, match="positive I/J"):
        validate_frame_grid_spec(zero_length)


def test_member_review_reports_hinge_and_mass_configuration():
    wizard = FrameWizard(_member_project())
    try:
        wizard.beam_formulation.setCurrentIndex(
            wizard.beam_formulation.findData("dispBeamColumn")
        )
        wizard.beam_section.setCurrentIndex(
            wizard.beam_section.findData(1)
        )
        wizard.beam_integration.setCurrentIndex(
            wizard.beam_integration.findData("HingeEndpoint")
        )
        for combo in (
            wizard.beam_hinge_i_section,
            wizard.beam_hinge_j_section,
            wizard.beam_interior_section,
        ):
            combo.setCurrentIndex(combo.findData(1))
        wizard.beam_hinge_i_length.setValue(0.2)
        wizard.beam_hinge_j_length.setValue(0.3)
        wizard.beam_mass_per_length.setValue(7.5)
        wizard.beam_consistent_mass.setChecked(True)
        wizard._update_member_summary()
        _APP.processEvents()

        review = wizard.member_summary.text()
        assert "HingeEndpoint" in review
        assert "LpI=0.2" in review
        assert "LpJ=0.3" in review
        assert "mass/L=7.5" in review
        assert "consistent mass" in review
    finally:
        wizard.close()
        wizard.deleteLater()
        _APP.processEvents()



def _joint_project() -> ProjectDatabase:
    project = ProjectDatabase()
    project.materials[9] = MaterialData(
        tag=9,
        name="Frame rotational spring",
        material_type="Elastic",
        parameters={"E": 1.0e6},
        source={
            "response_quantity": "moment_rotation",
            "parameter_dimensions": {"E": "stiffness"},
        },
    )
    return project


def test_frame_wizard_task3_zero_length_joint_spec_and_summary():
    wizard = FrameWizard(_joint_project())
    try:
        wizard.joint_model.setCurrentIndex(
            wizard.joint_model.findData("ZeroLength")
        )
        wizard.joint_material.setCurrentIndex(
            wizard.joint_material.findData(9)
        )
        _APP.processEvents()

        spec = wizard.spec()
        assert spec.joint_model == "ZeroLength"
        assert spec.joint_material_tag == 9
        assert spec.joint_scope == "all"
        assert frame_joint_connection_count(spec) == 12
        assert "Explicit springs: 12" in wizard.joint_summary.text()
        assert "Duplicate beam-side nodes: 12" in wizard.joint_summary.text()
        assert "Joint definition ready" in wizard.joint_validation_status.text()
        assert wizard.joints_scroll.widgetResizable()
    finally:
        wizard.close()
        wizard.deleteLater()
        _APP.processEvents()


def test_frame_wizard_joint_material_is_required_for_zero_length_mode():
    wizard = FrameWizard(ProjectDatabase())
    try:
        wizard.joint_model.setCurrentIndex(
            wizard.joint_model.findData("ZeroLength")
        )
        _APP.processEvents()
        assert "rotational" in wizard._joint_validation_error().lower()
        with pytest.raises(ValueError, match="rotational"):
            validate_frame_grid_spec(wizard.spec())
    finally:
        wizard.close()
        wizard.deleteLater()
        _APP.processEvents()


def test_generate_frame_project_builds_2d_zero_length_joint_topology():
    project = _joint_project()
    spec = FrameGridSpec(
        nx=2,
        ny=1,
        nz=1,
        dx=5.0,
        dz=3.5,
        planar_2d=True,
        create_columns=True,
        create_beams_x=True,
        create_beams_y=False,
        joint_model="ZeroLength",
        joint_material_tag=9,
    )

    result = generate_frame_project(project, spec)

    assert result == {
        "joint_nodes": 3,
        "joint_connections": 3,
        "duplicate_nodes": 3,
        "joint_constraints": 3,
    }
    assert len(project.model.nodes) == 9
    assert len(project.connections) == 3
    assert len(project.constraints) == 3

    original_top_nodes = {4, 5, 6}
    duplicate_nodes = set(project.model.nodes) - set(range(1, 7))
    assert duplicate_nodes == {7, 8, 9}

    beams = [
        element
        for element in project.model.elements.values()
        if element.group == "beam-2d"
    ]
    assert len(beams) == 2
    assert all(
        element.i in duplicate_nodes and element.j in duplicate_nodes
        for element in beams
    )
    assert all(
        connection.node_i in original_top_nodes
        and connection.node_j in duplicate_nodes
        and connection.materials_by_dof == {5: 9}
        for connection in project.connections.values()
    )
    assert all(
        constraint.dofs == (1, 2, 3, 4, 6)
        for constraint in project.constraints.values()
    )


def test_generate_frame_project_builds_independent_x_y_springs_in_3d():
    project = _joint_project()
    spec = FrameGridSpec(
        nx=1,
        ny=1,
        nz=1,
        planar_2d=False,
        create_columns=True,
        create_beams_x=True,
        create_beams_y=True,
        joint_model="ZeroLength",
        joint_material_tag=9,
    )

    result = generate_frame_project(project, spec)

    assert result["joint_nodes"] == 4
    assert result["joint_connections"] == 8
    assert result["duplicate_nodes"] == 8
    assert {
        next(iter(connection.materials_by_dof))
        for connection in project.connections.values()
    } == {4, 5}


def test_frame_joint_scope_interior_reduces_generated_springs():
    project = _joint_project()
    spec = FrameGridSpec(
        nx=3,
        ny=1,
        nz=2,
        planar_2d=True,
        create_columns=True,
        create_beams_x=True,
        create_beams_y=False,
        joint_model="ZeroLength",
        joint_material_tag=9,
        joint_scope="interior",
    )
    assert frame_joint_connection_count(spec) == 4
    result = generate_frame_project(project, spec)
    assert result["joint_connections"] == 4


def test_frame_wizard_joint2d_requires_panel_material():
    spec = FrameGridSpec(
        planar_2d=True,
        joint_model="Joint2D",
    )
    with pytest.raises(ValueError, match="panel rotational material"):
        validate_frame_grid_spec(spec)


def _macro_joint_project() -> ProjectDatabase:
    project = _member_project()
    for tag in range(21, 35):
        project.materials[tag] = MaterialData(
            tag=tag,
            name=f"Joint material {tag}",
            material_type="Elastic",
            parameters={"E": 1.0e7 + tag},
            source={
                "response_quantity": "moment_rotation",
                "parameter_dimensions": {"E": "stiffness"},
            },
        )
    return project


def test_frame_wizard_exposes_task3_macro_joint_controls():
    wizard = FrameWizard(_macro_joint_project())
    try:
        assert wizard.joint_model.findData("Joint2D") >= 0
        assert wizard.joint_model.findData("BeamColumnJoint") >= 0
        assert wizard.joint_model.findData("KrawinklerPanelZone") >= 0

        wizard.joint_model.setCurrentIndex(
            wizard.joint_model.findData("Joint2D")
        )
        wizard.joint_material.setCurrentIndex(
            wizard.joint_material.findData(21)
        )
        _APP.processEvents()
        assert not wizard.joint_panel_group.isHidden()
        assert not wizard.joint2d_group.isHidden()
        assert wizard.bcj_group.isHidden()
        assert wizard.kraw_group.isHidden()

        wizard.joint_model.setCurrentIndex(
            wizard.joint_model.findData("BeamColumnJoint")
        )
        for index, combo in enumerate(wizard.bcj_materials):
            combo.setCurrentIndex(combo.findData(21 + index))
        _APP.processEvents()
        assert not wizard.bcj_group.isHidden()
        assert not wizard.joint_material.isEnabled()
        assert wizard.spec().joint_component_material_tags == tuple(
            range(21, 34)
        )
    finally:
        wizard.close()
        wizard.deleteLater()
        _APP.processEvents()


def test_frame_macro_joint_validation_is_native_2d_only():
    spec = FrameGridSpec(
        planar_2d=False,
        joint_model="Joint2D",
        joint_material_tag=21,
    )
    with pytest.raises(ValueError, match="switch the frame dimension to 2D"):
        validate_frame_grid_spec(spec)


def test_generate_joint2d_frame_creates_external_core_nodes_and_shortens_members():
    project = _macro_joint_project()
    spec = FrameGridSpec(
        nx=1,
        ny=1,
        nz=1,
        dx=5.0,
        dz=3.5,
        planar_2d=True,
        create_columns=True,
        create_beams_x=True,
        create_beams_y=False,
        column_section_tag=1,
        beam_section_tag=1,
        joint_model="Joint2D",
        joint_material_tag=21,
        joint_panel_width=0.40,
        joint_panel_height=0.50,
        joint_interface_material_tags=(0, 0, 0, 0),
        joint_large_disp=0,
    )
    result = generate_frame_project(project, spec)

    assert project.model.ndm == 2
    assert project.model.ndf == 3
    assert result["joint_connections"] == 2
    assert result["panel_external_nodes"] == 8
    assert len(project.connections) == 2
    assert all(
        connection.connection_type == "Joint2D"
        for connection in project.connections.values()
    )

    first = project.connections[min(project.connections)]
    left, top, right, bottom = first.parameters["external_nodes"]
    coords = project.model.nodes
    assert coords[left].xyz[:2] == pytest.approx((-0.20, 3.5))
    assert coords[top].xyz[:2] == pytest.approx((0.0, 3.75))
    assert coords[right].xyz[:2] == pytest.approx((0.20, 3.5))
    assert coords[bottom].xyz[:2] == pytest.approx((0.0, 3.25))

    columns = [
        element
        for element in project.model.elements.values()
        if element.group == "column-2d"
    ]
    beams = [
        element
        for element in project.model.elements.values()
        if element.group == "beam-2d"
    ]
    assert len(columns) == 2
    assert len(beams) == 1
    assert any(
        project.model.nodes[element.j].xyz[1] == pytest.approx(3.25)
        for element in columns
    )


def test_generate_beamcolumnjoint_uses_thirteen_component_materials():
    project = _macro_joint_project()
    tags = tuple(range(21, 34))
    spec = FrameGridSpec(
        nx=1,
        nz=1,
        planar_2d=True,
        create_columns=True,
        create_beams_x=True,
        create_beams_y=False,
        column_section_tag=1,
        beam_section_tag=1,
        joint_model="BeamColumnJoint",
        joint_panel_width=0.40,
        joint_panel_height=0.50,
        joint_component_material_tags=tags,
        joint_height_factor=0.95,
        joint_width_factor=0.90,
    )
    result = generate_frame_project(project, spec)
    assert result["joint_connections"] == 2
    assert all(
        tuple(connection.parameters["component_materials"]) == tags
        for connection in project.connections.values()
    )
    assert all(
        connection.parameters["height_factor"] == pytest.approx(0.95)
        and connection.parameters["width_factor"] == pytest.approx(0.90)
        for connection in project.connections.values()
    )


def test_generate_krawinkler_native_2d_uses_rz_direction_six():
    project = _macro_joint_project()
    spec = FrameGridSpec(
        nx=1,
        nz=1,
        planar_2d=True,
        create_columns=True,
        create_beams_x=True,
        create_beams_y=False,
        column_section_tag=1,
        beam_section_tag=1,
        joint_model="KrawinklerPanelZone",
        joint_material_tag=21,
        joint_panel_width=0.40,
        joint_panel_height=0.50,
        joint_rigid_a=1000.0,
        joint_rigid_e=2.0e12,
        joint_rigid_i=1000.0,
    )
    prepare_frame_grid(project, spec)
    generate_frame_project(project, spec)
    source = to_openseespy(
        project.model,
        materials=project.materials,
        sections=project.sections,
        transformations=project.transformations,
        constraints=project.constraints,
        connections=project.connections,
        units=project.units,
        nd_materials=project.nd_materials,
    )
    assert "ops.model('basic', '-ndm', 2, '-ndf', 3)" in source
    assert "Krawinkler panel-zone macro" in source
    assert "'-dir', 6" in source


def test_frame_macro_joint_panel_must_fit_grid_spacing():
    spec = FrameGridSpec(
        nx=1,
        nz=1,
        dx=0.40,
        dz=0.50,
        planar_2d=True,
        joint_model="Joint2D",
        joint_material_tag=21,
        joint_panel_width=0.40,
        joint_panel_height=0.25,
    )
    with pytest.raises(ValueError, match="smaller than every X bay"):
        validate_frame_grid_spec(spec)


def test_main_window_frame_wizard_dispatches_and_views_macro_joint_models():
    source = inspect.getsource(MainWindow._generate_frame_grid)
    assert "generate_frame_project(self.project, spec)" in source
    assert '"Joint2D"' in source
    assert '"BeamColumnJoint"' in source
    assert '"KrawinklerPanelZone"' in source
    assert 'self.viewport.set_view("xy")' in source
    assert 'self.viewport.set_view("xz")' in source
    assert "joint core(s)" in source


def test_frame_project_restores_standard_backend_after_macro_generation():
    project = _macro_joint_project()
    macro = FrameGridSpec(
        nx=1,
        nz=1,
        planar_2d=True,
        create_columns=True,
        create_beams_x=True,
        create_beams_y=False,
        column_section_tag=1,
        beam_section_tag=1,
        joint_model="Joint2D",
        joint_material_tag=21,
        joint_panel_width=0.40,
        joint_panel_height=0.50,
        joint_interface_material_tags=(0, 0, 0, 0),
    )
    generate_frame_project(project, macro)
    assert (project.model.ndm, project.model.ndf) == (2, 3)
    assert project.connections

    standard = FrameGridSpec(
        nx=1,
        nz=1,
        planar_2d=True,
        create_columns=True,
        create_beams_x=True,
        create_beams_y=False,
        column_section_tag=1,
        beam_section_tag=1,
        joint_model="None",
    )
    generate_frame_project(project, standard)
    assert (project.model.ndm, project.model.ndf) == (3, 6)
    assert not project.connections
    assert all(node.ndf == 6 for node in project.model.nodes.values())


def test_frame_wizard_task4_floor_page_defaults_and_level_selection():
    wizard = FrameWizard(_member_project())
    try:
        assert wizard.diaphragm_mode.currentData() == "None"
        assert wizard.diaphragm_level_table.rowCount() == 3
        assert wizard.floors_scroll.widgetResizable()
        assert all(
            wizard.diaphragm_level_table.item(row, 0).checkState()
            == Qt.Checked
            for row in range(3)
        )

        wizard.dimension.setCurrentIndex(
            wizard.dimension.findData("3D")
        )
        wizard.diaphragm_mode.setCurrentIndex(
            wizard.diaphragm_mode.findData("Rigid")
        )
        wizard.diaphragm_floor_mass.setValue(125.0)
        wizard.diaphragm_rotational_inertia.setValue(80.0)
        wizard.diaphragm_level_table.item(1, 0).setCheckState(
            Qt.Unchecked
        )
        _APP.processEvents()

        spec = wizard.spec()
        assert spec.diaphragm_mode == "Rigid"
        assert spec.diaphragm_levels == (1, 3)
        assert spec.diaphragm_floor_mass == pytest.approx(125.0)
        assert spec.diaphragm_rotational_inertia == pytest.approx(80.0)
        assert frame_diaphragm_levels(spec) == (1, 3)
        assert frame_diaphragm_count(spec) == 2
        assert "Rigid diaphragms: 2" in wizard.diaphragm_summary.text()
        assert "Floor definition ready" in (
            wizard.diaphragm_validation_status.text()
        )
    finally:
        wizard.close()
        wizard.deleteLater()
        _APP.processEvents()


def test_frame_wizard_rigid_diaphragm_rejects_2d_frame():
    wizard = FrameWizard(_member_project())
    try:
        wizard.diaphragm_mode.setCurrentIndex(
            wizard.diaphragm_mode.findData("Rigid")
        )
        _APP.processEvents()
        assert "require a 3D frame" in wizard._diaphragm_validation_error()
        with pytest.raises(ValueError, match="require a 3D frame"):
            validate_frame_grid_spec(wizard.spec())
    finally:
        wizard.close()
        wizard.deleteLater()
        _APP.processEvents()


def test_generate_frame_project_builds_centroid_rigid_diaphragms():
    project = _member_project()
    spec = FrameGridSpec(
        nx=2,
        ny=1,
        nz=2,
        dx=4.0,
        dy=6.0,
        dz=3.0,
        planar_2d=False,
        create_columns=True,
        create_beams_x=True,
        create_beams_y=True,
        column_section_tag=1,
        beam_section_tag=1,
        diaphragm_mode="Rigid",
        diaphragm_levels=(1, 2),
        diaphragm_floor_mass=20.0,
        diaphragm_rotational_inertia=7.5,
    )
    prepare_frame_grid(project, spec)
    result = generate_frame_project(project, spec)

    assert result["diaphragm_constraints"] == 2
    assert result["diaphragm_master_nodes"] == 2
    rigid = [
        constraint
        for constraint in project.constraints.values()
        if constraint.constraint_type == "rigidDiaphragm"
    ]
    assert len(rigid) == 2
    assert all(constraint.perp_dirn == 3 for constraint in rigid)
    assert all(len(constraint.constrained_nodes) == 6 for constraint in rigid)

    masters = [
        project.model.nodes[constraint.retained_node]
        for constraint in rigid
    ]
    assert {tuple(node.xyz) for node in masters} == {
        (4.0, 3.0, 3.0),
        (4.0, 3.0, 6.0),
    }
    assert all(node.fixity == (0, 0, 1, 1, 1, 0) for node in masters)
    assert all(
        node.mass == pytest.approx((20.0, 20.0, 0.0, 0.0, 0.0, 7.5))
        for node in masters
    )


def test_frame_rigid_diaphragm_empty_level_tuple_means_all_floors():
    spec = FrameGridSpec(
        nx=1,
        ny=1,
        nz=3,
        planar_2d=False,
        diaphragm_mode="Rigid",
    )
    assert frame_diaphragm_levels(spec) == (1, 2, 3)
    assert frame_diaphragm_count(spec) == 3


def test_frame_rigid_diaphragm_validates_level_and_mass_inputs():
    bad_level = FrameGridSpec(
        nx=1,
        ny=1,
        nz=2,
        planar_2d=False,
        diaphragm_mode="Rigid",
        diaphragm_levels=(3,),
    )
    with pytest.raises(ValueError, match="between 1"):
        validate_frame_grid_spec(bad_level)

    bad_mass = FrameGridSpec(
        nx=1,
        ny=1,
        nz=2,
        planar_2d=False,
        diaphragm_mode="Rigid",
        diaphragm_floor_mass=-1.0,
    )
    with pytest.raises(ValueError, match="floor mass"):
        validate_frame_grid_spec(bad_mass)


def test_frame_rigid_diaphragm_coexists_with_zero_length_joints():
    project = _joint_project()
    project.add_section(
        SectionData(
            90,
            "3D elastic",
            "Elastic",
            parameters={
                "E": 2.0e11,
                "A": 0.03,
                "Iz": 1.2e-4,
                "Iy": 9.0e-5,
                "G": 7.7e10,
                "J": 6.0e-5,
                "Avy": 0.025,
                "Avz": 0.025,
            },
        )
    )
    spec = FrameGridSpec(
        nx=1,
        ny=1,
        nz=1,
        planar_2d=False,
        create_columns=True,
        create_beams_x=True,
        create_beams_y=True,
        column_section_tag=90,
        beam_section_tag=90,
        joint_model="ZeroLength",
        joint_material_tag=9,
        diaphragm_mode="Rigid",
        diaphragm_levels=(1,),
    )
    prepare_frame_grid(project, spec)
    result = generate_frame_project(project, spec)
    assert result["joint_connections"] == 8
    assert result["diaphragm_constraints"] == 1
    assert any(
        constraint.constraint_type == "rigidDiaphragm"
        for constraint in project.constraints.values()
    )


def _slab_project() -> ProjectDatabase:
    project = _member_project()
    project.add_section(
        SectionData(
            95,
            "Elastic Slab 200",
            "ElasticMembranePlate",
            parameters={
                "E": 30.0e9,
                "nu": 0.20,
                "h": 0.20,
                "rho": 0.0,
                "EpModifier": 1.0,
            },
        )
    )
    return project


def test_frame_wizard_task4_exposes_explicit_shell_slab_controls():
    wizard = FrameWizard(_slab_project())
    try:
        wizard.dimension.setCurrentIndex(
            wizard.dimension.findData("3D")
        )
        shell_index = wizard.diaphragm_mode.findData("Shell")
        assert shell_index >= 0
        wizard.diaphragm_mode.setCurrentIndex(shell_index)
        _APP.processEvents()

        assert wizard.slab_group.isVisible() or not wizard.slab_group.isHidden()
        assert wizard.slab_section.findData(95) >= 0
        assert wizard.slab_formulation.findData("ASDShellQ4") >= 0
        assert wizard.slab_formulation.findData("ShellMITC4") >= 0

        wizard.slab_section.setCurrentIndex(
            wizard.slab_section.findData(95)
        )
        wizard.slab_formulation.setCurrentIndex(
            wizard.slab_formulation.findData("ShellMITC4")
        )
        wizard.slab_divisions_x.setValue(2)
        wizard.slab_divisions_y.setValue(3)
        wizard.slab_mass_per_area.setValue(1.25)
        _APP.processEvents()

        spec = wizard.spec()
        assert spec.diaphragm_mode == "Shell"
        assert spec.slab_section_tag == 95
        assert spec.slab_element_type == "ShellMITC4"
        assert spec.slab_divisions_x == 2
        assert spec.slab_divisions_y == 3
        assert spec.slab_mass_per_area == pytest.approx(1.25)
        assert frame_floor_levels(spec) == (1, 2, 3)
        assert frame_slab_count(spec) == 3
        assert "Semi-rigid slab summary" in wizard.diaphragm_summary.text()
    finally:
        wizard.close()
        wizard.deleteLater()
        _APP.processEvents()


def test_frame_shell_slab_validation_rejects_2d_and_joint_bypass():
    planar = FrameGridSpec(
        planar_2d=True,
        diaphragm_mode="Shell",
        slab_section_tag=95,
    )
    with pytest.raises(ValueError, match="require a 3D frame"):
        validate_frame_grid_spec(planar)

    jointed = FrameGridSpec(
        planar_2d=False,
        joint_model="ZeroLength",
        joint_material_tag=9,
        diaphragm_mode="Shell",
        slab_section_tag=95,
    )
    with pytest.raises(ValueError, match="rigid centerline"):
        validate_frame_grid_spec(jointed)


def test_frame_shell_refined_mesh_rejects_nonlinear_beam_splitting():
    spec = FrameGridSpec(
        planar_2d=False,
        beam_element_type="forceBeamColumn",
        diaphragm_mode="Shell",
        slab_section_tag=95,
        slab_divisions_x=2,
        slab_divisions_y=1,
    )
    with pytest.raises(ValueError, match="elasticBeamColumn"):
        validate_frame_grid_spec(spec)


def test_generate_frame_shell_slab_one_element_per_bay_reuses_grid_nodes():
    project = _slab_project()
    spec = FrameGridSpec(
        nx=1,
        ny=1,
        nz=1,
        dx=5.0,
        dy=4.0,
        dz=3.0,
        planar_2d=False,
        create_columns=True,
        create_beams_x=True,
        create_beams_y=True,
        column_section_tag=1,
        beam_section_tag=1,
        diaphragm_mode="Shell",
        diaphragm_levels=(1,),
        slab_section_tag=95,
        slab_element_type="ASDShellQ4",
        slab_divisions_x=1,
        slab_divisions_y=1,
    )
    prepare_frame_grid(project, spec)
    result = generate_frame_project(project, spec)

    assert result["slab_floors"] == 1
    assert result["slab_elements"] == 1
    assert result["slab_nodes_created"] == 0
    assert result["slab_nodes_reused"] == 4
    assert result["slab_beam_segments_added"] == 0

    shells = [
        element
        for element in project.model.elements.values()
        if element.group == "slab:L1"
    ]
    assert len(shells) == 1
    shell = shells[0]
    assert shell.element_type == "ASDShellQ4"
    assert shell.section_tag == 95
    assert all(
        project.model.nodes[tag].xyz[2] == pytest.approx(3.0)
        for tag in shell.node_tags()
    )


def test_generate_refined_shell_slab_splits_elastic_beams_conformingly():
    project = _slab_project()
    spec = FrameGridSpec(
        nx=1,
        ny=1,
        nz=1,
        dx=5.0,
        dy=4.0,
        dz=3.0,
        planar_2d=False,
        create_columns=True,
        create_beams_x=True,
        create_beams_y=True,
        column_section_tag=1,
        beam_section_tag=1,
        diaphragm_mode="Shell",
        diaphragm_levels=(1,),
        slab_section_tag=95,
        slab_element_type="ShellMITC4",
        slab_divisions_x=2,
        slab_divisions_y=2,
        slab_mass_per_area=2.0,
    )
    prepare_frame_grid(project, spec)
    result = generate_frame_project(project, spec)

    assert result["slab_elements"] == 4
    assert result["slab_nodes_created"] == 5
    assert result["slab_nodes_reused"] == 4
    assert result["slab_beam_segments_added"] == 4
    assert result["slab_mass_nodes"] == 9

    shells = [
        element
        for element in project.model.elements.values()
        if element.group == "slab:L1"
    ]
    beams = [
        element
        for element in project.model.elements.values()
        if element.group in {"beam-x", "beam-y"}
    ]
    assert len(shells) == 4
    assert len(beams) == 8

    shell_nodes = {
        tag
        for element in shells
        for tag in element.node_tags()
    }
    beam_nodes = {
        tag
        for element in beams
        for tag in element.node_tags()
    }
    boundary_midpoints = {
        tag
        for tag in shell_nodes
        if (
            project.model.nodes[tag].xyz[2] == pytest.approx(3.0)
            and (
                project.model.nodes[tag].xyz[:2]
                in {
                    (2.5, 0.0),
                    (2.5, 4.0),
                    (0.0, 2.0),
                    (5.0, 2.0),
                }
            )
        )
    }
    assert len(boundary_midpoints) == 4
    assert boundary_midpoints <= beam_nodes

    total_ux_mass = sum(
        project.model.nodes[tag].mass[0]
        for tag in shell_nodes
    )
    assert total_ux_mass == pytest.approx(40.0)


def test_frame_shell_slab_requires_shell_compatible_project_section():
    project = _member_project()
    spec = FrameGridSpec(
        nx=1,
        ny=1,
        nz=1,
        planar_2d=False,
        column_section_tag=1,
        beam_section_tag=1,
        diaphragm_mode="Shell",
        slab_section_tag=1,
    )
    prepare_frame_grid(project, spec)
    with pytest.raises(ValueError, match="not shell-compatible"):
        generate_frame_project(project, spec)


def test_main_window_frame_wizard_reports_explicit_shell_slab_generation():
    source = inspect.getsource(MainWindow._generate_frame_grid)
    assert '"slab_floors"' in source
    assert '"slab_elements"' in source
    assert "shell slab floor(s)" in source


def test_frame_shell_slab_mesh_guard_blocks_oversized_generation():
    spec = FrameGridSpec(
        nx=10,
        ny=10,
        nz=3,
        planar_2d=False,
        create_beams_x=True,
        create_beams_y=True,
        diaphragm_mode="Shell",
        slab_section_tag=95,
        slab_divisions_x=20,
        slab_divisions_y=20,
    )
    with pytest.raises(ValueError, match="50,000"):
        validate_frame_grid_spec(spec)


def test_frame_shell_asdshell_corotational_option_reaches_export():
    project = _slab_project()
    spec = FrameGridSpec(
        nx=1,
        ny=1,
        nz=1,
        dx=5.0,
        dy=4.0,
        dz=3.0,
        planar_2d=False,
        create_columns=True,
        create_beams_x=True,
        create_beams_y=True,
        column_section_tag=1,
        beam_section_tag=1,
        diaphragm_mode="Shell",
        diaphragm_levels=(1,),
        slab_section_tag=95,
        slab_element_type="ASDShellQ4",
        slab_divisions_x=1,
        slab_divisions_y=1,
        slab_corotational=True,
    )
    prepare_frame_grid(project, spec)
    generate_frame_project(project, spec)
    source = to_openseespy(
        project.model,
        materials=project.materials,
        sections=project.sections,
        transformations=project.transformations,
        constraints=project.constraints,
        connections=project.connections,
        units=project.units,
        nd_materials=project.nd_materials,
    )
    assert "ops.element('ASDShellQ4'" in source
    assert "'-corotational'" in source


def _foundation_project() -> ProjectDatabase:
    project = _member_project()
    for tag, stiffness in (
        (61, 2.0e8),
        (62, 3.0e8),
        (63, 4.0e7),
        (64, 2.5e8),
        (65, 3.5e8),
        (66, 5.0e7),
    ):
        project.add_material(
            MaterialData(
                tag=tag,
                name=f"Foundation elastic {tag}",
                material_type="Elastic",
                parameters={"E": stiffness},
                source={
                    "response_quantity": "force_deformation",
                    "parameter_dimensions": {"E": "stiffness"},
                },
            )
        )
    return project


def test_frame_wizard_foundation_page_maps_planar_active_dofs():
    wizard = FrameWizard(_foundation_project())
    try:
        assert wizard.foundation_mode.currentData() == "Direct"
        wizard.foundation_mode.setCurrentIndex(
            wizard.foundation_mode.findData("Springs")
        )
        for dof, tag in ((1, 61), (3, 62), (5, 63)):
            combo = wizard.foundation_materials[dof - 1]
            combo.setCurrentIndex(combo.findData(tag))
        _APP.processEvents()

        spec = wizard.spec()
        assert spec.foundation_mode == "Springs"
        assert spec.foundation_material_tags == (61, 0, 62, 0, 63, 0)
        assert frame_foundation_count(spec) == 4
        assert not wizard.base_support.isEnabled()
        assert wizard.foundation_materials[0].isEnabled()
        assert not wizard.foundation_materials[1].isEnabled()
        assert wizard.foundation_materials[2].isEnabled()
        assert not wizard.foundation_materials[3].isEnabled()
        assert wizard.foundation_materials[4].isEnabled()
        assert not wizard.foundation_materials[5].isEnabled()
        assert "UX, UZ, RY" in wizard.foundation_summary.text()
        assert "Foundation definition ready" in (
            wizard.foundation_validation_status.text()
        )
        assert wizard.foundation_scroll.widgetResizable()
    finally:
        wizard.close()
        wizard.deleteLater()
        _APP.processEvents()


def test_frame_foundation_spring_mode_requires_active_material():
    spec = FrameGridSpec(
        nx=1,
        nz=1,
        planar_2d=True,
        foundation_mode="Springs",
    )
    with pytest.raises(ValueError, match="at least one active"):
        validate_frame_grid_spec(spec)


def test_frame_foundation_springs_reject_native_2d_joint_core_backend():
    spec = FrameGridSpec(
        nx=1,
        nz=1,
        planar_2d=True,
        joint_model="Joint2D",
        joint_material_tag=61,
        joint_interface_material_tags=(0, 0, 0, 0),
        foundation_mode="Springs",
        foundation_material_tags=(61, 0, 62, 0, 63, 0),
    )
    with pytest.raises(ValueError, match="standard 3D/6DOF"):
        validate_frame_grid_spec(spec)


def test_generate_planar_foundation_springs_create_ground_nodes_and_zero_length():
    project = _foundation_project()
    spec = FrameGridSpec(
        nx=1,
        ny=1,
        nz=1,
        dx=5.0,
        dz=3.5,
        planar_2d=True,
        create_columns=True,
        create_beams_x=True,
        create_beams_y=False,
        column_section_tag=1,
        beam_section_tag=1,
        foundation_mode="Springs",
        foundation_material_tags=(61, 0, 62, 0, 63, 0),
    )
    prepare_frame_grid(project, spec)
    result = generate_frame_project(project, spec)

    assert result["foundation_connections"] == 2
    assert result["foundation_ground_nodes"] == 2
    assert result["foundation_constraints"] == 0
    assert frame_foundation_count(spec) == 2

    foundation = [
        connection
        for connection in project.connections.values()
        if connection.name.startswith("Foundation spring")
    ]
    assert len(foundation) == 2
    assert all(
        connection.materials_by_dof == {1: 61, 3: 62, 5: 63}
        for connection in foundation
    )
    assert all(connection.generated_ground_node is not None for connection in foundation)

    base_tags = [1, 2]
    assert all(
        project.model.nodes[tag].fixity == (0, 1, 0, 1, 0, 1)
        for tag in base_tags
    )
    ground_tags = [
        int(connection.generated_ground_node)
        for connection in foundation
    ]
    assert all(
        project.model.nodes[tag].fixity == (1, 1, 1, 1, 1, 1)
        for tag in ground_tags
    )


def test_generate_3d_foundation_springs_rigidly_tie_unsprung_dofs():
    project = _foundation_project()
    spec = FrameGridSpec(
        nx=1,
        ny=1,
        nz=1,
        dx=5.0,
        dy=4.0,
        dz=3.0,
        planar_2d=False,
        create_columns=True,
        create_beams_x=True,
        create_beams_y=True,
        column_section_tag=1,
        beam_section_tag=1,
        foundation_mode="Springs",
        foundation_material_tags=(61, 0, 62, 0, 0, 0),
    )
    prepare_frame_grid(project, spec)
    result = generate_frame_project(project, spec)

    assert result["foundation_connections"] == 4
    assert result["foundation_ground_nodes"] == 4
    assert result["foundation_constraints"] == 4

    rigid_transfers = [
        constraint
        for constraint in project.constraints.values()
        if constraint.name.startswith("Foundation rigid transfer")
    ]
    assert len(rigid_transfers) == 4
    assert all(
        constraint.dofs == (2, 4, 5, 6)
        for constraint in rigid_transfers
    )

    foundation = [
        connection
        for connection in project.connections.values()
        if connection.name.startswith("Foundation spring")
    ]
    assert all(
        connection.materials_by_dof == {1: 61, 3: 62}
        for connection in foundation
    )


def test_frame_foundation_generator_rejects_missing_project_material():
    project = _member_project()
    spec = FrameGridSpec(
        nx=1,
        nz=1,
        planar_2d=True,
        column_section_tag=1,
        beam_section_tag=1,
        foundation_mode="Springs",
        foundation_material_tags=(999, 0, 0, 0, 0, 0),
    )
    prepare_frame_grid(project, spec)
    with pytest.raises(ValueError, match="do not exist"):
        generate_frame_project(project, spec)


def test_main_window_frame_wizard_reports_foundation_springs():
    source = inspect.getsource(MainWindow._generate_frame_grid)
    assert '"foundation_connections"' in source
    assert "foundation spring connection(s)" in source


def test_frame_wizard_foundation_per_base_profiles_flow_to_spec():
    wizard = FrameWizard(_foundation_project())
    try:
        wizard.foundation_mode.setCurrentIndex(
            wizard.foundation_mode.findData("Springs")
        )
        wizard.foundation_assignment_mode.setCurrentIndex(
            wizard.foundation_assignment_mode.findData("PerBase")
        )

        # Profile A = isolated footing equivalent.
        for dof, tag in ((1, 61), (3, 62), (5, 63)):
            combo = wizard.foundation_profile_materials[0][dof - 1]
            combo.setCurrentIndex(combo.findData(tag))

        # Profile B = pile-group equivalent.
        for dof, tag in ((1, 64), (3, 65), (5, 66)):
            combo = wizard.foundation_profile_materials[1][dof - 1]
            combo.setCurrentIndex(combo.findData(tag))

        # Use A/B alternately across the default four planar bases.
        for row, profile_index in enumerate((0, 1, 0, 1)):
            combo = wizard.foundation_base_table.cellWidget(row, 3)
            assert isinstance(combo, QComboBox)
            combo.setCurrentIndex(combo.findData(profile_index))

        _APP.processEvents()
        spec = wizard.spec()

        assert spec.foundation_assignment_mode == "PerBase"
        assert spec.foundation_profile_material_tags[0] == (
            61, 0, 62, 0, 63, 0
        )
        assert spec.foundation_profile_material_tags[1] == (
            64, 0, 65, 0, 66, 0
        )
        assert spec.foundation_base_profile_indices == (0, 1, 0, 1)
        assert frame_foundation_profile_assignments(spec) == (0, 1, 0, 1)
        assert frame_foundation_profiles(spec)[1] == (
            64, 0, 65, 0, 66, 0
        )
        assert "Profile A: 2 base(s)" in wizard.foundation_summary.text()
        assert "Profile B: 2 base(s)" in wizard.foundation_summary.text()
        assert wizard.preview.foundation_base_profiles == (0, 1, 0, 1)
    finally:
        wizard.close()
        wizard.deleteLater()
        _APP.processEvents()


def test_frame_foundation_per_base_assignment_count_must_match_bases():
    spec = FrameGridSpec(
        nx=2,
        nz=1,
        planar_2d=True,
        foundation_mode="Springs",
        foundation_assignment_mode="PerBase",
        foundation_profile_material_tags=(
            (61, 0, 62, 0, 63, 0),
            (64, 0, 65, 0, 66, 0),
        ),
        foundation_base_profile_indices=(0, 1),
    )
    with pytest.raises(ValueError, match="3 column bases"):
        validate_frame_grid_spec(spec)


def test_frame_foundation_per_base_assignment_rejects_missing_profile():
    spec = FrameGridSpec(
        nx=1,
        nz=1,
        planar_2d=True,
        foundation_mode="Springs",
        foundation_assignment_mode="PerBase",
        foundation_profile_material_tags=(
            (61, 0, 62, 0, 63, 0),
        ),
        foundation_base_profile_indices=(0, 1),
    )
    with pytest.raises(ValueError, match="unavailable profile"):
        validate_frame_grid_spec(spec)


def test_generate_per_base_foundation_profiles_map_materials_to_each_base():
    project = _foundation_project()
    spec = FrameGridSpec(
        nx=2,
        ny=1,
        nz=1,
        dx=5.0,
        dz=3.5,
        planar_2d=True,
        create_columns=True,
        create_beams_x=True,
        create_beams_y=False,
        column_section_tag=1,
        beam_section_tag=1,
        foundation_mode="Springs",
        foundation_assignment_mode="PerBase",
        foundation_profile_material_tags=(
            (61, 0, 62, 0, 63, 0),
            (64, 0, 65, 0, 66, 0),
        ),
        foundation_base_profile_indices=(0, 1, 0),
    )
    prepare_frame_grid(project, spec)
    result = generate_frame_project(project, spec)

    assert result["foundation_connections"] == 3
    assert result["foundation_profiles_used"] == 2

    foundation = sorted(
        (
            connection
            for connection in project.connections.values()
            if connection.name.startswith("Foundation ")
        ),
        key=lambda connection: connection.node_j,
    )
    assert len(foundation) == 3
    assert foundation[0].materials_by_dof == {1: 61, 3: 62, 5: 63}
    assert foundation[1].materials_by_dof == {1: 64, 3: 65, 5: 66}
    assert foundation[2].materials_by_dof == {1: 61, 3: 62, 5: 63}
    assert [
        connection.parameters["foundation_profile_label"]
        for connection in foundation
    ] == ["A", "B", "A"]


def test_frame_foundation_uniform_mode_keeps_profile_a_back_compatibility():
    spec = FrameGridSpec(
        nx=2,
        nz=1,
        planar_2d=True,
        foundation_mode="Springs",
        foundation_material_tags=(61, 0, 62, 0, 63, 0),
    )
    assert frame_foundation_profiles(spec) == (
        (61, 0, 62, 0, 63, 0),
    )
    assert frame_foundation_profile_assignments(spec) == (0, 0, 0)


def test_frame_foundation_profile_tabs_have_equivalent_preset_names():
    wizard = FrameWizard(_foundation_project())
    try:
        labels = [
            wizard.foundation_profile_tabs.tabText(index)
            for index in range(wizard.foundation_profile_tabs.count())
        ]
        assert labels == [
            "A · Isolated footing equivalent",
            "B · Pile-group equivalent",
            "C · Custom soil spring group",
        ]
    finally:
        wizard.close()
        wizard.deleteLater()
        _APP.processEvents()


def _brace_project() -> ProjectDatabase:
    project = _member_project()
    project.add_material(
        MaterialData(
            tag=81,
            name="Brace elastic",
            material_type="Elastic",
            parameters={"E": 2.0e11},
            source={
                "response_quantity": "stress_strain",
                "parameter_dimensions": {"E": "stress"},
            },
        )
    )
    project.add_material(
        MaterialData(
            tag=82,
            name="Brace nonlinear steel",
            material_type="Steel01",
            parameters={
                "Fy": 3.5e8,
                "E0": 2.0e11,
                "b": 0.01,
            },
            source={
                "response_quantity": "stress_strain",
                "parameter_dimensions": {
                    "Fy": "stress",
                    "E0": "stress",
                },
            },
        )
    )
    return project


def test_frame_wizard_bracing_page_maps_scope_and_element_settings():
    wizard = FrameWizard(_brace_project())
    try:
        assert wizard.brace_mode.currentData() == "None"
        wizard.brace_mode.setCurrentIndex(
            wizard.brace_mode.findData("Truss")
        )
        wizard.brace_material.setCurrentIndex(
            wizard.brace_material.findData(81)
        )
        wizard.brace_pattern.setCurrentIndex(
            wizard.brace_pattern.findData("X")
        )
        wizard.brace_element_type.setCurrentIndex(
            wizard.brace_element_type.findData("corotTruss")
        )
        wizard.brace_area.setValue(0.012)
        wizard.brace_mass_per_length.setValue(2.5)
        wizard.brace_do_rayleigh.setChecked(True)

        # Default tables select every X bay/storey. Keep only X2 / S2.
        for row in range(wizard.brace_x_table.rowCount()):
            wizard.brace_x_table.item(row, 1).setCheckState(
                Qt.Checked if row == 1 else Qt.Unchecked
            )
        for row in range(wizard.brace_storey_table.rowCount()):
            wizard.brace_storey_table.item(row, 1).setCheckState(
                Qt.Checked if row == 1 else Qt.Unchecked
            )
        _APP.processEvents()

        spec = wizard.spec()
        assert spec.brace_mode == "Truss"
        assert spec.brace_pattern == "X"
        assert spec.brace_element_type == "corotTruss"
        assert spec.brace_material_tag == 81
        assert spec.brace_area == pytest.approx(0.012)
        assert spec.brace_mass_per_length == pytest.approx(2.5)
        assert spec.brace_do_rayleigh
        assert spec.brace_x_bays == (1,)
        assert spec.brace_storeys == (2,)
        assert frame_brace_panel_count(spec) == 1
        assert frame_brace_element_count(spec) == 2
        assert "panels: 1" in wizard.brace_summary.text()
        assert "brace elements: 2" in wizard.brace_summary.text()
        assert wizard.bracing_scroll.widgetResizable()
    finally:
        wizard.close()
        wizard.deleteLater()
        _APP.processEvents()


def test_frame_brace_scope_helpers_repeat_across_exterior_3d_planes():
    spec = FrameGridSpec(
        nx=3,
        ny=2,
        nz=3,
        planar_2d=False,
        brace_mode="Truss",
        brace_material_tag=81,
        brace_x_bays=(0, 2),
        brace_storeys=(1, 3),
        brace_y_plane_scope="Exterior",
    )
    assert frame_brace_x_bays(spec) == (0, 2)
    assert frame_brace_storeys(spec) == (1, 3)
    assert frame_brace_y_grid_lines(spec) == (0, 2)
    assert frame_brace_panel_count(spec) == 8
    assert frame_brace_element_count(spec) == 16


def test_generate_frame_x_bracing_connects_existing_grid_nodes():
    project = _brace_project()
    spec = FrameGridSpec(
        nx=2,
        ny=1,
        nz=2,
        dx=5.0,
        dz=3.5,
        planar_2d=True,
        create_columns=True,
        create_beams_x=True,
        create_beams_y=False,
        column_section_tag=1,
        beam_section_tag=1,
        brace_mode="Truss",
        brace_pattern="X",
        brace_element_type="truss",
        brace_material_tag=81,
        brace_area=0.01,
        brace_x_bays=(0,),
        brace_storeys=(1,),
    )
    prepare_frame_grid(project, spec)
    result = generate_frame_project(project, spec)

    assert result["brace_panels"] == 1
    assert result["brace_elements"] == 2
    assert result["brace_midpoint_nodes"] == 0
    assert result["brace_member_splits"] == 0

    braces = [
        element
        for element in project.model.elements.values()
        if element.group.startswith("brace-x:")
    ]
    assert len(braces) == 2
    assert all(element.element_type == "truss" for element in braces)
    assert all(element.truss_material_tag == 81 for element in braces)
    assert all(element.truss_area == pytest.approx(0.01) for element in braces)


def test_generate_frame_upper_chevron_splits_beam_conformingly():
    project = _brace_project()
    spec = FrameGridSpec(
        nx=1,
        ny=1,
        nz=1,
        dx=6.0,
        dz=4.0,
        planar_2d=True,
        create_columns=True,
        create_beams_x=True,
        create_beams_y=False,
        column_section_tag=1,
        beam_section_tag=1,
        brace_mode="Truss",
        brace_pattern="VUpper",
        brace_material_tag=81,
        brace_area=0.01,
    )
    prepare_frame_grid(project, spec)
    result = generate_frame_project(project, spec)

    assert result["brace_panels"] == 1
    assert result["brace_elements"] == 2
    assert result["brace_midpoint_nodes"] == 1
    assert result["brace_member_splits"] == 1

    midpoint = [
        (tag, node)
        for tag, node in project.model.nodes.items()
        if node.xyz == pytest.approx((3.0, 0.0, 4.0))
    ]
    assert len(midpoint) == 1
    midpoint_tag = midpoint[0][0]

    beam_segments = [
        element
        for element in project.model.elements.values()
        if element.group == "beam-2d"
    ]
    assert len(beam_segments) == 2
    assert sum(midpoint_tag in element.node_tags() for element in beam_segments) == 2

    braces = [
        element
        for element in project.model.elements.values()
        if element.group.startswith("brace-x:")
    ]
    assert len(braces) == 2
    assert all(midpoint_tag in element.node_tags() for element in braces)


def test_generate_frame_k_bracing_splits_left_column_conformingly():
    project = _brace_project()
    spec = FrameGridSpec(
        nx=1,
        ny=1,
        nz=1,
        dx=6.0,
        dz=4.0,
        planar_2d=True,
        create_columns=True,
        create_beams_x=True,
        create_beams_y=False,
        column_section_tag=1,
        beam_section_tag=1,
        brace_mode="Truss",
        brace_pattern="KLeft",
        brace_material_tag=81,
        brace_area=0.01,
    )
    prepare_frame_grid(project, spec)
    result = generate_frame_project(project, spec)

    assert result["brace_elements"] == 2
    assert result["brace_midpoint_nodes"] == 1
    assert result["brace_member_splits"] == 1

    midpoint_tags = [
        tag
        for tag, node in project.model.nodes.items()
        if node.xyz == pytest.approx((0.0, 0.0, 2.0))
    ]
    assert len(midpoint_tags) == 1
    midpoint_tag = midpoint_tags[0]

    left_column_segments = [
        element
        for element in project.model.elements.values()
        if (
            element.group == "column-2d"
            and midpoint_tag in element.node_tags()
        )
    ]
    assert len(left_column_segments) == 2


def test_frame_lower_chevron_excludes_first_storey():
    bad = FrameGridSpec(
        nx=1,
        nz=2,
        planar_2d=True,
        brace_mode="Truss",
        brace_pattern="VLower",
        brace_material_tag=81,
        brace_storeys=(1, 2),
    )
    with pytest.raises(ValueError, match="cannot use storey 1"):
        validate_frame_grid_spec(bad)

    good = FrameGridSpec(
        nx=1,
        nz=2,
        planar_2d=True,
        brace_mode="Truss",
        brace_pattern="VLower",
        brace_material_tag=81,
        brace_storeys=(2,),
    )
    validate_frame_grid_spec(good)


def test_frame_bracing_rejects_macro_joint_core_and_missing_material():
    macro = FrameGridSpec(
        nx=1,
        nz=1,
        planar_2d=True,
        joint_model="Joint2D",
        joint_material_tag=9,
        brace_mode="Truss",
        brace_material_tag=81,
    )
    with pytest.raises(ValueError, match="macro-joint"):
        validate_frame_grid_spec(macro)

    project = _member_project()
    spec = FrameGridSpec(
        nx=1,
        nz=1,
        planar_2d=True,
        column_section_tag=1,
        beam_section_tag=1,
        brace_mode="Truss",
        brace_material_tag=999,
    )
    prepare_frame_grid(project, spec)
    with pytest.raises(ValueError, match="does not exist"):
        generate_frame_project(project, spec)


def test_main_window_frame_wizard_reports_bracing_generation():
    source = inspect.getsource(MainWindow._generate_frame_grid)
    assert '"brace_panels"' in source
    assert '"brace_elements"' in source
    assert "braced panel(s)" in source


def test_frame_brace_yz_scope_helpers_and_counts():
    spec = FrameGridSpec(
        nx=2,
        ny=3,
        nz=2,
        planar_2d=False,
        create_beams_x=True,
        create_beams_y=True,
        brace_mode="Truss",
        brace_plane_mode="Y",
        brace_material_tag=81,
        brace_y_bays=(0, 2),
        brace_storeys=(1, 2),
        brace_x_plane_scope="Exterior",
    )
    assert frame_brace_y_bays(spec) == (0, 2)
    assert frame_brace_x_grid_lines(spec) == (0, 2)
    assert frame_brace_panel_count(spec) == 8
    assert frame_brace_element_count(spec) == 16
    assert all(panel[0] == "Y" for panel in frame_brace_panels(spec))


def test_generate_frame_yz_bracing_uses_beam_y_plane_nodes():
    project = _brace_project()
    spec = FrameGridSpec(
        nx=1,
        ny=1,
        nz=1,
        dx=5.0,
        dy=4.0,
        dz=3.5,
        planar_2d=False,
        create_columns=True,
        create_beams_x=True,
        create_beams_y=True,
        column_section_tag=1,
        beam_section_tag=1,
        brace_mode="Truss",
        brace_plane_mode="Y",
        brace_pattern="X",
        brace_material_tag=81,
        brace_area=0.01,
        brace_y_bays=(0,),
        brace_storeys=(1,),
        brace_x_plane_scope="XMin",
    )
    prepare_frame_grid(project, spec)
    result = generate_frame_project(project, spec)

    assert result["brace_panels"] == 1
    assert result["brace_yz_panels"] == 1
    assert result["brace_xz_panels"] == 0
    assert result["brace_elements"] == 2
    braces = [
        element
        for element in project.model.elements.values()
        if element.group.startswith("brace-y:")
    ]
    assert len(braces) == 2
    assert all(
        project.model.nodes[tag].xyz[0] == pytest.approx(0.0)
        for element in braces
        for tag in element.node_tags()
    )


def test_frame_mixed_panel_overrides_change_pattern_and_can_disable_panel():
    spec = FrameGridSpec(
        nx=1,
        ny=1,
        nz=1,
        planar_2d=False,
        create_beams_x=True,
        create_beams_y=True,
        brace_mode="Truss",
        brace_plane_mode="Both",
        brace_pattern="X",
        brace_material_tag=81,
        brace_x_bays=(0,),
        brace_y_bays=(0,),
        brace_storeys=(1,),
        brace_y_plane_scope="YMin",
        brace_x_plane_scope="XMin",
        brace_panel_patterns=(
            ("X", 0, 0, 1, "DiagonalForward"),
            ("Y", 0, 0, 1, "None"),
        ),
    )
    panels = frame_brace_panels(spec)
    assert panels == (("X", 0, 0, 1, "DiagonalForward"),)
    assert frame_brace_panel_count(spec) == 1
    assert frame_brace_element_count(spec) == 1


def test_generate_mixed_bracing_supports_kright_on_yz_panel():
    project = _brace_project()
    spec = FrameGridSpec(
        nx=1,
        ny=1,
        nz=1,
        dx=5.0,
        dy=4.0,
        dz=4.0,
        planar_2d=False,
        create_columns=True,
        create_beams_x=True,
        create_beams_y=True,
        column_section_tag=1,
        beam_section_tag=1,
        brace_mode="Truss",
        brace_plane_mode="Both",
        brace_pattern="X",
        brace_material_tag=81,
        brace_area=0.01,
        brace_x_bays=(0,),
        brace_y_bays=(0,),
        brace_storeys=(1,),
        brace_y_plane_scope="YMin",
        brace_x_plane_scope="XMin",
        brace_panel_patterns=(
            ("X", 0, 0, 1, "DiagonalForward"),
            ("Y", 0, 0, 1, "KRight"),
        ),
    )
    prepare_frame_grid(project, spec)
    result = generate_frame_project(project, spec)

    assert result["brace_panels"] == 2
    assert result["brace_elements"] == 3
    assert result["brace_xz_panels"] == 1
    assert result["brace_yz_panels"] == 1
    assert result["brace_midpoint_nodes"] == 1
    assert result["brace_member_splits"] == 1

    midpoint_tags = [
        tag
        for tag, node in project.model.nodes.items()
        if node.xyz == pytest.approx((0.0, 4.0, 2.0))
    ]
    assert len(midpoint_tags) == 1
    midpoint_tag = midpoint_tags[0]
    brace_y = [
        element
        for element in project.model.elements.values()
        if element.group.startswith("brace-y:")
    ]
    assert len(brace_y) == 2
    assert all(midpoint_tag in element.node_tags() for element in brace_y)


def test_frame_wizard_mixed_panel_matrix_flows_to_spec():
    wizard = FrameWizard(_brace_project())
    try:
        wizard.dimension.setCurrentIndex(
            wizard.dimension.findData("3D")
        )
        wizard.brace_mode.setCurrentIndex(
            wizard.brace_mode.findData("Truss")
        )
        wizard.brace_material.setCurrentIndex(
            wizard.brace_material.findData(81)
        )
        wizard.brace_plane_mode.setCurrentIndex(
            wizard.brace_plane_mode.findData("Both")
        )
        wizard.brace_y_plane_scope.setCurrentIndex(
            wizard.brace_y_plane_scope.findData("YMin")
        )
        wizard.brace_x_plane_scope.setCurrentIndex(
            wizard.brace_x_plane_scope.findData("XMin")
        )

        for row in range(wizard.brace_x_table.rowCount()):
            wizard.brace_x_table.item(row, 1).setCheckState(
                Qt.Checked if row == 0 else Qt.Unchecked
            )
        for row in range(wizard.brace_y_table.rowCount()):
            wizard.brace_y_table.item(row, 1).setCheckState(
                Qt.Checked if row == 0 else Qt.Unchecked
            )
        for row in range(wizard.brace_storey_table.rowCount()):
            wizard.brace_storey_table.item(row, 1).setCheckState(
                Qt.Checked if row == 0 else Qt.Unchecked
            )
        _APP.processEvents()

        wizard._refresh_brace_panel_table()
        assert wizard.brace_panel_table.rowCount() == 2

        first = wizard.brace_panel_table.cellWidget(0, 4)
        second = wizard.brace_panel_table.cellWidget(1, 4)
        assert isinstance(first, QComboBox)
        assert isinstance(second, QComboBox)
        first.setCurrentIndex(first.findData("DiagonalForward"))
        second.setCurrentIndex(second.findData("KRight"))
        _APP.processEvents()

        spec = wizard.spec()
        assert spec.brace_plane_mode == "Both"
        assert len(spec.brace_panel_patterns) == 2
        assert {entry[-1] for entry in spec.brace_panel_patterns} == {
            "DiagonalForward",
            "KRight",
        }
        assert frame_brace_panel_count(spec) == 2
        assert frame_brace_element_count(spec) == 3
        assert "X-Z 1, Y-Z 1" in wizard.brace_summary.text()
    finally:
        wizard.close()
        wizard.deleteLater()
        _APP.processEvents()


def test_frame_wizard_brb_ready_requires_nonlinear_material_and_corottruss():
    wizard = FrameWizard(_brace_project())
    try:
        wizard.brace_mode.setCurrentIndex(
            wizard.brace_mode.findData("Truss")
        )
        wizard.brace_material.setCurrentIndex(
            wizard.brace_material.findData(81)
        )
        wizard.brace_response_preset.setCurrentIndex(
            wizard.brace_response_preset.findData("BRBReady")
        )
        _APP.processEvents()

        assert wizard.brace_element_type.currentData() == "corotTruss"
        error = wizard._brace_validation_error()
        assert "calibrated nonlinear" in error

        wizard.brace_material.setCurrentIndex(
            wizard.brace_material.findData(82)
        )
        _APP.processEvents()
        assert wizard._brace_validation_error() == ""
        spec = wizard.spec()
        assert spec.brace_response_preset == "BRBReady"
        assert spec.brace_material_tag == 82
    finally:
        wizard.close()
        wizard.deleteLater()
        _APP.processEvents()


def test_frame_brace_panel_override_validation_rejects_duplicates():
    spec = FrameGridSpec(
        nx=1,
        ny=1,
        nz=1,
        planar_2d=False,
        create_beams_x=True,
        create_beams_y=True,
        brace_mode="Truss",
        brace_material_tag=81,
        brace_panel_patterns=(
            ("X", 0, 0, 1, "X"),
            ("X", 0, 0, 1, "KRight"),
        ),
    )
    with pytest.raises(ValueError, match="duplicate panel keys"):
        validate_frame_grid_spec(spec)


def test_frame_wizard_load_page_maps_static_udl_and_storey_scope():
    wizard = FrameWizard(_member_project())
    try:
        wizard.load_mode.setCurrentIndex(
            wizard.load_mode.findData("Static")
        )
        wizard.load_beam_udl.setChecked(True)
        wizard.load_beam_scope.setCurrentIndex(
            wizard.load_beam_scope.findData("X")
        )
        wizard.load_beam_udl_coordinate.setCurrentIndex(
            wizard.load_beam_udl_coordinate.findData("global")
        )
        wizard.load_udl_x.setValue(0.0)
        wizard.load_udl_y.setValue(0.0)
        wizard.load_udl_z.setValue(-12.5)

        for row in range(wizard.load_storey_table.rowCount()):
            wizard.load_storey_table.item(row, 1).setCheckState(
                Qt.Checked if row == 1 else Qt.Unchecked
            )
        _APP.processEvents()

        spec = wizard.spec()
        assert spec.load_mode == "Static"
        assert not spec.load_self_weight
        assert spec.load_beam_udl
        assert spec.load_beam_scope == "X"
        assert spec.load_beam_udl_coordinate_system == "global"
        assert spec.load_beam_udl_vector == pytest.approx(
            (0.0, 0.0, -12.5)
        )
        assert spec.load_storeys == (2,)
        assert frame_load_storeys(spec) == (2,)
        assert "Beam UDL" in wizard.load_summary.text()
        assert "storeys 2" in wizard.load_summary.text()
        assert wizard.loads_scroll.widgetResizable()
        assert "Load definition ready" in wizard.load_validation_status.text()
    finally:
        wizard.close()
        wizard.deleteLater()
        _APP.processEvents()


def test_frame_wizard_load_page_planar_forces_x_beam_scope():
    wizard = FrameWizard(_member_project())
    try:
        wizard.load_mode.setCurrentIndex(
            wizard.load_mode.findData("Static")
        )
        wizard.load_beam_udl.setChecked(True)
        _APP.processEvents()
        assert wizard.dimension.currentData() == "2D"
        assert wizard.load_beam_scope.currentData() == "X"
        assert not wizard.load_beam_scope.isEnabled()
    finally:
        wizard.close()
        wizard.deleteLater()
        _APP.processEvents()


def test_frame_static_load_validation_rejects_zero_udl():
    spec = FrameGridSpec(
        nx=1,
        nz=1,
        planar_2d=True,
        load_mode="Static",
        load_beam_udl=True,
        load_beam_scope="X",
        load_beam_udl_vector=(0.0, 0.0, 0.0),
    )
    with pytest.raises(ValueError, match="cannot be zero"):
        validate_frame_grid_spec(spec)


def test_frame_static_load_validation_rejects_macro_joint_core():
    spec = FrameGridSpec(
        nx=1,
        nz=1,
        planar_2d=True,
        joint_model="Joint2D",
        joint_material_tag=9,
        load_mode="Static",
        load_beam_udl=True,
        load_beam_scope="X",
        load_beam_udl_vector=(0.0, 0.0, -1.0),
    )
    with pytest.raises(ValueError, match="automatic loads"):
        validate_frame_grid_spec(spec)


def test_generate_frame_udl_targets_final_chevron_split_beam_segments():
    project = _brace_project()
    spec = FrameGridSpec(
        nx=1,
        ny=1,
        nz=1,
        dx=6.0,
        dz=4.0,
        planar_2d=True,
        create_columns=True,
        create_beams_x=True,
        create_beams_y=False,
        column_section_tag=1,
        beam_section_tag=1,
        brace_mode="Truss",
        brace_pattern="VUpper",
        brace_material_tag=81,
        brace_area=0.01,
        load_mode="Static",
        load_beam_udl=True,
        load_beam_scope="X",
        load_storeys=(1,),
        load_beam_udl_vector=(0.0, 0.0, -15.0),
        load_beam_udl_coordinate_system="global",
    )
    prepare_frame_grid(project, spec)
    result = generate_frame_project(project, spec)

    assert result["brace_member_splits"] == 1
    assert result["beam_udl_loads"] == 2
    beam_segments = [
        element
        for element in project.model.elements.values()
        if element.group == "beam-2d"
    ]
    assert len(beam_segments) == 2
    load_targets = {
        load.element_tag
        for load in project.element_loads.values()
        if load.load_type == "Uniform"
    }
    assert load_targets == {element.tag for element in beam_segments}
    assert len(project.time_series) == 1
    assert len(project.load_patterns) == 1


def test_generate_frame_self_weight_uses_density_override_after_member_split():
    project = _brace_project()
    spec = FrameGridSpec(
        nx=1,
        ny=1,
        nz=1,
        dx=6.0,
        dz=4.0,
        planar_2d=True,
        create_columns=True,
        create_beams_x=True,
        create_beams_y=False,
        column_section_tag=1,
        beam_section_tag=1,
        brace_mode="Truss",
        brace_pattern="KLeft",
        brace_material_tag=81,
        brace_area=0.01,
        load_mode="Static",
        load_self_weight=True,
        load_self_weight_density=7850.0,
    )
    prepare_frame_grid(project, spec)
    result = generate_frame_project(project, spec)

    # K bracing splits one column: 3 column segments + 1 beam.
    assert result["brace_member_splits"] == 1
    assert result["self_weight_loads"] == 4
    self_weight = [
        load
        for load in project.element_loads.values()
        if load.load_type == "SelfWeight"
    ]
    assert len(self_weight) == 4
    assert all(
        load.density_override == pytest.approx(7850.0)
        for load in self_weight
    )


def test_frame_wizard_self_weight_without_density_reports_section_problem():
    wizard = FrameWizard(_member_project())
    try:
        wizard.column_section.setCurrentIndex(
            wizard.column_section.findData(1)
        )
        wizard.beam_section.setCurrentIndex(
            wizard.beam_section.findData(1)
        )
        wizard.load_mode.setCurrentIndex(
            wizard.load_mode.findData("Static")
        )
        wizard.load_self_weight.setChecked(True)
        wizard.load_self_weight_density.setValue(0.0)
        _APP.processEvents()
        assert "density" in wizard._load_validation_error().lower()
    finally:
        wizard.close()
        wizard.deleteLater()
        _APP.processEvents()


def test_main_window_frame_wizard_reports_automatic_loads():
    source = inspect.getsource(MainWindow._generate_frame_grid)
    assert '"self_weight_loads"' in source
    assert '"beam_udl_loads"' in source
    assert '"floor_area_loads"' in source
    assert '"mass_sources"' in source
    assert '"generated_nodal_mass"' in source
    assert '"modal_analyses"' in source
    assert '"modal_results"' in source
    assert "beam UDL(s)" in source
    assert "floor-area beam load(s)" in source
    assert "seismic Mass Source" in source
    assert "Modal analysis" in source


def test_frame_floor_area_load_distributes_by_tributary_width():
    project = _member_project()
    spec = FrameGridSpec(
        nx=1,
        ny=2,
        nz=1,
        dx=6.0,
        dy=4.0,
        y_bay_widths=(4.0, 6.0),
        dz=3.5,
        planar_2d=False,
        create_columns=True,
        create_beams_x=True,
        create_beams_y=False,
        column_section_tag=1,
        beam_section_tag=1,
        load_mode="Static",
        load_floor_area=True,
        load_floor_area_pressure=5.0,
        load_floor_area_direction="X",
        load_storeys=(1,),
    )
    prepare_frame_grid(project, spec)
    result = generate_frame_project(project, spec)

    assert result["floor_area_loads"] == 3
    floor_loads = [
        load
        for load in project.element_loads.values()
        if load.name.startswith("Frame floor area load")
    ]
    assert len(floor_loads) == 3
    assert sorted(-float(load.wz) for load in floor_loads) == pytest.approx(
        [10.0, 15.0, 25.0]
    )

    total = 0.0
    for load in floor_loads:
        element = project.model.elements[int(load.element_tag)]
        ni = project.model.nodes[int(element.i)]
        nj = project.model.nodes[int(element.j)]
        length = math.dist(ni.xyz, nj.xyz)
        total += -float(load.wz) * length

    # 6 m x (4 + 6) m floor at 5 force/area.
    assert total == pytest.approx(300.0)


def test_frame_floor_area_load_validation_requires_3d_and_positive_pressure():
    planar = FrameGridSpec(
        nx=1,
        ny=1,
        nz=1,
        planar_2d=True,
        load_mode="Static",
        load_floor_area=True,
        load_floor_area_pressure=5.0,
        load_floor_area_direction="X",
    )
    with pytest.raises(ValueError, match="requires a 3D"):
        validate_frame_grid_spec(planar)

    zero_pressure = FrameGridSpec(
        nx=1,
        ny=1,
        nz=1,
        planar_2d=False,
        create_beams_x=True,
        load_mode="Static",
        load_floor_area=True,
        load_floor_area_pressure=0.0,
        load_floor_area_direction="X",
    )
    with pytest.raises(ValueError, match="must be positive"):
        validate_frame_grid_spec(zero_pressure)


def test_frame_wizard_floor_area_load_maps_to_spec_and_clears_in_2d():
    wizard = FrameWizard(_member_project())
    try:
        wizard.dimension.setCurrentIndex(
            wizard.dimension.findData("3D")
        )
        wizard.load_mode.setCurrentIndex(
            wizard.load_mode.findData("Static")
        )
        wizard.load_floor_area.setChecked(True)
        wizard.load_floor_area_pressure.setValue(4.5)
        wizard.load_floor_area_direction.setCurrentIndex(
            wizard.load_floor_area_direction.findData("Y")
        )
        _APP.processEvents()

        spec = wizard.spec()
        assert spec.load_floor_area
        assert spec.load_floor_area_pressure == pytest.approx(4.5)
        assert spec.load_floor_area_direction == "Y"
        assert "Floor area gravity" in wizard.load_summary.text()
        assert wizard.load_floor_area_group.isEnabled()

        wizard.dimension.setCurrentIndex(
            wizard.dimension.findData("2D")
        )
        _APP.processEvents()
        assert not wizard.load_floor_area.isChecked()
        assert not wizard.load_floor_area_group.isEnabled()
    finally:
        wizard.close()
        wizard.deleteLater()
        _APP.processEvents()


def test_frame_mass_source_converts_generated_floor_gravity_to_nodal_mass():
    project = _member_project()
    spec = FrameGridSpec(
        nx=1,
        ny=1,
        nz=1,
        dx=5.0,
        dy=4.0,
        dz=3.5,
        planar_2d=False,
        create_columns=True,
        create_beams_x=True,
        create_beams_y=True,
        column_section_tag=1,
        beam_section_tag=1,
        load_mode="Static",
        load_floor_area=True,
        load_floor_area_pressure=1000.0,
        load_floor_area_direction="X",
        load_storeys=(1,),
        mass_source_mode="Source",
        mass_include_self=False,
        mass_include_static_loads=True,
        mass_static_load_factor=1.0,
        mass_gravity_axis=3,
        mass_directions=(1, 2),
    )
    prepare_frame_grid(project, spec)
    result = generate_frame_project(project, spec)

    assert result["load_patterns"] == 1
    assert result["load_pattern_tag"] > 0
    assert result["mass_sources"] == 1
    assert result["mass_nodes"] == 4
    expected_total = 5.0 * 4.0 * 1000.0 / 9.80665
    assert result["generated_nodal_mass"] == pytest.approx(expected_total)

    assert len(project.mass_sources) == 1
    source = next(iter(project.mass_sources.values()))
    assert source.include_self_mass is False
    assert source.load_factors == {
        int(result["load_pattern_tag"]): pytest.approx(1.0)
    }
    assert source.gravity_axis == 3
    assert source.directions == (1, 2)

    active = [
        node
        for node in project.model.nodes.values()
        if node.mass[0] > 0.0
    ]
    assert len(active) == 4
    assert all(node.mass[0] == pytest.approx(node.mass[1]) for node in active)
    assert all(node.mass[2] == pytest.approx(0.0) for node in active)
    assert sum(node.mass[0] for node in active) == pytest.approx(expected_total)


def test_frame_mass_source_rejects_explicit_rigid_floor_mass_overwrite():
    spec = FrameGridSpec(
        nx=1,
        ny=1,
        nz=1,
        planar_2d=False,
        diaphragm_mode="Rigid",
        diaphragm_floor_mass=10.0,
        mass_source_mode="Source",
        mass_include_self=True,
        mass_include_static_loads=False,
        mass_directions=(1, 2),
    )
    with pytest.raises(ValueError, match="replaces selected nodal mass"):
        validate_frame_grid_spec(spec)


def test_frame_mass_source_requires_static_pattern_when_selected():
    spec = FrameGridSpec(
        nx=1,
        ny=1,
        nz=1,
        planar_2d=False,
        mass_source_mode="Source",
        mass_include_self=False,
        mass_include_static_loads=True,
        mass_static_load_factor=1.0,
        mass_directions=(1, 2),
    )
    with pytest.raises(ValueError, match="static load generation is disabled"):
        validate_frame_grid_spec(spec)


def test_frame_wizard_mass_page_maps_source_settings():
    wizard = FrameWizard(_member_project())
    try:
        wizard.dimension.setCurrentIndex(
            wizard.dimension.findData("3D")
        )
        wizard.load_mode.setCurrentIndex(
            wizard.load_mode.findData("Static")
        )
        wizard.load_beam_udl.setChecked(True)
        wizard.load_udl_z.setValue(-10.0)

        wizard.mass_source_mode.setCurrentIndex(
            wizard.mass_source_mode.findData("Source")
        )
        wizard.mass_include_self.setChecked(False)
        wizard.mass_include_static.setChecked(True)
        wizard.mass_static_factor.setValue(0.75)
        wizard.mass_gravity_axis.setCurrentIndex(
            wizard.mass_gravity_axis.findData(3)
        )
        wizard.mass_direction_x.setChecked(True)
        wizard.mass_direction_y.setChecked(True)
        wizard.mass_direction_z.setChecked(False)
        _APP.processEvents()

        spec = wizard.spec()
        assert spec.mass_source_mode == "Source"
        assert not spec.mass_include_self
        assert spec.mass_include_static_loads
        assert spec.mass_static_load_factor == pytest.approx(0.75)
        assert spec.mass_gravity_axis == 3
        assert spec.mass_directions == (1, 2)
        assert "static gravity pattern" in wizard.mass_summary.text()
        assert wizard.mass_scroll.widgetResizable()
        assert "Mass definition ready" in wizard.mass_validation_status.text()
    finally:
        wizard.close()
        wizard.deleteLater()
        _APP.processEvents()


def test_frame_wizard_mass_page_planar_keeps_horizontal_x_only():
    wizard = FrameWizard(_member_project())
    try:
        wizard.mass_source_mode.setCurrentIndex(
            wizard.mass_source_mode.findData("Source")
        )
        wizard.mass_include_static.setChecked(False)
        wizard.mass_include_self.setChecked(True)
        wizard.mass_direction_y.setChecked(True)
        wizard.mass_direction_z.setChecked(True)
        wizard._sync_mass_controls()
        _APP.processEvents()

        assert wizard.dimension.currentData() == "2D"
        assert wizard.mass_direction_x.isChecked()
        assert not wizard.mass_direction_y.isChecked()
        assert not wizard.mass_direction_z.isChecked()
        assert wizard.spec().mass_directions == (1,)
    finally:
        wizard.close()
        wizard.deleteLater()
        _APP.processEvents()


def test_frame_modal_preset_uses_generated_seismic_mass():
    project = _member_project()
    spec = FrameGridSpec(
        nx=1,
        ny=1,
        nz=2,
        dx=5.0,
        dy=4.0,
        dz=3.5,
        planar_2d=False,
        create_columns=True,
        create_beams_x=True,
        create_beams_y=True,
        column_section_tag=1,
        beam_section_tag=1,
        load_mode="Static",
        load_floor_area=True,
        load_floor_area_pressure=1000.0,
        load_floor_area_direction="X",
        load_storeys=(1, 2),
        mass_source_mode="Source",
        mass_include_self=False,
        mass_include_static_loads=True,
        mass_static_load_factor=1.0,
        mass_gravity_axis=3,
        mass_directions=(1, 2),
        modal_mode="Modal",
        modal_num_modes=4,
        modal_eigen_solver="-genBandArpack",
    )
    prepare_frame_grid(project, spec)
    result = generate_frame_project(project, spec)

    assert result["mass_sources"] == 1
    assert result["generated_nodal_mass"] > 0.0
    assert result["modal_analyses"] == 1
    assert result["modal_analysis_tag"] > 0
    assert result["modal_results"] == 5

    assert len(project.analyses) == 1
    analysis = project.analyses[int(result["modal_analysis_tag"])]
    assert analysis.analysis_type == "Modal"
    assert analysis.num_modes == 4
    assert analysis.eigen_solver == "-genBandArpack"
    assert project.active_analysis_tag == analysis.tag

    results = project.solution_results_for_analysis(analysis.tag)
    assert len(results) == 5
    assert sum(item.result_type == "ModeShape" for item in results) == 4
    assert sum(item.result_type == "Motion" for item in results) == 1


def test_frame_modal_preset_accepts_member_element_mass_without_mass_source():
    project = _member_project()
    spec = FrameGridSpec(
        nx=1,
        ny=1,
        nz=1,
        dx=5.0,
        dy=4.0,
        dz=3.5,
        planar_2d=False,
        create_columns=True,
        create_beams_x=True,
        create_beams_y=True,
        column_section_tag=1,
        beam_section_tag=1,
        column_mass_per_length=2.0,
        beam_mass_per_length=1.0,
        mass_source_mode="None",
        modal_mode="Modal",
        modal_num_modes=3,
        modal_eigen_solver="-fullGenLapack",
    )
    prepare_frame_grid(project, spec)
    result = generate_frame_project(project, spec)

    assert result.get("mass_sources", 0) == 0
    assert result["modal_analyses"] == 1
    analysis = project.analyses[int(result["modal_analysis_tag"])]
    assert analysis.num_modes == 3
    assert analysis.eigen_solver == "-fullGenLapack"
    assert any(
        element.mass_per_length > 0.0
        for element in project.model.elements.values()
    )


def test_frame_modal_validation_requires_mass_definition():
    spec = FrameGridSpec(
        nx=1,
        ny=1,
        nz=1,
        planar_2d=False,
        modal_mode="Modal",
        modal_num_modes=3,
    )
    with pytest.raises(ValueError, match="needs a mass definition"):
        validate_frame_grid_spec(spec)


def test_frame_modal_validation_rejects_invalid_mode_count_and_solver():
    bad_count = FrameGridSpec(
        nx=1,
        ny=1,
        nz=1,
        planar_2d=False,
        column_mass_per_length=1.0,
        modal_mode="Modal",
        modal_num_modes=0,
    )
    with pytest.raises(ValueError, match="1 to 100 modes"):
        validate_frame_grid_spec(bad_count)

    bad_solver = FrameGridSpec(
        nx=1,
        ny=1,
        nz=1,
        planar_2d=False,
        column_mass_per_length=1.0,
        modal_mode="Modal",
        modal_num_modes=3,
        modal_eigen_solver="-notARealSolver",
    )
    with pytest.raises(ValueError, match="eigen solver"):
        validate_frame_grid_spec(bad_solver)


def test_frame_wizard_modal_controls_map_to_spec_and_summary():
    wizard = FrameWizard(_member_project())
    try:
        wizard.dimension.setCurrentIndex(
            wizard.dimension.findData("3D")
        )
        wizard.column_mass_per_length.setValue(2.0)
        wizard.modal_mode.setCurrentIndex(
            wizard.modal_mode.findData("Modal")
        )
        wizard.modal_num_modes.setValue(8)
        wizard.modal_eigen_solver.setCurrentIndex(
            wizard.modal_eigen_solver.findData("-fullGenLapack")
        )
        _APP.processEvents()

        spec = wizard.spec()
        assert spec.modal_mode == "Modal"
        assert spec.modal_num_modes == 8
        assert spec.modal_eigen_solver == "-fullGenLapack"
        assert wizard.modal_num_modes.isEnabled()
        assert wizard.modal_eigen_solver.isEnabled()
        assert "8 mode(s)" in wizard.mass_summary.text()
        assert "Modal analysis" in wizard.mass_summary.text()
        assert "Mass definition ready" in wizard.mass_validation_status.text()
    finally:
        wizard.close()
        wizard.deleteLater()
        _APP.processEvents()


def test_frame_wizard_final_review_page_is_live_and_ready_for_valid_model():
    wizard = FrameWizard(_member_project())
    try:
        wizard.show()
        _APP.processEvents()
        wizard.setCurrentId(wizard.review_page_id)
        _APP.processEvents()

        assert wizard.currentId() == wizard.review_page_id
        assert wizard.review_scroll.widgetResizable()
        assert wizard.review_preview.objectName() == "frame-wizard-final-preview"
        assert "2D X-Z frame" in wizard.review_geometry.text()
        assert "Members:" in wizard.review_modeling.text()
        assert "Static loads:" in wizard.review_loading.text()
        assert "New model" in wizard.review_impact.text()
        assert "Ready to generate" in wizard.review_validation_status.text()
        assert wizard.button(QWizard.FinishButton).text() == "Generate Model"
        assert wizard.validateCurrentPage()
    finally:
        wizard.close()
        wizard.deleteLater()
        _APP.processEvents()


def test_frame_wizard_final_review_warns_before_replacing_existing_fe_domain():
    project = _member_project()
    project.model.add_node(100, 0.0, 0.0, 0.0)
    project.model.add_node(101, 1.0, 0.0, 0.0)
    project.model.add_element(
        100,
        100,
        101,
        section_tag=1,
    )
    wizard = FrameWizard(project)
    try:
        wizard.show()
        _APP.processEvents()
        wizard.setCurrentId(wizard.review_page_id)
        _APP.processEvents()

        impact = wizard.review_impact.text()
        assert "Replacement mode" in impact
        assert "2 node(s)" in impact
        assert "1 element(s)" in impact
        assert "Material and section libraries are preserved" in impact
    finally:
        wizard.close()
        wizard.deleteLater()
        _APP.processEvents()


def test_frame_wizard_final_review_blocks_generate_for_invalid_definition():
    wizard = FrameWizard(ProjectDatabase())
    try:
        wizard.show()
        _APP.processEvents()
        wizard.setCurrentId(wizard.review_page_id)
        _APP.processEvents()

        assert not wizard.validateCurrentPage()
        assert "Model definition needs attention" in (
            wizard.review_validation_status.text()
        )
        assert not wizard.button(QWizard.FinishButton).isEnabled()
    finally:
        wizard.close()
        wizard.deleteLater()
        _APP.processEvents()


def test_frame_wizard_final_review_updates_3d_system_summary():
    wizard = FrameWizard(_member_project())
    try:
        wizard.dimension.setCurrentIndex(
            wizard.dimension.findData("3D")
        )
        wizard.brace_mode.setCurrentIndex(
            wizard.brace_mode.findData("Truss")
        )
        if wizard.brace_material.count() > 1:
            wizard.brace_material.setCurrentIndex(1)
        wizard.brace_area.setValue(0.01)
        wizard._refresh_brace_scope_tables()
        _APP.processEvents()

        wizard.show()
        wizard.setCurrentId(wizard.review_page_id)
        _APP.processEvents()

        assert "3D frame" in wizard.review_geometry.text()
        assert "Bracing:" in wizard.review_modeling.text()
        assert wizard.review_preview.dimension == "3D"
    finally:
        wizard.close()
        wizard.deleteLater()
        _APP.processEvents()
