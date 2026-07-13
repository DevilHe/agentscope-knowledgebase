#!/usr/bin/env bash
# Let's Encrypt 证书续期（证书约 90 天有效，建议每月自动执行）
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  echo "错误: 未找到 .env"
  exit 1
fi

# shellcheck disable=SC1091
source .env

DOMAIN="${DOMAIN_NAME:-}"
if [ -z "$DOMAIN" ]; then
  echo "错误: .env 中未设置 DOMAIN_NAME"
  exit 1
fi

CERT="/etc/letsencrypt/live/${DOMAIN}/fullchain.pem"
if [ ! -f "$CERT" ]; then
  echo "错误: 证书不存在，请先运行 ./scripts/init-ssl.sh"
  exit 1
fi

echo "检查并续期证书: ${DOMAIN}"
if sudo certbot renew --quiet --webroot -w /var/www/certbot; then
  echo "续期检查完成，重启 frontend 加载新证书..."
  docker compose restart frontend
  echo "完成"
else
  echo "续期失败，请检查 certbot 日志: /var/log/letsencrypt/letsencrypt.log"
  exit 1
fi
