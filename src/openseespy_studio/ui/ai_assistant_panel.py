from __future__ import annotations

from typing import Any

from PySide6.QtCore import QObject, QThread, Signal, Slot
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..ai_assistant import OllamaProvider, OpenAIProvider


class _AssistantWorker(QObject):
    finished = Signal(str)
    failed = Signal(str)

    def __init__(
        self,
        *,
        prompt: str,
        snapshot: dict[str, Any],
        history: list[dict[str, str]],
        provider: str,
        model: str,
        api_key: str,
        ollama_host: str,
    ):
        super().__init__()
        self.prompt = str(prompt)
        self.snapshot = snapshot
        self.history = history
        self.provider = str(provider)
        self.model = str(model)
        self.api_key = str(api_key)
        self.ollama_host = str(ollama_host)

    @Slot()
    def run(self) -> None:
        try:
            if self.provider == "ollama":
                provider = OllamaProvider(
                    model=self.model,
                    host=self.ollama_host,
                )
            else:
                provider = OpenAIProvider(
                    model=self.model,
                    api_key=self.api_key or None,
                )
            answer = provider.ask(
                self.prompt,
                snapshot=self.snapshot,
                history=self.history,
            )
        except BaseException as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")
            return
        self.finished.emit(answer)


class AIAssistantPanel(QWidget):
    send_requested = Signal(str, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._history: list[dict[str, str]] = []
        self._thread: QThread | None = None
        self._worker: _AssistantWorker | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 7, 8, 8)
        root.setSpacing(6)

        title = QLabel("SARE AI Assistant")
        title.setObjectName("PanelTitle")
        root.addWidget(title)

        note = QLabel(
            "Read-only engineering assistant. It can inspect the local SARE "
            "snapshot through controlled tools, but cannot modify or run the model."
        )
        note.setWordWrap(True)
        note.setObjectName("Muted")
        root.addWidget(note)

        settings = QFormLayout()
        settings.setContentsMargins(0, 0, 0, 0)
        settings.setVerticalSpacing(4)

        self.provider = QComboBox()
        self.provider.addItem("Ollama (Local · Free)", "ollama")
        self.provider.addItem("OpenAI (API)", "openai")
        self.provider.currentIndexChanged.connect(
            self._provider_changed
        )
        settings.addRow("Provider:", self.provider)

        self.model = QComboBox()
        self.model.setEditable(True)
        settings.addRow("Model:", self.model)

        self.ollama_host = QLineEdit("http://localhost:11434")
        self.ollama_host.setToolTip(
            "Local Ollama API address. The free provider is restricted to "
            "localhost/loopback addresses so project context stays on this PC."
        )
        settings.addRow("Local host:", self.ollama_host)

        self.api_key = QLineEdit()
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key.setPlaceholderText("OPENAI_API_KEY or session key")
        self.api_key.setToolTip(
            "Optional session-only API key. If blank, SARE reads "
            "OPENAI_API_KEY from the environment. The key is not saved "
            "in the project."
        )
        settings.addRow("API key:", self.api_key)
        root.addLayout(settings)

        self.focus = QLabel("Context: current model")
        self.focus.setWordWrap(True)
        self.focus.setObjectName("Muted")
        root.addWidget(self.focus)

        context_row = QHBoxLayout()
        self.include_selection = QCheckBox("Selection")
        self.include_analysis = QCheckBox("Analysis")
        self.include_validation = QCheckBox("Validation")
        self.include_job = QCheckBox("Jobs")
        self.include_log = QCheckBox("Solver Log")
        for checkbox in (
            self.include_selection,
            self.include_analysis,
            self.include_validation,
            self.include_job,
            self.include_log,
        ):
            checkbox.setChecked(True)
            context_row.addWidget(checkbox)
        root.addLayout(context_row)

        self.transcript = QPlainTextEdit()
        self.transcript.setReadOnly(True)
        self.transcript.setPlaceholderText(
            "Ask about the selected element, material, analysis, validation "
            "issues, convergence, or captured Job results."
        )
        root.addWidget(self.transcript, 1)

        self.input = QPlainTextEdit()
        self.input.setMaximumHeight(92)
        self.input.setPlaceholderText(
            "Ask SARE... e.g. Why did this cyclic analysis fail?"
        )
        root.addWidget(self.input)

        button_row = QHBoxLayout()
        self.clear_button = QPushButton("Clear")
        self.clear_button.clicked.connect(self.clear_chat)
        button_row.addWidget(self.clear_button)
        button_row.addStretch(1)
        self.send_button = QPushButton("Send")
        self.send_button.setObjectName("PrimaryButton")
        self.send_button.clicked.connect(self._emit_send)
        button_row.addWidget(self.send_button)
        root.addLayout(button_row)

        self.status = QLabel(
            "API key is never stored in the SARE project."
        )
        self.status.setObjectName("Muted")
        self.status.setWordWrap(True)
        root.addWidget(self.status)

        self._provider_changed()

    def _provider_changed(self) -> None:
        provider = str(self.provider.currentData() or "ollama")
        current = self.model.currentText().strip()
        self.model.blockSignals(True)
        try:
            self.model.clear()
            if provider == "openai":
                self.model.addItems([
                    "gpt-5.6-luna",
                    "gpt-5.6-terra",
                    "gpt-5.6-sol",
                ])
                self.model.setCurrentText(
                    current if current.startswith("gpt-") else "gpt-5.6-luna"
                )
                self.model.setToolTip(
                    "OpenAI Responses API model ID."
                )
                self.api_key.setEnabled(True)
                self.ollama_host.setEnabled(False)
                self.status.setText(
                    "OpenAI API mode · API usage is billed separately."
                )
            else:
                self.model.addItems([
                    "qwen3.5:4b",
                    "qwen3.5:9b",
                    "qwen3:4b",
                    "qwen3:8b",
                ])
                self.model.setCurrentText(
                    current
                    if (
                        current.startswith("qwen")
                        or "/" in current
                    )
                    else "qwen3.5:4b"
                )
                self.model.setToolTip(
                    "Local Ollama model. qwen3.5:4b is the lightweight "
                    "default with tool-calling support."
                )
                self.api_key.setEnabled(False)
                self.ollama_host.setEnabled(True)
                self.status.setText(
                    "Free local mode · requires Ollama and a downloaded model."
                )
        finally:
            self.model.blockSignals(False)

    def _append_turn(self, role: str, text: str) -> None:
        label = "You" if role == "user" else "SARE AI"
        if self.transcript.toPlainText().strip():
            self.transcript.appendPlainText("")
        self.transcript.appendPlainText(f"{label}:")
        self.transcript.appendPlainText(str(text).strip())
        cursor = self.transcript.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.transcript.setTextCursor(cursor)

    def _emit_send(self) -> None:
        if self._thread is not None:
            return
        prompt = self.input.toPlainText().strip()
        if not prompt:
            return

        history_before = [dict(item) for item in self._history[-12:]]
        self._history.append({"role": "user", "content": prompt})
        self._append_turn("user", prompt)
        self.input.clear()

        config = {
            "provider": str(self.provider.currentData()),
            "model": self.model.currentText().strip(),
            "api_key": self.api_key.text().strip(),
            "ollama_host": self.ollama_host.text().strip(),
            "include_selection": self.include_selection.isChecked(),
            "include_analysis": self.include_analysis.isChecked(),
            "include_validation": self.include_validation.isChecked(),
            "include_job": self.include_job.isChecked(),
            "include_log": self.include_log.isChecked(),
            "history": history_before,
        }
        self.set_busy(True, "Preparing local SARE context...")
        self.send_requested.emit(prompt, config)

    def run_request(
        self,
        prompt: str,
        config: dict[str, Any],
        snapshot: dict[str, Any],
    ) -> None:
        if self._thread is not None:
            return
        if str(config.get("provider", "ollama")) not in {
            "ollama",
            "openai",
        }:
            self.fail_request("Unsupported LLM provider.")
            return

        thread = QThread(self)
        worker = _AssistantWorker(
            prompt=str(prompt),
            snapshot=snapshot,
            history=list(config.get("history", [])),
            provider=str(config.get("provider", "ollama")),
            model=str(config.get("model", "qwen3.5:4b")),
            api_key=str(config.get("api_key", "")),
            ollama_host=str(
                config.get(
                    "ollama_host",
                    "http://localhost:11434",
                )
            ),
        )
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._request_finished)
        worker.failed.connect(self._request_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        thread.finished.connect(self._thread_finished)
        thread.finished.connect(thread.deleteLater)
        self._thread = thread
        self._worker = worker
        provider_label = (
            "local Ollama"
            if str(config.get("provider", "ollama")) == "ollama"
            else "OpenAI"
        )
        self.set_busy(True, f"Asking {provider_label}...")
        thread.start()

    @Slot(str)
    def _request_finished(self, answer: str) -> None:
        text = str(answer).strip()
        self._history.append({"role": "assistant", "content": text})
        self._append_turn("assistant", text)
        self.status.setText("Ready · read-only response")

    @Slot(str)
    def _request_failed(self, detail: str) -> None:
        message = str(detail).strip()
        self._append_turn("assistant", "Request failed: " + message)
        self.status.setText("AI request failed")

    @Slot()
    def _thread_finished(self) -> None:
        self._thread = None
        self._worker = None
        self.set_busy(False)

    def fail_request(self, detail: str) -> None:
        """Report a request/setup failure even if no worker thread was started."""
        self._request_failed(str(detail))
        if self._thread is None:
            self.set_busy(False)

    def set_busy(self, busy: bool, message: str | None = None) -> None:
        busy = bool(busy)
        self.send_button.setEnabled(not busy)
        self.provider.setEnabled(not busy)
        self.model.setEnabled(not busy)
        is_openai = str(self.provider.currentData()) == "openai"
        self.api_key.setEnabled((not busy) and is_openai)
        self.ollama_host.setEnabled((not busy) and not is_openai)
        if message:
            self.status.setText(str(message))

    def clear_chat(self) -> None:
        if self._thread is not None:
            return
        self._history.clear()
        self.transcript.clear()
        self.status.setText("Chat cleared · local model context is unchanged")

    def set_focus(self, kind: str | None, value: Any = None) -> None:
        if kind:
            self.focus.setText(f"Context focus: {kind} {value}")
        else:
            self.focus.setText("Context: current model")

    def prefill_question(self, text: str) -> None:
        self.input.setPlainText(str(text))
        self.input.setFocus()
