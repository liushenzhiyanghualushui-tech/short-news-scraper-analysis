<#==========================================
# 新闻采集系统 - 虚拟环境设置脚本
# 运行方式: .\setup_venv.ps1
#==========================================

$ErrorActionPreference = "Stop"

# 获取脚本所在目录
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  新闻数据采集系统 - 虚拟环境设置" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 检查 Python 是否安装
Write-Host "[1/4] 检查 Python 环境..." -ForegroundColor Yellow
try {
    $pythonVersion = python --version 2>&1
    Write-Host "  ✓ Python 已安装: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "  ✗ Python 未找到，请先安装 Python 3.8+" -ForegroundColor Red
    Write-Host "    下载地址: https://www.python.org/downloads/" -ForegroundColor Yellow
    exit 1
}

# 创建虚拟环境
Write-Host ""
Write-Host "[2/4] 创建虚拟环境..." -ForegroundColor Yellow
$venvPath = Join-Path $ScriptDir ".venv"
if (Test-Path $venvPath) {
    Write-Host "  ⚠  虚拟环境已存在，是否重新创建? [y/N]" -ForegroundColor Yellow
    $choice = Read-Host
    if ($choice -eq 'y' -or $choice -eq 'Y') {
        Write-Host "  正在删除现有虚拟环境..." -ForegroundColor Yellow
        Remove-Item -Path $venvPath -Recurse -Force
    } else {
        Write-Host "  跳过虚拟环境创建" -ForegroundColor Gray
    }
}

if (-not (Test-Path $venvPath)) {
    python -m venv .venv
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  ✓ 虚拟环境创建成功" -ForegroundColor Green
    } else {
        Write-Host "  ✗ 虚拟环境创建失败" -ForegroundColor Red
        exit 1
    }
}

# 激活虚拟环境并安装依赖
Write-Host ""
Write-Host "[3/4] 安装 Python 依赖包..." -ForegroundColor Yellow

# 确定 pip 路径
$pipPath = Join-Path $venvPath "Scripts\pip.exe"
if (-not (Test-Path $pipPath)) {
    # 尝试 Linux/Mac 路径
    $pipPath = Join-Path $venvPath "bin/pip"
}

& $pipPath install --upgrade pip --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Host "  ⚠ pip 升级失败，继续安装依赖..." -ForegroundColor Yellow
}

# 安装 requirements.txt 中的依赖
$requirementsPath = Join-Path $ScriptDir "requirements.txt"
& $pipPath install -r $requirementsPath

if ($LASTEXITCODE -eq 0) {
    Write-Host "  ✓ 依赖安装完成" -ForegroundColor Green
} else {
    Write-Host "  ✗ 依赖安装失败" -ForegroundColor Red
    exit 1
}

# 完成
Write-Host ""
Write-Host "[4/4] 设置完成!" -ForegroundColor Yellow
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  虚拟环境已配置完成!" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "启动项目:" -ForegroundColor White
Write-Host "  .\run.ps1                    # 启动 Web 服务" -ForegroundColor Gray
Write-Host "  .\run.ps1 --debug            # 调试模式启动" -ForegroundColor Gray
Write-Host "  .\run.ps1 --host 127.0.0.1   # 指定地址" -ForegroundColor Gray
Write-Host ""
Write-Host "手动激活虚拟环境:" -ForegroundColor White
Write-Host "  .\.venv\Scripts\Activate.ps1" -ForegroundColor Gray
Write-Host "  pip install -r requirements.txt" -ForegroundColor Gray
Write-Host "  python app.py" -ForegroundColor Gray
Write-Host ""

