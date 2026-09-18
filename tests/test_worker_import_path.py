import os
import subprocess
import sys

from openseespy_studio.runtime import (
    build_worker_pythonpath,
    studio_source_root,
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
