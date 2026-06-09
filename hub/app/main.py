from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db
from app.routers import agent_slots, devices, feishu, orchestrate, projects, tasks


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="联合器 Hub",
    description="协作控制面：项目、任务、多 Agent 审查、设备注册",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(devices.router)
app.include_router(agent_slots.router)
app.include_router(projects.router)
app.include_router(tasks.router)
app.include_router(orchestrate.router)
app.include_router(feishu.router)


@app.get("/health")
def health():
    return {"ok": True, "service": "unifier-hub"}


@app.get("/")
def root():
    return {
        "service": "unifier-hub",
        "docs": "/docs",
        "health": "/health",
    }
