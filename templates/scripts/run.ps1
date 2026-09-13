<#
==========================================
News Crawler System - Startup Script
Usage: .\run.ps1 [--debug] [--host address] [--port port]
==========================================
#>

param(
    [string]$Address = "0.0.0.0",
    [int]$Port = 5000,
    [switch]$Debug,
    [switch]$Help
)

# Show help
if ($Help) {
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  News Crawler System - Startup Args" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Usage: .\run.ps1 [options]" -ForegroundColor White
    Write-Host ""
    Write-Host "Options:" -ForegroundColor White
    Write-Host "  --host <addr>  Bind address (default: 0.0.0.0)" -ForegroundColor Gray
    Write-Host "  --port <port>  Port number (default: 5000)" -ForegroundColor Gray
    Write-Host "  --debug        Debug mode" -ForegroundColor Gray
    Write-Host "  --help         Show this help" -ForegroundColor Gray
    Write-Host ""
    Write-Host "Examples:" -ForegroundColor White
    Write-Host "  .\run.ps1                    # Default start" -ForegroundColor Gray
    Write-Host "  .\run.ps1 --debug            # Debug mode" -ForegroundColor Gray
    Write-Host "  .\run.ps1 --port 8080        # Custom port" -ForegroundColor Gray
    Write-Host "  .\run.ps1 --host 127.0.0.1   # Local access" -ForegroundColor Gray
    exit 0
}

# Get script directory and project root
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path (Join-Path $ScriptDir "..\..")
Set-Location $ProjectRoot

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  News Crawler System - Web Platform" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check virtual environment
$venvPath = Join-Path $ProjectRoot ".venv"
$pythonPath = Join-Path $venvPath "Scripts\python.exe"

if (-not (Test-Path $pythonPath)) {
    # Try Linux/Mac path
    $pythonPath = Join-Path $venvPath "bin/python"
}

if (-not (Test-Path $pythonPath)) {
    Write-Host "x Venv not found!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Please run setup_venv.ps1 first:" -ForegroundColor Yellow
    Write-Host "  .\scripts\setup_venv.ps1" -ForegroundColor Gray
    exit 1
}

Write-Host "v Venv found" -ForegroundColor Green
Write-Host ""

# Build startup command
$appPath = Join-Path $ProjectRoot "app.py"
# Use array for arguments to handle spaces correctly
$processArgs = @($appPath, "--host", $Address, "--port", $Port.ToString())

if ($Debug) {
    $processArgs += "--debug"
    Write-Host "Debug Mode: Enabled" -ForegroundColor Yellow
} else {
    Write-Host "Debug Mode: Disabled" -ForegroundColor Gray
}

Write-Host ""
Write-Host "Starting service..." -ForegroundColor Yellow
Write-Host "Access URL: http://${Address}:${Port}" -ForegroundColor Cyan
Write-Host ""
Write-Host "Press Ctrl+C to stop service" -ForegroundColor Gray
Write-Host ""

# Start application
& $pythonPath $processArgs
