from __future__ import annotations

from app.config import settings
from app.models import FeishuChatSession
from app.services.project_catalog import CatalogProject

PAGE_SIZE = 8
BUTTONS_PER_ROW = 4


def _button(label: str, owner: str, repo: str, name: str, btn_type: str = "default") -> dict:
    text = label if len(label) <= 16 else label[:15] + "…"
    return {
        "tag": "button",
        "text": {"tag": "plain_text", "content": text},
        "type": btn_type,
        "value": {
            "action": "select_project",
            "owner": owner,
            "repo": repo,
            "name": name,
        },
    }


def build_project_picker_card(
    projects: list[CatalogProject],
    *,
    page: int = 0,
    session: FeishuChatSession | None = None,
) -> dict:
    total = len(projects)
    pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, pages - 1))
    start = page * PAGE_SIZE
    chunk = projects[start : start + PAGE_SIZE]

    if session:
        current = f"{session.display_name or session.github_repo}（{session.github_owner}/{session.github_repo}）"
    else:
        current = "未选择"

    lines = [
        f"**当前项目**：{current}",
        "",
        "点击按钮选择项目；选中后可直接 @机器人 发任务标题。",
        "也可回复：`选 项目名` / `选 3` / `选 owner/repo`",
        "",
        f"**第 {page + 1}/{pages} 页** · 共 {total} 个项目",
    ]
    for idx, item in enumerate(chunk, start=start + 1):
        local = " · 本地" if item.local_path else ""
        lines.append(f"{idx}. **{item.display_name}** · `{item.slug}`{local}")

    elements: list[dict] = [
        {"tag": "markdown", "content": "\n".join(lines)},
        {"tag": "hr"},
    ]

    row: list[dict] = []
    for item in chunk:
        row.append(
            _button(
                item.display_name,
                item.github_owner,
                item.github_repo,
                item.display_name,
                btn_type="primary"
                if session
                and session.github_owner == item.github_owner
                and session.github_repo == item.github_repo
                else "default",
            )
        )
        if len(row) >= BUTTONS_PER_ROW:
            elements.append({"tag": "action", "actions": row})
            row = []
    if row:
        elements.append({"tag": "action", "actions": row})

    nav: list[dict] = []
    if page > 0:
        nav.append(
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "上一页"},
                "type": "default",
                "value": {"action": "project_page", "page": page - 1},
            }
        )
    if page < pages - 1:
        nav.append(
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "下一页"},
                "type": "default",
                "value": {"action": "project_page", "page": page + 1},
            }
        )
    nav.append(
        {
            "tag": "button",
            "text": {"tag": "plain_text", "content": "刷新列表"},
            "type": "default",
            "value": {"action": "project_refresh", "page": page},
        }
    )
    if nav:
        elements.append({"tag": "action", "actions": nav})

    roots = ", ".join(str(p) for p in settings.workspace_roots_list()[:2])
    if len(settings.workspace_roots_list()) > 2:
        roots += " …"
    elements.append(
        {
            "tag": "note",
            "elements": [
                {
                    "tag": "plain_text",
                    "content": f"来源：本地工作区 + GitHub API · 扫描：{roots or '未配置 UNIFIER_WORKSPACE_ROOTS'}",
                }
            ],
        }
    )

    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "blue",
            "title": {"tag": "plain_text", "content": "选择 GitHub 项目"},
        },
        "elements": elements,
    }
