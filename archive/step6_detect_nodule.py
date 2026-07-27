import torchvision.models as models
import torch
import pydicom
import cv2
import numpy as np
import matplotlib.pyplot as plt
from pytorch_grad_cam import GradCAM
from pytorch_grad_cam.utils.image import show_cam_on_image


def load_model(model_path):
    """加载训练好的模型"""
    model = models.resnet50(pretrained=False)
    num_features = model.fc.in_features
    model.fc = torch.nn.Linear(num_features, 2)
    model.load_state_dict(torch.load(model_path, map_location='cpu'))
    model.eval()
    return model


def preprocess_dicom(dcm_path):
    """读取 DICOM 文件并预处理"""
    ds = pydicom.dcmread(dcm_path)
    ct_image = ds.pixel_array.astype(np.float32)

    slope = getattr(ds, 'RescaleSlope', 1)
    intercept = getattr(ds, 'RescaleIntercept', 0)
    ct_image = ct_image * slope + intercept

    window_center = -600
    window_width = 1500
    min_val = window_center - window_width / 2
    max_val = window_center + window_width / 2
    ct_image = np.clip(ct_image, min_val, max_val)
    ct_image = ((ct_image - min_val) / (max_val - min_val) * 255).astype(np.uint8)

    ct_image = cv2.resize(ct_image, (224, 224))
    ct_image = cv2.cvtColor(ct_image, cv2.COLOR_GRAY2RGB)
    original_image = ct_image.astype(np.float32) / 255.0

    tensor_image = ct_image.transpose(2, 0, 1) / 255.0
    tensor = torch.FloatTensor(tensor_image).unsqueeze(0)

    return tensor, original_image


def preprocess_image(image_path):
    """读取普通图片并预处理"""
    import os#################################################################################
    image = cv2.imdecode(np.fromfile(image_path, dtype=np.uint8), cv2.IMREAD_COLOR)###########
    image = cv2.resize(image, (224, 224))
    image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    original_image = image.astype(np.float32) / 255.0

    tensor_image = image.transpose(2, 0, 1) / 255.0
    tensor = torch.FloatTensor(tensor_image).unsqueeze(0)

    return tensor, original_image


def predict(model, input_tensor):
    """进行良恶性预测"""
    with torch.no_grad():
        output = model(input_tensor)
        probabilities = torch.softmax(output, dim=1)

    predicted_class = torch.argmax(probabilities, dim=1).item()

    return {
        "class": "恶性" if predicted_class == 1 else "良性",
        "benign_prob": round(probabilities[0][0].item(), 4),
        "malignant_prob": round(probabilities[0][1].item(), 4)
    }


def generate_cam(model, input_tensor, original_image):
    """生成 CAM 热力图"""
    target_layer = model.layer4[-1]
    cam = GradCAM(model=model, target_layers=[target_layer])
    grayscale_cam = cam(input_tensor=input_tensor)
    grayscale_cam = grayscale_cam[0, :]
    visualization = show_cam_on_image(original_image, grayscale_cam, use_rgb=True)
    return visualization


def detect_nodule(image_path, model_path="D:/肺结节AI项目/models/resnet50_lung_nodule.pth"):
    """
    ============================================================
    肺结节检测主函数 - 刘佳峻调用这一个函数就够了
    ============================================================

    参数：
        image_path: CT影像文件路径（支持 .dcm / .jpg / .png）
        model_path: 模型权重文件路径（有默认值，一般不用改）

    返回：
        dict: {
            "class": "良性" 或 "恶性",
            "benign_prob": 良性概率（0-1），
            "malignant_prob": 恶性概率（0-1），
            "heatmap_path": 热力图保存路径
        }
    """
    # 1. 根据文件类型选择预处理方式
    if image_path.endswith('.dcm'):
        input_tensor, original_image = preprocess_dicom(image_path)
    else:
        input_tensor, original_image = preprocess_image(image_path)

    # 2. 加载模型
    model = load_model(model_path)

    # 3. 预测良恶性
    result = predict(model, input_tensor)

    # 4. 生成热力图
    heatmap = generate_cam(model, input_tensor, original_image)
    heatmap_path = image_path.rsplit('.', 1)[0] + "_heatmap.png"
    # 保存热力图（支持中文路径）
    from PIL import Image
    img = Image.fromarray(heatmap)
    img.save(heatmap_path)

    # 5. 组装返回结果
    result["heatmap_path"] = heatmap_path

    return result


if __name__ == "__main__":
    print("第6步：肺结节检测主函数")
    print("=" * 40)
    print("已封装完成！")
    print()
    print("使用方法：")
    print('  from step6_detect_nodule import detect_nodule')
    print('  result = detect_nodule("path/to/ct_image.dcm")')
    print()
    print("返回格式：")
    print("  {")
    print('    "class": "良性",')
    print('    "benign_prob": 0.85,')
    print('    "malignant_prob": 0.15,')
    print('    "heatmap_path": "xxx_heatmap.png"')
    print("  }")
    print()
    print("第6步完成！")