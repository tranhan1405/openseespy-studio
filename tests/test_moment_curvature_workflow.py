from __future__ import annotations

import pytest

from openseespy_studio.generator import to_openseespy
from openseespy_studio.model import StructuralModel
from openseespy_studio.moment_curvature import (
    MomentCurvatureSpec,
    build_moment_curvature_project,
)
from openseespy_studio.project import ProjectDatabase, SectionData


def _project(*, ndm: int, ndf: int) -> ProjectDatabase:
    project = ProjectDatabase(
        name="Research model",
        model=StructuralModel("Research model", ndm=ndm, ndf=ndf),
        units={"length": "m", "force": "kN", "time": "s"},
    )
    project.add_section(
        SectionData(
            7,
            "Test section",
            "Elastic",
            parameters={
                "E": 30.0e9,
                "A": 0.16,
                "Iz": 0.002,
                "Iy": 0.0015,
                "G": 12.0e9,
                "J": 0.0004,
            },
        )
    )
    return project


def _script(project: ProjectDatabase) -> str:
    return to_openseespy(
        project.model,
        project.materials,
        project.sections,
        project.transformations,
        project.constraints,
        project.connections,
        project.time_series,
        project.load_patterns,
        project.nodal_loads,
        project.analyses,
        project.active_analysis_tag,
        element_loads=project.element_loads,
        prescribed_displacements=project.prescribed_displacements,
        recorders=project.recorders,
        units=project.units,
        solution_results=project.solution_results,
    )


def test_build_2d_moment_curvature_project_is_isolated_and_recognized():
    source = _project(ndm=2, ndf=3)
    source.model.add_node(99, 3.0, 4.0)

    test_project = build_moment_curvature_project(
        source,
        MomentCurvatureSpec(
            section_tag=7,
            axis="Mz",
            axial_load=-900.0,
            max_curvature=0.03,
            increments=120,
        ),
    )

    assert set(source.model.nodes) == {99}
    assert set(test_project.model.nodes) == {1, 2}
    assert test_project.model.nodes[1].fixity == (1, 1, 1)
    assert test_project.model.nodes[2].fixity == (0, 1, 0)

    connection = test_project.connections[1]
    assert connection.connection_type == "zeroLengthSection"
    assert connection.section_tag == 7

    axial = test_project.nodal_loads[1]
    assert axial.values[:3] == pytest.approx((-900.0, 0.0, 0.0))
    driver = test_project.nodal_loads[2]
    assert driver.values[:3] == pytest.approx((0.0, 0.0, 1.0))

    analysis = test_project.analyses[1]
    assert analysis.analysis_type == "Static"
    assert analysis.integrator == "DisplacementControl"
    assert analysis.control_node == 2
    assert analysis.control_dof == 3
    assert analysis.steps == 120
    assert analysis.displacement_increment == pytest.approx(0.03 / 120)
    assert analysis.preload_gravity is True
    assert analysis.gravity_steps == 1
    assert analysis.deferred_pattern_tags == [2]

    script = _script(test_project)
    assert "ops.element('zeroLengthSection', 1, 1, 2, 7" in script
    assert "ops.load(2, -900, 0, 0)" in script
    assert "ops.load(2, 0, 0, 1)" in script
    assert "ops.integrator('DisplacementControl', 2, 3," in script
    assert "'kind': 'moment-curvature'" in script
    assert "_studio_moment_curvature_spec" in script


def test_3d_axis_changes_control_rotation_and_reference_moment():
    source = _project(ndm=3, ndf=6)

    my_project = build_moment_curvature_project(
        source,
        MomentCurvatureSpec(
            section_tag=7,
            axis="My",
            max_curvature=0.01,
            increments=50,
        ),
    )
    assert my_project.model.nodes[2].fixity == (0, 1, 1, 1, 0, 1)
    assert my_project.analyses[1].control_dof == 5
    assert my_project.nodal_loads[2].values == pytest.approx(
        (0.0, 0.0, 0.0, 0.0, 1.0, 0.0)
    )

    mz_project = build_moment_curvature_project(
        source,
        MomentCurvatureSpec(
            section_tag=7,
            axis="Mz",
            max_curvature=0.01,
            increments=50,
        ),
    )
    assert mz_project.model.nodes[2].fixity == (0, 1, 1, 1, 1, 0)
    assert mz_project.analyses[1].control_dof == 6
    assert mz_project.nodal_loads[2].values == pytest.approx(
        (0.0, 0.0, 0.0, 0.0, 0.0, 1.0)
    )


def test_2d_rejects_my_axis():
    source = _project(ndm=2, ndf=3)

    with pytest.raises(ValueError, match="only the Mz"):
        build_moment_curvature_project(
            source,
            MomentCurvatureSpec(
                section_tag=7,
                axis="My",
                max_curvature=0.01,
                increments=20,
            ),
        )
