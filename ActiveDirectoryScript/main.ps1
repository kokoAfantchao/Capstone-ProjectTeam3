<#
.SYNOPSIS
    CYBRIANTE CLI - A Google Cloud CLI-inspired PowerShell tool.
.DESCRIPTION
    A scaffolding script for building a command-line interface with
    groups, subgroups, commands, and interactive prompts.
.EXAMPLE
    ./CybrianteCLI.ps1 auth login
    ./CybrianteCLI.ps1 compute instances list --project=my-app
#>

[CmdletBinding()]
param (
    [Parameter(ValueFromRemainingArguments=$true)]
    [string[]]$CommandArgs
)

# -----------------------------------------------------------------------------
# 1. CORE UTILITIES & CONFIGURATION
# -----------------------------------------------------------------------------

# Simulating a persistent configuration (in memory for now, could be file-based)
$Global:CLI_Config = @{
    "Project" = "default-project"
    "Region"  = "us-central1"
    "Account" = $null
}

function Write-Info { param([string]$Msg) Write-Host $Msg -ForegroundColor White }
function Write-Success { param([string]$Msg) Write-Host $Msg -ForegroundColor Green }
function Write-Warn { param([string]$Msg) Write-Host "WARNING: $Msg" -ForegroundColor Yellow }
function Write-ErrorWithExit { 
    param([string]$Msg) 
    Write-Host "ERROR: $Msg" -ForegroundColor Red
    if (-not $Global:InteractiveMode) { exit 1 }
}

function Get-ConfigValue {
    param($Key)
    if ($Global:CLI_Config.ContainsKey($Key) -and $Global:CLI_Config[$Key]) {
        return $Global:CLI_Config[$Key]
    }
    return $null
}

# -----------------------------------------------------------------------------
# 2. COMMAND MODULES (The business logic)
# -----------------------------------------------------------------------------

function Handle-Setup {
    param($Arguments)
    Write-Info "Initializing Setup..."
    # Add your setup logic here (e.g. creating folders, checking dependencies)
    Invoke-SetupLogic
    Start-Sleep -Milliseconds 500
    Write-Success "Setup completed successfully."
}

function Handle-ExtractData {
    param($Arguments)
    Write-Info "Starting Data Extraction..."
    # Add extraction logic here
    Start-Sleep -Milliseconds 500
    Write-Success "Data extracted."
}

function Handle-PushData {
    param($Arguments)
    Write-Info "Pushing Data to destination..."
    # Add push logic here (e.g. BQ Load)
    Start-Sleep -Milliseconds 500
    Write-Success "Data push complete."
}

function Handle-CleanUp {
    param($Arguments)
    Write-Info "Cleaning up temporary files..."
    # Add cleanup logic here
    Invoke-CleanupLogic
    Start-Sleep -Milliseconds 500
    Write-Success "Cleanup finished."
}

# -----------------------------------------------------------------------------
# 2.5 LOGIC IMPLEMENTATION (Helper functions for specific tasks)
# -----------------------------------------------------------------------------

function Invoke-SetupLogic {
    Write-Info "Starting environment setup..."
    
    # 1. Detect OS and Architecture
    if ($IsWindows) {
        $os = "Windows"
        $arch = $env:PROCESSOR_ARCHITECTURE
    } elseif ($IsMacOS -or $PSVersionTable.OS -match 'Darwin') {
        $os = "macOS"
        $arch = (uname -m).Trim()
    } else {
        $os = "Linux" 
        $arch = (uname -m).Trim()
    }
    Write-Info "Detected OS: $os ($arch)"

    # 2. Check for Python
    $pythonCmd = "python3"
    try {
        if ($IsWindows) { $pythonCmd = "python" }
        $pyVer = & $pythonCmd --version 2>&1
        Write-Success "Python found: $pyVer"
    } catch {
        Write-Warn "System Python not found. Installing portable Python..."
        
        # Portable Python Installation Logic
        $installDir = Get-Location
        $pythonInstallPath = Join-Path $installDir "python"
        
        if (-not (Test-Path $pythonInstallPath)) {
            Write-Info "Fetching latest Python release info..."
            try {
                $latestRelease = Invoke-RestMethod -Uri "https://api.github.com/repos/indygreg/python-build-standalone/releases/latest" -Headers @{"User-Agent" = "PowerShell-Script"}
                $assets = $latestRelease.assets
                
                # Determine asset name pattern based on OS
                $pattern = ""
                if ($os -eq "Windows") {
                    $pattern = "*cpython-3.1*-x86_64-pc-windows-msvc-shared-install_only.tar.gz"
                } elseif ($os -eq "macOS" -and $arch -eq "arm64") {
                    $pattern = "cpython-3.1*-aarch64-apple-darwin-install_only.tar.gz"
                } elseif ($os -eq "macOS") {
                    $pattern = "cpython-3.1*-x86_64-apple-darwin-install_only.tar.gz"
                } else {
                    $pattern = "cpython-3.1*-x86_64-unknown-linux-gnu-install_only.tar.gz"
                }

                $pyAsset = $assets | Where-Object { $_.name -like $pattern } | Select-Object -First 1
                
                if ($pyAsset) {
                    $pyArchive = "python-portable.tar.gz"
                    Write-Info "Downloading $($pyAsset.name)..."
                    Invoke-WebRequest -Uri $pyAsset.browser_download_url -OutFile $pyArchive
                    
                    Write-Info "Extracting Python..."
                    tar -xf $pyArchive
                    
                    if (Test-Path $pyArchive) { Remove-Item $pyArchive }
                    Write-Success "Portable Python installed."
                } else {
                    Write-Error "Could not find compatible Python asset."
                }
            } catch {
                Write-Warn "Failed to download Python automatically. Please install Python 3 manually."
            }
        } else {
            Write-Info "Portable Python folder already exists."
        }
    }

    # 3. Check for GCloud
    if (Get-Command "gcloud" -ErrorAction SilentlyContinue) {
        Write-Success "Google Cloud CLI is already installed."
    } else {
        $gcloudDir = Join-Path (Get-Location) "google-cloud-sdk"
        if (Test-Path $gcloudDir) {
             Write-Success "Google Cloud SDK folder found locally."
        } else {
            Write-Warn "GCloud not found. Installing local version..."
            
            $gcloudUrl = ""
            $gcloudArchive = "google-cloud-sdk.tar.gz"
            
            if ($os -eq "Windows") {
                $gcloudUrl = "https://dl.google.com/dl/cloudsdk/channels/rapid/downloads/google-cloud-cli-windows-x86_64.zip"
                $gcloudArchive = "google-cloud-sdk.zip"
            } elseif ($os -eq "macOS" -and $arch -eq "arm64") {
                $gcloudUrl = "https://dl.google.com/dl/cloudsdk/channels/rapid/downloads/google-cloud-cli-darwin-arm.tar.gz"
            } elseif ($os -eq "macOS") {
                $gcloudUrl = "https://dl.google.com/dl/cloudsdk/channels/rapid/downloads/google-cloud-cli-darwin-x86_64.tar.gz"
            } else {
                $gcloudUrl = "https://dl.google.com/dl/cloudsdk/channels/rapid/downloads/google-cloud-cli-linux-x86_64.tar.gz"
            }
            
            Write-Info "Downloading GCloud CLI..."
            Invoke-WebRequest -Uri $gcloudUrl -OutFile $gcloudArchive
            
            Write-Info "Extracting GCloud CLI..."
            if ($gcloudArchive -like "*.zip") {
                Expand-Archive -Path $gcloudArchive -DestinationPath (Get-Location) -Force
            } else {
                tar -xf $gcloudArchive
            }
            
            if (Test-Path $gcloudArchive) { Remove-Item $gcloudArchive }
            
            # Run Install Script quietly
            $installScript = if ($os -eq "Windows") { Join-Path $gcloudDir "install.bat" } else { Join-Path $gcloudDir "install.sh" }
            if (Test-Path $installScript) {
                 Write-Info "Running GCloud configuration script..."
                 if ($os -eq "Windows") {
                    cmd /c "$installScript" --usage-reporting=false --path-update=false --command-completion=false --quiet
                 } else {
                    & $installScript --usage-reporting=false --path-update=false --command-completion=false --quiet
                 }
                 Write-Success "GCloud installed locally."
            }
        }
    }

    # 4. Set Environment Variables for Session
    $localPy = Join-Path (Get-Location) "python"
    if (Test-Path $localPy) {
        if ($os -eq "Windows") {
             $env:CLOUDSDK_PYTHON = Join-Path $localPy "python.exe"
        } else {
             $env:CLOUDSDK_PYTHON = Join-Path $localPy "bin/python3"
        }
        Write-Info "Configured CLOUDSDK_PYTHON to local python."
    }

    $localGCloudBin = Join-Path (Get-Location) "google-cloud-sdk/bin"
    if (Test-Path $localGCloudBin) {
        $env:PATH = "$localGCloudBin$([IO.Path]::PathSeparator)$env:PATH"
        Write-Info "Added local GCloud to PATH for this session."
    }
}
function Invoke-CleanupLogic {
    Write-Info "Starting cleanup of temporary files..."
    # Add logic to remove any temporary files or folders created during setup
    # PowerShell Cleanup Script
    # Removes locally installed Python/GCloud folders and cleans up environment variables

    $ErrorActionPreference = "Stop"

    $currentDir = Get-Location
    $pythonDir = Join-Path $currentDir "python"
    $gcloudDir = Join-Path $currentDir "google-cloud-sdk"
    # Depending on OS, the path separator might differ for string matching in PATH
    $localGCloudBin = Join-Path $gcloudDir "bin"

    Write-Host ">>> Starting Cleanup Process..." -ForegroundColor Cyan

    # 1. Remove Python Folder
    if (Test-Path $pythonDir) {
        Write-Host "Removing Python directory: $pythonDir ..." -NoNewline
        Remove-Item -Path $pythonDir -Recurse -Force -ErrorAction SilentlyContinue
        if (-not (Test-Path $pythonDir)) { Write-Host " [OK]" -ForegroundColor Green }
        else { Write-Host " [Failed]" -ForegroundColor Red }
    } else {
        Write-Host "Python directory not found. Skipping." -ForegroundColor DarkGray
    }

    # 2. Remove Google Cloud SDK Folder
    if (Test-Path $gcloudDir) {
        Write-Host "Removing Google Cloud SDK directory: $gcloudDir ..." -NoNewline
        Remove-Item -Path $gcloudDir -Recurse -Force -ErrorAction SilentlyContinue
        if (-not (Test-Path $gcloudDir)) { Write-Host " [OK]" -ForegroundColor Green }
        else { Write-Host " [Failed]" -ForegroundColor Red }
    } else {
        Write-Host "Google Cloud SDK directory not found. Skipping." -ForegroundColor DarkGray
    }

    # 3. Unset CLOUDSDK_PYTHON Environment Variable
    if ($env:CLOUDSDK_PYTHON) {
        Write-Host "Removing CLOUDSDK_PYTHON environment variable..." -NoNewline
        $env:CLOUDSDK_PYTHON = $null
        if (-not $env:CLOUDSDK_PYTHON) { Write-Host " [OK]" -ForegroundColor Green }
        else { Write-Host " [Failed]" -ForegroundColor Red }
    } else {
        Write-Host "CLOUDSDK_PYTHON not set. Skipping." -ForegroundColor DarkGray
    }

    # 4. Remove GCloud Bin from PATH
    $sep = [IO.Path]::PathSeparator # usually ';' on Windows, ':' on Mac/Linux

    if ($env:PATH -like "*$localGCloudBin*") {
        Write-Host "Removing GCloud Bin from PATH..."
        
        # Split the path, filter out the local bin, and join it back
        $pathParts = $env:PATH -split $sep
        $newPathParts = $pathParts | Where-Object { $_ -ne $localGCloudBin }
        $env:PATH = $newPathParts -join $sep

        # Verify
        if ($env:PATH -notlike "*$localGCloudBin*") {
            Write-Host "Successfully removed from PATH." -ForegroundColor Green
        } else {
            Write-Host "Failed to remove from PATH." -ForegroundColor Red
        }
    } else {
        Write-Host "GCloud Bin path not found in PATH environment variable." -ForegroundColor DarkGray
    }

    Write-Host "`n>>> Cleanup Complete!" -ForegroundColor Cyan
}
# -----------------------------------------------------------------------------
# 3. MAIN ROUTER
# -----------------------------------------------------------------------------

function Execute-Command {
    param([string[]]$ArgsList)
    
    if ($null -eq $ArgsList -or $ArgsList.Count -eq 0) { return }

    $Group = $ArgsList[0]
    $SubCommand = if ($ArgsList.Count -ge 2) { $ArgsList[1] } else { $null }
    $RestArgs = if ($ArgsList.Count -ge 3) { $ArgsList[2..($ArgsList.Count-1)] } else { @() }

    switch ($Group.ToLower()) {
        "setup"         { Handle-Setup -Arguments $RestArgs }
        "extract-data"  { Handle-ExtractData -Arguments $RestArgs }
        "push-data"     { Handle-PushData -Arguments $RestArgs }
        "clean-up"      { Handle-CleanUp -Arguments $RestArgs }
        "exit"          { exit 0 }
        "quit"          { exit 0 }
        "cls"           { Clear-Host }
        "help"          { Show-Help }
        Default   { 
            Write-Host "Unknown command '$Group'. Type 'help' for options." -ForegroundColor Red 
        }
    }
}

function Show-Help {
    Write-Host "CYBRIANTE CLI - v1.0.0" -ForegroundColor Cyan
    Write-Host "Usage: [GROUP] [COMMAND]"
    Write-Host ""
    Write-Host "Commands:"
    Write-Host "  setup         Initialize the environment  and install dependencies (Python and GCloud CLI if not found)"
    Write-Host "  extract-data  Retrieve data from sources"
    Write-Host "  push-data     Upload data to destinations (e.g., BigQuery)"
    Write-Host "  clean-up      Remove temporary files and uninstall dependencies"
    Write-Host "  exit          Quit the shell"
}

# -----------------------------------------------------------------------------
# 4. ENTRY POINT
# -----------------------------------------------------------------------------

if ($CommandArgs.Count -gt 0) {
    # Argument Mode (One-off command)
    $Global:InteractiveMode = $false
    Execute-Command -ArgsList $CommandArgs
} else {
    # Interactive Shell Mode
    $Global:InteractiveMode = $true
    Clear-Host
    Write-Host "Welcome to CYBRIANTE CLI Interactive Shell" -ForegroundColor Cyan
    Write-Host "Type 'help' for commands, 'exit' to quit." -ForegroundColor Gray
    
    while ($true) {
        $proj = $Global:CLI_Config["Project"]
        $prompt = "CYBRIANTE ($proj) > "
        
        Write-Host $prompt -NoNewline -ForegroundColor Green
        $input = Read-Host
        
        if (-not [string]::IsNullOrWhiteSpace($input)) {
            # Split by space, respecting quotes would require smarter regex but simple split works for basic cases
            $parts = $input -split "\s+"
            Execute-Command -ArgsList $parts
        }
    }
}