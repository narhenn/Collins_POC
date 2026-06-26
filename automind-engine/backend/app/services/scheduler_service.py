"""Dynamic schedule management using RedBeat (Celery Beat backed by Redis)."""

import logging

from celery.schedules import crontab
from redbeat import RedBeatSchedulerEntry

from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def parse_cron(cron_str: str) -> crontab:
    """Parse '0 9 * * 1-5' into a celery crontab object."""
    parts = cron_str.strip().split()
    if len(parts) != 5:
        raise ValueError(f"Invalid cron expression (expected 5 parts): {cron_str}")
    return crontab(
        minute=parts[0],
        hour=parts[1],
        day_of_month=parts[2],
        month_of_year=parts[3],
        day_of_week=parts[4],
    )


def schedule_agent(agent_id: str, cron_str: str, timezone: str = "UTC") -> None:
    """Create or update a RedBeat scheduled task for an agent."""
    # Remove existing entry first (if any) to avoid duplicates
    unschedule_agent(agent_id)

    entry = RedBeatSchedulerEntry(
        name=f"agent:{agent_id}",
        task="execute_workflow_scheduled",
        schedule=parse_cron(cron_str),
        args=[agent_id],
        app=celery_app,
    )
    entry.save()
    logger.info("Scheduled agent %s with cron '%s' tz=%s", agent_id, cron_str, timezone)


def unschedule_agent(agent_id: str) -> None:
    """Remove a scheduled task for an agent. No-op if it doesn't exist."""
    try:
        entry = RedBeatSchedulerEntry.from_key(
            f"redbeat:agent:{agent_id}", app=celery_app
        )
        entry.delete()
        logger.info("Unscheduled agent %s", agent_id)
    except Exception:
        pass  # Entry doesn't exist, that's fine
