# mypy: ignore-errors
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QEvent, QTimer
from PySide6.QtWidgets import QWidget

if TYPE_CHECKING:
    from ui.main_window.window import MainWindow


class WindowEventMixin:
    def changeEvent(self: "MainWindow", event):
        if event.type() == QEvent.WindowStateChange:
            self._layout_stabilizing = True
            try:
                self.sidebar.set_suspended(True)
            except Exception:
                pass

            def _clear():
                setattr(self, "_layout_stabilizing", False)
                try:
                    self.sidebar.set_suspended(False)
                except Exception:
                    pass

            QTimer.singleShot(1000, _clear)
        super().changeEvent(event)

    def eventFilter(self: "MainWindow", obj, event):
        try:
            if event.type() in (QEvent.MouseButtonPress, QEvent.MouseButtonDblClick):
                target_widget = obj if isinstance(obj, QWidget) else None

                def _belongs_to_range_controls(widget: QWidget) -> bool:
                    try:
                        if widget is None:
                            return False
                        if (
                            hasattr(self.sidebar, "points_list")
                            and self.sidebar.points_list is not None
                        ):
                            pl = self.sidebar.points_list
                            curr = widget
                            steps = 0
                            max_steps = 100
                            while curr is not None and steps < max_steps:
                                if curr is pl:
                                    return False
                                curr = curr.parent() if hasattr(curr, "parent") else None
                                steps += 1
                        if hasattr(self.sidebar, "is_widget_range_related") and callable(
                            self.sidebar.is_widget_range_related
                        ):
                            curr = widget
                            steps = 0
                            max_steps = 100
                            while curr is not None and steps < max_steps:
                                if self.sidebar.is_widget_range_related(curr):
                                    return True
                                curr = curr.parent() if hasattr(curr, "parent") else None
                                steps += 1
                    except Exception:
                        return False
                    return False

                if not _belongs_to_range_controls(target_widget):
                    try:
                        self.sidebar.clear_active_preview()
                    except Exception:
                        pass
        except Exception:
            pass
        return super().eventFilter(obj, event)

    def showEvent(self: "MainWindow", event):
        super().showEvent(event)
        QTimer.singleShot(0, self.sidebar.mark_ready)
