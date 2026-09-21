from __future__ import annotations

from types import SimpleNamespace

from openseespy_studio.ai_assistant import (
    OpenAIProvider,
    execute_read_only_tool,
    prepare_project_snapshot,
    project_summary,
)


def _snapshot():
    project = {
        "name": "AI test",
        "units": {"length": "mm", "force": "N", "time": "s"},
        "model": {
            "name": "column",
            "ndm": 2,
            "ndf": 3,
            "nodes": [
                {"tag": 1, "xyz": [0.0, 0.0, 0.0], "fixity": [1, 1, 1], "mass": [0, 0, 0]},
                {"tag": 2, "xyz": [0.0, 3000.0, 0.0], "fixity": [0, 0, 0], "mass": [1, 1, 0]},
            ],
            "elements": [
                {
                    "tag": 1,
                    "i": 1,
                    "j": 2,
                    "element_type": "dispBeamColumn",
                    "section_tag": 1,
                    "transf_tag": 1,
                }
            ],
        },
        "materials": [
            {
                "tag": 1,
                "name": "Steel",
                "material_type": "Steel02",
                "parameters": {"Fy": 355.0, "E0": 200000.0},
            }
        ],
        "sections": [
            {
                "tag": 1,
                "name": "Fiber",
                "section_type": "Fiber",
                "parameters": {"GJ": 1.0},
                "fibers": [
                    {"y": float(i), "z": 0.0, "area": 1.0, "material_tag": 1}
                    for i in range(100)
                ],
            }
        ],
        "transformations": [{"tag": 1, "name": "Linear", "transformation_type": "Linear"}],
        "constraints": [],
        "connections": [],
        "time_series": [
            {
                "tag": 1,
                "name": "Record",
                "series_type": "Path",
                "dt": 0.01,
                "values": [float(i) for i in range(100)],
            }
        ],
        "load_patterns": [],
        "nodal_loads": [],
        "prescribed_displacements": [],
        "element_loads": [],
        "mass_sources": [],
        "analyses": [
            {
                "tag": 1,
                "name": "Cyclic",
                "analysis_type": "Cyclic",
                "control_node": 2,
                "control_dof": 1,
            }
        ],
        "recorders": [],
        "solution_results": [],
        "active_analysis_tag": 1,
    }
    return {
        "project": prepare_project_snapshot(project),
        "selection": {"nodes": [2], "elements": [1]},
        "validation": [
            {
                "severity": "WARNING",
                "category": "Test",
                "message": "Example warning",
            }
        ],
        "jobs": [
            {
                "job_id": 7,
                "analysis_type": "Cyclic",
                "status": "Completed",
                "results": {"peak": 123.0},
            }
        ],
        "solver_log": "analysis completed",
        "focus": {"kind": "element", "value": 1},
    }


def test_project_snapshot_compacts_large_engineering_arrays():
    snapshot = _snapshot()
    project = snapshot["project"]

    series = project["time_series"][0]
    assert "values" not in series
    assert series["value_summary"]["count"] == 100
    assert series["value_summary"]["min"] == 0.0
    assert series["value_summary"]["max"] == 99.0

    section = project["sections"][0]
    assert section["fiber_count"] == 100
    assert len(section["fibers"]) == 40
    assert section["fibers_truncated"] is True


def test_read_only_tools_return_selection_analysis_and_diagnostics():
    snapshot = _snapshot()

    summary = project_summary(snapshot)
    assert summary["model"]["node_count"] == 2
    assert summary["model"]["element_count"] == 1
    assert summary["active_analysis_tag"] == 1

    selection = execute_read_only_tool("get_selection", {}, snapshot)
    assert selection["node_tags"] == [2]
    assert selection["element_tags"] == [1]
    assert selection["elements"][0]["section"]["tag"] == 1

    node = execute_read_only_tool("get_node", {"tag": 2}, snapshot)
    assert node["found"] is True
    assert node["node"]["xyz"][1] == 3000.0
    assert node["connected_elements"] == [1]

    element = execute_read_only_tool(
        "get_element",
        {"tag": 1},
        snapshot,
    )
    assert element["found"] is True
    assert element["element"]["section"]["tag"] == 1
    assert element["element"]["transformation"]["tag"] == 1

    material = execute_read_only_tool("get_material", {"tag": 1}, snapshot)
    assert material["found"] is True
    assert material["material"]["material_type"] == "Steel02"

    analysis = execute_read_only_tool("get_analysis", {}, snapshot)
    assert analysis["found"] is True
    assert analysis["analysis"]["analysis_type"] == "Cyclic"

    issues = execute_read_only_tool("get_validation_issues", {}, snapshot)
    assert issues["issues"][0]["severity"] == "WARNING"

    job = execute_read_only_tool("get_job_results", {}, snapshot)
    assert job["job"]["job_id"] == 7

    log = execute_read_only_tool("get_solver_log", {}, snapshot)
    assert "completed" in log["tail"]


class _FakeResponses:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if len(self.calls) == 1:
            return SimpleNamespace(
                id="response-1",
                output_text="",
                output=[
                    SimpleNamespace(
                        type="function_call",
                        name="get_model_summary",
                        arguments="{}",
                        call_id="call-1",
                    )
                ],
            )
        return SimpleNamespace(
            id="response-2",
            output_text="The model contains two nodes and one element.",
            output=[],
        )


class _FakeClient:
    def __init__(self):
        self.responses = _FakeResponses()


def test_openai_provider_executes_read_only_function_call_round_trip():
    client = _FakeClient()
    provider = OpenAIProvider(
        model="test-model",
        client=client,
    )

    answer = provider.ask(
        "Summarize the model.",
        snapshot=_snapshot(),
        history=[],
    )

    assert "two nodes" in answer
    assert len(client.responses.calls) == 2

    first = client.responses.calls[0]
    assert first["model"] == "test-model"
    assert first["tools"]
    assert first["store"] is False

    second = client.responses.calls[1]
    assert "previous_response_id" not in second
    assert second["store"] is False
    tool_outputs = [
        item
        for item in second["input"]
        if isinstance(item, dict)
        and item.get("type") == "function_call_output"
    ]
    assert len(tool_outputs) == 1
    assert tool_outputs[0]["call_id"] == "call-1"
    assert "node_count" in tool_outputs[0]["output"]
    assert any(
        getattr(item, "type", "") == "function_call"
        for item in second["input"]
    )


def test_optional_tool_ids_fail_closed_instead_of_raising():
    snapshot = _snapshot()

    analysis = execute_read_only_tool(
        "get_analysis",
        {"tag": "not-a-tag"},
        snapshot,
    )
    assert "error" in analysis

    job = execute_read_only_tool(
        "get_job_results",
        {"job_id": "not-a-job"},
        snapshot,
    )
    assert job["found"] is False
