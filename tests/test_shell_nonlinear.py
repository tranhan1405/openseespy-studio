import pytest

from openseespy_studio.generator import (
    nd_material_to_openseespy,
    section_to_openseespy,
    to_openseespy,
)
from openseespy_studio.mass_source import evaluate_mass_source
from openseespy_studio.model import StructuralModel
from openseespy_studio.project import (
    MassSourceData,
    NDMaterialData,
    ProjectDatabase,
    SectionData,
    ShellLayerData,
)


def _shell_model(section_tag: int = 1) -> StructuralModel:
    model = StructuralModel("nonlinear-shell")
    model.add_node(1, 0.0, 0.0, 0.0)
    model.add_node(2, 2.0, 0.0, 0.0)
    model.add_node(3, 2.0, 1.0, 0.0)
    model.add_node(4, 0.0, 1.0, 0.0)
    model.add_element(
        1,
        1,
        2,
        element_type="ASDShellQ4",
        section_tag=section_tag,
        group="shell",
        k=3,
        l=4,
    )
    return model


def test_nd_material_round_trip_and_section_dependency_guards():
    project = ProjectDatabase(model=_shell_model())
    material = NDMaterialData(
        1,
        "Elastic plate",
        "ElasticIsotropic",
        parameters={"E": 30.0e9, "nu": 0.2, "rho": 2400.0},
    )
    project.add_nd_material(material)
    section = SectionData(
        1,
        "Plate fiber",
        "PlateFiber",
        parameters={"h": 0.20},
        nd_material_tag=1,
    )
    project.add_section(section)

    restored = ProjectDatabase.from_dict(project.to_dict())
    assert restored.nd_materials[1].parameters["E"] == pytest.approx(30.0e9)
    assert restored.sections[1].nd_material_tag == 1

    with pytest.raises(ValueError, match="referenced by Shell section"):
        restored.remove_nd_material(1)


def test_layered_shell_round_trip_and_total_thickness():
    project = ProjectDatabase()
    project.add_nd_material(
        NDMaterialData(
            1,
            "Layer A",
            "ElasticIsotropic",
            parameters={"E": 25.0e9, "nu": 0.2, "rho": 2200.0},
        )
    )
    project.add_nd_material(
        NDMaterialData(
            2,
            "Layer B",
            "ElasticIsotropic",
            parameters={"E": 200.0e9, "nu": 0.3, "rho": 7850.0},
        )
    )
    section = SectionData(
        3,
        "Two layer",
        "LayeredShell",
        shell_layers=[
            ShellLayerData(1, 0.08),
            ShellLayerData(2, 0.02),
        ],
    )
    project.add_section(section)

    restored = ProjectDatabase.from_dict(project.to_dict())
    assert restored.sections[3].shell_total_thickness() == pytest.approx(0.10)
    assert restored.sections[3].shell_nd_material_tags() == {1, 2}


def test_nonlinear_shell_generator_orders_nd_material_before_section():
    model = _shell_model()
    nd_materials = {
        1: NDMaterialData(
            1,
            "Elastic isotropic",
            "ElasticIsotropic",
            parameters={"E": 30.0e9, "nu": 0.2, "rho": 2400.0},
        )
    }
    sections = {
        1: SectionData(
            1,
            "PlateFiber",
            "PlateFiber",
            parameters={"h": 0.15},
            nd_material_tag=1,
        )
    }

    code = to_openseespy(
        model,
        sections=sections,
        nd_materials=nd_materials,
        units={"length": "m", "force": "N", "time": "s"},
    )

    nd_line = "ops.nDMaterial('ElasticIsotropic', 1, 3e+10, 0.2, 2400)"
    section_line = "ops.section('PlateFiber', 1, 1, 0.15)"
    element_line = "ops.element('ASDShellQ4', 1, 1, 2, 3, 4, 1)"
    assert nd_line in code
    assert section_line in code
    assert element_line in code
    assert code.index(nd_line) < code.index(section_line) < code.index(element_line)


def test_layered_shell_generator_emits_layer_pairs():
    nd_materials = {
        1: NDMaterialData(
            1,
            "A",
            "ElasticIsotropic",
            parameters={"E": 20.0e9, "nu": 0.2, "rho": 2000.0},
        ),
        2: NDMaterialData(
            2,
            "B",
            "ElasticIsotropic",
            parameters={"E": 200.0e9, "nu": 0.3, "rho": 7800.0},
        ),
    }
    section = SectionData(
        7,
        "Layers",
        "LayeredShell",
        shell_layers=[
            ShellLayerData(1, 0.08),
            ShellLayerData(2, 0.02),
        ],
    )
    line = section_to_openseespy(
        section,
        units={"length": "m", "force": "N", "time": "s"},
        nd_materials=nd_materials,
    )[0]
    assert line == "ops.section('LayeredShell', 7, 2, 1, 0.08, 2, 0.02)"


@pytest.mark.parametrize(
    ("section", "expected_mass"),
    [
        (
            SectionData(
                1,
                "Plate",
                "PlateFiber",
                parameters={"h": 0.10},
                nd_material_tag=1,
            ),
            2400.0 * 0.10 * 2.0,
        ),
        (
            SectionData(
                1,
                "Layers",
                "LayeredShell",
                shell_layers=[
                    ShellLayerData(1, 0.08),
                    ShellLayerData(2, 0.02),
                ],
            ),
            (2400.0 * 0.08 + 7850.0 * 0.02) * 2.0,
        ),
    ],
)
def test_mass_source_includes_nonlinear_shell_density(section, expected_mass):
    project = ProjectDatabase(model=_shell_model())
    project.units = {"length": "m", "force": "N", "time": "s"}
    project.add_nd_material(
        NDMaterialData(
            1,
            "Concrete-like",
            "ElasticIsotropic",
            parameters={"E": 30.0e9, "nu": 0.2, "rho": 2400.0},
        )
    )
    project.add_nd_material(
        NDMaterialData(
            2,
            "Steel-like",
            "ElasticIsotropic",
            parameters={"E": 200.0e9, "nu": 0.3, "rho": 7850.0},
        )
    )
    project.add_section(section)

    summary = evaluate_mass_source(
        project,
        MassSourceData(
            1,
            "Shell self mass",
            include_self_mass=True,
            load_factors={},
            gravity_axis=3,
            directions=(1, 2),
        ),
    )
    assert summary.self_mass == pytest.approx(expected_mass)
    assert sum(summary.nodal_mass.values()) == pytest.approx(expected_mass)
