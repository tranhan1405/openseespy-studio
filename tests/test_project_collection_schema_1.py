import pytest

from openseespy_studio.project import ProjectDatabase


def test_constraints_loader_rejects_nonlist_container():
    with pytest.raises(ValueError, match=r"Constraints must be a list"):
        ProjectDatabase._load_constraints({})


def test_constraints_loader_rejects_nonobject_item():
    with pytest.raises(ValueError, match=r"Constraint item 0 must be an object"):
        ProjectDatabase._load_constraints([1])


def test_connections_loader_rejects_nonlist_container():
    with pytest.raises(ValueError, match=r"Connections must be a list"):
        ProjectDatabase._load_connections({})


def test_connections_loader_rejects_nonobject_item():
    with pytest.raises(ValueError, match=r"Connection item 0 must be an object"):
        ProjectDatabase._load_connections([1])


def test_time_series_loader_rejects_nonlist_container():
    with pytest.raises(ValueError, match=r"Time series must be a list"):
        ProjectDatabase._load_time_series({})
