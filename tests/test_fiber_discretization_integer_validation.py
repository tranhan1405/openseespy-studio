import pytest

from openseespy_studio.project import FiberComponentData


def _component(component_type, **parameters):
    return FiberComponentData(
        component_type,
        component_type,
        1,
        parameters=parameters,
    )


def _component_from_dict(component_type, **parameters):
    return FiberComponentData.from_dict(
        {
            "component_type": component_type,
            "name": component_type,
            "material_tag": 1,
            "parameters": parameters,
        }
    )


def test_rect_patch_rejects_fractional_n_y():
    with pytest.raises(ValueError, match=r"n_y must be an integer"):
        _component("RectPatch", n_y=10.5)
    with pytest.raises(ValueError, match=r"n_y must be an integer"):
        _component_from_dict("RectPatch", n_y=10.5)


def test_rect_patch_rejects_fractional_n_z():
    with pytest.raises(ValueError, match=r"n_z must be an integer"):
        _component("RectPatch", n_z=10.5)
    with pytest.raises(ValueError, match=r"n_z must be an integer"):
        _component_from_dict("RectPatch", n_z=10.5)


def test_circ_patch_rejects_fractional_n_radial():
    with pytest.raises(ValueError, match=r"n_radial must be an integer"):
        _component("CircPatch", n_radial=4.5)
    with pytest.raises(ValueError, match=r"n_radial must be an integer"):
        _component_from_dict("CircPatch", n_radial=4.5)


def test_circ_patch_rejects_fractional_n_circum():
    with pytest.raises(ValueError, match=r"n_circum must be an integer"):
        _component("CircPatch", n_circum=24.5)
    with pytest.raises(ValueError, match=r"n_circum must be an integer"):
        _component_from_dict("CircPatch", n_circum=24.5)


def test_straight_layer_rejects_fractional_bar_count():
    with pytest.raises(ValueError, match=r"n_bars must be an integer"):
        _component("StraightLayer", n_bars=4.5)
    with pytest.raises(ValueError, match=r"n_bars must be an integer"):
        _component_from_dict("StraightLayer", n_bars=4.5)


def test_circ_layer_rejects_fractional_bar_count():
    with pytest.raises(ValueError, match=r"n_bars must be an integer"):
        _component("CircLayer", n_bars=8.5)
    with pytest.raises(ValueError, match=r"n_bars must be an integer"):
        _component_from_dict("CircLayer", n_bars=8.5)
