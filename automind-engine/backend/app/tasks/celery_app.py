from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "automind",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    include=["app.tasks.workflow_tasks"],
    # RedBeat: dynamic Celery Beat schedules stored in Redis
    beat_scheduler="redbeat.RedBeatScheduler",
    redbeat_redis_url=settings.REDIS_URL,
)
