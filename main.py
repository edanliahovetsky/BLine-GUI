from __future__ import annotations

import argparse
import faulthandler
import os
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
                        [
                            "sips",
                            "-z",
                            str(size_2x),
                            str(size_2x),
                            str(png_path),
                            "--out",
                            str(output_2x),
                        ],
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
        # Windows shortcuts generally want an .ico for reliable display.
        try:
            # Store in a stable user location (temp dirs can be cleaned).
            ico_dir = Path.home() / ".bline"
            ico_dir.mkdir(parents=True, exist_ok=True)
            ico_path = ico_dir / "bline_icon.ico"
            # Generate an .ico using Qt (no extra deps).
            from PySide6.QtGui import QImage

            img = QImage(str(png_path))
            if img.isNull():
                return None
            # Prefer a 256x256 icon if available; Qt will scale as needed.
            img = img.scaled(
                256,
                256,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            if img.save(str(ico_path), "ICO") and ico_path.exists():
                return str(ico_path)
        except Exception:
            pass
        # Fallback to PNG path.
        return str(png_path)

    else:
        # Linux uses .png
        return str(png_path)


def find_bline_command() -> str | None:
    """Find the installed `bline` command (pipx or pip)."""
    import shutil

    bline_cmd = shutil.which("bline")
    if bline_cmd:
        return bline_cmd

    # Common pipx location on macOS/Linux
    pipx_bin = Path.home() / ".local" / "bin" / "bline"
    if pipx_bin.exists():
        return str(pipx_bin)

    return None


def create_macos_app_bundle(
    *,
    app_dir: Path,
    app_name: str,
    launch_cmd: str,
    icns_path: str | None,
) -> None:
    """Create a minimal macOS .app bundle that runs `launch_cmd`."""
    import shutil

    bundle = app_dir / f"{app_name}.app"
    contents = bundle / "Contents"
    macos_dir = contents / "MacOS"
    resources_dir = contents / "Resources"

    if bundle.exists():
        shutil.rmtree(bundle)

    resources_dir.mkdir(parents=True, exist_ok=True)
    macos_dir.mkdir(parents=True, exist_ok=True)

    # Launcher script
    launcher = macos_dir / app_name
    launcher.write_text(
        f'#!/bin/sh\nset -e\nexec {launch_cmd} "$@"\n',
        encoding="utf-8",
    )
    os.chmod(launcher, 0o755)

    icon_file = None
    if icns_path:
        src = Path(icns_path)
        if src.exists() and src.suffix.lower() == ".icns":
            icon_file = f"{app_name}.icns"
            shutil.copyfile(src, resources_dir / icon_file)

    # Info.plist
    plist = contents / "Info.plist"
    plist_lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">',
        '<plist version="1.0">',
        "  <dict>",
        "    <key>CFBundleDevelopmentRegion</key><string>en</string>",
        "    <key>CFBundleExecutable</key><string>%s</string>" % app_name,
        "    <key>CFBundleIdentifier</key><string>com.bline.gui</string>",
        "    <key>CFBundleInfoDictionaryVersion</key><string>6.0</string>",
        "    <key>CFBundleName</key><string>%s</string>" % app_name,
        "    <key>CFBundlePackageType</key><string>APPL</string>",
        "    <key>CFBundleShortVersionString</key><string>0.1.0</string>",
        "    <key>CFBundleVersion</key><string>0.1.0</string>",
    ]
    if icon_file:
        plist_lines.append("    <key>CFBundleIconFile</key><string>%s</string>" % icon_file)
    plist_lines += [
        "  </dict>",
        "</plist>",
        "",
    ]
    plist.write_text("\n".join(plist_lines), encoding="utf-8")


def create_windows_lnk(
    *,
    shortcut_path: Path,
    target_path: str,
    arguments: str,
    working_dir: str | None,
    icon_path: str | None,
) -> None:
    """Create a Windows .lnk shortcut via PowerShell (WScript.Shell COM)."""
    import subprocess

    shortcut_path.parent.mkdir(parents=True, exist_ok=True)

    # PowerShell-escape single quotes by doubling them.
    def ps_str(s: str) -> str:
        return "'" + s.replace("'", "''") + "'"

    ps_lines = [
        "$WshShell = New-Object -ComObject WScript.Shell",
        f"$Shortcut = $WshShell.CreateShortcut({ps_str(str(shortcut_path))})",
        f"$Shortcut.TargetPath = {ps_str(target_path)}",
        f"$Shortcut.Arguments = {ps_str(arguments)}",
    ]
    if working_dir:
        ps_lines.append(f"$Shortcut.WorkingDirectory = {ps_str(working_dir)}")
    if icon_path:
        # IconLocation supports 'path, index'
        ps_lines.append(f"$Shortcut.IconLocation = {ps_str(icon_path + ',0')}")
    ps_lines.append("$Shortcut.Save()")

    subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", "\n".join(ps_lines)],
        check=True,
        capture_output=True,
        text=True,
    )


def get_windows_known_folder(folder: str) -> Path:
    """Return a Windows known folder path.

    folder:
      - 'Desktop'
      - 'Programs' (Start Menu\\Programs)
    """
    import ctypes
    from ctypes import wintypes
    import uuid

    # GUIDs from Microsoft KNOWNFOLDERID
    folder_ids: dict[str, str] = {
        "Desktop": "{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}",  # FOLDERID_Desktop
        "Programs": "{A77F5D77-2E2B-44C3-A6A2-ABA601054A51}",  # FOLDERID_Programs
    }
    if folder not in folder_ids:
        raise ValueError(f"Unknown folder: {folder}")

    class GUID(ctypes.Structure):
        _fields_ = [
            ("Data1", wintypes.DWORD),
            ("Data2", wintypes.WORD),
            ("Data3", wintypes.WORD),
            ("Data4", wintypes.BYTE * 8),
        ]

    def guid_from_str(s: str) -> GUID:
        u = uuid.UUID(s)
        data4 = (wintypes.BYTE * 8).from_buffer_copy(u.bytes[8:])
        return GUID(u.time_low, u.time_mid, u.time_hi_version, data4)

    SHGetKnownFolderPath = ctypes.windll.shell32.SHGetKnownFolderPath
    SHGetKnownFolderPath.argtypes = [
        ctypes.POINTER(GUID),
        wintypes.DWORD,
        wintypes.HANDLE,
        ctypes.POINTER(ctypes.c_wchar_p),
    ]
    # Some Python builds don't expose wintypes.HRESULT; use c_long.
    SHGetKnownFolderPath.restype = ctypes.c_long

    CoTaskMemFree = ctypes.windll.ole32.CoTaskMemFree
    CoTaskMemFree.argtypes = [wintypes.LPVOID]
    CoTaskMemFree.restype = None

    fid = guid_from_str(folder_ids[folder])
    ppath = ctypes.c_wchar_p()
    hr = SHGetKnownFolderPath(ctypes.byref(fid), 0, 0, ctypes.byref(ppath))
    if hr != 0:
        raise OSError(f"SHGetKnownFolderPath failed for {folder}: HRESULT={hr}")
    try:
        return Path(ppath.value)
    finally:
        CoTaskMemFree(ppath)


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

    # Checkboxes for shortcut locations - platform-specific
    import platform

    desktop_cb = QCheckBox("Desktop")
    desktop_cb.setChecked(True)
    layout.addWidget(desktop_cb)

    system = platform.system()
    startmenu_cb: QCheckBox | None = None
    startmenu_text: str | None = None

    if system == "Darwin":
        startmenu_text = "Applications (/Applications)"
        startmenu_cb = QCheckBox(startmenu_text)
        startmenu_cb.setChecked(True)
        layout.addWidget(startmenu_cb)
    elif system == "Windows":
        # Start Menu = Apps list/shortcut folder (NOT "run on startup").
        startmenu_text = "Start Menu (Apps list)"
        startmenu_cb = QCheckBox(startmenu_text)
        startmenu_cb.setChecked(True)
        layout.addWidget(startmenu_cb)
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
        startmenu_checked = bool(startmenu_cb and startmenu_cb.isChecked())
        if not desktop_cb.isChecked() and not startmenu_checked:
            QMessageBox.warning(dialog, "No Location", "Please select at least one location.")
            return

        try:
            bline_cmd = find_bline_command()
            if not bline_cmd:
                QMessageBox.critical(
                    dialog,
                    "Not Installed",
                    "BLine is not installed. Please install with:\n\npipx install bline",
                )
                return

            icon = get_icon_for_shortcut()

            # macOS: pyshortcuts only creates Desktop .app bundles and does not support "Start Menu/Applications".
            # Create real .app bundles ourselves for Desktop and/or ~/Applications.
            if system == "Darwin":
                launch_cmd = f'"{bline_cmd}"'
                if desktop_cb.isChecked():
                    create_macos_app_bundle(
                        app_dir=Path.home() / "Desktop",
                        app_name="BLine",
                        launch_cmd=launch_cmd,
                        icns_path=icon,
                    )
                if startmenu_checked:
                    # Prefer the global /Applications (what users see in Finder sidebar).
                    # If we can't write there, fall back to ~/Applications.
                    system_apps_dir = Path("/Applications")
                    if system_apps_dir.exists() and os.access(system_apps_dir, os.W_OK):
                        apps_dir = system_apps_dir
                    else:
                        apps_dir = Path.home() / "Applications"
                        apps_dir.mkdir(parents=True, exist_ok=True)
                    create_macos_app_bundle(
                        app_dir=apps_dir,
                        app_name="BLine",
                        launch_cmd=launch_cmd,
                        icns_path=icon,
                    )
            else:
                # Windows/Linux shortcut creation
                if system == "Windows":
                    # On Windows, create a VBS launcher that runs bline without a console window,
                    # then point the .lnk shortcut at the VBS.

                    # Ensure ~/.bline exists for our helper files
                    bline_data_dir = Path.home() / ".bline"
                    bline_data_dir.mkdir(parents=True, exist_ok=True)

                    # Create a VBS wrapper that launches bline invisibly (no console flash)
                    vbs_path = bline_data_dir / "launch_bline.vbs"
                    vbs_content = f'''Set WshShell = CreateObject("WScript.Shell")
WshShell.Run """{bline_cmd}""", 0, False
'''
                    vbs_path.write_text(vbs_content, encoding="utf-8")

                    # Use known folders (handles OneDrive redirected Desktops, localization, etc.)
                    desktop_dir = get_windows_known_folder("Desktop")
                    startmenu_dir = get_windows_known_folder("Programs")

                    # The shortcut targets wscript.exe running our VBS
                    exe = "wscript.exe"
                    args = f'"{vbs_path}"'

                    created_paths: list[str] = []
                    if desktop_cb.isChecked():
                        dest = desktop_dir / "BLine.lnk"
                        create_windows_lnk(
                            shortcut_path=dest,
                            target_path=exe,
                            arguments=args,
                            working_dir=str(Path.home()),
                            icon_path=icon,
                        )
                        created_paths.append(str(dest))
                    if startmenu_checked:
                        dest = startmenu_dir / "BLine.lnk"
                        create_windows_lnk(
                            shortcut_path=dest,
                            target_path=exe,
                            arguments=args,
                            working_dir=str(Path.home()),
                            icon_path=icon,
                        )
                        created_paths.append(str(dest))
                else:
                    # Linux: rely on pyshortcuts
                    make_shortcut(
                        script=bline_cmd,
                        name="BLine",
                        description="FRC Robot Path Planning Tool",
                        icon=icon,
                        desktop=desktop_cb.isChecked(),
                        startmenu=startmenu_checked,
                        terminal=False,
                    )

            locations = []
            if desktop_cb.isChecked():
                locations.append("Desktop")
            if startmenu_checked and startmenu_text:
                locations.append(startmenu_text)

            message = f"Shortcut created in: {', '.join(locations)}"
            if system == "Windows":
                # Show exact file paths so users can verify where it went.
                try:
                    message += "\n\nCreated:\n" + "\n".join(created_paths)
                except Exception:
                    pass
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
        prog="bline", description="BLine - FRC Robot Path Planning Tool"
    )
    parser.add_argument(
        "--create-shortcut",
        action="store_true",
        help="Create a desktop/start menu shortcut for BLine",
    )

    args, remaining = parser.parse_known_args(argv)

    if args.create_shortcut:
        return create_shortcut_dialog()

    return run_app(remaining if remaining else None)


if __name__ == "__main__":
    raise SystemExit(main())
