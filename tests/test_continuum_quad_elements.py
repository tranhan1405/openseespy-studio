from openseespy_studio.generator import to_openseespy
from openseespy_studio.model import StructuralModel
from openseespy_studio.project import NDMaterialData, ProjectDatabase


def _project() -> ProjectDatabase:
    project = ProjectDatabase()
    project.model = StructuralModel(ndm=2, ndf=2)
    project.model.add_node(1, 0.0, 0.0)
    project.model.add_node(2, 2.0, 0.0)
    project.model.add_node(3, 2.0, 1.0)
    project.model.add_node(4, 0.0, 1.0)
    project.add_nd_material(
        NDMaterialData(
            tag=1,
            name="Elastic continuum",
            material_type="ElasticIsotropic",
            parameters={"E": 30.0e9, "nu": 0.2, "rho": 0.0},
        )
    )
    return project


def test_four_node_quad_round_trip_and_generation():
    project = _project()
    project.model.add_element(
        1,
        1,
        2,
        element_type="quad",
        k=3,
        l=4,
        group="continuum-2d",
        continuum_thickness=0.25,
        continuum_material_tag=1,
        continuum_type="PlaneStress",
        continuum_pressure=4.5,
        continuum_density=2.4,
        continuum_body_force=(0.0, -9.81),
    )
    project.validate_element_state(1)

    restored = ProjectDatabase.from_dict(project.to_dict())
    element = restored.model.elements[1]
    assert element.element_type == "quad"
    assert element.continuum_material_tag == 1
    assert element.continuum_type == "PlaneStress"
    assert element.continuum_body_force == (0.0, -9.81)

    script = to_openseespy(
        restored.model,
        nd_materials=restored.nd_materials,
        units=restored.units,
    )
    assert (
        "ops.element('quad', 1, 1, 2, 3, 4, 0.25, "
        "'PlaneStress', 1, 4.5, 2.4, 0, -9.81)"
    ) in script


def test_sspquad_generation():
    project = _project()
    project.model.add_element(
        2,
        1,
        2,
        element_type="SSPquad",
        k=3,
        l=4,
        continuum_thickness=0.3,
        continuum_material_tag=1,
        continuum_type="PlaneStrain",
        continuum_body_force=(1.2, -3.4),
    )
    project.validate_element_state(2)

    script = to_openseespy(
        project.model,
        nd_materials=project.nd_materials,
        units=project.units,
    )
    assert (
        "ops.element('SSPquad', 2, 1, 2, 3, 4, 1, "
        "'PlaneStrain', 0.3, 1.2, -3.4)"
    ) in script


def test_continuum_quad_requires_2d_2dof_and_ccw_order():
    model = StructuralModel(ndm=2, ndf=3)
    for tag, xy in enumerate(((0, 0), (1, 0), (1, 1), (0, 1)), 1):
        model.add_node(tag, *xy)
    try:
        model.add_element(
            1, 1, 2, element_type="quad", k=3, l=4,
            continuum_material_tag=1,
        )
    except ValueError as exc:
        assert "ndm=2/ndf=2" in str(exc)
    else:
        raise AssertionError("quad accepted invalid model signature")

    model = StructuralModel(ndm=2, ndf=2)
    for tag, xy in enumerate(((0, 0), (1, 0), (1, 1), (0, 1)), 1):
        model.add_node(tag, *xy)
    try:
        model.add_element(
            1, 1, 4, element_type="quad", k=3, l=2,
            continuum_material_tag=1,
        )
    except ValueError as exc:
        assert "counter-clockwise" in str(exc)
    else:
        raise AssertionError("quad accepted clockwise node order")
