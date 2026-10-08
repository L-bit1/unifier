"""联合器内置工作流：节点注册表与执行器。"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import smtplib
import time
from email.mime.text import MIMEText
from typing import Any, Callable

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.services.orchestrate import command_status, dispatch_command

logger = logging.getLogger(__name__)

NodeExecutor = Callable[[dict[str, Any], dict[str, Any], Session], dict[str, Any]]

_TEMPLATE_RE = re.compile(r"\{\{\s*([\w.]+)\s*\}\}")


def render_template(value: str, ctx: dict[str, Any]) -> str:
    def repl(match: re.Match[str]) -> str:
        path = match.group(1).split(".")
        cur: Any = ctx
        for part in path:
            if isinstance(cur, dict):
                cur = cur.get(part)
            else:
                return ""
        return "" if cur is None else str(cur)

    return _TEMPLATE_RE.sub(repl, value)


def deep_render(obj: Any, ctx: dict[str, Any]) -> Any:
    if isinstance(obj, str):
        return render_template(obj, ctx)
    if isinstance(obj, dict):
        return {k: deep_render(v, ctx) for k, v in obj.items()}
    if isinstance(obj, list):
        return [deep_render(v, ctx) for v in obj]
    return obj


def _resolve_path(ctx: dict[str, Any], path: str) -> Any:
    cur: Any = ctx
    for part in path.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


def _exec_trigger_hub_event(params: dict, ctx: dict, _db: Session) -> dict[str, Any]:
    allowed = params.get("events") or []
    event_type = (ctx.get("event") or {}).get("type", "")
    if allowed and event_type not in allowed:
        return {"ok": False, "skip": True, "branch": "default"}
    return {"ok": True, "output": ctx.get("event"), "branch": "default"}


def _exec_trigger_webhook(params: dict, ctx: dict, _db: Session) -> dict[str, Any]:
    return {"ok": True, "output": ctx.get("event", {}).get("data"), "branch": "default"}


def _exec_trigger_schedule(params: dict, ctx: dict, _db: Session) -> dict[str, Any]:
    return {"ok": True, "output": {"scheduled": True, "cron": params.get("cron")}, "branch": "default"}


def _exec_logic_if(params: dict, ctx: dict, _db: Session) -> dict[str, Any]:
    field = params.get("field", "")
    op = params.get("operator", "equals")
    expected = params.get("value")
    actual = _resolve_path(ctx, field)
    ok = False
    if op == "equals":
        ok = actual == expected
    elif op == "not_equals":
        ok = actual != expected
    elif op == "exists":
        ok = actual is not None and actual != ""
    elif op == "truthy":
        ok = bool(actual)
    return {"ok": True, "output": {"actual": actual, "matched": ok}, "branch": "true" if ok else "false"}


def _exec_logic_delay(params: dict, ctx: dict, _db: Session) -> dict[str, Any]:
    seconds = float(params.get("seconds", 1))
    time.sleep(min(max(seconds, 0), 300))
    return {"ok": True, "output": {"slept": seconds}, "branch": "default"}


def _exec_action_log(params: dict, ctx: dict, _db: Session) -> dict[str, Any]:
    message = deep_render(params.get("message", ""), ctx)
    logger.info("[workflow] %s", message)
    return {"ok": True, "output": {"message": message}, "branch": "default"}


def _exec_action_http(params: dict, ctx: dict, _db: Session) -> dict[str, Any]:
    rendered = deep_render(
        {
            "method": params.get("method", "GET"),
            "url": params.get("url", ""),
            "headers": params.get("headers") or {},
            "body": params.get("body"),
        },
        ctx,
    )
    if not rendered["url"]:
        return {"ok": False, "error": "url 为空", "branch": "default"}
    try:
        resp = httpx.request(
            rendered["method"],
            rendered["url"],
            headers=rendered["headers"],
            json=rendered["body"] if rendered["body"] is not None else None,
            timeout=float(params.get("timeout", 30)),
        )
        body: Any
        try:
            body = resp.json()
        except Exception:
            body = resp.text[:2000]
        return {
            "ok": resp.is_success,
            "output": {"status": resp.status_code, "body": body},
            "branch": "default",
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc), "branch": "default"}


def _exec_action_feishu(params: dict, ctx: dict, _db: Session) -> dict[str, Any]:
    from app.services.feishu import FeishuError, feishu_client

    chat_id = deep_render(params.get("chat_id") or "", ctx)
    if not chat_id:
        chat_id = _resolve_path(ctx, "event.data.feishu_chat_id") or ""
    text = deep_render(params.get("text", ""), ctx)
    if not chat_id or not text:
        return {"ok": False, "error": "缺少 chat_id 或 text", "branch": "default"}
    if not settings.feishu_configured:
        return {"ok": False, "error": "飞书未配置", "branch": "default"}
    try:
        message_id = asyncio.run(feishu_client.send_text_to_chat(chat_id, text))
        return {"ok": True, "output": {"message_id": message_id}, "branch": "default"}
    except FeishuError as exc:
        return {"ok": False, "error": str(exc), "branch": "default"}


def _exec_action_email(params: dict, ctx: dict, _db: Session) -> dict[str, Any]:
    host = params.get("smtp_host") or settings.workflow_smtp_host
    port = int(params.get("smtp_port") or settings.workflow_smtp_port)
    user = params.get("smtp_user") or settings.workflow_smtp_user
    password = params.get("smtp_password") or settings.workflow_smtp_password
    to_addr = deep_render(params.get("to", ""), ctx)
    subject = deep_render(params.get("subject", "联合器通知"), ctx)
    body = deep_render(params.get("body", ""), ctx)
    if not host or not to_addr:
        return {"ok": False, "error": "缺少 smtp_host 或 to", "branch": "default"}
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = user or settings.workflow_smtp_from
    msg["To"] = to_addr
    try:
        with smtplib.SMTP(host, port, timeout=20) as smtp:
            if params.get("use_tls", True):
                smtp.starttls()
            if user and password:
                smtp.login(user, password)
            smtp.send_message(msg)
        return {"ok": True, "output": {"to": to_addr}, "branch": "default"}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "branch": "default"}


def _exec_action_hub_dispatch(params: dict, ctx: dict, db: Session) -> dict[str, Any]:
    rendered = deep_render(
        {
            "github_owner": params.get("github_owner", ""),
            "github_repo": params.get("github_repo", ""),
            "title": params.get("title", ""),
            "branch": params.get("branch", ""),
            "implementer_device_id": params.get("implementer_device_id")
            or settings.feishu_default_implementer_device,
            "implementer_agent_id": params.get("implementer_agent_id")
            or settings.feishu_default_implementer_agent,
        },
        ctx,
    )
    if not all([rendered["github_owner"], rendered["github_repo"], rendered["title"]]):
        return {"ok": False, "error": "缺少 github_owner/repo/title", "branch": "default"}
    from app.services.agent_slots import resolve_dispatch_roles

    try:
        impl_d = rendered["implementer_device_id"]
        impl_a = rendered["implementer_agent_id"]
        reviewers = params.get("required_reviewers")
        if not reviewers:
            impl_d, impl_a, reviewers = resolve_dispatch_roles(db)
        task, project = dispatch_command(
            db,
            github_owner=rendered["github_owner"],
            github_repo=rendered["github_repo"],
            title=rendered["title"],
            description=params.get("description"),
            branch=rendered["branch"] or f"feature/workflow-{int(time.time())}",
            implementer_device_id=impl_d,
            implementer_agent_id=impl_a,
            required_reviewers=reviewers or [],
            feishu_chat_id=_resolve_path(ctx, "event.data.feishu_chat_id"),
        )
        status = command_status(task, db)
        return {
            "ok": True,
            "output": {
                "task_id": task.id,
                "project": f"{project.github_owner}/{project.github_repo}",
                "status": status,
            },
            "branch": "default",
        }
    except ValueError as exc:
        return {"ok": False, "error": str(exc), "branch": "default"}


def _exec_action_hub_task_status(params: dict, ctx: dict, db: Session) -> dict[str, Any]:
    from app.models import Task

    task_id = params.get("task_id") or _resolve_path(ctx, "event.data.task_id")
    if not task_id:
        return {"ok": False, "error": "缺少 task_id", "branch": "default"}
    task = db.get(Task, int(task_id))
    if not task:
        return {"ok": False, "error": f"任务 {task_id} 不存在", "branch": "default"}
    status = command_status(task, db)
    ctx.setdefault("vars", {})["task_status"] = status
    return {"ok": True, "output": status, "branch": "default"}


def _exec_action_hub_connectivity(params: dict, ctx: dict, db: Session) -> dict[str, Any]:
    from app.models import Device
    from app.services.devices import connectivity_report, parse_expected_devices

    expected = params.get("expected_devices")
    expected_ids = (
        [x.strip() for x in expected.split(",") if x.strip()]
        if isinstance(expected, str)
        else parse_expected_devices()
    )
    devices = db.query(Device).order_by(Device.device_id).all()
    report = connectivity_report(devices, expected_device_ids=expected_ids or None)
    ctx.setdefault("vars", {})["connectivity"] = report
    branch = "true" if report.get("ready_for_dispatch") else "false"
    return {"ok": True, "output": report, "branch": branch}


def _exec_action_set_var(params: dict, ctx: dict, _db: Session) -> dict[str, Any]:
    name = params.get("name", "")
    value = deep_render(params.get("value", ""), ctx)
    if name:
        ctx.setdefault("vars", {})[name] = value
    return {"ok": True, "output": {name: value}, "branch": "default"}


NODE_EXECUTORS: dict[str, NodeExecutor] = {
    "trigger.hub_event": _exec_trigger_hub_event,
    "trigger.webhook": _exec_trigger_webhook,
    "trigger.schedule": _exec_trigger_schedule,
    "logic.if": _exec_logic_if,
    "logic.delay": _exec_logic_delay,
    "action.log": _exec_action_log,
    "action.http": _exec_action_http,
    "action.feishu": _exec_action_feishu,
    "action.email": _exec_action_email,
    "action.hub_dispatch": _exec_action_hub_dispatch,
    "action.hub_task_status": _exec_action_hub_task_status,
    "action.hub_connectivity": _exec_action_hub_connectivity,
    "action.set_var": _exec_action_set_var,
}


NODE_CATALOG: list[dict[str, Any]] = [
    {
        "type": "trigger.hub_event",
        "category": "trigger",
        "name": "Hub 事件",
        "description": "任务派活、审查、merge 等生命周期事件",
        "params_schema": {
            "events": {
                "type": "multiselect",
                "options": [
                    "task.dispatched",
                    "task.manifest_submitted",
                    "task.review_started",
                    "task.review_submitted",
                    "task.merge_ready",
                    "task.changes_requested",
                ],
            }
        },
        "outputs": ["default"],
    },
    {
        "type": "trigger.webhook",
        "category": "trigger",
        "name": "Webhook",
        "description": "外部 POST 触发（GitHub 等）",
        "params_schema": {},
        "outputs": ["default"],
    },
    {
        "type": "trigger.schedule",
        "category": "trigger",
        "name": "定时",
        "description": "Cron 定时触发（5 段：分 时 日 月 周）",
        "params_schema": {"cron": {"type": "string", "default": "0 9 * * *"}},
        "outputs": ["default"],
    },
    {
        "type": "logic.if",
        "category": "logic",
        "name": "条件分支",
        "params_schema": {
            "field": {"type": "string", "placeholder": "event.data.merge_ready"},
            "operator": {
                "type": "select",
                "options": ["equals", "not_equals", "exists", "truthy"],
            },
            "value": {"type": "string"},
        },
        "outputs": ["true", "false"],
    },
    {
        "type": "logic.delay",
        "category": "logic",
        "name": "延迟",
        "params_schema": {"seconds": {"type": "number", "default": 5}},
        "outputs": ["default"],
    },
    {
        "type": "action.feishu",
        "category": "action",
        "name": "飞书消息",
        "params_schema": {
            "chat_id": {"type": "string", "placeholder": "留空则用 event.data.feishu_chat_id"},
            "text": {"type": "text", "placeholder": "任务 {{event.data.task_id}} 已完成"},
        },
        "outputs": ["default"],
    },
    {
        "type": "action.email",
        "category": "action",
        "name": "邮件",
        "params_schema": {
            "to": {"type": "string"},
            "subject": {"type": "string"},
            "body": {"type": "text"},
        },
        "outputs": ["default"],
    },
    {
        "type": "action.http",
        "category": "action",
        "name": "HTTP 请求",
        "description": "GitHub API、自定义 Webhook 等",
        "params_schema": {
            "method": {"type": "select", "options": ["GET", "POST", "PUT", "PATCH"]},
            "url": {"type": "string"},
            "body": {"type": "json"},
        },
        "outputs": ["default"],
    },
    {
        "type": "action.hub_dispatch",
        "category": "action",
        "name": "Hub 派活",
        "params_schema": {
            "github_owner": {"type": "string"},
            "github_repo": {"type": "string"},
            "title": {"type": "string"},
            "branch": {"type": "string"},
        },
        "outputs": ["default"],
    },
    {
        "type": "action.hub_task_status",
        "category": "action",
        "name": "查任务状态",
        "params_schema": {"task_id": {"type": "string", "placeholder": "{{event.data.task_id}}"}},
        "outputs": ["default"],
    },
    {
        "type": "action.hub_connectivity",
        "category": "action",
        "name": "设备联通检查",
        "params_schema": {
            "expected_devices": {"type": "string", "placeholder": "mac-a,win-pc"},
        },
        "outputs": ["true", "false"],
    },
    {
        "type": "action.set_var",
        "category": "action",
        "name": "设置变量",
        "params_schema": {
            "name": {"type": "string"},
            "value": {"type": "string"},
        },
        "outputs": ["default"],
    },
    {
        "type": "action.log",
        "category": "action",
        "name": "日志",
        "params_schema": {"message": {"type": "string"}},
        "outputs": ["default"],
    },
]
