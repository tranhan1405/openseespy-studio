from __future__ import annotations

from copy import deepcopy
from typing import Callable

from PySide6.QtGui import QUndoCommand


class ProjectSnapshotCommand(QUndoCommand):
    """Undo command backed by complete project snapshots.

    This is intentionally conservative for the early project milestones. As
    editing grows, high-frequency operations can migrate to smaller commands
    without changing the public undo stack used by the main window.
    """

    def __init__(
        self,
        text: str,
        before: dict,
        after: dict,
        apply_snapshot: Callable[[dict], None],
        *,
        already_applied: bool = True,
    ):
        super().__init__(text)
        self._before = deepcopy(before)
        self._after = deepcopy(after)
        self._apply_snapshot = apply_snapshot
        self._skip_first_redo = already_applied

    def undo(self) -> None:
        self._apply_snapshot(deepcopy(self._before))

    def redo(self) -> None:
        if self._skip_first_redo:
            self._skip_first_redo = False
            return
        self._apply_snapshot(deepcopy(self._after))
