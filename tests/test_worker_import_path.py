import os
import subprocess
import sys

from openseespy_studio.runtime import (
    build_worker_pythonpath,
    opensees_python_requirement,
    studio_source_root,
    worker_process_command,
)


def test_worker_pythonpath_prepends_source_root():
    existing = os.pathsep.join(["alpha", "beta"])
    value = build_worker_pythonpath(existing)
    parts = value.split(os.pathsep)

    assert parts[0] == str(studio_source_root())
    assert parts[1:] == ["alpha", "beta"]


def test_worker_pythonpath_does_not_duplicate_source_root():
    source = str(studio_source_root())
    value = build_worker_pythonpath(source)

    assert value.split(os.pathsep).count(source) == 1


def test_worker_module_imports_from_fresh_subprocess(tmp_path):
    env = os.environ.copy()
    env["PYTHONPATH"] = build_worker_pythonpath(
        env.get("PYTHONPATH", "")
    )

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import openseespy_studio.solver_worker as worker; "
                "print(worker.__name__)"
            ),
        ],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "openseespy_studio.solver_worker" in result.stdout


def test_windows_runtime_rejects_python_311():
    message = opensees_python_requirement("win32", (3, 11))
    assert message is not None
    assert "Python 3.12" in message


def test_windows_runtime_accepts_python_312():
    assert opensees_python_requirement("win32", (3, 12)) is None



def test_worker_process_command_uses_python_module_in_source_runtime(
    monkeypatch,
):
    monkeypatch.delattr(sys, "frozen", raising=False)

    program, prefix = worker_process_command(
        "openseespy_studio.solver_worker"
    )

    assert program == sys.executable
    assert prefix == ["-m", "openseespy_studio.solver_worker"]


def test_worker_process_command_uses_sibling_console_exe_when_frozen(
    monkeypatch,
    tmp_path,
):
    gui = tmp_path / "OpenSeesPyStudio.exe"
    worker = tmp_path / "OpenSeesPyStudioWorker.exe"
    gui.write_bytes(b"gui")
    worker.write_bytes(b"worker")
    monkeypatch.setattr(sys, "executable", str(gui))
    monkeypatch.setattr(sys, "frozen", True, raising=False)

    program, prefix = worker_process_command(
        "openseespy_studio.calibration_worker"
    )

    assert program == str(worker.resolve())
    assert prefix == ["--calibration-worker"]
