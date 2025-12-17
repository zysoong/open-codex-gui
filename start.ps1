# Open Claude UI Start Script for Windows (PowerShell)
# This script sets up the environment using embedded/portable runtimes
# and starts the services without polluting the system PATH
# Run with: powershell -ExecutionPolicy Bypass -File start.ps1

param(
    [switch]$SkipDocker,
    [switch]$NoStart
)

$ErrorActionPreference = "Stop"

# Configuration - versions to download
$PYTHON_VERSION = "3.12.7"
$NODE_VERSION = "20.18.0"

# Paths for embedded runtimes
$script:ScriptDir = if ($PSScriptRoot) {
    $PSScriptRoot
} elseif ($MyInvocation.MyCommand.Path) {
    Split-Path -Parent $MyInvocation.MyCommand.Path
} else {
    Get-Location
}

$LocalVenv = Join-Path $script:ScriptDir "local_venv"
$PythonDir = Join-Path $LocalVenv "python"
$NodeDir = Join-Path $LocalVenv "node"
$PythonExe = Join-Path $PythonDir "python.exe"
$PipExe = Join-Path $PythonDir "Scripts\pip.exe"
$PoetryExe = Join-Path $PythonDir "Scripts\poetry.exe"
$NodeExe = Join-Path $NodeDir "node.exe"
$NpmCmd = Join-Path $NodeDir "npm.cmd"
$NpxCmd = Join-Path $NodeDir "npx.cmd"

function Write-Header {
    Write-Host ""
    Write-Host "+=============================================================+" -ForegroundColor Blue
    Write-Host "|                  Open Claude UI Setup                       |" -ForegroundColor Blue
    Write-Host "|            Self-hosted Claude interface                     |" -ForegroundColor Blue
    Write-Host "|                                                             |" -ForegroundColor Blue
    Write-Host "|  Using embedded runtimes (no system PATH modification)      |" -ForegroundColor Blue
    Write-Host "+=============================================================+" -ForegroundColor Blue
    Write-Host ""
}

function Write-Step {
    param([string]$Message)
    Write-Host "[STEP] " -ForegroundColor Green -NoNewline
    Write-Host $Message
}

function Write-Warning {
    param([string]$Message)
    Write-Host "[WARNING] " -ForegroundColor Yellow -NoNewline
    Write-Host $Message
}

function Write-Error {
    param([string]$Message)
    Write-Host "[ERROR] " -ForegroundColor Red -NoNewline
    Write-Host $Message
}

function Write-Success {
    param([string]$Message)
    Write-Host "[SUCCESS] " -ForegroundColor Green -NoNewline
    Write-Host $Message
}

function Test-Command {
    param([string]$Command)
    $null = Get-Command $Command -ErrorAction SilentlyContinue
    return $?
}

function Ensure-Directory {
    param([string]$Path)
    if (-not (Test-Path $Path)) {
        New-Item -ItemType Directory -Path $Path -Force | Out-Null
    }
}

function Install-EmbeddedPython {
    Write-Step "Setting up embedded Python $PYTHON_VERSION..."

    if (Test-Path $PythonExe) {
        $version = & $PythonExe --version 2>&1
        Write-Success "Embedded Python already installed: $version"
        return
    }

    Ensure-Directory $LocalVenv

    # Download Python embeddable package
    $pythonZip = Join-Path $LocalVenv "python.zip"
    $pythonUrl = "https://www.python.org/ftp/python/$PYTHON_VERSION/python-$PYTHON_VERSION-embed-amd64.zip"

    Write-Step "Downloading Python $PYTHON_VERSION from python.org..."
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -Uri $pythonUrl -OutFile $pythonZip -UseBasicParsing
    } catch {
        Write-Error "Failed to download Python: $_"
        exit 1
    }

    Write-Step "Extracting Python..."
    Ensure-Directory $PythonDir
    Expand-Archive -Path $pythonZip -DestinationPath $PythonDir -Force
    Remove-Item $pythonZip

    # Enable pip in embedded Python by modifying python*._pth file
    $pthFile = Get-ChildItem -Path $PythonDir -Filter "python*._pth" | Select-Object -First 1
    if ($pthFile) {
        $pthContent = Get-Content $pthFile.FullName
        # Uncomment "import site" line to enable pip
        $pthContent = $pthContent -replace "^#import site", "import site"
        # Add Lib\site-packages for pip installations
        $newContent = @()
        foreach ($line in $pthContent) {
            $newContent += $line
        }
        $newContent += "Lib\site-packages"
        Set-Content $pthFile.FullName $newContent
    }

    # Create Lib\site-packages directory
    $sitePackages = Join-Path $PythonDir "Lib\site-packages"
    Ensure-Directory $sitePackages

    # Download and install pip
    Write-Step "Installing pip..."
    $getPipUrl = "https://bootstrap.pypa.io/get-pip.py"
    $getPipPath = Join-Path $LocalVenv "get-pip.py"
    Invoke-WebRequest -Uri $getPipUrl -OutFile $getPipPath -UseBasicParsing
    & $PythonExe $getPipPath --no-warn-script-location
    Remove-Item $getPipPath

    Write-Success "Embedded Python $PYTHON_VERSION installed"
}

function Install-Poetry {
    Write-Step "Setting up Poetry..."

    if (Test-Path $PoetryExe) {
        $version = & $PoetryExe --version 2>&1
        Write-Success "Poetry already installed: $version"
        return
    }

    Write-Step "Installing Poetry via pip..."
    & $PythonExe -m pip install poetry --no-warn-script-location

    if (-not (Test-Path $PoetryExe)) {
        Write-Error "Poetry installation failed"
        exit 1
    }

    $version = & $PoetryExe --version 2>&1
    Write-Success "Poetry installed: $version"
}

function Install-EmbeddedNode {
    Write-Step "Setting up embedded Node.js $NODE_VERSION..."

    if (Test-Path $NodeExe) {
        $version = & $NodeExe --version 2>&1
        Write-Success "Embedded Node.js already installed: $version"
        return
    }

    Ensure-Directory $LocalVenv

    # Download Node.js standalone
    $nodeZip = Join-Path $LocalVenv "node.zip"
    $nodeUrl = "https://nodejs.org/dist/v$NODE_VERSION/node-v$NODE_VERSION-win-x64.zip"

    Write-Step "Downloading Node.js $NODE_VERSION from nodejs.org..."
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -Uri $nodeUrl -OutFile $nodeZip -UseBasicParsing
    } catch {
        Write-Error "Failed to download Node.js: $_"
        exit 1
    }

    Write-Step "Extracting Node.js..."
    $tempExtract = Join-Path $LocalVenv "node-temp"
    Expand-Archive -Path $nodeZip -DestinationPath $tempExtract -Force

    # Move from nested folder to target
    $extractedFolder = Get-ChildItem -Path $tempExtract -Directory | Select-Object -First 1
    if ($extractedFolder) {
        if (Test-Path $NodeDir) {
            Remove-Item $NodeDir -Recurse -Force
        }
        Move-Item -Path $extractedFolder.FullName -Destination $NodeDir -Force
    }
    Remove-Item $tempExtract -Recurse -Force
    Remove-Item $nodeZip

    $version = & $NodeExe --version 2>&1
    Write-Success "Embedded Node.js installed: $version"
}

function Install-Docker {
    Write-Step "Checking Docker installation..."

    if (Test-Command "docker") {
        Write-Success "Docker is installed"
        return
    }

    Write-Step "Installing Docker Desktop via winget..."
    try {
        winget install -e --id Docker.DockerDesktop --accept-source-agreements --accept-package-agreements
        Write-Warning "Please start Docker Desktop manually after installation"
        Write-Warning "You may need to restart your computer for Docker to work properly"
    } catch {
        Write-Warning "Could not install Docker via winget. Trying chocolatey..."
        try {
            # Install Chocolatey if not present
            if (-not (Test-Command "choco")) {
                Write-Step "Installing Chocolatey..."
                Set-ExecutionPolicy Bypass -Scope Process -Force
                [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
                Invoke-Expression ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
                $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
            }
            choco install docker-desktop -y
            Write-Warning "Please start Docker Desktop manually after installation"
            Write-Warning "You may need to restart your computer for Docker to work properly"
        } catch {
            Write-Warning "Could not install Docker automatically. Please install Docker Desktop manually."
            Write-Warning "Download from: https://www.docker.com/products/docker-desktop/"
        }
    }
}

function Setup-Backend {
    Write-Step "Setting up backend..."

    Push-Location (Join-Path $script:ScriptDir "backend")

    try {
        # CRITICAL: Temporarily modify PATH to prioritize embedded Python
        # This prevents Poetry from finding WindowsApps stub or other system Python
        $originalPath = $env:Path
        $env:Path = "$PythonDir;$PythonDir\Scripts;$env:Path"
        Write-Step "Temporarily added embedded Python to PATH"

        # Remove any existing .venv that might reference wrong Python
        if (Test-Path ".venv") {
            Write-Step "Removing existing .venv to ensure clean setup..."
            Remove-Item -Recurse -Force ".venv" -ErrorAction SilentlyContinue
        }

        # Configure Poetry to create virtualenv in project directory
        Write-Step "Configuring Poetry..."
        & $PoetryExe config virtualenvs.in-project true --local

        # Clear any cached Poetry environments for this project
        $poetryCacheDirs = @(
            "$env:LOCALAPPDATA\pypoetry\virtualenvs",
            "$env:APPDATA\pypoetry\virtualenvs"
        )
        foreach ($cacheDir in $poetryCacheDirs) {
            if (Test-Path $cacheDir) {
                $projectName = "backend"
                $oldEnvs = Get-ChildItem -Path $cacheDir -Directory -ErrorAction SilentlyContinue | Where-Object { $_.Name -like "$projectName-*" }
                foreach ($oldEnv in $oldEnvs) {
                    Write-Step "Removing cached virtualenv: $($oldEnv.Name)"
                    Remove-Item -Recurse -Force $oldEnv.FullName -ErrorAction SilentlyContinue
                }
            }
        }

        # Tell Poetry to use our embedded Python explicitly
        Write-Step "Setting Poetry to use embedded Python: $PythonExe"
        & $PoetryExe env use $PythonExe

        if ($LASTEXITCODE -ne 0) {
            Write-Warning "poetry env use failed, trying alternative method..."
            # Alternative: set POETRY_PYTHON environment variable
            $env:POETRY_PYTHON = $PythonExe
        }

        # Verify Poetry is using correct Python before installing
        Write-Step "Verifying Poetry Python configuration..."
        $poetryEnvInfo = & $PoetryExe env info 2>&1
        Write-Host $poetryEnvInfo

        # Install dependencies using embedded Poetry
        Write-Step "Installing backend dependencies (this may take a few minutes)..."
        & $PoetryExe install --with dev

        if ($LASTEXITCODE -ne 0) {
            Write-Error "Failed to install backend dependencies"
            # Restore PATH before exiting
            $env:Path = $originalPath
            Pop-Location
            exit 1
        }

        # Create .env if it doesn't exist
        if (-not (Test-Path ".env")) {
            Write-Step "Creating .env file..."

            # Generate encryption key using the Poetry-managed Python
            $encryptionKey = & $PoetryExe run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" 2>&1

            if ($LASTEXITCODE -ne 0) {
                # Fallback to embedded Python directly
                Write-Warning "Using embedded Python for key generation"
                $encryptionKey = & $PythonExe -c "import secrets; print(secrets.token_urlsafe(32))"
            }

            if (Test-Path ".env.example") {
                Copy-Item ".env.example" ".env"
                $content = Get-Content ".env" -Raw
                if ($content -match "MASTER_ENCRYPTION_KEY=") {
                    $content = $content -replace "MASTER_ENCRYPTION_KEY=.*", "MASTER_ENCRYPTION_KEY=$encryptionKey"
                } else {
                    $content += "`nMASTER_ENCRYPTION_KEY=$encryptionKey"
                }
                Set-Content ".env" $content
            } else {
                @"
# Open Claude UI Backend Configuration
DATABASE_URL=sqlite+aiosqlite:///./data/open-claude-ui.db
HOST=127.0.0.1
PORT=8000
CORS_ORIGINS=http://localhost:3000,http://localhost:5173,http://localhost:5174
DOCKER_CONTAINER_POOL_SIZE=5
MASTER_ENCRYPTION_KEY=$encryptionKey
"@ | Set-Content ".env"
            }

            Write-Success ".env file created with encryption key"
        }

        # Create data directory
        if (-not (Test-Path "data")) {
            New-Item -ItemType Directory -Path "data" | Out-Null
        }

        Write-Success "Backend setup complete"
    }
    finally {
        # Always restore original PATH
        if ($originalPath) {
            $env:Path = $originalPath
        }
        Pop-Location
    }
}

function Setup-Frontend {
    Write-Step "Setting up frontend..."

    Push-Location (Join-Path $script:ScriptDir "frontend")

    try {
        # Install dependencies using embedded npm
        Write-Step "Installing frontend dependencies (this may take a few minutes)..."
        & $NpmCmd install

        if ($LASTEXITCODE -ne 0) {
            Write-Error "Failed to install frontend dependencies"
            Pop-Location
            exit 1
        }

        Write-Success "Frontend setup complete"
    }
    finally {
        Pop-Location
    }
}

function Build-DockerImages {
    $dockerAvailable = $false

    if (Test-Command "docker") {
        # Check if Docker daemon is running
        $null = docker info 2>&1
        if ($?) {
            $dockerAvailable = $true
        }
    }

    if ($dockerAvailable) {
        Write-Step "Building Docker sandbox images..."

        Push-Location (Join-Path $script:ScriptDir "backend\app\core\sandbox\environments")

        try {
            # Build only the default Python image for quick setup
            if (Test-Path "python3.13.Dockerfile") {
                docker build -t openclaudeui-env-python3.13:latest -f python3.13.Dockerfile .
                if (-not $?) {
                    Write-Warning "Failed to build Python 3.13 image"
                } else {
                    Write-Success "Docker images built"
                }
            }
        }
        finally {
            Pop-Location
        }
    } else {
        Write-Warning "Docker is not running. Skipping Docker image build."
        Write-Warning "Start Docker Desktop and run: cd backend\app\core\sandbox\environments; .\build_images.ps1"
    }
}

function Test-Installation {
    Write-Step "Verifying installation..."

    $errors = 0

    if (-not (Test-Path $PythonExe)) {
        Write-Error "Embedded Python is not installed"
        $errors++
    } else {
        $pyVersion = & $PythonExe --version 2>&1
        Write-Success "Python: $pyVersion"
    }

    if (-not (Test-Path $NodeExe)) {
        Write-Error "Embedded Node.js is not installed"
        $errors++
    } else {
        $nodeVersion = & $NodeExe --version 2>&1
        Write-Success "Node.js: $nodeVersion"
    }

    if (-not (Test-Path $PoetryExe)) {
        Write-Error "Poetry is not installed"
        $errors++
    } else {
        $poetryVersion = & $PoetryExe --version 2>&1
        Write-Success "Poetry: $poetryVersion"
    }

    if (-not (Test-Command "docker")) {
        Write-Warning "Docker is not installed (optional but recommended)"
    } else {
        Write-Success "Docker: installed"
    }

    if ($errors -gt 0) {
        Write-Error "Installation verification failed with $errors errors"
        exit 1
    }

    Write-Success "All required dependencies are installed!"
}

function Write-Usage {
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Green
    Write-Host "                    Setup Complete!                          " -ForegroundColor Green
    Write-Host "============================================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "Embedded runtimes installed in: $LocalVenv"
    Write-Host ""
    Write-Host "To start Open Claude UI, run this script again without -NoStart:"
    Write-Host "    powershell -ExecutionPolicy Bypass -File start.ps1"
    Write-Host ""
    Write-Host "Or start manually:"
    Write-Host ""
    Write-Host "  1. Start the backend:"
    Write-Host "     cd backend"
    Write-Host "     $PoetryExe run python -m app.main"
    Write-Host ""
    Write-Host "  2. Start the frontend (in a new terminal):"
    Write-Host "     cd frontend"
    Write-Host "     $NpmCmd run dev"
    Write-Host ""
    Write-Host "  3. Open http://localhost:5173 in your browser"
    Write-Host ""
}

function Start-Services {
    Write-Step "Starting Open Claude UI services..."

    # Temporarily modify PATH for verification
    $originalPath = $env:Path
    $env:Path = "$PythonDir;$PythonDir\Scripts;$NodeDir;$env:Path"

    # Verify Poetry can run Python in the backend directory
    Write-Step "Verifying Poetry environment..."
    Push-Location (Join-Path $script:ScriptDir "backend")
    try {
        $testResult = & $PoetryExe run python --version 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Error "Poetry cannot run Python. Error: $testResult"
            Pop-Location
            $env:Path = $originalPath
            return
        }
        Write-Success "Poetry Python is working: $testResult"
    } catch {
        Write-Error "Failed to verify Poetry environment: $_"
        Pop-Location
        $env:Path = $originalPath
        return
    }
    Pop-Location

    # Restore PATH
    $env:Path = $originalPath

    # Start backend in a new window - include PATH modification in the spawned shell
    Write-Step "Starting backend server..."
    $backendCmd = "`$env:Path = '$PythonDir;$PythonDir\Scripts;' + `$env:Path; cd '$($script:ScriptDir)\backend'; & '$PoetryExe' run python -m app.main"
    Start-Process -FilePath "powershell" -ArgumentList "-NoExit", "-Command", $backendCmd

    # Wait for backend to be ready
    Write-Step "Waiting for backend to start (max 30 seconds)..."
    $backendReady = $false
    for ($i = 1; $i -le 30; $i++) {
        Start-Sleep -Seconds 1
        try {
            $response = Invoke-WebRequest -Uri http://localhost:8000/ -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -eq 200) {
                Write-Success "Backend is running at http://localhost:8000"
                $backendReady = $true
                break
            }
        } catch {
            # Still waiting...
            if ($i % 10 -eq 0) {
                Write-Host "  Still waiting... ($i seconds)"
            }
        }
    }

    if (-not $backendReady) {
        Write-Warning "Backend did not respond within 30 seconds."
        Write-Warning "Check the backend terminal window for errors."
    }

    # Start frontend in a new window - include PATH modification in the spawned shell
    Write-Step "Starting frontend server..."
    $frontendCmd = "`$env:Path = '$NodeDir;' + `$env:Path; cd '$($script:ScriptDir)\frontend'; & '$NpmCmd' run dev"
    Start-Process -FilePath "powershell" -ArgumentList "-NoExit", "-Command", $frontendCmd

    # Wait for frontend to be ready
    Write-Step "Waiting for frontend to start (max 30 seconds)..."
    $frontendReady = $false
    for ($i = 1; $i -le 30; $i++) {
        Start-Sleep -Seconds 1
        try {
            $response = Invoke-WebRequest -Uri http://localhost:5173/ -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -eq 200) {
                Write-Success "Frontend is running at http://localhost:5173"
                $frontendReady = $true
                break
            }
        } catch {
            # Still waiting...
            if ($i % 10 -eq 0) {
                Write-Host "  Still waiting... ($i seconds)"
            }
        }
    }

    if (-not $frontendReady) {
        Write-Warning "Frontend did not respond within 30 seconds."
        Write-Warning "Check the frontend terminal window for errors."
    }

    Write-Host ""
    if ($backendReady -and $frontendReady) {
        Write-Host "============================================================" -ForegroundColor Green
        Write-Host "              Open Claude UI is running!                     " -ForegroundColor Green
        Write-Host "============================================================" -ForegroundColor Green
    } else {
        Write-Host "============================================================" -ForegroundColor Yellow
        Write-Host "          Open Claude UI started with warnings               " -ForegroundColor Yellow
        Write-Host "============================================================" -ForegroundColor Yellow
    }
    Write-Host ""
    Write-Host "  Backend:  http://localhost:8000"
    Write-Host "  Frontend: http://localhost:5173"
    Write-Host ""
    Write-Host "  Embedded runtimes: $LocalVenv"
    Write-Host ""
    Write-Host "  Close the terminal windows to stop the services"
    Write-Host ""

    # Open browser if frontend is ready
    if ($frontendReady) {
        Start-Process "http://localhost:5173"
    }
}

# Main
function Main {
    Write-Header

    # Change to script directory
    Set-Location $script:ScriptDir

    # Install embedded runtimes (no admin required, no system PATH changes)
    Install-EmbeddedPython
    Install-Poetry
    Install-EmbeddedNode

    # Install Docker (system-wide, optional - may require admin)
    if (-not $SkipDocker) {
        Install-Docker
    }

    # Setup backend and frontend
    Setup-Backend
    Setup-Frontend

    # Build Docker images
    if (-not $SkipDocker) {
        Build-DockerImages
    }

    # Verify installation
    Test-Installation

    # Start or show usage
    if ($NoStart) {
        Write-Usage
    } else {
        Start-Services
    }
}

Main
