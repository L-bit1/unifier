"""联合器内置工作流引擎：解析图、执行节点、记录运行。"""
from __future__ import annotations

import json
import logging
import threading
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Workflow, WorkflowRun, utcnow
from app.services.workflow_nodes import NODE_EXECUTORS

logger = logging.getLogger(__name__)


def parse_graph(graph_json: str) -> dict[str, Any]:
    data = json.loads(graph_json or "{}")
    if "nodes" not in data:
        raise ValueError("工作流 graph 缺少 nodes")
    return data


def _index_graph(graph: dict[str, Any]) -> tuple[dict[str, dict], dict[str, list[dict]]]:
    nodes = {n["id"]: n for n in graph.get("nodes", [])}
    edges: dict[str, list[dict]] = {nid: [] for nid in nodes}
    for edge in graph.get("edges", []):
        src = edge.get("from")
        if src in edges:
            edges[src].append(edge)
    return nodes, edges


def _find_trigger_node(graph: dict[str, Any]) -> dict[str, Any] | None:
    for node in graph.get("nodes", []):
        if str(node.get("type", "")).startswith("trigger."):
            return node
    return None


def _next_nodes(edges: list[dict], branch: str) -> list[str]:
    targets: list[str] = []
    for edge in edges:
        out = edge.get("output") or "default"
        if out == branch or (branch == "default" and out in ("", "default")):
            tgt = edge.get("to")
            if tgt:
                targets.append(tgt)
    return targets


def execute_workflow(
    db: Session,
    workflow: Workflow,
    *,
    event_type: str,
    event_data: dict[str, Any] | None = None,
    trigger: str = "hub_event",
) -> WorkflowRun:
    graph = parse_graph(workflow.graph_json)
    trigger_node = _find_trigger_node(graph)
    if not trigger_node:
        run = WorkflowRun(
            workflow_id=workflow.id,
            status="failed",
            trigger_type=trigger,
            trigger_event=event_type,
            error="工作流缺少触发器节点",
            finished_at=utcnow(),
        )
        db.add(run)
        db.commit()
        return run

    ctx: dict[str, Any] = {
        "event": {
            "type": event_type,
            "data": event_data or {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        "vars": {},
    }

    run = WorkflowRun(
        workflow_id=workflow.id,
        status="running",
        trigger_type=trigger,
        trigger_event=event_type,
        input_json=json.dumps(ctx["event"], ensure_ascii=False),
    )
    db.add(run)
    db.flush()

    nodes, edge_map = _index_graph(graph)
    queue = [trigger_node["id"]]
    visited: set[str] = set()
    last_output: Any = None
    error: str | None = None
    ok = True

    while queue:
        node_id = queue.pop(0)
        if node_id in visited:
            continue
        visited.add(node_id)
        node = nodes.get(node_id)
        if not node:
            continue

        node_type = node.get("type", "")
        executor = NODE_EXECUTORS.get(node_type)
        if not executor:
            error = f"未知节点类型: {node_type}"
            ok = False
            break

        params = node.get("params") or {}
        try:
            result = executor(params, ctx, db)
        except Exception as exc:
            logger.exception("workflow node %s failed", node_id)
            error = str(exc)
            ok = False
            break

        if result.get("skip"):
            run.status = "skipped"
            run.output_json = json.dumps({"reason": "trigger filter"}, ensure_ascii=False)
            run.finished_at = utcnow()
            db.commit()
            return run

        ctx["last_output"] = result.get("output")
        last_output = result.get("output")
        if not result.get("ok", True):
            ok = False
            error = result.get("error") or "节点执行失败"
            break

        branch = result.get("branch", "default")
        for nxt in _next_nodes(edge_map.get(node_id, []), branch):
            if nxt not in visited:
                queue.append(nxt)

    run.status = "success" if ok else "failed"
    run.output_json = json.dumps({"last_output": last_output}, ensure_ascii=False)
    run.error = error
    run.finished_at = utcnow()
    db.commit()
    db.refresh(run)
    return run


def run_workflow_by_id(
    workflow_id: int,
    *,
    event_type: str = "manual.run",
    event_data: dict[str, Any] | None = None,
    trigger: str = "manual",
) -> WorkflowRun | None:
    db = SessionLocal()
    try:
        workflow = db.get(Workflow, workflow_id)
        if not workflow or not workflow.active:
            return None
        return execute_workflow(
            db,
            workflow,
            event_type=event_type,
            event_data=event_data,
            trigger=trigger,
        )
    finally:
        db.close()


def trigger_hub_event(event_type: str, event_data: dict[str, Any]) -> None:
    db = SessionLocal()
    try:
        workflows = (
            db.query(Workflow)
            .filter(Workflow.active.is_(True), Workflow.trigger_kind == "hub_event")
            .all()
        )
        for wf in workflows:
            graph = parse_graph(wf.graph_json)
            trigger = _find_trigger_node(graph)
            if not trigger:
                continue
            allowed = (trigger.get("params") or {}).get("events") or []
            if allowed and event_type not in allowed:
                continue
            execute_workflow(
                db,
                wf,
                event_type=event_type,
                event_data=event_data,
                trigger="hub_event",
            )
    except Exception:
        logger.exception("trigger_hub_event failed for %s", event_type)
    finally:
        db.close()


def trigger_hub_event_async(event_type: str, event_data: dict[str, Any]) -> None:
    threading.Thread(
        target=trigger_hub_event,
        args=(event_type, event_data),
        daemon=True,
        name=f"wf-{event_type}",
    ).start()


def trigger_webhook(hook_id: str, payload: dict[str, Any]) -> list[WorkflowRun]:
    db = SessionLocal()
    runs: list[WorkflowRun] = []
    try:
        workflows = (
            db.query(Workflow)
            .filter(Workflow.active.is_(True), Workflow.hook_id == hook_id)
            .all()
        )
        for wf in workflows:
            run = execute_workflow(
                db,
                wf,
                event_type="webhook.received",
                event_data=payload,
                trigger="webhook",
            )
            runs.append(run)
        return runs
    finally:
        db.close()


def sync_workflow_meta(workflow: Workflow) -> None:
    graph = parse_graph(workflow.graph_json)
    trigger = _find_trigger_node(graph)
    if not trigger:
        workflow.trigger_kind = "unknown"
        return
    workflow.trigger_kind = trigger.get("type", "unknown").replace("trigger.", "")
    params = trigger.get("params") or {}
    if workflow.trigger_kind == "webhook" and not workflow.hook_id:
        workflow.hook_id = uuid.uuid4().hex[:16]
    if workflow.trigger_kind == "schedule":
        workflow.schedule_cron = params.get("cron") or workflow.schedule_cron
