from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from types import ModuleType
from typing import Any, Protocol


class SolverBackend(Protocol):
    """Minimal FEWIZ solver boundary.

    GUI and Wizard code should depend on FEWIZ model/project objects and use a
    backend only when a solver-specific script or runtime is required.
    """

    backend_id: str
    display_name: str

    def render_script(self, model: Any, **kwargs: Any) -> str:
        """Render a solver-specific analysis script from a FEWIZ model."""
        ...


def load_openseespy_runtime() -> ModuleType:
    """Load the OpenSeesPy runtime lazily behind the FEWIZ solver boundary."""
    return import_module("openseespy.opensees")


@dataclass(frozen=True)
class OpenSeesPyBackend:
    """Current OpenSeesPy backend, preserving the existing generator behavior."""

    backend_id: str = "openseespy"
    display_name: str = "OpenSeesPy"

    def render_script(self, model: Any, **kwargs: Any) -> str:
        # Local import keeps the model layer independent from solver runtime
        # loading and avoids introducing an import cycle.
        from .generator import to_openseespy

        return to_openseespy(model, **kwargs)

    def runtime(self) -> ModuleType:
        return load_openseespy_runtime()


DEFAULT_SOLVER_BACKEND = OpenSeesPyBackend()


def get_solver_backend(backend_id: str = "openseespy") -> SolverBackend:
    """Return a registered solver backend.

    The registry is intentionally tiny in the first boundary increment.  New
    backends (for example Tcl/executable or a native solver) can be added here
    without changing GUI/Wizard code.
    """
    normalized = str(backend_id).strip().lower()
    if normalized == DEFAULT_SOLVER_BACKEND.backend_id:
        return DEFAULT_SOLVER_BACKEND
    raise ValueError(f"Unsupported solver backend: {backend_id}")
