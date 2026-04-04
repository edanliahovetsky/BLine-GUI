from __future__ import annotations

from models.path_model import Path, TranslationTarget
from ui.sidebar.components.constraint_manager import ConstraintManager


class _ProjectManagerStub:
    def __init__(self, defaults: dict[str, float]):
        self._defaults = defaults

    def get_default_optional_value(self, key: str):
        return self._defaults.get(key)


def _translation_path() -> Path:
    return Path(path_elements=[TranslationTarget(), TranslationTarget()])


def test_gap_double_click_uses_project_manager_default_value(qt_app):
    key = "max_velocity_meters_per_sec"
    expected = 4.25

    manager = ConstraintManager()
    manager.project_manager = _ProjectManagerStub({key: expected})
    path = _translation_path()
    manager.set_path(path)

    manager._on_gap_double_clicked(key, 1, 1)

    matching = [
        rc
        for rc in path.ranged_constraints
        if rc.key == key and rc.start_ordinal == 1 and rc.end_ordinal == 1
    ]

    assert matching
    assert matching[-1].value == expected
