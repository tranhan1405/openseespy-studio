from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest

from openseespy_studio.generator import section_to_openseespy, to_openseespy
from openseespy_studio.importer import import_openseespy_source
from openseespy_studio.model import SHELL_ELEMENT_TYPES, StructuralModel
from openseespy_studio.project import ProjectDatabase, SectionData
from openseespy_studio.shell_mesh import ShellMeshSpec, build_shell_mesh
from openseespy_studio.ui.main_window import MainWindow
from openseespy_studio.ui.viewport import ModelViewport
from openseespy_studio.validation import validate_project


def _shell_model(*, corotational: bool = False) -> StructuralModel:
    model = StructuralModel("shell", ndm=3, ndf=6)
    model.add_node(1, 0.0, 0.0, 0.0)
    model.add_node(2, 2.0, 0.0, 0.0)
    model.add_node(3, 2.0, 1.0, 0.0)
    model.add_node(4, 0.0, 1.0, 0.0)
    model.add_element(
        10,
        1,
        2,
        element_type="ASDShellQ4",
        section_tag=7,
        group="shell",
        k=3,
        l=4,
        shell_corotational=corotational,
    )
    return model


def _shell_section(*, rho: float = 0.0) -> SectionData:
    return SectionData(
        7,
        "Elastic shell",
        "ElasticMembranePlate",
        parameters={
            "E": 30.0e9,
            "nu": 0.2,
            "h": 0.18,
            "rho": rho,
            "EpModifier": 1.0,
        },
    )


def test_shell_element_round_trip_preserves_four_node_topology():
    model = _shell_model(corotational=True)

    restored = StructuralModel.from_dict(model.to_dict())
    element = restored.elements[10]

    assert element.element_type == "ASDShellQ4"
    assert element.node_tags() == (1, 2, 3, 4)
    assert element.section_tag == 7
    assert element.transf_tag is None
    assert element.shell_corotational is True
    assert restored.to_dict() == model.to_dict()


def test_shell_requires_3d_six_dof_model_and_four_distinct_nodes():
    model = StructuralModel("2d", ndm=2, ndf=3)
    for tag, x, y in (
        (1, 0.0, 0.0),
        (2, 1.0, 0.0),
        (3, 1.0, 1.0),
        (4, 0.0, 1.0),
    ):
        model.add_node(tag, x, y)

    with pytest.raises(ValueError, match=r"requires a 3D/6DOF model"):
        model.add_element(
            1,
            1,
            2,
            element_type="ASDShellQ4",
            k=3,
            l=4,
        )

    model3d = StructuralModel("3d", ndm=3, ndf=6)
    for tag, xyz in {
        1: (0.0, 0.0, 0.0),
        2: (1.0, 0.0, 0.0),
        3: (1.0, 1.0, 0.0),
    }.items():
        model3d.add_node(tag, *xyz)

    with pytest.raises(ValueError, match=r"four distinct node tags"):
        model3d.add_element(
            1,
            1,
            2,
            element_type="ASDShellQ4",
            k=3,
            l=3,
        )


def test_shell_node_delete_cascades_surface_element():
    model = _shell_model()

    model.remove_node(3, cascade=True)

    assert 3 not in model.nodes
    assert 10 not in model.elements


def test_elastic_membrane_plate_section_validates_and_generates():
    section = _shell_section()

    line = section_to_openseespy(
        section,
        {"length": "m", "force": "N", "time": "s"},
    )[0]

    assert line.startswith(
        "ops.section('ElasticMembranePlateSection', 7, 3e+10, 0.2, 0.18"
    )
    assert line.endswith(", 0, 1)")

    with pytest.raises(ValueError, match=r"Poisson ratio"):
        SectionData(
            8,
            "Bad shell",
            "ElasticMembranePlate",
            parameters={
                "E": 30.0e9,
                "nu": 0.5,
                "h": 0.18,
                "rho": 0.0,
                "EpModifier": 1.0,
            },
        )


def test_shell_generator_emits_asd_shell_q4_without_transformation():
    model = _shell_model(corotational=True)
    section = _shell_section()

    code = to_openseespy(
        model,
        sections={7: section},
        units={"length": "m", "force": "N", "time": "s"},
    )

    assert "# ERROR:" not in code
    assert "ops.geomTransf(" not in code
    assert (
        "ops.element('ASDShellQ4', 10, 1, 2, 3, 4, 7, '-corotational')"
        in code
    )


@pytest.mark.parametrize(
    "formulation",
    sorted(SHELL_ELEMENT_TYPES),
)
def test_all_initial_quad_shell_formulations_generate(formulation: str):
    model = _shell_model()
    model.elements[10].element_type = formulation
    model.elements[10].shell_corotational = False

    code = to_openseespy(
        model,
        sections={7: _shell_section()},
        units={"length": "m", "force": "N", "time": "s"},
    )

    assert (
        f"ops.element('{formulation}', 10, 1, 2, 3, 4, 7)"
        in code
    )


def test_model_check_accepts_shell_without_geometric_transformation():
    project = ProjectDatabase(
        name="shell-check",
        model=_shell_model(),
    )
    project.add_section(_shell_section())
    project.model.set_fixity(1, (1, 1, 1, 1, 1, 1))
    project.model.set_fixity(4, (1, 1, 1, 1, 1, 1))

    issues = validate_project(project)
    shell_errors = [
        issue
        for issue in issues
        if issue.severity == "ERROR"
        and issue.entity_kind == "element"
        and issue.entity_tag == 10
    ]

    assert not shell_errors


def test_shell_section_density_counts_as_dynamic_mass():
    project = ProjectDatabase(
        name="shell-mass",
        model=_shell_model(),
    )
    project.add_section(_shell_section(rho=2500.0))

    holder = SimpleNamespace(
        project=project,
        model=project.model,
    )

    assert MainWindow._has_dynamic_mass(holder) is True


def test_shell_ui_routes_exist_and_are_frame_safe():
    create_source = inspect.getsource(MainWindow._create_shell)
    assert "_ensure_node_count(4" in create_source
    assert "_create_shell_section" in create_source
    assert "ShellElementDialog" in create_source

    tree_source = inspect.getsource(MainWindow._show_tree_context_menu)
    assert 'kind == "surfaces_root"' in tree_source
    assert "is_shell_group" in tree_source
    assert "_assign_shell_section_to_selection" in tree_source

    viewport_source = inspect.getsource(ModelViewport._combined_element_meshes)
    assert "_batched_shell_mesh" in viewport_source
    assert 'combined["shell"]' in viewport_source


def test_shell_generated_script_round_trips_through_importer():
    model = _shell_model(corotational=True)
    script = to_openseespy(
        model,
        sections={7: _shell_section(rho=2500.0)},
        units={"length": "m", "force": "N", "time": "s"},
    )

    imported = import_openseespy_source(
        script,
        source_name="shell-roundtrip.py",
        units={"length": "m", "force": "N", "time": "s"},
    )

    assert imported.error_count == 0
    section = imported.project.sections[7]
    assert section.section_type == "ElasticMembranePlate"
    assert section.parameters["E"] == pytest.approx(30.0e9)
    assert section.parameters["h"] == pytest.approx(0.18)
    assert section.parameters["rho"] == pytest.approx(2500.0)

    element = imported.project.model.elements[10]
    assert element.element_type == "ASDShellQ4"
    assert element.node_tags() == (1, 2, 3, 4)
    assert element.section_tag == 7
    assert element.shell_corotational is True


def test_structured_shell_mesh_reuses_corners_and_builds_quads():
    model = StructuralModel("mesh", ndm=3, ndf=6)
    model.add_node(1, 0.0, 0.0, 0.0)
    model.add_node(2, 4.0, 0.0, 0.0)
    model.add_node(3, 4.0, 2.0, 0.0)
    model.add_node(4, 0.0, 2.0, 0.0)
    project = ProjectDatabase(name="mesh", model=model)
    project.add_section(_shell_section())

    result = build_shell_mesh(
        project,
        ShellMeshSpec(
            corner_nodes=(1, 2, 3, 4),
            divisions_u=2,
            divisions_v=2,
            formulation="ASDShellQ4",
            section_tag=7,
        ),
    )

    assert len(result.element_tags) == 4
    assert len(result.node_tags) == 5
    assert len(project.model.nodes) == 9
    assert len(project.model.elements) == 4
    assert result.grid[0][0] == 1
    assert result.grid[0][-1] == 2
    assert result.grid[-1][-1] == 3
    assert result.grid[-1][0] == 4

    center = project.model.nodes[result.grid[1][1]]
    assert center.xyz == pytest.approx((2.0, 1.0, 0.0))

    for element in project.model.elements.values():
        assert element.element_type == "ASDShellQ4"
        assert len(element.node_tags()) == 4
        assert element.section_tag == 7


def test_structured_shell_mesh_handles_warped_surface_bilinearly():
    model = StructuralModel("warped", ndm=3, ndf=6)
    model.add_node(1, 0.0, 0.0, 0.0)
    model.add_node(2, 2.0, 0.0, 0.0)
    model.add_node(3, 2.0, 2.0, 1.0)
    model.add_node(4, 0.0, 2.0, 0.0)
    project = ProjectDatabase(name="warped", model=model)
    project.add_section(_shell_section())

    result = build_shell_mesh(
        project,
        ShellMeshSpec(
            corner_nodes=(1, 2, 3, 4),
            divisions_u=2,
            divisions_v=2,
            formulation="ASDShellQ4",
            section_tag=7,
        ),
    )

    center = project.model.nodes[result.grid[1][1]]
    assert center.xyz == pytest.approx((1.0, 1.0, 0.25))


def test_shell_mesh_ui_route_is_exposed():
    source = inspect.getsource(MainWindow._create_shell_mesh)
    assert "_ensure_node_count(4" in source
    assert "_create_shell_section" in source
    assert "ShellMeshDialog" in source
    assert "build_shell_mesh" in source

