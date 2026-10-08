"""定时工作流调度（内置 APScheduler）。"""
from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.database import SessionLocal
from app.models import Workflow
from app.services.workflow_engine import run_workflow_by_id, sync_workflow_meta

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def _parse_cron(cron: str) -> dict[str, str]:
    parts = cron.strip().split()
    if len(parts) != 5:
        raise ValueError("cron 须为 5 段：分 时 日 月 周")
    keys = ["minute", "hour", "day", "month", "day_of_week"]
    return dict(zip(keys, parts))


def _run_scheduled(workflow_id: int) -> None:
    run_workflow_by_id(
        workflow_id,
        event_type="schedule.tick",
        event_data={},
        trigger="schedule",
    )


def reload_schedules() -> None:
    global _scheduler
    if _scheduler is None:
        return
    _scheduler.remove_all_jobs()
    db = SessionLocal()
    try:
        workflows = (
            db.query(Workflow)
            .filter(Workflow.active.is_(True), Workflow.trigger_kind == "schedule")
            .all()
        )
        for wf in workflows:
            cron = wf.schedule_cron
            if not cron and wf.graph_json:
                sync_workflow_meta(wf)
                cron = wf.schedule_cron
            if not cron:
                continue
            try:
                trigger = CronTrigger(**_parse_cron(cron))
            except Exception as exc:
                logger.warning("workflow %s cron invalid: %s", wf.id, exc)
                continue
            _scheduler.add_job(
                _run_scheduled,
                trigger=trigger,
                id=f"workflow-{wf.id}",
                args=[wf.id],
                replace_existing=True,
            )
            logger.info("scheduled workflow #%s cron=%s", wf.id, cron)
        db.commit()
    finally:
        db.close()


def start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
    _scheduler.start()
    reload_schedules()
    logger.info("workflow scheduler started")


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
