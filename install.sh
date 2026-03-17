#!/bin/bash
# Redmine MCP Server installation script
# Target OS: RHEL
# Run as: root
set -euo pipefail

INSTALL_DIR=/opt/redmine-mcp-stateless
LOG_DIR=/var/log/redmine-mcp-stateless
SERVICE_NAME=redmine-mcp-stateless
PORT=8000

# ── Colored logging ───────────────────────────────────────────────────────────
info()  { echo -e "\e[32m[INFO]\e[0m  $*"; }
warn()  { echo -e "\e[33m[WARN]\e[0m  $*"; }
error() { echo -e "\e[31m[ERROR]\e[0m $*" >&2; }
die()   { error "$*"; exit 1; }

echo "========================================"
echo " Redmine MCP Server Installation"
echo "========================================"

# ── Pre-flight checks ─────────────────────────────────────────────────────────
info "Starting pre-flight checks"

# Root check
[[ "${EUID}" -eq 0 ]] || die "Please run as root"

# OS check
if [[ -f /etc/redhat-release ]]; then
    OS_VER=$(cat /etc/redhat-release)
    info "OS: ${OS_VER}"
else
    warn "/etc/redhat-release not found. May not be a RHEL environment"
fi

# Required files check
for f in redmine_mcp_interface.py redmine_mcp_server.py requirements.txt redmine-mcp-stateless.service; do
    [[ -f "${f}" ]] || die "Required file not found: ${f}"
done
info "Required files: OK"

# ── Install Python and required packages ──────────────────────────────────────
info "Checking and installing required packages"

# Check for dnf
command -v dnf &>/dev/null || die "dnf not found. Please verify RHEL environment"

# mcp library requires Python 3.10+
# RHEL default python3 is 3.9, so python3.12 is explicitly installed
RHEL_VER=$(rpm -q --queryformat '%{VERSION}' redhat-release 2>/dev/null \
           || rpm -q --queryformat '%{VERSION}' centos-stream-release 2>/dev/null \
           || echo "unknown")
if [[ "${RHEL_VER}" == 8* ]]; then
    warn "RHEL 8.x detected: python3.12 may not be in default repos."
    warn "If installation fails, enable AppStream or CRB repo:"
    warn "  dnf config-manager --enable appstream crb"
fi

DNF_PKGS=()
command -v python3.12           &>/dev/null || DNF_PKGS+=(python3.12)
rpm -q python3.12-devel         &>/dev/null || DNF_PKGS+=(python3.12-devel)
command -v gcc                  &>/dev/null || DNF_PKGS+=(gcc)
command -v semanage             &>/dev/null || DNF_PKGS+=(policycoreutils-python-utils)

if [[ ${#DNF_PKGS[@]} -gt 0 ]]; then
    info "Installing via dnf: ${DNF_PKGS[*]}"
    dnf install -y "${DNF_PKGS[@]}"
else
    info "All required packages are already installed"
fi

PYTHON=$(command -v python3.12 || true)
[[ -n "${PYTHON}" ]] || die "Failed to install python3.12"
PY_VER=$("${PYTHON}" --version)
info "Python: ${PY_VER}"

# ── Create service user ───────────────────────────────────────────────────────
SERVICE_USER=redmine-mcp-stateless
if id -u "${SERVICE_USER}" &>/dev/null; then
    info "Service user '${SERVICE_USER}' already exists"
else
    info "Creating service user: ${SERVICE_USER}"
    useradd --system --no-create-home --shell /sbin/nologin "${SERVICE_USER}"
fi

# ── Create directories ────────────────────────────────────────────────────────
info "Creating directories"
mkdir -p -m 0750 "${INSTALL_DIR}"
mkdir -p -m 0750 "${LOG_DIR}"
chown "${SERVICE_USER}:${SERVICE_USER}" "${INSTALL_DIR}" "${LOG_DIR}"

# ── Copy files ────────────────────────────────────────────────────────────────
info "Copying files to ${INSTALL_DIR}"
cp redmine_mcp_interface.py redmine_mcp_server.py requirements.txt "${INSTALL_DIR}/"
chown -R "${SERVICE_USER}:${SERVICE_USER}" "${INSTALL_DIR}"
chmod 750 "${INSTALL_DIR}/redmine_mcp_interface.py"

# ── Create Python virtual environment ─────────────────────────────────────────
if [[ -d "${INSTALL_DIR}/venv" ]]; then
    info "Virtual environment already exists, skipping creation"
else
    info "Creating Python virtual environment: ${INSTALL_DIR}/venv (python3.12)"
    "${PYTHON}" -m venv "${INSTALL_DIR}/venv"
fi
"${INSTALL_DIR}/venv/bin/pip" install --upgrade pip --quiet
info "Installing dependencies (this may take a while)"
"${INSTALL_DIR}/venv/bin/pip" install -r "${INSTALL_DIR}/requirements.txt"
info "Dependencies: installation complete"

# ── Configure logrotate ───────────────────────────────────────────────────────
info "Configuring logrotate"
if [[ -f /etc/logrotate.d/redmine-mcp-stateless ]]; then
    info "logrotate config already exists, skipping"
else
    cat > /etc/logrotate.d/redmine-mcp-stateless << 'EOF'
/var/log/redmine-mcp-stateless/*.log {
    daily
    rotate 14
    compress
    delaycompress
    missingok
    notifempty
    copytruncate
}
EOF
    info "logrotate: /etc/logrotate.d/redmine-mcp-stateless created"
fi

# ── Install systemd unit file ─────────────────────────────────────────────────
info "Installing systemd unit file"
cp redmine-mcp-stateless.service /etc/systemd/system/redmine-mcp-stateless.service
chmod 644 /etc/systemd/system/redmine-mcp-stateless.service
systemctl daemon-reload
info "systemctl daemon-reload: OK"

# ── SELinux support (if enforcing) ───────────────────────────────────────────
SELINUX_STATUS=$(getenforce 2>/dev/null || echo "Unknown")
info "SELinux status: ${SELINUX_STATUS}"

if [[ "${SELINUX_STATUS}" == "Enforcing" ]]; then
    # Register port 8000 as http_port_t
    if command -v semanage &>/dev/null; then
        if semanage port -l | grep -q "^http_port_t.*${PORT}"; then
            info "SELinux: port ${PORT} is already registered as http_port_t"
        else
            semanage port -a -t http_port_t -p tcp "${PORT}"
            info "SELinux: registered port ${PORT} as http_port_t"
        fi
    else
        warn "semanage not found. Please run manually:"
        warn "  semanage port -a -t http_port_t -p tcp ${PORT}"
    fi
fi

# ── Firewall configuration ────────────────────────────────────────────────────
if command -v firewall-cmd &>/dev/null && systemctl is-active --quiet firewalld; then
    info "firewalld: opening port ${PORT}/tcp"
    firewall-cmd --permanent --add-port="${PORT}/tcp" 2>/dev/null || true
    firewall-cmd --reload
    info "firewalld: reload complete"
else
    warn "firewalld is not running. Open the port manually if needed"
    warn "  firewall-cmd --permanent --add-port=${PORT}/tcp && firewall-cmd --reload"
fi

# ── Start service ─────────────────────────────────────────────────────────────
info "Enabling and starting service"
systemctl enable "${SERVICE_NAME}.service"
systemctl restart "${SERVICE_NAME}.service"

# Verify startup (wait up to 10 seconds)
for i in $(seq 1 10); do
    sleep 1
    if systemctl is-active --quiet "${SERVICE_NAME}.service"; then
        info "Service startup confirmed: OK (${i}s)"
        break
    fi
    if [[ ${i} -eq 10 ]]; then
        error "Service failed to start"
        journalctl -u "${SERVICE_NAME}" --no-pager -n 30
        exit 1
    fi
done

# Port check
if ss -tlnp | grep -q ":${PORT}"; then
    info "Port ${PORT}: listening OK"
else
    error "Port ${PORT} is not listening after service start"
    warn "Check logs for details:"
    journalctl -u "${SERVICE_NAME}" --no-pager -n 20
    exit 1
fi

# ── Completion message ────────────────────────────────────────────────────────
echo ""
echo "========================================"
echo " Installation Complete"
echo "========================================"
echo "  Status  : systemctl status ${SERVICE_NAME}"
echo "  Logs    : journalctl -u ${SERVICE_NAME} -f"
echo "          : tail -f ${LOG_DIR}/server.log"
echo "  Stop    : systemctl stop ${SERVICE_NAME}"
echo "  Restart : systemctl restart ${SERVICE_NAME}"
echo "  Remove  : bash uninstall.sh"
echo ""
echo "  Claude Code config (~/.claude.json):"
echo "    type: sse"
echo "    url: http://$(hostname -I | awk '{print $1}'):${PORT}/sse"
echo "========================================"
