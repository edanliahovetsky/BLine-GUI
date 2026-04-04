"""Pop-out dialog for editing ranged constraints with full-width segment bars."""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple, cast

from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QToolTip,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import Signal
from PySide6.QtGui import QColor, QCursor, QKeySequence

from ui.qt_compat import Qt
from ui.sidebar.widgets.segment_bar import SEGMENT_COLORS, SegmentBar, SegmentData
from ui.sidebar.utils.constants import (
    SPINNER_METADATA,
    RANGED_CONSTRAINT_KEYS,
    TRANSLATION_CONSTRAINT_KEYS,
    constraint_default_value,
)
from models.ranged_constraint_ops import (
    append_ranged_constraint_instance,
    split_ranged_constraint_instance,
)


class ConstraintPopout(QWidget):
    """Floating tool window with wider segment bars for all constraint types."""

    closed = Signal()
    segmentSelectedInPopout = Signal(str, int)  # key, segment_index
    aboutToChange = Signal()  # emitted BEFORE model mutation for undo snapshots
    modelChanged = Signal()
    undoRequested = Signal()
    redoRequested = Signal()

    def __init__(self, path, parent=None):
        super().__init__(parent, Qt.Tool | Qt.WindowStaysOnTopHint)

        self.setWindowTitle("Constraint Editor")
        self.resize(600, 400)
        self.setMinimumWidth(400)
        self.setMinimumHeight(200)

        self._path = path
        self._drag_started: bool = False

        # Per-key UI state: { key: { "bar", "spinbox", "ranged_list", "selected_idx" } }
        self._rows: Dict[str, dict] = {}

        self.setStyleSheet(
            "QWidget { background: #242424; color: #f0f0f0; }"
            "QLabel { background: transparent; }"
            "QPushButton { background: #3a3a3a; border: 1px solid #555555;"
            "  border-radius: 3px; padding: 3px 8px; color: #f0f0f0; }"
            "QPushButton:hover { background: #4a4a4a; }"
            "QDoubleSpinBox { background: #3a3a3a; border: 1px solid #555555;"
            "  border-radius: 3px; padding: 2px 4px; color: #f0f0f0; }"
            "QScrollArea { border: none; }"
        )

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(6, 6, 6, 6)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        main_layout.addWidget(scroll)

        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(4, 4, 4, 4)
        self._content_layout.setSpacing(12)
        scroll.setWidget(self._content)

        self.rebuild()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_path(self, path) -> None:
        """Update path reference and rebuild."""
        self._path = path
        self.rebuild()

    def rebuild(self) -> None:
        """Clear and rebuild all constraint rows from the path model."""
        # Clear existing widgets
        self._rows.clear()
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        if self._path is None:
            return

        present_keys = self._present_keys()

        if not present_keys:
            placeholder = QLabel("No ranged constraints defined.")
            placeholder.setAlignment(Qt.AlignCenter)
            self._content_layout.addWidget(placeholder)
            self._content_layout.addStretch()
            return

        for key in present_keys:
            self._add_constraint_row(key)

        self._content_layout.addStretch()

    def refresh_data(self) -> None:
        """Re-read model state and update bars/spinboxes without destroying widgets.

        Use this instead of rebuild() when only values or boundary positions changed
        (not the number of constraints or which keys are present).
        """
        if self._path is None:
            return

        if self._present_keys() != list(self._rows):
            self.rebuild()
            return

        for key, row in self._rows.items():
            segments, ranged_list = self._build_segments_for_key(key)
            row["ranged_list"] = ranged_list

            bar: SegmentBar = row["bar"]
            bar.set_segments(segments)

            # Update domain size in case elements changed
            domain_elements = self._get_domain_elements(key)
            bar.set_domain_size(len(domain_elements))
            row["domain_size"] = len(domain_elements)
            bar.set_element_labels(self._get_element_labels(key))

            # Re-select current segment if still valid, update spinbox
            idx = row["selected_idx"]
            spinbox: QDoubleSpinBox = row["spinbox"]
            if 0 <= idx < len(ranged_list):
                spinbox.blockSignals(True)
                spinbox.setValue(ranged_list[idx].value)
                spinbox.blockSignals(False)
                spinbox.setEnabled(True)
                bar.blockSignals(True)
                bar.set_selected_index(idx)
                bar.blockSignals(False)
            elif ranged_list:
                new_idx = len(ranged_list) - 1
                row["selected_idx"] = new_idx
                bar.blockSignals(True)
                bar.set_selected_index(new_idx)
                bar.blockSignals(False)
                spinbox.blockSignals(True)
                spinbox.setValue(ranged_list[new_idx].value)
                spinbox.blockSignals(False)
                spinbox.setEnabled(True)
            else:
                row["selected_idx"] = -1
                spinbox.blockSignals(True)
                spinbox.setValue(0)
                spinbox.blockSignals(False)
                spinbox.setEnabled(False)

    def select_segment_for_key(self, key: str, segment_index: int) -> None:
        """Select a segment in the bar for the given key."""
        row = self._rows.get(key)
        if row is None:
            return
        bar: SegmentBar = row["bar"]
        bar.set_selected_index(segment_index)

    def highlight_ordinals(self, key: str, ordinals: List[int]) -> None:
        """Highlight specific ordinals (for canvas selection sync).

        Currently selects the first segment that contains any of the ordinals.
        """
        row = self._rows.get(key)
        if row is None:
            return
        bar: SegmentBar = row["bar"]
        ranged_list = row["ranged_list"]
        for i, rc in enumerate(ranged_list):
            for o in ordinals:
                if rc.start_ordinal <= o <= rc.end_ordinal:
                    bar.set_selected_index(i)
                    return

    # ------------------------------------------------------------------
    # Close event
    # ------------------------------------------------------------------

    def sync_selection(self, key: str, segment_index: int) -> None:
        """Silently sync selection from sidebar without emitting signals."""
        row = self._rows.get(key)
        if row is None:
            return
        row["selected_idx"] = segment_index
        bar: SegmentBar = row["bar"]
        bar.blockSignals(True)
        bar.set_selected_index(segment_index)
        bar.blockSignals(False)
        spinbox: QDoubleSpinBox = row["spinbox"]
        ranged_list = row["ranged_list"]
        if 0 <= segment_index < len(ranged_list):
            spinbox.blockSignals(True)
            spinbox.setValue(ranged_list[segment_index].value)
            spinbox.blockSignals(False)
            spinbox.setEnabled(True)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.matches(QKeySequence.StandardKey.Undo):
            self.undoRequested.emit()
            event.accept()
            return
        if event.matches(QKeySequence.StandardKey.Redo):
            self.redoRequested.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._drag_started:
            self._drag_started = False
            self.modelChanged.emit()
        self.closed.emit()
        super().closeEvent(event)

    # ------------------------------------------------------------------
    # Domain helpers
    # ------------------------------------------------------------------

    def _get_domain_elements(self, key: str) -> list:
        """Get the domain elements for a constraint key."""
        from models.path_model import (
            EventTrigger,
            RotationTarget,
            TranslationTarget,
            Waypoint,
        )

        if key in TRANSLATION_CONSTRAINT_KEYS:
            return [
                e
                for e in self._path.path_elements
                if isinstance(e, (TranslationTarget, Waypoint))
            ]
        else:
            return [
                e
                for e in self._path.path_elements
                if isinstance(e, (Waypoint, RotationTarget, EventTrigger))
            ]

    def _get_element_labels(self, key: str) -> List[str]:
        """Build brief element labels like T1, W2, R1, E1."""
        from models.path_model import (
            EventTrigger,
            RotationTarget,
            TranslationTarget,
            Waypoint,
        )

        elements = self._get_domain_elements(key)
        counters: Dict[type[object], int] = {}
        labels: List[str] = []
        prefix_map: Dict[type[object], str] = {
            TranslationTarget: "T",
            Waypoint: "W",
            RotationTarget: "R",
            EventTrigger: "E",
        }
        for e in elements:
            t = type(e)
            counters[t] = counters.get(t, 0) + 1
            prefix = prefix_map.get(t, "?")
            labels.append(f"{prefix}{counters[t]}")
        return labels

    def _build_segments_for_key(
        self, key: str
    ) -> Tuple[List[SegmentData], list]:
        """Build SegmentData list and sorted ranged constraint list for a key."""
        from models.path_model import RangedConstraint  # noqa: F811

        ranged: List[RangedConstraint] = [
            rc for rc in (self._path.ranged_constraints or []) if rc.key == key
        ]
        ranged.sort(key=lambda rc: rc.start_ordinal)
        color = SEGMENT_COLORS.get(key, QColor("#666666"))
        segments = [
            SegmentData(rc.start_ordinal, rc.end_ordinal, rc.value, color)
            for rc in ranged
        ]
        return segments, ranged

    # ------------------------------------------------------------------
    # Row building
    # ------------------------------------------------------------------

    def _add_constraint_row(self, key: str) -> None:
        """Build and add a single constraint row to the content layout."""
        meta = SPINNER_METADATA.get(key, {})
        label_text = str(meta.get("label", key)).replace("<br/>", " ")

        domain_elements = self._get_domain_elements(key)
        domain_size = len(domain_elements)
        element_labels = self._get_element_labels(key)
        segments, ranged_list = self._build_segments_for_key(key)

        # --- Container ---
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(6, 6, 6, 6)
        container_layout.setSpacing(4)
        container.setStyleSheet(
            "QWidget#constraintContainer { border: 1px solid #444444;"
            "  border-radius: 4px; background: #2a2a2a; }"
        )
        container.setObjectName("constraintContainer")

        # --- Header ---
        header = QLabel(f"<b>{label_text}</b>")
        container_layout.addWidget(header)

        # --- Segment Bar ---
        bar = SegmentBar()
        bar.set_domain_size(domain_size)
        bar.set_segments(segments)
        bar.set_element_labels(element_labels)
        bar.set_show_labels(True)

        # Extract unit suffix for bar value display
        unit = self._unit_for_key(key)
        bar.set_unit_suffix(unit)

        container_layout.addWidget(bar)

        # --- Controls row ---
        controls = QHBoxLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(6)

        value_label = QLabel("Value:")
        controls.addWidget(value_label)

        spinbox = QDoubleSpinBox()
        rng = cast(tuple[float, float], meta.get("range", (0.0, 99999.0)))
        step_value = meta.get("step", 0.1)
        step = float(step_value) if isinstance(step_value, (int, float)) else 0.1
        spinbox.setMinimum(rng[0])
        spinbox.setMaximum(rng[1])
        spinbox.setSingleStep(step)
        spinbox.setDecimals(self._decimals_for_key(key))
        spinbox.setSuffix(unit)
        spinbox.setEnabled(False)
        spinbox.setKeyboardTracking(False)
        spinbox.setFixedWidth(120)
        controls.addWidget(spinbox)

        controls.addStretch()

        btn_delete = QPushButton("Delete")
        btn_split = QPushButton("Split")
        btn_add = QPushButton("Add")
        controls.addWidget(btn_delete)
        controls.addWidget(btn_split)
        controls.addWidget(btn_add)

        container_layout.addLayout(controls)
        self._content_layout.addWidget(container)

        # --- Store row state ---
        row_state = {
            "bar": bar,
            "spinbox": spinbox,
            "ranged_list": ranged_list,
            "selected_idx": -1,
            "domain_size": domain_size,
            "btn_delete": btn_delete,
            "btn_split": btn_split,
            "btn_add": btn_add,
        }
        self._rows[key] = row_state

        # --- Connect signals ---
        bar.segmentSelected.connect(lambda idx, k=key: self._on_segment_selected(k, idx))
        bar.segmentBoundaryDragged.connect(
            lambda idx, s, e, k=key: self._on_boundary_dragged(k, idx, s, e)
        )
        bar.segmentBoundaryDragFinished.connect(
            lambda k=key: self._on_boundary_drag_finished(k)
        )
        bar.segmentMoved.connect(
            lambda idx, s, e, k=key: self._on_segment_moved(k, idx, s, e)
        )
        bar.adjacentBoundaryDragged.connect(
            lambda a_idx, a_s, a_e, b_idx, b_s, b_e, k=key: self._on_adjacent_boundary_dragged(
                k, a_idx, a_s, a_e, b_idx, b_s, b_e
            )
        )
        bar.gapDoubleClicked.connect(
            lambda s, e, k=key: self._on_gap_double_clicked(k, s, e)
        )
        bar.deleteRequested.connect(lambda idx, k=key: self._on_delete(k, idx))
        bar.splitRequested.connect(lambda idx, k=key: self._on_split(k, idx))

        spinbox.valueChanged.connect(lambda val, k=key: self._on_spinbox_changed(k, val))

        btn_delete.clicked.connect(lambda _=False, k=key: self._on_delete_button(k))
        btn_split.clicked.connect(lambda _=False, k=key: self._on_split_button(k))
        btn_add.clicked.connect(lambda _=False, k=key: self._on_add_button(k))

        # Auto-select first segment so spinbox is usable after rebuild
        if ranged_list:
            bar.blockSignals(True)
            bar.set_selected_index(0)
            bar.blockSignals(False)
            self._on_segment_selected(key, 0)

    # ------------------------------------------------------------------
    # Signal handlers
    # ------------------------------------------------------------------

    def _on_segment_selected(self, key: str, idx: int) -> None:
        row = self._rows.get(key)
        if row is None:
            return
        row["selected_idx"] = idx
        spinbox: QDoubleSpinBox = row["spinbox"]
        ranged_list = row["ranged_list"]
        if 0 <= idx < len(ranged_list):
            spinbox.setEnabled(True)
            spinbox.blockSignals(True)
            spinbox.setValue(ranged_list[idx].value)
            spinbox.blockSignals(False)
        else:
            spinbox.blockSignals(True)
            spinbox.setValue(0)
            spinbox.blockSignals(False)
            spinbox.setEnabled(False)
        self.segmentSelectedInPopout.emit(key, idx)

    def _on_boundary_dragged(self, key: str, idx: int, start: int, end: int) -> None:
        if not self._drag_started:
            self._drag_started = True
            self.aboutToChange.emit()
        row = self._rows.get(key)
        if row is None:
            return
        ranged_list = row["ranged_list"]
        if 0 <= idx < len(ranged_list):
            rc = ranged_list[idx]
            rc.start_ordinal = start
            rc.end_ordinal = end

    def _on_segment_moved(self, key: str, idx: int, start: int, end: int) -> None:
        if not self._drag_started:
            self._drag_started = True
            self.aboutToChange.emit()
        row = self._rows.get(key)
        if row is None:
            return
        ranged_list = row["ranged_list"]
        if 0 <= idx < len(ranged_list):
            rc = ranged_list[idx]
            rc.start_ordinal = start
            rc.end_ordinal = end
            # No modelChanged here — _on_boundary_drag_finished handles commit on mouse release

    def _on_adjacent_boundary_dragged(
        self, key: str, a_idx: int, a_s: int, a_e: int, b_idx: int, b_s: int, b_e: int
    ) -> None:
        if not self._drag_started:
            self._drag_started = True
            self.aboutToChange.emit()
        row = self._rows.get(key)
        if row is None:
            return
        ranged_list = row["ranged_list"]
        if 0 <= a_idx < len(ranged_list):
            ranged_list[a_idx].start_ordinal = a_s
            ranged_list[a_idx].end_ordinal = a_e
        if 0 <= b_idx < len(ranged_list):
            ranged_list[b_idx].start_ordinal = b_s
            ranged_list[b_idx].end_ordinal = b_e

    def _on_boundary_drag_finished(self, key: str) -> None:
        self._drag_started = False
        self.modelChanged.emit()

    def _on_gap_double_clicked(self, key: str, start: int, end: int) -> None:
        self._create_constraint(key, start, end)

    def _on_delete(self, key: str, idx: int) -> None:
        row = self._rows.get(key)
        if row is None:
            return
        ranged_list = row["ranged_list"]
        if 0 <= idx < len(ranged_list):
            self.aboutToChange.emit()
            rc = ranged_list[idx]
            self._path.ranged_constraints.remove(rc)
            self.rebuild()
            self.modelChanged.emit()

    def _on_split(self, key: str, idx: int) -> None:
        row = self._rows.get(key)
        if row is None:
            return
        ranged_list = row["ranged_list"]
        if 0 <= idx < len(ranged_list):
            self._split_constraint(key, ranged_list[idx])

    def _on_spinbox_changed(self, key: str, value: float) -> None:
        row = self._rows.get(key)
        if row is None:
            return
        idx = row["selected_idx"]
        ranged_list = row["ranged_list"]
        if 0 <= idx < len(ranged_list):
            self.aboutToChange.emit()
            ranged_list[idx].value = value
            # Update bar segment value
            bar: SegmentBar = row["bar"]
            segs = bar.segments()
            if 0 <= idx < len(segs):
                segs[idx] = SegmentData(
                    segs[idx].start_ordinal,
                    segs[idx].end_ordinal,
                    value,
                    segs[idx].color,
                )
                bar.set_segments(segs)
            self.modelChanged.emit()

    def _on_delete_button(self, key: str) -> None:
        row = self._rows.get(key)
        if row is None:
            return
        idx = row["selected_idx"]
        if idx >= 0:
            self._on_delete(key, idx)

    def _on_split_button(self, key: str) -> None:
        row = self._rows.get(key)
        if row is None:
            return
        idx = row["selected_idx"]
        if idx >= 0:
            self._on_split(key, idx)

    def _on_add_button(self, key: str) -> None:
        row = self._rows.get(key)
        if row is None:
            return
        domain_size = row["domain_size"]
        self.aboutToChange.emit()
        new_rc = append_ranged_constraint_instance(
            self._path.ranged_constraints,
            key=key,
            value=constraint_default_value(key),
            total=domain_size,
        )
        if new_rc is None:
            QToolTip.showText(QCursor.pos(), "All elements are covered")
            return
        self.rebuild()
        self.modelChanged.emit()

    # ------------------------------------------------------------------
    # Model mutations
    # ------------------------------------------------------------------

    def _create_constraint(
        self,
        key: str,
        start: int,
        end: int,
        *,
        emit_about_to_change: bool = True,
        rebuild: bool = True,
        emit_model_changed: bool = True,
    ) -> None:
        """Create a new RangedConstraint and rebuild."""
        from models.path_model import RangedConstraint

        if emit_about_to_change:
            self.aboutToChange.emit()

        rc = RangedConstraint(
            key=key,
            value=constraint_default_value(key),
            start_ordinal=start,
            end_ordinal=end,
        )
        self._path.ranged_constraints.append(rc)
        if rebuild:
            self.rebuild()
        if emit_model_changed:
            self.modelChanged.emit()

    def _split_constraint(self, key: str, rc) -> None:
        """Split a RangedConstraint at its midpoint."""
        if rc.end_ordinal - rc.start_ordinal < 1:
            # Cannot split a single-ordinal constraint
            return

        self.aboutToChange.emit()
        if split_ranged_constraint_instance(self._path.ranged_constraints, rc) is None:
            return
        self.rebuild()
        self.modelChanged.emit()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _present_keys(self) -> List[str]:
        """Return ranged constraint keys currently represented in the model."""
        present_keys: List[str] = []
        for key in RANGED_CONSTRAINT_KEYS:
            if any(rc.key == key for rc in (self._path.ranged_constraints or [])):
                present_keys.append(key)
        return present_keys

    @staticmethod
    def _unit_for_key(key: str) -> str:
        """Extract a clean unit suffix like ' m/s' from SPINNER_METADATA label."""
        import re

        meta = SPINNER_METADATA.get(key, {})
        label = str(meta.get("label", "")).replace("<br/>", " ")
        m = re.search(r"\(([^)]+)\)\s*$", label)
        if m:
            unit = m.group(1)
            if re.fullmatch(r"[\d.\-\u2013]+", unit):
                return ""
            return " " + unit
        return ""

    @staticmethod
    def _decimals_for_key(key: str) -> int:
        """Determine decimal places for a key's spinbox."""
        meta = SPINNER_METADATA.get(key, {})
        step_value = meta.get("step", 0.1)
        step = float(step_value) if isinstance(step_value, (int, float)) else 0.1
        if step >= 1.0:
            return 1
        s = str(step)
        if "." in s:
            return len(s.split(".")[1])
        return 1
