from __future__ import annotations

import inspect
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from openseespy_studio.frame_setup import prepare_frame_grid
from openseespy_studio.generator import (
    FrameGridSpec,
    frame_grid_coordinates,
    frame_joint_connection_count,
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
