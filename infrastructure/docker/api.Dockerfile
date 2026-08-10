# =============================================================================
# MurasFood API image — Django + DRF + Celery.
# Multi-stage: `development` keeps dev tooling, `production` is slim and
# runs as a non-root user.
# =============================================================================

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# libpq for psycopg, build tools only where needed (dropped in the final stage).
RUN apt-get update \
    && apt-get install --no-install-recommends -y \
        build-essential \
        libpq-dev \
        curl \
    && rm -rf /var/lib/apt/lists/*

COPY apps/api/requirements /app/requirements


# --- development -------------------------------------------------------------
FROM base AS development

RUN pip install -r requirements/development.txt

COPY apps/api /app

EXPOSE 8000
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]


# --- production --------------------------------------------------------------
FROM base AS production

RUN pip install -r requirements/production.txt

COPY apps/api /app

# Collect static assets for the Django admin / DRF browsable API.
ENV DJANGO_SETTINGS_MODULE=config.settings.production \
    DJANGO_SECRET_KEY=build-time-placeholder \
    DJANGO_COLLECTSTATIC=1
RUN python manage.py collectstatic --noinput --clear || true
ENV DJANGO_COLLECTSTATIC=

# Least privilege: the app never needs to write to its own source tree.
RUN groupadd --system --gid 1001 murasfood \
    && useradd --system --uid 1001 --gid murasfood murasfood \
    && chown -R murasfood:murasfood /app
USER murasfood

EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
