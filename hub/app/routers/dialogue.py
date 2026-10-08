"""圆桌对话 API：Cursor / Trae 同场互读互回。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import DialogueOpenBody, DialogueReplyBody, DialogueUserMessageBody
from app.services import dialogue as dialogue_svc

router = APIRouter(prefix="/api/v1/dialogue", tags=["dialogue"])


@router.post("/rooms")
def create_room(body: DialogueOpenBody, db: Session = Depends(get_db)):
    title = (body.title or "").strip() or body.topic.strip()[:80]
    return dialogue_svc.open_room(
        db,
        title=title,
        topic=body.topic,
        project_key=body.project_key,
        participants=body.participants,
    )


@router.get("/rooms")
def list_rooms(
    project_key: str | None = Query(None),
    open_only: bool = Query(True),
    db: Session = Depends(get_db),
):
    if open_only:
        return {"rooms": dialogue_svc.list_open_rooms(db, project_key=project_key)}
    from app.models import DialogueRoom

    q = db.query(DialogueRoom)
    if project_key:
        q = q.filter(DialogueRoom.project_key == project_key.strip())
    rooms = q.order_by(DialogueRoom.id.desc()).limit(50).all()
    return {"rooms": [dialogue_svc._room_brief(r) for r in rooms]}


@router.post("/rooms/{room_id}/user-message")
def user_message(
    room_id: int, body: DialogueUserMessageBody, db: Session = Depends(get_db)
):
    return dialogue_svc.post_user_message(
        db, room_id, body.body, auto_reply=body.auto_reply
    )


@router.post("/rooms/{room_id}/auto-fill")
def auto_fill(room_id: int, db: Session = Depends(get_db)):
    """立即为未发言的 cursor/trae 自动代言补齐本轮。"""
    return dialogue_svc.auto_fill_pending(db, room_id)


@router.get("/rooms/{room_id}/events")
async def room_events(room_id: int):
    """SSE：房间有新消息时推送到圆桌网页（即时刷新）。

    DB 读写放线程池，避免同步 SQLAlchemy 堵死 uvicorn 事件循环。
    """
    import asyncio
    import json as _json

    from fastapi.responses import StreamingResponse
    from app.database import SessionLocal

    def _snapshot() -> tuple[int, str]:
        db = SessionLocal()
        try:
            data = dialogue_svc.transcript(db, room_id)
            msgs = data.get("messages") or []
            max_id = msgs[-1]["id"] if msgs else 0
            return max_id, _json.dumps(data, ensure_ascii=False)
        finally:
            db.close()

    async def gen():
        last_id = 0
        while True:
            try:
                max_id, payload = await asyncio.to_thread(_snapshot)
                if max_id != last_id:
                    last_id = max_id
                    yield f"event: transcript\ndata: {payload}\n\n"
                else:
                    yield f"event: ping\ndata: {max_id}\n\n"
            except Exception as e:
                yield f"event: error\ndata: {_json.dumps(str(e))}\n\n"
            await asyncio.sleep(0.8)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/rooms/{room_id}/poll")
def poll_room(
    room_id: int,
    participant: str = Query(..., min_length=1),
    since_id: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return dialogue_svc.poll(
        db, room_id, participant=participant, since_id=since_id
    )


@router.post("/rooms/{room_id}/reply")
def reply_room(
    room_id: int, body: DialogueReplyBody, db: Session = Depends(get_db)
):
    return dialogue_svc.post_reply(
        db, room_id, participant=body.participant, body=body.body
    )


@router.post("/rooms/{room_id}/end")
def end_room(room_id: int, db: Session = Depends(get_db)):
    return dialogue_svc.end_room(db, room_id)


@router.post("/rooms/{room_id}/reopen")
def reopen_room(
    room_id: int,
    body: DialogueUserMessageBody | None = None,
    db: Session = Depends(get_db),
):
    """重新打开已结束房间，继续对话。可选 body 作为新一轮开题。"""
    note = body.body if body else ""
    return dialogue_svc.reopen_room(db, room_id, note=note)


@router.get("/rooms/{room_id}/transcript")
def get_transcript(room_id: int, db: Session = Depends(get_db)):
    return dialogue_svc.transcript(db, room_id)
