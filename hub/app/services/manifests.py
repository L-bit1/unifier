from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session, joinedload

from app.models import Manifest, Project, Task


def resolve_manifest_fields(
    body_payload: dict[str, Any],
    *,
    intent: str | None = None,
    cot_summary: str | None = None,
    channel: str | None = None,
    channel_message_id: str | None = None,
    feishu_message_id: str | None = None,
    task: Task | None = None,
) -> dict[str, Any]:
    """合并 API 顶层字段与 payload，写入 Manifest 列。"""
    payload = dict(body_payload or {})
    resolved_intent = (intent or payload.get("intent") or "").strip() or None
    resolved_cot = (cot_summary or payload.get("cot_summary") or "").strip() or None
    resolved_channel = (channel or payload.get("channel") or "feishu").strip() or "feishu"

    msg_id = (
        channel_message_id
        or feishu_message_id
        or payload.get("channel_message_id")
        or payload.get("feishu_message_id")
    )
    if not msg_id and task:
        msg_id = task.feishu_message_id

    if resolved_intent:
        payload["intent"] = resolved_intent
    if resolved_cot:
        payload["cot_summary"] = resolved_cot
    payload["channel"] = resolved_channel
    if msg_id:
        payload["channel_message_id"] = msg_id
        if resolved_channel == "feishu":
            payload["feishu_message_id"] = msg_id

    return {
        "intent": resolved_intent,
        "cot_summary": resolved_cot,
        "channel": resolved_channel,
        "channel_message_id": msg_id,
        "payload_json": json.dumps(payload, ensure_ascii=False),
    }


def manifest_payload(m: Manifest) -> dict[str, Any]:
    base = json.loads(m.payload_json or "{}")
    if m.intent and "intent" not in base:
        base["intent"] = m.intent
    if m.cot_summary and "cot_summary" not in base:
        base["cot_summary"] = m.cot_summary
    if m.channel and "channel" not in base:
        base["channel"] = m.channel
    if m.channel_message_id:
        base.setdefault("channel_message_id", m.channel_message_id)
        if m.channel == "feishu":
            base.setdefault("feishu_message_id", m.channel_message_id)
    return base


def manifest_to_dict(m: Manifest) -> dict[str, Any]:
    return {
        "id": m.id,
        "task_id": m.task_id,
        "agent_id": m.agent_id,
        "device_id": m.device_id,
        "intent": m.intent,
        "cot_summary": m.cot_summary,
        "channel": m.channel,
        "channel_message_id": m.channel_message_id,
        "feishu_message_id": m.channel_message_id if m.channel == "feishu" else None,
        "payload": manifest_payload(m),
        "submitted_at": m.submitted_at,
    }


def search_manifests(
    db: Session,
    *,
    q: str | None = None,
    channel: str | None = None,
    task_id: int | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """意图检索：词袋向量余弦 + 子串加权（轻量，无额外依赖）。"""
    from app.services.vector_search import rank_by_vector

    query = (
        db.query(Manifest)
        .options(joinedload(Manifest.task).joinedload(Task.project))
        .order_by(Manifest.submitted_at.desc())
    )
    if task_id is not None:
        query = query.filter(Manifest.task_id == task_id)
    if channel:
        query = query.filter(Manifest.channel == channel)

    # 向量排序需要更大候选池
    fetch_n = max(1, min(limit * 4 if q else limit, 400))
    rows = query.limit(fetch_n).all()
    needle = (q or "").strip()

    docs: list[tuple[Any, str]] = []
    for m in rows:
        task = m.task
        project = task.project if task else None
        haystack = " ".join(
            filter(
                None,
                [
                    m.intent,
                    m.cot_summary,
                    m.payload_json,
                    task.title if task else None,
                    task.description if task else None,
                    f"{project.github_owner}/{project.github_repo}" if project else None,
                ],
            )
        )
        docs.append((m, haystack))

    if needle:
        ranked = rank_by_vector(needle, docs, min_score=0.06)
        ordered = [m for m, _score in ranked]
    else:
        ordered = [m for m, _ in docs]

    results: list[dict[str, Any]] = []
    for m in ordered[: max(1, min(limit, 200))]:
        task = m.task
        project = task.project if task else None
        item = manifest_to_dict(m)
        item["task_title"] = task.title if task else None
        item["task_status"] = task.status if task else None
        item["project"] = (
            f"{project.github_owner}/{project.github_repo}" if project else None
        )
        item["task_feishu_message_id"] = task.feishu_message_id if task else None
        if needle:
            from app.services.vector_search import cosine, embed

            hay = next((h for doc, h in docs if doc is m), "")
            item["score"] = round(cosine(embed(needle), embed(hay)), 4)
        results.append(item)
    return results


def _text_diff(left: str, right: str) -> list[str]:
    import difflib

    left_lines = (left or "").splitlines() or [""]
    right_lines = (right or "").splitlines() or [""]
    return list(
        difflib.unified_diff(
            left_lines,
            right_lines,
            lineterm="",
            n=3,
        )
    )


def compare_task_manifests(db: Session, task_id: int) -> dict[str, Any]:
    """双/多 Agent manifest 差异：按 agent 取最新一份比对。"""
    task = (
        db.query(Task)
        .options(joinedload(Task.manifests), joinedload(Task.project))
        .filter(Task.id == task_id)
        .first()
    )
    if not task:
        return {"task_id": task_id, "found": False, "pairs": []}

    project = task.project
    by_agent: dict[str, Manifest] = {}
    for m in sorted(task.manifests, key=lambda x: x.submitted_at):
        by_agent[m.agent_id] = m

    agents = sorted(by_agent.keys())
    pairs: list[dict[str, Any]] = []
    if len(agents) >= 2:
        for i in range(len(agents)):
            for j in range(i + 1, len(agents)):
                left = by_agent[agents[i]]
                right = by_agent[agents[j]]
                lp = manifest_payload(left)
                rp = manifest_payload(right)
                left_summary = str(lp.get("summary") or "")
                right_summary = str(rp.get("summary") or "")
                left_files = lp.get("files") or []
                right_files = rp.get("files") or []
                if not isinstance(left_files, list):
                    left_files = []
                if not isinstance(right_files, list):
                    right_files = []
                left_set = {str(f) for f in left_files}
                right_set = {str(f) for f in right_files}
                field_diffs = []
                for field, lv, rv in (
                    ("intent", left.intent or "", right.intent or ""),
                    ("cot_summary", left.cot_summary or "", right.cot_summary or ""),
                    ("summary", left_summary, right_summary),
                ):
                    if lv == rv:
                        continue
                    field_diffs.append(
                        {
                            "field": field,
                            "left_text": lv,
                            "right_text": rv,
                            "unified_diff": _text_diff(lv, rv),
                        }
                    )
                pairs.append(
                    {
                        "left_agent": left.agent_id,
                        "right_agent": right.agent_id,
                        "left_device": left.device_id,
                        "right_device": right.device_id,
                        "left_manifest_id": left.id,
                        "right_manifest_id": right.id,
                        "left_submitted_at": left.submitted_at,
                        "right_submitted_at": right.submitted_at,
                        "field_diffs": field_diffs,
                        "files_only_left": sorted(left_set - right_set),
                        "files_only_right": sorted(right_set - left_set),
                        "files_common": sorted(left_set & right_set),
                    }
                )

    return {
        "task_id": task.id,
        "found": True,
        "task_title": task.title,
        "task_status": task.status,
        "project": (
            f"{project.github_owner}/{project.github_repo}" if project else None
        ),
        "agents": agents,
        "manifest_count": len(task.manifests),
        "pairs": pairs,
    }
