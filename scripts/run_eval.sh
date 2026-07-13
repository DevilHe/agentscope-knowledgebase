#!/usr/bin/env bash
# RAG 评测脚本（本地/CI 运行，勿在 2G 生产机上跑 full 模式）
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/backend"

if [[ -d .venv ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

DATASET="${1:-$ROOT/eval/golden_set.json}"
if [[ ! -f "$DATASET" ]]; then
  DATASET="$ROOT/eval/golden_set.example.json"
  echo "未找到 eval/golden_set.json，使用示例数据集: $DATASET"
  echo "提示: cp eval/golden_set.example.json eval/golden_set.json 后按文档填写用例"
fi

MODE="${EVAL_MODE:-retrieval}"
TOP_K="${EVAL_TOP_K:-}"
OUTPUT="$ROOT/eval/results/$(date +%Y%m%d_%H%M%S).json"

ARGS=(--dataset "$DATASET" --output "$OUTPUT" --mode "$MODE")
if [[ -n "$TOP_K" ]]; then
  ARGS+=(--top-k "$TOP_K")
fi

python -m app.eval.runner "${ARGS[@]}"

echo ""
echo "最新报告软链: eval/results/latest.json"
mkdir -p "$ROOT/eval/results"
cp -f "$OUTPUT" "$ROOT/eval/results/latest.json"
