from __future__ import annotations

from models.path_model import Path, RangedConstraint, TranslationTarget
from ui.sidebar.components.constraint_manager import ConstraintManager
from ui.sidebar.dialogs.constraint_popout import ConstraintPopout


def _translation_path(*constraints: RangedConstraint) -> Path:
    return Path(
        path_elements=[TranslationTarget(), TranslationTarget()],
        ranged_constraints=list(constraints),
    )


def test_refresh_data_rebuilds_rows_when_present_keys_change(qt_app):
    path = _translation_path(
        RangedConstraint(
            key="max_velocity_meters_per_sec",
            value=2.0,
            start_ordinal=1,
            end_ordinal=1,
        )
    )
    popout = ConstraintPopout(path)

    assert list(popout._rows) == ["max_velocity_meters_per_sec"]

    path.ranged_constraints = [
        RangedConstraint(
            key="max_acceleration_meters_per_sec2",
            value=3.0,
            start_ordinal=1,
            end_ordinal=1,
        )
    ]

    popout.refresh_data()

    assert list(popout._rows) == ["max_acceleration_meters_per_sec2"]

    popout.close()


def test_create_constraint_uses_same_default_value_as_constraint_manager(qt_app):
    key = "max_velocity_meters_per_sec"
    path = _translation_path(
        RangedConstraint(
            key=key,
            value=2.0,
            start_ordinal=1,
            end_ordinal=1,
        )
    )
    popout = ConstraintPopout(path)
    manager = ConstraintManager()

    popout._create_constraint(key, 2, 2)

    matching = [
        rc
        for rc in path.ranged_constraints
        if rc.key == key and rc.start_ordinal == 2 and rc.end_ordinal == 2
    ]

    assert matching
    assert matching[-1].value == manager.get_default_value(key)

    popout.close()


def test_add_button_splits_existing_range_when_domain_is_fully_covered(qt_app):
    key = "max_velocity_meters_per_sec"
    path = _translation_path(
        RangedConstraint(
            key=key,
            value=4.0,
            start_ordinal=1,
            end_ordinal=2,
        )
    )
    popout = ConstraintPopout(path)

    popout._on_add_button(key)

    matching = sorted(
        [rc for rc in path.ranged_constraints if rc.key == key],
        key=lambda rc: rc.start_ordinal,
    )

    assert [(rc.start_ordinal, rc.end_ordinal) for rc in matching] == [(1, 1), (2, 2)]
    assert matching[-1].value == ConstraintManager().get_default_value(key)

    popout.close()
