#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  echo "错误: 未找到 .env，请先 cp .env.example .env 并配置 DOMAIN_NAME"
  exit 1
fi

# shellcheck disable=SC1091
source .env

if [ -z "${DOMAIN_NAME:-}" ]; then
  echo "错误: 请在 .env 中设置 DOMAIN_NAME=你的域名"
  exit 1
fi

if [ -z "${SSL_EMAIL:-}" ]; then
  echo "错误: 请在 .env 中设置 SSL_EMAIL=你的邮箱（Let's Encrypt 用）"
  exit 1
fi

sudo mkdir -p /var/www/certbot

echo "确保 frontend 已启动（HTTP + ACME 路径）..."
docker compose up -d frontend

echo "申请证书: ${DOMAIN_NAME}"
sudo certbot certonly --webroot \
  -w /var/www/certbot \
  -d "${DOMAIN_NAME}" \
  --email "${SSL_EMAIL}" \
  --agree-tos \
  --no-eff-email

echo "重启 frontend 以启用 HTTPS..."
docker compose restart frontend

echo "完成: https://${DOMAIN_NAME}/"
echo ""
echo "安装自动续期（每月检查，证书约 90 天有效）:"
echo "  chmod +x scripts/renew-ssl.sh scripts/setup-ssl-cron.sh"
echo "  ./scripts/setup-ssl-cron.sh"
