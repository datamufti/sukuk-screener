# Server Setup Guide

One-time setup for the Ubuntu Server 24.04 homelab node.

## 1. Install Docker Engine

```bash
# Remove old packages
sudo apt-get remove -y docker docker-engine docker.io containerd runc 2>/dev/null || true

# Add Docker's official GPG key and repo
sudo apt-get update
sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
    -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
    sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

## 2. Allow your user to run Docker without sudo

```bash
sudo usermod -aG docker talal
# Log out and back in (or run: newgrp docker)
```

Verify:

```bash
docker run --rm hello-world
```

## 3. Clone the repository

```bash
mkdir -p ~/webapps
cd ~/webapps
git clone https://github.com/datamufti/sukuk-screener.git
cd sukuk-screener
chmod +x deploy.sh
```

## 4. Initial deployment (manual)

```bash
cd ~/webapps/sukuk-screener
./deploy.sh
```

This builds the Docker image, starts the app + Caddy, and waits for the health check.

Once running, open `http://<server-lan-ip>` in your browser. Click "Refresh Data" to fetch the initial sukuk PDF.

## 5. Set up GitHub Actions secrets

In your GitHub repo, go to **Settings → Secrets and variables → Actions** and add:

| Secret name | Value |
|---|---|
| `SERVER_HOST` | Your server's LAN IP (e.g. `192.168.1.50`) |
| `SERVER_USER` | `talal` |
| `SERVER_SSH_KEY` | The **private** ed25519 key that can SSH into the server |
| `SERVER_PORT` | `22` (or custom if you changed it) |

### Generating a dedicated deploy key (recommended)

Rather than using your personal SSH key, generate a dedicated key pair for CI/CD:

```bash
# On your local machine
ssh-keygen -t ed25519 -f ~/.ssh/sukuk-deploy -C "github-actions-deploy" -N ""

# Copy the public key to the server
ssh-copy-id -i ~/.ssh/sukuk-deploy.pub talal@<server-ip>

# The PRIVATE key (~/.ssh/sukuk-deploy) goes into the GitHub secret SERVER_SSH_KEY
cat ~/.ssh/sukuk-deploy
```

## 6. Verify CI/CD

Push a small change to `main` (or trigger the workflow manually from the Actions tab). The pipeline will:

1. Run all pytest tests on GitHub's runners
2. SSH into your server
3. Pull latest code and rebuild/restart containers
4. Wait for the health check to pass

## 7. Switching to a public domain (later)

When you're ready to expose the app to the internet:

1. Point your domain's DNS (e.g. `sukuk.yourdomain.com`) to your home WAN IP
2. On OPNsense, create port-forwarding rules for ports 80 and 443 to the server's LAN IP
3. Edit `Caddyfile`: comment out the `:80` block, uncomment the domain block, replace `sukuk.example.com` with your domain
4. Redeploy: `./deploy.sh`

Caddy will automatically obtain and renew Let's Encrypt TLS certificates.

## Useful commands

```bash
# View logs
docker compose -f docker-compose.prod.yml logs -f

# View just the app logs
docker compose -f docker-compose.prod.yml logs -f sukuk-screener

# Restart everything
docker compose -f docker-compose.prod.yml restart

# Stop everything
docker compose -f docker-compose.prod.yml down

# Rebuild from scratch (preserves data volume)
docker compose -f docker-compose.prod.yml up -d --build --force-recreate

# Check container health
docker inspect --format='{{.State.Health.Status}}' sukuk-screener

# Access DuckDB data volume location
docker volume inspect sukuk-screener_sukuk-data
```

## Troubleshooting

**Port 80 already in use:**
Check if Apache or nginx is running: `sudo ss -tlnp | grep :80`. Stop/disable it or change the Caddy port.

**Docker permission denied:**
Make sure you ran `sudo usermod -aG docker talal` and logged out/in.

**Health check failing:**
The app needs outbound HTTPS to download the PDF. Check: `docker exec sukuk-screener curl -I https://www.emiratesislamic.ae` — if it times out, check firewall rules.

**DuckDB lock error on restart:**
DuckDB is single-writer. If the container didn't shut down cleanly, the lock file may be stale. Remove it: `docker compose -f docker-compose.prod.yml down && docker compose -f docker-compose.prod.yml up -d`.
