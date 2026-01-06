"""Path simulation engine for BLine-GUI.

This module provides an idealistic kinematic simulation of path following. It is
intended for visualization and initial path validation in the GUI, NOT as a
substitute for real-world testing.

Key characteristics:
- Uses idealistic kinematics assuming instant drivetrain response to commanded velocities
- Calculates desired speeds using a 2ad distance formula: v = sqrt(2 * a * remaining_distance)
- Does NOT simulate the actual PID controller-based approach used by BLine-Lib on the robot
- Applies acceleration rate limiting but assumes perfect velocity tracking

For accurate path validation, use a physics simulation framework (e.g., WPILib simulation)
or empirical testing on the actual robot. Empirical testing and rapid iteration is where
BLine's simplicity shines.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from models.path_model import (
    Path,
    RotationTarget,
    TranslationTarget,
    Waypoint,
    RangedConstraint,
)


@dataclass
class Pose:
    x_m: float
    y_m: float
    theta_rad: float


@dataclass
class ChassisSpeeds:
    vx_mps: float
    vy_mps: float
    omega_radps: float


@dataclass
class SimResult:
    poses_by_time: Dict[float, Tuple[float, float, float]]
    times_sorted: List[float]
    total_time_s: float
    trail_points: List[Tuple[float, float]]  # List of (x, y) positions for the trail


def wrap_angle_radians(theta: float) -> float:
    while theta > math.pi:
        theta -= 2.0 * math.pi
    while theta < -math.pi:
        theta += 2.0 * math.pi
    return theta


def shortest_angular_distance(target: float, current: float) -> float:
    delta = wrap_angle_radians(target - current)
    return delta


def dot(ax: float, ay: float, bx: float, by: float) -> float:
    return ax * bx + ay * by


def hypot2(x: float, y: float) -> float:
    return math.hypot(x, y)


def limit_acceleration(
    desired: ChassisSpeeds,
    last: ChassisSpeeds,
    dt: float,
    max_trans_accel_mps2: float,
    max_angular_accel_radps2: float,
) -> ChassisSpeeds:
    if dt <= 0.0:
        return last

    dvx = desired.vx_mps - last.vx_mps
    dvy = desired.vy_mps - last.vy_mps
    desired_acc = hypot2(dvx, dvy) / dt

    obtainable_acc = max(0.0, min(desired_acc, float(max_trans_accel_mps2)))
    theta = math.atan2(dvy, dvx) if (abs(dvx) + abs(dvy)) > 0.0 else 0.0

    desired_alpha = (desired.omega_radps - last.omega_radps) / dt
    obtainable_alpha = max(
        -float(max_angular_accel_radps2), min(desired_alpha, float(max_angular_accel_radps2))
    )

    return ChassisSpeeds(
        vx_mps=last.vx_mps + math.cos(theta) * obtainable_acc * dt,
        vy_mps=last.vy_mps + math.sin(theta) * obtainable_acc * dt,
        omega_radps=last.omega_radps + obtainable_alpha * dt,
    )


@dataclass
class _RotationKeyframe:
    t_ratio: float
    theta_target: float
    profiled_rotation: bool = True


@dataclass
class _Segment:
    ax: float
    ay: float
    bx: float
    by: float
    length_m: float
    ux: float
    uy: float
    keyframes: List[_RotationKeyframe]  # list of rotation keyframes


@dataclass
class _GlobalRotationKeyframe:
    s_m: float
    theta_target: float
    event_ordinal_1b: int
    profiled_rotation: bool = True


def _build_segments(path: Path) -> Tuple[List[_Segment], List[Tuple[float, float]], List[int]]:
    anchors: List[Tuple[float, float]] = []
    anchor_path_indices: List[int] = []

    for idx, elem in enumerate(path.path_elements):
        if isinstance(elem, TranslationTarget):
            anchors.append((float(elem.x_meters), float(elem.y_meters)))
            anchor_path_indices.append(idx)
        elif isinstance(elem, Waypoint):
            anchors.append(
                (float(elem.translation_target.x_meters), float(elem.translation_target.y_meters))
            )
            anchor_path_indices.append(idx)

    segments: List[_Segment] = []
    if len(anchors) < 2:
        return segments, anchors, anchor_path_indices

    # Map path index to anchor ordinal
    path_idx_to_anchor_ord: Dict[int, int] = {pi: i for i, pi in enumerate(anchor_path_indices)}

    # Initialize segments between consecutive anchors
    for i in range(len(anchors) - 1):
        ax, ay = anchors[i]
        bx, by = anchors[i + 1]
        dx = bx - ax
        dy = by - ay
        L = math.hypot(dx, dy)
        if L <= 1e-9:
            segments.append(_Segment(ax, ay, bx, by, 0.0, 1.0, 0.0, []))
        else:
            segments.append(_Segment(ax, ay, bx, by, L, dx / L, dy / L, []))

    # Assign rotation keyframes to segments
    for idx, elem in enumerate(path.path_elements):
        if isinstance(elem, RotationTarget):
            prev_anchor_ord: Optional[int] = None
            next_anchor_ord: Optional[int] = None
            for j in range(idx - 1, -1, -1):
                e = path.path_elements[j]
                if isinstance(e, (TranslationTarget, Waypoint)):
                    prev_anchor_ord = path_idx_to_anchor_ord.get(j)
                    break
            for j in range(idx + 1, len(path.path_elements)):
                e = path.path_elements[j]
                if isinstance(e, (TranslationTarget, Waypoint)):
                    next_anchor_ord = path_idx_to_anchor_ord.get(j)
                    break
            if prev_anchor_ord is None or next_anchor_ord is None:
                continue
            if next_anchor_ord != prev_anchor_ord + 1:
                continue
            t_ratio = float(getattr(elem, "t_ratio", 0.0))
            t_ratio = 0.0 if t_ratio < 0.0 else 1.0 if t_ratio > 1.0 else t_ratio
            theta = float(elem.rotation_radians)
            profiled = getattr(elem, "profiled_rotation", True)
            segments[prev_anchor_ord].keyframes.append(_RotationKeyframe(t_ratio, theta, profiled))
        elif isinstance(elem, Waypoint):
            rt = elem.rotation_target
            this_anchor_ord = path_idx_to_anchor_ord.get(idx)
            if this_anchor_ord is None:
                continue

            # For waypoints, the rotation should happen at the waypoint location
            # This means we need to add it to the segment that ENDS at this waypoint
            # (i.e., the previous segment with t_ratio = 1.0)
            # OR to the segment that STARTS at this waypoint with t_ratio = 0.0

            # Strategy: Add to the segment that starts at this waypoint with t_ratio = 0.0
            # This ensures the robot has the correct heading when leaving the waypoint
            if this_anchor_ord < len(segments):
                theta = float(rt.rotation_radians)
                profiled = getattr(rt, "profiled_rotation", True)
                segments[this_anchor_ord].keyframes.append(_RotationKeyframe(0.0, theta, profiled))

            # Also add to the previous segment with t_ratio = 1.0 if it exists
            # This ensures the robot rotates to the correct heading when arriving at the waypoint
            if this_anchor_ord > 0:
                theta = float(rt.rotation_radians)
                profiled = getattr(rt, "profiled_rotation", True)
                segments[this_anchor_ord - 1].keyframes.append(
                    _RotationKeyframe(1.0, theta, profiled)
                )

    for seg in segments:
        if not seg.keyframes:
            continue
        seg.keyframes.sort(key=lambda kf: kf.t_ratio)
        dedup: List[_RotationKeyframe] = []
        last_t: Optional[float] = None
        for kf in seg.keyframes:
            if last_t is not None and abs(kf.t_ratio - last_t) < 1e-9:
                dedup[-1] = kf  # Replace with latest
            else:
                dedup.append(kf)
                last_t = kf.t_ratio
        seg.keyframes = dedup

    return segments, anchors, anchor_path_indices


def _default_heading(ax: float, ay: float, bx: float, by: float) -> float:
    return math.atan2(by - ay, bx - ax)


def _build_global_rotation_keyframes(
    path: Path,
    anchor_path_indices: List[int],
    cumulative_lengths: List[float],
) -> List[_GlobalRotationKeyframe]:
    """Build a global rotation keyframe list along absolute path distance s (meters).

    RotationTarget elements between any two anchors (not necessarily adjacent)
    are mapped to a distance s by linearly interpolating between the cumulative
    distances of the surrounding anchors using the element's t_ratio.

    Waypoint rotations are mapped to the absolute distance at that waypoint.
    """
    path_idx_to_anchor_ord: Dict[int, int] = {pi: i for i, pi in enumerate(anchor_path_indices)}

    global_frames: List[_GlobalRotationKeyframe] = []

    rot_event_ord = 0  # 1-based ordinal over rotation-bearing events in path order
    for idx, elem in enumerate(path.path_elements):
        if isinstance(elem, RotationTarget):
            prev_anchor_ord: Optional[int] = None
            next_anchor_ord: Optional[int] = None
            for j in range(idx - 1, -1, -1):
                e = path.path_elements[j]
                if isinstance(e, (TranslationTarget, Waypoint)):
                    prev_anchor_ord = path_idx_to_anchor_ord.get(j)
                    break
            for j in range(idx + 1, len(path.path_elements)):
                e = path.path_elements[j]
                if isinstance(e, (TranslationTarget, Waypoint)):
                    next_anchor_ord = path_idx_to_anchor_ord.get(j)
                    break
            # Require valid surrounding anchors, but they do NOT need to be adjacent
            if prev_anchor_ord is None or next_anchor_ord is None:
                continue
            s0 = cumulative_lengths[prev_anchor_ord]
            s1 = cumulative_lengths[next_anchor_ord]
            seg_span = max(s1 - s0, 1e-9)
            t_ratio = float(getattr(elem, "t_ratio", 0.0))
            t_ratio = 0.0 if t_ratio < 0.0 else 1.0 if t_ratio > 1.0 else t_ratio
            theta = float(elem.rotation_radians)
            profiled = getattr(elem, "profiled_rotation", True)
            s_at = s0 + t_ratio * seg_span
            rot_event_ord += 1
            global_frames.append(_GlobalRotationKeyframe(s_at, theta, rot_event_ord, profiled))
        elif isinstance(elem, Waypoint):
            this_anchor_ord = path_idx_to_anchor_ord.get(idx)
            if this_anchor_ord is None:
                continue
            rt = elem.rotation_target
            theta = float(rt.rotation_radians)
            profiled = getattr(rt, "profiled_rotation", True)
            s_at = cumulative_lengths[this_anchor_ord]
            rot_event_ord += 1
            global_frames.append(_GlobalRotationKeyframe(s_at, theta, rot_event_ord, profiled))

    if not global_frames:
        return []

    # Sort and de-duplicate by s; keep the last entry for identical s positions
    global_frames.sort(key=lambda kf: kf.s_m)
    dedup: List[_GlobalRotationKeyframe] = []
    last_s: Optional[float] = None
    for kf in global_frames:
        if last_s is not None and abs(kf.s_m - last_s) < 1e-9:
            dedup[-1] = kf
        else:
            dedup.append(kf)
            last_s = kf.s_m
    return dedup


def _desired_heading_for_global_s(
    global_frames: List[_GlobalRotationKeyframe],
    s_m: float,
    start_heading: float,
) -> Tuple[float, float, bool]:
    """Compute desired heading and dtheta/ds at absolute path distance s_m.

    IMPORTANT:
    - For profiled rotation, the desired heading is an interpolated setpoint
      between successive rotation events, parameterized by completion ratio
      along path distance (s). The controller still uses 2ad-style dynamics to
      compute omega from angular error and applies angular acceleration limiting.
    - For non-profiled rotation, the desired heading steps immediately to the
      next event's target (no interpolation).

    Returns (desired_theta, dtheta_ds, profiled_rotation_for_interval).
    """
    if not global_frames:
        return start_heading, 0.0, True

    frames: List[Tuple[float, float, bool]] = []
    if global_frames[0].s_m > 0.0 + 1e-9:
        frames.append((0.0, start_heading, True))
    for kf in global_frames:
        frames.append((kf.s_m, kf.theta_target, kf.profiled_rotation))

    # Iterate across brackets
    for i in range(len(frames) - 1):
        s0, th0, profiled0 = frames[i]
        s1, th1, profiled1 = frames[i + 1]
        # Before (or exactly at) this keyframe: hold its heading; no pre-snap.
        if s_m <= s0 + 1e-12:
            delta = shortest_angular_distance(th1, th0)
            dtheta_ds = delta / max((s1 - s0), 1e-9)
            return th0, dtheta_ds, profiled1

        # Within this interval: either interpolate (profiled) or step (non-profiled).
        if s0 < s_m <= s1 + 1e-12:
            delta = shortest_angular_distance(th1, th0)
            dtheta_ds = delta / max((s1 - s0), 1e-9)
            if not profiled1:
                return th1, 0.0, profiled1
            alpha = (s_m - s0) / max((s1 - s0), 1e-9)
            desired_theta = wrap_angle_radians(th0 + delta * alpha)
            return desired_theta, dtheta_ds, profiled1

    # After the last frame, hold
    _, th_last, profiled_last = frames[-1]
    if not profiled_last:
        return th_last, 0.0, profiled_last
    return th_last, 0.0, profiled_last


def _resolve_constraint(value: Optional[float], fallback: Optional[float], default: float) -> float:
    try:
        if value is not None and float(value) > 0.0:
            return float(value)
    except Exception:
        pass
    try:
        if fallback is not None and float(fallback) > 0.0:
            return float(fallback)
    except Exception:
        pass
    return float(default)


def _get_handoff_radius_for_segment(
    path: Path, seg_index: int, anchor_path_indices: List[int], default_radius: float
) -> float:
    """Get the handoff radius for a specific segment. Uses the radius from the target element of that segment."""
    if seg_index < 0 or seg_index >= len(anchor_path_indices) - 1:
        return default_radius

    # The target element for this segment is at anchor_path_indices[seg_index + 1]
    target_element_index = anchor_path_indices[seg_index + 1]

    if target_element_index >= len(path.path_elements):
        return default_radius

    target_element = path.path_elements[target_element_index]

    # Get handoff radius from the target element
    radius = None
    if isinstance(target_element, TranslationTarget):
        radius = getattr(target_element, "intermediate_handoff_radius_meters", None)
    elif isinstance(target_element, Waypoint):
        radius = getattr(
            target_element.translation_target, "intermediate_handoff_radius_meters", None
        )

    # Use element radius if set and positive, otherwise use default
    if radius is not None and radius > 0:
        return float(radius)
    return default_radius


def _active_translation_limit(path: Path, key: str, next_anchor_ord: int) -> Optional[float]:
    """Return the most restrictive translation constraint (minimum value) active
    for the given next anchor ordinal (1-based). If none match, returns None.
    """
    best: Optional[float] = None
    try:
        for rc in getattr(path, "ranged_constraints", []) or []:
            try:
                if not isinstance(rc, RangedConstraint):
                    continue
                if rc.key != key:
                    continue
                l = int(getattr(rc, "start_ordinal", 1))
                h = int(getattr(rc, "end_ordinal", 1))
                if int(l) <= int(next_anchor_ord) <= int(h):
                    raw_value = getattr(rc, "value", None)
                    if not isinstance(raw_value, (int, float)):
                        continue
                    v = float(raw_value)
                    if v > 0.0:
                        best = v if (best is None or v < best) else best
            except Exception:
                continue
    except Exception:
        best = None
    return best


def _rotation_target_event_ordinal(
    global_keyframes: List[_GlobalRotationKeyframe], global_s_now: float
) -> Optional[int]:
    """Return the 1-based ordinal of the rotation-domain 'current target' event.
    - Before an event: that event
    - Exactly at an event: the next event if it exists, otherwise this event
    - After the last event: the last event
    """
    if not global_keyframes:
        return None
    tol_s = 1e-6
    n = len(global_keyframes)
    for i, kf in enumerate(global_keyframes):
        if global_s_now < kf.s_m - tol_s:
            return int(getattr(kf, "event_ordinal_1b", i + 1))
        if abs(global_s_now - kf.s_m) <= tol_s:
            # At an event: switch immediately to next if available
            if i + 1 < n:
                next_kf = global_keyframes[i + 1]
                return int(getattr(next_kf, "event_ordinal_1b", i + 2))
            # No next event; continue using this event
            return int(getattr(kf, "event_ordinal_1b", i + 1))
    # After the last event
    last_kf = global_keyframes[-1]
    return int(getattr(last_kf, "event_ordinal_1b", len(global_keyframes)))


def _active_rotation_limit(
    path: Path, global_keyframes: List[_GlobalRotationKeyframe], key: str, global_s_now: float
) -> Optional[float]:
    """Return the most restrictive rotation constraint (minimum value) for the
    current rotation target event. If none match, returns None.
    """
    event_ord_1b = _rotation_target_event_ordinal(global_keyframes, global_s_now)
    if event_ord_1b is None or event_ord_1b <= 0:
        return None
    best: Optional[float] = None
    try:
        for rc in getattr(path, "ranged_constraints", []) or []:
            try:
                if not isinstance(rc, RangedConstraint):
                    continue
                if rc.key != key:
                    continue
                l = int(getattr(rc, "start_ordinal", 1))
                h = int(getattr(rc, "end_ordinal", 1))
                if int(l) <= int(event_ord_1b) <= int(h):
                    raw_value = getattr(rc, "value", None)
                    if not isinstance(raw_value, (int, float)):
                        continue
                    v = float(raw_value)
                    if v > 0.0:
                        best = v if (best is None or v < best) else best
            except Exception:
                continue
    except Exception:
        best = None
    return best


def simulate_path(
    path: Path,
    config: Optional[Dict] = None,
    dt_s: float = 0.02,
) -> SimResult:
    """Simulate robot motion along a path using idealistic kinematics.

    This simulation uses a 2ad distance formula (v = sqrt(2 * a * d)) to compute
    desired velocities based on remaining path distance. It assumes instant
    drivetrain response and perfect velocity tracking, applying only acceleration
    rate limiting as a constraint.

    This is NOT equivalent to the PID-based path following in BLine-Lib. Use this
    for initial visualization only; empirical testing on the robot is required
    for path validation.

    Args:
        path: The Path object containing elements and constraints to simulate.
        config: Optional dict with default constraint values (e.g., from project config).
        dt_s: Simulation timestep in seconds (default 0.02s = 50Hz).

    Returns:
        SimResult containing poses indexed by time, sorted timestamps, total duration,
        and trail points for visualization.
    """
    cfg = config or {}
    segments, anchors, anchor_path_indices = _build_segments(path)

    poses_by_time: Dict[float, Tuple[float, float, float]] = {}
    times_sorted: List[float] = []
    trail_points: List[Tuple[float, float]] = []

    if len(anchors) < 2 or len(segments) == 0:
        if anchors:
            x0, y0 = anchors[0]
            poses_by_time[0.0] = (x0, y0, 0.0)
            times_sorted = [0.0]
            trail_points = [(x0, y0)]
        return SimResult(
            poses_by_time=poses_by_time,
            times_sorted=times_sorted,
            total_time_s=0.0,
            trail_points=trail_points,
        )

    c = getattr(path, "constraints", None)
    base_max_v = _resolve_constraint(
        getattr(c, "max_velocity_meters_per_sec", None),
        cfg.get("default_max_velocity_meters_per_sec"),
        3.0,
    )
    base_max_a = _resolve_constraint(
        getattr(c, "max_acceleration_meters_per_sec2", None),
        cfg.get("default_max_acceleration_meters_per_sec2"),
        2.5,
    )

    base_max_omega = math.radians(
        _resolve_constraint(
            getattr(c, "max_velocity_deg_per_sec", None),
            cfg.get("default_max_velocity_deg_per_sec"),
            180.0,
        )
    )
    base_max_alpha = math.radians(
        _resolve_constraint(
            getattr(c, "max_acceleration_deg_per_sec2", None),
            cfg.get("default_max_acceleration_deg_per_sec2"),
            360.0,
        )
    )

    # Tiny epsilon for exact end goal termination (idealized mechanics)
    _EPS_POS = 1e-3
    _EPS_ANG = 1e-3

    # Default handoff radius from config
    default_handoff_radius = _resolve_constraint(
        None, cfg.get("default_intermediate_handoff_radius_meters"), 0.05
    )

    total_path_len = 0.0
    cumulative_lengths: List[float] = [0.0]
    for seg in segments:
        L = max(seg.length_m, 0.0)
        total_path_len += L
        cumulative_lengths.append(total_path_len)

    first_seg = segments[0]
    start_heading_base = _default_heading(first_seg.ax, first_seg.ay, first_seg.bx, first_seg.by)

    # Build global rotation keyframes for rotation event ordinals and compute initial heading at s=0
    global_keyframes = _build_global_rotation_keyframes(
        path, anchor_path_indices, cumulative_lengths
    )
    initial_heading, _, _ = _desired_heading_for_global_s(global_keyframes, 0.0, start_heading_base)
    # Desired heading at the absolute end of the path
    end_heading_target, _, _ = _desired_heading_for_global_s(
        global_keyframes, total_path_len, start_heading_base
    )

    x = first_seg.ax
    y = first_seg.ay
    theta = initial_heading

    speeds = ChassisSpeeds(vx_mps=0.0, vy_mps=0.0, omega_radps=0.0)

    t_s = 0.0
    seg_idx = 0
    # Absolute end point
    end_x, end_y = anchors[-1]

    def remaining_distance_from(
        seg_index: int, current_x: float, current_y: float, proj_s: float
    ) -> float:
        """Calculate remaining path distance by summing actual distances to each subsequent target."""
        if seg_index >= len(segments):
            return 0.0

        remaining_distance = 0.0
        prev_x, prev_y = current_x, current_y  # Start from current position

        # Iterate through all remaining segments and sum distances to each endpoint
        for k in range(seg_index, len(segments)):
            seg = segments[k]
            # Add distance from previous point to end of this segment
            remaining_distance += hypot2(seg.bx - prev_x, seg.by - prev_y)
            # Update previous point to end of this segment
            prev_x, prev_y = seg.bx, seg.by

        return remaining_distance

    # Compute a realistic guard time using the slowest effective speed limits (including ranged constraints)
    min_trans_v = float(base_max_v)
    min_rot_omega_deg = math.degrees(float(base_max_omega))
    try:
        for rc in getattr(path, "ranged_constraints", []) or []:
            if not isinstance(rc, RangedConstraint):
                continue
            if rc.key == "max_velocity_meters_per_sec":
                try:
                    val = float(rc.value)
                    if val > 0.0:
                        min_trans_v = min(min_trans_v, val)
                except Exception:
                    pass
            elif rc.key == "max_velocity_deg_per_sec":
                try:
                    val = float(rc.value)
                    if val > 0.0:
                        min_rot_omega_deg = min(min_rot_omega_deg, val)
                except Exception:
                    pass
    except Exception:
        pass
    min_rot_omega = math.radians(max(1e-3, min_rot_omega_deg))
    min_trans_v = max(0.1, min_trans_v)
    est_trans_time = total_path_len / min_trans_v
    est_rot_time = math.pi / min_rot_omega  # enough for 180° worst-case
    guard_time = max(3.0, 2.0 * est_trans_time + 1.5 * est_rot_time)

    while t_s <= guard_time:
        if seg_idx >= len(segments):
            break

        seg = segments[seg_idx]

        dx = seg.bx - x
        dy = seg.by - y
        dist_to_target = hypot2(dx, dy)

        proj_dx = x - seg.ax
        proj_dy = y - seg.ay
        projected_s = dot(proj_dx, proj_dy, seg.ux, seg.uy)
        projected_s = max(0.0, min(projected_s, seg.length_m))

        # Get the current handoff radius for this segment
        current_handoff_radius = _get_handoff_radius_for_segment(
            path, seg_idx, anchor_path_indices, default_handoff_radius
        )

        # Only advance to the next segment via handoff radius if we are NOT on the last segment.
        # For the final segment, we finish based on end tolerances instead of handoff radius.
        while seg_idx < (len(segments) - 1) and dist_to_target <= current_handoff_radius:
            seg_idx += 1
            if seg_idx >= len(segments):
                break
            seg = segments[seg_idx]
            dx = seg.bx - x
            dy = seg.by - y
            dist_to_target = hypot2(dx, dy)
            proj_dx = x - seg.ax
            proj_dy = y - seg.ay
            projected_s = dot(proj_dx, proj_dy, seg.ux, seg.uy)
            projected_s = max(0.0, min(projected_s, seg.length_m))
            # Update handoff radius for the new segment
            current_handoff_radius = _get_handoff_radius_for_segment(
                path, seg_idx, anchor_path_indices, default_handoff_radius
            )

        if seg_idx >= len(segments):
            break

        if dist_to_target > 1e-9:
            ux = dx / dist_to_target
            uy = dy / dist_to_target
        else:
            ux = 1.0
            uy = 0.0

        # Compute desired heading using global keyframes at absolute distance along path
        global_s = cumulative_lengths[seg_idx] + projected_s
        desired_theta, _, _ = _desired_heading_for_global_s(
            global_keyframes, global_s, start_heading_base
        )

        remaining = remaining_distance_from(seg_idx, x, y, projected_s)

        # Resolve dynamic translation constraints for this segment based on next anchor ordinal (1-based)
        next_anchor_ord_1b = seg_idx + 2
        max_v_eff = _active_translation_limit(
            path, "max_velocity_meters_per_sec", next_anchor_ord_1b
        )
        max_a_eff = _active_translation_limit(
            path, "max_acceleration_meters_per_sec2", next_anchor_ord_1b
        )
        max_v = float(max_v_eff) if max_v_eff is not None else float(base_max_v)
        max_a = float(max_a_eff) if max_a_eff is not None else float(base_max_a)

        # Resolve dynamic rotation constraints based on the next rotation event ahead of current s
        max_omega_eff = _active_rotation_limit(
            path, global_keyframes, "max_velocity_deg_per_sec", global_s
        )
        max_alpha_eff = _active_rotation_limit(
            path, global_keyframes, "max_acceleration_deg_per_sec2", global_s
        )
        max_omega = (
            math.radians(float(max_omega_eff))
            if max_omega_eff is not None
            else float(base_max_omega)
        )
        max_alpha = (
            math.radians(float(max_alpha_eff))
            if max_alpha_eff is not None
            else float(base_max_alpha)
        )

        # 2ad controller: drive remaining distance to zero
        v_p_control = math.sqrt(2.0 * base_max_a * remaining)
        # Cap by velocity limit; leave acceleration limiting to the limiter below
        v_des_scalar = max(0.0, min(max_v, v_p_control))
        # If on the final segment and desired velocity collapses to ~0 while still away from the endpoint,
        # nudge toward the endpoint by requesting just enough velocity to reach it within one dt (bounded by max_v).
        if seg_idx == len(segments) - 1 and v_des_scalar <= 1e-9 and dist_to_target > _EPS_POS:
            v_des_scalar = min(max_v, dist_to_target / max(dt_s, 1e-9))

        vx_des = v_des_scalar * ux
        vy_des = v_des_scalar * uy

        # 2ad controller for rotation: omega = sqrt(2 * alpha * |error|)
        angular_error = shortest_angular_distance(desired_theta, theta)
        omega_control = math.sqrt(2.0 * max_alpha * abs(angular_error))
        # Cap by max_omega and apply sign based on error direction
        omega_des = min(omega_control, max_omega)
        if angular_error < 0:
            omega_des = -omega_des

        # Apply acceleration limiting AFTER desired speed has been clamped to max_v
        limited = limit_acceleration(
            desired=ChassisSpeeds(vx_des, vy_des, omega_des),
            last=speeds,
            dt=dt_s,
            max_trans_accel_mps2=max_a,
            max_angular_accel_radps2=max_alpha,
        )
        if abs(limited.omega_radps) > max_omega > 0.0:
            limited = ChassisSpeeds(
                limited.vx_mps, limited.vy_mps, math.copysign(max_omega, limited.omega_radps)
            )

        # Advance translation; clamp to final point on last segment to avoid overshoot with zero tolerances
        step_dx = limited.vx_mps * dt_s
        step_dy = limited.vy_mps * dt_s
        if seg_idx == len(segments) - 1:
            if hypot2(step_dx, step_dy) >= max(0.0, dist_to_target - _EPS_POS):
                x = end_x
                y = end_y
                # Once at final position, zero translational components to avoid endless micro-stepping
                limited = ChassisSpeeds(0.0, 0.0, limited.omega_radps)
            else:
                x += step_dx
                y += step_dy
        else:
            x += step_dx
            y += step_dy
        theta = wrap_angle_radians(theta + limited.omega_radps * dt_s)

        t_key = round(t_s, 3)
        poses_by_time[t_key] = (float(x), float(y), float(theta))
        times_sorted.append(t_key)

        # Add current position to trail
        trail_points.append((float(x), float(y)))

        # Check end-of-path conditions with ideal (zero) tolerances and internal eps snapping
        # Only check final endpoint termination when on the LAST segment to avoid early termination
        # when start and end points overlap (the robot must traverse all intermediate segments first)
        if seg_idx == len(segments) - 1:
            dx_end = end_x - x
            dy_end = end_y - y
            dist_to_final = hypot2(dx_end, dy_end)
            rot_err = abs(shortest_angular_distance(end_heading_target, theta))

            snapped_pos = False
            snapped_rot = False
            if dist_to_final <= _EPS_POS:
                x = end_x
                y = end_y
                dist_to_final = 0.0
                snapped_pos = True

            # Only check rotation snapping if we are close to the end point
            # to avoid premature snapping when start/end headings match but
            # intermediate rotation is required (e.g. W -> R -> W)
            if dist_to_final < 0.1 and rot_err <= _EPS_ANG:
                theta = end_heading_target
                rot_err = 0.0
                snapped_rot = True

            if snapped_pos or snapped_rot:
                poses_by_time[t_key] = (float(x), float(y), float(theta))
                trail_points[-1] = (float(x), float(y))
                # Zero corresponding velocities after snapping to avoid dithering away from the target
                if snapped_pos:
                    limited = ChassisSpeeds(0.0, 0.0, limited.omega_radps)
                    speeds = ChassisSpeeds(0.0, 0.0, speeds.omega_radps)
                if snapped_rot:
                    limited = ChassisSpeeds(limited.vx_mps, limited.vy_mps, 0.0)
                    speeds = ChassisSpeeds(speeds.vx_mps, speeds.vy_mps, 0.0)
                # If both snapped this step, we are exactly at the final state; terminate immediately
                if snapped_pos and snapped_rot:
                    speeds = ChassisSpeeds(0.0, 0.0, 0.0)
                    break

        t_s += dt_s
        speeds = limited

    last_time = round(t_s, 3)
    if last_time not in poses_by_time and times_sorted:
        poses_by_time[last_time] = poses_by_time[times_sorted[-1]]
        times_sorted.append(last_time)

    seen = set()
    uniq_times: List[float] = []
    for tk in times_sorted:
        if tk in seen:
            continue
        seen.add(tk)
        uniq_times.append(tk)

    total_time_s = uniq_times[-1] if uniq_times else 0.0
    return SimResult(
        poses_by_time=poses_by_time,
        times_sorted=uniq_times,
        total_time_s=total_time_s,
        trail_points=trail_points,
    )
