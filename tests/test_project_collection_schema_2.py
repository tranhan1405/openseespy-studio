import pytest

from openseespy_studio.project import ProjectDatabase


def test_time_series_loader_rejects_nonobject_item():
    with pytest.raises(ValueError, match=r"Time series item 0 must be an object"):
        ProjectDatabase._load_time_series([1])


def test_load_patterns_loader_rejects_nonlist_container():
    with pytest.raises(ValueError, match=r"Load patterns must be a list"):
        ProjectDatabase._load_patterns({})


def test_load_patterns_loader_rejects_nonobject_item():
    with pytest.raises(ValueError, match=r"Load pattern item 0 must be an object"):
        ProjectDatabase._load_patterns([1])


def test_nodal_loads_loader_rejects_nonlist_container():
    with pytest.raises(ValueError, match=r"Nodal loads must be a list"):
        ProjectDatabase._load_nodal_loads({})


def test_nodal_loads_loader_rejects_nonobject_item():
    with pytest.raises(ValueError, match=r"Nodal load item 0 must be an object"):
        ProjectDatabase._load_nodal_loads([1])
