from openseespy_studio.generator import (
    load_pattern_to_openseespy,
    nodal_load_to_openseespy,
    time_series_to_openseespy,
    to_openseespy,
)
from openseespy_studio.model import StructuralModel
from openseespy_studio.project import (
    LoadPatternData,
    NodalLoadData,
    ProjectDatabase,
    TimeSeriesData,
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
