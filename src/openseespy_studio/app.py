from __future__ import annotations

import json
from importlib import resources
from importlib.metadata import PackageNotFoundError, version
import math
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any


_FALLBACK_VERSION = "0.2.0a1"


def package_version() -> str:
    try:
        return version("openseespy-studio")
    except PackageNotFoundError:
        return _FALLBACK_VERSION


def _runtime_probe() -> int:
    try:
        import importlib.metadata as metadata
        import openseespy.opensees as ops

        print(f"openseespy={metadata.version('openseespy')}")
        if sys.platform == "win32":
            print(f"openseespywin={metadata.version('openseespywin')}")
        print(f"OpenSees={ops.version()}")
        return 0
    except BaseException as exc:
        print(
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
            flush=True,
        )
        return 2


def _packaged_worker_self_check() -> dict[str, Any]:
    from .runtime import worker_process_command

    script_source = """import openseespy.opensees as ops
ops.wipe()
ops.model('basic', '-ndm', 2, '-ndf', 2)
ops.node(1, 0.0, 0.0)
ops.node(2, 1.0, 0.0)
ops.fix(1, 1, 1)
ops.fix(2, 0, 1)
ops.uniaxialMaterial('Elastic', 1, 1000.0)
ops.element('truss', 1, 1, 2, 1.0, 1)
ops.timeSeries('Linear', 1)
ops.pattern('Plain', 1, 1)
ops.load(2, 1.0, 0.0)
ops.system('BandGeneral')
ops.numberer('Plain')
ops.constraints('Plain')
ops.integrator('LoadControl', 1.0)
ops.algorithm('Linear')
ops.analysis('Static')
_code = int(ops.analyze(1))
if _code != 0:
    raise RuntimeError(f'worker smoke analyze returned {_code}')
_studio_results = {
    'worker_smoke_displacement': float(ops.nodeDisp(2, 1)),
}
ops.wipe()
"""

    with tempfile.TemporaryDirectory(
        prefix="openseespy_studio_worker_check_"
    ) as directory:
        root = Path(directory)
        script_path = root / "worker_smoke.py"
        result_path = root / "worker_smoke_result.json"
        script_path.write_text(script_source, encoding="utf-8")

        program, prefix = worker_process_command(
            "openseespy_studio.solver_worker"
        )
        completed = subprocess.run(
            [
                program,
                *prefix,
                str(script_path),
                "--result-file",
                str(result_path),
            ],
            text=True,
            capture_output=True,
            check=False,
            timeout=30.0,
        )
        if completed.returncode != 0:
            detail = "\n".join(
                part.strip()
                for part in (completed.stdout, completed.stderr)
                if part and part.strip()
            )
            raise RuntimeError(
                "Packaged solver-worker smoke process failed"
                + (f": {detail}" if detail else ".")
            )
        if not result_path.exists():
            raise RuntimeError(
                "Packaged solver worker did not create its result file."
            )
        payload = json.loads(
            result_path.read_text(encoding="utf-8")
        )
        if payload.get("status") != "completed":
            raise RuntimeError(
                "Packaged solver worker returned an incomplete result."
            )
        displacement = float(
            payload.get("results", {}).get(
                "worker_smoke_displacement",
                math.nan,
            )
        )
        if not math.isclose(
            displacement,
            0.001,
            rel_tol=1.0e-8,
            abs_tol=1.0e-12,
        ):
            raise RuntimeError(
                "Packaged solver-worker displacement mismatch: "
                f"{displacement:g}."
            )

    return {
        "packaged_worker_status": "ok",
        "packaged_worker_displacement": displacement,
    }


def runtime_self_check() -> dict[str, Any]:
    """Verify runtime dependencies, resources and a tiny OpenSees solve."""
    import PySide6
    import pyvista
    import pyvistaqt
    import openseespy.opensees as ops

    from .ground_motion_library import (
        available_ground_motion_presets,
        load_bundled_ground_motion_record,
    )
    from .runtime import is_frozen_runtime

    offline_records = [
        preset
        for preset in available_ground_motion_presets(
            include_custom=False
        )
        if preset.bundled_resource
    ]
    if not offline_records:
        raise RuntimeError(
            "No bundled offline ground-motion records are available."
        )
    for preset in offline_records:
        record = load_bundled_ground_motion_record(preset.key)
        if not record.values or record.dt is None or record.dt <= 0.0:
            raise RuntimeError(
                "Bundled ground-motion record is invalid or missing: "
                f"{preset.key}"
            )

    try:
        ops.wipe()
        ops.model("basic", "-ndm", 2, "-ndf", 2)
        ops.node(1, 0.0, 0.0)
        ops.node(2, 1.0, 0.0)
        ops.fix(1, 1, 1)
        ops.fix(2, 0, 1)
        ops.uniaxialMaterial("Elastic", 1, 1000.0)
        ops.element("truss", 1, 1, 2, 1.0, 1)
        ops.timeSeries("Linear", 1)
        ops.pattern("Plain", 1, 1)
        ops.load(2, 1.0, 0.0)
        ops.system("BandGeneral")
        ops.numberer("Plain")
        ops.constraints("Plain")
        ops.integrator("LoadControl", 1.0)
        ops.algorithm("Linear")
        ops.analysis("Static")
        code = int(ops.analyze(1))
        if code != 0:
            raise RuntimeError(
                f"OpenSees runtime smoke analysis returned code {code}."
            )
        displacement = float(ops.nodeDisp(2, 1))
        expected = 1.0 / 1000.0
        if not math.isclose(
            displacement,
            expected,
            rel_tol=1.0e-8,
            abs_tol=1.0e-12,
        ):
            raise RuntimeError(
                "OpenSees runtime smoke displacement mismatch: "
                f"{displacement:g} != {expected:g}."
            )
    finally:
        ops.wipe()

    opensees_version = getattr(ops, "version", lambda: "unknown")()
    payload: dict[str, Any] = {
        "studio_version": package_version(),
        "python": sys.version.split()[0],
        "pyside6": getattr(PySide6, "__version__", "unknown"),
        "pyvista": getattr(pyvista, "__version__", "unknown"),
        "pyvistaqt": getattr(pyvistaqt, "__version__", "unknown"),
        "opensees": str(opensees_version),
        "solver_smoke_displacement": displacement,
        "bundled_ground_motion_count": len(offline_records),
        "bundled_ground_motions": [
            preset.key for preset in offline_records
        ],
        "frozen": is_frozen_runtime(),
        "status": "ok",
    }
    if is_frozen_runtime():
        payload.update(_packaged_worker_self_check())
    return payload


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)

    if args and args[0] == "--solver-worker":
        from .solver_worker import main as solver_main

        return solver_main(args[1:])

    if args and args[0] == "--calibration-worker":
        from .calibration_worker import main as calibration_main

        return calibration_main(args[1:])

    if args and args[0] == "--runtime-probe":
        return _runtime_probe()

    if "--version" in args:
        print(package_version())
        return 0

    if "--self-check" in args:
        try:
            payload = runtime_self_check()
        except BaseException as exc:
            print(
                json.dumps(
                    {
                        "status": "failed",
                        "error": f"{type(exc).__name__}: {exc}",
                    },
                    ensure_ascii=False,
                ),
                file=sys.stderr,
                flush=True,
            )
            return 2
        print(
            json.dumps(payload, ensure_ascii=False, sort_keys=True),
            flush=True,
        )
        return 0

    from PySide6.QtWidgets import QApplication, QMessageBox

    from .ui.icons import app_icon
    from .ui.main_window import MainWindow

    qt_argv = [sys.argv[0], *args]
    app = QApplication(qt_argv)
    app.setApplicationName("OpenSeesPy Studio")
    app.setApplicationVersion(package_version())
    app.setWindowIcon(app_icon())
    app.setStyle("Fusion")
    try:
        window = MainWindow()
    except RuntimeError as exc:
        QMessageBox.critical(None, "Startup error", str(exc))
        return 1
    window.show()
    return app.exec()
