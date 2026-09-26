from __future__ import annotations

import pytest

from openseespy_studio.generator import material_to_openseespy, to_openseespy
from openseespy_studio.importer import import_openseespy_source
from openseespy_studio.masonry_wall import (
    MasonryWallSpec,
    build_masonry_wall,
)
from openseespy_studio.project import MaterialData, ProjectDatabase
from openseespy_studio.ui.masonry_wall_wizard import MasonryWallWizard
from openseespy_studio.validation import validate_project


def _script(project: ProjectDatabase) -> str:
    return to_openseespy(
        project.model,
        materials=project.materials,
        sections=project.sections,
        transformations=project.transformations,
        constraints=project.constraints,
        connections=project.connections,
        units=project.units,
        nd_materials=project.nd_materials,
    )


def test_masonry_material_exports_native_opensees_command():
    material = MaterialData(
        1,
        "Masonry",
        "Masonry",
        parameters={
            "Fm": -5.0e6,
            "Ft": 0.2e6,
            "Um": -0.002,
            "Uult": -0.01,
            "Ucl": 0.0005,
            "Emo": 2.5e9,
            "L": 1.0,
            "A1": 1.0,
            "A2": 0.2,
            "D1": -0.002,
            "D2": -0.006,
            "Ach": 0.4,
            "Are": 0.3,
            "Ba": 1.75,
            "Bch": 0.2,
            "Gun": 2.0,
            "Gplu": 0.6,
            "Gplr": 1.3,
            "Exp1": 1.75,
            "Exp2": 1.25,
            "IENV": 0,
        },
    )

    command = material_to_openseespy(
        material,
        {"length": "m", "force": "kN", "time": "s"},
    )

    assert command.startswith("ops.uniaxialMaterial('Masonry', 1,")
    assert "-5000" in command
    assert "2.5e+06" in command


def test_equivalent_strut_masonry_builder_creates_crossed_diagonals():
    project = ProjectDatabase()
    spec = MasonryWallSpec(
        width=3.0,
        height=2.8,
        thickness=0.15,
        formulation="EquivalentStrut",
        crossed_struts=True,
        strut_width_ratio=0.1,
        name="Infill",
    )

    result = build_masonry_wall(project, spec)

    assert (project.model.ndm, project.model.ndf) == (2, 3)
    assert len(result.node_tags) == 4
    assert len(result.element_tags) == 2
    assert len(result.material_tags) == 1
    assert all(
        project.model.elements[tag].element_type == "corotTruss"
        for tag in result.element_tags
    )
    assert all(
        project.model.elements[tag].truss_material_tag
        == result.material_tags[0]
        for tag in result.element_tags
    )
    assert project.materials[result.material_tags[0]].material_type == "Masonry"
    assert not [
        issue
        for issue in validate_project(project)
        if issue.severity == "ERROR"
    ]


def test_masonpan12_builder_round_trips_and_exports_all_twelve_nodes():
    project = ProjectDatabase()
    spec = MasonryWallSpec(
        width=3.0,
        height=2.8,
        thickness=0.15,
        formulation="MasonPan12",
        masonpan_w_tot=0.25,
        masonpan_w1=0.5,
        name="Panel",
    )

    result = build_masonry_wall(project, spec)

    assert len(result.node_tags) == 12
    assert len(result.element_tags) == 1
    assert len(result.material_tags) == 2
    element = project.model.elements[result.element_tags[0]]
    assert element.element_type == "MasonPan12"
    assert element.node_tags() == tuple(result.node_tags)
    assert element.special_parameters["mat_1"] == result.material_tags[0]
    assert element.special_parameters["mat_2"] == result.material_tags[1]

    restored = ProjectDatabase.from_dict(project.to_dict())
    restored_element = restored.model.elements[result.element_tags[0]]
    assert restored_element.node_tags() == tuple(result.node_tags)
    assert restored_element.special_parameters == element.special_parameters

    script = _script(project)
    assert "ops.element('MasonPan12'" in script
    for node_tag in result.node_tags:
        assert f"{node_tag}" in script
    assert not [
        issue
        for issue in validate_project(project)
        if issue.severity == "ERROR"
    ]


def test_masonry_wall_wizard_switches_formulation_controls():
    project = ProjectDatabase()
    wizard = MasonryWallWizard(project)
    try:
        assert wizard.formulation.currentData() == "EquivalentStrut"
        assert wizard.strut_width_ratio.isEnabled()
        assert not wizard.masonpan_w_tot.isEnabled()

        wizard.formulation.setCurrentIndex(
            wizard.formulation.findData("MasonPan12")
        )
        assert not wizard.strut_width_ratio.isEnabled()
        assert wizard.masonpan_w_tot.isEnabled()
        assert wizard.masonpan_w1.isEnabled()
        assert wizard.data().formulation == "MasonPan12"
    finally:
        wizard.close()
        wizard.deleteLater()

def test_masonpan12_export_import_round_trip_preserves_topology_and_materials():
    source_project = ProjectDatabase()
    source_result = build_masonry_wall(
        source_project,
        MasonryWallSpec(
            width=3.2,
            height=2.6,
            thickness=0.18,
            formulation="MasonPan12",
            masonpan_w_tot=0.30,
            masonpan_w1=0.45,
            name="Round Trip Panel",
        ),
    )
    source = _script(source_project)

    imported = import_openseespy_source(
        source,
        units=source_project.units,
    ).project

    assert len(imported.model.nodes) == 12
    assert len(imported.model.elements) == 1
    element = next(iter(imported.model.elements.values()))
    assert element.element_type == "MasonPan12"
    assert len(element.node_tags()) == 12
    assert element.node_tags() == tuple(source_result.node_tags)
    assert element.special_parameters["thick"] == pytest.approx(0.18)
    assert element.special_parameters["w_tot"] == pytest.approx(0.30)
    assert element.special_parameters["w_1"] == pytest.approx(0.45)

    masonry_materials = [
        material
        for material in imported.materials.values()
        if material.material_type == "Masonry"
    ]
    assert len(masonry_materials) == 2
    assert all(material.parameters["Fm"] == pytest.approx(-5.0e6) for material in masonry_materials)
    assert all(material.parameters["Emo"] == pytest.approx(2.5e9) for material in masonry_materials)

def test_masonry_material_accepts_legacy_a1_a2_aliases():
    material = MaterialData(
        11,
        "Legacy masonry",
        "Masonry",
        parameters={
            "Fm": -5.0e6,
            "Ft": 0.2e6,
            "Emo": 2.5e9,
            "a1": 0.85,
            "a2": 0.15,
        },
    )
    assert material.parameters["A1"] == pytest.approx(0.85)
    assert material.parameters["A2"] == pytest.approx(0.15)
    assert "a1" not in material.parameters
    assert "a2" not in material.parameters


def test_equivalent_strut_can_reuse_existing_masonry_material():
    project = ProjectDatabase()
    project.add_material(
        MaterialData(7, "Calibrated infill", "Masonry")
    )
    result = build_masonry_wall(
        project,
        MasonryWallSpec(
            formulation="EquivalentStrut",
            material_strategy="UseExisting",
            existing_material_tag=7,
            crossed_struts=True,
            replace_geometry=True,
        ),
    )

    assert result.material_tags == [7]
    assert set(project.materials) == {7}
    assert all(
        project.model.elements[tag].truss_material_tag == 7
        for tag in result.element_tags
    )


def test_masonpan12_can_reuse_distinct_central_and_lateral_materials():
    project = ProjectDatabase()
    project.add_material(MaterialData(7, "Central", "Masonry"))
    project.add_material(MaterialData(8, "Lateral", "Masonry"))

    result = build_masonry_wall(
        project,
        MasonryWallSpec(
            formulation="MasonPan12",
            material_strategy="UseExisting",
            existing_material_tag=7,
            existing_lateral_material_tag=8,
            replace_geometry=True,
        ),
    )

    assert result.material_tags == [7, 8]
    assert set(project.materials) == {7, 8}
    element = project.model.elements[result.element_tags[0]]
    assert element.special_parameters["mat_1"] == 7
    assert element.special_parameters["mat_2"] == 8


def test_masonry_wall_wizard_reuses_project_materials_and_locks_custom_fields():
    project = ProjectDatabase()
    project.add_material(MaterialData(7, "Central", "Masonry"))
    project.add_material(MaterialData(8, "Lateral", "Masonry"))
    wizard = MasonryWallWizard(project)
    try:
        wizard.material_strategy.setCurrentIndex(
            wizard.material_strategy.findData("UseExisting")
        )
        wizard.formulation.setCurrentIndex(
            wizard.formulation.findData("MasonPan12")
        )
        wizard.existing_material.setCurrentIndex(
            wizard.existing_material.findData(7)
        )
        wizard.existing_lateral_material.setCurrentIndex(
            wizard.existing_lateral_material.findData(8)
        )

        assert not wizard.Fm.isEnabled()
        assert wizard.existing_material.isEnabled()
        assert wizard.existing_lateral_material.isEnabled()
        spec = wizard.data()
        assert spec.material_strategy == "UseExisting"
        assert spec.existing_material_tag == 7
        assert spec.existing_lateral_material_tag == 8
        assert wizard._validation_messages() == []
    finally:
        wizard.close()
        wizard.deleteLater()


def test_masonry_wall_rejects_non_masonry_reuse_dependency():
    project = ProjectDatabase()
    project.add_material(
        MaterialData(3, "Elastic spring", "Elastic", parameters={"E": 1.0e6})
    )
    with pytest.raises(ValueError, match="must be Masonry"):
        build_masonry_wall(
            project,
            MasonryWallSpec(
                formulation="EquivalentStrut",
                material_strategy="UseExisting",
                existing_material_tag=3,
                replace_geometry=True,
            ),
        )

def test_custom_masonry_wall_requires_normalized_length_and_area1():
    with pytest.raises(ValueError, match="normalized L=1"):
        validate_masonry_wall_spec(
            MasonryWallSpec(material_strategy="CreateCustom", L=2.0)
        )
    with pytest.raises(ValueError, match="normalized Area1=1"):
        validate_masonry_wall_spec(
            MasonryWallSpec(material_strategy="CreateCustom", a1=0.8)
        )
    with pytest.raises(ValueError, match="Area2"):
        validate_masonry_wall_spec(
            MasonryWallSpec(material_strategy="CreateCustom", a2=1.2)
        )


def test_custom_masonry_material_records_opensees_source_reference():
    project = ProjectDatabase()
    result = build_masonry_wall(
        project,
        MasonryWallSpec(
            formulation="EquivalentStrut",
            material_strategy="CreateCustom",
            replace_geometry=True,
        ),
    )
    material = project.materials[result.material_tags[0]]
    assert material.source["status"] == "user_defined"
    assert material.source["model"] == "Masonry"
    assert "Masonry.cpp" in material.source["reference"]["title"]
    assert material.source["reference"]["url"].endswith(
        "SRC/material/uniaxial/Masonry.cpp"
    )


def test_masonry_wizard_locks_normalized_custom_material_controls():
    wizard = MasonryWallWizard(ProjectDatabase())
    try:
        assert wizard.L.minimum() == pytest.approx(1.0)
        assert wizard.L.maximum() == pytest.approx(1.0)
        assert wizard.a1.minimum() == pytest.approx(1.0)
        assert wizard.a1.maximum() == pytest.approx(1.0)
        assert wizard.a2.maximum() == pytest.approx(1.0)
    finally:
        wizard.close()
        wizard.deleteLater()

