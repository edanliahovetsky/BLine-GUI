"""Segment bar widget for constraint editing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Signal, QSize
from PySide6.QtGui import QColor, QPen, QFont, QFontMetrics, QWheelEvent

from ui.qt_compat import Qt, QSizePolicy, QPainter


SEGMENT_COLORS = {
    "max_velocity_meters_per_sec": QColor("#2d6a9f"),
    "max_acceleration_meters_per_sec2": QColor("#9f6a2d"),
    "max_velocity_deg_per_sec": QColor("#6a2d9f"),
    "max_acceleration_deg_per_sec2": QColor("#9f2d6a"),
}


@dataclass
class SegmentData:
    start_ordinal: int  # 1-based inclusive
    end_ordinal: int  # 1-based inclusive
    value: float
    color: QColor


class SegmentBar(QWidget):
    """A bar widget that displays coloured segments over a discrete ordinal domain.

    Each segment covers a contiguous range of ordinals.  Users can select,
    drag boundaries, double-click gaps, delete, and split segments via
    keyboard shortcuts.
    """

    segmentSelected = Signal(int)
    segmentBoundaryDragged = Signal(int, int, int)  # seg_idx, new_start, new_end
    segmentMoved = Signal(int, int, int)  # seg_idx, new_start, new_end (whole segment drag)
    adjacentBoundaryDragged = Signal(int, int, int, int, int, int)  # seg_a_idx, a_start, a_end, seg_b_idx, b_start, b_end
    segmentBoundaryDragFinished = Signal()
    gapDoubleClicked = Signal(int, int)
    deleteRequested = Signal(int)
    splitRequested = Signal(int)

    # Layout constants
    CELL_MIN_WIDTH = 40
    LABEL_HEIGHT = 16
    BAR_HEIGHT = 28
    BOUNDARY_HIT_WIDTH = 8

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        self._domain_size: int = 1
        self._segments: List[SegmentData] = []
        self._selected_index: int = -1
        self._element_labels: List[str] = []
        self._show_labels: bool = True
        self._unit_suffix: str = ""

        # Interaction state
        self._dragging_boundary: Optional[Tuple[int, str]] = None  # (segment_index, "start"|"end")
        self._drag_original_ordinal: int = 0
        self._dragging_segment: int = -1  # segment index being dragged as a whole
        self._drag_segment_offset: int = 0  # ordinal offset from click to segment start
        self._drag_segment_width: int = 0  # original segment width in ordinals
        self._hovered_boundary: Optional[Tuple[int, str]] = None
        self._hovered_segment: int = -1
        self._scroll_offset: int = 0

        self.setFixedHeight(48)

        try:
            self.setFocusPolicy(Qt.StrongFocus)
        except Exception:
            pass

        try:
            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            self.setMouseTracking(True)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_domain_size(self, count: int) -> None:
        """Set the total number of ordinals in the domain."""
        self._domain_size = max(1, int(count))
        self.update()

    def set_segments(self, segments: List[SegmentData]) -> None:
        """Replace all segments and repaint."""
        self._segments = list(segments)
        self.update()

    def set_selected_index(self, index: int) -> None:
        """Select a segment by index (-1 for none).  Emits *segmentSelected* if changed."""
        index = int(index)
        if index != self._selected_index:
            self._selected_index = index
            self.segmentSelected.emit(index)
            self.update()

    def selected_index(self) -> int:
        return self._selected_index

    def set_element_labels(self, labels: List[str]) -> None:
        """Set per-ordinal labels (element names)."""
        self._element_labels = list(labels)
        self.update()

    def set_show_labels(self, show: bool) -> None:
        """Toggle ordinal label visibility."""
        self._show_labels = bool(show)
        self.update()

    def set_unit_suffix(self, suffix: str) -> None:
        """Set the unit suffix shown after segment values."""
        self._unit_suffix = str(suffix)
        self.update()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _content_width(self) -> int:
        return max(self.width(), self._domain_size * self.CELL_MIN_WIDTH)

    def _cell_width(self) -> float:
        return self._content_width() / max(1, self._domain_size)

    def _ordinal_to_x(self, ordinal: int) -> float:
        """Return pixel x for the left edge of *ordinal* (1-based), accounting for scroll."""
        return (ordinal - 1) * self._cell_width() - self._scroll_offset

    def _x_to_ordinal(self, x: float) -> int:
        """Reverse mapping from pixel x to ordinal, clamped to [1, domain_size]."""
        ordinal = int((x + self._scroll_offset) / self._cell_width()) + 1
        return max(1, min(ordinal, self._domain_size))

    def _hit_test_boundary(self, x: int, y: int) -> Optional[Tuple[int, str]]:
        """Return (segment_index, 'start'|'end') if *x* is near a segment boundary, else None."""
        half = self.BOUNDARY_HIT_WIDTH / 2
        for i, seg in enumerate(self._segments):
            start_x = self._ordinal_to_x(seg.start_ordinal)
            end_x = self._ordinal_to_x(seg.end_ordinal + 1)
            if abs(x - start_x) <= half:
                return (i, "start")
            if abs(x - end_x) <= half:
                return (i, "end")
        return None

    def _hit_test_segment(self, x: int) -> int:
        """Return the index of the segment under *x*, or -1."""
        for i, seg in enumerate(self._segments):
            start_x = self._ordinal_to_x(seg.start_ordinal)
            end_x = self._ordinal_to_x(seg.end_ordinal + 1)
            if start_x <= x < end_x:
                return i
        return -1

    def _covered_ordinals(self) -> set:
        """Return the set of ordinals covered by any segment."""
        covered: set = set()
        for seg in self._segments:
            for o in range(seg.start_ordinal, seg.end_ordinal + 1):
                covered.add(o)
        return covered

    def _find_gap_at_ordinal(self, ordinal: int) -> Optional[Tuple[int, int]]:
        """Find a contiguous gap (uncovered run) containing *ordinal*."""
        covered = self._covered_ordinals()
        if ordinal in covered:
            return None
        # Expand left
        start = ordinal
        while start > 1 and (start - 1) not in covered:
            start -= 1
        # Expand right
        end = ordinal
        while end < self._domain_size and (end + 1) not in covered:
            end += 1
        return (start, end)

    def _hit_test_gap(self, x: int) -> Optional[Tuple[int, int]]:
        """Return (gap_start, gap_end) if *x* falls in a gap, else None."""
        ordinal = self._x_to_ordinal(x)
        return self._find_gap_at_ordinal(ordinal)

    # ------------------------------------------------------------------
    # Painting
    # ------------------------------------------------------------------

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.Antialiasing, False)
        except Exception:
            pass

        w = self.width()
        h = self.height()
        cell_w = self._cell_width()

        # 1. Background
        painter.fillRect(0, 0, w, h, QColor("#242424"))

        # 2. Ordinal labels
        if self._show_labels:
            label_font = QFont()
            label_font.setPointSize(9)
            painter.setFont(label_font)
            painter.setPen(QColor("#888888"))
            fm = QFontMetrics(label_font)

            # Determine skip factor so labels don't overlap
            sample_text = str(self._domain_size)
            min_label_w = fm.horizontalAdvance(sample_text) + 4
            skip = max(1, int(min_label_w / cell_w) + 1) if cell_w < min_label_w else 1

            for ordinal in range(1, self._domain_size + 1):
                if (ordinal - 1) % skip != 0:
                    continue
                cx = self._ordinal_to_x(ordinal) + cell_w / 2
                if self._element_labels and ordinal <= len(self._element_labels):
                    text = self._element_labels[ordinal - 1]
                else:
                    text = str(ordinal)
                tw = fm.horizontalAdvance(text)
                painter.drawText(int(cx - tw / 2), self.LABEL_HEIGHT - 2, text)

        bar_top = self.LABEL_HEIGHT
        bar_h = self.BAR_HEIGHT

        # 3. Draw gaps (uncovered ordinals)
        covered = self._covered_ordinals()
        gap_pen = QPen(QColor("#555555"), 1, Qt.DashLine)
        for ordinal in range(1, self._domain_size + 1):
            if ordinal not in covered:
                gx = self._ordinal_to_x(ordinal)
                # Only draw if visible
                if gx + cell_w < 0 or gx > w:
                    continue
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor("#3a3a3a"))
                painter.drawRect(int(gx), bar_top, int(cell_w), bar_h)
                painter.setPen(gap_pen)
                painter.setBrush(Qt.NoBrush)
                painter.drawRect(int(gx), bar_top, int(cell_w), bar_h)

        # 4. Draw segments
        value_font = QFont()
        value_font.setPointSize(10)
        value_font.setBold(True)
        painter.setFont(value_font)
        vfm = QFontMetrics(value_font)

        for i, seg in enumerate(self._segments):
            sx = self._ordinal_to_x(seg.start_ordinal)
            ex = self._ordinal_to_x(seg.end_ordinal + 1)
            seg_w = ex - sx
            if ex < 0 or sx > w:
                continue

            # Fill colour
            fill = QColor(seg.color)
            if i == self._selected_index:
                fill.setAlpha(255)
            else:
                fill.setAlpha(178)

            painter.setPen(Qt.NoPen)
            painter.setBrush(fill)
            painter.drawRect(int(sx), bar_top, int(seg_w), bar_h)

            # Value text
            painter.setPen(QColor("#f0f0f0"))
            painter.setFont(value_font)

            full_text = f"{seg.value:.1f}{self._unit_suffix}"
            short_text = f"{seg.value:.0f}"
            ellipsis = "..."

            full_tw = vfm.horizontalAdvance(full_text)
            short_tw = vfm.horizontalAdvance(short_text)
            ellipsis_tw = vfm.horizontalAdvance(ellipsis)

            text_y = bar_top + bar_h // 2 + vfm.ascent() // 2

            if full_tw + 4 <= seg_w:
                text = full_text
                tw = full_tw
            elif short_tw + 4 <= seg_w:
                text = short_text
                tw = short_tw
            elif ellipsis_tw + 2 <= seg_w:
                text = ellipsis
                tw = ellipsis_tw
            else:
                text = ""
                tw = 0

            if text:
                tx = int(sx + seg_w / 2 - tw / 2)
                painter.drawText(tx, text_y, text)

        # 5. Selection highlight
        if 0 <= self._selected_index < len(self._segments):
            sel = self._segments[self._selected_index]
            sx = self._ordinal_to_x(sel.start_ordinal)
            ex = self._ordinal_to_x(sel.end_ordinal + 1)
            sel_pen = QPen(QColor("#15c915"), 2)
            painter.setPen(sel_pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(int(sx) + 1, bar_top + 1, int(ex - sx) - 2, bar_h - 2)

        # 6. Boundary markers
        for i, seg in enumerate(self._segments):
            for side in ("start", "end"):
                if side == "start":
                    bx = self._ordinal_to_x(seg.start_ordinal)
                else:
                    bx = self._ordinal_to_x(seg.end_ordinal + 1)
                if bx < 0 or bx > w:
                    continue
                if self._hovered_boundary == (i, side):
                    painter.setPen(QPen(QColor("#cccccc"), 3))
                else:
                    painter.setPen(QPen(QColor("#888888"), 2))
                painter.drawLine(int(bx), bar_top, int(bx), bar_top + bar_h)

        # 7. Scroll indicator
        content_w = self._content_width()
        if content_w > w:
            indicator_h = 2
            indicator_y = h - indicator_h
            # Track
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor("#333333"))
            painter.drawRect(0, indicator_y, w, indicator_h)
            # Thumb
            thumb_w = max(10, int(w * w / content_w))
            max_scroll = content_w - w
            thumb_x = int(self._scroll_offset / max_scroll * (w - thumb_w)) if max_scroll > 0 else 0
            painter.setBrush(QColor("#888888"))
            painter.drawRect(thumb_x, indicator_y, thumb_w, indicator_h)

        painter.end()

    # ------------------------------------------------------------------
    # Mouse interaction
    # ------------------------------------------------------------------

    def mousePressEvent(self, event) -> None:  # noqa: N802
        x = int(event.position().x() if hasattr(event, "position") else event.x())
        y = int(event.position().y() if hasattr(event, "position") else event.y())

        # 1. Boundary hit?
        boundary = self._hit_test_boundary(x, y)
        if boundary is not None:
            seg_idx, side = boundary
            seg = self._segments[seg_idx]
            self._dragging_boundary = boundary
            self._drag_original_ordinal = seg.start_ordinal if side == "start" else seg.end_ordinal
            event.accept()
            self.setFocus(Qt.MouseFocusReason)
            return

        # 2. Segment hit? — select and start potential drag
        seg_idx = self._hit_test_segment(x)
        if seg_idx >= 0:
            if seg_idx == self._selected_index:
                # Re-click on already-selected segment: re-emit to refresh preview
                self.segmentSelected.emit(seg_idx)
            else:
                self.set_selected_index(seg_idx)
            seg = self._segments[seg_idx]
            self._dragging_segment = seg_idx
            click_ordinal = self._x_to_ordinal(x)
            self._drag_segment_offset = click_ordinal - seg.start_ordinal
            self._drag_segment_width = seg.end_ordinal - seg.start_ordinal
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            self.setFocus(Qt.MouseFocusReason)
            return

        # 3. Gap — clear selection
        self.set_selected_index(-1)
        event.accept()
        self.setFocus(Qt.MouseFocusReason)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        x = int(event.position().x() if hasattr(event, "position") else event.x())
        gap = self._hit_test_gap(x)
        if gap is not None:
            self.gapDoubleClicked.emit(gap[0], gap[1])
            event.accept()
            return
        event.accept()

    def _find_adjacent_segment(self, seg_idx: int, side: str) -> int:
        """Find the index of a segment adjacent to seg on the given side, or -1."""
        seg = self._segments[seg_idx]
        for i, other in enumerate(self._segments):
            if i == seg_idx:
                continue
            if side == "start" and other.end_ordinal == seg.start_ordinal - 1:
                return i
            if side == "end" and other.start_ordinal == seg.end_ordinal + 1:
                return i
        return -1

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        x = int(event.position().x() if hasattr(event, "position") else event.x())
        y = int(event.position().y() if hasattr(event, "position") else event.y())

        # --- Boundary drag ---
        if self._dragging_boundary is not None:
            seg_idx, side = self._dragging_boundary
            new_ordinal = self._x_to_ordinal(x)
            seg = self._segments[seg_idx]

            # Find adjacent segment on the dragged side
            adj_idx = self._find_adjacent_segment(seg_idx, side)

            if side == "start":
                new_ordinal = min(new_ordinal, seg.end_ordinal)  # can't cross own end
                new_ordinal = max(1, new_ordinal)

                if adj_idx >= 0:
                    # Adjacent segment: resize both (shared boundary)
                    adj = self._segments[adj_idx]
                    new_ordinal = max(new_ordinal, adj.start_ordinal + 1)  # adj must keep at least 1
                    adj.end_ordinal = new_ordinal - 1
                    self.adjacentBoundaryDragged.emit(
                        adj_idx, adj.start_ordinal, adj.end_ordinal,
                        seg_idx, new_ordinal, seg.end_ordinal,
                    )
                else:
                    # No adjacent: clamp against other non-adjacent segments
                    for other in self._segments:
                        if other is seg:
                            continue
                        if other.end_ordinal < seg.end_ordinal and other.end_ordinal >= new_ordinal:
                            new_ordinal = other.end_ordinal + 1
                    new_ordinal = max(1, new_ordinal)
                    self.segmentBoundaryDragged.emit(seg_idx, new_ordinal, seg.end_ordinal)

                seg.start_ordinal = new_ordinal

            else:  # side == "end"
                new_ordinal = max(new_ordinal, seg.start_ordinal)  # can't cross own start
                new_ordinal = min(self._domain_size, new_ordinal)

                if adj_idx >= 0:
                    # Adjacent segment: resize both
                    adj = self._segments[adj_idx]
                    new_ordinal = min(new_ordinal, adj.end_ordinal - 1)  # adj must keep at least 1
                    adj.start_ordinal = new_ordinal + 1
                    self.adjacentBoundaryDragged.emit(
                        seg_idx, seg.start_ordinal, new_ordinal,
                        adj_idx, new_ordinal + 1, adj.end_ordinal,
                    )
                else:
                    # No adjacent: clamp against other segments
                    for other in self._segments:
                        if other is seg:
                            continue
                        if other.start_ordinal > seg.start_ordinal and other.start_ordinal <= new_ordinal:
                            new_ordinal = other.start_ordinal - 1
                    new_ordinal = min(self._domain_size, new_ordinal)
                    self.segmentBoundaryDragged.emit(seg_idx, seg.start_ordinal, new_ordinal)

                seg.end_ordinal = new_ordinal

            self.update()
            event.accept()
            return

        # --- Whole segment drag ---
        if self._dragging_segment >= 0:
            seg = self._segments[self._dragging_segment]
            target_ordinal = self._x_to_ordinal(x)
            new_start = target_ordinal - self._drag_segment_offset
            new_end = new_start + self._drag_segment_width

            # Clamp to domain bounds
            if new_start < 1:
                new_start = 1
                new_end = new_start + self._drag_segment_width
            if new_end > self._domain_size:
                new_end = self._domain_size
                new_start = new_end - self._drag_segment_width

            # Clamp against other segments
            for other in self._segments:
                if other is seg:
                    continue
                # Would overlap other segment — stop at its edge
                if new_start <= other.end_ordinal and new_end >= other.start_ordinal:
                    if seg.start_ordinal <= other.start_ordinal:
                        # Moving right into other
                        new_end = other.start_ordinal - 1
                        new_start = new_end - self._drag_segment_width
                    else:
                        # Moving left into other
                        new_start = other.end_ordinal + 1
                        new_end = new_start + self._drag_segment_width

            new_start = max(1, new_start)
            new_end = min(self._domain_size, new_end)

            if new_start != seg.start_ordinal or new_end != seg.end_ordinal:
                seg.start_ordinal = new_start
                seg.end_ordinal = new_end
                self.update()
                self.segmentMoved.emit(self._dragging_segment, new_start, new_end)

            event.accept()
            return

        # --- Not dragging — hover detection ---
        old_boundary = self._hovered_boundary
        old_segment = self._hovered_segment

        boundary = self._hit_test_boundary(x, y)
        if boundary is not None:
            self._hovered_boundary = boundary
            self._hovered_segment = -1
            self.setCursor(Qt.SizeHorCursor)
        else:
            self._hovered_boundary = None
            seg_idx = self._hit_test_segment(x)
            self._hovered_segment = seg_idx
            if seg_idx >= 0:
                self.setCursor(Qt.OpenHandCursor)
            else:
                self.unsetCursor()

        if old_boundary != self._hovered_boundary or old_segment != self._hovered_segment:
            self.update()

        event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._dragging_boundary is not None:
            self._dragging_boundary = None
            self._drag_original_ordinal = 0
            self.segmentBoundaryDragFinished.emit()
            self.update()
        if self._dragging_segment >= 0:
            self._dragging_segment = -1
            self.unsetCursor()
            self.segmentBoundaryDragFinished.emit()  # reuse same signal for undo commit
            self.update()
        event.accept()

    # ------------------------------------------------------------------
    # Wheel / Keyboard / Leave
    # ------------------------------------------------------------------

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        content_w = self._content_width()
        widget_w = self.width()
        if content_w <= widget_w:
            event.ignore()
            return
        delta = -event.angleDelta().y()
        self._scroll_offset = max(0, min(self._scroll_offset + delta, content_w - widget_w))
        self.update()
        event.accept()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        key = event.key()

        if key == Qt.Key_Left:
            if self._selected_index > 0:
                self.set_selected_index(self._selected_index - 1)
            event.accept()
            return
        if key == Qt.Key_Right:
            if self._selected_index < len(self._segments) - 1:
                self.set_selected_index(self._selected_index + 1)
            event.accept()
            return
        if key in (Qt.Key_Delete, Qt.Key_Backspace):
            if 0 <= self._selected_index < len(self._segments):
                self.deleteRequested.emit(self._selected_index)
            event.accept()
            return
        if key == Qt.Key_S:
            if 0 <= self._selected_index < len(self._segments):
                self.splitRequested.emit(self._selected_index)
            event.accept()
            return

        super().keyPressEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hovered_boundary = None
        self._hovered_segment = -1
        self.unsetCursor()
        self.update()

    # ------------------------------------------------------------------
    # Size hint
    # ------------------------------------------------------------------

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(200, 48)
