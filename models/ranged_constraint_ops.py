from __future__ import annotations

from typing import Optional

from models.path_model import RangedConstraint


def _normalized_bounds(rc: RangedConstraint, total: int) -> tuple[int, int]:
    start = max(1, min(int(rc.start_ordinal), total))
    end = max(start, min(int(rc.end_ordinal), total))
    return start, end


def append_ranged_constraint_instance(
    ranged_constraints: list[RangedConstraint],
    *,
    key: str,
    value: float,
    total: int,
) -> Optional[RangedConstraint]:
    """Append a ranged constraint for `key`, using a free slot or splitting the largest range."""
    total = max(1, int(total))
    existing = [rc for rc in ranged_constraints if rc.key == key]

    occupied_units: set[int] = set()
    largest_rc: Optional[RangedConstraint] = None
    largest_len = 0
    largest_bounds = (1, 1)

    for rc in existing:
        start, end = _normalized_bounds(rc, total)
        occupied_units.update(range(start, end + 1))
        current_len = end - start + 1
        if current_len > largest_len:
            largest_len = current_len
            largest_rc = rc
            largest_bounds = (start, end)

    if len(occupied_units) < total:
        for ordinal in range(1, total + 1):
            if ordinal not in occupied_units:
                new_rc = RangedConstraint(
                    key=key,
                    value=value,
                    start_ordinal=ordinal,
                    end_ordinal=ordinal,
                )
                ranged_constraints.append(new_rc)
                return new_rc
        return None

    if largest_rc is None or largest_len < 2:
        return None

    return split_ranged_constraint_instance(
        ranged_constraints,
        largest_rc,
        value=value,
    )


def split_ranged_constraint_instance(
    ranged_constraints: list[RangedConstraint],
    rc: RangedConstraint,
    *,
    value: Optional[float] = None,
) -> Optional[RangedConstraint]:
    """Split `rc` at its midpoint and insert the new range immediately after it."""
    if rc.end_ordinal - rc.start_ordinal < 1:
        return None

    mid = (rc.start_ordinal + rc.end_ordinal) // 2
    new_rc = RangedConstraint(
        key=rc.key,
        value=rc.value if value is None else value,
        start_ordinal=mid + 1,
        end_ordinal=rc.end_ordinal,
    )
    rc.end_ordinal = mid

    for idx, existing in enumerate(ranged_constraints):
        if existing is rc:
            ranged_constraints.insert(idx + 1, new_rc)
            return new_rc

    ranged_constraints.append(new_rc)
    return new_rc
