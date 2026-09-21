import pytest

from openseespy_studio.project import ProjectDatabase


def test_mass_sources_loader_rejects_nonobject_item():
    with pytest.raises(ValueError, match=r"Mass source item 0 must be an object"):
        ProjectDatabase._load_mass_sources([1])


def test_analyses_loader_rejects_nonlist_container():
    with pytest.raises(ValueError, match=r"Analyses must be a list"):
        ProjectDatabase._load_analyses({})


def test_analyses_loader_rejects_nonobject_item():
    with pytest.raises(ValueError, match=r"Analysis item 0 must be an object"):
        ProjectDatabase._load_analyses([1])


def test_solution_results_loader_rejects_nonlist_container():
    with pytest.raises(ValueError, match=r"Solution results must be a list"):
        ProjectDatabase._load_solution_results({})


def test_solution_results_loader_rejects_nonobject_item():
    with pytest.raises(ValueError, match=r"Solution result item 0 must be an object"):
        ProjectDatabase._load_solution_results([1])
