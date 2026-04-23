# mypy: ignore-errors
"""Constraint manager component for handling path constraints and segment bars."""

from typing import Dict, Optional, Tuple, Any, List
import traceback
from PySide6.QtCore import QObject, Signal, QTimer, QEvent
from PySide6.QtWidgets import (
    QWidget,
    QLabel,
    QDoubleSpinBox,
    QVBoxLayout,
    QFormLayout,
    QPushButton,
    QHBoxLayout,
)
from PySide6.QtGui import QCursor, QMouseEvent, QIcon, QColor
from PySide6.QtCore import QSize
from models.path_model import Path, RangedConstraint
from models.ranged_constraint_ops import (
    append_ranged_constraint_instance,
    split_ranged_constraint_instance,
)
from ..widgets import NoWheelDoubleSpinBox
from ..utils import (
    SPINNER_METADATA,
    PATH_CONSTRAINT_KEYS,
    NON_RANGED_CONSTRAINT_KEYS,
    TRANSLATION_CONSTRAINT_KEYS,
    constraint_default_value,
    get_constraint_domain_info,
)
from ui.sidebar.widgets.segment_bar import SegmentBar, SegmentData, SEGMENT_COLORS

from ui.qt_compat import Qt, QSizePolicy, QFormLayoutRoles


class ConstraintManager(QObject):
    """Manages path constraints and their UI representations including segment bars."""

    # Signals
    constraintAdded = Signal(str, float)  # key, value
    constraintRemoved = Signal(str)  # key
    constraintValueChanged = Signal(str, float)  # key, value
    constraintRangeChanged = Signal(str, int, int)  # key, start, end
    # Undo/redo coordination signals (forwarded by Sidebar)
    aboutToChange = Signal(str)
    userActionOccurred = Signal(str)

    # Preview overlay signals
    constraintRangePreviewRequested = Signal(str, int, int)  # key, start_ordinal, end_ordinal
    constraintRangePreviewCleared = Signal()

    # Popout lifecycle signals
    popoutOpened = Signal()
    popoutClosed = Signal()
    # Emitted when a segment is selected in the popout: key, start_ordinal, end_ordinal
    popoutSegmentSelected = Signal(str, int, int)
    # Forwarded from popout so main window can trigger undo/redo
    undoRequested = Signal()
    redoRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.path = None  # type: Optional[Path]
        self.project_manager = None  # Set externally for config access
        self._active_preview_key = None
        # Map of constraint key -> field container used in constraints layout
        self._constraint_field_containers = {}
        # Segment bar state
        self._segment_bars: Dict[str, SegmentBar] = {}
        self._segment_spinboxes: Dict[str, QDoubleSpinBox] = {}
        self._segment_rc_lists: Dict[str, List[RangedConstraint]] = {}
        self._selected_segment_indices: Dict[str, int] = {}
        self._popout_dialog = None
        self._boundary_drag_started: bool = False

    def set_path(self, path: Path):
        """Set the path to manage constraints for."""
        self.path = path
        # Update popout reference so it sees fresh objects (e.g. after undo/redo deepcopy)
        if self._popout_dialog is not None:
            try:
                self._popout_dialog.set_path(path)
            except Exception:
                pass

    def get_default_value(self, key: str) -> float:
        """Get default value for a constraint from config or metadata."""
        cfg_default = None
        try:
            if self.project_manager is not None:
                cfg_default = self.project_manager.get_default_optional_value(key)
        except Exception:
            cfg_default = None

        if cfg_default is not None:
            return float(cfg_default)

        return constraint_default_value(key)

    def add_constraint(self, key: str, value: Optional[float] = None) -> bool:
        """Add a path-level constraint.

        For ranged-capable constraints, this will APPEND a new ranged instance instead of
        replacing existing ones so multiple instances of the same constraint key may exist.
        """
        if self.path is None or not hasattr(self.path, "constraints"):
            return False

        if value is None:
            value = self.get_default_value(key)
        # For non-ranged keys, store directly on flat constraints
        if key in NON_RANGED_CONSTRAINT_KEYS:
            try:
                setattr(self.path.constraints, key, float(value))
            except Exception:
                pass
            # Remove any stray ranged constraints of same key (defensive)
            try:
                self.path.ranged_constraints = [
                    rc
                    for rc in (getattr(self.path, "ranged_constraints", []) or [])
                    if rc.key != key
                ]
            except Exception:
                pass
        else:
            try:
                _domain, count = self.get_domain_info_for_key(key)
                total = int(count) if int(count) > 0 else 1
                if (
                    not hasattr(self.path, "ranged_constraints")
                    or self.path.ranged_constraints is None
                ):
                    self.path.ranged_constraints = []
                new_rc = append_ranged_constraint_instance(
                    self.path.ranged_constraints,
                    key=key,
                    value=value,
                    total=total,
                )
                if new_rc is None:
                    return False
            except Exception:
                pass
            # Clear flat value storage for ranged keys
            try:
                setattr(self.path.constraints, key, None)
            except Exception:
                pass

        self.constraintAdded.emit(key, value)
        return True

    def remove_constraint(self, key: str) -> bool:
        """Remove a path-level constraint."""
        if self.path is None or not hasattr(self.path, "constraints"):
            return False

        if key in NON_RANGED_CONSTRAINT_KEYS:
            # Remove flat constraint only
            try:
                setattr(self.path.constraints, key, None)
            except Exception:
                pass
            self.constraintRemoved.emit(key)
            return True
        # Ranged-capable key
        try:
            ranged_list = [
                rc
                for rc in (getattr(self.path, "ranged_constraints", []) or [])
                if getattr(rc, "key", None) == key
            ]
        except Exception:
            ranged_list = []
        if not ranged_list:
            # Nothing to remove; ensure flat cleared
            try:
                setattr(self.path.constraints, key, None)
            except Exception:
                pass
            # Also remove any lingering UI container for this key
            try:
                self._remove_container_for_key(key)
            except Exception:
                pass
            self.constraintRemoved.emit(key)
            return True
        if len(ranged_list) > 1:
            # Remove only the FIRST instance (top) and keep others
            first = ranged_list[0]
            try:
                self.path.ranged_constraints = [
                    rc
                    for rc in (getattr(self.path, "ranged_constraints", []) or [])
                    if rc is not first
                ]
            except Exception:
                pass
            # Do NOT emit full removal; UI refresh will rebuild remaining instances
            return True
        # Single instance -> full removal
        try:
            self.path.ranged_constraints = [
                rc
                for rc in (getattr(self.path, "ranged_constraints", []) or [])
                if getattr(rc, "key", None) != key
            ]
        except Exception:
            pass
        try:
            setattr(self.path.constraints, key, None)
        except Exception:
            pass
        # Remove visual container if present
        try:
            self._remove_container_for_key(key)
        except Exception:
            pass
        self.constraintRemoved.emit(key)
        return True

    def _remove_container_for_key(self, key: str):
        """Hide the visual container and clear references for a ranged constraint key without disturbing others."""
        container = None
        try:
            container = self._constraint_field_containers.get(key, None)
        except Exception:
            container = None
        self._segment_bars.pop(key, None)
        self._segment_spinboxes.pop(key, None)
        self._segment_rc_lists.pop(key, None)
        self._selected_segment_indices.pop(key, None)
        if container is not None:
            try:
                container.setVisible(False)
            except Exception:
                pass

    def _dispose_dynamic_widget(self, widget: Optional[QWidget]) -> None:
        """Hide, detach, and defer-delete a rebuilt row widget."""
        if widget is None:
            return
        try:
            widget.hide()
        except Exception:
            pass
        try:
            parent = widget.parentWidget()
            if parent is not None and parent.layout() is not None:
                parent.layout().removeWidget(widget)
        except Exception:
            pass
        try:
            widget.setParent(None)
        except Exception:
            pass
        try:
            widget.deleteLater()
        except Exception:
            pass

    def _clear_dynamic_widgets_for_key(self, key: str, container: Optional[QWidget]) -> None:
        """Remove rebuilt SegmentBar/controls widgets while preserving the reusable spinbox."""
        if container is None:
            return
        layout = container.layout()
        if not isinstance(layout, QVBoxLayout):
            return

        spinbox = self._segment_spinboxes.get(key)
        if spinbox is not None:
            try:
                spinbox.hide()
            except Exception:
                pass
            try:
                spinbox.setParent(container)
            except Exception:
                pass

        while layout.count() > 2:
            item = layout.takeAt(2)
            widget = item.widget()
            if widget is not None:
                self._dispose_dynamic_widget(widget)

    def update_constraint_value(self, key: str, value: float):
        """Update the value of a constraint."""
        if self.path is None or not hasattr(self.path, "constraints"):
            return
        if key in NON_RANGED_CONSTRAINT_KEYS:
            # Direct flat update
            try:
                setattr(self.path.constraints, key, float(value))
            except Exception:
                setattr(self.path.constraints, key, value)
        else:
            # Update ranged constraints for this key ONLY if a single instance exists.
            # (When multiple instances exist they have dedicated spin boxes.)
            try:
                matching = [
                    rc
                    for rc in (getattr(self.path, "ranged_constraints", []) or [])
                    if getattr(rc, "key", None) == key
                ]
                if len(matching) == 1:
                    rc = matching[0]
                    try:
                        rc.value = float(value)
                    except Exception:
                        rc.value = value
                elif len(matching) > 1:
                    # Update only the FIRST instance to mirror legacy behavior (others keep own values)
                    rc0 = matching[0]
                    try:
                        rc0.value = float(value)
                    except Exception:
                        rc0.value = value
                # Always clear flat storage
                try:
                    setattr(self.path.constraints, key, None)
                except Exception:
                    pass
            except Exception:
                pass

        self.constraintValueChanged.emit(key, value)

    def get_domain_info_for_key(self, key: str) -> Tuple[str, int]:
        """Return (domain_type, count) for the given key.
        domain_type in {"translation", "rotation"}.
        """
        return get_constraint_domain_info(self.path, key)

    def create_segment_bar_for_key(
        self,
        key: str,
        control: QDoubleSpinBox,
        spin_row: QWidget,
        label_widget: QLabel,
        constraints_layout: QFormLayout,
    ) -> Optional[SegmentBar]:
        """Create or update a segment bar for a constraint key."""
        domain, count = self.get_domain_info_for_key(key)
        total = max(1, count)

        # Build / rebuild UI for ALL ranged instances of this key.
        # Gather current ranged constraints for this key, sorted by start_ordinal
        ranged_list = [
            rc for rc in (getattr(self.path, "ranged_constraints", []) or []) if rc.key == key
        ]
        if not ranged_list:
            # Nothing to build yet (should not happen if caller added constraint earlier)
            return None
        ranged_list.sort(key=lambda rc: rc.start_ordinal)
        self._segment_rc_lists[key] = ranged_list

        # Ensure container exists and wraps the original spin_row
        field_container = self._constraint_field_containers.get(key)
        if field_container is None:
            field_container = QWidget()
            vbox = QVBoxLayout(field_container)
            # Add generous insets to avoid tight edges against the background box
            vbox.setContentsMargins(8, 11, 8, 10)
            vbox.setSpacing(4)
            try:
                field_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            except Exception:
                pass
            # Move label to the top of the field container for vertical layout
            # and place the original spin row under it.
            # Replace the label cell in the form with a tiny placeholder to keep row height consistent.
            # Propagate properties used for styling
            try:
                group_name = spin_row.property("constraintGroup")
                if group_name is not None:
                    field_container.setProperty("constraintGroup", group_name)
                # Mark container as an encompassing group box; rows will be separate
                field_container.setProperty("constraintGroupContainer", "true")
            except Exception:
                pass
            self._constraint_field_containers[key] = field_container
            # Replace spin_row with container in form layout
            for i in range(constraints_layout.rowCount()):
                item = constraints_layout.itemAt(i, QFormLayoutRoles.LabelRole)
                if item and item.widget() == label_widget:
                    # Remove label from the form layout and reparent into our container
                    try:
                        constraints_layout.removeWidget(label_widget)
                    except Exception:
                        pass
                    # Remove the existing field widget, we will span across the row
                    try:
                        field_item = constraints_layout.itemAt(i, QFormLayoutRoles.FieldRole)
                        if field_item is not None and field_item.widget() is not None:
                            constraints_layout.removeWidget(field_item.widget())
                    except Exception:
                        pass
                    # Build vertical stack: label on top, then the spin row
                    label_widget.setParent(field_container)
                    try:
                        # Allow the label to elide instead of forcing horizontal scroll
                        label_widget.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
                    except Exception:
                        pass
                    vbox.addWidget(label_widget)
                    vbox.addWidget(spin_row)
                    # Add padding within the bordered base row (spinner+slider+minus)
                    try:
                        _base_layout = spin_row.layout()
                        if _base_layout is not None:
                            _base_layout.setContentsMargins(8, 8, 8, 8)
                            _base_layout.setSpacing(8)
                        spin_row.setMaximumHeight(44)
                    except Exception:
                        pass
                    # Span full row to align left edge with non-ranged combined rows
                    constraints_layout.setWidget(i, QFormLayoutRoles.SpanningRole, field_container)
                    try:
                        field_container.setVisible(True)
                    except Exception:
                        pass
                    break
        else:
            # Re-show previously hidden container and ensure it's in the layout
            try:
                field_container.setVisible(True)
            except Exception:
                pass
            try:
                present = False
                for i in range(constraints_layout.rowCount()):
                    for role in (
                        QFormLayoutRoles.SpanningRole,
                        QFormLayoutRoles.FieldRole,
                        QFormLayoutRoles.LabelRole,
                    ):
                        it = constraints_layout.itemAt(i, role)
                        if it is not None and it.widget() is field_container:
                            present = True
                            break
                    if present:
                        break
                if not present:
                    constraints_layout.addRow(field_container)
            except Exception:
                pass
        vbox: QVBoxLayout = field_container.layout()  # type: ignore

        # Clear existing dynamically added widgets (all after the first two: label and base spin_row)
        # We'll rebuild to reflect model state
        self._clear_dynamic_widgets_for_key(key, field_container)

        # Sanitize any invalid ordinals without repositioning existing ranges
        for rc in ranged_list:
            l = int(getattr(rc, "start_ordinal", 1))
            h = int(getattr(rc, "end_ordinal", total))
            l = max(1, min(l, total))
            h = max(l, min(h, total))
            rc.start_ordinal = int(l)
            rc.end_ordinal = int(h)

        # Hide the original spin_row -- we replace it with our own controls row
        spin_row.setVisible(False)

        # Create the SegmentBar widget
        from ui.sidebar.utils.constants import SPINNER_UNITS
        color = SEGMENT_COLORS.get(key, QColor("#666666"))
        bar = SegmentBar()
        bar.set_domain_size(total)
        segments = [SegmentData(rc.start_ordinal, rc.end_ordinal, rc.value, color) for rc in ranged_list]
        bar.set_segments(segments)
        unit_suffix = SPINNER_UNITS.get(key, "")
        bar.set_unit_suffix(unit_suffix)
        bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        vbox.addWidget(bar)
        self._segment_bars[key] = bar

        # Connect SegmentBar signals
        bar.segmentSelected.connect(lambda idx, k=key: self._on_segment_selected(k, idx))
        bar.segmentBoundaryDragged.connect(
            lambda seg_idx, ns, ne, k=key: self._on_segment_boundary_dragged(k, seg_idx, ns, ne)
        )
        bar.segmentMoved.connect(
            lambda seg_idx, ns, ne, k=key: self._on_segment_boundary_dragged(k, seg_idx, ns, ne)
        )
        bar.adjacentBoundaryDragged.connect(
            lambda ai, a_s, a_e, bi, b_s, b_e, k=key: self._on_adjacent_boundary_dragged(k, ai, a_s, a_e, bi, b_s, b_e)
        )
        bar.segmentBoundaryDragFinished.connect(lambda k=key: self._on_segment_boundary_drag_finished(k))
        bar.gapDoubleClicked.connect(lambda gs, ge, k=key: self._on_gap_double_clicked(k, gs, ge))
        bar.deleteRequested.connect(lambda seg_idx, k=key: self._on_segment_delete_requested(k, seg_idx))
        bar.splitRequested.connect(lambda seg_idx, k=key: self._on_segment_split_requested(k, seg_idx))

        # Create controls row: spinbox + Delete + Split
        controls_row = QWidget()
        controls_layout = QHBoxLayout(controls_row)
        controls_layout.setContentsMargins(4, 4, 4, 4)
        controls_layout.setSpacing(6)
        controls_row.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        controls_row.setMinimumHeight(32)
        controls_row.setMaximumHeight(44)

        # Style the controls row
        try:
            group_name = spin_row.property("constraintGroup")
            if group_name is not None:
                controls_row.setProperty("constraintGroup", group_name)
            controls_row.setProperty("constraintRow", "true")
        except Exception:
            pass

        # Spinbox (reuse the provided control)
        spinbox = control
        spinbox.setKeyboardTracking(False)
        try:
            spinbox.blockSignals(True)
            if ranged_list:
                spinbox.setValue(float(ranged_list[0].value))
        finally:
            spinbox.blockSignals(False)
        spinbox.setMinimumWidth(80)
        spinbox.setMaximumWidth(130)
        spinbox.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        # Reparent spinbox into controls row
        spinbox.setParent(controls_row)
        controls_layout.addWidget(spinbox)
        spinbox.show()
        self._segment_spinboxes[key] = spinbox

        # Disconnect any previous valueChanged handlers (from prior rebuilds or
        # the property editor) to avoid duplicate connections that create
        # multiple undo entries per change.
        try:
            spinbox.valueChanged.disconnect()
        except (TypeError, RuntimeError):
            pass
        # Connect spinbox value changes to update selected segment
        spinbox.valueChanged.connect(lambda v, k=key: self._on_segment_spinbox_changed(k, v))

        controls_layout.addStretch()

        # Add button (add another constraint of the same type)
        add_btn = QPushButton()
        add_btn.setIcon(QIcon(":/assets/add_icon.png"))
        add_btn.setFixedSize(24, 24)
        add_btn.setIconSize(QSize(16, 16))
        add_btn.setToolTip("Add another segment of this constraint type")
        add_btn.setStyleSheet(
            "QPushButton { border: none; } QPushButton:hover { background: #555; border-radius: 3px; }"
        )
        add_btn.clicked.connect(lambda checked=False, k=key: self._on_add_same_type_requested(k))
        controls_layout.addWidget(add_btn)

        # Delete button
        del_btn = QPushButton()
        del_btn.setIcon(QIcon(":/assets/remove_icon.png"))
        del_btn.setFixedSize(24, 24)
        del_btn.setIconSize(QSize(16, 16))
        del_btn.setToolTip("Delete selected segment")
        del_btn.setStyleSheet(
            "QPushButton { border: none; } QPushButton:hover { background: #555; border-radius: 3px; }"
        )
        del_btn.clicked.connect(lambda checked=False, k=key: self._on_segment_delete_requested(
            k, self._selected_segment_indices.get(k, -1)
        ))
        controls_layout.addWidget(del_btn)

        # Split button
        split_btn = QPushButton("Split")
        split_btn.setFixedHeight(24)
        split_btn.setToolTip("Split selected segment at midpoint")
        split_btn.setStyleSheet(
            "QPushButton { border: 1px solid #555; border-radius: 3px; padding: 2px 8px; color: #ccc; }"
            " QPushButton:hover { background: #555; }"
        )
        split_btn.clicked.connect(lambda checked=False, k=key: self._on_segment_split_requested(
            k, self._selected_segment_indices.get(k, -1)
        ))
        controls_layout.addWidget(split_btn)

        # Pop-out button
        popout_btn = QPushButton("\u2197")  # ↗ arrow
        popout_btn.setFixedSize(24, 24)
        popout_btn.setToolTip("Open in pop-out window")
        popout_btn.setStyleSheet(
            "QPushButton { border: 1px solid #555; border-radius: 3px; font-size: 14px; color: #ccc; }"
            " QPushButton:hover { background: #555; }"
        )
        popout_btn.clicked.connect(lambda checked=False: self.open_popout())
        controls_layout.addWidget(popout_btn)

        vbox.addWidget(controls_row)

        try:
            field_container.updateGeometry()
        except Exception:
            pass  # widget may be destroyed

        # Make label clickable to show preview of first segment
        label_widget.setStyleSheet(
            label_widget.styleSheet() + " QLabel:hover { text-decoration: underline; }"
        )
        label_widget.setCursor(QCursor(Qt.PointingHandCursor))

        class LabelClickFilter(QObject):
            def __init__(self, callback):
                super().__init__()
                self.callback = callback

            def eventFilter(self, obj, event):
                if event.type() == QEvent.MouseButtonPress:
                    if isinstance(event, QMouseEvent) and event.button() == Qt.LeftButton:
                        self.callback()
                        return True
                return False

        def _show_first_preview():
            rc_list = self._segment_rc_lists.get(key, [])
            if rc_list:
                rc = rc_list[0]
                self._active_preview_key = key
                self.constraintRangePreviewRequested.emit(key, rc.start_ordinal, rc.end_ordinal)

        old_filter = getattr(self, "_label_filters", {}).get(key) if hasattr(self, "_label_filters") else None
        if old_filter is not None:
            try:
                label_widget.removeEventFilter(old_filter)
            except Exception:
                pass

        label_filter = LabelClickFilter(_show_first_preview)
        label_widget.installEventFilter(label_filter)
        if not hasattr(self, "_label_filters"):
            self._label_filters = {}
        self._label_filters[key] = label_filter

        # Auto-select first segment (no preview — bar creation is programmatic)
        if ranged_list:
            bar.blockSignals(True)
            bar.set_selected_index(0)
            bar.blockSignals(False)
            self._on_segment_selected(key, 0, emit_preview=False)

        return bar

    # ------------------------------------------------------------------
    # Segment bar signal handlers
    # ------------------------------------------------------------------

    def _on_segment_selected(self, key: str, segment_index: int, emit_preview: bool = True):
        """Handle segment selection in the bar."""
        self._selected_segment_indices[key] = segment_index
        if key in self._segment_rc_lists and 0 <= segment_index < len(self._segment_rc_lists[key]):
            rc = self._segment_rc_lists[key][segment_index]
            # Update spinbox value (without triggering signals)
            spinbox = self._segment_spinboxes.get(key)
            if spinbox:
                spinbox.blockSignals(True)
                spinbox.setValue(rc.value)
                spinbox.blockSignals(False)
                spinbox.setEnabled(True)
            # Emit preview for canvas overlay — only on explicit user clicks, not programmatic rebuilds
            if emit_preview:
                try:
                    self._active_preview_key = key
                    self.constraintRangePreviewRequested.emit(key, rc.start_ordinal, rc.end_ordinal)
                except Exception:
                    traceback.print_exc()
        else:
            # No segment selected — disable and zero out spinbox
            spinbox = self._segment_spinboxes.get(key)
            if spinbox:
                spinbox.blockSignals(True)
                spinbox.setValue(0)
                spinbox.blockSignals(False)
                spinbox.setEnabled(False)
        # Sync selection to popout (silent — no signal cascade)
        if self._popout_dialog is not None:
            try:
                self._popout_dialog.sync_selection(key, segment_index)
            except Exception:
                pass

    def _on_segment_boundary_dragged(self, key: str, seg_idx: int, new_start: int, new_end: int):
        """Handle live boundary or segment drag."""
        if not self._boundary_drag_started:
            self._boundary_drag_started = True
            # Refresh references — the undo system may have replaced
            # path.ranged_constraints with deepcopy clones since the bar
            # was last built, making _segment_rc_lists stale.
            ranged_list = [
                rc for rc in (self.path.ranged_constraints or []) if rc.key == key
            ]
            ranged_list.sort(key=lambda rc: rc.start_ordinal)
            self._segment_rc_lists[key] = ranged_list
            try:
                self.aboutToChange.emit("Edit constraint range")
            except Exception:
                traceback.print_exc()

        rc_list = self._segment_rc_lists.get(key, [])
        if 0 <= seg_idx < len(rc_list):
            rc = rc_list[seg_idx]
            rc.start_ordinal = new_start
            rc.end_ordinal = new_end
            try:
                self.constraintRangePreviewRequested.emit(key, new_start, new_end)
            except Exception:
                traceback.print_exc()

    def _on_adjacent_boundary_dragged(self, key: str, a_idx: int, a_start: int, a_end: int, b_idx: int, b_start: int, b_end: int):
        """Handle dragging a shared boundary between two adjacent segments."""
        if not self._boundary_drag_started:
            self._boundary_drag_started = True
            ranged_list = [
                rc for rc in (self.path.ranged_constraints or []) if rc.key == key
            ]
            ranged_list.sort(key=lambda rc: rc.start_ordinal)
            self._segment_rc_lists[key] = ranged_list
            try:
                self.aboutToChange.emit("Edit constraint range")
            except Exception:
                traceback.print_exc()

        rc_list = self._segment_rc_lists.get(key, [])
        if 0 <= a_idx < len(rc_list):
            rc_list[a_idx].start_ordinal = a_start
            rc_list[a_idx].end_ordinal = a_end
        if 0 <= b_idx < len(rc_list):
            rc_list[b_idx].start_ordinal = b_start
            rc_list[b_idx].end_ordinal = b_end

    def _on_segment_boundary_drag_finished(self, key: str):
        """Commit boundary drag."""
        self._boundary_drag_started = False
        try:
            self.constraintRangeChanged.emit(key, 0, 0)  # trigger sim rebuild
        except Exception:
            traceback.print_exc()
        self._sync_popout()
        self._commit_and_resync("Edit constraint range")

    def _on_add_same_type_requested(self, key: str):
        """Add another ranged constraint of the same type via the + button."""
        try:
            self.aboutToChange.emit("Add constraint range")
        except Exception:
            traceback.print_exc()
        self.add_constraint(key)
        self._rebuild_segment_bar_for_key(key)
        self._sync_popout(full_rebuild=True)
        self._commit_and_resync("Add constraint range")

    def _on_gap_double_clicked(self, key: str, gap_start: int, gap_end: int):
        """Create new constraint in gap."""
        try:
            self.aboutToChange.emit("Add constraint range")
        except Exception:
            traceback.print_exc()

        default_val = self.get_default_value(key)

        rc = RangedConstraint(key=key, value=default_val, start_ordinal=gap_start, end_ordinal=gap_end)
        if self.path.ranged_constraints is None:
            self.path.ranged_constraints = []
        self.path.ranged_constraints.append(rc)

        self._rebuild_segment_bar_for_key(key)
        self._sync_popout(full_rebuild=True)
        self._commit_and_resync("Add constraint range")

    def _on_segment_delete_requested(self, key: str, seg_idx: int):
        """Delete a constraint segment."""
        rc_list = self._segment_rc_lists.get(key, [])
        if 0 <= seg_idx < len(rc_list):
            rc = rc_list[seg_idx]
            try:
                self.aboutToChange.emit("Delete constraint range")
            except Exception:
                traceback.print_exc()

            # Remove by identity, not equality
            self.path.ranged_constraints = [r for r in self.path.ranged_constraints if r is not rc]

            # Check if any instances remain
            remaining = [r for r in self.path.ranged_constraints if r.key == key]
            if not remaining:
                self._remove_container_for_key(key)
                self.constraintRemoved.emit(key)
            else:
                self._rebuild_segment_bar_for_key(key)
            self._sync_popout(full_rebuild=True)
            self._commit_and_resync("Delete constraint range")

    def _on_segment_split_requested(self, key: str, seg_idx: int):
        """Split a segment at its midpoint."""
        rc_list = self._segment_rc_lists.get(key, [])
        if 0 <= seg_idx < len(rc_list):
            rc = rc_list[seg_idx]
            if rc.end_ordinal - rc.start_ordinal < 1:
                return  # can't split single-element segment

            try:
                self.aboutToChange.emit("Split constraint range")
            except Exception:
                traceback.print_exc()

            if split_ranged_constraint_instance(self.path.ranged_constraints, rc) is None:
                return

            self._rebuild_segment_bar_for_key(key)
            self._sync_popout(full_rebuild=True)
            self._commit_and_resync("Split constraint range")

    def _on_segment_spinbox_changed(self, key: str, value: float):
        """Handle spinbox value change for the selected segment."""
        idx = self._selected_segment_indices.get(key, -1)
        rc_list = self._segment_rc_lists.get(key, [])
        if 0 <= idx < len(rc_list):
            try:
                self.aboutToChange.emit("Edit constraint value")
            except Exception:
                traceback.print_exc()
            rc_list[idx].value = value
            self._rebuild_segment_bar_for_key(key)
            self._sync_popout()
            self.constraintValueChanged.emit(key, value)
            self._commit_and_resync("Edit constraint value")

    def _commit_and_resync(self, description: str):
        """Emit userActionOccurred and schedule a deferred resync.

        The undo system creates a deferred command (QTimer.singleShot(0, ...))
        whose execute() replaces ranged_constraints with deepcopy clones.
        This invalidates our _segment_rc_lists references.  Schedule a resync
        at 0ms (FIFO after the undo command) to pick up the new objects.
        """
        try:
            self.userActionOccurred.emit(description)
        except Exception:
            traceback.print_exc()
        QTimer.singleShot(0, self._deferred_resync_after_undo)

    # ------------------------------------------------------------------
    # Segment bar rebuild helper
    # ------------------------------------------------------------------

    def _rebuild_segment_bar_for_key(self, key: str):
        """Refresh the segment bar for a key from current model state."""
        bar = self._segment_bars.get(key)
        if bar is None:
            return

        ranged_list = [rc for rc in (self.path.ranged_constraints or []) if rc.key == key]
        ranged_list.sort(key=lambda rc: rc.start_ordinal)
        self._segment_rc_lists[key] = ranged_list

        color = SEGMENT_COLORS.get(key, QColor("#666666"))
        segments = [SegmentData(rc.start_ordinal, rc.end_ordinal, rc.value, color) for rc in ranged_list]
        bar.set_segments(segments)

        # Update domain size in case it changed
        domain, count = self.get_domain_info_for_key(key)
        bar.set_domain_size(max(1, count))

        # Re-select if possible (no preview emit — rebuilds are programmatic, not user clicks)
        prev_idx = self._selected_segment_indices.get(key, 0)
        if ranged_list:
            new_idx = min(prev_idx, len(ranged_list) - 1)
            bar.blockSignals(True)
            bar.set_selected_index(new_idx)
            bar.blockSignals(False)
            self._on_segment_selected(key, new_idx, emit_preview=False)
        else:
            bar.set_selected_index(-1)

    # ------------------------------------------------------------------
    # Segment bar lifecycle
    # ------------------------------------------------------------------

    def clear_segment_bars(self):
        """Remove all segment bars and their state."""
        for key, container in list(self._constraint_field_containers.items()):
            try:
                self._clear_dynamic_widgets_for_key(key, container)
            except Exception:
                pass
            try:
                if container is not None:
                    container.setVisible(False)
            except Exception:
                pass  # widget may be destroyed
        self._segment_bars.clear()
        self._segment_spinboxes.clear()
        self._segment_rc_lists.clear()
        self._selected_segment_indices.clear()

    # ------------------------------------------------------------------
    # Popout dialog
    # ------------------------------------------------------------------

    def open_popout(self):
        """Open or raise the constraint popout dialog."""
        if self.path is None:
            return
        from ui.sidebar.dialogs.constraint_popout import ConstraintPopout

        # Rebuild sidebar bars from model to ensure they reflect current state
        for key in list(self._segment_bars.keys()):
            try:
                self._rebuild_segment_bar_for_key(key)
            except Exception:
                pass

        if self._popout_dialog is not None:
            try:
                self._popout_dialog.set_path(self.path)
                for key, idx in self._selected_segment_indices.items():
                    if idx >= 0:
                        self._popout_dialog.sync_selection(key, idx)
                self._popout_dialog.show()
                self._popout_dialog.raise_()
                self._popout_dialog.activateWindow()
                return
            except Exception:
                self._popout_dialog = None

        self._popout_dialog = ConstraintPopout(self.path)
        self._popout_dialog.closed.connect(self._on_popout_closed)
        self._popout_dialog.aboutToChange.connect(
            lambda: self.aboutToChange.emit("Edit constraint (popout)")
        )
        self._popout_dialog.modelChanged.connect(self._on_popout_model_changed)
        self._popout_dialog.segmentSelectedInPopout.connect(self._on_popout_segment_selected)
        self._popout_dialog.undoRequested.connect(self.undoRequested)
        self._popout_dialog.redoRequested.connect(self.redoRequested)
        for key, idx in self._selected_segment_indices.items():
            if idx >= 0:
                self._popout_dialog.sync_selection(key, idx)
        self._popout_dialog.show()
        self.popoutOpened.emit()

    def _sync_popout(self, full_rebuild=False):
        """Sync the popout dialog to reflect sidebar model changes.

        Args:
            full_rebuild: If True, destroy and recreate all widgets (for structural
                changes like add/remove/split).  If False, do a lightweight data
                refresh that preserves widgets and user focus.
        """
        if self._popout_dialog is not None:
            try:
                if full_rebuild:
                    self._popout_dialog.rebuild()
                else:
                    self._popout_dialog.refresh_data()
            except Exception:
                pass

    def _on_popout_closed(self):
        """Handle popout dialog closing."""
        self._popout_dialog = None
        self.popoutClosed.emit()

    def _on_popout_model_changed(self):
        """Handle model changes from the popout dialog."""
        # Rebuild sidebar segment bars to reflect popout edits
        for key in list(self._segment_bars.keys()):
            try:
                self._rebuild_segment_bar_for_key(key)
            except Exception:
                traceback.print_exc()
        # Trigger canvas/sim refresh — the undo system's first-execute callback is
        # suppressed for "Edit …" descriptions, so this is the only refresh path.
        try:
            self.constraintRangeChanged.emit("", 0, 0)
        except Exception:
            pass
        # Complete the undo snapshot (aboutToChange was emitted by the popout BEFORE mutation)
        try:
            self.userActionOccurred.emit("Edit constraint (popout)")
        except Exception:
            pass
        # The undo system creates a deferred command (QTimer.singleShot(0, ...))
        # whose execute() replaces ranged_constraints with deepcopy clones,
        # breaking the popout's object references.  Schedule a resync at 0ms too;
        # Qt processes same-timeout timers FIFO, so the undo command (registered
        # first via userActionOccurred) fires before this resync.
        QTimer.singleShot(0, self._deferred_resync_after_undo)

    def _deferred_resync_after_undo(self):
        """Rebuild sidebar bars and popout after the undo system replaces objects."""
        for key in list(self._segment_bars.keys()):
            try:
                self._rebuild_segment_bar_for_key(key)
            except Exception:
                pass
        self._sync_popout()

    def _on_popout_segment_selected(self, key: str, segment_index: int):
        """Handle segment selection in the popout -- sync sidebar and emit highlight."""
        rc_list = [
            rc for rc in (self.path.ranged_constraints or []) if rc.key == key
        ]
        rc_list.sort(key=lambda rc: rc.start_ordinal)
        if 0 <= segment_index < len(rc_list):
            rc = rc_list[segment_index]
            self.popoutSegmentSelected.emit(key, rc.start_ordinal, rc.end_ordinal)
            # Also show the green range overlay on the canvas
            self._active_preview_key = key
            self.constraintRangePreviewRequested.emit(key, rc.start_ordinal, rc.end_ordinal)
        # Sync sidebar bar and spinbox selection (silent — no signal cascade)
        self._selected_segment_indices[key] = segment_index
        bar = self._segment_bars.get(key)
        if bar is not None:
            bar.blockSignals(True)
            bar.set_selected_index(segment_index)
            bar.blockSignals(False)
        spinbox = self._segment_spinboxes.get(key)
        if spinbox is not None and 0 <= segment_index < len(rc_list):
            spinbox.blockSignals(True)
            spinbox.setValue(rc_list[segment_index].value)
            spinbox.blockSignals(False)
            spinbox.setEnabled(True)

    def handle_canvas_element_clicked(self, global_index: int):
        """Handle a canvas element click while popout is active.

        Finds which constraint segment contains the clicked element and
        selects it in the popout dialog.
        """
        if self._popout_dialog is None or self.path is None:
            return
        if global_index < 0 or global_index >= len(self.path.path_elements):
            return

        from models.path_model import (
            TranslationTarget,
            Waypoint,
            RotationTarget,
            EventTrigger,
        )

        element = self.path.path_elements[global_index]

        # For each active key in the popout, figure out the ordinal
        for key, row in self._popout_dialog._rows.items():
            if key in TRANSLATION_CONSTRAINT_KEYS:
                domain_types = (TranslationTarget, Waypoint)
            else:
                domain_types = (Waypoint, RotationTarget, EventTrigger)

            if not isinstance(element, domain_types):
                continue

            # Calculate the ordinal for this element in the domain
            ordinal = 0
            for i, elem in enumerate(self.path.path_elements):
                if isinstance(elem, domain_types):
                    ordinal += 1
                    if i == global_index:
                        break

            if ordinal == 0:
                continue

            # Find the segment containing this ordinal
            self._popout_dialog.highlight_ordinals(key, [ordinal])

    def set_active_preview_key(self, key: str):
        """Set the active constraint preview key and emit preview signal."""
        rc_list = self._segment_rc_lists.get(key, [])
        idx = self._selected_segment_indices.get(key, 0)
        if rc_list:
            if idx < 0 or idx >= len(rc_list):
                idx = 0
            rc = rc_list[idx]
            self._active_preview_key = key
            self.constraintRangePreviewRequested.emit(key, rc.start_ordinal, rc.end_ordinal)

    def refresh_active_preview(self):
        """Refresh the preview for the currently active constraint key."""
        if self._active_preview_key is not None:
            rc_list = self._segment_rc_lists.get(self._active_preview_key, [])
            idx = self._selected_segment_indices.get(self._active_preview_key, 0)
            if rc_list:
                if idx < 0 or idx >= len(rc_list):
                    idx = 0
                rc = rc_list[idx]
                self.constraintRangePreviewRequested.emit(
                    self._active_preview_key, rc.start_ordinal, rc.end_ordinal
                )

    def clear_active_preview(self):
        """Clear the active preview."""
        self._active_preview_key = None
        self.constraintRangePreviewCleared.emit()

    def is_widget_range_related(self, widget: QWidget) -> bool:
        """Return True if the clicked widget is inside a constraint segment bar/spinner area."""
        if widget is None:
            return False

        # Check segment bars
        for _key, bar in self._segment_bars.items():
            try:
                if bar is widget:
                    return True
                if hasattr(bar, "isAncestorOf") and bar.isAncestorOf(widget):
                    return True
            except Exception:
                pass  # widget may be destroyed

        # Check field containers
        for _key, container in self._constraint_field_containers.items():
            if container is None:
                continue
            try:
                if container is widget:
                    return True
                if hasattr(container, "isAncestorOf") and container.isAncestorOf(widget):
                    return True
            except Exception:
                pass  # widget may be destroyed

        # Check spinboxes and their child widgets
        for _key, spin in self._segment_spinboxes.items():
            try:
                if spin is widget:
                    return True
                if hasattr(spin, "isAncestorOf") and spin.isAncestorOf(widget):
                    return True
            except Exception:
                continue  # widget may be destroyed

        return False

    def can_add_more_instances(self, key: str) -> bool:
        """Return True if another ranged instance can be added for this key (i.e., below max).
        Max equals the number of domain elements (total).
        """
        if self.path is None:
            return False
        if key in NON_RANGED_CONSTRAINT_KEYS:
            return False
        try:
            _domain, count = self.get_domain_info_for_key(key)
            total = int(count) if int(count) > 0 else 1
            existing = [
                rc
                for rc in (getattr(self.path, "ranged_constraints", []) or [])
                if getattr(rc, "key", None) == key
            ]
            # Compute occupied units and whether a split is feasible
            occupied_units = set()
            largest_len = 0
            for rc in existing:
                try:
                    l = int(getattr(rc, "start_ordinal", 1))
                    h = int(getattr(rc, "end_ordinal", total))
                    l = max(1, min(l, total))
                    h = max(1, min(h, total))
                    if h < l:
                        h = l
                    for u in range(int(l), int(h) + 1):
                        occupied_units.add(int(u))
                    largest_len = max(largest_len, int(h - l + 1))
                except Exception:
                    continue
            if len(occupied_units) < total:
                return True
            # If fully occupied but there exists a range of length >= 2, we can split
            return largest_len >= 2
        except Exception:
            return False

    def get_constraint_value(self, key: str) -> Optional[float]:
        """Get the current value of a constraint."""
        if self.path is None or not hasattr(self.path, "constraints"):
            return None

        # Check ranged constraints first
        try:
            for rc in getattr(self.path, "ranged_constraints", []) or []:
                if getattr(rc, "key", None) == key:
                    return float(getattr(rc, "value", None))
        except Exception:
            pass

        # Check flat constraint
        try:
            val = getattr(self.path.constraints, key, None)
            if val is not None:
                return float(val)
        except Exception:
            pass

        return None

    def has_constraint(self, key: str) -> bool:
        """Check if a constraint is present."""
        if self.path is None:
            return False

        # Check ranged constraints
        try:
            if any(
                getattr(rc, "key", None) == key
                for rc in (getattr(self.path, "ranged_constraints", []) or [])
            ):
                return True
        except Exception:
            pass

        # Check flat constraint
        try:
            if (
                hasattr(self.path, "constraints")
                and getattr(self.path.constraints, key, None) is not None
            ):
                return True
        except Exception:
            pass

        return False
