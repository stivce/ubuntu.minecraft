#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# mimir-minecraft control script
# =============================================================================
# Usage: ./mc.sh <command>
#
# Commands:
#   start    Start all containers, render status page, op users, configure Bluemap
#   stop     Switch status page to maintenance, stop only the minecraft container
#   down     Stop and remove all containers (preserves data)
#   destroy  Stop, remove containers, AND delete all world data (irreversible)
#   backup   Stop minecraft, archive ./data/ to ./backups/, restart minecraft
#   status   Show container status
#   logs     Follow logs from all containers
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE="docker compose -f ${SCRIPT_DIR}/docker-compose.yml"
ENV_FILE="${SCRIPT_DIR}/.env"

if [[ -f "${ENV_FILE}" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "${ENV_FILE}"
    set +a
fi

OPS_FILE="${SCRIPT_DIR}/data/ops.json"
BLUEMAP_CONF="/data/config/bluemap/core.conf"
RCON_TIMEOUT=180  # seconds to wait for the server to accept rcon

cmd_start() {
    echo "Starting all containers..."
    $COMPOSE up -d

    echo "Rendering live status page..."
    if docker ps -q -f name=^minecraft-status$ | grep -q .; then
        docker exec minecraft-status sh -c \
            "sed 's|__MINECRAFT_DOMAIN__|${MINECRAFT_DOMAIN:-minecraft.example.com}|g' /templates/index.html > /usr/share/nginx/html/index.html"
    fi

    echo "Waiting for the server to accept rcon (timeout ${RCON_TIMEOUT}s)..."
    local elapsed=0
    until docker exec minecraft rcon-cli list >/dev/null 2>&1; do
        sleep 2
        elapsed=$((elapsed + 2))
        if (( elapsed >= RCON_TIMEOUT )); then
            echo "ERROR: server did not become ready within ${RCON_TIMEOUT}s." >&2
            echo "Check logs with: ./mc.sh logs" >&2
            exit 1
        fi
    done

    if [[ -n "${MINECRAFT_OPS:-}" ]]; then
        IFS=',' read -ra ops_list <<< "${MINECRAFT_OPS}"
        for op in "${ops_list[@]}"; do
            op="${op//[[:space:]]/}"
            [[ -z "$op" ]] && continue
            if grep -q "\"name\": \"${op}\"" "${OPS_FILE}" 2>/dev/null; then
                echo "  ${op} is already op, skipping"
            else
                echo "  Granting op to ${op}"
                docker exec minecraft rcon-cli op "${op}"
            fi
        done
    fi

    echo "Configuring Bluemap..."
    for _ in $(seq 1 30); do
        docker exec minecraft test -f "${BLUEMAP_CONF}" 2>/dev/null && break
        sleep 2
    done
    if docker exec minecraft grep -q "accept-download: false" "${BLUEMAP_CONF}" 2>/dev/null; then
        docker exec minecraft sed -i "s/accept-download: false/accept-download: true/" "${BLUEMAP_CONF}"
        docker exec minecraft sed -i "s/render-thread-count: .*/render-thread-count: 1/" "${BLUEMAP_CONF}"
        docker exec minecraft rcon-cli bluemap reload
        echo "  Bluemap configured and reloaded."
    else
        echo "  Bluemap config already correct."
    fi

    echo "Done."
}

cmd_stop() {
    if docker ps -q -f name=^minecraft-status$ | grep -q .; then
        echo "Switching status page to maintenance..."
        docker exec minecraft-status sh -c \
            "sed 's|__MINECRAFT_DOMAIN__|${MINECRAFT_DOMAIN:-minecraft.example.com}|g' /templates/maintenance.html > /usr/share/nginx/html/index.html"
    fi
    if docker ps -q -f name=^minecraft$ | grep -q .; then
        echo "Stopping minecraft..."
        $COMPOSE stop minecraft
    else
        echo "minecraft is not running, nothing to stop."
    fi
    echo "Done."
}

cmd_down() {
    echo "Stopping and removing all containers (data preserved)..."
    $COMPOSE down
    echo "Done. World data is safe in ./data/"
}

cmd_destroy() {
    echo "WARNING: This will permanently delete all world data, configs, and plugins."
    read -r -p "Type 'yes' to confirm: " confirm
    if [[ "$confirm" != "yes" ]]; then
        echo "Aborted."
        exit 1
    fi
    $COMPOSE down
    rm -rf "${SCRIPT_DIR}/data"
    echo "Everything has been wiped."
}

cmd_status() {
    $COMPOSE ps
}

cmd_logs() {
    $COMPOSE logs -f
}

cmd_backup() {
    local backup_dir="${SCRIPT_DIR}/backups"
    local timestamp
    timestamp="$(date +%F_%H-%M-%S)"
    local archive="${backup_dir}/backup-${timestamp}.tar.gz"

    mkdir -p "${backup_dir}"

    echo "Stopping minecraft for backup..."
    cmd_stop

    echo "Archiving ./data/ to ${archive}..."
    tar -czf "${archive}" -C "${SCRIPT_DIR}" data/
    echo "Backup saved: ${archive}"

    echo "Restarting minecraft..."
    $COMPOSE start minecraft
    echo "Done."
}

usage() {
    cat <<EOF
USAGE
    ./mc.sh <command>

COMMANDS
    start
        Bring up all containers. Renders the live status page, waits for the
        server to accept RCON, grants op to any users in MINECRAFT_OPS, and
        configures Bluemap on first run.

    stop
        Switch the status page to maintenance mode and stop only the minecraft
        container. Caddy, nginx, and stats keep running.

    down
        Stop and remove all containers. World data in ./data/ is preserved.

    destroy
        Stop all containers and permanently delete ./data/ (world, configs,
        plugins). Requires typing 'yes' to confirm. Irreversible.

    backup
        Stop minecraft, archive ./data/ to ./backups/backup-<timestamp>.tar.gz,
        then restart the minecraft container. Other containers stay up.

    status
        Show container status (docker compose ps).

    logs
        Follow logs from all containers.
EOF
    exit "${1:-0}"
}

case "${1:-}" in
    start)   cmd_start ;;
    stop)    cmd_stop ;;
    down)    cmd_down ;;
    destroy) cmd_destroy ;;
    backup)  cmd_backup ;;
    status)  cmd_status ;;
    logs)    cmd_logs ;;
    -h|--help|help|"") usage 0 ;;
    *)
        echo "Unknown command: ${1}" >&2
        echo ""
        usage 1
        ;;
esac
