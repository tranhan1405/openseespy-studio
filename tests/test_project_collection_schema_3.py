import pytest

from openseespy_studio.project import ProjectDatabase


def test_prescribed_displacements_loader_rejects_nonlist_container():
    with pytest.raises(ValueError, match=r"Prescribed displacements must be a list"):
        ProjectDatabase._load_prescribed_displacements({})


def test_prescribed_displacements_loader_rejects_nonobject_item():
    with pytest.raises(
        ValueError,
        match=r"Prescribed displacement item 0 must be an object",
    ):
        ProjectDatabase._load_prescribed_displacements([1])


def test_element_loads_loader_rejects_nonlist_container():
    with pytest.raises(ValueError, match=r"Element loads must be a list"):
        ProjectDatabase._load_element_loads({})


def test_element_loads_loader_rejects_nonobject_item():
    with pytest.raises(ValueError, match=r"Element load item 0 must be an object"):
        ProjectDatabase._load_element_loads([1])


def test_mass_sources_loader_rejects_nonlist_container():
    with pytest.raises(ValueError, match=r"Mass sources must be a list"):
        ProjectDatabase._load_mass_sources({})
