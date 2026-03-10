#!/usr/bin/env bash
# Resonance — One-command installer for macOS and Linux
# Usage: curl -LsSf https://raw.githubusercontent.com/whorne89/Resonance/main/install.sh | bash
set -euo pipefail

REPO_URL="https://github.com/whorne89/Resonance.git"
INSTALL_DIR="$HOME/Resonance"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

info()  { echo -e "${BLUE}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# --- Detect platform ---
OS="$(uname -s)"
case "$OS" in
    Darwin) PLATFORM="macos" ;;
    Linux)  PLATFORM="linux" ;;
    *)      error "Unsupported platform: $OS" ;;
esac
info "Detected platform: $PLATFORM"

# --- Detect Linux distro ---
DISTRO=""
if [ "$PLATFORM" = "linux" ]; then
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        DISTRO="$ID"
    fi
    info "Detected distro: ${DISTRO:-unknown}"
fi

# --- Check/install git ---
if command -v git &>/dev/null; then
    ok "git is installed"
else
    info "Installing git..."
    if [ "$PLATFORM" = "macos" ]; then
        xcode-select --install 2>/dev/null || true
        echo "Please complete the Xcode Command Line Tools installation, then re-run this script."
        exit 0
    else
        case "$DISTRO" in
            ubuntu|debian|pop|linuxmint)
                sudo apt-get update && sudo apt-get install -y git ;;
            fedora)
                sudo dnf install -y git ;;
            arch|manjaro)
                sudo pacman -Sy --noconfirm git ;;
            *)
                error "Please install git manually, then re-run this script." ;;
        esac
    fi
    ok "git installed"
fi

# --- Check/install uv ---
if command -v uv &>/dev/null; then
    ok "uv is installed"
else
    info "Installing uv (Python package manager)..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # Add to PATH for this session
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
    if ! command -v uv &>/dev/null; then
        error "uv installation failed. Please install manually: https://docs.astral.sh/uv/"
    fi
    ok "uv installed"
fi

# --- Check/install Tesseract OCR ---
if command -v tesseract &>/dev/null; then
    ok "Tesseract OCR is installed"
else
    info "Installing Tesseract OCR..."
    if [ "$PLATFORM" = "macos" ]; then
        if command -v brew &>/dev/null; then
            brew install tesseract
        else
            warn "Homebrew not found. Install it first: https://brew.sh"
            warn "Then run: brew install tesseract"
        fi
    else
        case "$DISTRO" in
            ubuntu|debian|pop|linuxmint)
                sudo apt-get update && sudo apt-get install -y tesseract-ocr ;;
            fedora)
                sudo dnf install -y tesseract ;;
            arch|manjaro)
                sudo pacman -Sy --noconfirm tesseract ;;
            *)
                warn "Please install Tesseract OCR manually for your distro." ;;
        esac
    fi
    if command -v tesseract &>/dev/null; then
        ok "Tesseract OCR installed"
    else
        warn "Tesseract OCR not found — OCR features will be unavailable"
    fi
fi

# --- Install system audio dependencies (Linux) ---
if [ "$PLATFORM" = "linux" ]; then
    info "Checking audio dependencies..."
    case "$DISTRO" in
        ubuntu|debian|pop|linuxmint)
            sudo apt-get install -y portaudio19-dev python3-dev 2>/dev/null || true ;;
        fedora)
            sudo dnf install -y portaudio-devel python3-devel 2>/dev/null || true ;;
        arch|manjaro)
            sudo pacman -Sy --noconfirm portaudio 2>/dev/null || true ;;
    esac
    ok "Audio dependencies checked"
fi

# --- Clone or update repo ---
if [ -d "$INSTALL_DIR/.git" ]; then
    info "Resonance directory exists, pulling latest changes..."
    cd "$INSTALL_DIR"
    git pull --ff-only origin main
    ok "Updated to latest version"
else
    info "Cloning Resonance..."
    git clone "$REPO_URL" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
    ok "Cloned to $INSTALL_DIR"
fi

# --- Install Python dependencies ---
info "Installing Python dependencies with uv..."
cd "$INSTALL_DIR"
uv sync
ok "Dependencies installed"

# --- Create launcher ---
if [ "$PLATFORM" = "macos" ]; then
    LAUNCHER="$HOME/Desktop/Resonance.command"
    cat > "$LAUNCHER" << 'LAUNCHER_EOF'
#!/usr/bin/env bash
cd "$HOME/Resonance"
uv run python src/main.py
LAUNCHER_EOF
    chmod +x "$LAUNCHER"
    ok "Created launcher: $LAUNCHER (double-click to run)"
elif [ "$PLATFORM" = "linux" ]; then
    DESKTOP_DIR="$HOME/.local/share/applications"
    mkdir -p "$DESKTOP_DIR"
    cat > "$DESKTOP_DIR/resonance.desktop" << DESKTOP_EOF
[Desktop Entry]
Name=Resonance
Comment=Voice-to-text dictation using Whisper
Exec=bash -c 'cd $INSTALL_DIR && uv run python src/main.py'
Icon=$INSTALL_DIR/src/resources/icons/tray_idle.png
Terminal=false
Type=Application
Categories=Utility;Accessibility;
DESKTOP_EOF
    chmod +x "$DESKTOP_DIR/resonance.desktop"
    ok "Created desktop entry: $DESKTOP_DIR/resonance.desktop"
fi

# --- Platform-specific notes ---
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Resonance installed successfully!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "  To run Resonance:"
echo "    cd $INSTALL_DIR && uv run python src/main.py"
echo ""

if [ "$PLATFORM" = "macos" ]; then
    echo -e "  ${YELLOW}macOS note:${NC} Resonance needs Accessibility permission"
    echo "  for global hotkeys and simulated typing."
    echo "  Go to: System Settings > Privacy & Security > Accessibility"
    echo "  and add your terminal app (or Resonance)."
    echo ""
    echo "  A desktop launcher has been created on your Desktop."
elif [ "$PLATFORM" = "linux" ]; then
    echo "  A .desktop entry has been created — find Resonance in your app launcher."
fi

echo ""
echo "  To update later: cd $INSTALL_DIR && git pull && uv sync"
echo ""
