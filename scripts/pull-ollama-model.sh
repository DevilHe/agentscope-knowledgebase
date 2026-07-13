#!/usr/bin/env bash
set -euo pipefail
HOST="${OLLAMA_HOST:-http://127.0.0.1:11434}"
MODEL="${EMBEDDING_MODEL:-nomic-embed-text}"
echo "Pulling $MODEL from $HOST ..."
curl -sf "$HOST/api/tags" >/dev/null || { echo "Ollama 未启动"; exit 1; }
docker exec askb-ollama ollama pull "$MODEL" 2>/dev/null || \
  curl -sf "$HOST/api/pull" -d "{\"name\":\"$MODEL\"}" || \
  ollama pull "$MODEL"
echo "Done."
