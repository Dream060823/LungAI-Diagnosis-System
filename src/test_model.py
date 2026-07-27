"""
测试脚本：用 JPG 图片测试模型效果

功能：
1. 加载训练好的模型
2. 对测试图片进行预测
3. 生成 CAM 热力图
4. 从热力图提取边界框
5. 保存结果图片（原图 + 边界框 + 热力图）
"""

import torch
import torchvision.models as models
import cv2
import numpy as np
import matplotlib.pyplot as plt
from pytorch_grad_cam import GradCAM
from pytorch_grad_cam.utils.image import show_cam_on_image
from pathlib import Path


# ==================== 模型加载 ====================

MODEL_PATH = "D:/肺结节AI项目/models/resnet50_finetuned.pth"


def load_model():
    model = models.resnet50(pretrained=False)
    num_features = model.fc.in_features
    model.fc = torch.nn.Sequential(
        torch.nn.Linear(num_features, 512),
        torch.nn.ReLU(),
        torch.nn.Dropout(0.7),
        torch.nn.Linear(512, 128),
        torch.nn.ReLU(),
        torch.nn.Dropout(0.5),
        torch.nn.Linear(128, 2)
    )
    model.load_state_dict(torch.load(MODEL_PATH, map_location='cpu'))
    model.eval()
    return model


# ==================== 预处理 ====================

def preprocess_image(image_path):
    """读取 JPG 图片并预处理"""
    image = cv2.imdecode(np.fromfile(image_path, dtype=np.uint8), cv2.IMREAD_COLOR)
    image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    original_image = cv2.resize(image, (224, 224))
    original_float = original_image.astype(np.float32) / 255.0

    tensor_image = original_image.transpose(2, 0, 1) / 255.0
    tensor = torch.FloatTensor(tensor_image).unsqueeze(0)
    return tensor, original_float, image


# ==================== 预测 ====================

def predict(model, input_tensor):
    with torch.no_grad():
        output = model(input_tensor)
        probabilities = torch.softmax(output, dim=1)
    predicted_class = torch.argmax(probabilities, dim=1).item()
    return {
        "class": "恶性" if predicted_class == 1 else "良性",
        "benign_prob": round(probabilities[0][0].item(), 4),
        "malignant_prob": round(probabilities[0][1].item(), 4),
    }


# ==================== CAM + 边界框 ====================

def generate_cam_and_bbox(model, input_tensor, original_image):
    """生成 CAM 热力图并提取边界框"""
    target_layer = model.layer4[-1]
    cam = GradCAM(model=model, target_layers=[target_layer])
    grayscale_cam = cam(input_tensor=input_tensor)
    grayscale_cam = grayscale_cam[0, :]

    # 生成热力图叠加图
    visualization = show_cam_on_image(original_image, grayscale_cam, use_rgb=True)

    # 从热力图提取边界框
    heatmap_smooth = cv2.GaussianBlur(grayscale_cam, (5, 5), 0)
    threshold = np.percentile(heatmap_smooth, 85)
    binary_map = (heatmap_smooth > threshold).astype(np.uint8)

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    binary_map = cv2.dilate(binary_map, kernel, iterations=2)
    binary_map = cv2.erode(binary_map, kernel, iterations=1)

    contours, _ = cv2.findContours(binary_map, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    bboxes = []
    if contours:
        min_area = 224 * 224 * 0.005
        valid_contours = [c for c in contours if cv2.contourArea(c) >= min_area]
        if not valid_contours:
            valid_contours = [max(contours, key=cv2.contourArea)]
        valid_contours = sorted(valid_contours, key=cv2.contourArea, reverse=True)[:3]

        for contour in valid_contours:
            x, y, w, h = cv2.boundingRect(contour)
            pad = 5
            x = max(0, x - pad)
            y = max(0, y - pad)
            w = min(224 - x, w + 2 * pad)
            h = min(224 - y, h + 2 * pad)
            bboxes.append((x, y, w, h))

    return visualization, grayscale_cam, bboxes


# ==================== 主测试 ====================

def test_images(num_images=5):
    """测试多张图片"""
    model = load_model()
    print("模型加载成功！\n")

    test_dir = Path("D:/肺结节AI项目/data/PN_test")
    test_images = list(test_dir.glob("*.jpg"))[:num_images]

    save_dir = Path("D:/肺结节AI项目/test_results")
    save_dir.mkdir(exist_ok=True)

    for i, img_path in enumerate(test_images):
        print(f"--- 测试 {i+1}/{len(test_images)}: {img_path.name} ---")

        # 预处理
        input_tensor, original_float, original_rgb = preprocess_image(str(img_path))

        # 预测
        result = predict(model, input_tensor)
        print(f"  判断结果：{result['class']}")
        print(f"  良性概率：{result['benign_prob'] * 100:.1f}%")
        print(f"  恶性概率：{result['malignant_prob'] * 100:.1f}%")

        # CAM + 边界框
        heatmap_vis, grayscale_cam, bboxes = generate_cam_and_bbox(model, input_tensor, original_float)
        print(f"  检测到 {len(bboxes)} 个候选区域")
        for j, (x, y, w, h) in enumerate(bboxes):
            print(f"    区域{j+1}: x={x}, y={y}, w={w}, h={h}")

        # 保存结果图片：原图 + 边界框
        result_img = original_float.copy()
        for (x, y, w, h) in bboxes:
            cv2.rectangle(result_img, (x, y), (x + w, y + h), (1, 0, 0), 2)

        # 三合一图：原图 | 热力图 | 带框的图
        fig, axes = plt.subplots(1, 3, figsize=(12, 4))
        axes[0].imshow(original_float)
        axes[0].set_title("Original")
        axes[0].axis("off")

        axes[1].imshow(heatmap_vis)
        axes[1].set_title("CAM Heatmap")
        axes[1].axis("off")

        axes[2].imshow(result_img)
        axes[2].set_title(f"Detection: {result['class']}")
        axes[2].axis("off")

        plt.tight_layout()
        save_path = save_dir / f"result_{img_path.stem}.png"
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        plt.close()
        print(f"  结果已保存：{save_path}\n")

    print(f"全部测试完成！结果保存在：{save_dir}")


if __name__ == "__main__":
    test_images(num_images=5)
