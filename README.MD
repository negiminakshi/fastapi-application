# Production FastAPI Deployment

A production-ready FastAPI service with PostgreSQL, Redis, NGINX reverse proxy, CI/CD via GitHub Actions, monitoring, and security hardening.

---
## Overview

This project demonstrates the deployment and productionization of a containerized FastAPI application using Docker and VPS infrastructure on Amazon Web Services EC2.

The stack includes:

FastAPI backend

PostgreSQL database

Redis caching

NGINX reverse proxy

Docker Compose orchestration

GitHub Actions CI/CD pipeline

Prometheus monitoring

Automated PostgreSQL backups

Basic server security hardening

----

## Architecture

```
Internet
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

All services run inside a single Docker bridge network (`backend`). Only NGINX exposes host ports 80 

---

## Quick Start (Local Dev)

```bash
# 1. Git Clone
# 2. Create Dockerfile
# 3. Start all services
docker compose up -d --build
# 4. Verify
curl -k https://localhost/health
# → {"status":"ok","database":"ok","redis":"ok","timestamp":"..."}
```

---

## Production VPS Deployment

### Prerequisites

- Ubuntu 22.04 / 24.04 ec2 (2 vCPU, 4 GB RAM minimum)
- GitHub repository with the code

### Step 1 — Initial Server Setup

```bash
# Launch ec2
# SSH in as root (or sudo user)
clone repo

# Harden the server (UFW, fail2ban, SSH hardening, Docker install)

```

### Step 2 — Dockerize application

# Create Dockerfile 
# Create Docker image (docker build -t fastapi-app .)
# Create docker-compose.yaml
-----


### Step 3 — Deploy

```bash
docker compose up -d --build
docker compose ps         # all containers should be healthy
```

### Step 4 - NGINX Reverse Proxy

NGINX is configured as a reverse proxy in front of the FastAPI application.

# sudo /etc/nginx/sites-enabled/nginx-conf
# sudo nginx -t          # test config
# sudo systemctl reload nginx

## Responsibilities handled by NGINX:

# Reverse proxy routing
# HTTP request forwarding
# Future SSL termination support

## Health Check
----
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
** check http://15.207.100.93
http://15.207.100.93/docs **

---
### Step 5 — Configure GitHub Actions Secrets

In your GitHub repository → Settings → Secrets → Actions:

| Secret | Value |
|--------|-------|
| `VPS_HOST` | Your server IP or hostname |
| `VPS_SSH_KEY` | Private SSH key (contents of `~/.ssh/id_ed25519`) |


After this, every push to `main` triggers: test → build → push to dockerhub → SSH deploy.

---

## CI/CD Pipeline

```
push to main
     │
     ▼
 [test] 
     │
     ▼
 [build]  
     │
     ▼
 [deploy]   
---

## SSL SETUP APPROCH

SSL certificates can be generated and managed using:

Certbot
Let's Encrypt
NGINX SSL termination


sudo apt install certbot python3-certbot-nginx -y
sudo certbot --nginx -d example.com
sudo certbot renew --dry-run

----

## Logging Strategy
**View logs:**
```bash
docker compose logs -f api        # FastAPI structured logs
docker compose logs -f nginx      # NGINX access + error
docker exec -it <db_ctr> psql … # Postgres query logs
```

## Monitoring Strategy

Prometheus is configured to scrape FastAPI metrics every 15 seconds.
http://15.207.100.93:9090

Monitoring includes:

API metrics
Request latency
Container uptime
Health monitoring
---

## Backup & Restore

Database backups are automated using:

cron jobs
PostgreSQL pg_dump

Backups are timestamped and stored locally.
chmod +x scripts/backup.sh
mkdir -p ~/backups

# Add to crontab — runs daily at 2am
crontab -e
# add: 0 2 * * * /home/ubuntu/devops-assignment/scripts/backup.sh

Future improvements:

S3 backup storage
Backup retention policies
---
## FIREWALL
---
sudo ufw allow 22
sudo ufw allow 80
sudo ufw allow 443
sudo ufw enable
---

## Security Measures

| Layer | Measure |
|-------|---------|
| OS | UFW — only 22/80/443 open |
| OS | fail2ban — SSH brute-force + NGINX 429 banning |
| OS | `PasswordAuthentication no` in sshd |
| Docker | Non-root `appuser` in container |
| Docker | DB/Redis have no host port exposure |
| NGINX | `server_tokens off` |
| NGINX | Security headers (X-Frame-Options, X-Content-Type, XSS protection) |
| NGINX | Rate limiting (30 req/min per IP, burst 10) |
| App | Environment variables for all secrets (never hard-coded) |
| App | `.env` in `.gitignore` |

---

## Cloudflare Integration (FUTURE DEVELOPMENT)

1. Point your domain's nameservers to Cloudflare.
2. Add an A record pointing to your VPS IP, with **Proxy enabled** (orange cloud).
3. In Cloudflare → SSL/TLS: set mode to **Full (strict)**.
4. Enable **Bot Fight Mode** and **DDoS protection**.

Cloudflare can be integrated for:

DNS management
CDN caching
SSL termination
DDoS protection

* A production domain is required for integration. *

This gives you free CDN, DDoS mitigation, and WAF in front of NGINX.

---
## Zero-Downtime Deployment Strategy

New containers are started alongside the old ones.
NGINX continues serving traffic to the old container.
Once the new container passes the /health check, NGINX reloads (graceful — no dropped connections).
Old container is removed only after the new one is confirmed healthy.
Result: zero dropped requests during deployment

## Troubleshooting

```bash
# Check all container health
docker compose ps

# Inspect a failing container
docker compose logs api --tail=50

# Test DB connectivity from API container
docker exec -it api bash

# Validate NGINX config
 nginx -t

---

### AI / LLM Ready Endpoint

# The application includes an AI-ready endpoint:

/ai

This endpoint is designed for future integration with:
 * check http://15.207.100.93:8000/ai *

### Verify all endpoints
Endpoint                         Description            
# http://15.207.100.93              root 
# http://15.207.100.93//health      Health check (DB + Redis status)
# http://15.207.100.93//docs        Swagger UI 
# http://15.207.100.93/metrics      Prometheus metrics 
# http://15.207.100.93:9090        Prometheus dashboard



