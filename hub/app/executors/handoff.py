from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from app.executors.base import ExecutorAdapter
from app.executors.types import DispatchResult, ExecutionContext


def _write_wake(home: Path, agent: str, item: dict, handoff: Path) -> Path:
    wake_dir = home / "wake"
    wake_dir.mkdir(parents=True, exist_ok=True)
    path = wake_dir / f"wake-{agent}.md"
    kind = "执行" if item.get("kind") == "work" else "审查"
    lines = [
        f"# wake · {agent} · task #{item['task_id']}（{kind}）",
        "",
        f"- time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- title: {item.get('title')}",
        f"- project: {item.get('project')}",
        f"- branch: {item.get('branch')}",
        f"- handoff: `{handoff}`",
        "",
        "## 你要做的",
        "",
        f"1. 打开 HANDOFF：`{handoff}`",
        "2. 按标题完成改动或审查；关键阶段可推里程碑：",
        f"   `curl -s -X POST \"$HUB_URL/api/v1/tasks/{item['task_id']}/milestones\" "
        "-H 'Content-Type: application/json' "
        '-d \'{"milestone":"edit","detail":"…"}\'`',
        "   （milestone: context|edit|test|commit|review|done）",
        "3. 结束后必须回飞书：",
        f"   `hub/scripts/submit-agent-reply.sh {item['task_id']} $DEVICE_ID {agent} \"摘要\"`",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


class HandoffExecutor(ExecutorAdapter):
    """Cursor / Trae / 任意 MCP IDE：HANDOFF + wake 文件。"""

    transport = "handoff"

    def __init__(self, name: str, *, mcp_tool_prefix: str = "unifier_") -> None:
        self.name = name
        self.mcp_tool_prefix = mcp_tool_prefix

    def dispatch(self, ctx: ExecutionContext) -> DispatchResult:
        if not ctx.handoff_path:
            raise ValueError("handoff_path required")
        wake = _write_wake(ctx.home, self.name, ctx.item, ctx.handoff_path)
        hook = os.environ.get("UNIFIER_ON_INBOX_HOOK", "").strip()
        if hook:
            env = os.environ.copy()
            env.update(
                {
                    "UNIFIER_TASK_ID": str(ctx.item["task_id"]),
                    "UNIFIER_TASK_KIND": str(ctx.item.get("kind") or ""),
                    "UNIFIER_TASK_TITLE": str(ctx.item.get("title") or ""),
                    "UNIFIER_HANDOFF": str(ctx.handoff_path),
                    "UNIFIER_AGENT_ID": self.name,
                    "UNIFIER_HOME": str(ctx.home),
                }
            )
            try:
                subprocess.run(hook, shell=True, env=env, check=False, timeout=120)
            except Exception:
                pass
        return DispatchResult(
            agent_id=self.name,
            handoff_path=ctx.handoff_path,
            wake_path=wake,
            message=f"handoff+wake for {self.name}",
            artifacts={"mcp_tools": f"{self.mcp_tool_prefix}*"},
        )


class DshQueueExecutor(ExecutorAdapter):
    """DeepSeek Harness：dsh-queue 提示词 + LATEST.md。"""

    name = "dsh"
    transport = "dsh_queue"

    def dispatch(self, ctx: ExecutionContext) -> DispatchResult:
        qdir = ctx.home / "dsh-queue"
        qdir.mkdir(parents=True, exist_ok=True)
        item = ctx.item
        tid = item["task_id"]
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = qdir / f"{stamp}-task-{tid}.md"
        prompt = f"""你是电脑端执行 Agent（联合器 device={ctx.device_id} agent=dsh）。
飞书用户已派活，请用 unifier_* 工具完成并回飞书。

任务 #{tid}
标题：{item.get('title')}
项目：{item.get('project')}
分支：{item.get('branch')}
说明：{item.get('description') or '（无）'}
类型：{item.get('kind')}

步骤：
1. unifier_hub_health
2. unifier_get_my_inbox — 确认本任务
3. 完成改动或审查
4. unifier_submit_manifest / unifier_submit_review_vote
5. unifier_submit_agent_reply task_id={tid} content=「完成摘要…」
"""
        path.write_text(prompt, encoding="utf-8")
        latest = qdir / "LATEST.md"
        latest.write_text(prompt, encoding="utf-8")
        (qdir / "LATEST.json").write_text(
            json.dumps(
                {
                    "task_id": tid,
                    "path": str(path),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return DispatchResult(
            agent_id=self.name,
            queue_path=path,
            artifacts={"latest": str(latest)},
            message="dsh-queue written",
        )
