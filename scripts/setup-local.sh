#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "已创建 .env，请编辑 OPENAI_API_KEY"
fi
if [[ ! -f .env.local ]]; then
  cp .env.local.example .env.local
fi

docker compose -f docker-compose.infra.yml up -d
echo "中间件已启动。请拉取 embedding 模型: ./scripts/pull-ollama-model.sh"
