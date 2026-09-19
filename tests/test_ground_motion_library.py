from openseespy_studio.ground_motion_library import (
    GROUND_MOTION_LIBRARY,
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


def test_target_pga_scale_factor():
    values = [0.0, 0.25, -0.5]
    factor = scale_factor_for_target_pga(
        values,
        "g",
        target_pga_g=0.35,
    )
    assert abs(factor - 0.7) < 1.0e-12
