#!/bin/bash
set -e

# BLine AppImage Build Script
# This script creates a portable AppImage for BLine

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BUILD_DIR="${SCRIPT_DIR}/build"
APPDIR="${BUILD_DIR}/BLine.AppDir"

echo "========================================"
echo "Building BLine AppImage"
echo "========================================"
echo ""

# Check for required tools
command -v python3 >/dev/null 2>&1 || { echo "Error: python3 is required but not installed."; exit 1; }

# Clean previous build
echo "Cleaning previous build..."
rm -rf "$BUILD_DIR"
mkdir -p "$APPDIR/usr"

# Create a virtual environment with all dependencies
echo "Creating virtual environment and installing dependencies..."
python3 -m venv "${BUILD_DIR}/venv"
source "${BUILD_DIR}/venv/bin/activate"

# Install the application and its dependencies
pip install --upgrade pip
pip install -e "$PROJECT_DIR"

# Copy the virtual environment to AppDir
echo "Copying Python environment to AppDir..."
cp -r "${BUILD_DIR}/venv/"* "${APPDIR}/usr/"

# Copy application files
echo "Copying application files..."
mkdir -p "${APPDIR}/usr/share/bline"
cp -r "${PROJECT_DIR}/models" "${APPDIR}/usr/share/bline/"
cp -r "${PROJECT_DIR}/ui" "${APPDIR}/usr/share/bline/"
cp -r "${PROJECT_DIR}/utils" "${APPDIR}/usr/share/bline/"
cp "${PROJECT_DIR}/main.py" "${APPDIR}/usr/share/bline/"
cp "${PROJECT_DIR}/assets_rc.py" "${APPDIR}/usr/share/bline/"

# Copy assets
echo "Copying assets..."
cp -r "${PROJECT_DIR}/assets" "${APPDIR}/usr/share/bline/"

# Create a Python wrapper that adds the application to sys.path
cat > "${APPDIR}/usr/bin/bline" << 'EOF'
#!/usr/bin/env python3
import sys
import os

# Add application directory to Python path
app_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'share', 'bline')
sys.path.insert(0, app_dir)

# Import and run
from main import main
sys.exit(main())
EOF
chmod +x "${APPDIR}/usr/bin/bline"

# Copy AppRun script
echo "Setting up AppRun..."
cat > "${APPDIR}/AppRun" << 'APPRUN'
#!/bin/bash
SELF=$(readlink -f "$0")
HERE=${SELF%/*}

# Add the embedded Python to PATH
export PATH="${HERE}/usr/bin:${PATH}"
export LD_LIBRARY_PATH="${HERE}/usr/lib:${LD_LIBRARY_PATH}"

# Disable writing .pyc files
export PYTHONDONTWRITEBYTECODE=1

# Launch the application
exec "${HERE}/usr/bin/bline" "$@"
APPRUN
chmod +x "${APPDIR}/AppRun"

# Copy desktop file
echo "Installing desktop file..."
cp "${SCRIPT_DIR}/bline.desktop" "${APPDIR}/"

# Copy icon
echo "Installing icon..."
cp "${PROJECT_DIR}/assets/rebel_logo.png" "${APPDIR}/bline.png"

# Download appimagetool if not present
APPIMAGETOOL="${BUILD_DIR}/appimagetool-x86_64.AppImage"
if [ ! -f "$APPIMAGETOOL" ]; then
    echo "Downloading appimagetool..."
    wget -q "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage" \
        -O "$APPIMAGETOOL"
    chmod +x "$APPIMAGETOOL"
fi

# Build the AppImage
echo "Building AppImage..."
OUTPUT="${PROJECT_DIR}/BLine-x86_64.AppImage"
ARCH=x86_64 "$APPIMAGETOOL" "$APPDIR" "$OUTPUT"

echo ""
echo "========================================"
echo "Build complete!"
echo "AppImage created: $OUTPUT"
echo "========================================"
echo ""
echo "You can now run: ./BLine-x86_64.AppImage"
