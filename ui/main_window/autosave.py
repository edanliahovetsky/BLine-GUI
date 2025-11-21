# mypy: ignore-errors
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QLabel

from ui.qt_compat import Qt

if TYPE_CHECKING:
    from ui.main_window.window import MainWindow
    from ui.sidebar.sidebar import Sidebar
    from ui.canvas.view import CanvasView


class AutosaveController:
    """Encapsulates autosave timers, indicators, and feedback messaging."""

    def __init__(self, window: "MainWindow"):
        self.window = window
        self.timer = QTimer(window)
        self.timer.setSingleShot(True)
        self.timer.setInterval(300)
        self.timer.timeout.connect(self._perform_autosave)

        self.status_label = QLabel("Saved")
        self.status_label.setFixedSize(85, 20)
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet(self._saved_style())

        status_bar = window.statusBar
        status_bar.addPermanentWidget(self.status_label, stretch=0)

    def connect_triggers(self, sidebar: "Sidebar", canvas: "CanvasView") -> None:
        sidebar.modelChanged.connect(self.schedule)
        sidebar.modelStructureChanged.connect(self.schedule)
        canvas.elementDragFinished.connect(self.schedule)

    def schedule(self) -> None:
        """Debounce save events and show the busy indicator."""
        self.timer.start()
        self._show_indicator()

    def _perform_autosave(self) -> None:
        project_manager = self.window.project_manager
        if not project_manager.has_valid_project():
            self._hide_indicator()
            self._show_feedback("Autosave skipped: No valid project", error=True)
            return

        try:
            result = project_manager.save_path(self.window.path)
            if result is not None:
                self._hide_indicator()
                self._show_feedback("Autosaved successfully", error=False)
            else:
                self._hide_indicator()
                self._show_feedback("Autosave failed: Could not save path", error=True)
        except Exception as exc:  # pragma: no cover - guard rail
            self._hide_indicator()
            self._show_feedback(f"Autosave failed: {exc}", error=True)

    def _show_indicator(self) -> None:
        self.status_label.setText("💾 Saving...")
        self.status_label.setStyleSheet(self._saving_style())
        self.status_label.setAlignment(Qt.AlignCenter)

    def _hide_indicator(self) -> None:
        self._reset_status()

    def _show_feedback(self, message: str, error: bool = False) -> None:
        if error:
            self.status_label.setText("❌ Error")
            self.status_label.setStyleSheet(self._error_style())
            self.status_label.setAlignment(Qt.AlignCenter)
            QTimer.singleShot(2000, self._reset_status)
        else:
            self.status_label.setText("✅ Saved")
            self.status_label.setStyleSheet(self._success_style())
            self.status_label.setAlignment(Qt.AlignCenter)
            QTimer.singleShot(1500, self._reset_status)

    def _reset_status(self) -> None:
        self.status_label.setText("Saved")
        self.status_label.setStyleSheet(self._saved_style())
        self.status_label.setAlignment(Qt.AlignCenter)

    @staticmethod
    def _saving_style() -> str:
        return """
            QLabel {
                background-color: #3a2a1a;
                color: #d4a76a;
                border: 1px solid #c47a2d;
                border-radius: 4px;
                padding: 2px 6px;
                font-size: 10px;
                font-weight: 500;
                margin-right: 5px;
            }
        """

    @staticmethod
    def _error_style() -> str:
        return """
            QLabel {
                background-color: #3a1a1a;
                color: #c66b6b;
                border: 1px solid #b33d3d;
                border-radius: 4px;
                padding: 2px 6px;
                font-size: 10px;
                font-weight: 500;
                margin-right: 5px;
            }
        """

    @staticmethod
    def _success_style() -> str:
        return """
            QLabel {
                background-color: #1a3a1a;
                color: #7fb97f;
                border: 1px solid #5fa85f;
                border-radius: 4px;
                padding: 2px 6px;
                font-size: 10px;
                font-weight: 500;
                margin-right: 5px;
            }
        """

    @staticmethod
    def _saved_style() -> str:
        return """
            QLabel {
                background-color: #2a2a2a;
                color: #7fb97f;
                border: 1px solid #5fa85f;
                border-radius: 4px;
                padding: 2px 6px;
                font-size: 10px;
                font-weight: 500;
                margin-right: 5px;
            }
        """
