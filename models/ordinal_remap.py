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

        new_id_to_ordinal = {eid: i + 1 for i, eid in enumerate(new_domain)}

        # Remap the actual covered ordinals rather than only the endpoints.
        # If an endpoint disappears, clamping to 1/domain-size can manufacture
        # overlap with neighboring ranges that were previously disjoint.
        old_start = min(int(rc.start_ordinal), int(rc.end_ordinal))
        old_end = max(int(rc.start_ordinal), int(rc.end_ordinal))
        old_range_ids = {
            old_domain[ord_i - 1]
            for ord_i in range(old_start, old_end + 1)
            if 0 <= ord_i - 1 < len(old_domain)
        }
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
