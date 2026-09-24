from openseespy_studio.ui.main_window import (
    tree_item_drives_fe_navigation,
    tree_selection_drives_fe_navigation,
)


def test_only_canonical_fe_entities_drive_model_tree_navigation():
    assert tree_item_drives_fe_navigation(
        "node",
        {"model_root", "fe_model_root", "nodes_root"},
    ) is True
    assert tree_item_drives_fe_navigation(
        "element",
        {"model_root", "fe_model_root", "elements_root"},
    ) is True
    assert tree_selection_drives_fe_navigation([
        ("node", {"nodes_root"}),
        ("element", {"elements_root"}),
    ]) is True


def test_boundary_condition_node_is_reference_not_fe_navigation():
    assert tree_item_drives_fe_navigation(
        "node",
        {"loads_bc_root", "boundary_root", "boundary_group"},
    ) is False
    assert tree_selection_drives_fe_navigation([
        (
            "node",
            {"loads_bc_root", "boundary_root", "boundary_group"},
        )
    ]) is False


def test_reference_objects_never_steal_tree_focus():
    passive_kinds = (
        "solution_result",
        "recorder",
        "constraint",
        "connection",
        "nodal_mass",
        "element_mass",
        "mass_source",
        "nodal_load",
        "element_load",
        "prescribed_displacement",
        "set",
        "analysis",
        "job",
        "job_plot",
    )
    for kind in passive_kinds:
        assert tree_item_drives_fe_navigation(kind, set()) is False
        assert tree_selection_drives_fe_navigation([
            (kind, set())
        ]) is False


def test_mixed_object_and_fe_selection_stays_on_clicked_object_context():
    assert tree_selection_drives_fe_navigation([
        ("solution_result", set()),
        ("node", {"nodes_root"}),
    ]) is False
    assert tree_selection_drives_fe_navigation([
        ("recorder", set()),
        ("element", {"elements_root"}),
    ]) is False
