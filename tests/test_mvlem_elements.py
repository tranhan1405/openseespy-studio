from openseespy_studio.generator import (
    material_to_openseespy,
    nd_material_to_openseespy,
    to_openseespy,
)
from openseespy_studio.model import StructuralModel
from openseespy_studio.project import (
    MaterialData,
    NDMaterialData,
    ProjectDatabase,
)


def _materials(project: ProjectDatabase) -> None:
    project.add_material(
        MaterialData(
            1, "Steel X", "Steel02",
            {"Fy": 500e6, "E0": 200e9, "b": 0.01},
        )
    )
    project.add_material(
        MaterialData(
            2, "Steel Y", "Steel02",
            {"Fy": 500e6, "E0": 200e9, "b": 0.01},
        )
    )
    project.add_material(
        MaterialData(
            3, "Concrete CM", "ConcreteCM",
            {
                "fpcc": -30e6, "epcc": -0.002, "Ec": 30e9,
                "rc": 7.0, "xcrn": 1.02, "ft": 3e6,
                "et": 0.0001, "rt": 1.2, "xcrp": 10000.0,
                "GapClose": 0.0,
            },
        )
    )
    project.add_material(
        MaterialData(4, "Shear", "Elastic", {"E": 12e9})
    )


def _fsam(project: ProjectDatabase, tag: int = 10) -> None:
    project.add_nd_material(
        NDMaterialData(
            tag, f"FSAM {tag}", "FSAM",
            {
                "rho": 0.0, "sX": 1, "sY": 2, "conc": 3,
                "rouX": 0.01, "rouY": 0.01,
                "nu": 0.35, "alfadow": 0.005,
            },
        )
    )


def test_concrete_cm_and_fsam_generators():
    project = ProjectDatabase()
    _materials(project)
    _fsam(project)
    concrete = material_to_openseespy(
        project.materials[3],
        {"length": "m", "force": "N", "time": "s"},
    )
    assert "ops.uniaxialMaterial('ConcreteCM', 3" in concrete
    assert "'-GapClose', 0" in concrete
    fsam = nd_material_to_openseespy(
        project.nd_materials[10],
        {"length": "m", "force": "N", "time": "s"},
    )
    assert fsam == (
        "ops.nDMaterial('FSAM', 10, 0, 1, 2, 3, "
        "0.01, 0.01, 0.35, 0.005)"
    )


def test_fsam_requires_concrete_cm_dependency():
    project = ProjectDatabase()
    project.add_material(MaterialData(1, "SX", "Elastic", {"E": 200e9}))
    project.add_material(MaterialData(2, "SY", "Elastic", {"E": 200e9}))
    project.add_material(MaterialData(3, "Wrong", "Concrete02"))
    material = NDMaterialData(
        10, "Bad FSAM", "FSAM",
        {
            "sX": 1, "sY": 2, "conc": 3,
            "rouX": 0.01, "rouY": 0.01,
            "nu": 0.35, "alfadow": 0.005,
        },
    )
    try:
        project.add_nd_material(material)
    except ValueError as exc:
        assert "ConcreteCM" in str(exc)
    else:
        raise AssertionError("FSAM accepted a non-ConcreteCM concrete tag")


def _mvlem_project() -> ProjectDatabase:
    project = ProjectDatabase()
    project.model = StructuralModel(ndm=2, ndf=3)
    project.model.add_node(1, 0.0, 0.0)
    project.model.add_node(2, 0.0, 3.0)
    _materials(project)
    return project


def test_mvlem_generation():
    project = _mvlem_project()
    project.model.add_element(
        1, 1, 2, element_type="MVLEM", group="rc-wall-macro",
        wall_center_ratio=0.4, wall_density=0.0,
        wall_thicknesses=(0.2, 0.2, 0.2, 0.2),
        wall_widths=(0.5, 0.5, 0.5, 0.5),
        wall_rhos=(0.02, 0.01, 0.01, 0.02),
        wall_concrete_tags=(3, 3, 3, 3),
        wall_steel_tags=(1, 1, 1, 1),
        wall_shear_tag=4,
    )
    project.validate_element_state(1)
    script = to_openseespy(
        project.model,
        materials=project.materials,
        nd_materials=project.nd_materials,
        units=project.units,
    )
    assert (
        "ops.element('MVLEM', 1, 0, 1, 2, 4, 0.4, "
        "'-thick', 0.2, 0.2, 0.2, 0.2, "
        "'-width', 0.5, 0.5, 0.5, 0.5"
    ) in script
    assert "'-matShear', 4)" in script


def test_sfi_mvlem_generation_with_fsam():
    project = _mvlem_project()
    for tag in range(10, 14):
        _fsam(project, tag)
    project.model.add_element(
        2, 1, 2, element_type="SFI_MVLEM", group="rc-wall-macro",
        wall_center_ratio=0.4,
        wall_thicknesses=(0.2, 0.2, 0.2, 0.2),
        wall_widths=(0.5, 0.5, 0.5, 0.5),
        wall_nd_material_tags=(10, 11, 12, 13),
    )
    project.validate_element_state(2)
    script = to_openseespy(
        project.model,
        materials=project.materials,
        nd_materials=project.nd_materials,
        units=project.units,
    )
    assert (
        "ops.element('SFI_MVLEM', 2, 1, 2, 4, 0.4, "
        "'-thick', 0.2, 0.2, 0.2, 0.2, "
        "'-width', 0.5, 0.5, 0.5, 0.5, "
        "'-mat', 10, 11, 12, 13)"
    ) in script


def test_mvlem_3d_generation_and_round_trip():
    project = ProjectDatabase()
    project.model = StructuralModel(ndm=3, ndf=6)
    for tag, xyz in enumerate(
        (
            (0.0, 0.0, 0.0), (2.0, 0.0, 0.0),
            (2.0, 0.0, 3.0), (0.0, 0.0, 3.0),
        ),
        1,
    ):
        project.model.add_node(tag, *xyz)
    _materials(project)
    project.model.add_element(
        3, 1, 2, element_type="MVLEM_3D", k=3, l=4,
        group="rc-wall-macro", wall_center_ratio=0.4,
        wall_density=0.0, wall_thicknesses=(0.2, 0.2),
        wall_widths=(1.0, 1.0), wall_rhos=(0.015, 0.015),
        wall_concrete_tags=(3, 3), wall_steel_tags=(1, 1),
        wall_shear_tag=4, wall_thick_mod=0.63, wall_poisson=0.25,
    )
    project.validate_element_state(3)
    restored = ProjectDatabase.from_dict(project.to_dict())
    element = restored.model.elements[3]
    assert element.element_type == "MVLEM_3D"
    assert element.node_tags() == (1, 2, 3, 4)
    assert element.wall_widths == (1.0, 1.0)
    script = to_openseespy(
        restored.model,
        materials=restored.materials,
        nd_materials=restored.nd_materials,
        units=restored.units,
    )
    assert "ops.element('MVLEM_3D', 3, 1, 2, 3, 4, 2" in script
    assert "'-ThickMod', 0.63, '-Poisson', 0.25" in script


def test_mvlem_dimension_guards():
    model = StructuralModel(ndm=3, ndf=6)
    model.add_node(1, 0, 0, 0)
    model.add_node(2, 0, 0, 3)
    try:
        model.add_element(
            1, 1, 2, element_type="MVLEM",
            wall_thicknesses=(0.2, 0.2),
            wall_widths=(1.0, 1.0),
            wall_rhos=(0.01, 0.01),
            wall_concrete_tags=(1, 1),
            wall_steel_tags=(2, 2),
            wall_shear_tag=3,
        )
    except ValueError as exc:
        assert "ndm=2/ndf=3" in str(exc)
    else:
        raise AssertionError("MVLEM accepted a 3D/6DOF model")
