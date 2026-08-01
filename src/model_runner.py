"""
AI 推理入口 - 林钟鑫实现

替换 backend/services/model_runner.py 中的 mock 数据
"""

import time
import base64
import torchvision.models as models
import torch
import pydicom
import cv2
import numpy as np
from pytorch_grad_cam import GradCAM
from pytorch_grad_cam.utils.image import show_cam_on_image
from pathlib import Path


# ==================== 模型加载 ====================

MODEL_PATH = "models/resnet50_finetuned.pth"
_model = None


def get_model():
    """加载模型（只加载一次，避免重复加载）"""
    global _model
    if _model is None:
        _model = models.resnet50(weights=None)
        num_features = _model.fc.in_features
        # 使用与训练时相同的3层结构
        _model.fc = torch.nn.Sequential(
            torch.nn.Linear(num_features, 512),
            torch.nn.ReLU(),
            torch.nn.Dropout(0.7),
            torch.nn.Linear(512, 128),
            torch.nn.ReLU(),
            torch.nn.Dropout(0.5),
            torch.nn.Linear(128, 2)
        )
        _model.load_state_dict(torch.load(MODEL_PATH, map_location='cpu', weights_only=True))
        _model.eval()
    return _model


# ==================== 数据预处理 ====================

def preprocess_dicom(dcm_path):
    """
    读取 DICOM 文件并预处理

    返回：
        input_tensor: 模型输入张量 (1, 3, 224, 224)
        original_image: 原始图片 (224, 224, 3) 0-1范围
        dicom_metadata: DICOM 元数据
    """
    ds = pydicom.dcmread(dcm_path)
    ct_image = ds.pixel_array.astype(np.float32)

    # 提取元数据
    dicom_metadata = {
        "rows": getattr(ds, 'Rows', 512),
        "columns": getattr(ds, 'Columns', 512),
        "pixel_spacing": [float(v) for v in getattr(ds, 'PixelSpacing', [1.0, 1.0])],
        "slice_thickness": getattr(ds, 'SliceThickness', 1.0),
    }

    # CT 值转换
    slope = getattr(ds, 'RescaleSlope', 1)
    intercept = getattr(ds, 'RescaleIntercept', 0)
    ct_image = ct_image * slope + intercept

    # 窗宽窗位调整（肺窗）
    window_center = -600
    window_width = 1500
    min_val = window_center - window_width / 2
    max_val = window_center + window_width / 2
    ct_image = np.clip(ct_image, min_val, max_val)
    ct_image = ((ct_image - min_val) / (max_val - min_val) * 255).astype(np.uint8)

    # 保存原始尺寸用于后续计算
    dicom_metadata["original_image"] = ct_image.copy()

    # 调整尺寸为 224x224
    ct_image = cv2.resize(ct_image, (224, 224))
    ct_image = cv2.cvtColor(ct_image, cv2.COLOR_GRAY2RGB)
    original_image = ct_image.astype(np.float32) / 255.0

    # 转成张量
    tensor_image = ct_image.transpose(2, 0, 1) / 255.0
    tensor = torch.FloatTensor(tensor_image).unsqueeze(0)
    # ImageNet 标准化（与训练时一致）
    mean = torch.tensor([0.485, 0.456, 0.406]).view(1, 3, 1, 1)
    std = torch.tensor([0.229, 0.224, 0.225]).view(1, 3, 1, 1)
    tensor = (tensor - mean) / std

    return tensor, original_image, dicom_metadata


# ==================== 预测 ====================

def predict(model, input_tensor):
    """进行良恶性预测"""
    with torch.no_grad():
        output = model(input_tensor)
        probabilities = torch.softmax(output, dim=1)

    predicted_class = torch.argmax(probabilities, dim=1).item()
    confidence = round(probabilities[0][predicted_class].item(), 4)
    malignancy_prob = round(probabilities[0][1].item(), 4)

    return {
        "predicted_class": predicted_class,  # 0=良性, 1=恶性
        "malignancy_probability": malignancy_prob,
        "confidence": confidence,
        "benign_prob": round(probabilities[0][0].item(), 4),
    }


# ==================== CAM 热力图 ====================

def generate_cam_base64(model, input_tensor, dicom_metadata):
    """
    生成 CAM 热力图，返回 base64 编码的 PNG 图片

    参数：
        model: 加载好的模型
        input_tensor: 模型输入张量 (1, 3, 224, 224)
        dicom_metadata: DICOM 元数据（含原始尺寸灰度图）

    返回：
        tuple: (base64字符串, 原始热力图numpy数组 (224,224))
    """
    target_layer = model.layer4[-1]
    cam = GradCAM(model=model, target_layers=[target_layer])
    grayscale_cam = cam(input_tensor=input_tensor)
    grayscale_cam = grayscale_cam[0, :]

    # 用原始 DICOM 尺寸生成 CAM 叠加图，与前端显示匹配
    original_h = dicom_metadata["rows"]
    original_w = dicom_metadata["columns"]
    orig_gray = dicom_metadata["original_image"]
    orig_rgb = cv2.cvtColor(orig_gray, cv2.COLOR_GRAY2RGB).astype(np.float32) / 255.0
    cam_resized = cv2.resize(grayscale_cam, (original_w, original_h))
    visualization = show_cam_on_image(orig_rgb, cam_resized, use_rgb=True)

    # 转成 base64（show_cam_on_image 返回 uint8，不需要再乘255）
    visualization_bgr = cv2.cvtColor(visualization, cv2.COLOR_RGB2BGR)
    _, buffer = cv2.imencode('.png', visualization_bgr)
    img_base64 = base64.b64encode(buffer).decode('utf-8')

    return img_base64, grayscale_cam


def extract_bbox_from_cam(grayscale_cam, original_shape, min_area_ratio=0.005):
    """
    从 CAM 热力图中提取结节边界框

    原理：热力图中高激活区域（红色）= 模型认为最可能是结节的区域
    对热力图做阈值处理 → 找轮廓 → 取最大轮廓 → 得到边界框

    参数：
        grayscale_cam: 热力图数组，形状 (224, 224)，值 0~1
        original_shape: 原始影像尺寸 (rows, cols)，用于坐标映射
        min_area_ratio: 最小面积比例，过滤掉太小的噪声区域

    返回：
        list[dict]: 每个结节的边界框列表，格式 {"x", "y", "width", "height"}
    """
    rows, cols = original_shape

    # 1. 高斯模糊，让热力图更平滑，减少噪声
    heatmap_smooth = cv2.GaussianBlur(grayscale_cam, (5, 5), 0)

    # 2. 取前 15% 高激活区域作为候选结节区域
    threshold = np.percentile(heatmap_smooth, 85)
    binary_map = (heatmap_smooth > threshold).astype(np.uint8)

    # 3. 形态学操作：先膨胀再腐蚀，填充小孔洞，让区域更完整
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    binary_map = cv2.dilate(binary_map, kernel, iterations=2)
    binary_map = cv2.erode(binary_map, kernel, iterations=1)

    # 4. 找轮廓
    contours, _ = cv2.findContours(binary_map, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if not contours:
        # 找不到轮廓时，回退到整张图中心区域
        fallback_size = int(min(rows, cols) * 0.15)
        return [{
            "x": cols // 2 - fallback_size // 2,
            "y": rows // 2 - fallback_size // 2,
            "width": fallback_size,
            "height": fallback_size
        }]

    # 5. 过滤掉面积太小的区域（噪声）
    min_area = grayscale_cam.shape[0] * grayscale_cam.shape[1] * min_area_ratio
    valid_contours = [c for c in contours if cv2.contourArea(c) >= min_area]

    if not valid_contours:
        valid_contours = [max(contours, key=cv2.contourArea)]

    # 6. 按面积从大到小排序，取前3个（最多报告3个结节）
    valid_contours = sorted(valid_contours, key=cv2.contourArea, reverse=True)[:3]

    # 7. 提取边界框并映射回原始影像坐标
    bboxes = []
    cam_h, cam_w = grayscale_cam.shape[:2]
    scale_x = cols / cam_w
    scale_y = rows / cam_h

    for contour in valid_contours:
        x, y, w, h = cv2.boundingRect(contour)

        # 从 224x224 映射回原始尺寸
        x_orig = int(x * scale_x)
        y_orig = int(y * scale_y)
        w_orig = int(w * scale_x)
        h_orig = int(h * scale_y)

        # 加一点 padding（10%），让框稍微大一些，更美观
        pad_x = int(w_orig * 0.1)
        pad_y = int(h_orig * 0.1)
        x_orig = max(0, x_orig - pad_x)
        y_orig = max(0, y_orig - pad_y)
        w_orig = min(cols - x_orig, w_orig + 2 * pad_x)
        h_orig = min(rows - y_orig, h_orig + 2 * pad_y)

        bboxes.append({
            "x": x_orig,
            "y": y_orig,
            "width": w_orig,
            "height": h_orig
        })

    return bboxes


# ==================== 辅助函数 ====================

def estimate_nodule_location(bbox, image_shape):
    """
    根据结节位置估计所在肺叶

    简化逻辑：
    - 图片上方 = 上叶
    - 图片中间 = 中叶
    - 图片下方 = 下叶
    - 左右根据 x 坐标判断
    """
    center_y = bbox["y"] + bbox["height"] / 2
    center_x = bbox["x"] + bbox["width"] / 2
    img_height, img_width = image_shape[:2]

    # 上下判断
    if center_y < img_height / 3:
        vertical = "上叶"
    elif center_y < img_height * 2 / 3:
        vertical = "中叶"
    else:
        vertical = "下叶"

    # 左右判断（注意：CT影像左右与患者左右相反）
    if center_x < img_width / 2:
        side = "右肺"
    else:
        side = "左肺"

    return f"{side}{vertical}"


def estimate_diameter_mm(bbox, pixel_spacing):
    """根据边界框和像素间距估算结节直径（毫米）"""
    width_mm = bbox["width"] * pixel_spacing[0]
    height_mm = bbox["height"] * pixel_spacing[1]
    diameter = round((width_mm + height_mm) / 2, 1)
    return max(diameter, 3.0)  # 最小3mm


# ==================== 主函数 ====================

def detect_nodules(stored_path: str) -> dict:
    """
    AI 肺结节检测推理函数

    输入：
        stored_path: DICOM 文件的本地绝对路径

    返回：
        符合后端接口约定的字典
    """
    start_time = time.time()

    path = Path(stored_path)
    if not path.exists():
        raise FileNotFoundError(f"影像文件不存在: {stored_path}")
    if path.suffix.lower() != ".dcm":
        raise ValueError("当前版本仅支持分析 .dcm 文件")

    # 1. 预处理
    input_tensor, original_image, metadata = preprocess_dicom(stored_path)

    # 2. 加载模型并预测
    model = get_model()
    pred_result = predict(model, input_tensor)

    # 3. 生成 CAM 热力图（同时返回原始热力图数据用于定位）
    cam_base64, grayscale_cam = generate_cam_base64(model, input_tensor, metadata)

    # 4. 从 CAM 热力图中提取真实的结节边界框
    original_h = metadata["rows"]
    original_w = metadata["columns"]
    pixel_spacing = metadata["pixel_spacing"]

    bboxes = extract_bbox_from_cam(grayscale_cam, (original_h, original_w))

    # 5. 组装每个结节的信息
    is_malignant = pred_result["predicted_class"] == 1
    malignancy_prob = pred_result["malignancy_probability"]

    nodules = []
    for i, bbox in enumerate(bboxes):
        location = estimate_nodule_location(bbox, (original_h, original_w))
        diameter_mm = estimate_diameter_mm(bbox, pixel_spacing)
        nodules.append({
            "id": f"nodule-{i+1}",
            "bbox": bbox,
            "diameter_mm": diameter_mm,
            "location": location,
            "malignancy_probability": malignancy_prob,
            "confidence": pred_result["confidence"],
        })

    # 6. 生成诊断结论
    nodule_count = len(nodules)
    if is_malignant:
        conclusion = f"发现 {nodule_count} 个可疑结节，恶性概率为 {malignancy_prob*100:.1f}%，建议进一步检查。"
        follow_up = "建议 3 个月内复查 CT，必要时进行穿刺活检。"
    else:
        conclusion = f"发现 {nodule_count} 个结节，良性概率较高（{(1-malignancy_prob)*100:.1f}%）。"
        follow_up = "建议 6-12 个月后复查 CT，观察结节变化。"

    inference_ms = int((time.time() - start_time) * 1000)

    return {
        "summary": f"检测到 {nodule_count} 个可疑结节",
        "disclaimer": "本结果仅供计算机辅助检测参考，不作为独立诊断依据。",
        "coordinate_system": "image_pixels_top_left",
        "nodules": nodules,
        "report": {
            "conclusion": conclusion,
            "follow_up": follow_up,
        },
        "cam_overlay_base64": cam_base64,
        "model_version": "v1.0.0",
        "inference_ms": inference_ms,
    }


# ==================== 测试 ====================

if __name__ == "__main__":
    print("测试 model_runner.py")
    print("=" * 40)

    # 用普通图片测试（需要先转成dcm或修改测试方式）
    print("该模块需要 DICOM 文件才能完整测试。")
    print("请将此文件替换到 backend/services/model_runner.py 后用真实数据测试。")