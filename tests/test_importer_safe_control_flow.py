from openseespy_studio.importer import import_openseespy_source


UNITS = {"length": "m", "force": "N", "time": "s"}


def test_safe_import_executes_resolvable_if_branch():
    source = """
import openseespy.opensees as ops
ops.model('basic', '-ndm', 3, '-ndf', 6)
height = 3.0
use_tall = True
if use_tall and height >= 3.0:
    ops.node(1, 0.0, 0.0, height)
else:
    ops.node(2, 0.0, 0.0, 1.0)
"""
    result = import_openseespy_source(source, units=UNITS)

    assert result.error_count == 0
    assert set(result.project.model.nodes) == {1}
    assert result.project.model.nodes[1].xyz == (0.0, 0.0, 3.0)


def test_safe_import_understands_main_guard_and_function_call():
    source = """
import openseespy.opensees as ops

def build_model(n, h):
    ops.model('basic', '-ndm', 3, '-ndf', 6)
    for i in range(n):
        ops.node(i + 1, 0.0, 0.0, i * h)

if __name__ == '__main__':
    build_model(4, 2.5)
"""
    result = import_openseespy_source(source, units=UNITS)

    assert result.error_count == 0
    assert set(result.project.model.nodes) == {1, 2, 3, 4}
    assert result.project.model.nodes[4].xyz == (0.0, 0.0, 7.5)


def test_safe_import_function_return_can_feed_opensees_arguments():
    source = """
import openseespy.opensees as ops

def elevation(level, h=3.0):
    return level * h

ops.model('basic', '-ndm', 3, '-ndf', 6)
ops.node(1, 0.0, 0.0, elevation(2))
ops.node(2, 0.0, 0.0, elevation(level=3, h=2.0))
"""
    result = import_openseespy_source(source, units=UNITS)

    assert result.error_count == 0
    assert result.project.model.nodes[1].xyz[2] == 6.0
    assert result.project.model.nodes[2].xyz[2] == 6.0


def test_safe_import_iterates_lists_and_enumerate():
    source = """
import openseespy.opensees as ops
ops.model('basic', '-ndm', 3, '-ndf', 6)
levels = [0.0, 3.0, 6.0]
for i, z in enumerate(levels):
    ops.node(i + 1, 0.0, 0.0, z)
"""
    result = import_openseespy_source(source, units=UNITS)

    assert result.error_count == 0
    assert set(result.project.model.nodes) == {1, 2, 3}
    assert result.project.model.nodes[3].xyz[2] == 6.0


def test_safe_import_iterates_zip_for_structural_coordinates():
    source = """
import openseespy.opensees as ops
ops.model('basic', '-ndm', 3, '-ndf', 6)
tags = [1, 2, 3]
zs = [0.0, 3.0, 6.0]
for tag, z in zip(tags, zs):
    ops.node(tag, 0.0, 0.0, z)
"""
    result = import_openseespy_source(source, units=UNITS)

    assert result.error_count == 0
    assert set(result.project.model.nodes) == {1, 2, 3}


def test_safe_import_supports_nested_functions_and_local_scope():
    source = """
import openseespy.opensees as ops

scale = 2.0

def coordinate(i):
    local_scale = 3.0
    return i * local_scale

def build():
    ops.model('basic', '-ndm', 3, '-ndf', 6)
    for i in range(3):
        ops.node(i + 1, 0.0, 0.0, coordinate(i))

build()
ops.node(10, scale, 0.0, 0.0)
"""
    result = import_openseespy_source(source, units=UNITS)

    assert result.error_count == 0
    assert result.project.model.nodes[3].xyz[2] == 6.0
    assert result.project.model.nodes[10].xyz[0] == 2.0


def test_safe_import_supports_if_continue_break_and_augmented_assignment():
    source = """
import openseespy.opensees as ops
ops.model('basic', '-ndm', 3, '-ndf', 6)
tag = 0
for i in range(10):
    if i == 1:
        continue
    if i == 4:
        break
    tag += 1
    ops.node(tag, float(i), 0.0, 0.0)
"""
    result = import_openseespy_source(source, units=UNITS)

    assert result.error_count == 0
    assert set(result.project.model.nodes) == {1, 2, 3}
    assert result.project.model.nodes[3].xyz[0] == 3.0


def test_safe_import_does_not_execute_unknown_function_inside_resolved_if(tmp_path):
    target = tmp_path / "unsafe.txt"
    source = f"""
import openseespy.opensees as ops
ops.model('basic', '-ndm', 3, '-ndf', 6)
if True:
    open({str(target)!r}, 'w').write('unsafe')
ops.node(1, 0.0, 0.0, 0.0)
"""
    result = import_openseespy_source(source, units=UNITS)

    assert not target.exists()
    assert 1 in result.project.model.nodes
    assert result.unsupported_count >= 1


def test_safe_import_reports_unresolved_runtime_if_without_guessing():
    source = """
import openseespy.opensees as ops
ops.model('basic', '-ndm', 3, '-ndf', 6)
if external_runtime_flag:
    ops.node(1, 0.0, 0.0, 0.0)
else:
    ops.node(2, 0.0, 0.0, 0.0)
"""
    result = import_openseespy_source(source, units=UNITS)

    assert not result.project.model.nodes
    assert any(
        issue.construct == "if" and issue.severity == "UNSUPPORTED"
        for issue in result.issues
    )


def test_single_stage_displacement_control_remains_pushover():
    source = """
import openseespy.opensees as ops
ops.model('basic', '-ndm', 2, '-ndf', 3)
ops.node(1, 0.0, 0.0)
ops.node(2, 0.0, 3.0)
ops.fix(1, 1, 1, 1)
ops.timeSeries('Linear', 1)
ops.pattern('Plain', 1, 1)
ops.load(2, 1.0, 0.0, 0.0)
ops.constraints('Plain')
ops.numberer('Plain')
ops.system('BandGeneral')
ops.test('NormUnbalance', 1e-8, 10)
ops.algorithm('Newton')
ops.integrator('DisplacementControl', 2, 1, 0.001)
ops.analysis('Static')
ops.analyze(10)
"""
    result = import_openseespy_source(source, units=UNITS)

    assert result.error_count == 0
    assert len(result.project.analyses) == 1
    analysis = next(iter(result.project.analyses.values()))
    assert analysis.analysis_type == "Pushover"
    assert analysis.integrator == "DisplacementControl"
    assert analysis.preload_gravity is False
    assert analysis.deferred_pattern_tags == []
