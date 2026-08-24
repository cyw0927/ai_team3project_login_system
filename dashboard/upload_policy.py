from pathlib import Path

from django.core.exceptions import ValidationError
from django.db.models import FileField
from django.db.models.signals import pre_save


ALLOWED_UPLOAD_EXTENSIONS = {
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".csv",
    ".ppt",
    ".pptx",
    ".txt",
    ".md",
    ".zip",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".py",
    ".ipynb",
    ".json",
}
BLOCKED_UPLOAD_CONTENT_TYPES = {
    "text/html",
    "application/xhtml+xml",
    "application/javascript",
    "text/javascript",
    "application/x-javascript",
    "application/x-sh",
    "application/x-msdownload",
}
DEFAULT_UPLOAD_MAX_BYTES = 20 * 1024 * 1024
EXCEL_UPLOAD_MAX_BYTES = 5 * 1024 * 1024
BACKUP_RESTORE_MAX_BYTES = 100 * 1024 * 1024


def validate_upload(file_obj, *, max_bytes=DEFAULT_UPLOAD_MAX_BYTES):
    """공통 업로드 정책을 검증한다.

    HTTP 업로드뿐 아니라 모델에 직접 저장되는 새 파일에도 같은 정책을 적용한다.
    """
    filename = Path(getattr(file_obj, "name", "") or "").name
    extension = Path(filename).suffix.lower()
    content_type = (getattr(file_obj, "content_type", "") or "").lower()

    if not filename or extension not in ALLOWED_UPLOAD_EXTENSIONS:
        raise ValidationError(
            "허용되지 않은 첨부파일 형식입니다. PDF, Office 문서, CSV, 텍스트, "
            "ZIP, 이미지, Python/Notebook 파일만 업로드할 수 있습니다."
        )
    if content_type in BLOCKED_UPLOAD_CONTENT_TYPES:
        raise ValidationError("브라우저에서 실행될 수 있는 파일 형식은 업로드할 수 없습니다.")

    size = getattr(file_obj, "size", None)
    if size is not None and size > max_bytes:
        limit_mb = max_bytes // (1024 * 1024)
        raise ValidationError(f"첨부파일은 {limit_mb}MB 이하만 업로드할 수 있습니다.")


def _validate_new_model_files(sender, instance, **kwargs):
    """dashboard 모델의 새 FileField 저장을 HTTP 경로 밖에서도 검증한다."""
    if sender._meta.app_label != "dashboard":
        return

    for field in sender._meta.fields:
        if not isinstance(field, FileField):
            continue
        field_file = getattr(instance, field.name, None)
        if not field_file or getattr(field_file, "_committed", True):
            continue
        validate_upload(field_file)


def register_model_upload_validation():
    """모든 dashboard 모델 FileField에 공통 pre-save 검증을 연결한다."""
    pre_save.connect(
        _validate_new_model_files,
        dispatch_uid="dashboard.validate_new_model_uploads",
        weak=False,
    )
