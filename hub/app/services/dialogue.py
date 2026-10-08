"""圆桌对话：用户开题 → Cursor/Trae 同轮各回一条 → 互读 → 下一轮。"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.models import DialogueAck, DialogueMessage, DialogueRoom, utcnow

DEFAULT_PARTICIPANTS = ["cursor", "trae"]


def _ensure_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _msg_dict(m: DialogueMessage) -> dict[str, Any]:
    return {
        "id": m.id,
        "round": m.round,
        "role": m.role,
        "participant": m.participant,
        "body": m.body,
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


def _room_brief(room: DialogueRoom) -> dict[str, Any]:
    return {
        "id": room.id,
        "project_key": room.project_key,
        "title": room.title,
        "status": room.status,
        "current_round": room.current_round,
        "round_complete": room.round_complete,
        "participants": room.participants,
        "created_at": room.created_at.isoformat() if room.created_at else None,
        "closed_at": room.closed_at.isoformat() if room.closed_at else None,
    }


def _replied_agents(db: Session, room: DialogueRoom, round_no: int) -> set[str]:
    rows = (
        db.query(DialogueMessage)
        .filter(
            DialogueMessage.room_id == room.id,
            DialogueMessage.round == round_no,
            DialogueMessage.role == "agent",
        )
        .all()
    )
    return {r.participant for r in rows}


def _maybe_complete_round(db: Session, room: DialogueRoom) -> None:
    if room.status != "open" or room.round_complete:
        return
    replied = _replied_agents(db, room, room.current_round)
    expected = set(room.participants)
    if expected and expected.issubset(replied):
        room.round_complete = True
        _write_system(
            db,
            room,
            f"第 {room.current_round} 轮齐员，可互读对方发言。",
        )
        return

    opened = _ensure_aware(room.round_opened_at)
    deadline = opened + timedelta(seconds=settings.dialogue_round_timeout_seconds)
    if utcnow() < deadline:
        return

    missing = sorted(expected - replied)
    if missing:
        _write_system(
            db,
            room,
            f"第 {room.current_round} 轮超时（{settings.dialogue_round_timeout_seconds}s），"
            f"缺席: {', '.join(missing)}。本轮强制结束。",
        )
    room.round_complete = True


def _write_system(db: Session, room: DialogueRoom, body: str) -> DialogueMessage:
    msg = DialogueMessage(
        room_id=room.id,
        round=room.current_round,
        role="system",
        participant="system",
        body=body,
    )
    db.add(msg)
    db.flush()
    return msg


def open_room(
    db: Session,
    *,
    title: str,
    topic: str,
    project_key: str = "maotai",
    participants: list[str] | None = None,
) -> dict[str, Any]:
    parts = [p.strip() for p in (participants or DEFAULT_PARTICIPANTS) if p.strip()]
    if len(parts) < 1:
        raise HTTPException(status_code=400, detail="至少需要一名 participant")
    room = DialogueRoom(
        project_key=(project_key or "maotai").strip(),
        title=(title or topic[:80]).strip() or "untitled",
        status="open",
        current_round=1,
        round_complete=False,
        round_opened_at=utcnow(),
    )
    room.participants = parts
    db.add(room)
    db.flush()
    db.add(
        DialogueMessage(
            room_id=room.id,
            round=1,
            role="user",
            participant="user",
            body=topic.strip(),
        )
    )
    db.commit()
    db.refresh(room)
    return {"room": _room_brief(room), "message": f"已开房 #{room.id} · {room.title}"}


def list_open_rooms(
    db: Session, *, project_key: str | None = None
) -> list[dict[str, Any]]:
    q = db.query(DialogueRoom).filter(DialogueRoom.status == "open")
    if project_key:
        q = q.filter(DialogueRoom.project_key == project_key.strip())
    rooms = q.order_by(DialogueRoom.id.desc()).all()
    return [_room_brief(r) for r in rooms]


def get_room(db: Session, room_id: int) -> DialogueRoom:
    room = (
        db.query(DialogueRoom)
        .options(joinedload(DialogueRoom.messages))
        .filter(DialogueRoom.id == room_id)
        .first()
    )
    if not room:
        raise HTTPException(status_code=404, detail="房间不存在")
    return room


def post_user_message(
    db: Session, room_id: int, body: str, *, auto_reply: bool | None = None
) -> dict[str, Any]:
    room = get_room(db, room_id)
    if room.status != "open":
        raise HTTPException(status_code=400, detail="房间已结束")
    text = (body or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="消息不能为空")

    _maybe_complete_round(db, room)
    if not room.round_complete:
        # 强制结束当前轮再开新轮，避免卡住
        missing = sorted(set(room.participants) - _replied_agents(db, room, room.current_round))
        note = f"用户推进新话题，强制结束第 {room.current_round} 轮"
        if missing:
            note += f"（未发言: {', '.join(missing)}）"
        _write_system(db, room, note)
        room.round_complete = True

    room.current_round += 1
    room.round_complete = False
    room.round_opened_at = utcnow()
    msg = DialogueMessage(
        room_id=room.id,
        round=room.current_round,
        role="user",
        participant="user",
        body=text,
    )
    db.add(msg)
    db.commit()
    db.refresh(room)

    do_auto = settings.dialogue_auto_reply if auto_reply is None else bool(auto_reply)
    auto_result: dict[str, Any] | None = None
    if do_auto:
        auto_result = auto_fill_pending(db, room.id)

    room = get_room(db, room_id)
    return {
        "room": _room_brief(room),
        "message": _msg_dict(msg),
        "hint": (
            f"第 {room.current_round} 轮已齐，双方可互读"
            if room.round_complete
            else f"第 {room.current_round} 轮已开题，等待 {', '.join(room.participants)}"
        ),
        "auto_reply": do_auto,
        "auto_fill": auto_result,
        "transcript": transcript(db, room_id),
    }


def _fallback_auto_body(who: str, user_topic: str, peer_snippets: list[str]) -> str:
    peers = "；".join(peer_snippets[:2]) if peer_snippets else "（尚无对方发言）"
    topic = (user_topic or "")[:200]
    if who == "cursor":
        return (
            f"【Cursor·Hub代言】收到：{topic}\n"
            f"立场：先给可执行结论与证据路径，避免空转。\n"
            f"已知对方/上下文：{peers}\n"
            f"（IDE 未及时 poll 时由 Hub 自动补位；你可在 Cursor 里继续深挖。）"
        )
    if who == "trae":
        return (
            f"【Trae·Hub代言】收到：{topic}\n"
            f"补充：交叉验证 Cursor 结论，标出风险与遗漏。\n"
            f"已知对方/上下文：{peers}\n"
            f"（IDE 未及时 poll 时由 Hub 自动补位。）"
        )
    return f"【{who}·Hub代言】收到：{topic}"


def _soul_auto_body(who: str, user_topic: str, transcript_tail: str) -> str | None:
    if not settings.dialogue_auto_use_soul:
        return None
    try:
        from app.services.soul_bridge import soul_chat_sync
    except Exception:
        return None
    prompt = (
        f"你是联合器圆桌里的参与者「{who}」。用中文简短回复（≤180字）。\n"
        f"用户本轮问题：{user_topic}\n"
        f"近期 transcript：\n{transcript_tail[-2500:]}\n"
        f"要求：有实质观点；若是 trae 请与 cursor 互补而非重复。"
    )
    res = soul_chat_sync(message=prompt, domain="general")
    if res.get("ok") and (res.get("reply") or "").strip():
        return f"【{who}·灵魂代言】{(res.get('reply') or '').strip()[:800]}"
    return None


def auto_fill_pending(db: Session, room_id: int) -> dict[str, Any]:
    """为尚未发言的 participant 自动 reply（Hub 代言）。"""
    room = get_room(db, room_id)
    if room.status != "open":
        return {"skipped": True, "reason": "room_closed"}
    _maybe_complete_round(db, room)
    if room.round_complete:
        return {"skipped": True, "reason": "round_already_complete"}

    msgs = (
        db.query(DialogueMessage)
        .filter(DialogueMessage.room_id == room.id)
        .order_by(DialogueMessage.id.asc())
        .all()
    )
    user_topic = ""
    for m in reversed(msgs):
        if m.round == room.current_round and m.role == "user":
            user_topic = m.body
            break
    transcript_txt = "\n".join(
        f"R{m.round} {m.participant}: {m.body}" for m in msgs[-20:]
    )
    replied = _replied_agents(db, room, room.current_round)
    filled: list[str] = []
    errors: list[str] = []

    for who in room.participants:
        if who in replied:
            continue
        peer_snips = [
            f"{m.participant}:{m.body[:80]}"
            for m in msgs
            if m.round == room.current_round and m.role == "agent" and m.participant != who
        ]
        body = _soul_auto_body(who, user_topic, transcript_txt)
        if not body:
            body = _fallback_auto_body(who, user_topic, peer_snips)
        try:
            post_reply(db, room_id, participant=who, body=body)
            filled.append(who)
            # refresh replied set for next peer context
            replied = _replied_agents(db, room, room.current_round)
            msgs = (
                db.query(DialogueMessage)
                .filter(DialogueMessage.room_id == room.id)
                .order_by(DialogueMessage.id.asc())
                .all()
            )
        except Exception as e:
            errors.append(f"{who}:{e}")

    db.refresh(room)
    return {
        "filled": filled,
        "errors": errors,
        "round_complete": room.round_complete,
    }


def post_reply(
    db: Session,
    room_id: int,
    *,
    participant: str,
    body: str,
) -> dict[str, Any]:
    room = get_room(db, room_id)
    if room.status != "open":
        raise HTTPException(status_code=400, detail="房间已结束")
    who = (participant or "").strip().lower()
    if who not in room.participants:
        raise HTTPException(
            status_code=400,
            detail=f"{who} 不在本房 participants={room.participants}",
        )
    text = (body or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="回复不能为空")

    _maybe_complete_round(db, room)
    if room.round_complete:
        raise HTTPException(
            status_code=409,
            detail=f"第 {room.current_round} 轮已结束，请等待用户开新题或 end",
        )

    replied = _replied_agents(db, room, room.current_round)
    if who in replied:
        raise HTTPException(
            status_code=409,
            detail=f"{who} 本轮已发言，同轮最多一条",
        )

    msg = DialogueMessage(
        room_id=room.id,
        round=room.current_round,
        role="agent",
        participant=who,
        body=text,
    )
    db.add(msg)
    db.flush()
    _maybe_complete_round(db, room)
    db.commit()
    db.refresh(room)
    db.refresh(msg)
    return {
        "room": _room_brief(room),
        "message": _msg_dict(msg),
        "round_complete": room.round_complete,
    }


def poll(
    db: Session,
    room_id: int,
    *,
    participant: str,
    since_id: int = 0,
) -> dict[str, Any]:
    room = get_room(db, room_id)
    who = (participant or "").strip().lower()
    if who not in room.participants and who != "user":
        raise HTTPException(
            status_code=400,
            detail=f"未知 participant={who}，本房={room.participants}",
        )

    if room.status == "open":
        _maybe_complete_round(db, room)
        db.commit()
        db.refresh(room)

    msgs = (
        db.query(DialogueMessage)
        .filter(DialogueMessage.room_id == room.id)
        .order_by(DialogueMessage.id.asc())
        .all()
    )

    # 当前未完成轮：默认可见对方发言（方便互读）；设 true 则齐员前遮罩
    visible: list[DialogueMessage] = []
    mask_peers = bool(getattr(settings, "dialogue_mask_peers_until_complete", False))
    for m in msgs:
        if (
            mask_peers
            and room.status == "open"
            and not room.round_complete
            and m.round == room.current_round
            and m.role == "agent"
            and m.participant != who
        ):
            continue
        visible.append(m)

    new_peer = [
        _msg_dict(m)
        for m in visible
        if m.id > since_id and m.participant != who and m.role != "system"
    ]
    # system 也推给客户端（超时通知等）
    new_system = [
        _msg_dict(m)
        for m in visible
        if m.id > since_id and m.role == "system"
    ]

    replied = _replied_agents(db, room, room.current_round)
    waiting_for = sorted(set(room.participants) - replied)
    my_turn = (
        room.status == "open"
        and not room.round_complete
        and who in room.participants
        and who not in replied
    )

    # ack
    if who:
        ack = (
            db.query(DialogueAck)
            .filter(
                DialogueAck.room_id == room.id,
                DialogueAck.participant == who,
            )
            .first()
        )
        max_id = visible[-1].id if visible else 0
        if ack is None:
            ack = DialogueAck(
                room_id=room.id,
                participant=who,
                last_seen_message_id=max_id,
            )
            db.add(ack)
        else:
            ack.last_seen_message_id = max(ack.last_seen_message_id, max_id)
        db.commit()

    tail = [_msg_dict(m) for m in visible[-40:]]
    hint = ""
    if room.status != "open":
        hint = "房间已结束"
    elif my_turn:
        hint = f"轮到你发言（第 {room.current_round} 轮）→ 调用 unifier_dialogue_reply"
    elif not room.round_complete:
        hint = f"等待对方：{', '.join(waiting_for) or '—'}"
    else:
        hint = f"第 {room.current_round} 轮已齐，可互读；等待用户开新题或 end"

    return {
        "room": _room_brief(room),
        "participant": who,
        "my_turn": my_turn,
        "waiting_for": waiting_for if room.status == "open" and not room.round_complete else [],
        "round_complete": room.round_complete,
        "new_peer_messages": new_peer,
        "new_system_messages": new_system,
        "transcript_tail": tail,
        "hint": hint,
    }


def end_room(db: Session, room_id: int) -> dict[str, Any]:
    room = get_room(db, room_id)
    if room.status == "closed":
        return {"room": _room_brief(room), "message": "房间已是 closed"}
    room.status = "closed"
    room.closed_at = utcnow()
    _write_system(db, room, "房间已结束。")
    db.commit()
    db.refresh(room)
    path = write_transcript_file(db, room)
    return {
        "room": _room_brief(room),
        "message": "已结束圆桌",
        "transcript_path": str(path) if path else None,
    }


def reopen_room(db: Session, room_id: int, *, note: str = "") -> dict[str, Any]:
    """把已结束房间重新打开，并开启新一轮（便于继续历史对话框）。"""
    room = get_room(db, room_id)
    if room.status == "open":
        return {"room": _room_brief(room), "message": "房间已是 open，无需 reopen"}
    room.status = "open"
    room.closed_at = None
    room.current_round += 1
    room.round_complete = False
    room.round_opened_at = utcnow()
    body = (note or "").strip() or f"房间重新打开，进入第 {room.current_round} 轮。"
    db.add(
        DialogueMessage(
            room_id=room.id,
            round=room.current_round,
            role="user",
            participant="user",
            body=body,
        )
    )
    db.commit()
    db.refresh(room)
    return {
        "room": _room_brief(room),
        "message": f"已 reopen #{room.id}，当前第 {room.current_round} 轮",
        "hint": f"等待 {', '.join(room.participants)} 各回一条",
    }


def transcript(db: Session, room_id: int) -> dict[str, Any]:
    room = get_room(db, room_id)
    msgs = (
        db.query(DialogueMessage)
        .filter(DialogueMessage.room_id == room.id)
        .order_by(DialogueMessage.id.asc())
        .all()
    )
    return {
        "room": _room_brief(room),
        "messages": [_msg_dict(m) for m in msgs],
    }


def format_transcript_md(room: DialogueRoom, messages: list[DialogueMessage]) -> str:
    lines = [
        f"# 圆桌对话 · room-{room.id}",
        "",
        f"- project: `{room.project_key}`",
        f"- title: {room.title}",
        f"- status: {room.status}",
        f"- participants: {', '.join(room.participants)}",
        "",
        "---",
        "",
    ]
    for m in messages:
        ts = m.created_at.isoformat() if m.created_at else ""
        lines.append(f"### R{m.round} · {m.participant} ({m.role}) · {ts}")
        lines.append("")
        lines.append(m.body)
        lines.append("")
    return "\n".join(lines)


def write_transcript_file(db: Session, room: DialogueRoom) -> Path | None:
    msgs = (
        db.query(DialogueMessage)
        .filter(DialogueMessage.room_id == room.id)
        .order_by(DialogueMessage.id.asc())
        .all()
    )
    text = format_transcript_md(room, msgs)
    roots: list[Path] = []
    configured = (settings.dialogue_transcript_dir or "").strip()
    if configured:
        roots.append(Path(configured).expanduser())
    roots.append(Path.home() / ".unifier" / "dialogue")
    # 茅台试点约定目录
    if room.project_key == "maotai":
        maotai = Path(
            "/Users/mac/Desktop/工作 /软件/茅台抢单软件/data/unifier-dialogue"
        )
        if maotai.parent.exists():
            roots.insert(0, maotai)

    written: Path | None = None
    preferred: Path | None = None
    for i, root in enumerate(roots):
        try:
            root.mkdir(parents=True, exist_ok=True)
            path = root / f"room-{room.id}.md"
            path.write_text(text, encoding="utf-8")
            written = path
            if preferred is None:
                preferred = path
        except OSError:
            continue
    return preferred or written
