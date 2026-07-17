#!/usr/bin/env python3
"""清理旧版 dense-only Qdrant collection（默认 standards）。

检索已迁移至 {QDRANT_COLLECTION}_hybrid，本脚本删除 legacy collection 内全部向量。
用法（项目根目录）:
  cd backend && source .venv/bin/activate && python ../scripts/purge_legacy_qdrant.py
  python ../scripts/purge_legacy_qdrant.py --delete-collection   # 直接删整个 collection
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from qdrant_client.http import models as qmodels

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import settings  # noqa: E402
from app.services.qdrant_hybrid import get_async_qdrant  # noqa: E402


async def main(delete_collection: bool) -> None:
    name = settings.qdrant_collection
    client = get_async_qdrant()
    if not await client.collection_exists(name):
        print(f"collection '{name}' 不存在，无需清理")
        return

    info = await client.get_collection(name)
    count = info.points_count or 0
    if delete_collection:
        await client.delete_collection(name)
        print(f"已删除 collection '{name}'（原 {count} 条向量）")
        return

    if count == 0:
        print(f"collection '{name}' 已为空")
        return

    await client.delete_collection(name)
    await client.create_collection(
        collection_name=name,
        vectors_config=qmodels.VectorParams(
            size=settings.embedding_dimensions,
            distance=qmodels.Distance.COSINE,
        ),
    )
    print(f"已清空 collection '{name}'（删除 {count} 条向量并重建空 collection）")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="清理 legacy Qdrant collection")
    parser.add_argument(
        "--delete-collection",
        action="store_true",
        help="删除整个 collection（不重建）",
    )
    args = parser.parse_args()
    asyncio.run(main(args.delete_collection))
