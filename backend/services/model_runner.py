"""
AI 推理入口。

团队约定（后端与算法模块接口契约）：

【输入约定】
- 后端只传 DICOM 文件本地路径（字符串）给算法模块
- 路径保证为有效的 .dcm 文件（后端已做校验）

【预处理约定】
- 窗宽窗位调整（肺窗：Window Width=1500 HU，Window Level=-600 HU）
- 空间归一化（统一分辨率，如 1×1×1mm³）
- HU 值映射到 0-255 灰度范围
以上预处理全部由算法模块（林钟鑫）内部完成

【输出坐标约定】
- bbox 为图像像素坐标，左上角为原点 (0,0)
- 与 DICOM 文件原始像素尺寸对应

【CAM热力图约定】
- 由算法生成 base64 编码的 PNG 图片
- 尺寸与原始影像一致（512×512）
- 前端直接叠加在原始影像上展示

【异常处理约定】
- 文件不存在：抛出 FileNotFoundError
- 非 DICOM 文件：抛出 ValueError
- 推理失败：抛出 Exception（后端会捕获并返回 500）
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def detect_nodules(stored_path: str) -> dict[str, Any]:
    """
    AI 肺结节检测推理函数。

    【函数签名】
    def detect_nodules(dicom_path: str) -> dict[str, Any]

    【输入参数】
    dicom_path: str - DICOM 文件的本地绝对路径

    【返回值结构】
    {
        "summary": str,           # 分析摘要，如"检测到 2 个可疑结节"
        "disclaimer": str,        # 免责声明（固定内容：本结果仅供计算机辅助检测参考...）
        "coordinate_system": str, # 坐标系统说明（固定值："image_pixels_top_left"）
        "nodules": [              # 检测到的结节列表（无结节时为空数组）
            {
                "id": str,                  # 结节唯一标识，如"nodule-1"
                "bbox": {                   # 边界框（图像像素坐标）
                    "x": int,               # 左上角X坐标（0-511）
                    "y": int,               # 左上角Y坐标（0-511）
                    "width": int,           # 宽度（像素）
                    "height": int           # 高度（像素）
                },
                "diameter_mm": float,       # 结节直径（毫米）
                "location": str,            # 位置描述，如"右肺上叶"
                "malignancy_probability": float,  # 恶性概率（0.0-1.0）
                "confidence": float         # 检测置信度（0.0-1.0）
            }
        ],
        "report": {               # 诊断报告
            "conclusion": str,    # 诊断结论
            "follow_up": str      # 随访建议
        },
        "cam_overlay_base64": str | None,  # CAM热力图（base64 PNG，无则为None）
        "model_version": str,     # 模型版本号，如"v1.0.0"
        "inference_ms": int       # 推理耗时（毫秒）
    }

    【当前状态】
    返回 mock 数据，便于前端联调。林钟鑫完成模型封装后替换此处实现。
    """
    path = Path(stored_path)
    if not path.exists():
        raise FileNotFoundError(f"影像文件不存在: {stored_path}")

    if path.suffix.lower() != ".dcm":
        raise ValueError("当前版本仅支持分析 .dcm 文件")

    return {
        "summary": "检测到 1 个可疑结节（mock 数据，待接入真实模型）",
        "disclaimer": "本结果仅供计算机辅助检测参考，不作为独立诊断依据。",
        "coordinate_system": "image_pixels_top_left",
        "nodules": [
            {
                "id": "nodule-1",
                "bbox": {"x": 120, "y": 180, "width": 40, "height": 38},
                "diameter_mm": 6.2,
                "location": "右肺上叶",
                "malignancy_probability": 0.23,
                "confidence": 0.87,
            }
        ],
        "report": {
            "conclusion": "发现 1 个可疑结节，建议结合临床并定期随访。",
            "follow_up": "建议 3-6 个月后复查 CT。",
        },
        "cam_overlay_base64": None,
        "model_version": "mock-v0.1",
        "inference_ms": 120,
    }
