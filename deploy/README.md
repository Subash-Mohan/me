# Deploying `Me` to a VPS

One-page operator runbook. The architecture is:

```
Linux VPS
├── systemd
│   ├── caddy.service     ← apt-installed, listens :80/:443, auto Let's Encrypt
│   └── docker.service    ← Docker daemon
│       └── me-api        ← container, uvicorn on 127.0.0.1:8000
└── managed Postgres lives elsewhere
```

## 1. First-time VPS bootstrap (Ubuntu/Debian)

Neither Caddy nor the modern Docker Compose plugin ship in Ubuntu's default
repos; add the upstream apt sources first, then install.

```bash
sudo apt update
sudo apt install -y ca-certificates curl gnupg debian-keyring debian-archive-keyring apt-transport-https

# --- Docker official apt repo (provides docker-ce + compose v2 plugin) ---
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# --- Caddy official apt repo (Cloudsmith) ---
curl -fsSL https://dl.cloudsmith.io/public/caddy/stable/gpg.key \
  | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -fsSL https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt \
  | sudo tee /etc/apt/sources.list.d/caddy-stable.list

# --- Install everything ---
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin caddy

# Caddy log dir
sudo mkdir -p /var/log/caddy
sudo chown caddy:caddy /var/log/caddy

# App env file (mode 600, root-owned). Paste contents of deploy/env.example
# and fill in real values.
sudo mkdir -p /etc/me
sudo install -m 600 -o root -g root /dev/null /etc/me/env
sudoedit /etc/me/env
sudo stat -c '%a %U:%G %n' /etc/me/env   # verify: 600 root:root /etc/me/env

# Clone the repo. Use SSH if private; copy the VPS host key to GitHub's deploy keys first.
sudo git clone <repo-url> /srv/me
sudo chown -R "$USER":"$USER" /srv/me
```

## 2. DNS

Point an `A` record for your domain at the VPS public IP. Caddy will fetch a
Let's Encrypt cert on the first HTTPS request.

## 3. Caddy config

```bash
sudo cp /srv/me/deploy/Caddyfile /etc/caddy/Caddyfile
sudoedit /etc/caddy/Caddyfile   # replace me.example.com with the real hostname
sudo systemctl reload caddy
journalctl -u caddy --since "1m ago"   # watch the cert get issued
```

## 4. Deploy a new version

From `/srv/me` on the VPS:

```bash
git pull

# Tag the current image so you can roll back to it (see section 6).
docker tag me-api:latest me-api:$(date +%Y%m%d-%H%M) 2>/dev/null || true

make prod-build       # docker compose -f deploy/docker-compose.prod.yml build
make prod-migrate     # alembic upgrade head against the live DB
make prod-up          # docker compose -f deploy/docker-compose.prod.yml up -d
```

Migrations are forward-only. Always run them before swapping the container.

## 4a. First-deploy only — create the owner user

On a fresh database, login is impossible until the owner row exists. Run once,
after the first `make prod-migrate`:

```bash
docker compose -f deploy/docker-compose.prod.yml run --rm api python -m app.cli create-owner
# (you'll be prompted for the passphrase, no echo)
```

## 5. Logs

```bash
docker logs -f me-api                 # app
journalctl -u caddy -f                # edge (TLS, request log)
tail -f /var/log/caddy/me.access.log  # structured access log
```

The app never logs message bodies, image bytes, or passphrases — only IDs,
timestamps, and error types.

## 6. Rollback

Migrations are forward-only; rollback is image-only. The tagging in section 4
must have already run for there to be a previous image to roll back to.

```bash
docker images me-api                                         # list available tags
docker compose -f deploy/docker-compose.prod.yml down
docker tag me-api:<previous-tag> me-api:latest
docker compose -f deploy/docker-compose.prod.yml up -d
```

If a migration shipped with the bad release made an incompatible schema change,
you'll need a forward-fix migration — there's no `alembic downgrade` path in
this app.

## 7. Backups

- **Postgres:** your managed provider (Neon / Supabase / RDS) handles
  point-in-time recovery. Confirm the retention window matches your tolerance.
- **Image uploads:** persisted on the `me_images` Docker volume at
  `/var/lib/docker/volumes/me_images/_data`. Snapshot this with your VPS
  provider's volume backup, or `tar` it on a cron — out of scope for this
  phase. (Long-term plan is to move images to S3/R2.)
- **Caddy access log rotation:** Caddy does not rotate `/var/log/caddy/me.access.log`
  on its own. Add `/etc/logrotate.d/caddy-me` with a weekly rotation + `postrotate`
  `systemctl reload caddy` to keep the disk from filling on a long-running VPS.

## 8. Smoke tests after a deploy

```bash
curl -fsS -I https://<your-domain>/healthz   # 200 + strict-transport-security header
curl -fsS -I http://<your-domain>/            # 308 redirect to https
```

## 9. Common operations

| Goal | Command |
|---|---|
| Restart the API only | `docker compose -f deploy/docker-compose.prod.yml restart api` |
| Reload Caddy after a Caddyfile edit | `sudo systemctl reload caddy` |
| Open a psql shell against the managed DB | `psql "$DATABASE_URL"` (sourced from `/etc/me/env`) |
| Check container health | `docker inspect me-api --format '{{.State.Health.Status}}'` |
| Run a one-off CLI command | `docker compose -f deploy/docker-compose.prod.yml run --rm api python -m app.cli <args>` |
