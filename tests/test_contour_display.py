from openseespy_studio.contour import (
    contour_colormap,
    contour_display_options,
    resolve_contour_range,
)


def test_signed_auto_range_defaults_to_symmetric_diverging():
    options = contour_display_options({})
    assert resolve_contour_range([-2.0, 5.0], options) == (-5.0, 5.0)
    assert contour_colormap(options) == "coolwarm"


def test_magnitude_auto_range_is_not_forced_symmetric():
    options = contour_display_options({}, magnitude=True)
    assert options.symmetric is False
    assert resolve_contour_range(
        [1.0, 4.0],
        options,
        magnitude=True,
    ) == (1.0, 4.0)
    assert contour_colormap(options, magnitude=True) == "viridis"


def test_user_range_and_symmetric_mode():
    options = contour_display_options({
        "contour_range_mode": "user",
        "contour_min": -2.0,
        "contour_max": 8.0,
        "contour_symmetric": False,
        "contour_bands": 17,
    })
    assert resolve_contour_range([-100.0, 100.0], options) == (-2.0, 8.0)
    assert options.bands == 17

    symmetric = contour_display_options({
        "contour_range_mode": "user",
        "contour_min": -2.0,
        "contour_max": 8.0,
        "contour_symmetric": True,
    })
    assert resolve_contour_range(
        [-100.0, 100.0],
        symmetric,
    ) == (-8.0, 8.0)


def test_contour_options_clamp_invalid_band_count():
    low = contour_display_options({"contour_bands": 1})
    high = contour_display_options({"contour_bands": 1000})
    assert low.bands == 3
    assert high.bands == 64
