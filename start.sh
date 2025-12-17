#!/bin/bash
# Open Claude UI Start Script for macOS and Linux
# This script sets up the environment and starts the services

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
PYTHON_VERSION="3.12"
NODE_VERSION="20"

print_header() {
    echo -e "${BLUE}"
    echo "╔════════════════════════════════════════════════════════════╗"
    echo "║                  Open Claude UI Setup                      ║"
    echo "║         Self-hosted Claude interface                       ║"
    echo "╚════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

print_step() {
    echo -e "${GREEN}[STEP]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

# Detect OS
detect_os() {
    if [[ "$OSTYPE" == "darwin"* ]]; then
        OS="macos"
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        OS="linux"
    else
        print_error "Unsupported operating system: $OSTYPE"
        exit 1
    fi
    echo "Detected OS: $OS"
}

# Check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Install Homebrew (macOS)
install_homebrew() {
    if [[ "$OS" == "macos" ]] && ! command_exists brew; then
        print_step "Installing Homebrew..."
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

        # Add Homebrew to PATH for Apple Silicon
        if [[ -f "/opt/homebrew/bin/brew" ]]; then
            eval "$(/opt/homebrew/bin/brew shellenv)"
        fi
    fi
}

# Install Python
install_python() {
    print_step "Checking Python installation..."

    if command_exists python3; then
        CURRENT_PYTHON=$(python3 --version 2>&1 | cut -d' ' -f2 | cut -d'.' -f1,2)
        if [[ "$CURRENT_PYTHON" == "3.11" || "$CURRENT_PYTHON" == "3.12" || "$CURRENT_PYTHON" == "3.13" ]]; then
            print_success "Python $CURRENT_PYTHON is installed"
            return
        fi
    fi

    print_step "Installing Python ${PYTHON_VERSION}..."
    if [[ "$OS" == "macos" ]]; then
        brew install python@${PYTHON_VERSION}
    else
        # Linux - use pyenv or system package manager
        if command_exists apt-get; then
            sudo apt-get update
            sudo apt-get install -y python3 python3-pip python3-venv
        elif command_exists dnf; then
            sudo dnf install -y python3 python3-pip
        elif command_exists pacman; then
            sudo pacman -S --noconfirm python python-pip
        else
            print_error "Could not install Python. Please install Python 3.11+ manually."
            exit 1
        fi
    fi
}

# Install Node.js
install_nodejs() {
    print_step "Checking Node.js installation..."

    if command_exists node; then
        CURRENT_NODE=$(node --version | cut -d'v' -f2 | cut -d'.' -f1)
        if [[ "$CURRENT_NODE" -ge 18 ]]; then
            print_success "Node.js v$(node --version | cut -d'v' -f2) is installed"
            return
        fi
    fi

    print_step "Installing Node.js ${NODE_VERSION}..."
    if [[ "$OS" == "macos" ]]; then
        brew install node@${NODE_VERSION}
    else
        # Linux - use NodeSource
        if command_exists apt-get; then
            curl -fsSL https://deb.nodesource.com/setup_${NODE_VERSION}.x | sudo -E bash -
            sudo apt-get install -y nodejs
        elif command_exists dnf; then
            curl -fsSL https://rpm.nodesource.com/setup_${NODE_VERSION}.x | sudo bash -
            sudo dnf install -y nodejs
        else
            print_error "Could not install Node.js. Please install Node.js 18+ manually."
            exit 1
        fi
    fi
}

# Install Docker
install_docker() {
    print_step "Checking Docker installation..."

    if command_exists docker; then
        print_success "Docker is installed"
        return
    fi

    print_step "Installing Docker..."
    if [[ "$OS" == "macos" ]]; then
        brew install --cask docker
        print_warning "Please start Docker Desktop manually after installation"
    else
        # Linux
        if command_exists apt-get; then
            sudo apt-get update
            sudo apt-get install -y docker.io docker-compose
            sudo systemctl start docker
            sudo systemctl enable docker
            sudo usermod -aG docker $USER
            print_warning "You may need to log out and back in for Docker group changes to take effect"
        elif command_exists dnf; then
            sudo dnf install -y docker docker-compose
            sudo systemctl start docker
            sudo systemctl enable docker
            sudo usermod -aG docker $USER
        else
            print_error "Could not install Docker. Please install Docker manually."
            exit 1
        fi
    fi
}

# Install Poetry
install_poetry() {
    print_step "Checking Poetry installation..."

    if command_exists poetry; then
        print_success "Poetry is installed"
        return
    fi

    print_step "Installing Poetry..."
    curl -sSL https://install.python-poetry.org | python3 -

    # Add Poetry to PATH
    export PATH="$HOME/.local/bin:$PATH"

    if ! command_exists poetry; then
        print_warning "Poetry installed but not in PATH. Add ~/.local/bin to your PATH"
    fi
}

# Setup Backend
setup_backend() {
    print_step "Setting up backend..."

    cd backend

    # Install dependencies
    poetry install --with dev

    # Create .env if it doesn't exist
    if [[ ! -f ".env" ]]; then
        print_step "Creating .env file..."
        if [[ -f ".env.example" ]]; then
            cp .env.example .env
        fi

        # Generate encryption key
        ENCRYPTION_KEY=$(python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')

        if [[ -f ".env" ]]; then
            # Update existing .env
            if grep -q "MASTER_ENCRYPTION_KEY=" .env; then
                sed -i.bak "s/MASTER_ENCRYPTION_KEY=.*/MASTER_ENCRYPTION_KEY=$ENCRYPTION_KEY/" .env
                rm -f .env.bak
            else
                echo "MASTER_ENCRYPTION_KEY=$ENCRYPTION_KEY" >> .env
            fi
        else
            # Create new .env
            cat > .env << EOF
# Open Claude UI Backend Configuration
DATABASE_URL=sqlite+aiosqlite:///./data/open-claude-ui.db
HOST=127.0.0.1
PORT=8000
CORS_ORIGINS=http://localhost:3000,http://localhost:5173,http://localhost:5174
DOCKER_CONTAINER_POOL_SIZE=5
MASTER_ENCRYPTION_KEY=$ENCRYPTION_KEY
EOF
        fi
        print_success ".env file created with encryption key"
    fi

    # Create data directory
    mkdir -p data

    cd ..
}

# Setup Frontend
setup_frontend() {
    print_step "Setting up frontend..."

    cd frontend

    # Install dependencies
    npm install

    cd ..
}

# Build Docker images (optional)
build_docker_images() {
    if command_exists docker && docker info >/dev/null 2>&1; then
        print_step "Building Docker sandbox images..."
        cd backend/app/core/sandbox/environments

        # Build only the default Python image for quick setup
        if [[ -f "python3.13.Dockerfile" ]]; then
            docker build -t openclaudeui-env-python3.13:latest -f python3.13.Dockerfile . || print_warning "Failed to build Python 3.13 image"
        fi

        cd ../../../../..
        print_success "Docker images built"
    else
        print_warning "Docker is not running. Skipping Docker image build."
        print_warning "Start Docker and run: cd backend/app/core/sandbox/environments && bash build_images.sh"
    fi
}

# Verify installation
verify_installation() {
    print_step "Verifying installation..."

    local errors=0

    if ! command_exists python3; then
        print_error "Python is not installed"
        errors=$((errors + 1))
    fi

    if ! command_exists node; then
        print_error "Node.js is not installed"
        errors=$((errors + 1))
    fi

    if ! command_exists poetry; then
        print_error "Poetry is not installed"
        errors=$((errors + 1))
    fi

    if ! command_exists docker; then
        print_warning "Docker is not installed (optional but recommended)"
    fi

    if [[ $errors -gt 0 ]]; then
        print_error "Installation verification failed with $errors errors"
        exit 1
    fi

    print_success "All required dependencies are installed!"
}

# Print usage instructions
print_usage() {
    echo ""
    echo -e "${GREEN}════════════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}                    Setup Complete!                          ${NC}"
    echo -e "${GREEN}════════════════════════════════════════════════════════════${NC}"
    echo ""
    echo "To start Open Claude UI:"
    echo ""
    echo "  1. Start the backend:"
    echo "     cd backend"
    echo "     poetry run python -m app.main"
    echo ""
    echo "  2. Start the frontend (in a new terminal):"
    echo "     cd frontend"
    echo "     npm run dev"
    echo ""
    echo "  3. Open http://localhost:5173 in your browser"
    echo ""
    echo "Optional: Build all Docker sandbox images:"
    echo "     cd backend/app/core/sandbox/environments"
    echo "     bash build_images.sh"
    echo ""
}

# Main
main() {
    print_header

    # Get script directory
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    cd "$SCRIPT_DIR"

    detect_os

    # Parse arguments
    SKIP_DOCKER=false
    START_SERVICES=true  # Default: start services after setup
    for arg in "$@"; do
        case $arg in
            --skip-docker)
                SKIP_DOCKER=true
                ;;
            --no-start)
                START_SERVICES=false
                ;;
        esac
    done

    install_homebrew
    install_python
    install_nodejs
    install_poetry

    if [[ "$SKIP_DOCKER" == false ]]; then
        install_docker
    fi

    # Ensure Poetry is in PATH
    export PATH="$HOME/.local/bin:$PATH"

    setup_backend
    setup_frontend

    if [[ "$SKIP_DOCKER" == false ]]; then
        build_docker_images
    fi

    verify_installation

    if [[ "$START_SERVICES" == true ]]; then
        start_services
    else
        print_usage
    fi
}

# Start backend and frontend services
start_services() {
    print_step "Starting Open Claude UI services..."

    # Ensure Poetry is in PATH
    export PATH="$HOME/.local/bin:$PATH"

    # Start backend in background
    print_step "Starting backend server..."
    cd backend
    poetry run python -m app.main &
    BACKEND_PID=$!
    cd ..

    # Wait for backend to be ready
    print_step "Waiting for backend to start..."
    for i in {1..30}; do
        if curl -s http://localhost:8000/ > /dev/null 2>&1; then
            print_success "Backend is running at http://localhost:8000"
            break
        fi
        sleep 1
    done

    # Start frontend in background
    print_step "Starting frontend server..."
    cd frontend
    npm run dev &
    FRONTEND_PID=$!
    cd ..

    # Wait for frontend to be ready
    print_step "Waiting for frontend to start..."
    for i in {1..30}; do
        if curl -s http://localhost:5173/ > /dev/null 2>&1; then
            print_success "Frontend is running at http://localhost:5173"
            break
        fi
        sleep 1
    done

    echo ""
    echo -e "${GREEN}════════════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}              Open Claude UI is running!                     ${NC}"
    echo -e "${GREEN}════════════════════════════════════════════════════════════${NC}"
    echo ""
    echo "  Backend:  http://localhost:8000"
    echo "  Frontend: http://localhost:5173"
    echo ""
    echo "  Press Ctrl+C to stop all services"
    echo ""

    # Handle Ctrl+C to kill both processes
    trap "echo ''; print_step 'Stopping services...'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit 0" SIGINT SIGTERM

    # Wait for processes
    wait
}

main "$@"
