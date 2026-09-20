from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from openseespy_studio.generator import to_openseespy
from openseespy_studio.model import StructuralModel
from openseespy_studio.project import (
    AnalysisSettingsData,
    LoadPatternData,
    NodalLoadData,
    SectionData,
    TimeSeriesData,
    TransformationData,
)
from openseespy_studio.solver_worker import run_script
from openseespy_studio.ui.viewport import ModelViewport


pytestmark = pytest.mark.integration

if importlib.util.find_spec("openseespy") is None:
    pytest.skip(
        "OpenSeesPy runtime is not installed in the unit-test environment.",
        allow_module_level=True,
    )


def test_generated_static_cantilever_runs_in_real_opensees(tmp_path: Path):
    model = StructuralModel("real-opensees-smoke")
    model.add_node(1, 0.0, 0.0, 0.0)
    model.add_node(2, 0.0, 0.0, 3.0)
    model.set_fixity(1, (1, 1, 1, 1, 1, 1))
    model.add_element(
        1,
        1,
        2,
        section_tag=1,
        transf_tag=1,
    )

    sections = {
        1: SectionData(
            1,
            "Elastic column",
            "Elastic",
            parameters={
                "E": 200.0e9,
                "A": 0.02,
                "Iz": 8.0e-5,
                "Iy": 8.0e-5,
                "G": 80.0e9,
                "J": 1.0e-4,
            },
        )
    }
    transformations = {
        1: TransformationData(
            1,
            "Column",
            "Linear",
            (1.0, 0.0, 0.0),
        )
    }
    time_series = {
        1: TimeSeriesData(1, "Linear", "Linear", factor=1.0)
    }
    load_patterns = {
        1: LoadPatternData(
            1,
            "Lateral",
            "Plain",
            time_series_tag=1,
        )
    }
    nodal_loads = {
        1: NodalLoadData(
            1,
            "Top lateral",
            pattern_tag=1,
            node_tag=2,
            values=(1000.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        )
    }
    analysis = AnalysisSettingsData(
        1,
        "Static smoke",
        analysis_type="Static",
        constraints_handler="Plain",
        numberer="Plain",
        system="BandGeneral",
        test="NormDispIncr",
        tolerance=1.0e-12,
        max_iterations=20,
        algorithm="Newton",
        steps=1,
        load_increment=1.0,
        control_node=2,
        control_dof=1,
        recovery=False,
        adaptive_step=False,
        live_convergence=False,
    )

    script = to_openseespy(
        model,
        sections=sections,
        transformations=transformations,
        time_series=time_series,
        load_patterns=load_patterns,
        nodal_loads=nodal_loads,
        analyses={1: analysis},
        active_analysis_tag=1,
        units={"length": "m", "force": "N", "time": "s"},
    )
    assert "# ERROR:" not in script

    script_path = tmp_path / "cantilever.py"
    result_path = tmp_path / "cantilever-result.json"
    script_path.write_text(script, encoding="utf-8")

    exit_code = run_script(script_path, result_path)
    payload = json.loads(result_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert payload["status"] == "completed"
    results = payload["results"]
    assert results["analysis"]["type"] == "Static"
    assert results["convergence"]["steps"][0]["status"] in {
        "converged",
        "recovered",
    }

    displacement = results["final"]["node_displacements"]["2"][0]
    expected = 1000.0 * 3.0**3 / (
        3.0 * 200.0e9 * 8.0e-5
    )
    assert displacement == pytest.approx(expected, rel=1.0e-6)

    reaction = results["final"]["node_reactions"]["1"][0]
    assert reaction == pytest.approx(-1000.0, rel=1.0e-8)


def test_batched_centerline_mesh_contains_only_line_cells():
    model = StructuralModel("centerline-smoke")
    model.add_node(1, 0.0, 0.0, 0.0)
    model.add_node(2, 4.0, 0.0, 0.0)
    model.add_node(3, 4.0, 0.0, 3.0)
    model.add_element(11, 1, 2)
    model.add_element(12, 2, 3)

    mesh = ModelViewport._batched_centerline_mesh(model, [11, 12])

    assert mesh is not None
    assert mesh.n_points == 4
    assert mesh.n_lines == 2
    assert mesh.n_verts == 0
    assert mesh.n_cells == 2
    assert list(mesh.cell_data["element_tag"]) == [11, 12]
