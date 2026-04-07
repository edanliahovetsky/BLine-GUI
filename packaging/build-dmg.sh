#!/bin/bash
set -e

# BLine macOS Build Script
# Creates a .app bundle with PyInstaller and packages it as a fancy .dmg

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BUILD_DIR="${SCRIPT_DIR}/build"
DIST_DIR="${SCRIPT_DIR}/dist"

echo "========================================"
echo "Building BLine for macOS"
echo "========================================"
echo ""

# Check for required tools
command -v python3 >/dev/null 2>&1 || { echo "Error: python3 is required but not installed."; exit 1; }
command -v brew >/dev/null 2>&1 || { echo "Error: Homebrew is required. Install from https://brew.sh"; exit 1; }
if ! command -v create-dmg >/dev/null 2>&1; then
    echo "Installing create-dmg..."
    brew install create-dmg
fi

# Get version from pyproject.toml
VERSION=$(grep '^version = ' "${PROJECT_DIR}/pyproject.toml" | sed 's/version = "\(.*\)"/\1/')
ARCH=$(uname -m)  # arm64/x86_64

echo "Version: $VERSION"
echo "Architecture: $ARCH"
echo ""

# Clean previous build
echo "Cleaning previous build..."
rm -rf "$BUILD_DIR" "$DIST_DIR"
mkdir -p "$BUILD_DIR"

# Generate .icns from rebel_logo.png
echo "Generating app icon..."
LOGO_SRC="${PROJECT_DIR}/assets/rebel_logo.png"
ICONSET_DIR="${BUILD_DIR}/BLine.iconset"
ICNS_PATH="${BUILD_DIR}/BLine.icns"
mkdir -p "$ICONSET_DIR"

for size in 16 32 64 128 256 512; do
    sips -z $size $size "$LOGO_SRC" --out "${ICONSET_DIR}/icon_${size}x${size}.png" >/dev/null
    double=$((size * 2))
    sips -z $double $double "$LOGO_SRC" --out "${ICONSET_DIR}/icon_${size}x${size}@2x.png" >/dev/null
done

iconutil -c icns "$ICONSET_DIR" -o "$ICNS_PATH"

# Create a venv and install deps
echo "Creating virtual environment and installing dependencies..."
python3 -m venv "${BUILD_DIR}/venv"
source "${BUILD_DIR}/venv/bin/activate"

pip install --upgrade pip
pip install pyinstaller
pip install -e "$PROJECT_DIR"

# Build .app bundle with PyInstaller
echo "Building .app bundle with PyInstaller..."
cd "$SCRIPT_DIR"
pyinstaller --clean --noconfirm \
    --distpath "$DIST_DIR" \
    --workpath "${BUILD_DIR}/pyinstaller" \
    bline-macos.spec

deactivate

APP_PATH="${DIST_DIR}/BLine.app"
if [ ! -d "$APP_PATH" ]; then
    echo "Error: PyInstaller build failed — ${APP_PATH} not found."
    exit 1
fi

# Create DMG 
echo "Creating DMG..."
OUTPUT="${PROJECT_DIR}/BLine-${VERSION}-macOS-${ARCH}.dmg"
STAGING_DIR="${BUILD_DIR}/dmg-staging"

rm -f "$OUTPUT"
mkdir -p "$STAGING_DIR"
cp -r "$APP_PATH" "$STAGING_DIR/"

create-dmg \
    --volname "BLine ${VERSION}" \
    --volicon "$ICNS_PATH" \
    --window-pos 200 150 \
    --window-size 660 400 \
    --icon-size 128 \
    --icon "BLine.app" 180 185 \
    --hide-extension "BLine.app" \
    --app-drop-link 480 185 \
    --no-internet-enable \
    "$OUTPUT" \
    "$STAGING_DIR/"

echo ""
echo "========================================"
echo "Build complete!"
echo "DMG created: $OUTPUT"
echo "========================================"

