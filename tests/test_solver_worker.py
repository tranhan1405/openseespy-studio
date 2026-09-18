from openseespy_studio.solver_worker import run_script


def test_worker_runs_python_script(tmp_path):
    script = tmp_path / "ok.py"
    script.write_text("print('hello worker')\n", encoding="utf-8")
    assert run_script(script) == 0


def test_worker_reports_python_exception(tmp_path):
    script = tmp_path / "bad.py"
    script.write_text("raise RuntimeError('boom')\n", encoding="utf-8")
    assert run_script(script) == 1
