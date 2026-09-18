from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


def studio_source_root() -> Path:
    """Return the source root that contains the openseespy_studio package."""
    return Path(__file__).resolve().parent.parent


def build_worker_pythonpath(existing: str = "") -> str:
    """Build PYTHONPATH for isolated Studio worker processes."""
    source_root = str(studio_source_root())
    parts = [
        part
        for part in str(existing or "").split(os.pathsep)
        if part
    ]
    normalized = {
        os.path.normcase(os.path.abspath(part))
        for part in parts
    }
    source_key = os.path.normcase(os.path.abspath(source_root))
    if source_key not in normalized:
        parts.insert(0, source_root)
    return os.pathsep.join(parts)


def opensees_python_requirement(
    platform_name: str | None = None,
    version: tuple[int, int] | None = None,
) -> str | None:
    platform_name = platform_name or sys.platform
    version = version or (sys.version_info.major, sys.version_info.minor)
    if platform_name == "win32" and version != (3, 12):
        return (
            "OpenSeesPy Studio on Windows requires Python 3.12. "
            f"Current interpreter is Python {version[0]}.{version[1]}."
        )
    return None


def probe_opensees_runtime(
    python_executable: str | None = None,
    *,
    timeout: float = 20.0,
) -> tuple[bool, str]:
    """Probe OpenSeesPy in a fresh process before launching a solver job."""
    requirement = opensees_python_requirement()
    if requirement:
        return False, requirement

    executable = python_executable or sys.executable
    env = os.environ.copy()
    env["PYTHONPATH"] = build_worker_pythonpath(
        env.get("PYTHONPATH", "")
    )
    command = (
        "import importlib.metadata as m; "
        "import openseespy.opensees as ops; "
        "print('openseespy=' + m.version('openseespy')); "
        "print('openseespywin=' + m.version('openseespywin'))"
        " if __import__('sys').platform == 'win32' else None
    )
    try:
        result = subprocess.run(
            [executable, "-c", command],
            env=env,
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"OpenSeesPy runtime probe could not start: {exc}"

    output = "\n".join(
        part.strip()
        for part in (result.stdout, result.stderr)
        if part and part.strip()
    )
    if result.returncode != 0:
        return False, output or (
            f"OpenSeesPy runtime probe failed with code {result.returncode}."
        )
    return True, output or "OpenSeesPy import succeeded."
