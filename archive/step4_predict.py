import torchvision.models as models
import torch


def load_model(model_path):
    """
    加载训练好的 ResNet-50 模型

    参数：
        model_path: 模型权重文件路径
    返回：
        model: 加载好权重的模型，已设置为推理模式
    """
    model = models.resnet50(pretrained=False)
    num_features = model.fc.in_features
    model.fc = torch.nn.Linear(num_features, 2)
    model.load_state_dict(torch.load(model_path, map_location='cpu'))
    model.eval()
    return model


def predict(model, input_tensor):
    """
    对预处理后的图片进行预测

    参数：
        model: 加载好的模型
        input_tensor: 预处理后的张量，形状 (1, 3, 224, 224)
    返回：
        dict: {
            "class": "良性" 或 "恶性",
            "benign_prob": 良性概率（0-1），
            "malignant_prob": 恶性概率（0-1）
        }
    """
    with torch.no_grad():
        output = model(input_tensor)
        probabilities = torch.softmax(output, dim=1)

    predicted_class = torch.argmax(probabilities, dim=1).item()

    result = {
        "class": "恶性" if predicted_class == 1 else "良性",
        "benign_prob": round(probabilities[0][0].item(), 4),
        "malignant_prob": round(probabilities[0][1].item(), 4)
    }

    return result


if __name__ == "__main__":
    from step3_preprocess import preprocess_image

    print("第4步：检测/分类模块")
    print("=" * 40)

    # 加载模型
    model_path = "D:/肺结节AI项目/models/resnet50_lung_nodule.pth"
    print(f"正在加载模型：{model_path}")
    model = load_model(model_path)
    print("模型加载成功！")

    # 用随机数据模拟测试
    print("\n用随机数据模拟一次推理：")
    fake_input = torch.randn(1, 3, 224, 224)
    result = predict(model, fake_input)
    print(f"  判断结果：{result['class']}")
    print(f"  良性概率：{result['benign_prob'] * 100}%")
    print(f"  恶性概率：{result['malignant_prob'] * 100}%")

    print("\n第4步完成！")