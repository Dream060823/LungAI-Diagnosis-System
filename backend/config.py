import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
CASES_DIR = DATA_DIR / "cases"

# 当前版本仅支持单张 DICOM 切片上传
ALLOWED_EXTENSIONS = {".dcm"}


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key")
    MAX_CONTENT_LENGTH = 512 * 1024 * 1024  # 512 MB
    UPLOAD_DIR = UPLOAD_DIR
    CASES_DIR = CASES_DIR
    CORS_ORIGINS = os.environ.get(
        "CORS_ORIGINS",
        "http://localhost:5173,http://localhost:8080,http://127.0.0.1:5173",
    ).split(",")


def ensure_data_dirs() -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    CASES_DIR.mkdir(parents=True, exist_ok=True)
