# Deployment

Target: a single Hetzner VPS running Docker, with an external object store and
SMTP provider. This document describes the intended procedure.

> **Not yet exercised.** Everything here is written and internally consistent,
> but no deployment has been run against a real host. Treat the first deploy as
> a rehearsal, and complete the restore drill in §6 before taking real orders.

## 1. Prerequisites

- A host with Docker and Docker Compose, 4 GB RAM minimum for the full stack.
- DNS A records for the storefront and API hostnames.
- An S3-compatible bucket (Cloudflare R2 or equivalent) with credentials.
- An SMTP provider with a verified sending domain (SPF, DKIM, DMARC).
- Payment provider credentials and a webhook secret.

## 2. Configuration

```bash
cp .env.example .env
```

Every value below must be set before the first boot; the production settings
module raises rather than starting with an insecure default.

| Variable | Notes |
| -------- | ----- |
| `DJANGO_SECRET_KEY` | 50+ random characters. Rotating it invalidates sessions. |
| `DJANGO_DEBUG` | `false`. Non-negotiable. |
| `DJANGO_ALLOWED_HOSTS` | Both hostnames. |
| `DATABASE_URL`, `POSTGRES_*` | Strong password; never the example one. |
| `REDIS_URL`, `CELERY_*` | |
| `S3_*` | Bucket must **not** be publicly listable. |
| `SMTP_*` | |
| `PAYMENT_PROVIDER` | A real PSP. `sandbox` moves no money and warns. |
| `PAYMENT_WEBHOOK_SECRET` | Without it the webhook endpoint refuses everything. |
| `CORS_ALLOWED_ORIGINS`, `CSRF_TRUSTED_ORIGINS` | Exact origins, no wildcards. |
| `MURASFOOD_WEB_DOMAIN`, `MURASFOOD_API_DOMAIN`, `MURASFOOD_ACME_EMAIL` | Used by Caddy for automatic TLS. |

## 3. First deploy

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

```bash
docker compose -f docker-compose.prod.yml exec api python manage.py migrate
```

```bash
docker compose -f docker-compose.prod.yml exec api python manage.py createsuperuser
```

Then create the merchant. `bootstrap_tenant` provisions roles, permissions,
units, delivery settings, the chart of accounts and the email templates:

```bash
docker compose -f docker-compose.prod.yml exec api python manage.py shell
```

```python
from apps.tenants.services import create_tenant
from apps.tenants.bootstrap import bootstrap_tenant

tenant = create_tenant(
    legal_name="…", trade_name="…", support_email="…", slug="…",
)
bootstrap_tenant(tenant)
```

**Do not run `seed_demo` in production.** It refuses to run with `DEBUG=False`
unless forced, and its data is fictitious.

## 4. What the production stack differs on

- No bind mounts and no development servers. Gunicorn serves the API; Nitro
  serves the web app from its build output.
- Containers run as non-root with health checks and `restart: unless-stopped`.
- Database ports are not published to the host.
- HSTS, secure cookies, `X-Content-Type-Options` and a strict referrer policy
  are on; `SECURE_SSL_REDIRECT` assumes the proxy sets `X-Forwarded-Proto`.
- Logs are JSON on stdout for a shipper to collect.

## 5. Health and monitoring

| Endpoint         | Checks                        | Use for               |
| ---------------- | ----------------------------- | --------------------- |
| `/health/live/`  | Process is up. Nothing else.  | Restart policy        |
| `/health/ready/` | Database and cache reachable  | Load balancer, deploys |

Liveness deliberately touches no dependency: a probe that checks the database
restarts healthy containers during a database blip and turns a small outage into
a large one.

## 6. Backups — and the drill that makes them real

Schedule the dump (host crontab):

```bash
0 3 * * * cd /opt/murasfood && bash infrastructure/scripts/backup-db.sh
```

Set `BACKUP_S3_TARGET` so copies leave the machine. A backup stored on the same
host as the database does not survive the failure it exists for.

**A backup is not implemented until a restore has been tested.** Before going
live, on a staging host:

```bash
bash infrastructure/scripts/restore-db.sh infrastructure/backups/<dump>.dump.gz
```

```bash
docker compose -f docker-compose.prod.yml exec api python manage.py migrate --check
```

Record how long it took. That number is the recovery time objective, and it is
the only honest one.

## 7. Updating

```bash
git pull && docker compose -f docker-compose.prod.yml up -d --build
```

```bash
docker compose -f docker-compose.prod.yml exec api python manage.py migrate
```

Take a backup first when a release contains a destructive migration. Migrations
run against a live database; additive changes are safe, column drops are not and
should be split across two releases.

## 8. Production readiness checklist

- [ ] HTTPS with a valid certificate on both hostnames
- [ ] `DEBUG=false`, real `DJANGO_SECRET_KEY`, explicit `ALLOWED_HOSTS`
- [ ] Database password changed from the example
- [ ] Automated backups running **and a restore drill completed**
- [ ] Redis reachable; worker and beat both healthy
- [ ] SMTP verified; a real transactional email received
- [ ] Real payment credentials; `PAYMENT_PROVIDER` is not `sandbox`
- [ ] Webhook URL registered with the PSP and signature validation confirmed
- [ ] Object storage configured and the bucket not publicly listable
- [ ] CORS and CSRF origins are exact
- [ ] Rate limiting reviewed for the expected traffic
- [ ] Log shipping and error tracking in place
- [ ] Privacy policy, terms and account deletion configured for this merchant
- [ ] Tenant isolation, payment and inventory tests green against production settings
- [ ] `seed_demo` never run on this database
