from __future__ import annotations

from models.path_model import RangedConstraint
from models.ranged_constraint_ops import (
    append_ranged_constraint_instance,
    split_ranged_constraint_instance,
)


def test_append_ranged_constraint_instance_uses_first_free_slot():
    constraints = [
        RangedConstraint(
            key="max_velocity_meters_per_sec",
            value=2.0,
            start_ordinal=1,
            end_ordinal=1,
        ),
        RangedConstraint(
            key="max_velocity_meters_per_sec",
            value=3.0,
            start_ordinal=3,
            end_ordinal=3,
        ),
    ]

    new_rc = append_ranged_constraint_instance(
        constraints,
        key="max_velocity_meters_per_sec",
        value=4.0,
        total=3,
    )

    assert new_rc is not None
    assert (new_rc.start_ordinal, new_rc.end_ordinal, new_rc.value) == (2, 2, 4.0)


def test_append_ranged_constraint_instance_splits_largest_range_when_full():
    constraints = [
        RangedConstraint(
            key="max_velocity_meters_per_sec",
            value=2.0,
            start_ordinal=1,
            end_ordinal=3,
        )
    ]

    new_rc = append_ranged_constraint_instance(
        constraints,
        key="max_velocity_meters_per_sec",
        value=5.0,
        total=3,
    )

    assert new_rc is not None
    assert [(rc.start_ordinal, rc.end_ordinal, rc.value) for rc in constraints] == [
        (1, 2, 2.0),
        (3, 3, 5.0),
    ]


def test_append_ranged_constraint_instance_returns_none_when_full_and_unsplittable():
    constraints = [
        RangedConstraint(
            key="max_velocity_meters_per_sec",
            value=2.0,
            start_ordinal=1,
            end_ordinal=1,
        ),
        RangedConstraint(
            key="max_velocity_meters_per_sec",
            value=3.0,
            start_ordinal=2,
            end_ordinal=2,
        ),
    ]

    new_rc = append_ranged_constraint_instance(
        constraints,
        key="max_velocity_meters_per_sec",
        value=4.0,
        total=2,
    )

    assert new_rc is None
    assert [(rc.start_ordinal, rc.end_ordinal, rc.value) for rc in constraints] == [
        (1, 1, 2.0),
        (2, 2, 3.0),
    ]


def test_split_ranged_constraint_instance_inserts_after_target():
    first = RangedConstraint(
        key="max_velocity_meters_per_sec",
        value=2.0,
        start_ordinal=1,
        end_ordinal=2,
    )
    second = RangedConstraint(
        key="max_velocity_meters_per_sec",
        value=3.0,
        start_ordinal=3,
        end_ordinal=3,
    )
    constraints = [first, second]

    new_rc = split_ranged_constraint_instance(constraints, first)

    assert new_rc is not None
    assert constraints == [first, new_rc, second]
    assert (first.start_ordinal, first.end_ordinal) == (1, 1)
    assert (new_rc.start_ordinal, new_rc.end_ordinal, new_rc.value) == (2, 2, 2.0)
