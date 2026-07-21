from __future__ import annotations

from typing import Any

import pydicom
from pydicom.errors import InvalidDicomError


def _to_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        value = value[0]
    elif hasattr(value, "__iter__") and not isinstance(value, (str, bytes)):
        value = list(value)[0]
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_dicom(file_path: str) -> dict[str, Any]:
    """解析单张 DICOM 切片，提取前端展示与联调所需元数据。"""
    try:
        dataset = pydicom.dcmread(file_path, force=False)
    except InvalidDicomError as exc:
        raise ValueError("无效的 DICOM 文件，请上传 .dcm 原始切片") from exc

    pixel_spacing = getattr(dataset, "PixelSpacing", None)
    spacing: list[float] = []
    if pixel_spacing is not None:
        spacing = [float(v) for v in pixel_spacing]

    return {
        "patient_id": _to_str(getattr(dataset, "PatientID", "")),
        "patient_name": _to_str(getattr(dataset, "PatientName", "")).replace("^", " "),
        "study_date": _to_str(getattr(dataset, "StudyDate", "")),
        "modality": _to_str(getattr(dataset, "Modality", "")),
        "rows": _to_int(getattr(dataset, "Rows", None)),
        "columns": _to_int(getattr(dataset, "Columns", None)),
        "pixel_spacing": spacing,
        "slice_thickness": _to_float(getattr(dataset, "SliceThickness", None)),
        "window_center": _to_float(getattr(dataset, "WindowCenter", None)),
        "window_width": _to_float(getattr(dataset, "WindowWidth", None)),
        "sop_instance_uid": _to_str(getattr(dataset, "SOPInstanceUID", "")),
    }
