# Production FastAPI Deployment

A production-ready FastAPI service with PostgreSQL, Redis, NGINX reverse proxy, CI/CD via GitHub Actions, monitoring, and security hardening.

---

## Architecture

```
Internet
   │
   ▼
[Cloudflare CDN / DNS]  ← optional, bonus
   │
   ▼
[UFW Firewall]  ports 80, 443, 22 only
   │
   ▼
[NGINX :443]  ← TLS termination, rate-limiting, security headers
   │  reverse proxy
   ▼
[FastAPI :8000]  ← 2 Uvicorn workers, structured JSON logs
   │         │
   ▼         ▼
[PostgreSQL] [Redis]  ← both internal-only (no host port exposure)
```

All services run inside a single Docker bridge network (`backend`). Only NGINX exposes host ports 80 and 443.

---

## Repository Layout

```
.
├── app/
│   ├── main.py              # FastAPI application
│   ├── requirements.txt
│   └── Dockerfile           # Multi-stage, non-root user
├── nginx/
│   ├── nginx.conf           # Worker tuning, JSON logging, rate-limit zones
│   ├── conf.d/
│   │   └── api.conf         # Virtual host, SSL, proxy settings
│   └── ssl/                 # gitignored — contains certs
├── scripts/
│   ├── gen-ssl.sh           # Self-signed cert for dev/no-domain
│   ├── certbot-init.sh      # Let's Encrypt one-time issuance
│   ├── deploy.sh            # Zero-downtime rolling deploy
│   ├── backup.sh            # Nightly Postgres backup + pruning
│   └── server-hardening.sh  # UFW, fail2ban, SSH hardening (run once)
├── monitoring/
│   ├── prometheus.yml
│   └── grafana/
├── .github/workflows/
│   └── ci-cd.yml            # Build → push → deploy pipeline
├── docker-compose.yml
├── docker-compose.monitoring.yml
└── .env.example
```

---

## Quick Start (Local Dev)

```bash
# 1. Clone & configure
git clone https://github.com/your-org/prod-api && cd prod-api
cp .env.example .env
# Edit .env — change all passwords

# 2. Generate self-signed SSL
bash scripts/gen-ssl.sh

# 3. Start all services
docker compose up -d --build

# 4. Verify
curl -k https://localhost/health
# → {"status":"ok","database":"ok","redis":"ok","timestamp":"..."}
```

---

## Production VPS Deployment

### Prerequisites

- Ubuntu 22.04 / 24.04 VPS (2 vCPU, 2 GB RAM minimum)
- A domain pointing to the server's IP (or proceed with self-signed)
- GitHub repository with the code

### Step 1 — Initial Server Setup

```bash
# SSH in as root (or sudo user)
git clone https://github.com/your-org/prod-api /opt/app
cd /opt/app

# Harden the server (UFW, fail2ban, SSH hardening, Docker install)
sudo bash scripts/server-hardening.sh
```

### Step 2 — Configure Secrets

```bash
cp .env.example .env
nano .env          # Set strong passwords for POSTGRES_PASSWORD and REDIS_PASSWORD
chmod 600 .env
```

### Step 3 — SSL Certificate

**Option A — Real domain (recommended):**
```bash
# Stop any process using port 80 first
bash scripts/certbot-init.sh yourdomain.com admin@yourdomain.com

# Update nginx/conf.d/api.conf:
# ssl_certificate     /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
# ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;

# Auto-renewal cron (add via crontab -e):
# 0 3 * * * certbot renew --quiet && docker compose exec nginx nginx -s reload
```

**Option B — No domain (self-signed):**
```bash
bash scripts/gen-ssl.sh
# Browser will show a warning — expected for self-signed certs.
# For API clients, pass -k (curl) or disable SSL verification.
```

### Step 4 — Deploy

```bash
docker compose pull
docker compose up -d
docker compose ps         # all containers should be healthy
curl https://yourdomain.com/health
```

### Step 5 — Configure GitHub Actions Secrets

In your GitHub repository → Settings → Secrets → Actions:

| Secret | Value |
|--------|-------|
| `VPS_HOST` | Your server IP or hostname |
| `VPS_USER` | SSH user (e.g. `ubuntu`) |
| `VPS_SSH_KEY` | Private SSH key (contents of `~/.ssh/id_ed25519`) |
| `VPS_PORT` | SSH port (default `22`) |

After this, every push to `main` triggers: test → build → push to GHCR → SSH deploy.

---

## CI/CD Pipeline

```
push to main
     │
     ▼
 [test]  ruff lint + pytest
     │
     ▼
 [build]  docker buildx → ghcr.io/org/prod-api:sha-<commit>
     │
     ▼
 [deploy]  SSH → git pull → scripts/deploy.sh (rolling restart)
```

**Zero-downtime deploy flow (`scripts/deploy.sh`):**
1. `docker compose pull api` — fetch new image while old container runs
2. `docker compose up -d --no-deps api` — start new container
3. Poll `/health` every 5s (up to 60s) — automatic rollback on failure
4. `nginx -s reload` — graceful config reload (no dropped connections)

---

## Health Check

```
GET /health
```

Response (200 when healthy, 503 when degraded):
```json
{
  "status": "ok",
  "timestamp": "2025-05-27T10:00:00",
  "database": "ok",
  "redis": "ok"
}
```

Used by:
- Docker `HEALTHCHECK` directive (restarts container if unhealthy)
- NGINX upstream health check
- GitHub Actions deploy readiness probe

---

## Logging Strategy

| Layer | Method | Format |
|-------|--------|--------|
| FastAPI | Python `logging` middleware | JSON (timestamp, level, method, path, status, duration_ms) |
| NGINX | `log_format json_combined` | JSON (time, IP, method, URI, status, upstream_time) |
| Docker | `json-file` log driver | Rotated: 10 MB × 5 files per container |

**View logs:**
```bash
docker compose logs -f api        # FastAPI structured logs
docker compose logs -f nginx      # NGINX access + error
docker exec -it <db_ctr> psql … # Postgres query logs
```

**Centralized logging (optional):** Ship Docker `json-file` logs to Loki or CloudWatch using the Grafana Loki Docker plugin or a Fluentd sidecar.

---

## Backup & Restore

**Automated nightly backup (cron):**
```bash
# Add to crontab -e on the VPS
0 2 * * * /opt/app/scripts/backup.sh >> /var/log/app-backup.log 2>&1
```

Backups saved to `/backups/postgres/db_YYYYMMDD_HHMMSS.sql.gz`, kept for 7 days. Enable S3 upload in the script for off-site copies.

**Manual restore:**
```bash
gunzip -c /backups/postgres/db_<timestamp>.sql.gz \
  | docker compose exec -T db psql -U $POSTGRES_USER $POSTGRES_DB
```

---

## Security Measures

| Layer | Measure |
|-------|---------|
| OS | UFW — only 22/80/443 open |
| OS | fail2ban — SSH brute-force + NGINX 429 banning |
| OS | `PasswordAuthentication no` in sshd |
| OS | Unattended security upgrades |
| Docker | Non-root `appuser` in container |
| Docker | Multi-stage build (no build tools in runtime image) |
| Docker | DB/Redis have no host port exposure |
| NGINX | `server_tokens off` |
| NGINX | Security headers (X-Frame-Options, X-Content-Type, XSS protection) |
| NGINX | Rate limiting (30 req/min per IP, burst 10) |
| NGINX | TLSv1.2/1.3 only, strong cipher suite |
| App | Environment variables for all secrets (never hard-coded) |
| App | `.env` in `.gitignore` |

---

## Monitoring (Bonus)

Start the monitoring stack alongside the main services:

```bash
docker compose -f docker-compose.yml -f docker-compose.monitoring.yml up -d
```

Access Grafana via SSH tunnel:
```bash
ssh -L 3000:localhost:3000 user@yourserver
# Open http://localhost:3000  (admin / value of GRAFANA_PASSWORD)
```

Includes: Prometheus scraping FastAPI + cAdvisor (container CPU/mem/net), Grafana dashboards.

---

## Cloudflare Integration (Bonus)

1. Point your domain's nameservers to Cloudflare.
2. Add an A record pointing to your VPS IP, with **Proxy enabled** (orange cloud).
3. In Cloudflare → SSL/TLS: set mode to **Full (strict)**.
4. Enable **Bot Fight Mode** and **DDoS protection**.
5. Optionally add a **Firewall Rule** to block traffic that bypasses Cloudflare (check `CF-Connecting-IP` header).

This gives you free CDN, DDoS mitigation, and WAF in front of NGINX.

---

## Troubleshooting

```bash
# Check all container health
docker compose ps

# Inspect a failing container
docker compose logs api --tail=50

# Test DB connectivity from API container
docker compose exec api python -c "
import asyncio, asyncpg, os
async def t(): c = await asyncpg.connect(os.getenv('DATABASE_URL')); print(await c.fetchval('SELECT version()')); await c.close()
asyncio.run(t())
"

# Test Redis
docker compose exec redis redis-cli -a $REDIS_PASSWORD ping

# Validate NGINX config
docker compose exec nginx nginx -t

# Force container restart
docker compose restart api
```

---

## API Endpoints

Base URL: `https://yourdomain.com`

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | API info + links |
| GET | `/health` | Liveness + readiness (DB & Redis check) |
| GET | `/docs` | Swagger UI (interactive) |
| POST | `/tasks` | Create a task |
| GET | `/tasks` | List all tasks (optional `?done=true/false`) |
| GET | `/tasks/{id}` | Get a single task |
| PATCH | `/tasks/{id}` | Update title, description, or done status |
| DELETE | `/tasks/{id}` | Delete a task |
| GET | `/tasks/stats/summary` | Total / done / pending counts |

### Example usage

```bash
# Create a task
curl -X POST https://yourdomain.com/tasks \
  -H "Content-Type: application/json" \
  -d '{"title": "Deploy to production", "description": "Set up VPS and CI/CD"}'

# List pending tasks
curl https://yourdomain.com/tasks?done=false

# Mark task as done
curl -X PATCH https://yourdomain.com/tasks/1 \
  -H "Content-Type: application/json" \
  -d '{"done": true}'

# Stats
curl https://yourdomain.com/tasks/stats/summary
# → {"total": 5, "done": 2, "pending": 3}
```
