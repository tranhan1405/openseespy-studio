from __future__ import annotations

import inspect
from types import SimpleNamespace

from openseespy_studio.ui.main_window import MainWindow


class _PrerequisiteHolder:
    _ensure_prerequisite = MainWindow._ensure_prerequisite

    def __init__(self, *, answer: bool = True):
        self.answer = bool(answer)
        self.prompt_calls = []
        self.created = 0
        self.available = False

    def _ask_create_prerequisite(
        self,
        *,
        title: str,
        message: str,
        action_label: str,
    ) -> bool:
        self.prompt_calls.append((title, message, action_label))
        return self.answer

    def create(self) -> None:
        self.created += 1
        self.available = True


def test_ensure_prerequisite_creates_and_resumes():
    holder = _PrerequisiteHolder(answer=True)

    ready = holder._ensure_prerequisite(
        title="Frame",
        message="Need a Section",
        action_label="Create Section Now...",
        available=lambda: holder.available,
        creator=holder.create,
    )

    assert ready is True
    assert holder.created == 1
    assert holder.prompt_calls[0][2] == "Create Section Now..."


def test_ensure_prerequisite_cancel_does_not_create():
    holder = _PrerequisiteHolder(answer=False)

    ready = holder._ensure_prerequisite(
        title="Frame",
        message="Need a Section",
        action_label="Create Section Now...",
        available=lambda: holder.available,
        creator=holder.create,
    )

    assert ready is False
    assert holder.created == 0


class _NodeHolder:
    _ensure_node_count = MainWindow._ensure_node_count

    def __init__(self):
        self.model = SimpleNamespace(nodes={})
        self.prompts = 0

    def _ask_create_prerequisite(self, **_kwargs) -> bool:
        self.prompts += 1
        return True

    def _create_node(self) -> None:
        tag = len(self.model.nodes) + 1
        self.model.nodes[tag] = object()


def test_node_prerequisite_can_create_until_required_count():
    holder = _NodeHolder()

    ready = holder._ensure_node_count(
        2,
        title="Create Frame",
    )

    assert ready is True
    assert len(holder.model.nodes) == 2
    assert holder.prompts == 2


def test_major_dependent_workflows_use_prerequisite_links():
    expected = {
        "_create_load_pattern": "_create_time_series",
        "_create_nodal_load": "_ensure_plain_load_pattern",
        "_create_prescribed_displacement": "_ensure_plain_load_pattern",
        "_create_element_load": "_ensure_plain_load_pattern",
        "_create_truss": "_create_material",
        "_create_frame": "_create_section",
        "_create_connection": "_ensure_node_count",
        "_assign_section_to_selection": "_create_section",
        "_assign_truss_material_to_selection": "_create_material",
        "_assign_transformation_to_selection": "_create_transformation",
        "_run_moment_curvature_workflow": "_create_section",
        "_start_analysis": "_create_analysis",
        "_open_calibration": "_create_analysis_template",
        "_create_analysis_template": "_offer_structural_model_creator",
    }

    for method_name, dependency_name in expected.items():
        source = inspect.getsource(getattr(MainWindow, method_name))
        assert dependency_name in source



def test_second_prerequisite_link_batch():
    expected = {
        "_create_constraint": "_ensure_node_count",
        "_create_recorder": "_ensure_node_count",
        "_create_element_load": "create_if_missing=True",
        "_apply_restraint": "create_if_missing=True",
        "_assign_mass": "create_if_missing=True",
        "_set_element_formulation": "create_if_missing=True",
        "_assign_section_to_selection": "create_if_missing=True",
        "_assign_transformation_to_selection": "create_if_missing=True",
        "_assign_truss_material_to_selection": "_create_truss",
        "_create_analysis_of_type": "_ensure_node_count",
    }

    for method_name, dependency_marker in expected.items():
        source = inspect.getsource(getattr(MainWindow, method_name))
        assert dependency_marker in source
