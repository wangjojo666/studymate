from __future__ import annotations

import zipfile
from pathlib import Path

from app.config import settings


class UploadValidationError(ValueError):
    pass


SUPPORTED_SUFFIXES = {".pdf", ".pptx", ".docx", ".txt", ".png", ".jpg", ".jpeg", ".webp"}
ZIP_SUFFIXES = {".docx", ".pptx"}


def validate_upload_file(path: Path, suffix: str) -> None:
    suffix = suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise UploadValidationError(
            "暂不支持该文件类型，请上传 PDF、PPTX、DOCX、TXT、PNG、JPG 或 WEBP。"
        )
    if not path.exists() or path.stat().st_size == 0:
        raise UploadValidationError("文件为空，请重新选择有效资料。")

    if suffix == ".pdf":
        _require_prefix(path, b"%PDF-", "这不是有效的 PDF 文件，请确认文件没有损坏或伪装扩展名。")
    elif suffix in ZIP_SUFFIXES:
        _validate_office_zip(path, suffix)
    elif suffix == ".png":
        _require_prefix(
            path, b"\x89PNG\r\n\x1a\n", "这不是有效的 PNG 图片，请确认文件没有损坏或伪装扩展名。"
        )
    elif suffix in {".jpg", ".jpeg"}:
        _validate_jpeg(path)
    elif suffix == ".webp":
        _validate_webp(path)
    elif suffix == ".txt":
        _validate_text(path)


def _require_prefix(path: Path, prefix: bytes, message: str) -> None:
    with path.open("rb") as file:
        if file.read(len(prefix)) != prefix:
            raise UploadValidationError(message)


def _validate_office_zip(path: Path, suffix: str) -> None:
    if not zipfile.is_zipfile(path):
        raise UploadValidationError(
            "这不是有效的 Office 文档，请确认 DOCX/PPTX 文件没有损坏或伪装扩展名。"
        )
    expected_prefix = "word/" if suffix == ".docx" else "ppt/"
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            _validate_zip_limits(infos)
            names = {info.filename for info in infos}
    except zipfile.BadZipFile as exc:
        raise UploadValidationError("Office 文档无法打开，请确认文件没有损坏。") from exc
    if "[Content_Types].xml" not in names or not any(
        name.startswith(expected_prefix) for name in names
    ):
        label = "Word" if suffix == ".docx" else "PowerPoint"
        raise UploadValidationError(f"这不是有效的 {label} 文档，请确认文件类型与扩展名一致。")


def _validate_zip_limits(infos: list[zipfile.ZipInfo]) -> None:
    if len(infos) > settings.office_zip_max_files:
        raise UploadValidationError(
            f"Office 文档内部文件数量过多（{len(infos)} 个），可能是异常压缩包，请重新导出后上传。"
        )
    total_uncompressed = 0
    for info in infos:
        normalized_name = info.filename.replace("\\", "/")
        if normalized_name.startswith("/") or ".." in normalized_name.split("/"):
            raise UploadValidationError("Office 文档包含异常路径，请重新导出后上传。")
        if info.file_size > settings.office_zip_max_member_bytes:
            raise UploadValidationError("Office 文档内部存在过大的单个文件，可能导致解压资源耗尽。")
        total_uncompressed += int(info.file_size)
        if total_uncompressed > settings.office_zip_max_total_uncompressed_bytes:
            raise UploadValidationError(
                "Office 文档解压后体积过大，可能是异常压缩包，请压缩内容后重试。"
            )


def _validate_jpeg(path: Path) -> None:
    with path.open("rb") as file:
        header = file.read(3)
    if header[:2] != b"\xff\xd8" or header[2:3] != b"\xff":
        raise UploadValidationError("这不是有效的 JPEG 图片，请确认文件没有损坏或伪装扩展名。")


def _validate_webp(path: Path) -> None:
    with path.open("rb") as file:
        header = file.read(12)
    if len(header) < 12 or header[:4] != b"RIFF" or header[8:12] != b"WEBP":
        raise UploadValidationError("这不是有效的 WEBP 图片，请确认文件没有损坏或伪装扩展名。")


def _validate_text(path: Path) -> None:
    data = path.read_bytes()
    text = None
    for encoding in ("utf-8", "utf-8-sig", "gbk"):
        try:
            text = data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise UploadValidationError("TXT 文件编码无法识别，请使用 UTF-8 或 GBK 文本重新上传。")
    if "\x00" in text:
        raise UploadValidationError("TXT 文件包含二进制内容，请确认文件类型与扩展名一致。")
