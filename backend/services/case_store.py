import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import CASES_DIR


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _case_path(case_id: str) -> Path:
    return CASES_DIR / f"{case_id}.json"


def create_case(
    *,
    filename: str,
    stored_path: str,
    patient_id: str | None = None,
    patient_name: str | None = None,
    file_type: str | None = None,
    dicom_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    case_id = uuid.uuid4().hex
    case = {
        "case_id": case_id,
        "patient_id": patient_id or "",
        "patient_name": patient_name or "",
        "filename": filename,
        "stored_path": stored_path,
        "file_type": file_type or "",
        "dicom_metadata": dicom_metadata or {},
        "status": "uploaded",
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "analysis": None,
    }
    save_case(case)
    return case


def save_case(case: dict[str, Any]) -> None:
    case["updated_at"] = _now_iso()
    _case_path(case["case_id"]).write_text(
        json.dumps(case, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_case(case_id: str) -> dict[str, Any] | None:
    path = _case_path(case_id)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def list_cases(limit: int = 50) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for path in CASES_DIR.glob("*.json"):
        case = json.loads(path.read_text(encoding="utf-8"))
        cases.append(
            {
                "case_id": case["case_id"],
                "patient_id": case.get("patient_id", ""),
                "patient_name": case.get("patient_name", ""),
                "filename": case.get("filename", ""),
                "status": case.get("status", "uploaded"),
                "created_at": case.get("created_at", ""),
                "updated_at": case.get("updated_at", ""),
                "nodule_count": len((case.get("analysis") or {}).get("nodules", [])),
            }
        )

    cases.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    return cases[:limit]
