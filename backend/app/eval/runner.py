# -*- coding: utf-8 -*-
"""RAG 评测执行器。"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import settings
from app.eval.metrics import (
    answer_keyword_coverage,
    keyword_coverage,
    mrr,
    recall_at_k,
    summarize_full,
    summarize_retrieval,
)
from app.services.llm import invoke_text
from app.services.retrieval import retrieve_detailed

RAG_ANSWER_PROMPT = """你是知识库问答助手。请仅根据以下参考资料回答问题；资料不足时请明确说「资料不足以回答」。

参考资料：
{context}

用户问题：{question}

请用简洁中文回答："""

FAITHFULNESS_PROMPT = """你是 RAG 答案忠实度评审。判断「回答」是否完全可由「参考资料」推出，不得包含参考资料中没有的臆测。

参考资料：
{context}

用户问题：{question}

模型回答：
{answer}

请仅输出 JSON：{{"faithful": true或false, "reason": "一句话说明"}}
faithful=true 表示回答忠实于资料；false 表示存在编造或超出资料的内容。"""


def _parse_faithfulness(raw: str) -> tuple[bool | None, str]:
    match = re.search(r"\{[\s\S]*\}", raw)
    if not match:
        return None, raw.strip()
    try:
        data = json.loads(match.group())
    except json.JSONDecodeError:
        return None, raw.strip()
    faithful = data.get("faithful")
    reason = str(data.get("reason") or "")
    if isinstance(faithful, bool):
        return faithful, reason
    return None, reason or raw.strip()


def _load_dataset(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if "cases" not in data or not isinstance(data["cases"], list):
        raise ValueError("数据集需包含 cases 数组")
    return data


def _stage_metrics(stage_items: list[dict], case: dict, k: int) -> dict[str, float | bool]:
    return {
        "recall@k": recall_at_k(stage_items, case, k),
        "mrr": mrr(stage_items, case),
        "keyword_coverage": keyword_coverage(stage_items, case, k),
    }


async def _evaluate_case(
    case: dict[str, Any],
    *,
    knowledge_base: str,
    top_k: int,
    mode: str,
) -> dict[str, Any]:
    question = case["question"]
    detail = await retrieve_detailed(question, knowledge_base, top_k)

    result: dict[str, Any] = {
        "id": case.get("id") or question[:32],
        "question": question,
        "tags": case.get("tags") or [],
        "stages": {
            "vector": _stage_metrics(detail["vector"], case, top_k),
            "bm25": _stage_metrics(detail["bm25"], case, top_k),
            "rrf": _stage_metrics(detail["rrf"], case, top_k),
            "final": _stage_metrics(detail["final"], case, top_k),
        },
        "recall@k": recall_at_k(detail["final"], case, top_k),
        "mrr": mrr(detail["final"], case),
        "keyword_coverage": keyword_coverage(detail["final"], case, top_k),
        "retrieved_sources": [item.get("source") for item in detail["final"]],
    }

    if mode != "full":
        return result

    context = detail["context"]
    if not context.strip():
        result["answer"] = "资料不足以回答"
        result["answer_keyword_coverage"] = answer_keyword_coverage(result["answer"], case)
        result["faithful"] = True
        result["faithfulness_reason"] = "无检索上下文，未生成臆测内容"
        return result

    answer = await invoke_text(RAG_ANSWER_PROMPT.format(context=context, question=question))
    result["answer"] = answer.strip()
    result["answer_keyword_coverage"] = answer_keyword_coverage(answer, case)

    judge_raw = await invoke_text(
        FAITHFULNESS_PROMPT.format(context=context, question=question, answer=answer)
    )
    faithful, reason = _parse_faithfulness(judge_raw)
    result["faithful"] = faithful
    result["faithfulness_reason"] = reason
    return result


async def run_eval(
    dataset_path: Path,
    *,
    output_path: Path | None = None,
    knowledge_base: str | None = None,
    top_k: int | None = None,
    mode: str = "retrieval",
) -> dict[str, Any]:
    dataset = _load_dataset(dataset_path)
    kb = knowledge_base or dataset.get("knowledge_base") or settings.knowledge_base
    k = top_k or int(dataset.get("top_k") or settings.top_k)

    case_results: list[dict[str, Any]] = []
    for case in dataset["cases"]:
        case_results.append(
            await _evaluate_case(case, knowledge_base=kb, top_k=k, mode=mode)
        )

    summary = summarize_full(case_results) if mode == "full" else summarize_retrieval(case_results)
    stage_summary: dict[str, dict[str, float]] = {}
    for stage in ("vector", "bm25", "rrf", "final"):
        stage_rows = [r["stages"][stage] for r in case_results if r.get("stages", {}).get(stage)]
        if stage_rows:
            stage_summary[stage] = {
                "recall@k": sum(1 for row in stage_rows if row["recall@k"]) / len(stage_rows),
                "mrr": sum(row["mrr"] for row in stage_rows) / len(stage_rows),
                "keyword_coverage": sum(row["keyword_coverage"] for row in stage_rows) / len(stage_rows),
            }

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset": str(dataset_path),
        "knowledge_base": kb,
        "top_k": k,
        "mode": mode,
        "config": {
            "hybrid_enabled": settings.retrieval_hybrid_enabled,
            "hybrid_backend": "qdrant",
            "rerank_enabled": settings.retrieval_rerank_enabled,
            "candidate_top_k": settings.retrieval_candidate_top_k,
            "rrf_k": settings.retrieval_rrf_k,
        },
        "summary": summary,
        "stage_summary": stage_summary,
        "cases": case_results,
    }

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def _print_report(report: dict[str, Any]) -> None:
    print("=" * 60)
    print(f"RAG Eval Report  mode={report['mode']}  kb={report['knowledge_base']}  top_k={report['top_k']}")
    print("=" * 60)
    print("\n[Final Pipeline]")
    for key, value in report["summary"].items():
        print(f"  {key}: {value:.4f}")

    if report.get("stage_summary"):
        print("\n[Per Stage]")
        for stage, metrics in report["stage_summary"].items():
            print(
                f"  {stage:6s}  recall@k={metrics['recall@k']:.4f}  "
                f"mrr={metrics['mrr']:.4f}  keyword_cov={metrics['keyword_coverage']:.4f}"
            )

    print("\n[Cases]")
    for case in report["cases"]:
        status = "PASS" if case.get("recall@k") else "FAIL"
        print(f"  [{status}] {case['id']}: {case['question'][:40]}")
        if case.get("faithful") is not None:
            tag = "FAITHFUL" if case["faithful"] else "HALLUC"
            print(f"         {tag}  answer_cov={case.get('answer_keyword_coverage', 0):.2f}")
    print("=" * 60)


def main() -> None:
    project_root = Path(__file__).resolve().parents[3]
    default_dataset = project_root / "eval" / "golden_set.example.json"

    parser = argparse.ArgumentParser(description="RAG 检索/生成评测脚本")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=default_dataset,
        help="黄金集 JSON 路径",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=project_root / "eval" / "results" / "latest.json",
        help="评测报告输出路径",
    )
    parser.add_argument("--kb", default=None, help="知识库名称，默认读数据集或配置")
    parser.add_argument("--top-k", type=int, default=None, help="检索 top_k")
    parser.add_argument(
        "--mode",
        choices=["retrieval", "full"],
        default="retrieval",
        help="retrieval=仅检索指标；full=含生成答案与忠实度评审",
    )
    args = parser.parse_args()

    report = asyncio.run(
        run_eval(
            args.dataset,
            output_path=args.output,
            knowledge_base=args.kb,
            top_k=args.top_k,
            mode=args.mode,
        )
    )
    _print_report(report)
    print(f"\n报告已写入: {args.output}")


if __name__ == "__main__":
    main()
