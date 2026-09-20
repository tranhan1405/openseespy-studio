from openseespy_studio.project import FiberData, SectionData
from openseespy_studio.ui.viewport import ModelViewport


def test_model_color_modes_normalize_user_facing_labels():
    assert ModelViewport._normalized_model_color_mode("Uniform") == "uniform"
    assert (
        ModelViewport._normalized_model_color_mode("Element Type")
        == "element_type"
    )
    assert ModelViewport._normalized_model_color_mode("Material") == "material"
    assert ModelViewport._normalized_model_color_mode("Section") == "section"
    assert ModelViewport._normalized_model_color_mode("unknown") == "uniform"


def test_display_palette_and_hex_conversion_are_deterministic():
    palette = ModelViewport._display_palette()
    assert len(palette) >= 8
    assert len(set(palette)) == len(palette)
    assert ModelViewport._hex_rgb("#2f80ed") == (47, 128, 237)


def test_fiber_dominant_material_uses_total_fiber_area():
    section = SectionData(
        tag=7,
        name="RC Fiber",
        section_type="Fiber",
        parameters={"GJ": 1.0e6},
        fibers=[
            FiberData(0.0, 0.0, 0.08, 1),
            FiberData(0.1, 0.1, 0.02, 1),
            FiberData(-0.1, -0.1, 0.01, 2),
            FiberData(0.2, 0.2, 0.01, 2),
        ],
    )

    assert ModelViewport._dominant_fiber_material(None, section) == 1
