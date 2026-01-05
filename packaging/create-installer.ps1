# BLine Inno Setup Installer Creation Script
# This script compiles the Inno Setup script to create a Windows installer

$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Creating BLine Windows Installer" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Get script directory
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$DistDir = Join-Path $ScriptDir "dist\BLine"

# Check if build exists
if (-not (Test-Path $DistDir)) {
    Write-Host "Error: Build not found at $DistDir" -ForegroundColor Red
    Write-Host "Please run build-windows.ps1 first" -ForegroundColor Yellow
    exit 1
}

# Look for Inno Setup
$InnoSetupPaths = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles}\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 5\ISCC.exe",
    "${env:ProgramFiles}\Inno Setup 5\ISCC.exe"
)

$ISCC = $null
foreach ($path in $InnoSetupPaths) {
    if (Test-Path $path) {
        $ISCC = $path
        break
    }
}

if (-not $ISCC) {
    Write-Host "Error: Inno Setup not found" -ForegroundColor Red
    Write-Host ""
    Write-Host "Please install Inno Setup from:" -ForegroundColor Yellow
    Write-Host "  https://jrsoftware.org/isdl.php" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Alternative: Create a portable ZIP instead" -ForegroundColor Yellow
    Write-Host "  .\windows\create-portable.ps1" -ForegroundColor White
    exit 1
}

Write-Host "Found Inno Setup: $ISCC" -ForegroundColor Green
Write-Host ""

# Compile installer
Write-Host "Compiling installer..." -ForegroundColor Yellow
Set-Location $ScriptDir

& $ISCC "installer.iss"

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Green
    Write-Host "Installer created successfully!" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Green
    Write-Host ""

    $InstallerPath = Get-ChildItem -Path $ScriptDir -Filter "BLine-*-Setup.exe" | Select-Object -First 1
    if ($InstallerPath) {
        Write-Host "Installer location: $($InstallerPath.FullName)" -ForegroundColor Cyan
        Write-Host "Size: $([math]::Round($InstallerPath.Length / 1MB, 2)) MB" -ForegroundColor Cyan
    }
    Write-Host ""
} else {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Red
    Write-Host "Installer creation failed!" -ForegroundColor Red
    Write-Host "========================================" -ForegroundColor Red
    exit 1
}
