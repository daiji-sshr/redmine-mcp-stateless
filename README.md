# RedmineMCP

An MCP (Model Context Protocol) server that lets [Claude Code](https://claude.ai/claude-code) operate Redmine directly.
Runs as an HTTP server on RHEL or Docker. Credentials are never stored on the server — they are passed per-request via HTTP headers from the Claude Code configuration file.

---

## Key Features

1. **Context-First Design**
   Returns journals (comments) alongside issues so the AI can reason about history, generate accurate follow-up proposals, and summarize progress.

2. **Stateless Design**
   API keys are passed per-request from the client and never stored on the server. This brings three practical benefits:
   - **Maximum security** — Even if the server is compromised, there are no API keys stored on it to steal.
   - **Multi-tenant out of the box** — Deploy one server for the whole team. Each user simply sets their own API key on the Claude side; no per-user configuration is needed on the server.
   - **Zero maintenance for credential changes** — When a Redmine password or API key changes, only the client-side Claude configuration needs updating. The server requires no changes.

3. **Powerful Full-Text Search**
   `search_issues_full` searches across subject, description, and all comments, returning results in an AI-friendly format.

---

## Requirements

- Redmine 5.0+ (Redmine 5.0+ required for `update_journal`)
- Python 3.12
- RHEL (systemd deployment) **or** Docker

---

## Redmine Initial Setup

Before using RedmineMCP, enable the Redmine REST API (disabled by default).

1. Log in as an administrator
2. **Administration → Settings → API** tab → check **Enable REST web service** and save

To get an API key:

1. Open **My account** from the top-right menu
2. Click **Show** next to **API access key**
3. Use this key as `X-Redmine-API-Key` in the Claude Code configuration

---

## Architecture

```
Client PC (Claude Code / Mac or Windows)
    ↓ HTTP :8000 + headers (X-Redmine-URL / X-Redmine-API-Key)
Server (RHEL or Docker)
    ↓ REST API
Redmine
```

---

## Installation

### Option A — RHEL (systemd)

**1. Transfer files to the server**
```bash
ssh root@<server> "mkdir -p /tmp/redmine-mcp-stateless"
scp redmine_mcp_interface.py redmine_mcp_server.py requirements.txt \
    redmine-mcp-stateless.service install.sh uninstall.sh \
    root@<server>:/tmp/redmine-mcp-stateless/
```

**2. Run the installer**
```bash
cd /tmp/redmine-mcp-stateless
chmod +x install.sh
./install.sh
```

`install.sh` performs the following:
- Pre-flight checks (root, OS, Python 3.12, required files)
- Creates a dedicated `redmine-mcp-stateless` system user
- Copies files to `/opt/redmine-mcp-stateless/` and creates a Python virtual environment
- Configures logrotate
- Registers and starts a systemd service
- Configures SELinux (registers port 8000 as `http_port_t`)
- Opens port 8000 in firewalld
- Verifies service startup and port listening

**3. Verify**
```bash
systemctl status redmine-mcp-stateless
journalctl -u redmine-mcp-stateless -f
```

**To uninstall**
```bash
bash uninstall.sh
```

---

### Option B — Docker

Runs the MCP server as a container. Requires an existing Redmine instance accessible from the host.

**1. Build and start**
```bash
docker compose up -d --build
```

**2. Verify**
```bash
docker compose ps
docker compose logs -f redmine-mcp-stateless
```

**Stop**
```bash
docker compose down
```

---

## Claude Code Configuration

Add the following to `~/.claude.json`:

**RHEL**
```json
{
  "mcpServers": {
    "redmine-mcp-stateless": {
      "type": "sse",
      "url": "http://<server-IP>:8000/sse",
      "headers": {
        "X-Redmine-URL": "https://<your-redmine>",
        "X-Redmine-API-Key": "<your-api-key>"
      }
    }
  }
}
```

**Docker**
```json
{
  "mcpServers": {
    "redmine-mcp-stateless": {
      "type": "sse",
      "url": "http://localhost:8000/sse",
      "headers": {
        "X-Redmine-URL": "https://<your-redmine>",
        "X-Redmine-API-Key": "<your-api-key>"
      }
    }
  }
}
```

**stdio transport (for registry inspection / local use)**

The server normally runs with SSE (HTTP). Setting the environment variable `MCP_TRANSPORT=stdio` switches it to stdio transport. In this mode, credentials are passed via environment variables instead of HTTP headers:

```bash
MCP_TRANSPORT=stdio REDMINE_URL=https://<your-redmine> REDMINE_API_KEY=<your-api-key> \
    python redmine_mcp_interface.py
```

This mode exists mainly for MCP registry inspection (e.g. Glama). Use SSE for shared team deployment.

---

## Available Tools

### Issues
| Tool | Description |
|---|---|
| `list_issues` | List issues with optional filters (project, status, assignee) |
| `get_issue` | Issue details including all comments and attachments |
| `create_issue` | Create a new issue |
| `update_issue` | Update an issue or add a comment |
| `update_journal` | Edit an existing comment (requires Redmine 5.0+) |
| `list_issues_with_journals` | List issues with all comments — useful for per-assignee progress review |
| `search_issues_full` | Full-text search across subject, description, and comments |

### Projects
| Tool | Description |
|---|---|
| `list_projects` | List all projects |
| `get_project` | Project details |

### Master Data
| Tool | Description |
|---|---|
| `list_statuses` | Available issue statuses |
| `list_trackers` | Available trackers |
| `list_priorities` | Available priorities |
| `list_users` | User list (may require admin privileges) |

---

## Retrievable Data

| Category | Fields |
|---|---|
| **Project** | ID, identifier, name, description, status |
| **Issue** | ID, subject, description, status, project, tracker, priority, assignee, created/updated date |
| **Journal (comment)** | comment ID, body, created date, author |
| **Attachment** | file ID, filename, file size, MIME type, description, author, created date |
| **Status / Tracker / Priority** | ID, name |
| **User** | ID, login, first name, last name, full name |

---

## File Structure

| File | Description |
|---|---|
| `redmine_mcp_interface.py` | MCP server entry point |
| `redmine_mcp_server.py` | Redmine REST API client |
| `requirements.txt` | Python dependencies |
| `Dockerfile` | Container image (python:3.12-slim) |
| `compose.yml` | Docker Compose configuration |
| `redmine-mcp-stateless.service` | systemd unit file |
| `install.sh` | RHEL installation script |
| `uninstall.sh` | Uninstallation script |
| `example-claude-code-config.json` | Example Claude Code configuration |

---

## Security Notes

- Redmine URL and API key are **never stored on the server**
- Passed per-request via `X-Redmine-URL` and `X-Redmine-API-Key` headers
- Stored temporarily in a `ContextVar` and discarded after each request completes
- On RHEL, the service runs as a dedicated unprivileged user (`redmine-mcp-stateless`)

---

## License

MIT
