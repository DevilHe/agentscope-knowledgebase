#!/usr/bin/env bash
# 安装 certbot 自动续期 cron（每月 1 日凌晨 3 点）
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
RENEW_SCRIPT="${PROJECT_DIR}/scripts/renew-ssl.sh"
CRON_LINE="0 3 1 * * ${RENEW_SCRIPT} >> /var/log/certbot-renew.log 2>&1"

chmod +x "${RENEW_SCRIPT}"

if crontab -l 2>/dev/null | grep -qF "${RENEW_SCRIPT}"; then
  echo "cron 已存在，无需重复安装"
  crontab -l | grep -F "${RENEW_SCRIPT}"
  exit 0
fi

(crontab -l 2>/dev/null; echo "${CRON_LINE}") | crontab -
echo "已安装自动续期 cron:"
echo "  ${CRON_LINE}"
echo ""
echo "手动测试续期: ${RENEW_SCRIPT}"
