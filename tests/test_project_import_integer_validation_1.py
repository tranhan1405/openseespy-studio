import pytest

from openseespy_studio.project import (
    PROJECT_FORMAT,
    PROJECT_FORMAT_VERSION,
    ProjectDatabase,
)


def _project_data(**overrides):
    data = {
        "format": PROJECT_FORMAT,
        "version": PROJECT_FORMAT_VERSION,
    }
    data.update(overrides)
    return data


def test_project_import_rejects_fractional_version():
    with pytest.raises(ValueError, match=r"Project version must be an integer"):
        ProjectDatabase.from_dict(_project_data(version=1.5))


def test_project_import_rejects_fractional_active_analysis_tag():
    with pytest.raises(
        ValueError,
        match=r"Active analysis tag must be an integer",
    ):
        ProjectDatabase.from_dict(
            _project_data(active_analysis_tag=1.5)
        )


def test_project_import_rejects_stale_active_analysis_reference():
    with pytest.raises(
        ValueError,
        match=r"Active analysis tag 1 does not exist",
    ):
        ProjectDatabase.from_dict(
            _project_data(active_analysis_tag=1)
        )


def test_legacy_material_loader_rejects_fractional_key():
    with pytest.raises(
        ValueError,
        match=r"Legacy material tag must be an integer",
    ):
        ProjectDatabase._load_materials({"1.5": {}})


def test_legacy_section_loader_rejects_fractional_key():
    with pytest.raises(
        ValueError,
        match=r"Legacy section tag must be an integer",
    ):
        ProjectDatabase._load_sections({"1.5": {}})
