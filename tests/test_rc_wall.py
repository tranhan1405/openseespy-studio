from __future__ import annotations

import math
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from openseespy_studio.generator import to_openseespy
from openseespy_studio.project import ProjectDatabase
from openseespy_studio.rc_wall import RCWallSpec, build_rc_wall
from openseespy_studio.ui.rc_wall_wizard import RCWallWizard


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
        assert "7 MEFI rows" in dialog.review.text()
    finally:
        dialog.close()
        dialog.deleteLater()
        _APP.processEvents()
