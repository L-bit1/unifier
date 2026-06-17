from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services.soul_bridge import aether_task, soul_chat, stack_health

router = APIRouter(prefix="/soul", tags=["soul"])


class SoulChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    domain: str = "general"


class AetherTaskRequest(BaseModel):
    message: str
    web_goal: str | None = None
    session_id: str | None = None


@router.get("/health")
async def soul_stack_health() -> dict:
    return await stack_health()


@router.post("/chat")
async def hub_soul_chat(req: SoulChatRequest) -> dict:
    return await soul_chat(
        message=req.message,
        session_id=req.session_id,
        domain=req.domain,
    )


@router.post("/aether/task")
async def hub_aether_task(req: AetherTaskRequest) -> dict:
    return await aether_task(
        message=req.message,
        web_goal=req.web_goal,
        session_id=req.session_id,
    )
