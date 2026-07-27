import pydicom
import cv2
import numpy as np
import torch


def preprocess_dicom(dcm_path):
    """
    读取 DICOM 文件并预处理，返回 ResNet-50 能接受的输入

    参数：
        dcm_path: DICOM 文件路径，例如 "data/patient001.dcm"
    返回：
        torch.Tensor: 形状为 (1, 3, 224, 224) 的张量，可直接送入模型
    """

    # 第1步：读取 DICOM 文件
    ds = pydicom.dcmread(dcm_path)
    ct_image = ds.pixel_array.astype(np.float32)

    # 第2步：转换为真实 CT 值（HU值）
    slope = getattr(ds, 'RescaleSlope', 1)
    intercept = getattr(ds, 'RescaleIntercept', 0)
    ct_image = ct_image * slope + intercept

    # 第3步：窗宽窗位调整（肺窗）
    window_center = -600
    window_width = 1500
    min_val = window_center - window_width / 2
    max_val = window_center + window_width / 2
    ct_image = np.clip(ct_image, min_val, max_val)
    ct_image = ((ct_image - min_val) / (max_val - min_val) * 255).astype(np.uint8)

    # 第4步：调整尺寸为 224x224
    ct_image = cv2.resize(ct_image, (224, 224))

    # 第5步：灰度图转 3 通道
    ct_image = cv2.cvtColor(ct_image, cv2.COLOR_GRAY2RGB)

    # 第6步：转成 PyTorch 张量并归一化
    ct_image = ct_image.transpose(2, 0, 1)
    ct_image = ct_image / 255.0
    tensor = torch.FloatTensor(ct_image).unsqueeze(0)

    return tensor


def preprocess_image(image_path):
    """
    读取普通图片（jpg/png）并预处理
    用于测试时没有 DICOM 文件的情况

    参数：
        image_path: 图片文件路径
    返回：
        torch.Tensor: 形状为 (1, 3, 224, 224) 的张量
    """
    image = cv2.imread(image_path)
    image = cv2.resize(image, (224, 224))
    image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    image = image.transpose(2, 0, 1)
    image = image / 255.0
    tensor = torch.FloatTensor(image).unsqueeze(0)
    return tensor


if __name__ == "__main__":
  print("第3步：数据预处理模块")
  print("=" * 40)
  print("已定义两个函数：")
  print("  preprocess_dicom(dcm_path)   → 处理 DICOM 格式的 CT 影像")
  print("  preprocess_image(image_path) → 处理普通 jpg/png 图片")
  print()
  print("函数返回形状为 (1, 3, 224, 224) 的张量")
  print("可直接送入 ResNet-50 模型进行推理")
  print()
  print("第3步完成！")  