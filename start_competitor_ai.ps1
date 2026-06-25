param()

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

function Show-Logo {
  Clear-Host
  $logo = @'
   ____                           _   _ _                  _    ___
  / ___|___  _ __ ___  _ __   ___| |_(_) |_ ___  _ __     / \  |_ _|
 | |   / _ \| '_ ` _ \| '_ \ / _ \ __| | __/ _ \| '__|   / _ \  | |
 | |__| (_) | | | | | | |_) |  __/ |_| | || (_) | |     / ___ \ | |
  \____\___/|_| |_| |_| .__/ \___|\__|_|\__\___/|_|    /_/   \_\___|
                      |_|
'@
  Write-Host $logo -ForegroundColor Yellow
}

function Wait-Return {
  param([string]$Prompt = "Press Enter to return to the menu")
  [void](Read-Host $Prompt)
}

function Write-LocalPythonConfig {
  param([string]$PythonPath)

  $pythonFullPath = [System.IO.Path]::GetFullPath($PythonPath)
  $configPath = Join-Path $ProjectRoot ".local_env.bat"
  $pythonPathFile = Join-Path $ProjectRoot ".local_python_path.txt"
  $localEncoding = [System.Text.Encoding]::Default
  $lines = @(
    "@echo off",
    "set `"COMPETITOR_AI_PROJECT_ROOT=$ProjectRoot`"",
    "set `"COMPETITOR_AI_PYTHON=$pythonFullPath`"",
    "set `"COMPETITOR_AI_VENV=`""
  )

  [System.IO.File]::WriteAllLines($configPath, $lines, $localEncoding)
  [System.IO.File]::WriteAllText($pythonPathFile, $pythonFullPath, $localEncoding)
  Write-Host "Local environment config written:" -ForegroundColor Green
  Write-Host "  $configPath"
  Write-Host "Saved Python path:" -ForegroundColor Green
  Write-Host "  $pythonFullPath"
}

function Resolve-PythonExecutable {
  param([string]$InputText)

  if ([string]::IsNullOrWhiteSpace($InputText)) {
    return $null
  }

  $candidate = $InputText.Trim().Trim('"')
  try {
    $probe = "import sys; print(sys.executable)"
    $output = @(& $candidate -c $probe 2>$null)
    if ($LASTEXITCODE -ne 0 -or $output.Count -lt 1) {
      return $null
    }
    $resolved = [string]$output[0]
    if (Test-Path -LiteralPath $resolved) {
      return [System.IO.Path]::GetFullPath($resolved)
    }
    return $null
  } catch {
    return $null
  }
}

function Read-ConfiguredPython {
  $pythonPathFile = Join-Path $ProjectRoot ".local_python_path.txt"
  $configPath = Join-Path $ProjectRoot ".local_env.bat"
  $localEncoding = [System.Text.Encoding]::Default

  if (Test-Path -LiteralPath $pythonPathFile) {
    $saved = [System.IO.File]::ReadAllText($pythonPathFile, $localEncoding).Trim()
    if (-not [string]::IsNullOrWhiteSpace($saved)) {
      return $saved
    }
  }

  if (Test-Path -LiteralPath $configPath) {
    foreach ($line in [System.IO.File]::ReadAllLines($configPath, $localEncoding)) {
      if ($line -match '^set "COMPETITOR_AI_PYTHON=(.*)"$') {
        return $Matches[1]
      }
    }
  }

  $venvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
  if (Test-Path -LiteralPath $venvPython) {
    return $venvPython
  }

  return $null
}

function Invoke-InstallEnv {
  Show-Logo
  Write-Host ""
  Write-Host "Starting the installer..."
  Write-Host ""
  & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $ProjectRoot "install_project_env.ps1")
  $code = if ($null -eq $LASTEXITCODE) { 0 } else { $LASTEXITCODE }
  Write-Host ""
  if ($code -eq 0) {
    Write-Host "Installation complete. Local environment config was written to .local_env.bat." -ForegroundColor Green
  } else {
    Write-Host "The installer returned an error. Check the log above." -ForegroundColor Red
  }
  Wait-Return
}

function Set-ExistingPython {
  Show-Logo
  Write-Host ""
  Write-Host "Enter a Python interpreter that already has the required dependencies installed."
  Write-Host "You can enter the full path to python.exe or a command name: python / python3 / py"
  Write-Host "Do not include extra arguments."
  Write-Host ""

  $inputText = Read-Host "Python path or command"
  $resolved = Resolve-PythonExecutable -InputText $inputText
  if ($null -eq $resolved) {
    Write-Host ""
    Write-Host "Cannot run this Python interpreter:" -ForegroundColor Red
    Write-Host "  $inputText"
    Write-Host "Check the path, or enter python / python3 / py."
    Wait-Return
    return
  }

  Write-Host ""
  Write-LocalPythonConfig -PythonPath $resolved
  Wait-Return
}

function Start-WebServer {
  $python = Read-ConfiguredPython
  if ([string]::IsNullOrWhiteSpace($python)) {
    Write-Host ""
    Write-Host "No local environment config .local_env.bat was found, and .venv was not found either." -ForegroundColor Yellow
    Write-Host "Choose [1] Install/update Python environment first, or choose [3] Specify an existing Python."
    Wait-Return
    return
  }

  if (-not (Test-Path -LiteralPath $python)) {
    Write-Host ""
    Write-Host "The saved Python path does not exist:" -ForegroundColor Red
    Write-Host "  $python"
    Write-Host "Choose [1] Install/update Python environment again, or choose [3] Specify an existing Python."
    Wait-Return
    return
  }

  $port = "8000"
  Write-Host ""
  $portInput = Read-Host "Enter the server port, or press Enter to use 8000"
  if (-not [string]::IsNullOrWhiteSpace($portInput)) {
    $port = $portInput.Trim()
  }

  Show-Logo
  Write-Host ""
  Write-Host "Using Python:"
  Write-Host "  $python"
  Write-Host ""
  Write-Host "Starting the web server:"
  Write-Host "  http://127.0.0.1:$port"
  Write-Host ""
  & $python (Join-Path $ProjectRoot "backend\server.py") $port
  Write-Host ""
  Write-Host "The server has exited."
  Wait-Return
}

while ($true) {
  Show-Logo
  Write-Host ""
  Write-Host "[1] Install/update Python environment"
  Write-Host "[2] Start web server with local Python"
  Write-Host "[3] Use an existing Python environment"
  Write-Host "[4] Exit"
  Write-Host ""

  $choice = Read-Host "Choose an action"
  switch ($choice.Trim()) {
    "1" { Invoke-InstallEnv }
    "2" { Start-WebServer }
    "3" { Set-ExistingPython }
    "4" { exit 0 }
    default {
      Write-Host ""
      Write-Host "Invalid input. Please choose again." -ForegroundColor Yellow
      Wait-Return
    }
  }
}
