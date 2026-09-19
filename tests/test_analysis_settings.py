from openseespy_studio.generator import analysis_to_openseespy, to_openseespy
from openseespy_studio.model import StructuralModel
from openseespy_studio.project import AnalysisSettingsData, ProjectDatabase


def model():
    m=StructuralModel(); m.add_node(1,0,0,0); m.add_node(2,1,0,0); return m


def test_analysis_round_trip_and_active():
    p=ProjectDatabase(model=model())
    a=AnalysisSettingsData(1,"Gravity","Static",steps=10,load_increment=0.1)
    p.add_analysis(a)
    assert p.active_analysis_tag==1
    restored=ProjectDatabase.from_dict(p.to_dict())
    assert restored.active_analysis_tag==1
    assert restored.analyses[1].analysis_type=="Static"


def test_static_analysis_generator():
    a=AnalysisSettingsData(1,"Gravity","Static",steps=5,load_increment=0.2,recovery=True)
    lines=analysis_to_openseespy(a)
    text="\n".join(lines)
    assert "ops.constraints('Transformation')" in text
    assert "ops.integrator('LoadControl', 0.2)" in text
    assert "ops.analysis('Static')" in text
    assert "for _studio_step in range(5):" in text
    assert "NewtonLineSearch" in text


def test_pushover_generator():
    a=AnalysisSettingsData(1,"Push","Pushover",steps=100,control_node=2,control_dof=1,displacement_increment=0.002)
    text="\n".join(analysis_to_openseespy(a))
    assert "ops.integrator('DisplacementControl', 2, 1, 0.002)" in text
    assert "'control_node': 2" in text
    assert "'control_dof': 1" in text
    assert "'monitor_node': 2, 'control_dof': 1" in text


def test_transient_generator():
    a=AnalysisSettingsData(1,"EQ","Transient",steps=200,dt=0.005,gamma=0.5,beta=0.25)
    text="\n".join(analysis_to_openseespy(a))
    assert "ops.integrator('Newmark', 0.5, 0.25)" in text
    assert "ops.analyze(1, 0.005)" in text


def test_modal_generator():
    a=AnalysisSettingsData(1,"Modes","Modal",num_modes=6)
    text="\n".join(analysis_to_openseespy(a))
    assert "_studio_eigenvalues = ops.eigen(6)" in text
    assert "ops.integrator" not in text


def test_only_active_analysis_is_generated():
    m=model()
    analyses={
        1:AnalysisSettingsData(1,"Static","Static"),
        2:AnalysisSettingsData(2,"Modes","Modal",num_modes=4),
    }
    script=to_openseespy(m,analyses=analyses,active_analysis_tag=2)
    assert "# Active analysis 2: Modes" in script
    assert "ops.eigen(4)" in script
    assert "# Active analysis 1: Static" not in script


def test_pushover_control_node_is_validated():
    p=ProjectDatabase(model=model())
    try:
        p.add_analysis(AnalysisSettingsData(1,"Bad","Pushover",control_node=99))
    except ValueError as exc:
        assert "control node" in str(exc)
    else:
        raise AssertionError("Expected control node validation")
