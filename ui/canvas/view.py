# mypy: ignore-errors
"""Refactored modular CanvasView building on decomposed items/components.

NOTE: This is an in-progress extraction from the monolithic ui/canvas.py.
It currently reuses many original private method names for compatibility
with MainWindow and Sidebar interactions. Further pruning can follow.
"""

from __future__ import annotations
import math
from typing import List, Optional, Tuple, Any
from PySide6.QtWidgets import (
    QGraphicsView,
    QGraphicsScene,
    QGraphicsPixmapItem,
    QGraphicsLineItem,
    QFrame,
)
from PySide6.QtCore import QPointF, QTimer, Signal, QPoint
from PySide6.QtGui import QPixmap, QTransform, QColor, QPen, QBrush, QPixmapCache

from ui.qt_compat import Qt, QPainter, QGraphicsItem

from models.path_model import (
    Path,
    PathElement,
    TranslationTarget,
    RotationTarget,
    Waypoint,
    EventTrigger,
)
from models.simulation import simulate_path, SimResult
from .constants import (
    FIELD_LENGTH_METERS,
    FIELD_WIDTH_METERS,
    FIELD_OFFSET_M,
    CONNECT_LINE_THICKNESS_M,
    HANDLE_DISTANCE_M,
    HANDLE_RADIUS_M,
    ELEMENT_RECT_WIDTH_M,
    ELEMENT_RECT_HEIGHT_M,
    DEFAULT_ZOOM_FACTOR,
    MIN_ZOOM_FACTOR,
    MAX_ZOOM_FACTOR,
    ZOOM_STEP_FACTOR,
    SIMULATION_UPDATE_INTERVAL_MS,
    SIMULATION_DEBOUNCE_INTERVAL_MS,
    SELECTION_PULSE_INTERVAL_MS,
    SELECTION_PULSE_STEP_RAD,
    SELECTION_PULSE_MIN_ALPHA,
    SELECTION_PULSE_MAX_ALPHA,
    SELECTION_PULSE_WIDTH_SCALE_MIN,
    SELECTION_PULSE_WIDTH_SCALE_MAX,
)
from .items.elements import (
    CircleElementItem,
    RectElementItem,
    RotationHandle,
    HandoffRadiusVisualizer,
    EventTriggerItem,
)
from .items.sim import RobotSimItem
from .components.transport import TransportControls


def _get_translation_position(element: Any) -> Tuple[float, float]:
    """Get the translation position (x, y) from a TranslationTarget or Waypoint element."""
    if isinstance(element, TranslationTarget):
        return float(element.x_meters), float(element.y_meters)
    elif isinstance(element, Waypoint):
        return float(element.translation_target.x_meters), float(
            element.translation_target.y_meters
        )
    else:
        return 0.0, 0.0


class CanvasView(QGraphicsView):
    # Signals (mirroring original)
    elementSelected = Signal(int)
    selectionCleared = Signal()
    elementMoved = Signal(int, float, float)
    elementRotated = Signal(int, float)
    elementDragFinished = Signal(int)
    deleteSelectedRequested = Signal()
    rotationDragFinished = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRenderHint(QPainter.Antialiasing, True)
        self.setViewportUpdateMode(QGraphicsView.BoundingRectViewportUpdate)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setFocusPolicy(Qt.StrongFocus)
        # Subtle rounded corners on the canvas frame
        try:
            self.setAttribute(Qt.WA_StyledBackground, True)
            # Keep the frame visually minimal while rounding corners
            self.setFrameShape(QFrame.NoFrame)
            # Apply rounding to both the view and its viewport to ensure clipping
            self.setStyleSheet("QGraphicsView { border-radius: 8px; background: palette(Base); }")
            if self.viewport() is not None:
                try:
                    self.viewport().setAttribute(Qt.WA_StyledBackground, True)
                    self.viewport().setStyleSheet("border-radius: 8px; background: palette(Base);")
                except Exception:
                    pass
        except Exception:
            pass
        self._is_fitting = False
        self._suppress_live_events = False
        self._rotation_t_cache: Optional[dict[int, float]] = None
        self._anchor_drag_in_progress = False
        self._zoom_factor = DEFAULT_ZOOM_FACTOR
        self._min_zoom = MIN_ZOOM_FACTOR
        self._max_zoom = MAX_ZOOM_FACTOR
        self._is_panning = False
        self._pan_start: Optional[QPoint] = None
        self.robot_length_m = ELEMENT_RECT_WIDTH_M
        self.robot_width_m = ELEMENT_RECT_HEIGHT_M
        self.protrusion_enabled: bool = False
        self.protrusion_distance_m: float = 0.0
        self.protrusion_side: str = "none"
        self.protrusion_default_state: str = ""
        self.protrusion_show_on_event_keys: set[str] = set()
        self.protrusion_hide_on_event_keys: set[str] = set()
        self._protrusion_current_visible: bool = False
        self._protrusion_trigger_schedule: list[tuple[float, bool]] = []
        self._element_protrusion_visibility_by_index: dict[int, bool] = {}
        self._sim_global_s_by_time: dict[float, float] = {}
        self._field_offset: float = FIELD_OFFSET_M  # 0.5m for 2026
        self.graphics_scene = QGraphicsScene(self)
        self.setScene(self.graphics_scene)
        self.graphics_scene.selectionChanged.connect(self._on_scene_selection_changed)
        self.graphics_scene.setSceneRect(0, 0, FIELD_LENGTH_METERS, FIELD_WIDTH_METERS)
        self._field_pixmap_item: Optional[QGraphicsPixmapItem] = None
        self._path: Optional[Path] = None
        self._items: List[Tuple[str, RectElementItem, Optional[RotationHandle]]] = []
        self._connect_lines: List[QGraphicsLineItem] = []
        self._handoff_visualizers: List[Optional[HandoffRadiusVisualizer]] = []
        self._selection_pulse_phase: float = 0.0
        self._selection_pulse_alpha: float = SELECTION_PULSE_MAX_ALPHA
        self._selection_pulse_width_scale: float = 1.0
        self._last_selected_items: set[QGraphicsItem] = set()
        self._active_press_index: Optional[int] = None
        self._press_moved: bool = False
        self._press_rotated: bool = False
        self._press_start_scene_pos: Optional[QPointF] = None
        self._press_start_angle_radians: Optional[float] = None
        self._press_move_epsilon_sq: float = 1e-6
        self._press_rotation_epsilon_rad: float = math.radians(0.05)
        self._selection_pulse_timer: QTimer = QTimer(self)
        self._selection_pulse_timer.setInterval(SELECTION_PULSE_INTERVAL_MS)
        self._selection_pulse_timer.timeout.connect(self._on_selection_pulse_tick)
        self._load_field_background(":/assets/field26.png")
        # Simulation state
        self._sim_result: Optional[SimResult] = None
        self._sim_poses_by_time: dict[float, tuple[float, float, float]] = {}
        self._sim_times_sorted: list[float] = []
        self._sim_total_time_s = 0.0
        self._sim_current_time_s = 0.0
        self._sim_timer: QTimer = QTimer(self)
        self._sim_timer.setInterval(SIMULATION_UPDATE_INTERVAL_MS)
        self._sim_timer.timeout.connect(self._on_sim_tick)
        self._sim_debounce: QTimer = QTimer(self)
        self._sim_debounce.setSingleShot(True)
        self._sim_debounce.setInterval(SIMULATION_DEBOUNCE_INTERVAL_MS)
        self._sim_debounce.timeout.connect(self._rebuild_simulation_now)
        self._sim_robot_item: Optional[RobotSimItem] = None
        self._ensure_sim_robot_item()
        self._trail_lines: List[QGraphicsLineItem] = []
        self._trail_points: List[Tuple[float, float]] = []
        self.transport = TransportControls(self)
        self.transport.ensure()
        self._range_overlay_lines: List[QGraphicsLineItem] = []
        self._range_overlay_saved_item_styles: dict[QGraphicsItem, Tuple[QPen, QBrush]] = {}

    # ---------------- Field Background ----------------
    def _load_field_background(self, image_path: str):
        pixmap = QPixmap(image_path)
        if pixmap.isNull():
            return
        self._field_pixmap_item = QGraphicsPixmapItem(pixmap)
        self._field_pixmap_item.setZValue(-10)
        if pixmap.width() > 0 and pixmap.height() > 0:
            # Scale the background so it fully fits inside the logical field rectangle
            # while preserving aspect ratio. Previously a hard‑coded PPM (200) was applied
            # for field25.png which could make the scaled pixmap wider than
            # FIELD_LENGTH_METERS, causing the right edge to be clipped when the view
            # fit the sceneRect. We now always apply aspect-fit scaling.
            try:
                scale_w = FIELD_LENGTH_METERS / float(pixmap.width())
                scale_h = FIELD_WIDTH_METERS / float(pixmap.height())
                s = min(scale_w, scale_h)
            except Exception:
                s = 1.0
            self._field_pixmap_item.setTransform(QTransform().scale(s, s))
            # Bottom-align the image within the field height so (0,0) remains top-left in model coords.
            h_scaled = pixmap.height() * s
            w_scaled = pixmap.width() * s
            # If width ends up smaller than field length (letterboxing), center it; else anchor at x=0.
            x_offset = 0.0
            try:
                if w_scaled < FIELD_LENGTH_METERS:
                    x_offset = (FIELD_LENGTH_METERS - w_scaled) / 2.0
            except Exception:
                x_offset = 0.0
            self._field_pixmap_item.setPos(x_offset, FIELD_WIDTH_METERS - h_scaled)
        self.graphics_scene.addItem(self._field_pixmap_item)

    def set_project_manager(self, project_manager):
        self._project_manager = project_manager

    # ------------- Path / Items -------------
    def set_path(self, path: Path):
        self._path = path
        self._last_selected_items.clear()
        try:
            self.clear_constraint_range_overlay()
        except Exception:
            pass
        self._rebuild_items()
        self._on_scene_selection_changed()
        self._rebuild_protrusion_trigger_schedule()
        self._rebuild_element_protrusion_visibility_map()
        self._apply_protrusion_visual_to_all_items()
        self._set_protrusion_visible(self._default_protrusion_visible())
        if self._path:
            self._reproject_rotation_items_in_scene()
        self.request_simulation_rebuild()

    @staticmethod
    def _coerce_bool(value: Any, fallback: bool = False) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in ("1", "true", "yes", "on", "enabled"):
                return True
            if lowered in ("0", "false", "no", "off", "disabled"):
                return False
        return fallback

    @staticmethod
    def _normalize_protrusion_side(value: Any) -> str:
        raw = str(value).strip().lower()
        return raw if raw in ("none", "left", "right", "front", "back") else "none"

    @staticmethod
    def _normalize_protrusion_state(value: Any) -> str:
        raw = str(value).strip().lower()
        if raw in ("shown", "show", "visible", "on", "true", "1"):
            return "shown"
        if raw in ("hidden", "hide", "invisible", "off", "false", "0"):
            return "hidden"
        return ""

    @staticmethod
    def _normalize_event_key_set(value: Any) -> set[str]:
        if value is None:
            return set()
        if isinstance(value, str):
            raw_items = value.replace("\n", ",").split(",")
        elif isinstance(value, (list, tuple, set)):
            raw_items = [str(v) for v in value]
        else:
            raw_items = [str(value)]
        return {str(v).strip() for v in raw_items if str(v).strip()}

    def _default_protrusion_visible(self) -> bool:
        return bool(self.protrusion_enabled and self.protrusion_default_state == "shown")

    def set_robot_dimensions(self, length_m: float, width_m: float):
        try:
            self.robot_length_m = float(length_m)
            self.robot_width_m = float(width_m)
            cfg = {}
            if hasattr(self, "_project_manager") and self._project_manager:
                if hasattr(self._project_manager, "config_as_dict"):
                    cfg = self._project_manager.config_as_dict()
                else:
                    cfg = dict(getattr(self._project_manager, "config", {}) or {})
            self.protrusion_enabled = self._coerce_bool(
                cfg.get("protrusion_enabled", self.protrusion_enabled),
                self.protrusion_enabled,
            )
            self.protrusion_distance_m = max(
                0.0,
                float(cfg.get("protrusion_distance_meters", self.protrusion_distance_m) or 0.0),
            )
            self.protrusion_side = self._normalize_protrusion_side(
                cfg.get("protrusion_side", self.protrusion_side)
            )
            self.protrusion_default_state = self._normalize_protrusion_state(
                cfg.get("protrusion_default_state", self.protrusion_default_state)
            )
            if not self.protrusion_enabled:
                self.protrusion_default_state = ""
            self.protrusion_show_on_event_keys = self._normalize_event_key_set(
                cfg.get("protrusion_show_on_event_keys", self.protrusion_show_on_event_keys)
            )
            self.protrusion_hide_on_event_keys = self._normalize_event_key_set(
                cfg.get("protrusion_hide_on_event_keys", self.protrusion_hide_on_event_keys)
            )
        except Exception:
            return
        self._rebuild_items()
        self._rebuild_protrusion_trigger_schedule()
        self._rebuild_element_protrusion_visibility_map()
        self._apply_protrusion_visual_to_all_items()
        self._set_protrusion_visible(self._default_protrusion_visible())
        if self._path:
            self._reproject_rotation_items_in_scene()
        try:
            self._ensure_sim_robot_item()
            self._update_sim_robot_dimensions()
        except Exception:
            pass

    # ----------- Handoff Radius -----------
    def update_handoff_radius_visualizers(self):
        if self._path is None or not self._items:
            return
        from models.path_model import TranslationTarget, Waypoint

        for i, (kind, item, _handle) in enumerate(self._items):
            if i >= len(self._handoff_visualizers):
                continue
            element = self._path.path_elements[i]
            pos = self._element_position_for_index(i)
            # Do not show handoff radius for the last path element
            try:
                if i == len(self._path.path_elements) - 1:
                    if self._handoff_visualizers[i] is not None:
                        self.graphics_scene.removeItem(self._handoff_visualizers[i])
                        self._handoff_visualizers[i].deleteLater()
                        self._handoff_visualizers[i] = None
                    continue
            except Exception:
                pass
            if kind in ("rotation", "event_trigger"):
                if self._handoff_visualizers[i] is not None:
                    self.graphics_scene.removeItem(self._handoff_visualizers[i])
                    self._handoff_visualizers[i].deleteLater()
                    self._handoff_visualizers[i] = None
                continue
            radius = None
            if isinstance(element, TranslationTarget):
                radius = getattr(element, "intermediate_handoff_radius_meters", None)
            elif isinstance(element, Waypoint):
                radius = getattr(
                    element.translation_target, "intermediate_handoff_radius_meters", None
                )
            if radius is None or radius <= 0:
                try:
                    if hasattr(self, "_project_manager") and self._project_manager:
                        default_radius = self._project_manager.get_default_optional_value(
                            "intermediate_handoff_radius_meters"
                        )
                        if default_radius and default_radius > 0:
                            radius = default_radius
                except Exception:
                    pass
            current = self._handoff_visualizers[i]
            if radius and radius > 0 and current is None:
                hv = HandoffRadiusVisualizer(self, QPointF(pos[0], pos[1]), radius)
                self.graphics_scene.addItem(hv)
                self._handoff_visualizers[i] = hv
            elif (not radius or radius <= 0) and current is not None:
                self.graphics_scene.removeItem(current)
                current.deleteLater()
                self._handoff_visualizers[i] = None
            elif radius and radius > 0 and current is not None:
                current.set_center(QPointF(pos[0], pos[1]))
                current.set_radius(radius)
        self.request_simulation_rebuild()

    def refresh_from_model(self):
        if self._path is None or not self._items:
            return
        self._suppress_live_events = True
        try:
            count = min(len(self._items), len(self._path.path_elements))
            for i in range(count):
                try:
                    kind, item, handle = self._items[i]
                    element = self._path.path_elements[i]
                    pos = self._element_position_for_index(i)
                    item.set_center(QPointF(pos[0], pos[1]))
                    if i < len(self._handoff_visualizers) and self._handoff_visualizers[i]:
                        self._handoff_visualizers[i].set_center(QPointF(pos[0], pos[1]))
                    if kind in ("rotation", "waypoint"):
                        angle = self._element_rotation(element)
                    else:
                        angle = self._angle_for_translation_index(i)
                    if kind == "event_trigger":
                        item.set_angle_radians(self._event_trigger_angle_for_index(i))
                    else:
                        item.set_angle_radians(angle)
                    if handle:
                        handle.set_angle(angle)
                        handle.sync_to_angle()
                except Exception:
                    continue
        finally:
            self._suppress_live_events = False
        self._update_connecting_lines()
        self._rebuild_protrusion_trigger_schedule()
        self._rebuild_element_protrusion_visibility_map()
        self._apply_protrusion_visual_to_all_items()
        if self._path:
            self._reproject_rotation_items_in_scene()
        self.request_simulation_rebuild()

    def refresh_rotations_from_model(self):
        if self._path is None or not self._items:
            return
        max_index = len(self._path.path_elements) - 1
        for i, (kind, item, handle) in enumerate(self._items):
            if i > max_index:
                break
            if kind != "rotation":
                continue
            try:
                element = self._path.path_elements[i]
                pos = self._element_position_for_index(i)
                item.set_center(QPointF(pos[0], pos[1]))
                if handle:
                    angle = self._element_rotation(element)
                    item.set_angle_radians(angle)
                    handle.set_angle(angle)
                    handle.sync_to_angle()
            except Exception:
                continue
        self._update_connecting_lines()
        self.request_simulation_rebuild()

    def select_index(self, index: int, center_on_item: bool = True):
        if index is None or index < 0 or index >= len(self._items):
            return
        try:
            _, item, _ = self._items[index]
        except Exception:
            return
        if item is None:
            return
        try:
            if item.scene() is None:
                return
        except Exception:
            return
        # Avoid deselect/reselect churn when the requested item is already selected.
        # This breaks the canvas <-> sidebar feedback loop that can cause visible flicker.
        try:
            selected_items = self.graphics_scene.selectedItems()
        except Exception:
            selected_items = []
        if len(selected_items) == 1 and selected_items[0] is item:
            if center_on_item:
                QTimer.singleShot(0, lambda it=item: self._safe_center_on(it))
            return
        try:
            self.graphics_scene.clearSelection()
            item.setSelected(True)
            if center_on_item:
                QTimer.singleShot(0, lambda it=item: self._safe_center_on(it))
        except Exception:
            return

    def clear_selection(self) -> bool:
        try:
            had_selection = bool(self.graphics_scene.selectedItems())
        except Exception:
            had_selection = False
        try:
            self.graphics_scene.clearSelection()
        except Exception:
            pass
        return had_selection

    def _ensure_pressed_item_selected(self, index: int) -> None:
        """Ensure the pressed item is selected without redundant churn."""
        if index is None or index < 0 or index >= len(self._items):
            return
        try:
            _, item, _ = self._items[index]
        except Exception:
            return
        if item is None:
            return
        try:
            if item.scene() is None:
                return
        except Exception:
            return
        try:
            selected_items = self.graphics_scene.selectedItems()
        except Exception:
            selected_items = []
        if len(selected_items) == 1 and selected_items[0] is item:
            return
        try:
            self.graphics_scene.clearSelection()
            item.setSelected(True)
        except Exception:
            pass

    def is_index_actively_pressed(self, index: int) -> bool:
        try:
            return self._active_press_index == int(index)
        except Exception:
            return False

    def _on_scene_selection_changed(self):
        try:
            selected_items = set(self.graphics_scene.selectedItems())
        except Exception:
            selected_items = set()
        has_selection = bool(selected_items)
        self._set_selection_pulse_active(has_selection)
        self._apply_selection_layering(selected_items)
        dirty_items = set(self._last_selected_items)
        dirty_items.update(selected_items)
        self._update_selected_item_visuals(dirty_items)
        self._last_selected_items = selected_items

    def _set_selection_pulse_active(self, active: bool):
        if active:
            if not self._selection_pulse_timer.isActive():
                self._selection_pulse_phase = 0.0
                self._selection_pulse_alpha = SELECTION_PULSE_MAX_ALPHA
                self._selection_pulse_width_scale = 1.0
                self._selection_pulse_timer.start()
            return
        if self._selection_pulse_timer.isActive():
            self._selection_pulse_timer.stop()
        self._selection_pulse_phase = 0.0
        self._selection_pulse_alpha = SELECTION_PULSE_MAX_ALPHA
        self._selection_pulse_width_scale = 1.0

    def _on_selection_pulse_tick(self):
        try:
            self._selection_pulse_phase = (
                self._selection_pulse_phase + SELECTION_PULSE_STEP_RAD
            ) % (2.0 * math.pi)
            pulse_wave = (math.sin(self._selection_pulse_phase) + 1.0) * 0.5
            self._selection_pulse_alpha = (
                SELECTION_PULSE_MIN_ALPHA
                + (SELECTION_PULSE_MAX_ALPHA - SELECTION_PULSE_MIN_ALPHA) * pulse_wave
            )
            self._selection_pulse_width_scale = (
                SELECTION_PULSE_WIDTH_SCALE_MIN
                + (SELECTION_PULSE_WIDTH_SCALE_MAX - SELECTION_PULSE_WIDTH_SCALE_MIN) * pulse_wave
            )
        except Exception:
            return
        self._update_selected_item_visuals()

    def _apply_selection_layering(self, selected_items: Optional[set[QGraphicsItem]] = None):
        if selected_items is None:
            try:
                selected_items = set(self.graphics_scene.selectedItems())
            except Exception:
                selected_items = set()
        for kind, item, handle in self._items:
            try:
                base_z = 12 if kind == "event_trigger" else 10
                item.setZValue(24 if item in selected_items else base_z)
            except Exception:
                continue
            if handle:
                handle_z = 25 if item in selected_items else 12
                for sub in handle.scene_items():
                    try:
                        sub.setZValue(handle_z)
                    except Exception:
                        continue

    def _update_selected_item_visuals(self, items: Optional[set[QGraphicsItem]] = None):
        if items is None:
            try:
                items = set(self.graphics_scene.selectedItems())
            except Exception:
                return
        for item in items:
            try:
                if item is None or item.scene() is None:
                    continue
                item.update()
            except Exception:
                continue

    def get_selection_pulse_alpha(self) -> float:
        try:
            return float(self._selection_pulse_alpha)
        except Exception:
            return float(SELECTION_PULSE_MAX_ALPHA)

    def get_selection_pulse_width_scale(self) -> float:
        try:
            return float(self._selection_pulse_width_scale)
        except Exception:
            return 1.0

    def _safe_center_on(self, item: QGraphicsItem):
        try:
            if item and item.scene():
                self.centerOn(item)
        except Exception:
            pass

    # ------------- Resize / Show -------------
    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self._fit_to_scene)
        QTimer.singleShot(0, self.transport.position)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self._fit_to_scene)
        QTimer.singleShot(0, self.transport.position)

    def _fit_to_scene(self):
        if self._is_fitting:
            return
        self._is_fitting = True
        try:
            rect = self.graphics_scene.sceneRect()
            if rect.width() > 0 and rect.height() > 0:
                try:
                    self.fitInView(rect, Qt.KeepAspectRatio)
                    if abs(self._zoom_factor - 1.0) > 1e-6:
                        self.scale(self._zoom_factor, self._zoom_factor)
                    # After any fit/scale, reposition transport overlay to viewport corner
                    QTimer.singleShot(0, self.transport.position)
                except Exception:
                    pass
        finally:
            self._is_fitting = False

    # ------------- Item build -------------
    def _clear_scene_items(self):
        self._set_selection_pulse_active(False)
        self._last_selected_items.clear()
        for _, item, handle in self._items:
            self.graphics_scene.removeItem(item)
            if handle:
                [self.graphics_scene.removeItem(sub) for sub in handle.scene_items()]
        for line in self._connect_lines:
            self.graphics_scene.removeItem(line)
        for viz in self._handoff_visualizers:
            if viz:
                self.graphics_scene.removeItem(viz)
        self._items.clear()
        self._connect_lines.clear()
        self._handoff_visualizers.clear()

    def _rebuild_items(self):
        self._clear_scene_items()
        if self._path is None:
            return
        for i, element in enumerate(self._path.path_elements):
            pos = self._element_position_for_index(i)
            if isinstance(element, TranslationTarget):
                kind = "translation"
                item = CircleElementItem(
                    self,
                    QPointF(*pos),
                    i,
                    filled_color=QColor("#3aa3ff"),
                    outline_color=QColor("#3aa3ff"),
                    dashed_outline=False,
                    triangle_color=None,
                )
                rotation_handle = None
                item.set_angle_radians(self._angle_for_translation_index(i))
                handoff_visualizer = None
                radius = getattr(element, "intermediate_handoff_radius_meters", None)
                if (
                    (radius is None or radius <= 0)
                    and hasattr(self, "_project_manager")
                    and self._project_manager
                ):
                    try:
                        default_radius = self._project_manager.get_default_optional_value(
                            "intermediate_handoff_radius_meters"
                        )
                        if default_radius and default_radius > 0:
                            radius = default_radius
                    except Exception:
                        pass
                # Skip creating visualizer for the last element
                if radius and radius > 0 and i != len(self._path.path_elements) - 1:
                    hv = HandoffRadiusVisualizer(self, QPointF(*pos), radius)
                    self.graphics_scene.addItem(hv)
                    handoff_visualizer = hv
            elif isinstance(element, RotationTarget):
                kind = "rotation"
                item = RectElementItem(
                    self,
                    QPointF(*pos),
                    i,
                    filled_color=None,
                    outline_color=QColor("#50c878"),
                    dashed_outline=True,
                    triangle_color=QColor("#50c878"),
                )
                rotation_handle = RotationHandle(
                    self, item, HANDLE_DISTANCE_M, HANDLE_RADIUS_M, QColor("#50c878")
                )
                ang = self._element_rotation(element)
                item.set_angle_radians(ang)
                rotation_handle.set_angle(ang)
                rotation_handle.sync_to_angle()
                self._apply_protrusion_visual_to_item(kind, item)
                handoff_visualizer = None
            elif isinstance(element, EventTrigger):
                kind = "event_trigger"
                length_m = max(0.2, float(self.robot_width_m) * 0.6)
                item = EventTriggerItem(
                    self,
                    QPointF(*pos),
                    i,
                    length_m=length_m,
                    color=QColor("#ffd54d"),
                )
                item.set_angle_radians(self._event_trigger_angle_for_index(i))
                rotation_handle = None
                handoff_visualizer = None
            elif isinstance(element, Waypoint):
                kind = "waypoint"
                item = RectElementItem(
                    self,
                    QPointF(*pos),
                    i,
                    filled_color=None,
                    outline_color=QColor("#ff7f3a"),
                    dashed_outline=False,
                    triangle_color=QColor("#ff7f3a"),
                )
                rotation_handle = RotationHandle(
                    self, item, HANDLE_DISTANCE_M, HANDLE_RADIUS_M, QColor("#ff7f3a")
                )
                ang = self._element_rotation(element)
                item.set_angle_radians(ang)
                rotation_handle.set_angle(ang)
                rotation_handle.sync_to_angle()
                self._apply_protrusion_visual_to_item(kind, item)
                handoff_visualizer = None
                radius = getattr(
                    element.translation_target, "intermediate_handoff_radius_meters", None
                )
                if (
                    (radius is None or radius <= 0)
                    and hasattr(self, "_project_manager")
                    and self._project_manager
                ):
                    try:
                        default_radius = self._project_manager.get_default_optional_value(
                            "intermediate_handoff_radius_meters"
                        )
                        if default_radius and default_radius > 0:
                            radius = default_radius
                    except Exception:
                        pass
                # Skip creating visualizer for the last element
                if radius and radius > 0 and i != len(self._path.path_elements) - 1:
                    hv = HandoffRadiusVisualizer(self, QPointF(*pos), radius)
                    self.graphics_scene.addItem(hv)
                    handoff_visualizer = hv
            else:
                continue
            try:
                self.graphics_scene.addItem(item)
            except Exception:
                continue
            if rotation_handle:
                for sub in rotation_handle.scene_items():
                    try:
                        self.graphics_scene.addItem(sub)
                    except Exception:
                        continue
            self._items.append((kind, item, rotation_handle))
            self._handoff_visualizers.append(handoff_visualizer)
        self._build_connecting_lines()
        self._apply_selection_layering(set())

    def _apply_protrusion_visual_to_item(self, kind: str, item):
        if kind not in ("rotation", "waypoint"):
            return
        try:
            index_in_model = int(getattr(item, "index_in_model", -1))
            shown = self._element_protrusion_visibility_by_index.get(
                index_in_model, self._default_protrusion_visible()
            )
            item.set_protrusion_visual(
                enabled=self.protrusion_enabled,
                shown=shown,
                side=self.protrusion_side,
                distance_m=self.protrusion_distance_m,
            )
        except Exception:
            pass

    def _apply_protrusion_visual_to_all_items(self):
        if not self._items:
            return
        for kind, item, _ in self._items:
            self._apply_protrusion_visual_to_item(kind, item)

    def _set_protrusion_visible(self, visible: bool):
        self._protrusion_current_visible = bool(visible)
        self._update_sim_robot_dimensions()

    def _update_sim_robot_dimensions(self):
        if self._sim_robot_item is None:
            return
        side = self._normalize_protrusion_side(self.protrusion_side)
        side_valid = side in ("front", "back", "left", "right")
        protrusion_visible = bool(
            self.protrusion_enabled
            and self._protrusion_current_visible
            and self.protrusion_distance_m > 0.0
            and side_valid
        )
        try:
            self._sim_robot_item.set_dimensions(
                self.robot_length_m,
                self.robot_width_m,
                protrusion_visible=protrusion_visible,
                protrusion_distance_m=self.protrusion_distance_m,
                protrusion_side=side,
            )
        except Exception:
            pass

    def _protrusion_visible_at_s(self, s_value: float) -> bool:
        if not self.protrusion_enabled:
            return False
        visible = self._default_protrusion_visible()
        for event_s, action in self._protrusion_trigger_schedule:
            if s_value + 1e-6 >= event_s:
                visible = bool(action)
            else:
                break
        return bool(visible)

    def _neighbor_anchor_indices(self, index: int) -> tuple[Optional[int], Optional[int]]:
        if self._path is None:
            return None, None
        prev_anchor_idx = None
        for j in range(index - 1, -1, -1):
            e = self._path.path_elements[j]
            if isinstance(e, (TranslationTarget, Waypoint)):
                prev_anchor_idx = j
                break
        next_anchor_idx = None
        for j in range(index + 1, len(self._path.path_elements)):
            e = self._path.path_elements[j]
            if isinstance(e, (TranslationTarget, Waypoint)):
                next_anchor_idx = j
                break
        return prev_anchor_idx, next_anchor_idx

    def _rebuild_element_protrusion_visibility_map(self):
        self._element_protrusion_visibility_by_index = {}
        if self._path is None:
            return

        _segments, anchor_s_by_path_index, _total_len = self._build_anchor_progress_geometry()
        if not anchor_s_by_path_index:
            return

        for idx, element in enumerate(self._path.path_elements):
            if isinstance(element, Waypoint):
                s_value = float(anchor_s_by_path_index.get(idx, 0.0))
                self._element_protrusion_visibility_by_index[idx] = self._protrusion_visible_at_s(
                    s_value
                )
            elif isinstance(element, RotationTarget):
                prev_anchor_idx, next_anchor_idx = self._neighbor_anchor_indices(idx)
                if (
                    prev_anchor_idx is None
                    or next_anchor_idx is None
                    or prev_anchor_idx not in anchor_s_by_path_index
                    or next_anchor_idx not in anchor_s_by_path_index
                ):
                    self._element_protrusion_visibility_by_index[idx] = (
                        self._protrusion_visible_at_s(0.0)
                    )
                    continue
                s0 = float(anchor_s_by_path_index[prev_anchor_idx])
                s1 = float(anchor_s_by_path_index[next_anchor_idx])
                span = max(0.0, s1 - s0)
                t_ratio = max(0.0, min(1.0, float(getattr(element, "t_ratio", 0.0))))
                s_value = s0 + (span * t_ratio)
                self._element_protrusion_visibility_by_index[idx] = self._protrusion_visible_at_s(
                    s_value
                )

    # ------------- Geometry helpers -------------
    def _angle_for_translation_index(self, index: int) -> float:
        if self._path is None or index <= 0:
            return 0.0
        for i in range(index - 1, -1, -1):
            el = self._path.path_elements[i]
            if isinstance(el, (RotationTarget, Waypoint)):
                return self._element_rotation(el)
        return 0.0

    def _element_position_for_index(self, index: int) -> Tuple[float, float]:
        if self._path is None or index < 0 or index >= len(self._path.path_elements):
            return 0.0, 0.0
        element = self._path.path_elements[index]
        if isinstance(element, (TranslationTarget, Waypoint)):
            return _get_translation_position(element)
        if isinstance(element, (RotationTarget, EventTrigger)):
            prev_pos, next_pos = self._neighbor_positions_model(index)
            if prev_pos is None or next_pos is None:
                return 0.0, 0.0
            ax, ay = prev_pos
            bx, by = next_pos
            t = float(getattr(element, "t_ratio", 0.0))
            t = max(0.0, min(1.0, t))
            return ax + t * (bx - ax), ay + t * (by - ay)
        return 0.0, 0.0

    def _neighbor_positions_model(
        self, index: int
    ) -> Tuple[Optional[Tuple[float, float]], Optional[Tuple[float, float]]]:
        if self._path is None:
            return None, None
        prev_pos = None
        for i in range(index - 1, -1, -1):
            e = self._path.path_elements[i]
            if isinstance(e, (TranslationTarget, Waypoint)):
                prev_pos = _get_translation_position(e)
                break
        next_pos = None
        for i in range(index + 1, len(self._path.path_elements)):
            e = self._path.path_elements[i]
            if isinstance(e, (TranslationTarget, Waypoint)):
                next_pos = _get_translation_position(e)
                break
        return prev_pos, next_pos

    def _element_rotation(self, element: PathElement) -> float:
        if isinstance(element, RotationTarget):
            return float(element.rotation_radians)
        if isinstance(element, Waypoint):
            return float(element.rotation_target.rotation_radians)
        return 0.0

    def _event_trigger_angle_for_index(self, index: int) -> float:
        if self._path is None:
            return 0.0
        prev_pos, next_pos = self._neighbor_positions_model(index)
        if prev_pos is None or next_pos is None:
            return 0.0
        ax, ay = prev_pos
        bx, by = next_pos
        angle = math.atan2(by - ay, bx - ax)
        return angle + (math.pi / 2.0)

    def _build_connecting_lines(self):
        self._connect_lines = []
        if not self._items:
            return
        for i in range(len(self._items) - 1):
            try:
                _, a, _ = self._items[i]
                _, b, _ = self._items[i + 1]
                if a and b:
                    line = QGraphicsLineItem(a.pos().x(), a.pos().y(), b.pos().x(), b.pos().y())
                    line.setPen(QPen(QColor("#cccccc"), CONNECT_LINE_THICKNESS_M))
                    line.setZValue(5)
                    self.graphics_scene.addItem(line)
                    self._connect_lines.append(line)
            except Exception:
                continue

    def _update_connecting_lines(self):
        if not self._items or not self._connect_lines:
            return
        for i in range(len(self._connect_lines)):
            if i >= len(self._items) - 1:
                break
            try:
                _, a, _ = self._items[i]
                _, b, _ = self._items[i + 1]
                if a and b:
                    self._connect_lines[i].setLine(
                        a.pos().x(), a.pos().y(), b.pos().x(), b.pos().y()
                    )
            except Exception:
                continue

    # -------- Live interactions --------
    def _on_item_live_moved(self, index: int, x_m: float, y_m: float):
        if index < 0 or index >= len(self._items):
            return
        if self._active_press_index == index:
            try:
                _, active_item, _ = self._items[index]
                if self._press_start_scene_pos is None:
                    self._press_moved = True
                else:
                    dx = float(active_item.pos().x() - self._press_start_scene_pos.x())
                    dy = float(active_item.pos().y() - self._press_start_scene_pos.y())
                    if (dx * dx + dy * dy) > float(self._press_move_epsilon_sq):
                        self._press_moved = True
            except Exception:
                self._press_moved = True
        self._update_connecting_lines()
        try:
            kind, _, handle = self._items[index]
            if handle:
                handle.sync_to_angle()
        except Exception:
            return
        if index < len(self._handoff_visualizers) and self._handoff_visualizers[index]:
            try:
                self._handoff_visualizers[index].set_center(QPointF(x_m, y_m))
            except Exception:
                pass
        self.elementMoved.emit(index, x_m, y_m)
        if kind in ("translation", "waypoint"):
            self._reproject_rotation_items_in_scene()
        self.request_simulation_rebuild()

    def _on_item_live_rotated(self, index: int, angle_radians: float):
        if index < 0 or index >= len(self._items):
            return
        if self._active_press_index == index:
            try:
                if self._press_start_angle_radians is None:
                    self._press_rotated = True
                elif abs(float(angle_radians) - float(self._press_start_angle_radians)) > float(
                    self._press_rotation_epsilon_rad
                ):
                    self._press_rotated = True
            except Exception:
                self._press_rotated = True
        try:
            kind, item, handle = self._items[index]
            if kind in ("rotation", "waypoint"):
                item.set_angle_radians(angle_radians)
                if handle:
                    handle.set_angle(angle_radians)
        except Exception:
            return
        self.elementRotated.emit(index, angle_radians)
        for j, (k, it, _) in enumerate(self._items):
            if k == "translation":
                try:
                    it.set_angle_radians(self._angle_for_translation_index(j))
                except Exception:
                    continue
        self.request_simulation_rebuild()

    def _on_item_clicked(self, index: int):
        self.elementSelected.emit(index)

    # -------- Coordinate conversion --------
    def _scene_from_model(self, x_m: float, y_m: float) -> QPointF:
        """Convert model coordinates to scene coordinates.

        For 2026 field, adds FIELD_OFFSET_M (0.5m) to account for image margin.
        """
        return QPointF(x_m + self._field_offset, FIELD_WIDTH_METERS - y_m - self._field_offset)

    def _model_from_scene(self, x_s: float, y_s: float) -> Tuple[float, float]:
        """Convert scene coordinates to model coordinates.

        For 2026 field, subtracts FIELD_OFFSET_M (0.5m) to account for image margin.
        """
        return float(x_s - self._field_offset), float(FIELD_WIDTH_METERS - y_s - self._field_offset)

    def _robot_half_extents(self) -> Tuple[float, float]:
        return max(0.0, self.robot_length_m * 0.5), max(0.0, self.robot_width_m * 0.5)

    def _clamp_scene_coords(self, x_s: float, y_s: float) -> Tuple[float, float]:
        return max(0.0, min(x_s, FIELD_LENGTH_METERS)), max(0.0, min(y_s, FIELD_WIDTH_METERS))

    def _clamp_scene_coords_with_robot_perimeter(
        self, x_s: float, y_s: float
    ) -> Tuple[float, float]:
        hx, hy = self._robot_half_extents()
        return (
            max(hx, min(x_s, FIELD_LENGTH_METERS - hx)),
            max(hy, min(y_s, FIELD_WIDTH_METERS - hy)),
        )

    def _constrain_scene_coords_for_index(
        self, index: int, x_s: float, y_s: float
    ) -> Tuple[float, float]:
        x_s, y_s = self._clamp_scene_coords(x_s, y_s)
        if index < 0 or index >= len(self._items):
            return x_s, y_s
        try:
            kind, _, _ = self._items[index]
        except Exception:
            return x_s, y_s
        if kind not in ("rotation", "event_trigger"):
            return self._clamp_scene_coords_with_robot_perimeter(x_s, y_s)
        prev_pos, next_pos = self._find_neighbor_item_positions(index)
        if prev_pos is None or next_pos is None:
            return x_s, y_s
        ax, ay = prev_pos
        bx, by = next_pos
        dx = bx - ax
        dy = by - ay
        denom = dx * dx + dy * dy
        if denom <= 0:
            return x_s, y_s
        t = ((x_s - ax) * dx + (y_s - ay) * dy) / denom
        t = max(0.0, min(1.0, t))
        proj_x = ax + t * dx
        proj_y = ay + t * dy
        return self._clamp_scene_coords_with_robot_perimeter(proj_x, proj_y)

    def _find_neighbor_item_positions(
        self, index: int
    ) -> Tuple[Optional[Tuple[float, float]], Optional[Tuple[float, float]]]:
        prev_pos = None
        for i in range(index - 1, -1, -1):
            try:
                kind, item, _ = self._items[i]
                if kind in ("translation", "waypoint"):
                    prev_pos = (item.pos().x(), item.pos().y())
                    break
            except Exception:
                continue
        next_pos = None
        for i in range(index + 1, len(self._items)):
            try:
                kind, item, _ = self._items[i]
                if kind in ("translation", "waypoint"):
                    next_pos = (item.pos().x(), item.pos().y())
                    break
            except Exception:
                continue
        return prev_pos, next_pos

    def _reproject_rotation_items_in_scene(self):
        self._suppress_live_events = True
        try:
            for i, (kind, item, handle) in enumerate(self._items):
                if kind not in ("rotation", "event_trigger"):
                    continue
                prev_pos, next_pos = self._find_neighbor_item_positions(i)
                if prev_pos is None or next_pos is None:
                    continue
                ax, ay = prev_pos
                bx, by = next_pos
                t = 0.0
                try:
                    if self._path and i < len(self._path.path_elements):
                        rt = self._path.path_elements[i]
                        if isinstance(rt, (RotationTarget, EventTrigger)):
                            t = float(getattr(rt, "t_ratio", 0.0))
                except Exception:
                    t = 0.0
                t = max(0.0, min(1.0, t))
                proj_x = ax + t * (bx - ax)
                proj_y = ay + t * (by - ay)
                try:
                    item.setPos(proj_x, proj_y)
                except Exception:
                    continue
                if kind == "event_trigger":
                    try:
                        item.set_angle_radians(self._event_trigger_angle_for_index(i))
                    except Exception:
                        pass
                if handle:
                    handle.sync_to_angle()
            self._update_connecting_lines()
        finally:
            self._suppress_live_events = False

    def _compute_rotation_t_cache(self) -> dict[int, float]:
        t_by_index = {}
        for i, (kind, item, _) in enumerate(self._items):
            if kind not in ("rotation", "event_trigger"):
                continue
            prev_pos, next_pos = self._find_neighbor_item_positions(i)
            if prev_pos is None or next_pos is None:
                continue
            ax, ay = prev_pos
            bx, by = next_pos
            dx = bx - ax
            dy = by - ay
            denom = dx * dx + dy * dy
            if denom <= 0:
                continue
            rx, ry = item.pos().x(), item.pos().y()
            t = ((rx - ax) * dx + (ry - ay) * dy) / denom
            t = max(0.0, min(1.0, t))
            t_by_index[i] = float(t)
        return t_by_index

    def _on_item_pressed(self, index: int):
        if index < 0 or index >= len(self._items):
            return
        self._ensure_pressed_item_selected(index)
        self._active_press_index = int(index)
        self._press_moved = False
        self._press_rotated = False
        self._press_start_scene_pos = None
        self._press_start_angle_radians = None
        try:
            _, item, _ = self._items[index]
            self._press_start_scene_pos = QPointF(item.pos())
            angle = getattr(item, "_angle_radians", None)
            if angle is not None:
                self._press_start_angle_radians = float(angle)
        except Exception:
            pass
        kind, _, _ = self._items[index]
        if kind in ("translation", "waypoint"):
            self._anchor_drag_in_progress = True
            self._rotation_t_cache = self._compute_rotation_t_cache()

    def _on_item_released(self, index: int):
        is_active_release = self._active_press_index == index
        did_transform = bool(is_active_release and (self._press_moved or self._press_rotated))
        if self._anchor_drag_in_progress:
            try:
                if did_transform:
                    for i, (kind, item, _) in enumerate(self._items):
                        if kind not in ("rotation", "event_trigger"):
                            continue
                        mx, my = self._model_from_scene(item.pos().x(), item.pos().y())
                        self.elementMoved.emit(i, mx, my)
            finally:
                self._anchor_drag_in_progress = False
                self._rotation_t_cache = None
        if did_transform:
            self.elementDragFinished.emit(index)
        if is_active_release:
            self._active_press_index = None
            self._press_moved = False
            self._press_rotated = False
            self._press_start_scene_pos = None
            self._press_start_angle_radians = None
        self.request_simulation_rebuild()

    def _build_anchor_progress_geometry(
        self,
    ) -> tuple[
        list[tuple[float, float, float, float, float, float, float]], dict[int, float], float
    ]:
        if self._path is None:
            return [], {}, 0.0

        anchors: list[tuple[int, float, float]] = []
        for idx, element in enumerate(self._path.path_elements):
            if isinstance(element, TranslationTarget):
                anchors.append((idx, float(element.x_meters), float(element.y_meters)))
            elif isinstance(element, Waypoint):
                anchors.append(
                    (
                        idx,
                        float(element.translation_target.x_meters),
                        float(element.translation_target.y_meters),
                    )
                )

        if len(anchors) < 2:
            anchor_map = {anchors[0][0]: 0.0} if anchors else {}
            return [], anchor_map, 0.0

        segments: list[tuple[float, float, float, float, float, float, float]] = []
        anchor_s_by_path_index: dict[int, float] = {}
        cumulative = 0.0
        anchor_s_by_path_index[anchors[0][0]] = 0.0
        for i in range(len(anchors) - 1):
            idx_a, ax, ay = anchors[i]
            idx_b, bx, by = anchors[i + 1]
            dx = bx - ax
            dy = by - ay
            denom = dx * dx + dy * dy
            seg_len = math.hypot(dx, dy)
            start_s = cumulative
            cumulative += seg_len
            anchor_s_by_path_index[idx_a] = start_s
            anchor_s_by_path_index[idx_b] = cumulative
            segments.append((ax, ay, dx, dy, denom, start_s, seg_len))

        return segments, anchor_s_by_path_index, cumulative

    def _project_point_to_global_s(
        self,
        x_m: float,
        y_m: float,
        segments: list[tuple[float, float, float, float, float, float, float]],
        fallback_s: float,
    ) -> float:
        if not segments:
            return float(fallback_s)

        best_s = float(fallback_s)
        best_dist2: Optional[float] = None
        for ax, ay, dx, dy, denom, start_s, seg_len in segments:
            t = 0.0
            if denom > 1e-12:
                t = ((x_m - ax) * dx + (y_m - ay) * dy) / denom
                t = max(0.0, min(1.0, t))
            proj_x = ax + t * dx
            proj_y = ay + t * dy
            dist2 = (x_m - proj_x) ** 2 + (y_m - proj_y) ** 2
            s_val = start_s + (seg_len * t)
            if best_dist2 is None or dist2 < best_dist2:
                best_dist2 = dist2
                best_s = s_val
        return float(best_s)

    def _rebuild_protrusion_trigger_schedule(self):
        self._protrusion_trigger_schedule = []
        if self._path is None or not self.protrusion_enabled:
            return

        show_keys = set(self.protrusion_show_on_event_keys)
        hide_keys = set(self.protrusion_hide_on_event_keys)
        if not show_keys and not hide_keys:
            return

        _segments, anchor_s_by_path_index, _total_len = self._build_anchor_progress_geometry()
        if not anchor_s_by_path_index:
            return

        trigger_schedule: list[tuple[float, int, bool]] = []
        for idx, element in enumerate(self._path.path_elements):
            if not isinstance(element, EventTrigger):
                continue
            key = str(getattr(element, "lib_key", "")).strip()
            if not key:
                continue

            action: Optional[bool] = None
            if key in show_keys:
                action = True
            elif key in hide_keys:
                action = False
            if action is None:
                continue

            prev_anchor_idx, next_anchor_idx = self._neighbor_anchor_indices(idx)
            if prev_anchor_idx is None or next_anchor_idx is None:
                continue
            if (
                prev_anchor_idx not in anchor_s_by_path_index
                or next_anchor_idx not in anchor_s_by_path_index
            ):
                continue

            s0 = float(anchor_s_by_path_index[prev_anchor_idx])
            s1 = float(anchor_s_by_path_index[next_anchor_idx])
            span = max(0.0, s1 - s0)
            t_ratio = max(0.0, min(1.0, float(getattr(element, "t_ratio", 0.0))))
            trigger_schedule.append((s0 + span * t_ratio, idx, action))

        trigger_schedule.sort(key=lambda x: (x[0], x[1]))
        self._protrusion_trigger_schedule = [
            (s_val, action) for s_val, _idx, action in trigger_schedule
        ]

    def _global_s_for_time(self, t_s: float, key_hint: Optional[float] = None) -> float:
        if not self._sim_global_s_by_time:
            return 0.0
        if key_hint is not None and key_hint in self._sim_global_s_by_time:
            return float(self._sim_global_s_by_time.get(key_hint, 0.0))
        if not self._sim_times_sorted:
            return 0.0
        selected = self._sim_times_sorted[0]
        for tk in self._sim_times_sorted:
            if tk <= t_s:
                selected = tk
            else:
                break
        return float(self._sim_global_s_by_time.get(selected, 0.0))

    def _update_protrusion_visibility_for_time(self, t_s: float, key_hint: Optional[float] = None):
        if not self.protrusion_enabled:
            self._set_protrusion_visible(False)
            return

        visible = self._default_protrusion_visible()
        if self._protrusion_trigger_schedule and self._sim_global_s_by_time:
            s_now = self._global_s_for_time(t_s, key_hint=key_hint)
            for event_s, action in self._protrusion_trigger_schedule:
                if s_now + 1e-6 >= event_s:
                    visible = bool(action)
                else:
                    break
        self._set_protrusion_visible(visible)

    # -------- Simulation API (subset) --------
    def request_simulation_rebuild(self):
        try:
            self._sim_debounce.start()
        except Exception:
            pass

    def _ensure_sim_robot_item(self):
        try:
            if self._sim_robot_item:
                return
            item = RobotSimItem(self)
            self.graphics_scene.addItem(item)
            self._sim_robot_item = item
            item.setVisible(False)
            try:
                self._update_sim_robot_dimensions()
            except Exception:
                pass
        except Exception:
            pass

    def _update_sim_robot_visibility(self):
        try:
            if self._sim_robot_item is None:
                return
            if not self._sim_times_sorted:
                self._sim_robot_item.setVisible(False)
                return
            if self._sim_timer.isActive():
                self._sim_robot_item.setVisible(True)
                return
            if self._sim_current_time_s <= 1e-6:
                self._sim_robot_item.setVisible(False)
            else:
                self._sim_robot_item.setVisible(True)
        except Exception:
            pass

    def _clear_trail(self):
        try:
            for line in self._trail_lines:
                if line.scene():
                    self.graphics_scene.removeItem(line)
            self._trail_lines.clear()
            self._trail_points.clear()
        except Exception:
            pass

    def _setup_trail(self, trail_points: List[Tuple[float, float]]):
        try:
            self._clear_trail()
            self._trail_points = trail_points.copy()
            orange_pen = QPen(QColor(255, 165, 0), 0.05)
            orange_pen.setCapStyle(Qt.RoundCap)
            for i in range(len(self._trail_points) - 1):
                line = QGraphicsLineItem()
                line.setPen(orange_pen)
                line.setZValue(14)
                line.setVisible(False)
                self.graphics_scene.addItem(line)
                self._trail_lines.append(line)
        except Exception:
            pass

    def _update_trail_visibility(self, current_index: int):
        try:
            if not self._trail_points or not self._trail_lines:
                return
            for i, line in enumerate(self._trail_lines):
                if i < current_index and i < len(self._trail_points) - 1:
                    x1, y1 = self._trail_points[i]
                    x2, y2 = self._trail_points[i + 1]
                    p1 = self._scene_from_model(x1, y1)
                    p2 = self._scene_from_model(x2, y2)
                    line.setLine(p1.x(), p1.y(), p2.x(), p2.y())
                    line.setVisible(True)
                else:
                    line.setVisible(False)
        except Exception:
            pass

    # Transport control callbacks (public subset kept for TransportControls wiring)
    def _toggle_play_pause(self):
        try:
            if self._sim_timer.isActive():
                self._sim_timer.stop()
                if self.transport.btn:
                    self.transport.btn.setText("▶")
                self._update_sim_robot_visibility()
            else:
                if not self._sim_times_sorted:
                    return
                if self._sim_current_time_s >= self._sim_total_time_s:
                    self._sim_current_time_s = 0.0
                    self._seek_to_time(0.0)
                    if self.transport.slider:
                        self.transport.slider.blockSignals(True)
                        self.transport.slider.setValue(0)
                        self.transport.slider.blockSignals(False)
                    self._update_trail_visibility(0)
                self._sim_timer.start()
                if self.transport.btn:
                    self.transport.btn.setText("⏸")
                self._update_sim_robot_visibility()
        except Exception:
            pass

    def _on_slider_changed(self, value: int):
        try:
            self._sim_current_time_s = float(value) / 10000.0
            self._seek_to_time(self._sim_current_time_s)
            self._update_sim_robot_visibility()
        except Exception:
            pass

    def _on_slider_pressed(self):
        try:
            if self._sim_timer.isActive():
                self._sim_timer.stop()
            if self.transport.btn:
                self.transport.btn.setText("▶")
            self._update_sim_robot_visibility()
        except Exception:
            pass

    def _on_slider_released(self):
        pass

    def _seek_to_time(self, t_s: float):
        try:
            if not self._sim_times_sorted or not self._sim_poses_by_time:
                return
            key_index = 0
            key = 0.0
            for i, tk in enumerate(self._sim_times_sorted):
                if tk <= t_s:
                    key = tk
                    key_index = i
                else:
                    break
            x, y, th = self._sim_poses_by_time.get(
                key, self._sim_poses_by_time[self._sim_times_sorted[0]]
            )
            self._set_sim_robot_pose(x, y, th)
            self._update_trail_visibility(key_index)
            self._update_protrusion_visibility_for_time(t_s, key_hint=key)
            if self.transport.label:
                self.transport.label.setText(f"{t_s:.2f} / {self._sim_total_time_s:.2f} s")
            self._update_sim_robot_visibility()
        except Exception:
            pass

    def _on_sim_tick(self):
        try:
            if not self._sim_times_sorted:
                self._sim_timer.stop()
                if self.transport.btn:
                    self.transport.btn.setText("▶")
                    return
            self._sim_current_time_s += 0.02
            if self._sim_current_time_s >= self._sim_total_time_s:
                self._sim_current_time_s = self._sim_total_time_s
                self._sim_timer.stop()
                if self.transport.btn:
                    self.transport.btn.setText("▶")
            if self.transport.slider:
                self.transport.slider.blockSignals(True)
                self.transport.slider.setValue(int(round(self._sim_current_time_s * 10000.0)))
                self.transport.slider.blockSignals(False)
            self._seek_to_time(self._sim_current_time_s)
        except Exception:
            pass

    def _set_sim_robot_pose(self, x_m: float, y_m: float, theta_rad: float):
        try:
            if not self._sim_robot_item:
                return
            self._sim_robot_item.set_center(QPointF(x_m, y_m))
            self._sim_robot_item.set_angle_radians(theta_rad)
        except Exception:
            pass

    def _rebuild_simulation_now(self):
        try:
            if self._path is None:
                self._sim_result = None
                self._sim_poses_by_time = {}
                self._sim_times_sorted = []
                self._sim_total_time_s = 0.0
                self._sim_current_time_s = 0.0
                self._sim_global_s_by_time = {}
                if self._sim_robot_item:
                    self._sim_robot_item.setVisible(False)
                self._clear_trail()
                if self.transport.slider:
                    self.transport.slider.setRange(0, 0)
                if self.transport.label:
                    self.transport.label.setText("0.00 / 0.00 s")
                self._rebuild_protrusion_trigger_schedule()
                self._set_protrusion_visible(self._default_protrusion_visible())
                return
            cfg = {}
            try:
                if hasattr(self, "_project_manager") and self._project_manager:
                    if hasattr(self._project_manager, "config_as_dict"):
                        cfg = self._project_manager.config_as_dict()
                    else:
                        cfg = dict(getattr(self._project_manager, "config", {}) or {})
            except Exception:
                cfg = {}
            result = simulate_path(self._path, cfg, dt_s=0.001)
            self._sim_result = result
            self._sim_poses_by_time = result.poses_by_time
            self._sim_times_sorted = result.times_sorted
            self._sim_total_time_s = float(result.total_time_s)
            self._sim_current_time_s = 0.0
            segments, _anchor_map, total_len = self._build_anchor_progress_geometry()
            self._sim_global_s_by_time = {}
            if segments and self._sim_times_sorted:
                last_s = 0.0
                for tk in self._sim_times_sorted:
                    pose = self._sim_poses_by_time.get(tk)
                    if pose is None:
                        continue
                    x_m, y_m, _ = pose
                    s_val = self._project_point_to_global_s(
                        float(x_m), float(y_m), segments, fallback_s=last_s
                    )
                    s_val = min(float(total_len), max(last_s, s_val))
                    self._sim_global_s_by_time[tk] = s_val
                    last_s = s_val
            self._rebuild_protrusion_trigger_schedule()
            if self.transport.slider:
                self.transport.slider.blockSignals(True)
                self.transport.slider.setRange(0, int(round(self._sim_total_time_s * 10000.0)))
                self.transport.slider.setValue(0)
                self.transport.slider.blockSignals(False)
            if self.transport.label:
                self.transport.label.setText(f"0.00 / {self._sim_total_time_s:.2f} s")
            if self._sim_robot_item and self._sim_times_sorted:
                t0 = self._sim_times_sorted[0]
                x, y, th = self._sim_poses_by_time.get(t0, (0.0, 0.0, 0.0))
                self._set_sim_robot_pose(x, y, th)
                self._update_protrusion_visibility_for_time(0.0, key_hint=t0)
                self._update_sim_robot_visibility()
            else:
                self._set_protrusion_visible(self._default_protrusion_visible())
            if hasattr(result, "trail_points") and result.trail_points:
                self._setup_trail(result.trail_points)
            else:
                self._clear_trail()
        except Exception:
            pass

    # -------- Keyboard & mouse --------
    def keyPressEvent(self, event):
        try:
            if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
                self.deleteSelectedRequested.emit()
                event.accept()
                return
            if event.key() == Qt.Key_Space:
                self._toggle_play_pause()
                event.accept()
                return
        except Exception:
            pass
        super().keyPressEvent(event)

    def wheelEvent(self, event):
        try:
            delta_y = 0
            delta = event.angleDelta()
            if delta:
                delta_y = int(delta.y())
            if delta_y == 0:
                pdelta = event.pixelDelta()
                if pdelta:
                    delta_y = int(pdelta.y())
            if delta_y == 0:
                return super().wheelEvent(event)
            zoom_step = ZOOM_STEP_FACTOR
            factor = zoom_step if delta_y > 0 else (1.0 / zoom_step)
            new_zoom = self._zoom_factor * factor
            if new_zoom < self._min_zoom:
                if self._zoom_factor <= self._min_zoom:
                    return
                factor = self._min_zoom / self._zoom_factor
                self._zoom_factor = self._min_zoom
            elif new_zoom > self._max_zoom:
                if self._zoom_factor >= self._max_zoom:
                    return
                factor = self._max_zoom / self._zoom_factor
                self._zoom_factor = self._max_zoom
            else:
                self._zoom_factor = new_zoom
            self.scale(factor, factor)
            event.accept()
            # Keep transport overlay anchored after zooming
            try:
                self.transport.position()
            except Exception:
                pass
        except Exception:
            try:
                super().wheelEvent(event)
            except Exception:
                pass

    def _on_rotation_handle_released(self, index: int):
        try:
            self.rotationDragFinished.emit(int(index))
        except Exception:
            pass

    def _should_start_pan(self, pos) -> bool:
        """Return True if a left-click at view position pos should start panning.
        Pan on empty/background areas; avoid panning on interactive items or the
        transport overlay.
        """
        try:
            item = self.itemAt(pos)
            if item is None:
                return True
            # Avoid panning when clicking the transport overlay
            from PySide6.QtWidgets import QGraphicsPixmapItem, QGraphicsProxyWidget

            if isinstance(item, QGraphicsProxyWidget):
                return False
            # Allow panning when clicking the background pixmap
            if isinstance(item, QGraphicsPixmapItem):
                return True
            # Otherwise, assume it's an interactive scene item; don't pan
            return False
        except Exception:
            return False

    def mousePressEvent(self, event):
        try:
            # Use left-click to pan on empty/background (not on interactive items)
            if event.button() == Qt.LeftButton and self._should_start_pan(event.pos()):
                self.clear_selection()
                try:
                    self.selectionCleared.emit()
                except Exception:
                    pass
                self._is_panning = True
                self._pan_start = event.pos()
                self.viewport().setCursor(Qt.ClosedHandCursor)
                event.accept()
                return
        except Exception:
            pass
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        try:
            if self._is_panning and self._pan_start is not None:
                delta = event.pos() - self._pan_start
                hbar = self.horizontalScrollBar()
                vbar = self.verticalScrollBar()
                hbar.setValue(hbar.value() - delta.x())
                vbar.setValue(vbar.value() - delta.y())
                self._pan_start = event.pos()
                event.accept()
                return
        except Exception:
            pass
        super().mouseMoveEvent(event)

        # Reposition overlay when the view scrolls due to any movement
        try:
            self.transport.position()
        except Exception:
            pass

    def scrollContentsBy(self, dx: int, dy: int):
        # Called for any programmatic or inertial scroll; keep overlay anchored
        try:
            super().scrollContentsBy(dx, dy)
        finally:
            try:
                self.transport.position()
            except Exception:
                pass

    def mouseReleaseEvent(self, event):
        try:
            if event.button() == Qt.LeftButton and self._is_panning:
                self._is_panning = False
                self._pan_start = None
                self.viewport().setCursor(Qt.ArrowCursor)
                event.accept()
                return
        except Exception:
            pass
        super().mouseReleaseEvent(event)

    # ---- Constraint overlay (kept simplified pass-through) ----
    def clear_constraint_range_overlay(self):
        # Restore any temporarily modified item styles
        try:
            for it, (old_pen, old_brush) in list(self._range_overlay_saved_item_styles.items()):
                try:
                    if hasattr(it, "setPen") and old_pen is not None:
                        it.setPen(old_pen)
                    if hasattr(it, "setBrush") and old_brush is not None:
                        it.setBrush(old_brush)
                except Exception:
                    pass
        finally:
            self._range_overlay_saved_item_styles.clear()

        if not self._range_overlay_lines:
            return
        for line in self._range_overlay_lines:
            if line and line.scene():
                self.graphics_scene.removeItem(line)
        self._range_overlay_lines.clear()

    def show_constraint_range_overlay(self, key: str, start_ordinal: int, end_ordinal: int):
        # Simplified placeholder: leaving original logic in monolithic file for now.
        # Future work: Extract overlay-building logic similarly.
        self.clear_constraint_range_overlay()
        if self._path is None or not self._items:
            return
        # Choose anchor domain based on constraint key (translation vs rotation)
        rotation_keys = ("max_velocity_deg_per_sec", "max_acceleration_deg_per_sec2")
        is_rotation_domain = key in rotation_keys
        if is_rotation_domain:
            anchors = [
                (i, it)
                for i, (k, it, _h) in enumerate(self._items)
                if k in ("rotation", "waypoint")
            ]
        else:
            anchors = [
                (i, it)
                for i, (k, it, _h) in enumerate(self._items)
                if k in ("translation", "waypoint")
            ]
        if not anchors:
            return
        lo = int(min(start_ordinal, end_ordinal))
        hi = int(max(start_ordinal, end_ordinal))
        green_pen = QPen(QColor("#15c915"), CONNECT_LINE_THICKNESS_M)
        green_pen.setCapStyle(Qt.RoundCap)
        if lo < 1:
            lo = 1
        if hi > len(anchors):
            hi = len(anchors)
        # If left handle is at the far left, tint the appropriate first element while previewing
        if lo == 1:
            try:
                first_item = None
                if is_rotation_domain:
                    for kind, it, _h in self._items:
                        if kind in ("rotation", "waypoint"):
                            first_item = it
                            break
                else:
                    if self._items and len(self._items) > 0 and len(self._items[0]) > 1:
                        first_item = self._items[0][1]
                # Save current styles once per overlay
                if first_item is not None:
                    try:
                        old_pen = first_item.pen() if hasattr(first_item, "pen") else None
                    except Exception:
                        old_pen = None
                    try:
                        old_brush = first_item.brush() if hasattr(first_item, "brush") else None
                    except Exception:
                        old_brush = None
                    if first_item not in self._range_overlay_saved_item_styles:
                        self._range_overlay_saved_item_styles[first_item] = (old_pen, old_brush)
                    # Apply green highlight
                    try:
                        hl_pen = QPen(
                            QColor("#15c915"),
                            (
                                old_pen.widthF()
                                if hasattr(old_pen, "widthF")
                                else CONNECT_LINE_THICKNESS_M
                            ),
                        )
                        hl_pen.setCapStyle(Qt.SquareCap)
                        hl_pen.setJoinStyle(Qt.MiterJoin)
                        first_item.setPen(hl_pen)
                    except Exception:
                        pass
                    try:
                        # Only fill if the item is a circle (translation) or already filled
                        from .items.elements import CircleElementItem

                        if isinstance(first_item, CircleElementItem) or (
                            hasattr(first_item, "brush")
                            and first_item.brush()
                            and first_item.brush().style() != Qt.NoBrush
                        ):
                            first_item.setBrush(QBrush(QColor("#15c915")))
                    except Exception:
                        pass
            except Exception:
                pass
        if is_rotation_domain:
            # Map rotation-domain ordinals to global path indices and draw along every segment in between
            rot_indices = [
                idx for idx, (k, _it, _h) in enumerate(self._items) if k in ("rotation", "waypoint")
            ]
            if not rot_indices:
                return
            lo = max(1, min(int(lo), len(rot_indices)))
            hi = max(1, min(int(hi), len(rot_indices)))
            if lo > hi:
                lo, hi = hi, lo
            start_anchor_i = lo - 1
            if lo > 1:
                start_anchor_i = (
                    lo - 2
                )  # include the segment leading into the first selected anchor
            end_anchor_i = hi - 1
            start_global = rot_indices[start_anchor_i]
            end_global = rot_indices[end_anchor_i]
            if start_global > end_global:
                start_global, end_global = end_global, start_global
            # Draw contiguous segments along the path between these global indices
            for j in range(start_global, end_global):
                if j < 0 or j + 1 >= len(self._items):
                    break
                try:
                    _k1, a, _h1 = self._items[j]
                    _k2, b, _h2 = self._items[j + 1]
                    if a is None or b is None:
                        continue
                    line = QGraphicsLineItem(a.pos().x(), a.pos().y(), b.pos().x(), b.pos().y())
                    line.setPen(green_pen)
                    line.setZValue(25)
                    self.graphics_scene.addItem(line)
                    self._range_overlay_lines.append(line)
                except Exception:
                    continue
            return
        # Translation-domain anchors: mirror rotation logic by mapping ordinal anchors to global indices
        tr_indices = [
            idx for idx, (k, _it, _h) in enumerate(self._items) if k in ("translation", "waypoint")
        ]
        if not tr_indices:
            return
        lo = max(1, min(int(lo), len(tr_indices)))
        hi = max(1, min(int(hi), len(tr_indices)))
        if lo > hi:
            lo, hi = hi, lo
        start_anchor_i = lo - 1
        if lo > 1:
            start_anchor_i = lo - 2  # include the segment leading into the first selected anchor
        end_anchor_i = hi - 1
        start_global = tr_indices[start_anchor_i]
        end_global = tr_indices[end_anchor_i]
        if start_global > end_global:
            start_global, end_global = end_global, start_global
        for j in range(start_global, end_global):
            if j < 0 or j + 1 >= len(self._items):
                break
            try:
                _k1, a, _h1 = self._items[j]
                _k2, b, _h2 = self._items[j + 1]
                if a is None or b is None:
                    continue
                line = QGraphicsLineItem(a.pos().x(), a.pos().y(), b.pos().x(), b.pos().y())
                line.setPen(green_pen)
                line.setZValue(25)
                self.graphics_scene.addItem(line)
                self._range_overlay_lines.append(line)
            except Exception:
                continue
