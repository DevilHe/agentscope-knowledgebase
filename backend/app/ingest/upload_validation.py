import zipfile
from io import BytesIO
from pathlib import Path

from fastapi import HTTPException, status

from app.config import settings
from app.ingest.pipeline import ALLOWED_SUFFIX

_TEXT_SUFFIXES = {".txt", ".md", ".markdown"}

_MAGIC_CHECKS: dict[str, list[bytes]] = {
    ".pdf": [b"%PDF"],
    ".docx": [b"PK\x03\x04"],
}


def _max_bytes() -> int:
    return settings.upload_max_size_mb * 1024 * 1024


def validate_upload_content(filename: str, content: bytes) -> None:
    suffix = Path(filename or "").suffix.lower()
    if suffix not in ALLOWED_SUFFIX:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"仅支持: {', '.join(sorted(ALLOWED_SUFFIX))}",
        )

    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="文件为空")

    if len(content) > _max_bytes():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"文件大小不能超过 {settings.upload_max_size_mb}MB",
        )

    if b"\x00" in content and suffix in _TEXT_SUFFIXES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="文本文件包含非法二进制内容")

    for magic in _MAGIC_CHECKS.get(suffix, []):
        if not content.startswith(magic):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"文件内容与类型 {suffix} 不匹配",
            )

    if suffix in _TEXT_SUFFIXES:
        try:
            content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="文本文件必须是 UTF-8 编码",
            ) from exc

    if suffix == ".docx":
        _validate_docx(content)

    if suffix == ".pdf":
        _validate_pdf(content)


def _validate_docx(content: bytes) -> None:
    try:
        with zipfile.ZipFile(BytesIO(content)) as zf:
            if "word/vbaProject.bin" in zf.namelist():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="不支持包含宏的 DOCX 文件",
                )
            total_uncompressed = sum(info.file_size for info in zf.infolist())
            if total_uncompressed > _max_bytes() * 10:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="压缩包解压后体积过大，疑似恶意文件",
                )
    except zipfile.BadZipFile as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="DOCX 文件格式无效",
        ) from exc


def _validate_pdf(content: bytes) -> None:
    lowered = content[:8192].lower()
    risky_markers = (b"/javascript", b"/js", b"/launch", b"/embeddedfile")
    if any(marker in lowered for marker in risky_markers):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="PDF 包含可疑脚本或嵌入对象",
        )
