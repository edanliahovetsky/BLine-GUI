from models.path_model import (
    Path,
    PathElement,
    RangedConstraint,
    TranslationTarget,
    Waypoint,
    RotationTarget,
    EventTrigger,
)
from typing import List

def _translation_domain(elements: List[PathElement]) -> List[int]:
    """Return Python id()s of elements in the translation domain, in order."""
    return [id(e) for e in elements if isinstance(e, (TranslationTarget, Waypoint))]

def _rotation_domain(elements: List[PathElement]) -> List[int]:
    """Return Python id()s of elements in the rotation domain, in order."""
    return [id(e) for e in elements if isinstance(e, (Waypoint, RotationTarget, EventTrigger))]

TRANSLATION_KEYS = {"max_velocity_meters_per_sec", "max_acceleration_meters_per_sec2"}
ROTATION_KEYS = {"max_velocity_deg_per_sec", "max_acceleration_deg_per_sec2"}

def _domain_for_key(key: str, elements: List[PathElement]) -> List[int]:
    if key in TRANSLATION_KEYS:
        return _translation_domain(elements)
    else:
        return _rotation_domain(elements)

def remap_ranged_constraints(path: Path, old_elements: List[PathElement]) -> None:
    """Update all RangedConstraint ordinals on `path` to reflect the
    current `path.path_elements` relative to the snapshot `old_elements`.

    Must be called AFTER the mutation has been applied to path.path_elements,
    but AFTER the undo snapshot of the old state has already been taken.

    Modifies path.ranged_constraints in place. Removes constraints whose
    entire range has been eliminated.
    """
    new_elements = path.path_elements
    surviving: List[RangedConstraint] = []

    for rc in path.ranged_constraints:
        old_domain = _domain_for_key(rc.key, old_elements)
        new_domain = _domain_for_key(rc.key, new_elements)
        new_domain_size = len(new_domain)

        if new_domain_size == 0:
            continue

        old_start_id = old_domain[rc.start_ordinal - 1] if rc.start_ordinal - 1 < len(old_domain) else None
        old_end_id = old_domain[rc.end_ordinal - 1] if rc.end_ordinal - 1 < len(old_domain) else None

        new_id_to_ordinal = {eid: i + 1 for i, eid in enumerate(new_domain)}

        new_start = new_id_to_ordinal.get(old_start_id) if old_start_id else None
        new_end = new_id_to_ordinal.get(old_end_id) if old_end_id else None

        if new_start is not None and new_end is not None:
            if new_start > new_end:
                new_start, new_end = new_end, new_start
            rc.start_ordinal = new_start
            rc.end_ordinal = new_end
            surviving.append(rc)
        elif new_start is not None:
            rc.start_ordinal = new_start
            rc.end_ordinal = new_domain_size
            surviving.append(rc)
        elif new_end is not None:
            rc.start_ordinal = 1
            rc.end_ordinal = new_end
            surviving.append(rc)
        else:
            old_range_ids = set()
            for ord_i in range(rc.start_ordinal, rc.end_ordinal + 1):
                if ord_i - 1 < len(old_domain):
                    old_range_ids.add(old_domain[ord_i - 1])
            surviving_ordinals = sorted(
                new_id_to_ordinal[eid]
                for eid in old_range_ids
                if eid in new_id_to_ordinal
            )
            if surviving_ordinals:
                rc.start_ordinal = surviving_ordinals[0]
                rc.end_ordinal = surviving_ordinals[-1]
                surviving.append(rc)

    path.ranged_constraints = surviving
