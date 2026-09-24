from openseespy_studio.ui.main_window import (
    tree_selection_drives_fe_navigation,
)


def test_only_direct_fe_entities_drive_model_tree_navigation():
    assert tree_selection_drives_fe_navigation({"node"}) is True
    assert tree_selection_drives_fe_navigation({"element"}) is True
    assert tree_selection_drives_fe_navigation({"node", "element"}) is True


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
        assert tree_selection_drives_fe_navigation({kind}) is False


def test_mixed_object_and_fe_selection_stays_on_clicked_object_context():
    assert (
        tree_selection_drives_fe_navigation({"solution_result", "node"})
        is False
    )
    assert (
        tree_selection_drives_fe_navigation({"recorder", "element"})
        is False
    )
