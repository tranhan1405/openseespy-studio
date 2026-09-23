from __future__ import annotations

import inspect

from openseespy_studio.ui.main_window import MainWindow, PropertiesPanel


def test_geometry_point_properties_expose_spatial_and_topology_information():
    source = inspect.getsource(MainWindow._show_point_geometry_properties)

    assert '"Distance from Origin"' in source
    assert '"Sketch Local"' in source
    assert '"Sketch Plane Offset"' in source
    assert '"Topology"' in source
    assert '"Used by Lines"' in source
    assert '"Used by Surfaces"' in source


def test_geometry_line_properties_expose_measurements_and_surface_usage():
    source = inspect.getsource(MainWindow._show_line_geometry_properties)

    assert '"Start XYZ"' in source
    assert '"End XYZ"' in source
    assert '"Delta XYZ"' in source
    assert '"Length"' in source
    assert '"Unit Direction"' in source
    assert '"Boundary of Surfaces"' in source


def test_geometry_surface_properties_expose_measurements_and_quality_hints():
    source = inspect.getsource(MainWindow._show_surface_geometry_properties)

    assert '"Center"' in source
    assert '"Area"' in source
    assert '"Perimeter"' in source
    assert '"Edge lengths"' in source
    assert '"Geometry aspect ratio"' in source
    assert '"Planarity error"' in source
    assert '"Boundary Geometry Lines"' in source


def test_properties_panel_allocates_room_for_descriptive_geometry_labels():
    source = inspect.getsource(PropertiesPanel.__init__)

    assert "self.table.setColumnWidth(0, 148)" in source
