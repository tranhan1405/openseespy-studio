import json

from openseespy_studio.solver_worker import run_script


def test_worker_runs_python_script(tmp_path):
    script = tmp_path / "ok.py"
    script.write_text("print('hello worker')\n", encoding="utf-8")
    assert run_script(script) == 0


def test_worker_reports_python_exception(tmp_path):
    script = tmp_path / "bad.py"
    script.write_text("raise RuntimeError('boom')\n", encoding="utf-8")
    assert run_script(script) == 1


def test_worker_writes_structured_results(tmp_path):
    script = tmp_path / "results.py"
    result = tmp_path / "result.json"
    script.write_text(
        "_studio_results = {'analysis': {'type': 'Static'}, "
        "'final': {'node_displacements': {'1': [1, 2, 3]}}}\n",
        encoding="utf-8",
    )

    assert run_script(script, result) == 0

    payload = json.loads(result.read_text(encoding="utf-8"))
    assert payload["status"] == "completed"
    assert payload["results"]["analysis"]["type"] == "Static"
    assert payload["results"]["final"]["node_displacements"]["1"] == [1, 2, 3]


def test_worker_writes_failure_payload(tmp_path):
    script = tmp_path / "partial.py"
    result = tmp_path / "result.json"
    script.write_text(
        "_studio_results = {'history': {'time': [0.1]}}\n"
        "raise RuntimeError('boom')\n",
        encoding="utf-8",
    )

    assert run_script(script, result) == 1

    payload = json.loads(result.read_text(encoding="utf-8"))
    assert payload["status"] == "failed"
    assert payload["results"]["history"]["time"] == [0.1]
    assert "RuntimeError: boom" in payload["error"]
