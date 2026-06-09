from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import HUB_ROOT, settings


class Base(DeclarativeBase):
    pass


def _db_path() -> Path:
    p = Path(settings.unifier_db)
    if not p.is_absolute():
        p = HUB_ROOT / p
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


engine = create_engine(
    f"sqlite:///{_db_path()}",
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from app import models  # noqa: F401
    from app.models import Device
    from app.services.agent_slots import sync_slots_from_device

    Base.metadata.create_all(bind=engine)
    _migrate_sqlite()

    db = SessionLocal()
    try:
        for device in db.query(Device).all():
            sync_slots_from_device(db, device)
    finally:
        db.close()


def _migrate_sqlite() -> None:
    """轻量迁移：为已有 SQLite 库补列。"""
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    if "tasks" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("tasks")}
    with engine.begin() as conn:
        if "feishu_chat_id" not in cols:
            conn.execute(text("ALTER TABLE tasks ADD COLUMN feishu_chat_id VARCHAR(128)"))
        if "feishu_message_id" not in cols:
            conn.execute(
                text("ALTER TABLE tasks ADD COLUMN feishu_message_id VARCHAR(128)")
            )
