"""Pure serialization helpers for project paths and assets."""

from __future__ import annotations

import json
import os
from typing import Any, Callable, Dict, List, Optional

from models.path_model import (
    Path,
    PathElement,
    RotationTarget,
    RangedConstraint,
    TranslationTarget,
    Waypoint,
    EventTrigger,
)

DefaultLookup = Callable[[str], Optional[float]]


def serialize_path(path: Path) -> Dict[str, Any]:
    """Convert a Path model into the JSON structure stored on disk."""
    items: List[Dict[str, Any]] = []
    for elem in path.path_elements:
        if isinstance(elem, TranslationTarget):
            entry: Dict[str, Any] = {
                "type": "translation",
                "x_meters": float(elem.x_meters),
                "y_meters": float(elem.y_meters),
            }
            if elem.intermediate_handoff_radius_meters is not None:
                entry["intermediate_handoff_radius_meters"] = float(
                    elem.intermediate_handoff_radius_meters
                )
            items.append(entry)
        elif isinstance(elem, RotationTarget):
            entry = {
                "type": "rotation",
                "rotation_radians": float(elem.rotation_radians),
                "t_ratio": float(getattr(elem, "t_ratio", 0.0)),
                "profiled_rotation": bool(getattr(elem, "profiled_rotation", True)),
            }
            items.append(entry)
        elif isinstance(elem, EventTrigger):
            entry = {
                "type": "event_trigger",
                "t_ratio": float(getattr(elem, "t_ratio", 0.0)),
                "lib_key": str(getattr(elem, "lib_key", "")),
            }
            items.append(entry)
        elif isinstance(elem, Waypoint):
            translation_data = {
                "x_meters": float(elem.translation_target.x_meters),
                "y_meters": float(elem.translation_target.y_meters),
            }
            if elem.translation_target.intermediate_handoff_radius_meters is not None:
                translation_data["intermediate_handoff_radius_meters"] = float(
                    elem.translation_target.intermediate_handoff_radius_meters
                )
            rotation_data = {
                "rotation_radians": float(elem.rotation_target.rotation_radians),
                "profiled_rotation": bool(getattr(elem.rotation_target, "profiled_rotation", True)),
            }
            items.append(
                {
                    "type": "waypoint",
                    "translation_target": translation_data,
                    "rotation_target": rotation_data,
                }
            )
        else:
            continue

    constraints_obj: Dict[str, Any] = {}
    ranged_keys: set[str] = set()
    try:
        for rc in getattr(path, "ranged_constraints", []) or []:
            if isinstance(rc, RangedConstraint) and rc.key in (
                "max_velocity_meters_per_sec",
                "max_acceleration_meters_per_sec2",
                "max_velocity_deg_per_sec",
                "max_acceleration_deg_per_sec2",
            ):
                ranged_keys.add(rc.key)
    except Exception:
        ranged_keys = set()

    if hasattr(path, "constraints") and path.constraints is not None:
        constraints = path.constraints
        for name in [
            "max_velocity_meters_per_sec",
            "max_acceleration_meters_per_sec2",
            "end_translation_tolerance_meters",
            "max_velocity_deg_per_sec",
            "max_acceleration_deg_per_sec2",
            "end_rotation_tolerance_deg",
        ]:
            if name in ranged_keys:
                continue
            value = getattr(constraints, name, None)
            if value is not None:
                constraints_obj[name] = float(value)

    ranged_grouped: Dict[str, List[Dict[str, Any]]] = {}
    try:
        for rc in getattr(path, "ranged_constraints", []) or []:
            if not isinstance(rc, RangedConstraint) or rc.key not in (
                "max_velocity_meters_per_sec",
                "max_acceleration_meters_per_sec2",
                "max_velocity_deg_per_sec",
                "max_acceleration_deg_per_sec2",
            ):
                continue
            try:
                start_zero_based = max(int(rc.start_ordinal) - 1, 0)
                end_zero_based = max(int(rc.end_ordinal) - 1, 0)
            except Exception:
                start_zero_based = 0
                end_zero_based = 0
            entry = {
                "value": float(rc.value),
                "start_ordinal": start_zero_based,
                "end_ordinal": end_zero_based,
            }
            ranged_grouped.setdefault(str(rc.key), []).append(entry)
    except Exception:
        ranged_grouped = {}

    if ranged_grouped:
        for key, values in ranged_grouped.items():
            constraints_obj[key] = values

    result: Dict[str, Any] = {"path_elements": items}
    if constraints_obj:
        result["constraints"] = constraints_obj
    return result


def deserialize_path(data: Any, default_lookup: DefaultLookup | None = None) -> Path:
    """Construct a Path object from JSON data."""
    path = Path()
    ranged_block: Any = []
    if isinstance(data, list):
        items = data
    else:
        if not isinstance(data, dict):
            return path
        constraints_block = data.get("constraints", {}) or {}
        if (
            isinstance(constraints_block, dict)
            and hasattr(path, "constraints")
            and path.constraints is not None
        ):
            for key in [
                "max_velocity_meters_per_sec",
                "max_acceleration_meters_per_sec2",
                "end_translation_tolerance_meters",
                "max_velocity_deg_per_sec",
                "max_acceleration_deg_per_sec2",
                "end_rotation_tolerance_deg",
            ]:
                if key in constraints_block:
                    setattr(path.constraints, key, _opt_float(constraints_block.get(key)))
                else:
                    legacy = f"default_{key}"
                    if legacy in constraints_block:
                        setattr(path.constraints, key, _opt_float(constraints_block.get(legacy)))

        ranged_block_list: List[Dict[str, Any]] = []
        try:
            if isinstance(constraints_block, dict):
                for key, value in constraints_block.items():
                    if isinstance(value, list):
                        for entry in value:
                            if isinstance(entry, dict):
                                entry_copy = dict(entry)
                                entry_copy["key"] = key
                                ranged_block_list.append(entry_copy)
        except Exception:
            pass
        ranged_block = ranged_block_list
        items = (
            data.get("path_elements", []) if isinstance(data.get("path_elements", []), list) else []
        )

    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            typ = item.get("type")
            if typ == "translation":
                handoff_radius = _handoff_default(
                    item.get("intermediate_handoff_radius_meters"), default_lookup
                )
                path.path_elements.append(
                    TranslationTarget(
                        x_meters=float(item.get("x_meters", 0.0)),
                        y_meters=float(item.get("y_meters", 0.0)),
                        intermediate_handoff_radius_meters=handoff_radius,
                    )
                )
            elif typ == "rotation":
                t_ratio_val = item.get("t_ratio")
                profiled_rotation_val = bool(item.get("profiled_rotation", True))
                rotation = RotationTarget(
                    rotation_radians=float(item.get("rotation_radians", 0.0)),
                    t_ratio=float(t_ratio_val) if t_ratio_val is not None else 0.0,
                    profiled_rotation=profiled_rotation_val,
                )
                if t_ratio_val is None:
                    rx = _opt_float(item.get("x_meters"))
                    ry = _opt_float(item.get("y_meters"))
                    if rx is not None and ry is not None:
                        rotation.legacy_position = (rx, ry)
                path.path_elements.append(rotation)
            elif typ == "event_trigger":
                t_ratio_val = item.get("t_ratio")
                trigger = EventTrigger(
                    t_ratio=float(t_ratio_val) if t_ratio_val is not None else 0.0,
                    lib_key=str(item.get("lib_key", "")),
                )
                path.path_elements.append(trigger)
            elif typ == "waypoint":
                translation_data = item.get("translation_target", {}) or {}
                rotation_data = item.get("rotation_target", {}) or {}
                rotation = RotationTarget(
                    rotation_radians=float(rotation_data.get("rotation_radians", 0.0)),
                    t_ratio=float(rotation_data.get("t_ratio", 0.0)),
                    profiled_rotation=bool(rotation_data.get("profiled_rotation", True)),
                )
                if "t_ratio" not in rotation_data:
                    rotation.t_ratio = 0.0
                    rx = _opt_float(rotation_data.get("x_meters"))
                    ry = _opt_float(rotation_data.get("y_meters"))
                    if rx is not None and ry is not None:
                        rotation.legacy_position = (rx, ry)
                handoff_radius = _handoff_default(
                    translation_data.get("intermediate_handoff_radius_meters"),
                    default_lookup,
                )
                waypoint = Waypoint(
                    translation_target=TranslationTarget(
                        x_meters=float(translation_data.get("x_meters", 0.0)),
                        y_meters=float(translation_data.get("y_meters", 0.0)),
                        intermediate_handoff_radius_meters=handoff_radius,
                    ),
                    rotation_target=rotation,
                )
                path.path_elements.append(waypoint)
        except Exception:
            continue

    _convert_legacy_positions(path)
    _load_ranged_constraints(path, ranged_block)
    return path


def create_example_paths(paths_dir: str) -> None:
    """Write example config + path files if none exist."""
    try:
        path1 = Path()
        path1.path_elements.extend(
            [
                TranslationTarget(x_meters=2.0, y_meters=2.0),
                RotationTarget(rotation_radians=0.0, t_ratio=0.5, profiled_rotation=True),
                Waypoint(
                    translation_target=TranslationTarget(x_meters=6.0, y_meters=4.0),
                    rotation_target=RotationTarget(
                        rotation_radians=0.5, t_ratio=0.0, profiled_rotation=True
                    ),
                ),
                TranslationTarget(x_meters=10.0, y_meters=6.0),
            ]
        )
        with open(os.path.join(paths_dir, "example_a.json"), "w", encoding="utf-8") as handle:
            json.dump(serialize_path(path1), handle, indent=2)
    except Exception:
        pass

    try:
        path2 = Path()
        path2.path_elements.extend(
            [
                TranslationTarget(x_meters=1.0, y_meters=7.5),
                TranslationTarget(x_meters=5.0, y_meters=6.0),
                RotationTarget(rotation_radians=1.2, t_ratio=0.5, profiled_rotation=True),
                TranslationTarget(x_meters=12.5, y_meters=3.0),
            ]
        )
        with open(os.path.join(paths_dir, "example_b.json"), "w", encoding="utf-8") as handle:
            json.dump(serialize_path(path2), handle, indent=2)
    except Exception:
        pass


def _handoff_default(value: Any, default_lookup: DefaultLookup | None) -> Optional[float]:
    option = _opt_float(value)
    if option is not None:
        return option
    if default_lookup is None:
        return None
    return default_lookup("intermediate_handoff_radius_meters")


def _convert_legacy_positions(path: Path) -> None:
    try:
        for idx, element in enumerate(path.path_elements):
            target: PathElement | None = None
            if isinstance(element, RotationTarget):
                target = element
            elif isinstance(element, Waypoint):
                target = element.rotation_target
            if (
                target is None
                or not isinstance(target, RotationTarget)
                or target.legacy_position is None
                or target.legacy_converted
            ):
                continue
            rx, ry = target.legacy_position
            prev_pos = _find_neighbor(path.path_elements, idx, reverse=True)
            next_pos = _find_neighbor(path.path_elements, idx, reverse=False)
            if prev_pos is None or next_pos is None:
                setattr(target, "t_ratio", 0.0)
            else:
                ax, ay = prev_pos
                bx, by = next_pos
                dx = bx - ax
                dy = by - ay
                denom = dx * dx + dy * dy
                if denom <= 0.0:
                    t_value = 0.0
                else:
                    t_value = ((rx - ax) * dx + (ry - ay) * dy) / denom
                    t_value = max(0.0, min(1.0, t_value))
                setattr(target, "t_ratio", float(t_value))
            target.legacy_position = None
            target.legacy_converted = True
    except Exception:
        pass


def _find_neighbor(
    elements: List[PathElement], start_index: int, *, reverse: bool
) -> Optional[tuple[float, float]]:
    indices = range(start_index - 1, -1, -1) if reverse else range(start_index + 1, len(elements))
    for idx in indices:
        candidate = elements[idx]
        if isinstance(candidate, TranslationTarget):
            return float(candidate.x_meters), float(candidate.y_meters)
        if isinstance(candidate, Waypoint):
            tt = candidate.translation_target
            return float(tt.x_meters), float(tt.y_meters)
    return None


def _load_ranged_constraints(path: Path, ranged_block: Any) -> None:
    try:
        normalized: List[Dict[str, Any]] = []
        if isinstance(ranged_block, list):
            normalized = [entry for entry in ranged_block if isinstance(entry, dict)]
        elif isinstance(ranged_block, dict):
            for key, arr in ranged_block.items():
                if not isinstance(arr, list):
                    continue
                for entry in arr:
                    if isinstance(entry, dict):
                        entry_copy = dict(entry)
                        entry_copy["key"] = key
                        normalized.append(entry_copy)

        anchor_count = 0
        rotation_event_count = 0
        for element in path.path_elements:
            if isinstance(element, (TranslationTarget, Waypoint)):
                anchor_count += 1
            if isinstance(element, (RotationTarget, Waypoint)):
                rotation_event_count += 1

        for entry in normalized:
            key = str(entry.get("key", ""))
            if key not in (
                "max_velocity_meters_per_sec",
                "max_acceleration_meters_per_sec2",
                "max_velocity_deg_per_sec",
                "max_acceleration_deg_per_sec2",
            ):
                continue
            value = _opt_float(entry.get("value"))
            if value is None:
                continue
            start_int = int(entry.get("start_ordinal") or 0)
            end_int = int(entry.get("end_ordinal") or 0)
            domain_size = (
                anchor_count
                if key in ("max_velocity_meters_per_sec", "max_acceleration_meters_per_sec2")
                else rotation_event_count
            )
            if (
                domain_size > 0
                and 0 <= start_int <= domain_size - 1
                and 0 <= end_int <= domain_size - 1
            ):
                start_int += 1
                end_int += 1
            elif start_int == 0 or end_int == 0:
                start_int += 1
                end_int += 1
            path.ranged_constraints.append(
                RangedConstraint(
                    key=key,
                    value=float(value),
                    start_ordinal=start_int,
                    end_ordinal=end_int,
                )
            )
    except Exception:
        pass


def _opt_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
