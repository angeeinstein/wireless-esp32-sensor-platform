#!/bin/bash
################################################################################
# Wireless ESP32 Sensor Platform - Installation Script
# Supports: Debian, Ubuntu, Raspbian, Raspberry Pi OS
# Usage: curl -sSL https://your-repo/install.sh | bash
#        or: wget -qO- https://your-repo/install.sh | bash
#        or: bash install.sh
################################################################################

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
REPO_URL="https://github.com/angeeinstein/wireless-esp32-sensor-platform.git"
INSTALL_DIR="/opt/esp32-sensor"
SERVICE_NAME="esp32-sensor-server"
SERVICE_USER="esp32sensor"
SERVICE_GROUP="esp32sensor"
PYTHON_MIN_VERSION="3.8"
SCRIPT_VERSION="1.0.0"
SCRIPT_URL="https://raw.githubusercontent.com/angeeinstein/wireless-esp32-sensor-platform/main/install.sh"

################################################################################
# Helper Functions
################################################################################

print_header() {
    echo ""
    echo -e "${BLUE}================================================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}================================================================${NC}"
    echo ""
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

# Check if running as root
check_root() {
    if [[ $EUID -ne 0 ]]; then
        print_error "This script must be run as root or with sudo"
        echo "Please run: sudo bash install.sh"
        exit 1
    fi
    print_success "Running with root privileges"
}

# Detect OS and version
detect_os() {
    if [[ -f /etc/os-release ]]; then
        . /etc/os-release
        OS=$NAME
        OS_VERSION=$VERSION_ID
        print_success "Detected OS: $OS $OS_VERSION"
    else
        print_error "Cannot detect operating system"
        exit 1
    fi
    
    # Check if supported OS
    case "$OS" in
        "Debian GNU/Linux"|"Ubuntu"|"Raspbian GNU/Linux"|"Raspberry Pi OS"*)
            print_success "Supported OS detected"
            ;;
        *)
            print_warning "OS may not be fully supported, continuing anyway..."
            ;;
    esac
}

# Check Python version
check_python() {
    print_info "Checking Python installation..."
    
    if command -v python3 &> /dev/null; then
        PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
        print_info "Found Python $PYTHON_VERSION"
        
        if python3 -c "import sys; exit(0 if sys.version_info >= (3, 8) else 1)"; then
            print_success "Python version is sufficient (>= $PYTHON_MIN_VERSION)"
            return 0
        else
            print_warning "Python version $PYTHON_VERSION is too old (need >= $PYTHON_MIN_VERSION)"
            return 1
        fi
    else
        print_warning "Python3 not found"
        return 1
    fi
}

# Install system packages
install_system_packages() {
    print_header "Installing System Packages"
    
    print_info "Updating package lists..."
    apt-get update -qq || {
        print_error "Failed to update package lists"
        exit 1
    }
    
    print_info "Installing required packages..."
    PACKAGES=(
        "python3"
        "python3-pip"
        "python3-venv"
        "git"
        "sqlite3"
        "curl"
        "wget"
        "net-tools"
    )
    
    for package in "${PACKAGES[@]}"; do
        if dpkg -l | grep -q "^ii  $package "; then
            print_success "$package already installed"
        else
            print_info "Installing $package..."
            apt-get install -y "$package" -qq || {
                print_error "Failed to install $package"
                exit 1
            }
            print_success "$package installed"
        fi
    done
    
    print_success "All system packages installed"
}

# Create service user
create_service_user() {
    print_header "Creating Service User"
    
    if id "$SERVICE_USER" &>/dev/null; then
        print_success "User $SERVICE_USER already exists"
    else
        print_info "Creating user $SERVICE_USER..."
        useradd --system --no-create-home --shell /bin/false "$SERVICE_USER" || {
            print_error "Failed to create user"
            exit 1
        }
        print_success "User $SERVICE_USER created"
    fi
}

# Check if installation exists
check_existing_installation() {
    if [[ -d "$INSTALL_DIR" ]]; then
        return 0
    else
        return 1
    fi
}

# Update this script itself
update_script() {
    print_header "Updating Installation Script"
    
    TEMP_SCRIPT=$(mktemp)
    
    print_info "Downloading latest version..."
    if curl -sSL "$SCRIPT_URL" -o "$TEMP_SCRIPT" 2>/dev/null; then
        # Check if download was successful and file is not empty
        if [[ -s "$TEMP_SCRIPT" ]]; then
            # Compare versions or checksums
            if ! cmp -s "$0" "$TEMP_SCRIPT"; then
                print_info "New version found, updating..."
                cp "$TEMP_SCRIPT" "$0"
                chmod +x "$0"
                rm -f "$TEMP_SCRIPT"
                print_success "Script updated! Re-running with new version..."
                exec "$0" "$@"
            else
                print_success "Script is already up to date"
                rm -f "$TEMP_SCRIPT"
            fi
        else
            print_warning "Downloaded script is empty, skipping update"
            rm -f "$TEMP_SCRIPT"
        fi
    else
        print_warning "Could not download script update, continuing with current version"
        rm -f "$TEMP_SCRIPT"
    fi
}

# Clone or update repository
setup_repository() {
    print_header "Setting Up Repository"
    
    if [[ -d "$INSTALL_DIR/.git" ]]; then
        print_info "Repository exists, updating..."
        cd "$INSTALL_DIR"
        
        # Stash any local changes
        sudo -u "$SERVICE_USER" git stash || true
        
        # Pull latest changes
        sudo -u "$SERVICE_USER" git pull origin main || sudo -u "$SERVICE_USER" git pull origin master || {
            print_error "Failed to update repository"
            exit 1
        }
        
        print_success "Repository updated"
    else
        print_info "Cloning repository..."
        
        # Remove directory if it exists but is not a git repo
        if [[ -d "$INSTALL_DIR" ]]; then
            print_warning "Removing existing non-git directory"
            rm -rf "$INSTALL_DIR"
        fi
        
        # Create parent directory
        mkdir -p "$(dirname "$INSTALL_DIR")"
        
        # Clone repository
        git clone "$REPO_URL" "$INSTALL_DIR" || {
            print_error "Failed to clone repository"
            print_info "Please update REPO_URL in the script or clone manually to $INSTALL_DIR"
            exit 1
        }
        
        print_success "Repository cloned"
    fi
    
    # Set ownership
    chown -R "$SERVICE_USER:$SERVICE_GROUP" "$INSTALL_DIR"
}

# Setup Python virtual environment
setup_python_venv() {
    print_header "Setting Up Python Virtual Environment"
    
    cd "$INSTALL_DIR/server"
    
    if [[ -d "venv" ]]; then
        print_info "Virtual environment exists, recreating..."
        rm -rf venv
    fi
    
    print_info "Creating virtual environment..."
    sudo -u "$SERVICE_USER" python3 -m venv venv || {
        print_error "Failed to create virtual environment"
        exit 1
    }
    
    print_success "Virtual environment created"
    
    print_info "Installing Python dependencies..."
    sudo -u "$SERVICE_USER" venv/bin/pip install --upgrade pip setuptools wheel -q
    
    if [[ -f "requirements.txt" ]]; then
        sudo -u "$SERVICE_USER" venv/bin/pip install -r requirements.txt -q || {
            print_error "Failed to install Python dependencies"
            exit 1
        }
    else
        # Install dependencies manually if requirements.txt doesn't exist
        print_warning "requirements.txt not found, installing dependencies manually"
        sudo -u "$SERVICE_USER" venv/bin/pip install flask flask-cors -q || {
            print_error "Failed to install Python dependencies"
            exit 1
        }
    fi
    
    print_success "Python dependencies installed"
}

# Create data directories
create_directories() {
    print_header "Creating Data Directories"
    
    DIRS=(
        "$INSTALL_DIR/server/data"
        "$INSTALL_DIR/server/logs"
        "/var/log/$SERVICE_NAME"
    )
    
    for dir in "${DIRS[@]}"; do
        if [[ ! -d "$dir" ]]; then
            mkdir -p "$dir"
            print_success "Created $dir"
        else
            print_success "$dir already exists"
        fi
    done
    
    # Set ownership
    chown -R "$SERVICE_USER:$SERVICE_GROUP" "$INSTALL_DIR/server/data"
    chown -R "$SERVICE_USER:$SERVICE_GROUP" "$INSTALL_DIR/server/logs"
    chown -R "$SERVICE_USER:$SERVICE_GROUP" "/var/log/$SERVICE_NAME"
    
    print_success "Data directories configured"
}

# Configure firewall
configure_firewall() {
    print_header "Configuring Firewall"
    
    if command -v ufw &> /dev/null; then
        print_info "UFW firewall detected"
        
        # Check if UFW is active
        if ufw status | grep -q "Status: active"; then
            print_info "Allowing ports 5000 (HTTP) and 9999 (UDP)..."
            ufw allow 5000/tcp comment "ESP32 Sensor HTTP API" || true
            ufw allow 9999/udp comment "ESP32 Sensor UDP Data" || true
            print_success "Firewall rules added"
        else
            print_warning "UFW is installed but not active, skipping firewall configuration"
        fi
    else
        print_info "UFW not installed, skipping firewall configuration"
    fi
}

# Create systemd service
create_systemd_service() {
    print_header "Creating Systemd Service"
    
    SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
    
    print_info "Creating service file at $SERVICE_FILE..."
    
    cat > "$SERVICE_FILE" << EOF
[Unit]
Description=ESP32 Wireless Sensor Platform Server
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_GROUP
WorkingDirectory=$INSTALL_DIR/server
Environment="PATH=$INSTALL_DIR/server/venv/bin:/usr/local/bin:/usr/bin:/bin"
Environment="FLASK_HOST=0.0.0.0"
Environment="FLASK_PORT=5000"
Environment="FLASK_DEBUG=False"
ExecStart=$INSTALL_DIR/server/venv/bin/python app.py
Restart=always
RestartSec=10
StandardOutput=append:/var/log/$SERVICE_NAME/output.log
StandardError=append:/var/log/$SERVICE_NAME/error.log

# Security settings
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$INSTALL_DIR/server/data $INSTALL_DIR/server/logs /var/log/$SERVICE_NAME

# Resource limits
LimitNOFILE=65536
LimitNPROC=4096

[Install]
WantedBy=multi-user.target
EOF
    
    print_success "Service file created"
    
    # Reload systemd
    print_info "Reloading systemd daemon..."
    systemctl daemon-reload
    
    print_success "Systemd service configured"
}

# Setup log rotation
setup_log_rotation() {
    print_header "Setting Up Log Rotation"
    
    LOGROTATE_FILE="/etc/logrotate.d/$SERVICE_NAME"
    
    cat > "$LOGROTATE_FILE" << EOF
/var/log/$SERVICE_NAME/*.log {
    daily
    rotate 14
    compress
    delaycompress
    notifempty
    missingok
    create 0640 $SERVICE_USER $SERVICE_GROUP
    sharedscripts
    postrotate
        systemctl reload $SERVICE_NAME > /dev/null 2>&1 || true
    endscript
}

$INSTALL_DIR/server/data/*.csv {
    weekly
    rotate 4
    compress
    delaycompress
    notifempty
    missingok
    create 0640 $SERVICE_USER $SERVICE_GROUP
}
EOF
    
    print_success "Log rotation configured"
}

# Start service
start_service() {
    print_header "Starting Service"
    
    print_info "Enabling service to start on boot..."
    systemctl enable "$SERVICE_NAME" || {
        print_error "Failed to enable service"
        exit 1
    }
    
    print_info "Starting service..."
    systemctl restart "$SERVICE_NAME" || {
        print_error "Failed to start service"
        print_info "Check logs with: journalctl -u $SERVICE_NAME -f"
        exit 1
    }
    
    # Wait a moment for service to start
    sleep 2
    
    # Check service status
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        print_success "Service is running"
    else
        print_error "Service failed to start"
        print_info "Check status with: systemctl status $SERVICE_NAME"
        print_info "Check logs with: journalctl -u $SERVICE_NAME -n 50"
        exit 1
    fi
}

# Display installation info
display_info() {
    print_header "Installation Complete!"
    
    # Get server IP addresses
    IP_ADDRESSES=$(hostname -I 2>/dev/null || ip addr show | grep 'inet ' | awk '{print $2}' | cut -d/ -f1 | grep -v 127.0.0.1)
    
    echo ""
    echo -e "${GREEN}════════════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}     ESP32 Wireless Sensor Platform - Ready!${NC}"
    echo -e "${GREEN}════════════════════════════════════════════════════════════${NC}"
    echo ""
    echo -e "${BLUE}Access URLs:${NC}"
    for ip in $IP_ADDRESSES; do
        echo -e "  ${GREEN}→${NC} Web Dashboard:  http://${ip}:5000"
        echo -e "  ${GREEN}→${NC} API Endpoint:   http://${ip}:5000/api/stats"
        echo -e "  ${GREEN}→${NC} UDP Receiver:   ${ip}:9999"
    done
    echo ""
    echo -e "${BLUE}Service Management:${NC}"
    echo -e "  ${GREEN}→${NC} Status:   systemctl status $SERVICE_NAME"
    echo -e "  ${GREEN}→${NC} Start:    systemctl start $SERVICE_NAME"
    echo -e "  ${GREEN}→${NC} Stop:     systemctl stop $SERVICE_NAME"
    echo -e "  ${GREEN}→${NC} Restart:  systemctl restart $SERVICE_NAME"
    echo -e "  ${GREEN}→${NC} Logs:     journalctl -u $SERVICE_NAME -f"
    echo ""
    echo -e "${BLUE}Data Locations:${NC}"
    echo -e "  ${GREEN}→${NC} Database:    $INSTALL_DIR/server/data/accelerometer.db"
    echo -e "  ${GREEN}→${NC} CSV Logs:    $INSTALL_DIR/server/data/accel_stream.csv"
    echo -e "  ${GREEN}→${NC} Service Log: /var/log/$SERVICE_NAME/"
    echo ""
    echo -e "${BLUE}Configuration:${NC}"
    echo -e "  ${GREEN}→${NC} Install Dir: $INSTALL_DIR"
    echo -e "  ${GREEN}→${NC} Service:     /etc/systemd/system/${SERVICE_NAME}.service"
    echo -e "  ${GREEN}→${NC} User:        $SERVICE_USER"
    echo ""
    echo -e "${BLUE}Next Steps:${NC}"
    echo -e "  ${GREEN}1.${NC} Configure your ESP32 to send data to: ${IP_ADDRESSES%% *}:9999"
    echo -e "  ${GREEN}2.${NC} Access the web dashboard at: http://${IP_ADDRESSES%% *}:5000"
    echo -e "  ${GREEN}3.${NC} Monitor logs with: journalctl -u $SERVICE_NAME -f"
    echo ""
    echo -e "${GREEN}════════════════════════════════════════════════════════════${NC}"
    echo ""
}

# Uninstall function
uninstall() {
    print_header "Uninstalling ESP32 Sensor Platform"
    
    read -p "Are you sure you want to uninstall? (yes/no): " -r
    if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
        print_info "Uninstall cancelled"
        exit 0
    fi
    
    read -p "Delete data files? (yes/no): " -r
    DELETE_DATA=$REPLY
    
    print_info "Stopping service..."
    systemctl stop "$SERVICE_NAME" 2>/dev/null || true
    systemctl disable "$SERVICE_NAME" 2>/dev/null || true
    
    print_info "Removing service file..."
    rm -f "/etc/systemd/system/${SERVICE_NAME}.service"
    systemctl daemon-reload
    
    print_info "Removing log rotation..."
    rm -f "/etc/logrotate.d/$SERVICE_NAME"
    
    if [[ $DELETE_DATA =~ ^[Yy][Ee][Ss]$ ]]; then
        print_info "Removing installation directory..."
        rm -rf "$INSTALL_DIR"
        print_info "Removing log directory..."
        rm -rf "/var/log/$SERVICE_NAME"
    else
        print_info "Keeping data files in $INSTALL_DIR"
    fi
    
    print_info "Removing service user..."
    userdel "$SERVICE_USER" 2>/dev/null || true
    
    print_success "Uninstallation complete"
}

# Main installation flow
main() {
    print_header "ESP32 Wireless Sensor Platform - Installer v${SCRIPT_VERSION}"
    
    # Check for uninstall flag
    if [[ "$1" == "--uninstall" ]]; then
        check_root
        uninstall
        exit 0
    fi
    
    # Check if running as root
    check_root
    
    # Detect OS
    detect_os
    
    # Check for existing installation
    if check_existing_installation; then
        print_warning "Existing installation detected at $INSTALL_DIR"
        echo ""
        read -p "Do you want to update the existing installation? (yes/no): " -r
        echo ""
        
        if [[ $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
            print_info "Performing update..."
            
            # Update script first
            update_script
            
            # Stop service for update
            print_info "Stopping service..."
            systemctl stop "$SERVICE_NAME" || true
            
            # Update repository
            setup_repository
            
            # Update Python environment
            setup_python_venv
            
            # Update directories
            create_directories
            
            # Update service file
            create_systemd_service
            
            # Update log rotation
            setup_log_rotation
            
            # Restart service
            start_service
            
            display_info
            exit 0
        else
            print_info "Update cancelled"
            exit 0
        fi
    fi
    
    # Fresh installation
    print_info "Performing fresh installation..."
    
    # Install system packages
    install_system_packages
    
    # Check Python
    if ! check_python; then
        print_error "Python requirements not met"
        exit 1
    fi
    
    # Create service user
    create_service_user
    
    # Setup repository
    setup_repository
    
    # Setup Python environment
    setup_python_venv
    
    # Create directories
    create_directories
    
    # Configure firewall
    configure_firewall
    
    # Create systemd service
    create_systemd_service
    
    # Setup log rotation
    setup_log_rotation
    
    # Start service
    start_service
    
    # Display info
    display_info
}

# Run main function
main "$@"
