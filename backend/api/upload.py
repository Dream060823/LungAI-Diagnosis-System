from pathlib import Path

from flask import current_app, jsonify, request
from werkzeug.utils import secure_filename

from api import api_bp
from config import ALLOWED_EXTENSIONS
from services.case_store import create_case
from services.dicom_parser import parse_dicom


def _allowed_file(filename: str) -> bool:
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS


@api_bp.post("/upload")
def upload_image():
    """
    接收前端上传的单张 .dcm 原始文件。
    后端使用 pydicom 解析元数据；窗宽窗位等预处理不在此接口执行。
    """
    if "file" not in request.files:
        return jsonify({"error": "缺少 file 字段"}), 400

    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "未选择文件"}), 400

    if not _allowed_file(file.filename):
        return jsonify(
            {
                "error": "当前版本仅支持单张 DICOM 切片上传",
                "allowed_extensions": sorted(ALLOWED_EXTENSIONS),
            }
        ), 400

    patient_id = request.form.get("patient_id", "").strip()
    patient_name = request.form.get("patient_name", "").strip()

    upload_dir: Path = current_app.config["UPLOAD_DIR"]
    upload_dir.mkdir(parents=True, exist_ok=True)

    safe_name = secure_filename(file.filename)
    stored_path = upload_dir / safe_name.lower()

    counter = 1
    while stored_path.exists():
        stored_path = upload_dir / f"{Path(safe_name).stem}_{counter}.dcm"
        counter += 1

    file.save(stored_path)

    try:
        dicom_metadata = parse_dicom(str(stored_path))
    except ValueError as exc:
        stored_path.unlink(missing_ok=True)
        return jsonify({"error": str(exc)}), 400

    resolved_patient_id = patient_id or dicom_metadata.get("patient_id", "")
    resolved_patient_name = patient_name or dicom_metadata.get("patient_name", "")

    case = create_case(
        filename=file.filename,
        stored_path=str(stored_path),
        patient_id=resolved_patient_id or None,
        patient_name=resolved_patient_name or None,
        file_type=".dcm",
        dicom_metadata=dicom_metadata,
    )

    return jsonify(
        {
            "message": "上传成功",
            "case": {
                "case_id": case["case_id"],
                "patient_id": case["patient_id"],
                "patient_name": case["patient_name"],
                "filename": case["filename"],
                "file_type": case["file_type"],
                "status": case["status"],
                "created_at": case["created_at"],
                "dicom_metadata": case["dicom_metadata"],
            },
        }
    ), 201
