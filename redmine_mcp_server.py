from typing import Any, Dict, List, Optional

import requests
from redminelib import Redmine
from redminelib.exceptions import (
    AuthError,
    ForbiddenError,
    ResourceNotFoundError,
)


class RedmineError(Exception):
    """Redmine operation error"""
    pass


class RedmineClient:
    def __init__(self, url: str, api_key: str):
        self._url = url.rstrip("/")
        self._api_key = api_key
        self._redmine = Redmine(self._url, key=api_key)

    def list_projects(self) -> List[Dict[str, Any]]:
        try:
            return [_project_dict(p) for p in self._redmine.project.all()]
        except (AuthError, ForbiddenError) as e:
            raise RedmineError(f"Authentication failed: {e}") from e
        except Exception as e:
            raise RedmineError(f"list_projects failed: {e}") from e

    def get_project(self, project_id: str) -> Dict[str, Any]:
        try:
            return _project_dict(self._redmine.project.get(project_id))
        except ResourceNotFoundError:
            raise RedmineError(f"Project not found: {project_id}")
        except (AuthError, ForbiddenError) as e:
            raise RedmineError(f"Authentication failed: {e}") from e
        except Exception as e:
            raise RedmineError(f"get_project failed: {e}") from e

    def list_issues(
        self,
        project_id: Optional[str] = None,
        status_id: Optional[str] = None,
        assigned_to_id: Optional[int] = None,
        limit: int = 25,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        try:
            kwargs: Dict[str, Any] = {"limit": limit, "offset": offset}
            if project_id is not None:
                kwargs["project_id"] = project_id
            if status_id is not None:
                kwargs["status_id"] = status_id
            if assigned_to_id is not None:
                kwargs["assigned_to_id"] = assigned_to_id
            return [_issue_dict(i) for i in self._redmine.issue.filter(**kwargs)]
        except (AuthError, ForbiddenError) as e:
            raise RedmineError(f"Authentication failed: {e}") from e
        except Exception as e:
            raise RedmineError(f"list_issues failed: {e}") from e

    def get_issue(self, issue_id: int) -> Dict[str, Any]:
        try:
            issue = self._redmine.issue.get(
                issue_id, include=["journals", "attachments"]
            )
            return _issue_dict(issue, detailed=True)
        except ResourceNotFoundError:
            raise RedmineError(f"Issue not found: #{issue_id}")
        except (AuthError, ForbiddenError) as e:
            raise RedmineError(f"Authentication failed: {e}") from e
        except Exception as e:
            raise RedmineError(f"get_issue failed: {e}") from e

    def create_issue(
        self,
        project_id: str,
        subject: str,
        description: Optional[str] = None,
        tracker_id: Optional[int] = None,
        status_id: Optional[int] = None,
        priority_id: Optional[int] = None,
        assigned_to_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        try:
            kwargs: Dict[str, Any] = {
                "project_id": project_id,
                "subject": subject,
            }
            if description is not None:
                kwargs["description"] = description
            if tracker_id is not None:
                kwargs["tracker_id"] = tracker_id
            if status_id is not None:
                kwargs["status_id"] = status_id
            if priority_id is not None:
                kwargs["priority_id"] = priority_id
            if assigned_to_id is not None:
                kwargs["assigned_to_id"] = assigned_to_id
            issue = self._redmine.issue.create(**kwargs)
            return _issue_dict(issue)
        except (AuthError, ForbiddenError) as e:
            raise RedmineError(f"Authentication failed: {e}") from e
        except Exception as e:
            raise RedmineError(f"create_issue failed: {e}") from e

    def update_issue(
        self,
        issue_id: int,
        subject: Optional[str] = None,
        description: Optional[str] = None,
        status_id: Optional[int] = None,
        priority_id: Optional[int] = None,
        assigned_to_id: Optional[int] = None,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        try:
            kwargs: Dict[str, Any] = {}
            if subject is not None:
                kwargs["subject"] = subject
            if description is not None:
                kwargs["description"] = description
            if status_id is not None:
                kwargs["status_id"] = status_id
            if priority_id is not None:
                kwargs["priority_id"] = priority_id
            if assigned_to_id is not None:
                kwargs["assigned_to_id"] = assigned_to_id
            if notes is not None:
                kwargs["notes"] = notes
            self._redmine.issue.update(issue_id, **kwargs)
            return self.get_issue(issue_id)
        except RedmineError:
            raise
        except ResourceNotFoundError:
            raise RedmineError(f"Issue not found: #{issue_id}")
        except (AuthError, ForbiddenError) as e:
            raise RedmineError(f"Authentication failed: {e}") from e
        except Exception as e:
            raise RedmineError(f"update_issue failed: {e}") from e

    def update_journal(self, journal_id: int, notes: str) -> Dict[str, Any]:
        """Edit a journal (comment). Requires Redmine 5.0+."""
        try:
            url = f"{self._url}/journals/{journal_id}.json"
            resp = requests.put(
                url,
                json={"journal": {"notes": notes}},
                headers={"X-Redmine-API-Key": self._api_key},
                timeout=30,
            )
            if resp.status_code == 200:
                return resp.json().get("journal", {"id": journal_id, "notes": notes})
            elif resp.status_code == 204:
                return {"id": journal_id, "notes": notes}
            else:
                raise RedmineError(
                    f"update_journal failed: HTTP {resp.status_code} {resp.text}"
                )
        except RedmineError:
            raise
        except Exception as e:
            raise RedmineError(f"update_journal failed: {e}") from e

    def list_statuses(self) -> List[Dict[str, Any]]:
        try:
            return [
                {"id": s.id, "name": s.name}
                for s in self._redmine.issue_status.all()
            ]
        except Exception as e:
            raise RedmineError(f"list_statuses failed: {e}") from e

    def list_trackers(self) -> List[Dict[str, Any]]:
        try:
            return [
                {"id": t.id, "name": t.name}
                for t in self._redmine.tracker.all()
            ]
        except Exception as e:
            raise RedmineError(f"list_trackers failed: {e}") from e

    def list_priorities(self) -> List[Dict[str, Any]]:
        try:
            return [
                {"id": p.id, "name": p.name, "is_default": _safe(p, "is_default", False)}
                for p in self._redmine.enumeration.filter(resource="issue_priorities")
            ]
        except Exception as e:
            raise RedmineError(f"list_priorities failed: {e}") from e

    def list_issues_with_journals(
        self,
        assigned_to_id: Optional[int] = None,
        project_id: Optional[str] = None,
        status_id: Optional[str] = None,
        limit: int = 25,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        try:
            kwargs: Dict[str, Any] = {"limit": limit, "offset": offset}
            if assigned_to_id is not None:
                kwargs["assigned_to_id"] = assigned_to_id
            if project_id is not None:
                kwargs["project_id"] = project_id
            if status_id is not None:
                kwargs["status_id"] = status_id
            issues = self._redmine.issue.filter(**kwargs)
            result = []
            for issue in issues:
                full = self._redmine.issue.get(issue.id, include=["journals"])
                journals = _safe(full, "journals", [])
                result.append({
                    "id": full.id,
                    "subject": full.subject,
                    "status": _safe(_safe(full, "status"), "name", ""),
                    "tracker": _safe(_safe(full, "tracker"), "name", ""),
                    "priority": _safe(_safe(full, "priority"), "name", ""),
                    "assigned_to": _safe(_safe(full, "assigned_to"), "name", ""),
                    "updated_on": str(_safe(full, "updated_on", "")),
                    "journals": [
                        {
                            "notes": _safe(j, "notes", ""),
                            "created_on": str(_safe(j, "created_on", "")),
                            "user": _safe(_safe(j, "user"), "name", ""),
                        }
                        for j in journals
                        if _safe(j, "notes")
                    ],
                })
            return result
        except (AuthError, ForbiddenError) as e:
            raise RedmineError(f"Authentication failed: {e}") from e
        except Exception as e:
            raise RedmineError(f"list_issues_with_journals failed: {e}") from e

    def search_issues_full(
        self,
        query: str,
        project_id: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        try:
            params: Dict[str, Any] = {
                "q": query,
                "issues": 1,
                "titles_only": 0,
            }
            if project_id is not None:
                params["scope"] = "projects"
                params["project_id"] = project_id
            else:
                params["scope"] = "all"

            issue_ids: List[int] = []
            offset = 0
            page_size = 25
            while True:
                params["offset"] = offset
                params["limit"] = page_size
                resp = requests.get(
                    f"{self._url}/search.json",
                    params=params,
                    headers={"X-Redmine-API-Key": self._api_key},
                    timeout=30,
                )
                if resp.status_code != 200:
                    raise RedmineError(
                        f"search_issues_full failed: HTTP {resp.status_code} {resp.text}"
                    )
                data = resp.json()
                results = data.get("results", [])
                for r in results:
                    if r.get("type") == "issue":
                        issue_ids.append(r["id"])
                if limit is not None and len(issue_ids) >= limit:
                    issue_ids = issue_ids[:limit]
                    break
                total = data.get("total_count", 0)
                offset += page_size
                if offset >= total or not results:
                    break

            output = []
            for issue_id in issue_ids:
                full = self._redmine.issue.get(
                    issue_id, include=["journals"]
                )
                journals = _safe(full, "journals", [])
                output.append({
                    "id": full.id,
                    "subject": full.subject,
                    "description": _safe(full, "description", ""),
                    "status": _safe(_safe(full, "status"), "name", ""),
                    "tracker": _safe(_safe(full, "tracker"), "name", ""),
                    "priority": _safe(_safe(full, "priority"), "name", ""),
                    "assigned_to": _safe(_safe(full, "assigned_to"), "name", ""),
                    "updated_on": str(_safe(full, "updated_on", "")),
                    "journals": [
                        {
                            "notes": _safe(j, "notes", ""),
                            "created_on": str(_safe(j, "created_on", "")),
                            "user": _safe(_safe(j, "user"), "name", ""),
                        }
                        for j in journals
                        if _safe(j, "notes")
                    ],
                })
            return output
        except (AuthError, ForbiddenError) as e:
            raise RedmineError(f"Authentication failed: {e}") from e
        except Exception as e:
            raise RedmineError(f"search_issues_full failed: {e}") from e

    def list_users(self) -> List[Dict[str, Any]]:
        try:
            return [
                {
                    "id": u.id,
                    "login": _safe(u, "login", ""),
                    "firstname": _safe(u, "firstname", ""),
                    "lastname": _safe(u, "lastname", ""),
                    "name": f"{_safe(u, 'lastname', '')} {_safe(u, 'firstname', '')}".strip(),
                }
                for u in self._redmine.user.all()
            ]
        except (AuthError, ForbiddenError) as e:
            raise RedmineError(f"Authentication failed (administrator privileges may be required): {e}") from e
        except Exception as e:
            raise RedmineError(f"list_users failed: {e}") from e


def _safe(obj, attr, default=None):
    try:
        return getattr(obj, attr)
    except Exception:
        return default


def _ref(obj) -> Optional[Dict[str, Any]]:
    if obj is None:
        return None
    try:
        return {"id": obj.id, "name": obj.name}
    except Exception:
        return None


def _project_dict(p) -> Dict[str, Any]:
    return {
        "id": p.id,
        "identifier": _safe(p, "identifier"),
        "name": p.name,
        "description": _safe(p, "description", ""),
        "status": _safe(p, "status"),
    }


def _issue_dict(issue, detailed: bool = False) -> Dict[str, Any]:
    d: Dict[str, Any] = {
        "id": issue.id,
        "subject": issue.subject,
        "description": _safe(issue, "description", ""),
        "status": _ref(_safe(issue, "status")),
        "project": _ref(_safe(issue, "project")),
        "tracker": _ref(_safe(issue, "tracker")),
        "priority": _ref(_safe(issue, "priority")),
        "assigned_to": _ref(_safe(issue, "assigned_to")),
        "created_on": str(_safe(issue, "created_on", "")),
        "updated_on": str(_safe(issue, "updated_on", "")),
    }
    if detailed:
        journals = _safe(issue, "journals", [])
        d["journals"] = [
            {
                "id": j.id,
                "notes": _safe(j, "notes", ""),
                "created_on": str(_safe(j, "created_on", "")),
                "user": _ref(_safe(j, "user")),
            }
            for j in journals
            if _safe(j, "notes")
        ]
        attachments = _safe(issue, "attachments", [])
        d["attachments"] = [
            {
                "id": _safe(a, "id"),
                "filename": _safe(a, "filename", ""),
                "filesize": _safe(a, "filesize"),
                "content_type": _safe(a, "content_type", ""),
                "description": _safe(a, "description", ""),
                "author": _ref(_safe(a, "author")),
                "created_on": str(_safe(a, "created_on", "")),
            }
            for a in attachments
        ]
    return d
