import math

import pytest

from openseespy_studio.generator import element_load_to_openseespy
from openseespy_studio.importer import import_openseespy_source
from openseespy_studio.model import StructuralModel
from openseespy_studio.postprocess import equilibrium_component_samples
from openseespy_studio.project import ElementLoadData, TransformationData


def test_triangular_load_round_trip_preserves_end_intensity_and_span():
    load = ElementLoadData(
        1,
        "Triangle",
        1,
        5,
        "Triangular",
        wy=0.0,
        wy_end=-12.0,
        a_over_l=0.1,
        b_over_l=0.9,
        coordinate_system="global",
    )

    restored = ElementLoadData.from_dict(load.to_dict())

    assert restored.load_type == "Triangular"
    assert restored.coordinate_system == "global"
    assert restored.wy == 0.0
    assert restored.wy_end == -12.0
    assert restored.a_over_l == 0.1
    assert restored.b_over_l == 0.9


def test_triangular_load_requires_exactly_one_zero_end():
    with pytest.raises(ValueError, match="exactly one zero-intensity end"):
        ElementLoadData(
            1,
            "Bad triangle",
            1,
            5,
            "Triangular",
            wy=-5.0,
            wy_end=-12.0,
        )

    with pytest.raises(ValueError, match="exactly one zero-intensity end"):
        ElementLoadData(
            2,
            "Zero triangle",
            1,
            5,
            "Triangular",
        )


def test_variable_distributed_load_rejects_invalid_span():
    with pytest.raises(ValueError, match=r"0 <= a/L < b/L <= 1"):
        ElementLoadData(
            1,
            "Bad span",
            1,
            5,
            "Trapezoidal",
            wy=-5.0,
            wy_end=-10.0,
            a_over_l=0.8,
            b_over_l=0.2,
        )


def test_3d_triangular_load_exports_native_beam_uniform_trapezoid_syntax():
    model = StructuralModel()
    load = ElementLoadData(
        1,
        "Triangle",
        1,
        5,
        "Triangular",
        wy=0.0,
        wz=0.0,
        wx=0.0,
        wy_end=-10.0,
        wz_end=-2.0,
        wx_end=1.0,
        a_over_l=0.2,
        b_over_l=0.8,
    )

    assert element_load_to_openseespy(load, model) == (
        "ops.eleLoad('-ele', 5, '-type', '-beamUniform', "
        "0, 0, 0, 0.2, 0.8, -10, -2, 1)"
    )


def test_2d_triangular_load_exports_native_partial_span_syntax():
    model = StructuralModel(ndm=2, ndf=3)
    load = ElementLoadData(
        1,
        "Triangle 2D",
        1,
        5,
        "Triangular",
        wy=-8.0,
        wx=2.0,
        wy_end=0.0,
        wx_end=0.0,
        a_over_l=0.25,
        b_over_l=1.0,
    )

    assert element_load_to_openseespy(load, model) == (
        "ops.eleLoad('-ele', 5, '-type', '-beamUniform', "
        "-8, 2, 0.25, 1, 0, 0)"
    )


def test_global_triangular_load_is_projected_at_both_ends():
    model = StructuralModel()
    model.add_node(1, 0.0, 0.0, 0.0)
    model.add_node(2, 2.0, 0.0, 0.0)
    model.add_element(1, 1, 2, transf_tag=1)
    transformations = {
        1: TransformationData(1, "Beam", "Linear", (0.0, 0.0, 1.0))
    }
    load = ElementLoadData(
        1,
        "Global triangle",
        1,
        1,
        "Triangular",
        wz=0.0,
        wz_end=-10.0,
        coordinate_system="global",
    )

    text = element_load_to_openseespy(
        load,
        model,
        transformations=transformations,
    )

    assert text == (
        "ops.eleLoad('-ele', 1, '-type', '-beamUniform', "
        "0, 0, 0, 0, 1, 0, -10, 0)"
    )


def test_importer_recovers_native_3d_triangular_beam_uniform():
    source = """
import openseespy.opensees as ops
ops.model('basic', '-ndm', 3, '-ndf', 6)
ops.node(1, 0, 0, 0)
ops.node(2, 3, 0, 0)
ops.geomTransf('Linear', 1, 0, 0, 1)
ops.element('elasticBeamColumn', 1, 1, 2, 0.02, 200e9, 80e9, 1e-4, 8e-5, 8e-5, 1)
ops.timeSeries('Linear', 1)
ops.pattern('Plain', 1, 1)
ops.eleLoad('-ele', 1, '-type', '-beamUniform', 0, 0, 0, 0.1, 0.9, -12, 0, 0)
"""
    result = import_openseespy_source(
        source,
        source_name="triangle.py",
        units={"length": "m", "force": "N", "time": "s"},
    )

    assert result.error_count == 0
    load = result.project.element_loads[1]
    assert load.load_type == "Triangular"
    assert load.wy == 0.0
    assert load.wy_end == -12.0
    assert load.a_over_l == 0.1
    assert load.b_over_l == 0.9


def test_linear_distributed_load_equilibrium_is_integrated_exactly():
    active = [{
        "type": "Linear",
        "wxa": 0.0,
        "wya": 0.0,
        "wza": 0.0,
        "wxb": 0.0,
        "wyb": -2.0,
        "wzb": 0.0,
        "a_over_l": 0.0,
        "b_over_l": 1.0,
    }]
    local_force = [0.0] * 12

    shear = equilibrium_component_samples(
        local_force,
        10.0,
        "Vy",
        active,
        sample_count=3,
    )
    moment = equilibrium_component_samples(
        local_force,
        10.0,
        "Mz",
        active,
        sample_count=3,
    )

    assert math.isclose(shear[-1][1], -10.0, abs_tol=1.0e-10)
    assert math.isclose(
        moment[-1][1],
        -100.0 / 3.0,
        rel_tol=1.0e-12,
        abs_tol=1.0e-10,
    )
