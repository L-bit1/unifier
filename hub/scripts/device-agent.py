#!/usr/bin/env python3
"""Device Agent：轮询 Hub 收件箱，写入本地 HANDOFF，可选 demo 自动上报。"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


def api(method: str, url: str, payload: dict | None = None) -> dict | list:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read().decode("utf-8")
        return json.loads(body) if body else {}


_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))
from reply_push_lib import write_active_task


def write_handoff(home: Path, device_id: str, agent_id: str, item: dict) -> Path:
    inbox = home / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = inbox / f"{stamp}-task-{item['task_id']}-{device_id}-{agent_id}.md"
    kind = "执行" if item["kind"] == "work" else "审查"
    content = f"""# 联合器任务 #{item['task_id']}（{kind}）

- 项目: {item['project']}
- 分支: {item['branch']}
- 状态: {item['status']}
- 设备/Agent: {device_id} / {agent_id}

## 标题
{item['title']}

## 说明
{item.get('description') or '（无）'}

## 下一步
1. 在 Cursor/Trae 中打开对应仓库，切到分支 `{item['branch']}`
2. 完成改动后运行:
   `hub/scripts/submit-manifest.sh {item['task_id']} "完成改动摘要"`
3. AI 回复会自动推送到飞书（Cursor Hook / auto-reply-push）；也可手动:
   `hub/scripts/submit-agent-reply.sh {item['task_id']} {device_id} {agent_id} "摘要"`
4. 若是审查任务，运行:
   `hub/scripts/submit-review-vote.sh {item['task_id']} approved`
"""
    path.write_text(content, encoding="utf-8")
    write_active_task(
        int(item["task_id"]),
        kind=item["kind"],
        title=item["title"],
        device=device_id,
        agent=agent_id,
    )
    return path


def demo_auto_handle(
    hub: str, device_id: str, agent_id: str, item: dict, reviewer_id: str
) -> None:
    task_id = item["task_id"]
    if item["kind"] == "work":
        api(
            "POST",
            f"{hub}/api/v1/tasks/{task_id}/manifest",
            {
                "agent_id": agent_id,
                "device_id": device_id,
                "payload": {
                    "summary": f"[demo] {device_id}/{agent_id} 完成实现",
                    "files": [],
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
        )
        api("POST", f"{hub}/api/v1/tasks/{task_id}/submit-review", None)
        print(f"  [demo] 已提交 manifest 并进入审查 · task #{task_id}")
        return

    api(
        "POST",
        f"{hub}/api/v1/tasks/{task_id}/reviews",
        {
            "reviewer_agent_id": reviewer_id,
            "status": "approved",
            "note": f"[demo] {reviewer_id} LGTM",
        },
    )
    print(f"  [demo] 已审查通过 · task #{task_id} · {reviewer_id}")


OUTBOX_NAME = re.compile(r"^task-(\d+)-(.+)-(cursor|trae)\.(txt|md)$", re.I)


def poll_outbox(hub: str, device_id: str, agent_id: str, home: Path, seen: set[str]) -> None:
    outbox = home / "outbox"
    if not outbox.is_dir():
        return
    for path in sorted(outbox.iterdir()):
        if not path.is_file() or path.name in seen:
            continue
        m = OUTBOX_NAME.match(path.name)
        if not m:
            continue
        task_id, file_device, file_agent, _ext = m.groups()
        if file_device != device_id or file_agent.lower() != agent_id.lower():
            continue
        content = path.read_text(encoding="utf-8").strip()
        if not content:
            continue
        api(
            "POST",
            f"{hub}/api/v1/tasks/{task_id}/agent-replies",
            {
                "device_id": device_id,
                "agent_id": agent_id,
                "content": content,
                "source": "agent",
                "notify_feishu": True,
            },
        )
        seen.add(path.name)
        archive = home / "outbox-sent"
        archive.mkdir(parents=True, exist_ok=True)
        path.rename(archive / path.name)
        print(f"[outbox] 已上报 task #{task_id} -> 飞书 · {path.name}")


def poll_once(
    hub: str,
    device_id: str,
    agent_id: str,
    home: Path,
    demo_auto: bool,
    seen: set[str],
) -> None:
    inbox = api(
        "GET",
        f"{hub}/api/v1/tasks/inbox?device_id={device_id}&agent_id={agent_id}",
    )
    reviewer_id = f"{device_id}:{agent_id}"
    for item in inbox:
        key = f"{item['kind']}:{item['task_id']}"
        if key in seen:
            continue
        seen.add(key)
        path = write_handoff(home, device_id, agent_id, item)
        print(f"[inbox] {item['kind']} task #{item['task_id']} -> {path}")
        if demo_auto:
            demo_auto_handle(hub, device_id, agent_id, item, reviewer_id)


def main() -> int:
    parser = argparse.ArgumentParser(description="联合器 Device Agent")
    parser.add_argument("--hub", default=os.environ.get("HUB_URL", "http://127.0.0.1:8787"))
    parser.add_argument("--device-id", default=os.environ.get("DEVICE_ID", ""))
    parser.add_argument("--agent-id", default=os.environ.get("AGENT_ID", "cursor"))
    parser.add_argument(
        "--home",
        default=os.environ.get("UNIFIER_HOME", str(Path.home() / ".unifier")),
    )
    parser.add_argument("--interval", type=int, default=10)
    parser.add_argument("--once", action="store_true")
    parser.add_argument(
        "--demo-auto",
        action="store_true",
        help="演示模式：自动提交 manifest / 审查（用于 e2e）",
    )
    args = parser.parse_args()

    if not args.device_id:
        import socket

        args.device_id = socket.gethostname().split(".")[0]

    home = Path(args.home)
    home.mkdir(parents=True, exist_ok=True)
    seen: set[str] = set()

    print(f"Device Agent 启动 hub={args.hub} device={args.device_id} agent={args.agent_id}")
    while True:
        try:
            poll_once(args.hub, args.device_id, args.agent_id, home, args.demo_auto, seen)
            poll_outbox(args.hub, args.device_id, args.agent_id, home, seen)
        except urllib.error.URLError as e:
            print(f"[warn] Hub 不可达: {e}", file=sys.stderr)
        if args.once:
            break
        time.sleep(args.interval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
