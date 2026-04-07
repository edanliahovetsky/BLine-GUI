from __future__ import annotations

from models.path_model import EventTrigger, Path, RotationTarget, TranslationTarget, Waypoint
from ui.sidebar.utils.ranged_constraint_ui import (
    get_constraint_domain_elements,
    get_constraint_domain_info,
    get_constraint_domain_labels,
)


def test_rotation_domain_includes_event_triggers():
    path = Path(
        path_elements=[
            TranslationTarget(),
            EventTrigger(),
            RotationTarget(),
            Waypoint(),
        ]
    )

    elements = get_constraint_domain_elements(path, "max_velocity_deg_per_sec")

    assert [type(element).__name__ for element in elements] == [
        "EventTrigger",
        "RotationTarget",
        "Waypoint",
    ]


def test_translation_domain_info_and_labels():
    path = Path(
        path_elements=[
            TranslationTarget(),
            Waypoint(),
            TranslationTarget(),
            EventTrigger(),
        ]
    )

    domain, count = get_constraint_domain_info(path, "max_velocity_meters_per_sec")

    assert (domain, count) == ("translation", 3)
    assert get_constraint_domain_labels(path, "max_velocity_meters_per_sec") == [
        "T1",
        "W1",
        "T2",
    ]
