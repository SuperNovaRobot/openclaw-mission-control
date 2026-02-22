#!/usr/bin/env bash
# Mission Control — start / stop / restart / status helper
# Usage: ./mc.sh [start|stop|restart|status|logs|build]

set -euo pipefail

COMPOSE_FILE="$(cd "$(dirname "$0")" && pwd)/compose.yml"
DC="sudo docker compose -f $COMPOSE_FILE"

usage() {
  cat <<EOF
Mission Control management script

Usage: $0 <command> [service...]

Commands:
  start   [svc]  Start all services (or specific ones)
  stop    [svc]  Stop all services (or specific ones)
  restart [svc]  Restart all services (or specific ones)
  status         Show container status
  logs    [svc]  Tail logs (all or specific service)
  build   [svc]  Rebuild images (all or specific ones)
  rebuild [svc]  Rebuild and restart (force recreate)

Services: db, redis, backend, frontend, webhook-worker

Examples:
  $0 start              # Start everything
  $0 restart backend    # Restart just the backend
  $0 logs frontend      # Tail frontend logs
  $0 rebuild            # Full rebuild + restart
EOF
}

cmd="${1:-}"
shift 2>/dev/null || true

case "$cmd" in
  start)
    echo "Starting Mission Control..."
    $DC up -d "$@"
    echo ""
    $DC ps
    echo ""
    echo "Frontend: http://localhost:3000"
    echo "Backend:  http://localhost:8000"
    echo "API docs: http://localhost:8000/docs"
    ;;

  stop)
    echo "Stopping Mission Control..."
    $DC down "$@"
    ;;

  restart)
    echo "Restarting Mission Control..."
    $DC restart "$@"
    echo ""
    $DC ps
    ;;

  status)
    $DC ps
    ;;

  logs)
    $DC logs -f --tail=100 "$@"
    ;;

  build)
    echo "Building images..."
    $DC build "$@"
    ;;

  rebuild)
    echo "Rebuilding and restarting..."
    $DC up -d --build --force-recreate "$@"
    echo ""
    $DC ps
    ;;

  *)
    usage
    exit 1
    ;;
esac
