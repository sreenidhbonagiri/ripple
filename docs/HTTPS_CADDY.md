# HTTPS with Caddy (Vultr VM)

Public edge: **Caddy** on the host (`:80` / `:443`) → Docker frontend on **`127.0.0.1:8080`**.  
Backend remains **unpublished** (`8000` on the Compose network only).

Domains: `followtheripple.us` (canonical), `www.followtheripple.us` → permanent redirect to canonical (path + query preserved).

Local development is unchanged: plain `docker compose up` still publishes `0.0.0.0:8080`.

## Prerequisites

1. **DNS** (required for Let’s Encrypt)
   - `followtheripple.us` **A** → VM public IPv4
   - `www.followtheripple.us` **A** (or CNAME → apex) → same host
   - Confirm with: `dig +short followtheripple.us A` and `dig +short www.followtheripple.us A`
2. Host packages: Docker Engine + Compose plugin (already in use at `/opt/ripple`)
3. Project `.env` on the VM (`chmod 600`) with runtime secrets — never commit
4. Optional CORS (same-origin via Caddy is enough for browsers; set if needed):
   - `RIPPLE_CORS_ORIGINS=https://followtheripple.us,https://www.followtheripple.us`

## Vultr Firewall Group (dashboard)

UFW on the VM is not enough if a **Vultr Firewall** is attached to the instance.

1. Vultr → **Products** → **Firewall**
2. Open the firewall group linked to this instance (or create one and attach it)
3. **Inbound** rules (IPv4):
   - TCP **22** — SSH (keep existing)
   - TCP **80** — HTTP (ACME + redirect)
   - TCP **443** — HTTPS
4. Do **not** add public TCP **8080** once Caddy is live (frontend is loopback-only)
5. Do **not** open TCP **8000** (backend stays internal)
6. Save; wait for the group to show as applied on the instance

## Host UFW (do not disable)

```bash
sudo ufw status verbose
sudo ufw allow 80/tcp comment 'Caddy HTTP/ACME'
sudo ufw allow 443/tcp comment 'Caddy HTTPS'
sudo ufw status verbose   # SSH 22 must still be ALLOW
```

## Install Caddy (official Ubuntu apt repo)

From [Caddy install docs](https://caddyserver.com/docs/install):

```bash
sudo apt install --yes debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
  | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
  | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo chmod o+r /usr/share/keyrings/caddy-stable-archive-keyring.gpg
sudo chmod o+r /etc/apt/sources.list.d/caddy-stable.list
sudo apt update
sudo apt install --yes caddy
caddy version
sudo systemctl enable --now caddy
```

## Deploy Compose overlay + Caddyfile

Repo files:

- `deploy/docker-compose.caddy.yml` — bind frontend to `127.0.0.1:8080`
- `deploy/Caddyfile` — TLS + reverse proxy + www redirect

On the VM (`/opt/ripple`):

```bash
cd /opt/ripple
# Ensure deploy/ files match the repo (git pull or copy)

# Validate Caddy config before replacing the live file
sudo caddy validate --config deploy/Caddyfile
sudo cp deploy/Caddyfile /etc/caddy/Caddyfile
sudo caddy validate --config /etc/caddy/Caddyfile

# Bind Docker :8080 to loopback only (local compose.yml unchanged)
docker compose -f docker-compose.yml -f deploy/docker-compose.caddy.yml up -d

# Confirm publish
ss -tlnp | grep -E ':8080|:80|:443'
# Expect: 127.0.0.1:8080 (docker), 0.0.0.0:80 and :443 (caddy)

sudo systemctl reload caddy
# If Caddy was still on the default site: sudo systemctl restart caddy
```

## Verification

```bash
# Loopback app (always)
curl -fsS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8080/api/health
curl -fsS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8080/api/ready

# After DNS + certs
curl -fsSI https://followtheripple.us/ | head
curl -fsS https://followtheripple.us/api/health
curl -fsS https://followtheripple.us/api/ready
curl -fsSI http://followtheripple.us/ | head          # → HTTPS redirect
curl -fsSI https://www.followtheripple.us/path?x=1 | head  # → https://followtheripple.us/path?x=1
sudo journalctl -u caddy -n 50 --no-pager
```

Certificate material lives under `/var/lib/caddy/` (managed by the `caddy` user). Do not copy private keys into the repo.

## Rollback

**A. Restore public `:8080` without Caddy (previous working shape)**

```bash
cd /opt/ripple
docker compose -f docker-compose.yml up -d
# Frontend listens on 0.0.0.0:8080 again; backend still unpublished
sudo systemctl stop caddy    # optional
# UFW: leave 22 open; you may delete 80/443 rules if unused
```

**B. Keep Caddy but undo only the loopback bind**

```bash
cd /opt/ripple
docker compose -f docker-compose.yml up -d
```

**C. Restore previous Caddyfile**

```bash
sudo cp /etc/caddy/Caddyfile.bak /etc/caddy/Caddyfile   # if you saved a bak
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

## On-host Compose habit

After enabling the overlay, always include both files (or set `COMPOSE_FILE`):

```bash
cd /opt/ripple
export COMPOSE_FILE=docker-compose.yml:deploy/docker-compose.caddy.yml
docker compose ps
docker compose up -d
```

A plain `docker compose up -d` (base file only) republishes `0.0.0.0:8080` and bypasses Caddy.

## Temporary access before DNS/certs

```bash
ssh -i ~/.ssh/id_rsa -L 8080:127.0.0.1:8080 root@<vm-ip>
# then open http://127.0.0.1:8080/
```

## Notes

- ACME **HTTP-01** needs public TCP **80** to the VM (UFW + Vultr firewall).
- Docker’s iptables integration can expose published container ports even when UFW denies them; binding to `127.0.0.1` avoids that class of leak for `:8080`.
- No database imports or analytical changes are required for TLS.

## Status snapshot (2026-10-24, VM `108.61.155.246`)

| Check | Result |
|-------|--------|
| DNS `followtheripple.us` / `www` A | **NXDOMAIN** (blocker for Let’s Encrypt) |
| UFW | active; **22 / 80 / 443** ALLOW; not disabled |
| Public TCP 80 / 443 from Internet | **open** (no Vultr Firewall change required at check time) |
| Public TCP 8080 | **closed** (loopback bind) |
| Docker frontend | `127.0.0.1:8080->80` healthy |
| Docker backend | `8000/tcp` internal only |
| Caddy | v2.11.7 active; Caddyfile validated before reload |
| `http://127.0.0.1:8080/api/health` | 200 |
| `http://127.0.0.1:8080/api/ready` | 200 `database=ok` |
| HTTP→HTTPS (Host: followtheripple.us) | **308** → `https://followtheripple.us/` |
| Public HTTPS certs | **pending** until DNS A records exist |

After DNS is published, Caddy retries ACME automatically. Re-check:

```bash
curl -fsSI https://followtheripple.us/
curl -fsS https://followtheripple.us/api/health
curl -fsS https://followtheripple.us/api/ready
```
