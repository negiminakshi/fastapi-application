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
# SSH in as root (or sudo user)
clone repo

# Harden the server (UFW, fail2ban, SSH hardening, Docker install)

```

### Step 2 — Dockerize application

Create Dockerfile
create docker-compose.yaml
-----


### Step 4 — Deploy

```bash
docker compose pull
docker compose up -d
docker compose ps         # all containers should be healthy
```

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

## NGINX Reverse Proxy

NGINX is configured as a reverse proxy in front of the FastAPI application.

Responsibilities handled by NGINX:

Reverse proxy routing
HTTP request forwarding
Future SSL termination support
Load balancing readiness
Centralized traffic management

Example request flow:

Client Request
      ↓
NGINX Reverse Proxy
      ↓
FastAPI Application

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
** check http://15.207.110.207
http://15.207.110.207/docs **

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
http://15.207.110.207:9090

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

Future improvements:

S3 backup storage
Backup retention policies
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

A production SSL setup can be configured using:

NGINX
Let's Encrypt
Certbot

* Since no production domain is configured, HTTPS setup is documented but not enabled. *

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

##** AI / LLM Ready Endpoint**

The application includes an AI-ready endpoint:

/ai

This endpoint is designed for future integration with:

OpenAI APIs
HuggingFace models
LLM inference services
 * check http://15.207.110.207:8000/ai *
