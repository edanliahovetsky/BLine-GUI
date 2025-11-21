"""Typing helpers for PySide6 enums/flags unavailable in stub metadata."""

from __future__ import annotations

from typing import Any, cast

from PySide6.QtCore import Qt as _Qt
from PySide6.QtGui import QKeySequence as _QKeySequence, QPainter as _QPainter
from PySide6.QtWidgets import (
    QDialogButtonBox as _QDialogButtonBox,
    QFormLayout as _QFormLayout,
    QGraphicsItem as _QGraphicsItem,
    QMessageBox as _QMessageBox,
    QSizePolicy as _QSizePolicy,
)

Qt = cast(Any, _Qt)
QSizePolicy = cast(Any, _QSizePolicy)
QDialogButtonBox = cast(Any, _QDialogButtonBox)
QGraphicsItem = cast(Any, _QGraphicsItem)
QMessageBox = cast(Any, _QMessageBox)
QKeySequence = cast(Any, _QKeySequence)
QPainter = cast(Any, _QPainter)
QFormLayoutRoles = cast(Any, _QFormLayout)

__all__ = [
    "Qt",
    "QSizePolicy",
    "QDialogButtonBox",
    "QGraphicsItem",
    "QMessageBox",
    "QKeySequence",
    "QPainter",
    "QFormLayoutRoles",
]

