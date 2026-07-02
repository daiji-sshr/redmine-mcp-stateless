#!/usr/bin/env python3
import contextvars
import logging
import logging.handlers
import os
from typing import Any, Dict, List, Optional

import uvicorn
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from redmine_mcp_server import RedmineClient, RedmineError

LOG_DIR = "/var/log/redmine-mcp-stateless"

logger = logging.getLogger("redmine-mcp-stateless")
logger.setLevel(logging.INFO)

_fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

try:
    os.makedirs(LOG_DIR, exist_ok=True)
    _fh = logging.handlers.RotatingFileHandler(
        os.path.join(LOG_DIR, "server.log"),
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    _fh.setFormatter(_fmt)
    logger.addHandler(_fh)
except OSError:
    pass  # Skip file logging if directory is not writable (e.g. Glama inspection)

_sh = logging.StreamHandler()
_sh.setFormatter(_fmt)
logger.addHandler(_sh)

_redmine_url: contextvars.ContextVar[str] = contextvars.ContextVar("redmine_url", default="")
_redmine_key: contextvars.ContextVar[str] = contextvars.ContextVar("redmine_key", default="")


class _CredentialsMiddleware:
    """
    ASGI middleware.
    Reads X-Redmine-URL / X-Redmine-API-Key from HTTP request headers
    and propagates them to handlers via ContextVar.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            headers = dict(scope.get("headers", []))
            url = headers.get(b"x-redmine-url", b"").decode()
            key = headers.get(b"x-redmine-api-key", b"").decode()

            if not url or not key:
                logger.warning(
                    "X-Redmine-URL or X-Redmine-API-Key header is missing"
                )

            tok_url = _redmine_url.set(url)
            tok_key = _redmine_key.set(key)
            try:
                await self.app(scope, receive, send)
            finally:
                _redmine_url.reset(tok_url)
                _redmine_key.reset(tok_key)
        else:
            await self.app(scope, receive, send)


def _client() -> RedmineClient:
    """Return a RedmineClient using credentials from ContextVar (SSE) or env vars (stdio)."""
    if os.environ.get("MCP_TRANSPORT") == "stdio":
        url = os.environ.get("REDMINE_URL", "")
        key = os.environ.get("REDMINE_API_KEY", "")
        if not url or not key:
            raise ValueError(
                "REDMINE_URL and REDMINE_API_KEY environment variables are required"
            )
    else:
        url = _redmine_url.get()
        key = _redmine_key.get()
        if not url or not key:
            raise ValueError(
                "X-Redmine-URL and X-Redmine-API-Key headers are required"
            )
    return RedmineClient(url, key)


# The SDK's DNS rebinding protection returns 421 when the Host header
# changes through a proxy/gateway, so disable it here.
# Access control is expected to be enforced at the infrastructure level
# (e.g. reverse proxy).
# see: https://github.com/modelcontextprotocol/python-sdk/issues/1798
mcp = FastMCP(
    "redmine-mcp-stateless-server",
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=False,
    ),
)


@mcp.tool()
def list_projects() -> List[Dict[str, Any]]:
    """Returns a list of Redmine projects."""
    logger.info("tool=list_projects")
    try:
        return _client().list_projects()
    except RedmineError as e:
        logger.error(f"list_projects error: {e}")
        raise


@mcp.tool()
def get_project(project_id: str) -> Dict[str, Any]:
    """Returns details of the specified project.

    Args:
        project_id: Project ID or identifier
    """
    logger.info(f"tool=get_project project_id={project_id}")
    try:
        return _client().get_project(project_id)
    except RedmineError as e:
        logger.error(f"get_project error: {e}")
        raise


@mcp.tool()
def list_issues(
    project_id: Optional[str] = None,
    status_id: Optional[str] = None,
    assigned_to_id: Optional[int] = None,
    limit: int = 25,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """Returns a list of issues.

    Args:
        project_id: Project ID (all projects if omitted)
        status_id: Status ID or "open" / "closed" / "*"
        assigned_to_id: Assignee ID
        limit: Number of results (max 100)
        offset: Starting offset
    """
    logger.info(
        f"tool=list_issues project_id={project_id} status_id={status_id} limit={limit}"
    )
    try:
        return _client().list_issues(
            project_id=project_id,
            status_id=status_id,
            assigned_to_id=assigned_to_id,
            limit=limit,
            offset=offset,
        )
    except RedmineError as e:
        logger.error(f"list_issues error: {e}")
        raise


@mcp.tool()
def get_issue(issue_id: int) -> Dict[str, Any]:
    """Returns details of the specified issue, including comments and attachments.

    Args:
        issue_id: Issue number
    """
    logger.info(f"tool=get_issue issue_id={issue_id}")
    try:
        return _client().get_issue(issue_id)
    except RedmineError as e:
        logger.error(f"get_issue error: {e}")
        raise


@mcp.tool()
def create_issue(
    project_id: str,
    subject: str,
    description: Optional[str] = None,
    tracker_id: Optional[int] = None,
    status_id: Optional[int] = None,
    priority_id: Optional[int] = None,
    assigned_to_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Creates a new issue.

    Args:
        project_id: Project ID or identifier
        subject: Subject
        description: Description
        tracker_id: Tracker ID
        status_id: Status ID
        priority_id: Priority ID
        assigned_to_id: Assignee ID
    """
    logger.info(f"tool=create_issue project_id={project_id} subject={subject!r}")
    try:
        return _client().create_issue(
            project_id=project_id,
            subject=subject,
            description=description,
            tracker_id=tracker_id,
            status_id=status_id,
            priority_id=priority_id,
            assigned_to_id=assigned_to_id,
        )
    except RedmineError as e:
        logger.error(f"create_issue error: {e}")
        raise


@mcp.tool()
def update_issue(
    issue_id: int,
    subject: Optional[str] = None,
    description: Optional[str] = None,
    status_id: Optional[int] = None,
    priority_id: Optional[int] = None,
    assigned_to_id: Optional[int] = None,
    notes: Optional[str] = None,
) -> Dict[str, Any]:
    """Updates an issue.

    Args:
        issue_id: Issue number
        subject: New subject
        description: New description
        status_id: New status ID
        priority_id: New priority ID
        assigned_to_id: New assignee ID
        notes: Comment
    """
    logger.info(f"tool=update_issue issue_id={issue_id}")
    try:
        return _client().update_issue(
            issue_id=issue_id,
            subject=subject,
            description=description,
            status_id=status_id,
            priority_id=priority_id,
            assigned_to_id=assigned_to_id,
            notes=notes,
        )
    except RedmineError as e:
        logger.error(f"update_issue error: {e}")
        raise


@mcp.tool()
def update_journal(journal_id: int, notes: str) -> Dict[str, Any]:
    """Edits a journal (comment) on an issue. Requires Redmine 5.0+.

    Args:
        journal_id: Comment ID (journals[].id from get_issue response)
        notes: New comment content
    """
    logger.info(f"tool=update_journal journal_id={journal_id}")
    try:
        return _client().update_journal(journal_id=journal_id, notes=notes)
    except RedmineError as e:
        logger.error(f"update_journal error: {e}")
        raise


@mcp.tool()
def list_statuses() -> List[Dict[str, Any]]:
    """Returns a list of available issue statuses."""
    logger.info("tool=list_statuses")
    try:
        return _client().list_statuses()
    except RedmineError as e:
        logger.error(f"list_statuses error: {e}")
        raise


@mcp.tool()
def list_trackers() -> List[Dict[str, Any]]:
    """Returns a list of available trackers."""
    logger.info("tool=list_trackers")
    try:
        return _client().list_trackers()
    except RedmineError as e:
        logger.error(f"list_trackers error: {e}")
        raise


@mcp.tool()
def list_priorities() -> List[Dict[str, Any]]:
    """Returns a list of available issue priorities. Used for priority_id in create_issue / update_issue."""
    logger.info("tool=list_priorities")
    try:
        return _client().list_priorities()
    except RedmineError as e:
        logger.error(f"list_priorities error: {e}")
        raise


@mcp.tool()
def search_issues_full(
    query: str,
    project_id: Optional[str] = None,
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Full-text search for issues by keyword. Returns results with description and all comments.
    Searches across subject, description, and all comments.

    Args:
        query: Search keyword
        project_id: Filter by project ID (all projects if omitted)
        limit: Maximum number of results (all results if omitted)
    """
    logger.info(f"tool=search_issues_full query={query!r} project_id={project_id}")
    try:
        return _client().search_issues_full(
            query=query,
            project_id=project_id,
            limit=limit,
        )
    except RedmineError as e:
        logger.error(f"search_issues_full error: {e}")
        raise


@mcp.tool()
def list_issues_with_journals(
    assigned_to_id: Optional[int] = None,
    project_id: Optional[str] = None,
    status_id: Optional[str] = None,
    limit: int = 25,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """Returns a list of issues with all comments. Useful for reviewing progress per assignee.

    Args:
        assigned_to_id: Assignee ID (obtain via list_users)
        project_id: Project ID (all projects if omitted)
        status_id: Status ID or "open" / "closed" / "*"
        limit: Number of issues to fetch (max 100)
        offset: Starting offset
    """
    logger.info(
        f"tool=list_issues_with_journals assigned_to_id={assigned_to_id} "
        f"project_id={project_id} status_id={status_id} limit={limit}"
    )
    try:
        return _client().list_issues_with_journals(
            assigned_to_id=assigned_to_id,
            project_id=project_id,
            status_id=status_id,
            limit=limit,
            offset=offset,
        )
    except RedmineError as e:
        logger.error(f"list_issues_with_journals error: {e}")
        raise


@mcp.tool()
def list_users() -> List[Dict[str, Any]]:
    """Returns a list of Redmine users. Useful for looking up assignee IDs by name.
    Note: May require Redmine administrator privileges."""
    logger.info("tool=list_users")
    try:
        return _client().list_users()
    except RedmineError as e:
        logger.error(f"list_users error: {e}")
        raise


if __name__ == "__main__":
    _transport = os.environ.get("MCP_TRANSPORT", "sse")

    if _transport == "stdio":
        logger.info("Starting Redmine MCP Server (stdio transport)")
        mcp.run()
    else:
        _port = int(os.environ.get("REDMINE_MCP_PORT", "8000"))
        logger.info(f"Starting Redmine MCP Server on 0.0.0.0:{_port}")

        inner_app = mcp.sse_app()
        app = _CredentialsMiddleware(inner_app)

        uvicorn.run(
            app,
            host="0.0.0.0",
            port=_port,
            log_level="info",
        )
