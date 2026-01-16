# BLine Portable ZIP Creation Script
# Creates a portable ZIP package for Windows (no installation required)

$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Creating BLine Portable ZIP" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Get script directory
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = Split-Path -Parent $ScriptDir
$DistDir = Join-Path $ScriptDir "dist\BLine"

# Get version from pyproject.toml
$PyProjectPath = Join-Path $ProjectDir "pyproject.toml"
$PyProjectContent = Get-Content $PyProjectPath -Raw
if ($PyProjectContent -match 'version\s*=\s*"([^"]+)"') {
    $Version = $matches[1]
    Write-Host "Detected version: $Version" -ForegroundColor Green
} else {
    Write-Host "Warning: Could not parse version from pyproject.toml, using default" -ForegroundColor Yellow
    $Version = "0.0.0"
}

$ZipName = "BLine-${Version}-Windows-Portable.zip"
$ZipPath = Join-Path $ProjectDir $ZipName

# Check if build exists
if (-not (Test-Path $DistDir)) {
    Write-Host "Error: Build not found at $DistDir" -ForegroundColor Red
    Write-Host "Please run build-windows.ps1 first" -ForegroundColor Yellow
    exit 1
}

# Remove old ZIP if exists
if (Test-Path $ZipPath) {
    Write-Host "Removing old ZIP file..." -ForegroundColor Yellow
    Remove-Item $ZipPath -Force
}

# Create README for portable version
$ReadmePath = Join-Path $DistDir "README.txt"
$ReadmeContent = @"
BLine Portable - Version $Version
=================================

This is a portable version of BLine that requires no installation.

QUICK START:
1. Extract this ZIP to any folder
2. Double-click BLine.exe to run
3. That's it!

FEATURES:
- No installation required
- No admin rights needed
- Can run from USB drive
- All settings stored in the same folder

SYSTEM REQUIREMENTS:
- Windows 10 or later (64-bit)
- No additional software needed (everything is bundled)

SUPPORT:
For issues, please visit: https://github.com/edanliahovetsky/BLine-GUI/issues

LICENSE:
BLine is licensed under the BSD 3-Clause License.
See LICENSE file for details.

Copyright (c) 2025 FRC Team 2638 Rebel Robotics
"@

Set-Content -Path $ReadmePath -Value $ReadmeContent -Force

# Copy LICENSE if exists
$LicenseSrc = Join-Path $ProjectDir "LICENSE"
if (Test-Path $LicenseSrc) {
    Copy-Item $LicenseSrc -Destination (Join-Path $DistDir "LICENSE") -Force
}

# Create the ZIP
Write-Host "Creating ZIP archive..." -ForegroundColor Yellow
Write-Host "This may take a minute..." -ForegroundColor Gray

Compress-Archive -Path "$DistDir\*" -DestinationPath $ZipPath -CompressionLevel Optimal -Force

# Display results
if (Test-Path $ZipPath) {
    $ZipFile = Get-Item $ZipPath
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Green
    Write-Host "Portable ZIP created successfully!" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "ZIP location: $ZipPath" -ForegroundColor Cyan
    Write-Host "Size: $([math]::Round($ZipFile.Length / 1MB, 2)) MB" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Users can extract this ZIP anywhere and run BLine.exe" -ForegroundColor Yellow
    Write-Host ""
} else {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Red
    Write-Host "ZIP creation failed!" -ForegroundColor Red
    Write-Host "========================================" -ForegroundColor Red
    exit 1
}
