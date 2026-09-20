from openseespy_studio.generator import (
    element_load_to_openseespy,
    load_pattern_to_openseespy,
    nodal_load_to_openseespy,
    prescribed_displacement_to_openseespy,
    time_series_to_openseespy,
    to_openseespy,
)
from openseespy_studio.model import StructuralModel
from openseespy_studio.project import (
    AnalysisSettingsData,
    ElementLoadData,
    LoadPatternData,
    MaterialData,
    NodalLoadData,
    PrescribedDisplacementData,
    ProjectDatabase,
    SectionData,
    TimeSeriesData,
    TransformationData,
)


def model_with_nodes():
    model=StructuralModel()
    model.add_node(1,0,0,0)
    model.add_node(2,1,0,0)
    return model


def test_nodal_mass_round_trip_and_generator():
    model=model_with_nodes()
    model.set_mass_many({1},(10,11,12,1,2,3))
    restored=StructuralModel.from_dict(model.to_dict())
    assert restored.nodes[1].mass==(10.0,11.0,12.0,1.0,2.0,3.0)
    script=to_openseespy(model)
    assert "ops.mass(1, 10, 11, 12, 1, 2, 3)" in script


def test_time_series_and_patterns_round_trip():
    project=ProjectDatabase(model=model_with_nodes())
    project.add_time_series(TimeSeriesData(1,"Gravity","Linear",1.0))
    project.add_time_series(TimeSeriesData(2,"EQ","Path",9.81,0.01,[0,0.1,-0.2]))
    project.add_load_pattern(LoadPatternData(1,"Dead","Plain",1))
    project.add_load_pattern(LoadPatternData(2,"EQ-X","UniformExcitation",2,1,1.0,0.0))
    project.add_nodal_load(NodalLoadData(1,"P",1,2,(1,2,3,4,5,6)))
    restored=ProjectDatabase.from_dict(project.to_dict())
    assert restored.time_series[2].values==[0.0,0.1,-0.2]
    assert restored.load_patterns[2].pattern_type=="UniformExcitation"
    assert restored.nodal_loads[1].values==(1.0,2.0,3.0,4.0,5.0,6.0)


def test_generator_load_commands():
    ts=TimeSeriesData(2,"EQ","Path",9.81,0.02,[0,0.5,-0.5])
    assert "ops.timeSeries('Path', 2" in time_series_to_openseespy(ts)
    plain=LoadPatternData(1,"Dead","Plain",2)
    uniform=LoadPatternData(2,"EQ","UniformExcitation",2,3,1.5,0.2)
    assert load_pattern_to_openseespy(plain)=="ops.pattern('Plain', 1, 2)"
    text=load_pattern_to_openseespy(uniform)
    assert "ops.pattern('UniformExcitation', 2, 3" in text
    assert "'-accel', 2" in text
    load=NodalLoadData(1,"Load",1,2,(10,0,-20,0,0,5))
    assert nodal_load_to_openseespy(load)=="ops.load(2, 10, 0, -20, 0, 0, 5)"


def test_full_script_places_nodal_load_under_plain_pattern():
    model=model_with_nodes()
    ts={1:TimeSeriesData(1,"Linear","Linear")}
    patterns={1:LoadPatternData(1,"Gravity","Plain",1)}
    loads={1:NodalLoadData(1,"P",1,2,(0,0,-100,0,0,0))}
    script=to_openseespy(model,time_series=ts,load_patterns=patterns,nodal_loads=loads)
    assert "ops.timeSeries('Linear', 1" in script
    assert "ops.pattern('Plain', 1, 1)" in script
    assert "ops.load(2, 0, 0, -100, 0, 0, 0)" in script


def test_nodal_load_requires_plain_pattern():
    project=ProjectDatabase(model=model_with_nodes())
    project.add_time_series(TimeSeriesData(1,"EQ","Path",1,0.01,[0,1]))
    project.add_load_pattern(LoadPatternData(1,"EQ","UniformExcitation",1,1))
    try:
        project.add_nodal_load(NodalLoadData(1,"Bad",1,1,(1,0,0,0,0,0)))
    except ValueError as exc:
        assert "Plain" in str(exc)
    else:
        raise AssertionError("Expected UniformExcitation nodal-load rejection")


def test_time_series_cannot_be_removed_when_used():
    project=ProjectDatabase(model=model_with_nodes())
    project.add_time_series(TimeSeriesData(1,"Linear","Linear"))
    project.add_load_pattern(LoadPatternData(1,"P","Plain",1))
    try:
        project.remove_time_series(1)
    except ValueError as exc:
        assert "used by load pattern" in str(exc)
    else:
        raise AssertionError("Expected dependency protection")


def test_prune_nodal_load_after_node_delete():
    project=ProjectDatabase(model=model_with_nodes())
    project.add_time_series(TimeSeriesData(1,"Linear","Linear"))
    project.add_load_pattern(LoadPatternData(1,"P","Plain",1))
    project.add_nodal_load(NodalLoadData(1,"P1",1,2,(1,0,0,0,0,0)))
    project.model.remove_node(2,cascade=True)
    assert project.prune_nodal_loads()==[1]





def test_prescribed_displacement_round_trip_and_generator():
    project=ProjectDatabase(model=model_with_nodes())
    project.add_time_series(TimeSeriesData(1,"Ramp","Linear"))
    project.add_load_pattern(LoadPatternData(1,"Settlement","Plain",1))
    displacement=PrescribedDisplacementData(
        1,
        "Support movement",
        1,
        2,
        1,
        0.015,
    )
    project.add_prescribed_displacement(displacement)

    restored=ProjectDatabase.from_dict(project.to_dict())
    item=restored.prescribed_displacements[1]
    assert item.node_tag==2
    assert item.dof==1
    assert item.value==0.015
    assert prescribed_displacement_to_openseespy(item)==(
        "ops.sp(2, 1, 0.015)"
    )


def test_full_script_places_prescribed_displacement_under_plain_pattern():
    model=model_with_nodes()
    ts={1:TimeSeriesData(1,"Ramp","Linear")}
    patterns={1:LoadPatternData(1,"Settlement","Plain",1)}
    displacements={
        1:PrescribedDisplacementData(
            1,"Move X",1,2,1,0.02
        )
    }

    script=to_openseespy(
        model,
        time_series=ts,
        load_patterns=patterns,
        prescribed_displacements=displacements,
    )

    pattern_index=script.index("ops.pattern('Plain', 1, 1)")
    sp_index=script.index("ops.sp(2, 1, 0.02)")
    assert pattern_index < sp_index
    assert "# Prescribed displacement 1: Move X" in script


def test_prescribed_displacement_rejects_restrained_dof():
    project=ProjectDatabase(model=model_with_nodes())
    project.model.set_fixity(2,(1,0,0,0,0,0))
    project.add_time_series(TimeSeriesData(1,"Ramp","Linear"))
    project.add_load_pattern(LoadPatternData(1,"Settlement","Plain",1))

    try:
        project.add_prescribed_displacement(
            PrescribedDisplacementData(
                1,"Bad UX",1,2,1,0.01
            )
        )
    except ValueError as exc:
        assert "restrained" in str(exc)
    else:
        raise AssertionError(
            "Expected prescribed displacement/support conflict"
        )


def test_prescribed_displacement_rejects_duplicate_node_dof():
    project=ProjectDatabase(model=model_with_nodes())
    project.add_time_series(TimeSeriesData(1,"Ramp","Linear"))
    project.add_load_pattern(LoadPatternData(1,"Settlement","Plain",1))
    project.add_prescribed_displacement(
        PrescribedDisplacementData(
            1,"Move once",1,2,1,0.01
        )
    )

    try:
        project.add_prescribed_displacement(
            PrescribedDisplacementData(
                2,"Move twice",1,2,1,0.02
            )
        )
    except ValueError as exc:
        assert "already has a prescribed displacement" in str(exc)
    else:
        raise AssertionError(
            "Expected duplicate node/DOF prescribed displacement rejection"
        )


def test_prescribed_displacement_requires_plain_pattern():
    project=ProjectDatabase(model=model_with_nodes())
    project.add_time_series(
        TimeSeriesData(1,"EQ","Path",1.0,0.01,[0.0,1.0])
    )
    project.add_load_pattern(
        LoadPatternData(1,"EQ","UniformExcitation",1,1)
    )

    try:
        project.add_prescribed_displacement(
            PrescribedDisplacementData(
                1,"Bad",1,2,1,0.01
            )
        )
    except ValueError as exc:
        assert "Plain" in str(exc)
    else:
        raise AssertionError(
            "Expected UniformExcitation prescribed-displacement rejection"
        )


def test_prune_prescribed_displacement_after_node_delete():
    project=ProjectDatabase(model=model_with_nodes())
    project.add_time_series(TimeSeriesData(1,"Ramp","Linear"))
    project.add_load_pattern(LoadPatternData(1,"Settlement","Plain",1))
    project.add_prescribed_displacement(
        PrescribedDisplacementData(
            1,"Move X",1,2,1,0.01
        )
    )
    project.model.remove_node(2,cascade=True)

    assert project.prune_prescribed_displacements()==[1]



def test_pattern_with_prescribed_displacement_cannot_become_uniform_excitation():
    project=ProjectDatabase(model=model_with_nodes())
    project.add_time_series(TimeSeriesData(1,"Ramp","Linear"))
    project.add_load_pattern(LoadPatternData(1,"Settlement","Plain",1))
    project.add_prescribed_displacement(
        PrescribedDisplacementData(
            1,"Move X",1,2,1,0.01
        )
    )

    try:
        project.update_load_pattern(
            1,
            LoadPatternData(
                1,
                "Not a Plain pattern",
                "UniformExcitation",
                1,
                1,
            ),
        )
    except ValueError as exc:
        assert "cannot be changed to UniformExcitation" in str(exc)
    else:
        raise AssertionError(
            "Expected dependency protection for prescribed displacement"
        )


def test_cyclic_driver_rejects_pattern_with_prescribed_displacement():
    model=model_with_nodes()
    ts={1:TimeSeriesData(1,"Linear","Linear")}
    patterns={1:LoadPatternData(1,"Driver","Plain",1)}
    displacements={
        1:PrescribedDisplacementData(
            1,"Move X",1,2,1,0.01
        )
    }
    analysis=AnalysisSettingsData(
        1,
        "Cyclic",
        analysis_type="Cyclic",
        control_node=2,
        control_dof=1,
        cyclic_targets=[0.01,-0.01,0.0],
        cyclic_increment=0.001,
        deferred_pattern_tags=[1],
    )

    try:
        to_openseespy(
            model,
            time_series=ts,
            load_patterns=patterns,
            prescribed_displacements=displacements,
            analyses={1:analysis},
            active_analysis_tag=1,
        )
    except ValueError as exc:
        assert "cannot contain Prescribed Displacement" in str(exc)
    else:
        raise AssertionError(
            "Expected cyclic driver/prescribed-displacement rejection"
        )

def test_element_load_round_trip_and_project_validation():
    project=ProjectDatabase(model=model_with_nodes())
    project.model.add_element(1,1,2,transf_tag=1)
    project.add_time_series(TimeSeriesData(1,"Linear","Linear"))
    project.add_load_pattern(LoadPatternData(1,"Dead","Plain",1))
    project.add_element_load(
        ElementLoadData(
            1,
            "UDL",
            1,
            1,
            "Uniform",
            wx=1.0,
            wy=-2.0,
            wz=-3.0,
        )
    )

    restored=ProjectDatabase.from_dict(project.to_dict())

    load=restored.element_loads[1]
    assert load.load_type=="Uniform"
    assert load.element_tag==1
    assert (load.wx,load.wy,load.wz)==(1.0,-2.0,-3.0)


def test_uniform_and_point_element_load_generator():
    uniform=ElementLoadData(
        1,"UDL",1,5,"Uniform",wx=1.0,wy=-2.0,wz=-3.0
    )
    point=ElementLoadData(
        2,"Point",1,5,"Point",
        px=4.0,py=-5.0,pz=-6.0,x_over_l=0.25
    )

    uniform_text=element_load_to_openseespy(
        uniform,
        StructuralModel(),
    )
    point_text=element_load_to_openseespy(
        point,
        StructuralModel(),
    )

    assert uniform_text == (
        "ops.eleLoad('-ele', 5, '-type', '-beamUniform', -2, -3, 1)"
    )
    assert point_text == (
        "ops.eleLoad('-ele', 5, '-type', '-beamPoint', -5, -6, 0.25, 4)"
    )


def _self_weight_model_and_data(*, vertical=False):
    model=StructuralModel()
    model.add_node(1,0,0,0)
    model.add_node(2,0,0,2 if vertical else 0)
    if not vertical:
        model.nodes[2].xyz=(2.0,0.0,0.0)
    model.add_element(1,1,2,section_tag=1,transf_tag=1)

    material=MaterialData(
        1,
        "Dense",
        "Elastic",
        {"E":2.0e11},
        density=1000.0,
    )
    section=SectionData(
        1,
        "A=0.2",
        "Elastic",
        {"A":0.2},
        material_tag=1,
    )
    transformation=TransformationData(
        1,
        "T",
        "Linear",
        (1.0,0.0,0.0) if vertical else (0.0,0.0,1.0),
    )
    load=ElementLoadData(
        1,
        "Self Weight",
        1,
        1,
        "SelfWeight",
        gravity=(0.0,0.0,-10.0),
    )
    return model,{1:section},{1:material},{1:transformation},load


def test_self_weight_horizontal_beam_projects_global_z_to_local_z():
    model,sections,materials,transformations,load=(
        _self_weight_model_and_data(vertical=False)
    )

    text=element_load_to_openseespy(
        load,
        model,
        sections,
        materials,
        transformations,
    )

    assert text == (
        "ops.eleLoad('-ele', 1, '-type', '-beamUniform', 0, -2, 0)"
    )


def test_self_weight_vertical_column_projects_global_z_to_local_x():
    model,sections,materials,transformations,load=(
        _self_weight_model_and_data(vertical=True)
    )

    text=element_load_to_openseespy(
        load,
        model,
        sections,
        materials,
        transformations,
    )

    assert text == (
        "ops.eleLoad('-ele', 1, '-type', '-beamUniform', 0, 0, -2)"
    )


def test_self_weight_density_override_works_without_linked_material():
    model=StructuralModel()
    model.add_node(1,0,0,0)
    model.add_node(2,2,0,0)
    model.add_element(1,1,2,section_tag=1,transf_tag=1)
    sections={
        1:SectionData(
            1,
            "Manual",
            "Elastic",
            {"A":0.1},
        )
    }
    transformations={
        1:TransformationData(
            1,"Beam","Linear",(0.0,0.0,1.0)
        )
    }
    load=ElementLoadData(
        1,
        "Self Weight",
        1,
        1,
        "SelfWeight",
        gravity=(0.0,0.0,-10.0),
        density_override=500.0,
    )

    text=element_load_to_openseespy(
        load,
        model,
        sections,
        {},
        transformations,
    )

    assert text == (
        "ops.eleLoad('-ele', 1, '-type', '-beamUniform', 0, -0.5, 0)"
    )


def test_full_script_places_element_load_under_plain_pattern():
    model=StructuralModel()
    model.add_node(1,0,0,0)
    model.add_node(2,2,0,0)
    model.set_fixity(1,(1,1,1,1,1,1))
    model.add_element(1,1,2,transf_tag=1)

    ts={1:TimeSeriesData(1,"Linear","Linear")}
    patterns={1:LoadPatternData(1,"Dead","Plain",1)}
    transformations={
        1:TransformationData(
            1,"Beam","Linear",(0.0,0.0,1.0)
        )
    }
    loads={
        1:ElementLoadData(
            1,"UDL",1,1,"Uniform",wz=-100.0
        )
    }

    script=to_openseespy(
        model,
        transformations=transformations,
        time_series=ts,
        load_patterns=patterns,
        element_loads=loads,
    )

    assert "ops.pattern('Plain', 1, 1)" in script
    assert (
        "ops.eleLoad('-ele', 1, '-type', '-beamUniform', 0, -100, 0)"
        in script
    )


def test_prune_element_load_after_element_delete():
    project=ProjectDatabase(model=model_with_nodes())
    project.model.add_element(1,1,2,transf_tag=1)
    project.add_time_series(TimeSeriesData(1,"Linear","Linear"))
    project.add_load_pattern(LoadPatternData(1,"P","Plain",1))
    project.add_element_load(
        ElementLoadData(1,"UDL",1,1,"Uniform",wy=-1.0)
    )
    project.model.remove_element(1)

    assert project.prune_element_loads()==[1]


def test_self_weight_can_generate_n_per_m_for_n_m_s_project():
    model,sections,materials,transformations,load=(
        _self_weight_model_and_data(vertical=False)
    )

    text=element_load_to_openseespy(
        load,
        model,
        sections,
        materials,
        transformations,
        {"length":"m","force":"N","time":"s"},
    )

    assert text == (
        "ops.eleLoad('-ele', 1, '-type', '-beamUniform', 0, -2000, 0)"
    )


def test_generated_script_declares_consistent_project_units():
    model=model_with_nodes()
    script=to_openseespy(
        model,
        units={"length":"m","force":"kN","time":"s"},
    )

    assert "# Consistent model units: m, kN, s" in script
    assert "Material stress/modulus inputs are stored in Pa" in script


def test_2d_beam_load_commands_use_2d_opensees_signature():
    model = StructuralModel("2d-loads", ndm=2, ndf=3)
    model.add_node(1, 0.0, 0.0)
    model.add_node(2, 3.0, 0.0)

    uniform = ElementLoadData(
        1,
        "2D uniform",
        pattern_tag=1,
        element_tag=1,
        load_type="Uniform",
        wx=2.0,
        wy=-5.0,
        wz=99.0,
    )
    point = ElementLoadData(
        2,
        "2D point",
        pattern_tag=1,
        element_tag=1,
        load_type="Point",
        px=3.0,
        py=-7.0,
        pz=88.0,
        x_over_l=0.25,
    )

    assert element_load_to_openseespy(uniform, model) == (
        "ops.eleLoad('-ele', 1, '-type', '-beamUniform', -5, 2)"
    )
    assert element_load_to_openseespy(point, model) == (
        "ops.eleLoad('-ele', 1, '-type', '-beamPoint', -7, 0.25, 3)"
    )
