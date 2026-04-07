from __future__ import annotations

from typing import List, Tuple

from models.path_model import (
    EventTrigger,
    Path,
    PathElement,
    RotationTarget,
    TranslationTarget,
    Waypoint,
)

from .constants import TRANSLATION_CONSTRAINT_KEYS


def get_constraint_domain_elements(path: Path | None, key: str) -> List[PathElement]:
    """Return the path elements in the UI domain for a ranged constraint key."""
    if path is None:
        return []

    if key in TRANSLATION_CONSTRAINT_KEYS:
        return [
            element
            for element in path.path_elements
            if isinstance(element, (TranslationTarget, Waypoint))
        ]

    return [
        element
        for element in path.path_elements
        if isinstance(element, (Waypoint, RotationTarget, EventTrigger))
    ]


def get_constraint_domain_info(path: Path | None, key: str) -> Tuple[str, int]:
    """Return the domain name and element count for a ranged constraint key."""
    domain = "translation" if key in TRANSLATION_CONSTRAINT_KEYS else "rotation"
    return domain, len(get_constraint_domain_elements(path, key))


def get_constraint_domain_labels(path: Path | None, key: str) -> List[str]:
    """Build brief element labels like T1, W2, R1, E1 for a ranged constraint domain."""
    counters: dict[type[object], int] = {}
    prefix_map: dict[type[object], str] = {
        TranslationTarget: "T",
        Waypoint: "W",
        RotationTarget: "R",
        EventTrigger: "E",
    }

    labels: List[str] = []
    for element in get_constraint_domain_elements(path, key):
        element_type = type(element)
        counters[element_type] = counters.get(element_type, 0) + 1
        labels.append(f"{prefix_map.get(element_type, '?')}{counters[element_type]}")
    return labels
