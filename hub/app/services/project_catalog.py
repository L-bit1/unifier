from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Project
from app.services.orchestrate import get_or_create_project

_GITHUB_REMOTE_RE = re.compile(
    r"github\.com[/:](?P<owner>[\w.-]+)/(?P<repo>[\w.-]+?)(?:\.git)?(?:/|$)"
)


@dataclass(frozen=True)
class CatalogProject:
    display_name: str
    github_owner: str
    github_repo: str
    local_path: str | None = None
    source: str = "workspace"

    @property
    def slug(self) -> str:
        return f"{self.github_owner}/{self.github_repo}"


def parse_github_remote(url: str) -> tuple[str, str] | None:
    m = _GITHUB_REMOTE_RE.search(url.strip())
    if not m:
        return None
    return m.group("owner"), m.group("repo")


def _git_remote_origin(path: Path) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(path), "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    remote = out.stdout.strip()
    return remote or None


def scan_workspace_roots() -> list[CatalogProject]:
    items: list[CatalogProject] = []
    for root in settings.workspace_roots_list():
        if not root.is_dir():
            continue
        for child in sorted(root.iterdir()):
            if not child.is_dir() or child.name.startswith("."):
                continue
            if not (child / ".git").is_dir():
                continue
            remote = _git_remote_origin(child)
            if not remote:
                continue
            parsed = parse_github_remote(remote)
            if not parsed:
                continue
            owner, repo = parsed
            items.append(
                CatalogProject(
                    display_name=child.name,
                    github_owner=owner,
                    github_repo=repo,
                    local_path=str(child),
                    source="workspace",
                )
            )
    return items


def fetch_github_repos() -> list[CatalogProject]:
    token = settings.github_token
    if not token:
        return []

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    items: list[CatalogProject] = []
    page = 1
    try:
        with httpx.Client(timeout=20.0) as client:
            while page <= 5:
                resp = client.get(
                    "https://api.github.com/user/repos",
                    headers=headers,
                    params={
                        "per_page": 100,
                        "page": page,
                        "sort": "updated",
                        "direction": "desc",
                    },
                )
                if resp.status_code != 200:
                    break
                data = resp.json()
                if not data:
                    break
                for repo in data:
                    if repo.get("fork"):
                        continue
                    owner = (repo.get("owner") or {}).get("login")
                    name = repo.get("name")
                    if not owner or not name:
                        continue
                    items.append(
                        CatalogProject(
                            display_name=name,
                            github_owner=owner,
                            github_repo=name,
                            local_path=None,
                            source="github",
                        )
                    )
                page += 1
    except httpx.HTTPError:
        return items
    return items


def _merge_catalog(*groups: Iterable[CatalogProject]) -> list[CatalogProject]:
    merged: dict[str, CatalogProject] = {}
    for group in groups:
        for item in group:
            key = item.slug.lower()
            existing = merged.get(key)
            if existing is None:
                merged[key] = item
                continue
            if existing.local_path is None and item.local_path:
                merged[key] = CatalogProject(
                    display_name=item.display_name or existing.display_name,
                    github_owner=item.github_owner,
                    github_repo=item.github_repo,
                    local_path=item.local_path,
                    source=item.source,
                )
    return sorted(
        merged.values(),
        key=lambda p: (p.display_name.lower(), p.slug.lower()),
    )


def discover_projects(db: Session | None = None) -> list[CatalogProject]:
    workspace = scan_workspace_roots()
    github = fetch_github_repos()
    hub: list[CatalogProject] = []
    if db is not None:
        for project in db.query(Project).order_by(Project.id).all():
            hub.append(
                CatalogProject(
                    display_name=project.github_repo,
                    github_owner=project.github_owner,
                    github_repo=project.github_repo,
                    local_path=None,
                    source="hub",
                )
            )
    return _merge_catalog(workspace, github, hub)


def sync_catalog_to_hub(db: Session, projects: list[CatalogProject]) -> None:
    for item in projects:
        get_or_create_project(db, item.github_owner, item.github_repo)
    db.commit()


def find_project(
    projects: list[CatalogProject],
    query: str,
) -> CatalogProject | None:
    q = query.strip()
    if not q:
        return None

    if "/" in q:
        owner, repo = q.split("/", 1)
        for item in projects:
            if (
                item.github_owner.lower() == owner.lower()
                and item.github_repo.lower() == repo.lower()
            ):
                return item
        return None

    if q.isdigit():
        idx = int(q) - 1
        if 0 <= idx < len(projects):
            return projects[idx]
        return None

    for item in projects:
        if item.display_name.lower() == q.lower():
            return item
    for item in projects:
        if item.github_repo.lower() == q.lower():
            return item
    for item in projects:
        if q.lower() in item.display_name.lower():
            return item
    return None
