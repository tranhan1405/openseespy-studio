import inspect

from openseespy_studio.ui.main_window import MainWindow
from openseespy_studio.ui.viewport import ModelViewport


def test_mass_tree_is_owned_by_fe_model_not_loads_and_bcs():
    source = inspect.getsource(MainWindow._refresh_tree)

    assert "fe_model.addChild(mass_root)" in source
    assert "mass_root.addChild(masses_root)" in source
    assert "mass_root.addChild(element_masses_root)" in source
    assert "mass_root.addChild(mass_sources_root)" in source
    assert "loads_bc_root.addChild(masses_root)" not in source
    assert "loads_bc_root.addChild(mass_sources_root)" not in source
    assert '("nodal_mass", tag)' in source
    assert '("element_mass", tag)' in source


def test_mass_commands_are_separate_from_loads_and_bcs_context():
    source = inspect.getsource(MainWindow._show_tree_context_menu)
    loads_block = source.split('if kind == "loads_bc_root":', 1)[1].split(
        'if kind == "boundary_root":', 1
    )[0]

    assert "Assign Mass to Current Node Selection" not in loads_block
    assert "New Mass Source" not in loads_block
    assert 'if kind == "mass_root":' in source
    assert "Assign Nodal Mass to Current Selection" in source


def test_mass_has_independent_viewport_display_option():
    init_source = inspect.getsource(ModelViewport.__init__)
    draw_source = inspect.getsource(ModelViewport._draw_masses)
    update_source = inspect.getsource(ModelViewport._update_display_option)

    assert '"masses": False' in init_source
    assert "display-mass-points" in draw_source
    assert "display-mass-labels" in draw_source
    assert 'name == "masses"' in update_source


def test_mass_context_actions_do_not_leak_into_properties_handler():
    source = inspect.getsource(MainWindow._show_tree_root_properties)

    assert "menu.addAction" not in source
    assert 'if kind == "element_masses_root":' in source
