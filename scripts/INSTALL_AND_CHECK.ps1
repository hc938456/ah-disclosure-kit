param(
    [string]$Extras = "pdf",
    [switch]$SkipMcpRegistration,
    [switch]$SkipSkillCopy,
    [switch]$CheckTesseract
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Write-Ok {
    param([string]$Message)
    Write-Host "[OK] $Message" -ForegroundColor Green
}

function Write-Warn {
    param([string]$Message)
    Write-Host "[WARN] $Message" -ForegroundColor Yellow
}

function Write-Fail {
    param([string]$Message)
    Write-Host "[FAIL] $Message" -ForegroundColor Red
}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path (Join-Path $ScriptDir "..")
Set-Location $ProjectRoot

Write-Step "Checking Python"
$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    Write-Fail "Python was not found on PATH. Install Python 3.11+ first, then rerun this script."
    exit 1
}

$pyInfoJson = & python -c "import json,sys; print(json.dumps({'version': sys.version.split()[0], 'major': sys.version_info.major, 'minor': sys.version_info.minor, 'executable': sys.executable}))"
$pyInfo = $pyInfoJson | ConvertFrom-Json
Write-Host "Python: $($pyInfo.version)"
Write-Host "Executable: $($pyInfo.executable)"
if (($pyInfo.major -lt 3) -or (($pyInfo.major -eq 3) -and ($pyInfo.minor -lt 11))) {
    Write-Fail "Python 3.11+ is required. This script does not install Python."
    exit 1
}
Write-Ok "Python version is supported"

Write-Step "Installing Python package dependencies"
& python -m pip install --upgrade pip
if ([string]::IsNullOrWhiteSpace($Extras)) {
    & python -m pip install -e .
} else {
    & python -m pip install -e ".[$Extras]"
}
Write-Ok "Python package dependencies installed with extras: $Extras"

Write-Step "Preparing default data directory"
$DataDir = (& python -c "from ah_disclosure.core.paths import get_data_dir; print(get_data_dir())").Trim()
$Dirs = @(
    "raw\cninfo",
    "raw\hkex",
    "raw\eastmoney",
    "raw\manual",
    "staging\downloads",
    "staging\extraction",
    "staging\ocr",
    "parsed",
    "normalized",
    "index",
    "cache",
    "logs",
    "manifests"
)
foreach ($dir in $Dirs) {
    New-Item -ItemType Directory -Force -Path (Join-Path $DataDir $dir) | Out-Null
}
Write-Ok "Default data directory is ready: $DataDir"

if (-not $SkipSkillCopy) {
    Write-Step "Copying Codex skill"
    $SkillSource = Join-Path $ProjectRoot "skills\ah-disclosure"
    $SkillTargetRoot = Join-Path $env:USERPROFILE ".codex\skills"
    $SkillTarget = Join-Path $SkillTargetRoot "ah-disclosure"
    if (-not (Test-Path -LiteralPath $SkillSource)) {
        Write-Fail "Skill source directory not found: $SkillSource"
        exit 1
    }
    New-Item -ItemType Directory -Force -Path $SkillTargetRoot | Out-Null
    Copy-Item -Recurse -Force -LiteralPath $SkillSource -Destination $SkillTargetRoot
    Write-Ok "Skill copied to: $SkillTarget"
}

if (-not $SkipMcpRegistration) {
    Write-Step "Registering MCP server"
    $claudeCmd = Get-Command claude -ErrorAction SilentlyContinue
    if ($claudeCmd) {
        & claude mcp add --transport stdio --scope user ah-disclosure "python -m ah_disclosure.mcp_server"
        Write-Ok "MCP registration command completed"
    } else {
        Write-Warn "Claude CLI was not found on PATH. Skipped MCP registration."
        Write-Warn "Run manually later: claude mcp add --transport stdio --scope user ah-disclosure `"python -m ah_disclosure.mcp_server`""
    }
}

Write-Step "Verifying installation"
$version = & python -m ah_disclosure.cli --version
Write-Host "ah-disclosure-kit version: $version"
if ($version.Trim() -ne "1.0.0") {
    Write-Warn "Expected version 1.0.0, got $version"
} else {
    Write-Ok "Version check passed"
}

$serverInfo = & python -m ah_disclosure.cli server-info
Write-Host $serverInfo
Write-Ok "CLI server-info check completed"

Write-Step "Checking optional system tools"
if ($CheckTesseract) {
    $tesseractCmd = Get-Command tesseract -ErrorAction SilentlyContinue
    if ($tesseractCmd) {
        & tesseract --version
        Write-Ok "Tesseract is available"
    } else {
        Write-Warn "Tesseract was not found. This script does not install Tesseract."
    }
} else {
    Write-Warn "Tesseract check skipped. This script does not install Tesseract."
}

Write-Step "Done"
Write-Ok "ah-disclosure-kit install/check completed"
