# mimir-minecraft

Minecraft Java server (Fabric) for ~10 players running in Docker, with a live world map (Bluemap), a status page, a lightweight stats API, and automatic HTTPS via Caddy.

## Stack

| Container | Image | Purpose |
|---|---|---|
| `caddy`   | `caddy:2-alpine`                 | Reverse proxy, automatic HTTPS (local CA) |
| `minecraft` | `itzg/minecraft-server` (Fabric) | Game server + Bluemap mod |
| `status`    | `nginx:alpine`                   | Public status page + Bluemap proxy |
| `stats`     | `python:3-alpine`                | CPU / memory / temp API consumed by the status page |

## Ports

| Port    | Protocol | Purpose                     |
|---------|----------|-----------------------------|
| `25565` | TCP      | Minecraft game — forward on router |
| `80`    | TCP      | HTTP → HTTPS redirect        |
| `443`   | TCP/UDP  | HTTPS (status page, Bluemap, CA) |

## Prerequisites

- Docker + Docker Compose v2 on the host
- Port `25565` (TCP) and `443` (TCP/UDP) forwarded on your router to the host
- DNS A records for `${MINECRAFT_DOMAIN}` and `ca.${MINECRAFT_DOMAIN}` pointing to the public IP

## Deploy

```bash
git clone <repo-url> ~/minecraft && cd ~/minecraft

cp .env.example .env
# edit .env: set MINECRAFT_DOMAIN and (optionally) MINECRAFT_OPS

./mc.sh start
```

The first run downloads Fabric + Bluemap and takes a couple of minutes. `mc.sh start` waits for the server, ops the configured users (idempotent), and patches Bluemap to accept its download and use a single render thread.

### Trust the local CA (first time)

Caddy issues certificates from its own local CA. Download and install the root cert so browsers trust the site:

1. Visit `http://ca.${MINECRAFT_DOMAIN}` and download `caddy-root-ca.crt`
2. Follow the platform instructions on that page (macOS, Linux, Windows, iOS)

## Control script

`mc.sh` is the single entrypoint:

| Command           | What it does |
|-------------------|--------------|
| `./mc.sh start`   | Bring up all containers, render the live status page, op users, configure Bluemap |
| `./mc.sh stop`    | Switch the status page to maintenance, stop only the `minecraft` container |
| `./mc.sh down`    | Stop and remove all containers (world data preserved in `./data/`) |
| `./mc.sh destroy` | Stop, remove containers, AND wipe `./data/` (irreversible) |
| `./mc.sh backup`  | Stop minecraft, archive `./data/` to `./backups/backup-<timestamp>.tar.gz`, restart |
| `./mc.sh status`  | `docker compose ps` |
| `./mc.sh logs`    | Follow logs from all containers |

## Access

| URL | Description |
|-----|-------------|
| `${MINECRAFT_DOMAIN}:25565` | Game server address (use in Minecraft client) |
| `https://${MINECRAFT_DOMAIN}` | Status page |
| `https://${MINECRAFT_DOMAIN}/map/` | Bluemap live world map |
| `http://ca.${MINECRAFT_DOMAIN}` | Download & install the local CA certificate |

## Configuration

Common server settings live in `docker-compose.yml`:

| Variable      | Default              | Description |
|---------------|----------------------|-------------|
| `DIFFICULTY`  | `normal`             | `peaceful` / `easy` / `normal` / `hard` |
| `MODE`        | `survival`           | `survival` / `creative` / `adventure` |
| `MAX_PLAYERS` | `5`                  | Maximum concurrent players |
| `MOTD`        | `A Minecraft Server` | Message shown in the server list |
| `ONLINE_MODE` | `true`               | Set to `false` for offline/cracked accounts |
| `VERSION`     | `26.1`               | Fabric loader version (pinned) |
| `TZ`          | `Europe/Vienna`      | Server timezone |

The domain is configured in `.env`:

| Variable           | Example              | Description |
|--------------------|----------------------|-------------|
| `MINECRAFT_DOMAIN` | `mc.example.com`     | Public-facing domain for the server |
| `MINECRAFT_OPS`    | `alice,bob`          | Comma-separated usernames to auto-op on first start |

After changing a value: `./mc.sh start` (no rebuild needed).

## World backups

```bash
./mc.sh backup
```

Archives `./data/` to `./backups/backup-<timestamp>.tar.gz` with only the minecraft container stopped. Other services stay up.
