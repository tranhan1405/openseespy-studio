from __future__ import annotations

from PySide6.QtWidgets import QApplication

from openseespy_studio.generator import connection_to_openseespy
from openseespy_studio.project import (
    ConnectionData,
    MATERIAL_DEFAULTS,
    MaterialData,
    ProjectDatabase,
    SectionData,
)
from openseespy_studio.ui.connection_dialog import ConnectionDialog


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _materials() -> dict[int, MaterialData]:
    return {
        1: MaterialData(
            1,
            "Elastic",
            "Elastic",
            parameters=MATERIAL_DEFAULTS["Elastic"],
        ),
        2: MaterialData(
            2,
            "Bond",
            "Bond_SP01",
            parameters=MATERIAL_DEFAULTS["Bond_SP01"],
        ),
        3: MaterialData(
            3,
            "Pinching",
            "Pinching4",
            parameters=MATERIAL_DEFAULTS["Pinching4"],
        ),
    }


def test_connection_data_rejects_parallel_orientation_vectors():
    try:
        ConnectionData(
            1,
            "Bad axes",
            "zeroLength",
            1,
            2,
            materials_by_dof={1: 1},
            orient_x=(1.0, 0.0, 0.0),
            orient_y=(2.0, 0.0, 0.0),
        )
    except ValueError as exc:
        assert "cannot be parallel" in str(exc)
    else:
        raise AssertionError("Expected parallel local axes to be rejected")


def test_zero_length_project_validation_requires_coincident_nodes():
    project = ProjectDatabase()
    project.model.add_node(1, 0.0, 0.0, 0.0)
    project.model.add_node(2, 1.0, 0.0, 0.0)
    project.add_material(_materials()[1])

    connection = ConnectionData(
        1,
        "Spring",
        "zeroLength",
        1,
        2,
        materials_by_dof={1: 1},
    )
    try:
        project.add_connection(connection)
    except ValueError as exc:
        assert "must be coincident" in str(exc)
    else:
        raise AssertionError("Expected separated zeroLength nodes to fail")


def test_connection_generator_preserves_dof_material_mapping_order():
    connection = ConnectionData(
        7,
        "Joint",
        "zeroLength",
        10,
        11,
        materials_by_dof={6: 30, 1: 10, 2: 20},
        orient_x=(1.0, 0.0, 0.0),
        orient_y=(0.0, 1.0, 0.0),
        do_rayleigh=True,
    )
    command = connection_to_openseespy(connection)
    assert "'-mat', 10, 20, 30" in command
    assert "'-dir', 1, 2, 6" in command
    assert "'-doRayleigh', 1" in command


def test_builder_default_axial_preset_prefers_macro_slip_material():
    _app()
    dialog = ConnectionDialog(
        _materials(),
        next_tag=1,
        initial_node_i=1,
        initial_node_j=2,
        node_positions={
            1: (0.0, 0.0, 0.0),
            2: (0.0, 0.0, 0.0),
        },
        units={"length": "mm", "force": "N", "time": "s"},
    )
    assert dialog.preset.currentText() == "Axial / translational slip spring"
    assert dialog.dof_checks[0].isChecked()
    assert not dialog.dof_checks[1].isChecked()
    assert dialog.material_combos[0].currentData() in {1, 3}
    spec = dialog.spec()
    assert spec["materials_by_dof"][1] in {1, 3}
    dialog.close()


def test_builder_rotational_hinge_preset_prefers_pinching_material():
    _app()
    dialog = ConnectionDialog(
        _materials(),
        next_tag=1,
        initial_node_i=1,
        initial_node_j=2,
        node_positions={
            1: (0.0, 0.0, 0.0),
            2: (0.0, 0.0, 0.0),
        },
    )
    index = dialog.preset.findText("Rotational hinge RZ")
    dialog.preset.setCurrentIndex(index)
    assert dialog.dof_checks[5].isChecked()
    assert dialog.material_combos[5].currentData() == 3
    assert dialog.spec()["materials_by_dof"] == {6: 3}
    dialog.close()


def test_builder_blocks_separated_zero_length_nodes():
    _app()
    dialog = ConnectionDialog(
        _materials(),
        initial_node_i=1,
        initial_node_j=2,
        node_positions={
            1: (0.0, 0.0, 0.0),
            2: (0.5, 0.0, 0.0),
        },
    )
    try:
        dialog.spec()
    except ValueError as exc:
        assert "requires coincident nodes" in str(exc)
    else:
        raise AssertionError("Expected separated zeroLength pair to fail")
    dialog.close()



def test_builder_rejects_direct_bond_sp01_zero_length_assignment():
    _app()
    dialog = ConnectionDialog(
        _materials(),
        next_tag=1,
        initial_node_i=1,
        initial_node_j=2,
        node_positions={
            1: (0.0, 0.0, 0.0),
            2: (0.0, 0.0, 0.0),
        },
        units={"length": "mm", "force": "N", "time": "s"},
    )
    dialog.preset.setCurrentIndex(0)
    dialog.dof_checks[0].setChecked(True)
    index = dialog.material_combos[0].findData(2)
    dialog.material_combos[0].setCurrentIndex(index)

    try:
        dialog.spec()
    except ValueError as exc:
        assert "zeroLengthSection" in str(exc)
        assert "Bond_SP01" in str(exc)
    else:
        raise AssertionError("Expected direct Bond_SP01 zeroLength use to fail")
    dialog.close()



def _sections() -> dict[int, SectionData]:
    return {
        7: SectionData(
            tag=7,
            name="Fiber Section",
            section_type="Fiber",
            parameters={"GJ": 1.0e6},
        ),
    }


def test_builder_creates_zero_length_section_from_section_assignment():
    _app()
    dialog = ConnectionDialog(
        _materials(),
        sections=_sections(),
        next_tag=10,
        initial_node_i=1,
        initial_node_j=2,
        node_positions={
            1: (0.0, 0.0, 0.0),
            2: (0.0, 0.0, 0.0),
        },
    )
    dialog.connection_type.setCurrentText("zeroLengthSection")
    section_index = dialog.section_combo.findData(7)
    dialog.section_combo.setCurrentIndex(section_index)

    spec = dialog.spec()

    assert spec["connection_type"] == "zeroLengthSection"
    assert spec["section_tag"] == 7
    assert spec["materials_by_dof"] == {}
    assert dialog.tabs.isTabEnabled(dialog.section_tab_index)
    assert not dialog.tabs.isTabEnabled(dialog.dof_tab_index)
    dialog.close()


def test_builder_zero_length_section_requires_section_assignment():
    _app()
    dialog = ConnectionDialog(
        _materials(),
        sections={},
        initial_node_i=1,
        initial_node_j=2,
        node_positions={
            1: (0.0, 0.0, 0.0),
            2: (0.0, 0.0, 0.0),
        },
    )
    dialog.connection_type.setCurrentText("zeroLengthSection")

    try:
        dialog.spec()
    except ValueError as exc:
        assert "requires a Section assignment" in str(exc)
    else:
        raise AssertionError("Expected missing zeroLengthSection section to fail")
    dialog.close()


def test_builder_zero_length_section_requires_coincident_nodes():
    _app()
    dialog = ConnectionDialog(
        _materials(),
        sections=_sections(),
        initial_node_i=1,
        initial_node_j=2,
        node_positions={
            1: (0.0, 0.0, 0.0),
            2: (0.25, 0.0, 0.0),
        },
    )
    dialog.connection_type.setCurrentText("zeroLengthSection")
    dialog.section_combo.setCurrentIndex(
        dialog.section_combo.findData(7)
    )

    try:
        dialog.spec()
    except ValueError as exc:
        assert "zeroLengthSection requires coincident nodes" in str(exc)
    else:
        raise AssertionError("Expected separated zeroLengthSection pair to fail")
    dialog.close()


def test_builder_edits_general_zero_length_section_selection():
    _app()
    connection = ConnectionData(
        4,
        "Section interface",
        "zeroLengthSection",
        1,
        2,
        section_tag=7,
    )
    dialog = ConnectionDialog(
        _materials(),
        connection=connection,
        sections=_sections(),
        node_positions={
            1: (0.0, 0.0, 0.0),
            2: (0.0, 0.0, 0.0),
        },
    )

    assert dialog.connection_type.currentText() == "zeroLengthSection"
    assert dialog.section_combo.currentData() == 7
    assert dialog.spec()["section_tag"] == 7
    dialog.close()
