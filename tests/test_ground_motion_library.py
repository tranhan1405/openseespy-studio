import io
import zipfile

from openseespy_studio.ground_motion_library import (
    GROUND_MOTION_LIBRARY,
    available_ground_motion_presets,
    discover_fema_p695_presets,
    download_fema_p695_farfield_library,
    fema_p695_library_installed,
    common_scale_factor_for_target_pga,
    load_bundled_ground_motion_record,
    parse_ground_motion_record_text,
    parse_peer_at2_text,
    pga_in_g,
    scale_factor_for_target_pga,
)


def test_ground_motion_library_keys_are_unique():
    keys = [item.key for item in GROUND_MOTION_LIBRARY]
    assert len(keys) == len(set(keys))
    assert "custom" in keys
    assert "el-centro-1940" in keys
    assert "northridge-1994-rinaldi" in keys
    assert "kobe-1995-kjma" in keys


def test_parse_peer_at2_reads_all_values_and_header_metadata():
    text = """
PEER NGA STRONG MOTION DATABASE RECORD
ACCELERATION TIME HISTORY IN UNITS OF G
NPTS= 6, DT= .02000 SEC
 1.0E-03  2.0E-03  3.0E-03
-4.0E-03 -5.0E-03 -6.0E-03
"""
    parsed = parse_peer_at2_text(text)

    assert parsed.npts == 6
    assert parsed.dt == 0.02
    assert parsed.input_unit == "g"
    assert parsed.format == "PEER AT2"
    assert parsed.values == [
        0.001,
        0.002,
        0.003,
        -0.004,
        -0.005,
        -0.006,
    ]


def test_auto_parser_detects_at2_from_header_without_extension():
    text = """
ACCELERATION TIME HISTORY IN UNITS OF G
NPTS= 4, DT= 0.01 SEC
0.1 0.2
0.3 0.4
"""
    parsed = parse_ground_motion_record_text(
        text,
        filename="record.txt",
    )
    assert parsed.format == "PEER AT2"
    assert parsed.values == [0.1, 0.2, 0.3, 0.4]
    assert parsed.dt == 0.01


def test_text_csv_parser_preserves_column_selection():
    text = "0.00, 0.10\n0.01, -0.20\n0.02, 0.30\n"
    parsed = parse_ground_motion_record_text(
        text,
        column=2,
        filename="record.csv",
    )
    assert parsed.format == "text/CSV"
    assert parsed.dt is None
    assert parsed.values == [0.10, -0.20, 0.30]


def test_pga_conversion_to_g_for_supported_units():
    assert pga_in_g([0.0, -0.5], "g") == 0.5
    assert abs(pga_in_g([0.0, 9.80665], "m/s²") - 1.0) < 1.0e-12
    assert abs(pga_in_g([0.0, 980.665], "cm/s²") - 1.0) < 1.0e-12
    assert abs(pga_in_g([0.0, 9806.65], "mm/s²") - 1.0) < 1.0e-12


def test_target_pga_scale_factor():
    values = [0.0, 0.25, -0.5]
    factor = scale_factor_for_target_pga(
        values,
        "g",
        target_pga_g=0.35,
    )
    assert abs(factor - 0.7) < 1.0e-12


def test_common_target_pga_scale_preserves_component_ratio():
    factor = common_scale_factor_for_target_pga(
        [
            [0.0, 0.25, -0.50],
            [0.0, 0.10, -0.20],
        ],
        "g",
        target_pga_g=0.40,
    )
    assert abs(factor - 0.8) < 1.0e-12
    assert abs(0.50 * factor - 0.40) < 1.0e-12
    assert abs(0.20 * factor - 0.16) < 1.0e-12



def test_bundled_el_centro_record_loads_without_user_file():
    record = load_bundled_ground_motion_record("el-centro-1940")
    assert record.format == "PEER AT2"
    assert record.npts == 1559
    assert record.dt == 0.02
    assert record.input_unit == "g"
    assert len(record.values) == 1559
    assert pga_in_g(record.values, "g") > 0.30


def test_bundled_northridge_rinaldi_record_loads_without_user_file():
    record = load_bundled_ground_motion_record(
        "northridge-1994-rinaldi"
    )
    assert record.format == "SimCenter JSON"
    # Upstream SimCenter metadata declares 1992 points, while its bundled
    # accel_data array contains 1991 actual samples. Use the real data length.
    assert record.npts == 1991
    assert record.dt == 0.01
    assert record.input_unit == "g"
    assert len(record.values) == 1991
    assert pga_in_g(record.values, "g") > 0.50


def test_available_library_hides_reference_only_presets():
    available = available_ground_motion_presets()
    assert any(item.key == "el-centro-1940" for item in available)
    assert any(
        item.key == "northridge-1994-rinaldi"
        for item in available
    )
    assert not any(
        item.key == "kobe-1995-kjma"
        for item in available
    )
    assert all(
        item.key == "custom"
        or item.bundled_resource
        or item.local_path
        for item in available
    )


def test_fema_p695_downloader_caches_horizontal_records_and_skips_vertical(
    tmp_path,
):
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        for index in range(44):
            archive.writestr(
                f"ATC63/NORTHR/H{index:02d}000.AT2",
                (
                    "PEER NGA RECORD\n"
                    "ACCELERATION TIME HISTORY IN UNITS OF G\n"
                    "NPTS= 2, DT= 0.010 SEC\n"
                    "0.0 0.1\n"
                ),
            )
        archive.writestr(
            "ATC63/NORTHR/H-UP.AT2",
            (
                "PEER NGA RECORD\n"
                "ACCELERATION TIME HISTORY IN UNITS OF G\n"
                "NPTS= 2, DT= 0.010 SEC\n"
                "0.0 0.2\n"
            ),
        )
    zip_bytes = payload.getvalue()

    class Response(io.BytesIO):
        def close(self):
            super().close()

    cache = tmp_path / "fema_p695_ff22"
    records = download_fema_p695_farfield_library(
        cache_dir=cache,
        opener=lambda _url: Response(zip_bytes),
    )

    assert len(records) == 44
    assert fema_p695_library_installed(cache)
    assert len(discover_fema_p695_presets(cache)) == 44
    assert all("UP" not in item.station for item in records)
    assert (cache / "_source.json").exists()
