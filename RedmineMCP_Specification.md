# RedmineMCP Specification

Created: 2026-03-15

---

## Overview

An MCP server for operating an internal Redmine instance from Claude Code (office PC).
Runs as an HTTP server on RHEL. Credentials are not stored on the server side; instead, they are passed via request headers from the client (Claude Code configuration file) on each request.

---

## System Architecture

```
Office PC (Claude Code / Mac or Windows)
    ↓ HTTP :8000 + headers (X-Redmine-URL / X-Redmine-API-Key)
RHEL (redmine_mcp_interface.py running as a service)
    ↓ REST API
Redmine (internal)
```

---

## File Structure

| File | Role |
|---|---|
| `redmine_mcp_interface.py` | MCP protocol entry point (interface) |
| `redmine_mcp_server.py` | Redmine REST API communication layer (core) |
| `requirements.txt` | Python dependencies |
| `redmine-mcp-stateless.service` | systemd unit file |
| `install.sh` | Installation script for RHEL |
| `uninstall.sh` | Uninstallation script |
| `example-claude-code-config.json` | Example Claude Code configuration |

---

## Installation

### 1. Transfer Files (from Mac/Win)

```bash
ssh root@<RHEL> "mkdir -p /tmp/redmine-mcp-stateless"
scp redmine_mcp_interface.py redmine_mcp_server.py requirements.txt \
    redmine-mcp-stateless.service install.sh uninstall.sh \
    root@<RHEL>:/tmp/redmine-mcp-stateless/
```

### 2. Install on RHEL

```bash
cd /tmp/redmine-mcp-stateless
chmod +x install.sh
./install.sh
```

What `install.sh` does:

- Pre-flight checks (root, OS, Python, required files)
- Copy files to `/opt/redmine-mcp-stateless/`
- Create Python virtual environment and install dependencies
- Configure logrotate (`/etc/logrotate.d/redmine-mcp-stateless`)
- Register and start systemd unit file
- SELinux support (register port 8000 as `http_port_t`)
- Open port 8000 in firewalld
- Verify service startup and port listening

### 3. Verify

```bash
systemctl status redmine-mcp-stateless
journalctl -u redmine-mcp-stateless -f
ss -tlnp | grep 8000
```

### 4. Claude Code Configuration (add to `~/.claude.json`)

```json
{
  "mcpServers": {
    "redmine-mcp-stateless": {
      "type": "sse",
      "url": "http://<RHEL-IP>:8000/sse",
      "headers": {
        "X-Redmine-URL": "https://<Redmine-URL>",
        "X-Redmine-API-Key": "<API-Key>"
      }
    }
  }
}
```

---

## Tool Reference

### Projects

#### `list_projects`

Returns a list of Redmine projects.

Args: none

#### `get_project`

Returns details of the specified project.

| Arg | Type | Required | Description |
|---|---|---|---|
| `project_id` | string | yes | Project ID or identifier |

---

### Issues

#### `list_issues`

Returns a list of issues.

| Arg | Type | Required | Description |
|---|---|---|---|
| `project_id` | string | - | Project ID (all projects if omitted) |
| `status_id` | string | - | Status ID or `"open"` / `"closed"` / `"*"` |
| `assigned_to_id` | int | - | Assignee ID |
| `limit` | int | - | Number of results (default 25, max 100) |
| `offset` | int | - | Starting offset (default 0) |

#### `get_issue`

Returns details of the specified issue, including comments and attachments.

| Arg | Type | Required | Description |
|---|---|---|---|
| `issue_id` | int | yes | Issue number |

#### `create_issue`

Creates a new issue.

| Arg | Type | Required | Description |
|---|---|---|---|
| `project_id` | string | yes | Project ID or identifier |
| `subject` | string | yes | Subject |
| `description` | string | - | Description |
| `tracker_id` | int | - | Tracker ID (obtain via `list_trackers`) |
| `status_id` | int | - | Status ID (obtain via `list_statuses`) |
| `priority_id` | int | - | Priority ID (obtain via `list_priorities`) |
| `assigned_to_id` | int | - | Assignee ID (obtain via `list_users`) |

#### `update_issue`

Updates an issue. Can also add comments.

| Arg | Type | Required | Description |
|---|---|---|---|
| `issue_id` | int | yes | Issue number |
| `subject` | string | - | New subject |
| `description` | string | - | New description |
| `status_id` | int | - | New status ID |
| `priority_id` | int | - | New priority ID |
| `assigned_to_id` | int | - | New assignee ID |
| `notes` | string | - | Comment |

#### `list_issues_with_journals`

Returns a list of issues with all comments and priority. Useful for checking progress per assignee.

| Arg | Type | Required | Description |
|---|---|---|---|
| `assigned_to_id` | int | - | Assignee ID |
| `project_id` | string | - | Project ID |
| `status_id` | string | - | Status ID or `"open"` / `"closed"` / `"*"` |
| `limit` | int | - | Number of results (default 25, max 100) |
| `offset` | int | - | Starting offset (default 0) |

#### `search_issues_full`

Full-text search for issues by keyword. Returns results with description, all comments, and priority. Searches across subject, description, and comments.

| Arg | Type | Required | Description |
|---|---|---|---|
| `query` | string | yes | Search keyword |
| `project_id` | string | - | Filter by project ID (all projects if omitted) |
| `limit` | int | - | Maximum number of results (all results if omitted) |

---

### Master Data

#### `list_statuses`

Returns a list of available issue statuses.

Args: none

#### `list_trackers`

Returns a list of available trackers.

Args: none

#### `list_priorities`

Returns a list of available issue priorities. Used for `priority_id` in `create_issue` / `update_issue`.

Args: none

#### `list_users`

Returns a list of Redmine users. Useful for looking up assignee IDs by name.

Args: none

> Note: May require Redmine administrator privileges.

---

## Design Notes

### Credential Handling

- Redmine URL and API key are not stored on the RHEL server
- Stored in `headers` within Claude Code's `~/.claude.json`
- Sent on every HTTP request via `X-Redmine-URL` / `X-Redmine-API-Key` headers
- Stored temporarily in a ContextVar on the server side and discarded after the request completes

### MCP SDK Transport

- Uses `mcp.sse_app()` (SSE transport)
- `streamable_http_app()` was rejected because it does not propagate ContextVar credentials correctly, as tool calls are processed as separate tasks within a session
- Claude Code configuration: `"type": "sse"`, URL: `http://<IP>:8000/sse`
