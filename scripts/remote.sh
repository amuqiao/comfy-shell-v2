#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="${ROOT_DIR:-$(cd "$SCRIPT_DIR/.." && pwd)}"
source "$SCRIPT_DIR/lib/common.sh"

usage() {
  cat <<'EOF'
Usage:
  ./scripts/remote.sh <command> [options]
  ./scripts/remote.sh -h|--help

职责:
  macOS 到远端 GPU host 的轻量操作入口。P1 只提供 status、logs、tunnel。

不负责:
  不同步 .env；不管理 ComfyUI instance 生命周期；不执行任意远端 shell。

命令:
  status --host <user@host> --dir <remote-dir>
  logs   --host <user@host> --dir <remote-dir> [--tail <n>]
  tunnel --host <user@host> [--local-port <port>] [--remote-port <port>]
  help

示例:
  ./scripts/remote.sh status --host user@gpu-host --dir /data/wangqiao/comfy-shell-v2
  ./scripts/remote.sh logs --host user@gpu-host --dir /data/wangqiao/comfy-shell-v2 --tail 120
  ./scripts/remote.sh tunnel --host user@gpu-host --local-port 7800 --remote-port 7800
EOF
}

require_value() {
  local name="$1"
  local value="$2"
  [[ -n "$value" ]] || die "$name is required" 2
}

validate_remote_dir() {
  case "$REMOTE_DIR" in
    *"'"*|*$'\n'*)
      die "--dir must not contain single quotes or newlines" 2
      ;;
  esac
}

parse_common() {
  REMOTE_HOST=""
  REMOTE_DIR=""
  TAIL_LINES="80"
  LOCAL_PORT="7800"
  REMOTE_PORT="7800"
  while (($#)); do
    case "$1" in
      --host)
        REMOTE_HOST="${2:-}"
        shift 2
        ;;
      --dir)
        REMOTE_DIR="${2:-}"
        shift 2
        ;;
      --tail)
        TAIL_LINES="${2:-}"
        shift 2
        ;;
      --local-port)
        LOCAL_PORT="${2:-}"
        shift 2
        ;;
      --remote-port)
        REMOTE_PORT="${2:-}"
        shift 2
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        die "unknown option: $1" 2
        ;;
    esac
  done
}

validate_port_arg() {
  local name="$1"
  local value="$2"
  case "$value" in
    ''|*[!0-9]*) die "$name must be numeric: $value" 2 ;;
  esac
  if (( value < 1 || value > 65535 )); then
    die "$name must be between 1 and 65535: $value" 2
  fi
}

remote_status() {
  require_value "--host" "$REMOTE_HOST"
  require_value "--dir" "$REMOTE_DIR"
  validate_remote_dir
  ssh "$REMOTE_HOST" "cd '$REMOTE_DIR' && ./scripts/dev.sh status"
}

remote_logs() {
  require_value "--host" "$REMOTE_HOST"
  require_value "--dir" "$REMOTE_DIR"
  validate_remote_dir
  validate_port_arg "--tail" "$TAIL_LINES"
  ssh "$REMOTE_HOST" "cd '$REMOTE_DIR' && tail -n '$TAIL_LINES' logs/api.log"
}

remote_tunnel() {
  require_value "--host" "$REMOTE_HOST"
  validate_port_arg "--local-port" "$LOCAL_PORT"
  validate_port_arg "--remote-port" "$REMOTE_PORT"
  ssh -N -L "${LOCAL_PORT}:127.0.0.1:${REMOTE_PORT}" "$REMOTE_HOST"
}

cmd="${1:-}"
case "$cmd" in
  status)
    shift
    parse_common "$@"
    remote_status
    ;;
  logs)
    shift
    parse_common "$@"
    remote_logs
    ;;
  tunnel)
    shift
    parse_common "$@"
    remote_tunnel
    ;;
  help|-h|--help)
    usage
    ;;
  "")
    usage >&2
    exit 2
    ;;
  *)
    usage >&2
    die "unknown command: $cmd" 2
    ;;
esac
