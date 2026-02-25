from celery import Celery

from app.config import settings

celery_app = Celery(
    "rag",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
)
# Register tasks so the worker knows about them
import app.tasks.ingest  # noqa: F401