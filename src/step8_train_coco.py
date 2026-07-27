"""
第8步：使用 COCO 格式的 LUNA16 数据集训练模型

数据来源：https://github.com/dremmanuel2/COCO_format_for_the_LUNA16_dataset
数据格式：COCO JSON + JPG 图片
"""

import json
import os
import numpy as np
import cv2
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
import torchvision.models as models
import torchvision.transforms as transforms
import time


# ==================== 配置参数 ====================

class Config:
    """训练配置"""
    # 数据路径
    DATA_DIR = "D:/肺结节AI项目/data"
    TRAIN_IMAGE_DIR = os.path.join(DATA_DIR, "PN_train")
    TEST_IMAGE_DIR = os.path.join(DATA_DIR, "PN_test")
    TRAIN_ANNOTATION = os.path.join(DATA_DIR, "annotations", "PN_train.json")
    TEST_ANNOTATION = os.path.join(DATA_DIR, "annotations", "PN_test.json")

    # 模型保存路径
    MODEL_SAVE_PATH = "D:/肺结节AI项目/models/resnet50_finetuned.pth"

    # 训练参数
    BATCH_SIZE = 8  # CPU训练用小batch
    NUM_EPOCHS = 10  # CPU训练减少轮次
    LEARNING_RATE = 0.0005  # 降低学习率
    IMAGE_SIZE = 224


# ==================== 数据增强 ====================

train_transform = transforms.Compose([
    transforms.ToPILImage(),
    transforms.Resize((Config.IMAGE_SIZE, Config.IMAGE_SIZE)),
    transforms.RandomHorizontalFlip(),  # 水平翻转
    transforms.RandomVerticalFlip(),    # 垂直翻转
    transforms.RandomRotation(15),      # 随机旋转
    transforms.ColorJitter(brightness=0.2, contrast=0.2),  # 亮度对比度调整
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
])

val_transform = transforms.Compose([
    transforms.ToPILImage(),
    transforms.Resize((Config.IMAGE_SIZE, Config.IMAGE_SIZE)),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
])


# ==================== 数据集类 ====================

class COCOLungNoduleDataset(Dataset):
    """
    COCO 格式的肺结节数据集

    数据集说明：
    - 所有图片都是结节区域（正样本）
    - 为了训练二分类模型，我们同时生成负样本（随机噪声或随机增强）
    """

    def __init__(self, image_dir, annotation_file, transform=None, is_train=True):
        self.image_dir = image_dir
        self.transform = transform
        self.is_train = is_train

        # 读取 COCO 标注
        with open(annotation_file, 'r') as f:
            coco_data = json.load(f)

        # 构建 image_id -> filename 映射
        self.image_info = {}
        for img in coco_data['images']:
            self.image_info[img['id']] = img['file_name']

        # 构建标注列表
        self.annotations = coco_data['annotations']

        # 所有图片文件名
        self.image_files = list(self.image_info.values())

        print(f"  加载了 {len(self.image_files)} 张图片，{len(self.annotations)} 个标注")

    def __len__(self):
        # 返回正样本数量的2倍（正样本 + 负样本）
        return len(self.image_files) * 2

    def __getitem__(self, idx):
        # 正样本：结节图片
        if idx < len(self.image_files):
            img_name = self.image_files[idx]
            img_path = os.path.join(self.image_dir, img_name)
            label = 1  # 结节
        # 负样本：用正样本图片做重度数据增强，模拟非结节的肺部组织
        else:
            # 从正样本中随机选一张，做重度变换让它看起来不像结节
            neg_idx = np.random.randint(0, len(self.image_files))
            neg_name = self.image_files[neg_idx]
            neg_path = os.path.join(self.image_dir, neg_name)
            label = 0  # 非结节

            try:
                image = cv2.imdecode(np.fromfile(neg_path, dtype=np.uint8), cv2.IMREAD_COLOR)
                if image is None:
                    raise ValueError("图片读取失败")
                image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            except Exception:
                image = np.zeros((Config.IMAGE_SIZE, Config.IMAGE_SIZE, 3), dtype=np.uint8)

            # 重度数据增强：打乱像素排列，破坏结节结构
            # 方法1：随机裁剪一小块区域（模拟非结节的肺组织）
            h, w = image.shape[:2]
            crop_size = int(min(h, w) * 0.5)
            y1 = np.random.randint(0, h - crop_size)
            x1 = np.random.randint(0, w - crop_size)
            image = image[y1:y1+crop_size, x1:x1+crop_size]
            image = cv2.resize(image, (Config.IMAGE_SIZE, Config.IMAGE_SIZE))

            # 方法2：随机水平翻转 + 强烈的颜色扰动
            if np.random.random() > 0.5:
                image = cv2.flip(image, 1)

            # 随机调整亮度和对比度（幅度比正样本大）
            alpha = np.random.uniform(0.3, 1.7)  # 对比度
            beta = np.random.randint(-50, 50)     # 亮度
            image = np.clip(alpha * image + beta, 0, 255).astype(np.uint8)

            if self.transform:
                image = self.transform(image)
            else:
                image = val_transform(image)
            return image, label

        # 读取正样本图片（支持中文路径）
        try:
            image = cv2.imdecode(np.fromfile(img_path, dtype=np.uint8), cv2.IMREAD_COLOR)
            if image is None:
                raise ValueError("图片读取失败")
            image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        except Exception:
            image = np.zeros((Config.IMAGE_SIZE, Config.IMAGE_SIZE, 3), dtype=np.uint8)
            label = 0

        # 应用变换
        if self.transform:
            image = self.transform(image)
        else:
            image = val_transform(image)

        return image, label


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

    # 解冻最后两个残差块（layer3和layer4）进行微调
    for param in model.layer3.parameters():
        param.requires_grad = True
    for param in model.layer4.parameters():
        param.requires_grad = True

    # 修改最后一层（增加正则化）
    num_features = model.fc.in_features
    model.fc = nn.Sequential(
        nn.Linear(num_features, 512),
        nn.ReLU(),
        nn.Dropout(0.7),  # 增加dropout，减少过拟合
        nn.Linear(512, 128),
        nn.ReLU(),
        nn.Dropout(0.5),
        nn.Linear(128, 2)
    )

    return model


# ==================== 训练 ====================

def train_model(model, train_loader, val_loader, device):
    """训练模型"""
    criterion = nn.CrossEntropyLoss()

    # 使用不同的学习率
    optimizer = optim.Adam([
        {'params': model.layer3.parameters(), 'lr': Config.LEARNING_RATE * 0.1},
        {'params': model.layer4.parameters(), 'lr': Config.LEARNING_RATE * 0.1},
        {'params': model.fc.parameters(), 'lr': Config.LEARNING_RATE}
    ])
    scheduler = optim.lr_scheduler.StepLR(optimizer, step_size=5, gamma=0.5)

    best_val_acc = 0.0

    print(f"\n开始训练...")
    print(f"  设备：{device}")
    print(f"  批次大小：{Config.BATCH_SIZE}")
    print(f"  训练轮次：{Config.NUM_EPOCHS}")
    print(f"  学习率：{Config.LEARNING_RATE}")
    print("=" * 60)

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

        print(f"Epoch [{epoch+1:2d}/{Config.NUM_EPOCHS}] "
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

    print("=" * 60)
    print(f"训练完成！最佳验证准确率：{best_val_acc:.2f}%")
    print(f"模型已保存到：{Config.MODEL_SAVE_PATH}")


# ==================== 主函数 ====================

def main():
    print("=" * 60)
    print("肺结节模型微调训练（COCO格式数据）")
    print("=" * 60)

    # 检查数据是否存在
    if not os.path.exists(Config.TRAIN_IMAGE_DIR):
        print(f"\n错误：找不到训练图片目录 {Config.TRAIN_IMAGE_DIR}")
        print("请先下载 COCO 格式的 LUNA16 数据集")
        return

    if not os.path.exists(Config.TRAIN_ANNOTATION):
        print(f"\n错误：找不到训练标注文件 {Config.TRAIN_ANNOTATION}")
        return

    # 创建数据集
    print("\n加载训练数据...")
    train_dataset = COCOLungNoduleDataset(
        Config.TRAIN_IMAGE_DIR,
        Config.TRAIN_ANNOTATION,
        transform=train_transform,
        is_train=True
    )

    print("\n加载验证数据...")
    val_dataset = COCOLungNoduleDataset(
        Config.TEST_IMAGE_DIR,
        Config.TEST_ANNOTATION,
        transform=val_transform,
        is_train=False
    )

    # 创建数据加载器
    train_loader = DataLoader(
        train_dataset,
        batch_size=Config.BATCH_SIZE,
        shuffle=True,
        num_workers=0
    )
    val_loader = DataLoader(
        val_dataset,
        batch_size=Config.BATCH_SIZE,
        shuffle=False,
        num_workers=0
    )

    # 创建模型
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = create_model()
    model = model.to(device)

    print(f"\n模型信息：")
    print(f"  骨干网络：ResNet-50（ImageNet预训练）")
    print(f"  修改层：全连接层 → 256 → 2（结节/非结节）")
    print(f"  设备：{device}")

    # 训练
    train_model(model, train_loader, val_loader, device)

    print("\n训练完成！")
    print(f"模型保存在：{Config.MODEL_SAVE_PATH}")
    print("现在可以运行 step7_test.py 测试模型效果")


if __name__ == "__main__":
    main()
