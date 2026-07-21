from pathlib import Path

from flask import jsonify, request, send_file

from api import api_bp
from services.case_store import get_case, save_case
from services.model_runner import detect_nodules


@api_bp.post("/analyze")
def analyze_case():
    payload = request.get_json(silent=True) or {}
    case_id = payload.get("case_id", "").strip()

    if not case_id:
        return jsonify({"error": "缺少 case_id"}), 400

    case = get_case(case_id)
    if case is None:
        return jsonify({"error": "病例不存在"}), 404

    try:
        analysis = detect_nodules(case["stored_path"])
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except Exception as exc:  # noqa: BLE001 - 比赛项目保留统一错误出口
        return jsonify({"error": f"AI 分析失败: {exc}"}), 500

    case["analysis"] = analysis
    case["status"] = "analyzed"
    save_case(case)

    return jsonify(
        {
            "message": "分析完成",
            "case_id": case_id,
            "status": case["status"],
            "analysis": analysis,
        }
    )


@api_bp.get("/cases/<case_id>")
def get_case_detail(case_id: str):
    case = get_case(case_id)
    if case is None:
        return jsonify({"error": "病例不存在"}), 404

    case.pop("stored_path", None)
    return jsonify({"case": case})


@api_bp.get("/cases/<case_id>/image")
def get_case_image(case_id: str):
    """返回已上传的DICOM原始文件，供前端Cornerstone.js加载渲染。"""
    case = get_case(case_id)
    if case is None:
        return jsonify({"error": "病例不存在"}), 404

    stored_path = case.get("stored_path")
    if not stored_path or not Path(stored_path).exists():
        return jsonify({"error": "影像文件不存在"}), 404

    return send_file(
        stored_path,
        mimetype="application/dicom",
        as_attachment=False,
        download_name=case.get("filename", "image.dcm"),
    )
