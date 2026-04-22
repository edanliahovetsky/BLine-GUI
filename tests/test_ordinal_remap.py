"""Tests for models.ordinal_remap — ranged constraint ordinal adjustment."""

from __future__ import annotations

import pytest

from models.path_model import (
    Path,
    RangedConstraint,
    TranslationTarget,
    Waypoint,
    RotationTarget,
    EventTrigger,
)
from models.ordinal_remap import (
    remap_ranged_constraints,
    _translation_domain,
    _rotation_domain,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_path(*elements, constraints=None):
    """Build a Path with the given elements and optional ranged constraints."""
    p = Path(path_elements=list(elements))
    if constraints:
        p.ranged_constraints = list(constraints)
    return p


# ---------------------------------------------------------------------------
# Domain helpers
# ---------------------------------------------------------------------------

class TestDomainHelpers:
    def test_translation_domain_includes_translation_and_waypoint(self):
        t = TranslationTarget()
        w = Waypoint()
        r = RotationTarget()
        e = EventTrigger()
        elems = [t, r, w, e]
        assert _translation_domain(elems) == [id(t), id(w)]

    def test_rotation_domain_includes_waypoint_rotation_event(self):
        t = TranslationTarget()
        w = Waypoint()
        r = RotationTarget()
        e = EventTrigger()
        elems = [t, r, w, e]
        assert _rotation_domain(elems) == [id(r), id(w), id(e)]

    def test_empty_list(self):
        assert _translation_domain([]) == []
        assert _rotation_domain([]) == []


# ---------------------------------------------------------------------------
# Addition tests
# ---------------------------------------------------------------------------

class TestAddition:
    def test_insert_before_shifts_ordinals_forward(self):
        """Inserting a TranslationTarget before existing ones should shift ordinals."""
        t1 = TranslationTarget()
        t2 = TranslationTarget()
        rc = RangedConstraint(
            key="max_velocity_meters_per_sec", value=2.0,
            start_ordinal=1, end_ordinal=2,
        )
        old_elements = [t1, t2]
        # Insert a new TranslationTarget at position 0
        t_new = TranslationTarget()
        path = _make_path(t_new, t1, t2, constraints=[rc])

        remap_ranged_constraints(path, old_elements)

        assert rc.start_ordinal == 2
        assert rc.end_ordinal == 3
        assert len(path.ranged_constraints) == 1

    def test_insert_after_does_not_change_ordinals(self):
        """Inserting after the constrained range preserves ordinals."""
        t1 = TranslationTarget()
        t2 = TranslationTarget()
        rc = RangedConstraint(
            key="max_velocity_meters_per_sec", value=2.0,
            start_ordinal=1, end_ordinal=2,
        )
        old_elements = [t1, t2]
        t_new = TranslationTarget()
        path = _make_path(t1, t2, t_new, constraints=[rc])

        remap_ranged_constraints(path, old_elements)

        assert rc.start_ordinal == 1
        assert rc.end_ordinal == 2

    def test_insert_between_range_endpoints(self):
        """Inserting between start and end keeps both endpoints the same."""
        t1 = TranslationTarget()
        t2 = TranslationTarget()
        rc = RangedConstraint(
            key="max_velocity_meters_per_sec", value=1.0,
            start_ordinal=1, end_ordinal=2,
        )
        old_elements = [t1, t2]
        t_new = TranslationTarget()
        path = _make_path(t1, t_new, t2, constraints=[rc])

        remap_ranged_constraints(path, old_elements)

        assert rc.start_ordinal == 1
        assert rc.end_ordinal == 3

    def test_insert_non_domain_element_no_change(self):
        """Inserting a RotationTarget (not in translation domain) does not shift
        translation constraint ordinals."""
        t1 = TranslationTarget()
        t2 = TranslationTarget()
        rc = RangedConstraint(
            key="max_velocity_meters_per_sec", value=1.0,
            start_ordinal=1, end_ordinal=2,
        )
        old_elements = [t1, t2]
        r_new = RotationTarget()
        path = _make_path(t1, r_new, t2, constraints=[rc])

        remap_ranged_constraints(path, old_elements)

        assert rc.start_ordinal == 1
        assert rc.end_ordinal == 2


# ---------------------------------------------------------------------------
# Removal tests
# ---------------------------------------------------------------------------

class TestRemoval:
    def test_remove_before_range_shifts_backward(self):
        t1 = TranslationTarget()
        t2 = TranslationTarget()
        t3 = TranslationTarget()
        rc = RangedConstraint(
            key="max_velocity_meters_per_sec", value=1.0,
            start_ordinal=2, end_ordinal=3,
        )
        old_elements = [t1, t2, t3]
        path = _make_path(t2, t3, constraints=[rc])

        remap_ranged_constraints(path, old_elements)

        assert rc.start_ordinal == 1
        assert rc.end_ordinal == 2

    def test_remove_start_endpoint(self):
        """Removing the start endpoint: constraint starts at ordinal 1."""
        t1 = TranslationTarget()
        t2 = TranslationTarget()
        t3 = TranslationTarget()
        rc = RangedConstraint(
            key="max_velocity_meters_per_sec", value=1.0,
            start_ordinal=1, end_ordinal=3,
        )
        old_elements = [t1, t2, t3]
        # Remove t1
        path = _make_path(t2, t3, constraints=[rc])

        remap_ranged_constraints(path, old_elements)

        # start was removed, end survived -> start clamps to 1
        assert rc.start_ordinal == 1
        assert rc.end_ordinal == 2

    def test_remove_end_endpoint(self):
        """Removing the end endpoint: constraint end clamps to domain size."""
        t1 = TranslationTarget()
        t2 = TranslationTarget()
        t3 = TranslationTarget()
        rc = RangedConstraint(
            key="max_velocity_meters_per_sec", value=1.0,
            start_ordinal=1, end_ordinal=3,
        )
        old_elements = [t1, t2, t3]
        # Remove t3
        path = _make_path(t1, t2, constraints=[rc])

        remap_ranged_constraints(path, old_elements)

        assert rc.start_ordinal == 1
        assert rc.end_ordinal == 2

    def test_remove_both_endpoints_middle_survives(self):
        """Both endpoints removed but interior element survives -> constraint kept."""
        t1 = TranslationTarget()
        t2 = TranslationTarget()
        t3 = TranslationTarget()
        rc = RangedConstraint(
            key="max_velocity_meters_per_sec", value=1.0,
            start_ordinal=1, end_ordinal=3,
        )
        old_elements = [t1, t2, t3]
        # Remove t1 and t3, keep t2
        path = _make_path(t2, constraints=[rc])

        remap_ranged_constraints(path, old_elements)

        assert rc.start_ordinal == 1
        assert rc.end_ordinal == 1
        assert len(path.ranged_constraints) == 1

    def test_remove_all_elements_in_range_drops_constraint(self):
        """If all elements in the constrained range are removed, constraint is dropped."""
        t1 = TranslationTarget()
        t2 = TranslationTarget()
        t3 = TranslationTarget()
        rc = RangedConstraint(
            key="max_velocity_meters_per_sec", value=1.0,
            start_ordinal=1, end_ordinal=2,
        )
        old_elements = [t1, t2, t3]
        # Remove t1 and t2, keep t3 (outside the range)
        path = _make_path(t3, constraints=[rc])

        remap_ranged_constraints(path, old_elements)

        assert len(path.ranged_constraints) == 0

    def test_domain_shrinks_to_zero_drops_all_constraints(self):
        """If the entire domain is empty, all constraints in that domain are dropped."""
        t1 = TranslationTarget()
        rc = RangedConstraint(
            key="max_velocity_meters_per_sec", value=1.0,
            start_ordinal=1, end_ordinal=1,
        )
        old_elements = [t1]
        # Only a RotationTarget remains (not in translation domain)
        r = RotationTarget()
        path = _make_path(r, constraints=[rc])

        remap_ranged_constraints(path, old_elements)

        assert len(path.ranged_constraints) == 0

    def test_remove_element_does_not_expand_range_into_disjoint_neighbor(self):
        """Removing an interior element must not make a disjoint sibling overlap."""
        t1 = TranslationTarget()
        t2 = TranslationTarget()
        t3 = TranslationTarget()
        rc1 = RangedConstraint(
            key="max_velocity_meters_per_sec", value=1.0,
            start_ordinal=1, end_ordinal=1,
        )
        rc2 = RangedConstraint(
            key="max_velocity_meters_per_sec", value=2.0,
            start_ordinal=2, end_ordinal=3,
        )
        old_elements = [t1, t2, t3]
        path = _make_path(t1, t3, constraints=[rc1, rc2])

        remap_ranged_constraints(path, old_elements)

        assert [(rc.start_ordinal, rc.end_ordinal) for rc in path.ranged_constraints] == [
            (1, 1),
            (2, 2),
        ]


# ---------------------------------------------------------------------------
# Reorder tests
# ---------------------------------------------------------------------------

class TestReorder:
    def test_swap_two_elements(self):
        """Swapping two elements should remap ordinals by identity."""
        t1 = TranslationTarget()
        t2 = TranslationTarget()
        t3 = TranslationTarget()
        rc = RangedConstraint(
            key="max_velocity_meters_per_sec", value=1.0,
            start_ordinal=1, end_ordinal=2,
        )
        old_elements = [t1, t2, t3]
        # Swap t1 and t3
        path = _make_path(t3, t2, t1, constraints=[rc])

        remap_ranged_constraints(path, old_elements)

        # t1 was ordinal 1 -> now ordinal 3, t2 was ordinal 2 -> still ordinal 2
        # new range should be [2, 3] (auto-sorted)
        assert rc.start_ordinal == 2
        assert rc.end_ordinal == 3

    def test_reverse_order(self):
        """Reversing the list should swap start/end if needed."""
        t1 = TranslationTarget()
        t2 = TranslationTarget()
        rc = RangedConstraint(
            key="max_acceleration_meters_per_sec2", value=5.0,
            start_ordinal=1, end_ordinal=2,
        )
        old_elements = [t1, t2]
        path = _make_path(t2, t1, constraints=[rc])

        remap_ranged_constraints(path, old_elements)

        # t1 was start (1) -> now 2, t2 was end (2) -> now 1
        # Should auto-correct to [1, 2]
        assert rc.start_ordinal == 1
        assert rc.end_ordinal == 2

    def test_reorder_with_mixed_domain(self):
        """Reorder involving non-domain elements: rotation elements among translations."""
        t1 = TranslationTarget()
        r1 = RotationTarget()
        t2 = TranslationTarget()
        rc = RangedConstraint(
            key="max_velocity_meters_per_sec", value=1.0,
            start_ordinal=1, end_ordinal=2,
        )
        old_elements = [t1, r1, t2]
        # Reverse: t2, r1, t1
        path = _make_path(t2, r1, t1, constraints=[rc])

        remap_ranged_constraints(path, old_elements)

        # Translation domain was [t1, t2], now [t2, t1]
        # Original start=t1 is now ordinal 2, end=t2 is now ordinal 1
        # Auto-corrected to [1, 2]
        assert rc.start_ordinal == 1
        assert rc.end_ordinal == 2


# ---------------------------------------------------------------------------
# Type change tests
# ---------------------------------------------------------------------------

class TestTypeChange:
    def test_translation_to_rotation_removes_from_translation_domain(self):
        """When a TranslationTarget becomes a RotationTarget, it leaves the
        translation domain. Constraint range adjusts or drops."""
        t1 = TranslationTarget()
        t2 = TranslationTarget()
        t3 = TranslationTarget()
        rc = RangedConstraint(
            key="max_velocity_meters_per_sec", value=1.0,
            start_ordinal=1, end_ordinal=3,
        )
        old_elements = [t1, t2, t3]
        # t2 changed to RotationTarget (new object at same position)
        r2_new = RotationTarget()
        path = _make_path(t1, r2_new, t3, constraints=[rc])

        remap_ranged_constraints(path, old_elements)

        # t2 was in the interior of [1,3]; endpoints t1(1) and t3(3) survive
        # New translation domain is [t1, t3] so ordinals are 1 and 2
        assert rc.start_ordinal == 1
        assert rc.end_ordinal == 2

    def test_type_change_endpoint_becomes_non_domain(self):
        """Start endpoint changes type and leaves the domain."""
        t1 = TranslationTarget()
        t2 = TranslationTarget()
        rc = RangedConstraint(
            key="max_velocity_meters_per_sec", value=1.0,
            start_ordinal=1, end_ordinal=2,
        )
        old_elements = [t1, t2]
        # t1 replaced by RotationTarget
        r_new = RotationTarget()
        path = _make_path(r_new, t2, constraints=[rc])

        remap_ranged_constraints(path, old_elements)

        # Start (t1) gone, end (t2) survives at ordinal 1
        # start clamps to 1
        assert rc.start_ordinal == 1
        assert rc.end_ordinal == 1

    def test_rotation_constraint_gains_element(self):
        """A TranslationTarget becomes a RotationTarget, entering the rotation
        domain and shifting rotation constraint ordinals."""
        w1 = Waypoint()
        r1 = RotationTarget()
        t1 = TranslationTarget()
        rc = RangedConstraint(
            key="max_velocity_deg_per_sec", value=100.0,
            start_ordinal=1, end_ordinal=2,
        )
        old_elements = [w1, r1, t1]
        # t1 changes to RotationTarget -> now in rotation domain
        r_new = RotationTarget()
        path = _make_path(w1, r1, r_new, constraints=[rc])

        remap_ranged_constraints(path, old_elements)

        # Old rotation domain: [w1, r1] -> ordinals 1,2
        # New rotation domain: [w1, r1, r_new] -> w1=1, r1=2, r_new=3
        # Constraint was [1,2] -> w1(1), r1(2) -> still [1,2]
        assert rc.start_ordinal == 1
        assert rc.end_ordinal == 2

    def test_type_change_does_not_expand_range_into_disjoint_neighbor(self):
        """A type change that removes an interior element must preserve disjoint ranges."""
        t1 = TranslationTarget()
        t2 = TranslationTarget()
        t3 = TranslationTarget()
        rc1 = RangedConstraint(
            key="max_velocity_meters_per_sec", value=1.0,
            start_ordinal=1, end_ordinal=1,
        )
        rc2 = RangedConstraint(
            key="max_velocity_meters_per_sec", value=2.0,
            start_ordinal=2, end_ordinal=3,
        )
        old_elements = [t1, t2, t3]
        path = _make_path(t1, RotationTarget(), t3, constraints=[rc1, rc2])

        remap_ranged_constraints(path, old_elements)

        assert [(rc.start_ordinal, rc.end_ordinal) for rc in path.ranged_constraints] == [
            (1, 1),
            (2, 2),
        ]


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_no_ranged_constraints_is_noop(self):
        t1 = TranslationTarget()
        t2 = TranslationTarget()
        path = _make_path(t1, t2)
        old_elements = [t1]

        remap_ranged_constraints(path, old_elements)

        assert path.ranged_constraints == []

    def test_multiple_constraints_independent(self):
        """Multiple constraints remap independently."""
        t1 = TranslationTarget()
        t2 = TranslationTarget()
        t3 = TranslationTarget()
        rc1 = RangedConstraint(
            key="max_velocity_meters_per_sec", value=1.0,
            start_ordinal=1, end_ordinal=2,
        )
        rc2 = RangedConstraint(
            key="max_velocity_meters_per_sec", value=2.0,
            start_ordinal=2, end_ordinal=3,
        )
        old_elements = [t1, t2, t3]
        # Remove t1
        path = _make_path(t2, t3, constraints=[rc1, rc2])

        remap_ranged_constraints(path, old_elements)

        # rc1: start=t1 (removed) -> clamp to 1, end=t2 -> ordinal 1
        assert rc1.start_ordinal == 1
        assert rc1.end_ordinal == 1
        # rc2: start=t2 -> ordinal 1, end=t3 -> ordinal 2
        assert rc2.start_ordinal == 1
        assert rc2.end_ordinal == 2
        assert len(path.ranged_constraints) == 2

    def test_out_of_bounds_start_ordinal(self):
        """Ordinal beyond old domain size is treated as None (endpoint removed)."""
        t1 = TranslationTarget()
        rc = RangedConstraint(
            key="max_velocity_meters_per_sec", value=1.0,
            start_ordinal=5, end_ordinal=1,
        )
        old_elements = [t1]
        t2 = TranslationTarget()
        path = _make_path(t1, t2, constraints=[rc])

        remap_ranged_constraints(path, old_elements)

        # start ordinal 5 is out of bounds -> None
        # end ordinal 1 -> t1 -> new ordinal 1
        assert rc.start_ordinal == 1
        assert rc.end_ordinal == 1

    def test_waypoint_in_both_domains(self):
        """Waypoints appear in both translation and rotation domains."""
        w1 = Waypoint()
        w2 = Waypoint()
        rc_trans = RangedConstraint(
            key="max_velocity_meters_per_sec", value=1.0,
            start_ordinal=1, end_ordinal=2,
        )
        rc_rot = RangedConstraint(
            key="max_velocity_deg_per_sec", value=100.0,
            start_ordinal=1, end_ordinal=2,
        )
        old_elements = [w1, w2]
        w_new = Waypoint()
        # Insert at front
        path = _make_path(w_new, w1, w2, constraints=[rc_trans, rc_rot])

        remap_ranged_constraints(path, old_elements)

        # Both domains shift: w1 was 1 -> now 2, w2 was 2 -> now 3
        assert rc_trans.start_ordinal == 2
        assert rc_trans.end_ordinal == 3
        assert rc_rot.start_ordinal == 2
        assert rc_rot.end_ordinal == 3

    def test_single_element_constraint_survives_if_element_survives(self):
        """A constraint spanning a single element survives if that element persists."""
        t1 = TranslationTarget()
        t2 = TranslationTarget()
        rc = RangedConstraint(
            key="max_velocity_meters_per_sec", value=1.0,
            start_ordinal=2, end_ordinal=2,
        )
        old_elements = [t1, t2]
        # Remove t1 only
        path = _make_path(t2, constraints=[rc])

        remap_ranged_constraints(path, old_elements)

        assert rc.start_ordinal == 1
        assert rc.end_ordinal == 1
        assert len(path.ranged_constraints) == 1

    def test_single_element_constraint_dropped_if_element_removed(self):
        """A constraint spanning a single element is dropped when that element is removed."""
        t1 = TranslationTarget()
        t2 = TranslationTarget()
        rc = RangedConstraint(
            key="max_velocity_meters_per_sec", value=1.0,
            start_ordinal=1, end_ordinal=1,
        )
        old_elements = [t1, t2]
        # Remove t1
        path = _make_path(t2, constraints=[rc])

        remap_ranged_constraints(path, old_elements)

        assert len(path.ranged_constraints) == 0

    def test_event_trigger_in_rotation_domain(self):
        """EventTrigger is in the rotation domain only."""
        e1 = EventTrigger()
        e2 = EventTrigger()
        rc = RangedConstraint(
            key="max_velocity_deg_per_sec", value=50.0,
            start_ordinal=1, end_ordinal=2,
        )
        old_elements = [e1, e2]
        e_new = EventTrigger()
        path = _make_path(e_new, e1, e2, constraints=[rc])

        remap_ranged_constraints(path, old_elements)

        assert rc.start_ordinal == 2
        assert rc.end_ordinal == 3
