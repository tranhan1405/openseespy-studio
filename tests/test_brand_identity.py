from pathlib import Path

from openseespy_studio.brand import (
    BRAND_NAVY,
    BRAND_ORANGE,
    BRAND_RED,
    PRODUCT_BACKEND,
    PRODUCT_FULL_NAME,
    PRODUCT_NAME,
)


def test_fewiz_product_identity_is_canonical():
    assert PRODUCT_NAME == "FEWIZ"
    assert PRODUCT_FULL_NAME == "Finite Element Wizard"
    assert PRODUCT_BACKEND == "OpenSeesPy"


def test_fewiz_brand_colors_are_stable_hex_values():
    assert BRAND_NAVY == "#0B315C"
    assert BRAND_RED == "#E5252A"
    assert BRAND_ORANGE == "#F28C00"


def test_fewiz_brand_assets_are_bundled_in_source_tree():
    root = Path(__file__).resolve().parents[1]
    branding = root / "src" / "openseespy_studio" / "resources" / "branding"
    assert (branding / "fewiz_mark.svg").is_file()
    assert (branding / "fewiz_mark_light.svg").is_file()
    assert (branding / "fewiz_mark_mono.svg").is_file()
    assert (branding / "fewiz_wordmark.svg").is_file()


def test_legacy_brand_asset_aliases_remain_available():
    root = Path(__file__).resolve().parents[1]
    branding = root / "src" / "openseespy_studio" / "resources" / "branding"
    assert (branding / "sare_mark.svg").is_file()
    assert (branding / "sare_wordmark.svg").is_file()
