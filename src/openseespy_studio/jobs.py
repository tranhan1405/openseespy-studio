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
    project_signature: str = ""
    status: str = "Queued"
    started_at: float | None = None
    finished_at: float | None = None
    exit_code: int | None = None
    message: str = ""
    progress_current: int = 0
    progress_total: int = 0
    progress_percent: float = 0.0
    current_algorithm: str = ""
    iterations: int = 0
    results: dict[str, Any] = field(default_factory=dict)
    plots: list[dict[str, Any]] = field(default_factory=list)

    def start(self) -> None:
        self.status = "Running"
        self.started_at = monotonic()
        self.finished_at = None
        self.exit_code = None
        self.message = ""
        self.progress_current = 0
        self.progress_total = 0
        self.progress_percent = 0.0
        self.current_algorithm = ""
        self.iterations = 0

    def update_progress(
        self,
        current: int,
        total: int,
        *,
        algorithm: str = "",
        iterations: int = 0,
        message: str = "",
    ) -> None:
        self.progress_current = max(0, int(current))
        self.progress_total = max(0, int(total))
        if self.progress_total > 0:
            self.progress_percent = min(
                100.0,
                max(
                    0.0,
                    100.0
                    * self.progress_current
                    / self.progress_total,
                ),
            )
        else:
            self.progress_percent = 0.0
        self.current_algorithm = str(algorithm)
        self.iterations = max(0, int(iterations))
        if message:
            self.message = str(message)

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
        if status == "Completed" and self.progress_total > 0:
            self.progress_current = self.progress_total
            self.progress_percent = 100.0
        if results is not None:
            self.results = dict(results)

    def next_plot_id(self) -> int:
        return max(
            (
                int(plot.get("plot_id", 0) or 0)
                for plot in self.plots
                if isinstance(plot, dict)
            ),
            default=0,
        ) + 1

    def add_plot(
        self,
        *,
        name: str,
        result_type: str,
        settings: dict[str, Any] | None = None,
        node_scope: list[int] | None = None,
        element_scope: list[int] | None = None,
    ) -> dict[str, Any]:
        base_name = str(name).strip() or "Result"
        existing = {
            str(plot.get("name", ""))
            for plot in self.plots
            if isinstance(plot, dict)
        }
        unique_name = base_name
        suffix = 2
        while unique_name in existing:
            unique_name = f"{base_name} {suffix}"
            suffix += 1

        plot = {
            "plot_id": self.next_plot_id(),
            "name": unique_name,
            "result_type": str(result_type),
            "settings": dict(settings or {}),
            "node_scope": sorted(
                {int(tag) for tag in (node_scope or [])}
            ),
            "element_scope": sorted(
                {int(tag) for tag in (element_scope or [])}
            ),
        }
        self.plots.append(plot)
        return plot

    def plot(self, plot_id: int) -> dict[str, Any] | None:
        target = int(plot_id)
        for plot in self.plots:
            if (
                isinstance(plot, dict)
                and int(plot.get("plot_id", 0) or 0) == target
            ):
                return plot
        return None

    def remove_plot(self, plot_id: int) -> None:
        target = int(plot_id)
        self.plots = [
            plot
            for plot in self.plots
            if not (
                isinstance(plot, dict)
                and int(plot.get("plot_id", 0) or 0) == target
            )
        ]

    @property
    def elapsed_seconds(self) -> float:
        if self.started_at is None:
            return 0.0
        end = self.finished_at if self.finished_at is not None else monotonic()
        return max(0.0, float(end - self.started_at))
