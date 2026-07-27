import torchvision.models as models
import torch
import numpy as np
import cv2
import matplotlib.pyplot as plt
from pytorch_grad_cam import GradCAM
from pytorch_grad_cam.utils.image import show_cam_on_image


def load_model(model_path):
    """加载模型"""
    model = models.resnet50(pretrained=False)
    num_features = model.fc.in_features
    model.fc = torch.nn.Linear(num_features, 2)
    model.load_state_dict(torch.load(model_path, map_location='cpu'))
    model.eval()
    return model


def generate_cam(model, input_tensor, original_image):
    """
    生成 CAM 热力图

    参数：
        model: 加载好的模型
        input_tensor: 预处理后的张量，形状 (1, 3, 224, 224)
        original_image: 原始图片（0-1范围的numpy数组，形状 224x224x3）
    返回：
        visualization: 带热力图叠加的图片（numpy数组）
    """
    # 指定目标层：ResNet-50 最后一个卷积层
    # GradCAM 会分析这一层的特征图，找出对判断结果影响最大的区域
    target_layer = model.layer4[-1]

    # 创建 GradCAM 对象
    cam = GradCAM(model=model, target_layers=[target_layer])

    # 生成热力图
    grayscale_cam = cam(input_tensor=input_tensor)
    grayscale_cam = grayscale_cam[0, :]  # 取第一张图的结果

    # 叠加到原图上
    visualization = show_cam_on_image(original_image, grayscale_cam, use_rgb=True)

    return visualization


if __name__ == "__main__":
    print("第5步：CAM 热力图模块")
    print("=" * 40)

    # 加载模型
    model_path = "D:/肺结节AI项目/models/resnet50_lung_nodule.pth"
    print(f"正在加载模型：{model_path}")
    model = load_model(model_path)
    print("模型加载成功！")

    # 创建一张假的图片来测试
    # 生成一个 224x224 的随机灰度图，转成3通道
    fake_gray = np.random.randint(0, 255, (224, 224), dtype=np.uint8)
    fake_rgb = cv2.cvtColor(fake_gray, cv2.COLOR_GRAY2RGB)
    fake_normalized = fake_rgb.astype(np.float32) / 255.0

    # 转成模型输入格式
    input_tensor = torch.FloatTensor(fake_normalized.transpose(2, 0, 1)).unsqueeze(0)

    # 生成热力图
    print("\n正在生成 CAM 热力图...")
    heatmap = generate_cam(model, input_tensor, fake_normalized)

    # 保存热力图
    save_path = "D:/肺结节AI项目/src/test_heatmap.png"
    plt.imsave(save_path, heatmap)
    print(f"热力图已保存到：{save_path}")

    print("\n第5步完成！")