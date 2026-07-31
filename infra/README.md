# Covenant Study — Infrastructure

This directory contains all deployment and infrastructure-as-code for Covenant Study on Wittycomp Lab.

## Files

| File | Purpose |
|------|---------|
| `caddy.conf` | Caddy site block for `study.wittycomp.com` — paste into the lab Caddyfile |
| `dns.md` | DNS records required (Technitium internal + Cloudflare external + tunnel ingress) |

## Lab Deployment (wn-bible-01)

The canonical lab deployment uses the compose.yaml at the repo root and runs on the `witty_vlan30`
macvlan network. The image is built and published to GHCR, then pulled by the lab host.

### Deploy a new build

```bash
# 1. From the repo root — build and push the image
docker compose build
docker push ghcr.io/bearboss/wn-bible-01:latest

# 2. On wn-docker-01 (wittycomp-lab) — pull and restart
cd /home/bearboss/wittycomp-lab/apps/wn-bible-01
docker compose pull
docker compose up -d
```

### First-time setup

```bash
# DNS: Technitium (internal)
# Add A record: study.wittycomp.com → 10.10.30.246

# DNS: Cloudflare (external)
# Add CNAME: study → <CF tunnel CNAME>

# Caddy: add site block from infra/caddy.conf to the lab Caddyfile

# Tunnel: add ingress rule from infra/dns.md to wn-tunnel-01/config.yaml
```

## Standalone Deployment (any Docker host)

```bash
cp .env.example .env
# Edit .env — set ADMIN_PASSWORD to something strong
docker compose -f compose.standalone.yml up -d
# Access at http://localhost:8000
```

## Port and Memory Budget

| Resource | Value |
|----------|-------|
| Port | 8000 (internal) → Caddy (443) |
| Memory limit | 256MB (lab compose) / 1GB (standalone) |
| Volumes | `bible-notes` (legacy migration), `bible-userdata` (accounts, bookmarks, notes, highlights) |

## Upgrading Gunicorn (future)

Currently using plain Uvicorn. When concurrent load grows, upgrade to:

```dockerfile
RUN pip install gunicorn
CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "-w", "2", "app:app", "--bind", "0.0.0.0:8000"]
```

Two workers is sufficient for a personal/small-team deployment. Each worker runs its own
async event loop — no shared memory, so SQLite WAL mode is required if enabling.
