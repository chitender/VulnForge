from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "patchpilot",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    broker_transport_options={"visibility_timeout": 1020},  # TASK_TIME_LIMIT + 60s
    worker_prefetch_multiplier=1,
    task_soft_time_limit=900,
    task_time_limit=960,
    worker_max_tasks_per_child=50,
)
