# BLine Windows Build Script (PowerShell)
# This script creates a Windows executable using PyInstaller

param(
    [switch]$Clean = $false,
    [switch]$SkipInstall = $false
)

$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Building BLine for Windows" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Get script and project directories
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = Split-Path -Parent $ScriptDir
$BuildDir = Join-Path $ScriptDir "build"
$DistDir = Join-Path $ScriptDir "dist"

# Clean previous build if requested
if ($Clean) {
    Write-Host "Cleaning previous build..." -ForegroundColor Yellow
    Remove-Item -Path $BuildDir -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -Path $DistDir -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -Path (Join-Path $ScriptDir "*.spec") -Force -ErrorAction SilentlyContinue
}

# Create virtual environment if it doesn't exist
$VenvDir = Join-Path $BuildDir "venv"
if (-not (Test-Path $VenvDir) -or $Clean) {
    Write-Host "Creating virtual environment..." -ForegroundColor Yellow
    python -m venv $VenvDir
}

# Activate virtual environment
$ActivateScript = Join-Path $VenvDir "Scripts\Activate.ps1"
Write-Host "Activating virtual environment..." -ForegroundColor Yellow
& $ActivateScript

# Install dependencies
if (-not $SkipInstall) {
    Write-Host "Installing dependencies..." -ForegroundColor Yellow
    python -m pip install --upgrade pip
    pip install pyinstaller
    pip install -e $ProjectDir
}

# Convert PNG icon to ICO if needed
$IconPath = Join-Path $ProjectDir "assets\rebel_logo.png"
$IcoPath = Join-Path $ScriptDir "bline.ico"

Write-Host "Creating application icon..." -ForegroundColor Yellow
if (Test-Path $IconPath) {
    # Use Python/Pillow to convert PNG to ICO
    python -c @"
from PIL import Image
img = Image.open('$($IconPath.Replace('\', '\\'))')
img.save('$($IcoPath.Replace('\', '\\'))', format='ICO', sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
print('Icon created successfully')
"@
} else {
    Write-Host "Warning: Icon file not found at $IconPath" -ForegroundColor Yellow
}

# Build with PyInstaller
Write-Host "Building executable with PyInstaller..." -ForegroundColor Yellow
Set-Location $ScriptDir

# Create updated spec file with icon
$SpecContent = Get-Content "bline.spec" -Raw
if (Test-Path $IcoPath) {
    $SpecContent = $SpecContent -replace "icon=str\(assets_dir / 'rebel_logo\.png'\).*", "icon='$($IcoPath.Replace('\', '\\'))',"
    Set-Content -Path "bline.spec" -Value $SpecContent
}

pyinstaller --clean --noconfirm bline.spec

# Check if build succeeded
$ExePath = Join-Path $DistDir "BLine\BLine.exe"
if (Test-Path $ExePath) {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Green
    Write-Host "Build complete!" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "Executable location: $DistDir\BLine\" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "To run the application:" -ForegroundColor Yellow
    Write-Host "  .\windows\dist\BLine\BLine.exe" -ForegroundColor White
    Write-Host ""
    Write-Host "To create an installer, run:" -ForegroundColor Yellow
    Write-Host "  .\windows\create-installer.ps1" -ForegroundColor White
    Write-Host ""
} else {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Red
    Write-Host "Build failed!" -ForegroundColor Red
    Write-Host "========================================" -ForegroundColor Red
    Write-Host ""
    exit 1
}
