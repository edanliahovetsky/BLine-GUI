# mypy: ignore-errors
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QPoint
from PySide6.QtGui import (
    QAction,
    QIcon,
    QPen,
    QBrush,
    QColor,
    QPolygon,
    QPixmap,
)
from PySide6.QtWidgets import QMenu, QMenuBar

from ui.qt_compat import Qt, QKeySequence, QPainter

if TYPE_CHECKING:
    from ui.main_window.window import MainWindow


def build_menu_bar(window: "MainWindow") -> None:
    bar: QMenuBar = window.menuBar()
    bar.setVisible(True)
    bar.setNativeMenuBar(False)
    try:
        bar.setStyleSheet(
            """
            QMenuBar {
                background-color: #2f2f2f;
                border: none;
                border-bottom: 1px solid #4a4a4a;
                padding: 1px 6px;
                color: #eeeeee;
                font-size: 13px;
            }
            QMenuBar::item {
                background: transparent;
                padding: 3px 6px;
                margin: 0px 2px;
                border-radius: 4px;
                border-left: 1px solid #3b3b3b;
            }
            QMenuBar::item:selected {
                background: #555555;
            }
            QMenuBar::item:pressed {
                background: #666666;
            }

            QMenu {
                background-color: #242424;
                border: 1px solid #3f3f3f;
                color: #f0f0f0;
                padding: 3px 0;
            }
            QMenu::item {
                padding: 3px 10px;
                margin: 1px 3px;
                border-radius: 3px;
            }
            QMenu::item:selected {
                background: #555555;
            }
            QMenu::separator {
                height: 1px;
                margin: 2px 6px;
                background: #3b3b3b;
            }
            QMenu::indicator {
                width: 6px;
                height: 6px;
                margin-right: 10px;
                margin-left: 4px;
            }
            """
        )
    except Exception:
        pass

    project_menu: QMenu = bar.addMenu("Project")
    window.action_open_project = QAction("Open Project…", window)
    window.action_open_project.triggered.connect(window._action_open_project)
    project_menu.addAction(window.action_open_project)
    project_menu.addSeparator()

    window.menu_recent_projects = project_menu.addMenu("Recent Projects")
    window.menu_recent_projects.aboutToShow.connect(window._populate_recent_projects)

    path_menu: QMenu = bar.addMenu("Path")
    window.action_current_path = QAction("Current: (No Path)", window)
    window.action_current_path.setEnabled(False)
    path_menu.addAction(window.action_current_path)
    path_menu.addSeparator()

    window.menu_load_path = path_menu.addMenu("Load Path")
    window.menu_load_path.aboutToShow.connect(window._populate_load_path_menu)
    path_menu.addSeparator()

    window.action_new_path = QAction("Create New Path", window)
    window.action_new_path.triggered.connect(window._action_create_new_path)
    path_menu.addAction(window.action_new_path)
    path_menu.addSeparator()

    window.action_save_as = QAction("Save Path As…", window)
    window.action_save_as.triggered.connect(window._action_save_as)
    path_menu.addAction(window.action_save_as)
    path_menu.addSeparator()

    window.action_rename_path = QAction("Rename Path…", window)
    window.action_rename_path.triggered.connect(window._action_rename_path)
    path_menu.addAction(window.action_rename_path)
    path_menu.addSeparator()

    window.action_delete_path = QAction("Delete Paths…", window)
    window.action_delete_path.triggered.connect(window._show_delete_path_dialog)
    path_menu.addAction(window.action_delete_path)

    edit_menu: QMenu = bar.addMenu("Edit")
    window.action_undo = QAction(_create_arrow_icon("undo", 12), "Undo", window)
    window.action_undo.setShortcut(QKeySequence.Undo)
    window.action_undo.triggered.connect(window._action_undo)
    window.action_undo.setEnabled(False)
    edit_menu.addAction(window.action_undo)
    edit_menu.addSeparator()

    window.action_redo = QAction(_create_arrow_icon("redo", 12), "Redo", window)
    window.action_redo.setShortcut(QKeySequence.Redo)
    window.action_redo.triggered.connect(window._action_redo)
    window.action_redo.setEnabled(False)
    edit_menu.addAction(window.action_redo)

    settings_menu: QMenu = bar.addMenu("Settings")
    window.action_edit_config = QAction("Edit Config…", window)
    window.action_edit_config.triggered.connect(window._action_edit_config)
    settings_menu.addAction(window.action_edit_config)

    window.addAction(window.action_undo)
    window.addAction(window.action_redo)

    menu_bar = window.menuBar()
    menu_bar.setVisible(True)
    menu_bar.show()
    menu_bar.setMinimumHeight(30)
    menu_bar.setMaximumHeight(40)
    window.setMenuBar(menu_bar)
    menu_bar.raise_()
    menu_bar.update()
    window.update()


def _create_arrow_icon(direction: str, size: int = 16) -> QIcon:
    try:
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QColor("#333333"), 1)
        brush = QBrush(QColor("#333333"))
        painter.setPen(pen)
        painter.setBrush(brush)

        center_x, center_y = size // 2, size // 2
        arrow_size = size // 4

        if direction == "undo":
            arrow = QPolygon(
                [
                    QPoint(center_x - arrow_size, center_y),
                    QPoint(center_x + arrow_size // 2, center_y - arrow_size // 2),
                    QPoint(center_x + arrow_size // 2, center_y - arrow_size // 4),
                    QPoint(center_x, center_y),
                    QPoint(center_x + arrow_size // 2, center_y + arrow_size // 4),
                    QPoint(center_x + arrow_size // 2, center_y + arrow_size // 2),
                ]
            )
        else:
            arrow = QPolygon(
                [
                    QPoint(center_x + arrow_size, center_y),
                    QPoint(center_x - arrow_size // 2, center_y - arrow_size // 2),
                    QPoint(center_x - arrow_size // 2, center_y - arrow_size // 4),
                    QPoint(center_x, center_y),
                    QPoint(center_x - arrow_size // 2, center_y + arrow_size // 4),
                    QPoint(center_x - arrow_size // 2, center_y + arrow_size // 2),
                ]
            )

        painter.drawPolygon(arrow)
        painter.end()
        return QIcon(pixmap)
    except Exception:
        return QIcon()
