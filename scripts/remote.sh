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
  status [--profile <file>] [--host <user@host>] [--dir <remote-dir>]
  logs   [--profile <file>] [--host <user@host>] [--dir <remote-dir>] [--tail <n>]
  tunnel [--profile <file>] [--host <user@host>] [--local-port <port>] [--remote-host <host>] [--remote-port <port>] [--dry-run]
  help

配置:
  默认读取 .env，也可用 ENV_FILE 或 --profile 指定配置文件。
  CLI 参数优先级最高，其次进程环境变量，其次配置文件。
  remote.sh 不猜远端地址；REMOTE_HOST 必须是 macOS 本机可 ssh 的 USER@HOST。

配置键:
  REMOTE_HOST=wangqiao@47.94.108.140
  REMOTE_DIR=/data/wangqiao/comfy-shell-v2
  REMOTE_LOG_TAIL=80
  REMOTE_TUNNEL_LOCAL_PORT=7800
  REMOTE_TUNNEL_REMOTE_HOST=127.0.0.1
  REMOTE_TUNNEL_REMOTE_PORT=7800

示例:
  ./scripts/remote.sh status --host user@gpu-host --dir /data/wangqiao/comfy-shell-v2
  ./scripts/remote.sh logs --host user@gpu-host --dir /data/wangqiao/comfy-shell-v2 --tail 120
  ./scripts/remote.sh tunnel --host user@gpu-host --local-port 7800 --remote-port 7800
  ./scripts/remote.sh tunnel --profile .env --dry-run
EOF
}

require_value() {
  local name="$1"
  local value="$2"
  [[ -n "$value" ]] || die "$name is required" 2
}

config_file_path() {
  resolve_repo_path "${PROFILE_FILE:-${ENV_FILE:-.env}}"
}

config_value() {
  local key="$1"
  env_value_from "$key" "$(config_file_path)"
}

configured_value() {
  local key="$1"
  local arg_value="$2"
  local env_value="${!key:-}"
  if [[ -n "$arg_value" ]]; then
    printf "%s" "$arg_value"
    return 0
  fi
  if [[ -n "$env_value" ]]; then
    printf "%s" "$env_value"
    return 0
  fi
  config_value "$key"
}

remote_config_error() {
  local missing="$1"
  local needs_dir="$2"
  local verb="is"
  if [[ "$missing" == *,* ]]; then
    verb="are"
  fi
  {
    printf 'ERROR: %s %s not configured.\n\n' "$missing" "$verb"
    printf 'remote.sh does not guess remote targets. Configure real values through environment, --profile FILE, ENV_FILE, or %s.\n\n' "$(config_file_path)"
    printf 'Example config:\n'
    printf '  REMOTE_HOST=wangqiao@47.94.108.140\n'
    if [[ "$needs_dir" == "true" ]]; then
      printf '  REMOTE_DIR=/data/wangqiao/comfy-shell-v2\n'
    else
      printf '  # REMOTE_DIR=/data/wangqiao/comfy-shell-v2  # needed by status/logs\n'
    fi
  } >&2
  exit 2
}

validate_remote_host() {
  [[ "$REMOTE_HOST" == *@* ]] || die "--host/REMOTE_HOST must use USER@HOST" 2
  [[ "$REMOTE_HOST" != -* && "$REMOTE_HOST" != *[[:space:]]* ]] || die "--host/REMOTE_HOST contains invalid characters: $REMOTE_HOST" 2
}

validate_remote_dir() {
  [[ "$REMOTE_DIR" == /* ]] || die "--dir/REMOTE_DIR must be an absolute path" 2
  case "$REMOTE_DIR" in
    *"'"*|*$'\n'*)
      die "--dir must not contain single quotes or newlines" 2
      ;;
  esac
}

parse_common() {
  PROFILE_FILE=""
  PROFILE_EXPLICIT=false
  REMOTE_HOST_ARG=""
  REMOTE_DIR_ARG=""
  TAIL_LINES_ARG=""
  LOCAL_PORT_ARG=""
  TUNNEL_REMOTE_HOST_ARG=""
  REMOTE_PORT_ARG=""
  DRY_RUN=false
  while (($#)); do
    case "$1" in
      --profile)
        require_value "--profile" "${2:-}"
        PROFILE_FILE="$2"
        PROFILE_EXPLICIT=true
        shift 2
        ;;
      --host)
        require_value "--host" "${2:-}"
        REMOTE_HOST_ARG="$2"
        shift 2
        ;;
      --dir)
        require_value "--dir" "${2:-}"
        REMOTE_DIR_ARG="$2"
        shift 2
        ;;
      --tail)
        require_value "--tail" "${2:-}"
        TAIL_LINES_ARG="$2"
        shift 2
        ;;
      --local-port)
        require_value "--local-port" "${2:-}"
        LOCAL_PORT_ARG="$2"
        shift 2
        ;;
      --remote-host)
        require_value "--remote-host" "${2:-}"
        TUNNEL_REMOTE_HOST_ARG="$2"
        shift 2
        ;;
      --remote-port)
        require_value "--remote-port" "${2:-}"
        REMOTE_PORT_ARG="$2"
        shift 2
        ;;
      --dry-run)
        DRY_RUN=true
        shift
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

require_config_file_if_explicit() {
  if [[ "$PROFILE_EXPLICIT" == true && ! -f "$(config_file_path)" ]]; then
    die "config file not found: $(config_file_path)" 2
  fi
}

apply_common_config() {
  require_config_file_if_explicit
  REMOTE_HOST="$(configured_value REMOTE_HOST "$REMOTE_HOST_ARG")"
  REMOTE_DIR="$(configured_value REMOTE_DIR "$REMOTE_DIR_ARG")"
  TAIL_LINES="$(configured_value REMOTE_LOG_TAIL "$TAIL_LINES_ARG")"
  TAIL_LINES="${TAIL_LINES:-80}"
  LOCAL_PORT="$(configured_value REMOTE_TUNNEL_LOCAL_PORT "$LOCAL_PORT_ARG")"
  LOCAL_PORT="${LOCAL_PORT:-7800}"
  TUNNEL_REMOTE_HOST="$(configured_value REMOTE_TUNNEL_REMOTE_HOST "$TUNNEL_REMOTE_HOST_ARG")"
  TUNNEL_REMOTE_HOST="${TUNNEL_REMOTE_HOST:-127.0.0.1}"
  REMOTE_PORT="$(configured_value REMOTE_TUNNEL_REMOTE_PORT "$REMOTE_PORT_ARG")"
  REMOTE_PORT="${REMOTE_PORT:-7800}"
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

validate_simple_host_arg() {
  local name="$1"
  local value="$2"
  [[ "$value" != -* && "$value" != *[[:space:]]* ]] || die "$name contains invalid characters: $value" 2
}

print_command() {
  printf "COMMAND   "
  printf "%q " "$@"
  printf "\n"
}

require_remote_host() {
  [[ -n "$REMOTE_HOST" ]] || remote_config_error "REMOTE_HOST" false
  validate_remote_host
}

require_remote_host_dir() {
  local missing=""
  [[ -n "$REMOTE_HOST" ]] || missing="REMOTE_HOST"
  [[ -n "$REMOTE_DIR" ]] || missing="${missing:+$missing, }REMOTE_DIR"
  [[ -z "$missing" ]] || remote_config_error "$missing" true
  validate_remote_host
  validate_remote_dir
}

remote_status() {
  require_remote_host_dir
  ssh "$REMOTE_HOST" "cd '$REMOTE_DIR' && ./scripts/dev.sh status"
}

remote_logs() {
  require_remote_host_dir
  validate_port_arg "--tail" "$TAIL_LINES"
  ssh "$REMOTE_HOST" "cd '$REMOTE_DIR' && tail -n '$TAIL_LINES' logs/api.log"
}

remote_tunnel() {
  require_remote_host
  validate_port_arg "--local-port" "$LOCAL_PORT"
  validate_port_arg "--remote-port" "$REMOTE_PORT"
  validate_simple_host_arg "--remote-host" "$TUNNEL_REMOTE_HOST"
  ssh_args=(ssh -o ConnectTimeout=10 -o ExitOnForwardFailure=yes -N -L "${LOCAL_PORT}:${TUNNEL_REMOTE_HOST}:${REMOTE_PORT}" "$REMOTE_HOST")
  section "Tunnel"
  event "URL" "web" "http://127.0.0.1:${LOCAL_PORT}/ui/"
  event "FORWARD" "local" "127.0.0.1:${LOCAL_PORT} -> ${TUNNEL_REMOTE_HOST}:${REMOTE_PORT} via ${REMOTE_HOST}"
  event "HOLD" "terminal" "keep this command running while using the tunnel"
  print_command "${ssh_args[@]}"
  if [[ "$DRY_RUN" == true ]]; then
    return 0
  fi
  exec "${ssh_args[@]}"
}

cmd="${1:-}"
case "$cmd" in
  status)
    shift
    parse_common "$@"
    apply_common_config
    remote_status
    ;;
  logs)
    shift
    parse_common "$@"
    apply_common_config
    remote_logs
    ;;
  tunnel)
    shift
    parse_common "$@"
    apply_common_config
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
