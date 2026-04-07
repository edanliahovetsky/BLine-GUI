from __future__ import annotations

from pathlib import Path

from models.path_model import (
    EventTrigger,
    Path as PathModel,
    RangedConstraint,
    RotationTarget,
    TranslationTarget,
)
from utils.project_io import deserialize_path, serialize_path


def test_serialize_deserialize_round_trip(tmp_path: Path):
    path = PathModel()
    path.path_elements.append(TranslationTarget(x_meters=0.0, y_meters=0.0))
    path.path_elements.append(RotationTarget(rotation_radians=0.5, t_ratio=0.5))
    path.path_elements.append(TranslationTarget(x_meters=2.0, y_meters=1.0))

    data = serialize_path(path)
    restored = deserialize_path(
        data, lambda key: 0.1 if key == "intermediate_handoff_radius_meters" else None
    )

    assert len(restored.path_elements) == len(path.path_elements)
    serialized_again = serialize_path(restored)
    assert serialized_again["path_elements"][0]["type"] == "translation"


def test_deserialize_rotation_ranged_constraint_counts_event_triggers():
    data = {
        "path_elements": [
            {"type": "translation", "x_meters": 0.0, "y_meters": 0.0},
            {"type": "event_trigger", "t_ratio": 0.25, "lib_key": "A"},
            {"type": "rotation", "rotation_radians": 0.5, "t_ratio": 0.5},
            {"type": "translation", "x_meters": 1.0, "y_meters": 1.0},
        ],
        "constraints": {
            "max_velocity_deg_per_sec": [
                {"value": 90.0, "start_ordinal": 1, "end_ordinal": 1},
            ]
        },
    }

    restored = deserialize_path(data)

    assert isinstance(restored.path_elements[1], EventTrigger)
    assert isinstance(restored.path_elements[2], RotationTarget)
    assert restored.ranged_constraints == [
        RangedConstraint(
            key="max_velocity_deg_per_sec",
            value=90.0,
            start_ordinal=2,
            end_ordinal=2,
        )
    ]
