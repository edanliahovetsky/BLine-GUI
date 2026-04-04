"""Constants and enums for the sidebar module."""

from enum import Enum
from ui.canvas import FIELD_LENGTH_METERS, FIELD_WIDTH_METERS


class ElementType(Enum):
    """Enum representing different types of path elements."""

    TRANSLATION = "translation"
    ROTATION = "rotation"
    WAYPOINT = "waypoint"
    EVENT_TRIGGER = "event_trigger"


# Human-readable labels for element types
ELEMENT_TYPE_LABELS = {
    ElementType.TRANSLATION: "Translation",
    ElementType.ROTATION: "Rotation",
    ElementType.WAYPOINT: "Waypoint",
    ElementType.EVENT_TRIGGER: "Event Trigger",
}

# Reverse mapping: friendly label -> ElementType
ELEMENT_LABEL_TO_TYPE = {v: k for k, v in ELEMENT_TYPE_LABELS.items()}


# Spinner metadata configuration
SPINNER_METADATA = {
    # Put rotation first so it appears at the top of Core
    "rotation_degrees": {
        "label": "Rotation (deg)",
        "step": 1.0,
        "range": (-99999.0, 99999.0),
        "removable": False,
        "section": "core",
    },
    "x_meters": {
        "label": "X (m)",
        "step": 0.05,
        "range": (0.0, float(FIELD_LENGTH_METERS)),
        "removable": False,
        "section": "core",
    },
    "y_meters": {
        "label": "Y (m)",
        "step": 0.05,
        "range": (0.0, float(FIELD_WIDTH_METERS)),
        "removable": False,
        "section": "core",
    },
    # Handoff radius is a core control for TranslationTarget and Waypoint
    "intermediate_handoff_radius_meters": {
        "label": "Handoff Radius (m)",
        "step": 0.05,
        "range": (0, 99999),
        "removable": False,
        "section": "core",
    },
    # Ratio along the segment between previous and next anchors for rotation elements (0..1)
    "rotation_position_ratio": {
        "label": "Rotation Pos (0–1)",
        "step": 0.01,
        "range": (0.0, 1.0),
        "removable": False,
        "section": "core",
    },
    "event_trigger_position_ratio": {
        "label": "Event Pos (0–1)",
        "step": 0.01,
        "range": (0.0, 1.0),
        "removable": False,
        "section": "core",
    },
    "event_trigger_lib_key": {
        "label": "Lib Key",
        "type": "text",
        "removable": False,
        "section": "core",
    },
    # Boolean checkbox for profiled rotation
    "profiled_rotation": {
        "label": "Profiled Rotation",
        "type": "checkbox",
        "removable": False,
        "section": "core",
    },
    # Constraints (optional)
    "max_velocity_meters_per_sec": {
        "label": "Max Velocity (m/s)",
        "step": 0.1,
        "range": (0, 99999),
        "removable": True,
        "section": "constraints",
    },
    "max_acceleration_meters_per_sec2": {
        "label": "Max Acceleration (m/s²)",
        "step": 0.1,
        "range": (0, 99999),
        "removable": True,
        "section": "constraints",
    },
    "max_velocity_deg_per_sec": {
        "label": "Max Rot Velocity<br/>(deg/s)",
        "step": 1.0,
        "range": (0, 99999),
        "removable": True,
        "section": "constraints",
    },
    "max_acceleration_deg_per_sec2": {
        "label": "Max Rot Acceleration<br/>(deg/s²)",
        "step": 1.0,
        "range": (0, 99999),
        "removable": True,
        "section": "constraints",
    },
    "end_translation_tolerance_meters": {
        "label": "End Translation Tol (m)",
        "step": 0.005,
        "range": (0.0, 5.0),
        "removable": True,
        "section": "constraints",
    },
    "end_rotation_tolerance_deg": {
        "label": "End Rotation Tol (deg)",
        "step": 0.1,
        "range": (0.0, 180.0),
        "removable": True,
        "section": "constraints",
    },
}

# Map UI spinner keys to model attribute names (for rotation fields in degrees)
DEGREES_TO_RADIANS_ATTR_MAP = {"rotation_degrees": "rotation_radians"}

# Path constraint keys
PATH_CONSTRAINT_KEYS = [
    # Ranged-capable constraints
    "max_velocity_meters_per_sec",
    "max_acceleration_meters_per_sec2",
    "max_velocity_deg_per_sec",
    "max_acceleration_deg_per_sec2",
    # Non-ranged constraints
    "end_translation_tolerance_meters",
    "end_rotation_tolerance_deg",
]

# Subset of constraint keys that are always stored as flat (non-ranged) values
NON_RANGED_CONSTRAINT_KEYS = [
    "end_translation_tolerance_meters",
    "end_rotation_tolerance_deg",
]

# Constraint keys that support ranged (per-segment) editing
RANGED_CONSTRAINT_KEYS = [
    "max_velocity_meters_per_sec",
    "max_acceleration_meters_per_sec2",
    "max_velocity_deg_per_sec",
    "max_acceleration_deg_per_sec2",
]

# Constraint keys in the translation domain (TranslationTarget + Waypoint)
TRANSLATION_CONSTRAINT_KEYS = frozenset({
    "max_velocity_meters_per_sec",
    "max_acceleration_meters_per_sec2",
})


def _extract_unit(label: str) -> str:
    """Extract the unit suffix from a label like 'X (m)' -> ' m'.

    Returns empty string for non-unit parenthetical info (e.g. '(0-1)').
    """
    import re
    m = re.search(r'\(([^)]+)\)\s*$', label.replace("<br/>", " "))
    if m:
        unit = m.group(1)
        # Skip range indicators like "0-1" — those aren't units
        if re.fullmatch(r'[\d.\-–]+', unit):
            return ""
        return " " + unit
    return ""


# Pre-computed mapping of spinner key -> unit suffix string (e.g. " m", " deg")
SPINNER_UNITS = {
    key: _extract_unit(str(data.get("label", "")))
    for key, data in SPINNER_METADATA.items()
    if data.get("type", "spinner") == "spinner"
}


def constraint_default_value(key: str) -> float:
    """Return the metadata-backed default value for a constraint spinner."""
    meta = SPINNER_METADATA.get(key, {})
    default_value = meta.get("default")
    if isinstance(default_value, (int, float)):
        return float(default_value)

    range_values = meta.get("range")
    if (
        isinstance(range_values, tuple)
        and len(range_values) == 2
        and isinstance(range_values[0], (int, float))
    ):
        return float(range_values[0])

    return 0.0
