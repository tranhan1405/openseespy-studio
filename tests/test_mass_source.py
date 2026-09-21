import pytest

from openseespy_studio.mass_source import (
    apply_mass_source,
    evaluate_mass_source,
)
from openseespy_studio.model import StructuralModel
from openseespy_studio.project import (
    ConnectionData,
    ElementLoadData,
    LoadPatternData,
    MassSourceData,
    MaterialData,
    NodalLoadData,
    ProjectDatabase,
    SectionData,
    TimeSeriesData,
    TransformationData,
)


def build_mass_project() -> ProjectDatabase:
    model = StructuralModel("mass-source")
    model.add_node(1, 0.0, 0.0, 0.0)
    model.add_node(2, 4.0, 0.0, 0.0)
    model.add_element(
        1,
        1,
        2,
        section_tag=1,
        transf_tag=1,
    )
    project = ProjectDatabase(model=model)
    project.add_material(
        MaterialData(
            1,
            "Test material",
            "Elastic",
            {"E": 2.0e11},
            density=1000.0,
        )
    )
    project.add_section(
        SectionData(
            1,
            "A=0.2",
            "Elastic",
            {
                "E": 2.0e11,
                "A": 0.2,
                "Iz": 1.0,
                "Iy": 1.0,
                "G": 8.0e10,
                "J": 1.0,
            },
            material_tag=1,
        )
    )
    project.add_transformation(
        TransformationData(
            1,
            "Global Z",
            "Linear",
            (0.0, 0.0, 1.0),
        )
    )

    project.add_time_series(TimeSeriesData(1, "Dead TS", "Linear", 1.0))
    project.add_load_pattern(LoadPatternData(1, "Dead", "Plain", 1))
    project.add_element_load(
        ElementLoadData(
            1,
            "Dead uniform",
            1,
            1,
            "Uniform",
            wz=-10.0,
        )
    )

    project.add_time_series(TimeSeriesData(2, "Live TS", "Linear", 1.0))
    project.add_load_pattern(LoadPatternData(2, "Live", "Plain", 2))
    project.add_nodal_load(
        NodalLoadData(
            1,
            "Live node",
            2,
            2,
            (0.0, 0.0, -20.0, 0.0, 0.0, 0.0),
        )
    )
    return project


def test_mass_source_combines_self_dead_and_fractional_live_load():
    project = build_mass_project()
    source = MassSourceData(
        1,
        "Seismic mass",
        include_self_mass=True,
        load_factors={1: 1.0, 2: 0.25},
        gravity_axis=3,
        directions=(1, 2),
    )

    summary = evaluate_mass_source(project, source)

    # rho=1000 kg/m3 = 1 t/m3 in kN-m-s.
    # A=0.2 m2, L=4 m -> 0.8 t structural self mass.
    assert summary.self_mass == pytest.approx(0.8)

    dead_mass = 10.0 * 4.0 / 9.80665
    live_mass = (20.0 * 0.25) / 9.80665
    assert summary.load_mass == pytest.approx(dead_mass + live_mass)
    assert summary.total_mass == pytest.approx(
        0.8 + dead_mass + live_mass
    )


def test_apply_mass_source_replaces_selected_translational_components():
    project = build_mass_project()
    project.model.set_mass(1, (99.0, 88.0, 7.0, 6.0, 5.0, 4.0))
    source = MassSourceData(
        1,
        "Dead only",
        include_self_mass=False,
        load_factors={1: 1.0},
        gravity_axis=3,
        directions=(1, 2),
    )

    first = apply_mass_source(project, source)
    expected = (10.0 * 4.0 / 9.80665) / 2.0
    assert project.model.nodes[1].mass == pytest.approx(
        (expected, expected, 7.0, 6.0, 5.0, 4.0)
    )

    # Regeneration replaces rather than accumulates mass.
    second = apply_mass_source(project, source)
    assert project.model.nodes[1].mass[0] == pytest.approx(expected)
    assert second.total_mass == pytest.approx(first.total_mass)


def test_mass_source_skips_self_weight_load_when_self_mass_is_enabled():
    project = build_mass_project()
    project.add_element_load(
        ElementLoadData(
            3,
            "Self weight",
            1,
            1,
            "SelfWeight",
            gravity=(0.0, 0.0, -9.80665),
        )
    )
    source = MassSourceData(
        1,
        "No duplicate self weight",
        include_self_mass=True,
        load_factors={1: 1.0},
        gravity_axis=3,
        directions=(1,),
    )

    summary = evaluate_mass_source(project, source)
    assert summary.skipped_self_weight_load_tags == [3]
    assert summary.self_mass == pytest.approx(0.8)
    assert summary.load_mass == pytest.approx(10.0 * 4.0 / 9.80665)


def test_mass_source_round_trip_and_load_pattern_tag_follow():
    project = build_mass_project()
    source = MassSourceData(
        1,
        "Code mass",
        include_self_mass=True,
        load_factors={1: 1.0, 2: 0.3},
        gravity_axis=3,
        directions=(1, 2),
    )
    project.add_mass_source(source)

    restored = ProjectDatabase.from_dict(project.to_dict())
    assert restored.mass_sources[1].load_factors == {1: 1.0, 2: 0.3}
    assert restored.mass_sources[1].directions == (1, 2)

    pattern = restored.load_patterns[2]
    restored.update_load_pattern(
        2,
        LoadPatternData(
            5,
            "Live renamed",
            "Plain",
            pattern.time_series_tag,
        ),
    )
    assert restored.mass_sources[1].load_factors == {1: 1.0, 5: 0.3}

    restored.remove_load_pattern(5)
    assert restored.mass_sources[1].load_factors == {1: 1.0}


def test_mass_source_rejects_dynamic_path_pattern():
    project = build_mass_project()
    project.add_time_series(
        TimeSeriesData(3, "Dynamic", "Path", 1.0, 0.01, [0.0, 1.0])
    )
    project.add_load_pattern(
        LoadPatternData(3, "Not gravity", "Plain", 3)
    )
    source = MassSourceData(
        1,
        "Bad",
        include_self_mass=False,
        load_factors={3: 1.0},
        gravity_axis=3,
        directions=(1,),
    )

    with pytest.raises(ValueError, match="Linear/Constant"):
        evaluate_mass_source(project, source)


def test_mass_source_excludes_managed_ground_nodes():
    project = build_mass_project()
    project.model.add_node(3, 4.0, 0.0, 0.0)
    project.model.nodes[3].fixity = (1, 1, 1, 1, 1, 1)
    project.add_material(
        MaterialData(2, "Ground spring", "Elastic", {"E": 1.0e6})
    )
    project.add_connection(
        ConnectionData(
            10,
            "Managed ground",
            "zeroLength",
            2,
            3,
            materials_by_dof={1: 2},
            generated_ground_node=3,
        )
    )
    project.add_nodal_load(
        NodalLoadData(
            9,
            "Accidental ground gravity load",
            2,
            3,
            (0.0, 0.0, -100.0, 0.0, 0.0, 0.0),
        )
    )
    project.model.set_mass(3, (9.0, 8.0, 7.0, 6.0, 5.0, 4.0))

    source = MassSourceData(
        9,
        "Ground-safe mass",
        include_self_mass=False,
        load_factors={2: 1.0},
        gravity_axis=3,
        directions=(1, 2),
    )

    summary = evaluate_mass_source(project, source)
    assert summary.nodal_mass[3] == 0.0

    apply_mass_source(project, source)
    assert project.model.nodes[3].mass == (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)


def test_project_rejects_mass_source_using_path_time_series():
    project = build_mass_project()
    project.add_time_series(
        TimeSeriesData(3, "Dynamic", "Path", dt=0.01, values=[0.0, 1.0])
    )
    project.add_load_pattern(
        LoadPatternData(3, "Dynamic plain", "Plain", time_series_tag=3)
    )

    with pytest.raises(
        ValueError,
        match=r"requires Linear/Constant gravity-style time series",
    ):
        project.add_mass_source(
            MassSourceData(
                3,
                "Bad source",
                include_self_mass=False,
                load_factors={3: 1.0},
                gravity_axis=3,
                directions=(1,),
            )
        )


def test_project_rejects_time_series_change_that_breaks_mass_source():
    project = build_mass_project()
    project.add_mass_source(
        MassSourceData(
            1,
            "Dead mass",
            include_self_mass=False,
            load_factors={1: 1.0},
            gravity_axis=3,
            directions=(1,),
        )
    )

    with pytest.raises(
        ValueError,
        match=r"must remain Linear or Constant",
    ):
        project.update_time_series(
            1,
            TimeSeriesData(
                1,
                "Dynamic replacement",
                "Path",
                dt=0.01,
                values=[0.0, 1.0],
            ),
        )

    assert project.time_series[1].series_type == "Linear"


def test_project_rejects_pattern_type_change_that_breaks_mass_source():
    project = build_mass_project()
    project.add_mass_source(
        MassSourceData(
            1,
            "Dead mass",
            include_self_mass=False,
            load_factors={1: 1.0},
            gravity_axis=3,
            directions=(1,),
        )
    )

    with pytest.raises(
        ValueError,
        match=r"must remain a Plain pattern",
    ):
        project.update_load_pattern(
            1,
            LoadPatternData(
                1,
                "Excitation",
                "UniformExcitation",
                time_series_tag=1,
                direction=1,
            ),
        )

    assert project.load_patterns[1].pattern_type == "Plain"
