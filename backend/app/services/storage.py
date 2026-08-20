"""증빙 파일 저장.

MVP는 로컬 볼륨(UPLOAD_DIR)에 저장한다. 저장 위치를 이 모듈 뒤로 숨겨
이후 S3 등으로 교체할 때 호출부가 바뀌지 않게 한다.
"""

import uuid
from pathlib import Path

from fastapi import UploadFile

from app.api.errors import AppError
from app.config import get_settings

# 화이트리스트 외 형식은 거부한다 (실행 파일 업로드 등 방지)
ALLOWED_MIME_EXT = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
}
MAX_SIZE_BYTES = 10 * 1024 * 1024  # 10MB
_CHUNK = 1024 * 1024


def save_evidence_file(upload: UploadFile, expense_id: int) -> tuple[str, int]:
    """파일을 저장하고 (상대 경로, 크기)를 반환한다.

    파일명은 서버가 생성한 uuid를 쓴다 — 업로드 원본 이름을 경로에 쓰면
    경로 조작(../)과 이름 충돌 문제가 생기므로 원본 이름은 DB 컬럼으로만 보존한다.
    """
    mime = upload.content_type or ""
    if mime not in ALLOWED_MIME_EXT:
        raise AppError(
            422,
            "UNSUPPORTED_FILE_TYPE",
            "PDF, JPG, PNG 파일만 업로드할 수 있습니다.",
            {"mime_type": mime},
        )

    relative = Path(str(expense_id)) / f"{uuid.uuid4().hex}{ALLOWED_MIME_EXT[mime]}"
    absolute = Path(get_settings().upload_dir) / relative
    absolute.parent.mkdir(parents=True, exist_ok=True)

    size = 0
    with absolute.open("wb") as f:
        while chunk := upload.file.read(_CHUNK):
            size += len(chunk)
            if size > MAX_SIZE_BYTES:
                f.close()
                absolute.unlink(missing_ok=True)
                raise AppError(
                    422,
                    "FILE_TOO_LARGE",
                    "파일은 10MB를 넘을 수 없습니다.",
                    {"limit": MAX_SIZE_BYTES},
                )
            f.write(chunk)
    return str(relative), size


def evidence_absolute_path(relative_path: str) -> Path:
    return Path(get_settings().upload_dir) / relative_path
