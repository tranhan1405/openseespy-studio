from __future__ import annotations

from PySide6.QtWidgets import QApplication

from openseespy_studio.generator import connection_to_openseespy
from openseespy_studio.project import (
    ConnectionData,
    MATERIAL_DEFAULTS,
    MaterialData,
    ProjectDatabase,
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


def test_builder_default_axial_preset_prefers_bond_material():
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
    assert dialog.preset.currentText() == "Axial / bond-slip spring"
    assert dialog.dof_checks[0].isChecked()
    assert not dialog.dof_checks[1].isChecked()
    assert dialog.material_combos[0].currentData() == 2
    spec = dialog.spec()
    assert spec["materials_by_dof"] == {1: 2}
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
