"""导入 hub/workflows/presets 预置工作流。"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import HUB_ROOT
from app.models import Workflow
from app.services.workflow_engine import sync_workflow_meta
from app.services.workflow_scheduler import reload_schedules

logger = logging.getLogger(__name__)

PRESETS_DIR = HUB_ROOT / "workflows" / "presets"


def import_presets(db: Session, *, activate: bool = False) -> list[Workflow]:
    imported: list[Workflow] = []
    if not PRESETS_DIR.is_dir():
        return imported

    for path in sorted(PRESETS_DIR.glob("*.json")):
        preset_key = path.stem
        existing = (
            db.query(Workflow).filter(Workflow.preset_key == preset_key).first()
        )
        if existing:
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("skip preset %s: %s", path, exc)
            continue

        wf = Workflow(
            name=data.get("name") or preset_key,
            description=data.get("description"),
            graph_json=json.dumps(data["graph"], ensure_ascii=False),
            active=bool(data.get("active", activate)),
            preset_key=preset_key,
        )
        sync_workflow_meta(wf)
        db.add(wf)
        imported.append(wf)

    if imported:
        db.commit()
        reload_schedules()
        logger.info("imported %s workflow presets", len(imported))
    return imported
