"""
第8步：微调训练代码

功能：
1. 读取 LUNA16 数据集（.mhd 格式的 CT 扫描）
2. 根据 annotations.csv 提取结节区域
3. 生成正样本（有结节）和负样本（无结节）
4. 微调 ResNet-50 模型
5. 保存训练好的模型
"""

import os
import numpy as np
import pandas as pd
import cv2
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
import torchvision.models as models
import SimpleITK as sitk
from pathlib import Path
import time


# ==================== 配置参数 ====================

class Config:
    """训练配置"""
    # 数据路径
    DATA_DIR = "D:/肺结节AI项目/data/subset0"
    ANNOTATIONS_FILE = "D:/肺结节AI项目/data/annotations.csv"

    # 模型保存路径
    MODEL_SAVE_PATH = "D:/肺结节AI项目/models/resnet50_finetuned.pth"

    # 训练参数
    BATCH_SIZE = 16
    NUM_EPOCHS = 20
    LEARNING_RATE = 0.001
    IMAGE_SIZE = 224

    # 结节提取参数
    PATCH_SIZE = 64  # 从CT中裁取的结节区域大小（像素）
    NUM_NEGATIVE_SAMPLES_PER_NODULE = 3  # 每个结节对应生成几个负样本


# ==================== 数据加载 ====================

def load_ct_scan(mhd_path):
    """
    读取 .mhd 格式的 CT 扫描文件

    参数：
        mhd_path: .mhd 文件路径
    返回：
        numpy数组: 3D CT数据
        spacing: 像素间距 (x, y, z)
        origin: 原点坐标
    """
    itk_image = sitk.ReadImage(mhd_path)
    ct_array = sitk.GetArrayFromImage(itk_image)  # (slices, rows, cols)
    spacing = itk_image.GetSpacing()  # (x, y, z)
    origin = itk_image.GetOrigin()  # (x, y, z)

    return ct_array, spacing, origin


def world_to_voxel(world_coord, origin, spacing):
    """
    将世界坐标转换为体素坐标

    参数：
        world_coord: 世界坐标 (x, y, z)
        origin: CT原点坐标
        spacing: 像素间距
    返回：
        voxel_coord: 体素坐标 (x, y, z)
    """
    voxel_coord = [(world_coord[i] - origin[i]) / spacing[i] for i in range(3)]
    return np.array(voxel_coord)


def extract_patch(ct_array, center_voxel, patch_size):
    """
    从CT数组中提取一个立方体区域

    参数：
        ct_array: 3D CT数据
        center_voxel: 中心点体素坐标 (x, y, z)
        patch_size: 立方体边长
    返回：
        patch: 提取的区域（2D切片，取中间层）
    """
    center = np.round(center_voxel).astype(int)

    half = patch_size // 2
    # 确保不越界
    z = np.clip(center[2], 0, ct_array.shape[0] - 1)
    y_start = max(0, center[1] - half)
    y_end = min(ct_array.shape[1], center[1] + half)
    x_start = max(0, center[0] - half)
    x_end = min(ct_array.shape[2], center[0] + half)

    # 提取2D切片（取z坐标处的切片）
    patch_2d = ct_array[z, y_start:y_end, x_start:x_end]

    # 如果尺寸不够，用0填充
    if patch_2d.shape[0] < patch_size or patch_2d.shape[1] < patch_size:
        padded = np.zeros((patch_size, patch_size), dtype=patch_2d.dtype)
        padded[:patch_2d.shape[0], :patch_2d.shape[1]] = patch_2d
        patch_2d = padded

    return patch_2d


def apply_window(ct_image, window_center=-600, window_width=1500):
    """窗宽窗位调整"""
    min_val = window_center - window_width / 2
    max_val = window_center + window_width / 2
    ct_image = np.clip(ct_image, min_val, max_val)
    ct_image = ((ct_image - min_val) / (max_val - min_val) * 255).astype(np.uint8)
    return ct_image


# ==================== 数据集类 ====================

class LungNoduleDataset(Dataset):
    """
    肺结节数据集

    从LUNA16数据中提取正样本（结节）和负样本（非结节）
    """

    def __init__(self, samples, transform=None):
        """
        参数：
            samples: 列表，每个元素为 (patch, label)
                patch: 2D图像 (numpy数组)
                label: 0=非结节, 1=结节
            transform: 数据增强变换
        """
        self.samples = samples
        self.transform = transform

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        patch, label = self.samples[idx]

        # 窗宽窗位调整
        patch = apply_window(patch)

        # 调整尺寸为 224x224
        patch = cv2.resize(patch, (Config.IMAGE_SIZE, Config.IMAGE_SIZE))

        # 灰度图转3通道
        patch = cv2.cvtColor(patch, cv2.COLOR_GRAY2RGB)

        # 转成张量并归一化
        patch = patch.transpose(2, 0, 1) / 255.0
        patch = torch.FloatTensor(patch)

        return patch, label


# ==================== 数据准备 ====================

def prepare_training_data(data_dir, annotations_file):
    """
    准备训练数据

    从LUNA16数据中提取结节和非结节样本

    返回：
        samples: [(patch, label), ...] 的列表
    """
    print("正在准备训练数据...")
    print(f"数据目录：{data_dir}")
    print(f"标注文件：{annotations_file}")

    # 读取标注文件
    if not os.path.exists(annotations_file):
        print(f"错误：找不到标注文件 {annotations_file}")
        print("请确保 annotations.csv 在 data 目录下")
        return []

    annotations = pd.read_csv(annotations_file)
    print(f"标注数量：{len(annotations)}")

    samples = []
    processed_count = 0

    # 遍历每个CT扫描文件
    mhd_files = list(Path(data_dir).glob("*.mhd"))
    print(f"找到 {len(mhd_files)} 个CT扫描文件")

    for mhd_path in mhd_files:
        series_uid = mhd_path.stem

        # 查找该CT对应的标注
        nodule_annotations = annotations[annotations['seriesuid'] == series_uid]

        if len(nodule_annotations) == 0:
            continue

        print(f"处理：{series_uid[:30]}... （{len(nodule_annotations)} 个结节）")

        try:
            ct_array, spacing, origin = load_ct_scan(str(mhd_path))
        except Exception as e:
            print(f"  读取失败：{e}")
            continue

        # 提取正样本（结节区域）
        for _, row in nodule_annotations.iterrows():
            world_coord = np.array([row['coordX'], row['coordY'], row['coordZ']])
            voxel_coord = world_to_voxel(world_coord, origin, spacing)

            # 提取结节区域
            patch = extract_patch(ct_array, voxel_coord, Config.PATCH_SIZE)
            if patch.size > 0:
                samples.append((patch, 1))  # label=1 表示结节

                # 生成负样本（随机偏移位置，避开结节区域）
                for _ in range(Config.NUM_NEGATIVE_SAMPLES_PER_NODULE):
                    offset = np.random.randint(-50, 50, size=3)
                    neg_coord = voxel_coord + offset
                    neg_coord = np.clip(neg_coord, 0, [s - 1 for s in ct_array.shape])
                    neg_patch = extract_patch(ct_array, neg_coord, Config.PATCH_SIZE)
                    if neg_patch.size > 0:
                        samples.append((neg_patch, 0))  # label=0 表示非结节

        processed_count += 1

    print(f"\n数据准备完成：")
    print(f"  处理了 {processed_count} 个CT扫描")
    print(f"  总样本数：{len(samples)}")
    print(f"  正样本（结节）：{sum(1 for _, l in samples if l == 1)}")
    print(f"  负样本（非结节）：{sum(1 for _, l in samples if l == 0)}")

    return samples


# ==================== 模型 ====================

def create_model():
    """
    创建微调模型

    使用 ImageNet 预训练的 ResNet-50，修改最后一层为2分类
    """
    model = models.resnet50(pretrained=True)

    # 冻结前面的层（只训练最后几层）
    for param in model.parameters():
        param.requires_grad = False

    # 修改最后一层（需要训练）
    num_features = model.fc.in_features
    model.fc = nn.Sequential(
        nn.Linear(num_features, 256),
        nn.ReLU(),
        nn.Dropout(0.5),
        nn.Linear(256, 2)
    )

    return model


# ==================== 训练 ====================

def train_model(model, train_loader, val_loader, device):
    """
    训练模型

    参数：
        model: 待训练的模型
        train_loader: 训练数据加载器
        val_loader: 验证数据加载器
        device: 训练设备（cpu或cuda）
    """
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(model.fc.parameters(), lr=Config.LEARNING_RATE)
    scheduler = optim.lr_scheduler.StepLR(optimizer, step_size=10, gamma=0.1)

    best_val_acc = 0.0

    print(f"\n开始训练...")
    print(f"  设备：{device}")
    print(f"  批次大小：{Config.BATCH_SIZE}")
    print(f"  训练轮次：{Config.NUM_EPOCHS}")
    print(f"  学习率：{Config.LEARNING_RATE}")
    print("=" * 50)

    for epoch in range(Config.NUM_EPOCHS):
        start_time = time.time()

        # 训练阶段
        model.train()
        train_loss = 0.0
        train_correct = 0
        train_total = 0

        for batch_idx, (inputs, labels) in enumerate(train_loader):
            inputs, labels = inputs.to(device), labels.to(device)

            optimizer.zero_grad()
            outputs = model(inputs)
            loss = criterion(outputs, labels)
            loss.backward()
            optimizer.step()

            train_loss += loss.item()
            _, predicted = outputs.max(1)
            train_total += labels.size(0)
            train_correct += predicted.eq(labels).sum().item()

        train_acc = 100. * train_correct / train_total

        # 验证阶段
        model.eval()
        val_loss = 0.0
        val_correct = 0
        val_total = 0

        with torch.no_grad():
            for inputs, labels in val_loader:
                inputs, labels = inputs.to(device), labels.to(device)
                outputs = model(inputs)
                loss = criterion(outputs, labels)

                val_loss += loss.item()
                _, predicted = outputs.max(1)
                val_total += labels.size(0)
                val_correct += predicted.eq(labels).sum().item()

        val_acc = 100. * val_correct / val_total

        elapsed = time.time() - start_time
        scheduler.step()

        print(f"Epoch [{epoch+1}/{Config.NUM_EPOCHS}] "
            f"Train Loss: {train_loss/len(train_loader):.4f} "
            f"Train Acc: {train_acc:.2f}% "
            f"Val Loss: {val_loss/len(val_loader):.4f} "
            f"Val Acc: {val_acc:.2f}% "
            f"Time: {elapsed:.1f}s")

        # 保存最佳模型
        if val_acc > best_val_acc:
            best_val_acc = val_acc
            torch.save(model.state_dict(), Config.MODEL_SAVE_PATH)
            print(f"  → 保存最佳模型（验证准确率：{val_acc:.2f}%）")

    print("=" * 50)
    print(f"训练完成！最佳验证准确率：{best_val_acc:.2f}%")
    print(f"模型已保存到：{Config.MODEL_SAVE_PATH}")


# ==================== 主函数 ====================

def main():
    print("=" * 50)
    print("肺结节模型微调训练")
    print("=" * 50)

    # 检查数据是否存在
    if not os.path.exists(Config.DATA_DIR):
        print(f"\n错误：找不到数据目录 {Config.DATA_DIR}")
        print("请先下载 LUNA16 subset0 并解压到该目录")
        print("下载地址：https://luna16.grand-challenge.org/data/")
        return

    if not os.path.exists(Config.ANNOTATIONS_FILE):
        print(f"\n错误：找不到标注文件 {Config.ANNOTATIONS_FILE}")
        print("请确保 annotations.csv 在 data 目录下")
        return

    # 准备数据
    samples = prepare_training_data(Config.DATA_DIR, Config.ANNOTATIONS_FILE)

    if len(samples) == 0:
        print("\n没有找到训练数据，请检查数据路径")
        return

    # 打乱数据
    np.random.shuffle(samples)

    # 划分训练集和验证集（80%训练，20%验证）
    split_idx = int(len(samples) * 0.8)
    train_samples = samples[:split_idx]
    val_samples = samples[split_idx:]

    print(f"\n数据划分：")
    print(f"  训练集：{len(train_samples)} 样本")
    print(f"  验证集：{len(val_samples)} 样本")

    # 创建数据加载器
    train_dataset = LungNoduleDataset(train_samples)
    val_dataset = LungNoduleDataset(val_samples)

    train_loader = DataLoader(train_dataset, batch_size=Config.BATCH_SIZE, shuffle=True, num_workers=0)
    val_loader = DataLoader(val_dataset, batch_size=Config.BATCH_SIZE, shuffle=False, num_workers=0)

    # 创建模型
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = create_model()
    model = model.to(device)

    print(f"\n模型结构：")
    print(f"  骨干网络：ResNet-50（ImageNet预训练）")
    print(f"  修改层：全连接层 → 256 → 2（良性/恶性）")

    # 训练
    train_model(model, train_loader, val_loader, device)

    print("\n训练完成！")


if __name__ == "__main__":
    main()