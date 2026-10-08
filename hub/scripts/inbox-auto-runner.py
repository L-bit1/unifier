#!/usr/bin/env python3
"""Inbox Auto-Runner：收件 →（可选确认）→ 唤醒执行端。

能力：
  1. 多 Agent 轮询（cursor / trae / dsh / continue / opencode）
  2. P1 半自动：UNIFIER_CONFIRM_EXEC=1 时先请求确认，确认后才 dispatch
  3. P0 审查等待催促（默认 3 分钟）
  4. ExecutionSupervisor 超时熔断
  5. 飞书/App ack

用法：
  HUB_URL=http://127.0.0.1:8787 DEVICE_ID=mac-a \\
    python3 inbox-auto-runner.py --agents cursor,trae,dsh
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import time
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_HUB_DIR = _SCRIPT_DIR.parent
if str(_HUB_DIR) not in sys.path:
    sys.path.insert(0, str(_HUB_DIR))


def _load_device_agent():
    import importlib.util

    path = _SCRIPT_DIR / "device-agent.py"
    spec = importlib.util.spec_from_file_location("unifier_device_agent", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_da = _load_device_agent()
api = _da.api
write_handoff = _da.write_handoff
poll_outbox = getattr(_da, "poll_outbox", lambda *a, **k: None)

from app.executors.registry import ExecutionSupervisor, get_executor  # noqa: E402
from app.executors.types import ExecutionContext  # noqa: E402
from app.services.exec_confirm import (  # noqa: E402
    confirm_exec_enabled,
    list_confirmed,
    pop_confirmed,
    request_confirm,
)


def notify(title: str, body: str) -> None:
    try:
        if sys.platform == "darwin":
            import subprocess

            subprocess.run(
                [
                    "osascript",
                    "-e",
                    f'display notification {json.dumps(body)} with title {json.dumps(title)}',
                ],
                check=False,
            )
    except Exception:
        pass


def resolve_workspace(project: str | None) -> Path | None:
    if not project or "/" not in str(project):
        return None
    owner, repo = str(project).split("/", 1)
    roots = os.environ.get(
        "UNIFIER_WORKSPACE_ROOTS",
        str(Path.home() / "Desktop"),
    ).split(":")
    for root in roots:
        root = root.strip()
        if not root:
            continue
        for candidate in (
            Path(root) / owner / repo,
            Path(root) / f"{owner}-{repo}",
            Path(root) / repo,
        ):
            if candidate.is_dir():
                return candidate
    return None


def feishu_ack(hub: str, device_id: str, agent_id: str, item: dict) -> None:
    if os.environ.get("INBOX_AUTO_FEISHU_ACK", "1") != "1":
        return
    tid = item["task_id"]
    kind = "执行" if item.get("kind") == "work" else "审查"
    content = (
        f"✅ 已收到，正在唤醒 {agent_id}…\n"
        f"任务 #{tid}（{kind}）\n"
        f"标题：{item.get('title')}\n"
        f"执行端：{device_id}/{agent_id}\n"
        f"HANDOFF 已写入；超时 "
        f"{os.environ.get('UNIFIER_EXEC_TIMEOUT_SECONDS', '300')}s 将自动熔断"
    )
    try:
        api(
            "POST",
            f"{hub.rstrip('/')}/api/v1/tasks/{tid}/agent-replies",
            {
                "device_id": device_id,
                "agent_id": agent_id,
                "content": content,
                "source": "inbox-auto-runner",
                "notify_feishu": True,
            },
        )
        try:
            api(
                "POST",
                f"{hub.rstrip('/')}/api/v1/tasks/{tid}/lifecycle",
                {
                    "event": "task.inbox_acked",
                    "extra": {"device_id": device_id, "agent_id": agent_id},
                },
            )
        except Exception:
            pass
        print(f"  [feishu] ack task #{tid}")
    except Exception as e:
        print(f"  [warn] feishu ack failed: {e}", file=sys.stderr)


def heartbeat(hub: str, device_id: str) -> None:
    try:
        api("POST", f"{hub.rstrip('/')}/api/v1/devices/{device_id}/heartbeat", {})
    except Exception:
        pass


def _dispatch_one(
    hub: str,
    device_id: str,
    agent_id: str,
    home: Path,
    item: dict,
    supervisor: ExecutionSupervisor,
) -> None:
    path = write_handoff(home, device_id, agent_id, item)
    workspace = resolve_workspace(item.get("project"))
    executor = get_executor(agent_id)
    ctx = ExecutionContext(
        hub_url=hub,
        device_id=device_id,
        agent_id=agent_id,
        item=item,
        home=home,
        handoff_path=path,
        workspace_path=workspace,
    )
    result = executor.dispatch(ctx)
    print(
        f"[inbox] {agent_id} {item['kind']} #{item['task_id']} "
        f"via {executor.transport} -> {path}"
    )
    if result.wake_path:
        print(f"  wake -> {result.wake_path}")
    if result.queue_path:
        print(f"  queue -> {result.queue_path}")
    # DSH：可选自动打开 LATEST
    if agent_id == "dsh" and os.environ.get("UNIFIER_DSH_AUTO_OPEN", "0") == "1":
        latest = home / "dsh-queue" / "LATEST.md"
        if latest.is_file():
            try:
                if sys.platform == "darwin":
                    import subprocess

                    subprocess.run(["open", str(latest)], check=False)
            except Exception:
                pass
    supervisor.register(
        hub,
        device_id,
        agent_id,
        item,
        workspace_path=str(workspace) if workspace else None,
    )
    notify(
        f"联合器 · {agent_id}",
        f"#{item['task_id']} {item.get('title') or ''}"[:100],
    )
    feishu_ack(hub, device_id, agent_id, item)


def poll_agent(
    hub: str,
    device_id: str,
    agent_id: str,
    home: Path,
    seen: set[str],
    requested: set[str],
    supervisor: ExecutionSupervisor,
) -> None:
    inbox = api(
        "GET",
        f"{hub.rstrip('/')}/api/v1/tasks/inbox?device_id={device_id}&agent_id={agent_id}",
    )
    if not isinstance(inbox, list):
        inbox = inbox.get("items") or inbox.get("tasks") or []
    active_keys = {f"{agent_id}:{i.get('kind')}:{i['task_id']}" for i in inbox}

    state = supervisor._load()
    for key in list(state.keys()):
        if key.startswith(f"{agent_id}:") and key not in active_keys:
            rec = state[key]
            supervisor.complete(
                rec.get("agent_id", agent_id),
                {"task_id": rec["task_id"], "kind": rec.get("kind")},
            )

    confirm_on = confirm_exec_enabled()

    for item in inbox:
        key = f"{agent_id}:{item['kind']}:{item['task_id']}"
        if key in seen:
            continue

# 确认门只拦执行（work）；审查（review）默认跳过二次确认
# UNIFIER_CONFIRM_EXEC=0 可关闭确认门
# UNIFIER_CONFIRM_REVIEW=1 可强制审查也走确认
        kind = (item.get("kind") or "work").lower()
        confirm_review = os.environ.get("UNIFIER_CONFIRM_REVIEW", "0") in ("1", "true", "True")
        need_confirm = confirm_on and (kind == "work" or (kind == "review" and confirm_review))
        if need_confirm:
            if key not in requested:
                tid = int(item["task_id"])
                try:
                    # 本地也写一份，API 再通知 App/飞书
                    request_confirm(
                        task_id=tid,
                        device_id=device_id,
                        agent_id=agent_id,
                        item=item,
                    )
                    api(
                        "POST",
                        f"{hub.rstrip('/')}/api/v1/tasks/{tid}/exec-confirm",
                        {
                            "action": "request",
                            "device_id": device_id,
                            "agent_id": agent_id,
                            "item": item,
                        },
                    )
                    print(f"[confirm] 等待确认 #{tid} {agent_id}")
                except Exception as e:
                    print(f"[warn] request confirm failed: {e}", file=sys.stderr)
                requested.add(key)
            continue

        seen.add(key)
        _dispatch_one(hub, device_id, agent_id, home, item, supervisor)


def poll_confirmed(
    hub: str,
    device_id: str,
    agents: list[str],
    home: Path,
    seen: set[str],
    supervisor: ExecutionSupervisor,
) -> None:
    for data in list_confirmed(device_id):
        item = data.get("item") or {}
        agent_id = data.get("agent_id") or item.get("agent_id")
        tid = int(data.get("task_id") or item.get("task_id") or 0)
        if not agent_id or agent_id not in agents or not tid:
            continue
        kind = item.get("kind") or "work"
        key = f"{agent_id}:{kind}:{tid}"
        if key in seen:
            pop_confirmed(tid)
            continue
        item.setdefault("task_id", tid)
        item.setdefault("kind", kind)
        print(f"[confirm] 已确认，开始执行 #{tid} {agent_id}")
        seen.add(key)
        try:
            _dispatch_one(hub, device_id, agent_id, home, item, supervisor)
        finally:
            pop_confirmed(tid)


def poll_review_nudge(hub: str, home: Path) -> None:
    """P0：审查卡住催促（默认 3 分钟）。"""
    minutes = int(os.environ.get("UNIFIER_REVIEW_NUDGE_MINUTES", "3"))
    if minutes <= 0:
        return
    state_path = home / "review-nudge-state.json"
    try:
        nudged = json.loads(state_path.read_text(encoding="utf-8")) if state_path.is_file() else {}
    except Exception:
        nudged = {}

    try:
        # 拉审查中任务
        tasks = []
        for st in ("ReviewPending", "Reviewing"):
            try:
                chunk = api("GET", f"{hub.rstrip('/')}/api/v1/tasks?status={st}")
                if isinstance(chunk, list):
                    tasks.extend(chunk)
                else:
                    tasks.extend(chunk.get("items") or [])
            except Exception:
                pass
    except Exception:
        return

    now = datetime.now(timezone.utc)
    for t in tasks:
        status = (t.get("status") or "").lower()
        if status not in ("reviewpending", "reviewing", "review_pending"):
            # 兼容枚举值
            if t.get("status") not in ("ReviewPending", "Reviewing"):
                continue
        tid = t.get("id") or t.get("task_id")
        if not tid:
            continue
        key = str(tid)
        updated = t.get("updated_at") or t.get("created_at")
        if not updated:
            continue
        try:
            ts = datetime.fromisoformat(str(updated).replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
        except Exception:
            continue
        waited = (now - ts).total_seconds() / 60.0
        if waited < minutes:
            continue
        if nudged.get(key):
            continue
        try:
            api(
                "POST",
                f"{hub.rstrip('/')}/api/v1/tasks/{tid}/lifecycle",
                {
                    "event": "task.review_waiting",
                    "extra": {
                        "waited_minutes": int(waited),
                        "missing_reviewers": t.get("review_summary", {}).get("pending")
                        if isinstance(t.get("review_summary"), dict)
                        else [],
                    },
                },
            )
            nudged[key] = now.isoformat()
            print(f"[nudge] 审查等待 #{tid} ~{int(waited)}min")
        except Exception as e:
            print(f"[warn] review nudge: {e}", file=sys.stderr)

    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(nudged, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="联合器 Inbox Auto-Runner")
    parser.add_argument("--hub", default=os.environ.get("HUB_URL", "http://127.0.0.1:8787"))
    parser.add_argument(
        "--device-id",
        default=os.environ.get("UNIFIER_DEVICE_ID")
        or os.environ.get("DEVICE_ID")
        or "",
    )
    parser.add_argument(
        "--agents",
        default=os.environ.get("INBOX_AUTO_AGENTS", "cursor,trae,dsh"),
    )
    parser.add_argument(
        "--home",
        default=os.environ.get("UNIFIER_HOME", str(Path.home() / ".unifier")),
    )
    parser.add_argument("--interval", type=int, default=int(os.environ.get("INBOX_AUTO_INTERVAL", "8")))
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    if not args.device_id:
        args.device_id = socket.gethostname().split(".")[0]

    agents = [a.strip() for a in args.agents.split(",") if a.strip()]
    home = Path(args.home)
    home.mkdir(parents=True, exist_ok=True)
    seen: set[str] = set()
    requested: set[str] = set()
    outbox_seen: set[str] = set()
    supervisor = ExecutionSupervisor(home)

    print(
        f"Inbox Auto-Runner 启动 hub={args.hub} device={args.device_id} "
        f"agents={','.join(agents)} interval={args.interval}s "
        f"exec_timeout={supervisor.timeout_seconds}s "
        f"confirm_exec={confirm_exec_enabled()}"
    )

    while True:
        try:
            heartbeat(args.hub, args.device_id)
            fired = supervisor.check_timeouts()
            for key in fired:
                print(f"[supervisor] 熔断 {key}", file=sys.stderr)
            poll_confirmed(args.hub, args.device_id, agents, home, seen, supervisor)
            for agent in agents:
                poll_agent(
                    args.hub, args.device_id, agent, home, seen, requested, supervisor
                )
                poll_outbox(args.hub, args.device_id, agent, home, outbox_seen)
            poll_review_nudge(args.hub, home)
        except urllib.error.URLError as e:
            print(f"[warn] Hub 不可达: {e}", file=sys.stderr)
        except Exception as e:
            print(f"[warn] {e}", file=sys.stderr)
        if args.once:
            break
        time.sleep(max(3, args.interval))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
