import pytest

from openseespy_studio.project import AnalysisSettingsData


def test_analysis_rejects_fractional_tag_on_create_and_load():
    with pytest.raises(
        ValueError,
        match=r"Analysis tag must be an integer",
    ):
        AnalysisSettingsData(
            1.5,
            "Static",
            "Static",
        )

    with pytest.raises(
        ValueError,
        match=r"Analysis tag must be an integer",
    ):
        AnalysisSettingsData.from_dict(
            {
                "tag": 1.5,
                "name": "Static",
                "analysis_type": "Static",
            }
        )


def test_static_analysis_rejects_fractional_max_iterations():
    with pytest.raises(
        ValueError,
        match=r"Analysis max iterations must be an integer",
    ):
        AnalysisSettingsData(
            2,
            "Static",
            "Static",
            max_iterations=20.5,
        )

    with pytest.raises(
        ValueError,
        match=r"Analysis max iterations must be an integer",
    ):
        AnalysisSettingsData.from_dict(
            {
                "tag": 2,
                "name": "Static",
                "analysis_type": "Static",
                "max_iterations": 20.5,
            }
        )


def test_step_driven_analysis_rejects_fractional_steps():
    with pytest.raises(
        ValueError,
        match=r"Analysis steps must be an integer",
    ):
        AnalysisSettingsData(
            3,
            "Transient",
            "Transient",
            steps=10.5,
            dt=0.01,
        )

    with pytest.raises(
        ValueError,
        match=r"Analysis steps must be an integer",
    ):
        AnalysisSettingsData.from_dict(
            {
                "tag": 3,
                "name": "Transient",
                "analysis_type": "Transient",
                "steps": 10.5,
                "dt": 0.01,
            }
        )


def test_gravity_preload_rejects_fractional_step_count():
    with pytest.raises(
        ValueError,
        match=r"Analysis gravity steps must be an integer",
    ):
        AnalysisSettingsData(
            4,
            "Gravity preload",
            "Static",
            preload_gravity=True,
            gravity_steps=5.5,
        )

    with pytest.raises(
        ValueError,
        match=r"Analysis gravity steps must be an integer",
    ):
        AnalysisSettingsData.from_dict(
            {
                "tag": 4,
                "name": "Gravity preload",
                "analysis_type": "Static",
                "preload_gravity": True,
                "gravity_steps": 5.5,
            }
        )


def test_modal_analysis_rejects_fractional_mode_count():
    with pytest.raises(
        ValueError,
        match=r"Analysis number of modes must be an integer",
    ):
        AnalysisSettingsData(
            5,
            "Modes",
            "Modal",
            num_modes=3.5,
        )

    with pytest.raises(
        ValueError,
        match=r"Analysis number of modes must be an integer",
    ):
        AnalysisSettingsData.from_dict(
            {
                "tag": 5,
                "name": "Modes",
                "analysis_type": "Modal",
                "num_modes": 3.5,
            }
        )
