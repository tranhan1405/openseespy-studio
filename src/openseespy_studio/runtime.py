from __future__ import annotations

import os
from pathlib import Path


def studio_source_root() -> Path:
    """Return the source root that contains the openseespy_studio package."""
    return Path(__file__).resolve().parent.parent


def build_worker_pythonpath(existing: str = "") -> str:
    """Build PYTHONPATH for isolated Studio worker processes.

    Studio is often started directly with python run.py. In that mode run.py
    modifies only the GUI process sys.path. Child Python processes need the
    source root explicitly so python -m openseespy_studio.solver_worker works
    from a source checkout as well as from an installed package.
    """
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
