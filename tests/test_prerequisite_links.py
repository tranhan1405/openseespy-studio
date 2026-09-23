from __future__ import annotations

import inspect
from types import SimpleNamespace

from openseespy_studio.ui.main_window import FrameGridPanel, MainWindow
from openseespy_studio.ui.recorder_dialog import RecorderDialog
from openseespy_studio.ui.analysis_dialog import AnalysisDialog
from openseespy_studio.ui.geometry_dialogs import ElementDialog, TrussDialog
from openseespy_studio.ui.line_geometry_dialog import LineGeometryDialog
from openseespy_studio.ui.load_dialogs import (
    ElementLoadDialog,
    LoadPatternDialog,
    NodalLoadDialog,
    PrescribedDisplacementDialog,
)
from openseespy_studio.ui.moment_curvature_dialog import MomentCurvatureDialog
from openseespy_studio.ui.mass_source_dialog import MassSourceDialog
from openseespy_studio.ui.shell_dialog import ShellElementDialog, ShellMeshDialog
from openseespy_studio.ui.surface_dialog import SurfaceGeometryDialog
from openseespy_studio.ui.surface_edge_load_dialog import SurfaceEdgeLoadDialog
from openseespy_studio.ui.surface_pressure_dialog import SurfacePressureDialog
from openseespy_studio.ui.surface_result_dialog import SurfaceResultDialog


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
        "_run_moment_curvature_workflow": "new_section_callback=self._create_section_dependency",
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

class _GeometryPointHolder:
    _ensure_geometry_point_count = MainWindow._ensure_geometry_point_count

    def __init__(self):
        self.project = SimpleNamespace(points={})
        self.prompts = 0

    def _ask_create_prerequisite(self, **_kwargs) -> bool:
        self.prompts += 1
        return True

    def _create_point_geometry(self) -> int:
        tag = len(self.project.points) + 1
        self.project.points[tag] = object()
        return tag


def test_geometry_point_prerequisite_can_create_until_required_count():
    holder = _GeometryPointHolder()

    ready = holder._ensure_geometry_point_count(
        2,
        title="New Geometry Line",
    )

    assert ready is True
    assert len(holder.project.points) == 2
    assert holder.prompts == 2


def test_inline_prerequisite_buttons_cover_core_dependency_dialogs():
    checks = (
        (
            LineGeometryDialog,
            (
                "New Section...",
                "New Transformation...",
                "New Material...",
                "new_section_callback",
                "new_transformation_callback",
                "new_material_callback",
            ),
        ),
        (
            SurfaceGeometryDialog,
            ("New Shell Section...", "new_section_callback"),
        ),
        (
            ShellElementDialog,
            ("New Shell Section...", "new_section_callback"),
        ),
        (
            ShellMeshDialog,
            ("New Shell Section...", "new_section_callback"),
        ),
        (
            ElementDialog,
            (
                "New Section...",
                "New Transformation...",
                "new_section_callback",
                "new_transformation_callback",
            ),
        ),
        (
            TrussDialog,
            ("New Material...", "new_material_callback"),
        ),
        (
            LoadPatternDialog,
            ("New Time Series...", "new_time_series_callback"),
        ),
        (
            NodalLoadDialog,
            ("New Plain Pattern...", "new_pattern_callback"),
        ),
        (
            PrescribedDisplacementDialog,
            ("New Plain Pattern...", "new_pattern_callback"),
        ),
        (
            ElementLoadDialog,
            ("New Plain Pattern...", "new_pattern_callback"),
        ),
        (
            SurfacePressureDialog,
            ("New Plain Pattern...", "new_pattern_callback"),
        ),
        (
            SurfaceEdgeLoadDialog,
            ("New Plain Pattern...", "new_pattern_callback"),
        ),
        (
            SurfaceResultDialog,
            ("New Analysis...", "new_analysis_callback"),
        ),
        (
            AnalysisDialog,
            (
                "New Plain Pattern...",
                "new_plain_pattern_callback",
                "New Ground Motion...",
                "new_ground_motion_callback",
            ),
        ),
        (
            MassSourceDialog,
            ("New Plain Pattern...", "new_pattern_callback"),
        ),
        (
            MomentCurvatureDialog,
            ("New Section...", "new_section_callback"),
        ),
    )

    for dialog_class, markers in checks:
        source = inspect.getsource(dialog_class)
        for marker in markers:
            assert marker in source, (
                f"{dialog_class.__name__} is missing prerequisite route: "
                f"{marker}"
            )


def test_inline_dependency_callbacks_are_wired_from_main_window():
    expected = {
        "_configure_line_mesh": (
            "new_section_callback=self._create_frame_section_dependency",
            "new_transformation_callback=self._create_transformation_dependency",
            "new_material_callback=self._create_material_dependency",
        ),
        "_configure_surface_mesh": (
            "new_section_callback=self._create_shell_section_dependency",
        ),
        "_create_shell_mesh": (
            "new_section_callback=self._create_shell_section_dependency",
        ),
        "_create_shell": (
            "new_section_callback=self._create_shell_section_dependency",
        ),
        "_create_frame": (
            "new_section_callback=self._create_frame_section_dependency",
            "new_transformation_callback=self._create_transformation_dependency",
        ),
        "_create_truss": (
            "new_material_callback=self._create_material_dependency",
        ),
        "_create_nodal_load": (
            "new_pattern_callback=self._create_plain_pattern_dependency",
        ),
        "_create_prescribed_displacement": (
            "new_pattern_callback=self._create_plain_pattern_dependency",
        ),
        "_create_element_load": (
            "new_pattern_callback=self._create_plain_pattern_dependency",
        ),
        "_run_moment_curvature_workflow": (
            "new_section_callback=self._create_section_dependency",
        ),
    }
    for method_name, markers in expected.items():
        source = inspect.getsource(getattr(MainWindow, method_name))
        for marker in markers:
            assert marker in source


def test_eighth_prerequisite_link_batch():
    edit_recorder = inspect.getsource(MainWindow._edit_recorder)
    assert "target_creator=self._recorder_target_creator" in edit_recorder

    mass_create = inspect.getsource(MainWindow._create_mass_source)
    mass_edit = inspect.getsource(MainWindow._edit_mass_source)
    for source in (mass_create, mass_edit):
        assert (
            "new_pattern_callback=self._create_plain_pattern_dependency"
            in source
        )

    analysis_create = inspect.getsource(MainWindow._create_analysis_of_type)
    analysis_edit = inspect.getsource(MainWindow._edit_analysis)
    for source in (analysis_create, analysis_edit):
        assert (
            "new_ground_motion_callback="
            "self._create_ground_motion_dependency"
            in source
        )

    frame_grid = inspect.getsource(FrameGridPanel)
    assert "Create a Section and assign it to columns." in frame_grid
    assert "Create a Section and assign it to beams." in frame_grid
    assert (
        "Create a Geometric Transformation and assign it to columns."
        in frame_grid
    )
    assert (
        "Create a Geometric Transformation and assign it to beams."
        in frame_grid
    )
    assert "_create_section_dependency" in frame_grid
    assert "_create_transformation_dependency" in frame_grid

    moment = inspect.getsource(MainWindow._run_moment_curvature_workflow)
    dialog_index = moment.index("MomentCurvatureDialog(")
    assert "_ensure_prerequisite" not in moment[:dialog_index]
    assert "new_section_callback=self._create_section_dependency" in moment


def test_managed_surface_dependency_callbacks_are_wired():
    edge_source = inspect.getsource(
        MainWindow._manage_surface_edge_line_load
    )
    pressure_source = inspect.getsource(
        MainWindow._create_surface_pressure_for_surfaces
    )
    result_source = inspect.getsource(
        MainWindow._manage_surface_shell_result
    )

    assert (
        "new_pattern_callback=self._create_plain_pattern_dependency"
        in edge_source
    )
    assert (
        "new_pattern_callback=self._create_plain_pattern_dependency"
        in pressure_source
    )
    assert (
        "new_analysis_callback=self._create_analysis_dependency"
        in result_source
    )


def test_nodal_load_edit_no_longer_passes_element_load_only_keyword():
    source = inspect.getsource(MainWindow._edit_nodal_load)

    assert "allowed_load_types=" not in source
    assert "new_pattern_callback=self._create_plain_pattern_dependency" in source

