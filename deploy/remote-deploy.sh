#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [[ ! -f .env ]]; then
  echo "missing .env in $(pwd)" >&2
  exit 1
fi

chmod 600 .env

GHCR_LOGGED_IN=0
ACTIVE_BACKUP_TMP=""

cleanup() {
  if [[ -n "$ACTIVE_BACKUP_TMP" && -f "$ACTIVE_BACKUP_TMP" ]]; then
    rm -f "$ACTIVE_BACKUP_TMP"
  fi
  if [[ "$GHCR_LOGGED_IN" -eq 1 ]]; then
    docker logout ghcr.io >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

# 安全解析 .env：逐行读取，避免 source/eval 执行密码中的特殊字符
parse_env_file() {
  local env_file="$1"
  local line key val
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%$'\r'}"
    # 跳过空行与注释
    [[ -z "${line//[[:space:]]/}" ]] && continue
    [[ "$line" =~ ^[[:space:]]*# ]] && continue
    [[ "$line" != *=* ]] && continue

    key="${line%%=*}"
    val="${line#*=}"

    # 去除 key 前后空白及可选的 export 前缀
    key="${key#"${key%%[![:space:]]*}"}"
    key="${key%"${key##*[![:space:]]}"}"
    key="${key#export }"
    key="${key#"${key%%[![:space:]]*}"}"

    # 去除成对单引号或双引号（不做变量展开）
    if [[ "$val" =~ ^\"(.*)\"$ ]]; then
      val="${BASH_REMATCH[1]}"
    elif [[ "$val" =~ ^\'(.*)\'$ ]]; then
      val="${BASH_REMATCH[1]}"
    fi

    case "$key" in
      DB_HOST) DB_HOST="$val" ;;
      DB_PORT) DB_PORT="$val" ;;
      DB_NAME) DB_NAME="$val" ;;
      DB_USER) DB_USER="$val" ;;
      DB_PASSWORD) DB_PASSWORD="$val" ;;
      BACKUP_BEFORE_MIGRATE) BACKUP_BEFORE_MIGRATE="$val" ;;
      BACKUP_DIR) BACKUP_DIR="$val" ;;
      BACKUP_KEEP_COUNT) BACKUP_KEEP_COUNT="$val" ;;
      MYSQL_CONTAINER) MYSQL_CONTAINER="$val" ;;
      COMPOSE_FILE) COMPOSE_FILE="$val" ;;
    esac
  done < "$env_file"
}

DB_HOST="${DB_HOST:-}"
DB_PORT="${DB_PORT:-}"
DB_NAME="${DB_NAME:-}"
DB_USER="${DB_USER:-}"
DB_PASSWORD="${DB_PASSWORD:-}"
BACKUP_BEFORE_MIGRATE="${BACKUP_BEFORE_MIGRATE:-}"
BACKUP_DIR="${BACKUP_DIR:-}"
BACKUP_KEEP_COUNT="${BACKUP_KEEP_COUNT:-}"
MYSQL_CONTAINER="${MYSQL_CONTAINER:-}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"

parse_env_file .env

DB_HOST="${DB_HOST:-host.docker.internal}"
DB_PORT="${DB_PORT:-3306}"
DB_NAME="${DB_NAME:-hr_system}"
DB_USER="${DB_USER:-hr_system}"
BACKUP_BEFORE_MIGRATE="${BACKUP_BEFORE_MIGRATE:-true}"
BACKUP_DIR="${BACKUP_DIR:-./backups}"
BACKUP_KEEP_COUNT="${BACKUP_KEEP_COUNT:-7}"

# 私有 GHCR 包需要 PAT；包设为 public 时可跳过登录
if [[ -n "${GHCR_READ_TOKEN:-}" ]]; then
  printf '%s' "$GHCR_READ_TOKEN" \
    | docker login ghcr.io -u "${GHCR_USERNAME:?GHCR_USERNAME is required}" --password-stdin
  # 部署使用的是短期 token，拉取完成后清理，避免把临时凭据留在服务器
  GHCR_LOGGED_IN=1
fi

compose=(docker compose --env-file .env -f "$COMPOSE_FILE")

"${compose[@]}" pull

# 迁移前数据库备份
if [[ "${BACKUP_BEFORE_MIGRATE,,}" == "false" ]]; then
  echo "[deploy] WARNING: BACKUP_BEFORE_MIGRATE=false, skipping pre-migration database backup." >&2
else
  if [[ -z "$DB_PASSWORD" ]]; then
    echo "[deploy] ERROR: DB_PASSWORD is empty in .env; cannot run pre-migration backup." >&2
    exit 1
  fi

  mkdir -p "$BACKUP_DIR"
  chmod 700 "$BACKUP_DIR"

  timestamp="$(date -u +%Y%m%d_%H%M%S)"
  backup_file="${BACKUP_DIR%/}/hr_backup_${timestamp}.sql.gz"
  tmp_file="${backup_file}.tmp"
  ACTIVE_BACKUP_TMP="$tmp_file"

  # 宿主机直连 mysqldump 时，Linux 无法解析容器专用域名 host.docker.internal
  dump_host="$DB_HOST"
  if [[ "$dump_host" == "host.docker.internal" ]]; then
    dump_host="127.0.0.1"
  fi

  mysqldump_bin="$(command -v mysqldump 2>/dev/null || true)"
  if [[ -z "$mysqldump_bin" && -x /www/server/mysql/bin/mysqldump ]]; then
    mysqldump_bin="/www/server/mysql/bin/mysqldump"
  fi

  if [[ -n "$mysqldump_bin" ]]; then
    echo "[deploy] Backing up database '${DB_NAME}' via host mysqldump (${dump_host}:${DB_PORT})..."
    if ! MYSQL_PWD="$DB_PASSWORD" "$mysqldump_bin" \
      --protocol=TCP -h "$dump_host" -P "$DB_PORT" -u "$DB_USER" \
      --single-transaction --quick --no-tablespaces "$DB_NAME" | gzip -c > "$tmp_file"; then
      echo "[deploy] ERROR: Pre-migration backup failed via host mysqldump; aborting migration." >&2
      exit 1
    fi
  else
    target_container="$MYSQL_CONTAINER"
    if [[ -z "$target_container" ]]; then
      target_container="$(docker ps --format '{{.Names}}' | grep -Fx -e hr-mysql -e mysql | head -n 1 || true)"
    fi
    if [[ -z "$target_container" ]]; then
      mysql_image_matches="$(docker ps --format '{{.Names}} {{.Image}}' | awk '$2 ~ /(^|\/)mysql(:|$)/ {print $1}' || true)"
      if [[ -n "$mysql_image_matches" && "$(printf '%s\n' "$mysql_image_matches" | wc -l)" -eq 1 ]]; then
        target_container="$mysql_image_matches"
      fi
    fi

    if [[ -n "$target_container" ]]; then
      echo "[deploy] Backing up database '${DB_NAME}' via docker exec (${target_container})..."
      if ! docker exec -e MYSQL_PWD="$DB_PASSWORD" "$target_container" \
        mysqldump --protocol=TCP -h 127.0.0.1 -P "$DB_PORT" -u "$DB_USER" \
        --single-transaction --quick --no-tablespaces "$DB_NAME" | gzip -c > "$tmp_file"; then
        echo "[deploy] ERROR: Pre-migration backup failed via container '${target_container}'; aborting migration." >&2
        exit 1
      fi
    else
      cat >&2 <<'EOF'
[deploy] ERROR: Cannot perform pre-migration database backup: neither local 'mysqldump' nor a running MySQL container (MYSQL_CONTAINER / hr-mysql / mysql) was found.
[deploy] Please do one of the following before retrying:
  1. Install mysql-client on the host so 'mysqldump' is available;
  2. Set MYSQL_CONTAINER=<container_name> in .env (or run a container named hr-mysql / mysql);
  3. If using an external cloud database with confirmed snapshot backups, explicitly set BACKUP_BEFORE_MIGRATE=false.
EOF
      exit 1
    fi
  fi

  if [[ ! -s "$tmp_file" ]] || ! gzip -t "$tmp_file"; then
    echo "[deploy] ERROR: Backup file '${tmp_file}' is empty or invalid gzip; aborting migration." >&2
    exit 1
  fi

  chmod 600 "$tmp_file"
  mv "$tmp_file" "$backup_file"
  ACTIVE_BACKUP_TMP=""
  echo "[deploy] Backup saved: ${backup_file}"

  if [[ "$BACKUP_KEEP_COUNT" =~ ^[1-9][0-9]*$ ]]; then
    while IFS= read -r old_backup; do
      [[ -n "$old_backup" ]] && rm -f "$old_backup"
    done < <(ls -1t "${BACKUP_DIR%/}"/hr_backup_*.sql.gz 2>/dev/null | tail -n +"$((BACKUP_KEEP_COUNT + 1))" || true)
  fi
fi

# 独立一次性容器执行数据库迁移（带依赖启动，确保栈内 MySQL 已就绪）
echo "[deploy] Running Alembic migrations..."
"${compose[@]}" run --rm backend python -m alembic upgrade head

# 启动服务
"${compose[@]}" up -d --remove-orphans --wait --wait-timeout 180
"${compose[@]}" ps

# 清理部署目录下可能遗留的静态文档目录与宿主机悬空镜像层
if [[ -d ./learning ]]; then
  rm -rf ./learning
fi
docker image prune -f >/dev/null 2>&1 || true
