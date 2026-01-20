"""Shared data models for the GUI."""

# Re-export key types for convenience when importing the package directly.
from .path_model import Path, PathElement, RotationTarget, TranslationTarget, Waypoint, EventTrigger

__all__ = [
    "Path",
    "PathElement",
    "RotationTarget",
    "TranslationTarget",
    "Waypoint",
    "EventTrigger",
]
