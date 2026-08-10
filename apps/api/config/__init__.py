"""Project configuration package.

Importing the Celery application here guarantees that ``@shared_task`` is bound
to the configured app as soon as Django starts.
"""

from .celery import app as celery_app

__all__ = ("celery_app",)
