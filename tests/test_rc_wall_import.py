from __future__ import annotations

from openseespy_studio.generator import build_mefi_crack_specs, to_openseespy
from openseespy_studio.importer import import_openseespy_source


def test_importer_recovers_official_rc_wall_stack():
    source = """
import openseespy.opensees as ops

ops.model('basic', '-ndm', 2, '-ndf', 3)

ops.node(1, 0.0, 0.0)
ops.node(2, 1220.0, 0.0)
ops.node(3, 0.0, 315.6857142857)
ops.node(4, 1220.0, 315.6857142857)
ops.fix(1, 1, 1, 1)
ops.fix(2, 1, 1, 1)

ops.uniaxialMaterial('Steel02', 1, 469.93, 200000.0, 0.02, 20.0, 0.925, 0.15)
ops.uniaxialMaterial('Steel02', 2, 409.71, 200000.0, 0.02, 20.0, 0.925, 0.15)
ops.uniaxialMaterial('Steel02', 3, 429.78, 200000.0, 0.01, 20.0, 0.925, 0.15)
ops.uniaxialMaterial(
    'Concrete02', 4,
    -47.09, -0.00232, 0.0, -0.037, 0.1, 2.13, 1738.33
)
ops.uniaxialMaterial(
    'Concrete02', 5,
    -53.78, -0.00397, -9.42, -0.047, 0.1, 2.13, 1827.12
)

ops.nDMaterial(
    'OrthotropicRAConcrete', 6,
    4, 0.00008, -0.00232, 0.0,
    '-damageCte1', 0.175, '-damageCte2', 0.5
)
ops.nDMaterial(
    'OrthotropicRAConcrete', 7,
    5, 0.00008, -0.00397, 0.0,
    '-damageCte1', 0.175, '-damageCte2', 0.5
)
ops.nDMaterial(
    'SmearedSteelDoubleLayer', 8,
    1, 2, 0.0027, 0.0027, 0.0
)
ops.nDMaterial(
    'SmearedSteelDoubleLayer', 9,
    1, 3, 0.0082, 0.0323, 0.0
)

ops.section(
    'RCLMS', 10, 1, 1,
    '-reinfSteel', 8,
    '-conc', 6,
    '-concThick', 152.4
)
ops.section(
    'RCLMS', 11, 1, 2,
    '-reinfSteel', 9,
    '-conc', 6, 7,
    '-concThick', 50.8, 101.6
)

ops.element(
    'MEFI', 1, 1, 2, 4, 3, 8,
    '-width',
    228.6, 127.1333333333, 127.1333333333,
    127.1333333333, 127.1333333333, 127.1333333333,
    127.1333333335, 228.6,
    '-sec',
    11, 10, 10, 10, 10, 10, 10, 11
)
"""

    result = import_openseespy_source(
        source,
        source_name="rw_a20_wall_only.py",
        units={"length": "mm", "force": "N", "time": "s"},
    )

    assert result.error_count == 0
    assert result.unsupported_count == 0
    assert result.project.nd_materials[8].material_type == (
        "SmearedSteelDoubleLayer"
    )
    assert result.project.sections[10].section_type == "RCLMS"
    assert result.project.sections[11].section_type == "RCLMS"

    crack_specs = build_mefi_crack_specs(
        result.project.model,
        sections=result.project.sections,
        nd_materials=result.project.nd_materials,
    )
    assert 1 in crack_specs
    assert len(crack_specs[1]["panels"]) == 8
    assert all(
        panel["cracking_strain"] == 0.00008
        for panel in crack_specs[1]["panels"]
    )

    element = result.project.model.elements[1]
    assert element.element_type == "MEFI"
    assert element.node_tags() == (1, 2, 4, 3)
    assert len(element.mefi_widths) == 8
    assert element.mefi_section_tags == (
        11, 10, 10, 10, 10, 10, 10, 11,
    )

    exported = to_openseespy(
        result.project.model,
        materials=result.project.materials,
        sections=result.project.sections,
        transformations=result.project.transformations,
        constraints=result.project.constraints,
        connections=result.project.connections,
        units=result.project.units,
        nd_materials=result.project.nd_materials,
    )
    assert "ops.nDMaterial('SmearedSteelDoubleLayer', 8" in exported
    assert "ops.section('RCLMS', 10, 1, 1" in exported
    assert "ops.element('MEFI', 1, 1, 2, 4, 3, 8" in exported


def test_importer_rejects_mefi_array_count_mismatch():
    source = """
import openseespy.opensees as ops
ops.model('basic', '-ndm', 2, '-ndf', 3)
ops.node(1, 0.0, 0.0)
ops.node(2, 1.0, 0.0)
ops.node(3, 0.0, 1.0)
ops.node(4, 1.0, 1.0)
ops.element(
    'MEFI', 1, 1, 2, 4, 3, 4,
    '-width', 0.25, 0.25, 0.25,
    '-sec', 1, 1, 1, 1
)
"""

    result = import_openseespy_source(
        source,
        source_name="bad_mefi.py",
        units={"length": "m", "force": "N", "time": "s"},
    )

    assert 1 not in result.project.model.elements
    assert result.error_count >= 1
    assert any(
        "MEFI width/section arrays must match numFib"
        in issue.message
        for issue in result.issues
    )
