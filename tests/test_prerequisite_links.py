from __future__ import annotations

import inspect
from types import SimpleNamespace

from openseespy_studio.ui.main_window import MainWindow
from openseespy_studio.ui.recorder_dialog import RecorderDialog


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


def test_third_prerequisite_link_batch():
    measure_source = inspect.getsource(
        MainWindow._activate_measure_distance
    )
    assert "_ensure_node_count" in measure_source
    assert "2," in measure_source

    menu_source = inspect.getsource(
        MainWindow._show_viewport_context_menu
    )
    cases = {
        "support": (
            "apply_support.triggered.connect(self._apply_restraint)",
            "support_menu.setEnabled(bool(self.selection.nodes))",
        ),
        "constraint": (
            "constraint_action.triggered.connect(self._create_constraint)",
            "constraint_action.setEnabled(len(self.selection.nodes) >= 2)",
        ),
        "connection": (
            "connection_action.triggered.connect(self._create_connection)",
            "connection_action.setEnabled(1 <= len(self.selection.nodes) <= 2)",
        ),
        "mass": (
            "mass_action.triggered.connect(self._assign_mass)",
            "mass_action.setEnabled(bool(self.selection.nodes))",
        ),
        "nodal_load": (
            "load_action.triggered.connect(self._create_nodal_load)",
            "load_action.setEnabled(bool(self.selection.nodes))",
        ),
        "prescribed_displacement": (
            "self._create_prescribed_displacement",
            "displacement_action.setEnabled(bool(self.selection.nodes))",
        ),
        "beam_load": (
            "beam_load_action.triggered.connect(self._create_element_load)",
            "beam_load_action.setEnabled(has_frame and not has_truss)",
        ),
        "formulation": (
            "self._set_element_formulation",
            "formulation_action.setEnabled(has_frame and not has_truss)",
        ),
    }
    for trigger_marker, stale_gate in cases.values():
        assert trigger_marker in menu_source
        assert stale_gate not in menu_source

    assert "assign_menu.setEnabled(bool(selected_elements))" not in menu_source
    assert "assign_material.setEnabled(has_truss)" not in menu_source
    assert "assign_section.setEnabled(has_frame)" not in menu_source
    assert "assign_transformation.setEnabled(has_frame)" not in menu_source
    assert "clear_material.setEnabled(has_truss)" in menu_source
    assert "clear_section.setEnabled(has_frame)" in menu_source
    assert "clear_transformation.setEnabled(has_frame)" in menu_source


def test_fourth_prerequisite_link_batch():
    expected = {
        "_create_mass_source": "_offer_structural_model_creator",
        "_create_named_selection": "_ensure_node_count",
        "_load_analysis_result": "_offer_result_analysis_run",
        "_evaluate_all_solution_results": "_offer_result_analysis_run",
        "_show_plot_menu": "_offer_result_analysis_run",
        "_export_active_job_results": "_offer_result_analysis_run",
        "_create_analysis_template": "_ensure_first_mode_modal_prerequisite",
    }
    for method_name, marker in expected.items():
        source = inspect.getsource(getattr(MainWindow, method_name))
        assert marker in source

    tree_source = inspect.getsource(MainWindow._show_tree_context_menu)
    assert (
        "create.setEnabled(\n"
        "                bool(self.selection.nodes or self.selection.elements)"
        not in tree_source
    )
    assert (
        "apply_support.setEnabled(bool(self.selection.nodes))"
        not in tree_source
    )
    assert (
        "constraint.setEnabled(len(self.selection.nodes) >= 2)"
        not in tree_source
    )

    modal_source = inspect.getsource(
        MainWindow._ensure_first_mode_modal_prerequisite
    )
    assert '_create_analysis_template("Modal")' in modal_source
    assert "_run_analysis_from_tree(modal_tag)" in modal_source

    result_source = inspect.getsource(
        MainWindow._offer_result_analysis_run
    )
    assert "_offer_structural_model_creator" in result_source
    assert "_create_analysis" in result_source
    assert "_run_analysis_from_tree" in result_source


def test_fifth_prerequisite_link_batch():
    tree_source = inspect.getsource(MainWindow._show_tree_context_menu)

    # Empty element-type groups must still expose creation-aware workflows.
    assert "formulation.setEnabled(bool(tags) and not is_truss_group)" not in tree_source
    assert "material.setEnabled(bool(tags) and is_truss_group)" not in tree_source
    assert "section.setEnabled(bool(tags) and not is_truss_group)" not in tree_source
    assert "transformation.setEnabled(bool(tags) and not is_truss_group)" not in tree_source
    assert "beam_load.setEnabled(bool(tags) and not is_truss_group)" not in tree_source
    assert "assign.setEnabled(bool(tags))" not in tree_source

    assert "not is_truss_group and not is_shell_group" in tree_source
    assert "material.setEnabled(is_truss_group)" in tree_source
    assert "section.setEnabled(not is_truss_group)" in tree_source
    assert "self._assign_shell_section_to_selection()" in tree_source
    assert "is_shell_group" in tree_source

    # Mixed Frame + Truss selections may still operate on the eligible frames.
    assert "formulation.setEnabled(has_frame and not has_truss)" not in tree_source
    assert "beam_load.setEnabled(has_frame and not has_truss)" not in tree_source
    assert "formulation.setEnabled(has_frame)" in tree_source
    assert "beam_load.setEnabled(has_frame)" in tree_source

    result_methods = {
        "_show_deformation_result": "Deformed Shape",
        "_show_node_contour_result": "Nodal Result",
        "_show_member_force_result": "Member Force Result",
    }
    for method_name, title in result_methods.items():
        source = inspect.getsource(getattr(MainWindow, method_name))
        assert "_offer_result_analysis_run" in source
        assert title in source


def test_sixth_prerequisite_link_batch():
    expected = {
        "_create_analysis_of_type": "_ensure_dynamic_mass",
        "_show_hinge_state_result": "_offer_result_analysis_run",
        "_show_mode_shape_result": "_ensure_active_modal_result",
        "_activate_job_result": "_offer_job_analysis_rerun",
        "_show_job_plot": "_offer_job_analysis_rerun",
        "_quick_plot_job_result": "_offer_job_analysis_rerun",
        "_export_job_result_json": "_offer_job_analysis_rerun",
    }
    for method_name, marker in expected.items():
        source = inspect.getsource(getattr(MainWindow, method_name))
        assert marker in source

    dynamic_source = inspect.getsource(MainWindow._ensure_dynamic_mass)
    assert "_create_mass_source" in dynamic_source
    assert "_has_dynamic_mass" in dynamic_source

    modal_source = inspect.getsource(MainWindow._ensure_active_modal_result)
    assert "_ensure_first_mode_modal_prerequisite" in modal_source
    assert 'job.analysis_type == "Modal"' in modal_source

    rerun_source = inspect.getsource(MainWindow._offer_job_analysis_rerun)
    assert "_run_analysis_from_tree" in rerun_source
    assert "Run Analysis Again..." in rerun_source

    tree_source = inspect.getsource(MainWindow._show_tree_context_menu)
    assert "activate.setEnabled(bool(job and job.results))" not in tree_source
    assert "plot_menu.setEnabled(bool(job and job.results))" not in tree_source
    assert "export.setEnabled(bool(job and job.results))" not in tree_source
    assert "activate.setEnabled(job is not None)" in tree_source
    assert "plot_menu.setEnabled(job is not None)" in tree_source
    assert "export.setEnabled(job is not None)" in tree_source


def test_seventh_prerequisite_link_batch():
    recorder_source = inspect.getsource(MainWindow._recorder_target_creator)

    # 1-4: each Recorder type can create/link its own required target.
    recorder_cases = {
        "Node": "_ensure_node_count",
        "Element": "_create_frame",
        "Section": "_ensure_nonlinear_beam_target",
        "Fiber": "_ensure_fiber_beam_target",
    }
    for recorder_type, marker in recorder_cases.items():
        assert f'kind == "{recorder_type}"' in recorder_source
        assert marker in recorder_source

    create_recorder_source = inspect.getsource(MainWindow._create_recorder)
    assert "target_creator=self._recorder_target_creator" in create_recorder_source
    recorder_dialog_source = inspect.getsource(RecorderDialog.__init__)
    assert "Create / Link Target..." in recorder_dialog_source
    assert "self._create_or_link_target" in recorder_dialog_source

    result_source = inspect.getsource(
        MainWindow._prepare_solution_result_prerequisites
    )

    # 5: Member Force -> Frame.
    assert 'kind == "MemberForce"' in result_source
    assert 'action_label="Create Frame Now..."' in result_source

    # 6: Section Response -> zeroLengthSection/nonlinear beam target.
    assert 'kind == "SectionResponse"' in result_source
    assert "section_response_sources" in result_source
    assert "_ensure_nonlinear_beam_target" in result_source

    # 7-9: fiber-derived results -> Fiber-section nonlinear beam.
    for result_type in ("FiberStress", "FiberStrain", "HingeState"):
        assert f'"{result_type}"' in result_source
    assert "_ensure_fiber_beam_target" in result_source

    # 10: Specimen Response -> Quick 1D Column / Test Specimen.
    assert 'kind == "SpecimenResponse"' in result_source
    assert "_show_test_column_wizard" in result_source
    assert 'action_label="Create 1D Column Now..."' in result_source

    insert_source = inspect.getsource(MainWindow._insert_solution_result)
    assert "_prepare_solution_result_prerequisites" in insert_source

    fiber_source = inspect.getsource(MainWindow._ensure_fiber_beam_target)
    assert "_create_fiber_beam_prerequisite" in fiber_source

    # Section Response must remain visible even when its prerequisite target
    # does not exist yet, otherwise the user cannot reach the creation route.
    tree_source = inspect.getsource(MainWindow._show_tree_context_menu)
    assert "section_response_available=True" in tree_source


def test_remaining_prerequisite_dead_ends_are_linked():
    edit_analysis = inspect.getsource(MainWindow._edit_analysis)
    assert "_ensure_dynamic_mass" in edit_analysis
    assert 'updated.analysis_type in {"Modal", "Transient"}' in edit_analysis

    ground_pair = inspect.getsource(MainWindow._ground_motion_pair)
    assert 'series.series_type != "Path"' in ground_pair

    edit_ground = inspect.getsource(MainWindow._edit_ground_motion)
    assert "Create / Link Path Series Now..." in edit_ground
    assert "_ask_create_prerequisite" in edit_ground
    assert "update_load_pattern" in edit_ground

