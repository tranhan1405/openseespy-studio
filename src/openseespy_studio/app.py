from __future__ import annotations

import json
from importlib import resources
from importlib.metadata import PackageNotFoundError, version
import math
import sys
from typing import Any


_FALLBACK_VERSION = "0.2.0a1"


def package_version() -> str:
    try:
        return version("openseespy-studio")
    except PackageNotFoundError:
        return _FALLBACK_VERSION


def runtime_self_check() -> dict[str, Any]:
    """Verify packaged runtime dependencies and a tiny OpenSees solve."""
    import PySide6
    import pyvista
    import pyvistaqt
    import openseespy.opensees as ops

    resource = (
        resources.files("openseespy_studio")
        .joinpath("resources")
        .joinpath("ground_motions")
        .joinpath("elCentro_1940_NS.at2")
    )
    if not resource.is_file():
        raise RuntimeError(
            "Bundled ground-motion resource is missing: "
            "elCentro_1940_NS.at2"
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
    return {
        "studio_version": package_version(),
        "python": sys.version.split()[0],
        "pyside6": getattr(PySide6, "__version__", "unknown"),
        "pyvista": getattr(pyvista, "__version__", "unknown"),
        "pyvistaqt": getattr(pyvistaqt, "__version__", "unknown"),
        "opensees": str(opensees_version),
        "solver_smoke_displacement": displacement,
        "bundled_ground_motion": resource.name,
        "status": "ok",
    }


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)

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
