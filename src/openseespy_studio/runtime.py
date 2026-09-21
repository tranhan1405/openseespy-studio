from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


_WORKER_SWITCHES = {
    "openseespy_studio.solver_worker": "--solver-worker",
    "openseespy_studio.calibration_worker": "--calibration-worker",
}

_RUNTIME_MATERIAL_PROBES: dict[str, tuple[object, ...]] = {
    "FRPConfinedConcrete": (
        27.5, 27.5, 0.002, 400.0, 35.0, 266000.0,
        0.0, 0.222, 0.0163, 150.0, 374.0, 363.0,
        16.0, 6.0, 200000.0, 0.2, 0.8, 1.0,
    ),
}


def is_frozen_runtime() -> bool:
    return bool(getattr(sys, "frozen", False))


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


def packaged_worker_executable() -> Path:
    """Return the sibling console worker executable in a frozen build."""
    executable = Path(sys.executable).resolve()
    suffix = executable.suffix or (".exe" if sys.platform == "win32" else "")
    worker = executable.with_name(
        "OpenSeesPyStudioWorker" + suffix
    )
    if not worker.exists():
        raise RuntimeError(
            "Packaged solver worker is missing: "
            f"{worker.name}. Reinstall OpenSeesPy Studio."
        )
    return worker


def worker_process_command(
    module_name: str,
) -> tuple[str, list[str]]:
    """Return program/prefix arguments for source or frozen workers."""
    module = str(module_name)
    if is_frozen_runtime():
        try:
            switch = _WORKER_SWITCHES[module]
        except KeyError as exc:
            raise ValueError(
                f"Unsupported packaged worker module: {module}"
            ) from exc
        return str(packaged_worker_executable()), [switch]
    return sys.executable, ["-m", module]


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

    if is_frozen_runtime() and os.path.abspath(executable) == os.path.abspath(
        sys.executable
    ):
        executable = str(packaged_worker_executable())
        args = ["--runtime-probe"]
    else:
        command = (
            "import importlib.metadata as m, sys\n"
            "import openseespy.opensees as ops\n"
            "print('openseespy=' + m.version('openseespy'))\n"
            "if sys.platform == 'win32':\n"
            "    print('openseespywin=' + m.version('openseespywin'))\n"
        )
        args = ["-c", command]

    try:
        result = subprocess.run(
            [executable, *args],
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


def opensees_material_requires_runtime_probe(material_type: str) -> bool:
    """Return whether Studio has a targeted runtime capability probe."""
    return str(material_type) in _RUNTIME_MATERIAL_PROBES


def check_opensees_material_in_process(material_type: str) -> None:
    """Construct a material in the current OpenSees binary or raise."""
    kind = str(material_type)
    try:
        args = _RUNTIME_MATERIAL_PROBES[kind]
    except KeyError as exc:
        raise ValueError(
            f"No OpenSees runtime material probe is registered for {kind}."
        ) from exc

    import openseespy.opensees as ops

    ops.wipe()
    try:
        ops.uniaxialMaterial(kind, 2147483000, *args)
    finally:
        ops.wipe()


def probe_opensees_material_support(
    material_type: str,
    python_executable: str | None = None,
    *,
    timeout: float = 20.0,
) -> tuple[bool, str]:
    """Probe whether the active OpenSees binary actually contains a material."""
    kind = str(material_type)
    if kind not in _RUNTIME_MATERIAL_PROBES:
        return True, f"No targeted runtime probe is required for {kind}."

    requirement = opensees_python_requirement()
    if requirement:
        return False, requirement

    executable = python_executable or sys.executable
    env = os.environ.copy()
    env["PYTHONPATH"] = build_worker_pythonpath(
        env.get("PYTHONPATH", "")
    )

    if is_frozen_runtime() and os.path.abspath(executable) == os.path.abspath(
        sys.executable
    ):
        executable = str(packaged_worker_executable())
        args = ["--material-probe", kind]
    else:
        command = (
            "from openseespy_studio.runtime import "
            "check_opensees_material_in_process\n"
            f"check_opensees_material_in_process({kind!r})\n"
            f"print('material={kind}: supported')\n"
        )
        args = ["-c", command]

    try:
        result = subprocess.run(
            [executable, *args],
            env=env,
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, (
            f"OpenSees material probe for {kind} could not start: {exc}"
        )

    output = "\n".join(
        part.strip()
        for part in (result.stdout, result.stderr)
        if part and part.strip()
    )
    if result.returncode != 0:
        return False, output or (
            f"OpenSees material probe for {kind} failed with code "
            f"{result.returncode}."
        )
    return True, output or f"{kind} constructed successfully."
