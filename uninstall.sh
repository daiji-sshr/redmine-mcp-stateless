#!/bin/bash
# Redmine MCP Server uninstallation script
# Run as: root
set -euo pipefail

INSTALL_DIR=/opt/redmine-mcp-stateless
LOG_DIR=/var/log/redmine-mcp-stateless
SERVICE_NAME=redmine-mcp-stateless
PORT=8000

[[ "${EUID}" -eq 0 ]] || { echo "Please run as root"; exit 1; }

echo "=== Redmine MCP Server Uninstall ==="

# Stop and disable service
if systemctl is-active --quiet "${SERVICE_NAME}.service" 2>/dev/null; then
    systemctl stop "${SERVICE_NAME}.service"
    echo "Service stopped: OK"
fi
if systemctl is-enabled --quiet "${SERVICE_NAME}.service" 2>/dev/null; then
    systemctl disable "${SERVICE_NAME}.service"
    echo "Service disabled: OK"
fi

# Remove unit file
rm -f /etc/systemd/system/redmine-mcp-stateless.service
systemctl daemon-reload
echo "Unit file removed: OK"

# Remove logrotate config
rm -f /etc/logrotate.d/redmine-mcp-stateless
echo "logrotate config removed: OK"

# Remove SELinux port config
SELINUX_STATUS=$(getenforce 2>/dev/null || echo "Unknown")
if [[ "${SELINUX_STATUS}" == "Enforcing" ]] && command -v semanage &>/dev/null; then
    if semanage port -l | grep -q "^http_port_t.*${PORT}"; then
        semanage port -d -t http_port_t -p tcp ${PORT} 2>/dev/null || true
        echo "SELinux port config removed: OK"
    fi
fi

# Remove firewall rule
if command -v firewall-cmd &>/dev/null && systemctl is-active --quiet firewalld; then
    firewall-cmd --permanent --remove-port=${PORT}/tcp 2>/dev/null || true
    firewall-cmd --reload
    echo "firewalld port removed: OK"
fi

# Remove install directory
rm -rf "${INSTALL_DIR}"
echo "Install directory removed: ${INSTALL_DIR}"

# Remove log directory (with confirmation)
read -rp "Also remove log directory ${LOG_DIR}? [y/N]: " ans
if [[ "${ans}" =~ ^[Yy]$ ]]; then
    rm -rf "${LOG_DIR}"
    echo "Log directory removed: ${LOG_DIR}"
fi

# Remove service user
if id -u redmine-mcp-stateless &>/dev/null; then
    userdel redmine-mcp-stateless
    echo "Service user removed: redmine-mcp-stateless"
fi

echo "=== Uninstall Complete ==="
