from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import HUB_ROOT, settings
from app.database import SessionLocal, init_db
from app.middleware_access import AccessTokenMiddleware
from app.routers import (
    agent_slots,
    audit,
    automation,
    devices,
    dialogue,
    executors,
    feishu,
    mobile,
    orchestrate,
    projects,
    soul,
    tasks,
    workflows,
    feishu_oa,
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    if settings.workflows_enabled:
        from app.services.workflow_presets import import_presets
        from app.services.workflow_scheduler import start_scheduler

        db = SessionLocal()
        try:
            import_presets(db)
        finally:
            db.close()
        start_scheduler()
    yield
    if settings.workflows_enabled:
        from app.services.workflow_scheduler import stop_scheduler

        stop_scheduler()


app = FastAPI(
    title="联合器 Hub",
    description="协作控制面：项目、任务、多 Agent 审查、设备注册、圆桌对话",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(AccessTokenMiddleware)

app.include_router(workflows.router)
app.include_router(automation.router)
app.include_router(audit.router)
app.include_router(executors.router)
app.include_router(devices.router)
app.include_router(agent_slots.router)
app.include_router(projects.router)
app.include_router(tasks.router)
app.include_router(orchestrate.router)
app.include_router(dialogue.router)
app.include_router(feishu.router)
app.include_router(feishu_oa.router)
app.include_router(mobile.router)
app.include_router(soul.router)

static_dir = HUB_ROOT / "static"
if static_dir.is_dir():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/health")
def health():
    return {
        "ok": True,
        "service": "unifier-hub",
        "soul_api": "/soul/health",
        "workflow_editor": "/workflows/editor",
        "workflows_api": "/api/v1/workflows",
        "audit_console": "/audit",
    }


@app.get("/")
def root():
    return {
        "service": "unifier-hub",
        "docs": "/docs",
        "health": "/health",
        "workflow_editor": "/workflows/editor",
        "dialogue": "/dialogue",
        "audit": "/audit",
        "audit_api": "/api/v1/audit/manifests",
    }


@app.get("/audit")
def audit_ui():
    """AI 编程审计黑匣子：意图时间线 + 双 Agent manifest diff。"""
    from fastapi.responses import FileResponse

    path = HUB_ROOT / "static" / "audit.html"
    return FileResponse(path)


@app.get("/dialogue")
def dialogue_ui():
    """圆桌可视化对话框（Cursor / Trae 同场 transcript）。"""
    from fastapi.responses import FileResponse

    path = HUB_ROOT / "static" / "dialogue.html"
    return FileResponse(path)
