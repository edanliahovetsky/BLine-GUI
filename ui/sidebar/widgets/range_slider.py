"""Range slider widget for constraint range selection."""

from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Signal, QRect, QSize
from PySide6.QtGui import QColor, QPen, QFont, QFontMetrics
from typing import Optional, Tuple

from ui.qt_compat import Qt, QSizePolicy, QPainter


class RangeSlider(QWidget):
    """A custom range slider widget for selecting a range between min and max values."""

    rangeChanged = Signal(int, int)
    interactionFinished = Signal(int, int)

    def __init__(self, minimum: int = 1, maximum: int = 1, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._min = int(minimum)
        self._max = int(maximum)
        self._low = int(minimum)
        self._high = int(maximum)
        self._dragging: Optional[str] = None  # 'low' | 'high' | 'band'
        self._press_value: int = self._low
        self._band_width: int = max(0, self._high - self._low)
        self._press_low: int = self._low
        # Minimum number of notches the handles must be apart. 1 prevents overlap.
        self._min_separation: int = 1
        # Drag offset to prevent handle snap on click
        self._drag_offset: int = 0
        # Hover state
        self._hovered_handle: Optional[str] = None
        # Keyboard focus state
        self._focused_handle: str = "low"
        self.setMinimumHeight(38)

        try:
            self.setEnabled(True)
            self.setFocusPolicy(Qt.StrongFocus)
            self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        except Exception:
            pass

        try:
            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            self.setMouseTracking(True)
        except Exception:
            pass

    def setRange(self, minimum: int, maximum: int):
        """Set the range of the slider."""
        self._min = int(minimum)
        self._max = max(int(maximum), self._min)
        self._low = min(max(self._low, self._min), self._max)
        self._high = min(max(self._high, self._min), self._max)
        # Enforce minimum separation after range change
        self._low, self._high = self._apply_min_separation(self._low, self._high)
        self.update()

    def setMinimumSeparation(self, separation: int):
        """Set the minimum required separation (in notches) between handles."""
        self._min_separation = max(0, int(separation))
        # Re-apply constraint to current values
        self._low, self._high = self._apply_min_separation(self._low, self._high)
        self.update()

    def setValues(self, low: int, high: int):
        """Set the current range values."""
        low = int(low)
        high = int(high)
        if low > high:
            low, high = high, low
        low = min(max(low, self._min), self._max)
        high = min(max(high, self._min), self._max)
        low, high = self._apply_min_separation(low, high)
        changed = (low != self._low) or (high != self._high)
        self._low, self._high = low, high
        if changed:
            self.rangeChanged.emit(self._low, self._high)
            self.update()

    def _setValuesInternal(self, low: int, high: int):
        """Internal value update without emitting signals - for drag operations."""
        low = int(low)
        high = int(high)
        if low > high:
            low, high = high, low
        low = min(max(low, self._min), self._max)
        high = min(max(high, self._min), self._max)
        low, high = self._apply_min_separation(low, high)
        self._low, self._high = low, high
        self.update()

    def _apply_min_separation(self, low: int, high: int) -> Tuple[int, int]:
        """Ensure that high - low >= effective minimum separation.
        Attempts to resolve according to the drag context for natural behavior.
        """
        # Effective separation cannot exceed the available span
        total_span = max(0, self._max - self._min)
        sep = min(max(0, self._min_separation), total_span)
        if sep <= 0:
            return low, high
        if (high - low) >= sep:
            return low, high

        # Need to adjust values to satisfy separation
        if self._dragging == "low":
            # Keep high as requested, move low leftwards
            high = min(high, self._max)
            low = min(high - sep, self._max - sep)
            low = max(low, self._min)
        elif self._dragging == "high":
            # Keep low as requested, move high rightwards
            low = max(low, self._min)
            high = max(low + sep, self._min + sep)
            high = min(high, self._max)
        elif self._dragging == "band":
            # Maintain at least sep width while respecting bounds
            low = max(low, self._min)
            # Prefer expanding to the right if possible
            if low + sep <= self._max:
                high = low + sep
            else:
                high = self._max
                low = max(self._min, high - sep)
        else:
            # No specific drag context (programmatic set). Prefer expanding upwards.
            low = max(low, self._min)
            if low + sep <= self._max:
                high = low + sep
            else:
                high = self._max
                low = max(self._min, high - sep)
        return int(low), int(high)

    def values(self) -> Tuple[int, int]:
        """Get the current range values."""
        return self._low, self._high

    def _get_track_h(self) -> int:
        """Get the track height based on widget height."""
        rect = self.contentsRect()
        return max(6, rect.height() // 6)

    def _get_handle_dims(self, track_h: int) -> Tuple[int, int]:
        """Get handle width and height."""
        handle_w = max(14, track_h * 2)
        handle_h = max(22, int(track_h * 3.5))
        return handle_w, handle_h

    def _pos_to_value(self, x: int) -> int:
        """Convert a pixel position to a value."""
        rect = self.contentsRect()
        if rect.width() <= 0:
            return self._min
        # Account for padding to match _value_to_pos
        track_h = self._get_track_h()
        handle_w, _ = self._get_handle_dims(track_h)
        padding = handle_w // 2
        usable_width = max(1.0, float(rect.width() - 2 * padding))
        ratio = (x - rect.left() - padding) / usable_width
        ratio = max(0.0, min(1.0, ratio))  # Clamp to valid range
        val = self._min + ratio * (self._max - self._min)
        return int(round(val))

    def _value_to_pos(self, v: int) -> int:
        """Convert a value to a pixel position."""
        rect = self.contentsRect()
        if self._max == self._min:
            return rect.left()
        # Add padding to prevent handle clipping at edges
        track_h = self._get_track_h()
        handle_w, _ = self._get_handle_dims(track_h)
        padding = handle_w // 2
        usable_width = max(1, rect.width() - 2 * padding)
        ratio = (float(v) - self._min) / float(self._max - self._min)
        return int(rect.left() + padding + ratio * usable_width)

    def _hit_test(self, x: int, y: int) -> Optional[str]:
        """Hit-test the given coordinates. Returns 'low', 'high', 'band', or None."""
        x1 = self._value_to_pos(self._low)
        x2 = self._value_to_pos(self._high)
        if x1 > x2:
            x1, x2 = x2, x1
        rect = self.contentsRect()
        cy = rect.center().y()
        track_h = self._get_track_h()
        handle_w, handle_h = self._get_handle_dims(track_h)

        click_padding = 8
        low_rect = QRect(
            x1 - handle_w // 2 - click_padding,
            cy - handle_h // 2 - click_padding,
            handle_w + 2 * click_padding,
            handle_h + 2 * click_padding,
        )
        high_rect = QRect(
            x2 - handle_w // 2 - click_padding,
            cy - handle_h // 2 - click_padding,
            handle_w + 2 * click_padding,
            handle_h + 2 * click_padding,
        )

        # Check handles first (prefer handle over band when overlapping)
        if low_rect.contains(x, y):
            return "low"
        if high_rect.contains(x, y):
            return "high"
        if x1 <= x <= x2:
            return "band"
        return None

    def sizeHint(self):
        """Provide a size hint for the widget."""
        try:
            return QSize(200, max(38, self.minimumHeight()))
        except Exception:
            return super().sizeHint()

    def paintEvent(self, event):
        """Paint the range slider."""
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.Antialiasing, False)
        except Exception:
            pass
        rect = self.contentsRect()
        track_h = self._get_track_h()
        handle_w, handle_h = self._get_handle_dims(track_h)
        cy = rect.center().y()

        # Focus border (dotted green when widget has keyboard focus)
        if self.hasFocus():
            focus_pen = QPen(QColor("#15c915"), 1, Qt.DotLine)
            painter.setPen(focus_pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(rect.adjusted(0, 0, -1, -1))

        # Track
        pen = QPen(QColor("#666666"), 1)
        painter.setPen(pen)
        painter.setBrush(QColor("#444444"))
        painter.drawRect(QRect(rect.left(), cy - track_h // 2, rect.width(), track_h))

        # Tick marks at integer positions
        try:
            total = max(1, self._max - self._min)
            # Limit number of ticks to avoid clutter (aim ~20 max)
            step = 1
            if total > 20:
                # choose a step that results in ~20 ticks
                step = max(1, (total // 20))
            painter.setPen(QPen(QColor("#aaaaaa"), 1))
            tick_h = max(4, track_h)
            for v in range(self._min, self._max + 1, step):
                x = self._value_to_pos(v)
                painter.drawLine(x, cy - tick_h, x, cy + tick_h)
        except Exception:
            pass

        # Selected range (band)
        x1 = self._value_to_pos(self._low)
        x2 = self._value_to_pos(self._high)
        band_hovered = self._hovered_handle == "band" and self._dragging is None
        band_color = "#1ad61a" if band_hovered else "#15c915"
        painter.setBrush(QColor(band_color))
        painter.setPen(Qt.NoPen)
        painter.drawRect(QRect(min(x1, x2), cy - track_h // 2, abs(x2 - x1), track_h))

        # Band grip lines (3 short horizontal lines at center, only when band >= 3 units)
        if (self._high - self._low) >= 3:
            band_cx = (x1 + x2) // 2
            grip_color = QColor("#0ea00e")
            painter.setPen(QPen(grip_color, 1))
            grip_w = 2
            for i in range(-1, 2):  # -1, 0, 1 -> 3 lines, 1px apart
                gy = cy + i * 2
                painter.drawLine(band_cx - grip_w, gy, band_cx + grip_w, gy)

        # Handles
        for handle_name, hx in [("low", x1), ("high", x2)]:
            is_dragged = self._dragging == handle_name
            is_hovered = self._hovered_handle == handle_name and self._dragging is None
            is_focused_kb = self.hasFocus() and self._focused_handle == handle_name and self._dragging is None

            if is_dragged:
                fill = QColor("#ffffff")
                border = QColor("#15c915")
                border_w = 2
            elif is_hovered or is_focused_kb:
                fill = QColor("#eeeeee")
                border = QColor("#15c915")
                border_w = 2
            else:
                fill = QColor("#dddddd")
                border = QColor("#222222")
                border_w = 1

            painter.setBrush(fill)
            painter.setPen(QPen(border, border_w))
            handle_rect = QRect(
                hx - handle_w // 2,
                cy - handle_h // 2,
                handle_w,
                handle_h,
            )
            painter.drawRect(handle_rect)

        # Value labels above handles
        label_font = QFont()
        label_font.setPointSize(10)
        label_font.setBold(True)
        painter.setFont(label_font)
        painter.setPen(QColor("#f0f0f0"))
        fm = QFontMetrics(label_font)

        low_text = str(int(self._low))
        high_text = str(int(self._high))
        low_tw = fm.horizontalAdvance(low_text)
        high_tw = fm.horizontalAdvance(high_text)
        label_y = cy - handle_h // 2 - 3  # just above handle

        # Check if labels would overlap
        labels_overlap = abs(x2 - x1) < (low_tw + high_tw) // 2 + 4

        if labels_overlap and self._low != self._high:
            # Draw combined label centered between handles
            combined = f"{int(self._low)}-{int(self._high)}"
            combined_tw = fm.horizontalAdvance(combined)
            combined_x = (x1 + x2) // 2 - combined_tw // 2
            painter.drawText(combined_x, label_y, combined)
        else:
            # Draw individual labels centered above each handle
            painter.drawText(x1 - low_tw // 2, label_y, low_text)
            painter.drawText(x2 - high_tw // 2, label_y, high_text)

        # Min/max endpoint labels below the track
        endpoint_font = QFont()
        endpoint_font.setPointSize(9)
        painter.setFont(endpoint_font)
        painter.setPen(QColor("#888888"))
        efm = QFontMetrics(endpoint_font)

        min_text = str(int(self._min))
        max_text = str(int(self._max))
        min_tw = efm.horizontalAdvance(min_text)
        max_tw = efm.horizontalAdvance(max_text)
        endpoint_y = cy + handle_h // 2 + efm.ascent() + 2

        min_x = self._value_to_pos(self._min)
        max_x = self._value_to_pos(self._max)
        painter.drawText(min_x - min_tw // 2, endpoint_y, min_text)
        painter.drawText(max_x - max_tw // 2, endpoint_y, max_text)

    def mousePressEvent(self, event):
        """Handle mouse press events to start dragging."""
        x = int(event.position().x() if hasattr(event, "position") else event.x())
        y = int(event.position().y() if hasattr(event, "position") else event.y())

        hit = self._hit_test(x, y)

        if hit == "low":
            self._dragging = "low"
            self._drag_offset = x - self._value_to_pos(self._low)
        elif hit == "high":
            self._dragging = "high"
            self._drag_offset = x - self._value_to_pos(self._high)
        elif hit == "band":
            self._dragging = "band"
            self._press_value = self._pos_to_value(x)
            self._band_width = max(0, self._high - self._low)
            self._press_low = self._low
            self.setCursor(Qt.ClosedHandCursor)
        else:
            # Click on track outside -> move nearest handle
            x1 = self._value_to_pos(self._low)
            x2 = self._value_to_pos(self._high)
            if abs(x - x1) <= abs(x - x2):
                self._dragging = "low"
                self._drag_offset = 0
                self._setValuesInternal(self._pos_to_value(x), self._high)
                self.rangeChanged.emit(self._low, self._high)
            else:
                self._dragging = "high"
                self._drag_offset = 0
                self._setValuesInternal(self._low, self._pos_to_value(x))
                self.rangeChanged.emit(self._low, self._high)

        # Accept event and focus
        try:
            event.accept()
        except Exception:
            pass
        try:
            self.setFocus(Qt.MouseFocusReason)
        except Exception:
            pass

    def mouseMoveEvent(self, event):
        """Handle mouse move events during dragging and hover."""
        x = int(event.position().x() if hasattr(event, "position") else event.x())
        y = int(event.position().y() if hasattr(event, "position") else event.y())

        if not self._dragging:
            # Hover detection
            hit = self._hit_test(x, y)
            old_hovered = self._hovered_handle
            self._hovered_handle = hit
            if hit == "low" or hit == "high":
                self.setCursor(Qt.SizeHorCursor)
            elif hit == "band":
                self.setCursor(Qt.OpenHandCursor)
            else:
                self.unsetCursor()
            if old_hovered != self._hovered_handle:
                self.update()
            return

        prev_low, prev_high = self._low, self._high
        if self._dragging == "low":
            target_x = x - self._drag_offset
            self._setValuesInternal(self._pos_to_value(target_x), self._high)
        elif self._dragging == "high":
            target_x = x - self._drag_offset
            self._setValuesInternal(self._low, self._pos_to_value(target_x))
        elif self._dragging == "band":
            curr_val = self._pos_to_value(x)
            delta = curr_val - self._press_value
            new_low = self._press_low + delta
            new_high = new_low + self._band_width
            # Clamp to bounds
            if new_low < self._min:
                new_low = self._min
                new_high = self._band_width + new_low
            if new_high > self._max:
                new_high = self._max
                new_low = new_high - self._band_width
            self._setValuesInternal(int(new_low), int(new_high))
        # Emit live update if values changed
        if self._low != prev_low or self._high != prev_high:
            try:
                self.rangeChanged.emit(self._low, self._high)
            except Exception:
                pass
        try:
            event.accept()
        except Exception:
            pass

    def mouseReleaseEvent(self, event):
        """Handle mouse release events to finish dragging."""
        try:
            event.accept()
        except Exception:
            pass

        was_dragging = self._dragging is not None
        self._dragging = None
        self._drag_offset = 0

        # Restore cursor based on hover
        x = int(event.position().x() if hasattr(event, "position") else event.x())
        y = int(event.position().y() if hasattr(event, "position") else event.y())
        hit = self._hit_test(x, y)
        self._hovered_handle = hit
        if hit == "low" or hit == "high":
            self.setCursor(Qt.SizeHorCursor)
        elif hit == "band":
            self.setCursor(Qt.OpenHandCursor)
        else:
            self.unsetCursor()

        if was_dragging:
            try:
                self.interactionFinished.emit(self._low, self._high)
            except Exception:
                pass
        self.update()

    def leaveEvent(self, event):
        """Reset hover state when mouse leaves the widget."""
        self._hovered_handle = None
        self.unsetCursor()
        self.update()

    def keyPressEvent(self, event):
        """Handle keyboard navigation of the slider."""
        key = event.key()
        modifiers = event.modifiers()
        shift = bool(modifiers & Qt.ShiftModifier)

        if key == Qt.Key_Tab:
            # Toggle focused handle
            self._focused_handle = "high" if self._focused_handle == "low" else "low"
            self.update()
            event.accept()
            return

        step = 5 if shift else 1
        changed = False

        if key == Qt.Key_Left:
            if self._focused_handle == "low":
                new_low = max(self._min, self._low - step)
                if new_low != self._low:
                    self._low = new_low
                    # Enforce separation
                    self._low, self._high = self._apply_min_separation(self._low, self._high)
                    changed = True
            else:
                new_high = max(self._min, self._high - step)
                if new_high != self._high:
                    self._high = new_high
                    self._low, self._high = self._apply_min_separation(self._low, self._high)
                    changed = True
        elif key == Qt.Key_Right:
            if self._focused_handle == "low":
                new_low = min(self._max, self._low + step)
                if new_low != self._low:
                    self._low = new_low
                    self._low, self._high = self._apply_min_separation(self._low, self._high)
                    changed = True
            else:
                new_high = min(self._max, self._high + step)
                if new_high != self._high:
                    self._high = new_high
                    self._low, self._high = self._apply_min_separation(self._low, self._high)
                    changed = True
        elif key == Qt.Key_Home:
            if self._focused_handle == "low":
                if self._low != self._min:
                    self._low = self._min
                    self._low, self._high = self._apply_min_separation(self._low, self._high)
                    changed = True
            else:
                if self._high != self._min:
                    self._high = self._min
                    self._low, self._high = self._apply_min_separation(self._low, self._high)
                    changed = True
        elif key == Qt.Key_End:
            if self._focused_handle == "low":
                if self._low != self._max:
                    self._low = self._max
                    self._low, self._high = self._apply_min_separation(self._low, self._high)
                    changed = True
            else:
                if self._high != self._max:
                    self._high = self._max
                    self._low, self._high = self._apply_min_separation(self._low, self._high)
                    changed = True
        else:
            super().keyPressEvent(event)
            return

        if changed:
            # Ensure low <= high
            if self._low > self._high:
                self._low, self._high = self._high, self._low
            self.rangeChanged.emit(self._low, self._high)
            self.update()
        event.accept()

    def keyReleaseEvent(self, event):
        """Emit interactionFinished on key release for arrow/home/end keys."""
        key = event.key()
        if key in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Home, Qt.Key_End):
            try:
                self.interactionFinished.emit(self._low, self._high)
            except Exception:
                pass
        super().keyReleaseEvent(event)
