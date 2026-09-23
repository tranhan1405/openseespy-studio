from __future__ import annotations

import inspect
from types import SimpleNamespace

from openseespy_studio.ui.main_window import FrameGridPanel, MainWindow
from openseespy_studio.ui.recorder_dialog import RecorderDialog
from openseespy_studio.ui.analysis_dialog import AnalysisDialog
from openseespy_studio.ui.analysis_template_dialog import AnalysisTemplateDialog
from openseespy_studio.ui.calibration_dialog import CalibrationDialog
from openseespy_studio.ui.constraint_dialog import ConstraintDialog
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


def test_ninth_prerequisite_link_batch():
    calibration_source = inspect.getsource(CalibrationDialog)
    assert "New Material..." in calibration_source
    assert "new_material_callback" in calibration_source
    assert "_create_material_dependency" in calibration_source

    open_calibration = inspect.getsource(MainWindow._open_calibration)
    assert (
        "new_material_callback=self._create_material_dependency"
        in open_calibration
    )

    constraint_source = inspect.getsource(ConstraintDialog)
    assert "New Node..." in constraint_source
    assert "Add New Node..." in constraint_source
    assert "new_node_callback" in constraint_source

    for method_name in ("_create_constraint", "_edit_constraint"):
        source = inspect.getsource(getattr(MainWindow, method_name))
        assert "new_node_callback=self._create_node_dependency" in source

    helper_source = inspect.getsource(MainWindow._ensure_surface_meshes)
    assert "Mesh Surface {tag} Now..." in helper_source
    assert "_configure_surface_mesh(tag, generate=True)" in helper_source

    pressure_source = inspect.getsource(
        MainWindow._create_surface_pressure_for_surfaces
    )
    assert "_ensure_surface_meshes" in pressure_source
    assert "Mesh the following Surface geometry first" not in pressure_source

    edge_source = inspect.getsource(
        MainWindow._manage_surface_edge_line_load
    )
    assert "_ensure_surface_meshes" in edge_source

    recorder_source = inspect.getsource(
        MainWindow._manage_surface_shell_recorder
    )
    assert "_ensure_surface_meshes" in recorder_source
    assert "Mesh the Surface before creating" not in recorder_source


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

def test_tenth_prerequisite_link_batch():
    three_point_plane = inspect.getsource(
        MainWindow._create_three_point_sketch_plane
    )
    assert "_ensure_geometry_point_count" in three_point_plane
    assert "3," in three_point_plane
    assert "Create at least three Geometry Points first." not in three_point_plane

    line_preview = inspect.getsource(MainWindow._preview_line_mesh)
    assert "Configure Line Mesh Now..." in line_preview
    assert "_configure_line_mesh(tag, generate=False)" in line_preview
    assert "before previewing." not in line_preview

    line_select = inspect.getsource(MainWindow._select_line_generated_fe)
    assert "Mesh Line Now..." in line_select
    assert "_mesh_line_geometry(tag)" in line_select
    assert "is not meshed." not in line_select

    surface_quality = inspect.getsource(MainWindow._show_surface_quality_map)
    assert "_ensure_surface_meshes" in surface_quality
    assert 'title="Shell Mesh Quality"' in surface_quality
    assert "before visualizing" not in surface_quality

    surface_select = inspect.getsource(
        MainWindow._select_generated_fe_for_surfaces
    )
    assert "_ensure_surface_meshes" in surface_select
    assert 'title="Select Generated FE"' in surface_select
    assert "has no live generated" not in surface_select

def test_eleventh_prerequisite_link_batch():
    tree_source = inspect.getsource(MainWindow._show_tree_context_menu)

    # 1: Line Preview stays reachable even before its mesh recipe exists.
    assert "preview.setEnabled(line.mesh_recipe_configured)" not in tree_source
    line_preview = inspect.getsource(MainWindow._preview_line_mesh)
    assert "Configure Line Mesh Now..." in line_preview

    # 2: Line Select Generated FE stays reachable and can mesh inline.
    line_select = inspect.getsource(MainWindow._select_line_generated_fe)
    assert "Mesh Line Now..." in line_select
    assert (
        'select_fe.setEnabled(live_mesh)\n'
        '            select_fe.triggered.connect(\n'
        '                lambda checked=False, t=tag:\n'
        '                self._select_line_generated_fe(t)'
        not in tree_source
    )

    # 3: Surface Preview can configure missing recipes without leaving.
    surface_preview = inspect.getsource(MainWindow._preview_surface_meshes)
    assert "Configure Surface {tag} Mesh Now..." in surface_preview
    assert "_configure_surface_mesh(tag, generate=False)" in surface_preview
    assert "Configure Surface Mesh first for:" not in surface_preview
    assert "preview.setEnabled(surface.mesh_recipe_configured)" not in tree_source

    # 4: Surface Select Generated FE stays reachable and can mesh inline.
    surface_select = inspect.getsource(
        MainWindow._select_generated_fe_for_surfaces
    )
    assert "_ensure_surface_meshes" in surface_select
    assert (
        'select_fe.setEnabled(live_mesh)\n'
        '            select_fe.triggered.connect(\n'
        '                lambda checked=False, t=tag:\n'
        '                self._select_generated_fe_for_surfaces([t])'
        not in tree_source
    )

    # 5: Surface mesh-quality menu stays reachable and meshes inline.
    surface_quality = inspect.getsource(MainWindow._show_surface_quality_map)
    assert "_ensure_surface_meshes" in surface_quality
    assert "quality_menu.setEnabled(live_mesh)" not in tree_source

def test_twelfth_prerequisite_link_batch():
    tree_source = inspect.getsource(MainWindow._show_tree_context_menu)

    # 1: Managed Edge Support can create the required Surface mesh inline.
    support_source = inspect.getsource(MainWindow._manage_surface_edge_support)
    assert "_ensure_surface_meshes" in support_source
    assert 'title="Managed Surface Edge Support"' in support_source
    assert "managed_support.setEnabled(live_mesh)" not in tree_source

    # 2: Managed Edge Line Load remains reachable before meshing.
    edge_load_source = inspect.getsource(
        MainWindow._manage_surface_edge_line_load
    )
    assert "_ensure_surface_meshes" in edge_load_source
    assert "managed_line_load.setEnabled(live_mesh)" not in tree_source

    # 3: Managed Surface Pressure remains reachable before meshing.
    pressure_source = inspect.getsource(
        MainWindow._create_surface_pressure_for_surfaces
    )
    assert "_ensure_surface_meshes" in pressure_source
    assert "pressure.setEnabled(live_mesh)" not in tree_source

    # 4: Managed Shell Recorder remains reachable before meshing.
    recorder_source = inspect.getsource(
        MainWindow._manage_surface_shell_recorder
    )
    assert "_ensure_surface_meshes" in recorder_source
    assert "managed_shell_recorder.setEnabled(live_mesh)" not in tree_source

    # 5: Managed Shell Result can create the required Surface mesh inline.
    result_source = inspect.getsource(
        MainWindow._manage_surface_shell_result
    )
    assert "_ensure_surface_meshes" in result_source
    assert 'title="Managed Surface Shell Result"' in result_source
    assert "Mesh the following Surface geometry first:" not in result_source
    assert "managed_shell_result.setEnabled(live_mesh)" not in tree_source

def test_thirteenth_prerequisite_link_batch():
    tree_source = inspect.getsource(MainWindow._show_tree_context_menu)

    # 1: 3-point Plane remains reachable and can create missing Points inline.
    three_point = inspect.getsource(MainWindow._create_three_point_sketch_plane)
    assert "_ensure_geometry_point_count" in three_point
    assert "three.setEnabled(len(self.project.points) >= 3)" not in tree_source

    # 2: Line Mesh Quality can configure its missing mesh recipe inline.
    quality_source = inspect.getsource(MainWindow._show_line_mesh_quality)
    assert "Configure Line Mesh Now..." in quality_source
    assert "_configure_line_mesh(tag, generate=False)" in quality_source
    assert "quality.setEnabled(line.mesh_recipe_configured)" not in tree_source

    # 3: Surface Edge FE-node selection can create the Surface mesh inline.
    edge_nodes = inspect.getsource(MainWindow._select_surface_edge_nodes)
    assert "_ensure_surface_meshes" in edge_nodes
    assert 'title="Select Surface Edge FE Nodes"' in edge_nodes

    # 4: Surface Boundary FE-node selection can create all missing meshes inline.
    boundary_nodes = inspect.getsource(MainWindow._select_surface_boundary_nodes)
    assert "_ensure_surface_meshes" in boundary_nodes
    assert 'title="Select Surface Boundary FE Nodes"' in boundary_nodes

    # 5: Analysis Wizard -> Mass Source keeps Plain Pattern creation inline.
    template_source = inspect.getsource(AnalysisTemplateDialog)
    assert "new_pattern_callback=None" in template_source
    assert "self._new_pattern_callback = new_pattern_callback" in template_source
    assert "new_pattern_callback=self._new_pattern_callback" in template_source

    create_template = inspect.getsource(MainWindow._create_analysis_template)
    assert (
        "new_pattern_callback=self._create_plain_pattern_dependency"
        in create_template
    )

def test_fourteenth_prerequisite_link_batch():
    viewport_menu = inspect.getsource(MainWindow._show_viewport_context_menu)
    tree_menu = inspect.getsource(MainWindow._show_tree_context_menu)

    # 1: Beam Load remains reachable so it can create Pattern/Frame prerequisites.
    assert 'beam_load_action.setEnabled(has_frame)' not in viewport_menu
    create_beam_load = inspect.getsource(MainWindow._create_element_load)
    assert "_ensure_plain_load_pattern" in create_beam_load
    assert "create_if_missing=True" in create_beam_load

    # 2: Shell Pressure remains reachable so it can create Shell/Pattern prerequisites.
    assert 'shell_pressure_action.setEnabled(has_shell)' not in viewport_menu
    create_pressure = inspect.getsource(MainWindow._create_shell_pressure)
    assert "Create & Mesh Surface Now..." in create_pressure

    # 3: Generate Line Meshes can configure missing Line recipes inline.
    line_generate = inspect.getsource(
        MainWindow._generate_all_configured_line_meshes
    )
    assert "Configure Line {tag} Mesh Now..." in line_generate
    assert "_configure_line_mesh(tag, generate=False)" in line_generate
    assert "No configured unmeshed Geometry Lines are ready." not in line_generate
    assert "line_generate.setEnabled(bool(self.project.lines))" in tree_menu

    # 4: Generate Surface Meshes can configure missing Surface recipes inline.
    surface_generate = inspect.getsource(
        MainWindow._generate_all_configured_surface_meshes
    )
    assert "Configure Surface {tag} Mesh Now..." in surface_generate
    assert "_configure_surface_mesh(tag, generate=False)" in surface_generate
    assert "No configured unmeshed Surfaces are ready." not in surface_generate
    assert "surface_generate.setEnabled(bool(self.project.surfaces))" in tree_menu

    # 5: Editing a meshed Geometry Point automatically remeshes dependants.
    edit_point = inspect.getsource(MainWindow._edit_point_geometry)
    assert "Edit + Remesh Now..." in edit_point
    assert "remesh_line_geometry(self.project, line_tag)" in edit_point
    assert "remesh_surface_geometry(self.project, surface_tag)" in edit_point
    assert "Delete/remesh the generated FE mesh before moving it." not in edit_point

def test_fifteenth_prerequisite_link_batch():
    # 1: Editing a generated nodal load routes directly to its managed owner.
    edit_nodal = inspect.getsource(MainWindow._edit_nodal_load)
    assert "Edit Managed Edge Load Now..." in edit_nodal
    assert "edge_load_tag=owner.tag" in edit_nodal
    assert "Edit the Geometry Edge load instead." not in edit_nodal

    # 2: Deleting a generated nodal load routes directly to managed removal.
    delete_nodal = inspect.getsource(MainWindow._delete_nodal_load)
    assert "Remove Managed Edge Load Now..." in delete_nodal
    assert "edge_load_tag=owner.tag" in delete_nodal
    assert "Remove the Geometry Edge load instead." not in delete_nodal

    # 3: Editing a generated element load opens its exact managed pressure.
    edit_element = inspect.getsource(MainWindow._edit_element_load)
    assert "Edit Managed Pressure Now..." in edit_element
    assert "pressure_tag=owner.tag" in edit_element
    assert "Edit the Geometry Surface pressure instead." not in edit_element

    # 4: Deleting a generated element load routes to exact managed pressure removal.
    delete_element = inspect.getsource(MainWindow._delete_element_load)
    assert "Remove Managed Pressure Now..." in delete_element
    assert "pressure_tag=owner.tag" in delete_element
    assert "Remove the Geometry Surface pressure instead." not in delete_element

    # 5: Editing a generated recorder opens its exact managed recorder definition.
    edit_recorder = inspect.getsource(MainWindow._edit_recorder)
    assert "Edit Managed Recorder Now..." in edit_recorder
    assert "recorder_tag=owner.tag" in edit_recorder
    assert "Edit the Geometry Surface recorder instead." not in edit_recorder

    edge_editor = inspect.getsource(MainWindow._manage_surface_edge_line_load)
    assert "edge_load_tag: int | None = None" in edge_editor

    edge_remove = inspect.getsource(MainWindow._remove_surface_edge_line_load)
    assert "edge_load_tag: int | None = None" in edge_remove

    pressure_editor = inspect.getsource(
        MainWindow._create_surface_pressure_for_surfaces
    )
    assert "pressure_tag: int | None = None" in pressure_editor

    pressure_remove = inspect.getsource(
        MainWindow._remove_managed_surface_pressure
    )
    assert "pressure_tag: int | None = None" in pressure_remove

    recorder_editor = inspect.getsource(
        MainWindow._manage_surface_shell_recorder
    )
    assert "recorder_tag: int | None = None" in recorder_editor

def test_sixteenth_prerequisite_link_batch():
    # 1: Deleting a generated recorder routes to exact managed removal.
    delete_recorder = inspect.getsource(MainWindow._delete_recorder)
    assert "Remove Managed Recorder Now..." in delete_recorder
    assert "recorder_tag=owner.tag" in delete_recorder
    assert "Remove the Geometry Surface recorder instead." not in delete_recorder

    recorder_remove = inspect.getsource(
        MainWindow._remove_managed_surface_shell_recorder
    )
    assert "recorder_tag: int | None = None" in recorder_remove

    # 2: Managed Surface result scope editing opens the exact owner result.
    scope_source = inspect.getsource(
        MainWindow._use_current_selection_for_solution_result
    )
    assert "Edit Managed Surface Result Now..." in scope_source
    assert "result_tag=result.tag" in scope_source
    assert "Select/edit the Geometry Surface result instead." not in scope_source

    result_editor = inspect.getsource(MainWindow._manage_surface_shell_result)
    assert "result_tag: int | None = None" in result_editor

    # 3: Missing recorder FE realization can mesh and rebuild inline.
    recorder_targets = inspect.getsource(
        MainWindow._select_managed_surface_recorder_targets
    )
    assert "Mesh + Rebuild Recorder Now..." in recorder_targets
    assert "_ensure_surface_meshes" in recorder_targets
    assert "sync_surface_recorder" in recorder_targets
    assert "Mesh/remesh the Surface first." not in recorder_targets

    # 4: Managed ground nodes route directly to their owning Connection.
    ground_nodes = inspect.getsource(MainWindow._exclude_managed_ground_nodes)
    assert "Edit Owning Connection Now..." in ground_nodes
    assert "self._edit_connection(owner.tag)" in ground_nodes
    assert "Edit the structural/source node instead." not in ground_nodes

    # 5: Managed support nodes route directly to the exact Surface support.
    support_nodes = inspect.getsource(
        MainWindow._exclude_managed_surface_support_nodes
    )
    assert "Edit Managed Edge Support Now..." in support_nodes
    assert "support_tag=owner.tag" in support_nodes
    assert "Surface context menu instead." not in support_nodes

    support_editor = inspect.getsource(MainWindow._manage_surface_edge_support)
    assert "support_tag: int | None = None" in support_editor

def test_seventeenth_prerequisite_link_batch():
    # Shared Geometry-Line prerequisite chain can create Lines, which in turn
    # can create missing Geometry Points through the existing Line workflow.
    ensure_lines = inspect.getsource(MainWindow._ensure_geometry_line_count)
    assert "Create Geometry Line Now..." in ensure_lines
    assert "self._create_line_geometry()" in ensure_lines

    # 1: Trim / Extend can create the missing Geometry Line inline.
    trim_extend = inspect.getsource(MainWindow._activate_geometry_line_target_tool)
    assert "_ensure_geometry_line_count" in trim_extend
    assert "Create at least two Geometry Lines before using" not in trim_extend

    # 2: Copy Line Mesh Recipe can create a missing target Line inline.
    copy_recipe = inspect.getsource(MainWindow._copy_line_mesh_recipe_to_selected)
    assert "_ensure_geometry_line_count" in copy_recipe
    assert 'title="Copy Line Mesh / FE Recipe"' in copy_recipe
    assert "targets = sorted(" in copy_recipe

    # 3: Split by Line can create the missing Line and resume with both Lines.
    split_lines = inspect.getsource(
        MainWindow._split_selected_geometry_lines_at_intersection
    )
    assert "_ensure_geometry_line_count" in split_lines
    assert 'title="Split by Line"' in split_lines
    assert "tags = sorted(self.project.lines)[:2]" in split_lines

    # 4: Fillet can create the missing Line and resume.
    fillet = inspect.getsource(MainWindow._fillet_selected_geometry_lines)
    assert "_ensure_geometry_line_count" in fillet
    assert 'title="Fillet Geometry Lines"' in fillet
    assert "tags = sorted(self.project.lines)[:2]" in fillet

    # 5: Chamfer can create the missing Line and resume.
    chamfer = inspect.getsource(MainWindow._chamfer_selected_geometry_lines)
    assert "_ensure_geometry_line_count" in chamfer
    assert 'title="Chamfer Geometry Lines"' in chamfer
    assert "tags = sorted(self.project.lines)[:2]" in chamfer

def test_eighteenth_prerequisite_link_batch():
    # 1: Deleting a referenced nD Material can edit the owning Shell Section inline.
    delete_nd = inspect.getsource(MainWindow._delete_nd_material)
    assert "Edit Shell Section {owner_tag} Now..." in delete_nd
    assert "self._edit_shell_section(owner_tag)" in delete_nd
    assert "Reassign those references first." not in delete_nd

    # 2: Deleting a Material referenced by a Section routes to that Section.
    delete_material = inspect.getsource(MainWindow._delete_material)
    assert "Edit Section {owner_tag} Now..." in delete_material
    assert "self._edit_section(owner_tag)" in delete_material

    # 3: Deleting a Material referenced by a Connection routes to that Connection.
    assert "Edit Connection {owner_tag} Now..." in delete_material
    assert "self._edit_connection(owner_tag)" in delete_material

    # Managed specimen Connections no longer stop at an information-only dead end.
    edit_connection = inspect.getsource(MainWindow._edit_connection)
    assert "Open Quick 1D Column Wizard Now..." in edit_connection
    assert "self._show_test_column_wizard()" in edit_connection

    # 4: Deleting a Material referenced by a wrapper/composite Material routes inline.
    assert "Edit Wrapper Material {owner_tag} Now..." in delete_material
    assert "self._edit_material(owner_tag)" in delete_material
    assert "Reassign those references first." not in delete_material

    # 5: Deleting a referenced Transformation can create/select a replacement inline.
    delete_transformation = inspect.getsource(MainWindow._delete_transformation)
    assert "Reassign Transformation Now..." in delete_transformation
    assert "Create New Transformation..." in delete_transformation
    assert "_create_transformation_dependency" in delete_transformation
    assert "assign_transformation_to_elements" in delete_transformation
    assert "Transformation is assigned to element(s):" not in delete_transformation

