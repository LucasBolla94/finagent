"""
Celery application — background task queue.

Workers run independently from the FastAPI server.
They handle: alert checks, notifications, weekly summaries,
embedding indexing, promise follow-ups.

Beat schedule (cron-like):
- Every hour:    check alerts for all active tenants
- Every hour:    check pending agent promises
- Daily 08:00:   send "good morning" summaries (optional, per tenant setting)
- Monday 09:00:  weekly financial summary
- 1st of month:  monthly report
"""
import os
from celery import Celery
from celery.schedules import crontab

# Celery app
celery = Celery("finagent")

celery.conf.update(
    broker_url=os.environ.get("CELERY_BROKER_URL", "redis://redis:6379/1"),
    result_backend=os.environ.get("CELERY_RESULT_BACKEND", "redis://redis:6379/2"),
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="America/Sao_Paulo",
    enable_utc=True,
    worker_prefetch_multiplier=1,       # Don't pre-fetch tasks (memory friendly)
    task_acks_late=True,                # Ack after task completes (retry-safe)
    worker_max_tasks_per_child=100,     # Restart worker after 100 tasks (memory leak prevention)
    task_soft_time_limit=300,           # 5 min soft limit
    task_time_limit=600,                # 10 min hard limit
    # Beat schedule
    beat_schedule={
        "check-alerts-hourly": {
            "task": "app.workers.alert_checker.check_all_alerts",
            "schedule": crontab(minute=0),  # Every hour at :00
        },
        "check-promises-hourly": {
            "task": "app.workers.promise_checker.check_all_promises",
            "schedule": crontab(minute=30),  # Every hour at :30
        },
        "weekly-summary-monday": {
            "task": "app.workers.weekly_summary.send_weekly_summaries",
            "schedule": crontab(hour=9, minute=0, day_of_week=1),  # Monday 9am
        },
        "monthly-report-first": {
            "task": "app.workers.monthly_report.send_monthly_reports",
            "schedule": crontab(hour=8, minute=0, day_of_month=1),  # 1st of month 8am
        },
    },
)

# Auto-discover tasks from workers package
celery.autodiscover_tasks([
    "app.workers.alert_checker",
    "app.workers.notification_worker",
    "app.workers.embedding_indexer",
    "app.workers.weekly_summary",
    "app.workers.promise_checker",
    "app.workers.monthly_report",
])
