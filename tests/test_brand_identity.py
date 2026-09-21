from pathlib import Path

from openseespy_studio.brand import (
    BRAND_NAVY,
    BRAND_RED,
    PRODUCT_BACKEND,
    PRODUCT_FULL_NAME,
    PRODUCT_NAME,
)


def test_sare_product_identity_is_canonical():
    assert PRODUCT_NAME == "SARE"
    assert PRODUCT_FULL_NAME == (
        "Structural Analysis & Research Environment for OpenSees"
    )
    assert PRODUCT_BACKEND == "OpenSeesPy"


def test_sare_brand_colors_are_stable_hex_values():
    assert BRAND_NAVY == "#0B315C"
    assert BRAND_RED == "#E5252A"


def test_sare_brand_assets_are_bundled_in_source_tree():
    root = Path(__file__).resolve().parents[1]
    branding = root / "src" / "openseespy_studio" / "resources" / "branding"
    assert (branding / "sare_mark.svg").is_file()
    assert (branding / "sare_wordmark.svg").is_file()
