# mimir-minecraft

Minecraft Java server (Fabric) for ~10 players running in Docker, with a live world map (Bluemap), a status page, and a lightweight stats API.

## Stack

| Container | Image | Purpose |
|---|---|---|
| `minecraft` | `itzg/minecraft-server` (Fabric) | Game server + Bluemap mod |
| `status`    | `nginx:alpine`                   | Public status page |
| `stats`     | `python:3-alpine`                | CPU / memory / temp API consumed by the status page |

## Ports

| Port    | Protocol | Purpose                     |
|---------|----------|-----------------------------|
| `25565` | TCP      | Minecraft game — forward on router |
| `8100`  | TCP      | Bluemap live map — forward on router |
| `8200`  | TCP      | Status page — forward on router |

## Prerequisites

- Docker + Docker Compose v2 on the host
- Ports `25565`, `8100`, `8200` forwarded (TCP) on your router to the host
- DNS A record for your status domain pointing to the public IP

## Deploy

```bash
git clone <repo-url> ~/minecraft && cd ~/minecraft

cp .env.example .env
# edit .env: set MINECRAFT_DOMAIN and (optionally) MINECRAFT_OPS

./mc.sh start
```

The first run downloads Fabric + Bluemap and takes a couple of minutes. `mc.sh start` waits for the server, ops the configured users (idempotent), and patches Bluemap to accept its download and use a single render thread.

## Control script

`mc.sh` is the single entrypoint:

| Command           | What it does |
|-------------------|--------------|
| `./mc.sh start`   | Bring up all containers, render the live status page, op users, configure Bluemap |
| `./mc.sh stop`    | Switch the status page to maintenance, stop only the `minecraft` container |
| `./mc.sh down`    | Stop and remove all containers (world data preserved in `./data/`) |
| `./mc.sh destroy` | Stop, remove containers, AND wipe `./data/` (irreversible) |
| `./mc.sh status`  | `docker compose ps` |
| `./mc.sh logs`    | Follow logs from all containers |

## Access

| URL                                    | Description |
|----------------------------------------|-------------|
| `${MINECRAFT_DOMAIN}`                  | Game server address (use in Minecraft client) |
| `http://${MINECRAFT_DOMAIN}:8200`      | Status page |
| `http://${MINECRAFT_DOMAIN}:8100`      | Bluemap live world map |

## Configuration

Common server settings live in `docker-compose.yml`:

| Variable      | Default              | Description |
|---------------|----------------------|-------------|
| `DIFFICULTY`  | `normal`             | `peaceful` / `easy` / `normal` / `hard` |
| `MODE`        | `survival`           | `survival` / `creative` / `adventure` |
| `MAX_PLAYERS` | `12`                 | Maximum concurrent players |
| `MOTD`        | `A Minecraft Server` | Message shown in the server list |
| `ONLINE_MODE` | `true`               | Set to `false` for offline/cracked accounts |
| `VERSION`     | `26.1`               | Fabric loader version (pinned) |

After changing a value: `./mc.sh start` (no rebuild needed).

## World backups

World data lives in `./data/`. Back it up with the server stopped:

```bash
./mc.sh down
tar -czf backup-$(date +%F).tar.gz data/
./mc.sh start
```
