from __future__ import annotations

from dataclasses import dataclass, field
from time import monotonic
from typing import Any


@dataclass
class JobRecord:
    job_id: int
    analysis_tag: int | None
    analysis_name: str
    analysis_type: str
    status: str = "Queued"
    started_at: float | None = None
    finished_at: float | None = None
    exit_code: int | None = None
    message: str = ""
    results: dict[str, Any] = field(default_factory=dict)

    def start(self) -> None:
        self.status = "Running"
        self.started_at = monotonic()
        self.finished_at = None
        self.exit_code = None
        self.message = ""

    def finish(
        self,
        status: str,
        *,
        exit_code: int | None = None,
        message: str = "",
        results: dict[str, Any] | None = None,
    ) -> None:
        self.status = str(status)
        self.finished_at = monotonic()
        self.exit_code = exit_code
        self.message = str(message)
        if results is not None:
            self.results = dict(results)

    @property
    def elapsed_seconds(self) -> float:
        if self.started_at is None:
            return 0.0
        end = self.finished_at if self.finished_at is not None else monotonic()
        return max(0.0, float(end - self.started_at))
