from flask import jsonify, request

from api import api_bp
from services.case_store import get_case, list_cases


@api_bp.get("/history")
def get_history():
    limit = request.args.get("limit", default=50, type=int)
    limit = max(1, min(limit, 200))
    all_cases = list_cases(limit=200)
    return jsonify({"items": all_cases[:limit], "total": len(all_cases)})


@api_bp.get("/compare")
def compare_cases():
    """
    随访对比接口（预留）。
    第一版仅返回两个病例的基础信息，供前端做同屏对比布局。
    """
    case_id_a = request.args.get("case_id_a", "").strip()
    case_id_b = request.args.get("case_id_b", "").strip()

    if not case_id_a or not case_id_b:
        return jsonify({"error": "需要 case_id_a 与 case_id_b 两个参数"}), 400

    case_a = get_case(case_id_a)
    case_b = get_case(case_id_b)

    if case_a is None or case_b is None:
        return jsonify({"error": "其中一个病例不存在"}), 404

    case_a.pop("stored_path", None)
    case_b.pop("stored_path", None)

    return jsonify(
        {
            "message": "对比数据已返回（预留接口，后续可扩展结节变化分析）",
            "case_a": case_a,
            "case_b": case_b,
        }
    )
