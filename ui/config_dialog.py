from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from ui.qt_compat import Qt, QSizePolicy, QDialogButtonBox
from ui.sidebar.widgets.no_wheel_spinbox import NoWheelDoubleSpinBox


class ConfigDialog(QDialog):
    """Dialog to edit config.json values with grouped sections."""

    def __init__(
        self,
        parent=None,
        existing_config: Optional[Dict[str, Any]] = None,
        on_change: Optional[Callable[[str, Any], None]] = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Edit Config")
        self.setModal(True)
        self._on_change = on_change
        self._controls: Dict[str, Any] = {}
        cfg = existing_config or {}

        # Apply dark dialog background to match the app
        try:
            self.setObjectName("configDialog")
            self.setStyleSheet(
                """
                QDialog#configDialog { background-color: #151515; }
                QLabel { color: #f0f0f0; }
                """
            )
        except Exception:
            pass

        root = QVBoxLayout(self)
        try:
            root.setContentsMargins(8, 8, 8, 8)
            root.setSpacing(8)
        except Exception:
            pass

        self._build_title_bar(root)

        # GUI section
        gui_layout = self._add_section(root, "GUI")
        self._add_spin(
            gui_layout,
            cfg,
            "robot_length_meters",
            "Robot Length (m)",
            0.60,
            (0.05, 5.0),
            0.01,
        )
        self._add_spin(
            gui_layout,
            cfg,
            "robot_width_meters",
            "Robot Width (m)",
            0.60,
            (0.05, 5.0),
            0.01,
        )
        self._add_checkbox(
            gui_layout,
            cfg,
            "protrusion_enabled",
            "Enable Protrusions",
            False,
        )
        self._add_spin(
            gui_layout,
            cfg,
            "protrusion_distance_meters",
            "Protrusion Distance (m)",
            0.0,
            (0.0, 2.0),
            0.01,
        )
        self._add_combo(
            gui_layout,
            cfg,
            "protrusion_side",
            "Protrusion Side",
            ["none", "left", "right", "front", "back"],
            "none",
        )
        self._add_combo(
            gui_layout,
            cfg,
            "protrusion_default_state",
            "Default Protrusion State",
            ["", "shown", "hidden"],
            "",
        )
        self._add_key_list_input(
            gui_layout,
            cfg,
            "protrusion_show_on_event_keys",
            "Show On Event Keys",
        )
        self._add_key_list_input(
            gui_layout,
            cfg,
            "protrusion_hide_on_event_keys",
            "Hide On Event Keys",
        )

        # Kinematic constraints section
        kinematic_layout = self._add_section(root, "Kinematic Constraints")
        self._add_spin(
            kinematic_layout,
            cfg,
            "default_max_velocity_meters_per_sec",
            "Default Max Velocity (m/s)",
            4.5,
            (0.0, 99999.0),
            0.1,
        )
        self._add_spin(
            kinematic_layout,
            cfg,
            "default_max_acceleration_meters_per_sec2",
            "Default Max Accel (m/s²)",
            7.0,
            (0.0, 99999.0),
            0.1,
        )
        self._add_spin(
            kinematic_layout,
            cfg,
            "default_intermediate_handoff_radius_meters",
            "Default Handoff Radius (m)",
            0.2,
            (0.0, 99999.0),
            0.05,
        )
        self._add_spin(
            kinematic_layout,
            cfg,
            "default_max_velocity_deg_per_sec",
            "Default Max Rot Vel (deg/s)",
            720.0,
            (0.0, 99999.0),
            1.0,
        )
        self._add_spin(
            kinematic_layout,
            cfg,
            "default_max_acceleration_deg_per_sec2",
            "Default Max Rot Accel (deg/s²)",
            1500.0,
            (0.0, 99999.0),
            1.0,
        )
        self._add_spin(
            kinematic_layout,
            cfg,
            "default_end_translation_tolerance_meters",
            "End Translation Tolerance (m)",
            0.03,
            (0.0, 1.0),
            0.01,
        )
        self._add_spin(
            kinematic_layout,
            cfg,
            "default_end_rotation_tolerance_deg",
            "End Rotation Tolerance (deg)",
            2.0,
            (0.0, 180.0),
            0.1,
        )

        # Wire protrusion enabled state behavior
        enabled_box = self._controls.get("protrusion_enabled")
        if isinstance(enabled_box, QCheckBox):
            enabled_box.toggled.connect(self._on_protrusion_enabled_toggled)
        self._refresh_protrusion_state_options(emit_change=False)

        # Buttons styled to fit dark UI
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, orientation=Qt.Horizontal, parent=self
        )
        try:
            buttons.setStyleSheet(
                """
                QDialogButtonBox QPushButton {
                    background-color: #303030;
                    color: #eeeeee;
                    border: 1px solid #5a5a5a;
                    border-radius: 4px;
                    padding: 4px 10px;
                }
                QDialogButtonBox QPushButton:hover { background: #575757; }
                QDialogButtonBox QPushButton:pressed { background: #6a6a6a; }
                """
            )
        except Exception:
            pass
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _build_title_bar(self, root: QVBoxLayout) -> None:
        self.title_bar = QWidget()
        self.title_bar.setObjectName("configTitleBar")
        try:
            self.title_bar.setStyleSheet(
                """
                QWidget#configTitleBar {
                    background-color: #2a2a2a;
                    border: 1px solid #5a5a5a;
                    border-radius: 6px;
                }
                """
            )
        except Exception:
            pass
        title_layout = QHBoxLayout(self.title_bar)
        try:
            title_layout.setContentsMargins(10, 0, 10, 0)
            title_layout.setSpacing(0)
        except Exception:
            pass
        title_label = QLabel("Configuration")
        try:
            title_label.setStyleSheet(
                """
                font-size: 14px;
                font-weight: bold;
                color: #eeeeee;
                background: transparent;
                border: none;
                padding: 6px 0;
                """
            )
        except Exception:
            pass
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        root.addWidget(self.title_bar)

    def _add_section(self, root: QVBoxLayout, title: str) -> QVBoxLayout:
        section = QGroupBox(title)
        try:
            section.setStyleSheet(
                """
                QGroupBox {
                    background-color: #202020;
                    border: 1px solid #444444;
                    border-radius: 6px;
                    color: #f0f0f0;
                    margin-top: 8px;
                    padding-top: 8px;
                }
                QWidget[constraintRow='true'] {
                    background: #2d2d2d;
                    border: 1px solid #454545;
                    border-radius: 6px;
                    margin: 4px 0;
                }
                """
            )
        except Exception:
            pass
        layout = QVBoxLayout(section)
        try:
            layout.setContentsMargins(8, 8, 8, 8)
            layout.setSpacing(4)
        except Exception:
            pass
        root.addWidget(section)
        return layout

    def _add_row(self, group_layout: QVBoxLayout, label_text: str, control: QWidget) -> None:
        row = QWidget()
        row.setProperty("constraintRow", "true")
        row_layout = QHBoxLayout(row)
        try:
            row_layout.setContentsMargins(8, 6, 8, 6)
            row_layout.setSpacing(8)
        except Exception:
            pass

        lbl = QLabel(label_text)
        try:
            lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            lbl.setMinimumWidth(220)
        except Exception:
            pass
        row_layout.addWidget(lbl)
        row_layout.addStretch()
        row_layout.addWidget(control)
        group_layout.addWidget(row)

    def _coerce_bool(self, value: Any, fallback: bool = False) -> bool:
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

    def _normalize_side(self, value: Any) -> str:
        raw = str(value).strip().lower()
        return raw if raw in ("none", "left", "right", "front", "back") else "none"

    def _normalize_state(self, value: Any) -> str:
        raw = str(value).strip().lower()
        if raw in ("shown", "show", "visible", "on", "true", "1"):
            return "shown"
        if raw in ("hidden", "hide", "invisible", "off", "false", "0"):
            return "hidden"
        return ""

    def _split_keys(self, raw: str) -> list[str]:
        items = [part.strip() for part in raw.replace("\n", ",").split(",")]
        values: list[str] = []
        seen: set[str] = set()
        for key in items:
            if not key or key in seen:
                continue
            seen.add(key)
            values.append(key)
        return values

    def _join_keys(self, value: Any) -> str:
        if isinstance(value, str):
            return value
        if isinstance(value, (list, tuple, set)):
            return ", ".join([str(v).strip() for v in value if str(v).strip()])
        return ""

    def _add_spin(
        self,
        group_layout: QVBoxLayout,
        cfg: Dict[str, Any],
        key: str,
        label: str,
        default: float,
        rng: tuple[float, float],
        step: float = 0.01,
    ) -> None:
        spin = NoWheelDoubleSpinBox(self)
        spin.setDecimals(4)
        spin.setSingleStep(step)
        spin.setRange(rng[0], rng[1])
        try:
            spin.setValue(float(cfg.get(key, default)))
        except Exception:
            spin.setValue(float(default))
        try:
            spin.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            spin.setMinimumWidth(120)
        except Exception:
            pass
        spin.valueChanged.connect(lambda _v, k=key, w=spin: self._emit_change(k, float(w.value())))
        self._controls[key] = spin
        self._add_row(group_layout, label, spin)

    def _add_checkbox(
        self,
        group_layout: QVBoxLayout,
        cfg: Dict[str, Any],
        key: str,
        label: str,
        default: bool,
    ) -> None:
        box = QCheckBox(self)
        box.setChecked(self._coerce_bool(cfg.get(key, default), default))
        box.toggled.connect(lambda v, k=key: self._emit_change(k, bool(v)))
        self._controls[key] = box
        self._add_row(group_layout, label, box)

    def _add_combo(
        self,
        group_layout: QVBoxLayout,
        cfg: Dict[str, Any],
        key: str,
        label: str,
        options: list[str],
        default: str,
    ) -> None:
        combo = QComboBox(self)
        combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        combo.addItems(options)
        current = str(cfg.get(key, default)).strip().lower()
        if current in options:
            combo.setCurrentText(current)
        else:
            combo.setCurrentText(default)
        combo.currentTextChanged.connect(lambda text, k=key: self._emit_change(k, str(text)))
        self._controls[key] = combo
        self._add_row(group_layout, label, combo)

    def _add_key_list_input(
        self, group_layout: QVBoxLayout, cfg: Dict[str, Any], key: str, label: str
    ) -> None:
        edit = QLineEdit(self)
        edit.setPlaceholderText("Comma-separated event keys")
        edit.setText(self._join_keys(cfg.get(key, [])))
        edit.textChanged.connect(lambda _t, k=key, w=edit: self._emit_change(k, self._split_keys(w.text())))
        self._controls[key] = edit
        self._add_row(group_layout, label, edit)

    def _on_protrusion_enabled_toggled(self, checked: bool) -> None:
        self._refresh_protrusion_state_options(emit_change=True)

    def _refresh_protrusion_state_options(self, emit_change: bool) -> None:
        enabled = False
        enabled_ctrl = self._controls.get("protrusion_enabled")
        if isinstance(enabled_ctrl, QCheckBox):
            enabled = bool(enabled_ctrl.isChecked())

        state_ctrl = self._controls.get("protrusion_default_state")
        if isinstance(state_ctrl, QComboBox):
            current = self._normalize_state(state_ctrl.currentText())
            state_ctrl.blockSignals(True)
            state_ctrl.clear()
            if enabled:
                state_ctrl.addItems(["shown", "hidden"])
                state_ctrl.setCurrentText(current if current in ("shown", "hidden") else "shown")
                state_ctrl.setEnabled(True)
            else:
                state_ctrl.addItem("")
                state_ctrl.setCurrentIndex(0)
                state_ctrl.setEnabled(False)
            state_ctrl.blockSignals(False)
            if emit_change:
                self._emit_change("protrusion_default_state", state_ctrl.currentText())

        for key in (
            "protrusion_distance_meters",
            "protrusion_side",
            "protrusion_show_on_event_keys",
            "protrusion_hide_on_event_keys",
        ):
            ctrl = self._controls.get(key)
            if ctrl is not None:
                ctrl.setEnabled(enabled)

    def get_values(self) -> Dict[str, Any]:
        enabled = False
        enabled_ctrl = self._controls.get("protrusion_enabled")
        if isinstance(enabled_ctrl, QCheckBox):
            enabled = bool(enabled_ctrl.isChecked())

        side = "none"
        side_ctrl = self._controls.get("protrusion_side")
        if isinstance(side_ctrl, QComboBox):
            side = self._normalize_side(side_ctrl.currentText())

        default_state = ""
        state_ctrl = self._controls.get("protrusion_default_state")
        if isinstance(state_ctrl, QComboBox) and enabled:
            default_state = self._normalize_state(state_ctrl.currentText())

        show_keys = []
        hide_keys = []
        show_ctrl = self._controls.get("protrusion_show_on_event_keys")
        hide_ctrl = self._controls.get("protrusion_hide_on_event_keys")
        if isinstance(show_ctrl, QLineEdit):
            show_keys = self._split_keys(show_ctrl.text())
        if isinstance(hide_ctrl, QLineEdit):
            hide_keys = self._split_keys(hide_ctrl.text())

        def _spin_value(key: str, fallback: float = 0.0) -> float:
            ctrl = self._controls.get(key)
            if isinstance(ctrl, NoWheelDoubleSpinBox):
                return float(ctrl.value())
            return float(fallback)

        return {
            "robot_length_meters": _spin_value("robot_length_meters", 0.60),
            "robot_width_meters": _spin_value("robot_width_meters", 0.60),
            "protrusion_enabled": bool(enabled),
            "protrusion_distance_meters": _spin_value("protrusion_distance_meters", 0.0),
            "protrusion_side": side,
            "protrusion_default_state": default_state if enabled else "",
            "protrusion_show_on_event_keys": show_keys,
            "protrusion_hide_on_event_keys": hide_keys,
            "default_max_velocity_meters_per_sec": _spin_value(
                "default_max_velocity_meters_per_sec", 4.5
            ),
            "default_max_acceleration_meters_per_sec2": _spin_value(
                "default_max_acceleration_meters_per_sec2", 7.0
            ),
            "default_intermediate_handoff_radius_meters": _spin_value(
                "default_intermediate_handoff_radius_meters", 0.2
            ),
            "default_max_velocity_deg_per_sec": _spin_value("default_max_velocity_deg_per_sec", 720.0),
            "default_max_acceleration_deg_per_sec2": _spin_value(
                "default_max_acceleration_deg_per_sec2", 1500.0
            ),
            "default_end_translation_tolerance_meters": _spin_value(
                "default_end_translation_tolerance_meters", 0.03
            ),
            "default_end_rotation_tolerance_deg": _spin_value("default_end_rotation_tolerance_deg", 2.0),
        }

    def _emit_change(self, key: str, value: Any):
        if self._on_change is not None:
            try:
                self._on_change(key, value)
            except Exception:
                pass

    def sync_from_config(self, cfg: Dict[str, Any]) -> None:
        """Update control values from config without emitting signals."""
        for key, control in self._controls.items():
            if key not in cfg:
                continue
            value = cfg.get(key)
            try:
                control.blockSignals(True)
                if isinstance(control, NoWheelDoubleSpinBox):
                    if value is not None:
                        control.setValue(float(value))
                elif isinstance(control, QCheckBox):
                    control.setChecked(self._coerce_bool(value, control.isChecked()))
                elif isinstance(control, QComboBox):
                    if key == "protrusion_side":
                        control.setCurrentText(self._normalize_side(value))
                    elif key == "protrusion_default_state":
                        control.setCurrentText(self._normalize_state(value))
                    else:
                        control.setCurrentText(str(value))
                elif isinstance(control, QLineEdit):
                    control.setText(self._join_keys(value))
            except Exception:
                pass
            finally:
                control.blockSignals(False)

        self._refresh_protrusion_state_options(emit_change=False)
        state_ctrl = self._controls.get("protrusion_default_state")
        if isinstance(state_ctrl, QComboBox):
            try:
                state_ctrl.blockSignals(True)
                enabled_ctrl = self._controls.get("protrusion_enabled")
                enabled = bool(enabled_ctrl.isChecked()) if isinstance(enabled_ctrl, QCheckBox) else False
                if enabled:
                    state_ctrl.setCurrentText(self._normalize_state(cfg.get("protrusion_default_state", "")))
                else:
                    state_ctrl.setCurrentText("")
            finally:
                state_ctrl.blockSignals(False)
