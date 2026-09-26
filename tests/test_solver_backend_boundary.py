from __future__ import annotations

import ast
from pathlib import Path

import pytest

from openseespy_studio import solver_backend


def test_default_solver_backend_is_openseespy() -> None:
    backend = solver_backend.get_solver_backend()
    assert backend is solver_backend.DEFAULT_SOLVER_BACKEND
    assert backend.backend_id == "openseespy"
    assert backend.display_name == "OpenSeesPy"


def test_unknown_solver_backend_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unsupported solver backend"):
        solver_backend.get_solver_backend("unknown")


def test_opensees_runtime_is_loaded_lazily(monkeypatch) -> None:
    marker = object()
    calls: list[str] = []

    def fake_import_module(name: str):
        calls.append(name)
        return marker

    monkeypatch.setattr(solver_backend, "import_module", fake_import_module)

    assert solver_backend.load_openseespy_runtime() is marker
    assert calls == ["openseespy.opensees"]


def test_ui_layer_does_not_import_openseespy_directly() -> None:
    package_root = Path(solver_backend.__file__).resolve().parent
    ui_root = package_root / "ui"

    violations: list[str] = []
    for path in sorted(ui_root.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("openseespy"):
                        violations.append(f"{path.name}:{node.lineno}")
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module.startswith("openseespy"):
                    violations.append(f"{path.name}:{node.lineno}")

    assert violations == [], (
        "GUI/Wizard modules must go through FEWIZ model/solver boundaries, "
        f"not import OpenSeesPy directly: {violations}"
    )
