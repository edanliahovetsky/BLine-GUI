from __future__ import annotations

import argparse
import faulthandler
import sys
from pathlib import Path
from typing import Sequence

from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QCheckBox,
    QPushButton,
    QLabel,
    QMessageBox,
)
from PySide6.QtGui import QPalette, QColor, QPixmap
from PySide6.QtCore import Qt
from typing import cast

from ui.main_window import MainWindow
from ui.resources import ensure_assets_loaded

faulthandler.enable()


def get_package_root() -> Path:
    """Get the root directory of the installed package."""
    return Path(__file__).parent


def find_icon_path() -> Path | None:
    """Find the icon file, checking multiple possible locations."""
    possible_paths = [
        get_package_root() / "assets" / "rebel_logo.png",  # Dev / source install
        Path(sys.prefix) / "bline_assets" / "rebel_logo.png",  # Installed via pip
        Path(__file__).parent.parent / "assets" / "rebel_logo.png",  # Alternate structure
    ]
    for path in possible_paths:
        if path.exists():
            return path
    return None


def get_icon_for_shortcut() -> str | None:
    """Get the icon path in the correct format for the current platform."""
    import platform
    import subprocess
    import tempfile
    
    png_path = find_icon_path()
    if not png_path or not png_path.exists():
        return None
    
    if platform.system() == "Darwin":
        # macOS needs .icns format - convert using sips
        try:
            # Create a temporary .icns file
            icns_path = Path(tempfile.gettempdir()) / "bline_icon.icns"
            
            # First create an iconset directory
            iconset_path = Path(tempfile.gettempdir()) / "bline.iconset"
            iconset_path.mkdir(exist_ok=True)
            
            # Use sips to resize and create the required icon sizes
            sizes = [16, 32, 64, 128, 256, 512]
            for size in sizes:
                output = iconset_path / f"icon_{size}x{size}.png"
                subprocess.run(
                    ["sips", "-z", str(size), str(size), str(png_path), "--out", str(output)],
                    capture_output=True,
                    check=True,
                )
                # Also create @2x versions for retina
                if size <= 256:
                    output_2x = iconset_path / f"icon_{size}x{size}@2x.png"
                    size_2x = size * 2
                    subprocess.run(
                        ["sips", "-z", str(size_2x), str(size_2x), str(png_path), "--out", str(output_2x)],
                        capture_output=True,
                        check=True,
                    )
            
            # Convert iconset to icns
            subprocess.run(
                ["iconutil", "-c", "icns", str(iconset_path), "-o", str(icns_path)],
                capture_output=True,
                check=True,
            )
            
            # Clean up iconset
            import shutil
            shutil.rmtree(iconset_path, ignore_errors=True)
            
            if icns_path.exists():
                return str(icns_path)
        except (subprocess.CalledProcessError, FileNotFoundError):
            # If conversion fails, return None (pyshortcuts will use default)
            pass
        return None
    
    elif platform.system() == "Windows":
        # Windows prefers .ico but can sometimes use .png
        # For best results, we'd convert to .ico, but .png often works
        return str(png_path)
    
    else:
        # Linux uses .png
        return str(png_path)


def create_shortcut_dialog() -> int:
    """Show a dialog to create desktop/start menu shortcuts."""
    try:
        from pyshortcuts import make_shortcut
    except ImportError:
        print("Error: pyshortcuts not installed. Run: pip install pyshortcuts")
        return 1

    app = QApplication.instance() or QApplication(sys.argv)
    
    # Apply dark theme for consistency
    set_dark_theme(cast(QApplication, app))

    dialog = QDialog()
    dialog.setWindowTitle("BLine - Create Shortcut")
    dialog.setFixedSize(350, 200)

    layout = QVBoxLayout(dialog)

    # Icon preview and title
    header_layout = QHBoxLayout()
    icon_path = find_icon_path()
    if icon_path and icon_path.exists():
        icon_label = QLabel()
        pixmap = QPixmap(str(icon_path)).scaled(48, 48, Qt.AspectRatioMode.KeepAspectRatio)
        icon_label.setPixmap(pixmap)
        header_layout.addWidget(icon_label)
    
    title_label = QLabel("Create BLine Shortcut")
    title_label.setStyleSheet("font-size: 16px; font-weight: bold;")
    header_layout.addWidget(title_label)
    header_layout.addStretch()
    layout.addLayout(header_layout)

    layout.addSpacing(10)

    # Checkboxes for shortcut locations - platform-specific text
    import platform
    
    desktop_cb = QCheckBox("Desktop")
    desktop_cb.setChecked(True)
    layout.addWidget(desktop_cb)

    if platform.system() == "Darwin":
        startmenu_text = "~/Applications folder"
    elif platform.system() == "Windows":
        startmenu_text = "Start Menu"
    else:
        startmenu_text = "Applications menu"
    
    startmenu_cb = QCheckBox(startmenu_text)
    startmenu_cb.setChecked(True)
    layout.addWidget(startmenu_cb)

    layout.addStretch()

    # Buttons
    button_layout = QHBoxLayout()
    button_layout.addStretch()
    
    cancel_btn = QPushButton("Cancel")
    cancel_btn.clicked.connect(dialog.reject)
    button_layout.addWidget(cancel_btn)

    create_btn = QPushButton("Create Shortcut")
    create_btn.setDefault(True)
    button_layout.addWidget(create_btn)
    
    layout.addLayout(button_layout)

    def on_create():
        if not desktop_cb.isChecked() and not startmenu_cb.isChecked():
            QMessageBox.warning(dialog, "No Location", "Please select at least one location.")
            return

        try:
            # Get the icon in the correct format for this platform
            icon = get_icon_for_shortcut()
            
            # Create the shortcut
            make_shortcut(
                script="bline",
                name="BLine",
                description="FRC Robot Path Planning Tool",
                icon=icon,
                desktop=desktop_cb.isChecked(),
                startmenu=startmenu_cb.isChecked(),
                terminal=False,
            )
            
            locations = []
            if desktop_cb.isChecked():
                locations.append("Desktop")
            if startmenu_cb.isChecked():
                locations.append(startmenu_text)
            
            message = f"Shortcut created in: {', '.join(locations)}"
            QMessageBox.information(dialog, "Success", message)
            dialog.accept()
        except Exception as e:
            QMessageBox.critical(dialog, "Error", f"Failed to create shortcut:\n{e}")

    create_btn.clicked.connect(on_create)

    result = dialog.exec()
    return 0 if result == QDialog.DialogCode.Accepted else 1


DARK_STYLE_SHEET = """
QMainWindow,
QWidget#mainCentralWidget {
    background-color: #111111;
    color: #f0f0f0;
}

QMenuBar,
QMenu,
QToolBar,
QStatusBar {
    background-color: #1b1b1b;
    color: #f0f0f0;
}

QMenu::item:selected {
    background-color: #2a82da;
    color: #000000;
}
"""


def set_dark_theme(app: QApplication) -> None:
    """Apply a dark theme to the application."""
    app.setStyle("Fusion")

    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(17, 17, 17))
    palette.setColor(QPalette.ColorRole.WindowText, Qt.GlobalColor.white)
    palette.setColor(QPalette.ColorRole.Base, QColor(28, 28, 28))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(38, 38, 38))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(42, 42, 42))
    palette.setColor(QPalette.ColorRole.ToolTipText, Qt.GlobalColor.white)
    palette.setColor(QPalette.ColorRole.Text, Qt.GlobalColor.white)
    palette.setColor(QPalette.ColorRole.Button, QColor(43, 43, 43))
    palette.setColor(QPalette.ColorRole.ButtonText, Qt.GlobalColor.white)
    palette.setColor(QPalette.ColorRole.BrightText, Qt.GlobalColor.red)
    palette.setColor(QPalette.ColorRole.Link, QColor(42, 130, 218))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
    palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.black)
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(150, 150, 150))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(115, 115, 115))
    palette.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(115, 115, 115)
    )

    app.setPalette(palette)
    app.setStyleSheet(DARK_STYLE_SHEET)


def run_app(argv: Sequence[str] | None = None) -> int:
    """Create the QApplication and show the main window."""
    ensure_assets_loaded()
    existing_app = QApplication.instance()
    app = existing_app or QApplication(list(argv) if argv is not None else sys.argv)

    set_dark_theme(cast(QApplication, app))

    window = MainWindow()
    window.show()
    return app.exec()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="bline",
        description="BLine - FRC Robot Path Planning Tool"
    )
    parser.add_argument(
        "--create-shortcut",
        action="store_true",
        help="Create a desktop/start menu shortcut for BLine"
    )
    
    args, remaining = parser.parse_known_args(argv)
    
    if args.create_shortcut:
        return create_shortcut_dialog()
    
    return run_app(remaining if remaining else None)


if __name__ == "__main__":
    raise SystemExit(main())
