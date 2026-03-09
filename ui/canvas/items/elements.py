# mypy: ignore-errors
"""Graphics item subclasses for path elements (circle/rect + rotation handle + handoff radius)."""

from __future__ import annotations
import math
from typing import Optional, List, TYPE_CHECKING

from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsRectItem,
    QGraphicsPolygonItem,
    QGraphicsLineItem,
)
from PySide6.QtGui import QBrush, QColor, QPen, QPolygonF
from PySide6.QtCore import QPointF, QTimer

from ui.qt_compat import Qt, QGraphicsItem

from ..constants import (
    ELEMENT_CIRCLE_RADIUS_M,
    TRIANGLE_REL_SIZE,
    OUTLINE_THIN_M,
    OUTLINE_THICK_M,
    OUTLINE_EDGE_PEN,
    HANDLE_LINK_THICKNESS_M,
    HANDLE_DISTANCE_M,
    HANDLE_RADIUS_M,
    HANDOFF_RADIUS_PEN,
    SELECTION_ACCENT_COLOR,
    SELECTION_CIRCLE_RING_WIDTH_M,
    SELECTION_CIRCLE_RING_PADDING_M,
    SELECTION_RECT_OUTLINE_WIDTH_M,
    SELECTION_RECT_OUTLINE_PADDING_M,
    SELECTION_EVENT_LINE_WIDTH_M,
    SELECTION_PULSE_WIDTH_SCALE_MAX,
)
from models.path_model import Waypoint, TranslationTarget

if TYPE_CHECKING:
    from ui.canvas.view import CanvasView


def _highlight_margin(padding: float, width: float) -> float:
    return padding + 0.5 * width * SELECTION_PULSE_WIDTH_SCALE_MAX


def _apply_rotation_dash_style(pen: QPen) -> QPen:
    try:
        # Frequent dash pattern with visible gaps; use FlatCap so gaps remain open
        pen.setStyle(Qt.CustomDashLine)
        pen.setDashPattern([1, 0.5])
    except Exception:
        pen.setStyle(Qt.DashLine)
    pen.setCapStyle(Qt.FlatCap)
    # Slightly thin the dashed stroke so it doesn't read as solid
    try:
        current_w = float(pen.widthF())
        pen.setWidthF(max(0.02, current_w * 0.8))
    except Exception:
        pass
    pen.setJoinStyle(Qt.MiterJoin)
    pen.setCosmetic(False)
    return pen


class CircleElementItem(QGraphicsEllipseItem):
    def __init__(
        self,
        canvas_view: "CanvasView",
        center_m: QPointF,
        index_in_model: int,
        *,
        filled_color: Optional[QColor],
        outline_color: Optional[QColor],
        dashed_outline: bool,
        triangle_color: Optional[QColor],
    ):
        super().__init__()
        self.canvas_view = canvas_view
        self.index_in_model = index_in_model
        self.setRect(
            -ELEMENT_CIRCLE_RADIUS_M,
            -ELEMENT_CIRCLE_RADIUS_M,
            ELEMENT_CIRCLE_RADIUS_M * 2,
            ELEMENT_CIRCLE_RADIUS_M * 2,
        )
        self.setPos(self.canvas_view._scene_from_model(center_m.x(), center_m.y()))
        thickness = OUTLINE_THICK_M if (outline_color and not dashed_outline) else OUTLINE_THIN_M
        pen = QPen(outline_color or QColor("#000"), thickness if outline_color else 0.0)
        if dashed_outline:
            pen.setStyle(Qt.DashLine)
        self.setPen(pen)
        self.setBrush(QBrush(filled_color) if filled_color else Qt.NoBrush)
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setZValue(10)
        self.triangle_item: Optional[QGraphicsPolygonItem] = None
        if triangle_color is not None:
            self.triangle_item = QGraphicsPolygonItem(self)
            self._build_triangle(triangle_color)
        self._angle_radians: float = 0.0

    def _build_triangle(self, color: QColor):
        if not self.triangle_item:
            return
        base_size = ELEMENT_CIRCLE_RADIUS_M * 2 * TRIANGLE_REL_SIZE
        half_base = base_size * 0.5
        height = base_size
        points = [
            QPointF(height / 2.0, 0.0),
            QPointF(-height / 2.0, half_base),
            QPointF(-height / 2.0, -half_base),
        ]
        self.triangle_item.setPolygon(QPolygonF(points))
        self.triangle_item.setBrush(QBrush(color))
        self.triangle_item.setPen(OUTLINE_EDGE_PEN)
        self.triangle_item.setZValue(self.zValue() + 1)

    def set_center(self, center_m: QPointF):
        self.setPos(self.canvas_view._scene_from_model(center_m.x(), center_m.y()))

    def set_angle_radians(self, radians: float):
        self._angle_radians = radians
        self.setRotation(math.degrees(-radians))

    def boundingRect(self):
        base_rect = super().boundingRect()
        margin = _highlight_margin(SELECTION_CIRCLE_RING_PADDING_M, SELECTION_CIRCLE_RING_WIDTH_M)
        return base_rect.adjusted(-margin, -margin, margin, margin)

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value):
        if change == QGraphicsItem.ItemPositionChange:
            new_pos: QPointF = value
            try:
                cx, cy = self.canvas_view._constrain_scene_coords_for_index(
                    self.index_in_model, new_pos.x(), new_pos.y()
                )
                return QPointF(cx, cy)
            except Exception:
                return value
        elif change == QGraphicsItem.ItemPositionHasChanged:
            if not getattr(self.canvas_view, "_suppress_live_events", False):
                try:
                    x_m, y_m = self.canvas_view._model_from_scene(self.pos().x(), self.pos().y())
                    self.canvas_view._on_item_live_moved(self.index_in_model, x_m, y_m)
                except Exception:
                    pass
        return super().itemChange(change, value)

    def mousePressEvent(self, event):
        try:
            self.canvas_view._on_item_pressed(self.index_in_model)
        except Exception:
            pass
        super().mousePressEvent(event)
        try:
            QTimer.singleShot(
                0, lambda idx=self.index_in_model: self.canvas_view._on_item_clicked(idx)
            )
        except Exception:
            pass

    def mouseReleaseEvent(self, event):
        try:
            self.canvas_view._on_item_released(self.index_in_model)
        except Exception:
            pass
        super().mouseReleaseEvent(event)

    def paint(self, painter, option, widget=None):  # noqa: D401
        super().paint(painter, option, widget)
        if not (
            self.isSelected() or self.canvas_view.is_index_actively_pressed(self.index_in_model)
        ):
            return
        try:
            painter.save()
            pulse_alpha = self.canvas_view.get_selection_pulse_alpha()
            pulse_scale = self.canvas_view.get_selection_pulse_width_scale()
            selection_color = QColor(SELECTION_ACCENT_COLOR)
            selection_color.setAlphaF(pulse_alpha)
            selection_pen = QPen(
                selection_color, max(0.01, SELECTION_CIRCLE_RING_WIDTH_M * pulse_scale)
            )
            selection_pen.setCapStyle(Qt.RoundCap)
            selection_pen.setJoinStyle(Qt.RoundJoin)
            selection_pen.setCosmetic(False)
            ring_rect = self.rect().adjusted(
                -SELECTION_CIRCLE_RING_PADDING_M,
                -SELECTION_CIRCLE_RING_PADDING_M,
                SELECTION_CIRCLE_RING_PADDING_M,
                SELECTION_CIRCLE_RING_PADDING_M,
            )
            painter.setPen(selection_pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(ring_rect)
        except Exception:
            pass
        finally:
            try:
                painter.restore()
            except Exception:
                pass


class RectElementItem(QGraphicsRectItem):
    def __init__(
        self,
        canvas_view: "CanvasView",
        center_m: QPointF,
        index_in_model: int,
        *,
        filled_color: Optional[QColor],
        outline_color: Optional[QColor],
        dashed_outline: bool,
        triangle_color: QColor,
    ):
        super().__init__()
        self.canvas_view = canvas_view
        self.index_in_model = index_in_model
        rw = getattr(self.canvas_view, "robot_length_m", 0.60)
        rh = getattr(self.canvas_view, "robot_width_m", 0.60)
        self._outline_color = outline_color or QColor("#000")
        self._protrusion_enabled: bool = False
        self._protrusion_shown: bool = False
        self._protrusion_side: str = "none"
        self._protrusion_distance_m: float = 0.0
        self._protrusion_lines: List[QGraphicsLineItem] = []
        pen_width_m = OUTLINE_THICK_M if (outline_color and not dashed_outline) else OUTLINE_THIN_M
        inset = (pen_width_m if outline_color else 0.0) * 0.5
        x_min = -(rw / 2.0)
        x_max = rw / 2.0
        y_min = -(rh / 2.0)
        y_max = rh / 2.0
        self.setRect(
            x_min + inset, y_min + inset, (x_max - x_min) - inset * 2, (y_max - y_min) - inset * 2
        )
        self.setPos(self.canvas_view._scene_from_model(center_m.x(), center_m.y()))
        pen = QPen(self._outline_color, pen_width_m if outline_color else 0.0)
        if dashed_outline:
            pen = _apply_rotation_dash_style(pen)
        else:
            pen.setCapStyle(Qt.SquareCap)
            pen.setJoinStyle(Qt.MiterJoin)
            pen.setCosmetic(False)
        self.setPen(pen)
        if filled_color and not isinstance(
            self.canvas_view._path.path_elements[index_in_model], Waypoint
        ):
            self.setBrush(QBrush(filled_color))
        else:
            self.setBrush(Qt.NoBrush)
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setZValue(10)
        self.triangle_item = QGraphicsPolygonItem(self)
        self._build_triangle(triangle_color)
        # Tiny squares at corners to avoid voids with dashed outline
        self._corner_squares: List[QGraphicsRectItem] = []
        if dashed_outline:
            try:
                self._create_corner_squares(self._outline_color, float(pen.widthF()))
            except Exception:
                self._corner_squares = []
        self._angle_radians: float = 0.0
        self._refresh_protrusion_item()

    def _build_triangle(self, color: QColor):
        r = self.rect()
        rw = float(r.width())
        rh = float(r.height())
        base_size = min(rw, rh) * TRIANGLE_REL_SIZE
        half_base = base_size * 0.5
        height = base_size
        points = [
            QPointF(height / 2.0, 0.0),
            QPointF(-height / 2.0, half_base),
            QPointF(-height / 2.0, -half_base),
        ]
        self.triangle_item.setPolygon(QPolygonF(points))
        from models.path_model import Waypoint  # local import to avoid cycle

        if isinstance(self.canvas_view._path.path_elements[self.index_in_model], Waypoint):
            self.triangle_item.setBrush(Qt.NoBrush)
            p = QPen(color, OUTLINE_THICK_M)
            p.setJoinStyle(Qt.MiterJoin)
            p.setCapStyle(Qt.SquareCap)
            p.setCosmetic(False)
            self.triangle_item.setPen(p)
        else:
            self.triangle_item.setBrush(QBrush(color))
            self.triangle_item.setPen(OUTLINE_EDGE_PEN)
        self.triangle_item.setZValue(self.zValue() + 1)

    def set_center(self, center_m: QPointF):
        self.setPos(self.canvas_view._scene_from_model(center_m.x(), center_m.y()))

    def set_angle_radians(self, radians: float):
        self._angle_radians = radians
        self.setRotation(math.degrees(-radians))

    def boundingRect(self):
        base_rect = super().boundingRect()
        margin = _highlight_margin(SELECTION_RECT_OUTLINE_PADDING_M, SELECTION_RECT_OUTLINE_WIDTH_M)
        return base_rect.adjusted(-margin, -margin, margin, margin)

    def set_protrusion_visual(self, *, enabled: bool, shown: bool, side: str, distance_m: float):
        self._protrusion_enabled = bool(enabled)
        self._protrusion_shown = bool(shown)
        self._protrusion_side = str(side or "none").strip().lower()
        self._protrusion_distance_m = max(0.0, float(distance_m))
        self._refresh_protrusion_item()

    def _refresh_protrusion_item(self):
        valid_side = self._protrusion_side in ("front", "back", "left", "right")
        should_draw = (
            self._protrusion_enabled
            and self._protrusion_shown
            and valid_side
            and self._protrusion_distance_m > 0.0
        )

        if not should_draw:
            for line in self._protrusion_lines:
                line.setVisible(False)
            return

        while len(self._protrusion_lines) < 3:
            line = QGraphicsLineItem(self)
            line.setZValue(self.zValue() + 0.7)
            self._protrusion_lines.append(line)

        pen = QPen(self._outline_color, OUTLINE_THIN_M)
        pen = _apply_rotation_dash_style(pen)
        for line in self._protrusion_lines:
            line.setPen(pen)

        r = self.rect()
        rect_pen_width = float(self.pen().widthF()) if self.pen() is not None else OUTLINE_THIN_M
        protrusion_pen_width = float(pen.widthF())

        left = float(r.left())
        right = float(r.right())
        top = float(r.top())
        bottom = float(r.bottom())
        outer_left = left - (rect_pen_width * 0.5)
        outer_right = right + (rect_pen_width * 0.5)
        outer_top = top - (rect_pen_width * 0.5)
        outer_bottom = bottom + (rect_pen_width * 0.5)
        line_half = protrusion_pen_width * 0.5
        edge_offset = self._protrusion_distance_m
        top_y = outer_top + line_half
        bottom_y = outer_bottom - line_half
        left_x = outer_left + line_half
        right_x = outer_right - line_half

        side = self._protrusion_side
        if side == "front":
            x = outer_right + edge_offset + line_half
            self._protrusion_lines[0].setLine(x, top_y, x, bottom_y)
            self._protrusion_lines[1].setLine(outer_right, top_y, x, top_y)
            self._protrusion_lines[2].setLine(outer_right, bottom_y, x, bottom_y)
        elif side == "back":
            x = outer_left - edge_offset - line_half
            self._protrusion_lines[0].setLine(x, top_y, x, bottom_y)
            self._protrusion_lines[1].setLine(outer_left, top_y, x, top_y)
            self._protrusion_lines[2].setLine(outer_left, bottom_y, x, bottom_y)
        elif side == "left":
            # Robot-left is negative local Y after model->scene conversion.
            y = outer_top - edge_offset - line_half
            self._protrusion_lines[0].setLine(left_x, y, right_x, y)
            self._protrusion_lines[1].setLine(left_x, outer_top, left_x, y)
            self._protrusion_lines[2].setLine(right_x, outer_top, right_x, y)
        else:  # right
            # Robot-right is positive local Y after model->scene conversion.
            y = outer_bottom + edge_offset + line_half
            self._protrusion_lines[0].setLine(left_x, y, right_x, y)
            self._protrusion_lines[1].setLine(left_x, outer_bottom, left_x, y)
            self._protrusion_lines[2].setLine(right_x, outer_bottom, right_x, y)

        for line in self._protrusion_lines:
            line.setVisible(True)

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value):
        if change == QGraphicsItem.ItemPositionChange:
            new_pos: QPointF = value
            try:
                cx, cy = self.canvas_view._constrain_scene_coords_for_index(
                    self.index_in_model, new_pos.x(), new_pos.y()
                )
                return QPointF(cx, cy)
            except Exception:
                return value
        elif change == QGraphicsItem.ItemPositionHasChanged:
            if not getattr(self.canvas_view, "_suppress_live_events", False):
                try:
                    x_m, y_m = self.canvas_view._model_from_scene(self.pos().x(), self.pos().y())
                    self.canvas_view._on_item_live_moved(self.index_in_model, x_m, y_m)
                except Exception:
                    pass
        return super().itemChange(change, value)

    def mousePressEvent(self, event):
        try:
            self.canvas_view._on_item_pressed(self.index_in_model)
        except Exception:
            pass
        super().mousePressEvent(event)
        try:
            QTimer.singleShot(
                0, lambda idx=self.index_in_model: self.canvas_view._on_item_clicked(idx)
            )
        except Exception:
            pass

    def mouseReleaseEvent(self, event):
        try:
            self.canvas_view._on_item_released(self.index_in_model)
        except Exception:
            pass
        super().mouseReleaseEvent(event)

    def paint(self, painter, option, widget=None):  # noqa: D401
        try:
            painter.setRenderHint(painter.Antialiasing, False)  # type: ignore
            painter.setRenderHint(painter.HighQualityAntialiasing, False)  # type: ignore
        except Exception:
            pass
        super().paint(painter, option, widget)
        if not (
            self.isSelected() or self.canvas_view.is_index_actively_pressed(self.index_in_model)
        ):
            return
        try:
            painter.save()
            pulse_alpha = self.canvas_view.get_selection_pulse_alpha()
            pulse_scale = self.canvas_view.get_selection_pulse_width_scale()
            selection_color = QColor(SELECTION_ACCENT_COLOR)
            selection_color.setAlphaF(pulse_alpha)
            selection_pen = QPen(
                selection_color, max(0.01, SELECTION_RECT_OUTLINE_WIDTH_M * pulse_scale)
            )
            selection_pen.setCapStyle(Qt.SquareCap)
            selection_pen.setJoinStyle(Qt.MiterJoin)
            selection_pen.setCosmetic(False)
            selection_rect = self.rect().adjusted(
                -SELECTION_RECT_OUTLINE_PADDING_M,
                -SELECTION_RECT_OUTLINE_PADDING_M,
                SELECTION_RECT_OUTLINE_PADDING_M,
                SELECTION_RECT_OUTLINE_PADDING_M,
            )
            painter.setPen(selection_pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(selection_rect)
        except Exception:
            pass
        finally:
            try:
                painter.restore()
            except Exception:
                pass

    def _create_corner_caps(self, color: QColor, pen_width_m: float, subtle: bool = False):
        # Deprecated: kept for reference
        for it in getattr(self, "_corner_caps", []) or []:
            try:
                if it.scene():
                    it.scene().removeItem(it)
            except Exception:
                pass
        self._corner_caps = []
        r = self.rect()
        left = r.left()
        right = r.right()
        top = r.top()
        bottom = r.bottom()
        # Make very short caps; if subtle, reduce width and length
        cap_len = max(0.04, (pen_width_m * (1.5 if subtle else 3.0)))
        pen = QPen(color, (pen_width_m * 0.6 if subtle else pen_width_m))
        # Flat caps keep caps from extending beyond endpoints
        pen.setCapStyle(Qt.FlatCap)
        pen.setJoinStyle(Qt.MiterJoin)
        pen.setCosmetic(False)

        def _add_line(x1, y1, x2, y2):
            ln = QGraphicsLineItem(self)
            ln.setLine(x1, y1, x2, y2)
            ln.setPen(pen)
            ln.setZValue(self.zValue() + 0.5)
            self._corner_caps.append(ln)

        # Top-left
        _add_line(left, top, left + cap_len, top)
        _add_line(left, top, left, top + cap_len)
        # Top-right
        _add_line(right - cap_len, top, right, top)
        _add_line(right, top, right, top + cap_len)
        # Bottom-left
        _add_line(left, bottom, left + cap_len, bottom)
        _add_line(left, bottom - cap_len, left, bottom)
        # Bottom-right
        _add_line(right - cap_len, bottom, right, bottom)
        _add_line(right, bottom - cap_len, right, bottom)

    def _create_corner_squares(self, color: QColor, pen_width_m: float):
        # Clear any existing squares
        for it in getattr(self, "_corner_squares", []) or []:
            try:
                if it.scene():
                    it.scene().removeItem(it)
            except Exception:
                pass
        self._corner_squares = []
        r = self.rect()
        left = r.left()
        right = r.right()
        top = r.top()
        bottom = r.bottom()
        size = max(0.01, float(pen_width_m))
        half = size * 0.5

        def _add_square(cx, cy):
            sq = QGraphicsRectItem(self)
            sq.setRect(cx - half, cy - half, size, size)
            sq.setBrush(QBrush(color))
            sq.setPen(Qt.NoPen)
            sq.setZValue(self.zValue() + 0.6)
            self._corner_squares.append(sq)

        _add_square(left, top)
        _add_square(right, top)
        _add_square(left, bottom)
        _add_square(right, bottom)


class EventTriggerItem(QGraphicsLineItem):
    def __init__(
        self,
        canvas_view: "CanvasView",
        center_m: QPointF,
        index_in_model: int,
        *,
        length_m: float,
        color: QColor,
    ):
        super().__init__()
        self.canvas_view = canvas_view
        self.index_in_model = index_in_model
        self._angle_radians: float = 0.0
        self._length_m = float(length_m)
        half = self._length_m * 0.5
        self.setLine(-half, 0.0, half, 0.0)
        self.setPos(self.canvas_view._scene_from_model(center_m.x(), center_m.y()))
        pen = QPen(color, OUTLINE_THIN_M)
        pen.setStyle(Qt.SolidLine)
        pen.setCapStyle(Qt.FlatCap)
        pen.setJoinStyle(Qt.MiterJoin)
        pen.setCosmetic(False)
        self.setPen(pen)
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setZValue(12)

    def set_center(self, center_m: QPointF):
        self.setPos(self.canvas_view._scene_from_model(center_m.x(), center_m.y()))

    def set_angle_radians(self, radians: float):
        self._angle_radians = radians
        self.setRotation(math.degrees(-radians))

    def set_length(self, length_m: float):
        self._length_m = float(length_m)
        half = self._length_m * 0.5
        self.setLine(-half, 0.0, half, 0.0)

    def boundingRect(self):
        base_rect = super().boundingRect()
        margin = _highlight_margin(0.0, SELECTION_EVENT_LINE_WIDTH_M)
        return base_rect.adjusted(-margin, -margin, margin, margin)

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value):
        if change == QGraphicsItem.ItemPositionChange:
            new_pos: QPointF = value
            try:
                cx, cy = self.canvas_view._constrain_scene_coords_for_index(
                    self.index_in_model, new_pos.x(), new_pos.y()
                )
                return QPointF(cx, cy)
            except Exception:
                return value
        elif change == QGraphicsItem.ItemPositionHasChanged:
            if not getattr(self.canvas_view, "_suppress_live_events", False):
                try:
                    x_m, y_m = self.canvas_view._model_from_scene(self.pos().x(), self.pos().y())
                    self.canvas_view._on_item_live_moved(self.index_in_model, x_m, y_m)
                except Exception:
                    pass
        return super().itemChange(change, value)

    def mousePressEvent(self, event):
        try:
            self.canvas_view._on_item_pressed(self.index_in_model)
        except Exception:
            pass
        super().mousePressEvent(event)
        try:
            QTimer.singleShot(
                0, lambda idx=self.index_in_model: self.canvas_view._on_item_clicked(idx)
            )
        except Exception:
            pass

    def mouseReleaseEvent(self, event):
        try:
            self.canvas_view._on_item_released(self.index_in_model)
        except Exception:
            pass
        super().mouseReleaseEvent(event)

    def paint(self, painter, option, widget=None):  # noqa: D401
        super().paint(painter, option, widget)
        if not (
            self.isSelected() or self.canvas_view.is_index_actively_pressed(self.index_in_model)
        ):
            return
        try:
            painter.save()
            pulse_alpha = self.canvas_view.get_selection_pulse_alpha()
            pulse_scale = self.canvas_view.get_selection_pulse_width_scale()
            selection_color = QColor(SELECTION_ACCENT_COLOR)
            selection_color.setAlphaF(pulse_alpha)
            selection_pen = QPen(
                selection_color, max(0.01, SELECTION_EVENT_LINE_WIDTH_M * pulse_scale)
            )
            selection_pen.setStyle(Qt.SolidLine)
            selection_pen.setCapStyle(Qt.RoundCap)
            selection_pen.setJoinStyle(Qt.RoundJoin)
            selection_pen.setCosmetic(False)
            painter.setPen(selection_pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawLine(self.line())
        except Exception:
            pass
        finally:
            try:
                painter.restore()
            except Exception:
                pass


class RotationHandle(QGraphicsEllipseItem):
    def __init__(
        self,
        canvas_view: "CanvasView",
        parent_center_item: RectElementItem,
        handle_distance_m: float,
        handle_radius_m: float,
        color: QColor,
    ):
        super().__init__()
        self.canvas_view = canvas_view
        self.center_item = parent_center_item
        self.handle_distance_m = handle_distance_m
        self.handle_radius_m = handle_radius_m
        self._dragging: bool = False
        self._syncing: bool = False
        # Make the handle invisible but still interactive: fully transparent fill, no pen
        self.setBrush(QBrush(QColor(0, 0, 0, 0)))
        self.setPen(Qt.NoPen)
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, False)
        self.setZValue(12)
        self._angle_radians: float = 0.0
        # Remove the visual link line; keep an instance for legacy calls but make it non-drawing
        self.link_line = QGraphicsLineItem()
        self.link_line.setPen(Qt.NoPen)
        self.link_line.setZValue(11)
        self.setRect(-handle_radius_m, -handle_radius_m, handle_radius_m * 2, handle_radius_m * 2)
        self.sync_to_angle()

    def scene_items(self) -> List[QGraphicsItem]:
        # Only the (invisible) handle participates in the scene; the link line is omitted
        return [self]

    def set_angle(self, radians: float):
        self._angle_radians = radians
        self.sync_to_angle()

    def sync_to_angle(self):
        self._syncing = True
        try:
            cx, cy = self.center_item.pos().x(), self.center_item.pos().y()
            angle_scene = -self._angle_radians
            # Place handle at the midpoint of the front (forward-facing) edge of the rectangle
            front_offset_m = float(self.center_item.rect().width()) * 0.5
            hx = cx + math.cos(angle_scene) * front_offset_m
            hy = cy + math.sin(angle_scene) * front_offset_m
            self.setPos(QPointF(hx, hy))
            # No link line to update (kept for legacy but non-drawing)
        finally:
            self._syncing = False

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value):
        if change == QGraphicsItem.ItemPositionChange:
            new_center: QPointF = value
            try:
                cx = self.center_item.pos().x()
                cy = self.center_item.pos().y()
                dx = new_center.x() - cx
                dy = new_center.y() - cy
                angle_scene = math.atan2(dy, dx)
                # Constrain movement to the front-edge midpoint radius
                front_offset_m = float(self.center_item.rect().width()) * 0.5
                hx = cx + math.cos(angle_scene) * front_offset_m
                hy = cy + math.sin(angle_scene) * front_offset_m
                angle_model = -angle_scene
                self._angle_radians = angle_model
                if not self._syncing and self._dragging:
                    self.canvas_view._on_item_live_rotated(
                        self.center_item.index_in_model, angle_model
                    )
                return QPointF(hx, hy)
            except Exception:
                return value
        return super().itemChange(change, value)

    def mousePressEvent(self, event):
        try:
            self.canvas_view.graphics_scene.clearSelection()
            self.center_item.setSelected(True)
        except Exception:
            pass
        self.center_item.setFlag(QGraphicsItem.ItemIsMovable, False)
        self._dragging = True
        super().mousePressEvent(event)
        try:
            QTimer.singleShot(
                0,
                lambda idx=self.center_item.index_in_model: self.canvas_view._on_item_clicked(idx),
            )
        except Exception:
            pass

    def mouseReleaseEvent(self, event):
        try:
            self.center_item.setFlag(QGraphicsItem.ItemIsMovable, True)
            self.canvas_view._on_rotation_handle_released(self.center_item.index_in_model)
        except Exception:
            pass
        self._dragging = False
        super().mouseReleaseEvent(event)


class HandoffRadiusVisualizer(QGraphicsEllipseItem):
    def __init__(self, canvas_view: "CanvasView", center_m: QPointF, radius_m: float):
        super().__init__()
        self.canvas_view = canvas_view
        self.radius_m = radius_m
        self.setRect(-radius_m, -radius_m, radius_m * 2, radius_m * 2)
        self.setPos(self.canvas_view._scene_from_model(center_m.x(), center_m.y()))
        self.setPen(HANDOFF_RADIUS_PEN)
        self.setBrush(Qt.NoBrush)
        self.setZValue(20)
        self.setFlag(QGraphicsItem.ItemIsMovable, False)
        self.setFlag(QGraphicsItem.ItemIsSelectable, False)

    def set_center(self, center_m: QPointF):
        self.setPos(self.canvas_view._scene_from_model(center_m.x(), center_m.y()))

    def set_radius(self, radius_m: float):
        self.radius_m = radius_m
        self.setRect(-radius_m, -radius_m, radius_m * 2, radius_m * 2)
