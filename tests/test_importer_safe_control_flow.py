import math

import pytest

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

def test_safe_import_recovers_constant_namespace_class():
    source = """
import openseespy.opensees as op

class constants:
    def __init__(self):
        self.FREE = 0
        self.FIXED = 1
        self.X = 1

opc = constants()
op.model('basic', '-ndm', 2, '-ndf', 3)
op.node(1, 0.0, 0.0)
op.node(2, 0.0, 0.0)
op.fix(1, opc.FIXED, opc.FIXED, opc.FIXED)
op.fix(2, opc.FREE, opc.FIXED, opc.FIXED)
"""
    result = import_openseespy_source(source, units=UNITS)

    assert result.error_count == 0
    assert set(result.project.model.nodes) == {1, 2}
    assert result.project.model.nodes[1].fixity == (1, 1, 1)
    assert result.project.model.nodes[2].fixity == (0, 1, 1)
    assert result.imported_counts["Constant namespaces"] == 1


def test_safe_import_reads_wrapped_nonlinear_sdof_with_external_signal():
    source = """
import requests
import eqsig
import matplotlib.pyplot as plt
import numpy as np
from os.path import exists
import openseespy.opensees as op

class opensees_constants:
    def __init__(self):
        self.FREE = 0
        self.FIXED = 1
        self.X = 1
        self.Y = 2
        self.ROTZ = 3

opc = opensees_constants()

def get_inelastic_response(
    mass, k_spring, f_yield, motion, dt, xi=0.05, r_post=0.0
):
    op.wipe()
    op.model('basic', '-ndm', 2, '-ndf', 3)
    bot_node = 1
    top_node = 2
    op.node(bot_node, 0.0, 0.0)
    op.node(top_node, 0.0, 0.0)
    op.fix(top_node, opc.FREE, opc.FIXED, opc.FIXED)
    op.fix(bot_node, opc.FIXED, opc.FIXED, opc.FIXED)
    op.equalDOF(1, 2, *[2, 3])
    op.mass(top_node, mass, 0.0, 0.0)

    bilinear_mat_tag = 1
    op.uniaxialMaterial(
        'Steel01', bilinear_mat_tag, f_yield, k_spring, r_post
    )
    op.element(
        'zeroLength', 1, bot_node, top_node,
        '-mat', bilinear_mat_tag, '-dir', 1, '-doRayleigh', 1
    )

    values = list(-1 * motion)
    op.timeSeries('Path', 1, '-dt', dt, '-values', *values)
    op.pattern('UniformExcitation', 1, opc.X, '-accel', 1)

    op.wipeAnalysis()
    op.algorithm('Newton')
    op.system('SparseGeneral')
    op.numberer('RCM')
    op.constraints('Transformation')
    op.integrator('Newmark', 0.5, 0.25)
    op.analysis('Transient')
    op.test('EnergyIncr', 1.0e-10, 10, 0, 2)

    analysis_time = (len(values) - 1) * dt
    analysis_dt = 0.001
    outputs = {
        'time': [],
        'rel_disp': [],
        'rel_accel': [],
        'rel_vel': [],
        'force': [],
    }
    while op.getTime() < analysis_time:
        curr_time = op.getTime()
        op.analyze(1, analysis_dt)
        outputs['time'].append(curr_time)
        outputs['rel_disp'].append(op.nodeDisp(top_node, 1))
        outputs['rel_vel'].append(op.nodeVel(top_node, 1))
        outputs['rel_accel'].append(op.nodeAccel(top_node, 1))
        op.reactions()
        outputs['force'].append(-op.nodeReaction(bot_node, 1))
    op.wipe()
    return outputs

def show_single_comparison(acc_signal):
    rec = acc_signal.values
    motion_step = acc_signal.dt
    period = 1.0
    xi = 0.05
    mass = 1.0
    f_yield = 1.5
    r_post = 0.0
    k_spring = 4 * np.pi ** 2 * mass / period ** 2
    outputs = get_inelastic_response(
        mass, k_spring, f_yield,
        motion=rec, dt=motion_step, xi=xi, r_post=r_post
    )
    outputs_elastic = get_inelastic_response(
        mass, k_spring, f_yield * 100,
        rec, motion_step, xi=xi, r_post=r_post
    )

if __name__ == '__main__':
    if exists('test_motion_dt0p01.txt'):
        eq_motion = []
    else:
        response = requests.get('https://example.invalid/motion.txt')
        eq_motion = response.text
    eq_motion_dt = 0.01
    acc_signal = eqsig.AccSignal(eq_motion, eq_motion_dt)
    show_single_comparison(acc_signal)
"""
    result = import_openseespy_source(source, units=UNITS)

    assert result.error_count == 0, [
        (issue.severity, issue.line, issue.construct, issue.message)
        for issue in result.issues
    ]
    assert set(result.project.model.nodes) == {1, 2}
    assert result.project.model.nodes[2].mass[:3] == (1.0, 0.0, 0.0)

    material = result.project.materials[1]
    assert material.material_type == "Steel01"
    assert material.parameters["Fy"] == 1.5
    assert material.parameters["E0"] == pytest.approx(4 * math.pi ** 2)
    assert material.parameters["b"] == 0.0

    connection = result.project.connections[1]
    assert connection.connection_type == "zeroLength"

    analysis = next(iter(result.project.analyses.values()))
    assert analysis.analysis_type == "Transient"
    assert analysis.integrator == "Newmark"
    assert analysis.dt == pytest.approx(0.001)
    assert analysis.steps == 1

    probes = [
        item
        for item in result.project.solution_results.values()
        if bool(item.settings.get("probe", False))
    ]
    quantities = {
        str(item.settings.get("quantity"))
        for item in probes
    }
    assert quantities >= {
        "Displacement",
        "Velocity",
        "Acceleration",
        "Reaction",
    }

    assert not result.project.time_series
    assert not result.project.load_patterns
    assert any(
        issue.construct == "eqsig.AccSignal"
        for issue in result.issues
    )
    assert any(
        issue.construct == "Transient duration"
        for issue in result.issues
    )
    assert any(
        issue.construct == "repeated model builder"
        for issue in result.issues
    )

